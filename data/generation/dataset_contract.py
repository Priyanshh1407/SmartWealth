import csv
import hashlib
import io
import json
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_DIR = PROJECT_ROOT / 'data' / 'synthetic'
DEFAULT_PUBLIC_DIR = PROJECT_ROOT / 'frontend' / 'public'
GROUND_TRUTH_SCHEMA_PATH = PROJECT_ROOT / 'data' / 'generation' / 'ground_truth_schema.json'

TRANSACTIONS_FILENAME = 'transactions_2025.csv'
GROUND_TRUTH_FILENAME = 'ground_truth.json'
MANIFEST_FILENAME = 'dataset_manifest.json'
MANAGED_MARKER_FILENAME = '.smartwealth-generated.json'
MANAGED_BY = 'smartwealth-data-generator'

PUBLIC_COLUMNS = (
    'transaction_id',
    'date',
    'merchant',
    'amount',
    'description',
)
FORBIDDEN_EVALUATION_COLUMNS = {
    'category',
    'true_category',
    'expected_treatment',
    'expected_deductibility',
    'has_receipt',
    'section',
}
TREATMENTS = {
    'deductible',
    'non_deductible',
    'depreciable',
    'partially_deductible',
    'undetermined',
}


class DatasetContractError(ValueError):
    pass


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(content)
    temporary.replace(path)


def atomic_write_json(path: Path, payload: Any) -> bytes:
    content = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + '\n'
    ).encode('utf-8')
    atomic_write_bytes(path, content)
    return content


def csv_bytes(rows: Iterable[dict[str, Any]]) -> bytes:
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(
        buffer,
        fieldnames=PUBLIC_COLUMNS,
        lineterminator='\n',
        extrasaction='ignore',
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode('utf-8')


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def ensure_managed_directory(
    directory: Path,
    *,
    allowed_root: Path,
    initialize: bool = False,
    allowed_existing_names: set[str] | None = None,
) -> Path:
    target = directory.resolve()
    root = allowed_root.resolve()
    if target == root or not _is_relative_to(target, root):
        raise DatasetContractError(
            f'Generated directory must be a child of {root}, got {target}.'
        )
    target.mkdir(parents=True, exist_ok=True)
    marker = target / MANAGED_MARKER_FILENAME
    if marker.exists():
        try:
            marker_data = json.loads(marker.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise DatasetContractError(f'Invalid generated-directory marker: {marker}') from exc
        if marker_data.get('managed_by') != MANAGED_BY:
            raise DatasetContractError(f'Unrecognized generated-directory marker: {marker}')
        return target

    existing_names = {item.name for item in target.iterdir()}
    if existing_names and not initialize:
        raise DatasetContractError(
            f'Refusing to adopt non-empty unmarked directory: {target}.'
        )
    if existing_names and allowed_existing_names is not None:
        unexpected = {
            name
            for name in existing_names
            if name not in allowed_existing_names
        }
        if unexpected:
            raise DatasetContractError(
                f'Refusing to adopt directory with unexpected entries: {sorted(unexpected)}'
            )
    atomic_write_json(marker, {'managed_by': MANAGED_BY, 'format_version': 1})
    return target


def clear_generated_files(directory: Path, pattern: str) -> list[Path]:
    marker = directory / MANAGED_MARKER_FILENAME
    if not marker.is_file():
        raise DatasetContractError(
            f'Refusing to clear an unmanaged directory: {directory.resolve()}'
        )
    removed = []
    for path in directory.glob(pattern):
        if path.is_file():
            path.unlink()
            removed.append(path)
    return removed


def load_ground_truth(path: Path, schema_path: Path = GROUND_TRUTH_SCHEMA_PATH) -> dict:
    payload = json.loads(path.read_text(encoding='utf-8'))
    schema = json.loads(schema_path.read_text(encoding='utf-8'))
    Draft202012Validator(schema).validate(payload)
    return payload


def load_transactions(path: Path) -> list[dict[str, str]]:
    with path.open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        fields = tuple(reader.fieldnames or ())
        if fields != PUBLIC_COLUMNS:
            raise DatasetContractError(
                f'CSV columns must be exactly {PUBLIC_COLUMNS}; got {fields}.'
            )
        leaked = set(fields) & FORBIDDEN_EVALUATION_COLUMNS
        if leaked:
            raise DatasetContractError(
                f'Evaluation CSV contains answer-key columns: {sorted(leaked)}'
            )
        rows = list(reader)
    if not rows:
        raise DatasetContractError('Dataset must contain at least one transaction.')
    return rows


def validate_dataset_artifacts(
    dataset_dir: Path,
    *,
    public_csv: Path | None = None,
    receipts_dir: Path | None = None,
) -> dict[str, Any]:
    dataset_dir = dataset_dir.resolve()
    csv_path = dataset_dir / TRANSACTIONS_FILENAME
    ground_truth_path = dataset_dir / GROUND_TRUTH_FILENAME
    rows = load_transactions(csv_path)
    ground_truth = load_ground_truth(ground_truth_path)
    truth_rows = ground_truth['transactions']

    transaction_ids = [row['transaction_id'] for row in rows]
    truth_ids = [row['transaction_id'] for row in truth_rows]
    if len(transaction_ids) != len(set(transaction_ids)):
        raise DatasetContractError('CSV transaction IDs must be unique.')
    if len(truth_ids) != len(set(truth_ids)):
        raise DatasetContractError('Ground-truth transaction IDs must be unique.')
    if set(transaction_ids) != set(truth_ids):
        raise DatasetContractError('CSV and ground-truth transaction IDs differ.')

    for row in rows:
        transaction_id = row.get('transaction_id')
        raw_date = row.get('date')
        try:
            parsed = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise DatasetContractError(
                f'Non-ISO date for {transaction_id}: {raw_date}'
            ) from exc
        if parsed.isoformat() != raw_date:
            raise DatasetContractError(
                f'Date must use canonical YYYY-MM-DD format: {raw_date}'
            )

    csv_hash = sha256_file(csv_path)
    if public_csv is not None and sha256_file(public_csv) != csv_hash:
        raise DatasetContractError('Generated and public CSV hashes differ.')

    expected_receipts = {
        row['transaction_id'] for row in truth_rows if row['has_receipt']
    }
    actual_receipts = None
    if receipts_dir is not None:
        actual_receipts = {path.stem for path in receipts_dir.glob('*.pdf')}
        if actual_receipts != expected_receipts:
            missing = sorted(expected_receipts - actual_receipts)
            stale = sorted(actual_receipts - expected_receipts)
            raise DatasetContractError(
                f'Receipt parity failed; missing={missing}, stale={stale}.'
            )

    return {
        'dataset_version': ground_truth['dataset_version'],
        'seed': ground_truth['seed'],
        'transaction_count': len(transaction_ids),
        'receipt_count': len(expected_receipts),
        'transaction_ids_sha256': sha256_bytes(
            '\n'.join(sorted(transaction_ids)).encode('utf-8')
        ),
        'transactions_sha256': csv_hash,
        'ground_truth_sha256': sha256_file(ground_truth_path),
        'receipt_ids_sha256': sha256_bytes(
            '\n'.join(sorted(expected_receipts)).encode('utf-8')
        ),
        'actual_receipt_count': (
            len(actual_receipts) if actual_receipts is not None else None
        ),
    }
