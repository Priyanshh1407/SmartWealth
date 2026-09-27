import csv
import json
from datetime import date
from pathlib import Path

import pytest
import yaml

from data.generation.dataset_contract import (
    GROUND_TRUTH_FILENAME,
    MANAGED_MARKER_FILENAME,
    MANIFEST_FILENAME,
    PUBLIC_COLUMNS,
    TRANSACTIONS_FILENAME,
    DatasetContractError,
    ensure_managed_directory,
    load_ground_truth,
    validate_dataset_artifacts,
)
from data.generation.generate_receipts import render_receipts
from data.generation.generate_transactions import generate_dataset
from eval.evaluation import (
    aggregate_prediction_runs,
    aggregate_token_usage,
    build_run_metadata,
    evaluate_predictions,
)
from eval.metrics import calculate_metrics, calculate_selective_metrics


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MOCK_PREDICTIONS = PROJECT_ROOT / 'eval' / 'fixtures' / 'mock_predictions.json'


def _write_config(path: Path, *, seed: int = 42, count: int = 40) -> Path:
    payload = {
        'generation': {
            'dataset_version': 'phase2-test-v1',
            'seed': seed,
            'num_transactions': count,
            'start_date': '2025-01-01',
            'receipt_gap_percentage': 20,
        }
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding='utf-8')
    return path


def _generate(tmp_path: Path, name: str = 'dataset') -> tuple[Path, Path, dict]:
    allowed_root = tmp_path / 'generated'
    output_dir = allowed_root / name
    public_dir = tmp_path / f'{name}-public'
    config_path = _write_config(tmp_path / f'{name}.yaml')
    manifest = generate_dataset(
        config_path=config_path,
        output_dir=output_dir,
        public_dir=public_dir,
        allowed_root=allowed_root,
    )
    return output_dir, public_dir, manifest


def test_generation_is_byte_deterministic_and_public_copy_matches(tmp_path):
    first_dir, first_public, first = _generate(tmp_path, 'first')
    second_dir, second_public, second = _generate(tmp_path, 'second')

    assert first['transactions_sha256'] == second['transactions_sha256']
    assert first['ground_truth_sha256'] == second['ground_truth_sha256']
    assert (
        first_dir / TRANSACTIONS_FILENAME
    ).read_bytes() == (
        second_dir / TRANSACTIONS_FILENAME
    ).read_bytes()
    assert (
        first_public / TRANSACTIONS_FILENAME
    ).read_bytes() == (
        first_dir / TRANSACTIONS_FILENAME
    ).read_bytes()
    assert (
        second_public / TRANSACTIONS_FILENAME
    ).read_bytes() == (
        second_dir / TRANSACTIONS_FILENAME
    ).read_bytes()


def test_public_csv_has_iso_dates_and_no_answer_key_columns(tmp_path):
    dataset_dir, _, _ = _generate(tmp_path)
    with (dataset_dir / TRANSACTIONS_FILENAME).open(
        encoding='utf-8',
        newline='',
    ) as handle:
        reader = csv.DictReader(handle)
        assert tuple(reader.fieldnames or ()) == PUBLIC_COLUMNS
        assert 'category' not in reader.fieldnames
        rows = list(reader)

    assert rows
    assert all(date.fromisoformat(row['date']).isoformat() == row['date'] for row in rows)


def test_ground_truth_matches_json_schema_and_uses_string_treatments(tmp_path):
    dataset_dir, _, _ = _generate(tmp_path)
    payload = load_ground_truth(dataset_dir / GROUND_TRUTH_FILENAME)

    assert payload['dataset_version'] == 'phase2-test-v1'
    assert all(
        isinstance(row['expected_treatment'], str)
        for row in payload['transactions']
    )
    assert {row['transaction_id'] for row in payload['transactions']}


def test_managed_directory_rejects_broad_or_unmarked_targets(tmp_path):
    root = tmp_path / 'generated'
    root.mkdir()
    with pytest.raises(DatasetContractError):
        ensure_managed_directory(root, allowed_root=root)

    unmanaged = root / 'unmanaged'
    unmanaged.mkdir()
    (unmanaged / 'personal.txt').write_text('do not delete', encoding='utf-8')
    with pytest.raises(DatasetContractError):
        ensure_managed_directory(unmanaged, allowed_root=root)


def test_receipt_generation_removes_stale_pdfs_and_enforces_id_parity(tmp_path):
    dataset_dir, _, manifest = _generate(tmp_path)
    receipts_dir = dataset_dir / 'receipts'

    def fake_renderer(html: str, path: Path) -> None:
        path.write_bytes(b'%PDF-1.4\n' + html.encode('utf-8'))

    first = render_receipts(
        dataset_dir=dataset_dir,
        output_dir=receipts_dir,
        renderer=fake_renderer,
    )
    assert first['actual_receipt_count'] == manifest['receipt_count']
    assert (receipts_dir / MANAGED_MARKER_FILENAME).is_file()

    stale = receipts_dir / 'TXN-999999.pdf'
    stale.write_bytes(b'stale')
    second = render_receipts(
        dataset_dir=dataset_dir,
        output_dir=receipts_dir,
        renderer=fake_renderer,
    )
    assert second['removed_stale_receipts'] == manifest['receipt_count'] + 1
    assert not stale.exists()
    validated = validate_dataset_artifacts(
        dataset_dir,
        receipts_dir=receipts_dir,
    )
    assert validated['actual_receipt_count'] == validated['receipt_count']
    stored_manifest = json.loads(
        (dataset_dir / MANIFEST_FILENAME).read_text(encoding='utf-8')
    )
    assert stored_manifest['receipt_ids_sha256'] == validated['receipt_ids_sha256']


def test_macro_f1_is_average_of_per_class_f1_and_confusion_is_correct():
    metrics = calculate_metrics(
        ['A', 'A', 'B', 'B'],
        ['A', 'B', 'B', 'B'],
    )

    assert metrics['per_class']['A']['f1'] == pytest.approx(2 / 3)
    assert metrics['per_class']['B']['f1'] == pytest.approx(0.8)
    assert metrics['macro_f1'] == pytest.approx(((2 / 3) + 0.8) / 2)
    assert metrics['confusion_matrix'] == {
        'labels': ['A', 'B'],
        'matrix': [[1, 1], [0, 2]],
    }


@pytest.mark.parametrize(
    ('truth', 'predictions'),
    [
        ([], []),
        (['A'], []),
        (['A'], ['A', 'B']),
    ],
)
def test_metrics_reject_empty_or_unequal_inputs(truth, predictions):
    with pytest.raises(ValueError):
        calculate_metrics(truth, predictions)


def test_selective_accuracy_is_separate_from_coverage():
    selective = calculate_selective_metrics(
        ['A', 'B', 'C', 'D'],
        ['A', 'Unknown', 'C', 'Unknown'],
        abstain_label='Unknown',
    )

    assert selective['coverage'] == pytest.approx(0.5)
    assert selective['abstention_rate'] == pytest.approx(0.5)
    assert selective['selective_accuracy'] == pytest.approx(1.0)


def test_frozen_mock_baseline_and_repeated_run_variance():
    records = json.loads(MOCK_PREDICTIONS.read_text(encoding='utf-8'))
    result = evaluate_predictions(records)
    combined, variance = aggregate_prediction_runs([records, records])

    assert result['categorization']['accuracy'] == pytest.approx(4 / 6)
    assert result['treatment']['accuracy'] == pytest.approx(5 / 6)
    assert result['categorization_selective']['coverage'] == pytest.approx(4 / 6)
    assert result['categorization_selective']['selective_accuracy'] == pytest.approx(0.75)
    assert result['treatment_selective']['coverage'] == pytest.approx(4 / 6)
    assert result['treatment_selective']['selective_accuracy'] == pytest.approx(1.0)
    assert combined['categorization']['sample_count'] == 12
    assert all(value == 0.0 for value in variance.values())


def test_evaluation_metadata_records_reproducibility_fields():
    token_usage = aggregate_token_usage([
        {
            'model-v1': {
                'input_tokens': 10,
                'output_tokens': 4,
                'total_tokens': 14,
            }
        },
        {
            'model-v1': {
                'input_tokens': 8,
                'output_tokens': 2,
                'total_tokens': 10,
            }
        },
    ])
    metadata = build_run_metadata(
        dataset_version='phase2-test-v1',
        dataset_sha256='abc123',
        seed=42,
        corpus_version='corpus-v1',
        prompt_versions={'categorization': 'prompt-v1'},
        model_ids={'classifier': 'model-v1'},
        repeated_runs=2,
        latency_seconds=1.25,
        token_usage=token_usage,
    )

    assert metadata['dataset_sha256'] == 'abc123'
    assert metadata['seed'] == 42
    assert metadata['repeated_runs'] == 2
    assert metadata['token_usage']['status'] == 'captured'
    assert metadata['token_usage']['total_tokens'] == 24
    assert (
        metadata['token_usage']['totals_by_model']['model-v1']['input_tokens']
        == 18
    )
    assert metadata['estimated_cost']['status'] == 'not_calculated'
    assert metadata['estimated_cost']['amount'] is None
    assert metadata['timestamp_utc'].endswith('+00:00')
