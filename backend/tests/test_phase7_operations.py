import json
import logging
from pathlib import Path
from threading import Event

import pytest

from backend.app.api import routes_ops
from backend.app.backup import sqlite_backup, sqlite_restore
from backend.app.errors import CircuitOpenError, ErrorClass, ProviderBudgetError
from backend.app.migrations import migration_files
from backend.app.observability import JsonFormatter, MetricRegistry
from backend.app.rag.versioning import (
    chroma_release_path,
    collection_name,
    validate_corpus_version,
)
from backend.app.resilience import (
    CircuitBreaker,
    RetryPolicy,
    TTLCache,
    call_with_resilience,
)
from backend.app.runs.executor import BoundedRunExecutor
from backend.app.runs.store import _PostgresConnection
from backend.app.runs.store import RunStore
from backend.app.progress import ProgressStore
from scripts.load_test import percentile, run_load
from backend.app.config import get_settings


def test_metrics_render_prometheus_without_high_cardinality_labels():
    registry = MetricRegistry()
    registry.increment('smartwealth_runs_total', 2)
    registry.gauge('smartwealth_queue_depth', 3)
    registry.observe('smartwealth_latency_seconds', 0.25)
    rendered = registry.render_prometheus()
    assert 'smartwealth_runs_total 2' in rendered
    assert 'smartwealth_queue_depth 3' in rendered
    assert 'smartwealth_latency_seconds_count 1' in rendered
    assert 'run_id' not in rendered


def test_json_formatter_emits_machine_readable_context():
    record = logging.LogRecord(
        'phase7', logging.INFO, __file__, 1, 'ready', (), None
    )
    payload = json.loads(JsonFormatter().format(record))
    assert payload['level'] == 'info'
    assert payload['message'] == 'ready'
    assert {'request_id', 'trace_id', 'run_id', 'provider_attempt_id'} <= payload.keys()


def test_retry_uses_bounded_jitter_and_attempt_ids():
    call_count = [0]
    attempts = []
    delays = []
    breaker = CircuitBreaker('retry-test', failure_threshold=5)

    def flaky():
        call_count[0] += 1
        if call_count[0] < 3:
            raise TimeoutError('timeout')
        return 'ok'

    result = call_with_resilience(
        flaky,
        name='test_provider',
        policy=RetryPolicy(3, 1.0, 2.0, 0.25),
        breaker=breaker,
        is_retryable=lambda error: isinstance(error, TimeoutError),
        sleep=delays.append,
        random_value=lambda: 0.5,
        on_attempt=lambda attempt_id, number: attempts.append((attempt_id, number)),
    )
    assert result == 'ok'
    assert delays == [1.0, 2.0]
    assert call_count[0] == 3
    assert len({item[0] for item in attempts}) == 3


def test_provider_outage_opens_and_recovers_circuit():
    clock = [0.0]
    breaker = CircuitBreaker(
        'provider-outage',
        failure_threshold=2,
        recovery_seconds=10,
        clock=lambda: clock[0],
    )
    policy = RetryPolicy(max_attempts=1)

    def outage():
        raise ConnectionError('provider unavailable')

    for _ in range(2):
        with pytest.raises(ConnectionError):
            call_with_resilience(
                outage,
                name='outage',
                policy=policy,
                breaker=breaker,
                is_retryable=lambda _: True,
                sleep=lambda _: None,
            )
    assert breaker.state == 'open'
    with pytest.raises(CircuitOpenError):
        breaker.allow()
    clock[0] = 11.0
    assert breaker.state == 'half_open'
    breaker.allow()
    breaker.success()
    assert breaker.state == 'closed'


def test_ttl_cache_bounds_entries_and_can_be_cleared():
    cache = TTLCache[str](ttl_seconds=60, max_entries=1)
    cache.set('first', 'one')
    cache.set('second', 'two')
    assert cache.get('first') is None
    assert cache.get('second') == 'two'
    cache.clear()
    assert cache.get('second') is None


def test_typed_budget_error_is_stable_and_non_retryable():
    error = ProviderBudgetError()
    assert error.code == 'PROVIDER_BUDGET_EXHAUSTED'
    assert error.error_class == ErrorClass.BUDGET
    assert not error.retryable


def test_versioned_vector_names_are_stable_and_isolated(tmp_path):
    first = collection_name('smartwealth_tax', 'corpus-v1')
    second = collection_name('smartwealth_tax', 'corpus-v2')
    assert first != second
    assert chroma_release_path(tmp_path, 'corpus-v1') == tmp_path / 'corpus-v1'
    with pytest.raises(ValueError):
        validate_corpus_version('../escape')


def test_sqlite_backup_restore_drill(tmp_path):
    import sqlite3

    source = tmp_path / 'source.sqlite'
    backup = tmp_path / 'backup.sqlite'
    restored = tmp_path / 'restored.sqlite'
    with sqlite3.connect(source) as connection:
        connection.execute('CREATE TABLE values_table(value TEXT)')
        connection.execute("INSERT INTO values_table VALUES ('preserved')")
    sqlite_backup(source, backup)
    sqlite_restore(backup, restored)
    with sqlite3.connect(restored) as connection:
        assert connection.execute('SELECT value FROM values_table').fetchone()[0] == 'preserved'


def test_migrations_are_ordered_and_postgres_placeholders_are_adapted():
    files = migration_files()
    assert files and files[0].name == '001_phase7_postgres.sql'
    assert _PostgresConnection._query('SELECT * FROM x WHERE id = ?') == (
        'SELECT * FROM x WHERE id = %s'
    )
    assert _PostgresConnection._query('BEGIN IMMEDIATE') == 'BEGIN'


def test_operational_endpoints_report_health_and_protect_metrics(monkeypatch):
    assert routes_ops.liveness() == {'status': 'alive'}
    request = type('Request', (), {
        'app': type('App', (), {'state': type('State', (), {'ready': True})()})()
    })()
    monkeypatch.setattr(routes_ops.run_service.store, 'ping', lambda: True)
    response = routes_ops.readiness(request)
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body['status'] == 'ready'
    rendered = routes_ops.prometheus_metrics()
    assert 'smartwealth_queue_capacity' in rendered


def test_executor_exposes_bounded_queue_depth():
    executor = BoundedRunExecutor(max_workers=1, queue_capacity=1)
    started = Event()
    release = Event()

    def work():
        started.set()
        release.wait(timeout=2)

    assert executor.reserve()
    future = executor.submit_reserved(work)
    assert started.wait(timeout=1)
    snapshot = executor.snapshot()
    assert snapshot['running'] == 1
    assert snapshot['reserved'] == 1
    assert executor.reserve()
    assert executor.snapshot()['reserved'] == 2
    executor.release_reservation()
    release.set()
    future.result(timeout=2)
    executor.shutdown()


def test_percentile_and_simulated_soak_probe(monkeypatch):
    assert percentile([0.1, 0.2, 0.3, 0.4], 0.95) == 0.3
    monkeypatch.setattr(
        'scripts.load_test.probe',
        lambda _url, _timeout: (True, 0.01),
    )
    result = run_load('http://test/health', requests=100, concurrency=8, timeout=1)
    assert result['successes'] == 100
    assert result['error_rate'] == 0
    assert result['p95_seconds'] == pytest.approx(0.01)


def test_provider_token_usage_is_persisted_when_metadata_is_available(tmp_path, monkeypatch):
    store = RunStore(tmp_path / 'usage.sqlite')
    record, _ = store.create_run(
        owner_id='owner',
        idempotency_key='usage-key',
        request_hash='hash',
        payload={'transactions': []},
        total=0,
    )
    monkeypatch.setattr('backend.app.progress.run_store', store)
    response = type('Response', (), {
        'usage_metadata': {'input_tokens': 12, 'output_tokens': 5}
    })()
    ProgressStore().record_provider_usage(record.run_id, response)
    updated = store.get(record.run_id)
    assert updated.provider_input_tokens == 12
    assert updated.provider_output_tokens == 5


def test_production_defaults_to_pgvector_while_development_defaults_to_chroma(monkeypatch):
    try:
        monkeypatch.delenv('VECTOR_BACKEND', raising=False)
        monkeypatch.setenv('ENVIRONMENT', 'production')
        get_settings.cache_clear()
        assert get_settings().vector_backend == 'pgvector'
        monkeypatch.setenv('ENVIRONMENT', 'development')
        get_settings.cache_clear()
        assert get_settings().vector_backend == 'chroma'
    finally:
        get_settings.cache_clear()
