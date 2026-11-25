import io
import sys

from backend.app.graph.builder import route_after_extraction
from backend.app.graph.nodes import auditor_loop as auditor_module
from backend.app.graph.state import CategorizedTransaction


def _legacy_console(monkeypatch):
    # Redirected Windows output defaults to a legacy code page, not UTF-8.
    stream = io.TextIOWrapper(io.BytesIO(), encoding='cp1252', errors='strict')
    monkeypatch.setattr(sys, 'stdout', stream)
    return stream


def test_router_logging_survives_non_utf8_stdout(monkeypatch):
    _legacy_console(monkeypatch)
    low = CategorizedTransaction(
        transaction_id='TXN-1',
        predicted_category='Unknown',
        confidence_score=0.2,
    )
    high = CategorizedTransaction(
        transaction_id='TXN-2',
        predicted_category='Office Supplies',
        confidence_score=0.99,
    )

    assert route_after_extraction({'categorized': [low]}) == 'auditor_loop'
    assert route_after_extraction({'categorized': [high]}) == 'corrective_rag'


def test_auditor_loop_logging_survives_non_utf8_stdout(monkeypatch):
    _legacy_console(monkeypatch)
    monkeypatch.setattr(auditor_module, 'interrupt', lambda pending: [
        {'transaction_id': 'TXN-1', 'answer': 'idk'},
    ])
    state = {
        'thread_id': '',
        'categorized': [
            CategorizedTransaction(
                transaction_id='TXN-1',
                predicted_category='Unknown',
                confidence_score=0.2,
            ),
        ],
        'pending_clarifications': [],
        'resolved_clarifications': {},
        'unresolved_flags': [],
    }
    monkeypatch.setattr(auditor_module.progress_store, 'update', lambda *a, **k: None)

    result = auditor_module.auditor_loop(state)

    assert result['pending_clarifications'][0]['retries'] == 1
