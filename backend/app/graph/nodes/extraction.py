import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from backend.app.graph.state import AuditState, CategorizedTransaction
from backend.app.tools.categorizer_tools import CategorizationResult, CATEGORIZER_PROMPT

# Load the .env file containing your GEMINI_API_KEY
load_dotenv()

primary_llm = ChatGoogleGenerativeAI(
        model="gemini-3-flash-preview",
        temperature=0,
        max_retries=0
)

# 2. Define the fallback LLM (Groq)
# Llama 3 8B is incredibly fast and free on Groq, perfect for categorization
fallback_llm = ChatGroq(
    model="llama-3.1-8b-instant", 
    temperature=0,
    api_key=os.environ.get("GROQ_API_KEY")
)

# 3. Bind the structured output schema to both models
# Replace 'CategorizationSchema' with your actual Pydantic model
primary_structured = primary_llm.with_structured_output(CategorizationResult)
fallback_structured = fallback_llm.with_structured_output(CategorizationResult)

structured_llm = primary_structured.with_fallbacks([fallback_structured])

def extraction_node(state: AuditState):
    print("🟢 [NODE 1] Running LLM Extraction & Categorization...")
    
    transactions = state.get("transactions", [])
    categorized_results = []
    
    for txn in transactions:
        print(f"   -> Analyzing {txn.transaction_id} (Merchant: {txn.merchant})...")
        
        prompt = f"""
        {CATEGORIZER_PROMPT}
        
        TRANSACTION DETAILS:
        - ID: {txn.transaction_id}
        - Date: {txn.date}
        - Merchant: {txn.merchant}
        - Amount: ₹{txn.amount}
        - Description: {txn.description}
        """
        
        try:
            result = structured_llm.invoke(prompt)
            
            categorized_txn = CategorizedTransaction(
                transaction_id=txn.transaction_id,
                predicted_category=result.predicted_category,
                confidence_score=result.confidence_score
            )
            categorized_results.append(categorized_txn)
            
            print(f"      Result: {result.predicted_category} | Confidence: {result.confidence_score}")
            print(f"      Reasoning: {result.reasoning}\n")
            
        except Exception as e:
            print(f"      ⚠️ API Error on {txn.transaction_id}: {e}\n")
            categorized_results.append(
                CategorizedTransaction(
                    transaction_id=txn.transaction_id,
                    predicted_category="Unknown",
                    confidence_score=0.0
                )
            )
            
    return {"categorized": categorized_results, "current_node": "extraction_node"}