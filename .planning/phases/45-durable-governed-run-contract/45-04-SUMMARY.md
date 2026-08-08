---
phase: 45-durable-governed-run-contract
plan: 04
subsystem: api
tags: [fastapi, pydantic, sqlite, research-only, security]

# Dependency graph
requires:
  - phase: 45-durable-governed-run-contract
    provides: immutable run snapshots, append-only candidate/event facts, guarded lifecycle, token fencing, bounded progress, and worker adapter
provides:
  - typed principal-scoped Alpha run create/inspect/replay/retry/cancel/history/progress API
  - safe candidate/event/progress projections and strict bounded DTO contracts
  - complete Phase 45 AST/import/call and runtime research-only boundary guard
affects: [phase-46, phase-47, phase-48, phase-49, phase-50]

# Actuals (#2632)
actuals:
  tokens: 18775
  tasks: 2
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns: [typed FastAPI routes via app.state service, strict Pydantic extra-forbid DTOs, deny-by-default projections, AST/import/call boundary scans, raising-fake runtime guards]

key-files:
  created: [backend/tests/test_phase45_guard.py]
  modified: [backend/app/api/research_alpha.py, backend/app/research/run_schemas.py, backend/app/research/projections.py, backend/app/research/run_service.py, backend/tests/api/test_run_api.py]

key-decisions:
  - "Keep the existing shared app.state.research_run_service and ResearchRepository wiring from Plan 45-01; this plan verifies and consumes that seam without adding a second repository or database."
  - "Map same-principal stale lifecycle requests and retry idempotency conflicts to explicit HTTP 409 while preserving one 404 boundary for unknown and cross-principal run IDs."
  - "Treat the optional post-commit publisher as a legitimate wake-up seam, not an execution collaborator; the runtime guard injects raising fakes only at worker bookkeeping boundaries."

patterns-established:
  - "All Alpha API reads and writes resolve the host principal, delegate to ResearchRunService, and project only allowlisted durable fields."
  - "History endpoints use bounded server-side pagination and monotonic durable sequence/ordinal ordering."
  - "The Phase 45 module graph is mechanically checked for prohibited execution/provider/evaluator/OOS/promotion/queue/database imports and calls, with module/symbol diagnostics."

requirements-completed: [AF-REQ-10, AF-REQ-16]

coverage:
  - id: D1
    description: "Typed principal-scoped create, inspect, replay, retry, cancel, event history, candidate history, and four-counter progress API"
    requirement: AF-REQ-10
    verification:
      - kind: integration
        ref: "backend/.venv/bin/pytest tests/api/test_run_api.py -k 'api or history or progress or retry or cancel or principal or cross_principal or redaction or strict' -q"
        status: pass
    human_judgment: false
  - id: D2
    description: "Complete Phase 45 module-graph research-only boundary and runtime no-execution guard"
    requirement: AF-REQ-16
    verification:
      - kind: integration
        ref: "backend/.venv/bin/pytest tests/test_phase45_guard.py -q"
        status: pass
      - kind: integration
        ref: "backend/.venv/bin/pytest tests/api/test_run_api.py -k 'principal or cross_principal or progress or retry or cancel' -q"
        status: pass
    human_judgment: false

# Metrics
duration: 6min
completed: 2026-08-08
status: complete
---

# Phase 45 Plan 04: Durable Alpha API and Research-Only Boundary Summary

**Typed principal-scoped durable run operations with safe projections, explicit lifecycle conflicts, and a complete no-execution module-graph guard.**

## Performance

- **Duration:** 6 minutes
- **Started:** 2026-08-08T15:23:30Z
- **Completed:** 2026-08-08T15:29:53Z
- **Tasks:** 2 completed
- **Files modified/created by this plan:** 6

## Accomplishments

- Exposed strict typed create/get/replay/retry/cancel/event-history/candidate-history/progress operations through the shared `ResearchRunService` app-state seam, with host-resolved principal scoping, bounded query parameters, safe 404 behavior, and no route-level SQL.
- Added allowlisted candidate/event/progress projections and strict retry/cancel/progress/candidate DTOs; public responses omit principal identity, raw payloads, paths, diagnostics, policy internals, and attempt-token plaintext.
- Added explicit HTTP conflict handling: stale same-principal cancellation and retry idempotency conflicts return 409, while unknown and cross-principal IDs remain indistinguishable 404s.
- Added a 542-line guard covering the Phase 45 migration/research/API graph, prohibited imports/calls/attributes, second-database and external-queue tokens, browser/SSE/Watchlist surface, runtime raising fakes, cross-principal boundaries, checkpoint bounds, token redaction, and app wiring.

## Task Commits

1. **Task 45-04-01: Expose typed principal-scoped history, progress, retry, and cancel routes** - `26b2b60` (feat)
2. **Task 45-04-02: Lock the complete Phase 45 module graph to the research-only boundary** - `0befdd5` (test)
3. **Rule 2 follow-up: map stale lifecycle conflicts to HTTP 409** - `844c7e4` (fix)

The Rule 2 follow-up is included because the acceptance contract requires explicit 409 conflict responses for stale lifecycle requests and retry idempotency conflicts; it touched only Task 45-04-01 declared files.

## Files Created/Modified

- `backend/app/api/research_alpha.py` - typed Alpha routes, principal resolver, bounded queries, safe 404/409/503 mapping.
- `backend/app/research/run_schemas.py` - strict retry/cancel/progress/candidate/event/progress DTO contracts.
- `backend/app/research/projections.py` - deny-by-default run, event, candidate, replay, and progress projections.
- `backend/app/research/run_service.py` - stale cancellation fencing at the service boundary.
- `backend/tests/api/test_run_api.py` - API status, redaction, history, progress, retry/cancel idempotency, principal, and conflict coverage.
- `backend/tests/test_phase45_guard.py` - complete static/runtime research-only boundary guard.
- `backend/app/main.py` - unchanged by this plan; existing shared `ResearchRepository`/`ResearchRunService` app-state initialization and `research_alpha.router` include from Plan 45-01 were verified by the guard.

## Verification Evidence

All plan-focused verification commands passed after the final fix:

```text
cd backend && .venv/bin/pytest tests/api/test_run_api.py -k 'api or history or progress or retry or cancel or principal or cross_principal or redaction or strict' -q
→ 36 passed

cd backend && .venv/bin/pytest tests/test_phase45_guard.py -q
→ 52 passed

cd backend && .venv/bin/pytest tests/api/test_run_api.py -k 'principal or cross_principal or progress or retry or cancel' -q
→ 27 passed, 9 deselected
```

The bare `pytest` executable was not on PATH; the repository-managed `backend/.venv/bin/pytest` ran the exact requested selections. No formatter, linter, broad suite, provider call, evaluator, OOS, promotion, queue, browser, or SSE command was run.

## Decisions Made

- Reused the existing shared `ResearchRepository`/`ResearchRunService` in `app.state`; no second database or in-memory authority was introduced.
- Preserved one fail-closed 404 boundary for unknown and cross-principal IDs across reads and writes; same-principal stale lifecycle conflicts are explicit 409 responses.
- Kept the optional post-commit publisher semantics intact. The runtime guard does not misclassify that notification seam as execution authority and uses raising fakes for worker-side optional bookkeeping.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical security/error mapping] Explicit stale lifecycle and retry conflict responses**
- **Found during:** Task 45-04-01 focused acceptance review
- **Issue:** A stale same-principal cancel could be returned as the unchanged run (HTTP 200), and a changed retry request reusing an idempotency key could escape as an unhandled server error instead of an explicit conflict.
- **Fix:** Added service-side stale-version fencing, route ownership precheck, HTTP 409 mappings for stale lifecycle/idempotency conflicts, and regression tests. Unknown/cross-principal requests still return 404.
- **Files modified:** `backend/app/api/research_alpha.py`, `backend/app/research/run_service.py`, `backend/tests/api/test_run_api.py`
- **Verification:** API focused selection passed 36 tests; principal/lifecycle selection passed 27 tests.
- **Committed in:** `844c7e4`

**2. [Rule 2 - Guard correctness] Avoided treating the allowed publisher wake-up callback as an execution collaborator**
- **Found during:** Task 45-04-02 guard execution
- **Issue:** The initial runtime guard injected a raising fake into `ResearchRunService.publisher`, but D-05 explicitly permits post-commit publisher notification; the test therefore failed on the required callback rather than an execution escalation.
- **Fix:** The service runtime fixture now uses no optional publisher, while the worker adapter test retains a raising fake for optional JobStore bookkeeping. This keeps the guard focused on prohibited execution collaborators without weakening the static boundary checks.
- **Files modified:** `backend/tests/test_phase45_guard.py`
- **Verification:** Guard passed all 52 tests.
- **Committed in:** `0befdd5`

**Total deviations:** 2 auto-fixed (Rule 2)
**Impact on plan:** Both fixes tightened explicit conflict/error and security-boundary acceptance without adding runtime dependencies or out-of-scope surfaces.

## Issues Encountered

- `pytest` was not installed on the shell PATH. The project-managed `backend/.venv/bin/pytest` was available and executed all exact focused selections successfully.
- `.planning/STATE.md` had a pre-existing orchestrator modification and was intentionally left for the required state-update/final metadata step; no unrelated files were staged.

## Threat Model Mitigations

- **T-45-08:** Public projections and strict DTOs allowlist only bounded durable state; token/plaintext, principal, raw paths, payloads, prompts, policy internals, and diagnostics are omitted.
- **T-45-09:** AST/import/call/attribute scans plus runtime raising-fake tests cover the complete Phase 45-owned research/API graph and reject execution/provider/evaluator/OOS/promotion/queue/second-database escalation.
- **T-45-10:** `extra="forbid"`, server-owned identity/version/status fields, bounded pagination, and explicit 409 conflict mapping protect retry/cancel/progress inputs.
- **T-45-11:** Event and candidate reads are bounded and ordered by durable server sequence/attempt ordinal.
- **T-45-12:** Every API operation resolves the host principal and scopes service/repository access; unknown and cross-principal paths share the same 404 boundary.

## Next Phase Readiness

Phase 46 can consume one typed durable seam for run state, candidate/event history, retry/cancel, and four progress counters. The guard establishes that later additions must remain research-only and cannot import or call execution/provider/evaluator/OOS/promotion/queue collaborators. Browser/SSE workbench transport remains intentionally deferred to Phase 50.

## Self-Check: PASSED

- `backend/tests/test_phase45_guard.py` exists and its 52 focused tests pass.
- Task commits `26b2b60`, `0befdd5`, and `844c7e4` exist in git history.
- All declared implementation/test files are committed; no generated untracked files remain.
- The required summary artifact was written at `.planning/phases/45-durable-governed-run-contract/45-04-SUMMARY.md`.

---
*Phase: 45-durable-governed-run-contract*
*Completed: 2026-08-08*
