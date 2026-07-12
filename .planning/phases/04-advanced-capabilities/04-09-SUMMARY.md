---
phase: 04-advanced-capabilities
plan: "09"
subsystem: advanced-api
tags: [fastapi, sqlite, authorization, immutable-records, sandbox, sse]
requires:
  - phase: 04-05
    provides: immutable attributed viewpoints and governed calibration
  - phase: 04-06
    provides: immutable experiment and promotion services
  - phase: 04-07
    provides: scoped authorization and fail-closed sandbox admission
  - phase: 04-08
    provides: ownership-safe job/audit projections and scoped advanced SSE
provides:
  - authenticated viewpoint and experiment API resources with safe projections
  - server-persisted experiment ownership for opaque-record authorization
  - strict same-request custom-strategy sandbox submission endpoint
  - advanced router registration on the single shared FastAPI application
affects: [04-10, 04-11, advanced-backend, advanced-frontend]
tech-stack:
  added: []
  patterns:
    - resolve persisted resource scope before returning a hand-built projection
    - derive experiment ownership from request middleware and retain it immutably
    - return a safe unavailable response rather than attempting unbound workflow resume
key-files:
  created: []
  modified:
    - backend/app/advanced/api.py
    - backend/app/main.py
    - backend/app/advanced/experiments.py
    - backend/app/advanced/jobs.py
    - backend/app/operational/migrations.py
    - backend/tests/advanced/test_viewpoints.py
    - backend/tests/advanced/test_experiments.py
    - backend/tests/advanced/test_sandbox.py
key-decisions:
  - "Viewpoint disclosure checks the persisted instrument against a server-derived scope before applying the public projection."
  - "New experiment specifications retain the middleware-resolved owner; legacy ownerless records fail closed at the API boundary."
  - "Custom strategy API calls retain source binding and return only the sandbox validation allowlist."
requirements-completed: [ADV-01, ADV-02, ADV-03, SAFE-01, SAFE-02]
coverage:
  - id: D1
    description: Authenticated viewpoint creation and immutable version reads reject browser authority and cross-scope opaque identifiers.
    requirement: ADV-01
    verification:
      - kind: unit
        ref: cd backend && uv run pytest tests/advanced/test_viewpoints.py tests/advanced/test_experiments.py -q
        status: pass
    human_judgment: false
  - id: D2
    description: Experiment specifications and feedback are strict, append-only API operations with server-derived ownership.
    requirement: ADV-02
    verification:
      - kind: unit
        ref: cd backend && uv run pytest tests/advanced/test_viewpoints.py tests/advanced/test_experiments.py -q
        status: pass
    human_judgment: false
  - id: D3
    description: Promotion, scoped job/SSE behavior, and fail-closed sandbox admission expose no browser execution authority or source data.
    requirement: SAFE-02
    verification:
      - kind: unit
        ref: cd backend && uv run pytest tests/advanced -q
        status: pass
    human_judgment: false
metrics:
  duration: 10m
  completed: 2026-07-12
status: complete
---

# Phase 04 Plan 09: Authenticated Advanced API Summary

**The shared FastAPI host now registers strict advanced research routes that authorize persisted viewpoint and experiment records before returning safe DTOs, while sandbox submissions remain hash-bound and fail closed.**

## Performance

- **Duration:** 10m
- **Started:** 2026-07-12T14:52:50Z
- **Completed:** 2026-07-12T15:02:28Z
- **Tasks:** 2/2
- **Files modified:** 8

## Accomplishments

- Added authenticated viewpoint creation, immutable version reads, calibration access, experiment specification reads/creation, and append-only feedback routes with strict Pydantic inputs and non-enumerating authorization failures.
- Registered the advanced repository, policy, authorization, job, viewpoint, experiment, evolution, and fail-closed sandbox services against the existing operational SQLite database in the sole FastAPI lifespan.
- Added a same-request custom-strategy submission route that validates the source SHA-256 before sandbox admission and returns only safe validation data.
- Kept promotion, job, audit, and SSE projections constrained to the existing server-owned service boundaries; unbound workflow resume now returns safe `503` rather than an internal error.

## Task Commits

1. **Task 1: Implement authorized read/create routes and safe errors for immutable research records** - `b0ec09f` (`test`), `04d8a27` (`feat`)
2. **Task 2: Implement promotion, agent, sandbox, and audit route actions** - `e78585f` (`test`), `3af1096` (`feat`)

## Files Created/Modified

- `backend/app/advanced/api.py` - Strict authenticated advanced router, safe projections, and sandbox admission endpoint.
- `backend/app/main.py` - Shared application lifecycle initialization and router registration.
- `backend/app/advanced/experiments.py` - Immutable server-resolved experiment owner persistence.
- `backend/app/advanced/jobs.py` - Instrument subject binding for advanced job scope checks.
- `backend/app/operational/migrations.py` - Forward SQLite migration for experiment owner lookup.
- `backend/tests/advanced/test_viewpoints.py`, `backend/tests/advanced/test_experiments.py`, `backend/tests/advanced/test_sandbox.py` - API-level authorization, immutable-record, and safe-redaction contracts.

## Verification

```text
cd backend && uv run pytest tests/advanced/test_viewpoints.py tests/advanced/test_experiments.py -q
25 passed

cd backend && uv run pytest tests/advanced/test_evolution.py tests/advanced/test_api_sse.py tests/advanced/test_sandbox.py -q
35 passed

cd backend && uv run pytest tests/advanced -q
72 passed in 26.74s
```

## Decisions Made

- Resource IDs are lookup keys only: the router resolves their persisted subject or owner and checks server-derived scope before projection or mutation.
- The browser cannot submit experiment ownership; the API derives it from `request.state.reviewer_principal` and the new immutable column records it for all subsequent reads.
- The router does not emulate a workflow resume when no server-bound resume adapter is available.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Persisted experiment ownership for authorized opaque-record reads**
- **Found during:** Task 1
- **Issue:** Experiment specifications and their linked runs/feedback lacked a persisted owner, so the API could not meet ownership-before-projection requirements.
- **Fix:** Added a forward SQLite migration, immutable owner persistence in `ExperimentService`, server-derived owner injection in the API, and fail-closed handling for ownerless historical records.
- **Files modified:** `backend/app/operational/migrations.py`, `backend/app/advanced/experiments.py`, `backend/app/advanced/api.py`, `backend/tests/advanced/test_experiments.py`
- **Verification:** Focused viewpoint/experiment API contracts passed; full advanced suite passed with 72 tests.
- **Committed in:** `04d8a27`

**2. [Rule 1 - Bug] Rejected unavailable workflow resume without a 500**
- **Found during:** Task 2
- **Issue:** The existing production job service has no server-bound `resume` method, so the route would raise an attribute error.
- **Fix:** The router now detects the absent adapter and emits a safe `503` before attempting a state transition.
- **Files modified:** `backend/app/advanced/api.py`
- **Verification:** Evolution, API/SSE, and sandbox contracts passed.
- **Committed in:** `3af1096`

**Total deviations:** 2 auto-fixed (1 Rule 2 critical functionality gap, 1 Rule 1 bug).
**Impact on plan:** Both corrections preserve the planned server-owned authorization boundary and do not add execution, broker, monitor, or decision-plan activation paths.

## Known Stubs

None. The default governed experiment runner and sandbox launcher intentionally fail closed when no proven bounded execution adapter is configured; neither exposes a browser-triggered host execution path.

## Issues Encountered

`backend/app/main.py` has pre-existing whole-file Ruff findings outside this plan's edited lifecycle block. Focused advanced lint, compilation, and all targeted tests pass; no unrelated formatting changes were made.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plans 04-10 and 04-11 can consume the authenticated advanced API and existing root SSE boundary without client-side authority fields. `STATE.md` and `ROADMAP.md` were intentionally not modified per the execution request.

## Self-Check: PASSED

Verified all eight listed implementation/test files exist and task commits `b0ec09f`, `04d8a27`, `e78585f`, and `3af1096` are present in git history.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-12*
