---
status: clean
phase: 13-walk-forward-validation-parameter-search
reviewed: 2026-08-02
depth: standard
files_reviewed: 14
resolved: 2026-08-02
files_reviewed_list:
  - backend/app/backtest/walkforward.py
  - backend/app/backtest/ensemble.py
  - backend/app/backtest/optimizer.py
  - backend/app/backtest/strategy.py
  - backend/app/research/repository.py
  - backend/app/research/signal_chain.py
  - backend/app/research/universe.py
  - backend/app/research/artifacts.py
  - backend/app/operational/migrations.py
  - backend/tests/backtest/test_walkforward.py
  - backend/tests/backtest/test_ensemble.py
  - backend/tests/backtest/test_optimizer_run.py
  - backend/tests/backtest/conftest.py
  - backend/tests/test_operational_migrations.py
findings:
  blocker: 1
  warning: 10
  info: 5
  total: 16
---

# Phase 13: Code Review Report — Walk-Forward Validation & Parameter Search

**Reviewed:** 2026-08-02
**Depth:** standard
**Files Reviewed:** 14
**Status:** findings

## Summary

Phase 13 lands the validation layer: measured-calendar walk-forward geometry (`build_plan`), the shared-chain per-fold runner (`run_walk_forward`), the OOS-scored search (`WalkForwardOptimizer`), the exactly-once OOS validation gate (`evaluate_best_params`), and the rank-average ensemble (`build_ensemble`/`save_ensemble`), backed by five append-only `wf_*` tables.

**Verified-good (positive findings):**
- The rolling (non-expanding) fold geometry is correct: train=120/gap=20/test=20, step=20, k=3, OOS=40 with a non-empty buffer; test segments tile contiguously and are pairwise disjoint; fold boundaries snap to the *measured* calendar (Feb 2026 CNY hole respected — verified empirically: each fold test window has exactly 20 distinct dates); `timedelta` is used only for the label buffer (1 occurrence, grep gate satisfied); no hard-coded fold dates.
- The fail-closed geometry guard works for the general case: `< 180` measured days raises a clear "insufficient history" error; 221+ days builds 2 folds.
- Per-fold PIT is genuinely per-fold: `_run_fold` resolves `resolve_universe_daily` over `[train_start - warmup, test_end + horizon]`, computes the SHARED `FactorSignalChain` with a per-fold `SignalChainConfig(end=test_end+horizon)`, and records the chain's `membership_fingerprint` (which changes when membership changes — Pitfall-5 contract proven by test).
- `effective_days` label-buffer accounting is internally consistent (verified: fold eff=18/20 with buffer, OOS eff=35/40) and the `< 10` guard raises before any fold row is written.
- The `wf_*` schema is append-only with `no_update`/`no_delete` triggers, CHECKs on 64-hex digests, FK graph (folds→plan, verdicts→plan/search/fold, OOS evidence UNIQUE), and `UNIQUE (plan_id, fold_index, is_oos, strategy_id, params_sha256)` exactly-once key. Migration tests cover triggers, FKs, UNIQUE, idempotence.
- Security posture: no execution authority anywhere; artifacts go through `write_bundle` (O_EXCL + fsync + sha256); no scipy/manual rank loop in `ensemble.py`; repository SQL is parameterized; `resolve_universe_daily` is read-only.
- All Phase 13 gates pass: 47 backtest tests + 13 migration tests (60 total) green; ruff clean on all 5 changed app modules.

Findings below focus on correctness/robustness defects that survived the green suite.

## Findings Table

| # | Severity | File | Line/Function | Issue | Recommendation |
|---|----------|------|---------------|-------|----------------|
| BL-01 | BLOCKER | backend/app/backtest/optimizer.py | `WalkForwardOptimizer._run_one` L373-394 | Search trials run `StrategyBacktestConfig(symbols=None, …)` over the test window — the FULL lake universe, not the per-fold PIT membership symbols that the fold manifests and OOS validation use (`_fold_symbols(membership)`). `best_params` are therefore selected on a different (broader) universe than the OOS "unbiased estimate", and the search path never calls `resolve_universe_daily` / never goes through the shared chain. This is exactly the selection/validation universe skew WFWD-02 must prevent. | Score each search trial with the same per-fold PIT membership as `_default_fold_score` (e.g. thread each fold's `_fold_symbols(membership)` through the optimizer, or route trials through a shared fold-scorer seam). At minimum, record the search universe in `wf_search_runs.search_space_json` so the skew is auditable. |
| WR-01 | WARNING | backend/app/backtest/walkforward.py | `run_walk_forward` L217; migrations `UNIQUE` L1748 | The reserved OOS is evaluated once per `(plan, fold, is_oos, strategy, params_sha256)`, and `run_walk_forward` evaluates the OOS with whatever params are passed. The intended flow (and the test `test_evaluate_best_params_oos_exactly_once_and_validation_gate`) preheats the OOS with exploration params 0.01 *before* the best-params 0.02 evaluation — i.e. the reserved OOS is touched by a non-best params set, contradicting WFWD-01 "evaluated exactly once and never touched by selection or parameter search". | Make OOS evaluation opt-in: add an `evaluate_oos: bool = False` guard to `run_walk_forward` (search/exploration calls omit it), so the only OOS write path is `evaluate_best_params`. |
| WR-02 | WARNING | backend/app/backtest/walkforward.py | `evaluate_best_params` L264-281 | The OOS fold row is written (exactly-once slot consumed) inside `_run_folds` BEFORE `test_stats[objective]` is confirmed present. If the OOS test backtest errors (e.g. strategy produces no entry signals in the OOS window), `_default_fold_score` leaves `test_stats` empty, `raw is None` raises, the verdict is never recorded — but the OOS fold row is already persisted and a retry with the same params raises "OOS segment already evaluated". A transient backtest failure permanently burns the once-evaluation. | Extract/validate the objective from the fold scorer before writing the fold row, or write the OOS fold only after the verdict is computable; otherwise allow a retry when the fold row has no test_stats. |
| WR-03 | WARNING | backend/app/research/repository.py | `create_wf_plan` L862-887 | Idempotent re-create suppresses *all* `IntegrityError`s and returns the existing row. If the same `plan_id` is re-pinned with a re-measured calendar / changed geometry, the new geometry is silently ignored and the OOS reservation silently stays stale (the re-measurement contract in 13-05). No equality check between the incoming plan and the persisted geometry. | Before returning the existing row, compare `trading_dates_json`/`fold_geometry_json` (or a geometry sha256) and raise a clear error on mismatch. |
| WR-04 | WARNING | backend/app/backtest/optimizer.py | `WalkForwardOptimizer.optimize` L461-476 | The optimizer never calls `repo.create_wf_plan(plan)`. With a repo, `record_wf_search` FK-fails with a raw `sqlite3.IntegrityError` if the plan wasn't pre-pinned (the test explicitly pre-pins; a user following the API without that step hits an unmapped DB error). | Call `repo.create_wf_plan(plan)` (idempotent) at the start of `optimize`, or wrap the FK error into a ValueError naming the missing plan. |
| WR-05 | WARNING | backend/app/backtest/optimizer.py | `_run_one` L388-410; L436-437 | For min-direction objectives (`avg_holding_days`), the trial-level `objective_raw` is set to the direction-adjusted `pooled` value (negated), not the raw stat, and `best_score` is the negated pooled mean. `evaluate_best_params` reads the *raw* `test_stats[objective]` (positive). A researcher comparing search `best_score` with the OOS `validation_score` sees opposite signs for min-direction objectives, and `wf_search_runs.best_score` stores the negated value. | Preserve raw per-fold stats at the trial level and report `best_score` in the raw metric space (as `StrategyOptimizer` does via `objective_raw`), keeping only an internal sort key signed. |
| WR-06 | WARNING | backend/app/backtest/walkforward.py | `evaluate_best_params` L296 | The validation verdict's `fold_evidence_json` defaults to `{}` unless the caller hand-passes per-fold scores; the plan expects the verdict to carry the per-fold search evidence. A caller invoking `evaluate_best_params` directly (as the tests do) loses the audit trail of the per-fold scores that produced the verdict. | Wire the search's per-fold results into `fold_evidence` automatically (e.g. accept the `score_distribution`/`results` from the optimizer), or validate that `fold_evidence` is non-empty before recording a verdict. |
| WR-07 | WARNING | backend/app/backtest/walkforward.py | `evaluate_best_params` L289-298 | `resolved_asset_ids` is never populated by the primary validation path (defaults to `[]`), so the Phase 14 "bind composite snapshot without re-resolving" contract (research Open Question Q3) is not met by the default flow. The column exists and round-trips, but every verdict produced through `evaluate_best_params` carries an empty list. | Resolve the OOS fold's membership symbols (already available as `_fold_symbols(membership)`) and pass them as `resolved_asset_ids` when recording the verdict. |
| WR-08 | WARNING | backend/app/backtest/walkforward.py | `build_plan` L130-150; `_build_oos_fold` L382-412; `_assert_geometry` L449-456 | The documented fail-closed threshold is off by one: the message/test claim "minimum 220", but a 220-day calendar fails in `_assert_geometry` with "fold rectangle must keep train < gap < test in index order" (the OOS gap buffer is empty at 220; the true minimum for a valid 2-fold build is 221). At the boundary the error is misleading and the claimed minimum is not buildable. | Use `oos + train + gap + 2*test + 1` as the true minimum (or make the OOS gap tolerantly zero-length), and assert the boundary in a test. |
| WR-09 | WARNING | backend/app/backtest/walkforward.py | `_fold_chain_config` L432; `_effective_test_days` L610-628 | The label buffer is `test_end + horizon` CALENDAR days, but the chain's forward-return drop is ROW-based (`close.shift(-horizon)` per symbol = `horizon` trading days). Across weekends/holidays the calendar buffer can supply fewer than `horizon` trading days, so the last few test days are silently unscorable (verified: fold eff=18/20 even with the buffer; a 14-day CNY hole or long holiday would shrink it further). The "labels finite through the whole test segment" guarantee is therefore not met. | Buffer by trading days (snap `end` to `horizon` trading days past `test_end` on the measured calendar) rather than calendar days, or at least document `effective_days < test_size` as expected and make the fold scorer use only scorable days. |
| WR-10 | WARNING | backend/app/backtest/optimizer.py | `optimize` L459, L479-491 | When `repo is None`, `search_run_id = uuid4().hex` is fabricated but never persisted. Passing that id later to `evaluate_best_params(search_run_id=…)` violates the `wf_validated_strategies.search_run_id` FK and raises a *misleading* "validation verdict conflicts with a persisted OOS evidence fold" error. | Return `search_run_id=None` (or a persisted id) when no repo is provided, and map FK IntegrityErrors in `record_validated_strategy` to a message naming the missing search run. |
| IN-01 | INFO | backend/app/backtest/walkforward.py | `_find_existing_fold` L533-552 | The search-fold query path returns the existing row without re-verifying the fold's `chain_config`/fingerprint; a re-run with the same params after membership drift silently returns the stale manifest (the membership-drift test only proves fingerprints change for *different* params). Acceptable append-only behavior, but easy to misread as freshness. | Document that the query path is cache-only; optionally hash the current fold config into the lookup key. |
| IN-02 | INFO | backend/app/research/repository.py | `record_wf_fold` L955-966 | Any `IntegrityError` on an `is_oos` row is mapped to "OOS segment already evaluated", which can mask FK (missing plan) or CHECK failures. | Inspect the error message/`sqlite3.Error` code and only map genuine UNIQUE violations to the OOS message. |
| IN-03 | INFO | backend/app/backtest/ensemble.py | `build_ensemble` L91-93 | The date-window filter compares `pl.col("date").cast(pl.Utf8)` lexicographically against ISO strings; a `Datetime`-dtype date column would serialize as `"2026-07-01 00:00:00"` and fail the inclusive upper bound. Works for the chain's `Date` dtype and test string frames, but fragile to dtype drift. | Cast with `pl.col("date").dt.date()` (or compare against a `pl.Date` literal) instead of string coercion. |
| IN-04 | INFO | backend/app/backtest/walkforward.py | `_default_fold_score` L556-589 | The fold/OOS test backtest uses the window-UNION symbol set (`_fold_symbols`), not per-date membership. Survivorship is mostly neutralized by data availability (delisted symbols have no test-window rows), but it is not the chain's per-date membership semantics. | If strict per-date PIT is required for the score, apply the per-date membership join to the backtest panel as the chain does. |
| IN-05 | INFO | backend/app/backtest/ensemble.py | `build_ensemble` L107-112 | `ensemble_rank` uses `rank(method="max")` — a documented deviation from the plan's `method="average"` (module docstring + 13-04-SUMMARY). Ties collapse to the top of the tied block (two tied at rank 2.0 → both 2.0) instead of the average (1.5). Changes downstream rank semantics for Phase 14. | Confirm the tie semantics with the Phase 14 consumer; if average-rank is desired, use `method="average"` and update the scaffold contract accordingly. |

## BLOCKER

### BL-01: Search trials are scored on the full universe, not the per-fold PIT membership universe

**File:** `backend/app/backtest/optimizer.py:373-394` (`WalkForwardOptimizer._run_one`)

**Issue:** Each search trial runs `StrategyBacktestConfig(strategy_id=…, symbols=None, start=fold.test_start, end=fold.test_end, params=combo, …)` directly through `StrategyBacktestService`. `symbols=None` loads the entire lake universe for the test window. The fold manifests (`run_walk_forward` → `_default_fold_score`) and the OOS validation (`evaluate_best_params` → `_default_fold_score`) instead pass `symbols=_fold_symbols(membership)` — the per-fold PIT membership symbol set resolved by `resolve_universe_daily`. Consequence:

- `best_params` are selected on a universe that includes symbols outside the PIT membership (delisted/never-listed), while the "unbiased estimate" (OOS) is computed on the PIT universe.
- The search path never calls `resolve_universe_daily` and never computes the shared `FactorSignalChain` per fold — so WFWD-02's "scored on walk-forward folds" is satisfied only at the window level, not at the PIT-universe level the phase mandates (must-have #2, FACT-06).
- The search `best_score` and the OOS `validation_score` are not directly comparable, weakening the multiple-comparison guard (T-13-03).

The existing test `test_wf_search_scores_test_folds_only_never_oos` asserts only the *windows* (`start/end`), not the *universe*, so the defect is green-lit.

**Fix:** Score each trial with the same per-fold membership the fold/OOS scorer uses. Concretely, either (a) thread each `search_fold`'s resolved membership symbols into the optimizer (e.g. store `symbols` on `WalkForwardFold` after resolution, or have the optimizer resolve via the same resolver), or (b) route every trial through the shared fold-scorer seam so there is exactly one scoring implementation. Persist the search universe (symbol count / a universe fingerprint) in `wf_search_runs.search_space_json` for auditability.

## Warnings

### WR-01: Reserved OOS is evaluated for non-best params via `run_walk_forward`

`run_walk_forward` always includes `plan.oos_fold` in the fold set (L217), and the exactly-once guard is keyed on `params_sha256`, so the OOS is evaluated once *per distinct params set*. The shipped test `test_evaluate_best_params_oos_exactly_once_and_validation_gate` preheats the OOS with params 0.01 before the best-params 0.02 evaluation — proving the OOS is touched by an exploratory params set in the intended flow. This contradicts WFWD-01's "evaluated exactly once and never touched by selection or parameter search." **Fix:** gate OOS evaluation behind an explicit flag (default off) so exploration via `run_walk_forward` does not touch the OOS.

### WR-02: Failed OOS backtest permanently consumes the exactly-once slot

`evaluate_best_params` calls `_run_folds` (which writes the OOS fold row) *before* checking `test_stats[objective]`. A strategy that fails to produce the objective in the OOS window leaves `test_stats` empty → ValueError raised after the row is persisted → the params key can never be re-evaluated (the UNIQUE fires on retry). **Fix:** confirm the objective is present before persisting the OOS fold row, or permit retry when the persisted row has no `test_stats`.

### WR-03: `create_wf_plan` idempotency silently keeps stale geometry

The `suppress(IntegrityError)` + query-path re-create returns the existing row for *any* IntegrityError, including a same-`plan_id` re-pin with a re-measured calendar / different `train_size` etc. The OOS reservation silently stays stale; no mismatch is reported. **Fix:** compare the incoming plan's serialized geometry to the stored row and raise on divergence.

### WR-04: Optimizer does not pin the plan before `record_wf_search`

With a repo, `WalkForwardOptimizer.optimize` FK-fails on `record_wf_search` if the plan was not pre-pinned, surfacing a raw `sqlite3.IntegrityError` (unmapped). **Fix:** call `repo.create_wf_plan(plan)` (idempotent) inside `optimize`.

### WR-05: Min-direction objectives report negated `best_score` in the search path

`objective_value` negates min-direction stats, and the trial `objective_raw`/`best_score` are the (negated) pooled values, while `evaluate_best_params` uses the raw stat. `wf_search_runs.best_score` can therefore store `-1.0` for a 1.0-day `avg_holding_days`. **Fix:** keep raw per-fold stats for display/persistence and use the signed value only as an internal sort key (mirror `StrategyOptimizer`).

### WR-06: Verdict `fold_evidence` empty by default

`evaluate_best_params` records `fold_evidence or {}`. The per-fold search evidence the plan expects in the verdict is not attached automatically. **Fix:** feed the optimizer's per-fold results into the verdict, or require non-empty `fold_evidence`.

### WR-07: `resolved_asset_ids` never populated on the validation path

Every verdict produced by `evaluate_best_params` carries `resolved_asset_ids == []`, so Phase 14 cannot bind the composite snapshot "without re-resolving" as designed. **Fix:** resolve the OOS fold membership symbols and pass them into `record_validated_strategy`.

### WR-08: `build_plan` minimum threshold is off by one

At exactly 220 measured days the build fails with "fold rectangle must keep train < gap < test in index order" (empty OOS buffer), not the documented "insufficient history / minimum 220" message; the real minimum for a valid 2-fold build is 221. **Fix:** correct the threshold to `oos + train + gap + 2*test + 1` and add a boundary test at 220/221.

### WR-09: Calendar-day label buffer does not guarantee labels finite through the whole test segment

`end = test_end + horizon` calendar days, but the chain's label drop is `horizon` trading days (rows). Weekends/holidays reduce the buffer below `horizon` trading days, silently shrinking scorable test evidence (measured 18/20). **Fix:** snap the buffer to `horizon` trading days on the measured calendar (or otherwise guarantee `effective_days == test_size` when the fold is fully covered).

### WR-10: Fabricated `search_run_id` when no repo is supplied

`optimize(repo=None)` returns a `uuid4().hex` that was never persisted; passing it to `evaluate_best_params` triggers an FK violation surfaced as a misleading "validation verdict conflicts" error. **Fix:** return `None` (or persist) when no repo is provided, and map the FK IntegrityError to a clear message.

## Info

- **IN-01** (`_find_existing_fold`): query path returns stale manifests on same-params re-runs without re-verifying config/fingerprint — documented as cache-only.
- **IN-02** (`record_wf_fold` error mapping): FK/CHECK IntegrityErrors are mislabeled as "OOS segment already evaluated" — now maps only genuine UNIQUE violations.
- **IN-03** (`build_ensemble` date filter): string-lexicographic window compare is fragile for `Datetime`-dtype date columns — now compares against `pl.Date` literals.
- **IN-04** (`_default_fold_score`): fold/OOS score symbol set is the window union, not per-date membership; survivorship is mostly neutralized by data availability but is not the chain's semantics — documented in module contract.
- **IN-05** (`build_ensemble` rank method): `method="max"` is a documented deviation from the plan's `method="average"`; tie semantics (mean 2.0 → 2.0) locked by the scaffold contract and documented in module docstring — Phase 14 consumer confirms.

---

## Resolved

All 16 findings fixed in 6 atomic commits:

| # | Fix | Commit |
|---|-----|--------|
| BL-01 | Search trials scored on per-fold PIT membership symbols (thread `_fold_symbols(membership)` via new `resolver` param); search universe persisted in `search_space["universe"]`; orchestrator regression test | `8be11e6` |
| WR-01 | OOS evaluation gated behind `evaluate_oos: bool = False` (default off) | `c9a9807` |
| WR-02 | OOS objective validated BEFORE the exactly-once fold row is persisted; retry no longer burns the slot | `c9a9807` (+ regression test in `9ea598e`) |
| WR-03 | `create_wf_plan` compares incoming vs stored geometry; raises on divergence | `35243e3` |
| WR-04 | `optimize` pins the plan via idempotent `repo.create_wf_plan(plan)` before `record_wf_search` | `35243e3` |
| WR-05 | `best_score` / per-fold values report raw objective space; signed value is internal sort key only | `35243e3` (+ raw pooled `objective_raw` fix in `9ea598e`) |
| WR-06 | `fold_evidence` auto-fed with the OOS fold stats when omitted (never `{}`) | `b427637` |
| WR-07 | OOS fold membership symbols resolved and passed as `resolved_asset_ids` | `c9a9807` |
| WR-08 | `build_plan` minimum corrected to `oos+train+gap+2*test+1`; 220/221 boundary test | `b427637` |
| WR-09 | Label buffer snapped to `horizon` trading days on the measured calendar (search folds fully covered → `effective_days == test_size`) | `b427637` |
| WR-10 | `repo=None` returns `search_run_id=None`; FK IntegrityError mapped to a clear missing-search-run message | `35243e3` (+ regression test in `9ea598e`) |
| IN-01 | Query path documented as cache-only | `b427637` |
| IN-02 | Only genuine UNIQUE violations map to "OOS segment already evaluated" | `35243e3` |
| IN-03 | Ensemble window filter compares `pl.Date` literals | `aea70b6` |
| IN-04 | Window-union vs per-date membership documented in `_default_fold_score` | `b427637` |
| IN-05 | Rank `method="max"` tie semantics documented in module contract | `aea70b6` |

**Verification:** `pytest tests/backtest -q` → 114 passed; full main suite `pytest -q --tb=short -p no:cacheprovider --ignore=tests/test_phase5_optional_host.py --ignore=tests/shadow` → 1169 passed, 2 skipped; ruff clean.

---

_Reviewed: 2026-08-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
_Resolved: 2026-08-02_
