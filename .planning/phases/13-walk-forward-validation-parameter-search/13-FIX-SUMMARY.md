---
phase: 13-walk-forward-validation-parameter-search
fixed_at: 2026-08-02
source_review: 13-REVIEW.md
findings_in_scope: 16
fixed: 16
skipped: 0
status: all_fixed
---

# Phase 13: Code Review Fix Summary

**Fixed at:** 2026-08-02
**Source review:** `13-REVIEW.md` (1 BLOCKER + 10 WARNING + 5 INFO)

## Summary

- Findings in scope: 16
- Fixed: 16
- Skipped: 0

All 16 findings from the Phase 13 code review were fixed across 7 atomic commits.
Verification: `pytest tests/backtest -q` → **114 passed**; full main suite
`pytest -q --tb=short -p no:cacheprovider --ignore=tests/test_phase5_optional_host.py
--ignore=tests/shadow` → **1169 passed, 2 skipped**; `ruff check` clean on all
modified modules.

## Fixed Issues

### BL-01: Search trials scored on the full universe instead of the per-fold PIT membership universe

**Files modified:** `backend/app/backtest/optimizer.py`, `backend/tests/backtest/test_optimizer_run.py`
**Commit:** `8be11e6`
**Applied fix:** `WalkForwardOptimizer.optimize` accepts a `resolver`; each search
trial is now scored on the same per-fold PIT membership symbols the fold/OOS
scorer uses (`_fold_symbols(membership)`), never `symbols=None`. The search
universe (symbol count + per-fold counts + fingerprint) is persisted in
`search_space["universe"]` (→ `wf_search_runs.search_space_json`). Added the
orchestrator regression test
`test_wf_search_trials_use_per_fold_membership_symbols_when_resolver_passed`.

### WR-01: Reserved OOS evaluated per distinct params set via `run_walk_forward`

**Files modified:** `backend/app/backtest/walkforward.py`, `backend/tests/backtest/test_walkforward.py`
**Commit:** `c9a9807`
**Applied fix:** OOS evaluation gated behind `evaluate_oos: bool = False`
(default off). `run_walk_forward` now runs search folds only unless the caller
explicitly opts in; the only OOS write in the intended flow is best-params
validation (`evaluate_best_params`). Tests updated to pass `evaluate_oos=True`
where the OOS spine is under test, and the preheat assertion now locks that
search folds never touch OOS.

### WR-02: Failed OOS backtest permanently burns the exactly-once slot

**Files modified:** `backend/app/backtest/walkforward.py`, `backend/tests/backtest/test_walkforward.py`
**Commit:** `c9a9807`, `9ea598e`
**Applied fix:** `evaluate_best_params` now validates that `test_stats[objective]`
is present BEFORE the OOS fold row is persisted (`record_wf_fold`). A strategy
that fails to produce the objective in the OOS window raises ValueError with
nothing persisted, so a retry with corrected inputs is allowed. Added
`test_evaluate_best_params_wr02_no_oos_row_on_missing_objective`.

### WR-03: `create_wf_plan` idempotent re-create silently kept stale geometry

**Files modified:** `backend/app/research/repository.py`, `backend/tests/backtest/test_walkforward.py`
**Commit:** `35243e3`
**Applied fix:** On the idempotent re-create path, `create_wf_plan` compares the
incoming plan geometry (start/end/sizes/horizon/trading_dates/fold_geometry)
against the stored row and raises `ValueError` on divergence, so a re-measured
calendar / changed geometry can never silently keep a stale OOS reservation.
Added `test_create_wf_plan_raises_on_geometry_divergence`.

### WR-04: Optimizer never pinned the plan before `record_wf_search`

**Files modified:** `backend/app/backtest/optimizer.py`
**Commit:** `35243e3`
**Applied fix:** `WalkForwardOptimizer.optimize` calls idempotent
`repo.create_wf_plan(plan)` before any search bookkeeping when a repo is passed,
so FK failures on `record_wf_search` are no longer possible for un-pre-pinned plans.

### WR-05: Min-direction objectives reported negated `best_score`

**Files modified:** `backend/app/backtest/optimizer.py`, `backend/tests/backtest/test_optimizer_run.py`
**Commit:** `35243e3`, `9ea598e`
**Applied fix:** Per-fold `objective_raw` (raw metric) is preserved and used for
display/persistence; `best_score` and `per_trial`/`per_fold` distributions now
report the raw metric space (mirroring `StrategyOptimizer`), with the signed
value used only as the internal sort key. Added
`test_wf_search_min_direction_reports_raw_best_score` to lock the raw sign.

### WR-06: Verdict `fold_evidence` empty by default

**Files modified:** `backend/app/backtest/walkforward.py`
**Commit:** `b427637`
**Applied fix:** `evaluate_best_params` auto-feeds `fold_evidence` from the OOS
fold's own stats (`effective_days`/`train_stats`/`test_stats`) when the caller
omits it — the verdict never records an empty `{}`. Callers may still pass richer
per-fold search evidence (e.g. optimizer `score_distribution`).

### WR-07: `resolved_asset_ids` never populated on the validation path

**Files modified:** `backend/app/backtest/walkforward.py`, `backend/tests/backtest/test_walkforward.py`
**Commit:** `c9a9807`
**Applied fix:** `evaluate_best_params` resolves the OOS fold's PIT membership
symbols via the shared `_resolve_fold_membership` seam and passes them as
`resolved_asset_ids` to `record_validated_strategy`. Test assertion updated to
expect the membership symbols.

### WR-08: `build_plan` minimum threshold off by one

**Files modified:** `backend/app/backtest/walkforward.py`, `backend/tests/backtest/test_walkforward.py`
**Commit:** `b427637`
**Applied fix:** Threshold corrected to `oos + train + gap + 2*test + 1` (the
true minimum for a valid 2-fold build where the OOS gap buffer is non-empty).
Added `test_build_plan_boundary_220_fails_221_builds` and updated the
fail-closed message assertion to `minimum 221`.

### WR-09: Calendar-day label buffer does not guarantee finite labels through the whole test segment

**Files modified:** `backend/app/backtest/walkforward.py`, `backend/tests/backtest/test_walkforward.py`
**Commit:** `b427637`
**Applied fix:** `_fold_chain_config` now snaps the label buffer to `horizon`
TRADING days past `test_end` on the measured calendar (falls back to calendar
days only when the calendar has insufficient trailing days, e.g. the OOS fold at
the calendar end). Fully-covered search folds now achieve
`effective_days == test_size`; spine test asserts the trading-day snapping.

### WR-10: Fabricated `search_run_id` when no repo is supplied

**Files modified:** `backend/app/backtest/optimizer.py`, `backend/app/research/repository.py`, `backend/tests/backtest/test_optimizer_run.py`, `backend/tests/backtest/test_walkforward.py`
**Commit:** `35243e3`, `9ea598e`
**Applied fix:** `optimize(repo=None)` returns `search_run_id=None` instead of a
fabricated uuid. `record_validated_strategy` maps the `search_run_id` FK
IntegrityError to a clear message naming the missing search run. Test updated to
assert `None` for the no-repo path; added
`test_evaluate_best_params_wr10_unknown_search_run_fk_mapped`.

### IN-01: `_find_existing_fold` query path is cache-only

**Files modified:** `backend/app/backtest/walkforward.py`
**Commit:** `b427637`
**Applied fix:** Documented in the docstring that the query path is cache-only —
it does not re-verify chain config/fingerprint; membership drift is captured by a
new `params_sha256`/`plan_id`.

### IN-02: `record_wf_fold` mapped every IntegrityError to "OOS segment already evaluated"

**Files modified:** `backend/app/research/repository.py`
**Commit:** `35243e3`
**Applied fix:** Only genuine `UNIQUE constraint failed` violations map to the
OOS/existing-fold messages; FK (missing plan) and CHECK failures now surface
with the underlying DB error.

### IN-03: Ensemble date filter used string coercion

**Files modified:** `backend/app/backtest/ensemble.py`
**Commit:** `aea70b6`
**Applied fix:** `build_ensemble` window filter compares `pl.col("date").cast(pl.Date)`
against `pl.Date` literals (new `_to_date` helper) instead of string-lexicographic
comparison, robust to `Datetime`-dtype date columns.

### IN-04: `_default_fold_score` symbol set is the window union, not per-date membership

**Files modified:** `backend/app/backtest/walkforward.py`
**Commit:** `b427637`
**Applied fix:** Documented the window-union semantics and the survivorship
neutralization by data availability; strict per-date membership join on the
backtest panel is noted as Phase 14 work.

### IN-05: Ensemble rank `method="max"` deviation from the plan

**Files modified:** `backend/app/backtest/ensemble.py`
**Commit:** `aea70b6`
**Applied fix:** Documented the deliberate `method="max"` tie semantics (mean 2.0
→ 2.0, locked by the scaffold contract) in the module contract; the Phase 14
consumer confirms the tie semantics downstream.

---

_Fixed: 2026-08-02_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
