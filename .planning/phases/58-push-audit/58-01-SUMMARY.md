---
phase: 58-push-audit
plan: 01
subsystem: backend
tags: [audit, wecom, workbench, push-stats]
requires:
  - Phase 52 tool_call_envelopes table
  - Phase 52 notification_deliveries table
  - Phase 55 WS connection audit
  - Phase 56 SCT channel audit pattern
provides:
  - WeCom push delivery audit (tool=wecom in tool_call_envelopes)
  - GET /api/workbench push_stats section (today/by_tool/recent_failures)
affects:
  - webhook_adapter.send_wecom / send_wecom_markdown
  - workbench.py workbench() endpoint
tech-stack:
  added: []
  patterns:
    - get_audit_repo().append() audit pattern (from SctChannel)
    - _safe() fail-soft wrapper (from workbench _pending_section)
key-files:
  created:
    - backend/tests/test_wecom_audit.py
    - backend/tests/test_workbench_push_stats.py
  modified:
    - backend/app/services/webhook_adapter.py
    - backend/app/api/workbench.py
decisions:
  - D-02: WeCom audit scope uses push:{title[:50]} prefix (Claude discretion per D-02)
  - D-03: push_stats queries tool_call_envelopes + notification_deliveries, fail-soft via _safe()
metrics:
  duration: 676s
  completed: 2026-08-22
actuals:
  tokens: 4140
  tasks: 3
  commits: 3
status: complete
---

# Phase 58 Plan 01: Backend WeCom Audit + Workbench Push Stats + PA-01 Verification Summary

WeCom 推送投递审计 (tool=wecom) + workbench push_stats 统计子项 + PA-01 WS 连接审计验证。

## What Was Built

### Task 1: WeCom 推送投递审计 (PA-02, D-02)

在 `webhook_adapter.py` 的 `send_wecom` 和 `send_wecom_markdown` 中添加审计调用:

- 新增 `_audit_wecom(title, payload, t0, success)` 内部 helper, 与 SctChannel.deliver 审计模式一致
- `send_wecom`: 用 `try/finally` 包裹 `_post_wecom`, finally 块调用 `_audit_wecom`
- `send_wecom_markdown`: 同样的 `try/finally` + `_audit_wecom` 模式
- 审计记录: `tool="wecom", category="notification", scope=f"push:{title[:50]}", response_summary="sent"/"failed", raw=json.dumps(payload)[:500], duration_ms, error`
- 审计失败不阻断推送 (`except: pass`); `get_audit_repo()` 返回 None 时跳过
- 创建 `test_wecom_audit.py`: 4 个测试 (成功/失败/markdown成功/无repo不报错)

### Task 2: Workbench push_stats 统计子项 (PA-03, D-03)

在 `workbench.py` 新增 `_push_stats_section(request)` 函数:

- 查询 `tool_call_envelopes` 今日 `tool IN ('sct', 'wecom', 'connection')` 的 total/sent/failed 统计
- 查询 `notification_deliveries` 今日 `status='skipped' AND error='dedup'` 的去重跳过计数
- 查询最近 10 条 `error IS NOT NULL` 的失败记录 (ORDER BY seq DESC)
- 返回结构: `{today: {total, sent, failed, dedup_skipped}, by_tool: {...}, recent_failures: [...]}`
- 在 `workbench()` 端点通过 `_safe(_push_stats_section, request)` 装配, fail-soft
- 创建 `test_workbench_push_stats.py`: 4 个测试 (空库/计数/dedup/failures)

### Task 3: PA-01 WS 连接审计验证 (D-01)

- 运行 `test_ws_audit.py` 确认 WS 连接审计 (tool=connection, scope=ws) 正常工作 — **PASS**
- 运行回归测试: ws_audit + sct_channel + wecom_audit + push_stats + pipeline_fixes — **29 passed**
- 运行 notification_delivery 测试 (排除 1 个预存失败) — **15 passed**
- 运行 ruff: 新增/修改文件无新告警 (预存 RUF100/RUF001 在 webhook_adapter.py 不在本 plan 范围)
- PA-01 无需新增代码 (Phase 55 已实现), 仅验证通过

## Verification Results

| Check | Command | Result |
|-------|---------|--------|
| WeCom 审计 | `pytest tests/test_wecom_audit.py -x -q` | 4 passed |
| push_stats | `pytest tests/test_workbench_push_stats.py -x -q` | 4 passed |
| PA-01 WS 审计 | `pytest tests/test_ws_audit.py -x -q` | 1 passed |
| 回归 (核心) | `pytest tests/test_ws_audit.py tests/test_sct_channel.py tests/test_wecom_audit.py tests/test_workbench_push_stats.py tests/test_pipeline_and_monitor_fixes.py -x -q` | 29 passed |
| 回归 (notification_delivery) | `pytest tests/test_notification_delivery.py --deselect ...slow_delivery -x -q` | 15 passed |
| ruff (新文件) | `ruff check tests/test_wecom_audit.py tests/test_workbench_push_stats.py` | All checks passed |
| ruff (修改文件) | `ruff check app/services/webhook_adapter.py app/api/workbench.py` | 3 pre-existing warnings (RUF001/RUF100, not from this plan) |

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | aa88b747 | feat(58-01): add WeCom push delivery audit (PA-02, D-02) |
| 2 | 453faa42 | feat(58-01): add workbench push_stats section (PA-03, D-03) |
| 3 | 6e2d81a0 | test(58-01): verify PA-01 WS audit + fix lint (D-01) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Pre-existing test failure in test_notification_delivery.py**
- **Found during:** Task 3
- **Issue:** `test_event_persists_and_streams_before_slow_delivery_completes` fails with AssertionError — confirmed pre-existing via `git stash` test (fails without Plan 01 changes)
- **Fix:** Logged to `deferred-items.md`, excluded from regression run. Not related to WeCom audit or push_stats changes.
- **Files modified:** `.planning/phases/58-push-audit/deferred-items.md`

**2. [Rule 1 - Bug] Ruff lint in test files**
- **Found during:** Task 3
- **Issue:** Test files had unused `pytest` import, non-UTC alias, unused loop variable
- **Fix:** Removed unused import, used `datetime.UTC`, renamed loop var to `_i`
- **Files modified:** `backend/tests/test_workbench_push_stats.py`

### Threat Model Compliance

| Threat ID | Disposition | Status |
|-----------|-------------|--------|
| T-58-01 | mitigate | **Mitigated** — raw payload json.dumps truncated to 500 bytes, only SHA-256 hash stored via `_compute_hash` in `append()` |
| T-58-02 | mitigate | **Mitigated** — SQL queries limited to `date(created_at) = date('now')` + `tool IN` 3 values; `_safe()` fail-soft returns None on exception |
| T-58-03 | accept | **OK** — tool_call_envelopes append-only (Phase 52 triggers), push_stats only reads |
| T-58-SC | accept | **OK** — no new packages installed |

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|---------|
| PA-01 | Verified | test_ws_audit.py passes — WS connection audit (tool=connection, scope=ws) confirmed |
| PA-02 | Delivered | send_wecom/send_wecom_markdown record tool=wecom audit; 4 tests pass |
| PA-03 | Delivered | GET /api/workbench returns push_stats; 4 tests pass |

## Known Stubs

None — all code is production-quality with real audit calls and real SQL queries.

## Self-Check: PASSED

- [x] `backend/app/services/webhook_adapter.py` — FOUND (modified, _audit_wecom added)
- [x] `backend/app/api/workbench.py` — FOUND (modified, _push_stats_section added)
- [x] `backend/tests/test_wecom_audit.py` — FOUND (4 tests, all pass)
- [x] `backend/tests/test_workbench_push_stats.py` — FOUND (4 tests, all pass)
- [x] Commit aa88b747 — FOUND in git log
- [x] Commit 453faa42 — FOUND in git log
- [x] Commit 6e2d81a0 — FOUND in git log
