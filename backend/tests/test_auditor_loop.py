from backend.app.graph.nodes import auditor_loop as auditor_module
from backend.app.graph.state import CategorizedTransaction


def _state(resolved=None):
    return {
        'thread_id': 'run-1',
        'categorized': [
            CategorizedTransaction(
                transaction_id='TXN-1',
                predicted_category='Unknown',
                confidence_score=0.2,
            ),
            CategorizedTransaction(
                transaction_id='TXN-2',
                predicted_category='Office Supplies',
                confidence_score=0.5,
            ),
            CategorizedTransaction(
                transaction_id='TXN-3',
                predicted_category='Office Supplies',
                confidence_score=0.99,
            ),
        ],
        'pending_clarifications': [],
        'resolved_clarifications': resolved or {},
        'unresolved_flags': [],
    }


def test_question_explains_why_the_row_was_flagged(monkeypatch):
    captured = {}
    monkeypatch.setattr(auditor_module.progress_store, 'update', lambda *a, **k: None)
    monkeypatch.setattr(
        auditor_module,
        'interrupt',
        lambda pending: captured.setdefault('pending', pending) and [],
    )

    auditor_module.auditor_loop(_state())

    questions = {item['transaction_id']: item['question'] for item in captured['pending']}
    assert set(questions) == {'TXN-1', 'TXN-2'}
    assert questions['TXN-1'] == (
        'Model confidence 20% is below the 70% review threshold '
        '(model suggestion: Unknown). Confirm the correct category.'
    )
    assert '50%' in questions['TXN-2']


def test_progress_counts_reviewed_rows_out_of_flagged_rows(monkeypatch):
    updates = []
    monkeypatch.setattr(
        auditor_module.progress_store,
        'update',
        lambda run_id, **kwargs: updates.append(kwargs),
    )
    monkeypatch.setattr(auditor_module, 'interrupt', lambda pending: [])
    state = _state(resolved={'TXN-1': 'Office Supplies'})
    state['pending_clarifications'] = [
        {'transaction_id': 'TXN-1', 'question': 'q', 'retries': 0},
        {'transaction_id': 'TXN-2', 'question': 'q', 'retries': 0},
    ]

    auditor_module.auditor_loop(state)

    waiting = [update for update in updates if 'total' in update][-1]
    assert (waiting['processed'], waiting['total']) == (1, 2)
