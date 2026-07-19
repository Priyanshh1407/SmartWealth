from pydantic import BaseModel, Field

# 1. Define the specific schema we want the LLM to output
class CategorizationResult(BaseModel):
    predicted_category: str = Field(
        description="The exact tax category of the expense. MUST be one of: 'Software Subscriptions', 'Travel & Transit', 'Meals & Entertainment', 'Office Supplies', 'Hardware & Equipment'."
    )
    confidence_score: float = Field(
        description="A float between 0.0 and 1.0 indicating confidence. CRITICAL: If the merchant is missing, an acronym like 'AMZN', or the description is vague (e.g. 'POS DEBIT'), you MUST output a score below 0.70."
    )
    reasoning: str = Field(
        description="A short 1-sentence explanation of why this category and confidence score were chosen."
    )

# 2. Define our system prompt instruction
CATEGORIZER_PROMPT = """
You are an expert Indian financial auditor AI. Your job is to analyze a single bank transaction and categorize it for business tax deduction purposes.

You must be highly skeptical. 
- If the merchant name is clear and maps perfectly to a category (e.g., 'AWS' -> Software Subscriptions), your confidence_score should be 0.9 or 1.0.
- If the merchant name is missing, truncated (e.g., 'AMZN'), or the description is generic (e.g., 'MISC CHRG', 'POS DEBIT'), you cannot know for sure what was purchased. Your confidence_score MUST be below 0.70 so a human accountant can review it.

Do not guess blindly. It is better to have a low confidence score than to incorrectly categorize a transaction.
"""