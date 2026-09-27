CREATE TABLE IF NOT EXISTS sw_run_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES sw_runs(run_id) ON DELETE CASCADE,
    owner_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS sw_run_event_timeline
    ON sw_run_events(run_id, occurred_at, event_id);

ALTER TABLE sw_audit_events
    ADD COLUMN IF NOT EXISTS prior_prediction TEXT NOT NULL DEFAULT '';
ALTER TABLE sw_audit_events
    ADD COLUMN IF NOT EXISTS downstream_impact TEXT NOT NULL DEFAULT '';
