---
phase: 13-walk-forward-validation-parameter-search
plan: 13-01
subsystem: backtest
tags: [wfwd-01, wave-1, tracer, walk-forward, measured-calendar, pit, membership-fingerprint, exactly-once-oos]
requires:
  - phase: 13-02
    provides: "wf_plans/wf_folds append-only tables + wf_* repo methods (create_wf_plan, record_wf_fold, list_wf_folds) + Wave 0 test scaffolding (measured_calendar / wf_fixture_plan / stub chain/resolver/service)"
provides:
  - "backtest/walkforward.py — WalkForwardFold/WalkForwardPlan dataclasses, trading_calendar, build_plan, run_walk_forward (WFWD-01)"
  - "per-fold PIT: resolve_universe_daily window + membership_fingerprint + effective_days manifests in append-only wf_folds"
  - "per-fold SignalChainConfig(end=test_end+horizon) through the SHARED FactorSignalChain (FACT-06)"
  - "exactly-once OOS: pinned wf_plans row (oos_pinned_at) before any search reuse; second OOS evaluation raises ValueError"
affects: [13-03, 13-05]
actuals:
  tokens: 7600
  tasks: 3
  commits: 2
tech-stack:
  added: []
  patterns: [measured-calendar fold geometry (never timedelta boundaries), shared-chain per-fold config, append-only fold manifests, exactly-once OOS via UNIQUE]
key-files:
  created:
    - backend/app/backtest/walkforward.py
  modified:
    - backend/tests/backtest/test_walkforward.py
key-decisions:
  - "Per-fold effective_days is computed from trading-day position (label buffer window minus last horizon days), not calendar arithmetic; asserted >= 10 per fold."
  - "Search-fold reruns take the query path (append-only idempotency); only the OOS fold takes the write path so its UNIQUE exactly-once guard stays live."
  - "fold_scorer seam: default is the fixed-params strategy backtest variant (train + test windows through StrategyBacktestService); Phase 14 portfolio variant plugs in without forking geometry."
requirements-completed: [WFWD-01]
coverage:
  - id: D1
    description: "measured-calendar geometry — build_plan derives 3 rolling folds (train=120/gap=20/test=20, step=20) plus a reserved 40-day OOS snapped to the measured calendar; tests pairwise disjoint and tiled; fail-closed below 2 folds"
    requirement: WFWD-01
    verification:
      - kind: unit
        ref: "tests/backtest/test_walkforward.py#test_build_plan_derives_three_folds_with_gap_and_reserved_oos"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_walkforward.py#test_build_plan_fails_closed_on_short_history"
        status: pass
      - kind: unit
        ref: "tests/backtest/test_walkforward.py#test_calendar_snapping_respects_feb_2026_cny_hole"
        status: pass
    human_judgment: false
  - id: D2
    description: "OOS reservation pinned BEFORE any search reuse — create_wf_plan records oos_pinned_at idempotently; wf_plans append-only"
    requirement: WFWD-01
    verification:
      - kind: unit
        ref: "tests/backtest/test_walkforward.py#test_wf_plan_pinned_idempotently_and_fold_recorded_exactly_once"
        status: pass
    human_judgment: false
  - id: D3
    description: "exactly-once OOS — the reserved OOS fold is evaluated exactly once; a second evaluation of the same (plan, strategy, params) raises ValueError"
    requirement: WFWD-01
    verification:
      - kind: integration
        ref: "tests/backtest/test_walkforward.py#test_run_walk_forward_pins_plan_and_records_fingerprints"
        status: pass
    human_judgment: false
  - id: D4
    description: "per-fold PIT universe + membership_fingerprint — every fold resolves its own membership window and records a 64-hex fingerprint that changes when membership changes"
    requirement: WFWD-01
    verification:
      - kind: integration
        ref: "tests/backtest/test_walkforward.py#test_membership_fingerprint_changes_when_membership_changes"
        status: pass
    human_judgment: false
  - id: D5
    description: "per-fold SignalChainConfig — chain_config.end == test_end + horizon for every fold (search + OOS), label buffer through the shared chain; effective_days >= 10 recorded in each manifest"
    requirement: WFWD-01
    verification:
      - kind: integration
        ref: "tests/backtest/test_walkforward.py#test_run_walk_forward_pins_plan_and_records_fingerprints"
        status: pass
    human_judgment: false
duration: 18min
completed: 2026-08-02
status: complete
---

# Phase 13 Plan 13-01: Walk-Forward Tracer — Summary

**Measured-calendar rolling walk-forward spine proven end-to-end on a fixture: build_plan derives 3 gap-separated, tiled test folds + a reserved 40-day OOS snapped to the measured calendar; run_walk_forward pins the plan (oos_pinned_at) before any fold, computes each fold through a per-fold SignalChainConfig on the shared FactorSignalChain, records membership_fingerprint + effective_days manifests in append-only wf_folds, and evaluates the OOS exactly once (second evaluation → ValueError).**

## Performance

- **Duration:** 18 min
- **Started:** 2026-08-02T10:42:00Z
- **Completed:** 2026-08-02T11:00:00Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- `trading_calendar` reads distinct measured dates through the governed `BacktestEngine.load_panel(columns=["date"])` date-only probe (PanelCache reused) — never a synthetic weekday calendar, so the Feb-2026 CNY 14-day hole is respected by construction.
- `build_plan` derives the exact 3-fold + OOS geometry (train=120/gap=20/test=20, step=20, k=3, OOS=40) with fail-closed asserts: tests pairwise disjoint and contiguously tiled, `fold_N.test_end < oos_start`, OOS length exact, `train < gap < test` in index order, and `ValueError("insufficient history")` below 2 folds.
- `run_walk_forward` first pins the plan row via `repo.create_wf_plan` (append-only idempotent, `oos_pinned_at` recorded BEFORE any search reuse), then per fold resolves the PIT membership window through `resolve_universe_daily`, computes the shared `FactorSignalChain` with the per-fold `SignalChainConfig(end=test_end+horizon)` label buffer, records the 64-hex `membership_fingerprint` from `frame.resolved_universe`, and appends a `wf_folds` manifest with `effective_days >= 10`.
- The OOS fold is evaluated exactly once: `wf_folds` UNIQUE `(plan_id, fold_index, is_oos, strategy_id, params_sha256)` maps to `ValueError("OOS segment already evaluated")` on the second run — the WFWD-01 integrity boundary is live end-to-end.
- Search-fold reruns take the append-only query path (idempotent), so only the OOS write path exercises the exactly-once guard.

## Task Commits

Each task was committed atomically:

1. **Task 1: build walkforward.py (dataclasses + trading_calendar + build_plan)** - `2ab8291` (feat)
2. **Task 2: build run_walk_forward (PIT + shared chain + manifests + exactly-once OOS)** - `2ab8291` (feat, same commit — tasks 1+2 form one logical feat group)
3. **Task 3: test — tracer proof extended (chain_config end lock)** - `851cf0f` (test)

**Plan metadata:** pending (final docs commit follows state updates)

## Files Created/Modified

- `backend/app/backtest/walkforward.py` (new, 541 lines) — `WalkForwardFold` / `WalkForwardPlan` frozen slots dataclasses; `trading_calendar`; `build_plan`; `run_walk_forward`; per-fold `_run_fold`; `_effective_test_days`; `_fold_chain_config`; `_assert_geometry`; `fold_scorer` seam.
- `backend/tests/backtest/test_walkforward.py` (modified) — the Wave 0 tracer cases now additionally assert every manifest's `chain_config["end"] == test_end + horizon` (the FACT-06 label-buffer contract).

## Decisions Made

- **effective_days semantics:** computed as the count of test dates `d` in the fold for which the compute window `end = test_end + horizon` still has `horizon` trading dates after `d` — the last `horizon` dates of the extended window have null forward returns (chain `shift(-horizon)`) and are excluded. Asserted `>= 10` per fold; the Feb-2026 test fold (scorable days before the 14-day hole) passes with this definition.
- **Idempotency split:** search folds reuse the query path (`list_wf_folds` scan) so re-running a walk-forward is append-only-safe; the OOS fold always takes the write path so its UNIQUE exactly-once guard is what fires on double evaluation. This keeps both the idempotency contract and the integrity boundary live.
- **fold_scorer seam:** default = the fixed-params strategy backtest variant (train + test windows through `StrategyBacktestService`, stats recorded as `train_stats`/`test_stats`); the Phase 14 per-fold portfolio-optimization scorer plugs into the same geometry without forking.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `_default_fold_score` stats rejected by `record_wf_fold` `_json` path**
- **Found during:** Task 2 (`run_walk_forward` integration)
- **Issue:** `StubBacktestService.run` returns `SimpleNamespace(stats={...})`; `vars()` of a `SimpleNamespace` contains non-JSON-serializable key order but more importantly the plan called for backtest `stats` — the stub's `stats` dict is fine, but direct dict coercion of arbitrary result shapes is fragile.
- **Fix:** `_default_fold_score` explicitly copies `getattr(result, "stats", {}) or {}` into `stats["train_stats"]` / `stats["test_stats"]` and guards on `result.error is None`; only the serializable scalar dict enters `record_wf_fold(stats=...)`.
- **Files modified:** `backend/app/backtest/walkforward.py`
- **Verification:** `pytest tests/backtest/test_walkforward.py -q --tb=short` → 7 passed.
- **Committed in:** 2ab8291 (part of task 1+2 commit)

**2. [Rule 1 - Bug] `_effective_test_days` over the full calendar undercounted the Feb-2026 test fold**
- **Found during:** Task 2
- **Issue:** an earlier draft counted label sufficiency over the *entire* calendar, so the fold-1 test (ending 2026-03-27, with the 14-day CNY hole behind it) looked short of 10 effective days.
- **Fix:** the count is now scoped to the per-fold compute window (`day <= compute_end = test_end + horizon`) — the same window the chain actually scores — giving fold 1 `effective_days = 14 >= 10` (correctly reflecting the label buffer).
- **Files modified:** `backend/app/backtest/walkforward.py`
- **Verification:** all folds report `effective_days >= 10`; 7 passed.
- **Committed in:** 2ab8291

**3. [Rule 3 - Blocking] Ruff RUF007 flagged `zip(folds, folds[1:])`**
- **Found during:** Task 2 (pre-commit lint)
- **Issue:** `RUF007 Prefer itertools.pairwise()` on the adjacency loop in `_assert_geometry`.
- **Fix:** `for left, right in itertools.pairwise(folds)`.
- **Files modified:** `backend/app/backtest/walkforward.py`
- **Verification:** `ruff check` clean; 7 passed.
- **Committed in:** 2ab8291

**4. [Rule 2 - Missing Critical] Wave 0 scaffold never asserted the label-buffer contract it documents**
- **Found during:** Task 3 (tracer proof)
- **Issue:** the scaffold asserted fingerprint length + `effective_days >= 10` but only *commented* `chain_config end == test_end + horizon`; the FACT-06 anti train/serve-skew path the tracer exists to prove was unasserted.
- **Fix:** added per-manifest assertion `chain_config["end"] == (test_end + timedelta(days=plan.horizon)).isoformat()` for every fold (search + OOS).
- **Files modified:** `backend/tests/backtest/test_walkforward.py`
- **Verification:** 7 passed with the new assertion.
- **Committed in:** 851cf0f

---

**Total deviations:** 4 auto-fixed (2 blocking, 1 bug, 1 missing critical)
**Impact on plan:** All fixes were necessary for the tracer contract to hold (serializable manifests, correct effective-day semantics, lint gate, asserted label buffer). No scope creep.

## Issues Encountered

- None beyond the auto-fixed items above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **13-03 (OOS-scored parameter search):** `WalkForwardPlan.folds` / `plan.oos_fold` are ready for the structurally-excluding `WalkForwardOptimizer`; `wf_search_runs` repo method already fails closed on `oos_excluded != 1`; the exactly-once OOS guard is proven live, so the final `best_params` OOS evaluation will raise `ValueError` on double-run as designed.
- **13-05 (geometry robustness + breadth):** `build_plan` is already fail-closed on `fold_count < 2` (the `H ≈ 180` ceiling) and snaps to the measured calendar; `trading_calendar` re-measures at execution.
- No blockers.

---
*Phase: 13-walk-forward-validation-parameter-search*
*Completed: 2026-08-02*
## Self-Check: PASSED
