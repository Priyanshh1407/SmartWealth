import os
import sys
import csv
import uuid
from pathlib import Path

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.app.graph.builder import graph
from backend.app.graph.state import Transaction
from langgraph.types import Command

def run_pipeline_cli():
    print("="*50)
    print("🚀 SMART WEALTH - END-TO-END AUDITOR RUNNER")
    print("="*50)
    
    # 1. Load Data
    project_root = Path(__file__).resolve().parent.parent.parent
    csv_path = project_root / 'data' / 'synthetic' / 'transactions_2025.csv'
    
    transactions = []
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            # Process a limited number of rows for testing to keep it fast and avoid API limits
            if i >= 30:
                break
            transactions.append(
                Transaction(
                    transaction_id=row['transaction_id'], 
                    date=row['date'], 
                    merchant=row['merchant'],
                    amount=float(row['amount']), 
                    category=row.get('category', ''),
                    description=row['description']
                )
            )
            
    print(f"Loaded {len(transactions)} transactions.")
    
    # 3. Initialize State — use a unique thread_id every run to avoid stale checkpoints
    run_id = uuid.uuid4().hex[:8]
    config = {"configurable": {"thread_id": f"run_{run_id}"}}
    initial_state = {
        "thread_id": f"run_{run_id}",
        "transactions": transactions,
        "categorized": [],
        "deductibility_results": [],
        "pending_clarifications": [],
        "resolved_clarifications": {},
        "unresolved_flags": [],
        "final_report": None,
        "current_node": "init"
    }

    # 4. Stream Graph Execution
    print(f"\n▶️ Starting pipeline execution (run: {run_id})...\n")
    events = graph.stream(initial_state, config, stream_mode="values")
    
    while True:
        try:
            for event in events:
                pass # Node logs will print to stdout
        except StopIteration:
            pass # Iterator exhausted

        # Check graph state
        snapshot = graph.get_state(config)
        
        if not snapshot.next:
            print("\n🏁 Pipeline Completed!")
            break
            
        if "auditor_loop" in snapshot.next:
            # We hit an interrupt!
            pending_tasks = []
            if snapshot.tasks and snapshot.tasks[0].interrupts:
                pending_tasks = snapshot.tasks[0].interrupts[0].value
                
            if pending_tasks:
                print("\n" + "="*50)
                print(f"⚠️ HUMAN-IN-THE-LOOP INTERRUPT: {len(pending_tasks)} pending clarifications")
                print("="*50)
                
                human_answers = []
                for task in pending_tasks:
                    txn_id = task.get("transaction_id", "Unknown") if isinstance(task, dict) else getattr(task, 'transaction_id', 'Unknown')
                    q = task.get("question", "") if isinstance(task, dict) else getattr(task, 'question', '')
                    retries = task.get("retries", 0) if isinstance(task, dict) else getattr(task, 'retries', 0)
                    
                    if retries > 0:
                        print(f"\n[RETRY {retries}] Transaction {txn_id}: {q}")
                    else:
                        print(f"\nTransaction {txn_id}: {q}")
                        
                    # Find original transaction for context
                    orig = next((t for t in transactions if t.transaction_id == txn_id), None)
                    if orig:
                        print(f"   Context: {orig.date} | {orig.merchant} | ₹{orig.amount} | {orig.description}")
                        
                    # Ask user for input
                    prompt_msg = "   Enter an allowed category (or 'idk'): "
                        
                    answer = input(prompt_msg)
                    human_answers.append({"transaction_id": txn_id, "answer": answer})
                
                print("\n▶️ Resuming graph with human answers...\n")
                events = graph.stream(Command(resume=human_answers), config, stream_mode="values")
            else:
                print("⚠️ Graph paused but no pending tasks found. Exiting.")
                break

if __name__ == "__main__":
    run_pipeline_cli()
