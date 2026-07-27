---
phase: 05-optional-enhancements
reviewed: 2026-07-26T18:38:43Z
depth: standard
files_reviewed: 98
files_reviewed_list:
  - backend/app/advanced/sandbox.py
  - backend/app/forecast/api.py
  - backend/app/forecast/artifacts.py
  - backend/app/forecast/calendar.py
  - backend/app/forecast/calibration.py
  - backend/app/forecast/catalog.py
  - backend/app/forecast/checkpoints.example.json
  - backend/app/forecast/input.py
  - backend/app/forecast/kronos_adapter.py
  - backend/app/forecast/projections.py
  - backend/app/forecast/repository.py
  - backend/app/forecast/runner.py
  - backend/app/forecast/service.py
  - backend/app/main.py
  - backend/app/operational/migrations.py
  - backend/app/optional_artifacts.py
  - backend/app/optional_modules.py
  - backend/app/shadow/__init__.py
  - backend/app/shadow/api.py
  - backend/app/shadow/artifacts.py
  - backend/app/shadow/distillation.py
  - backend/app/shadow/evaluation.py
  - backend/app/shadow/importer.py
  - backend/app/shadow/production.py
  - backend/app/shadow/projections.py
  - backend/app/shadow/repository.py
  - backend/app/shadow/schemas.py
  - backend/app/shadow/service.py
  - backend/app/theses/__init__.py
  - backend/app/theses/api.py
  - backend/app/theses/conditions.py
  - backend/app/theses/evidence.py
  - backend/app/theses/projections.py
  - backend/app/theses/repository.py
  - backend/app/theses/scheduler.py
  - backend/app/theses/schemas.py
  - backend/app/theses/service.py
  - backend/app/vendor/kronos/__init__.py
  - backend/app/vendor/kronos/kronos.py
  - backend/app/vendor/kronos/LICENSE
  - backend/app/vendor/kronos/module.py
  - backend/app/vendor/kronos/UPSTREAM.json
  - backend/pyproject.toml
  - backend/scripts/provision_kronos.py
  - backend/scripts/sync_kronos.py
  - backend/scripts/verify_phase5_final_gate.py
  - backend/tests/advanced/test_sandbox.py
  - backend/tests/forecast/fixtures/cn_a_sessions.parquet
  - backend/tests/forecast/fixtures/governed_daily.parquet
  - backend/tests/forecast/fixtures/maturity_actuals.parquet
  - backend/tests/forecast/fixtures/sample_paths.npy
  - backend/tests/forecast/test_api.py
  - backend/tests/forecast/test_calibration.py
  - backend/tests/forecast/test_catalog.py
  - backend/tests/forecast/test_input.py
  - backend/tests/forecast/test_kronos_adapter.py
  - backend/tests/forecast/test_kronos_regression.py
  - backend/tests/forecast/test_runner.py
  - backend/tests/forecast/verify_red_contract.py
  - backend/tests/phase5_real_host_harness.py
  - backend/tests/shadow/fixtures/executions_gb18030.csv
  - backend/tests/shadow/fixtures/executions_utf8.csv
  - backend/tests/shadow/fixtures/executions.xlsx
  - backend/tests/shadow/test_distillation.py
  - backend/tests/shadow/test_evaluation_retention.py
  - backend/tests/shadow/test_evidence_sets.py
  - backend/tests/shadow/test_imports.py
  - backend/tests/shadow/verify_red_contract.py
  - backend/tests/test_kronos_provisioner.py
  - backend/tests/test_kronos_vendor_sync.py
  - backend/tests/test_operational_migrations.py
  - backend/tests/test_phase5_final_gate.py
  - backend/tests/test_phase5_foundation.py
  - backend/tests/test_phase5_optional_dependencies.py
  - backend/tests/test_phase5_optional_host.py
  - backend/tests/theses/test_api.py
  - backend/tests/theses/test_contracts.py
  - backend/tests/theses/test_lifecycle.py
  - backend/tests/theses/test_scheduler.py
  - backend/tests/theses/test_versions.py
  - backend/tests/theses/verify_red_contract.py
  - backend/tests/verify_phase5_host_red.py
  - frontend/e2e/phase5-optional-enhancements.spec.ts
  - frontend/e2e/phase5-shadow-real-host.spec.ts
  - frontend/e2e/verify-phase5-red-contract.mjs
  - frontend/playwright.phase5-real-host.config.ts
  - frontend/src/components/analysis/AnalysisWorkspace.tsx
  - frontend/src/components/analysis/ForecastPanel.tsx
  - frontend/src/components/analysis/ThesisPanel.tsx
  - frontend/src/components/PageHeader.tsx
  - frontend/src/index.css
  - frontend/src/lib/api.ts
  - frontend/src/lib/forecastTask.ts
  - frontend/src/lib/phase5Api.ts
  - frontend/src/lib/queryKeys.ts
  - frontend/src/pages/Backtest.tsx
  - frontend/src/pages/backtest/ShadowAccount.tsx
  - frontend/src/pages/StockAnalysis.tsx
findings:
  critical: 4
  warning: 1
  info: 0
  total: 5
status: issues_found
---

# Phase 05：代码审查报告

**审查时间：** 2026-07-26T18:38:43Z
**深度：** standard  
**审查文件：** 98
**状态：** issues_found

## Summary

本轮按原 frontmatter 精确复用 98 个文件，对报告生成后的四笔维护提交
`04e2de9`、`9cf5e73`、`42a8fe6`、`b86437b` 做了 iteration 3/3 standard 复审。
新增的 6 个定向修复测试全部通过，Sandbox 全文件在 Windows 为 52 passed。

仍发现 4 项 BLOCKER 和 1 项 WARNING。Sandbox 的 AST 修复可通过先给 `getattr`
取别名而绕过；Forecast service 新增的 terminal 集合与仓储状态机不一致；retry
在幂等 terminal 重放及创建后的绑定失败路径仍会遗留 artifact/queued lineage；
dispatcher 超时关闭后 host 会永久丢弃仍存活 worker 的所有权。Forecast runner
测试还保留未隔离的 POSIX 假设，本轮 Windows 运行结果为 67 passed、15 failed。

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01 [BLOCKER]：Sandbox 反射检查可通过 builtin 别名绕过

**File:** `backend/app/advanced/sandbox.py:568-585`

**Issue:** `_validate_ast()` 只在 `ast.Call.func` 是名字且名字本身等于
`getattr`/`vars` 等时拒绝。它允许先把 builtin 赋给普通变量，再通过该变量调用；
字符串形式的 `"__builtins__"` 和 `"Popen"` 也不受 `ast.Name`/`ast.Attribute`
检查约束。以下源码的实测验证结果仍为 `None`：

```python
import json
reflect = getattr
builtins = reflect(json, "__builtins__")
importer = builtins["__import__"]
module = importer("subprocess")
constructor = reflect(module, "Popen")
constructor(["/usr/bin/python3", "-c", "import time; time.sleep(60)"])
```

这会恢复任意导入和子进程创建能力，因而 `04e2de9` 没有关闭原安全边界。

**Fix:** 不要把 AST denylist 当作 Python capability 边界。移除普通 Python 模块
导入与完整 builtins，改用受控 DSL/解释器或只暴露无反射面的 capability proxy；
同时在隔离层限制进程数、系统调用和 descendant 生命周期。短期回归至少必须覆盖
builtin 赋值、默认参数/容器转存、字符串拼接属性名等间接调用路径。

### CR-02 [BLOCKER]：Service 与 repository 的 terminal 状态集合漂移，合法 retry 被拒绝

**File:** `backend/app/forecast/service.py:23-32`

**Related:** `backend/app/forecast/service.py:291-295`,
`backend/app/forecast/repository.py:32-41`

**Issue:** service 的 `_TERMINAL_JOB_STATUSES` 使用
`inference_failed`、`commit_failed`、`cancelled`，而仓储真实状态机使用
`model_unavailable`、`timed_out`、`resource_limited`。集合差异已实测为：

```text
service_only     = cancelled, commit_failed, inference_failed
repository_only  = model_unavailable, resource_limited, timed_out
```

因此由 runner 合法 terminalize 为模型不可用、超时或资源受限的 job，在 service
第 294 行就返回冲突；repository 本来允许这些 source 创建 retry，却永远不会被调用。

**Fix:** 删除 service 中重复定义的状态集合，由 repository 提供单一的
`is_retryable_terminal(job)`/枚举并让 service 调用；或者至少从同一公共状态定义导入。
增加对 repository 每个 terminal 状态的参数化 service/API retry 测试，防止状态机再次漂移。

### CR-03 [BLOCKER]：Retry 的幂等重放和 post-create 失败仍未事务性清理

**File:** `backend/app/forecast/service.py:299-357`

**Related:** `backend/app/forecast/repository.py:592-607`

**Issue:** service 在调用 `create_retry_job()` 前总会 `_prepare_for_job()` 并冻结新
artifact，但 repository 可能因相同 idempotency key 返回既有 terminal retry。
service 只在 `job.status == "queued"` 分支处理新 artifact；terminal 重放直接返回，
导致每次幂等重放都留下一个未绑定 namespace。最小复现实测返回
`result_status=completed` 且 `discarded=[]`。

创建新 queued retry 后也没有覆盖 `_bind()`、`_dispatch()` 和 canonical reload 的
补偿边界。实测令 `_bind()` 抛错后，请求抛出 `RuntimeError`，数据库仍保留
`status=queued`，新 artifact 同样没有被丢弃；轮询 dispatcher 随后仍可消费这个
客户端不知道 ID、且缺少完整 worker context 的 job。

**Fix:** 在 freeze 前先做 operation-first idempotency lookup，terminal/已绑定重放
直接返回 canonical，不创建 artifact。对真正的新 retry，把 lineage 创建、commit
identity 绑定和可消费状态发布放入一个 repository 事务；在事务完成前不要暴露
`queued`。若现有 schema 必须先插入，则所有 bind/dispatch/reload 失败路径都必须
terminalize 可追踪 job，并在确认无引用后清理 invocation-owned artifact。增加
terminal replay、binder failure、dispatcher failure 和 canonical reload failure
后的“无 orphan artifact、无隐藏 queued cursor”测试。

### CR-04 [BLOCKER]：Dispatcher 超时关闭会被当作成功，host 永久遗失活 worker

**File:** `backend/app/forecast/service.py:103-108`

**Related:** `backend/app/optional_modules.py:501-512`

**Issue:** `DurableForecastDispatcher.close()` 在 `join(timeout)` 后不检查线程是否仍
存活。若 `runner.run_job()` 阻塞，最小复现实测 `close(timeout_seconds=.01)` 返回后
`thread.is_alive()` 仍为 `True`。与此同时 `mark_unavailable()` 在调用 close 前已从
`_module_services` pop bundle，并吞掉所有 close 异常；后续 `host.close()` 无法再次
取得该 dispatcher。模块已报告 unavailable 时，遗失的 daemon 仍可持有 repository
并继续执行/提交 job。

**Fix:** dispatcher close 必须在超时后显式报告失败，并提供可中断/可撤销的 runner
协议，使 stop/join 有确定终态。host 应先尝试关闭并验证 worker 已死，再从活动所有权
表移除；关闭失败的 bundle 应进入独立 retired/closing 集合，由 shutdown 重试，而不能
静默遗忘。增加真实 `DurableForecastDispatcher` + blocking runner 的 close-timeout、
重复 close 和 host shutdown 回归测试。

## Warnings

### WR-01 [WARNING]：Forecast runner 测试未隔离 POSIX-only 进程组能力

**File:** `backend/tests/forecast/test_runner.py:1605`

**Related:** `backend/tests/forecast/test_runner.py:1628-1676`,
`backend/tests/forecast/test_runner.py:1697-1737`,
`backend/tests/forecast/test_runner.py:1777-1815`

**Issue:** `test_runner_child_ready_handshake_precedes_work_deadline` 使用默认
`raising=True` monkeypatch Windows 不存在的 `os.setsid`；多项 worker/process-group
测试也没有 POSIX marker 或完整 fake，因此生产代码在 Windows 正确 fail-closed 为
`resource_terminated`/`resource_limited` 时，测试却要求 timeout/completed 等 Linux
结果。本轮两个 Forecast 文件运行结果为 67 passed、15 failed；同一并发测试重复运行
还会在 `resource_limited`、`running` 和 SQLite lease invariant 异常间变化，无法作为
跨平台稳定回归信号。

**Fix:** 对纯逻辑单测用独立 fake OS/process-group adapter，并以
`raising=False` 注入 `setsid`/`killpg`；对真实 Linux namespace/process-group 行为加
明确 `skipif(sys.platform != "linux")` marker，并在 Linux CI 单独运行。Windows CI
应断言 fail-closed 结果，而不是复用 Linux terminal 期望。

---

_Reviewed: 2026-07-26T18:38:43Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
