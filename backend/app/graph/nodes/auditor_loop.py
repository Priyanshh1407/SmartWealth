from langgraph.types import interrupt
from backend.app.graph.state import AuditState
from backend.app.progress import progress_store
from backend.app.config import get_settings

settings = get_settings()
CONFIDENCE_THRESHOLD = settings.confidence_threshold

def auditor_loop(state: AuditState):
    print("🟡 [NODE 3] Auditor Loop triggered (Validating state & retries)...")
    
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
                question = "Please clarify this transaction."
                pending.append({
                    "transaction_id": txn_id, 
                    "question": question, 
                    "retries": 0
                })

    # 2. Check if there is anything left to clarify
    active_clarifications = [
        p for p in pending
        if getattr(p, 'transaction_id', p.get('transaction_id') if isinstance(p, dict) else p.transaction_id) not in resolved
        and getattr(p, 'transaction_id', p.get('transaction_id') if isinstance(p, dict) else p.transaction_id) not in unresolved
    ]

    if not active_clarifications:
        return {"current_node": "report_generation"}

    # 3. Update progress before pausing
    progress_store.update(
        thread_id,
        message=f"Waiting for human review on {len(active_clarifications)} transaction(s)…",
        processed=len(active_clarifications),
        total=len(active_clarifications),
    )

    # 4. PAUSE THE GRAPH (Wait for the frontend to submit an answer)
    human_responses = interrupt(active_clarifications)

    # 4. PROCESS THE ANSWER (This runs instantly when the graph wakes up)
    if human_responses:
        for response in human_responses:
            txn_id = response.get("transaction_id")
            answer = response.get("answer")

            if is_unusable_answer(answer):
                print(f"      🚫 Unusable answer detected for {txn_id}: '{answer}'")
                
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

                        print(f"      🔄 Retry count for {txn_id} is now: {current_retries}")

                        # Execute the downgrade if they failed twice
                        if current_retries > 1:
                            print(f"      🛑 Max retries reached! Moving {txn_id} to unresolved.")
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

def is_unusable_answer(answer: str) -> bool:
    bad_answers = ["idk", "not sure", "unknown", ""]
    return answer.strip().lower() in bad_answers
