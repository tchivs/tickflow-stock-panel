# Plan 15-04 Summary — Portfolio Panels Breadth: RiskAttribution + RebalancePlan (UI-02)

**Status:** complete · **Committed:** 3316241

## What landed

- `api/portfolio_panels.py` route bodies over `PortfolioRepository` + `paper`:
  - `GET /attribution` — evidence rows (exposure/contribution + drawdown), run_id/attribution_type/risk_model filters, reconciliation payload (server-owned, opaque to the browser).
  - `GET /rebalance-plans` (run_id filter), `GET /rebalance-plans/{id}/paper` (state + append-only transition ledger), `POST /rebalance-plans/{id}/approve` + `/reject` — idempotent append-only via `paper.approve`/`reject`, 404 on missing plan, 400 on invalid transition, `PaperActionResponse` carries `idempotent`.
- `api.ts` typed methods (`listAttribution`, `listRebalancePlans`, `getPaperState`, `approveRebalance`, `rejectRebalance`) + QK factories (`attribution`, `rebalancePlans`, `paperState`).
- `pages/portfolio/RiskAttribution.tsx` — evidence list + detail (signed components, reconciliation summary, **PSD-repair warning chip** surfaced from recorded provenance — never silent).
- `pages/portfolio/RebalancePlan.tsx` — plan header (as-of, run ref, output sha256), target vs discrete weights side by side with deviation, lot sizes + blocked instruments expandable, cash residue / turnover cost / RMSE metrics, **paper state machine**: state chip, append-only transition ledger, approve/reject buttons ONLY on a suggested/undecided plan. **No execute/order/submit control exists anywhere in the panel — not even disabled.**
- `Portfolio.tsx` nav entries (研究面板 → 优化运行 / 风险归因 / 再平衡计划).

## Evidence

- `tests/api/test_portfolio_panels.py` breadth green: attribution/plans/paper routes typed; approve appends ledger row; re-POST idempotent (same row, `idempotent: true`); reject-after-approve → 400; expired → 400; zero-execution gate asserted (no positions row written).
- Frontend `tsc -b` + `vite build` clean.
- Zero-execution-UI grep gate == 0 matches in all three portfolio panels.

## Deviations

None.
