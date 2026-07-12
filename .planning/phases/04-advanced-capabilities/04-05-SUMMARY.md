---
phase: 04-advanced-capabilities
plan: "05"
subsystem: advanced-viewpoints
tags: [sqlite, immutable-facts, governed-data, calibration, viewpoints]
requires:
  - phase: 04-04
    provides: strict policy bootstrap and append-only advanced SQLite foundation
provides:
  - immutable attributed viewpoint version lineage and structural stance comparison
  - frozen benchmark/window evaluation facts with governed input fingerprints
  - low/medium/high confidence calibration with explicit insufficient-sample status
affects: [04-08, 04-09, 04-10, advanced-backend]
tech-stack:
  added: []
  patterns:
    - service-owned policy validation before immutable viewpoint append
    - append-only evaluation plan and outcome event ledger
    - injected governed snapshot collaborator for historical evaluation inputs
key-files:
  created:
    - backend/app/advanced/viewpoints.py
  modified:
    - backend/app/advanced/repository.py
    - backend/app/operational/migrations.py
    - backend/tests/advanced/test_viewpoints.py
key-decisions:
  - "Viewpoint versions write policy snapshot, lineage, structured fields, evidence, and frozen evaluation plan in one transaction."
  - "Evaluation facts are append-only events so the initially frozen plan and later governed outcome are both auditable."
  - "Calibration reports every confidence bucket and never treats unevaluable or small samples as reliable performance."
requirements-completed: [ADV-01]
coverage:
  - id: D1
    description: Immutable viewpoint versions preserve attribution, evidence, correction reason, and structured material-change classification.
    requirement: ADV-01
    verification:
      - kind: tests
        ref: backend/tests/advanced/test_viewpoints.py
        status: pass
    human_judgment: false
  - id: D2
    description: Governed evaluations freeze 20/60/120-day windows, benchmarks, fingerprints, unevaluable reasons, and complete confidence calibration buckets.
    requirement: ADV-01
    verification:
      - kind: tests
        ref: cd backend && timeout 30s uv run pytest tests/advanced/test_viewpoints.py -q
        status: pass
    human_judgment: false
metrics:
  duration: 6m
  completed: 2026-07-12
status: complete
---

# Phase 04 Plan 05: Attributed Viewpoints Summary

**Immutable attributed viewpoints now retain policy-bound versions, evidence, structural stance changes, frozen governed outcomes, and honest confidence calibration.**

## Performance

- **Duration:** 6m
- **Started:** 2026-07-12T14:24:51Z
- **Completed:** 2026-07-12T14:30:54Z
- **Tasks:** 2/2
- **Files modified:** 4

## Accomplishments

- Added server-authoritative viewpoint creation, revision, correction, reverse-chronological lineage, and structured material-change classification.
- Validated only the deployment policy's source profile, CN-A scope, asset benchmark defaults, and allowed benchmark overrides before append-only persistence.
- Added frozen evaluation-plan facts and governed snapshot evaluation with explicit missing-price or missing-benchmark outcomes.
- Added a forward SQLite migration from a single evaluation row to immutable plan/outcome events with governed input fingerprints.
- Reported low, medium, and high confidence buckets with hit rate, relative return, coverage, and typed insufficient-sample status.

## Task Commits

1. **Task 1: Implement immutable version lineage and structured stance comparison** - `52d7b01` (`feat`)
2. **Task 2: Implement frozen outcome and calibration calculation** - `e12a83b` (`feat`)

## Files Created/Modified

- `backend/app/advanced/viewpoints.py` - Policy-validated immutable version, governed outcome, and calibration service.
- `backend/app/advanced/repository.py` - Transactional viewpoint, evidence, evaluation, and calibration read primitives.
- `backend/app/operational/migrations.py` - Forward migration for append-only evaluation events and governed input fingerprints.
- `backend/tests/advanced/test_viewpoints.py` - Green viewpoint lineage, frozen outcome, calibration, and fingerprint contracts.

## Verification

```text
cd backend && timeout 30s uv run pytest tests/advanced/test_viewpoints.py -q
16 passed in 6.71s

cd backend && uv run ruff check app/advanced/viewpoints.py app/advanced/repository.py app/operational/migrations.py tests/advanced/test_viewpoints.py
All checks passed

cd backend && uv run python -m compileall -q app/advanced app/operational/migrations.py
passed
```

## Decisions Made

- Persist the frozen evaluation plan separately from later outcomes so historical intent and governed inputs cannot be overwritten.
- Keep policy authority in the deployment bootstrap; callers cannot supply source-profile, scope, benchmark, or materiality authority.
- Retain all confidence buckets, including insufficient samples, and exclude unevaluable rows from numerical aggregates without silently removing their recorded outcomes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Issue] Added required viewpoint repository transaction primitives**
- **Found during:** Task 1
- **Issue:** The Phase 04 foundation exposed no transaction methods for viewpoint versions, evidence, or evaluations, which would have forced the service to bypass repository ownership.
- **Fix:** Added narrow append/read repository methods and used them for all service persistence.
- **Files modified:** `backend/app/advanced/repository.py`
- **Verification:** Focused lineage contracts passed.
- **Commit:** `52d7b01`

**2. [Rule 2 - Missing Critical Functionality] Migrated evaluations to an append-only plan/outcome ledger**
- **Found during:** Tasks 1-2
- **Issue:** The initial single-row evaluation constraint could not preserve both the frozen evaluation plan and a later immutable governed outcome; it also lacked an input fingerprint.
- **Fix:** Added a forward SQLite rebuild migration, persisted governed input fingerprints, and kept plan plus outcome as separate immutable facts.
- **Files modified:** `backend/app/operational/migrations.py`, `backend/app/advanced/repository.py`, `backend/app/advanced/viewpoints.py`, `backend/tests/advanced/test_viewpoints.py`
- **Verification:** All 16 focused viewpoint contracts passed.
- **Commit:** `e12a83b`

**Total deviations:** 2 auto-fixed (1 Rule 3 blocker, 1 Rule 2 critical functionality gap).
**Impact on plan:** The changes preserve the required transactional and forensic guarantees without adding user-facing scope.

## Known Stubs

None. The service persists concrete immutable facts and receives historical prices only through its injected governed collaborator.

## Threat Flags

None. This plan added no endpoint, authentication route, file-access pattern, or trust-boundary schema beyond the planned immutable viewpoint ledger.

## Next Phase Readiness

Plans 04-08 and 04-09 can expose viewpoint service projections without reconstructing historical market performance in the browser.

## Self-Check: PASSED

Verified `backend/app/advanced/viewpoints.py` and `backend/tests/advanced/test_viewpoints.py` exist, commits `52d7b01` and `e12a83b` are present, and `STATE.md` and `ROADMAP.md` remain untouched as requested.

---
*Phase: 04-advanced-capabilities*
*Completed: 2026-07-12*
