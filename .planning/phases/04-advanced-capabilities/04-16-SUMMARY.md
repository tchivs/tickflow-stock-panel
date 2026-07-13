---
phase: 04-advanced-capabilities
plan: "16"
subsystem: advanced-viewpoints
tags: [fastapi, sqlite, governed-data, immutable-facts, authorization]
requires:
  - phase: 04-05
    provides: immutable viewpoint lineage, frozen evaluation plans, and calibration ledger
  - phase: 04-12
    provides: authorized latest-evaluation projections and the production lifespan host
provides:
  - lifecycle-owned governed historical viewpoint evaluation inputs
  - scoped immutable viewpoint revision, correction, and evaluation actions
  - production-host proof of material changes, corrections, and unevaluable outcomes
affects: [ADV-01, advanced-api, advanced-research]
tech-stack:
  added: []
  patterns:
    - evaluation inputs are derived only from frozen plans and the governed Kline repository
    - mutation routes reauthorize the persisted instrument before appending immutable facts
key-files:
  created:
    - .planning/phases/04-advanced-capabilities/04-16-SUMMARY.md
  modified:
    - backend/app/main.py
    - backend/app/advanced/viewpoints.py
    - backend/app/advanced/api.py
    - backend/app/advanced/schemas.py
    - backend/tests/advanced/test_viewpoints.py
    - backend/tests/advanced/test_production_host.py
key-decisions:
  - "Viewpoint evaluation reads frozen historical windows through KlineRepository and never QuoteService or browser inputs."
  - "Evaluation routes accept an empty strict body and reload the authorized immutable version after append before projecting it."
patterns-established:
  - "Lifecycle collaborator: domain services receive only governed evaluation input facts, not repository or request authority."
  - "Persisted-object authorization: resolve a version or viewpoint's instrument before every advanced mutation."
requirements-completed: [ADV-01]
coverage:
  - id: D1
    description: Authorized users append immutable material revisions and corrections without client-provided scope or identity authority.
    requirement: ADV-01
    verification:
      - kind: integration
        ref: backend/tests/advanced/test_production_host.py#test_authenticated_main_host_projects_latest_immutable_viewpoint_evaluation
        status: pass
    human_judgment: false
  - id: D2
    description: Governed historical inputs append evaluated or explicit unevaluable viewpoint facts and retain deterministic calibration inputs.
    requirement: ADV-01
    verification:
      - kind: integration
        ref: cd backend && timeout 60s uv run pytest tests/advanced/test_viewpoints.py tests/advanced/test_production_host.py -q
        status: pass
    human_judgment: false
metrics:
  duration: 8m
  completed: 2026-07-13
status: complete
---

# Phase 04 Plan 16: Governed Viewpoint Production API Summary

**Immutable viewpoints now use a lifecycle-owned governed historical snapshot for outcome facts and expose authorized revision, correction, and evaluation actions.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-13T03:25:37Z
- **Completed:** 2026-07-13T03:33:33Z
- **Tasks:** 2/2
- **Files modified:** 6

## Accomplishments

- Added a FastAPI lifespan-owned viewpoint snapshot collaborator that reads only governed Kline repository data for the frozen instrument, benchmark, publication date, and 20/60/120-day window.
- Persisted evaluated relative returns with real coverage dates, or explicit append-only missing-price, missing-benchmark, and unsupported-scope outcomes.
- Added strict, scoped revision, correction, and zero-input evaluation routes that reauthorize persisted instruments and project only allowlisted immutable state.
- Replaced direct host-ledger writes with authenticated FastAPI lifecycle coverage for material stance changes, corrections, and governed outcomes.

## Task Commits

1. **Task 1: 在真实 lifespan 中提供受治理的 viewpoint evaluation collaborator** - `1dba64a` (test RED), `d62dece` (feat GREEN)
2. **Task 2: 添加授权 scoped 的 revision、correction 与 evaluation API** - `cc20654` (test RED), `00397a2` (feat GREEN)

## Files Created/Modified

- `backend/app/main.py` - Lifecycle-owned frozen historical evaluation collaborator.
- `backend/app/advanced/viewpoints.py` - Governed input validation, real return calculation, coverage persistence, and version lookup.
- `backend/app/advanced/api.py` - Authorized append-only revision, correction, and evaluation endpoints.
- `backend/app/advanced/schemas.py` - Strict correction request contract.
- `backend/tests/advanced/test_viewpoints.py` - Service and API authority-boundary regression contracts.
- `backend/tests/advanced/test_production_host.py` - Real FastAPI lifespan mutation and evaluation integration path.

## Verification

```text
cd backend && timeout 60s uv run pytest tests/advanced/test_viewpoints.py tests/advanced/test_production_host.py -q
26 passed, 15 warnings

cd backend && uv run ruff check app/advanced/viewpoints.py app/advanced/api.py tests/advanced/test_viewpoints.py tests/advanced/test_production_host.py
All checks passed

cd backend && uv run python -m compileall -q app/advanced/viewpoints.py app/advanced/api.py app/main.py
passed
```

## Decisions Made

- Evaluation is driven by each persisted version's frozen plan and governed historical repository reads, never current quotes or client-provided market data.
- Routes resolve the persisted instrument before scope authorization; a browser ID remains a lookup key rather than authority.
- The evaluation action has a strict empty request body, and returns a reloaded allowlisted version projection after appending its outcome.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Reloaded immutable version state after evaluation append**
- **Found during:** Task 2 (authorized evaluation API)
- **Issue:** `ViewpointService.evaluate_viewpoint()` returns only an outcome record, which cannot safely satisfy the existing viewpoint DTO projection.
- **Fix:** Reloaded the authorized version from the immutable lineage after appending the fact, then projected that version with its latest evaluation.
- **Files modified:** `backend/app/advanced/api.py`
- **Verification:** Focused API and production-host tests pass.
- **Committed in:** `00397a2`

**Total deviations:** 1 auto-fixed (1 Rule 1 bug).
**Impact on plan:** The fix preserves the DTO allowlist and makes the newly added evaluation route usable without exposing raw ledger records.

## Issues Encountered

The production-host suite emits existing Polars streaming deprecation and sortedness warnings. All planned checks completed successfully.

## Known Stubs

None. The production collaborator reads governed repository windows and persists actual evaluated or explicit unevaluable facts; no placeholder result is exposed to the API.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

ADV-01 now has a production-accessible path from immutable creation through revisions, corrections, governed evaluation, and authorized historical review.

## Self-Check: PASSED

Verified the six modified source/test files exist and task commits `1dba64a`, `d62dece`, `cc20654`, and `00397a2` are present in git history.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-13*
