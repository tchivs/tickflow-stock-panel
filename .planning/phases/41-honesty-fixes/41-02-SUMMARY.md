# 41-02-SUMMARY.md — HON-02 诚实性修复 (Wave 2)

**Phase:** 41-honesty-fixes · **Wave:** 02 (HON-02) · **Date:** 2026-08-07
**Executor:** ExecP4102 · **Status:** DONE — 4 commits (T1 RED→GREEN, T2 feat→test), test_auction_backfill.py 29/29 全绿, 41 族 74 passed/2 skipped

## 交付物

| Artifact | Path | 说明 |
|---|---|---|
| 终态 emit 接线 | `backend/app/services/auction_backfill.py` | `_emit_fail_closed` helper + 五条 fail-closed 提前返回 emit (含 reason) + 41-01 预检 source_blocked 分支补 emit |
| 取消 stage + done 门 | `backend/app/services/auction_backfill.py` | 取消独立 `cancelled` stage + 实际 pct, `cancelled` 门住循环尾 done (二次 done/100 修复) |
| 循环逐 symbol emit | `backend/app/services/auction_backfill.py` | 空帧分支 continue→if/else 化, 每 processed symbol 一行进度 (回归锁要求) |
| CLI stderr | `backend/scripts/auction_backfill.py:147` | `on_progress` 打 `file=sys.stderr` (stdout 留给终态摘要/台账) |
| 测试 ×4 | `backend/tests/test_auction_backfill.py` | 五路径 emit 断言 ×2 + 取消断言 ×1 + 回归锁 ×1 |

## Commit 链 (RED → GREEN 可回溯)

| Commit | Sha | 内容 |
|---|---|---|
| T1 (RED) | `14da88a` | test(41-02): fail-closed 五路径 emit 断言 — 收集期红: `assert 0 == 1` (零 emit) |
| T1 (GREEN) | `d8129b9` | feat(41-02): fail-closed 提前返回补终态 emit — 25/25 绿 |
| T2 (feat) | `f4bb1b7` | feat(41-02): 取消独立 cancelled stage + done 门 + CLI stderr |
| T2 (test) | `6475542` | test(41-02): 回归锁 — 全空帧批量逐 symbol 进度 + failed 计数 |

## Verify 命令输出摘录

**T1 (RED):**
```
tests/test_auction_backfill.py::test_auction_backfill_fail_closed_source_unavailable_emits - AssertionError: assert 0 == 1
tests/test_auction_backfill.py::test_auction_backfill_fail_closed_five_paths_emit - AssertionError: assert 'fail-closed: no_scope' in []
2 failed, 1 passed, 22 deselected
```

**T2 (RED, 二次 done/100 实锤):**
```
assert ('cancelled', 0, '回填被取消 (已处理 0/3)') in [('auction_backfill', 0, '回填 3 个标的 × 2 日…'),
    ('done', 100, '回填被取消'), ('done', 100, '回填完成: 0 成功, 0 失败')]
```

**T2 (GREEN, 全文件):**
```
tests/test_auction_backfill.py .............................  [100%]
29 passed in 1.55s
```

**41 族最终 (41-01 + 41-02 合并态):**
```
tests/test_auction_backfill.py tests/test_auction_backfill_honesty.py tests/test_auction_probe.py
tests/test_xyz_provider.py tests/test_verify_auction_backfill.py
74 passed, 2 skipped in 3.45s
```

**CLI 冒烟:** `python scripts/auction_backfill.py --help` → 退出 0; `grep file=sys.stderr scripts/auction_backfill.py` → :147 命中。

## 契约锁死点 (HON-02)

- **五路径终态 emit**: :217 `source_unavailable` / :242 `no_scope` / :247 `no_provider` / :290 预检异常 `str(e)[:_ERROR_DETAIL_MAX]` / :293 `preflight_empty` — 每条 `return _fail_closed(...)` 前 `_emit_fail_closed(emit, <同字面量>)`; 测试断言 emit 行与终态 dict `reason` 一致且 0 写。`test_auction_backfill_fail_closed_source_unavailable_emits` 断言**恰 1 行** `("auction_backfill", 0, "fail-closed: source_unavailable")`。
- **取消路径**: 独立 stage `cancelled` + 实际 pct (`int(100*i/requested)`, 预置=0, 循环中翻转=33), 消息 `回填被取消 (已处理 {i}/{requested})`; **零** `done` 行、零「回填完成」消息 (done 门 `if not cancelled`); 终态 8 键 (无 reason, 部分成功语义) 不变。
- **回归锁** `test_auction_backfill_all_empty_progress_and_failed_count`: 预检 symbol 选无覆盖的 `920146.BJ` (绕开 preflight_empty 整批门) + 两个有覆盖 symbol → stage `auction_backfill` 行数 == 1(起始) + 3(逐 symbol), pct `[33, 66, 100]`, `failed == 2`, `failed_symbols` 恰 `[{"symbol": "000001.SZ", "reason": "empty_response"}, {"symbol": "600000.SH", "reason": "empty_response"}]`, 最后 done 行 `回填完成: 0 成功, 2 失败`。
- **CLI**: `[progress]` 行走 stderr, stdout 仅终态摘要/台账 (operator 管道语义)。

## 计划偏差 (均有依据, 已在代码注释落点)

1. **循环 emit 结构性补全 (回归锁前提)**: 计划注「循环内 :308-313 已逐 symbol 输出, 勿重复实现」— 现状核实发现两条空帧分支 `continue` **在 emit 之前**跳过该行 → 全空批量仍进度冻结。回归锁规范 (`len(symbols)+1` 行) 要求每 processed symbol 一行 → 空帧分支 continue 改 if/else 嵌套, 底部 emit 对每 symbol 恒触发。台账/计数语义零变化 (空+无覆盖 symbol 现在也如实输出进度行)。
2. **41-01 新预检分支补 emit**: 41-01 引入的预检 `except SourceBlockedError` → `_fail_closed(rpm, "source_blocked")` 是第六条 fail-closed 提前返回, 同样会冻结进度 → 补 `_emit_fail_closed(emit, "source_blocked")` (HON-02 进度永不冻结的完整性)。
3. **d8129b9 提交归属混杂**: 提交时 ExecP4101 未提交的 41-01 服务层 hunks (SourceBlockedError import / `_fetch_auction` 零重试 / 预检+循环 except 分支) 已在工作树 → 被一并扫入本 feat 提交。经 IRC 协调确认不重写历史: ExecP4101 在 93252a1 提交消费面其余部分并在其 SUMMARY 注明归属; 共享文件合并后 41 族全绿。

## 约束复核

- **零新增依赖**: 无 pyproject/uv.lock 改动。
- **Watchlist 零触碰**: `frontend/src/pages/Watchlist.tsx` 保持唯一 unstaged 改动, 未被我修改。
- **既有契约零破坏**: W-5 终态键集 (成功 8 键 / fail-closed 9 键) 不变; 0 写语义不变; only_missing 空态返回 (成功 8 键 requested=0) 不加 emit (幂等无事可做非错误); test_xyz_provider.py:126-137 空帧契约绿。

## 协作注记

- 与 ExecP4101 (41-01) 共享 `auction_backfill.py` / `test_auction_backfill.py`: 全程 IRC 协调提交边界 (服务层 hunks 归属 d8129b9, 消费面 93252a1, verify 区分门 5fc01bd); 测试文件按函数块各自落位 (:248-293 其 HON-01 测试 / :843-942 本 wave 测试), 无相互覆写。
- 观察 (不在本 wave 范围): `pool_backfill.py:88-92,115` 存在相同的「取消 emit done/100 + 循环尾无条件 done」二次 done 反模式, 建议后续 wave 对齐修复。
- 全量回归 `pytest tests/ -x` 由 orchestrator 统一收口 (本 wave 只跑 41 相关文件)。
