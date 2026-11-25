-- Reviewer decisions remembered per merchant so the same merchant is not
-- asked about again. Not tied to a run: it outlives run retention and is
-- cleared explicitly through DELETE /api/merchant-memory.
CREATE TABLE IF NOT EXISTS sw_merchant_memory (
    owner_id TEXT NOT NULL,
    merchant_key TEXT NOT NULL,
    merchant TEXT NOT NULL,
    category TEXT NOT NULL,
    source_run_id TEXT NOT NULL,
    source_transaction_id TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, merchant_key)
);
