# 32-02 SUMMARY — AQ-02/03/05 竞价历史回填任务 + API 端点

**Plan:** `.planning/phases/32-auction-backfill/32-02-PLAN.md`
**Executor:** ExecutorP3202 · **Wave:** 2 (parallel with 32-03) · **Depends:** 32-01 (DONE)
**Date:** 2026-08-06 · **Status:** COMPLETE

## Deliverables

| Artifact | Contains |
|---|---|
| `backend/app/services/auction_backfill.py` | `run_auction_backfill` — 探针闸门 + kline_daily 分区对齐范围/写边界 + 预检可达性 + per-symbol 串行限速循环 + 429 退避重试 + 合作取消 + 失败台账 + 终态 dict (W-5 契约) |
| `backend/app/api/auction_backfill.py` | `POST /api/kline/auction/backfill` — 校验 + 单飞 + 重任务槽 + executor + job_store 生命周期 + 缓存失效 (独立模块, 不放 GET-only auction_history) |
| `backend/app/main.py` | import 面 + `app.include_router(auction_backfill.router)` (auction_history 之后, L856); guest 白名单零改动 |
| `backend/tests/test_auction_backfill.py` | 23 用例: job 单测 12 + 限速/取消/写缝 5 + 端点 6 |

## Commits (7 + SUMMARY)

```
ae54252 test(32-02): provider contract — get_auction receives date objects not ISO strings (live-smoke caught strftime crash)
f61aa95 fix(32-02): pass date objects (not ISO strings) to provider.get_auction — xyz strftime contract (live smoke caught)
61e3b07 test(32-02): auction backfill endpoint tests — singleflight reuse, param validation 400, executor, main.py registration, guest whitelist untouched, heavy-slot fail-fast (AQ-02)
885eb32 feat(32-02): POST /api/kline/auction/backfill endpoint — validation, single-flight, heavy-slot, executor, job_store lifecycle + main.py registration (AQ-02)
f5a6f59 test(32-02): pacing (W-3 module-level patch), cooperative cancel, atomic no-tmp, 0930 excluded, unmatched-col-absent via job (AQ-04/05)
733b650 feat(32-02): run_auction_backfill — probe/preflight gates, kline_daily-aligned scope+write boundary, per-symbol serial loop, failure ledger, terminal dict (AQ-02/03/05)
5d6926a test(32-02): auction backfill job unit tests — probe/preflight fail-closed, aligned-dates, failure ledger, bounds, idempotent, one-symbol (AQ-02/03/05)
```

TDD per task: test commit → feat commit (Task 2 service side verified unchanged — Task 1 已含 pacing/cancel/progress, 故 Task 2 仅 test commit; Task 3 test commit 先于 endpoint 实现). 冒烟发现的 date-object 契约 bug 同样 test→fix 成对提交.

## Verification

```
cd backend && .venv/bin/python -m pytest tests/test_auction_backfill.py -x -q
   → 23 passed (3 consecutive runs)
cd backend && .venv/bin/python -m pytest tests/test_pool_backfill.py tests/test_auction_sync.py tests/test_auction_history.py -x -q
   → 45 passed (回归锁零改动)
结构门: include_router(auction_backfill.router) in main.py = 1 (L856, auction_history L853 之后);
        def auction_backfill in api/auction_backfill.py = 1; def run_auction_backfill in services/auction_backfill.py = 1
```

## Live end-to-end smoke (OPTIONAL, executed — network reachable, timeboxed)

Real probe (`available`, source `xyz`) + real `data/` lake + real provider, via endpoint → job → executor:

- POST `{"symbols":["000001.SZ","000002.SZ"],"rpm":60}` → `started` → job succeeded:
  `{"requested": 2, "backfilled_symbols": 2, "rows": 496, "dates": 248, "failed": 0, "failed_symbols": [], "origin": "backfill", "rpm": 60}`
  — 248 dates = real kline_daily 分区数 (2025-07-29..2026-08-05), 496 = 248×2 码, 0 失败.
- 幂等重跑: 湖行数仍 496 (merge-upsert 只填缺口, 无重复).
- 取消: POST 3 码任务 → 1s 后 `POST /api/pipeline/jobs/{id}/cancel` → 200 `cancelled` → job `failed | error: 用户手动取消` (合作式取消实时生效).
- 首次冒烟暴露 bug: 服务传 ISO 字符串而 `xyz.get_auction` 需要 `date` 对象 (`strftime`) — fail-closed 闸门如实 0 写 + reason 记录 (诚实路径本身工作正常); 已 test→fix 成对修复 (`f61aa95`/`ae54252`).
- 冒烟写入 `data/kline_auction` (gitignored, `.gitignore:46 data/**`) + `data/job_store`, 均不污染 git.

## Deviations (记录, 均已在实现中处理)

1. **Provider date 契约** (冒烟发现): `_fetch_auction` 收 `date` 对象而非计划字面写的 ISO 字符串 (`xyz_provider.py:189 strftime`) — 预检/循环用 `eff_start_date/eff_end_date = date.fromisoformat(...)` 一次转换; `_has_daily_rows` 仍用 ISO 字符串喂 DuckDB (两边各取所需).
2. **循环传有效日期而非裸参数**: 计划 action 写 `provider.get_auction([sym], start, end)` — `start=None` 会触发 xyz `ValueError` (全范围任务必炸); 改为 `start or aligned_dates[0]` / `end or aligned_dates[-1]` (与计划预检行同一模式).
3. **`_wait_job_terminal` 健壮化** (测试侧): fail-closed 任务无 await、`job_store.fail` pop-后-写盘, 并发 get 存在瞬时「内存/磁盘皆无」窗口 → 轮询整窗而非首个 poll 即返 None (3 次连续全绿).
4. **429 自动退避** (上下文要求, 计划未详述): 上游显式 429/限速异常 → 指数退避重试 (2 次, 2s→4s); 非限速异常不重试; `_call_tool` 吞错为空的场景仍走 empty_response 诚实台账.
5. **Task 2 feat commit 为空**: Task 1 的循环已含 `sleep_between_batches` + 取消 + 进度 (计划 Task 1 action 即要求), Task 2 服务侧「仅核对」→ 只提交 test (不伪造空 feat commit).

## Plan-check warnings applied (W-1/2/3/5)

- **W-1** (KlineRepository 无 `repo.query`): universe 用 `repo.db.execute("SELECT DISTINCT symbol FROM kline_daily").fetchall()` (DuckDB 视图, union_by_name=true) + polars `scan_parquet` 列限兜底 (schema drift R6). 单测经真实 `DataStore`/`KlineRepository` (tmp) 视图验证.
- **W-2** (import 块镜像): 模块级 `from datetime import date`、`logger = logging.getLogger(__name__)`、`_noop(stage, pct, msg, **kwargs)` (镜像 pool_backfill.py:20-27); 重 import (auction_probe/auction_sync/pipeline_jobs) 函数内, polars/rate_limits/repository 模块级.
- **W-3** (pacing 补丁层级): `sleep_between_batches` **模块级 import** (`app.tickflow.rate_limits`); `test_auction_backfill_rate_limit_pacing` monkeypatch `app.services.auction_backfill.sleep_between_batches` 记录 `[(0,30),(1,30),(2,30)]` + rpm=10 透传; autouse `_neutralize_pacing` fixture 让其余 job 测试不真 sleep.
- **W-5** (终态键集契约): 模块 docstring + `run_auction_backfill` docstring + `_fail_closed` 三处文档化 — 成功 8 键 / fail-closed 9 键 (+`reason`); `test_auction_backfill_cooperative_cancel`(a) 用 set-equality 锁成功路径 8 键; 冒烟终态 dict 实测 8 键/9 键两形.

## Honesty requirements (verified)

- 探针 fail-closed: `source_down` 参数化 3 态 → 0 写 (`not list(kline_auction/date=*)`); 预检异常/空-有覆盖 → `preflight_empty`/异常 reason, 0 写.
- 只写 kline_daily 对齐日期: 范围 = 分区目录 ∩ [start,end] + 写边界 `datetime.date().is_in(aligned_dates)` (08-03 无分区不写, 测试 + 冒烟 248 dates 实测).
- per-symbol 台账: `failed_symbols:[{symbol, reason}]`, reason 截断 200, empty_response 有覆盖才记; `origin="backfill"` 仅终态 dict; `auction_unmatched_volume` 绝不写 (列存在性 crop); 无 0 填.
- 未 consult `auction_sync_enabled`; 未触碰 `api/auction_history.py` / `pool_backfill.py` / `auction_sync.py` / `frontend/`; 零新增运行时依赖.

## Watchlist proof

`git status --short` (final): 唯一未暂存变更 = `M frontend/src/pages/Watchlist.tsx` — 全程未读未触, 其余全部已提交.
