---
phase: 03-ai-analysis
plan: 03
subsystem: frontend-transport
tags: [typescript, react-query, sse, playwright, analysis]
requires:
  - phase: 03-02
    provides: Wave 0 analysis domain contracts and approved Phase 3 constraints.
provides:
  - Typed browser API contracts for server-owned analysis reports, evidence, runs, and lifecycle review actions.
  - Subject-isolated analysis query keys and a narrow root-SSE invalidation path.
  - Fixture-backed, bounded RED browser contracts for the later evidence-first UI.
tech-stack:
  added: []
  patterns: [typed-request-client, subject-scoped-query-keys, shared-eventsource, fixture-red-contracts]
key-files:
  created:
    - frontend/e2e/phase3-ai-analysis.spec.ts
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/lib/queryKeys.ts
    - frontend/src/lib/useQuoteStream.ts
decisions:
  - "Analysis client actions carry only bounded subject identifiers or server-issued review references; they never send reviewer, provenance, grade, or lifecycle authority."
  - "Every analysis cache key includes the subject so persisted progress invalidates only the affected object's panels."
  - "Phase 3 browser scenarios remain per-case expected failures until 03-08 removes the markers after delivering the UI."
metrics:
  duration: 7m
  completed: 2026-07-12
  tasks: 2
  files: 4
status: complete
---

# Phase 03 Plan 03: Frontend Analysis Transport Summary

**Typed, subject-isolated analysis transport with coarse root-SSE invalidation and fixture-backed evidence-first RED browser contracts.**

## Accomplishments

- Added strict TypeScript projections and unified `request`-based methods for analysis runs, immutable reports, evidence, signal history, and server-authorized confirm/reject actions.
- Added independent subject/resource `QK` factories so report, evidence, signal history, and run panels cannot clear one another or another subject's cache.
- Reused the sole intraday `EventSource` to parse only coarse `analysis_progress` identifiers and invalidate affected subject analysis keys.
- Created server-projection-only Playwright fixtures with explicit failures for unhandled `/api/` requests and three bounded expected-failure UI scenarios for 03-08.

## Verification

- `cd frontend && pnpm run build` - passed.
- `cd frontend && pnpm exec playwright test e2e/phase3-ai-analysis.spec.ts --project=desktop-chromium` - passed with 3 expected-failure scenarios; these intentionally remain RED until 03-08 implements the workspace UI.
- `git diff --check` - passed.

## Task Commits

1. **Task 1 RED: Add analysis browser contracts** - `aba71d9` (`test`)
2. **Task 1 GREEN: Add typed analysis client contracts and isolated query keys** - `8a29cd2` (`feat`)
3. **Task 2: Reuse root SSE for narrow analysis cache invalidation** - `a9d2b14` (`feat`)

## Decisions Made

- Lifecycle confirmation sends only the server-issued review ID and an allowed observation window; reject sends only the review ID.
- SSE payload parsing deliberately ignores all values except valid subject identifiers needed for cache targeting; no token, prompt, evidence excerpt, or lifecycle mutation is rendered or persisted by the client.
- The RED fixture file is the same file 03-08 must convert to GREEN, preventing test-contract drift.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] Restored missing analysis type declarations before build**
- **Found during:** Task 1 verification
- **Issue:** API methods referenced analysis types before their declarations had landed in the source file, causing TypeScript build failures.
- **Fix:** Added the server-owned TypeScript projection interfaces adjacent to existing API models, then rebuilt successfully.
- **Files modified:** `frontend/src/lib/api.ts`
- **Commit:** `8a29cd2`

**2. [Rule 3 - Blocking issue] Bounded the keyboard RED locator timeout**
- **Found during:** Task 1 RED verification
- **Issue:** A missing pre-03-08 tab waited for Playwright's 30-second default and turned a bounded expected failure into a test timeout.
- **Fix:** Set a one-second locator timeout so the expected-failure contract completes deterministically.
- **Files modified:** `frontend/e2e/phase3-ai-analysis.spec.ts`
- **Commit:** `aba71d9`

## Known Stubs

- `frontend/e2e/phase3-ai-analysis.spec.ts:56`, `:66`, `:76` - UI assertions are intentionally marked `test.fail` until 03-08 delivers `AnalysisWorkspace` and its panels. The fixtures are real server-owned projections and do not block this plan's transport-contract objective.

## Residual Risks

- Browser verification covers fixture contracts only because the analysis workspace components and backend analysis router are scheduled in later plans. The expected-failure markers must be removed and the same scenarios turned GREEN in 03-08.

## Self-Check: PASSED

- Verified `frontend/src/lib/api.ts`, `frontend/src/lib/queryKeys.ts`, `frontend/src/lib/useQuoteStream.ts`, and `frontend/e2e/phase3-ai-analysis.spec.ts` exist.
- Verified task commits `aba71d9`, `8a29cd2`, and `a9d2b14` exist in Git history.
