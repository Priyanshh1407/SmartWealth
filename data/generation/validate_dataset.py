import argparse
import json
from pathlib import Path

from data.generation.dataset_contract import (
    DEFAULT_DATASET_DIR,
    DEFAULT_PUBLIC_DIR,
    PROJECT_ROOT,
    TRANSACTIONS_FILENAME,
    validate_dataset_artifacts,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Validate SmartWealth dataset, answer key, public copy, and receipts.'
    )
    parser.add_argument('--dataset-dir', type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument(
        '--public-csv',
        type=Path,
        default=DEFAULT_PUBLIC_DIR / TRANSACTIONS_FILENAME,
    )
    parser.add_argument(
        '--receipts-dir',
        type=Path,
        default=DEFAULT_DATASET_DIR / 'receipts',
    )
    args = parser.parse_args()
    result = validate_dataset_artifacts(
        args.dataset_dir,
        public_csv=args.public_csv,
        receipts_dir=args.receipts_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
