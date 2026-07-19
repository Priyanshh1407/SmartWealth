import sqlite3
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from .state import AuditState

from backend.app.graph.nodes.extraction import extraction_node  

# --- 1. Stub Nodes (The Placeholder Logic) ---

def corrective_rag_node(state: AuditState):
    print("🟢 [NODE 2] Running Corrective RAG...")
    return {"current_node": "corrective_rag_node"}

def auditor_loop_node(state: AuditState):
    print("🟡 [NODE 3] Auditor Loop triggered (Waiting for human input)...")
    return {"current_node": "auditor_loop_node"}

def report_node(state: AuditState):
    print("🟢 [NODE 4] Generating Final Report...")
    return {"current_node": "report_node"}

# --- 1.5 The Traffic Cop (Conditional Router) ---
def route_after_extraction(state: AuditState):
    categorized_txns = state.get("categorized", [])
    
    # Check if any transaction fell below our 70% confidence threshold
    for txn in categorized_txns:
        if txn.confidence_score < 0.70:
            print(f"🚦 [ROUTER] Low confidence detected on {txn.transaction_id} ({txn.confidence_score}). Routing to Auditor Loop!")
            return "auditor_loop"
            
    print("🚦 [ROUTER] All transactions are high confidence. Proceeding to RAG.")
    return "corrective_rag"

# --- 2. Wire the Graph ---

# Initialize the graph with our state schema
builder = StateGraph(AuditState)

# Add all our nodes to the graph
builder.add_node("extraction", extraction_node)
builder.add_node("corrective_rag", corrective_rag_node)
builder.add_node("auditor_loop", auditor_loop_node)
builder.add_node("report", report_node)

# Define the sequential flow (we will add conditional edges in Phase 2)
builder.set_entry_point("extraction")
builder.add_conditional_edges(
    "extraction", 
    route_after_extraction,
    {
        "auditor_loop": "auditor_loop",     # If router returns 'auditor_loop', go to Node 3
        "corrective_rag": "corrective_rag"  # If router returns 'corrective_rag', go to Node 2
    }
)

builder.add_edge("corrective_rag", "report")
builder.add_edge("auditor_loop", "report")
builder.add_edge("report", END)

# --- 3. Attach the Checkpointer and Compile ---

# We create a local SQLite database to persist the state
conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
memory = SqliteSaver(conn)

# Compile the graph.
# The 'interrupt_before' parameter is the secret to our whole project!
graph = builder.compile(
    checkpointer=memory,
    interrupt_before=["auditor_loop"] 
)