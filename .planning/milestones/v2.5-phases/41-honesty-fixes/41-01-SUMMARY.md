# 41-01-SUMMARY.md — HON-01 三态化 (Wave 1)

**Phase:** 41-honesty-fixes · **Wave:** 01 (HON-01 诚实性修复) · **Date:** 2026-08-07
**Executor:** ExecP4101 · **Status:** DONE — 4 commits (T1 RED → T1 GREEN → T2 → T3), 74 passed / 2 skipped (phase-内五文件套件全绿)

## 交付物

| Artifact | Path | 说明 |
|---|---|---|
| typed 异常 | `backend/app/data_providers/base.py` | `SourceBlockedError` (ProviderCapabilities 同契约模块, 消息 ≤200 纪律, 镜像 stockdb typed 异常先例) |
| 三态化 | `backend/app/data_providers/xyz_provider.py` | 双信号分类器 `_is_policy_block` (HTTP 403 + `_POLICY_BLOCK_MARKERS` 文案面) + `_call_tool` HTTPStatusError/error 载荷重抛 + `get_auction` 原样重抛 + `_price_frame` (daily/minute) 空帧降级保留 |
| R1 零重试 + 台账第三类 | `backend/app/services/auction_backfill.py` | `_fetch_auction` 先捕 `SourceBlockedError` 直接重抛 (marker 重叠词不误重试); 预检 → 终态 reason `"source_blocked"`; 循环 → `failed_symbols` 恰 `{"symbol", "source_blocked"}` (两键形状不变) |
| probe verdict | `backend/app/services/auction_probe.py` | `resolve_auction_probe` 遇策略封锁 → `fail_closed` + detail 恰 `"source_blocked"` (常量 `SOURCE_BLOCKED_DETAIL`, 非异常串) |
| verify 区分门 | `backend/scripts/verify_auction_backfill.py` | `_classify_source_block` 第三类独立归类: 非 BJ `source_blocked` → YES 策略封锁; 非 BJ `empty_response` → 疑似真空 (403 伪装含义移除) |
| 测试 | `backend/tests/{test_xyz_provider,test_auction_backfill,test_auction_backfill_honesty,test_auction_probe,test_verify_auction_backfill}.py` | 新增 9 用例 (见下) |

## Commit 链 (RED → GREEN 可回溯)

| Commit | Sha | 内容 |
|---|---|---|
| T1 (RED) | `abfab82` | 三态化契约测试 ×4 — 收集期红: `ImportError: cannot import name 'SourceBlockedError'` |
| T1 (GREEN) | `4e8cbf5` | xyz 三态化 — typed 信号 + 双信号分类器 (base.py + xyz_provider.py) |
| T2 | `93252a1` | R1 零重试 + 台账第三类 + probe fail_closed verdict (消费面 + 三态互斥测试) |
| T3 | `5fc01bd` | verify 区分门 — source_blocked 第三类独立归类 |

**服务侧 attribution 注记:** `auction_backfill.py` 的 HON-01 hunks (SourceBlockedError import / `_fetch_auction` 零重试 / 预检+循环 except 分支 / docstring) 与 41-02 共享该文件 — 工作树合并提交时落入 ExecP4102 的 `d8129b9` (feat(41-02): fail-closed 提前返回补终态 emit)。功能已提交在 HEAD, 经协调双方确认: 41-01 不再重提交该文件, 本 SUMMARY 显式注记归属。ExecP4102 另在预检 `SourceBlockedError` 分支加 `_emit_fail_closed(emit, "source_blocked")` (HON-02 emit 完整性, 其 commit `f4bb1b7`), 与 HON-01 语义兼容。

## Verify 命令输出摘录

**T1 (RED, 验收第一步行):**
```
tests/test_xyz_provider.py:166: ImportError: cannot import name 'SourceBlockedError' from 'app.data_providers.base'
1 failed, 5 passed
```

**T1 (GREEN, 三态化契约):**
```
tests/test_xyz_provider.py .........    [100%]
9 passed in 0.34s
```

**T2 (消费面 + 三态互斥):**
```
tests/test_auction_backfill.py::test_auction_backfill_preflight_source_blocked_zero_writes ... PASS
tests/test_auction_backfill.py::test_auction_backfill_source_blocked_recorded ... PASS
tests/test_auction_backfill_honesty.py::test_auction_backfill_source_blocked_reason_category_distinct ... PASS
tests/test_auction_probe.py::test_source_blocked_provider_is_fail_closed ... PASS
```

**T3 (verify 区分门):**
```
tests/test_verify_auction_backfill.py ..........    [100%]
10 passed in 1.16s
python scripts/verify_auction_backfill.py --help  → 退出 0
```

**Phase-内验收 (五文件套件, 最终):**
```
tests/test_xyz_provider.py tests/test_auction_backfill.py tests/test_auction_backfill_honesty.py
tests/test_auction_probe.py tests/test_verify_auction_backfill.py
74 passed, 2 skipped in 3.51s
```
(2 skipped = RUN_NETWORK_TESTS 网络门用例, 与基线一致; 41-02 的 cancelled/all-empty 测试已由 ExecP4102 提交于 `f4bb1b7`/`6475542`, 一并绿)

## 契约锁死点 (可执行规范)

- **三态化分类器 (HON-01 核心):** HTTP 403 或错误文案命中 `_POLICY_BLOCK_MARKERS` (`配额/带宽/限速/限流/频率/频繁/forbidden/blocked/denied`) → `SourceBlockedError` 上抛; 其余 4xx/5xx/超时/连接 → `""` → 空帧不抛。
- **既有契约保持绿:** `test_xyz_provider.py:126-137` (Test 4: `""` / `RuntimeError` → 空帧不抛) 零改动; `get_auction` 网络错误空帧契约不变。
- **daily/minute scope 决策:** `_price_frame` 捕 `SourceBlockedError` → 空帧降级 (契约不变, 只修竞价路径标签诚实性)。
- **R1 结构性只对可重试态:** `_fetch_auction` 先捕 `SourceBlockedError` 直接重抛 — 即便消息含「带宽」等 `_RATE_LIMIT_MARKERS` 重叠词也不误重试 (T-41-02: 2h 配额窗 × 5537 symbols 退避放大 = DoS); 测试断言预检/循环每 symbol 恰 1 次 provider 调用。
- **台账第三类互斥:** `failed_symbols` 恰两键 `{symbol, reason}`; `source_blocked` / `empty_response` / `str(e)[:200]` 三态互斥 (36-03 事故链闭环)。
- **probe verdict:** `SourceBlockedError` → `fail_closed` + detail 恰 `"source_blocked"`; `RuntimeError` 仍 `error` + 异常串 ≤200 (T-16-05 信息泄露 mitigation)。
- **verify 区分门:** 非 BJ `source_blocked` → `YES — 台账含 N 个非 BJ 标的 source_blocked (上游 403/配额窗策略封锁…)`; 非 BJ `empty_response` → `疑似 — … (上游真空/无数据, 非策略封锁 — source_blocked 已独立归类…)`; BJ-only / 台账不可读 / 无台账 分支文案同步更新。

## 约束复核

- **零新增依赖:** `git diff abfab82^..5fc01bd -- backend/pyproject.toml backend/uv.lock` → 0 行。
- **Watchlist 零触碰:** 该区间 commits 不触及 `frontend/src/pages/Watchlist.tsx` (保持唯一 unstaged 改动, 非本 executor 所为)。
- **零新机制:** 全部镜像既有 typed 异常 (stockdb_provider) / 台账形状 / verdict / 区分门模式。
- **与 41-02 共享文件协调:** auction_backfill.py + test_auction_backfill.py 双 executor 共写 — 经 hub 协商边界 (我的 hunks vs 其 hunks), `git apply --cached` 精确暂存我方 hunks, 互不覆盖。

## 协作注记

- ExecP4102 (41-02) 提交链: `14da88a` (红) → `d8129b9` (fail-closed emit, 含我方 HON-01 auction_backfill hunks) → `f4bb1b7` (取消 cancelled stage + done 门 + CLI stderr) → `6475542` (回归锁)。我方 HEAD 提交 `93252a1`/`5fc01bd` 与其余交错线性, 无冲突。
