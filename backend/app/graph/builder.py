import sqlite3
import os
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver # type: ignore
from .state import AuditState

from backend.app.graph.nodes.extraction import extraction_node  
from backend.app.graph.nodes.corrective_rag import corrective_rag_node
from backend.app.graph.nodes.auditor_loop import auditor_loop
from backend.app.graph.nodes.report import generate_report_node

RECEIPT_THRESHOLD = float(os.environ.get("RECEIPT_THRESHOLD", 500))
CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", 0.70))

# --- 1. Stub Nodes ---

# --- 1.5 Conditional Routers ---
def route_after_extraction(state: AuditState):
    categorized_txns = state.get("categorized", [])
    
    for txn in categorized_txns:
        if txn.confidence_score < CONFIDENCE_THRESHOLD:
            print(f"🚦 [ROUTER] Low confidence detected on {txn.transaction_id} ({txn.confidence_score}). Routing to Auditor Loop!")
            return "auditor_loop"
            
    print("🚦 [ROUTER] All transactions are high confidence. Proceeding to RAG.")
    return "corrective_rag"

def route_after_auditor(state: AuditState):
    """Checks if there are still pending clarifications. If yes, loops back. If no, moves to report."""
    pending = state.get("pending_clarifications", [])
    resolved = state.get("resolved_clarifications", {})
    unresolved = state.get("unresolved_flags", [])

    active = [
        p for p in pending
        if getattr(p, 'transaction_id', p.get('transaction_id') if isinstance(p, dict) else p.transaction_id) not in resolved
        and getattr(p, 'transaction_id', p.get('transaction_id') if isinstance(p, dict) else p.transaction_id) not in unresolved
    ]
    
    if active:
        return "auditor_loop"
    return "corrective_rag"

# --- 2. Wire the Graph ---
builder = StateGraph(AuditState)

builder.add_node("extraction", extraction_node)
builder.add_node("corrective_rag", corrective_rag_node)
builder.add_node("auditor_loop", auditor_loop)
builder.add_node("report", generate_report_node)

builder.set_entry_point("extraction")
builder.add_conditional_edges("extraction", route_after_extraction, {"auditor_loop": "auditor_loop", "corrective_rag": "corrective_rag"})

# Add the loop-back edge so the Bouncer can re-prompt the user
builder.add_conditional_edges("auditor_loop", route_after_auditor, {"auditor_loop": "auditor_loop", "corrective_rag": "corrective_rag"})

builder.add_edge("corrective_rag", "report")
builder.add_edge("report", END)

# --- 3. Attach the Checkpointer ---
conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
memory = SqliteSaver(conn)

graph = builder.compile(checkpointer=memory)