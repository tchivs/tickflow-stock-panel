# Feature Research

**Domain:** A-share factor portfolio research pipeline (factor library → portfolio construction → risk attribution → walk-forward research → paper rebalance suggestions)
**Researched:** 2026-07-31
**Confidence:** HIGH (grounded in local knowledge base DEEP-ANALYSIS docs and AthenaQuant v1.0 shipped code)

## Feature Landscape

> Scope note: This is a SUBSEQUENT milestone. v1.0 already ships: restricted factor DSL (`research/factor_dsl.py`), factor registry with deterministic similarity discovery (`research/factor_registry.py`), IC/RankIC factor evaluation (`research/evaluation.py`), immutable experiment catalog (`research/catalog.py`), SHA-256 governed-panel strategy backtests (`backtest/frozen_panel.py`, `backtest/strategy.py`), an A-share-aware matching engine (T+1, price limits, suspension, 100-share lots, stamp tax/slippage — `backtest/engine.py`), and a param grid optimizer (`backtest/optimizer.py`). The features below are ONLY the NEW capabilities required to extend that into a factor → portfolio → risk → rebalance pipeline. Where a feature reuses an existing seam, that is called out as a dependency, not a build.

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = the pipeline feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Factor admission gates** (train/val IC threshold, no lookahead, no label leakage, similarity dedup) | A "multi-factor library" is only trustworthy if junk factors cannot enter. Users expect IC to be measured out-of-sample, not on the same window used to approve the factor. | MEDIUM | Reuses existing DSL parse + evaluation service. NEW: chronological train/val split of the evaluation window, monthly robustness check, leakage audit, and a similarity-dedup admission threshold. AlphaAgent makes these explicit: parse_ok / eval_ok / coverage / train+val IC / monthly robustness / similarity / no-label-leakage. |
| **ICIR + monthly robustness + coverage in factor evaluation** | Standard factor health metrics beyond point IC. ICIR (mean/std of IC series) exists in `evaluation.py` as `information_ratio`; monthly robustness (positive month ratio / month-stable IC) and coverage (finite fraction) are NOT yet surfaced as admission inputs. | LOW–MEDIUM | Qlib `SigAnaRecord` computes IC, ICIR, RankIC, RankICIR, long/short returns. AlphaAgent returns `monthly_corr_robustness` and coverage in every eval. |
| **Factor catalog with admission status + summary storage** | Users expect to browse admitted vs rejected factors and see summary stats without recomputing full panels. | LOW–MEDIUM | `ExperimentCatalog` + `research/repository.py` already store immutable snapshots. NEW: an admission-status field and a compact summary (train/val IC, ICIR, monthly robustness, coverage, similarity-to-nearest) written at eval time. |
| **Multi-factor composite expected returns** (cross-sectional z-score / rank-average of admitted factors) | Single-factor scores do not form a portfolio. Users expect an explicit, deterministic rule for turning N admitted factors into one expected-return vector. | MEDIUM | Alpha Zoo pattern (Vibe-Trading): per-factor z-score → weighted sum → optional top-N discretization. Keep weighting deterministic (equal-weight or IC-weight) in MVP; no ML mixing. |
| **Long-only min-volatility optimizer as stable baseline** | Min-vol with long-only + basic constraints is the stable, defensible first objective. Users expect "the boring optimizer" to work before exotic objectives. | MEDIUM | PyPortfolioOpt pattern: expected returns + covariance + explicit objective + constraints → continuous weights. Min-vol is convex (safe); needs a solver (scipy SLSQP or CVXPY). Must NOT default to max Sharpe. |
| **HRP (hierarchical risk parity) as a second stable baseline** | HRP needs no covariance inverse and handles ill-conditioned covariance better than MV; it is the standard "compare against" baseline for individual investors. | MEDIUM–HIGH | PyPortfolioOpt `HRPOpt`: correlation-distance clustering + recursive variance allocation. Needs scipy linkage. Adds a defensible non-MV baseline without max-Sharpe instability. |
| **Immutable optimization run records** | Every optimization must be reproducible: input snapshot (returns/cov/constraints/objective/solver), output weights, status. Users expect auditability consistent with the platform's existing SHA-256 panel identity. | MEDIUM | PyPortfolioOpt: "each optimizer instance freezes objective+constraints after first solve; inputs must be recorded." Mirror the existing `FrozenPanelArtifactStore` contract — freeze inputs, checksum, persist, never overwrite. |
| **RebalancePlan: continuous weights → A-share discrete lots, cash, turnover, blocked instruments, expiry** | A research pipeline that ends in weights must convert them to A-share reality: 100-share lots, T+1, suspension/limit-up/limit-down blocking, cash buffer, fees. Users expect the plan to be actionable-on-paper, not abstract percentages. | MEDIUM–HIGH | Do NOT mutate continuous weights in the optimizer; separate the lot-sizing/market adapter layer (PyPortfolioOpt `DiscreteAllocation` pattern + A-share rules already proven in `backtest/engine.py`: `buy_limit_up`, `buy_suspended`, `buy_lot_size`, `buy_same_day_reentry`, `buy_cash`). Plan carries `blocked_instruments` + `expires_at`. |
| **Suggestions to auditable paper rebalance — NO execution authority** | The whole point of the milestone: output rebalance *suggestions* to a paper account with full audit, never an order to a broker. | MEDIUM | Reuse Shadow's retention-gate pattern (`shadow/`): frozen evidence → chronological IS/OOS → explicit retain. PA_Agent pattern: ApprovalTicket consumed only with fresh evidence + deterministic RiskAssessment. No execution path exists or is planned. |
| **Rolling walk-forward validation (NOT expanding) with a reserved independent final OOS segment** | Strategy research beyond a single IS/OOS split is table stakes for any "deeper strategy research" claim. Rolling (not expanding) prevents early validation windows from re-entering later training. | MEDIUM | AlphaMaster: 5-fold rolling window with `WF_GAP`; explicitly warns that walk-forward OOS is still on the same data file and a *reserved final segment* untouched by any search is required for a true blind test. |
| **Risk exposure + contribution attribution** | Users expect to see portfolio risk broken down (by instrument, by factor/sector where data allows) — not just a total volatility number. | MEDIUM | Requires covariance + weights. Contribution = weight · (Σw) exposure. Drawdown attribution (which names drove the drawdown) is add-after, not launch. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **LLM proposes factor DSL expressions — never free code** | Extends the platform's existing "bounded AI" philosophy to factor discovery: an LLM writes whitelisted DSL, not Python. This is a genuine differentiator vs most retail quant tools that either forbid AI or allow arbitrary code. | MEDIUM | Already shipped for manual entry (`research/api.py` `/dsl/options`, `/factors`); the differentiator is wiring the same whitelist-parse path as the *only* AI entry. AlphaAgent shows the safe path: NL idea → DSL → parser whitelist → sandbox evaluator → metrics → store. |
| **Deterministic admission gates with train/val IC + monthly robustness + similarity dedup + no-lookahead/no-leakage** | Anti-overfit rigor as a first-class feature, not a footnote. Most retail tools show point IC and stop. | MEDIUM | AlphaAgent's exact admission list; makes factor promotion auditable and comparable to the platform's existing experiment-retention gates. |
| **Immutable optimization run records with governed-panel SHA-256 identity** | Every weight vector traces to exact frozen inputs. Differentiator for trust: "this portfolio is exactly reproducible." | MEDIUM | Extends `frozen_panel.py` contract to the optimizer. |
| **Stable baselines first (min-vol + HRP), max-Sharpe explicitly NOT default** | Honest optimization: max-Sharpe is numerically unstable and encourages overfit. Leading with stable objectives is a defensibility differentiator. | MEDIUM | PyPortfolioOpt: max_sharpe uses variable substitution that makes extra objectives non-intuitive; warn before enabling. |
| **A-share-native RebalancePlan (lots/T+1/limits/blocked/expiry) → paper suggestion pool** | The A-share adapter is the hard part; shipping it as an auditable suggestion (not an order) is the product. | MEDIUM–HIGH | Prove the adapter in backtest first (already done in `backtest/engine.py`), then reuse the same rules for the plan. |
| **Shared backtest/live signal chain** | One factor implementation compiled once, used identically for walk-forward research and live paper scoring — eliminates train-serve skew. | MEDIUM | AlphaMaster: "one feature/VM/signal implementation shared by backtest and online scoring." AthenaQuant's DSL-compile seam makes this cheap. |
| **Risk models: Ledoit-Wolf + PSD repair** (add-after) | Better covariance estimation with shrinkage + a positivity guarantee so the optimizer can never fail on a non-PSD matrix. | MEDIUM | PyPortfolioOpt `risk_models` (sample/semi/exponential/Ledoit-Wolf/Oracle) + spectral/diagonal PSD repair. Add after sample covariance is validated. |
| **Ensembling of strategies scored on walk-forward folds** (add-after) | Rank-average of independently validated strategies, chosen on OOS folds not IS. | MEDIUM | Alpha Evolution Lab: mutation/promotion gates; ensemble only after each member passes walk-forward. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Max Sharpe as the default objective** | "Best risk-adjusted return" sounds like the obvious goal. | Numerically unstable (leverages estimation error in expected returns), overfits the in-sample period, and its variable substitution makes added constraints behave unintuitively (PyPortfolioOpt warning). | Default to min-vol and HRP baselines; expose max-Sharpe only as an explicit, labelled option after baselines are proven. |
| **Black-Litterman in the MVP** | "Modern" portfolio theory with views; sounds sophisticated. | Needs structured views → Q/P/omega mapping, market prior, risk-aversion/tau calibration, and confidence conversion (idzorek). LLM/natural-language views cannot bypass evidence+horizon+confidence transforms. High complexity for little MVP value. | Defer to add-after. When added, require a structured view object (asset, direction, horizon, evidence, confidence), not free text. |
| **Free-form Python factor code (AI-written)** | Maximum expressiveness; "the LLM can just write the formula." | Security boundary break (the platform deliberately ships AST/whitelist sandboxes: `quantdinger`, `joinquant-skill` future-function lint), reproducibility loss, and no DSL-based dedup/lookahead audit. | Restricted DSL only — LLM proposes expressions, whitelist parser compiles them. |
| **Short selling / leverage in optimization** | Higher potential returns. | A-share individual investors face T+1, restricted shorting, and margin complexity; adds non-convexity and solver risk. Milestone scope says long-only. | Long-only in MVP; document shorting as future. |
| **Expanding-window walk-forward** | "Use all history" feels rigorous. | Expanding windows re-use early validation data in later training segments — the exact leakage the milestone forbids. | Rolling windows with a fixed training span + explicit `WF_GAP`; reserve an independent final OOS segment. |
| **Parameter optimization scored on in-sample only** | Grid search already exists (`optimizer.py`), easy to reuse. | Selection on in-sample objective (default `sortino`) overfits; multiple-comparison makes a "best" combo a statistical artifact. | Score param combos on walk-forward OOS folds; enforce train/val gap and pre-registered candidate counts (AlphaMaster + RD-Agent hypothesis discipline). |
| **Industry cap without verified industry mapping** | Sector diversification is table stakes in theory. | AthenaQuant's sector JOIN is currently fail-closed (`monitor.py`: "sector JOIN 未实现"); industry data only arrives via ext_data presets (concept/industry). A cap built on ungoverned mapping silently mis-caps. | Make industry cap an add-after gated on a governed industry mapping column; ship per-instrument cap + min cash + turnover cost in MVP. |
| **Storing full factor value matrices for every factor** | "Fast retrieval later." | Storage/IO bloat in a single-host Parquet+SQLite deployment; recompute-from-DSL is cheap and always version-consistent. | Store catalog summaries + admission stats; recompute values on demand from the frozen DSL revision. (AlphaAgent FactorZoo stores only summaries + sample stats for search.) |
| **"One-click best portfolio" auto-pilot** | Convenience. | Removes the human review that makes the pipeline auditable; the milestone explicitly forbids execution authority and requires suggestions + expiry. | Suggestion pool with explicit review, expiry, and immutable audit. |
| **External DB / message queue** | "Scale-ready." | Violates the single-container, Parquet+SQLite architecture constraint. | Keep everything in the existing host; the pipeline is research-only. |

## Feature Dependencies

```
[A: Factor admission gates]
    └──requires──> [B: Admitted factor catalog]
                       └──requires──> [C: Multi-factor composite expected returns]
                                          └──requires──> [D: Covariance / risk model]
                                          └──requires──> [E: Optimization (min-vol / HRP)]
                                                              └──requires──> [F: RebalancePlan + A-share lots]
                                                                                  └──requires──> [G: Paper rebalance suggestion]

[H: Walk-forward harness] ──provides──> [I: Parameter optimization (OOS-scored)] ──provides──> [J: Ensembling]

[E: Optimization] ──produces──> [K: Risk exposure/contribution attribution]

[D: Covariance] ──enhances──> [K: Risk attribution]
                              └──enhances──> [E: Optimization]

[Existing: restricted DSL + IC/RankIC eval + frozen panels] ──precedes──> [A, C, H]

[F: RebalancePlan] ──enhances──> [G: Paper suggestion] (plan is the input to the suggestion)

[Industry cap] ──conflicts──> [MVP timeline] (blocked on governed industry mapping)
[Max Sharpe default] ──conflicts──> [Stable baselines]
[Expanding walk-forward] ──conflicts──> [No-lookahead guarantee]
```

### Dependency Notes

- **Factor admission gates (A) must precede portfolio construction (C/E):** only admitted factors may feed expected returns and optimization. Feeding raw unvalidated factors makes the whole downstream pipeline inherit junk. This is the single most important ordering constraint.
- **No-lookahead / no-label-leakage (A) is a precondition of trustworthy IC (B):** the DSL restricts to governed columns (already shipped), but the *label* must be future-close shifted (`shift(-N)`) and the factor must never reference a future window. The admission gate audits this before a factor can enter the catalog.
- **Admitted catalog (B) precedes composite returns (C):** C is defined over the admitted set, so the dedup/similarity gate must run first or the composite double-counts near-identical factors.
- **Expected returns (C) + covariance (D) are independent inputs to the optimizer (E):** PyPortfolioOpt's core layering. Both must be frozen into the run record for reproducibility.
- **Risk models (D) precede risk attribution (K) and feed optimization (E):** attribution is `weight · exposure` against the same covariance used to optimize; using a different covariance makes attribution inconsistent.
- **Optimization (E) precedes RebalancePlan (F):** F is a *rendering* of E's continuous weights into A-share lots + blocked instruments + expiry. The lot-sizing adapter must not modify the optimizer output (audit separation).
- **RebalancePlan (F) precedes paper suggestion (G):** G consumes the plan, applies the suggestion-pool rules (expiry, no execution authority), and persists an audit trail.
- **Walk-forward (H) precedes parameter optimization (I):** params must be scored on OOS folds produced by H; otherwise I is just in-sample curve fitting. Ensembling (J) then only combines candidates that passed I's gates.
- **Shared signal chain is a horizontal requirement:** the same DSL-compile path must back H, live paper scoring, and the composite C — otherwise research results do not reproduce live. AlphaMaster treats this as a core invariant.
- **MVP conflicts:** industry cap and max-Sharpe both conflict with the MVP timeline by design — ship without them, gate them behind governed data / proven baselines.

## MVP Definition

### Launch With (v1.2 core)

Minimum viable pipeline — must validate the concept end-to-end:

- [ ] **Factor admission gates on existing evaluation** — chronological train/val split of the eval window, train/val IC threshold, no-lookahead audit, no-label-leakage audit, similarity-dedup admission threshold. Reuses DSL + evaluation service; adds gate logic + monthly robustness + coverage to the metric set.
- [ ] **Admitted factor catalog with summary storage** — extend `ExperimentCatalog`/repository with admission status + compact summaries (train/val IC, ICIR, monthly robustness, coverage, nearest-neighbor similarity). No full value-matrix persistence.
- [ ] **Multi-factor composite expected returns** — cross-sectional z-score (or rank-average) + deterministic equal-weight or IC-weight combination of admitted factors. No ML, no LLM in the return model.
- [ ] **Sample covariance + PSD check/repair** — sample covariance from governed returns; reject or repair non-PSD so the optimizer never fails on an invalid matrix. (Ledoit-Wolf/semi/exponential are add-after.)
- [ ] **Long-only min-volatility optimizer** — objective + constraints layering: long-only, per-instrument cap, min cash, turnover cost. Continuous weights out. Solver: scipy SLSQP (or CVXPY if already present); must not default to max-Sharpe.
- [ ] **HRP baseline** — hierarchical risk parity as a second stable objective where scipy linkage is available; if unavailable at build time, defer HRP but ship min-vol alone.
- [ ] **Immutable optimization run records** — freeze returns/cov/objective/constraints/solver/status + output weights under the existing checksum identity contract; persist, never overwrite.
- [ ] **RebalancePlan** — target weights → A-share discrete lots (100-share), expected cash, turnover/cost, `blocked_instruments` (suspension/limit-up/limit-down from enriched panel), `expires_at`.
- [ ] **Paper rebalance suggestion (NO execution authority)** — plan lands in the auditable suggestion pool with expiry; server-owned authorization; no broker/execution seam anywhere.
- [ ] **Risk exposure + contribution attribution** — per-instrument exposure and contribution from weights + covariance. (Drawdown attribution is add-after.)
- [ ] **Rolling walk-forward harness (not expanding) with reserved independent final OOS** — fixed training span, explicit gap, last segment reserved and never used for any search/selection. Reuses strategy backtest + frozen panels.

### Add After Validation (v1.2.x)

Features to add once the launch core is working:

- [ ] **Ledoit-Wolf / semi / exponential covariance + PSD repair options** — trigger: sample covariance validated; users need shrinkage for unstable estimates.
- [ ] **Drawdown attribution** — trigger: exposure/contribution attribution is accepted; users ask "which names drove the drawdown."
- [ ] **Industry cap** — trigger: a governed industry mapping column is available (currently sector JOIN is fail-closed). Do NOT ship a cap on ungoverned ext_data.
- [ ] **Parameter optimization scored on walk-forward OOS** — trigger: walk-forward harness exists; grid search gains OOS-scored objective + train/val gap checks (extends `optimizer.py`).
- [ ] **Strategy ensembling** — trigger: ≥2 strategies pass walk-forward; rank-average them and re-evaluate on the reserved OOS segment only.
- [ ] **Black-Litterman** — trigger: a structured research-view object (asset, direction, horizon, evidence, confidence) exists; then map to Q/P/omega via idzorek. Natural-language views must not bypass the transform.

### Future Consideration (v2+)

Features to defer until product-market fit is established:

- [ ] **Max Sharpe as an explicit, labelled objective** — only after min-vol/HRP baselines are proven and users understand its instability; never a default.
- [ ] **Short selling / leverage in optimization** — needs A-share margin semantics and solver scope well beyond long-only.
- [ ] **Auto-rebalance scheduling** — periodic re-suggestion; still paper-only, gated by explicit opt-in and fresh evidence at each run (PA_Agent refresh-at-approval pattern).
- [ ] **ML-based expected-return models** — Kronos-style forecasts or learned alpha mixing; needs a separate validation regime (the platform's Forecast module already models this boundary).
- [ ] **Multi-period / path-dependent objectives** — transaction-cost-aware dynamic programming; high complexity, low MVP value.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Factor admission gates (train/val IC, no lookahead, no leakage, dedup) | HIGH | MEDIUM | P1 |
| Admitted factor catalog + summaries | HIGH | LOW–MEDIUM | P1 |
| ICIR / monthly robustness / coverage in eval | HIGH | LOW | P1 |
| Multi-factor composite expected returns | HIGH | MEDIUM | P1 |
| Sample covariance + PSD repair | HIGH | LOW–MEDIUM | P1 |
| Long-only min-vol optimizer | HIGH | MEDIUM | P1 |
| HRP baseline | MEDIUM | MEDIUM–HIGH | P1 (P2 if scipy absent) |
| Immutable optimization run records | HIGH | MEDIUM | P1 |
| RebalancePlan (A-share lots, cash, turnover, blocked, expiry) | HIGH | MEDIUM–HIGH | P1 |
| Paper rebalance suggestion (no execution) | HIGH | MEDIUM | P1 |
| Risk exposure + contribution attribution | MEDIUM | MEDIUM | P1 |
| Rolling walk-forward (not expanding) + reserved OOS | HIGH | MEDIUM | P1 |
| Shared backtest/live signal chain | HIGH | LOW (reuse DSL seam) | P1 |
| Ledoit-Wolf / semi / exponential covariance | MEDIUM | MEDIUM | P2 |
| Drawdown attribution | LOW–MEDIUM | MEDIUM–HIGH | P2 |
| Parameter optimization on OOS folds | MEDIUM | MEDIUM | P2 |
| Strategy ensembling | MEDIUM | MEDIUM | P2 |
| Industry cap | MEDIUM | HIGH (data dependency) | P2 |
| Black-Litterman | LOW | HIGH | P3 |
| Max-Sharpe (explicit, non-default) | LOW | LOW (after optimizer exists) | P3 |
| Short selling / leverage | LOW | HIGH | P3 |
| Auto-rebalance scheduling | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Qlib | AlphaAgent | PyPortfolioOpt | Lean (QuantConnect) | Our Approach |
|---------|------|------------|----------------|---------------------|--------------|
| Factor expression language | Config-driven models, no user DSL | Restricted A-share DSL (pyparsing, operator registry, `field@freq`) | N/A (consumes returns/cov) | Insights from arbitrary C# | Existing whitelist DSL; LLM proposes expressions only |
| Factor evaluation | SignalRecord + SigAnaRecord: IC/ICIR/RankIC/RankICIR, long-short | IC/RankIC, monthly robustness, coverage, split eval | N/A | Backtest statistics | IC/RankIC shipped; add ICIR + monthly robustness + coverage + admission gates |
| Admission / promotion gates | Experiment records, no hard factor gate | Explicit admission list (coverage, train/val IC, robustness, similarity, leakage) | N/A | Algorithm registration, no factor gate | Deterministic admission gates mirroring AlphaAgent + existing experiment-retention gates |
| Similarity dedup | N/A | FactorZoo manifest + sample-summary similarity | N/A | N/A | Existing structural-signature + Jaccard similarity (`factor_registry.py`); add admission threshold |
| Portfolio optimization | Strategy/Executor/Decision (targets, not MV math) | N/A | EfficientFrontier (min-vol, max-Sharpe, HRP, BL), constraints, discrete allocation | PortfolioConstructionModel → IPortfolioTarget | Min-vol + HRP baselines, long-only + caps + min cash + turnover, immutable runs |
| Risk models | Portfolio metrics; no shrinkage library | N/A | Sample/semi/exponential/Ledoit-Wolf + PSD repair | RiskManagementModel (target mutation) | Sample + PSD in MVP; shrinkage add-after |
| Risk attribution | N/A | N/A | N/A | Not first-class | Exposure + contribution in MVP; drawdown add-after |
| Walk-forward | Rolling train in workflow | Split-based eval | N/A | Backtesting with rolling windows | Rolling (not expanding) + reserved final OOS |
| Parameter optimization | Model config search | N/A | N/A | Grid search | Extend existing grid to OOS-scored objective + gap checks |
| Ensembling | Model zoo ensembles | N/A | N/A | Composite alpha models | Rank-average of walk-forward-validated strategies |
| Output boundary | N/A | N/A | DiscreteAllocation (generic) | ExecutionModel → orders | RebalancePlan (A-share lots) → auditable paper suggestion, no execution |

## Sources

**Local knowledge base (DEEP-ANALYSIS, HIGH confidence — static-source verified):**
- [AlphaAgent DEEP-ANALYSIS](../docs/aaa/alphaagent/DEEP-ANALYSIS.md) — restricted DSL, IC eval with monthly robustness/coverage, FactorZoo storage, admission list, no-lookahead/leakage audit.
- [PyPortfolioOpt DEEP-ANALYSIS](../docs/aaa/pyportfolioopt/DEEP-ANALYSIS.md) — expected-return/cov/objective/constraint layering, min-vol/HRP/BL, PSD repair, DiscreteAllocation + A-share LotSizingAdapter, max_sharpe instability warning, immutable run contract.
- [Qlib DEEP-ANALYSIS](../docs/aaa/qlib/DEEP-ANALYSIS.md) — SignalRecord/SigAnaRecord (IC/ICIR/RankIC), Recorder/ExpManager run records, data health as first-class artifact.
- [AlphaMaster DEEP-ANALYSIS](../docs/aaa/alphamaster/DEEP-ANALYSIS.md) — rolling walk-forward with WF_GAP, reserved final OOS warning, shared backtest/live signal chain, factor-correlation penalties.
- [Lean DEEP-ANALYSIS](../docs/aaa/lean/DEEP-ANALYSIS.md) — Insight → PortfolioTarget → Risk → Execution layering; risk must be target mutation/rejection, not prose; A-share adapter gap list.
- [PA_Agent DEEP-ANALYSIS](../docs/aaa/pa-agent/DEEP-ANALYSIS.md) — two-stage analysis, ApprovalTicket with fresh-evidence revalidation, deterministic RiskEngine, paper ledger, fail-closed preflight.
- [tickflow-stock-panel DEEP-ANALYSIS](../docs/aaa/tickflow-stock-panel/DEEP-ANALYSIS.md) — StrategyDef reuse, A-share backtest matching (T+1, limits, suspension, lots, fees), sector JOIN fail-closed.
- [策略与信号系统篇 (07)](../docs/aaa/07-策略与信号系统篇.md) — Alpha Zoo z-score combination, PyPortfolioOpt migration rules (long-only first, no max-Sharpe default, BL deferred), suggestion-pool boundaries.
- [10-SYNTHESIS.md](../docs/aaa/10-SYNTHESIS.md) — data contract first, quality gates, paper/sandbox defaults for high-risk actions.
- [Alpha Evolution Lab QUICK-START](../docs/aaa/alpha-evolution-lab/QUICK-START.md) — promotion gates (score_delta, train_val_gap, val_test_gap, data quality), save-failures-as-evidence.
- [joinquant-skill QUICK-START](../docs/aaa/joinquant-skill/QUICK-START.md) — AST lint, future-function checks, FactorMeta as asset with metadata.

**AthenaQuant shipped code (HIGH confidence — directly inspected):**
- `backend/app/research/factor_dsl.py` — restricted DSL, whitelisted fields/functions, compile_ast, canonicalization.
- `backend/app/research/evaluation.py` — IC/RankIC series, ICIR (`information_ratio`), positive_rate, forward-horizon labels, rebalance cadence.
- `backend/app/research/factor_registry.py` — immutable revisions, structural-signature + Jaccard similarity discovery.
- `backend/app/research/catalog.py` + `api/research.py` — immutable experiment snapshots, retain, comparison.
- `backend/app/backtest/frozen_panel.py` — SHA-256 governed-panel identity contract.
- `backend/app/backtest/engine.py` — A-share matching: `buy_limit_up`, `buy_suspended`, `buy_lot_size`, `buy_same_day_reentry`, `buy_cash`, stamp tax/slippage.
- `backend/app/backtest/optimizer.py` — existing param grid search (needs OOS-scored objective for v1.2).
- `backend/app/portfolio/service.py` — valuation projection only (no optimization yet).
- `backend/app/shadow/` — chronological non-overlapping IS/OOS evaluation + retention gates (pattern to reuse for factor admission and paper suggestions).

**Milestone context (HIGH confidence):**
- `.planning/PROJECT.md` — v1.2 target features and architecture constraints (single host, Parquet+SQLite, no external DB/MQ, research-only promotion, no execution authority).

---
*Feature research for: AthenaQuant v1.2 End-to-End Factor Portfolio Pipeline*
*Researched: 2026-07-31*
