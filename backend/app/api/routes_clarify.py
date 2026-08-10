from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from langgraph.types import Command
import threading

# Changed app_graph to graph to match your builder.py
from backend.app.graph.builder import graph

router = APIRouter()

class ClarificationAnswer(BaseModel):
    transaction_id: str
    answer: str

@router.get("/clarifications/{thread_id}")
async def get_clarifications(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    state = graph.get_state(config)
    
    # If the graph is paused, next will contain the node name
    if not state.next:
        return {"status": "running or completed", "pending": []}
        
    # Safely extract the interrupt data from the tasks
    pending_tasks = []
    if state.tasks and state.tasks[0].interrupts:
        pending_tasks = state.tasks[0].interrupts[0].value
        
    return {"status": "paused", "pending": pending_tasks}

@router.post("/resume/{thread_id}")
async def resume_graph(thread_id: str, answers: List[ClarificationAnswer]):
    config = {"configurable": {"thread_id": thread_id}}
    state = graph.get_state(config)
    
    if not state.next:
        raise HTTPException(status_code=400, detail="Graph is not paused.")

    # Format answers to pass back into the graph
    formatted_answers = [{"transaction_id": ans.transaction_id, "answer": ans.answer} for ans in answers]
    
    # Run in a background thread so we don't block the FastAPI event loop!
    # If we block the loop, the frontend cannot poll /state and progress bars freeze.
    def _resume_graph():
        try:
            for _ in graph.stream(Command(resume=formatted_answers), config, stream_mode="values"):
                pass 
        except Exception as e:
            print(f"Error resuming graph: {e}")
            
    thread = threading.Thread(target=_resume_graph, daemon=True)
    thread.start()
        
    return {"status": "resumed"}