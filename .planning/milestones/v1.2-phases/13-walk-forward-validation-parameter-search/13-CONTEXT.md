# Phase 13: Walk-Forward Validation & Parameter Search - Context

**Gathered:** 2026-08-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 13 delivers the validation layer of the v1.2 pipeline: **rolling (non-expanding) walk-forward validation** with an explicit gap between train/test folds, disjoint recorded folds, and a **reserved independent final OOS segment** evaluated exactly once; **parameter optimization scored on OOS folds** (never in-sample) with multiple-comparison bookkeeping; and **strategy ensembling** via rank-average of validated signals. It consumes the Phase 10 shared signal chain and Phase 11 optimizer, and produces validated strategies that feed Phase 14's RebalancePlan.

It is the fourth phase of milestone v1.2. All three requirements in scope: WFWD-01 (P1), WFWD-02 (P2), WFWD-03 (P2). No execution authority anywhere.

**In scope:** WFWD-01, WFWD-02, WFWD-03.
**Out of scope:** RebalancePlan discretization (Phase 14), frontend (Phase 15). No execution routes.

</domain>

<decisions>
## Implementation Decisions

### Fold Geometry (WFWD-01)
- **Rolling (non-expanding)** windows — a fold is a `(train_start, train_end, test_start, test_end)` rectangle with an explicit gap between train and test.
- **Explicit gap** — starting point `WF_GAP = 20` trading days (AlphaMaster documented baseline), calibrated to available A-share history during planning.
- **Disjoint recorded folds** — each test segment is recorded; folds do not overlap.
- **Reserved final OOS segment** — evaluated exactly once, never touched by selection or parameter search. Its reservation is pinned BEFORE any parameter-search reuse.

### PIT Universe per Fold (WFWD-01 + Phase 10 contract)
- Every fold resolves its universe via `resolve_universe_daily` (Phase 10 PIT contract — per-date membership, no survivorship bias).
- Fold manifests record `membership_fingerprint`.
- Each fold's signal chain uses a per-fold `SignalChainConfig` (same shared chain — anti train/serve skew).

### Parameter Optimization (WFWD-02, P2)
- Scored on **walk-forward OOS folds** (never in-sample).
- Records **trial count, search space, score distribution** — the multiple-comparison-bias guard.
- Reuses `backtest/optimizer.py` grid-search pattern (`GRID_MAX_COMBINATIONS` cap) with OOS reservation.

### Strategy Ensembling (WFWD-03, P2)
- **Rank-average** of validated strategy signals (only strategies that passed walk-forward validation).
- Output is research-use (candidate input for Phase 14 RebalancePlan).
- Consumed via the shared signal chain.

### Claude's Discretion
- Exact fold train/test sizes + gap value (WF_GAP starting 20, calibrated to A-share history length), fold count.
- Parameter search space definition + trial cap, score metric (e.g. OOS Sharpe/IC).
- Ensemble weighting details within rank-average.
- New append-only table schema for fold/search/ensemble records (following existing conventions).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `research/signal_chain.py` — `FactorSignalChain.compute` with per-fold `SignalChainConfig`; PIT per-date filter already wired (Phase 10).
- `research/universe.py` — `resolve_universe_daily` (Phase 10 PIT contract).
- `backtest/optimizer.py` — grid-search pattern (`OptimizeConfig`, `StrategyOptimizer`, `GRID_MAX_COMBINATIONS` cap) — the pattern to extend with OOS reservation.
- `backtest/engine.py` — `BacktestEngine.load_panel` governed seam; portfolio simulation.
- `portfolio/optimizer.py` + `portfolio/risk.py` — Phase 11/12 optimization + risk models (per-fold covariance/optimization candidates).
- `research/repository.py` + `operational/migrations.py` — append-only conventions; Phase 10/11/12 tables.
- `research/models.py` — composite models (validated-strategy signal source).

### Established Patterns
- Append-only SQLite rows + immutability triggers; membership_fingerprint in manifests; O_EXCL+fsync+sha256 artifacts.
- `BacktestEngine.load_panel` sole governed seam; PIT per-date filter after the seam.
- Shared signal chain single implementation.
- Module docstrings know/don't-know; ruff line-100 py311.

### Integration Points
- New `backtest/walkforward.py` (rolling folds + reserved OOS), `backtest/ensemble.py` (rank-average).
- `backtest/optimizer.py` gains OOS reservation (search scored on OOS folds).
- Phase 14 consumes validated strategies → RebalancePlan input.

</code_context>

<specifics>
## Specific Ideas

- Rolling walk-forward: for each fold, train on `[t0, t1]`, gap `[t1, t1+gap]`, test on `[t1+gap, t2]`; disjoint non-overlapping test segments; reserved final OOS segment `[tN, end]` evaluated exactly once.
- AlphaMaster `WF_GAP=20` documented starting point for the gap (research SUMMARY).
- Parameter search: grid over the search space, each trial scored on OOS folds only; trial count + search space + score distribution recorded (multiple-comparison guard).
- Ensemble: rank-average of validated strategies' per-date cross-sectional signals; output feeds Phase 14.

</specifics>

<deferred>
## Deferred Ideas

- RebalancePlan + paper rebalance (Phase 14).
- Frontend panels (Phase 15).
- Black-Litterman, ML expected returns (v2).

</deferred>
