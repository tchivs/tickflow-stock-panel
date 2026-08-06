# 概念板块 PIT 历史映射 — v2.2 research

**研究日期:** 2026-08-06
**领域:** 概念板块 point-in-time 归属解析（历史股池视图消除 `current_snapshot` 标注）
**结论:** 上游无法提供历史概念归属 → 只能**前向按日归档**；推荐「平台自有历史概念分区 + as_of 读侧解析 + 缺档回退标注」方案。
**整体置信度:** HIGH（代码锚点全部实测）；上游历史可用性为 [INFERENCE]。

---

## 现状 (current state with code anchors)

### 1. 概念归属今天存在哪里

单一来源 = 扩展数据表 `ext_gn_ths`（同花顺概念），**snapshot 模式**，物理文件为覆盖写单文件：

- `backend/app/services/ext_presets.py:37-64` `_concept_preset()` — `id="ext_gn_ths"`, `mode="snapshot"`, 字段含 `所属概念`（分号拼接），`pull.url="https://files.688798.xyz/ths/concepts.json"`, `schedule_minutes=1440`, **`enabled=False`**。
- `backend/app/services/ext_data.py:214-226` `write_ext_parquet()` — snapshot 分支写 `data/ext_data/{id}/part.parquet`（覆盖写 + 按 symbol 去重）；timeseries 分支才写 `data/ext_data/{id}/timeseries/date=xxx/part.parquet`。
- 实测数据：`data/ext_data/ext_gn_ths/part.parquet`（260KB，全 A 股概念映射，~387 概念 [rps_rotation 文档字符串]）、`data/ext_data/ext_hy_ths/part.parquet`（103KB）；两份 `config.json` 均 `mode:"snapshot"`, `pull.enabled:false`（**手动**点「获取数据」才刷新，`api/ext_data.py:295-310` `POST /api/ext-data/presets/{config_id}/fetch`）。

**读侧 seam（所有消费方共用）:** `backend/app/services/market_overview_builder.py`
- `_ext_files()` :70-75 — snapshot 读 `ext_data/{id}/*.parquet`；timeseries 读 `ext_data/{id}/timeseries/**/*.parquet`（`hive_partitioning=True`，`date=` 目录变 `date` 列）。
- `_read_ext_rows()` :77-117 — **timeseries 只过滤 `date == max()`（取最新），无 as_of 参数**。
- `_dimension_values()` :119-130、`_symbol_keys()` :143-164。

> 关键结论：**读侧已具备读取按日 hive 分区的能力（`_read_ext_rows` + `hive_partitioning`），但缺少 as_of 参数；且没有任何代码写入过历史概念分区。** `data/ext_data/*/timeseries/` 目录全局不存在（glob 零命中）。

### 2. 历史股池快照如何存概念

- 冻结式点快照：`backend/app/services/pool_snapshot.py:29-40` `_SNAPSHOT_ROOT="screener_results"`, `persist_point_snapshot()` :66-122 原子写 `screener_results/date={as_of}/part.json`；payload 只含 `{as_of, computed_at, strategy_version, snapshot_type, schema_version, snapshot_origin, results}`。
- 快照行**不携带概念列**：`run_all_with_hits`（`screener.py:723+`）行集 = enriched 列 + `hit_factors`（服务端聚合 :802-810），无 concept。
- 概念列是**投影时实时 join 当前 ext**：`backend/app/services/pool_hub.py:31-56` `_build_concept_map(data_dir)`（遍历 `ExtConfigStore.load_all()` + `_read_ext_rows` 当前快照）→ `_project_hub()` :83-187 `:123` `"concept_board": concept_map.get(symbol.upper(), [])`。
- 诚实标注：`_project_hub` :182 恒返回 `"concept_attribution": "current_snapshot"`；`build_pool_hub_snapshot()` :225-260 空态 :237-249 同键 + `snapshot_origin:None`，非空态 :259 透传 `snapshot_origin`。API 侧 `api/pool.py:78-113` `/history`（as_of 双校验 :99-107）。
- **前端不渲染该标注**：`frontend/src/lib/api.ts:764-766` 有 `concept_attribution?: string` 类型，但全前端 grep 无任何读取/渲染点；`StockListTable.tsx:49-56` `ConceptChips` :373 直接渲染 `row.concept_board`，无徽标/工具提示。

### 3. 其他消费方（同样的 drift，且**未标注**）

- `market_overview_builder.py:166-203` `_dimension_rank()` — 总览 `concept_rank`/`industry_rank`（含历史 `as_of` 复盘路径）用当前 ext join 历史行情 → 历史复盘概念榜同样漂移且无标注。
- `backend/app/services/rps_rotation.py:60-109` `_load_concept_map_df()` — 概念涨幅 RPS 矩阵把**当前**概念映射 join **历史** `change_pct`（`build_rps_rotation` :111-200）。
- `backend/app/services/concept_rotation_analyzer.py:257-358` `analyze_rotation_stream()` — AI 轮动分析消费 RPS 矩阵。

### 4. 上游能否提供历史概念归属（[INFERENCE]）

- `concepts.json` schema = `[{symbol, name, concepts:[...]}]`，**无 date 字段、无历史端点**（`_flatten_concept_rows` 只取这三个键，丢弃其余）；代码库无任何指向「历史版本概念接口」的路径。→ **当前上游只提供当下快照，不提供历史。**
- TickFlow 不提供 THS 概念/行业成员：grep `backend/app/tickflow/` 仅 `pools.py:100-133` 用 `universes.list()` 里 `SW1_*` 做股池成员回退（申万一级行业 universe id），不是逐股概念映射。→ **TickFlow 也非 THS 概念历史来源。**
- 推论：历史 PIT 只能**前向按日归档**（从功能上线日起 EOD 抓当日映射落盘）；对已存在的历史日期（v2.0/v2.1 快照）**无法回填**——除非引入新数据源（当前无）。这是本领域承重约束。

---

## 方案选项 (options with tradeoffs)

### 选项 A：前向按日历史概念分区 + as_of 读侧解析（+ 缺档回退标注）

在 EOD 持久化 job 里新增「当日概念归档」写 `data/ext_history/gn_ths/date={as_of}/part.parquet`（平台自有根目录，hive 分区）；读侧 `_build_concept_map(data_dir, as_of)` 优先取 `date == as_of` 分区，取不到则回退当前 ext 快照并保留 `current_snapshot` 标注。

- **存储成本:** 概念快照 ~260KB/日（parquet 压缩）；年化 ≈ 260KB × ~247 交易日 ≈ **64MB/年**（~5-6MB/月）。可忽略。
- **数据源可用性:** 复用既有 `ext_presets._fetch_json`/`_flatten_concept_rows`（零新依赖）；只对**未来交易日**有效。
- **回填含义:** 已写快照（功能上线前）无历史分区 → 回退 `current_snapshot` 标注（诚实缺档，非伪造）。RPS/总览共享同一分区后可一并消除未标注 drift。
- **诚实性:** 分区 = 「该交易日可见的已发布归属」；`as_of_snapshot` 显式标注；缺档回退诚实。
- **风险:** 上游更新节奏未知（需上线前探针）；EOD 抓取失败日留缺口 → 回退（诚实但不完美）。

### 选项 B：生成时把概念冻结进每个股池快照

`run_all_with_hits` 生成行时嵌入当日 `concept_board`，随 `part.json` 落盘，天然 as-of。

- **存储成本:** 快照 JSON 已 0.3-2MiB/日（24-RESEARCH R4），概念 chips 增 ~60-320B/行 × 284-1461 行 ≈ 17-470KB/日 → 快照体积最多 +30%；年化累计 ~1GiB 量级。概念是 many-to-many，JSON 非最优载体。
- **数据源可用性:** 同 A，仅未来有效。
- **回填含义:** **已写快照缺该字段**——要么重算（重算用**当前**概念 = 对历史日仍错），要么回退标注 → 与 A 相比无增量收益且更贵。
- **诚实性:** 生成时冻结对当日诚实；但把筛选器/读侧与 ext 抓取耦合（ext 失败日冻结空概念），且快照自包含（无法日后修正）。
- **结论:** 未来日可接受，但**不能修复存量**、体积更大、耦合生成路径 → 不作首选。

### 选项 C：保留 `current_snapshot` + 前端可见免责声明（不新增数据）

把已存在的 `concept_attribution` 字段渲染到历史视图（徽标/工具提示）。

- **成本:** 最低，零存储、零后端改动（仅前端渲染 + 文案）。
- **诚实性:** 让漂移可见，完全诚实。
- **缺陷:** 不产出任何 PIT 标签；与 v2.2 目标（PROJECT.md「消除 current_snapshot 标注」）冲突。只能作为 A 的**回退腿**，不能单独成方向。

---

## 推荐方案 (recommended direction)

**选项 A（前向按日历史概念归档 + as_of 读侧解析），以选项 C 为缺档回退腿。** 理由：

1. **数据优先 + 零新依赖**：归档完全复用 `ext_presets` 的抓取/扁平化 + `write_ext_parquet` 的 timeseries 写路径 + 读侧既有 hive 分区读取能力（`_read_ext_rows` 已支持 `date=` 分区），唯一新增是一个平台自有模块 `concept_history.py`（stdlib + polars，零 npm/pip）。
2. **诚实 provenance 铁律**：分区即「该交易日可见的已发布归属」；缺失日期回退 `current_snapshot` 并保留标注，**绝不静默填充、绝不伪造历史**（POOL-03 精神延续）。存量快照零改动（不重算、不污染）。
3. **架构一致**：`screener_results/`、`premarket_results/` 已是「平台自有根目录」先例；`data/ext_history/gn_ths/` 沿用该模式，不进用户可配置的 `ext_data` 列表（避免双计数与用户配置污染）。
4. **惠及全部消费方**：`pool_hub._build_concept_map`、`market_overview_builder._dimension_rank`、`rps_rotation._load_concept_map_df` 共享同一 seam，一次升级同时消除历史总览/RPS 的**未标注** drift（CONCEPT-06）。

**诚实边界（明确声明）:**
- 历史 PIT 覆盖仅从功能上线日**前向**有效；上线前的快照日期一律回退 `current_snapshot` 标注（本项目不会回填伪造历史）。
- 上游 `concepts.json` 为作者维护的「当下快照」，as-of 精度受其更新节奏约束；若作者多日不更新，各日分区会相同（诚实反映「当日可发布态」，UI 需展示映射生效日期，见 CONCEPT-07）。
- 实时 `/pool/hub` 仍读用户手动刷新的 `ext_gn_ths` 当前快照，可能与同日历史分区存在差异——两者均诚实，属产品可接受范围（见开放问题 OQ-1）。

---

## 需求草案 (verifiable requirement drafts)

### CONCEPT-01: 平台自有历史概念归档（写入侧）
新增 `backend/app/services/concept_history.py`（镜像 `pool_snapshot`：严格 `_DATE_RE` 校验、temp+os.replace 原子写、只写 `data/ext_history/gn_ths/date={as_of}/part.parquet`，字段与 `ext_gn_ths` 一致：symbol/code/股票代码/股票简称/所属概念）。在 `jobs/daily_pipeline.py:973-1015` `_pool_eod_persist` 快照落盘后调用 `concept_history.capture(data_dir, as_of)`（复用 `ext_presets._fetch_json` + `_flatten_concept_rows`）。
- **可验证:** 交易日 D 跑完 `_pool_eod_persist` 后存在 `date=D` 分区且行数 == 当日 `concepts.json` 行数；无数据日诚实 skip 不写文件；抓取失败仅记 warning、**不阻断**快照持久化；grep 确认写路径只出现在该模块。

### CONCEPT-02: as_of 读侧解析
`pool_hub._build_concept_map(data_dir, as_of=None)`：as_of 非空且存在 `date={as_of}` 分区 → 用分区行；否则回退当前 ext 快照。`_project_hub` 透传 as_of（`build_pool_hub_snapshot` 传入快照 `as_of`）。
- **可验证:** 构造历史分区后 `build_pool_hub_snapshot(data_dir, D)["strategies"][i]["rows"][j]["concept_board"]` 等于 D 日映射；无分区时行为与现状逐位一致（17 个既有 `test_pool_hub.py` 回归零改动）。

### CONCEPT-03: 诚实归属状态机
`concept_attribution` 三态：分区命中 → `"as_of_snapshot"`；分区缺失但有当前 ext → `"current_snapshot"`；全无概念数据 → `"unavailable"`。**永不按行混用。** 空态（无快照）保持既有 `"current_snapshot"`（避免破坏 `test_build_pool_hub_snapshot_missing_available_false` 精确 dict 断言）。
- **可验证:** 三态单测各一；`test_build_pool_hub_snapshot_has_concept_attribution`（:486-494）在无分区路径下继续绿。

### CONCEPT-04: 前端可见标注
历史股池视图（`PoolHubPage` 日期导航区 / `StockListTable` 概念列表头）在 `concept_attribution !== "as_of_snapshot"` 时渲染徽标/工具提示「概念归属为当前快照，非该日数据」；`as_of_snapshot` 时显示「概念按当日快照」。`api.ts:764-766` 类型已存在，补充到响应消费。
- **可验证:** Playwright 用例断言 `current_snapshot` 载荷出现徽标文案、`as_of_snapshot` 载荷显示按日文案、徽标不出现于 `as_of_snapshot`。

### CONCEPT-05: 禁止回填伪造
概念历史分区**只**由 `concept_history.capture` 在真实抓取后创建；任何对 `data/ext_history/` 的其它写路径 = 零（AST 守卫）。缺口日期读侧回退 `current_snapshot`，永不合成分区。
- **可验证:** grep 对 `ext_history` 写调用只命中 capture；测试断言「缺分区 → 回退非伪造」；POOL-03 AST 守卫扩展：`concept_history.py` 只写 `ext_history`，`api/pool.py` 仍全 GET 无写。

### CONCEPT-06: 共享 seam 扩展到总览/RPS（后续阶段可拆分）
`market_overview_builder._dimension_rank`（历史 as_of 复盘）与 `rps_rotation._load_concept_map_df` 接受 as_of，历史总览概念榜 / RPS 矩阵同样按日解析，消除当前**未标注** drift。
- **可验证:** `build_market_overview(..., as_of=D)` 的 `concept_rank` 由 D 日分区聚合；RPS 矩阵列与 D 日分区一致。

### CONCEPT-07: 归档 provenance 元数据
分区写入时附加清单（`source_url`、`captured_at`、`fetched_at`、行数、schema_version），读侧透传，UI 可显示「概念数据生效日期」——上游多日不更新时用户可见映射实际更新时间。
- **可验证:** 分区旁 manifest 存在且字段齐全；`/pool/history` 响应携带 `concept_effective_date`（= 分区日期）与 `concept_captured_at`。

---

## 风险 / 开放问题

| 风险 | 等级 | 缓解 |
|------|------|------|
| 上游 `concepts.json` 更新节奏未知（可能数日不变 → 各日分区相同） | 中 | CONCEPT-07 生效日期展示 + 规划期「一周逐日抓取 diff」探针验证 |
| EOD 抓取失败 → 当日缺口 | 低-中 | 回退 `current_snapshot`（诚实）；`captured_at` 留痕；可后续重跑 capture（幂等） |
| 实时 hub 与同日历史分区概念可能不一致（用户手动 ext 刷新节奏） | 低 | 两者均诚实且标注区分；OQ-1 决策 |
| 存量 ~247 个历史日期无法获得 PIT 概念 | 高（范围） | 明确范围 = 前向；缺口回退标注；不伪造 |
| 写路径新增 → POOL-03 AST 守卫需扩展（E2 现只放行 `screener_results`） | 低 | 守卫按模块拆分：`concept_history` 只写 `ext_history` |
| 存储增长 ~64MB/年 | 低 | 相对 enriched 湖（51MiB）+ 快照（79-693MiB）可忽略；压缩路径已有 |

**开放问题:**
- **OQ-1:** EOD 归档是否同时自动刷新 `ext_gn_ths` 当前快照（让实时 hub 也逐日更新），还是保持「用户手动刷新 ext」的既有设计？—— 产品决策，影响 CONCEPT-01 范围。
- **OQ-2:** 行业（`ext_hy_ths`）是否本期同建归档，还是仅概念优先？股池视图只展示 `concept_board`，行业仅用于总览 `industry_rank` → 建议随 CONCEPT-06 一起做。
- **OQ-3:** 规划阶段需实测 `concepts.json` 是否逐日变化（一周探针），以校准 CONCEPT-01 抓取策略（每日强制 vs 内容 diff 后写）。

---

## 关键锚点 (exact anchors for planning)

| 锚点 | 位置 | 用途 |
|------|------|------|
| `ext_presets._concept_preset` | `backend/app/services/ext_presets.py:37-64` | 概念表定义（snapshot, 上游 URL, enabled=False） |
| `write_ext_parquet` / `rows_to_parquet` | `backend/app/services/ext_data.py:214-226` / ~:600 | timeseries 写路径复用点 |
| `_read_ext_rows` / `_ext_files` | `backend/app/services/market_overview_builder.py:77-117` / :70-75 | 读侧 hive 分区能力（需加 as_of） |
| `_build_concept_map` | `backend/app/services/pool_hub.py:31-56` | 概念 join 入口（升级为 as_of） |
| `_project_hub`（concept_board + attribution） | `backend/app/services/pool_hub.py:83-187`（:123, :182） | 投影核心，attribution 状态机落点 |
| `build_pool_hub_snapshot` | `backend/app/services/pool_hub.py:225-260` | 历史投影入口，透传 as_of |
| `GET /pool/history` | `backend/app/api/pool.py:78-113` | 历史取池 API（as_of 双校验） |
| `_pool_eod_persist` | `backend/app/jobs/daily_pipeline.py:973-1015` | EOD 钩子（归档调用点） |
| `_pool_eod_persist` job 注册 | `backend/app/jobs/daily_pipeline.py:1131-1140` | 调度确认（mon-fri, 管道后 +5min） |
| `run_pool_backfill` | `backend/app/services/pool_backfill.py:57-96` | 回填不写概念分区（维持） |
| `persist_point_snapshot` / `_SNAPSHOT_ROOT` | `backend/app/services/pool_snapshot.py:29-40` :66-122 | 快照根目录先例（平台自有根模式） |
| `_dimension_rank`（overview 版） | `backend/app/services/market_overview_builder.py:166-203` | CONCEPT-06 总览侧 |
| `_load_concept_map_df` | `backend/app/services/rps_rotation.py:60-109` | CONCEPT-06 RPS 侧 |
| `ConceptChips` / 概念列表头 | `frontend/src/components/pool-hub/StockListTable.tsx:49-56` :373 | CONCEPT-04 前端落点 |
| `PoolHubPage`（历史视图 / DateNavigator） | `frontend/src/pages/PoolHubPage.tsx` | CONCEPT-04 徽标位置 |
| `concept_attribution` 类型 | `frontend/src/lib/api.ts:764-766` | 已存在，需消费 |
| 归属标注测试 | `backend/tests/test_pool_hub.py:479-494` | 状态机兼容性基线 |
| 概念数据实测 | `data/ext_data/ext_gn_ths/part.parquet`（260KB）/ `config.json` | 存储/结构事实 |

---

## Sources

- 代码锚点全部为本仓库实测（grep/read），置信度 HIGH。
- 上游历史可用性、TickFlow 无 THS 概念、更新节奏为 [INFERENCE]（基于 schema 与代码路径缺证），规划阶段需一周探针验证（OQ-3）。
