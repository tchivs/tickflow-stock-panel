# Phase 15 — API/SSE + Frontend Panels — Complete

## Delivered

Five plans across four waves, all gates green:

| Wave | Plan | Deliverable |
|------|------|-------------|
| 0 | 15-02 | Server-owned strict DTOs (`contracts/panels.py`, `extra="forbid"`), both typed read routers scaffolded, TestClient app-state fixtures, UI-SPEC approved. Decision: **option-a** single DTO module. |
| 1 | 15-01 | Optimization panel end-to-end tracer: `OptimizationRunDTO` + GET routes → typed `api.ts` → panel with baselines (never "optimal" alone) + honest failure reason. |
| 2 | 15-03 | ModelLibrary + WalkForward panels (UI-01): IC and RankIC as **separate** fields; reserved OOS visually distinct + honestly labeled. |
| 2 | 15-04 | RiskAttribution + RebalancePlan panels (UI-02): attribution + PSD provenance; paper state machine with approve/reject **only for suggested state**; no execute affordance. |
| 3 | 15-05 | Walk-forward SSE streaming (durable `_WfJob` + replay on reconnect); optimization/plan fan-out via shared SSE stream. |

## Acceptance evidence

- **Backend suite**: `1328 passed, 2 skipped, 0 failed` (full `pytest -x`).
- **Frontend**: `tsc -b && vite build` green.
- **Panel API tests**: `tests/api/` — 43 passed (DTO strictness, tracer, breadth, SSE).
- **Zero-execution-UI gate**: `grep -nE 'execute|placeOrder|submitOrder|trade'` across all 5 panels + SSE module == 0 matches.
- **Honest display**: RankIC ≠ IC (separate DTO fields/columns); optimizer runs always render baselines; reserved OOS labeled "仅评估一次"; RebalancePlan list chip neutral (no misleading live-state assertion).

## Artifacts

- `backend/app/contracts/panels.py` — 18 strict DTOs
- `backend/app/api/research_panels.py` + `portfolio_panels.py` + `walkforward_sse.py` — typed READ + paper POST + SSE routes
- `frontend/src/pages/backtest/{ModelLibrary,WalkForward}.tsx`, `frontend/src/pages/portfolio/{Optimization,RiskAttribution,RebalancePlan}.tsx`
- `frontend/src/lib/api.ts` + `queryKeys.ts` — typed methods + QK factories + `SSE_INVALIDATE_PREFIXES` (`optimization-runs` / `rebalance-plans` / `paper`)
- `backend/tests/api/` — conftest + 3 test files (43 tests)

## Boundary

- **Zero execution authority** held: no execute/order/submit/trade affordance anywhere; RebalancePlan panel has no such control at all.
- Paper approve/reject are the only write surface — idempotent append-only, never a live path.
- No new backend features; all data surfaces are Phases 10-14 immutable rows/artifacts read via typed DTOs.
