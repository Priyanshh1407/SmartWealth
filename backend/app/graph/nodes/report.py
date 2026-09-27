from collections import Counter

from backend.app.graph.state import (
    AuditReport,
    AuditState,
    DeductionClaim,
    TaxTreatment,
    UnresolvedItem,
)
from backend.app.progress import progress_store


CLAIMABLE_TREATMENTS = {
    TaxTreatment.DEDUCTIBLE,
    TaxTreatment.DEPRECIABLE,
    TaxTreatment.PARTIALLY_DEDUCTIBLE,
}


def generate_report_node(state: AuditState):
    '''Create only evidence-backed, transaction-specific draft claims.'''
    print('[NODE 4] Generating evidence-backed draft report...')
    thread_id = state.get('thread_id', '')
    progress_store.update(
        thread_id,
        current_node='report',
        message='Generating evidence-backed draft pending review...',
    )

    transactions = state.get('transactions', [])
    transaction_by_id = {
        transaction.transaction_id: transaction for transaction in transactions
    }
    category_by_id = {
        item.transaction_id: item.predicted_category
        for item in state.get('categorized', [])
    }
    unresolved_ids = set(state.get('unresolved_flags', []))
    results = state.get('deductibility_results', [])

    report_claims = []
    unresolved_by_id = {}
    total_allowed = 0.0

    def add_unresolved(transaction_id: str, reason: str) -> None:
        transaction = transaction_by_id.get(transaction_id)
        if transaction is None:
            return
        existing = unresolved_by_id.get(transaction_id)
        combined_reason = reason
        if existing and reason not in existing.reason_flagged:
            combined_reason = f'{existing.reason_flagged} {reason}'
        unresolved_by_id[transaction_id] = UnresolvedItem(
            transaction_id=transaction_id,
            original_description=transaction.description,
            reason_flagged=combined_reason,
        )

    for transaction_id in unresolved_ids:
        add_unresolved(
            transaction_id,
            'Human clarification remained unresolved; no claim was created.',
        )

    for result in results:
        transaction = transaction_by_id.get(result.transaction_id)
        if transaction is None:
            continue

        if result.treatment == TaxTreatment.UNDETERMINED:
            reasons = result.review_reasons or ['Tax treatment is undetermined.']
            add_unresolved(result.transaction_id, ' '.join(reasons))
            continue

        if result.requires_accountant_review and result.allowed_current_period_amount == 0:
            reasons = result.review_reasons or ['Accountant review is required.']
            add_unresolved(result.transaction_id, ' '.join(reasons))

        is_claimable = (
            result.transaction_id not in unresolved_ids
            and result.treatment in CLAIMABLE_TREATMENTS
            and result.allowed_current_period_amount > 0
            and result.evidence is not None
            and result.business_purpose_supported
        )
        if not is_claimable:
            continue

        claim = DeductionClaim(
            transaction_id=result.transaction_id,
            category=category_by_id.get(result.transaction_id, 'Unknown'),
            treatment=result.treatment,
            transaction_amount=result.transaction_amount,
            allowed_current_period_amount=result.allowed_current_period_amount,
            evidence=result.evidence,
            reasoning=result.reasoning,
        )
        report_claims.append(claim)
        total_allowed += claim.allowed_current_period_amount

    outcome_counts = Counter(result.treatment.value for result in results)
    warnings = [
        'Evidence-backed draft pending review; this report is not tax advice.',
    ]
    final_report = AuditReport(
        total_transactions_processed=len(transactions),
        total_allowed_current_period_deductions_inr=round(total_allowed, 2),
        deduction_claims=report_claims,
        unresolved_items=list(unresolved_by_id.values()),
        outcome_counts=dict(outcome_counts),
        warnings=warnings,
    )

    print(f'   Transactions: {final_report.total_transactions_processed}')
    print(
        '   Allowed current-period draft amount: '
        f'INR {final_report.total_allowed_current_period_deductions_inr:,.2f}'
    )
    print(f'   Draft claims: {len(final_report.deduction_claims)}')
    print(f'   Accountant-review items: {len(final_report.unresolved_items)}')
    return {'final_report': final_report, 'current_node': 'report_node'}
