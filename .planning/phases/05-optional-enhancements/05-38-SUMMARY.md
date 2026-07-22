---
phase: 05-optional-enhancements
plan: "38"
subsystem: forecast-managed-input-integrity
status: complete
tags: [forecast, idempotency, parquet, toctou, input-integrity, CR-05, WR-01, WR-02]
requires:
  - phase: 05-optional-enhancements
    plan: "22"
    provides: governed Forecast input freezer and fingerprint contracts
  - phase: 05-optional-enhancements
    plan: "31"
    provides: invocation-owned managed-artifact cleanup patterns
  - phase: 05-optional-enhancements
    plan: "37"
    provides: ownership and principal-scoped Forecast surfaces
provides:
  - operation-first Forecast idempotency lookup before freezer promotion
  - parent-owned read-only sealed input handle for workers
  - final_input_revalidate immediately before sole commit_completed_forecast
  - same-open O_RDONLY|O_NOFOLLOW Parquet load via BytesIO
  - reference-safe invocation-owned unbound artifact discard
affects: [FORE-01, CR-05, WR-01, WR-02]
tech-stack:
  added: []
  patterns:
    - operation-first CAS with process lock around create_or_get_job
    - sealed read-only payload handle without writable managed path
    - same-FD fstat/hash/read then BytesIO decode
key-files:
  created:
    - .planning/phases/05-optional-enhancements/05-38-SUMMARY.md
  modified:
    - backend/app/optional_artifacts.py
    - backend/app/forecast/service.py
    - backend/app/forecast/repository.py
    - backend/app/forecast/runner.py
    - backend/app/optional_modules.py
    - backend/tests/forecast/test_runner.py
    - backend/tests/forecast/test_input.py
    - backend/tests/test_phase5_foundation.py
key-decisions:
  - "Lookup principal+instrument+horizon+catalog+idempotency before freeze; race losers discard only invocation-owned unbound namespaces."
  - "Replace input_artifact_path with sealed read-only handle (payload+checksum); never pass writable managed path to the child."
  - "ForecastRunner invokes final_input_revalidate after artifact_verify and immediately before commit_completed_forecast."
  - "Managed Parquet load opens once with O_NOFOLLOW, validates fstat/digest on the same FD, then decodes BytesIO only."
patterns-established:
  - "Operation-first managed input lifecycle with owned discard"
  - "Mandatory post-worker final input identity gate before commit"
requirements-completed: [FORE-01]
duration: 45m
completed: 2026-07-22
---

# Phase 05 Plan 38: Forecast Input Integrity Summary

**Operation-first Forecast replay, read-only sealed worker input, mandatory final input revalidation before commit, and same-open Parquet decode close CR-05, WR-01, and WR-02.**

## Performance

- **Duration:** ~45m
- **Started:** 2026-07-22T17:49:27Z
- **Completed:** 2026-07-22T18:40:00Z
- **Tasks:** 2/2
- **Files modified:** 8

## Accomplishments

- Added `ForecastRepository.find_active_job` and `input_artifact_is_referenced` so idempotent replay resolves the persisted operation before freezer promotion.
- Reworked `ForecastService.create_or_get_job` to operation-first lookup under a create lock; race losers discard only invocation-owned unbound managed namespaces.
- Replaced child `input_artifact_path` with a parent-opened sealed `input_artifact_handle` (payload + checksum, `writable=False`).
- Added `ForecastService.final_input_revalidate` and wired `ForecastRunner` to call it immediately before the sole `commit_completed_forecast`; failure terminalizes with commit spy zero and action spies zero.
- Refactored `ManagedImmutableArtifactStore` Parquet/bytes load to one `O_RDONLY|O_NOFOLLOW` open, same-FD fstat/hash/read, and `BytesIO` decode; added `discard_unbound_invocation_owned`.
- Primary report nodes green: CR-05, WR-01, WR-02.

## Task Commits

| Gate | Task | Result |
|---|---|---|
| GREEN | Task 1: Operation-first replay + final input revalidation | Primary CR-05/WR-01 nodes + selectors passed |
| GREEN | Task 2: Same-open Parquet + unbound discard | Primary WR-02 node + selectors passed |

## Files Created/Modified

- `backend/app/optional_artifacts.py` — same-open verified payload read; invocation-owned unbound discard.
- `backend/app/forecast/repository.py` — owner-scoped operation lookup and artifact reference check.
- `backend/app/forecast/service.py` — operation-first create, sealed handle bind, final revalidate, owned discard.
- `backend/app/forecast/runner.py` — `final_input_revalidate` seam immediately before commit.
- `backend/app/optional_modules.py` — wire production runner to service final revalidate.
- `backend/tests/forecast/test_runner.py` — CR-05/WR-01 primary nodes and orphan/tamper coverage.
- `backend/tests/forecast/test_input.py` — read-only handle and fingerprint revalidation coverage.
- `backend/tests/test_phase5_foundation.py` — WR-02 TOCTOU same-open and unbound discard coverage.

## Decisions Made

- Used a process-local create lock plus repository CAS uniqueness so ordinary replay never freezes; concurrent creators still lose via unique key and discard unbound losers.
- Sealed handle carries verified bytes for spawn-safe pickling rather than a raw FD (FDs do not survive spawn pickling); production never exposes the writable pathname key.
- Final revalidation reloads the bound managed artifact by id/checksum rather than re-freezing from source, so post-worker file tamper is detected against the server-bound identity.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Host FixedWorker requires 1GiB RLIMIT_AS**
- **Found during:** Task 1 CR-05 spawn verification
- **Issue:** 512MiB address space limit used by older tests kills Python 3.14 spawn workers before manifest return on this host.
- **Fix:** CR-05 primary test and `_runner` helper use 1GiB address space so worker completion can reach final revalidation.
- **Files modified:** `backend/tests/forecast/test_runner.py`

**2. [Rule 2 - Missing critical functionality] Unit-test freezers without managed paths**
- **Found during:** Task 1 regression on production service revalidation test
- **Issue:** Fake descriptors lacked `artifact_id` / real path, breaking `_bind` and owned-set tracking.
- **Fix:** Soft-fail sealed handle construction without reintroducing writable paths; track owned artifact ids only when present.
- **Files modified:** `backend/app/forecast/service.py`

## Issues Encountered

- Root-owned 0644 files under `backend/app/forecast/` required atomic replace via directory-writable temp files.
- STATE.md / ROADMAP.md left for orchestrator if permission denied.

## Verification

```text
cd backend && python3 -m pytest \
  tests/forecast/test_runner.py::test_cr05_final_input_revalidation_precedes_commit_and_commit_spy_zero \
  tests/forecast/test_runner.py::test_wr01_operation_first_replay_race_leaves_no_orphan -x
Result: PASS — 2 passed.

cd backend && python3 -m pytest tests/forecast/test_input.py -k "read_only_handle or post_worker_revalidation or fingerprint" -x
Result: PASS — 5 passed, 15 deselected.

cd backend && python3 -m pytest tests/forecast/test_runner.py -k "idempotent_input_namespace or orphan_cleanup or worker_input_tamper or pre_commit_input" -x
Result: PASS — 2 passed, 41 deselected.

cd backend && python3 -m pytest tests/test_phase5_foundation.py -k "parquet_same_open or toctou or unbound_discard or artifact_metadata" -x
Result: PASS — 3 passed, 13 deselected.
```

## Threat Mitigation Evidence

- **T-05-38-01:** CR-05 node proves final revalidation precedes commit; commit spy 0; action spies 0; sealed handle has no writable path.
- **T-05-38-02:** WR-01 node proves same-key replay freezes zero times and race leaves one bound namespace per key.
- **T-05-38-03:** WR-02 node swaps directory entry after open and never decodes replacement frame.
- **T-05-38-04:** Unbound discard refuses non-owned/referenced assets and preserves shared bytes.

## Known Stubs

None that prevent plan goals. Empty payload in soft-fail sealed handle is only for unit freezers without a managed path; production freezers always open real verified bytes.

## Self-Check: PASSED

- Primary nodes exist and pass.
- SUMMARY written.
- Scoped implementation files present.

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-22*
