import argparse
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from data.generation.dataset_contract import (
    DEFAULT_DATASET_DIR,
    DEFAULT_PUBLIC_DIR,
    GROUND_TRUTH_FILENAME,
    MANIFEST_FILENAME,
    PROJECT_ROOT,
    TRANSACTIONS_FILENAME,
    atomic_write_bytes,
    atomic_write_json,
    csv_bytes,
    ensure_managed_directory,
    validate_dataset_artifacts,
)


CATEGORIES = [
    'Software Subscriptions',
    'Travel & Transit',
    'Business Meals',
    'Entertainment',
    'Office Supplies',
    'Hardware & Equipment',
    'Professional Fees',
    'Telephone & Internet',
]

MERCHANTS = {
    'Software Subscriptions': ['GitHub', 'AWS India', 'Zoho', 'Freshworks', 'Razorpay'],
    'Travel & Transit': ['Ola', 'IndiGo', 'IRCTC', 'Uber India', 'Air India'],
    'Business Meals': ['Swiggy', 'Zomato', 'Chai Point', 'Haldirams', 'Barbeque Nation'],
    'Entertainment': ['BookMyShow', 'PVR INOX', 'Wonderla', 'Netflix India'],
    'Office Supplies': ['Amazon India', 'Flipkart', 'Nalli Silks Stationery'],
    'Hardware & Equipment': ['Croma', 'Reliance Digital', 'Apple India'],
    'Professional Fees': ['Deloitte India', 'KPMG India', 'IndiaFilings'],
    'Telephone & Internet': ['Jio', 'Airtel', 'BSNL', 'ACT Fibernet'],
}

TREATMENT_RULES = {
    'Software Subscriptions': {
        'treatment': 'deductible',
        'allowed_fraction': 1.0,
        'section': 'Section 37(1)',
    },
    'Travel & Transit': {
        'treatment': 'deductible',
        'allowed_fraction': 1.0,
        'section': 'Section 37(1)',
    },
    'Business Meals': {
        'treatment': 'deductible',
        'allowed_fraction': 1.0,
        'section': 'Section 37(1)',
    },
    'Entertainment': {
        'treatment': 'non_deductible',
        'allowed_fraction': 0.0,
        'section': 'Section 37',
    },
    'Office Supplies': {
        'treatment': 'deductible',
        'allowed_fraction': 1.0,
        'section': 'Section 37(1)',
    },
    'Hardware & Equipment': {
        'treatment': 'depreciable',
        'allowed_fraction': None,
        'section': 'Section 32',
    },
    'Professional Fees': {
        'treatment': 'deductible',
        'allowed_fraction': 1.0,
        'section': 'Section 37(1)',
    },
    'Telephone & Internet': {
        'treatment': 'deductible',
        'allowed_fraction': 1.0,
        'section': 'Section 37(1)',
    },
}

VAGUE_DESCRIPTIONS = [
    'POS DEBIT',
    'MISC CHRG',
    'UPI/UNKNOWN',
    'NEFT TRANSFER',
    'ATM WDL',
]

EDGE_CASES = {
    'TXN-1038': {
        'category': 'Hardware & Equipment',
        'merchant': 'Apple India',
        'amount': 163572.42,
        'description': 'POS 4892 APPLE BKC MUMBAI',
        'has_receipt': True,
    },
    'TXN-1095': {
        'category': 'Unknown',
        'merchant': 'Unknown',
        'amount': 17133.89,
        'description': 'MISC CHRG',
        'has_receipt': False,
    },
    'TXN-1187': {
        'category': 'Office Supplies',
        'merchant': 'Flipkart',
        'amount': 33259.70,
        'description': 'NEFT-123-FLIPKART-STATIONERY',
        'has_receipt': True,
    },
    'TXN-1192': {
        'category': 'Software Subscriptions',
        'merchant': 'GitHub',
        'amount': 13463.88,
        'description': 'BIL/ONLPAY/GITHUB INC',
        'has_receipt': True,
    },
    'TXN-1292': {
        'category': 'Entertainment',
        'merchant': 'PVR INOX',
        'amount': 4500.00,
        'description': 'UPI/987654/PVR/DELHI',
        'has_receipt': True,
    },
}


def load_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding='utf-8'))
    config = payload.get('generation', {}) if isinstance(payload, dict) else {}
    required = {
        'dataset_version',
        'seed',
        'num_transactions',
        'start_date',
        'receipt_gap_percentage',
    }
    missing = required - set(config)
    if missing:
        raise ValueError(f'Missing generation configuration: {sorted(missing)}')
    if not 0 <= int(config['receipt_gap_percentage']) <= 100:
        raise ValueError('receipt_gap_percentage must be between 0 and 100.')
    if int(config['num_transactions']) <= 0:
        raise ValueError('num_transactions must be positive.')
    date.fromisoformat(str(config['start_date']))
    return config


def generate_indian_description(
    merchant: str,
    rng: random.Random,
) -> str:
    if merchant == 'Unknown':
        return rng.choice(VAGUE_DESCRIPTIONS)
    if rng.random() < 0.15:
        return rng.choice(VAGUE_DESCRIPTIONS)
    prefix = rng.choice(['UPI', 'NEFT', 'POS', 'IMPS', 'BIL/ONLPAY'])
    reference = rng.randint(100000, 999999)
    city = rng.choice(['MUMBAI', 'DELHI', 'BENGALURU', 'CHENNAI', 'PUNE', 'HYDERABAD'])
    return f'{prefix}/{reference}/{merchant.upper()}/{city}'


def _amount_for(category: str, rng: random.Random) -> float:
    if category == 'Hardware & Equipment':
        bounds = (40000.0, 250000.0)
    elif category in {'Business Meals', 'Entertainment'}:
        bounds = (800.0, 12000.0)
    elif category == 'Professional Fees':
        bounds = (15000.0, 100000.0)
    elif category == 'Telephone & Internet':
        bounds = (500.0, 5000.0)
    else:
        bounds = (1500.0, 40000.0)
    return round(rng.uniform(*bounds), 2)


def generate_data(config: dict[str, Any]) -> tuple[list[dict], dict]:
    rng = random.Random(int(config['seed']))
    start_date = date.fromisoformat(str(config['start_date']))
    transactions = []
    truth_rows = []

    for index in range(int(config['num_transactions'])):
        transaction_id = f'TXN-{1000 + index}'
        edge = EDGE_CASES.get(transaction_id)
        if edge:
            category = edge['category']
            merchant = edge['merchant']
            amount = edge['amount']
            description = edge['description']
            has_receipt = edge['has_receipt']
        else:
            category = rng.choice(CATEGORIES)
            merchant = rng.choice(MERCHANTS[category])
            amount = _amount_for(category, rng)
            description = generate_indian_description(merchant, rng)
            has_receipt = (
                rng.randint(1, 100) > int(config['receipt_gap_percentage'])
            )

        transaction_date = (
            start_date + timedelta(days=rng.randint(0, 364))
        ).isoformat()
        transactions.append({
            'transaction_id': transaction_id,
            'date': transaction_date,
            'merchant': merchant,
            'amount': f'{float(amount):.2f}',
            'description': description,
        })

        if category == 'Unknown':
            treatment = {
                'treatment': 'undetermined',
                'allowed_fraction': None,
                'section': None,
            }
        else:
            treatment = TREATMENT_RULES[category]
        truth_rows.append({
            'transaction_id': transaction_id,
            'true_category': category,
            'expected_treatment': treatment['treatment'],
            'expected_allowed_fraction': treatment['allowed_fraction'],
            'section': treatment['section'],
            'has_receipt': bool(has_receipt),
        })

    transactions.sort(key=lambda row: (row['date'], row['transaction_id']))
    ground_truth = {
        'dataset_version': str(config['dataset_version']),
        'seed': int(config['seed']),
        'transactions': truth_rows,
    }
    return transactions, ground_truth


def generate_dataset(
    *,
    config_path: Path,
    output_dir: Path,
    public_dir: Path,
    allowed_root: Path,
    initialize_output: bool = False,
) -> dict[str, Any]:
    config = load_config(config_path)
    output_dir = ensure_managed_directory(
        output_dir,
        allowed_root=allowed_root,
        initialize=initialize_output,
        allowed_existing_names={
            TRANSACTIONS_FILENAME,
            GROUND_TRUTH_FILENAME,
            MANIFEST_FILENAME,
            'receipts',
        },
    )
    public_dir.mkdir(parents=True, exist_ok=True)
    transactions, ground_truth = generate_data(config)

    transaction_content = csv_bytes(transactions)
    csv_path = output_dir / TRANSACTIONS_FILENAME
    public_csv = public_dir / TRANSACTIONS_FILENAME
    atomic_write_bytes(csv_path, transaction_content)
    atomic_write_bytes(public_csv, transaction_content)
    atomic_write_json(output_dir / GROUND_TRUTH_FILENAME, ground_truth)

    validation = validate_dataset_artifacts(
        output_dir,
        public_csv=public_csv,
    )
    manifest = {
        **validation,
        'public_columns': list(transactions[0].keys()),
        'schema': 'ground_truth_schema.json',
    }
    atomic_write_json(output_dir / MANIFEST_FILENAME, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Generate the versioned SmartWealth synthetic dataset.'
    )
    parser.add_argument(
        '--config',
        type=Path,
        default=PROJECT_ROOT / 'data' / 'generation' / 'config.yaml',
    )
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument('--public-dir', type=Path, default=DEFAULT_PUBLIC_DIR)
    parser.add_argument(
        '--initialize-output',
        action='store_true',
        help='Adopt an existing directory only when it contains known generated entries.',
    )
    args = parser.parse_args()
    manifest = generate_dataset(
        config_path=args.config,
        output_dir=args.output_dir,
        public_dir=args.public_dir,
        allowed_root=PROJECT_ROOT / 'data',
        initialize_output=args.initialize_output,
    )
    transaction_count = manifest['transaction_count']
    dataset_version = manifest['dataset_version']
    transactions_hash = manifest['transactions_sha256']
    print(
        f'Generated {transaction_count} transactions '
        f'for dataset {dataset_version}.'
    )
    print(f'Transactions SHA-256: {transactions_hash}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
