from fastapi import APIRouter
from backend.app.graph.builder import graph
from backend.app.progress import progress_store

router = APIRouter()

@router.get("/state/{thread_id}")
async def get_state(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    state = graph.get_state(config)
    
    # Get real-time progress (updated by nodes during batch processing)
    progress = progress_store.get(thread_id)
    
    if not state.values:
        return {
            "status": "not_found",
            "progress": progress,
        }
        
    values = state.values
    
    # We want to return the categorized results, the original transactions, the deductions, and pending clarifications
    # If the graph is paused, we need to extract pending clarifications from tasks
    pending_tasks = []
    if state.next and state.tasks and state.tasks[0].interrupts:
        pending_tasks = state.tasks[0].interrupts[0].value
    else:
        pending_tasks = values.get("pending_clarifications", [])
    
    # Determine status based on graph state + progress store
    if state.next:
        status = "paused"
    elif progress and progress.get("completed"):
        status = "completed"
    else:
        status = "running"
        
    return {
        "status": status,
        "transactions": [t.dict() for t in values.get("transactions", [])] if values.get("transactions") else [],
        "categorized": [c.dict() for c in values.get("categorized", [])] if values.get("categorized") else [],
        "deductibility_results": [d.dict() for d in values.get("deductibility_results", [])] if values.get("deductibility_results") else [],
        "pending_clarifications": pending_tasks,
        "unresolved_flags": values.get("unresolved_flags", []),
        "current_node": values.get("current_node", "unknown"),
        "final_report": values.get("final_report").dict() if values.get("final_report") else None,
        "progress": progress,
        "errors": values.get("errors", []) + (progress.get("errors", []) if progress else []),
    }

@router.post("/reset")
async def reset_backend():
    """
    Called when the user clicks 'Reset Audit' in the UI.
    Clears the progress store to ensure no stale state lingers.
    """
    progress_store.clear_all()
    return {"status": "backend_reset"}
