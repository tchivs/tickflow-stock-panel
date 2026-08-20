# Roadmap: AthenaQuant v3.1

**Milestone:** v3.1 可信工作台与运维闭环
**Goal:** 以打磨现有功能为主, 补齐「用户能否看懂、验证、操作」的闭环 — 统一工具调用审计与数据质量可见性、首页今日工作台与统一待办、监控与报告闭环; 暂不扩展新的大型量化能力。
**Phase numbering:** Continues from completed v3.0 Phase 50 (`phase_naming: sequential`).
**Granularity:** Standard (four dependency-ordered delivery boundaries, 21/21 requirements mapped).

## Locked Boundaries

- 不引入新的模型执行权威: 工具审计只记录与展示, 不改变确定性代码对候选生成/评估/门禁/晋级的所有权。
- ToolCallEnvelope 只追加事实(tool/params/version/scope/response_shape/raw_hash/duration/error), 审计内容脱敏后才可离开后端。
- Provider Doctor 与数据质量 API 只读; 不新增自动修复动作。
- 监控 test-fire 是 synthetic 投递, 不触达真实通知渠道预算以外的副作用。
- 暂缓: 多市场扩张、新一轮因子/RL 搜索、Moderator 多 Agent 会议室(v3.2)、大规模实时架构、自动实盘交易。

## Milestone Acceptance Chain

端到端验收主链路(`.planning/v3.1-milestone-spec.md` 权威), 每一环由对应 phase 交付:

| # | 链路环节 | 交付 phase | 支撑需求 |
|---|---------|-----------|---------|
| 1 | Provider 降级可诊断、可见 | Phase 52 | AUDIT-03, AUDIT-04 |
| 2 | 首页显示质量告警 | Phase 53 | WORK-01, WORK-06 |
| 3 | 启动研究任务(首页入口) | Phase 53 | WORK-02 |
| 4 | SSE 查看运行过程 | Phase 54 | MON-06 |
| 5 | 查看工具调用和 raw hash | Phase 52 | AUDIT-01, AUDIT-02 |
| 6 | 报告回链证据 | Phase 54 | MON-04 |
| 7 | 产生待确认事项 | Phase 53 | WORK-05 |
| 8 | 人工审批 | Phase 53 | WORK-05 |
| 9 | 创建监控并 test-fire | Phase 54 | MON-01 |
| 10 | 查看通知投递结果 | Phase 54 | MON-02 |

里程碑验收 = Phase 51-54 全部成功标准通过后, 上述链路在单一部署上可连续走通。

## Phases

- [x] **Phase 51: 发布基线收口** - 统一 STATE/PROJECT/ROADMAP/REQUIREMENTS 状态, 执行并纳入 Vitest, 补真实 LLM/Provider 降级/SSE 重连部署冒烟, 处理或明确关闭 v3.0 技债。
- [x] **Phase 52: 全局可信度与工具审计** - Provider/AI/通知/外部工具统一 ToolCallEnvelope, 统一 Provider Doctor 与数据质量 API, 审计脱敏与前端来源/日期/缓存/降级/schema/失败原因展示。
- [x] **Phase 53: 今日工作台与统一待办** - 首页集中展示数据新鲜度、Provider 健康、运行中/失败任务、最近报告与产物、监控触发、统一待确认收件箱, 每项有明确下一步入口。
- [ ] **Phase 54: 监控与报告闭环** - synthetic test-fire、预算、冷却剩余、渠道健康与 digest 预览; 报告统一数据质量 Banner、证据卡、引用回链、多空冲突与失败路径; 运行页统一 Timeline、参数、工具调用、产物、失败重试与 SSE 恢复。

## Phase Details

### Phase 51: 发布基线收口

**Goal**: 里程碑在可信基线上开工 — 规划文档与真实进度一致, 前端单测默认执行, 三项部署冒烟可运行并给出结论, v3.0 每项技债有处理或明确关闭结论。

**Depends on**: Phase 50 (v3.0, completed 2026-08-09); first v3.1 phase, no v3.1 dependency.

**Requirements**: BASE-01, BASE-02, BASE-03, BASE-04

**Success Criteria** (what must be TRUE):

1. 用户打开 STATE.md、PROJECT.md、ROADMAP.md、REQUIREMENTS.md 中任一文档, 看到的都是 v3.1 同一里程碑、同一阶段的同一状态; 「STATE 写 v3.0 完成但 Phase 50 未开始」「PROJECT 写正在建设 v3.0」这类互相矛盾不再存在。
2. 开发者运行一条命令即可执行 Vitest 前端单测套件并得到通过/失败汇总; vitest 成为前端依赖, 且该套件在本地/CI 检查流程中被默认纳入(v3.0 已写好未执行的 unit suites 默认执行)。
3. 开发者可在部署环境分别执行真实 LLM(两阶段分析)、Provider 降级、SSE 重连三个冒烟脚本, 每个脚本输出明确的通过/失败结论 — 不静默跳过, 不伪造通过。
4. 用户可在文档中查阅 v3.0 技债清单(Tier-2 stress matrix 422、成本 turnover×rate 近似、Stage 1 partial labeling、部署后真实 LLM 验证)及每项「已处理 / 明确关闭(含理由)」结论。

**Research flag**: **No dedicated research phase** — 状态收口是文档工作; Vitest/冒烟脚本按既有 e2e 与部署模式落地。

**Explicit non-goals**: 不修复与基线无关的业务缺陷, 不新增产品功能, 不做性能优化。

**Plans**: TBD

### Phase 52: 全局可信度与工具审计

**Goal**: Provider、AI、通知与外部工具的每次调用都留下统一、脱敏、可查询的 ToolCallEnvelope 审计事实; 统一 Provider Doctor 与数据质量 API 让降级、新鲜度与缺陷对用户可见。

**Depends on**: Phase 51 (统一基线与默认 Vitest 为审计页面前端提供测试保障; 部署冒烟为 Provider 降级验证提供手段)。

**Requirements**: AUDIT-01, AUDIT-02, AUDIT-03, AUDIT-04, AUDIT-05

**Success Criteria** (what must be TRUE):

1. Provider、AI、通知与外部工具的每次调用都追加一条统一 ToolCallEnvelope 记录(tool/params/version/scope/response_shape/raw_hash/duration/error), 开发者可按 principal/scope 查询; 审计只追加事实, 不改变确定性代码对生成/评估/门禁/晋级的所有权。
2. 用户在统一审计页面查看全部工具调用, 可按来源、日期、缓存、降级、schema、失败原因筛选定位任一次调用。
3. 用户可对任一 Provider 执行 Doctor 诊断, 看到健康/降级/不可用分级结论与建议动作; 诊断只读, 无自动修复副作用。
4. 用户可通过统一数据质量 API 拉取各数据源新鲜度与缺陷摘要, 前端据此渲染质量告警 — 该 API 是 Phase 53 首页与各页面共享 Banner 的数据源。
5. 审计对外展示经过脱敏: 密钥、完整报文与个人数据不出后端, 页面/API 只能看到 raw_hash 与脱敏摘要。

**Research flag**: **Yes** — settle ToolCallEnvelope 存储形态(复用 append-only SQLite 事实表模式)、Provider/AI/通知/外部工具四类调用方的接入 seam、脱敏白名单与 raw 仅存 hash 的保留策略, 再动手实现。

**Explicit non-goals**: 不建第二套审计语义或调用重放系统, 不改变 Provider 调用行为本身, 不做自动修复。

**Plans**: TBD
**UI hint**: yes

### Phase 53: 今日工作台与统一待办

**Goal**: 首页成为「今天什么状态、什么信号、什么任务、什么风险、下一步点哪里」的唯一入口 — 数据健康、任务、报告、监控、待确认事项一屏可见, 每项有明确下一步。

**Depends on**: Phase 52 (首页健康总览与质量 Banner 消费统一数据质量 API 与 Doctor; 失败原因消费 ToolCallEnvelope)。

**Requirements**: WORK-01, WORK-02, WORK-03, WORK-04, WORK-05, WORK-06

**Success Criteria** (what must be TRUE):

1. 用户在首页一屏看到数据新鲜度与 Provider 健康总览; 质量告警 Banner 与 Alpha 工作台等页面共享同一数据源 — Provider 降级时首页出现质量告警, 不再只在 Alpha 工作台可见。
2. 用户在首页看到运行中与失败任务及失败原因, 每项可跳转到对应运行页(验收链路第 3 环入口)。
3. 用户在首页看到最近报告与研究产物入口, 每项可跳转到报告/产物详情。
4. 用户在首页看到最近监控触发记录, 可跳转到监控详情。
5. 用户在统一「待确认」收件箱看到生命周期、论点、因子晋升、纸面调仓四类待办, 每项有明确下一步入口直达审批/处理动作(验收链路第 7-8 环)。

**Research flag**: **No dedicated research phase** — 复用既有首页/React Query 模式与 Phase 52 数据质量 API; 计划期需核对四类待办的既有后端来源与聚合边界。

**Explicit non-goals**: 不改变各待办的审批语义与权限; 首页只读聚合, 不新增执行动作; 不做个性化/可配置仪表盘。

**Plans**: TBD
**UI hint**: yes

### Phase 54: 监控与报告闭环

**Goal**: 监控可验证(test-fire/预算/冷却/渠道健康/digest 预览)、报告可信(质量 Banner/证据卡/引用回链/冲突与失败路径)、运行页完整(Timeline/参数/工具调用/产物/重试/SSE 恢复) — 验收主链路端到端闭合。

**Depends on**: Phase 53 (首页已聚合监控触发与待办入口) and Phase 52 (工具调用与 raw hash 可查, 供报告回链与运行页展示)。

**Requirements**: MON-01, MON-02, MON-03, MON-04, MON-05, MON-06

**Success Criteria** (what must be TRUE):

1. 用户可对任一监控规则执行 synthetic test-fire 并看到与真实触发一致的通知预览; test-fire 是 synthetic 投递, 不触达真实通知渠道预算以外的副作用。
2. 用户可查看每个监控的预算消耗、冷却剩余时间与通知渠道健康状态; 可先预览 digest 汇总内容再启用定期投递。
3. 每份报告带数据质量 Banner、证据卡与引用回链, 读者可从任一结论跳转到原始证据(含工具调用 raw hash 与产物)。
4. 报告可展示多空冲突观点与失败路径(哪些数据/步骤不可用), 不隐藏坏消息。
5. 运行页统一展示 Timeline、参数、工具调用与产物; 失败任务可重试; SSE 断连重连后从断点恢复, 不丢失也不发明事件。

**Research flag**: **Yes** — settle test-fire 与真实通知链路的隔离边界(渠道预算/冷却是否共享)、报告证据卡的统一数据契约、运行页 SSE 恢复复用 Phase 45/50 durable Last-Event-ID 模式的适用范围。

**Explicit non-goals**: 不新增通知渠道, 不做实时推送架构, 不改变监控规则评估语义。

**Plans**: TBD
**UI hint**: yes

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 51. 发布基线收口 | 4/4 | Complete | 2026-08-19 |
| 52. 全局可信度与工具审计 | 5/5 | Complete | 2026-08-19 |
| 53. 今日工作台与统一待办 | 6/6 | Complete | 2026-08-20 |
| 54. 监控与报告闭环 | 0/TBD | Not started | - |

**Execution order:** 51 → 52 → 53 → 54. Each phase consumes its predecessors' unified audit/quality/inbox contracts; no phase gains execution or repair authority.

## Requirement Coverage

21/21 v1 requirements mapped, no orphans, no duplicates: BASE-01..04 → Phase 51; AUDIT-01..05 → Phase 52; WORK-01..06 → Phase 53; MON-01..06 → Phase 54. Per-requirement traceability lives in `.planning/REQUIREMENTS.md`.

---
*Last updated: 2026-08-20 — Phase 51-53 complete (BASE-01..04, AUDIT-01..05, WORK-01..06); Phase 54 next.*
