# SmartWealth Architecture

SmartWealth is built on an **Agentic State Machine** powered by LangGraph. It is designed to evaluate raw financial transactions against actual legal corpora (like the Indian Income Tax Act), preventing AI hallucinations using Corrective RAG, and pausing for human intervention on ambiguous edges.

## High-Level Graph Architecture

```mermaid
graph TD
    %% Core Nodes
    START((Start))
    Extraction[NODE 1: Extraction & Categorization]
    Router1{Router: Confidence Check}
    Auditor[NODE 3: Human-in-the-Loop Auditor]
    CRAG[NODE 2: Corrective RAG]
    Router2{Router: Pending Answers?}
    Report[NODE 4: Generate Validated Report]
    END((End))

    %% Edges
    START --> Extraction
    Extraction --> Router1
    
    %% Router 1 Logic
    Router1 -- "Confidence < 70%" --> Auditor
    Router1 -- "Confidence >= 70%" --> CRAG
    
    %% Auditor Loop Logic
    Auditor --> Router2
    Router2 -- "Unanswered Questions" --> Auditor
    Router2 -- "All Resolved" --> CRAG
    
    %% Execution Path
    CRAG --> Report
    Report --> END

    %% Styles
    classDef node fill:#1a1a1a,stroke:#4cd7f6,stroke-width:2px,color:#fff;
    classDef router fill:#1a1a1a,stroke:#ffb95f,stroke-width:2px,color:#fff;
    classDef endpoint fill:#1a1a1a,stroke:#4ade80,stroke-width:2px,color:#fff;
    
    class Extraction,CRAG,Auditor,Report node;
    class Router1,Router2 router;
    class START,END endpoint;
```

## Corrective RAG (CRAG) Flow

The CRAG node is the hallucination guardrail. It prevents the AI from approving a tax deduction unless it can physically cite a relevant section of the tax law.

```mermaid
graph TD
    %% CRAG Nodes
    Input(Category Name)
    Retrieve[Retrieve from ChromaDB]
    Grade{Grader LLM: Relevant?}
    Rewrite[Rewrite Query]
    Analyze[Analyze Deductibility]
    Fail[Mark Not Deductible]
    Pass[Mark Deductible with Citation]

    %% Edges
    Input --> Retrieve
    Retrieve --> Grade
    
    Grade -- "Yes" --> Analyze
    Grade -- "No" --> Rewrite
    
    Rewrite --> Retrieve
    Rewrite -. "Max Retries" .-> Fail
    
    Analyze -- "is_deductible: False" --> Fail
    Analyze -- "is_deductible: True" --> Pass

    %% Styles
    classDef process fill:#1a1a1a,stroke:#4cd7f6,stroke-width:2px,color:#fff;
    classDef decision fill:#1a1a1a,stroke:#ffb95f,stroke-width:2px,color:#fff;
    classDef success fill:#1a1a1a,stroke:#4ade80,stroke-width:2px,color:#fff;
    classDef error fill:#1a1a1a,stroke:#ff5449,stroke-width:2px,color:#fff;
    
    class Input,Retrieve,Rewrite,Analyze process;
    class Grade decision;
    class Pass success;
    class Fail error;
```

## Data Persistence & State

1. **Graph checkpoint:** LangGraph checkpoints `AuditState` at node
   boundaries, allowing the auditor interrupt to survive a process restart.
2. **Authoritative run store:** A separate optimistic-locked run record owns
   queued/running/waiting/completed/failed/cancelled lifecycle, progress,
   retention, idempotency, provider budget, and safe errors.
3. **Durable evidence events:** Lifecycle/stage events and hash-chained human
   overrides are committed with run mutations. The current SSE stream delivers
   those events to the visual timeline and audit trail.
4. **Versioned evidence:** Legal results carry corpus, document, section, page,
   chunk, passage, and retrieval score into the evidence drawer and report.
5. **Optimized batching:** CRAG evaluates each unique category once, then
   applies transaction-specific amount, unresolved, and review safeguards.

## Access boundary

The local single-workspace build has no login or API credential and uses one trusted
`local-workspace` namespace. Opaque run IDs scope workflow operations but are
not authorization. Restricted hosts/origins, validation, rate/body/concurrency
limits, provider budgets, safe errors, and scoped deletion remain active. A
hosted multi-user deployment requires real identity and tenant authorization.
