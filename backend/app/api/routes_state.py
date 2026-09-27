import asyncio
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from backend.app.api.dependencies import get_workspace_owner, lifecycle_http_error
from backend.app.runs.runtime import run_service
from backend.app.shutdown import shutdown_requested

router = APIRouter()
TERMINAL_STATUSES = {'completed', 'failed', 'cancelled'}


def state_delta(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    """Return only top-level fields whose values changed."""
    return {
        key: value
        for key, value in current.items()
        if key not in previous or previous[key] != value
    }


def sse_event(event: str, data: dict[str, Any], event_id: int) -> str:
    payload = json.dumps(data, separators=(',', ':'), ensure_ascii=False)
    return f'id: {event_id}\nevent: {event}\ndata: {payload}\n\n'


@router.get('/state/{run_id}')
@router.get('/runs/{run_id}')
async def get_state(
    run_id: str,
    owner_id: Annotated[str, Depends(get_workspace_owner)],
):
    try:
        return run_service.state_payload(run_id, owner_id)
    except Exception as error:
        raise lifecycle_http_error(error) from error


@router.get('/runs/{run_id}/events')
async def stream_state(
    run_id: str,
    request: Request,
    owner_id: Annotated[str, Depends(get_workspace_owner)],
):
    async def events():
        previous: dict[str, Any] | None = None
        event_id = 0
        yield 'retry: 1000\n\n'
        while (
            not shutdown_requested.is_set()
            and not await request.is_disconnected()
        ):
            try:
                current = run_service.state_payload(run_id, owner_id)
            except Exception as error:
                http_error = lifecycle_http_error(error)
                event_id += 1
                yield sse_event(
                    'error',
                    {'status': http_error.status_code, 'detail': http_error.detail},
                    event_id,
                )
                return

            update = current if previous is None else state_delta(previous, current)
            if update:
                event_id += 1
                yield sse_event(
                    'snapshot' if previous is None else 'delta',
                    update,
                    event_id,
                )
                previous = current

            if current.get('status') in TERMINAL_STATUSES:
                event_id += 1
                yield sse_event(
                    'end',
                    {'status': current['status']},
                    event_id,
                )
                return

            await asyncio.sleep(0.5)

    return StreamingResponse(
        events(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache, no-transform',
            'X-Accel-Buffering': 'no',
        },
    )
