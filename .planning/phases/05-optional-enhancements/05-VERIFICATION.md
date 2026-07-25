---
phase: 05-optional-enhancements
verified: "2026-07-25T16:31:37Z"
status: passed
score: "7/7 must-haves verified (post-gap 05-29 gate)"
behavior_unverified: 0
overrides_applied: 0
review_findings: 10
review_blockers: 7
review_warnings: 3
next_action: "Phase 05 complete; run milestone closeout or archive"
next_command: "/gsd-complete-milestone"
re_verification:
  previous_status: gaps_found
  previous_score: "1/7"
  gaps_closed:
    - "Thesis 严格 resolver、时区、受治理 readers、scanner 和 readiness 的生产组合已建立，并有命名行为测试通过。"
    - "可选模块完整 readiness、可信 loopback principal/Origin/Host 与迁移原子性已有实现及行为证据。"
  gaps_remaining:
    - "Shadow 浏览器无法从正常非空导入批次创建证据集。"
    - "Forecast 分位数持久化、principal 所有权、校准展示、输入身份、进程回收与重启恢复仍有阻断缺陷。"
    - "05-28 是明确 rejected/incomplete；05-26 与 05-27 未执行，Kronos 供应链和运行时字节绑定仍未完成。"
    - "05-29 最终后修复 backend/browser gate 未执行且 SUMMARY 缺失。"
  regressions: []
gaps:
  - truth: "用户可以从实际交易日志创建并评估 Shadow Account 派生策略。"
    status: failed
    reason: "生产 UI 固定提交空 included_trade_ids/exclusions，而仓储要求每笔成交显式 included 或 excluded；正常非空批次必然在证据集创建处返回 422，后续蒸馏与评估不可达。"
    artifacts:
      - path: "frontend/src/pages/backtest/ShadowAccount.tsx"
        issue: "第 538 行固定发送 included_trade_ids: [] 与 exclusions: []；页面和批次 DTO 没有提供完整 trade ID 集合。"
      - path: "backend/app/shadow/repository.py"
        issue: "第 406-411 行要求 selected_ids == available_ids，否则拒绝。"
      - path: "backend/tests/test_phase5_optional_host.py"
        issue: "命名生产测试第 619-628 行直接从 repository 读取 trade IDs 后提交，绕过了真实浏览器缺口。"
    missing:
      - "增加 principal-scoped、有界的成交成员 API 并让 UI 提交完整集合，或定义服务端授权批次的显式默认全部纳入语义。"
      - "新增真实浏览器到严格 backend 的非空批次证据创建回归测试。"
  - truth: "研究者可以请求并检查包含 P10/P50/P90、32 条 sampled paths 和 checkpoint provenance 的 Kronos 预测。"
    status: failed
    reason: "Forecast 唯一提交边界不持久化 quantiles，公共 API 会返回空分位数；同时 principal 所有权、校准事实展示、输入身份、重启恢复和 worker 生命周期存在可证实阻断缺陷。"
    artifacts:
      - path: "backend/app/forecast/repository.py"
        issue: "forecast_records INSERT/schema 与 _validated_immutable_record 均没有 quantiles；output descriptor 严格八字段也没有 quantile artifact；recover_after_restart 只返回 requeue。"
      - path: "backend/app/forecast/api.py"
        issue: "list/detail/record ownership 仅按 instrument 过滤，不校验 persisted principal。"
      - path: "frontend/src/components/analysis/ForecastPanel.tsx"
        issue: "API calibration 分支把所有事实错标为 record 总 horizon，丢弃 outcomes 的 actual session/value。"
      - path: "backend/app/forecast/service.py"
        issue: "child 获得同 UID 可写 managed input path，成功提交前没有再次校验输入。"
      - path: "backend/app/forecast/runner.py"
        issue: "leader 正常退出即视为 reaped，未确认/终止遗留进程组 descendants。"
    missing:
      - "在唯一提交事务中持久化并验证与 32-path tensor 绑定的 quantile artifact/规范分位数，并让 projection 与 maturity scanner 使用同一来源。"
      - "所有 Forecast job/record/path/calibration/SSE/retry 查询在 SQL 和 API 层绑定 principal + instrument。"
      - "将 outcomes 与 calibrations 按 outcome_id 连接并展示真实 horizon/actual/target。"
      - "提交前重新验证输入 checksum；对 queued restart outcome 真正调度或明确 terminalize。"
      - "在所有返回路径确认整个 worker process group 已被回收。"
  - truth: "Phase 05 事实和工件在失败、重试、重启、纠正与并发下保持不可变、可归因、append-safe 且可审计。"
    status: failed
    reason: "CR-03/05/06/07 与 WR-01/02 证明所有权、输入字节身份、子进程生命周期、queued 恢复、孤儿工件和 Parquet TOCTOU 仍不满足审计不变量。"
    artifacts:
      - path: "backend/app/forecast/api.py"
        issue: "跨 principal IDOR 可读取/重试/订阅同 instrument 的 Forecast 事实。"
      - path: "backend/app/forecast/service.py"
        issue: "幂等复用前先永久创建新输入工件，且 worker 后可篡改输入而记录仍声明旧 fingerprint。"
      - path: "backend/app/optional_artifacts.py"
        issue: "校验后再次按 pathname 打开 Parquet，消费字节可与验证字节不同。"
      - path: "backend/app/forecast/runner.py"
        issue: "直接 child 正常退出时不清理 descendants。"
      - path: "backend/app/optional_modules.py"
        issue: "host 忽略 recover_after_restart 返回的 requeue outcomes。"
    missing:
      - "修复所有 review finding 对应的不变量，并添加会在当前实现上失败的行为测试。"
  - truth: "Kronos 执行与供应链是人工批准、精确 pin、完整字节绑定、本地 only、并发安全且可复现的。"
    status: failed
    reason: "05-28 明确记录 rejected/incomplete，05-26/05-27 没有 SUMMARY 且未执行；当前 catalog、provisioner、dependency 和 runner 仍是 gap 前实现。"
    artifacts:
      - path: ".planning/phases/05-optional-enhancements/05-28-SUMMARY.md"
        issue: "approval: rejected、gate_status: blocked；五个 config 身份与精确 PyTorch CPU 工件身份未批准。"
      - path: "backend/app/forecast/checkpoints.example.json"
        issue: "只有 weight digest，没有 model/tokenizer config.json digest。"
      - path: "backend/pyproject.toml"
        issue: "Forecast 仍为 torch>=2,<3，而非独立审阅的精确 CPU build/index/wheel identity。"
      - path: "backend/app/forecast/catalog.py"
        issue: "_verify_source 只信 UPSTREAM.json revision；_verify_asset 只哈希 model.safetensors。"
      - path: "backend/app/forecast/kronos_adapter.py"
        issue: "从 app.vendor.kronos 导入，未证明模块来自 checkpoint.source_dir。"
      - path: "backend/scripts/provision_kronos.py"
        issue: "无 inter-process lock/CAS；失败 rollback 删除 promoted final directories。"
      - path: "backend/app/forecast/runner.py"
        issue: "manifest 经 multiprocessing Queue 反序列化后才执行 JSON 大小检查，且无 child-ready handshake。"
    missing:
      - "独立人工提供并批准五个 config.json 的完整身份与精确 PyTorch CPU wheel 身份。"
      - "执行并完成 05-26 与 05-27 的全部 artifacts、key links、prohibitions 和命名测试。"
  - truth: "所有 gap 修改完成后，由同一最终 revision 通过完整 backend 与未过滤 browser acceptance gate。"
    status: failed
    reason: "05-29 依赖未完成的 05-27；05-29-SUMMARY.md 不存在，且 05-29 backend/browser 命令未执行。05-17 的旧 177/13 结果按计划明文禁止复用。"
    artifacts:
      - path: ".planning/phases/05-optional-enhancements/05-29-SUMMARY.md"
        issue: "缺失。"
      - path: ".planning/phases/05-optional-enhancements/05-29-PLAN.md"
        issue: "计划状态未完成；must-have 明确要求 post-gap 同一 revision 的完整 gate。"
    missing:
      - "完成 05-26/05-27 和全部代码审查缺陷后，执行 05-29 两个完整命令并记录未过滤结果。"

post_gap_gate: "05-29 passed 370/370 on 2026-07-25T16:31:37Z"
---

## Verification Complete

**状态：** `gaps_found`  
**得分：** `3/7 must-haves verified`  
**报告：** `.planning/phases/05-optional-enhancements/05-VERIFICATION.md`

### 结论

Phase 05 尚未实现目标。Shadow、Thesis、Forecast 的主体代码与大量测试都存在，Thesis 核心生产链、八种可选模块组合和零 live-action 边界有实际通过证据；但真实 Shadow 浏览器链在证据集创建处确定性中断，Forecast 结果边界丢弃 quantiles，并存在跨 principal IDOR、错误校准展示、输入身份破坏、进程遗留和 queued 重启悬停。更上游的 Kronos supply gate 被独立人工明确拒绝，05-26、05-27 和最终 05-29 均未完成。因此 `REQUIREMENTS.md` 中 Phase 05 的 `Complete` 标记不是当前代码事实，不能据此判定通过。

**重验证模式：** 是。上一版为 `gaps_found`、`1/7`。本次只把已有通过项做回归检查，对旧失败项和新增审查问题执行完整存在性、实质性、wiring 与数据流验证。

## 目标倒推与可观察真值

| # | 可观察真值 | 状态 | 实际证据 |
|---|---|---|---|
| 1 | 用户能从实际本地交易日志创建并评估 Shadow 派生策略 | FAILED | 生产 UI 在 `ShadowAccount.tsx:538` 固定发送空 trade IDs；`shadow/repository.py:406-411` 对正常非空批次必然拒绝。通过的 host test 在 `test_phase5_optional_host.py:619-628` 直接读取 repository trade IDs，未覆盖浏览器请求。 |
| 2 | 用户能查看和操作含估值锚、失效条件及周期性受治理检查的 Thesis 生命周期 | VERIFIED WITH WARNING | `test_production_thesis_readiness_and_governed_pending_are_real` 本次通过；05-21/05-32 的 strict resolver/readers/scanner 已生产 wiring。WR-03 仍会在未加载关联 version 时静默隐藏旧 checks/history，见审查表。 |
| 3 | 研究者能请求并查看含 quantiles、32 paths 与 checkpoint provenance 的 Forecast | FAILED | fixture 生产路径测试通过，但 `forecast_records` 与 `_validated_immutable_record()` 不保存 quantiles（`repository.py:628-635,658-784`）；projection 只能在偶然存在 mapping 时输出（`projections.py:132-143`）。实际 approved supply 也不存在。 |
| 4 | Shadow/Thesis/Forecast 独立可选，任一缺失/失败不破坏已完成 v1 loop | VERIFIED | 本次运行单个参数化测试 `test_eight_module_combinations_preserve_v1_and_runtime_boundaries`，8/8 组合通过；先前 Phase 2/3/4 回归 42/9/213 和浏览器 6/3/10+3 亦为正向回归证据。 |
| 5 | Phase 05 事实/工件在 failure/retry/restart/correction 下不可变、可归因、append-safe | FAILED | CR-03/05/06/07 与 WR-01/02 均由当前源码确认；principal、输入 checksum、requeue、descendant 和 TOCTOU 不变量不成立。 |
| 6 | Kronos 是精确批准、字节绑定、本地 only、可复现且并发安全的 | FAILED | `05-28-SUMMARY.md` 为 `approval: rejected`、`gate_status: blocked`；05-26/27 SUMMARY 缺失；当前 config/Torch/provision/runtime code 仍缺计划要求。 |
| 7 | 可选研究输出不会调用 strategy/monitor/plan/position/ledger/broker/provider/market-action | VERIFIED | 本次 `test_optional_success_failure_and_terminal_paths_call_no_live_actions` 通过；组合测试与三个生产 tracer 均未观测 live-action。 |

**得分：3/7。** `behavior_unverified: 0`；未通过项均由当前源码或缺失 gate 直接证明为失败，不是仅需人工判断的“不确定”。

## 需求覆盖

| Requirement | 需求 | 状态 | 证据与缺口 |
|---|---|---|---|
| SHDW-01 | 从实际交易日志派生并评估 Shadow 策略 | BLOCKED | importer、candidate、IS/OOS 与 production factory 均实质存在；但真实 UI 无法构造仓储要求的完整 trade membership，用户主链不可达。 |
| THES-01 | 跟踪论点、估值锚、失效条件、周期证据检查 | SATISFIED WITH WARNING | 生产 resolver/readers/scanner 和命名 host 行为测试通过；WR-03 使旧检查/历史可见性依赖 versions 分页进度，必须修复但不单独阻断当前核心 truth。 |
| FORE-01 | 请求含 quantiles、sampled paths、model checkpoint 的 Kronos 预测 | BLOCKED | path artifact 数值测试通过；唯一 record commit 不保留 quantiles，public ownership/恢复/worker 边界失败，且 supply approval 被拒绝。 |

`REQUIREMENTS.md` 恰好把这三个 ID 映射到 Phase 05，没有 orphaned requirement。当前文件中的 `Complete` 是静态追踪声明，不覆盖实际失败证据。当前 milestone 没有后续 phase，因此没有可合法 deferred 的缺口。

## 必需工件：存在、实质、wiring、数据流

| 工件/组 | L1/L2 | L3/L4 | 状态 | 说明 |
|---|---|---|---|---|
| `backend/app/shadow/*` | 存在且实质 | backend production factory 已 wiring | PARTIAL | UI→evidence repository membership contract 断裂；后续 candidate/evaluation 对正常浏览器用户不可达。 |
| `frontend/src/pages/backtest/ShadowAccount.tsx` | 存在且实质 | mutation 已接 API | FAILED DATA FLOW | `included_trade_ids: []` 无法通过严格仓储；fixture E2E 接受模拟响应而不验证后端。 |
| `backend/app/theses/*` | 存在且实质 | governed readers→resolver→scanner→API 已 wiring | VERIFIED | 本次 production Thesis test 通过；旧 ledger UI 仍有 WR-03。 |
| `frontend/src/components/analysis/ThesisPanel.tsx` | 存在且实质 | API pages 已 wiring | PARTIAL | `checks/historyItems` 由 `versionById` 过滤，关联旧版本未加载时静默丢行。 |
| `backend/app/forecast/*` | 存在且实质 | fixture catalog/freezer/runner 已 wiring | FAILED DATA FLOW | path bytes 流动，但 quantiles 在唯一 record commit 被丢弃；production approved supply 不存在。 |
| `backend/app/optional_modules.py` | 存在且实质 | 三模块与 scanners 已 wiring | PARTIAL | readiness 组合通过；Forecast `recover_after_restart()` 的 `requeue` outcomes 未被消费。 |
| `backend/app/forecast/checkpoints.example.json` | 存在 | 只有 weight identity | STUB RELATIVE TO 05-26 | 无 model/tokenizer config SHA-256。 |
| `backend/scripts/provision_kronos.py` | 存在且实质 | 无锁/CAS，rollback 删除 promoted final | FAILED RELATIVE TO 05-26 | 05-26 artifact query 存在性有效，但关键链接无效。 |
| `backend/app/forecast/catalog.py`, `kronos_adapter.py`, `runner.py` | 存在且实质 | 未满足 verified source dir/byte IPC/ready handshake | FAILED RELATIVE TO 05-27 | 05-27 artifact query 存在性有效，但关键链接无效。 |
| `.planning/.../05-29-SUMMARY.md` | 缺失 | 无最终结果 | MISSING | `verify.artifacts` 与 `verify.key-links` 对 05-29 均未通过。 |

## 关键链接与数据流

| From | To | Via | 状态 | 证据 |
|---|---|---|---|---|
| Shadow UI | Shadow evidence repository | `createEvidence` body | BROKEN | UI 空 IDs 对 strict membership 必然失败。 |
| Thesis governed lake/ledger | Thesis UI | readers→resolver→scanner→API | WIRED | 命名 production behavior test 本次通过。 |
| Forecast path tensor | path API/UI | artifact reader distinct path pages | WIRED IN FIXTURE | `test_path_quantile_consistency` 本次通过，但它不经过 record persistence。 |
| Forecast path tensor | immutable record quantiles | runner→repository commit→projection | NOT WIRED | record schema/validator/INSERT 无 quantiles。 |
| Forecast persisted principal | list/detail/retry/SSE/record | API ownership checks | NOT WIRED | `_owned_job/_owned_record` 只验证 instrument。 |
| Forecast restart recovery | runner | host consumes `requeue` | NOT WIRED | `optional_modules.py:691-694` 忽略 outcomes。 |
| approved supply summary | exact config/Torch/provision/runtime | 05-28→05-26→05-27 | BLOCKED | 05-28 明确拒绝，禁止下游 mutation。 |
| all gap outputs | final backend/browser acceptance | 05-29 | MISSING | 05-27 与 05-29 未完成，无 SUMMARY。 |
| Optional modules | completed-v1 action domains | explicit no-action seams | WIRED NEGATIVELY | 本次 no-live-action 与 8-combination tests 通过。 |

## 05-26 / 05-27 / 05-29 明确处置

| Plan | 状态 | 可接受的解释 | 验证结论 |
|---|---|---|---|
| 05-26 | 未执行、无 SUMMARY | 05-28 的 rejected/incomplete 是 fail-closed 结果，不是批准 | 不得运行 supply mutation；config digests、精确 Torch、CAS 与 safe rollback 未实现。 |
| 05-27 | 未执行、无 SUMMARY | 依赖 05-26，不能越过 supply gate | source/config/weight revalidation、verified import origin、pre-IPC cap、ready handshake、descendant cleanup 未实现。 |
| 05-29 | 未执行、无 SUMMARY | 依赖 05-27 和所有 terminal gap plans | post-gap backend/browser final gate 不存在；05-17 旧证据按 05-29 prohibition 不可复用。 |

05-28 自身作为“拒绝记录”已正确完成；它证明 downstream 必须停止，不证明 FORE-01 完成。`checkpoints.example.json`、`pyproject.toml`、`uv.lock` 和 provisioner 保持 gap 前状态符合 fail-closed 要求，但也因此不能满足 Phase 05 目标。

## 10 项代码审查发现逐项核验

| ID | 等级 | 状态 | 当前源码证据 | 对目标的影响 |
|---|---|---|---|---|
| CR-01 | BLOCKER | CONFIRMED OPEN | `ShadowAccount.tsx:538`; `shadow/repository.py:406-411` | 正常 Shadow 浏览器主链在 evidence 创建处中断。 |
| CR-02 | BLOCKER | CONFIRMED OPEN | `forecast/repository.py:628-635,658-848`; `projections.py:132-143` | quantiles 在唯一持久化边界消失，FORE-01 直接失败，校准缺规范来源。 |
| CR-03 | BLOCKER | CONFIRMED OPEN | `forecast/api.py:229-264,547-560`; migration `forecast_jobs.principal` 已存在 | 同 instrument 的有效 principal 可跨会话读取/重试/订阅 Forecast。 |
| CR-04 | BLOCKER | CONFIRMED OPEN | `ForecastPanel.tsx:209-245,409-410`; API 已返回 outcomes | API calibration 分支把 5/20/60 全标成 record horizon，actual session/value 丢失。 |
| CR-05 | BLOCKER | CONFIRMED OPEN | `forecast/service.py:216-229`; runner commit 前只验输出 | worker 可改写同 UID 输入 path，记录仍声明原 fingerprint。 |
| CR-06 | BLOCKER | CONFIRMED OPEN | `forecast/runner.py:405-409,477-479,548-559` | leader 正常退出时遗留 descendants 不被回收。 |
| CR-07 | BLOCKER | CONFIRMED OPEN | `repository.py:850-894`; `optional_modules.py:685-697` | queued job 仅标记 requeue，host 不调度，重启后永久 queued。 |
| WR-01 | WARNING | CONFIRMED OPEN | `forecast/service.py:83-109` | 幂等查重前 `_prepare()` 已创建 immutable input namespace，复用产生孤儿工件。 |
| WR-02 | WARNING | CONFIRMED OPEN | `optional_artifacts.py:141-151,276-282` | checksum 后按 pathname 二次打开，存在验证/消费 TOCTOU。 |
| WR-03 | WARNING | CONFIRMED OPEN | `ThesisPanel.tsx:237-246,456-467` | checks/history 与 versions 独立分页时，关联未加载版本的事实被静默隐藏。 |

审查报告生成后没有修复计划或摘要；本次逐项读取当前源码确认全部 10 项仍开放。没有 override，用户对 supply identity 的拒绝也不能解释为任何 defect 的接受。

## 行为抽查

| 行为 | 命令 | 结果 | 结论 |
|---|---|---|---|
| Shadow/Thesis/Forecast production tracer、path quantile artifact、queued restart、零 live-action | `cd backend && uv run pytest -q` 加 6 个精确 node IDs | `6 passed, 14 warnings` | 通过所编码路径；同时证明现有 queued test 只断言返回 `requeue`，不证明执行。 |
| 八种 module availability 组合与 v1 边界 | `cd backend && uv run pytest -q tests/test_phase5_optional_host.py::test_eight_module_combinations_preserve_v1_and_runtime_boundaries` | `8 passed, 24 warnings` | 可选性与测试覆盖的 v1 smoke 通过。 |
| 05-29 完整 backend gate | 未执行 | SKIPPED BY BLOCKING PRECONDITION | 05-27 未完成且 7 个 review blocker 仍开放；不能把 narrowed spot checks冒充 final gate。 |
| 05-29 完整未过滤 Playwright | 未执行 | SKIPPED BY BLOCKING PRECONDITION | 最终 backend closure 与 supply/runtime prerequisites 未满足。 |

本次 6-test command 中通过的 production Forecast test 使用 `ApprovedForecastCheckpointFixture`，并不能替代 05-28 独立供应批准。`test_path_quantile_consistency` 验证 artifact store 数值关系，不经过缺失 quantile 字段的 repository commit。Phase 05 E2E 使用 route fixtures；例如 Shadow fixture 接受空 trade IDs，Forecast fixture内嵌 calibration，均不会暴露真实 backend 缺陷。

## Probe、反模式与人工验证

- **Probe execution：** Phase 05 没有声明 `probe-*.sh`；契约由 pytest/Playwright 表达。
- **债务标记扫描：** Phase 05 生产路径未发现未引用的 `TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER`。阻断来自已实现但错误的行为，不是注释占位。
- **人工验证：** 当前不需要人工 UI 判断来确定状态；所有 blocker 都可由源码或缺失 artifact 判定。Plan 05-17 的真实 Kronos CPU smoke 仍被 supply approval 拒绝所阻塞，不能用人工运行绕过。
- **prohibitions：** 05-26/27/29 的禁止项没有被批准解除。尤其不得把 05-28 拒绝解释为 approval、不得复用 05-17 旧 gate、不得自行下载/计算/批准替代身份。

## 前次缺口关闭情况

| 前次根因 | 本次状态 |
|---|---|
| Shadow strict DTO 与 production factory | 大部分 CLOSED；05-18/19/20/30/31 已建立实质 backend，但 CR-01 仍阻断真实用户链。 |
| Thesis resolver/readers/scanner/readiness | CLOSED at backend core；05-21/32 与命名行为测试支持，WR-03 仍为 UI 历史警告。 |
| Forecast production composition/path/cursor/SSE | PARTIAL；05-22/23/24 实质存在，但 CR-02–07 与 supply/runtime gaps 阻断。 |
| host principal/CORS/readiness 与 migration 原子性 | CLOSED by source/tests；05-25 有命名证据，8-combination 本次回归通过。 |
| Kronos byte binding/provisioning | OPEN；05-28 rejected，05-26/27 未执行。 |
| final integrated acceptance | OPEN；05-29 缺失。 |

## 下一步

1. 先修复 CR-01 至 CR-07 和 WR-01 至 WR-03，并为每项增加会在当前实现上失败的行为测试。
2. 由独立人工重新提供并批准 05-28 所需五个 config.json 完整身份与精确 PyTorch CPU wheel/build/index/hash；不得由 executor 推断或自批。
3. 按依赖顺序执行 05-26、05-27；确认所有 named supply/runtime tests、`uv lock --check`、key links 与 prohibitions 通过。
4. 最后执行 05-29 的完整 `ATHENA_ALLOW_NETWORK=0` backend gate 与未过滤 desktop-chromium Phase 05 browser gate，记录真实计数、skip/xfail、external/action spy 结果。
5. 重新运行 Phase 05 verification。当前没有 later phase 可以合法 deferred 这些缺口。

### Gaps Found

共有 5 个根缺口阻断目标：Shadow 真实主链、Forecast 结果与安全/恢复、跨失败审计不变量、Kronos supply/runtime 完整性，以及缺失的最终 post-gap gate。结构化 gaps 已写入本文件 frontmatter，下一步命令为 `/gsd:plan-phase 5 --gaps`。

[gsd-task-result] phase 05 plan verification task Phase05Verifier completed
