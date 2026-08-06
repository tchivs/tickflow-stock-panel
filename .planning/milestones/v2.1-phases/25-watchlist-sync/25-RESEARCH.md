# Phase 25 研究：自选股联动（WATCH-01..04）

**Researched:** 2026-08-06
**Domain:** 前端股池钻取 × 自选清单（react-query 缓存 join）
**Confidence:** HIGH（全部结论基于本会话实读代码 file:line；仅跨页运行时一致性等推断标 [INFERENCE]）

## 摘要

Phase 25 是在**纯前端**为股池钻取明细表（`StockListTable`）接入既有的服务端自选体系：VIP 模式下每行渲染自选星标、提供「只看自选」过滤开关、复用共享 `QK.watchlist` 缓存保证跨页一致，并可（P2）批量加入可见行。**零后端改动、零 POOL-03 守卫改动、零 guest 掩码改动、零新增 npm 依赖**——因为服务端 `is_watched` 投影被 `test_pool_hub.py` 的 `_EXECUTION_TOKEN`（含 `watchlist`）锁死，而纯前端 join 完全避开两条锁死测试边界。

**Primary recommendation:** 复用 `frontend/src/pages/Screener.tsx:429-447` 的完整先例（`useQuery(QK.watchlist)` → `Set.has(row.symbol)` → mutation 增删 → `invalidateQueries(QK.watchlist)`），在 `PoolHubPage` 持有自选集合与 toggle mutation，经新 props 下发给 `StockListTable` 渲染星标；「只看自选」是 `PoolHubPage.filteredRows` 的第二个前端投影条件（与既有概念筛选同层，`total` 权威不变）。关键陷阱：`enabled` 必须 `!!data && mode === 'vip'` 双门控，否则 guest 首次加载会因 mode 回退 vip 触发 `/api/watchlist` 查询 → 401 → 跳登录，破坏 guest 面。

<phase_requirements>
## Phase Requirements

| ID | 描述 | Research Support |
|----|------|------------------|
| WATCH-01 | 股池钻取行自选星标+切换（VIP；guest 逐像素不变，零 watchlist 查询） | D1/D4 + 现状 §1/§4；先例 `ScreenerTable.tsx:166-210`；门控 `enabled: !!data && mode==='vip'` |
| WATCH-02 | 「只看自选」过滤开关（VIP；total 权威不变，最新+历史同构，空态诚实） | D2/D5 + `PoolHubPage.tsx:43-51` filteredRows 扩展；`StockListTable.tsx:400-413` footer total 权威 |
| WATCH-03 | 自选集合一致性（共享 QK.watchlist 缓存；匹配键=全后缀 symbol 精确） | D3 + `queryKeys.ts:25`；`pool_hub.py:132-138` row.symbol 全后缀；`watchlist.py` parquet 同格式 |
| WATCH-04（P2） | 批量加可见行（display_limit 范围），复用 batch-add 端点 | D6 + `useSharedMutations.ts:32-41`；`screener.py:614-621/778-798` display_limit 截断语义；`pool_hub.py:117-118` rows ≤ total |

</phase_requirements>

## 现状（代码证据，file:line）

### 1. 自选能力已完整存在，服务端是唯一事实来源

- **存储 = Parquet**：`backend/app/services/watchlist.py:21-24` — `_path()` 指向 `settings.data_dir / "user_data" / "watchlist.parquet"`。`list_symbols()`（`:26-32`）读全表；`add()`（`:37-52`）**幂等去重**（`# 已存在则先移除，后面重新插入到最前面`，`if symbol in df["symbol"].to_list()` 后 filter 掉再插头部）；`remove()`（`:54-60`）；`move_to_top()`（`:62-75`）；`clear()`（`:77-86`）。
- **API 全 CRUD**：`backend/app/api/watchlist.py` — `GET ""` list_all（`:24-27`）、`POST ""` add_one（`:29-33`）、`POST "/batch"` add_batch（`:35-40`，**逐 symbol 调 `watchlist.add`**）、`POST "/{symbol}/top"`（`:42-47`）、`DELETE "/{symbol}"`（`:49-53`）、`DELETE ""` clear_all（`:55-58`）、`GET "/enriched"`（`:104+`）。路由注册 `backend/app/main.py:847`。
- **前端 API 客户端**：`frontend/src/lib/api.ts:2025-2051` — `watchlistList: () => request<{ symbols: WatchlistEntry[] }>('/api/watchlist')`、`watchlistAdd(symbol, note='')`、`watchlistBatchAdd(symbols: string[], note='') => request<{symbols; added:number}>('/api/watchlist/batch', POST)`、`watchlistRemove(symbol)`、`watchlistMoveToTop`、`watchlistClear`、`watchlistQuotes`、`watchlistEnriched`。`WatchlistEntry { symbol; added_at; note?; name? }`（`:602-605`）。
- **查询键**：`frontend/src/lib/queryKeys.ts:25-28` — `watchlist: ['watchlist']`、`watchlistQuotes`、`watchlistEnriched: (ext?) => ['watchlist-enriched', ext]`、`watchlistKlineBatch`。**`SSE_INVALIDATE_PREFIXES` 含 `'watchlist'`**（`:215-216`）→ 行情 tick 会按前缀失效 `QK.watchlist`（见风险 R4）。
- **localStorage 只存 UI 偏好**：`frontend/src/lib/storage.ts:28-44` — `watchlistColumns/watchlistView/watchlistCandle/watchlistIntraday/watchlistBoardFilter` 全是视图偏好，非 symbol 清单。`kv<T>(key)` 形状（`:8-23`）：`get(fallback)`/`set(val)`，JSON 序列化 + try/catch。

### 2. 服务端已把自选当一级池消费（不能引入第二套自选清单的根本原因）

- `backend/app/tickflow/pools.py:22` — `PoolId = Literal["CSI300", "CSI500", "SSE50", "CN_Equity_A", "CN_Index", "watchlist"]`；`:55-58` `get_pool(pool_id)` 对 `"watchlist"` 走 `_load_watchlist()`（`:135-140` 直读同一份 `watchlist.parquet`）。
- `backend/app/jobs/daily_pipeline.py:154-156` — Free 用户拉数兜底 `base.update(get_pool("watchlist"))`。
- 结论：自选清单被 实时监控（quote_service）/ 池（pools.py）/ 盘后管道（daily_pipeline）/ extend_history 多处服务端消费 → **localStorage 第二清单必然与服务端漂移**。

### 3. 匹配键 = 全后缀 symbol（两端已一致，直接精确 join）

- `backend/app/services/pool_hub.py:132-138` — `_project_hub` 行投影：`symbol = str(row["symbol"])`（全后缀，直接取自结果行）、`code = symbol.split(".", 1)[0]`、`name`、`open_gap`、`change_pct`、`concept_board`（`concept_map.get(symbol.upper(), [])`）、`hit_factors`、`cross_resonance`，竞价四列透传。
- 自选 parquet 的 symbol 亦为全后缀（领域研究实测 `600664.SH`/`001258.SZ`；`watchlist.add` 原样存 symbol `watchlist.py:37-52`）。
- → 前端 `new Set(symbols.map(s => s.symbol))` + `watchlistSet.has(row.symbol)` 即为精确 join，无归一化。

### 4. guest / auth 语义（联动是 VIP 专属，且 guest 面被测试锁死）

- `backend/app/main.py:778-790` — `_GUEST_READ_GET_PATHS = frozenset({"/api/pool/hub","/api/screener/strategies","/api/pool/dates","/api/pool/history"})`，恰 4 个只读 GET；`:802-812` 游客分支放行这 4 个，其余 `/api/*` 一律 `401 {"detail":"未登录或会话已过期"}`。**`/api/watchlist` 不在白名单 → guest 访问必 401**。
- `backend/app/services/guest_masking.py:24` — `MASKED_IDENTITY = "******"`；`:27-29` `_GUEST_VISIBLE = {"change_pct","concept_board","hit_factors","cross_resonance"}`；`:31-56` `mask_guest_hub` 把每行 code/name/symbol 替换为 `******`、省略 `open_gap`、`pop("auction_columns")`。
- `backend/app/api/pool.py:42-47`（hub）与 `:97-102`（history）— `is_vip = getattr(request.state, "reviewer_principal", None) is not None`，`hub["mode"] = "vip" if is_vip else "guest"`，guest → `mask_guest_hub(hub)`。**mode 由服务端声明，前端只消费不推导**。
- `frontend/src/main.tsx:22-27` — QueryCache/MutationCache `onError` 对 401/`未登录`/`会话已过期` → `window.location.href = '/login?...'`。**因此股池页 guest 模式绝不能发起 `QK.watchlist` 查询**（否则整页跳登录）。
- 守卫：`backend/tests/test_guest_masking.py:507-529` — T-19-03 `test_guest_cannot_read_authed_surfaces`（游客读 4 白名单外 `/api/` 全部 401）+ `test_guest_read_paths_are_get_only`。

### 5. POOL-03 AST 守卫锁死服务端 `is_watched` 投影

- `backend/tests/test_pool_hub.py:857-861` — `_EXECUTION_TOKEN = re.compile(r"broker|order|execution|trade|portfolio|watchlist|position|account|transaction|下单|委托", re.IGNORECASE)`。
- `:895-902` `test_pool_hub_no_execution_imports` — `pool_hub.py / pool.py / pool_snapshot.py` 的 import 模块名不得匹配该 token → **`import watchlist` 直接红**。
- → 服务端在 hub 投影里标注 `is_watched`（方案 b）必然要 pool 特性读自选 → 触碰守卫。**纯前端 join（方案 c）是唯一不碰守卫的路径**。`guest_masking.py` 自身也被 `_GUEST_BANNED_IMPORT` 禁 watchlist（`test_guest_masking.py:453-492`）。

### 6. 前端已存在完全相同的联动先例（策略页 / 个股弹窗）

- `frontend/src/pages/Screener.tsx:429-447`：
  ```tsx
  const watchlist = useQuery({ queryKey: QK.watchlist, queryFn: api.watchlistList })
  const watchlistSet = useMemo(() => new Set((watchlist.data?.symbols ?? []).map((s: any) => s.symbol)), [watchlist.data])
  const toggleWatchlist = useMutation({
    mutationFn: ({ symbol, inList }) => inList ? api.watchlistRemove(symbol) : api.watchlistAdd(symbol),
    onSuccess: () => { qc.invalidateQueries({ queryKey: QK.watchlist }); qc.invalidateQueries({ queryKey: QK.watchlistEnriched() }) },
  })
  ```
- `frontend/src/components/screener/ScreenerTable.tsx:166-210` — symbol 列内星标按钮：在自选 `Check` 实心（`border-accent/40 bg-accent/10 text-accent`）、不在 `Plus` 空心；`disabled={watchlistPending}`；`title={inWatchlist ? '移出自选' : '加入自选'}`。
- `frontend/src/lib/useSharedMutations.ts:32-41` — `useWatchlistBatchAdd()`：`mutationFn: (symbols) => api.watchlistBatchAdd(symbols)`，onSuccess 失效 `QK.watchlist` + `QK.watchlistEnriched()`。
- `frontend/src/components/StockPreviewDialog.tsx:47-60` — 同款 query + toggle（`inWatchlist = (watchlist.data?.symbols ?? []).some(s => s.symbol === symbol)`）。
- `frontend/src/pages/Screener.tsx:498-513` — `handleBatchAdd` 用 `displayRows.map(r => r.symbol)` 调 `batchAdd.mutate`，成功 toast `已添加 ${data.added} 只到自选`；`:735-745` 批量按钮（`Star` 图标 + `disabled={batchAdd.isPending}`，文案 `批量加自选`/`添加中…`）。
- **`Star` 图标 in-tree**：lucide-react `^0.439.0`（`frontend/package.json` deps），已用于 `Screener.tsx:5`、`Layout.tsx:26`、`StockInfoBar.tsx:2/225`、`Watchlist.tsx:5`、`StrategySettingsDialog.tsx:3`。`StockInfoBar.tsx:224-226` 给出条件着色先例：在自选 `text-[#FACC15]`（黄）、不在 `text-muted hover:text-foreground`。

### 7. 股池钻取组件现状

- `frontend/src/pages/PoolHubPage.tsx`：
  - `:26-31` — `poolQuery` key 按 `selectedDate` 切换：`selectedDate ? QK.poolHistory(selectedDate) : QK.poolHub()`；`placeholderData: (prev) => prev` 防切换闪空。
  - `:34` — `const mode = data?.mode === 'guest' ? 'guest' : 'vip'`（**data 未加载时回退 vip**）。
  - `:36-38` — `activeStrategy = data?.strategies.find(s => s.id === activeId) ?? data?.strategies[0] ?? null`。
  - `:43-51` — `filteredRows = activeStrategy.rows.filter(r => r.concept_board.some(c => c.toLowerCase().includes(q)))`（概念子串，纯前端投影，D-04 同层）。
  - `:120-135` — `<StockListTable mode={mode} strategy={activeStrategy} rows={filteredRows} filterText={filterText} total={activeStrategy.total} … />`。**目前无任何 watchlist 相关代码**。
- `frontend/src/components/pool-hub/StockListTable.tsx`：
  - `:15-16` — `GUEST_COLUMNS = ['代码','名称','涨跌幅','概念板块','关联因子']`；`VIP_COLUMNS = ['代码','名称','开盘涨幅','涨跌幅','概念板块','关联因子']`。
  - `:18-46` — props：`strategy / mode: 'guest'|'vip' / rows / filterText / total / loading / error / onRetry / onClearFilter / resonanceCount / auctionColumns`。
  - `:178-205` — 两个空态：概念筛选无匹配（`无符合「{filterText}」的个股` + 清除筛选）；策略当日无命中（`该策略当日无命中个股`）。
  - `:214-242` — 代码/名称单元格：**guest 分支** `:228-242` 渲染 `row.code`/`row.name`（`******` 原样，mono muted，无板块标识）；**VIP 分支** `:214-227` 渲染板块标识（`boardTag` 18px）+ `row.code`。`rowKey`：guest = `${strategy.id}-${index}`，vip = `row.symbol`（`:199-203`，T-19-10 duplicate-key 防御）。
  - `:400-413` — footer：`filterActive ? <>筛选后 {rows.length} 只 / 共 {total} 只</> : <>共 {total} 只</>`。**`total` 即权威，筛选不改变它**。
- `frontend/src/components/pool-hub/ConceptFilter.tsx` — 纯客户端筛选先例（`输入绝不触发第二次 fetch`）；`PoolHubPage` 已有 `filterText` state 驱动。
- `frontend/src/components/pool-hub/GuestModeBanner.tsx` — `BANNER_TITLE`/`BANNER_BODY`/`GUEST_BANNER_ACCESSIBLE_TEXT` 为锁定 exported 常量（UI-SPEC Copywriting Contract），本期不动。

### 8. display_limit 语义（WATCH-04 批量范围的事实基础）

- `backend/app/services/screener.py:614-621` — `display_limit: None=不限制, 0=全部, N=前N个`，`limit is not None and limit > 0` → `df.head(limit)`；`:650-651` `total=len(rows)`。
- `backend/app/services/screener.py:778-798`（`run_all_with_hits`）— PRESET 走 `run_preset(..., display_limit=dl)`；非 PRESET `r.rows = r.rows[:dl]; r.total = min(r.total, dl)`。
- `backend/app/services/pool_hub.py:117-118` — 投影时 `total = result.get("total", len(rows))`（Divergence 1 修正，**快照/缓存显式存 total，`len(rows) ≤ total`**）。
- 前端策略设置 `frontend/src/components/screener/StrategySettingsDialog.tsx:390` — display_limit 输入 `min=10 max=200`。
- → 股池 `activeStrategy.rows` 已是 display_limit 截断后的可见行；**WATCH-04 批量范围 = 当前可见行（`filteredRows`）**，绝不用未展开的 `total`。

### 9. e2e 现状（pool-hub.spec.ts）

- `frontend/e2e/pool-hub.spec.ts`（共 1081 行）— 全部 `test.skip(testInfo.project.name !== DESKTOP_PROJECT)`；`installShell`（`:250-330`）先 `page.route('**/api/**', unhandled)`（未覆盖的 /api 请求大声 500）再覆盖 settings/capabilities/preferences/pool/dates/pool/history/auction-probe 等。**目前无 `/api/watchlist` mock**。
- SC1-SC4 区域：SC1 历史步进（`:855`）、SC2/SC2b 日期白名单（`:902/:932`）、SC3/SC3b/SC3c 竞价列分组（`:949/:980/:1000`）、SC4a-d 竞价徽标（`:1020-1057`）。
- **新增 VIP 控件必碰的两条守卫测试**（规划时必须同步更新，见 Common Pitfall P1）：
  - `pool page renders zero execution affordances (POOL-03)`（`:591-641`）— `ALLOWED_RE = /刷新股池|当日池|当日无命中|数据不可用|清除筛选|清除概念筛选|重试|收起|\+\d+|上一个交易日|下一个交易日|最新/`（`:620-626`）遍历 `main` 内**所有按钮**并要求匹配 → 新增「只看自选」「批量加自选」及星标按钮的 aria-label 必须加进白名单，否则红。
  - `pool page never issues a mutating request (POOL-03)`（`:620-643`）— 交互只有 刷新/概念输入/卡片钻取，断言 `captured` 无非 GET 请求、无执行族路径。新增 `GET /api/watchlist`（VIP 自动查）是 GET，不触发；**不点击星标则无 mutation**。
  - 源码 grep 守卫：`pool page source contains no execution API call or form`（`:645-662`）对 `PoolHubPage.tsx/StrategyCardGrid/ConceptFilter/StockListTable` 禁 `<form`、`api.\w*(order|trade|execute|…)`、裸 `fetch(..., {method:'POST|PUT|DELETE|PATCH'})` — 用 `api.watchlistAdd` 包装不匹配；`frontend contains no client-side masking code`（`:776-798`）禁 `\*{6,}` 字面量、`code/symbol === '******'` 推导、`\bmask` 标识符 — 本期代码不得新增任何掩码字面量/标识符。
  - **视觉 backstop**：`captures visual evidence for the five UI-SPEC backstop scalars`（`:742-774`）对 VIP 载荷截 `pool-table-resonance.png` / `pool-table-filter-active.png` → **新增 VIP 星标会改变这两张快照，需 `--update-snapshots` 并人工复核**（guest 快照不受影响）。
- Playwright 配置：`frontend/playwright.config.ts` — `testDir: '.'`，`desktop-chromium` 项目跑全部；webServer 自动起 vite `4173`。**无 vitest**（`frontend/package.json` scripts 仅 dev/build/preview/lint；build = `tsc -b && vite build`）。

## 关键决策

### D1 星标 UI 形态

| 选项 | 说明 | 取舍 |
|---|---|---|
| a. lucide `Star` + 条件 fill（推荐） | 在自选=`fill="currentColor"` 实心 amber，不在=空心 muted；`aria-label/title = 移出自选/加入自选`；`disabled={watchlistPending}` | 语义贴合 WATCH-01「自选星标」；沿用 `StockInfoBar.tsx:224-226` 条件着色先例；`Star` 已在树内多处 import |
| b. `Check`/`Plus` 圆形按钮（ScreenerTable 同款） | 与策略页完全一致 | 非「星标」形态，与需求文案不符；但若追求页间一致性可选 |
| c. `Star`/`StarOff` 双图标 | lucide 双图标 | `StarOff` 未在仓库出现 [ASSUMED: lucide-react 存在该导出]；徒增一个图标，无收益 |

**推荐 a。** 渲染位置：`StockListTable.tsx` VIP 代码单元格（`:214-227` 的 `<div className="flex items-center gap-2">` 内、code 之后），**仅 `!isGuest` 分支渲染** → guest 分支逐像素不变。**风险**：星标按钮是 icon-only，必须给 aria-label 否则 e2e `ALLOWED_RE` 白名单遍历拿空 name 报错。

### D2 过滤层（「只看自选」在哪过滤）

| 选项 | 取舍 |
|---|---|
| a. 前端行过滤（推荐） | 与既有概念筛选同层（`PoolHubPage.tsx:43-51`）；`total` prop 保持 `activeStrategy.total` 权威（`StockListTable.tsx:400-413`）；零后端、零守卫 |
| b. 服务端过滤参数 | 需 pool 特性读自选 → **POOL-03 `_EXECUTION_TOKEN` 含 watchlist 锁死**（`test_pool_hub.py:857-902`）；或新增不在 pool 特性的 annotate 端点（本期不做） |

**推荐 a。** `filteredRows` 扩展为「概念子串 AND 只看自选」两个投影条件。**空态诚实**：`StockListTable` 需区分——只看自选开启且 `rows.length===0` → 独立文案「自选清单中无该策略个股」（非静默空白）；与概念筛选同时激活时的空态文案优先级见实现草案。`total` 权威不变（概念筛选已证明该模式，D-04）。**风险**：过滤依赖自选集合已加载（VIP 门控），加载前星标/开关禁用或空集。

### D3 QK 缓存复用（WATCH-03 一致性的实现机制）

**推荐**：`PoolHubPage` 直接 `useQuery({ queryKey: QK.watchlist, queryFn: api.watchlistList })`，与 Screener/个股弹窗/自选页共用同一全局缓存键；任一入口增删都 `invalidateQueries(QK.watchlist)` → 股池星标/过滤即时一致，**无需新同步机制**。**不新建任何独立自选键/存储**（WATCH-03 验收）。匹配键 = `row.symbol` 全等（`pool_hub.py:132-138` vs parquet 同格式）。**风险**：`SSE_INVALIDATE_PREFIXES` 含 `'watchlist'`（`queryKeys.ts:215-216`）→ 行情 tick 会失效 `QK.watchlist` 使股池页重取（本地小 parquet，开销可忽略，但 e2e 需 mock `/api/watchlist` 否则 unhandled 500）。

### D4 guest 门控（零 watchlist 查询、逐像素不变）

**关键陷阱**：`PoolHubPage.tsx:34` 的 mode 回退是 `data?.mode === 'guest' ? 'guest' : 'vip'` —— **data 未加载时 mode='vip'**。若 `enabled: mode === 'vip'`，guest 会话首次加载会在 mode 未知窗口发出 `/api/watchlist` → 401 → `main.tsx:22-27` 跳登录，**破坏 guest 面**。

**推荐**：`enabled: !!data && mode === 'vip'`（等 hub 载荷落地、确知服务端声明模式后才查；guest 全程零查询）。StockListTable 的星标/开关/批量按钮均以 `mode === 'vip'`（即现有 `isGuest` 分支之外）为渲染前提，guest 分支 `:228-242` 原样保留。**风险**：VIP 首次渲染星标晚于表格（hub + watchlist 双请求，可接受）；补一条 e2e 断言「guest 载荷下捕获不到 `/api/watchlist` 请求」。

### D5 历史视图一致性

`poolQuery` 按 `selectedDate` 切 key（`PoolHubPage.tsx:26-31`），历史 `/api/pool/history` 与最新 `/api/pool/hub` 行形状 bit-identical（`pool_hub.py` docstring / `pool.py:97-102`）；`watchlistSet` 是全局的（不分日期）→ 星标与「只看自选」对 latest/history **天然同构**，`filteredRows` 同一段代码即可。**语义**：星标/过滤 = 「当前自选清单」对任意 as_of 行的**实时标注**，非历史自选快照（领域研究明确：自选不是时间序列）。**风险**：无；无需按日期分键。

### D6 WATCH-04 批量范围

**推荐**：批量按钮仅 VIP；scope = 当前可见行 `filteredRows`（概念/只看自选过滤后的行，`rows ⊆ activeStrategy.rows`，而 `activeStrategy.rows` 已受 display_limit 截断，`pool_hub.py:117-118` `len(rows) ≤ total`）；复用 `useWatchlistBatchAdd`（`useSharedMutations.ts:32-41`）。重复添加幂等（`watchlist.py:37-52` 去重）。**与「只看自选」交互**：开关开启时可见行全在自选 → 隐藏批量按钮或显示禁用态「全部已在自选」（推荐隐藏，语义最诚实）。成功回调失效 `QK.watchlist` + `QK.watchlistEnriched()`；toast 复用 Screener 文案 `已添加 ${data.added} 只到自选`。**风险**：单次 body ≤ 200 symbol（display_limit 上限），后端 batch 端点逐 symbol `watchlist.add` 无上限校验，量级安全。

## 实现方案草案（文件级改动清单 + 顺序）

**零后端改动；零新增 npm 依赖。改动全在前端 + e2e。**

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

**改动清单（按实施顺序）：**

1. **`frontend/src/lib/storage.ts`** — 新增 `poolWatchlistOnly: kv<boolean>('pool-watchlist-only')`（与既有 UI 偏好键同型，`:8-23` 模式）。
2. **`frontend/src/pages/PoolHubPage.tsx`**：
   - import `useMutation`/`useQueryClient`（或 `useWatchlistBatchAdd`）、`storage`。
   - state：`const [watchlistOnly, setWatchlistOnly] = useState(() => storage.poolWatchlistOnly.get(false))`，onChange 时 `storage.poolWatchlistOnly.set(v)`。
   - `const watchlist = useQuery({ queryKey: QK.watchlist, queryFn: api.watchlistList, enabled: !!data && mode === 'vip' })`（**D4 双门控**）。
   - `const watchlistSet = useMemo(() => new Set((watchlist.data?.symbols ?? []).map(s => s.symbol)), [watchlist.data])`（Screener.tsx:432-437 同款）。
   - `const toggleWatchlist = useMutation({ mutationFn: ({symbol,inList}) => inList ? api.watchlistRemove(symbol) : api.watchlistAdd(symbol), onSuccess: () => { qc.invalidateQueries({queryKey: QK.watchlist}); qc.invalidateQueries({queryKey: QK.watchlistEnriched()}) } })`（Screener.tsx:440-447 同款）。
   - `filteredRows` 扩展：概念子串基础上，`if (watchlistOnly) rows = rows.filter(r => watchlistSet.has(r.symbol))`。
   - 批量：`const batchAdd = useWatchlistBatchAdd()`；`handleBatchAdd = () => filteredRows.length && batchAdd.mutate(filteredRows.map(r => r.symbol), {...})`（Screener.tsx:498-513 同款）。
   - 渲染：钻取区 header（`<h2>…股池明细</h2>` 行右侧或 ConceptFilter 同行）新增——`只看自选` 开关（`role="switch"` + `aria-checked`，先例 `frontend/src/components/ext-data/ExtDataPullPanel.tsx:205-209`；**仅 `mode==='vip'` 渲染**）；`批量加自选` 按钮（`Star` 图标 + `disabled={batchAdd.isPending}`；**仅 VIP 且 `!watchlistOnly` 渲染**）。
   - `<StockListTable>` 新增 props：`watchlistSet`、`onToggleWatchlist={(s,in) => toggleWatchlist.mutate({symbol:s, inList:in})}`、`watchlistPending={toggleWatchlist.isPending}`、`watchlistOnly`。
3. **`frontend/src/components/pool-hub/StockListTable.tsx`**：
   - props 扩展：`watchlistSet: Set<string>`、`onToggleWatchlist: (symbol: string, inList: boolean) => void`、`watchlistPending: boolean`、`watchlistOnly: boolean`。
   - VIP 代码单元格（`:214-227` 分支内）在 `row.code` 后渲染星标按钮：`const inList = watchlistSet.has(row.symbol)`；`<button type="button" onClick={() => onToggleWatchlist(row.symbol, inList)} disabled={watchlistPending} aria-label={inList ? '移出自选' : '加入自选'} title={…} className={...}>`；内 `{inList ? <Star className="h-3.5 w-3.5" fill="currentColor" /> : <Star className="h-3.5 w-3.5" />}`，颜色 `inList ? 'text-amber-400' : 'text-muted hover:text-accent'`（对齐 StockInfoBar 先例）。**guest 分支 `:228-242` 一字不改**。
   - 空态：`filterActive = filterText.trim().length > 0 || watchlistOnly`；新增分支——`watchlistOnly && !conceptActive && rows.length===0` → 「自选清单中无该策略个股」（诚实空态）；两者同时激活且 0 行 → 优先概念文案或合并文案（建议：只看自选文案，因其是更窄的主动过滤）。footer 复用现有「筛选后 N 只 / 共 total 只」语义（`total` 权威不变）。
   - 表头列结构不变（星标在代码单元格内，不新增列）。
4. **`frontend/e2e/pool-hub.spec.ts`**：
   - `installShell`（`:250-330`）追加默认 `await page.route('**/api/watchlist**', route => json(route, { symbols: [] }))`，避免 VIP 用例因 unhandled 500。
   - **更新 `ALLOWED_RE`**（`:620-626`）加入 `只看自选|批量加自选|加入自选|移出自选`（Common Pitfall P1，不改则红）。
   - 新增用例（全部 desktop 项目 + installShell）：
     - WATCH-01 VIP 星标：mock hub(vip) + `/api/watchlist` → `{symbols:[{symbol:'300750.SZ',added_at:'…'}]}`；断言 300750 行星标 aria-label=移出自选、600519 行=加入自选；点击 600519 星标 → 断言捕获 `POST /api/watchlist` 且 body symbol=600519.SH → 星标翻转（cache invalidate）。
     - WATCH-01 guest 零查询：mock hub(guest)；`page.on('request')` 捕获 → 断言无 `/api/watchlist`；且 `main` 内无 加入自选/移出自选 控件（`getByLabel('加入自选')` count 0）。
     - WATCH-02 只看自选：mock vip + watchlist 含 `300750.SZ`；点开关 → 表格仅剩 300750 行，footer `筛选后 1 只 / 共 2 只`（total 权威）；再 mock 一个自选不含任何行的策略 → 开关开 → 空态文案「自选清单中无该策略个股」。
     - WATCH-02 历史同构：切历史日期（复用 historyPayload 夹具）后开关仍生效。
     - WATCH-04 批量：点「批量加自选」→ 断言捕获 `POST /api/watchlist/batch` 且 body.symbols 恰为可见行 symbol 数组。
   - 视觉快照：`captures visual evidence for the five UI-SPEC backstop scalars`（`:742-774`）的 VIP 快照（pool-table-resonance / pool-table-filter-active）因新增星标需 `npx playwright test --update-snapshots` 重生成并人工复核（只应出现星标/开关/批量按钮，无其他漂移）。
5. **验证**：`cd frontend && npm run build`（tsc -b && vite build）+ `npx playwright test pool-hub.spec.ts`；后端 `cd backend && pytest`（确认 POOL-03 / guest 守卫仍绿——本 phase 零后端改动）。

## Standard Stack

| 类别 | 选型 | 版本 | 用途 | 依据 |
|---|---|---|---|---|
| 图标 | `lucide-react` 内 `Star` | ^0.439.0（已在树） | 星标 + 批量按钮 | `Screener.tsx:5`/`StockInfoBar.tsx:2` import 证据 |
| 服务端状态 | `@tanstack/react-query` `useQuery/useMutation` | ^5.55.0（已在树） | QK.watchlist 共享缓存 + toggle 乐观态 | `Screener.tsx:429-447` 先例 |
| 开关控件 | 原生 `role="switch"` button | — | 「只看自选」开关 | `ExtDataPullPanel.tsx:205-209` 先例 |
| 持久化 | `storage.kv<boolean>` | 内置 | `poolWatchlistOnly` UI 偏好 | `storage.ts:8-23` |

**安装：无。** 零新增依赖（v2.1 约束；`frontend/package.json` 现有锁定栈）。

## Package Legitimacy Audit

| Package | Registry | Verdict | Disposition |
|---|---|---|---|
| lucide-react / @tanstack/react-query | npm（已在树） | OK（既有锁定依赖，非新增） | 复用，不安装 |

**无新增包** — 本 phase 不触发安装门。

## Don't Hand-Roll

| 问题 | 不要自建 | 用现有 | 原因 |
|---|---|---|---|
| 自选清单存储 | localStorage 第二清单 | 服务端 `watchlist.parquet` + `QK.watchlist` | 四处服务端消费（pools.py/daily_pipeline/quote_service），双源必漂移 |
| 星标 toggle | 手写 fetch | `api.watchlistAdd/Remove` mutation | 401 拦截/缓存失效/乐观态全在 react-query 层 |
| 批量加自选 | 手写循环 POST | `api.watchlistBatchAdd` + `useWatchlistBatchAdd` | 端点幂等、共享失效逻辑已封装 |
| 服务端 is_watched 投影 | 给 hub 加自选字段 | 前端 join | POOL-03 `_EXECUTION_TOKEN` 含 watchlist 锁死 import |
| 跨页一致性同步 | 事件总线/轮询 | `QK.watchlist` 全局缓存 + invalidate | 自选页/策略页/弹窗已共用同一 key |

**Key insight**：自选是「单一事实来源在服务端、前端持有一份缓存投影」的问题——react-query 的共享 key 就是现成的「本地持有一致」机制，任何自定义同步都是重复造轮子且必然漂移。

## Common Pitfalls

### P1：e2e `ALLOWED_RE` 白名单锁死新增控件（必踩）
- **What**：`pool page renders zero execution affordances`（pool-hub.spec.ts:591-641）遍历 `main` 内所有按钮并要求 name 匹配 `ALLOWED_RE`；新增「只看自选」「批量加自选」及星标 aria-label 均不匹配 → 测试红。
- **Why**：POOL-03 守卫用白名单穷举「股池页唯一交互」，任何新控件都必须显式登记。
- **How**：把新控件的可访问名加进白名单（`只看自选|批量加自选|加入自选|移出自选`）；星标按钮必须给 aria-label（icon-only 拿空 name 也会红）。
- **Warning**：跑 e2e 前先 grep 白名单。

### P2：guest 首屏 401 跳登录（最危险）
- **What**：guest 会话因 `mode` 回退 vip（`PoolHubPage.tsx:34`）在 data 落地前发出 `/api/watchlist` → 401 → `main.tsx:22-27` 整页跳登录。
- **Why**：mode 是从 `data?.mode` 推导的，data 为 null 时默认 vip。
- **How**：`enabled: !!data && mode === 'vip'` 双门控；并加 guest 零查询 e2e。
- **Warning**：用 guest 载荷跑一次完整加载看捕获请求。

### P3：VIP 视觉快照漂移
- **What**：`captures visual evidence for the five UI-SPEC backstop scalars`（:742-774）对 VIP 载荷截 `pool-table-resonance.png`/`pool-table-filter-active.png`；新增星标会改变画面 → 快照对比失败。
- **Why**：星标渲染在表格区域内。
- **How**：`--update-snapshots` 重生成 + 人工复核仅新增预期控件；guest 快照不受影响（不要误更新）。
- **Warning**：确认只更新 VIP 两张，勿连带更新 guest 快照。

### P4：`filterActive` 空态文案错位
- **What**：现有空态只按 `filterText` 判 `filterActive`（StockListTable.tsx:178-205）；加了「只看自选」后若直接把 `filterActive` 扩展为 `|| watchlistOnly`，0 行时会显示「无符合『{filterText}』的个股」——filterText 为空时文案荒谬。
- **Why**：空态文案与「哪个过滤条件导致空」耦合。
- **How**：拆分 conceptActive / watchlistOnly 两个布尔，分别给独立空态文案（见实现草案）。
- **Warning**：两个条件同时激活且 0 行时明确文案优先级。

### P5：`installShell` 未 mock `/api/watchlist`
- **What**：`installShell` 对未覆盖 `/api` 请求回 500；VIP 用例现在会自动发 `GET /api/watchlist` → 500 → 网络错误日志污染（多数用例仍过，但脆弱）。
- **Why**：`**/api/**` 兜底路由。
- **How**：installShell 加默认 `{symbols: []}` mock；需要具体自选集合的用例后注册覆盖（后注册优先）。
- **Warning**：新用例必须自带 watchlist 夹具，否则 500。

## 风险与开放问题

1. **POOL-05 编号冲突**：v2.0 已 shipped 的 POOL-05 =「历史视图独立只读端点」（pool.py docstring），v2.1 又把自选联动标为 POOL-05。需求文件已用 **WATCH-01..04** 编号，建议全程用 WATCH 编号，避免追溯串号。
2. **Watchlist.tsx 用户未提交改动**（`git status`：`M frontend/src/pages/Watchlist.tsx`）：本方案只消费公共 API + `QK.watchlist`，与页面内部解耦；grep 结构已确认其仍以 `QK.watchlist` 失效（`Watchlist.tsx:693-695/717-720`），未引入第二套存储。**执行前需再确认该改动未改 QK 契约**。
3. **SSE 高频失效 QK.watchlist**（R3）：`SSE_INVALIDATE_PREFIXES` 含 `'watchlist'` → 行情 tick 会失效 `QK.watchlist`。股池页重取是本地小 parquet，开销可忽略；且这是 WATCH-03「共享同一 key」的必要代价，**不可为此换键**。若将来出现节流需求，应在 `useQuoteStream` 层处理而非换键。
4. **批量按钮与只看自选交互**：开关开启时可见行全在自选 → 推荐隐藏批量按钮；如产品要「反向取未自选行」可后续扩展（本期不做）。
5. **自选 symbol 规范化**：`watchlist.add` 原样存 symbol（`watchlist.py:37-52`）；当前所有入口（搜索/策略行/股池行）均为全后缀，join 稳定。若未来出现裸代码入口，**修入口而非加模糊匹配**（WATCH-03 验收）。
6. **ETF 自选**：自选页可加 ETF（`api/kline.py:32` asset_types=stock,etf），股池仅股票 → join 自然不命中，无副作用，无需特判。
7. **历史自选快照**：星标/过滤是「当前自选」对任意 as_of 的实时标注，非历史快照（自选不是时间序列）——产品若需「某历史日自选」，是另一需求。
8. **未来 is_watched 服务端化**：若行数上万或需服务端过滤，再评估独立 annotate 端点（置于 `api/watchlist.py`，不进 pool 特性）或显式改守卫——均需独立决策，本期不做。

## Validation Architecture

> `.planning/config.json` `workflow.nyquist_validation: true` → 包含本段。前端无 vitest；验证 = build + Playwright e2e。

### Test Framework

| Property | Value |
|----------|-------|
| Framework | Playwright 1.61.1（`frontend/devDependencies`） |
| Config file | `frontend/playwright.config.ts`（webServer vite:4173；desktop-chromium 项目） |
| 类型检查 | `npm run build` = `tsc -b && vite build` |
| 快速验证 | `npx playwright test pool-hub.spec.ts --project=desktop-chromium` |
| 全量 | `npm run build` + `npx playwright test` |
| 后端回归 | `cd backend && pytest`（本 phase 零后端改动，POOL-03/guest 守卫必须仍绿） |

### Phase Requirements → Test Map

| Req ID | 行为 | 测试类型 | 自动化命令 | 文件存在？ |
|--------|------|---------|-----------|-----------|
| WATCH-01 | VIP 行星标渲染 + toggle 调 CRUD + 失效缓存；guest 无控件无查询 | e2e | `pool-hub.spec.ts` 新增 2 用例 | ❌ 新增 |
| WATCH-02 | 只看自选收窄行、total 不变、空态诚实、历史同构 | e2e | `pool-hub.spec.ts` 新增 2 用例 | ❌ 新增 |
| WATCH-03 | 共享 QK.watchlist（跨页一致） | e2e + 代码审查 | e2e 断言星标翻转经缓存失效；审查 `PoolHubPage` 只用 QK.watchlist | ❌ 新增 |
| WATCH-04 | 批量按钮 scope=可见行 → `POST /api/watchlist/batch` | e2e | `pool-hub.spec.ts` 新增 1 用例 | ❌ 新增 |

### Sampling Rate
- **Per task commit**：`npx tsc -b --noEmit`（或所属文件的 lint）
- **Per wave merge**：`npm run build` + `npx playwright test pool-hub.spec.ts`
- **Phase gate**：`npm run build` + `npx playwright test` + 后端 `pytest` 全绿

### Wave 0 Gaps
- [ ] `pool-hub.spec.ts` — `installShell` 增加 `/api/watchlist` 默认 mock + `ALLOWED_RE` 白名单扩增（P1/P5）
- [ ] 无新测试框架安装（Playwright 已在树）

## Security Domain

> `.planning/config.json` `workflow.security_enforcement: true` → 包含本段（ASVS L1）。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | 服务端会话中间件 `main.py:802-812`；前端 `enabled: !!data && mode==='vip'` 双门控杜绝 guest 令牌泄漏 |
| V3 Session Management | no | 无新会话逻辑 |
| V4 Access Control | yes | `/api/watchlist` 全 CRUD 已 auth 保护（guest 401）；股池页 guest 不发查询 |
| V5 Input Validation | yes | symbol 来源 = 服务端投影行（`pool_hub.py:132-138`），非用户自由输入；前端不构造 symbol |
| V6 Cryptography | no | 无加解密 |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| guest 越权读自选清单 | Information Disclosure | 前端查询双门控 + 服务端 401（`main.py:802-812`）；e2e 断言 guest 零请求 |
| 星标按钮无意义请求风暴 | DoS | `disabled={watchlistPending}`；批量仅可见行（≤200） |
| 掩码绕过 | Spoofing | 不新增任何 `******` 字面量/`mask` 标识符（e2e grep 守卫 :776-798）；guest 分支原样渲染服务端脱敏值 |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `Star` 图标支持 `fill="currentColor"` 实心渲染 | D1 | lucide-react Star 支持 fill 是 SVG 通用语义 [VERIFIED: 已在树内大量使用 Star；fill 用法为 SVG 标准] |
| A2 | `StarOff` 存在于 lucide-react ^0.439.0 | D1（选项 c，未采用） | 低——推荐方案 a 只依赖 `Star` |
| A3 | SSE 对 `QK.watchlist` 的高频失效对股池页可接受 | R3 | 若节流需求出现，应改 `useQuoteStream` 而非换键（换键破坏 WATCH-03） |
| A4 | 用户未提交的 Watchlist.tsx 改动未破坏 `QK.watchlist` 契约 | 风险 2 | 执行前以 grep 复核其失效逻辑（已确认 :693-695/:717-720 仍用 QK.watchlist） |

## Open Questions

1. **「只看自选」开关与批量按钮的放置**：ConceptFilter 同行（页面级）vs 钻取区 header（表格级）。
   - 已知：概念筛选是页面级（`PoolHubPage.tsx:103-105`）；两个新控件都作用于当前策略的钻取行。
   - 建议：放钻取区 header（与 `批量加自选` 同排），因为它们是「当前策略明细表」专属，且视觉 backstop 只截表格区。交给 planner 落地时定夺。
2. **空态文案矩阵**：概念 + 只看自选同时激活且 0 行时显示哪条？
   - 建议：显示「自选清单中无该策略个股」（自选是更窄的主动过滤），概念文案在仅概念激活时保留。
3. **批量按钮在只看自选开启时**：隐藏 vs 禁用「全部已在自选」。
   - 建议：隐藏（最诚实）。如需反馈，可显示一条静态文本。

## Sources

### Primary（HIGH — 本会话实读）
- `frontend/src/pages/Screener.tsx:429-447, 498-513, 735-745, 800-802`（先例）
- `frontend/src/components/screener/ScreenerTable.tsx:166-210`（星标先例）
- `frontend/src/lib/useSharedMutations.ts:32-41`（批量 mutation）
- `frontend/src/lib/api.ts:2025-2051, 602-605, 696-729`（API + 类型）
- `frontend/src/lib/queryKeys.ts:25-28, 215-216`（QK + SSE 前缀）
- `frontend/src/lib/storage.ts:8-23, 28-44`（kv + UI 偏好）
- `frontend/src/main.tsx:22-27`（401 跳登录）
- `frontend/src/pages/PoolHubPage.tsx:26-51, 120-135`（股池页现状）
- `frontend/src/components/pool-hub/StockListTable.tsx:15-46, 178-242, 400-413`（明细表）
- `frontend/src/components/pool-hub/ConceptFilter.tsx`、`GuestModeBanner.tsx`、`ExtDataPullPanel.tsx:205-209`
- `frontend/e2e/pool-hub.spec.ts:250-330, 591-662, 685-798, 855-1081`（e2e + 守卫）
- `frontend/playwright.config.ts`、`frontend/package.json`
- `backend/app/services/watchlist.py:21-86`、`backend/app/api/watchlist.py:24-58`
- `backend/app/services/pool_hub.py:117-138, 143-267`、`backend/app/api/pool.py:42-47, 97-102`
- `backend/app/main.py:778-812, 847`、`backend/app/services/guest_masking.py:24-56`
- `backend/app/tickflow/pools.py:22, 55-58, 135-140`、`backend/app/jobs/daily_pipeline.py:154-156`
- `backend/app/services/screener.py:614-621, 723-806`
- `backend/tests/test_pool_hub.py:857-902`、`backend/tests/test_guest_masking.py:453-529`

### Secondary（MEDIUM）
- `.planning/research/v2.1-depth/WATCHLIST.md`（领域研究，其结论与本会话实读一致）
- `.planning/REQUIREMENTS.md`（WATCH-01..04 验收语义）

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — 全部复用树内既有库，逐行验证
- Architecture: HIGH — 前端 join + 共享缓存方案与 Screener 先例逐行对照；守卫边界已读测试源码
- Pitfalls: HIGH — e2e 白名单/快照/401 陷阱均来自实际测试源码断言

**Research date:** 2026-08-06
**Valid until:** 2026-08-13（v2.1 开发窗口，前端栈无新版本依赖）
