# Phase 11: Portfolio Construction & Optimization - Research

**Researched:** 2026-08-01
**Domain:** Convex portfolio optimization (cvxpy QP), hierarchical risk parity, covariance PSD repair, immutable run-record audit
**Confidence:** HIGH

## Summary

Phase 11 is the optimization core of milestone v1.2: it builds **sample covariance** from a governed panel with an explicit **PSD check/repair** step, solves **long-only minimum-volatility** and **HRP-baseline** portfolios under a **constraint stack** (per-instrument cap, min cash, convex turnover penalty), and persists every run as an **immutable append-only record** carrying `input_snapshot_sha256`, expected-return method, risk model, solver name/version/options/status, output weights, and failure reason. It consumes the Phase 10 multi-factor composite **by snapshot** (never a live module hand-off) and produces continuous target weights for Phase 14's RebalancePlan. Risk-model suite (semi/exponential/Ledoit-Wolf), attribution, and walk-forward are out of scope (Phases 12–13).

The engine decision flagged in roadmap research is **resolved in CONTEXT**: **cvxpy 1.9.2 is the primary QP solver** (PyPI-verified 2026-08-01: latest 1.9.2, `requires-python >=3.11`, cp311 wheels, bundled OSQP/Clarabel/SCS/HiGHS/qdldl), **scipy is used only for HRP clustering** (`scipy.cluster.hierarchy.linkage`, already base `>=1.17.1,<1.18`). The constraint stack is genuine convex-QP territory where scipy SLSQP degrades. This research fixes the concrete design: exact QP formulation, solver default (Clarabel) with option capture, the ~50-line HRP baseline, PSD repair provenance, the immutable run-record schema + migration, and the fail-closed snapshot-binding contract.

**Primary recommendation:** `portfolio/{risk,optimizer,constraints,repository,artifacts,schemas}.py` — sample covariance + PSD repair in `risk.py`, min-vol QP (Clarabel) + HRP baseline in `optimizer.py`, policy constants in `constraints.py`, append-only run records in `repository.py`, O_EXCL+fsync+sha256 weight artifacts mirroring `research/artifacts.py`, one new migration appended to `operational/migrations.py`. Default solver **CLARABEL** (cvxpy ≥1.5 default per official docs), solver/options/status captured from `Problem.solver_stats`. Max-Sharpe is explicit non-default with baselines rendered (never default). PSD repair is **never silent** — method/epsilon/eigenvalues before/after are mandatory fields in the run record.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Optimization Engine (research flag — resolved 2026-08-01)
- **cvxpy 1.9.2 is the primary QP solver** — added as a new base dependency (passes package-legitimacy gate: PyPI-verified, active maintainers, bundled OSQP/Clarabel/SCS/HiGHS, supports Python 3.11–3.14). The constraint stack (long-only box + per-instrument cap + min cash + convex turnover penalty) is genuine convex-QP territory where scipy SLSQP degrades.
- **scipy is used only for HRP clustering** (`scipy.cluster.hierarchy.linkage`, already promoted to base in Phase 10) — never as the general optimizer.
- Solver/options/status recorded in every run record (audit contract). Default solver: Clarabel (or OSQP) with recorded options.

#### Objectives & Baselines (PFOL-02)
- **Default objective: long-only minimum volatility** (min-vol).
- **HRP baseline** ships in Phase 11 (scipy linkage available): hierarchical risk parity as a baseline portfolio rendered alongside min-vol.
- **max-Sharpe is an explicit non-default option** — never the default; when selected, baselines (min-vol + HRP) MUST be rendered alongside for comparison.

#### Covariance & PSD (PFOL-01)
- Sample covariance built from a governed panel (PIT-filtered, per Phase 10 universe resolution).
- **PSD check + repair is an explicit recorded step** — method, epsilon, eigenvalues before/after written into the immutable run record. Never silent repair.
- **Immutable run records**: every optimization run is append-only with `input_snapshot_sha256`, expected-return method, risk model, solver name/version/options, problem status, output weights; failed runs retained with their failure reason.

#### Inputs & Costs (PFOL-03/04)
- **Expected-return input**: Phase 10 composite model snapshot (z-score, deterministic, no ML) consumed BY SNAPSHOT (artifact + `input_snapshot_sha256`), never a live module hand-off.
- **Constraint stack**: long-only bounds, per-instrument cap, minimum cash, convex turnover cost.
- **Industry cap deferred** — fail-closed until a governed industry mapping exists (sector JOIN is not implemented).
- **Turnover cost**: linear proxy based on historical turnover rate (reuses the fees/slippage pattern from the backtest engine).

### Claude's Discretion
- Exact cvxpy formulation (objective scaling, constraint parameters), default cap/min-cash values, turnover penalty coefficient — planner/researcher discretion within the locked decisions above.
- New SQLite table schema for optimization run records (append-only, following `migrations.py` + `ResearchRepository` conventions).
- Whether HRP uses single-linkage or other linkage method — standard scipy linkage default.

### Deferred Ideas (OUT OF SCOPE)
- Full risk-model suite (semi/exponential/Ledoit-Wolf + PSD provenance) → Phase 12.
- Drawdown/exposure/contribution attribution → Phase 12.
- Industry cap — deferred until a governed industry mapping exists (fail-closed).
- Black-Litterman expected returns, max-Sharpe as first-class objective, short selling, auto-rebalance → v2.
- ML-based expected returns (OPT-01, v2).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PFOL-01 | Sample covariance from a governed panel with PSD check; any PSD repair is an explicit recorded step (method, epsilon, eigenvalues before/after) in the immutable run record | `## PSD Check/Repair` — governed panel via `BacktestEngine.load_panel`, `eigen_clip` repair, provenance dict mandatory in `risk_model_json`; never silent |
| PFOL-02 | Long-only min-vol portfolio + HRP baseline; max-Sharpe only as explicit non-default with baselines alongside | `## cvxpy QP Formulation` (min-vol Clarabel QP) + `## HRP Baseline` (scipy linkage ~50 lines); max-Sharpe gate + baseline rendering contract |
| PFOL-03 | Constraint stack: long-only bounds, per-instrument cap, minimum cash, convex turnover cost; industry cap fails closed until governed industry mapping | `## Constraint Stack` — policy constants, cvxpy constraint expressions, industry-cap fail-closed gate |
| PFOL-04 | Every run immutable with input-snapshot SHA-256, expected-return method, risk model, solver name/version/options, problem status, output weights; failed runs retain failure reason | `## Immutable Run Records` + `## Schema/Migration Sketch` — append-only table + immutability triggers, checksum-verified weight artifacts |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Sample covariance + PSD repair | API/Backend | Database/Storage | Server logic over governed panel; PSD provenance persisted in the immutable run record (`risk_model_json`) |
| QP solve (min-vol / max-Sharpe) | API/Backend | — | cvxpy runs in `portfolio/optimizer.py`; no client/SSR involvement (single-user research host) |
| HRP baseline | API/Backend | — | scipy `linkage` + recursive bisection in `portfolio/optimizer.py`; deterministic, no solver status |
| Constraint stack | API/Backend | — | Policy constants (`constraints.py`) → cvxpy constraint expressions; industry cap fail-closed |
| Expected-return input (composite snapshot) | API/Backend | Database/Storage | `catalog.get_composite_model` → checksum-verified artifact load → cross-section at `as_of`; never a live module hand-off |
| Immutable run records | Database/Storage | API/Backend | Append-only SQLite rows + immutability triggers; weight/covariance artifacts under `data/research_artifacts/` |

## Overview

The phase is layered so Phase 12 (risk suite), Phase 13 (walk-forward), and Phase 14 (RebalancePlan) inherit a stable audit contract:

1. **Governed-data boundary:** the covariance return matrix comes from a single `BacktestEngine.load_panel` read (`engine.py:191-200`) — PIT-filtered per Phase 10 `UniverseResolver.resolve_universe_daily` (`universe.py`, returns `[symbol, date]` membership), applied AFTER the governed read exactly as `signal_chain._resolve_membership` does (`signal_chain.py:200-224`). No parallel parquet reads.
2. **Composite-by-snapshot:** expected returns are read from the Phase 10 composite artifact (`research_artifacts/<model_id>/signals.json`, `models.py:_write_composite_artifact` l.97-129) via `catalog.get_composite_model` (l.451+), checksum-verified against the recorded `output_sha256`, then the cross-section at the run's `as_of` is taken. `input_snapshot_sha256` on the run row equals the composite's input snapshot.
3. **PSD gate:** sample covariance is symmetrized, eigenvalue-checked; if min eigenvalue < −ε, an `eigen_clip` repair runs and the provenance (method/epsilon/eigenvalues before/after) is written into `risk_model_json`. The optimizer fails closed if repair was needed but provenance is absent — never silent.
4. **Constraint stack:** long-only (`w >= 0`), per-instrument cap (`w <= cap`), min cash (`sum(w) <= 1 - min_cash`), convex turnover penalty (`coef * ||w - w_prev||_1`). Industry cap is a hard fail-closed gate until a governed industry mapping exists.
5. **Immutable audit:** one append-only `portfolio_optimization_runs` table (+ immutability triggers, Phase 10 convention `migrations.py:1510-1576`) records every run including failures; weights/covariance are checksum-verified immutable artifacts.

## cvxpy QP Formulation (PRIMARY)

### Problem structure — long-only min-vol under the constraint stack

```python
import cvxpy as cp
import numpy as np

n = len(symbols)
w = cp.Variable(n, nonneg=True)               # long-only via nonneg (PFOL-03)
Sigma = np.asarray(cov_repaired, dtype=float) # MUST be PSD — cvxpy rejects indefinite quad_form

sum_to = 1.0 - min_cash                       # min cash leaves a cash floor
constraints = [
    cp.sum(w) <= sum_to,                      # min cash: at most (1 - min_cash) invested
    w <= per_instrument_cap,                  # per-instrument cap (vector of caps)
]

objective = cp.Minimize(
    cp.quad_form(w, Sigma)                     # wᵀΣw  (risk, no ½ needed — cvxpy scales)
    + turnover_coef * cp.norm1(w - w_prev)     # convex turnover penalty (PFOL-03)
)

problem = cp.Problem(objective, constraints)
options = {"solver": "CLARABEL", "eps_abs": 1e-8, "eps_rel": 1e-8, "max_iter": 20000}
problem.solve(**options)

# ── audit capture (PFOL-04) ─────────────────────────────────────────
status        = problem.status                 # 'optimal' | 'optimal_inaccurate' | ...
solver_name   = problem.solver_stats.solver_name
solve_time    = problem.solver_stats.solve_time
num_iters     = problem.solver_stats.num_iters
weights       = dict(zip(symbols, np.asarray(w.value).round(8)))
```

Notes (verified against CVXPY official docs via Context7 2026-08-01):
- **Default solver is Clarabel** — CVXPY changed the default to **Clarabel in v1.5** and **dropped the ECOS dependency in v1.6** (`doc/source/updates/index.md`). Clarabel is a modern interior-point conic solver; for a research-grade audit record it returns reliable `optimal` status and tight tolerances, which is what the immutable record should capture.
- **OSQP** (first-order ADMM) is the fallback and is the better choice only for very large sparse problems; it can return `optimal_inaccurate` unless `polish=True` and tighter tolerances are set. Since A-share universes here are hundreds of names (not tens of thousands), Clarabel's interior-point accuracy is preferred; OSQP stays as `solver_path` fallback.
- **Solver/options/status capture:** `Problem.solver_stats` exposes `solver_name`, `solve_time`, `setup_time`, `num_iters`, `extra_stats` (verified: `api_reference/cvxpy.problems.md`); `Problem.status` / `Problem.value` / variable `.value` are populated after solve. Record the **exact `options` dict passed to `solve()`** verbatim in `solver_options_json`, plus `cp.__version__` and the solver package version via `importlib.metadata.version("clarabel")` / `("osqp")` — this satisfies PFOL-04 "solver name/version/options".
- **`cp.quad_form(w, Sigma)` requires Σ PSD** — the PSD check/repair in `risk.py` MUST run before the QP is constructed. Passing an indefinite matrix raises a cvxpy error or yields garbage; the PSD gate is therefore a hard prerequisite, not a nicety.
- **Variable/parameter naming contract:** `w` (weight variable), `Sigma` (covariance array), `per_instrument_cap` (vector), `min_cash` (scalar), `w_prev` (previous weights for turnover), `turnover_coef` (scalar penalty). These names go into `portfolio/optimizer.py` and the schemas.

### max-Sharpe (explicit non-default)

```python
# Only reachable when objective == "max_sharpe" AND caller passes baselines=True.
mu = expected_returns_vector                 # composite z-score cross-section at as_of
risk_aversion = 1.0                          # policy constant
objective = cp.Maximize(mu @ w - (risk_aversion / 2) * cp.quad_form(w, Sigma))
```

Contract (PFOL-02): the run record stores `objective='max_sharpe'` AND the response/record includes the **min-vol and HRP baselines** rendered alongside. The PyPortfolioOpt variable-substitution warning (μ-uncertainty → unstable extreme weights) is honored by making it non-default — it is never the default objective.

### Default solver choice rationale (Clarabel vs OSQP)

| Criterion | Clarabel (default) | OSQP (fallback) |
|-----------|--------------------|------------------|
| Algorithm | Interior-point (conic) | First-order ADMM |
| Accuracy | High; reliable `optimal` status | Coarser; `optimal_inaccurate` common without polish |
| Problem size fit | Hundreds of names — ideal | Very large sparse — overkill here |
| Status for audit | Clean `optimal`/`infeasible`/`unbounded` | Needs `polish=True`, tighter eps |
| cvxpy default since | 1.5 (verified) | was default pre-1.5 |

`problem.solve(solver_path=["CLARABEL", "OSQP"], eps_abs=1e-8, eps_rel=1e-8)` records whichever solver actually ran via `solver_stats.solver_name`.

### Install verification plan (empty-`.venv` gate, mirroring Phase 10)

cvxpy is **not yet installed** (verified 2026-08-01: `.venv/bin/python -c "import cvxpy"` → `ModuleNotFoundError`; scipy 1.17.1 / numpy 2.4.6 / polars 1.40.1 present). Plan Wave 0 gate:

1. `cd backend && uv venv --clear` — fresh empty environment.
2. `uv sync` — cvxpy 1.9.2 resolves (requires-python `>=3.11` verified; cp311 wheels verified 2026-08-01 via PyPI JSON).
3. `uv pip check` / `uv lock --check` — no conflicts (cvxpy pins `numpy>=2.0.0`, `scipy>=1.13.0`; installed numpy 2.4.6 / scipy 1.17.1 satisfy).
4. `python -c "import cvxpy as cp; print(cp.__version__, cp.installed_solvers())"` → `1.9.2` and a list containing `CLARABEL`, `OSQP`, `SCS`, `HIGHS`.
5. `python -c "import importlib.metadata as m; print(m.version('clarabel'), m.version('osqp'))"` → record solver versions (for `solver_version` in run records).
6. **Module-top import audit:** importing `app.portfolio.optimizer` must not pull pandas at module top (numpy-only math path; pandas only at the optimization boundary per `pyproject.toml` ADR-19 comment) — subprocess asserts `"pandas" not in sys.modules`.
7. Smoke: 5-symbol fixture QP → assert `status == "optimal"`, `sum(w) <= 1 - min_cash`, weights within caps.

## HRP Baseline

~50 lines over `scipy.cluster.hierarchy` (design reference: PyPortfolioOpt HRP contract; **not** a runtime dependency — CONTEXT out-of-scope list). Deterministic: `linkage` is deterministic given input; `optimal_ordering=True` is deterministic; the recursion is pure NumPy.

```python
import numpy as np
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.spatial.distance import squareform


def _cov_to_corr(cov: np.ndarray) -> np.ndarray:
    d = np.sqrt(np.diag(cov))
    corr = cov / np.outer(d, d)
    return np.clip(corr, -1.0, 1.0)


def _cluster_weights(cov: np.ndarray, idx: np.ndarray) -> np.ndarray:
    sub = cov[np.ix_(idx, idx)]
    inv_diag = 1.0 / np.diag(sub)              # inverse-variance within cluster
    return inv_diag / inv_diag.sum()


def _cluster_variance(cov: np.ndarray, idx: np.ndarray, w: np.ndarray) -> float:
    sub = cov[np.ix_(idx, idx)]
    return float(w @ sub @ w)


def _recursive_bisect(cov: np.ndarray, order: np.ndarray,
                      left: int = 0, right: int | None = None,
                      out: np.ndarray | None = None) -> np.ndarray:
    if right is None:
        right = len(order)
    if out is None:
        out = np.ones(len(order))
    if right - left <= 1:
        return out
    mid = (left + right) // 2
    l_idx, r_idx = order[left:mid], order[mid:right]
    w_l, w_r = _cluster_weights(cov, l_idx), _cluster_weights(cov, r_idx)
    v_l, v_r = _cluster_variance(cov, l_idx, w_l), _cluster_variance(cov, r_idx, w_r)
    alpha = 1.0 - v_l / (v_l + v_r)            # more weight to lower-variance cluster
    out[l_idx] *= alpha
    out[r_idx] *= 1.0 - alpha
    _recursive_bisect(cov, order, left, mid, out)
    _recursive_bisect(cov, order, mid, right, out)
    return out


def hrp_weights(cov: np.ndarray) -> np.ndarray:
    corr = _cov_to_corr(cov)
    dist = squareform(np.sqrt((1.0 - corr) / 2.0), checks=False)
    link = linkage(dist, method="single", optimal_ordering=True)  # quasi-diagonalization
    order = leaves_list(link).astype(int)      # scipy.cluster.hierarchy.leaves_list
    return _recursive_bisect(cov, order)
```

- **Steps:** correlation distance → `linkage(method="single", optimal_ordering=True)` → `leaves_list` (quasi-diagonalization) → recursive bisection with inverse-variance allocation per cluster.
- **Linkage method:** CONTEXT leaves it to discretion; **`single` (scipy default)** matches the PyPortfolioOpt contract. `optimal_ordering=True` gives deterministic, reproducible leaf ordering (scipy 1.0+; verified available in installed scipy 1.17.1).
- **Rendering alongside min-vol:** HRP produces a full-investment weight vector (sums to 1). When rendered as a baseline in a min-cash world, scale by `(1 - min_cash)` so the comparison is apples-to-apples with the QP. The run record stores the HRP weights in `baseline_weights_json`.
- **PSD note:** HRP needs positive diagonal (`_cluster_weights` divides by diag) — the same PSD gate runs first. A diagonal-clip on a repaired covariance is fine; HRP is a baseline, not a claim of optimality.

## PSD Check/Repair

Never silent (PFOL-01, pitfall 3 from milestone research). `portfolio/risk.py`:

```python
import numpy as np


def sample_covariance(returns: np.ndarray, dropna: bool = True) -> np.ndarray:
    """Cross-sectional sample covariance on the common (all-finite) window."""
    if dropna:
        returns = returns[np.all(np.isfinite(returns), axis=1)]
    return np.cov(returns, rowvar=False)


def check_psd(cov: np.ndarray, tol: float = 1e-8) -> tuple[float, np.ndarray]:
    sym = (cov + cov.T) / 2.0
    eigvals = np.linalg.eigvalsh(sym)
    return float(eigvals.min()), eigvals


def repair_psd(cov: np.ndarray, *, method: str = "eigen_clip",
               epsilon: float = 1e-10) -> tuple[np.ndarray, dict]:
    sym = (cov + cov.T) / 2.0
    eigvals, eigvecs = np.linalg.eigh(sym)
    clipped = np.maximum(eigvals, epsilon)
    repaired = (eigvecs * clipped) @ eigvecs.T
    repaired = (repaired + repaired.T) / 2.0
    provenance = {
        "method": method,                      # 'none' if no repair was needed
        "epsilon": epsilon,
        "min_eigenvalue_before": float(eigvals.min()),
        "eigenvalues_before": eigvals.tolist(),
        "eigenvalues_after": np.linalg.eigvalsh(repaired).tolist(),
    }
    return repaired, provenance
```

- **Gate semantics:** if `check_psd(...).min() >= -tol` (numerically PSD), record `method="none"` and `eigenvalues_after=None`; still record `eigenvalues_before` (the audit wants the full spectrum). If repair ran, all four provenance keys are mandatory.
- **Fail-closed:** `portfolio/optimizer.py` refuses to build the QP (or records a `failed` run with reason) if the covariance needed repair but the provenance block is missing/empty. Never a silent `np.clip` on eigenvalues without a record.
- **`eigen_clip` vs Higham nearest-PSD:** eigen-clip is the standard, simple, auditable projection (PyPortfolioOpt `fix_nonpositive_semidefinite` contract). Higham's nearest-PSD / Dykstra iteration is a Phase 12 refinement for the full risk suite — not needed for Phase 11's sample covariance. `scipy.linalg` offers `eigh`/`eigvalsh` if preferred; numpy's LAPACK-backed `eigvalsh` is sufficient and already a base dep.
- **Why a panel can be non-PSD:** missing bars → pairwise/NaN covariance, fat tails, and the composite reindex. Dropna on the common cross-section (recorded in `risk_model_json`) removes most cases; the gate + repair closes the rest.

## Immutable Run Records

Every optimization run is one append-only row (PFOL-04). Failed runs are retained with `failure_reason`. Schema follows the Phase 10 append-only discipline: canonical JSON, `INSERT`-only, immutability triggers (see `## Schema/Migration Sketch`).

| Column | Type | Meaning |
|--------|------|---------|
| `id` | TEXT PK | `uuid4().hex` (matches artifact namespace regex `[0-9a-f]{32}`) |
| `objective` | TEXT CHECK | `min_volatility` \| `hrp` \| `max_sharpe` |
| `as_of` | TEXT | portfolio-construction date (ISO) |
| `universe` | TEXT | universe name (e.g. `cn-a-share`) |
| `model_id` | TEXT FK | composite model (Phase 10 `factor_model_models`), NULL when expected returns unused (`'none'`) |
| `composite_snapshot_id` | TEXT | `factor_model_composites.id` consumed |
| `input_snapshot_sha256` | TEXT CHECK(len=64) | = composite `input_snapshot_sha256` (audit root) |
| `expected_return_method` | TEXT | `composite-zscore-v1` \| `none` |
| `risk_model` | TEXT | `sample_covariance_v1` |
| `risk_model_json` | TEXT | covariance window + PSD provenance (method/epsilon/eigenvalues before/after) + covariance sha256 |
| `constraint_stack_json` | TEXT | cap/min-cash/turnover-coef values + policy version |
| `solver_name` | TEXT | `CLARABEL` \| `OSQP` \| ... |
| `solver_version` | TEXT | `importlib.metadata.version("clarabel")` etc. |
| `solver_options_json` | TEXT | verbatim `options` dict passed to `solve()` |
| `problem_status` | TEXT | `optimal` \| `optimal_inaccurate` \| `infeasible` \| `unbounded` \| `solver_error` \| `failed` |
| `failure_reason` | TEXT NULL | required when status = `failed`/`solver_error` |
| `output_weights_json` | TEXT NULL | `{symbol: weight}` sorted; NULL on failure |
| `output_sha256` | TEXT CHECK(len=64) NULL | sha256 of canonical weights JSON |
| `weights_artifact_relative_path` | TEXT NULL | `research_artifacts/<run_id>/weights.json` |
| `baseline_weights_json` | TEXT NULL | HRP (for min-vol/max-sharpe) or min-vol+HRP (for max-sharpe) |
| `created_at` | TEXT | ISO timestamp |

**Repository methods** (`portfolio/repository.py`, following `research/repository.py` conventions — `_json` canonical serialization l.37-44, transactional `with connection, connection` inserts, `_record` JSON un-wrapping):
- `record_optimization_run(**fields)` — atomic INSERT run row; validates sha256 hex via `re.fullmatch`, validates `problem_status` set, raises `ValueError` on `failure_reason` missing for failed status.
- `get_optimization_run(run_id)` — single row → dict with JSON columns unwrapped.
- `list_optimization_runs(objective=None, as_of=None)` — ordered by `created_at, id`; filter on objective/as_of for the Phase 15 API.
- Optional `portfolio_optimization_artifacts` table (mirrors `research_experiment_artifacts`) if Phase 12 needs covariance artifact rows; Phase 11 can store the covariance sha256 + weights path directly on the run row to keep the migration minimal.

**Artifact binding:** weights are written through a `portfolio/artifacts.py` `PortfolioArtifactService.write_bundle(run_id, weights=..., covariance=..., ...)` that mirrors `research/artifacts.py:_write_json` (l.76-118) — O_EXCL namespace + per-file O_EXCL + fsync + sha256. The run row stores `output_sha256` (weights bytes) + `weights_artifact_relative_path`; reads are checksum-verified (frozen_panel `load` pattern, `backtest/frozen_panel.py:75-137`). Covariance matrix optionally written as `covariance.json` under the same namespace for Phase 12.

## Constraint Stack

Policy constants in `portfolio/constraints.py` with recorded provenance (Claude's-discretion values — **planner must surface for user confirmation**, mirroring Phase 10 assumptions A3):

```python
# portfolio/constraints.py  —  provenance: "phase-11-policy-v1"
PER_INSTRUMENT_CAP_DEFAULT = 0.10     # 10% max single-name weight
MIN_CASH_DEFAULT = 0.05               # 5% minimum cash floor
TURNOVER_COEF_DEFAULT = 0.0014        # round-trip cost proxy (see below)
PSD_EPSILON_DEFAULT = 1e-10
MAX_SHARPE_RISK_AVERSION = 1.0        # only when objective == max_sharpe
INDUSTRY_CAP_ENABLED = False          # fail-closed until governed industry mapping exists
```

- **Per-instrument cap:** `w <= PER_INSTRUMENT_CAP_DEFAULT` (scalar broadcast to a vector). Rationale: A-share single-name concentration control; 10% keeps any optimizer from piling into one name.
- **Minimum cash:** `cp.sum(w) <= 1 - MIN_CASH_DEFAULT` — a *floor* on cash (cash = 1 − Σw ≥ 5%), consistent with Phase 14's cash-residue handling (`RBAL-01`). Alternative strict equality `==` is over-constrained; floor semantics lets the optimizer hold more cash if it wants.
- **Turnover penalty:** `TURNOVER_COEF_DEFAULT * cp.norm1(w - w_prev)` — convex (PFOL-03), not a hard constraint. The coefficient is a **linear proxy from the backtest fee model**: `MatcherConfig` defaults commission 0.02% bilateral + slippage 5bps bilateral (`engine.py:33-76`, `buy_cost_pct` l.70-71, `sell_cost_pct` l.73-76) → round-trip ≈ 0.0002×2 + 0.0005×2 ≈ **0.0014** per unit of |Δw|. Recorded provenance: `"source": "MatcherConfig fee model (engine.py)"`.
- **`w_prev` reference:** first run for a universe uses the equal-weight portfolio `1/n` (or zeros); subsequent runs accept a prior run's weights (Phase 14 rebalance context). The reference is recorded in `constraint_stack_json` as `turnover_reference` (`equal_weight` | `run_id`).
- **Industry cap:** `INDUSTRY_CAP_ENABLED = False` is a **hard fail-closed gate** — if a caller requests an industry cap, the optimizer raises/records `failed` with reason `"industry mapping unavailable"` (the sector JOIN is not implemented; milestone research pitfall 11). It is NOT silently ignored.
- All values serialize into `constraint_stack_json` on every run so the exact policy is auditable.

## Input Snapshot Binding

The optimizer consumes the Phase 10 composite **by snapshot** — never a live module hand-off (FACT-03 contract, `models.py` docstring; `catalog.CompositeModelRecord` l.172-205).

1. **Resolve the model record:** `catalog.get_composite_model(model_id)` → `CompositeModelRecord` with `input_snapshot_sha256`, `weights`, `latest_composite` = `{id, output_sha256, artifact_relative_path, input_snapshot_sha256, created_at}` (`catalog.py:451-...`).
2. **Checksum-verified artifact load:** read `data_dir / artifact_relative_path` (`research_artifacts/<model_id>/signals.json`), verify `sha256(bytes) == output_sha256`; tamper/absent/mismatch → fail closed (frozen_panel `load` pattern, `frozen_panel.py:75-137`).
3. **Cross-section at `as_of`:** parse `[symbol, date, composite]` rows; PIT-filter with `UniverseResolver.resolve_universe_daily` membership (post-seam inner join, `signal_chain.py:200-224`); take the `as_of` date's cross-sectional composite z-scores as the expected-return vector `mu` (expected-return method `composite-zscore-v1`).
4. **Audit root:** the run row's `input_snapshot_sha256` **equals the composite's `input_snapshot_sha256`** (not a re-hash of the weight output). Cross-module integrity check: `run.input_snapshot_sha256 == factor_model_composites.input_snapshot_sha256` for the recorded `composite_snapshot_id`.
5. **Fail-closed paths (all recorded as a `failed` run with `failure_reason`):**
   - `model_id` missing from catalog,
   - `latest_composite` is None (no snapshot ever recorded),
   - artifact file absent / tampered / checksum mismatch,
   - `as_of` precedes the composite artifact's `created_at` or the panel window (lookahead guard).

The risk input (returns matrix for covariance) is loaded from the same governed panel window, NOT from the composite artifact — covariance and expected returns are distinct inputs with distinct provenance (`risk_model_json` vs `input_snapshot_sha256`).

## Dependency Changes (cvxpy)

### cvxpy 1.9.2 → base deps

- **Current state (verified 2026-08-01):** `backend/pyproject.toml` has **no** cvxpy dependency; `backend/uv.lock` has **no** `cvxpy` entry; `.venv` import fails (`ModuleNotFoundError`). scipy is base `>=1.17.1,<1.18` (l.~28), numpy 2.4.6 / polars 1.40.1 installed.
- **Change:** add to base `[project] dependencies`: `"cvxpy==1.9.2"` (exact pin — solver results are version-sensitive; the audit record cites `cp.__version__`).
- **Rationale:** CONTEXT resolves the engine decision; roadmap research recommends cvxpy as the only maintained convex DSL for Python 3.11–3.14 with bundled solvers. `[VERIFIED: PyPI]` 2026-08-01: latest = **1.9.2**, released 2026-06-22, `requires-python >=3.11`, **cp311 wheels present** (5 bdist_wheel for cp311), dependencies include `osqp>=1.0.0`, `clarabel>=0.5.0`, `scs>=3.2.4.post1`, `highspy>=1.14.0`, `qdldl>=0.1.7.post0`, `numpy>=2.0.0`, `scipy>=1.13.0`, `sparsediffpy`.
- `uv lock` regenerates after the edit; installed numpy 2.4.6 / scipy 1.17.1 satisfy the floor.
- **No new extras:** base dependency, matching the milestone research ("cvxpy 1.9.2 as the optimization engine").
- `uv.lock` regenerates after the edit (`uv lock`); the solver stack (clarabel/osqp/scs/highspy/qdldl) resolves transitively.

## Schema/Migration Sketch

One new script appended to `MIGRATIONS` in `operational/migrations.py` (Phase 10 convention `migrations.py:1510-1576`; `migrate_operational_db` applies atomically with `PRAGMA user_version`, `migrations.py:1606-1635`).

```sql
-- Phase 11 append-only optimization run records (PFOL-04).
CREATE TABLE portfolio_optimization_runs (
    id TEXT PRIMARY KEY,
    objective TEXT NOT NULL CHECK (objective IN ('min_volatility', 'hrp', 'max_sharpe')),
    as_of TEXT NOT NULL,
    universe TEXT NOT NULL,
    model_id TEXT REFERENCES factor_model_models(model_id) ON DELETE RESTRICT,
    composite_snapshot_id TEXT,
    input_snapshot_sha256 TEXT NOT NULL CHECK (length(input_snapshot_sha256) = 64),
    expected_return_method TEXT NOT NULL CHECK (expected_return_method IN ('composite-zscore-v1', 'none')),
    risk_model TEXT NOT NULL CHECK (risk_model IN ('sample_covariance_v1')),
    risk_model_json TEXT NOT NULL,
    constraint_stack_json TEXT NOT NULL,
    solver_name TEXT NOT NULL,
    solver_version TEXT NOT NULL,
    solver_options_json TEXT NOT NULL,
    problem_status TEXT NOT NULL CHECK (
        problem_status IN ('optimal', 'optimal_inaccurate', 'infeasible',
                           'unbounded', 'solver_error', 'failed')
    ),
    failure_reason TEXT,
    output_weights_json TEXT,
    output_sha256 TEXT CHECK (output_sha256 IS NULL OR length(output_sha256) = 64),
    weights_artifact_relative_path TEXT,
    baseline_weights_json TEXT,
    created_at TEXT NOT NULL,
    CHECK (
        (problem_status IN ('failed', 'solver_error')) = (failure_reason IS NOT NULL)
    )
);
CREATE INDEX idx_portfolio_optimization_runs_as_of ON portfolio_optimization_runs(as_of, objective);
CREATE TRIGGER portfolio_optimization_runs_no_update BEFORE UPDATE ON portfolio_optimization_runs
BEGIN SELECT RAISE(ABORT, 'portfolio optimization runs are append-only'); END;
CREATE TRIGGER portfolio_optimization_runs_no_delete BEFORE DELETE ON portfolio_optimization_runs
BEGIN SELECT RAISE(ABORT, 'portfolio optimization runs are append-only'); END;
```

- **CHECK guarantees:** objective enum, expected-return method enum, risk-model enum, problem-status enum, sha256 length, and the invariant **failed ⇔ failure_reason present** (PFOL-04 "failed runs retained with their failure reason").
- **Model id nullable** only when `expected_return_method='none'` (min-vol/HRP risk-only runs); the CHECK for "model_id present iff method != none" is enforced at the repository layer (JSON/conditional CHECKs in SQLite are awkward — Phase 10 keeps such invariants in `ResearchRepository`).
- **Immutability triggers** exactly mirror Phase 10 (`factor_model_composites_no_update/_no_delete`, `migrations.py:1573-1576`).
- `migrate_operational_db` applies it atomically; `ResearchRepository.migrate()` / `portfolio/repository.py.migrate()` call the shared migration (the operational DB is the single append-only store, `main.py:124`).

## Verification Plan

> Read-only plan for the planner; nothing below is executed during research.

### Unit / integration tests (map to Wave 0)
- `tests/portfolio/test_risk.py` (new) — sample covariance matches a NumPy reference on a fixture panel; `check_psd` reports the true min eigenvalue; `repair_psd` returns PSD matrix + provenance with eigenvalues before/after; **never-silent** test: a non-PSD covariance without provenance is rejected.
- `tests/portfolio/test_optimizer.py` (new) — min-vol on a 2-asset fixture matches the analytical solution; cap and min-cash are active constraints (weights respect both); turnover penalty shifts weights toward `w_prev`; **max-sharpe requires explicit opt-in AND baselines rendered**; determinism: two identical runs → identical weights + identical `input_snapshot_sha256` + identical solver options.
- `tests/portfolio/test_hrp.py` (new) — HRP on a 3-asset correlated fixture respects the known cluster ordering (quasi-diagonal leaves); weights sum to 1; scaled by (1 − min_cash) when rendered; deterministic across two calls.
- `tests/portfolio/test_repository.py` (new) — run row inserted, JSON columns round-trip; UPDATE/DELETE blocked by triggers; `failed` requires `failure_reason`; sha256 length validated.
- `tests/portfolio/test_snapshot_binding.py` (new) — model present + artifact checksum match → success; model missing / artifact tampered / as_of before artifact → run recorded as `failed` with reason; run `input_snapshot_sha256 == factor_model_composites.input_snapshot_sha256`.
- Extend `tests/test_operational_migrations.py` — new table present, forward-only idempotence, enum/sha256 CHECKs, immutability triggers (mirror `test_phase10_append_only_tables_...`, l.349+).
- Extend `tests/research/test_models.py` — composite snapshot consumption path returns the artifact bytes identified by `input_snapshot_sha256` (cross-module).
- Wave 0 gate: empty-`.venv` `uv sync` + cvxpy version + `installed_solvers()` + clarabel/osqp versions + module-top import audit (`## cvxpy QP Formulation`).

### Cross-module integrity checks
- `run.input_snapshot_sha256 == factor_model_composites.input_snapshot_sha256` for the recorded snapshot.
- Library composite used as expected returns == artifact bytes verified by `output_sha256`.
- PSD provenance present in `risk_model_json` whenever the covariance was repaired (cross-module with Phase 12's risk suite).

### Phase gate
- Full backend suite green before `/gsd-verify-work` (not run during research).

## Package Legitimacy Audit

> Ecosystem verification. The gsd-tools `package-legitimacy` seam defaults to **npm**; the npm records for `cvxpy`/`clarabel`/`osqp` are squatted low-download packages — a **cross-ecosystem false positive** (protocol Step 2), the same pattern Phase 10 documented for `scipy`/`scikit-learn`. The correct registry is PyPI; verified below via direct PyPI JSON (2026-08-01) + `backend/uv.lock` + installed `.venv`.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| cvxpy | PyPI | ~10 yrs (2015) | high | github.com/cvxpy/cvxpy | OK | Approved — add `==1.9.2` to base deps |
| clarabel | PyPI (transitive) | 2025+ | n/a | github.com/oxfordcontrol/Clarabel.rs | OK | Approved — cvxpy ≥0.5.0 dependency, not declared directly |
| osqp | PyPI (transitive) | 2017+ | high | osqp.org / github.com/osqp/osqp-python | OK | Approved — cvxpy ≥1.0.0 dependency |
| scs / highspy / qdldl | PyPI (transitive) | mature | high | github.com/cvxgrp/scs, ERGO-Code/HiGHS, osqp/qdldl | OK | Approved — cvxpy bundled solvers |
| cvxpy / clarabel / osqp | **npm** | n/a | low (squats) | unrelated | SUS (cross-ecosystem) | **Inapplicable** — npm is the wrong registry for Python packages |

**Verification detail:** `pip` is absent in `.venv`; PyPI JSON fetched directly (2026-08-01) — `cvxpy` latest **1.9.2** (`requires-python >=3.11`, cp311 wheels, release 2026-06-22), `clarabel` 0.11.1 (`>=3.9`), `osqp` 1.1.3 (`>=3.8`), `scs` 3.2.11 (`>=3.9`), `highspy` 1.15.1 (`>=3.9`). The seam returned `SUS` for all PyPI entries with reason `unknown-downloads` (the seam's weekly-download lookup is null for PyPI — a seam data gap, not a slopsquat signal; `repoUrl` resolved correctly for cvxpy/osqp).

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none on the correct (PyPI) registry. The npm `SUS` results are documented false positives from a wrong-ecosystem lookup.

## Common Pitfalls

### Pitfall 1: Silent PSD repair
**What goes wrong:** eigen-clip or diagonal jitter applied without a record — the stated risk model is wrong and Phase 12 attribution reconciles to garbage.
**Why:** sample covariance from missing bars / fat tails is frequently indefinite; repair is a one-liner that's easy to apply inline.
**How to avoid:** `check_psd` → `repair_psd` as an explicit step in `portfolio/risk.py`; provenance (method/epsilon/eigenvalues before/after) is a **mandatory** field of `risk_model_json`; the optimizer fails closed if repair occurred but provenance is empty.
**Warning signs:** `risk_model_json` missing `eigenvalues_before`; `np.clip` on eigenvalues anywhere outside `risk.py`.

### Pitfall 2: Max-Sharpe default
**What goes wrong:** extreme, unstable weights from μ-estimation error (PyPortfolioOpt variable-substitution warning).
**How to avoid:** min-vol is the default; max-sharpe requires explicit `objective="max_sharpe"` + `render_baselines=True`; run record always carries min-vol + HRP baselines for max-sharpe runs.
**Warning signs:** `objective='max_sharpe'` in a run without `baseline_weights_json`.

### Pitfall 3: Non-PSD covariance passed to `cp.quad_form`
**What goes wrong:** cvxpy errors or returns garbage when Σ is indefinite; the run dies mid-flight without a record.
**How to avoid:** PSD gate is a hard prerequisite in `optimizer.py`; a `failed` run records the reason.
**Warning signs:** solver `solver_error` with no recorded PSD provenance.

### Pitfall 4: `optimal_inaccurate` treated as success
**What goes wrong:** OSQP first-order solutions are often `optimal_inaccurate` at default tolerance; weights are recorded as if exact.
**How to avoid:** default to Clarabel (interior-point, accurate); record the real status; on `optimal_inaccurate` either tighten tolerances and re-solve or mark the run `solver_error` with reason.
**Warning signs:** `problem_status` never equals `optimal_inaccurate` despite OSQP.

### Pitfall 5: Composite consumed live instead of by snapshot
**What goes wrong:** train/serve skew — the optimizer reads a live module instead of the frozen artifact; re-runs diverge.
**How to avoid:** `catalog.get_composite_model` → checksum-verified artifact load (`output_sha256`); `input_snapshot_sha256` on the run equals the composite's snapshot; fail closed on mismatch.
**Warning signs:** any `build_composite(...)` call inside `portfolio/optimizer.py`.

### Pitfall 6: cvxpy version drift changes solver results
**What goes wrong:** solver behavior (and even default solver) changes across versions; the audit record's numbers are not reproducible.
**How to avoid:** pin `cvxpy==1.9.2`; record `cp.__version__` + solver package versions in every run.
**Warning signs:** `solver_version` absent from run rows.

### Pitfall 7: Min-cash double-count / weights not summing
**What goes wrong:** `sum(w) == 1` combined with a separate cash constraint double-counts; or `sum(w) <= 1 - min_cash` is misread and cash = 1 − Σw is wrong downstream in Phase 14.
**How to avoid:** floor semantics `cp.sum(w) <= 1 - MIN_CASH_DEFAULT`; a unit test asserts `1 - sum(w) >= min_cash` and `sum(w) <= 1`.
**Warning signs:** RebalancePlan cash residue mismatch (Phase 14 integration).

### Pitfall 8: Industry cap on ungoverned data
**What goes wrong:** a cap applied to `ext_data` sector labels that aren't governed → wrong, un-auditable results.
**How to avoid:** `INDUSTRY_CAP_ENABLED=False` and a hard fail-closed gate (raise/record `failed`) when requested.
**Warning signs:** any code path joining sector labels inside the optimizer.

### Pitfall 9: HRP on indefinite covariance
**What goes wrong:** `_cluster_weights` divides by `np.diag(sub)`; a negative diagonal yields nonsense weights.
**How to avoid:** run the same PSD gate before HRP; HRP is a baseline, still audited.
**Warning signs:** HRP baseline weights outside [0,1].

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Convex QP solver | Hand-written gradient/active-set optimizer | **cvxpy 1.9.2** + Clarabel/OSQP | Convex DSL with bundled solvers; solver/options/status auditable; scipy SLSQP degrades on box+turnover |
| Hierarchical clustering | Custom agglomerative code | **`scipy.cluster.hierarchy.linkage`** (`single`, `optimal_ordering=True`) | Shipped, deterministic, tested; scipy already base |
| Quasi-diagonalization | Manual reordering | **`scipy.cluster.hierarchy.leaves_list`** | Standard HRP step; deterministic |
| Eigenvalues / PSD projection | Manual Jacobi | **`numpy.linalg.eigvalsh`/`eigh`** (LAPACK) | Verified, fast, symmetric-aware |
| Immutable weight artifacts | ad-hoc file writes | **`portfolio/artifacts.py`** mirroring `research/artifacts.py:_write_json` (O_EXCL + fsync + sha256) | Proven Phase 10 discipline; tamper-detecting reads |
| Append-only run records | New persistence layer | **`portfolio/repository.py`** following `research/repository.py` `_json`/transaction conventions | Canonical JSON, atomic inserts, UNIQUE/CHECK guards |
| Solver stats capture | Parsing solver log text | **`Problem.solver_stats`** | Official API: solver_name/solve_time/num_iters |
| Expected-return input | Live module hand-off | **`catalog.get_composite_model`** + checksum-verified artifact | Snapshot-bound, fail-closed, anti train/serve skew |

**Key insight:** every hard problem (determinism, audit, PSD provenance, snapshot binding) is solved by *reusing* shipped seams — the artifact store, the append-only repository, the governed `load_panel`, the Phase 10 composite snapshot — and adding only thin, auditable contracts on top. PyPortfolioOpt / skfolio / riskfolio-lib are **design references only** (CONTEXT out-of-scope: "Use their contracts as design spec only").

## Code Examples

### 1. Min-vol QP with full audit capture (Clarabel default)
```python
# Source: CVXPY official docs (Context7 2026-08-01) — Problem.solve / solver_stats / default-solver change
import cvxpy as cp
import numpy as np
from importlib import metadata

def solve_min_vol(cov: np.ndarray, symbols: list[str], *,
                  per_instrument_cap: float, min_cash: float,
                  turnover_coef: float, w_prev: np.ndarray) -> dict:
    n = len(symbols)
    w = cp.Variable(n, nonneg=True)
    constraints = [cp.sum(w) <= 1.0 - min_cash, w <= per_instrument_cap]
    objective = cp.Minimize(
        cp.quad_form(w, cov) + turnover_coef * cp.norm1(w - w_prev)
    )
    problem = cp.Problem(objective, constraints)
    options = {"solver": "CLARABEL", "eps_abs": 1e-8, "eps_rel": 1e-8, "max_iter": 20000}
    problem.solve(**options)                       # populates status/value/weights
    return {
        "status": problem.status,
        "solver_name": problem.solver_stats.solver_name,
        "solve_time": problem.solver_stats.solve_time,
        "num_iters": problem.solver_stats.num_iters,
        "options": options,
        "cvxpy_version": cp.__version__,
        "solver_version": metadata.version(problem.solver_stats.solver_name.lower()),
        "weights": dict(zip(symbols, np.asarray(w.value).round(8))),
    }
```
`metadata.version(...)` fails for some solver package names (`scs`, `highspy`) — record those via a fixed mapping (e.g. `{"CLARABEL": "clarabel", "OSQP": "osqp", "SCS": "scs", "HIGHS": "highspy"}`), with a `failed`-safe fallback to `"unknown"`.

### 2. PSD provenance (never silent)
```python
# Source: numpy.linalg.eigvalsh/eigh — LAPACK-backed symmetric eigendecomposition
min_eig, eigvals = check_psd(cov)                  # see ## PSD Check/Repair
if min_eig < -PSD_EPSILON_DEFAULT:
    cov, prov = repair_psd(cov, method="eigen_clip", epsilon=PSD_EPSILON_DEFAULT)
    assert prov["eigenvalues_before"] and prov["eigenvalues_after"]  # audit gate
else:
    prov = {"method": "none", "epsilon": PSD_EPSILON_DEFAULT,
            "min_eigenvalue_before": min_eig,
            "eigenvalues_before": eigvals.tolist(), "eigenvalues_after": None}
risk_model_json = {"risk_model": "sample_covariance_v1", "window": [start, end],
                   "dropna": True, "psd_repair": prov,
                   "covariance_sha256": sha256(canonical_bytes).hexdigest()}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| scipy.optimize SLSQP general NLP | **cvxpy disciplined QP** (long-only box + cap + min cash + turnover) | Phase 11 (CONTEXT-resolved) | Constraint stack is convex-QP territory; SLSQP degrades with box+turnover |
| Default solver ECOS / OSQP | **Clarabel** default since cvxpy 1.5; ECOS dropped in 1.6 | cvxpy 1.5 (verified) | Accurate interior-point results; OSQP stays as fallback |
| Max-Sharpe default | **Min-vol default + HRP baseline**; max-Sharpe explicit non-default with baselines | Phase 11 (PyPortfolioOpt variable-substitution warning) | Stable, auditable weights; no μ-driven extreme positions by default |
| Silent eigen-clip PSD repair | **Recorded PSD provenance** (method/epsilon/eigenvalues before/after) in the immutable run | Phase 11 (milestone pitfall 3) | Stated risk is correct; Phase 12 attribution reconciles |
| Un-audited optimizer runs | **Immutable run records** with solver/options/status + input snapshot sha256 | Phase 11 | Every later phase (12–14) inherits the audit contract |

**Deprecated/outdated:**
- **ECOS / ECOS_BB** as cvxpy solvers — removed in cvxpy 1.6 (verified via CVXPY updates doc); use Clarabel/OSQP/SCS.
- **scipy.optimize as the general portfolio optimizer** — scipy remains only for HRP clustering (`scipy.cluster.hierarchy.linkage`), never for the QP (CONTEXT locked decision).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `PER_INSTRUMENT_CAP_DEFAULT = 0.10` and `MIN_CASH_DEFAULT = 0.05` are reasonable A-share research defaults | Constraint Stack | Caps/cash floor too tight or loose change the feasible set; user-revisable policy constants — planner surfaces for confirmation |
| A2 | `TURNOVER_COEF_DEFAULT = 0.0014` derived from `MatcherConfig` fee model (commission 2×2bp + slippage 2×5bps) | Constraint Stack | Over/under-penalizes turnover vs variance; units differ from variance (needs calibration); user confirmation recommended |
| A3 | Clarabel is the right default solver for this problem scale (hundreds of names) | cvxpy QP Formulation | For much larger universes OSQP/SCS may be faster; solver_path fallback mitigates |
| A4 | `single` linkage + `optimal_ordering=True` is the HRP method (scipy default, PyPortfolioOpt contract) | HRP Baseline | Other linkage methods change cluster structure; single is the standard baseline |
| A5 | Min-cash is a floor (`sum(w) <= 1 - min_cash`), not strict equality | Constraint Stack | RebalancePlan cash-residue handling (Phase 14) assumes residual cash allowed |
| A6 | Run-table column names/enum values are at planner discretion within the locked audit-field contract | Schema/Migration Sketch | Cosmetic; PFOL-04 field semantics are locked |
| A7 | `metadata.version(solver)` resolves for all bundled solvers via a fixed mapping; `"unknown"` fallback if not | Code Examples | Audit completeness of solver_version; fallback keeps runs recordable |
| A8 | cvxpy 1.9.2 cp311 wheels exist (verified) and `uv sync` on the host Python 3.11.2 succeeds | Dependency Changes | If resolution differs, Wave 0 empty-`.venv` gate catches it before implementation |

## Open Questions (RESOLVED)

1. **Turnover coefficient scale.** `TURNOVER_COEF_DEFAULT = 0.0014` is a *cost* proxy (fraction of notional per unit |Δw|), but the risk term `wᵀΣw` is a *variance* in return units. The two have different units; a fixed coefficient is defensible for a research baseline but should be confirmed. *Recommendation:* keep 0.0014 with provenance; document that calibration is a Phase 13 walk-forward item.
2. **Default cap/min-cash values.** 10%/5% are Claude's-discretion proposals. *Recommendation:* surface as policy constants (`phase-11-policy-v1`) for user confirmation in discuss/plan; the values are recorded in every run so changing them is auditable.
3. **`w_prev` for the first run.** Equal-weight `1/n` vs zeros changes the turnover penalty's anchor. *Recommendation:* equal-weight (neutral start), recorded as `turnover_reference: "equal_weight"`.
4. **Min-cash semantics.** Floor (`sum(w) <= 1 - min_cash`) vs strict equality. *Recommendation:* floor (matches Phase 14 cash residue). Confirm.
5. **`expected_return_method='none'` for min-vol/HRP.** PFOL-04 requires the field on every run; min-vol/HRP don't consume expected returns. *Recommendation:* allow `'none'` with nullable `model_id`, but still record `input_snapshot_sha256` (composite snapshot identity is part of the audit trail even when unused).
6. **HRP determinism across numpy/scipy versions.** `optimal_ordering=True` tie-breaking is deterministic within a version but could differ across scipy releases. *Recommendation:* scipy pinned `<1.18` (already), and the run record stores the weights (frozen), so reproducibility holds for recorded runs.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python runtime | all | ✓ | 3.11.2 (`.venv/bin/python`) / 3.11.2 (host) | — |
| scipy | HRP clustering + PSD helpers | ✓ | 1.17.1 (installed, base `>=1.17.1,<1.18`) | — |
| numpy | covariance/eigen math | ✓ | 2.4.6 (installed) | — |
| polars | governed panel loading | ✓ | 1.40.1 (installed) | — |
| cvxpy | QP engine | ✗ | — (NOT installed; PyPI 1.9.2) | Wave 0 `uv sync` |
| clarabel / osqp / scs / highspy | bundled cvxpy solvers | ✗ | — (transitive with cvxpy) | Wave 0 `uv sync` |
| SQLite / operational.db | append-only run records | ✓ | stdlib | — |
| uv | dependency management | ✓ | 0.11.32 | — |

**Missing dependencies with no fallback:** cvxpy (and its solver stack) — the plan MUST install in Wave 0 via the empty-`.venv` gate before any implementation task that imports `cvxpy`.
**Missing dependencies with fallback:** none — everything else is installed.

## Validation Architecture

> `workflow.nyquist_validation: true` (config.json) → section required.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8+ (dev extra, `pyproject.toml`) |
| Config file | `backend/pyproject.toml` `[tool.pytest.ini_options]` (`--import-mode=importlib`, asyncio auto) |
| Quick run command | `cd backend && .venv/bin/python -m pytest tests/portfolio -x` |
| Full suite command | `cd backend && .venv/bin/python -m pytest -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PFOL-01 | Sample covariance + PSD check/repair provenance (never silent) | unit | `pytest tests/portfolio/test_risk.py -x` | ❌ Wave 0 |
| PFOL-02 | Min-vol QP + HRP baseline; max-Sharpe non-default with baselines | unit | `pytest tests/portfolio/test_optimizer.py tests/portfolio/test_hrp.py -x` | ❌ Wave 0 |
| PFOL-03 | Constraint stack (cap/min-cash/turnover); industry cap fail-closed | unit | `pytest tests/portfolio/test_optimizer.py -x` | ❌ Wave 0 |
| PFOL-04 | Immutable run records incl. failure reason; snapshot binding | unit | `pytest tests/portfolio/test_repository.py tests/portfolio/test_snapshot_binding.py -x` | ❌ Wave 0 |
| Migration | New table + triggers + CHECKs | unit | `pytest tests/test_operational_migrations.py -x` | ✅ extend |
| Cross-module | Composite snapshot == artifact bytes | unit | `pytest tests/research/test_models.py -x` | ✅ extend |

### Sampling Rate
- **Per task commit:** `pytest tests/portfolio -x` (or the touched test file).
- **Per wave merge:** `pytest tests/portfolio tests/research tests/test_operational_migrations.py -x`.
- **Phase gate:** full backend suite green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/portfolio/test_risk.py` — PFOL-01 (new)
- [ ] `tests/portfolio/test_optimizer.py` — PFOL-02/03 (new)
- [ ] `tests/portfolio/test_hrp.py` — PFOL-02 HRP baseline (new)
- [ ] `tests/portfolio/test_repository.py` — PFOL-04 immutable runs (new)
- [ ] `tests/portfolio/test_snapshot_binding.py` — PFOL-04 fail-closed snapshot (new)
- [ ] Extend `tests/test_operational_migrations.py` — `portfolio_optimization_runs` table + triggers
- [ ] Extend `tests/research/test_models.py` — composite snapshot consumption cross-check
- [ ] Wave 0 gate: empty-`.venv` `uv sync` + cvxpy version + `installed_solvers()` + solver versions + module-top import audit

## Security Domain

> `workflow.security_enforcement: true` (config.json) → section required.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Local single-user research host; no new auth surface |
| V3 Session Management | no | No new sessions |
| V4 Access Control | minimal | Server-issued run IDs only (`uuid4`); `model_id` resolved server-side via catalog (fail-closed like `research_strategy_asset_bindings`, `migrations.py:726-732`) |
| V5 Input Validation | yes | Optimization DTOs use Pydantic strict models (mirror `api/research.py` request models); `objective`/`universe`/`as_of` enums + date validation; no arbitrary solver-option injection (options dict is a fixed whitelist) |
| V6 Cryptography | yes | SHA-256 for input snapshot, weight artifact, covariance (`_checksum` pattern, `artifacts.py` / `frozen_panel.py`) |

### Known Threat Patterns for {FastAPI + Polars + SQLite + cvxpy}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Composite artifact substitution / tampering | Spoofing | Checksum-verified artifact read (`output_sha256` vs bytes) — `frozen_panel.load` pattern; fail closed on mismatch |
| Silent PSD repair hiding bad risk | Tampering | Provenance (method/epsilon/eigenvalues before/after) is a mandatory run-record field; optimizer refuses to build without it |
| Run-record tampering after the fact | Tampering | Append-only table + immutability triggers (`no_update`/`no_delete`) |
| Solver-option injection (arbitrary kwargs) | Tampering | Fixed options whitelist in `optimizer.py`; verbatim options recorded for audit |
| Lookahead (as_of before artifact window) | Elevation of Privilege (data) | `as_of`-vs-artifact/panel window guard; recorded `failed` run |
| Un-governed industry cap | Tampering | `INDUSTRY_CAP_ENABLED=False` hard fail-closed gate |

## Sources

### Primary (HIGH confidence — verified 2026-08-01)
- **PyPI JSON** (direct fetch): `cvxpy` latest 1.9.2 (`requires-python >=3.11`, cp311 wheels, release 2026-06-22, deps osqp/clarabel/scs/highspy/qdldl/numpy>=2.0/scipy>=1.13); `clarabel` 0.11.1; `osqp` 1.1.3; `scs` 3.2.11; `highspy` 1.15.1.
- **CVXPY official docs (Context7 `/cvxpy/cvxpy`)** — default-solver change to Clarabel in 1.5, ECOS removed in 1.6 (`updates/index.md`); `Problem.solve` / `SolverStats` (solver_name/solve_time/setup_time/num_iters/extra_stats) (`api_reference/cvxpy.problems.md`); `installed_solvers()`; solver options as `solve(**kwargs)`.
- **SciPy official docs (Context7 `/scipy/scipy`)** — `scipy.cluster.hierarchy.linkage` (methods incl. single/ward, nearest-neighbor chain O(N²)), `leaves_list`, `optimal_leaf_ordering`.
- **Verified code seams:** `backend/pyproject.toml` (scipy `>=1.17.1,<1.18`, no cvxpy), `backend/uv.lock` (no cvxpy entry), installed `.venv` (scipy 1.17.1, numpy 2.4.6, polars 1.40.1, cvxpy absent), `portfolio/service.py` (operational valuation — untouched by Phase 11), `research/models.py` (`build_composite` l.131+, `_input_snapshot_sha256` l.30-46, `_write_composite_artifact` l.97-129), `research/catalog.py` (`CompositeModelRecord` l.172-205, `record_composite_model` l.415-449, `get_composite_model` l.451+), `research/repository.py` (`_json` l.37-44, transactional inserts), `research/artifacts.py` (`_write_json` O_EXCL+fsync+sha256 l.76-118), `backtest/frozen_panel.py` (`create` l.38-73, `load` l.75-137), `backtest/engine.py` (`MatcherConfig` l.33-76, `load_panel` l.191-200), `research/universe.py` (`resolve_universe_daily`), `research/signal_chain.py` (`_resolve_membership` l.200-224), `operational/migrations.py` (Phase 10 block l.1510-1576, `migrate_operational_db` l.1606-1635), `app/main.py` (operational.db l.124, artifact service l.178), `tests/` (conftest, test_models.py, test_frozen_panel_artifact.py, test_operational_migrations.py).

### Secondary (MEDIUM confidence)
- `.planning/research/SUMMARY.md` — cvxpy 1.9.2 recommendation, scipy `<1.18` pin rationale, Phase 11 research flag + gap, pitfalls 3/5/11.
- `.planning/phases/10-*/10-RESEARCH.md` — empty-`.venv` gate pattern, package-legitimacy npm false-positive documentation, append-only conventions.
- `.planning/phases/11-*/11-CONTEXT.md` — locked decisions (verbatim in `## User Constraints`).

### Tertiary (LOW confidence)
- PyPortfolioOpt HRP contract (`hrp_portfolio` — correlation distance, single linkage, quasi-diag via `leaves_list`, recursive bisection inverse-variance) — used as **design reference** only (CONTEXT out-of-scope for the dependency); the exact tie-breaking is not verified this session.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — cvxpy 1.9.2 + solver versions verified against PyPI JSON (2026-08-01) and installed `.venv`; scipy 1.17.1 pinned.
- Architecture: HIGH — every recommendation mapped to a shipped seam with file:line references (artifact store, append-only repository, governed `load_panel`, composite snapshot).
- Pitfalls: HIGH — each pitfall anchored to a measured fact (cvxpy absent, scipy present, cvxpy 1.5/1.6 solver change, npm false-positive) or a shipped code path.

**Research date:** 2026-08-01
**Valid until:** 2026-08-31 (30 days; stack facts stable, cvxpy/solver versions re-verify at Wave 0)
