# Phase 27 研究:盘前股池 (Premarket Pool)

**Researched:** 2026-08-06
**Domain:** 盘前预览调度 (09:26) + `open_gap` 补算 seam + probe 今日窗口诚实语义 + 独立存储 + 前端盘前视图
**Confidence:** HIGH(现状/决策 = 逐行代码核验)/ MEDIUM(实时竞价源可行性 = 外部依赖, [INFERENCE])
**Requirements covered:** PM-01, PM-02, PM-03, PM-04

---

## 0. 用户约束

Phase 27 目录为空,无 `CONTEXT.md`(已 `ls -la .planning/phases/27-premarket-pool/` 核验);仓库根与 `.claude/` 均无 `CLAUDE.md`(已 glob 核验)。约束来自任务书(批次 context):

- 仓库根 `/home/orca/source/AthenaQuant`,分支 `gsd/v2.1-planning`(已 `git branch --show-current` 核验,HEAD `b29ccda`)
- **只读研究**:不修改任何代码/现有文档(除本 27-RESEARCH.md);不跑测试/构建
- **绝不触碰 `frontend/src/pages/Watchlist.tsx`**(git status ` M` 用户预存未提交改动;只可 grep 结构)
- 后端测试 `cd backend && .venv/bin/python -m pytest <file> -x -q`;前端验证 `cd frontend && npm run build` + Playwright e2e;**零新增运行时依赖**
- 诚实:不可验证的外部依赖标 `[INFERENCE]`;每条结论附 file:line 证据
- 需求:`.planning/REQUIREMENTS.md` PM-01..04;领域研究:`.planning/research/v2.1-depth/PREMARKET.md`

**与 PatternMapper27 的分工:** 本文件只做领域研究/决策/方案;`.planning/phases/27-premarket-pool/27-PATTERNS.md` 由 PatternMapper27 产出,零文件重叠。

<phase_requirements>
## Phase Requirements (PM-01..04)

| ID | Description | Research Support |
|----|-------------|------------------|
| PM-01 | 09:26 调度盘前预览 job,经 `run_all_with_hits(as_of=T)` 生成到独立存储 `premarket_results/date={T}/`,绝不写 `strategy_cache`/`screener_results` | §1.1 调度现状 / §1.2 数据帧来源 / §2 D1 / §2 D3 / §3 阶段 A |
| PM-02 | 盘前数据帧完整 — `open_gap` 补算(单一实现,无 EOD Pass 4 漂移);缺真实竞价列 fail-closed 到派生;除权日口径 fixture | §1.3 open_gap 缺口 / §2 D2 / §3 阶段 B / §5 测试映射 |
| PM-03 | probe 盘前诚实 — 今日 probe available → 竞价列读时注入;否则缺席 + degraded/窗口状态 | §1.4 probe 语义 / §2 D4 / §3 阶段 C |
| PM-04 | 前端盘前视图区别于 EOD — 窗口标注、诚实空态、DateNavigator 只列 EOD 快照日 | §1.6 前端现状 / §2 D5 / §3 阶段 D |

</phase_requirements>

---

## 1. 现状(代码证据,file:line)

### 1.1 调度现状 — 股池只做盘后 EOD,盘前只有维表同步

- `start_scheduler`(`backend/app/jobs/daily_pipeline.py:1010-1153`)注册 4 个工作日 job,全部 `CronTrigger(day_of_week="mon-fri", ..., timezone="Asia/Shanghai")`:
  - `pre_market_instruments` @ `inst_sched`(默认 09:10,`preferences.get_instruments_schedule()` `preferences.py:345-348`;上限 09:15,`set_instruments_schedule` `preferences.py:351-358`)— 只同步个股维表(`_instruments_task` → `run_instruments_sync`,`daily_pipeline.py:1024-1038`,`168-`)。
  - `daily_pipeline` @ `sched`(默认 15:30,`preferences.get_pipeline_schedule()` `preferences.py:329-332`)— 盘后管道,`_pipeline_then_refresh` 内 `with qs.paused(): run_now(...)`(`daily_pipeline.py:1042-1075`)。
  - `pool_eod_persist` @ 管道时刻 +5min(`_POOL_EOD_OFFSET_MIN = 5`,`daily_pipeline.py:963`;默认 15:35)— 股池 EOD 持久化。
  - `depth_finalize` @ 默认 15:02(`preferences.get_depth_finalize_time()` `preferences.py:404-407`)。
- `_pool_eod_persist`(`daily_pipeline.py:966-1008`):`as_of = svc.latest_date()`(`screener.py:704-707` → repo enriched 缓存日)→ `ScreenerService.run_all_with_hits(as_of, engine=...)` → `strategy_cache.write_cache` 刷新最新指针 → `pool_snapshot.persist_point_snapshot` 落冻结快照。无 app state / 无数据日 → 诚实 skip 不写任何文件(966-975)。
- **结论:** 股池在 T 日盘后 15:35 生成。T+1 日 09:30 前用户看到的最新池 = T 日(昨日)收盘池。盘前没有股池生成 job。

### 1.2 盘前数据帧来源 — live enriched 内存缓存是可行路径

- `ScreenerService.run_all_with_hits`(`screener.py:723-812`)只读一次 as-of 帧 `precomputed = self._load_enriched_for_date(as_of)`(`screener.py:740`),所有策略共享;历史策略惰性加载 `_load_enriched_history`(`screener.py:405-494`)。
- `_load_enriched_for_date`(`screener.py:245-297`)三级路径:
  1. **repo 最新日缓存**:`get_enriched_latest_asset(self.asset_type)` 返回 `(_enriched_cache, _enriched_cache_date)`,当 `cache_date == target_date` 即用(`screener.py:254-268`)— **盘前若 quote service 已 flush 今日 live enriched,`_load_enriched_for_date(today)` 直接命中此分支**。
  2. repo 历史缓存(`screener.py:269-285`)。
  3. 慢路径读 `kline_daily_enriched/date={as_of}/part.parquet`(`screener.py:286-296`);T 日分区盘前不存在 → 返回空帧。
- repo 缓存语义:`get_enriched_latest()`(`backend/app/tickflow/repository.py:906-918`);`flush_live_enriched_asset`(`repository.py:1819-1833`)在 quote flush 时覆写 `_enriched_cache = df.sort(["symbol"])` + `_enriched_cache_date = today`。
- quote service 盘前已在拉行情:`_market_phase()`(`quote_service.py:1099-1117`)有 `"preopen"` 阶段(09:15 ≤ t < 09:30);`_should_poll_for_phase("preopen")` 返回 True(`quote_service.py:1131-1139`)→ 09:15 起轮询线程拉全市场实时行情 → `_flush_live_enriched`(`quote_service.py:1459-1563`)经 `compute_enriched_today` 增量算今日 live enriched → flush 到内存缓存 + 写今日 enriched 分区。
- **因此 PM-01 的关键前提成立:** 09:26 时今日 live 帧已在 repo 内存缓存,`run_all_with_hits(as_of=T)` 能取到。冷启动/quote 未启用 → 缓存未焐热 → `_load_enriched_for_date(T)` 返回空 → `run_all_with_hits` 返回 `{}` → 诚实 skip(镜像 `_pool_eod_persist` 的 skip 语义)。

### 1.3 `open_gap` 缺口 — compute_enriched_today 不计算,竞价策略盘前静默空池

- `compute_enriched_today`(`pipeline.py:1250-1540`)覆盖:前复权调整(1286-1296)、`prev_close` 对齐(1301-1310)、change_pct/change_amount/amplitude(1312-1324)、EMA/MACD/MA/Boll/KDJ/ATR/RSI、量比(1410-1417)、极值/动量/波动/信号、涨跌停(1570+)… **全程无 `open_gap` 列产出**(已逐行核验 1250-1540 全函数)。
- 对比 EOD 全量路径 `compute_enriched` Pass 4(`pipeline.py:499-507`):`open_gap = when(prev_close>0).then(open/prev_close-1).otherwise(None)`;`prev_close` 来自 Pass 1 `close.shift(1)`(前复权昨收)。`open_gap` 在 `ENRICHED_STORAGE_COLS`(`pipeline.py:66`)与 `ENRICHED_COLUMNS_BY_CATEGORY["basic"]`(`pipeline.py:170`)。
- 竞价策略族几乎全部引用 `open_gap`(已 grep 核验):
  - `auction_allround.py:37,43`(缺列 `pl.lit(False)` 守卫)
  - `auction_alpha.py:34,59,67`(真列/派生双分支)
  - `auction_bullish.py:33`、`auction_early_star.py:35`、`auction_preopen_quant.py:33`
  - `auction_fast_grab.py:55-57`、`auction_intraday_confirm.py:40-43`、`t1_flash.py:36,42`、`strong_open.py:39`
- `run_all_with_hits` 对单策略异常 `except (ValueError, Exception): continue`(`screener.py:799-800`)→ 盘前帧缺 `open_gap` 时:有守卫的策略返回 `pl.lit(False)` 空池(auction_allround/t1_flash/auction_fast_grab/intraday_confirm),**无守卫的策略(auction_alpha 派生分支、auction_bullish、auction_early_star、auction_preopen_quant)抛 ColumnNotFoundError → 被静默吞掉,连空池都不列出**。这就是「静默空池」问题 — PM-02 必须补算。
- **补算 seam:** `compute_enriched_today` 在 prev_close 对齐后(≈`pipeline.py:1310`)插入与 Pass 4 逐字一致的公式即可;两路径都用「已复权 open / 已复权 prev_close」→ 正常日口径一致(见 D2)。

### 1.4 probe 盘前语义 — 探测日自动变 T,但当前无盘前主动调用点

- `resolve_auction_probe`(`auction_probe.py:139-181`):枚举候选源(`_default_sources` `auction_probe.py:86-118`)→ 取第一个 → `provider.get_auction([PROBE_SYMBOL], _last_trade_date())` → `_has_in_window_rows` 严格 [09:15:00, 09:25:59] 分类(`auction_probe.py:119-137`)→ `available`/`fail_closed`/`not_configured`/`error`。
- `_last_trade_date()`(`auction_probe.py:71-84`)= `kline_daily` 最大分区日期,否则今天。**盘前首次行情轮询后今日日线分区已存在 → 探测日自动变 T。** 探测本身日期动态,但当前无盘前主动调用点(probe 只被 auction_sync/attach_auction_columns/API 消费)。
- 真实竞价列读路径 `attach_auction_columns`(`auction_columns.py:89-150`)双闸门:第一闸门 probe available(`auction_columns.py:107-109`);第二闸门 `kline_auction/date={trade_date}/part.parquet` 存在且有行(`auction_columns.py:112-120`)。**盘前 T 日竞价分区不存在**(`auction_sync.sync_and_persist_auction` 只被盘后管道 Step 2.6 调用,`daily_pipeline.py:591-593,695-707`;`auction_sync.py:96-137`)→ 第二闸门盘前必失败 → 竞价列诚实缺席。
- 无内置竞价源:各内置 provider `capabilities.auction` 默认 False(`base.py:19-26`);只有配置了 `auction` 数据集的自定义源才可能 probe available(`custom/provider.py:129-160`)。**实时竞价源 = 外部依赖,本仓库不可验证([INFERENCE] MEDIUM)。**
- API:`GET /api/data/auction-probe` 30s TTL(`data.py:626-639`),`POST /auction-probe/redetect` 绕过缓存(`data.py:641-650`)。

### 1.5 存储契约 — 快照铁律 + strategy_cache 单 as_of,盘前不得混写

- `pool_snapshot.persist_point_snapshot`(`pool_snapshot.py:52-104`):`_SNAPSHOT_ROOT = "screener_results"`(`pool_snapshot.py:30-33`);`_DATE_RE = ^\d{4}-\d{2}-\d{2}$` 防路径穿越;`origin ∈ {eod, backfill, manual}`;payload 只含当次 results 与元数据,无 union 键(POOL-04);`.tmp + os.replace` 原子写。
- `strategy_cache.write_cache`(`strategy_cache.py:103-118`):单一 as_of 最新指针;同日合并 `today_ever_rows` 并集(`strategy_cache.py:138-151`)。**盘前若写 strategy_cache,会污染「最新」指针并与 EOD 同日合并「曾命中」**。
- `/api/pool/dates`(`pool.py:55-77`):source of truth = `screener_results/date=*` 含 part.json 者。`/api/pool/hub` 读 `strategy_cache`(`pool_hub.py:189-222`);`/api/pool/history` 读点快照(`pool_hub.py:225-267`)。历史回填 job `pool_backfill.py:30-101` 铁律「绝不 write_cache」,`origin="backfill"` — 是独立存储的先例。
- `api/screener.py run_all`(`screener.py:408-469`):`write_cache` 仅当 `is_latest`(`screener.py:442-453`);快照总是落盘(HIST-04 修复)。盘前预览必须走**独立存储**,镜像 backfill 的「不碰 strategy_cache」纪律。

### 1.6 前端现状 — 盘前诚实徽标钩子已预留

- `AuctionColumnStatusBadge`(`frontend/src/components/pool-hub/StockListTable.tsx:72-138`):消费服务端 `auction_columns` 声明 + `useAuctionProbe` + `useQuoteStatus`;`viewingToday && !tradingHours` 时渲染「盘前/休市 · 竞价窗口 09:15-09:25 未开始」(`StockListTable.tsx:134-137`)。**PM-04 可直接复用。**
- `quoteStatus` 暴露 `is_trading_hours`(严格 = `_is_continuous_trading()`,排除 09:15-09:30,`quote_service.py:1141-1157`)、`market_phase`(含 `"preopen"`)、`is_polling_window`(`quote_service.py:621-624`)。
- `PoolHubPage`(`frontend/src/pages/PoolHubPage.tsx`):`selectedDate == null` → `/api/pool/hub`(最新);非 null → `/api/pool/history`(PIT-1);`DateNavigator`(`components/pool-hub/DateNavigator.tsx:3-5`)dates = `/api/pool/dates` 白名单,非交易日物理不可达。`api.ts:752-766` PoolHubResponse 类型含 `available?`/`auction_columns?`;`api.ts:710-715` AuctionColumnsDecl。路由 `router.tsx:83` `pool-hub`。
- `main.py:779-785` `_GUEST_READ_GET_PATHS` 含 `/api/pool/hub`、`/api/pool/dates`、`/api/pool/history`、`/api/kline/auction/history` — **新盘前只读端点需加进此白名单**(guest 可读)。

### 1.7 无实时竞价源(界定 PM 第二档边界)

- `data/kline_auction/` 目录不存在(本环境空);内置源无 `auction` 能力;`auction_sync_enabled` 默认 False(`preferences.py:129-131`)。
- **结论:** 盘前真实竞价列默认不可用;PM 第二档(读时注入真实竞价列)= gate(自定义 auction 源 probe available),第一档(open_gap 派生预览)是交付。

---

## 2. 关键决策(选项/推荐/理由/风险)

### D1 调度时刻与互斥(PM-01)

| 选项 | 说明 | 风险 |
|---|---|---|
| **A. 固定 09:26(推荐)** | `CronTrigger(day_of_week="mon-fri", hour=9, minute=26, timezone="Asia/Shanghai")`,id=`_PREMARKET_JOB_ID`,经 `_run_tracked` 单飞包裹(镜像 EOD job 注册形,`daily_pipeline.py:1076-1088`) | 低 — 与 09:10 维表同步/15:35 EOD job 天然错开;`_run_tracked` 单飞兜底并发 |
| B. 偏好可配(镜像 instruments_schedule) | 新 `get_premarket_schedule()` + 设置 API | 中 — 需求写死 09:26;可配化增加偏好面;且 09:25 撮合定盘是硬边界,不宜让用户配早于 09:25 |
| C. 09:10 维表完成后触发 | 在 `_instruments_task` 末尾串行跑预览 | 中 — 09:10 早于 09:25 撮合定盘,open 仍是指示价;且把两个 job 耦合 |

**推荐 A。理由:** 09:26 位于 09:25 集合竞价撮合定盘后、09:30 连续竞价前,open 已定盘,`open_gap` 与 EOD 口径一致。`_run_tracked`(`daily_pipeline.py:722-770`)已提供 job_store 单飞 + 重任务执行槽互斥,与手动 run_all/EOD job 并发写防护一致(T-22-02-01)。**风险:** 09:26 时若 quote service 尚未完成首轮 flush(冷启动/禁用)→ `_load_enriched_for_date(T)` 空帧 → 诚实 skip(无文件),与 `_pool_eod_persist` skip 语义一致。**配套:** 注册形 grep 门禁(镜像 `test_pool_eod_job.py::test_pool_eod_job_registered_in_scheduler` 的常量 + `_run_tracked` + mon-fri cron 断言)。

### D2 `open_gap` 补算 seam(PM-02)

| 选项 | 说明 | 风险 |
|---|---|---|
| **A. 在 `compute_enriched_today` 补算(推荐)** | prev_close 对齐后(≈`pipeline.py:1310`)插入与 Pass 4 逐字一致的 `when(prev_close>0).then(open/prev_close-1).otherwise(None)`;单一实现,live 路径与 EOD 路径公式同源 | 低 — 两路径都用「已复权 open / 已复权 prev_close」;正常日因子相消,与 EOD 口径一致 |
| B. 预览服务 post-hoc 自算 | 预览 job 在 run_all 结果帧上再算 open_gap | 中 — 第二处实现,与 Pass 4 漂移风险;且 live 缓存帧仍缺列,其它消费方(监控引擎等)不受益 |
| C. 新共享函数双路调用 | 抽 `_open_gap_expr()` 给 Pass 4 与 today 共用 | 低 — 但 Pass 4 是列存在性门控(`if "open_gap" in want`),抽函数收益有限,改动面更大 |

**推荐 A。理由:** 单一实现 = 与 EOD Pass 4(`pipeline.py:499-507`)同公式,防双源漂移(需求原文)。`open_gap` 已在 `ENRICHED_STORAGE_COLS`(`pipeline.py:66`),`flush_live_enriched_asset` 写今日 enriched 分区时按存储列裁剪(`repository.py:1772-1773`)→ 补算列会随 live flush 落今日分区,盘后 EOD 重算时同列覆盖,无残留。**风险:除权日口径。** `compute_enriched_today` 的 prev_close = API 原始前收 × `_adj_factor`(`pipeline.py:1306-1310`),open = 原始开 × `_adj_factor`(`pipeline.py:1286-1296`)→ 因子相消 → `open_gap = raw_open / raw_prev_close − 1`;EOD Pass 4 用前复权 `close.shift(1)`(`pipeline.py:499-507`)。正常日 `raw_prev_close = raw_close_{T-1}` 且因子链一致 → 两路径相等。除权日(T)API 前收 = 交易所除权参考价,若因子链与参考价存在舍入/时滞差 → 两路径可能微偏(**LOW 概率,[INFERENCE]**)。**配套:** fixture 覆盖除权日(见 §5):构造 T 日 raw_prev_close ≠ 前复权昨收的帧,断言补算 open_gap 采用对齐后 prev_close 口径,与 EOD 公式逐位一致。

### D3 独立存储(PM-01)

| 选项 | 说明 | 风险 |
|---|---|---|
| **A. 新根 `premarket_results/date={T}/part.json`(推荐)** | 新 `premarket_snapshot.py`(镜像 pool_snapshot: `_DATE_RE` 校验 + `.tmp`+`os.replace` 原子写 + 无 union 键);payload 含 `window: "pre_open"`、`computed_at`、`provisional: true`、`as_of`、`results`、`probe`;独立 `list_premarket_dates()` 只读 helper | 低 — 与 `screener_results` 物理隔离;`/api/pool/dates` 不枚举此根 → DateNavigator 天然只列 EOD 日(PM-04) |
| B. `screener_results` + `snapshot_origin="premarket"` | 复用现有湖 | 高 — PM-01 明令不写 `screener_results`;`/api/pool/dates` 会列出盘前日 → 违反 PM-04;`origin` 白名单 `{eod,backfill,manual}` 需扩 |
| C. 写 strategy_cache 加 window 字段 | 最小侵入 | 高 — 污染 single-as_of 指针 + 与 EOD 同日 `today_ever` 并集;直接违反 PM-01 验收 3 |

**推荐 A。理由:** 镜像 backfill「不碰 strategy_cache」先例(`pool_backfill.py:5-6,46-47`),镜像 pool_snapshot 原子写模式;`strategy_cache.json` 的 `as_of` 与 `screener_results/date=*` 在盘前 job 后不变 → 单测 grep 锁死(PM-01 验收 3)。**风险:** 需新模块 + 新端点,但改动面小且全部复用现有 seam。**配套:** 存储层 `_DATE_RE` 严格校验(防路径穿越,镜像 `pool.py:22`);读侧端点只读零执行(POOL-03)。

### D4 probe 盘前语义(PM-03)

| 维度 | 推荐 | 理由/证据 |
|---|---|---|
| 探测日 | 沿用 `_last_trade_date()`(盘前自然 = 今日),**不加新参数**;加单测锁「盘前探测日 == T」(fixture 造今日 kline_daily 分区) | `auction_probe.py:71-84` 已取最大日线分区;盘前首轮行情后即 T。改签名反而引入第二个语义 |
| 可用判定 | 沿用 `_has_in_window_rows` 严格 [09:15:00, 09:25:59] 时间戳分类,绝不被源标签授予(T-16-01) | `auction_probe.py:119-137`;PM-03 验收 1 同词汇透传 |
| 降级表达 | 预览响应携带 `probe` 判定(`status/source/probed_at`,同 `/api/data/auction-probe` 词汇)+ `degraded: bool`;probe 非 available → `auction_columns.real == []` + `degraded: true` | 镜像 `attach_auction_columns` 双闸门 fail-closed(`auction_columns.py:107-120`);前端据此渲染「仅派生列」而非「竞价可用」 |
| 读时注入(第二档) | 今日 probe available 时,预览端点直接读竞价源(probe 的 fetcher)取今日窗口行 → 左联注入真实列;**不写 kline_auction 湖** | 盘前 T 日竞价分区不存在(auction_sync 仅盘后写,`daily_pipeline.py:591-593`),第二闸门必失败 → 只能「读源注入」;避免与 Step 2.6 唯一写湖路径分叉 |

**推荐:** probe 语义零改动(现有逻辑已诚实),预览 job/端点显式消费 `resolve_auction_probe().to_dict()`,把判定透传进响应;第二档注入 gate = `probe.status == available`,源不可用自动回落第一档。**风险:** 读源注入依赖外部实时源([INFERENCE] MEDIUM);`_has_in_window_rows` 要求源返回今日窗口行,09:30+ 行绝不入竞价列(回归锁死,镜像 `test_auction_probe.py` 诚实守卫)。

### D5 前端视图(PM-04)

| 选项 | 说明 | 风险 |
|---|---|---|
| **A. PoolHubPage 集成盘前预览 + 独立端点(推荐)** | 新 `GET /api/pool/premarket`(只读,200 语义);`selectedDate == null`(最新视图)时:今日预览存在且 EOD 今日快照未生成 → 渲染预览池 + 「盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿」标注;15:35 EOD 后回退 `/api/pool/hub` | 中 — 需前端「何时显示预览 vs 收盘」判定;复用 AuctionColumnStatusBadge 盘前分支 + `market_phase` 驱动 |
| B. 新独立页面 `/premarket` | 导航/路由新增 | 中 — 股池语义割裂;用户要在一个页面看「盘前预览 + 历史归档」 |
| C. hub 载荷内加 window 字段混排 | `/api/pool/hub` 直接返回预览 | 高 — 与 strategy_cache 单 as_of 语义冲突;15:35 切换需缓存双写 |

**推荐 A。理由:** 预览与 EOD 物理分离(独立端点 + 独立白名单,镜像 `pool_hub` 只读契约);`DateNavigator` 保持 `/api/pool/dates`(EOD 快照日),盘前预览永不进日期导航(PM-04 验收 3)。`AuctionColumnStatusBadge` 已预留 `viewingToday && !tradingHours` 分支(`StockListTable.tsx:134-137`),零新徽标。**风险:** 「最新」视图需判定优先级(预览 vs 收盘),建议服务端在预览端点回 `computed_at` + 前端以「今日预览存在 ∧ (现时盘前 ∨ 无今日 EOD 快照)」显示预览,否则 hub — 判定逻辑进前端 util + e2e 锁死。**配套:** `main.py:779-785` `_GUEST_READ_GET_PATHS` 加 `/api/pool/premarket`;guest 掩码(镜像 `pool.py:48-53`,`guest_masking.py:52-53`)。

### D6 两档交付边界(PM 第二档 gate)

| 档 | 交付内容 | Gate | 验证 |
|---|---|---|---|
| **第一档(交付)** | 09:26 预览 job + `open_gap` 补算 + 独立存储 + pre_open 诚实标注 + degraded/空态;竞价列诚实缺席 | 无外部依赖 | PM-01..04 验收 1/2 全绿 |
| **第二档(可选)** | 今日 probe available 时预览端点读源注入真实竞价列(`auction_volume/amount/volume_ratio`) | 自定义 auction 源在 09:15-09:25 返回今日窗口行(probe available) | 注入假 fetcher 强制 available 分支(镜像 `test_auction_probe.py` injectable);本环境无源 → [INFERENCE],不可端到端验证 |

**推荐:** 第一档为交付边界;第二档实现「注入 seam + 诚实降级」但标注 [INFERENCE] 依赖,无源时全链路走降级分支。**理由:** 与 REQUIREMENTS「Out of Scope — 盘前真实竞价列注入 (PM tier-2) Gated on today-probe available」逐字一致;零新增运行时依赖;PM-03 验收 2 的 injectable 测试天然覆盖两档切换。

---

## 3. 实现方案草案(文件级改动清单 + 顺序)

> 顺序原则:后端 seam(open_gap 补算)→ 存储 + job(PM-01)→ probe 语义透传(PM-03)→ 只读 API → 后端测试 → 前端(PM-04)→ e2e → 文档。零新增运行时依赖。

### 阶段 A:open_gap 补算(PM-02,风险集中点)

1. `backend/app/indicators/pipeline.py`
   - `compute_enriched_today` 在 prev_close 对齐块后(≈`:1310`)插入:
     ```python
     df = df.with_columns(
         pl.when(pl.col("prev_close") > 0)
           .then(pl.col("open") / pl.col("prev_close") - 1)
           .otherwise(None)
           .alias("open_gap"),
     )
     ```
     (与 Pass 4 `pipeline.py:499-507` 逐字一致,单一实现)
   - 回归确认:补算不改 EOD 路径(`compute_enriched` Pass 4 已存在,勿双源)。

### 阶段 B:盘前预览存储 + job(PM-01)

2. `backend/app/services/premarket_snapshot.py`(新)— 镜像 `pool_snapshot.py:52-104`:
   - `_PREMARKET_ROOT = "premarket_results"`、`_DATE_RE`、`_SCHEMA_VERSION`
   - `persist_premarket_snapshot(data_dir, as_of, results, probe, computed_at)` → 原子写 `premarket_results/date={as_of}/part.json`;payload `{as_of, computed_at, window:"pre_open", provisional:true, probe, strategy_version, snapshot_origin:"premarket", results}`;无 union 键
   - `load_premarket_snapshot(data_dir, as_of)` / `list_premarket_dates(data_dir)`(ISO desc)
3. `backend/app/jobs/daily_pipeline.py`
   - `_PREMARKET_JOB_ID = "premarket_pool_preview"` + `_premarket_preview(on_progress=None)`:`as_of = cn_today()`(北京时间,`market_time.py:26-28`)→ 经 `ScreenerService.run_all_with_hits(as_of, engine=...)` → 若 results:`premarket_snapshot.persist_premarket_snapshot`(**绝不** `strategy_cache.write_cache`/`pool_snapshot`);空帧/无 app state → 诚实 skip
   - `start_scheduler` 注册:`scheduler.add_job(lambda: _run_tracked(_premarket_preview, "premarket_pool_preview"), trigger=CronTrigger(day_of_week="mon-fri", hour=9, minute=26, timezone="Asia/Shanghai"), id=_PREMARKET_JOB_ID, misfire_grace_time=..., replace_existing=True)`
4. `backend/tests/test_premarket_job.py`(新)— 镜像 `test_pool_eod_job.py`:
   - 注册形 grep 门禁(常量 + `_run_tracked` + mon-fri cron + `timezone="Asia/Shanghai"`)
   - 写预览只落 `premarket_results/date={T}/part.json`;断言 `strategy_cache.json` 与 `screener_results/date=*` 不被改动
   - 无数据日/无 app state → 诚实 skip 不写文件

### 阶段 C:probe 透传 + 只读 API(PM-03)

5. `backend/app/services/premarket_view.py`(新,或并入 premarket_snapshot)
   - `build_premarket_payload(data_dir, as_of, repo)`:读预览快照 + `resolve_auction_probe().to_dict()` + 派生 `degraded`(`probe.status != "available"`)+ `auction_columns` 声明(镜像 `pool_hub._project_hub` 的 real/derived 推导,`pool_hub.py:104-117`)
   - 第二档(可选):probe available 时经 probe fetcher 读源今日窗口行 → 左联注入真实竞价列(不写湖);异常/无源 → 列缺席 + `degraded: true`
6. `backend/app/api/pool.py`(或新 `premarket.py`)
   - `GET /api/pool/premarket`(只读):`_AS_OF_RE` 校验;预览缺失 → 200 `{available: false, ...}`(镜像 `/api/pool/history` 空态,`pool.py:78-114`);guest 掩码(镜像 `pool.py:48-53`);`computed_at`/`window`/`provisional` 透传
7. `backend/app/main.py`
   - `_GUEST_READ_GET_PATHS` 加 `/api/pool/premarket`(`main.py:779-785`);若新模块则 `app.include_router(...)`(`main.py:846-878`)
8. `backend/tests/test_premarket_api.py`(新)— 空态 200 / as_of 非法 400 / guest 掩码 / POOL-03 式 AST 守卫(镜像 `test_pool_hub.py:853-918`);probe 注入假 fetcher 三态(not_configured/fail_closed/available → degraded 或 real 列,镜像 `test_auction_probe.py`)

### 阶段 D:前端(PM-04)

9. `frontend/src/lib/api.ts` — `PremarketResponse` 类型 + `api.poolPremarket: () => request<...>('/api/pool/premarket')`(镜像 `poolDates` `api.ts:2142`);`PoolHubResponse` 复用
10. `frontend/src/lib/queryKeys.ts` — `QK.poolPremarket: ['pool-premarket']`(镜像 `poolDates` `queryKeys.ts:44`)
11. `frontend/src/pages/PoolHubPage.tsx`
    - `selectedDate == null` 时:`poolPremarketQuery` 有今日预览且(现时盘前 ∨ 无今日 EOD 快照)→ 渲染预览池 + 窗口标注「盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿」;否则回退现 hub 流
    - 预览空态(`available: false`)→ 诚实空态(200 语义,镜像 `CalendarX` 分支 `PoolHubPage.tsx:146-150`)
    - 复用 `AuctionColumnStatusBadge`(`StockListTable.tsx:72-138`)驱动竞价徽标
12. `frontend/e2e/premarket.spec.ts`(新)— Playwright mock `/api/pool/premarket`:预览有数据 → 标注文案;`available:false` → 空态;`degraded:true` → 「仅派生列」徽标;15:35 场景 → 回退 hub
    - **绝不触碰 `Watchlist.tsx`**

### 阶段 E:验证与文档

13. 后端:`cd backend && .venv/bin/python -m pytest tests/test_premarket_job.py tests/test_premarket_api.py tests/test_auction_probe.py tests/test_pool_hub.py tests/test_pool_eod_job.py -x -q`(POOL-03 AST 守卫保持绿)
14. open_gap 单测:`tests/test_pipeline_today_open_gap.py`(新,或并入既有 pipeline 测试)— 正常日断言 `open_gap == open/prev_close−1`;除权日 fixture 断言口径一致
15. 前端:`cd frontend && npm run build` + `npx playwright test e2e/premarket.spec.ts`
16. 文档(可选):`docs/features.md` 补「盘前预览」小节(诚实标注词),`docs/strategy.md` 计数对账不漂移

---

## 4. 风险与开放问题

### 风险

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R1 | **实时竞价源不可得(第二档)**:盘前真实竞价列注入依赖自定义 auction 源在 09:15-09:25 返回今日窗口行;本仓库无内置源、湖为空 | 中 | 第二档 = gate(probe available);无源全链路走第一档降级;`[INFERENCE]` 标注,不阻塞交付 |
| R2 | **09:26 时 live 帧未焐热**:quote service 冷启动/禁用 → `_load_enriched_for_date(T)` 空帧 → run_all 空 results | 中 | 诚实 skip(镜像 `_pool_eod_persist` 966-975);文档标注预览依赖实时行情轮询开启 |
| R3 | **open_gap 除权日口径漂移**:API 原始前收 vs 前复权昨收在除权日可能微偏(因子链舍入/时滞) | 低 | D2 单一公式 + 除权日 fixture 锁口径;预览标注「基于前收,provisional」 |
| R4 | **盘前 vol_ratio_5d 失真**:`trading_minutes_elapsed=0`(`market_time.py:34-41`)→ `time_factor=1.0`(`pipeline.py:1410-1417`)→ 竞价量被当全天量 | 中 | 预览响应标注 provisional;pre_open 白名单策略已禁 `vol_ratio_5d`;`auction_alpha` 派生分支的 vol_ratio_5d 项在盘前语义失真 → 建议预览策略集默认过滤到 pre_open-safe 集(可经 `run_all_with_hits(strategy_ids=...)` 限定,`screener.py:760-766`) |
| R5 | **预览混入 EOD 存储**:若误写 strategy_cache/screener_results → 污染单 as_of 指针 + 日期导航出现盘前日 | 高 | D3 独立存储 + 单测 grep 锁死(strategy_cache.json as_of 与 screener_results/date=* 在盘前 job 后不变) |
| R6 | **前端「预览 vs 收盘」切换判定漂移**:15:35 EOD 后仍显示盘前预览 | 中 | 服务端透传 `computed_at` + `window`;前端以「今日预览存在 ∧ 现时盘前 ∨ 无今日 EOD 快照」判定;e2e 锁 15:35 回退 |
| R7 | **probe 探测日语义回归**:`_last_trade_date()` 盘前依赖今日日线分区存在,若行情未落盘探测日退回昨日 | 低 | 单测造今日分区断言探测日 == T;探测日只影响第二档注入,第一档不依赖 |
| R8 | **guest 泄露预览敏感量/价** | 低 | 预览端点 guest 掩码(镜像 `pool.py:48-53`);`main.py:779-785` 白名单纳入但掩码在前 |

### 开放问题

| # | 问题 | 现状 | 建议 |
|---|---|---|---|
| OQ-1 | 外部实时竞价源是否可得(第二档前置) | 本环境无源可测;内置源无 auction 能力;自定义源需配置 auction 数据集 | 不阻塞第一档;第二档 gate = probe available 实测 |
| OQ-2 | 盘前预览策略集:全部策略 or pre_open-safe 子集 | `run_all_with_hits` 默认全跑(PM-01 字面);`vol_ratio_5d`/`change_pct` 盘前为暂定/失真值 | 建议 job 默认全跑 + 响应 `provisional: true`,前端标注;若产品要「盘前可算策略」专属视图,加 `strategy_ids` 白名单配置(可后续迭代,不改协议) |
| OQ-3 | 09:26 预览与 09:10 维表同步的依赖 | 预览只读 enriched 内存缓存 + 历史,不依赖维表 | 无依赖;`_run_tracked` 单飞兜底并发 |
| OQ-4 | 盘前预览是否参与「今日曾命中」语义 | strategy_cache `today_ever_rows` 是 EOD union | 本期不合并;若要「盘前命中计入今日曾命中」需单独评审 union 语义 |
| OQ-5 | 预览保留期/清理 | 快照湖无保留期(全仓库未发现 kline_auction retention) | 本期不加;若磁盘敏感可后续加 retention |

---

## 5. Validation Architecture

`.planning/config.json`:`workflow.nyquist_validation: true`(启用)→ 本节必需;`security_enforcement: true` → §6。

### 后端

| 属性 | 值 |
|---|---|
| Framework | pytest(仓库既有;`.venv/bin/python -m pytest`) |
| 快速命令 | `cd backend && .venv/bin/python -m pytest tests/test_premarket_job.py tests/test_premarket_api.py -x -q` |
| 全量(相关) | `cd backend && .venv/bin/python -m pytest tests/test_premarket_job.py tests/test_premarket_api.py tests/test_auction_probe.py tests/test_pool_hub.py tests/test_pool_eod_job.py -x -q` |

### 前端

| 属性 | 值 |
|---|---|
| Framework | **无 vitest**;验证 = `npm run build`(tsc -b + vite build)+ Playwright e2e(`@playwright/test 1.61.1`) |
| e2e 命令 | `cd frontend && npx playwright test e2e/premarket.spec.ts` |

### 需求 → 测试映射

| Req | 行为 | 类型 | 命令 |
|---|---|---|---|
| PM-01 | 09:26 job 注册形 grep 门禁;写预览只落 `premarket_results/`;strategy_cache/screener_results 不变;无数据日诚实 skip | unit | `pytest tests/test_premarket_job.py -x -q` |
| PM-02 | `compute_enriched_today` 输出 `open_gap = open/prev_close−1`(fixture 数值断言);除权日口径一致;缺真实竞价列 → 派生/空池 | unit | `pytest tests/test_pipeline_today_open_gap.py tests/test_auction_columns.py -x -q` |
| PM-03 | probe 三态(injectable fetcher):not_configured/fail_closed → degraded + `auction_columns.real==[]`;available → real 列注入;09:30+ 行永不入竞价列 | unit | `pytest tests/test_premarket_api.py tests/test_auction_probe.py -x -q` |
| PM-04 | 预览池 + 窗口标注;空态 200;DateNavigator 只列 EOD 日;15:35 回退 hub | e2e(mock) | `playwright test e2e/premarket.spec.ts`;build 绿 |

### 回归面(必须保持绿)

- `test_pool_eod_job.py` / `test_pool_hub.py:853-918`(POOL-03 AST 守卫)— 新模块不得破坏
- `test_auction_probe.py` / `test_auction_columns.py` — 竞价域既有诚实守卫
- `test_guest_masking.py` — 掩码纪律(预览端点若触达 guest_masking 需回归)

### Wave 0 缺口

- [ ] `backend/tests/test_premarket_job.py`(新)— PM-01 注册门禁 + 独立存储 + skip
- [ ] `backend/tests/test_premarket_api.py`(新)— PM-03 三态 + 空态 + 掩码 + AST 守卫
- [ ] `backend/tests/test_pipeline_today_open_gap.py`(新)— PM-02 补算 + 除权日 fixture
- [ ] `frontend/e2e/premarket.spec.ts`(新)— PM-04 mock 三态

---

## 6. Security Domain

`security_enforcement: true`(`config.json`),ASVS Level 1。

### 适用 ASVS 类别

| ASVS | 适用 | 控制 |
|---|---|---|
| V2 Authentication | 是(guest/vip 掩码) | `request.state.reviewer_principal` 判定(镜像 `pool.py:48-53`) |
| V3 Session Management | 否 | 只读端点,复用既有会话 |
| V4 Access Control | 是 | guest 掩码:预览端点对 guest 剥离 `auction_columns` + 敏感列(镜像 `guest_masking.py:52-53`) |
| V5 Input Validation | 是 | `_AS_OF_RE = ^\d{4}-\d{2}-\d{2}$` 防路径穿越(镜像 `pool.py:22`);as_of 非法 → 400 |
| V6 Cryptography | 否 | 无敏感数据落盘/传输 |

### 威胁模式

| 模式 | STRIDE | 缓解 |
|---|---|---|
| 盘前预览误写 EOD 存储(污染 single-as_of / 日期导航) | Tampering | D3 独立存储 + 单测 grep 锁死(strategy_cache/screener_results 不变) |
| 路径穿越(as_of 注入) | Tampering | `_DATE_RE` fullmatch 后才拼路径(镜像 `pool_snapshot.py:52-104`) |
| 预览数据被标为收盘定稿/竞价可用(lookahead/误导) | Spoofing | `window:"pre_open"` + `provisional:true` + probe 判定透传 + 前端诚实词汇回归 |
| probe error 详情信息泄露 | Information Disclosure | `_ERROR_DETAIL_MAX = 200` 截断(`auction_probe.py:24-25`)已处理 |
| 盘前写湖(打破 Step 2.6 唯一写路径) | Tampering | 第二档读时注入不落 `kline_auction`;`_run_tracked` 单飞防并发写 |

---

## 7. Sources

### Primary(HIGH confidence — 本会话 Read 逐行核验)

- `backend/app/jobs/daily_pipeline.py:722-770,966-1008,1010-1153` — 调度/单飞/EOD job
- `backend/app/services/screener.py:245-314,723-812` — run_all_with_hits / 数据帧来源 / latest_date
- `backend/app/indicators/pipeline.py:1250-1540`(compute_enriched_today 全函数)、`:499-507`(Pass 4 open_gap)、`:66,170`(存储列)
- `backend/app/services/quote_service.py:1099-1157,1459-1563` — preopen 阶段 / live enriched flush / market_phase
- `backend/app/services/auction_probe.py:71-181` — 探测日 / 源枚举 / 窗口判定
- `backend/app/services/auction_columns.py:89-150` — 读路径双闸门
- `backend/app/services/auction_sync.py:76-144` — 写湖闸门(盘后 only)
- `backend/app/services/pool_snapshot.py:30-104` — 快照铁律 / 原子写
- `backend/app/services/strategy_cache.py:103-177` — single-as_of / today_ever union
- `backend/app/services/pool_hub.py:83-186` — 共享投影 / auction_columns 声明
- `backend/app/api/pool.py:22-114`、`backend/app/api/screener.py:408-469` — 只读端点 / run_all 写纪律
- `backend/app/tickflow/repository.py:906-935,1819-1833` — enriched 缓存 / flush
- `backend/app/services/preferences.py:129-131,329-358,404-419` — 调度偏好 / auction 开关
- `backend/app/market_time.py:31-48` — trading_minutes_elapsed(盘前 = 0)
- `backend/app/main.py:779-785,846-878` — guest 白名单 / 路由注册
- `backend/tests/test_pool_eod_job.py` — EOD job 契约 + 注册 grep 门禁样板
- `frontend/src/components/pool-hub/StockListTable.tsx:72-138` — AuctionColumnStatusBadge 盘前分支
- `frontend/src/pages/PoolHubPage.tsx`、`frontend/src/components/pool-hub/DateNavigator.tsx`、`frontend/src/lib/api.ts:710-766,2135-2147`、`frontend/src/lib/queryKeys.ts:41-45` — 前端视图/类型
- `backend/app/strategy/builtin/auction_*.py` — 竞价策略 open_gap 引用 + pre_open 白名单

### Secondary(MEDIUM confidence)

- `.planning/research/v2.1-depth/PREMARKET.md` — 领域研究(方案 B 推荐,已核实后采纳)
- `.planning/REQUIREMENTS.md` PM-01..04 / ROADMAP.md Phase 27 Goal & Success Criteria

### Tertiary(LOW confidence / [INFERENCE])

- 实时竞价源可行性(自定义 auction 源盘前返回今日窗口行)— 本环境不可验证
- 除权日 open_gap 微偏概率(因子链 vs 交易所参考价时滞)— fixture 覆盖

---

## Metadata

**Confidence breakdown:**
- 现状/调度/存储: HIGH — 逐行代码核验
- open_gap seam / probe 语义: HIGH — 公式与双闸门逐字核对
- 实时竞价源(第二档): LOW-MEDIUM — [INFERENCE],外部依赖

**Research date:** 2026-08-06
**Valid until:** 2026-09-05(调度/存储/前端契约稳定;若 Phase 28 触碰调度需复查)
