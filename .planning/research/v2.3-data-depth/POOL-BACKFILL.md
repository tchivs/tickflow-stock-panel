# 股池历史回填 OQ-1 + PIT 纵深 — v2.3 research (Domain B)

**研究日期:** 2026-08-06
**领域:** 股池历史回填 OQ-1（回填补充）+ 概念 PIT 与回填快照的联动
**结论预览:** 回填全链路已存在（v2.1 Phase 24 交付）且**沙箱内可确定性执行**；OQ-1 的"补充"= 真正跑一次回填把 248 个 enriched 日变成快照分区。premarket_results 缺失 = 部署门禁 + 实时数据依赖（诚实不可沙箱模拟）。概念 PIT 对存量历史日不可回填（上游无历史），回填后的历史池概念标注诚实回退 `current_snapshot`。
**整体置信度:** HIGH（全部代码锚点本仓库实测 + 磁盘实测）；回填耗时/存储量级为 [INFERENCE]（沿袭 24-RESEARCH）。

---

## 1. OQ-1 定义与来源

**OQ-1 = "无批量回填被补充"（回填 job 已建、从未执行）**，来源 v2.1 里程碑审计 tech_debt：

- `v2.1-MILESTONE-AUDIT.md:27` — `"OQ-1 无批量回填被补充(回填 job 仍绝无回填: 手动 run_all 历史 as_of 写 cache 指针污染已修复 D6)"`。即 Phase 24 交付了回填 job（HIST-01..04 全 Complete），但 **screener_results 湖仍 0 分区** —— "补充"= 把历史缺口真正跑出来。
- 历史沿革（命名注意，仓库里多个 OQ-1 同名异义）：
  - `v2.0-MILESTONE-AUDIT.md:20` — v2.0 的 OQ-1：**无回填 job** 是有意决策（EOD 前向，历史缺口手动 run_all 填充）。
  - `22-RESEARCH.md:572` — v2.2 期 22 的 OQ-1：历史日回填策略，OPEN → 推荐不做，若产品要求全历史覆盖需加"逐日期 run_all、耗时与分区数线性"的回填 job。Phase 24 即落实此推荐。
  - `v2.2-MILESTONE-AUDIT.md:22` — v2.2 的 OQ-1（不同义）：盘前 live-API close 值 @09:26 语义待部署验证。
  - `CONCEPT-PIT.md` OQ-1（不同义）：EOD 归档是否自动刷新 ext 当前快照（决策：否）。
  - 本项目（v2.3 股池历史回填）引用的是 **v2.1 审计的 OQ-1**，语义 = 回填 gap closure。

**Phase 24 建了什么**（`v2.1-phases/24-historical-archive/24-01-PLAN.md` must_haves + `24-01-SUMMARY.md`）：
- `pool_snapshot.persist_point_snapshot(..., origin="backfill")` — snapshot_origin 诚实 provenance（HIST-02）。
- `services/pool_backfill.py::run_pool_backfill` — 逐日重放服务（HIST-01）：缺口集/升序/限界/进度/合作取消/失败继续/**绝不 write_cache**（D2 byte-identical 断言锁死）。
- `api/pipeline.py` `POST /backfill` 触发端点（D1：operator-only，单飞 + 执行槽 + 后台 executor，镜像 extend_history）。
- `api/screener.py` run_all D6 修复（latest-only write_cache，快照总是落盘）。
- **未完成项 = 无任何真实执行**：sandbox 无 cron、端点需 operator 触发、EOD job 从不运行 → `screener_results/` 仍 0 分区（本次磁盘实测）。这就是 OQ-1 残留。

## 2. 回填入口（file:line）

| 层 | 位置 | 说明 |
|----|------|------|
| 触发端点 | `backend/app/api/pipeline.py:90` `pool_backfill`（POST /api/pipeline/backfill，body 校验 :103-121，单飞 job_store :128-135，`run_in_executor` 后台化 :143-147） | operator-only（非 GET → 游客自动 401，main.py 认证中间件）；**绝不放 /api/pool/***（POOL-03 E4 GET-only 守卫锁死，`api/pool.py:1-5`） |
| 回填服务 | `backend/app/services/pool_backfill.py:30` `run_pool_backfill`（缺口集 = `list_backfill_gaps` :57-59，升序/限界 :61-68，逐日 `run_all_with_hits` + `persist_point_snapshot(origin="backfill")` :72-89，合作取消 :73-77，失败继续 :91-93） | 铁律：绝不 import/调用 strategy_cache（D2）；不 import 执行族模块（E1/E3 形自洽） |
| 缺口单点 | `backend/app/services/pool_snapshot.py:157` `list_backfill_gaps`（= `list_enriched_dates` :144 − `list_snapshot_dates`） | 幂等：含 part.json 的日期自动跳过；enriched root 缺失 → `[]` |
| 快照写入 | `backend/app/services/pool_snapshot.py:52` `persist_point_snapshot`（origin ∈ {eod,backfill,manual} :67-69，temp+os.replace 原子写） | schema_version=1；旧 payload 缺字段读侧缺省 eod（:333 pool_hub 透传） |
| 共享核心 | `backend/app/services/screener.py:723` `run_all_with_hits`（PRESET :745 + engine 策略 :746-750，逐策略 try/except 继续 :790-803，`build_factor_hits`/`attach_factor_hits` :808-812） | EOD/手动 run_all/回填共用单条代码路径（POOL-04） |
| 策略引擎 | `backend/app/strategy/engine.py:299` `StrategyEngine.run`（filter_history 分支 :320-334；`requires_auction_data` 短路 :345-347 → 竞价列缺席返回空 StrategyResult，fail-closed） | 确定性：as_of + precomputed + overrides 全读湖/配置，无实时依赖 |
| EOD 前向（非回填） | `backend/app/jobs/daily_pipeline.py:973` `_pool_eod_persist`（write_cache :1005 + persist :1006-1009 + `concept_history.capture` :1017） | 只向前生成；与回填并发写同分区由 `_run_tracked` 单飞 + 执行槽互斥防护 |
| 手动 run_all | `backend/app/api/screener.py`（D6：仅 `svc.latest_date()==as_of` 才 write_cache；快照总是落盘） | 单日补缺口保留路径 |

**无 CLI 脚本**：`backend/scripts/` 现有 cleanup_halt_days / probe_concept_drift / probe_phase13 / provision_kronos / sync_kronos / verify_phase5_final_gate，无回填脚本。24-RESEARCH 曾评估选项 C（operator CLI）并否决（无 HTTP 进度、与 job_store 脱节，`24-RESEARCH.md:133`），推荐 A（端点）。v2.3 若要 CLI 属**新增**（见 §6）。

## 3. 沙箱内确定性回填可行性裁决

**裁决：可行（IN）。** 248 个 enriched 日全部可确定性重放为 `screener_results/date={d}/part.json`（origin="backfill"）。

### 3.1 数据前置（全部满足，本次磁盘实测）
- `data/kline_daily/` 248 分区、`data/kline_daily_enriched/` 248 分区（15 列，无 auction 列）。回填日期集 = enriched 分区 glob（`pool_snapshot.py:144-155`），候选日必然有 enriched 数据 → 无"空湖日"。
- `kline_auction/` 0 分区 → `_attach_auction` probe×分区双闸门 fail-closed（`screener.py:299-329`：列缺席诚实返回）；`requires_auction_data` 策略短路为空（`engine.py:345-347`）。**确定性**：每次重放同日结果一致（无实时源扰动）。
- 策略参数源：PRESET 内置（`screener.py:30+`）+ engine 策略（builtin/custom/ai 目录，`main.py:555-558`）+ 用户覆盖 `user_data/strategy_overrides/`（`strategy/config.py:16-19,61-66`；沙箱为空 → 默认参数，确定性）。
- warm 路径：启动 `_refresh_enriched` 预计算全历史 `_enriched_history_cache`（`tickflow/repository.py:461,552-556`；`get_enriched_history` :937-946），filter_history 策略 `_load_enriched_history` 基本 0ms 命中（`screener.py:405-413` 区域，24-RESEARCH:82）。

### 3.2 执行 token / POOL-03 守卫交织
- `_EXECUTION_TOKEN` 是**测试侧 AST 正则**（如 `test_pool_hub.py:858-861`：`broker|order|execution|trade|portfolio|watchlist|...`），约束的是**零执行只读面**：`api/pool.py`（E4 GET-only，:1-5）、`pool_hub.py`、`pool_snapshot.py`（E3 不 import strategy_cache，:14-15）、auction 只读族、concept_history（E1/E3 形）。
- **回填路径不需要也不存在运行时 token**：回填属 operator 执行面（与 EOD job 同类），本就调用 `run_all_with_hits`。守卫对回填的约束是**结构性**的：触发端点放 `api/pipeline.py`（非 pool 面，E4 不破）、`pool_backfill.py` 不 import strategy_cache（D2/E3，byte-identical 测试 `test_backfill_never_touches_strategy_cache`）、只写 `screener_results`（E2）。POOL-03 守卫 E1-E6 全绿即为合规证明（24-01-SUMMARY）。
- 沙箱内跑回填 = 起服务后 POST /backfill（有 strategy_engine → 全策略集；engine=None 直调服务 → 仅 PRESET，更快）。两者均确定性。

### 3.3 运行时与存储（[INFERENCE]，沿袭 24-RESEARCH）
- 单日成本 ≈ `_compute_enriched_full`（~5000 symbols × 150 日窗口重算，估 **5-30s/日**）；filter_history 策略因 repo 缓存基本免费。**247 日顺序 ≈ 20-120 分钟**（`24-RESEARCH.md:83`，R2 :352）。
- 存储 ≈ **0.3-2 MiB/日 → 248 日 ≈ 79-693 MiB**（`24-RESEARCH.md:354`，R4）。沙箱磁盘实测 enriched 湖 ~51MiB 量级，快照翻倍量级可接受但需确认余量。
- 无跨日 warmup 复用（`_history_cache` 按日 key 不同、`_compute_enriched_full` 不缓存）→ **升序是正确基线**（D5 已编码），真正摊销需改 seam（未来优化，非本期）。

### 3.4 幂等性
- `list_backfill_gaps` 自动跳过已有 part.json 的日期（`pool_snapshot.py:157-163`）；重跑全量 → `requested:0`。
- 原子写（temp + os.replace）无 .tmp 残留；同 as_of 幂等覆盖（`pool_snapshot.py:84-95`）。
- 失败日记录 `failed_dates` 并继续，终态如实反映部分失败（`pool_backfill.py:91-93`）；合作式取消（job failed 即停，:73-77）。
- 快照携带 `snapshot_origin:"backfill"` + `strategy_version`（回填时刻策略集指纹，`pool_snapshot.py:166-185`）→ 诚实 provenance，重算产物非伪造（R3）。

### 3.5 硬 blockers
- **无硬阻塞**。软约束：全量 248 需 20-120 分钟 operator 批（max_days ≤ 500 已允许，:121）；`strategy_version` 反映回填时刻策略集（若后续改策略需重跑，语义诚实）；沙箱磁盘余量（79-693 MiB）。
- 前端消费链路已通：`GET /api/pool/dates`（快照日期 glob）+ `GET /api/pool/history?as_of=`（`api/pool.py:78-113`）→ `build_pool_hub_snapshot`（`pool_hub.py:294-333`，available:false 诚实空态 :312-321，snapshot_origin 透传 :332-333）。

## 4. premarket_results 缺失 — 诚实缺口（不可沙箱模拟）

**结论：缺失 = 部署门禁 + 实时数据依赖，无确定性沙箱路径，诚实记录。**
- 唯一创建方 = 09:26 job `_premarket_pool_preview`（`daily_pipeline.py:1024-1075`，注册 :1168-1173，id=`premarket_pool_preview` :969）→ `premarket_snapshot.persist_premarket_snapshot`（:1063）写 `data/premarket_results/date={T}/part.json`（`premarket_snapshot.py:47-48`）。
- **部署门禁**：scheduler 仅在非 fixture_mode 启动（`main.py:118` fixture_mode 判定；`main.py:514-520` 才 `start_scheduler`）；沙箱从不跑 cron（约束既定事实：EOD/09:26/15:40 job 均不执行）。
- **即使手动调**：`build_premarket_preview`（`premarket_pool.py:30-90`）以 as_of=今日 T 读 enriched 缓存/分区 —— 沙箱 EOD 从未跑 → 今日无 enriched → `available:false` 诚实空态（:71-77，:40-42 注释"盘前不存在 → 空帧 → available:false"）；且盘前语义需真实 09:15-09:25 竞价数据 + probe 判定（degraded 标注 :86）。→ **无确定性沙箱产盘前快照的路径**。
- 磁盘实测：`data/premarket_results/` **目录不存在**（`[ -d ]` MISSING；与 screener_results 空目录存在形成对照 —— repository 只占位 screener_results 一类 root）。
- 前端已有诚实消费：`/api/pool/premarket` 空态（`api/pool.py:119-` 注释"盘前结果湖独立 root"；frontend 盘前视图空态 + 15:35 EOD 回退）。**v2.3 对本项 = 记录 + 维持现状，不产出。**

## 5. 概念 PIT 与回填快照的联动评估

**部分成链（PARTIAL）：回填让"池成员"历史真实；概念标签对存量日诚实回退，PIT 只对部署后的前向日生效。**
- 读侧已就绪：`build_pool_hub_snapshot` 传 `as_of=snap["as_of"]`（`pool_hub.py:330`）→ `_build_concept_map(data_dir, as_of)`（:61-141）优先 `concept_history.read_partition(data_dir, "gn_ths", as_of)`（:82）→ 命中则 `as_of_snapshot` + effective_date/captured_at（:112-115，:251-253）；未命中回退当前 ext 快照 `current_snapshot`/`unavailable`（:135-141）。
- 写侧只前向：`ext_history/` 分区仅由 `concept_history.capture` 在真实 EOD 创建（`daily_pipeline.py:1017`；`concept_history.py:171-214`；`_HISTORY_ROOT="ext_history"` :33）。**沙箱 `data/ext_history/` 目录不存在**（本次实测）。
- **不可回填的根因**（v2.2 research 已定，`CONCEPT-PIT.md` §4）：上游 `concepts.json` schema 无 date 字段、无历史端点 → 无历史版本可回填；`capture_from_upstream`（`concept_history.py:217-273`）只做 OQ-3 探针（一周逐日 diff，`backend/scripts/probe_concept_drift.py`），把当前快照标成历史日期 = **伪造历史（CONCEPT-05 禁止）**。
- **因此**：回填 248 个历史快照后，`/pool/history?as_of=D` 概念标注 = `current_snapshot`（诚实但非 PIT）；只有部署后真实交易日 EOD 才会逐日前向累积 `ext_history` 分区，让 D 日查看变成真 `as_of_snapshot`。sandbox 无法模拟这一链（诚实答案：否）。

## 6. v2.3 范围建议

| 项 | 裁决 | 内容 | 工作量 |
|----|------|------|--------|
| (a) 确定性回填子集验证 | **IN（核心）** | 沙箱内对 5-10 日子集跑通现有 `POST /api/pipeline/backfill`（或 `run_pool_backfill` 直调）→ 验证 `part.json`（origin=backfill）+ strategy_cache byte-identical + `GET /pool/history` 渲染 + 幂等重跑 requested:0；全量 248 门控于运行时（20-120 分钟 operator 批，可 max_days 分块 + 合作取消） | S（复用现有服务，零新依赖，~1 计划） |
| (b) OQ-1 gap closure 补充 | **IN（与 a 同一交付）** | 定义"OQ-1 完成 = screener_results 覆盖 enriched 全缺口"的验收口径 + 运行记录（job 输出/快照计数）；可选新增 `backend/scripts/pool_backfill.py` operator CLI（直调 run_pool_backfill + on_progress + data_gate 诚实输出 + 幂等，不 import 执行族/strategy_cache，不碰 POOL-03 面）——CLI 为新增面，需守卫自查（E1/E3 形） | S（CLI ~80-150 行，可选） |
| (c) premarket 诚实记录 | **OUT（维持现状）** | 文档注明 premarket_results 需真实部署 + 实时竞价数据；无沙箱产物 | 0 |
| 概念 PIT 纵深 | **OUT（仅文档）** | 存量日概念 = current_snapshot 诚实回退；PIT 前向链已由 v2.2 Phase 28 交付，sandbox 不可验证（OQ-3 探针部署后跑） | 0 |
| 文档 | 随 (a)/(b) | research doc 本文件 + features 对账（可选） | S 内 |

**推荐：(a)+(b) 合并为单一 v2.3 phase**：子集验证作为 in-sandbox 验收（可执行、可复现），全量回填作为部署后 operator 操作指引（含进度/取消/幂等/失败继续语义）。**明确不做**：premarket 模拟、概念历史伪造回填、新数据源。

## 7. 风险

| 风险 | 等级 | 缓解 |
|------|------|------|
| 回填耗时：248 日 ≈ 20-120 分钟 [INFERENCE]（单日 5-30s） | 中 | 子集先行 + max_days 分块 + 后台 executor 请求零阻塞 + 合作式取消 + 升序基线；实测远慢 → 共享 warmup 帧优化（改 seam，单日语义不变，24-RESEARCH R2） |
| 存储：79-693 MiB（248 日，0.3-2 MiB/日 [INFERENCE]） | 低-中 | 回填前核对磁盘余量；膨胀路径 = JSON→Parquet/压缩（R4） |
| POOL-03 守卫交织 | 低（已锁） | 触发面只在 api/pipeline.py；pool_backfill 不 import strategy_cache/执行族；只写 screener_results；E1-E6 + D2 byte-identical 测试回归全绿后再验收 |
| 与 EOD/手动 run_all 并发写同分区 | 中 | job_store 单飞 + try_acquire_run_slot 互斥 + 原子幂等覆盖（T-24-01-06） |
| strategy_version = 回填时刻策略集指纹 | 低 | snapshot_origin=backfill + 指纹留痕；策略变更后需重跑（诚实重算语义，R3） |
| 空湖/空态诚实性 | 低 | 快照 results 空策略 total=0 保留；读侧无快照 → 200 available:false；data_gate:"empty" 模式既有先例（auction_validation D-02） |
| 概念 PIT 存量缺口（~248 日无 PIT 概念） | 高（范围已定） | 明确 = 前向；回退 current_snapshot 标注；绝不伪造（CONCEPT-05） |

## 8. 关键锚点索引

| 锚点 | 位置 |
|------|------|
| OQ-1 tech_debt 定义 | `.planning/milestones/v2.1-MILESTONE-AUDIT.md:27`；前史 `v2.0-MILESTONE-AUDIT.md:20`、`22-RESEARCH.md:572` |
| Phase 24 交付与未完成 | `v2.1-phases/24-historical-archive/24-01-PLAN.md`（must_haves）、`24-01-SUMMARY.md`、`24-RESEARCH.md:83,133-136,352-354` |
| 回填端点 | `backend/app/api/pipeline.py:90-148` |
| 回填服务 | `backend/app/services/pool_backfill.py:30-93` |
| 缺口单点/快照写/指纹 | `backend/app/services/pool_snapshot.py:52,144,157,166` |
| 共享核心 | `backend/app/services/screener.py:723`（run_all_with_hits）、`:245,299,354`（loaders）、`backend/app/strategy/engine.py:299,345-347` |
| EOD 前向 + 概念归档钩子 | `backend/app/jobs/daily_pipeline.py:973,1017` |
| 09:26 盘前 job + persist | `backend/app/jobs/daily_pipeline.py:1024,1063,1168-1173`；`backend/app/services/premarket_pool.py:30-90`；`premarket_snapshot.py:47-48` |
| 调度部署门禁 | `backend/app/main.py:118,514-520` |
| 概念 PIT 读侧 as_of | `backend/app/services/pool_hub.py:61-141,330`；`concept_history.py:171,217,275` |
| 上游无概念历史 | `.planning/research/v2.2-decision-loop/CONCEPT-PIT.md` §4（[INFERENCE]） |
| v2.2 tech_debt（前向归档 + OQ-3 探针） | `.planning/milestones/v2.2-MILESTONE-AUDIT.md:28-29,85` |

---

*研究者: ResearcherV23B · 2026-08-06 · 只读研究，未执行回填*
