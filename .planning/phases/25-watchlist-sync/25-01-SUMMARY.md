---
phase: 25-watchlist-sync
plan: 1
subsystem: ui
tags: [react, react-query, watchlist, pool-hub, lucide-react]

# Dependency graph
requires:
  - phase: 24
    provides: 历史/最新股池行投影 (row.symbol 全后缀, PoolHubPage/StockListTable 结构, auction_columns)
  - phase: 21
    provides: 服务端自选体系 (watchlist.parquet + /api/watchlist CRUD + QK.watchlist 共享缓存)
provides:
  - 股池钻取面 VIP 星标 (WATCH-01) — 实心/空心 + aria + pending 禁用 + toggle 双 key 失效
  - 「只看自选」过滤开关 (WATCH-02) — 与概念筛选 AND, total 权威, 诚实空态, storage 偏好持久化
  - 共享 QK.watchlist 复用的 join 契约 (WATCH-03) — row.symbol 全等, 无独立存储
  - 批量加可见行 (WATCH-04) — scope=filteredRows, useWatchlistBatchAdd 复用, toast 反馈
affects: [25-02 (e2e + docs), Watchlist 页/策略页/个股弹窗 (共享 QK.watchlist 失效即一致)]

# Actuals (#2632) — pairs with the plan's `estimate` (chars/4 over realized diff, not harness tokens).
actuals:
  tokens: 3594
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "react-query 双门控 enabled: !!data && mode==='vip' 防 guest 误发受保护端点 (D4/P2)"
    - "受控 props 下放 (watchlistSet/onToggleWatchlist/watchlistPending) 镜像 ScreenerTableProps"
    - "storage kv<boolean> UI 偏好键 (绝不存 symbol 清单)"

key-files:
  created: []
  modified:
    - frontend/src/lib/storage.ts
    - frontend/src/pages/PoolHubPage.tsx
    - frontend/src/components/pool-hub/StockListTable.tsx

key-decisions:
  - "watchlist 查询 enabled: !!data && mode === 'vip' 双门控 (D4/P2) — mode 由 data 派生回退 vip, data 未落地不误发"
  - "filteredRows 重构为单一 base 变量 (概念投影 → watchlistOnly AND), 规避早退路径绕过 (REVIEW W2)"
  - "批量 scope = filteredRows 可见行 (display_limit 内), 绝不按 activeStrategy.total (D6/H8)"
  - "watchlistOnly 开启时隐藏批量按钮 (可见行全在自选, 语义最诚实 D6)"
  - "watchlistPending = toggleWatchlist.isPending || watchlist.isPending || watchlist.isError (H9 fail-closed)"

requirements-completed: [WATCH-01, WATCH-02, WATCH-03, WATCH-04]

coverage:
  - id: D1
    description: "VIP 代码单元格星标按钮 (WATCH-01) — 在自选实心 amber/不在空心 muted, aria/title=移出/加入自选, pending 禁用, 点击 onToggleWatchlist(row.symbol, inList)"
    requirement: WATCH-01
    verification:
      - kind: other
        ref: "cd frontend && npm run build (tsc -b && vite build)"
        status: pass
      - kind: other
        ref: "grep \"aria-label={inList ? '移出自选' : '加入自选'}\" src/components/pool-hub/StockListTable.tsx"
        status: pass
      - kind: other
        ref: "grep \"fill={inList ? 'currentColor' : 'none'}\" src/components/pool-hub/StockListTable.tsx"
        status: pass
    human_judgment: false
  - id: D2
    description: "「只看自选」过滤开关 (WATCH-02) — switch 双态 + aria + fail-closed 禁用 + storage.poolWatchlistOnly 持久化; filteredRows 概念 AND 只看自选; footer total 权威; 诚实空态优先"
    requirement: WATCH-02
    verification:
      - kind: other
        ref: "grep \"enabled: !!data && mode === 'vip'\" src/pages/PoolHubPage.tsx"
        status: pass
      - kind: other
        ref: "grep \"自选清单中无该策略个股\" src/components/pool-hub/StockListTable.tsx"
        status: pass
      - kind: other
        ref: "grep 'role=\"switch\"' src/pages/PoolHubPage.tsx"
        status: pass
    human_judgment: false
  - id: D3
    description: "自选集合一致性 (WATCH-03) — 复用 QK.watchlist + api.watchlistList + watchlistSet Set 投影; join 键 = row.symbol 全等; toggle 失效 QK.watchlist + QK.watchlistEnriched()"
    requirement: WATCH-03
    verification:
      - kind: other
        ref: "grep \"poolWatchlistOnly: kv<boolean>('pool-watchlist-only')\" src/lib/storage.ts"
        status: pass
      - kind: other
        ref: "cd frontend && npm run build"
        status: pass
    human_judgment: false
  - id: D4
    description: "批量加可见行 (WATCH-04) — handleBatchAdd scope=filteredRows, useWatchlistBatchAdd 复用, watchlistOnly 隐藏, toast 已添加 N 只到自选/批量添加失败"
    requirement: WATCH-04
    verification:
      - kind: other
        ref: "grep 'handleBatchAdd' src/pages/PoolHubPage.tsx"
        status: pass
      - kind: other
        ref: "grep '批量加自选' src/pages/PoolHubPage.tsx"
        status: pass
      - kind: other
        ref: "cd frontend && npm run build"
        status: pass
    human_judgment: false

# Metrics
duration: 10min
completed: 2026-08-06
status: complete
---

# Phase 25 Plan 1: 只看自选 + 星标 + 批量 — 股池钻取面自选体系 Summary

**股池钻取面接入既有服务端自选体系 (WATCH-01..04): VIP 星标 (实心/空心 + aria + fail-closed)、「只看自选」AND 过滤 (total 权威 + 诚实空态)、共享 QK.watchlist 复用 (guest 双门控零查询)、批量加可见行 — 纯前端, 零后端改动/零新增依赖**

## Performance

- **Duration:** 10 min
- **Started:** 2026-08-06T09:55:00Z (approx)
- **Completed:** 2026-08-06T10:02:00Z (approx)
- **Tasks:** 3 / 3
- **Files modified:** 3

## Accomplishments

- **WATCH-01 星标:** VIP 明细行代码旁内嵌星标 — 在自选 `Star` `fill=currentColor` + `text-[#FACC15]` 实心 amber, 不在空心 muted; `aria-label`/`title` = 移出自选/加入自选; `disabled={watchlistPending}` (H9); 点击 `onToggleWatchlist(row.symbol, inList)` → `api.watchlistAdd/Remove` → 失效 `QK.watchlist` + `QK.watchlistEnriched()` (Screener 先例逐字)。guest 分支与表头零变更。
- **WATCH-02 只看自选:** 钻取区 header `role="switch"` 开关 (仅 VIP) — `aria-checked` + `aria-label="只看自选"`, fail-closed 禁用 (error 期 title=`自选清单加载失败`), 状态持久化 `storage.poolWatchlistOnly`; `filteredRows` = 概念子串 AND `watchlistSet.has(r.symbol)`; footer `筛选后 N 只 / 共 M 只` M = `activeStrategy.total` 权威 (H1); 只看自选 0 行 → 独立诚实空态「自选清单中无该策略个股」优先于概念空态 (P4)。
- **WATCH-03 一致性:** 复用共享 `QK.watchlist` + `api.watchlistList`; join 键 = `row.symbol` 全等 (无归一化/无 code 匹配); 无独立 localStorage 自选清单; `api.ts`/`queryKeys.ts`/`useSharedMutations.ts` 零改动。
- **WATCH-04 批量:** 「批量加自选」按钮 (仅 VIP 且 `!watchlistOnly`) scope = `filteredRows.map(r => r.symbol)` (可见行, display_limit 内, 绝不按 total); 复用 `useWatchlistBatchAdd` (双 key 失效已封装); pending 文案 `添加中…`; toast `已添加 ${data.added} 只到自选` / `批量添加失败`。
- **Guest 双门控 (最高危 P2):** watchlist 查询 `enabled: !!data && mode === 'vip'` — data 未落地 (mode 回退 vip 窗口) 或服务端声明 guest 都不发 `/api/watchlist`, 杜绝 guest 首屏 401 → main.tsx 整页跳登录。

## Task Commits

Each task committed atomically:

1. **Task 1: 只看自选过滤垂直切片 (WATCH-02/03)** - `f96766a` (feat) — storage 偏好键 + 双门控查询 + Set 投影 + filteredRows AND + footer/空态
2. **Task 2: VIP 代码单元格星标按钮 (WATCH-01)** - `a18cb37` (feat) — 实心/空心 + aria/title + pending 禁用, guest 分支零变更
3. **Task 3: 钻取区 header 控件 (WATCH-02/04)** - `1e32126` (feat) — 只看自选 switch + 批量加自选 button + fail-closed

**Plan metadata:** pending (final docs commit)

## Files Created/Modified

- `frontend/src/lib/storage.ts` - 新增 `poolWatchlistOnly: kv<boolean>('pool-watchlist-only')` UI 偏好键 (绝不存 symbol 清单)
- `frontend/src/pages/PoolHubPage.tsx` - watchlist 双门控查询 + watchlistSet + toggleWatchlist mutation + watchlistOnly state + filteredRows AND + handleBatchAdd + 钻取区 header 控件 (switch/批量/toast) + 新 props 透传
- `frontend/src/components/pool-hub/StockListTable.tsx` - 新 props 接口 + VIP 星标按钮 + 空态三分流 (只看自选优先) + footer filterActive 扩展

## Decisions Made

- **guest 双门控 `enabled: !!data && mode === 'vip'`** — mode 由 `data?.mode` 派生 (未加载回退 vip), 必须 data 落地 + 服务端声明 vip 双条件才发查询; 否则 guest 首屏误发 `/api/watchlist` → 401 → main.tsx:22-27 全局跳登录 (RESEARCH D4/P2)。
- **`filteredRows` 重构为单一 `base` 变量** — 既有实现有早退路径 (`if (!q) return activeStrategy.rows`); 重构为 `let base = q ? 概念投影 : rows`, 尾部 `if (watchlistOnly) base = base.filter(...)`, 确保开关在最常见场景 (filterText 空) 也生效; 结果新数组引用, 不原地改 `activeStrategy.rows` (REVIEW W2)。
- **批量 scope = `filteredRows` 可见行** — 受 display_limit 截断, `len(rows) ≤ total`; 绝不按未展开的 `activeStrategy.total` 构造超大 body (D6/H8)。
- **watchlistOnly 开启时隐藏批量按钮** — 可见行全在自选, 隐藏最诚实 (D6)。
- **watchlistPending = toggle.isPending || watchlist.isPending || watchlist.isError** — 成员资格未知时不诱导误操作, 不以空集冒充全未自选 (H9 fail-closed)。
- **星标/批量按钮/开关全部带非空可访问名** — 星标 aria/title=移出自选/加入自选, switch aria-label=只看自选, 批量 aria-label/title=批量加自选 (P1: e2e ALLOWED_RE 白名单前提)。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `noUnusedLocals: true` 使中间任务提交无法绿 build (tsc strict)**
- **Found during:** Task 1 (只看自选垂直切片)
- **Issue:** 计划要求每任务提交前 `npm run build` 绿, 但 Task 1 引入的 props (`watchlistSet`/`onToggleWatchlist`/`watchlistPending`) 与 `setWatchlistOnly` 只在 Task 2/3 被消费; `tsc -b` 的 `noUnusedLocals`/`noUnusedParameters` 把未使用解构当错误, 中间提交必红。
- **Fix:** 接口与调用点保留完整契约 (Task 1 即透传全部 4 个新 props), 但把「解构赋值」推迟到消费它的任务: Task 1 只解构 `watchlistOnly` (空态使用), Task 2 解构 `watchlistSet`/`onToggleWatchlist`/`watchlistPending` (星标使用), Task 3 恢复 `setWatchlistOnly` (开关使用)。每个任务提交各自绿 build。
- **Files modified:** PoolHubPage.tsx, StockListTable.tsx
- **Verification:** 三个任务各自 `npm run build` 全绿
- **Committed in:** f96766a / a18cb37 / 1e32126 (各任务提交内)

**2. [Rule 3 - Implementation refinement] 开关移动端触控目标以包裹容器实现 (REVIEW W1 部分)**
- **Found during:** Task 3 (钻取区 header 控件)
- **Issue:** 计划父注释「移动端 max-md:h-11 max-md:w-11 触控目标」若直接加在 switch 按钮上, 会把视觉轨道 (h-4 w-7) 撑成 44×44, knob 位移 (`translate-x-3.5`/`translate-x-0.5`) 按 28px 轨道设计, 移动端视觉破碎。
- **Fix:** 外层包 `inline-flex max-md:h-11 max-md:w-11 max-md:items-center max-md:justify-center` 触控容器, switch 按钮本体保持 `h-4 w-7` 视觉轨道 — 桌面/移动视觉一致, 移动端触控面积 ≥44px (UI-SPEC §3.5)。
- **Files modified:** PoolHubPage.tsx
- **Verification:** `npm run build` 绿; 桌面 DOM 结构与计划一致 (role=switch + aria-checked 在按钮上)
- **Committed in:** 1e32126

---

**Total deviations:** 2 auto-fixed (2 Rule 3)
**Impact on plan:** 均为保持「每任务绿 build」与「移动端触控规范」的实现层调整, 无功能范围变化, 无新增文件, 无后端/依赖变更。

## Issues Encountered

- **计划 `read_first` 行号漂移 (REVIEW W1):** 计划的 `StockListTable.tsx:400-413` (footer) 超文件末尾 (实际 ~L366-370)、`filterActive` 实际 L166、空态实际 L205-229、VIP 代码单元格实际 L296-311 等。执行前用 grep/read 重新核对锚点, 按名定位修订, 未影响实现正确性。
- **harness `grep` 内建 shell builtin 的 `(...)` 正则怪癖:** `grep -n "poolWatchlistOnly: kv<boolean>('pool-watchlist-only')"` 在本环境 bash builtin 下不命中, 但文件行字节级正确 (`_grep` 工具与 `grep -F` 均命中)。计划 verify 门以标准 GNU grep 语义为准, 无代码影响。

## Known Stubs

无 — 全部控件/数据源已接实 (watchlistSet/toggleWatchlist/batchAdd/开关均 wired 到真实 `api.watchlist*` 与 `QK.watchlist`)。

## Threat Surface

零新增威胁面: 未新增网络端点/文件访问/权限路径; 修改的 3 个文件全部在计划 `<threat_model>` 范围内 (T-25-01-01..05 均有对应 mitigation)。无 Threat Flags。

## Next Phase Readiness

- **25-02 (e2e + docs):** 本计划合入的源码符号 (星标 `aria-label`=移出/加入自选、switch `role="switch"`+`aria-label="只看自选"`、批量按钮 `aria-label="批量加自选"`) 全部就位, 25-02 的 `<precondition>` grep 门 (`mode === 'vip'` / `移出自选`) 已命中; e2e 可断言 guest 零 `/api/watchlist` 请求 + 零控件、VIP 星标/开关/批量行为、`POST /api/watchlist/batch` body = 可见行。
- **POOL-03 守卫:** 源码 grep 守卫复核通过 (无 `<form` / 执行族 API 标识符 / 裸 fetch 写 / 掩码字面量与 `mask` 标识符); 新增控件可访问名均入 ALLOWED_RE 白名单 (25-02 更新)。
- **后端:** 零改动, 无回归风险。

---
*Phase: 25-watchlist-sync*
*Completed: 2026-08-06*
