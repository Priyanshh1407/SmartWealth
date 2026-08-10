import time
import requests
import sys
import sqlite3
import os

API_BASE = "http://localhost:8000/api"

def get_latest_thread():
    """Attempts to find the latest thread ID from the local SQLite DB to save the user from copy-pasting."""
    if not os.path.exists("checkpoints.sqlite"):
        return None
    try:
        conn = sqlite3.connect("checkpoints.sqlite")
        c = conn.cursor()
        c.execute("SELECT thread_id FROM checkpoints ORDER BY rowid DESC LIMIT 1")
        row = c.fetchone()
        conn.close()
        return row[0] if row else None
    except:
        return None

def run_auto_auditor(thread_id):
    print(f"🤖 Starting Auto-Auditor for thread: {thread_id}")
    print("Polling every 3 seconds for pending clarifications...\n")

    while True:
        try:
            res = requests.get(f"{API_BASE}/state/{thread_id}")
            if res.status_code == 404:
                print("❌ Audit thread not found. Did you start the audit in the UI yet?")
                break
                
            data = res.json()
            status = data.get("status")
            
            if status in ["completed", "error"]:
                print(f"✅ Audit finished with status: {status}")
                break
                
            pending = data.get("pending_clarifications", [])
            resolved = data.get("resolved_clarifications", {})
            unresolved = data.get("unresolved_flags", [])
            
            # Filter to only active ones
            active = [p for p in pending if p.get("transaction_id") not in resolved and p.get("transaction_id") not in unresolved]
            
            if active:
                print(f"⚠️ Found {len(active)} pending transactions requiring human review.")
                
                responses = []
                for p in active:
                    txn_id = p.get("transaction_id")
                    # We default to a generic category to quickly push it through the loop
                    auto_category = "Office Supplies"
                    
                    print(f"   -> Auto-resolving {txn_id} as '{auto_category}'")
                    responses.append({
                        "transaction_id": txn_id,
                        "answer": auto_category
                    })
                    
                # Submit the answers back to the API to unpause the graph
                post_res = requests.post(f"{API_BASE}/resume/{thread_id}", json=responses)
                
                if post_res.status_code == 200:
                    print("✅ Successfully submitted auto-answers. The audit will now resume.\n")
                else:
                    print(f"❌ Failed to submit answers: {post_res.text}\n")
            
            time.sleep(3)
            
        except Exception as e:
            print(f"❌ Error connecting to backend: {e}")
            time.sleep(3)

if __name__ == "__main__":
    thread_id = None
    if len(sys.argv) > 1:
        thread_id = sys.argv[1]
    else:
        print("Searching for latest thread in database...")
        thread_id = get_latest_thread()
        
    if not thread_id:
        print("Usage: python auto_auditor.py <thread_id>")
        print("Hint: You can find your thread_id in your browser's Developer Tools (Network Tab) when you click 'Run Audit'")
        sys.exit(1)
        
    run_auto_auditor(thread_id)
