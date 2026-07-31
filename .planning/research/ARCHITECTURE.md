# Architecture Research

**Domain:** A-share quantitative factor portfolio pipeline (v1.2 end-to-end factor → portfolio → risk → rebalance-suggestion)
**Researched:** 2026-07-31
**Confidence:** HIGH (code-verified against the shipped v1.0/v1.1 host; reference contracts from the local knowledge base)

## Executive Summary (for roadmappers)

The v1.2 milestone extends an existing, shipped architecture — it does not introduce a second engine. The decisive finding is that **most of the factor-domain scaffolding already exists**: `app/research/factor_dsl.py` is a working restricted DSL with whitelist parsing (no `eval`, allowlisted fields/operators/functions, canonical serialization, AST signatures), `app/research/evaluation.py` already produces IC/RankIC/group/long-short evidence with SHA-256 governed-input manifests, `app/research/factor_registry.py` already implements immutable factor revisions with similarity dedup, and `app/research/catalog.py` already persists immutable experiment snapshots. The **genuinely new backend surface is the portfolio domain** (`optimization runs`, `risk models`, `RebalancePlan`) plus **admission gates**, **multi-factor model composition**, **rolling walk-forward**, and a **shared signal chain**.

The single most important architectural seam is the **shared factor signal chain**: one implementation that computes cross-sectional factor values from the compiled DSL over governed panels, used identically by factor evaluation, multi-factor scoring, walk-forward folds, expected-return estimation, and live as-of rebalance suggestions. Everything else hangs off that chain, and the entire milestone's credibility rests on not creating a second, "live-only" factor implementation (train/serve skew — AlphaMaster lesson).

All new state must follow the established pattern: **append-only SQLite rows with input-snapshot SHA-256 hashes**, governed panels read only through `BacktestEngine.load_panel`, heavy matrices (covariance, weights) as managed immutable artifacts under `data/research_artifacts/`, and every optimization/rebalance suggestion staying **research-only with zero execution authority**.

---

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                        Frontend (React SPA)                                  │
│  Backtest workspace (ResearchLibrary, FactorBacktest, StrategyOptimizer,     │
│    NEW: ModelLibrary, WalkForward)  ·  Portfolio workspace                   │
│    (NEW: Optimization, RiskAttribution, RebalancePlan panels)                │
│  lib/api.ts (typed) · lib/queryKeys.ts · SSE via existing stream hooks       │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │  HTTP (JSON, strict Pydantic) / SSE (progress)
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      FastAPI Host  (app/main.py lifespan)                    │
│  auth middleware · capability gating · router registration                   │
├───────────────────────┬───────────────────────┬──────────────────────────────┤
│  app/api/research.py  │  app/api/portfolio*.py│  app/api/backtest.py         │
│  (extend)             │  (NEW optimization /  │  (extend: walk-forward SSE)  │
│                       │   risk / rebalance)   │                              │
├───────────────────────┴───────────────────────┴──────────────────────────────┤
│                          Service layer                                       │
│  research/            portfolio/              backtest/                      │
│   factor_dsl (REUSE)   optimizer.py (NEW)      engine (REUSE)                │
│   evaluation (MOD)     risk.py (NEW)           frozen_panel (REUSE)          │
│   factor_registry(MOD) rebalance.py (NEW)      strategy (REUSE)              │
│   catalog (MOD)        repository.py (NEW)     walkforward.py (NEW)          │
│   admission.py (NEW)   schemas.py (NEW)        ensemble.py (NEW)             │
│   signal_chain.py(NEW) service.py (MOD)        optimizer (MOD: OOS reserve)  │
│   models.py (NEW)                                                        │
├──────────────────────────────────────────────────────────────────────────────┤
│                         Data layer                                           │
│  Parquet lake (kline_daily_enriched, financials, ext_data industry/concept)  │
│  DuckDB views · Polars hot cache  →  BacktestEngine.load_panel (ONLY seam)   │
│  SQLite operational.db (positions, accounts, preferences, decision,          │
│    research_*, advanced_*, NEW: portfolio_*, factor_model_*, admission_*)    │
│  data/research_artifacts/  (immutable JSON/Parquet evidence bundles)         │
└──────────────────────────────────────────────────────────────────────────────┘
```

Key structural decisions:

- **One engine, one panel seam.** Factor evaluation, multi-factor scoring, walk-forward, expected returns, and risk attribution all read governed market data exclusively through `BacktestEngine.load_panel()` (`app/backtest/engine.py:191`) — the same call the shipped Phase 2 evaluation already uses. No new data-loading path, no copying raw market rows into SQLite. [VERIFIED: codebase]
- **The signal chain is the backbone.** A new `app/research/signal_chain.py` centralizes "factor revision(s) → governed panel → cross-sectional factor values/rank/zscore". It is called by every consumer; there is exactly one implementation. [INFERENCE from AlphaMaster DEEP-ANALYSIS §8.1]
- **Portfolio state is immutable and hash-bound.** Each optimization run and rebalance plan freezes a canonical `PortfolioInputSnapshot` (universe, data version, positions/cash, constraints, expected-return & risk method, solver) and stores `input_snapshot_sha256` alongside append-only weights/metrics — mirroring the shipped `research_experiments` + `advanced_*` insert-only pattern. [VERIFIED: codebase; contract from PyPortfolioOpt DEEP-ANALYSIS §6]
- **No execution authority.** RebalancePlan is a research suggestion: discrete A-share lots, blocked instruments, expiry, and an auditable "paper rebalance" record. Nothing in the pipeline can place an order. [Locked by PROJECT.md Out of Scope]

---

## Component Responsibilities

| Component | Responsibility | Status | Key Contract |
|-----------|----------------|--------|--------------|
| `research/factor_dsl.py` | Restricted factor expression language: tokenizer, AST, whitelist validation, canonical serialize, `parse_factor`/`compile_factor` → `pl.Expr` | **REUSE unchanged** | `DSL_VERSION="factor-dsl-v1"`, `ALLOWED_FIELDS`, arity-checked operator/function table [VERIFIED] |
| `research/factor_registry.py` | Immutable factor definitions + revisions, deterministic similarity ranking (AST-signature + Jaccard on fields/operators/functions) | **MODIFY**: add admission status/summary reference | `FactorRevision`, `SimilarityCandidate` [VERIFIED] |
| `research/evaluation.py` | Governed single-factor evaluation: IC, RankIC, group stats, long-short, governed-input manifest, artifact bundle | **MODIFY**: add ICIR exposure, monthly robustness, coverage; refactor value computation to call `signal_chain` | `FactorEvaluationResult`, `ResolvedEvaluationConfig`, `MetricSummary` (already has information_ratio) [VERIFIED] |
| `research/admission.py` | **NEW** — admission gate pipeline: parse/eval-ok, coverage threshold, train-IC & val-IC thresholds, no-lookahead, no-label-leakage, monthly robustness, similarity dedup against catalog | NEW | Gate verdicts are append-only facts; a factor is "admitted" only after every gate passes on separate train/val windows |
| `research/models.py` | **NEW** — multi-factor composite model: admitted factor revisions + weights + standardization method; `score(panel)` via signal chain → composite cross-sectional score; immutable model revisions | NEW | `FactorModel` / `FactorModelRevision` rows; used by expected-return estimator and walk-forward |
| `research/catalog.py` | Immutable experiment snapshots + comparison | **MODIFY**: store per-factor summary rows (latest admitted evaluation summary) and multi-factor model snapshots | `ExperimentSnapshot`, `ExperimentComparison` [VERIFIED] |
| `research/signal_chain.py` | **NEW** — THE shared backtest/live signal chain: `compute_factor_values(revision_ids, panel)` and `composite_score(model, panel)`; one standardization path (cross-sectional rank or zscore), fixed warmup, closed-bar as-of semantics | NEW | Same output shape for evaluation, backtest, live as-of |
| `research/repository.py` | SQLite access for research tables | **MODIFY**: add `factor_models`, `factor_admission_gates`, `factor_summaries` tables | Shares `operational.db`, `migrate_operational_db` [VERIFIED] |
| `backtest/engine.py` | Governed panel loading, matching, metrics | **REUSE unchanged** | `load_panel(symbols, start, end, columns, asset_type)` [VERIFIED] |
| `backtest/frozen_panel.py` | SHA-256 checksum-verified governed panels for spawned workers | **REUSE unchanged** | `FrozenPanelArtifactStore.create/load` [VERIFIED] |
| `backtest/strategy.py` | Registered-strategy backtest with `governed_input_manifest` | **REUSE unchanged** | `StrategyBacktestService` [VERIFIED] |
| `backtest/walkforward.py` | **NEW** — rolling walk-forward validation: fixed-size train folds, forward test fold, reserved independent OOS segment never touched by search; consumes signal chain + strategy/portfolio backtest | NEW | Rolling NOT expanding; `WF_GAP`; OOS reservation (AlphaMaster §4.2, Qlib §7) |
| `backtest/ensemble.py` | **NEW** — ensemble of admitted models/parameter sets by ranked-score or weight averaging with recorded membership | NEW | Every ensemble persists component identities + combination rule |
| `backtest/optimizer.py` | Parameter grid search (exists) | **MODIFY**: add OOS reservation so search never sees the reserved segment; keep `GRID_MAX_COMBINATIONS` cap | `StrategyOptimizer` [VERIFIED] |
| `portfolio/optimizer.py` | **NEW** — constraint-layered portfolio optimizer: expected returns + covariance + constraint stack + objective (min-vol / HRP baselines; max-Sharpe opt-in only) | NEW | `PortfolioOptimizationRun` immutable record; long-only, per-instrument cap, industry cap, min cash, turnover cost |
| `portfolio/risk.py` | **NEW** — risk models (sample / semi / exponential / Ledoit-Wolf) + PSD repair (spectral/diagonal fallback); exposure, marginal contribution, drawdown attribution | NEW | Pure functions over run weights + governed returns; PSD repair method recorded |
| `portfolio/rebalance.py` | **NEW** — continuous weights → A-share RebalancePlan: 100-share lots, sell odd-lot handling, cash, turnover/cost, blocked instruments (ST / suspension / limit-up-down), expiry | NEW | `RebalancePlan`; plan is research-only suggestion; paper rebalance record |
| `portfolio/repository.py` | **NEW** — SQLite repository for immutable portfolio runs, plans, risk attributions | NEW | Insert-only rows + UPDATE/DELETE triggers, `input_snapshot_sha256` |
| `portfolio/schemas.py` | **NEW** — strict Pydantic request/DTO contracts (`extra="forbid"`) | NEW | `PortfolioInputSnapshot`, `OptimizationRunDto`, `RebalancePlanDto`, `RiskAttributionDto` |
| `portfolio/service.py` | Existing valuation service | **MODIFY**: gain run orchestration entry points | `PortfolioService` [VERIFIED] |
| `api/research.py` | Factor/research API | **MODIFY**: add admission, model, summary endpoints | Existing strict model pattern [VERIFIED] |
| `api/portfolio.py` + NEW `api/optimization.py` | Portfolio CRUD (exists) + **NEW** optimization/risk/rebalance API | MODIFY + NEW | Typed server-owned DTOs |
| `api/backtest.py` | Backtest + optimizer SSE (exists) | **MODIFY**: add walk-forward SSE using durable job pattern | `_BacktestJob` / `_running_jobs` in-memory today → recommend durable rows for runs [VERIFIED] |
| `operational/migrations.py` | Versioned SQLite migrations | **MODIFY**: append new table migrations | `MIGRATIONS` tuple, `migrate_operational_db` [VERIFIED] |
| `services/quote_service.py` | Shared SSE fan-out | **MODIFY**: add `notify_portfolio_run_updated` / coarse invalidation | `QuoteSubscriber.notify_*` [VERIFIED] |
| Frontend `pages/Backtest.tsx`, `pages/Portfolio.tsx` | Workspaces | **MODIFY**: add model library, walk-forward, optimization, risk, rebalance panels | Existing typed `api.ts` + `queryKeys.ts` + SSE hooks |

---

## Recommended Project Structure (new/changed files)

```text
backend/app/
├── research/
│   ├── factor_dsl.py          # REUSE (unchanged)
│   ├── factor_registry.py     # MODIFY: admission status on revisions
│   ├── evaluation.py          # MODIFY: ICIR/monthly-robustness/coverage; call signal_chain
│   ├── admission.py           # NEW: gate pipeline + gate verdict facts
│   ├── models.py              # NEW: multi-factor composite model + revisions
│   ├── signal_chain.py        # NEW: single backtest/live factor-value chain
│   ├── catalog.py             # MODIFY: factor summaries + model snapshots
│   ├── repository.py          # MODIFY: new tables
│   └── artifacts.py           # REUSE (unchanged)
├── portfolio/
│   ├── optimizer.py           # NEW
│   ├── risk.py                # NEW
│   ├── rebalance.py           # NEW
│   ├── repository.py          # NEW
│   ├── schemas.py             # NEW
│   └── service.py             # MODIFY
├── backtest/
│   ├── walkforward.py         # NEW
│   ├── ensemble.py            # NEW
│   └── optimizer.py           # MODIFY: OOS reservation
├── api/
│   ├── research.py            # MODIFY
│   ├── optimization.py        # NEW (portfolio runs/risk/rebalance)
│   └── backtest.py            # MODIFY (walk-forward SSE)
├── operational/migrations.py  # MODIFY
└── services/quote_service.py  # MODIFY

backend/tests/
├── research/test_admission.py   # NEW
├── research/test_models.py      # NEW
├── research/test_signal_chain.py# NEW
├── portfolio/test_optimizer.py  # NEW
├── portfolio/test_risk.py       # NEW
├── portfolio/test_rebalance.py  # NEW
├── portfolio/test_repository.py # NEW
├── backtest/test_walkforward.py # NEW
└── (existing suites extended)

frontend/src/
├── lib/api.ts                   # MODIFY
├── lib/queryKeys.ts             # MODIFY
├── pages/backtest/ModelLibrary.tsx        # NEW
├── pages/backtest/WalkForward.tsx         # NEW
├── pages/Portfolio.tsx                     # MODIFY
└── components/portfolio/OptimizationPanel.tsx   # NEW
    components/portfolio/RiskAttributionPanel.tsx# NEW
    components/portfolio/RebalancePlanPanel.tsx  # NEW
```

### Structure Rationale

- **Research owns the factor language and its lifecycle end-to-end.** The DSL, registry, evaluation, admission, and models all live under `app/research/` because they share one domain boundary (factor definitions → evaluated evidence → admitted reusable factors). `signal_chain.py` lives here too — it is the factor-expression→values compiler path and is imported by portfolio/backtest, not the reverse.
- **Portfolio is a new, independent domain, not an extension of the operational portfolio monitor.** The existing `app/portfolio/service.py` is a *valuation* service (positions + quotes). The v1.2 optimization/risk/rebalance machinery is research-construction, so it gets its own `optimizer.py`/`risk.py`/`rebalance.py`/`repository.py`/`schemas.py` while `service.py` only gains orchestration entry points. This respects PROJECT.md's "independent modules" constraint.
- **Backtest stays the only execution/panel authority.** `walkforward.py` and `ensemble.py` are placed under `app/backtest/` because they drive governed-panel backtests and reuse `BacktestEngine` + `FrozenPanelArtifactStore`. They depend on `research.signal_chain` for factor values, never re-deriving them.
- **API is a thin typed projection layer.** No business logic in routers; every endpoint resolves server-owned state and returns strict DTOs, matching the shipped research/advanced API convention. [VERIFIED]

---

## Architectural Patterns

### Pattern 1: The Shared Signal Chain (anti train/serve skew)

**What:** One module, `app/research/signal_chain.py`, owns the entire "factor revisions → governed panel → cross-sectional values" path. Consumers pass a list of factor revisions (or a model) plus a governed panel; the chain compiles each expression via `factor_dsl.compile_factor`, computes values with identical warmup/window semantics, and standardizes cross-sectionally (rank or zscore) with an explicit method string. The chain never looks at future labels — `_forward_return` exists only in the evaluation layer.

**Why:** Factor evaluation (research), multi-factor scoring (models), walk-forward (backtest), expected returns (portfolio), and live as-of rebalance suggestions all need the *same* numbers. AlphaMaster's strongest engineering lesson is that separate backtest/live factor implementations are the #1 source of silent strategy degradation (DEEP-ANALYSIS §8.1, §6). Qlib's `SignalRecord` → `SigAnaRecord` also assumes one signal artifact feeds both IC analysis and backtest (DEEP-ANALYSIS §5).

**When to use:** Every factor-value computation in the milestone. Backtest folds and live suggestions call the same function with the same revision IDs; the only difference is the panel window and the `as_of` closed-bar bound.

**Example:**
```python
# app/research/signal_chain.py
class FactorSignalChain:
    """One implementation of factor values shared by every consumer."""
    def __init__(self, engine: BacktestEngine, registry: FactorRegistry):
        self._engine = engine
        self._registry = registry

    def factor_values(self, revision_ids: list[str], symbols, start, end,
                      asset_type: str = "stock") -> pl.DataFrame:
        # 1. resolve revisions (server-owned), 2. compile DSL -> pl.Expr,
        # 3. load ONE governed panel via BacktestEngine.load_panel,
        # 4. return long-format [symbol, date, factor_<rev_id>] with warmup excluded.
        ...

    def composite_score(self, model, panel) -> pl.DataFrame:
        # cross-sectional rank/zscore per factor (method stored on the model),
        # weighted combine -> [symbol, date, composite]
        ...
```

**Trade-offs:** Centralization is a contract — adding a factor variant means editing the chain, not forking it. Cost: the chain must expose an explicit `as_of`/warmup API so evaluation and live don't silently disagree.

### Pattern 2: Immutable, Hash-Bound Portfolio Run Records

**What:** Before any optimization, build a canonical `PortfolioInputSnapshot` (assets, eligible universe, prices/returns data version + observed date range, current positions/cash, constraint stack, expected-return method, risk model + parameters, solver). Serialize to canonical JSON → `sha256` → store with the run. The run row is insert-only: objective, weights JSON, summary metrics, status/error, solver/options, input-snapshot hash, artifacts. `UPDATE`/`DELETE` are blocked by triggers (the shipped immutable-record convention, e.g. analysis triggers and `advanced_*` insert-only).

**Why:** PyPortfolioOpt's design boundary is exactly this: `PortfolioInputSnapshot → PortfolioOptimizationRun → RebalancePlan`, with each optimizer instance freezing its inputs (DEEP-ANALYSIS §1, §6). Qlib's Recorder contract stores params/artifacts per run (DEEP-ANALYSIS §4). The shipped `research_experiments` already stores `resolved_config_json`, `input_manifest_json` with schema+source fingerprints [VERIFIED].

**When to use:** Every optimization run and every rebalance plan.

**Example (schema sketch):**
```sql
CREATE TABLE portfolio_optimization_runs (
    id TEXT PRIMARY KEY,
    input_snapshot_sha256 TEXT NOT NULL,
    input_snapshot_json TEXT NOT NULL,      -- canonical PortfolioInputSnapshot
    objective TEXT NOT NULL,                 -- 'min_volatility' | 'hrp' | 'max_sharpe'(opt-in)
    expected_return_method TEXT NOT NULL,    -- e.g. 'factor_model_v1'
    risk_model TEXT NOT NULL,                -- 'sample'|'semi'|'exponential'|'ledoit_wolf'
    psd_repair TEXT,                         -- null | 'spectral' | 'diagonal'
    solver TEXT,                             -- e.g. 'scipy.slsqp' | 'hrp_clustering'
    weights_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    status TEXT NOT NULL,                    -- 'completed' | 'failed' | 'invalid'
    error TEXT,
    created_at TEXT NOT NULL
);
```

### Pattern 3: Admission-Gated Factor Lifecycle

**What:** A factor revision is promoted to "admitted" only by passing an ordered gate pipeline, each gate recorded as an append-only fact:

1. **parse/eval gate** — DSL parses and evaluates without error (already enforced by evaluation).
2. **coverage gate** — finite observations / universe coverage ≥ threshold over the train window.
3. **train IC / RankIC gate** — IC/RankIC and ICIR above floor on the train window only.
4. **val IC / RankIC gate** — independent validation window, no reuse of train.
5. **no-lookahead / no-label-leakage gate** — factor columns ⊆ `ALLOWED_FIELDS` (already structural), warmup excluded, no `_forward_return` in the chain path; verified by construction + a deterministic check.
6. **monthly robustness gate** — positive-rate/IC stability across months (alphaagent `monthly_corr_robustness`, DEEP-ANALYSIS §4.2).
7. **similarity dedup gate** — AST-signature / field-operator Jaccard distance below threshold against already-admitted catalog factors (registry already computes this; DEEP-ANALYSIS §5).

**Why:** A factor with high IC on one window is noise. The train/val split, monthly robustness, and similarity dedup are exactly what the reference projects insist on (alphaagent §7.2 admission checklist; AlphaMaster §4.2 train/validation gap + factor-pool correlation penalty). The shipped code already computes most inputs — gates are a new *decision layer*, not new math.

**When to use:** Before a factor may enter the catalog summary or be composed into a multi-factor model. LLM-proposed expressions (hypotheses gateway) must pass gates before admission — the gateway stays a draft-only boundary.

### Pattern 4: Constraint-Layered Portfolio Optimizer (min-vol / HRP baselines)

**What:** `PortfolioOptimizer` separates inputs from the solver:

- **Expected returns** — derived from an admitted multi-factor model's composite score (via signal chain), not from raw price momentum. Method recorded on the run.
- **Covariance** — from `portfolio/risk.py`; PSD-checked and repaired (method recorded) before solving.
- **Constraint stack** — long-only `(0,1)`; per-instrument cap; industry cap (from `ext_data` industry tables); min cash; turnover cost. Each constraint is a named layer with bounds in the snapshot.
- **Objective** — **min-volatility and HRP are the shipped defaults**; max-Sharpe is explicit opt-in only. Rationale (PyPortfolioOpt DEEP-ANALYSIS §2): `max_sharpe()` does a variable substitution that makes additional objectives behave counter-intuitively.

**Why:** PyPortfolioOpt's core is that the optimizer *freezes* its objective+constraint set at construction (DEEP-ANALYSIS §1), and HRP avoids explicit covariance inversion — a robust comparison baseline, not a replacement (DEEP-ANALYSIS §4). The knowledge base explicitly warns that PSD repair makes the problem *solvable*, not *correct*: the run must record the repair and never present repaired output as data-quality clean (DEEP-ANALYSIS §3).

**When to use:** All portfolio construction. Keep the solver minimal: the base lockfile has `numpy` only; `scipy` currently arrives via the `shadow`/`vectorbt` extras, not base. Recommend **promoting `scipy` to base dependencies** (already in `uv.lock`, widely used) and implementing min-vol via `scipy.optimize` (SLSQP) + HRP via hierarchical clustering; avoid CVXPY in v1.2 unless a true QP is required — if added, it must pass the project's package-legitimacy approval gate (like the Phase 5 optional packages).

### Pattern 5: Risk Attribution as Pure Functions Over a Frozen Run

**What:** `portfolio/risk.py` computes, from a completed run's frozen weights + governed returns, three projections: (a) exposure per instrument/industry, (b) marginal contribution to risk (weight × covariance × weight-vector / portfolio variance), (c) drawdown attribution (which names drove drawdown over the window). All are deterministic pure functions; nothing is stored except the projection rows bound to the run id.

**Why:** Lean's layering mandates risk as *computable target mutation or quantification*, never prose (DEEP-ANALYSIS §3). Because the run is immutable, attribution is always reproducible from the snapshot hash + governed panel — no need to persist the full covariance (SQLite stores bounded identity + summary; heavy matrices go to artifacts). [INFERENCE from the milestone contract + Forecast's "SQLite stores bounded identity" precedent]

### Pattern 6: RebalancePlan as a Research-Only Suggestion

**What:** Continuous weights → `RebalancePlan`: target weight per instrument, **A-share discrete lots (100-share rounding)** with odd-lot sell handling, resulting cash, turnover + estimated cost, **blocked instruments** (ST / suspended / limit-up-down via existing enriched/depth signals), expiry timestamp. A "paper rebalance" action records an immutable audit fact (plan id, as-of, principal, rationale) and *nothing else*.

**Why:** This is the hard boundary of the milestone. PyPortfolioOpt's `DiscreteAllocation` is explicitly "a candidate, not an executable order" (DEEP-ANALYSIS §4), Lean's `ExecutionModel` only receives targets that passed risk + human approval (DEEP-ANALYSIS §1, §3), and QuantDinger's paper-only scopes are the precedent already absorbed. `ActionGuard approval paper_only` is the reference contract (PyPortfolioOpt §6).

**When to use:** Every plan output. No API in the milestone may mutate accounts/positions or reach an order gateway.

---

## Data Flow

### Flow 1: Factor admission

```text
researcher / LLM hypothesis
   └─ hypotheses gateway (draft only, unchanged)
       └─ create factor revision (factor_registry, immutable)
           └─ evaluate train window ─┐
           └─ evaluate val window ───┴─ signal_chain.factor_values() → evaluation
               └─ admission.gates(...) → append-only gate verdicts
                   ├─ PASS → factor_summaries row (admitted) → catalog
                   └─ FAIL → gate facts retained; not composed into models
```

### Flow 2: Multi-factor model composition

```text
admitted factors (from Flow 1)
   └─ POST /api/research/models {factor_revision_ids, weights, method, universe}
       └─ models.py validates all revisions are admitted + dedup-cleared
           └─ FactorModelRevision (immutable, insert-only)
               └─ evaluation: composite_score via signal_chain → IC/backtest evidence
```

### Flow 3: Optimization run

```text
POST /api/portfolio/optimization/runs {universe, as_of, constraints, methods, positions_ref}
   └─ portfolio.optimizer builds PortfolioInputSnapshot (canonical JSON)
       ├─ hash → input_snapshot_sha256
       ├─ expected_returns ← models.composite_score (signal chain)
       ├─ covariance ← risk.covariance (sample/semi/exp/Ledoit-Wolf + PSD repair)
       ├─ solve (min-vol / HRP baseline; max-Sharpe opt-in)
       └─ INSERT portfolio_optimization_runs (immutable) + artifact bundle
   └─ SSE: notify_portfolio_run_updated → Portfolio workspace refresh
```

### Flow 4: Risk attribution

```text
GET /api/portfolio/optimization/runs/{id}/risk
   └─ load frozen run + governed returns (via snapshot hash + panel)
       └─ risk.exposure / contribution / drawdown_attribution (pure functions)
           └─ return RiskAttributionDto (no persistence needed; optionally cached as artifact)
```

### Flow 5: Rolling walk-forward (not expanding) with reserved OOS

```text
POST /api/backtest/walkforward {model_id, symbols, train_size, test_size, gap, reserved_oos}
   └─ assert reserved_oos is disjoint from every fold and from any optimizer search
   └─ for each fold: signal_chain values → train on [t, t+K) → predict [t+K, t+K+G)
       └─ record fold metrics
   └─ final: one evaluation on reserved_oos ONLY (never trained on)
       └─ walkforward_run row (immutable) + SSE progress
```

### Flow 6: Live as-of rebalance suggestion

```text
GET /api/portfolio/plans/latest?as_of=closed_bar
   └─ signal_chain.composite_score(model, panel bounded to as_of)  ← same chain as backtest
       └─ optimizer run (reuses latest frozen snapshot) → weights
       └─ rebalance.to_plan(...) → 100-share lots, blocked instruments, cash, turnover, expiry
   └─ RebalancePlanDto (research-only)
       └─ POST /api/portfolio/plans/{id}/paper-rebalance → append-only audit fact (no execution)
```

---

## Scaling Considerations

| Concern | At v1.2 (personal A-share) | Notes |
|---------|----------------------------|-------|
| Optimization universe | Cap at ~200–500 instruments per run (top-N by composite / liquidity) | Full A-share ≈ 5,000 names → covariance 5000×5000 = 200 MB float64 and slow SLSQP. Enforce a `PORTFOLIO_MAX_SYMBOLS` guard mirroring `FACTOR_MAX_SYMBOLS=1000` [VERIFIED: api/backtest.py] |
| Backtest memory | Keep `_backtest_semaphore = Semaphore(2)` for spawned backtests | Server ~1.8 GB; walk-forward runs N folds → serialize folds or reuse frozen panels so only one panel is live [VERIFIED: api/backtest.py] |
| Factor value caching | Warm the chain with the existing `PanelCache` (LRU+TTL) | `BacktestEngine.load_panel` already caches; signal chain should reuse it, not add a second cache |
| SQLite volume | Run/plan/gate rows are small; weights stored as JSON text | Store only bounded identity + summary + weights; full covariance/returns → `data/research_artifacts/` |
| SSE fan-out | Coarse `portfolio_run_updated` invalidation for the workspace; per-run SSE only for walk-forward | Reuse `QuoteSubscriber`; keep the durable-job pattern for long runs so restart doesn't lose evidence |
| Solver cost | `scipy.optimize` SLSQP on ≤500 vars with linear constraints is fine (seconds) | If universe grows or QP is needed, add CVXPY behind approval gate |

**First bottleneck:** covariance estimation + solve on a large universe. Mitigate with the universe cap and by defaulting to HRP (no explicit inverse) for broad universes, min-vol for narrower ones.

---

## Anti-Patterns

### Anti-Pattern 1: A second, "live-only" factor implementation

**What people do:** compute factors one way in evaluation and another (e.g., re-implemented in the monitor or a live module) at as-of time.
**Why it's wrong:** Train/serve skew — silently different values in backtest vs live; the flagship AlphaMaster lesson (DEEP-ANALYSIS §6, §8.1).
**Do this instead:** Every consumer calls `research/signal_chain`. If a live path diverges, it is a bug, not a feature.

### Anti-Pattern 2: Expanding walk-forward (or reusing validation in training)

**What people do:** grow the train window each fold (expanding) so early validation windows reappear in later training; or let the parameter optimizer touch the final reserved OOS segment.
**Why it's wrong:** Reusing validation in training inflates OOS scores (AlphaMaster `WF_GAP`, DEEP-ANALYSIS §4.2). Expanding windows also leak early folds into later training.
**Do this instead:** Rolling fixed-size folds with an explicit gap, and a reserved independent OOS segment that is disjoint from every fold and every search. The optimizer gets a search split; the reserved OOS is scored exactly once.

### Anti-Pattern 3: Max-Sharpe as the default objective

**What people do:** make `max_sharpe()` the default "best portfolio".
**Why it's wrong:** The variable substitution in max-Sharpe makes additional objectives (caps, turnover) behave counter-intuitively (PyPortfolioOpt DEEP-ANALYSIS §2).
**Do this instead:** Ship min-vol and HRP as stable baselines; max-Sharpe is explicit opt-in with documented caveats.

### Anti-Pattern 4: Mutable run records (overwrite last weights)

**What people do:** keep a single "current portfolio weights" row and update it on each optimization.
**Why it's wrong:** Loses the audit trail; a re-run can silently replace a worse-but-different answer; breaks reproducibility.
**Do this instead:** Every optimization is a new insert-only `portfolio_optimization_runs` row bound to an input-snapshot hash. "Current plan" is a *projection* over the latest completed run, never a mutable table.

### Anti-Pattern 5: Treating PSD repair as data validation

**What people do:** run Ledoit-Wolf / spectral repair and assume the inputs are clean.
**Why it's wrong:** Repair only makes the problem solvable; it cannot fix lookahead, survivorship, or misaligned price data (PyPortfolioOpt DEEP-ANALYSIS §3).
**Do this instead:** Record the risk model + repair method + underlying data manifest on every run, and surface a warning when repair was required.

### Anti-Pattern 6: RebalancePlan reaching execution authority

**What people do:** let a "paper rebalance" or "apply plan" endpoint mutate positions/accounts.
**Why it's wrong:** Out-of-scope for the milestone and a fail-closed violation of PROJECT.md (no automated execution).
**Do this instead:** Plans are suggestions; the only side effect is an append-only paper-rebalance audit fact. Any future execution must be a separate milestone with explicit scope and approval gates.

### Anti-Pattern 7: Storing covariance/returns matrices in SQLite

**What people do:** dump `weights`, `covariance`, or full return matrices into rows.
**Why it's wrong:** SQLite is operational state; the repo deliberately stores bounded identity and lets Parquet hold the time series (data-lake-first principle).
**Do this instead:** Weights + summary metrics as JSON text (bounded), heavy matrices as managed artifacts under `data/research_artifacts/` with checksums, exactly like the shipped `EvaluationArtifactService` [VERIFIED].

---

## Integration Points

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `research.signal_chain ↔ backtest.engine` | direct call (`load_panel`) | The ONLY market-data read path; panels are governed enriched Parquet [VERIFIED] |
| `research.models ↔ portfolio.optimizer` | `composite_score()` → expected returns | Model revisions are immutable; optimizer snapshot records model id + revision |
| `portfolio.optimizer ↔ portfolio.risk` | covariance matrix + run weights | PSD repair method recorded on the run |
| `portfolio.rebalance ↔ operational.repository` | **read-only** current positions/cash | RebalancePlan may *read* positions for turnover/cash math but never writes them |
| `portfolio.rebalance ↔ tickflow/repository` + `strategy/engine` | blocked-instrument inputs | Reuse ST/exclusion basic-filter logic and enriched/depth signals; do not re-derive |
| `api/* ↔ services` | strict DTOs | Server-owned state resolution; no business logic in routers |
| `services/quote_service ↔ frontend` | SSE `portfolio_run_updated` | Coarse invalidation; durable job SSE only for walk-forward/optimization progress |
| `operational/migrations ↔ new repositories` | `migrate_operational_db` | New tables appended to `MIGRATIONS`; repositories share `operational.db` [VERIFIED] |

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| TickFlow market data | unchanged — via `tickflow/repository.py` + `BacktestEngine` | No new provider work |
| AI provider (hypothesis → DSL) | unchanged — `research/hypotheses.py` draft gateway | Proposals never auto-admit; gates require explicit reviewed factor revisions |
| No external DB / message queue | preserved | Single-container constraint remains |

---

## New vs Modified Components (summary)

| Kind | Components |
|------|-----------|
| **NEW backend modules** | `research/admission.py`, `research/models.py`, `research/signal_chain.py`, `portfolio/{optimizer,risk,rebalance,repository,schemas}.py`, `backtest/walkforward.py`, `backtest/ensemble.py`, `api/optimization.py` |
| **MODIFIED backend** | `research/{factor_registry,evaluation,catalog,repository}.py`, `portfolio/service.py`, `backtest/optimizer.py`, `api/{research,backtest}.py`, `operational/migrations.py`, `services/quote_service.py`, `main.py` (wiring) |
| **REUSED unchanged** | `research/factor_dsl.py`, `research/artifacts.py`, `research/hypotheses.py`, `backtest/{engine,factor,strategy,frozen_panel}.py`, `operational/repository.py`, auth/capability gating |
| **NEW frontend** | `ModelLibrary`, `WalkForward` panels; Portfolio `Optimization/RiskAttribution/RebalancePlan` panels |
| **MODIFIED frontend** | `lib/api.ts`, `lib/queryKeys.ts`, `pages/Backtest.tsx`, `pages/Portfolio.tsx` |

---

## Dependency-Aware Build Order

```text
Wave 0 (contracts & foundations):
  migrations for portfolio_*, factor_model_*, admission_*, summaries
  portfolio/schemas.py (PortfolioInputSnapshot, DTOs)
  promote scipy to base deps (package-legitimacy gate if required)

Wave 1 (the backbone):
  research/signal_chain.py  ← everything downstream depends on this
  evaluation refactor to use the chain; add ICIR/monthly-robustness/coverage

Wave 2 (factor library completion):
  research/admission.py gates (append-only verdicts)
  research/models.py multi-factor composition
  catalog summaries + registry admission status

Wave 3 (portfolio construction):
  portfolio/risk.py (risk models + PSD repair + attribution pure functions)
  portfolio/optimizer.py (min-vol + HRP baselines, constraint stack)
  portfolio/repository.py (immutable run records)

Wave 4 (output & boundary):
  portfolio/rebalance.py (A-share lots, blocked instruments, expiry)
  paper-rebalance audit fact

Wave 5 (deeper strategy research — can overlap Wave 3/4):
  backtest/walkforward.py (rolling, reserved OOS)
  backtest/optimizer.py OOS reservation + backtest/ensemble.py

Wave 6 (API/SSE + frontend):
  api/optimization.py, api/research.py additions, api/backtest.py walk-forward SSE
  quote_service notify_portfolio_run_updated
  frontend api.ts / queryKeys.ts / panels
```

**Rationale:** Wave 1 must precede everything because evaluation, models, expected returns, walk-forward, and live plans all consume the chain. Waves 2 → 3 → 4 are strictly ordered (admitted factors feed models → composite score feeds expected returns → weights feed plans). Wave 5 depends only on Wave 1 + 2 and can run parallel to Waves 3–4 for throughput, but its OOS reservation must be defined before any parameter search is reused.

---

## Sources

- AthenaQuant codebase (verified 2026-07-31): `backend/app/research/*`, `backend/app/portfolio/*`, `backend/app/backtest/*`, `backend/app/operational/*`, `backend/app/api/*`, `backend/app/services/quote_service.py`, `backend/app/main.py`, `frontend/src/lib/api.ts`, `frontend/src/pages/Backtest.tsx`, `frontend/src/router.tsx`, `backend/pyproject.toml`, `backend/uv.lock`
- `/home/orca/source/AthenaQuant/docs/ARCHITECTURE.md` and `.planning/codebase/ARCHITECTURE.md` — existing host layers
- `.planning/PROJECT.md` — v1.2 milestone scope, constraints, fail-closed boundaries
- `/home/orca/source/docs/aaa/qlib/DEEP-ANALYSIS.md` — Recorder/RecordTemp, Strategy/Executor contracts, SignalRecord→SigAnaRecord (HIGH)
- `/home/orca/source/docs/aaa/alphaagent/DEEP-ANALYSIS.md` — DSL layering, FactorZoo similarity dedup, admission checklist, monthly robustness (HIGH)
- `/home/orca/source/docs/aaa/pyportfolioopt/DEEP-ANALYSIS.md` — PortfolioInputSnapshot/OptimizationRun/RebalancePlan contract, risk models, min-vol/HRP baselines, discrete allocation, ActionGuard paper-only (HIGH)
- `/home/orca/source/docs/aaa/alphamaster/DEEP-ANALYSIS.md` — shared backtest/live signal chain, rolling walk-forward with gap + reserved OOS, vocab versioning (HIGH)
- `/home/orca/source/docs/aaa/lean/DEEP-ANALYSIS.md` — Insight→target→risk→execution layering, risk as computable mutation, paper-only execution boundary (HIGH)
- `/home/orca/source/docs/aaa/15-数据底座与采集底座篇.md` — Parquet/DuckDB/Polars, enriched narrow-table storage, data contracts (MEDIUM)

---
*Architecture research for: AthenaQuant v1.2 End-to-End Factor Portfolio Pipeline*
*Researched: 2026-07-31*
