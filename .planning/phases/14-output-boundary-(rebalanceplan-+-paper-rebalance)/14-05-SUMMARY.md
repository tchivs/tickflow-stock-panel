---
phase: 14-output-boundary-(rebalanceplan-+-paper-rebalance)
plan: 14-05
subsystem: portfolio
tags: [reporting, robustness, checksum, run-gate, rebalance, paper]

requires: [14-03, 14-04]
provides:
  - "Reporting read/list breadth (Phase 15 surface): list_rebalance_plans(run_id filter, limit fail-closed), list_paper_transitions(plan/transition filters, limit fail-closed), get_paper_state derived, get_rebalance_plan full JSON unwrap"
  - "Run fail-closed: build_rebalance_plan raises ValueError on missing / non-optimal / empty-output_weights runs (mirrors analyzer L92-95)"
  - "Checksum-verified read: load_rebalance_plan via read_artifact(checksum_sha256=output_sha256) — tamper raises ArtifactReadError; input_snapshot_sha256 bound from the run row, never recomputed"
  - "blocked_instruments recorded verbatim in the plan row"
affects: [phase-15]

actuals:
  tokens: 5120
  tasks: 3
  commits: 1

tech-stack:
  added: []
  patterns:
    - "read_artifact is the ONLY artifact read in rebalance.py (no raw read_bytes in the plan path)"
    - "input_snapshot_sha256 appears only as a binding read from the run row (never recomputed)"

key-files:
  created: []
  modified:
    - backend/tests/portfolio/test_rebalance.py
    - backend/tests/portfolio/test_paper.py
  verified:
    - backend/app/portfolio/repository.py
    - backend/app/portfolio/rebalance.py

key-decisions:
  - "Run-gate messages mirror analyzer.py: 'no optimization run' / 'problem_status must be optimal' / 'no output weights'"
  - "Tampered plan artifact fails the checksum gate with ArtifactReadError('artifact checksum mismatch')"

patterns-established:
  - "The Phase 15 panel surface: get/list rebalance plans with filters, list paper transitions, derived paper state — all JSON-unwrapped"

requirements-completed: [RBAL-01, RBAL-02]

coverage:
  - id: D1
    description: "Reporting read/list breadth — list_rebalance_plans(run_id filter + limit fail-closed), list_paper_transitions(plan/transition filters + limit fail-closed), get_paper_state derived (suggested/approved/filled/rejected terminal), get_rebalance_plan full unwrap"
    requirement: RBAL-01
    verification:
      - kind: unit
        ref: "backend/tests/portfolio/test_rebalance.py#test_list_rebalance_plans_filters_and_caps + test_get_rebalance_plan_unwraps_all_json_columns_and_blocked_verbatim"
        status: pass
      - kind: unit
        ref: "backend/tests/portfolio/test_paper.py#test_list_paper_transitions_filters_and_caps + test_get_paper_state_rejected_terminal_and_filled"
        status: pass
    human_judgment: false
  - id: D2
    description: "Run fail-closed + checksum-verified read — missing / non-optimal / empty-output_weights runs raise ValueError; tampered artifact raises ArtifactReadError; input_snapshot_sha256 bound from run row"
    requirement: RBAL-01
    verification:
      - kind: unit
        ref: "backend/tests/portfolio/test_rebalance.py#test_build_rebalance_plan_fails_closed_on_{missing_run,non_optimal_run,empty_output_weights} + test_load_rebalance_plan_checksum_verified_read"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-08-02
status: complete
---

# Phase 14 Plan 14-05: Robustness + Reporting Breadth Summary

**The Phase 15 reporting surface and the RBAL-01/02 robustness contract are locked: run-gate fail-closed (missing / non-optimal / empty-weight), checksum-verified artifact read (tamper → ArtifactReadError), full JSON unwrap on get/list, derived paper state, and verbatim blocked_instruments.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-08-02T18:20:00Z
- **Completed:** 2026-08-02T18:35:00Z
- **Tasks:** 3
- **Files modified:** 2 (tests)

## Accomplishments

- Verified the 14-05 code surface (landed in 14-02/14-01) already implements every build requirement: `list_rebalance_plans(run_id=None, limit=200)` with run_id filter + limit fail-closed; `list_paper_transitions(plan_id, transition, limit)` with filters + limit fail-closed; `get_paper_state` derived from the max-ordinal transition row; `get_rebalance_plan` full unwrap; `build_rebalance_plan` fails closed on missing / non-optimal / empty-output_weights runs; `load_rebalance_plan` checksum-verified via `read_artifact(checksum_sha256=output_sha256)`; `input_snapshot_sha256` bound from the run row, never recomputed; `blocked_instruments` verbatim.
- Added the missing breadth TESTS (the plan's test task): `test_build_rebalance_plan_fails_closed_on_non_optimal_run`, `..._on_empty_output_weights` (via a `_record_run_like` helper that re-records a fixture run under a new id with DB-column field names), `test_load_rebalance_plan_checksum_verified_read` (valid read + tampered file → ArtifactReadError), `test_get_rebalance_plan_unwraps_all_json_columns_and_blocked_verbatim`, `test_get_paper_state_rejected_terminal_and_filled`.
- Full portfolio suite: 39 passed in `test_rebalance.py` + `test_paper.py`.

## Task Commits

1. **Breadth tests (run gate, checksum, unwrap, derived state)** - committed (test) — the five new cases above.

## Files Created/Modified

- `backend/tests/portfolio/test_rebalance.py` - Added `_record_run_like` helper + 4 new green tests (non-optimal run, empty-weight run, tampered-artifact read, full unwrap + blocked verbatim).
- `backend/tests/portfolio/test_paper.py` - Added `test_get_paper_state_rejected_terminal_and_filled`.
- `backend/app/portfolio/repository.py` + `backend/app/portfolio/rebalance.py` - Verified (already implemented by 14-02/14-01; no changes needed).

## Decisions Made

- Run-gate error messages mirror analyzer.py exactly ('no optimization run' / 'problem_status must be optimal' / 'no output weights') so cross-module fail-closed is greppable.
- Tampered plan artifact fails the checksum gate with `ArtifactReadError('artifact checksum mismatch')`.

## Deviations from Plan

None — the build surface was already in place; only the plan's test-task breadth needed authoring (the executor for 14-05 hit the LLM usage cap and the work was completed inline by the orchestrator).

---

**Total deviations:** 0
**Impact on plan:** None.

## Issues Encountered

- The dispatched executor for 14-05 failed with an upstream LLM usage-limit 429 (no work was lost); the orchestrator executed the plan inline.

## User Setup Required

None.

## Next Phase Readiness

- Phase 14 Wave 3 complete: all 5 plans landed, portfolio suite green, no-execution-route gate holds.
- Phase 15 (API/SSE + Frontend Panels) consumes the rebalance/paper read surface directly.

---
*Phase: 14-output-boundary-(rebalanceplan-+-paper-rebalance)*
*Completed: 2026-08-02*

## Self-Check: PASSED

- `cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -q --tb=short` → 39 passed.
- No-execution grep gate: 0 forbidden tokens; 0 `INSERT INTO positions`; 0 raw `INSERT INTO` in paper.py.
- `read_artifact` is the only artifact read in rebalance.py; `input_snapshot_sha256` only as a run-row binding.
