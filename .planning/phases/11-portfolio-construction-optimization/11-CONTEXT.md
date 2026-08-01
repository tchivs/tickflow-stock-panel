# Phase 11: Portfolio Construction & Optimization - Context

**Gathered:** 2026-08-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 11 delivers the optimization core of the v1.2 pipeline: sample covariance with explicit PSD check/repair, auditable long-only **minimum-volatility** and **HRP-baseline** portfolios under a **constraint stack**, and **immutable optimization run records** (input-snapshot SHA-256, solver/options/status, failed runs retained with reason). It consumes the Phase 10 multi-factor composite (by snapshot) as the expected-return input and produces continuous target weights for Phase 14's RebalancePlan.

It is the second phase of milestone v1.2. Risk models and attribution land in Phase 12; Phase 11 ships the sample-covariance path and the optimizer. Every run is an append-only immutable record — the audit contract later phases inherit.

**In scope:** PFOL-01, PFOL-02, PFOL-03, PFOL-04.
**Out of scope:** risk-model suite beyond sample covariance (semi/exponential/Ledoit-Wolf → Phase 12), drawdown/exposure attribution (Phase 12), walk-forward (Phase 13), RebalancePlan discretization (Phase 14), frontend (Phase 15). No execution authority anywhere.

</domain>

<decisions>
## Implementation Decisions

### Optimization Engine (research flag — resolved 2026-08-01)
- **cvxpy 1.9.2 is the primary QP solver** — added as a new base dependency (passes package-legitimacy gate: PyPI-verified, active maintainers, bundled OSQP/Clarabel/SCS/HiGHS, supports Python 3.11–3.14). The constraint stack (long-only box + per-instrument cap + min cash + convex turnover penalty) is genuine convex-QP territory where scipy SLSQP degrades.
- **scipy is used only for HRP clustering** (`scipy.cluster.hierarchy.linkage`, already promoted to base in Phase 10) — never as the general optimizer.
- Solver/options/status recorded in every run record (audit contract). Default solver: Clarabel (or OSQP) with recorded options.

### Objectives & Baselines (PFOL-02)
- **Default objective: long-only minimum volatility** (min-vol).
- **HRP baseline** ships in Phase 11 (scipy linkage available): hierarchical risk parity as a baseline portfolio rendered alongside min-vol.
- **max-Sharpe is an explicit non-default option** — never the default; when selected, baselines (min-vol + HRP) MUST be rendered alongside for comparison.

### Covariance & PSD (PFOL-01)
- Sample covariance built from a governed panel (PIT-filtered, per Phase 10 universe resolution).
- **PSD check + repair is an explicit recorded step** — method, epsilon, eigenvalues before/after written into the immutable run record. Never silent repair.
- **Immutable run records**: every optimization run is append-only with `input_snapshot_sha256`, expected-return method, risk model, solver name/version/options, problem status, output weights; failed runs retained with their failure reason.

### Inputs & Costs (PFOL-03/04)
- **Expected-return input**: Phase 10 composite model snapshot (z-score, deterministic, no ML) consumed BY SNAPSHOT (artifact + `input_snapshot_sha256`), never a live module hand-off.
- **Constraint stack**: long-only bounds, per-instrument cap, minimum cash, convex turnover cost.
- **Industry cap deferred** — fail-closed until a governed industry mapping exists (sector JOIN is not implemented).
- **Turnover cost**: linear proxy based on historical turnover rate (reuses the fees/slippage pattern from the backtest engine).

### Claude's Discretion
- Exact cvxpy formulation (objective scaling, constraint parameters), default cap/min-cash values, turnover penalty coefficient — planner/researcher discretion within the locked decisions above.
- New SQLite table schema for optimization run records (append-only, following `migrations.py` + `ResearchRepository` conventions).
- Whether HRP uses single-linkage or other linkage method — standard scipy linkage default.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `research/models.py` — Phase 10 `build_composite` produces deterministic composite z-score + `input_snapshot_sha256`; Phase 11 consumes by snapshot.
- `research/signal_chain.py` — `FactorSignalChain.compute`; governed panel access via `BacktestEngine.load_panel`.
- `research/universe.py` — PIT universe resolver (per-date membership filter).
- `backtest/engine.py` — `BacktestEngine.load_panel`, A-share matching rules (fees/slippage pattern, T+1, limits).
- `backtest/optimizer.py` — existing grid-search pattern (`OptimizeConfig`, `StrategyOptimizer`, `GRID_MAX_COMBINATIONS` cap) — the pattern, not the engine.
- `research/repository.py` + `operational/migrations.py` — append-only SQLite conventions; Phase 10 added 4 tables + immutability triggers.
- `research/catalog.py` — `ExperimentCatalog` first-class records (Phase 10 `record_composite_model`).
- scipy 1.17.1 (base deps, Phase 10) — `scipy.cluster.hierarchy.linkage` for HRP.

### Established Patterns
- Append-only SQLite rows with signature checksums + immutability triggers (Phase 10).
- `BacktestEngine.load_panel` as the sole governed-data seam; PIT per-date filter AFTER the seam.
- Snapshot-bound immutable artifacts (`input_snapshot_sha256`, O_EXCL + fsync + sha256).
- Module docstrings state know/don't-know; ruff line-100 py311; `# noqa: BLE001` for broad catches.

### Integration Points
- New `portfolio/{optimizer,risk,repository,schemas}.py` modules (portfolio/ currently has only service.py).
- `operational/migrations.py` gains optimization-run tables.
- `research/models.py` composite snapshot → optimizer input.
- Phase 12 consumes the recorded risk model + PSD provenance; Phase 14 consumes continuous weights.

</code_context>

<specifics>
## Specific Ideas

- cvxpy 1.9.2 as the auditable QP engine — records solver/options/status (PyPortfolioOpt variable-substitution warning honored: max-Sharpe not default).
- HRP ~50 lines over scipy linkage — hierarchical clustering → inverse-variance allocation per cluster (PyPortfolioOpt HRP contract as design reference).
- Immutable run records follow the Phase 10 frozen-panel checksum discipline: O_EXCL + fsync + sha256.
- Turnover cost as a convex penalty in the QP (not a hard constraint) — keeps the problem convex and auditable.

</specifics>

<deferred>
## Deferred Ideas

- Full risk-model suite (semi/exponential/Ledoit-Wolf + PSD provenance) → Phase 12.
- Drawdown/exposure/contribution attribution → Phase 12.
- Industry cap — deferred until a governed industry mapping exists (fail-closed).
- Black-Litterman expected returns, max-Sharpe as first-class objective, short selling, auto-rebalance → v2.
- ML-based expected returns (OPT-01, v2).

</deferred>
