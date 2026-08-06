---
phase: 30-premarket-monitor
plan: 2
subsystem: monitoring
tags: [preopen, scheduling, quote-service, guest-masking, ast-guard, options, persist-first]

# Dependency graph
requires: ["30-01 (evaluate_premarket + preopen_eval.py + PREOPEN_ALLOWED_FIELDS)"]
provides:
  - "MON-03 调度接线: _premarket_pool_preview 尾段 (persist 后同 _run_tracked 单飞内, 内存 payload) → QuoteService.evaluate_premarket_alerts (持久化优先 → SSE → webhook, 无时间 gate)"
  - "MON-04 持久化 round-trip: record_alert_event → get_alert_event 全字段保真 (event_json 全量快照, 不改表)"
  - "MON-06 防御性脱敏: guest_masking.mask_guest_alert (身份 ****** + 竞价值剥离 + 纯拷贝)"
  - "MON-07 后端: /api/monitor-rules/options 外露 preopen 类型 + preopen_threshold_fields (5 字段白名单 + ENRICHED_COLUMNS 中文标签)"
  - "MON-05 AST 守卫回归锁: preopen_eval.py 整文件 + 三函数段 (零执行族 import / 零写路径 / 零 run_all·persist_point_snapshot·strategy_cache 触发)"
affects: [30-03]

actuals:
  tokens: 11248        # chars/4 over realized diff (44,990 bytes, 8 files)
  tasks: 3
  commits: 6

tech-stack:
  added: []
  patterns:
    - "持久化优先: record_alert_event 落库成功才广播/投递 (逐字节镜像 _evaluate_monitors:1266-1278); operational=None → alert_store.append_many 降级 + 跳过投递"
    - "诚实 skip: engine 缺失 / payload 非 available → {skipped: ...} 早退, 不评估不告警 (T-30-02-05)"
    - "失败非致命: 尾段 try/except + warning + preopen_eval.skipped 摘要 (镜像 _pool_eod_persist concept_history 风格)"
    - "SSE 增量键: _preopen_sse_shape 在既有 SSE 键集上追加 window/provisional/degraded/probe/strategy_ids/preopen_metrics (纯增量, 旧客户端忽略未知键)"
    - "AST 守卫按模块拆分: preopen_eval.py 整文件白名单 (OQ-5) + monitor/quote_service/daily_pipeline 函数段 ast 子集解析"
    - "getattr 默认 None → skip 设计保证: test_premarket_pool._FakeRepo/SimpleNamespace app_state 零改动"

key-files:
  created:
    - backend/tests/test_preopen_scheduling.py
    - backend/tests/test_preopen_honesty.py
    - backend/tests/test_preopen_ast_guard.py
    - backend/tests/test_preopen_api_options.py
  modified:
    - backend/app/services/quote_service.py
    - backend/app/jobs/daily_pipeline.py
    - backend/app/services/guest_masking.py
    - backend/app/api/monitor_rules.py

key-decisions:
  - "尾段接线保持常量/单飞/cron 零改动 (T11 注册形锁死, 同一 _run_tracked 单飞内 persist 后 evaluate)"
  - "evaluate_premarket_alerts 无时间 gate (仅 09:26 job 触发; 盘中 evaluate() 跳过集 {position, preopen} 天然隔离)"
  - "degraded/probe 事件携带冻结快照 (round-trip 保真, 绝不静默 0 填 — T17)"
  - "mask_guest_alert 为防御性 DTO 边界 (当前 /api/alerts 为登录面, 无 guest 路径; 飞书/Telegram 所有者通道不受掩码约束)"
  - "T19 守卫扫描 docstring 剥离后的源码 (docstring 为禁令声明文本, 非调用面 — 见 Deviations)"

requirements-completed: [MON-03, MON-04, MON-05, MON-06, MON-07]

# Metrics
duration: 24min
completed: 2026-08-06
status: complete
---

# Phase 30 Plan 2: 后端接线层 Summary

**09:26 盘前 job 尾段接入统一告警链 (evaluate_premarket_alerts 持久化优先 → SSE → webhook) + mask_guest_alert 防御性脱敏 + /options preopen 白名单外露 + AST 守卫回归锁, 配套 T11-T20 测试全绿**

## Performance

- **Duration:** 24 min
- **Started:** 2026-08-06T14:02:00Z
- **Completed:** 2026-08-06T14:26:00Z
- **Tasks:** 3 (tracer 垂直切片 → 诚实接线扩张 → API 选项面 + AST 守卫)
- **Files modified:** 8 (4 created, 4 modified)
- **Test counts:** 16 计划内 (T11-T20) + 85 回归 (test_monitor_etf / test_pipeline_and_monitor_fixes / test_position_monitor / test_guest_masking / test_pool_hub / test_premarket_pool) 全绿

## Accomplishments

- **MON-03 调度接线**: `_premarket_pool_preview` 尾段在 `persist_premarket_snapshot` 之后、`emit("done")` 之前插入 — 同一 `_run_tracked` 单飞内, 内存直取 payload (T12 断言 `calls[0][1] is payload`, 免二次读盘); `getattr(app_state, "quote_service", None)` → None → 诚实 skip (`{"skipped": "quote_service not assembled"}`, 保证 test_premarket_pool 的 `_FakeRepo`/`SimpleNamespace` 零改动); 失败非致命 (T14: 快照文件存在 + job 成功返回 + `preopen_eval.skipped == "evaluation error"`); job result 追加 `preopen_eval` 摘要 (available:false 路径不追加键 — T13)。注册常量 `_PREMARKET_JOB_ID/_HOUR/_MINUTE` 与 `scheduler.add_job` 零改动 (T11 注册形锁死: `id=_PREMARKET_JOB_ID` 恰一次)。
- **MON-03 服务编排**: `QuoteService.evaluate_premarket_alerts(payload) -> dict` 与 `_evaluate_monitors` 并列 — 无时间 gate (不调 `_is_continuous_trading`, 仅由 09:26 job 触发); engine 经 `getattr(self._app_state, "monitor_engine", None)` 取, 缺失 → `{"skipped": "no monitor engine"}`; 持久化优先逐字节镜像 `_evaluate_monitors:1266-1278` (落库成功才广播/投递, 失败 `logger.warning` 跳过); operational=None → `alert_store.append_many` 降级写路径 + 跳过投递 (T16 降级: SSE 仍广播 + enqueue 零调用); `_preopen_sse_shape(ev)` 在既有 SSE 键集基础上追加 window/provisional/degraded/probe/strategy_ids/preopen_metrics (纯增量键); `_broadcast_alerts` + `_maybe_send_webhook` 原样复用 (T16 集成: record → SSE 增量键 → feishu enqueue 全链)。
- **MON-04 round-trip**: `record_alert_event` → `get_alert_event` 全字段保真 (event_json 全量快照, 不改表) — window/provisional/degraded/probe/strategy_ids/preopen_metrics/conditions 逐键相等; degraded + probe 冻结快照 round-trip 保真 (T17, 绝不静默 0 填)。
- **MON-06 防御性脱敏**: `guest_masking.mask_guest_alert(event)` — 纯拷贝 (输入不被修改); symbol/name/code → `MASKED_IDENTITY`; 剥离 open_gap/auction_*/preopen_metrics/probe; `_GUEST_ALERT_VISIBLE` 白名单重建 (message/severity/window/provisional/degraded/rule_name/conditions/occurred_at/rule_id/source/type); 缺键容忍 (T18 防御性); 飞书/Telegram 所有者通道不受掩码约束。
- **MON-07 后端**: `/api/monitor-rules/options` — `types` 追加 `{key: "preopen", label: "盘前异动"}`; 新增 `preopen_threshold_fields` (5 白名单字段 + `ENRICHED_COLUMNS` 中文标签, 零新标签表); operators/scopes/logics/severities/directions 零改动; preopen 不污染 threshold_fields (T20: change_pct/close 仍在 threshold_fields, open_gap/auction_* 不在)。
- **MON-05 AST 守卫**: `test_preopen_ast_guard.py` (镜像 test_pool_hub E-guard) — preopen_eval.py 整文件 + monitor.evaluate_premarket / quote_service.evaluate_premarket_alerts / daily_pipeline._premarket_pool_preview 三函数段: 无执行族 import、无写路径 (open-w/write_parquet/os.replace/unlink/mkdir)、无 run_all/run_all_with_hits/persist_point_snapshot/strategy_cache/write_cache 触发 token; monitor 段不含 `_match_strategy` (池基线污染点零触碰)。test_pool_hub 既有 E-guard 35 测试回归绿 (扫描面零冲突)。

## Task Commits

Each task was committed atomically (TDD 门序列: test(RED) → feat/refactor(GREEN)):

1. **Task 1: MON-03 垂直切片 — 尾段接线 + evaluate_premarket_alerts 持久化优先链** — `cbf9c03` (test, RED) + `2c5469e` (feat, GREEN)
2. **Task 2: 诚实接线扩张 — 注册形锁 / skip / 失败非致命 / round-trip / mask_guest_alert** — `6d7ce1e` (test, RED) + `1b126e9` (feat, GREEN)
3. **Task 3: /options 外露 preopen + preopen_threshold_fields + AST 守卫 T19** — `a0beaca` (test, RED) + `139815f` (feat, GREEN)

**Plan metadata:** `(final docs commit — 见下文)`

## Files Created/Modified

- `backend/app/services/quote_service.py` (modified) — `evaluate_premarket_alerts(payload)` (engine getattr → 诚实 skip → evaluate_premarket → 持久化优先 → `_preopen_sse_shape` 广播 + `_maybe_send_webhook`; 返回 {rules, events, degraded, probe_status}); `_preopen_sse_shape(ev)` 静态方法 (既有 SSE 键集 + 6 增量键)。
- `backend/app/jobs/daily_pipeline.py` (modified) — `_premarket_pool_preview` 尾段: persist 后同单飞内 `getattr(app_state, "quote_service", None)` → `evaluate_premarket_alerts(payload)`, 失败非致命 warning, job result 追加 `preopen_eval` 摘要 (available:false 路径零改动)。
- `backend/app/services/guest_masking.py` (modified) — `_GUEST_ALERT_VISIBLE` 白名单常量 + `mask_guest_alert(event)` (纯拷贝, 身份掩码 + 竞价值/探测剥离); mask_guest_hub 零改动。
- `backend/app/api/monitor_rules.py` (modified) — `get_options`: types 追加 preopen 盘前异动; 新增 `preopen_threshold_fields` (PREOPEN_ALLOWED_FIELDS + ENRICHED_COLUMNS 中文标签)。
- `backend/tests/test_preopen_scheduling.py` (created) — T11-T16: 注册形 grep / 尾段接线 (内存 payload 同一对象) / available:false skip / 失败非致命 / 时间无重叠 / 集成 (落库→SSE→投递) + 降级 append_many + skip 语义。
- `backend/tests/test_preopen_honesty.py` (created) — T17 round-trip 全字段保真 (含 degraded/probe 冻结快照); T18 mask_guest_alert 快照 + 缺键容忍。
- `backend/tests/test_preopen_ast_guard.py` (created) — T19 整文件 + 函数段 AST 守卫 (docstring 剥离后扫描)。
- `backend/tests/test_preopen_api_options.py` (created) — T20 /options preopen 类型 + 5 字段白名单 + 既有键不污染。

## Decisions Made

- 尾段接线保持调度注册零改动 (T11 锁死): 不新增 job、不碰常量, 与 persist 同一 `_run_tracked` 单飞内完成评估 — 免新 job 竞态 (D-07/D-04 保持)。
- `evaluate_premarket_alerts` 与 `_evaluate_monitors` 并列而非复用其主体 — 无时间 gate 是刻意差异 (09:26 由调度器独占触发), 持久化/广播/投递三件套逐字节复用。
- degraded 事件带冻结 probe 快照落库 (round-trip 保真) — 「为什么不报」排查由 job result 摘要 + 事件标志覆盖, 不新增「未触发日志」表 (OQ-3 保持 v2.2 范围)。
- mask_guest_alert 白名单含 message/conditions (盘前文案非 PII) — 与 RESEARCH §8 字段清单逐字一致。
- T19 扫描 docstring 剥离后的源码 — 30-01 交付的 preopen_eval.py 铁律 docstring 本身枚举被禁 token (禁令声明), 逐字扫描会误伤; 剥离后守卫意图 (零执行调用/零写路径) 完全保留 (见 Deviations)。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Test-side] T19 AST 守卫需剥离 docstring 后扫描**
- **Found during:** Task 3 (T19 编写)
- **Issue:** 计划要求「整文件/函数段统一断言 (无执行族 import、无写路径、无 run_all/persist_point_snapshot 触发 token)」, 但 30-01 交付的 preopen_eval.py 铁律 docstring 与 monitor.py evaluate_premarket docstring 本身**声明式枚举**被禁 token (`strategy_cache.write_cache` / `persist_point_snapshot` / 执行族模块名), 逐字文本扫描必然误伤禁令声明 — 守卫会把「禁令文档」当成「违规调用」。
- **Fix:** `_strip_docstring(src, container)` 用 ast 提取并移除 docstring 段后再扫描 — docstring 是注释性文本, 非调用面/写路径; 守卫意图 (import 面白名单 + 写路径缺位 + 触发 token 缺位 + `_match_strategy` 零引用) 完全保留。
- **Files modified:** backend/tests/test_preopen_ast_guard.py
- **Verification:** T19 3 测试绿; test_pool_hub 既有 E-guard 35 测试回归绿 (其扫描面模块 docstring 不含被禁 token, 无需同改)。
- **Committed in:** a0beaca (Task 3 RED 提交内)

**2. [Rule 3 - Test-side] _make_app_state_with_quoteservice 不构造真实 StrategyEngine**
- **Found during:** Task 1 (T12 编写)
- **Issue:** 计划要求「复制 _make_app_state (test_premarket_pool.py:57-118 逐字) 并扩展」; 逐字复制需携带 canned 策略写入器。但 T12/T13/T14 全部 monkeypatch `premarket_pool.build_premarket_preview` 返回哨兵 payload, 策略引擎根本不会被执行 — 复制 canned 策略夹具属死代码。
- **Fix:** 保留 `_FakeRepo`/enriched 形 (latest_date 判定必需), 扩展 `quote_service` 属性; `strategy_engine=None` (build_premarket_preview 已 monkeypatch)。与 test_premarket_pool 形兼容, 免去重复夹具。
- **Files modified:** backend/tests/test_preopen_scheduling.py
- **Verification:** T12/T13/T14 绿; test_premarket_pool 全文件回归绿。
- **Committed in:** cbf9c03 (Task 1 RED 提交内)

**3. [计划结构说明, 非偏差] T13/T14 测试先行落入 Task 1 文件**
- **说明:** 计划 Task 1 Test 4 (skip 语义) 与 Task 2 Test 2/3 (T13 available:false skip / T14 失败非致命) 语义重叠; Task 1 的 `_premarket_pool_preview` 测试天然覆盖这两条行为, 故 T13/T14 随 Task 1 落地 (job 级), Task 2 按计划补充 T11/T15 注册形与时间无重叠锁。所有 6 项计划行为均实现且全绿, done 标准全部满足。

---

**Total deviations:** 3 (2 Rule 3 测试侧, 1 结构说明); 生产实现 (quote_service.py / daily_pipeline.py / guest_masking.py / monitor_rules.py) 与计划 action 逐项一致, 零范围蔓延, 零生产代码偏差。

### TDD 门说明 (非偏差, 计划设计使然)

- Task 1 有 test(RED)→feat(GREEN) 提交对; Task 2 有 test(RED)→feat(GREEN) 提交对 (T18 为真 RED — mask_guest_alert 缺失; T17/T11/T15 由既有实现与 Task 1 先行覆盖, RED 阶段即通过 — 计划 §11 已预期「扩张测试在实现已覆盖边界上编写」); Task 3 有 test(RED)→feat(GREEN) 提交对 (T20 为真 RED — /options 缺 preopen; T19 为回归锁, 守卫既有不变量即绿)。
- 门序列检查: 三任务均有 test(...) 后跟 feat(...) 提交, 无缺失门。

## Issues Encountered

- test_premarket_pool 的 2 个 starlette DeprecationWarning (per-request cookies) 为既有测试自身警告, 与本计划改动无关, 未触碰。
- 无阻塞问题; 无 auth 门; 无 package 安装 (零新增依赖, T-30-02-SC 不适用)。

## Known Stubs

None — 无占位/空值流。`mask_guest_alert` 当前无调用点属**设计使然** (防御性 DTO 守卫: /api/alerts 为登录面, 未来任何 guest 可见 alerts 表面必须经此函数 — RESEARCH §8/PATTERNS「No Exact Analog」明确), 非 stub。

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 30-03 (wave 3) 可直接消费: `/options` 契约 (`types` 含 preopen + `preopen_threshold_fields` 5 字段) + SSE 事件增量键集 (window/provisional/degraded/probe/strategy_ids/preopen_metrics) — 前端 api.ts/RuleEditor/Monitor.tsx 按 RESEARCH §9.2 消费; Watchlist.tsx 铁律保持 (本计划零触碰, 工作区该文件存在用户未提交改动, 未纳入任何提交)。
- 飞书模板可消费 `preopen_metrics` 结构化数值 (message 保持稳定可断言, 30-01 Issues 记录的字形 `>=` 已在前置知识中)。

---
*Phase: 30-premarket-monitor*
*Completed: 2026-08-06*
## Self-Check: PASSED
