import sys
import os
from dotenv import load_dotenv, find_dotenv

# 1. Automatically hunt down the .env file in the directory tree
env_file = find_dotenv()
if not env_file:
    raise FileNotFoundError("FATAL: Could not find a .env file. Check if Windows accidentally named it '.env.txt'.")

load_dotenv(env_file)

# 2. Verify the key actually loaded into memory
if not os.getenv("GOOGLE_API_KEY"):
    raise ValueError("FATAL: Found the .env file, but 'GOOGLE_API_KEY' is missing or spelled wrong inside it.")

# 3. Fix the import path so Python can find the 'app' module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.graph.state import Transaction
from app.graph.nodes.corrective_rag import evaluate_deductibility

def run_crag_test():
    print("🚀 Triggering Node 2 (CRAG) Negative Test...")
    
    ambiguous_transaction = Transaction(
        transaction_id="tx_999",
        merchant="New Vegas Transit",
        description="Monthly Hyper-Loop Pass - New Vegas County",
        amount=450.00,
        category="New Vegas County Hyper-Loop Commuter Deduction",
        date="2025-06-15",
        confidence_score=0.95
    )

    result = evaluate_deductibility(ambiguous_transaction, max_retries=1)

    # 3. Assert
    assert result.is_deductible is False, \
        f"Expected is_deductible to be False, but got '{result.is_deductible}'."
    
    assert result.reasoning == "undetermined", \
        f"Expected reasoning to be 'undetermined', but got '{result.reasoning}'. The model hallucinated an answer."
    
    assert result.source_citation == "None", \
        "Expected no source citations for an undetermined expense."

    print("✅ Negative test passed: System successfully flagged 'undetermined' and avoided hallucination fallback.")

if __name__ == "__main__":
    run_crag_test()