---
phase: 04-advanced-capabilities
plan: "10"
subsystem: advanced-analysis-ui
tags: [fastapi, react-query, sse, authorization, playwright]
requires:
  - phase: 04-09
    provides: authenticated advanced projections and scoped SSE delivery
provides:
  - server-session-bound advanced viewpoint reads and job starts
  - typed advanced API DTOs and object-scoped cache keys
  - strict root-SSE advanced-progress cache updates
  - immutable viewpoint and safe task display inside AnalysisWorkspace
affects: [04-11, advanced-backend, advanced-frontend, analysis-workspace]
tech-stack:
  added: []
  patterns:
    - derive task authorization and scope from the server session
    - reject unknown advanced-progress event fields before cache mutation
    - retain display subject versus server request subject mapping
key-files:
  created:
    - frontend/src/components/advanced/ViewpointPanel.tsx
  modified:
    - backend/app/advanced/api.py
    - backend/app/advanced/jobs.py
    - backend/app/advanced/authorization.py
    - backend/app/advanced/repository.py
    - backend/app/advanced/viewpoints.py
    - backend/app/advanced/projections.py
    - backend/app/main.py
    - backend/tests/advanced/test_api_sse.py
    - backend/tests/advanced/test_viewpoints.py
    - frontend/src/lib/api.ts
    - frontend/src/lib/queryKeys.ts
    - frontend/src/lib/useQuoteStream.ts
    - frontend/src/components/analysis/AnalysisWorkspace.tsx
    - frontend/e2e/phase4-advanced-capabilities.spec.ts
decisions:
  - "The browser starts an advanced task through an object path and literal task type only; the server derives authorization, market, scope, and idempotency data."
  - "Advanced SSE events are accepted only as strict server-issued progress projections and update cache entries for the matching object/job/audit."
metrics:
  duration: 15m
  completed: 2026-07-12
status: complete
---

# Phase 04 Plan 10: Advanced Analysis UI Summary

**Session-authorized advanced research now renders immutable viewpoints, calibration uncertainty, and scoped task/audit status in the existing object analysis workspace without browser-held authority.**

## Accomplishments

- Added a server-session-bound advanced job start route and an authorized instrument viewpoint list route. Browser payloads contain only the object identifier and an allowlisted task type.
- Added exact advanced API DTOs, resource-specific Query keys, and a strict root-owned `advanced_progress` parser that rejects unknown fields, malformed identifiers, unsafe stages, and client scope fields.
- Added `ViewpointPanel` to `AnalysisWorkspace` with immutable version lineage, frozen evaluation metadata, calibration buckets, explicit unevaluable/insufficient states, and safe job/audit disclosure.
- Updated browser fixtures to validate the real object-local view and rejection behavior while retaining 04-11 Backtest scenarios as expected failures.

## Task Commits

1. **Task 1: Add typed advanced API methods and granular cache ownership** - `97594c4` (`test` RED), `3ebc788` (`feat`)
2. **Task 2: Render immutable viewpoints and task safety states in object-local analysis** - `f1f0e00` (`feat`)

## Verification

```text
cd backend && uv run pytest tests/advanced -q
73 passed

cd frontend && pnpm run build
passed

cd frontend && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts --project=desktop-chromium
7 passed
```

The browser suite intentionally retains five `test.fail` contracts for Plan 04-11's Backtest experiment, promotion, sandbox, and responsive controls. Its completed Task 1/Task 2 scenarios execute as regular passing tests.

## Decisions Made

- The server creates the short-lived opaque advanced authorization record after resolving the authenticated principal and allowed object; authorization tokens and market scope never cross the browser boundary.
- The advanced job policy wildcard is internal-only and is constrained by the request-scoped server resolver before a job is created; it is not a client-exposed allowlist.
- The Analysis workspace continues to map `stock`/`portfolio` display subjects to `instrument`/`account` request subjects, preventing the UI from inventing API authority.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Add server-session-bound list/read and job-start endpoints**
- **Found during:** Task 1
- **Issue:** Existing advanced job creation required a browser-supplied authorization token, market, instrument, and idempotency key; there was no authorized instrument-scoped viewpoint list endpoint. This violated SAFE-01 and the approved Option A boundary.
- **Fix:** Added a constrained object-path job start request, server-created short-lived authorization, instrument-scoped immutable viewpoint listing, explicit safe projections, and API contracts that reject injected token/scope fields.
- **Files modified:** `backend/app/advanced/api.py`, `backend/app/advanced/jobs.py`, `backend/app/advanced/authorization.py`, `backend/app/advanced/repository.py`, `backend/app/advanced/viewpoints.py`, `backend/app/advanced/projections.py`, `backend/app/main.py`, and focused advanced tests.
- **Verification:** 73 advanced backend tests passed; typed browser task-start assertions passed.
- **Committed in:** `3ebc788`

**Total deviations:** 1 auto-fixed Rule 2 security/correctness requirement.

## Known Stubs

None. All viewpoint, calibration, job, and audit values shown by the new panel are typed server projections or explicit loading/empty/error states.

## Self-Check: PASSED

- Verified `frontend/src/components/advanced/ViewpointPanel.tsx` and this summary exist.
- Verified task commits `97594c4`, `3ebc788`, and `f1f0e00` exist in history.
- `STATE.md` and `ROADMAP.md` were intentionally not modified per the execution request.
