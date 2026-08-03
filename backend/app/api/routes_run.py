import threading
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Any, Dict
from backend.app.graph.builder import graph
from backend.app.graph.state import Transaction
from backend.app.progress import progress_store

router = APIRouter()

class RunRequest(BaseModel):
    thread_id: str
    transactions: List[Dict[str, Any]]
    receipts_index: Dict[str, str] = {}

@router.post("/run")
async def run_graph(request: RunRequest):
    config = {"configurable": {"thread_id": request.thread_id}}
    
    # Format incoming JSON into your Pydantic Transaction models
    txns = []
    for t in request.transactions:
        txns.append(
            Transaction(
                transaction_id=t.get("transaction_id"),
                date=t.get("date", "2025-01-01"),
                merchant=t.get("merchant", "UNKNOWN"),
                amount=float(t.get("amount") if t.get("amount") is not None else 0.0),
                category=t.get("category", ""),
                description=t.get("description", "")
            )
        )
        
    initial_state = {
        "transactions": txns,
        "receipts_index": request.receipts_index,
        "thread_id": request.thread_id,
        "current_node": "init",
        "errors": [],
    }
    
    # Initialize progress tracking
    progress_store.init(request.thread_id, total=len(txns))
    
    # Run graph in a background thread so the endpoint returns immediately
    # and the frontend can poll for real-time progress
    def _run_graph():
        try:
            for _ in graph.stream(initial_state, config, stream_mode="values"):
                pass
            progress_store.complete(request.thread_id)
        except Exception as e:
            progress_store.add_error(request.thread_id, f"Pipeline crashed: {str(e)}")
            progress_store.complete(request.thread_id)
    
    thread = threading.Thread(target=_run_graph, daemon=True)
    thread.start()
        
    return {"status": "started", "thread_id": request.thread_id}


@router.post("/reset")
async def reset_audit():
    """Clears all checkpoint data so the user can start a completely fresh audit."""
    from backend.app.graph.builder import conn
    try:
        # Clear all tables in the checkpoint SQLite database
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        for (table_name,) in tables:
            cursor.execute(f"DELETE FROM {table_name}")
        conn.commit()
        print("🗑️  [RESET] All checkpoints cleared.")
    except Exception as e:
        print(f"⚠️  [RESET] Error clearing checkpoints: {e}")
    
    # Clear in-memory progress store
    progress_store._data.clear()
    
    return {"status": "reset_complete"}