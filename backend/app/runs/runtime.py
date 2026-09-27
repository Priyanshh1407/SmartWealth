from backend.app.config import get_settings
from backend.app.graph.builder import graph
from backend.app.runs.service import RunService
from backend.app.runs.store import run_store


settings = get_settings()
run_service = RunService(
    store=run_store,
    graph=graph,
    max_workers=settings.run_worker_count,
    queue_capacity=settings.run_queue_capacity,
    retention_hours=settings.run_retention_hours,
    max_active_runs_per_owner=settings.max_active_runs_per_owner,
)
