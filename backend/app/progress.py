"""Persistent progress adapter backed by the authoritative Run record."""
from typing import Any

from backend.app.config import get_settings
from backend.app.runs.models import RunNotFoundError, RunStatus
from backend.app.runs.store import run_store
from backend.app.observability import metrics


class ProgressStore:
    def init(self, run_id: str, total: int = 0) -> None:
        run_store.update_progress(
            run_id,
            current_node='starting',
            message='Initializing audit pipeline.',
            processed=0,
            total=total,
        )

    def update(
        self,
        run_id: str,
        *,
        current_node: str | None = None,
        message: str | None = None,
        processed: int | None = None,
        total: int | None = None,
    ) -> None:
        run_store.update_progress(
            run_id,
            current_node=current_node,
            message=message,
            processed=processed,
            total=total,
        )

    def add_error(self, run_id: str, error: str) -> None:
        run_store.add_warning(run_id, error)

    def record_event(
        self,
        run_id: str,
        *,
        event_type: str,
        stage: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        run_store.append_run_event(
            run_id,
            event_type=event_type,
            stage=stage,
            message=message,
            details=details,
        )

    def complete(self, run_id: str) -> None:
        run_store.update_progress(
            run_id,
            current_node='completed',
            message='Audit complete.',
        )

    def get(self, run_id: str) -> dict[str, Any] | None:
        try:
            record = run_store.get(run_id)
        except RunNotFoundError:
            return None
        result = record.progress.model_dump(mode='json')
        result['completed'] = record.status == RunStatus.COMPLETED
        result['errors'] = list(record.warnings)
        return result

    def clear_all(self) -> None:
        raise RuntimeError(
            'Global progress reset was removed; delete an owner-scoped run.'
        )

    def consume_provider_budget(
        self,
        run_id: str,
        call_count: int = 1,
    ) -> bool:
        settings = get_settings()
        allowed = run_store.consume_provider_budget(
            run_id,
            call_count=call_count,
            estimated_cost_usd=(
                call_count * settings.provider_call_estimated_cost_usd
            ),
            max_calls=settings.max_provider_calls_per_run,
            max_cost_usd=settings.max_estimated_provider_cost_usd,
        )
        if allowed:
            metrics.increment('smartwealth_provider_budgeted_calls_total', call_count)
            metrics.increment(
                'smartwealth_provider_estimated_cost_usd_total',
                call_count * settings.provider_call_estimated_cost_usd,
            )
        else:
            metrics.increment('smartwealth_provider_budget_rejections_total')
        return allowed

    def record_provider_usage(self, run_id: str, response: Any) -> None:
        usage = getattr(response, 'usage_metadata', None) or {}
        response_metadata = getattr(response, 'response_metadata', None) or {}
        usage = usage or response_metadata.get('token_usage', {})
        input_tokens = int(
            usage.get('input_tokens', usage.get('prompt_tokens', 0)) or 0
        )
        output_tokens = int(
            usage.get('output_tokens', usage.get('completion_tokens', 0)) or 0
        )
        if input_tokens or output_tokens:
            run_store.record_provider_usage(
                run_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            metrics.increment('smartwealth_provider_input_tokens_total', input_tokens)
            metrics.increment('smartwealth_provider_output_tokens_total', output_tokens)


progress_store = ProgressStore()
