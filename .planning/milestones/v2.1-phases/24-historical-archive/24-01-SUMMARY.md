---
phase: 24-historical-archive
plan: 1
subsystem: api
tags: [fastapi, pool, backfill, snapshot, provenance, screener, job-store]

# Dependency graph
requires: []
provides:
  - "persist_point_snapshot origin 参数 + payload snapshot_origin (eod/backfill/manual), schema_version=1"
  - "list_enriched_dates / list_backfill_gaps 纯读 helper (缺口单点)"
  - "run_pool_backfill 逐日回填服务 (缺口/升序/限界/进度/合作取消/失败继续, 绝不 write_cache)"
  - "POST /api/pipeline/backfill 触发端点 (operator-only, 单飞+执行槽+后台 executor)"
  - "api/screener.run_all D6 修复 (latest-only write_cache, 快照总是落盘 origin=eod/backfill)"
affects: [24-02 (backfill_needed + read-side provenance), pool_hub, api/pool, test_pool_eod_job, frontend PoolHubPage]

actuals:
  tokens: 9430   # 37723 diff bytes / 4 over the 6 realized files
  tasks: 3
  commits: 3

tech-stack:
  added: []   # 零新增外部运行时依赖 (锁定栈: fastapi/asyncio/polars stdlib)
  patterns:
    - "快照来源 provenance 字段 (snapshot_origin) 镜像 snapshot_type 枚举写法, 读侧缺省 eod"
    - "缺口驱动的批量回填 (enriched 分区 − 含 part.json 的快照分区, 升序摊销 warmup)"
    - "single-as_of 最新指针与历史日写路径严格分离 (latest-only cache 写闸门)"

key-files:
  created:
    - backend/app/services/pool_backfill.py
    - backend/tests/test_pool_backfill.py
  modified:
    - backend/app/services/pool_snapshot.py
    - backend/app/api/pipeline.py
    - backend/app/api/screener.py
    - backend/tests/test_pool_snapshot.py

key-decisions:
  - "D1: 回填触发端点放 api/pipeline.py (POST /backfill), 绝不放 /api/pool/* — POOL-03 E4 GET-only AST 守卫锁死"
  - "D2: 回填路径结构上绝不调 strategy_cache.write_cache; test_backfill_never_touches_strategy_cache byte-identical 断言锁死"
  - "D3: persist_point_snapshot 增 origin (默认 eod, 校验 {eod,backfill,manual}); payload 写 snapshot_origin; schema_version 保持 1; 旧 payload 缺字段读 eod"
  - "D5: job_store.create 单飞 + try_acquire_run_slot 重任务互斥 + run_in_executor(_long_task_executor) 请求内零阻塞 + 合作式取消 (每日期查 job 状态)"
  - "D6: api/screener.run_all 仅当 svc.latest_date()==as_of 才 write_cache; 快照总是落盘 origin='eod' if is_latest else 'backfill'"

patterns-established:
  - "回填 = _pool_eod_persist 单日序列 (run_all_with_hits → persist_point_snapshot) 的逐日循环版, 唯一差别是删掉 write_cache"
  - "端点镜像 extend_history (api/kline.py:633-700): 参数校验 + job_store.create + try_acquire_run_slot + run_in_executor + create_task"
  - "缺口单点 list_backfill_gaps = list_enriched_dates − list_snapshot_dates, 24-02 backfill_needed 复用"

requirements-completed: [HIST-01, HIST-02, HIST-04]

coverage:
  - id: D1
    description: "POST /api/pipeline/backfill 触发端点 — operator-only, 单飞复用活跃 job, 参数 400 校验 (start/end ISO + max_days 1..500), 后台 executor 执行, 返回 {status, job_id}"
    requirement: HIST-01
    verification:
      - kind: integration
        ref: "backend/tests/test_pool_backfill.py#test_backfill_endpoint_singleflight_and_reuse"
        status: pass
      - kind: integration
        ref: "backend/tests/test_pool_backfill.py#test_backfill_endpoint_parameter_validation"
        status: pass
      - kind: integration
        ref: "backend/tests/test_pool_backfill.py#test_backfill_endpoint_runs_in_executor_and_succeeds"
        status: pass
    human_judgment: false
  - id: D2
    description: "回填路径绝不写 strategy_cache.json (byte-identical / 不创建断言)"
    requirement: HIST-01
    verification:
      - kind: unit
        ref: "backend/tests/test_pool_backfill.py#test_backfill_never_touches_strategy_cache"
        status: pass
    human_judgment: false
  - id: D3
    description: "persist_point_snapshot origin 参数 + snapshot_origin 字段 (eod/backfill/manual), schema_version=1, 旧 payload 缺字段读 eod; list_enriched_dates/list_backfill_gaps helper"
    requirement: HIST-02
    verification:
      - kind: unit
        ref: "backend/tests/test_pool_snapshot.py#test_snapshot_origin_explicit_and_default"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_snapshot.py#test_snapshot_origin_tolerance_old_payload"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_snapshot.py#test_list_enriched_dates_and_backfill_gaps"
        status: pass
    human_judgment: false
  - id: D5
    description: "回填服务逐日重放 (缺口/升序/限界/进度/合作式取消/失败继续) — run_pool_backfill 返回 {requested, backfilled, failed, failed_dates, origin}"
    requirement: HIST-01
    verification:
      - kind: unit
        ref: "backend/tests/test_pool_backfill.py#test_pool_backfill_replays_gaps_ascending"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_backfill.py#test_pool_backfill_bounds"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_backfill.py#test_pool_backfill_cooperative_cancel"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_backfill.py#test_pool_backfill_failed_days_continue"
        status: pass
    human_judgment: false
  - id: D6
    description: "api/screener.run_all D6 修复 — 历史 as_of 不写 strategy_cache (latest-only), 快照总是落盘 origin=eod/backfill"
    requirement: HIST-04
    verification:
      - kind: unit
        ref: "backend/tests/test_pool_snapshot.py#test_run_all_historical_asof_skips_cache_write"
        status: pass
      - kind: integration
        ref: "backend/tests/test_pool_hub.py (POOL-03 E1-E6 守卫全绿)"
        status: pass
    human_judgment: false

# Metrics
duration: 18min
completed: 2026-08-06
status: complete
---

# Phase 24 Plan 1: 回填核心 (Backfill Core) Summary

**snapshot_origin provenance (eod/backfill/manual) + 缺口 helper + `run_pool_backfill` 逐日回填服务 + `POST /api/pipeline/backfill` 触发端点 + `api/screener.run_all` D6 latest-only cache 指针修复**

## Performance

- **Duration:** ~18min (估算)
- **Started:** 2026-08-06
- **Completed:** 2026-08-06
- **Tasks:** 3 / 3
- **Files modified:** 4 源码 + 2 测试 (6 files)

## Accomplishments
- **HIST-02 写侧 provenance:** `persist_point_snapshot` 增 `origin: str = "eod"` 参数 (校验 ∈ {eod, backfill, manual}), payload 写 `snapshot_origin`, `schema_version` 保持 1, 旧 payload 缺字段读侧默认 eod (向后兼容锁)。
- **缺口单点:** 新增纯读 helper `list_enriched_dates` (glob `kline_daily_enriched/date=*` 升序) 与 `list_backfill_gaps` (= enriched − 含 part.json 的快照分区, 升序), 24-02 `backfill_needed` 直接消费。
- **HIST-01 回填服务:** 新 `services/pool_backfill.py::run_pool_backfill` — 复用与 EOD/手动 run_all 完全相同的 `run_all_with_hits` + `persist_point_snapshot(origin="backfill")` 单条代码路径; 缺口集/升序/start-end-max_days 限界/进度回调/合作式取消 (job failed 即停)/失败日记录继续;**结构上绝不 import 或调用 `strategy_cache.write_cache`** (D2 byte-identical 断言锁死)。
- **HIST-01 触发端点:** `POST /api/pipeline/backfill` (放 `api/pipeline.py`, 绝不放 `/api/pool/*` — E4 GET-only 守卫锁死)。镜像 `extend_history`: 参数校验 (start/end `^\d{4}-\d{2}-\d{2}$` + `date.fromisoformat` + start≤end; max_days 1..500) + `job_store.reap_stale`/`create` 单飞 + `try_acquire_run_slot` 重任务互斥 + `run_in_executor(_long_task_executor)` 请求内零阻塞 + `asyncio.create_task`。游客自动 401 (不在 `_GUEST_READ_GET_PATHS` 白名单且非 GET)。
- **HIST-04 D6 修复:** `api/screener.run_all` 仅当 `svc.latest_date() == as_of` 才 `strategy_cache.write_cache` (历史 as_of 不再污染 single-as_of 最新指针); 快照**总是**落盘, `origin = "eod" if is_latest else "backfill"`。

## Task Commits

Each task was committed atomically:

1. **Task 1: snapshot_origin + 缺口 helper** - `1df58d4` (feat)
2. **Task 2: run_pool_backfill 服务** - `1eb764a` (feat)
3. **Task 3: POST /backfill 端点 + D6 修复** - `e17477b` (feat)

## Files Created/Modified
- `backend/app/services/pool_snapshot.py` - persist_point_snapshot origin 参数 + snapshot_origin 字段; 新增 `_ENRICHED_ROOT` + `list_enriched_dates`/`list_backfill_gaps`
- `backend/app/services/pool_backfill.py` - 新服务: run_pool_backfill 逐日重放 (缺口/升序/限界/进度/取消/失败继续)
- `backend/app/api/pipeline.py` - 新增 POST /backfill 端点 (镜像 extend_history), import 面加 `re` + `date as date_type`
- `backend/app/api/screener.py` - run_all D6 修复 (latest-only write_cache + origin eod/backfill)
- `backend/tests/test_pool_snapshot.py` - origin round-trip/容错/gap helper 测试; D6 回归; _FakeRepo.enriched_latest_date; 精确键集断言更新
- `backend/tests/test_pool_backfill.py` - 新测试模块: 服务 6 例 (回放/byte-identical/幂等/限界/取消/失败继续) + 端点 3 例 (单飞/400 校验/executor+succeed)

## Decisions Made
- D1 端点位置: `api/pipeline.py` (POOL-03 E4 锁死 pool.py GET-only; pipeline.py 已有 job 生命周期基础设施)
- D2 回填绝不写 cache: byte-identical 断言 + 结构上不 import strategy_cache
- D3 snapshot_origin 字段: schema_version 保持 1, 读侧 `.get("snapshot_origin", "eod")` 容错旧快照
- D5 调度: job_store 单飞 + 重任务执行槽 + 后台 executor + 合作式取消 (每日期查 job 状态)
- D6 修复: latest-only cache 写闸门, 快照总是落盘

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] persist_point_snapshot docstring 转义回归 (DeprecationWarning)**
- **Found during:** Task 1 (pool_snapshot origin 字段)
- **Issue:** 编辑时 docstring 内 `\\d` 被写成了 `\d`, 触发 Python DeprecationWarning "invalid escape sequence '\d'" (原文为 `\\d` 双反斜杠)
- **Fix:** 恢复 docstring 双反斜杠转义 (`^\\d{4}-\\d{2}-\\d{2}$`), 与 HEAD 原文一致
- **Files modified:** backend/app/services/pool_snapshot.py
- **Verification:** `pytest tests/test_pool_snapshot.py -x -q` 无 warning, 11 passed
- **Committed in:** 1df58d4 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 Rule 1)
**Impact on plan:** 无 scope creep; 修复为文档字符串正确性, 不影响行为。

## Issues Encountered
- `test_pool_backfill_bounds` 首次实现复用了同一 `tmp_path` 三次, 前一次回填写的快照泄漏到后一次 → 改用独立子目录 (m1/m2/m3)。测试实现细节, 非计划偏差。
- `test_pool_backfill_cooperative_cancel` 初版 fake_get 对不存在的 job 返回 None (触发取消分支) → 改为前 2 次返回 running、之后返回 failed, 精确模拟合作式取消。测试实现细节, 非计划偏差。
- 环境缺陷: `GSD_RUNTIME=omp` 使 gsd-tools `query commit` 静默 no-op → 全部提交用 `git commit` 直接完成 (批次 context 既定)。

## User Setup Required
None - 零新增外部依赖, 无环境变量变更。

## Next Phase Readiness
- **24-02 消费点就位:** `list_backfill_gaps` (backfill_needed) + `persist_point_snapshot(origin=...)`/读侧缺省 (pool_hub 透传/EOD 断言) 签名可用。
- **D6 source guard:** `api/screener.py` `def run_all` 段内 `latest_date`/`is_latest` 均先于 `strategy_cache.write_cache`, 24-02 `test_screener_run_all_cache_write_is_latest_gated` 可直接通过。
- 回填链路完整: 端点到服务到 `screener_results/date={d}/part.json` (origin="backfill") 全链路测试绿; `strategy_cache.json` 回填前后 byte-identical。
- 无 blockers; POOL-03 守卫 (E1-E6) 全绿。

## Self-Check: PASSED
- 关键文件存在: pool_backfill.py / test_pool_backfill.py / 24-01-SUMMARY.md
- 提交存在: 1df58d4 (T1) / 1eb764a (T2) / e17477b (T3)
- 测试: 21 (24-01 套件) + 60 (回归: eod_job/hub/guest/factor_hits) 全绿

---
*Phase: 24-historical-archive*
*Completed: 2026-08-06*
