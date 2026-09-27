CREATE TABLE IF NOT EXISTS sw_runs (
    run_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('queued', 'running', 'waiting_for_input', 'completed', 'failed', 'cancelled')
    ),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    error_code TEXT,
    error_message TEXT,
    current_node TEXT NOT NULL,
    progress_message TEXT NOT NULL,
    progress_processed INTEGER NOT NULL CHECK (progress_processed >= 0),
    progress_total INTEGER NOT NULL CHECK (progress_total >= 0),
    version INTEGER NOT NULL CHECK (version >= 1),
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
    warnings_json TEXT NOT NULL DEFAULT '[]',
    provider_calls INTEGER NOT NULL DEFAULT 0 CHECK (provider_calls >= 0),
    provider_input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (provider_input_tokens >= 0),
    provider_output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (provider_output_tokens >= 0),
    estimated_provider_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0 CHECK (
        estimated_provider_cost_usd >= 0
    ),
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS sw_runs_owner_status
    ON sw_runs(owner_id, status);
CREATE INDEX IF NOT EXISTS sw_runs_expiry
    ON sw_runs(expires_at, status);

CREATE TABLE IF NOT EXISTS sw_idempotency (
    owner_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES sw_runs(run_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, operation, idempotency_key)
);

CREATE TABLE IF NOT EXISTS sw_audit_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES sw_runs(run_id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    answer TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS sw_audit_run
    ON sw_audit_events(run_id, occurred_at);
