# Phase 4: Advanced Capabilities - Research

**Researched:** 2026-07-12
**Domain:** 受治理的量化研究工作流、授权任务、策略晋级与本地受限执行
**Confidence:** MEDIUM

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Attributed Viewpoints And Confidence-Aware Performance
- **D-01:** A tracked viewpoint is an immutable version identified by a controlled source profile, market/instrument scope, and publication time. Every version retains its evidence, conclusion, and confidence; later changes never overwrite it.
- **D-02:** A material stance change is detected from structured-field thresholds across direction, rating/conclusion, target range, horizon, or confidence. Minor wording and evidence-only revisions remain visible revisions but do not become stance changes.
- **D-03:** Each viewpoint version freezes a 20-, 60-, or 120-trading-day evaluation window, benchmark, and outcome metric at creation. The benchmark defaults by asset type and may be explicitly overridden only from an allowed set; the chosen benchmark remains part of the immutable record.
- **D-04:** Performance presents confidence calibration in low/medium/high buckets with hit rate, relative return, sample count, and coverage period. Insufficient samples must be marked rather than summarized as a reliable conclusion.
- **D-05:** Corrections append a new version with a correction reason; original content remains auditable. Missing prices, benchmarks, or unsupported scope produce an explicit unevaluable outcome, never an inferred, zero, or silently excluded result.

### Hypothesis Experiment And Feedback Cycle
- **D-06:** A hypothesis becomes an immutable experiment-specification version before its sandbox run. The specification records the hypothesis, data scope, method, metrics, and success/failure criteria.
- **D-07:** Runs reference a governed-data snapshot/fingerprint and execution manifest containing strategy/factor version, parameters, resource limits, and environment information; they do not copy raw market data into a second store.
- **D-08:** Research feedback is an append-only structured conclusion of supported, refuted, inconclusive, or needs-replication, linked to the run, metrics, artifacts, and explanatory notes.
- **D-09:** Validation, timeout, and resource-limit failures remain auditable with their constraint-trigger reason and sanitized diagnostics. A retry is a new run and, where configuration changes, a new specification version.

### Strategy Evolution And Promotion
- **D-10:** Strategy candidates arise only through constrained mutations of validated research assets. Each candidate persists parent version, mutation operation, seed, and resolved configuration.
- **D-11:** Promotion requires explicit gates for contract and sandbox safety, complete provenance, in-sample and out-of-sample evidence, robustness, and cost assumptions. A single aggregate ranking cannot substitute for these gates.
- **D-12:** After automated gates pass, a researcher must explicitly approve promotion with an auditable time and rationale. Promotion creates a reusable registered research-strategy version only; it does not activate monitoring, create a decision plan, or execute a market action.

### Scoped Agent Authorization
- **D-13:** Agent workflows require short-lived, server-validated scoped tokens that authorize only named task types and approved market/instrument ranges.
- **D-14:** The operator owns the authoritative allowlist policy. Server-side token issuance binds the permitted intersection to the authorization record, and task creation checks the request target again.
- **D-15:** Unauthorized, out-of-allowlist, and rate-limited requests are rejected before a runnable task or SSE work begins. They retain a security audit summary that explains the rejection without exposing sensitive policy detail.
- **D-16:** Pending agent tasks revalidate current token and allowlist policy immediately before execution. A revoked or newly out-of-scope request is rejected and audited rather than running under its original creation-time authorization.

### the agent's Discretion
- Exact SQLite schema, migration mechanism, API route names, source-profile ingestion workflow, structured-field threshold values, supported benchmark catalog, and UI composition remain open, provided immutable lineage, visible uncertainty, and evaluability rules are preserved.
- The planner determines detailed idempotency, rate-limit accounting, SSE event shapes, audit-summary projection, machine-readable custom-strategy contract, AST/import policy, process/container isolation, timeout/memory values, and diagnostic redaction. These designs MUST satisfy `SAFE-01` and `SAFE-02`, enforce checks before execution, and preserve the established single-container, local operational-state boundary.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within Phase 4 scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ADV-01 | User can track attributed market viewpoints, identify material stance changes, and review confidence-aware performance results. | 不可变版本、冻结评估计划、可评估状态与校准投影。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| ADV-02 | Researcher can progress a hypothesis through an experiment specification, sandbox run, and recorded feedback cycle. | 规格/运行/反馈三层状态机、受治理输入清单与受限运行边界。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| ADV-03 | Researcher can evaluate and promote an evolved strategy from research asset through mutation, evaluation, and explicit promotion gates. | 候选谱系、独立门禁矩阵、人工批准事务与只注册不启用的结果。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| SAFE-01 | Operator can invoke agent workflows through scoped tokens, market and instrument allowlists, rate limits, idempotent jobs, audit summaries, and SSE progress updates. | 创建前与执行前授权、业务幂等、服务器范围过滤 SSE、脱敏审计。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| SAFE-02 | Researcher can validate and run custom strategies only through a machine-readable contract and sandbox with AST, import, timeout, and memory controls. | 严格合同/AST/import 准入、独立进程限制、失败分类和受限诊断。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] |
</phase_requirements>

## Summary

本期应新增一个独立的 `backend/app/advanced/` 领域，复用单一 `operational.db` 的迁移、事务和不可变记录风格，读取市场数据时只经既有 TickFlow/Backtest 边界。Phase 3 已在同一数据库中实现短生命周期、参数化 SQLite 连接，且用触发器阻止分析证据、报告、审阅、事件和观察记录更新或删除；Phase 4 应延续这个已验证的持久化模式。 [VERIFIED: codebase]

LangGraph 已以 `langgraph==1.2.9` 与 `langgraph-checkpoint-sqlite==3.1.0` 声明在后端依赖中，并且 Phase 3 已实现每次异步调用临时打开 `AsyncSqliteSaver` 的 `PersistentAnalysisGraph`。Phase 4 可复用该模式实现可恢复的受限工作流，但 checkpoint 只能保存执行游标和紧凑状态，不能替代 SQLite 中的授权、审计、观点、实验、门禁或晋级事实。 [VERIFIED: codebase] [CITED: https://docs.langchain.com/oss/python/langgraph/checkpointers]

现有 `StrategyEngine` 通过 `importlib` 执行位于 `data/strategies/custom` 与 `data/strategies/ai` 的 Python 文件；这与 SAFE-02 的不可信代码执行边界不兼容。高级自定义策略不得写入这些目录后由宿主引擎加载，也不得在 FastAPI 进程内执行。它必须先通过合同、AST 与 import allowlist，然后在独立、受限、无网络的子进程中运行；任何没有可用隔离启动条件的环境必须在实际执行前拒绝。 [VERIFIED: codebase] [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] [CITED: https://docs.python.org/3.11/library/subprocess.html]

**Primary recommendation:** 以“SQLite 业务状态机 + 固定 LangGraph 编排 + 两阶段服务器授权 + 独立受限进程”为核心；先建立可测的不可变/拒绝合同，再连接既有回测、SSE 与 React 工作区。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 观点版本、评估窗口、校准与不可评估状态 | API / Backend | Database / Storage | 版本、基准与市场输入必须在服务端冻结并持久化；浏览器不得按当前价格重算。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| 实验规格、运行清单、反馈和候选谱系 | API / Backend | Database / Storage | 这是可复算研究记录，须通过 SQLite 事务与外键保存。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| 策略评估 | API / Backend | Database / Storage | 调用既有 `StrategyBacktestService`/`BacktestEngine` 读取受治理面板并产出清单；不复制市场时序数据。 [VERIFIED: codebase] |
| 候选门禁与人工晋级 | API / Backend | Database / Storage | 独立门禁和批准理由是确定性业务规则，不由模型或客户端决定。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| 代理 token、allowlist、限流、任务二次校验 | API / Backend | Database / Storage | 发放、撤销、请求交集和执行前重验必须由服务器读取当前策略。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| 工作流恢复和人工暂停 | API / Backend | Database / Storage | LangGraph `thread_id` 管理 checkpoint；业务结果仍由 SQLite 幂等事务记录。 [CITED: https://docs.langchain.com/oss/python/langgraph/interrupts] |
| 自定义策略验证与受限运行 | API / Backend | OS process | 服务端控制合同准入与进程启动；Linux 子进程承受 CPU、内存、文件与网络边界。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] [CITED: https://docs.python.org/3.11/library/subprocess.html] |
| 受控任务状态流 | API / Backend | Browser / Client | 后端只广播允许的持久化阶段；既有 SSE 已将分析进度按服务器绑定范围过滤。 [VERIFIED: codebase] |
| 工作区呈现与本地阅读状态 | Browser / Client | API / Backend | React/TanStack Query 应渲染显式 DTO 与局部状态，不推断授权、门禁或审计。 [VERIFIED: codebase] [CITED: .planning/phases/04-advanced-capabilities/04-UI-SPEC.md] |

## Existing Integration Map

| Boundary | Exact module(s) | Phase 4 use | Do not do |
|----------|-----------------|-------------|-----------|
| 应用生命周期 | `backend/app/main.py:lifecycle` | 在同一 lifespan 中迁移并挂载 `advanced_repository`、授权/运行/门禁服务与可选图工厂，再注册独立 router。 [VERIFIED: codebase] | 不创建第二个 FastAPI app、独立 worker、外部队列或第二个运行数据库。 [CITED: .planning/PROJECT.md] |
| HTTP 会话身份 | `backend/app/main.py:auth_middleware`, `backend/app/services/auth.py` | 从 `request.state.reviewer_principal` 读取已认证且服务器派生的主体；将其绑定到授权、批准与审计记录。 [VERIFIED: codebase] | 不接受请求体中的操作者、reviewer、token 主体或授权范围作为权威。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| SQLite 演进 | `backend/app/operational/migrations.py`, `backend/app/analysis/repository.py` | 在 `MIGRATIONS` 追加版本化 schema；每连接启用外键，使用参数化 SQL、短生命周期连接与事务。 [VERIFIED: codebase] | 不为不可变对象提供 UPDATE/DELETE repository 或 API。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| 已有不可变范式 | `analysis_*` 迁移和 `AnalysisRepository` | 复用 partial unique index、状态受限 UPDATE、append-only 表与拒绝写入触发器的组合。 [VERIFIED: codebase] | 不将完整未验证 prompt、token、原始行情或完整异常堆栈写入审计。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] |
| LangGraph | `backend/app/analysis/graph.py` | 复用 per-invocation `AsyncSqliteSaver`、服务器生成 `thread_id` 与 `ainvoke` 适配层。 [VERIFIED: codebase] | 不让 graph state 成为系统记录，不让客户端提供/猜测 `thread_id`。 [CITED: https://docs.langchain.com/oss/python/langgraph/checkpointers] |
| 受治理数据与回测 | `backend/app/tickflow/repository.py`, `backend/app/backtest/engine.py`, `backend/app/backtest/strategy.py` | 使用既有 `StrategyBacktestService.run()`、返回的 `governed_input_manifest` 和已管理 artifacts 作为实验/门禁证据。 [VERIFIED: codebase] | 不将原始行情复制到 SQLite 或允许候选绕过 BacktestEngine。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| 既有策略 SSE | `backend/app/api/backtest.py:strategy_stream`, `frontend/src/lib/backtestTask.ts` | 复用任务去重、取消、受控进度和客户端重连经验，但为高级任务建立独立的持久化 job 状态机。 [VERIFIED: codebase] | 不把内存 `_running_jobs` 当作 SAFE-01 的授权、重放或审计系统。 [VERIFIED: codebase] |
| 共享 SSE | `backend/app/services/quote_service.py`, `backend/app/api/intraday.py` | 追加 allowlist 的 `advanced_progress` 事件；订阅时绑定服务器解析出的 advanced scope，发布前筛选。 [VERIFIED: codebase] | 不流式发送模型 token、原始草稿、token、策略源代码、allowlist 细节或未验证输出。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] |
| 现有策略保存 | `backend/app/api/strategy.py`, `backend/app/strategy/engine.py` | 仅作为待替换的风险路径和注册策略读取协作方。 [VERIFIED: codebase] | 不把 `/api/strategies/code/save`、`StrategyEngine.reload()` 或 `importlib` 用于 SAFE-02 的执行。 [VERIFIED: codebase] |
| 前端数据层 | `frontend/src/lib/api.ts`, `frontend/src/lib/queryKeys.ts` | 添加显式 advanced DTO/API 和对象/版本/运行维度的 Query Key。 [VERIFIED: codebase] | 不直接 `fetch`，不以前端状态合成授权、门禁、评估或审计。 [CITED: .planning/phases/04-advanced-capabilities/04-UI-SPEC.md] |
| 前端宿主 | `frontend/src/pages/Backtest.tsx`, `StockAnalysis`/Portfolio 分析详情，`frontend/src/pages/Analysis.tsx` | 将实验、演化、自定义策略置入 Backtest strategy mode；对象观点置入对象分析；任务审计置入现有分析/历史宿主。 [VERIFIED: codebase] [CITED: .planning/phases/04-advanced-capabilities/04-UI-SPEC.md] | 不增加顶级“高级能力”导航、平行壳或第二侧栏。 [CITED: .planning/phases/04-advanced-capabilities/04-UI-SPEC.md] |

## Standard Stack

### Core
| Library / component | Version | Purpose | Why Standard |
|---------------------|---------|---------|--------------|
| Existing Python | `3.11.2` environment; project requires `>=3.11` | FastAPI 服务、`ast`、`subprocess`、`resource` 等基础运行能力。 [VERIFIED: environment] [VERIFIED: codebase] | 标准库具备子进程超时、受控 `cwd`/`env`/文件描述符和 session 参数；需由 Phase 4 组合为 fail-closed runner。 [CITED: https://docs.python.org/3.11/library/subprocess.html] |
| Existing FastAPI | project declares `>=0.115` | 已认证 API、lifespan 资源、SSE endpoint。 [VERIFIED: codebase] | 已有应用/认证/路由注册模式；`StreamingResponse` 和 SSE generator 适合传送受控状态。 [CITED: https://fastapi.tiangolo.com/advanced/custom-response/] |
| Existing Pydantic | environment `2.13.4`; project declares `>=2.7` | 严格请求、合同、状态转移与 model draft schema。 [VERIFIED: environment] [VERIFIED: codebase] | `extra='forbid'`、字段限制和 `model_validate_json()` 可使未知字段与不合格 JSON fail closed。 [CITED: https://docs.pydantic.dev/latest/concepts/models/] |
| Existing SQLite | Python reports `3.40.1`; existing `operational.db` | 业务记录、授权/撤销、限流计数、审计、版本、门禁和批准。 [VERIFIED: environment] [VERIFIED: codebase] | 已有单容器运行边界、事务、外键、partial unique index 与不可变触发器前例。 [VERIFIED: codebase] [CITED: https://www.sqlite.org/docs.html] |
| Existing LangGraph | pin `1.2.9` declared by project | 有界、可恢复的自动化编排和人工批准暂停。 [VERIFIED: codebase] | 官方 API 支持 `StateGraph`、`interrupt()`、`Command(resume=...)` 与 checkpointer；它不承担策略裁决。 [CITED: https://docs.langchain.com/oss/python/langgraph/interrupts] |
| Existing SQLite checkpointer | pin `langgraph-checkpoint-sqlite==3.1.0` declared by project | 每个 job 的图 checkpoint。 [VERIFIED: codebase] | Phase 3 已用 `AsyncSqliteSaver` per invocation 的异步封装；延续已落地兼容模式。 [VERIFIED: codebase] |

### Supporting
| Library / component | Version | Purpose | When to Use |
|---------------------|---------|---------|-------------|
| Existing Polars/DuckDB/Parquet repository | existing project dependencies | 冻结评估和回测的受治理输入。 [VERIFIED: codebase] | 只在 TickFlow repository/BacktestEngine 内读取时序数据。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| Existing `sse-starlette` EventSourceResponse | project declares `>=2.0` | 共享 SSE endpoint。 [VERIFIED: codebase] | 保持现有 `QuoteSubscriber` 广播与 scope 绑定，而非新增流协议。 [VERIFIED: codebase] |
| Existing React 18 + TanStack Query 5 + lucide-react | versions in `frontend/package.json` | 既有工作区内的 DTO 渲染、查询失效、无障碍操作。 [VERIFIED: codebase] | 仅扩展 `api.ts`、`QK` 和本地组件。 [CITED: .planning/phases/04-advanced-capabilities/04-UI-SPEC.md] |
| Existing pytest/pytest-asyncio and Playwright | backend dev deps / frontend dev deps | 领域状态机、SQLite、假 sandbox、API、SSE 和浏览器合同验证。 [VERIFIED: codebase] | 在 Wave 0 建立安全拒绝矩阵与 E2E fixture。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 固定 LangGraph 编排 | 临时 coroutine 链 | 已锁定 LangGraph；coroutine 链不提供既有 checkpoint/interrupt 语义。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] |
| 单一 SQLite operational state | 外部队列、PostgreSQL 或第二个 datastore | 违背单容器、SQLite 运行状态和无外部队列边界。 [CITED: .planning/PROJECT.md] |
| 新受限子进程 runner | 宿主 `StrategyEngine` 动态 import | 后者会在应用进程内 `exec_module()`，不提供 SAFE-02 的隔离。 [VERIFIED: codebase] |
| 共享范围过滤 SSE | 任务专用 raw token stream | UI/AI 规范只允许受控阶段且禁止 raw token/未验证草稿。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] [CITED: .planning/phases/04-advanced-capabilities/04-UI-SPEC.md] |

**Installation:** 本期建议不安装新运行时或前端包；所有核心依赖已在项目声明中。 [VERIFIED: codebase]

**Version verification:** PyPI 当前列出 `langgraph` `1.2.9`、`langgraph-checkpoint-sqlite` `3.1.0`、`pydantic` `2.13.4` 和 `fastapi` `0.139.0`；Phase 4 应保持已经锁定/声明的兼容包，不因 registry 较新版本自动升级。 [VERIFIED: PyPI] [VERIFIED: codebase]

## Package Legitimacy Audit

本期的推荐实现不安装新外部包，因此不触发新增 Package Legitimacy Gate。`langgraph` 与 SQLite saver 已在项目依赖中，且其启用批准已作为 Phase 3 的既有决策记录。 [VERIFIED: codebase]

## Architecture Patterns

### System Architecture Diagram
```text
Selected object / research asset / validated parent strategy
                 |
                 v
        Advanced FastAPI router
                 |
                 +-- resolve authenticated server principal
                 +-- derive current policy and authorized subject scope
                 |
          [reject before job] ------------------> immutable security-audit summary
                 |
                 v
  SQLite transaction: authorization record + idempotency key + queued advanced_job
                 |
                 v
  worker-start revalidation: token expiry/revocation + allowlist + rate quota
                 |
       +---------+--------------------+--------------------+
       |         |                    |                    |
       v         v                    v                    v
 Viewpoint   Experiment spec/run   Evolution candidate   Agent draft workflow
 version     -> governed manifest  -> five gates          -> fixed graph state
       |         |                    |                    |
       +---------+--------------------+--------------------+
                 |                         |
                 v                         v
    SQLite append-only records       LangGraph checkpoint SQLite
    (source of truth)                (recovery cursor only)
                 |
                 +--> shared SSE: only persisted allowlisted phase + scoped DTO
                 |
                 +--> React object/Backtest/analysis-host panels

Custom strategy path:
 machine-readable contract -> AST/import validation -> isolated subprocess -> manifest/result
                              | fail                         | success/fail
                              v                              v
                    redacted constraint audit       append run evidence only
```

### Recommended Project Structure
```text
backend/app/advanced/
├── api.py                    # strict API contracts; resolves server principal/scope
├── schemas.py                # Pydantic domain and projected DTO models
├── repository.py             # SQLite transactions, append-only records, DTO readers
├── viewpoints.py             # immutable versions, stance diff, frozen outcome/calibration
├── experiments.py            # specification/run/feedback state machine and manifests
├── evolution.py              # constrained mutation, evidence gates, promotion transaction
├── authorization.py          # token issuance/revocation, policy intersection, quota checks
├── jobs.py                   # persistent job state and before-execution revalidation
├── workflow.py               # fixed StateGraph node adapters, no policy authority
├── sandbox.py                # contract/AST/import validation and isolated runner
├── audit.py                  # append-only redacted audit projection
└── projections.py            # response allowlists; never raw records/checkpoints

backend/tests/advanced/
├── test_viewpoints.py
├── test_experiments.py
├── test_evolution.py
├── test_authorization_jobs.py
├── test_sandbox.py
├── test_workflow.py
└── test_api_sse.py

frontend/src/components/advanced/
├── ViewpointPanel.tsx
├── ExperimentRunPanel.tsx
├── EvolutionPromotionPanel.tsx
├── AgentTaskPanel.tsx
├── SandboxStrategyPanel.tsx
└── AuditDetails.tsx
```

### Pattern 1: Authoritative State Is a Transactional SQLite State Machine
**What:** 将 `advanced_jobs` 的可变执行状态限制为已定义的单向转换；将 viewpoint/experiment spec/run/feedback/candidate/gate/approval/security audit 作为 append-only 事实。`job_id + outcome_type` 或 equivalent idempotency key 应有唯一约束，最终记录操作必须在事务中检查前序状态。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md]

**When to use:** 所有创建、恢复、重试、拒绝、批准和结果记录。Phase 3 已验证对活跃 run 使用 partial unique index，并通过条件 `UPDATE` 防止非法状态跳转。 [VERIFIED: codebase]

**Persistence minimum:**

| Table group | Required facts / invariants |
|-------------|-----------------------------|
| `advanced_viewpoint_versions`, `advanced_viewpoint_evidence`, `advanced_viewpoint_evaluations` | source profile、scope、published time、structured conclusion/confidence、correction/revision reason、frozen window/benchmark/metric、evaluable status/reason；version insert-only。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| `advanced_experiment_specs`, `advanced_experiment_runs`, `advanced_feedback` | frozen hypothesis/data/method/metrics/criteria；governed fingerprint、asset version、params、environment/resource manifest、artifact references；feedback enum only after completed eligible run。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| `advanced_strategy_candidates`, `advanced_promotion_gates`, `advanced_promotions` | parent version、mutation/seed/resolved config、five independent gate rows、approval principal/time/rationale、registered research-strategy version；one approval per candidate. [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| `advanced_authorizations`, `advanced_policy_revisions`, `advanced_rate_windows`, `advanced_jobs`, `advanced_security_audit` | opaque token hash/expiry/revocation, issued policy intersection, job ownership/target/idempotency/status, both authorization decisions, quota result and sanitized reason. [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| `advanced_sandbox_validations`, `advanced_sandbox_runs` | contract fingerprint、AST/import verdicts、resource limits、runner manifest、terminal constraint reason、sanitized diagnostics hash/summary；never source/secret/stack output in public projection。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] |

### Pattern 2: Authorize Twice, Then Create Work
**What:** 路由先由认证会话解析 principal，再由服务器以当前 operator policy 计算任务类型与 market/instrument 的允许交集。只有通过该检查、原子配额扣减及幂等获取后才插入可运行 job；实际 worker 开始前必须重新读取 token、撤销与最新 allowlist。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md]

**When to use:** 所有 agent workflow、sandbox run 和任何可排队高级操作。被拒绝请求只插入安全审计摘要，不创建 runnable job，不调用模型/runner，也不登记 SSE work。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md]

### Pattern 3: Graph Is an Orchestrator, Not an Authority
**What:** 每个节点只调用窄的服务接口。建议顺序为 `authorize_and_freeze -> optional_draft -> deterministic_gates -> human_interrupt -> record_once`；graph state 只含 server-generated job ID、授权 record ID、冻结引用、状态和经校验 draft。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md]

**When to use:** 需要模型研究草稿或人工批准暂停的 agent workflow；纯观点计算、实验写入和 sandbox 准入仍可直接走确定性服务。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md]

LangGraph 在 resume 时从节点开头重新执行 `interrupt()` 所在节点，因此批准节点不得写入外部结果。将结果写入置于 interrupt 之后的独立节点，并以 SQLite 幂等 key 保证重放只产生一次业务结果。 [CITED: https://docs.langchain.com/oss/python/langgraph/interrupts]

### Pattern 4: Validate Before Spawn, Record Every Terminal Constraint
**What:** custom strategy 是机器可读 contract 加受限代码包，而不是可自由运行的 Python。先严格验证 contract，再 parse AST；AST 规则至少拒绝 dynamic execution、动态 import、危险 attribute 链与 contract 未声明的顶层能力，并将 imports 限于显式 allowlist。只有通过验证后才由 runner 在新 session 的子进程启动。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md]

**When to use:** SAFE-02 的所有运行，包括重试。超时、内存、验证、import 或环境隔离失败分别记录为终态约束失败，不能生成 feedback 或晋级证据。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md]

`subprocess.Popen` 支持 `cwd`、受控 `env`、`close_fds=True`、`start_new_session=True` 和 timeout 控制；timeout 后必须终止整个子进程组并截断 stdout/stderr 后再生成诊断摘要。`communicate()` 会把输出缓存在内存，故 runner 必须限制输出大小，不能直接收集无限输出。 [CITED: https://docs.python.org/3.11/library/subprocess.html]

### Anti-Patterns to Avoid
- **将 checkpoint 当审计帐本：** checkpoint 可被恢复/重放；业务谱系、授权和批准必须由 append-only SQLite 记录承担。 [CITED: https://docs.langchain.com/oss/python/langgraph/checkpointers]
- **先建 job 再检查授权：** 这会违反 SAFE-01 “拒绝早于 runnable task/SSE” 的锁定决定。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md]
- **恢复时沿用旧 allowlist：** pending job 必须读取当前 token 和 policy；撤销/越界要记录拒绝而非运行。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md]
- **复用 `StrategyEngine` 执行 user code：** 该引擎使用 `importlib.util.spec_from_file_location(...).loader.exec_module()`，在宿主进程执行策略模块。 [VERIFIED: codebase]
- **单一排名即晋级：** 策略候选必须分别保留 contract/sandbox、provenance、IS/OOS、robustness、cost/feasibility 五项门禁。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md]
- **把缺少价格/基准的观点归零或删除：** 必须保存 `unevaluable` 状态及原因，校准汇总不可静默排除。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md]
- **把 raw model/code/error 通过 SSE 或 DTO 暴露：** 只发送 allowlisted stage/status/time/audit reference；详情以服务端脱敏投影读取。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 可恢复人审工作流 | 非持久化 callback 或无限 agent loop | 已有 LangGraph `StateGraph` + `AsyncSqliteSaver` + `interrupt`/`Command`。 [VERIFIED: codebase] [CITED: https://docs.langchain.com/oss/python/langgraph/interrupts] | 显式节点、thread checkpoint 与恢复语义可审阅；业务写入仍在 repository。 |
| 结构化输入/输出 | 宽松 dict、Markdown/regex 或前端拼接 JSON | Pydantic strict schema、`extra='forbid'`、`Field` bounds、`model_validate_json()`。 [CITED: https://docs.pydantic.dev/latest/concepts/models/] | 未知字段、越界范围和不合格模型 JSON 必须失败而不是降级猜测。 |
| 业务幂等 | 内存去重 dict | SQLite unique/partial unique index + transaction + 条件状态更新。 [VERIFIED: codebase] [CITED: https://www.sqlite.org/docs.html] | 重启、resume 和并发请求下仍需保证一次权威结果。 |
| SSE transport | 新建 websocket/agent stream | 既有 `QuoteService`/`EventSourceResponse` 范围过滤广播。 [VERIFIED: codebase] | 已有每连接队列、背压上限和分析 subject scope 前例。 |
| 市场数据快照 | 复制 raw prices 到新库 | `BacktestEngine`/TickFlow repository 与 manifest/reference。 [VERIFIED: codebase] | 保持 Parquet/DuckDB/Polars 为时序真相源，SQLite 只存元数据。 |
| Python 策略执行 | `eval`、`exec` 或 `importlib` 宿主加载 | 明确 contract + AST/import 规则 + 独立受限子进程。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] | 宿主动态加载已经能执行任意模块，不满足未信任代码边界。 [VERIFIED: codebase] |

**Key insight:** Phase 4 的难点不是生成研究建议，而是让每次创建、拒绝、重试、恢复和批准都能证明“当前授权有效、输入冻结、结果可归因、没有越界执行”。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md]

## Common Pitfalls

### Pitfall 1: 把不变版本实现为可更新的“最新记录”
**What goes wrong:** correction、minor revision、material stance change 和 evaluation 被更新到同一 row，历史证据或冻结 benchmark 被覆盖。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md]

**How to avoid:** 用一个稳定 viewpoint identity 和只增不改的 version row；明确 `revision_kind`、`correction_reason`、结构字段 diff 与评估计划。对版本/evidence/evaluation 使用 `BEFORE UPDATE/DELETE` triggers，类似现有 analysis 表。 [VERIFIED: codebase] [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md]

**Warning signs:** API 出现 PATCH/DELETE；UI 把历史版本标题叫“编辑”；evaluation 使用当前 benchmark/price 而非冻结 manifest。 [CITED: .planning/phases/04-advanced-capabilities/04-UI-SPEC.md]

### Pitfall 2: 授权只在创建时检查
**What goes wrong:** job 入队后 token 被撤销、policy 改变或 quota 被消耗，旧 job 仍启动模型或 sandbox。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md]

**How to avoid:** 将 `pre_execution_authorized` 作为 runnable 前唯一入口，重读 token hash、expiry、revocation、task type、scope intersection 与配额；失败写审计并转 rejected。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md]

**Warning signs:** worker 只接受一个创建时 payload；SSE 有 `running` 而无相应 pre-execution audit；撤销测试仍看到 runner/model 调用。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md]

### Pitfall 3: interrupt/replay 产生双重晋级或反馈
**What goes wrong:** 在 `interrupt()` 同一节点写 promotion/audit；resume 会回放节点，导致两条权威结果。 [CITED: https://docs.langchain.com/oss/python/langgraph/interrupts]

**How to avoid:** pause node 无副作用；后续 `record_once` 将 `job_id + outcome_type` unique key 和完整前序状态放进同一事务。 [CITED: https://docs.langchain.com/oss/python/langgraph/interrupts] [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md]

**Warning signs:** 同一 candidate 出现多个 promotion 记录；重放 `Command(resume)` 通过；事务外先写审计再写结果。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md]

### Pitfall 4: AST allowlist 被误称为完整 sandbox
**What goes wrong:** 仅解析 AST 或仅拒绝 `import`，然后仍用宿主进程/目录运行 code；资源、文件、网络与子进程逸出未被执行边界限制。 [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md]

**How to avoid:** AST/import 是 admission control，不是唯一隔离；另用独立 session/process、最小环境、只读/临时工作目录、资源限制、网络禁用与 fail-closed launcher。在当前系统环境中 `unshare`、`prlimit`、`timeout` 可用而 `bwrap` 不可用，实施计划必须先验证实际 namespace 权限和网络隔离，再允许任何 run。 [VERIFIED: environment] [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md]

**Warning signs:** runner 调用 `StrategyEngine.reload()`；任意 Python import 仍通过；sandbox test 没有文件/网络/动态执行/资源耗尽用例。 [VERIFIED: codebase] [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md]

### Pitfall 5: 将已有内存 SSE job 误用为 durable security job
**What goes wrong:** 既有 strategy stream 在 `_running_jobs` 内存字典创建并保留结果，重启后没有授权/审计恢复依据。 [VERIFIED: codebase]

**How to avoid:** 高级 job 以 SQLite job row 为真实状态；SSE 只读取已提交的 stage projection。沿用 EventSource 的连接/reconnect 表现，不沿用其内存安全模型。 [VERIFIED: codebase] [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md]

### Pitfall 6: 前端把不可评估或门禁不完整渲染为成功
**What goes wrong:** 缺失值被画成 `0%`、汇总不显示 sample/period，或排名/绿色图标替代门禁行。 [CITED: .planning/phases/04-advanced-capabilities/04-UI-SPEC.md]

**How to avoid:** DTO 使用明确的 `evaluable_status`、`gate_status` 和 `safe_reason` enum；UI 先显示 warning/rejection 和完整文字状态，保持五个 gate 行与所有 coverage 元数据。 [CITED: .planning/phases/04-advanced-capabilities/04-UI-SPEC.md]

## Code Examples

### SQLite Idempotent Finalization
```python
# Source: existing AnalysisRepository conditional transitions and Phase 4 AI-SPEC.
def record_promotion_once(repository, *, job_id: str, candidate_id: str, principal: str, rationale: str):
    with repository.connection() as conn, conn:
        job = conn.execute(
            "SELECT status FROM advanced_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if job is None or job["status"] != "awaiting_review":
            raise ValueError("advanced job state changed; refresh and retry")
        gates = conn.execute(
            "SELECT COUNT(*) FROM advanced_promotion_gates "
            "WHERE candidate_id = ? AND status = 'passed'", (candidate_id,)
        ).fetchone()[0]
        if gates != 5:
            raise ValueError("promotion gates are incomplete")
        conn.execute(
            "INSERT INTO advanced_promotions "
            "(job_id, candidate_id, reviewer_principal, rationale, created_at) "
            "VALUES (?, ?, ?, ?, ?) ",
            (job_id, candidate_id, principal, rationale, now()),
        )
        changed = conn.execute(
            "UPDATE advanced_jobs SET status = 'recorded' "
            "WHERE id = ? AND status = 'awaiting_review'", (job_id,)
        ).rowcount
        if changed != 1:
            raise ValueError("advanced job state changed; refresh and retry")
```
The real migration must add a unique `advanced_promotions(job_id)` or equivalent outcome-key constraint and map `IntegrityError` to a safe conflict response. [VERIFIED: codebase] [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md]

### Pure Approval Pause, Then Idempotent Write
```python
# Source: LangGraph interrupts documentation and Phase 4 AI-SPEC.
from langgraph.types import Command, interrupt

def human_gate(state: AdvancedState) -> dict[str, str]:
    # No audit or promotion write here: this node re-runs on resume.
    decision = interrupt({"job_ref": state["job_ref"], "kind": "promotion"})
    return {"human_decision": "approved" if decision == "approve" else "rejected"}

async def record_outcome(state: AdvancedState) -> dict[str, object]:
    await outcome_service.record_once(
        job_id=state["job_id"],
        decision=state["human_decision"],
    )
    return {}

async def resume(job_id: str, approved: bool):
    return await graph.ainvoke(
        Command(resume="approve" if approved else "reject"),
        {"configurable": {"thread_id": job_id}},
    )
```
[CITED: https://docs.langchain.com/oss/python/langgraph/interrupts]

### Scoped SSE Projection
```python
# Source: existing QuoteSubscriber.push_analysis_progress pattern.
def publish_advanced_stage(quote_service, job):
    quote_service.notify_advanced_progress(
        job_id=job.id,
        subject_kind=job.subject_kind,
        subject_key=job.subject_key,
        stage=job.stage,  # enum: authorized/frozen/gates_complete/awaiting_review/recorded/rejected
        occurred_at=job.stage_recorded_at,
    )

# Subscriber checks its server-bound scope before appending; API routes never
# accept the subscriber scope from the browser.
```
`QuoteSubscriber.push_analysis_progress()` already filters event delivery through its server-provided scope and caps queued progress entries; Phase 4 should mirror that design with a separate advanced projection. [VERIFIED: codebase]

### Strict Contract Boundary Before Any Runner Spawn
```python
# Source: Pydantic strict validation docs and Phase 4 AI-SPEC.
class CustomStrategyContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    contract_version: Literal["advanced-strategy-v1"]
    parent_asset_id: str = Field(min_length=1, max_length=128)
    declared_inputs: list[Literal["governed_panel"]] = Field(min_length=1, max_length=1)
    declared_imports: list[str] = Field(default_factory=list, max_length=8)
    timeout_seconds: int = Field(ge=1, le=60)
    memory_limit_mb: int = Field(ge=64, le=1024)

def validate_contract(payload: str) -> CustomStrategyContract:
    return CustomStrategyContract.model_validate_json(payload)
```
After schema validation, AST/import validation and a platform-isolation availability check remain mandatory; Pydantic validation alone cannot grant execution authority. [CITED: https://docs.pydantic.dev/latest/concepts/models/] [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| In-memory strategy task and arbitrary Python module loading | Persistent, server-authorized job record plus isolated custom execution path | Phase 4 design | 把授权/replay/audit与执行进程边界纳入可验证合同。 [VERIFIED: codebase] [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] |
| 可写的当前对象快照 | 不可变版本、补正/重试追加、派生当前投影 | Phase 3 precedent extended in Phase 4 | 保留观点、实验、晋级和安全拒绝的完整谱系。 [VERIFIED: codebase] [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| SSE 可传任意任务文本 | scope-filtered persisted stage DTO | Phase 3 existing pattern extended in Phase 4 | 防止未验证草稿、机密策略或 policy 细节通过 streaming 泄露。 [VERIFIED: codebase] [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] |

**Deprecated/outdated:** `/api/strategies/code/save` 加载到 `StrategyEngine` 的宿主 Python module 机制不得作为 Phase 4 custom strategy runner；保留其既有功能的同时，SAFE-02 必须走独立路径。 [VERIFIED: codebase]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `unshare` 与 `prlimit` 可执行并不证明当前 Docker/host namespace 权限可建立足以禁止网络和文件逸出的隔离；实现前必须有 capability smoke test，失败则拒绝 custom execution。 [ASSUMED] | Common Pitfalls / Environment | 若错误放行，会把未隔离代码当作 sandbox 执行。 |
| A2 | 五项 promotion gate 在数据库中各保存一条 row，且“通过”数量为五是批准的最小条件。此为实现建议，阶段决定只锁定独立门禁类别。 [ASSUMED] | Architecture Patterns | 若 gate 定义有额外/替代类别，批准逻辑会错误阻断或放行。 |
| A3 | 60 秒/1024MB 是示例 contract 上限而非已批准的生产限制；最终值应由 planner 依据本机容量、回测负载和 UI-SPEC 的资源摘要决定。 [ASSUMED] | Code Examples | 过低会误拒绝合法任务，过高会削弱单容器保护。 |

## Open Questions

1. **Sandbox launcher 的可验证 Linux 隔离方案 — RESOLVED BY PLAN**
   - What we know: 环境发现 `unshare`、`prlimit`、`timeout`，没有 `bwrap`。 [VERIFIED: environment]
    - Resolution: Plan 04-03 defines the required harmless probe evidence; Plan 04-07 implements and persists affirmative proof of user/mount/network namespaces, blocked network, read-only governed input, temporary writable work area, resource limits, and cleanup. Any missing or inconclusive proof permanently makes every custom-run API reject before spawning until a later affirmative probe exists. [CITED: .planning/phases/04-advanced-capabilities/04-03-PLAN.md] [CITED: .planning/phases/04-advanced-capabilities/04-07-PLAN.md]

2. **权威 allowlist policy 的本地管理来源 — RESOLVED BY PLAN**
   - What we know: operator 拥有权威 allowlist；UI-SPEC 明确本期不实现 token/allowlist editor。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] [CITED: .planning/phases/04-advanced-capabilities/04-UI-SPEC.md]
    - Resolution: Plan 04-04 defines strict deployment-owned `advanced_policy_v1`; Plan 04-07 loads it only during server bootstrap, persists canonical revision/fingerprint snapshots, refuses issuance when it is absent or malformed, and provides no browser policy editor or policy-detail endpoint. [CITED: .planning/phases/04-advanced-capabilities/04-04-PLAN.md] [CITED: .planning/phases/04-advanced-capabilities/04-07-PLAN.md]

3. **观点 source-profile 的导入入口和 benchmark catalog — RESOLVED BY PLAN**
   - What we know: source-profile ingestion、结构差异阈值和 benchmark catalog 被明确保留给 agent discretion。 [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md]
    - Resolution: Plans 04-04 and 04-05 define the initial server-only catalog: `operator-research-v1` accepts `CN-A`; stock/ETF default to `000300.SH`; index defaults to `000001.SH`; explicit overrides are limited to `000300.SH`, `000905.SH`, and `000852.SH`. The policy revision/fingerprint freezes with every viewpoint; absent or mismatched profile/scope/benchmark records an explicit unevaluable condition rather than a guessed default. [CITED: .planning/phases/04-advanced-capabilities/04-04-PLAN.md] [CITED: .planning/phases/04-advanced-capabilities/04-05-PLAN.md]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | backend/domain/sandbox runner | ✓ | `3.11.2` | — [VERIFIED: environment] |
| `uv` | backend test/install workflow | ✓ | `0.9.30` | — [VERIFIED: environment] |
| Existing LangGraph + SQLite saver declaration | workflow/checkpoint | ✓ declared; runtime import not independently confirmed | pins `1.2.9` / `3.1.0` | retain Phase 3 graph path; do not upgrade. [VERIFIED: codebase] |
| SQLite | operational state | ✓ | `3.40.1` | — [VERIFIED: environment] |
| `unshare` | potential namespace isolation | ✓ | executable found | must still prove permissions and network/filesystem isolation. [VERIFIED: environment] [ASSUMED] |
| `prlimit` | resource limits | ✓ | executable found | Python `resource` pre-exec mechanism may be used only after runner test. [VERIFIED: environment] [ASSUMED] |
| `timeout` | hard wall-clock fallback | ✓ | executable found | process-group kill implemented by runner. [VERIFIED: environment] [CITED: https://docs.python.org/3.11/library/subprocess.html] |
| `bwrap` | alternative sandbox launcher | ✗ | — | do not install by default; capability probe decides whether existing Linux primitives suffice. [VERIFIED: environment] [ASSUMED] |
| Node/pnpm | frontend build/E2E | ✓ | Node `25.6.0`; pnpm `11.1.1` | — [VERIFIED: environment] |
| Docker | single-container verification | ✓ | `29.2.1` | — [VERIFIED: environment] |

**Missing dependencies with no fallback:** none at research time; SAFE-02 implementation is blocked until the planned isolation capability test proves a safe launcher or returns a fail-closed outcome. [ASSUMED]

**Missing dependencies with fallback:** `bwrap` is absent; the planner must not install it implicitly and may use a verified existing launcher only after the capability test. [VERIFIED: environment] [ASSUMED]

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest>=8.0` + `pytest-asyncio>=0.23`; Playwright `@playwright/test` `1.61.1`. [VERIFIED: codebase] |
| Config file | `backend/pyproject.toml` with `asyncio_mode = "auto"`; `frontend/playwright.config.ts`. [VERIFIED: codebase] |
| Quick run command | `cd backend && uv run pytest tests/advanced -q` |
| Full suite command | `cd backend && uv run pytest -q && cd ../frontend && pnpm run build && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ADV-01 | Immutable viewpoint versions, structured material changes, frozen window/benchmark, unevaluable outcomes and calibration buckets. | repository + service + API | `cd backend && uv run pytest tests/advanced/test_viewpoints.py -q` | ❌ Wave 0 |
| ADV-02 | Frozen experiment specs, governed manifests, terminal resource failures, append-only eligible feedback and retry semantics. | repository + service | `cd backend && uv run pytest tests/advanced/test_experiments.py -q` | ❌ Wave 0 |
| ADV-03 | Mutation provenance, five independent gates, approval reason/idempotency, registered-only result and no execution invocation. | service + repository + API | `cd backend && uv run pytest tests/advanced/test_evolution.py -q` | ❌ Wave 0 |
| SAFE-01 | Expired/revoked/out-of-range/rate-limited requests reject before work/SSE; pending job revalidates; events stay scoped. | API + state machine + SSE | `cd backend && uv run pytest tests/advanced/test_authorization_jobs.py tests/advanced/test_api_sse.py -q` | ❌ Wave 0 |
| SAFE-02 | Contract/AST/import validation, isolated runner time/memory/process failure, redaction and no feedback/promotion on failure. | unit + controlled subprocess fixture | `cd backend && uv run pytest tests/advanced/test_sandbox.py -q` | ❌ Wave 0 |
| ADV-01..SAFE-02 | Required UI placement, rejection/unevaluable states, promotion dialog, task stages, keyboard and responsive scenarios. | Playwright E2E | `cd frontend && pnpm exec playwright test e2e/phase4-advanced-capabilities.spec.ts` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** relevant `tests/advanced` subset plus `cd frontend && pnpm run build` when TypeScript changes. [VERIFIED: codebase]
- **Per wave merge:** `cd backend && uv run pytest -q` plus targeted Phase 4 desktop/mobile Playwright. [ASSUMED]
- **Phase gate:** full suite green, sandbox hostile-input matrix green, and all six UI-SPEC verification scenarios performed at `1440px`, `1024px`, `375px`. [CITED: .planning/phases/04-advanced-capabilities/04-UI-SPEC.md]

### Wave 0 Gaps
- [ ] `backend/tests/advanced/test_viewpoints.py` — append-only versions, material diff, frozen 20/60/120 outcomes, missing data and calibration coverage.
- [ ] `backend/tests/advanced/test_experiments.py` — specification/run/feedback state transitions and retry/new-version semantics.
- [ ] `backend/tests/advanced/test_evolution.py` — mutation lineage, gate truth table, approval replay and no broker/activation dependency call.
- [ ] `backend/tests/advanced/test_authorization_jobs.py` — token expiry/revocation/scope/quota/idempotency/create-vs-start rejection matrix.
- [ ] `backend/tests/advanced/test_sandbox.py` — malicious AST/import/dynamic execution/file/network/process/resource probes and diagnostic redaction.
- [ ] `backend/tests/advanced/test_workflow.py` — exact graph topology, replay-safe interrupt, `thread_id` ownership and one business outcome.
- [ ] `backend/tests/advanced/test_api_sse.py` — DTO allowlist, denied no-stream behavior, subscriber scope and terminal stages.
- [ ] `frontend/e2e/phase4-advanced-capabilities.spec.ts` — API fixtures, UI-SPEC scenario coverage, responsive keyboard/dialog states.
- [ ] Harmless sandbox capability probe — verifies the selected launcher has the required isolation properties before any custom code endpoint can execute.

## Security Domain

OWASP ASVS enforcement is enabled at Level 1 in `.planning/config.json`; this phase handles authentication-derived authority, authorization, untrusted input, executable code and sensitive audit output, so the following categories apply. [VERIFIED: codebase] [CITED: https://owasp.org/www-project-application-security-verification-standard/]

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Existing `/api/` middleware validates the session and attaches opaque server principal before advanced routes execute. [VERIFIED: codebase] |
| V3 Session Management | yes | Bind advanced authorization records to server-resolved principal; do not treat `job_id`, browser scope or token claims as authority. [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| V4 Access Control | yes | Server computes allowlist intersection at create and start; scope every job/version/audit lookup through persisted subject ownership. [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| V5 Input Validation | yes | Strict Pydantic contracts; bounded enums/IDs; AST/import allowlists; parameterized SQLite; server-issued IDs. [CITED: https://docs.pydantic.dev/latest/concepts/models/] [VERIFIED: codebase] |
| V6 Cryptography | yes | Store only hash/fingerprint of short-lived authorization secret in audit state; use existing session transport/configuration and do not hand-roll token crypto. [ASSUMED] |
| V7 Error Handling and Logging | yes | Redact runner/provider diagnostics and expose safe reason/audit reference only; never stream raw output/secrets. [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] |
| V8 Data Protection | yes | Keep market data in governed lake; persist manifest/hash/references in SQLite; do not expose evidence, source code, allowlists or tokens in client DTOs. [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| V10 Malicious Code | yes | Admission validation plus independently constrained subprocess; capability failure blocks execution. [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] |

### Known Threat Patterns for This Stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Forged or replayed task/approval ID | Spoofing / Tampering | Resolve job to persisted subject and principal, compare expected state in transaction, unique idempotency outcome, and audit conflict. [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] |
| Token revoked after enqueue | Elevation of Privilege | Revalidate current token and allowlist immediately before work; reject before model/sandbox/SSE work. [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] |
| Policy-detail disclosure through errors/SSE | Information Disclosure | Safe reason enum plus redacted audit projection; scope-filtered named stage events only. [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] |
| SQLite race/replay | Tampering | Transactional conditional updates, foreign keys, partial/unique indexes, append-only triggers and idempotency keys. [VERIFIED: codebase] [CITED: https://www.sqlite.org/docs.html] |
| Prompt/evidence injection changes authority | Tampering | Treat all source/user text as data, Pydantic validate drafts, freeze server references, deterministic routes/gates and no model tools. [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] |
| Custom code filesystem/network/subprocess escape or resource exhaustion | Elevation of Privilege / Denial of Service | AST/import admission, isolated runner, namespace capability verification, minimal environment, process-group termination, resource/output limits and fail-closed behavior. [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] [CITED: https://docs.python.org/3.11/library/subprocess.html] |
| Unauthorized promotion or broker call | Elevation of Privilege | All gates plus human reason in transaction; no execution/broker capability injected into advanced domain; tests assert zero calls. [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] |

## Sources

### Primary (HIGH confidence)
- `backend/app/main.py`, `backend/app/analysis/{graph.py,repository.py,service.py}`, `backend/app/operational/migrations.py` — actual lifecycle, SQLite and checkpoint patterns. [VERIFIED: codebase]
- `backend/app/api/{backtest.py,intraday.py,strategy.py}`, `backend/app/services/quote_service.py`, `backend/app/strategy/engine.py` — actual strategy execution, SSE and unsafe dynamic-load seams. [VERIFIED: codebase]
- `frontend/src/{lib/api.ts,lib/queryKeys.ts,lib/backtestTask.ts,pages/Backtest.tsx}`, existing Phase 3 E2E config — client integration and validation conventions. [VERIFIED: codebase]

### Secondary (MEDIUM confidence)
- https://docs.langchain.com/oss/python/langgraph/interrupts — replay/interrupt/Command/idempotency behavior. [CITED: https://docs.langchain.com/oss/python/langgraph/interrupts]
- https://docs.langchain.com/oss/python/langgraph/checkpointers — durable checkpoint role. [CITED: https://docs.langchain.com/oss/python/langgraph/checkpointers]
- https://fastapi.tiangolo.com/advanced/custom-response/ — async streaming response behavior. [CITED: https://fastapi.tiangolo.com/advanced/custom-response/]
- https://docs.pydantic.dev/latest/concepts/models/ — strict model validation behavior. [CITED: https://docs.pydantic.dev/latest/concepts/models/]
- https://docs.python.org/3.11/library/subprocess.html — subprocess control and timeout semantics. [CITED: https://docs.python.org/3.11/library/subprocess.html]
- https://www.sqlite.org/docs.html — SQLite transactions, foreign keys and WAL documentation. [CITED: https://www.sqlite.org/docs.html]
- `.planning/phases/04-advanced-capabilities/{04-CONTEXT.md,04-AI-SPEC.md,04-UI-SPEC.md}` — locked domain, AI and UI contracts. [CITED: .planning/phases/04-advanced-capabilities/04-CONTEXT.md] [CITED: .planning/phases/04-advanced-capabilities/04-AI-SPEC.md] [CITED: .planning/phases/04-advanced-capabilities/04-UI-SPEC.md]

### Tertiary (LOW confidence)
- None beyond assumptions explicitly listed above. [VERIFIED: research]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH for existing project dependencies and integration seams; MEDIUM for upstream API semantics supplied by official Context7 documentation. [VERIFIED: codebase] [CITED: https://docs.langchain.com/oss/python/langgraph/interrupts]
- Architecture: HIGH for existing SQLite/SSE/graph/strategy seams; MEDIUM for the final sandbox launcher pending capability probe. [VERIFIED: codebase] [ASSUMED]
- Pitfalls: HIGH for dynamic module loading and in-memory job behavior; MEDIUM for OS isolation operation details pending environment probe. [VERIFIED: codebase] [ASSUMED]

**Research date:** 2026-07-12
**Valid until:** 2026-08-11 for stable project seams; recheck Python/Linux isolation conditions immediately before SAFE-02 implementation. [ASSUMED]
