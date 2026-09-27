# ADR 0004: Trusted local single-workspace privacy boundary

- Status: Accepted for the local single-workspace build
- Date: 2026-09-27

## Context

The current product boundary is a local single-workspace application. The previous bearer-token gate
added configuration and UI friction without supplying a complete identity
system. A partial credential layer could be mistaken for production security.

## Decision

Remove the API credential flow completely. All runs use one fixed
`local-workspace` namespace. Retain strict schemas, opaque server IDs, scoped
run deletion, body/rate/concurrency/provider budgets, restricted CORS/trusted
hosts, safe errors, retention, and audit hashing. Remove the global purge route.

## Consequences

Local use is simpler and the boundary is honest. Anyone who can reach the
API can access the workspace, so it must not be exposed to an untrusted or
multi-user network. A hosted deployment is blocked until real identity,
authorization, tenant isolation, and protected operations are added.
