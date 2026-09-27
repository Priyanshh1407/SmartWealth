import json
from pathlib import Path

from data.generation.dataset_contract import (
    PROJECT_ROOT,
    atomic_write_bytes,
    atomic_write_json,
    sha256_file,
)
from eval.evaluation import aggregate_prediction_runs, build_run_metadata
from eval.metrics import format_metrics_report


FIXTURE = PROJECT_ROOT / 'eval' / 'fixtures' / 'mock_predictions.json'
REPORT_JSON = PROJECT_ROOT / 'eval' / 'mock_baseline.json'
REPORT_MARKDOWN = PROJECT_ROOT / 'eval' / 'mock_baseline.md'
DASHBOARD_JSON = PROJECT_ROOT / 'eval' / 'evaluation_dashboard.json'


def dashboard_payload(metrics: dict, metadata: dict) -> dict:
    return {
        'schema_version': 'evaluation-dashboard-v1',
        'generated_at': metadata['timestamp_utc'],
        'before': {
            'label': 'Historical pre-remediation baseline',
            'source': 'Historical repository evaluation record',
            'scope': 'Legacy live evaluation; raw predictions unavailable.',
            'categorization_accuracy': 0.1962,
            'treatment_accuracy': 0.3038,
            'categorization_macro_f1': None,
            'treatment_macro_f1': None,
            'coverage': None,
            'retrieval_faithfulness': None,
            'latency_seconds': None,
            'estimated_cost_usd': None,
        },
        'after': {
            'label': 'Controlled provider-free fixture',
            'source': 'eval/fixtures/mock_predictions.json',
            'scope': (
                'Deterministic harness validation only; this is not a live-model '
                'or tax-law accuracy claim.'
            ),
            'categorization_accuracy': metrics['categorization']['accuracy'],
            'treatment_accuracy': metrics['treatment']['accuracy'],
            'categorization_macro_f1': metrics['categorization']['macro_f1'],
            'treatment_macro_f1': metrics['treatment']['macro_f1'],
            'coverage': metrics['categorization_selective']['coverage'],
            'retrieval_faithfulness': metrics['retrieval_faithfulness'],
            'latency_seconds': metadata['latency_seconds'],
            'estimated_cost_usd': 0.0,
            'confusion_matrix': metrics['categorization']['confusion_matrix'],
        },
    }


def main() -> int:
    records = json.loads(FIXTURE.read_text(encoding='utf-8'))
    metrics, variance = aggregate_prediction_runs([records, records])
    metadata = build_run_metadata(
        dataset_version='mock-baseline-v1',
        dataset_sha256=sha256_file(FIXTURE),
        seed=0,
        corpus_version='mock-corpus-v1',
        prompt_versions={
            'categorization': 'mock-categorization-v1',
            'tax_treatment': 'mock-treatment-v1',
        },
        model_ids={'provider': 'mock-provider-v1'},
        repeated_runs=2,
        latency_seconds=0.0,
    )
    metadata['timestamp_utc'] = '2026-09-25T00:00:00+00:00'
    payload = {
        'metadata': metadata,
        'metrics': metrics,
        'variance': variance,
        'prediction_runs': [records, records],
    }
    atomic_write_json(REPORT_JSON, payload)
    atomic_write_json(DASHBOARD_JSON, dashboard_payload(metrics, metadata))
    markdown = format_metrics_report(
        categorization=metrics['categorization'],
        treatment=metrics['treatment'],
        categorization_selective=metrics['categorization_selective'],
        treatment_selective=metrics['treatment_selective'],
        metadata=metadata,
        variance=variance,
    )
    atomic_write_bytes(REPORT_MARKDOWN, markdown.encode('utf-8'))
    print(f'Frozen mocked baseline written to {REPORT_JSON}')
    print(f'Evaluation dashboard written to {DASHBOARD_JSON}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
