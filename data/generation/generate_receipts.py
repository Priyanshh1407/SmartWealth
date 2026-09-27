import argparse
import json
import re
from contextlib import contextmanager
from html import escape
from pathlib import Path
from typing import Callable, Iterator

from data.generation.dataset_contract import (
    DEFAULT_DATASET_DIR,
    GROUND_TRUTH_FILENAME,
    MANAGED_MARKER_FILENAME,
    MANIFEST_FILENAME,
    PROJECT_ROOT,
    TRANSACTIONS_FILENAME,
    atomic_write_json,
    clear_generated_files,
    ensure_managed_directory,
    load_ground_truth,
    load_transactions,
    validate_dataset_artifacts,
)


ReceiptRenderer = Callable[[str, Path], None]
RECEIPT_NAME_PATTERN = re.compile(r'^TXN-[0-9]+\.pdf$')


def generate_html(transaction: dict[str, str]) -> str:
    merchant = escape(transaction['merchant'])
    transaction_date = escape(transaction['date'])
    transaction_id = escape(transaction['transaction_id'])
    description = escape(transaction['description'][:40])
    amount = escape(transaction['amount'])
    return f'''<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <style>
    body {{ font-family: monospace; padding: 40px; color: #111; }}
    .receipt {{ border: 2px dashed #555; padding: 30px; max-width: 420px; margin: auto; }}
    h1 {{ text-align: center; font-size: 22px; }}
    .row {{ display: flex; justify-content: space-between; margin: 12px 0; }}
    .total {{ border-top: 1px solid #555; padding-top: 14px; font-weight: bold; }}
  </style>
</head>
<body>
  <div class='receipt'>
    <h1>{merchant}</h1>
    <p>Date: {transaction_date}</p>
    <p>Transaction: {transaction_id}</p>
    <div class='row'><span>{description}</span><span>INR {amount}</span></div>
    <div class='row total'><span>Total paid</span><span>INR {amount}</span></div>
  </div>
</body>
</html>'''


@contextmanager
def playwright_renderer() -> Iterator[ReceiptRenderer]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()

        def render(html: str, path: Path) -> None:
            page.set_content(html)
            page.pdf(path=str(path), format='A5', print_background=True)

        try:
            yield render
        finally:
            browser.close()


def _adoptable_receipt_names(output_dir: Path) -> set[str]:
    if not output_dir.exists():
        return set()
    return {
        item.name
        for item in output_dir.iterdir()
        if item.is_file() and RECEIPT_NAME_PATTERN.fullmatch(item.name)
    }


def render_receipts(
    *,
    dataset_dir: Path,
    output_dir: Path,
    initialize_output: bool = False,
    renderer: ReceiptRenderer | None = None,
) -> dict:
    dataset_dir = dataset_dir.resolve()
    output_dir = ensure_managed_directory(
        output_dir,
        allowed_root=dataset_dir,
        initialize=initialize_output,
        allowed_existing_names=_adoptable_receipt_names(output_dir),
    )
    ground_truth = load_ground_truth(dataset_dir / GROUND_TRUTH_FILENAME)
    transactions = {
        row['transaction_id']: row
        for row in load_transactions(dataset_dir / TRANSACTIONS_FILENAME)
    }
    truth_rows = ground_truth['transactions']
    expected_ids = {
        row['transaction_id'] for row in truth_rows if row['has_receipt']
    }
    if not expected_ids <= set(transactions):
        missing = sorted(expected_ids - set(transactions))
        raise ValueError(f'Receipt transactions missing from CSV: {missing}')

    removed = clear_generated_files(output_dir, '*.pdf')

    def generate(active_renderer: ReceiptRenderer) -> None:
        for transaction_id in sorted(expected_ids):
            transaction = transactions[transaction_id]
            active_renderer(
                generate_html(transaction),
                output_dir / f'{transaction_id}.pdf',
            )

    if renderer is None:
        with playwright_renderer() as active_renderer:
            generate(active_renderer)
    else:
        generate(renderer)

    validation = validate_dataset_artifacts(
        dataset_dir,
        receipts_dir=output_dir,
    )
    manifest_path = dataset_dir / MANIFEST_FILENAME
    manifest = (
        json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest_path.exists()
        else {}
    )
    manifest.update(validation)
    atomic_write_json(manifest_path, manifest)
    return {
        **validation,
        'removed_stale_receipts': len(removed),
        'receipt_output_directory': str(output_dir),
        'managed_marker': str(output_dir / MANAGED_MARKER_FILENAME),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Render receipts for a validated SmartWealth dataset.'
    )
    parser.add_argument('--dataset-dir', type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=DEFAULT_DATASET_DIR / 'receipts',
    )
    parser.add_argument(
        '--initialize-output',
        action='store_true',
        help='Adopt an existing receipt directory only if every entry is a generated PDF.',
    )
    args = parser.parse_args()
    result = render_receipts(
        dataset_dir=args.dataset_dir,
        output_dir=args.output_dir,
        initialize_output=args.initialize_output,
    )
    actual_receipt_count = result['actual_receipt_count']
    removed_stale_receipts = result['removed_stale_receipts']
    receipt_ids_hash = result['receipt_ids_sha256']
    print(
        f'Rendered {actual_receipt_count} receipts; '
        f'removed {removed_stale_receipts} previous PDFs.'
    )
    print(f'Receipt ID SHA-256: {receipt_ids_hash}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
