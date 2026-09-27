# Security Policy

## Supported version

Security fixes target the current main branch. No separate release line is
declared.

## Reporting a vulnerability

Do not open a public issue or publish provider keys, financial data, private
documents, credentials, or exploit details.

Use the repository owner's private contact channel or GitHub private
vulnerability reporting when enabled. Include the affected revision,
synthetic-data reproduction, expected and observed impact, and a suggested
mitigation when known.

## Current boundary

SmartWealth is a trusted local single-workspace application. It has no login,
bearer token, or tenant authorization. Do not expose its API to an untrusted or
multi-user network.

A hosted deployment requires real identity, tenant-scoped authorization,
protected operations, TLS, managed secrets, and verified managed storage. See
[docs/SECURITY_AND_PRIVACY.md](./docs/SECURITY_AND_PRIVACY.md) for the detailed
control and privacy model.
