---
phase: 41-honesty-fixes
verified: 2026-08-07T18:30:00Z
status: passed
score: 2/2 HON requirements — HON-01/02 verified (0 blockers; 3 sandbox-unassertable items recorded in human_verification)
overrides_applied: 0 — 执行区间 5061aa2..HEAD 未改动 REQUIREMENTS.md/ROADMAP.md 文本; PLAN-CHECK 3 warnings 均已在执行期消化 (见 §6)
human_verification: 3 items (上游配额窗真实响应体回填 marker 表定稿; 生产长任务真实取消路径; 生产网络 403/配额窗 live 行为) — sandbox 无法断言, 按既有诚实政策标注
---

# Phase 41 Verification — 诚实性修复 (HON-01..02)

**Verifier:** VerifierP41 · **Date:** 2026-08-07 · **Scope:** `.planning/REQUIREMENTS.md` HON-01/HON-02 (Phase 41), 提交集 5061aa2..HEAD (10 commits: wave1 `abfab82/4e8cbf5/93252a1/5fc01bd/fa5c488`, wave2 `14da88a/d8129b9/f4bb1b7/6475542/cb70cdc`).
**Method:** Behavior-level verification — 逐需求读实现 + 契约测试 + 守卫核验; 独立重跑 4 个指定测试文件 (64 passed) 与 41 族五文件套件 (74 passed/2 skipped); 所有数字为本 verifier 亲自重推导, 不采信 SUMMARY 文本。NEVER read `frontend/src/pages/Watchlist.tsx` (全程只经 git diff/status 核验零触碰)。

## Verdict: **PASSED**

两项需求全部验证通过: HON-01 source_blocked 三态化 (typed 信号 + 台账第三类 + probe fail_closed + R1 零重试 + verify 区分门), HON-02 fail-closed 终态 emit (五路径 + cancelled stage + CLI stderr + 回归锁)。既有 126-137 空帧契约零改动且绿, 台账两键形状不变, 零新依赖, Watchlist 零触碰。

---

## 1. 守卫核验 (guard rails)

| 守卫 | 命令 (本 verifier 亲自跑) | 结果 |
|---|---|---|
| 零新增依赖 | `git diff 5061aa2..HEAD -- backend/pyproject.toml backend/uv.lock` | **0 行** — pyproject/uv.lock 零改动 (SourceBlockedError/httpx/polars 均既有) |
| 126-137 空帧契约 untouched | `git diff 5061aa2..HEAD -- backend/tests/test_xyz_provider.py` | 仅 **+60 行追加** (diff hunk `@@ -153,3 +153,63 @@`), Test 4 (`""`/`RuntimeError` → 空帧不抛, :126-137) 零改动且绿 |
| Watchlist 零触碰 | `git diff --name-only 5061aa2..HEAD \| grep -i watchlist` | 提交内 **0**; 工作树唯一未暂存项 `M frontend/src/pages/Watchlist.tsx` (既有用户改动, 本 verifier 未读取该文件) |
| 台账两键形状 | 代码读 + `test_auction_backfill_failed_ledger_terminal_shape` | `failed_symbols` 每条恰 `{"symbol","reason"}` 两键 (`assert set(entry.keys()) == {"symbol","reason"}`), 三种 reason (source_blocked / empty_response / `str(e)[:200]`) 形状一致 |
| 提交集完整性 | `git log --oneline 5061aa2..HEAD` | 10 commits 与 claim 完全一致 (wave1 4+1docs, wave2 4), HEAD=`cb70cdc` |
| 零新机制 | 实现读 | 全部镜像既有 typed 异常 (stockdb_provider) / 台账形状 / verdict / 区分门模式; 无新依赖无新面 |

---

## 2. 逐需求证据 (REQ-by-REQ)

### HON-01 — `source_blocked` 三态化 — **PASS**

证据 (base.py / xyz_provider.py / auction_backfill.py / auction_probe.py / verify_auction_backfill.py 全文读 + 9 新测试):

- **typed 信号**: base.py 新增 `SourceBlockedError` (消息 ≤200 纪律, 镜像 auction_probe 错误纪律)。
- **双信号分类器**: xyz_provider.py `_is_policy_block(status, text)` — 状态码面 `status == 403 → True`; 文案面 `_POLICY_BLOCK_MARKERS = ("配额","带宽","限速","限流","频率","频繁","forbidden","blocked","denied")` 任一命中 → True。`_call_tool` 对 `HTTPStatusError` / 200 载荷 `error` 串分别判类: 命中 → `raise SourceBlockedError(...) from e`; 未命中 (其余 4xx/5xx/超时/连接) → 返回 `""` 空帧不抛。`get_auction` 捕 `SourceBlockedError` 原样重抛 (绝不吞成空帧, 36-03 闭环); `_price_frame` (daily/minute, scope 决策) 捕到 → 空帧降级, 契约不变。
- **分类器边界实测** (本 verifier 直接调): `(403, anything)→True`, `(200,"配额窗口未开放")→True`, `(200,"限速")→True`, `(500,"internal server error")→False`, `(200,"timeout")→False`。
- **R1 零重试**: auction_backfill.py `_fetch_auction` (行 151-166) **先捕** `SourceBlockedError` 直接重抛 — 即便消息含「带宽」等 `_RATE_LIMIT_MARKERS` 重叠词也不进退避面 (2h 配额窗 × 5537 symbols 退避放大即 DoS); 测试 `test_auction_backfill_preflight_source_blocked_zero_writes` 用消息「带宽限制批量请求」断言 `len(provider.calls) == 1` (预检恰 1 次), `test_auction_backfill_source_blocked_recorded` 断言 3 symbols 恰 3 次调用 (B 零重试)。
- **台账第三类**: 预检 `except SourceBlockedError` → `_fail_closed(rpm, "source_blocked")` 0 写 (行 284-287); 循环 `except SourceBlockedError` → `failed_symbols.append({"symbol": sym, "reason": "source_blocked"})` (行 336-338)。与 `empty_response` / `str(e)[:200]` 三态互斥 (per-symbol 唯一 reason, 见 §4 诚实性专项)。
- **probe fail_closed**: auction_probe.py `resolve_auction_probe` 捕 `SourceBlockedError` → `status=fail_closed` + `detail=SOURCE_BLOCKED_DETAIL` (`"source_blocked"` 常量, 非异常串; 行 162-172); `RuntimeError` 仍 → `error` + 截断串 ≤200 (T-16-05 mitigation 不变)。测试 `test_source_blocked_provider_is_fail_closed` 断言 verdict.fail_closed + detail 恰 `"source_blocked"` 与 error 分支互斥。
- **verify 区分门**: verify_auction_backfill.py `_classify_source_block` (行 190-233) — 非 BJ `source_blocked` → `YES — 台账含 N 个非 BJ 标的 source_blocked (上游 403/配额窗策略封锁: ...)`; 非 BJ `empty_response` → `疑似 — ... (上游真空/无数据, 非策略封锁 — source_blocked 已独立归类: ...)`; 全 BJ → `NO`; 无台账 → `UNKNOWN`。测试 `test_verify_partial_source_block_yes_non_bj_failures` / `_vacuum_empty_response` / `_no_bj_only_failures` 绿。

### HON-02 — fail-closed 终态 emit — **PASS**

证据 (auction_backfill.py / scripts/auction_backfill.py 全文读 + 4 新测试):

- **fail-closed 路径 emit**: `_emit_fail_closed(emit, reason)` helper (行 70-75, 与 `_fail_closed` 同 reason 字面量); 全部提前返回路径在 return 前 emit: 行 217 `source_unavailable` / 242 `no_scope` / 247 `no_provider` / 286 `source_blocked` (41-01 预检分支, HON-02 完整性补) / 290 预检异常 `str(e)[:_ERROR_DETAIL_MAX]` / 293 `preflight_empty`。测试 `test_auction_backfill_fail_closed_source_unavailable_emits` 断言恰 1 行 `("auction_backfill", 0, "fail-closed: source_unavailable")` + 终态 9 键; `test_auction_backfill_fail_closed_five_paths_emit` 逐路径断言 emit 行与终态 reason 同字面量 + 0 写。only_missing 全跳过空态 (成功 8 键 requested=0, 幂等无事可做) 不加 emit, 前有「覆盖扫描」进度行 — 非 fail-closed, 符合契约。
- **取消独立 stage**: 循环顶 job failed 检测 (行 264-272) → `cancelled=True` + `emit("cancelled", int(100*i/requested), f"回填被取消 (已处理 {i}/{requested})")` — 独立 stage + 实际 pct (预置=0, 循环中翻转=33), **绝不 done/100**; 循环尾 done 门 `if not cancelled:` (行 352) 消除二次 done。测试 `test_auction_backfill_cancel_emits_cancelled_stage` 双段 (a) 预置 failed → `("cancelled", 0, "回填被取消 (已处理 0/3)")`、(b) 循环中翻转 → `("cancelled", 33, "回填被取消 (已处理 1/3)")`, 两段都断言零 done 行 + 零「回填完成」消息 + 终态 8 键。
- **循环逐 symbol emit**: 空帧分支 continue → if/else 嵌套 (行 299-335), 底部 emit 对每 processed symbol 恒触发 (行 345-350) — 全空批量进度不再冻结; 计划偏差已在代码注释落点。
- **CLI stderr**: scripts/auction_backfill.py `on_progress=lambda stage, pct, msg, **kw: print(f"[progress] {msg}", file=sys.stderr, flush=True)` — 走 stderr, stdout 留终态摘要/台账 (operator 管道语义); 本 verifier 跑 `python scripts/auction_backfill.py --help` → 退出 0。
- **回归锁**: `test_auction_backfill_all_empty_progress_and_failed_count` — 预检 symbol 选无覆盖 `920146.BJ` (绕开 preflight_empty 整批门) + 两个有覆盖 symbol → stage `auction_backfill` 行数 == 1(起始) + 3(逐 symbol), pct `[33,66,100]`, `failed == 2`, `failed_symbols` 恰两键 `[{"symbol":"000001.SZ","reason":"empty_response"},{"symbol":"600000.SH","reason":"empty_response"}]`, done 行恰 `("done", 100, "回填完成: 0 成功, 2 失败")`, 0 写。

---

## 3. 独立测试跑 (本 verifier)

```
$ cd backend && uv run --frozen pytest tests/test_xyz_provider.py tests/test_auction_backfill.py tests/test_auction_probe.py tests/test_auction_backfill_honesty.py -q
64 passed, 2 skipped in 3.80s

$ uv run --frozen pytest tests/test_xyz_provider.py tests/test_auction_backfill.py tests/test_auction_probe.py tests/test_auction_backfill_honesty.py tests/test_verify_auction_backfill.py -q
74 passed, 2 skipped in 3.44s
```

| 文件 | 结果 | 构成 |
|---|---|---|
| test_xyz_provider.py | 9 passed | 5 既有 (含 Test 4 :126-137 空帧契约) + 4 新增 HON-01 三态化 |
| test_auction_backfill.py | 29 passed | 既有 + HON-01 预检/循环 source_blocked ×2 + HON-02 emit ×2 + 取消 ×1 + 回归锁 ×1 |
| test_auction_backfill_honesty.py | 16 passed / 1 skipped | 台账形状/BJ 空响应/三态互斥 + POOL-03 AST 守卫 + 1 网络门 |
| test_auction_probe.py | 9 passed / 1 skipped | 含新增 `test_source_blocked_provider_is_fail_closed` |
| test_verify_auction_backfill.py | 10 passed | 含新增/改造的区分门三测试 |

(2 skipped = `test_auction_probe.py:276` + `test_auction_backfill_honesty.py:392` network-gated, `-rs` 明示, 与基线门模式一致, 非本 phase 引入。74 passed/2 skipped 与 executor claim 逐字一致; orchestrator 全量 53 passed/1 skipped 为 40 族记录, 本 verifier 按分工只跑 41 族, 不虚报。)

## 4. 诚实性专项核验

| 专项 | 证据 (代码读 + 测试断言) | 结果 |
|---|---|---|
| source_blocked 与 empty_response 互斥 (无同 symbol 双 reason) | 循环内 per-symbol 唯一出口: `if df.is_empty() → [empty_response]` / `else → 过滤后可能 empty_response` / `except SourceBlockedError → source_blocked` / `except Exception → str(e)[:200]` — 互斥 if/else + 独立 except 分支, 单 symbol 最多记 1 条 reason; `test_auction_backfill_source_blocked_reason_category_distinct` 断言 reason 恰 `"source_blocked"` 且 != 原始消息「配额窗口未开放」; `test_auction_backfill_empty_response_reason_category_distinct` 同类断言 | **通过** |
| BJ 真空仍记 empty_response | `test_auction_backfill_bj_stock_empty_response_recorded` (family 绿): kline_daily 含 `920146.BJ` + 上游对 BJ 返回空 → 台账 `{"symbol":"920146.BJ","reason":"empty_response"}`, 湖无该 symbol 分区 (不预填、不假装覆盖); 回归锁中 BJ 也按无覆盖/有覆盖分治如实计数 | **通过** |
| 取消路径绝不 done/100 | 代码: done 门 `if not cancelled` (行 352); 测试: 取消双段均断言零 done 行、零「回填完成」, cancelled stage 独立 + 实际 pct (0/33) | **通过** |
| R1 零重试 | `_fetch_auction` 先捕 SourceBlockedError 直接重抛 (行 158-161); 测试断言预检恰 1 次 / 循环每 symbol 恰 1 次 (含「带宽」重叠 marker 误重试陷阱) | **通过** |

## 5. ROADMAP/需求逐句对照

| 需求句 | 证据 | 结果 |
|---|---|---|
| HON-01: xyz_provider.py:189-198/:228-250 HTTP 403/配额窗 markers 分类为 policy-block 信号 (typed 异常或带 reason 空帧) | `_is_policy_block` + `_call_tool` 重抛 + `get_auction` 原样重抛 (typed 异常形态; 空帧仅 daily/minute 降级路径) | PASS |
| HON-01: 其余网络错误保持「空帧不抛」契约 (test_xyz_provider.py:126-137 保持绿) | Test 4 零改动 + family 跑绿; 分类器边界实测 500/timeout → False | PASS |
| HON-01: 台账 reason 第三类 `"source_blocked"` (两键形状 {symbol,reason} 不变, 与 empty_response/str(e)[:200] 互斥) | 行 336-338 + 三态互斥测试 + 两键形状断言 | PASS |
| HON-01: `services/auction_probe.py` preflight 遇 policy-block → verdict `fail_closed` + detail=`"source_blocked"` | 行 162-172 + `test_source_blocked_provider_is_fail_closed` | PASS |
| HON-01: R1 重试只对可重试态生效 | `_fetch_auction` 先捕 SourceBlockedError (429/限速文案才进退避面) + 调用计数断言 | PASS |
| HON-02: 所有 fail-closed 提前返回路径 (行 200/224/228/266/268) 补终态 emit (每 symbol 一行, 含 reason) | 现实现 6 条路径全部 emit (行 217/242/247/286/290/293; 行号因插入移位, 语义与需求句一致) + 五路径 emit 测试 | PASS |
| HON-02: 取消路径独立 stage (`cancelled`/实际 pct, 绝不 `done`/100) | cancelled stage + done 门 + 双段取消测试 | PASS |
| HON-02: `scripts/auction_backfill.py` CLI 接 on_progress 打 stderr (现零进度输出) | `print(..., file=sys.stderr, flush=True)` + --help 冒烟 exit 0 | PASS |
| HON-02: 回归锁: 全空帧批量 → 断言每 symbol 进度行 + 终态 failed 计数正确 | `test_auction_backfill_all_empty_progress_and_failed_count` (1+3 行进度 / pct [33,66,100] / failed==2) | PASS |

## 6. PLAN-CHECK 对照 (0 blocker 3 warnings)

- **W1 (共享文件双 executor 并发)**: 已解决 — 41-01/41-02 经 IRC 协调提交边界, `git apply --cached` 精确暂存 hunks, 工作树合并后 41 族全绿; 41-01-SUMMARY 显式注记归属, 不重写历史。**无残留**。
- **W2 (verify 区分门语义 403 伪装移除)**: 已实现 — `_classify_source_block` 第三类独立归类, 测试改造 `_vacuum_empty_response` 新分支。**无残留**。
- **W3 (观察: pool_backfill.py:88-92,115 同类二次 done 反模式)**: 明确记录为 41-02 观察项, 不在本 phase 范围 (范围纪律), 建议后续 wave 对齐修复。**转 human_items #3**。

## 7. Human items (sandbox 无法断言)

1. **上游配额窗真实响应体回填 marker 表定稿**: `_POLICY_BLOCK_MARKERS` 注释标注「配额窗 2h 复现时按真实响应体回填定稿 (RESEARCH UNKNOWN flag)」— 当前 marker 词表基于研究期实测推断, 生产环境下次自然复现 2h 配额窗 (或人工触发) 时应核对真实响应体文案是否命中词表; 若出现未命中文案, 需回填定稿并补契约测试 (403 状态码面已全量覆盖, 此风险仅限 200 载荷文案面)。
2. **生产长任务真实取消路径**: 取消语义经代码读 + fake `job_store.get` 测试 (预置 failed / 循环中翻转) 验证; 生产形态 (真实 job 注册表 + 运行中多 symbol 任务被标记 failed → 下次迭代取消) 未在真实长任务上 live 观测 — 机制与既有 pool_backfill 合作式取消一致, 风险低, 但真实任务上的 stage/pct 输出建议首次运营观察。
3. **pool_backfill.py 同类反模式 (41-02 观察项)**: `pool_backfill.py:88-92,115` 存在相同的「取消 emit done/100 + 循环尾无条件 done」二次 done 反模式, 41-02-SUMMARY 已记录 — 建议后续 phase (对齐 HON-02) 修复, 本 phase 按范围纪律未动。

## 8. Honesty notes

- 所有 PASS 证据为本 verifier 亲自重观察: 自己的 pytest 跑 (64 + 74 passed, `-rs` 明示 skip 原因), 自己的 git log/diff/status 跑 (10 commits 顺序与 claim 一致, dep/Watchlist/126-137 守卫), 自己的分类器边界实测 + CLI --help 冒烟。
- 未采信 SUMMARY 文本: 行号 (217/242/247/286/290/293, 与需求原稿 200/224/228/266/268 因插入移位不一致但语义一一对应)、测试数、pass/skip 数均由本 verifier 独立重推导。
- 需求原稿行号 (200/224/228/266/268) 为规划期基线, 实现后因 `_emit_fail_closed` helper + emit 行插入位移 — 需求句语义 (所有 fail-closed 提前返回路径补 emit) 由五路径测试锁死, 非行号契约。
- `frontend/src/pages/Watchlist.tsx` 全程未读取, 仅经 `git diff/status` 核验: 提交内零触碰, 工作树唯一未暂存用户改动。
- 全量 backend 套件 (1836 passed 基线) 按分工由 orchestrator 收口, 本 verifier 只跑 41 族五文件, 不虚报全量。
