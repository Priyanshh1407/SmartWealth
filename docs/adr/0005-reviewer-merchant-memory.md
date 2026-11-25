# ADR 0005: Reviewer merchant memory and post-completion category changes

- Status: Accepted
- Date: 2026-11-25

## Context

Merchants the categorizer does not recognise are routed to human review row by
row. A ledger with several charges from the same unknown merchant asked the
reviewer the same question repeatedly, and every new audit asked again. Once a
run completed there was no way to correct a category without starting over.

## Decision

Store each reviewer category decision per owner and normalised merchant
(case- and whitespace-insensitive) in `sw_merchant_memory`. Before pausing for
review, the auditor loop resolves open rows whose merchant is remembered and
records each as a `memory_override` event in the run's hash-chained audit trail,
linked to the source transaction. Placeholder merchants such as `POS DEBIT`,
`Unknown`, and `MISC CHRG` are never remembered, because they identify no
counterparty.

Completed runs accept `POST /api/runs/{run_id}/revise`. The change is recorded
as a `human_revision` event, updates the memory, and reopens the run: the
decision is written into the checkpoint as if the review step produced it, so
the graph's own edges re-run corrective RAG and the report.

## Consequences

Reviewers answer once per merchant, and audits get faster over time. A wrong
memory propagates, so remembered rows are labelled in the ledger, the evidence
drawer, and the audit trail, any row can be changed after completion, and
`DELETE /api/merchant-memory` clears the memory. Memory is merchant-level, not
transaction-level: a merchant that sells across categories still needs a
reviewer to change individual rows. It is not tied to run retention and lives
until cleared.
