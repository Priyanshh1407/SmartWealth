from statistics import pvariance
from typing import Any, Iterable, Sequence


def _validate_labels(y_true: Sequence[str], y_pred: Sequence[str]) -> None:
    if not y_true or not y_pred:
        raise ValueError('y_true and y_pred must both be nonempty.')
    if len(y_true) != len(y_pred):
        raise ValueError(
            f'y_true and y_pred lengths differ: {len(y_true)} != {len(y_pred)}'
        )


def calculate_metrics(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    *,
    labels: Iterable[str] | None = None,
) -> dict[str, Any]:
    '''Return per-class metrics, conventional macro averages, and a confusion matrix.'''
    _validate_labels(y_true, y_pred)
    class_labels = (
        list(dict.fromkeys(labels))
        if labels is not None
        else sorted(set(y_true) | set(y_pred))
    )
    if not class_labels:
        raise ValueError('At least one class label is required.')
    unknown = (set(y_true) | set(y_pred)) - set(class_labels)
    if unknown:
        raise ValueError(f'Observed labels are missing from labels: {sorted(unknown)}')

    per_class = {}
    for label in class_labels:
        true_positive = sum(
            actual == label and predicted == label
            for actual, predicted in zip(y_true, y_pred)
        )
        false_positive = sum(
            actual != label and predicted == label
            for actual, predicted in zip(y_true, y_pred)
        )
        false_negative = sum(
            actual == label and predicted != label
            for actual, predicted in zip(y_true, y_pred)
        )
        support = sum(actual == label for actual in y_true)
        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0.0
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else 0.0
        )
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        per_class[label] = {
            'precision': precision,
            'recall': recall,
            'f1': f1,
            'support': support,
            'true_positive': true_positive,
            'false_positive': false_positive,
            'false_negative': false_negative,
        }

    confusion_matrix = [
        [
            sum(
                actual == actual_label and predicted == predicted_label
                for actual, predicted in zip(y_true, y_pred)
            )
            for predicted_label in class_labels
        ]
        for actual_label in class_labels
    ]
    count = len(class_labels)
    return {
        'sample_count': len(y_true),
        'accuracy': sum(
            actual == predicted for actual, predicted in zip(y_true, y_pred)
        ) / len(y_true),
        'macro_precision': sum(
            values['precision'] for values in per_class.values()
        ) / count,
        'macro_recall': sum(
            values['recall'] for values in per_class.values()
        ) / count,
        'macro_f1': sum(values['f1'] for values in per_class.values()) / count,
        'per_class': per_class,
        'confusion_matrix': {
            'labels': class_labels,
            'matrix': confusion_matrix,
        },
    }


def calculate_selective_metrics(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    *,
    abstain_label: str,
) -> dict[str, float | int]:
    '''Measure accuracy only where the system answered, separate from abstention.'''
    _validate_labels(y_true, y_pred)
    answered = [
        (actual, predicted)
        for actual, predicted in zip(y_true, y_pred)
        if predicted != abstain_label
    ]
    answered_count = len(answered)
    sample_count = len(y_true)
    selective_accuracy = (
        sum(actual == predicted for actual, predicted in answered) / answered_count
        if answered_count
        else 0.0
    )
    return {
        'sample_count': sample_count,
        'answered_count': answered_count,
        'abstained_count': sample_count - answered_count,
        'coverage': answered_count / sample_count,
        'abstention_rate': (sample_count - answered_count) / sample_count,
        'selective_accuracy': selective_accuracy,
    }


def calculate_retrieval_faithfulness(
    records: Sequence[dict[str, Any]],
) -> dict[str, float | int]:
    evaluated = [
        record
        for record in records
        if record.get('retrieval_required', False)
    ]
    supported = sum(
        bool(record.get('retrieval_supported', False))
        for record in evaluated
    )
    return {
        'evaluated_claims': len(evaluated),
        'supported_claims': supported,
        'faithfulness': supported / len(evaluated) if evaluated else 0.0,
    }


def metric_variance(
    runs: Sequence[dict[str, Any]],
    metric_name: str,
) -> float:
    if not runs:
        raise ValueError('At least one metric run is required.')
    values = [float(run[metric_name]) for run in runs]
    return pvariance(values) if len(values) > 1 else 0.0


def _format_metric_section(title: str, metrics: dict[str, Any]) -> list[str]:
    lines = [
        f'## {title}',
        '',
        f"- Accuracy: {metrics['accuracy']:.2%}",
        f"- Macro precision: {metrics['macro_precision']:.2%}",
        f"- Macro recall: {metrics['macro_recall']:.2%}",
        f"- Macro F1: {metrics['macro_f1']:.2%}",
        '',
        '| Class | Precision | Recall | F1 | Support |',
        '|---|---:|---:|---:|---:|',
    ]
    for label, values in metrics['per_class'].items():
        lines.append(
            f"| {label} | {values['precision']:.2%} | {values['recall']:.2%} "
            f"| {values['f1']:.2%} | {values['support']} |"
        )
    matrix = metrics['confusion_matrix']
    labels = matrix['labels']
    lines.extend([
        '',
        'Confusion matrix; rows are actual and columns are predicted:',
        '',
        '| Actual \\ Predicted | ' + ' | '.join(labels) + ' |',
        '|---|' + '|'.join('---:' for _ in labels) + '|',
    ])
    for label, row in zip(labels, matrix['matrix']):
        lines.append(f'| {label} | ' + ' | '.join(str(value) for value in row) + ' |')
    lines.append('')
    return lines


def format_metrics_report(
    *,
    categorization: dict[str, Any],
    treatment: dict[str, Any],
    categorization_selective: dict[str, Any],
    treatment_selective: dict[str, Any],
    metadata: dict[str, Any],
    variance: dict[str, float],
) -> str:
    lines = [
        '# Evaluation Report',
        '',
        '## Run Metadata',
        '',
        f"- Dataset version: {metadata['dataset_version']}",
        f"- Dataset SHA-256: {metadata['dataset_sha256']}",
        f"- Seed: {metadata['seed']}",
        f"- Corpus version: {metadata['corpus_version']}",
        f"- Prompt versions: {metadata['prompt_versions']}",
        f"- Model IDs: {metadata['model_ids']}",
        f"- Timestamp UTC: {metadata['timestamp_utc']}",
        f"- Repeated runs: {metadata['repeated_runs']}",
        f"- Total latency seconds: {metadata['latency_seconds']:.4f}",
        f"- Token usage: {metadata['token_usage']}",
        f"- Estimated provider cost: {metadata['estimated_cost']}",
        '',
    ]
    lines.extend(_format_metric_section('Categorization Metrics', categorization))
    lines.extend(_format_metric_section('Tax-Treatment Metrics', treatment))
    lines.extend([
        '## Selective Metrics',
        '',
        '| Task | Coverage | Abstention Rate | Selective Accuracy |',
        '|---|---:|---:|---:|',
        (
            f"| Categorization | {categorization_selective['coverage']:.2%} "
            f"| {categorization_selective['abstention_rate']:.2%} "
            f"| {categorization_selective['selective_accuracy']:.2%} |"
        ),
        (
            f"| Tax treatment | {treatment_selective['coverage']:.2%} "
            f"| {treatment_selective['abstention_rate']:.2%} "
            f"| {treatment_selective['selective_accuracy']:.2%} |"
        ),
        '',
        '## Repeated-Run Variance',
        '',
    ])
    for name, value in sorted(variance.items()):
        lines.append(f'- {name}: {value:.8f}')
    lines.extend([
        '',
        'Token and cost fields remain unavailable until provider callbacks are instrumented.',
        '',
    ])
    return '\n'.join(lines)
