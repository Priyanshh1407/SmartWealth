from enum import Enum
from typing import Dict, List, Optional, TypedDict

from pydantic import BaseModel, Field, field_validator, model_validator


class TaxTreatment(str, Enum):
    DEDUCTIBLE = 'deductible'
    NON_DEDUCTIBLE = 'non_deductible'
    DEPRECIABLE = 'depreciable'
    PARTIALLY_DEDUCTIBLE = 'partially_deductible'
    UNDETERMINED = 'undetermined'


class LegalEvidence(BaseModel):
    '''Exact, versioned evidence supporting one legal treatment.'''

    corpus_version: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    page: int = Field(ge=1)
    chunk_id: str = Field(min_length=1)
    section: str = Field(min_length=1)
    passage: str = Field(min_length=20)
    retrieval_score: float = Field(ge=0.0, le=1.0)

    @field_validator('corpus_version', 'document_id', 'title', 'chunk_id', 'section', 'passage')
    @classmethod
    def reject_blank_or_placeholder_text(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned.lower() in {'none', 'unknown', 'n/a', 'unversioned'}:
            raise ValueError('evidence fields cannot use placeholder values')
        return cleaned

    @model_validator(mode='after')
    def require_consistent_chunk_identity(self):
        if not self.chunk_id.startswith(f'{self.document_id}:'):
            raise ValueError('chunk_id must be namespaced by document_id')
        return self


class Transaction(BaseModel):
    transaction_id: str
    date: str
    merchant: str
    amount: float = Field(ge=0.0)
    category: str
    description: str


class CategorizedTransaction(BaseModel):
    transaction_id: str
    predicted_category: str
    confidence_score: float = Field(ge=0.0, le=1.0)


class DeductibilityResult(BaseModel):
    transaction_id: str
    treatment: TaxTreatment
    transaction_amount: float = Field(ge=0.0)
    allowed_current_period_amount: float = Field(ge=0.0)
    reasoning: str
    evidence: Optional[LegalEvidence] = None
    business_purpose_supported: bool = False
    requires_accountant_review: bool = False
    review_reasons: List[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def enforce_safe_treatment_and_amount(self):
        positive = {
            TaxTreatment.DEDUCTIBLE,
            TaxTreatment.DEPRECIABLE,
            TaxTreatment.PARTIALLY_DEDUCTIBLE,
        }
        if self.treatment in positive and self.evidence is None:
            raise ValueError('positive treatment requires complete legal evidence')
        if self.allowed_current_period_amount > self.transaction_amount:
            raise ValueError('allowed amount cannot exceed transaction amount')
        if self.treatment in {TaxTreatment.NON_DEDUCTIBLE, TaxTreatment.UNDETERMINED}:
            if self.allowed_current_period_amount != 0:
                raise ValueError('non-deductible or undetermined treatment must allow zero')
        if self.treatment == TaxTreatment.PARTIALLY_DEDUCTIBLE and self.allowed_current_period_amount:
            if self.allowed_current_period_amount >= self.transaction_amount:
                raise ValueError('partial deduction must be less than transaction amount')
        return self


class ClarificationRequest(BaseModel):
    transaction_id: str
    question: str
    retries: int = 0


class DeductionClaim(BaseModel):
    transaction_id: str
    category: str
    treatment: TaxTreatment
    transaction_amount: float = Field(ge=0.0)
    allowed_current_period_amount: float = Field(gt=0.0)
    evidence: LegalEvidence
    reasoning: str
    status: str = 'evidence_backed_draft_pending_review'


class UnresolvedItem(BaseModel):
    transaction_id: str
    original_description: str
    reason_flagged: str


class AuditReport(BaseModel):
    total_transactions_processed: int
    total_allowed_current_period_deductions_inr: float
    deduction_claims: List[DeductionClaim]
    unresolved_items: List[UnresolvedItem]
    outcome_counts: Dict[str, int]
    warnings: List[str]


class AuditState(TypedDict):
    thread_id: str
    demo_scenario: Optional[str]
    transactions: List[Transaction]
    categorized: List[CategorizedTransaction]
    deductibility_results: List[DeductibilityResult]
    pending_clarifications: List[ClarificationRequest]
    resolved_clarifications: Dict[str, str]
    unresolved_flags: List[str]
    final_report: Optional[AuditReport]
    current_node: str
    errors: List[str]
