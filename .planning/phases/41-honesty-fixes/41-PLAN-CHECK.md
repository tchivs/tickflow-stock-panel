# Phase 41 Plan Check — 诚实性修复 (Honesty Fixes)

**Checked:** 2026-08-07 · **Plans:** 41-01 / 41-02 · **Method:** goal-backward (gsd-plan-checker 惯例), 只读评审, 零代码修改
**参照物:** REQUIREMENTS.md HON-01..02 · ROADMAP Phase 41 (4 success criteria) · RESEARCH.md (轻量现状核实) · PATTERNS.md · 既有源码/测试逐条核实 (xyz_provider / auction_backfill / auction_probe / verify_auction_backfill / scripts/auction_backfill / test_xyz / test_auction_backfill / test_auction_backfill_honesty / test_auction_probe / test_verify_auction_backfill)

---

## Verdict: **EXECUTABLE**

0 blockers · 3 warnings · 2 info。行号全部与当前 HEAD 源码逐一核对 (见 D4 证据表); 既有测试保持绿承诺逐条锁定 (D5)。

## D1 — Goal-backward: 每 success criterion → 可观测验收 (反向无孤儿)

| ROADMAP Success Criterion | 覆盖 Plan/Task | 可观测验收 | 状态 |
|---|---|---|---|
| SC1: xyz 403/配额窗 markers → policy-block 信号; 其余网络错误空帧不抛 (test :126-137 保持绿) | 41-01 T1 (Test A/B/C/D/E) | `pytest.raises(SourceBlockedError)` 三用例; Test 4 (:126-137) 零改动绿; get_daily 空帧保持 | ✅ |
| SC2: 台账第三类 `source_blocked` (两键形状不变, 三态互斥); probe 遇 policy-block → fail_closed + detail "source_blocked"; R1 只对可重试态 | 41-01 T2 (Test 1-4) + T3 | 台账条目恰 `{"symbol","source_blocked"}`; 预检终态 reason 恰 `"source_blocked"`; verdict fail_closed+detail 常量; 每 symbol 恰 1 次调用 (零重试); verify 门 YES/真空文案 | ✅ |
| SC3: 五条 fail-closed 提前返回补终态 emit (含 reason); 取消独立 stage cancelled/实际 pct, 绝不 done/100 | 41-02 T1 (Test A/B) + T2 (Test C) | 五路径各 ≥1 行 `fail-closed: {reason}`; cancelled stage + 实际 pct; 取消后零 done 行 (二次 done bug 修复) | ✅ |
| SC4: CLI on_progress 打 stderr; 回归锁: 全空帧批量 → 每 symbol 进度行 + failed 计数正确 | 41-02 T2 (Test D + CLI) | `file=sys.stderr`; 回归锁: 4 行 auction_backfill stage + `回填完成: 0 成功, 2 失败` + failed==2 | ✅ |

**反向孤儿检查:** 全部 5 任务可回溯到 HON-01/02 与 SC1..4, 无孤儿任务; 需求覆盖 HON-01✅ HON-02✅。41-02 的取消二次 done/100 修复为 RESEARCH 新发现 (超需求但同属 SC3 语义), 已显式标注。

## D2 — 依赖/顺序

- 41-01 (wave 1, `depends_on: []`) → 41-02 (wave 2, `[41-01]`): 共享文件 `auction_backfill.py` + `test_auction_backfill.py` → 隐式依赖强制顺序 (wave 规则), 无环, 无前向引用。41-02 与 41-01 逻辑独立 (不 import 其符号), 顺序仅因文件共享 — 已注明。
- 41-01 任务顺序: T1 (信号产生) → T2 (消费) → T3 (verify 门) — 正确; T3 依赖 T2 的台账 reason 语义落地 (测试各自独立, 无文件冲突: T3 只动 verify 两文件)。
- 41-02 任务顺序: T1 (五路径 emit) → T2 (取消 + CLI + 回归锁) — 同文件顺序追加, 正确。

## D3 — 风险覆盖 (RESEARCH 遗留逐项)

| RESEARCH 遗留 | PLAN 处理 | 状态 |
|---|---|---|
| P2: 403-vs-真空吞错链 (36-03 事故) | 41-01 T1 三态化 (403/文案 → SourceBlockedError) + T2 台账第三类 + probe verdict + verify 门 — 四消费面闭环 | ✅ |
| P2: R1 重试死代码 → 只对可重试态 | 41-01 T2 `_fetch_auction` 先捕 SourceBlockedError 重抛 + Test 1 调用数==1 断言 (marker 重叠词不误重试) | ✅ |
| P3: 空帧批量进度冻结 (真因 = fail-closed 零 emit, 非 283-296) | 41-02 T1 五路径 emit (循环内 :308-313 已存在, 明确不重复实现) | ✅ |
| P3: 取消=done/100 | 41-02 T2 cancelled stage + done 门 (+ 新发现二次 done bug) | ✅ |
| xyz 403 真实响应体 UNKNOWN | 分类器双信号 (403 + `_POLICY_BLOCK_MARKERS` 常量可调), RESEARCH 标注 2h 窗复现时回填定稿 | ✅ (标注) |
| 全空帧批量整体 preflight_empty (回归锁陷阱) | PATTERNS 回归锁注: 预检 symbol 选无覆盖者绕门 — 41-02 T2 Test D 已按此设计 | ✅ |
| W-5 终态键集 (8/9 键) | 41-01/02 done 均断言键集不变; only_missing 空态返回 (8 键成功) 明确不加 emit | ✅ |

## D4 — 可执行性 (行号核对证据表)

| 计划引用 | 源码实测 | 判定 |
|---|---|---|
| xyz_provider.py:189-198 / :228-250 | get_auction try/except @ :193-197 (`except Exception` :194); _call_tool HTTP catch-all @ :243-247, error 分支 :248-250 | ✅ 一致 |
| xyz_provider.py:130-151 `_price_frame` | `_call_tool` 调用无 try/except (daily/minute 面) | ✅ 一致 |
| auction_backfill.py :200/224/228/266/268 | 五条 fail-closed 提前返回, 全部零 emit | ✅ 一致 |
| auction_backfill.py :308-313 循环 emit + :314 done | 逐 symbol emit 在循环内 (733b650e, git log 核实); done :314 取消后仍执行 (二次 done bug) | ✅ 一致 |
| auction_backfill.py :281-283 取消 | `emit("done", 100, "回填被取消")` + break | ✅ 一致 |
| auction_probe.py :161-167 | `except Exception` → error verdict | ✅ 一致 |
| verify_auction_backfill.py:187-217 | `_classify_source_block` 非 BJ empty_response → 疑似源受阻 | ✅ 一致 |
| scripts/auction_backfill.py:139 | on_progress lambda 打 stdout | ✅ 一致 |
| test_xyz_provider.py:126-137 | Test 4 空载荷/异常 → 空帧不抛 | ✅ 一致 (保持绿承诺) |
| 验收命令 | `pytest tests/test_xyz_provider.py -x` 等五条均为真实文件路径; `scripts/auction_backfill.py --help` argparse 退出 0 | ✅ 可运行 |

任务粒度: 3/2 任务, 全部含 files/action/verify/done; 动作达断言级 (逐测试名 + 期望值 + 注入面); 无 fenced code block 于 action 内; 无占位/降级措辞 (「v1/placeholder」类) — 每项需求都有完整实现路径。

## D5 — 回归面 (保持绿承诺)

- test_xyz_provider.py:126-137 (空帧契约): 41-01 T1 显式「零改动」+ Test D 复验 — 保持绿承诺成立。
- test_auction_backfill.py 既有 17 用例: 41-01 T2 与 41-02 均为**新增**用例 + 既有用例不修改 (除 41-02 T2 取消路径行为变更 → cooperative_cancel 终态键集断言不受影响, 已核实该测试不断言 done emit); 41-02 verify 命令整文件 -x。
- test_auction_backfill_honesty.py: 41-01 T2 新增类别互斥用例; 既有 W-5/BJ/形状用例零改动 (fail-closed 9 键含 reason 不变)。
- test_auction_probe.py: 新增 source_blocked 用例; `test_raising_provider_is_error` (RuntimeError → error) 不变 — 41-01 T2 已注明。
- test_verify_auction_backfill.py: 1 个既有用例断言随门文案更新 (empty_response 分支语义变化, HON-01 显式要求), 其余零改动。
- 零改动门: frontend/src/pages/Watchlist.tsx 未读未改 (两 plan files_modified 均无); base.py 仅追加异常类 (41-01 T1 files 内, 零破坏面 — 无 import 循环: base.py 无 app import)。

## 附加标准维度 (gsd-plan-checker 全维度)

- **结构有效性:** 2 plan 均含完整 frontmatter (phase/plan/type/wave/depends_on/files_modified/autonomous/requirements/must_haves/estimate); requirements 非空 (HON-01 / HON-02); 任务数 3/2 (目标 2-3)。
- **must_haves:** truths 为用户可观测断言级 (抛不抛/台账 reason/verdict detail/进度行数), 非实现细节; artifacts/key_links 完整。
- **Context Compliance:** 无 CONTEXT.md (本 phase 由需求文本定稿), RESEARCH/PATTERNS 先行 — 满足。
- **Architectural Tier:** 全部改动落 backend 服务/脚本/测试层, 无前端/DB schema 面 — PASS。
- **Pattern Compliance:** 镜像 stockdb_provider typed 异常 / policy 关键词判据 / 既有 emit 形状 / 既有测试 helper (file:line 全部核实) — PASS。
- **Nyquist:** 每任务均有 `<automated>` pytest/CLI 命令 (< 60s), 无 watch 模式, 无 MISSING 标记。
- **Verify 门卫生:** 无 `2>/dev/null || echo` 喂比较、无 `^` 锚定包管理输出; 回归锁断言用行数/字面量计数, 非 grep -c 文本。

---

## Warnings (should fix)

**1. [注释卫生] 41-01 T1 `_POLICY_BLOCK_MARKERS` 与 backfill `_RATE_LIMIT_MARKERS` 词面重叠 ("带宽"/"限速")**
- 重叠无害但有认知负担: `_fetch_auction` 先捕 `SourceBlockedError` 的结构性保证已锁死不误重试 (Test 1 调用数==1 断言)。若后续有人改 except 顺序会踩雷 — 已在 41-01 T2 action 与 PATTERNS 关键差异点显式标注「先捕」, 建议执行时在 `_POLICY_BLOCK_MARKERS` 定义处加一行注释指向该保证。

**2. [回归面] test_verify_auction_backfill.py 既有用例 `test_verify_partial_source_block_yes_non_bj_failures` 断言会随门文案更新而改**
- 属 HON-01 显式范围 (区分门第三类), 非破坏; 但该用例被 41-01 T3 与 41-02 验证清单共用 — 执行顺序为 41-01 T3 先行, 41-02 不触碰该文件, 无冲突。仅记录提醒。

**3. [信息面] 41-02 Test D 回归锁依赖 env fixture 的 kline_daily 仅覆盖 "000001.SZ"/"600000.SH" 两 symbol 的隐含前提**
- 若未来 env fixture 扩 symbol 集, 回归锁断言 (failed==2 / 行数==4) 会静默失效。建议 Test D 内显式注释该前提 (或按 symbols 参数动态计算期望), 已在 action 内写明注入面, 属低风险提醒。

## Info (suggestions)

1. 41-01 T1 的 `httpx.Response(403, request=httpx.Request(...))` 构造需 httpx 已安装 — backend deps 已含 httpx 0.28.1 (RESEARCH STACK 核实), 零风险。
2. 41-02 取消路径终态 dict 保持 8 键无 reason (部分成功语义, CLI 退出码 0) — 与现有 `_print_summary` 分支 (`"reason" in result`) 一致, 无需 CLI 侧改动; 若未来需要取消可见性可加 `"cancelled": true` 键, 属后续决策, 不在本 phase。

---

## 结论

两处诚实性缺口 (P2 吞错链 / P3 进度冻结+取消误报) 的计划完整: goal-backward 覆盖 4 条 success criteria 全绿, 风险逐项闭环, 行号与当前 HEAD 逐一核对零偏差 (含 RESEARCH 新发现的二次 done/100 bug 被 41-02 吸收), 既有测试保持绿承诺逐条锁定, 回归锁绕过 preflight_empty 门的陷阱已在设计内。**Verdict: EXECUTABLE** — 可直接进入 41-01 执行 (wave 1) → 41-02 执行 (wave 2)。
