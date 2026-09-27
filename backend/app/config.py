"""Centralized runtime configuration; entry points load environment files."""
from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value.")


def _int(name: str, default: int, low: int, high: int) -> int:
    value = int(os.environ.get(name, default))
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}.")
    return value


def _float(name: str, default: float, low: float, high: float) -> float:
    value = float(os.environ.get(name, default))
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}.")
    return value


def _path(name: str, default: Path) -> Path:
    value = Path(os.environ.get(name, str(default)))
    if not value.is_absolute():
        value = PROJECT_ROOT / value
    return value.resolve()


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in os.environ.get(name, default).split(',')
        if item.strip()
    )


def _choice(name: str, default: str, allowed: set[str]) -> str:
    value = os.environ.get(name, default).strip().lower()
    if value not in allowed:
        raise ValueError(f'{name} must be one of {sorted(allowed)}.')
    return value


@dataclass(frozen=True)
class Settings:
    offline_demo_mode: bool
    google_api_key: str | None
    groq_api_key: str | None
    gemini_model: str
    groq_model: str
    embedding_model: str
    tax_corpus_version: str
    minimum_retrieval_score: float
    batch_size: int
    max_retries: int
    api_delay_seconds: float
    confidence_threshold: float
    run_worker_count: int
    run_queue_capacity: int
    cors_origins: tuple[str, ...]
    trusted_hosts: tuple[str, ...]
    force_https: bool
    environment: str
    max_request_body_bytes: int
    max_transactions_per_run: int
    max_string_length: int
    requests_per_minute: int
    max_active_runs_per_owner: int
    max_provider_calls_per_run: int
    provider_call_estimated_cost_usd: float
    max_estimated_provider_cost_usd: float
    provider_timeout_seconds: float
    retry_base_delay_seconds: float
    retry_max_delay_seconds: float
    retry_jitter_ratio: float
    circuit_failure_threshold: int
    circuit_recovery_seconds: float
    rag_max_concurrency: int
    retrieval_grading_concurrency: int
    category_cache_ttl_seconds: int
    max_run_latency_seconds: float
    log_level: str
    run_storage_mode: str
    run_database_url: str
    checkpoint_database_url: str
    vector_backend: str
    vector_database_url: str
    vector_collection: str
    run_retention_hours: int
    allowed_data_root: Path
    checkpoint_path: Path
    chroma_path: Path
    pdf_dir: Path

    def provider_errors(self) -> list[str]:
        if self.offline_demo_mode:
            return []
        errors = []
        if not self.google_api_key:
            errors.append("GOOGLE_API_KEY is required in live mode.")
        if not self.groq_api_key:
            errors.append("GROQ_API_KEY is required in live mode.")
        return errors


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    environment = _choice(
        'ENVIRONMENT',
        'development',
        {'development', 'test', 'production'},
    )
    storage_mode = _choice(
        'RUN_STORAGE_MODE',
        'session',
        {'session', 'durable'},
    )
    default_checkpoint = (
        Path(tempfile.gettempdir())
        / f'smartwealth-session-{os.getpid()}.sqlite'
        if storage_mode == 'session'
        else PROJECT_ROOT / 'checkpoints.sqlite'
    )
    return Settings(
        offline_demo_mode=_bool('OFFLINE_DEMO_MODE', False),
        google_api_key=os.environ.get('GOOGLE_API_KEY'),
        groq_api_key=os.environ.get('GROQ_API_KEY'),
        gemini_model=os.environ.get('GEMINI_MODEL', 'gemini-3-flash-preview').strip(),
        groq_model=os.environ.get('GROQ_MODEL', 'llama-3.1-8b-instant').strip(),
        embedding_model=os.environ.get('EMBEDDING_MODEL', 'all-MiniLM-L6-v2').strip(),
        tax_corpus_version=os.environ.get('TAX_CORPUS_VERSION', 'smartwealth-tax-corpus-v1').strip(),
        minimum_retrieval_score=_float('MINIMUM_RETRIEVAL_SCORE', 0.45, 0.0, 1.0),
        batch_size=_int('BATCH_SIZE', 5, 1, 100),
        max_retries=_int('MAX_RETRIES', 3, 1, 10),
        api_delay_seconds=_float('API_DELAY_SECONDS', 4.0, 0.0, 60.0),
        confidence_threshold=_float('CONFIDENCE_THRESHOLD', 0.70, 0.0, 1.0),
        run_worker_count=_int('RUN_WORKER_COUNT', 2, 1, 32),
        run_queue_capacity=_int('RUN_QUEUE_CAPACITY', 8, 0, 1000),
        cors_origins=_csv(
            'CORS_ORIGINS',
            'http://localhost:5173,http://127.0.0.1:5173',
        ),
        trusted_hosts=_csv(
            'TRUSTED_HOSTS',
            'localhost,127.0.0.1,testserver',
        ),
        force_https=_bool('FORCE_HTTPS', False),
        environment=environment,
        max_request_body_bytes=_int(
            'MAX_REQUEST_BODY_BYTES',
            1_000_000,
            1_024,
            50_000_000,
        ),
        max_transactions_per_run=_int(
            'MAX_TRANSACTIONS_PER_RUN',
            500,
            1,
            10_000,
        ),
        max_string_length=_int(
            'MAX_STRING_LENGTH',
            500,
            20,
            10_000,
        ),
        requests_per_minute=_int(
            'REQUESTS_PER_MINUTE',
            120,
            1,
            100_000,
        ),
        max_active_runs_per_owner=_int(
            'MAX_ACTIVE_RUNS_PER_OWNER',
            2,
            1,
            100,
        ),
        max_provider_calls_per_run=_int(
            'MAX_PROVIDER_CALLS_PER_RUN',
            500,
            1,
            100_000,
        ),
        provider_call_estimated_cost_usd=_float(
            'PROVIDER_CALL_ESTIMATED_COST_USD',
            0.01,
            0.0,
            100.0,
        ),
        max_estimated_provider_cost_usd=_float(
            'MAX_ESTIMATED_PROVIDER_COST_USD',
            5.0,
            0.01,
            10_000.0,
        ),
        provider_timeout_seconds=_float(
            'PROVIDER_TIMEOUT_SECONDS',
            30.0,
            1.0,
            300.0,
        ),
        retry_base_delay_seconds=_float(
            'RETRY_BASE_DELAY_SECONDS',
            0.5,
            0.0,
            60.0,
        ),
        retry_max_delay_seconds=_float(
            'RETRY_MAX_DELAY_SECONDS',
            8.0,
            0.0,
            300.0,
        ),
        retry_jitter_ratio=_float(
            'RETRY_JITTER_RATIO',
            0.25,
            0.0,
            1.0,
        ),
        circuit_failure_threshold=_int(
            'CIRCUIT_FAILURE_THRESHOLD',
            5,
            1,
            100,
        ),
        circuit_recovery_seconds=_float(
            'CIRCUIT_RECOVERY_SECONDS',
            30.0,
            0.0,
            3600.0,
        ),
        rag_max_concurrency=_int('RAG_MAX_CONCURRENCY', 3, 1, 16),
        retrieval_grading_concurrency=_int(
            'RETRIEVAL_GRADING_CONCURRENCY',
            3,
            1,
            8,
        ),
        category_cache_ttl_seconds=_int(
            'CATEGORY_CACHE_TTL_SECONDS',
            3600,
            0,
            86_400,
        ),
        max_run_latency_seconds=_float(
            'MAX_RUN_LATENCY_SECONDS',
            300.0,
            1.0,
            86_400.0,
        ),
        log_level=_choice(
            'LOG_LEVEL',
            'info',
            {'debug', 'info', 'warning', 'error', 'critical'},
        ),
        run_storage_mode=storage_mode,
        run_database_url=os.environ.get('RUN_DATABASE_URL', '').strip(),
        checkpoint_database_url=os.environ.get(
            'CHECKPOINT_DATABASE_URL',
            '',
        ).strip(),
        vector_backend=_choice(
            'VECTOR_BACKEND',
            'pgvector' if environment == 'production' else 'chroma',
            {'chroma', 'pgvector'},
        ),
        vector_database_url=os.environ.get('VECTOR_DATABASE_URL', '').strip(),
        vector_collection=os.environ.get(
            'VECTOR_COLLECTION',
            'smartwealth_tax_corpus',
        ).strip(),
        run_retention_hours=_int(
            'RUN_RETENTION_HOURS',
            24,
            1,
            8760,
        ),
        allowed_data_root=_path(
            'ALLOWED_DATA_ROOT',
            PROJECT_ROOT / 'data',
        ),
        checkpoint_path=_path('CHECKPOINT_PATH', default_checkpoint),
        chroma_path=_path('CHROMA_PATH', PROJECT_ROOT / 'data' / 'chroma_db'),
        pdf_dir=_path('PDF_DIR', PROJECT_ROOT / 'data' / 'tax_corpus' / 'raw_pdfs'),
    )
