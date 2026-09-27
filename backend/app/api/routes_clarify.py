from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.api.dependencies import get_workspace_owner, lifecycle_http_error
from backend.app.tools.categorizer_tools import VALID_CATEGORIES
from backend.app.runs.runtime import run_service

router = APIRouter()


class ClarificationAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    transaction_id: str = Field(min_length=1, max_length=128)
    answer: str = Field(min_length=1, max_length=100)

    @field_validator('answer')
    @classmethod
    def validate_answer(cls, value: str) -> str:
        if value not in VALID_CATEGORIES:
            raise ValueError('answer must be an allowed category')
        return value


@router.get('/clarifications/{run_id}')
async def get_clarifications(
    run_id: str,
    owner_id: Annotated[str, Depends(get_workspace_owner)],
):
    try:
        state = run_service.state_payload(run_id, owner_id)
    except Exception as error:
        raise lifecycle_http_error(error) from error
    return {
        'status': state['status'],
        'pending': state['pending_clarifications'],
    }


@router.post('/resume/{run_id}', status_code=status.HTTP_202_ACCEPTED)
async def resume_graph(
    run_id: str,
    answers: Annotated[
        list[ClarificationAnswer],
        Body(min_length=1),
    ],
    response: Response,
    request: Request,
    owner_id: Annotated[str, Depends(get_workspace_owner)],
    idempotency_key: Annotated[
        str,
        Header(alias='Idempotency-Key', min_length=8, max_length=128),
    ],
):
    payload = [answer.model_dump(mode='json') for answer in answers]
    try:
        record, replayed = run_service.resume(
            run_id=run_id,
            owner_id=owner_id,
            idempotency_key=idempotency_key,
            answers=payload,
            correlation_id=getattr(
                request.state,
                'correlation_id',
                'unassigned',
            ),
        )
    except Exception as error:
        raise lifecycle_http_error(error) from error
    response.headers['Idempotency-Replayed'] = str(replayed).lower()
    return {
        **record.public_dict(),
        'replayed': replayed,
    }


@router.get('/runs/{run_id}/audit')
async def get_human_override_audit(
    run_id: str,
    owner_id: Annotated[str, Depends(get_workspace_owner)],
):
    try:
        return {
            'events': run_service.audit_events(
                run_id,
                owner_id,
            )
        }
    except Exception as error:
        raise lifecycle_http_error(error) from error
