import time
import uuid

from backend.app.runs.models import RunStatus
from backend.app.runs.service import RunService


def _txn(txn_id: str, merchant: str, amount: float = 100.0) -> dict:
    return {
        'transaction_id': txn_id,
        'date': '2025-01-01',
        'merchant': merchant,
        'amount': amount,
        'category': '',
        'description': 'Demo purchase',
    }


def _wait(store, run_id: str, expected: RunStatus, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if store.get(run_id).status == expected:
            return
        time.sleep(0.02)
    raise AssertionError(f'{run_id} stayed {store.get(run_id).status}, expected {expected}')


def _pending_ids(service, run_id, owner):
    return [
        item['transaction_id']
        for item in service.state_payload(run_id, owner)['pending_clarifications']
    ]


def test_reviewer_memory_resolves_repeat_merchants_and_revision_recalculates():
    from backend.app.graph.builder import graph
    from backend.app.runs.store import run_store

    owner = f'memory-{uuid.uuid4().hex}'
    service = RunService(store=run_store, graph=graph, max_workers=1, queue_capacity=4)
    run_ids = []
    try:
        # Run 1: two rows from a merchant the offline rules do not know, plus a
        # terminal ID that must never be remembered.
        first, _ = service.start(
            owner_id=owner,
            idempotency_key=f'start-{uuid.uuid4().hex}',
            payload={'transactions': [
                _txn('TXN-A1', 'Nalli Silks Stationery'),
                _txn('TXN-A2', 'Nalli Silks Stationery'),
                _txn('TXN-A3', 'POS DEBIT'),
                _txn('TXN-A4', 'GitHub'),
            ]},
        )
        run_ids.append(first.run_id)
        _wait(run_store, first.run_id, RunStatus.WAITING_FOR_INPUT)
        assert _pending_ids(service, first.run_id, owner) == ['TXN-A1', 'TXN-A2', 'TXN-A3']

        service.resume(
            run_id=first.run_id,
            owner_id=owner,
            idempotency_key=f'resume-{uuid.uuid4().hex}',
            answers=[{'transaction_id': 'TXN-A1', 'answer': 'Office Supplies'}],
        )
        _wait(run_store, first.run_id, RunStatus.WAITING_FOR_INPUT)
        # The second Nalli row came from memory; only the terminal ID is asked.
        assert _pending_ids(service, first.run_id, owner) == ['TXN-A3']
        state = service.state_payload(first.run_id, owner)
        assert state['human_override_ids'] == ['TXN-A1']
        assert state['memory_override_ids'] == ['TXN-A2']
        memory_event = [e for e in state['audit_trail'] if e['event_type'] == 'memory_override']
        assert memory_event[0]['answer'] == 'Office Supplies'
        assert 'TXN-A1' in memory_event[0]['downstream_impact']

        service.resume(
            run_id=first.run_id,
            owner_id=owner,
            idempotency_key=f'resume-{uuid.uuid4().hex}',
            answers=[{'transaction_id': 'TXN-A3', 'answer': 'Travel & Transit'}],
        )
        _wait(run_store, first.run_id, RunStatus.COMPLETED)
        remembered = run_store.merchant_memory(owner)
        assert {key: item['category'] for key, item in remembered.items()} == {
            'nalli silks stationery': 'Office Supplies',
        }
        audit = service.state_payload(first.run_id, owner)['audit_trail']
        assert len(audit) == 3  # one human, one memory, one human; no duplicates
        for previous, current in zip(audit, audit[1:]):
            assert current['previous_hash'] == previous['event_hash']

        # Run 2: the remembered merchant (different spacing/case) is not asked.
        second, _ = service.start(
            owner_id=owner,
            idempotency_key=f'start-{uuid.uuid4().hex}',
            payload={'transactions': [
                _txn('TXN-B1', 'nalli  silks STATIONERY', 250.0),
                _txn('TXN-B2', 'GitHub'),
            ]},
        )
        run_ids.append(second.run_id)
        _wait(run_store, second.run_id, RunStatus.COMPLETED)
        state = service.state_payload(second.run_id, owner)
        assert state['memory_override_ids'] == ['TXN-B1']
        assert state['resolved_clarifications']['TXN-B1'] == 'Office Supplies'
        results = {r['transaction_id']: r for r in state['deductibility_results']}
        assert results['TXN-B1']['treatment'] == 'deductible'

        # Revision: change the remembered category on the completed run.
        service.revise(
            run_id=second.run_id,
            owner_id=owner,
            idempotency_key=f'revise-{uuid.uuid4().hex}',
            answers=[{'transaction_id': 'TXN-B1', 'answer': 'Entertainment'}],
        )
        _wait(run_store, second.run_id, RunStatus.COMPLETED)
        state = service.state_payload(second.run_id, owner)
        results = {r['transaction_id']: r for r in state['deductibility_results']}
        assert results['TXN-B1']['treatment'] == 'non_deductible'
        assert results['TXN-B1']['allowed_current_period_amount'] == 0
        assert state['human_override_ids'] == ['TXN-B1']
        assert state['memory_override_ids'] == []
        assert run_store.merchant_memory(owner)['nalli silks stationery']['category'] == 'Entertainment'

        # Run 3 pauses for the terminal ID; the remembered row already shows the
        # reviewer's latest category while paused, before the tax step runs.
        third, _ = service.start(
            owner_id=owner,
            idempotency_key=f'start-{uuid.uuid4().hex}',
            payload={'transactions': [
                _txn('TXN-C1', 'Nalli Silks Stationery'),
                _txn('TXN-C2', 'POS DEBIT'),
            ]},
        )
        run_ids.append(third.run_id)
        _wait(run_store, third.run_id, RunStatus.WAITING_FOR_INPUT)
        state = service.state_payload(third.run_id, owner)
        assert _pending_ids(service, third.run_id, owner) == ['TXN-C2']
        assert state['resolved_clarifications'] == {'TXN-C1': 'Entertainment'}
        assert state['memory_override_ids'] == ['TXN-C1']
    finally:
        for run_id in run_ids:
            if run_store.get(run_id).status not in {
                RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED,
            }:
                service.cancel(run_id, owner)
        service.shutdown()
        for run_id in run_ids:
            run_store.delete(run_id, owner)
        run_store.clear_merchant_memory(owner)


def test_revision_rejects_unknown_transactions_and_unfinished_runs(tmp_path):
    from backend.app.graph.builder import graph
    from backend.app.runs.models import InvalidTransitionError
    from backend.app.runs.store import run_store

    owner = f'memory-{uuid.uuid4().hex}'
    service = RunService(store=run_store, graph=graph, max_workers=1, queue_capacity=4)
    run, _ = service.start(
        owner_id=owner,
        idempotency_key=f'start-{uuid.uuid4().hex}',
        payload={'transactions': [_txn('TXN-C1', 'POS DEBIT')]},
    )
    try:
        _wait(run_store, run.run_id, RunStatus.WAITING_FOR_INPUT)
        for answers in (
            [{'transaction_id': 'TXN-OTHER', 'answer': 'Office Supplies'}],
            [{'transaction_id': 'TXN-C1', 'answer': 'Office Supplies'}],
        ):
            try:
                service.revise(
                    run_id=run.run_id,
                    owner_id=owner,
                    idempotency_key=f'revise-{uuid.uuid4().hex}',
                    answers=answers,
                )
            except InvalidTransitionError:
                pass
            else:
                raise AssertionError('revision should be rejected')
        assert run_store.merchant_memory(owner) == {}
    finally:
        service.cancel(run.run_id, owner)
        service.shutdown()
        run_store.delete(run.run_id, owner)
