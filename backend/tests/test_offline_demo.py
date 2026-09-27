import csv
from pathlib import Path

from backend.app.demo.offline import categorize_transaction, evaluate_category
from backend.app.graph.state import TaxTreatment, Transaction


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_CSV = PROJECT_ROOT / 'data' / 'demo' / 'smartwealth_demo.csv'


def _load_demo() -> list[Transaction]:
    with DEMO_CSV.open(encoding='utf-8', newline='') as handle:
        return [
            Transaction(
                transaction_id=row['transaction_id'],
                date=row['date'],
                merchant=row['merchant'],
                amount=float(row['amount']),
                category=row['category'],
                description=row['description'],
            )
            for row in csv.DictReader(handle)
        ]


def test_canonical_demo_is_deterministic_and_has_one_ambiguous_row():
    transactions = _load_demo()
    first = [categorize_transaction(transaction).model_dump() for transaction in transactions]
    second = [categorize_transaction(transaction).model_dump() for transaction in transactions]

    assert len(transactions) == 24
    assert first == second
    assert [item['transaction_id'] for item in first if item['confidence_score'] < 0.70] == [
        'DEMO-023'
    ]


def test_secured_api_shape_keeps_only_the_unknown_demo_row_ambiguous():
    transactions = _load_demo()
    secured_transactions = [
        transaction.model_copy(update={'category': ''})
        for transaction in transactions
    ]

    categorized = [
        categorize_transaction(transaction)
        for transaction in secured_transactions
    ]

    assert [
        item.transaction_id
        for item in categorized
        if item.confidence_score < 0.70
    ] == ['DEMO-023']
    assert [
        item.predicted_category
        for item in categorized
        if item.transaction_id != 'DEMO-023'
    ] == [
        transaction.category
        for transaction in transactions
        if transaction.transaction_id != 'DEMO-023'
    ]


def test_offline_tax_treatment_is_conservative_for_demo():
    assert evaluate_category('Software Subscriptions')['treatment'] == TaxTreatment.DEDUCTIBLE
    assert evaluate_category('Entertainment')['treatment'] == TaxTreatment.NON_DEDUCTIBLE
    assert evaluate_category('Hardware & Equipment')['treatment'] == TaxTreatment.DEPRECIABLE
    assert evaluate_category('Unsupported')['treatment'] == TaxTreatment.UNDETERMINED
