---
phase: 23
slug: frontend
status: draft
shadcn_initialized: false
preset: none
created: 2026-08-05
---

# Phase 23 — UI Design Contract（DateNavigator 按交易日浏览 + 竞价列钻取）

> Visual and interaction contract for the v2.0 前端收尾面：在既有 PoolHubPage 上落地
> (1) **DateNavigator**（‹ › 步进 + 日期列表）按交易日浏览股池，as_of 重取刷新卡片与明细；
> (2) **股池钻取竞价列** —— 真实集合竞价（竞价量/股、竞价金额/元）与派生/虚拟成交明确分组
> 展示，probe/窗口状态诚实呈现。本契约覆盖 **FRONT-01 / FRONT-02** 全部成功标准，并包含
> 唯一跨层改动（后端 `_project_hub` 透传竞价列 + `auction_columns` 声明字段）的前端消费契约。
> 后端 source of truth：`23-RESEARCH.md`（RQ1-RQ6、OQ-1~10、PIT-1~8）。

---

## 1. 目标与用户故事

### FRONT-01 — DateNavigator 按交易日浏览股池

**用户故事（User Story）：** 作为研究员，我想在股池页按**交易日**逐日浏览快照（‹ › 步进 + 日期下拉），
每次切换触发 `as_of` 重取并刷新策略卡片计数与钻取明细，以便回溯历史日的股池构成。非交易日
（周末/节假日/无快照日）在界面上**物理不可达**（不出现、不可选），**绝不静默跳日**；无快照日显示
**诚实的空态**（「该日期无股池快照」），绝不伪装成「当日零命中」。

**Success criteria mapping（REQUIREMENTS.md FRONT-01）：**

| 成功标准行为 | 本契约条款 |
|---|---|
| DateNavigator（‹ › 步进 + 日期列表） | §3.1、§4.2 |
| 每次步进触发 as_of 重取并刷新卡片计数与钻取明细 | §3.1、§4.1（queryKey 驱动重取） |
| 非交易日禁用且不静默跳日 | §3.1（白名单日期集 + 下标步进）、§7（不做什么） |
| 无快照日期显示诚实空态/状态文案，而非误导性零池 | §3.3、§4.1（`available:false` 分流）、§2 诚实规则 |

### FRONT-02 — 股池钻取竞价列（真实 vs 派生 + 诚实状态）

**用户故事：** 作为研究员，我想在股池钻取明细中看到**竞价列**（竞价量/股、竞价金额/元），并明确区分
**真实集合竞价**数据与**派生/虚拟成交**估算（竞价量比、虚拟未匹配金额），以便评估竞价策略命中股
的竞价强度。当竞价 probe 不可用或盘前时，界面诚实展示 probe/窗口状态（fail-closed 空态或派生
标注），**绝不暗示存在真实竞价数据**。

**Success criteria mapping（REQUIREMENTS.md FRONT-02）：**

| 成功标准行为 | 本契约条款 |
|---|---|
| 竞价列（竞价量/金额）在股池钻取中展示 | §3.2、§4.4（StockListTable 扩展） |
| 真实集合竞价 vs 派生/虚拟成交明确分开展示并标注单位（股/元） | §3.2（分组表头 + 单位 + tooltip）、§5.1（服务端 `auction_columns` 声明） |
| probe 非 `available` 或盘前 → 诚实展示 probe/窗口状态（fail-closed 或派生标注） | §3.3、§4.3（状态徽标）、§2 诚实规则 |
| 绝不暗示存在真实竞价数据 | §2（诚实规则）、§7（不做什么） |

### Phase boundary

- **In scope：** PoolHubPage 的 DateNavigator（`components/pool-hub/DateNavigator.tsx` 新建）、
  `selectedDate` state + `datesQuery` + `poolQuery` 切换、`available:false` 诚实空态分流、
  StockListTable 竞价列分组渲染（真实组/派生组 + 单位 + tooltip）、probe/盘前状态徽标
  （`AuctionColumnStatusBadge`）、后端 `_project_hub` 透传竞价列 + `auction_columns` 声明字段
  （OQ-2，本期唯一跨层改动）、`api.ts`/`queryKeys.ts` 类型与方法扩展、`e2e/pool-hub.spec.ts`
  扩展 mock 用例。
- **Out of scope：** 实时竞价列（历史快照无实时行情列）；竞价数据湖/Data 页竞价面板（Phase 16/20，
  已交付）；策略族/策略结果列（Phase 21）；股池概念筛选/交叉共振（Phase 18/19，既有逻辑复用）；
  任何 `/api/pool/hub` 单 as_of 契约改动（反漂移 + 17 回归零改动）；客户端合成 probe 判定或
  竞价列存在性；`frontend/src/pages/Watchlist.tsx`（用户未提交改动，绝不触碰）。

### Hard boundaries（binding，同 20-UI-SPEC 风格）

1. **真实/派生永不混排、永不相加：** 真实集合竞价列（`auction_volume` 竞价量/股、`auction_amount`
   竞价金额/元）与派生/虚拟成交列（`auction_volume_ratio` 竞价量比/×、`auction_unmatched_amount`
   虚拟未匹配金额/元·估算）必须物理分组展示、列头标注单位与「估算/虚拟」语义；任何合计、求和、
   合并列或颜色等同处理均禁止。
2. **无快照日 ≠ 零池日：** `available:false`（快照不存在，200 语义）渲染独立空态「该日期无股池
   快照」；`strategies.length === 0`（快照存在但全策略零命中）保持既有「当日无股池结果」。二者
   文案与图标必须可区分，渲染序上 `available:false` 先短路。
3. **probe 不可用 fail-closed：** 真实竞价列只在该快照计算时 probe `available` 且分区有行（服务端
   冻结的列存在性 `auction_columns.real`）时渲染；否则真实组整组不渲染 + warning 徽标「竞价数据
   未接入，仅展示派生列」，绝不渲染占位零值或把派生/虚拟数据呈现为真实竞价数据。
4. **09:30 bar 永不标集合竞价：** 09:30 起的连续竞价 bar 永不标记为集合竞价数据（沿用
   AuctionProbeCard 诚实词汇，Phase 16/20 契约）。
5. **single-as_of hub 契约不破坏：** 历史取池**必须**走 `GET /api/pool/history?as_of=`；`/api/pool/hub`
   反漂移回显缓存日期（PIT-1），拿它查历史是静默错误数据。`QK.poolHub` 与 `QK.poolHistory` 分离。
6. **游客掩码不泄露竞价列：** 游客会话行级 `auction_*` 列被 `_GUEST_VISIBLE` 白名单天然丢弃；
   顶层 `auction_columns` 声明字段必须对游客**整体剥离**（`mask_guest_hub` 顶层 drop，见 §5.4），
   新增守卫测试锁死。前端只渲染服务端返回字段（GUEST-01 哲学，绝不从行值推导模式/列存在性）。

---

## 2. 设计原则（诚实规则）

本契约的 UI 决策全部由以下诚实规则驱动（对应 23-RESEARCH.md §设计决策 OQ-1~10 与 PIT-1~8）：

| # | 规则 | 落地条款 |
|---|---|---|
| H1 | **列存在性由服务端声明，前端零猜测。** `auction_columns` 分组字段是唯一权威；前端绝不按行值 null 推导「该日有无真实竞价列」（PIT-3）。 | §4.4、§5.1 |
| H2 | **真实/派生两轨永不混用、永不相加。** 派生列头带「估算/虚拟」标注；无求和逻辑（PIT-4）。 | §3.2、§2 硬边界 1 |
| H3 | **冻结列存在性 vs 实时 probe 双轨。** 快照行列（含真实竞价列）由冻结声明决定，**历史快照不因今日 probe 状态被重写**；实时 probe/时段只驱动**状态徽标**（Pattern 4）。 | §3.3、§4.3 |
| H4 | **无快照日诚实空态。** `available:false` → 「该日期无股池快照」；`strategies.length===0` → 「当日无股池结果」（PIT-2）。 | §3.3、§4.1 |
| H5 | **非交易日物理不可达、绝不静默跳日。** 白名单日期集 + 下标步进（PIT-5）。 | §3.1 |
| H6 | **历史必走 history 端点。** 绝不拿 `/hub?as_of=` 查历史（PIT-1，最高危）。 | §4.1 |
| H7 | **游客零泄露。** 竞价列/open_gap 不出现在游客响应（PIT-7）。 | §5.4 |
| H8 | **类型诚实。** `updated_at` hub=epoch ms / history=ISO string 双型容忍（PIT-8）；`available` 显式可选键。 | §4.5 |

---

## 3. 视觉与交互规范

### 3.1 DateNavigator（日期步进 + 日期列表）

**放置（OQ-1 决议）：** PoolHubPage 内容区顶部 —— `PageHeader` 下方、加载/空态分支上方，
`div.px-4 py-4 space-y-3 sm:px-6 lg:px-8` 的**第一个子元素**。刷新按钮留在 `PageHeader.right`（既有）。

**布局：** 单行水平条 `flex flex-wrap items-center gap-2`，左对齐：

```
[‹]  [▼ 2026-08-04 ▾]  [›]  [最新]        ← selectedDate ≠ null 时显示「最新」
```

| 控件 | 规格 | 状态 |
|---|---|---|
| `‹`（上一个/更早交易日） | 图标按钮：`ChevronLeft`，`h-9 w-9 rounded-btn border border-border bg-surface text-secondary hover:text-accent hover:border-accent/50 transition-colors`，`aria-label="上一个交易日"` | 已到最旧（`idx === dates.length - 1`）或 `dates` 空 → `disabled:opacity-50 disabled:cursor-not-allowed` |
| `›`（下一个/更近交易日） | 图标按钮：`ChevronRight`，同上，`aria-label="下一个交易日"` | 已到最新（`idx === 0`）或 `idx === -1`（当前 as_of 不在列表，不猜测）→ disabled |
| 日期下拉 | 原生 `<select>`，`aria-label="选择日期"`，`h-9 rounded-input border border-border bg-surface px-3 text-xs text-foreground num`；options = `dates` 数组（ISO desc，label 同 value） | `dates` 空 → disabled + 显示 `暂无历史日期` |
| 「最新」复位 | 文本按钮：`h-9 px-3 rounded-btn border border-border bg-surface text-xs font-medium text-accent hover:border-accent/50`，label `最新`，`title="返回最新股池"` | 仅 `selectedDate !== null` 时渲染；点击置 null 回 `/api/pool/hub` |

**交互与步进语义（OQ-4）：**
- `dates` = `GET /api/pool/dates` 返回的 ISO desc 数组 = **有快照的交易日全集**（白名单）。
  `idx = dates.indexOf(currentAsOf)`，其中 `currentAsOf = selectedDate ?? latest ?? null`。
- `‹` 步进 → `selectedDate = dates[idx + 1]`（更早一日）；`›` 步进 → `selectedDate = dates[idx - 1]`
  （更近一日）。**严格在数组下标内移动 —— 非交易日/无快照日不在数组内，物理不可达，无
  「跳到最近有效日」逻辑。**
- 下拉 value = `selectedDate ?? latest ?? ''`；options 只含 `dates` 中存在的日期。
- `datesQuery` pending → 条内显示 `Loader2 animate-spin` + `加载日期中…`（`role="status"`），
  按钮 disabled。
- `datesQuery` error → 行内 `role="alert"`：`日期列表加载失败：{msg}` + `重试` 按钮
  （`datesQuery.refetch()`）。
- 移动端（<768px）：‹ › 按钮满足 44×44 触控目标（`max-md:min-h-11 max-md:min-w-11`），
  下拉与按钮换行不溢出；相邻触控目标间距 ≥8px。

**as_of 重取（Pattern 2）：** 步进只改 `selectedDate`；`poolQuery` 依据 key 变化自动重取
（`QK.poolHub()` / `QK.poolHistory(d)` 天然带日期维度，历史日各自缓存）。**不做手动 `refetch` 步进。**

### 3.2 竞价列分组（StockListTable 扩展）

仅 VIP（`mode === 'vip'`）且服务端返回 `auction_columns` 时生效；游客/无 `auction_columns` 时
表结构与既有完全一致（无竞价列，无分组表头）。

**分组表头（OQ-5 决议，两行 thead）：**

```
thead
  ├─ row 1 (group band):
  │    代码(rowSpan=2) │ 名称(rowSpan=2) │ 开盘涨幅(rowSpan=2) │ 涨跌幅(rowSpan=2)
  │    │ 概念板块(rowSpan=2) │ 关联因子(rowSpan=2)
  │    │ 真实集合竞价 (colSpan=2, accent, 仅 real.length>0) │ 派生 · 虚拟成交 (colSpan=2, secondary)
  └─ row 2 (member):
        竞价量（股） │ 竞价金额（元）     ← real 组（仅 real.length>0）
        竞价量比（×） │ 虚拟未匹配金额（元·估算）   ← derived 组
```

| 组带 | 视觉 | 成员列 | 列头单位/语义标注 | 渲染条件 |
|---|---|---|---|---|
| `真实集合竞价` | `text-accent` + `font-semibold` + 12px，底色 `bg-accent/[0.06]`，顶边 `border-accent/30`；`scope="colgroup"` | 竞价量（股）`auction_volume`；竞价金额（元）`auction_amount` | 单位在列头文本（股/元） | `auction_columns.real` 含 `auction_volume` 或 `auction_amount`（**整组同存同隐**） |
| `派生 · 虚拟成交` | `text-secondary` + `font-medium` + 12px，底色 `bg-elevated`；`scope="colgroup"` | 竞价量比（×）`auction_volume_ratio`；虚拟未匹配金额（元·估算）`auction_unmatched_amount` | 量比是**倍数**（×）非百分比；未匹配金额标注 **估算/虚拟** | `auction_columns.derived` 含 `auction_volume_ratio` 或 `auction_unmatched_amount`（`open_gap` 已在基础列「开盘涨幅」渲染，**不重复渲染**，见下） |

**`open_gap` 处理（OQ-5 附加决议）：** 既有基础列「开盘涨幅」已诚实渲染 `open_gap`
（fail-closed 基准恒在，20-RESEARCH 语义）。**不**将其物理搬入派生组（避免破坏既有列顺序与
`e2e` 断言，且无诚实增益 —— 列头「开盘涨幅」本就是诚实标签）。`auction_columns.derived` 声明
含 `open_gap` 仅作信息性确认（该快照基线列存在），前端不重复渲染。

**单元格渲染（OQ-7 决议）：**

| 列 | 值 | 格式化 | 空值 |
|---|---|---|---|
| 竞价量（股） | `row.auction_volume` | `fmtBigNum`（万/亿），`num tabular-nums`，右对齐，**无涨跌色** | `—`（`text-muted`） |
| 竞价金额（元） | `row.auction_amount` | `fmtBigNum`（万/亿），`num tabular-nums`，右对齐 | `—` |
| 竞价量比（×） | `row.auction_volume_ratio` | `value.toFixed(2) + '×'`（如 `2.35×`），`num tabular-nums`，右对齐 —— **不用 `fmtPct`**（量比是倍数非百分比） | `—` |
| 虚拟未匹配金额（元·估算） | `row.auction_unmatched_amount` | `fmtBigNum`（万/亿），`num tabular-nums`，右对齐 | `—` |

**Tooltip（`title` 属性，原生提示，零新依赖）：**

| 元素 | tooltip 文案 |
|---|---|
| `真实集合竞价` 组带 | `集合竞价撮合成交（09:15-09:25），仅在快照计算时竞价数据可用且分区有行时存在。` |
| `竞价量（股）` | `竞价量 = 集合竞价撮合成交量（单位：股）。` |
| `竞价金额（元）` | `竞价金额 = 集合竞价撮合成交额（单位：元）。` |
| `派生 · 虚拟成交` 组带 | `由竞价量与历史均量、委托量输入派生的估算值，非真实成交。` |
| `竞价量比（×）` | `竞价量 ÷ 前 5 日均量（不含当日）。` |
| `虚拟未匹配金额（元·估算）` | `虚拟未匹配量 × 虚拟参考价的估算值，非真实成交金额。` |

**真实组隐藏 + warning 徽标（OQ-5/6）：** 当 `auction_columns.real` 为空（或 real 组两列均不存
在）时：`真实集合竞价` 组带与其 2 成员列**整组不渲染**；派生组保留；表上方渲染 warning 徽标
「竞价数据未接入，仅展示派生列」。当 real 与 derived 均无可渲染列时，不加分组表头、不渲染徽标
（等同无竞价列）。

### 3.3 空态 / 状态徽标

**空态分流（OQ-8，渲染序固定）：**

```
1. poolQuery.isPending && !data           → 既有「股池加载中…」骨架（role="status"）
2. poolQuery.isError && !data             → 既有「股池加载失败…」role="alert" + 重试
3. data?.available === false              → 【新增】EmptyState「该日期无股池快照」   ← 先于零池短路
4. data && data.strategies.length === 0   → 既有 EmptyState「当日无股池结果」（零池语义，保留）
5. data && data.strategies.length > 0     → 概念筛选 → 策略卡片 → 钻取明细（含竞价列）
```

| 状态 | 判定信号 | 渲染 |
|---|---|---|
| 无快照日 | `data.available === false` | `EmptyState icon={CalendarX} title="该日期无股池快照" hint="{selectedDate} 无股池快照（非交易日或尚未生成）。请选择其他日期或返回最新。"` |
| 零池日 | `data.strategies.length === 0`（快照存在） | 既有 `EmptyState icon={ScanSearch} title="当日无股池结果"`（文案保留） |
| 日期列表为空 | `dates.length === 0` | DateNavigator 双按钮 disabled + 下拉 disabled 显示 `暂无历史日期`；hub 最新查询照常 |

**竞价状态徽标（§4.3 `AuctionColumnStatusBadge`，渲染于钻取区 `<h2>{name} · 股池明细</h2>` 与
`<StockListTable>` 之间，VIP 且有 `auction_columns` 时）：**

| 场景 | 判定信号 | 徽标文案 + 视觉 |
|---|---|---|
| 真实竞价列可用 | `auction_columns.real.length > 0` | `竞价数据可用 · 窗口 09:15-09:25`（accent + `CheckCircle2`，info） |
| 真实列缺席（probe 非 available） | `auction_columns.real` 空 且 `useAuctionProbe().data?.status !== 'available'` | `竞价数据未接入，仅展示派生列`（warning + `AlertTriangle`） |
| 真实列缺席（probe available 但快照无） | `auction_columns.real` 空 且 probe `available` | `该快照计算时无真实竞价数据，仅展示派生列`（warning + `AlertTriangle`） |
| 盘前/休市（今日） | `useQuoteStatus().data?.is_trading_hours === false` 且查看日 == 今日 | 追加 secondary 状态行：`盘前/休市 · 竞价窗口 09:15-09:25 未开始`（与列状态徽标并列，不覆盖） |

**诚实语义（H3）：** 徽标回答「当前数据源/时段状态」，列存在性回答「这张快照有没有真实竞价列」。
历史快照 `real` 非空 + 今日 probe `fail_closed` → 真实列**仍渲染**（历史事实不因今日状态重写），
徽标按 `auction_columns.real` 显示 info（见 §6 SC4 验收）。

**加载/错误语义（既有，保留）：** 明细加载中 `股池明细加载中…`（`role="status"` + `Loader2`）；
明细失败 `股池明细加载失败：{msg}。请重试。`（`role="alert"` + `重试`）。**诚实文字，不靠颜色/图标
单独传达状态。**

### 3.4 响应式

| Viewport | 要求 |
|---|---|
| `≥1280px` | 既有 PoolHubPage 布局不变；DateNavigator 单行水平条；明细表自然宽（含竞价列） |
| `768–1279px` | DateNavigator 换行自适应（`flex-wrap`）；明细表 `overflow-x-auto` 横向滚动 |
| `<768px` | DateNavigator ‹ › 按钮 44×44 触控目标；下拉/按钮堆叠换行；表头组带与列头文本 `whitespace-nowrap` 不折行，由横向滚动承载 |

明细表 `minWidth: 720` 在含竞价列时需增大（基础 6 列 + 4 竞价列 ≈ 940px，`style={{ minWidth: 940 }}`
或按列数计算）；横向滚动保留既有 `overflow-x-auto rounded-card border border-border` 容器。

---

## 4. 组件契约

### 4.1 查询与状态接线（PoolHubPage）

```tsx
// PoolHubPage.tsx — 既有 state 保留；新增 selectedDate + datesQuery + poolQuery 切换
const [selectedDate, setSelectedDate] = useState<string | null>(null)   // null = 最新

const datesQuery = useQuery({
  queryKey: QK.poolDates(),              // ['pool-dates']（新增）
  queryFn: api.poolDates,                // GET /api/pool/dates
  retry: 1,
})

// 单 query 按选中日期切换数据源（OQ-3）：历史必走 /api/pool/history，最新走 /api/pool/hub
const poolQuery = useQuery({
  queryKey: selectedDate ? QK.poolHistory(selectedDate) : QK.poolHub(),
  queryFn: () => (selectedDate ? api.poolHistory(selectedDate) : api.poolHub()),
  retry: 1,
  placeholderData: (prev) => prev,       // 切换日期保留旧数据避免整页闪空（Dashboard 同款）
})

const data = poolQuery.data
const asOf = data?.as_of ?? selectedDate ?? null        // 副标题：以实际数据日期为准（诚实）
const mode = data?.mode === 'guest' ? 'guest' : 'vip'   // 不变：服务端声明
const refresh = () => { void poolQuery.refetch() }      // 刷新当前选中日期
```

**诚实细节（placeholderData）：** key 切换后新查询未落地前，`data` = 上一日期的旧载荷（占位）。
副标题 `asOf = data?.as_of ?? selectedDate` 此时显示**旧载荷的真实 as_of**（绝不伪造目标日期的
`as_of`）；`pending = poolQuery.isFetching` 期间明细区显示 `股池明细加载中…`、卡片 `counting`。
新日期落地后 `available:false` 分支接管渲染空态。

**空态分流渲染序（PoolHubPage 渲染体，自上而下）：** `datesQuery` 加载/错误 → DateNavigator →
`poolQuery` 加载中骨架 → 加载失败 alert → `available === false` EmptyState（新）→ 零池
EmptyState（既有）→ 有结果分支（ConceptFilter → StrategyCardGrid → 钻取明细）。

### 4.2 `DateNavigator`（NEW，`frontend/src/components/pool-hub/DateNavigator.tsx`）

**Props（只读受控组件，无内部数据获取）：**

```tsx
export interface DateNavigatorProps {
  /** 有快照的交易日全集（ISO desc），GET /api/pool/dates 返回；白名单唯一日期集 */
  dates: string[]
  /** 服务端声明的最近快照日（dates[0]）；null = 无任何快照 */
  latest: string | null
  /** 当前选中日期；null = 最新（回 /api/pool/hub） */
  selectedDate: string | null
  /** datesQuery 加载中 → 显示「加载日期中…」+ 禁用步进 */
  loading?: boolean
  /** datesQuery 失败 → 行内 role="alert" + 重试回调 */
  error?: string | null
  onRetry: () => void
  /** 步进/下拉/「最新」唯一出口：null = 回最新 */
  onChange: (date: string | null) => void
}
```

**内部逻辑（OQ-4）：**
- `currentAsOf = selectedDate ?? latest ?? null`；`idx = currentAsOf ? dates.indexOf(currentAsOf) : -1`。
- `‹` `disabled = loading || dates.length === 0 || idx === dates.length - 1 || idx === -1`。
- `›` `disabled = loading || dates.length === 0 || idx === 0 || idx === -1`（`idx === -1` = 当前
  as_of 不在列表，不猜测 → 双禁用）。
- 下拉 `value = currentAsOf ?? ''`；`onChange={v => onChange(v || null)}`；options 渲染 `dates`；
  `dates.length === 0` 时下拉 disabled 并显示 `暂无历史日期`。
- 「最新」按钮 `selectedDate !== null` 时渲染，`onClick={() => onChange(null)}`。

### 4.3 `AuctionColumnStatusBadge`（NEW，`frontend/src/components/pool-hub/AuctionColumnStatusBadge.tsx`）

**Props：**

```tsx
export interface AuctionColumnStatusBadgeProps {
  /** 服务端冻结的竞价列存在性声明（§5.1）；null = 无竞价列契约（guest/后端未透传）→ 不渲染 */
  auctionColumns: AuctionColumnsDecl | null
  /** 当前载荷 as_of（用于「盘前」判定：查看日 == 今日） */
  asOf: string | null
}
```

**内部消费（H3 双轨）：** `useAuctionProbe()`（QK.auctionProbe，30s stale）+ `useQuoteStatus()`。
徽标状态机见 §3.3 表格。`auctionColumns == null` → 返回 `null`。文案与视觉全在 §3.3 / §5 Copywriting
契约，文字 + 图标成对，图标 `aria-hidden`。

### 4.4 `StockListTable`（MOD，`frontend/src/components/pool-hub/StockListTable.tsx`）

**新增 Props：**

```tsx
/** 服务端冻结的竞价列存在性声明；null/guest → 不渲染竞价列，表结构既有不变 */
auctionColumns?: AuctionColumnsDecl | null
```

**渲染规则（§3.2）：**
- `mode === 'guest'` 或 `auctionColumns` 为空 → 既有单行表头（GUEST_COLUMNS / VIP_COLUMNS），
  无竞价列、无分组。
- VIP 且 `auctionColumns` 有可渲染列 → 两行 thead（§3.2 结构）：基础列 `<th rowSpan={2}>`，
  `真实集合竞价` `<th colSpan={2} scope="colgroup">`（仅 real 组有可渲染列时）、
  `派生 · 虚拟成交` `<th colSpan={2} scope="colgroup">`（仅 derived 组有可渲染列时）。
- 行单元格按 §3.2 表格格式化；`row.auction_volume` 等为 `number | null | undefined`，null/NaN → `—`。
- 数值列右对齐 + `num tabular-nums`；竞价量/金额/未匹配金额**不套 `priceColorClass`**（非涨跌色）。

### 4.5 `api.ts` / `queryKeys.ts` 类型与方法扩展

**`frontend/src/lib/queryKeys.ts`：**

```ts
// 新增（pool-hub 不在 SSE_INVALIDATE_PREFIXES —— 股池按日静态，不需 tick 刷新，保持现状）
poolDates:   ['pool-dates'] as const,
poolHistory: (asOf: string) => ['pool-history', asOf] as const,
```

**`frontend/src/lib/api.ts`：**

```ts
export interface PoolDatesResponse {
  dates: string[]          // ISO desc，有快照交易日全集
  count: number
  latest: string | null
}

/** 服务端冻结的竞价列存在性声明（OQ-2）：列存在性唯一权威（H1） */
export interface AuctionColumnsDecl {
  real: string[]           // e.g. ["auction_volume","auction_amount"]；空 = 该快照无真实竞价列
  derived: string[]        // e.g. ["auction_volume_ratio","auction_unmatched_amount","open_gap"]
}

export interface PoolHubRow {
  // 既有 8 键不变
  symbol: string; code: string; name: string
  open_gap: number | null; change_pct: number | null
  concept_board: string[]; hit_factors: string[]; cross_resonance: boolean
  // Phase 23 新增（服务端声明存在性；guest 永无）
  auction_volume?: number | null
  auction_amount?: number | null
  auction_volume_ratio?: number | null
  auction_unmatched_amount?: number | null
}

export interface PoolHubResponse {
  as_of: string | null
  /** PIT-8 容忍：hub=epoch ms(number) / history=ISO string / 空态 null */
  updated_at: number | string | null
  mode: 'guest' | 'vip'
  strategies: PoolHubStrategy[]
  resonance_count: number
  /** Phase 23 新增：false = 无快照日诚实空态（200 语义，非 404） */
  available?: boolean
  /** Phase 23 新增：服务端冻结的竞价列存在性声明（仅 vip；guest 剥离） */
  auction_columns?: AuctionColumnsDecl
  concept_attribution?: string
}

// 新增方法
poolDates: () => request<PoolDatesResponse>('/api/pool/dates'),
poolHistory: (asOf: string) =>
  request<PoolHubResponse>(`/api/pool/history?as_of=${encodeURIComponent(asOf)}`),
```

**既有 `QK.poolHub(asOf?)` / `api.poolHub(asOf?, concept?)` 语义不变**（绑定 `/api/pool/hub`，
反漂移），`QK.poolHistory` / `api.poolHistory` 与它**物理分离**（PIT-1 防线）。前端概念筛选仍为
客户端投影，`api.poolHistory` **不传 concept**。

---

## 5. 后端契约（OQ-2 跨层透传）

本期唯一跨层改动：`_project_hub`（`backend/app/services/pool_hub.py:116-125`）透传竞价列 +
顶层 `auction_columns` 声明字段。`/api/pool/hub`、`/api/pool/dates`、`/api/pool/history` 端点语义
**零改动**（仅 `_project_hub` 输出扩展）。

### 5.1 `auction_columns` 声明字段（exact JSON shape）

`_project_hub` 对每行 raw row（快照 `df.to_dicts()` 已携带竞价列，screener.py:638/797）追加：

```python
# projected row（既有 8 键 + 4 竞价键，_safe_num 消毒）
{
  "symbol": "300750.SZ", "code": "300750", "name": "宁德时代",
  "open_gap": 0.0234, "change_pct": 0.0512,
  "concept_board": ["新能源"], "hit_factors": ["竞价多头"], "cross_resonance": True,
  "auction_volume": 1234567,          # 竞价量（股），仅 real 存在时
  "auction_amount": 234567890,        # 竞价金额（元），仅 real 存在时
  "auction_volume_ratio": 2.35,       # 竞价量比（×）
  "auction_unmatched_amount": 12345678,  # 虚拟未匹配金额（元·估算）
}
```

顶层响应新增 `auction_columns`（**逐快照冻结**，由投影时该快照列存在性决定）：

```json
{
  "as_of": "2026-08-04",
  "updated_at": "2026-08-04T09:25:00+08:00",
  "mode": "vip",
  "strategies": [ { "id": "auction_bullish", "name": "竞价多头", "total": 2, "rows": [/* 见上 */] } ],
  "resonance_count": 1,
  "concept_attribution": "current_snapshot",
  "auction_columns": {
    "real":    ["auction_volume", "auction_amount"],
    "derived": ["auction_volume_ratio", "auction_unmatched_amount", "open_gap"]
  }
}
```

**分组规则（后端权威）：**
- `real` 非空 **iff** 快照计算时 `resolve_auction_probe().status == available` **且**
  `kline_auction/date={d}` 分区有行（auction_columns.py 双闸门）—— 否则 `real: []`（fail-closed）。
- `derived` 包含 `auction_volume_ratio` / `auction_unmatched_amount` 当各自派生输入可得时；
  `open_gap` 恒在（fail-closed 基准恒在）。
- `test_pool_hub.py:246-253` 的 `expected_keys` 从 8 键扩展为 12 键（8 + 4 auction_*），并新增
  断言：real 存在时行携带 `auction_volume/auction_amount`，real 缺时列缺席（诚实缺列，非 null 占位）。

### 5.2 逐策略可用性语义（strategy-level availability）

点快照是一次性 `run_all_with_hits` 产物，**同一快照内所有策略共享同一 probe/分区状态** ——
因此 `auction_columns` 是**顶层（快照级）**声明，不逐策略重复。逐策略/逐股差异由**行级 null**
诚实表达：某股在 `kline_auction/date={d}` 分区缺席 → 该行 `auction_volume: null` → 前端渲染 `—`
（列存在但该标的缺席，PIT-3 由服务端声明消歧）。**若未来快照合并多个计算时点的策略**，再升级为
per-strategy `auction_columns`（本期 OQ，默认不做）。

### 5.3 `updated_at` PIT-8 容忍

- `/api/pool/hub`：`updated_at` 为 **epoch ms（number）**（strategy_cache.py:166
  `int(time.time()*1000)`）。
- `/api/pool/history`（快照存在）：`updated_at` = 快照 `computed_at`（**ISO string**）。
- 缺失分支：`updated_at: null`。
- 前端类型已声明 `number | string | null`（§4.5）。本期**不展示** `updated_at`；若后续展示，
  需 `fmtUpdatedAt` 双型容忍格式化（number→ms，string→ISO）。后端**不做**类型统一（诚实保留
  两源语义，前端容忍）。

### 5.4 游客掩码（H7）

- 行级：`mask_guest_hub` 的 `_GUEST_VISIBLE` 白名单（`{change_pct, concept_board, hit_factors,
  cross_resonance}`，guest_masking.py:18-24）构造 masked_row 时**天然丢弃** `auction_*` 与
  `open_gap`。
- **顶层（必须新增）**：`mask_guest_hub` 返回 `{**hub, "strategies": ...}` 会**透传**顶层
  `auction_columns` —— 必须显式剥离：`masked.pop("auction_columns", None)`（或在端点 vip-only
  注入）。否则游客虽无列数据，仍能读到「该日真实竞价列存在」的元信息，违反游客契约。
- **守卫测试**：`test_guest_masking.py` 新增断言 —— guest 响应无 `auction_columns` 键、行无
  `auction_*` 键、行无 `open_gap` 键。

---

## 6. 验收标准

### SC1 — DateNavigator 步进 + 日期列表 + as_of 重取

- `cd frontend && npm run build`（tsc -b + vite build）通过。
- **e2e（Playwright mock）**：`installShell(page)` 后 mock `/api/pool/dates` →
  `{dates:['2026-08-04','2026-08-01','2026-07-31'], count:3, latest:'2026-08-04'}` + `/api/pool/hub`
  → hubPayload + `/api/pool/history?as_of=` → 逐日 payload。
  - 初始：subtitle `竞价策略 · 数据日期 2026-08-04 · 仅研究参考`；`›` disabled、`‹` enabled。
  - 点 `‹` → subtitle 变 `数据日期 2026-08-01`；断言发出 `history?as_of=2026-08-01` 请求
    （计数 mock 不同值断言卡片刷新）。
  - 下拉选 `2026-07-31` → subtitle 更新 + `history?as_of=2026-07-31` 请求。
  - 点 `最新` → 回 `/api/pool/hub`，subtitle `2026-08-04`；「最新」按钮消失。
  - `›` 到最新（idx 0）→ disabled；`‹` 到最旧 → disabled。
  - 刷新按钮触发 `poolQuery.refetch()`（刷新当前日期，不换 key）。

### SC2 — 非交易日禁用 + 无快照日诚实空态

- **e2e：** 下拉 options 只含 `dates` 白名单日期（无周末/节假日）。
- mock `history?as_of=2026-08-02` → `{as_of:null, available:false, strategies:[], resonance_count:0,
  updated_at:null, mode:'vip', concept_attribution:'current_snapshot'}` → 断言 heading
  `该日期无股池快照` 可见，`当日无股池结果` **不出现**，无策略卡片/明细表。
- mock `dates: []` → 双按钮 disabled + 下拉显示 `暂无历史日期`。
- 渲染序断言：`available:false` 分支先于零池分支（用 zero-hit 载荷 + available:false 载荷分别断言
  两个不同 heading 各自出现）。

### SC3 — 竞价列分组 + 单位 + 真实/派生分离

- **e2e（VIP 载荷带 `auction_columns` + 行值）：**
  - 表头出现 `真实集合竞价`、`派生 · 虚拟成交` 组带；成员列 `竞价量（股）`、`竞价金额（元）`、
    `竞价量比（×）`、`虚拟未匹配金额（元·估算）`。
  - 行值：竞价量/金额 `fmtBigNum`（万/亿）、竞价量比 `2.35×`；null 行渲染 `—`。
  - 组带/列头 `title` tooltip 存在（可断言 `toHaveAttribute('title', /…/)`）。
- mock `auction_columns.real: []` → `真实集合竞价` 组带与成员列**不渲染**；warning 徽标
  `竞价数据未接入，仅展示派生列` 可见；派生组仍渲染。
- mock `auction_columns` 缺失（或 guest 载荷）→ 表无竞价列、无分组表头、无徽标（既有结构不变）。
- **后端（跨层）：** `cd backend && .venv/bin/python -m pytest tests/test_pool_hub.py -x -q` 全绿
  —— `expected_keys` 12 键 + 透传/诚实缺列测试。

### SC4 — probe/盘前诚实状态

- **e2e（mock `/api/data/auction-probe` + `quoteStatus`）：**
  - probe `available` + `real` 非空 → info 徽标 `竞价数据可用 · 窗口 09:15-09:25`。
  - probe `fail_closed` + `real` 空 → warning `竞价数据未接入，仅展示派生列`。
  - `quoteStatus.is_trading_hours: false` + 查看今日 → secondary 行
    `盘前/休市 · 竞价窗口 09:15-09:25 未开始`。
  - **历史快照诚实（H3）**：`history?as_of=2026-08-01` 载荷 `real` 非空 + 今日 probe
    `fail_closed` → 真实列**仍渲染**（列存在由冻结声明驱动，不被今日状态抹掉）；徽标按
    `auction_columns.real` 显示。
- **后端（游客守卫）：** `cd backend && .venv/bin/python -m pytest tests/test_guest_masking.py -x -q`
  全绿 —— guest 响应无 `auction_columns` / `auction_*` / `open_gap`。

### 门禁汇总

| 门禁 | 命令 | 范围 |
|---|---|---|
| 类型 + 构建（强制） | `cd frontend && npm run build` | 全部前端任务 |
| e2e（mock） | `cd frontend && npx playwright test e2e/pool-hub.spec.ts` | DateNavigator/空态/竞价列/状态徽标用例 |
| 后端跨层 | `cd backend && .venv/bin/python -m pytest tests/test_pool_hub.py -x -q` | OQ-2 透传 + expected_keys |
| 游客守卫 | `cd backend && .venv/bin/python -m pytest tests/test_guest_masking.py -x -q` | guest 无竞价列 |

---

## 7. 不做什么（Out of Scope / Anti-Goals）

- **不新增 npm 运行时依赖**（零新包；lucide-react 既有 `ChevronLeft/ChevronRight/CalendarX/Info/
  CheckCircle2/AlertTriangle/Loader2` 全部在册）。
- **不改 `/api/pool/hub` 单 as_of 契约**（反漂移 + 17 回归零改动）；历史必走 `/api/pool/history`。
- **不拿 `/api/pool/hub?as_of=` 查历史**（PIT-1 最高危）。
- **前端不推导 real/derived 列存在性**（只消费 `auction_columns` 声明，PIT-3）；不按行值 null 判断
  列存在。
- **不把 `available:false` 渲染为零池**（PIT-2）；两个空态文案永不互换。
- **不做实时竞价列**：历史快照无实时行情列；实时竞价数据面属 Data 页（Phase 16/20）范围。
- **不回填/补生成缺失快照**（后端不做；前端不假装有数据、不提供「生成」入口）。
- **不把 09:30 连续竞价 bar 标为集合竞价**（硬边界 4）。
- **不搬移/移除 `open_gap` 基础列**（保持既有列顺序与 e2e 断言；`open_gap` 不在派生组重复渲染）。
- **不把 `pool-dates` / `pool-history` 加入 SSE 失效前缀**（股池按日静态，不需 tick 刷新）。
- **不使用 DatePicker 做非交易日禁用**（其 `disabled` 仅按 min/max 计算，DatePicker.tsx:47-56，
  无法表达白名单日期集；用下拉白名单 + 下标步进替代）。
- **不触碰 `frontend/src/pages/Watchlist.tsx`**（用户未提交改动）。

---

## Open Questions（OQ 决议）

> 23-RESEARCH.md OQ-1~10 在本契约中的决议。未列出的视为研究已锁。

| # | 问题 | 本契约决议（默认） | 依据 |
|---|---|---|---|
| OQ-1 | DateNavigator 放置与状态 | 内容区顶部（PageHeader 下方、空态上方），`selectedDate: string \| null`（null=最新）；刷新留在 PageHeader.right | §3.1、§4.1 |
| OQ-2 | 竞价列如何到前端（跨层） | `_project_hub` 透传 4 键 + 顶层 `auction_columns` 声明；guest 顶层剥离 | §5.1、§5.4 |
| OQ-3 | 最新 vs 历史查询 | 单 `poolQuery` 按 `selectedDate` 切换 `QK.poolHub()`/`QK.poolHistory(d)` | §4.1 |
| OQ-4 | 非交易日禁用 | 下拉白名单 + 数组下标步进；`idx === -1` 双禁用不猜测 | §3.1、§4.2 |
| OQ-5 | 竞价列分组 UI | 两行分组表头；`open_gap` 留在基础列「开盘涨幅」不重复渲染 | §3.2 |
| OQ-6 | probe/盘前诚实态 | 冻结列存在性驱动数据列，实时 probe/时段驱动徽标（双轨 H3） | §3.3、§4.3 |
| OQ-7 | 单位格式化 | 表头承载单位（股/元/×/估算），单元格 `fmtBigNum`；量比 `toFixed(2)+'×'` | §3.2 |
| OQ-8 | `available:false` vs 零池空态 | 独立 EmptyState「该日期无股池快照」先短路；零池文案保留 | §3.3 |
| OQ-9 | guest 竞价列 | 后端 `_GUEST_VISIBLE` 行级丢弃 + 顶层 `auction_columns` 剥离；前端零处理 | §5.4 |
| OQ-10 | `updated_at` 类型 | 前端 `number \| string \| null` 容忍；本期不展示 | §4.5、§5.3 |

---

## Design System

| Property | Value |
|---|---|
| Tool | Manual existing system: Tailwind CSS 3.4 tokens and local React components |
| Preset | Not applicable — `components.json` absent as of 2026-08-05; do not initialize shadcn for this phase |
| Component library | Existing local components（`DateNavigator`/`AuctionColumnStatusBadge` NEW，`StockListTable`/`PoolHubPage`/`EmptyState`/`GuestModeBanner` MOD/复用）+ native semantic controls（原生 `select`/`button`）；无新组件注册表 |
| Icon library | `lucide-react`；14–16px outline icons beside visible labels（`ChevronLeft`/`ChevronRight`/`CalendarX`/`Info`/`CheckCircle2`/`AlertTriangle`/`Loader2`/`RefreshCw`） |
| Font | `Inter`、`HarmonyOS Sans SC`、`PingFang SC`、system sans；`JetBrains Mono`/`IBM Plex Mono` 仅用于数据、列标识、日期、单位、计数（mono/tabular） |
| Server state | 既有 typed `api.ts` + TanStack Query `QK` 工厂；无直接 `fetch`、无重复请求助手、无客户端合成 probe 判定或竞价列存在性 |

### 既有 visual tokens to preserve

沿用 `frontend/src/index.css` CSS 变量与 Tailwind 语义名（`base`/`surface`/`elevated`/`border`/
`foreground`/`secondary`/`muted`/`accent`/`bull`/`bear`/`warning`/`danger`）。深色为默认。1px
`border-border` 分隔；圆角 `rounded-input` 4px / `rounded-btn` 6px / `rounded-card` 8px /
`rounded-dialog` 12px。不引入渐变、玻璃面、超大圆角卡片、装饰性阴影或 Phase-23 专属调色板。

---

## Spacing Scale

声明值（全部 4 的倍数，沿用 20-UI-SPEC）：

| Token | Value | Usage |
|---|---:|---|
| xs | 4px | 图标-文本间隙、紧凑徽标 padding |
| sm | 8px | DateNavigator 相邻控件间距、组带到列行间隙 |
| md | 16px | 默认组件间距、面板内边距、真实↔派生组垂直分隔 |
| lg | 24px | 相关面板分隔、内容区左右 padding（`px-6`） |
| xl | 32px | 页面内区块分隔 |
| 2xl | 48px | 仅主工作流边界 |
| 3xl | 64px | 仅页级分隔；数据工具内不添加装饰性空白 |

**Exceptions：** 既有紧凑桌面控件沿用 8px padding。移动端（<768px）`‹ ›`/「最新」按钮 44×44
触控目标（`max-md:min-h-11 max-md:min-w-11`）；相邻触控目标间距 ≥8px。

---

## Typography

一套既有 sans 族用于全部 UI 标签/标题/按钮/正文；本期仅用以下四档字号、两档字重；代码/数据可用
既有 mono 族同档字号。

| Role | Size | Weight | Line Height |
|---|---:|---:|---:|
| Metadata / labels | 12px | 400 | 1.5 |
| Body / panel content | 14px | 400 | 1.5 |
| Section heading（`{name} · 股池明细`、组带） | 16px | 600 | 1.2 |
| Page heading（PageHeader） | 20px | 600 | 1.2 |

- `font-weight: 600` 仅用于页面/区块标题、状态名、主操作；其余 400。
- 列标识、单位、日期、计数、竞价数值用 mono + `tabular-nums`。
- 散文说明 ≤65ch；状态/徽标文案可随面板宽度换行且 `overflow-wrap:anywhere` 不溢出。

---

## Color

沿用既有限制深色优先系统；60/30/10 描述**表面分配**而非给所有控件上色。

| Role | Value | Usage |
|---|---|---|
| Dominant (60%) | `base`：dark `#0A0A0B`；light `#FAFAFA` | 应用/股池页背景 |
| Secondary (30%) | `surface`：dark `#18181B`；light `#FFFFFF`；`elevated`：dark `#212126`；light `#F4F4F5` | 面板、卡片、表头带（`bg-elevated`）、下拉/按钮背景 |
| Accent (10%) | `accent` `#3B82F6` | 真实集合竞价组带标识、info 徽标（`竞价数据可用 · 窗口 09:15-09:25`）、「最新」按钮、focus ring、`真实集合竞价` 文本 |
| Warning | `warning` `#F79009` | fail-closed/降级状态：`竞价数据未接入，仅展示派生列`、`该快照计算时无真实竞价数据，仅展示派生列` |
| Destructive | `danger` `#F04438` | probe 失败诊断与真破坏性控件 |
| Market direction | `bull` `#F04438` 红涨 / `bear` `#12B76A` 绿跌 | 仅 `开盘涨幅`/`涨跌幅`；**绝不用于竞价量/金额/徽标** |

Accent 保留给：主操作、激活态、focus ring、中性信息标识（真实竞价列身份、info 徽标）。**不是**
装饰色、通用卡片边框、或每个可点击元素的视觉状态。`bear` 绿仅限市场方向，**不**作通用「可用」
成功色（`竞价数据可用` 用 accent + 勾选图标）。

真实/派生区分由**可见文字标签**（`真实集合竞价` / `派生 · 虚拟成交`）、分组物理分隔与列头单位/
「估算」标注传达，**绝不靠颜色单独传达**。`估算` 语义在列头文本（`（元·估算）`），中性信息性。

所有普通文本/交互标签对所在表面 ≥4.5:1；大号/粗体与 focus indicator ≥3:1。每个状态/市场方向
状态提供文字 + 图标冗余。

---

## Copywriting Contract

| Element | Copy |
|---|---|
| Primary CTA（既有，保留） | `刷新股池`（PageHeader.right） |
| DateNavigator 步进按钮 aria-label | `上一个交易日` / `下一个交易日` |
| DateNavigator 下拉 aria-label | `选择日期` |
| 「最新」复位按钮 | `最新`（title `返回最新股池`） |
| 日期列表加载中 | `加载日期中…`（`role="status"`） |
| 日期列表加载失败 | `日期列表加载失败：{message}` + `重试`（`role="alert"`） |
| 日期列表为空 | `暂无历史日期`（下拉 disabled 显示） |
| 无快照日空态标题（新增） | `该日期无股池快照` |
| 无快照日空态正文（新增） | `{selectedDate} 无股池快照（非交易日或尚未生成）。请选择其他日期或返回最新。` |
| 零池空态（既有，保留） | 标题 `当日无股池结果`；正文 `截至 {asOf ?? '—'}，竞价策略均无命中个股。请先在策略页运行竞价策略，或确认数据日期。` |
| 真实集合竞价组带 | `真实集合竞价` |
| 真实列 | `竞价量（股）` · `auction_volume`；`竞价金额（元）` · `auction_amount` |
| 派生 · 虚拟成交组带 | `派生 · 虚拟成交` |
| 派生列 | `竞价量比（×）` · `auction_volume_ratio`；`虚拟未匹配金额（元·估算）` · `auction_unmatched_amount` |
| Info 徽标（真实列可用） | `竞价数据可用 · 窗口 09:15-09:25` |
| Warning 徽标（真实列缺席，probe 非 available） | `竞价数据未接入，仅展示派生列` |
| Warning 徽标（真实列缺席，probe available） | `该快照计算时无真实竞价数据，仅展示派生列` |
| 盘前/休市状态行 | `盘前/休市 · 竞价窗口 09:15-09:25 未开始` |
| 明细加载中（既有） | `股池明细加载中…` |
| 明细失败（既有） | `股池明细加载失败：{message}。请重试。` |
| 研究只读声明（既有） | `本页面仅用于研究参考，不提供任何交易执行功能。` |
| Destructive confirmation | None in Phase 23 — 无破坏性操作 |

使用清晰中文任务语言，不用未解释的内部实现名。`auction_volume` 等列标识可作为可检查元数据出现
但必须伴随人类可读标签（列头中文 + 单位）。

---

## UI Considerations

> 由 ui-phase UI-consideration probe 填充（Step 9.5）；空态/错误态文案见上方 Copywriting Contract，
> 本节覆盖状态形状并引用对应行，不重复文案。

Applicable state considerations resolved: 9 covered, 3 backstop, 0 unresolved。

| Category | Element(s) | Status | Resolution / Reason |
|---|---|---|---|
| loading | DateNavigator 日期列表 | ✅ covered | `加载日期中…` + `Loader2` + `role="status"`；步进按钮 disabled（§3.1） |
| loading | 明细区（日期切换） | ✅ covered | `placeholderData` 保留旧数据 + `股池明细加载中…` + 卡片 `counting`；副标题显示旧载荷真实 `as_of`（诚实占位） |
| error | DateNavigator 日期列表 | ✅ covered | `日期列表加载失败：{msg}` + `重试`（`role="alert"`） |
| error | 明细区 | ✅ covered | 既有 `股池明细加载失败：{msg}。请重试。`（`role="alert"` + 重试） |
| empty | 日期列表为空 | ✅ covered | `暂无历史日期` + 双按钮/下拉 disabled |
| empty | 无快照日 | ✅ covered | 独立 EmptyState `该日期无股池快照`，先于零池短路；零池 `当日无股池结果` 保留 |
| populated | 有数据（VIP + 竞价列） | ✅ covered | 两行分组表头 + 竞价列 + 状态徽标（§3.2/§3.3） |
| partial | real 空 derived 有 | ✅ covered | 真实组整组不渲染 + warning 徽标 `竞价数据未接入，仅展示派生列`；派生组保留 |
| partial | 行级 null（某股分区缺席） | ✅ covered | 单元格 `—`（列存在但该标的缺席，服务端声明消歧 PIT-3） |
| zero-one-many | dates 计数 0/1/many | ✅ covered | 0 → 全禁用 + `暂无历史日期`；1 → ‹ › 均 disabled（最新==最旧）；many → 下标步进 |
| overflow | 明细表宽 | 🧪 backstop | 含竞价列 `minWidth ~940px` + `overflow-x-auto` 横向滚动；visual 截图回测 |
| long-text | 状态徽标/空态文案 | 🧪 backstop | `overflow-wrap:anywhere` 安全换行，不截断；visual 截图回测 |
| zero-one-many | 真实/派生列数 | 🧪 backstop | real/derived 可渲染列 0/1/2 的组带 colSpan 正确（0 → 组带不渲染）；visual 截图回测 |

<!-- Status vocabulary (locked by probe-core projectTruths):
     ✅ covered   → a plain truth string lifted into must_haves.truths
     🧪 backstop  → a flat scalar { statement, verification: backstop }; at verify time, no explicit
                    evidence → insufficient_spec → human_needed (never a silent pass, #1154)
     ⚠ unresolved → an explicit planner assumption (surfaced, never silently dropped)
     Rows are REPLACED (not appended) on a probe re-run — idempotent. -->

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|---|---|---|
| shadcn official | None | Not applicable — `components.json` absent when scanned on 2026-08-05; shadcn initialization explicitly excluded for this phase. |
| Third-party registry | None | No third-party blocks declared or permitted; no registry vetting needed. 零新增 npm 依赖。 |

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: 诚实空态/状态徽标/分组标注文案清晰，真实 vs 派生与估算语义无歧义，无未解释内部名
- [ ] Dimension 2 Visuals: 既有 PoolHubPage 布局内嵌 DateNavigator + 分组表头扩展，无重复 shell/新路由
- [ ] Dimension 3 Color: 既有 60/30/10 token，accent 保留给真实列/info/「最新」/focus，warning 仅 fail-closed，无市场方向色误用于竞价量/徽标
- [ ] Dimension 4 Typography: 四档字号/两档字重，mono/tabular 数据列、单位、日期、计数
- [ ] Dimension 5 Spacing: 4px 基数、移动端 44px 触控例外、真实↔派生组节奏
- [ ] Dimension 6 Registry Safety: 无 shadcn 初始化、无第三方 registry；时间戳化的缺席证据已记录

**Approval:** pending
