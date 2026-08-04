---
phase: 15-api-sse-frontend-panels
plan: phase-plan
type: execute
requirements: [UI-01, UI-02]
wave_summary:
  wave_0: [15-02]
  wave_1: [15-01]
  wave_2: [15-03, 15-04]
  wave_3: [15-05]
must_haves:
  truths:
    - "Researcher can open the ModelLibrary and WalkForward panels in the Backtest workspace and inspect admitted factors, multi-factor models, and walk-forward/OOS results backed by typed server-owned contracts (UI-01)."
    - "Researcher can open the Optimization, RiskAttribution, and RebalancePlan panels in the Portfolio workspace and inspect immutable runs, attribution, and paper-rebalance suggestions backed by typed server-owned contracts (UI-02)."
    - "Walk-forward runs stream progress over SSE through the durable job pattern, and optimization/plan updates fan out through the existing shared SSE stream (success criterion 3)."
    - "ZERO execution authority in the UI: no execute/order/submit affordance anywhere; the RebalancePlan panel offers only read + human approve/reject (append-only audit)."
    - "Honest display: RankIC never rendered as IC; optimizer output always rendered with baselines; reserved OOS vs selection/validation folds visually distinct and honestly labeled."
    - "Panels read immutable rows/artifacts via typed read API routes over Phases 10-14 repositories — never live module hand-off; DTOs are server-owned and frontend api.ts strictly consumes them."
  artifacts:
    - path: backend/app/api/research_panels.py
      provides: "typed READ routes: GET /api/research/models (model definitions + composites), GET /api/research/factors (admitted catalog w/ verdicts + IC/ICIR), GET /api/research/wf/plans (plans + folds + OOS), GET /api/research/wf/search-runs, GET /api/research/wf/validated, GET /api/research/wf/ensembles"
    - path: backend/app/api/portfolio_panels.py
      provides: "typed READ routes: GET /api/portfolio/optimization-runs, GET /api/portfolio/optimization-runs/{id}, GET /api/portfolio/attribution, GET /api/portfolio/rebalance-plans, GET /api/portfolio/rebalance-plans/{id}/paper (state + transitions), POST /api/portfolio/rebalance-plans/{id}/approve, POST /api/portfolio/rebalance-plans/{id}/reject (idempotent, append-only)"
    - path: backend/app/contracts/panels.py
      provides: "server-owned Pydantic DTOs (strict, extra=forbid) for every panel response — OptimizationRunDTO, AttributionEvidenceDTO, RebalancePlanDTO, PaperStateDTO, ModelDefinitionDTO, WfPlanDTO, etc."
    - path: backend/app/api/walkforward_sse.py
      provides: "SSE streaming endpoint for walk-forward progress (durable _BacktestJob-style module job + progress replay on reconnect) + optimization/plan fan-out events on the shared SSE stream"
    - path: frontend/src/lib/api.ts (extend)
      provides: "typed client methods: listOptimizationRuns / getOptimizationRun / listAttribution / listRebalancePlans / getPaperState / approveRebalance / rejectRebalance / listModels / listFactors / listWfPlans / listWfSearchRuns / listWfValidated / listWfEnsembles"
    - path: frontend/src/lib/queryKeys.ts (extend)
      provides: "QK factories for the five panels + SSE_INVALIDATE_PREFIXES entries for optimization-run / rebalance-plan / paper-transition updates"
    - path: frontend/src/pages/backtest/ModelLibrary.tsx + WalkForward.tsx
      provides: "UI-01 panels over typed contracts (admitted factors + models; wf plans/folds/OOS/ensembles)"
    - path: frontend/src/pages/portfolio/Optimization.tsx + RiskAttribution.tsx + RebalancePlan.tsx
      provides: "UI-02 panels over typed contracts (immutable runs + baselines; attribution + PSD provenance; plan + paper state machine w/ approve/reject)"
    - path: frontend/src/router.tsx (extend) + frontend/src/pages/Backtest.tsx + Portfolio.tsx (nav)
      provides: "panel routes wired into the existing workspace tabs"
  key_links:
    - from: backend/app/api/portfolio_panels.py
      to: backend/app/portfolio/repository.py
      via: "PortfolioRepository.list_optimization_runs / list_attribution_evidence / list_rebalance_plans / list_paper_transitions / get_paper_state"
      pattern: "read routes over immutable rows"
    - from: backend/app/api/research_panels.py
      to: backend/app/research/repository.py
      via: "ResearchRepository.list_current_revisions / get_admission_verdict / get_model_definition / list_model_composites / list_wf_plans / list_wf_folds / list_wf_search_runs / list_validated_strategies / list_wf_ensembles"
      pattern: "read routes over immutable rows"
    - from: backend/app/contracts/panels.py
      to: backend/app/api/*_panels.py
      via: "response_model=... on every route — strict server-owned DTOs"
      pattern: "typed server-owned contracts"
    - from: frontend/src/lib/api.ts
      to: backend/app/api/*_panels.py
      via: "typed methods returning the DTO types"
      pattern: "strict consumption"
    - from: frontend/src/lib/queryKeys.ts
      to: frontend/src/lib/api.ts
      via: "QK factories + SSE_INVALIDATE_PREFIXES (optimization/plan fan-out)"
      pattern: "shared SSE invalidation"
---

# Phase 15: API/SSE + Frontend Panels — Executable Plan

## Phase Goal

Backtest and Portfolio workspaces surface the full pipeline through typed server-owned contracts and streaming progress, with ModelLibrary/WalkForward and Optimization/RiskAttribution/RebalancePlan panels.

## Scope

**In scope (UI-01..02):** five read panels (ModelLibrary, WalkForward in Backtest; Optimization, RiskAttribution, RebalancePlan in Portfolio) backed by **typed server-owned contracts** (Pydantic DTOs, strict `extra="forbid"`; frontend `api.ts` strictly consumes them). The panels read immutable rows/artifacts from Phases 10-14 repositories (append-only tables + checksum-verified artifacts) via NEW typed READ routes under `/api/research` + `/api/portfolio` — never live module hand-off. Walk-forward runs stream progress over SSE through the durable job pattern (module-level `_BacktestJob`-style job + progress replay on reconnect, mirroring `backtestTask.ts`); optimization/plan updates fan out through the existing shared SSE stream. The RebalancePlan panel offers human approve/reject (append-only audit) and NOTHING else.

**Out of scope:** live broker execution (forever out of scope — platform boundary); new backend features (all data surfaces exist from Phases 10-14 — this phase only ADDS typed read routes + panels + SSE wiring); auto-rebalance scheduling (v2); any execute/order/submit affordance in the UI (hard acceptance — even a disabled one).

## Source Coverage Audit

| Source | ID | Required behavior or constraint | Plans | Status |
|---|---|---|---|---|
| GOAL | Phase 15 | Workspaces surface the full pipeline through typed server-owned contracts + streaming progress, with the five panels | 15-01..15-05 | COVERED |
| REQ | UI-01 | Backtest workspace: ModelLibrary + WalkForward panels backed by typed server-owned contracts | 15-01, 15-03, 15-05 | COVERED |
| REQ | UI-02 | Portfolio workspace: Optimization + RiskAttribution + RebalancePlan panels backed by typed server-owned contracts | 15-01, 15-04, 15-05 | COVERED |
| SC3 | SSE | Walk-forward streams progress over SSE through the durable job pattern; optimization/plan updates fan out through the existing shared SSE stream | 15-05 | COVERED |
| CONTEXT | Typed contracts | Server-owned Pydantic DTOs first; frontend api.ts strictly consumes; reuse api.ts/queryKeys.ts/SSE hooks | 15-01, 15-02, 15-03, 15-04 | COVERED |
| CONTEXT | Panel scope | Five panels all in scope; read immutable rows/artifacts, never live hand-off | 15-01, 15-03, 15-04 | COVERED |
| CONTEXT | SSE | Walk-forward durable job + optimization/plan fan-out; reconnect/idempotent | 15-05 | COVERED |
| CONTEXT | Boundary | Paper panel read-only + human approve/reject; NO execute affordance; honest display (RankIC≠IC, baselines, OOS honest) | 15-01..15-05 | COVERED |
| CODE | Repositories | Phases 10-14 read surfaces (PortfolioRepository + ResearchRepository) | 15-01, 15-02 | COVERED |
| CODE | Jobs | `_BacktestJob`-style durable job + SSE replay | 15-05 | COVERED |

**Exclusions (not gaps):** deferred ideas in `15-CONTEXT.md` (live broker execution, auto-rebalance v2, new backend features, execute affordance); v2 requirements.

## Plan List

- [ ] 15-01: **Tracer** — one typed read API route → one panel end-to-end (Optimization panel over `list_optimization_runs` + `get_optimization_run`, with baselines rendered) on a fixture run; DTOs + api.ts method + panel component + route wiring (UI-02 spine)
- [ ] 15-02: **Wave 0 foundations** — server-owned DTO contracts (`contracts/panels.py`) + typed READ route scaffolding (both routers) + backend pytest fixtures (TestClient app-state injection: research_repository / portfolio repos / operational) + 15-UI-SPEC.md sign-off
- [ ] 15-03: **Backtest panels breadth** — ModelLibrary + WalkForward panels (admitted factors + models; wf plans/folds/OOS/validated/ensembles) with honest RankIC/OOS labeling (UI-01)
- [ ] 15-04: **Portfolio panels breadth** — RiskAttribution (attribution + PSD provenance) + RebalancePlan (plan + paper state machine w/ approve/reject, NO execute affordance) (UI-02)
- [ ] 15-05: **SSE streaming + reporting breadth** — walk-forward SSE durable-job progress + optimization/plan fan-out via shared SSE stream; reconnect/idempotent (SC3)

## Wave Structure

| Wave | Plans | Purpose |
|------|-------|---------|
| 0 | 15-02 | Foundations: server-owned DTOs + route scaffolding + TestClient fixtures; UI-SPEC sign-off. |
| 1 | 15-01 | The tracer: one typed read route → one panel end-to-end before any breadth. |
| 2 | 15-03, 15-04 | Backtest panels (research routes + ModelLibrary/WalkForward) and Portfolio panels (attribution + rebalance plan) — disjoint, parallel. |
| 3 | 15-05 | SSE streaming + fan-out breadth. |

## Artifacts this phase produces

| Artifact | Kind | Provides |
|---|---|---|
| `contracts/panels.py` | Pydantic DTOs | server-owned strict DTOs (OptimizationRunDTO, AttributionEvidenceDTO, RebalancePlanDTO, PaperStateDTO, ModelDefinitionDTO, WfPlanDTO, ...) |
| `api/research_panels.py` + `api/portfolio_panels.py` | FastAPI routers | typed READ routes over Phases 10-14 repositories (response_model=DTO on every route) |
| `api/walkforward_sse.py` | SSE endpoint | walk-forward progress stream (durable job + replay) + optimization/plan fan-out |
| `lib/api.ts` + `lib/queryKeys.ts` | frontend client | typed methods + QK factories + SSE_INVALIDATE_PREFIXES |
| `pages/backtest/{ModelLibrary,WalkForward}.tsx` | UI-01 panels | admitted factors/models + wf results over typed contracts |
| `pages/portfolio/{Optimization,RiskAttribution,RebalancePlan}.tsx` | UI-02 panels | immutable runs + attribution + paper state machine (approve/reject, no execute) |
| `router.tsx` + workspace nav | wiring | panel routes in the existing Backtest/Portfolio tabs |

## Requirement → Plan Mapping

| Requirement | Behavior | Plans | Verification command |
|---|---|---|---|
| UI-01 | ModelLibrary + WalkForward panels backed by typed contracts | 15-01, 15-03, 15-05 | `cd backend && .venv/bin/python -m pytest tests/api/test_research_panels.py -x` + frontend build/typecheck |
| UI-02 | Optimization + RiskAttribution + RebalancePlan panels backed by typed contracts | 15-01, 15-04, 15-05 | `cd backend && .venv/bin/python -m pytest tests/api/test_portfolio_panels.py -x` + frontend build/typecheck |
| SC3 | SSE streaming (walk-forward durable job + optimization/plan fan-out) | 15-05 | `cd backend && .venv/bin/python -m pytest tests/api/test_walkforward_sse.py -x` |

All commands run from `backend/` (pytest) or `frontend/` (pnpm build / tsc) with the project interpreters.

---

# Plan 15-01 — Tracer: Optimization Panel End-to-End (UI-02 spine)

**wave:** 1 · **depends_on:** [15-02] · **autonomous:** true
**requirements:** [UI-02]
**files_modified:**
- backend/app/contracts/panels.py (extend — OptimizationRunDTO)
- backend/app/api/portfolio_panels.py (extend — GET /api/portfolio/optimization-runs + /{id})
- frontend/src/lib/api.ts (extend — listOptimizationRuns / getOptimizationRun)
- frontend/src/lib/queryKeys.ts (extend — optimizationRuns factories)
- frontend/src/pages/portfolio/Optimization.tsx (new — the panel)
- frontend/src/pages/Portfolio.tsx + router.tsx (wire the panel)
- backend/tests/api/test_portfolio_panels.py (tracer tests)

## Objective

Prove the complete Phase 15 spine on a fixture, end to end, before any breadth: a recorded Phase 11 optimization run → typed server-owned DTO (`OptimizationRunDTO`, strict) → GET route → `api.ts` typed method → the Optimization panel rendering the immutable run WITH baselines (min-vol + HRP side by side — never "optimal" alone) and the failure reason for failed runs. This is the milestone's UI keel: it forces the DTO discipline, the read route over immutable rows, the strict api.ts consumption, and the honest-display rule into existence on the first commit.

## Context

- @.planning/phases/15-api-sse-frontend-panels/15-CONTEXT.md + 15-UI-SPEC.md (locked decisions; the Optimization panel section)
- backend/app/portfolio/repository.py — `list_optimization_runs` (L210) + `get_optimization_run` (L202) — the immutable row surface
- backend/app/contracts/validator.py — the existing Pydantic DTO conventions (strict ConfigDict)
- backend/app/api/portfolio.py — the router pattern (`prefix="/api/portfolio"`, `_repository(request)` app-state access)
- frontend/src/lib/api.ts + queryKeys.ts — the typed client + QK conventions
- frontend/src/pages/portfolio/ + components/portfolio/ — the panel patterns (HoldingsTable etc.)
- backend/tests/portfolio/conftest.py — `fixture_attribution_run` / `fixture_rebalance_run` (the recorded optimal run fixture to reuse)

## Tasks

- **build: `OptimizationRunDTO` + GET routes (typed read over immutable runs)**
  - Files: backend/app/contracts/panels.py, backend/app/api/portfolio_panels.py, backend/app/main.py
  - Read first: backend/app/portfolio/repository.py `list_optimization_runs`/`get_optimization_run` (field names incl. `output_weights`, `baseline_weights`, `constraint_stack`, `solver_name`, `solver_version`, `solver_options`, `problem_status`, `failure_reason`, `input_snapshot_sha256`), backend/app/contracts/validator.py (strict DTO conventions), backend/app/api/portfolio.py (`_repository(request)` pattern)
  - Action: Add `OptimizationRunDTO` (strict `extra="forbid"`): id, objective, as_of, universe, model_id, input_snapshot_sha256, expected_return_method, risk_model, risk_model_detail, constraint_stack, solver_name, solver_version, solver_options, problem_status, failure_reason | None, output_weights, baseline_weights, output_sha256, weights_artifact_relative_path, created_at. Add `GET /api/portfolio/optimization-runs` (list, `limit` fail-closed ge=1 le=500, optional `objective` filter) + `GET /api/portfolio/optimization-runs/{run_id}` (404 on missing) with `response_model=list[OptimizationRunDTO]` / `OptimizationRunDTO`. Register the router in `backend/app/main.py` (`app.include_router(portfolio_panels.router)`).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/api/test_portfolio_panels.py -x -q --tb=short` (the 15-02 scaffolded route cases turn green)
  - Done: both routes return server-owned DTOs (extra=forbid enforced); list filters + limit fail-closed; missing run → 404.

- **build: frontend typed methods + Optimization panel (with baselines)**
  - Files: frontend/src/lib/api.ts, frontend/src/lib/queryKeys.ts, frontend/src/pages/portfolio/Optimization.tsx, frontend/src/pages/Portfolio.tsx, frontend/src/router.tsx
  - Read first: frontend/src/lib/api.ts (request<T> + typed methods), frontend/src/lib/queryKeys.ts (QK factories + SSE_INVALIDATE_PREFIXES), frontend/src/pages/portfolio/ (panel patterns), frontend/src/router.tsx (lazy page registration)
  - Action: Add `listOptimizationRuns(params?)` / `getOptimizationRun(id)` typed methods + `QK.optimizationRuns` factories. Create `pages/portfolio/Optimization.tsx`: list immutable runs (objective chip, status chip incl. `failed` + failure reason, solver, as-of, input_snapshot_sha256 mono); a run detail view renders output weights WITH baselines (min-vol + HRP side by side — a run whose objective is max_sharpe or has render_baselines=true MUST show the baseline table; never "optimal" alone); expandable constraint stack / risk model / solver options. Wire the route in `router.tsx` + a nav entry in `pages/Portfolio.tsx`.
  - Verify: `cd frontend && pnpm build` (tsc + vite build pass)
  - Done: the panel renders typed data with baselines; failed runs show failure_reason; no execute/order affordance exists anywhere in the panel.

- **test: End-to-end tracer proof**
  - Files: backend/tests/api/test_portfolio_panels.py (extend)
  - Read first: the 15-02 scaffold cases, backend/tests/portfolio/conftest.py fixtures
  - Action: Record a fixture run (`fixture_attribution_run`-style) into a tmp_path operational.db, inject `app.state` repositories into the TestClient app (mirroring tests/forecast/test_api.py: `app.state.portfolio_repository = ...`), then GET the routes: list returns the run; get by id returns the DTO with output_weights + baseline_weights; a failed run (problem_status="solver_error" + failure_reason) renders its failure reason; missing id → 404; extra field in the request/response is rejected by the strict DTO.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/api/test_portfolio_panels.py -x -q --tb=short`
  - Done: the full run-row → DTO → route → panel spine works end-to-end with baselines + honest failure display — the Phase 15 keel is proven before any breadth.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/api/test_portfolio_panels.py -x -q --tb=short
cd frontend && pnpm build
```

All green. **Zero-execution-UI gate** (hard acceptance): grep the Optimization panel source — no `execute` / `order` / `submit` / `trade` affordance (`grep -nE 'execute|placeOrder|submitOrder' frontend/src/pages/portfolio/Optimization.tsx` == 0); no POST route to a live path is added (only GET read routes in this plan).

## Success Criteria

- A recorded optimization run renders through a typed server-owned DTO + GET route + typed api.ts method into the Optimization panel with baselines shown and failure reasons honest.
- The zero-execution-UI gate holds: the panel offers read-only inspection only.

---

# Plan 15-02 — Wave 0: Server-Owned DTOs + Route Scaffolding + Test Fixtures

**wave:** 0 · **depends_on:** [] · **autonomous:** false (UI-SPEC sign-off checkpoint)
**requirements:** [UI-01, UI-02]
**files_modified:**
- backend/app/contracts/panels.py (new)
- backend/app/api/research_panels.py (new — route scaffolding)
- backend/app/api/portfolio_panels.py (new — route scaffolding)
- backend/app/main.py (register both routers)
- backend/tests/api/conftest.py (new — TestClient app-state injection fixtures)
- backend/tests/api/test_portfolio_panels.py (new — RED scaffold)
- backend/tests/api/test_research_panels.py (new — RED scaffold)
- .planning/phases/15-api-sse-frontend-panels/15-UI-SPEC.md (sign-off)

## Objective

Land the irreversible foundations every other plan builds on: the **server-owned DTO contract** (`contracts/panels.py` — strict Pydantic DTOs for every panel response), the two typed read routers (research + portfolio) scaffolded with their route signatures, the TestClient app-state injection fixtures the tracer/breadth tests use, and the UI design contract sign-off. This is the one-way schema door of the UI surface: every panel response type is pinned here before any frontend consumes it.

## Context

- @.planning/phases/15-api-sse-frontend-panels/15-CONTEXT.md + 15-UI-SPEC.md
- backend/app/contracts/validator.py — the strict DTO conventions
- backend/app/api/research.py + portfolio.py — the router patterns + app-state access
- backend/app/research/repository.py + portfolio/repository.py — the read surfaces the DTOs mirror
- backend/tests/forecast/test_api.py — the TestClient app-state injection pattern
- backend/app/main.py — router registration

## Tasks

- **checkpoint:decision — Approve the server-owned DTO contract + panel surface (one-way door)**
  - Decision: Land `contracts/panels.py` with the strict server-owned DTOs for all five panels (OptimizationRunDTO, AttributionEvidenceDTO, RebalancePlanDTO, PaperStateDTO, ModelDefinitionDTO, WfPlanDTO, WfSearchRunDTO, WfValidatedStrategyDTO, WfEnsembleDTO) — every response_model on the typed read routes. This is a one-way door: the DTO shapes become the frontend contract; changing a field later ripples to api.ts + panels.
  - Options:
    - option-a: ONE `contracts/panels.py` module with all DTOs (strict, extra="forbid", Field constraints mirroring the repositories' validation).
    - option-b: Per-router DTO modules (research_panels_contracts.py + portfolio_panels_contracts.py). Pros: smaller files; Cons: the shared PaperStateDTO / RunDTO cross both routers.
  - Resume signal: Select: option-a or option-b

- **build: `contracts/panels.py` + both typed read routers (scaffold)**
  - Files: backend/app/contracts/panels.py, backend/app/api/research_panels.py, backend/app/api/portfolio_panels.py, backend/app/main.py
  - Read first: backend/app/contracts/validator.py, backend/app/research/repository.py + portfolio/repository.py (the exact read-surface field names), backend/app/api/research.py + portfolio.py (router + app-state patterns)
  - Action: Create the DTO module per the approved option. Create `api/research_panels.py` (router prefix="/api/research", tags=["research-panels"]) with scaffolded typed routes: `GET /models` (list model definitions + composites), `GET /factors` (admitted catalog), `GET /wf/plans`, `GET /wf/search-runs`, `GET /wf/validated`, `GET /wf/ensembles`. Create `api/portfolio_panels.py` (prefix="/api/portfolio", tags=["portfolio-panels"]) with scaffolded routes: `GET /optimization-runs` + `/{id}`, `GET /attribution`, `GET /rebalance-plans`, `GET /rebalance-plans/{id}/paper`, `POST /rebalance-plans/{id}/approve` + `/reject`. All with response_model=DTO. Register both routers in main.py.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/api/test_portfolio_panels.py tests/api/test_research_panels.py -x -q --tb=short` (RED — routes exist but return 501/NotImplemented until 15-01/15-03/15-04 land; or the scaffold tests assert the routes register + DTO validation)
  - Done: both routers registered; every route declares a response_model; the strict DTOs reject extra fields.

- **test: TestClient app-state injection fixtures (Wave 0 scaffolding)**
  - Files: backend/tests/api/conftest.py, backend/tests/api/test_portfolio_panels.py, backend/tests/api/test_research_panels.py
  - Read first: backend/tests/forecast/test_api.py (the app-state injection pattern), backend/tests/portfolio/conftest.py (fixture runs)
  - Action: Add `tests/api/conftest.py`: a `panel_app` fixture that builds the FastAPI app (or the real app) and injects `app.state.research_repository` / `app.state.portfolio_repository` / `app.state.operational` pointing at a tmp_path operational.db (migrated) + a `TestClient`. Scaffold RED tests in both test files: routes register (200 on empty list), strict DTO rejects an extra field, 404 on missing run/plan.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/api/test_portfolio_panels.py tests/api/test_research_panels.py -q --tb=short` — expected RED until 15-01/15-03/15-04 land the route bodies
  - Done: the fixtures exist; the scaffold cases are provably RED; the exact tests 15-01/15-03/15-04 turn green.

- **docs: UI-SPEC sign-off**
  - Files: .planning/phases/15-api-sse-frontend-panels/15-UI-SPEC.md
  - Action: Mark the UI-SPEC status approved (the planner produced it; this plan records the sign-off as the UI phase's design contract gate).
  - Done: 15-UI-SPEC.md status: approved.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/api/test_portfolio_panels.py tests/api/test_research_panels.py -q --tb=short   # RED scaffolds expected
```

The DTOs + routers + fixtures exist; the scaffold cases are provably RED until the route bodies land.

**Zero-execution-UI gate (hard acceptance):** this foundations plan introduces NO UI panel and NO execute/order/submit affordance — the DTOs and routes are read-only (except the paper approve/reject POST stubs, which call `paper.approve`/`reject` — idempotent append-only, never a live path).

## Success Criteria

- Server-owned strict DTOs pinned for all five panels; both typed read routers registered with response_model on every route.
- TestClient app-state fixtures exist; scaffolds RED.
- 15-UI-SPEC.md approved (the UI design contract gate).

---

# Plan 15-03 — Backtest Panels Breadth: ModelLibrary + WalkForward (UI-01)

**wave:** 2 · **depends_on:** [15-01] · **autonomous:** true
**requirements:** [UI-01]
**files_modified:**
- backend/app/api/research_panels.py (extend — route bodies)
- backend/app/contracts/panels.py (extend — ModelDefinitionDTO / WfPlanDTO / ...)
- frontend/src/lib/api.ts + queryKeys.ts (extend)
- frontend/src/pages/backtest/ModelLibrary.tsx (new)
- frontend/src/pages/backtest/WalkForward.tsx (new)
- frontend/src/pages/Backtest.tsx + router.tsx (wire)
- backend/tests/api/test_research_panels.py (extend — green)

## Objective

Deliver UI-01: the ModelLibrary + WalkForward panels in the Backtest workspace over typed server-owned contracts — admitted factors (verdicts, IC/ICIR, monthly evidence summary), multi-factor models (weights, lineage), and walk-forward/OOS results (plans, folds, search runs, validated strategies, ensembles) with honest RankIC/OOS labeling.

## Context

- 15-UI-SPEC.md (Backtest workspace sections: ModelLibrary + WalkForward)
- backend/app/research/repository.py — list_current_revisions / get_admission_verdict / get_model_definition / list_model_composites / list_wf_plans / list_wf_folds / list_wf_search_runs / list_validated_strategies / list_wf_ensembles
- frontend/src/pages/backtest/ResearchLibrary.tsx — the existing panel pattern

## Tasks

- **build: research_panels route bodies + DTO breadth**
  - Files: backend/app/api/research_panels.py, backend/app/contracts/panels.py
  - Action: Implement the route bodies over ResearchRepository: `GET /models` (model definitions + composites + lineage), `GET /factors` (admitted catalog: name, current revision, admission verdict w/ policy version + gates, IC + RankIC as SEPARATE fields, ICIR, monthly evidence summary, coverage), `GET /wf/plans` (plans w/ oos_pinned_at + fold geometry), `GET /wf/search-runs` (trial count + search space + score distribution), `GET /wf/validated`, `GET /wf/ensembles`. DTOs mirror the repository field names exactly.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/api/test_research_panels.py -x -q --tb=short`
  - Done: every route returns typed DTOs over immutable rows; RankIC and IC are distinct fields (never conflated).

- **build: ModelLibrary + WalkForward panels**
  - Files: frontend/src/lib/api.ts, frontend/src/lib/queryKeys.ts, frontend/src/pages/backtest/ModelLibrary.tsx, frontend/src/pages/backtest/WalkForward.tsx, frontend/src/pages/Backtest.tsx, frontend/src/router.tsx
  - Action: Add typed methods + QK factories. ModelLibrary.tsx: factor rows (name, revision, verdict chips, IC column + RankIC column SEPARATE, ICIR, coverage, monthly evidence sparkline via ECharts), model rows (weighting, weights, lineage, input_snapshot_sha256 mono). WalkForward.tsx: plan rows (OOS reservation), fold breakdown (train/gap/test with the reserved-OOS segment visually distinct + honestly labeled "reserved OOS — evaluated once"), search-run summary (trial count, search space, score distribution), validated strategies + ensembles.
  - Verify: `cd frontend && pnpm build`
  - Done: both panels render typed data; RankIC never rendered as IC; reserved OOS visually distinct from selection/validation folds.

- **test: research_panels green breadth**
  - Files: backend/tests/api/test_research_panels.py (extend)
  - Action: Seed a research repo with a factor revision + admission verdict + model + composite + wf plan/fold/search/validated/ensemble (via the existing repository methods or fixtures), then GET each route and assert the DTO fields.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/api/test_research_panels.py -x -q --tb=short`
  - Done: all research panel routes return typed immutable data; the honest-label contract (RankIC separate, OOS distinct) is exercised by tests.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/api/test_research_panels.py -x -q --tb=short
cd frontend && pnpm build
```

**Zero-execution-UI gate (hard acceptance):** `grep -nE 'execute|placeOrder|submitOrder|trade' frontend/src/pages/backtest/ModelLibrary.tsx frontend/src/pages/backtest/WalkForward.tsx` == 0 — no execute/order/submit affordance in either panel.

## Success Criteria

- ModelLibrary + WalkForward panels render typed immutable data with honest IC/RankIC + OOS labeling (UI-01).

---

# Plan 15-04 — Portfolio Panels Breadth: RiskAttribution + RebalancePlan (UI-02)

**wave:** 2 · **depends_on:** [15-01] · **autonomous:** true
**requirements:** [UI-02]
**files_modified:**
- backend/app/api/portfolio_panels.py (extend — route bodies)
- backend/app/contracts/panels.py (extend — AttributionEvidenceDTO / RebalancePlanDTO / PaperStateDTO)
- frontend/src/lib/api.ts + queryKeys.ts (extend)
- frontend/src/pages/portfolio/RiskAttribution.tsx (new)
- frontend/src/pages/portfolio/RebalancePlan.tsx (new)
- frontend/src/pages/Portfolio.tsx + router.tsx (wire)
- backend/tests/api/test_portfolio_panels.py (extend — green)

## Objective

Deliver UI-02's remaining panels: RiskAttribution (exposure + marginal-contribution attribution reconciling to portfolio variance, PSD provenance — never silent) and RebalancePlan (plan + paper state machine with human approve/reject, append-only audit, and NO execute affordance).

## Context

- 15-UI-SPEC.md (Portfolio workspace sections)
- backend/app/portfolio/repository.py — list_attribution_evidence / list_rebalance_plans / list_paper_transitions / get_paper_state
- backend/app/portfolio/paper.py — approve / reject (the idempotent append-only actions)
- frontend/src/pages/portfolio/ — the panel patterns

## Tasks

- **build: portfolio_panels route bodies + DTO breadth**
  - Files: backend/app/api/portfolio_panels.py, backend/app/contracts/panels.py
  - Action: Implement: `GET /attribution` (evidence rows: exposure + marginal contribution, signed components, reconciliation to portfolio variance, covariance provenance incl. PSD-repair method/epsilon/eigenvalues when present, drawdown attribution), `GET /rebalance-plans` (plans: continuous vs discrete weights, lot sizes, cash residue, turnover cost, blocked, RMSE, expires_at), `GET /rebalance-plans/{id}/paper` (current state + append-only transition ledger), `POST /rebalance-plans/{id}/approve` + `/{id}/reject` (idempotent, append-only — call paper.approve/reject; 404 on missing plan, 409/400 on invalid transition).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/api/test_portfolio_panels.py -x -q --tb=short`
  - Done: attribution + plan + paper routes return typed DTOs; approve/reject are idempotent append-only actions; NO route can push to a live path.

- **build: RiskAttribution + RebalancePlan panels**
  - Files: frontend/src/lib/api.ts, frontend/src/lib/queryKeys.ts, frontend/src/pages/portfolio/RiskAttribution.tsx, frontend/src/pages/portfolio/RebalancePlan.tsx, frontend/src/pages/Portfolio.tsx, frontend/src/router.tsx
  - Action: RiskAttribution.tsx: attribution table (exposure / marginal contribution / signed components), reconciliation line "ΣMC == wᵀΣw (rtol 1e-12)" or the recorded reconciliation, PSD-repair warning chip (method + ε, expandable eigenvalues before/after — never silent). RebalancePlan.tsx: plan detail (continuous vs discrete weights side by side, lot sizes, cash residue, turnover cost, blocked instruments, RMSE, expires_at), the paper state machine (state chip + append-only ledger), and — ONLY for a `suggested` plan — an `approve` / `reject` button pair (idempotent POST). **NO execute/order/submit control exists anywhere in this panel** — the panel simply has no such affordance.
  - Verify: `cd frontend && pnpm build`
  - Done: both panels render typed immutable data; approve/reject work; no execute affordance.

- **test: portfolio_panels green breadth**
  - Files: backend/tests/api/test_portfolio_panels.py (extend)
  - Action: Seed a portfolio repo with a run + attribution evidence + rebalance plan; GET attribution/plans/paper; POST approve → ledger appends; re-POST approve (same idempotency) → same row; reject after approve → 400; expired plan → 400; assert NO positions row was written (the zero-execution gate).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/api/test_portfolio_panels.py -x -q --tb=short`
  - Done: all portfolio panel routes typed; approve/reject idempotent + append-only; zero-execution gate asserted.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/api/test_portfolio_panels.py -x -q --tb=short
cd frontend && pnpm build
```

**Zero-execution-UI gate (HARD):** `grep -nE 'execute|placeOrder|submitOrder|trade' frontend/src/pages/portfolio/RebalancePlan.tsx` == 0; the panel has NO execute/order/submit control (not even disabled).

## Success Criteria

- RiskAttribution + RebalancePlan panels render typed immutable data; approve/reject are idempotent append-only; zero execution authority holds (UI-02).

---

# Plan 15-05 — SSE Streaming + Reporting Breadth (SC3)

**wave:** 3 · **depends_on:** [15-03, 15-04] · **autonomous:** true
**requirements:** [UI-01, UI-02]
**files_modified:**
- backend/app/api/walkforward_sse.py (new)
- backend/app/main.py (register)
- frontend/src/lib/api.ts + queryKeys.ts (extend — SSE invalidation prefixes)
- frontend/src/pages/backtest/WalkForward.tsx (extend — live progress)
- frontend/src/pages/portfolio/Optimization.tsx + RebalancePlan.tsx (extend — fan-out refresh)
- backend/tests/api/test_walkforward_sse.py (new)

## Objective

Deliver success criterion 3: walk-forward runs stream progress over SSE through the durable job pattern (module-level `_BacktestJob`-style job + progress-history replay on reconnect, mirroring the backtest SSE in `backend/app/api/backtest.py` + `frontend/src/lib/backtestTask.ts`), and optimization/plan updates fan out through the existing shared SSE stream (`SSE_INVALIDATE_PREFIXES` in queryKeys.ts) so the panels auto-refresh without polling.

## Context

- backend/app/api/backtest.py `_BacktestJob` + `_running_jobs` + the SSE endpoint (the durable job pattern to mirror)
- frontend/src/lib/backtestTask.ts (the reconnect + replay client pattern)
- frontend/src/lib/queryKeys.ts `SSE_INVALIDATE_PREFIXES` (the shared SSE fan-out mechanism)
- 15-UI-SPEC.md (Streaming progress section)

## Tasks

- **build: walk-forward SSE endpoint (durable job + replay)**
  - Files: backend/app/api/walkforward_sse.py, backend/app/main.py
  - Action: Mirror `_BacktestJob`: a module-level `_wf_jobs` dict keyed by plan_id/run key, progress history (fold index / total folds / status) replayable on reconnect, TTL cleanup, thread-safe. Add `GET /api/research/wf/plans/{plan_id}/stream` (SSE) emitting fold progress events; a `POST /api/research/wf/plans/{plan_id}/run` (or reuse the existing walk-forward entry point) that records the run into wf_search_runs and streams progress. Optimization/plan fan-out: emit events on the shared SSE stream when an optimization run or rebalance-plan/paper-transition is recorded (the existing SSE mechanism).
  - Verify: `cd backend && .venv/bin/python -m pytest tests/api/test_walkforward_sse.py -x -q --tb=short`
  - Done: walk-forward progress streams over SSE; reconnect replays the progress history; optimization/plan updates emit fan-out events.

- **build: frontend SSE consumption (progress + fan-out refresh)**
  - Files: frontend/src/lib/api.ts, frontend/src/lib/queryKeys.ts, frontend/src/pages/backtest/WalkForward.tsx, frontend/src/pages/portfolio/Optimization.tsx, frontend/src/pages/portfolio/RebalancePlan.tsx
  - Action: Add `QK.wfPlanStream(planId)` + SSE_INVALIDATE_PREFIXES entries for `optimization-runs` / `rebalance-plans` / `paper` so the Optimization + RebalancePlan panels auto-refresh on fan-out events. WalkForward.tsx: a live progress bar with reconnect state (mirror backtestTask.ts). Optimization.tsx + RebalancePlan.tsx: subscribe to the shared SSE stream for invalidation.
  - Verify: `cd frontend && pnpm build`
  - Done: walk-forward progress streams live with reconnect; optimization/plan updates fan out and refresh the panels.

- **test: SSE + fan-out green**
  - Files: backend/tests/api/test_walkforward_sse.py (extend)
  - Action: Start a walk-forward job, read the SSE stream (or the recorded progress history), assert progress events + replay; record an optimization run + a paper transition and assert the fan-out event was emitted on the shared stream.
  - Verify: `cd backend && .venv/bin/python -m pytest tests/api/test_walkforward_sse.py -x -q --tb=short`
  - Done: the durable-job SSE contract + fan-out are locked by tests.

## Verification

```bash
cd backend && .venv/bin/python -m pytest tests/api/test_walkforward_sse.py -x -q --tb=short
cd frontend && pnpm build
```

**Zero-execution-UI gate:** the SSE fan-out only refreshes read panels — no new write route to a live path.

## Success Criteria

- Walk-forward progress streams over SSE through the durable job pattern; optimization/plan updates fan out through the shared SSE stream (SC3).

---

# Consolidated Threat Model

> `workflow.security_enforcement: true` (config.json) — section required. Trust model: local single-user research host. **Zero execution authority is the phase's cardinal UI invariant** — no execute/order/submit affordance anywhere.

## Trust Boundaries

| Boundary | Description |
|---|---|
| Repository rows → DTOs | Immutable rows cross into strict server-owned DTOs (extra="forbid") via typed read routes — never live module hand-off |
| DTOs → frontend | api.ts strictly consumes the DTO types; no client-side provenance synthesis |
| Paper approve/reject → ledger | POST routes call paper.approve/reject (idempotent, append-only) — the ONLY write surface of the phase, and it is paper-only |
| SSE stream → panels | Progress + fan-out events refresh read panels; no SSE-driven write path |

## STRIDE / ASVS L1 Traceability

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|---|---|---|---|---|---|
| T-15-01 | Tampering | Execute affordance appears in the UI | critical | mitigate | Zero-execution-UI grep gate on every panel (no execute/order/submit/trade); RebalancePlan panel has NO such control — not even disabled (15-01/15-04). |
| T-15-02 | Spoofing | RankIC shown as IC / optimizer shown "optimal" without baselines / OOS mislabeled | high | mitigate | RankIC and IC are separate DTO fields + separate columns; optimizer runs always render baselines (min-vol + HRP); reserved OOS visually distinct + honestly labeled (15-01/15-03/15-04). |
| T-15-03 | Tampering | Paper approve/reject bypasses the state machine | high | mitigate | Routes call paper.approve/reject (state validation + expiry + idempotency); 400 on invalid transition; no raw ledger write from the route (15-04). |
| T-15-04 | Spoofing | DTO field drift between server and client | medium | mitigate | Server-owned strict DTOs + api.ts typed methods; response_model on every route (15-02). |
| T-15-05 | Tampering | SSE stream drives a write | medium | mitigate | SSE emits read-only refresh events; no SSE handler can write (15-05). |
| T-15-SC | Tampering | Python/JS package supply chain | low | accept | No new installs in Phase 15 (existing FastAPI + React/Vite/pnpm lockfile). |

# Phase Verification

```bash
# Per-wave gates (from backend/)
cd backend && .venv/bin/python -m pytest tests/api/test_portfolio_panels.py tests/api/test_research_panels.py -q --tb=short   # wave 0 (RED scaffolds)
cd backend && .venv/bin/python -m pytest tests/api/test_portfolio_panels.py -x -q --tb=short                                   # wave 1 (tracer)
cd backend && .venv/bin/python -m pytest tests/api/test_research_panels.py -x -q --tb=short                                     # wave 2 (backtest panels)
cd backend && .venv/bin/python -m pytest tests/api/test_portfolio_panels.py -x -q --tb=short                                     # wave 2 (portfolio panels)
cd backend && .venv/bin/python -m pytest tests/api/test_walkforward_sse.py -x -q --tb=short                                      # wave 3 (SSE)
cd frontend && pnpm build                                                                                                       # every frontend wave

# Phase gate (before /gsd-verify-work)
cd backend && .venv/bin/python -m pytest -x
cd frontend && pnpm build
```

Cross-module integrity checks:
- Every panel response is a strict server-owned DTO (extra="forbid"); api.ts consumes the exact types.
- RankIC and IC are separate fields/columns; optimizer output always renders baselines; reserved OOS visually distinct + honestly labeled.
- Paper approve/reject are idempotent append-only actions over paper.py — the only write surface of the phase.
- **Zero-execution-UI gate** (hard acceptance): no execute/order/submit/trade affordance in any panel (grep each panel source == 0); the RebalancePlan panel has NO execute control at all.
- Walk-forward SSE uses the durable job pattern (progress replay on reconnect); optimization/plan updates fan out via the existing shared SSE stream.

# Phase Success Criteria

- All 5 plans complete with their per-plan gates green; full backend suite green + frontend build green before /gsd-verify-work.
- UI-01 (ModelLibrary + WalkForward) + UI-02 (Optimization + RiskAttribution + RebalancePlan) backed by typed server-owned contracts; SC3 (SSE durable-job + fan-out) delivered.
- Zero execution authority holds in the UI; honest display (RankIC≠IC, baselines, OOS labeling) everywhere.

# Output

After each plan completes, create the matching summary at `.planning/phases/15-api-sse-frontend-panels/15-{NN}-SUMMARY.md` documenting what landed, the evidence, and any deviations. The phase gate is the full backend suite green + frontend build green before /gsd-verify-work.
