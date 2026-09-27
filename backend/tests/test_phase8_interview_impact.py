import json
import time
import uuid

from backend.app.api import routes_ops
from backend.app.graph.nodes.extraction import extraction_node
from backend.app.graph.state import Transaction
from backend.app.runs.models import RunStatus
from backend.app.runs.service import RunService
from backend.app.runs.store import RunStore


def payload() -> dict:
    return {
        'transactions': [{
            'transaction_id': 'TXN-1',
            'date': '2025-03-14',
            'merchant': 'Unknown Counterparty',
            'amount': 1800,
            'category': '',
            'description': 'Ambiguous expense',
        }],
    }


def wait_for_status(store, run_id, status, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = store.get(run_id)
        if record.status == status:
            return record
        time.sleep(0.02)
    raise AssertionError(f'Run {run_id} did not reach {status.value}.')


def test_durable_timeline_and_override_context_share_run_transaction(tmp_path):
    store = RunStore(tmp_path / 'phase8.sqlite')
    run, _ = store.create_run(
        owner_id='local-workspace',
        idempotency_key='phase8-start',
        request_hash='start-hash',
        payload=payload(),
        total=1,
    )
    running = store.transition(
        run.run_id,
        expected_statuses=[RunStatus.QUEUED],
        new_status=RunStatus.RUNNING,
        current_node='starting',
        message='Starting audit pipeline.',
    )
    store.update_progress(
        run.run_id,
        current_node='extraction',
        message='Starting classification.',
    )
    waiting = store.transition(
        run.run_id,
        expected_statuses=[RunStatus.RUNNING],
        new_status=RunStatus.WAITING_FOR_INPUT,
        current_node='auditor_loop',
        message='Waiting for clarification.',
    )
    resumed, replayed = store.reserve_resume(
        run_id=run.run_id,
        owner_id='local-workspace',
        idempotency_key='phase8-resume',
        request_hash='resume-hash',
        answers=[{'transaction_id': 'TXN-1', 'answer': 'Office Supplies'}],
        override_context={
            'TXN-1': {
                'prior_prediction': 'Unknown',
                'downstream_impact': 'Tax treatment and report are recalculated.',
            },
        },
        correlation_id='phase8-request-0001',
    )

    assert running.status == RunStatus.RUNNING
    assert waiting.status == RunStatus.WAITING_FOR_INPUT
    assert resumed.status == RunStatus.RUNNING
    assert replayed is False
    timeline = store.timeline_events(run.run_id, 'local-workspace')
    assert [event['stage'] for event in timeline] == [
        'queued',
        'starting',
        'extraction',
        'auditor_loop',
        'resume',
    ]
    audit = store.audit_events(run.run_id, 'local-workspace')
    assert audit[0]['actor'] == 'local-workspace'
    assert audit[0]['prior_prediction'] == 'Unknown'
    assert audit[0]['answer'] == 'Office Supplies'
    assert audit[0]['downstream_impact'] == (
        'Tax treatment and report are recalculated.'
    )
    assert audit[0]['previous_hash'] == 'GENESIS'


def test_controlled_429_demo_records_fallback_in_normal_run_store(
    tmp_path,
    monkeypatch,
):
    store = RunStore(tmp_path / 'failure-demo.sqlite')
    run, _ = store.create_run(
        owner_id='local-workspace',
        idempotency_key='failure-demo',
        request_hash='failure-hash',
        payload=payload(),
        total=1,
    )
    store.transition(
        run.run_id,
        expected_statuses=[RunStatus.QUEUED],
        new_status=RunStatus.RUNNING,
        current_node='starting',
        message='Starting audit pipeline.',
    )
    monkeypatch.setattr('backend.app.progress.run_store', store)
    result = extraction_node({
        'thread_id': run.run_id,
        'demo_scenario': 'provider_429_fallback',
        'transactions': [Transaction.model_validate(payload()['transactions'][0])],
        'errors': [],
    })

    assert result['categorized'][0].predicted_category == 'Unknown'
    event_types = {
        event['event_type']
        for event in store.timeline_events(run.run_id, 'local-workspace')
    }
    assert 'provider_rate_limited' in event_types
    assert 'provider_fallback_succeeded' in event_types


def test_controlled_failure_demo_survives_restart_and_completes():
    from backend.app.graph.builder import graph
    from backend.app.runs.store import run_store

    owner = 'phase8-integration'
    suffix = uuid.uuid4().hex
    run_id = None
    first = RunService(
        store=run_store,
        graph=graph,
        max_workers=1,
        queue_capacity=1,
    )
    second = None
    try:
        request_payload = payload()
        request_payload['demo_scenario'] = 'provider_429_fallback'
        run, _ = first.start(
            owner_id=owner,
            idempotency_key=f'phase8-start-{suffix}',
            payload=request_payload,
        )
        run_id = run.run_id
        wait_for_status(
            run_store,
            run_id,
            RunStatus.WAITING_FOR_INPUT,
        )
        first.shutdown()

        second = RunService(
            store=run_store,
            graph=graph,
            max_workers=1,
            queue_capacity=1,
        )
        recovery = second.recover()
        assert recovery['waiting'] == 1
        second.resume(
            run_id=run_id,
            owner_id=owner,
            idempotency_key=f'phase8-resume-{suffix}',
            answers=[{
                'transaction_id': 'TXN-1',
                'answer': 'Office Supplies',
            }],
            correlation_id='phase8-restart-0001',
        )
        wait_for_status(run_store, run_id, RunStatus.COMPLETED)
        state = second.state_payload(run_id, owner)
        assert state['final_report'] is not None
        event_types = {event['event_type'] for event in state['run_timeline']}
        assert {
            'provider_rate_limited',
            'provider_fallback_succeeded',
            'run_waiting_for_input',
            'run_resumed',
            'run_completed',
        } <= event_types
        assert state['audit_trail'][0]['prior_prediction'] == 'Unknown'
    finally:
        first.shutdown()
        if second is not None:
            second.shutdown()
        if run_id is not None:
            current = run_store.get(run_id)
            if current.status in {
                RunStatus.QUEUED,
                RunStatus.RUNNING,
                RunStatus.WAITING_FOR_INPUT,
            }:
                run_store.cancel(run_id, owner)
            run_store.delete(run_id, owner)


def test_evaluation_dashboard_artifact_is_versioned_and_honest():
    result = routes_ops.evaluation_summary()

    assert result['schema_version'] == 'evaluation-dashboard-v1'
    assert result['before']['categorization_accuracy'] == 0.1962
    assert 'not a live-model' in result['after']['scope']
    matrix = result['after']['confusion_matrix']
    assert len(matrix['labels']) == len(matrix['matrix'])
    assert result['after']['retrieval_faithfulness']['evaluated_claims'] > 0
    json.dumps(result)
