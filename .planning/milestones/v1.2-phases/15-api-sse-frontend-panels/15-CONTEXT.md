# Phase 15: API/SSE + Frontend Panels - Context

**Gathered:** 2026-08-01
**Status:** Ready for planning (UI phase — `workflow.ui_phase: true`, `ui_review: true`)

<domain>
## Phase Boundary

Phase 15 is the milestone's final phase: it surfaces the full v1.2 pipeline through **typed server-owned contracts** and **streaming progress**, with **ModelLibrary/WalkForward** panels in the Backtest workspace and **Optimization/RiskAttribution/RebalancePlan** panels in the Portfolio workspace. It is the milestone's UI surface for everything Phases 10-14 built (factors, multi-factor models, walk-forward/OOS, optimization runs, risk attribution, paper-rebalance suggestions).

Both requirements in scope: UI-01 (P2, Backtest workspace panels), UI-02 (P2, Portfolio workspace panels). Success criterion 3 adds SSE streaming: walk-forward runs stream progress over SSE through the durable job pattern, and optimization/plan updates fan out through the existing shared SSE stream.

**In scope:** UI-01, UI-02 (five panels), SSE streaming, typed DTOs, zero-execution-authority boundary in the UI.
**Out of scope:** live broker execution (forever out of scope); new backend features (all data surfaces already exist from Phases 10-14 — this phase only ADDS typed API routes + frontend panels over them); auto-rebalance scheduling (v2).

</domain>

<decisions>
## Implementation Decisions

### Typed Server-Owned Contracts (UI-01/02)
- Server-owned Pydantic DTOs first; frontend `api.ts` strictly consumes them.
- Reuse existing typed `api.ts` / `queryKeys.ts` / SSE hooks patterns (no rewrite).
- Phase 14 server-owned state + strict DTOs stable before frontend wiring.

### Panel Scope (UI-01/02)
- Backtest workspace: ModelLibrary (admitted factors + multi-factor models) + WalkForward (walk-forward/OOS results).
- Portfolio workspace: Optimization (immutable runs) / RiskAttribution (attribution) / RebalancePlan (paper-rebalance suggestions).
- Panels read immutable rows/artifacts (append-only tables + checksum-verified artifacts), never live module hand-off.

### SSE Streaming (success criterion 3)
- Walk-forward runs stream progress over SSE through the durable job pattern (existing `backtestTask.ts` SSE + reconnect pattern).
- Optimization/plan updates fan out through the existing shared SSE stream.
- Reconnect/idempotent consumption (durable job contract).

### Boundary & Honest Display (hard acceptance)
- Paper-rebalance panel: read-only display + human approve/reject actions (append-only audit).
- NO execute/order entry point anywhere in the UI (zero execution authority).
- Never label RankIC as generic IC; never present optimizer output as "optimal" without baselines; label selection-validation vs reserved OOS honestly.

### Claude's Discretion
- Exact DTO field sets, panel component structure, SSE event names, route paths.
- How the five panels organize into the existing workspace layouts (Backtest / Portfolio tabs).
- Whether ModelLibrary + WalkForward are one or two routes.

</decisions>

<code_context>
## Existing Code Insights

### Backend
- `backend/app/api/portfolio.py` — existing `/api/portfolio` router (accounts/positions/...); new read routes for optimization runs / attribution / rebalance plans / paper transitions.
- `backend/app/api/research.py` — existing `/api/research` router; new read routes for factor catalog / multi-factor models / walk-forward plans/folds/validated strategies.
- `backend/app/portfolio/repository.py` — PortfolioRepository (runs / attribution evidence / rebalance plans / paper transitions).
- `backend/app/research/repository.py` — ResearchRepository (factor catalog / models / composites / walk-forward).
- `backend/app/jobs/` — durable job pattern for SSE streaming (backtest task).
- `backend/app/contracts/` — existing Pydantic DTO conventions.

### Frontend
- `frontend/src/lib/api.ts` — typed API client (existing patterns).
- `frontend/src/lib/queryKeys.ts` — react-query keys.
- `frontend/src/lib/backtestTask.ts` — SSE + task cache + reconnect pattern.
- `frontend/src/pages/backtest/` — Backtest workspace pages (ResearchLibrary, StrategyOptimizer, ...).
- `frontend/src/components/portfolio/` — Portfolio components.

### Established Patterns
- Append-only rows + O_EXCL+fsync+sha256 artifacts (Phases 10-14).
- Typed server-owned DTOs; strict api.ts consumption; react-query.
- SSE durable job pattern with reconnect.

### Integration Points
- New read-only API routes under `/api/portfolio` + `/api/research` over existing repositories.
- New panels in `frontend/src/pages/backtest/` + `frontend/src/pages/portfolio/`.
- SSE stream wiring for walk-forward progress + optimization/plan fan-out.

</code_context>

<specifics>
## Specific Ideas

- ModelLibrary panel: admitted factors (verdicts, IC/ICIR/monthly evidence) + multi-factor models (weights, lineage).
- WalkForward panel: plans, folds, OOS results, validated strategies, ensemble signals.
- Optimization panel: immutable runs (weights, baselines, constraint stack, solver, status, failure reason).
- RiskAttribution panel: exposure/contribution evidence + drawdown attribution.
- RebalancePlan panel: plans (continuous vs discrete weights, RMSE) + paper state machine (approve/reject, append-only audit), NO execute affordance.

</specifics>

<deferred>
## Deferred Ideas

- Live broker execution — forever out of scope (platform boundary).
- Auto-rebalance scheduling (v2).
- New backend features — this phase only surfaces existing immutable data.
- Any execute/order affordance in the UI — never.

</deferred>
