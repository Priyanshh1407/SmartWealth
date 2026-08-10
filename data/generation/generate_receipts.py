import json
import csv
import os
from playwright.sync_api import sync_playwright

def load_data():
    # 1. Load the secret answer key
    with open("data/generation/ground_truth_schema.json", "r") as f:
        ground_truth = json.load(f)
    
    # 2. Load the public ledger
    transactions = {}
    with open("data/synthetic/transactions_2025.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            transactions[row["transaction_id"]] = row
            
    return ground_truth, transactions

def generate_html(txn):
    # An HTML template with a dark, neon-accented UI for our synthetic receipts
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: 'Courier New', Courier, monospace; background-color: #0d0d0d; color: #00ffcc; padding: 40px; }}
            .receipt {{ border: 2px dashed #b026ff; padding: 30px; max-width: 350px; margin: auto; box-shadow: 0 0 15px rgba(176, 38, 255, 0.2); }}
            h1 {{ color: #b026ff; text-align: center; text-transform: uppercase; font-size: 24px; letter-spacing: 2px; }}
            .details {{ margin-bottom: 20px; font-size: 14px; opacity: 0.8; }}
            .item {{ display: flex; justify-content: space-between; margin-bottom: 15px; font-size: 16px; }}
            .total {{ font-weight: bold; border-top: 1px solid #00ffcc; padding-top: 15px; margin-top: 25px; font-size: 18px; color: #ffffff; }}
        </style>
    </head>
    <body>
        <div class="receipt">
            <h1>{txn['merchant']}</h1>
            <div class="details">
                <p>Date: {txn['date']}</p>
                <p>TXN ID: {txn['transaction_id']}</p>
            </div>
            <hr style="border: 1px dashed #333; margin-bottom: 20px;">
            <div class="item">
                <span>{txn['description'][:20]}...</span>
                <span>₹{txn['amount']}</span>
            </div>
            <div class="item total">
                <span>TOTAL PAID</span>
                <span>₹{txn['amount']}</span>   
            </div>
        </div>
    </body>
    </html>
    """
    return html_content

def render_pdfs():
    ground_truth, transactions = load_data()
    
    # Ensure the receipts output directory exists
    output_dir = "data/synthetic/receipts"
    os.makedirs(output_dir, exist_ok=True)
    
    print("Initializing PDF engine...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        count = 0
        for txn_id, truth in ground_truth.items():
            # The gap rate logic: Only generate a PDF if has_receipt is True!
            if truth["has_receipt"]:
                txn = transactions[txn_id]
                html = generate_html(txn)
                
                # Load the HTML string into the browser
                page.set_content(html)
                
                # Print to PDF
                pdf_path = f"{output_dir}/{txn_id}.pdf"
                page.pdf(path=pdf_path, format="A5", print_background=True)
                
                count += 1
                if count % 25 == 0:
                    print(f"Rendered {count} PDFs so far...")
                
        browser.close()
        
        # Calculate exactly how many were skipped for our Auditor Loop later
        total_txns = len(transactions)
        missing_count = total_txns - count
        
        print("\n--- GENERATION COMPLETE ---")
        print(f"[SUCCESS] Generated {count} receipt PDFs.")
        print(f"[WARNING] Deliberately skipped {missing_count} receipts (This is your {missing_count/total_txns*100:.1f}% gap rate).")

if __name__ == "__main__":
    render_pdfs()