---
phase: 05-optional-enhancements
plan: "39"
subsystem: forecast-runtime
tags: [forecast, recovery, process-group, pgid, cas, restart, cr-06, cr-07]
requires:
  - phase: 05-optional-enhancements
    provides: 05-27 ready handshake/IPC cleanup; 05-38 managed input integrity; CAS/global lease runner
provides:
  - consumed and observable queued-recovery dispatch during real host startup
  - one-winner recovered-job path under CAS/global lease
  - handshake PGID whole-group finalization on every post-spawn path
  - real-host CR-07 and process-group CR-06 regressions
affects: [FORE-01, 05-29]
tech-stack:
  added: []
  patterns:
    - recover_after_restart outcomes consumed one-by-one via ForecastService.run_recovered_job
    - app.state.forecast_recovery_outcomes publishes safe action/status only
    - child ready frame carries verified PGID; finalizer ignores leader is_alive for group cleanup
key-files:
  created: []
  modified:
    - backend/app/forecast/service.py
    - backend/app/optional_modules.py
    - backend/app/forecast/runner.py
    - backend/app/forecast/repository.py
    - backend/tests/forecast/test_runner.py
    - backend/tests/test_phase5_optional_host.py
key-decisions:
  - "Recovery reuses the normal runner CAS/global-lease path; no separate queue consumer."
  - "Handshake PGID is the only group identity used after spawn; leader exit never proves cleanup."
  - "Host recovery outcomes stay path/principal-free; recovery failure marks only Forecast unavailable."
patterns-established:
  - "Pattern: startup recovery publishes bounded outcomes and dispatches requeue via run_recovered_job."
  - "Pattern: post-spawn finally always reaps the saved process group before return."
requirements-completed: [FORE-01]
coverage:
  - id: D1
    description: "Startup consumes every recover_after_restart outcome; valid queued jobs execute once under CAS/global lease."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "tests/test_phase5_optional_host.py::test_cr07_real_host_queued_restart_executes_once"
        status: pass
      - kind: unit
        ref: "tests/forecast/test_runner.py -k 'restart_dispatches_queued or concurrent_recovery_one_winner or restart_terminalizes'"
        status: pass
    human_judgment: false
  - id: D2
    description: "Ready handshake carries PGID; every post-spawn path reaps the process group before completion is observable."
    requirement: FORE-01
    verification:
      - kind: unit
        ref: "tests/forecast/test_runner.py::test_cr06_normal_leader_exit_reaps_process_group_before_commit"
        status: pass
      - kind: unit
        ref: "tests/forecast/test_runner.py -k 'normal_exit_descendants_reaped or every_return_reaps_group or child_ready_handshake or descendants_reaped'"
        status: pass
    human_judgment: false
  - id: D3
    description: "Recovery failure is Forecast-local; peer modules and completed v1 remain available."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "tests/test_phase5_optional_host.py -k 'forecast_recovery_failure_is_local'"
        status: pass
    human_judgment: false
duration: 19min
completed: 2026-07-25
status: complete
---

# Phase 05 Plan 39: CR-06/CR-07 Recovery And PGID Cleanup Summary

**Startup recovery now dispatches each durable queued Forecast job once under CAS/global lease, and the runner reaps the handshake process group on every post-spawn path including normal leader exit.**

## Performance

- **Duration:** ~19 min
- **Started:** 2026-07-25T15:13:50Z
- **Completed:** 2026-07-25T15:32:38Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Host startup consumes every `recover_after_restart` outcome, dispatches valid `requeue` jobs through `ForecastService.run_recovered_job`, and publishes safe `forecast_recovery_outcomes`.
- Concurrent recovered dispatches produce one CAS/global-lease winner and one terminal forecast record.
- Child ready handshake reports the post-`setsid` PGID; a unified finalizer TERM/KILL-confirms the group even when the leader already exited.
- CR-06 primary proves a successful leader with a lingering descendant cannot complete until the group is gone.

## Task Commits

1. **Task 1: Restart the real host and advance one durable queued Forecast job exactly once** - `1a037b1` (feat)
2. **Task 2: Reap the saved process group after normal leader exit and every post-spawn return** - `d62fc23` (feat)
3. **Rule 1 fix: verified artifact payload bytes** - `41f561e` (fix)

## Files Created/Modified

- `backend/app/forecast/service.py` - `run_recovered_job` recovered dispatch under the normal runner
- `backend/app/optional_modules.py` - consume recovery outcomes, publish safe status, clear on failure
- `backend/app/forecast/runner.py` - ready PGID, unconditional group finalizer, SuccessWithDescendantWorker
- `backend/app/forecast/repository.py` - use store-returned verified payload bytes
- `backend/tests/forecast/test_runner.py` - CR-06/CR-07 unit regressions
- `backend/tests/test_phase5_optional_host.py` - real-host queued restart and module-local recovery failure; HostForecastWorker emits full artifact bundle

## Decisions Made

- Recovery is not a second queue: it reuses `run_job` so reauthorization, catalog, input, lease, and commit remain one code path.
- Group cleanup keys only on the handshake PGID (equal to the child leader pid after `setsid`); never infer a group from a dead leader later.
- Observable recovery status is limited to `job_id` / `action` / `status` with no principal, paths, or raw errors.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Managed artifact store returns payload bytes, not a path**
- **Found during:** Task 1 host verification
- **Issue:** `ForecastRepository` still expected `_verified_payload` to return a path and re-read bytes.
- **Fix:** Use the returned payload bytes directly.
- **Files modified:** `backend/app/forecast/repository.py`
- **Commit:** `41f561e`

**2. [Rule 2 - Missing Critical] HostForecastWorker still emitted legacy single-path descriptors**
- **Found during:** Task 1 real-host recovery
- **Issue:** Production verifier requires `paths_artifact` + `quantiles_artifact` bundles; the host fixture worker returned a pre-bundle descriptor, so recovered and live requests artifact_failed.
- **Fix:** HostForecastWorker persists via `ForecastArtifactStore` and returns `capped_manifest()`.
- **Files modified:** `backend/tests/test_phase5_optional_host.py`
- **Commit:** `1a037b1`

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical for host fixture correctness)
**Impact on plan:** Required for CR-07 primary to complete; no architectural scope change.

## Issues Encountered

- Root-owned host test file blocked in-place edits until unlinked and recreated from git.
- Spawned workers do not share parent-side CountingBoundary call counters; concurrency tests assert one completed forecast instead of parent call counts.

## User Setup Required

None - no external service configuration required. Recovery remains local-only and uses the approved 05-40 → 05-26 → 05-27 supply/runtime chain with test fixtures only.

## Next Phase Readiness

- CR-06 and CR-07 blockers are closed with primary report nodes green.
- Remaining incomplete plan in phase 05 is `05-29-PLAN.md` if still open after parallel work.

## Self-Check: PASSED

- SUMMARY present at `.planning/phases/05-optional-enhancements/05-39-SUMMARY.md`
- Commits `1a037b1`, `d62fc23`, `41f561e` exist on `gsd/v1.0-milestone`
- Primary nodes and acceptance selectors all passed

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-25*
