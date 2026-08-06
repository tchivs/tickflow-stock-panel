# Phase 26 研究:历史竞价图 + 派生列复活

**Researched:** 2026-08-06
**Domain:** 竞价数据湖只读聚合 API + 前端 ECharts 多日趋势 + 湖摄入 canonical 扩展(复活 DATA-06)
**Confidence:** HIGH(代码证据全量 file:line 核验)/ MEDIUM(窗口行粒度与外部源语义不可在本环境验证)
**Requirements covered:** CHART-01, CHART-02, CHART-03

---

## 0. 用户约束

无 `CONTEXT.md`(Phase 26 目录为空),无 `CLAUDE.md`(仓库根不存在,已 `ls` 核验)。约束来自任务书:

- 仓库根 `/home/orca/source/AthenaQuant`,分支 `gsd/v2.0-planning`(已 `git branch --show-current` 核验)
- **只读研究**:不修改任何代码/现有文档(除本 RESEARCH.md);不跑测试/构建
- **绝不触碰 `frontend/src/pages/Watchlist.tsx`**(git status 显示 ` M frontend/src/pages/Watchlist.tsx`,用户预存未提交改动;只可 grep 结构)
- 前端无 vitest;验证 = `npm run build` + Playwright e2e;零新增 npm 依赖(echarts/echarts-for-react 已 in-tree)
- 诚实:不可验证的外部依赖标 `[INFERENCE]`;每条结论附 file:line 证据

---

## 1. 现状(代码证据,file:line)

### 1.1 湖 canonical 只有 4 列,无价格列

- `CANONICAL_AUCTION_COLS = ["symbol","datetime","auction_volume","auction_amount"]` — `backend/app/services/auction_sync.py:32-35`
- `_TABLE_FIELD_DESC["kline_auction"]` 仅 4 字段(`symbol/datetime/auction_volume/auction_amount`)— `backend/app/api/data.py:769-774`
- 当前环境湖 **0 分区**:`data/kline_auction` 目录不存在(`ls -d` 返回 ABSENT);`data/` 下列表无 `kline_auction`
- 结论:无价格列 → 无法从湖重建「单日竞价窗口内撮合价格曲线」;只能画量/额趋势(隐含均价 = amount/volume 可另算,非独立列)

### 1.2 `auction_unmatched_amount`(DATA-06)生产数据流是死代码

- 派生计算:`compute_auction_unmatched_amount` 需要输入列 `auction_unmatched_volume` × `auction_virtual_price` — `backend/app/services/auction_columns.py:100-106`(`_AUCTION_UNMATCHED_VOLUME_COL`/`_AUCTION_VIRTUAL_PRICE_COL`/`_AUCTION_UNMATCHED_AMOUNT_COL` 常量在 `auction_columns.py:17-19`)
- 读路径注入点:`attach_auction_columns` 在 `auction_columns.py:123-124` 检查两输入列在分区内才派生
- **双重裁剪导致输入列永远到不了湖**:
  - 自定义源归一化 `_normalize_auction`:`keep = [c for c in ("symbol","datetime","auction_volume","auction_amount") if c in df.columns]` — `backend/app/data_providers/custom/provider.py:149-160`
  - 写湖 `sync_and_persist_auction`:`keep = [c for c in CANONICAL_AUCTION_COLS if c in df.columns]` — `backend/app/services/auction_sync.py:128-133`
- 全仓库 grep `auction_unmatched_volume|auction_virtual_price` 只命中 `auction_columns.py` 常量 + `test_auction_columns.py`(纯函数单测);生产数据流零命中 → `attach_auction_columns` 的派生分支(auction_columns.py:123)永不触发

### 1.3 写路径细节(CHART-03 改动点)

- 写湖唯一准入闸门 = probe `available`(`can_sync_auction` → `resolve_auction_probe().status == available`)— `auction_sync.py:80-87`;`sync_and_persist_auction` 本体同样先判 probe — `auction_sync.py:91-99`
- 09:30 起连续竞价 bar 由 555..565 分钟谓词双重排除 — `auction_sync.py:105-118`(写湖过滤器)+ `custom/provider.py:149-156`(_normalize_auction)
- 按日分区 merge-upsert:**`pl.concat([existing, day_df.drop("_trade_date")]).unique(subset=["symbol","datetime"], keep="last")`** — `auction_sync.py:135-141`;**默认 `pl.concat` 纵向严格 schema 匹配**,旧 4 列分区与新 6 列写入直接 concat 会 SchemaError(见风险 R1)
- 原子写(.tmp rename)— `auction_sync.py:37-48`
- EOD 一次性、probe 门控:`daily_pipeline.py:593-602` Step 2.6 + `_run_auction_sync` 双闸门(偏好 `auction_sync_enabled` 默认 False `preferences.py:129-131` + probe available)— `daily_pipeline.py:695-705`
- 无保留期/裁剪逻辑(全仓库未发现 kline_auction retention;对比 `alert_store.py:179-181` 有 MAX_DAYS)

### 1.4 读路径 `attach_auction_columns`(CHART-03 无需改代码)

- 双闸门:probe available(`auction_columns.py:107-109`)+ `kline_auction/date={d}/part.parquet` 存在且有行(`auction_columns.py:112-120`)
- 通过后:输入列可得时派生 `auction_unmatched_amount`(auction_columns.py:123-124)→ `_attach_auction_volume_ratio`(需前 5 日均量分母, PIT-safe, `auction_columns.py:126-128` / `52-74`)→ 真实列裁剪 keep(`auction_columns.py:131-141`)→ 防 fan-out 每 symbol 单行 `unique(subset=["symbol"], keep="last")`(auction_columns.py:145)→ `df.join(auction, on="symbol", how="left")`(auction_columns.py:151)
- 消费方:`ScreenerService._attach_auction`(`screener.py:299-314`)注入策略 as-of 帧与池快照;`pool_hub._project_hub` 透传竞价列进钻取行 + 顶层 `auction_columns:{real,derived}` 声明(`pool_hub.py:114-121, 183-186`)
- DuckDB 视图 `kline_auction` 已登记(`repository.py:162-163`,`read_parquet('{d}/kline_auction/**/*.parquet', union_by_name=true)` — union_by_name 天然兼容 4/6 列混合分区);`/api/data/schema/auction` 可用(`data.py:822` + `826-853` 静态回退)
- **缺口**:无任何读 API 暴露「按 symbol 拉多日竞价序列」;`_compute_storage` 不统计 auction 目录(`data.py:484-523` subdirs 无 kline_auction)

### 1.5 现有只读聚合端点先例(CHART-01 镜像)

- `GET /api/kline/daily`(只读,`kline.py:128-186`);`days: int = Query(120, ge=10, le=2000)`;`start = end - timedelta(days=days)`(日历日语义)— `kline.py:130-139`
- `GET /api/pool/history` 空态模式:`available: False` 200 空态(非 404)+ as_of 严格校验 400 — `pool.py:78-114`,`_AS_OF_RE = ^\d{4}-\d{2}-\d{2}$`(`pool.py:22`)
- `GET /api/data/auction-probe` + 30s TTL 缓存 — `data.py:626-650`
- POOL-03 AST 守卫先例(执行族 import 禁 + 写路径禁 + 全部路由 GET):`test_pool_hub.py:853-918`

### 1.6 前端图表基建(CHART-02 零新依赖)

- 依赖在册:`echarts ^5.5.0`、`echarts-for-react ^3.0.2`、`lightweight-charts ^4.2.0` — `frontend/package.json`
- 既有:`EChartsIntraday`(`components/EChartsIntraday.tsx:407`,buildOption 双 grid 双 xAxis 范例 `EChartsIntraday.tsx:124-263`)、`EChartsCandlestick`(SUB_CHARTS vol 子图 `EChartsCandlestick.tsx:82-123`)、`useChartTheme`(`lib/theme.ts:118-121`)、`useECharts` hook(`pages/backtest/charts/useECharts.ts`)
- 集成点:`StockPreviewDialog`(`components/StockPreviewDialog.tsx:41-44`;顶栏「分时」toggle `StockPreviewDialog.tsx:160-175`;`StockPanel` 渲染 `StockPreviewDialog.tsx:234-238`)内嵌 `StockPanel`(`components/StockPanel.tsx:39-53`;K 图 + 条件分时图 `StockPanel.tsx:153-157`)
- 空态组件:`EmptyState`(`components/EmptyState.tsx`,图标 + 引导文案)
- Phase 23 UI 已渲染「派生·虚拟成交」组含 `auction_unmatched_amount` 列(`components/pool-hub/StockListTable.tsx:272-275, 388-389`);API 类型已含 `auction_unmatched_amount`(`lib/api.ts:706-713`)— **只差湖里真实输入列,派生列即点亮**
- 弹窗是跨页面全站通用(ConceptAnalysis/Dashboard/Indices/IndustryAnalysis/LimitUpLadder/Monitor/Screener/StockAnalysis/Watchlist 均挂 `StockPreviewDialog`)— 改 StockPreviewDialog/StockPanel 一处,全站生效

### 1.7 无实时竞价源(界定 CHART-04 范围)

- 内置源无 `auction` 数据集:`_BUILTIN_CHAIN` 无 `"auction"` 键 — `chain.py:20-26`
- `ProviderCapabilities.auction: bool = False` 默认 — `data_providers/base.py:19-26`
- 自定义源 `DatasetName` 含 `"auction"`(`custom/config.py:10`)、loader 接受 auction 数据集(`custom/loader.py:353-357`)— 仅自定义源配置 auction 数据集才可能 probe available
- 现网「实时」= 连续竞价实时行情,无竞价字段(本环境未核验 tencent_provider,沿用 CHART.md [INFERENCE])

---

## 2. 关键决策

### D1 末行 vs 求和(窗口行粒度)

| 选项 | 说明 | 风险 |
|---|---|---|
| **A. 末行(推荐)** | 每 symbol 每交易日照 `datetime` 降序取首行(09:25 最终撮合) | 若源是逐分钟累计快照,末行即最终撮合 ✓;若是独立事件行,末行会低估总量 |
| B. 求和 | 每 symbol 每日量/额求和 | 若源是累计快照,求和 = 多窗口重复累计 → 严重误读 ✗ |
| C. 全量返回 | 返回窗口内所有行,前端自行聚合 | API 体积大;语义决策推给前端 ✗ |

**推荐:A 末行**(与 CHART-01 需求「每交易日照末行(09:25 最终撮合)聚合」逐字一致)。
**理由:** 写路径 fixture 3 行/日(`test_auction_sync.py:31-42` `_rows((16,0),(20,30),(25,0))`),源粒度未验证;末行是默认最稳。**配套:** 响应每行附带 `row_count`(窗口内行数)与 `min_datetime`/`max_datetime`,供前端标注粒度,接入真实源后按源语义钉死(OQ-1)。

### D2 API 形态

| 维度 | 推荐 | 证据/理由 |
|---|---|---|
| 端点 | `GET /api/kline/auction/history?symbol=&days=` | 与 `/api/kline/daily` 只读风格同前缀(`kline.py:15` router prefix `/api/kline`) |
| 模块归属 | **新文件 `backend/app/api/auction_history.py`**(router prefix `/api/kline/auction`) | kline.py 已有 POST sync 端点(`kline.py:550,562,612`),无法做模块级 GET-only 守卫;新文件可镜像 `test_pool_hub.py:853-918` 的 POOL-03 式 AST 守卫;在 `main.py:844-856` 注册 |
| 参数 | `symbol: str`(必需,正则校验)+ `days: int = Query(120, ge=1, le=120)` | 镜像 `pool.py:22` `_AS_OF_RE` 显式校验返 400(注意:FastAPI `Query(ge=1,le=120)` 越界默认返 **422**,验收要 400 需 handler 内显式判断) |
| 数据源 | DuckDB `kline_auction` 视图(`repository.py:162-163`)+ `repo.execute_all`(`repository.py:337-340`),`WHERE symbol=? AND date(datetime) >= ?`,按 `date(datetime)` 分组取末行 | `union_by_name=true` 天然兼容 4/6 列混合分区;只读零写 |
| 响应 | `{symbol, name, available, probe, window:"09:15-09:25", coverage, rows:[{date, datetime, auction_volume, auction_amount, auction_unmatched_volume?, auction_virtual_price?, row_count, min_datetime, max_datetime}]}` | 空湖/无该 symbol 行 → 200 `{available:false, rows:[]}`(绝不 404/500/0 填充);`probe` = 服务端 `resolve_auction_probe().to_dict()`(auction_probe.py:186, `to_dict` 在 `auction_probe.py:52-58`),前端零推导(PIT-3) |
| GET-only 守卫 | 新测试镜像 `test_pool_hub.py:853-918`(执行族 import 禁 + 写路径禁 + 全 GET) | CHART-01 验收「GET-only 守卫(无任何写/执行 import)」 |

**响应骨架(供 executor 参考):**
```json
{
  "symbol": "000001.SZ", "name": "平安银行",
  "available": true,
  "probe": {"status": "available", "source": "custom_x", "window": "09:15-09:25", "...": "..."},
  "window": "09:15-09:25",
  "coverage": 42,
  "rows": [
    {"date": "2026-08-04", "datetime": "2026-08-04T09:25:00", "auction_volume": 8000,
     "auction_amount": 42000.0, "row_count": 3,
     "min_datetime": "2026-08-04T09:16:00", "max_datetime": "2026-08-04T09:25:00"}
  ]
}
```

### D3 图表集成点

| 选项 | 说明 |
|---|---|
| **A. StockPreviewDialog 顶栏加「竞价历史」toggle(推荐)** | 镜像现有「分时」toggle(`StockPreviewDialog.tsx:160-175`);`showAuction` state 传给 StockPanel 新 prop;StockPanel 条件渲染 `AuctionHistoryChart`(与 `showIntraday && selectedDate` 的 `StockIntradayChart` 同槽位 `StockPanel.tsx:153-157`) |
| B. StockPanel 内加 tab | 侵入日K/分时切换逻辑,改动面更大 |

**推荐 A。** 新组件 `components/AuctionHistoryChart.tsx`:
- 查询:`useQuery({queryKey: QK.auctionHistory(symbol, days), queryFn: () => api.auctionHistory(symbol, days)})`(新 key + 新 client 函数;镜像 `QK.kline` `queryKeys.ts:144-145` / `api.klineDaily` `lib/api.ts:1918-1929`)
- 双轴:右轴线 = `auction_amount`(元),左轴柱 = `auction_volume`(股);x = date(category);用 `useChartTheme()`(`lib/theme.ts:118-121`)+ `useECharts`(`pages/backtest/charts/useECharts.ts`)
- 窗口标注:「09:15-09:25」标题 chip + 数据 tooltip;真实/派生纪律:只画 `auction_volume/auction_amount` 真实列,不画/不混排派生列
- 空态:`probe.status !== 'available'` 或 `available:false` → `<EmptyState title="无历史竞价数据" hint="需配置集合竞价数据源并开启 EOD 竞价同步" /`(`EmptyState.tsx`)
- aria:容器 `role="img"` + `aria-label="历史竞价量/金额趋势图"`;加载中/错误文案镜像 `StockDailyKChart.tsx:211-215`
- **绝不触碰 `Watchlist.tsx`**(git status ` M frontend/src/pages/Watchlist.tsx`)

### D4 canonical 扩展(CHART-03)

| 设计点 | 推荐 |
|---|---|
| 常量 | **保留 `CANONICAL_AUCTION_COLS` = 4 必需不变**(`auction_sync.py:32-35`);新增 `OPTIONAL_AUCTION_COLS = ["auction_unmatched_volume","auction_virtual_price"]`(镜像 `auction_columns.py:17-19` 常量名) |
| 写路径 keep | `auction_sync.py:128-133` 与 `custom/provider.py:149-160` 扩为 `CANONICAL_AUCTION_COLS + OPTIONAL_AUCTION_COLS`,按 `if c in df.columns` 存在性过滤(源不提供即列缺席,诚实缺列不 0 填) |
| **merge-upsert schema 兼容** | `auction_sync.py:137` `pl.concat([existing, day_df])` 改 `how="diagonal_relaxed"`(已有先例 `custom/provider.py:178,303`)— 旧 4 列分区 + 新 6 列写入必须能并集 |
| 类型 | `auction_unmatched_volume`: Int64(股);`auction_virtual_price`: Float64(元/股);派生 `auction_unmatched_amount` = 乘积(Float64, `auction_columns.py:101-104`) |
| 自定义源映射 | `map_rows` 只保留 `field_map.values()`(`custom/mapper.py:31-40`)→ 源的 field_map 需含两可选字段映射;`_REQUIRED` 无 auction 键(`provider.py:20-28`),可选字段天然不强制 |
| schema 描述 | `_TABLE_FIELD_DESC["kline_auction"]`(`data.py:769-774`)+ 2 字段,带「估算」标注(镜像 `pipeline.py:178` `auction_unmatched_amount` 描述「估算, 非真实成交」) |
| 读路径 | **`attach_auction_columns` 零代码改动**:输入列在分区即自动派生(`auction_columns.py:123-124`);Phase 23 UI 派生组自动点亮(`StockListTable.tsx:388-389`) |
| 向后兼容 | 源不提供可选列 → 分区仍 4 列,`test_sync_writes_partition` 的 `df.columns == CANONICAL_AUCTION_COLS` 断言(`test_auction_sync.py:70`)不破坏 |

### D5 guest/vip 掩码

| 选项 | 说明 |
|---|---|
| **A. guest 返 200 `{available:false, rows:[], mode:"guest"}`(推荐)** | 镜像 pool 掩码:顶层 `auction_columns` pop + 行级 auction 列不在 `_GUEST_VISIBLE` 白名单(`guest_masking.py:31-37, 52-53`);竞价量/额是「价格/量敏感元信息」(H7/PIT-7),guest 不应见 |
| B. guest 与 vip 同数据 | 泄露敏感量/价,违反既有掩码纪律 ✗ |

**推荐 A。** 前端 guest → 空态(与 pool 钻取一致:guest 永无竞价列)。端点需读 `request.state.reviewer_principal`(镜像 `pool.py:109-112`)。

### D6 空态语义

| 场景 | 行为 |
|---|---|
| 湖空 / 该 symbol 无行 | 200 `{available:false, rows:[]}`(绝不 404、绝不 500、绝不 0 填充) |
| probe 非 available | 200 `{available:false, rows:[]}` + `probe.status` 透传(not_configured/fail_closed/error),UI 显示「需配置集合竞价数据源」 |
| symbol 非法(不匹配 `^\d{6}\.(SH\|SZ\|BJ)$` 等) | 400(镜像 `pool.py:99-105`) |
| days 越界(>120 或 <1) | 400(handler 内显式判断;FastAPI Query 约束默认 422,验收要求 400) |
| 前端 | `<EmptyState>`;绝不渲染零值柱冒充真实 |

---

## 3. 实现方案草案(文件级改动清单 + 顺序)

> 顺序原则:后端写路径(CHART-03)→ 后端只读 API(CHART-01)→ 后端测试 → 前端 API client/组件(CHART-02)→ e2e → 文档。每步单测先行。

### 阶段 A:CHART-03 写路径复活 DATA-06(小改,风险集中点)

1. `backend/app/services/auction_sync.py`
   - 新增 `OPTIONAL_AUCTION_COLS = ["auction_unmatched_volume", "auction_virtual_price"]`(紧邻 `CANONICAL_AUCTION_COLS` `auction_sync.py:32-35`)
   - `sync_and_persist_auction` keep 扩为 `CANONICAL_AUCTION_COLS + OPTIONAL_AUCTION_COLS`(`auction_sync.py:128-133`)
   - `pl.concat([existing, day_df.drop("_trade_date")], how="diagonal_relaxed")`(`auction_sync.py:137`)
2. `backend/app/data_providers/custom/provider.py`
   - `_normalize_auction` keep 同步扩(`provider.py:149-160`)
3. `backend/app/api/data.py`
   - `_TABLE_FIELD_DESC["kline_auction"]` + `auction_unmatched_volume`/`auction_virtual_price` 描述带「估算」标注(`data.py:769-774`)
   - (可选)`_compute_storage` subdirs + `kline_auction`(`data.py:489-502`)
4. 测试:`backend/tests/test_auction_sync.py` 新增「写湖含可选列 → 分区 6 列;不含 → 仍 4 列(向后兼容);旧 4 列分区 + 新 6 列写入 merge 不炸(diagonal_relaxed)」;`backend/tests/test_auction_columns.py` 新增「分区含输入列 → attach 输出含 `auction_unmatched_amount`(= 乘积)」

### 阶段 B:CHART-01 只读聚合 API

5. `backend/app/api/auction_history.py`(新)
   - router `prefix="/api/kline/auction"`;`@router.get("/history")`
   - 校验 symbol(正则 → 400)+ days(显式 1..120 → 400)
   - `resolve_auction_probe().to_dict()` 得 `probe`;guest 掩码
   - 读 `kline_auction` 视图:`repo.execute_all("SELECT symbol, datetime, auction_volume, auction_amount, auction_unmatched_volume, auction_virtual_price FROM kline_auction WHERE symbol = ? AND date(datetime) >= ?", [symbol, start])`(可选列无则 SQL 列缺席,DuckDB 对该 symbol 分区无此列时整列返回 NULL 还是报错需 executor 实测;兜底用 `pl.read_parquet` 分区扫描 + polars 聚合更稳)
   - 分组取末行(每 date 按 datetime 降序首行)+ `row_count`/`min_datetime`/`max_datetime`
   - 空 → 200 `{available:false, rows:[]}`
   - 纯读:不 import 任何 execution/broker/order/portfolio/watchlist 模块,无写路径
6. `backend/app/main.py` — `app.include_router(auction_history.router)`(`main.py:844-856`)
7. 测试:`backend/tests/test_auction_history.py`(新)
   - 复用 `test_auction_columns.py` `_write_auction_partition`/`_daily_frame` 模式(`test_auction_columns.py:40-50`)
   - 多日分区 fixture → 末行聚合正确;空湖 → 200 available:false;非法 symbol/days → 400;guest → 掩码;POOL-03 式 AST 守卫(镜像 `test_pool_hub.py:853-918`)

### 阶段 C:CHART-02 前端

8. `frontend/src/lib/api.ts` — `AuctionHistoryRow` 接口 + `auctionHistory: (symbol, days=120) => request<...>(/api/kline/auction/history?...)`(镜像 `klineDaily` `api.ts:1918-1929`)
9. `frontend/src/lib/queryKeys.ts` — `auctionHistory: (symbol, days) => ['auction-history', symbol, days]`(镜像 `kline` `queryKeys.ts:144-145`)
10. `frontend/src/components/AuctionHistoryChart.tsx`(新)— 双轴柱线图 + 诚实空态 + 窗口标注 + aria(见 D3)
11. `frontend/src/components/StockPanel.tsx` — Props + `showAuction`;`showAuction` 时渲染 `AuctionHistoryChart`(`StockPanel.tsx:153-157` 同槽位)
12. `frontend/src/components/StockPreviewDialog.tsx` — 顶栏加「竞价历史」toggle(镜像 `StockPreviewDialog.tsx:160-175`),state `showAuction`,传给 StockPanel
    - **不触碰 `Watchlist.tsx`**
13. `frontend/e2e/auction-history.spec.ts`(新)— Playwright mock `/api/kline/auction/history`(镜像 `pool-hub.spec.ts:1-83` mock 风格):有数据 → 图渲染 + 轴标签单位;空/`available:false` → 空态文案;probe 非 available → 空态 + 窗口标注;guest → 空态

### 阶段 D:验证与文档

14. 后端:`cd backend && .venv/bin/python -m pytest tests/test_auction_history.py tests/test_auction_sync.py tests/test_auction_columns.py tests/test_auction_probe.py tests/test_pool_hub.py -x -q`(POOL-03 AST 守卫必须保持绿)
15. 前端:`cd frontend && npm run build` + `npx playwright test e2e/auction-history.spec.ts`
16. 文档(可选):`docs/custom-data-source.md` auction 数据集对账(`20-RESEARCH.md:340` 已记缺口)

---

## 4. 风险与开放问题

### 风险

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R1 | **merge-upsert schema 并集**:`pl.concat` 默认严格纵向(`auction_sync.py:137`),旧 4 列分区 + 新 6 列写入会 SchemaError | **高** | 改 `how="diagonal_relaxed"`(已有先例);加专门测试覆盖「旧分区 + 新列写入」 |
| R2 | 验收「非法 days → 400」与 FastAPI `Query(ge/le)` 默认 **422** 冲突 | 中 | handler 内显式 `if not (1 <= days <= 120): raise HTTPException(400)`(镜像 `pool.py:99-105`);或调整验收措辞 |
| R3 | 空湖/当前环境 0 分区:CHART-02 无法用真实数据目验 | 中 | 诚实空态 + e2e mock 数据;文档标注「需配置 auction 源并开启 EOD 竞价同步」 |
| R4 | 窗口行粒度(末行 vs 求和)依赖源语义,本环境不可验证 | 中 | D1 锁末行 + 响应带 `row_count`/`min/max datetime`;接入真实源后按源语义钉死(OQ-1) |
| R5 | `test_sync_writes_partition` 断言 `df.columns == CANONICAL_AUCTION_COLS`(`test_auction_sync.py:70`) | 低(设计已规避) | **必须保持 `CANONICAL_AUCTION_COLS` = 4 不变**,可选列走独立常量;新测试只断言「含可选列时分区含之」 |
| R6 | Watchlist.tsx 用户未提交改动 | 高(触碰即灾难) | 只 grep 结构;集成走 StockPreviewDialog/StockPanel(Watchlist 页面也挂 StockPreviewDialog,`Watchlist.tsx:1339-1342`,无需改它) |
| R7 | 可选列在 DuckDB 视图 union_by_name 下的 NULL 行为 | 低 | 端点读路径用 polars 分区扫描或实测 `union_by_name` 对缺失列返回 NULL 后再定 SQL 实现 |
| R8 | `_compute_storage` 缺 auction 目录(可选改) | 低 | 顺带加 `kline_auction` subdir(`data.py:489-502`),非必需 |

### 开放问题

| # | 问题 | 现状 | 建议 |
|---|---|---|---|
| OQ-1 | 外部实时竞价源是否可得(CHART-04 前置) | 本环境无源可测;内置源无 auction 能力(`chain.py:20-26`、`base.py:26`);自定义源需配置 auction 数据集才可能 probe available | 本期不实现 CHART-04;probe 实测判定条件:源返回窗口内行且含 `auction_unmatched_volume`+`auction_virtual_price` → 可行,否则正式 defer |
| OQ-2 | 自定义源 `get_auction` 映射链路:可选列要存活需 `field_map` 含之(`custom/mapper.py:31-40`) | 无真实源可测 | 写路径 keep 放宽后,文档注明源配置需映射两可选字段 |
| OQ-3 | guest 是否应看到「竞价历史」图 | pool 钻取 guest 永无竞价列(掩码纪律) | 按 D5 掩码;若产品要 guest 看量(非价)趋势,需显式放宽掩码白名单 — 本期建议不放开 |
| OQ-4 | `days` 上限 120 是否够(镜像 kline daily 默认 120/上限 2000) | 需求写 `<1..120>` | 按 120 实现;可后续放宽,不改协议 |
| OQ-5 | 隐含均价(amount/volume)是否值得画 | 湖无独立价格列 | 本期只画量/额;隐含均价留作可选增强,不入 CHART-02 范围 |

---

## 5. Validation Architecture

`.planning/config.json`:`workflow.nyquist_validation: true`(启用)→ 本节必需;`security_enforcement: true`(启用)→ 见 §6。

### 后端

| 属性 | 值 |
|---|---|
| Framework | pytest(仓库既有;`.venv/bin/python -m pytest`) |
| Config | `backend/pytest.ini` / 无独立配置(仓库约定模块级不触发 DuckDB 单例,import 放测试函数内) |
| 快速命令 | `cd backend && .venv/bin/python -m pytest tests/test_auction_history.py tests/test_auction_columns.py -x -q` |
| 全量(相关) | `cd backend && .venv/bin/python -m pytest tests/test_auction_history.py tests/test_auction_sync.py tests/test_auction_columns.py tests/test_auction_probe.py tests/test_pool_hub.py -x -q` |

### 前端

| 属性 | 值 |
|---|---|
| Framework | **无 vitest**;验证 = `npm run build`(tsc -b + vite build,`package.json` scripts)+ Playwright e2e(`@playwright/test 1.61.1`) |
| e2e 命令 | `cd frontend && npx playwright test e2e/auction-history.spec.ts` |

### 需求 → 测试映射

| Req | 行为 | 类型 | 命令 |
|---|---|---|---|
| CHART-01 | 有分区 → 末行聚合正确;空湖 → 200 available:false;非法 → 400;guest → 掩码;GET-only AST 守卫 | unit/integration | `pytest tests/test_auction_history.py -x -q` |
| CHART-02 | 图渲染 + 轴标签单位;空态文案;窗口标注;guest 空态 | e2e(mock) | `playwright test e2e/auction-history.spec.ts`;build 绿 |
| CHART-03 | 写湖含可选列 → 分区 6 列;不含 → 4 列;merge 不炸;读路径派生 `auction_unmatched_amount` | unit | `pytest tests/test_auction_sync.py tests/test_auction_columns.py -x -q` |

### 回归面(必须保持绿)

- `test_auction_sync.py` / `test_auction_columns.py` / `test_auction_probe.py` — 竞价域既有
- `test_pool_hub.py:853-918` — POOL-03 AST 守卫(新增 auction_history 模块不得破坏)
- `test_guest_masking.py` — 掩码纪律(若 D5 触达 guest_masking 需回归)

---

## 6. Security Domain

`security_enforcement: true`(`config.json`),ASVS Level 1。

### 适用 ASVS 类别

| ASVS | 适用 | 控制 |
|---|---|---|
| V2 Authentication | 是(guest/vip 掩码) | `request.state.reviewer_principal` 判定(`pool.py:109-112` 先例) |
| V3 Session Management | 否 | 只读端点,复用既有会话 |
| V4 Access Control | 是 | guest 掩码:`auction_history` 对 guest 返空态(镜像 `guest_masking.py:52-53`) |
| V5 Input Validation | 是 | symbol 正则 + days 范围显式校验 → 400(镜像 `pool.py:99-105`);防路径穿越(`_AS_OF_RE` 先例 `pool.py:22`) |
| V6 Cryptography | 否 | 无敏感数据落盘/传输 |

### 威胁模式

| 模式 | STRIDE | 缓解 |
|---|---|---|
| 越权读取竞价量/额(guest) | Information Disclosure | D5 掩码;镜像 `guest_masking.py` 白名单纪律 |
| 非法 symbol 注入 SQL/路径 | Tampering | 参数化 SQL(`repo.execute_all(sql, params)` `repository.py:337-340`)+ symbol 正则 400 |
| 写/执行逃逸 | Elevation | POOL-03 式 AST 守卫(镜像 `test_pool_hub.py:853-918`);`auction_history.py` 无写路径、无 execution import |
| probe 详情信息泄露(error 透出) | Information Disclosure | `_ERROR_DETAIL_MAX = 200` 截断(`auction_probe.py:24-25, 141`)已处理 |

---

## 7. Environment Availability

| 依赖 | 需要方 | 可用 | 版本 | Fallback |
|---|---|---|---|---|
| Python + pytest | 后端测试 | ✓ | 仓库既有 | — |
| Node/pnpm + vite + Playwright | 前端 build/e2e | ✓ | vite ^5.4.3 / playwright 1.61.1 | — |
| ECharts(前端) | CHART-02 | ✓ in-tree | ^5.5.0 | — |
| `data/kline_auction` 湖分区 | CHART-01/02 真实数据 | **✗(0 分区,目录不存在)** | — | 诚实空态;fixture/mock 验收 |
| 真实集合竞价数据源(自定义源 auction 数据集) | 湖累积 + probe available | **✗(本环境不可验证)** | — | CHART-04 defer;CHART-01/02 条件式交付 |

**缺失且无 fallback:** 真实竞价数据源(阻塞 CHART-04 与真实数据目验,不阻塞代码交付 — CHART-01/02/03 全部按「有数据就画、无数据诚实空态」交付)。

---

## 8. 来源与置信

### 代码证据(HIGH,本会话直接读取)

- 写路径:`auction_sync.py:32-35, 37-48, 80-87, 91-153`;`custom/provider.py:135-160`;`custom/mapper.py:31-40`
- 读路径:`auction_columns.py:17-19, 52-74, 89-151`
- 湖/视图/存储:`repository.py:57-58, 162-163, 337-345, 1668-1669`;`data.py:484-523, 626-650, 769-774, 822, 826-853`
- probe/闸门:`auction_probe.py:24-38, 86-133, 134-186`;`daily_pipeline.py:593-602, 695-705`;`preferences.py:129-131`;`chain.py:20-26`;`base.py:19-26`;`custom/config.py:10`
- 消费方/掩码:`screener.py:299-314`;`pool_hub.py:114-121, 183-186`;`guest_masking.py:31-37, 52-53`;`pool.py:22, 55-114`
- 注册面:`pipeline.py:176-185`(ENRICHED_COLUMNS/BY_CATEGORY['auction'])
- 测试:`test_auction_sync.py:31-42, 67-71, 94-223`;`test_auction_columns.py:14-60, 123-243, 284-294`;`test_pool_hub.py:853-918`
- 前端:`StockPreviewDialog.tsx:41-44, 160-175, 234-238`;`StockPanel.tsx:39-53, 153-157`;`EChartsIntraday.tsx:124-263, 407`;`EChartsCandlestick.tsx:82-123`;`EmptyState.tsx`;`useECharts.ts`;`lib/api.ts:67-71, 683-714, 1918-1962, 2217-2222`;`lib/queryKeys.ts:135, 144-151`;`lib/useSharedQueries.ts:85-91`;`lib/theme.ts:118-121`;`package.json`;`StockListTable.tsx:272-275, 388-389`
- 环境核验:`git branch --show-current`(gsd/v2.0-planning);`git status --short`(Watchlist.tsx 用户改动);`ls -d data/kline_auction`(ABSENT);`.planning/config.json`

### [INFERENCE] 项(训练知识/不可本环境验证,需用户确认)

- 窗口行粒度 = 逐分钟累计快照(末行 = 最终撮合):[INFERENCE],写路径 fixture 3 行/日(`test_auction_sync.py:31-42`)仅证明多行可能
- tencent 实时源无竞价字段:沿用 CHART.md [INFERENCE](本会话未重读 tencent_provider)
- 真实竞价源可得性:不可验证(OQ-1)

**置信 breakdown:** 现状/决策/方案 = HIGH(逐行代码核验);窗口粒度/外部源 = MEDIUM-LOW([INFERENCE],见 OQ-1)。
