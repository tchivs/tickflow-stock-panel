# Roadmap: AthenaQuant

## Milestones

### v1.0 MVP — shipped 2026-07-27

Five phases delivered the governed data and portfolio loop, deterministic decision safety, reproducible factor and strategy research, evidence-grounded AI analysis, controlled advanced workflows, and independently activatable Shadow, Thesis, and Forecast modules.

- Requirements: 23/23 verified
- Phases: 5/5 complete and Nyquist-compliant
- Integration: 23/23 wired
- End-to-end flows: 10/10 complete
- Final gate: 653/653 checks passed against frozen release source

Archive:

- [v1.0 roadmap](./milestones/v1.0-ROADMAP.md)
- [v1.0 requirements](./milestones/v1.0-REQUIREMENTS.md)
- [v1.0 milestone audit](./milestones/v1.0-MILESTONE-AUDIT.md)
- [v1.0 phase artifacts](./milestones/v1.0-phases/)

---

### v1.1 Operational Hardening — shipped 2026-07-29

Four phases hardened the shipped MVP: reproducible release evidence, validation hygiene (zero application-code warnings), verified optional-model supply path, and visual regression baselines.

- Requirements: 4/4 delivered
- Phases: 4/4 complete (Phase 6-9)
- Backend tests: 961 passed, 0 failed (down from 9 failures)
- Test warnings: 143 → 84 (84 all pytest GC artifacts, 0 application-code)
- Closeout: native-Linux release evidence reverified 659/659; real Windows/WSL execution deferred by user and not claimed as tested

Archive:

- [v1.1 roadmap](./milestones/v1.1-ROADMAP.md)
- [v1.1 requirements](./milestones/v1.1-REQUIREMENTS.md)

---

### v1.2 End-to-End Factor Portfolio Pipeline — in progress (Phases 10-15)

Six phases extend the shipped research platform from single-factor evaluation into an auditable factor → portfolio → risk → walk-forward → rebalance-suggestion pipeline with zero execution authority: a factor library and multi-factor model, portfolio construction and optimization, risk models and attribution, walk-forward validation and parameter search, the RebalancePlan output and paper-rebalance boundary, and the API/SSE + frontend panels that surface it all.

- Requirements: 20/20 mapped (14 P1, 6 P2)
- Phases: 6 planned (Phase 10-15), 0 complete
- Plans: 6/6 Phase 10 plans executed (10-01..10-06 complete)
- Boundary: RebalancePlan and paper rebalance carry zero execution authority (hard acceptance criterion)

## Phases

**Phase Numbering:**

- Integer phases (10, 11, ...): v1.2 continues v1.1's numbering (v1.1 ended at Phase 9)
- Decimal phases (11.1, 11.2): urgent insertions after planning, marked with INSERTED

- [x] **Phase 10: Factor Library & Multi-Factor Model** - Admission gates, full monthly evidence, multi-factor expected returns, catalog, and the shared signal chain (completed 2026-08-01)
- [x] **Phase 11: Portfolio Construction & Optimization** - Sample covariance with PSD repair, min-vol/HRP baselines, constraint stack, immutable run records (completed 2026-08-01)
- [ ] **Phase 12: Risk Models & Attribution** - Risk-model suite with PSD provenance, exposure/contribution and drawdown attribution
- [ ] **Phase 13: Walk-Forward Validation & Parameter Search** - Rolling folds, reserved final OOS, OOS-scored parameter search, ensembling
- [ ] **Phase 14: Output & Boundary (RebalancePlan + Paper Rebalance)** - A-share lot-sized plans, auditable paper rebalance, zero execution authority
- [ ] **Phase 15: API/SSE + Frontend Panels** - ModelLibrary/WalkForward and Optimization/RiskAttribution/RebalancePlan panels

## Phase Details

### Phase 10: Factor Library & Multi-Factor Model

**Goal**: Researchers can admit factors through deterministic gates, evaluate them on full monthly evidence, compose them into a deterministic multi-factor expected-return model, and reuse one shared signal chain everywhere — with every verdict and catalog entry immutable.
**Depends on**: Phase 9 (v1.1 completion — first v1.2 phase)
**Requirements**: FACT-01, FACT-02, FACT-03, FACT-04, FACT-05, FACT-06
**Success Criteria** (what must be TRUE):

  1. Researcher can run the admission gates (train/val IC threshold, no-lookahead, no-label-leakage, similarity dedup) on a candidate factor and inspect every verdict — including rejections — as an immutable append-only record with the candidate trail.
  2. Researcher can open a factor evaluation report that shows IC, RankIC, ICIR, monthly robustness, and coverage, with the full monthly evidence set exposed rather than a scalar mean.
  3. Researcher can compose admitted factors into a deterministic multi-factor expected-return model (equal-weight or IC-weighted cross-sectional z-score, no ML) and hand it to portfolio optimization.
  4. Researcher cannot compile a DSL change whose operators lack explicit partition semantics (per-date / per-symbol / pointwise) or that references a denied label field — the compiler rejects it and the shifted-label leakage gate blocks the change.
  5. Researcher can open the admitted factor catalog and see summary storage (coverage, finite counts, signature) with revision lineage; evaluation, multi-factor models, expected returns, and live as-of rebalance suggestions all consume the same signal chain.

**Plans**: 6/6 plans executed (10-01..10-06 complete; all per-plan gates green)

- [x] 10-PLAN.md

*Planning research: point-in-time universe snapshot design (largest open data gap; persist validity ranges / delisted markers / membership-as-of without a second datastore); runtime install verification — scipy 1.17.1 promotion to base deps and sklearn 1.8.0 lazy import must be verified in an empty `.venv`, not assumed.*

### Phase 11: Portfolio Construction & Optimization

**Goal**: Researchers can build a sample covariance from governed data with explicit PSD repair, solve auditable long-only min-vol and HRP-baseline portfolios under a constraint stack, and retrieve every run as an immutable record.
**Depends on**: Phase 10
**Requirements**: PFOL-01, PFOL-02, PFOL-03, PFOL-04
**Success Criteria** (what must be TRUE):

  1. Researcher can build sample covariance from a governed panel and inspect any PSD repair as an explicit recorded step (method, epsilon, eigenvalues before/after) in the immutable run record — never silent.
  2. Researcher can solve a long-only minimum-volatility portfolio and an HRP baseline side by side; max-Sharpe is available only as an explicit non-default option with baselines rendered alongside.
  3. Researcher can apply the constraint stack — long-only bounds, per-instrument cap, minimum cash, convex turnover cost — and an industry cap fails closed until a governed industry mapping exists.
  4. Researcher can retrieve any optimization run as an immutable record carrying input-snapshot SHA-256, expected-return method, risk model, solver name/version/options, problem status, and output weights; failed runs retain their failure reason.

**Plans**: 6/6 plans executed (11-02, 11-01, 11-03, 11-04, 11-05, 11-06 complete; per-plan gates green)

- [x] 11-PLAN.md

- [x] 11-02 Wave 0 — cvxpy dep + runs migration + test scaffolds (2026-08-01)
- [x] 11-01 Tracer — end-to-end optimization pipeline
- [x] 11-03 HRP baseline
- [x] 11-04 Min-vol breadth + max-Sharpe non-default
- [x] 11-05 Snapshot binding + run-record breadth
- [x] 11-06 Constraint hardening + artifact breadth

*Planning research: optimizer engine — cvxpy 1.9.2 vs scipy SLSQP (research flag). Stack research recommends cvxpy as primary QP solver; architecture research cautions scipy-only unless a true QP is required and flags the package-legitimacy approval gate. The constraint stack (caps / min-cash / turnover) is the deciding factor. Resolve before planning.*

### Phase 12: Risk Models & Attribution

**Goal**: Researchers can inspect risk exposure and marginal contribution attribution — reconciling exactly to portfolio variance — backed by a risk-model suite whose every PSD repair carries explicit provenance, plus drawdown attribution by instrument and time segment.
**Depends on**: Phase 11
**Requirements**: RSK-01, RSK-02, RSK-03
**Success Criteria** (what must be TRUE):

  1. Researcher can inspect risk exposure and marginal contribution attribution for an optimized portfolio, and the attribution reconciles to portfolio variance (cross-module integrity check).
  2. Researcher can select among sample, semi-covariance, exponentially weighted, and Ledoit-Wolf risk models, and every PSD repair records method, epsilon, and eigenvalues before/after.
  3. Researcher can inspect drawdown attribution decomposed by instrument and time segment.

**Plans**: 3/3 plans executed (12-02 Wave 0 + 12-01 Wave 1 + 12-04 Wave 2 complete)

- [x] 12-02 Wave 0 — evidence migration + risk-model enum + test scaffolding (2026-08-02)
- [x] 12-01 Wave 1 — tracer: end-to-end attribution on a fixture run (2026-08-02)
- [x] 12-04 Wave 2 — attribution breadth (signed components + full summary report)

*Planning notes: standard patterns (PyPortfolioOpt `risk_models` contracts) — skip research-phase.*

**Plan Progress (12-03, 12-05, 12-06)**:

- [ ] 12-03 Wave 2 — risk-model suite breadth (semi / EWMA / Ledoit-Wolf + dispatcher)
- [ ] 12-05 Wave 3 — cross-model attribution + reconciliation breadth
- [ ] 12-06 Wave 4 — drawdown attribution breadth (instrument × segment)

### Phase 13: Walk-Forward Validation & Parameter Search

**Goal**: Researchers can validate strategies and tune parameters on rolling walk-forward folds with a reserved, once-evaluated final OOS segment, and ensemble validated strategies by rank-averaged signals.
**Depends on**: Phase 10, Phase 11 (may overlap Phases 11-12; the final-OOS reservation must be pinned before any parameter-search reuse)
**Requirements**: WFWD-01, WFWD-02, WFWD-03
**Success Criteria** (what must be TRUE):

  1. Researcher can run rolling (non-expanding) walk-forward validation with an explicit gap between train and test folds and disjoint recorded folds; the reserved final OOS segment is evaluated exactly once and never touched by selection or parameter search.
  2. Researcher can run parameter optimization scored on walk-forward OOS folds (never in-sample), with trial count, search space, and score distribution recorded to guard against multiple-comparison bias.
  3. Researcher can ensemble validated strategies via rank-average of their signals.

**Plans**: 4 plans
*Planning research: fold geometry (train/test size, gap) calibrated to available A-share history; AlphaMaster's `WF_GAP=20` is a documented starting point.*

### Phase 14: Output & Boundary (RebalancePlan + Paper Rebalance)

**Goal**: Researchers can render an immutable A-share RebalancePlan from continuous optimizer weights and land suggestions in an auditable paper-rebalance state machine — with zero execution authority as a hard acceptance criterion.
**Depends on**: Phase 11 (consumes continuous optimizer weights; milestone boundary phase)
**Requirements**: RBAL-01, RBAL-02
**Success Criteria** (what must be TRUE):

  1. Researcher can render a RebalancePlan from continuous optimizer weights through the A-share lot-sizing adapter — 100-share lots, odd-lot sell handling, cash residue, turnover cost, blocked instruments, expiry — as an immutable research-only artifact with discretization RMSE visible.
  2. Researcher can approve or reject a rebalance suggestion in the paper-rebalance state machine, and every transition is an append-only audit fact with idempotency.
  3. No execution route exists anywhere: no API endpoint, UI affordance, or service path can push a RebalancePlan to a live broker.

**Plans**: 3 plans
*Planning notes: standard patterns — the A-share matching layer already proven in `backtest/engine.py` (T+1, limits, suspension, lots, fees); reuse it, do not build a naive second matcher.*

### Phase 15: API/SSE + Frontend Panels

**Goal**: Backtest and Portfolio workspaces surface the full pipeline through typed server-owned contracts and streaming progress, with ModelLibrary/WalkForward and Optimization/RiskAttribution/RebalancePlan panels.
**Depends on**: Phase 14 (server-owned state and strict DTOs stable before frontend wiring)
**Requirements**: UI-01, UI-02
**Success Criteria** (what must be TRUE):

  1. Researcher can open the ModelLibrary and WalkForward panels in the Backtest workspace and inspect admitted factors, multi-factor models, and walk-forward/OOS results backed by typed server-owned contracts.
  2. Researcher can open the Optimization, RiskAttribution, and RebalancePlan panels in the Portfolio workspace and inspect immutable runs, attribution, and paper-rebalance suggestions backed by typed server-owned contracts.
  3. Walk-forward runs stream progress over SSE through the durable job pattern, and optimization/plan updates fan out through the existing shared SSE stream.

**Plans**: 4 plans
**UI hint**: yes
*Planning notes: standard patterns — existing typed `api.ts` / `queryKeys.ts` / SSE hooks; avoid UX pitfalls: never label RankIC as generic IC, never present optimizer output as "optimal" without baselines, never offer an "execute" affordance on plans, label selection-validation vs reserved OOS honestly.*

## Progress

**Execution Order:**
Phases execute in numeric order: 10 → 11 → 12 → 13 → 14 → 15 (Phase 13 may overlap Phases 11-12)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 10. Factor Library & Multi-Factor Model | 6/6 | Complete    | 2026-08-01 |
| 11. Portfolio Construction & Optimization | 7/1 | Complete    | 2026-08-01 |
| 12. Risk Models & Attribution | 3/3 | In progress |  |
| 13. Walk-Forward Validation & Parameter Search | 0/4 | Not started | - |
| 14. Output & Boundary (RebalancePlan + Paper Rebalance) | 0/3 | Not started | - |
| 15. API/SSE + Frontend Panels | 0/4 | Not started | - |

---
*Last updated: 2026-07-31 — v1.2 roadmap created (Phases 10-15, 20/20 requirements mapped)*
