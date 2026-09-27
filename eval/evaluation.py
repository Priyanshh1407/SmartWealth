from datetime import datetime, timezone
from typing import Any, Sequence

from eval.metrics import (
    calculate_metrics,
    calculate_retrieval_faithfulness,
    calculate_selective_metrics,
    metric_variance,
)


def _merge_numeric_tree(
    target: dict[str, Any],
    source: dict[str, Any],
) -> None:
    for key, value in source.items():
        if isinstance(value, dict):
            branch = target.setdefault(key, {})
            if isinstance(branch, dict):
                _merge_numeric_tree(branch, value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            target[key] = target.get(key, 0) + value


def aggregate_token_usage(
    usage_by_run: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    totals_by_model: dict[str, Any] = {}
    for run_usage in usage_by_run:
        _merge_numeric_tree(totals_by_model, run_usage)
    total_tokens = sum(
        model_usage.get('total_tokens', 0)
        for model_usage in totals_by_model.values()
        if isinstance(model_usage, dict)
    )
    return {
        'status': 'captured' if totals_by_model else 'unavailable',
        'per_run': list(usage_by_run),
        'totals_by_model': totals_by_model,
        'total_tokens': total_tokens,
    }


def evaluate_predictions(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        raise ValueError('At least one prediction record is required.')
    true_categories = [record['true_category'] for record in records]
    predicted_categories = [record['predicted_category'] for record in records]
    true_treatments = [record['true_treatment'] for record in records]
    predicted_treatments = [record['predicted_treatment'] for record in records]
    return {
        'categorization': calculate_metrics(
            true_categories,
            predicted_categories,
        ),
        'treatment': calculate_metrics(
            true_treatments,
            predicted_treatments,
        ),
        'categorization_selective': calculate_selective_metrics(
            true_categories,
            predicted_categories,
            abstain_label='Unknown',
        ),
        'treatment_selective': calculate_selective_metrics(
            true_treatments,
            predicted_treatments,
            abstain_label='undetermined',
        ),
        'retrieval_faithfulness': calculate_retrieval_faithfulness(records),
    }


def aggregate_prediction_runs(
    runs: Sequence[Sequence[dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, float]]:
    if not runs or any(not run for run in runs):
        raise ValueError('Every evaluation run must contain predictions.')
    per_run = [evaluate_predictions(run) for run in runs]
    combined_records = [record for run in runs for record in run]
    combined = evaluate_predictions(combined_records)
    variance = {
        'categorization_accuracy': metric_variance(
            [result['categorization'] for result in per_run],
            'accuracy',
        ),
        'categorization_macro_f1': metric_variance(
            [result['categorization'] for result in per_run],
            'macro_f1',
        ),
        'treatment_accuracy': metric_variance(
            [result['treatment'] for result in per_run],
            'accuracy',
        ),
        'treatment_macro_f1': metric_variance(
            [result['treatment'] for result in per_run],
            'macro_f1',
        ),
        'categorization_selective_accuracy': metric_variance(
            [result['categorization_selective'] for result in per_run],
            'selective_accuracy',
        ),
        'treatment_selective_accuracy': metric_variance(
            [result['treatment_selective'] for result in per_run],
            'selective_accuracy',
        ),
    }
    return combined, variance


def build_run_metadata(
    *,
    dataset_version: str,
    dataset_sha256: str,
    seed: int,
    corpus_version: str,
    prompt_versions: dict[str, str],
    model_ids: dict[str, str],
    repeated_runs: int,
    latency_seconds: float,
    token_usage: dict[str, Any] | None = None,
    estimated_cost: dict[str, Any] | None = None,
) -> dict[str, Any]:
    usage = token_usage or aggregate_token_usage([])
    cost = estimated_cost or {
        'status': 'not_calculated',
        'amount': None,
        'currency': 'USD',
        'reason': 'No versioned provider pricing table is configured.',
    }
    return {
        'dataset_version': dataset_version,
        'dataset_sha256': dataset_sha256,
        'seed': seed,
        'corpus_version': corpus_version,
        'prompt_versions': prompt_versions,
        'model_ids': model_ids,
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'repeated_runs': repeated_runs,
        'latency_seconds': latency_seconds,
        'token_usage': usage,
        'estimated_cost': cost,
        'instrumentation_note': (
            'Token metadata is captured when providers expose it. Cost is only '
            'calculated when a versioned pricing table is configured.'
        ),
    }
