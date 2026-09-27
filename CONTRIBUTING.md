# Contributing to SmartWealth

Keep contributions focused, reviewable, and safe for a financial-data
application.

## Development setup

Follow the offline installation and startup instructions in
[README.md](./README.md). Offline mode is deterministic and needs no provider
credentials.

## Before opening a pull request

~~~bash
source .venv/Scripts/activate
python -m pytest -q backend/tests
python -m compileall -q backend eval scripts data
cd frontend
npm test -- --run
npm run lint
npm run build
npm audit
~~~

Also run git diff --check. Confirm no databases, credentials, real financial
records, build output, or local environment files are included.

## Expectations

- Preserve conservative evidence and treatment invariants.
- Add tests for behavior changes.
- Reflect API changes in the README and acceptance guide.
- Use synthetic data only.
- Document security impact before changing hosts, origins, limits, or
  retention.
- Do not add authentication-looking placeholders; hosted identity must provide
  real tenant authorization and isolation.
- Explain behavior, risk, and testing in each pull request.

Do not disclose vulnerabilities in a public issue. Follow
[SECURITY.md](./SECURITY.md).
