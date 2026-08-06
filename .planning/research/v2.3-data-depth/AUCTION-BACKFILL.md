# 领域 A 研究:竞价/分钟历史数据可达性 (Auction & Minute Historical Availability)

**Research domain:** v2.3 数据纵深解锁 (Data Depth & Unlocks) — 领域 A 竞价/分钟历史回填可行性
**Researched:** 2026-08-06
**Researcher:** ResearcherV23A
**Confidence:** HIGH (代码 seam 逐行核验 + 上游 live probe 实测 + 与本地日K交叉验证) / MEDIUM (rate limit 与 2010 年完整覆盖为单点采样推断)

---

## 0. Verdict

**PARTIAL — 竞价历史 = OPEN(已实测可行,单 symbol 单请求可取满 248 交易日),分钟历史 = CLOSED(当前可用源最远仅 ~1 个月,无法回填 248 天)。**

- 竞价:上游 `xyz` MCP `stockdb_get_call_auction` 实测返回 2010 至今逐交易日 **09:25:00 最终撮合行**,单请求区间拉取 248 行全部命中(2025-07-29..2026-08-05),且 `current` 与本地 `kline_daily` open **三日期逐值相等**(11.41/12.30/11.19 = 11.41/12.30/11.19)→ 真实交易所集合竞价数据,非伪造。
- 分钟:实测 `xyz` 1m bar 仅回溯 ~21 个交易日(2026-07-07..08-04);`ifzq` 尾随窗口(~320 行 m5)、`sina` 尾随 1500 行、`free_stockdb` 仅近期;TickFlow 分钟K 需 pro+ 档(当前 key 实测 = Free,`kline.minute.*` ✗)。→ **分钟回填 248 天不可行,只能增量前向(现有 `sync_and_persist_minute` 已覆盖,上限 30 天偏好)。**

---

## 1. Q1 — 248 天 kline_daily 是怎么种出来的

**不是订阅,是带日期区间的历史 batch 拉取。** 证据链:

| 环节 | 证据 |
|---|---|
| 首次种子 | `backend/app/jobs/daily_pipeline.py:290-307` — `run_now` 无数据分支 `start_date = today - _td(days=365)` → `sync_and_persist_daily_batch(universe, repo, capset, start_date, end_date)`(首拉 1 年区间) |
| 增量补齐 | `daily_pipeline.py:266-288` — `latest_daily` 存在 → 从缺口起点到 today 的区间 batch(gap fill) |
| 区间 fetch | `backend/app/services/kline_sync.py:210` `sync_and_persist_daily_batch` → `sync_daily_batch`(`kline_sync.py:130-156`)`tf.klines.batch(chunk, period="1d", adjust="none", start_time=ms, end_time=ms, count=10000)` — **历史路径存在**,非 live 订阅 |
| 通道/档位 | `.env` `TICKFLOW_API_KEY=tk_9f8a…`;`data/capabilities.json` label=`Free`(free-api 服务器);`tiers.yaml` none/free 行 `kline.daily.batch {rpm:60, batch:100}` → 248 天经 free-api 批量日K 拉取 |
| 分区落盘 | `sync_and_persist_daily_batch` → `KlineRepository` 按 `date={d}` 分区原子写(`backend/app/tickflow/repository.py` `_atomic_write_parquet`) |

248 分区 (2025-07-29..2026-08-05) ≈ 一年交易日数,与「首拉 1 年」路径吻合。用户手动往前扩展另有 `backend/app/services/extend_history.py:102` `run_extend_history`(同样走 `sync_and_persist_daily_batch` 区间)。

## 2. Q2 — 同一或任何已配置源是否暴露历史竞价 K (09:15-09:25)

**现状:没有内置源声明 auction 能力;仅自定义源支持;data/data_sources/ 为空 → probe 必然 not_configured/fail_closed。**

- 内置源枚举:`backend/app/services/auction_probe.py:86-133` `_default_sources` — (a) 自定义源含 `auction` 数据集;(b) `_BUILTIN_CHAIN` 成员中 `capabilities.auction == True` 者。
- 能力声明:`backend/app/data_providers/base.py:19-26` `ProviderCapabilities.auction: bool = False` **默认关闭**,且全仓库没有任何 provider 把它置 True(`grep auction=True` 零命中;`xyz_provider.py:50-58`、`tickflow_provider.py`、`free_stockdb_provider.py` 均未声明)。
- 能力枚举无 auction 项:`backend/app/tickflow/capabilities.py:11-28` `Cap` 枚举只有 QUOTE/KLINE_DAILY/KLINE_MINUTE/INTRADAY/DEPTH5/WEBSOCKET/FINANCIAL/ADJ_FACTOR — **无 auction 标志**;`tiers.yaml` 无 auction 条目。
- 自定义源通道存在但未配置:`backend/app/data_providers/custom/config.py:10` `DatasetName` Literal 含 `"auction"`;`custom/provider.py:129-148` `get_auction(symbols, trade_date)` 已实现(把 `start_time=09:15 / end_time=09:26` 作为 start_param/end_param 传给上游);`data/data_sources/` 目录为空 → 无源。
- 写湖闸门:`backend/app/services/auction_sync.py:87-92` `can_sync_auction` / `:97-112` `sync_and_persist_auction` 均以 `resolve_auction_probe().status == available` 为准(fail-closed);`daily_pipeline.py:696-708` `_run_auction_sync` 双闸门(偏好 `auction_sync_enabled` 默认 False `preferences.py:129` + probe)。

**新发现(本研究会话实测):`xyz` MCP 端点 `http://8.138.149.215:7898/mcp` 暴露 `stockdb_get_call_auction`,2010 至今逐日 09:25 集合竞价撮合行——与项目任何既有 seam 尚未接线,但完全满足 canonical 列。**

## 3. Q3 — 任何源暴露历史分钟 K?

| 源 | 能力声明 | 历史深度(实测/代码) | 结论 |
|---|---|---|---|
| `xyz` (8.138.149.215:7898/mcp) | minute=True(`xyz_provider.py:50-58`) | `stockdb_get_price` frequency='1m' start/end → **2025-08-05 返回 0 行**;`stockdb_get_bars` unit='1m' count=5000 → 仅 21 个交易日 (2026-07-07..08-04) | 分钟历史仅 ~1 个月,不可回填 248 天 |
| `ifzq` (ifzq.gtimg.cn) | minute=True(`ifzq_provider.py:91-97`) | `mkline` 尾随窗口,count 上限 ~800(m5 实测 ~320)(`ifzq_provider.py:11-14, 239-246`) | 尾随窗口,无全历史 |
| `sina` (quotes.sina.cn) | minute=True | `datalen<=1500` 尾随(`ifzq_provider.py:20-23, 349-355`) | 尾随窗口 |
| `free_stockdb` (127.0.0.1:7899) | minute=True | 自托管,只存近期已同步数据(`xyz_provider.py:4-8` docstring 明言) | 近期 |
| TickFlow | minute=True(`tickflow_provider.py:31-38`) | `kline.minute.*` 需 pro/expert(`tiers.yaml`);当前 key Free(`data/capabilities.json` probe_log ✗×2) | 当前档位不可用 |

分钟链:`chain.py:20-26` `_BUILTIN_CHAIN["minute"] = [free_stockdb, ifzq, sina, xyz, tickflow]`;增量同步 `kline_sync.py:829` `sync_and_persist_minute`(偏好 `minute_sync_days` 上限 30,`preferences.py:98-99`)已是最优可达形态。

## 4. Q4 — READ-ONLY HTTP probe 记录(全部实测,2026-08-06)

**上游 1:`http://8.138.149.215:7898/mcp`(xyz JSON-RPC MCP;来源 `backend/app/data_providers/xyz_provider.py:30-38` 常量 + docstring「2005-present history」)**

| # | 请求 | 结果 |
|---|---|---|
| 1 | `POST tools/list` | 200 — 工具清单含 **`stockdb_get_call_auction`**【行情】通用集合竞价数据,时间范围 **2010 年至今(股票)**,盘后 15:00 更新、24:00 校对入库;参数 `security`(列表/必填)、`start_date`、`end_date`(必填)、`fields`(time/current/volume/money/b1-5_v/b1-5_p/a1-5_v/a1-5_p) |
| 2 | `call_auction {"security":["000001"],"start_date":"2026-08-05","end_date":"2026-08-05"}` | 200 — 1 行:`{'code':'000001','time':'2026-08-05T09:25:00','current':11.41,'volume':467700.0,'money':5336457.0,'a1_p':11.42,'a1_v':161500.0,…,'b5_p':11.37,'b5_v':75000.0}` |
| 3 | 同上,日期 `2025-08-05`(248 天窗内) | 200 — 1 行 `current:12.3 / volume:335300.0 / money:4124190.0`(历史可用) |
| 4 | 同上,区间 `2026-07-28..2026-08-03` | 200 — 每交易日 1 行(07-28/07-29 均 09:25:00) |
| 5 | 同上,日期 `2024-01-02` | 200 — 1 行(2010 至今声明可信,至少 2024 实测) |
| 6 | 同上,区间 `2025-07-29..2026-08-05`(全 248 天,单请求) | 200 — **248 行,首 2025-07-29T09:25:00 末 2026-08-05T09:25:00,全部 09:25:00**,耗时 1.6s |
| 7 | `security:["000001","600519","000858"]` 批量 | **错误 `{'error':'带宽限制批量请求，检测到 3 个代码'}` — 单请求仅限 1 symbol** |
| 8 | `stockdb_get_price {"security":["000001"],"start_date":"2026-08-05","end_date":"2026-08-05","frequency":"1m"}` | 200 — 0 行(该日 1m 未入库或参数组合不返回) |
| 9 | `stockdb_get_price …count:400,end_date:"2026-08-05",frequency:"1m"` | 200 — 400 行,10:51→15:00,含 08-03/08-05;**无 09:15-09:25 行** |
| 10 | `stockdb_get_bars …count:5000,unit:"1m",end_dt:"2026-08-05"` | 200 — 5000 行,覆盖 **21 个交易日 (2026-07-07..08-04)**;`get_price 1m 2025-08-05` → 0 行 |
| 11 | `stockdb_get_price {"security":["000001"],"start_date":"2025-08-05","end_date":"2025-08-05","frequency":"1m"}` | 200 — 0 行(1m 无 2025 数据) |

**交叉验证(竞价真伪):** 上游 `current` vs 本地 `data/kline_daily` open — 2026-08-05: 11.41=11.41 ✓;2025-08-05: 12.30=12.30 ✓;2026-07-29: 11.19=11.19 ✓ → 09:25 撮合价 = 当日开盘价,真实交易所口径。

**上游 2:`https://files.688798.xyz`(ext 概念/行业种子,`ext_presets.py:30` `_THS_BASE`)**

| # | 请求 | 结果 |
|---|---|---|
| 12 | `GET /ths/concepts.json` | 200,1.4MB,0.2s(与 ext_gn_ths 5542 行快照对应) |
| 13 | `GET /`、`/ths/kline.json`、`/ths/auction.json` | 200 静态页 / **404** ×2 — **纯静态文件宿主,无竞价/分钟行情端点** |

**auth/rate limit:** xyz MCP 无鉴权头;每请求强制单 symbol(带宽限制,见 #7);单 symbol 248 日区间请求 1.6s 无节流迹象(未做压力测试,未知 rpm 上限 → UNKNOWN)。688798.xyz 无鉴权、静态文件无速率限制。**TickFlow free-api 未直接探测**(SDK 封装,capabilities.json 已实证 Free 档无 minute)。

## 5. Q5 — backend/scripts/ 既有回填机械

`backend/scripts/` 现有:`cleanup_halt_days.py`、`probe_concept_drift.py`、`probe_phase13.py`、`provision_kronos.py`、`sync_kronos.py`、`verify_phase5_final_gate.py` — **无任何竞价/分钟历史回填脚本**。

仓库内可复用的回填/捕获机械(均在服务层):
- `backend/app/services/pool_backfill.py:30` `run_pool_backfill` — 快照回填:缺口日期集 = 分区差集(幂等跳过)、升序摊销、合作式取消(job_id failed → 提前停)、失败日记录继续、`origin='backfill'` provenance、绝不写 strategy_cache。**竞价回填 job 的直接模板。**
- `backend/app/services/extend_history.py:102` `run_extend_history` — 用户手动扩展日K:独立于 daily_pipeline、job_store 进度、view 刷新。模板二。
- `backend/app/services/kline_sync.py:829` `sync_and_persist_minute` — 分钟增量:date 分区 merge-upsert(`unique(subset=["symbol","datetime"], keep="last")`)+ 原子写;`fetch_minute_single`(:673)单日单标的 09:25-15:05 抓取(历史单日路径先例)。
- `backend/app/services/auction_sync.py:97` `sync_and_persist_auction` — 竞价写湖:probe 闸门 + 555..565 窗口谓词 + 分区 merge-upsert + `.tmp` 原子 rename。**回填写盘必须复用本路径。**

## 6. Q6 — 竞价/分钟回填 job 的既有 seam 设计

### 竞价回填(可行,推荐落地)

1. **provider seam**:给 `backend/app/data_providers/xyz_provider.py` 加 `get_auction(symbols, start_date, end_date)`(内部调 `stockdb_get_call_auction`,把响应映射为 `symbol/datetime/auction_volume/auction_amount/auction_virtual_price`),并把 `capabilities.auction = True`(`base.py:19-26` 字段已存在)。→ `auction_probe._default_sources`(auction_probe.py:103-114)与 `auction_sync._first_auction_provider`(auction_sync.py:75-84)自动发现,probe 转 `available`,既有 EOD `sync_and_persist_auction` 当日实时链路同步打通。
2. **回填 job 模块**:新 `backend/app/services/auction_backfill.py`(镜像 pool_backfill/extend_history:单飞、job_store、进度 emit、合作式取消)。循环:对每个 symbol 调 `get_auction(symbol, start, end)`(单请求取全区间的 09:25 行,~5500 symbols × 1 请求);逐日写盘**复用 `auction_sync.sync_and_persist_auction` 的写湖段**(555..565 窗口谓词 + 4+2 列 keep + 分区 merge-upsert + `_atomic_write_parquet` auction_sync.py:45-55/137-164)。
3. **诚实闸门**:回填**不复用**当日 probe(probe 只测最近交易日)。闸门 = (a) 源可达且 `call_auction` 对该区间返回窗口内行;(b) **只写 `kline_daily` 已存在的 date 分区**(竞价列是日K的补充面,日K无该日 → 不写,诚实覆盖对齐);(c) 单 symbol 失败 → 记入 failed 列表继续(镜像 pool_backfill),终态如实反映部分失败;源整体不可达 → 0 写 + fail-closed 记录。
4. **幂等**:分区 merge-upsert `unique(subset=["symbol","datetime"], keep="last")` 天然幂等(重跑只补差);原子写保证中断不损坏。
5. **触发面**:`POST /api/kline/auction/backfill`(只读+写湖,job_store 跟踪,单飞)——或并入 `extend_history` 的日K扩展语义(「扩展竞价历史」)。

### 分钟回填(不可行,记录关闭理由)

现有 `sync_and_persist_minute`(kline_sync.py:829)已是可达上限形态:增量从 `_latest_minute_datetime`(kline_sync.py:735)或 `now - days`(偏好上限 30 天,preferences.py:98-99)起拉;xyz 1m 仅 ~21 天、ifzq/sina 尾随、TickFlow 需 pro+ → **248 天分钟回填在现有源下 CLOSED**。若未来引入支持历史 1m 的源(如 TickFlow pro+ `tf.klines.batch(period="1m", start_time, end_time)` 已在 kline_sync.py:655-671 就绪),把 `minute_sync_days` 放宽即可,无需新 seam。

### schema 映射(上游 → canonical)

| 上游 `call_auction` 字段 | canonical 列 | 语义/验证 |
|---|---|---|
| `code` | `symbol` | 6 位代码,写盘时按 `kline_daily` 后缀补 `.SZ/.SH` |
| `time` (YYYY-MM-DDTHH:MM:SS) | `datetime` | 恒 09:25:00,落在 555..565 窗口谓词内 |
| `volume` (累计成交量,股) | `auction_volume` | 09:25 最终撮合累计量 |
| `money` (累计成交额,元) | `auction_amount` | 09:25 最终撮合累计额 |
| `current` | `auction_virtual_price`(OPTIONAL) | 与日K open 三日期逐值相等,实测验证 ✓ |
| — | `auction_unmatched_volume`(OPTIONAL) | **上游无未匹配量字段;仅 5 档盘口(a/b1-5_p/v)可近似,不得冒充真实未匹配量 → 列缺席(fail-closed,诚实缺列不 0 填)** |

注意:上游每 symbol 每日只有 **1 行(09:25:00)**,非逐分钟累计快照。这与 phase 26 的「末行聚合」读路径语义天然一致(26-RESEARCH.md D1 推荐 A);但 probe `_has_in_window_rows`(auction_probe.py:120-137)判定的是「窗口内行存在」,单行即可 available,语义自洽。

### 诚实缺口 + UNKNOWN

- **[实测缺口] 分钟历史 248 天不可得**(xyz 1m 仅 ~21 交易日;ifzq/sina 尾随;TickFlow 当前档位无 minute)→ 分钟回填 v2.3 正式 defer。
- **[实测缺口] `auction_unmatched_volume` 上游不提供** → 派生 `auction_unmatched_amount` 在真实源下仍不可派生(输入列缺席),读路径保持回退量比+金额强度。
- **[UNKNOWN] xyz 速率上限**:单 symbol/请求已实证,但并发/rpm 上限未压力测试;全市场 ~5500 symbols 回填耗时估计 1.5-3h(1.6s/请求量级),需在 job 内做限速(`tickflow/rate_limits.py` chunked/sleep_between_batches 既有)。
- **[UNKNOWN] 2010 至今完整覆盖**:2024-01-02 实测通过,更早日期未抽验;回填 job 应以「实测返回空/报错 → 该日跳过 + 记录」诚实处理,不预填充。
- **[UNKNOWN] 网络可达性漂移**:8.138.149.215 是公网直连 IP,MCP 端点若下线则全部闸门 fail-closed(设计已兼容:probe error → 不写湖)。
- **[INFERENCE] `current`=撮合价语义**:三日期与 open 相等实证,其余日期未抽验;写盘保留原始语义即可(列描述「09:25 撮合/虚拟成交价」)。

### REQUIREMENTS 级含义(v2.3 可承诺 vs defer)

**可承诺(竞价,数据纵深解锁主链路):**
- `kline_auction` 湖从 0 分区回填至与 `kline_daily` 对齐(248 交易日 × 全市场 A 股,单 symbol 单请求);`GET /api/kline/auction/history`(CHART-01)、策略真列分支(29 竞价验证)、`attach_auction_columns` 真列注入、复盘 Block 1 真实竞价活跃度(31)全部从条件式交付变为真实数据驱动。
- **BT-07 全量竞价回测 gate 解锁**(v2.2-REQUIREMENTS.md:60 — 需湖有足够历史分区):248 日竞价列 + 日K + 概念 PIT 可构成全量回测底座。
- probe 转 `available` 后,盘前监控/预览(PM-01)的 degraded 语义升级为真实竞价列(09:26 job 需竞价实时行——注意回填的是历史,当日 09:26 实时行仍依赖当日 probe+sync 链路,`sync_and_persist_auction` 当日路径已就绪)。

**defer(诚实声明):**
- 分钟历史回填 248 天(源不可达)——`kline_minute` 维持增量近期窗口(≤30 天偏好),BT-07 的 `minute_confirm_fn` 维度(若依赖历史分钟)随之受限。
- `auction_unmatched_volume` 真实未匹配量列(上游无此字段)——`auction_unmatched_amount` 派生在真实数据下依旧不可得,UI/复盘继续展示「估算缺位」诚实态。
- 多 symbol 批量竞价抓取(上游带宽限制单 symbol/请求)——回填 job 需逐 symbol 串行+限速,吞吐 ~1.6s/请求。

---

## 7. 证据索引(核心 file:line)

- `backend/app/jobs/daily_pipeline.py:290-307`(首拉 1 年区间)/ `:266-288`(gap fill)/ `:696-708`(竞价双闸门)/ `:564-583`(分钟增量)
- `backend/app/services/kline_sync.py:130-156`(日K区间 batch)/ `:597-671`(分钟链+`tf.klines.batch 1m`)/ `:673-698`(fetch_minute_single)/ `:829-926`(sync_and_persist_minute 分区 merge-upsert)
- `backend/app/services/auction_sync.py:33-41`(canonical 4+2 列)/ `:45-55`(原子写)/ `:87-92`(probe 闸门)/ `:97-164`(写湖:窗口谓词+merge-upsert)
- `backend/app/services/auction_probe.py:71-84`(_last_trade_date)/ `:86-133`(_default_sources 枚举)/ `:139-186`(resolve_auction_probe 判定)
- `backend/app/data_providers/custom/provider.py:129-148`(get_auction)/ `:150-167`(_normalize_auction 555..565)
- `backend/app/data_providers/xyz_provider.py:44-58`(capabilities minute=True, auction 未声明)/ `:107-147`(_price_frame start_date/end_date/frequency)
- `backend/app/data_providers/chain.py:20-26`(_BUILTIN_CHAIN 无 auction 键)
- `backend/app/data_providers/base.py:19-26`(ProviderCapabilities.auction 默认 False)
- `backend/app/tickflow/capabilities.py:11-28`(Cap 枚举无 auction)/ `data/capabilities.json`(Free 档 minute ✗)
- `backend/app/services/pool_backfill.py:30`(回填模板)/ `backend/app/services/extend_history.py:102`(扩展模板)
- `backend/app/services/preferences.py:89-99,117-119,129-140`(minute/auction 同步偏好)
- probe 实测:xyz MCP `http://8.138.149.215:7898/mcp` `stockdb_get_call_auction`(单 symbol、区间、2010-至今、09:25:00 行);`stockdb_get_price/bars` 1m 仅 ~21 交易日;`https://files.688798.xyz` 静态宿主无行情端点
