---
phase: 25
slug: watchlist-sync
type: ui-spec
status: draft
shadcn_initialized: false
preset: none
created: 2026-08-06
---

# Phase 25 UI-SPEC:自选股联动（WATCH-01..04，纯前端）

> 在股池钻取面（`PoolHubPage` → `StockListTable`）接入既有服务端自选体系：VIP 模式每行渲染
> **自选星标**（WATCH-01）、钻取区 header 提供**「只看自选」过滤开关**（WATCH-02）、复用共享
> **`QK.watchlist` 缓存**保证跨页一致（WATCH-03）、并支持**批量加可见行**（WATCH-04，P2）。
> **零后端改动、零新增 npm 依赖、零 vitest**（验证 = `npm run build` + Playwright e2e）。
>
> 后端 source of truth：`25-RESEARCH.md`（D1–D6、P1–P5）；组件先例：`25-PATTERNS.md`（10/10 analogs）。

---

## 1. 目标与用户故事

### WATCH-01 — 股池钻取行自选星标 + 切换（VIP）

**用户故事：** 作为已登录研究员，我在股池钻取明细表的每行代码旁看到自选星标——在自选中为
实心高亮（amber），不在为空心；点击即经既有 `/api/watchlist` CRUD 加入/移出自选，切换后跨页
（自选页/策略页/个股弹窗/股池页）即时一致。游客会话渲染的股池表与 v2.0 **逐像素一致**：无星标、
无任何自选控件、不发任何 `/api/watchlist` 请求（避免 401 全局跳登录，`main.tsx:22-27`）。

### WATCH-02 — 「只看自选」过滤开关（VIP）

**用户故事：** 作为已登录研究员，我在钻取区 header 打开「只看自选」开关，明细表立即收窄为当前
策略在自选清单中的行；与既有概念筛选 **AND** 组合；策略卡 `total` 权威不变（筛选永不改计数）；
开关对最新 `/api/pool/hub` 与历史 `/api/pool/history` 视图同样生效；自选清单中无该策略个股时
显示**诚实空态**（非静默空白、非「无符合『』」误报）。

### WATCH-03 — 自选集合一致性与匹配键契约

**用户故事：** 股池页的自选集合与自选页/策略页/个股弹窗共享同一 `QK.watchlist` 全局缓存；
任何入口增删都失效同一 key → 股池星标/过滤即时一致，无需新同步机制。匹配键 = 全后缀 `symbol`
（`603221.SH`）**精确全等**，不做大小写/后缀猜测。

### WATCH-04 — 批量加自选（P2，边界）

**用户故事：** 作为已登录研究员，我在钻取区 header 点击「批量加自选」，当前策略的**可见行**
（`filteredRows`，受 `display_limit` 截断，`len(rows) ≤ total`）一次性加入自选；重复加入幂等
（后端 `watchlist.add` 去重）；成功 toast 反馈已添加数量。

### Phase boundary

- **In scope：** `PoolHubPage.tsx`（watchlist query + Set + toggle mutation + 只看自选 state +
  批量 handler + 钻取区 header 控件）、`StockListTable.tsx`（VIP 代码单元格星标 + 空态分流 +
  footer `filterActive` 扩展）、`storage.ts`（`poolWatchlistOnly` UI 偏好键）、可选
  `components/pool-hub/WatchlistFilter.tsx`、`e2e/pool-hub.spec.ts`（installShell mock +
  POOL-03 守卫更新 + WATCH 新用例 + VIP 快照重生成）。
- **Out of scope：** 后端任何改动（投影 `is_watched`/annotate 端点/import watchlist）——POOL-03
  AST 守卫 `_EXECUTION_TOKEN` 含 `watchlist`（`test_pool_hub.py:857-861`）锁死；guest 掩码改动
  （`guest_masking.py` 自身被 `_GUEST_BANNED_IMPORT` 禁 watchlist）；localStorage 第二自选清单；
  独立自选 query key；历史自选快照（自选非时间序列）；`frontend/src/pages/Watchlist.tsx`（用户
  未提交改动，**绝不修改/提交/read 内容**，仅消费公共 API + `QK.watchlist` 契约）。

---

## 2. 设计原则（诚实 / vip-guest 边界 / 一致性）

本契约的 UI 决策全部由以下诚实规则驱动（对应 `25-RESEARCH.md` D1–D6 / P1–P5）：

| # | 规则 | 落地条款 |
|---|---|---|
| H1 | **`total` 权威不可破。** 过滤（概念 AND 只看自选）只投影行，永不改 `activeStrategy.total`；footer 沿用「筛选后 N 只 / 共 M 只」语义（`StockListTable.tsx:400-413`）。 | §3.3、§4.2 |
| H2 | **空态诚实、绝不误报。** 只看自选开启且 0 行 → 独立文案「自选清单中无该策略个股」，**绝不**渲染「无符合『』的个股」（filterText 空时文案荒谬，P4）。概念 + 只看自选同时激活且 0 行 → 优先只看自选文案（更窄的主动过滤）。 | §3.3、§4.2 |
| H3 | **guest 逐像素不变。** `GUEST_COLUMNS` 五列不动；guest 代码/名称单元格原样渲染服务端脱敏值（`StockListTable.tsx:228-242` 一字不改）；guest 不渲染星标/开关/批量按钮、不发任何 watchlist 查询。`GuestModeBanner` 的 `BANNER_TITLE/BANNER_BODY/GUEST_BANNER_ACCESSIBLE_TEXT` 为锁定 exported 常量，本期不动。 | §4.1、§4.2、§5 |
| H4 | **mode 由服务端声明，前端只消费不推导。** `mode = data?.mode === 'guest' ? 'guest' : 'vip'`（`PoolHubPage.tsx:34`）不变；前端零客户端掩码（不加 `******` 字面量、不加 `mask` 标识符——e2e grep 守卫 `:776-798`）。 | §4.1、§8 |
| H5 | **单一事实来源在服务端。** 自选清单 = `watchlist.parquet`；前端 = 共享 `QK.watchlist` 缓存投影。**不建第二套存储/独立 key**（WATCH-03 验收）。 | §5 |
| H6 | **匹配键 = 全后缀 `symbol` 精确全等。** `watchlistSet.has(row.symbol)`（`PoolHubRow.symbol` 与 `WatchlistEntry.symbol` 两端同格式）；无归一化、无模糊匹配。 | §4.2、§5 |
| H7 | **最新/历史天然同构。** `poolQuery` 按 `selectedDate` 切 key（`PoolHubPage.tsx:26-31`），两视图行形状 bit-identical；`watchlistSet` 全局不分日期 → 星标/过滤对任意 as_of 行做「当前自选」实时标注（非历史快照）。 | §4.1、§5 |
| H8 | **批量范围 = 可见行。** WATCH-04 只批量 `filteredRows`（display_limit 内，`len(rows) ≤ total`），**绝不**按未展开的 `total`。 | §4.1、§4.3 |
| H9 | **失败 fail-closed。** watchlist 查询 pending/error 期，星标与开关禁用（成员资格未知时不诱导误操作），不得以空集冒充「全未自选」。 | §4.2、§4.4 |

### Hard boundaries（binding）

1. **guest 像素级不变：** 游客会话下股池页 DOM 与 v2.0 完全一致——无星标按钮、无「只看自选」
   开关、无「批量加自选」按钮、无新文案。`GUEST_COLUMNS` 五列（`代码/名称/涨跌幅/概念板块/关联因子`）
   一字不动；guest 行 key（`${strategy.id}-${index}`）与 `rowKey` 逻辑不变（T-19-10 防御）。
2. **guest 零 watchlist 查询：** watchlist 查询必须 `enabled: !!data && mode === 'vip'` **双门控**
   （`data` 落地 + 服务端声明 vip 后才发）。违反将触发 guest 首屏 `/api/watchlist` → 401 →
   `main.tsx:22-27` 全局跳登录，破坏 guest 面（P2，最高危）。
3. **`total` 权威：** 卡片计数与 footer「共 M 只」永不因过滤改变；「筛选后 N 只 / 共 M 只」的
   N = `rows.length`、M = `total`。
4. **匹配键单一：** join 只允许 `watchlistSet.has(row.symbol)`（全后缀精确）；禁止用 `code`、
   `row.code` 匹配、大小写折叠或后缀猜测（失配应修入口，而非加模糊匹配）。
5. **批量范围限制：** WATCH-04 只对 `filteredRows`（可见行）调 `api.watchlistBatchAdd`；body
   symbol 数 ≤ display_limit 上限（200）。
6. **零后端/零依赖/零 vitest：** 本 phase 不改 `backend/`、不加 npm 依赖、不引入 vitest。
   `api.ts`/`queryKeys.ts`/`useSharedMutations.ts` 为纯复用**零改动**。
7. **POOL-03 e2e 守卫同步更新：** `pool-hub.spec.ts` 的 affordances 白名单与 no-mutating-request
   守卫必须随新控件更新（§8），否则测试红。
8. **不触碰 `Watchlist.tsx`：** 用户未提交改动文件，任何操作（读/改/提交）均禁止；只消费
   `api.watchlist*` + `QK.watchlist` 公共契约。

---

## 3. 视觉与交互规范

### 3.1 放置总览（钻取区）

```
section[aria-label="{activeStrategy.name} · 股池明细"]
├─ header 行（flex items-center justify-between gap-2）
│   ├─ <h2 class="text-sm font-semibold text-foreground">{name} · 股池明细</h2>   （既有）
│   └─ 右侧控件组（flex items-center gap-2，仅 mode==='vip' 渲染）
│       ├─ [只看自选]  switch（role="switch"，aria-checked）      ← WATCH-02
│       └─ [批量加自选] button（Star 图标 + 文案）                 ← WATCH-04（仅 !watchlistOnly）
├─ AuctionColumnStatusBadge（既有，条件渲染）
└─ <StockListTable …/>（新增 watchlist props；星标内嵌 VIP 代码单元格）   ← WATCH-01
```

**放置决策（RESEARCH OQ-1）：** 「只看自选」开关与「批量加自选」按钮放**钻取区 header**（`<h2>`
同行右侧），因为二者作用于当前策略的明细表行（`filteredRows`），是表格级控件，且视觉 backstop
只截表格区。**不**放页面级 ConceptFilter 行（概念筛选是全载荷级，二者作用域不同）。

### 3.2 星标按钮（WATCH-01，仅 VIP 代码单元格）

| 属性 | 规格 |
|---|---|
| 位置 | `StockListTable.tsx` VIP 代码 `<td>` 的 `<div class="flex items-center gap-2">` 内、`row.code` 之后；**仅 `!isGuest` 分支** |
| 形态 | lucide `Star`，`h-3.5 w-3.5`；在自选 = `fill="currentColor"` **实心**；不在 = 空心 |
| 颜色 | 在自选 `text-[#FACC15]`（amber，对齐 `StockInfoBar.tsx:224-226`）；不在 `text-muted hover:text-foreground hover:bg-elevated` |
| 按钮壳 | `p-1 rounded-btn transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed` |
| 可访问名 | `aria-label` + `title` = 在自选 `移出自选` / 不在 `加入自选`（icon-only 按钮**必须** aria-label，否则 e2e affordances 白名单取空名报错） |
| 状态 | `disabled={watchlistPending}`；`watchlistPending = toggleWatchlist.isPending \|\| watchlist.isPending \|\| watchlist.isError`（H9 fail-closed） |
| 交互 | 点击 `onToggleWatchlist(row.symbol, inList)` → `inList ? api.watchlistRemove : api.watchlistAdd` → 成功失效 `QK.watchlist` + `QK.watchlistEnriched()` |

**表头零变化：** 星标内嵌代码单元格，**不新增列** → 分组表头、`minWidth`、既有列序零改动。

### 3.3 空态分流（WATCH-02，渲染序固定）

在 `StockListTable` 现有两个空态基础上，新增「只看自选」独立空态。判定布尔：
`conceptActive = filterText.trim().length > 0`；`watchlistOnly`（prop）。

| 顺序 | 条件 | 渲染 |
|---|---|---|
| 1 | `watchlistOnly && rows.length === 0` | **【新增】** 「自选清单中无该策略个股」+ hint「试试关闭「只看自选」或切换策略。」（复用既有空态 div 结构：`flex flex-col items-center gap-1 py-10 text-center`） |
| 2 | `conceptActive && rows.length === 0` | 既有「无符合「{filterText}」的个股」+「清除筛选」按钮（保留，含「清除筛选」aria-label 已入白名单） |
| 3 | `!conceptActive && !watchlistOnly && rows.length === 0` | 既有「该策略当日无命中个股。」 |

> P4 防线：空态文案与「哪个过滤条件导致空」**解耦**——只看自选激活时不插值 filterText，
> 绝不渲染「无符合『』的个股」。概念 + 只看自选同时激活且 0 行 → 走第 1 条（自选是更窄的主动过滤）。

### 3.4 footer 计数（H1）

`filterActive = conceptActive || watchlistOnly`：

- 任一激活 → `筛选后 {rows.length} 只 / 共 {total} 只`（N 实时、M 权威不变）
- 均未激活 → `共 {total} 只`

### 3.5 响应式

| Viewport | 要求 |
|---|---|
| `≥1280px` | 钻取区 header 单行：h2 左、控件右；明细表自然宽 |
| `768–1279px` | 控件组 `flex-wrap` 换行不溢出；星标保持内嵌不换行 |
| `<768px` | 「只看自选」开关与「批量加自选」按钮满足 44×44 触控目标（`max-md:min-h-11 max-md:min-w-11`）；相邻触控目标间距 ≥8px；星标按钮 `max-md:h-11 max-md:w-11` |

---

## 4. 组件契约（props / 状态 / 交互 / aria / guest 行为）

### 4.1 `PoolHubPage.tsx`（modified — page / controller）

**新增 import：** `useMutation, useQueryClient`（`@tanstack/react-query`）、`Star`（lucide）、
`useWatchlistBatchAdd`（`@/lib/useSharedMutations`）、`storage`（`@/lib/storage`）。

**watchlist 查询（D4 双门控，唯一与 Screener 先例的差异）：**

```tsx
const watchlist = useQuery({
  queryKey: QK.watchlist,
  queryFn: api.watchlistList,
  enabled: !!data && mode === 'vip',   // H3/H4/H9: guest 全程零查询; data 未落地不误发 (P2)
})
const watchlistSet = useMemo(
  () => new Set((watchlist.data?.symbols ?? []).map((s: any) => s.symbol)),
  [watchlist.data],
)
```

**toggle mutation（逐字复制 `Screener.tsx:440-447`）：**

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

**只看自选 state（H5：只存 UI 偏好，绝不存 symbol 清单）：**

```tsx
const [watchlistOnly, setWatchlistOnly] = useState(() => storage.poolWatchlistOnly.get(false))
// onChange: setWatchlistOnly(v); storage.poolWatchlistOnly.set(v)
```

**filteredRows 扩展（概念 AND 只看自选，`PoolHubPage.tsx:43-51` 基础上追加）：**

```tsx
// 既有概念子串投影保留; 尾部追加:
if (watchlistOnly) return base.filter(r => watchlistSet.has(r.symbol))
```

**批量 handler（WATCH-04，scope = 可见行）：**

```tsx
const batchAdd = useWatchlistBatchAdd()   // 已封装 QK.watchlist + watchlistEnriched 双失效
const handleBatchAdd = () => {
  const symbols = filteredRows.map(r => r.symbol)   // 可见行 (display_limit 内), 绝不按 total
  if (!symbols.length) return
  batchAdd.mutate(symbols, {
    onSuccess: data => { /* toast: 已添加 ${data.added} 只到自选 */ },
    onError: () => { /* toast: 批量添加失败 */ },
  })
}
```

**钻取区 header 控件（仅 `mode === 'vip'` 渲染）：**

| 控件 | 规格 | 状态 |
|---|---|---|
| 「只看自选」switch | `role="switch"` + `aria-checked={watchlistOnly}` + `aria-label="只看自选"`（可见 label 同文案）；样式镜像 `ExtDataPullPanel.tsx:205-209`（`h-4 w-7 rounded-full`，on=`bg-accent`/off=`bg-border`，knob `translate-x-3.5`/`translate-x-0.5`） | `disabled={watchlist.isPending \|\| watchlist.isError}`（H9）；guest 不渲染 |
| 「批量加自选」button | `Star` 图标（`h-3.5 w-3.5`）+ 文案；`title="批量加自选"`；`h-9 px-3 rounded-btn border border-border bg-surface text-xs font-medium text-secondary hover:text-accent`；移动端 44px | `disabled={batchAdd.isPending}`；文案 pending 期 `添加中…`；**`watchlistOnly` 开启时整组隐藏**（可见行全在自选，语义最诚实，D6） |

**StockListTable 新 props 透传（受控接口，镜像 `ScreenerTableProps`）：**

```tsx
<StockListTable
  … 既有 props …
  mode={mode}
  watchlistSet={watchlistSet}
  onToggleWatchlist={(symbol, inList) => toggleWatchlist.mutate({ symbol, inList })}
  watchlistPending={toggleWatchlist.isPending || watchlist.isPending || watchlist.isError}
  watchlistOnly={watchlistOnly}
/>
```

### 4.2 `StockListTable.tsx`（modified — component / render）

**Props 扩展：**

```tsx
watchlistSet: Set<string>
onToggleWatchlist: (symbol: string, inList: boolean) => void
watchlistPending: boolean
watchlistOnly: boolean
```

**星标（仅 VIP 代码单元格；guest 分支 `:228-242` 一字不改）：**

```tsx
// VIP 分支 <div className="flex items-center gap-2"> 内, row.code 之后:
const inList = watchlistSet.has(row.symbol)
<button
  type="button"
  onClick={() => onToggleWatchlist(row.symbol, inList)}
  disabled={watchlistPending}
  aria-label={inList ? '移出自选' : '加入自选'}
  title={inList ? '移出自选' : '加入自选'}
  className="p-1 rounded-btn transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
>
  <Star className={`h-3.5 w-3.5 ${inList ? 'text-[#FACC15]' : 'text-muted hover:text-foreground hover:bg-elevated'}`}
    fill={inList ? 'currentColor' : 'none'} aria-hidden />
</button>
```

**空态/footer：** 按 §3.3/§3.4。本文件**不发任何请求**（星标状态来自 props；写操作全在
`api.ts` 封装层——e2e 源码 grep 守卫通过的前提）。

**guest 行为：** 无新 props 渲染；`GUEST_COLUMNS` 不动；`isGuest` 分支零变更。

### 4.3 `WatchlistFilter.tsx`（NEW，可选 — component，controlled）

**Analog：** `ConceptFilter.tsx` 受控行骨架。仅当开关逻辑放独立组件时创建（也可内联于
`PoolHubPage`，二选一由 executor 定；本契约按受控组件规格）：

```tsx
interface WatchlistFilterProps {
  value: boolean
  disabled?: boolean
  onChange: (v: boolean) => void
}
// 渲染: 可见 label「只看自选」+ role="switch" button (aria-checked={value})
// 零 fetch、零状态提升; guest 由 PoolHubPage 门控不渲染
```

### 4.4 `storage.ts`（modified — utility）

```ts
/** 股池「只看自选」过滤开关 (WATCH-02) — UI 偏好, 不落后端, 绝不存 symbol 清单 */
poolWatchlistOnly: kv<boolean>('pool-watchlist-only'),
```

key 沿用既有 kebab-case 风格（`storage.ts:8-20` `kv<T>()` 模式；Boolean 先例 `watchlistCandle`）。
**明令禁止**用它存自选 symbol 列表（H5/WATCH-03）。

---

## 5. 状态与数据流（查询 / 缓存 / mutation / 失效）

```mermaid
flowchart LR
  subgraph PoolHubPage[PoolHubPage.tsx]
    PQ[useQuery QK.poolHub/poolHistory] --> MODE[mode: guest|vip]
    PQ --> AS[activeStrategy.rows]
    WQ[useQuery QK.watchlist\nenabled: !!data && vip] --> WS[watchlistSet Set&lt;symbol&gt;]
    TM[toggleWatchlist mutation] --> INV[invalidate QK.watchlist\n+ watchlistEnriched]
    AS --> FR[filteredRows\n概念 AND 只看自选]
  end
  subgraph StockListTable[StockListTable.tsx]
    FR --> T[明细表]
    WS --> T
    TM --> T
    MODE --> T[guest 分支逐像素不变]
  end
  T --> S[星标按钮\n仅 VIP]
  FR --> FT[只看自选开关\n仅 VIP]
  FR --> BA[批量加自选\n仅 VIP 可见行]
```

| 环节 | 契约 |
|---|---|
| 查询 | `QK.watchlist`（`['watchlist']`，`queryKeys.ts:25`）全局共享；`api.watchlistList`（`api.ts:2025`）。**不新建独立 key**（WATCH-03）。 |
| 门控 | `enabled: !!data && mode === 'vip'`（H4/H9）。guest 会话**零查询、零写**。 |
| 缓存投影 | `watchlistSet = new Set(symbols.map(s => s.symbol))`；join = `Set.has(row.symbol)` 全等（H6）。 |
| mutation | 单只 `api.watchlistAdd/Remove`；批量 `api.watchlistBatchAdd`（`api.ts:2031-2036`，复用 `useWatchlistBatchAdd` `useSharedMutations.ts:32-41`）。 |
| 失效 | 所有增删成功 → `invalidateQueries(QK.watchlist)` + `invalidateQueries(QK.watchlistEnriched())`（Screener/弹窗同款）。**无乐观更新**（沿用 Screener 先例：pending 期 disabled）。 |
| 跨页一致 | 任一入口（自选页/策略页/弹窗/股池页）增删都失效同一 key → 股池星标/过滤即时一致；无需事件总线/轮询。 |
| SSE | `SSE_INVALIDATE_PREFIXES` 含 `'watchlist'`（`queryKeys.ts:215-216`）→ 行情 tick 会失效重取（本地小 parquet，开销可忽略）。**不可为此换 key**（破坏 WATCH-03）。 |
| 加载 | VIP 首帧：星标晚于表格（hub + watchlist 双请求，可接受）；pending 期星标/开关 `disabled`（H9）。 |
| 错误 | watchlist 查询 error（VIP）→ 星标/开关禁用 + `title="自选清单加载失败"`（fail-closed）；不显示阻断式 alert（成员标注不应阻塞明细表）。 |

---

## 6. 文案契约（Copywriting Contract）

| 元素 | 文案 | 备注 |
|---|---|---|
| 星标 aria/title（在自选） | `移出自选` | 入 e2e ALLOWED_RE 白名单 |
| 星标 aria/title（不在自选） | `加入自选` | 入 e2e ALLOWED_RE 白名单 |
| 「只看自选」开关 | `只看自选` | switch 可访问名 + 可见 label；入白名单 |
| 批量按钮（idle / pending） | `批量加自选` / `添加中…` | 入白名单 |
| 批量成功 toast | `已添加 {N} 只到自选`（N=`data.added`） | 复用 Screener 文案（`Screener.tsx` 先例） |
| 批量失败 toast | `批量添加失败` | — |
| 空态（只看自选，WATCH-02 新增） | 标题 `自选清单中无该策略个股`；正文 `试试关闭「只看自选」或切换策略。` | 诚实空态；不插值 filterText |
| 空态（概念，既有，保留） | `无符合「{filterText}」的个股` + `清除筛选` | 不改 |
| 空态（零命中，既有，保留） | `该策略当日无命中个股。` | 不改 |
| 错误（既有，保留） | `股池明细加载失败：{msg}。请重试。` / `股池加载失败：{msg}。请检查数据源后重试。` | 不改 |
| Guest 横幅（锁定常量，**本期不动**） | `BANNER_TITLE` / `BANNER_BODY` / `GUEST_BANNER_ACCESSIBLE_TEXT` | 不新增「登录后可用」引导（产品决策，本期不做） |

**Destructive actions：** 本 phase 无破坏性操作。「移出自选」（星标）不是 destructive——它是
可逆的成员切换，直接执行、无确认弹窗（对齐 Screener/弹窗先例）。「清除筛选」为既有控件，不改。

---

## 7. UI 状态覆盖（UI Considerations）

适用元素：星标按钮（interactive-control）、只看自选开关（interactive-control）、批量按钮
（interactive-control）、钻取明细表（list-collection）。适用状态：8/8 覆盖。

| Category | Element(s) | Status | Resolution / Reason |
|---|---|---|---|
| empty | 钻取明细表 / 只看自选开关 | ✅ covered | 只看自选开启且 0 行 → 文档化文案「自选清单中无该策略个股」（H2/§3.3 顺序 1）；概念/零命中既有空态保留 |
| loading | 星标 / 开关 / 批量按钮 | ✅ covered | watchlist 查询 pending（VIP）→ 星标与开关 `disabled`（H9）；明细加载沿用既有「股池明细加载中…」 |
| error | 星标 / 开关 | ✅ covered | watchlist 查询 error → 星标/开关禁用 + `title="自选清单加载失败"`（fail-closed）；明细既有错误 alert 保留 |
| populated | 钻取明细表（VIP） | ✅ covered | 常规行量下星标内嵌代码单元格、`h-3.5` 14px、无新列 → 不撑宽表格（minWidth 不变） |
| partial | 钻取明细表（VIP） | ✅ covered | 自选集合为部分行子集 → 逐行 `Set.has` 实心/空心并存；非自选行渲染空心星标 |
| overflow | 钻取明细表 | ✅ covered | 长概念 chip 既有 `max-w-40 truncate` 不变；星标不引入横向增长；表容器既有 `overflow-x-auto` |
| zero-one-many | 钻取明细表 / footer | ✅ covered | 0 行空态；1 行 footer「筛选后 1 只 / 共 N 只」；多行正常；文案恒用「只」无复数形变 |
| long-text | 星标 / 开关 / 批量按钮 | 🧪 backstop | 控件文案全部固定短串（移出自选/加入自选/只看自选/批量加自选）；视觉 backstop 快照（`pool-table-resonance.png`/`pool-table-filter-active.png`）经 `--update-snapshots` 复核 |

---

## 8. 视觉快照与 e2e 契约（受影响测试 + 更新方式）

### 8.1 必须同步更新的既有测试（3 条 POOL-03 守卫 + 1 条 backstop）

| 测试 | 位置 | 现断言 | 更新方式 |
|---|---|---|---|
| `pool page renders zero execution affordances (POOL-03)` | `pool-hub.spec.ts:591-641` | `ALLOWED_RE = /刷新股池\|当日池\|当日无命中\|数据不可用\|清除筛选\|清除概念筛选\|重试\|收起\|\+\d+\|上一个交易日\|下一个交易日\|最新/` 遍历 main 内所有按钮 | **白名单扩增**：`只看自选\|批量加自选\|加入自选\|移出自选`。icon-only 星标必须带 aria-label（`aria-label ?? textContent` 取名，空名即红）。 |
| `pool page never issues a mutating request (POOL-03)` | `pool-hub.spec.ts:620-643` | `nonGet toEqual([])` | **语义放宽到「非 watchlist 写仍为零」**：VIP 会话放行 `POST /api/watchlist` / `POST /api/watchlist/batch` / `DELETE /api/watchlist/{symbol}`，其余 non-GET 仍 `toEqual([])`；**guest 会话保持零 non-GET**（含 watchlist）。用 `page.on('request')` 捕获（既有 `captured` 数组复用）。 |
| `pool page source contains no execution API call or form` | `pool-hub.spec.ts:645-662` | 文件列表 grep `<form` / `api.\w*(order\|trade\|…)` / `fetch(..., {method: POST\|PUT\|DELETE\|PATCH})` | **零改动**（走 `api.watchlist*` 封装天然通过）；若新建 `WatchlistFilter.tsx` 则并入 checked files。 |
| `frontend contains no client-side masking code (grep guard)` | `pool-hub.spec.ts:776-798` | 禁 `\*{6,}` 字面量 / 行值推导 / `\bmask` | **零改动**——本期新代码不得含掩码字面量/标识符（H4）。 |
| `captures visual evidence for the five UI-SPEC backstop scalars` | `pool-hub.spec.ts:742-774` | VIP 载荷截 `pool-table-resonance.png` / `pool-table-filter-active.png`（含星标后画面变化） | **`npx playwright test pool-hub.spec.ts --update-snapshots` 重生成 + 人工复核**：只应出现星标/开关/批量按钮增量；**guest 快照（`pool-grid-populated.png`/`pool-empty-zero-hit.png`/`pool-card-unavailable.png`）不受影响，勿连带更新**（P3）。 |

### 8.2 `installShell` 增默认 watchlist mock（P5）

```ts
// installShell 末尾追加 — 避免 VIP 用例 /api/watchlist unhandled 500:
await page.route('**/api/watchlist**', route => json(route, { symbols: [] }))
// 具体用例后注册覆盖 (Playwright 后注册优先):
//   POST /api/watchlist/batch → { symbols: [], added: N }
//   DELETE /api/watchlist/{symbol} → { symbols: [] }
```

### 8.3 新增 e2e 用例（全部 desktop-only + installShell）

| 用例 | mock | 断言 |
|---|---|---|
| WATCH-01 VIP 星标渲染 + toggle | hub(vip) + `/api/watchlist` → `{symbols:[{symbol:'300750.SZ', added_at:'…'}]}` | `300750.SZ` 行星标 `aria-label=移出自选`；`600519.SH` 行 `=加入自选`；点 600519 星标 → 捕获 `POST /api/watchlist` 且 body.symbol 正确 → 星标翻转（缓存失效重取） |
| WATCH-01 guest 零查询 + 零控件 | hub(guest) | 捕获数组**不含 `/api/watchlist`**；`getByLabel('加入自选')` count 0、`getByRole('switch')` count 0（guest 逐像素不变的自动化断言） |
| WATCH-02 只看自选收窄 + total 权威 | hub(vip, 2 行) + watchlist 含 1 只 | 点开关 → 表格仅剩自选行；footer `筛选后 1 只 / 共 2 只` |
| WATCH-02 空态诚实 | hub(vip, 策略 A 行与自选无交集) | 开关开 → 空态「自选清单中无该策略个股」；关闭 → 行恢复 |
| WATCH-02 历史同构 | 切历史日期（`historyPayload` 夹具）后点开关 | 历史视图下开关同样生效、footer 计数权威 |
| WATCH-04 批量加可见行 | hub(vip) + watchlist 空 | 点「批量加自选」→ 捕获 `POST /api/watchlist/batch` 且 `body.symbols` 恰为可见行 symbol 数组；成功 toast `已添加 N 只到自选` |

### 8.4 验证命令

```bash
cd frontend && npm run build          # tsc -b && vite build（类型 + 构建门）
cd frontend && npx playwright test pool-hub.spec.ts   # 全部股池页用例（含 3 守卫）
cd backend && pytest                  # 回归：POOL-03 / guest 守卫仍绿（本 phase 零后端改动）
```

---

## 9. 验收（映射 WATCH-01..04）

| Req | 验收行为 | 契约条款 | 自动化 |
|---|---|---|---|
| WATCH-01 | VIP 每行星标：在自选=实心 amber、不在=空心；点击调 `api.watchlistAdd/Remove` → 失效 `QK.watchlist`(+`watchlistEnriched`);pending 禁用 | §3.2、§4.1、§4.2、§5 | e2e WATCH-01 两用例 |
| WATCH-01（guest） | guest 渲染逐像素与 v2.0 一致：无星标/无控件/无查询 | H3、硬边界 1/2、§4.2 | e2e WATCH-01 guest 零查询 |
| WATCH-02 | 「只看自选」开关收窄到自选行；与概念筛选 AND；`total` 权威不变；空态诚实；最新+历史同构；开关状态存 `storage.poolWatchlistOnly` | §3.3、§3.4、§4.1、§4.4 | e2e WATCH-02 三用例 |
| WATCH-03 | 复用 `QK.watchlist` + `api.watchlistList`；无独立存储/key；join 用 `row.symbol` 全等；增删失效后股池页即时一致 | H5/H6、§5 | e2e（toggle 后二次 fetch 出现）+ 代码审查 |
| WATCH-04（P2） | 批量按钮仅 VIP；scope=可见行 `filteredRows`（display_limit 内）；幂等；成功失效双 key；watchlistOnly 开启时隐藏 | §4.1、H8、硬边界 5 | e2e WATCH-04 一用例 |

**完成定义（Definition of Done）：** `25-UI-SPEC.md` 全契约落地 → `npm run build` 绿 →
`npx playwright test pool-hub.spec.ts` 绿（含 3 条更新后守卫 + 新 WATCH 用例）→ VIP 两张快照
人工复核、guest 快照未动 → 后端 `pytest` 绿 → 未触碰 `Watchlist.tsx` 与 `backend/`。

---

## 10. 设计系统（Design System）

| Property | Value |
|----------|-------|
| Tool | none（hand-rolled Tailwind 设计令牌，非 shadcn） |
| Preset | not applicable（`shadcn_initialized: false`） |
| Component library | none（既有 Tailwind 组件 + lucide-react 图标） |
| Icon library | `lucide-react` ^0.439.0（在树）— 本 phase 仅新增使用 `Star` |
| Font | 系统 UI 栈（既有，未声明新字体） |

### Spacing Scale（4 的倍数）

| Token | Value | Usage |
|---|---|---|
| xs | 4px | 星标 `p-1`、图标间距 |
| sm | 8px | 控件组 gap、触控目标间距 |
| md | 16px | 钻取区控件间距、表格单元格 px |
| lg | 24px | 钻取区 section 间距 |
| xl | 32px | 页面级分段 |
| 2xl | 48px | — |
| 3xl | 64px | — |

**Exceptions：** 星标图标 14px（`h-3.5`）；开关 16×28px（`h-4 w-7`，镜像 `ExtDataPullPanel`）；
移动端触控目标 44px（`max-md:h-11`/`max-md:w-11`）。

### Typography（既有令牌，不新增）

| Role | Size | Weight | Line Height | Token |
|---|---|---|---|---|
| Body | 14px | 400 | 1.5 | `text-sm` |
| Label | 12px | 500 | 1.4 | `text-xs font-medium` |
| Heading（钻取区 h2） | 14px | 600 | 1.2 | `text-sm font-semibold` |
| Display | — | — | — | 不适用（无新增展示型文本） |

### Color（60/30/10，沿用既有语义令牌）

| Role | Token | Usage |
|---|---|---|
| Dominant (60%) | `bg-base` / `bg-surface` | 页面背景、控件底色（`bg-surface`） |
| Secondary (30%) | `bg-elevated` / `border-border` / `text-secondary` / `text-muted` | 表头、卡片、边框、次要文本、空心星标 |
| Accent (10%) | `text-[#FACC15]`（amber）/ `bg-accent` / `text-accent` / `border-accent` | **仅限**：在自选星标实心 amber；开关 on 态轨道 `bg-accent`；开关 knob 白；按钮 hover 边框/文字；focus ring |
| Destructive | `text-danger` / `bg-danger/10` | 仅破坏性语义（既有错误 alert、「清除筛选」hover） |

**Accent 保留清单（explicit）：** 在自选星标（amber `#FACC15`）、「只看自选」开关 on 态、
「批量加自选」hover 强调、focus ring。**不**用于通用文本/装饰。

---

## 11. Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none | not applicable（未初始化 shadcn） |
| 第三方 registry | none | not applicable — 零新增包；仅复用树内 `lucide-react` / `@tanstack/react-query` |

**Package Legitimacy：** `lucide-react` / `@tanstack/react-query` 均为既有锁定依赖（非新增），
不触发安装门。

---

## 12. Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS（§6 文案契约，含空态/错误/aria）
- [ ] Dimension 2 Visuals: PASS（§3 视觉规范 + §10 设计系统）
- [ ] Dimension 3 Color: PASS（§10 60/30/10 + accent 保留清单）
- [ ] Dimension 4 Typography: PASS（§10 3 档字号 + 2 档字重）
- [ ] Dimension 5 Spacing: PASS（§10 4 的倍数 + exceptions）
- [ ] Dimension 6 Registry Safety: PASS（§11 零第三方）

**Approval：** pending

---

## 13. 不做什么（Explicit No-Go）

- ❌ 不碰 `frontend/src/pages/Watchlist.tsx`（用户未提交改动；只消费公共 API + `QK.watchlist`）。
- ❌ 不改 `backend/`（POOL-03 AST 守卫 + guest 掩码锁死；纯前端 join 是唯一路径）。
- ❌ 不加 npm 依赖、不引入 vitest。
- ❌ 不新建独立自选存储/查询 key（localStorage 第二清单、`watchlist-local` key 均禁止——WATCH-03）。
- ❌ 不在前端做任何客户端掩码（`******` 字面量 / `mask` 标识符 / 行值模式推导）。
- ❌ 不做历史自选快照（星标/过滤 = 当前自选对任意 as_of 的实时标注）。
- ❌ 不做服务端 `is_watched` 投影、不做批量按 `total`、不做模糊 symbol 匹配。
- ❌ 不把「登录后可用」塞进锁定的 `GuestModeBanner` 文案。
- ❌ 不引入乐观更新（沿用 Screener 先例：pending 期 disabled + 成功失效）。
