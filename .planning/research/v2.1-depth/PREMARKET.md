# 盘前股池 (09:30 前可用) 研究

**领域:** DATA-05 盘前股池 — 依赖实时竞价数据源, probe 门控哲学延续, fail-closed 诚实降级
**研究者:** ResearcherPremarket
**日期:** 2026-08-06
**总置信度:** MEDIUM-HIGH(现状结论 HIGH; 实时竞价源可行性为外部依赖, [INFERENCE] MEDIUM)

---

## 现状(代码证据)

### 1. 股池生成时机 — 盘后 EOD,非盘前、非"次日"

- 调度总览在 `backend/app/jobs/daily_pipeline.py:1-6` 模块 docstring:「09:10 盘前 — 同步个股维表 instruments (全量覆盖) / 15:30 盘后 — 日K同步 + 增量除权因子 + enriched 计算 + 刷新视图」。**盘前只有维表同步,没有股池生成。**
- `start_scheduler` (`daily_pipeline.py:1010-1085`) 注册 4 个工作日 job:
  - `pre_market_instruments` @ `inst_sched`(默认 09:10,`preferences.get_instruments_schedule()` `preferences.py:345-348`;上限 09:15,`set_instruments_schedule` `preferences.py:351-358`) — 仅个股维表。
  - `daily_pipeline` @ `sched`(默认 15:30,`preferences.get_pipeline_schedule()` `preferences.py:329-332`;下限 15:00,`set_pipeline_schedule` `preferences.py:335-342`) — 盘后管道。
  - `pool_eod_persist` @ 管道时刻 +5min(`_POOL_EOD_OFFSET_MIN = 5`,`daily_pipeline.py:962-963`,默认 15:35)— 股池 EOD 持久化。
  - `depth_finalize` @ 默认 15:02(`preferences.get_depth_finalize_time()` `preferences.py:404-407`)。
- `_pool_eod_persist`(`daily_pipeline.py:966-1008`):`as_of = svc.latest_date()` → `ScreenerService.run_all_with_hits(as_of, engine=...)` → 先 `strategy_cache.write_cache` 刷新最新指针,再 `pool_snapshot.persist_point_snapshot` 落冻结式点快照。

**结论:** 股池在 **T 日盘后 15:35** 生成,**基于 T 日完整收盘数据**(当日 enriched 需当日完整日线 bar)。它不是"次日"生成,而是**当日盘后**。因此 T+1 日 09:30 前,用户能看到的"最新股池"是 **T 日(昨日)收盘池**。

### 2. screener run_all 的数据依赖 — 当日 enriched 分区需要当日收盘数据

- `ScreenerService.run_all_with_hits`(`backend/app/services/screener.py:723-812`) 只读一次 as-of 帧 `precomputed = self._load_enriched_for_date(as_of)`(`screener.py:730`)。
- `_load_enriched_for_date`(`screener.py:245-297`):
  1. 优先 repo 内存最新缓存(`get_enriched_latest_asset`),`cache_date == target_date` 命中即用;
  2. 其次 repo 历史缓存;
  3. 慢路径直接读 `kline_daily_enriched/date={as_of}/part.parquet` 分区。
- enriched 存储列(`backend/app/indicators/pipeline.py:36-67` `ENRICHED_STORAGE_COLS`)含当日 OHLCV + `open_gap` + `quote_ts`;指标/信号由这些列即时计算。**T 日分区的完整指标必须等 T 日收盘 bar(close/volume/amount)落盘** — 这是盘后管道 15:30 才跑 enriched 的根本原因。
- 盘前 09:30,T 日 enriched 分区尚不存在;`_load_enriched_for_date(T)` 只可能在**盘中/盘前 quote service 已 flush 今日 live enriched 到内存缓存**时命中(cache 分支)。

### 3. 盘前已经具备的数据资产(现状缝隙)

- **实时行情(含今日 open/prev_close):已存在。**
  - `quote_service._market_phase()`(`backend/app/services/quote_service.py:1099-1117`)有 `"preopen"` 阶段(09:15 ≤ t < 09:30);`_should_poll_for_phase` 对 preopen 返回 True(`quote_service.py:1131-1139`)→ **盘前时段轮询线程已在拉全市场行情**。
  - `_fetch_full_market_quotes`(`quote_service.py:713-...`)→ `_process_full_market_records` → 写今日 `kline_daily` + `_flush_live_enriched`(`quote_service.py:1459-1563`)→ `compute_enriched_today` 增量计算今日 live enriched 并 flush 到内存缓存(`repo.flush_live_enriched_asset`)。live 帧含 `open`(竞价指示价/09:25 定盘价)、`prev_close`(API quote_extra)、`close`(=last_price)。
  - **缺口:** `compute_enriched_today`(`pipeline.py:1250-1540`)按递推式算 EMA/MA/MACD/KDJ/RSI/量比/信号,但**不计算 `open_gap`**。而竞价策略族几乎全部引用 `open_gap`(`auction_alpha.py:34,59,67`、`auction_fast_grab.py:55-57`、`auction_allround.py:37,43`、`t1_flash.py:36,42`、`auction_preopen_quant.py:33`、`auction_intraday_confirm.py:40-43`)。盘前 live 帧缺 `open_gap` → 这些策略在盘前要么 `pl.lit(False)` 空池(显式守卫),要么列缺失被吞异常静默空。**盘前预览必须补算 `open_gap`(open/prev_close−1)。**
  - 另:盘前 `trading_minutes_elapsed = 0`(`market_time.py:31-48` 开盘前=0)→ `compute_enriched_today` 中 `time_factor = 1.0`(`pipeline.py:1423-1429`)→ `vol_ratio_5d = 竞价量/前5日均量`,把竞价量当全天量,语义失真。盘前帧应优先 `auction_volume_ratio`(设计上就是"竞价量/前5日均量",PIT-safe,`auction_columns.py:52-83`),不展示盘前 `vol_ratio_5d`。

- **真实竞价列(auction_volume/amount/volume_ratio):盘前不可用。**
  - `auction_sync` 是**盘后管道 Step 2.6**:`_run_auction_sync`(`daily_pipeline.py:695-707`)仅在 `run_now`(15:30 盘后)内被调用,`auction_sync.sync_and_persist_auction` 把当日竞价行写 `kline_auction/date={d}/part.parquet`(`auction_sync.py:96-137`)。**没有实时/盘前竞价摄入路径。**
  - 读路径 `attach_auction_columns`(`auction_columns.py:89-150`)是 probe×分区双闸门:第二闸门要求 `kline_auction/date={trade_date}/part.parquet` 存在且有行(`auction_columns.py:111-115`)。盘前 T 日分区不存在 → **竞价列缺席**(诚实缺列,非 500)。
  - 数据环境佐证:仓库 `data/kline_auction/` 目录不存在(空),`data/screener_results/` 为空,`strategy_cache.json` 停在 `as_of=2026-07-31`。生产上竞价湖与快照均未启用。

### 4. probe 哲学现状 — 判定路径与盘前语义缝隙

- `resolve_auction_probe`(`backend/app/services/auction_probe.py:139-181`):枚举候选源 → 取第一个 → `provider.get_auction([PROBE_SYMBOL=000001], _last_trade_date())` → `_has_in_window_rows` 严格按 [09:15:00, 09:25:59] 时间戳分类 → `available`/`fail_closed`/`not_configured`/`error`。
- `_last_trade_date()`(`auction_probe.py:71-84`) = `kline_daily` 最大分区日期,否则今天。**盘前首次行情轮询后今日日线分区已存在 → 探测目标日会自动变成 T**;若自定义源在盘前能返回今日撮合行,probe 即 `available`。探测本身是日期动态的,但**当前没有任何东西在盘前主动调它**(probe 只被 auction_sync/attach_auction_columns/API 端点消费)。
- `_default_sources`(`auction_probe.py:86-113`)= 配置了 `auction` 数据集的自定义源 + 声明 `capabilities.auction` 的内置源。**grep 全部内置源(`tickflow/free_stockdb/ifzq/tencent/xyz/fixture`)均未声明 `auction=True`**(`base.py:25-26` 默认 False;各 provider capabilities 见 `tickflow_provider.py:20-26` 等)→ **真实竞价数据只可能来自操作员配置的自定义源**(`custom/provider.py:129-160` `get_auction`)。盘前实时竞价源可行性 = 外部依赖,本仓库无法验证([INFERENCE] MEDIUM)。
- API 层:GET `/api/data/auction-probe` 30s TTL(`api/data.py:626-639`),POST `/redetect` 绕过缓存(`api/data.py:641-...`)。
- **前端已预留盘前诚实状态钩子:** `AuctionColumnStatusBadge`(`frontend/src/components/pool-hub/StockListTable.tsx:72-122`)在 `viewingToday && !tradingHours` 时渲染「盘前/休市 · 竞价窗口 09:15-09:25 未开始」;quote status 暴露 `market_phase`(含 `"preopen"`)与 `is_trading_hours`(严格 = `_is_continuous_trading()`,排除 09:15-09:30,`quote_service.py:621-624,1141-1157`)。

### 5. 架构约束(盘前方案必须遵守的现有契约)

- **POOL-03 零执行权:** `GET /api/pool/*` 只读,`pool_hub.py` / `pool.py` 不 import 任何 broker/execution(`pool.py:1-12`;`tests/test_pool_hub.py` AST 守卫)。盘前方案必须是只读研究面。
- **快照铁律(POOL-04):** `persist_point_snapshot` 只落当次 results,无 union 键(`pool_snapshot.py:52-104`;`test_pool_eod_job.py` 回归锁死)。盘前快照不得把 `today_ever_rows` 混入。
- **strategy_cache 单 as_of 指针:** `/api/pool/hub` 读 `strategy_cache.json` 单一 as_of(`pool_hub.py:120-145`);`write_cache` 同日合并 `today_ever_matched/rows` 并集(`strategy_cache.py:98-173`)。**若盘前预览直接写 strategy_cache,会污染"最新"指针、并与 EOD 同日合并"曾命中"** — 推荐盘前预览独立存储(见方案 B)。
- **EOD 列一票否决(pre_open 白名单):** 策略 `auction_alpha.py:2-3`、`auction_fast_grab.py:8-9` 显式「pre_open 窗口禁 EOD 列 change_pct/close (lookahead)」;`auction_intraday_confirm.py:39-41`「EOD 列一票否决」。盘前预览的 as-of 帧语义必须与这一白名单一致。

---

## 候选方案对比

| 方案 | 数据依赖 | 工作量 | 风险 | 与现有架构契合 |
|---|---|---|---|---|
| **(a) 盘前即时 run_all + 竞价列实时注入** | 需**实时竞价源**(自定义 auction 源在 09:15-09:25 返回今日撮合行)+ 今日 open + prev_close | **高** — 新盘前 job + 今日竞价行实时摄入路径(写湖或内存注入)+ probe 语义改造(今日窗口)+ open_gap 补算 + 与 quote 轮询并发控制 + 缓存/快照标记 | **高** — 实时源可用性无法在本仓库验证([INFERENCE]);09:15-09:25 open 为指示价、09:25 才定盘 → 提前触发数据漂移;新增"盘前写湖"打破"auction 湖仅盘后写"现状;竞态面扩大 | 中 — 复用 `run_all_with_hits` + `attach_auction_columns` seam,但需新增实时摄入与并发防护,偏离现有 Step 2.6 单一写湖路径 |
| **(b) 盘前预览股池 + 诚实 pre_open 标注(推荐)** | 今日 open(quote 实时,09:26 已定盘)+ prev_close(昨日 enriched)+ 昨日 enriched 历史;竞价列**可选**:有实时源则注入,无则诚实缺席 | **中** — 新盘前 job(09:26)+ open_gap 补算(或预览服务自算)+ 独立预览存储(`premarket_results/date={d}/part.json` 或带 `window` 字段的姊妹快照)+ 前端诚实标注;竞价列注入复用现有 `attach_auction_columns`(无需新写湖路径,可做"读时注入") | 中 — 09:25 前 open 未定盘(用 09:26 调度缓解 + 诚实标注);close 相关指标为暂定值(close=开盘价);盘前 `vol_ratio_5d` 失真(需禁用/换 `auction_volume_ratio`);预览与 EOD 需显式区分(独立存储 + 窗口标注) | **高** — 全部复用现有 seam(`run_all_with_hits` / `strategy_cache` / `pool_snapshot` / hub 投影 / AuctionColumnStatusBadge 盘前分支);只新增调度 + 存储标记 + 前端标注;延续 probe fail-closed 哲学 |
| **(c) 不做实时,保持 EOD** | 无新依赖 | 低 | 低 — 但不交付"09:30 前可用"特性 | 高 — 现状 |

---

## 推荐方案 + 理由

**推荐 (b):盘前预览股池 + 诚实 pre_open 标注,分两档实现。**

- **第一档(无实时竞价源,默认):** 工作日 **09:26**(09:25 集合竞价撮合定盘后,北京时间)盘前 job 经 `ScreenerService.run_all_with_hits(as_of=today)` 生成预览池,数据 = quote 实时帧(今日 open 已定盘)+ 昨日 enriched 历史;**补算 `open_gap`**;竞价列诚实缺席(`auction_columns.real == []`),策略走派生分支(open_gap 等)或显式空池;预览写入**独立存储**(不与 `screener_results`/`strategy_cache` 混写),响应/前端标注 `window: "pre_open"` + `computed_at` + `provisional: true`。
- **第二档(有实时竞价源,可选):** 当自定义 auction 源在盘前返回今日 09:15-09:25 撮合行(probe 对今日 `available`)时,预览帧经现有 `attach_auction_columns` 双闸门注入真实竞价列(`auction_volume/amount/volume_ratio`);源不可用/未配置自动回落第一档(诚实标注,绝不静默填充)。此档**无需新增盘前写湖路径** — 竞价列在预览服务内"读时注入"(读源→左联帧),不落 `kline_auction` 湖,避免与 Step 2.6 唯一写湖路径分叉;EOD 时 Step 2.6 照常落湖供历史竞价列/竞价图消费。

**理由:**
1. **数据语义可靠:** 09:26 调度避开 09:15-09:25 指示价漂移窗口,open 已撮合定盘,`open_gap` 与 EOD 口径一致(open/prev_close−1)。
2. **诚实性最大:** 预览 = "盘前预览",显式标注非收盘定稿;竞价列存在性继续由 probe×分区双闸门服务端声明,09:30+ bar 永不标为竞价数据(T-16-01 延续)。
3. **最小侵入:** 零新增运行时依赖、零新写湖路径、复用全部共享核心;与 POOL-03/POOL-04 契约不冲突。
4. **渐进交付:** 无实时源即可交付第一档(高开预览本身有研究价值);有源自动升级第二档,不阻塞。

---

## 需求草案(编号 PM-01..,含验收标准)

### PM-01:盘前预览股池 job(调度 + 生成 + 独立存储)

盘前预览由独立调度 job 生成,写入独立存储,不覆写 `strategy_cache` 最新指针、不写 `screener_results` EOD 点快照。

- 工作日 09:26(Asia/Shanghai,09:25 撮合定盘后)触发;复用 `_run_tracked` 单飞(`daily_pipeline.py:722-`)与 JobStore 跟踪;无 app state / 无昨日 enriched → 诚实 skip,不写任何文件。
- 生成路径 = `ScreenerService.run_all_with_hits(as_of=today)`(今日 open 来自 quote 实时帧);预览结果写入独立分区,如 `data/premarket_results/date={as_of}/part.json`,payload 含 `window: "pre_open"`、`computed_at`、`provisional: true`、`as_of`、`results`。
- **验收:**
  1. 工作日 09:26(北京时间)后,盘前预览端点(见 PM-04)返回今日预览(`as_of=T`,`window="pre_open"`,`computed_at` 非空)。
  2. 无数据日(昨日 enriched 缺失 / 非工作日)→ 诚实 skip,`data/premarket_results/` 不产生新文件。
  3. 断言 `strategy_cache.json` 的 `as_of` 与 `data/screener_results/date=*` 在盘前 job 运行后**不被改动**(grep/单测锁死)。
  4. 调度注册形锁死:`_PREMARKET_JOB_ID` + `_run_tracked` 包裹 + `CronTrigger(day_of_week="mon-fri", hour=9, minute=26, timezone="Asia/Shanghai")`(镜像 `test_pool_eod_job.py::test_pool_eod_job_registered_in_scheduler` 的 grep 门禁写法)。

### PM-02:盘前数据帧完整性(open_gap 补算 + 诚实列语义)

盘前预览 as-of 帧必须能支撑 pre_open 白名单策略,且绝不把暂定值当收盘值。

- 预览帧每行含 `open_gap`(open/prev_close−1):若复用 `compute_enriched_today` live 帧,需在该路径补算 `open_gap`(当前缺口,`pipeline.py:1250-1540` 未算);或预览服务在帧上自算。
- 真实竞价列(`auction_volume/auction_amount/auction_volume_ratio`)仅在「probe 对今日 `available` **且** 源返回今日窗口行」时注入,否则列缺席(沿用 `attach_auction_columns` 双闸门语义,`auction_columns.py:89-150`);09:30+ 连续竞价 bar 永不进入竞价列。
- 暂定列语义:`change_pct`/`close` 及全部 close 派生指标在预览帧标注为 provisional(close = 开盘/定盘价,非收盘);盘前 `vol_ratio_5d`(time_factor=1.0 失真)不用于预览策略,pre_open 白名单策略继续禁 EOD 列。
- **验收:**
  1. 预览帧每行 `open_gap` 非空且 = `open/prev_close − 1`(fixture 断言数值)。
  2. probe 非 `available` / 源无今日行 → 预览响应 `auction_columns.real == []`,行内无 `auction_volume/amount` 键(诚实缺列,非 0 填充)。
  3. 有今日竞价行 → 行内出现真实竞价列且 `auction_columns.real` 声明它们;构造 09:30+ 行 → 永不进入竞价列(回归锁死,镜像 `test_auction_probe.py` 诚实守卫)。

### PM-03:probe 盘前语义(今日窗口实时判定 + fail-closed 降级)

- 盘前探测目标日 = **今日**(而非 `_last_trade_date` 的"最新日线分区"语义),判定沿用时间戳窗口规则(available 仅由 [09:15:00, 09:25:59] 观测行授予,T-16-01 不变)。
- 源不可用/未配置/仅 09:30+ 行 → 盘前预览**降级为派生列预览**(open_gap 仍有价值),响应携带 probe 判定 + `degraded: true`;绝不静默把 09:30 bar 标为竞价数据,也绝不把预览标为收盘定稿。
- **验收:**
  1. 盘前预览端点响应含 probe 判定字段(`status/source/probed_at`),与 `/api/data/auction-probe` 同词汇。
  2. 注入假 fetcher 强制各状态(镜像 `test_auction_probe.py` 的 injectable 模式):无源 → `not_configured` + derived-only 预览;仅 09:30+ 行 → `fail_closed` + derived-only;有窗口行 → `available` + real 列。
  3. 降级预览在响应中显式标记(`degraded: true`),前端据此渲染诚实标注(不渲染"竞价数据可用")。

### PM-04:前端盘前视图(诚实窗口标注 + 预览/EOD 分离)

- 股池页新增盘前预览展示:当查看日 == 今日且盘前预览存在时显示预览池,标注「盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿」;`market_phase == "preopen"` / `is_trading_hours == false` 驱动徽标(复用 `AuctionColumnStatusBadge` 盘前分支与 quote status,`StockListTable.tsx:72-122`)。
- 预览与 EOD 物理分离:独立只读端点(如 `GET /api/pool/premarket`)+ 独立白名单;15:35 EOD 后「最新」视图切回收盘池(现 `/api/pool/hub` 语义不变)。
- **验收:**
  1. 盘前时段(09:26-15:35)页面显示预览池 + 「盘前预览 · 非收盘定稿」标注;15:35 后显示收盘池(端到端 Playwright,或按现有无 vitest 约束以 `npm run build` + 浏览器验证)。
  2. 无预览日 → 诚实空态(200 语义,非 404),不伪装零池(镜像 PIT-2 无快照空态)。
  3. 任何 UI 均不把预览标为收盘定稿、不把 09:30 bar 标为集合竞价数据(镜像 UI-SPEC 诚实词汇回归)。

---

## 风险与开放问题

1. **实时竞价源可行性 = 外部依赖(本仓库不可验证):** 无内置 auction 源(`base.py:26` 默认 False;全部内置 provider 未声明 `auction=True`),`data/kline_auction` 为空。**判定条件:** 配置自定义 `auction` 数据集源且其在 09:15-09:25 返回今日行 → 方案 B 第二档成立;否则仅第一档(派生预览)。风险:MEDIUM。
2. **09:25 前 open 为指示价:** 09:26 调度缓解主路径;若产品允许用户手动提前触发预览,必须诚实标注「开盘价未定盘」(09:15-09:25 间数值会变)。
3. **盘前 vol_ratio_5d 失真:** `trading_minutes_elapsed=0` → `time_factor=1.0`(`market_time.py:31-48`,`pipeline.py:1423-1429`),竞价量被当全天量。预览帧必须禁用 vol_ratio_5d,改用 `auction_volume_ratio`(PIT-safe 分母)或明确不展示。
4. **`compute_enriched_today` 缺 `open_gap`:** 当前 live 帧无此列 → 竞价策略盘前静默空池。PM-02 必须补算;需回归确认补算不改变 EOD 路径(`compute_enriched` Pass 4 已有 open_gap,勿双源漂移 — 建议单一实现)。
5. **strategy_cache 单 as_of + today_ever union 语义:** 若盘前预览误写 strategy_cache,会污染「最新」指针并与 EOD 同日合并"曾命中"。PM-01 强制独立存储;若产品未来想要"今日曾命中含盘前",需单独评审 union 语义。
6. **并发与竞态:** 盘前 job 与 quote 轮询同写 `kline_daily`/enriched — 复用 `_run_tracked` 单飞 + `quote_service.paused()`(管道已有先例,`daily_pipeline.py:1040-1057`);预览服务若读时注入竞价列,需与 Step 2.6 盘后写湖并发无冲突(读源不落湖,天然解耦)。
7. **前端徽标粒度:** `is_trading_hours` = `_is_continuous_trading()`(排除 09:15-09:30,`quote_service.py:621,1141-1157`),`market_phase` 另有 `"preopen"` 字段 — PM-04 应消费 `market_phase` 而非仅布尔,以区分"盘前竞价窗口进行中"与"休市"。
8. **除权日 prev_close 对齐:** 09:26 的 `open_gap` 使用 quote 原始 prev_close;若 T 日有除权事件,盘后 enriched 的 prev_close 复权对齐可能使 EOD `open_gap` 与盘前预览不一致 — 预览需标注「基于原始前收」或与复权口径对齐后计算([INFERENCE] LOW 概率,但需在 PM-02 验收中覆盖 fixtures)。

---

## 来源(代码证据索引)

- `backend/app/jobs/daily_pipeline.py:1-6,695-707,722-770,962-1008,1010-1085` — 调度/盘前维表/盘后管道/EOD job
- `backend/app/services/screener.py:245-297,299-317,704-719,723-812` — run_all 数据依赖
- `backend/app/indicators/pipeline.py:36-67,1250-1540` — enriched 存储列 / compute_enriched_today(缺 open_gap)
- `backend/app/services/quote_service.py:1099-1157,1459-1563,621-625` — preopen 阶段 / live enriched / market_phase
- `backend/app/services/auction_sync.py:96-137` — 盘后竞价写湖
- `backend/app/services/auction_columns.py:89-150` — 竞价列读路径双闸门
- `backend/app/services/auction_probe.py:71-84,86-118,139-181` — probe 判定
- `backend/app/data_providers/base.py:25-26` + 各 provider capabilities — 无内置 auction 源
- `backend/app/services/pool_hub.py:120-145`;`pool_snapshot.py:52-104`;`strategy_cache.py:98-173` — hub 投影/快照铁律/缓存单 as_of
- `backend/tests/test_pool_eod_job.py` — EOD job 契约 + 注册 grep 门禁样板
- `frontend/src/components/pool-hub/StockListTable.tsx:72-122` — 盘前徽标钩子
- `backend/app/api/data.py:626-644` — probe API 30s TTL
