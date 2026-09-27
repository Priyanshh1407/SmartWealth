from pydantic import BaseModel, ConfigDict, Field, field_validator

CATEGORIZER_PROMPT_VERSION = 'categorizer-v1'

# The ONLY valid business tax deduction categories
VALID_CATEGORIES = [
    "Software Subscriptions",
    "Travel & Transit",
    "Business Meals",
    "Entertainment",
    "Office Supplies",
    "Hardware & Equipment",
    "Professional Fees",
    "Telephone & Internet",
]

# 1. Define the specific schema we want the LLM to output
class CategorizationResult(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    predicted_category: str = Field(
        description="The exact tax category of the expense. MUST be one of: 'Software Subscriptions', 'Travel & Transit', 'Business Meals', 'Entertainment', 'Office Supplies', 'Hardware & Equipment', 'Professional Fees', 'Telephone & Internet'."
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="A float between 0.0 and 1.0 indicating confidence. Score MUST be below 0.70 ONLY when the merchant is missing/truncated/a POS terminal identifier, OR the original category is not a recognized business expense category."
    )
    reasoning: str = Field(
        min_length=1,
        max_length=500,
        description="A short 1-sentence explanation of why this category and confidence score were chosen."
    )

    @field_validator('predicted_category')
    @classmethod
    def require_allowed_category(cls, value: str) -> str:
        if value not in VALID_CATEGORIES:
            raise ValueError('predicted_category is not allowed')
        return value

# 2. Define our system prompt instruction
CATEGORIZER_PROMPT = """
You are an expert Indian financial auditor AI. Your job is to analyze a single bank transaction and categorize it for business tax deduction purposes.

THE ONLY ALLOWED CATEGORIES ARE:
- Software Subscriptions
- Travel & Transit
- Business Meals
- Entertainment
- Office Supplies
- Hardware & Equipment
- Professional Fees
- Telephone & Internet

CONFIDENCE SCORING RULES (follow in exact order):

RULE 1 — MERCHANT NAME IS KING:
  If the merchant name is a well-known, recognizable business (e.g., 'Amazon India', 'Flipkart', 'Croma', 'Reliance Digital', 'AWS India', 'GitHub', 'Zoho', 'Swiggy', 'Zomato', 'Chai Point', 'BookMyShow', 'PVR INOX', 'IndiGo', 'Ola', 'IRCTC', 'Jio', 'Airtel', 'Deloitte India'), the MERCHANT ALONE is sufficient to categorize the transaction. Ignore how strange or nonsensical the description may look — descriptions from bank statements are often auto-generated gibberish and should NOT reduce confidence.
  → confidence_score = 0.85 to 1.0

RULE 2 — FLAG IF MERCHANT IS UNCLEAR:
  If the merchant name is EMPTY, MISSING, a POS terminal identifier (e.g., 'POS DEBIT', 'POS PURCHASE'), or a truncated abbreviation that is ambiguous (e.g., 'AMZN Mktp US', 'AMZN', 'SQ *', 'PYMT'):
  → confidence_score MUST be below 0.70

RULE 3 — FLAG IF ORIGINAL CATEGORY IS SUSPICIOUS:
  Each transaction may include an "Original Category" field from the bank statement. If this original category does NOT match any of the allowed business categories listed above (e.g., it says something like 'Moj Masti', 'Personal', 'Fun', or any non-business label), this is a RED FLAG that the expense may not be a legitimate business deduction.
  → confidence_score MUST be below 0.70, even if the merchant name is recognizable.

RULE 4 — DESCRIPTIONS ARE UNRELIABLE:
  Bank descriptions are frequently auto-generated nonsense or UPI references (e.g., 'UPI/412856789/SWIGGY/MUMBAI'). These are normal bank statement artifacts. Do NOT lower confidence just because a description sounds weird. Only lower confidence if the merchant itself is unclear (Rule 2) or the original category is suspicious (Rule 3).

EXAMPLES OF CORRECT SCORING:
- Merchant='Apple India', Original Category='Hardware & Equipment', Description='POS 4892' → Hardware & Equipment, confidence=0.95 (clear merchant, valid category, ignore gibberish description)
- Merchant='Unknown', Original Category='Travel & Transit', Description='MISC CHRG' → Travel & Transit, confidence=0.50 (no merchant at all)
- Merchant='POS DEBIT', Original Category='Travel & Transit', Description='some text' → Travel & Transit, confidence=0.50 (POS terminal, not a real merchant)
- Merchant='Amazon India', Original Category='Moj Masti', Description='some text' → Hardware & Equipment, confidence=0.50 (merchant is clear BUT original category 'Moj Masti' is NOT a valid business category — flag for review)

Do not guess blindly. It is better to have a low confidence score than to incorrectly categorize a transaction.
"""
