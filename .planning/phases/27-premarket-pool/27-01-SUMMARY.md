---
phase: 27-premarket-pool
plan: 1
subsystem: api
tags: [premarket, screener, apscheduler, polars, fastapi, guest-masking, open-gap, auction-probe]

# Dependency graph
requires:
  - phase: 26
    provides: auctionHistory API/hook + AuctionColumnStatusBadge 盘前分支 + DateNavigator EOD-only
provides:
  - PM-01 09:26 盘前预览 job (premarket_pool_preview) + 独立存储 premarket_results/date={T}/part.json
  - PM-02 compute_enriched_today 补算 open_gap (与 EOD Pass 4 单一公式零漂移)
  - PM-03/04 后端半: GET /api/pool/premarket 只读端点 + guest 白名单 + POOL-03 AST 守卫
affects: [27-premarket-pool plan 2 (frontend premarket view + e2e), verifier]

# Actuals (#2632) — pairs with the plan's `estimate` (estimateTokens: 66000 / raw_tokens: 44000).
# Same estimateTokens scale (chars/4 over the realized diff), never a harness token count.
actuals:
  tokens: 9991       # 39964 chars / 4 over the realized diff (8 files, 976 insertions / 2 deletions)
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []          # 零新增运行时依赖 (apscheduler/fastapi/polars 全部既有)
  patterns:
    - "独立存储根 _PREMARKET_ROOT=premarket_results 与 EOD _SNAPSHOT_ROOT=screener_results 物理分离 (D3), temp+os.replace 原子写 + _DATE_RE 防路径穿越"
    - "job/service 绝不调 strategy_cache.write_cache / 绝不写 screener_results (镜像 pool_backfill.py:1-11 铁律)"
    - "probe 判定经 resolve_auction_probe 注入点消费, verdict 词汇 (status/source/probed_at/window/fallback/detail) 与 /api/data/auction-probe 一致, 端点零重探"
    - "open_gap 补算与 EOD Pass 4 逐字一致 + 'open_gap' not in columns 幂等守卫 (D2 单一实现)"

key-files:
  created:
    - backend/app/services/premarket_snapshot.py
    - backend/app/services/premarket_pool.py
    - backend/tests/test_premarket_pool.py
  modified:
    - backend/app/jobs/daily_pipeline.py
    - backend/app/indicators/pipeline.py
    - backend/app/api/pool.py
    - backend/app/main.py
    - backend/tests/test_guest_masking.py

key-decisions:
  - "固定 09:26 mon-fri Asia/Shanghai (CronTrigger + _PREMARKET_HOUR/_PREMARKET_MINUTE 常量), _run_tracked 单飞, misfire_grace_time=1800 (盘前窗口窄)"
  - "open_gap 补算放 compute_enriched_today (prev_close 对齐块后), 与 EOD Pass 4 同一公式; 预览服务零自算 (无第二实现)"
  - "盘前预览只落 premarket_results/date={T}/part.json; 绝不写 strategy_cache/screener_results (single-as_of 指针 + EOD 语义不动)"
  - "GET /api/pool/premarket 只读零执行 (POOL-03); 预览缺失 → 200 available:false 诚实空态 (非 404); guest 掩码 + 白名单就位"

patterns-established:
  - "独立只读端点进 _GUEST_READ_GET_PATHS (guest 先过 auth 中间件到达掩码, 不 401)"
  - "预览 payload 恒带 window:pre_open + provisional:true + degraded + probe (诚实标注, 绝不伪装收盘定稿)"
  - "存储层 _DATE_RE 只锁格式, 日历合法性由 API 层 date.fromisoformat 二次校验 (get_pool_history 先例)"

requirements-completed: [PM-01, PM-02, PM-03]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "PM-01 盘前预览垂直切片 — 09:26 job 注册形 (常量 + _run_tracked 单飞 + mon-fri cron) + 独立存储 premarket_results/date={T}/part.json + 诚实 skip 三态"
    requirement: "PM-01"
    verification:
      - kind: unit
        ref: "backend/tests/test_premarket_pool.py#test_premarket_job_registered_in_scheduler"
        status: pass
      - kind: unit
        ref: "backend/tests/test_premarket_pool.py#test_premarket_preview_never_touches_eod_store"
        status: pass
      - kind: unit
        ref: "backend/tests/test_premarket_pool.py#test_premarket_preview_skips_no_data_date"
        status: pass
      - kind: unit
        ref: "backend/tests/test_premarket_pool.py#test_premarket_preview_skips_no_app_state"
        status: pass
      - kind: unit
        ref: "backend/tests/test_premarket_pool.py#test_premarket_snapshot_storage_roundtrip_and_list"
        status: pass
    human_judgment: false
  - id: D2
    description: "PM-02 compute_enriched_today 补算 open_gap — 正常日数值 (open/prev_close−1) + prev_close≤0→None guard + 除权日口径 + 幂等不覆盖"
    requirement: "PM-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_premarket_pool.py#test_compute_enriched_today_open_gap_normal_day"
        status: pass
      - kind: unit
        ref: "backend/tests/test_premarket_pool.py#test_compute_enriched_today_open_gap_exdiv_caliber"
        status: pass
      - kind: unit
        ref: "backend/tests/test_premarket_pool.py#test_compute_enriched_today_open_gap_idempotent"
        status: pass
    human_judgment: false
  - id: D3
    description: "PM-03 probe 三态 + 诚实降级 — build_premarket_preview 注入 probe_resolver (not_configured/fail_closed/available → degraded 布尔 + probe.status 透传) + 空 results available:false"
    requirement: "PM-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_premarket_pool.py#test_build_premarket_preview_probe_three_states"
        status: pass
    human_judgment: false
  - id: D4
    description: "PM-03/04 后端半 — GET /api/pool/premarket 只读端点: 空态 200 available:false + 有预览投影 (total 权威 + window/provisional/degraded/probe 透传 + auction_columns real==[]) + guest 掩码"
    requirement: "PM-03"
    verification:
      - kind: unit
        ref: "backend/tests/test_premarket_pool.py#test_premarket_api_empty_state_200"
        status: pass
      - kind: unit
        ref: "backend/tests/test_premarket_pool.py#test_premarket_api_returns_stored_preview"
        status: pass
      - kind: unit
        ref: "backend/tests/test_premarket_pool.py#test_premarket_api_guest_mask"
        status: pass
      - kind: unit
        ref: "backend/tests/test_guest_masking.py#test_guest_cannot_read_authed_surfaces"
        status: pass
      - kind: unit
        ref: "backend/tests/test_guest_masking.py#test_guest_read_paths_are_get_only"
        status: pass
    human_judgment: false
  - id: D5
    description: "POOL-03 AST 守卫 — pool.py 路由全 GET / 无执行族 import / 无写路径 / 端点无 as_of/concept Query; 既有 test_pool_hub AST 守卫保持绿"
    verification:
      - kind: unit
        ref: "backend/tests/test_premarket_pool.py#test_premarket_api_pool03_ast_guard"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_pool_api_is_get_only"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_pool_hub_no_execution_imports"
        status: pass
    human_judgment: false

# Metrics
duration: 11min
completed: "2026-08-06"
status: complete
---

# Phase 27 Plan 1: Premarket Pool 后端 Summary

**09:26 盘前预览 job (premarket_pool_preview) 经 run_all_with_hits 生成今日股池到独立 premarket_results/date={T}/part.json (绝不污染 strategy_cache/screener_results) + compute_enriched_today 补算 open_gap (与 EOD Pass 4 单一公式) + probe 诚实降级语义 + 只读 GET /api/pool/premarket (空态 200, guest 白名单+掩码, POOL-03 AST 守卫)**

## Performance

- **Duration:** 11 min
- **Started:** 2026-08-06T08:05:00Z (approx)
- **Completed:** 2026-08-06T08:16:18Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments

- PM-01: `_premarket_pool_preview` 盘前 job — 固定 09:26 (mon-fri, Asia/Shanghai), `_run_tracked` 单飞, `_PREMARKET_JOB_ID`/`_PREMARKET_HOUR,MINUTE` 常量注册形锁死; 只落 `premarket_results/date={T}/part.json` (payload 含 window/pre_open + computed_at + provisional:true + degraded + probe), strategy_cache.json 与 screener_results/date=* 在 job 运行后不被改动 (PM-01 验收 3); 无数据日/无 app state → 诚实 skip 不写文件。
- PM-02: `compute_enriched_today` 在 prev_close 对齐块后补算 `open_gap = when(prev_close>0).then(open/prev_close−1).otherwise(None)`, 与 EOD Pass 4 (pipeline.py:499-507) 逐字一致 + 幂等守卫; 正常日数值/除权日口径/幂等 fixture 全绿; `compute_enriched` Pass 4 与 vol_ratio 块零改动。
- PM-03/04 后端半: `GET /api/pool/premarket` 只读端点 (POOL-03 零执行) — 预览缺失 → 200 `{available:false, degraded:true}` 空态 (非 404); 有预览 → `_project_hub` 同形状投影 (total 权威) + window/provisional/degraded/probe 透传 (端点零重探); guest → mode:guest + `mask_guest_hub`; `_GUEST_READ_GET_PATHS` 加 `/api/pool/premarket` (D5: guest 先到掩码不 401)。

## Task Commits

Each task was committed atomically:

1. **Task 1: PM-01 盘前预览垂直切片 (独立存储 + 编排服务 + 09:26 job + 注册 + 测试)** — `8063b95` (feat)
2. **Task 2: PM-02 open_gap 补算 seam — compute_enriched_today** — `8bdb35e` (feat)
3. **Task 3: PM-03/04 后端 — 只读 API + guest 白名单 + 空态/掩码/POOL-03 守卫** — `3cfad7b` (feat)

**Plan metadata:** pending (docs commit after this SUMMARY)

## Files Created/Modified

- `backend/app/services/premarket_snapshot.py` (created) - 独立盘前存储: `_PREMARKET_ROOT="premarket_results"` + `_DATE_RE` 防路径穿越 + temp/os.replace 原子写 `persist_premarket_snapshot` + `load_premarket_snapshot`/`list_premarket_dates`
- `backend/app/services/premarket_pool.py` (created) - `build_premarket_preview`: run_all_with_hits 单条代码路径 + probe verdict 注入点 + window/pre_open/provisional/degraded payload; 绝不写缓存
- `backend/app/jobs/daily_pipeline.py` (modified) - `cn_today` 模块级 import + `_PREMARKET_JOB_ID`/`_PREMARKET_HOUR,MINUTE` 常量 + `_premarket_pool_preview` job + start_scheduler CronTrigger 注册 (mon-fri 09:26 Asia/Shanghai, misfire_grace_time=1800)
- `backend/app/indicators/pipeline.py` (modified) - `compute_enriched_today` 补算 `open_gap` (Pass 4 逐字一致 + 幂等守卫)
- `backend/app/api/pool.py` (modified) - `GET /premarket` 只读端点 + imports (`cn_today`/`load_premarket_snapshot`/`_project_hub`)
- `backend/app/main.py` (modified) - `_GUEST_READ_GET_PATHS` 加 `/api/pool/premarket`
- `backend/tests/test_premarket_pool.py` (created) - 13 tests: 注册门禁/存储隔离/诚实 skip/存储校验/probe 三态/open_gap 三用例/API 空态+投影+掩码/POOL-03 AST 守卫
- `backend/tests/test_guest_masking.py` (modified) - 游客可 GET /api/pool/premarket + 非 GET 不放行 (T-19-03 扩宽)

## Decisions Made

- 固定 09:26 (不可配) — 位于 09:25 集合竞价撮合定盘后 / 09:30 连续竞价前, open 已定盘, open_gap 与 EOD 口径一致 (D1 推荐 A)。
- open_gap 补算放 `compute_enriched_today` (prev_close 对齐块后) — 单一实现复制 Pass 4 公式, 预览服务零自算 (D2 推荐 A)。
- 独立存储根 `premarket_results` — 与 screener_results 物理分离, `/api/pool/dates` 不枚举 → DateNavigator 天然只列 EOD 日 (D3 推荐 A)。
- `build_premarket_preview` 默认 probe_resolver=resolve_auction_probe, 测试注入点零签名改动 (D4); 端点零重探 (POOL-03)。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `strategy_fingerprint(None)` 防护 (engine 容错)**
- **Found during:** Task 1 (build_premarket_preview 实现)
- **Issue:** 计划动作原文 `"strategy_version": pool_snapshot.strategy_fingerprint(engine)` 无守卫; 当 engine=None (容错路径/测试无引擎) 时 `None.list_strategies()` 会崩溃。
- **Fix:** 改为 `pool_snapshot.strategy_fingerprint(engine) if engine is not None else "unknown"`, 镜像 pool_backfill.py 既有的 fingerprint 守卫。
- **Files modified:** backend/app/services/premarket_pool.py
- **Verification:** `test_build_premarket_preview_probe_three_states` 断言 `strategy_version == "unknown"` (engine=None)。
- **Committed in:** 8063b95

**2. [Rule 1 - Test construction] 存储层 `_DATE_RE` 只锁格式, 日历合法性在 API 层**
- **Found during:** Task 1 (test_premarket_snapshot_storage_roundtrip_and_list)
- **Issue:** 初始用例把 `"2026-13-01"` 列为 persist 非法 as_of, 但 `_DATE_RE` (镜像 pool_snapshot) 只校验 `YYYY-MM-DD` 格式, 日历合法性由 API 层 `date.fromisoformat` 二次校验 (get_pool_history 先例) — 断言会误失败。
- **Fix:** 从非法集移除 `"2026-13-01"`, 保留格式/路径穿越非法集 (`"../x"`, `"2026-8-6"`, `"2026/08/06"`, `123`, `None`)。
- **Files modified:** backend/tests/test_premarket_pool.py
- **Verification:** 存储校验用例过 (ValueError persist / None load)。
- **Committed in:** 8063b95

**3. [Rule 1 - Test construction] 除权日 fixture 口径 (open/prev_close 均乘 _adj_factor, 因子相消)**
- **Found during:** Task 2 (exdiv fixture)
- **Issue:** 计划例文「API 原始 prev_close=10.0 → 对齐后 9.0, open=8.64 → open_gap == −0.04」中 open=8.64 实际指对齐后 open; 代码中 open 与 prev_close 都乘 `_adj_factor`, 因子相消 → open_gap = raw_open/raw_prev_close − 1。
- **Fix:** fixture 用 open_raw=9.6, prev_close_raw=10.0, adj_factor=0.9 → 对齐后 open=8.64, prev_close=9.0, open_gap == 8.64/9.0 − 1 == −0.04 (与计划期望值逐位一致), 并断言对齐后口径 == EOD Pass 4 口径。
- **Files modified:** backend/tests/test_premarket_pool.py
- **Verification:** `test_compute_enriched_today_open_gap_exdiv_caliber` 三重 approx 断言过。
- **Committed in:** 8bdb35e

> W-1 (load_premarket_snapshot 独立 import + _project_hub 从 pool_hub import)、W-2 (注册用常量, 断言断常量赋值与 tokens)、W-3 (Task 2 verify 结构门 = grep -c compute_enriched_today ≥1) 已在计划内修订 (27-REVIEW), 按修订后动作执行, 非额外偏差。

---

**Total deviations:** 3 auto-fixed (1 Rule 3 blocking, 2 Rule 1 test-construction)
**Impact on plan:** 全部为保证正确性/鲁棒性的必要修正, 无 scope creep; 交付语义与计划一致。

## Issues Encountered

- Starlette TestClient per-request cookies 触发 DeprecationWarning (test_premarket_pool.py API 用例) — 无害, 既有仓库测试模式。

## Stub Tracking

无已知 stub — 空态 `available:false` 是诚实语义 (非占位); 零 TODO/placeholder。

## Threat Flags

无 — 新端点/白名单均在计划 threat_model 覆盖范围内 (T-27-01-01..07 全部 mitigate/accept, 零新增外部依赖 T-27-01-SC accept)。

## User Setup Required

None - 零新增外部运行时依赖; 无环境变量/配置。

## Next Phase Readiness

- 27-02 (前端盘前视图 + e2e) 的 `<precondition>` grep 门 (`GET /api/pool/premarket` 端点 + guest 白名单就位) 已满足 — 端点/白名单/独立存储均已合入。
- 后端验证汇总: `test_premarket_pool.py` 13 passed; 回归面 (test_pool_eod_job / test_pool_hub / test_guest_masking / test_auction_probe / test_auction_columns / test_pipeline_and_monitor_fixes) 90 passed; 结构门 `_PREMARKET_JOB_ID`>=3 / `premarket_results`>=2 / `pool/premarket`>=1 / `compute_enriched_today`>=1。

---
*Phase: 27-premarket-pool*
*Completed: 2026-08-06*

## Self-Check: PASSED

- SUMMARY.md 存在; 8 个计划文件全部存在 (3 created + 5 modified); 3 个 task commits (8063b95/8bdb35e/3cfad7b) 均在 git log 中核验。
- 验证: test_premarket_pool.py 13 passed; 回归面 90 passed; 结构门全绿。
