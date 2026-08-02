---
phase: 13-walk-forward-validation-parameter-search
plan: 13-05
subsystem: backtest/research
tags: [wfwd-01, wfwd-02, wfwd-03, geometry-robustness, reporting-breadth, wave-4]
requires:
  - phase: 13-walk-forward-validation-parameter-search
    provides: build_plan / run_walk_forward / WalkForwardFold/Plan with measured-calendar geometry + exactly-once OOS (13-01), wf_* append-only tables + repo read methods (13-02), WalkForwardOptimizer + evaluate_best_params validation gate (13-03)
provides:
  - Fail-closed geometry breadth: explicit 2-fold minimum (H < train+gap+2*test+oos raises with measured count + minimum), measured-at-execution trading_calendar contract
  - Reporting read breadth: list_wf_plans + list_wf_search_runs (new), documented passed_gate filter + resolved_asset_ids unwrap on list_validated_strategies
  - Robustness test breadth: calendar re-measure rolls folds/OOS forward, effective_days label-buffer guard, membership-drift reproducibility, reporting round-trips
affects: [Phase 14 (RebalancePlan consumes validated strategies + resolved_asset_ids), Phase 15 (WalkForward panels consume get/list reads)]
actuals:
  tokens: 0
  tasks: 3
  commits: 3
tech-stack:
  added: []
  patterns: [fail-closed geometry asserts (ValueError, never 1-fold validation), measured-at-execution re-measurement, positive-int limit guards, JSON unwrap read surface, passed_gate filter]
key-files:
  created: []
  modified:
    - backend/app/backtest/walkforward.py
    - backend/app/research/repository.py
    - backend/tests/backtest/test_walkforward.py
    - backend/tests/backtest/test_ensemble.py
key-decisions:
  - "Explicit 2-fold minimum check len(dates) - oos_size < train_size + gap_size + 2*test_size placed BEFORE fold derivation; message states the measured day count and the minimum (H≈180 fail-closed, T-13-09)"
  - "trading_calendar is measured at execution — the enriched lake grows ~20 trading days/month; callers re-measure, never hard-code the 2026-07-30 end (grep gate: 0 hard-coded 2026-0 dates in walkforward.py)"
  - "effective_days >= 10 remains an assert in run_walk_forward (never a silent clamp) — the label-lookahead guard T-13-04"
  - "Reporting breadth adds list_wf_plans + list_wf_search_runs (Phase 15 panel); list_validated_strategies already carried passed_gate filter + resolved_asset_ids unwrap from 13-02 — no schema change (resolved_asset_ids_json column already in DDL)"
  - "Fold-count growth: +~20 measured trading days ⇒ +1 fold and the OOS rolls forward by design (verified 249→269 days ⇒ 3→4 folds, OOS end 2026-07-30→2026-08-28)"
requirements-completed: [WFWD-01, WFWD-02, WFWD-03]
coverage:
  - id: D1
    description: "build_plan fails closed below 2 folds with a clear error naming the measured day count and the minimum; the calendar is re-measured at execution and geometry rolls forward with the lake"
    requirement: WFWD-01
    verification:
      - kind: unit
        ref: "tests/backtest/test_walkforward.py#test_fail_closed_below_two_folds_reports_measured_count"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_walkforward.py#test_calendar_remeasured_grows_fold_count_and_rolls_oos_forward"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_walkforward.py#test_overlapping_fold_geometry_fails_closed"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_walkforward.py#test_oos_colliding_config_fails_closed"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every fold manifest asserts effective_days >= 10 (label-lookahead guard); membership fingerprints change with membership and are reproducible"
    requirement: WFWD-01
    verification:
      - kind: unit
        ref: "tests/backtest/test_walkforward.py#test_effective_days_label_buffer_reports_test_size_minus_horizon"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_walkforward.py#test_run_walk_forward_effective_days_below_10_raises"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_walkforward.py#test_membership_fingerprint_changes_when_membership_changes"
        status: pass
    human_judgment: false
  - id: D3
    description: "The read/list reporting surface (get_wf_plan / list_wf_plans / list_wf_folds / list_wf_search_runs / list_validated_strategies incl. passed_gate + resolved_asset_ids) supports Phase 14 handoff and Phase 15 panels"
    requirement: WFWD-02
    verification:
      - kind: unit
        ref: "tests/backtest/test_walkforward.py#test_reporting_surface_get_plan_list_folds_and_validated"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_ensemble.py#test_ensemble_gate_consumes_passed_gate_filtered_reports"
        status: pass
    human_judgment: false
duration: 15min
completed: 2026-08-02
status: complete
---

# Phase 13 Plan 13-05: Geometry Robustness + Reporting Breadth — Summary

Walk-forward robustness + reporting breadth: `build_plan` now fails closed below 2 folds (H≈180) with a clear `ValueError` stating the measured day count and the minimum; `trading_calendar` documents the measured-at-execution contract so the enriched lake's ~20 trading days/month roll the fold count and OOS forward instead of assuming hard-coded dates; the `effective_days >= 10` label-buffer guard remains an assert (never a silent clamp); and the repository read surface grows `list_wf_plans` + `list_wf_search_runs` with the Phase 14/15 read contract (passed_gate filter + `resolved_asset_ids` unwrap) — WFWD-01/02/03 robustness breadth locked by 26 green tests.

## Performance

- **Duration:** ~15 min
- **Started:** 2026-08-02T11:20:00Z
- **Completed:** 2026-08-02T11:35:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- **Fail-closed geometry (T-13-09)** — `build_plan` raises `ValueError` when `len(dates) - oos_size < train_size + gap_size + 2 * test_size`, i.e. fewer than 2 folds (walk-forward degenerates below H≈180). The message names the measured day count and the minimum (`"180 measured trading days < minimum 220"`), so a 1-fold "validation" is impossible.
- **Measured-at-execution calendar** — `trading_calendar` docstring documents the contract (callers re-measure at run time; a stale calendar produces the wrong fold count and rolls the OOS forward by design; never hard-code the 2026-07-30 end date). Verified: 249 → 269 measured days ⇒ 3 → 4 folds and the OOS end rolls 2026-07-30 → 2026-08-28.
- **Label-buffer guard** — `effective_days >= 10` is an assert inside `run_walk_forward`'s per-fold manifest path (not a silent clamp). A horizon large enough to collapse scorable days below 10 raises `ValueError("fold N has N effective days (< 10)")`.
- **Reporting breadth** — new `list_wf_plans` (newest first, unwrapped trading_dates/fold_geometry, positive-int limit) and `list_wf_search_runs` (filtered by plan_id/strategy_id, unwrapped search_space/score_distribution/best_params, limit guard). `list_validated_strategies` already carried the `passed_gate` filter + `resolved_asset_ids` unwrap from 13-02 — docstrings now state the Phase 14/15 read contract. **No schema column added** (`resolved_asset_ids_json` already in the 13-02 DDL; only the read surface is extended).
- **Robustness test breadth** — 8 new tests in `test_walkforward.py` + 1 in `test_ensemble.py`: calendar re-measure, fail-closed below 2 folds, overlapping-fold and OOS-collision geometry guards, effective_days label-buffer math, runner below-10 raise, reporting round-trips, and the ensemble gate consuming exactly `list_validated_strategies(passed_gate=1)` with `resolved_asset_ids`.
- Per-plan gate `pytest tests/backtest/test_walkforward.py tests/backtest/test_ensemble.py -q --tb=short`: **26 passed** (16 walkforward + 10 ensemble). Related suites still green: `test_optimizer_run.py` 21 passed, `tests/test_operational_migrations.py` 13 passed.

## Task Commits

Each task was committed atomically:

1. **Task 1: Calendar re-measurement + fail-closed geometry breadth in `walkforward.py`** — `bd5e3e1` (feat): explicit 2-fold minimum with measured-count message + measured-at-execution contract; `effective_days >= 10` assert already enforced per fold manifest.
2. **Task 2: Reporting read/list breadth in `repository.py`** — `d9cd447` (feat): `list_wf_plans` + `list_wf_search_runs`; docstring contracts on `get_wf_plan` / `list_wf_folds` / `list_validated_strategies`.
3. **Task 3: Breadth tests** — `03370fb` (test): 8 new walkforward + 1 new ensemble case; gate green; ruff clean.

## Files Created/Modified

- `backend/app/backtest/walkforward.py` — explicit `minimum = oos_size + train_size + gap_size + 2 * test_size` fail-closed check before fold derivation; `trading_calendar` measured-at-execution docstring. Grep gates: 0 hard-coded `2026-0` dates, `timedelta` ≤ 1 (label buffer only).
- `backend/app/research/repository.py` — `list_wf_plans` + `list_wf_search_runs` read methods (both positive-int limit fail-closed, JSON unwrap); read-contract docstrings on `get_wf_plan` / `list_wf_folds` / `list_validated_strategies`.
- `backend/tests/backtest/test_walkforward.py` — 8 new 13-05 cases (16 total green).
- `backend/tests/backtest/test_ensemble.py` — 1 new case: the ensemble gate reads exactly `list_validated_strategies(passed_gate=1)` and rows carry `resolved_asset_ids` (10 total green).

## Decisions Made

- **Explicit minimum formula** — `len(dates) - oos_size < train_size + gap_size + 2 * test_size` checked BEFORE the fold-count loop, so the degenerate 1-fold/zero-fold geometry is rejected up front with the exact measured-count message the plan requires (T-13-09).
- **No schema addition** — per the batch contract, `resolved_asset_ids_json` already exists in the 13-02 migration DDL; 13-05 only extends the repository read surface to unwrap it (`_unpack_json` mapping already in place) plus the two new list methods.
- **`effective_days >= 10` stays an assert** — the guard lives in `run_walk_forward._run_fold` (`raise ValueError(f"fold ... has ... effective days (< 10)")`), satisfying the plan's grep gate ("an assert, not a silent clamp").
- **Grown-calendar test math** — verified empirically: 249 measured days (3 folds, OOS end 2026-07-30) + 20 weekday days ⇒ 269 days (4 folds, OOS end 2026-08-28). The test asserts `len(large.folds) == len(small.folds) + 1` and `large.oos_fold.test_end > small.oos_fold.test_end`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Overlapping-fold / OOS-collision tests did not reproduce the geometry guards**
- **Found during:** Task 3 (running the new tests)
- **Issue:** `build_plan` derives fold count from the selection region, so a truncated history either raised "insufficient history" (the new minimum check) or the fold rectangles could not overlap by construction — the "overlapping config" and "OOS-colliding config" tests as initially written could not reach `_assert_geometry`'s overlap/OOS guards.
- **Fix:** test `_assert_geometry` directly with hand-built `WalkForwardFold` rectangles — fold 0 test [30,49] vs fold 1 test [40,59] (overlap → `tile contiguously|must be disjoint`) and a fold whose test [30,49] collides with an OOS test starting at index 45 (`must not overlap`). The rectangle structure (train < gap < test) is preserved so only the target guard fires.
- **Files modified:** `backend/tests/backtest/test_walkforward.py`
- **Verification:** `pytest tests/backtest/test_walkforward.py` green; ruff clean.
- **Committed in:** 03370fb (Task 3 commit)

**2. [Rule 1 - Bug] Label-buffer effective_days assertion mis-stated the semantics**
- **Found during:** Task 3
- **Issue:** the plan says "effective_days = test_size - horizon (label buffer in play)" — but with the buffer (chain end = test_end + horizon) active, the effective days are `test_size` (all 20 test days scoreable); only WITHOUT the buffer do the last `horizon` days lose forward returns. The first test draft asserted the buffered value == `test_size - horizon`, which the implementation correctly did not produce (18 ≠ 15).
- **Fix:** the test now measures the no-buffer case (`_effective_test_days(..., compute_end=test_end, horizon) == test_size - horizon == 15`) and asserts the buffered value is `>=` the no-buffer floor, both `>= 10`. The below-10 runner raise uses `horizon=40` (empirically effective 8 < 10).
- **Files modified:** `backend/tests/backtest/test_walkforward.py`
- **Verification:** 16 walkforward tests green.
- **Committed in:** 03370fb (Task 3 commit)

**3. [Rule 1 - Bug] `resolved_asset_ids` assertion assumed a non-empty snapshot**
- **Found during:** Task 3
- **Issue:** `record_validated_strategy` (13-03 path) calls `resolved_asset_ids=[]` when not provided — the existing min/max gate test records verdicts without asset ids, so asserting `== ["000001.SZ", "000002.SZ"]` failed on `[]`.
- **Fix:** assert the column unwraps to a `list` (Phase-14 contract: a list, never a JSON string) and that the fixture path carries the expected ids in the ensemble test (which seeds them).
- **Files modified:** `backend/tests/backtest/test_walkforward.py`, `backend/tests/backtest/test_ensemble.py`
- **Verification:** gate green.
- **Committed in:** 03370fb (Task 3 commit)

**4. [Rule 3 - Lint] RUF012 ambiguous regex in pytest.raises**
- **Found during:** post-task lint pass
- **Issue:** `match="tile contiguously|must be disjoint"` flagged by ruff (regex without raw string).
- **Fix:** `r"tile contiguously|must be disjoint"`.
- **Files modified:** `backend/tests/backtest/test_walkforward.py`
- **Verification:** `ruff check` clean.
- **Committed in:** 03370fb (Task 3 commit)

---

**Total deviations:** 4 auto-fixed (3 Rule 1, 1 Rule 3)
**Impact on plan:** All auto-fixes are test-correctness fixes within the task's own files — the production code (walkforward.py minimum check + repository read methods) was implemented exactly per plan. No scope creep; no architectural changes.

## Issues Encountered

- **`_assert_geometry` is the right seam for overlap/OOS-collision testing** — `build_plan`'s geometry is derived, so degenerate overlap can only be exercised through the shared assertion helper. The plan's "overlapping fold config raises / OOS-colliding config raises" cases are now direct unit tests of `_assert_geometry` (the same code `build_plan` runs at the end).
- **Grep gate compliance** — `grep -v '^#' backend/app/backtest/walkforward.py | grep -c "2026-0"` == 0 (no hard-coded fold dates); `grep -c timedelta` == 1 (label buffer only); `effective_days < 10` raise confirmed at walkforward.py:505.

## Auth Gates

None.

## Known Stubs

None — no stubs in delivered code; the two new list methods return real read surfaces over the append-only wf_* tables.

## Threat Flags

None — no new network endpoints, auth paths, file-access patterns, or execution routes. The reporting breadth is read-only over append-only research records; the fail-closed geometry is a security boundary (T-13-09).

## Self-Check: PASSED

- `backend/app/backtest/walkforward.py` — modified; explicit 2-fold minimum + measured-at-execution docstring present; grep gates pass (0 hard-coded dates, 1 timedelta).
- `backend/app/research/repository.py` — modified; `list_wf_plans` + `list_wf_search_runs` present; limit guards smoke-tested (limit=0 → ValueError).
- `backend/tests/backtest/test_walkforward.py` — 16 green; `backend/tests/backtest/test_ensemble.py` — 10 green; gate `pytest tests/backtest/test_walkforward.py tests/backtest/test_ensemble.py -q --tb=short` → 26 passed.
- Related suites: `tests/backtest/test_optimizer_run.py` 21 passed; `tests/test_operational_migrations.py` 13 passed.
- Commits `bd5e3e1`, `d9cd447`, `03370fb` exist on `gsd/v1.2-end-to-end-factor-portfolio-pipeline-in-progress`; ruff clean on all 4 modified files.

## Next Phase Readiness

- WFWD-01/02/03 robustness contract complete: measured-calendar snapping, fail-closed geometry below 2 folds, `effective_days ≥ 10` guard, membership-drift fingerprints, and the read/list reporting surface for Phase 14 handoff / Phase 15 panels.
- All 5 Phase 13 plans complete; the phase gate (`pytest -x` full backend suite) runs before `/gsd-verify-work`.
- No blockers.

---
*Phase: 13-walk-forward-validation-parameter-search*
*Completed: 2026-08-02*
