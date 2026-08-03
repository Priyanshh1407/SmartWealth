from typing import TypedDict, List, Dict, Optional
from pydantic import BaseModel, Field

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
    source_passage: str = ""  # The actual text chunk from the tax PDF that supports the claim

class ClarificationRequest(BaseModel):
    transaction_id: str
    question: str
    retries: int = 0  # Track how many times we've asked

class DeductionClaim(BaseModel):
    transaction_id: str
    category: str
    amount: float
    is_deductible: bool
    # ENFORCER: This field is mandatory!
    source_passage_id: str = Field(..., description="Exact ChromaDB document ID")
    source_passage: str = Field(default="", description="The text passage supporting the claim")
    reasoning: str

class UnresolvedItem(BaseModel):
    transaction_id: str
    original_description: str
    reason_flagged: str

class AuditReport(BaseModel):
    total_transactions_processed: int
    total_deductions_inr: float
    deduction_claims: List[DeductionClaim]
    unresolved_items: List[UnresolvedItem]
    warnings: List[str]

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
    receipt_warnings: List[str]                       # Items missing receipts
    final_report: Optional[AuditReport]               # Output of Node 4
    current_node: str                                 # Tracks execution for the frontend
    errors: List[str]                                 # Accumulated errors/warnings from all nodes