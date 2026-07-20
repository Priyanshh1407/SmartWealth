from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Any, Dict
from app.graph.builder import graph
from app.graph.state import Transaction

router = APIRouter()

class RunRequest(BaseModel):
    thread_id: str
    transactions: List[Dict[str, Any]]

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
                amount=float(t.get("amount", 0.0)),
                category=t.get("category", ""),
                description=t.get("description", "")
            )
        )
        
    initial_state = {
        "transactions": txns,
        "current_node": "init"
    }
    
    # Start the graph execution
    for _ in graph.stream(initial_state, config, stream_mode="values"):
        pass
        
    return {"status": "started", "thread_id": request.thread_id}