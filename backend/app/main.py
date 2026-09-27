import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

from backend.app.config import get_settings
from backend.app.observability import (
    ObservabilityMiddleware,
    configure_logging,
    metrics,
    trace_span,
)
from backend.app.security import BodySizeLimitMiddleware, RequestSecurityMiddleware

settings = get_settings()
configure_logging(settings.log_level)
provider_errors = settings.provider_errors()
if provider_errors:
    raise RuntimeError("Configuration error: " + " ".join(provider_errors))
if settings.environment == 'production':
    missing_production_storage = [
        name
        for name, value in (
            ('RUN_DATABASE_URL', settings.run_database_url),
            ('CHECKPOINT_DATABASE_URL', settings.checkpoint_database_url),
            ('VECTOR_DATABASE_URL', settings.vector_database_url),
        )
        if not value
    ]
    if settings.vector_backend != 'pgvector':
        missing_production_storage.append('VECTOR_BACKEND=pgvector')
    if missing_production_storage:
        raise RuntimeError(
            'Production requires managed PostgreSQL storage: '
            + ', '.join(missing_production_storage)
        )

# Import your new route files
from backend.app.api.routes_run import router as run_router
from backend.app.api.routes_clarify import router as clarify_router
from backend.app.api.routes_state import router as state_router
from backend.app.api.routes_ops import router as ops_router
from backend.app.graph.nodes.corrective_rag import initialize_rag_resources
from backend.app.graph.nodes.extraction import initialize_extraction_resources
from backend.app.runs.runtime import run_service
from backend.app.shutdown import shutdown_requested

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    shutdown_requested.clear()
    app.state.ready = False
    try:
        with trace_span('application_startup'):
            initialize_extraction_resources()
            initialize_rag_resources()
            app.state.run_recovery = run_service.recover()
            app.state.ready = True
            metrics.gauge('smartwealth_application_ready', 1)
            logger.info(
                'application_ready',
                extra={
                    'event': 'application_ready',
                    'recovery': app.state.run_recovery,
                },
            )
        yield
    finally:
        shutdown_requested.set()
        app.state.ready = False
        metrics.gauge('smartwealth_application_ready', 0)
        run_service.shutdown(wait=True)
        if settings.run_storage_mode == 'session':
            from backend.app.graph.builder import conn
            conn.close()
            for suffix in ('', '-shm', '-wal'):
                Path(f'{settings.checkpoint_path}{suffix}').unlink(missing_ok=True)


app = FastAPI(title="Smart Wealth API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=['GET', 'POST', 'DELETE', 'OPTIONS'],
    allow_headers=['Content-Type', 'Idempotency-Key', 'X-Request-ID'],
    expose_headers=['Idempotency-Replayed', 'X-Request-ID'],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=list(settings.trusted_hosts),
)
if settings.force_https:
    app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(
    BodySizeLimitMiddleware,
    max_bytes=settings.max_request_body_bytes,
)
app.add_middleware(ObservabilityMiddleware)
app.add_middleware(RequestSecurityMiddleware)

# Attach the routers to the app with the /api prefix
app.include_router(run_router, prefix="/api")
app.include_router(clarify_router, prefix="/api")
app.include_router(state_router, prefix="/api")
app.include_router(ops_router)


@app.exception_handler(Exception)
async def safe_internal_error(
    request: Request,
    error: Exception,
) -> JSONResponse:
    logger.error(
        'Unhandled API error on %s: %s (request_id=%s)',
        request.url.path,
        type(error).__name__,
        getattr(request.state, 'correlation_id', 'unassigned'),
    )
    return JSONResponse(
        status_code=500,
        content={'detail': 'Internal server error.'},
    )

@app.get("/")
def read_root():
    return {"message": "Smart Wealth API is running!"}

def run_server(*, host: str = "0.0.0.0", port: int = 8000) -> None:
    import uvicorn

    class ShutdownAwareServer(uvicorn.Server):
        def handle_exit(self, sig, frame):
            shutdown_requested.set()
            super().handle_exit(sig, frame)

    shutdown_requested.clear()
    server_config = uvicorn.Config(
        app,
        host=host,
        port=port,
        timeout_graceful_shutdown=5,
    )
    try:
        ShutdownAwareServer(server_config).run()
    except KeyboardInterrupt:
        # Ctrl+C is the expected local shutdown path. The shutdown-aware
        # handler has already released open event streams and run cleanup.
        pass


if __name__ == "__main__":
    run_server()
