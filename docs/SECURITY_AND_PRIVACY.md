# Security and privacy operations

## Data flow and consent

The browser requires explicit consent before upload. It sends transaction date,
merchant, amount, and description to the local API. The API creates
transaction IDs; client-supplied IDs and categories are rejected.

In live mode, transaction fields are sent to the configured Gemini provider and,
on failure, to Groq. Relevant tax-corpus passages may also be sent for grading
and treatment analysis. In OFFLINE_DEMO_MODE=true, no provider data leaves the
application. Confirm each vendor's current retention, training, contractual, and
regional-processing terms before live use. Region guarantees are not assumed by
this repository; select region-controlled vendor endpoints where required.

Provider fallback increases availability but may expand the processors receiving
data. Disable live mode when that is unacceptable. Consent text must identify
both configured providers.

## Trust boundary, secrets, and transport

This build intentionally has no login or API credential. Every run belongs to
one fixed `local-workspace` namespace. Run IDs scope normal read, resume,
cancel, and delete operations, but they are not authorization. Bind the API to
a trusted local interface and do not expose it to an untrusted or multi-user
network. A future hosted deployment must add identity and authorization before
exposure. Provider keys must remain in a platform secret manager or injected
environment variables, never committed files or frontend bundles.

Terminate TLS at a trusted proxy such as the included Caddy configuration. Set
ENVIRONMENT=production, configure exact CORS_ORIGINS and TRUSTED_HOSTS, and set
FORCE_HTTPS=true only when the application receives correct scheme information
directly or from a trusted proxy.

## Retention and deletion

RUN_STORAGE_MODE=session is the default. Its temporary SQLite checkpoint is
removed on clean shutdown. Browser storage contains only the run ID, status,
progress, and safe errors in sessionStorage; transaction and report data are not
persisted there.

Runs expire after RUN_RETENTION_HOURS; terminal expired runs and their
checkpoints, idempotency records, and human-override audit events are purged
during recovery. Owners can delete terminal runs immediately through
DELETE /api/runs/{run_id}. Durable mode must be paired with an operational
scheduled restart/recovery or purge process and encrypted storage backups.

## Threat model and controls

| Threat | Control | Residual risk |
|---|---|---|
| Unauthorized network access | Trusted local binding, restricted hosts/CORS, opaque run IDs, no global purge route | No identity boundary; network access implies workspace access |
| Request flooding/cost exhaustion | Body, row, active-run, rate, provider-call, and estimated-cost caps | In-memory rate counters reset on restart |
| Prompt injection | Untrusted-data delimiters, capped input, strict ID/order/category/confidence validation | Model behavior still requires monitoring |
| Provider/log leakage | No raw provider exceptions or merchant details in operational logs | Infrastructure logs must also be configured safely |
| Destructive index rebuild | Allowed-root validation, staging build, atomic swap, rollback | Host-level compromise |
| Human override tampering | Append-only application path with SHA-256 hash chain and correlation IDs | Database administrators can rewrite storage |
| Supply-chain compromise | Pinned Python requirements, npm lockfile, audits, secret scan, and SBOM CI | Newly disclosed issues between CI runs |

## Incident and verification checklist

Rotate affected provider credentials, preserve correlation-ID logs,
and assess provider exposure. Run backend tests, frontend lint and build,
pip-audit, npm audit, and secret scanning before release. Review generated
CycloneDX files in sbom and document any accepted vulnerability with an owner
and expiry date.

## Temporary ChromaDB advisory exception

As of 2026-09-26, pip-audit reports PYSEC-2026-311,
PYSEC-2026-3813, PYSEC-2026-3814, and PYSEC-2026-3815 against the
latest ChromaDB 1.5.9 and lists no fixed release. They concern the Chroma
HTTP server's collection-management and multi-tenant authorization endpoints.
Smart Wealth uses only the embedded persistent client and does not start or
publish a Chroma server. Network access to Chroma must remain blocked.

CI ignores only these four IDs so any new advisory still fails the build.
Remove the exceptions and upgrade immediately when upstream publishes a fixed
release. This is a time-limited risk acceptance, not a claim that the package
is vulnerability-free.
