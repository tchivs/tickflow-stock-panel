---
phase: 04-advanced-capabilities
verified: 2026-07-12T00:00:00Z
status: gaps_found
score: 0/4 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "用户可审阅归因市场观点、材料立场变化和置信度感知的表现结果。"
    status: failed
    reason: "服务层可记录评价，但生产 API/UI 路径既不调用评价，也不从 SQLite 读取/投影评价结果。"
    artifacts:
      - path: backend/app/advanced/repository.py
        issue: "viewpoint_versions() 只读取版本与证据，未关联 advanced_viewpoint_evaluations。"
      - path: frontend/src/components/advanced/ViewpointPanel.tsx
        issue: "只能渲染 API 已提供的 evaluation；真实响应会是 null。"
    missing:
      - "将受治理的冻结评价连接到生产服务并把最新不可变评价投影到授权 API/UI。"
  - truth: "研究员可完成沙箱实验、记录反馈，并通过显式门禁评估演化策略晋级。"
    status: failed
    reason: "生产生命周期把 ExperimentService 连接到明确抛出 RuntimeError 的 _UnavailableAdvancedRunner；运行端点不能完成真实受限实验。"
    artifacts:
      - path: backend/app/main.py
        issue: "_UnavailableAdvancedRunner.run() 始终抛异常，且被注入 ExperimentService。"
    missing:
      - "接入受治理、受资源限制的真实实验运行适配器，并将完成/失败记录、反馈及候选门禁接至生产 API。"
  - truth: "运营者可启动已授权 agent job、查看 SSE 进度和审计；拒绝请求在工作前停止。"
    status: failed
    reason: "会话启动路由仅持久化 queued job；生产 provider 是 no-op，未装配 workflow，且不存在生产调用 notify_advanced_progress 的路径。"
    artifacts:
      - path: backend/app/main.py
        issue: "AdvancedJobService 注入 provider=lambda **_kwargs: None；没有 advanced workflow 实例。"
      - path: backend/app/services/quote_service.py
        issue: "notify_advanced_progress() 只有定义和测试调用，没有生产发布者。"
    missing:
      - "将授权后作业接入执行前复核、固定 workflow、持久化阶段迁移、审计和提交后 SSE 发布。"
  - truth: "研究员仅在合同、AST、导入、超时和内存约束通过后运行自定义策略，并审阅受限运行结果或失败记录。"
    status: failed
    reason: "默认 launcher 始终无法证明隔离；沙箱没有成功 terminal run 路径，任何提交只产生 rejected validation，不能审阅实际受限运行结果。"
    artifacts:
      - path: backend/app/advanced/sandbox.py
        issue: "_UnavailableLauncher 的所有能力字段为 false；submit() 在成功 spawn 后仍将 outcome 映射为 rejection，且未写 advanced_sandbox_runs。"
    missing:
      - "提供经能力探针验证的隔离 launcher、资源终止实现和成功/失败 run 记录投影；在不可证明时继续 fail-closed。"
---

# Phase 4: Advanced Capabilities Verification Report

**Phase Goal:** Researchers and operators can use advanced research and automation workflows within explicit promotion, authorization, audit, and execution safeguards.
**Verified:** 2026-07-12T00:00:00Z
**Status:** gaps_found
**Re-verification:** No - initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | 用户可审阅归因观点、材料立场变化及置信度感知的表现结果。 | ✗ FAILED | 不可变版本与结构化变化服务存在，但 [repository.py](/root/source/AthenaQuant/backend/app/advanced/repository.py:327) 的版本读取未加载评价，且 [api.py](/root/source/AthenaQuant/backend/app/advanced/api.py:208) 没有触发/读取评价。UI 只能显示 `evaluation: null` 的“等待服务端评估”。 |
| 2 | 研究员可从假设完成沙箱实验、记录反馈，并以显式门禁评估演化策略晋级。 | ✗ FAILED | [main.py](/root/source/AthenaQuant/backend/app/main.py:36) 的运行器始终抛出 `RuntimeError`，并在 [main.py](/root/source/AthenaQuant/backend/app/main.py:155) 注入生产 ExperimentService；`POST /runs` 无可完成的生产运行路径。 |
| 3 | 运营者可启动授权 agent、观察 SSE 进度并审阅审计；拒绝发生在工作之前。 | ✗ FAILED | 授权拒绝和队列前复核由测试覆盖，但 [api.py](/root/source/AthenaQuant/backend/app/advanced/api.py:349) 只创建 job；[main.py](/root/source/AthenaQuant/backend/app/main.py:182) 注入 no-op provider，且全仓库生产代码没有调用 [notify_advanced_progress](/root/source/AthenaQuant/backend/app/services/quote_service.py:427)。 |
| 4 | 自定义策略仅在合同、AST、导入、超时和内存约束通过后运行，并可审阅受限运行结果或失败记录。 | ✗ FAILED | 默认 [sandbox.py](/root/source/AthenaQuant/backend/app/advanced/sandbox.py:37) launcher 不能证明隔离。独立探针提交无害、哈希匹配的策略返回 `isolation_unavailable`；该服务没有成功 run 记录/投影路径。 |

**Score:** 0/4 truths verified

## Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `backend/app/advanced/viewpoints.py` | 不可变观点与冻结评价 | ⚠️ HOLLOW | 服务和 SQLite 账本实质存在，但生产 API/UI 没有真实评价数据流。 |
| `backend/app/advanced/experiments.py` | 冻结实验、运行和反馈 | ⚠️ HOLLOW | 业务服务存在；生产 runner 明确不可用。 |
| `backend/app/advanced/evolution.py` | 五项门禁和注册型晋级 | ✓ VERIFIED (service) | 门禁矩阵、原子批准和 `registered_research_only` 状态存在；未发现 broker/monitor/decision-plan 调用。 |
| `backend/app/advanced/authorization.py`, `jobs.py` | 双阶段授权、限流和审计 | ⚠️ PARTIAL | 创建与 `run()` 前复核实现存在，但真实启动路由不触发 run/workflow。 |
| `backend/app/advanced/workflow.py` | 固定可恢复工作流 | ⚠️ ORPHANED | 图和单元测试存在，生产 lifespan 未构建/注入/调用它。 |
| `backend/app/advanced/sandbox.py` | fail-closed 受限执行 | ⚠️ PARTIAL | 拒绝边界有效，但无经验证 launcher 和成功受限运行结果。 |
| `frontend/src/components/advanced/ViewpointPanel.tsx` | 对象内观点与任务呈现 | ⚠️ HOLLOW | 已接入 typed API；后端生产数据缺失，E2E 使用路由拦截 fixture。 |
| `frontend/src/components/advanced/AdvancedResearchPanels.tsx` | 实验、晋级和沙箱工作流 | ⚠️ HOLLOW | 已组合进 Backtest；实际 experiment/sandbox 执行不可用。 |

## Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| Viewpoint service | SQLite ledger | 追加版本/证据/评价 | WIRED | 不可变触发器和 focused tests 通过。 |
| Viewpoint ledger | authorized API/UI | 评价读取和投影 | NOT WIRED | 版本查询没有 evaluation join；API 无评价 endpoint/runner。 |
| Experiment API | governed bounded runner | `run_specification()` | NOT WIRED | 生产配置是 `_UnavailableAdvancedRunner`。 |
| Session-bound job API | pre-run authorization + workflow | job start | NOT WIRED | 创建 job 后没有 `AdvancedJobService.run()` 或 `PersistentAdvancedGraph.ainvoke()` 调用。 |
| Job transitions | shared SSE | committed `advanced_progress` | NOT WIRED | SSE consumer/publisher函数存在，未从生产 job/workflow 调用。 |
| Sandbox API | proven isolated runner | contract admission then run | PARTIAL | admission拒绝存在；没有可通过的 launcher 或 run result。 |
| Frontend panels | typed API/root SSE | Query + shared EventSource | WIRED BUT HOLLOW | 客户端接线存在；自动浏览器测试用 `page.route()` 提供虚拟 API/SSE。 |

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `ViewpointPanel` | `viewpoint.evaluation` | `/api/advanced/viewpoints` | 否：版本仓储未读取评价 | ✗ DISCONNECTED |
| `AdvancedResearchPanels` | runs / feedback | `/api/advanced/experiments` | 否：生产 runner 始终不可用 | ✗ DISCONNECTED |
| `ViewpointPanel` job state | root `advanced_progress` | QuoteService | 否：没有生产发布调用 | ✗ DISCONNECTED |
| Sandbox panel | validation/run | `/sandbox/submissions` | 仅拒绝验证；无受限 run | ✗ DISCONNECTED |

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Advanced backend contracts | `cd backend && timeout 60s uv run pytest tests/advanced -q` | `73 passed in 21.68s` | ✓ PASS, but fakes do not prove lifespan wiring |
| Frontend build and Phase 4 browser suite | `cd frontend && pnpm run build && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts` | build passed; `8 passed, 6 skipped` | ✓ PASS, fixture-only |
| Default sandbox handles a harmless hash-bound strategy | focused `uv run python -c ... CustomStrategySandboxService.submit(...)` | `isolation_unavailable` | ✗ FAIL for executable-run path |

## Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
| ----------- | ------------ | ----------- | ------ | -------- |
| ADV-01 | 04-01, 04-04, 04-05, 04-09, 04-10 | 归因观点、变化与置信度表现 | ✗ BLOCKED | 评价事实不流向生产 API/UI。 |
| ADV-02 | 04-01, 04-04, 04-06, 04-09, 04-11 | 冻结规格、沙箱实验和反馈周期 | ✗ BLOCKED | 生产实验 runner 不可用。 |
| ADV-03 | 04-01, 04-04, 04-06, 04-08, 04-09, 04-11 | 受限演化与显式晋级门禁 | ✗ BLOCKED | 服务门禁存在，但真实实验链路无法生成可评估生产候选。 |
| SAFE-01 | 04-02, 04-04, 04-07, 04-08, 04-09, 04-10, 04-11 | 授权、allowlist、限流、作业、审计与 SSE | ✗ BLOCKED | 真实启动不执行/不发布 SSE；仅拒绝路径及 isolated unit fake 已证明。 |
| SAFE-02 | 04-03, 04-04, 04-07, 04-09, 04-11 | 合同与 fail-closed sandbox | ✗ BLOCKED | 安全拒绝实现存在，但成功受限运行及结果记录不存在。 |

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `backend/app/main.py` | 36 | `_UnavailableAdvancedRunner` injected as production experiment runner | 🛑 BLOCKER | 所有真实实验运行失败。 |
| `backend/app/main.py` | 185 | advanced job provider is a no-op lambda | 🛑 BLOCKER | 授权 agent 作业不会执行任何工作流。 |
| `backend/app/advanced/sandbox.py` | 37 | default launcher returns every capability as false | 🛑 BLOCKER | 不能产生已验证隔离的自定义策略运行。 |
| `frontend/e2e/phase4-advanced-capabilities.spec.ts` | 40-61 | all advanced API/SSE responses are Playwright fixtures | ⚠️ Warning | 通过的 UI tests 不能证明真实 FastAPI 生命周期、数据流或 SSE 发布。 |

未发现 Phase 4 变更文件中的未引用 `TBD`、`FIXME` 或 `XXX` 债务标记。禁止项“无 broker execution”在 advanced domain 中得到代码级支持：evolution 仅返回 `registered_research_only`，测试的 broker/monitor/plan/execution spies 为零调用；未发现 advanced 域调用 broker 或订单接口。

## Gaps Summary

本阶段的基础契约、SQLite 不可变记录、授权拒绝、五项晋级门禁和前端组件均已实现，并且计划级 `verify.artifacts`/`verify.key-links` 的存在性检查全部通过。但是这些检查产生了假阳性：它们没有验证生产 lifespan 是否装配真实执行者，也没有验证动态数据是否到达 UI。

需要先完成四个关联的垂直接线：受治理 viewpoint evaluation 投影、真实 bounded experiment runner、作业到 workflow/SSE/audit 的提交后链路，以及经肯定能力证明的 sandbox launcher 与 run ledger。然后用不拦截 `/api/advanced/*` 与 `/api/intraday/stream` 的临时生产宿主测试有效与拒绝路径，才可重新验证本阶段。

---

_Verified: 2026-07-12T00:00:00Z_
_Verifier: the agent (gsd-verifier)_
