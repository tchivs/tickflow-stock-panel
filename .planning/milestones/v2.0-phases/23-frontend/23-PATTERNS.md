# Phase 23: 前端 (Frontend) — DateNavigator 按交易日浏览 + 竞价列钻取 - Pattern Map

**Mapped:** 2026-08-05
**Files analyzed:** 9（6 前端 / 3 后端跨层）
**Analogs found:** 9 / 9（exact 6 / role-match 2 / partial 1；另有 4 处子功能级无既有 analog 的缺口，见 No Analog Found）

> 本文件把 Phase 23 的每个新建/修改文件映射到仓库内最接近的既有实现，并给出可直接复制/镜像的具体代码段（带文件路径与行号）。Phase 23 的核心是 **DateNavigator 按交易日步进**（‹ › + 日期下拉 + as_of 重取 + 非交易日禁用 + 无快照日诚实空态）+ **竞价列钻取**（真实集合竞价 vs 派生/虚拟成交分组 + 单位标注 + probe/盘前诚实状态）。前端日期 state 进 queryKey 触发重取镜像 `LimitUpLadder.tsx:1391/1474-1476` 与 `Dashboard.tsx:499/507-510`；查询层扩展镜像 `api.ts:2071-2079`（poolHub）+ `queryKeys.ts:41`（QK.poolHub）；表格列插入点即 `StockListTable.tsx:17-18`（GUEST/VIP_COLUMNS）+ 行渲染 `:144-229`；空态/状态徽标镜像 `EmptyState.tsx:10-23` / `AuctionProbeCard.tsx:5-13` 诚实词汇；**唯一跨层改动**是 `pool_hub.py:116-125` 投影循环透传竞价列 + 服务端声明 `auction_columns` 分组字段（对齐 GUEST-01「只消费 server 声明」哲学）。**真正无类比的是 4 个子功能**：白名单式 ‹ › 步进组件（DatePicker 只支持 min/max）、真实/派生两组表头渲染（screener/watchlist 分组是列自定义器模型非渲染表头）、`auction_columns` 服务端列存在性声明字段、`available:false` 独立空态分流（pool_hub.py:207 有服务端形状但前端无消费先例）。planner 需以 23-RESEARCH.md（RQ3/RQ4/OQ-2/OQ-5 + PIT-1..8）兜底。

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `frontend/src/components/pool-hub/DateNavigator.tsx` (new) | component | request-response（纯客户端 state） | `DatePicker.tsx` 按钮+AnimatePresence 下拉形 (116-163) + ChevronLeft/Right (143-147) + `LimitUpLadder.tsx` asOf state (1391) + queryKey 切换 (1474-1476) | partial |
| `frontend/src/components/pool-hub/StockListTable.tsx` (modified) | component | CRUD render | 模块内 GUEST/VIP_COLUMNS (17-18) + PctCell (70-77) + 行渲染 (144-229) | exact (in-file) |
| `frontend/src/pages/PoolHubPage.tsx` (modified) | page/controller | request-response | 模块内 hubQuery (22-26) + mode 声明 (36-39) + 零池空态 (125-132) + 刷新按钮 (79-96) | exact (in-file) |
| `frontend/src/lib/api.ts` (modified) | API client | request-response | 模块内 poolHub (2071-2079) + PoolHubRow/Response 类型 (683-709) + auctionProbe (2181) | exact (in-file) |
| `frontend/src/lib/queryKeys.ts` (modified) | config | — | 模块内 QK.poolHub (41) + limitLadder (40) + SSE_INVALIDATE_PREFIXES (211-223) | exact (in-file) |
| `frontend/e2e/pool-hub.spec.ts` (modified) | test | transform | 模块内 installShell 全 mock 夹具 (144-173) + hubPayload (23-44) + 逐用例 route (179 起) | exact (in-file) |
| `backend/app/services/pool_hub.py` (modified) | service | request-response | 模块内 `_project_hub` 投影循环 (78-130, projected 116-125) + `_safe_num` 消毒 (42-53) | exact (in-file) |
| `backend/tests/test_pool_hub.py` (modified) | test | transform | 模块内 expected_keys 锁死 (246-253) | exact (in-file) |
| `backend/tests/test_guest_masking.py` (modified) | test | transform | `guest_masking.py` `_GUEST_VISIBLE` 白名单 (18-24) + mask_guest_hub (31-43) | role-match |

## Pattern Assignments

### 1. `frontend/src/components/pool-hub/DateNavigator.tsx` (new, component / request-response)

**Analog:** `DatePicker.tsx` 按钮 + AnimatePresence 下拉（116-163）+ 月导航 ChevronLeft/ChevronRight（143-147）；`LimitUpLadder.tsx` asOf state + queryKey 切换（1391, 1474-1476）；`Dashboard.tsx` placeholderData 平滑切换（507-510）。

**组件壳（复制 DatePicker.tsx:116-163 的按钮 + AnimatePresence 弹出形 — 零新增图标，lucide 在册）:**
```tsx
// DatePicker.tsx:143-147 — 同款 ‹ › 步进按钮
<button type="button" onClick={prevMonth} className="p-1 rounded-btn hover:bg-elevated text-secondary ...">
  <ChevronLeft className="h-4 w-4" />
</button>
<button type="button" onClick={nextMonth} className="p-1 rounded-btn hover:bg-elevated text-secondary ...">
  <ChevronRight className="h-4 w-4" />
</button>
```
```tsx
// DatePicker.tsx:116-121 — 触发按钮样板 (h-7 px-2.5 rounded-input + Calendar icon)
<button type="button" onClick={() => setOpen(!open)}
  className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-input border border-border bg-elevated ...">
  <Calendar className="h-3.5 w-3.5 text-accent" />
  <span className={value ? undefined : 'text-muted'}>{displayLabel}</span>
</button>
```

**受控 state 契约（镜像 LimitUpLadder.tsx:1391 的 asOf state — 组件只读受控，父页持有日期）:**
```tsx
// LimitUpLadder.tsx:1391
const [asOf, setAsOf] = useState('')
// Dashboard.tsx:499 — null 语义 (Phase 23 用 null=最新, 与 Dashboard undefined=未选 同构)
const [selectedDate, setSelectedDate] = useState<string | undefined>()
```
> DateNavigator props 设计 `{ dates: string[]; value: string | null; onChange: (d: string | null) => void }` — 组件不持有 state，步进/下拉/复位全部回调父页（`PoolHubPage` 是唯一 state 持有者，DRY）。

**Deltas（新形态，无既有单组件 analog）:**
- **白名单步进**: `idx = dates.indexOf(currentAsOf)`；`‹ disabled = idx === dates.length - 1 || idx === -1`，`› disabled = idx === 0 || idx === -1`。**用户只能在 `dates` 数组内移动 → 非交易日物理不可达，无「静默跳日」语义**（DatePicker 做不到——见 No Analog Found #1）。
- 下拉 `select` options = `dates` 数组（原生 select 天然只列可用日）；`dates` 空数组 → 下拉 disabled + 「暂无历史日期」。
- 「最新」复位 = `onChange(null)` → 父页切回 `QK.poolHub()`。
- 无障碍: 步进按钮带 `aria-label="上一个交易日"/"下一个交易日"`，`disabled` 时 `aria-disabled`（沿 StrategyCardGrid.tsx:60-62 的 `disabled`/`aria-pressed` 双标记形）。

---

### 2. `frontend/src/components/pool-hub/StockListTable.tsx` (modified, component / CRUD render)

**Analog:** 模块内 GUEST/VIP_COLUMNS (17-18) + 按 mode 选列 (99) + PctCell (70-77) + 行渲染 (144-229) + footer meta (240-250)。

**列定义 + 按 mode 选列（复制 StockListTable.tsx:17-18 + :99 — 竞价列插入点）:**
```tsx
const GUEST_COLUMNS = ['代码', '名称', '涨跌幅', '概念板块', '关联因子'] as const
const VIP_COLUMNS = ['代码', '名称', '开盘涨幅', '涨跌幅', '概念板块', '关联因子'] as const
// :99
const columns = mode === 'guest' ? GUEST_COLUMNS : VIP_COLUMNS
```

**空值单元格规范（复制 PctCell:70-77 — 空值渲染 `—`，Phase 23 竞价列空值同款）:**
```tsx
function PctCell({ value }: { value: number | null }) {
  if (value == null || Number.isNaN(value)) return <span className="text-muted">—</span>
  return (
    <span className={cn('num tabular-nums', priceColorClass(value))}>
      {fmtPct(value)}
    </span>
  )
}
```

**行渲染骨架（复制 :144-229 的 tr/td 链 — 竞价列作为新 `<td>` 追加在 open_gap 之后）:**
```tsx
{!isGuest && <td className="px-3 py-2"><PctCell value={row.open_gap} /></td>}  // :205-206 VIP-only 列
<td className="px-3 py-2"><PctCell value={row.change_pct} /></td>
<td className="px-3 py-2"><ConceptChips concepts={row.concept_board} /></td>
```
> guest 列裁剪逻辑（`!isGuest &&` 整列不渲染，:205）是竞价列「guest 自动无列」的既有样板——后端 `mask_guest_hub` 白名单已丢弃竞价列，前端**不需要**额外处理，只渲染服务端返回字段即可。

**Deltas（真实/派生两组表头 — 见 No Analog Found #2）:**
- 在 `<thead>` 加第二行分组表头：`<tr><th colSpan={N}>真实集合竞价</th><th colSpan={M}>派生 / 虚拟成交</th></tr>`，各组列头带单位（竞价量 股 / 竞价金额 元 / 竞价量比 × / 虚拟未匹配金额 元·估算）。
- 分组渲染由服务端 `auction_columns.real/derived` 驱动（OQ-2 声明字段）；`real` 空数组 → 真实组整组不渲染 + warning 徽标「竞价数据未接入，仅展示派生列」。
- 数值单元格用 `fmtBigNum`（万元/亿，format.ts:44-52）显示竞价量/金额，单位由**表头承载**（对齐 LimitUpLadder `fmtSealVol`/`fmtSealAmount` 大数转万/亿，LimitUpLadder.tsx:125-135）；`auction_volume_ratio` 用 `toFixed(2) + '×'`。

---

### 3. `frontend/src/pages/PoolHubPage.tsx` (modified, page/controller / request-response)

**Analog:** 模块内 hubQuery (22-26) + mode 声明 (36-39) + 零池空态 (125-132) + 刷新按钮 (79-96)。

**单查询按选中日期切换（复制 :22-26 形，追加 selectedDate 分支 — Phase 23 核心模式）:**
```tsx
// 现: PoolHubPage.tsx:22-26
const hubQuery = useQuery({
  queryKey: QK.poolHub(),
  queryFn: () => api.poolHub(),
  retry: 1,
})
// Phase 23 改为: 同构 LimitUpLadder.tsx:1474-1476 (asOf 进 key)
const [selectedDate, setSelectedDate] = useState<string | null>(null)   // null = 最新
const datesQuery = useQuery({ queryKey: QK.poolDates(), queryFn: api.poolDates })
const poolQuery = useQuery({
  queryKey: selectedDate ? QK.poolHistory(selectedDate) : QK.poolHub(),
  queryFn: () => selectedDate ? api.poolHistory(selectedDate) : api.poolHub(),
  retry: 1,
  placeholderData: (prev) => prev,   // Dashboard.tsx:510 同款 — 切换日期保留旧数据防闪空
})
```

**服务端 mode 声明（复制 :36-39 — 绝不从行值推导，GUEST-01 铁律）:**
```tsx
const mode = data?.mode === 'guest' ? 'guest' : 'vip'
```

**空态分流（复制 :125-132 零池 EmptyState 形 — 新增 available:false 独立分支，短路于零池之前）:**
```tsx
{data && data.strategies.length === 0 && (
  <EmptyState icon={ScanSearch} title="当日无股池结果"
    hint={`截至 ${asOf ?? '—'}，竞价策略均无命中个股。…`} />
)}
// Phase 23 新增 (渲染序在零池分支之前):
{data && data.available === false && (
  <EmptyState icon={CalendarX} title="该日期无股池快照"
    hint={`${selectedDate} 无股池快照（非交易日或尚未生成）。请选择其他日期或返回最新。`} />
)}
```
> **PIT-2**: `available === false`（无快照日, pool_hub.py:207）与 `strategies.length === 0`（零池日）是两种诚实空态，文案必须区分。`PoolHubResponse` 需加 `available?: boolean`（现类型 api.ts:701-709 无此键）。

**Deltas:**
- PageHeader subtitle 显示选中日期（沿用 :73 的 `asOf ? \`竞价策略 · 数据日期 ${asOf} …\`` 模式）。
- 刷新按钮 `refresh()` 改 `void poolQuery.refetch()`（:83-85 形不变，刷当前日期）。
- `DateNavigator` 放 PageHeader 下方、ConceptFilter 上方；`data.as_of` 不在 `dates` 时步进按钮按 `-1` 处理禁用（RQ3 边界，不猜测）。

---

### 4. `frontend/src/lib/api.ts` (modified, API client / request-response)

**Analog:** 模块内 poolHub (2071-2079) + PoolHubRow/Strategy/Response 类型 (683-709) + auctionProbe (2181)。

**新端点拼参形（复制 poolHub:2071-2079 的 URLSearchParams + request<T> 封装 — Phase 23 加 poolDates/poolHistory）:**
```tsx
poolHub: (asOf?: string, concept?: string) => {
  const params = new URLSearchParams()
  if (asOf) params.set('as_of', asOf)
  if (concept) params.set('concept', concept)
  const qs = params.toString()
  return request<PoolHubResponse>(`/api/pool/hub${qs ? `?${qs}` : ''}`)
},
// Phase 23 新增:
poolDates: () => request<{ dates: string[]; count: number; latest: string | null }>('/api/pool/dates'),
poolHistory: (asOf: string) => request<PoolHistoryResponse>(`/api/pool/history?as_of=${asOf}`),
```

**类型扩展（改 :683-709 — 对齐服务端投影 8 键 → 12+ 键）:**
```tsx
export interface PoolHubRow {
  symbol: string; code: string; name: string
  open_gap: number | null
  change_pct: number | null
  concept_board: string[]; hit_factors: string[]; cross_resonance: boolean
  // Phase 23 (OQ-2 透传, _safe_num 消毒后可选): 
  auction_volume?: number | null          // 竞价量 股 (仅 probe available 日存在)
  auction_amount?: number | null          // 竞价金额 元
  auction_volume_ratio?: number | null    // 竞价量比 (派生)
  auction_unmatched_amount?: number | null // 虚拟未匹配金额 元·估算 (派生)
}
export interface PoolHubResponse {
  as_of: string | null
  updated_at: number | string | null      // PIT-8: hub=epoch ms / history=ISO 串
  mode: 'guest' | 'vip'
  strategies: PoolHubStrategy[]
  resonance_count: number
  available?: boolean                     // PIT-8: 现类型缺此键, history 空态才返回
  auction_columns?: { real: string[]; derived: string[] }  // OQ-2 服务端声明
}
```
> `PoolHistoryResponse = PoolHubResponse`（与 /hub 同形状，pool_hub.py:185-220）；缺失日 `available:false` 200 空态。

---

### 5. `frontend/src/lib/queryKeys.ts` (modified, config / —)

**Analog:** 模块内 QK.poolHub (41) + limitLadder (40) — key 工厂 + 日期维度参数化先例；SSE_INVALIDATE_PREFIXES (211-223) — pool-hub 不在列表。

**新增 key（复制 queryKeys.ts:40-41 的 key 工厂形 — 一行一条，日期带进 key）:**
```ts
// queryKeys.ts:40-41
limitLadder: (asOf?: string) => ['limit-ladder', asOf] as const,
poolHub:   (asOf?: string) => ['pool-hub', asOf ?? 'latest'] as const,
// Phase 23 新增:
poolDates:   ['pool-dates'] as const,
poolHistory: (asOf: string) => ['pool-history', asOf] as const,
```

**Deltas:**
- **不加入 `SSE_INVALIDATE_PREFIXES`（:211-223）**: 股池按日静态，不需要行情 tick 刷新；`pool-hub` 现不在列表即先例（RQ2 VERIFIED）。
- `QK.poolHistory(d)` 带日期 → 历史日各自缓存互不覆盖；`QK.poolHub()` 保持最新视图缓存（Pattern 2 的 key 驱动语义）。

---

### 6. `frontend/e2e/pool-hub.spec.ts` (modified, test / transform)

**Analog:** 模块内 installShell 全 mock 夹具 (144-173) + hubPayload (23-44) + 逐用例 route 覆盖 (179 起) + desktop-only 门禁 (177)。

**installShell 扩展（复制 :144-173 形 — 新增 /api/pool/dates + /api/pool/history 路由）:**
```ts
async function installShell(page: Page) {
  await page.route('**/api/**', unhandled)                     // :145 — 未覆盖请求大声失败
  ...
  await page.route('**/api/pool/dates**', route => json(route, datesPayload))       // Phase 23
  await page.route('**/api/pool/history**', route => json(route, historyPayload))   // Phase 23
}
```

**载荷形状（复制 :23-44 hubPayload 形 — 扩展 auction 列 + available 变体）:**
```ts
const hubPayload = {
  as_of: HUB_AS_OF, updated_at: HUB_UPDATED_AT, mode: 'vip',
  strategies: [ /* rows: 加 auction_volume/auction_amount/auction_volume_ratio/auction_unmatched_amount */ ],
  resonance_count: 1,
  auction_columns: { real: ['auction_volume', 'auction_amount'], derived: ['auction_volume_ratio', 'auction_unmatched_amount', 'open_gap'] },
}
const missingSnapshotPayload = { as_of: null, available: false, strategies: [], resonance_count: 0, updated_at: null, concept_attribution: 'current_snapshot' }
```

**Deltas（Phase 23 新增用例，沿既有逐用例 route 形）:**
- DateNavigator 步进/下拉/最新复位（断言步进后 `as_of` 变化 + 请求路径切到 `/api/pool/history`——**PIT-1 守卫**）。
- `available:false` 空态用例（断言「该日期无股池快照」文案，**PIT-2 守卫**）。
- 竞价列分组渲染 + 单位用例（真实组 vs 派生组表头 + 单元格 `×`/单位，**PIT-4 守卫**）。
- probe/盘前状态徽标用例（mock `/api/data/auction-probe` 四态 + `/api/intraday/status` `is_trading_hours:false`）。
- guest 无竞价列守卫（mock `mode:'guest'` 载荷 → 断言无 `auction_*` 列/无 `开盘涨幅`）。

---

### 7. `backend/app/services/pool_hub.py` (modified, service / request-response)

**Analog:** 模块内 `_project_hub` 投影循环 (78-130, projected dict 116-125) + `_safe_num` 消毒 (42-53)。**唯一跨层改动（OQ-2）。**

**投影循环透传（改 :116-125 — 8 键 → 12 键，竞价列 `_safe_num` 消毒后加入）:**
```python
projected = {
    "symbol": symbol,
    "code": symbol.split(".", 1)[0],
    "name": str(row.get("name") or ""),
    "open_gap": _safe_num(row.get("open_gap")),
    "change_pct": _safe_num(row.get("change_pct")),
    "concept_board": concept_map.get(symbol.upper(), []),
    "hit_factors": hit_factors,
    "cross_resonance": cross_resonance,
}
# Phase 23 (OQ-2): 透传竞价列 — raw rows 已携带 (screener.py:638 to_dicts + :299-314 _attach_auction 注入)
for col in ("auction_volume", "auction_amount", "auction_volume_ratio", "auction_unmatched_amount"):
    projected[col] = _safe_num(row.get(col))
```
> **诚实缺列语义**: raw row 无该列 → `row.get(col)` 返回 None → `_safe_num(None) → None`（pool_hub.py:44-45），投影行该键为 null（列存在性由 `auction_columns` 声明字段区分，见下）。

**JSON 消毒（复制 pool_hub.py:42-53 — NaN/Inf → None，镜像 screener._safe 语义）:**
```python
def _safe_num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return float(value)
    return value
```

**服务端列存在性声明（Deltas — 在 `_project_hub` 返回 dict 追加，见 :133-140 返回形）:**
```python
return {
    "as_of": str(resolved_as_of),
    "updated_at": updated_at,
    "strategies": strategies,
    "resonance_count": len(resonance_symbols),
    "concept_attribution": "current_snapshot",
    # Phase 23 (OQ-2): 列存在性由投影时快照/缓存的行级键存在性决定
    #   real 只在该快照 probe available 时非空 (attach_auction_columns 双闸门, auction_columns.py:100-131)
    "auction_columns": {
        "real": [c for c in ("auction_volume", "auction_amount") if any(c in r for r in rows)],
        "derived": ["auction_volume_ratio", "auction_unmatched_amount", "open_gap"],
    },
}
```
> **PIT-3 防线**: null 行值无法区分「列缺席」与「该标的缺席」——`auction_columns.real` 空数组 = 该快照整组无真实竞价列（前端整组不渲染），行级 null 只表示该标的缺席。对齐 GUEST-01「只消费 server mode，绝不从行值推导」哲学（PoolHubPage.tsx:37-39）。
> **PIT-6 铁律**: 只扩展 `_project_hub` 透传字段，**绝不改** `build_pool_hub` 的反漂移 `resolved_as_of`（:170-174）——`/hub` 单 as_of 契约 + 17 回归零改动。

---

### 8. `backend/tests/test_pool_hub.py` (modified, test / transform)

**Analog:** 模块内 expected_keys 锁死 (246-253)。

**expected_keys 扩展（改 :246-253 — 8 → 12 键 + 透传/诚实缺列断言）:**
```python
expected_keys = {
    "symbol", "code", "name", "open_gap", "change_pct",
    "concept_board", "hit_factors", "cross_resonance",
    # Phase 23 (OQ-2): + auction_volume/auction_amount/auction_volume_ratio/auction_unmatched_amount
    "auction_volume", "auction_amount", "auction_volume_ratio", "auction_unmatched_amount",
}
for strategy in strategies.values():
    for row in strategy["rows"]:
        assert set(row) == expected_keys
```

**Deltas:**
- 新增 fixture 行带竞价列 → 断言透传值等于原始（round-trip，`_safe_num` 消毒后）。
- 新增缺列 fixture（raw row 无竞价列）→ 断言投影行为 `None` + `auction_columns.real` 为 `[]`（诚实缺列，非 0 填充）。
- `auction_columns` 声明字段断言：real/derived 分组与投影键一致（PIT-3 防线）。
- **PIT-6 守卫**: 现有反漂移/空缓存早退测试（L87-90 / 442-447）**不得改动**——追加 `auction_columns` 键后先跑全量确认按 key 断言的测试不受影响（Divergence 2 同型）。

---

### 9. `backend/tests/test_guest_masking.py` (modified, test / transform)

**Analog:** `guest_masking.py` `_GUEST_VISIBLE` 白名单 (18-24) + mask_guest_hub (31-43)。

**白名单自动丢弃（读 guest_masking.py:18-24 — 竞价列/open_gap 不在白名单 → 游客响应自动无竞价列）:**
```python
_GUEST_VISIBLE = frozenset({"change_pct", "concept_board", "hit_factors", "cross_resonance"})
```
> Phase 23 透传竞价列后，`mask_guest_hub`（:31-43）按白名单重建 masked_row——`auction_*`/`open_gap` 键**自动丢弃**（不在白名单）。**不需要改白名单**（PIT-7）。

**Deltas（新增守卫测试，沿 test_guest_masking.py:405-427 白名单测试形）:**
- 新增 `test_guest_hub_rows_have_no_auction_columns`: 游客响应每个策略行断言 `set(row) <= _GUEST_VISIBLE ∪ {code,name,symbol}`（即无 `auction_*`/`open_gap` 键）。
- 断言顶层 `auction_columns` 键在 guest 响应中被剥除（或前端不渲染——服务端声明字段也应随掩码移除，防止 UI 按声明渲染空组）。

---

## Shared Patterns

### 1. queryKey 切换驱动 as_of 重取（不手动 refetch）
**Source:** `LimitUpLadder.tsx:1474-1476`（`queryKey: [QK.limitLadder(asOf || undefined), ...]`）+ `Dashboard.tsx:507-510`（`placeholderData: (prev) => prev`）+ `Indices.tsx:131-135`（selectedDate 进 key + placeholderData）
**Apply to:** `PoolHubPage.poolQuery`（selectedDate 切 `QK.poolHistory(d)`/`QK.poolHub()`）+ `DateNavigator` 步进
```tsx
const poolQuery = useQuery({
  queryKey: selectedDate ? QK.poolHistory(selectedDate) : QK.poolHub(),
  queryFn: () => selectedDate ? api.poolHistory(selectedDate) : api.poolHub(),
  placeholderData: (prev) => prev,
})
```
> 手动 `refetch()` 无法区分「同 key 刷新」与「换 key 换数据」；key 驱动自动获得 per-date 缓存 + 回退切换（Pattern 2）。

### 2. 服务端 mode 声明（GUEST-01）
**Source:** `PoolHubPage.tsx:36-39` + `api/pool.py:87-90, 115-117`（`mode` 由 reviewer_principal 决定）+ `guest_masking.py:18-24`（`_GUEST_VISIBLE` 白名单）
**Apply to:** `StockListTable` 列选择（`columns = mode === 'guest' ? GUEST_COLUMNS : VIP_COLUMNS`，:99）+ 竞价列分组渲染
```tsx
const mode = data?.mode === 'guest' ? 'guest' : 'vip'
```
> 前端只消费服务端声明，绝不从行值推导——竞价列存在性同理（`auction_columns` 声明字段是同一哲学的应用）。

### 3. 诚实空态分流（无快照日 ≠ 零池日）
**Source:** 服务端形状 `pool_hub.py:204-212`（`available:false` 200 空态）+ 前端零池 `PoolHubPage.tsx:125-132`
**Apply to:** `PoolHubPage` 渲染序（`available === false` 分支短路于零池分支之前）+ `e2e/pool-hub.spec.ts` 文案断言
```tsx
{data && data.available === false && <EmptyState icon={CalendarX} title="该日期无股池快照" ... />}
{data && data.strategies.length === 0 && <EmptyState icon={ScanSearch} title="当日无股池结果" ... />}
```
> PIT-2: `available:false` 是「无快照」，`strategies.length===0` 是「零池」——文案必须区分，否则成功标准 2 违规。

### 4. 数值单元格规范 + 单位承载
**Source:** `StockListTable.tsx:70-77`（PctCell 空值 `—`）+ `format.ts:44-52`（fmtBigNum 万/亿）+ `LimitUpLadder.tsx:125-135`（fmtSealVol/fmtSealAmount 大数转万/亿）
**Apply to:** 竞价量/金额列（表头带单位 股/元，单元格 fmtBigNum）+ 竞价量比列（`toFixed(2) + '×'`）
```tsx
// OQ-7: 表头承载单位; 单元格数值用既有 fmtBigNum — 无需新 fmtShares
<td className={cn('num tabular-nums', 'px-3 py-2')}>{fmtBigNum(row.auction_amount)}</td>
```

### 5. 诚实状态徽标词汇（probe/盘前）
**Source:** `AuctionProbeCard.tsx:5-13`（四态词汇 not_configured/available/fail_closed/error + 诚实规则「绝不把 09:30 连续竞价 bar 标为集合竞价」）+ `useSharedQueries.ts:42-54, 58-63`（useQuoteStatus.is_trading_hours / useAuctionProbe 30s stale）
**Apply to:** `StockListTable` 表头上方状态徽标（probe 非 available → warning「竞价数据未接入，仅展示派生列」；盘前 → status「竞价窗口 09:15-09:25 未开始」）
```ts
// useSharedQueries.ts:58-63 — 30s stale 与服务端 30s TTL 对齐
export function useAuctionProbe() {
  return useQuery({ queryKey: QK.auctionProbe, queryFn: api.auctionProbe, staleTime: 30_000 })
}
```
> Pattern 4: 冻结列存在性（`auction_columns` 声明，回答「这张快照有没有真实竞价列」）与实时 probe/时段（回答「当前数据源/时段状态」）**不混用**——历史快照不因今日 probe 状态被重写。

### 6. `_safe_num` JSON 消毒（后端透传）
**Source:** `pool_hub.py:42-53`
**Apply to:** `_project_hub` 透传 4 竞价列（NaN/Inf → None，诚实缺列）
```python
def _safe_num(value: Any) -> float | None:  # NaN/Inf → None (镜像 screener._safe)
```

## No Analog Found (Gaps)

| File / Feature | Role | Data Flow | Reason / Fallback |
|----------------|------|-----------|-------------------|
| 白名单式 ‹ › 步进 + 日期下拉（DateNavigator 核心） | component 子功能 | request-response | `DatePicker.tsx:47-56` 的 disabled 只按 min/max 计算，**无法表达白名单日期集**；无任何「只在可用日期间步进」先例。**Fallback:** 23-RESEARCH.md RQ3 设计（`idx = dates.indexOf(currentAsOf)` + 边界禁用 + 原生 select 只列 dates；无「跳到最近日」分支） |
| 真实/派生两组表头渲染 | component 子功能 | CRUD render | `SCREENER_COLUMN_GROUPS`（screener-columns.ts:87-98）/ `COLUMN_GROUPS`（watchlist-columns.ts:88-98）是**列自定义器分组模型**（id/label/icon/keys），非渲染表头分组；仓库无任何表格渲染双组表头先例。**Fallback:** 23-RESEARCH.md OQ-5（两组 `<colgroup>`/表头行 + 列头单位 + 派生组「估算/虚拟」标注） |
| `auction_columns` 服务端列存在性声明字段 | service 子功能 | request-response | 无既有「服务端声明列存在性」字段（null 值无法区分「列缺席」与「该标的缺席」）；`mode` 声明（GUEST-01）是最接近哲学先例。**Fallback:** 23-RESEARCH.md OQ-2（投影时由行级键存在性决定 real/derived） |
| `available:false` 前端独立空态分流 | page 子功能 | request-response | 服务端形状已交付（pool_hub.py:204-212），但前端 `PoolHubResponse`（api.ts:701-709）无 `available` 键、无消费先例。**Fallback:** 23-RESEARCH.md RQ3（`available === false` → 独立 EmptyState「该日期无股池快照」，短路于零池分支之前，PIT-2） |

> 其余 9 个文件均有 exact/role-match analog（含 4 处 in-file 精确镜像）；上述 4 项是**子功能级缺口**，非整文件无类比 — planner 需以 23-RESEARCH.md（RQ3/RQ4/OQ-2/OQ-5/OQ-7 + PIT-1..8 + Security Domain）作为兜底实现依据。

## Divergences (Phase 23 特有差异, planner 须注意)

1. **`updated_at` 类型双源不一致（PIT-8）:** `/api/pool/hub` 回 epoch ms（strategy_cache.py:166 `int(time.time()*1000)`），`/api/pool/history` 回 ISO 串（`snap["computed_at"]`，pool_hub.py:216）。前端 `PoolHubResponse.updated_at` 类型必须改 `number | string | null`；本期不展示 updated_at 则不阻塞，但类型不扩 tsc 会报错。
2. **`available` / `auction_columns` 键追加对既有测试的影响:** `build_pool_hub` 空缓存早退（pool_hub.py:87-90）不经过 `_project_hub`，精确 dict 相等测试（test_pool_hub.py:442-447）安全；populated hub 各测试按 key 断言——追加 `auction_columns` 顶层键安全，但**执行时先跑 test_pool_hub.py 全量确认**（Divergence 2 同型，Phase 22 已验证该模式）。
3. **真实/派生列透传只发生在 VIP 侧:** `mask_guest_hub`（guest_masking.py:31-43）按 `_GUEST_VISIBLE` 白名单重建行 dict，`auction_*`/`open_gap` 键自动剥除（PIT-7 自动安全）。新增守卫测试锁死，**绝不**把竞价列加入白名单。
4. **零新增 npm 依赖:** lucide 的 `ChevronLeft/ChevronRight/Calendar/Info` 已在 `frontend/package.json`（DatePicker.tsx:2 同款 import）；DateNavigator 不引入任何新包。
5. **历史必走 `/api/pool/history`（PIT-1 最高危）:** `api.poolHub(asOf)` 底层是 `/api/pool/hub`，反漂移回显缓存日期（pool_hub.py:170-174）——拿历史会静默返回最新日。`QK.poolHistory` 与 `QK.poolHub` 必须分离，e2e 断言步进后请求路径切到 `/api/pool/history`。

## Metadata

**Analog search scope:** `frontend/src/`（pages/PoolHubPage.tsx, LimitUpLadder.tsx, Dashboard.tsx, Indices.tsx；components/pool-hub/StockListTable.tsx, StrategyCardGrid.tsx, GuestModeBanner.tsx；components/DatePicker.tsx, EmptyState.tsx, WarmupBadge.tsx, SealedBadge.tsx, data/AuctionProbeCard.tsx；lib/api.ts, queryKeys.ts, useSharedQueries.ts, format.ts, screener-columns.ts, watchlist-columns.ts, list-columns.ts）、`frontend/e2e/pool-hub.spec.ts`、`backend/app/services/`（pool_hub.py, auction_columns.py, guest_masking.py, screener.py）、`backend/app/api/pool.py`、`backend/tests/`（test_pool_hub.py, test_guest_masking.py）、`data/`（kline_auction hive 分区经 auction_columns.py:121 确认）
**Files scanned:** 24（PoolHubPage, LimitUpLadder, Dashboard, Indices, StockListTable, StrategyCardGrid, GuestModeBanner, DatePicker, EmptyState, WarmupBadge, SealedBadge, AuctionProbeCard, api, queryKeys, useSharedQueries, format, screener-columns, watchlist-columns, list-columns, pool-hub.spec, pool_hub.py, auction_columns.py, guest_masking.py, screener.py, api/pool.py, test_pool_hub.py）
**Pattern extraction date:** 2026-08-05
**Line numbers verified against live code:** 全部 excerpt 行号在本 session 逐行读取确认（LimitUpLadder asOf L1391/queryKey L1474-1476/fmtSeal L125-135、Dashboard L499/507/510、Indices L75/131-135、DatePicker min/max L47-56 + Chevron L143-147、queryKeys poolHub L41/SSE L211-223、api poolHub L2071-2079 + PoolHub 类型 L683-709 + auctionProbe L2181、useSharedQueries useAuctionProbe L58-63、EmptyState L10-23、StockListTable GUEST/VIP L17-18 + PctCell L70-77 + 行渲染 L144-229、screener-columns groups L87-98、watchlist-columns groups L88-98、pool_hub.py _project_hub L78-130/projected L116-125/_safe_num L42-53/build_pool_hub_snapshot L185-220、api/pool.py /dates L55-65 + /history L67-102、auction_columns.py _AUCTION_REAL_COLS L31-32 + attach L100-131、guest_masking.py _GUEST_VISIBLE L18-24、screener.py _attach_auction L299-314 + to_dicts L638 + run_all_with_hits L723、test_pool_hub.py expected_keys L246-253、pool-hub.spec.ts installShell L144-173 + hubPayload L23-44）。
