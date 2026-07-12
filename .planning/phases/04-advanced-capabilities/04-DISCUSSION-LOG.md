# Phase 4: Advanced Capabilities - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md; this log preserves the alternatives considered.

**Date:** 2026-07-12
**Phase:** 4-Advanced Capabilities
**Areas discussed:** 观点与绩效, 实验反馈闭环, 策略演化晋升, 代理授权范围

---

## 观点与绩效

| Question | Options considered | Selected |
|--------|-------------|----------|
| Auditable viewpoint unit | 不可变观点版本; 标的最新观点; 仅跟踪研究对象 | 不可变观点版本 |
| Material stance change | 结构化字段阈值; 任何新版本; 人工标记 | 结构化字段阈值 |
| Performance measurement | 固定观察窗+基准; 持续累计收益; 仅方向命中率 | 固定观察窗+基准 |
| Confidence-aware display | 分桶校准+样本量; 单一综合分; 只显示原始置信度 | 分桶校准+样本量 |
| Source attribution | 受控来源档案; 自由文本署名; 仅平台内部作者 | 受控来源档案 |
| Corrections | 追加更正版本; 直接覆盖; 删除并重录 | 追加更正版本 |
| Benchmark selection | 按资产类型预设，可显式覆盖; 统一宽基指数; 每次自由填写 | 按资产类型预设，可显式覆盖 |
| Missing evaluation inputs | 不可评估记录; 延后到可计算; 排除且不显示 | 不可评估记录 |

**User's choice:** Preserve versioned attribution and fixed, confidence-calibrated evidence rather than mutable snapshots or opaque aggregate scores.

---

## 实验反馈闭环

| Question | Options considered | Selected |
|--------|-------------|----------|
| Experiment specification | 运行前冻结版本; 运行中可编辑; 只保留自然语言 | 运行前冻结版本 |
| Inputs and environment | 受治理快照+运行清单; 只存参数; 保存完整数据副本 | 受治理快照+运行清单 |
| Feedback conclusion | 结构化结论+证据链接; 单一通过/失败; 自由文本笔记 | 结构化结论+证据链接 |
| Failed run retry | 保留失败并派生新运行; 自动静默重试; 删除失败记录 | 保留失败并派生新运行 |

**User's choice:** Preserve reproducible specifications, evidence-linked feedback, and append-only failure/retry history.

---

## 策略演化晋升

| Question | Options considered | Selected |
|--------|-------------|----------|
| Candidate origin | 受限变异并保留谱系; 任意新代码; 仅参数搜索 | 受限变异并保留谱系 |
| Promotion criteria | 显式多重闸门; 单一排名分; 人工自由判断 | 显式多重闸门 |
| Final approval | 研究者显式确认; 自动晋升; 双人审批 | 研究者显式确认 |
| Promoted state | 注册研究资产; 自动启用监控; 自动生成交易建议 | 注册研究资产 |

**User's choice:** Keep evolution constrained, auditable, and manually promoted into research use only.

---

## 代理授权范围

| Question | Options considered | Selected |
|--------|-------------|----------|
| Token granularity | 短期、作用域化令牌; 全权长期令牌; 只凭登录会话 | 短期、作用域化令牌 |
| Allowlist source | 服务端策略签发; 客户端请求声明; 只检查市场 | 服务端策略签发 |
| Rejected requests | 执行前拒绝并审计; 创建后取消; 静默忽略 | 执行前拒绝并审计 |
| Revocation semantics | 启动时重新授权; 创建即永久授权; 终止所有任务 | 启动时重新授权 |

**User's choice:** Enforce least-privilege authorization at the server before work starts and revalidate pending work when policy changes.

---

## the agent's Discretion

- Exact schemas, APIs, threshold values, benchmark catalog, idempotency/rate-limit accounting, SSE projections, custom-strategy contract, resource isolation, and diagnostic redaction remain for research and planning, subject to the locked safety and provenance decisions.

## Deferred Ideas

None.
