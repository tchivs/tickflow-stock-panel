---
phase: 18-pool-hub
plan: 2
subsystem: ui
tags: [react, tanstack-query, playwright, pool-hub, 股池, 交叉共振, vite]

requires:
  - phase: 18-pool-hub (18-01)
    provides: "GET /api/pool/hub single-as_of projection: { as_of, updated_at, strategies: [{id,name,total,rows:[{symbol,code,open_gap,change_pct,concept_board,hit_factors,cross_resonance}]}], resonance_count }"
provides:
  - "PoolHubPage at /pool-hub with 股池 nav — single-as_of read-only workspace"
  - "StrategyCardGrid (当日池 N 只 / 股池统计中… / 当日无命中 / 数据不可用 / active states)"
  - "StockListTable drill-down with exact 代码|开盘涨幅|涨跌幅|概念板块|关联因子 columns + 交叉共振 highlight"
  - "ConceptFilter client-side projection (筛选后 N 只 / 共 M 只, no second fetch)"
  - "api.poolHub + QK.poolHub + PoolHub types"
  - "POOL-03 guard: e2e tests proving zero execution affordances / no mutating requests / no execution API in source"
affects: [19-guest-mode, POOL-04-v2-date-navigation]

actuals:
  tokens: 13500
  tasks: 3
  commits: 4

tech-stack:
  added: [lucide-react icons, framer-motion useReducedMotion]
  patterns:
    - "single-as_of no-drift: cards + drill rows from ONE QK.poolHub payload (PITFALL #10)"
    - "client-side concept projection over loaded payload; footer 共 {M} authoritative"
    - "server-derived 交叉共振: cross_resonance + hit_factors rendered, never recomputed"
    - "main-scoped Playwright POOL-03 guard (execution regex + interaction whitelist + request instrumentation)"

key-files:
  created:
    - frontend/src/pages/PoolHubPage.tsx
    - frontend/src/components/pool-hub/StrategyCardGrid.tsx
    - frontend/src/components/pool-hub/ConceptFilter.tsx
    - frontend/src/components/pool-hub/StockListTable.tsx
    - frontend/e2e/pool-hub.spec.ts
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/lib/queryKeys.ts
    - frontend/src/router.tsx
    - frontend/src/components/Layout.tsx

key-decisions:
  - "Drill-down is derived from the single QK.poolHub payload (no per-strategy fetch) — drill loading/error states appear during background refetch / stale-while-revalidate, keeping the no-drift invariant"
  - "数据不可用 cards need the strategy universe: page also queries api.screenerStrategies('stock') purely as the name source; counts and rows stay hub-payload-only"
  - "概念筛选 is entirely client-side: api.poolHub exposes the optional concept param for API parity, but the page never sends it (typing never fetches)"
  - "auto-select first strategy so the drill table is visible on entry; clicking any card (including zero-hit) drills"

requirements-completed: [POOL-01, POOL-02, POOL-03]

coverage:
  - id: D1
    description: "PoolHubPage renders from the single-as_of payload via api.poolHub + QK.poolHub (route /pool-hub, nav 股池, refresh, subtitle 数据日期, research-only footer)"
    requirement: POOL-01
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#populated hub renders strategy cards and drill-down table from one as_of payload"
        status: pass
    human_judgment: false
  - id: D2
    description: "Strategy card grid with 当日池 {N} 只 counts and all four card states (股池统计中… / 当日无命中 / 数据不可用 / active); zero-hit drills to an empty table; unavailable cards are disabled with tooltip"
    requirement: POOL-01
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#zero-hit strategy drills to 当日无命中 empty state"
        status: pass
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#strategy absent from the payload renders 数据不可用 with no click"
        status: pass
    human_judgment: false
  - id: D3
    description: "Drill-down stock list with exact columns 代码|开盘涨幅|涨跌幅|概念板块|关联因子 and footer 共 {M} 只 — card count and drill list derive from one payload"
    requirement: POOL-01
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#populated hub renders strategy cards and drill-down table from one as_of payload"
        status: pass
    human_judgment: false
  - id: D4
    description: "概念 filter is a client-side projection (筛选后 {N} 只 / 共 {M} 只), never triggers a second fetch; no-match renders 无符合「{概念}」的个股 + 清除筛选"
    requirement: POOL-02
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#concept filter projects client-side over the loaded payload with 筛选后/共 footer"
        status: pass
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#concept filter with no match renders 无符合「{概念}」的个股 with 清除筛选"
        status: pass
    human_judgment: false
  - id: D5
    description: "交叉共振 rows accent-highlighted with 交叉共振 · {N} 策略 badge + legend (server cross_resonance/hit_factors); 今日无交叉共振 none-state"
    requirement: POOL-02
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#交叉共振 row renders the badge and legend; single-hit row omits it"
        status: pass
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#no cross resonance renders 今日无交叉共振 footnote"
        status: pass
    human_judgment: false
  - id: D6
    description: "POOL-03: zero execution affordances on the pool surface, no mutating request while interacting, no <form> / execution-family API in page+component source"
    requirement: POOL-03
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#pool page renders zero execution affordances (POOL-03)"
        status: pass
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#pool page never issues a mutating request (POOL-03)"
        status: pass
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#pool page source contains no execution API call or form"
        status: pass
    human_judgment: false
  - id: D7
    description: "Accessibility/copy compliance: visible 概念筛选 label + aria-describedby, role=status/alert, +/− sign beside color, 交叉共振 badge beside accent tint, backstop structural assertions"
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts#accessibility and copy compliance on the pool surface"
        status: pass
    human_judgment: false
  - id: D8
    description: "Visual evidence for the five UI-SPEC backstop scalars (数据不可用 card, long-name truncate, missing-cell —, many-row scroll, long-concept wrap)"
    verification:
      - kind: e2e
        ref: "frontend/e2e/pool-hub.spec.ts-snapshots/pool-*.png (5 baselines committed)"
        status: pass
    human_judgment: true
    rationale: "Backstop scalars are human-judgment items per UI-SPEC #1154 — evidence (committed Playwright snapshots) is captured but end-of-phase human sign-off is required; automation alone must not silently pass them."

duration: 45min
completed: 2026-08-04
status: complete
---

# Phase 18 Plan 2: PoolHubPage Frontend Summary

**股池 (Pool Hub) single-as_of read-only workspace — strategy cards with 当日池数, exact five-column drill-down table, client-side 概念 filter, and 交叉共振 highlight — with an automated POOL-03 zero-execution guard and committed visual-regression evidence.**

## Performance

- **Duration:** 45 min
- **Started:** 2026-08-04 ~17:20 UTC+4
- **Completed:** 2026-08-04 18:08 UTC+4
- **Tasks:** 3 (tracer + 2 auto)
- **Files modified:** 10 (5 created, 5 modified) + 5 snapshot baselines
- **Tests:** 16 Playwright (desktop-chromium), all passing; `npx tsc --noEmit` exit 0

## Accomplishments

- **Data plumbing:** `api.poolHub` + `PoolHubRow/StrategyHub/PoolHubResponse` types + `QK.poolHub`; `/pool-hub` lazy route + 股池 nav.
- **Single-as_of no-drift:** card counts and drill rows render from ONE `QK.poolHub` payload (PITFALL #10); the strategy universe for `数据不可用` cards comes from `api.screenerStrategies` (names only, never counts).
- **Full component tree per UI-SPEC:** `StrategyCardGrid` (四态: 统计中/无命中/数据不可用/active), `ConceptFilter` (客户端投影, 不二次请求), `StockListTable` (精确五列 + 交叉共振 accent 行 + `交叉共振 · {N} 策略` 徽标 + legend).
- **Exact Simplified Chinese vocabulary:** 股池加载中… / 股池加载失败：{message}。请检查数据源后重试。 / 当日无股池结果 / 当日池 {N} 只 / 股池统计中… / 当日无命中 / 数据不可用 / 共 {M} 只 / 筛选后 {N} 只 / 共 {M} 只 / 无符合「{概念}」的个股 / 今日无交叉共振 / 本页面仅用于研究参考，不提供任何交易执行功能。
- **POOL-03 guard (Task 3):** main-scoped execution-family regex (买入|卖出|委托|下单|交易|buy|sell|order|trade|execute), interaction whitelist, request instrumentation (no non-GET, no order/trade/broker/portfolio endpoint), static source gate (no `<form>`, no execution API call, no mutating fetch verb).
- **Visual evidence:** 5 Playwright `toHaveScreenshot` baselines committed under `frontend/e2e/pool-hub.spec.ts-snapshots/` covering the UI-SPEC backstop scalars.

## Task Commits

1. **Task 1 (tracer): pool hub data plumbing + PoolHubPage shell + route/nav + tracer e2e** - `8f4eae2` (feat)
2. **Task 2: full pool-hub component tree — cards, concept filter, drill table + 交叉共振** - `a3c934c` (feat)
3. **Task 3: POOL-03 no-execution guard + a11y/copy compliance + visual evidence** - `a2345c2` (feat)

## Files Created/Modified

- `frontend/src/lib/api.ts` - PoolHubRow/PoolHubStrategy/PoolHubResponse types + `api.poolHub(asOf?, concept?)`
- `frontend/src/lib/queryKeys.ts` - `QK.poolHub(asOf?)` (manual refresh; not in SSE_INVALIDATE_PREFIXES)
- `frontend/src/pages/PoolHubPage.tsx` - composed workspace: header → ConceptFilter → StrategyCardGrid → StockListTable; motion reveal honors prefers-reduced-motion
- `frontend/src/components/pool-hub/StrategyCardGrid.tsx` - read-only card grid, four card states, 数据不可用 tooltip
- `frontend/src/components/pool-hub/ConceptFilter.tsx` - label + input + clear X + 清除筛选, aria-describedby
- `frontend/src/components/pool-hub/StockListTable.tsx` - exact columns, PctCell (fmtPct + priceColorClass), concept chips expand/collapse, STRATEGY_TAG_CLS factor tags, 交叉共振 row, footer + legend
- `frontend/src/router.tsx` - `/pool-hub` lazy route
- `frontend/src/components/Layout.tsx` - 股池 nav entry (Layers3)
- `frontend/e2e/pool-hub.spec.ts` - shell fixture + 16 tests (populated/empty/error/loading/filter/交叉共振/no-match/zero-hit/unavailable/无共振/POOL-03×3/a11y/drill-error/visual-evidence)
- `frontend/e2e/pool-hub.spec.ts-snapshots/` - 5 visual baselines

## Decisions Made

- **Drill-down derived from the hub payload** (no separate drill fetch): `股池明细加载中…` / `股池明细加载失败：{message}。请重试。` states are driven by background-refetch (stale-while-revalidate), preserving PITFALL #10.
- **Strategy universe for 数据不可用**: second query `api.screenerStrategies('stock')` supplies known strategy names only; counts and rows stay hub-payload-only.
- **Auto-select first strategy** so the drill table is immediately visible; zero-hit cards still drill to `当日无命中`.
- **api.poolHub keeps the optional `concept` param** for API parity with 18-01, but the page never sends it — projection is client-side.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Exact-match heading locator for 股池**
- **Found during:** Task 3 verification
- **Issue:** `getByRole('heading', { name: '股池' })` matched both the page `<h1>股池</h1>` and the drill `<h2>竞价多头 · 股池明细</h2>` (substring), intermittently tripping strict mode when the drill heading rendered before the assertion.
- **Fix:** `{ name: '股池', exact: true }`.
- **Files modified:** frontend/e2e/pool-hub.spec.ts
- **Verification:** 3 consecutive full-suite runs, 16/16 green.
- **Committed in:** a2345c2 (Task 3)

**2. [Rule 1 - Bug] `__dirname` undefined under Playwright ESM**
- **Found during:** Task 3
- **Issue:** the static source-gate test used `__dirname`, which is not defined in Playwright's ESM loader.
- **Fix:** use `process.cwd()` (Playwright runs from `frontend/`).
- **Files modified:** frontend/e2e/pool-hub.spec.ts
- **Committed in:** a2345c2 (Task 3)

**3. [Rule 1 - Bug] Concept chips collapse hid the long-concept chip under test**
- **Found during:** Task 3
- **Issue:** `锂电池隔膜` (6th concept) is behind the `+{N}` collapse, so the truncate-class assertion timed out.
- **Fix:** click the row's `+3` expand button before asserting the long chip.
- **Files modified:** frontend/e2e/pool-hub.spec.ts
- **Committed in:** a2345c2 (Task 3)

---

**Total deviations:** 3 auto-fixed (all Rule 1 test-robustness bugs; no scope creep, no plan rework)
**Impact on plan:** All fixes were within test code and did not change the shipped UI contract.

## Issues Encountered

- The `a3c934c` task-commit initially landed the `poolHub` method mid-`screenerRunAll` in api.ts (stale line anchor after the type insertion shifted lines); repaired immediately and re-verified with tsc before commit.
- Playwright visual baselines are environment-tied (Linux/Chromium); committed baselines are the reference for this repo's CI/verifier and can be regenerated with `--update-snapshots` if the runtime differs.

## User Setup Required

None - no external service configuration required. The API is mocked in e2e; the live page reads `GET /api/pool/hub` served by 18-01.

## Next Phase Readiness

- POOL-01/02/03 frontend complete and green against the documented 18-01 contract (sibling plan committed `23ce583`).
- Ready for end-of-phase human check: open `/pool-hub` and confirm the five backstop scalars against the committed snapshots (`frontend/e2e/pool-hub.spec.ts-snapshots/`).
- Deferred: guest/VIP masking (Phase 19, GUEST-01..02), date navigation (POOL-04, v2).

---
*Phase: 18-pool-hub*
*Completed: 2026-08-04*

## Self-Check: PASSED

- Created files verified on disk: `PoolHubPage.tsx`, `StrategyCardGrid.tsx`, `ConceptFilter.tsx`, `StockListTable.tsx`, `e2e/pool-hub.spec.ts`, `18-02-SUMMARY.md`.
- Commit hashes verified in git: `8f4eae2` (Task 1), `a3c934c` (Task 2), `a2345c2` (Task 3).
- Verification: `cd frontend && npx tsc --noEmit` exit 0; `npx playwright test e2e/pool-hub.spec.ts --project=desktop-chromium` 16/16 passing (3 consecutive runs).
