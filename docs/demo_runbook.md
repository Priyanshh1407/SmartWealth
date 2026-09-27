# SmartWealth Deterministic Demo Runbook

## Reliable offline mode

Run these commands in Git Bash from the repository root:

```bash
source .venv/Scripts/activate
export OFFLINE_DEMO_MODE=true
export RUN_STORAGE_MODE=durable
export CHECKPOINT_PATH=demo-checkpoints.sqlite
export ENVIRONMENT=development
export API_DELAY_SECONDS=0
python -m backend.app.preflight
python -m backend.app.main
```

In a second Git Bash terminal:

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`.

## Three-minute product walkthrough

1. Explain that SmartWealth converts a ledger into an evidence-backed draft
   while escalating uncertainty to a human.
2. Select **Failure demo**. The request follows the real run, SSE, checkpoint,
   and LangGraph path.
3. Show the timeline's clearly marked simulated provider rate limit and
   deterministic fallback.
4. At the human-review pause, resolve the row as **Office Supplies**.
5. Show successful resume, RAG analysis, report generation, and completion.
6. Open the override record and explain prior prediction, answer, downstream
   impact, correlation identity, and hash chain.
7. Open the evidence drawer and show document/chunk provenance and support
   reasoning.
8. Open Evaluation and explain the separation between historical evidence and
   the controlled provider-free fixture.
9. State the boundary: offline evidence validates workflow behavior, not
   tax-law accuracy, and the API is limited to a trusted local workspace.

## Durable recovery demonstration

While a run is waiting for input:

1. Stop the backend with Ctrl+C.
2. Restart it with the same durable configuration.
3. Reload the browser.
4. Confirm the same run is still waiting.
5. Resolve the clarification and confirm completion.

## Live-provider mode

Use live mode only with authorization to transmit the selected data and after
reviewing provider quota, cost, retention, and region terms.

```bash
unset OFFLINE_DEMO_MODE
python -m backend.app.preflight --env-file .env
python -m backend.app.main
```

## Fallback

If live network or provider access is unavailable, return to offline mode and
use the controlled failure demo. Never modify or display a live environment
file during a presentation.

## Cleanup

After stopping the backend:

```bash
rm -f -- demo-checkpoints.sqlite demo-checkpoints.sqlite-wal demo-checkpoints.sqlite-shm
unset OFFLINE_DEMO_MODE RUN_STORAGE_MODE CHECKPOINT_PATH ENVIRONMENT API_DELAY_SECONDS
```
