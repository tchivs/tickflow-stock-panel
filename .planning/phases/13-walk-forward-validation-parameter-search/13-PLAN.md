---
phase: 13-walk-forward-validation-parameter-search
plan: phase-plan
type: execute
requirements: [WFWD-01, WFWD-02, WFWD-03]
wave_summary:
  wave_0: [13-02]
  wave_1: [13-01]
  wave_2: [13-03]
  wave_3: [13-04]
  wave_4: [13-05]
must_haves:
  truths:
    - "Researcher can run rolling (non-expanding) walk-forward validation on the measured A-share calendar with an explicit gap between train and test, disjoint recorded test folds, and a reserved final OOS segment that is evaluated exactly once and never touched by selection or parameter search (WFWD-01)."
    - "Every fold resolves its own PIT universe via resolve_universe_daily, records a membership_fingerprint in its manifest, and runs the SHARED FactorSignalChain through a per-fold SignalChainConfig whose end = test_end + horizon so labels are finite through the whole test segment (WFWD-01 + FACT-06 anti train/serve skew)."
    - "Researcher can run parameter optimization scored on walk-forward OOS folds only (never in-sample), with n_trials / search_space / score_distribution recorded on an append-only wf_search_runs row whose oos_excluded=1 is enforced — the multiple-comparison-bias guard (WFWD-02)."
    - "The final OOS run of best_params is the unbiased estimate: the OOS fold row is UNIQUE exactly-once (a second evaluation raises ValueError) and wf_validated_strategies requires the OOS evidence fold id (WFWD-02)."
    - "Researcher can ensemble validated strategies by rank-averaging their per-date cross-sectional _rank signals; only passed_gate=1 strategies enter (else fail closed) and the output binds an input_snapshot_sha256 + checksum-verified artifact (WFWD-03)."
  artifacts:
    - path: backend/app/backtest/walkforward.py
      provides: "WalkForwardFold / WalkForwardPlan dataclasses, trading_calendar (distinct dates from BacktestEngine.load_panel), build_plan (pure rolling geometry + fail-closed asserts), run_walk_forward (per-fold resolve_universe_daily + per-fold SignalChainConfig + chain compute + fold manifests + exactly-once OOS)"
    - path: backend/app/backtest/optimizer.py
      provides: "WalkForwardOptimizer — OOS-scored grid search reusing expand_param_grid / GRID_MAX_COMBINATIONS / per-combo error isolation, scoring test folds only, recording trial/space/score-distribution, structurally excluding plan.oos_fold"
    - path: backend/app/backtest/ensemble.py
      provides: "EnsembleConfig + build_ensemble — Polars rank-average of per-strategy _rank per (symbol, date) with a validated-only gate (wf_validated_strategies passed_gate=1), output [symbol, date, ensemble_rank, ensemble_zscore]"
    - path: backend/app/research/repository.py
      provides: "wf_* repository methods — create_wf_plan / record_wf_fold / record_wf_search / record_validated_strategy / record_wf_ensemble + get_wf_plan / list_wf_folds / list_validated_strategies (append-only, IntegrityError→ValueError)"
    - path: backend/app/operational/migrations.py
      provides: "ONE appended script creating wf_plans / wf_folds / wf_search_runs / wf_validated_strategies (incl. resolved_asset_ids_json) / wf_ensembles — append-only + no_update/no_delete triggers + UNIQUE exactly-once OOS (per the approved one-way-door decision)"
    - path: backend/tests/backtest/test_walkforward.py
      provides: "WFWD-01 unit + integration — disjoint/tiled test segments, OOS pinned before search, calendar snapping (Feb 2026 14-day month), per-fold SignalChainConfig, membership_fingerprint, label-buffer effective_days, exactly-once OOS"
    - path: backend/tests/backtest/test_optimizer_run.py
      provides: "WFWD-02 OOS-scored search cases — search folds exclude oos_fold, GRID cap, trial/space/distribution bookkeeping, per-combo error isolation, never-in-sample scoring, exactly-once OOS of best_params"
    - path: backend/tests/backtest/test_ensemble.py
      provides: "WFWD-03 rank-average cases — validated-only gate, mean-of-_rank per (symbol,date), output shape, input-snapshot binding"
    - path: backend/tests/backtest/conftest.py
      provides: "measured-calendar fold-plan fixture (244-day-style calendar with a CNY hole) + stub chain/resolver/service fixtures shared across the three test files"
  key_links:
    - from: backtest/walkforward.py
      to: research/signal_chain.py
      via: "per-fold SignalChainConfig(end=fold.test_end + timedelta(days=plan.horizon)) computed through the SHARED FactorSignalChain.compute — the anti train/serve-skew path (FACT-06); membership_fingerprint read from frame.resolved_universe"
      pattern: "run_walk_forward"
    - from: backtest/walkforward.py
      to: research/universe.py
      via: "resolve_universe_daily(repo, universe_name, start=train_start-warmup, end=test_end+horizon) — per-date PIT membership, no survivorship bias"
      pattern: "resolve_universe_daily"
    - from: backtest/optimizer.py
      to: backtest/walkforward.py
      via: "WalkForwardOptimizer consumes plan.folds (search folds = [f for f in plan.folds if not f.is_oos]); plan.oos_fold structurally excluded; wf_search_runs.oos_excluded=1 enforced at insert"
      pattern: "expand_param_grid"
    - from: backtest/ensemble.py
      to: research/repository.py
      via: "validated-only gate — every strategy_id resolves to a wf_validated_strategies row with passed_gate=1, else fail closed; wf_ensembles row binds input_snapshot_sha256 (strategy_ids, weights, validation_record_ids, membership_fingerprint)"
      pattern: "list_validated_strategies"
    - from: research/repository.py
      to: operational/migrations.py
      via: "wf_folds UNIQUE (plan_id, fold_index, is_oos, strategy_id, params_sha256) enforces exactly-once OOS; wf_validated_strategies.oos_evidence_fold_id UNIQUE ties the verdict to the once-evaluated OOS; append-only triggers"
      pattern: "record_wf_fold"
---

# Phase 13: Walk-Forward Validation & Parameter Search — Executable Plan

## Phase Goal

Researchers can validate strategies and tune parameters on rolling walk-forward folds with a reserved, once-evaluated final OOS segment, and ensemble validated strategies by rank-averaged signals — every fold a leakage-safe, per-date PIT slice through the shared signal chain, every record an immutable append-only fact, and the reserved OOS never touched by selection or search.

## Scope

**In scope (WFWD-01..03):** rolling (non-expanding) walk-forward geometry over the MEASURED A-share trading calendar (244 days, 2025-07-29 → 2026-07-30 — re-measured at execution; Feb 2026 has only 14 trading days, CNY — never `timedelta` arithmetic); explicit gap `WF_GAP=20` between train and test; disjoint, tiled test folds (train=120 / gap=20 / test=20, step=20, k=3 folds); a reserved final 40-day OOS segment (2026-06-04 → 2026-07-30) pinned in an append-only `wf_plans` row BEFORE any parameter-search reuse and evaluated exactly once; per-fold PIT universe via `resolve_universe_daily` with `membership_fingerprint` in every manifest; per-fold `SignalChainConfig` (end = test_end + horizon so labels are finite through the whole test segment) through the shared `FactorSignalChain`; OOS-scored parameter search extending `backtest/optimizer.py` (GRID cap `GRID_MAX_COMBINATIONS=2000`, per-combo error isolation, `n_trials`/`search_space`/`score_distribution` bookkeeping on `wf_search_runs`, `oos_excluded=1` enforced); the validation gate (`wf_validated_strategies` requiring the once-evaluated OOS evidence); and rank-average ensembling of validated strategies (Polars mean of per-strategy `_rank` per (symbol, date), validated-only gate, `wf_ensembles` + checksum-verified artifact). The trading calendar comes exclusively from the governed panel (`BacktestEngine.load_panel`).

**Out of scope:** RebalancePlan + paper rebalance (Phase 14), API/frontend panels (Phase 15), Black-Litterman / ML expected returns (v2), per-fold portfolio-optimization fold scorer (documented `fold_scorer` seam only — the tracer implements the fixed-params strategy backtest variant). Deferred ideas from `13-CONTEXT.md` MUST NOT appear in any task. No execution routes anywhere — this is a research/validation layer over immutable records.

## Source Coverage Audit

| Source | ID | Required behavior or constraint | Plans | Status |
|---|---|---|---|---|
| GOAL | Phase 13 | Rolling walk-forward + reserved once-evaluated OOS; OOS-scored parameter search; rank-average ensemble of validated strategies | 13-01..13-05 | COVERED |
| REQ | WFWD-01 | Rolling (non-expanding) walk-forward with explicit gap, disjoint recorded folds, reserved final OOS evaluated exactly once and never touched by selection/search | 13-01, 13-02, 13-03, 13-05 | COVERED |
| REQ | WFWD-02 | Parameter optimization scored on walk-forward OOS folds (never in-sample), with trial count / search space / score distribution recorded | 13-02, 13-03, 13-05 | COVERED |
| REQ | WFWD-03 | Ensemble validated strategies via rank-average of their signals | 13-02, 13-04 | COVERED |
| CONTEXT | Fold geometry | Rolling windows, explicit gap WF_GAP=20, disjoint recorded folds, reserved final OOS evaluated exactly once, pinned BEFORE search reuse | 13-01, 13-02, 13-05 | COVERED |
| CONTEXT | PIT per fold | resolve_universe_daily per fold, membership_fingerprint in manifests, per-fold SignalChainConfig through the shared chain | 13-01 | COVERED |
| CONTEXT | Parameter search | Scored on walk-forward OOS folds only; records trial count / search space / score distribution; reuses optimizer.py grid pattern with OOS reservation | 13-02, 13-03 | COVERED |
| CONTEXT | Ensembling | Rank-average of validated strategy signals; research-use output for Phase 14; consumed via the shared signal chain | 13-04 | COVERED |
| CONTEXT | Discretion | Exact fold sizes (train=120/gap=20/test=20, k=3, OOS=40 — calibrated to measured history), search space + trial cap + score metric (default mean OOS Sharpe), ensemble weights (default equal), new append-only wf_* schema | 13-01, 13-02, 13-03, 13-04, 13-05 | COVERED |
| CODE | Migrations | Five new append-only wf_* tables (wf_plans, wf_folds, wf_search_runs, wf_validated_strategies, wf_ensembles) — one-way-door schema decision | 13-02 | COVERED (checkpoint:decision) |
| CODE | Repository | wf_* methods on ResearchRepository (append-only, IntegrityError→ValueError mirroring create_experiment) | 13-02 | COVERED |
| CODE | Calendar | trading calendar from governed panel (Feb 2026 14 trading days) — never a synthetic weekday calendar | 13-01, 13-05 | COVERED |
| CODE | Label buffer | per-fold config.end = test_end + horizon; effective_days recorded and asserted ≥ 10 per fold | 13-01, 13-05 | COVERED |
| CODE | Ensemble | Polars rank-mean of per-strategy _rank (signal_chain.py rank path); validated-only gate; artifact for Phase 14 | 13-04 | COVERED |

**Exclusions (not gaps):** deferred ideas in `13-CONTEXT.md`; Phase 14-15 scope; per-fold portfolio-optimization scorer (out of WFWD-01..03 — the `fold_scorer` seam is pre-built for it); expanding-window walk-forward (explicitly rejected).

## Plan List

- [ ] 13-01: **Tracer** — end-to-end walk-forward slice on a fixture: measured calendar → build_plan (3 folds, gap, reserved OOS) → pin wf_plans → per-fold resolve_universe_daily + SignalChainConfig + shared chain compute → fold manifests with membership_fingerprint → OOS evaluated exactly once (WFWD-01)
- [ ] 13-02: **Wave 0 foundations** — one-way-door checkpoint for the 5 append-only wf_* tables, migration script + tests, repository wf_* methods, Wave 0 test scaffolding (2 new test files + test_optimizer_run.py OOS cases + conftest measured-calendar fixture)
- [ ] 13-03: **OOS-scored parameter search + validation gate** — WalkForwardOptimizer in optimizer.py (GRID cap reuse, test-folds-only scoring, bookkeeping) + best_params OOS exactly-once + wf_validated_strategies gate (WFWD-02)
- [ ] 13-04: **Rank-average ensemble breadth** — ensemble.py rank-mean with the validated-only gate, wf_ensembles record + checksum-verified artifact (WFWD-03)
- [ ] 13-05: **Geometry robustness + reporting breadth** — calendar re-measure at execution, fail-closed geometry below H≈180, effective_days asserts, read/list APIs, membership-drift cases (WFWD-01/02/03)

## Wave Structure

| Wave | Plans | Purpose |
|------|-------|---------|
| 0 | 13-02 | Foundations: append-only wf_* migration (one-way-door checkpoint) + repo methods + Wave 0 test scaffolding — prerequisites for the tracer. |
| 1 | 13-01 | The tracer: prove the whole walk-forward spine end-to-end on a fixture before any breadth. |
| 2 | 13-03 | OOS-scored parameter search + the validation gate — search consumes the tracer's plan folds and records wf_search_runs. |
| 3 | 13-04 | Rank-average ensemble of validated strategies (needs the 13-03 validation gate). |
| 4 | 13-05 | Geometry robustness + reporting breadth (sequential after 13-01/13-03: shares walkforward.py + test_walkforward.py). |

## Artifacts this phase produces

| Artifact | Kind | Provides |
|---|---|---|
| `WalkForwardFold` / `WalkForwardPlan` / `trading_calendar` / `build_plan` / `run_walk_forward` (walkforward.py) | dataclasses + functions | pure-Polars rolling geometry over the measured calendar; per-fold PIT universe + per-fold SignalChainConfig through the shared chain; fold manifests with membership_fingerprint; exactly-once OOS (WFWD-01) |
| `WalkForwardOptimizer` (optimizer.py) | class | OOS-scored grid search reusing `expand_param_grid` / `GRID_MAX_COMBINATIONS=2000` / per-combo error isolation; test-folds-only scoring; n_trials/search_space/score_distribution bookkeeping; oos_excluded=1 enforced (WFWD-02) |
| `EnsembleConfig` / `build_ensemble` (ensemble.py) | dataclass + function | Polars rank-average of per-strategy `_rank` per (symbol, date) with the validated-only gate; output [symbol, date, ensemble_rank, ensemble_zscore] (WFWD-03) |
| wf_* repository methods (repository.py) | methods | create_wf_plan / record_wf_fold / record_wf_search / record_validated_strategy / record_wf_ensemble + get_wf_plan / list_wf_folds / list_validated_strategies — append-only, IntegrityError→ValueError |
| wf_plans / wf_folds / wf_search_runs / wf_validated_strategies / wf_ensembles (migrations.py) | SQLite tables | append-only fold/search/validated/ensemble records with CHECKs + no_update/no_delete triggers + UNIQUE exactly-once OOS |
| tests/backtest/{test_walkforward, test_ensemble}.py + test_optimizer_run.py OOS cases + conftest.py | test files | per-requirement unit contracts + the end-to-end tracer proof + the OOS-scored search cases + the measured-calendar fixture |
| tests/test_operational_migrations.py (extend) | migration tests | wf_* schema CHECKs, immutability triggers, FK integrity, forward-only idempotence |

## Requirement → Plan Mapping

| Requirement | Behavior | Plans | Verification command |
|---|---|---|---|
| WFWD-01 | Rolling folds, explicit gap, disjoint recorded tests, reserved once-evaluated OOS, per-fold PIT + fingerprint | 13-01, 13-02, 13-03, 13-05 | `cd backend && .venv/bin/python -m pytest tests/backtest/test_walkforward.py -x` |
| WFWD-02 | OOS-scored search + trial/space/distribution bookkeeping + exactly-once OOS of best_params + validation gate | 13-02, 13-03, 13-05 | `cd backend && .venv/bin/python -m pytest tests/backtest/test_optimizer_run.py -x` |
| WFWD-03 | Rank-average of validated signals only, artifact-bound | 13-02, 13-04 | `cd backend && .venv/bin/python -m pytest tests/backtest/test_ensemble.py -x` |
| Schema | 5 append-only wf_* tables + triggers + UNIQUE exactly-once | 13-02 | `cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short` |

All commands run from `backend/` with the project interpreter: `cd backend && .venv/bin/python -m pytest …`.

---

# Plan 13-01 — Tracer: End-to-End Walk-Forward Slice on a Fixture (WFWD-01)

**wave:** 1 · **depends_on:** [13-02] · **autonomous:** true
**requirements:** [WFWD-01]
**files_modified:**
- backend/app/backtest/walkforward.py (new)
- backend/tests/backtest/test_walkforward.py (extend — tracer proof)

## Objective

Prove the complete Phase 13 spine on a fixture, end to end, before any breadth: measure the fixture trading calendar from the governed seam → `build_plan` derives 3 rolling folds (train=120 / gap=20 / test=20, step=20) plus the reserved 40-day OOS over the measured dates (fold boundaries snap to the calendar — a CNY hole of 14 trading days in "Feb" is respected) → the `WalkForwardPlan` is INSERTed into `wf_plans` with `oos_pinned_at` (the reservation pinned BEFORE any search reuse) → per fold, resolve the PIT universe via `resolve_universe_daily`, build the per-fold `SignalChainConfig(end=test_end+horizon)` and compute through the SHARED `FactorSignalChain` (never a second compute path — FACT-06), record `membership_fingerprint`, run the train- and test-window backtests, and append one `wf_folds` row → the reserved OOS is evaluated exactly once (a second evaluation of the same (plan, strategy, params) raises `ValueError`).

Purpose: This is the validation layer's keel. It forces the measured-calendar geometry (never `timedelta`), the OOS-pinned-before-search reservation, the per-fold PIT + per-fold config through the single chain, the append-only fold manifest discipline, and the exactly-once OOS contract into existence on the first commit, and catches a dead-end (calendar drift, fold overlap, OOS collision, fingerprint misbinding, UNIQUE failure) before breadth is committed. Functionality is fixture-scoped (StubBacktestEngine + fixture calendar + StubUniverseResolver + tmp_path repository + fixture strategy); no architectural gap is left.
Output: `walkforward.py` (the plan builder + runner), the pinned `wf_plans` + append-only `wf_folds` records, and the green tracer test that locks the contracts.

## Context

- @.planning/phases/13-walk-forward-validation-parameter-search/13-CONTEXT.md — locked decisions: rolling windows, explicit gap WF_GAP=20, disjoint recorded folds, reserved final OOS pinned BEFORE search reuse, per-fold PIT universe + membership_fingerprint, per-fold SignalChainConfig (same shared chain)
- @.planning/phases/13-walk-forward-validation-parameter-search/13-RESEARCH.md — `## Fold Geometry Calibration` (measured 244-day calendar, train=120/gap=20/test=20, k=3, OOS=40, concrete fold dates) + `## Walk-Forward Runner` (WalkForwardFold/Plan surface, trading_calendar, run_walk_forward) + `## OOS Reservation` (pinned before search, structurally excluded, exactly-once UNIQUE)
- backend/app/backtest/engine.py — `load_panel` (L191-200, the sole governed seam) + `PanelCache` (L141-176, the date-only probe reuses it)
- backend/app/research/universe.py — `resolve_universe_daily` (L67-122, per-date PIT membership)
- backend/app/research/signal_chain.py — `FactorSignalChain.compute` (L78-158), `SignalChainConfig` (L39-58), `_resolve_membership` (L228-251), `_union_symbols` (L253-257), `_resolved_universe` membership_fingerprint (L302-328)
- backend/app/research/repository.py — the 13-02 wf_* methods (create_wf_plan, record_wf_fold) + the IntegrityError→ValueError pattern (L338-341)
- backend/tests/backtest/conftest.py — the 13-02 `measured_calendar` / `wf_fixture_plan` fixtures + StubBacktestEngine/StubUniverseResolver
- backend/app/backtest/strategy.py — `StrategyBacktestService.run` (L147-360) + `StrategyBacktestConfig` (the train/test-window backtest contract)

## Tasks

- **build: Create `backtest/walkforward.py` — WalkForwardFold/Plan dataclasses + `trading_calendar` + `build_plan`**
  - Files: backend/app/backtest/walkforward.py
  - Read first: 13-RESEARCH.md `## Walk-Forward Runner` (the dataclass surface + the fold arithmetic) + `## Fold Geometry Calibration` (the 244-day measured calendar, concrete fold dates, the label-horizon effect), backend/app/backtest/engine.py `load_panel` (L191-200) + `PanelCache` (L141-176)
  - Action: Module docstring states know/don't-know per CONVENTIONS.md (knows: rolling fold geometry over a supplied measured date list, OOS reservation; does not know: factor computation, strategy backtests, repository, artifacts). Implement `trading_calendar(engine, *, symbols, start, end, asset_type="stock") -> list[date]` — distinct sorted dates from a date-only probe through `BacktestEngine.load_panel(columns=["date"])` (reuses PanelCache; never synthesize a weekday calendar). Implement the frozen, slots dataclasses `WalkForwardFold(fold_index, is_oos, train_start, train_end, gap_start, gap_end, test_start, test_end, membership_fingerprint, chain_config)` and `WalkForwardPlan(plan_id, universe, asset_type, start, end, train_size, gap_size, test_size, oos_size, horizon, folds, oos_fold, trading_dates, created_at)` exactly per the research surface (folds = search/selection folds only; oos_fold = reserved final segment). Implement `build_plan(*, dates, train_size=120, gap_size=20, test_size=20, oos_size=40, horizon=5, universe, asset_type, plan_id) -> WalkForwardPlan` — split `[start,end]` into selection region + reserved OOS (`dates[-oos_size:]`), build the fold rectangles with the research arithmetic (train `[20i, 20i+119]`, gap `[20i+120, 20i+139]`, test `[20i+140, 20i+159]`, step=20), and FAIL CLOSED with `ValueError` on: fewer than 2 folds (`H - oos_size < train+gap+2*test`), any pair of test segments overlapping, non-tiling tests (`test_end_{i+1} != test_start_{i} + test_size`), `fold_N.test_end >= oos_start`, `len(oos_segment) != oos_size`, or `train_end + gap >= test_start`. Default sizes are module constants (`WF_TRAIN_SIZE=120`, `WF_GAP=20`, `WF_TEST_SIZE=20`, `WF_OOS_SIZE=40`) so geometry is derived, never hard-coded dates.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/backtest/test_walkforward.py -q --tb=short` (the geometry/calendar cases in the Wave 0 scaffold turn green)
  - Done: `build_plan` derives the exact 3-fold + OOS geometry from a measured date list; the geometry identity asserts hold; a calendar with a 14-day month still yields 20-day folds (calendar snapping); overlapping/OOS-colliding/short histories fail closed.

- **build: Implement `run_walk_forward` — per-fold PIT + SignalChainConfig + shared chain + fold manifests + exactly-once OOS**
  - Files: backend/app/backtest/walkforward.py
  - Read first: 13-RESEARCH.md `## Walk-Forward Runner` (run_walk_forward surface + the per-fold SignalChainConfig block) + `## OOS Reservation` (pinned before search, structurally excluded, exactly-once), backend/app/research/signal_chain.py `_resolve_membership` (L228-251) + `_resolved_universe` (L302-328), backend/app/backtest/strategy.py `StrategyBacktestService.run` + `StrategyBacktestConfig`
  - Action: Implement `run_walk_forward(plan: WalkForwardPlan, *, strategy_id: str, params: dict, service, chain: FactorSignalChain, resolver, repo: ResearchRepository, fold_scorer=None) -> dict` — FIRST pin the plan if not already recorded: `repo.create_wf_plan(plan)` recording `oos_pinned_at` (reservation BEFORE any search reuse; a re-run of the same plan_id returns the existing row — append-only idempotent). For each fold in `plan.folds` (search folds) AND `plan.oos_fold`: (1) resolve membership via `resolve_universe_daily(repo, universe_name=plan.universe, start=fold.train_start - warmup, end=fold.test_end + horizon, asset_type=plan.asset_type)`; (2) build the per-fold `SignalChainConfig(universe=plan.universe, symbols=(), asset_type=plan.asset_type, start=fold.train_start, end=fold.test_end + timedelta(days=plan.horizon), warmup_days=120, forward_return_horizon=plan.horizon, rebalance="daily")` — the label buffer makes forward returns finite through test_end; (3) compute `frame = chain.compute(revision_id=..., config=fold_cfg)` through the SHARED chain; (4) read `membership_fingerprint = frame.resolved_universe["membership_fingerprint"]`; (5) score the fold via the `fold_scorer` callable — the default scorer runs `StrategyBacktestService.run` with `StrategyBacktestConfig(strategy_id, symbols=..., start=fold.train_start, end=fold.train_end, params=params)` (train) and `(start=fold.test_start, end=fold.test_end, params=params)` (test), returning test-window stats; (6) `repo.record_wf_fold(...)` — one append-only row with fold_index, is_oos (1 only for the reserved OOS), strategy_id, `params_sha256` (64-hex of the canonical params JSON), train/test bounds, membership_fingerprint, `chain_config_json`, `stats_json` (test-window stats + `effective_days` = finite test dates after the horizon drop). The OOS fold (is_oos=1) is evaluated through the SAME path — the `UNIQUE (plan_id, fold_index, is_oos, strategy_id, params_sha256)` on `wf_folds` makes a second evaluation of the same (plan, strategy, params) raise `sqlite3.IntegrityError`, mapped to `ValueError("OOS segment already evaluated")` (mirroring `create_experiment` L338-341). The `fold_scorer` seam stays strategy-agnostic so the Phase 11/12 per-fold portfolio scorer can plug in later without forking the geometry.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/backtest/test_walkforward.py -q --tb=short`
  - Done: one plan row is pinned (oos_pinned_at recorded) before any fold; every fold records a distinct membership_fingerprint resolved over its own window; every fold's chain config end = test_end + horizon; the OOS fold is evaluated exactly once and a second evaluation raises ValueError; fold manifests are append-only rows with effective_days.

- **test: End-to-end tracer proof — `tests/backtest/test_walkforward.py`**
  - Files: backend/tests/backtest/test_walkforward.py
  - Read first: the Wave 0 scaffold cases + `tests/backtest/conftest.py` (`measured_calendar` + `wf_fixture_plan` + stub fixtures), backend/app/backtest/walkforward.py (module under test)
  - Action: Write one integration test walking the full spine on a fixture: `measured_calendar` (a ~244-trading-day synthetic calendar with a 14-trading-day "Feb" hole, per 13-RESEARCH) → `build_plan` → assert the 3 test segments are pairwise disjoint and tile contiguously, the OOS is the final 40 dates and `fold_3.test_end < oos_start`, and every fold has exactly 20 test dates (calendar snapping) → `create_wf_plan` pins the plan with `oos_pinned_at` → `run_walk_forward(plan, strategy_id="fixture_strategy", params={...})` on the stub chain/resolver/service → per fold: `chain_config_json["end"] == test_end + horizon`, `membership_fingerprint` 64-hex and CHANGES when the membership fixture changes, `effective_days >= 10`; the OOS fold row has `is_oos=1`; a SECOND `run_walk_forward` of the same (plan, strategy, params) raises `ValueError("OOS segment already evaluated")` — the UNIQUE exactly-once guard.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/backtest/test_walkforward.py -q --tb=short`
  - Done: the full measured-calendar → build_plan → pinned plan → per-fold PIT chain compute → fingerprint manifests → exactly-once OOS path works end-to-end on a fixture — the spine is proven before any breadth plan starts.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/backtest/test_walkforward.py -q --tb=short
```

All green. Grep gate: `timedelta` appears in `walkforward.py` ONLY for the `end = test_end + horizon` label buffer (never for fold boundaries — `grep -v '^#' | grep -c timedelta` ≤ 1); `load_panel` is the only panel load (no parquet path in walkforward.py); the shared `FactorSignalChain` is the only compute path (no parallel factor loop).

## Success Criteria

- The 3-fold + reserved-OOS geometry derives from the measured calendar, tests are disjoint and tiled, and the OOS is pinned in `wf_plans` BEFORE any search reuse.
- Every fold resolves its own PIT universe, computes through a per-fold `SignalChainConfig` on the shared chain, and records a 64-hex `membership_fingerprint` + `effective_days` in an append-only `wf_folds` row.
- The reserved OOS is evaluated exactly once — a second evaluation raises `ValueError` (UNIQUE exactly-once guard).

---

# Plan 13-02 — Wave 0: wf_* Migration, Repo Methods, Test Scaffolding

**wave:** 0 · **depends_on:** [] · **autonomous:** false (one one-way-door checkpoint:decision gate)
**requirements:** [WFWD-01, WFWD-02, WFWD-03]
**files_modified:**
- backend/app/operational/migrations.py
- backend/tests/test_operational_migrations.py
- backend/app/research/repository.py
- backend/tests/backtest/conftest.py (new)
- backend/tests/backtest/test_walkforward.py (new — RED scaffold)
- backend/tests/backtest/test_ensemble.py (new — RED scaffold)
- backend/tests/backtest/test_optimizer_run.py (extend — OOS-scored search RED cases)

## Objective

Land the irreversible foundations every other plan builds on: the five append-only `wf_*` tables (wf_plans, wf_folds, wf_search_runs, wf_validated_strategies, wf_ensembles) in the existing operational.db migration sequence — the one-way schema door the whole phase's audit contract rests on — the repository `wf_*` methods, and the base test scaffolding (2 new test files + conftest measured-calendar fixture + `test_optimizer_run.py` OOS-scored search RED cases) that 13-01/13-03/13-04 turn green. The one-way-door decision (new append-only tables) is gated behind an explicit `checkpoint:decision` task BEFORE any implementation — per the reversibility contract this is `one-way` (undoing requires a follow-up migration that breaks the Phase 13 contract).

Purpose: Every later plan assumes these tables, this repo surface, and these test files exist. Wave 0 is the only place the migration sequence advances and the only place the Phase 13 evidence contract (exactly-once OOS, oos_excluded, validated-only ensembles) is pinned.
Output: the 5 wf_* tables migrated with CHECKs + triggers, the approved schema decision applied, the wf_* repo methods, 2 new test files + conftest fixtures + test_optimizer_run.py OOS cases, and the migration test coverage.

## Context

- @.planning/phases/13-walk-forward-validation-parameter-search/13-CONTEXT.md — locked decisions: append-only fold/search/ensemble records, WFWD-02 bookkeeping, rank-average ensembling
- @.planning/phases/13-walk-forward-validation-parameter-search/13-RESEARCH.md — `## Schema/Migration Sketch` (the 5-table DDL, the UNIQUE exactly-once OOS constraint, the `_no_update`/`_no_delete` trigger convention) + `## Repository methods` + `## Verification Plan` (Wave 0 gaps)
- backend/app/operational/migrations.py — the `MIGRATIONS` tuple (Phase 12 script is the last entry, ending with the attribution evidence table + triggers; the tuple closes with `""",` then `)`); `migrate_operational_db` applies atomically with `PRAGMA user_version`
- backend/app/research/repository.py — `_json` (L20-25), `_record` (L27-40), `create_experiment` IntegrityError→ValueError (L338-341), `_connection` context manager — the conventions the wf_* methods mirror
- backend/tests/test_operational_migrations.py — the Phase 11/12 runs-table/evidence-table tests (the pattern for the wf_* cases)
- backend/tests/research/conftest.py — `StubBacktestEngine` + `StubUniverseResolver` + `research_repository` (the fixture patterns to mirror in tests/backtest/conftest.py)

## Tasks

- **checkpoint:decision — Approve the five append-only `wf_*` tables (one-way door)**
  - Decision: Land the five Phase 13 tables — `wf_plans`, `wf_folds`, `wf_search_runs`, `wf_validated_strategies`, `wf_ensembles` — in `operational/migrations.py` as ONE new migration script appended to the `MIGRATIONS` tuple (advancing `PRAGMA user_version` for the shared operational.db), with the CHECK constraints, `no_update`/`no_delete` triggers, and indexes per the 13-RESEARCH schema sketch.
  - Context: This is a one-way door: the migration advances the user_version for every operational.db (research + forecast + jobs share the same database); undoing requires a follow-up migration, and Phase 14 (RebalancePlan consuming validated strategies) and Phase 15 (WalkForward panels) build on these audit records. The tables are MANDATED by the append-only contract (fold manifests, search bookkeeping, validation verdicts, and ensemble outputs are immutable facts) and by the exactly-once-OOS integrity boundary (WFWD-01/02). All five tables share one script so the FK graph (wf_folds.plan_id → wf_plans, wf_search_runs.plan_id → wf_plans, wf_validated_strategies → wf_plans + wf_search_runs + wf_folds, wf_ensembles standalone) is created in a single atomic step.
  - Options:
    - option-a: ONE migration script with all five tables exactly per the research sketch — `wf_folds` with `UNIQUE (plan_id, fold_index, is_oos, strategy_id, params_sha256)` (exactly-once incl. OOS), `wf_search_runs.oos_excluded INTEGER NOT NULL CHECK (oos_excluded IN (0,1))`, `wf_validated_strategies.oos_evidence_fold_id TEXT NOT NULL UNIQUE REFERENCES wf_folds(id)` (verdict tied to the once-evaluated OOS), `wf_ensembles` with `input_snapshot_sha256` + `output_sha256` + `artifact_relative_path`; `_no_update`/`_no_delete` triggers on all five; indexes `idx_wf_folds_plan(plan_id, fold_index)`, `idx_wf_validated_strategies(strategy_id)`, `idx_wf_ensembles_created(created_at)`. Pros: one atomic schema step; FK graph intact; matches the research sketch exactly; the single place Phase 14/15 read from. Cons: one larger migration script to review; the one-way door is bigger.
    - option-b: Two scripts — (1) wf_plans + wf_folds + wf_search_runs (the fold/search spine), (2) wf_validated_strategies + wf_ensembles (the validation/ensemble layer). Pros: smaller incremental steps; validation tables can be deferred if the spine proves insufficient. Cons: two user_version advances; the FK from wf_validated_strategies → wf_folds spans scripts; more surface for drift between the two decisions.
  - Resume signal: Select: option-a or option-b

- **build: Append the Phase 13 migration script (+ the 5 wf_* tables per the approved option) + extend migration tests**
  - Files: backend/app/operational/migrations.py, backend/tests/test_operational_migrations.py
  - Read first: backend/app/operational/migrations.py (the last MIGRATIONS entry — the Phase 12 attribution-evidence script — and the tuple close), 13-RESEARCH.md `## Schema/Migration Sketch` (the exact DDL), backend/tests/test_operational_migrations.py (the Phase 12 evidence-table test conventions)
  - Action: Append ONE new SQL script to the `MIGRATIONS` tuple per the approved option. Per the research sketch: `wf_plans` (universe, asset_type CHECK IN ('stock','etf'), start/end, train_size/gap_size/test_size/oos_size CHECKs, horizon CHECK > 0, `trading_dates_json` TEXT NOT NULL, `fold_geometry_json` TEXT NOT NULL, `oos_pinned_at` TEXT NOT NULL, created_at); `wf_folds` (plan_id FK → wf_plans ON DELETE RESTRICT, fold_index, is_oos CHECK IN (0,1), strategy_id, params_sha256 CHECK length 64, train_start/train_end/test_start/test_end, membership_fingerprint CHECK length 64, chain_config_json, stats_json, created_at, `UNIQUE (plan_id, fold_index, is_oos, strategy_id, params_sha256)`); `wf_search_runs` (plan_id FK, strategy_id, objective, direction, search_space_json, n_trials, n_completed, score_distribution_json, best_params_json, best_score REAL, `oos_excluded INTEGER NOT NULL CHECK (oos_excluded IN (0,1))`, created_at); `wf_validated_strategies` (strategy_id, plan_id FK, search_run_id FK → wf_search_runs, params_sha256 CHECK length 64, `oos_evidence_fold_id TEXT NOT NULL UNIQUE REFERENCES wf_folds(id)`, validation_score REAL NOT NULL, fold_evidence_json, resolved_asset_ids_json TEXT, passed_gate CHECK IN (0,1), created_at, UNIQUE (strategy_id, params_sha256, plan_id)); `wf_ensembles` (name, strategy_ids_json, weights_json, validation_record_ids_json, input_snapshot_sha256 CHECK length 64, output_sha256 CHECK length 64, artifact_relative_path, created_at). `_no_update`/`_no_delete` triggers on all five (`RAISE(ABORT, '<table> facts are append-only')`); indexes per the sketch. Extend `tests/test_operational_migrations.py` with the Phase 13 cases: each table migrates with its CHECKs + triggers (incl. the `wf_validated_strategies.resolved_asset_ids_json` column); `wf_folds` UNIQUE fires a second same-key insert; `wf_validated_strategies.oos_evidence_fold_id` UNIQUE fires a second OOS-verdict insert; `wf_search_runs.oos_excluded` rejects 0 when the caller sets 1… the CHECK only allows 0/1; the FAIL-CLOSED-on-0 behavior is a repository-level guard (task below); the migration test proves the constraint space + immutability triggers + forward-only idempotence.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short`
  - Done: all five wf_* tables migrate atomically with the CHECKs/FKs/triggers/indexes; UPDATE/DELETE on any wf_* table raises (triggers); the exactly-once UNIQUE constraints fire; the migration is forward-only idempotent.

- **build: Extend `ResearchRepository` with the wf_* methods**
  - Files: backend/app/research/repository.py
  - Read first: backend/app/research/repository.py `_json` (L20-25) + `_record` (L27-40) + `create_experiment` (L292-341, the IntegrityError→ValueError mapping) + the Phase 13 schema (the 13-02 migration above)
  - Action: Add the append-only wf_* methods, each taking a `ResearchRepository`-style short-lived connection: `create_wf_plan(plan: WalkForwardPlan) -> dict` — INSERT into wf_plans (id = plan.plan_id, trading_dates_json + fold_geometry_json canonical-JSON via `_json`, oos_pinned_at = now); a re-insert of the same plan_id returns the existing row (query path — append-only idempotent, no error); `record_wf_fold(**fields) -> dict` — INSERT into wf_folds, mapping `sqlite3.IntegrityError` to `ValueError("OOS segment already evaluated")` when the UNIQUE constraint names the wf_folds key (mirroring L338-341); `record_wf_search(**fields) -> dict` — INSERT into wf_search_runs, FAILING CLOSED with `ValueError` if `oos_excluded != 1` (the search must never touch the OOS — the structural guard beyond the DB CHECK); `record_validated_strategy(**fields) -> dict` — INSERT into wf_validated_strategies (passed_gate 0/1, oos_evidence_fold_id UNIQUE — a second verdict on the same OOS evidence raises ValueError); `record_wf_ensemble(**fields) -> dict`; read paths `get_wf_plan(plan_id)`, `list_wf_folds(*, plan_id=None, is_oos=None, limit=200)` (ORDER BY plan_id, fold_index; unwrap JSON columns via `_record`-style mapping), `list_validated_strategies(*, strategy_id=None, plan_id=None, limit=200)` (ORDER BY created_at, id). All rows INSERT-only; no UPDATE/DELETE anywhere.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/backtest/test_walkforward.py tests/backtest/test_ensemble.py tests/backtest/test_optimizer_run.py -q --tb=short` (the repository-touching RED cases turn green where the methods exist; idempotency + IntegrityError cases pass)
  - Done: wf_plans round-trips with idempotent re-create; wf_folds exactly-once UNIQUE maps to ValueError; record_wf_search fails closed on oos_excluded=0; validated/ensemble rows round-trip; list paths filter and cap at limit.

- **test: Scaffold the new test files + conftest measured-calendar fixture + test_optimizer_run.py OOS cases (Wave 0 gaps)**
  - Files: backend/tests/backtest/conftest.py, backend/tests/backtest/test_walkforward.py, backend/tests/backtest/test_ensemble.py, backend/tests/backtest/test_optimizer_run.py
  - Read first: backend/tests/research/conftest.py (StubBacktestEngine + StubUniverseResolver + research_repository — the fixture patterns), backend/tests/backtest/test_optimizer_run.py (the fake-service injection pattern), 13-RESEARCH.md `## Verification Plan` (the per-file assertion lists)
  - Action: Create `tests/backtest/conftest.py`: `measured_calendar` — a deterministic ~244-trading-day date list (weekday dates with a 14-trading-day "Feb" hole so calendar snapping is testable) built in pure Python; `wf_fixture_plan` — a `WalkForwardPlan` built by `build_plan` over `measured_calendar` (default geometry) with a stub universe; `stub_chain` / `stub_resolver` / `stub_backtest_service` — minimal doubles that record calls and return controlled `FactorSignalFrame`-shaped + backtest-stats-shaped results (membership_fingerprint derived from a per-test membership frame so fingerprint-change is testable); `research_repository` — the existing research conftest pattern (tmp_path operational.db + migrate). Create `tests/backtest/test_walkforward.py` (RED scaffold): geometry identity / disjointness / tiling / OOS-exclusion cases; calendar-snap case; per-fold SignalChainConfig end == test_end + horizon; membership_fingerprint recorded + changes with membership; exactly-once OOS (second eval raises). Create `tests/backtest/test_ensemble.py` (RED scaffold): validated-only gate (a non-passed strategy fails closed); rank-average = mean of per-strategy _rank per (symbol,date); output shape [symbol, date, ensemble_rank, ensemble_zscore]; input-snapshot binding. Extend `tests/backtest/test_optimizer_run.py` (RED scaffold): WalkForwardOptimizer search folds exclude plan.oos_fold (fail-closed if referenced); GRID_MAX_COMBINATIONS cap respected; n_trials/search_space/score_distribution recorded; per-combo error isolation; scores come from test folds only (never in-sample); exactly-once OOS of best_params.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/backtest/test_walkforward.py tests/backtest/test_ensemble.py tests/backtest/test_optimizer_run.py -q --tb=short` — expected failures (RED) until 13-01/13-03/13-04 land
  - Done: the 2 new test files + the test_optimizer_run.py OOS cases exist with the Phase 13 contracts; conftest provides `measured_calendar` + `wf_fixture_plan` + the stub doubles; the scaffolds are provably RED (failing on the missing modules/functions) — the exact tests 13-01/13-03/13-04/13-05 turn green.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short
cd backend && .venv/bin/python -m pytest tests/backtest/test_walkforward.py tests/backtest/test_ensemble.py tests/backtest/test_optimizer_run.py -q --tb=short   # expected RED (scaffolds) until 13-01/13-03/13-04
```

The wf_* tables migrate with their constraints and triggers; the 2 new test files are scaffolded RED with shared fixtures; the OOS-search cases are scaffolded RED.

## Success Criteria

- The five append-only wf_* tables migrate atomically per the approved one-way-door option, with the exactly-once-OOS UNIQUE, the oos_excluded CHECK, the validated-verdict UNIQUE, immutability triggers, and FK integrity.
- The wf_* repository methods are append-only, idempotent on plan re-create, IntegrityError→ValueError mapped, and fail closed on oos_excluded=0.
- The 2 new test files + conftest fixtures + test_optimizer_run.py OOS cases are scaffolded RED — the exact tests 13-01/13-03/13-04/13-05 turn green.

---

# Plan 13-03 — OOS-Scored Parameter Search + Validation Gate (WFWD-02)

**wave:** 2 · **depends_on:** [13-01] · **autonomous:** true
**requirements:** [WFWD-01, WFWD-02]
**files_modified:**
- backend/app/backtest/optimizer.py (extend — WalkForwardOptimizer)
- backend/app/backtest/walkforward.py (extend — best_params OOS evaluation + validation gate)
- backend/tests/backtest/test_optimizer_run.py (extend — green OOS cases)
- backend/tests/backtest/test_walkforward.py (extend — validation-gate integration cases)

## Objective

Harden the parameter-search layer from the Phase 11 in-sample grid to the WFWD-02 surface: a `WalkForwardOptimizer` that scores every trial on the **test segments of the walk-forward folds only** (never the reserved OOS, never in-sample train), reuses the existing grid machinery unchanged (`expand_param_grid` / `count_combinations` / `GRID_MAX_COMBINATIONS=2000` / per-combo error isolation / `objective_value` / `default_direction`), records `n_trials` / `search_space` / `score_distribution` on an append-only `wf_search_runs` row with `oos_excluded=1` enforced, and then — after search — evaluates `best_params` on the reserved OOS **exactly once** (the unbiased estimate, WFWD-02) and records the `wf_validated_strategies` verdict whose `oos_evidence_fold_id` UNIQUE ties validation to the once-evaluated OOS.

Purpose: WFWD-02's multiple-comparison guard is only real when the search can't see the OOS structurally, the trial/space/distribution bookkeeping is recorded, and the final OOS run of best_params is the only score ever reported as forward-looking evidence.
Output: `WalkForwardOptimizer`, the best_params OOS evaluation + `wf_validated_strategies` gate, green `test_optimizer_run.py` OOS cases + `test_walkforward.py` validation-gate cases.

## Context

- @.planning/phases/13-walk-forward-validation-parameter-search/13-CONTEXT.md — locked decisions: scored on walk-forward OOS folds (never in-sample), records trial count/search space/score distribution, reuses optimizer.py grid pattern with OOS reservation
- @.planning/phases/13-walk-forward-validation-parameter-search/13-RESEARCH.md — `## OOS-Scored Parameter Search` (WalkForwardOptimizer surface + design points: never in-sample, GRID cap, score metric default mean OOS Sharpe, multiple-comparison guard, error isolation, progress/cancel) + `## OOS Reservation` (structurally excluded, exactly-once, validation gate ties OOS to verdict)
- backend/app/backtest/optimizer.py — `GRID_MAX_COMBINATIONS` (L15), `VALID_OBJECTIVES` (L26-34), `expand_param_grid` (L87-103), `objective_value` / `default_direction`, `StrategyOptimizer._run_one` per-combo isolation (L189-213), `progress_cb` (L229-237)
- backend/app/backtest/walkforward.py (from 13-01) — `WalkForwardPlan`/`WalkForwardFold` + `run_walk_forward` (the exactly-once OOS path to reuse for best_params)
- backend/app/research/repository.py (from 13-02) — `record_wf_search` + `record_validated_strategy`
- backend/tests/backtest/test_optimizer_run.py (from 13-02 RED scaffold) + test_walkforward.py

## Tasks

- **build: Add `WalkForwardOptimizer` to `backtest/optimizer.py` — OOS-scored, GRID-capped, bookkeeping**
  - Files: backend/app/backtest/optimizer.py
  - Read first: 13-RESEARCH.md `## OOS-Scored Parameter Search` (the class surface + design points), backend/app/backtest/optimizer.py `expand_param_grid` (L87-103) + `StrategyOptimizer` (L150-263 — the DI shape + per-combo isolation + progress)
  - Action: In the SAME `optimizer.py` (do NOT fork the grid machinery), add `class WalkForwardOptimizer` with the same DI as `StrategyOptimizer` (`__init__(self, service, strategy_engine)`). `optimize(*, plan: WalkForwardPlan, strategy_id: str, param_grid: dict, objective: str = "sharpe", max_workers: int = 4, progress_cb=None, cancel_event=None) -> dict`: (1) `search_folds = [f for f in plan.folds if not f.is_oos]` — the OOS is STRUCTURALLY excluded (`plan.folds` never contains `plan.oos_fold` by construction); assert `search_folds` is non-empty and raise `ValueError` if any referenced fold is the OOS (fail-closed); (2) `params_meta = self.strategy_engine.get(strategy_id).meta.get("params", [])`, `combos = expand_param_grid(params_meta, param_grid)` — the `GRID_MAX_COMBINATIONS=2000` cap is inherited unchanged; (3) per combo, for EACH search fold run the TEST-window backtest through the fold scorer (the 13-01 default scorer with `StrategyBacktestConfig(start=fold.test_start, end=fold.test_end, params=merged)`) with the per-combo try/except error isolation (L189-213 — one failing combo sinks to `_sort=-inf`, never kills the batch); pooled score = mean of per-fold `objective_value`; NEVER score train windows; (4) record per-combo per-fold scores; (5) `direction = default_direction(objective)`; (6) return `{"objective", "direction", "n_trials": len(combos), "n_completed", "search_space": {"param_grid", "params_meta"}, "score_distribution": {"per_trial": [...], "per_fold": {fold_index: [...]}, "min", "median", "max", "mean", "std"}, "best_params", "best_score", "results": ranked}`; (7) `repo.record_wf_search(...)` with `oos_excluded=1` (the repository fails closed if not 1). Reuse `count_combinations`, `objective_value`, `default_direction`, `_validate_backtest_kwargs` unchanged — the only new logic is the fold loop + distribution bookkeeping.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/backtest/test_optimizer_run.py -q --tb=short`
  - Done: trials are scored on test folds only (never in-sample, never OOS); the GRID cap is inherited (an over-cap grid raises before any trial); the wf_search_runs row records n_trials/search_space/score_distribution with oos_excluded=1; per-combo failures are isolated; progress/cancel reuse the StrategyOptimizer shape.

- **build: best_params OOS evaluation (exactly once) + the validation gate**
  - Files: backend/app/backtest/walkforward.py
  - Read first: 13-RESEARCH.md `## OOS Reservation` (validation gate ties OOS to the verdict) + `## OOS-Scored Parameter Search` ("the final OOS run of best_params is the unbiased estimate"), backend/app/backtest/walkforward.py `run_walk_forward` (from 13-01 — the OOS path to reuse)
  - Action: Add `evaluate_best_params(plan: WalkForwardPlan, *, strategy_id: str, best_params: dict, service, chain, resolver, repo) -> dict` — run `run_walk_forward` restricted to `plan.oos_fold` with `params=best_params` (the SAME per-fold PIT + per-fold SignalChainConfig + shared chain path; the `UNIQUE (plan_id, fold_index, is_oos=1, strategy_id, params_sha256)` makes a second evaluation raise `ValueError("OOS segment already evaluated")` — best_params can only ever produce ONE OOS estimate). Then record the validation verdict: `repo.record_validated_strategy(strategy_id=..., plan_id=..., search_run_id=..., params_sha256=..., oos_evidence_fold_id=<the OOS fold row id>, validation_score=<the OOS objective value>, fold_evidence_json=<per-fold test scores from the search>, passed_gate=1)` — the `oos_evidence_fold_id UNIQUE` constraint ties the verdict to the once-evaluated OOS (a second verdict on the same OOS evidence raises ValueError). Return `{"oos_fold_id", "validation_score", "validated_strategy_id"}`.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/backtest/test_walkforward.py -q --tb=short`
  - Done: best_params is evaluated on the OOS exactly once (a second evaluation raises ValueError); the validated-strategy row requires the OOS evidence fold id (UNIQUE); validation_score = the OOS objective value; passed_gate=1 rows are what the ensemble gate (13-04) consumes.

- **test: Turn the `test_optimizer_run.py` OOS cases green + `test_walkforward.py` validation-gate cases**
  - Files: backend/tests/backtest/test_optimizer_run.py, backend/tests/backtest/test_walkforward.py
  - Read first: the 13-02 RED cases in both files, backend/app/backtest/optimizer.py (WalkForwardOptimizer) + backend/app/backtest/walkforward.py (evaluate_best_params)
  - Action: Make the scaffolded cases pass and add: (1) `WalkForwardOptimizer.optimize` search folds exclude `plan.oos_fold` — pass a plan whose folds reference the OOS and assert `ValueError` (fail-closed); (2) the GRID cap — an over-cap grid raises before any backtest runs; (3) `n_trials == len(combos)`, `search_space` captures param_grid + params_meta, `score_distribution` has per_trial/per_fold/min/median/max/mean/std; (4) per-combo error isolation — a scorer that raises on one combo still yields the others ranked with the failing combo last; (5) never in-sample — a scorer that records every window it is asked to score shows NO train-window calls (train windows are only used for the parameter-behavior confirmation path if the fold scorer opts in — the default scores test folds only); (6) `evaluate_best_params` runs the OOS exactly once and `record_validated_strategy` raises on a second verdict for the same OOS evidence; (7) the validation gate — `list_validated_strategies(strategy_id=...)` returns the passed_gate=1 row with `oos_evidence_fold_id`.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/backtest/test_optimizer_run.py tests/backtest/test_walkforward.py -q --tb=short`
  - Done: the WFWD-02 contract — OOS-structural-exclusion, GRID cap, trial/space/distribution bookkeeping, per-combo isolation, never-in-sample, exactly-once OOS of best_params, and the validated-verdict gate — is locked by green tests.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/backtest/test_optimizer_run.py tests/backtest/test_walkforward.py -q --tb=short
```

All green. Grep gate: `expand_param_grid` is called from `WalkForwardOptimizer.optimize` (not a reimplementation); the OOS dates never appear in any search backtest config (`grep -v '^#' | grep -c "oos"` in the search path reflects only the structural exclusion + bookkeeping).

## Success Criteria

- Every trial scores the test segments of the walk-forward folds only; the reserved OOS is structurally excluded and `wf_search_runs.oos_excluded=1` is enforced.
- `n_trials` / `search_space` / `score_distribution` are recorded (the multiple-comparison guard); the GRID cap is inherited.
- best_params is evaluated on the OOS exactly once; the `wf_validated_strategies` verdict requires that OOS evidence (UNIQUE) — the only unbiased estimate.

---

# Plan 13-04 — Rank-Average Ensemble Breadth (WFWD-03)

**wave:** 3 · **depends_on:** [13-03] · **autonomous:** true
**requirements:** [WFWD-03]
**files_modified:**
- backend/app/backtest/ensemble.py (new)
- backend/app/research/repository.py (extend — record_wf_ensemble read-back, if needed)
- backend/tests/backtest/test_ensemble.py (extend — green)

## Objective

Deliver the WFWD-03 ensembling layer: a `build_ensemble` that rank-averages the per-strategy `_rank` signals (already computed per date by the shared chain at `signal_chain.py:139-146`) across ONLY the strategies with a `wf_validated_strategies` row `passed_gate=1` — any non-validated strategy fails closed — producing `[symbol, date, ensemble_rank, ensemble_zscore]`, persisted as an immutable checksum-verified artifact (O_EXCL + fsync + sha256 via `EvaluationArtifactService.write_bundle`) with an append-only `wf_ensembles` row binding `input_snapshot_sha256` over (strategy_ids, weights, validation_record_ids, membership_fingerprint).

Purpose: WFWD-03 requires ensembles of VALIDATED strategies only, computed with one code path (Polars rank-mean — no scipy, no re-implemented rank), and delivered to Phase 14 as a research-use signal source through the shared chain.
Output: `ensemble.py` (EnsembleConfig + build_ensemble), the `wf_ensembles` record + artifact, green `test_ensemble.py`.

## Context

- @.planning/phases/13-walk-forward-validation-parameter-search/13-CONTEXT.md — locked decisions: rank-average of validated strategy signals, research-use output consumed via the shared signal chain
- @.planning/phases/13-walk-forward-validation-parameter-search/13-RESEARCH.md — `## Rank-Average Ensembling` (EnsembleConfig surface, rank-mean math, validated-only gate, weighting default equal, output shape for Phase 14, artifact binding) + `## Schema/Migration Sketch` (wf_ensembles row)
- backend/app/research/signal_chain.py — `_rank` per-date cross-sectional rank (L139-146) — the input column every validated strategy's chain frame carries
- backend/app/research/repository.py (from 13-02) — `list_validated_strategies` + `record_wf_ensemble`
- backend/app/research/models.py — `EvaluationArtifactService.write_bundle` (L189-207, O_EXCL + fsync + sha256 artifact pattern) + `ArtifactDescriptor`
- backend/tests/backtest/test_ensemble.py (from 13-02 RED scaffold)

## Tasks

- **build: Create `backtest/ensemble.py` — EnsembleConfig + build_ensemble (rank-average, validated-only)**
  - Files: backend/app/backtest/ensemble.py
  - Read first: 13-RESEARCH.md `## Rank-Average Ensembling` (the surface + math + gate), backend/app/research/signal_chain.py `_rank` (L139-146, the input shape), backend/app/research/repository.py `list_validated_strategies`
  - Action: Module docstring states know/don't-know (knows: rank-averaging per-date cross-sectional signals of validated strategies; does not know: factor computation, fold geometry, strategy backtests, repository internals). Implement `@dataclass(frozen=True, slots=True) EnsembleConfig(strategy_ids: tuple[str, ...], weights: Mapping[str, float], validation_record_ids: tuple[str, ...])` per the research surface. Implement `build_ensemble(*, config, signals: Mapping[str, pl.DataFrame], universe, start, end, horizon) -> pl.DataFrame`: (1) GATE — resolve every `config.validation_record_ids` against `list_validated_strategies` and assert each has `passed_gate=1`; any strategy_id in `config.strategy_ids` WITHOUT a passed_gate=1 record raises `ValueError` (fail closed — a non-validated strategy never enters); (2) each strategy's frame is expected to carry `_rank` (per-date cross-sectional average rank from the shared chain); (3) rank-average = mean over strategies of `_rank` per (symbol, date) — Polars: `signals[sid].select(["symbol", "date", "_rank"])` per strategy, join/stack on (symbol, date), `mean_rank = weighted mean over strategies` (weights default equal 1/n per research discretion — frozen into the config); (4) re-rank the mean: `ensemble_rank = mean_rank.rank(method="average").over("date")`, `ensemble_zscore = (mean_rank - mean(mean_rank).over("date")) / std(mean_rank).over("date")`; (5) return `[symbol, date, ensemble_rank, ensemble_zscore]` sorted by (date, symbol). Raise on empty/overlapping-inconsistent inputs; never a second compute path.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/backtest/test_ensemble.py -q --tb=short`
  - Done: only passed_gate=1 strategies enter (else ValueError); the ensemble rank equals the manual mean-of-_rank reference; the output columns/shape match [symbol, date, ensemble_rank, ensemble_zscore]; equal-weight default is frozen.

- **build: Persist the ensemble — `record_wf_ensemble` + checksum-verified artifact**
  - Files: backend/app/backtest/ensemble.py
  - Read first: backend/app/research/models.py `EvaluationArtifactService.write_bundle` (L189-207), backend/app/research/repository.py `record_wf_ensemble` (from 13-02), 13-RESEARCH.md `## Rank-Average Ensembling` (artifact binding)
  - Action: Add `save_ensemble(*, config, frame: pl.DataFrame, artifact_service, repo, name: str = "wf-ensemble-v1") -> dict` — compute `input_snapshot_sha256` over the canonical JSON of (sorted strategy_ids, weights, validation_record_ids, membership_fingerprint), persist the ensemble frame via `artifact_service.write_bundle(name, signals=[...rows...])` (O_EXCL + fsync + sha256 — a second write with different inputs fails rather than overwriting), then `repo.record_wf_ensemble(name=name, strategy_ids_json, weights_json, validation_record_ids_json, input_snapshot_sha256, output_sha256=<artifact digest>, artifact_relative_path=<write_bundle descriptor path>, created_at)`. Return the wf_ensembles row + descriptor. No execution route — this is a research-use artifact Phase 14's RebalancePlan consumes as a signal source.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/backtest/test_ensemble.py -q --tb=short`
  - Done: the ensemble frame persists as an O_EXCL + fsync + sha256 artifact; the wf_ensembles row binds input_snapshot_sha256 + output_sha256 + relative path; a second save with the same inputs returns the existing row (idempotent) and with different inputs raises (O_EXCL).

- **test: Turn `test_ensemble.py` green — gate, rank-mean, shape, binding**
  - Files: backend/tests/backtest/test_ensemble.py
  - Read first: the 13-02 RED cases, backend/app/backtest/ensemble.py (module under test), backend/tests/backtest/conftest.py stub fixtures
  - Action: Make the scaffolded cases pass and add: (1) validated-only gate — an EnsembleConfig whose validation_record_ids include a passed_gate=0 row raises ValueError; a strategy with no record raises; only full-passed configs build; (2) rank-average reference — two fixture strategy frames with known `_rank`, assert the ensemble `_rank` equals the manual mean re-ranked per date; (3) output shape — `[symbol, date, ensemble_rank, ensemble_zscore]` with one row per (symbol, date); (4) weights — equal weights default; (5) artifact binding — `save_ensemble` writes the artifact, the wf_ensembles row's `output_sha256` verifies the artifact bytes (read via the existing checksum-verified read), `input_snapshot_sha256` 64-hex; (6) a non-validated strategy added to a later config fails closed even though earlier builds succeeded.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/backtest/test_ensemble.py -q --tb=short`
  - Done: the WFWD-03 contract — validated-only rank-average with the exact output shape and checksum-bound artifact persistence — is locked by green tests.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/backtest/test_ensemble.py -q --tb=short
```

All green. Grep gate: no scipy / manual rank loop in `ensemble.py` (rank comes from the chain `_rank` + Polars `.rank().over("date")`); the ensemble consumes only passed_gate=1 validated records.

## Success Criteria

- Rank-average of per-strategy `_rank` per (symbol, date) with the validated-only gate (non-validated fails closed).
- Output `[symbol, date, ensemble_rank, ensemble_zscore]` persisted as a checksum-verified artifact with the wf_ensembles row binding input + output digests — the Phase 14 signal source.

---

# Plan 13-05 — Geometry Robustness + Reporting Breadth (WFWD-01/02/03)

**wave:** 4 · **depends_on:** [13-01, 13-03] · **autonomous:** true
**requirements:** [WFWD-01, WFWD-02, WFWD-03]
**files_modified:**
- backend/app/backtest/walkforward.py (extend — calendar re-measure + fail-closed breadth)
- backend/app/research/repository.py (extend — read/list breadth)
- backend/tests/backtest/test_walkforward.py (extend — green breadth cases)
- backend/tests/backtest/test_ensemble.py (extend — green breadth cases, if needed)

## Objective

Harden the walk-forward layer from the tracer's happy path to the full WFWD-01..03 robustness surface: the trading calendar is RE-MEASURED from the governed panel at execution (the enriched lake grows ~20 trading days/month — geometry must roll forward, never assume hard-coded dates), `build_plan` fails closed below `H≈180` trading days (walk-forward degenerates below 2 folds — a clear error, never a 1-fold "validation"), every fold manifest asserts `effective_days >= 10` (the label-lookahead silent-truncation guard), and the read/list reporting surface (`get_wf_plan` / `list_wf_folds` / `list_validated_strategies`) supports the Phase 15 panel and Phase 14 handoff. Membership-drift breadth proves per-fold fingerprints change when membership changes — the reproducibility contract.

Purpose: WFWD-01's "measured, never synthetic" calendar and the label-buffer guard are only trustworthy when re-measurement and fail-closed thresholds are tested; the reporting breadth is what Phase 14/15 consume.
Output: `trading_calendar` re-measurement + fail-closed geometry breadth, `effective_days` asserts, read/list reporting breadth, green breadth tests.

## Context

- @.planning/phases/13-walk-forward-validation-parameter-search/13-RESEARCH.md — `## Fold Geometry Calibration` (history ceiling H≈180, "future enrichment" rolls the OOS forward, "re-measure at execution" validity note) + `## Common Pitfalls` (Pitfall 1 calendar, Pitfall 2 label truncation, Pitfall 5 membership drift) + `## Open Questions` (Q3 resolved_asset_ids_json for Phase 14)
- backend/app/backtest/walkforward.py (from 13-01) — build_plan + run_walk_forward
- backend/app/research/repository.py (from 13-02) — get_wf_plan / list_wf_folds / list_validated_strategies
- backend/tests/backtest/test_walkforward.py + test_ensemble.py

## Tasks

- **build: Calendar re-measurement + fail-closed geometry breadth in `walkforward.py`**
  - Files: backend/app/backtest/walkforward.py
  - Read first: 13-RESEARCH.md `## Fold Geometry Calibration` (history ceiling, enrichment note, re-measure note) + `## Common Pitfalls` (Pitfall 1 + Pitfall 2), backend/app/backtest/engine.py `load_panel`
  - Action: Extend `walkforward.py`: (1) `trading_calendar` gains a documented "measured at execution" contract — callers re-measure at run time (the enriched lake grows ~20 trading days/month; a stale calendar produces the wrong fold count and rolls the OOS forward by design — never hard-code the 2026-07-30 end date); (2) `build_plan` fails closed with a clear `ValueError` when `len(dates) - oos_size < train_size + gap_size + 2 * test_size` (i.e. fewer than 2 folds — walk-forward degenerates below H≈180); the message states the measured day count and the minimum; (3) `run_walk_forward` asserts `effective_days >= 10` per fold manifest (the label-lookahead guard — a test segment scored with horizon=5 yields only `test_size - horizon` scorable days unless the label buffer extends the compute window; anything below 10 is a silent-evidence-shrink bug and must raise); (4) keep the module constants (`WF_TRAIN_SIZE=120`, `WF_GAP=20`, `WF_TEST_SIZE=20`, `WF_OOS_SIZE=40`) as the only geometry knobs.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/backtest/test_walkforward.py -q --tb=short`
  - Done: a shortened calendar (< 180 trading days) raises a clear fail-closed error instead of a 1-fold "validation"; re-measuring a grown calendar yields a new fold count / rolls the OOS forward; effective_days < 10 raises; geometry derives from measured dates at every run.

- **build: Reporting read/list breadth in `repository.py`**
  - Files: backend/app/research/repository.py
  - Read first: 13-RESEARCH.md `## Open Questions` (Q3 — resolved_asset_ids_json so Phase 14 binds without re-resolving) + `## Repository methods`, backend/app/research/repository.py (from 13-02)
  - Action: Extend the read surface: (1) `get_wf_plan(plan_id)` returns the plan row with `trading_dates_json` + `fold_geometry_json` unwrapped; (2) `list_wf_folds(*, plan_id=None, is_oos=None, limit=200)` — ORDER BY plan_id, fold_index; unwrap chain_config_json/stats_json; positive-int limit fail-closed (limit=0 raises ValueError); (3) `list_validated_strategies(*, strategy_id=None, plan_id=None, passed_gate=None, limit=200)` — add the passed_gate filter (the ensemble gate and Phase 15 panel both filter on it); ORDER BY created_at, id; (4) READ the `resolved_asset_ids_json` column already defined by the 13-02 migration DDL (no schema addition here — Phase 14 binds the composite snapshot without re-resolving; per research Open Question 3 recommendation) and unwrap it in returned rows. All JSON columns unwrapped via the existing `_record`-style mapping; still append-only.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/backtest/test_walkforward.py tests/backtest/test_ensemble.py -q --tb=short`
  - Done: get/list round-trips with unwrapped JSON; list filters by plan_id/is_oos/passed_gate and caps at limit (limit=0 raises); validated strategies carry resolved_asset_ids_json for Phase 14.

- **test: Breadth — membership drift, calendar snap, effective_days, reporting**
  - Files: backend/tests/backtest/test_walkforward.py, backend/tests/backtest/test_ensemble.py
  - Read first: the existing green cases in both files, the 13-02 conftest fixtures (measured_calendar with the CNY hole)
  - Action: Add to `test_walkforward.py`: (1) membership drift — two runs of `run_walk_forward` with different per-date membership fixtures produce DIFFERENT membership_fingerprints (Pitfall 5 guard) while identical fixtures produce identical fingerprints (reproducibility); (2) calendar snap — the measured_calendar's 14-trading-day "Feb" hole is respected: every fold's test window has exactly 20 distinct trading dates and the gap is 20 trading dates (Pitfall 1); (3) fail-closed — `build_plan` on a <180-day calendar raises; an overlapping fold config raises; an OOS-colliding config raises; (4) effective_days — a fold whose chain frame drops the last horizon days still reports effective_days = test_size - horizon (label buffer in play) and never < 10; (5) reporting — `get_wf_plan` / `list_wf_folds(is_oos=1)` / `list_validated_strategies(passed_gate=1)` round-trip on the fixture. Add to `test_ensemble.py` if needed: `list_validated_strategies(passed_gate=1)` feeds the ensemble gate (the exact query the gate uses).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/backtest/test_walkforward.py tests/backtest/test_ensemble.py -q --tb=short`
  - Done: the WFWD-01/02/03 robustness contract — measured-calendar snapping, fail-closed geometry, effective_days guard, membership-drift fingerprints, and the read/list reporting surface — is locked by green tests.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/backtest/test_walkforward.py tests/backtest/test_ensemble.py -q --tb=short
```

All green. Grep gate: no hard-coded fold dates in `walkforward.py` (the geometry derives from `measured dates` — `grep -v '^#' | grep -c "2026-0"` == 0 in walkforward.py); `effective_days >= 10` is an assert (not a silent clamp).

## Success Criteria

- The calendar is re-measured at execution and geometry rolls forward with the lake; a <180-day history fails closed with a clear error.
- Every fold manifest asserts effective_days ≥ 10; membership fingerprints change with membership and are reproducible.
- The read/list reporting surface (get_wf_plan / list_wf_folds / list_validated_strategies incl. passed_gate + resolved_asset_ids_json) supports Phase 14 handoff and Phase 15 panels.

---

# Consolidated Threat Model

> `workflow.security_enforcement: true` (config.json) — section required. Trust model: local single-user research host; no new auth/session surface (ASVS V2/V3 N/A). New records are server-issued only (V4 minimal). Pydantic strict DTOs + enum validation (V5); SHA-256 checksums for fingerprints, params, search/ensemble inputs, and artifact bytes (V6). No execution routes anywhere.

## Trust Boundaries

| Boundary | Description |
|---|---|
| Governed panel → walk-forward | The trading calendar and per-fold panels cross from `BacktestEngine.load_panel` — the SOLE governed seam; fold boundaries snap to measured distinct dates, never a synthetic weekday calendar. |
| PIT universe → fold manifest | Per-fold membership crosses via `resolve_universe_daily`; `membership_fingerprint` (64-hex) binds each manifest to its resolved universe — a changed membership changes the fingerprint. |
| Search → wf_search_runs | Trial scores cross as OOS-fold-only aggregates; `oos_excluded=1` is enforced at insert (the search must never touch the reserved OOS); n_trials/search_space/score_distribution are recorded — the multiple-comparison guard. |
| OOS evaluation → wf_validated_strategies | The once-evaluated OOS evidence (UNIQUE wf_folds row) is the ONLY thing that can produce a validated verdict (oos_evidence_fold_id UNIQUE) — the unbiased estimate. |
| Ensemble → wf_ensembles + artifact | Only passed_gate=1 strategies cross the validated-only gate; the output artifact is O_EXCL + fsync + sha256 and the row binds input_snapshot_sha256 + output_sha256. |

## STRIDE / ASVS L1 Traceability

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|---|---|---|---|---|---|
| T-13-01 | Tampering | OOS reuse in selection (the integrity of the estimate) | critical | mitigate | Structural exclusion (`plan.folds` never contains `plan.oos_fold`) + `wf_search_runs.oos_excluded=1` enforced at insert + `wf_folds` UNIQUE exactly-once (a second OOS evaluation raises ValueError) (13-01/13-02/13-03). Test: test_walkforward exactly-once + test_optimizer_run exclusion cases. |
| T-13-02 | Tampering | Calendar misalignment — timedelta/naive-weekday fold arithmetic drifting across CNY holidays | high | mitigate | `trading_calendar` from the governed panel; `build_plan` snaps to measured indices and asserts len(test)==test_size; the Feb-2026 14-day month is a test case (13-01/13-05). Test: test_walkforward calendar-snap cases. |
| T-13-03 | Spoofing | Best-of-N selection bias presented as expected forward performance | high | mitigate | n_trials/search_space/score_distribution recorded on wf_search_runs; only the once-evaluated OOS run of best_params is reported as the unbiased estimate (13-03). Test: test_optimizer_run bookkeeping cases. |
| T-13-04 | Tampering | Silently shrinking test evidence via label lookahead | high | mitigate | Per-fold config.end = test_end + horizon; `effective_days` recorded in every manifest and asserted ≥ 10 (13-01/13-05). Test: test_walkforward effective_days cases. |
| T-13-05 | Tampering | Membership drift breaking reproducibility / stale fingerprints | medium | mitigate | Per-fold `membership_fingerprint` from `chain.resolved_universe` (sha256 over the per-date membership); identical memberships hash identically, changed memberships differ (13-01/13-05). Test: test_walkforward membership-drift cases. |
| T-13-06 | Tampering | Non-validated strategy entering an ensemble | high | mitigate | `build_ensemble` gate — every validation_record_ids resolves to a passed_gate=1 wf_validated_strategies row else fail closed (13-04). Test: test_ensemble gate cases. |
| T-13-07 | Tampering | wf_* evidence-row rewrite / fabrication | high | mitigate | All five wf_* tables append-only + no_update/no_delete triggers; UNIQUE exactly-once constraints; output/input sha256 CHECKs (13-02). Test: test_operational_migrations wf_* cases. |
| T-13-08 | Tampering | Artifact tampering / input-snapshot mismatch | medium | mitigate | Ensemble + fold evidence artifacts via O_EXCL + fsync + sha256; wf_ensembles binds input_snapshot_sha256 + output_sha256; read side checksum-verified (13-04). Test: test_ensemble binding cases. |
| T-13-09 | Tampering | 1-fold "validation" masquerading as walk-forward on short history | low | mitigate | `build_plan` fails closed below 2 folds (H < ~180) with a clear error naming the measured day count (13-05). Test: test_walkforward fail-closed cases. |
| T-13-SC | Tampering | Python package supply chain | low | accept | No new installs in Phase 13 — reuses locked polars/numpy/sqlite3 + Phase 11-12 cvxpy/scipy already `[ASSUMED]` approved (RESEARCH Package Legitimacy Audit: none added). |

# Phase Verification

```bash
# Per-wave gates (from backend/)
cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short                                             # wave 0
cd backend && .venv/bin/python -m pytest tests/backtest/test_walkforward.py tests/backtest/test_ensemble.py tests/backtest/test_optimizer_run.py -q --tb=short   # wave 0 (expected RED scaffolds)
cd backend && .venv/bin/python -m pytest tests/backtest/test_walkforward.py -q --tb=short                                             # wave 1 (tracer)
cd backend && .venv/bin/python -m pytest tests/backtest/test_optimizer_run.py tests/backtest/test_walkforward.py -q --tb=short       # wave 2 (search + validation gate)
cd backend && .venv/bin/python -m pytest tests/backtest/test_ensemble.py -q --tb=short                                               # wave 3 (ensemble)
cd backend && .venv/bin/python -m pytest tests/backtest/test_walkforward.py tests/backtest/test_ensemble.py -q --tb=short             # wave 4 (robustness + reporting)

# Phase gate (before /gsd-verify-work)
cd backend && .venv/bin/python -m pytest -x
```

Cross-module integrity checks:
- Fold boundaries snap to MEASURED trading dates (never timedelta) — the Feb-2026 14-day-month test proves the calendar snap (13-01/13-05).
- Per-fold SignalChainConfig.end == test_end + horizon — labels finite through the whole test segment; effective_days ≥ 10 asserted (13-01/13-05).
- The reserved OOS is pinned in `wf_plans` (oos_pinned_at) BEFORE any search reuse; `wf_folds` UNIQUE (plan_id, fold_index, is_oos, strategy_id, params_sha256) enforces exactly-once evaluation — a second OOS evaluation raises (13-01/13-02/13-03).
- Search scores test folds only — no train-window, no OOS — with oos_excluded=1 enforced; n_trials/search_space/score_distribution recorded (13-03).
- Ensembles consume only passed_gate=1 validated records; the artifact is checksum-bound by input_snapshot_sha256 + output_sha256 (13-04).
- Grep gate hygiene: `timedelta` in walkforward.py only for the label buffer (≤ 1 occurrence after `grep -v '^#'`); no hard-coded fold dates; negative greps use `grep -v '^#'` filtering where comments could self-invalidate.

# Phase Success Criteria

- All 5 plans complete with their per-plan gates green.
- The full backend suite is green before `/gsd-verify-work` (phase gate).
- Every locked decision in 13-CONTEXT.md is implemented (see Source Coverage Audit): rolling walk-forward with explicit gap + disjoint recorded folds + reserved once-evaluated OOS pinned before search (WFWD-01), OOS-scored parameter search with trial/space/distribution bookkeeping (WFWD-02), rank-average ensemble of validated strategies (WFWD-03), per-fold PIT universe + membership_fingerprint + per-fold SignalChainConfig through the shared chain (FACT-06), and append-only wf_* records — with zero execution authority anywhere.
- Deferred ideas from CONTEXT (RebalancePlan, frontend panels, Black-Litterman, ML expected returns) do NOT appear in any delivered artifact.

# Output

After each plan completes, create the matching summary at `.planning/phases/13-walk-forward-validation-parameter-search/13-{NN}-SUMMARY.md` documenting what landed, the evidence, and any deviations from this plan. The phase gate is the full backend suite green before `/gsd-verify-work`.
