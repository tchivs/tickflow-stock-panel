# 逐日全量存档模式(非回放) 研究

**领域:** 历史股池逐日全量存档 / 批量回填 / 非回放查询
**研究日期:** 2026-08-06
**结论速览:** 现有冻结式点快照机制(POOL-04/05/06)已提供「按日分区 + 冻结 + 零 union 污染」的正确存档载体;缺口不是存储格式,而是「只有 EOD 前向累积、无历史补齐」的生成策略。推荐在**现有快照湖上补一个用户触发的批量回填 job**,复用 `run_all_with_hits` + `persist_point_snapshot` 单条代码路径,**但绝不复用 EOD job 的 `write_cache` 步骤**(会污染 single-as_of 最新指针),并新增 `snapshot_origin` 字段区分「EOD 当日归档」与「事后回填重算」以维持诚实性。存储与查询接口均零改动。

---

## 现状(代码证据)

### 1. 冻结式点快照已逐日,载体正确(POOL-04)
- `pool_snapshot.persist_point_snapshot` (`backend/app/services/pool_snapshot.py:50-99`): 原子写 `screener_results/date={as_of}/part.json`(temp + `os.replace`, 无 .tmp 残留);payload 仅含 `as_of` / `computed_at` / `strategy_version` / `snapshot_type:"point"` / `schema_version:1` / `results`(`pool_snapshot.py:78-87`),**结构上无 `today_ever_rows` / `today_ever_matched` union 键**(模块 docstring 铁律)。
- `as_of` 严格校验 `^\d{4}-\d{2}-\d{2}$` 防路径穿越(`pool_snapshot.py:30-31,58-61`);非法 as_of → persist 抛 ValueError / load 返回 None。
- `load_point_snapshot` (`pool_snapshot.py:102-117`): 文件不存在/解析失败 → None(诚实空态)。
- `list_snapshot_dates` (`pool_snapshot.py:120-133`): source of truth = `screener_results/date=*` 分区 glob 中含 `part.json` 者,ISO desc;无 `part.json` 的目录被排除;root 不存在 → `[]`。
- `strategy_fingerprint` (`pool_snapshot.py:135-149`): 排序后的策略 meta + 各策略源文件内容 sha256[:16];meta 或源码变化 → 新指纹,**历史快照不被静默重解释**(回填快照的指纹 = 回填时刻策略集,见「风险」)。

### 2. `strategy_cache.json` 是 single-as_of **最新指针**,与历史回填冲突
- `strategy_cache.read_cache` / `write_cache`(`backend/app/services/strategy_cache.py:63-118`): `strategy_cache.json` 语义是「最新一天」——`_write_cache_locked` 同 as_of 时对 `today_ever_rows` 做 union 合并,换日则重置,payload `as_of` = 本次写入日(`strategy_cache.py:121-170`,尤其 L138-142、L161)。
- **关键风险(研究核心发现):** 用**历史 as_of** 调 `write_cache` 会把 `strategy_cache.json` 的 `as_of` 改成过去日期,`GET /api/pool/hub` 的 single-as_of 契约(`pool_hub.build_pool_hub`, `pool_hub.py:173-181`「始终回显缓存日期」)就会回显陈旧日期。v2.0 实测就出现过「陈旧 as_of=2026-07-31 → EOD write_cache 修复为 2026-08-04」(22-02-PLAN 事实 3)。→ **任何回填路径都绝不能把 EOD job 的「先 write_cache 再 persist」顺序照搬过来**。
- 附带发现: 手动 `POST /api/screener/run_all` 对**任意历史 as_of** 也会 `write_cache`(`api/screener.py:443-447`),同样存在指针污染隐患(既有行为,本领域范围外,但回填设计必须绕开)。

### 3. EOD job 只向前生成,绝无回填(OQ-1 决策已编码)
- `_pool_eod_persist`(`backend/app/jobs/daily_pipeline.py:966-1010`): `ScreenerService(repo).latest_date()` → `run_all_with_hits(as_of, engine=app_state.strategy_engine)` → `strategy_cache.write_cache`(刷新最新指针)→ `pool_snapshot.persist_point_snapshot`;无数据日 / 无 app state → 诚实 skip 不写任何文件。
- 注册形(`daily_pipeline.py:1078-1087`): `mon-fri` cron、管道时间 +5min 偏移、`misfire_grace_time=3600`、`replace_existing=True`,包 `_run_tracked` 单飞(`daily_pipeline.py:722-752`)防与手动 run_all 并发写。
- **OQ-1 DECISION(v2.0 22-02): 不做首日一次性全量回填;EOD 只向前生成,历史缺口由用户手动 run_all 补齐。** grep 证实 `daily_pipeline.py` 与全仓无 pool 回填/backfill job;v2.0-MILESTONE-AUDIT 将「无回填 job (OQ-1 采纳)」列为**有意决策非缺陷**。

### 4. 手动 run_all 已支持任意 as_of,且是「缺口的既有补法」
- `POST /api/screener/run_all`(`backend/app/api/screener.py:408-465`): `body.as_of` 任意日期 → 共享核心 `ScreenerService.run_all_with_hits`(`screener.py:437`)→ `write_cache`(`:445`)→ `persist_point_snapshot`(`:450-458`)。
- `run_all_with_hits`(`screener.py:723-803`): 一次读取目标日 enriched,所有策略共享;`strategy_ids` 空 → 全部(PRESET + engine);空列表 → `{}`;历史策略惰性加载 `_load_enriched_history`(PIT: 只含 <= as_of)。
- 历史日期读路径(`screener.py:245-297`): 最新日走 repo 内存缓存;历史日走慢路径——读 `kline_daily_enriched/date={d}/part.parquet`(14 列)+ `_compute_enriched_full` 即时重算指标(`screener.py:354-385`,加载目标日**前 ~150 天 warmup**)。→ 回填单日成本显著高于 EOD(后者命中缓存)。

### 5. 数据现状:247 个 enriched 日,0 个快照(缺口即「全量存档」要补的东西)
- `data/kline_daily_enriched/` **247 个分区**(至 2026-08-04),每区 `part.parquet` ~200 KiB、~5291 行;总量 **~51 MiB**(实测)。
- `data/screener_results/` **0 个快照**(空占位)。→ 当前历史股池**只能回放/手动补**,无逐日存档。`GET /api/pool/dates` 返回 `{dates:[], count:0}`。
- `data/kline_auction/` 0 分区(sandbox;probe 门控的逐日 hive 湖已存在——**竞价数据本身已是按日存档**,不属本领域要新建的存储)。
- **无交易日历**: 日期枚举一律用 `date=*` 分区 glob(daily_pipeline.py:386-390 既有模式);全仓无 list_enriched_dates helper(需 glob 自行枚举)。
- **无任何 pool backfill/archive/snapshot_origin 代码**(grep 证实)。

### 6. 查询契约现状(回填后零改动即可用)
- `GET /api/pool/dates`(`api/pool.py:55-65`): 列出含 `part.json` 的日期。
- `GET /api/pool/history?as_of=`(`api/pool.py:79-110`): 快照缺失 → 200 `available:false` 空态;存在 → 与 `/hub` 同形状投影(`build_pool_hub_snapshot`, `pool_hub.py:204-221`)。
- 前端 PoolHubPage 已按 `selectedDate` 切 `QK.poolHistory(d)`(`frontend/src/pages/PoolHubPage.tsx:21-38`),DateNavigator 白名单 = `/api/pool/dates`。→ 回填完成后前端无需改动即可浏览全量历史。

---

## 候选方案对比

| 方案 | 工作量 | 风险 | 与现有架构契合 |
|------|--------|------|----------------|
| **A. 现有快照湖 + 批量回填 job** | 中(1 个后台 job + 1 个触发端点 + origin 字段 + 测试) | **低**;主风险 = 误写 `write_cache` 污染指针(可设计规避)与历史慢路径耗时 | **高**。复用 `run_all_with_hits`(screener.py:723)与 `persist_point_snapshot`(pool_snapshot.py:50)单条代码路径;读路径(/dates、/history)与 POOL-03 零执行权 AST 守卫全部不变 |
| **B. 新增独立归档层 `pool_archive/date=*`** | 高(新存储 + 新写路径 + 双源读合并 + 迁移) | **中-高**。双 storage = 双 source of truth,违背「单一事实源」;`/history` 需仲裁读哪个;存储翻倍(快照 ~0.3-2 MiB/日,247 日 ≈ 79-693 MiB,见风险) | **低**。POOL-04 已把 `screener_results/` 定为唯一快照湖;再造一层是重复建设。「EOD 归档 vs 手动重算」的区分用字段(origin)表达即可,不必用目录 |
| **C. 纯查询聚合(请求内回放)** | 低(仅改 history 触发 run_all) | **高**。请求内 run_all 卡页面——正是 POOL-06「自给自足、首个历史日请求不被阻塞」要消灭的问题(v2.0 成功标准 3);回放语义(用今日代码重算历史)与「逐日全量存档」的目标直接冲突 | **低**。与 POOL-06 反向 |

**补充说明(方案 A 的内部选型):**
- **存储位置:** 沿用 `screener_results/date={as_of}/part.json`(与 EOD 同一湖),**不建**独立归档层。理由: 快照 payload 已冻结、按日分区、原子写、无 union 键——「存档载体」本就正确;缺口只是「没跑」。
- **触发方式:** 用户触发(如 `POST /api/pool/backfill`,镜像 `extend_history` 的手动触发模式 `app/services/extend_history.py`)而非 EOD 内隐式回填、也非启动即回填。理由: 保留 OQ-1 的「不静默写盘」护栏;247 日 × 秒级-数十秒 ≈ 30-120 分钟后台批,不应藏在每日 cron 里。
- **写路径纪律:** 回填 job 对每个历史日只做 `run_all_with_hits(d)` + `persist_point_snapshot(d, ..., origin="backfill")`,**绝不调 `write_cache`**(见现状 §2)。

---

## 推荐方案 + 理由

**推荐:方案 A + 三个补充**(`snapshot_origin` 字段、`backfill_needed` 缺口信号、用户触发后台 job 与护栏)。

**理由:**

1. **存档载体已存在且正确,不应重建。** POOL-04 的冻结快照(按日 hive 分区、原子写、携带 `as_of`/`computed_at`/`strategy_version`/`schema_version`、无 union 键)就是「逐日全量存档」的存储格式。v2.1 要补的是**生成策略**:把「EOD 只向前 + 历史缺口手动补」升级为「缺口可一键批量补齐」,把 `screener_results/` 从「0 个快照」变成「覆盖全部 247 个 enriched 日」。
2. **单条代码路径保证 PIT 与契约一致。** 回填逐日调用与 EOD/手动 run_all 完全相同的 `run_all_with_hits`(screener.py:723)——单日 enriched 分区是冻结的,历史日重算天然 PIT(读 `<= as_of` 分区);`persist_point_snapshot` 输出与 EOD 快照**同 schema、同形状**,`/api/pool/history` 与 `/api/pool/dates` 零改动即可消费。这直接满足「逐日完整重建与查询」。
3. **诚实性靠显式 provenance,不靠第二份存储。** 回填快照与 EOD 快照有一个不可消除的语义差异:回填快照的 `strategy_version` 是**回填时刻**的策略集,而非 `as_of` 时刻的——这是「重算/回放」语义,不是「当日归档」语义。用 `snapshot_origin: "eod" | "backfill"` 字段显式标注(v2.0 已有 `snapshot_type:"point"` 先例),读侧可透传/过滤,既不混称也不造假;无需为此建独立目录。
4. **OQ-1 是「补充」而非「推翻」。** OQ-1 的合理内核是 v2.0 不做全量回填(避免首日阻塞、静默写盘、非产品必需)。v2.1 的目标特性「逐日全量存档模式(非回放)」**正是**要求历史全覆盖——所以补回填 job 是执行目标,不是翻案。OQ-1 的三条护栏(不阻塞请求、不静默写盘、保持 POOL-03 零执行权)全部保留。
5. **存储与查询零破坏。** 快照 ~0.3-2 MiB/日 [INFERENCE](见风险),247 日 ≈ 79-693 MiB,个人部署可接受;enriched 湖本身已 51 MiB。查询端 `/history`、`/dates`、前端 DateNavigator 全部不变,零新增运行时依赖(stdlib + 既有 polars/apscheduler)。

---

## 需求草案

### HIST-01: 批量回填 job — 历史缺口一键补齐,零指针污染

**作为** 股池使用者,**我** 能触发一次后台回填,让所有「enriched 有数据但无冻结快照」的历史交易日都生成冻结快照,从而无需逐日手动 `run_all`。

**验收标准:**
1. 存在用户触发的回填入口(如 `POST /api/pool/backfill`,可传 `max_days`/`start`/`end` 边界;不设则枚举全部缺口)。
2. 回填日期集 = `kline_daily_enriched/date=*` 分区(glob,`daily_pipeline.py:386-390` 既有模式)减 `screener_results/date=*` 含 `part.json` 者(`list_snapshot_dates`, `pool_snapshot.py:120`);已存在快照的日期被跳过(幂等)。
3. 对每个目标日调用 `ScreenerService.run_all_with_hits(d)` + `pool_snapshot.persist_point_snapshot(d, ...)`;**绝不调用 `strategy_cache.write_cache`**(AST/grep 守卫锁死,防止污染 `strategy_cache.json` 的 single-as_of 指针,`strategy_cache.py:121-170`)。
4. 回填走后台 job 基础设施: `job_store` 单飞(`pipeline_jobs.py`) + `_run_tracked` 式包裹 + 进度回调(`stage/pct`),与 `pool_eod_persist`(`daily_pipeline.py:966`)同构;可被 `POST /api/pipeline/jobs/{id}/cancel` 取消;请求内零阻塞。
5. 回填完成后 `GET /api/pool/dates` 返回全部缺口日期,`GET /api/pool/history?as_of=` 对每个已回填日返回 `available:true` 的正常投影。

### HIST-02: 快照来源诚实性 — `snapshot_origin` 显式区分 EOD 归档与回填重算

**作为** 研究员,**我** 在浏览历史股池时能分辨「该日 EOD 当日归档」与「事后用当前策略集重算」,避免把回填快照误读为当日冻结事实。

**验收标准:**
1. `part.json` payload 新增 `snapshot_origin: "eod" | "backfill"` 字段(schema_version 保持 1 或按向后兼容策略递增并让 `load_point_snapshot` 容错缺失字段,默认按 `"eod"` 处理旧文件)。
2. `_pool_eod_persist`(`daily_pipeline.py:966`)写入 `origin="eod"`;回填 job 写入 `origin="backfill"`;手动 `run_all`(`api/screener.py:450`)维持现状或显式 `"manual"`。
3. 读侧(如 `/api/pool/history`)至少透传 `snapshot_origin`,或提供 `?origin=` 过滤;既有 `available:false` 空态与响应形状不破坏(回归锁)。
4. 回填快照的 `strategy_version` 保持为「产生该快照的策略集指纹」(`strategy_fingerprint`, `pool_snapshot.py:135`)——诚实反映这是重算产物,不伪造 as_of 时刻指纹。

### HIST-03: 存档完整性可见 — 缺口与回填进度对用户透明

**作为** 股池使用者,**我** 能看到历史存档当前缺多少天、回填是否完成,而非只能从「日期列表短了一截」间接推断。

**验收标准:**
1. `GET /api/pool/dates`(或独立状态端点)增补缺口信息: `backfill_needed` 日期计数与示例(如 `{"dates": [...], "backfill_needed": N}`),source of truth = enriched 分区减快照分区(v2.0 22-RESEARCH A5 已预留此方向,「本期可不做」→ 本期做)。
2. 回填 job 进行中,前端可经既有 job 查询端点看到 `stage/pct/status`;完成后缺口计数归零。
3. 该端点保持 GET-only、零执行权,纳入 POOL-03 AST 守卫词汇(游客可读,与 `/pool/dates` 一致)。

### HIST-04: 回填护栏与规模化 — 可取消、可限界、升序摊销 warmup

**作为** 运营者,**我** 能安全地在大湖(如 247+ 日)上跑回填,不阻塞其他任务、不失控、不过度占用磁盘/计算。

**验收标准:**
1. 回填默认按 `as_of` **升序**处理,使相邻日的 150 天 warmup 窗口(`_compute_enriched_full`, `screener.py:354-385`)尽量复用(可选:共享已读 warmup 帧,作为性能优化,不改变单日语义)。
2. 提供 `max_days` 上限(默认如最近 N 个交易日或一次性全量由用户显式选择),每次 job 有界;重复触发幂等跳过已快照日。
3. 单飞与执行槽复用 `job_store.create` + `try_acquire_run_slot`(`pipeline_jobs.py:99,314`),与 EOD/手动任务互斥;失败日记录并继续(或 fail-fast,由入参决定),终态如实反映部分失败。
4. 零新增外部运行时依赖;回填全程只写 `screener_results/`(AST 守卫 E2 词汇扩展)。

---

## 风险与开放问题

| # | 风险/问题 | 级别 | 处置 |
|---|-----------|------|------|
| R1 | **回填污染最新指针**: 若回填照搬 EOD 的「先 `write_cache` 再 persist」,`strategy_cache.json` 会被写成过去日期,`/api/pool/hub` 回显陈旧日(实测先例: 陈旧 as_of=2026-07-31)。 | 高 | HIST-01 硬约束: 回填**绝不调 `write_cache`**;grep/AST 守卫锁死。现有手动 `run_all` 历史 as_of 也写 cache(`api/screener.py:445`)——建议本里程碑一并修复为「非最新日不写 cache」或至少文档化,列为开放问题 |
| R2 | **回填慢路径成本**: 历史日走 `_compute_enriched_full`(逐日加载 ~150 天 warmup,`screener.py:354-385`),247 日顺序执行估计 **30-120 分钟**[INFERENCE,基于单日 5-30s 估算],且逐日独立无法复用缓存。 | 中 | 后台 job + 可取消(HIST-01/04);升序摊销 warmup(HIST-04);必要时分块(如每批 30 日)由 `max_days` 控制。若实测过慢,可加「只读 warmup 状态跨日复用」优化(单日语义不变) |
| R3 | **回填快照 = 重算产物,非当日冻结**: 回填用「当前策略集」重算历史日,`strategy_version` 反映回填时刻;概念标签本就标注 `current_snapshot`(`pool_hub.py` RQ4 决议),但「当日归档 vs 事后重算」无字段区分。 | 中 | HIST-02 `snapshot_origin` 显式标注;读侧透传。不做第二份存储(方案 B 被否) |
| R4 | **存储量级**: 快照 JSON ~0.3-2 MiB/日 [INFERENCE,基于实测单条件命中 284-1461 行 × 投影行 ~244 B 外推],247 日 ≈ **79-693 MiB**(enriched 湖本身 51 MiB)。量级可接受但非「几十 KB」的乐观估计(22-RESEARCH 文档值偏小)。 | 低-中 | 接受;若未来膨胀,缩放路径为 JSON → Parquet/压缩或仅存 `display_limit` 行(与 OQ-2/duckdb 缩放路径一致)。HIST-01 无需预建 |
| R5 | **竞价数据不回填**: `kline_auction` 是 probe 门控的逐日存档,历史缺口(probe 当时不可用/未开启)是诚实缺失;回填不补竞价,回填快照的竞价列由 `attach_auction_columns` 双闸门(probe×分区)自然决定——有分区才注入,无则列缺席,保持诚实。 | 低 | 明确边界: 竞价历史属「历史竞价图」研究(ResearcherChart/ResearcherPremarket),本领域不越界 |
| R6 | **OQ-1 是否推翻**: 本领域结论是**补充而非推翻**——v2.1 目标特性要求全量存档,故加回填 job;OQ-1 的护栏(不阻塞、不静默、零执行权)全部保留。若产品仅需「EOD 前向」,HIST-01 可降级为可选开关。 | 决策点 | 交由 roadmap 合成与用户确认: 回填触发方式(手动端点 vs 启动后空闲时自动)与默认边界(全量 vs 最近 N 日) |
| R7 | **交易日历缺失**: 无独立交易日历,as_of 来源 = enriched 分区 glob。回填「无数据日」天然不在候选集内;若某日 enriched 分区存在但当日非交易日(罕见脏数据),快照照常生成,由 `latest_date`/freshness 判据兜底(与监控模块「快照日期=当日」判据同思路,`quote_service.py:1181-1184`)。 | 低 | 采用数据驱动日期集,不引入日历依赖 |
| R8 | **与手动 run_all 并发**: 回填 job 与手动 run_all 可能同时写同一 `date={d}` 分区。 | 中 | 复用 `_run_tracked` 单飞 + 执行槽互斥(与 `pool_eod_persist` 同构,`daily_pipeline.py:722-752`);`persist_point_snapshot` 幂等覆盖保证最终一致 |

---

## Sources

- 仓库源码(全部结论以源码与磁盘实测为准): `backend/app/services/pool_snapshot.py`、`backend/app/services/strategy_cache.py`、`backend/app/services/pool_hub.py`、`backend/app/services/screener.py`、`backend/app/api/pool.py`、`backend/app/api/screener.py`、`backend/app/jobs/daily_pipeline.py`、`backend/app/services/pipeline_jobs.py`、`backend/app/services/extend_history.py`、`backend/app/tickflow/repository.py`
- 规划文档: `.planning/STATE.md`(Deferred Items: 逐日全量存档模式)、`.planning/PROJECT.md`(HIST-01)、`.planning/milestones/v2.0-MILESTONE-AUDIT.md`(OQ-1 有意决策)、`.planning/milestones/v2.0-phases/22-pool-date-navigation/22-RESEARCH.md`(RQ2/A5 backfill_needed、RQ3/OQ-1 回填策略、OQ-2 快照格式)
- 磁盘实测: `data/kline_daily_enriched/` 247 分区 ~51 MiB;`data/screener_results/` 0 快照;`data/kline_auction/` 0 分区
