---
phase: 04-advanced-capabilities
plan: "11"
subsystem: governed-advanced-research-workspace
tags: [fastapi, react, tanstack-query, playwright, authorization, sandbox]
requires:
  - phase: 04-10
    provides: typed advanced client conventions and server-scoped progress contracts
provides:
  - server-authorized experiment, candidate, gate, and sandbox validation projections
  - typed Backtest experiment, feedback, promotion, and sandbox panels
  - focused browser proof for frozen runs, gates, dialog behavior, safety, and responsive controls
affects: [advanced-backend, advanced-frontend, backtest, ADV-02, ADV-03, SAFE-01, SAFE-02]
tech-stack:
  added: []
  patterns:
    - explicit allowlisted API projections instead of exposing service records
    - server-derived principal and research-asset authorization before experiment and candidate reads/actions
    - Backtest panels consume typed TanStack Query resources and never use direct fetch or browser-held authority
key-files:
  created:
    - frontend/src/components/advanced/AdvancedResearchPanels.tsx
  modified:
    - backend/app/advanced/api.py
    - backend/app/advanced/evolution.py
    - backend/app/advanced/experiments.py
    - backend/app/advanced/projections.py
    - backend/tests/advanced/test_evolution.py
    - frontend/src/lib/api.ts
    - frontend/src/lib/queryKeys.ts
    - frontend/src/pages/Backtest.tsx
    - frontend/src/pages/backtest/StrategyBacktest.tsx
    - frontend/e2e/phase4-advanced-capabilities.spec.ts
decisions:
  - "Experiment and candidate lists require a server-resolved principal plus a server-authorized research asset; clients never submit ownership, eligibility, or gate authority."
  - "Backtest renders advanced research below the existing research library and experiment comparison, retaining the single application shell."
  - "Sandbox submission is typed as one source-and-contract request; only source hashes, safe reasons, and opaque audit references are rendered."
metrics:
  duration: 28m
  completed: 2026-07-12
status: complete
---

# Phase 04 Plan 11: Governed Advanced Research Workspace Summary

**Backtest now supports immutable experiment records, independent promotion gates, registered-only approval, and constrained custom-strategy sandbox review through typed server-authorized projections.**

## Accomplishments

- Added narrow advanced routes for experiment listing, run and retry actions, append-only feedback, candidate and five-gate reads, promotion, and sandbox validation history.
- Added deny-by-default projections for immutable specifications, runs, feedback, candidates, and sandbox validation results. They omit raw source, tokens, paths, stack traces, and diagnostics.
- Added a compositional Backtest module with bounded native forms, immutable manifests, feedback eligibility controls, five visible gate rows, focus-managed promotion confirmation, and sandbox source clearing after submission.
- Composed the module after the existing strategy research library and experiment comparison without adding a route, shell, direct fetch, or parallel stream.
- Converted the deferred Phase 4 Backtest browser contracts into executable desktop coverage, including responsive geometry checks for desktop, tablet, and mobile widths.

## Task Commits

1. **Tasks 1 and 2: Authorized advanced API projections and Backtest workspace panels** - `3cc081c` (`feat`)

## Verification

```text
cd backend && uv run pytest tests/advanced -q
73 passed

cd frontend && pnpm run build
passed

cd frontend && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts
8 passed, 6 skipped
```

The six skips are the existing non-desktop project copies; each responsive viewport is exercised inside the desktop Chromium owner scenario at 1440px, 1024px, and 375px.

## Decisions Made

- Experiment specifications, runs, retries, feedback, candidates, and promotion operations resolve server identity and research-asset eligibility before projection or mutation.
- Candidate gates remain five independent rows; no ranking or aggregate score can enable promotion.
- Promotion returns only a registered research strategy outcome and has no activation, monitoring, decision-plan, broker, or market-execution control.

## Deviations from Plan

### User-approved Scope Extension

**1. Extend the advanced router and typed client for missing governed research operations**
- **Found during:** Checkpoint continuation before Task 1.
- **Issue:** Plan 09 exposed sandbox submission and limited advanced reads, but did not expose the authorized experiment lists/runs/retries, candidate gates, or sandbox validation history required for a real Plan 11 Backtest UI.
- **Fix:** Added minimal server-authorized, explicit-allowlist projections and constrained actions. Identity and research-asset authorization remain server-derived; DTOs exclude source, credentials, raw diagnostics, paths, and tokens.
- **Files modified:** Advanced API, service, projection, typed client, cache keys, and focused tests listed above.
- **Commit:** `3cc081c`.

## Known Stubs

None. Changed UI data originates from typed advanced API projections or explicit loading, empty, disabled, and failure states.

## Self-Check: PASSED

- Verified `frontend/src/components/advanced/AdvancedResearchPanels.tsx` and this summary exist.
- Verified task commit `3cc081c` exists in history.
- `STATE.md` and `ROADMAP.md` were intentionally not modified per the continuation request.
