---
phase: 05-optional-enhancements
plan: "37"
subsystem: forecast-api-authorization
tags: [forecast, sqlite, fastapi, idor, sse, pagination]
requires:
  - phase: 05-optional-enhancements
    plan: "23"
    provides: persisted Forecast transition history, Last-Event-ID resume, bounded subscriptions, immutable records
  - phase: 05-optional-enhancements
    plan: "25"
    provides: server-owned reviewer principal and atomic operational SQLite migrations
  - phase: 05-optional-enhancements
    plan: "34"
    provides: verified quantile artifact projection and calibration persistence
provides:
  - principal-plus-instrument SQL pages for Forecast jobs and records before count/order/limit/offset
  - persisted-owner detail and descendant joins for retry, SSE, record, path, outcome, and calibration boundaries
  - same-instrument dual-principal CR-03 IDOR matrix with zero-side-effect assertions
affects: [FORE-01, CR-03, forecast-api, forecast-repository]
tech-stack:
  added: []
  patterns:
    - principal ownership is resolved from request state and matched to immutable forecast_jobs.principal
    - record descendants inherit authorization through forecast_records.job_id joined to forecast_jobs
    - list totals and rows share the same SQL owner predicate before pagination
key-files:
  created:
    - .planning/phases/05-optional-enhancements/05-37-SUMMARY.md
  modified:
    - backend/app/forecast/repository.py
    - backend/app/forecast/api.py
    - backend/tests/forecast/test_api.py
key-decisions:
  - "Public job/record lists use dedicated owned SQL pages; API code never fetches an unbounded Forecast table and filters it in memory."
  - "Opaque job and record IDs first resolve through persisted principal predicates, then pass the canonical instrument scope check; every mismatch remains the same 404."
  - "Outcome, calibration, record-id, and transition reads use joined owner queries before any hub, scanner, runner, or path-reader collaborator can run."
patterns-established:
  - "Owned Forecast page: COUNT and row SELECT both bind principal plus instrument, with created_at DESC/id DESC and bounded LIMIT/OFFSET."
  - "Owned Forecast descendant: join child → forecast_records → forecast_jobs and bind persisted principal plus instrument before projection."
requirements-completed: [FORE-01]
coverage:
  - id: D1
    description: "Forecast job and record pages are filtered by principal plus instrument in SQLite before count, ordering, limit, and offset."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "backend/tests/forecast/test_api.py::test_forecast_owned_pages_filter_principal_and_instrument_before_pagination"
        status: pass
    human_judgment: false
  - id: D2
    description: "A second valid principal with the same instrument scope cannot list foreign IDs or detail, retry, subscribe, read paths/outcomes, or invoke calibration for the first principal's Forecast objects."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "backend/tests/forecast/test_api.py::test_cr03_same_instrument_cross_principal_matrix_denies_every_surface"
        status: pass
    human_judgment: false
  - id: D3
    description: "Owner access preserves persisted SSE resume, bounded hub cleanup, retry lineage, record/path projection, and record-scoped calibration."
    requirement: FORE-01
    verification:
      - kind: integration
        ref: "backend/tests/forecast/test_api.py -x"
        status: pass
    human_judgment: false
duration: 13m42s
completed: 2026-07-22
status: complete
---

# Phase 05 Plan 37: Persisted Forecast Principal Ownership Summary

**Forecast 的公开列表、详情、重试、SSE、record/path/outcome/calibration 现均由持久化 principal 与规范 instrument 双重约束，且同 instrument 的第二 principal 无法观察或触发首个 principal 的任何资源。**

## Performance

- **Duration:** 13m42s
- **Started:** 2026-07-22T05:38:47Z
- **Completed:** 2026-07-22T05:52:29Z
- **Tasks:** 1/1
- **Files modified:** 3 production/test files plus this summary

## Accomplishments

- 新增 `page_owned_jobs` 与 `page_owned_forecasts`：COUNT 和 row query 共享 `principal = ? AND instrument_id = ?`，在 SQLite 内完成稳定 newest-first 排序与有界分页。
- 新增 persisted-owner job/record detail、job→record、transition、outcome、calibration joined readers；record descendants 均通过 `forecast_records.job_id → forecast_jobs.principal` 继承所有权。
- API 的 list/detail/retry/events/stream/record/path/calibration GET/POST 全部先完成 owner 检查；foreign 请求统一返回不可区分 404，且不会 publish/subscribe hub、创建 retry、调用 scanner/runner 或读取 path artifact。
- 双 principal 同时获准访问 `600000.SH` 的精确 CR-03 主节点覆盖列表隔离、job/record detail、retry、两个 SSE alias、path、outcome/calibration GET/POST 与零副作用；owner 仍保留 resume、retry lineage、record/path 和 calibration 行为。

## Task Commits

| Gate | Task | Commit | Result |
|---|---|---|---|
| RED | Task 1: complete same-instrument Forecast ownership matrix | `76bb108` | 主节点以 foreign list total=2 失败；owned page 节点以缺少 repository 方法失败 |
| GREEN | Task 1: persisted principal ownership across SQL/API | `1fcc694` | 精确主节点 1 passed；计划 selector 4 passed；完整 Forecast API 15 passed |

**Plan metadata:** committed separately after self-check.

## Files Created/Modified

- `backend/app/forecast/repository.py` — owned SQL pages、job/record details、job→record、transition、outcome 与 calibration joined readers；fixture records 可绑定明确 principal。
- `backend/app/forecast/api.py` — list/detail/retry/SSE/record/path/calibration 全面切换到 persisted-owner 方法，并在 collaborator 前 fail closed。
- `backend/tests/forecast/test_api.py` — 精确 CR-03 双 principal IDOR matrix、SQL page/detail/descendant 回归及 owner companion behavior。
- `.planning/phases/05-optional-enhancements/05-37-SUMMARY.md` — 执行证据、TDD gate 与安全闭环。

## Decisions Made

- 列表响应直接消费 repository 已分页的 owned rows，不再调用 `list_jobs()`/`list_forecasts_for_instrument()` 后内存过滤；这样 total、has_more 和 page contents 均无法包含 foreign facts。
- 详情路由以 persisted principal SQL predicate 隐藏 opaque ID，再以 `_require_instrument` 执行当前请求的规范 instrument authority；缺失、foreign owner 与 foreign instrument 都返回同一个 404。
- SSE 每次读取 persisted transition page 前重新取得 owned job，并把 principal 与 instrument 一并绑定到 transition JOIN；Last-Event-ID 语义、终态退出及 hub capacity cleanup 不变。
- calibration payload 不复用无 owner 条件的全局 repository readers；outcome/fact 均通过 record/job join 后才 projection。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] 修复隔离 worktree 的 pytest launcher 来源漂移**
- **Found during:** Task 1 GREEN verification
- **Issue:** ignored `backend/.venv/bin/pytest` shebang 指向主 checkout，最初 GREEN 命令加载旧 `ForecastRepository` 并误报 owned 方法不存在。
- **Fix:** 仅在当前隔离 worktree 内把 ignored launcher 指向当前 `.venv/bin/python3`；未提交环境文件。
- **Files modified:** `backend/.venv/bin/pytest`（ignored local environment）
- **Verification:** `uv run pytest` 随后从当前 worktree 加载代码；精确主节点、计划 selector 与完整 API 文件均通过。
- **Committed in:** Not applicable

---

**Total deviations:** 1 auto-fixed blocking environment issue.
**Impact on plan:** 仅保证测试真实执行当前隔离实现；未改变产品范围或授权模型。

## Issues Encountered

- 首次多 hunk test edit 将追加内容置于既有测试函数中；在任何测试或 commit 前按原始函数边界修复，随后 RED 以预期授权缺口失败。
- `repository.py` 含 Plan 05-34 的未提交依赖基线。依 parent 约束，GREEN commit 通过交互式 hunk staging 仅纳入 05-37 owned-query 与 fixture-principal hunks；05-34 hunks保持未修改、未暂存、未提交。

## Verification

```text
cd backend && uv run pytest tests/forecast/test_api.py::test_cr03_same_instrument_cross_principal_matrix_denies_every_surface -x
PASS — 1 passed.

cd backend && uv run pytest tests/forecast/test_api.py -k "principal_owner or cross_principal or owned_page or last_event_id" -x
PASS — 4 passed, 11 deselected by the required selector; no skip/xfail.

cd backend && uv run pytest tests/forecast/test_api.py -x
PASS — 15 passed; no skip/xfail.

cd backend && uv run pytest tests/forecast/test_runner.py -k "explicit_retry_lineage or completed_commit_atomically or persisted_transition" -x
PASS — 1 passed, 38 deselected by the companion selector.
```

## Acceptance Criteria

- **PASS — cross-principal deny by default:** principal B sees only B-owned list rows/totals and receives the same 404 for A-owned job detail, retry, events, stream, record detail, paths, and calibration GET/POST.
- **PASS — zero side effects:** foreign matrix leaves job count unchanged and records zero hub publish/subscribe, active subscription, scanner, runner, and path-reader calls.
- **PASS — SQL boundary:** job and record page COUNT/rows bind principal plus instrument before ordering/pagination; record descendants join through the immutable owning job.
- **PASS — owner behavior:** owner detail exposes its completed record, Last-Event-ID resumes the persisted done transition, retry preserves lineage, paths remain bounded, and calibration returns persisted outcome/fact data.
- **PASS — exact primary node:** `backend/tests/forecast/test_api.py::test_cr03_same_instrument_cross_principal_matrix_denies_every_surface` passes directly; no required node was skipped.

## Threat Mitigation Evidence

- **T-05-37-01:** request-state principal is compared in SQL against immutable `forecast_jobs.principal`; no browser DTO or query parameter carries owner identity.
- **T-05-37-02:** job/record opaque IDs and child facts resolve only through owner predicates/joins, with all mismatches projected as `Forecast resource not found`.
- **T-05-37-03:** retry, SSE subscription, path reader, and calibration scanner are all reached only after owner authorization; the foreign matrix proves zero collaborator calls and zero new job rows.

## TDD Gate Compliance

- RED commit `76bb108` precedes GREEN commit `1fcc694` and failed for the intended observable reasons: foreign list disclosure and missing owned SQL page contract.
- GREEN preserves the exact RED node name and passes the literal plan selector plus complete companion API regressions.
- No refactor-only commit was necessary.

## Known Stubs

None. Scoped production/test files contain no TODO, FIXME, placeholder, coming-soon, skip, or xfail marker; empty path pages in the spy are deliberate zero-collaborator fixtures, not production fallback data.

## User Setup Required

None. No dependency, environment variable, schema migration, service, or manual approval was introduced.

## Next Phase Readiness

- CR-03 persisted-principal ownership is closed for every public Forecast surface and can be re-evaluated by the Phase 05 verifier.
- FORE-01 concurrency remains descriptor-less/unverified beyond this plan's exact same-instrument concurrent-principal ownership matrix; no broader ordering guarantee is asserted.
- Shared `.planning/STATE.md`, `.planning/ROADMAP.md`, and `.planning/REQUIREMENTS.md` had unrelated pre-existing hunks and are intentionally left untouched for the parent orchestrator.

## Self-Check: PASSED

- Scoped production/test files与 `05-37-SUMMARY.md` 均存在。
- RED/GREEN commits `76bb108` 与 `1fcc694` 均可由 git object database 解析。
- 精确 CR-03 主节点 1 passed；literal plan selector 4 passed；完整 Forecast API 文件 15 passed；无 required skip/xfail。
- 两个 task commits 未删除 tracked file；stub/skip 扫描为空。
- `repository.py` 剩余 unstaged 内容仅为 parent 指定不可变的 05-34 依赖基线，未进入 05-37 commits。

---
*Phase: 05-optional-enhancements*
*Completed: 2026-07-22*
