import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from backend.app.graph.state import AuditState, CategorizedTransaction
from backend.app.tools.categorizer_tools import CategorizationResult, CATEGORIZER_PROMPT

# Load the .env file containing your GEMINI_API_KEY
load_dotenv()

# Initialize the Gemini model.
llm = ChatGoogleGenerativeAI(model="gemini-3-flash-preview", temperature=0)

# Bind our strict Pydantic schema to the LLM
structured_llm = llm.with_structured_output(CategorizationResult)

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