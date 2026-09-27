"""Operational endpoints for orchestration and monitoring."""
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from backend.app.config import PROJECT_ROOT
from backend.app.graph.nodes.corrective_rag import rag_resources_ready
from backend.app.graph.nodes.extraction import extraction_resources_ready
from backend.app.observability import metrics
from backend.app.runs.runtime import run_service


router = APIRouter(tags=['operations'])


@router.get('/health/live')
def liveness() -> dict[str, str]:
    return {'status': 'alive'}


@router.get('/health/ready')
def readiness(request: Request):
    checks = {
        'startup': bool(getattr(request.app.state, 'ready', False)),
        'run_store': False,
        'worker_queue': run_service.executor.accepting,
        'extraction_resources': extraction_resources_ready(),
        'rag_resources': rag_resources_ready(),
    }
    try:
        checks['run_store'] = run_service.store.ping()
    except Exception:
        checks['run_store'] = False
    ready = all(checks.values())
    queue = run_service.executor.snapshot()
    metrics.gauge('smartwealth_queue_running', int(queue['running']))
    metrics.gauge('smartwealth_queue_reserved', int(queue['reserved']))
    return JSONResponse(
        status_code=200 if ready else 503,
        content={'status': 'ready' if ready else 'not_ready', 'checks': checks},
    )


@router.get('/metrics', response_class=PlainTextResponse)
def prometheus_metrics() -> str:
    queue = run_service.executor.snapshot()
    metrics.gauge('smartwealth_queue_running', int(queue['running']))
    metrics.gauge('smartwealth_queue_reserved', int(queue['reserved']))
    metrics.gauge('smartwealth_queue_capacity', int(queue['queue_capacity']))
    return metrics.render_prometheus()


@router.get('/api/evaluation/summary')
def evaluation_summary() -> dict:
    artifact = PROJECT_ROOT / 'eval' / 'evaluation_dashboard.json'
    try:
        return json.loads(artifact.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(
            status_code=503,
            detail='Evaluation dashboard artifact is unavailable.',
        ) from error
