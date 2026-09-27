from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    QUEUED = 'queued'
    RUNNING = 'running'
    WAITING_FOR_INPUT = 'waiting_for_input'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


ACTIVE_STATUSES = {
    RunStatus.QUEUED,
    RunStatus.RUNNING,
    RunStatus.WAITING_FOR_INPUT,
}
TERMINAL_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
}


class RunProgress(BaseModel):
    current_node: str = 'starting'
    message: str = 'Queued for processing.'
    processed: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)


class RunRecord(BaseModel):
    run_id: str
    owner_id: str
    status: RunStatus
    created_at: str
    updated_at: str
    expires_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    progress: RunProgress
    version: int = Field(ge=1)
    cancel_requested: bool = False
    warnings: list[str] = Field(default_factory=list)
    provider_calls: int = Field(default=0, ge=0)
    provider_input_tokens: int = Field(default=0, ge=0)
    provider_output_tokens: int = Field(default=0, ge=0)
    estimated_provider_cost_usd: float = Field(default=0.0, ge=0.0)
    payload: dict[str, Any] = Field(default_factory=dict, exclude=True)

    def public_dict(self) -> dict[str, Any]:
        return self.model_dump(mode='json', exclude={'payload'})


class RunLifecycleError(Exception):
    pass


class RunNotFoundError(RunLifecycleError):
    pass


class InvalidTransitionError(RunLifecycleError):
    pass


class IdempotencyConflictError(RunLifecycleError):
    pass


class RunQueueFullError(RunLifecycleError):
    pass
