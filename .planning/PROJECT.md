# AthenaQuant

## What This Is

AthenaQuant is a shipped, self-hosted quantitative research platform for individual A-share investors. Its v1.0 MVP unifies governed market data, portfolio monitoring, deterministic decision plans, factor and strategy research, evidence-grounded AI analysis, controlled advanced workflows, and independently activatable optional research modules.

## Core Value

An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.

## Current Milestone: v1.2 End-to-End Factor Portfolio Pipeline

**Goal:** Extend the research platform from single-factor evaluation into an auditable factor → portfolio → risk pipeline that outputs rebalance suggestions (no automated execution).

**Target features:**
- **Factor library & multi-factor model**: restricted factor DSL with whitelist parsing, IC/RankIC/ICIR/monthly-robustness evaluation, admission gates (train/val IC, no lookahead, no label leakage, similarity dedup), catalog+summary storage
- **Portfolio construction & optimization**: expected-return + covariance + constraints layering, stable objectives (min volatility / HRP) as baselines, long-only, per-instrument/industry caps, min cash, turnover cost, immutable optimization run records
- **Risk analysis & attribution**: risk models (sample/semi/exponential/Ledoit-Wolf + PSD repair), exposure, contribution, drawdown attribution
- **Deeper strategy research**: rolling walk-forward validation (not expanding, reserved independent OOS segment), parameter optimization & ensembling, shared backtest/live signal chain
- **Output & boundary**: RebalancePlan (target weights, A-share discrete lots, cash, turnover cost, blocked instruments, expiry), suggestions to auditable paper rebalance — no execution authority

## Success Metric

The v1.0 release is successful when all 23 requirements are verified end to end, the five phases pass Nyquist validation, and one provenance-bound final gate proves the backend and browser contracts against the frozen release source. This was achieved on 2026-07-27.

## Requirements

### Active

Building toward v1.2 (End-to-End Factor Portfolio Pipeline). Requirements are defined in `.planning/REQUIREMENTS.md`.

### Validated in v1.1

- [x] Release evidence is reproducible from a clean native-Linux checkout without historical attestations; real Windows/WSL execution is explicitly deferred and not claimed as verified (REL-01, approved scope override).
- [x] Runtime, data-stack, and frontend validation complete without avoidable deprecation or sortedness warnings (VAL-01).
- [x] Optional local-model supply remains fail-closed with a documented, testable operator provisioning command (SUP-01).
- [x] Critical desktop and 375px responsive workflows have durable screenshot-based visual regression evidence (VIS-01).

### Validated in v1.0

- [x] An investor can synchronize governed market data, maintain holdings, receive rule-based alerts, and inspect real-time updates from one deployment.
- [x] An investor can generate an auditable deterministic trade plan and distinguish it from bounded AI adjustments.
- [x] A researcher can create and evaluate factors and strategies against reproducible governed data.
- [x] An investor can assess AI-assisted research using visible data quality, numerical validation, and signal-lifecycle evidence.
- [x] An operator can use advanced agent and strategy workflows only within explicit authorization and sandbox controls.
- [x] Shadow Account strategy distillation and evaluation is independently activatable and research-only.
- [x] Investment-thesis tracking and evidence review preserves immutable lineage and human authority.
- [x] Kronos forecasting is local-only, provenance-bound, principal-scoped, and fail-closed when supply identity is incomplete.

### Validated in v1.2 Phase 10

- [x] FACT-01: Researcher can run factor admission gates (train/val IC threshold, no-lookahead, no-label-leakage, similarity dedup) with immutable append-only verdicts including rejections and candidate trail — Phase 10.
- [x] FACT-02: Factor evaluation reports ICIR, monthly robustness, and coverage alongside IC/RankIC with the full monthly evidence set exposed — Phase 10.
- [x] FACT-03: Researcher can compose admitted factors into a deterministic multi-factor expected-return model (equal-weight or IC-weighted cross-sectional z-score, no ML) — Phase 10.
- [x] FACT-04: DSL partition-context contract — every operator declares per-date/per-symbol/pointwise semantics, label fields denied, deterministic shifted-label leakage gate — Phase 10.
- [x] FACT-05: Admitted factors stored in an immutable catalog with summary storage (coverage, finite counts, signature) and revision lineage — Phase 10.
- [x] FACT-06: A single shared factor signal chain used identically by evaluation, multi-factor models, walk-forward, expected returns, and live as-of suggestions (no train/serve skew) — Phase 10.

### Validated in v1.2 Phase 12

- [x] RSK-01: Researcher can view risk exposure and marginal contribution attribution for an optimized portfolio, reconciling exactly to portfolio variance (hard cross-module assertion) — Phase 12.
- [x] RSK-02: Risk-model suite includes semi-covariance, exponentially weighted covariance, and Ledoit-Wolf shrinkage, each with explicit PSD-repair provenance — Phase 12.
- [x] RSK-03: Researcher can view drawdown attribution decomposed by instrument and time segment — Phase 12.

### Validated in v1.2 Phase 11

- [x] PFOL-01: Researcher can build sample covariance from a governed panel with explicit recorded PSD repair (method, epsilon, eigenvalues before/after) in the immutable run record — never silent — Phase 11.
- [x] PFOL-02: Researcher can solve a long-only minimum-volatility portfolio and an HRP baseline side by side; max-Sharpe is an explicit non-default option that always renders baselines alongside — Phase 11.
- [x] PFOL-03: Optimizer supports the constraint stack — long-only bounds, per-instrument cap, minimum cash, convex turnover cost — and industry cap fails closed until a governed industry mapping exists — Phase 11.
- [x] PFOL-04: Every optimization run is an immutable record carrying input-snapshot SHA-256, expected-return method, risk model, solver name/version/options, problem status, and output weights; failed runs retain their failure reason — Phase 11.

### Out of Scope

- Automated live broker order execution.
- A mandatory all-modules deployment; later capabilities remain independently activatable.
- External database or message queue dependencies in the Phase 1 Docker Compose deployment.

## Architecture Constraints

- **Runtime**: Phase 1 runs on Linux through one Docker Compose command as a single container, with no external database or message queue.
- **Data lake first**: Time-series market data is stored in Parquet and accessed through DuckDB and Polars. SQLite stores operational state such as positions, rules, and notification history.
- **Upstream synchronization**: Tickflow and PanWatch integrations retain a practical upstream synchronization path; changes must avoid fork-and-forget ownership.
- **Independent modules**: Integrated capabilities remain separately owned packages or domains that can be activated progressively rather than becoming an inseparable monolith.
- **Decision safety**: Hermes remains a core decision package. AI adjustments are field-bounded, direction-constrained, clamped or vetoed when invalid, audited, and comparable with a deterministic baseline and LLM-free replay.
- **Delivery sequence**: Preserve the source architecture's progression: core merger, factor and strategy research, AI analysis, advanced capabilities, then optional enhancements.

## Decision Status

v1.0 validated the host architecture and locked its safety boundaries: one FastAPI host, Parquet/DuckDB/Polars governed data, SQLite operational state, server-owned authorization and identity, append-only audit facts, bounded AI proposals, research-only promotion, and independently activatable optional modules. Future milestones may harden or simplify these seams but must not weaken their fail-closed behavior.

## Phase 10 Decisions (2026-08-01)

- **Shared signal chain is the only factor-value implementation** — `research/signal_chain.py` binds revision → one governed panel → cross-sectional values/rank/zscore; evaluation, composite models, walk-forward, expected returns, and live as-of suggestions all delegate to it (FACT-06 anti train/serve skew).
- **Hard-threshold admission gates** — fixed policy constants (train/val IC 0.02/0.01, similarity 0.80, IC-corr 0.90, shifted-label 0.02, coverage 0.50); temporal 70/30 date split; rejections recorded identically to admissions in append-only verdicts with candidate trail.
- **PIT universe membership table** — append-only `factor_universe_membership` in operational.db (no second datastore); per-date resolution filters AFTER the single `BacktestEngine.load_panel` seam; `membership_fingerprint` recorded in every manifest; `UniverseResolver` wired into `FactorEvaluationService` in main.py.
- **DSL partition-context contract** — `_FUNCTION_PARTITION` beside `_FUNCTION_ARITY`; `DENIED_FIELDS` explicit; `DSL_VERSION` bumped to factor-dsl-v2; shifted-label leakage test (IC must collapse ≤0.02) gates every DSL change.
- **Deterministic composite** — equal or IC-weighted (∝ catalog-recorded mean IC, NOT ICIR) cross-sectional z-score; no ML; snapshot-immutable output with `input_snapshot_sha256`; consumed by Phase 11 by snapshot.
- **Evaluation evidence** — ICIR = mean(monthly IC)/std(monthly IC), monthly robustness = positive-month share, coverage on resolved universe pre-filter; full monthly series in checksummed artifact; summary-only storage (no factor matrices).
- **scipy promoted to base deps** (`>=1.17.1,<1.18`, 1.18 needs Python ≥3.12 vs floor 3.11); sklearn stays shadow-extra lazy-imported; empty-.venv Wave 0 gate verified.

## Phase 11 Decisions (2026-08-01)

- **cvxpy 1.9.2 is the primary QP solver** — exact-pinned base dep (PyPI-verified; bundled OSQP/Clarabel/SCS/HiGHS); default solver CLARABEL with per-solver option namespaces (Clarabel `tol_gap_abs/tol_gap_rel`, OSQP `eps_abs/eps_rel`); `solver_stats` + importlib version captured in every run. scipy used only for HRP clustering, never as the general optimizer.
- **QP formulation** — `w = cp.Variable(nonneg=True)`; constraints `sum(w) == 1 - min_cash` (documented tested deviation from the floor: avoids degenerate all-cash min-vol) and `w <= cap`; objective `quad_form(w, Σ) + turnover_coef·‖w − w_prev‖₁`; PSD gate is a hard prerequisite for `cp.quad_form` (non-PSD → recorded failed run).
- **PSD repair never silent** — eigen-clip provenance (method/epsilon/eigenvalues before/after) mandatory in `risk_model_json`; optimizer fails closed without it.
- **Immutable run records** — `portfolio_optimization_runs` append-only table + no_update/no_delete triggers + CHECK enums (objective/expected_return_method/risk_model/problem_status) + `failed⇔failure_reason` invariant + sha256 length CHECK; weights as O_EXCL+fsync+sha256 artifacts.
- **max-Sharpe is explicit non-default** — rejected without `render_baselines=True`; when allowed, min-vol + HRP baselines are always recorded alongside; `optimal_inaccurate` is treated as non-optimal (recorded solver_error run, no weights persisted).
- **Snapshot binding fail-closed** — `portfolio/snapshot.py` loads the composite via `catalog.get_composite_model` → checksum-verified artifact → as_of cross-section; `run.input_snapshot_sha256 == factor_model_composites.input_snapshot_sha256`; never calls `build_composite`; as_of beyond panel coverage rejected as lookahead.
- **Constraint hardening** — solver-options whitelist enforced (unknown keys rejected); industry cap requested → recorded failed run 'industry mapping unavailable'; `created_at` = real UTC run time.

## Phase 12 Decisions (2026-08-01)

- **Exact variance reconciliation is a hard assertion** — `sum(MC) == wᵀΣw` at rtol 1e-12 enforced inside `attribution_report` before any evidence write; segment identity `Σc_i == segment_return` at rtol 1e-10 computed independently (never a tautology).
- **Four-model risk suite** — sample + semi-covariance + EWMA (λ=0.94) + Ledoit-Wolf via a single `make_risk_model_family` dispatcher; every model's PSD repair records method/epsilon/eigenvalues before/after; Ledoit-Wolf lazy-imports sklearn 1.8.0 at the risk-model boundary only (never module-top).
- **Covariance provenance in evidence** — every attribution evidence row carries `covariance_sha256` + `covariance_source` (`artifact` checksum-bound vs `recompute` from caller returns); tampered covariance raises `ArtifactReadError` with no evidence row.
- **Finiteness fail-closed** — `run_attribution`/`reconcile_all_models` reject non-finite returns; `underwater_curve` rejects returns ≤ −1.0 (equity NaN guard).
- **Drawdown attribution** — underwater curve → periods (module constants depth 2% / min 2 obs) → per-instrument × per-time-segment contributions with the segment-identity hard assertion; `run_drawdown` produces a full report + append-only evidence.
- **Append-only attribution evidence** — `portfolio_risk_attribution_evidence` table + no_update/no_delete triggers; FK → optimization runs; `risk_model` equality filter ready for Phase 15 API.

## Source Context

- Architecture source: `docs/ARCHITECTURE.md`
- Synthesized intake: `.planning/intel/SYNTHESIS.md`
- v1.0 milestone archive: `.planning/milestones/v1.0-ROADMAP.md`
- v1.0 canonical release audit: `.planning/milestones/v1.0-MILESTONE-AUDIT.md`
- v1.1 milestone archive: `.planning/milestones/v1.1-ROADMAP.md`

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-01 after Phase 12*
