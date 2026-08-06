# Phase 24 研究:逐日全量存档

**研究日期:** 2026-08-06
**领域:** 历史股池逐日全量存档 / 批量回填 / 诚实 provenance / 缺口可见
**置信度:** HIGH(全部结论基于本次会话仓库实读代码 + 磁盘实测;唯一估算为回填耗时与存储量级,标 `[INFERENCE]`)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HIST-01 | 用户触发批量回填 job:逐历史 as_of 重放 `run_all_with_hits` → `screener_results/date={as_of}/`,绝不写 `strategy_cache.json`;可取消、可限界(最近 N / 日期区间)、升序摊销 warmup | D1/D2/D5;`run_all_with_hits` 签名与语义见 §现状-4;`persist_point_snapshot` 原子写见 §现状-1 |
| HIST-02 | 快照诚实 provenance:`snapshot_origin` 字段区分 eod/backfill;旧快照无字段读为 eod | D3;payload 结构与 `_SCHEMA_VERSION` 见 §现状-1 |
| HIST-03 | 存档完整性可见:`backfill_needed` 缺口信号(API + DateNavigator 空态)+ 回填进度可观察 | D4/D5;`/api/pool/dates` 与前端消费见 §现状-6 |
| HIST-04 | 平台护栏:POOL-03 零执行权、无请求内阻塞回放、手动 run_all 历史 as_of 写 cache 指针污染修复 | D1/D6;POOL-03 AST 守卫测试见 §现状-7 |

## Summary

AthenaQuant 的冻结式点快照湖(`screener_results/date={as_of}/part.json`,POOL-04)已经具备「按日分区 + 原子写 + 无 union 键」的正确存档载体,但生成策略只有「EOD 前向累积」——磁盘实测 `kline_daily_enriched/` 有 **247 个分区**(2025-07-29 ~ 2026-08-04)而 `screener_results/` **0 个快照**,这就是 HIST-01 要补的缺口。推荐方案:**在现有快照湖上补一个用户触发的批量回填 job**,复用 `ScreenerService.run_all_with_hits`(`screener.py:723`)+ `pool_snapshot.persist_point_snapshot`(`pool_snapshot.py:50`)单条代码路径,每个历史日只落 `screener_results/date={d}/part.json`,**绝不调 `strategy_cache.write_cache`**(它会改写 single-as_of 最新指针,`strategy_cache.py:157-164`),同时补 `snapshot_origin` 字段与 `backfill_needed` 缺口信号,并修复手动 `run_all` 对历史 as_of 写 cache 的既有指针污染(`api/screener.py:445`)。

**Primary recommendation:** 回填触发 = `POST /api/pipeline/backfill`(镜像 `extend_history` 手动触发模式,放在 `api/pipeline.py`——因为 POOL-03 的 AST 守卫把 `api/pool.py` 锁死为 GET-only,`test_pool_hub.py:811-812`);回填 job 内逐日 `run_all_with_hits(d)` + `persist_point_snapshot(d, origin="backfill")`,绝不 `write_cache`;缺口信号扩展 `GET /api/pool/dates` 响应;手动 run_all 仅当 `as_of == svc.latest_date()` 才 `write_cache`。**零新增运行时依赖**。

## 现状(代码证据,file:line)

### 1. 冻结式点快照载体已正确且已冻结(POOL-04)

- `persist_point_snapshot(data_dir, as_of, results, strategy_version, computed_at)`(`backend/app/services/pool_snapshot.py:50`):原子写 temp + `os.replace` 到 `screener_results/date={as_of}/part.json`。
- payload 结构(`pool_snapshot.py:87-93`,本次会话已读,逐字引用):
  ```python
  payload = {
      "as_of": as_of,
      "computed_at": computed_at,
      "strategy_version": strategy_version,
      "snapshot_type": "point",
      "schema_version": _SCHEMA_VERSION,
      "results": results,
  }
  ```
  其中 `_SCHEMA_VERSION = 1`(`pool_snapshot.py:34`),`_SNAPSHOT_ROOT = "screener_results"`(`pool_snapshot.py:29`),`_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")`(`pool_snapshot.py:31`,防路径穿越,`persist` 前 fullmatch,非法即抛 ValueError)。
- `load_point_snapshot(data_dir, as_of)`(`pool_snapshot.py:102`):文件缺失/解析失败 → `None`(诚实空态)。
- `list_snapshot_dates(data_dir)`(`pool_snapshot.py:120`):source of truth = `screener_results/date=*` 分区 glob 中含 `part.json` 者,ISO **desc**;root 不存在 → `[]`。
- `strategy_fingerprint(engine)`(`pool_snapshot.py:135`):排序策略 meta + 各策略源文件内容 sha256[:16];meta/源码变化 → 新指纹(回填快照指纹 = 回填时刻策略集,诚实反映「重算产物」)。

### 2. `strategy_cache.json` 是 single-as_of「最新指针」,与历史回填天然冲突

- `write_cache(data_dir, as_of, results)`(`backend/app/services/strategy_cache.py:118`),`_write_cache_locked`(`:132`)的 payload(`strategy_cache.py:157-164`,逐字引用):
  ```python
  payload = {
      "as_of": as_of,
      "results": results,
      "today_ever_matched": today_ever_matched,
      "today_ever_rows": today_ever_rows,
      "enriched_mtime": enriched_mtime,
      "updated_at": int(time.time() * 1000),
  }
  ```
- 同 as_of 时对 `today_ever_rows` 做 union 合并,换日重置(`strategy_cache.py:138-155`)——**语义是「最新一天」**。
- **核心风险:** 用历史 as_of 调 `write_cache` 会把文件 `as_of` 改成过去日期;`build_pool_hub` 以缓存为准回显(`pool_hub.py:189-210`,「始终回显缓存日期」),`GET /api/pool/hub` 即回显陈旧日。v2.0 实测先例「陈旧 as_of=2026-07-31 → EOD write_cache 修复为 2026-08-04」(ARCHIVE.md R1)。

### 3. EOD job 只向前生成,绝无回填(OQ-1 决策已编码)

- `_pool_eod_persist`(`backend/app/jobs/daily_pipeline.py:966-1010`):`ScreenerService(repo).latest_date()` → `run_all_with_hits(as_of, engine=...)`(`:995`)→ `strategy_cache.write_cache` 刷新最新指针(`:998`)→ `pool_snapshot.persist_point_snapshot`(`:999-1008`);无数据日/无 app state → 诚实 skip。
- 注册形(`daily_pipeline.py:1081-1086`):`mon-fri` cron、管道时间 +5min 偏移、`misfire_grace_time=3600`、`replace_existing=True`,包 `_run_tracked` 单飞(`daily_pipeline.py:722-752`,`job_store.create()` 非新 → skip + `try_acquire_run_slot()` 占重任务执行槽)。
- **结论:** 全仓无 pool backfill/archive/snapshot_origin 代码(本次 grep 证实,唯一命中是 `financial_sync.py` 无关的日志词)。

### 4. `run_all_with_hits` 可对任意历史 as_of 调用,是回填的共享核心

- 签名(`screener.py:723-727`,逐字引用):
  ```python
  def run_all_with_hits(
      self,
      as_of: date,
      strategy_ids: list[str] | None = None,
      engine=None,
  ) -> dict:
  ```
  docstring:`输出与 api/screener.run_all 同形 {sid: {total, as_of, rows}}`,`engine` 为 kwargs(路由传 `request.app.state.strategy_engine`,EOD job 传 `app_state.strategy_engine`;`engine=None` 容错只跑 PRESET)。
- 内部行为(`screener.py:753-812`):一次 `self._load_enriched_for_date(as_of)` 供所有策略共享;`strategy_ids` 空/None → 全部(PRESET + engine 非 PRESET);filter_history 策略惰性加载 `self._load_enriched_history(as_of, max_lb)`(**PIT: 只含 ≤ as_of**);每行附加 hit_factors。**内部不调用 `write_cache`**——写缓存是调用方(EOD job / 手动 run_all)的事。
- 历史日期读路径:
  - `_load_enriched_for_date(target_date)`(`screener.py:245-302`):最新日命中 repo 内存缓存(0ms);历史日走慢路径——读 `kline_daily_enriched/date={d}/part.parquet` 14 列 + `_compute_enriched_full` 即时重算指标。
  - `_compute_enriched_full`(`screener.py:354-403`):`start = target_date - timedelta(days=150)`(`:363`,docstring 写「~120 天」但代码是 **150 天**)扫描 `enriched_dir/**/*.parquet` 重算指标后只留目标日行。
  - `_load_enriched_history(target_date, lookback_days)`(`screener.py:405-498`):优先级 1 = `repo.get_enriched_history`(启动时 `_refresh_enriched` 已预计算完整历史,`repository.py:461,552-556` → **stock 历史日基本 0ms 命中**);优先级 2 = 进程级 TTL 缓存(`_history_cache`,`_HISTORY_CACHE_TTL = 120.0`,`screener.py:19-22`);优先级 3 = 慢路径 `scan_parquet + compute_indicators`,`warmup = 60; start = target_date - timedelta(days=min((lookback_days + warmup) * 2, 180))`(`screener.py:450-452`)。
- **成本模型:** 回填单日主要成本 = `_compute_enriched_full`(~5000 symbols × 150 日窗口重算,估 5-30s/日);filter_history 策略的 `_load_enriched_history` 因 repo 缓存基本免费。247 日顺序执行 ≈ **20-120 分钟** `[INFERENCE]`。**当前代码无跨日 warmup 复用**(`_history_cache` 按日 key 不同、`_compute_enriched_full` 不缓存)→ 升序是正确基线,真正的摊销优化需未来改 seam(见 D5)。

### 5. 数据现状:247 个 enriched 日,0 个快照(本次磁盘实测)

- `data/kline_daily_enriched/` **247 个分区**(2025-07-29 … 2026-08-04),每区 `part.parquet`;`data/screener_results/` **0 个快照**(空目录)。→ 当前历史股池只能回放/手动补,无逐日存档。
- **无独立交易日历**:日期枚举一律 `date=*` 分区 glob(`daily_pipeline.py:387` 既有模式:`enriched_dates = sorted(d.stem.split("=")[1] for d in enriched_dir.glob("date=*"))`);无 `list_enriched_dates` helper(需新增)。

### 6. 查询契约与前端消费(回填后零改动即可用)

- `GET /api/pool/dates`(`backend/app/api/pool.py:55-65`):返回 `{"dates": [...], "count": N, "latest": ...}`,source = `list_snapshot_dates`。
- `GET /api/pool/history?as_of=`(`api/pool.py:79-110`):as_of 严格双校验(`_AS_OF_RE` + `date.fromisoformat`,非法 → 400);快照缺失 → 200 `available:false` 空态;存在 → `build_pool_hub_snapshot` 同形状投影(`pool_hub.py:225-260`,读 `snap["results"]/["as_of"]/["computed_at"]`)。
- `build_pool_hub` / `build_pool_hub_snapshot` 共享 `_project_hub`(`pool_hub.py:83-187`);`total` 权威、概念 `current_snapshot` 标注、竞价列存在性声明(`auction_columns`)。
- 前端:`PoolHubPage.tsx` 用 `QK.poolDates` → `api.poolDates()`(`frontend/src/lib/api.ts:2110`),`PoolDatesResponse` 当前为 `{dates, count, latest}`(`api.ts:689-692`);`DateNavigator` 是受控只读组件(`frontend/src/components/pool-hub/DateNavigator.tsx:24-94`),空态由 `PoolHubPage.tsx:154-157` 渲染「该日期无股池快照」。回填完成后前端零改动即可浏览全量历史。

### 7. 测试锁定边界(本阶段必须绕开或显式扩展)

| 守卫 | 位置 | 内容 |
|------|------|------|
| POOL-03 E1 | `tests/test_pool_hub.py:788-797` | `pool_hub.py`/`pool.py`/`pool_snapshot.py` 不得 import 执行族模块;token `broker|order|execution|trade|portfolio|watchlist|position|account|transaction|下单|委托` |
| POOL-03 E4 | `test_pool_hub.py:807-813` | `pool.py` 只允许 GET 路由:`assert methods and set(methods) == {"get"}` |
| POOL-03 E2 | `test_pool_hub.py:826-863` | `pool_snapshot.py` 写路径必须引用 `_SNAPSHOT_ROOT`(只写 screener_results) |
| POOL-03 E3 | `test_pool_hub.py:880-888` | `pool_snapshot.py` 不 import/reference `strategy_cache` |
| POOL-03 E5 | `test_pool_hub.py:891-896` | `pool.py` 不得出现 `run_all`/`run_preset`/`write_cache`/`persist_point_snapshot` |
| POOL-03 E6 | `test_pool_hub.py:900-922` | hub/history/dates 响应键不含 `orders|execution|broker|deals` |
| `/api/pool/dates` 形状 | `test_pool_hub.py:704-723` | **精确相等断言** `resp.json() == {"dates": [...], "count": 2, "latest": "2026-08-04"}` → 加 `backfill_needed` 键必须同步更新此测试 |
| history 投影键集 | `test_pool_hub.py:726-745` | `{"as_of","updated_at","strategies","resonance_count","concept_attribution"} <= set(body)`(子集断言,加键不破坏) |
| EOD job 写 cache | `tests/test_pool_eod_job.py:113-159` | EOD job 必须写 `strategy_cache.json` 且 `as_of == 最新日` |
| run_all 落快照 | `tests/test_pool_snapshot.py:334-351` | run_all 后 part.json 存在,含 point 元数据,无 union 键 |
| 游客只读面 | `tests/test_guest_masking.py:508-530` | `/api/pool/*` GET 游客可读;非 GET 一律不放行 |

**关键推论:** 回填触发端点**不能**放在 `api/pool.py`(违反 E4);须放 `api/pipeline.py`(已有 `POST /run`、`/jobs/{id}/cancel`、`_long_task_executor`(`api/pipeline.py:15`),认证中间件自动挡游客(POST 不在 `_GUEST_READ_GET_PATHS`,`main.py:778-783`))。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 回填 job 编排(逐日重放/进度/取消) | Backend(services) | Backend(API) | 新 `services/pool_backfill.py` 复用 `run_all_with_hits` + `persist_point_snapshot`;端点只负责触发与 job 生命周期 |
| 回填触发端点 | Backend(API) | — | `POST /api/pipeline/backfill`,运营操作(写研究快照),非实盘执行;POOL-03 只锁 pool 面 |
| cache 指针保护 | Backend(services) | — | 回填绝不 `write_cache`;手动 run_all 修复点 `api/screener.py:445` |
| `snapshot_origin` provenance | Database/Storage(快照湖) | Backend(services) | 字段在 `persist_point_snapshot` 写入,读侧透传;旧快照默认 eod |
| `backfill_needed` 缺口信号 | Backend(API 读) | Browser/Client | `GET /api/pool/dates` 增补字段;DateNavigator/PoolHubPage 空态消费 |
| 进度可见 | Backend(API) | Browser/Client | 既有 `GET /api/pipeline/jobs/{id}` 轮询 |

## 关键决策

### D1 回填触发方式

**选项:**
- **A(推荐):** `POST /api/pipeline/backfill`,body `{start?, end?, max_days?}`,立即返回 `{status, job_id}`,后台 executor 跑(镜像 `POST /api/kline/extend_history`,`api/kline.py:633-700`)。
- B: `POST /api/pool/backfill` — **否决**:`test_pool_api_is_get_only`(`test_pool_hub.py:807-813`)锁死 pool.py 只允许 GET;加 POST = 必红。
- C: 操作员 CLI 脚本(`backend/scripts/`)—— 可行但无 HTTP 进度,违背 HIST-03「回填进度可观察」;且与 job_store 脱节。
- D: 空闲自动(启动后/每日低峰)—— 违背 OQ-1「不静默写盘」;247 日 20-120 分钟后台批不应藏在 cron 里。

**推荐:A。** 理由:(1) `api/pipeline.py` 已拥有 job 生命周期端点(`/run` `/jobs/{id}` `/jobs/{id}/cancel`)、`_long_task_executor`(`api/pipeline.py:15`)、`job_store`/`try_acquire_run_slot` 导入,是天然的运营批处理入口;(2) 认证中间件对非游客 POST 一律 401(`main.py:838-840`),天然 operator-only;(3) 不触碰任何 POOL-03 守卫测试。
**风险:** 端点须不 import 执行族模块(虽无 pool 面守卫,保持平台一致性);`max_days`/日期参数须校验(见 D5)。

### D2 cache 保护边界

**选项:**
- **A(推荐):** 回填 job 内**绝不调 `strategy_cache.write_cache`**;由新增测试断言回填前后 `strategy_cache.json` **byte-identical**(如 `test_pool_backfill.py::test_backfill_never_touches_strategy_cache`)。
- B: 有条件写(如仅最新日写)—— 回填的语义就是「历史日补齐」,不存在需要刷最新指针的场景;引入条件即引入误触风险。

**推荐:A。** 理由:`write_cache` 把 `as_of` 写进 payload(`strategy_cache.py:157-164`),历史日写会污染 single-as_of 指针,`/api/pool/hub` 回显陈旧日;`run_all_with_hits` 内部天然不写 cache(调用点只在 `api/screener.py:445` 与 `daily_pipeline.py:998`),回填直接调共享核心即天然安全。
**风险:** 低;若未来有人给回填路径加 write_cache,靠守卫测试 + 代码评审锁死。

### D3 snapshot_origin 兼容

**选项:**
- **A(推荐):** `persist_point_snapshot` 增 `origin: str = "eod"` 参数(校验 ∈ {eod, backfill, manual}),payload 增 `"snapshot_origin": origin`;**`schema_version` 保持 1**;读侧 `snap.get("snapshot_origin", "eod")` 容错。
- B: `schema_version` 递增到 2,读侧按版本分支。

**推荐:A。** 理由:旧 reader 忽略未知键、新 reader 默认 eod,零迁移;`_SCHEMA_VERSION = 1`(`pool_snapshot.py:34`)保持;`load_point_snapshot`/`build_pool_hub_snapshot` 现有读路径只取 `results/as_of/computed_at`,不受影响。
**风险:** 若读侧强制要求字段则破坏旧快照(已排除);需在 `build_pool_hub_snapshot` 的投影响应里透传 `snapshot_origin`(`pool_hub.py:243-260`),并回归 `test_pool_history_snapshot` 键集断言(子集断言,加键安全)。

### D4 backfill_needed 形态

**选项:**
- **A(推荐):** 扩展 `GET /api/pool/dates` 响应,增 `backfill_needed: int`(缺口计数)+ `backfill_examples: string[]`(最多 5 个示例缺口日)。缺口 = `list_enriched_dates` − `list_snapshot_dates`(升序)。
- B: 独立 `GET /api/pool/gaps` 端点。

**推荐:A。** 理由:前端已有 `QK.poolDates` 单次 query(`PoolHubPage.tsx:25-29`),加字段零新增请求;GET-only 保持;E6 词汇守卫(`orders/execution/broker/deals`)不冲突;`test_pool_dates_api` 是精确相等断言,更新它即可(属 HIST-03 合同变更,非守卫破坏)。
**风险:** 修改一个既有行为测试(`test_pool_hub.py:713-717` 加入新键);若选 B 则需新 guest 白名单 + 第二个前端 query,得不偿失。

### D5 调度与取消

**选项:**
- **A(推荐):** 复用 `job_store.create()` 单飞(`pipeline_jobs.py:99-112`,pending∨running 去重)+ `try_acquire_run_slot()` 重任务执行槽(`pipeline_jobs.py:314-316`)+ `run_in_executor(_long_task_executor, ...)` 后台化 + 升序处理 + **合作式取消**(循环每日期检查 `job_store.get(job_id).status`,发现 failed 即停)。
- B: 硬中断(threading.Event + cancel 回调)—— 当前 `POST /api/pipeline/jobs/{id}/cancel` 只 `job_store.fail(job_id, "用户手动取消")`(`api/pipeline.py:98-107`),无线程中断通道;硬中断需动 cancel 端点,超出本阶段。

**推荐:A。** 理由:`job_store` 单飞天然防回填与 EOD/manual 并发写同一 `date={d}` 分区;`reap_stale` 兜底卡死(`pipeline_jobs.py:210-245`);合作式取消在单日 5-30s 粒度下足够及时;`persist_point_snapshot` 幂等覆盖保证最终一致。
**风险:** 取消不是硬中断,当前日算完才停(可接受);升序不减少单日 `_compute_enriched_full` 成本(当前代码无跨日 warmup 复用),真正的摊销优化需改 seam,列为后续优化。

### D6 修复手动 run_all 指针污染

**选项:**
- **A(推荐):** 在 `api/screener.py` `run_all`(`:408-461`)中,仅当 `as_of == svc.latest_date()` 才 `strategy_cache.write_cache`(`:445`);快照**总是**落(`:450-456`),origin 按 `"eod" if is_latest else "backfill"`。
- B: 给 `run_all_with_hits` 加 `write_cache: bool = False` 参数 —— 改动共享核心签名,EOD job 与监控路径全部受影响,过度设计。

**推荐:A。** 理由:修复点精确(`api/screener.py:445` 无条件写);`svc.latest_date()`(`screener.py:704`)已存在;不改共享核心;历史 as_of 仍落快照(手动补缺口行为保留),仅不再污染 cache 指针。
**风险:** 行为变更(历史 as_of 不再写 cache)——这正是 HIST-04 目标;grep 证实无测试断言「历史 as_of 的 run_all 写 cache」;回归 `test_pool_snapshot.py:334`(fixture 的 as_of=最新日,仍写 cache)与 `test_pool_eod_job.py:113`(EOD job 不受影响)。

## Standard Stack

**零新增运行时依赖(锁定约束,`uv.lock` 既有栈,本阶段只复用):**

| 组件 | 用途 | 位置 |
|------|------|------|
| `ScreenerService.run_all_with_hits` | 逐历史日重放的共享核心 | `backend/app/services/screener.py:723` |
| `pool_snapshot.persist_point_snapshot` | 原子写快照(扩展 origin 参数) | `backend/app/services/pool_snapshot.py:50` |
| `pool_snapshot.list_snapshot_dates` | 已快照日期集 | `pool_snapshot.py:120` |
| `job_store`(`JobStore`) | 单飞/进度/终态持久化 | `backend/app/services/pipeline_jobs.py:40-263` |
| `try_acquire_run_slot` / `release_run_slot` | 重任务执行槽互斥 | `pipeline_jobs.py:314-316` |
| `_long_task_executor` | 后台线程池(请求内零阻塞) | `backend/app/api/pipeline.py:15` |
| `daily_pipeline.enriched_dates` glob 模式 | 枚举 enriched 日期(缺 helper,需新增 `list_enriched_dates`) | `daily_pipeline.py:387` |
| `api/pipeline.py` 既有端点 | job 查询/取消(进度可见) | `api/pipeline.py:87-115` |

**版本核实:** 无需新包;`polars`/`apscheduler`/`fastapi` 均在既有 `uv.lock`。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 后台 job 单飞/进度/取消/终态 | 自写线程管理 | `job_store`(`pipeline_jobs.py:40-263`) | 已与 EOD/手动 run_all 同构,reap_stale 自愈 |
| 快照原子写 | 自写 os.replace | `persist_point_snapshot`(`pool_snapshot.py:50`) | temp+os.replace 幂等覆盖,无 .tmp 残留 |
| 枚举 enriched 日期 | 自写日历 | `date=*` 分区 glob(镜像 `daily_pipeline.py:387`) | 无交易日历;数据驱动,脏数据日由 freshness 兜底 |
| as_of 校验 | 自写正则 | 复用 `_DATE_RE`(`pool_snapshot.py:31`)/`_AS_OF_RE`(`api/pool.py:16`) | 防路径穿越,已锁 |
| 最新日判定 | 自写 | `ScreenerService.latest_date()`(`screener.py:704`) | D6 的 cache 写入闸门 |

**Key insight:** 回填的正确性不来自新机制,而来自「复用与 EOD/manual 完全相同的 `run_all_with_hits` + `persist_point_snapshot` 单条代码路径」,再刻意**省略** write_cache 一步。任何「另造归档层/回放路径」都是重复建设。

## 实现方案草案(文件级改动清单 + 顺序)

### 顺序与依赖

1. **`backend/app/services/pool_snapshot.py`(基础)**
   - `persist_point_snapshot(..., origin: str = "eod")`:校验 `origin in {"eod","backfill","manual"}`,payload 增 `"snapshot_origin": origin`(保持 `_SCHEMA_VERSION = 1`)。
   - 新增 `list_enriched_dates(data_dir) -> list[str]`:glob `data_dir/kline_daily_enriched/date=*`(升序),镜像 `daily_pipeline.py:387`;纯读 helper,不触发 E2 守卫(无写 pattern)。
2. **`backend/app/services/pool_hub.py` + `backend/app/api/pool.py`(HIST-02/03 读侧)**
   - `build_pool_hub_snapshot`(`pool_hub.py:243-260`)投影响应增 `"snapshot_origin": snap.get("snapshot_origin", "eod")`;空态响应亦可加 `snapshot_origin: None`(可选)。
   - `get_pool_dates`(`api/pool.py:55-65`)增 `backfill_needed`(=`set(list_enriched_dates) - set(list_snapshot_dates)` 的基数)+ `backfill_examples`(升序前 5 个)。GET-only 保持。
3. **`backend/app/api/screener.py`(D6 修复)** — `run_all`(`:408-461`):`is_latest = (svc.latest_date() == as_of)`;`if results and is_latest: strategy_cache.write_cache(...)`;`persist_point_snapshot(..., origin="eod" if is_latest else "backfill")`。
4. **`backend/app/services/pool_backfill.py`(新服务)**
   - `run_pool_backfill(repo, engine, start=None, end=None, max_days=None, on_progress=None, job_id=None) -> dict`:
     - 缺口集 = `list_enriched_dates` − `list_snapshot_dates`;应用 `start/end/max_days` 边界;**升序**。
     - 逐日:`results = ScreenerService(repo).run_all_with_hits(d, engine=engine)`;`if results: persist_point_snapshot(data_dir, str(d), results, strategy_version=strategy_fingerprint(engine), computed_at=now, origin="backfill")`;**绝不 `write_cache`**。
     - 每日期 `on_progress("pool_backfill", pct, f"{done}/{total} {d}", stage_pct=...)`;若 `job_id` 且 `job_store.get(job_id).status == "failed"` → 停止(合作式取消)。
     - 失败日记录 `failed_dates` 并继续;返回 `{requested, backfilled, skipped_existing, failed, failed_dates, origin: "backfill"}`。
5. **`backend/app/api/pipeline.py`(触发端点)** — 新增 `POST /backfill`(镜像 `extend_history` 模式):
   - body `{start?, end?, max_days?}`;校验:start/end 匹配 `^\d{4}-\d{2}-\d{2}$` + `date.fromisoformat` + `start <= end`;`max_days` 正整数且有上限(如 ≤500)。
   - `job_store.create()` 单飞(`not is_new` → 返回复用);`try_acquire_run_slot()` 失败 → `job_store.fail`;`run_in_executor(_long_task_executor, lambda: run_pool_backfill(repo, engine, ..., on_progress=progress, job_id=job_id))`。
   - 返回 `{"status": "started"|"reused", "job_id"}`;进度经既有 `GET /api/pipeline/jobs/{id}` 可见,取消经既有 `POST /api/pipeline/jobs/{id}/cancel`。
6. **`backend/app/jobs/daily_pipeline.py`(显式 honest)** — `_pool_eod_persist`(`:999-1008`)调 `persist_point_snapshot(..., origin="eod")`(默认值已覆盖,显式标注自文档化)。
7. **前端(最小 HIST-03 消费,不触碰 `Watchlist.tsx`)**
   - `frontend/src/lib/api.ts`:`PoolDatesResponse` 增 `backfill_needed?: number` / `backfill_examples?: string[]`(`api.ts:689-692`);新增 `poolBackfill(params)` → `POST /api/pipeline/backfill`。
   - `frontend/src/pages/PoolHubPage.tsx`:`datesQuery.data?.backfill_needed > 0` 时显示缺口横幅 + 回填触发按钮(成功后 invalidate `QK.poolDates`);DateNavigator 空态已有(`PoolHubPage.tsx:154-157`),横幅与之互补。
8. **测试**
   - 新增 `backend/tests/test_pool_backfill.py`:缺口计算/边界/max_days/升序;回填落快照且 `snapshot_origin=="backfill"`;**断言 `strategy_cache.json` 前后 byte-identical**;幂等跳过已快照日;合作式取消(置 job failed → 停);失败日继续;EOD 路径仍写 cache(回归)。
   - 更新 `tests/test_pool_hub.py`:`test_pool_dates_api` 期望 dict 增 `backfill_needed`/`backfill_examples`;history 投影断言增 `snapshot_origin`(若透传)。
   - 更新 `tests/test_pool_snapshot.py`:origin 参数 round-trip;旧 payload 无字段 → 读为 eod;D6 回归(历史 as_of run_all 不写 cache、最新日写)。
   - 更新 `tests/test_pool_eod_job.py`:断言快照 `snapshot_origin == "eod"`。
9. **验证命令(约束)**
   ```bash
   cd backend && .venv/bin/python -m pytest tests/test_pool_backfill.py tests/test_pool_hub.py tests/test_pool_snapshot.py tests/test_pool_eod_job.py tests/test_factor_hits.py tests/test_guest_masking.py -x -q
   ```

## Common Pitfalls

### Pitfall 1:回填误写 `strategy_cache.json` 污染最新指针
**What goes wrong:** `/api/pool/hub` 回显陈旧 as_of(v2.0 先例 2026-07-31)。
**Why:** `write_cache` 把历史 as_of 写进 payload(`strategy_cache.py:157-164`),`build_pool_hub` 以缓存为准回显。
**How to avoid:** 回填路径 AST/grep 锁死 + `test_backfill_never_touches_strategy_cache` byte-identical 断言。
**Warning signs:** 回填后 `data/user_data/strategy_cache.json` 的 `as_of` 非最新日。

### Pitfall 2:在 `api/pool.py` 加 POST 端点
**What goes wrong:** `test_pool_api_is_get_only` 必红。
**Why:** POOL-03 E4 守卫用 `re.findall(r"@router\.(get|post|...)")` 断言全 GET(`test_pool_hub.py:807-813`)。
**How to avoid:** 触发端点放 `api/pipeline.py`。
**Warning signs:** `pool.py` 出现 `@router.post`。

### Pitfall 3:请求内阻塞回放
**What goes wrong:** 页面卡死,违背 POOL-06「首个历史日请求不被阻塞」。
**Why:** 若把回填放在请求同步路径,247 日 × 秒级 = 分钟级阻塞。
**How to avoid:** `run_in_executor(_long_task_executor, ...)`(`api/pipeline.py:15`)后台化,立即返回 job_id。
**Warning signs:** 触发接口响应耗时与回填耗时成正比。

### Pitfall 4:无界/非法日期参数
**What goes wrong:** 路径穿越或失控长任务。
**Why:** start/end 未校验、max_days 未限。
**How to avoid:** 复用 `_DATE_RE`(`pool_snapshot.py:31`)+ `date.fromisoformat` + `start <= end` + `max_days` 正整数上限。
**Warning signs:** 参数直接拼路径。

### Pitfall 5:读侧强制 `snapshot_origin` 破坏旧快照
**What goes wrong:** 回填前已有的 0 个快照(现在)或未来 EOD 旧快照读失败。
**Why:** 若 `build_pool_hub_snapshot` 直接 `snap["snapshot_origin"]` 而非 `.get(..., "eod")`,旧 payload 无字段即 KeyError。
**How to avoid:** `snap.get("snapshot_origin", "eod")`;回归 `test_pool_history_snapshot`。
**Warning signs:** 旧快照日期在 history 端点 500。

## Validation Architecture

`workflow.nyquist_validation = true`(config.json)→ 本阶段纳入验证。

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest(backend,`.venv`) |
| Config file | 无独立 pytest.ini;沿用仓库惯例 |
| Quick run command | `cd backend && .venv/bin/python -m pytest tests/test_pool_backfill.py -x -q` |
| Full suite command | `cd backend && .venv/bin/python -m pytest tests/test_pool_hub.py tests/test_pool_snapshot.py tests/test_pool_eod_job.py tests/test_pool_backfill.py tests/test_factor_hits.py tests/test_guest_masking.py -x -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HIST-01 | 回填逐日落快照、绝不写 cache、可限界/升序/可取消 | unit/integration | `pytest tests/test_pool_backfill.py -x -q` | ❌ Wave 0 |
| HIST-02 | snapshot_origin eod/backfill + 旧快照读 eod | unit | `pytest tests/test_pool_snapshot.py tests/test_pool_eod_job.py -x -q` | ⚠️ 更新既有 |
| HIST-03 | `/api/pool/dates` backfill_needed + 进度可见 | integration | `pytest tests/test_pool_hub.py tests/test_pool_backfill.py -x -q` | ⚠️ 更新既有 |
| HIST-04 | POOL-03 守卫不破 + 手动 run_all 历史 as_of 不写 cache | unit | `pytest tests/test_pool_hub.py tests/test_pool_snapshot.py tests/test_factor_hits.py tests/test_guest_masking.py -x -q` | ✅ 既有 |

### Sampling Rate
- **Per task commit:** `cd backend && .venv/bin/python -m pytest <改动的测试文件> -x -q`
- **Per wave merge:** 上表 full suite
- **Phase gate:** Full suite 全绿后 `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_pool_backfill.py` — 覆盖 HIST-01..04 回填侧全部行为
- [ ] 更新 `backend/tests/test_pool_hub.py::test_pool_dates_api` — 增 `backfill_needed` 键
- [ ] 更新 `backend/tests/test_pool_snapshot.py` — origin round-trip + 旧 payload 默认 eod + D6 回归

*(若无缺口:"None — 既有测试基础设施覆盖全部需求")——本阶段有上述 Wave 0 缺口,需新建/更新。*

## Security Domain

`security_enforcement = true`(config.json)→ 本阶段纳入;ASVS L1。

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | 触发端点 POST 天然非游客面(中间件 401);回填端点不新增认证逻辑 |
| V3 Session Management | no | 无会话变更 |
| V4 Access Control | yes | 回填端点 operator-only(POST + 非 `_GUEST_READ_GET_PATHS`);`backfill_needed` GET 游客可读(与 `/pool/dates` 一致) |
| V5 Input Validation | yes | as_of/start/end 复用 `^\d{4}-\d{2}-\d{2}$` 全匹配 + `date.fromisoformat`;`max_days` 正整数上限;回填服务内对目标日再经 `persist_point_snapshot` 的 `_DATE_RE` 双保险 |
| V6 Cryptography | no | 无密文处理;`strategy_fingerprint` 为 sha256[:16] 指纹(非安全用途) |
| V8 (path traversal) | yes | `_DATE_RE` fullmatch 防 `../../`;快照路径由 `_snapshot_path` 拼接(`pool_snapshot.py:47`) |

### Known Threat Patterns for {stack}
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| 路径穿越 via as_of | Tampering | `_DATE_RE` fullmatch(`pool_snapshot.py:31`)+ `date.fromisoformat` 双校验(`api/pool.py:83-90`) |
| 无界资源消耗(全量回填) | DoS | `max_days` 上限 + 单飞(`job_store.create`)+ 执行槽(`try_acquire_run_slot`) |
| 最新指针污染 | Integrity | 回填绝不 write_cache + byte-identical 测试锁死 |
| 并发写同一分区 | Integrity | `job_store` 单飞 + 执行槽互斥 + `persist_point_snapshot` 幂等覆盖 |
| 游客触发写操作 | Spoofing | POST 不在 `_GUEST_READ_GET_PATHS`(`main.py:778-783`)→ 401 |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `data/kline_daily_enriched/` | 回填候选日期源 | ✓ | 247 分区(2025-07-29..2026-08-04) | — |
| `data/screener_results/` 可写 | 回填写入 | ✓ | 0 快照(空目录,可写) | — |
| Python + polars + fastapi + apscheduler | 回填 job 运行时 | ✓ | 既有 `uv.lock` 栈 | — |
| `data/user_data/strategy_cache.json` | 不得被回填触碰 | ✓(存在/可写) | 既有 | 回填后 byte-identical 断言 |

**Missing dependencies with no fallback:** 无——本阶段零新增外部依赖。
**Missing dependencies with fallback:** 无。

## 风险与开放问题

| # | 风险/问题 | 级别 | 处置 |
|---|-----------|------|------|
| R1 | **write_cache 指针污染**(回填/手动历史 run_all) | 高 | D2/D6;测试锁死 |
| R2 | **回填耗时**:247 日 × 单日 5-30s ≈ 20-120 分钟 `[INFERENCE]` | 中 | 后台化 + 可取消 + 升序 + max_days 限界;若实测过慢再加「共享 warmup 帧」优化(需改 seam,单日语义不变) |
| R3 | **回填快照 = 重算产物**:`strategy_version` 反映回填时刻策略集 | 中 | D3 `snapshot_origin:"backfill"` 显式标注,读侧透传;不做第二份存储 |
| R4 | **存储量级**:~0.3-2 MiB/日 `[INFERENCE]`,247 日 ≈ 79-693 MiB | 低-中 | 接受;膨胀路径 = JSON→Parquet/压缩 |
| R5 | **`/api/pool/dates` 精确断言测试**随新键更新 | 低 | 属 HIST-03 合同变更,非守卫破坏;同步更新 `test_pool_dates_api` |
| R6 | **无交易日历**:日期集 = enriched 分区 glob | 低 | 数据驱动;无数据日天然不在候选集;脏数据日由 freshness 兜底 |
| R7 | **与手动 run_all/EOD 并发写同一分区** | 中 | `job_store` 单飞 + 执行槽互斥 + 幂等覆盖 |
| R8 | **回填只读不写 `kline_auction`**:竞价列由 `attach_auction_columns` 双闸门自然决定 | 低 | 明确边界,属 CHART/PM 领域 |

**Open Questions**
1. **回填默认边界(全量 vs 最近 N)** — 里程碑目标是「全量覆盖 247 日」,推荐默认全量缺口 + `max_days`/`start`/`end` 可选限界;是否把默认改为「最近 N」需与用户确认(要求 HIST-01 原文「最近 N 或日期区间」均支持)。
2. **手动 run_all 的 origin 语义** — 推荐「最新日 → eod,历史日 → backfill」;是否要单独的 `"manual"` 值(要求文档提过)需产品定夺。
3. **`snapshot_origin` 是否在 `/api/pool/hub`(最新视图)透传** — 最新视图读 `strategy_cache`,无 origin;建议只在 history 投影透传,不扩 hub。
4. **前端回填横幅是否本阶段交付** — HIST-03 写「API + DateNavigator 空态」;最小实现为 PoolHubPage 横幅 + 触发按钮;若前端不在本阶段范围,可仅交付 API + 文档标注(需 Main/用户确认)。
5. **warmup 摊销优化** — 当前代码无跨日复用;升序为正确基线,「共享 warmup 帧」优化需改 `run_all_with_hits`/`_load_enriched_for_date` seam,建议回填 v1 之后按实测再定。

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | 回填 247 日约 20-120 分钟(单日 5-30s) | 现状-4 / R2 | 若远慢于估计,需加共享 warmup 优化或分块 |
| A2 | 快照 ~0.3-2 MiB/日,247 日 ≈ 79-693 MiB | R4 | 磁盘占用超预期 → 压缩/Parquet 路径 |
| A3 | `repo.get_enriched_history` 覆盖全部历史日(启动时预计算) | 现状-4 | 若缓存只覆盖近窗,`_load_enriched_history` 走慢路径,成本上升;回填 v1 以实测为准 |
| A4 | 手动 run_all 历史 as_of 无既有测试断言「写 cache」 | D6 | 若遗漏,更新测试即可(行为变更是 HIST-04 目标) |

## Sources

### 仓库源码(本次会话全部实读,file:line 已内联)
- `backend/app/services/pool_snapshot.py`(50/87-93/102/120/135)
- `backend/app/services/strategy_cache.py`(118/132-170)
- `backend/app/services/screener.py`(19-22/245/354-403/405-498/704/723-812)
- `backend/app/services/pool_hub.py`(83-187/189-210/225-260)
- `backend/app/api/pool.py`(1-8/24/55-65/79-110)
- `backend/app/api/screener.py`(408-461)
- `backend/app/api/pipeline.py`(15/31/87-115)
- `backend/app/api/kline.py`(633-700,extend_history 手动触发范本)
- `backend/app/jobs/daily_pipeline.py`(386-390/722-752/966-1010/1081-1086/1166)
- `backend/app/services/pipeline_jobs.py`(40-263/314-316)
- `backend/app/services/extend_history.py`(102-235)
- `backend/app/tickflow/repository.py`(32/461-556/937-970/1118)
- `backend/app/main.py`(778-783/786-788/838-840/848/858)
- `backend/tests/test_pool_hub.py`(704-723/726-745/788-922)
- `backend/tests/test_pool_snapshot.py`(334-351)
- `backend/tests/test_pool_eod_job.py`(113-159)
- `backend/tests/test_guest_masking.py`(508-530)
- `frontend/src/lib/api.ts`(689-692/2110)、`frontend/src/pages/PoolHubPage.tsx`(25-39/108-114/154-157)、`frontend/src/components/pool-hub/DateNavigator.tsx`(24-94)

### 规划文档
- `.planning/REQUIREMENTS.md`(HIST-01..04)、`.planning/ROADMAP.md`(Phase 24 Goal/Success Criteria)、`.planning/research/v2.1-depth/SUMMARY.md`、`.planning/research/v2.1-depth/ARCHIVE.md`、`.planning/config.json`(nyquist_validation/security_enforcement)

### 磁盘实测(本次会话)
- `data/kline_daily_enriched/` 247 分区;`data/screener_results/` 0 快照;`data/job_store/` JSON 终态文件存在

## Metadata

**Confidence breakdown:**
- 现状(代码证据):HIGH — 全部 file:line 本次会话实读,关键 payload 逐字引用。
- 关键决策(D1-D6):HIGH — 基于守卫测试与既有模式;唯一估算(A1/A2/A3)标 `[INFERENCE]`。
- 实现方案:MEDIUM-HIGH — 文件级清单与顺序明确;具体函数签名在规划时按既有惯例细化。

**Research date:** 2026-08-06
**Valid until:** 30 天(仓库快照湖/守卫测试稳定;`strategy_cache`/`pool_snapshot` 为既有冻结契约)
