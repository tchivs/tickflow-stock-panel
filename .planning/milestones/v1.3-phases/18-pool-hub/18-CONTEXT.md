# Phase 18: 股池 Hub (Pool Hub) - Context

**Gathered:** 2026-08-04
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous smart discuss — user requested automated GSD flow)

<domain>
## Phase Boundary

**Goal**: Users can open a pool hub showing strategy cards with per-day pool counts, drill into each strategy's stock list (code, 开盘涨幅, 涨跌幅, 概念板块, 关联因子), filter by 概念, and highlight 交叉共振 — all research-only.

**Depends on**: Phase 17 (strategy results + 关联因子 hit_factors)

**Success Criteria** (must be TRUE):
1. User can open the pool hub and see strategy cards with当日 pool counts and drill into a per-strategy stock list backed by `screener_results/` persistence with a single as_of source of truth.
2. User can filter the pool by 概念 and see 交叉共振 (stocks hit by multiple auction strategies) highlighted.
3. No execution authority exists anywhere in the pool feature — no API endpoint, UI affordance, or service path can push a pool to a live broker.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion — Authorized Constraints

1. **Backend projection, not a new datastore.** Pool hub reads `screener_results/` Parquet persistence (existing `strategy_cache` single as_of source of truth — PITFALL #10). A pool-hub projection service computes per-strategy counts + per-stock rows (code/开盘涨幅/涨跌幅/概念板块/关联因子). No new DB.
2. **单 as_of 源.** All pool counts and drill-down lists derive from ONE as_of date's persisted results. No client-side recompute that could drift from a strategy card count to a drill-down list (PITFALL #10).
3. **交叉共振 = multi-strategy hits.** A stock is 交叉共振 when hit by ≥2 auction strategies — computed from the Phase 17 `hit_factors` list (STRAT-02 seam). Highlight in UI.
4. **概念筛选 from enriched/概念 columns.** The 概念板块 column comes from the enriched lake where available. Filtering is a projection over the current as_of pool.
5. **Zero execution authority (POOL-03).** The pool feature is a research-only projection: no API endpoint, UI button, or service path can push a pool to a live broker. Enforced at API boundary + no broker client imported anywhere in the feature.
6. **Frontend workspace.** New Pool page (or hub) composes: strategy cards → drill-down stock list → concept filter → 交叉共振 highlight. Consistent with existing Screener.tsx / ConceptAnalysis.tsx patterns and design tokens.
7. **日期导航 deferred to v2** (POOL-04). Single as_of view only in v1.3.

</decisions>

<code_context>
## Existing Code Insights

- `backend/app/strategy/factor_hits.py` — Phase 17 landed build_factor_hits/attach_factor_hits; `hit_factors` on every run_all row (STRAT-02 seam for 交叉共振).
- `backend/app/api/screener.py` — run_all endpoint persists results (strategy_cache) and returns rows with hit_factors.
- `screener_results/` — existing persistence dir in the data lake (research SUMMARY); strategy_cache single as_of.
- `frontend/src/pages/Screener.tsx` — strategy cards + results UI pattern.
- `frontend/src/pages/ConceptAnalysis.tsx` — concept data display pattern.
- Design tokens / brand: existing frontend components under frontend/src/components/.

</code_context>

<specifics>
## Specific Ideas

- Backend: `backend/app/services/pool_hub.py` — projection service: read persisted strategy results for as_of, build per-strategy pools + counts, per-stock rows with 概念板块 + hit_factors, 交叉共振 flag (≥2 hits), concept filter. API: `GET /api/pool/hub?as_of=...` (+ optional `concept` filter).
- Frontend: Pool page — strategy cards (name + 当日股池数), drill-down stock list table (code/开盘涨幅/涨跌幅/概念板块/关联因子), 概念 filter input, 交叉共振 rows highlighted (accent). Zero execution affordances.
- POOL-03 guard: no broker/order API import in pool_hub service; test asserts no execution path exists.

</specifics>

<deferred>
## Deferred Ideas

- 日期导航 (per-day historical pool browsing) → POOL-04 (v2)
- True auction match data columns → DATA-04 (v2)
- Additional auction strategies beyond core 3 → STRAT-04/05 (v2)
</deferred>
