import sys
import os
import csv
from langgraph.types import Command  # <-- Crucial import for resuming

if os.path.exists("checkpoints.sqlite"):
    os.remove("checkpoints.sqlite")
    print("🧹 Wiped old SQLite checkpoints for a clean test run.\n")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from backend.app.graph.builder import graph
from backend.app.graph.state import Transaction
from backend.app.graph.state import DeductibilityResult

def run_crash_test():
    config = {"configurable": {"thread_id": "placement_season_demo_02"}}
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/synthetic/transactions_2025.csv'))
    transactions_to_test = []
    
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= 30: break
            transactions_to_test.append(
                Transaction(
                    transaction_id=row['transaction_id'], date=row['date'], merchant=row['merchant'],
                    amount=float(row['amount']), category=row['category'], description=row['description']
                )
            )

    initial_state = {
        "thread_id": "placement_season_demo_02", "transactions": transactions_to_test,
        "receipts_index": {}, "categorized": [], "deductibility_results": [],
        "pending_clarifications": [], "resolved_clarifications": {}, "unresolved_flags": [],
        "final_report": None, "current_node": "init"
    }

    print("🚀 --- TEST RUN 1: STARTING FRESH GRAPH ---")
    for event in graph.stream(initial_state, config, stream_mode="values"): pass
        
    snapshot = graph.get_state(config)
    print(f"\n⏸️ Graph Status: Is it waiting for input? -> {snapshot.next}")
    if "auditor_loop" in snapshot.next:
        print("✅ Success: Graph hit the tripwire and paused perfectly!")
        print("💥 CRASH: Simulating hard process kill ('kill -9')... Closing execution.")
        return config

def resume_after_crash(config):
    print("\n🔄 --- TEST RUN 2: REBOOTING SERVER & RESUMING FROM SQLITE ---")
    snapshot = graph.get_state(config)
    
    pending_tasks = []
    if snapshot.tasks and snapshot.tasks[0].interrupts:
        pending_tasks = snapshot.tasks[0].interrupts[0].value
        
    if pending_tasks:
        print(f"📝 Found pending clarifications: {pending_tasks}")
        # Answer EVERY pending clarification so the graph is fully satisfied
        mock_human_answer = []
        for task in pending_tasks:
            txn_id = getattr(task, 'transaction_id', None) or (
                task.get('transaction_id') if isinstance(task, dict) else None
            )
            if txn_id:
                mock_human_answer.append({
                    "transaction_id": txn_id, 
                    "answer": "This was for office supplies."
                })
        print(f"🧑‍💻 Injecting human answer: {mock_human_answer}")
        
        mock_crag_data = [
            # Claim 1: A good claim with a proper citation
            DeductibilityResult(
                transaction_id="TXN-1294", # Amtrak (Travel)
                is_deductible=True,
                reasoning="Travel is deductible under section 162.",
                source_citation="tax_code_doc_page_4" # VALID CITATION
            ),
            # Claim 2: A HALLUCINATION! The AI claims it is deductible but forgets the citation!
            DeductibilityResult(
                transaction_id="TXN-1039", # AWS (Software)
                is_deductible=True,
                reasoning="Software is usually deductible.",
                source_citation="" # MISSING CITATION!
            )
        ]
    
        # Force this into the graph's state before we resume
        graph.update_state(config, {"deductibility_results": mock_crag_data})
        # --------------------------------------------------------------

        print("▶️ Resuming graph execution...")
        # Use Command(resume=...) to properly wake up the interrupt!
        events = graph.stream(Command(resume=mock_human_answer), config, stream_mode="values")
        for event in events: pass
    else:
        print("⚠️ Could not dynamically find pending tasks.")

    final_snapshot = graph.get_state(config)
    print(f"\n🏁 Final Graph Status: Next expected node? -> {final_snapshot.next}")
    if not final_snapshot.next:
        print("✅ Success: Graph woke up from SQLite database, processed the human input, and completed cleanly!")
    else:
        print("❌ Failure: Graph is still stuck or paused.")

def test_unusable_answer_downgrade():
    print("\n🚫 --- TEST RUN 3: THE BAD ANSWER LOOP ---")
    config = {"configurable": {"thread_id": "bad_answer_demo_01"}}
    
    initial_state = {
        "thread_id": "bad_answer_demo_01",
        "transactions": [Transaction(transaction_id="TXN-999", date="2025-01-01", merchant="UNKNOWN", amount=100.0, category="", description="???")],
        "pending_clarifications": [], "resolved_clarifications": {}, "unresolved_flags": [], "current_node": "init"
    }
    
    for _ in graph.stream(initial_state, config, stream_mode="values"): pass
    
    print("🧑‍💻 User submits bad answer: 'idk'")
    bad_answer_1 = [{"transaction_id": "TXN-999", "answer": "idk"}]
    # Resume the exact interrupt with the answer
    for _ in graph.stream(Command(resume=bad_answer_1), config, stream_mode="values"): pass
    
    state_after_retry = graph.get_state(config)
    if "auditor_loop" in state_after_retry.next:
        print("✅ Success: Graph rejected 'idk' and paused to re-prompt!")
    
    print("🧑‍💻 User submits another bad answer: 'not sure'")
    bad_answer_2 = [{"transaction_id": "TXN-999", "answer": "not sure"}]
    # Resume the exact interrupt a second time
    for _ in graph.stream(Command(resume=bad_answer_2), config, stream_mode="values"): pass
    
    final_state = graph.get_state(config).values
    if "TXN-999" in final_state.get("unresolved_flags", []):
        print("✅ Success: Graph downgraded to unresolved and finished cleanly!")
    else:
        print("❌ Failure: Graph did not move transaction to unresolved_flags.")

if __name__ == "__main__":
    session_config = run_crash_test()
    if session_config:
        resume_after_crash(session_config)
        test_unusable_answer_downgrade()