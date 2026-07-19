import sys
import os
import csv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from backend.app.graph.nodes.extraction import extraction_node
from backend.app.graph.state import Transaction

def run_extraction_test():
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../data/synthetic/transactions_2025.csv'))
    transactions_to_test = []
    
    # Read only the first 5 rows of our CSV for a quick test
    with open(csv_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= 5:
                break
            transactions_to_test.append(
                Transaction(
                    transaction_id=row['transaction_id'],
                    date=row['date'],
                    merchant=row['merchant'],
                    amount=float(row['amount']),
                    category=row['category'], 
                    description=row['description']
                )
            )

    # Mock the state object
    mock_state = {
        "transactions": transactions_to_test,
        "categorized": []
    }
    
    print("🚀 Triggering Node 1 against live CSV data...")
    new_state = extraction_node(mock_state)
    print("✅ Extraction Complete!")

if __name__ == "__main__":
    run_extraction_test()