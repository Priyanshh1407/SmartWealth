from typing import TypedDict, List, Dict, Optional
from pydantic import BaseModel

# --- 1. Pydantic Models for Strict Validation ---

class Transaction(BaseModel):
    transaction_id: str
    date: str
    merchant: str
    amount: float
    category: str
    description: str

class CategorizedTransaction(BaseModel):
    transaction_id: str
    predicted_category: str
    confidence_score: float

class DeductibilityResult(BaseModel):
    transaction_id: str
    is_deductible: bool
    reasoning: str
    source_citation: str

class ClarificationRequest(BaseModel):
    transaction_id: str
    question: str

class AuditReport(BaseModel):
    total_deductions_inr: float
    unresolved_items_count: int
    flags: List[str]

# --- 2. The Master State Object ---

class AuditState(TypedDict):
    thread_id: str
    transactions: List[Transaction]                   # Raw data from CSV
    receipts_index: Dict[str, str]                    # Maps txn_id -> path to PDF
    categorized: List[CategorizedTransaction]         # Output of Node 1
    deductibility_results: List[DeductibilityResult]  # Output of Node 2
    pending_clarifications: List[ClarificationRequest]# Queue for Node 3
    resolved_clarifications: Dict[str, str]           # User answers mapped by txn_id
    unresolved_flags: List[str]                       # Items permanently flagged for an accountant
    final_report: Optional[AuditReport]               # Output of Node 4
    current_node: str                                 # Tracks execution for the frontend