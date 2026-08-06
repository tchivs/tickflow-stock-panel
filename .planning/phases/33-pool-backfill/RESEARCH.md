# 股池回填 OQ-1 — Phase 33 research (PB-01..04)

**研究日期:** 2026-08-06 · **研究者:** ResearcherP33 · **消费方:** gsd-planner (Phase 33)
**输入:** `research/v2.3-data-depth/POOL-BACKFILL.md` (域研究) + `REQUIREMENTS.md` PB-01..04 + `ROADMAP.md` Phase 33 + `milestones/v2.1-phases/24-historical-archive/` (24-01/02 PLAN+SUMMARY, 24-RESEARCH.md) + `v2.1-MILESTONE-AUDIT.md:27` (OQ-1 定义)
**约束:** 只读研究, 仅写本文件; 未执行回填 (可读湖分区); 零新增依赖。

**裁决: 实施就绪 (YES)** — 回填链 24 期已交付且本会话逐行核实; 沙箱子集跑 (PB-01) 可确定性执行; 稀疏竞价湖交互已推演到策略级 (引擎短路 / 列注入 / 按标的 null); 测试设计沿用既有 patch 约定; 全量 248 为 operator 操作 (PB-02); PIT 回退 (PB-03) 与 premarket 缺口 (PB-04) 均诚实可记录。

---

## 1. 现状: 回填链 (本会话 file:line 核实)

| 层 | 位置 | 行为 |
|----|------|------|
| 触发端点 | `backend/app/api/pipeline.py:89-90` `@router.post("/backfill")` `pool_backfill` | body `{start?, end?, max_days?}`; 参数校验 `:103-121` (start/end `^\d{4}-\d{2}-\d{2}$` + fromisoformat, start≤end, max_days 整数 1..500 `:115-121`); 单飞 `job_store.create()` 复用活跃任务 `:133-139` (`is_new=False` → `{"status":"reused","job_id"}`); 重任务槽 `try_acquire_run_slot()` `:143-147` (与 EOD/手动 run_all 并发写同分区互斥; 失败 → job fail 记录 `"已有数据任务在运行"`); 后台 `loop.run_in_executor(_long_task_executor, ...)` `:151-156`; 响应 `{"status":"started","job_id":...}` `:162` |
| job 生命周期 | `backend/app/api/pipeline.py:169-190` | `GET /jobs/{job_id}` (轮询, 含 reap_stale) `:169-178`; `POST /jobs/{job_id}/cancel` (合作式: 置 job failed, 回填每日期自查) `:180-190` |
| 回填服务 | `backend/app/services/pool_backfill.py:30` `run_pool_backfill` | 缺口集 = `list_backfill_gaps` `:57`; start/end/max_days 限界 `:58-63` (max_days 取前 N 升序); 空缺口 → 终态 `{requested:0,...}` `:65-71`; 指纹 `strategy_fingerprint(engine) if engine else "unknown"` `:66-67`; **升序**逐日循环 `:73-97`; 合作式取消 (job 状态 failed → break) `:77-81`; 每日 `svc.run_all_with_hits(date, engine=engine)` + `persist_point_snapshot(..., origin="backfill")` `:84-90`; **绝不 write_cache** (D2, 模块 docstring :11-12); 失败日记 `failed_dates` 继续 `:91-95`; 终态 `{"requested","backfilled","failed","failed_dates","origin":"backfill"}` `:118-123` |
| 缺口单点 | `backend/app/services/pool_snapshot.py:157` `list_backfill_gaps` | = `list_enriched_dates` (:144, enriched 分区 glob 升序) − `list_snapshot_dates` (:129, 含 part.json 者 desc); root 缺失 → `[]`; 幂等: 已快照日自动跳过 |
| 快照写入 | `backend/app/services/pool_snapshot.py:52` `persist_point_snapshot` | origin ∈ {eod,backfill,manual} 校验 `:68-70` (非法 → ValueError); payload 含 `snapshot_origin`/`strategy_version`/`snapshot_type:"point"`/`schema_version:1` `:83-93`; temp + `os.replace` 原子写 `:98-103`; 同 as_of 幂等覆盖; 异常吞掉记 warning (非致命) |
| 共享核心 | `backend/app/services/screener.py:723` `run_all_with_hits` | 一次 `_load_enriched_for_date(as_of)` 全策略共享 `:740`; 策略集 = PRESET (7 个, `:30`) + engine 非 PRESET (`:744-750`); filter_history 策略惰性共享 `_load_enriched_history` `:766-777`; 逐策略 try/except 继续 `:788-803`; `build_factor_hits`/`attach_factor_hits` `:808-812`; **内部不写 cache** (调用方职责) |
| 读路径 | `backend/app/api/pool.py:79-113` `GET /api/pool/history?as_of=` → `build_pool_hub_snapshot` (`pool_hub.py:293`) | as_of 双校验 (非法 → 400) `:99-107`; 快照缺失 → 200 `available:false` `:301-310`; 存在 → `_project_hub(results, as_of=snap["as_of"], ...)` `:311-318` + `snapshot_origin` 透传 (旧 payload 缺省 eod) `:330-332` |
| 概念 PIT 读侧 | `backend/app/services/pool_hub.py:61` `_build_concept_map` | as_of 非空 → `concept_history.read_partition(data_dir, "gn_ths", as_of)` (:66-70); 命中 → `as_of_snapshot` + effective_date/captured_at (:112-115, :251-253 经 `_project_hub` :161-162 落地); 未命中 → 回退 `current_snapshot`/`unavailable` (:135-141) |
| EOD 前向 | `backend/app/jobs/daily_pipeline.py:973` `_pool_eod_persist` | 最新日 write_cache + persist (origin 默认 eod) + `concept_history.capture` `:1017` (仅真实 EOD 前向写 `ext_history/`) |
| 手动 run_all D6 | `backend/app/api/screener.py:445-462` | `latest = svc.latest_date()`; 仅 `str(as_of)==latest` 才 `write_cache` (:445-451); 快照**总是**落盘, origin = `"eod" if is_latest else "backfill"` (:457-462) |
| 无 CLI | `backend/scripts/` | 无回填脚本 (24-RESEARCH.md:133 否决选项 C); 本阶段沿用端点, CLI 属新增面 |

**请求/响应形状 (PB-01 验收依据):** `POST /api/pipeline/backfill` body `{"start"?, "end"?, "max_days"?}` → `{"status":"started"|"reused","job_id"}`; `GET /api/pipeline/jobs/{id}` → job dict (status/progress/result); 终态 dict 6 键含 `origin:"backfill"`。认证: 非游客 POST 一律 401 (`main.py:782-794` `_GUEST_READ_GET_PATHS` 仅 GET 白名单, 含 `/api/pool/history` → 回填结果游客可浏览)。

```mermaid
flowchart LR
    OP[Operator] -->|POST /api/pipeline/backfill<br>start/end/max_days| EP[api/pipeline.py:89 pool_backfill]
    EP -->|job_store.create 单飞| JS[(job_store)]
    EP -->|try_acquire_run_slot| SLOT{执行槽空闲?}
    SLOT -- no --> FAIL[失败记录: 已有数据任务在运行]
    SLOT -- yes --> EX[run_in_executor _long_task_executor<br>pipeline.py:151-156]
    EX --> SVC[services/pool_backfill.py:30<br>run_pool_backfill]
    SVC --> GAP[list_backfill_gaps<br>pool_snapshot.py:157<br>enriched − snapshot 升序]
    GAP --> LOOP{每个缺口日}
    LOOP --> CANCEL{job 状态 failed?}
    CANCEL -- yes --> DONE[终态 6 键 dict]
    CANCEL -- no --> RUN[ScreenerService.run_all_with_hits<br>screener.py:723 → engine.run engine.py:295<br>竞价短路 engine.py:345-348]
    RUN --> PERSIST[persist_point_snapshot<br>origin='backfill' pool_snapshot.py:52<br>原子写 part.json]
    PERSIST --> LOOP
    LOOP -- 失败日记 failed_dates 继续 --> LOOP
    OP -->|GET /api/pipeline/jobs/{id}| JS
    OP -->|GET /api/pool/history?as_of=D| HIST[pool_hub.py:293 build_pool_hub_snapshot<br>→ _build_concept_map as_of pool_hub.py:61]
```

### 1.1 POOL-03 守卫交织 (回填合规证明, 24-01-SUMMARY E1-E6 全绿)
- 触发面只在 `api/pipeline.py` (非 pool 面) → E4 (`test_pool_hub.py:807-813` GET-only) 不破; `pool_backfill.py` 不 import 执行族/strategy_cache (E1/E3 形); 只写 `screener_results` (E2, `_SNAPSHOT_ROOT` 引用)。
- **运行时无 token**: `_EXECUTION_TOKEN` 是测试侧 AST 正则 (test_pool_hub.py:858-861), 约束零执行只读面; 回填属 operator 执行面 (与 EOD 同类), 本就调 `run_all_with_hits`。
- 沙箱跑回填后必跑守卫回归: `test_pool_hub_no_execution_imports` / `test_pool_api_is_get_only` / `test_pool_snapshot_writes_only_screener_results` / `test_pool_snapshot_never_writes_runtime_cache` / `test_pool_api_no_compute_trigger` (+ `test_guest_masking.py` 游客面)。

---

## 2. 稀疏竞价湖交互 (Phase 32 落地后的关键新事实, 本会话实测)

### 2.1 湖现状 (磁盘实测, polars 校验)
- `data/kline_auction/`: **248 分区** (2025-07-29..2026-08-05), **2 symbols** (000001.SZ, 000002.SZ), **496 行** (248×2), 列 `[symbol, datetime, auction_volume, auction_amount, auction_virtual_price]` — 无 `auction_unmatched_volume` (上游无该字段, 32-RESEARCH §8 锁定) → 派生 `auction_unmatched_amount` 不产生。
- `data/kline_daily_enriched/`: 248 分区 (同上日期区间, 每区 ~5293 行/5537 symbols)。`data/screener_results/`: **0 分区** (空目录)。`data/ext_history/`, `data/premarket_results/`: **目录不存在**。
- Phase 32 冒烟 (32-02-SUMMARY): 端点对 2 码 × 248 日真实跑通, `{"rows": 496, "dates": 248, "failed": 0, ...}`, probe 当时 `available` (source `xyz`)。

### 2.2 注入双闸门 (竞价列是否进入回填帧)
`ScreenerService._load_enriched_for_date` 三条路径 (repo 最新日缓存 :252-270 / enriched 历史缓存 :272-282 / parquet 慢路径 :285-296) **全部以 `self._attach_auction(df, target_date)` 收尾** (:297, :325, :336) → `attach_auction_columns` (`auction_columns.py:93`):
- **闸门 1 (probe)**: `resolve_auction_probe().status == available` 否则原样返回 (列缺席, 诚实缺列) `:96-99`。`resolve_auction_probe` (`auction_probe.py:139-186`): 候选源 = custom + 内建链中 `capabilities.auction==True` 者 (`:86-116`); **xyz_provider 已声明 `auction=True`** (`xyz_provider.py:59`) → 沙箱必有候选 → **每次调用做一次 live HTTP** (`_default_fetcher` :117-118 对 PROBE_SYMBOL `000001` :17 取 `_last_trade_date()` = 最新 kline_daily 分区 :71-84; 超时 8.0s `xyz_provider.py:62-64`)。网络通 (Phase 32 冒烟证实) → `available`; 源挂 → `error`/`fail_closed`。
- **闸门 2 (分区)**: `kline_auction/date={d}/part.parquet` 存在且有行 `:101-112` — 回填 248 日**全部通过** (分区已齐)。
- 注入语义 (`:146-147`): 按 symbol 左联, 分区内有行但某 symbol 缺席 → **该 symbol 竞价列为 null** (诚实按标的缺席); symbol 级去重防 fan-out `:143-145`。

### 2.3 策略级后果 (运行 `run_all_with_hits` 时, 引擎策略全部参与, screener.py:744-750)
builtin 28 策略中 8 个竞价族 (`backend/app/strategy/builtin/`), 按 meta 分三类:

| 策略 | requires_auction_data | probe 非 available (列缺席) | probe available + 稀疏湖 (列注入, 5535 码 null) |
|---|---|---|---|
| auction_allround / auction_fast_grab / t1_flash | True | **0 行** — 引擎短路 `engine.py:345-348` (`auction_volume` 列缺席 → 空 StrategyResult) | **≤2 行** — 过滤器运行, polars null 比较恒假 → 仅 000001/000002 可能命中 (阈值若满足; 含 `pl.lit(False)` 列守卫双保险 `auction_allround.py:37-38`) |
| auction_intraday_confirm | True + minute_confirm_required=True | 0 行 | **恒 0 行** — `_minute_loader` 未装配 (`engine.py:151-163` 参数; main.py:556-565 构造未传) → `engine.py:376-378` required → 空池 |
| auction_alpha | False (列存在性选分支) | **派生分支** (open_gap+vol_ratio_5d+amount) 全市场正常结果 | **真列分支** (`auction_volume_ratio`/`auction_amount`/`open_gap` ≥ 阈值) → ≤2 行 |
| auction_bullish / auction_early_star / auction_preopen_quant | 无 meta (纯派生列 open_gap/change_pct/vol_ratio_5d) | 全市场正常结果 | 全市场正常结果 (与 probe 无关) |

**诚实结论 (PB-01 预期声明):** 回填快照中竞价策略行数 = 双峰且**网络相关** — (a) probe fail-closed → `requires_auction_data` 策略 total=0, auction_alpha 走派生分支 (与 32 期前基线一致); (b) probe available → 竞价列注入, 这些策略最多命中 2 个标的 (大概率 0, 取决于样本码是否过阈值), 绝不产生全市场规模结果。**任一分支行内确定性成立** (策略过滤器对同输入帧确定; probe 判定在单次运行内恒定, `_last_trade_date` 固定 2026-08-05)。快照如实记录 (total=0 策略保留, pool_snapshot.py:87-93)。`engine=None` 直调服务 (PRESET-only) → 竞价策略不参与 → **完全确定**, 是纯链路验证的捷径 (见 §3.3)。

### 2.4 附带成本 (24-RESEARCH 未计的新增项)
每次 `_attach_auction` 触发一次 live probe: 单日 +1.6s 名义 / 8s 超时上限。248 日全量回填, 源挂时最坏 **+~33 分钟纯超时**; 子集 10 日 → +16-80s。确定性断言 (cache byte-identical / 幂等) 不受影响。

---

## 3. 沙箱子集流程 (PB-01, 最小可行运行)

### 3.1 前置 (全部实测满足)
- enriched 248 分区 (2025-07-29..2026-08-05); `screener_results/` 0 分区 → 缺口 = 248。
- 策略参数确定: 7 PRESET 内置 (screener.py:30) + builtin 28 引擎策略; `data/user_data/strategy_overrides/` 空 (0 文件, 实测) → 默认参数; `data/strategies/custom|ai` 不存在 → 无自定义/无 AI 策略。
- 启动成本: `_refresh_enriched` 启动预计算全历史 `_enriched_history_cache` (`repository.py:461` `_refresh_enriched`, :556-570 全历史缓存) → filter_history 策略 `_load_enriched_history` (screener.py:405, 优先级 1 repo 缓存) 基本 0ms; 慢路径 `_compute_enriched_full` (:354, **150 日窗口** :363) 是单日主成本。

### 3.2 精确参数
- **推荐日期窗**: `start=2026-07-27&end=2026-08-05` (最近 8 个连续交易日, 完整 150 日 warmup → 单日成本对全量运行有代表性)。纯 `max_days=10` 会取 248 缺口**最早** 10 日 (2025-07-29 起) — 更便宜 (湖起点无历史 warmup) 但成本不代表性。
- **Universe**: 全 5537 symbols。回填路径**无 universe 参数** (端点仅 start/end/max_days, pool_backfill.py:58-63; run_all_with_hits 无 pool 入参) — "最小运行"只能按**日**子集, 不能按标的子集。
- **触发**: 起服务 (`cd backend && uv run uvicorn app.main:app --port 3018`, README.md:54) → `curl -X POST localhost:3018/api/pipeline/backfill -H 'Content-Type: application/json' -d '{"start":"2026-07-27","end":"2026-08-05"}'` → `{"status":"started","job_id":...}`; 轮询 `GET /api/pipeline/jobs/{id}`。

### 3.3 期望产出 (验收口径)
1. `data/screener_results/date=2026-07-27..08-05/part.json` 8 个, `snapshot_origin=="backfill"` (jq 抽查), `strategy_version` 非空指纹。
2. `strategy_cache.json` 前后 byte-identical (D2; 沙箱若不存在则不创建)。
3. `GET /api/pool/dates` → `count==8`, `backfill_needed==240`; 二次重跑同参数 → `requested:0` (幂等, 缺口差集)。
4. `GET /api/pool/history?as_of=2026-07-27` → 200, strategies 渲染, `snapshot_origin:"backfill"`, `concept_attribution:"current_snapshot"` (ext_history 缺失, §5)。
5. 竞价策略行数符合 §2.3 双峰表 (记录 probe 判定); PRESET + 派生-only 竞价策略 (auction_bullish/early_star/preopen_quant) 正常全市场结果。
6. **确定性捷径**: 纯链路验证 (cache 断言/幂等/origin) 可用直调 `run_pool_backfill(repo, engine=None, start=..., end=...)` (PRESET-only, 无竞价策略, 无 live probe 分支差异 — 注: probe HTTP 仍在 `_attach_auction` 触发, 但不再影响输出行); 端点全策略跑作为对照观察 §2.3 行为。

### 3.4 耗时与存储
- **耗时 (8 日)**: 8 × (单日 5-30s [INFERENCE, 24-RESEARCH.md:83] + probe ~2-8s) ≈ **1-5 分钟**; 248 日 ≈ **20-120 分钟** [INFERENCE, 24-RESEARCH R2 :352] + probe 开销 (源挂 +33min 最坏)。
- **存储 (8 日)**: ~2-16 MiB (0.2-2 MiB/日 [INFERENCE, R4 :354]); 实测锚点: enriched 湖 52 MiB/248 日 ≈ 0.21 MiB/日 (parquet), JSON 快照同量级或略高; 全量 248 ≈ 50-500 MiB。`data/` 现 105 MiB, 磁盘余量 1013 GiB (`df -h /home/orca/source` 48% 用) → **非阻塞**。
- 无跨日 warmup 复用 (升序是正确基线, D5; 摊销优化需改 seam, 非本期)。

---

## 4. 验证设计 (PB-01/03 新测试, 沿用既有约定)

### 4.1 既有覆盖 (本会话收集, 全部可复用)
- **回填服务/端点**: `tests/test_pool_backfill.py` 9 用例 — `test_pool_backfill_replays_gaps_ascending`, `test_backfill_never_touches_strategy_cache` (D2 byte-identical), `test_pool_backfill_idempotent_skips_existing_snapshots`, `test_pool_backfill_bounds`, `test_pool_backfill_cooperative_cancel`, `test_pool_backfill_failed_days_continue`, `test_backfill_endpoint_singleflight_and_reuse`, `test_backfill_endpoint_parameter_validation`, `test_backfill_endpoint_runs_in_executor_and_succeeds`。
- **EOD job**: `tests/test_pool_eod_job.py` 6 用例 (写快照+cache / skip 语义 / 注册形 / concept capture 非致命)。
- **快照服务**: `tests/test_pool_snapshot.py` 12 用例 (origin round-trip / 旧 payload 容错 / gaps / D6 `test_run_all_historical_asof_skips_cache_write` :441)。
- **读侧渲染**: `tests/test_pool_hub.py` 47 用例 — `test_pool_history_snapshot`, `test_pool_history_snapshot_origin_passthrough`, `test_pool_history_snapshot_origin_default_eod`, `test_pool_history_missing_available_false`, `test_pool_dates_backfill_needed_zero_when_all_covered`; POOL-03 AST 守卫 (E1-E6) 同文件 :788-922。
- **概念 PIT 读侧**: `tests/test_concept_history.py` — `test_build_pool_hub_snapshot_as_of_partition_priority`, `test_attribution_three_state_machine`, `test_pool_history_api_passthrough_as_of_snapshot`; `tests/test_concept_seam.py` 8 用例。
- **盘前诚实**: `tests/test_premarket_pool.py` 12 用例 — `test_premarket_api_empty_state_200`, `test_premarket_preview_never_touches_eod_store`。
- **约定** (回填测试不跑真 screener): `monkeypatch.setattr(ScreenerService, "run_all_with_hits", fake)` + `_FakeRepo` 桩 + `_make_env` 造分区目录 (test_pool_backfill.py:32-50, :78-88); EOD 侧用 canned 策略目录造引擎 (test_pool_eod_job.py:28-54)。

### 4.2 新增测试 (名称 + 落点 + 断言)
| 测试名 (建议) | 文件 | 断言 (可观察契约) |
|---|---|---|
| `test_backfill_endpoint_subset_bounds_integration` | `tests/test_pool_backfill.py` | 端点带 start/end/max_days=5 于 tmp data_dir (fake repo + patch run_all_with_hits): 仅 5 个缺口日写盘, 全部 `snapshot_origin=="backfill"`, `strategy_version=="unknown"` (engine=None 直调) 或指纹 (engine 注入), 升序; 终态 6 键精确集 |
| `test_backfill_endpoint_never_touches_strategy_cache` | `tests/test_pool_backfill.py` | 经**端点** (executor 路径) 跑子集: `strategy_cache.json` 前后 byte-identical; 不存在则不创建 (镜像服务级 `test_backfill_never_touches_strategy_cache`) |
| `test_backfill_endpoint_idempotent_rerun_subset` | `tests/test_pool_backfill.py` | 二跑同参数 → `requested:0`; `GET /api/pool/dates` `backfill_needed == 总缺口-5` |
| `test_backfill_auction_sparse_lake_honest_rows` | `tests/test_pool_backfill.py` | 真 polars 帧: enriched 帧含 5 symbols + `kline_auction/date=D/part.parquet` 仅 2 symbols; `monkeypatch` `auction_probe.resolve_auction_probe` → ① available: canned `requires_auction_data=True` 策略 (canned 策略文件, 镜像 test_pool_eod_job) 经 engine.run → rows ⊆ {2 symbols} (稀疏诚实); ② fail_closed: 该策略 `total==0` (引擎短路); ③ auction_alpha 分支切换 (真列分支 vs 派生分支列集) |
| `test_pool_history_renders_backfilled_snapshot` | `tests/test_pool_hub.py` | tmp 写 `origin="backfill"` 快照 → `GET /api/pool/history?as_of=D` 200, strategies/rows/total 渲染, `snapshot_origin=="backfill"`, `updated_at==computed_at` |
| `test_pool_history_backfilled_date_concept_fallback` | `tests/test_concept_history.py` (或 test_pool_hub.py) | 回填快照 + 无 `ext_history/gn_ths/D` 分区 → `/pool/history?as_of=D` `concept_attribution=="current_snapshot"` 且**不追加** `concept_effective_date`/`concept_captured_at` 键 (键集锁, 镜像 T-22-06) |
| `test_pool_backfill_never_creates_premarket_root` (可选, PB-04 结构门) | `tests/test_premarket_pool.py` | 回填子集后 `data/premarket_results/` 不存在 (root 隔离锁) |

注: (a) 子集"集成测试"= 服务+端点级 (patch run_all_with_hits), 不跑真 5537×150 日重算 (hermetic, 镜像既有约定); **真实 8 日湖上运行**是 sandbox 验收步骤 (§3.2) 而非单元测试。(b) 不新增测试文件 — 4 个既有文件扩展, 符合仓库约定。(c) probe 状态注入沿用 `test_build_premarket_preview_probe_three_states` 的 resolver 注入形。

**验证命令:** `cd backend && .venv/bin/python -m pytest tests/test_pool_backfill.py tests/test_pool_hub.py tests/test_concept_history.py tests/test_premarket_pool.py -x -q` + 守卫回归 `tests/test_pool_hub.py::test_pool_hub_no_execution_imports tests/test_pool_hub.py::test_pool_api_is_get_only tests/test_pool_hub.py::test_pool_snapshot_writes_only_screener_results tests/test_pool_hub.py::test_pool_snapshot_never_writes_runtime_cache` + `tests/test_guest_masking.py` (游客白名单零改动)。

---

## 5. PIT 联动 (PB-03)

- 读侧已就绪: `/pool/history?as_of=D` → `build_pool_hub_snapshot` (pool_hub.py:293) → `_project_hub(..., as_of=snap["as_of"])` (:311-318) → `_build_concept_map(data_dir, as_of)` (:161-162) → 分区命中 `as_of_snapshot` / 未命中回退 `current_snapshot`|`unavailable` (pool_hub.py:66-70, :135-141)。
- **沙箱现状** (实测): `ext_history/` 目录不存在 → 回填 248 日全部渲染 `concept_attribution=="current_snapshot"` — 诚实回退, **非 PIT 伪造** (CONCEPT-05 禁止把当前概念快照标成历史日)。PB-03 验收 = 此回退在回填快照上端到端成立 (测试 §4.2)。
- **前向链** (部署后才真实): 真实 EOD → `concept_history.capture` (daily_pipeline.py:1017) 写 `ext_history/gn_ths/date=D` 分区; 沙箱无 EOD → 不可模拟 (诚实答案: 否)。既有测试已锁读侧 (test_concept_history.py 3 用例)。
- 结论: **PB-03 = 验证 + 记录, 零新代码面**; 不建任何"概念历史回填"写路径。

---

## 6. premarket 诚实缺口 (PB-04)

- 唯一创建方 = 09:26 job `_premarket_pool_preview` (daily_pipeline.py:1024-1076, 注册 :1168-1173, id `premarket_pool_preview` :969) → `premarket_snapshot.persist_premarket_snapshot` (:1063) 写 `data/premarket_results/date={T}/part.json` (premarket_snapshot.py:47-48)。
- **部署门禁**: scheduler 仅非 fixture_mode 启动 (main.py:510-520; `fixture_mode = PHASE1_FIXTURE_MODE` env :119); 沙箱从不跑 cron → 目录永不产生 (实测不存在)。
- **数据门禁**: `build_premarket_preview` (premarket_pool.py:30-90) 以 as_of=今日读 live enriched (:40-42 注释"盘前不存在 → 空帧 → available:false"); 沙箱今日无 EOD → `if not results: return {"available": False, "degraded": True, ...}` (:71-79); probe 非 available → `degraded:true` (:86)。
- **PB-04 = 记录维持现状**: 文档 (runbook/features.md) 注明需真实部署 + 实时 09:15-09:25 竞价数据; 无沙箱产物; 前端空态已诚实 (api/pool.py:119-133 `GET /api/pool/premarket`)。

---

## 7. 运营手册大纲 (PB-02, 全量 248)

1. **前置检查**: `df -h data/` (余量 ≥ 1 GiB; 实测 1013 GiB 空闲); `ls data/kline_daily_enriched | wc -l` == 248; `ls data/screener_results 2>/dev/null | wc -l` == 0 (或记当前缺口); 确认网络 (probe 每日常量 1 次 live HTTP, 8s 超时 — 源挂则 +33min 最坏)。
2. **起服务**: `cd backend && uv run uvicorn app.main:app --port 3018`; 等启动日志 enriched refresh 完成 (全历史预计算, filter_history 策略此后 ~0ms)。
3. **触发**: `curl -X POST localhost:3018/api/pipeline/backfill -H 'Content-Type: application/json' -d '{}'` — **单次调用即可**: max_days 上限 500 ≥ 248 (pipeline.py:115-121), 无需分块; 可选显式界 `'{"start":"2025-07-29","end":"2026-08-05"}'`。
4. **轮询**: `curl localhost:3018/api/pipeline/jobs/{id}` → status/progress/stage; 终态 6 键 (requested/backfilled/failed/failed_dates/origin:"backfill")。
5. **取消**: `curl -X POST localhost:3018/api/pipeline/jobs/{id}/cancel` → 合作式, 当前日完成后停 (pool_backfill.py:77-81)。
6. **失败处理**: `failed_dates` 列表即剩余缺口; 直接重跑同端点 (幂等只补缺口); 单飞/执行槽互斥 → 与 EOD/手动 run_all/竞价回填并发时 fail 记录 `"已有数据任务在运行"`。
7. **跑后验证**: `ls data/screener_results | wc -l` == 248; `jq -r '.snapshot_origin' data/screener_results/date=2026-08-05/part.json` == `backfill` (**provenance 在分区 payload 内**: `snapshot_origin` 键 + `strategy_version` 指纹, pool_snapshot.py:83-93 — 无独立 manifest, 无文件系统元数据); `curl localhost:3018/api/pool/dates` → `count==248, backfill_needed==0`; `curl "localhost:3018/api/pool/history?as_of=2025-07-29"` 渲染; 抽查竞价策略行数符合 §2.3。
8. **预期**: 20-120 分钟 [INFERENCE] + probe 开销; 存储 50-500 MiB [INFERENCE] (实测锚点 enriched 52 MiB/248 日); `strategy_version` = 回填时刻策略集指纹 — 后续改策略需重跑 (诚实重算语义, R3)。

---

## 8. 计划拆分建议 (3 plans)

| Plan | 内容 | 落点 (文件) | 验证命令 |
|---|---|---|---|
| **33-01** | 沙箱子集运行 (§3) + 集成测试 (a/b/c) + cache byte-identical | `tests/test_pool_backfill.py` + 4 新用例 (§4.2 前三); sandbox 真实 8 日运行记录 | `pytest tests/test_pool_backfill.py -x -q` + 手动 POST/轮询/jq 抽查 (§3.3) |
| **33-02** | PIT 回退 + /pool/history 渲染验证 (PB-03) | `tests/test_pool_hub.py` + `tests/test_concept_history.py` 各 1 用例 (§4.2 后二) | `pytest tests/test_pool_hub.py tests/test_concept_history.py -x -q` + 对回填日 curl 抽查 |
| **33-03** | 运营手册落地 (PB-02) + premarket 缺口文档 (PB-04) + features.md 对账 | docs/features.md (或 ops 文档) + 可选结构门测试 (§4.2 末) | `pytest tests/test_premarket_pool.py -x -q` + 手册步骤 7 复验 |

依赖: 33-01 先行 (产出真实快照供 33-02 渲染验证与 33-03 手册实证); 33-02/33-03 可并行。

---

## 9. 风险 / 未知

| 风险 | 等级 | 缓解 |
|---|---|---|
| 全量耗时 20-120min [INFERENCE] + probe 8s/日 (源挂 +33min 最坏, **新识别**) | 中 | 子集先行; 单次 248 调用即可; 合作取消; 升序; 后台 executor 零阻塞; 若实测过慢 → 共享 warmup seam (24-RESEARCH R2) |
| 存储 50-500 MiB [INFERENCE] (实测锚点 enriched 52 MiB/248 日) | 低 | 磁盘余量 1013 GiB, 非阻塞; 膨胀路径 = JSON→Parquet (R4) |
| 竞价策略行数双峰 (probe 网络相关) | 低 (已诚实) | §2.3 预期表写入计划; `engine=None` 直调 = 完全确定链路验证; 快照如实记录 total=0 |
| 策略参数默认值漂移 | 低 | overrides 空 (实测); strategy_version 指纹留痕; 策略变更 → 重跑诚实重算 |
| 与 EOD/手动 run_all/竞价回填并发写 | 中 | job_store 单飞 + `try_acquire_run_slot` 全局互斥 (失败如实记录); 原子幂等覆盖 |
| `if results:` 语义 (全策略异常 → 不写分区, 日留缺口) | 低 | 重跑幂等补上; failed_dates 如实 |
| 未知: PRESET 策略 7 个的 exact 参数 (screener.py:30) | 低 | 运行产物即事实 (快照行数/内容可复查) |

---

## 10. 置信度

| 章节 | 置信度 | 依据 |
|---|---|---|
| §1 回填链 machinery | **HIGH** | 本会话逐行读 pipeline.py/pool_backfill.py/pool_snapshot.py/screener.py/pool_hub.py/api/pool.py |
| §2 稀疏竞价湖交互 | **HIGH** | 湖磁盘实测 (polars: 248 分区/2 码/496 行) + engine.py/auction_columns.py/auction_probe.py/xyz_provider.py 全读; 行数双峰为逻辑推演 (null 比较恒假), 非实测运行 |
| §3 子集流程 | **HIGH** (参数) / **MEDIUM** (耗时 [INFERENCE]) | 参数/产出逐项核实; 5-30s/日 沿袭 24-RESEARCH 未实测 |
| §4 验证设计 | **HIGH** (约定) / **MEDIUM** (新用例断言细节) | 既有测试名全收集; 新用例按约定设计, 未执行 |
| §5 PIT | **HIGH** | ext_history 缺失实测 + pool_hub.py 全读 + 既有测试覆盖 |
| §6 premarket | **HIGH** | 门禁代码全读 + 目录缺失实测 |
| §7 手册 | **HIGH** (机制) / **MEDIUM** (估算) | 机制逐行核实; 时间/存储为 [INFERENCE] |

**总体: 实施就绪 YES** — 唯一真正需要运行时确认的量是单日耗时 (决定全量是 20min 还是 120min), 子集先行即覆盖该风险。

---

## 11. 证据锚点索引 (本会话逐行核实)

| 锚点 | 位置 |
|------|------|
| OQ-1 定义 | `.planning/milestones/v2.1-MILESTONE-AUDIT.md:27` |
| Phase 24 交付 | `v2.1-phases/24-historical-archive/24-01-PLAN.md` (must_haves) / `24-01-SUMMARY.md` (D1/D2/D3/D5/D6 + E1-E6 全绿) / `24-RESEARCH.md:83,133-136,352-354` |
| 回填端点 | `backend/app/api/pipeline.py:89-90` (校验 :103-121, 单飞 :133-139, 执行槽 :143-147, executor :151-156, 响应 :162), jobs :169-190 |
| 回填服务 | `backend/app/services/pool_backfill.py:30` (缺口 :57, 限界 :58-63, 取消 :77-81, persist origin=backfill :84-90, failed_dates :91-95, 终态 :118-123) |
| 快照写/缺口/指纹 | `backend/app/services/pool_snapshot.py:52` (origin 校验 :68-70, payload :83-93, 原子写 :98-103), :129, :144, :157, :166 |
| 共享核心 | `backend/app/services/screener.py:723` (PRESET :30, 策略集 :744-750, 历史共享 :766-777, try/except :788-803, hit_factors :808-812); loaders :245/:299/:354/:405; latest_date :704 |
| 引擎竞价短路 | `backend/app/strategy/engine.py:295` (run), :345-348 (requires_auction_data), :376-390 (minute_confirm), :151-163 (minute_loader 参数) |
| 竞价列注入 | `backend/app/services/auction_columns.py:93` (双闸门 :96-99/:101-112, symbol 级 null :146-147); `auction_probe.py:17,71-84,86-116,117-118,139-186`; `xyz_provider.py:59` (auction=True), :62-64 (8s 超时) |
| 竞价策略 | `backend/app/strategy/builtin/` — auction_allround/fast_grab/t1_flash (requires=True), auction_intraday_confirm (True+minute), auction_alpha (False 分支), bullish/early_star/preopen_quant (纯派生) |
| EOD 前向 + 概念归档 | `backend/app/jobs/daily_pipeline.py:973,1017` |
| 盘前 job | `daily_pipeline.py:969,1024,1063,1168-1173`; `premarket_pool.py:30,71-79,86`; `premarket_snapshot.py:47-48` |
| 调度门禁 | `backend/app/main.py:119` (fixture_mode), :510-520 (scheduler); guest 白名单 :782-794 |
| PIT 读侧 | `backend/app/services/pool_hub.py:61,66-70,112-115,135-141,144,161-162,251-253,293,301-318,330-332`; `api/pool.py:79-113` (history), :55-77 (dates) |
| 启动缓存 | `backend/app/tickflow/repository.py:461` (_refresh_enriched), :556-570 (_enriched_history_cache 全历史) |
| D6 手动 run_all | `backend/app/api/screener.py:445-462` (latest-only write_cache :445-451, origin :457-462) |
| 湖现状 (实测) | kline_auction 248 分区 2025-07-29..08-05, 2 码, 496 行; kline_daily_enriched 248; screener_results 0; ext_history/premarket_results 不存在; data/ 105 MiB; 磁盘余量 1013 GiB |
| 测试收集 | test_pool_backfill 9 / test_pool_eod_job 6 / test_pool_snapshot 12 / test_pool_hub 47 / test_concept_history 15 / test_concept_seam 8 / test_premarket_pool 12 (pytest --collect-only 实测) |
| 服务器启动 | `README.md:54` — `uv run uvicorn app.main:app --port 3018` |
