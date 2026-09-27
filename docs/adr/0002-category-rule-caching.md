# ADR 0002: Category-level legal-rule cache with row-level safeguards

- Status: Accepted with limitations
- Date: 2026-09-27

## Context

Retrieving and grading the same legal rule for every row is slow and consumes
provider budget. Reusing one result for a category can overgeneralize business
purpose, mixed use, capitalization, and evidence.

## Decision

Cache versioned legal-rule analysis by category and corpus release, bounded by
TTL and entry count. Apply the cached rule only after transaction-specific
amount, unresolved-state, evidence, and accountant-review safeguards.

## Consequences

The cache reduces repeated retrieval calls and improves latency. It is not a
substitute for transaction facts. The evidence drawer exposes the exact corpus,
document, page, chunk, passage, score, and reasoning so reuse is inspectable.
