---
phase: 14-output-boundary-(rebalanceplan-+-paper-rebalance)
plan: phase-plan
type: execute
requirements: [RBAL-01, RBAL-02]
wave_summary:
  wave_0: [14-02]
  wave_1: [14-01]
  wave_2: [14-03, 14-04]
  wave_3: [14-05]
must_haves:
  truths:
    - "Researcher can render a RebalancePlan from continuous Phase 11 optimizer weights through the A-share lot-sizing adapter — 100-share lots, odd-lot sell handling, cash residue, turnover cost, blocked instruments, expiry — as an immutable research-only artifact (O_EXCL + fsync + sha256) with discretization RMSE visible (RBAL-01)."
    - "The plan path REUSES the proven A-share matching rules from backtest/engine.py — the lot formula `floor(allocation / (price * (1 + cost)) / 100) * 100` (engine.py:1158) and the MatcherConfig fee model (buy_cost_pct/sell_cost_pct) — never a naive second matcher."
    - "Researcher can approve or reject a rebalance suggestion in the paper-rebalance state machine; every transition (suggested/approved/rejected/filled) is an append-only audit fact and approve/reject/fill are idempotent (RBAL-02)."
    - "Paper fills NEVER write positions and no execution route exists anywhere — no broker/order/submit/place_order path in the plan or paper modules, no INSERT INTO positions from paper.py (hard acceptance criterion, Phase 14 success criterion 3)."
    - "Every RebalancePlan binds its Phase 11 optimization run via optimization_run_id + input_snapshot_sha256 and reads back checksum-verified from its artifact (audit contract)."
    - "Phase 15 can surface plans and paper state through the read/list repository surface (get/list rebalance plans, list paper transitions, derived current state)."
  artifacts:
    - path: backend/app/portfolio/rebalance.py
      provides: "RebalancePlan dataclass, discretize_weights (cash-aware largest-weight-first lot-sizing adapter: engine.py lot formula + MatcherConfig fees, odd-lot sell, cash residue, blocked instruments, turnover cost, RMSE simple/weighted), build_rebalance_plan (run weights → plan artifact → rebalance_plans row), load_rebalance_plan (checksum-verified read)"
    - path: backend/app/portfolio/paper.py
      provides: "create_suggestion / approve / reject / paper_fill — the append-only paper-rebalance state machine (suggested/approved/rejected/filled) with idempotency and expired-plan fail-closed; paper fills write ONLY paper_rebalance_transitions, never positions"
    - path: backend/app/portfolio/repository.py
      provides: "record_rebalance_plan / get_rebalance_plan / list_rebalance_plans / record_paper_transition / get_paper_state / list_paper_transitions — append-only, UNIQUE (plan_id, transition) idempotency, IntegrityError→ValueError"
    - path: backend/app/operational/migrations.py
      provides: "ONE appended script creating rebalance_plans + paper_rebalance_transitions — append-only + no_update/no_delete triggers + UNIQUE (plan_id, transition) idempotency (per the approved one-way-door decision)"
    - path: backend/tests/portfolio/conftest.py
      provides: "fixture_rebalance_run (recorded optimal Phase 11 run with output_weights + artifact namespace), fixture_prices, fixture_plan_inputs (blocked set, equity, MatcherConfig), fixture run/paper doubles"
    - path: backend/tests/portfolio/test_rebalance.py
      provides: "RBAL-01 unit + integration — lot floor matches engine.py, odd-lot sell, cash residue, turnover cost reference, blocked exclusion, expiry, RMSE simple/weighted reference, run fail-closed, checksum-verified read, reporting breadth"
    - path: backend/tests/portfolio/test_paper.py
      provides: "RBAL-02 state-machine cases — suggestion→approve→fill audit ledger, idempotent approve/reject/fill, reject terminal, expired fail-closed, no-execution-route regression gate"
    - path: backend/tests/test_operational_migrations.py
      provides: "rebalance_plans + paper_rebalance_transitions schema CHECKs, immutability triggers, FK integrity, UNIQUE idempotency, forward-only idempotence"
  key_links:
    - from: portfolio/rebalance.py
      to: backtest/engine.py
      via: "MatcherConfig.buy_cost_pct()/sell_cost_pct() + the `floor(allocation / (price * (1 + cost)) / 100) * 100` lot formula (engine.py:1158) — REUSE, never a second matcher"
      pattern: "discretize_weights"
    - from: portfolio/rebalance.py
      to: portfolio/repository.py
      via: "get_optimization_run(run_id).output_weights (fail-closed on non-optimal, mirroring analyzer.py:92-95) → record_rebalance_plan(optimization_run_id, input_snapshot_sha256, ...)"
      pattern: "build_rebalance_plan"
    - from: portfolio/rebalance.py
      to: portfolio/artifacts.py
      via: "PortfolioArtifactService.write_analysis_artifact(run_id, subdir='rebalance', filename=f'rebalance-{plan_id}.json', ...) — O_EXCL + fsync + sha256; row binds output_sha256 + artifact_relative_path; read side checksum-verified via read_artifact"
      pattern: "write_analysis_artifact"
    - from: portfolio/paper.py
      to: portfolio/repository.py
      via: "record_paper_transition (UNIQUE (plan_id, transition) idempotency) + get_paper_state (derived from the max-ordinal transition row) — every transition is an append-only audit fact"
      pattern: "paper_fill"
    - from: portfolio/paper.py
      to: portfolio/rebalance.py
      via: "paper_fill consumes RebalancePlan discrete lot_sizes + prices through MatcherConfig fees and records paper_position_delta_json — NEVER INSERT INTO positions (no execution route)"
      pattern: "paper_fill"
    - from: portfolio/repository.py
      to: operational/migrations.py
      via: "UNIQUE (plan_id, transition) enforces transition idempotency; no_update/no_delete triggers make the audit ledger immutable; FK rebalance_plans.optimization_run_id → portfolio_optimization_runs"
      pattern: "record_paper_transition"
---

# Phase 14: Output & Boundary (RebalancePlan + Paper Rebalance) — Executable Plan

## Phase Goal

Researchers can render an immutable A-share RebalancePlan from continuous optimizer weights and land suggestions in an auditable paper-rebalance state machine — with zero execution authority as a hard acceptance criterion.

## Scope

**In scope (RBAL-01..02):** an immutable RebalancePlan rendered from continuous Phase 11 optimizer weights through a **lot-sizing adapter** that REUSES the proven A-share matching layer in `backtest/engine.py` (the `floor(… / 100) * 100` lot formula at engine.py:1158 and the `MatcherConfig` fee model — `buy_cost_pct()`/`sell_cost_pct()`) — 100-share lots, odd-lot sell handling, cash residue, turnover cost, researcher-provided blocked instruments, `expires_at` expiry, and discretization RMSE visible in the plan artifact; suggestions land in an auditable **paper-rebalance state machine** (suggestion → human approve/reject → paper fill) where every transition is an append-only audit fact with idempotency. The plan is an immutable research-only artifact (O_EXCL + fsync + sha256) bound to its Phase 11 run via `optimization_run_id` + `input_snapshot_sha256`. **Zero execution authority is a hard acceptance criterion** — no API endpoint, UI affordance, or service path can push a RebalancePlan to a live broker, and paper fills never write positions.

**Out of scope:** live broker execution (forever out of scope — platform boundary since v1.0); writing real positions from paper fills (never — research-only); auto-rebalance scheduling (v2); frontend panels (Phase 15). Deferred ideas from `14-CONTEXT.md` MUST NOT appear in any task. No execution routes anywhere.

## Source Coverage Audit

| Source | ID | Required behavior or constraint | Plans | Status |
|---|---|---|---|---|
| GOAL | Phase 14 | Immutable A-share RebalancePlan from continuous optimizer weights through a lot-sizing adapter; auditable paper-rebalance state machine; zero execution authority (hard acceptance) | 14-01..14-05 | COVERED |
| REQ | RBAL-01 | RebalancePlan from continuous weights via A-share lot-sizing adapter — 100-share lots, odd-lot sell, cash residue, turnover cost, blocked instruments, expiry — immutable research-only artifact with discretization RMSE visible | 14-01, 14-02, 14-03, 14-05 | COVERED |
| REQ | RBAL-02 | Suggestions land in an auditable paper-rebalance state machine (append-only audit fact, human approval, idempotency) with no execution route anywhere | 14-01, 14-02, 14-04, 14-05 | COVERED |
| CONTEXT | Lot-Sizing Adapter | Reuse `backtest/engine.py` matching layer (T+1, limits, suspension, 100-share lots, fees) — do NOT build a naive second matcher; continuous weights → 100-share lots with odd-lot sell + cash residue; discretization RMSE visible | 14-01, 14-03 | COVERED |
| CONTEXT | RebalancePlan Structure | Continuous → discrete lot weights; discretization RMSE exposed; turnover cost, `blocked_instruments`, `expires_at`, target weights (continuous + discrete); immutable research-only artifact (O_EXCL + fsync + sha256) | 14-01, 14-02, 14-03, 14-05 | COVERED |
| CONTEXT | Paper-Rebalance State Machine | suggestion → human approve/reject → paper fill (PA_Agent ApprovalTicket pattern); every transition an append-only audit fact with idempotency; paper fill does NOT write real positions; no execution route anywhere | 14-01, 14-02, 14-04 | COVERED |
| CONTEXT | Inputs & Binding | Input = Phase 11 optimization run weights + Phase 13 validated strategies, bound by `input_snapshot_sha256`; cash / blocked instruments provided explicitly by the researcher; consumed via snapshot (artifact + sha256), never live module hand-off | 14-01, 14-05 | COVERED |
| CONTEXT | Claude's Discretion | Exact lot-sizing algorithm (cash-aware largest-weight-first), RMSE definition (simple vs weighted), state-machine transition names (suggested/approved/rejected/filled), new append-only table schemas (rebalance_plans + paper_rebalance_transitions), `expires_at` default (now + 7 calendar days) | 14-01..14-05 | COVERED |
| CODE | Migrations | New append-only tables rebalance_plans + paper_rebalance_transitions — one-way-door schema decision | 14-02 | COVERED (checkpoint:decision) |
| CODE | Artifacts | O_EXCL + fsync + sha256 plan artifact; checksum-verified read | 14-01, 14-05 | COVERED |
| CODE | No execution | Paper fills never write positions; no broker/order/submit path anywhere | 14-01, 14-04 | COVERED |

**Exclusions (not gaps):** deferred ideas in `14-CONTEXT.md` (live broker execution, auto-rebalance scheduling v2, real positions from paper fills, frontend Phase 15); Phase 15 API/frontend panels; live execution is forever out of scope (platform boundary since v1.0).

## Plan List

- [ ] 14-01: **Tracer** — end-to-end RebalancePlan → paper-rebalance slice on a fixture: Phase 11 run weights → lot-sizing adapter (100-share lots, odd-lot sell, cash residue, turnover, blocked, expiry, RMSE) → immutable artifact + rebalance_plans row → suggestion → approve → paper fill with append-only audit (RBAL-01 + RBAL-02 spine)
- [ ] 14-02: **Wave 0 foundations** — one-way-door checkpoint for rebalance_plans + paper_rebalance_transitions, migration script + tests, PortfolioRepository rebalance/paper methods, Wave 0 test scaffolding (test_rebalance.py + test_paper.py + conftest fixtures)
- [ ] 14-03: **Lot-sizing adapter breadth** — odd-lot liquidation, cash residue floor, turnover cost reference, RMSE simple/weighted, blocked/expiry breadth (RBAL-01)
- [ ] 14-04: **Paper-rebalance state machine breadth** — reject path, expired fail-closed, no-execution-route regression gate (RBAL-02)
- [ ] 14-05: **Robustness + reporting breadth** — read/list surface for Phase 15, run fail-closed + checksum-verified read (RBAL-01/02)

## Wave Structure

| Wave | Plans | Purpose |
|------|-------|---------|
| 0 | 14-02 | Foundations: append-only rebalance_plans + paper_rebalance_transitions migration (one-way-door checkpoint) + repo methods + Wave 0 test scaffolding — prerequisites for the tracer. |
| 1 | 14-01 | The tracer: prove the whole RebalancePlan → paper-rebalance spine end-to-end on a fixture before any breadth. |
| 2 | 14-03, 14-04 | Lot-sizing adapter breadth (rebalance.py) and paper state-machine breadth (paper.py) — disjoint files, parallel. |
| 3 | 14-05 | Robustness + reporting breadth (needs both breadth plans). |

## Artifacts this phase produces

| Artifact | Kind | Provides |
|---|---|---|
| `RebalancePlan` / `discretize_weights` / `build_rebalance_plan` / `load_rebalance_plan` (portfolio/rebalance.py) | dataclass + functions | the A-share lot-sizing adapter — cash-aware largest-weight-first discretization reusing the engine.py lot formula + MatcherConfig fee model; odd-lot sell, cash residue, turnover cost, blocked instruments, expiry, RMSE (simple/weighted); the immutable plan artifact (O_EXCL + fsync + sha256) and the rebalance_plans row (RBAL-01) |
| `create_suggestion` / `approve` / `reject` / `paper_fill` (portfolio/paper.py) | functions | the paper-rebalance state machine — suggestion → human approve/reject → paper fill; every transition an append-only audit fact with idempotency; paper fills write ONLY paper_rebalance_transitions, never positions (RBAL-02) |
| rebalance_* / paper_* repository methods (portfolio/repository.py) | methods | record_rebalance_plan / get_rebalance_plan / list_rebalance_plans / record_paper_transition / get_paper_state / list_paper_transitions — append-only, UNIQUE (plan_id, transition) idempotency, IntegrityError→ValueError |
| rebalance_plans + paper_rebalance_transitions (operational/migrations.py) | SQLite tables | append-only plan + transition ledger with CHECKs, no_update/no_delete triggers, FK to portfolio_optimization_runs, UNIQUE idempotency (per the approved one-way-door decision) |
| tests/portfolio/{test_rebalance, test_paper}.py + conftest.py | test files | per-requirement unit contracts + the end-to-end tracer proof + the state-machine / no-execution-gate cases + the fixture-run / prices / plan-input fixtures |
| tests/test_operational_migrations.py (extend) | migration tests | rebalance_plans + paper_rebalance_transitions schema CHECKs, immutability triggers, FK integrity, UNIQUE idempotency, forward-only idempotence |

## Requirement → Plan Mapping

| Requirement | Behavior | Plans | Verification command |
|---|---|---|---|
| RBAL-01 | RebalancePlan via lot-sizing adapter — 100-share lots, odd-lot sell, cash residue, turnover cost, blocked instruments, expiry, immutable artifact, RMSE visible | 14-01, 14-02, 14-03, 14-05 | `cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py -x` |
| RBAL-02 | Paper-rebalance state machine — append-only audit fact, human approval, idempotency, no execution route | 14-01, 14-02, 14-04, 14-05 | `cd backend && .venv/bin/python -m pytest tests/portfolio/test_paper.py -x` |
| Schema | rebalance_plans + paper_rebalance_transitions + triggers + UNIQUE idempotency | 14-02 | `cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short` |

All commands run from `backend/` with the project interpreter: `cd backend && .venv/bin/python -m pytest …`.

---

# Plan 14-01 — Tracer: End-to-End RebalancePlan → Paper-Rebalance Slice on a Fixture (RBAL-01 + RBAL-02)

**wave:** 1 · **depends_on:** [14-02] · **autonomous:** true
**requirements:** [RBAL-01, RBAL-02]
**files_modified:**
- backend/app/portfolio/rebalance.py (new)
- backend/app/portfolio/paper.py (new)
- backend/tests/portfolio/test_rebalance.py (extend — tracer proof)
- backend/tests/portfolio/test_paper.py (extend — tracer proof)

## Objective

Prove the complete Phase 14 spine on a fixture, end to end, before any breadth: load a recorded Phase 11 optimization run (`get_optimization_run` → `output_weights`, fail-closed on missing/non-optimal) → run the **lot-sizing adapter** `discretize_weights` (cash-aware largest-weight-first; `floor(allocation / (price * (1 + cost)) / 100) * 100` — the engine.py:1158 lot formula REUSED, never a second matcher; odd-lot sell, cash residue, turnover cost, researcher-provided blocked instruments, `expires_at` default now + 7 calendar days, RMSE visible) → write the immutable plan artifact (`PortfolioArtifactService.write_analysis_artifact(run_id, subdir="rebalance", …)` — O_EXCL + fsync + sha256) and INSERT the append-only `rebalance_plans` row binding `optimization_run_id` + `input_snapshot_sha256` + `output_sha256` → land the suggestion in the **paper-rebalance state machine** (`create_suggestion` → `approve` → `paper_fill`), every transition an append-only `paper_rebalance_transitions` fact with idempotency, and the paper fill writes ONLY that ledger — never a position row (no execution route).

Purpose: This is the milestone's boundary keel. It forces the engine.py-lot-formula reuse, the O_EXCL + fsync + sha256 artifact discipline, the run-bound audit contract, and the append-only idempotent paper state machine into existence on the first commit — and catches a dead-end (a second matcher, a writable position path, a non-immutable artifact, an idempotency hole) before breadth is committed. Functionality is fixture-scoped (recorded `fixture_rebalance_run` + deterministic prices + MatcherConfig + tmp_path repository + artifact root); no architectural gap is left.
Output: `portfolio/rebalance.py` (adapter + plan builder), `portfolio/paper.py` (state machine), the `rebalance_plans` + `paper_rebalance_transitions` records, and the green tracer tests that lock the contracts.

## Context

- @.planning/phases/14-output-boundary-(rebalanceplan-+-paper-rebalance)/14-CONTEXT.md — locked decisions: reuse engine.py matching layer (no second matcher); RebalancePlan structure (continuous → discrete weights, RMSE exposed, turnover cost, blocked_instruments, expires_at); immutable research-only artifact (O_EXCL + fsync + sha256); paper state machine (suggestion → approve/reject → paper fill, append-only audit fact, idempotency, no execution route); inputs bound by input_snapshot_sha256; discretion (lot algorithm, RMSE definition, transition names, expires_at default)
- backend/app/backtest/engine.py — `MatcherConfig` (`buy_cost_pct()` L69-71, `sell_cost_pct()` L73-76 — commission + stamp + slippage) + the lot formula at L1158 (`shares = np.floor(allocation / (entry_price * (1 + buy_cost_pct)) / 100) * 100`) — the REUSED A-share rules
- backend/app/portfolio/repository.py — `get_optimization_run` (L168-173, output_weights unwrapped), `record_optimization_run` (L112-166), `_record` JSON unwrap (L54-71) — the Phase 11 run row is the input boundary (its `input_snapshot_sha256` covers the composite-model snapshot; Phase 13 validated strategies are UPSTREAM of the optimizer, not directly consumed by the plan)
- backend/app/portfolio/analyzer.py — fail-closed run gate (L92-95: no output_weights / non-optimal → ValueError) + non-finite fail-closed (L117-118) — the contract `build_rebalance_plan` mirrors
- backend/app/portfolio/artifacts.py — `PortfolioArtifactService.write_analysis_artifact` (L135-169, O_EXCL + fsync + sha256 inside the run's existing namespace) + `read_artifact` (L111-131, checksum-verified)
- backend/app/operational/migrations.py — the 14-02 rebalance_plans + paper_rebalance_transitions tables + PortfolioRepository methods (from 14-02)
- backend/tests/portfolio/conftest.py — `fixture_attribution_run` (L146-198, the recorded-optimal-run pattern `run_optimization(..., fixture_mode=True)`) + `portfolio_repository` + `artifact_root` + `FIXTURE_SYMBOLS` — the tracer fixture mirrors it
- backend/tests/portfolio/test_rebalance.py + test_paper.py (from 14-02 RED scaffold)

## Tasks

- **build: Create `portfolio/rebalance.py` — RebalancePlan + `discretize_weights` + `build_rebalance_plan`**
  - Files: backend/app/portfolio/rebalance.py
  - Read first: backend/app/backtest/engine.py `MatcherConfig` (L32-76, buy/sell cost pct) + `simulate_portfolio._process_entries` (L1158, the lot formula), backend/app/portfolio/analyzer.py (L92-95 + L117-118, fail-closed contracts), backend/app/portfolio/artifacts.py `write_analysis_artifact` (L135-169), backend/app/portfolio/repository.py `get_optimization_run` (L168-173)
  - Action: Module docstring states know/don't-know per CONVENTIONS.md (knows: A-share lot discretization of continuous weights, plan artifact + row; does NOT know: solving, risk models, execution, the live portfolio, API/frontend — the docstring must NOT contain the tokens `broker` / `submit` / `place_order` / `live_` so the no-execution grep gate stays clean). Import `MatcherConfig` from `app.backtest.engine` (REUSE). Implement the frozen, slots dataclass `RebalancePlan(plan_id, optimization_run_id, input_snapshot_sha256, as_of, target_weights, discrete_weights, lot_sizes, cash_residue, turnover_cost, blocked_instruments, discretization_rmse, rmse_definition, expires_at, output_sha256, artifact_relative_path, created_at)` and `DiscretizationResult`. Implement `discretize_weights(*, target_weights, prices, equity, matcher_config, blocked, odd_lot_positions=None, min_cash=0.0, rmse_definition="simple") -> DiscretizationResult`: (1) excluded = symbols in `blocked` (recorded verbatim, discrete weight 0); (2) process the remaining symbols in DESCENDING target-value order (cash-aware largest-weight-first, deterministic tie-break by symbol); per symbol `shares = floor(allocation / (price * (1 + matcher_config.buy_cost_pct())) / 100) * 100` — the engine.py L1158 formula, no re-derivation; stop when cash runs out; (3) odd-lot sell — a symbol whose `odd_lot_positions[sym]` shares % 100 != 0 with target < 1 board lot is sold in full (the odd remainder is sellable in A-shares); with target ≥ 1 lot the sell leg carries the odd remainder when reducing below the current full-lot count; (4) cash residue = `equity - Σ share_i * price_i * (1 + buy_cost_pct)` — never reallocated, recorded; (5) turnover cost = Σ buy_value·buy_cost_pct + Σ sell_value·sell_cost_pct (REUSE the MatcherConfig model); (6) RMSE over the FULL universe incl. blocked: `simple` = `sqrt(mean((w_cont − w_disc)²))`, `weighted` = `sqrt(mean(w_cont·(w_cont − w_disc)²))`; non-finite weights fail closed (mirror analyzer L117-118). Implement `build_rebalance_plan(*, run_id, prices, equity, matcher_config, blocked, expires_at=None, repository: PortfolioRepository, artifact_service_root: Path) -> RebalancePlan` — load the run via `repository.get_optimization_run(run_id)`, fail closed (missing / `problem_status != "optimal"` / empty `output_weights` → ValueError, mirroring analyzer L92-95), bind `input_snapshot_sha256` from the run row, discretize, `expires_at` default `now + 7 calendar days`, write the artifact via `PortfolioArtifactService(artifact_service_root).write_analysis_artifact(run_id, subdir="rebalance", filename=f"rebalance-{plan_id}.json", payload=plan_dict)` (O_EXCL + fsync + sha256), then `repository.record_rebalance_plan(...)` binding `output_sha256` + `artifact_relative_path`. No execution route — this module only renders a research plan.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py -q --tb=short` (the Wave 0 scaffold cases turn green)
  - Done: the lot formula matches engine.py's `floor(.../100)*100` exactly; blocked symbols carry zero discrete weight and are recorded; cash residue is deterministic; RMSE is deterministic and recorded with `rmse_definition`; the plan artifact is O_EXCL + fsync + sha256 and the rebalance_plans row binds `output_sha256` + `artifact_relative_path` + `input_snapshot_sha256`.

- **build: Create `portfolio/paper.py` — the paper-rebalance state machine + no-execution contract**
  - Files: backend/app/portfolio/paper.py
  - Read first: backend/app/operational/migrations.py `forecast_job_transitions` (L1332-1374, the append-only transition-ledger + monotonic-trigger pattern), backend/app/portfolio/repository.py `record_paper_transition` + `get_paper_state` (from 14-02), 14-CONTEXT.md `## Paper-Rebalance State Machine` (suggestion → human approve/reject → paper fill, append-only audit fact, idempotency, no execution route)
  - Action: Module docstring states know/don't-know + the explicit boundary contract "paper fills are research-only audit facts — this module NEVER writes positions and exposes NO execution route" (worded WITHOUT the tokens `broker` / `submit` / `place_order` / `live_` / `INSERT INTO positions` so the grep gate stays clean). Implement `create_suggestion(plan_id, *, repository) -> dict` — records the `suggested` transition (idempotent: an existing `suggested` row returns it); fail closed if the plan is missing or expired. Implement `approve(plan_id, *, repository, idempotency_key) -> dict` — the human approval gate; only valid from the `suggested` state (a `rejected` or `filled` plan raises); expired plans fail closed; idempotent (a repeated approve of the same plan returns the existing `approved` row when `idempotency_key` matches). Implement `reject(plan_id, *, repository, idempotency_key) -> dict` — terminal `rejected` transition, mutually exclusive with `approved`. Implement `paper_fill(plan_id, *, repository, prices, matcher_config) -> dict` — only from the `approved` state; values the plan's discrete `lot_sizes` at `prices` through `matcher_config` fees (REUSE the MatcherConfig model), records the `filled` transition whose `paper_position_delta_json` = {symbol: shares}; the ONLY table this module ever writes is `paper_rebalance_transitions`. No method named `execute` / `submit` / `place_order`; no import of any broker/live client; no `INSERT INTO positions`.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_paper.py -q --tb=short` (the Wave 0 scaffold cases turn green)
  - Done: suggestion → approve → fill each append one audit fact in ordinal order; re-approve / re-reject / re-fill are idempotent (same transition returns the existing row); reject is terminal and mutually exclusive with approve; expired plans fail closed; paper_fill writes ONLY `paper_rebalance_transitions`.

- **test: End-to-end tracer proof — `tests/portfolio/test_rebalance.py` + `test_paper.py`**
  - Files: backend/tests/portfolio/test_rebalance.py, backend/tests/portfolio/test_paper.py
  - Read first: the 14-02 RED scaffold cases in both files, backend/tests/portfolio/conftest.py (`fixture_rebalance_run` + `fixture_prices` + `fixture_plan_inputs`), backend/app/portfolio/rebalance.py + portfolio/paper.py (modules under test)
  - Action: Write one integration test walking the full spine on a fixture: `fixture_rebalance_run` (a recorded optimal run via `run_optimization(..., fixture_mode=True)` mirroring `fixture_attribution_run`) → `build_rebalance_plan` (discretize → write_analysis_artifact → rebalance_plans row) → assert RMSE / lots / cash_residue / turnover_cost / blocked / expires_at on the returned plan → `create_suggestion` → `approve` (second approve returns the same row — idempotent) → `paper_fill` → assert the append-only transition ledger (suggested → approved → filled ordinals), the paper `position_delta_json` equals the discrete lots, and NO position row was written (`SELECT COUNT(*) FROM positions` is unchanged before/after; `grep -c "INSERT INTO positions" backend/app/portfolio/paper.py` == 0). Also assert the module surface has no execution methods (`approve`/`reject`/`paper_fill`/`create_suggestion` are the ONLY public transitions).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -q --tb=short`
  - Done: the full run-weights → lot-sizing → plan artifact → suggestion → approve → paper-fill path works end-to-end on a fixture with the no-execution gate asserted — the Phase 14 spine is proven before any breadth plan starts.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -q --tb=short
```

All green. **No-execution-route gate** (hard acceptance criterion): `grep -vE '^\s*(#|""")' app/portfolio/rebalance.py app/portfolio/paper.py | grep -cE '\b(broker|submit|place_order|live_)\b'` == 0; `grep -c "INSERT INTO positions" app/portfolio/paper.py` == 0; `grep -c "INSERT INTO" app/portfolio/paper.py` == 0 (raw SQL is absent — all writes route through `repository.record_paper_transition`; the transition INSERT lives in repository.py). `load_panel`/parquet never appear in the plan path — the adapter imports only `MatcherConfig` from `backtest/engine.py` (no second matcher).

## Success Criteria

- A RebalancePlan renders from a recorded Phase 11 run through the engine.py-lot-formula adapter with 100-share lots, odd-lot sell handling, cash residue, turnover cost, researcher-provided blocked instruments, `expires_at` default (now + 7d), and discretization RMSE visible — as an O_EXCL + fsync + sha256 artifact with the rebalance_plans row binding `optimization_run_id` + `input_snapshot_sha256` + `output_sha256`.
- The paper-rebalance state machine lands suggestion → approve → fill as append-only idempotent audit facts; reject is available; paper fills never write positions.
- The no-execution-route grep gate passes — the boundary holds on the first commit.

---

# Plan 14-02 — Wave 0: rebalance_plans + paper_rebalance_transitions Migration, Repo Methods, Test Scaffolding

**wave:** 0 · **depends_on:** [] · **autonomous:** false (one one-way-door checkpoint:decision gate)
**requirements:** [RBAL-01, RBAL-02]
**files_modified:**
- backend/app/operational/migrations.py
- backend/tests/test_operational_migrations.py
- backend/app/portfolio/repository.py
- backend/tests/portfolio/conftest.py (extend — fixture_rebalance_run / fixture_prices / fixture_plan_inputs)
- backend/tests/portfolio/test_rebalance.py (new — RED scaffold)
- backend/tests/portfolio/test_paper.py (new — RED scaffold)

## Objective

Land the irreversible foundations every other plan builds on: the two append-only tables `rebalance_plans` + `paper_rebalance_transitions` in the existing operational.db migration sequence — the one-way schema door the phase's audit + no-execution contract rests on — the `PortfolioRepository` rebalance/paper methods, and the base test scaffolding (2 new test files + conftest fixtures) that 14-01/14-03/14-04/14-05 turn green. The one-way-door decision (new append-only tables) is gated behind an explicit `checkpoint:decision` task BEFORE any implementation — per the reversibility contract this is `one-way` (undoing requires a follow-up migration that breaks the Phase 14 contract).

Purpose: Every later plan assumes these tables, this repo surface, and these test files exist. Wave 0 is the only place the migration sequence advances and the only place the Phase 14 audit contract (`UNIQUE (plan_id, transition)` idempotency, append-only triggers, FK to `portfolio_optimization_runs`) is pinned.
Output: the two tables migrated with CHECKs + triggers, the approved schema decision applied, the rebalance/paper repo methods, 2 new test files + conftest fixtures, and the migration test coverage.

> **Execution order:** tasks run 1 → 2 → **4** → 3. Task 3's Verify (`pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py`) targets the test files scaffolded in task 4 — those files must exist first, so scaffold (task 4) precedes the repo-method verify (task 3). Task 4's scaffold asserts RED until the task-3 methods land; task 3's verify then turns the repo-touching cases green.

## Context

- @.planning/phases/14-output-boundary-(rebalanceplan-+-paper-rebalance)/14-CONTEXT.md — locked decisions: append-only plan + transition records, idempotency, no execution route; Claude's Discretion: new append-only table schemas (rebalance_plans + paper_rebalance_* audit facts) following existing conventions
- backend/app/operational/migrations.py — the `MIGRATIONS` tuple (the Phase 13 wf_* script is the last entry, ending at the tuple close L1812-1813); `migrate_operational_db` applies atomically with `PRAGMA user_version`
- backend/app/research/repository.py — the IntegrityError→ValueError analog (create_experiment L365-368); portfolio/repository.py has `_json` (L47-52), `_record` (L54-71), `record_optimization_run` (L112-166) — the new rebalance/paper methods introduce the IntegrityError→ValueError mapping fresh (no existing analog in portfolio/repository.py)
- backend/tests/test_operational_migrations.py — the Phase 11/13 runs-table/wf-table tests (the pattern for the rebalance/paper cases)
- backend/tests/portfolio/conftest.py — `portfolio_repository` + `artifact_root` + `fixture_attribution_run` (L146-198, the recorded-run fixture pattern to mirror for `fixture_rebalance_run`)

## Tasks

- **checkpoint:decision — Approve the two append-only Phase 14 tables (one-way door)**
  - Decision: Land the two Phase 14 tables — `rebalance_plans` + `paper_rebalance_transitions` — in `operational/migrations.py` as ONE new migration script appended to the `MIGRATIONS` tuple (advancing `PRAGMA user_version` for the shared operational.db), with the CHECK constraints, `no_update`/`no_delete` triggers, and indexes per the schema below.
  - Context: This is a one-way door: the migration advances the user_version for every operational.db consumer, undoing requires a follow-up migration, and Phase 15 (RebalancePlan panels) builds on these audit records. The tables are MANDATED by the append-only contract (a RebalancePlan and every paper transition are immutable facts) and by the idempotency + no-execution boundary (RBAL-01/02). Both tables share one script so the FK graph (`rebalance_plans.optimization_run_id → portfolio_optimization_runs`, `paper_rebalance_transitions.plan_id → rebalance_plans`) is created in a single atomic step.
  - Options:
    - option-a: ONE migration script with both tables — `rebalance_plans` (id TEXT PK, optimization_run_id TEXT NOT NULL REFERENCES portfolio_optimization_runs(id) ON DELETE RESTRICT, input_snapshot_sha256 TEXT NOT NULL CHECK length 64, as_of TEXT NOT NULL, target_weights_json TEXT NOT NULL, discrete_weights_json TEXT NOT NULL, lot_sizes_json TEXT NOT NULL, cash_residue REAL NOT NULL, turnover_cost REAL NOT NULL, blocked_instruments_json TEXT NOT NULL, discretization_rmse REAL NOT NULL, rmse_definition TEXT NOT NULL CHECK (rmse_definition IN ('simple','weighted')), expires_at TEXT NOT NULL, output_sha256 TEXT NOT NULL CHECK length 64, artifact_relative_path TEXT NOT NULL, created_at TEXT NOT NULL); `paper_rebalance_transitions` (id INTEGER PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES rebalance_plans(id) ON DELETE RESTRICT, transition TEXT NOT NULL CHECK (transition IN ('suggested','approved','rejected','filled')), idempotency_key TEXT NOT NULL, previous_state TEXT, paper_position_delta_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE (plan_id, transition)); indexes `idx_rebalance_plans_run(optimization_run_id)`, `idx_paper_transitions_plan(plan_id)`; `_no_update`/`_no_delete` triggers on both. Pros: one atomic schema step; FK graph intact; idempotency enforced at the DB; matches the append-only convention exactly. Cons: a single larger script.
    - option-b: Two scripts — (1) rebalance_plans, (2) paper_rebalance_transitions. Pros: smaller incremental steps; the paper ledger can be deferred if the plan table proves insufficient. Cons: two user_version advances; the FK from paper_rebalance_transitions → rebalance_plans spans scripts; more surface for drift.
  - **APPROVED 2026-08-01 (user): option-a — ONE migration script with both tables.** Resume signal: option-a

- **build: Append the Phase 14 migration script (+ the two tables per the approved option) + extend migration tests**
  - Files: backend/app/operational/migrations.py, backend/tests/test_operational_migrations.py
  - Read first: backend/app/operational/migrations.py (the last MIGRATIONS entry — the Phase 13 wf_* script — and the tuple close at L1812), backend/tests/test_operational_migrations.py (the Phase 13 wf-table test conventions)
  - Action: Append ONE new SQL script to the `MIGRATIONS` tuple per the approved option. Per the schema above: `rebalance_plans` with the CHECKs (rmse_definition enum, sha256 lengths), the FK to `portfolio_optimization_runs` (ON DELETE RESTRICT), and `_no_update`/`_no_delete` triggers; `paper_rebalance_transitions` with the `transition` enum CHECK, the `UNIQUE (plan_id, transition)` idempotency key, the FK to `rebalance_plans` (ON DELETE RESTRICT), and `_no_update`/`_no_delete` triggers; the two indexes. Mirror the Phase 13 trigger wording (`'... are append-only'`). Extend `tests/test_operational_migrations.py`: schema CHECKs (rmse_definition / transition enums fire), UPDATE/DELETE on either table raises (triggers), FK integrity (orphan plan/run rejected), UNIQUE idempotency (a duplicate (plan_id, transition) is rejected), forward-only idempotence (re-migrate is a no-op).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short`
  - Done: both tables migrate atomically with the CHECKs/FKs/triggers/indexes; UPDATE/DELETE on either raises; the UNIQUE (plan_id, transition) fires; the migration is forward-only idempotent.

- **build: Extend `PortfolioRepository` with the rebalance_plans + paper_rebalance_transitions methods**
  - Files: backend/app/portfolio/repository.py
  - Read first: backend/app/research/repository.py create_experiment (L365-368, the IntegrityError→ValueError analog) + backend/app/portfolio/repository.py `_json` (L47-52) + `_record` (L54-71) + `record_optimization_run` (L112-166) + `_connection` context manager, the Phase 14 schema (the 14-02 migration above)
  - Action: Add the append-only methods, each taking a short-lived connection like the existing ones: `record_rebalance_plan(**fields) -> dict` — validates `input_snapshot_sha256`/`output_sha256` (64-hex), `rmse_definition` enum, `expires_at` present; canonical-JSON via `_json` for target_weights_json / discrete_weights_json / lot_sizes_json / blocked_instruments_json; INSERT; `sqlite3.IntegrityError` → `ValueError` (duplicate plan or missing run). `get_rebalance_plan(plan_id) -> dict | None` — SELECT with the four JSON columns unwrapped (extend `_record` or add `_record_rebalance`). `list_rebalance_plans(*, run_id=None, limit=200) -> list[dict]` — ORDER BY created_at DESC, id; positive-int limit fail-closed (limit=0 raises ValueError, per 13-05 pattern); optional run_id filter. `record_paper_transition(**fields) -> dict` — INSERT into paper_rebalance_transitions; on the `UNIQUE (plan_id, transition)` violation, if the stored `idempotency_key` matches the incoming one return the EXISTING row (idempotent — the state machine's repeated approve/reject/fill contract), else raise `ValueError`; any other IntegrityError (missing plan) raises. `get_paper_state(plan_id) -> str | None` — derive the current state from the MAX-ordinal transition row (the append-only ledger read — mirror the `forecast_job_transitions` derivation). `list_paper_transitions(*, plan_id=None, transition=None, limit=200) -> list[dict]` — ORDER BY id; unwrap `paper_position_delta_json`; positive-int limit fail-closed.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -q --tb=short` (the repo-touching RED cases turn green where the methods exist; idempotency + IntegrityError cases pass)
  - Done: rebalance_plans round-trips with unwrapped JSON; a duplicate plan raises ValueError; paper transitions are idempotent on (plan_id, transition) with a matching idempotency_key and raise otherwise; `get_paper_state` derives the current state from the ledger; list paths filter and cap at limit.

- **test: Scaffold the new test files + conftest fixtures (Wave 0 gaps)**
  - Files: backend/tests/portfolio/conftest.py, backend/tests/portfolio/test_rebalance.py, backend/tests/portfolio/test_paper.py
  - Read first: backend/tests/portfolio/conftest.py `fixture_attribution_run` (L146-198) + `portfolio_repository` + `artifact_root` (the recorded-run fixture pattern), 14-CONTEXT.md (the RBAL-01/02 contracts to encode as RED assertions)
  - Action: Extend `tests/portfolio/conftest.py`: `fixture_rebalance_run` — a recorded optimal run via `run_optimization(..., fixture_mode=True)` on the fixture composite (mirroring `fixture_attribution_run`), returning the run dict (weights + artifact namespace); `fixture_prices` — deterministic {symbol: price} for `FIXTURE_SYMBOLS`; `fixture_plan_inputs` — a dataclass-ish dict {equity, blocked, matcher_config: MatcherConfig, odd_lot_positions} with a blocked symbol and one odd-lot position so odd-lot sell is testable. Create `tests/portfolio/test_rebalance.py` (RED scaffold): lot-floor vs engine.py formula reference, blocked exclusion, cash residue, RMSE reference, expires_at default, artifact + row binding, run fail-closed. Create `tests/portfolio/test_paper.py` (RED scaffold): suggestion→approve→fill ledger, idempotency, reject terminal, expired fail-closed, no-execution gate. Both files' cases assert the Phase 14 contracts against modules/functions that do not exist yet — provably RED.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -q --tb=short` — expected failures (RED) until 14-01/14-03/14-04 land
  - Done: the 2 new test files exist with the Phase 14 contracts; conftest provides `fixture_rebalance_run` + `fixture_prices` + `fixture_plan_inputs`; the scaffolds are provably RED (failing on the missing modules/functions) — the exact tests 14-01/14-03/14-04/14-05 turn green.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short
cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -q --tb=short   # expected RED (scaffolds) until 14-01
```

The two tables migrate with their constraints and triggers; the 2 new test files are scaffolded RED with shared fixtures. **No-execution-route gate** (hard acceptance — applies to the repo surface): `grep -vE '^\s*(#|""")' app/portfolio/repository.py | grep -cE '\b(broker|submit|place_order|live_)\b'` == 0; the rebalance/paper methods write ONLY `rebalance_plans` / `paper_rebalance_transitions` — no `positions` INSERT appears in the new methods.

## Success Criteria

- The two append-only tables migrate atomically per the approved one-way-door option, with the UNIQUE (plan_id, transition) idempotency key, the transition/rmse_definition enums, immutability triggers, and FK integrity to `portfolio_optimization_runs`.
- The PortfolioRepository rebalance/paper methods are append-only, idempotent on repeated transitions, IntegrityError→ValueError mapped, and expose the derived paper state.
- The 2 new test files + conftest fixtures are scaffolded RED — the exact tests 14-01/14-03/14-04/14-05 turn green.

---

# Plan 14-03 — Lot-Sizing Adapter Breadth (RBAL-01)

**wave:** 2 · **depends_on:** [14-01] · **autonomous:** true
**requirements:** [RBAL-01]
**files_modified:**
- backend/app/portfolio/rebalance.py (extend — odd-lot sell + cash residue + turnover + RMSE breadth)
- backend/tests/portfolio/test_rebalance.py (extend — green breadth cases)

## Objective

Harden the lot-sizing adapter from the tracer's happy path to the full RBAL-01 surface: exact odd-lot sell handling (a symbol with an odd-lot position selling down below one board lot carries the odd remainder — legal in A-shares; a full exit sells the entire position incl. the odd lot), deterministic cash-residue flooring (never reallocated; min_cash respected), a turnover-cost contract that matches the hand-computed reference from `MatcherConfig` fees (zero on a no-change plan), blocked-instrument exclusion, the `expires_at` default window, and the discretization RMSE under both definitions (`simple` / `weighted`) — with non-finite weights failing closed.

Purpose: RBAL-01's "100-share lots, odd-lot sell handling, cash residue, turnover cost, blocked instruments, expiry, RMSE visible" is only trustworthy when each edge is a locked green test, not an incidental behavior of the happy path.
Output: adapter breadth in `rebalance.py`, green `test_rebalance.py` breadth cases.

## Context

- @.planning/phases/14-output-boundary-(rebalanceplan-+-paper-rebalance)/14-CONTEXT.md — locked decisions: continuous weights → 100-share lots with odd-lot sell + cash residue; turnover cost; blocked instruments; expiry; RMSE visible; discretion: lot-sizing algorithm details (cash-aware largest-weight-first vs remainder ordering), RMSE definition (weighted vs simple), expires_at default window
- backend/app/backtest/engine.py — `MatcherConfig.buy_cost_pct()`/`sell_cost_pct()` (L65-76) + the L1158 lot formula — the REUSED A-share rules the breadth cases assert against
- backend/app/portfolio/rebalance.py (from 14-01) — `discretize_weights` + `build_rebalance_plan`
- backend/tests/portfolio/test_rebalance.py (from 14-02 RED scaffold) + conftest `fixture_plan_inputs` / `fixture_prices` / `fixture_rebalance_run`

## Tasks

- **build: Odd-lot sell + cash-residue breadth in `rebalance.py`**
  - Files: backend/app/portfolio/rebalance.py
  - Read first: backend/app/backtest/engine.py L1158 (the buy lot formula) + L946-982 (`_sell` — the exit path), 14-CONTEXT.md `## Lot-Sizing Adapter` (odd-lot sell + cash residue)
  - Action: Harden `discretize_weights`: (1) odd-lot sell — a symbol whose `odd_lot_positions[sym]` shares % 100 != 0 with target weight 0 is sold in FULL (the odd remainder included — selling odd lots is legal in A-shares; buying is not); with a target ≥ 1 board lot, the sell leg computes `floor(current/100) − floor(target/100)` board-lot deltas and the odd remainder is carried when the target falls below the current full-lot count (a reduce-from-250→150 sell sells 100 as the board lot and keeps the 50-lot residue only if the target still requires ≥ 1 lot — otherwise the whole odd position is sold); (2) cash residue — `equity − Σ share_i·price_i·(1 + buy_cost_pct)` recorded and NEVER reallocated, with `min_cash` respected (a plan that would breach `min_cash` leaves the excess in residue rather than forcing a partial lot); (3) determinism — symbols processed in DESCENDING target-value order with a stable symbol tie-break; weights rounded to 8 decimals (mirror `optimizer._finalize_result` L346-349); no float-iteration drift.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py -q --tb=short`
  - Done: odd-lot liquidation and cash-residue flooring are exact and deterministic, with unit cases locking each edge (full-odd-lot exit, reduce-below-one-lot, min_cash breach).

- **build: Turnover-cost + RMSE breadth in `rebalance.py`**
  - Files: backend/app/portfolio/rebalance.py
  - Read first: backend/app/backtest/engine.py `MatcherConfig` (L65-76), 14-CONTEXT.md `## RebalancePlan Structure` (turnover cost, RMSE exposed; discretion: RMSE weighted vs simple)
  - Action: (1) turnover cost — accumulate the buy leg `Σ buy_value·buy_cost_pct` + the sell leg `Σ sell_value·sell_cost_pct` from the REUSED `MatcherConfig` model; zero on a no-change plan (identical current/target lots); recorded as `turnover_cost`; (2) RMSE — `simple` = `sqrt(mean((w_cont − w_disc)²))` over the FULL universe incl. blocked (blocked contributes honestly — its discrete weight is 0); `weighted` = `sqrt(mean(w_cont·(w_cont − w_disc)²))`; `rmse_definition` recorded; both fail closed on non-finite weights (mirror analyzer L117-118 — never silent).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py -q --tb=short`
  - Done: turnover_cost matches the hand-computed reference from MatcherConfig fees; RMSE matches the manual reference for both definitions; non-finite weights raise ValueError.

- **test: Turn the `test_rebalance.py` breadth cases green**
  - Files: backend/tests/portfolio/test_rebalance.py
  - Read first: the 14-02 RED cases, backend/app/portfolio/rebalance.py (module under test), conftest `fixture_plan_inputs` / `fixture_prices` / `fixture_rebalance_run`
  - Action: Make the scaffolded cases pass and add: (1) lot floor — `discretize_weights` lots equal the engine.py formula reference `floor(allocation / (price * (1 + buy_cost_pct)) / 100) * 100` for every symbol; (2) odd-lot full-exit and reduce-below-one-lot; (3) cash residue — the recorded residue equals the hand-computed remainder and is never reallocated; min_cash breach leaves excess in residue; (4) blocked — a blocked symbol has discrete weight 0 and appears in `blocked_instruments`; (5) expiry — default `expires_at` = now + 7 calendar days (and a caller-provided value is honored); (6) RMSE simple/weighted references; (7) turnover cost reference + zero on no-change; (8) deterministic tie-break (same inputs → identical output twice).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py -q --tb=short`
  - Done: the RBAL-01 contract — engine.py lot formula reuse, odd-lot sell, cash residue, turnover cost, blocked instruments, expiry, and RMSE under both definitions — is locked by green tests.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py -q --tb=short
```

All green. Grep gate (no-execution-route, hard acceptance): `grep -vE '^\s*(#|""")' app/portfolio/rebalance.py app/portfolio/paper.py | grep -cE '\b(broker|submit|place_order|live_)\b'` == 0; `grep -c "INSERT INTO positions" app/portfolio/paper.py` == 0. The only lot arithmetic in `rebalance.py` is the engine.py formula (`grep -n "floor" app/portfolio/rebalance.py` references the single `floor(.../100)*100` expression); no `load_panel` / parquet path (no second matcher).

## Success Criteria

- The lot-sizing adapter produces exact 100-share lots from the engine.py formula, with deterministic odd-lot sell handling and cash residue that is never reallocated (min_cash respected).
- Turnover cost matches the MatcherConfig fee reference (zero on no-change); RMSE is recorded under the chosen definition and fails closed on non-finite weights.
- Blocked instruments are excluded and recorded; `expires_at` defaults to now + 7 calendar days.

---

# Plan 14-04 — Paper-Rebalance State Machine Breadth (RBAL-02)

**wave:** 2 · **depends_on:** [14-01] · **autonomous:** true
**requirements:** [RBAL-02]
**files_modified:**
- backend/app/portfolio/paper.py (extend — reject path + expired fail-closed + no-execution contract)
- backend/tests/portfolio/test_paper.py (extend — green breadth cases)

## Objective

Complete the RBAL-02 state-machine surface: the reject path (terminal, mutually exclusive with approve), expired-plan fail-closed on every post-creation transition, and the **no-execution-route regression gate** — an automated test that locks the hard acceptance criterion (no broker/order/submit/place_order vocabulary, no `INSERT INTO positions`, no execution-named method) so the boundary cannot silently regress.

Purpose: RBAL-02's "human approval, idempotency, no execution route anywhere" is a hard acceptance criterion — it must be a locked test, not a docstring promise.
Output: reject/expiry breadth in `paper.py`, the no-execution regression gate, green `test_paper.py` breadth cases.

## Context

- @.planning/phases/14-output-boundary-(rebalanceplan-+-paper-rebalance)/14-CONTEXT.md — locked decisions: suggestion → human approve/reject → paper fill; every transition an append-only audit fact with idempotency; paper fill does NOT write real positions; no execution route anywhere (hard acceptance)
- backend/app/portfolio/paper.py (from 14-01) — `create_suggestion` / `approve` / `reject` / `paper_fill`
- backend/app/portfolio/repository.py (from 14-02) — `record_paper_transition` (UNIQUE idempotency) + `get_paper_state`
- backend/tests/portfolio/test_paper.py (from 14-02 RED scaffold) + conftest fixtures

## Tasks

- **build: Reject path + expired-plan fail-closed in `paper.py`**
  - Files: backend/app/portfolio/paper.py
  - Read first: 14-CONTEXT.md `## Paper-Rebalance State Machine`, backend/app/portfolio/repository.py `get_paper_state` (from 14-02), backend/app/portfolio/paper.py (from 14-01)
  - Action: Complete the state machine: (1) `reject` — only valid from the `suggested` state, terminal (`rejected`), idempotent (a repeated reject of the same plan returns the existing row when `idempotency_key` matches); a plan can never be both `approved` and `rejected` — the repository `get_paper_state` guard + the UNIQUE transition key raise on the conflicting transition; (2) expired fail-closed — every post-creation transition (`approve` / `reject` / `paper_fill`) compares `now` against the plan's `expires_at` and raises `ValueError("rebalance plan expired at ...")` when `now > expires_at` (the plan itself is already immutable; a new suggestion requires a NEW plan); (3) `paper_fill` values the discrete lots at prices through `matcher_config` fees and records `paper_position_delta_json` — the ONLY table written is `paper_rebalance_transitions`.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_paper.py -q --tb=short`
  - Done: reject is terminal and mutually exclusive with approve; approve/reject/fill on an expired plan raise ValueError; the ledger remains append-only.

- **build: No-execution-route regression gate (locked test + grep)**
  - Files: backend/app/portfolio/paper.py, backend/tests/portfolio/test_paper.py
  - Read first: 14-CONTEXT.md `## Paper-Rebalance State Machine` (no execution route — hard acceptance), backend/app/portfolio/paper.py (module under test), backend/tests/portfolio/test_paper.py (the scaffolded gate cases)
  - Action: Add a `test_no_execution_route` regression test that (1) inspects `paper.py` + `rebalance.py` source (via `inspect.getsource`) and asserts there is NO `INSERT INTO positions`, NO `import broker` / `requests` / `websocket` / live-client import, and NO method named `execute` / `submit` / `place_order` (grep the module `__dict__` for public callables); (2) asserts `paper.py` contains NO raw `INSERT INTO` at all — all writes route through `repository.record_paper_transition`, whose only INSERT targets `paper_rebalance_transitions` (assert the repository.py INSERT statement too); (3) runs a full suggestion→approve→fill on the fixture and asserts the `positions` table row count is unchanged (SELECT COUNT(*) before/after). Keep the module docstrings worded WITHOUT the gate tokens (`broker` / `submit` / `place_order` / `live_` / `INSERT INTO positions`) so the grep gate is self-consistent — the denial is phrased as "research-only audit facts", "never writes positions", "zero execution authority".
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_paper.py -q --tb=short`
  - Done: the zero-execution-authority contract is locked by an automated regression test + grep gate — the boundary cannot regress silently.

- **test: Turn the `test_paper.py` breadth cases green**
  - Files: backend/tests/portfolio/test_paper.py
  - Read first: the 14-02 RED cases, backend/app/portfolio/paper.py (module under test), conftest `fixture_rebalance_run` + `fixture_prices` + `fixture_plan_inputs`
  - Action: Make the scaffolded cases pass and add: (1) full ledger — suggestion→approve→filled with increasing ordinals and `previous_state` recorded per transition; (2) idempotency — a second approve / re-reject / re-fill of the same plan returns the existing row (matching idempotency_key) and raises on a mismatched key; (3) reject-then-approve raises; (4) fill-before-approve raises; (5) expired-approve / expired-fill raise ValueError; (6) paper fill values the discrete lots at prices with MatcherConfig fees and `paper_position_delta_json` == {symbol: shares}; (7) the no-execution gate (above) passes.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_paper.py -q --tb=short`
  - Done: the RBAL-02 contract — append-only idempotent transitions, human approve/reject, terminal reject, expired fail-closed, and zero execution authority — is locked by green tests.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/portfolio/test_paper.py -q --tb=short
```

All green. **No-execution-route gate** (hard acceptance criterion): `grep -vE '^\s*(#|""")' app/portfolio/paper.py app/portfolio/rebalance.py | grep -cE '\b(broker|submit|place_order|live_)\b'` == 0; `grep -c "INSERT INTO positions" app/portfolio/paper.py` == 0; `grep -c "INSERT INTO" app/portfolio/paper.py` == 0 (raw SQL is absent — all writes route through `repository.record_paper_transition`; the transition INSERT lives in repository.py).

## Success Criteria

- Approve/reject/fill each append one idempotent audit fact; reject is terminal and mutually exclusive with approve; expired plans fail closed.
- Paper fills value the discrete lots and write ONLY `paper_rebalance_transitions`.
- The no-execution-route regression gate + grep gate pass — zero execution authority is a locked, testable contract.

---

# Plan 14-05 — Robustness + Reporting Breadth (RBAL-01/02)

**wave:** 3 · **depends_on:** [14-03, 14-04] · **autonomous:** true
**requirements:** [RBAL-01, RBAL-02]
**files_modified:**
- backend/app/portfolio/repository.py (extend — read/list reporting breadth)
- backend/app/portfolio/rebalance.py (extend — run fail-closed + checksum-verified read)
- backend/tests/portfolio/test_rebalance.py (extend — green breadth cases)
- backend/tests/portfolio/test_paper.py (extend — green breadth cases, if needed)

## Objective

Harden the boundary layer from the tracer's happy path to the full robustness + reporting surface: the read/list reporting APIs Phase 15 consumes (`get_rebalance_plan` / `list_rebalance_plans` with filters / `list_paper_transitions` / derived `get_paper_state`), the fail-closed run gate (missing / non-optimal / empty-output-weights runs raise — mirroring analyzer L92-95), the checksum-verified plan-artifact read (`read_artifact(relative_path, checksum_sha256=output_sha256)` — an ArtifactReadError on mismatch), and the input-snapshot binding integrity (`input_snapshot_sha256` taken from the run row, never recomputed). Phase 15 surfaces plans + paper state via this surface.

Purpose: RBAL-01/02's audit contract is only trustworthy when the read side verifies bytes and the run gate fails closed; the reporting breadth is what Phase 15 (RebalancePlan panels) consumes.
Output: reporting read/list breadth in `repository.py`, fail-closed + checksum-verified read in `rebalance.py`, green breadth tests.

## Context

- @.planning/phases/14-output-boundary-(rebalanceplan-+-paper-rebalance)/14-CONTEXT.md — locked decisions: inputs bound by input_snapshot_sha256; consumed via snapshot (artifact + sha256), never live module hand-off; immutable research-only artifact
- backend/app/portfolio/repository.py (from 14-02) — get/list rebalance plans + paper transitions + get_paper_state
- backend/app/portfolio/artifacts.py — `read_artifact` (L111-131, checksum-verified read) + `ArtifactReadError`
- backend/app/portfolio/analyzer.py — L92-95 (missing run / empty output_weights → ValueError) + L117-118 (non-finite fail-closed) — the gate `build_rebalance_plan` mirrors
- backend/tests/portfolio/test_rebalance.py + test_paper.py (green cases from 14-03/14-04)

## Tasks

- **build: Read/list reporting breadth in `repository.py`**
  - Files: backend/app/portfolio/repository.py
  - Read first: backend/app/portfolio/repository.py (from 14-02) + the Phase 13 `list_wf_folds` / `list_validated_strategies` breadth pattern (limit fail-closed, filters), 14-CONTEXT.md `## Integration Points` (Phase 15 surfaces plans + paper state via typed API)
  - Action: Extend the read surface: (1) `list_rebalance_plans(*, run_id=None, limit=200)` — add the `run_id` filter + unwrap all four JSON columns; ORDER BY created_at DESC, id; positive-int limit fail-closed (limit=0 raises ValueError per 13-05); (2) `list_paper_transitions(*, plan_id=None, transition=None, limit=200)` — add the `transition` filter; unwrap `paper_position_delta_json`; ORDER BY id; limit fail-closed; (3) `get_paper_state(plan_id)` — return the derived current state ('suggested' / 'approved' / 'rejected' / 'filled' / None) from the max-ordinal transition row; (4) `get_rebalance_plan(plan_id)` returns the FULL unwrapped record (all JSON columns) for the Phase 15 panel.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -q --tb=short`
  - Done: get/list round-trips with unwrapped JSON; filters (run_id / plan_id / transition) and limit fail-closed; `get_paper_state` derives the current state from the ledger.

- **build: Run fail-closed + checksum-verified read in `rebalance.py`**
  - Files: backend/app/portfolio/rebalance.py
  - Read first: backend/app/portfolio/analyzer.py L92-95 (missing / empty-output_weights → ValueError) + L117-118, backend/app/portfolio/artifacts.py `read_artifact` (L111-131) + `ArtifactReadError`, backend/app/portfolio/repository.py `get_optimization_run`
  - Action: (1) `build_rebalance_plan` fails closed when the run is missing, `problem_status != "optimal"`, or `output_weights` is empty — a clear `ValueError` (mirroring analyzer L92-95); bind `input_snapshot_sha256` from the run row (NEVER recomputed — consumed via snapshot, not live hand-off); (2) add `load_rebalance_plan(plan_id, *, repository, artifact_service_root) -> dict` — reads the rebalance_plans row, loads the artifact bytes via `PortfolioArtifactService(artifact_service_root).read_artifact(relative_path, checksum_sha256=output_sha256)`, and returns the plan record + verified bytes; a checksum mismatch / missing file raises `ArtifactReadError`; (3) `blocked_instruments` recorded verbatim in the row so the plan audit shows exactly what was excluded.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py -q --tb=short`
  - Done: missing / non-optimal / empty-weight runs raise; the plan artifact reads back checksum-verified (mismatch → ArtifactReadError); input_snapshot_sha256 binds the Phase 11 run.

- **test: Breadth — reporting, run gate, checksum, state**
  - Files: backend/tests/portfolio/test_rebalance.py, backend/tests/portfolio/test_paper.py
  - Read first: the green cases in both files, conftest fixtures, backend/app/portfolio/repository.py + rebalance.py (modules under test)
  - Action: Add to `test_rebalance.py`: (1) run fail-closed — a missing run_id raises ValueError; a `problem_status != "optimal"` run raises; an empty-output-weights run raises; (2) checksum-verified read — `load_rebalance_plan` returns verified bytes; a tampered artifact file raises `ArtifactReadError`; (3) reporting — `list_rebalance_plans(run_id=...)` filters; `limit=0` raises ValueError; `get_rebalance_plan` unwraps all JSON columns; blocked_instruments round-trips verbatim. Add to `test_paper.py`: (4) `get_paper_state` returns the derived state after each transition (suggested → approved → filled; rejected terminal); (5) `list_paper_transitions(transition="approved")` filters; limit fail-closed.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -q --tb=short`
  - Done: the RBAL-01/02 robustness contract — fail-closed run gate, checksum-verified artifact read, reporting filters + limit fail-closed, derived paper state, verbatim blocked_instruments — is locked by green tests.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -q --tb=short
```

All green. Grep gate (no-execution-route, hard acceptance): `grep -vE '^\s*(#|""")' app/portfolio/rebalance.py app/portfolio/paper.py | grep -cE '\b(broker|submit|place_order|live_)\b'` == 0; `grep -c "INSERT INTO positions" app/portfolio/paper.py` == 0; `grep -c "INSERT INTO" app/portfolio/paper.py` == 0 (raw SQL absent — writes route through `repository.record_paper_transition`). `read_artifact` is the ONLY artifact read in `rebalance.py` (checksum-verified — no raw `read_bytes` in the plan path); `input_snapshot_sha256` appears only as a binding read from the run row (never recomputed).

## Success Criteria

- The read/list reporting surface (get/list rebalance plans with filters, list paper transitions, derived paper state) supports the Phase 15 panel.
- Missing / non-optimal / empty-weight runs fail closed; the plan artifact reads back checksum-verified (mismatch raises ArtifactReadError).
- `blocked_instruments` and `input_snapshot_sha256` are recorded verbatim — the plan audit shows exactly what was excluded and what it was bound to.

---

# Consolidated Threat Model

> `workflow.security_enforcement: true` (config.json) — section required. Trust model: local single-user research host; no new auth/session surface (ASVS V2/V3 N/A). New records are server-issued only (V4 minimal). Strict DTOs + enum validation (V5); SHA-256 checksums for snapshot/artifact binding (V6). **Zero execution authority is the phase's cardinal invariant** — no broker/order/submit path anywhere.

## Trust Boundaries

| Boundary | Description |
|---|---|
| Phase 11 run → RebalancePlan | Continuous weights cross from `portfolio_optimization_runs.output_weights` via `get_optimization_run`; `build_rebalance_plan` fails closed on missing/non-optimal runs and binds `input_snapshot_sha256` from the run row. |
| Continuous weights → discrete lots | The lot-sizing adapter crosses weights through the REUSED engine.py formula (`floor(.../100)*100`) + MatcherConfig fees — never a second matcher; RMSE between continuous and discrete weights is recorded. |
| Plan → artifact + rebalance_plans row | The plan artifact crosses as O_EXCL + fsync + sha256 bytes (`write_analysis_artifact`); the row binds `output_sha256` + `artifact_relative_path`; the read side is checksum-verified (`read_artifact`). |
| Suggestion → paper state machine | Human approve/reject/fill cross as append-only `paper_rebalance_transitions` facts with `UNIQUE (plan_id, transition)` idempotency; expired plans fail closed. |
| Paper fill → boundary | Paper fills value discrete lots and write ONLY the transition ledger — never `positions`; no execution route exists anywhere (hard acceptance criterion). |

## STRIDE / ASVS L1 Traceability

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|---|---|---|---|---|---|
| T-14-01 | Tampering | Plan artifact tampering / snapshot mismatch | high | mitigate | O_EXCL + fsync + sha256 artifact; rebalance_plans binds output_sha256 + artifact_relative_path + input_snapshot_sha256 (64-hex CHECK); read side checksum-verified — mismatch raises ArtifactReadError (14-01/14-02/14-05). Test: test_rebalance checksum cases. |
| T-14-02 | Tampering | Paper fill writing real positions / an execution route appearing | critical | mitigate | No-execution-route regression gate — paper.py writes ONLY paper_rebalance_transitions; no INSERT INTO positions, no broker/submit/place_order vocabulary, no execution-named method; grep gate on both modules (14-01/14-04). Test: test_paper test_no_execution_route. |
| T-14-03 | Tampering | Audit-ledger rewrite / fabrication | high | mitigate | rebalance_plans + paper_rebalance_transitions append-only with no_update/no_delete triggers; UNIQUE (plan_id, transition) idempotency; IntegrityError→ValueError mapping (14-02). Test: test_operational_migrations rebalance/paper cases. |
| T-14-04 | Spoofing | Discretization RMSE hidden or dishonest | medium | mitigate | RMSE computed over the FULL universe incl. blocked, recorded with `rmse_definition`; non-finite weights fail closed; deterministic 8-decimal rounding (14-01/14-03). Test: test_rebalance RMSE reference cases. |
| T-14-05 | Tampering | Idempotency bypass (double approve / double fill) | high | mitigate | UNIQUE (plan_id, transition) at the DB + repository idempotency (matching idempotency_key returns the existing row, mismatch raises) (14-02/14-04). Test: test_paper idempotency cases. |
| T-14-06 | Tampering | Expired plan approved / filled | medium | mitigate | Every post-creation transition compares now against expires_at and raises ValueError (14-04). Test: test_paper expired cases. |
| T-14-07 | Tampering | Blocked instrument entering the plan | medium | mitigate | `blocked` set filtered before lot-sizing, recorded verbatim in blocked_instruments_json; discrete weight 0 (14-01/14-03). Test: test_rebalance blocked cases. |
| T-14-08 | Tampering | Non-optimal / empty-weight run rendered as a plan | medium | mitigate | `build_rebalance_plan` fails closed on missing run / problem_status != "optimal" / empty output_weights (mirrors analyzer L92-95) (14-05). Test: test_rebalance run-gate cases. |
| T-14-SC | Tampering | Python package supply chain | low | accept | No new installs in Phase 14 — reuses the locked engine.py MatcherConfig + polars/numpy/sqlite3 + Phase 11-12 cvxpy/scipy already `[ASSUMED]` approved (no package-manager install task exists; RESEARCH Package Legitimacy Audit N/A — no research phase). |

# Phase Verification

```bash
# Per-wave gates (from backend/)
cd backend && .venv/bin/python -m pytest tests/test_operational_migrations.py -q --tb=short                                             # wave 0
cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -q --tb=short                   # wave 0 (expected RED scaffolds)
cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -q --tb=short                   # wave 1 (tracer)
cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py -q --tb=short                                                 # wave 2 (lot-sizing breadth)
cd backend && .venv/bin/python -m pytest tests/portfolio/test_paper.py -q --tb=short                                                     # wave 2 (paper breadth)
cd backend && .venv/bin/python -m pytest tests/portfolio/test_rebalance.py tests/portfolio/test_paper.py -q --tb=short                   # wave 3 (robustness + reporting)

# Phase gate (before /gsd-verify-work)
cd backend && .venv/bin/python -m pytest -x
```

Cross-module integrity checks:
- The lot-sizing adapter reuses the engine.py formula (`floor(allocation / (price * (1 + cost)) / 100) * 100`, engine.py:1158) + MatcherConfig fees — no second matcher (`grep -c "load_panel" app/portfolio/rebalance.py` == 0).
- The plan artifact is O_EXCL + fsync + sha256; rebalance_plans binds output_sha256 + artifact_relative_path + input_snapshot_sha256; the read side is checksum-verified (14-01/14-05).
- Every paper transition is an append-only fact with UNIQUE (plan_id, transition) idempotency; approve/reject/fill are idempotent; reject is terminal; expired plans fail closed (14-02/14-04).
- **No-execution-route gate** (hard acceptance): `grep -vE '^\s*(#|""")' app/portfolio/rebalance.py app/portfolio/paper.py | grep -cE '\b(broker|submit|place_order|live_)\b'` == 0; `grep -c "INSERT INTO positions" app/portfolio/paper.py` == 0; `grep -c "INSERT INTO" app/portfolio/paper.py` == 0 (raw SQL is absent — all writes route through `repository.record_paper_transition`; the transition INSERT lives in repository.py).
- Grep-gate hygiene: negative greps use `grep -vE '^\s*(#|""")'` filtering where comments/docstrings could self-invalidate; module docstrings are worded without the gate tokens.

# Phase Success Criteria

- All 5 plans complete with their per-plan gates green.
- The full backend suite is green before `/gsd-verify-work` (phase gate).
- Every locked decision in 14-CONTEXT.md is implemented (see Source Coverage Audit): RBAL-01 (lot-sizing adapter reusing engine.py — 100-share lots, odd-lot sell, cash residue, turnover cost, blocked instruments, expiry, immutable artifact with RMSE visible) and RBAL-02 (paper-rebalance state machine — append-only audit fact, human approval, idempotency) — with zero execution authority as the hard acceptance criterion (success criterion 3).
- Deferred ideas from CONTEXT (live broker execution, auto-rebalance scheduling v2, real positions from paper fills, frontend panels Phase 15) do NOT appear in any delivered artifact.

# Output

After each plan completes, create the matching summary at `.planning/phases/14-output-boundary-(rebalanceplan-+-paper-rebalance)/14-{NN}-SUMMARY.md` documenting what landed, the evidence, and any deviations from this plan. The phase gate is the full backend suite green before `/gsd-verify-work`.
