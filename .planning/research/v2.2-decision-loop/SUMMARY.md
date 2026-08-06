# 研究合成摘要:AthenaQuant v2.2 决策闭环与历史纵深

**项目:** AthenaQuant
**里程碑:** v2.2 决策闭环与历史纵深
**研究日期:** 2026-08-06
**研究输入:** CONCEPT-PIT.md / BACKTEST-AUCTION.md / MONITOR-PREOPEN.md / RECAP-AUCTION.md
**置信度:** MEDIUM-HIGH（四份研究均以仓库实读代码 + 磁盘实测为据；唯一不可验证项 = 外部实时竞价源可得性与上游数据节奏，已统一标 [INFERENCE]）

---

## Executive Summary

v2.2 在 v2.1（盘前预览 `premarket_results`、历史存档、自选联动，Phase 24-27）基础上，把既有竞价资产（历史股池快照、盘前预览、`kline_auction` 湖、9 个竞价/盘前策略族）接入**决策闭环**：历史概念归属按日解析（消除 `current_snapshot` 标注）、竞价/盘前策略获得历史验证路径、盘前预览进入监控告警、竞价信号进入盘后复盘。四个候选领域**全部研究确认可行（IN）**，且共享同一条铁律——**零新增运行时依赖、POOL-03 零执行权、诚实 provenance/fail-closed**。研究结论高度一致：缺口不是"缺库"或"缺依赖"，而是**数据治理与诚实标注**——四份研究各自独立得出"空数据必须诚实空态、缺失必须显式标注、派生绝不冒充真值"。

核心数据现实决定交付形态：`kline_auction` 湖当前 **0 分区**且无历史回填路径，`screener_results` **0 快照**，`premarket_results` **MISSING**（尚无任何预览文件），而 `kline_daily_enriched` 已有 **248 分区**。因此竞价验证（BT）与竞价复盘（REV）的"真实竞价列"部分只能是**条件式交付**（湖有数据即亮、湖空诚实空态），今天即可落地的是只读信号质量报告 + 派生/EOD 分支验证 + `open_gap` 恒真档。概念 PIT（CONCEPT）与盘前监控（MON）不依赖外部源历史，**数据可用性自给**，是本里程碑确定性最高的两个领域。

推荐做法：**数据优先 + 独立可交付**，按 Phase 28-31（延续 v2.1 顺序编号）四阶段推进——**Phase 28 概念板块 PIT → Phase 29 竞价策略历史验证 → Phase 30 盘前监控告警 → Phase 31 竞价复盘**。最大风险与一致护栏：复盘默认调度 **15:10 早于竞价同步 15:30** 的时序缺口（REV R1，需 roadmap 决策是否把默认时间移到 15:35+）；`kline_auction` 空湖使真列验证与真实竞价活跃度暂时无法交付（BT/REV 数据闸门）；上游 `concepts.json` 更新节奏未知（CONCEPT 需一周探针）；盘前 `change_pct` 计算口径未核实（MON R1）。

---

## 范围裁决 (Scope Verdict)

四个候选领域**全部 IN**，但各自有明确的边界（哪些在、哪些延后、哪些明确否决）：

| 领域 | 裁决 | 证据 | 边界 |
|------|------|------|------|
| **概念板块 PIT** (CONCEPT) | **IN** | `ext_gn_ths` 为 snapshot 模式覆盖写单文件（`ext_presets.py:37-64`，`enabled=False` 手动刷新）；读侧 `_read_ext_rows` 已具备 hive 分区读取能力但无 as_of 参数（`market_overview_builder.py:77-117`）；`concept_attribution` 恒返回 `"current_snapshot"` 且前端不渲染（`pool_hub.py:182`；全前端 grep 无消费点） | **前向按日归档**（CONCEPT-01）；上线前的 ~247 个历史日**无法回填**（上游无历史端点，[INFERENCE]）→ 回退 `current_snapshot` 标注；行业归档（`ext_hy_ths`）为开放问题 OQ-2（建议随 CONCEPT-06） |
| **竞价策略历史验证** (BT) | **IN（只读报告形态）** | 回测装载 seam `_load_panel_inner` 物理无竞价列（`ENRICHED_STORAGE_SCHEMA` 15 列，`parquet.py:48-58`）；`kline_auction` 0 分区；无历史竞价回填代码；4 个 `requires_auction_data` 策略回测空池 | **只读信号质量报告**（BT-01..06）；**BT-07 全量竞价回测显式延后 v2.3+**；选项 C（快照重放）为互补非主路径（`screener_results` 0 快照，无法测漏报） |
| **盘前监控告警** (MON) | **IN** | v2.1 已交付盘前预览（09:26 job + `premarket_results/` + `provisional/degraded/probe`）；监控规则引擎 4 类规则 + cooldown + 持久化 + SSE + 飞书全链路现成（`monitor.py:329`、`quote_service._evaluate_monitors:1169-1353`）；输入形状错位（JSON payload vs DataFrame）但条件匹配机制可复用 | **新增 `preopen` 规则类型**（MON-01..07）；**选项 B（复用 type=strategy 指向盘前行）明确否决**——`_strategy_pools` 池 diff 基线污染 09:30 盘中首轮 |
| **竞价复盘** (REV) | **IN** | 复盘为纯 AI 大盘复盘、无竞价维度（`_SYSTEM_PROMPT` 8 节模板无竞价节，`market_recap.py:40-109`）；`build_market_overview` 返回键无任何竞价列；`open_gap` 是 enriched 存储列恒在（唯一恒真竞价代理） | **确定性数据面板内嵌复盘 + 可选 AI 点评（默认关）**（REV-01..04）；REV-05 独立只读端点为 **P2 可选**；**时序缺口必须决策**（默认 15:10 < 竞价同步 15:30） |

**数据前置事实（四份研究一致，磁盘实测 2026-08-06）:** `kline_daily_enriched/` 248 分区、`kline_auction/` 0 分区、`kline_minute/` 0 分区、`screener_results/` 0 快照、`premarket_results/` MISSING。所有"真实竞价列"消费方（BT 真列验证、REV 真实竞价活跃度）都被 `kline_auction` 空湖数据闸门限制为**条件式交付**。

---

## 架构决策要点

### 跨领域 seam（每个领域触碰的既有接缝）

```
pool_hub._build_concept_map (CONCEPT)     → 概念 join 入口升级为 as_of 读侧解析
BacktestEngine.load_panel (BT)            → 回测装载 seam 物理无竞价列 → 新只读注入原语，不动受治理面板
MonitorRuleEngine.evaluate (MON)          → 新 preopen 规则类型 + evaluate_premarket() 输入适配
recap_market_stream / review 调度 (REV)   → done 前追加确定性面板 delta + 调度时间决策
```

1. **CONCEPT seam — `pool_hub._build_concept_map(data_dir, as_of=None)`:** 读侧已有 hive 分区能力（`_read_ext_rows`），唯一缺 as_of 参数。EOD 钩子 `_pool_eod_persist`（`daily_pipeline.py:973-1015`）后追加 `concept_history.capture`，写平台自有根 `data/ext_history/gn_ths/date={as_of}/part.parquet`（镜像 `screener_results/`/`premarket_results/` 平台自有根先例，不进用户可配置的 `ext_data`）。**一次升级同时惠及** `pool_hub` / `market_overview_builder._dimension_rank`（历史复盘概念榜）/ `rps_rotation._load_concept_map_df`（RPS 矩阵）三处消费方，消除**未标注** drift（CONCEPT-06）。
2. **BT seam — `_load_panel_inner`（engine.py:202-276）:** 快路径 `get_enriched_range` 与慢路径 `scan_enriched_parquet` 均无 auction 列；`requires_auction_data` 策略由 `StrategyEngine.run` 短路空池（`engine.py:345-348`）。选项 A 新增**独立只读研究原语** `attach_auction_columns_range`（`app/research/` 或 `auction_columns.py`），严格镜像 `attach_auction_columns` 的 probe×分区双闸门 + PIT-safe 分母（`volume.shift(1).rolling_mean(5).over("symbol")`），产出 enabled-dates 元数据；**不触碰** frozen panel scope/checksum。
3. **MON seam — `MonitorRuleEngine`（monitor.py:329）:** 复用 `_apply_scope` / `_build_condition_mask` / `_match_conditions` / `_last_fire` cooldown；新增 `evaluate_premarket(payload)` 把 `payload["results"]` 全部策略 rows 抽 symbol 去重建 DataFrame（`change_pct` 置 None 诚实缺列）；**绝不触碰** `_strategy_pools` / `_latest_strategy_results`。调度：`_premarket_pool_preview` **尾段**（persist 之后，同一 `_run_tracked` 单飞内）接线，免二次读盘、免新增 job 竞态（MON-03）。
4. **REV seam — `recap_market_stream`（market_recap.py:253）:** 在 `done` 前追加确定性面板 delta（与 AI 内容同流 → SSE/归档/飞书三跳全收，前端零改动）；`_build_user_prompt` 用可选参数（默认 None）向后兼容。新只读装配服务 `auction_recap.py` 消费**冻结资产**（`load_premarket_snapshot` + `attach_auction_columns` + enriched），**绝不调 `run_all_with_hits`**（REV-01 验收 4）。

### 共享护栏（四领域共同遵守的平台律）

| 护栏 | 内容 | 覆盖 |
|------|------|------|
| **POOL-03 零执行权** | 所有新模块/端点禁止 import 执行族（broker/order/trade/execution/portfolio/position/account/transaction）；AST 守卫扩展（镜像 `test_pool_hub.py` E3 形） | `concept_history.py`（只写 `ext_history`）、BT 验证端点（GET-only 零写零执行）、`evaluate_premarket` 模块（import 白名单）、`auction_recap.py`（无写路径） |
| **strategy_cache single-as_of 完整性** | 任何非「最新日 EOD」路径不得写 `strategy_cache.json`（v2.0/2.1 已锁：回填/盘前绝不 write_cache） | CONCEPT 归档走独立 `ext_history`；MON 评估只读 `premarket_results`；BT/REV 纯读 |
| **诚实 provenance / fail-closed** | 空数据诚实空态、缺失显式标注、派生绝不冒充真值、分支永不混用 | 详见下方「诚实性护栏」逐领域 |

**零新增运行时依赖（四领域全部确认）:** 全部复用既有栈——`ext_presets` 抓取/扁平化、`write_ext_parquet` timeseries 写路径、Polars 分区读、规则引擎、复盘流；纯 stdlib + polars，无 npm/pip 新增。

---

## 特性分组 (Features as Milestone Phases)

### Phase 28: 概念板块 PIT 历史映射（CONCEPT-01..07）
**Rationale:** v2.2 里程碑命名目标「消除 current_snapshot 标注」的数据主体；零外部依赖（复用 `ext_presets` 现有抓取，仅未来交易日有效）；研究置信度最高（代码锚点全部实测）；共享 seam 一次升级同时消除总览/RPS 的未标注 drift。存储成本可忽略（~260KB/日 ≈ 64MB/年）。
**Delivers:** `concept_history.py` 前向按日归档 + EOD 钩子 + `pool_hub` as_of 读侧解析 + `concept_attribution` 三态状态机（`as_of_snapshot`/`current_snapshot`/`unavailable`）+ 前端可见徽标 + provenance manifest（CONCEPT-07）。
**Addresses:** PROJECT.md「概念板块 PIT 历史映射」；STATE Blockers 遗留。
**Avoids:** 上游无历史端点（前向归档，不伪造回填）；缺档回退 `current_snapshot`（诚实）；写路径新增 → POOL-03 AST 守卫按模块拆分。
**Research flag:** **需要 `--research-phase`** —— OQ-3 一周逐日抓取 diff 探针校准抓取策略（每日强制 vs 内容 diff）；OQ-1（EOD 归档是否同时自动刷新 `ext_gn_ths` 当前快照）；OQ-2（行业归档本期做否）。

### Phase 29: 竞价策略历史验证（BT-01..06）
**Rationale:** 决策闭环的「信号→结果」实证缺口；只读 GET 报告形态满足 POOL-03 零执行；**湖空时仍诚实可交付**（4 个真列策略诚实报空，5 个派生/EOD 策略给出历史验证并显式标 branch）。与 Phase 28 无依赖，可独立交付。
**Delivers:** `GET /api/research/auction/validation` 信号质量报告 + `attach_auction_columns_range` 向量化注入原语 + 前瞻口径锁死（BT-04，无 lookahead 无静默填充）+ 分支标注互斥（BT-05）+ 数据覆盖报告（BT-01 `data_gate`）。
**Addresses:** PROJECT.md「竞价策略历史验证」；9 个竞价/盘前策略无验证路径。
**Avoids:** 空湖误导（`data_gate:"empty"` 200 非 404/500）；真列/派生/EOD 分支混用（branch 永不混用）；受治理回测 seam 污染（不碰 frozen panel）。
**Research flag:** **需要 `--research-phase`（中）** —— `attach_auction_columns_range` 向量化与 enabled-dates 语义、`BACKTEST_MAX_SERVER_DAYS=186` guard 与 248 天 enriched 的区间冲突、以及「上游是否提供历史竞价数据」这一**数据源可行性问题**（超出代码范围，需 Researcher 与数据源评估）。

### Phase 30: 盘前监控告警（MON-01..07）
**Rationale:** 决策闭环的另一半「盘前异动/竞价强度」告警；复用 v2.1 盘前预览（数据已具备）+ 统一规则引擎全链路，新增面 = 规则类型 + 输入适配 + 调度尾段。选项 B 池基线污染已明确否决，方案收敛。
**Delivers:** `preopen` 规则类型（白名单字段 `open_gap`/`auction_volume`/`auction_amount`/`auction_volume_ratio`/`auction_unmatched_amount`，禁 EOD 列）+ `evaluate_premarket()` + 09:26 预览 job 尾段接线 + 事件带 `provisional/degraded/probe` + 游客脱敏 + 规则 API/前端选项。
**Addresses:** PROJECT.md「盘前/竞价监控」。
**Avoids:** MON R1（`change_pct` 口径未核实 → 白名单禁 EOD 列 + DataFrame 置 None）；R4（否决选项 B 的池基线污染）；R2（噪音：独立 rule_id cooldown + `severity=info` 默认）；R3（degraded 静默不报 → UI 透传 degraded 状态）。
**Research flag:** **需要 `--research-phase`（高）** —— R1 需实施时核实 pre-open enriched 帧 `change_pct`/`close` 计算口径（`indicators/pipeline.py compute_enriched_today` + quote_service preopen flush）；调度决策（尾段 vs 独立 09:27 job）；`scope=sector` 是否支持。

### Phase 31: 竞价复盘（REV-01..04，REV-05 可选 P2）
**Rationale:** 决策闭环的收口——把竞价信号质量回填进**唯一盘后交付物**（SSE 实时 + 归档 + 飞书），确定性面板零 AI 成本、诚实性最高；与既有复盘链路集成（`done` 前追加 delta）。依赖 `premarket_results` + `kline_auction` + enriched，横跨最多数据资产，**并携带调度时间决策**，放最后。
**Delivers:** `auction_recap.py` 确定性装配（真实竞价活跃度 + 恒真 `open_gap` 快照 + 盘前信号质量三块）+ 诚实标注/降级（REV-02）+ 复盘集成（REV-04）+ 可选 AI 点评（默认关，带「只引用切片数值 + 缺失明说」护栏）。
**Addresses:** PROJECT.md「竞价复盘」。
**Avoids:** REV R1（时序缺口 → 面板内建 `pre_eod` 诚实降级，不假装有竞价数据）；R3（AI 幻觉 → 默认关 + 面板为准）；R5（历史 as_of 的 probe 闸门语义 → 历史日走分区存在性主闸门）；R6（预览 `change_pct ≈ open_gap` 漂移 → 信号质量 join EOD enriched 口径）；R10（策略集合漂移 → 表由预览实际有行的策略驱动，不硬编码）。
**Research flag:** **需要 `--research-phase`（高）** —— 复盘默认调度时间决策（15:10 vs 15:35+，需 roadmap 层定）；R8（AI 失败时面板是否兜底交付，改变报告契约）；R9（`_build_user_prompt` 签名变更向后兼容）；REV-05 是否纳入。

### Phase Ordering Rationale
- **数据优先 + 独立可交付:** 四领域依赖图基本独立（CONCEPT 依赖 ext 抓取+EOD 钩子；BT 依赖回测 seam+空湖；MON 依赖 v2.1 premarket_results；REV 依赖 premarket_results+kline_auction+复盘链路）。排序依据：**确定性最高、零外部数据门、覆盖里程碑命名**的 CONCEPT 先行；BT 只读报告零写路径、湖空也诚实可交付，紧随其后；MON 数据自给（预览由 v2.1 09:26 job 产出）、范围中等，第三；REV 横跨最多资产 + 携带调度决策 + 与复盘交付物最耦合，最后。
- **跨阶段共享纪律:** 所有新写路径（`concept_history` 写 `ext_history`）与所有评估入口（MON/BT/REV）都以 POOL-03 AST 守卫按模块拆分 + 不写 `strategy_cache`/`screener_results`/`premarket_results` 为硬约束；诚实语义在每阶段数据入口定死（`as_of_snapshot`/`data_gate`/`provisional`/`pre_eod`），消费端只读透传。
- **与 v2.1 衔接零破坏:** 全部新端点/存储为**新增**——`data/ext_history/`、`/api/research/auction/validation`、`preopen` 规则类型、复盘面板 delta；既有 `/api/pool/hub`、`/api/pool/premarket`、`strategy_cache` 单 as_of、`screener_results`、`monitor_rules` 契约全部不变（回归锁）。

### Defer / 条件式汇总
- **BT-07 全量竞价回测（含 frozen panel 竞价列 provenance + minute_confirm_fn 接入）:** **显式延后 v2.3+**（待 `kline_auction` 湖有足够历史分区）。
- **真实竞价活跃度（BT 真列验证 / REV `real_auction_activity`）:** **gate** 在 `kline_auction` 分区存在且 probe available；空湖 → BT `data_gate:"empty"`、REV 块诚实省略并注明。
- **CONCEPT 历史回填:** **defer（范围外）**——上游无历史端点，上线前历史日一律 `current_snapshot` 回退。
- **REV-05 独立只读端点:** **P2 可选**，不阻塞核心交付。
- **MON 的「预览基线 vs 实际开盘」对比** 与 **REV 的「盘前异动告警直喂复盘」**: 跨领域可选衔接，属 v2.2 后续或 v2.3。

---

## 诚实性护栏 (Honesty Guardrails per Domain)

| 领域 | fail-closed 行为 | 触发条件 | 表达方式 |
|------|------------------|----------|----------|
| **CONCEPT** | 缺 `date={as_of}` 分区 → 回退当前 ext 快照 + 保留 `current_snapshot` 标注；全无概念数据 → `unavailable`；**永不按行混用、永不合成分区、绝不回填伪造** | 上游无历史端点；EOD 抓取失败日留缺口；上线前历史日无分区 | `concept_attribution` 三态 + 前端徽标 + manifest（`source_url`/`captured_at`/`fetched_at`）+ `concept_effective_date` |
| **BT** | 湖空或 probe 非 available → 200 `{data_gate:"empty", coverage:0, strategies:[], probe}`（非 404/500）；无分区日不进 enabled-dates（**绝不做 null-as-present**）；结果日缺行 → 计 `n_missing_outcomes` 不 0 填/前向填充；真列策略湖空 `n_dates==0` 不落 derived | `kline_auction` 0 分区；probe 不可用；停牌/退市 T+1 缺失 | `data_gate` + `branch: real\|derived\|eod`（互斥）+ `coverage` + `n_missing_outcomes` |
| **MON** | 竞价列缺失 → `_build_condition_mask` 无命中 → 不告警；`degraded=true` 或 probe 非 available → 竞价列依赖规则 fail-closed 无命中，但**不静默**——事件/UI 透传 degraded；预览 `available:false` → 不评估不告警 | 09:26 帧无竞价列；probe 不可用；预览空态 | 事件字段 `provisional=true`/`degraded`/`probe` + 前端「盘前·非最终」徽标 + 白名单禁 EOD 列（`change_pct` 置 None） |
| **REV** | `kline_auction/{as_of}` 无分区或 probe 非 available → `real_auction_activity` 整块省略 + 注明；预览缺失 → 信号质量块省略 + `no_premarket_preview`；复盘时刻 < 竞价同步（默认 15:10）→ `pre_eod` 诚实标注「盘后竞价同步未完成」；预览 `degraded` → 「盘前信号基于派生因子」 | 空湖；预览缺失；调度早于 15:30；probe 不可用 | `data_completeness: {full, no_auction_lake, no_premarket_preview, pre_eod, partial}` + 每块来源标注 + 顶部「确定性数据，非 AI 生成」标识 |

---

## 开放决策 (Open Decisions for Orchestrator)

| # | 决策 | 选项 | 影响 | 来源 |
|---|------|------|------|------|
| 1 | **复盘默认调度时间** | (a) 移到 15:35+（竞价同步 15:30 + 股池持久化 15:35 之后）→ 三块全亮；(b) 保持 15:10 默认 + 面板 `pre_eod` 诚实降级（建议用户在竞价同步后重跑） | REV-01/02/04 验收与默认体验 | RECAP R1 / REV-02 |
| 2 | **BT-07 延后确认** | 显式 defer 到 v2.3+（本期只做只读报告） | Phase 29 范围 | BACKTEST 推荐 |
| 3 | **BT 数据源可行性（历史竞价）** | 上游是否提供历史竞价？若否，真列验证在湖有数据前只能诚实空（产品预期校准） | Phase 29 交付形态 | BACKTEST 风险 1 |
| 4 | **tier-2 派生/EOD 分支验证** | 湖空时报告是否仍对 5 个派生/EOD 策略给出历史验证（推荐：是，显式标 branch） | BT-03/05 验收口径 | BACKTEST 选项 A |
| 5 | **CONCEPT 前向范围接受** | 确认 ~247 个上线前历史日无法获得 PIT 概念、一律 `current_snapshot` 回退为产品可接受（不伪造回填） | CONCEPT-01/05 范围 | CONCEPT 诚实边界 |
| 6 | **MON-01 `change_pct` 语义核实** | 实施时核实 pre-open enriched 帧 `change_pct`/`close` 计算口径（可能=0 或=open_gap）；未核实前白名单禁 EOD 列 | MON-01/02 规则字段 | MONITOR R1 |
| 7 | **CONCEPT OQ-1: EOD 归档是否同时自动刷新 `ext_gn_ths` 当前快照** | (a) 自动刷新（实时 hub 也逐日更新）；(b) 保持用户手动刷新 ext 既有设计 | CONCEPT-01 范围 | CONCEPT OQ-1 |
| 8 | **CONCEPT OQ-2: 行业归档本期做否** | (a) 概念优先，行业随 CONCEPT-06 一起做；(b) 本期概念+行业同时建归档 | CONCEPT-06 范围 | CONCEPT OQ-2 |
| 9 | **premarket_results/backfill 交织** | `screener_results` 当前 0 快照（Phase 24 回填未跑）；BT 选项 C 快照重放需先回填——本期是否需要 Phase 24 回填先行以启用快照重放补充视角？ | BT-03 与 Phase 24 衔接 | BACKTEST 风险 6 |
| 10 | **REV-05 独立端点** | 本期纳入（P2）还是延后；REV-08 AI 失败兜底面板（改变报告契约）是否要 | Phase 31 范围 | RECAP REV-05 / R8 |
| 11 | **前端约束** | CONCEPT-04（PoolHubPage/StockListTable 徽标）与 MON（规则编辑器/alerts 页）触碰前端，但**均不触碰 `frontend/src/pages/Watchlist.tsx`**（用户预存改动，off-limits 铁律保持） | 规划/执行护栏 | 全局约束 |

---

## 置信度评估

| 领域 | 置信度 | 说明 |
|------|--------|------|
| 概念 PIT (CONCEPT) | **HIGH**（上游历史可用性 [INFERENCE]） | 代码锚点全部实测（`ext_presets`/`ext_data`/`pool_hub`/`market_overview_builder`/`rps_rotation`/`daily_pipeline`）；唯一不可验证 = 上游 `concepts.json` 历史与更新节奏 → 前向归档 + 一周探针（OQ-3） |
| 竞价验证 (BT) | **MEDIUM** | 回测 seam/双闸门/9 策略列依赖全部直接观测；湖覆盖率当前环境实测；生产部署后竞价湖覆盖速度为 [INFERENCE]；历史竞价数据可得性超出代码范围 |
| 盘前监控 (MON) | **MEDIUM-HIGH** | 引擎/调度/预览/投递链路全部源码核验；R1 `change_pct` 盘前帧口径未核实（[INFERENCE]） |
| 竞价复盘 (REV) | **MEDIUM-HIGH** | 复盘链路与数据装配全部源码核验 + 磁盘实测；外部实时竞价源 [INFERENCE]；时序缺口已量化（15:10 < 15:30） |

**总体置信度:MEDIUM-HIGH。** 四领域全部以仓库实读代码 + 磁盘实测为据；残余不确定项均集中在**外部数据源**（实时竞价 probe、`concepts.json` 节奏、历史竞价可得性），已统一按 [INFERENCE] + 判定条件处理，不假装可得。

### Gaps to Address
- **外部实时竞价源（probe）:** `kline_auction` 空湖 + 无历史回填 → BT 真列验证与 REV 真实竞价活跃度**当前不可交付**；判定条件 = 湖分区存在且 probe available；不满足则诚实空态/省略。
- **历史竞价数据可得性（BT 风险 1）:** 超出代码范围的数据源问题，需 Researcher 与数据源评估；若产品期望「今天就验证极速抢筹」，这是数据缺口而非代码缺口。
- **复盘调度时间决策（REV R1）:** roadmap 层必须定（15:10 vs 15:35+），否则默认调度下真实竞价活跃度恒为 `pre_eod` 降级。
- **`concepts.json` 更新节奏（CONCEPT OQ-3）:** 规划期一周逐日抓取 diff 探针；若多日不变，各日分区相同（诚实反映「当日可发布态」，UI 需展示映射生效日期）。
- **盘前 `change_pct` 口径（MON R1）:** 实施时读 `compute_enriched_today` + quote_service preopen flush 核实；未核实前规则白名单禁 EOD 列。
- **`screener_results`/`premarket_results` 空数据现状:** Phase 24 回填未跑 + 09:26 预览尚未在真实交易日运行过 → BT 选项 C 快照重放、MON/REV 的盘前信号消费在无数据日诚实空态；验收全用 fixture/mock。
- **历史 as_of 的 probe 语义（REV R5）:** 历史分区存在但当前 probe 非 available 时会被 `attach_auction_columns` 第一闸门挡住——REV-01 需明确「T 日走 attach 双闸门、历史日走分区存在性主闸门」。
- **POOL-03 AST 守卫词汇扩展:** 新增写路径（`ext_history`）与评估模块（research 端点/preopen 评估/auction_recap）须按模块拆分守卫，避免与既有 `screener_results` 单目录守卫冲突。

---

## Sources

### 领域研究（本里程碑，全部为仓库实读代码 + 磁盘实测）
- **CONCEPT-PIT.md** — `ext_presets.py:37-64`、`ext_data.py:214-226`、`market_overview_builder.py:70-117`（`_ext_files`/`_read_ext_rows`）、`pool_hub.py:31-56,83-187,225-260`、`api/pool.py:78-113`、`pool_snapshot.py:29-40,66-122`、`rps_rotation.py:60-109`、`concept_rotation_analyzer.py:257-358`、`daily_pipeline.py:973-1015,1131-1140`、`pool_backfill.py:57-96`、`frontend/.../StockListTable.tsx:49-56,373`、`lib/api.ts:764-766`、`tests/test_pool_hub.py:479-494`；磁盘实测 `data/ext_data/ext_gn_ths/part.parquet`（260KB）、`ext_hy_ths`（103KB）
- **BACKTEST-AUCTION.md** — `backtest/engine.py:191-276`、`backtest/strategy.py:89-115,522-598`、`frozen_panel.py:44-73`、`parquet.py:48-58`（`ENRICHED_STORAGE_SCHEMA`）、`services/auction_columns.py:89-151`、`auction_probe.py:139`、`services/screener.py:306-314,722-812`、`strategy/engine.py:345-348`、9 个 builtin 策略源文件、`services/pool_snapshot.py:39-183`、`pool_backfill.py:26-96`、`api/backtest.py:29`（`BACKTEST_MAX_SERVER_DAYS=186`）、`walkforward.py`；磁盘实测 `kline_daily_enriched/` 248、`kline_auction/` 0、`kline_minute/` 0、`screener_results/` 0、`premarket_results/` 0
- **MONITOR-PREOPEN.md** — `strategy/monitor_rules.py:29,101-241`、`strategy/monitor.py:329,497,617-700,736-900,903`、`services/quote_service.py:1146-1353`、`operational/repository.py:345-391`、`api/alerts.py:18-46`、`api/monitor_rules.py:59,82-143`、`jobs/daily_pipeline.py:966-970,1017-1061,1145-1153`、`services/premarket_pool.py:30-100`、`premarket_snapshot.py:48-101`、`services/auction_columns.py:90-131`、`api/pool.py:118-176`、`services/guest_masking.py:20`、`main.py:625-703`、builtin pre_open 策略白名单参照
- **RECAP-AUCTION.md** — `jobs/daily_pipeline.py:760-957`（`_run_scheduled_review`/`_stream_review_with_retry`/`_register_review_job`）、`services/preferences.py:433-457`（默认 disabled,15:10,强制下限 15:00）、`api/settings.py:1425-1465`、`services/market_recap.py:40-109,177-227,253-356`、`market_overview_builder.py:345-580`、`market_recap_reports.py`、`api/market_recap.py`、`ai_provider.py`、`services/auction_columns.py:89-150`、`auction_probe.py:28-56`、`auction_sync.py:32-35,96-137`、`premarket_snapshot.py:29-88`、`premarket_pool.py:32-74`、`pool_snapshot.py:93-102`、`screener.py:723,245,30,205`、`api/pool.py:79-93,117`、`api/auction_history.py`、`api/data.py:626-641`、`tests/test_pool_hub.py:858-913`、`tests/test_auction_probe.py`、`frontend/.../Review.tsx`、`lib/reviewStore.ts`；磁盘实测同 BACKTEST

### 规划文档（交叉核验里程碑目标与编号）
- `.planning/PROJECT.md`（v2.2 目标「决策闭环与历史纵深」、四个 target features、零新增运行时依赖）、`.planning/STATE.md`（4 个 Deferred Items 映射到 v2.2 研究；Phase 28+ 顺序编号；v2.1 止于 Phase 27）

---
*研究合成完成:2026-08-06*
*Ready for roadmap: yes*
