import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.app.api.routes_state import router, sse_event, state_delta


AUTH = {}


def test_state_delta_emits_only_changed_top_level_fields():
    previous = {'status': 'running', 'progress': {'processed': 1}, 'rows': [1, 2]}
    current = {'status': 'running', 'progress': {'processed': 2}, 'rows': [1, 2]}

    assert state_delta(previous, current) == {'progress': {'processed': 2}}


def test_sse_event_is_compact_and_named():
    encoded = sse_event('delta', {'status': 'running'}, 7)

    assert encoded == 'id: 7\nevent: delta\ndata: {"status":"running"}\n\n'


def test_stream_sends_snapshot_then_terminal_event(monkeypatch):
    import backend.app.api.routes_state as routes

    captured = {}

    class StubService:
        def state_payload(self, run_id, owner_id):
            captured.update(run_id=run_id, owner_id=owner_id)
            return {
                'run_id': run_id,
                'status': 'completed',
                'version': 3,
                'transactions': [],
                'categorized': [],
                'deductibility_results': [],
                'pending_clarifications': [],
                'unresolved_flags': [],
                'human_override_ids': [],
                'progress': {'completed': True},
                'errors': [],
                'final_report': None,
            }

    monkeypatch.setattr(routes, 'run_service', StubService())
    app = FastAPI()
    app.include_router(router, prefix='/api')
    client = TestClient(app)

    response = client.get('/api/runs/run-1/events', headers=AUTH)

    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/event-stream')
    assert 'event: snapshot' in response.text
    assert 'event: end' in response.text
    assert captured == {'run_id': 'run-1', 'owner_id': 'local-workspace'}


def test_stream_stops_when_server_shutdown_is_requested(monkeypatch):
    import backend.app.api.routes_state as routes

    class StubRequest:
        async def is_disconnected(self):
            return False

    class StubService:
        def state_payload(self, _run_id, _owner_id):
            raise AssertionError('Shutdown stream must not request another snapshot.')

    async def exercise():
        response = await routes.stream_state(
            'run-active',
            StubRequest(),
            'local-workspace',
        )
        iterator = response.body_iterator
        assert await anext(iterator) == 'retry: 1000\n\n'
        routes.shutdown_requested.set()
        with pytest.raises(StopAsyncIteration):
            await anext(iterator)

    monkeypatch.setattr(routes, 'run_service', StubService())
    routes.shutdown_requested.clear()
    try:
        asyncio.run(exercise())
    finally:
        routes.shutdown_requested.clear()
