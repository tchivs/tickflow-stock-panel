# Requirements: AthenaQuant v3.1 可信工作台与运维闭环

**Defined:** 2026-08-18
**Core Value:** An investor can turn reliable market data and their own holdings into an auditable, actionable research and monitoring workflow without operating multiple disconnected tools.

## Milestone Scope

v3.1 以打磨现有功能为主: 补齐「用户能否看懂、验证、操作」的闭环。范围定义来自 `.planning/v3.1-milestone-spec.md`(用户已确认)。

Locked boundaries:

- 不引入新的模型执行权威: 工具审计只记录与展示, 不改变确定性代码对候选生成/评估/门禁/晋级的所有权
- ToolCallEnvelope 只追加事实(tool/params/version/scope/response_shape/raw_hash/duration/error), 审计内容脱敏后才可离开后端
- Provider Doctor 与数据质量 API 只读; 不新增自动修复动作
- 监控 test-fire 是 synthetic 投递, 不触达真实通知渠道预算以外的副作用
- 暂缓: 多市场扩张、新一轮因子/RL 搜索、Moderator 多 Agent 会议室、大规模实时架构、自动实盘交易

## v1 Requirements

### 发布基线收口 (Phase 51)

- [x] **BASE-01**: 用户打开任一规划文档(STATE/PROJECT/ROADMAP/REQUIREMENTS)看到的都是同一里程碑的同一状态, 无互相矛盾
- [x] **BASE-02**: 开发者运行一次命令即可执行 Vitest 前端单测套件, 且它在 CI/本地检查流程中被默认纳入
- [x] **BASE-03**: 开发者可在部署环境执行真实 LLM、Provider 降级与 SSE 重连三项冒烟脚本并得到通过/失败结论
- [x] **BASE-04**: 用户可在文档中查阅 v3.0 技债清单(Tier-2 stress matrix、成本近似等)及每项的处理或明确关闭结论

### 全局可信度与工具审计 (Phase 52)

- [ ] **AUDIT-01**: 开发者通过统一 ToolCallEnvelope 结构(tool/params/version/scope/response_shape/raw_hash/duration/error)记录 Provider、AI、通知与外部工具调用
- [ ] **AUDIT-02**: 用户可在统一审计页面按来源/日期/缓存/降级/schema/失败原因筛选查看全部工具调用
- [ ] **AUDIT-03**: 用户可对任一 Provider 执行 Doctor 诊断并看到分级结论(健康/降级/不可用)与建议动作
- [ ] **AUDIT-04**: 用户可通过统一数据质量 API 拉取各数据源新鲜度与缺陷摘要, 前端据此渲染质量告警
- [ ] **AUDIT-05**: 审计展示内容经过脱敏, 不暴露密钥、完整报文或个人数据

### 今日工作台与统一待办 (Phase 53)

- [ ] **WORK-01**: 用户在首页一屏看到数据新鲜度与 Provider 健康总览
- [ ] **WORK-02**: 用户在首页看到运行中/失败任务及失败原因
- [ ] **WORK-03**: 用户在首页看到最近报告与研究产物入口
- [ ] **WORK-04**: 用户在首页看到最近监控触发记录
- [ ] **WORK-05**: 用户在统一「待确认」收件箱处理生命周期、论点、因子晋升、纸面调仓四类待办, 每项有明确下一步入口
- [ ] **WORK-06**: 数据质量告警不再只出现在 Alpha 工作台, 首页与相关页面共享同一 Banner 数据源

### 监控与报告闭环 (Phase 54)

- [ ] **MON-01**: 用户可对任一监控规则执行 synthetic test-fire 并看到与真实触发一致的通知预览
- [ ] **MON-02**: 用户可查看每个监控的预算消耗、冷却剩余时间与通知渠道健康状态
- [ ] **MON-03**: 用户可预览 digest 汇总内容后再启用定期投递
- [ ] **MON-04**: 每份报告带数据质量 Banner、证据卡与引用回链, 读者可从结论跳转到原始证据
- [ ] **MON-05**: 报告可展示多空冲突观点与失败路径(哪些数据/步骤不可用), 不隐藏坏消息
- [ ] **MON-06**: 运行页统一展示 Timeline、参数、工具调用、产物, 失败可重试, SSE 断连可恢复

## v2 Requirements

### Moderator 研究会议室 (下一功能型里程碑候选)

- **MODR-01**: 多 Agent 会议室以 Moderator 主持的研究讨论形式接入, 复用 v3.1 的工具审计与证据回链

## Out of Scope

| Feature | Reason |
|---------|--------|
| 多市场全面扩张 | v3.0 结论: 继续加市场只会扩大维护面 |
| 新一轮因子/RL 搜索 | Alpha158 与挖掘引擎刚收口, 先消化 |
| 完整 Moderator 多 Agent 会议室 | 推迟到 v3.2, 依赖 v3.1 审计与证据链 |
| 大规模实时架构 | 单人自托管场景收益不成比例 |
| 自动实盘交易/券商连接 | 平台边界, 永久排除 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BASE-01 | Phase 51 | Complete |
| BASE-02 | Phase 51 | Complete |
| BASE-03 | Phase 51 | Complete |
| BASE-04 | Phase 51 | Complete |
| AUDIT-01 | Phase 52 | Pending |
| AUDIT-02 | Phase 52 | Pending |
| AUDIT-03 | Phase 52 | Pending |
| AUDIT-04 | Phase 52 | Pending |
| AUDIT-05 | Phase 52 | Pending |
| WORK-01 | Phase 53 | Pending |
| WORK-02 | Phase 53 | Pending |
| WORK-03 | Phase 53 | Pending |
| WORK-04 | Phase 53 | Pending |
| WORK-05 | Phase 53 | Pending |
| WORK-06 | Phase 53 | Pending |
| MON-01 | Phase 54 | Pending |
| MON-02 | Phase 54 | Pending |
| MON-03 | Phase 54 | Pending |
| MON-04 | Phase 54 | Pending |
| MON-05 | Phase 54 | Pending |
| MON-06 | Phase 54 | Pending |

**Coverage:**
- v1 requirements: 21 total
- Mapped to phases: 21
- Unmapped: 0 ✓

---
*Requirements defined: 2026-08-18*
*Last updated: 2026-08-18 — traceability confirmed against v3.1 ROADMAP.md (Phase 51-54)*
