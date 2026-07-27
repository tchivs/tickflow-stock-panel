---
phase: 03-ai-analysis
verified: 2026-07-12T06:04:45Z
status: passed
score: 4/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
completion_marker: phase_goal_achieved
re_verification:
  previous_status: gaps_found
  previous_score: 0/3
  gaps_closed:
    - "生产 AnalysisService 已加载受治理证据并在认证真实主机内完成运行。"
    - "报告、证据和生命周期端点已返回授权展示 DTO。"
    - "报告 signal_id 使 UI 可到达审阅、计划和结果历史。"
    - "图验证已改为生产使用的 AsyncSqliteSaver 异步路径。"
  gaps_remaining: []
  regressions: []
---

# Phase 3: AI Analysis Verification Report

**Phase Goal:** Investors can consume AI-assisted research that makes quality, reasoning, and signal validity visible rather than opaque.
**Verified:** 2026-07-12T06:04:45Z
**Status:** passed
**Re-verification:** Yes - after gap closure 03-10, 03-11, and 03-12
**Completion Marker:** `phase_goal_achieved`

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | 用户可审阅带 A/B/C 来源质量及 material number 已核验/冲突/未解决状态的市场或组合分析。 | VERIFIED | [main.py](/root/source/AthenaQuant/backend/app/main.py:87) 注入 [GovernedEvidenceLoader](/root/source/AthenaQuant/backend/app/analysis/evidence_loader.py:45)。其仅从 Kline、财务 Parquet 和 operational holdings 构造记录；真实认证宿主测试完成 run 并返回顶层 `sources`/`material_numbers`。 |
| 2 | 用户可检查多视角报告、可见评分理由、适用估值与 IC 备忘录。 | VERIFIED | [api.py](/root/source/AthenaQuant/backend/app/analysis/api.py:162) 经 [projections.py](/root/source/AthenaQuant/backend/app/analysis/projections.py:21) 返回 allowlist DTO；[ReportPanel.tsx](/root/source/AthenaQuant/frontend/src/components/analysis/ReportPanel.tsx:13) 安全处理 optional limitations。真实 DTO 测试和浏览器报告场景通过。 |
| 3 | 用户可查看信号当前状态，以及生命周期演化或结果。 | VERIFIED | [api.py](/root/source/AthenaQuant/backend/app/analysis/api.py:180) 聚合 events、reviews、plans、outcomes；[AnalysisWorkspace.tsx](/root/source/AthenaQuant/frontend/src/components/analysis/AnalysisWorkspace.tsx:27) 使用服务器 `signal_id` 查询历史。真实宿主测试完成 confirm、plan、outcome 后可重读。 |
| 4 | 锁定依赖可运行生产使用的最小 SQLite 固定图检查。 | VERIFIED | `uv lock --check` 成功；`test_analysis_graph_executes_the_fixed_nodes_with_async_sqlite_checkpoints` 通过，生产图使用 `AsyncSqliteSaver`。 |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `backend/app/analysis/evidence_loader.py` | 只读受治理 market/financial/account 证据适配器 | VERIFIED | 仅读取已治理 repository、财务 loader 和 operational positions；空上下文受控失败。 |
| `backend/app/main.py` | 生产 evidence loader 装配 | VERIFIED | lifespan 构造 graph、repository、lifecycle service 和 loader 后注入 `AnalysisService`。 |
| `backend/app/analysis/projections.py` | immutable records 到展示 DTO 的唯一映射器 | VERIFIED | 显式 allowlist 报告、证据、生命周期字段；排除 raw report/snapshot、prompt 和 reviewer principal。 |
| `backend/app/analysis/api.py` | 授权报告、证据与生命周期资源 | VERIFIED | 每个 opaque ID 先解析持久化 subject 并授权；详情发放 `signal_id`，history 聚合 review、plan、outcome。 |
| `frontend/src/lib/api.ts` 与 `components/analysis/*.tsx` | 对齐的类型客户端与工作区 | VERIFIED | 端点、字段与 projection 对齐；workspace 被 Stock 与 Portfolio 页面实际引用。 |
| `frontend/e2e/phase3-ai-analysis.spec.ts` | 对齐 DTO 的浏览器回归 | VERIFIED | 三个 stock/portfolio/响应式场景通过，fixture 仅使用当前 display DTO，未处理 API 请求失败。 |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| `main.py` | `GovernedEvidenceLoader` | lifespan 注入 `AnalysisService` | WIRED | [service.py](/root/source/AthenaQuant/backend/app/analysis/service.py:85) 冻结 loader 返回的记录，执行 graph 并持久化 completed run/report。 |
| `POST /api/analysis/runs` | `operational.db` | 认证请求、冻结、AsyncSqliteSaver 图、持久化 | WIRED | 真实 `TestClient(app)` 测试验证 `401`、登录后 `completed` 与可读 artifacts。 |
| `analysis/api.py` | `frontend/src/lib/api.ts` | 单一 report/evidence/history DTO | WIRED | 后端命名测试逐字段断言 response；前端调用相同 URL 和包裹形状。 |
| `AnalysisWorkspace.tsx` | `LifecyclePanel.tsx` | report-issued `signal_id` history query | WIRED | [AnalysisWorkspace.tsx](/root/source/AthenaQuant/frontend/src/components/analysis/AnalysisWorkspace.tsx:28) 在 signal 存在时查询并传递返回值。 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| --- | --- | --- | --- | --- |
| `AnalysisService` | frozen evidence | governed loader -> evidence preparer -> repository | 是 | FLOWING |
| report/evidence panels | report、sources、material_numbers | authenticated `/api/analysis/reports/*` -> projections | 是 | FLOWING |
| lifecycle panel | signal_id、reviews、plans、outcomes | report detail -> scoped history resource | 是 | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| 真实认证主机闭环 | `uv run pytest tests/test_analysis_host_integration.py::test_authenticated_main_host_completes_governed_analysis_and_persists_immutable_artifacts -q` | `1 passed`；401、登录、completed run、report/evidence、signal、confirm、60 日 plan 和 outcome。 | PASS |
| allowlist DTO 与生命周期投影 | `uv run pytest tests/test_analysis_api.py::test_analysis_api_returns_allowlisted_report_evidence_and_lifecycle_display_dtos -q` | `1 passed`；断言推理/评分/估值/memo、顶层 evidence/history，无 raw JSON 或 reviewer principal。 | PASS |
| 配置失败和异步图 | `uv run pytest tests/test_analysis_service.py::test_analysis_service_records_terminal_failure_when_new_run_lacks_execution_collaborator tests/test_analysis_graph.py::test_analysis_graph_executes_the_fixed_nodes_with_async_sqlite_checkpoints -q` | `4 passed`。 | PASS |
| 受治理输入、状态门槛、subject 授权 | `uv run pytest tests/test_analysis_evidence.py::test_governed_evidence_loader_uses_only_repository_financial_and_operational_boundaries tests/test_analysis_lifecycle.py::test_lifecycle_rules_require_independent_contradiction_and_price_event_context tests/test_analysis_api.py::test_analysis_api_authorizes_subject_before_start_reads_and_review_writes -q` | `3 passed`。 | PASS |
| 前端编译与浏览器合同 | `pnpm run build && pnpm exec playwright test e2e/phase3-ai-analysis.spec.ts --project=desktop-chromium` | build 成功；3 个 Playwright 场景通过。 | PASS |

### Requirements Coverage

| Requirement | Status | Evidence |
| --- | --- | --- |
| ANLY-01 | SATISFIED | 生产 loader、冻结/投影、真实 host 和 EvidencePanel 链路均有代码与聚焦测试。 |
| ANLY-02 | SATISFIED | 固定图、server DTO、ReportPanel 与真实 DTO/浏览器测试。 |
| ANLY-03 | SATISFIED | completed report 可发放 signal，认证 history 返回 review/plan/outcome；真实 host 确认及结果追加后可重读。 |

未发现映射到 Phase 3 但未被计划声明的孤立需求；Phase 4/5 未承担任何本阶段缺口，故无 deferred 项。

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- |
| `backend/app/analysis/service.py` | 69 | 缺少协作者时受控 terminal failure | Info | 前次“伪 queued”阻塞项已修复，命名测试确认新 run 为 `failed`。 |
| `frontend/e2e/phase3-ai-analysis.spec.ts` | 64 | DTO fixture | Info | 浏览器不调用 live backend；真实 FastAPI host 和逐字段 DTO 测试独立覆盖接口契约，未构成断链。 |

### Re-verification Conclusion

前次四个阻塞项均已关闭。认证请求从受治理边界冻结证据，执行固定异步图，持久化报告，并经授权 DTO 到达对象工作区和生命周期数据。没有 blocker、warning 或待人工确认项。

---

_Verified: 2026-07-12T06:04:45Z_
_Verifier: the agent (gsd-verifier)_
