import hashlib
import json
import logging
import time
from threading import Lock, RLock
from typing import Any, Iterable

from langgraph.types import Command

from backend.app.graph.state import Transaction
from backend.app.observability import bind_run, metrics, trace_span
from backend.app.runs.executor import BoundedRunExecutor
from backend.app.runs.models import (
    ACTIVE_STATUSES,
    InvalidTransitionError,
    RunQueueFullError,
    RunRecord,
    RunStatus,
)
from backend.app.runs.store import RunStore

logger = logging.getLogger(__name__)


def request_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(',', ':'),
        ensure_ascii=False,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _model_dump(value: Any) -> Any:
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    if hasattr(value, 'dict'):
        return value.dict()
    return value


class RunService:
    def __init__(
        self,
        *,
        store: RunStore,
        graph: Any,
        max_workers: int,
        queue_capacity: int,
        retention_hours: int = 24,
        max_active_runs_per_owner: int = 2,
    ):
        self.store = store
        self.graph = graph
        self.executor = BoundedRunExecutor(max_workers, queue_capacity)
        self.retention_hours = retention_hours
        self.max_active_runs_per_owner = max_active_runs_per_owner
        self._shutdown_lock = Lock()
        self._shutdown = False
        self._future_lock = Lock()
        self._futures: dict[str, Any] = {}
        self._recovery_lock = RLock()

    @staticmethod
    def _config(run_id: str) -> dict[str, Any]:
        return {'configurable': {'thread_id': run_id}}

    @staticmethod
    def _initial_state(record: RunRecord) -> dict[str, Any]:
        payload = record.payload
        transactions = [
            Transaction.model_validate(transaction)
            for transaction in payload['transactions']
        ]
        return {
            'thread_id': record.run_id,
            'demo_scenario': payload.get('demo_scenario'),
            'transactions': transactions,
            'categorized': [],
            'deductibility_results': [],
            'pending_clarifications': [],
            'resolved_clarifications': {},
            'unresolved_flags': [],
            'final_report': None,
            'current_node': 'init',
            'errors': [],
        }

    def _override_context(
        self,
        run_id: str,
        answers: list[dict[str, str]],
    ) -> dict[str, dict[str, str]]:
        try:
            snapshot = self.graph.get_state(self._config(run_id))
            categorized = snapshot.values.get('categorized', [])
        except Exception:
            categorized = []
        predictions = {
            str(_model_dump(item).get('transaction_id')): str(
                _model_dump(item).get('predicted_category', 'Unknown')
            )
            for item in categorized
        }
        return {
            str(answer['transaction_id']): {
                'prior_prediction': predictions.get(
                    str(answer['transaction_id']),
                    'Unknown',
                ),
                'downstream_impact': (
                    'Category replaced by human review; tax treatment, '
                    'deduction amount, evidence, and final report are recalculated.'
                ),
            }
            for answer in answers
        }

    def _reserve_capacity(self) -> None:
        with self._shutdown_lock:
            if self._shutdown or not self.executor.reserve():
                metrics.increment('smartwealth_queue_rejections_total')
                raise RunQueueFullError(
                    'Run worker queue is full or shutting down.'
                )

    def _submit_reserved(
        self,
        run_id: str,
        function: Any,
        *args: Any,
    ) -> None:
        future = self.executor.submit_reserved(function, *args)
        with self._future_lock:
            self._futures[run_id] = future

        def finished(completed: Any) -> None:
            with self._future_lock:
                if self._futures.get(run_id) is completed:
                    self._futures.pop(run_id, None)
            with self._shutdown_lock:
                should_recover = not self._shutdown
            if should_recover:
                self.recover()

        future.add_done_callback(finished)

    def start(
        self,
        *,
        owner_id: str,
        idempotency_key: str,
        payload: dict[str, Any],
        idempotency_payload: Any | None = None,
    ) -> tuple[RunRecord, bool]:
        digest = request_hash(
            payload if idempotency_payload is None else idempotency_payload
        )
        existing = self.store.find_idempotent(
            owner_id,
            'start',
            idempotency_key,
            digest,
        )
        if existing is not None:
            return existing, True

        self._reserve_capacity()
        try:
            record, replayed = self.store.create_run(
                owner_id=owner_id,
                idempotency_key=idempotency_key,
                request_hash=digest,
                payload=payload,
                total=len(payload['transactions']),
                retention_hours=self.retention_hours,
                max_active_runs=self.max_active_runs_per_owner,
            )
            if replayed:
                self.executor.release_reservation()
                return record, True
            self._submit_reserved(
                record.run_id,
                self._execute_start,
                record.run_id,
            )
            metrics.increment('smartwealth_runs_submitted_total')
            return record, False
        except Exception:
            self.executor.release_reservation()
            raise

    def resume(
        self,
        *,
        run_id: str,
        owner_id: str,
        idempotency_key: str,
        answers: list[dict[str, str]],
        correlation_id: str = 'unassigned',
    ) -> tuple[RunRecord, bool]:
        digest = request_hash(answers)
        operation = f'resume:{run_id}'
        existing = self.store.find_idempotent(
            owner_id,
            operation,
            idempotency_key,
            digest,
        )
        if existing is not None:
            return existing, True

        self._reserve_capacity()
        try:
            record, replayed = self.store.reserve_resume(
                run_id=run_id,
                owner_id=owner_id,
                idempotency_key=idempotency_key,
                request_hash=digest,
                answers=answers,
                override_context=self._override_context(run_id, answers),
                correlation_id=correlation_id,
            )
            if replayed:
                self.executor.release_reservation()
                return record, True
            self._submit_reserved(
                run_id,
                self._execute_resume,
                run_id,
                answers,
            )
            return record, False
        except Exception:
            self.executor.release_reservation()
            raise

    def _execute_start(self, run_id: str) -> None:
        record = self.store.get(run_id)
        if record.status == RunStatus.CANCELLED:
            return
        if record.status != RunStatus.QUEUED:
            return
        try:
            record = self.store.transition(
                run_id,
                expected_statuses=[RunStatus.QUEUED],
                new_status=RunStatus.RUNNING,
                expected_version=record.version,
                current_node='starting',
                message='Starting audit pipeline.',
            )
        except InvalidTransitionError:
            return
        self._drive_graph(run_id, self._initial_state(record))

    def _execute_resume(
        self,
        run_id: str,
        answers: list[dict[str, str]],
    ) -> None:
        record = self.store.get(run_id)
        if record.status != RunStatus.RUNNING:
            return
        self._drive_graph(run_id, Command(resume=answers))

    def _execute_recovery(self, run_id: str, graph_input: Any) -> None:
        record = self.store.get(run_id)
        if record.status == RunStatus.QUEUED:
            try:
                record = self.store.transition(
                    run_id,
                    expected_statuses=[RunStatus.QUEUED],
                    new_status=RunStatus.RUNNING,
                    expected_version=record.version,
                    current_node='recovery',
                    message='Recovering interrupted audit.',
                )
            except InvalidTransitionError:
                return
        if record.status != RunStatus.RUNNING:
            return
        if graph_input == 'initial':
            graph_input = self._initial_state(record)
        self._drive_graph(run_id, graph_input)

    def _drive_graph(self, run_id: str, graph_input: Any) -> None:
        config = self._config(run_id)
        started = time.perf_counter()
        with bind_run(run_id), trace_span('audit_run'):
            try:
                events = self.graph.stream(
                    graph_input,
                    config,
                    stream_mode='values',
                )
                for _ in events:
                    if self.store.get(run_id).status == RunStatus.CANCELLED:
                        close = getattr(events, 'close', None)
                        if close is not None:
                            close()
                        metrics.increment('smartwealth_runs_cancelled_total')
                        return

                record = self.store.get(run_id)
                if record.status == RunStatus.CANCELLED:
                    metrics.increment('smartwealth_runs_cancelled_total')
                    return
                snapshot = self.graph.get_state(config)
                if snapshot.next:
                    self.store.transition(
                        run_id,
                        expected_statuses=[RunStatus.RUNNING],
                        new_status=RunStatus.WAITING_FOR_INPUT,
                        current_node='auditor_loop',
                        message='Waiting for clarification.',
                    )
                    metrics.increment('smartwealth_runs_waiting_total')
                else:
                    self.store.transition(
                        run_id,
                        expected_statuses=[RunStatus.RUNNING],
                        new_status=RunStatus.COMPLETED,
                        current_node='completed',
                        message='Audit complete.',
                    )
                    metrics.increment('smartwealth_runs_completed_total')
            except Exception as error:
                metrics.increment('smartwealth_runs_failed_total')
                logger.error(
                    'audit_pipeline_failed',
                    extra={
                        'event': 'audit_pipeline_failed',
                        'error_class': type(error).__name__,
                    },
                )
                try:
                    record = self.store.get(run_id)
                    if record.status in ACTIVE_STATUSES:
                        self.store.transition(
                            run_id,
                            expected_statuses=[record.status],
                            new_status=RunStatus.FAILED,
                            error_code='PIPELINE_ERROR',
                            error_message='Audit pipeline failed.',
                            current_node='failed',
                            message='Audit failed.',
                        )
                except Exception as persistence_error:
                    logger.error(
                        'failure_state_persistence_failed',
                        extra={
                            'event': 'failure_state_persistence_failed',
                            'error_class': type(persistence_error).__name__,
                        },
                    )
            finally:
                duration = time.perf_counter() - started
                metrics.observe('smartwealth_run_duration_seconds', duration)
                from backend.app.config import get_settings
                if duration > get_settings().max_run_latency_seconds:
                    metrics.increment('smartwealth_run_latency_budget_exceeded_total')

    @staticmethod
    def _has_interrupt(snapshot: Any) -> bool:
        return bool(
            snapshot.next
            and snapshot.tasks
            and snapshot.tasks[0].interrupts
        )

    def recover(self) -> dict[str, int]:
        with self._recovery_lock:
            self.store.purge_expired()
            return self._recover_unlocked()

    def _recover_unlocked(self) -> dict[str, int]:
        recovered = 0
        waiting = 0
        completed = 0
        failed = 0
        deferred = 0
        for record in self.store.list_recoverable():
            with self._future_lock:
                if record.run_id in self._futures:
                    continue
            config = self._config(record.run_id)
            try:
                snapshot = self.graph.get_state(config)
                has_values = bool(snapshot.values)
            except Exception:
                snapshot = None
                has_values = False

            if record.status == RunStatus.WAITING_FOR_INPUT:
                if snapshot is not None and self._has_interrupt(snapshot):
                    waiting += 1
                    continue
                if snapshot is not None and has_values and not snapshot.next:
                    self.store.transition(
                        record.run_id,
                        expected_statuses=[RunStatus.WAITING_FOR_INPUT],
                        new_status=RunStatus.COMPLETED,
                        current_node='completed',
                        message='Audit complete.',
                    )
                    completed += 1
                else:
                    self.store.transition(
                        record.run_id,
                        expected_statuses=[RunStatus.WAITING_FOR_INPUT],
                        new_status=RunStatus.FAILED,
                        error_code='RECOVERY_STATE_INVALID',
                        error_message='Saved clarification state is unavailable.',
                        current_node='failed',
                        message='Audit recovery failed.',
                    )
                    failed += 1
                continue

            if record.status == RunStatus.RUNNING:
                if snapshot is not None and self._has_interrupt(snapshot):
                    self.store.transition(
                        record.run_id,
                        expected_statuses=[RunStatus.RUNNING],
                        new_status=RunStatus.WAITING_FOR_INPUT,
                        current_node='auditor_loop',
                        message='Waiting for clarification.',
                    )
                    waiting += 1
                    continue
                if snapshot is not None and has_values and not snapshot.next:
                    self.store.transition(
                        record.run_id,
                        expected_statuses=[RunStatus.RUNNING],
                        new_status=RunStatus.COMPLETED,
                        current_node='completed',
                        message='Audit complete.',
                    )
                    completed += 1
                    continue

            if not self.executor.reserve():
                deferred += 1
                continue
            graph_input: Any = None if has_values else 'initial'
            try:
                self._submit_reserved(
                    record.run_id,
                    self._execute_recovery,
                    record.run_id,
                    graph_input,
                )
                recovered += 1
            except Exception:
                self.executor.release_reservation()
                raise
        return {
            'recovered': recovered,
            'waiting': waiting,
            'completed': completed,
            'failed': failed,
            'deferred': deferred,
        }

    def get(self, run_id: str, owner_id: str) -> RunRecord:
        return self.store.get(run_id, owner_id)

    def cancel(self, run_id: str, owner_id: str) -> RunRecord:
        record = self.store.cancel(run_id, owner_id)
        with self._future_lock:
            future = self._futures.get(run_id)
        if future is not None:
            future.cancel()
        return record

    def delete(self, run_id: str, owner_id: str) -> None:
        with self._future_lock:
            future = self._futures.get(run_id)
        if future is not None and not future.done():
            raise InvalidTransitionError(
                'Run worker is still stopping; retry deletion shortly.'
            )
        self.store.delete(run_id, owner_id)

    def purge(self) -> int:
        return self.store.purge_all()

    def audit_events(
        self,
        run_id: str,
        owner_id: str,
    ) -> list[dict[str, Any]]:
        return self.store.audit_events(run_id, owner_id)

    def state_payload(self, run_id: str, owner_id: str) -> dict[str, Any]:
        record = self.store.get(run_id, owner_id)
        config = self._config(run_id)
        try:
            snapshot = self.graph.get_state(config)
            values = snapshot.values or {}
        except Exception:
            snapshot = None
            values = {}

        pending: list[Any] = []
        if (
            record.status == RunStatus.WAITING_FOR_INPUT
            and snapshot is not None
            and self._has_interrupt(snapshot)
        ):
            pending = snapshot.tasks[0].interrupts[0].value
        elif record.status == RunStatus.WAITING_FOR_INPUT:
            pending = values.get('pending_clarifications', [])

        errors = list(values.get('errors', []))
        errors.extend(record.warnings)
        if record.error_message:
            errors.append(record.error_message)
        progress = record.progress.model_dump(mode='json')
        progress['completed'] = record.status == RunStatus.COMPLETED
        audit_trail = self.store.audit_events(run_id, owner_id)
        run_timeline = self.store.timeline_events(run_id, owner_id)
        human_override_ids = list(dict.fromkeys(
            event['transaction_id']
            for event in audit_trail
            if event['event_type'] == 'human_override'
        ))
        return {
            **record.public_dict(),
            'transactions': [
                _model_dump(value)
                for value in values.get('transactions', [])
            ],
            'categorized': [
                _model_dump(value)
                for value in values.get('categorized', [])
            ],
            'deductibility_results': [
                _model_dump(value)
                for value in values.get('deductibility_results', [])
            ],
            'pending_clarifications': [
                _model_dump(value) for value in pending
            ],
            'unresolved_flags': values.get('unresolved_flags', []),
            'human_override_ids': human_override_ids,
            'run_timeline': run_timeline,
            'audit_trail': audit_trail,
            'final_report': (
                _model_dump(values.get('final_report'))
                if values.get('final_report')
                else None
            ),
            'progress': progress,
            'errors': errors,
        }

    def shutdown(self, *, wait: bool = True) -> None:
        with self._shutdown_lock:
            self._shutdown = True
        self.executor.shutdown(wait=wait)
