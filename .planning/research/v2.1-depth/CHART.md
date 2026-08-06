# 历史竞价图 / 虚拟成交实时列 研究

**领域:** 历史竞价图(多日竞价量/金额趋势) + 虚拟成交列(盘前/派生估算)
**Researched:** 2026-08-06
**模式:** Ecosystem(数据可得性核实 + 候选方案对比)
**总体置信:** MEDIUM —— 代码 seam 全部逐行核验(HIGH);外部「实时竞价源」可行性与窗口内行粒度**无法在本环境验证**,给出判定条件(MEDIUM/LOW 标注)。

---

## 一、现状(代码证据)

### 1.1 湖保留了什么:`data/kline_auction/date={d}/part.parquet` 只有 canonical 4 列,**不是**研究问题假设的那 4 列

| 研究问题假设列 | 实际是否在湖里 | 证据 |
|---|---|---|
| `auction_volume`(竞价量/股) | ✅ 在 | `CANONICAL_AUCTION_COLS = ["symbol","datetime","auction_volume","auction_amount"]` — `backend/app/services/auction_sync.py:32-35` |
| `auction_amount`(竞价金额/元) | ✅ 在 | 同上 + `_TABLE_FIELD_DESC["kline_auction"]` 仅 4 字段 — `backend/app/api/data.py:769-774` |
| `auction_unmatched_amount` | ❌ **不在湖里** | 派生读路径列(估算),`attach_auction_columns` 在委托量输入列可得时才派生 — `backend/app/services/auction_columns.py:35-51`;写路径裁剪集只有 4 canonical 列 — `auction_sync.py:128-133` |
| `auction_virtual_fill` | ❌ **代码中不存在** | 全仓库 grep `auction_virtual_fill` 零命中;仅出现在 v2.0 规划文档(STATE.md:73「字段语义依赖上游,物化前以 probe 实测确认」) |

关键结论:**湖 = `symbol + datetime + auction_volume + auction_amount` 四列**。没有价格列 → **「单日竞价窗口内撮合曲线(价格曲线)」从湖数据无法重建**;只有窗口内 `auction_volume/auction_amount` 随时间步进的累计/增量趋势。

### 1.2 `auction_unmatched_amount`(DATA-06)在生产数据流中是死代码路径

- 输入列 `auction_unmatched_volume` / `auction_virtual_price` 的**唯一生产写入点** `_normalize_auction` 会裁剪掉它们:`keep = [c for c in ("symbol","datetime","auction_volume","auction_amount") if c in df.columns]` — `backend/app/data_providers/custom/provider.py:150-160`
- 写湖 `sync_and_persist_auction` 同样裁剪:`keep = [c for c in CANONICAL_AUCTION_COLS if c in df.columns]` — `auction_sync.py:128-133`
- 全仓库 grep `auction_unmatched_volume|auction_virtual_price` 只命中 `auction_columns.py` 常量 + `test_auction_columns.py`(纯函数单测)
- 因此读路径 `attach_auction_columns` 里的 `compute_auction_unmatched_amount` 分支(`auction_columns.py:100-106`)在真实数据流中**永远不触发** → `auction_unmatched_amount` 列在真实池中恒缺席。「虚拟成交列」目前只存在于 schema 描述(`pipeline.py:160`)/UI 契约(Phase 23 `派生·虚拟成交` 组),**没有任何真实值**。

### 1.3 摄入时机与保留

- **EOD 一次性、probe 门控**:`daily_pipeline.py:593-602` Step 2.6 调 `_run_auction_sync`;双闸门 = 偏好 `auction_sync_enabled`(**默认 False**,`preferences.py:129-131`)+ `can_sync_auction`(probe `available`,`auction_sync.py:80-87`)。`_run_auction_sync` 本体 `daily_pipeline.py:695-705`。
- **无盘前/盘中写入**:湖只累积每日 EOD 窗口行;没有 09:15-09:25 实时订阅回填路径。
- **无保留期/裁剪**:全仓库未发现 `kline_auction` 的任何 retention/prune/cleanup 逻辑(对比 `alert_store.py:179-181` 有 `MAX_DAYS` 裁剪)。分区随每日 EOD 无限累积(镜像 kline_daily)。
- 写入为按日分区 merge-upsert(`unique(subset=["symbol","datetime"], keep="last")`)+ 原子写(`.tmp` rename)— `auction_sync.py:37-48, 135-144`。

### 1.4 湖实际分区:当前环境 **0 个分区**

```bash
$ ls data/ | grep auction        # (无输出)
$ find . -maxdepth 4 -name kline_auction  # (无输出)
```

- `data/kline_auction` 目录**不存在**;`data/kline_daily` 有 249 个 `date=*` 分区,但竞价湖零分区。
- 与 v2.0 实测基线一致:`resolve_auction_probe()` 返回 `not_configured`(20-RESEARCH.md:11,`probed_at` 实测)。
- 原因(代码):`_BUILTIN_CHAIN` 无 `"auction"` 数据集(`chain.py:20-26`);`ProviderCapabilities.auction` 默认 `False`(`base.py:19-26`),内置源 free_stockdb/ifzq/xyz/tickflow 全部未声明 `auction=True`;仅自定义源配置 `auction` 数据集才会让 probe 有机会 `available`(`auction_probe.py:86-112`)。当前 free 档 capabilities.json 无 auction 能力。

### 1.5 读路径 `attach_auction_columns`

- 双闸门:probe `available` + `kline_auction/date={d}/part.parquet` 存在且有行;任一不通过 → 原样返回(列缺席、诚实缺列)— `auction_columns.py:93-149`。
- 通过后:按 symbol 去重为每行(防窗口内多行 fan-out)→ 左联注入 `auction_volume/auction_amount`(+ 输入可得时 `auction_unmatched_amount`,+ `auction_volume_ratio` 需前 5 日均量分母 PIT-safe)。
- 消费方:`ScreenerService._attach_auction`(`screener.py:299-314`)注入策略 as-of 帧与池快照;`pool_hub` 透传竞价列进钻取行 + 顶层 `auction_columns:{real,derived}` 声明(`pool_hub.py:104-125, 154-162`);DuckDB 视图 `kline_auction` 已登记(`repository.py:162-163`);`/api/data/schema/auction` 可用(`data.py:769-774, 822`)。
- **缺口**:没有任何读 API 暴露「按 symbol 拉多日竞价序列」。`_compute_storage` 不统计 auction 目录(`data.py:489-502`),`_table_cache` 无 auction 聚合(`data.py:33-44`)。现有 `kline_auction` 视图只能被 SQL 查询,前端无直接通道。

### 1.6 前端图表基础设施:充足,零新依赖

- 依赖在册:`echarts` + `echarts-for-react` + `lightweight-charts`(`frontend/package.json` dependencies)。
- 既有组件:`EChartsIntraday`(分时,`EChartsIntraday.tsx:407`)、`EChartsCandlestick`、`StockDailyKChart`、`MiniIntraday/MiniCandlestick`、`pages/backtest/charts/*`(FactorICChart/StrategyNavChart 等柱/线图范例)、`useChartTheme`(`lib/theme.ts`)。
- 集成点:`StockPreviewDialog`(全站通用个股弹窗,`StockPreviewDialog.tsx:41-44`)内嵌 `StockPanel`(`StockPanel.tsx:153-157`)承载 日K + 分时 toggle。历史竞价图可作第三 tab/面板。

### 1.7 「实时」的现状:无任何实时竞价源

- 免费实时源 Tencent(`tencent_provider.py:171-193`)归一化字段为 `last_price/prev_close/open/high/low/volume/amount/change_pct/.../session:"realtime"` —— **无 `auction_*`、无未匹配/虚拟字段**;`session:"realtime"` 语义是连续竞价时段报价。
- 实时推送基建存在但不承载竞价:`useQuoteStream`(SSE)+ `useQuoteStatus`(60s poll,`useSharedQueries.ts:45-52`)+ `useAuctionProbe`(30s stale,`useSharedQueries.ts:85-91`)+ `/api/data/auction-probe(redetect)`(`data.py:626-650`)。
- 结论:现网「实时」= 连续竞价行情实时,**不是** 09:15-09:25 集合竞价实时快照。竞价实时源需外部自定义源(probe 门控)或新增能力,本环境**不可验证**(见开放问题 OQ-1)。

---

## 二、候选方案对比

| 方案 | 数据可得性 | 工作量 | 风险 | 与现有架构契合 |
|---|---|---|---|---|
| **(a) 历史竞价图 = 湖只读聚合 API + 前端图** | 湖 4 列;但**当前 0 分区**——需用户配置真实 auction 源 + 开 `auction_sync_enabled` 累积 EOD 分区后才有点可画 | 中(后端 1 只读端点 + 前端 1 ECharts 组件 + 1 集成点) | 低-中:空湖诚实空态;行粒度歧义(窗口多行 → 取末行还是求和需钉死);无价格列 → 只能画量/额趋势,不能画价格撮合曲线 | 高:完全复用 lake/probe/视图/schema 机制,零新增依赖,POOL-03 零执行权模式可镜像 |
| **(b) 虚拟成交实时列 = 实时竞价源订阅** | **无可用源**:内置源无 auction 能力;Tencent 实时无竞价字段;外部源可行性未验证 | 高(新数据源接入 + 盘前摄入/刷新循环 + SSE 推送 + 前端列刷新) | 高:外部源不可得则整条白做;零新增运行时依赖约束下只能走自定义源;且 DATA-06 输入列现被写路径裁剪,需先打通 | 中:probe 门控哲学早已为「缺源 fail-closed」铺路,但本期无源可验 |
| **(c) 都不做,defer** | — | 0 | 无 | 与 v2.1 「候选,研究确认」措辞一致;但放弃了一个低成本、与既有湖架构天然契合的只读特性 |

**关键诚实标注:**
- (a) 的「v2.0 已存逐日竞价数据则零新依赖」**在当前环境不成立**——湖是空的。只有当用户配置了真实竞价源并开启 EOD 竞价同步后,(a) 才有数据可画。因此 (a) 应设计为「有数据就画、无数据诚实空态」的条件式交付,而不是假设湖里有历史。
- (b) 的「实时」语义歧义已澄清:盘前实时刷新(09:15-09:25 逐点更新)需要**实时竞价快照源**,现有任何内置源都不提供;盘中/盘后静态列则不需要实时源,但当前派生列因写路径裁剪而恒缺席。

---

## 三、推荐方案 + 理由

**推荐:做 (a) 历史竞价图(多日趋势,条件式)+ 一个「复活 DATA-06」的小后端改动;虚拟成交实时列 defer 到外部源 probe 验证之后。**

1. **(a) 历史竞价图做,但定位为「条件式」**:后端只读聚合 API + 前端 ECharts 多日竞价量/金额柱线图,挂在 `StockPreviewDialog`/`StockPanel`。理由:与既有 `kline_auction` 湖/视图/probe/诚实缺列机制**完全同构**,零新依赖,POOL-03 零执行权模式现成;即便当前空湖,UI 诚实空态 + 未来配置源后自动点亮,是低成本、不烂尾的交付。行粒度先按「每窗口取末行(09:25 最终撮合)」为默认,把「求和 vs 末行」作为显式设计决策写进验收。
2. **「虚拟成交」不追实时,改为打通派生列数据流**:让写路径/归一化**保留** `auction_unmatched_volume`/`auction_virtual_price`(源提供时),使 `auction_unmatched_amount`(估算)真正从湖读路径派生出来。这是让 Phase 23 已交付的「派生·虚拟成交」UI 分组有真实值的最短路径,也是 DATA-06 的诚实补全;不依赖任何新数据源。
3. **虚拟成交实时列(盘前)明确 defer**:阻塞在「实时竞价快照源是否可得」这一外部不可验证项上。推荐先开一个 probe 验证研究(自定义 auction 源实测窗口内是否返回虚拟未匹配量/参考价),验证通过再单开 phase。

**不推荐(c) 全 defer**:因为 (a) 的只读聚合 + 图与现有湖架构契合度极高、风险低,且「复活 DATA-06」是把已注册未生效的能力补全,两者都不需要新外部源即可完成代码面(数据面待源)。

---

## 四、需求草案(可验收)

### CHART-01 历史竞价聚合只读 API

**目标:** 研究者/前端可按 symbol 拉取多日竞价量/金额序列。

- 新增只读端点 `GET /api/kline/auction/history?symbol=<code>&days=<1..120>`(镜像 `kline.py` 既有只读风格;GET-only,零执行权,可挂 POOL-03 式 AST 守卫)。
- 数据源:`kline_auction` DuckDB 视图(已登记,`repository.py:162-163`),按 `symbol` 过滤、按 `date` 升序聚合;每窗口默认取**末行(09:25 最终撮合)**,窗口多行的行数与 min/max datetime 一并返回供前端标注粒度。
- 响应含 `probe`(服务端 `resolve_auction_probe()` 判定)与 `coverage`(实际返回天数);湖空/该 symbol 无行 → 200 诚实 `{available:false, rows:[]}`(绝不 500、绝不 0 填充)。
- PIT-safe:只读历史分区,不混入当日、不做任何写路径。
- **验收标准:**
  - `backend/tests/test_auction_history.py` 覆盖:有分区返回正确聚合(末行语义);空湖/缺 symbol → `available:false` 且 200;非法 symbol/days 越界 → 400;GET-only 守卫(无任何写/执行 import)。
  - 与 `test_auction_columns.py` 复用 `_write_auction_partition` 模式,hermetic 无网络。
  - 单测命令 `cd backend && .venv/bin/python -m pytest tests/test_auction_history.py -x -q` 全绿。

### CHART-02 历史竞价图前端

**目标:** 用户在个股详情里看到多日竞价量/金额趋势图。

- 新组件 `components/AuctionHistoryChart.tsx`(ECharts 柱+线,镜像 `EChartsIntraday`/`useChartTheme` 模式;量=柱、金额=线,双 y 轴),挂载进 `StockPreviewDialog`/`StockPanel` 作为新 toggle(日K/分时/竞价历史)。
- 诚实态:probe 非 `available` 或湖空 → 空态文案「无历史竞价数据 · 需配置集合竞价数据源」+ 窗口标注「09:15-09:25」;绝不渲染零值柱冒充真实。
- 真实/派生纪律延续:只画真实 `auction_volume/auction_amount`,不画/不混排派生列;单位由轴标签承载(股/元)。
- 零新增 npm 依赖(echarts 在册);不触碰 `frontend/src/pages/Watchlist.tsx`。
- **验收标准:**
  - `npm run build` 全绿(无 vitest,验证 = build + Playwright e2e)。
  - e2e(`frontend/e2e/pool-hub.spec.ts` 风格 mock `/api/kline/auction/history`):有数据 → 图渲染 + 轴标签单位;mock 空/`available:false` → 诚实空态文案可见;mock probe 非 available → 空态 + 窗口标注。
  - 手动:空湖环境打开个股弹窗 → 竞价历史 tab 显示诚实空态而非空白/报错。

### CHART-03 湖摄入保留委托量输入列(复活 DATA-06)

**目标:** 让 `auction_unmatched_amount`(估算,非真实成交)真正从湖读路径派生出来,补全 Phase 23 已交付的「派生·虚拟成交」列。

- 写路径 `_normalize_auction`(`custom/provider.py:150-160`)与 `sync_and_persist_auction` 的裁剪集(`auction_sync.py:128-133`)在**源提供列时**保留 `auction_unmatched_volume`/`auction_virtual_price`(canonical 集扩为「4 必需 + 2 可选」);源不提供 → 列缺席(诚实缺列,不 0 填)。
- 读路径 `attach_auction_columns` 既有 `compute_auction_unmatched_amount` 分支(`auction_columns.py:100-106`)因此激活;`_TABLE_FIELD_DESC["kline_auction"]`/schema 同步补字段描述(带「估算」标注)。
- 约束:派生列与真实列分列共存、永不相加(延续 `auction_columns.py` 既有纪律与 Phase 23 UI 分组)。
- **验收标准:**
  - `backend/tests/test_auction_sync.py` / `test_auction_columns.py` 新增:写湖 fixture 带 `auction_unmatched_volume/auction_virtual_price` → 分区含该两列;不带 → 分区仍 4 列(向后兼容)。
  - 读路径:分区含输入列 → `attach_auction_columns` 输出含 `auction_unmatched_amount`(= 乘积,估算);缺输入列 → 原样缺列。
  - 既有 `test_auction_sync.py`/`test_auction_columns.py`/`test_auction_strategy_family.py` 全套 `-x -q` 全绿(无回归)。

### CHART-04(候选/条件式,建议本期只研究不实现)虚拟成交实时列(盘前)

**目标:** 盘前(09:30 前)实时刷新 09:15-09:25 虚拟未匹配量/参考价/金额列。

- 前置条件(probe 验证):存在一个自定义 auction 数据源,实测返回窗口内行且含 `auction_unmatched_volume`/`auction_virtual_price`(或等价虚拟撮合字段)。
- 若满足:新增盘前摄入/轮询 loop(镜像 `_run_auction_sync` 的 probe 双闸门)+ SSE/poll 推送 + 前端列刷新(复用 `useQuoteStream`/`useQuoteStatus` 基建)。
- **本期验收标准(研究门)**:不实现代码,只产出 probe 实测报告——候选源是否在 09:15-09:25 返回含虚拟未匹配/参考价的行;返回则开出 phase 实现,不返回则**正式 defer 并归档**,UI 保持现有诚实空态。

---

## 五、风险与开放问题

| 风险/问题 | 等级 | 说明与缓解 |
|---|---|---|
| **OQ-1 外部实时竞价源不可验证** | 高 | CHART-04 完全依赖「存在返回虚拟未匹配/参考价的窗口内行源」。本环境无源可测;必须 probe 实测,不做来源推测(STATE.md:73 既有纪律)。判定条件:源返回行时间戳 ∈ [09:15, 09:25:59] 且含 `auction_unmatched_volume`+`auction_virtual_price`(或可映射字段)→ 可行;否则 defer。 |
| **空湖 / 默认环境零数据** | 中 | CHART-01/02 在当前环境无点可画。缓解:UI 诚实空态 + 文档标注「需配置 auction 源并开启 EOD 竞价同步」;验收用 fixture/mock 而非真实数据。 |
| **窗口内行粒度歧义(末行 vs 求和)** | 中 | 湖内每 symbol 每日可能多行(`test_auction_sync.py:31-42` fixture 用 3 行;真实源粒度未验证)。默认「取末行(09:25 最终撮合)」并随行数/时间窗返回,避免「求和 = 多窗口重复累计」误读。若源是逐分钟累计快照,「末行」即最终撮合;若是独立行,求和才是总量——**需在接入真实源后按源语义钉死**,CHART-01 先按末行。 |
| **无价格列 → 不能画撮合价格曲线** | 中(语义) | 湖只有量/额,`amount/volume` 可得窗口内隐含均价但非独立价格列。若产品要「撮合价格曲线」,需先在写路径加价格列(源提供时),属 CHART-03 之外的增强。 |
| **CHART-03 改变 canonical 集的风险** | 低 | 扩为「4 必需 + 2 可选」是向后兼容(源不提供即列缺席);需防把派生列误入真实列求和/混排(既有 `auction_columns.py` 纪律 + Phase 23 UI 分组回归)。 |
| **storage/schema 面遗漏** | 低 | `_compute_storage`(`data.py:489-502`)/`_table_cache`(`data.py:33-44`)不跟踪 auction;CHART-01 若暴露覆盖天数,建议顺带把 auction 纳入 storage 统计(小改,非必需)。 |
| **Docs 漂移** | 低 | `docs/custom-data-source.md` 未对账 auction 数据集(20-RESEARCH.md:340 已记);CHART-01/03 落地时对账更新。 |

---

## 来源

- 代码:后端 `auction_sync.py` / `auction_columns.py` / `auction_probe.py` / `custom/provider.py` / `tencent_provider.py` / `chain.py` / `base.py` / `daily_pipeline.py` / `preferences.py` / `repository.py` / `api/data.py` / `screener.py` / `pool_hub.py` / `indicators/pipeline.py`(行号见正文);前端 `package.json` / `EChartsIntraday.tsx` / `StockPanel.tsx` / `StockPreviewDialog.tsx` / `useSharedQueries.ts` / `queryKeys.ts`。
- 规划:v2.0 `20-RESEARCH.md`(live probe `not_configured` 基线、tushare vs Level-2 口径、Docs 漂移)、`STATE.md`(defer 项与 `auction_virtual_fill` 语义 blocker)、`PROJECT.md`(v2.1 目标措辞「候选,研究确认」)。
- 本环境核实:仓库根 `data/` 目录 `ls`(无 `kline_auction`)、`find` 全树搜索(零命中)、`capabilities.json`(free 档无 auction 能力)。

*置信标注:代码与湖状态 = 直接观察(HIGH);外部源可行性/窗口粒度 = [INFERENCE]/不可验证(MEDIUM-LOW),按 OQ-1 判定条件执行。*
