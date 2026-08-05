---
phase: 22-pool-date-navigation
plan: 2
subsystem: pool
tags: [pool-eod-persist, guest-whitelist, docs-reconciliation, apscheduler, frozen-snapshot]

# Dependency graph
requires:
  - phase: 22-pool-date-navigation (22-01)
    provides: ScreenerService.run_all_with_hits + pool_snapshot.persist_point_snapshot/strategy_fingerprint/list_snapshot_dates + GET /api/pool/dates + /api/pool/history + build_pool_hub_snapshot
provides:
  - POOL-06 盘后 EOD 股池持久化 job: pool_eod_persist (mon-fri, 管道时间+5min, _run_tracked 单飞, misfire_grace_time=3600)
  - 游客白名单扩展 (RQ5 E7): /api/pool/dates + /api/pool/history 游客可读 (GET-only + mode 词汇)
  - docs 对账: features.md 股池日期导航小节 + "27 个内置策略" 计数保持 1 处不漂移
affects: [23-frontend (DateNavigator 消费 dates/history 端点)]

# Tech tracking
tech-stack:
  added: []  # 零新增外部运行时依赖 (apscheduler 3.11.2 既有锁定)
  patterns:
    - "EOD job 直调 service 级共享核心 run_all_with_hits, 绝不 HTTP 自调 POST /api/screener/run_all"
    - "先 write_cache 刷新最新指针, 再 persist_point_snapshot 落冻结快照 (与手动 run_all 调用点 1 顺序一致)"
    - "_run_tracked 单飞复用: EOD job 与手动 run_all 并发写防护 (T-22-02-01)"
    - "无数据日/无 app state → 诚实 skip 不写任何文件 (成功标准 3 前置守卫)"

key-files:
  created:
    - backend/tests/test_pool_eod_job.py
  modified:
    - backend/app/jobs/daily_pipeline.py
    - backend/app/main.py
    - backend/tests/test_guest_masking.py
    - docs/features.md

key-decisions:
  - "OQ-1 DECISION 编码: 本期不做首日一次性全量回填; EOD 只向前生成, 历史缺口由手动 run_all 补齐"
  - "EOD job 注册用 _POOL_EOD_JOB_ID 常量 (id=_POOL_EOD_JOB_ID), grep 门禁同时锁常量值与 _run_tracked 包裹 + mon-fri cron 形"
  - "游客白名单两新路径加入 main.py _GUEST_READ_GET_PATHS (auth_middleware 路由前 401 拦截必须同步放行), _is_guest_readable 读同一集合无需改"
  - "docs 股池日期导航小节只做特性描述不枚举端点 (features.md 不建 API 参考章节)"

requirements-completed: [POOL-06]

# Metrics
duration: ~40min
completed: 2026-08-05
status: complete
---

# Phase 22 Plan 2: POOL-06 EOD 股池持久化 job + 游客白名单扩展 + docs 对账 Summary

**盘后定时 `pool_eod_persist` job 落地 (mon-fri, 管道+5min, 单飞): 经 `run_all_with_hits` 预生成冻结快照 + 刷新最新指针; 游客可读 /pool/dates + /pool/history (GET-only); features.md 股池日期导航小节, 策略计数 27 无漂移**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-08-05 (approx)
- **Completed:** 2026-08-05
- **Tasks:** 3
- **Files modified:** 5 (1 new test file + 4 modified)
- **Commits:** 4 (Task 1 / Task 2 / Task 3 / summary)

## Accomplishments

- **Task 1 (POOL-06)**: `start_scheduler` 注册独立 `pool_eod_persist` cron job (`_POOL_EOD_JOB_ID="pool_eod_persist"`, mon-fri, 管道时间 +5min 偏移含跨小时进位, `misfire_grace_time=3600`, `replace_existing=True`, `_run_tracked` 单飞包裹)。`_pool_eod_persist(on_progress=None)` 经 `_get_app_state()` 延迟取用 → `ScreenerService.latest_date()` (无数据日返回 `{"as_of": None, "skipped": "no data date"}`) → `run_all_with_hits(as_of, engine=...)` service 级共享核心 (**绝不 HTTP 自调**) → `strategy_cache.write_cache` 刷新最新指针 (顺带修复实测陈旧 as_of=2026-07-31) → `pool_snapshot.persist_point_snapshot` 落冻结式点快照 (strategy_version=指纹 + computed_at=ISO 秒)。
- **Task 2 (RQ5 E7)**: `main.py._GUEST_READ_GET_PATHS` 追加 `/api/pool/dates` + `/api/pool/history` (auth_middleware 路由前 401 拦截同步放行); `test_guest_masking.py` 三个白名单测试路径元组扩展 + history mode 词汇/6 位代码泄露断言。
- **Task 3 (docs 对账)**: `docs/features.md` 选股引擎节末尾追加「股池日期导航」小节 (冻结快照 / 日期列表 / as_of 取池 / EOD 预生成 / 诚实空态 / concept_attribution current_snapshot); "27 个内置策略" 计数保持 1 处。

## Task Commits

Each task committed atomically (plain git per harness rule; `gsd-tools query commit` silent no-op):

1. **Task 3 (docs 对账, 无 precondition 先做)** — `dd0a2b2` — `docs(22): 股池日期导航小节 — frozen snapshot + dates/history endpoints + EOD pre-generate (22-02 Task 3)`
2. **Task 2 (游客白名单扩展)** — `76f12aa` — `feat(22): 游客白名单扩展 /pool/dates + /pool/history (RQ5 E7, 22-02 Task 2)`
3. **Task 1 (EOD job)** — `0e68953` — `feat(22): 盘后 EOD pool_eod_persist job — 冻结快照 + 缓存刷新 + _run_tracked 单飞 (POOL-06, 22-02 Task 1)`

## Test Results

| Suite | Command | Result |
|-------|---------|--------|
| EOD job | `.venv/bin/python -m pytest tests/test_pool_eod_job.py -x -q` | 4 passed (writes snapshot+cache / skips no-data-date / skips no-app-state / registration grep gate) |
| Guest whitelist | `.venv/bin/python -m pytest tests/test_guest_masking.py -x -q` | 15 passed (既有 15 + 白名单扩展断言全绿; history mode 词汇 + 无 6 位代码泄露) |
| Combined (plan verify) | `.venv/bin/python -m pytest tests/test_pool_eod_job.py tests/test_guest_masking.py -x -q` | 19 passed |
| Regression (22-01 面) | `.venv/bin/python -m pytest tests/test_pool_hub.py -q` | 27 passed (单飞/白名单/投影不回归) |
| Docs gate | `test "$(grep -c "27 个内置策略" docs/features.md)" = "1" && grep -q "股池日期导航" docs/features.md` | PASSED |

## Deviations from Plan

### Sequencing / Tooling Deviations

**1. [Precondition wait] Task 1 与 Task 2 等待 22-01 合入**
- **原因:** 两个任务均有 `<precondition>` 门禁。初始检查 `app.services.pool_snapshot` 不存在 (`ModuleNotFoundError`)、pool.py 无 `/dates`+`/history` 路由 (`AssertionError`) → 先执行无 precondition 的 Task 3 (docs), 提交 `dd0a2b2`。
- **等待过程:** 与 22-01 executor (Executor2201) 经 hub 协调; 22-01 分 4 批合入 (`f33f6b7` pool_snapshot → `00279cf` pool_hub _project_hub → `8daa116` pool 端点+守卫 → `49f91f6` run_all_with_hits)。
- **恢复:** Task 2 在 `8daa116` (pool 端点落地, PRE-2 OK) 后立即执行并全绿; Task 1 在 `49f91f6` (run_all_with_hits, PRE-1 OK, 签名与计划契约逐参一致) 后执行并全绿。
- **未 invent 22-01 交付物:** 未自行实现 run_all_with_hits/persist_point_snapshot/路由, 全部消费 22-01 实际签名。

**2. [Grep gate 适配] 注册形断言改用常量引用**
- **原因:** 计划 Test 3 字面断言 `id="pool_eod_persist"`, 但计划 action 同时要求 `id=_POOL_EOD_JOB_ID` (常量)。源码含 `_POOL_EOD_JOB_ID = "pool_eod_persist"` 与 `id=_POOL_EOD_JOB_ID`, 不含字面 `id="pool_eod_persist"`。
- **Fix:** 测试断言 `_POOL_EOD_JOB_ID = "pool_eod_persist"` + `id=_POOL_EOD_JOB_ID` + `_run_tracked(_pool_eod_persist` + `CronTrigger(day_of_week="mon-fri"` + `timezone="Asia/Shanghai"`, 锁注册形意图不变。

**3. [Test 增补] 追加无 app state skip 测试**
- **原因:** `_pool_eod_persist` 实现含 `{"as_of": None, "skipped": "no app state"}` 分支 (计划 must_haves 之一), 但计划 Test 清单仅列 no-data-date skip。增补 `test_pool_eod_persist_skips_no_app_state` 覆盖该诚实分支。

---

**Total deviations:** 3 (1 precondition wait, 1 grep gate adaptation, 1 test supplement)
**Impact on plan:** 全部为保证正确性/可执行性的必要调整, 无 scope creep; 三任务功能与交付按计划完整落地。

## Issues Encountered

- **22-01 并行合并竞态**: 两 precondition 门禁初始失败属预期 (并行契约), 经 hub 协调等待后合入; 无代码冲突 (22-01/22-02 零文件重叠)。
- **gsd-tools 不可用**: `gsd-tools query commit` 静默 no-op, 按任务契约 fallback 到 plain git 原子提交。
- **Watchlist.tsx**: 用户未提交改动保持原样, 未 stage/commit (watchlist_touched=false)。

## User Setup Required

None - 零新增外部运行时依赖 (apscheduler 3.11.2 既有锁定)。

## Next Phase Readiness

- 每交易日盘后由 EOD job 预生成冻结快照, 首个历史日请求只读快照自给自足 (成功标准 3)。
- 游客可读日期导航 (dates + history), 与游客 hub 读一致。
- Phase 23 前端 DateNavigator 可直接消费 `GET /api/pool/dates` + `GET /api/pool/history?as_of=` (含空态 `available:false` 与 `concept_attribution: "current_snapshot"` 标注)。

## Self-Check: PASSED

- 5 个交付文件存在且仅这些文件被提交: `daily_pipeline.py` / `main.py` / `test_pool_eod_job.py` (new) / `test_guest_masking.py` / `docs/features.md` ✓
- 3 个任务提交存在: `dd0a2b2` / `76f12aa` / `0e68953` ✓
- 全部目标测试绿: test_pool_eod_job 4 + test_guest_masking 15 = 19 passed; test_pool_hub 回归 27 passed ✓
- docs grep 门禁通过: "27 个内置策略" 计数=1, 含 "股池日期导航" ✓
- Watchlist.tsx 未被本计划触碰 (watchlist_touched=false) ✓

---
*Phase: 22-pool-date-navigation*
*Plan: 22-02*
*Completed: 2026-08-05*
