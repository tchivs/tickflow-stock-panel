# Phase 25: 自选股联动 (Watchlist Sync) - Pattern Map

**Mapped:** 2026-08-06
**Files analyzed:** 6（2 修改 / 1 新组件 / 1 修改工具库 / 2 e2e）
**Analogs found:** 10 / 10（exact 9 / role-match 1；另有 3 处「复用既有、零新增」见 Reuse）

> 本文件把 Phase 25（WATCH-01..04）的每个新建/修改文件映射到仓库内最接近的既有实现，并给出可直接复制/镜像的具体代码段（带文件路径与行号，全部在本 session 逐行读取确认）。
>
> **一句话总结:** WATCH-01..04 是纯前端——把策略页 `Screener.tsx:429-447` 的「`useQuery(QK.watchlist)` → `Set` → 行内星标 → `api.watchlistAdd/Remove` mutation → `invalidateQueries(QK.watchlist)`」整条链路搬进股池钻取面，复用既有 `QK.watchlist` 共享缓存实现跨页一致（WATCH-03），再加一个「只看自选」过滤开关（ConceptFilter 形态）与一个批量加自选按钮（Screener `handleBatchAdd` 形态）。**零后端改动、零新 npm 依赖、零 vitest（前端验证 = `npm run build` + Playwright e2e）。**
>
> **给 planner 的第一优先级决策点:** 既有 e2e 守卫 `pool page never issues a mutating request (POOL-03)`（`frontend/e2e/pool-hub.spec.ts:620-643`）断言股池页 `nonGet toEqual([])`——WATCH-01 的星标 toggle 会发 `POST /api/watchlist` / `DELETE /api/watchlist/{symbol}`，**该测试必然红**。必须同步更新此守卫（VIP 允许 watchlist CRUD，guest 仍零 non-GET），并同步更新同文件 `pool page renders zero execution affordances (POOL-03)`（:591-617）的白名单 `ALLOWED_RE`（星标/只看自选/批量加按钮须入白名单，且 icon-only 按钮须带 `aria-label`，否则 `textContent` 为空过不了 `toMatch(ALLOWED_RE)`）。

## 关键约束与危险区（先读）

| 边界 | 位置 | 本阶段影响 |
|---|---|---|
| **前端 401 → 跳登录** | `frontend/src/main.tsx:22-27`（QueryCache/MutationCache `onError` 收 401 → `window.location.href = '/login?...'`） | 股池页 guest 会话**绝不发起** `QK.watchlist` 查询/`api.watchlistAdd/Remove`（guest 访问 `/api/watchlist` 一律 401，`backend/app/main.py:778-788` 游客白名单不含它）。watchlist query 必须 `enabled` 门控于 `mode === 'vip'` |
| **e2e POOL-03 no-mutating-request 守卫** | `frontend/e2e/pool-hub.spec.ts:620-643` | 断言 `nonGet toEqual([])`。WATCH-01/04 会发 watchlist 写请求 → **必须更新**：VIP 放行 `/api/watchlist*`，guest 仍零写 |
| **e2e POOL-03 affordances 白名单** | `frontend/e2e/pool-hub.spec.ts:591-617` | `ALLOWED_RE` 白名单扫描 main 内全部 button，icon-only 按钮取 `aria-label ?? textContent`——星标/批量按钮须加 `aria-label` 且入白名单，否则红 |
| **e2e POOL-03 源码 grep 守卫** | `frontend/e2e/pool-hub.spec.ts:645-660` | 对 `PoolHubPage.tsx`/`StrategyCardGrid.tsx`/`ConceptFilter.tsx`/`StockListTable.tsx` grep：`<form`、`api.\w*(order\|trade\|execute\|broker\|transaction\|deals)`、`fetch(...method: POST|PUT|DELETE|PATCH)`。经 `api.watchlist*` 封装调用天然通过（页面文件无裸 fetch），但**若在 PoolHubPage/StockListTable 内直接写 fetch 即红**——必须走 `api` 模块 |
| **guest 像素级不变（WATCH-01/GUEST-01）** | `StockListTable.tsx:20-21` `GUEST_COLUMNS`/`VIP_COLUMNS`；`:183-207` 代码单元格 | guest 不渲染星标列/只看自选开关/批量按钮；`GUEST_COLUMNS` 五列原样。星标只在 VIP 代码单元格内追加 |
| **Watchlist.tsx 用户未提交改动** | `frontend/src/pages/Watchlist.tsx`（1346 行，未提交） | **绝不修改/提交/read 内容**；本 session 仅 grep 导出名与查询键契约确认：`QK.watchlist` + `api.watchlistList`（:631-634）、`addMutation`/`remove` 均 `setQueryData` + `invalidateQueries(QK.watchlist)`（:674-697）——契约与 Screener 一致，股池页消费同一 key 即自动一致 |
| **POOL-03 后端 AST 守卫（零后端改动的根因）** | `backend/tests/test_pool_hub.py:788-833`（token 含 `watchlist`） | 后端 `pool_hub.py`/`pool.py`/`pool_snapshot.py` 禁 import watchlist 执行族。**本期零后端改动**——纯前端 join 天然避开 |
| **游客面守卫（后端）** | `backend/tests/test_guest_masking.py` T-19-03；`main.py:778-788` | `/api/watchlist` 不在 guest 只读白名单 → guest 面不能有任何自选查询/写。前端按 `mode` 门控即满足 |

## File Classification（目标文件 → analogs）

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality | 关键差异 |
|---|---|---|---|---|---|
| `frontend/src/pages/PoolHubPage.tsx` (modified) | page/controller | request-response + CRUD | `pages/Screener.tsx:429-447`（watchlist query → Set → toggle mutation）+ 本文件既有 `mode`/`filteredRows` 结构 | exact | watchlist query **`enabled` 门控 `mode==='vip'`**（Screener 无条件，因策略页非 guest 面）；「只看自选」过滤与既有 `filteredRows` AND 组合；批量加按钮 |
| `frontend/src/components/pool-hub/StockListTable.tsx` (modified) | component | render (CRUD 触发回调) | `components/screener/ScreenerTable.tsx:166-210`（symbol 列星标按钮）+ `components/StockInfoBar.tsx:215-227`（金色 Star 图标）+ 本文件既有 `isGuest` 分支 | exact | 星标仅 VIP 代码单元格；传 `watchlistSet`/`onToggleWatchlist`/`watchlistPending` props（ScreenerTable 同款受控）；guest 渲染逐像素不变 |
| `frontend/src/components/pool-hub/WatchlistFilter.tsx` (new, 可选) | component | controlled filter | `components/pool-hub/ConceptFilter.tsx`（受控行：label + 控件 + 清除按钮 + sr-only 帮助） | exact | 换为「只看自选」开关（Switch/checkbox 形态），零 fetch，纯客户端投影 |
| `frontend/src/lib/storage.ts` (modified) | utility | key-value 持久化 | 本文件 `kv<T>()` 实现（:8-20）+ 既有偏好键条目（如 `limitLadderDirection`） | exact (in-file) | 新增 `poolWatchlistOnly: kv<boolean>('pool-watchlist-only')`（WATCH-02 开关持久化，**不落后端**） |
| `frontend/e2e/pool-hub.spec.ts` (modified) | test | e2e mock + assert | 本文件 `installShell`（:256-295）+ `page.on('request')` 捕获（:620-643）+ SC1-SC4 场景形（:855-1081） | exact (in-file) | 更新 3 个 POOL-03 守卫；`installShell` 增 `/api/watchlist*` 路由；新增 WATCH-01/02 VIP 场景 + guest 零写回归 |
| `frontend/e2e/watchlist-sync.spec.ts` (new, 可选) | test | e2e mock + assert | `pool-hub.spec.ts` 结构（`installShell` + fixtures + `json()` helper + desktop-only skip） | role-match | 聚焦跨页一致（WATCH-03）：自选页/策略页/股池页共享 `QK.watchlist` 缓存互失效；批量加（WATCH-04） |

## Pattern Assignments

### 1. `frontend/src/pages/PoolHubPage.tsx` (modified, page / request-response + CRUD)

**Analogs:** `pages/Screener.tsx:429-447`（自选 query + Set + toggle mutation 完整链路）+ 本文件既有 `mode` 派生（:39-43）与 `filteredRows`（:57-63）。

**Imports 追加（复制 Screener.tsx:5-10 的 react-query 组合 + useSharedMutations）:**
```tsx
// 既有: import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useWatchlistBatchAdd } from '@/lib/useSharedMutations'   // useSharedMutations.ts:33
```

**自选 query + Set（复制 Screener.tsx:429-437，唯一差异 = VIP 门控 `enabled`）:**
```tsx
// Screener.tsx:429-437 原样（Screener 无条件）:
const watchlist = useQuery({ queryKey: QK.watchlist, queryFn: api.watchlistList })
const watchlistSet = useMemo(() => {
  const symbols = watchlist.data?.symbols ?? []
  return new Set(symbols.map((s: any) => s.symbol))
}, [watchlist.data])

// 股池版必须加 enabled 门控 (WATCH-01 验收: guest 不发查询, 防 401 跳登录):
// mode 由 data?.mode 派生 (PoolHubPage.tsx:39-43, 缺省回退 vip) — 用 !!data && mode==='vip'
// 防未加载期 data=undefined 时误发 (mode 缺省回退 vip 会绕过 guest 意图)。
const watchlist = useQuery({
  queryKey: QK.watchlist,
  queryFn: api.watchlistList,
  enabled: !!data && mode === 'vip',
})
```

**单只 toggle mutation（逐字复制 Screener.tsx:440-447）:**
```tsx
const toggleWatchlist = useMutation({
  mutationFn: ({ symbol, inList }: { symbol: string; inList: boolean }) =>
    inList ? api.watchlistRemove(symbol) : api.watchlistAdd(symbol),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: QK.watchlist })
    qc.invalidateQueries({ queryKey: QK.watchlistEnriched() })
  },
})
```

**「只看自选」过滤与既有概念筛选 AND 组合（扩展 PoolHubPage.tsx:57-63 的 `filteredRows`）:**
```tsx
// 既有 (概念子串投影, D-04): PoolHubPage.tsx:57-63
const filteredRows = useMemo(() => {
  if (!activeStrategy) return []
  const q = filterText.trim().toLowerCase()
  if (!q) return activeStrategy.rows
  return activeStrategy.rows.filter(r =>
    r.concept_board.some(c => c.toLowerCase().includes(q)),
  )
}, [activeStrategy, filterText])

// WATCH-02: 开关状态存 storage (poolWatchlistOnly), 与概念筛选 AND 组合:
// const [watchlistOnly, setWatchlistOnly] = useState(() => storage.poolWatchlistOnly.get(false))
// filteredRows 尾部追加: if (watchlistOnly) return base.filter(r => watchlistSet.has(r.symbol))
```

**批量加可见行（复制 Screener.tsx:494-512 的 `handleBatchAdd` + useSharedMutations）:**
```tsx
// useWatchlistBatchAdd 已封装 mutation + 双 key 失效 (useSharedMutations.ts:33-41)
const batchAdd = useWatchlistBatchAdd()
const handleBatchAdd = () => {
  const symbols = filteredRows.map(r => r.symbol)   // WATCH-04: 可见行 (display_limit 内), 绝不按 total
  if (!symbols.length) return
  batchAdd.mutate(symbols, {
    onSuccess: (data) => { /* toast/setBatchMsg(`已添加 ${data.added} 只到自选`) */ },
    onError: () => { /* toast 添加失败 */ },
  })
}
```

**透传给 StockListTable（新增 props 同 ScreenerTable.tsx:24-28 受控接口）:**
```tsx
<StockListTable
  …
  mode={mode}
  watchlistSet={watchlistSet}
  onToggleWatchlist={(symbol, inList) => toggleWatchlist.mutate({ symbol, inList })}
  watchlistPending={toggleWatchlist.isPending}
  batchAddPending={batchAdd.isPending}
  onBatchAdd={handleBatchAdd}
  watchlistOnly={watchlistOnly}
  onToggleWatchlistOnly={() => setWatchlistOnly(v => !v)}
/>
```

**Deltas:**
- `qc` = `useQueryClient()`（Screener.tsx 顶部同款，PoolHubPage 需新增 import）。
- 星标/开关/批量按钮**只在 `mode === 'vip'`** 渲染（PoolHubPage.tsx:39-43 已有 mode 派生；`:118-119` GuestModeBanner 只在 guest 渲染，对照）。
- 空态：WATCH-02 开关开且命中 0 行 → 诚实空态「自选清单中无该策略个股」，复用 `StockListTable.tsx:130-150` 空态 div 结构（filterActive 分支的镜像）。

---

### 2. `frontend/src/components/pool-hub/StockListTable.tsx` (modified, component / render)

**Analogs:** `components/screener/ScreenerTable.tsx:166-210`（symbol 列星标按钮，逐字模板）+ `components/StockInfoBar.tsx:215-227`（金色 Star 图标样式）+ 本文件既有 `isGuest`/`columns` 分支。

**Props 扩展（镜像 ScreenerTable.tsx:24-28 受控接口）:**
```tsx
// 追加到 StockListTableProps (StockListTable.tsx:23-48):
watchlistSet: Set<string>
onToggleWatchlist: (symbol: string, inList: boolean) => void
watchlistPending: boolean
```

**VIP 代码单元格内星标（复制 ScreenerTable.tsx:166-210，图标换成 Star 金色）:**
```tsx
// ScreenerTable.tsx:167-210 原样:
const inWatchlist = watchlistSet.has(r.symbol)
…
<button
  type="button"
  onClick={() => onToggleWatchlist(r.symbol, inWatchlist)}
  disabled={watchlistPending}
  className={`shrink-0 inline-flex items-center justify-center w-5 h-5 rounded-full border transition-colors cursor-pointer
    disabled:opacity-50
    ${inWatchlist
      ? 'border-accent/40 bg-accent/10 text-accent'
      : 'border-border text-muted hover:border-accent/40 hover:text-accent'
    }`}
  title={inWatchlist ? '移出自选' : '加入自选'}
>
  {inWatchlist ? <Check className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
</button>
```

**星标视觉（WATCH-01「实心高亮/空心」— 取 StockInfoBar.tsx:215-227 金色 Star 语义，lucide `Star` 加 `fill` 实现实心）:**
```tsx
// StockInfoBar.tsx:224-227 既有金色 Star (在自选中金色, 不在 muted):
<Star className={inWatchlist ? 'text-[#FACC15]' : 'text-muted'} />
// 实心 vs 空心: lucide Star 默认空心; 实心加 fill="currentColor" (无既有先例, 属本 phase 最小新意,
// 或沿用 Screener 的 Check/Plus 圆形按钮 — 二选一, planner 定, 但 guest 面两者都不渲染)
```

**插入位置（关键 — 只在 VIP 代码单元格，guest 逐像素不变）:**
```tsx
// StockListTable.tsx:194-220 既有 VIP 代码 td 的 `<div className="flex items-center gap-2">` 内追加:
<td className={cn('px-4 py-2 whitespace-nowrap', cross && 'border-l-2 border-accent/60')}>
  {isGuest ? (
    <span className="num tabular-nums text-muted">{row.code}</span>   // guest: 原样, 无星标
  ) : (
    <div className="flex items-center gap-2">
      {board ? <span className={…boardTag…}>{board.label}</span> : <span className="shrink-0 w-[18px]" />}
      <span className="num tabular-nums text-secondary">{row.code}</span>
      {/* ← 星标按钮插这里 (仅 VIP) */}
    </div>
  )}
</td>
```

**「只看自选」开关 UI（可选放本文件表上方，镜像 ConceptFilter.tsx 受控行 + 既有空态）:**
```tsx
// ConceptFilter.tsx:16-32 受控行骨架 (label + 控件 + 帮助文本), 换成 checkbox/switch:
<label className="inline-flex items-center gap-2 text-xs font-medium text-secondary">
  <input type="checkbox" checked={watchlistOnly} onChange={e => onToggleWatchlistOnly(e.target.checked)} />
  只看自选
</label>
```

**空态（WATCH-02 诚实空态，镜像 StockListTable.tsx:130-150 filterActive 空态 div）:**
```tsx
{!loading && !error && watchlistOnly && filterActive === false && rows.length === 0 && (
  <div className="flex flex-col items-center gap-1 py-10 text-center">
    <p className="text-sm font-medium text-foreground">自选清单中无该策略个股</p>
    <p className="text-xs text-secondary">试试关闭「只看自选」或切换策略。</p>
  </div>
)}
```

**Deltas:**
- **guest 渲染零变更**：`GUEST_COLUMNS`（StockListTable.tsx:20）不动；星标/开关全部 `!isGuest` 分支内。
- 表头**不加**新列（星标内嵌代码单元格，列数不变）→ 既有分组表头逻辑（:98-148）与 footer（:360-383）零改动，`minWidth` 不变。
- 与后端无关：星标状态来自 props（`watchlistSet`），本文件**不发任何请求**——fetch/写操作全在 `api.ts` 封装层（过 e2e 源码 grep 守卫 :645-660 的前提）。

---

### 3. `frontend/src/components/pool-hub/WatchlistFilter.tsx` (new, 可选 / component, controlled)

**Analog:** `components/pool-hub/ConceptFilter.tsx`（受控筛选行 + 清除按钮 + sr-only 帮助文本）——本文件是「控件筛选」的既有形态，WATCH-02 开关照此骨架。

**骨架（复制 ConceptFilter.tsx:12-31 受控行，值从 text 换 boolean）:**
```tsx
interface WatchlistFilterProps {
  value: boolean
  onChange: (v: boolean) => void
}
export function WatchlistFilter({ value, onChange }: WatchlistFilterProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="inline-flex items-center gap-2 text-xs font-medium text-secondary whitespace-nowrap">
        <input
          type="checkbox"
          checked={value}
          onChange={e => onChange(e.target.checked)}
          className="accent-accent"
        />
        只看自选
      </label>
    </div>
  )
}
```

**Deltas:** 零 fetch、零状态提升（状态在 PoolHubPage，经 `storage.poolWatchlistOnly` 持久化）；guest 不渲染（由 PoolHubPage 门控）。

---

### 4. `frontend/src/lib/storage.ts` (modified, utility / key-value)

**Analog:** 本文件 `kv<T>()`（:8-20）+ 既有偏好键条目（Boolean 型先例 `watchlistCandle` :53-56）。

**新增键（WATCH-02 验收: 开关状态存 storage，与既有 UI 偏好同型）:**
```ts
// 复制 watchlistCandle 条目形 (storage.ts:53-56):
/** 股池「只看自选」过滤开关 (WATCH-02) — UI 偏好, 不落后端 */
poolWatchlistOnly: kv<boolean>('pool-watchlist-only'),
```

**Deltas:** key 命名沿用既有风格（kebab-case 为主，如 `limit-ladder-board-filter`）；**绝不**用它存自选 symbol 列表（自选清单唯一事实来源 = 服务端 `watchlist.parquet` + 共享 `QK.watchlist` 缓存，见 Avoid）。

---

### 5. `frontend/e2e/pool-hub.spec.ts` (modified, e2e)

**Analogs:** 本文件 `installShell`（:256-295）+ `page.on('request')` 捕获守卫（:620-643）+ SC1-SC4 场景形（:855-1081）+ `json()`/`unhandled()` helpers（:240-253）。

**installShell 增 watchlist 路由（后注册优先, 覆盖 `**/api/**` unhandled）:**
```ts
// installShell (pool-hub.spec.ts:256-295) 末尾追加 — WATCH-01/03:
await page.route('**/api/watchlist', route => json(route, {
  symbols: [{ symbol: '603221.SH', added_at: '2026-08-01T00:00:00', note: '' }],
}))
await page.route('**/api/watchlist/batch', route =>
  route.request().method() === 'POST'
    ? json(route, { symbols: [], added: 1 })
    : unhandled(route))
await page.route('**/api/watchlist/*', route =>
  route.request().method() === 'DELETE'
    ? json(route, { symbols: [] })
    : unhandled(route))
```

**3 个 POOL-03 守卫的必须更新（本 phase 最危险的契约变更）:**
```ts
// 1) :620-643 no-mutating-request — nonGet toEqual([]) 将因 POST/DELETE /api/watchlist 红。
//    改为: guest 会话 (hubPayloadGuest) 仍 zero non-GET; VIP 会话允许 /api/watchlist* 写, 其余仍零写:
const nonGet = captured.filter(c => !/^GET /.test(c))
const watchlistWrites = nonGet.filter(c => /^POST \/api\/watchlist|^DELETE \/api\/watchlist/.test(c))
const otherWrites = nonGet.filter(c => !/^POST \/api\/watchlist|^DELETE \/api\/watchlist/.test(c))
expect(otherWrites, `non-watchlist non-GET requests: ${otherWrites.join(', ')}`).toEqual([])

// 2) :591-617 affordances 白名单 — ALLOWED_RE 增:
//    /加入自选|移出自选|只看自选|批量加自选/
//    (icon-only 星标按钮须设 aria-label=「加入自选/移出自选」, 因按钮取 aria-label ?? textContent)

// 3) :645-660 源码 grep — 文件列表保持; 因走 api.watchlist* 封装无裸 fetch, 天然通过;
//    若新增 WatchlistFilter.tsx, 可并入 checked files 保持覆盖面
```

**新增 WATCH e2e 场景（镜像 SC1-SC4 形: `test.skip` desktop-only + installShell + route 覆盖 + 断言）:**
- WATCH-01: VIP 载荷 → 星标渲染（`getByTitle('加入自选')`）→ 点击 → 捕获 `POST /api/watchlist` → 断言 mutation 后星标态翻转。
- WATCH-01b: guest 载荷（`hubPayloadGuest`）→ 断言无 `加入自选`/`移出自选` 按钮、无 `/api/watchlist` 请求（请求捕获数组不含 watchlist）。
- WATCH-02: VIP + `/api/watchlist` 命中部分行 → 勾「只看自选」→ 仅自选行可见 + footer 计数诚实；0 命中 → 空态文案。
- WATCH-03: 先在股池页 toggle → 断言 `invalidateQueries` 后的 `QK.watchlist` 使自选页/策略页同步（可只断言「同一 key 已失效」行为：股池页 toggle 后二次 fetch `/api/watchlist` 出现）。
- WATCH-04: 批量按钮仅 VIP；点击 → 捕获 `POST /api/watchlist/batch` 且 body.symbols == 可见行集合。

---

### 6. `frontend/e2e/watchlist-sync.spec.ts` (new, 可选 / e2e)

**Analog:** `pool-hub.spec.ts` 结构（role-match）：`installShell` 脚手架 + `json()`/`unhandled()` helpers + `DESKTOP_PROJECT` skip + `page.on('request')` 捕获。

**Deltas:** 聚焦 WATCH-03 跨页一致与 WATCH-04 批量边界；若与 pool-hub.spec.ts 合并（推荐，避免双 installShell 维护），则此文件不建。Playwright 配置 `frontend/playwright.config.ts` 无需改动（testDir='.' 已含 e2e/）。

## Shared Patterns

### 自选 query → Set → toggle 链路（WATCH-01/03 核心，全仓一致先例）
**Source:** `pages/Screener.tsx:429-447`；个股弹窗同款 `components/StockPreviewDialog.tsx:47-60`
**Apply to:** PoolHubPage.tsx
```tsx
const watchlist = useQuery({ queryKey: QK.watchlist, queryFn: api.watchlistList })
const watchlistSet = useMemo(() => new Set((watchlist.data?.symbols ?? []).map((s: any) => s.symbol)), [watchlist.data])
const toggleWatchlist = useMutation({
  mutationFn: ({ symbol, inList }) => inList ? api.watchlistRemove(symbol) : api.watchlistAdd(symbol),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: QK.watchlist })
    qc.invalidateQueries({ queryKey: QK.watchlistEnriched() })
  },
})
```

### QK 失效契约（WATCH-03 跨页一致的唯一机制）
**Source:** `lib/queryKeys.ts:25-28`（`watchlist: ['watchlist']` / `watchlistEnriched`）；`lib/useSharedMutations.ts:33-41`
**Apply to:** 所有增删入口（自选页/策略页/个股弹窗/股池页）
- 增删后 `invalidateQueries(QK.watchlist)` + `invalidateQueries(QK.watchlistEnriched())`（+`['watchlist-kline-batch']` 仅自选页需要，Watchlist.tsx:679-680）。
- `SSE_INVALIDATE_PREFIXES` 已含 `'watchlist'`（queryKeys.ts:215-226）→ 实时行情刷新自动失效，无需新增。
- **不新建独立自选 key**（WATCH-03 验收：股池页复用 `QK.watchlist`）。

### 批量加自选（WATCH-04）
**Source:** `lib/useSharedMutations.ts:32-41` `useWatchlistBatchAdd`；Screener 调用形 `pages/Screener.tsx:494-512, 737-746`
**Apply to:** PoolHubPage.tsx
```tsx
const batchAdd = useWatchlistBatchAdd()          // 已含 QK.watchlist + watchlistEnriched 双失效
batchAdd.mutate(symbols, { onSuccess: (data) => setBatchMsg(`已添加 ${data.added} 只到自选`) })
```

### 星标按钮视觉
**Source:** `components/screener/ScreenerTable.tsx:166-210`（Check/Plus 圆形按钮 + pending disabled）；`components/StockInfoBar.tsx:215-227`（金色 Star）
**Apply to:** StockListTable.tsx（仅 VIP 代码单元格）

### guest 门控
**Source:** `pages/PoolHubPage.tsx:39-43`（`mode = data?.mode === 'guest' ? 'guest' : 'vip'`）；`components/pool-hub/GuestModeBanner.tsx`（文案锁定）
**Apply to:** 所有 WATCH UI + watchlist query
- 渲染门控：`mode === 'vip'`；query 门控：`enabled: !!data && mode === 'vip'`（防 401 跳登录，main.tsx:22-27）。

### storage 偏好键
**Source:** `lib/storage.ts:8-20` `kv<T>()`
**Apply to:** `poolWatchlistOnly` 布尔开关

## 复用什么 / 避开什么

| 复用（Reuse） | 位置 | 用途 |
|---|---|---|
| `api.watchlistList / Add / Remove / BatchAdd` | `lib/api.ts:2025-2054` | WATCH-01/04 全部 CRUD，**api.ts 零改动** |
| `QK.watchlist` + `QK.watchlistEnriched()` | `lib/queryKeys.ts:25-26` | 共享缓存跨页一致（WATCH-03），**queryKeys.ts 零改动** |
| `useWatchlistBatchAdd` | `lib/useSharedMutations.ts:32-41` | WATCH-04 批量加（Screener/Intraday 已共用） |
| toggle mutation + invalidate 双 key | `Screener.tsx:440-447` / `StockPreviewDialog.tsx:47-60` | WATCH-01 逐字模板 |
| 星标按钮 | `ScreenerTable.tsx:166-210` / `StockInfoBar.tsx:215-227` | WATCH-01 行内星标 |
| 受控筛选行 | `ConceptFilter.tsx` | WATCH-02 开关骨架 |
| storage kv | `storage.ts:8-20` | WATCH-02 开关持久化 |
| e2e 脚手架 | `pool-hub.spec.ts:240-295` | WATCH e2e（installShell + fixtures + helpers） |
| 匹配键 = 全后缀 symbol | `PoolHubRow.symbol`（api.ts:696-698）与 `WatchlistEntry.symbol`（api.ts:602-605）实测同格式 | `watchlistSet.has(row.symbol)` 精确 join（WATCH-03） |

| 避开（Avoid） | 位置 | 原因 |
|---|---|---|
| 后端任何改动（投影 `is_watched`/annotate 端点/import watchlist） | `backend/` + `test_pool_hub.py:788-833` | POOL-03 AST 守卫 token 含 `watchlist` + guest 掩码 + pool.py GET-only——触碰即红，纯前端 join 天然避开 |
| localStorage 存自选清单 / 独立自选 query key | `lib/storage.ts` / `lib/queryKeys.ts` | 与服务端 `watchlist.parquet` 分裂双源；四处服务端消费（tickflow/pools、daily_pipeline、extend_history、quote_service）全部脱节；违反 WATCH-03 单一事实来源 |
| guest 面发 watchlist 查询/写 | `PoolHubPage.tsx` | 401 → 全局跳登录（main.tsx:22-27），破坏 guest 现状；e2e `no-mutating` 守卫兜底 |
| 批量按未展开 `total` | `pool_hub.py` docstring Divergence 1 | WATCH-04 边界：只批量 `activeStrategy.rows` 可见行（display_limit 内），幂等由后端 `watchlist.add` 去重（backend watchlist.py:37-52） |
| 模糊 symbol 匹配（`600664` ↔ `600664.SH`） | 全前端 | 所有入口已全后缀（instrumentSearch/策略行/股池行）；失配修入口而非加模糊匹配 |
| 触碰 `Watchlist.tsx` | `frontend/src/pages/Watchlist.tsx` | 用户有未提交改动；本 phase 只消费公共 API + `QK.watchlist` 契约 |
| 新增 npm 依赖 / vitest | `frontend/package.json` | 约束：零新依赖；前端验证 = `npm run build` + Playwright e2e |

## 命名与约定

- **组件文件**：`frontend/src/components/pool-hub/` 目录内，Kebab/Pascal 与既有一致（`ConceptFilter.tsx`、`DateNavigator.tsx`）。
- **存储键**：`poolWatchlistOnly`（camelCase 属性名 + kebab-case localStorage key `'pool-watchlist-only'`，沿 `storage.ts` 既有风格）。
- **受控 props**：`watchlistSet: Set<string>` / `onToggleWatchlist(symbol, inList)` / `watchlistPending: boolean`——与 `ScreenerTableProps`（ScreenerTable.tsx:24-28）逐字段同名，跨组件心智一致。
- **e2e 场景命名**：沿用 `SC{N}` 序列（现有 SC1-SC4），WATCH 场景用 `WATCH-01..04` 前缀（如 `'WATCH-01: vip row star toggles membership via /api/watchlist'`）。
- **空态文案**：诚实、非静默——「自选清单中无该策略个股」；不引用锁定横幅文案（GuestModeBanner 的 `BANNER_TITLE/BODY`/`GUEST_BANNER_ACCESSIBLE_TEXT` 本期不动）。
- **aria**：icon-only 星标/批量按钮必须 `aria-label`（e2e affordances 白名单取 `aria-label ?? textContent`）；开关用 checkbox 原生 label 绑定。

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| 无 | — | — | 全部目标文件均命中 exact/role-match analog；`api.ts`/`queryKeys.ts`/`useSharedMutations.ts` 为纯复用零改动。星标「实心」视觉（lucide `Star` + `fill="currentColor"`）无既有先例，属本 phase 最小新意，或改用 Screener 既有 Check/Plus 圆形按钮（二选一，planner 定） |

## Metadata

**Analog search scope:** `frontend/src/lib`、`frontend/src/pages`、`frontend/src/components`（含 `pool-hub/`、`screener/`、`stock-table/`）、`frontend/e2e`、`.planning/research/v2.1-depth/WATCHLIST.md`；后端仅核对守卫/游客边界（`test_pool_hub.py`、`test_guest_masking.py`、`main.py`）确认「零后端改动」成立。
**Files scanned:** 16（api.ts、queryKeys.ts、useSharedMutations.ts、useSharedQueries.ts、storage.ts、main.tsx、router.tsx、Screener.tsx、ScreenerTable.tsx、StockInfoBar.tsx、StockPanel.tsx、StockPreviewDialog.tsx、PoolHubPage.tsx、StockListTable.tsx、DateNavigator.tsx、ConceptFilter.tsx、GuestModeBanner.tsx、primitives.tsx、pool-hub.spec.ts、playwright.config.ts、package.json）
**Analogs extracted:** 10（exact 9 / role-match 1）
**Pattern extraction date:** 2026-08-06

> 所有 excerpt 行号均在本 session 逐行读取确认；Watchlist.tsx 仅 grep 导出名/查询键契约（用户未提交改动，未 read 内容）。Structured result 见 Pattern Mapper 返回。
