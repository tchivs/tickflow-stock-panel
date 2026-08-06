---
phase: 26-auction-history-chart
plan: 2
subsystem: ui
tags: [echarts, react-query, auction, playwright, chart, empty-state]

requires:
  - phase: 26-auction-history-chart
    plan: 1
    provides: "CHART-01 GET /api/kline/auction/history read-only endpoint contract (AuctionHistoryRow, available/probe/mode envelope, honest 200 available:false)"
provides:
  - "CHART-02 个股弹窗「竞价历史」toggle — ECharts 双轴柱线图 (柱=竞价量/股, 线=竞价金额/元) + 09:15-09:25 窗口标注 + 诚实空态"
  - "查询链路: api.auctionHistory + QK.auctionHistory + useAuctionHistory (staleTime 5min, 不入 SSE 无效刷新)"
affects: [26-auction-history-chart, verify-work, future auction UI]

actuals:
  tokens: 5566
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "ECharts dual-yAxis single-grid chart (bar=left/volume, line=right/amount) with useChartTheme + init/ResizeObserver/dispose lifecycle (mirrors EChartsIntraday)"
    - "Honest empty-state discipline: probe not available / available:false / rows empty → EmptyState, never zero-value bars"
    - "Historical-immutable query: staleTime 5min + key excluded from SSE_INVALIDATE_PREFIXES"

key-files:
  created:
    - frontend/src/components/AuctionHistoryChart.tsx
    - frontend/e2e/auction-history.spec.ts
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/lib/queryKeys.ts
    - frontend/src/lib/useSharedQueries.ts
    - frontend/src/components/StockPanel.tsx
    - frontend/src/components/StockPreviewDialog.tsx

key-decisions:
  - "Integration point = StockPreviewDialog top-bar third toggle (镜像 分时 button) + StockPanel showAuction prop — one change applies to all pages mounting the dialog; Watchlist.tsx untouched"
  - "AuctionHistoryChart queries days=120 explicitly (more history = more complete trend; server cap 120)"
  - "Unit labels exposed as DOM text (柱·竞价量(股) / 线·竞价金额(元)) + window chip so e2e can assert 股/元/09:15-09:25 without relying on canvas text"
  - "e2e opens dialog via /screener drill-down (B1 revision — /pool-hub does not mount StockPreviewDialog)"

patterns-established:
  - "Dual-axis bar/line chart component pattern with DOM unit legend + window annotation chip for testable canvas-adjacent text"
  - "Playwright installShell with default empty auction-history route + per-test post-registration override (later route wins)"

requirements-completed: [CHART-02]

coverage:
  - id: D1
    description: "CHART-02 query chain — api.auctionHistory(symbol, days) GET /api/kline/auction/history, QK.auctionHistory factory excluded from SSE_INVALIDATE_PREFIXES, useAuctionHistory hook (enabled:!!symbol, staleTime 5min)"
    requirement: CHART-02
    verification:
      - kind: integration
        ref: "cd frontend && npm run build (tsc -b strict type gate)"
        status: pass
      - kind: other
        ref: "grep auctionHistory in api.ts/queryKeys.ts + SSE_INVALIDATE_PREFIXES exclusion"
        status: pass
    human_judgment: false
  - id: D2
    description: "AuctionHistoryChart dual-axis ECharts — bar=auction_volume (left axis, 股), line=auction_amount (right axis, 元), category x=date, 09:15-09:25 window annotation, role=img + aria-label, loading/error copy"
    requirement: CHART-02
    verification:
      - kind: e2e
        ref: "frontend/e2e/auction-history.spec.ts#有数据: 双轴柱线图渲染 + 轴单位 + 09:15-09:25 窗口标注"
        status: pass
    human_judgment: false
  - id: D3
    description: "Honest empty state — probe not available / available:false / rows empty → EmptyState「无历史竞价数据」with 数据源未配置 degradation hint; guest → empty (zero volume/price leak); never zero-value bars"
    requirement: CHART-02
    verification:
      - kind: e2e
        ref: "frontend/e2e/auction-history.spec.ts#available:false → 诚实空态「无历史竞价数据」+ 无画布"
        status: pass
      - kind: e2e
        ref: "frontend/e2e/auction-history.spec.ts#probe 非 available → 空态 + 降级窗口标注「数据源未配置」"
        status: pass
      - kind: e2e
        ref: "frontend/e2e/auction-history.spec.ts#guest → 空态 (量/价零泄露)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Integration — StockPreviewDialog「竞价历史」toggle (aria-pressed) + showAuction state → StockPanel showAuction prop → conditional AuctionHistoryChart in the same slot as StockIntradayChart"
    requirement: CHART-02
    verification:
      - kind: e2e
        ref: "frontend/e2e/auction-history.spec.ts (openPreviewDialog helper asserts toggle visible inside dialog)"
        status: pass
      - kind: other
        ref: "grep showAuction in StockPanel.tsx + 竞价历史 in StockPreviewDialog.tsx"
        status: pass
    human_judgment: false
  - id: D5
    description: "Derived-column discipline — AuctionHistoryChart renders only real auction_volume/auction_amount; auction_unmatched_amount never imported/rendered (Phase 23 grouping rule)"
    requirement: CHART-02
    verification:
      - kind: other
        ref: "grep auction_unmatched_amount across plan frontend files = 0 occurrences"
        status: pass
    human_judgment: false

duration: 38min
completed: 2026-08-06
status: complete
---

# Phase 26 Plan 2: Frontend — Auction History Chart (CHART-02)

**个股弹窗第三开关「竞价历史」— ECharts 双轴柱线图 (柱=竞价量/股, 线=竞价金额/元) + 09:15-09:25 窗口标注 + 诚实空态 (probe 非 available / available:false / rows 空 / guest → EmptyState, 绝不零值柱冒充), 全站挂 StockPreviewDialog 的页面一改全生效, Watchlist.tsx 零触碰。**

## Performance

- **Duration:** ~38 min (含等待 26-01 并行合入)
- **Started:** 2026-08-06T07:10:00Z
- **Completed:** 2026-08-06T07:48:00Z
- **Tasks:** 2
- **Commits:** 2
- **Files modified:** 7 (2 created, 5 modified)

## Accomplishments

- **CHART-02 全链路垂直切片**: `api.auctionHistory` (GET /api/kline/auction/history) + `QK.auctionHistory` (不入 SSE_INVALIDATE_PREFIXES) + `useAuctionHistory` hook (enabled:!!symbol, staleTime 5min) — 历史不可变数据不随行情 tick 无效刷新。
- **AuctionHistoryChart 双轴柱线图**: 单 grid 双 yAxis — 左轴柱 = `auction_volume` (股), 右轴线 = `auction_amount` (元), x = date 类别轴; 只画真实两列, `auction_unmatched_amount` 零引用 (Phase 23 分组纪律); 生命周期镜像 EChartsIntraday (init/ResizeObserver/dispose + useChartTheme)。
- **诚实空态 D6**: probe 非 available → EmptyState「无历史竞价数据」+ 降级 hint「需配置集合竞价数据源 · 窗口 09:15-09:25（数据源未配置）」; available:false / rows 空 →「需配置集合竞价数据源并开启 EOD 竞价同步」; guest → 空态零量价泄露。绝不渲染零值柱。
- **窗口标注**: 图表头部 chip「窗口 09:15-09:25」+ tooltip 首行「窗口 09:15-09:25」+ 轴单位 DOM 标注「柱·竞价量(股) / 线·竞价金额(元)」— e2e 可断言。
- **aria/文案**: 容器 role="img" + aria-label="历史竞价量/金额趋势图"; 加载中/错误文案镜像 StockDailyKChart (加载中… / 竞价历史加载失败)。
- **e2e 四用例**: mock `/api/kline/auction/history` 三态 (有数据 → 图渲染 + 单位 + 窗口标注; available:false → 空态 + 无画布; probe 非 available → 空态 + 「数据源未配置」; guest → 空态 + 零量价) — 4 desktop 全绿 (8 skip: mobile/host 项目)。
- **零新 npm 依赖**; 未触碰 `frontend/src/pages/Watchlist.tsx`; 零后端改动。

## Task Commits

Each task was committed atomically:

1. **Task 1: CHART-02 全链路垂直切片 — api client + query key + hook + AuctionHistoryChart + StockPanel prop + StockPreviewDialog toggle** - `edc4a4d` (feat)
2. **Task 2: CHART-02 e2e — mock 三态锁死图渲染与诚实空态** - `51d53d3` (test)

## Files Created/Modified

- `frontend/src/components/AuctionHistoryChart.tsx` - 新建双轴柱线图组件 (真实量/额 + 诚实空态 + 窗口标注 + aria)
- `frontend/e2e/auction-history.spec.ts` - 新建四用例 e2e (installShell 复制自 pool-hub.spec + /screener 钻取开弹窗)
- `frontend/src/lib/api.ts` - 新增 AuctionHistoryRow/AuctionHistoryResponse 接口 + api.auctionHistory 方法
- `frontend/src/lib/queryKeys.ts` - 新增 QK.auctionHistory 工厂 (不入 SSE_INVALIDATE_PREFIXES)
- `frontend/src/lib/useSharedQueries.ts` - 新增 useAuctionHistory hook
- `frontend/src/components/StockPanel.tsx` - 新增 showAuction prop + 条件渲染 AuctionHistoryChart
- `frontend/src/components/StockPreviewDialog.tsx` - 新增 showAuction state + 「竞价历史」toggle (Gavel) + 透传 StockPanel

## Decisions Made

- 集成点 = StockPreviewDialog 顶栏第三开关 + StockPanel `showAuction` prop (镜像「分时」toggle 形态 + aria-pressed), 与 `showIntraday` 独立可并列 — 全站挂该弹窗的页面一改全生效。
- `useAuctionHistory(symbol, 120)` — days=120 显式 (更多历史 = 更完整趋势; 服务端上限 120)。
- 轴单位 + 窗口标注以 DOM 文本渲染 (非仅 canvas 轴标签) — 让 e2e 能断言「股/元/09:15-09:25」, 不依赖 canvas 内文本。
- e2e 在 /screener 打开弹窗 (B1 修订): 注入 strategy-pool localStorage → 点策略卡 → 点 ScreenerTable:173 行情行; /pool-hub 不挂载 StockPreviewDialog。
- e2e installShell 复制自 pool-hub.spec (独立文件, 不 import 跨文件耦合); 默认空态 auction-history 路由 + 后注册用例覆盖 (Playwright 后注册优先)。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] echarts 类型导出名与计划假设不符**
- **Found during:** Task 1 (AuctionHistoryChart 组件编写)
- **Issue:** 计划要求 `import type { TopLevelFormatterParams } from 'echarts'`, 但 echarts 5.6.0 根包不导出该类型 (仅 `TooltipComponentFormatterCallbackParams` 别名导出); `CallbackDataParams` 亦不在根导出。
- **Fix:** 改用根包实际导出的 `TooltipComponentFormatterCallbackParams` (= TopLevelFormatterParams); tooltip 日期字段用 `CallbackDataParams.name` (类别轴值), 而非不存在的 `axisValue`。
- **Files modified:** frontend/src/components/AuctionHistoryChart.tsx
- **Verification:** `npm run build` (tsc -b) 绿
- **Committed in:** edc4a4d (Task 1 commit)

**2. [Rule 1 - Bug] 行号引用漂移 (B2 修订已覆盖, 执行时按名定位)**
- **Found during:** Task 1 (read_first 阶段)
- **Issue:** 计划 read_first 行号有多处偏移 (queryKeys SSE 实际 L218 而非 L172; include_router 在 main.py:850 而非 849)。
- **Fix:** 按符号名定位 (grep 而非行号), 未影响实现。
- **Files modified:** 无
- **Verification:** 结构 grep 全部命中
- **Committed in:** — (无代码变更)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug/line-drift, 无 scope creep)
**Impact on plan:** 均为纯类型/定位修正, 不影响功能与验收。

## TDD Gate Compliance

- 计划 Task 1/2 均标 `tdd="true"`, 但项目硬约束 **无 vitest** (前端验证 = `npm run build` + Playwright e2e)。行为测试由 Task 2 的 `e2e/auction-history.spec.ts` (四用例) 承担, RED→GREEN 提交对不适用。无 `test(...)` RED 提交 — 已在计划内按 no-vitest 约束设计, 非遗漏。

## Issues Encountered

- 26-02 Task 1 `<precondition>` (26-01 端点存在) 在启动时未满足 — Executor26A 并行执行 26-01, 等待其 `dc70f0e` 合入后 gate 转绿, 随后正常执行。无阻塞性事故。
- Playwright 首次运行时 vite webServer 自动拉起; 4 desktop 用例 (含 /screener 钻取路径) 全部一次通过。

## Known Stubs

None — 诚实空态是本设计的预期行为 (当前湖 0 分区, UI 显式 EmptyState), 不是未完成占位。

## Threat Flags

None — 全部威胁已由计划 `<threat_model>` 覆盖并按 mitigate 实现: guest 空态零泄露 (D5 依赖 26-01 掩码), installShell unhandled 大声失败 + 全 GET-only 断言 (T-26-02-02), 派生列不混排 (T-26-02-03, grep 0 命中), Watchlist.tsx 零触碰 (T-26-02-04, git status 仅剩用户 M), 历史 key 不入 SSE 无效刷新 (T-26-02-05)。

## Next Phase Readiness

- CHART-02 前端全链路就绪: 查询链路 + 双轴图 + 诚实空态 + 四态 e2e。未来配置真实 auction 数据源并开启 EOD 竞价同步后, 图自动点亮 (无需前端改动)。
- 26-01 (后端) 已合入 (dc70f0e/81e9c25/06944ed), 后端回归 36 passed。
- Watchlist.tsx 用户未提交改动保持原样。

## Self-Check: PASSED

- 2 created + 5 modified files verified present (`git status` + file listing).
- Task commits verified: `edc4a4d`, `51d53d3` in `git log`.
- `npm run build` green; `npx playwright test e2e/auction-history.spec.ts` 4 passed / 8 skipped; backend regression `pytest tests/test_auction_history.py tests/test_guest_masking.py -x -q` 36 passed.
- Final `git status` shows only the user's `frontend/src/pages/Watchlist.tsx` uncommitted.

---
*Phase: 26-auction-history-chart*
*Completed: 2026-08-06*
