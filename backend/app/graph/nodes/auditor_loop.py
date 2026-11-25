from langgraph.types import interrupt
from backend.app.graph.state import AuditState
from backend.app.progress import progress_store
from backend.app.config import get_settings
from backend.app.merchants import is_memorable_merchant, merchant_key

settings = get_settings()
CONFIDENCE_THRESHOLD = settings.confidence_threshold

def auditor_loop(state: AuditState):
    print("[NODE 3] Auditor Loop triggered (Validating state & retries)...")
    
    thread_id = state.get("thread_id", "")
    progress_store.update(
        thread_id,
        current_node="auditor_loop",
        message="Checking for low-confidence transactions requiring human review…",
    )

    pending = state.get("pending_clarifications", [])
    resolved = state.get("resolved_clarifications", {})
    unresolved = state.get("unresolved_flags", [])
    categorized = state.get("categorized", [])

    # 1. Populate pending clarifications for low confidence items
    pending_ids = [getattr(p, 'transaction_id', p.get('transaction_id') if isinstance(p, dict) else None) for p in pending]
    
    for txn in categorized:
        txn_id = getattr(txn, 'transaction_id', "")
        is_low_conf = getattr(txn, 'confidence_score', 0.0) < CONFIDENCE_THRESHOLD
        
        # Only low confidence goes to pending clarification
        if is_low_conf:
            if txn_id not in pending_ids and txn_id not in resolved and txn_id not in unresolved:
                confidence = getattr(txn, 'confidence_score', 0.0)
                predicted = getattr(txn, 'predicted_category', 'Unknown')
                question = (
                    f"Model confidence {confidence:.0%} is below the "
                    f"{CONFIDENCE_THRESHOLD:.0%} review threshold "
                    f"(model suggestion: {predicted}). Confirm the correct category."
                )
                pending.append({
                    "transaction_id": txn_id, 
                    "question": question, 
                    "retries": 0
                })

    # 1b. Reviewer memory: a merchant a reviewer already categorised is not
    #     asked about again. This node re-runs from the top after an interrupt,
    #     so the store records each memory decision only once per row.
    apply_reviewer_memory(state, pending, resolved, unresolved)

    # 2. Check if there is anything left to clarify
    active_clarifications = [
        p for p in pending
        if getattr(p, 'transaction_id', p.get('transaction_id') if isinstance(p, dict) else p.transaction_id) not in resolved
        and getattr(p, 'transaction_id', p.get('transaction_id') if isinstance(p, dict) else p.transaction_id) not in unresolved
    ]

    if not active_clarifications:
        return {
            "pending_clarifications": pending,
            "resolved_clarifications": resolved,
            "unresolved_flags": unresolved,
            "current_node": "report_generation",
        }

    # 3. Update progress before pausing: reviewed rows out of all flagged rows
    progress_store.update(
        thread_id,
        message=f"Waiting for human review on {len(active_clarifications)} transaction(s)…",
        processed=len(pending) - len(active_clarifications),
        total=len(pending),
    )

    # 4. PAUSE THE GRAPH (Wait for the frontend to submit an answer)
    human_responses = interrupt(active_clarifications)

    # 4. PROCESS THE ANSWER (This runs instantly when the graph wakes up)
    if human_responses:
        for response in human_responses:
            txn_id = response.get("transaction_id")
            answer = response.get("answer")

            if is_unusable_answer(answer):
                print(f"      [WARN] Unusable answer detected for {txn_id}: '{answer}'")
                
                # Increment the retry counter
                for req in pending:
                    req_txn_id = getattr(req, 'transaction_id', req.get('transaction_id') if isinstance(req, dict) else None)
                    if req_txn_id == txn_id:
                        if isinstance(req, dict):
                            req['retries'] = req.get('retries', 0) + 1
                            current_retries = req['retries']
                        else:
                            req.retries += 1
                            current_retries = req.retries

                        print(f"      [RETRY] Retry count for {txn_id} is now: {current_retries}")

                        # Execute the downgrade if they failed twice
                        if current_retries > 1:
                            print(f"      [UNRESOLVED] Max retries reached! Moving {txn_id} to unresolved.")
                            unresolved.append(txn_id)
                        break
            else:
                resolved[txn_id] = answer

    # Save state. The router will send us back here if things are still pending!
    return {
        "pending_clarifications": pending,
        "resolved_clarifications": resolved,
        "unresolved_flags": unresolved,
        "current_node": "auditor_loop"
    }

def apply_reviewer_memory(state, pending, resolved, unresolved) -> None:
    """Resolve open clarifications whose merchant a reviewer already categorised."""
    thread_id = state.get("thread_id", "")
    merchant_by_id = {
        getattr(txn, 'transaction_id', ''): getattr(txn, 'merchant', '')
        for txn in state.get("transactions", [])
    }
    predicted_by_id = {
        getattr(txn, 'transaction_id', ''): getattr(txn, 'predicted_category', 'Unknown')
        for txn in state.get("categorized", [])
    }
    open_ids = [
        item.get('transaction_id') if isinstance(item, dict) else item.transaction_id
        for item in pending
    ]
    open_ids = [
        txn_id for txn_id in open_ids
        if txn_id not in resolved and txn_id not in unresolved
        and is_memorable_merchant(merchant_by_id.get(txn_id, ''))
    ]
    memory = progress_store.remembered_categories(
        thread_id,
        {merchant_key(merchant_by_id[txn_id]) for txn_id in open_ids},
    )
    decisions = []
    for txn_id in open_ids:
        entry = memory.get(merchant_key(merchant_by_id[txn_id]))
        if entry is None:
            continue
        resolved[txn_id] = entry['category']
        decisions.append({
            'transaction_id': txn_id,
            'answer': entry['category'],
            'prior_prediction': predicted_by_id.get(txn_id, 'Unknown'),
            'downstream_impact': (
                f"Applied from reviewer memory: {entry['merchant']} was categorised "
                f"as {entry['category']} on transaction {entry['source_transaction_id']}. "
                'Tax treatment, deduction amount, evidence, and final report are recalculated.'
            ),
        })
    progress_store.record_memory_resolutions(thread_id, decisions)


def is_unusable_answer(answer: str) -> bool:
    bad_answers = ["idk", "not sure", "unknown", ""]
    return answer.strip().lower() in bad_answers
