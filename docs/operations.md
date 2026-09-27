# SmartWealth Operations Runbook

## Deployment boundary

Development and tests default to SQLite checkpoints/run records and an immutable,
versioned Chroma directory. Setting `ENVIRONMENT=production` changes the default
vector backend to pgvector and requires PostgreSQL URLs for run records,
LangGraph checkpoints, and corpus embeddings. Production startup fails rather
than silently falling back to single-machine SQLite or Chroma.
The API exposes `/health/live`, `/health/ready`, and `/metrics` endpoints.
The current build is a trusted local/single-workspace prototype with no
authentication boundary; do not expose it to an untrusted network.

## Deploy

1. Provide the three PostgreSQL connection URLs, provider keys,
   `TRUSTED_HOSTS`, and `CORS_ORIGINS` through the deployment
   secret manager.
2. Install pinned dependencies in an isolated runtime and run the full CI suite.
   Do not bake runtime environment files into deployment artifacts.
3. Run `python -m backend.app.migrations`; checksum mismatches stop deployment.
4. Ingest the requested `TAX_CORPUS_VERSION` into its versioned pgvector
   collection before routing traffic.
5. Start Uvicorn through the selected managed process/hosting platform and wait
   for `/health/ready`.
6. Run `python scripts/load_test.py`, then a provider-free audit smoke test.

## Metrics and alerts

Scrape `/metrics` only from the trusted local/operations network. Alert on readiness zero,
HTTP 5xx growth, queue rejections/saturation, provider failures, open circuits,
run failures, latency-budget violations, and cost-budget exhaustion. Metrics
avoid owner IDs, run IDs, descriptions, and other private/high-cardinality
labels. JSON logs carry request, trace, run, and provider-attempt IDs.

## Backup and restore drill

- PostgreSQL backup: `python -m backend.app.backup backup --database-url ...`
- Restore into a clean drill database, never over the live database first:
  `python -m backend.app.backup restore --database-url ... --file <dump>`
- Run migrations, compare row counts and audit-chain verification, start one
  backend against the drill database, and execute an offline audit.
- Retain encrypted backups according to policy and test restoration quarterly.

SQLite development backups use `--sqlite-path`; the helper uses SQLite's
online backup API rather than copying a live WAL database directly.

## Corpus release and rollback

Every corpus version maps to a distinct Chroma directory or pgvector
collection. Verify a rollback target with:

`python -m scripts.corpus_release <version> --verify`

Redeploy with `TAX_CORPUS_VERSION=<version>`. Because releases are immutable,
rollback changes only the selected collection; it does not destructively
rewrite the newer release. Re-run readiness, retrieval fixtures, and the
provider-free smoke test after switching.

## Application rollback

Roll back frontend and backend to the prior compatible source release. Database migrations are forward-only; restore the
pre-deploy backup into a new database when a schema rollback is required,
validate it, then switch the connection secret. Never edit an applied
migration because checksum verification will reject it.

Containerization is intentionally deferred until a hosting target is chosen.
When added, images should run as non-root, use the existing health endpoints,
execute migrations as a release step, and preserve the same rollback rules.
