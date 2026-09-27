from fastapi import HTTPException, Request

from backend.app.security import rate_limiter
from backend.app.runs.models import (
    IdempotencyConflictError,
    InvalidTransitionError,
    RunNotFoundError,
    RunQueueFullError,
)


LOCAL_WORKSPACE_OWNER = 'local-workspace'


def get_workspace_owner(request: Request) -> str:
    client_host = request.client.host if request.client else 'local-client'
    rate_limiter.check(client_host)
    return LOCAL_WORKSPACE_OWNER


def lifecycle_http_error(error: Exception) -> HTTPException:
    if isinstance(error, RunNotFoundError):
        return HTTPException(status_code=404, detail='Run not found.')
    if isinstance(
        error,
        (InvalidTransitionError, IdempotencyConflictError),
    ):
        return HTTPException(status_code=409, detail=str(error))
    if isinstance(error, RunQueueFullError):
        return HTTPException(
            status_code=503,
            detail='Run worker queue is currently full.',
        )
    return HTTPException(status_code=500, detail='Internal server error.')
