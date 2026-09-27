import uuid
from datetime import date
from typing import Literal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.api.dependencies import (
    get_workspace_owner,
    lifecycle_http_error,
)
from backend.app.config import get_settings
from backend.app.graph.state import Transaction
from backend.app.runs.runtime import run_service

router = APIRouter()
settings = get_settings()


class TransactionInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    date: date
    merchant: str = Field(min_length=1)
    amount: float = Field(gt=0, le=1_000_000_000, allow_inf_nan=False)
    description: str = ''

    @field_validator('merchant', 'description')
    @classmethod
    def cap_untrusted_text(cls, value: str) -> str:
        if len(value) > settings.max_string_length:
            raise ValueError(
                f'text cannot exceed {settings.max_string_length} characters'
            )
        return value


class RunRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    transactions: list[TransactionInput] = Field(min_length=1)
    data_processing_consent: Literal[True]
    demo_scenario: Literal['provider_429_fallback'] | None = None

    @field_validator('transactions')
    @classmethod
    def cap_rows(cls, value: list[TransactionInput]) -> list[TransactionInput]:
        if len(value) > settings.max_transactions_per_run:
            raise ValueError(
                f'cannot exceed {settings.max_transactions_per_run} transactions'
            )
        return value


@router.post('/run', status_code=status.HTTP_202_ACCEPTED)
async def run_graph(
    request: RunRequest,
    response: Response,
    owner_id: Annotated[str, Depends(get_workspace_owner)],
    idempotency_key: Annotated[
        str,
        Header(alias='Idempotency-Key', min_length=8, max_length=128),
    ],
):
    if request.demo_scenario and not settings.offline_demo_mode:
        raise HTTPException(
            status_code=409,
            detail='Controlled failure scenarios require OFFLINE_DEMO_MODE=true.',
        )
    payload = {
        'transactions': [
            Transaction(
                transaction_id=f'TXN-{uuid.uuid4()}',
                date=transaction.date.isoformat(),
                merchant=transaction.merchant,
                amount=transaction.amount,
                category='',
                description=transaction.description,
            ).model_dump(mode='json')
            for transaction in request.transactions
        ],
        'demo_scenario': request.demo_scenario,
    }
    try:
        record, replayed = run_service.start(
            owner_id=owner_id,
            idempotency_key=idempotency_key,
            payload=payload,
            idempotency_payload=request.model_dump(mode='json'),
        )
    except Exception as error:
        raise lifecycle_http_error(error) from error
    response.headers['Idempotency-Replayed'] = str(replayed).lower()
    return {
        **record.public_dict(),
        'replayed': replayed,
        'retention': {
            'mode': settings.run_storage_mode,
            'expires_at': record.expires_at,
            'delete_endpoint': f'/api/runs/{record.run_id}',
        },
    }


@router.post(
    '/runs/{run_id}/cancel',
    status_code=status.HTTP_202_ACCEPTED,
)
async def cancel_run(
    run_id: str,
    owner_id: Annotated[str, Depends(get_workspace_owner)],
):
    try:
        return run_service.cancel(
            run_id,
            owner_id,
        ).public_dict()
    except Exception as error:
        raise lifecycle_http_error(error) from error


@router.delete('/runs/{run_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(
    run_id: str,
    owner_id: Annotated[str, Depends(get_workspace_owner)],
) -> Response:
    try:
        run_service.delete(run_id, owner_id)
    except Exception as error:
        raise lifecycle_http_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
