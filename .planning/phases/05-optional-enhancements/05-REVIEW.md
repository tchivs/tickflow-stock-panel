---
phase: 05-optional-enhancements
reviewed: 2026-07-17T14:09:02Z
depth: standard
status: issues_found
files_reviewed: 34
files_reviewed_list:
  - backend/app/forecast/api.py
  - backend/app/forecast/artifacts.py
  - backend/app/forecast/calendar.py
  - backend/app/forecast/calibration.py
  - backend/app/forecast/input.py
  - backend/app/forecast/projections.py
  - backend/app/forecast/repository.py
  - backend/app/forecast/runner.py
  - backend/app/forecast/service.py
  - backend/app/main.py
  - backend/app/operational/migrations.py
  - backend/app/optional_artifacts.py
  - backend/app/optional_modules.py
  - backend/app/shadow/api.py
  - backend/app/shadow/evaluation.py
  - backend/app/shadow/importer.py
  - backend/app/shadow/production.py
  - backend/app/shadow/projections.py
  - backend/app/shadow/repository.py
  - backend/app/shadow/schemas.py
  - backend/app/shadow/service.py
  - backend/app/theses/api.py
  - backend/app/theses/evidence.py
  - backend/app/theses/repository.py
  - backend/app/theses/scheduler.py
  - backend/app/theses/service.py
  - frontend/src/components/analysis/AnalysisWorkspace.tsx
  - frontend/src/components/analysis/ForecastPanel.tsx
  - frontend/src/components/analysis/ThesisPanel.tsx
  - frontend/src/lib/forecastTask.ts
  - frontend/src/lib/phase5Api.ts
  - frontend/src/lib/queryKeys.ts
  - frontend/src/pages/StockAnalysis.tsx
  - frontend/src/pages/backtest/ShadowAccount.tsx
critical: 7
warning: 3
info: 0
total: 10
findings:
  critical: 7
  warning: 3
  info: 0
  total: 10
---

# Phase 05：代码审查报告

**审查时间：** 2026-07-17T14:09:02Z  
**深度：** standard  
**审查文件：** 34  
**状态：** issues_found

## Summary

对清单中的 34 个生产源文件逐一进行标准深度审查，重点追踪了 API/UI 契约、SQLite 不变量、请求主体与 principal 权限、规范身份、并发与恢复、SSE、子进程/工件清理以及可选模块隔离。供应链拒绝及 Forecast 默认不可用被视为既定的 fail-closed 状态，没有作为缺陷报告。

发现 10 项可证实缺陷：7 项 BLOCKER、3 项 WARNING。最严重的问题会直接中断 Shadow 浏览器主流程、使 Forecast 分位数和校准不可用、跨 principal 暴露 Forecast 数据、让重启后的 queued 任务永久悬停，并允许 worker 污染已绑定的输入身份或遗留子进程。

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01 [BLOCKER]：Shadow 浏览器永远无法从正常导入批次创建证据集

**File:** `frontend/src/pages/backtest/ShadowAccount.tsx:533-539`  
**Related:** `backend/app/shadow/repository.py:406-411`

**Issue:** UI 固定提交 `included_trade_ids: []` 与 `exclusions: []`。仓储却要求纳入批次中的每一笔成交都必须显式出现在 included 或 excluded 集合中，并以 `selected_ids != available_ids` 拒绝请求。批次公共投影和当前页面也没有提供可供用户构造该完整成员集合的 trade IDs。因此，只要正常 completed 批次包含成交，点击“创建新证据集”就必然返回 422，Shadow 的导入→证据→蒸馏生产链路在浏览器端不可达。

**Fix:** 统一契约。推荐增加一个由服务端按已授权批次构造“默认全部纳入”的明确请求语义，或增加 principal-scoped、分页且有界的成交成员 API，让 UI 显式提交完整 included/excluded 清单。不得通过放松仓储的归属与完整成员校验来修复。

### CR-02 [BLOCKER]：Forecast 记录边界丢弃 quantiles，分位数展示与校准均无法成功

**File:** `backend/app/forecast/repository.py:658-784`  
**Related:** `backend/app/forecast/repository.py:786-848`, `backend/app/forecast/calibration.py:217-230`, `backend/app/forecast/projections.py:132-143`, `frontend/src/components/analysis/ForecastPanel.tsx:157-174`

**Issue:** `_validated_immutable_record()` 返回的规范记录没有 `quantiles`；`_validated_output_descriptor()` 又要求输出描述符字段集合严格等于八个固定字段，禁止携带 quantiles 或 quantile artifact 身份。持久化的 `forecast_records` 也没有 quantile 字段。结果是：即使 worker 计算了 P10/P50/P90，唯一提交边界仍会丢弃它们。公共投影只在记录中偶然存在 `quantiles` 时输出，前端因此得到空分位数；成熟度扫描器 `_quantiles()` 同样总是得到 `None`，在实际值出现后只会写入 `unevaluable/missing_quantiles`，永远不能产生真实校准。

**Fix:** 在唯一提交事务中持久化并验证 quantile artifact 描述符及其与已校验 32 路 path tensor 的绑定；读取时从校验过的不可变字节重建 P10/P50/P90，或持久化规范有限值并绑定 source path checksum。随后让 record projection 与 maturity scanner 使用同一规范来源。必须迁移 SQLite 模式和所有调用方，不能在 UI 中伪造分位数。

### CR-03 [BLOCKER]：Forecast API 忽略已持久化 principal，存在跨会话 IDOR 与历史泄露

**File:** `backend/app/forecast/api.py:229-243`  
**Related:** `backend/app/forecast/api.py:547-565`, `backend/app/forecast/repository.py:213-240`, `backend/app/operational/migrations.py:1000-1021`

**Issue:** Forecast job 的规范唯一键和表结构明确包含 `principal`，但列表路由调用无 principal 条件的 `list_jobs()` 后仅按 instrument 过滤；`_owned_job()` 只检查 instrument scope；`_owned_record()` 也只检查 instrument。只要另一个有效会话 principal 可以访问同一 instrument，它就能列出、读取、订阅 SSE、重试其他 principal 的 job，并读取对应 record/path/calibration。Shadow 的同类接口均重复 principal 所有权检查，说明 Forecast 当前行为不是统一的授权模型。

**Fix:** 所有公共 Forecast 查询必须在 SQL 中同时绑定 `principal` 和 instrument；job detail/retry/SSE 应比较 `row.principal == request principal`。record/path/calibration 必须通过 `forecast_records JOIN forecast_jobs` 验证 owner。为列表增加 principal-owned、LIMIT/OFFSET 的仓储方法，避免先取全表再过滤。

### CR-04 [BLOCKER]：Forecast 校准 UI 把所有事实标成记录总 horizon，并丢失实际交易日/实际值

**File:** `frontend/src/components/analysis/ForecastPanel.tsx:209-245`  
**Related:** `frontend/src/components/analysis/ForecastPanel.tsx:409-415`, `frontend/src/lib/phase5Api.ts:544-569`, `frontend/src/lib/phase5Api.ts:786-789`

**Issue:** API 同时返回 `outcomes` 和 `calibration`，但 `ForecastPanel` 只把 calibration 数组传入 `calibrationViews()`。该函数把每一条 calibration 的 horizon 固定写成 `recordValue.horizon`，把 actual session/value 固定成 `null`，并把 target session 固定成整条记录的最后一个 future session。对 60 日记录，5/20/60 日三条事实都会被展示成 60 日，实际值和目标日期也错误。这是审计数据的实质性错标，而非仅显示缺失。

**Fix:** 将 `outcomes` 一并传入 `calibrationViews`，按 `calibration.outcome_id` 连接对应 outcome，使用 outcome 的 `horizon`、`actual_session_id`、`actual_close`；target session 应为 `future_session_ids[horizon - 1]`。若连接缺失或重复，UI 必须 fail closed 显示“校准身份不完整”，不能回退到总 horizon。

### CR-05 [BLOCKER]：Forecast worker 可改写已经绑定的输入工件，提交时不会重新验证

**File:** `backend/app/forecast/service.py:216-229`  
**Related:** `backend/app/optional_artifacts.py:106-116`, `backend/app/forecast/runner.py:274-279`, `backend/app/forecast/runner.py:445-476`

**Issue:** 管理型 Parquet payload 以 `0600` 写入并保持同一进程用户可写；`ForecastService` 把其真实 `managed_path` 放进 child context。worker 与父进程使用相同 OS 用户，因此 worker/native dependency 可以在 pre-spawn `input_revalidate` 之后改写该文件。成功返回后，runner 只校验输出工件并提交数据库，不会再次读取/校验输入 payload。由此可使输出基于被篡改字节，但记录仍声明原 `input_fingerprint`，破坏唯一不可变来源身份。

**Fix:** 不要把可写路径作为子进程权威输入。父进程应打开并校验输入后通过只读 FD/密封对象传递，或给子进程受限副本；无论采用哪种方式，提交前必须对规范输入重新校验 checksum 并与 server-bound identity 比较。仅 `chmod` 不足以隔离同 UID 的 worker。

### CR-06 [BLOCKER]：worker 主进程正常退出时不会清理其遗留进程组成员

**File:** `backend/app/forecast/runner.py:405-409`  
**Related:** `backend/app/forecast/runner.py:477-484`, `backend/app/forecast/runner.py:548-559`

**Issue:** 收到消息后，如果直接 child 已退出，代码直接令 `reaped = True`；finally 也只在 `process.is_alive()` 时调用 `_reap()`。一个 worker 或 native 库可以生成后代进程、返回 manifest、随后让直接 child 正常退出；后代仍留在由 `setsid()` 创建的进程组中，但父进程从不发送 SIGTERM/SIGKILL。即使 manifest 后续验证失败，这些后代也会继续运行，绕过 wall-clock 生命周期和资源回收边界。

**Fix:** 建立显式的 child-ready/process-group 握手并保存受控 PGID；在收到最终消息、异常、超时和所有 return 路径上都终止并确认整个进程组消失，而不是以 leader 的存活状态代表组状态。更稳妥的 Linux 实现可使用 pidfd/cgroup 统一回收 descendants。

### CR-07 [BLOCKER]：重启恢复只标记 queued job 为“requeue”，却从不重新执行

**File:** `backend/app/forecast/repository.py:850-894`  
**Related:** `backend/app/optional_modules.py:685-697`, `frontend/src/lib/forecastTask.ts:191-219`

**Issue:** `recover_after_restart()` 对通过重验证的 queued job 仅返回 `{"action": "requeue"}`，不改变状态、不调用 runner。optional host 调用该方法后完全忽略 outcomes。系统没有独立 Forecast 队列消费者；正常执行只发生在创建请求的同步路径。因此，进程在 job 落库后、`run_job()` 前崩溃时，该 job 重启后会永久保持 queued。前端 SSE 会持续重连/读取，且没有可把同一 queued job推进执行的恢复动作。

**Fix:** 在模块启动恢复阶段，对成功 revalidate 的 queued jobs 逐个交给受全局 lease 保护的 runner；或明确终态化为 interrupted 并要求一个新的显式 retry。恢复结果必须被 host 消费并可观测，不能只返回未使用的描述字典。

## Warnings

### WR-01 [WARNING]：幂等 Forecast 重放会在查找既有 job 前永久创建孤儿输入工件

**File:** `backend/app/forecast/service.py:83-109`  
**Related:** `backend/app/forecast/input.py:196-225`

**Issue:** 每次 `create_or_get_job()` 都先 `_prepare()`，而 freezer 在该阶段立即创建新的 immutable Parquet namespace；之后才用 idempotency key 查询或复用 job。网络不确定后的同 key 重试会反复创建内容相同但无人引用的目录。它们没有数据库引用，也没有任何清理路径，长期运行会造成不可回收的受管存储增长。

**Fix:** 将规范 frame/checksum 计算与最终 artifact promotion 分离：先解析操作身份并查找既有 job；只有新 canonical job 才 promote。若必须先 promote，应在 canonical job 复用或后续失败时，使用 invocation-owned 引用安全地删除未绑定 namespace。

### WR-02 [WARNING]：通用 Parquet 读取在校验后按路径二次打开，存在验证字节与消费字节不一致

**File:** `backend/app/optional_artifacts.py:141-151`  
**Related:** `backend/app/optional_artifacts.py:276-282`

**Issue:** `_read_record()` 对 pathname 计算大小和 SHA-256 后返回 `payload_path`；`load_parquet()` 随后让 Polars 按该路径重新打开文件。在两步之间同 UID 写入者可以替换或改写 payload，使解析的字节并非刚刚校验的字节。Forecast path reader 已采用“读入校验过的 bytes，再从 BytesIO 解码”的正确模式，但通用 store 没有复用该模式。

**Fix:** 一次打开文件并从同一 FD/bytes 完成 stat、digest 和 decode；至少应读取为 bytes、验证后通过 `BytesIO` 交给 Polars，避免 pathname 二次打开。

### WR-03 [WARNING]：Thesis UI 会静默丢弃 API 已返回但对应版本尚未加载的历史/检查行

**File:** `frontend/src/components/analysis/ThesisPanel.tsx:237-246`  
**Related:** `frontend/src/components/analysis/ThesisPanel.tsx:456-467`

**Issue:** `checks` 与 `historyItems` 都用当前已加载的 `versionById` 过滤。版本分页默认只加载前 25 条，而检查/历史是独立 50 条分页；因此 API 返回的旧版本事实会在客户端被静默隐藏，用户继续翻历史页时仍可能看不到它们，直到另外手动加载足够多版本。页面宣称展示“所有版本不可变历史”，实际内容取决于另一资源的分页进度。

**Fix:** 不要以本地版本缓存作为 ledger 行的准入条件。服务端 page DTO 应直接携带安全的 version/instrument 展示身份，前端验证 instrument 后渲染；需要更多版本详情时按 version ID 单独查询，而不是丢弃 ledger 行。

---

_Reviewed: 2026-07-17T14:09:02Z_  
_Reviewer: Claude (gsd-code-reviewer)_  
_Depth: standard_
