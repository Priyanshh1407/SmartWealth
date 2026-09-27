# ADR 0001: LangGraph for durable human-supervised workflow

- Status: Accepted
- Date: 2026-09-27

## Context

The audit must branch on confidence, stop for human judgment, survive a process
restart, and resume from the same logical point. A request/response chain or a
collection of unrelated agents would make those transitions implicit.

## Decision

Use one explicit LangGraph state machine: extraction, optional auditor
interrupt, corrective RAG, and report. Persist graph checkpoints under the
server-generated run ID and keep lifecycle status in the authoritative run
store. Durable run events explain the graph's visible history.

## Consequences

Interrupt/resume behavior is deterministic and testable, but graph checkpoints
and lifecycle records must be reconciled during recovery. Nodes remain
sequential responsibilities; the project does not claim a multi-agent design.
