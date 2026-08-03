# Smart Wealth — Tax & Expense Auditor
### Full Project Plan, Phases, Architecture & Master Prompt
*Prepared for portability across AI coding assistants (Claude Code, Cursor, etc.)*

---

## 0. Project Identity (read this first, every session)

**One-line pitch:** An agentic LangGraph pipeline that ingests messy financial records, cross-references expenses against real tax-code documents via Corrective RAG, and — when it hits genuine ambiguity — pauses execution, checkpoints state, asks the user a targeted clarifying question, and resumes from that exact point with zero lost work.

**What this project is NOT claiming:**
- Not a TurboTax/accountant replacement. It's a pre-processing/triage layer before a human accountant.
- Not zero-hallucination. It's "escalates uncertainty instead of hiding it."
- Not multi-agent (v1). It's a single orchestrated state graph with specialized nodes. (See §7 for an optional v2 multi-agent extension — don't build this until the core is solid.)

**The one thing this project must prove, above all else:** a working interrupt → checkpoint → human-in-the-loop → resume cycle, demoable live, with a real recorded failure story. Everything else (categorization accuracy, RAG quality, UI polish) is secondary to nailing this.

**Data:** 100% synthetic transactions/receipts (Faker-generated). Real, public tax-authority PDFs for the RAG corpus only. No real personal financial data ever touches this project.

---

## 1. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Orchestration | **LangGraph** (Python) | Native support for checkpointing, interrupts, conditional edges — this is the entire reason this framework was chosen over a plain agent loop |
| LLM | Claude API (Sonnet-class) or Gemini free tier (reuse DevTelemetry pattern) | Tool-calling + structured output support |
| Vector store | ChromaDB (reuse from RecruitIQ) | Familiar, local, no infra overhead |
| Checkpointer | LangGraph's `SqliteSaver` (start local) → Postgres later if deployed | This is what makes pause/resume durable across process restarts, not just in-memory |
| Backend | FastAPI | Reuse from DevTelemetry |
| Frontend | React + Vite + Tailwind + Zustand | Reuse from RecruitIQ — you already have this stack muscle-memoried |
| Synthetic data | Python `Faker` | Procedural generation, seeded for reproducibility |
| Receipts | HTML → PDF render (`weasyprint` or `playwright`) | Simple, controllable, no scanning/OCR needed for v1 |
| Eval | Custom harness — precision/recall against known synthetic ground truth | This is your defensible number for the resume |

---

## 2. Repo / Folder Structure

```
smart-wealth/
├── README.md                          # Public-facing project overview
├── PROJECT_PLAN.md                    # This document — keep in repo root
├── .env.example
├── .gitignore
│
├── data/
│   ├── generation/
│   │   ├── generate_transactions.py   # Faker script — seeded, reproducible
│   │   ├── generate_receipts.py       # Renders subset of transactions to PDF
│   │   ├── ground_truth_schema.json   # The "answer key" — used ONLY by eval, never by the pipeline
│   │   └── config.yaml                # Seed, date range, category distribution, gap %
│   ├── synthetic/
│   │   ├── transactions_2025.csv      # Generated output (gitignored, regenerate via script)
│   │   └── receipts/                  # Generated PDFs (gitignored)
│   └── tax_corpus/
│       ├── raw_pdfs/                  # Real public tax authority docs
│       └── source_manifest.md         # URL + retrieval date for every PDF — cite your corpus
│
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI entrypoint
│   │   ├── graph/
│   │   │   ├── state.py               # TypedDict / Pydantic state schema (§4 below)
│   │   │   ├── builder.py             # StateGraph assembly — nodes + edges wired here
│   │   │   ├── nodes/
│   │   │   │   ├── extraction.py      # Node 1
│   │   │   │   ├── corrective_rag.py  # Node 2 (CRAG: retrieve → grade → rewrite/retry)
│   │   │   │   ├── auditor_loop.py    # Node 3 — the interrupt/resume centerpiece
│   │   │   │   └── report.py          # Node 4 — final structured output
│   │   │   ├── edges/
│   │   │   │   └── conditionals.py    # Confidence-based routing logic
│   │   │   └── checkpointer.py        # SqliteSaver config
│   │   ├── rag/
│   │   │   ├── ingest.py              # Chunk + embed tax PDFs into Chroma
│   │   │   ├── retriever.py
│   │   │   └── grader.py              # Relevance-grading step (CRAG-specific)
│   │   ├── tools/
│   │   │   └── categorizer_tools.py   # Tool-calling schemas for extraction node
│   │   ├── api/
│   │   │   ├── routes_run.py          # POST /run, POST /resume/{thread_id}
│   │   │   └── routes_clarify.py      # GET pending clarifications, POST answer
│   │   └── db/
│   │       └── models.py              # Run metadata, clarification queue table
│   ├── tests/
│   │   ├── test_extraction.py
│   │   ├── test_crag.py
│   │   ├── test_interrupt_resume.py   # THE most important test file in this repo
│   │   └── test_failure_injection.py  # Deliberately broken inputs — see §6
│   └── requirements.txt
│
├── eval/
│   ├── run_eval.py                    # Compares pipeline output to ground_truth_schema.json
│   ├── metrics.py                     # Precision/recall/F1 for categorization + deductibility
│   └── eval_report.md                 # Generated output — your resume number lives here
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── UploadPanel.jsx
│   │   │   ├── ClarificationDashboard.jsx   # The UI for the pause/resume UX
│   │   │   ├── AuditReport.jsx
│   │   │   └── RunStatusTimeline.jsx        # Visualizes which node the graph is on
│   │   ├── store/
│   │   │   └── useRunStore.js         # Zustand — run state, polling for pending clarifications
│   │   └── api/
│   │       └── client.js
│   └── package.json
│
└── docs/
    ├── phase_logs/                    # One file per phase — your debugging story lives here
    │   ├── phase0_log.md
    │   ├── phase1_log.md
    │   └── ...
    ├── architecture_diagram.md
    └── interview_talking_points.md    # Write this AS you build, not after
```

**Why `docs/phase_logs/` matters:** per your own project history (DevTelemetry, RecruitIQ, Document Tampering Detector), your strongest interview material has always come from documented debugging — not the finished feature. Write the log entry *when the bug happens*, not reconstructed afterward from memory.

---

## 3. Phases

Each phase has: goal, deliverable, exit criteria (what must work before you move on), and the failure-handling concern specific to that phase.

### Phase 0 — Environment & Data Foundation
- **Goal:** Repo scaffolded, synthetic data generation working end-to-end, tax corpus collected.
- **Deliverables:** `generate_transactions.py` producing a seeded 12-month CSV; `generate_receipts.py` producing a deliberately incomplete subset of PDFs; 3-5 real tax authority PDFs downloaded with `source_manifest.md` populated.
- **Exit criteria:** Running the generation scripts twice with the same seed produces byte-identical output (reproducibility for eval later).
- **Failure concern:** None yet — but decide your gap percentage now (what % of transactions get NO receipt) since this directly controls how often Node 3 triggers later. Recommend 15-20% gap rate — enough to demo the auditor loop repeatedly, not so much it looks unrealistic.

### Phase 1 — State Schema & Graph Skeleton
- **Goal:** Define the LangGraph state object and wire up an empty graph (nodes are stubs that just pass state through).
- **Deliverable:** `state.py` + `builder.py` compiling and running a no-op graph end to end with the SqliteSaver checkpointer attached.
- **Exit criteria:** You can call the graph, kill the process mid-run (literally `kill -9`), restart, and resume from the checkpoint. Prove this *before* any real node logic exists — it's infrastructure, not a feature, and everything else depends on it working.
- **Failure concern:** This IS the failure-handling phase for the whole project. If checkpointing doesn't survive a hard process kill here, no amount of node logic later will save you.

### Phase 2 — Node 1: Extraction & Categorization
- **Goal:** Parse the CSV, categorize each line item, attach a confidence score per categorization.
- **Deliverable:** Tool-calling extraction node; conditional edge that routes low-confidence rows toward Node 3 instead of forcing a guess.
- **Exit criteria:** Run against synthetic data, manually spot-check 20 rows — do confidence scores actually correlate with rows you'd find genuinely ambiguous?
- **Failure concern:** Malformed/truncated descriptions ("AMZN", empty merchant field). Explicitly test these — this is where §Failure Handling from our chat gets implemented, not just discussed.

### Phase 3 — Node 2: Corrective RAG
- **Goal:** Ingest tax PDFs into Chroma; implement retrieve → grade → rewrite-and-retry → give-up-and-flag.
- **Deliverable:** `corrective_rag.py` with the full CRAG loop, `grader.py` scoring retrieval relevance.
- **Exit criteria:** Deliberately ask about an expense type NOT covered by your corpus (e.g., something jurisdiction-specific you didn't ingest) and confirm the node flags "deductibility undetermined" rather than answering from the model's parametric memory. This is your most important correctness test in the whole project — write it down as a passing test, not a manual check.
- **Failure concern:** The silent-hallucination-fallback failure mode. Build the negative test case (Phase 3 exit criteria above) before you consider this node done.

### Phase 4 — Node 3: The Auditor Loop (Interrupt/Resume) — the centerpiece
- **Goal:** Wire the actual human-in-the-loop pause/resume mechanic using LangGraph's `interrupt()`.
- **Deliverable:** Graph pauses on ambiguous transactions, persists a "pending clarification" record, exposes it via API, resumes correctly once answered — including after a real process restart, not just an in-memory pause.
- **Exit criteria (all must pass):**
  1. Single ambiguous transaction → pause → answer via API → resume → correct categorization applied downstream.
  2. Kill the server process while paused → restart → clarification still pending → answer → resumes correctly. (This is the test that actually proves your resume claim — an in-memory-only pause doesn't count.)
  3. Batch of 300 transactions with 40 ambiguous → confirm the other 260 aren't blocked waiting on the 40 (decide explicitly: parallel continue + batch clarifications at the end, per our earlier discussion).
  4. Unusable clarification answer ("idk") → decide and implement: re-prompt once, then downgrade to "unresolved — flag for accountant" rather than hang forever.
- **Failure concern:** This entire phase IS failure handling. Do not treat it as "add error handling later" — the graceful-degradation paths above (partial batch continuation, bad-answer downgrade, crash-durability) are the feature.

### Phase 5 — Node 4: Report Generation
- **Goal:** Structured final output — deduction totals, audit-risk flags (with cited source passages), unresolved items list.
- **Deliverable:** `report.py` producing a schema-validated JSON, plus a human-readable rendering.
- **Exit criteria:** Every deductibility claim in the output traces back to a specific retrieved passage ID — no unsourced claims allowed to reach the report.

### Phase 6 — Eval Harness
- **Goal:** Turn "it seems to work" into a real number.
- **Deliverable:** `run_eval.py` comparing pipeline output against `ground_truth_schema.json` (the answer key generated alongside the synthetic data in Phase 0), producing precision/recall/F1 for both categorization and deductibility flags.
- **Exit criteria:** A real, reproducible number written into `eval_report.md`. This is your resume bullet — don't skip it or leave it vague like you flagged in your own notes.

### Phase 7 — Frontend
- **Goal:** Upload panel, the Clarification Dashboard (the UX for the pause/resume cycle — this should visually make the interrupt mechanic legible, since it's your centerpiece), audit report view, a run-status timeline showing which node is currently active.
- **Deliverable:** React app wired to the FastAPI backend.
- **Exit criteria:** A live demo path: upload → watch it process → see it pause on an ambiguous transaction → answer inline → watch it resume → see final report.

### Phase 8 — Polish, Documentation, Interview Prep
- **Goal:** README, architecture diagram, `interview_talking_points.md` finalized, deployment (Render, reusing your DevTelemetry pattern) if you want it live.
- **Deliverable:** Everything demoable from a public URL or a clean local `docker-compose up`.
- **Exit criteria:** You can walk a stranger through the interrupt/resume demo in under 3 minutes without touching code.

---

## 4. State Schema (design this in Phase 1, sketch now)

```python
class AuditState(TypedDict):
    thread_id: str
    transactions: list[Transaction]          # from CSV ingestion
    receipts_index: dict[str, str]            # transaction_id -> receipt_path if matched
    categorized: list[CategorizedTransaction] # output of Node 1
    deductibility_results: list[DeductibilityResult]  # output of Node 2, each with source_citation
    pending_clarifications: list[ClarificationRequest]  # queue for Node 3
    resolved_clarifications: dict[str, str]   # transaction_id -> user answer
    unresolved_flags: list[str]               # transactions downgraded after bad/no answer
    final_report: AuditReport | None
    current_node: str                         # for the frontend run-status timeline
```

Keep every sub-object (`Transaction`, `DeductibilityResult`, etc.) as a Pydantic model, not a loose dict — you want schema validation errors to surface immediately, not three nodes downstream.

---

## 5. Failure-Handling Matrix (reference this throughout, don't rebuild it per-node)

| Failure mode | Where it happens | Design response |
|---|---|---|
| Malformed/truncated transaction description | Node 1 | Confidence score below threshold → route to clarification, don't force-categorize |
| Retrieval returns irrelevant tax-code passage | Node 2 | Grade relevance → rewrite query + retry once → if still bad, flag "undetermined," never fall back to parametric memory |
| Transaction has no matching receipt | Node 1→3 handoff | Route to Auditor Loop, not silently skipped or silently assumed-deductible |
| User never answers a pending clarification | Node 3 | State persists indefinitely via checkpointer; no timeout-based data loss |
| User gives an unusable answer | Node 3 | Re-prompt once with a more specific question; if still unusable, downgrade to "unresolved — flag for accountant," continue rather than hang |
| Process crash mid-run (server restart, deploy) | Any node | SqliteSaver checkpoint means resume from last completed node, not from zero |
| Large batch with partial ambiguity (40/300 flagged) | Node 3 | Don't block the 260 clean transactions — continue processing, batch clarifications for user review at the end |
| Schema validation failure on a node's output | Any node | Fail loudly at that node with a logged error, don't let malformed state silently propagate downstream |

---

## 6. Master Prompt (for continuing this project across AI coding assistant sessions)

Copy this into a fresh Claude Code / Cursor session whenever you resume work, and append the specific phase you're on:

```
I'm building "Smart Wealth" — a Tax & Expense Auditor built as a LangGraph state machine.
Full context and phase plan is in PROJECT_PLAN.md at the repo root — read it first.

Core identity: this project's centerpiece is a working interrupt → checkpoint →
human-in-the-loop clarification → resume cycle (Node 3, the "Auditor Loop"), backed by
LangGraph's SqliteSaver checkpointer. This must survive an actual process restart, not
just an in-memory pause. Everything else in the pipeline (categorization, Corrective RAG)
is real but secondary to this mechanic working correctly.

Hard constraints, do not violate:
- 100% synthetic transaction/receipt data (Faker-generated). Real data only for the
  tax-code RAG corpus (public government PDFs), never for financial records.
- Every deductibility claim in the final output must cite a specific retrieved passage.
  If retrieval fails or is low-relevance after one rewrite/retry, flag "undetermined" —
  never let the model answer from parametric memory as a fallback. This is the single
  most important correctness rule in the project.
- Node 1 (extraction) must attach a confidence score to every categorization and route
  low-confidence rows to the clarification queue instead of forcing a guess.
- The Auditor Loop must not block unrelated transactions in a batch — continue
  processing clean items, batch clarifications for the user at the end.
- A user giving an unusable clarification answer gets one re-prompt, then downgrades to
  "unresolved — flag for accountant," never an indefinite hang.

I am currently on: [PHASE X — paste from PROJECT_PLAN.md]
My exit criteria for this phase: [paste from PROJECT_PLAN.md]

Please [specific ask for this session]. Follow the folder structure in PROJECT_PLAN.md
section 2 exactly — don't restructure without asking first.
```

---

## 7. Things to Decide Before Writing Code (don't skip this)

1. **Gap rate for receipts** (Phase 0) — recommend 15-20%. This is the single number that controls how often your demo centerpiece actually triggers.
2. **Confidence threshold for Node 1 routing** — pick a number (e.g., <0.7 confidence → clarification queue) and write down *why* that number, since you'll be asked.
3. **CRAG retry limit** — how many query rewrites before giving up and flagging undetermined? Recommend 1 retry, not more — a longer retry chain adds latency without a clear accuracy payoff for a v1.
4. **Batch clarification UX** — do clarifications surface one at a time or all at once at the end of a run? Decide before building the frontend, not during.
5. **Deployment or local-only?** — DevTelemetry is already deployed on Render, so you have the muscle memory; decide if this needs a live URL or if a clean local demo is enough for interviews.

## 8. Optional v2 Extension (do NOT build until v1's core is solid)

If you want a genuine multi-agent extension later (separate from this v1 scope): a categorizer agent and a compliance/deductibility agent that can actually *disagree* and reconcile — e.g., categorizer says "Meals," compliance agent flags the 50%-deductibility rule and asks whether it was a client meeting — with the disagreement itself triggering a clarification. That's real agent-to-agent communication, distinct from this project's sequential-node design. Resist adding this for the label alone; per your own meta-lesson, depth on the interrupt/resume mechanic outweighs bolting on multi-agent complexity that dilutes focus.
