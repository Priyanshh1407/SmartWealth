import sys
import os
import csv

# Ensure Python can find the backend/app directory for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.app.graph.builder import graph
from backend.app.graph.state import Transaction

def run_crash_test():
    config = {"configurable": {"thread_id": "placement_season_demo_02"}} # Updated thread_id to avoid cache
    
    # Read the first 5 rows from the CSV
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/synthetic/transactions_2025.csv'))
    transactions_to_test = []
    
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= 5:
                break
            transactions_to_test.append(
                Transaction(
                    transaction_id=row['transaction_id'],
                    date=row['date'],
                    merchant=row['merchant'],
                    amount=float(row['amount']),
                    category=row['category'],
                    description=row['description']
                )
            )

    # Inject the CSV rows into the state
    initial_state = {
        "thread_id": "placement_season_demo_02",
        "transactions": transactions_to_test,
        "receipts_index": {},
        "categorized": [],
        "deductibility_results": [],
        "pending_clarifications": [],
        "resolved_clarifications": {},
        "unresolved_flags": [],
        "final_report": None,
        "current_node": "init"
    }

    print("🚀 --- TEST RUN 1: STARTING FRESH GRAPH ---")
    
    events = graph.stream(initial_state, config, stream_mode="values")
    for event in events:
        print(f"Captured State at Node: {event.get('current_node')}")
        
    snapshot = graph.get_state(config)
    print(f"\n⏸️ Graph Status: Is it waiting for input? -> {snapshot.next}")
    
    if "auditor_loop" in snapshot.next:
        print("✅ Success: Graph hit the tripwire and paused perfectly!")
        print("💥 CRASH: Simulating hard process kill ('kill -9')... Closing execution.")
        return config

def resume_after_crash(config):
    print("\n🔄 --- TEST RUN 2: REBOOTING SERVER & RESUMING FROM SQLITE ---")
    
    # We pass None as the state input because LangGraph automatically loads the 
    # historical state from checkpoints.sqlite based on the thread_id config!
    events = graph.stream(None, config, stream_mode="values")
    for event in events:
        print(f"Captured State at Node: {event.get('current_node')}")
        
    final_snapshot = graph.get_state(config)
    print(f"\n🏁 Final Graph Status: Next expected node? -> {final_snapshot.next}")
    print("✅ Success: Graph woke up from SQLite database and completed cleanly!")

if __name__ == "__main__":
    # --- 1. GENERATE VISUAL GRAPH ---
    print("📸 Generating architecture diagram...")
    try:
        # LangGraph generates a Mermaid diagram and converts it to PNG
        png_bytes = graph.get_graph().draw_mermaid_png()
        
        # Save it into our docs folder
        diagram_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../docs/architecture_diagram.png'))
        with open(diagram_path, "wb") as f:
            f.write(png_bytes)
        print(f"✅ Saved architecture diagram to {diagram_path}\n")
    except Exception as e:
        print(f"⚠️ Could not generate graph image: {e}\n")

    # --- 2. RUN THE CRASH TEST ---
    session_config = run_crash_test()
    if session_config:
        resume_after_crash(session_config)