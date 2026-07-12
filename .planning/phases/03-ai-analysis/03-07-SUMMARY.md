---
phase: 03-ai-analysis
plan: 07
subsystem: api
tags: [fastapi, sqlite, sse, authorization, analysis]
requires:
  - phase: 03-05
    provides: durable analysis reports, runs, and evidence snapshots
  - phase: 03-06
    provides: immutable lifecycle review and observation-plan transactions
provides:
  - subject-scoped analysis HTTP resources and review actions
  - middleware-derived reviewer attribution for lifecycle decisions
  - server-authorized analysis_progress delivery on the shared SSE stream
affects: [03-08, analysis-ui, sse]
tech-stack:
  added: []
  patterns: [opaque-ID subject authorization, server-bound SSE scopes, middleware reviewer principal]
key-files:
  created: [backend/app/analysis/api.py]
  modified: [backend/app/main.py, backend/app/services/quote_service.py, backend/app/api/intraday.py, backend/app/analysis/repository.py, backend/tests/test_analysis_api.py]
key-decisions:
  - "Analysis route IDs are resolved to their persisted subject before every read or mutation."
  - "Lifecycle confirmation receives only the middleware-resolved opaque reviewer principal; browser identity fields are rejected."
  - "analysis_progress is queued only after run persistence and only for an immutable subscription-time server scope."
patterns-established:
  - "Shared SSE authorization: bind a server-derived scope when subscribing, then filter at the subscriber queue."
  - "Analysis lifecycle API: use fixed server observation defaults and a typed, reviewer-free request body."
requirements-completed: [ANLY-01, ANLY-02, ANLY-03]
coverage:
  - id: D1
    description: Subject-scoped analysis reports, evidence, signal history, and lifecycle review actions.
    requirement: ANLY-03
    verification:
      - kind: integration
        ref: backend/tests/test_analysis_api.py
        status: pass
    human_judgment: false
  - id: D2
    description: Existing FastAPI host retains analysis-menus while registering the governed analysis API.
    requirement: ANLY-01
    verification:
      - kind: integration
        ref: backend/tests/test_analysis_api.py#test_main_registers_analysis_domain_without_replacing_analysis_menus_router
        status: pass
    human_judgment: false
  - id: D3
    description: Persisted analysis progress is isolated by subscription-time subject scope without changing quote fanout.
    requirement: ANLY-02
    verification:
      - kind: integration
        ref: backend/tests/test_analysis_api.py#test_analysis_progress_is_limited_to_the_server_bound_subscriber_scope
        status: pass
    human_judgment: false
duration: 9min
completed: 2026-07-12
status: complete
---

# Phase 03 Plan 07: Secure Analysis API And SSE Summary

**Authenticated analysis reports and lifecycle reviews now enforce persisted subject scope, middleware-owned reviewer identity, and filtered shared-stream progress events.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-07-12T04:51:12Z
- **Completed:** 2026-07-12T05:00:01Z
- **Tasks:** 2/2
- **Files modified:** 6

## Accomplishments

- Added typed `/api/analysis` run, report, evidence, history, review, and outcome resources with fail-closed subject authorization.
- Registered analysis repository, graph, evidence service, lifecycle service, and router in the existing FastAPI lifespan while retaining `/api/analysis-menus`.
- Added bounded `analysis_progress` fanout to the existing intraday SSE stream, filtered by immutable server-derived subject/account scope.

## Task Commits

1. **Task 1: 添加范围授权的分析 HTTP 资源和审核动作** - `2438755` (feat)
2. **Task 2: 在既有主机和 SSE 中装配安全分析状态** - `faf6fa7` (feat)

## Files Created/Modified

- `backend/app/analysis/api.py` - Typed analysis routes, server-only reviewer attribution, and reusable subject scope.
- `backend/app/analysis/repository.py` - Read-only signal and observation-plan subject resolution for opaque-ID authorization.
- `backend/app/main.py` - Analysis domain lifecycle construction, router aliases, scope resolver, and reviewer middleware context.
- `backend/app/services/quote_service.py` - Bounded per-subscriber analysis progress queue and scoped fanout.
- `backend/app/api/intraday.py` - Shared SSE authorization binding and named `analysis_progress` emission.
- `backend/tests/test_analysis_api.py` - API scope, reviewer, router coexistence, and SSE isolation coverage.

## Decisions Made

- Opaque report, signal, review, and observation-plan IDs are never authorization credentials: each is resolved back to its persisted subject before exposure or mutation.
- The lifecycle service accepts the principal supplied from authenticated request state; no cookie, header, or request-body identity fallback exists in the analysis router.
- Instrument scope is public within the authenticated single-user host, while account subjects must match existing server-side accounts.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Added read-only subject resolution for signals and observation plans**
- **Found during:** Task 1
- **Issue:** Repository lookups for opaque signal and plan IDs did not expose their owning subject, so history/outcome authorization could not fail closed.
- **Fix:** Added parameterized read-only repository lookups and required their subject scope before these endpoints act.
- **Files modified:** `backend/app/analysis/repository.py`, `backend/app/analysis/api.py`
- **Verification:** `uv run pytest tests/test_analysis_api.py tests/test_analysis_lifecycle.py -q`
- **Committed in:** `2438755`

**2. [Rule 1 - Bug] Bound SSE analysis scope inside the stream endpoint**
- **Found during:** Task 2
- **Issue:** Initial implementation placed the scope binding in the status endpoint, leaving the stream without its local scope.
- **Fix:** Moved binding to `/api/intraday/stream` before subscription creation.
- **Files modified:** `backend/app/api/intraday.py`
- **Verification:** `uv run pytest tests/test_analysis_api.py tests/test_analysis_graph.py tests/test_analysis_service.py -q`
- **Committed in:** `faf6fa7`

**Total deviations:** 2 auto-fixed (1 Rule 2, 1 Rule 1).

## TDD Gate Compliance

The required RED state was supplied by the existing Wave 0 API contract committed in Plan 03-02. This plan recorded GREEN feature commits after confirming `ModuleNotFoundError` for `app.analysis.api`; no new standalone `test(03-07)` commit was needed.

## Issues Encountered

- Targeted `ruff` on the touched modules reports pre-existing repository-wide lint findings in `main.py`, `intraday.py`, and `quote_service.py`. New API-file lint findings were fixed; no unrelated formatting was changed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 03-08 can consume the stable `/api/analysis` resource paths and the single `analysis_progress` SSE event.
- Successful-run lifecycle proposal wiring remains intentionally deferred to Plan 03-09.

## Self-Check: PASSED

- FOUND: `.planning/phases/03-ai-analysis/03-07-SUMMARY.md`
- FOUND: `2438755`
- FOUND: `faf6fa7`
