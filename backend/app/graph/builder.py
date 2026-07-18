import sqlite3
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from .state import AuditState

# --- 1. Stub Nodes (The Placeholder Logic) ---

def extraction_node(state: AuditState):
    print("🟢 [NODE 1] Running Extraction & Categorization...")
    return {"current_node": "extraction_node"}

def corrective_rag_node(state: AuditState):
    print("🟢 [NODE 2] Running Corrective RAG...")
    return {"current_node": "corrective_rag_node"}

def auditor_loop_node(state: AuditState):
    print("🟡 [NODE 3] Auditor Loop triggered (Waiting for human input)...")
    return {"current_node": "auditor_loop_node"}

def report_node(state: AuditState):
    print("🟢 [NODE 4] Generating Final Report...")
    return {"current_node": "report_node"}

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
builder.add_edge("extraction", "corrective_rag")
builder.add_edge("corrective_rag", "auditor_loop")
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