---
phase: 30-premarket-monitor
plan: 1
subsystem: monitoring
tags: [preopen, monitor-rules, polars, premarket, isolation, fail-closed]

# Dependency graph
requires: []
provides:
  - "preopen 规则类型 + PREOPEN_ALLOWED_FIELDS 白名单 + validate 专属分支 + _validate_conditions_shape/_validate_condition_field 公共 helper"
  - "strategy/preopen_eval.py 纯只读适配模块 (build_preopen_frame / extract_preopen_metrics) — 30-02 AST 守卫整文件扫描面"
  - "MonitorRuleEngine.evaluate_premarket(payload) 隔离评估入口 (事件标注 source/type=preopen, window=pre_open, provisional, degraded/probe 透传, strategy_ids, preopen_metrics)"
  - "D-03 盘中跳过回归锁: evaluate() 跳过集 {position, preopen}"
  - "T1-T10 测试套件 (tests/test_preopen_monitor_rules.py)"
affects: [30-02, 30-03]

actuals:
  tokens: 9508        # chars/4 over realized diff of the 4 touched files
  tasks: 3
  commits: 5          # 2×test(RED), feat, test, refactor(GREEN) — TDD 门序列

tech-stack:
  added: []
  patterns:
    - "preopen 白名单常量与 ALLOWED_FIELDS 并列 (禁 EOD 列, 镜像 builtin pre_open 策略语义)"
    - "独立只读评估模块 + 铁律 docstring (OQ-5/D-06, AST 守卫面)"
    - "隔离评估入口复用 _evaluate_rule 单一事件构建路径"
    - "诚实空态: available:false / 缺列 fail-closed / null-as-absent"

key-files:
  created:
    - backend/app/strategy/preopen_eval.py
    - backend/tests/test_preopen_monitor_rules.py
  modified:
    - backend/app/strategy/monitor_rules.py
    - backend/app/strategy/monitor.py

key-decisions:
  - "preopen 规则 op=truth 配置期显式拒绝 (D2 — 盘前帧无布尔信号列, 拒绝优于评估期静默)"
  - "scope 仅 symbols/all (D3 — sector/positions 与盘前语义无关, 与 /options scopes 下发一致)"
  - "帧重建只保留白名单+展示列, change_pct 恒 None 双保险 (R1 — 盘前帧 EOD 语义无意义)"
  - "cooldown 复用 _last_fire (rule_id, symbol) 域, preopen rule_id 与盘中规则天然隔离"
  - "事件 message 走 _default_message preopen 分支 (盘前 {条件摘要}), 数值由 preopen_metrics 结构化携带"

patterns-established:
  - "诚实缺列 fail-closed: _build_condition_mask field not in cols → head(0), 绝不 0 填/派生兜底"
  - "逐规则隔离评估 try/except warning (单条规则异常不丢弃整轮)"
  - "symbol 级去重 keep=first + source_strategies 排序列表 (多策略命中聚合)"

requirements-completed: [MON-01, MON-02, MON-04]

coverage:
  - id: D1
    description: "preopen 规则类型 + PREOPEN_ALLOWED_FIELDS 白名单 + validate 专属分支 (EOD 字段/op=truth/sector/positions 配置期 ValueError, normalize 默认值零改动)"
    requirement: MON-01
    verification:
      - kind: unit
        ref: "backend/tests/test_preopen_monitor_rules.py#test_preopen_validate_whitelist_positive"
        status: pass
      - kind: unit
        ref: "backend/tests/test_preopen_monitor_rules.py#test_preopen_validate_negative_cases"
        status: pass
      - kind: unit
        ref: "backend/tests/test_preopen_monitor_rules.py#test_preopen_normalize_defaults"
        status: pass
    human_judgment: false
  - id: D2
    description: "evaluate_premarket(payload) 隔离评估 — 帧重建 (symbol 去重/change_pct=None/source_strategies/白名单列), 事件字段标注, 策略池三属性零变化 (T7)"
    requirement: MON-02
    verification:
      - kind: unit
        ref: "backend/tests/test_preopen_monitor_rules.py#test_build_preopen_frame_dedup_and_columns"
        status: pass
      - kind: unit
        ref: "backend/tests/test_preopen_monitor_rules.py#test_preopen_event_fields"
        status: pass
      - kind: unit
        ref: "backend/tests/test_preopen_monitor_rules.py#test_evaluate_premarket_isolation_from_strategy_pools"
        status: pass
      - kind: unit
        ref: "backend/tests/test_preopen_monitor_rules.py#test_evaluate_premarket_cooldown"
        status: pass
    human_judgment: false
  - id: D3
    description: "D-03 盘中跳过回归锁 — evaluate() 规则循环跳过集 {position, preopen}, open_gap 规则盘中 0 事件 (T6)"
    verification:
      - kind: unit
        ref: "backend/tests/test_preopen_monitor_rules.py#test_evaluate_intraday_skips_preopen_rules"
        status: pass
    human_judgment: false
  - id: D4
    description: "引擎层 MON-04 诚实降级 — degraded/缺列 → auction_* 规则 fail-closed 0 命中, open_gap 仍命中且事件 degraded=True; 单 symbol 缺竞价值按标的缺席; available:false → []"
    requirement: MON-04
    verification:
      - kind: unit
        ref: "backend/tests/test_preopen_monitor_rules.py#test_preopen_degraded_fail_closed"
        status: pass
      - kind: unit
        ref: "backend/tests/test_preopen_monitor_rules.py#test_preopen_absent_symbol_not_hit"
        status: pass
      - kind: unit
        ref: "backend/tests/test_preopen_monitor_rules.py#test_evaluate_premarket_empty_states"
        status: pass
    human_judgment: false

# Metrics
duration: 31min
completed: 2026-08-06
status: complete
---

# Phase 30 Plan 1: 盘前监控后端核心 Summary

**preopen 规则类型 + 独立只读评估模块 (preopen_eval.py) + 隔离的 evaluate_premarket 入口 + D-03 盘中跳过回归锁, 配套 T1-T10 测试全绿**

## Performance

- **Duration:** 31 min
- **Started:** 2026-08-06T13:10:30Z
- **Completed:** 2026-08-06T13:41:21Z
- **Tasks:** 3 (tracer-first 垂直切片 → 边界/隔离/cooldown 扩张 → 降级/负例/message/helper 收尾)
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments

- **MON-01 规则面**: `preopen` 追加进 `RULE_TYPES`; `PREOPEN_ALLOWED_FIELDS = frozenset({open_gap, auction_volume, auction_amount, auction_volume_ratio, auction_unmatched_amount})` 与 `ALLOWED_FIELDS` 并列; `validate()` preopen 专属分支 — scope 仅 symbols/all、op=truth 显式拒绝、EOD 列 (change_pct/close/vol_ratio_5d/amount) 白名单外 ValueError、value 必须数字; `normalize()` 零改动 (T3 断言默认值)。
- **MON-02 隔离评估**: `MonitorRuleEngine.evaluate_premarket(payload)` — payload rows 抽 symbol 去重重建 Polars 帧 (change_pct 全 None、close/code 剥离、source_strategies 排序), 逐规则复用 `_evaluate_rule` (scope/mask/cooldown/单事件构建路径), 事件标注纯增量键 (source/type=preopen, window=pre_open, provisional, degraded/probe, strategy_ids, preopen_metrics); T7 隔离断言证明 `_strategy_pools`/`_latest_strategy_results`/`_building_strategy_results` 三属性零变化。
- **D-03 回归锁**: `evaluate()` 盘中跳过集改为 `{position, preopen}` — open_gap 规则盘中 0 事件 (T6)。
- **MON-04 诚实降级 (引擎层)**: 缺列 → `_build_condition_mask` head(0) fail-closed (T9/T10); 单 symbol 缺竞价值 → 该 symbol 不命中且 preopen_metrics 缺键; available:false → `[]` (T6 空态)。
- **OQ-5/D-06**: `strategy/preopen_eval.py` 纯只读模块 (铁律 docstring 镜像 premarket_pool.py:1-18, 仅 import stdlib + polars + PREOPEN_ALLOWED_FIELDS), 供 30-02 整文件 AST 守卫扫描。
- **唯一既有代码重构**: conditions 形状校验抽为 `_validate_conditions_shape` + 按类型分派的 `_validate_condition_field`, 错误消息逐字节等价 (helper 等价回归绿)。

## Task Commits

Each task was committed atomically (TDD 门序列: test(RED) → feat/refactor(GREEN)):

1. **Task 1: preopen 规则类型 + 独立评估核心垂直切片 + D-03 盘中跳过** — `c81a290` (test, RED) + `a0e43ff` (feat, GREEN)
2. **Task 2: 帧构建边界 + 隔离断言 + cooldown 扩张** — `183bb27` (test)
3. **Task 3: 诚实降级 + 校验负例 + preopen message + helper 抽取收尾** — `d16cd70` (test, RED) + `5702ada` (refactor, GREEN)

**Plan metadata:** `(final docs commit — 见下文)`

## Files Created/Modified

- `backend/app/strategy/preopen_eval.py` (created) — 纯只读盘前评估适配模块: `build_preopen_frame(payload)` (symbol 去重 keep=first、白名单+展示列、change_pct=None、source_strategies) + `extract_preopen_metrics(frame, symbol)` (非 None 白名单数值), 铁律 docstring。
- `backend/app/strategy/monitor_rules.py` (modified) — `RULE_TYPES` + preopen; `PREOPEN_ALLOWED_FIELDS` 白名单常量; validate preopen 分支; `_validate_conditions_shape`/`_validate_condition_field` 公共 helper (else 分支迁移, 消息等价)。
- `backend/app/strategy/monitor.py` (modified) — `evaluate()` 跳过集 {position, preopen} (D-03); `evaluate_premarket(payload)` 隔离入口; `_default_message` preopen 分支 (盘前 {条件摘要}); `_match_strategy` 池基线警示注释; 顶层 import preopen_eval。
- `backend/tests/test_preopen_monitor_rules.py` (created) — T1-T10: 白名单正例/负例, normalize 默认, 帧构建核心+边界, 事件字段, 盘中跳过回归, 隔离断言, cooldown, 降级 fail-closed, 按标的缺席, message, helper 等价。

## Decisions Made

- op=truth 配置期拒绝 (D2) — 盘前帧全数值无布尔信号列, 拒绝优于评估期静默 fail-closed。
- scope 仅 symbols/all (D3) — sector/positions 与盘前语义无关; validate 期拒绝。
- 帧内 change_pct 恒 None (R1 双保险) — 与白名单禁 EOD 列互为双保险, 防行内残留 EOD 值冒入事件。
- 事件 message 走 `_default_message` preopen 分支, 具体数值由 `preopen_metrics` 结构化携带 — message 稳定可断言 (与 30-02/30-03 消费契约一致)。
- 测试生产 import 放函数内 (hermetic) — 按计划约定, 引擎直构镜像 test_monitor_etf 惯例。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Task 1 测试 helper 生成非法规则 id (`r_open_gap_>` 含 `>` 字符)**
- **Found during:** Task 1 (TDD RED 首次运行)
- **Issue:** `_preopen_rule(f"r_{field}_{op}", ...)` 的 op 直接拼进 id, `>` 违反 `ID_RE = ^[a-z0-9_]{1,40}$`, validate 抛「规则 id 非法」而非预期的 preopen 分支行为。
- **Fix:** 测试内 op → 单词后缀映射 (gt/gte/lt/lte/eq/ne), id 合法化。
- **Files modified:** backend/tests/test_preopen_monitor_rules.py
- **Verification:** 重跑后 RED 变更为真正的特性缺失 (type 必须是 {...} 之一), 后续全绿。
- **Committed in:** c81a290 (Task 1 RED 提交内)

**2. [Rule 1 - Bug] Task 2 cooldown 测试期望语义错误 (r_cd2 自冷却, 非跨规则干扰)**
- **Found during:** Task 2 (T8 首次运行 1 failed / 9 passed)
- **Issue:** `r_cd2` 也设了 cooldown=3600 — 第二次调用时它被**自己的**冷却挡住, 期望 2 事件实际 1 事件。实现 (key=(rule_id, symbol)) 行为正确; 测试期望与计划「异 rule_id 不受影响」语义不符。
- **Fix:** `r_cd2` 改 cooldown=0 (独立触发验证), 并补充计划措辞的严格版: 单条 cooldown=3600 规则第一次 1 事件 → 第二次 0 事件。
- **Files modified:** backend/tests/test_preopen_monitor_rules.py
- **Verification:** 全文件 10 passed; 实现零改动 (Task 2 计划的条件修复路径未触发)。
- **Committed in:** 183bb27 (Task 2 提交内)

---

**Total deviations:** 2 auto-fixed (2 Rule 1, 均为测试侧修正, 生产代码零偏差)
**Impact on plan:** 无 — 生产实现 (monitor_rules.py / preopen_eval.py / monitor.py) 与计划 action 逐项一致, 无范围蔓延。

### TDD 门说明 (非偏差, 计划设计使然)

- Task 2 的 4 个扩张测试在 Task 1 实现已覆盖的边界上编写 — RED 阶段即通过 (特性已存在), 按计划 action 5 的「若实现暴露缺陷则修, 否则回跑」路径执行, 未触发修复。
- Task 3 的 T2/T9/helper 等价测试同样由 Task 1 内联实现先行满足; message 测试为唯一真 RED (无 preopen message 分支), RED→GREEN 闭环完整。
- 门序列检查: Task 1 有 test(RED)→feat(GREEN) 提交对; Task 3 有 test(RED)→refactor(GREEN) 提交对; Task 2 为纯 test 提交 (无实现变更, 无 GREEN 提交必要) — 符合计划任务结构。

## Issues Encountered

- 计划 RESEARCH §4.3/PATTERNS 声称 `_format_conditions_text` 将 op `>=` 渲染为 `≥`; 实测渲染为 `open_gap>=0.05` (op_map 键为 gte/lte/gt/lt/eq, 与 OPS 符号不匹配, `op_map.get(op, op)` 原样透传)。测试按「与 `_format_conditions_text` 同款渲染」断言 (`message == f"盘前 {cond_text}"`), 对字形鲁棒 — 不改动既有渲染器 (计划要求零改动), 记录供 30-03 前端/文档对齐参考。
- 无阻塞问题; 无 auth 门; 无 package 安装。

## Known Stubs

None — 无占位/空值流 (事件 message 由真实条件摘要生成; preopen_metrics 为命中行真实数值)。

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 30-02 (wave 2) 可直接消费: `evaluate_premarket(payload)` 契约 (事件键集 source/type/window/provisional/degraded/probe/strategy_ids/preopen_metrics 已稳定) + `preopen_eval.py` 整文件 AST 守卫扫描面 (仅 import stdlib + polars + PREOPEN_ALLOWED_FIELDS)。
- 09:26 尾段接线点 (daily_pipeline `_premarket_pool_preview` persist 后 / emit done 前) 与 quote_service `evaluate_premarket_alerts` 的编排/持久化/SSE/webhook 由 30-02 实现。
- 前置知识: message 渲染字形 (`>=` 而非 `≥`) 已在 Issues 记录, 30-03 前端/飞书模板断言时注意。

---
*Phase: 30-premarket-monitor*
*Completed: 2026-08-06*
