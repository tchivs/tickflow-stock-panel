---
phase: 30-premarket-monitor
plan: 3
subsystem: monitoring
tags: [preopen, rule-editor, alert-rendering, playwright-e2e, frontend, api-types]

# Dependency graph
requires:
  - "30-02 (/options 契约: types 含 preopen + preopen_threshold_fields 5 字段白名单; SSE 事件增量键 window/provisional/degraded/strategy_ids/preopen_metrics)"
provides:
  - "MON-07 前端类型契约: api.ts MonitorRule.type 含 'preopen' + MonitorRuleOptions.preopen_threshold_fields + AlertEvent 增量可选字段 (旧载荷零崩溃)"
  - "MON-07 规则编辑: RuleEditor preopen 类型编辑路径 (白名单字段下拉 / truth 隐藏 / open_gap 默认条件 / 保存校验沿用)"
  - "MON-07 告警渲染: Monitor.tsx TYPE_LABEL/SOURCE_BADGE_STYLE preopen 条目 + 「盘前·非最终」(provisional) / 「数据降级」(degraded) 徽标"
  - "e2e: frontend/e2e/monitor.spec.ts (5 用例: 编辑器路径 2 + 渲染 3), installShell 独立 mock"
  - "docs: features.md 监控中心小节 (五类监控 + 盘前监控表行 + preopen 特性 bullet)"
affects: [monitor-ui, features-docs]

actuals:
  tokens: 3598        # chars/4 over realized diff (14,390 added chars, 5 files)
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "增量兼容: 全部新键可选 (preopen_threshold_fields ?? 空数组 / ev.source === 'preopen' 条件包裹徽标) — 旧载荷/旧后端零崩溃"
    - "诚实渲染: preopen 事件 price/change_pct 恒 null → 既有 != null 条件天然不渲染价格/涨跌幅 chip"
    - "e2e 独立 spec: installShell 复制 premarket-pool.spec.ts (不跨文件 import), 后注册 route 优先覆盖"
    - "TDD: Task 1 test(RED) → feat(GREEN) 提交对; 类型门 (tsc) + Playwright e2e 双门禁"

key-files:
  created:
    - frontend/e2e/monitor.spec.ts
  modified:
    - frontend/src/lib/api.ts
    - frontend/src/components/monitor/RuleEditor.tsx
    - frontend/src/pages/Monitor.tsx
    - docs/features.md

key-decisions:
  - "thresholdFields 按类型切换 (preopen → preopen_threshold_fields ?? []), 而非合并两份字段表 — 配置期白名单隔离, 杜绝建出必失败的规则"
  - "preopen 隐藏 truth 信号点选仅为 UX (后端 validate 白名单为最终防线 — 双保险, T-30-03-02)"
  - "徽标区整体以 ev.source === 'preopen' 包裹, provisional/degraded 为可选字段 — 旧事件零渲染零崩溃 (T-30-03-04)"
  - "筛选下拉不加 preopen 项 (RESEARCH 范围外; source=preopen 事件在「全部」可见)"
  - "e2e 断言命中条件行与渲染器字形一致: 'open_gap>=0.05' 而非 '≥' (30-01 已记录的前端渲染器事实)"

requirements-completed: [MON-07]

coverage:
  - id: D1
    description: "api.ts 类型契约 — MonitorRule.type 联合含 'preopen'; MonitorRuleOptions.preopen_threshold_fields 可选数组; AlertEvent 增量可选 window/provisional/degraded/strategy_ids/preopen_metrics"
    requirement: MON-07
    verification:
      - kind: other
        ref: "cd frontend && npm run build (tsc -b 严格类型门)"
        status: pass
    human_judgment: false
  - id: D2
    description: "RuleEditor preopen 编辑路径 — 类型下拉出现「盘前异动」; 字段下拉仅 5 白名单 label; 无「信号条件」按钮/信号点选区; 阈值条件默认 open_gap; 保存载荷 type=preopen"
    requirement: MON-07
    verification:
      - kind: e2e
        ref: "frontend/e2e/monitor.spec.ts#MON-07: 规则编辑器 preopen 类型 — 白名单字段下拉 + 无 truth + open_gap 默认 + 保存载荷"
        status: pass
    human_judgment: false
  - id: D3
    description: "兼容 — 旧 /options 载荷 (无 preopen_threshold_fields) 选 preopen 零崩溃 (字段下拉空); signal 类型 truth 点选零回归"
    requirement: MON-07
    verification:
      - kind: e2e
        ref: "frontend/e2e/monitor.spec.ts#MON-07: 兼容 — 旧 /options 载荷 (无 preopen_threshold_fields) 零崩溃 + signal 路径 truth 回归"
        status: pass
    human_judgment: false
  - id: D4
    description: "Monitor.tsx preopen 告警渲染 — 「盘前·非最终」(provisional) + 「数据降级」(degraded) 徽标; price/change_pct null 无价格/涨跌幅 chip; 命中条件行 open_gap>=0.05"
    requirement: MON-07
    verification:
      - kind: e2e
        ref: "frontend/e2e/monitor.spec.ts#MON-07: preopen 告警渲染 — provisional/degraded 徽标 + 无价格/涨跌幅 chip"
        status: pass
    human_judgment: false
  - id: D5
    description: "非降级 preopen 事件 — 「数据降级」不出现, provisional「盘前·非最终」恒标注; signal 旧载荷 (无增量键) 渲染零回归"
    requirement: MON-07
    verification:
      - kind: e2e
        ref: "frontend/e2e/monitor.spec.ts#MON-07: preopen 非降级事件 — 「数据降级」不出现, provisional 恒标注; frontend/e2e/monitor.spec.ts#MON-07: 兼容 — signal 事件 (无增量键) 渲染零回归"
        status: pass
    human_judgment: false
  - id: D6
    description: "docs/features.md 监控中心小节 — 五类监控 + 盘前监控表行 + preopen 白名单/provisional·degraded/09:26 尾段互斥 bullet"
    requirement: MON-07
    verification: []
    human_judgment: true
    rationale: "文档内容正确性由人工阅读确认 (特性列表措辞与产品行为一致)"

# Metrics
duration: 36min
completed: 2026-08-06
status: complete
---

# Phase 30 Plan 3: MON-07 前端 (preopen 规则编辑 + 告警渲染 + e2e + docs) Summary

**api.ts preopen 类型契约 + RuleEditor「盘前异动」规则编辑路径 (5 字段白名单下拉 / truth 隐藏 / open_gap 默认) + Monitor.tsx provisional「盘前·非最终」/ degraded「数据降级」徽标, 配套 5 用例 Playwright e2e + docs; 零新依赖, Watchlist.tsx 零触碰**

## Performance

- **Duration:** 36 min
- **Started:** 2026-08-06T14:36:00Z
- **Completed:** 2026-08-06T15:12:00Z
- **Tasks:** 2 (tracer 垂直切片 → 告警渲染扩张)
- **Files modified:** 5 (1 created, 4 modified)
- **Test counts:** 5 e2e 计划内 (monitor.spec.ts, desktop 项目全绿) + 5 回归 (premarket-pool.spec.ts) + 10 skipped (mobile/host 项目按 DESKTOP_PROJECT 跳过, 与既有 spec 一致)

## Accomplishments

- **api.ts 类型契约 (MON-07 前端)**: `MonitorRule.type` 联合追加 `'preopen'` (tsc 严格类型门 — 保存载荷类型安全, T-30-03-01); `MonitorRuleOptions.preopen_threshold_fields?: { key; label }[]` (30-02 /options 5 字段白名单契约); `AlertEvent` 追加可选 `window/provisional/degraded/strategy_ids/preopen_metrics` (30-02 `_preopen_sse_shape` 增量键对齐, 旧载荷缺键零崩溃, T-30-03-04)。
- **RuleEditor preopen 编辑路径 (D-07)**: 类型下拉由 options.types 驱动自动出现「盘前异动」; `thresholdFields` 按类型切换 — preopen 用 `preopen_threshold_fields ?? []` (配置期白名单隔离, 禁 EOD 列); `addCond('threshold')` 默认字段 preopen 时 `open_gap` (否则保存必被后端白名单拒绝); preopen 时隐藏「信号条件」按钮与 SignalPicker 区 (op=truth 后端拒绝 — UX 双保险, T-30-03-02); 空态提示文案对齐; 保存校验零改动 (conditions 非空 + 数值 value 已覆盖)。
- **Monitor.tsx 告警渲染**: `TYPE_LABEL.preopen '盘前'` + `SOURCE_BADGE_STYLE.preopen` (cyan 色系视觉区分); AlertsList 非 strategy 分支源徽标之后追加徽标区 — `ev.source === 'preopen'` 时 `provisional` → 「盘前·非最终」、`degraded` → 「数据降级」(镜像 DELIVERY_LABEL chip 尺寸/样式约定); 徽标区整体包裹 `ev.source === 'preopen'` 条件 — 旧事件零渲染零崩溃; price/change_pct null → 既有 `!= null` 条件天然不渲染价格/涨跌幅 chip (诚实, T-30-03-04); 筛选下拉不加 preopen 项 (RESEARCH 范围外)。
- **e2e (monitor.spec.ts, 5 用例)**: installShell 独立复制 (不跨文件 import); 编辑器路径 — preopen 类型可选 → 5 白名单 label (开盘涨幅/竞价量/竞价金额/竞价量比/派生未匹配金额) → 无 truth → open_gap 默认 → POST 载荷 type/conditions 断言; 兼容 — 旧 /options 缺键零崩溃 + signal 路径回归; 渲染 — provisional/degraded 双徽标 + 无价格 chip + 非降级 + signal 旧载荷零回归。断言字形与前端渲染器一致 (`open_gap>=0.05` 非 `≥`; `RSI14<30` 经 cnSignal 映射)。
- **docs/features.md**: 监控中心小节 — 四类监控 → 五类监控 (类型表追加盘前监控行); 特性列表追加 3 条 bullet (白名单禁 EOD 列 / provisional·degraded 徽标 + 降级 fail-closed 0 告警 / 09:26 尾段与盘中互斥)。

## Task Commits

Each task was committed atomically (Task 1 TDD 门序列: test(RED) → feat(GREEN)):

1. **Task 1: preopen 类型契约 + 规则编辑器编辑路径 — api.ts + RuleEditor** — `da547f7` (test, RED) + `05294fc` (feat, GREEN)
2. **Task 2: preopen 告警渲染 — Monitor.tsx 徽标 + e2e 渲染用例 + docs** — `2b2f0a4` (feat, 单提交)

**Plan metadata:** `(final docs commit — 见下文)`

## Files Created/Modified

- `frontend/src/lib/api.ts` (modified) — MonitorRule.type + 'preopen'; MonitorRuleOptions.preopen_threshold_fields 可选数组; AlertEvent 增量可选 window/provisional/degraded/strategy_ids/preopen_metrics (30-02 SSE 键集对齐注释)。
- `frontend/src/components/monitor/RuleEditor.tsx` (modified) — TYPE_DEFAULT_NAME.preopen '盘前异动'; thresholdFields 按类型切换 (preopen → 白名单, 缺键回退空数组); addCond threshold 默认字段 open_gap; preopen 隐藏 truth 按钮 + SignalPicker 区; 空态提示文案条件化。
- `frontend/src/pages/Monitor.tsx` (modified) — TYPE_LABEL.preopen '盘前'; SOURCE_BADGE_STYLE.preopen cyan 色系; AlertsList source=preopen 时渲染「盘前·非最终」/「数据降级」徽标。
- `frontend/e2e/monitor.spec.ts` (created) — installShell 复制 premarket-pool.spec.ts + monitor-options 契约 mock + 5 用例 (编辑器 2 + 渲染 3)。
- `docs/features.md` (modified) — 监控中心小节: 五类监控 + 盘前监控表行 + 3 条 preopen 特性 bullet。

## Decisions Made

- thresholdFields 按类型切换而非合并白名单 — 配置期即隔离 EOD 字段, 与后端 PREOPEN_ALLOWED_FIELDS 单一权威对齐 (规则必建即必能保存)。
- preopen 隐藏 truth 仅为 UX 优化 — 后端 validate 白名单为最终防线 (双保险, T-30-03-02 disposition: mitigate 已落地)。
- 徽标全部可选字段 + `ev.source === 'preopen'` 包裹 — 旧后端/旧事件零崩溃 (T-30-03-04 mitigate 落地); e2e 兼容用例锁死。
- e2e 断言以实际渲染文本为准 (`>=` 非 `≥`; cnSignal 映射后字段名) — 与 30-01 SUMMARY 记录的前端渲染器字形事实一致, 避免误用后端消息格式。
- 筛选下拉不加 preopen 项 — RESEARCH §9.2 范围外; source=preopen 事件在「全部」可见。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test-side] e2e 选择器 CSS 点号转义缺失 (gap-1.5)**
- **Found during:** Task 1 GREEN 验证
- **Issue:** 计划未指定条件行选择器; 我写的 `div.flex.items-center.gap-1.5 select` 中 `.1.5` 被 CSS 解析为非法 token ("Unexpected token .5"), 两个用例在 toHaveValue/toHaveCount 阶段报解析错误 — 应用代码本身正确 (truth 按钮断言已通过)。
- **Fix:** 选择器转义为 `div.flex.items-center.gap-1\\.5 select`。
- **Files modified:** frontend/e2e/monitor.spec.ts
- **Verification:** 5/5 e2e 全绿。
- **Committed in:** 05294fc (Task 1 GREEN 提交内)

**2. [Rule 1 - Test-side] signal 兼容用例严格模式双匹配 (189.50)**
- **Found during:** Task 2 验证
- **Issue:** signal 事件 price=189.5 同时渲染于头部 price chip 与详情行「现价」(conditions 存在 → 详情行展示现价) — `getByText('189.50')` 严格模式报双元素违规。这是既有渲染行为 (非回归), 断言需放宽。
- **Fix:** 断言改为 `.first()` 可见 (任一渲染点即证明价格 chip 正常)。
- **Files modified:** frontend/e2e/monitor.spec.ts
- **Verification:** 5/5 e2e 全绿。
- **Committed in:** 2b2f0a4 (Task 2 提交内)

**3. [文档一致性, 非偏差] docs "四类监控" → "五类监控"**
- **说明:** 计划只要求类型表追加盘前监控行 + 特性 bullet; 小节引言 "一个页面管理**四类监控**" 与新增第五行矛盾, 顺带修正为五类 (同小节内一致性, 无范围蔓延)。

---

**Total deviations:** 2 auto-fixed (均 Rule 1 测试侧) + 1 文档一致性说明
**Impact on plan:** 生产实现 (api.ts / RuleEditor.tsx / Monitor.tsx) 与计划 action 逐项一致, 零范围蔓延; 偏差全部位于 e2e 测试自身选择器/断言, 无生产代码偏差。

### TDD 门说明

- Task 1 有 test(RED)→feat(GREEN) 提交对 (da547f7 → 05294fc); RED 阶段 2 编辑器用例真失败 (truth 按钮 count=1 ≠ 0), GREEN 后全绿。Task 2 为 type="auto" 单提交 (无 tdd 标记), 按计划执行。
- 门序列检查: 存在 test(...) 后跟 feat(...) 提交, 无缺失门。

## Issues Encountered

- Playwright CSS 类选择器含 `gap-1.5` 需转义点号 (见 Deviation 1) — 已修复。
- `npm run build` 产出 chunk 体积警告 (index >500kB) 为既有状态, 与本次改动无关, 未触碰。
- 无阻塞问题; 无 auth 门; 无 package 安装 (零新增依赖, T-30-03-SC 不适用)。

## Known Stubs

None — 无占位/空值流。preopen 事件无价格/涨跌幅 chip 属**设计使然** (price/change_pct 恒 null 诚实不渲染, RESEARCH §6 诚实语义), 非 stub。

## Threat Surface

- 本计划零新增网络端点/鉴权路径/文件访问模式/信任边界 schema 变更 (纯前端类型 + 渲染 + 测试 + 文档)。
- T-30-03-01 (类型联合缺 preopen) / T-30-03-02 (truth 可用) / T-30-03-04 (旧载荷崩溃) 全部 mitigate 落地并经 e2e/tsc 验证; T-30-03-03 (guest 竞价值) accept 保持 (登录面 + 服务端 DTO 掩码边界); T-30-03-SC accept (零新增依赖)。
- 无 Threat Flags 需要上报。

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- MON-07 前端已交付: 类型契约 (api.ts) + 编辑器路径 (RuleEditor) + 告警渲染 (Monitor.tsx) + e2e + docs — Phase 30 全部计划 (30-01/02/03) 完成, 里程碑 v2.2「盘前预览进入监控告警」目标达成。
- `Watchlist.tsx` 工作区存在用户未提交改动 (执行前即存在, 未纳入任何提交, git status 验证零触碰) — 用户侧待处理, 与 30-03 无关。
- 30-01 ISSUES 记录的字形事实 (前端渲染 `>=` 非 `≥`) 已被本计划 e2e 断言消费并固化。

---
*Phase: 30-premarket-monitor*
*Completed: 2026-08-06*
## Self-Check: PASSED
- Files verified: 30-03-SUMMARY.md / monitor.spec.ts / api.ts / RuleEditor.tsx / Monitor.tsx / features.md 全部存在
- Commits verified: da547f7 (RED), 05294fc (GREEN), 2b2f0a4 (Task 2) 全部存在
- Watchlist.tsx 零触碰: 工作区改动为执行前用户未提交状态, 未纳入任何提交
