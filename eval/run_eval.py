import argparse
import json
import time
import uuid
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from langgraph.types import Command
from langchain_core.callbacks import UsageMetadataCallbackHandler

from backend.app.config import get_settings
from backend.app.graph.builder import graph
from backend.app.graph.nodes.corrective_rag import TAX_TREATMENT_PROMPT_VERSION
from backend.app.graph.state import TaxTreatment, Transaction
from backend.app.tools.categorizer_tools import CATEGORIZER_PROMPT_VERSION
from data.generation.dataset_contract import (
    DEFAULT_DATASET_DIR,
    GROUND_TRUTH_FILENAME,
    PROJECT_ROOT,
    TRANSACTIONS_FILENAME,
    atomic_write_bytes,
    atomic_write_json,
    load_ground_truth,
    load_transactions,
    validate_dataset_artifacts,
)
from eval.evaluation import (
    aggregate_prediction_runs,
    aggregate_token_usage,
    build_run_metadata,
)
from eval.metrics import format_metrics_report


def load_evaluation_dataset(
    dataset_dir: Path,
    num_samples: int | None,
) -> tuple[list[Transaction], dict[str, dict[str, Any]]]:
    rows = load_transactions(dataset_dir / TRANSACTIONS_FILENAME)
    if num_samples is not None:
        if num_samples <= 0:
            raise ValueError('num_samples must be positive.')
        rows = rows[:num_samples]
    truth_payload = load_ground_truth(dataset_dir / GROUND_TRUTH_FILENAME)
    truth_by_id = {
        row['transaction_id']: row for row in truth_payload['transactions']
    }
    transactions = [
        Transaction(
            transaction_id=row['transaction_id'],
            date=row['date'],
            merchant=row['merchant'],
            amount=float(row['amount']),
            category='',
            description=row['description'],
        )
        for row in rows
    ]
    missing = {
        transaction.transaction_id
        for transaction in transactions
        if transaction.transaction_id not in truth_by_id
    }
    if missing:
        raise ValueError(f'Missing ground truth for transaction IDs: {sorted(missing)}')
    return transactions, truth_by_id


def run_graph_once(
    transactions: list[Transaction],
    truth_by_id: dict[str, dict[str, Any]],
    callbacks: list[Any] | None = None,
) -> list[dict[str, str]]:
    thread_id = f'eval-{uuid.uuid4().hex}'
    config = {
        'configurable': {'thread_id': thread_id},
        'callbacks': callbacks or [],
    }
    initial_state = {
        'thread_id': thread_id,
        'transactions': transactions,
        'categorized': [],
        'deductibility_results': [],
        'pending_clarifications': [],
        'resolved_clarifications': {},
        'unresolved_flags': [],
        'final_report': None,
        'current_node': 'start',
        'errors': [],
    }
    events = graph.stream(initial_state, config, stream_mode='values')
    while True:
        for _ in events:
            pass
        snapshot = graph.get_state(config)
        if not snapshot.next:
            break
        if 'auditor_loop' not in snapshot.next:
            raise RuntimeError(f'Graph paused at unexpected node: {snapshot.next}')
        pending = []
        if snapshot.tasks and snapshot.tasks[0].interrupts:
            pending = snapshot.tasks[0].interrupts[0].value
        answers = [
            {
                'transaction_id': (
                    task.get('transaction_id')
                    if isinstance(task, dict)
                    else task.transaction_id
                ),
                'answer': 'idk',
            }
            for task in pending
        ]
        if not answers:
            raise RuntimeError('Graph interrupted without clarification payload.')
        events = graph.stream(
            Command(resume=answers),
            config,
            stream_mode='values',
        )

    values = graph.get_state(config).values
    categorized = {
        item.transaction_id: item.predicted_category
        for item in values.get('categorized', [])
    }
    treatments = {
        item.transaction_id: (
            item.treatment.value
            if isinstance(item.treatment, TaxTreatment)
            else str(item.treatment)
        )
        for item in values.get('deductibility_results', [])
    }
    records = []
    for transaction in transactions:
        truth = truth_by_id[transaction.transaction_id]
        records.append({
            'transaction_id': transaction.transaction_id,
            'true_category': truth['true_category'],
            'predicted_category': categorized.get(
                transaction.transaction_id,
                'Unknown',
            ),
            'true_treatment': truth['expected_treatment'],
            'predicted_treatment': treatments.get(
                transaction.transaction_id,
                TaxTreatment.UNDETERMINED.value,
            ),
        })
    return records


def run_evaluation(
    *,
    dataset_dir: Path,
    report_dir: Path,
    num_samples: int | None,
    repeats: int,
    verbose_graph: bool = False,
) -> dict[str, Any]:
    if repeats <= 0:
        raise ValueError('repeats must be positive.')
    validation = validate_dataset_artifacts(dataset_dir)
    transactions, truth_by_id = load_evaluation_dataset(
        dataset_dir,
        num_samples,
    )
    started = time.perf_counter()
    prediction_runs = []
    usage_by_run = []

    def collect_runs() -> None:
        for _ in range(repeats):
            usage_handler = UsageMetadataCallbackHandler()
            prediction_runs.append(
                run_graph_once(
                    transactions,
                    truth_by_id,
                    callbacks=[usage_handler],
                )
            )
            usage_by_run.append(dict(usage_handler.usage_metadata))

    if verbose_graph:
        collect_runs()
    else:
        with redirect_stdout(StringIO()):
            collect_runs()
    latency_seconds = time.perf_counter() - started
    metrics, variance = aggregate_prediction_runs(prediction_runs)

    settings = get_settings()
    metadata = build_run_metadata(
        dataset_version=validation['dataset_version'],
        dataset_sha256=validation['transactions_sha256'],
        seed=validation['seed'],
        corpus_version=settings.tax_corpus_version,
        prompt_versions={
            'categorization': CATEGORIZER_PROMPT_VERSION,
            'tax_treatment': TAX_TREATMENT_PROMPT_VERSION,
        },
        model_ids={
            'gemini': settings.gemini_model,
            'groq': settings.groq_model,
            'embedding': settings.embedding_model,
        },
        repeated_runs=repeats,
        latency_seconds=latency_seconds,
        token_usage=aggregate_token_usage(usage_by_run),
    )
    metadata['evaluated_sample_count_per_run'] = len(transactions)

    payload = {
        'metadata': metadata,
        'metrics': metrics,
        'variance': variance,
        'prediction_runs': prediction_runs,
    }
    report_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(report_dir / 'eval_report.json', payload)
    markdown = format_metrics_report(
        categorization=metrics['categorization'],
        treatment=metrics['treatment'],
        categorization_selective=metrics['categorization_selective'],
        treatment_selective=metrics['treatment_selective'],
        metadata=metadata,
        variance=variance,
    )
    atomic_write_bytes(
        report_dir / 'eval_report.md',
        markdown.encode('utf-8'),
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Run a reproducible SmartWealth evaluation.'
    )
    parser.add_argument('--dataset-dir', type=Path, default=DEFAULT_DATASET_DIR)
    parser.add_argument(
        '--report-dir',
        type=Path,
        default=PROJECT_ROOT / 'eval',
    )
    parser.add_argument('--num-samples', type=int)
    parser.add_argument('--repeats', type=int, default=1)
    parser.add_argument(
        '--verbose-graph',
        action='store_true',
        help='Show internal graph-node logs during evaluation.',
    )
    args = parser.parse_args()
    payload = run_evaluation(
        dataset_dir=args.dataset_dir,
        report_dir=args.report_dir,
        num_samples=args.num_samples,
        repeats=args.repeats,
        verbose_graph=args.verbose_graph,
    )
    metadata = payload['metadata']
    metrics = payload['metrics']
    dataset_version = metadata['dataset_version']
    sample_count = metadata['evaluated_sample_count_per_run']
    categorization_accuracy = metrics['categorization']['accuracy']
    treatment_accuracy = metrics['treatment']['accuracy']
    print(f'Evaluated dataset {dataset_version} with {sample_count} samples per run.')
    print(f'Categorization accuracy: {categorization_accuracy:.2%}')
    print(f'Tax-treatment accuracy: {treatment_accuracy:.2%}')
    print(f"Reports written to {args.report_dir.resolve()}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
