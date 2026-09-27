from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from backend.app.config import get_settings

settings = get_settings()

class GradeResult(BaseModel):
    """Binary score for relevance check on retrieved documents."""
    binary_score: str = Field(
        description="Documents are relevant to the question, 'yes' or 'no'"
    )

def get_retrieval_grader():
    """Returns a runnable chain that outputs a strict yes/no GradeResult."""
    # 1. Initialize primary LLM (Groq is much faster, so we use it as primary)
    primary_llm = ChatGroq(
        model=settings.groq_model,
        temperature=0,
        max_retries=0,
        timeout=15
    )
    
    # 2. Initialize the fallback LLM (Gemini)
    fallback_llm = ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        temperature=0,
        max_retries=0,
        timeout=15
    )

    # 3. Bind the Pydantic schema to BOTH models individually
    primary_structured = primary_llm.with_structured_output(GradeResult)
    fallback_structured = fallback_llm.with_structured_output(GradeResult)
    
    # 4. Chain them together — when Gemini hits 429, Groq takes over
    structured_llm_grader = primary_structured.with_fallbacks(
        [fallback_structured],
        exceptions_to_handle=(Exception,)  # Catch ALL exceptions including gRPC errors
    )

    system = """You are a grader assessing relevance of a retrieved document to a user question.
    If the document contains keyword(s) or semantic meaning related to the question, grade it as relevant.
    Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question."""

    grade_prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        ("human", "Retrieved document: \n\n {document} \n\n User question: {question}"),
    ])

    return grade_prompt | structured_llm_grader
