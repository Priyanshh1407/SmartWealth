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
fake = Faker('en_IN')
Faker.seed(config["seed"])
random.seed(config["seed"])

# 3. Domain Logic — Aligned with Indian Income Tax Act Sections 30-37
CATEGORIES = [
    "Software Subscriptions",   # Sec 37(1) — general business expenditure
    "Travel & Transit",         # Sec 37(1) — business travel
    "Business Meals",           # Sec 37(1) — wholly and exclusively for business
    "Entertainment",            # Sec 37(2A) abolished — NOT deductible
    "Office Supplies",          # Sec 37(1) — general business expenditure
    "Hardware & Equipment",     # Sec 32 — depreciable assets
    "Professional Fees",        # Sec 37(1) — consultants, lawyers, CAs
    "Telephone & Internet",     # Sec 37(1) — communication expenses
]

MERCHANTS = {
    "Software Subscriptions": ["GitHub", "AWS India", "Zoho", "Freshworks", "Razorpay"],
    "Travel & Transit": ["Ola", "IndiGo", "IRCTC", "Uber India", "Air India"],
    "Business Meals": ["Swiggy", "Zomato", "Chai Point", "Haldirams", "Barbeque Nation"],
    "Entertainment": ["BookMyShow", "PVR INOX", "Wonderla", "Netflix India"],
    "Office Supplies": ["Amazon India", "Flipkart", "Nalli Silks Stationery"],
    "Hardware & Equipment": ["Croma", "Reliance Digital", "Apple India"],
    "Professional Fees": ["Deloitte India", "KPMG India", "IndiaFilings"],
    "Telephone & Internet": ["Jio", "Airtel", "BSNL", "ACT Fibernet"],
}

# Ground truth rules — aligned with Indian Income Tax Act
DEDUCTIBILITY_RULES = {
    "Software Subscriptions": {"status": "Fully Deductible", "section": "Section 37(1)"},
    "Travel & Transit":       {"status": "Fully Deductible", "section": "Section 37(1)"},
    "Business Meals":         {"status": "Fully Deductible", "section": "Section 37(1)"},
    "Entertainment":          {"status": "Not Deductible",   "section": "Section 37(2A) abolished"},
    "Office Supplies":        {"status": "Fully Deductible", "section": "Section 37(1)"},
    "Hardware & Equipment":   {"status": "Requires Depreciation", "section": "Section 32"},
    "Professional Fees":      {"status": "Fully Deductible", "section": "Section 37(1)"},
    "Telephone & Internet":   {"status": "Fully Deductible", "section": "Section 37(1)"},
}

VAGUE_DESCRIPTIONS = ["POS DEBIT", "MISC CHRG", "UPI/UNKNOWN", "NEFT TRANSFER", "ATM WDL"]

def generate_indian_description(merchant, category):
    """Generates descriptions that look like real Indian bank statements."""
    if merchant == "Unknown":
        return random.choice(VAGUE_DESCRIPTIONS)
    if random.random() < 0.15:
        return random.choice(VAGUE_DESCRIPTIONS)
    prefix = random.choice(["UPI", "NEFT", "POS", "IMPS", "BIL/ONLPAY"])
    ref_num = random.randint(100000, 999999)
    city = random.choice(["MUMBAI", "DELHI", "BENGALURU", "CHENNAI", "PUNE", "HYDERABAD"])
    return f"{prefix}/{ref_num}/{merchant.upper()}/{city}"

def generate_data():
    transactions = []
    ground_truth = {}
    
    start_date = datetime.strptime(config["start_date"], "%Y-%m-%d")
    
    for i in range(config["num_transactions"]):
        txn_id = f"TXN-{1000 + i}"
        
        # --- HARDCODED EDGE CASES FOR DEMO ---
        if txn_id == "TXN-1095":
            category, merchant, amount, description = "Unknown", "Unknown", 17133.89, "MISC CHRG"
            has_receipt, expected_deductibility, section = False, "Not Deductible", "N/A"
        elif txn_id == "TXN-1187":
            category, merchant, amount, description = "Office Supplies", "Flipkart", 33259.70, "NEFT-123-FLIPKART-STATIONERY"
            has_receipt, expected_deductibility, section = True, "Fully Deductible", "Section 37(1)"
        elif txn_id == "TXN-1038":
            category, merchant, amount, description = "Hardware & Equipment", "Apple India", 163572.42, "POS 4892 APPLE BKC MUMBAI"
            has_receipt, expected_deductibility, section = True, "Requires Depreciation", "Section 32"
        elif txn_id == "TXN-1292":
            category, merchant, amount, description = "Entertainment", "PVR INOX", 4500.00, "UPI/987654/PVR/DELHI"
            has_receipt, expected_deductibility, section = True, "Not Deductible", "Section 37(2A) abolished"
        elif txn_id == "TXN-1192":
            category, merchant, amount, description = "Software Subscriptions", "GitHub", 13463.88, "BIL/ONLPAY/GITHUB INC"
            has_receipt, expected_deductibility, section = True, "Fully Deductible", "Section 37(1)"
        else:
            # NORMAL GENERATION
            category = random.choice(CATEGORIES)
            merchant = random.choice(MERCHANTS[category])
            
            if category == "Hardware & Equipment":
                amount = round(random.uniform(40000.0, 250000.0), 2)
            elif category in ("Business Meals", "Entertainment"):
                amount = round(random.uniform(800.0, 12000.0), 2)
            elif category == "Professional Fees":
                amount = round(random.uniform(15000.0, 100000.0), 2)
            elif category == "Telephone & Internet":
                amount = round(random.uniform(500.0, 5000.0), 2)
            else:
                amount = round(random.uniform(1500.0, 40000.0), 2)
                
            description = generate_indian_description(merchant, category)
            has_receipt = random.randint(1, 100) > config["receipt_gap_percentage"]
            expected_deductibility = DEDUCTIBILITY_RULES[category]["status"]
            section = DEDUCTIBILITY_RULES[category]["section"]

        random_days = random.randint(0, 364)
        txn_date = (start_date + timedelta(days=random_days)).strftime("%Y-%m-%d")
        
        # 1. The public ledger (CSV data)
        transactions.append({
            "transaction_id": txn_id,
            "date": txn_date,
            "merchant": merchant,
            "amount": amount,
            "category": category,
            "description": description
        })
        
        # 2. The secret answer key (JSON data)
        ground_truth[txn_id] = {
            "true_category": category,
            "expected_deductibility": expected_deductibility,
            "section": section,
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
    print(f"Saved {len(transactions)} transactions to {csv_path}")
    
    # Save JSON Answer Key
    json_path = "data/generation/ground_truth_schema.json"
    with open(json_path, mode="w", encoding="utf-8") as file:
        json.dump(ground_truth, file, indent=4)
    print(f"Saved ground truth schema to {json_path}")

if __name__ == "__main__":
    print("Generating synthetic data with ground truth...")
    txns, truth = generate_data()
    save_outputs(txns, truth)