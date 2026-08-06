# Phase 30 盘前监控告警 — PLAN-CHECK (Pre-Execution)

**Phase:** 30-premarket-monitor (MON-01..07)
**Plans checked:** 30-01 / 30-02 / 30-03
**Checked:** 2026-08-06 (PlanCheckerP30, Revision Gate — 静态计划分析, 未运行应用/构建/测试, 未触碰 Watchlist.tsx 与任何源文件)
**Method:** Goal-backward — 从 ROADMAP Phase 30 Goal + MON-01..07 出发, 逐计划核对需求覆盖 / 任务完整性 / 依赖图 / 关键接线 / 作用域 / 隐藏阻塞点, 并对 RESEARCH.md 全部关键锚点做了源码实读抽查 (grep 级验证, 非 grep 处均标注)。

---

## Verdict

**PASS — 2 WARNING, 2 NOTE, 0 BLOCKER.** 三份计划可执行: 需求全覆盖 (MON-01..07), 依赖图无环, 任务字段完备, 关键接线已规划, 隐藏阻塞点全部排除。两个 WARNING 均可在执行期前低成本修正 (文档措辞对齐 + nyquist 工件决策), 不阻断执行。

---

## Per-Plan Verdict

### 30-01 — 后端核心 (MON-01 / MON-02 / 引擎层 MON-04) — ✅ VALID

- **需求映射:** MON-01 (preopen 类型 + PREOPEN_ALLOWED_FIELDS + validate 专属分支 + `_validate_conditions_shape`), MON-02 (evaluate_premarket 隔离评估 + 帧重建 + 事件标注), 引擎层 MON-04 (降级 fail-closed + 按标的缺席 + 诚实空态), **D-03 盘中跳过回归锁 (T6)** 显式在列。
- **锚点实读核对 (全部命中):** `RULE_TYPES` :29 / `validate` :101-201 / `normalize` :203-241 / `_is_signal_field` :96 / `ALLOWED_FIELDS` (custom_signals import) / `MonitorRuleEngine` :329 / `evaluate` :497 / `_evaluate_rule` :617 / `_apply_scope` :702 / `_match_conditions` :903 / `_build_condition_mask` :281 (缺列 fail-closed) / `_default_message` :1005 / `_last_fire` :349 / `_strategy_pools`/`_latest_strategy_results`/`_building_strategy_results` :354-373 / `premarket_pool.py` 铁律 docstring :1-18 先例存在。
- **新文件由计划创建:** `strategy/preopen_eval.py` (Task 1 B, D-06 独立只读模块 — 整文件 AST 守卫面) + `tests/test_preopen_monitor_rules.py` (T1-T10)。测试文件名与全部 3 个任务的 `<verify>` 命令一致。
- **Import 无环 (已核对):** `monitor.py → preopen_eval.py → monitor_rules.py → custom_signals.py`; monitor_rules.py 仅 import custom_signals, 无回边; preopen_eval.py 仅 import stdlib + polars + `PREOPEN_ALLOWED_FIELDS`。
- **任务粒度:** 3 任务 (tracer-first 垂直切片 → 边界/隔离/cooldown 扩张 → 降级/负例/helper 收尾), 4 文件, wave 1, 每任务含 read_first/behavior/action/verify/done + 原子提交 done 标准。`_match_strategy` (:736, 池基线污染点) 明确严禁 + 警示注释 + T7 隔离断言 (三属性快照等值)。

### 30-02 — 后端接线 (MON-03 / MON-04 round-trip / MON-05 / MON-06 / MON-07 后端) — ✅ VALID

- **需求映射:** MON-03 (09:26 尾段 + evaluate_premarket_alerts 持久化优先链), MON-04 (event_json round-trip T17), MON-05 (AST 守卫 T19), MON-06 (mask_guest_alert T18), MON-07 后端 (/options preopen + preopen_threshold_fields T20)。
- **锚点实读核对 (全部命中):** `_evaluate_monitors` :1168 (persist-first :1266-1278, SSE dict :1278-1297 键集与 `_preopen_sse_shape` 增量键声明一致) / `_broadcast_alerts` :405 / `_maybe_send_webhook(rule_events, engine)` :1356 / `trigger_phase1_fixture_monitor` :635 (直调 seam 先例) / `_PREMARKET_JOB_ID` :969 / `_PREMARKET_HOUR,_PREMARKET_MINUTE = 9, 26` :970 / `_premarket_pool_preview` :1024 (persist :1058 → emit("done") :1059 — 尾段插缝与计划一致) / `scheduler.add_job` :1152-1160 (hour/minute/timezone/id/misfire_grace_time=1800 全对) / `mask_guest_hub` :23 / `MASKED_IDENTITY` :17 / `get_options` :65-66 (threshold_fields :72, types :99) / `alert_store.append_many(data_dir, events)` :52 (降级路径签名匹配) / `engine.rule_count` 属性 :460。
- **新文件由计划创建:** 4 个测试文件 (test_preopen_scheduling / test_preopen_honesty / test_preopen_ast_guard / test_preopen_api_options), 文件名与各任务 `<verify>` 命令逐一一致。AST 守卫镜像 `tests/test_pool_hub.py` (文件存在, E-guard 范本 :854-963 已在 RESEARCH 实读复核)。
- **兼容设计核实:** 尾段 `getattr(app_state, "quote_service", None)` → None → skip, 保证 `test_premarket_pool.py` 的 `_FakeRepo`/`SimpleNamespace` 不被破坏 (既有测试零改动); T14 快照路径断言 `premarket_results/date={as_of}/part.json` 与 `premarket_snapshot.py` 实际路径 :45/:66 一致。
- **任务粒度:** 3 任务, 8 文件 (阈值上沿但合规), wave 2, `depends_on: ["30-01"]` ✓。

### 30-03 — 前端 P2 (MON-07) — ✅ VALID

- **需求映射:** MON-07 前端 (api.ts 类型契约 + RuleEditor preopen 编辑 + Monitor.tsx provisional/degraded 徽标 + e2e + docs)。
- **锚点实读核对 (全部命中):** `api.ts` — `MonitorRule` :945 (type 联合), `MonitorRuleOptions` :973 (threshold_fields), `AlertEvent` :1004; `RuleEditor.tsx` — `TYPE_DEFAULT_NAME` :21-23, `addCond` :148-155, `thresholdFields` :173, SignalPicker 区 :373-378; `Monitor.tsx` — `TYPE_LABEL` :20-22, `SOURCE_BADGE_STYLE` :30-36, `DELIVERY_LABEL` :38-44 (徽标 chip 先例), AlertsList :220; 模拟对象 `premarket-pool.spec.ts` 存在 (installShell 先例); `docs/features.md` 监控中心小节 :97+ 存在。
- **新文件由计划创建:** `frontend/e2e/monitor.spec.ts` (Task 1 C), 与 `<verify>` 命令一致; `Watchlist.tsx` 不在 files_modified, 铁律 + git status 验证均在计划内。
- **任务粒度:** 2 任务, 5 文件, wave 3, `depends_on: ["30-02"]` ✓ (消费 /options 契约与事件键集, 零文件重叠)。

---

## Requirement Coverage (MON-01..07)

| Requirement | 30-01 | 30-02 | 30-03 | Status |
|-------------|-------|-------|-------|--------|
| MON-01 preopen 类型 + 白名单 + validate | ✅ T1-T3, helper | — | — | Covered |
| MON-02 evaluate_premarket 隔离评估 | ✅ T4-T8 (帧/事件/盘中跳过/隔离/cooldown) | — | — | Covered |
| MON-03 09:26 尾段 + 持久化优先链 | — | ✅ T11-T16 | — | Covered |
| MON-04 诚实标注 + fail-closed + round-trip | ✅ T9-T10 (引擎层) | ✅ T17 (持久化层) | — | Covered |
| MON-05 零执行 + AST 守卫 | — | ✅ T19 | — | Covered |
| MON-06 guest 掩码 | — | ✅ T18 | — | Covered |
| MON-07 /options + 前端 (P2) | — | ✅ T20 (后端) | ✅ (前端 + e2e + docs) | Covered |

PROJECT.md v2.2 目标「盘前预览进入监控告警」已覆盖; 无遗漏映射的里程碑需求。

---

## Dimension Table

| # | Dimension | Result | Notes |
|---|-----------|--------|-------|
| 1 | Requirement Coverage | ✅ PASS | MON-01..07 全覆盖; 无需求缺席 (计划前 frontmatter `requirements` 字段与 roadmap 一致) |
| 2 | Task Completeness | ✅ PASS | gsd-tools `verify.plan-structure`: 3/3/3/2 任务全部 hasFiles+hasAction+hasVerify+hasDone; action 具体到文件/函数/行段; verify 为可运行 pytest/playwright 命令 |
| 3 | Dependency Correctness | ✅ PASS | 30-01 (wave 1, []) → 30-02 (wave 2, [30-01]) → 30-03 (wave 3, [30-02]); 无环、无前向引用、wave = max(deps)+1 |
| 4 | Key Links Planned | ✅ PASS | 帧构建→引擎 (build_preopen_frame); job 尾段→quote_service (内存 payload, 免二次读盘); quote_service→operational (record_alert_event); editor→/options (preopen_threshold_fields); Monitor.tsx→SSE 增量键; 每链均有实现任务 |
| 5 | Scope Sanity | ✅ PASS | 任务 3/3/2 (阈值内); 文件 4/8/5 (30-02 在 5-8 上沿); estimate 46k/48k/34k tokens, confidence=low (未校准, 按任务/文件阈值加权) |
| 6 | Verification Derivation | ✅ PASS | truths 以验收行为表述 (白名单拒绝 / 隔离断言 / 事件字段 / fail-closed), 非纯实现细节 |
| 7 | Context Compliance | ⚠️ 见 W-1 | 无 CONTEXT.md (Dimension 7 N/A); 需求级对照发现 ROADMAP/REQUIREMENTS MON-01 措辞与实现不一致 (`op=truth`) |
| 7b | Scope Reduction | ✅ PASS | 无 v1/static/stub/未来接线语言; OQ-2 (scope=sector)/OQ-3 (未触发日志) 为研究层明确延后项 (域研究原文「sector 可后续」), 非用户决策缩水 |
| 7c | Architectural Tier | ⛔ SKIPPED | RESEARCH.md 无 Architectural Responsibility Map 小节 |
| 8 | Nyquist | ⛔ SKIPPED + ⚠️ 见 W-2 | RESEARCH.md 无「Validation Architecture」小节 → 按顶层 skip 规则 SKIPPED; VALIDATION.md 缺失 (见 W-2) |
| 9 | Cross-Plan Data Contracts | ✅ PASS | 共享实体 = preopen 事件 dict + payload: 30-01 定义键集 → 30-02 全量透传 (SSE/event_json) → 30-03 可选字段消费; 无裁剪/冲突变换; payload 全程只读 |
| 10 | CLAUDE.md Compliance | ⛔ SKIPPED | 工作目录无 `./CLAUDE.md` 且 `.claude/CLAUDE.md` 不存在 |
| 11 | Research Resolution | ✅ PASS | RESEARCH §14 开放问题 OQ-1..5 均为「范围外/延后」且带处置 (OQ-5 已被计划落地为 preopen_eval.py; OQ-1 双保险覆盖); 无阻塞规划的问题 |
| 12 | Pattern Compliance | ✅ PASS | 每个新/改文件引用 PATTERNS.md analog; 共享模式 (persist-first/cooldown/fail-closed/失败非致命/AST 守卫/铁律 docstring/诚实 skip/逐规则隔离) 在任务 action 中落地 |
| — | Verify Command Format Sanity | ✅ PASS | 全部 `<automated>` 为直接 pytest/playwright 调用; 无 `^` 锚定包管理输出、无 `2>/dev/null || echo` 吞错、无硬编码计数断言 (T11 注册形 grep 为测试内容而非 verify 命令, 镜像既有先例) |
| — | Numeric/Factual Claim Authority | ✅ PASS | RESEARCH 锚点全部抽查命中; 前端行号轻微漂移 (见 N-2), 符号存在性无争议 |

---

## Hidden-Blocker Checklist (task 指定)

| 检查项 | 结果 |
|--------|------|
| `Watchlist.tsx` 零触碰 | ✅ 不在任何 plan 的 files_modified; 30-03 明示铁律 + 验证含 git status 确认 |
| strategy_cache 写入 | ✅ 三计划均禁止 (MON-05); 铁律 docstring + T19 守卫 token 缺位 + T7 隔离断言 |
| POOL-03 零执行权 | ✅ preopen 路径不 import 执行族/不写存储; AST 守卫按模块拆分 (preopen_eval.py 整文件 + 三函数段); test_pool_hub 既有 E-guard 扫描面 (pool_hub/pool/pool_snapshot) 零冲突 |
| D-03 evaluate() 盘中跳过 | ✅ 30-01 Task 1 (action C.1: `{position, preopen}` 跳过集 + 回归锁 T6); 防止 open_gap 规则盘中误触发 |
| Import 环 | ✅ 无环 (见 30-01 段): preopen_eval.py 独立, monitor.py → preopen_eval → monitor_rules → custom_signals 单向 |
| 测试文件名一致性 | ✅ 每个 `<verify>` 命令引用恰为对应任务 `<files>` 列表中的文件 (30-01: 1 文件; 30-02: 4 文件; 30-03: e2e/monitor.spec.ts) |
| 尾段接线顺序 (persist 后 / emit done 前) | ✅ 源码 :1058/:1059 与计划插缝一致; 失败非致命 (warning + preopen_eval.skipped 摘要, 镜像 _pool_eod_persist :1008-1015 风格) |
| 既有测试兼容 | ✅ 尾段 getattr 默认 None → skip 设计保证; normalize/validate 增量分支; evaluate 跳过集只加 "preopen"; /options 无 types 精确列表断言 (RESEARCH §12 已 grep 确认) |

---

## Issues

### W-1 [context_compliance / docs_alignment] REQUIREMENTS.md + ROADMAP 的 MON-01 措辞与实现相反 — `op=truth`

- **Plan:** 30-01 (Task 1/3) — 全计划
- **描述:** `REQUIREMENTS.md` MON-01 与 `ROADMAP.md` Phase 30 Success Criterion 1 均写「`op=truth` supported」; 但计划 (依 RESEARCH D2) 在 validate 中对 preopen 规则**显式拒绝 `op=truth`** (T2 负例断言 `op=truth → ValueError`)。域研究 `.planning/research/v2.2-decision-loop/MONITOR-PREOPEN.md` MON-01 原文明确「**禁止 op=truth** (pre-open 无布尔信号列)」——计划行为与设计权威一致 (truth 规则在盘前帧结构上不可能命中, 配置期拒绝优于评估期静默)。此为 ROADMAP/REQUIREMENTS 措辞伪影, 非用户决策违背。
- **风险:** 执行期/验收期 (gsd-verifier) 若按 REQUIREMENTS 字面「op=truth supported」验收, 会对 T2 拒绝行为误判为缺陷。
- **Fix (执行前低成本):** 将 `ROADMAP.md` Phase 30 SC-1 与 `REQUIREMENTS.md` MON-01 措辞改为「`op=truth` 显式拒绝 (配置期 ValueError)」或「truth 场景已处理 (拒绝)」; 或在 30-01-PLAN.md 补一行 D2 决策引用说明其优于字面措辞。

### W-2 [nyquist] VALIDATION.md 缺失 / RESEARCH 无 Validation Architecture 小节

- **Plan:** Phase 30 (全部)
- **描述:** `workflow.nyquist_validation=true`, 但 `.planning/phases/30-premarket-monitor/` 无 `*-VALIDATION.md`, 且 RESEARCH.md 无「Validation Architecture」小节 → 按 Dimension 8 顶层 skip 规则判定 **SKIPPED**。仓库先例: 归档的 24-27 均有 VALIDATION.md, 而当前里程碑 28/29 (已完成) 亦无 — 属 v2.2 规划流程缺口而非本计划独有。
- **Fix (决策):** 若期望本阶段 nyquist 校验, 重跑 `/gsd-plan-phase 30 --research` 补生成; 若接受 28/29 先例, 记录本 WARNING 为流程已知缺口 (执行器/验证器不需额外动作)。

### N-1 [advisory] estimate-check 工具不可用

- 本 gsd-tools 版本无 `estimate-check` 命令, #2631 校准检查未能执行。计划 estimate (46k/48k/34k tokens, confidence=low — 该仓 <3 个已完结相位带 actuals, 未校准) 仅作参考; 任务/文件阈值均合规, 不构成风险。

### N-2 [advisory] 前端行号轻微漂移

- 计划/RESEARCH 引用的前端行号比实际代码偏 3-6 行 (RuleEditor `TYPE_DEFAULT_NAME` :26-28→实际 :21-23, `thresholdFields` :191→:173; Monitor.tsx `TYPE_LABEL` :25-29→:20-22; api.ts `AlertEvent` :1000-1011→:1004+)。符号全部存在, 行号为指引性, 执行时按符号定位即可。

```yaml
issues:
  - plan: "30-01"
    dimension: context_compliance
    severity: warning
    description: "ROADMAP/REQUIREMENTS MON-01 措辞 'op=truth supported' 与计划实现 (D2: op=truth 显式拒绝, T2 ValueError 断言) 相反; 域研究 MONITOR-PREOPEN.md MON-01 原文支持计划 (禁止 truth)"
    fix_hint: "执行前对齐 ROADMAP.md SC-1 与 REQUIREMENTS.md MON-01 措辞为 'op=truth 显式拒绝', 或在 PLAN 中引用 D2 决策说明"
  - plan: "30 (phase-level)"
    dimension: nyquist_compliance
    severity: warning
    description: "nyquist_validation=true 但 VALIDATION.md 缺失且 RESEARCH.md 无 Validation Architecture 小节 (Dimension 8 SKIPPED); 28/29 同缺为仓库先例"
    fix_hint: "决策: 重跑 /gsd-plan-phase 30 --research 补生成, 或接受 28/29 先例记为流程缺口"
  - plan: null
    dimension: scope_sanity
    severity: info
    description: "estimate-check 命令在本 gsd-tools 版本不存在, 校准检查未运行; 计划 estimate confidence=low (未校准)"
    fix_hint: "以任务/文件阈值为准 (3/3/2 任务, 4/8/5 文件, 均合规)"
  - plan: "30-03"
    dimension: task_completeness
    severity: info
    description: "前端行号引用漂移 3-6 行 (TYPE_DEFAULT_NAME/thresholdFields/TYPE_LABEL/AlertEvent); 符号均存在"
    fix_hint: "执行时按符号名定位, 行号仅指引"
```

---

## Recommendation

**0 个 blocker — 计划可进入执行 (`/gsd-execute-phase 30`)。** 建议执行前 (或执行首波并行时) 由 orchestrator 处理 W-1 (一处文档措辞对齐, 约 5 分钟), 并对 W-2 做流程决策。无需求缩水、无架构错层、无数据契约冲突、无隐藏阻塞点; 既有测试兼容由设计保证 (getattr skip / 增量分支 / 扫描面零冲突)。

*静态计划检查完成 — 未修改任何源文件/计划, 未运行构建/测试, 未触碰 Watchlist.tsx。*
