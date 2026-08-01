# Requirements: AthenaQuant v1.2 End-to-End Factor Portfolio Pipeline

**Defined:** 2026-07-31
**Core Value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.

## v1 Requirements

Requirements for the v1.2 milestone. Each maps to a roadmap phase.

### Factor Library & Multi-Factor Model

- [x] **FACT-01**: Researcher can run factor admission gates — train/val IC threshold, no-lookahead check, no-label-leakage check, and similarity dedup — and every admission verdict is recorded as an immutable append-only record with the candidate trail (including rejections).
- [x] **FACT-02**: Factor evaluation reports ICIR, monthly robustness, and coverage alongside IC/RankIC, with the full monthly evidence set exposed (not a scalar mean).
- [x] **FACT-03**: Researcher can compose admitted factors into a deterministic multi-factor expected-return model (equal-weight or IC-weighted cross-sectional z-score, no ML), consumed by portfolio optimization.
- [ ] **FACT-04**: Factor DSL extension enforces a partition-context contract — every operator declares per-date / per-symbol / pointwise semantics, label fields are denied in the allowlist, and a deterministic shifted-label leakage test gates DSL changes.
- [x] **FACT-05**: Admitted factors are stored in an immutable catalog with summary storage (coverage, finite counts, signature) and revision lineage.
- [x] **FACT-06**: A single shared factor signal chain computes cross-sectional factor values from compiled DSL over governed panels, used identically by evaluation, multi-factor models, walk-forward, expected returns, and live as-of rebalance suggestions (no train/serve skew).

### Portfolio Construction & Optimization

- [ ] **PFOL-01**: Researcher can build sample covariance from a governed panel with PSD check, and any PSD repair is an explicit recorded step (method, epsilon, eigenvalues before/after) in the immutable run record.
- [ ] **PFOL-02**: Researcher can solve a long-only minimum-volatility portfolio and an HRP baseline; max-Sharpe is available only as an explicit non-default option with baselines rendered alongside.
- [ ] **PFOL-03**: Optimizer supports a constraint stack: long-only bounds, per-instrument cap, minimum cash, and convex turnover cost; industry cap is deferred until a governed industry mapping exists (fail-closed otherwise).
- [ ] **PFOL-04**: Every optimization run is an immutable record with input-snapshot SHA-256, expected-return method, risk model, solver name/version/options, problem status, and output weights; failed runs are retained with their failure reason.

### Risk Analysis & Attribution

- [ ] **RSK-01**: Researcher can view risk exposure and marginal contribution attribution for an optimized portfolio, and the attribution reconciles to portfolio variance (cross-module integrity check).
- [ ] **RSK-02**: Risk-model suite includes semi-covariance, exponentially weighted covariance, and Ledoit-Wolf shrinkage with explicit PSD-repair provenance (P2).
- [ ] **RSK-03**: Researcher can view drawdown attribution decomposed by instrument and time segment (P2).

### Walk-Forward Validation & Parameter Search

- [ ] **WFWD-01**: Researcher can run rolling (non-expanding) walk-forward validation with an explicit gap between train and test folds, disjoint recorded folds, and a reserved independent final OOS segment evaluated exactly once and never touched by selection or parameter search.
- [ ] **WFWD-02**: Parameter optimization is scored on walk-forward OOS folds (not in-sample), with trial count, search space, and score distribution recorded to guard against multiple-comparison bias (P2).
- [ ] **WFWD-03**: Researcher can ensemble validated strategies via rank-average of their signals (P2).

### Output & Boundary

- [ ] **RBAL-01**: Researcher can render a RebalancePlan from continuous optimizer weights through an A-share lot-sizing adapter — 100-share lots, odd-lot sell handling, cash residue, turnover cost, blocked instruments, expiry — as an immutable research-only artifact with discretization RMSE visible.
- [ ] **RBAL-02**: Rebalance suggestions land in an auditable paper-rebalance state machine (append-only audit fact, human approval, idempotency) with no execution route anywhere; no execution authority is a hard acceptance criterion.

### API & Frontend

- [ ] **UI-01**: Backtest workspace gains ModelLibrary and WalkForward panels backed by typed server-owned contracts (P2).
- [ ] **UI-02**: Portfolio workspace gains Optimization, RiskAttribution, and RebalancePlan panels backed by typed server-owned contracts (P2).

## v2 Requirements

Deferred to future releases. Tracked but not in current roadmap.

### Portfolio

- **PFOL-05**: Black-Litterman expected returns with structured Q/P/omega view objects (natural language cannot bypass structured confidence transforms).
- **PFOL-06**: Max-Sharpe as a first-class objective with full baseline comparison (currently explicit non-default option only).
- **PFOL-07**: Short selling / leverage.
- **PFOL-08**: Auto-rebalance scheduling.

### Factor

- **FACT-07**: LLM proposes DSL expressions interactively through a mining loop with trajectory audit (restricted to DSL, never free Python).

### Optimization

- **OPT-01**: ML-based expected returns.
- **OPT-02**: Multi-period / path-dependent objectives.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Automated live broker execution | Platform-wide boundary since v1.0; RebalancePlan and paper rebalance carry zero execution authority |
| Industry cap in optimizer | Governed industry mapping does not exist; sector JOIN is fail-closed — cap deferred until mapping exists |
| Storing full factor value matrices | Anti-feature per research — summary storage only |
| "One-click best portfolio" autopilot | Hides constraint/objective tradeoffs; baselines must be rendered |
| External database or message queue | Architecture constraint since v1.0 |
| PyPortfolioOpt / skfolio / riskfolio-lib as runtime deps | Use their contracts as design spec only; cvxpy + scipy provide the solver stack |
| MLflow or external experiment tracking | Existing SQLite append-only records already cover run provenance |
| Expanding-window walk-forward | Re-leaks early validation data; rolling only |

## Traceability

Populated during roadmap creation (2026-07-31). Verified: all 20 v1 requirements mapped to exactly one phase; Status remains Pending.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FACT-01 | Phase 10 | Complete |
| FACT-02 | Phase 10 | Complete |
| FACT-03 | Phase 10 | Complete |
| FACT-04 | Phase 10 | Pending |
| FACT-05 | Phase 10 | Complete |
| FACT-06 | Phase 10 | Complete |
| PFOL-01 | Phase 11 | Pending |
| PFOL-02 | Phase 11 | Pending |
| PFOL-03 | Phase 11 | Pending |
| PFOL-04 | Phase 11 | Pending |
| RSK-01 | Phase 12 | Pending |
| RSK-02 | Phase 12 | Pending |
| RSK-03 | Phase 12 | Pending |
| WFWD-01 | Phase 13 | Pending |
| WFWD-02 | Phase 13 | Pending |
| WFWD-03 | Phase 13 | Pending |
| RBAL-01 | Phase 14 | Pending |
| RBAL-02 | Phase 14 | Pending |
| UI-01 | Phase 15 | Pending |
| UI-02 | Phase 15 | Pending |

**Coverage:**

- v1 requirements: 20 total (14 P1, 6 P2)
- Mapped to phases: 20
- Unmapped: 0 ✓

---
*Requirements defined: 2026-07-31*
*Last updated: 2026-08-01 — 10-06 complete: FACT-03 composite (catalog IC evidence + snapshot-immutable outputs) and FACT-05 admitted-factor summaries (coverage/finite-counts/signature + revision lineage) landed; Phase 10 all six FACT requirements complete*
