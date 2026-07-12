---
phase: 04-advanced-capabilities
plan: "12"
subsystem: advanced-production-host
tags: [fastapi, sqlite, immutable-facts, multiprocessing, resource-limits]
requires:
  - phase: 04-05
    provides: immutable viewpoint evaluations and confidence calibration
  - phase: 04-06
    provides: immutable experiment runs and feedback eligibility
  - phase: 04-09
    provides: authenticated advanced API and shared lifespan registration
provides:
  - deterministic authorized projection of latest immutable viewpoint evaluations
  - production-lifecycle governed experiment execution with persisted resource limits
  - host-lifespan integration proof for evaluation disclosure and experiment eligibility
affects: [advanced-backend, ADV-01, ADV-02, ADV-03]
tech-stack:
  added: []
  patterns:
    - correlated SQLite latest-fact projection with created-at and ID tie-breaking
    - parent-owned spawned worker with resource-limit verification and process-group reaping
key-files:
  created:
    - backend/app/advanced/governed_runner.py
    - backend/tests/advanced/test_production_host.py
  modified:
    - backend/app/advanced/repository.py
    - backend/app/advanced/viewpoints.py
    - backend/app/main.py
key-decisions:
  - "Viewpoint reads select the latest immutable evaluation by created_at then stable ID, never response ordering."
  - "Experiment execution uses a spawned, parent-owned process group and returns only bounded manifest metadata."
requirements-completed: [ADV-01, ADV-02, ADV-03]
coverage:
  - id: D1
    description: Authorized production viewpoint routes project the newest immutable evaluated or unevaluable record without disclosing evidence content.
    requirement: ADV-01
    verification:
      - kind: integration
        ref: backend/tests/advanced/test_production_host.py#test_authenticated_main_host_projects_latest_immutable_viewpoint_evaluation
        status: pass
    human_judgment: false
  - id: D2
    description: Governed experiment runs persist applied budgets, admit feedback only after completion, and terminate blocked workers.
    requirement: ADV-02
    verification:
      - kind: integration
        ref: backend/tests/advanced/test_production_host.py#test_governed_runner_persists_applied_limits_and_completed_feedback
        status: pass
      - kind: integration
        ref: backend/tests/advanced/test_production_host.py#test_governed_runner_reaps_blocked_work_and_rejects_feedback
        status: pass
    human_judgment: false
metrics:
  duration: 21m
  completed: 2026-07-12
status: complete
---

# Phase 04 Plan 12: Production Host Completion Summary

**Authorized immutable viewpoint outcomes and bounded experiment execution now run through the real FastAPI lifespan with durable, safe terminal evidence.**

## Performance

- **Duration:** 21m
- **Started:** 2026-07-12T18:42:37Z
- **Completed:** 2026-07-12T19:03:37Z
- **Tasks:** 2/2
- **Files modified:** 6

## Accomplishments

- Added deterministic latest-evaluation projection from the append-only SQLite ledger to the existing authorized viewpoint routes.
- Preserved frozen evaluation window and benchmark metadata while exposing only the allowlisted status, reason, and relative return.
- Replaced the production unavailable experiment runner with a spawned governed worker boundary that applies CPU, address-space, wall-clock, and output budgets.
- Persisted completed and constrained terminal records through the existing immutable experiment service, retaining feedback eligibility only for completed runs.
- Added real-lifespan FastAPI coverage for scoped evaluation disclosure and worker-backed terminal experiment paths.

## Task Commits

1. **Task 1: Project latest immutable viewpoint evaluations through authorized records** - `6eb3390` (`feat`)
2. **Task 2: Provide and lifecycle-wire the bounded governed experiment runner** - `709a559` (`feat`)

## Files Created/Modified

- `backend/app/advanced/repository.py` - Deterministic latest immutable evaluation read.
- `backend/app/advanced/viewpoints.py` - Evaluation projection on service DTOs.
- `backend/app/advanced/governed_runner.py` - Spawned governed worker, resource enforcement, terminal result sanitization, and StrategyBacktest adapter.
- `backend/app/main.py` - Lifecycle construction of the server-owned governed experiment runner.
- `backend/tests/advanced/test_production_host.py` - Real host, scoped disclosure, successful-run, and blocked-worker integration coverage.

## Verification

```text
cd backend && timeout 60s uv run pytest tests/advanced/test_viewpoints.py tests/advanced/test_experiments.py tests/advanced/test_evolution.py tests/advanced/test_production_host.py -q
37 passed, 3 warnings

cd backend && uv run ruff check app/advanced/governed_runner.py app/advanced/experiments.py tests/advanced/test_production_host.py
All checks passed

cd backend && uv run python -m compileall -q app/advanced/governed_runner.py app/advanced/experiments.py
passed
```

## Decisions Made

- Newest evaluation selection is SQL-deterministic across equal timestamps, so older immutable facts cannot become current by response ordering.
- Process spawning is used instead of in-process cancellation so a blocked experiment has a parent-controlled termination boundary.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Avoided a multi-threaded fork deadlock while collecting worker evidence**
- **Found during:** Task 2
- **Issue:** Forking after the FastAPI TestClient thread had started could inherit a locked queue state and prevent a finished worker from publishing terminal evidence.
- **Fix:** Used the `spawn` multiprocessing context and fail-closed worker startup handling.
- **Files modified:** `backend/app/advanced/governed_runner.py`
- **Verification:** Successful and blocked-worker integration tests pass.
- **Committed in:** `709a559`

**Total deviations:** 1 auto-fixed (1 Rule 1 bug).
**Impact on plan:** The fix strengthens the parent-controlled boundary and never falls back to host-process execution.

## Issues Encountered

`backend/app/main.py` has pre-existing whole-file Ruff findings outside the lifecycle block changed by this plan. Targeted runner, experiment, and host checks pass; no unrelated formatting changes were made.

## Known Stubs

None. Worker results use persisted governed manifests and bounded metadata; no empty value is rendered as a completed research result.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The production host now provides real evaluation and experiment paths for the remaining advanced-capability verification work.

## Self-Check: PASSED

Verified `backend/app/advanced/governed_runner.py` and `backend/tests/advanced/test_production_host.py` exist, and task commits `6eb3390` and `709a559` are present in git history.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-12*
