---
phase: 13-walk-forward-validation-parameter-search
plan: 13-03
subsystem: backtest/research
tags: [wfwd-02, wave-2, parameter-search, oos-scored, validation-gate, walk-forward]
requires:
  - phase: 13-02
    provides: "wf_* tables (wf_plans/wf_folds/wf_search_runs/wf_validated_strategies), wf_* repo methods, test_optimizer_run.py OOS RED cases, conftest measured-calendar fixtures"
  - phase: 13-01
    provides: "WalkForwardPlan/WalkForwardFold dataclasses + run_walk_forward (exactly-once OOS path) + test_walkforward.py green spine"
provides:
  - "WalkForwardOptimizer in optimizer.py — OOS-scored grid search reusing expand_param_grid/GRID_MAX_COMBINATIONS/per-combo error isolation, scoring test folds only"
  - "evaluate_best_params in walkforward.py — best_params OOS evaluated exactly once + wf_validated_strategies verdict (oos_evidence_fold_id UNIQUE)"
  - "wf_search_runs bookkeeping: n_trials/search_space/score_distribution with oos_excluded=1 enforced"
affects: [13-04 ensemble.py validated-only gate, 13-05 robustness breadth, Phase 14 validated-strategy consumption]
tech-stack:
  added: []
  patterns:
    - "OOS-scored search reuses grid machinery (expand_param_grid/objective_value/default_direction) — no forked grid"
    - "Search folds = [f for f in plan.folds if not f.is_oos] — OOS structurally excluded, fail-closed on leak"
    - "exactly-once OOS via wf_folds UNIQUE (plan_id, fold_index, is_oos, strategy_id, params_sha256) -> ValueError"
    - "Validation verdict tied to the once-evaluated OOS via oos_evidence_fold_id UNIQUE"
key-files:
  created: []
  modified:
    - backend/app/backtest/optimizer.py
    - backend/app/backtest/walkforward.py
    - backend/tests/backtest/test_optimizer_run.py
    - backend/tests/backtest/test_walkforward.py
key-decisions:
  - "WalkForwardOptimizer lives in optimizer.py (same DI as StrategyOptimizer); repo persistence optional via repo kwarg (defaults to generated search_run_id when no repo)"
  - "Pooled trial score = mean of per-fold test objective values (mean OOS Sharpe default, per research discretion)"
  - "Score distribution uses population std (pstdev) over valid trial scores; per-fold distributions recorded per fold"
  - "evaluate_best_params reads the OOS objective from the fold manifest's test_stats; validation_threshold=None = explicit researcher accept (passed_gate=1)"
  - "Mechanical gate: min-direction objectives use <= threshold, max-direction use >= (matches optimizer._MINIMIZE_OBJECTIVES via default_direction)"
requirements-completed: [WFWD-01, WFWD-02]

# Coverage metadata (#1602) — deterministic UAT routing
coverage:
  - id: D1
    description: "WalkForwardOptimizer — OOS-scored grid search; trials score walk-forward test folds only; GRID cap inherited; per-combo error isolation; never in-sample"
    requirement: WFWD-02
    verification:
      - kind: unit
        ref: "tests/backtest/test_optimizer_run.py#test_wf_search_scores_test_folds_only_never_oos"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_optimizer_run.py#test_wf_search_never_scores_train_or_oos_windows"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_optimizer_run.py#test_wf_search_grid_cap_respected"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_optimizer_run.py#test_wf_search_isolates_per_combo_failures"
        status: pass
    human_judgment: false
  - id: D2
    description: "wf_search_runs bookkeeping — n_trials/search_space/score_distribution recorded, oos_excluded=1 enforced (fail-closed on 0)"
    requirement: WFWD-02
    verification:
      - kind: unit
        ref: "tests/backtest/test_optimizer_run.py#test_wf_search_records_trial_space_and_score_distribution"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_optimizer_run.py#test_wf_search_persists_search_run_row_when_repo_passed"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_optimizer_run.py#test_wf_search_oos_excluded_zero_fails_closed"
        status: pass
    human_judgment: false
  - id: D3
    description: "Search folds structurally exclude plan.oos_fold; a plan leaking the reserved OOS into folds fails closed"
    requirement: WFWD-02
    verification:
      - kind: unit
        ref: "tests/backtest/test_optimizer_run.py#test_wf_search_folds_exclude_plan_oos_fold"
        status: pass
    human_judgment: false
  - id: D4
    description: "best_params OOS evaluated exactly once (second evaluation raises ValueError); wf_validated_strategies verdict requires the OOS evidence fold id"
    requirement: WFWD-02
    verification:
      - kind: integration
        ref: "tests/backtest/test_walkforward.py#test_evaluate_best_params_oos_exactly_once_and_validation_gate"
        status: pass
    human_judgment: false
  - id: D5
    description: "Validation gate — mechanical threshold (min <= else >=) produces passed_gate verdicts; passed_gate=0 rows filterable"
    requirement: WFWD-02
    verification:
      - kind: integration
        ref: "tests/backtest/test_walkforward.py#test_evaluate_best_params_threshold_gate_min_and_max_direction"
        status: pass
    human_judgment: false

metrics:
  duration: 0
  completed: "2026-08-02"
status: complete
---

# Phase 13 Plan 13-03: OOS-Scored Parameter Search + Validation Gate Summary

**WalkForwardOptimizer in optimizer.py scores every grid trial on walk-forward test folds only (never in-sample, never the reserved OOS), records n_trials/search_space/score_distribution on wf_search_runs with oos_excluded=1 enforced, and evaluate_best_params turns the once-evaluated best-params OOS run into the wf_validated_strategies verdict — the only unbiased estimate (WFWD-02).**

## Performance

- **Duration:** 41 min
- **Started:** 2026-08-02T03:10:00Z
- **Completed:** 2026-08-02T03:51:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- `WalkForwardOptimizer` (optimizer.py, same DI as `StrategyOptimizer`) reuses `expand_param_grid` / `GRID_MAX_COMBINATIONS=2000` / `objective_value` / `default_direction` — the grid machinery is not forked; an over-cap grid raises before any trial runs.
- Every trial scores the **test segments of the walk-forward folds only** — no train-window, no OOS; `search_folds = [f for f in plan.folds if not f.is_oos]` with a fail-closed `ValueError` if a plan leaks the reserved OOS into `plan.folds`.
- Search results persist `n_trials` / `search_space` / `score_distribution` (per_trial, per_fold, min/median/max/mean/std) on an append-only `wf_search_runs` row with `oos_excluded=1`; `record_wf_search` fails closed on `oos_excluded=0` (WFWD-02 multiple-comparison guard).
- `evaluate_best_params` (walkforward.py) runs best_params on `plan.oos_fold` exactly once — the `wf_folds` UNIQUE makes a second evaluation raise `ValueError("OOS segment already evaluated")` — and records the `wf_validated_strategies` verdict whose `oos_evidence_fold_id` UNIQUE ties the verdict to that once-evaluated OOS evidence.
- Mechanical validation gate: `validation_threshold` produces `passed_gate` from the OOS score (min-direction `<=`, else `>=`); `None` = explicit researcher accept. `passed_gate=0` rows are filterable via `list_validated_strategies(passed_gate=False)`.
- Search folds and the reserved OOS share one `_run_folds` PIT/chain/backtest path (`run_walk_forward` refactored onto it) — the anti train/serve-skew invariant holds for the best-params OOS run too.

## Task Commits

1. **Task 1: WalkForwardOptimizer (OOS-scored, GRID-capped, bookkeeping)** - `1cea840` (feat)
2. **Task 2: evaluate_best_params (exactly-once OOS + validation gate)** - `7a7b9df` (feat)
3. **Task 3: green WFWD-02 cases (OOS exclusion, bookkeeping, exactly-once, gate)** - `885d351` (test)

## Files Created/Modified

- `backend/app/backtest/optimizer.py` - `WalkForwardOptimizer` class (OOS-scored fold loop, pooled mean-of-test-score, score-distribution bookkeeping, optional wf_search_runs persistence) + `_dist` helper; imports `statistics`/`uuid`/`Any`.
- `backend/app/backtest/walkforward.py` - `evaluate_best_params` + extracted `_run_folds`; `run_walk_forward` refactored onto the shared fold loop (no behavior change, 7 existing tests still green).
- `backend/tests/backtest/test_optimizer_run.py` - green WFWD-02 search cases + repo-persistence + never-in-sample + oos_excluded=0 fail-closed cases.
- `backend/tests/backtest/test_walkforward.py` - validation-gate integration cases (exactly-once OOS, verdict binding, threshold gate) + `_record_search_run` helper + `_HoldingDaysService` double.

## Decisions Made

- **WalkForwardOptimizer DI mirrors StrategyOptimizer** (`service` + `strategy_engine`); repo persistence is an explicit `repo=` kwarg so pure-search callers stay repository-free while research callers get the WFWD-02 audit row.
- **Pooled trial score = mean of per-fold test objective values** (default mean OOS Sharpe, per 13-RESEARCH discretion); per-fold scores are always recorded so the distribution is inspectable.
- **`score_distribution` uses population std (`pstdev`)** over valid trial scores; all-distribution stats are rounded consistently.
- **`evaluate_best_params` requires the OOS objective in the fold's test_stats** — it raises a clear `ValueError` when the objective is absent rather than silently mis-gating.
- **`validation_threshold=None` means explicit researcher accept** (passed_gate=1); when set, direction-aware comparison (min `<=`, max `>=`) decides the mechanical gate.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] `record_wf_search` called without `oos_excluded=1`**
- **Found during:** Task 3 (repo-persistence test)
- **Issue:** The WFWD-02 guard in `repository.record_wf_search` fails closed unless `oos_excluded=1` is passed, but the optimizer's persistence call initially omitted it — the audit row could never be written.
- **Fix:** Added `oos_excluded=1` to the `record_wf_search` call in `WalkForwardOptimizer.optimize`.
- **Files modified:** backend/app/backtest/optimizer.py
- **Verification:** `test_wf_search_persists_search_run_row_when_repo_passed` now passes (row persisted with `oos_excluded=1`).
- **Committed in:** 885d351

**2. [Rule 3 - Blocking] Validation-verdict FK required a real wf_search_runs row**
- **Found during:** Task 3 (validation-gate integration tests)
- **Issue:** `wf_validated_strategies.search_run_id REFERENCES wf_search_runs(id)` — the first test passed a synthetic `search_run_id` that did not exist, so `record_validated_strategy` raised a FOREIGN KEY IntegrityError mapped to the verdict-conflict ValueError.
- **Fix:** Tests now either pass a real search-run id via a `_record_search_run` helper (inserting a valid `wf_search_runs` row) or `search_run_id=None` (fixed-params direct validation, no search-run dependency). FK-correct, still exercises the UNIQUE oos_evidence_fold_id verdict guard.
- **Files modified:** backend/tests/backtest/test_walkforward.py
- **Verification:** Both gate integration tests pass.
- **Committed in:** 885d351

**3. [Rule 1 - Bug] Test design: best_params OOS row collided with the preheat params key**
- **Found during:** Task 3 (exactly-once integration test)
- **Issue:** The first draft preheated `run_walk_forward` with the same params as `evaluate_best_params`, so the OOS fold row already existed and `evaluate_best_params` raised "OOS segment already evaluated" on its own first call.
- **Fix:** Preheat with a distinct params key (`{"ma_proximity": 0.01}`) so the best-params OOS evaluation is a genuinely first evaluation; assertions updated to check the OOS evidence is a fresh row while the exactly-once guard still fires on the second evaluation.
- **Files modified:** backend/tests/backtest/test_walkforward.py
- **Verification:** Test passes; second evaluation raises `ValueError("OOS segment already evaluated")`.
- **Committed in:** 885d351

**4. [Rule 1 - Bug] min-direction gate case used a sharpe-only service double**
- **Found during:** Task 3 (threshold-gate test)
- **Issue:** The `avg_holding_days` min-direction case scored through the sharpe-only stub, whose test_stats lack `avg_holding_days` — `evaluate_best_params` correctly raised "no objective in test stats" rather than mis-gating.
- **Fix:** Added a `_HoldingDaysService` double exposing only `avg_holding_days`; the min-direction case now scores a real min-direction objective.
- **Files modified:** backend/tests/backtest/test_walkforward.py
- **Verification:** Threshold-gate test passes (max passes 1.0>=0.5; min fails 1.0>0.5).
- **Committed in:** 885d351

---

**Total deviations:** 4 auto-fixed (2 missing-critical/blocking, 2 test-design bugs)
**Impact on plan:** All fixes necessary for the WFWD-02 contract to hold end to end. No scope creep; no plan surface changed.

## Issues Encountered

- `test_ensemble.py` still has 2 RED cases (`ModuleNotFoundError: No module named 'app.backtest.ensemble'`) — expected; 13-04 lands the ensemble module. Not part of the 13-03 gate.
- The `wf_validated_strategies` FK graph (search_run_id → wf_search_runs) is stricter than the plan's synthetic-id tests assumed; resolved as documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 13-04 (rank-average ensemble) consumes `list_validated_strategies(passed_gate=1)` + `record_wf_ensemble` — both already landed by 13-02 and verified usable by the gate tests here.
- The `evaluate_best_params` verdict rows produced here are the exact `passed_gate=1` inputs the ensemble gate requires (T-13-06 mitigation).
- 13-05 robustness breadth builds on the same walkforward.py/optimizer.py surfaces; no API changes anticipated.

---
*Phase: 13-walk-forward-validation-parameter-search*
*Completed: 2026-08-02*
