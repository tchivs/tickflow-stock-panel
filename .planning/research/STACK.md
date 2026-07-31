# Stack Research

**Domain:** A-share factor → portfolio → risk research pipeline (v1.2 additions to an existing FastAPI / Polars / DuckDB / SQLite quant platform)
**Researched:** 2026-07-31
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **cvxpy** (new core dependency) | 1.9.2 | Portfolio optimization modeling — min-volatility, constrained quadratic utility, per-instrument cap, industry cap, min cash, turnover-cost | The only maintained, Python 3.11–3.14-supported convex DSL whose stock solvers (OSQP/Clarabel/SCS/HiGHS) are bundled. It is the engine PyPortfolioOpt and skfolio are built on, so it gives us the solver stack with a fraction of the dependency surface, and it compiles the exact QP we need (long-only box + linear caps + convex turnover penalty). CVXPY 1.9.2 requires Python >=3.11, matching the project. CVXPY 1.5+ defaults to Clarabel for SOCPs and removed the ECOS dependency in 1.6 — the current 1.9 series is well past the solver transition. **Recommended over PyPortfolioOpt as the primary dependency** (see Alternatives). |
| **scipy** (new core dependency) | 1.17.1 (lock-compatible; 1.18.0 is latest but requires Python >=3.12) | HRP hierarchical clustering, covariance PSD repair helpers, distance transforms | Already a transitive dependency (via scikit-learn and vectorbt), but not a declared direct dependency of the app — the research/optimization layer must declare it explicitly. HRP is ~50 lines over `scipy.cluster.hierarchy.linkage` + `fcluster`; there is no reason to import a whole HRP framework. scipy 1.17.1 requires Python 3.11–3.14 and NumPy >=1.26.4 — compatible with the locked numpy 2.4.6. Latest scipy 1.18.0 requires Python >=3.12, so pin to 1.17.x to stay aligned with the project's Python 3.11 floor. |
| **numpy** (existing transitive dep; declare explicitly) | 2.4.6 (locked) | Covariance/risk-metric math, weight vectors, correlation stats | Already locked. Factor evaluation already uses `np.corrcoef`/`np.isfinite` in `app/research/evaluation.py` and `app/backtest/engine.py` uses NumPy for matching math. The portfolio/risk layer consumes numpy arrays at the cvxpy boundary. Declare it directly so the optimization package is honest about its dependency (currently it only reaches numpy through the pandas/polars stack). |
| **pandas** (existing, ADR-19 boundary — do NOT expand) | 3.0.3 (locked) | Covariance/expected-return estimation and optimizer input snapshots at the optimization boundary only | PyPortfolioOpt/skfolio/riskfolio are pandas-native; pandas is already present at the `BacktestService` boundary per ADR-19 and pinned `>=2.2` (locked 3.0.3). v1.2 should keep the same discipline: convert the governed panel to pandas **only** at the `PortfolioOptimizationRun` boundary, never in the research/factor hot paths. This is the pragmatic seam: the panel → covariance/return estimators are most readable in pandas, and the resulting weight vector converts back to Polars for artifact storage. Do not introduce new pandas usage in factor evaluation or backtest paths. |
| **Polars + DuckDB + Parquet** (existing — no change) | polars 1.40.1, duckdb 1.5.3 (locked) | Factor evaluation over governed panels, backtest data loading, immutable panel identity | Verified in `app/backtest/engine.py` (Polars-only `scan_enriched_parquet` + `BacktestEngine.load_panel`), `app/tickflow/repository.py` (DuckDB in-memory views over Parquet), and `app/research/evaluation.py` (Polars `group_by("date").agg(pl.corr(...))` for IC/RankIC). **Decision: keep factor evaluation in Polars, do NOT move it to DuckDB SQL.** The IC/RankIC computation is a per-date group-by correlation over a wide panel — exactly Polars' strength — and the existing v1.0 code already implements it correctly and deterministically (verified `_correlation_series`, lines 317-334). DuckDB stays the cold-query layer for panels and the source of governed input identity (SHA-256 frozen-panel artifact store already exists in `app/backtest/frozen_panel.py`). |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **pyparsing** (existing transitive dep — declare directly) | 3.3.2 (locked; latest 3.3.2, released 2026-01-20) | Restricted factor DSL tokenizer/parser | AlphaAgent proves pyparsing (packrat mode) is the right parser for a restricted factor DSL. The project's v1.0 `app/research/factor_dsl.py` already ships a **hand-rolled recursive-descent parser** (tokenizer regexes + `_Parser` class, ~500 lines) with whitelist fields, fixed function arity (`abs/sign/log1p/clip/rank/zscore/rolling_mean`), canonical serialization, and AST→Polars compilation. **Recommendation: keep the hand-rolled parser — do NOT rewrite on pyparsing or lark.** It is deterministic, has zero new deps, is already tested by v1.0's hostile-input matrix, and gives exact source-location diagnostics. pyparsing stays a locked transitive dep (through matplotlib) and is listed here only for completeness. |
| **scikit-learn** (existing optional `shadow` extra) | 1.8.0 (locked) | Ledoit-Wolf covariance shrinkage (`sklearn.covariance.LedoitWolf`) | The v1.2 risk-model requirement (sample / semi / exponential / Ledoit-Wolf + PSD repair) maps exactly onto `sklearn.covariance.LedoitWolf`. sklearn is already locked as the `shadow` extra (1.8.0) and imported lazily in `app/shadow/distillation.py` — the same lazy-import pattern should be reused at the risk-model boundary. **Move sklearn from the `shadow` extra into the core optimization extra/group** rather than requiring the whole shadow module. |
| **PyPortfolioOpt** | 1.6.0 (released 2026-02-26) | Reference implementation for risk models, HRP, and optimization contracts — NOT a runtime dependency | The knowledge base's DEEP-ANALYSIS (commit `a6638d2`, v1.6.0) documents exactly the layered contract this milestone needs: `expected_returns` → `cov_matrix` → optimizer → discrete allocation, with every input recorded for audit. Its `risk_models` module is the canonical source of the sample/semi/exponential/Ledoit-Wolf + PSD-repair matrix set. **Use its contracts as the design spec; do not add it as a runtime dependency** — see What NOT to Use. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv (existing) | Dependency locking; add new deps via `uv add --extra` | Keep the existing optional-extras pattern (`backtest`, `shadow`, `forecast`, `desktop`). Add an `optimization` extra for cvxpy + scipy + sklearn, and keep base deps lean. Verify the lock with `uv lock --check`. |
| pytest (existing) | Deterministic RED-contract tests for optimization runs, risk models, walk-forward folds | Follow the v1.0 pattern: frozen governed panels + assert-only contracts. No real-market dependency. |

## Installation

```bash
# Existing core (unchanged — from backend/pyproject.toml)
uv add "fastapi>=0.115" "polars>=1.0" "duckdb>=1.0" "pyarrow>=16.0" "pydantic>=2.7"

# NEW: optimization extra (cvxpy brings OSQP/Clarabel/SCS/HiGHS solvers + numpy/scipy)
uv add --extra optimization "cvxpy==1.9.2" "scipy>=1.17,<1.18" "numpy>=2.4,<2.8"

# sklearn: currently only in the `shadow` extra — promote into `optimization`
# (or a shared `risk` extra) with the same lazy-import discipline
uv add --extra optimization "scikit-learn==1.8.0"

# Dev (existing)
uv add --dev pytest pytest-asyncio ruff mypy
```

**Version pinning note (verified against `backend/uv.lock`):** numpy 2.4.6, scipy 1.17.1, pandas 3.0.3, polars 1.40.1, duckdb 1.5.3, pyparsing 3.3.2, scikit-learn 1.8.0, numba 0.65.1, llvmlite 0.47.0, vectorbt 0.28.2 are the currently locked versions. cvxpy is **not** in the lockfile — it is a genuine addition. The local `.venv` exists but has no installed packages (empty `pip list`), so runtime install verification is deferred to the phase that adds the extra; versions above are cross-checked against PyPI metadata as of 2026-07-31.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| **cvxpy 1.9.2** (modeling + bundled solvers) | **PyPortfolioOpt 1.6.0** (wrapper on cvxpy) | PyPortfolioOpt is the fastest path when you accept its pandas-first API and its `max_sharpe` variable-substitution quirk (documented in the knowledge base: additional objectives under the substitution behave counter-intuitively — this milestone explicitly does NOT default to max Sharpe). It adds pandas+sklearn+scikit-base as required deps and hides the CVXPY model, which hurts auditability of the `PortfolioOptimizationRun` (solver, tolerances, constraint list must be recorded). **Choose PyPortfolioOpt only as a later convenience layer** if the direct-CVXPY model becomes repetitive — but the v1.2 audit contract (immutable run records with solver/options/constraints) favors owning the model. |
| **cvxpy 1.9.2** | **skfolio 0.20.1** (sklearn-style portfolio API) | skfolio is well-maintained and has excellent risk-model coverage, but pulls `cvxpy-base` + clarabel + sklearn + pandas and imposes its estimator/`Portfolio` object model. It is a heavier abstraction for a milestone that needs 4 specific objectives and 3 constraint families with full input recording. **Choose skfolio when the portfolio layer grows beyond v1.2 scope** (e.g., dozens of estimators, model selection, ensemble portfolios). |
| **cvxpy 1.9.2** | **riskfolio-lib 7.3.0** | riskfolio has the widest risk-measure coverage (CVaR, EVaR, CDaR) but a much larger surface (matplotlib + clarabel + SCS + pandas) and heavier optimization models. **Choose it only if the roadmap later requires CVaR-style risk measures** that cvxpy would need custom conic modeling for. |
| **cvxpy 1.9.2** | **scipy.optimize.minimize (SLSQP/trust-constr)** | scipy.optimize is already present and adequate for a *single* small QP (e.g., min-variance with box constraints). It becomes wrong as soon as you layer industry caps, min-cash, and turnover penalties: SLSQP returns a local solution, gives no dual/certificate, has no disciplined convexity checking, and each new constraint family needs bespoke handling. **Use scipy.optimize only for the HRP cluster-quantity optimization** (the `HRPOpt`-style top-down allocation where the cluster-variance allocation has closed form) or for tiny feasibility probes — never as the general optimizer. |
| **cvxpy 1.9.2** | **quadprog / osqp direct** | quadprog is a one-shot QP wrapper (Goldfarb-Idnani), OSQP direct is the solver itself. Both skip modeling — every constraint must be hand-coded as QP matrices, which is exactly where per-instrument/industry/min-cash/turnover layering bugs appear. **Choose them only when the entire constraint set is stable and the cvxpy model-compile overhead (ms-scale) matters** — it does not at daily rebalance frequency. |
| **Polars for factor evaluation (chosen)** | **DuckDB SQL for factor evaluation** | DuckDB SQL could compute the IC group-by (corr over a windowed panel), but: (1) the existing v1.0 evaluation already implements it correctly in Polars and is a locked, tested contract; (2) the DSL compiles to Polars expressions — evaluating via SQL would add a translation layer; (3) Polars keeps the research hot path in one language. **Use DuckDB SQL when the query is a cold, ad-hoc analysis** (e.g., ad-hoc panel inspection, missing-data checks) — that is what the repository's DuckDB views are for. |
| **scipy 1.17.1 (pinned)** | **scipy 1.18.0 (latest)** | scipy 1.18.0 requires Python >=3.12; the project floor is Python 3.11 (`requires-python = ">=3.11"`). Pin `<1.18` until the project raises its floor. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| **qlib (wholesale)** | Microsoft qlib is a full research operating system: data loaders for its own `qlib_data` format, a model zoo, recorder/experiment framework (MLflow-style), nested strategy/executor/backtest machinery. Its data-layer assumptions (its own expression engine, its own calendar/exchange) conflict with the governed Parquet/DuckDB/Polars lake, and its weight would dwarf the single-container deployment. The knowledge base DEEP-ANALYSIS itself recommends adopting only its **contracts** (Experiment / Recorder / SignalRecord / IC analysis), not the framework. | Adopt the qlib **contracts** (experiment run → immutable records, IC/RankIC signal analysis) — already implemented in v1.0's `app/research/` catalog and `evaluation.py`. |
| **MLflow (full)** | MLflow is a server/client experiment-tracking service. The milestone needs immutable run records in the existing SQLite `operational.db`, not a separate tracking server, artifact store, or model registry. v1.0 already rejected this (Phase 2 research: "no MLflow service, external database, queue, or separate dataset storage"). | Existing `app/operational/migrations.py` versioned migration tuple + `app/research/repository.py` immutable insert-only tables. |
| **PyPortfolioOpt as runtime dependency** | It would add pandas+scikit-base+scikit-learn as hard requirements (sklearn is currently optional), hide the CVXPY model, and its `DiscreteAllocation` assumes single-share units — the A-share lot-sizing adapter (100-share lots, T+1, price-limit blocked instruments, stamp tax) must be built locally anyway, so the only real value is the risk-model module, which is ~200 lines we can own and audit. | Direct CVXPY model + own risk-model module (using sklearn's LedoitWolf), following PyPortfolioOpt's contracts as the design spec. |
| **vectorbt / numba** | Already an optional `backtest` extra (vectorbt 0.28.2 + numba 0.65.1) used by legacy backtest paths. The v1.2 walk-forward loop reuses the existing `BacktestEngine` (Polars/NumPy, verified pure-Polars in `app/backtest/engine.py`) — do not add vectorbt to the new optimization/research path. numba compiles poorly with Python 3.14 in some toolchains and adds a heavy llvmlite dep. | Existing `BacktestEngine` + `app/backtest/optimizer.py` grid-search pattern (GRID_MAX_COMBINATIONS=2000 guard) extended to walk-forward folds. |
| **statsmodels / arch** | Not needed: the milestone's "risk models" are covariance estimators (sample/semi/exponential/Ledoit-Wolf), not GARCH/ARIMA. ICIR is a simple mean/std ratio (`np.mean(values)/np.std(values)` — verified pattern in `evaluation.py:347-355`). | numpy + sklearn.covariance.LedoitWolf. |
| **PyTorch / jax** | Factor evaluation, optimization, and walk-forward are all linear-algebra scale. Torch is already gated behind the optional `forecast` extra (Kronos) — do not let it leak into the research path. | numpy/scipy/cvxpy. |
| **lark parser** | Lark is a fine general parser, but the existing hand-rolled factor DSL parser is deterministic, dependency-free, already hostile-input tested in v1.0, and gives exact line/column diagnostics. Rewriting adds a dependency for zero benefit. | Existing `app/research/factor_dsl.py` recursive-descent parser. |

## Stack Patterns by Variant

**If the optimization constraint set stays at the v1.2 scope (long-only, per-instrument cap, industry cap, min cash, turnover cost):**
- Use a single CVXPY QP per objective (min-volatility, constrained quadratic utility), with HRP computed via scipy linkage as the non-convex baseline.
- Because every input and constraint is recorded in the immutable `PortfolioOptimizationRun`, expose the CVXPY `solver` + `solver_options` + final `problem.status` in the run record (matching PyPortfolioOpt's auditable-input table in the knowledge base).

**If the objective set later expands to max-Sharpe:**
- Use the variable-substitution approach (PyPortfolioOpt's `max_sharpe` does this) — but keep it non-default and document the counter-intuitive behavior under extra objectives. v1.2 explicitly keeps max Sharpe out of the default set per the milestone contract.

**If a factor evaluation query becomes a cold ad-hoc analysis over a huge window:**
- Route it through the existing DuckDB views (cold queries) instead of Polars, exactly as `KlineRepository` already does (`DuckDB cold SQL → Polars warm cache → in-memory hot`).

**If walk-forward needs parameter search (v1.2 "parameter optimization & ensembling"):**
- Reuse the existing `app/backtest/optimizer.py` grid-search pattern with its combination cap and `PanelCache`, but with **rolling** (not expanding) windows and a reserved independent OOS segment — the AlphaMaster knowledge-base evidence shows rolling-with-gap avoids early validation segments reappearing in later training.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| cvxpy 1.9.2 | Python >=3.11, numpy >=2.0, scipy >=1.13 | CVXPY 1.9 supports Python 3.11–3.14; bundles OSQP/Clarabel/SCS/HiGHS. Confirmed on PyPI 2026-07-31. |
| cvxpy 1.9.2 | numpy 2.4.6 (locked) | CVXPY 1.9.2 requires numpy >=2.0 — the lock's 2.4.6 satisfies it. |
| scipy 1.17.1 (pinned) | Python 3.11–3.14, numpy >=1.26.4 | Do NOT float to 1.18.0 — it requires Python >=3.12. |
| scipy 1.17.1 | numpy 2.4.6 | scipy 1.17.1 release notes confirm numpy 2.4 support. |
| pyportfolioopt 1.6.0 | cvxpy>=1.1.19, numpy<3.0,>=1.26, pandas<4.0,>=1.0, scikit-base<0.14 | Only relevant if adopted as a later convenience layer; requires scikit-learn>=0.24.1. |
| scikit-learn 1.8.0 | numpy, scipy, joblib, threadpoolctl | Already locked in the `shadow` extra; compatible with numpy 2.4.6 / scipy 1.17.1. |
| polars 1.40.1 | Python >=3.10, numpy optional | Factor evaluation stays Polars-native; locked version verified. |
| duckdb 1.5.3 | Python >=3.10 | In-memory views over Parquet; locked version verified. |

## Sources

- [PyPI metadata (fetched 2026-07-31)] — cvxpy 1.9.2 (py>=3.11; osqp/clarabel/scs/highspy/numpy>=2.0/scipy>=1.13), pyportfolioopt 1.6.0 (2026-02-26; cvxpy/pandas/sklearn/scikit-base), riskfolio-lib 7.3.0, skfolio 0.20.1, lark 1.3.1, pyparsing 3.3.2 (2026-01-20), scipy 1.18.0 (py>=3.12), numpy 2.5.1 (py>=3.12) — HIGH
- [backend/uv.lock, backend/pyproject.toml] — locked versions: numpy 2.4.6, scipy 1.17.1, pandas 3.0.3, polars 1.40.1, duckdb 1.5.3, pyparsing 3.3.2, scikit-learn 1.8.0, numba 0.65.1, vectorbt 0.28.2; cvxpy NOT present; Python floor >=3.11 — HIGH (verified)
- [CVXPY install/changes docs] — CVXPY 1.5+ default solver Clarabel (ECOS removed in 1.6); Python 3.11–3.14 support — HIGH
- [SciPy 1.17.0 release notes] — Python 3.11–3.14, NumPy >=1.26.4 — HIGH
- [PyPortfolioOpt DEEP-ANALYSIS (knowledge base, v1.6.0 @ a6638d2)] — auditable input contract, max_sharpe substitution warning, HRP, risk-model matrix (sample/semi/exponential/Ledoit-Wolf + PSD repair), DiscreteAllocation single-share limitation — HIGH
- [AlphaAgent DEEP-ANALYSIS (knowledge base)] — pyparsing-based restricted factor DSL, operator registry, IC/RankIC evaluation, FactorZoo storage — HIGH
- [qlib DEEP-ANALYSIS (knowledge base)] — adopt contracts (Recorder/SignalRecord/IC) not the framework; experiment-record patterns — HIGH
- [AlphaMaster DEEP-ANALYSIS (knowledge base)] — rolling (not expanding) walk-forward with gap; train/val leakage avoidance — HIGH
- [07-策略与信号系统篇.md (knowledge base)] — PyPortfolioOpt as the deterministic allocation layer between StrategyDef and RebalancePlan; A-share lot sizing must be local — HIGH
- [18-模式决策矩阵.md (knowledge base)] — default to SQLite + Parquet/DuckDB; constrained long-only optimization + discrete rebalance plan as default; only escalate when real conditions appear — HIGH
- [AthenaQuant v1.0 phase-2 research] — "no MLflow service, external database, queue, or separate dataset storage"; existing DSL parser and evaluation contracts — HIGH (verified in repo)
- [app/research/factor_dsl.py, evaluation.py, app/backtest/engine.py, frozen_panel.py, app/operational/migrations.py] — verified existing seams: hand-rolled DSL parser, Polars IC/RankIC group-by, pure-Polars backtest engine, SHA-256 frozen-panel store, versioned SQLite migrations — HIGH (verified)

---
*Stack research for: AthenaQuant v1.2 End-to-End Factor Portfolio Pipeline*
*Researched: 2026-07-31*
