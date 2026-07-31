# Pitfalls Research

**Domain:** A-share quantitative factor research → auditable portfolio pipeline (factor library, portfolio optimization, risk attribution, walk-forward validation, RebalancePlan suggestions)
**Researched:** 2026-07-31
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Lookahead / Future-Function / Label Leakage in the Factor DSL

**What goes wrong:**
A factor or multi-factor model uses data that was not available at the time the signal would have been computed: same-bar close used to predict forward returns, rolling windows that include the signal bar, `rank`/`zscore` computed over the full panel including future rows, or the forward-return label leaking into the factor input. Because v1.2 adds *multi-factor combination* on top of the existing v1.0 DSL, new combination operators (weighted sums, cross-sectional scores, correlation-style terms) can silently acquire full-panel semantics and re-introduce lookahead that the v1.0 single-factor DSL carefully avoided.

**Why it happens:**
- The v1.0 DSL pins semantics in the compiler: `rank`/`zscore` reset per date (`.over("date")`) and `rolling_mean` resets per symbol (`.over("symbol")`) — this contract is established, but new operators added for multi-factor models may be implemented without re-deriving point-in-time semantics.
- LLM-proposed expressions (the existing natural-language→DSL hypothesis gate) are the primary source of new factor ideas, and models are skilled at writing expressions that "accidentally" reference the label or future bars.
- The forward-return label lives adjacent to features in the panel, so a misspecified field allowlist lets it in.

**How to avoid:**
- Keep the DSL closed, versioned, and canonical-serialized; every operator must declare its partition context (per-date cross-section, per-symbol time-series, or pointwise) in the compiler, never inferred at runtime.
- The compiler must reject any reference to label/target fields (explicit deny-list in the field allowlist) and any construct outside the grammar (no `eval`, no `pl.sql_expr`, no dynamic attribute lookup — v1.0 already forbids these).
- Add a deterministic leakage test: shift the forward-return label by one period and assert the factor's IC collapses/does not persist — a lookahead factor survives the shift and reveals itself.
- Route multi-factor evaluation through the same governed `BacktestEngine.load_panel()` boundary so panel identity and partition semantics are inherited.
- Re-verify every operator when the DSL is extended; the v1.2 DSL extension is the highest-risk edit in the milestone.

**Warning signs:**
- Sustained daily IC far above the plausible domain range (A-share daily IC ≳ 0.1 is a red flag).
- A factor's value on day *t* is identical whether computed at *t* or at *t+5* (no information decay — classic lookahead).
- A "factor" is near-perfectly correlated with the forward return itself.
- `rolling_mean`/`rolling_std` windows appear to include the current bar in their sum.

**Phase to address:** Phase 10 — Factor Library & Multi-Factor Model. The admission gates explicitly include "no lookahead" and "no label leakage" checks, and the compiler partition-context contract is part of the DSL extension work.

---

### Pitfall 2: Survivorship Bias and Non-Point-in-Time Universe Selection

**What goes wrong:**
Factor evaluation, portfolio construction, and walk-forward validation use *today's* instrument list (current index constituents or the current lake inventory) instead of the universe as of each historical date. Delisted, suspended-then-delisted, or bankruptcy names never appear in the panel, so IC is inflated, covariance is biased, and backtest returns are systematically overstated. A "good" factor may be an artifact of only having survived stocks.

**Why it happens:**
- The governed lake stores the current instrument snapshot; the universe is resolved once at query time from the latest list rather than from a per-date universe table.
- Index constituents are captured as "current" and used for all history.
- v1.0's governed-data manifest records resolved symbols and observed data span, but there is no point-in-time universe contract yet.

**How to avoid:**
- Persist point-in-time universe snapshots: instrument list date, delist date, and index membership as-of date (the lake already stores instruments; extend with validity ranges).
- Resolve the universe per evaluation date from the snapshot — never from the live list for historical windows.
- Keep delisted securities' history in the lake (or record an explicit delisting marker) so they can enter historical panels.
- Record the resolved universe + snapshot revision in every run's governed-data manifest (extend the v1.0 manifest pattern).
- For walk-forward, resolve a fresh universe per fold using the fold's as-of dates.

**Warning signs:**
- The same universe list is returned for 2015 and 2025.
- No strategy backtest ever includes a delisted stock.
- OOS performance collapses when re-run on a fixed historical universe.
- Universe size is constant over a decade (real A-share universes grow and shrink).

**Phase to address:** Phase 10 (universe snapshot contract + manifest extension) and Phase 13 (per-fold universe resolution in walk-forward). Without the Phase 10 contract, Phases 11-13 all silently inherit the bias.

---

### Pitfall 3: IC Robustness Overfitting and Monthly-Only Significance

**What goes wrong:**
A factor is admitted because mean IC / RankIC / ICIR looks strong, but the signal is driven by two or three months or a single regime. "Monthly robustness" is gamed by choosing a favorable month window, or the monthly gate is passed on data that was already used to select the factor. Because the LLM mining loop can propose thousands of candidates cheaply, only the winners are recorded — the catalog hides the true multiple-comparison context.

**Why it happens:**
- Scalar summaries (mean IC) hide the per-month distribution.
- Admission thresholds are tuned *after* seeing candidate performance (thresholds become part of the selection, not a fixed policy).
- The factor mining loop (already in the architecture) generates many candidates; without a candidate trail, the admission ratio is invisible.
- Monthly robustness is evaluated over a window chosen to make the factor look stable.

**How to avoid:**
- Mandate the full monthly evidence set for admission: monthly IC series, sign-consistency ratio (fraction of months with same-sign IC), worst-month IC, and rolling ICIR — not just a mean.
- Fix the monthly window and admission thresholds as *policy constants* before any candidate is evaluated; apply them unchanged to every candidate.
- Record every candidate attempt (including rejected ones) in the catalog with its metrics — the trial count, admission ratio, and threshold application must be auditable (AlphaAgent's `monthly_ic_robustness` gate and AlphaMaster's selection-bias audit).
- Use a train/val split where thresholds are applied only to the validation segment.
- Run similarity dedup against the stored factor library (AST structural signature + value/sample-summary similarity) before admission so near-duplicate factors don't inflate the catalog.

**Warning signs:**
- Monthly IC heatmap shows a single hot streak; most months are near zero or negative.
- ICIR is high but computed over very few months.
- Hundreds of failed candidates are deleted; only winners persist.
- Admission thresholds differ per factor (clear sign of post-hoc tuning).

**Phase to address:** Phase 10 — the admission gates (train/val IC, monthly robustness, similarity dedup) and the candidate trail are the gates themselves.

---

### Pitfall 4: Covariance PSD Failures and Silent Fixes

**What goes wrong:**
The sample covariance matrix is not positive semi-definite (common with wide A-share panels: more assets than observations, pairwise estimation over NaN-heavy data caused by suspensions), so the optimizer either fails or a silent "fix" (clip negative eigenvalues, bump the diagonal) is applied to make the solver happy. The result is a portfolio whose *stated* risk does not match the true covariance, and risk attribution no longer sums to portfolio variance. Because the "fix" is invisible, the researcher trusts risk numbers that are wrong.

**Why it happens:**
- Covariance is estimated pairwise over the full cross-section, and suspensions create NaN gaps that make pairwise matrices indefinite.
- A one-line `eigh`-clip or `+epsilon*I` is the fastest way to stop the solver complaining, and it ships without being recorded.
- The milestone explicitly lists "PSD repair" as a feature, which can read as permission to do it silently.

**How to avoid:**
- Choose a risk model deliberately and record it: Ledoit-Wolf shrinkage as the default for wide panels, exponential weighting for non-stationarity, semi-covariance for downside focus — don't default to raw sample covariance.
- Make PSD repair an *explicit, recorded step*: method used, epsilon, eigenvalue range before/after — stored in the immutable optimization run record (PyPortfolioOpt's audit-field pattern: `cov_matrix` must record risk model, frequency, window, missing-value rule, repair method).
- Validate PSD before solving; assert the optimizer's reported risk equals the recorded risk model's own variance for the same weights.
- Compare portfolios across risk models (sample vs Ledoit-Wolf vs exponential) and surface disagreement rather than picking one quietly.

**Warning signs:**
- Negative eigenvalues in the covariance spectrum.
- Solver logs warnings about non-PSD matrices.
- Optimizer-reported portfolio volatility differs from the risk model's estimate.
- Risk contributions sum to ≠ 100% of portfolio variance.

**Phase to address:** Phase 12 — Risk models + explicit PSD-repair provenance; feeds Phase 11 (optimization consumes the recorded risk model). The repair must be part of the immutable run record, not a helper that mutates in place.

---

### Pitfall 5: Max-Sharpe as the Default Objective (Overfitting + Instability)

**What goes wrong:**
Defaulting to max-Sharpe (or presenting it as "the" optimum) overfits to noisy expected-return estimates: tiny input changes produce wildly different weights, the "optimal" portfolio concentrates in a handful of names with the best estimated alphas, and OOS performance degrades. Users mistake an optimizer output for a discovered edge. The milestone explicitly mandates that max-Sharpe must *not* be the default.

**Why it happens:**
- Max Sharpe is the textbook objective and produces an impressive-looking frontier, so it gets the default slot.
- Expected returns are noisy; any optimizer will exploit the noise, and max-Sharpe is the most sensitive objective to that noise.
- No baseline comparison is rendered, so there is nothing to show that the "optimum" is fragile.

**How to avoid:**
- Default to stable baselines: min-volatility and HRP (hierarchical risk parity) as the first-class objectives, per the milestone.
- Expose max-Sharpe only as an explicit researcher choice, with a warning and with expected-return source/confidence recorded (PyPortfolioOpt also warns that `max_sharpe` does a variable substitution that makes extra objectives behave unintuitively).
- Always render baseline comparison side-by-side (min-vol vs HRP vs max-Sharpe) so overfitting is visible.
- Add a weight-stability check: perturb inputs slightly and measure weight turnover; flag objectives whose weights flip.

**Warning signs:**
- Portfolio weights flip sign/magnitude with a one-day data change.
- A few names sit at the cap while most are zero.
- Max-Sharpe is the first option in the UI dropdown.
- No baseline portfolio is shown next to the "optimal" one.

**Phase to address:** Phase 11 — Portfolio Construction & Optimization. Objective defaults and baseline rendering are part of the optimization-run contract.

---

### Pitfall 6: A-share Microstructure Ignored (T+1, Price Limits, 100-Share Lots, Fees, Suspensions)

**What goes wrong:**
Backtests and RebalancePlans assume continuous fractional execution: same-day round trips (violating T+1), fills at limit-up/limit-down prices that are impossible in practice, fractional share weights, missing stamp duty/commission/min-commission, and suspended or limit-locked names traded at stale prices. The research pipeline outputs a "plan" that cannot actually be executed in an A-share account.

**Why it happens:**
- Portfolio optimizers output continuous weights; generic libraries (PyPortfolioOpt's `DiscreteAllocation` defaults to single shares) are used directly without an A-share adapter.
- The v1.0 backtest engine already enforces T+1, price limits, suspension handling, position caps, and fees/slippage (per the tickflow-derived matching layer), but the *new* walk-forward / plan path can bypass that layer and re-implement a naive matcher.

**How to avoid:**
- Treat the existing A-share matching layer as the single source of truth: T+1 restriction, 涨跌停/停牌 (limit-up/limit-down and suspension) fill blocking, per-instrument position caps, fees and slippage.
- Add a dedicated A-share lot-sizing adapter between continuous weights and the RebalancePlan: 100-share board lots, cash residue, sell odd-lots handling, min commission, sell-side stamp duty, transfer fee.
- Mark suspended and limit-locked instruments as *blocked* in the plan (explicit blocked-instrument field), never silently excluded.
- Record turnover cost and fees explicitly in the plan's expected-cash math; validate the plan under T+1 (no same-day buy+sell of the same name).
- Walk-forward folds must run through the same matching layer, not a second one.

**Warning signs:**
- Backtest shows same-day buy and sell of the same instrument.
- Plan lists fractional share counts.
- A suspended name appears in target weights.
- Fees are absent from the plan's expected cash; limit-up names included in buys.

**Phase to address:** Phase 14 — Output & Boundary (RebalancePlan lot-sizing adapter, blocked instruments, expiry, cash/turnover), with Phase 13 reusing the existing matching layer in walk-forward.

---

### Pitfall 7: Train/Serve Skew Between Backtest and Live Signal

**What goes wrong:**
The factor computed in research (evaluation/backtest) differs from the factor computed at "live" serve time when generating a rebalance suggestion — because of different data snapshots, different warmup history, different universe membership, or different adjustment factors. The suggestion produced for date *D* does not match the backtested portfolio for *D*, so the researcher cannot trust the plan as a realization of the validated strategy.

**Why it happens:**
- Backtest and live use separate code paths; the v1.0 `BacktestEngine.load_panel` governed boundary is used in research but the live suggestion path may read the repository directly.
- The live path has fewer historical bars (warmup) or uses a different universe resolution and adjustment factors (qfq vs hfq) than the frozen research snapshot.
- Normalization (cross-sectional z-score) depends on the universe membership and NaN pattern at compute time, which differ between snapshot and live.

**How to avoid:**
- Build one *shared signal chain*: the same factor-compile → evaluate → score implementation used by backtest, walk-forward, and live suggestion (AlphaMaster's single feature/VM/signal path; `max(MIN_BARS, 500)` warm-up guard).
- Freeze the data revision/panel fingerprint at serve time and record it in the plan's manifest (v1.0 governed-manifest pattern).
- Live serve must use the same adjustment-factor convention and universe snapshot logic as backtest.
- Add a deterministic test that the live path's factor values equal the research path's for the same as-of date on the same panel.

**Warning signs:**
- The plan's weights for date *D* differ from the backtest's weights for *D* on identical inputs.
- Factor values differ between the research result view and the suggestion view.
- The live path re-implements `rolling_mean`/`rank` differently, or NaN handling differs.

**Phase to address:** Phase 13 — shared backtest/live signal chain; Phase 14 — plan carries serve-time provenance so skew is detectable.

---

### Pitfall 8: Walk-Forward Leakage — Expanding Windows, Overlapping Folds, No True OOS

**What goes wrong:**
Walk-forward validation uses expanding windows (early validation segments reappear in later training), overlapping folds (train and test share bars), or reports the walk-forward "OOS" score as the final validation when that same segment was already used for factor/parameter selection. The result: no genuinely untouched segment exists, and the headline OOS number is optimistically biased. The milestone explicitly requires *rolling* (not expanding) windows and a *reserved independent OOS segment*.

**Why it happens:**
- Expanding windows feel natural and maximize training data; overlapping folds squeeze more "testing" out of a short A-share history.
- Researchers reuse the same segment for selection and for reporting, not realizing the selection already consumed its information.
- Fold layout is not recorded, so leakage is invisible to the catalog.

**How to avoid:**
- Use rolling windows with a gap between train and test (AlphaMaster uses `WF_GAP=20`; adopt an explicit gap so test segments never appear in training).
- Keep folds disjoint; record fold boundaries, gaps, and the data revision in the run record.
- Reserve a final independent OOS segment that *no* search, factor admission, threshold tuning, or ensembling ever touches — evaluate it exactly once at the end and gate promotion on it (AlphaMaster explicitly warns its walk-forward OOS is not a true blind test; a reserved segment closes that gap).
- Forbid promoting a strategy whose parameters were selected using the final OOS segment.

**Warning signs:**
- The same calendar date appears in both train and test of a fold.
- Early fold test data reappears in later fold training.
- The "final" OOS number improves after each retune.
- The reserved OOS segment is smaller than the validation used for search, or is re-run repeatedly.

**Phase to address:** Phase 13 — walk-forward validation: fold design (rolling + gap), the reserved OOS gate, and fold-layout recording.

---

### Pitfall 9: Parameter-Search Multiple-Comparison Bias

**What goes wrong:**
Grid/random search over hundreds of parameter combinations picks the best by validation score, then reports that best as the expected performance. The winner is an order statistic of many noisy trials, so OOS performance is systematically overstated. Ensembling that selects the best factor subset on the same data has the same bias. With LLM-proposed factor families, the search space is effectively unbounded, making the bias severe.

**Why it happens:**
- Every extra trial is another chance to get lucky; the best-of-N estimate is biased high and the bias grows with N.
- Trial count and search space are not recorded, so the multiple-comparison context is invisible.
- Selection and evaluation use the same segment (see Pitfall 8).

**How to avoid:**
- Restrict search to a training/validation split and keep the final OOS completely out of search (Phase 13's reserved segment).
- Record trial count, search space, selection rule, and the distribution of validation scores (not just the max) in the run record — this is the audit trail a reviewer needs (AlphaMaster's selection-bias audit: search count, candidate total, elite pool, unselected candidates, final thresholds).
- Prefer few, well-motivated parameters over broad grids; document why each parameter range was chosen.
- For ensembling, use a fixed averaging procedure rather than selecting the best subset by OOS; never tune ensemble weights on the final OOS.

**Warning signs:**
- Thousands of grid cells tried, only the winner persisted.
- Reported OOS ≈ the best validation score (suspiciously tight).
- Trial count not recorded in the run.
- Ensemble weights chosen on the final OOS.

**Phase to address:** Phase 13 — parameter optimization & ensembling: search bookkeeping, val-only selection, and OOS discipline.

---

### Pitfall 10: Treating Continuous Weights as Executable Orders

**What goes wrong:**
The optimizer's continuous target weights (e.g., 12.37% of the portfolio) are presented as if they were tradable — fractional shares, no lot rounding, no cash/limit handling — and the "plan" is promoted to a paper rebalance without a discrete A-share execution layer. Infeasible weights pass through to a suggestion the user might act on, and the discretization gap (continuous optimum vs actual lots) is invisible.

**Why it happens:**
- Portfolio optimization outputs a vector of floats and it *looks* like a plan.
- The milestone's RebalancePlan is the missing seam: developers conflate the optimizer output with the deliverable.
- Generic discretizers (PyPortfolioOpt's `DiscreteAllocation`) default to single-share units and don't know A-share lot rules.

**How to avoid:**
- Enforce strict layering (the Lean/PA_Agent pattern): `PortfolioOptimizationRun` (continuous weights, immutable) → `RebalancePlan` (discrete lots, cash, turnover, blocked instruments, expiry) → auditable paper rebalance with *no execution authority*.
- The lot-sizing adapter must round to 100-share lots, preserve residual cash, and record the discretization error (RMSE between continuous and discrete weights) so the gap is visible.
- Validate the plan for T+1, price limits, and suspensions before it becomes a suggestion; record blocked instruments explicitly.
- Nothing in the plan is ever executed — it is a research-only suggestion (server-owned authorization, paper-only).

**Warning signs:**
- Plan lists fractional share counts.
- No blocked-instrument field and no expiry date on the plan.
- Plan's total target weight ≠ 100% + cash.
- Any UI affordance suggests "execute".

**Phase to address:** Phase 14 — Output & Boundary: RebalancePlan + lot-sizing adapter + paper-rebalance state machine, consuming Phase 11 continuous weights.

---

### Pitfall 11: Auditability Gaps — Unrecorded Input Versions, Solver Choices, Failed Runs

**What goes wrong:**
Optimization runs and factor admissions are not reproducible: the data revision, expected-return source, risk model + PSD repair, constraint set, solver name/version/options, trial counts, and failed runs are not recorded. A result cannot be reconstructed or defended; silent solver fallbacks and numerical-tolerance hits are invisible. The append-only audit discipline established in v1.0 for factor/strategy research does not extend to the new portfolio/risk/search modules.

**Why it happens:**
- v1.0 built an immutable catalog for factor/strategy experiments; the new modules are added without extending that contract.
- Solvers are treated as black boxes; options and fallbacks go unlogged.
- Failed runs are deleted rather than retained (v1.0 already retains failed/cancelled/draft rows but excludes them from comparison — new code must do the same).

**How to avoid:**
- Extend the existing append-only catalog contract to every new run type: `PortfolioOptimizationRun` (input snapshot hash, expected-return method + confidence, risk model + PSD repair, constraint set, solver name/version/options, status), walk-forward fold layouts, parameter-search runs (trial count + space + selection rule), and factor admissions including rejected candidates (AlphaAgent's manifest/hash-on-metrics pattern).
- Retain failed/cancelled runs with diagnostics; only completed validated rows become comparable (the established v1.0 rule).
- Record the governed-data manifest (v1.0 pattern: asset type, resolved universe, date range, data span/fingerprint) in every run; never overwrite an optimization result.
- Pin solver/library versions at run time and record them.

**Warning signs:**
- Two identical inputs produce different outputs with no solver/version recorded.
- Failed runs vanish from history.
- The run record lacks an input snapshot hash.
- Cannot tell which factor revisions or data revision fed a portfolio.

**Phase to address:** Phase 11 (optimization run records) + Phase 12 (risk-model provenance) + Phase 13 (search/admission trails) — the catalog extension should land with the first new pipeline module (Phase 10/11 foundation) so later phases inherit it.

---

### Pitfall 12 (Integration): New Pipeline Bypasses the Governed Data Boundary

**What goes wrong:**
The new factor/portfolio/risk modules read Parquet/DuckDB directly (or copy market rows into SQLite) instead of going through the established governed loading boundary (`BacktestEngine.load_panel()`), so results are computed on inconsistent data and the platform's single-source-of-truth invariant is broken. This is the classic "adding a feature to an existing system" failure: the new module re-implements access instead of reusing the sanctioned seam.

**Why it happens:**
- v1.0 established `BacktestEngine.load_panel()` as the only governed read and the data-lake-first constraint (no raw market rows in SQLite, no second datastore).
- New modules need panel access for covariance, scoring, and backtesting, and it is easier to reach into the repository directly than to go through the loading boundary with manifest capture.

**How to avoid:**
- Route every new computation through the existing governed loading boundary; capture the governed manifest for every new run type.
- Store only metadata + artifact references in SQLite — never market rows.
- Add an import/read isolation test asserting the new modules cannot bypass the boundary (v1.0 already has this pattern for evaluation).
- Keep one research-artifacts store; do not create a second lake.

**Warning signs:**
- New code calls `repository`/`scan_parquet` directly instead of `load_panel`.
- Market data appears in SQLite.
- A second "research lake" directory appears.
- The same factor scores differ between the v1.0 evaluator and the new pipeline.

**Phase to address:** Phase 10/11 foundation — enforce the boundary when the first new module lands; all later phases (12-14) inherit it.

---

### Pitfall 13 (Integration): Divergent Implementations of the Same Computation Across Modules

**What goes wrong:**
IC in the factor library, expected returns in the optimizer, covariance in risk attribution, and weights in the plan are each computed by different code with different conventions (adjustment factors, NaN handling, universe), so stage outputs do not reconcile and an audit cannot trace one number to another. The pipeline "works" stage by stage but fails end to end.

**Why it happens:**
- Each new feature is added as an independent module (the platform's "independently activatable modules" constraint), and each module re-implements rather than imports the shared research math.
- No single source of truth for adjustment-factor convention, universe resolution, or missing-data policy across the pipeline.

**How to avoid:**
- Define a shared research-contract seam (governed panel loader + factor evaluator + metric definitions + manifest) that all new modules import (the milestone's "shared backtest/live signal chain" extended to research math).
- Each stage must record which upstream stage output (run ID, artifact) it consumed — lineage between factor evaluation → expected returns → covariance → weights.
- Add reconciliation checks: portfolio variance from risk attribution must equal the variance implied by the optimizer's covariance for the same weights; factor IC from the library must equal the factor scores used in the optimizer.

**Warning signs:**
- Factor IC from the library differs from factor scores used in the optimizer.
- Risk contributions do not reconcile to portfolio variance.
- Two modules use different NaN/adjustment-factor policies.
- Artifact lineage (which upstream run fed this stage) is missing.

**Phase to address:** Phase 10 (shared contract) enforced across Phases 11-13; reconciliation checks in Phase 12 (risk) and Phase 13 (walk-forward).

---

### Pitfall 14 (Integration): RebalancePlan Crossing Into Execution Authority

**What goes wrong:**
The new suggestion output (RebalancePlan) is wired into an existing action path — a portfolio mutation endpoint, a notification with an "apply" button, or an order-like record — violating the platform's core "no execution authority" boundary. Because the existing platform already has portfolio-mutation APIs, the risk is that the plan reuses them rather than remaining a research-only artifact.

**Why it happens:**
- The milestone's RebalancePlan naturally looks like an order (target weights, lots, cash), and the existing platform already has portfolio mutation endpoints.
- The "suggestions to auditable paper rebalance with NO execution authority" boundary is easy to blur when a UI button is added for convenience.

**How to avoid:**
- RebalancePlan is a research-only artifact: server-owned, immutable, carrying no execution route.
- Paper rebalance is a separate, auditable state machine (PA_Agent's ApprovalTicket pattern): explicit human approval, idempotency key, paper-only scope, and no route to live portfolio mutation.
- Authorization middleware rejects any execution intent on plan objects; UI renders the plan as a suggestion with expiry and blocked instruments, never with an "execute" affordance.
- Audit every plan → paper-rebalance transition as an append-only fact.

**Warning signs:**
- A plan object is accepted by a portfolio-update endpoint.
- A UI button offers to "apply" or "execute" the plan.
- SSE broadcasts a plan as an order.
- Plan records are mutable after creation.

**Phase to address:** Phase 14 — Output & Boundary. This is the phase's raison d'être; the no-execution-authority contract must be a hard acceptance criterion.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Silent PSD repair (eigenvalue clip / diagonal bump) | Solver "just works" | Risk numbers are wrong and unreproducible; attribution doesn't reconcile | **Never** — record method + epsilon in the run |
| Universe resolved from current instrument list | No PIT snapshot work | Survivorship bias in every historical result | Never for retained research |
| Max-Sharpe as default objective | Impressive-looking frontier | Overfit, unstable, concentrated weights | Only as explicit researcher choice with baselines |
| Reusing single-factor evaluator for multi-factor without a manifest | Fast to wire | No lineage; can't tell what fed the model | Only if the governed manifest is captured |
| Skipping lot-sizing, keeping continuous weights | Saves the adapter | Infeasible, non-executable plans | Never |
| Recording only successful runs | Cleaner history | Selection bias; no debugging context | Never — retain failed/cancelled with diagnostics |
| Trial count / search space not recorded | Less bookkeeping | Overstated OOS; un-auditable multiple comparisons | Never for retained search runs |
| Duplicate computation per module | Local convenience | Reconciliation failure; engine drift | Never — shared research-contract seam |
| Overlapping walk-forward folds to "use more data" | Larger effective test set | Leakage; optimistic OOS | Never |
| Solver defaults used silently | Fewer options to manage | Non-reproducible results | Never — record solver name/version/options |
| Plan doubles as an order | Fewer abstractions | Execution-authority leak | Never |

---

## Integration Gotchas

Common mistakes when connecting new features to the existing AthenaQuant system.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| v1.0 DSL compiler | Adding multi-factor operators without re-deriving partition context (`.over("date")`/`.over("symbol")`) | Every operator declares point-in-time semantics; versioned canonical DSL; leakage test on extension |
| v1.0 `BacktestEngine.load_panel()` boundary | New portfolio/risk modules read the repository/parquet directly | Route all market access through the governed loader; capture manifest; import-isolation test |
| v1.0 factor evaluator | Multi-factor model re-implements evaluation instead of composing stored factor revisions | Compose through the shared signal chain; record which revisions fed the model |
| v1.0 operational catalog | New run types (optimization, walk-forward, admissions) don't use the append-only catalog | Extend the catalog contract: input snapshot hash, solver, risk model, failures retained |
| v1.0 A-share matching layer (T+1/涨跌停/停牌/fees) | Walk-forward / plan path builds a naive second matcher | Reuse the existing matching layer; lot-sizing adapter only for plan discretization |
| v1.0 immutable artifacts store | New modules write their own files outside `research_artifacts` | Use the managed artifact store with relative paths + checksums; no second store |
| v1.0 frontend Backtest workspace + `api.ts`/query keys | New pages use a second request helper or global state | Extend the typed `api.ts` client and query-key factories; no second convention |
| LLM hypothesis gate | New multi-factor expressions bypass the parser/draft-review gate | All factor expressions go through the same validation → review → retention flow |
| Existing portfolio-mutation endpoints | RebalancePlan is wired to them | Plan is research-only; paper rebalance is a separate approved state machine |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Full-universe covariance over the whole A-share cross-section | Minutes-long solve, PSD failures, memory spikes | Ledoit-Wolf shrinkage, exponential weighting, blockwise estimation; cap universe | ~1000+ names daily; wide panels with suspensions |
| Monthly-robustness recompute over many candidates | LLM mining loop stalls; repeated full-history evaluation | Cache factor values; incremental per-month aggregation; sample-summary prefilter (FactorZoo pattern) | Thousands of candidate factors |
| Walk-forward folds reloading the panel per fold × parameter | Runtime explodes with grid size | Load panel once per fold; vectorized Polars evaluation; bound the parameter grid | Large grids (100s of cells) × many folds |
| Similarity dedup as full pairwise scan on every admission | O(n) growth in admission latency | AST structural signature + sample-summary similarity prefilter; exact check only on near matches | Factor library grows beyond a few thousand |
| ILP-based discrete allocation (e.g., `lp_portfolio`) | Solver dependency, slow for large universes | Greedy lot-sizing with recorded RMSE as default; ILP only on explicit request | Larger universes on the single-container deployment |
| Retained artifacts per run (weights, plans, curves) accumulating | `data_dir` fills; catalog queries slow | Managed relative paths + checksums in SQLite, artifacts on disk; retention policy for old runs | Hundreds of retained optimization runs |

---

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| DSL expression injection (import/exec/attribute access) | LLM-proposed factor executes arbitrary code | Closed whitelist parser; no `eval`/`pl.sql_expr`/dynamic lookup; sandboxed evaluation (v1.0 pattern) |
| Label/future fields reachable in the DSL field allowlist | Lookahead leak silently corrupts research | Field deny-list for labels; compiler partition context; leakage test |
| RebalancePlan treated as executable (authorization gap) | Research suggestion becomes a trade | Research-only plan; paper-rebalance state machine; server-owned authorization; no execution route |
| Artifact path traversal from run inputs | Read/write outside the managed artifact root | Managed relative paths; checksums; reject absolute/`..` paths (v1.0 artifact contract) |
| Serve-time data snapshot confusion | Rebalance suggestion computed on a different revision than validated | Fingerprint + serve-time manifest recorded in the plan |
| Failed runs deleted to "clean up" | Hides selection bias and debugging context | Retain failed/cancelled rows with diagnostics; only completed validated rows comparable |

---

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Re-labeling RankIC as a generic "IC" in the new multi-factor UI | Users misread signal strength; v1.0's IC=Pearson / RankIC=Spearman decision regresses | Keep separate explicit labels and metric families everywhere (v1.0 UI-SPEC contract) |
| Presenting optimizer output as "optimal" | Users over-trust an overfit, unstable portfolio | Show objective label, baseline comparison, weight-stability/sensitivity, and expected-return provenance |
| RebalancePlan without blocked instruments / expiry | Stale or unexecutable suggestions; users act on outdated plans | Visible blocked list, expiry date, cash, turnover, and lot counts |
| Walk-forward "OOS" presented as final truth | Users believe selection-biased numbers are validation | Label segments honestly: "selection-validation" vs "reserved OOS"; show fold layout |
| Hiding failed/cancelled optimization runs | No debugging path; selection bias invisible | Retain and render failed runs with diagnostics alongside completed ones |
| Monthly robustness collapsed to a single IC number | Users can't see the signal is a few hot months | Monthly IC series/chart with sign-consistency and worst-month visible |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Factor DSL extension:** new operators look right but partition context isn't re-derived — verify every operator declares per-date/per-symbol/pointwise semantics and the shifted-label leakage test passes.
- [ ] **Multi-factor evaluation:** pipeline composes factors — verify the governed manifest records which factor revisions and data revision fed the model (no lineage = not done).
- [ ] **Admission gates:** monthly robustness exists — verify the monthly window and thresholds are fixed policy constants, the candidate trail (including rejections) is recorded, and thresholds were not tuned post-hoc.
- [ ] **Covariance/PSD repair:** the optimizer solves — verify the repair method, epsilon, and eigenvalue before/after are in the immutable run record and risk attribution reconciles to portfolio variance.
- [ ] **Baseline objectives:** min-vol/HRP exist — verify they are the defaults and max-Sharpe is an explicit choice with baselines rendered.
- [ ] **Walk-forward:** folds are rolling — verify train/test windows are disjoint with a gap and a reserved OOS segment is evaluated exactly once and never touched by selection.
- [ ] **Parameter search:** a best config was found — verify trial count, search space, and score distribution are recorded and the final OOS was not used for selection.
- [ ] **RebalancePlan:** shows target weights — verify discrete 100-share lots, cash residue, blocked instruments, expiry, turnover cost, and discretization RMSE are present, and there is no execution route.
- [ ] **A-share matching:** backtest returns results — verify T+1, price limits, suspensions, and fees are enforced by the shared matching layer and no naive second matcher exists.
- [ ] **Audit catalog:** optimization runs persist — verify failed/cancelled runs with diagnostics are retained and input snapshot hash/solver version are recorded for every run.
- [ ] **Shared signal chain:** backtest and suggestion both work — verify they call the *same* factor implementation and produce identical values for the same as-of date.

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Lookahead / label leakage in a factor | HIGH | Re-run the shifted-label test across the catalog; quarantine affected revisions; re-derive results; admission gates re-checked from the candidate trail |
| Survivorship bias discovered | HIGH | Backfill point-in-time universe snapshots + delisted history; re-run evaluations/plans; mark prior results non-comparable (manifest mismatch warning) |
| IC robustness overfitting | MEDIUM | Re-run admission with fixed policy thresholds and the recorded candidate trail; report trial counts; only val-gated factors stay |
| Silent PSD repair shipped | MEDIUM | Re-run optimization with recorded risk model + explicit repair; reconcile risk attribution; keep prior run immutable |
| Max-Sharpe default contaminated results | MEDIUM | Re-run with baselines; keep max-Sharpe runs labeled high-risk; add weight-stability check |
| Walk-forward leakage found | HIGH | Rebuild folds with gaps + reserved OOS; re-run selection against val only; re-gate promotion |
| Parameter-search multiple comparisons | MEDIUM | Re-run with trial count + OOS discipline; report N alongside any claimed performance |
| Train/serve skew | MEDIUM | Unify on the shared signal chain; reissue the plan from the shared path; compare values |
| Execution-authority leak | HIGH | Remove the route; plan read-only; paper-rebalance state machine with approval; audit the transition |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Lookahead / label leakage in DSL | Phase 10 — Factor Library & Multi-Factor Model | Shifted-label test fails on lookahead factors; compiler partition-context contract pinned; field deny-list rejects labels |
| Survivorship bias / universe selection | Phase 10 (PIT universe contract); Phase 13 (per-fold universes) | Point-in-time universe snapshots exist; delisted history present; manifest records resolved universe + snapshot revision |
| IC robustness overfitting | Phase 10 — admission gates | Monthly IC sign-consistency/worst-month mandatory; fixed policy thresholds; candidate trail incl. rejections recorded |
| Covariance PSD failure / silent fix | Phase 12 — Risk models + PSD-repair provenance (feeds Phase 11) | Repair method + epsilon + eigenvalue before/after in immutable run; risk attribution reconciles to portfolio variance |
| Max-Sharpe default | Phase 11 — Portfolio Construction | Default objectives are min-vol/HRP; max-Sharpe explicit with baselines; weight-stability check present |
| A-share microstructure | Phase 14 — RebalancePlan lot-sizing + blocked instruments; Phase 13 reuses matching layer | Lot adapter produces 100-share plans; T+1/涨跌停/停牌 enforced; fees in expected cash; blocked list populated |
| Train/serve skew | Phase 13 — shared signal chain; Phase 14 — serve-time provenance | Same factor implementation in backtest and suggestion; values equal for same as-of date; manifest recorded in plan |
| Walk-forward leakage | Phase 13 — rolling folds + gap + reserved OOS | Fold boundaries disjoint with gap; reserved OOS evaluated once; fold layout recorded |
| Parameter-search multiple comparisons | Phase 13 — search bookkeeping + OOS discipline | Trial count, search space, score distribution recorded; final OOS untouched by selection |
| Continuous weights as orders | Phase 14 — RebalancePlan + paper-rebalance state machine | Discrete lots + cash + RMSE visible; no execution route; paper-only approval |
| Auditability gaps | Phase 11 (optimization run records); Phase 12 (risk provenance); Phase 13 (search trails) | Input snapshot hash, solver/version/options, failures retained; only completed validated rows comparable |
| Governed boundary bypass | Phase 10/11 foundation | Import-isolation test: new modules can only reach market data through `load_panel`; no market rows in SQLite |
| Divergent cross-module implementations | Phase 10 shared contract; enforced 11-13 | Reconciliation checks pass (IC library == optimizer scores; risk attribution == portfolio variance) |
| Execution-authority leak | Phase 14 — Output & Boundary | No plan→portfolio route; paper rebalance requires explicit human approval; plan immutable |

---

## Sources

- AlphaAgent `DEEP-ANALYSIS.md` (§4 factor evaluation, §7 DSL safety, §8 audit concerns — future-function operator tagging, monthly_ic_robustness, coverage/finite-count, AST+sample-summary similarity, panel manifest/hash) — HIGH confidence
- AlphaMaster `DEEP-ANALYSIS.md` (§4 walk-forward rolling folds + `WF_GAP=20`, OOS-not-blind warning, selection-bias audit fields; §6 shared signal chain + `max(MIN_BARS,500)` warm-up; §2 forward-fill and target-definition causality) — HIGH confidence
- PyPortfolioOpt `DEEP-ANALYSIS.md` (§2 max_sharpe variable-substitution caveat, min-vol/HRP baselines; §3 PSD repair is not data-quality proof; §4 DiscreteAllocation single-share default → A-share LotSizingAdapter; §6 immutable `PortfolioOptimizationRun` audit fields, long-only first release) — HIGH confidence
- Qlib `DEEP-ANALYSIS.md` (§5 SigAnaRecord IC/ICIR/RankIC/RankICIR; §8 data health + backtest exchange fees/slippage/limit-up-down/volume constraints; §10 audit rules) — HIGH confidence
- `10-SYNTHESIS.md` (quality gates, data contracts first, paper-only default, immutable local data lake, high-risk actions restricted) — HIGH confidence
- `07-策略与信号系统篇.md` (tickflow A-share matching: T+1/涨跌停/停牌/position cap/fees/slippage; QuantDinger strict_mode closed-bar/next-bar; Lean + PA_Agent Insight→target→risk→execution layering and ApprovalTicket paper state machine) — HIGH confidence
- AthenaQuant v1.0 phase artifacts: `02-RESEARCH.md`, `02-CONTEXT.md`, `02-VERIFICATION.md`, `02-UI-SPEC.md` (closed DSL + `.over("date")`/`.over("symbol")` partition contract, IC=Pearson/RankIC=Spearman decision, `BacktestEngine.load_panel` sole governed boundary, immutable catalog retaining failed/cancelled rows, governed-data manifest pattern) — HIGH confidence
- AthenaQuant `docs/ARCHITECTURE.md` and `.planning/codebase/ARCHITECTURE.md` (data-lake-first, SQLite operational state, single FastAPI host, independently activatable modules, existing backtest engine with A-share matching) — HIGH confidence
- AthenaQuant `.planning/PROJECT.md` (v1.2 milestone target features and constraints: no external DB/queue, no execution authority, rolling-not-expanding walk-forward, reserved OOS, stable objectives) — HIGH confidence

---
*Pitfalls research for: AthenaQuant v1.2 End-to-End Factor Portfolio Pipeline*
*Researched: 2026-07-31*
