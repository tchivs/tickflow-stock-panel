# Phase 12: Risk Models & Attribution - Context

**Gathered:** 2026-08-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 12 delivers the risk-analysis layer of the v1.2 pipeline: **risk exposure + marginal contribution attribution** that reconciles exactly to portfolio variance (cross-module integrity check), an **extended risk-model suite** (semi-covariance, exponentially weighted covariance, Ledoit-Wolf shrinkage) with explicit PSD-repair provenance for every model, and **drawdown attribution** decomposed by instrument and time segment. It builds on Phase 11's `portfolio/risk.py` (sample covariance + PSD eigen-clip) and consumes Phase 11's immutable optimization run records (weights + covariance snapshot).

It is the third phase of milestone v1.2. All three requirements are in scope: RSK-01 (P1), RSK-02 (P2), RSK-03 (P2). No execution authority anywhere — this is a read/analyze layer over immutable records.

**In scope:** RSK-01, RSK-02, RSK-03.
**Out of scope:** walk-forward (Phase 13), RebalancePlan (Phase 14), frontend (Phase 15). No new execution routes.

</domain>

<decisions>
## Implementation Decisions

### Exposure & Contribution Attribution (RSK-01)
- Risk exposure = weight · covariance per instrument; marginal contribution = weight · (covariance · weight) contributing to portfolio variance; attribution MUST reconcile exactly to total portfolio variance (cross-module integrity check).
- Per-instrument contribution + summary; the reconciliation (sum of contributions == portfolio variance) is a hard assertion, not approximate.
- Consumes Phase 11 immutable run records (weights + covariance snapshot by `input_snapshot_sha256`/`covariance_sha256`).

### Risk-Model Suite (RSK-02, P2)
- Three models added to `portfolio/risk.py`: **semi-covariance** (downside co-movement), **exponentially weighted covariance** (EWMA), **Ledoit-Wolf shrinkage**.
- Ledoit-Wolf uses scikit-learn 1.8.0 **lazy-imported** at the risk-model boundary (shadow extra — never module-top import; Phase 10 import-audit contract).
- Every model's PSD repair records explicit provenance (method/epsilon/eigenvalues before/after) — reusing Phase 11's eigen-clip pattern. Never silent.

### Drawdown Attribution (RSK-03, P2)
- Drawdown attribution decomposed by instrument AND time segment.
- Standard underwater-curve (drawdown series) identifies drawdown periods.
- Output: drawdown periods + per-instrument contribution table.

### Integration with Phase 11
- Risk models + PSD-repair provenance recorded into `risk_model_json` (Phase 11's `covariance_sha256` seam continues).
- Attribution reads Phase 11 immutable run records — never modifies them (append-only contract).
- New risk models reuse the existing sample-covariance path and `covariance_sha256` canonical hashing.

### Claude's Discretion
- Exact semi-covariance / EWMA / Ledoit-Wolf formulas (standard implementations), decay factors (EWMA λ), shrinkage intensity (Ledoit-Wolf δ) — planner/researcher discretion within the locked decisions.
- Drawdown-period identification thresholds (e.g. min drawdown depth/duration).
- Schema shape for attribution/drawdown evidence (append-only, following existing conventions).

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `portfolio/risk.py` — Phase 11: sample covariance, `repair_psd` eigen-clip, `covariance_sha256` canonical hashing, `ensure_psd_provenance`. Extend with the 3 new models.
- `portfolio/repository.py` — `PortfolioRepository`, `portfolio_optimization_runs` append-only records with weights + covariance snapshot (Phase 11).
- `portfolio/optimizer.py` — `run_optimization`, `risk_model_json` with `covariance_sha256` + `covariance_artifact_relative_path` (Phase 12 seam).
- `portfolio/snapshot.py` — checksum-verified composite snapshot binding.
- `portfolio/artifacts.py` — immutable artifact writer (O_EXCL + fsync + sha256).
- scipy 1.17.1 (base) + scikit-learn 1.8.0 (shadow, lazy-import).
- `backtest/engine.py` — existing portfolio simulation for drawdown/returns reference.

### Established Patterns
- Append-only SQLite rows + immutability triggers; PSD repair provenance never silent.
- `covariance_sha256` canonical hashing (8-decimal JSON) for artifact round-trip.
- O_EXCL + fsync + sha256 artifact discipline.
- Module docstrings know/don't-know; ruff line-100 py311; lazy-import contract for sklearn.

### Integration Points
- `portfolio/risk.py` gains semi/EWMA/Ledoit-Wolf covariance builders + PSD provenance.
- New `portfolio/attribution.py` (exposure + contribution + reconciliation) + `portfolio/drawdown.py` (underwater curve + attribution).
- Attribution reads run records via `PortfolioRepository`; writes append-only evidence rows.
- Phase 13 walk-forward will consume risk models for per-fold covariance.

</code_context>

<specifics>
## Specific Ideas

- Marginal contribution: `MC_i = w_i · (Σ·w)_i`; portfolio variance = `wᵀΣw`; sum of MC_i == variance (hard reconciliation assertion — the cross-module integrity guard).
- Ledoit-Wolf via `sklearn.covariance.LedoitWolf` lazy-imported in `portfolio/risk.py` only (never module-top).
- EWMA: `Σ_t = λΣ_{t-1} + (1-λ)r_t r_tᵀ` with λ default 0.94 (RiskMetrics standard).
- Semi-covariance: covariance of below-mean (or below-zero) return co-movement (PyPortfolioOpt `risk_models.semicovariance` contract as reference).
- Drawdown attribution: underwater curve → drawdown periods → per-instrument contribution via return decomposition.

</specifics>

<deferred>
## Deferred Ideas

- Walk-forward validation + parameter search (Phase 13).
- RebalancePlan + paper rebalance (Phase 14).
- Frontend panels (Phase 15).
- Black-Litterman, ML expected returns (v2).

</deferred>
