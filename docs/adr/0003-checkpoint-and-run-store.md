# ADR 0003: Separate graph checkpoints from authoritative run lifecycle

- Status: Accepted
- Date: 2026-09-27

## Context

A LangGraph checkpoint describes computation state, but it does not by itself
represent queueing, cancellation, safe errors, retention, idempotency, cost, or
operator-facing progress.

## Decision

Store lifecycle state in an optimistic-locked run record and graph state in the
checkpoint store, both keyed by the run UUID. Append timeline and human
override events in the same database transactions as lifecycle mutations.
Recovery reconciles the two sources before accepting work.

## Consequences

Waiting, failed, completed, and cancelled states remain truthful across
restarts. The design adds reconciliation logic and requires migrations,
backup/restore coverage, and atomic deletion of runs, events, and checkpoints.
