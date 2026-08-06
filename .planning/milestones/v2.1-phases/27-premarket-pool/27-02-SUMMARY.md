---
phase: 27-premarket-pool
plan: 2
subsystem: ui
tags: [react, react-query, playwright, premarket-preview, pool-hub, degraded-badge]

# Dependency graph
requires:
  - phase: 27-01
    provides: GET /api/pool/premarket 只读端点 (available/window/provisional/degraded/probe/strategies 契约) + guest 白名单 + premarket_snapshot 服务
provides:
  - poolPremarket api client + PremarketPoolResponse 类型 (extends PoolHubResponse)
  - QK.poolPremarket (不入 SSE_INVALIDATE_PREFIXES) + usePremarketPool hook (staleTime 30s)
  - PoolHubPage 盘前预览分支 (showPremarket/showPremarketEmpty) + 窗口标注 + 诚实空态 + degraded 透传
  - AuctionColumnStatusBadge degraded 诚实警告分支 (绝不渲染「竞价数据可用」)
  - e2e/premarket-pool.spec.ts (五用例) + docs/features.md 盘前预览小节
affects: [verify-work, Phase 28, 任何盘前/股池后续工作]

# Actuals (#2632) — pairs with the plan's `estimate` (56000) to calibrate future estimates.
actuals:
  tokens: 6500    # chars/4 over the realized diff (25954 chars / 4)
  tasks: 3        # tasks completed
  commits: 3      # commits made (f225393, 7650de5, e4e8f04)

# Tech tracking
tech-stack:
  added: []       # 零新增 npm 依赖 (既有 @tanstack/react-query + lucide-react)
  patterns:
    - "池页双源路由: showPremarket ? premarket.data : poolQuery.data — 预览 payload 复用 hub 渲染路径"
    - "degraded prop 强制诚实徽标分支 — 服务端冻结 probe 判定驱动, 不依赖 live probe"
    - "e2e 独立 spec 复制 installShell (不 import 跨文件耦合), 后注册 route 覆盖四态"

key-files:
  created:
    - frontend/e2e/premarket-pool.spec.ts
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/lib/queryKeys.ts
    - frontend/src/lib/useSharedQueries.ts
    - frontend/src/pages/PoolHubPage.tsx
    - frontend/src/components/pool-hub/StockListTable.tsx
    - docs/features.md

key-decisions:
  - "盘前判定用 dates 白名单 (hasTodayEod = today ∈ /api/pool/dates) 而非时钟 — 15:35 EOD 后自动回退 hub, DateNavigator 保持 EOD-only"
  - "showPremarketEmpty 时零池/策略网格短路 (盘前空态优先, 不混排昨日 hub 流)"
  - "QK.poolPremarket 不入 SSE_INVALIDATE_PREFIXES (定时快照, 行情 tick 不重拉预览); staleTime 30s 对齐服务端 probe 30s TTL"
  - "AuctionColumnStatusBadge degraded prop 置于 hasReal 之前 — degraded 时绝不渲染「竞价数据可用」"

patterns-established:
  - "盘前预览 = 独立端点 + 独立 key + 独立空态, 与 EOD 归档物理分离 (PIT-5 镜像)"
  - "诚实标注词: 盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿 / 仅派生列 · 竞价数据源未配置"

requirements-completed: [PM-04]

# Coverage metadata (#1602) — drives deterministic UAT routing in verify-work.
coverage:
  - id: D1
    description: "查询链路 — api.poolPremarket() (GET /api/pool/premarket) + QK.poolPremarket (不入 SSE) + usePremarketPool hook (enabled/staleTime 30s/retry 1)"
    requirement: PM-04
    verification:
      - kind: other
        ref: "cd frontend && npm run build (tsc -b && vite build) 全绿; grep poolPremarket api.ts(1)/queryKeys.ts(1)/useSharedQueries.ts(1)"
        status: pass
    human_judgment: false
  - id: D2
    description: "PoolHubPage 盘前分支 — viewingToday ∧ available ∧ window=pre_open ∧ !hasTodayEod → 预览池 + 窗口标注「盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿」; showPremarketEmpty → 「今日盘前预览尚未生成」空态; degraded → 页面标注「仅派生列 · 竞价数据源未配置」; 15:35 (today∈dates) 回退 hub"
    requirement: PM-04
    verification:
      - kind: e2e
        ref: "frontend/e2e/premarket-pool.spec.ts#PM-04: 盘前预览 + 窗口标注 / 诚实空态 / degraded / 15:35 回退 — 4 passed"
        status: pass
    human_judgment: false
  - id: D3
    description: "AuctionColumnStatusBadge degraded prop — 置于 hasReal 之前强制诚实警告分支「仅展示派生列 · 竞价数据源未配置」, 绝不渲染「竞价数据可用」"
    requirement: PM-04
    verification:
      - kind: e2e
        ref: "frontend/e2e/premarket-pool.spec.ts#PM-04: degraded 徽标诚实 — getByText('竞价数据可用') count 0"
        status: pass
    human_judgment: false
  - id: D4
    description: "e2e 五用例 — 盘前预览+标注 / available:false 诚实空态 / degraded 徽标诚实 / 15:35 回退 hub / DateNavigator EOD-only (dates 白名单只列 EOD 日)"
    requirement: PM-04
    verification:
      - kind: e2e
        ref: "cd frontend && npx playwright test e2e/premarket-pool.spec.ts — 5 passed (desktop-chromium), 10 skipped (非桌面 project)"
        status: pass
    human_judgment: false
  - id: D5
    description: "docs/features.md「盘前预览 (Premarket Preview)」小节 — 09:26 job → premarket_results 独立存储 (绝不写 strategy_cache/screener_results), window/provisional/degraded 诚实标注, GET /api/pool/premarket 只读, DateNavigator EOD-only"
    requirement: PM-04
    verification:
      - kind: other
        ref: "grep 盘前预览 docs/features.md(4); grep premarket_results docs/features.md(1); docs/strategy.md 零改动; backend tests/test_pool_eod_job.py 4 passed (回归 smoke)"
        status: pass
    human_judgment: false

# Metrics
duration: 35min
completed: 2026-08-06
status: complete
---

# Phase 27 Plan 2: 盘前预览前端 (Premarket Pool Frontend) Summary

**盘前预览垂直切片 — PoolHubPage「最新」视图在 09:26-15:35 展示 pre_open 预览池 (独立 `GET /api/pool/premarket` 端点, 窗口标注「盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿」+ 诚实空态 + degraded 徽标), 15:35 EOD 后自动回退既有 `/api/pool/hub` 流; DateNavigator 保持 EOD-only (PIT-5)**

## Performance

- **Duration:** 35 min (不含 27-01 前置门等待)
- **Started:** 2026-08-06 (Wave 1 并行启动, 等待 Executor27A 合入端点契约后开工)
- **Completed:** 2026-08-06
- **Tasks:** 3
- **Files modified:** 6 (5 前端 + 1 文档)

## Accomplishments
- **查询链路**: `api.poolPremarket()` + `PremarketPoolResponse` (extends PoolHubResponse + window/provisional/degraded/probe) + `QK.poolPremarket` (不入 SSE_INVALIDATE_PREFIXES) + `usePremarketPool` hook (enabled 控制 / staleTime 30s / retry 1)
- **视图判定**: PoolHubPage 在「最新」视图下以 `viewingToday ∧ available===true ∧ window==='pre_open' ∧ !hasTodayEod` 渲染预览池 — 预览 payload 为 hub 同形状投影, 复用既有 asOf/mode/activeStrategy/StrategyCardGrid/ConceptFilter/StockListTable 渲染路径; `today ∈ /api/pool/dates` 时 (15:35 EOD 后) 自动回退 hub
- **诚实标注**: 窗口标注「盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿」+ degraded 追加「仅派生列 · 竞价数据源未配置」; available:false → 「今日盘前预览尚未生成」空态 (200 语义, 非 404, 非零池伪装); AuctionColumnStatusBadge 新增 `degraded` prop 强制诚实警告分支 (绝不渲染「竞价数据可用」)
- **DateNavigator EOD-only**: dates 白名单仍来自 `/api/pool/dates` (EOD 快照日), `DateNavigator.tsx` 零改动, 盘前预览绝不冒充归档日 (PIT-5)
- **e2e + 文档**: `premarket-pool.spec.ts` 五用例全绿; `docs/features.md` 补「盘前预览」小节 (诚实标注词)

## Task Commits

Each task was committed atomically:

1. **Task 1: PM-04 全链路垂直切片 (api + QK + hook + 页面分支 + 徽标 degraded)** - `f225393` (feat)
2. **Task 2: PM-04 e2e (五用例: 预览/空态/降级/15:35 回退/DateNavigator EOD-only)** - `7650de5` (test, 含 PoolHubPage 空态短路修正)
3. **Task 3: docs/features.md 盘前预览小节** - `e4e8f04` (docs)

**Plan metadata:** 27-01 由 Executor27A 合入 (`8063b95`/`8bdb35e`/`3cfad7b`), 27-02 前端三提交如上; 阶段文档提交 `b5742d7` (27-01 状态) 与本次最终状态提交分离。

## Files Created/Modified
- `frontend/src/lib/api.ts` - `PremarketPoolResponse` 接口 + `poolPremarket()` GET 方法 (只读, 走既有 request helper)
- `frontend/src/lib/queryKeys.ts` - `QK.poolPremarket = ['pool-premarket']` (不入 SSE_INVALIDATE_PREFIXES)
- `frontend/src/lib/useSharedQueries.ts` - `usePremarketPool(opts)` hook (enabled/staleTime 30s/retry 1)
- `frontend/src/pages/PoolHubPage.tsx` - `viewingToday`/`hasTodayEod`/`showPremarket`/`showPremarketEmpty` 判定 + 窗口标注 + 盘前空态 + degraded 透传 + 空态时零池/网格短路
- `frontend/src/components/pool-hub/StockListTable.tsx` - `AuctionColumnStatusBadge` 新增 `degraded` prop → 强制诚实警告分支
- `frontend/e2e/premarket-pool.spec.ts` (新) - 独立 spec 复制 installShell, 五用例 mock 四态
- `docs/features.md` - 「🕗 盘前预览 (Premarket Preview)」小节

## Decisions Made
- 盘前判定消费 dates 白名单 (`hasTodayEod = today ∈ dates`) 而非墙钟 — 15:35 EOD 快照落盘后自动回退 hub, 判定可 e2e 稳定复现
- `showPremarketEmpty` 时零池/策略网格分支短路 — 盘前空态优先, 不把昨日 hub 流混排在「今日盘前预览尚未生成」旁 (Rule 3 修正, 原计划只守卫了 available:false 分支)
- `QK.poolPremarket` 不入 `SSE_INVALIDATE_PREFIXES` — 盘前预览是定时快照 (09:26 job), 行情 tick 不重拉; staleTime 30s 对齐服务端 probe 30s TTL
- 徽标 `degraded` 分支置于 `hasReal` 之前 — degraded 时绝不渲染「竞价数据可用」, 服务端冻结 probe 判定驱动, 不依赖 live probe

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] showPremarketEmpty 时 hub 流策略网格未短路**
- **Found during:** Task 2 (设计 e2e 诚实空态用例时发现)
- **Issue:** 计划 step 7 的 `data = showPremarket ? premarket.data : poolQuery.data` 在 showPremarketEmpty (premarket available:false) 时回退到 hub payload — 而 hub payload 有 strategies, 导致策略网格与「今日盘前预览尚未生成」空态同时渲染, 空态被淹没 (e2e Test 2 会失败)
- **Fix:** 零池分支与策略网格渲染条件均加 `!showPremarketEmpty` 守卫 — 盘前空态优先, 不混排昨日 hub 流
- **Files modified:** frontend/src/pages/PoolHubPage.tsx
- **Verification:** e2e Test 2「诚实空态」断言 `当日无股池结果`/`当日池` count 0 通过; `npm run build` 绿
- **Committed in:** 7650de5 (Task 2 commit)

### 前置门等待 (非偏差)

27-02 `depends_on: [27-01]` 但 Wave 1 并行启动 — Task 1 `<precondition>` grep 门首次检查未命中 (27-01 端点未合入), 按协议 halt 等待; Executor27A 合入 `3cfad7b` (GET /api/pool/premarket + guest 白名单) 后重检通过, 正常开工。零代码影响, 已与 Executor27A 通过 hub 协调。

---

**Total deviations:** 1 auto-fixed (Rule 3 blocking)
**Impact on plan:** 修正使盘前诚实空态成为主导视图, 符合计划 PIT-2 镜像意图; 无 scope creep。

## Issues Encountered
- 27-01 端点契约未在 Wave 1 启动时立即可用 — 前置门 halt + hub 协调 Executor27A, 合入后重检通过 (已记录于 Deviations)

## User Setup Required

None - 无外部服务配置; 零新增 npm 依赖 (既有 @tanstack/react-query + lucide-react)。

## Next Phase Readiness
- PM-04 前端全链路可用: 盘前预览池 + 窗口标注 + 诚实空态 + degraded 徽标 + DateNavigator EOD-only
- e2e 五用例为 verify-work 提供确定性 UAT 路由 (coverage 块 D1-D5)
- 遗留: 盘前真实竞价列注入 (tier-2) 依赖外部实时竞价源, 未实现 (需求 Out of Scope, 诚实降级已交付)

## Self-Check: PASSED

- 8/8 created/modified files exist (5 前端 + 1 e2e + 1 文档 + 1 SUMMARY)
- 3/3 task commits exist: `f225393` (feat), `7650de5` (test), `e4e8f04` (docs)
- 验证门: `npm run build` 全绿 (tsc -b + vite build); `npx playwright test e2e/premarket-pool.spec.ts` 5 passed; 后端回归 smoke 30 passed (test_premarket_pool + test_guest_masking)
- DateNavigator.tsx / Watchlist.tsx 零改动; 工作树仅剩用户 Watchlist.tsx 未提交

---
*Phase: 27-premarket-pool*
*Completed: 2026-08-06*
