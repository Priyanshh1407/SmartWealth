import csv
import random
import json
import yaml
from datetime import datetime, timedelta
from faker import Faker
import os

# 1. Load Configuration
with open("data/generation/config.yaml", "r") as f:
    config = yaml.safe_load(f)["generation"]

# 2. Initialization and Seeding
fake = Faker()
Faker.seed(config["seed"])
random.seed(config["seed"])

# 3. Domain Logic
CATEGORIES = [
    "Software Subscriptions", 
    "Travel & Transit", 
    "Meals & Entertainment", 
    "Office Supplies", 
    "Hardware & Equipment"
]

MERCHANTS = {
    "Software Subscriptions": ["GitHub", "AWS", "Notion", "Adobe", "Vercel"],
    "Travel & Transit": ["Uber", "Delta Airlines", "Amtrak", "Lyft"],
    "Meals & Entertainment": ["Starbucks", "Sweetgreen", "Local Steakhouse", "DoorDash"],
    "Office Supplies": ["Staples", "Amazon", "Paper Source"],
    "Hardware & Equipment": ["Apple", "Best Buy", "B&H Photo Video"]
}

# The ground truth rules for our synthetic universe
DEDUCTIBILITY_RULES = {
    "Software Subscriptions": "Fully Deductible",
    "Travel & Transit": "Fully Deductible",
    "Meals & Entertainment": "Partially Deductible", 
    "Office Supplies": "Fully Deductible",
    "Hardware & Equipment": "Requires Depreciation"
}

def generate_data():
    transactions = []
    ground_truth = {}
    
    start_date = datetime.strptime(config["start_date"], "%Y-%m-%d")
    
    for i in range(config["num_transactions"]):
        category = random.choice(CATEGORIES)
        merchant = random.choice(MERCHANTS[category])
        
        if category == "Hardware & Equipment":
            # Realistic laptop/server costs in INR
            amount = round(random.uniform(40000.0, 250000.0), 2)
        elif category == "Meals & Entertainment":
            # Realistic business lunch/dinner costs in INR
            amount = round(random.uniform(800.0, 12000.0), 2)
        else:
            # Software, transit, and supplies in INR
            amount = round(random.uniform(1500.0, 40000.0), 2)
            
        random_days = random.randint(0, 364)
        txn_date = (start_date + timedelta(days=random_days)).strftime("%Y-%m-%d")
        txn_id = f"TXN-{1000 + i}"
        
        # --- THE GAP RATE LOGIC ---
        # A random roll between 1 and 100. If it's greater than 15, we have a receipt.
        has_receipt = random.randint(1, 100) > config["receipt_gap_percentage"]
        
        # 1. The public ledger (CSV data)
        transactions.append({
            "transaction_id": txn_id,
            "date": txn_date,
            "merchant": merchant,
            "amount": amount,
            "category": category,
            "description": fake.catch_phrase()
        })
        
        # 2. The secret answer key (JSON data)
        ground_truth[txn_id] = {
            "true_category": category,
            "expected_deductibility": DEDUCTIBILITY_RULES[category],
            "has_receipt": has_receipt
        }
        
    transactions.sort(key=lambda x: x["date"])
    return transactions, ground_truth

def save_outputs(transactions, ground_truth):
    # Save CSV
    csv_path = "data/synthetic/transactions_2025.csv"
    with open(csv_path, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=transactions[0].keys())
        writer.writeheader()
        writer.writerows(transactions)
    print(f"✅ Saved {len(transactions)} transactions to {csv_path}")
    
    # Save JSON Answer Key
    json_path = "data/generation/ground_truth_schema.json"
    with open(json_path, mode="w", encoding="utf-8") as file:
        json.dump(ground_truth, file, indent=4)
    print(f"✅ Saved ground truth schema to {json_path}")

if __name__ == "__main__":
    print("Generating synthetic data with ground truth...")
    txns, truth = generate_data()
    save_outputs(txns, truth)