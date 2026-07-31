# Project Research Summary

**Project:** AthenaQuant
**Domain:** A-share quantitative factor research → portfolio construction → risk attribution → walk-forward validation → paper rebalance suggestions (research-only, no execution authority)
**Researched:** 2026-07-31
**Confidence:** HIGH

## Executive Summary

AthenaQuant v1.2 ("End-to-End Factor Portfolio Pipeline") extends a shipped single-factor research platform into an auditable factor → portfolio → risk → rebalance-suggestion pipeline for A-share individual investors. Experts build this class of system with three non-negotiable seams: (1) **one shared factor signal chain** used identically by evaluation, multi-factor scoring, walk-forward folds, expected returns, and live as-of suggestions (eliminates train/serve skew — the AlphaMaster flagship lesson); (2) **immutable, hash-bound run records** (every weight/plan traces to a canonical `PortfolioInputSnapshot` SHA-256, following the existing frozen-panel contract); and (3) a **hard research-only output boundary** where the deliverable is a discrete A-share RebalancePlan suggestion with zero execution authority. The milestone reuses ~60% of existing scaffolding (DSL parser, IC/RankIC evaluation, factor registry with similarity dedup, immutable catalog, SHA-256 frozen panels, A-share-aware matching engine) and adds a new `portfolio/` domain plus the signal-chain backbone.

The recommended approach is a dependency-aware build: promote scipy to base deps and add cvxpy 1.9.2 as the optimization engine; land the shared signal chain before any consumer; then admit factors → compose multi-factor expected returns → solve min-vol/HRP baselines → render A-share RebalancePlans → walk-forward validate → wire API/frontend. Max-Sharpe is explicitly **not** a default objective (numerical instability + PyPortfolioOpt variable-substitution warning), Black-Litterman is deferred, and industry cap is gated on a governed industry mapping that does not yet exist (sector JOIN is fail-closed).

The key risks, each with a deterministic guard: lookahead/label leakage when the DSL is extended (shifted-label leakage test + compiler partition-context contract); survivorship bias from the missing point-in-time universe contract (the largest open data gap); silent PSD repair and un-audited optimization runs (repair method/epsilon/eigenvalues recorded in the immutable run); walk-forward leakage (rolling not expanding folds with explicit gap + reserved final OOS); and the pipeline drifting into execution authority (RebalancePlan as an immutable research-only artifact + a separate approved paper-rebalance state machine). Three integration pitfalls — governed-data boundary bypass, divergent cross-module computation, and RebalancePlan crossing into portfolio-mutation endpoints — are the top gotchas when wiring new modules into the existing host.

## Key Findings

### Recommended Stack

The stack is a **minimal addition** to an existing locked FastAPI / Polars / DuckDB / SQLite host. Core recommendation: **cvxpy 1.9.2 as the primary optimization dependency** — the only maintained convex DSL supporting Python 3.11–3.14 with bundled solvers (OSQP/Clarabel/SCS/HiGHS), compiles the exact QP needed (long-only box + per-instrument cap + industry cap + min cash + convex turnover penalty), and records solver/options/status for the audit contract. **scipy must be declared directly and pinned 1.17.1 (NOT 1.18.0 — it requires Python ≥3.12; project floor is 3.11)**; HRP is ~50 lines over `scipy.cluster.hierarchy.linkage`. **scikit-learn 1.8.0** (Ledoit-Wolf shrinkage) is promoted out of the `shadow` extra into an `optimization` extra with the existing lazy-import discipline. numpy 2.4.6 and pandas 3.0.3 are declared directly, but pandas stays confined to the `PortfolioOptimizationRun` boundary (ADR-19); factor evaluation **stays in Polars, not DuckDB SQL**. The hand-rolled factor DSL parser is kept — **no pyparsing/lark rewrite**. New deps land via `uv add --extra optimization`.

**Core technologies:**
- **cvxpy 1.9.2**: portfolio optimization modeling — direct convex DSL with bundled solvers; auditable solver/options/status
- **scipy 1.17.1** (pinned `<1.18`): HRP clustering, PSD-repair helpers, distance transforms — declare explicitly
- **scikit-learn 1.8.0**: Ledoit-Wolf covariance shrinkage — promote from `shadow` extra, lazy-import at risk-model boundary
- **numpy 2.4.6 / pandas 3.0.3**: declare directly; pandas only at the optimization boundary
- **Polars 1.40.1 + DuckDB 1.5.3 + Parquet** (unchanged): factor evaluation stays Polars-native; DuckDB only for cold ad-hoc queries
- **Existing backtest engine + optimizer**: reuse pure-Polars `BacktestEngine.load_panel` and grid-search pattern (`GRID_MAX_COMBINATIONS` cap) extended to walk-forward folds

**Do NOT add:** PyPortfolioOpt/skfolio/riskfolio-lib as runtime deps (use their contracts as design spec), qlib wholesale (contracts only), MLflow (existing SQLite append-only records), vectorbt/numba, statsmodels/arch, PyTorch/jax (gated behind `forecast` extra), lark. scipy.optimize only for HRP cluster allocation, never as the general optimizer.

### Expected Features

**Must have (table stakes / MVP launch):** factor admission gates (train/val IC threshold, no-lookahead, no-label-leakage, similarity dedup); ICIR + monthly robustness + coverage in evaluation; admitted factor catalog with summary storage; multi-factor composite expected returns (deterministic equal/IC-weight z-score, no ML); sample covariance + PSD check/repair; long-only min-volatility optimizer; HRP baseline; immutable optimization run records; RebalancePlan (continuous weights → A-share 100-share lots, cash, turnover, blocked instruments, expiry); suggestions to an auditable paper rebalance with **NO execution authority**; rolling walk-forward (not expanding) with a reserved independent final OOS segment; risk exposure + contribution attribution.

**Should have (differentiators / add-after):** shared backtest/live signal chain (anti train/serve skew); deterministic admission gates as first-class rigor; Ledoit-Wolf/semi/exponential covariance + PSD-repair options; drawdown attribution; parameter optimization scored on walk-forward OOS folds; strategy ensembling; industry cap (gated on governed industry mapping); LLM proposes DSL expressions only (never free Python code).

**Defer (v2+):** max-Sharpe as an explicit, non-default objective; Black-Litterman (needs structured view object); short selling/leverage; auto-rebalance scheduling; ML-based expected returns; multi-period/path-dependent objectives.

**Anti-features to reject:** max-Sharpe as default; free-form Python factor code; expanding-window walk-forward; industry cap without governed mapping; storing full factor value matrices; "one-click best portfolio" autopilot; external DB/message queue.

### Architecture Approach

One engine, one panel seam: **every** new computation reads governed market data exclusively through `BacktestEngine.load_panel()`, never direct repository/Parquet reads. A new **`app/research/signal_chain.py`** is the shared factor-value backbone (revision IDs → one governed panel → cross-sectional values/rank/zscore) consumed by evaluation, models, walk-forward, expected returns, and live as-of plans. All new state is **append-only SQLite rows with `input_snapshot_sha256`**; heavy matrices (covariance, weights) are managed immutable artifacts under `data/research_artifacts/`; every optimization/rebalance suggestion stays research-only.

**Major components:**
1. `research/signal_chain.py` (NEW) — single factor-value implementation; anti train/serve skew; one compile→evaluate→score path
2. `research/admission.py` + `research/models.py` (NEW) — admission gate pipeline (append-only verdicts) + multi-factor composite models
3. `portfolio/{optimizer,risk,rebalance,repository,schemas}.py` (NEW) — immutable optimization runs, risk models + PSD-repair provenance, A-share RebalancePlans, strict DTOs
4. `backtest/walkforward.py` + `backtest/ensemble.py` (NEW) — rolling folds + reserved OOS; `backtest/optimizer.py` gains OOS reservation
5. `api/optimization.py` (NEW) + `api/research.py`/`api/backtest.py` (MODIFY) — thin typed projection + walk-forward SSE (durable job pattern)
6. Modified: `research/{factor_registry,evaluation,catalog,repository}.py`, `portfolio/service.py`, `operational/migrations.py`, `services/quote_service.py`, frontend `api.ts`/`queryKeys.ts` + panels (ModelLibrary, WalkForward, Optimization, RiskAttribution, RebalancePlan)

Build order (architecture "Waves 0–6"): contracts/migrations/scipy-promote → signal_chain + evaluation refactor → admission gates + models + catalog → portfolio risk + optimizer + repository → rebalance + paper boundary → walk-forward/OOS/ensemble (can overlap 3–4) → API/SSE + frontend.

### Critical Pitfalls

1. **Lookahead / label leakage in the DSL** (Phase 10) — new multi-factor operators can silently acquire full-panel semantics. Guard: every operator declares partition context (per-date/per-symbol/pointwise) in the compiler; label fields denied in the allowlist; deterministic shifted-label test (IC must collapse when the label shifts) as the gate.
2. **Survivorship bias / no point-in-time universe** (Phase 10 + 13) — today's universe used for all history inflates IC and returns. Guard: persist PIT universe snapshots (validity ranges, delisted markers, membership as-of); resolve universe per evaluation date and per walk-forward fold; record resolved universe in every manifest.
3. **IC robustness overfitting & silent PSD repair** (Phases 10 + 12) — scalar mean-IC hides a few hot months; unrecorded eigen-clips make stated risk wrong. Guard: full monthly evidence set + fixed policy thresholds + candidate trail (incl. rejections); PSD repair is an explicit recorded step (method, epsilon, eigenvalues before/after) in the immutable run.
4. **Walk-forward leakage & multiple-comparison bias** (Phase 13) — expanding/overlapping folds and best-of-N search inflate OOS. Guard: rolling windows with explicit gap (`WF_GAP`), disjoint recorded folds, reserved final OOS evaluated exactly once; record trial count, search space, score distribution.
5. **Max-Sharpe default & continuous weights as orders** (Phases 11 + 14) — unstable objective + infeasible plans. Guard: min-vol + HRP as defaults, max-Sharpe explicit opt-in with baselines rendered; RebalancePlan has strict layering (continuous weights immutable → discrete lots with RMSE + cash + blocked + expiry) and no execution route.
6. **Execution-authority leak** (Phase 14, integration) — RebalancePlan wired to existing portfolio-mutation endpoints. Guard: plan is a research-only artifact; paper rebalance is a separate approved state machine (PA_Agent ApprovalTicket pattern); UI never offers "execute"; audit every plan→paper transition append-only.
7. **Train/serve skew & divergent cross-module computation** (integration) — separate backtest/live implementations silently diverge. Guard: one shared signal chain; reconciliation checks (risk attribution sums to portfolio variance; library IC == optimizer scores).

## Implications for Roadmap

Based on combined research, suggested phase structure (continuing v1.1's numbering; Phase 10 = first v1.2 phase). Phases 10–14 follow the pitfall-research mapping; Phase 15 carries the Wave 6 API/SSE + frontend integration.

### Phase 10: Factor Library & Multi-Factor Model (foundations + backbone)
**Rationale:** Everything downstream depends on the signal chain and the append-only contract; admission gates MUST precede portfolio construction (unvalidated factors poison expected returns). The catalog extension should land with the first new module so later phases inherit it.
**Delivers:** migrations for `portfolio_*`/`factor_model_*`/`admission_*` tables; `portfolio/schemas.py`; scipy promoted to base; `research/signal_chain.py`; evaluation refactor (ICIR/monthly robustness/coverage); `admission.py` gates; `models.py` multi-factor composition; catalog summaries; PIT universe snapshot contract + manifest extension.
**Addresses:** admission gates, ICIR/robustness/coverage, admitted catalog, composite expected returns, shared signal chain (all P1).
**Avoids:** Pitfalls 1 (leakage test), 2 (PIT universe), 3 (fixed thresholds + candidate trail), 11/12 (boundary + auditability from first module).
**Uses:** scipy 1.17.1, sklearn 1.8.0 (lazy Ledoit-Wolf later), existing DSL unchanged.

### Phase 11: Portfolio Construction & Optimization
**Rationale:** Sample covariance + PSD check must exist before the optimizer consumes it; immutable run records are the audit contract for every later phase.
**Delivers:** `portfolio/risk.py` (sample covariance + PSD check/repair), `portfolio/optimizer.py` (min-vol + HRP baselines; long-only, per-instrument cap, min cash, turnover constraint stack), `portfolio/repository.py` (immutable runs with `input_snapshot_sha256`), `api/optimization.py` (run creation).
**Addresses:** sample covariance + PSD, min-vol optimizer, HRP baseline, immutable run records (P1).
**Avoids:** Pitfall 5 (max-Sharpe not default; baselines rendered), Pitfall 4 (PSD repair recorded — begins here, completes in Phase 12), Pitfall 11 (run audit fields).
**Uses:** cvxpy 1.9.2 (or scipy SLSQP if the constraint set stays minimal — **decision flag**, see Gaps), scipy linkage for HRP.
**Research flag:** **needs planning research** — cvxpy vs scipy.optimize engine choice must be resolved; stack research recommends cvxpy 1.9.2 as primary, architecture research cautions scipy-only unless a true QP is required and notes the package-legitimacy approval gate.

### Phase 12: Risk Models & Attribution
**Rationale:** Feeds optimization (recorded risk model) and produces attribution; reconciliation checks (attribution sums to portfolio variance) are the cross-module integrity guard.
**Delivers:** full risk-model suite (sample/semi/exponential/Ledoit-Wolf) + explicit PSD-repair provenance (method/epsilon/eigenvalues) in the run record; exposure + marginal contribution attribution; drawdown attribution (add-after trigger).
**Addresses:** Ledoit-Wolf/semi/exponential + PSD options (P2), risk exposure + contribution (P1), drawdown (P2).
**Avoids:** Pitfall 4 (recorded PSD repair, never silent), Pitfall 13 (reconciliation checks).
**Research flag:** standard patterns (PyPortfolioOpt `risk_models` contracts) — skip research-phase.

### Phase 13: Walk-Forward Validation & Parameter Search
**Rationale:** Depends only on Phase 10 + 11 (signal chain + optimizer); OOS reservation must be defined before any existing grid search is reused. Can overlap Phases 11–12 for throughput.
**Delivers:** `backtest/walkforward.py` (rolling folds + explicit gap + reserved final OOS evaluated exactly once), `backtest/optimizer.py` OOS reservation, `backtest/ensemble.py` (rank-average of validated strategies), search bookkeeping (trial count, space, score distribution).
**Addresses:** rolling walk-forward + reserved OOS (P1), parameter optimization on OOS folds (P2), ensembling (P2).
**Avoids:** Pitfall 8 (rolling not expanding, disjoint folds, reserved OOS), Pitfall 9 (multiple-comparison bookkeeping), Pitfall 2 (per-fold PIT universe resolution).
**Research flag:** **medium** — fold design (train/test size, `WF_GAP` value) against A-share history length; AlphaMaster's `WF_GAP=20` is a documented starting point.

### Phase 14: Output & Boundary — RebalancePlan + Paper Rebalance
**Rationale:** The milestone's raison d'être: continuous weights → A-share reality as a research-only suggestion with zero execution authority. Reuses the existing A-share matching layer — the plan path must NOT build a naive second matcher.
**Delivers:** `portfolio/rebalance.py` (100-share lots, odd-lot sell handling, cash residue, turnover/cost, `blocked_instruments`, `expires_at`, discretization RMSE), paper-rebalance state machine (append-only audit fact, human approval, idempotency), no execution route anywhere.
**Addresses:** RebalancePlan + A-share lots, paper suggestion no-execution (P1).
**Avoids:** Pitfall 6 (A-share microstructure reuses matching layer), Pitfall 10 (lot-sizing adapter, RMSE visible), Pitfall 14 (execution-authority leak — hard acceptance criterion).
**Research flag:** standard patterns — existing `backtest/engine.py` already proves the A-share rules (T+1, limits, suspension, lots, fees); skip research-phase.

### Phase 15: API/SSE + Frontend Panels
**Rationale:** Thin typed projection over server-owned state; wiring last so contracts (immutable runs, plans) are stable before UI.
**Delivers:** walk-forward SSE (durable job pattern), `quote_service` `notify_portfolio_run_updated`, frontend `ModelLibrary` + `WalkForward` panels in Backtest workspace; `Optimization`/`RiskAttribution`/`RebalancePlan` panels in Portfolio workspace.
**Addresses:** all P1 features' user-facing surfaces.
**Avoids:** UX pitfalls — never label RankIC as generic IC, never present optimizer output as "optimal" without baselines, never offer an "execute" affordance on plans, label selection-validation vs reserved OOS honestly.
**Research flag:** standard patterns — existing typed `api.ts`/`queryKeys.ts`/SSE hooks; skip research-phase.

### Phase Ordering Rationale
- **Strict dependency chain:** admission gates → admitted catalog → composite returns + covariance → optimization → RebalancePlan → paper suggestion; walk-forward feeds parameter search and ensembling. This is the single most important ordering constraint (FEATURES dependency graph).
- **Shared signal chain first:** evaluation, models, expected returns, walk-forward, and live plans all consume it; a second implementation is a bug, not a feature.
- **Risk precedes/wraps optimization:** recorded PSD repair and reconciliation are prerequisites for trusting optimizer output; Phases 11–12 are tightly coupled and can merge if the milestone wants fewer phases.
- **Phase 13 can run parallel to 11–12** (depends only on the chain + admission), but its OOS reservation must be pinned before any parameter search is reused.
- **Phase 14 is the boundary phase** — no execution authority is a hard acceptance criterion, not a nicety.
- **Phase 15 last:** server-owned state and strict DTOs stabilize before frontend wiring.

### Research Flags

Phases likely needing deeper research during planning (`/gsd-plan-phase --research-phase`):
- **Phase 11:** optimizer engine — cvxpy 1.9.2 vs scipy SLSQP; stack research and architecture research diverge. Resolve before planning; constraint stack (caps/min-cash/turnover) is the deciding factor; cvxpy addition must pass the package-legitimacy approval gate.
- **Phase 10 (data sub-item):** point-in-time universe snapshot design — how to persist validity ranges/delisted markers/membership-as-of in the existing governed lake without a second datastore. Largest open data question.
- **Phase 13:** walk-forward fold geometry (train/test size, gap) calibrated to available A-share history.

Phases with standard patterns (skip research-phase):
- **Phase 12:** risk models + PSD repair — PyPortfolioOpt `risk_models` contracts are well documented.
- **Phase 14:** A-share lot rules — already proven in `backtest/engine.py`; reuse, don't research.
- **Phase 15:** frontend/SSE — existing typed client + SSE hook conventions.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | PyPI metadata verified 2026-07-31 + `backend/uv.lock` cross-check; cvxpy is a genuine lockfile addition (not yet installed — .venv empty) |
| Features | HIGH | Grounded in local knowledge-base DEEP-ANALYSIS docs + v1.0 shipped code; clear P1/P2/P3 triage with MVP definition |
| Architecture | HIGH | Code-verified against shipped v1.0/v1.1 host; wave build order derived from dependency analysis; component inventory explicit |
| Pitfalls | HIGH | 14 critical pitfalls + technical-debt/security/UX tables + pitfall-to-phase mapping; mitigations from reference projects |

**Overall confidence:** HIGH

### Gaps to Address

- **cvxpy vs scipy.optimize engine decision:** stack research recommends cvxpy 1.9.2 as the primary optimization dep; architecture research recommends scipy-only "unless a true QP is required" and flags a package-legitimacy approval gate. Resolve at Phase 11 planning. The constraint stack (per-instrument/industry caps, min cash, turnover) is convex-QP territory where scipy SLSQP degrades; a leaner alternative is cvxpy for the QP + scipy only for HRP.
- **Point-in-time universe snapshots (survivorship bias):** the governed lake stores the current instrument snapshot with no per-date universe table; the milestone's data-layer work for PIT snapshots is unplanned. Highest-impact data gap — flag during Phase 10 planning; without it, Phases 11–13 silently inherit the bias.
- **Industry mapping:** sector JOIN is fail-closed ("sector JOIN 未实现"); industry cap must be deferred until a governed industry mapping column exists. Do NOT ship a cap on ungoverned ext_data.
- **Runtime install verification deferred:** local `.venv` exists but is empty (no installed packages); cvxpy/scipy/sklearn install must be verified in Phase 10, not assumed.
- **HRP dependency:** HRP requires scipy linkage — scipy must be promoted to base deps in Phase 10 or HRP falls to P2 and min-vol ships alone.
- **Merge option:** Phases 11 and 12 are tightly coupled (PSD provenance feeds the optimizer); the roadmapper may merge them into a single "Portfolio Construction & Risk" phase.

## Sources

### Primary (HIGH confidence)
- **Stack:** PyPI metadata for cvxpy/pyportfolioopt/riskfolio/skfolio/lark/pyparsing/scipy/numpy (fetched 2026-07-31); `backend/uv.lock` + `backend/pyproject.toml` locked versions; CVXPY install/changes docs; SciPy 1.17.0 release notes; PyPortfolioOpt/AlphaAgent/qlib/AlphaMaster DEEP-ANALYSIS (knowledge base); AthenaQuant v1.0 phase-2 research; verified repo seams (`factor_dsl.py`, `evaluation.py`, `engine.py`, `frozen_panel.py`, `migrations.py`)
- **Features:** AlphaAgent/PyPortfolioOpt/Qlib/AlphaMaster/Lean/PA_Agent/tickflow-stock-panel DEEP-ANALYSIS docs; `07-策略与信号系统篇.md`, `10-SYNTHESIS.md`, Alpha Evolution Lab QUICK-START, joinquant-skill QUICK-START; AthenaQuant shipped code (`factor_dsl.py`, `evaluation.py`, `factor_registry.py`, `catalog.py`, `frozen_panel.py`, `engine.py`, `optimizer.py`, `portfolio/service.py`, `shadow/`); `.planning/PROJECT.md`
- **Architecture:** AthenaQuant codebase verification (`app/research/*`, `app/portfolio/*`, `app/backtest/*`, `app/api/*`, `services/quote_service.py`, `frontend/src/*`); `docs/ARCHITECTURE.md`, `.planning/codebase/ARCHITECTURE.md`; `.planning/PROJECT.md`; qlib/alphaagent/pyportfolioopt/alphamaster/lean DEEP-ANALYSIS docs
- **Pitfalls:** AlphaAgent/AlphaMaster/PyPortfolioOpt/Qlib DEEP-ANALYSIS docs; `10-SYNTHESIS.md`, `07-策略与信号系统篇.md`; AthenaQuant v1.0 phase artifacts (`02-RESEARCH.md`, `02-CONTEXT.md`, `02-VERIFICATION.md`, `02-UI-SPEC.md`); `docs/ARCHITECTURE.md`; `.planning/PROJECT.md`

### Secondary (MEDIUM confidence)
- `15-数据底座与采集底座篇.md` — Parquet/DuckDB/Polars data-base layer (architecture MEDIUM)
- Alpha Evolution Lab QUICK-START + joinquant-skill QUICK-START — promotion-gate and AST-lint patterns (features MEDIUM)

### Tertiary (LOW confidence)
- None — all four research files are code-verified and knowledge-base-grounded; remaining uncertainty is captured in Gaps to Address rather than source quality.

---
*Research completed: 2026-07-31*
*Ready for roadmap: yes*
