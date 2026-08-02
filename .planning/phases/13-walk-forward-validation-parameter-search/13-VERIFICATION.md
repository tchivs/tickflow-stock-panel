---
phase: 13-walk-forward-validation-parameter-search
verified: 2026-08-02T00:00:00Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0 # every behavior-dependent truth has a passing named test (exactly-once OOS, evaluate_oos gate, per-fold PIT scoring)
overrides_applied: 0
gaps: []
human_verification:
  - test: "Run the fold-planner over the actual enriched governed panel (trading_calendar via the real BacktestEngine.load_panel date-only probe) and confirm the measured A-share calendar: Feb-2026 CNY month yields 14 trading days, and a real walk-forward run (run_walk_forward + WalkForwardOptimizer + evaluate_best_params) completes end-to-end on a real strategy."
    expected: "trading_calendar returns the real measured trading dates (Feb-2026 = 14 days, never a synthetic weekday calendar); build_plan derives 3 folds + reserved OOS snapped to those dates; a real run records per-fold manifests (membership_fingerprint, effective_days >= 10) and the OOS is evaluated exactly once."
    why_human: "Requires the real governed panel + heavy BacktestEngine + enriched lake data. Automated coverage uses the deterministic synthetic measured_calendar fixture (conftest) with the 14-trading-day CNY hole; the real-panel probe is the 13-VALIDATION.md manual-only item and cannot run in a read-only verification without the production datastore."
    result: "SATISFIED 2026-08-02 via scripts/probe_phase13.py on the real governed lake: measured calendar 241 trading days 2025-08-01..2026-07-30; Feb-2026 = 14 trading days (CNY); build_plan derived 3 folds + reserved OOS 2026-06-04..2026-07-30 snapped to measured dates; run_walk_forward recorded 3 fold manifests each effective_days=20 with membership_fingerprint; WalkForwardOptimizer ran 3 OOS-excluded trials. OOS exactly-once is DB-enforced (UNIQUE, covered by automated tests)."
---

# Phase 13: Walk-Forward Validation & Parameter Search Verification Report

**Phase Goal:** Researchers can validate strategies and tune parameters on rolling walk-forward folds with a reserved, once-evaluated final OOS segment, and ensemble validated strategies by rank-averaged signals.
**Verified:** 2026-08-02
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (PLAN.md must_haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Researcher can run rolling (non-expanding) walk-forward validation on the measured A-share calendar with an explicit gap between train and test, disjoint recorded test folds, and a reserved final OOS segment evaluated exactly once and never touched by selection or parameter search (WFWD-01). | ✓ VERIFIED | `walkforward.py:build_plan` — index-sliced train/gap/test rectangles snapped to a measured date list, `_assert_geometry` (disjoint + contiguously tiled, `fold_N.test_end < oos_start`, exact OOS length), `WF_GAP=20` gap, fail-closed below 2 folds with measured-count message, WR-08 minimum `oos+train+gap+2*test+1`. `run_walk_forward(evaluate_oos=False)` default never writes the OOS (WR-01); `wf_folds UNIQUE (plan_id, fold_index, is_oos, strategy_id, params_sha256)` maps to `ValueError("OOS segment already evaluated")`. Tests pass: `test_run_walk_forward_pins_plan_and_records_fingerprints`, `test_evaluate_best_params_oos_exactly_once_and_validation_gate`, `test_build_plan_derives_three_folds_with_gap_and_reserved_oos`, `test_calendar_snapping_respects_feb_2026_cny_hole`, `test_build_plan_boundary_220_fails_221_builds` (ran, 5/5 green). |
| 2 | Every fold resolves its own PIT universe via resolve_universe_daily, records a membership_fingerprint in its manifest, and runs the SHARED FactorSignalChain through a per-fold SignalChainConfig whose end = test_end + horizon so labels are finite through the whole test segment (WFWD-01 + FACT-06). | ✓ VERIFIED | `walkforward.py:_run_fold` → `_resolve_fold_membership` calls `resolver.resolve_universe_daily(universe_name, start=train_start-120d, end=fold.chain_config.end)`; `_fold_chain_config` snaps the label buffer to `horizon` TRADING days past test_end (WR-09) and always sets `SignalChainConfig(start=train_start, end=buffer_end, forward_return_horizon=horizon)`; the per-fold config flows into the ONE shared `FactorSignalChain.compute` (FACT-06 — no second compute path); 64-hex `membership_fingerprint` read from `frame.resolved_universe` (signal_chain.py `_resolved_universe`). `effective_days` asserted >= 10 per fold; fully-covered search folds get `effective_days == test_size`. Tests pass: `test_membership_fingerprint_changes_when_membership_changes`, `test_run_walk_forward_effective_days_below_10_raises`, `test_run_walk_forward_pins_plan_and_records_fingerprints` (chain_config end + fingerprint length asserts) (ran, 3/3 green). |
| 3 | Researcher can run parameter optimization scored on walk-forward OOS folds only (never in-sample), with n_trials / search_space / score_distribution recorded on an append-only wf_search_runs row whose oos_excluded=1 is enforced (WFWD-02). | ✓ VERIFIED | `optimizer.py:WalkForwardOptimizer.optimize` — `search_folds = [f for f in plan.folds if not f.is_oos]`; fail-closed if a plan leaks `is_oos` into folds; every trial runs `StrategyBacktestConfig(start=fold.test_start, end=fold.test_end)` (test windows only, never train/OOS); BL-01 fix: trials threaded with per-fold `_fold_symbols(membership)` via the new `resolver` param (never `symbols=None`), search universe persisted in `search_space["universe"]`; WR-04 pins the plan via idempotent `repo.create_wf_plan(plan)`; WR-05 `best_score` in raw metric space; WR-10 `repo=None` → `search_run_id=None`. `repository.record_wf_search` raises `ValueError("...oos_excluded=1")` unless `oos_excluded == 1` (caller hard-codes 1). Tests pass: `test_wf_search_scores_test_folds_only_never_oos`, `test_wf_search_never_scores_train_or_oos_windows`, `test_wf_search_folds_exclude_plan_oos_fold`, `test_wf_search_oos_excluded_zero_fails_closed`, `test_wf_search_records_trial_space_and_score_distribution`, `test_wf_search_trials_use_per_fold_membership_symbols_when_resolver_passed` (ran, 6/6 green). |
| 4 | The final OOS run of best_params is the unbiased estimate: the OOS fold row is UNIQUE exactly-once (a second evaluation raises ValueError) and wf_validated_strategies requires the OOS evidence fold id (WFWD-02). | ✓ VERIFIED | `walkforward.py:evaluate_best_params` — WR-02 validates `test_stats[objective]` present BEFORE `record_wf_fold` (no slot burn on failure); OOS row written via `repo.record_wf_fold(is_oos=True)` → UNIQUE fires `ValueError` on the second evaluation; verdict `record_validated_strategy` requires `oos_evidence_fold_id` UNIQUE → wf_folds(id) and persists `resolved_asset_ids` (WR-07), non-empty `fold_evidence` (WR-06), mechanical gate `passed_gate` (min `<=`, max `>=`); WR-10 unknown search_run FK mapped to a clear error. Migration: `wf_folds UNIQUE (plan_id, fold_index, is_oos, strategy_id, params_sha256)`; `wf_validated_strategies.oos_evidence_fold_id TEXT NOT NULL UNIQUE REFERENCES wf_folds(id)`. Tests pass: `test_evaluate_best_params_oos_exactly_once_and_validation_gate` (exactly-once + verdict binding + preheat never writes OOS), `test_evaluate_best_params_wr02_no_oos_row_on_missing_objective`, `test_evaluate_best_params_wr10_unknown_search_run_fk_mapped`, `test_evaluate_best_params_threshold_gate_min_and_max_direction` (ran, 4/4 green). |
| 5 | Researcher can ensemble validated strategies by rank-averaging their per-date cross-sectional _rank signals; only passed_gate=1 strategies enter (else fail closed) and the output binds an input_snapshot_sha256 + checksum-verified artifact (WFWD-03). | ✓ VERIFIED | `ensemble.py:build_ensemble` — Polars `group_by(symbol, date)` weighted mean of per-strategy `_rank`, per-date re-rank (`method="max"`, documented tie semantics IN-05) → `[symbol, date, ensemble_rank, ensemble_zscore]`; `_validate_gate` requires every strategy resolve via `repo.list_validated_strategies(strategy_id, passed_gate=True)` and every `validation_record_id` ∈ passed ids, else `ValueError` (fail-closed; repo is a required kwarg); IN-03 window filter compares `pl.Date` literals. `save_ensemble` writes via `EvaluationArtifactService.write_bundle` (O_EXCL + fsync + sha256), records `wf_ensembles` row binding `input_snapshot_sha256` (sorted strategy_ids, weights, validation_record_ids, membership_fingerprint) + `output_sha256` + artifact path; idempotent same name+snapshot, ValueError on same-name-different-input. Tests pass: `test_build_ensemble_rank_averages_validated_signals`, `test_build_ensemble_fails_closed_on_unvalidated_strategy`, `test_build_ensemble_fails_closed_on_non_passed_gate_record`, `test_save_ensemble_persists_checksum_verified_artifact` (ran, 4/4 green). |

**Score:** 5/5 truths verified (0 present-but-behavior-unverified — every behavior-dependent truth has a passing named test)

### ROADMAP Success Criteria → Code + Test Evidence

| Criterion | Concrete code path | Automated test evidence | PASS/FAIL |
|-----------|--------------------|------------------------|-----------|
| 1. Rolling (non-expanding) walk-forward with explicit gap, disjoint recorded folds; reserved final OOS evaluated exactly once, never touched by selection/search | `walkforward.py:build_plan` (index-sliced rectangles, gap, `_assert_geometry` disjoint/tiled), `_build_oos_fold`, `run_walk_forward(evaluate_oos=False)` (WR-01 gate), `evaluate_best_params` (WR-02 objective-before-persist), `wf_folds` UNIQUE exactly-once, `wf_plans.oos_pinned_at` (reservation before any search reuse) | `test_build_plan_derives_three_folds_with_gap_and_reserved_oos`, `test_run_walk_forward_pins_plan_and_records_fingerprints` (preheat writes 0 OOS rows; 2nd evaluation raises), `test_evaluate_best_params_oos_exactly_once_and_validation_gate`, `test_build_plan_boundary_220_fails_221_builds` — **all passed** | ✓ PASS |
| 2. Parameter optimization scored on walk-forward OOS folds (never in-sample), trial count / search space / score distribution recorded (multiple-comparison guard) | `optimizer.py:WalkForwardOptimizer.optimize` (test-windows only, OOS structural exclusion, GRID cap, per-combo isolation, BL-01 per-fold PIT symbols), `repository.record_wf_search` (`oos_excluded=1` fail-closed, `search_space`/`score_distribution`/`n_trials` persisted), `evaluate_best_params` exactly-once OOS + `wf_validated_strategies` verdict | `test_wf_search_scores_test_folds_only_never_oos`, `test_wf_search_never_scores_train_or_oos_windows`, `test_wf_search_folds_exclude_plan_oos_fold`, `test_wf_search_records_trial_space_and_score_distribution`, `test_wf_search_persists_search_run_row_when_repo_passed`, `test_wf_search_oos_excluded_zero_fails_closed` — **all passed** | ✓ PASS |
| 3. Ensemble validated strategies via rank-average of their signals | `ensemble.py:build_ensemble` (per-(symbol,date) weighted `_rank` mean + per-date re-rank), `_validate_gate` (passed_gate=1 only, fail-closed, repo required), `save_ensemble` (O_EXCL+fsync+sha256 artifact + `wf_ensembles` row with input/output digests) | `test_build_ensemble_rank_averages_validated_signals`, `test_build_ensemble_fails_closed_on_unvalidated_strategy`, `test_build_ensemble_fails_closed_on_non_passed_gate_record`, `test_save_ensemble_persists_checksum_verified_artifact`, `test_ensemble_gate_consumes_passed_gate_filtered_reports` — **all passed** | ✓ PASS |

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| WFWD-01 | Rolling (non-expanding) walk-forward, explicit gap, disjoint recorded folds, reserved final OOS evaluated exactly once and never touched by selection/search | ✓ SATISFIED | `walkforward.py` + `wf_plans`/`wf_folds` migration + `test_walkforward.py` (16 green) |
| WFWD-02 | Parameter optimization scored on walk-forward OOS folds (never in-sample), trial count/search space/score distribution recorded | ✓ SATISFIED | `optimizer.py:WalkForwardOptimizer` + `wf_search_runs`/`wf_validated_strategies` + `test_optimizer_run.py` OOS cases (21 green) |
| WFWD-03 | Ensemble validated strategies via rank-average of their signals | ✓ SATISFIED | `ensemble.py` + `wf_ensembles` + `test_ensemble.py` (10 green) |

No ORPHANED requirements: WFWD-01..03 all claimed by 13-01..13-05 plans and all implemented.

### Cross-Module Integrity

| Integrity check | Evidence | Status |
|-----------------|----------|--------|
| Per-fold `resolve_universe_daily` | `walkforward.py:_resolve_fold_membership` (start=train_start-warmup, end=chain_config.end); `optimizer.py:_fold_trial_symbols` uses the SAME `_calendar_days_before`/`_fold_symbols` seam (BL-01) | ✓ WIRED |
| Per-fold `SignalChainConfig` through the SHARED `FactorSignalChain` | `walkforward.py:_fold_chain_config` builds a per-fold config; `_run_fold`/`evaluate_best_params` call the one `chain.compute`; no parallel factor loop anywhere; test asserts `chain_config["end"]` per manifest | ✓ WIRED |
| `membership_fingerprint` manifests | `_run_fold` reads `frame.resolved_universe.membership_fingerprint` (signal_chain.py `_resolved_universe` → `_membership_fingerprint`) into `wf_folds`; fingerprint-change test green | ✓ WIRED |
| OOS exactly-once UNIQUE guard | `migrations.py` `wf_folds UNIQUE (plan_id, fold_index, is_oos, strategy_id, params_sha256)` + `wf_validated_strategies.oos_evidence_fold_id UNIQUE`; repo maps UNIQUE → `ValueError`; migration test `test_phase13_wf_tables_migrate_with_constraints_and_idempotence` passed | ✓ WIRED |
| Search trials on per-fold PIT membership (BL-01 fix live) | `optimizer.py:optimize(resolver=...)` → `_run_one` builds `StrategyBacktestConfig(symbols=_fold_trial_symbols(fold))`; regression test asserts every trial's symbols == membership set and never `None`/full-lake; `search_space["universe"]` persisted | ✓ WIRED |
| `evaluate_oos` gate (WR-01 fix live) | `run_walk_forward` default `evaluate_oos=False`; preheat test asserts 0 OOS rows after search-fold-only run | ✓ WIRED |
| Raw `best_score` (WR-05 fix live) | `optimizer.py` per-fold `objective_raw` + pooled raw `best_score`; `_sort` signed only internally; regression test `test_wf_search_min_direction_reports_raw_best_score` | ✓ WIRED |
| Append-only + FK graph + immutability | All five wf_* tables have `no_update`/`no_delete` triggers, CHECKs on 64-hex digests, `oos_excluded IN (0,1)`; migration test + repository `IntegrityError→ValueError` mapping verified | ✓ WIRED |

### Review Fixes Confirmed Live in Source (13-REVIEW.md: 16/16 resolved)

| Finding | Fix in source | Regression test | Status |
|---------|---------------|-----------------|--------|
| BL-01 search on full universe | `optimizer.py` `resolver` param threads `_fold_symbols(membership)` per trial; `search_space["universe"]` audit | `test_wf_search_trials_use_per_fold_membership_symbols_when_resolver_passed` — passed | ✓ LIVE |
| WR-01 OOS touched by exploration | `run_walk_forward(evaluate_oos: bool = False)` default off | preheat assertion in `test_evaluate_best_params_oos_exactly_once_and_validation_gate` — passed | ✓ LIVE |
| WR-02 OOS slot burned on failure | `evaluate_best_params` validates objective BEFORE `record_wf_fold` | `test_evaluate_best_params_wr02_no_oos_row_on_missing_objective` — passed | ✓ LIVE |
| WR-03 stale geometry on re-pin | `create_wf_plan` compares incoming vs stored geometry, raises on divergence | `test_create_wf_plan_raises_on_geometry_divergence` — passed | ✓ LIVE |
| WR-04 plan not pinned before search | `optimize` calls idempotent `repo.create_wf_plan(plan)` | `test_wf_search_persists_search_run_row_when_repo_passed` — passed | ✓ LIVE |
| WR-05 negated best_score | raw `objective_raw`/`best_score`; signed value only as `_sort` | `test_wf_search_min_direction_reports_raw_best_score` — passed | ✓ LIVE |
| WR-06 empty fold_evidence | auto-fed `{"oos": stats}` when omitted | covered by `test_evaluate_best_params_oos_exactly_once_and_validation_gate` (verdict row non-empty) | ✓ LIVE |
| WR-07 empty resolved_asset_ids | OOS membership symbols passed to `record_validated_strategy` | `test_evaluate_best_params_threshold_gate_min_and_max_direction` asserts `resolved_asset_ids` list | ✓ LIVE |
| WR-08 220/221 boundary | minimum = `oos+train+gap+2*test+1` | `test_build_plan_boundary_220_fails_221_builds` — passed | ✓ LIVE |
| WR-09 trading-day buffer | `_fold_chain_config` snaps `end` to `horizon` trading days past test_end (calendar-day fallback only at calendar end) | `test_run_walk_forward_pins_plan_and_records_fingerprints` asserts trading-day snapping + `effective_days == test_size` for search folds — passed | ✓ LIVE |
| WR-10 fabricated search_run_id | `repo=None` → `search_run_id=None`; FK IntegrityError mapped | `test_evaluate_best_params_wr10_unknown_search_run_fk_mapped`, `test_wf_search_records_search_run_row` — passed | ✓ LIVE |
| IN-01..IN-05 | Documented cache-only query path, UNIQUE-only error mapping, `pl.Date` window compare, window-union doc, `method="max"` tie doc | — | ✓ LIVE (documented; IN-05 tie semantics is Phase 14 consumer confirmation) |

### Behavioral Spot-Checks (run in verifier process)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Tracer spine: plan pinned, per-fold fingerprints, chain_config end, exactly-once OOS raise | `pytest tests/backtest/test_walkforward.py::test_run_walk_forward_pins_plan_and_records_fingerprints` | 1 passed | ✓ PASS |
| best_params OOS exactly-once + verdict binding + preheat never writes OOS | `pytest ...::test_evaluate_best_params_oos_exactly_once_and_validation_gate` | 1 passed | ✓ PASS |
| WR-02: no OOS row on missing objective | `pytest ...::test_evaluate_best_params_wr02_no_oos_row_on_missing_objective` | 1 passed | ✓ PASS |
| WR-08: 220 fails / 221 builds | `pytest ...::test_build_plan_boundary_220_fails_221_builds` | 1 passed | ✓ PASS |
| WR-03: geometry divergence raises | `pytest ...::test_create_wf_plan_raises_on_geometry_divergence` | 1 passed | ✓ PASS |
| BL-01: search trials on per-fold PIT membership, never None | `pytest tests/backtest/test_optimizer_run.py::test_wf_search_trials_use_per_fold_membership_symbols_when_resolver_passed` | 1 passed | ✓ PASS |
| Never in-sample: only fold test windows scored | `pytest ...::test_wf_search_never_scores_train_or_oos_windows` | 1 passed | ✓ PASS |
| WFWD-02 bookkeeping recorded | `pytest ...::test_wf_search_records_trial_space_and_score_distribution` | 1 passed | ✓ PASS |
| oos_excluded=0 fails closed | `pytest ...::test_wf_search_oos_excluded_zero_fails_closed` | 1 passed | ✓ PASS |
| WFWD-03 rank-average + gate + artifact | `pytest tests/backtest/test_ensemble.py::test_build_ensemble_rank_averages_validated_signals` (+ unvalidated fail-closed, checksum artifact) | 3 passed | ✓ PASS |
| WFWD-01 fingerprint change + below-10 raise | `pytest tests/backtest/test_walkforward.py::test_membership_fingerprint_changes_when_membership_changes test_run_walk_forward_effective_days_below_10_raises` | 2 passed | ✓ PASS |
| Migration: 5 wf_* tables + constraints + triggers | `pytest tests/test_operational_migrations.py::test_phase13_wf_tables_migrate_with_constraints_and_idempotence` | 1 passed | ✓ PASS |

15/15 targeted tests passed in the verifier process. Full suite verified green by the phase gate (1169 passed main + 11 shadow + 24 phase5; `pytest tests/backtest -q` → 114 passed; ruff clean) — not re-run per read-only verification constraints.

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes are declared by Phase 13 plans or summaries; the phase's verification contract is pytest-based. Not applicable.

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| — | No TBD/FIXME/XXX/PLACEHOLDER markers in any Phase 13 modified source file | ℹ️ none | — |
| — | No hardcoded empty data, stub returns, or `symbols=None` fallback in delivered code (the BL-01 fallback is an explicit degraded `[]` documented with a warning, not the full-lake bug) | ℹ️ none | — |
| `optimizer.py` (resolver=None branch) | Degraded search universe when no resolver passed | ℹ️ Info | Documented warning; not reachable in the intended research flow (resolver is passed by the orchestrator); regression test locks the degraded path as `[]`, never full-lake |
| `walkforward.py` | `timedelta` used only for the label buffer (1 occurrence, grep gate) | ℹ️ Info | Satisfies the plan grep gate |
| `ROADMAP.md` Progress table | Phase 13 shows "2/5" plans complete — stale aggregate counter last updated 2026-07-31; the Phase Details section lists 5/5 plans executed and the Traceability table marks WFWD-01..03 Complete | ℹ️ Info | Documentation-only; does not affect goal achievement |

### Human Verification Required

1. **Real governed-panel calendar probe**
   - **Test:** Run the fold-planner over the actual enriched governed panel (`trading_calendar` via the real `BacktestEngine.load_panel(columns=["date"])` probe) and confirm the measured A-share calendar: the Feb-2026 CNY month yields 14 trading days, and a real walk-forward run (`run_walk_forward` + `WalkForwardOptimizer` + `evaluate_best_params`) completes end-to-end on a real strategy.
   - **Expected:** `trading_calendar` returns the real measured trading dates (never a synthetic weekday calendar); `build_plan` derives 3 folds + reserved OOS snapped to those dates; a real run records per-fold manifests (`membership_fingerprint`, `effective_days >= 10`) and the OOS is evaluated exactly once.
   - **Why human:** Requires the real governed panel + heavy BacktestEngine + enriched lake data. Automated coverage uses the deterministic synthetic `measured_calendar` fixture (conftest) with the 14-trading-day CNY hole; this is the 13-VALIDATION.md manual-only item and cannot run in a read-only verification without the production datastore.

### Gaps Summary

No gaps found. All three ROADMAP success criteria are demonstrably TRUE in the codebase with concrete code paths and passing automated tests; all five PLAN must-have truths verified; all 16 review findings confirmed live in source (BL-01, WR-01..WR-10, IN-01..IN-05); cross-module integrity (per-fold PIT + shared chain + fingerprints + exactly-once OOS + evaluate_oos gate + raw best_score) verified wired; no execution authority exists in any Phase 13 module (grep across `backend/app/backtest` and `backend/app` found no broker/order/execution routes introduced by this phase — the only `broker_*` tokens are Phase 5 shadow-evidence import schema fields and deliberately-never-invoked compatibility args in `advanced/evolution.py`).

Status is **human_needed** solely for the single manual-only item: the real governed-panel calendar probe (13-VALIDATION.md manual-only row). All automated evidence is green.

---

_Verified: 2026-08-02_
_Verifier: Claude (gsd-verifier)_
