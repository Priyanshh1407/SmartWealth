import os

import pytest
from pydantic import ValidationError

os.environ.setdefault('OFFLINE_DEMO_MODE', 'true')

from backend.app.demo.offline import evaluate_category
from backend.app.graph.nodes.corrective_rag import _apply_rule_to_transaction
from backend.app.graph.nodes.report import generate_report_node
from backend.app.graph.state import (
    CategorizedTransaction,
    LegalEvidence,
    TaxTreatment,
    Transaction,
)


def _transaction(
    transaction_id: str = 'TX-1',
    amount: float = 1000.0,
    category: str = 'Software Subscriptions',
) -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        date='2026-04-01',
        merchant='GitHub',
        amount=amount,
        category=category,
        description='Annual business software subscription',
    )


def _categorized(
    transaction_id: str = 'TX-1',
    category: str = 'Software Subscriptions',
) -> CategorizedTransaction:
    return CategorizedTransaction(
        transaction_id=transaction_id,
        predicted_category=category,
        confidence_score=0.99,
    )


def _rule(treatment: TaxTreatment, fraction=None) -> dict:
    if treatment == TaxTreatment.UNDETERMINED:
        return evaluate_category('Unsupported')
    if treatment == TaxTreatment.NON_DEDUCTIBLE:
        return evaluate_category('Entertainment')
    if treatment == TaxTreatment.DEPRECIABLE:
        return evaluate_category('Hardware & Equipment')
    rule = evaluate_category('Software Subscriptions')
    rule['treatment'] = treatment.value
    rule['allowed_fraction'] = fraction
    return rule


@pytest.mark.parametrize(
    ('treatment', 'fraction', 'expected_amount', 'review_required'),
    [
        (TaxTreatment.DEDUCTIBLE, None, 1000.0, False),
        (TaxTreatment.NON_DEDUCTIBLE, None, 0.0, False),
        (TaxTreatment.DEPRECIABLE, None, 0.0, True),
        (TaxTreatment.PARTIALLY_DEDUCTIBLE, 0.25, 250.0, False),
        (TaxTreatment.UNDETERMINED, None, 0.0, True),
    ],
)
def test_all_five_tax_outcomes(
    treatment,
    fraction,
    expected_amount,
    review_required,
):
    result = _apply_rule_to_transaction(
        _transaction(),
        _categorized(),
        _rule(treatment, fraction),
        set(),
    )

    assert result.treatment == treatment
    assert result.allowed_current_period_amount == expected_amount
    assert result.requires_accountant_review is review_required


def test_positive_treatment_without_complete_evidence_becomes_undetermined():
    rule = {
        'treatment': TaxTreatment.DEDUCTIBLE.value,
        'reasoning': 'Unsupported positive result.',
        'evidence': None,
        'allowed_fraction': 1.0,
    }
    result = _apply_rule_to_transaction(
        _transaction(),
        _categorized(),
        rule,
        set(),
    )

    assert result.treatment == TaxTreatment.UNDETERMINED
    assert result.allowed_current_period_amount == 0.0
    assert result.requires_accountant_review is True


def test_active_demo_does_not_claim_or_gate_on_receipts():
    result = _apply_rule_to_transaction(
        _transaction(),
        _categorized(),
        _rule(TaxTreatment.DEDUCTIBLE),
        set(),
    )

    assert result.treatment == TaxTreatment.DEDUCTIBLE
    assert result.allowed_current_period_amount == 1000.0
    assert 'receipt_status' not in result.model_dump()


def test_unresolved_transaction_is_never_positive_or_claimable():
    result = _apply_rule_to_transaction(
        _transaction(),
        _categorized(),
        _rule(TaxTreatment.DEDUCTIBLE),
        {'TX-1'},
    )

    assert result.treatment == TaxTreatment.UNDETERMINED
    assert result.allowed_current_period_amount == 0.0
    assert result.evidence is None


def test_inconsistent_evidence_identity_is_rejected():
    with pytest.raises(ValidationError):
        LegalEvidence(
            corpus_version='corpus-v1',
            document_id='document-a',
            title='Tax Act',
            page=1,
            chunk_id='different-document:chunk-1',
            section='Section 1',
            passage='A sufficiently long evidence passage for validation.',
            retrieval_score=0.9,
        )


def test_report_excludes_hardware_purchase_and_undetermined_items():
    deductible = _apply_rule_to_transaction(
        _transaction('TX-DEDUCT', 1000.0),
        _categorized('TX-DEDUCT'),
        _rule(TaxTreatment.DEDUCTIBLE),
        set(),
    )
    hardware_transaction = _transaction(
        'TX-HARDWARE',
        100000.0,
        'Hardware & Equipment',
    )
    hardware = _apply_rule_to_transaction(
        hardware_transaction,
        _categorized('TX-HARDWARE', 'Hardware & Equipment'),
        _rule(TaxTreatment.DEPRECIABLE),
        set(),
    )
    unresolved_transaction = Transaction(
        transaction_id='TX-UNKNOWN',
        date='2026-04-01',
        merchant='Unknown',
        amount=5000.0,
        category='Unknown',
        description='MISC CHRG',
    )
    unresolved = _apply_rule_to_transaction(
        unresolved_transaction,
        _categorized('TX-UNKNOWN', 'Unknown'),
        _rule(TaxTreatment.UNDETERMINED),
        {'TX-UNKNOWN'},
    )
    state = {
        'thread_id': 'phase1-report',
        'transactions': [
            _transaction('TX-DEDUCT', 1000.0),
            hardware_transaction,
            unresolved_transaction,
        ],
        'categorized': [
            _categorized('TX-DEDUCT'),
            _categorized('TX-HARDWARE', 'Hardware & Equipment'),
            _categorized('TX-UNKNOWN', 'Unknown'),
        ],
        'deductibility_results': [deductible, hardware, unresolved],
        'unresolved_flags': ['TX-UNKNOWN'],
    }

    report = generate_report_node(state)['final_report']

    assert report.total_allowed_current_period_deductions_inr == 1000.0
    assert [claim.transaction_id for claim in report.deduction_claims] == ['TX-DEDUCT']
    assert {item.transaction_id for item in report.unresolved_items} == {
        'TX-HARDWARE',
        'TX-UNKNOWN',
    }
    assert report.warnings[0] == (
        'Evidence-backed draft pending review; this report is not tax advice.'
    )
