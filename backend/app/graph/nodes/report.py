from backend.app.graph.state import AuditState, AuditReport, DeductionClaim, UnresolvedItem
from backend.app.progress import progress_store

def generate_report_node(state: AuditState):
    print("🟢 [NODE 4] Generating Final Validated Report...")
    
    thread_id = state.get("thread_id", "")
    progress_store.update(
        thread_id,
        current_node="report",
        message="Generating final validated audit report…",
    )
    
    transactions = state.get("transactions", [])
    categorized = state.get("categorized", [])
    unresolved_flags = state.get("unresolved_flags", [])
    deductibility_results = state.get("deductibility_results", []) 
    
    report_claims = []
    unresolved_list = []
    total_deductions = 0.0
    
    # 1. Process Unresolved Items (The bad answers/flags from Node 3)
    for txn_id in unresolved_flags:
        original_txn = next((t for t in transactions if t.transaction_id == txn_id), None)
        if original_txn:
            unresolved_list.append(
                UnresolvedItem(
                    transaction_id=txn_id,
                    original_description=original_txn.description,
                    reason_flagged="Flagged by Auditor Loop (Max retries or manual escalation)."
                )
            )

    # 2. Process Deductibility Claims (Enforcing the citation rule)
    for result in deductibility_results:
        original_txn = next((t for t in transactions if t.transaction_id == result.transaction_id), None)
        
        if result.is_deductible and original_txn:
            citation = result.source_citation
            
            # The Exit Criteria Check!
            if not citation or citation.strip() == "" or citation.lower() == "none":
                unresolved_list.append(
                    UnresolvedItem(
                        transaction_id=original_txn.transaction_id,
                        original_description=original_txn.description,
                        reason_flagged="CRITICAL: AI claimed deductible but provided no source citation."
                    )
                )
                continue
                
            # If it has a citation, it passes the test
            claim = DeductionClaim(
                transaction_id=original_txn.transaction_id,
                category=next((c.predicted_category for c in categorized if c.transaction_id == original_txn.transaction_id), "Unknown"),
                amount=original_txn.amount,
                is_deductible=True,
                source_passage_id=citation,
                source_passage=result.source_passage,
                reasoning=result.reasoning
            )
            report_claims.append(claim)
            total_deductions += original_txn.amount

    # 3. Construct the Final Validated Schema
    receipt_warnings = state.get("receipt_warnings", [])
    warnings = ["Report generated successfully with verified citations."] + receipt_warnings
    
    final_report = AuditReport(
        total_transactions_processed=len(transactions),
        total_deductions_inr=total_deductions,
        deduction_claims=report_claims,
        unresolved_items=unresolved_list,
        warnings=warnings
    )
    
    # Print the clean output to the terminal
    print("\n" + "="*50)
    print(f"📊 FINAL AUDIT REPORT")
    print("="*50)
    print(f"Total Transactions: {final_report.total_transactions_processed}")
    print(f"Total Deductible: ₹{final_report.total_deductions_inr:,.2f}")
    
    if final_report.deduction_claims:
        print("\n--- Deductible Breakdown ---")
        for claim in final_report.deduction_claims:
            print(f"  • {claim.transaction_id} ({claim.category}): ₹{claim.amount:,.2f}")
            
    print(f"\nUnresolved Items requiring Accountant: {len(final_report.unresolved_items)}")
    print("="*50 + "\n")

    return {"final_report": final_report, "current_node": "report_node"}    