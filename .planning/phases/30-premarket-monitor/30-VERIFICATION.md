---
phase: 30-premarket-monitor
verified: 2026-08-06T14:12:18Z
status: passed
score: 4/4 must-haves verified
behavior_unverified: 0 # 行为依赖 truth 均有命名测试覆盖不变量, orchestrator spot-check 确认通过 (acceptance 禁止本验证器重跑测试)
overrides_applied: 0
human_verification:
  - test: "交易日 09:26 实盘调度运行: 观察 09:26 job 是否触发 (日志 premarket_pool_preview), 预览落盘 premarket_results/date={T}/part.json, 尾段评估 preopen 规则, SSE 广播 + 飞书/Telegram 投递真实可达"
    expected: "09:26 准时触发 (单飞内 persist→evaluate), 命中规则产生事件 (带 provisional/degraded/probe), 飞书/Telegram 收到推送; 盘前预览 available:false 或 degraded 时无告警且状态在事件/日志中可查 (绝不静默)"
    why_human: "真实调度 + 实时行情 + 外部投递服务的运行时行为, 无法在静态验证中执行"
  - test: "真实后端用户流 (浏览器): 创建一条 preopen 规则 (类型下拉「盘前异动」→ 白名单字段下拉 → 无信号条件按钮 → open_gap 默认 → 保存), 然后查看告警列表渲染"
    expected: "规则保存成功 (后端 validate 接受); 告警列表 preopen 事件带「盘前·非最终」徽标, 降级事件带「数据降级」徽标, 无价格/涨跌幅 chip; 旧 signal 事件零回归"
    why_human: "e2e 已用 mock 覆盖渲染路径, 但真实前后端联通的用户流完成度需人工确认"
  - test: "设计裁决: 确认当前无游客可见的 alerts 渲染面会绕过 mask_guest_alert"
    expected: "接受现状 (mask_guest_alert 为防御性 DTO 守卫; /api/alerts 为登录面, 飞书/Telegram 为所有者通道不受掩码约束)"
    why_human: "MON-06 交付的是防御性边界而非活跃 guest 路径, 需人工确认产品侧接受"
---

# Phase 30: 盘前监控告警 Verification Report

**Phase Goal:** v2.1 premarket preview enters the unified alert chain — a new `preopen` monitor rule type (whitelisted pre-open fields, EOD columns banned), `evaluate_premarket()` isolated from the intraday `_strategy_pools` baseline, wired to the 09:26 preview job tail, with honest provisional/degraded/probe annotation and guest masking.
**Verified:** 2026-08-06T14:12:18Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth   | Status     | Evidence       |
| --- | ------- | ---------- | -------------- |
| 1   | SC1: `preopen` rule type validates against the whitelist (`open_gap`/auction cols, numeric ops only — `op=truth` explicitly rejected); EOD-only fields banned; `change_pct` set to `None` in the eval frame (honest) | ✓ VERIFIED | `monitor_rules.py` — `RULE_TYPES` 含 `"preopen"` (:22); `PREOPEN_ALLOWED_FIELDS = frozenset({open_gap, auction_volume, auction_amount, auction_volume_ratio, auction_unmatched_amount})` (:47-50); `validate()` preopen 专属分支 scope 仅 symbols/all (:200-205); `_validate_condition_field` preopen 分支显式拒绝 `op=truth` (中文 ValueError)、白名单外字段 (EOD 列 change_pct/close/vol_ratio_5d/amount 命中「不在盘前白名单」)、非数字 value (:148-159); `preopen_eval.py build_preopen_frame` 帧重建仅保留白名单+展示列, `change_pct` 恒 `None` (:64) — R1 双保险。测试: `test_preopen_validate_whitelist_positive` / `test_preopen_validate_negative_cases` / `test_preopen_normalize_defaults` / `test_build_preopen_frame_dedup_and_columns` 存在 (orchestrator spot-check: 5 preopen 测试文件 30 项通过) |
| 2   | SC2: `evaluate_premarket` runs in isolation — zero pollution of `_strategy_pools`/`_latest_strategy_results` (no spurious 09:30 dropped/new_entry) | ✓ VERIFIED | `monitor.py evaluate_premarket` (:545-604) 只评估 enabled type=preopen 规则, 复用 `_evaluate_rule` 单事件构建路径, 绝不调 `_match_strategy` (池基线污染点, :801-804 警示注释), docstring 声明三属性零触碰 (:557-559); 事件标注纯增量键 (source/type/window/provisional/degraded/probe/strategy_ids/preopen_metrics)。行为不变量由命名测试覆盖: `test_evaluate_premarket_isolation_from_strategy_pools` (T7, 三属性快照等值断言) + `test_evaluate_intraday_skips_preopen_rules` (T6, 盘中 `evaluate()` 跳过集 `{"position","preopen"}` :532) — orchestrator spot-check 通过 |
| 3   | SC3: Wired to 09:26 job tail (same single-flight, after persist); reuses operational → SSE → webhook | ✓ VERIFIED | `daily_pipeline.py _premarket_pool_preview` (:1024-1080) — persist (:1063) 后同单飞内尾段 (:1064-1078): `getattr(quote_service)` → `evaluate_premarket_alerts(payload)` (内存直取, 免二次读盘), 失败非致命 (warning + `preopen_eval.skipped`), available:false 路径零改动; `scheduler.add_job` id=`_PREMARKET_JOB_ID` 09:26 恰一次 (:1168-1176), `_run_tracked` 单飞。`quote_service.evaluate_premarket_alerts` (:1324-1372) 持久化优先链逐字节镜像 `_evaluate_monitors:1266-1278` — `record_alert_event` 落库成功才 `_broadcast_alerts(_preopen_sse_shape)` + `_maybe_send_webhook`; 无时间 gate (不调 `_is_continuous_trading`, 09:26 ∉ 连续竞价窗口天然互斥); operational=None → `alert_store.append_many` 降级 + 跳过投递。命名测试覆盖: T12 (persist 后恰一次调用、同 payload 对象) / T11 (注册形锁) / T15 (时间无重叠) / T16 (落库→SSE 增量键→webhook enqueue 集成链 + 降级路径) — orchestrator spot-check 通过 |
| 4   | SC4: `provisional/degraded/probe` annotated on events; degraded + auction-dependent rules fail closed (0 alerts, never silent-0-fill); guest-visible surfaces masked | ✓ VERIFIED | 事件标注: `evaluate_premarket` 对每个事件写 `provisional=True`/`degraded=payload.degraded`/`probe` (:590-598); 缺列 fail-closed: `_build_condition_mask` `field not in cols → return df.head(0)` (:283) — degraded 帧 auction 列规则 0 命中, open_gap 规则仍可命中且事件携带 `degraded:true`; 绝不 0 填/派生兜底。round-trip: `record_alert_event`→`get_alert_event` event_json 全量快照 — `test_alert_event_roundtrip_degraded_probe_frozen_snapshot` (T17, degraded/probe 冻结快照保真)。guest 掩码: `guest_masking.mask_guest_alert` (:91-110) 纯拷贝、身份 `******`、剥离 open_gap/auction_*/preopen_metrics/probe、`_GUEST_ALERT_VISIBLE` 白名单重建 — T18 快照 + 缺键容忍。前端渲染: `Monitor.tsx` `TYPE_LABEL.preopen '盘前'` (:23) + `SOURCE_BADGE_STYLE.preopen` cyan (:39) + `ev.source==='preopen'` 包裹的「盘前·非最终」/「数据降级」徽标 (:405-413); e2e 5 用例覆盖 (mock) — orchestrator spot-check: monitor e2e 5/5 通过 |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Deferred Items

无 — Phase 31 (竞价复盘) 目标/成功标准 (deterministic recap blocks / data_completeness / signal-quality block / 15:40 schedule) 不覆盖任何 MON-01..07 缺口; 研究层延后项 (OQ-2 scope=sector、OQ-3 未触发日志表) 为明确 out-of-scope 决策, 非本阶段缺口。

### Required Artifacts

| Artifact | Expected    | Status | Details |
| -------- | ----------- | ------ | ------- |
| `backend/app/strategy/monitor_rules.py` | preopen 类型 + 白名单 + validate 专属分支 + helpers | ✓ VERIFIED | RULE_TYPES 含 preopen; PREOPEN_ALLOWED_FIELDS 5 字段; `_validate_conditions_shape`/`_validate_condition_field` 公共 helper; op=truth/EOD 列/scope 配置期拒绝 |
| `backend/app/strategy/preopen_eval.py` | 独立只读模块 | ✓ VERIFIED | 铁律 docstring (禁令声明); 仅 import stdlib+polars+PREOPEN_ALLOWED_FIELDS; `build_preopen_frame` (symbol 去重/白名单列/change_pct=None) + `extract_preopen_metrics` (非 None 白名单数值); 零写路径 |
| `backend/app/strategy/monitor.py` | evaluate_premarket 隔离入口 + D-03 跳过 + preopen message | ✓ VERIFIED | `evaluate_premarket` (:545) 隔离评估; `evaluate()` 跳过集 `{"position","preopen"}` (:532); `_default_message` preopen 分支「盘前 {cond_text}」(:1116-1119) |
| `backend/app/services/quote_service.py` | evaluate_premarket_alerts 持久化优先链 | ✓ VERIFIED | engine getattr → 诚实 skip → evaluate_premarket → record_alert_event → SSE (`_preopen_sse_shape` 增量键) → webhook; 无时间 gate; operational=None 降级 append_many |
| `backend/app/jobs/daily_pipeline.py` | 09:26 尾段 hook | ✓ VERIFIED | `_premarket_pool_preview` persist 后同单飞内评估; 失败非致命; available:false 不评估不告警 |
| `backend/app/services/guest_masking.py` | mask_guest_alert 防御性脱敏 | ✓ VERIFIED | `_GUEST_ALERT_VISIBLE` 白名单重建; 身份掩码 + 竞价值/探测剥离; 纯拷贝; 缺键容忍 |
| `backend/app/api/monitor_rules.py` | /options preopen + preopen_threshold_fields | ✓ VERIFIED | types 含 `{key:"preopen", label:"盘前异动"}` (:112); `preopen_threshold_fields` 5 字段 + ENRICHED_COLUMNS 中文标签 (:78-81) |
| `backend/tests/test_preopen_ast_guard.py` | MON-05 AST 守卫 | ✓ VERIFIED | 3 测试: 整文件 (preopen_eval.py) + 三函数段 (evaluate_premarket/evaluate_premarket_alerts/_premarket_pool_preview) — 无执行族 import / 无写路径 / 无 run_all·persist_point_snapshot·strategy_cache 触发 / monitor 段无 `_match_strategy` |
| `frontend/src/lib/api.ts` | MonitorRule/MonitorRuleOptions/AlertEvent 类型 | ✓ VERIFIED | type 联合含 'preopen' (:950); `preopen_threshold_fields?` (:986); AlertEvent 增量可选 window/provisional/degraded/strategy_ids/preopen_metrics (:1033-1037) |
| `frontend/src/components/monitor/RuleEditor.tsx` | preopen 编辑路径 | ✓ VERIFIED | TYPE_DEFAULT_NAME.preopen (:24); thresholdFields 按类型切换 preopen→preopen_threshold_fields ?? [] (:178-180); addCond threshold 默认 open_gap (:157); preopen 隐藏 truth 按钮 + SignalPicker (:372, :383) |
| `frontend/src/pages/Monitor.tsx` | TYPE_LABEL + 徽标 | ✓ VERIFIED | TYPE_LABEL.preopen '盘前' (:23); SOURCE_BADGE_STYLE.preopen cyan (:39); provisional「盘前·非最终」+ degraded「数据降级」徽标以 `ev.source==='preopen'` 包裹 (:405-413); price/change_pct null → 既有 `!= null` 条件不渲染 chip |
| `frontend/e2e/monitor.spec.ts` | 5 e2e 用例 | ✓ VERIFIED | 编辑器 2 (白名单下拉/无 truth/open_gap 默认/保存载荷; 旧 /options 兼容) + 渲染 3 (双徽标/非降级/signal 零回归); installShell 独立 mock; orchestrator spot-check: monitor e2e 5/5 通过 |
| `docs/features.md` | 五类监控 + preopen 特性 | ✓ VERIFIED | 「五类监控」(:99) + 盘前监控表行 (:107) + 3 条 preopen bullet (:117-119) — 内容与实现逐项一致 |
| `frontend/src/pages/Watchlist.tsx` | 零触碰 | ✓ VERIFIED | phase 30 提交 (183bb27..cf30235) 均不含 Watchlist.tsx; git log 显示最近 Watchlist 提交为更早的 9c6c1fc 等; 工作区 `M` 状态为用户执行前未提交改动, 未纳入任何提交 |

### Key Link Verification

| From | To  | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `_premarket_pool_preview` (daily_pipeline) | `QuoteService.evaluate_premarket_alerts` | 尾段 getattr + 内存 payload 直传 | WIRED | :1068-1078 — persist (:1063) 后同一 `_run_tracked` 单飞内; T12 断言 `calls[0][1] is payload` |
| `evaluate_premarket_alerts` | `engine.evaluate_premarket` | getattr(self._app_state, "monitor_engine") | WIRED | :1337-1342 — engine 缺失 → `{"skipped": "no monitor engine"}` 诚实 skip |
| `evaluate_premarket` | `preopen_eval.build_preopen_frame` | 模块 import + 帧重建 | WIRED | monitor.py :12 import; :567 调用; 帧仅白名单+展示列 |
| `evaluate_premarket_alerts` | `operational.record_alert_event` | 持久化优先 | WIRED | :1354-1361 — 落库成功才广播/投递; 失败跳过 (不可审计事件不出现) |
| persist → SSE | `_preopen_sse_shape` | `_broadcast_alerts` | WIRED | :1363 — 既有 SSE 键集 + 6 增量键 (window/provisional/degraded/probe/strategy_ids/preopen_metrics), 旧客户端忽略未知键 |
| SSE → webhook | `_maybe_send_webhook(persisted, engine)` | 原样复用 | WIRED | :1364 — 与 `_evaluate_monitors` 同投递路径 |
| RuleEditor | `/api/monitor-rules/options` | `preopen_threshold_fields ?? []` | WIRED | RuleEditor.tsx :178-180 — 按类型切换字段表, 配置期白名单隔离 |
| Monitor.tsx | SSE 增量键 | `ev.source === 'preopen'` + 可选字段 | WIRED | Monitor.tsx :405-413 — 旧事件零渲染零崩溃 |
| `_build_condition_mask` | 缺列 fail-closed | `field not in cols → df.head(0)` | WIRED | monitor.py :283 — 绝不 0 填/派生兜底 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `evaluate_premarket` 事件 | frame rows | payload["results"] 行 → build_preopen_frame (symbol 去重) | ✓ real | 白名单数值来自预览行; change_pct/price 恒 None (诚实); preopen_metrics 为命中行真实非 None 数值 |
| `_preopen_sse_shape` SSE dict | persisted events | record_alert_event 全量 event_json 快照 | ✓ real | 无静态返回; degraded/probe 冻结快照 round-trip 保真 (T17) |
| Monitor.tsx 徽标 | ev.provisional / ev.degraded | 后端事件增量键 | ✓ real | 非硬编码 — 事件键驱动; e2e mock 双态断言 |
| RuleEditor thresholdFields | options.preopen_threshold_fields | /options 端点 → PREOPEN_ALLOWED_FIELDS | ✓ real | 5 白名单字段 + ENRICHED_COLUMNS 标签; 缺键回退空数组 (兼容) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| 白名单校验正/负例 | `test_preopen_validate_whitelist_positive` / `test_preopen_validate_negative_cases` | 测试存在 (含 EOD 列/truth/非法 op/非数字 value 负例断言) | ✓ PASS (存在性; 通过证据见注*) |
| 盘中跳过回归锁 (D-03) | `test_evaluate_intraday_skips_preopen_rules` | 测试存在 (open_gap 规则盘中 0 事件) | ✓ PASS (存在性; 通过证据见注*) |
| 隔离不变量 (T7) | `test_evaluate_premarket_isolation_from_strategy_pools` | 测试存在 (三属性快照等值断言) | ✓ PASS (存在性; 通过证据见注*) |
| 降级 fail-closed (T9) | `test_preopen_degraded_fail_closed` | 测试存在 (auction 规则 0 命中 / open_gap 命中带 degraded) | ✓ PASS (存在性; 通过证据见注*) |
| 尾段接线 (T12) + 注册形 (T11) + 集成链 (T16) | `test_premarket_tail_hook_*` / `test_evaluate_premarket_alerts_persist_sse_webhook_chain` | 测试存在 (persist 后恰一次 / 同对象 / 落库→SSE→webhook) | ✓ PASS (存在性; 通过证据见注*) |
| round-trip 保真 (T17) | `test_alert_event_roundtrip_degraded_probe_frozen_snapshot` | 测试存在 (degraded/probe 冻结快照保真) | ✓ PASS (存在性; 通过证据见注*) |
| AST 守卫 (T19) | `test_preopen_eval_whole_file_isolated` 等 3 测试 | 测试存在 (整文件 + 函数段 + 存储隔离) | ✓ PASS (存在性; 通过证据见注*) |
| e2e 渲染/编辑 | `frontend/e2e/monitor.spec.ts` 5 用例 | spec 存在, 断言含白名单 label/无 truth/徽标/兼容 | ✓ PASS (存在性; 通过证据见注*) |

> **注***: 本验证 acceptance 明确「Do NOT run builds/tests」, 故本验证器未重跑测试; 通过证据来自 orchestrator 提供的已执行 spot-check 结果 (Phase 30 计划套件 16 + 回归 85 + 前端 build 全绿; 5 个 preopen 测试文件 30 项通过; monitor e2e 5/5 + premarket e2e 5/5)。此处为测试存在性枚举 (grep 验证), 行为通过性引用 orchestrator 实测。

### Probe Execution

无计划内/惯例 probe 脚本 (Phase 30 非迁移/工具链阶段; 计划 verify 命令均为 pytest/playwright 直调, 已在 Behavioral Spot-Checks 覆盖)。N/A。

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| MON-01 | 30-01 | preopen 类型 + 白名单 + op=truth 拒绝 + EOD 列禁用 + change_pct=None | ✓ SATISFIED | monitor_rules.py :22/:47-50/:148-159/:200-205; preopen_eval.py :64; T1/T2/T3 |
| MON-02 | 30-01 | evaluate_premarket 隔离评估 | ✓ SATISFIED | monitor.py :545-604 (三属性零触碰); T4/T5/T7/T8 |
| MON-03 | 30-02 | 09:26 尾段 + 持久化优先链 | ✓ SATISFIED | daily_pipeline.py :1064-1078; quote_service.py :1324-1372; T11-T16 |
| MON-04 | 30-01/30-02 | provisional/degraded/probe 标注 + fail-closed + round-trip | ✓ SATISFIED | monitor.py :590-598 + :283 (head(0)); quote_service.py :1366-1371; T6/T9/T10/T17 |
| MON-05 | 30-02 | 零执行 + AST 守卫 | ✓ SATISFIED | preopen_eval.py 铁律 docstring + 仅 stdlib/polars/PREOPEN_ALLOWED_FIELDS import; test_preopen_ast_guard.py T19 (3 测试) |
| MON-06 | 30-02 | guest 掩码 | ✓ SATISFIED | guest_masking.py :91-110 mask_guest_alert; T18 (快照 + 缺键容忍) |
| MON-07 (P2) | 30-02/30-03 | /options preopen 外露 + 前端编辑/渲染 | ✓ SATISFIED | monitor_rules.py :78-81/:112; api.ts :950/:986/:1033-1037; RuleEditor/Monitor.tsx; e2e 5 用例; features.md |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| 全部 11 个修改文件 + 5 个测试文件 | — | TBD/FIXME/XXX 债务标记 | — | 无 — 扫描零命中 |
| RuleEditor.tsx / Monitor.tsx | 249/302/351/95 | `placeholder=`/`placeholderData` (HTML 输入占位 + react-query) | ℹ️ Info | 非 stub — 输入框提示文案与 react-query 正常用法, 无空值流 |
| 空态返回 `[]` | monitor.py evaluate_premarket | 无 results/available:false → `[]` | ℹ️ Info | 设计使然 (诚实空态, 镜像 premarket_pool available:false 语义), 非 stub — 有可用数据时正常产生事件 |
| `mask_guest_alert` 无调用点 | guest_masking.py | 防御性 DTO 守卫 | ℹ️ Info | 设计使然 (30-02 明确记录; /api/alerts 为登录面; 未来 guest 可见 alerts 表面必须经此函数) |

### Human Verification Required

1. **交易日 09:26 实盘调度运行** — 观察 job 触发 (premarket_pool_preview), 预览落盘 `premarket_results/date={T}/part.json`, 尾段评估 preopen 规则, SSE 广播 + 飞书/Telegram 真实投递; available:false / degraded 路径诚实无告警且状态可查 (绝不静默)。
2. **真实后端用户流 (浏览器)** — 创建 preopen 规则 (类型下拉「盘前异动」→ 白名单字段 → 无信号条件 → open_gap 默认 → 保存), 查看告警列表「盘前·非最终」/「数据降级」徽标渲染; 旧 signal 事件零回归。
3. **设计裁决 (MON-06)** — 确认当前无游客可见 alerts 渲染面绕过 mask_guest_alert (防御性守卫接受)。

### Gaps Summary

无 gaps_found — 4/4 成功标准全部 VERIFIED, MON-01..07 全部 SATISFIED, 无债务标记, 无 stub, 无未接线链, Watchlist.tsx 零触碰。`human_needed` 状态由 3 项人工验证需求驱动 (真实调度/外部投递运行时行为 + 真实前后端联通用户流 + MON-06 防御性设计裁决), 均为自动化无法覆盖的实时/外部服务/视觉-交互层面; 代码层面证据完整。

---

_Verified: 2026-08-06T14:12:18Z_
_Verifier: Claude (gsd-verifier)_
