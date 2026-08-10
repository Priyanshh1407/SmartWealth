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

# 3. Fix the import path so Python can find the 'backend' module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.app.graph.nodes.corrective_rag import _evaluate_category

def run_crag_test():
    print("[TEST] Triggering Node 2 (CRAG) Negative Test...")
    
    # Test with a category that should NOT be found in the Indian tax corpus
    result = _evaluate_category("New Vegas County Hyper-Loop Commuter Passes", max_retries=1)

    assert result["is_deductible"] is False, \
        f"Expected is_deductible=False, got {result['is_deductible']}"
    
    assert result["reasoning"] == "undetermined", \
        f"Expected 'undetermined', got '{result['reasoning']}'. Model hallucinated."
    
    assert result["source_citation"] == "None", \
        "Expected no citations for undetermined expense."

    print("[SUCCESS] Negative test passed: System flagged 'undetermined' for fictitious category.")

if __name__ == "__main__":
    run_crag_test()