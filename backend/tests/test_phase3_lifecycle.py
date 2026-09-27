import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.runs.models import (
    IdempotencyConflictError,
    InvalidTransitionError,
    RunNotFoundError,
    RunQueueFullError,
    RunStatus,
)
from backend.app.runs.service import RunService
from backend.app.runs.store import RunStore


def payload(description: str = 'Office purchase') -> dict:
    return {
        'transactions': [
            {
                'transaction_id': 'TXN-1',
                'date': '2025-01-01',
                'merchant': 'Example Merchant',
                'amount': 100.0,
                'category': '',
                'description': description,
            }
        ],
    }


def api_payload(description: str = 'Office purchase') -> dict:
    return {
        'transactions': [
            {
                'date': '2025-01-01',
                'merchant': 'Example Merchant',
                'amount': 100.0,
                'description': description,
            }
        ],
        'data_processing_consent': True,
    }


AUTH_HEADERS = {}


def snapshot(*, values=None, next_nodes=(), pending=None):
    tasks = ()
    if pending is not None:
        interrupt = SimpleNamespace(value=pending)
        tasks = (SimpleNamespace(interrupts=(interrupt,)),)
    return SimpleNamespace(
        values=values or {},
        next=tuple(next_nodes),
        tasks=tasks,
    )


def wait_for_status(
    store: RunStore,
    run_id: str,
    expected: RunStatus,
    timeout: float = 3.0,
):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = store.get(run_id)
        if record.status == expected:
            return record
        time.sleep(0.01)
    raise AssertionError(
        f'Run {run_id} did not reach {expected}; '
        f'last status was {store.get(run_id).status}.'
    )


class CompleteGraph:
    def __init__(self):
        self.snapshots = {}
        self.calls = 0

    def stream(self, graph_input, config, stream_mode):
        run_id = config['configurable']['thread_id']
        self.calls += 1
        yield {'node': 'complete'}
        self.snapshots[run_id] = snapshot(
            values={'final_report': {'status': 'done'}},
        )

    def get_state(self, config):
        run_id = config['configurable']['thread_id']
        return self.snapshots.get(run_id, snapshot())


class WaitThenCompleteGraph(CompleteGraph):
    def __init__(self, block_resume: bool = False):
        super().__init__()
        self.block_resume = block_resume
        self.resume_started = Event()
        self.release_resume = Event()

    def stream(self, graph_input, config, stream_mode):
        run_id = config['configurable']['thread_id']
        self.calls += 1
        is_resume = hasattr(graph_input, 'resume')
        if not is_resume:
            pending = [
                {
                    'transaction_id': 'TXN-1',
                    'question': 'Which category applies?',
                }
            ]
            yield {'node': 'auditor_loop'}
            self.snapshots[run_id] = snapshot(
                values={'pending_clarifications': pending},
                next_nodes=('auditor_loop',),
                pending=pending,
            )
            return
        self.resume_started.set()
        if self.block_resume:
            self.release_resume.wait(timeout=3)
        yield {'node': 'complete'}
        self.snapshots[run_id] = snapshot(
            values={'final_report': {'status': 'done'}},
        )


class FailingGraph(CompleteGraph):
    def stream(self, graph_input, config, stream_mode):
        if False:
            yield None
        raise RuntimeError('provider details must not escape')


class BlockingGraph(CompleteGraph):
    def __init__(self):
        super().__init__()
        self.release = Event()
        self.started = Event()
        self.lock = Lock()
        self.active = 0
        self.max_active = 0

    def stream(self, graph_input, config, stream_mode):
        run_id = config['configurable']['thread_id']
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            if self.active >= 1:
                self.started.set()
        try:
            yield {'node': 'started'}
            self.release.wait(timeout=3)
            yield {'node': 'complete'}
            self.snapshots[run_id] = snapshot(
                values={'final_report': {'status': 'done'}},
            )
        finally:
            with self.lock:
                self.active -= 1


@pytest.fixture
def store(tmp_path: Path) -> RunStore:
    return RunStore(tmp_path / 'lifecycle.sqlite')


def make_service(
    store: RunStore,
    graph,
    *,
    workers: int = 2,
    queue_capacity: int = 4,
) -> RunService:
    return RunService(
        store=store,
        graph=graph,
        max_workers=workers,
        queue_capacity=queue_capacity,
    )


def test_start_uses_server_uuid_and_is_idempotent(store):
    service = make_service(store, CompleteGraph())
    try:
        first, replayed = service.start(
            owner_id='owner-a',
            idempotency_key='start-key-0001',
            payload=payload(),
        )
        second, second_replayed = service.start(
            owner_id='owner-a',
            idempotency_key='start-key-0001',
            payload=payload(),
        )

        assert uuid.UUID(first.run_id)
        assert replayed is False
        assert second_replayed is True
        assert second.run_id == first.run_id
        with pytest.raises(IdempotencyConflictError):
            service.start(
                owner_id='owner-a',
                idempotency_key='start-key-0001',
                payload=payload('Different request'),
            )
        wait_for_status(store, first.run_id, RunStatus.COMPLETED)
    finally:
        service.shutdown()


def test_interrupt_waits_and_idempotent_resume_completes(store):
    graph = WaitThenCompleteGraph()
    service = make_service(store, graph)
    try:
        run, _ = service.start(
            owner_id='owner-a',
            idempotency_key='start-key-0002',
            payload=payload(),
        )
        waiting = wait_for_status(
            store,
            run.run_id,
            RunStatus.WAITING_FOR_INPUT,
        )
        assert waiting.status != RunStatus.COMPLETED
        state = service.state_payload(run.run_id, 'owner-a')
        assert state['pending_clarifications'][0]['transaction_id'] == 'TXN-1'

        resumed, replayed = service.resume(
            run_id=run.run_id,
            owner_id='owner-a',
            idempotency_key='resume-key-0001',
            answers=[{'transaction_id': 'TXN-1', 'answer': 'Office Supplies'}],
        )
        duplicate, duplicate_replayed = service.resume(
            run_id=run.run_id,
            owner_id='owner-a',
            idempotency_key='resume-key-0001',
            answers=[{'transaction_id': 'TXN-1', 'answer': 'Office Supplies'}],
        )
        assert resumed.status == RunStatus.RUNNING
        assert replayed is False
        assert duplicate.run_id == run.run_id
        assert duplicate_replayed is True
        wait_for_status(store, run.run_id, RunStatus.COMPLETED)
    finally:
        service.shutdown()


def test_simultaneous_resume_allows_one_transition(store):
    graph = WaitThenCompleteGraph(block_resume=True)
    service = make_service(store, graph, workers=2)
    try:
        run, _ = service.start(
            owner_id='owner-a',
            idempotency_key='start-key-0003',
            payload=payload(),
        )
        wait_for_status(store, run.run_id, RunStatus.WAITING_FOR_INPUT)

        def resume(key):
            return service.resume(
                run_id=run.run_id,
                owner_id='owner-a',
                idempotency_key=key,
                answers=[
                    {
                        'transaction_id': 'TXN-1',
                        'answer': 'Office Supplies',
                    }
                ],
            )

        with ThreadPoolExecutor(max_workers=2) as callers:
            futures = [
                callers.submit(resume, 'resume-concurrent-a'),
                callers.submit(resume, 'resume-concurrent-b'),
            ]
            outcomes = []
            for future in futures:
                try:
                    outcomes.append(future.result())
                except InvalidTransitionError:
                    outcomes.append('conflict')
        assert sum(outcome == 'conflict' for outcome in outcomes) == 1
        assert graph.resume_started.wait(timeout=2)
        graph.release_resume.set()
        wait_for_status(store, run.run_id, RunStatus.COMPLETED)
    finally:
        graph.release_resume.set()
        service.shutdown()


def test_exception_sets_failed_not_completed(store):
    service = make_service(store, FailingGraph())
    try:
        run, _ = service.start(
            owner_id='owner-a',
            idempotency_key='start-key-0004',
            payload=payload(),
        )
        failed = wait_for_status(store, run.run_id, RunStatus.FAILED)
        assert failed.error_code == 'PIPELINE_ERROR'
        assert failed.error_message == 'Audit pipeline failed.'
    finally:
        service.shutdown()


def test_cancel_and_reset_during_running_are_safe(store):
    graph = BlockingGraph()
    service = make_service(store, graph, workers=1)
    run_id = None
    try:
        run, _ = service.start(
            owner_id='owner-a',
            idempotency_key='start-key-0005',
            payload=payload(),
        )
        run_id = run.run_id
        assert graph.started.wait(timeout=2)
        wait_for_status(store, run_id, RunStatus.RUNNING)

        with pytest.raises(InvalidTransitionError):
            service.delete(run_id, 'owner-a')
        cancelled = service.cancel(run_id, 'owner-a')
        assert cancelled.status == RunStatus.CANCELLED
        with pytest.raises(InvalidTransitionError):
            service.delete(run_id, 'owner-a')

        graph.release.set()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                service.delete(run_id, 'owner-a')
                break
            except InvalidTransitionError:
                time.sleep(0.01)
        with pytest.raises(RunNotFoundError):
            store.get(run_id)
    finally:
        graph.release.set()
        service.shutdown()


def test_bounded_multi_worker_queue(store):
    graph = BlockingGraph()
    service = make_service(
        store,
        graph,
        workers=2,
        queue_capacity=0,
    )
    try:
        first, _ = service.start(
            owner_id='owner-a',
            idempotency_key='multi-worker-1',
            payload=payload('First'),
        )
        second, _ = service.start(
            owner_id='owner-a',
            idempotency_key='multi-worker-2',
            payload=payload('Second'),
        )
        deadline = time.monotonic() + 2
        while graph.max_active < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert graph.max_active == 2
        with pytest.raises(RunQueueFullError):
            service.start(
                owner_id='owner-a',
                idempotency_key='multi-worker-3',
                payload=payload('Third'),
            )
        graph.release.set()
        wait_for_status(store, first.run_id, RunStatus.COMPLETED)
        wait_for_status(store, second.run_id, RunStatus.COMPLETED)
    finally:
        graph.release.set()
        service.shutdown()


def test_restart_recovery_handles_queued_running_and_interrupt(store):
    graph = CompleteGraph()
    queued, _ = store.create_run(
        owner_id='owner-a',
        idempotency_key='recover-queued',
        request_hash='hash-queued',
        payload=payload('Queued'),
        total=1,
    )
    interrupted, _ = store.create_run(
        owner_id='owner-a',
        idempotency_key='recover-interrupted',
        request_hash='hash-interrupted',
        payload=payload('Interrupted'),
        total=1,
    )
    interrupted = store.transition(
        interrupted.run_id,
        expected_statuses=[RunStatus.QUEUED],
        new_status=RunStatus.RUNNING,
        expected_version=interrupted.version,
    )
    pending = [{'transaction_id': 'TXN-1', 'question': 'Confirm category'}]
    graph.snapshots[interrupted.run_id] = snapshot(
        values={'pending_clarifications': pending},
        next_nodes=('auditor_loop',),
        pending=pending,
    )

    completed_checkpoint, _ = store.create_run(
        owner_id='owner-a',
        idempotency_key='recover-completed',
        request_hash='hash-completed',
        payload=payload('Completed'),
        total=1,
    )
    completed_checkpoint = store.transition(
        completed_checkpoint.run_id,
        expected_statuses=[RunStatus.QUEUED],
        new_status=RunStatus.RUNNING,
        expected_version=completed_checkpoint.version,
    )
    graph.snapshots[completed_checkpoint.run_id] = snapshot(
        values={'final_report': {'status': 'done'}},
    )

    service = make_service(store, graph)
    try:
        result = service.recover()
        assert result['recovered'] == 1
        assert result['waiting'] == 1
        assert result['completed'] == 1
        wait_for_status(store, queued.run_id, RunStatus.COMPLETED)
        assert store.get(interrupted.run_id).status == RunStatus.WAITING_FOR_INPUT
        assert store.get(completed_checkpoint.run_id).status == RunStatus.COMPLETED
    finally:
        service.shutdown()


def test_shutdown_rejects_new_work(store):
    service = make_service(store, CompleteGraph())
    service.shutdown()
    with pytest.raises(RunQueueFullError):
        service.start(
            owner_id='owner-a',
            idempotency_key='after-shutdown',
            payload=payload(),
        )


def test_recovery_drains_more_runs_than_queue_capacity(store):
    graph = CompleteGraph()
    runs = []
    for index in range(3):
        run, _ = store.create_run(
            owner_id='owner-a',
            idempotency_key=f'drain-recovery-{index}',
            request_hash=f'drain-hash-{index}',
            payload=payload(f'Recovery {index}'),
            total=1,
        )
        runs.append(run)
    service = make_service(
        store,
        graph,
        workers=1,
        queue_capacity=0,
    )
    try:
        service.recover()
        for run in runs:
            wait_for_status(store, run.run_id, RunStatus.COMPLETED)
    finally:
        service.shutdown()


@pytest.mark.parametrize(
    'node_name',
    ['extraction', 'corrective_rag', 'report'],
)
def test_restart_resumes_persisted_graph_node(store, node_name):
    graph = CompleteGraph()
    run, _ = store.create_run(
        owner_id='owner-a',
        idempotency_key=f'recover-node-{node_name}',
        request_hash=f'hash-node-{node_name}',
        payload=payload(node_name),
        total=1,
    )
    running = store.transition(
        run.run_id,
        expected_statuses=[RunStatus.QUEUED],
        new_status=RunStatus.RUNNING,
        expected_version=run.version,
    )
    graph.snapshots[run.run_id] = snapshot(
        values={'current_node': node_name},
        next_nodes=(node_name,),
    )
    service = make_service(store, graph, workers=1)
    try:
        recovery = service.recover()
        assert recovery['recovered'] == 1
        wait_for_status(store, running.run_id, RunStatus.COMPLETED)
    finally:
        service.shutdown()


def test_owner_scope_optimistic_version_and_purge_guard(store):
    run, _ = store.create_run(
        owner_id='owner-a',
        idempotency_key='store-guard',
        request_hash='hash',
        payload=payload(),
        total=1,
    )
    with pytest.raises(RunNotFoundError):
        store.get(run.run_id, 'owner-b')
    with pytest.raises(InvalidTransitionError):
        store.purge_all()
    running = store.transition(
        run.run_id,
        expected_statuses=[RunStatus.QUEUED],
        new_status=RunStatus.RUNNING,
        expected_version=run.version,
    )
    with pytest.raises(InvalidTransitionError):
        store.transition(
            run.run_id,
            expected_statuses=[RunStatus.RUNNING],
            new_status=RunStatus.COMPLETED,
            expected_version=run.version,
        )
    store.cancel(run.run_id, 'owner-a')
    assert store.purge_all() == 1


def test_api_status_codes_and_validation(store, monkeypatch):
    import backend.app.api.routes_clarify as clarify_routes
    import backend.app.api.routes_run as run_routes
    import backend.app.api.routes_state as state_routes

    service = make_service(store, WaitThenCompleteGraph())
    monkeypatch.setattr(run_routes, 'run_service', service)
    monkeypatch.setattr(clarify_routes, 'run_service', service)
    monkeypatch.setattr(state_routes, 'run_service', service)

    app = FastAPI()

    @app.middleware('http')
    async def attach_correlation_id(request, call_next):
        request.state.correlation_id = request.headers.get(
            'X-Request-ID',
            'generated-test-correlation',
        )
        return await call_next(request)

    app.include_router(run_routes.router, prefix='/api')
    app.include_router(clarify_routes.router, prefix='/api')
    app.include_router(state_routes.router, prefix='/api')
    client = TestClient(app)
    try:
        missing_key = client.post(
            '/api/run',
            json=api_payload(),
            headers=AUTH_HEADERS,
        )
        assert missing_key.status_code == 422

        started = client.post(
            '/api/run',
            json=api_payload(),
            headers={
                **AUTH_HEADERS,
                'Idempotency-Key': 'api-start-key',
            },
        )
        assert started.status_code == 202
        assert started.headers['Idempotency-Replayed'] == 'false'
        run_id = started.json()['run_id']

        replayed_start = client.post(
            '/api/run',
            json=api_payload(),
            headers={
                **AUTH_HEADERS,
                'Idempotency-Key': 'api-start-key',
            },
        )
        assert replayed_start.status_code == 202
        assert replayed_start.headers['Idempotency-Replayed'] == 'true'
        assert replayed_start.json()['run_id'] == run_id

        conflicting_start = client.post(
            '/api/run',
            json=api_payload('Changed request'),
            headers={
                **AUTH_HEADERS,
                'Idempotency-Key': 'api-start-key',
            },
        )
        assert conflicting_start.status_code == 409

        wait_for_status(store, run_id, RunStatus.WAITING_FOR_INPUT)

        missing = client.get(
            '/api/state/missing-run',
            headers=AUTH_HEADERS,
        )
        assert missing.status_code == 404
        invalid_resume = client.post(
            '/api/resume/missing-run',
            json=[{'transaction_id': 'TXN-1', 'answer': 'Office Supplies'}],
            headers={
                **AUTH_HEADERS,
                'Idempotency-Key': 'api-resume-key',
            },
        )
        assert invalid_resume.status_code == 404
        active_delete = client.delete(
            f'/api/runs/{run_id}',
            headers=AUTH_HEADERS,
        )
        assert active_delete.status_code == 409

        answers = [
            {
                'transaction_id': 'TXN-1',
                'answer': 'Office Supplies',
            }
        ]
        resumed = client.post(
            f'/api/resume/{run_id}',
            json=answers,
            headers={
                **AUTH_HEADERS,
                'Idempotency-Key': 'api-resume-key-2',
                'X-Request-ID': 'api-correlation-0001',
            },
        )
        assert resumed.status_code == 202
        assert resumed.headers['Idempotency-Replayed'] == 'false'

        replayed_resume = client.post(
            f'/api/resume/{run_id}',
            json=answers,
            headers={
                **AUTH_HEADERS,
                'Idempotency-Key': 'api-resume-key-2',
                'X-Request-ID': 'api-correlation-0001',
            },
        )
        assert replayed_resume.status_code == 202
        assert replayed_resume.headers['Idempotency-Replayed'] == 'true'
        assert replayed_resume.json()['run_id'] == run_id

        events = client.get(
            f'/api/runs/{run_id}/audit',
            headers=AUTH_HEADERS,
        )
        assert events.status_code == 200
        assert len(events.json()['events']) == 1
        event = events.json()['events'][0]
        assert event['event_type'] == 'human_override'
        assert event['correlation_id'] == 'api-correlation-0001'
        assert event['previous_hash'] == 'GENESIS'
        assert event['event_hash']

        wait_for_status(store, run_id, RunStatus.COMPLETED)
        deleted = client.delete(
            f'/api/runs/{run_id}',
            headers=AUTH_HEADERS,
        )
        assert deleted.status_code == 204
        assert client.get(
            f'/api/state/{run_id}',
            headers=AUTH_HEADERS,
        ).status_code == 404
    finally:
        if 'run_id' in locals():
            try:
                service.cancel(run_id, 'local-demo')
            except (RunNotFoundError, InvalidTransitionError):
                pass
        service.shutdown()


def test_api_cancel_then_delete_running_work(store, monkeypatch):
    import backend.app.api.routes_run as run_routes
    import backend.app.api.routes_state as state_routes

    graph = BlockingGraph()
    service = make_service(store, graph, workers=1)
    monkeypatch.setattr(run_routes, 'run_service', service)
    monkeypatch.setattr(state_routes, 'run_service', service)

    app = FastAPI()
    app.include_router(run_routes.router, prefix='/api')
    app.include_router(state_routes.router, prefix='/api')
    client = TestClient(app)
    run_id = None
    try:
        started = client.post(
            '/api/run',
            json=api_payload(),
            headers={
                **AUTH_HEADERS,
                'Idempotency-Key': 'api-cancel-key',
            },
        )
        assert started.status_code == 202
        run_id = started.json()['run_id']
        assert graph.started.wait(timeout=2)
        wait_for_status(store, run_id, RunStatus.RUNNING)

        cancelled = client.post(
            f'/api/runs/{run_id}/cancel',
            headers=AUTH_HEADERS,
        )
        assert cancelled.status_code == 202
        assert cancelled.json()['status'] == RunStatus.CANCELLED.value

        stopping_delete = client.delete(
            f'/api/runs/{run_id}',
            headers=AUTH_HEADERS,
        )
        assert stopping_delete.status_code in {204, 409}

        if stopping_delete.status_code == 409:
            graph.release.set()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                deleted = client.delete(
                    f'/api/runs/{run_id}',
                    headers=AUTH_HEADERS,
                )
                if deleted.status_code == 204:
                    break
                assert deleted.status_code == 409
                time.sleep(0.01)
            else:
                raise AssertionError('Cancelled run was not deletable after worker exit.')

        assert client.get(
            f'/api/state/{run_id}',
            headers=AUTH_HEADERS,
        ).status_code == 404
    finally:
        graph.release.set()
        service.shutdown()


def test_unexpected_lifecycle_errors_map_to_safe_500():
    from backend.app.api.dependencies import lifecycle_http_error

    response = lifecycle_http_error(
        RuntimeError('sensitive provider failure details')
    )
    assert response.status_code == 500
    assert response.detail == 'Internal server error.'


def test_real_offline_graph_wait_resume_and_complete():
    from backend.app.graph.builder import graph
    from backend.app.runs.store import run_store

    service = make_service(run_store, graph, workers=1)
    key_suffix = uuid.uuid4().hex
    run_id = None
    try:
        run, _ = service.start(
            owner_id='phase3-integration',
            idempotency_key=f'integration-start-{key_suffix}',
            payload=payload('???'),
        )
        run_id = run.run_id
        wait_for_status(
            run_store,
            run_id,
            RunStatus.WAITING_FOR_INPUT,
            timeout=5,
        )
        service.resume(
            run_id=run_id,
            owner_id='phase3-integration',
            idempotency_key=f'integration-resume-{key_suffix}',
            answers=[
                {
                    'transaction_id': 'TXN-1',
                    'answer': 'Office Supplies',
                }
            ],
        )
        completed = wait_for_status(
            run_store,
            run_id,
            RunStatus.COMPLETED,
            timeout=5,
        )
        assert completed.error_code is None
        assert service.state_payload(
            run_id,
            'phase3-integration',
        )['final_report'] is not None
    finally:
        if run_id is not None:
            current = run_store.get(run_id)
            if current.status in {
                RunStatus.QUEUED,
                RunStatus.RUNNING,
                RunStatus.WAITING_FOR_INPUT,
            }:
                service.cancel(run_id, 'phase3-integration')
        service.shutdown()
        if run_id is not None:
            run_store.delete(run_id, 'phase3-integration')
