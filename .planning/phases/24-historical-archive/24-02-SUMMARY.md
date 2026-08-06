---
phase: 24-historical-archive
plan: 2
subsystem: api
tags: [pool, snapshot, backfill, provenance, gap-signal, fastapi, pytest]

# Dependency graph
requires:
  - phase: 24-historical-archive (24-01)
    provides: persist_point_snapshot(origin=...) + snapshot_origin 字段; list_enriched_dates/list_backfill_gaps helper; api/screener.py D6 fix
provides:
  - "GET /api/pool/dates 增 backfill_needed 缺口计数 + backfill_examples 升序前 5 示例日 (HIST-03)"
  - "build_pool_hub_snapshot 读侧透传 snapshot_origin (present 快照 .get(...,'eod'), 空态 None, 旧快照缺省 eod)"
  - "EOD job 落盘快照 snapshot_origin=='eod' 断言"
  - "D6 回归 source guard (run_all 段内 is_latest/latest_date 先于 strategy_cache.write_cache)"
  - "docs/features.md 股池日期导航小节补回填/缺口信号/provenance 说明"
affects: [frontend PoolHubPage 缺口横幅消费, 25-* phases]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 3110   # chars/4 over the realized diff (5 files, 24-02 commits only)
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []  # 零新增运行时依赖
  patterns: [snapshot_origin provenance 缺省 eod 读侧兼容, backfill_needed 缺口单点复用 list_backfill_gaps, D6 source guard 用 def run_all 段作用域]

key-files:
  created: []
  modified:
    - backend/app/services/pool_hub.py
    - backend/app/api/pool.py
    - backend/tests/test_pool_hub.py
    - backend/tests/test_pool_eod_job.py
    - docs/features.md

key-decisions:
  - "W-1 修订落地: D6 source guard 断言作用域限定 `src[src.index(\"def run_all\"):]`, 避开 _update_single_strategy_cache 的 write_cache"
  - "W-2 修订落地: docs verify 在 `cd backend` 后用 `cd ..` 回仓库根再 grep docs/features.md"
  - "test_pool_dates_api 精确相等断言更新为含新键 (属 HIST-03 合同变更, 非守卫破坏)"

patterns-established:
  - "snapshot_origin 读侧: snap.get(\"snapshot_origin\", \"eod\") 绝不用直取 (Pitfall 5)"
  - "缺口信号与回填共用 list_backfill_gaps 单点 (enriched 分区 − 快照分区)"

requirements-completed: [HIST-02, HIST-03, HIST-04]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "GET /api/pool/dates 返回 backfill_needed 缺口计数 + backfill_examples 升序前 5 示例日 (数据源 = list_backfill_gaps, GET-only 零执行)"
    requirement: HIST-03
    verification:
      - kind: integration
        ref: "backend/tests/test_pool_hub.py#test_pool_dates_api"
        status: pass
      - kind: integration
        ref: "backend/tests/test_pool_hub.py#test_pool_dates_backfill_examples_truncated"
        status: pass
      - kind: integration
        ref: "backend/tests/test_pool_hub.py#test_pool_dates_backfill_needed_zero_when_all_covered"
        status: pass
    human_judgment: false
  - id: D2
    description: "build_pool_hub_snapshot 读侧透传 snapshot_origin: present 快照透传 (缺省 eod), 旧快照无字段读 eod 不 KeyError, 空态 None"
    requirement: HIST-02
    verification:
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_pool_history_snapshot_origin_passthrough"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_pool_history_snapshot_origin_default_eod"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_pool_history_missing_available_false"
        status: pass
    human_judgment: false
  - id: D3
    description: "EOD job 落盘快照 snapshot_origin == 'eod' (缺省路径 provenance 锁)"
    requirement: HIST-02
    verification:
      - kind: unit
        ref: "backend/tests/test_pool_eod_job.py#test_pool_eod_persist_writes_snapshot_and_cache"
        status: pass
    human_judgment: false
  - id: D4
    description: "D6 回归 source guard: api/screener.py run_all 段内 is_latest/latest_date 均先于 strategy_cache.write_cache (历史 as_of 绝不写 cache 指针)"
    requirement: HIST-04
    verification:
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_screener_run_all_cache_write_is_latest_gated"
        status: pass
    human_judgment: false
  - id: D5
    description: "POOL-03 守卫 E1-E6 全绿 (E4 GET-only / E5 无计算触发 token / E6 响应无执行词汇), 新增键 backfill_needed/backfill_examples/snapshot_origin 不破坏"
    requirement: HIST-04
    verification:
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_pool_api_is_get_only"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_pool_api_no_compute_trigger"
        status: pass
      - kind: unit
        ref: "backend/tests/test_pool_hub.py#test_hub_response_has_no_execution_vocabulary"
        status: pass
    human_judgment: false
  - id: D6
    description: "docs/features.md 股池日期导航小节补 POST /api/pipeline/backfill 批量回填 + backfill_needed 缺口信号 + snapshot_origin provenance; '27 个内置策略' 计数保持 1 处"
    requirement: HIST-03
    verification:
      - kind: other
        ref: "grep -c '27 个内置策略' docs/features.md == 1 && grep -q backfill_needed && grep -q POST /api/pipeline/backfill"
        status: pass
    human_judgment: false

# Metrics
duration: 22min
completed: 2026-08-06
status: complete
---

# Phase 24 Plan 2: 缺口信号与读侧兼容 Summary

**GET /api/pool/dates 增 backfill_needed 缺口信号, 读侧 snapshot_origin 透传 (旧快照缺省 eod), EOD origin 断言 + D6 source guard 回归锁, docs 对账**

## Performance

- **Duration:** 22 min (等待 24-01 合入后执行)
- **Started:** 2026-08-06T03:15:00Z
- **Completed:** 2026-08-06T03:37:00Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- `GET /api/pool/dates` 响应增 `backfill_needed`(缺口计数)+ `backfill_examples`(升序前 5 示例日), 数据源 = 24-01 的 `list_backfill_gaps` 单点; 空态含 0/[], 全量已快照 → 缺口归零 (集成用例)
- `build_pool_hub_snapshot` 读侧透传 `snapshot_origin`: present 快照 `.get("snapshot_origin", "eod")` (旧快照缺字段不 KeyError), 空态 None; EOD job 落盘快照断言 `snapshot_origin=="eod"`
- D6 回归 source guard: `run_all` 段内 `is_latest`/`latest_date` 均先于 `strategy_cache.write_cache` (历史 as_of 手动 run_all 绝不写 cache 指针)
- POOL-03 守卫 E1-E6 全绿: `api/pool.py` 只加只读字段, 无 POST/无 run_all/write_cache/persist_point_snapshot token
- `docs/features.md` 股池日期导航小节补回填/缺口信号/provenance 说明, "27 个内置策略" 计数保持 1 处

## Task Commits

Each task was committed atomically:

1. **Task 1: 读侧 snapshot_origin 透传 — build_pool_hub_snapshot + EOD origin 断言** - `30563cf` (feat)
2. **Task 2: backfill_needed 缺口信号 — GET /api/pool/dates 扩展 + test_pool_dates_api 同步 + 守卫回归** - `0a3d302` (feat), `e7b6148` (test: gap-zero 集成)
3. **Task 3: D6 回归 source guard + docs 对账** - `b84092d` (test)

**Plan metadata:** (SUMMARY commit 见 STATE.md 更新)

## Files Created/Modified
- `backend/app/services/pool_hub.py` - `build_pool_hub_snapshot` 空态加 `snapshot_origin: None`, present 分支透传 `snap.get("snapshot_origin", "eod")`
- `backend/app/api/pool.py` - `get_pool_dates` 增 `backfill_needed`/`backfill_examples` (消费 `list_backfill_gaps`), GET-only 保持
- `backend/tests/test_pool_hub.py` - `_write_snapshot` fixture 增 `origin` 参数; 新增 origin 透传/缺省/空态断言; `test_pool_dates_api` 精确断言更新; 缺口截断 + 缺口归零集成; D6 source guard
- `backend/tests/test_pool_eod_job.py` - EOD 快照断言 `snapshot_origin == "eod"`
- `docs/features.md` - 股池日期导航小节补回填/缺口信号/provenance

## Decisions Made
- W-1/W-2 修订落地 (来自 24-REVIEW): D6 source guard 作用域限定 `def run_all` 段; docs verify 在 `cd backend` 后回仓库根再 grep
- 新增 gap-zero 集成测试 `test_pool_dates_backfill_needed_zero_when_all_covered` 以显式满足 plan `<verification>` 第 3 条 (回填后缺口归零)

## Deviations from Plan

None - plan executed as written (含 REVIEW 已修订的 W-1/W-2 执行细节)。

---

**Total deviations:** 0 auto-fixed
**Impact on plan:** N/A — plan executed exactly as specified, W-1/W-2 修订按 24-REVIEW 建议落地.

## Issues Encountered
- Task 1 前置门初次执行失败 (24-01 未合入, `persist_point_snapshot` 无 `origin` 参数) — 按 precondition 协议等待 Executor24A 合入 24-01 Task 1 后重跑 gate 通过
- Task 1 引入空态 `snapshot_origin: None` 后, 既有精确断言 `test_build_pool_hub_snapshot_missing_available_false` 失败 — 同步更新该精确 dict 断言 (属 HIST-02 合同变更)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- 后端 API 契约就位: `GET /api/pool/dates` 新字段 (backfill_needed/backfill_examples) 可供前端 PoolHubPage 缺口横幅消费 (本期不触碰前端)
- 回填链路完整: POST /api/pipeline/backfill (24-01) → 快照湖 → gap 归零可观测; 历史视图 provenance 可分辨
- 守卫 E1-E6 全绿, D6 修复被 source guard 锁死

---
*Phase: 24-historical-archive*
*Completed: 2026-08-06*
