# SmartWealth Frontend

The SmartWealth frontend is a React 19 and Vite 8 single-page dashboard for
validated ledger upload, live audit progress, human review, evidence inspection,
evaluation results, and final draft reporting.

Start with the repository [README](../README.md) for full installation,
architecture, backend configuration, security boundaries, and end-to-end usage.

## Git Bash commands

```bash
cd frontend
npm ci
npm run dev
```

The development server normally opens at `http://localhost:5173`.

Configure a different API location by copying `.env.example` to an ignored
`.env` file and changing `VITE_API_BASE_URL`.

## Verification

```bash
npm test -- --run
npm run lint
npm run build
npm audit
```

## Main areas

- `src/components/UploadZone.jsx`: CSV selection, validation, preview, and
  processing consent
- `src/components/Dashboard.jsx`: lifecycle, metrics, report, and panel layout
- `src/components/AuditorPanel.jsx`: human clarification
- `src/components/RunTimeline.jsx`: durable event and override history
- `src/components/EvidenceDrawer.jsx`: evidence provenance
- `src/components/EvaluationDashboard.jsx`: evaluation evidence
- `src/store/useRunStore.js`: Zustand state, run lifecycle, and SSE recovery
- `src/api/client.js`: validated API URL, JSON requests, and event streaming

The frontend stores only recovery-safe run metadata in session storage. It does
not store ledger transactions, evidence, reports, or an API credential.
