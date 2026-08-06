# 概念板块 PIT 历史映射 — Phase 28 实现研究

**里程碑:** v2.2 决策闭环与历史纵深
**阶段:** Phase 28（CONCEPT-01..07）
**研究日期:** 2026-08-06
**输入:** `.planning/research/v2.2-decision-loop/CONCEPT-PIT.md` + 仓库实读代码（全部锚点本轮复核）+ 写路径 dry-run 实测
**结论置信度:** HIGH（代码锚点全部实测；上游 `concepts.json` 更新节奏仍为 [INFERENCE]，见 OQ-3 探针）

---

## 1. 现状（本阶段复核后的代码事实）

### 1.1 概念/行业当前只存在「当前快照」单文件

| 表 | id | mode | 磁盘 | 行数 | 列 |
|---|---|---|---|---|---|
| 概念 | `ext_gn_ths` | snapshot | `data/ext_data/ext_gn_ths/part.parquet`（260,465 B） | 5,542 | `股票代码/股票简称/所属概念/symbol/code` |
| 行业 | `ext_hy_ths` | snapshot | `data/ext_data/ext_hy_ths/part.parquet` | 5,542 | `股票代码/股票简称/所属同花顺行业/symbol/code` |

- `backend/app/services/ext_presets.py:37-64` `_concept_preset()` — 字段 `所属概念`（分号拼接），`pull.url=https://files.688798.xyz/ths/concepts.json`，**`enabled=False`**（手动点「获取数据」才刷新；`api/ext_data.py` `POST /presets/{config_id}/fetch`）。
- `backend/app/services/ext_data.py:467-591` `write_ext_parquet` — snapshot 分支覆盖写 `ext_data/{id}/part.parquet`；timeseries 分支写 `ext_data/{id}/timeseries/date={snap}/part.parquet`（symbol 去重 + `cast_df_to_schema`）。
- 已确认：`data/ext_data/*/timeseries/` **全局不存在**（glob 零命中），`data/ext_history/` 不存在。

### 1.2 读侧 seam 与缺 as_of

- `backend/app/services/market_overview_builder.py:74-80` `_ext_files()` — snapshot 读 `ext_data/{id}/*.parquet`；timeseries 读 `ext_data/{id}/timeseries/**/*.parquet`（`hive_partitioning=True`）。
- `:82-117` `_read_ext_rows()` — **timeseries 只过滤 `date == max()` 取最新，无 as_of 参数**；返回 `[dimension_field, *symbol_cols]` 投影行。
- `:121-230` `_dimension_values()` / `_symbol_keys()` / `_dimension_field()` — 概念/行业维度识别与 join 键提取（`symbol`/`code`/`股票代码`/`代码`）。
- `:243-315` `_dimension_rank(rows, repo, kind, limit, level)` — 用**当前** ext join 传入行（历史 as_of 复盘同样如此 → 未标注 drift）。

### 1.3 股池投影与归属标注

- `backend/app/services/pool_hub.py:38-56` `_build_concept_map(data_dir)` — 遍历 `ExtConfigStore.load_all()` + `_read_ext_rows` 当前快照 → `{SYMBOL_UPPER: sorted[概念]}`。**无 as_of 参数。**
- `:96-187` `_project_hub()` — `:97` `concept_map = _build_concept_map(data_dir)`；`:123` `"concept_board": concept_map.get(symbol.upper(), [])`；`:182` 恒返回 `"concept_attribution": "current_snapshot"`。
- `:225-267` `build_pool_hub_snapshot(data_dir, as_of, ...)` — 空态 `:246` 返回 `concept_attribution: "current_snapshot"` + `snapshot_origin: None`（精确 dict 断言，**不得改动**）；非空态 `:252-267` `_project_hub(...)` 后透传 `snapshot_origin`。
- `build_pool_hub(data_dir, as_of=None, ...)` — 空缓存 `:210` 返回 `{"as_of": None, "updated_at": None, "strategies": [], "resonance_count": 0}`（**精确 dict，无 attribution 键**）；有缓存时 `:212-222` 走 `_project_hub`。

### 1.4 EOD 钩子与调度

- `backend/app/jobs/daily_pipeline.py:973-1015` `_pool_eod_persist()` — **同步函数**；`:992` `as_of = svc.latest_date()`（`date` 对象）；`:1001` `data_dir = repo.store.data_dir`；`:1006-1011` `strategy_cache.write_cache` + `pool_snapshot.persist_point_snapshot(...)` 落在 `if results:` 块内。**概念归档钩子插在 `persist_point_snapshot` 之后、同一 `if results:` 块内。**
- `:1131-1140` job 注册 `pool_eod_persist`：mon-fri，管道完成 +5min，`_run_tracked` 单飞（同步执行）。

### 1.5 POOL-03 AST 守卫现状（`backend/tests/test_pool_hub.py:857-963`）

- `_EXECUTION_TOKEN`（:858）正则：`broker|order|execution|trade|portfolio|watchlist|position|account|transaction|下单|委托`。
- `_WRITE_PATTERNS`（:868-875）：`open(...,"w"/"wb"/"a")`、`write_parquet`、`os.replace`、`unlink(`、`mkdir(`。
- 守卫形态：E1 无执行 import（:895）；E2 `pool_snapshot` 只写 `screener_results`（:920，写函数必须引用 `_SNAPSHOT_ROOT` 常量）；E3 不引用 strategy_cache（:949）；E4 pool.py 仅 GET（:905）；E5 无计算触发（:960）；E6 响应无执行词汇（:999）。
- `test_build_pool_hub_has_no_write_path`（:913）—— `pool_hub.py` **不得出现任何写路径**。新增 `concept_history.read_partition`（返回 `list[dict]`）不破坏它；`pool_hub` 内新增逻辑**必须保持零写**（不引入 polars 写、`os.replace`、`mkdir`）。

### 1.6 写路径 shape 实测（dry-run，2026-08-06）

对当前 `ext_gn_ths` 快照执行「读 → 写 hive 分区 → hive 读回」dry-run（写入 `/tmp`，未触碰仓库数据）：

- 快照 5,542 行；写入 `ext_history/gn_ths/date=2026-08-06/part.parquet` 后 `hive_partitioning=True` 读回自动追加 `date` 列（**polars `Date` dtype**），`date==max` 过滤得全量 5,542 行。
- 结论：**parquet hive 分区写/读路径完全可行**；`date` 列为 `Date` 类型（非字符串）→ 读侧应优先「分区存在性」判定（镜像 `pool_snapshot.load_point_snapshot` 的 `date={as_of}` 路径 glob），避免字符串 vs Date 比较坑。

---

## 2. 实现方案（总览）

```
EOD 钩子                    capture(data_dir, as_of)
┌─────────────────────┐    ┌──────────────────────────────────────────┐
│ _pool_eod_persist   │──▶ │ concept_history.capture:                  │
│  persist_point_...  │    │  读当前 ext_gn_ths / ext_hy_ths 快照行      │
│  └─ capture()       │    │  → 原子写 ext_history/{kind}/date={D}/     │
└─────────────────────┘    │    part.parquet + manifest.json            │
                           └──────────────────────────────────────────┘
                                            │
读侧 seam（三消费方共享）                      ▼
┌────────────────────────────────────────────────────────────────────┐
│ concept_history.read_partition(data_dir, kind, as_of) → {rows,manifest}│
│ pool_hub._build_concept_map(data_dir, as_of)  ← 本阶段主改造         │
│ market_overview_builder._dimension_rank(..., as_of)  ← CONCEPT-06   │
│ rps_rotation._load_concept_map_df(repo, as_of)      ← CONCEPT-06    │
└────────────────────────────────────────────────────────────────────┘
```

核心设计取舍（与规划期 OQ 呼应）：

1. **归档源 = 当前 ext 快照行（离线、确定性）**，而非 EOD 重新抓上游。理由：orchestrator 决策 (b)「不自动刷新当前快照」；归档「当日平台可见的归属」与用户实际看到的一致，EOD 关键路径零网络。上游逐日变化与否由 OQ-3 探针单独测量（`capture_from_upstream`）。**`as_of_snapshot` 的语义 = 「D 日平台存档的已发布归属」**，content 是否逐日变化由 `concept_effective_date` 诚实暴露（CONCEPT-07）。
2. **写根目录 `data/ext_history/`（平台自有根）**，镜像 `_SNAPSHOT_ROOT="screener_results"` 先例；**绝不进 `ext_data`**（避免与用户可配置列表双计数）。
3. **读侧统一走 `concept_history.read_partition`**，`pool_hub`/`_dimension_rank`/`_load_concept_map_df` 三消费方共享同一原语（CONCEPT-06 一次升级全收）。
4. **状态机只在有概念数据源的语境下判定 `unavailable`**——保 `test_build_pool_hub_snapshot_has_concept_attribution`（:486）无分区、无 ext 配置时继续绿（见 §4 状态机）。

---

## 3. 模块职责

### 3.1 `backend/app/services/concept_history.py`（新模块，stdlib + polars，零新依赖）

```python
_HISTORY_ROOT = "ext_history"          # 平台自有根（相对 data_dir）
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SCHEMA_VERSION = 1
_KINDS = ("gn_ths", "hy_ths")          # 概念 + 行业同建（orchestrator 决策 c）

# 内部
def _partition_dir(data_dir, kind, as_of) -> Path   # data_dir/ext_history/{kind}/date={as_of}
def _partition_path(data_dir, kind, as_of) -> Path  # .../part.parquet
def _manifest_path(data_dir, kind, as_of) -> Path   # .../manifest.json
def _write_partition(data_dir, kind, as_of, rows, *, source_url, fetched_at, captured_at, dimension_field) -> Path
    # 严格 _DATE_RE.fullmatch + date.fromisoformat（非法 → ValueError，防穿越）
    # temp + os.replace 原子写 part.parquet（cast_df_to_schema 对齐 ext schema）+
    # 同目录 manifest.json 原子写（temp + os.replace）；异常吞掉记 warning（非致命）
def _current_rows(data_dir, config) -> list[dict]   # 读 data/ext_data/{id}/part.parquet 全行

# 写侧
def capture(data_dir, as_of) -> dict
    # 主路径：读当前 ext_gn_ths + ext_hy_ths 快照行 → 各写一个分区 + manifest
    # 返回 {"as_of", "gn_ths": {written, rows}, "hy_ths": {written, rows}}
    # 快照缺失/0 行 → 该 kind 诚实 skip（不写文件）；整体不抛（不阻断 EOD）
def capture_from_upstream(data_dir, as_of) -> dict
    # OQ-3 探针用：httpx.Client 同步抓 pull.url → ext_presets._flatten_*_rows
    # → _write_partition；与 capture 共用写路径（只多一个抓取源）
    # 抓取失败/0 行 → warning + skip，不抛

# 读侧（三消费方共享）
def read_partition(data_dir, kind, as_of) -> dict | None
    # 返回 {"rows": list[dict], "manifest": dict}；分区缺失/非法 as_of/解析失败 → None
    # 读 part.parquet（hive_partitioning 或直读）+ manifest.json（可选，缺省合成）
def list_partition_dates(data_dir, kind) -> list[str]     # ISO desc
def partition_sha256(data_dir, kind, as_of) -> str | None  # 内容哈希，探针/幂等判定用
```

**manifest.json schema（CONCEPT-07）：**
```json
{
  "as_of": "2026-08-06",
  "kind": "gn_ths",
  "dimension_field": "所属概念",
  "source_url": "https://files.688798.xyz/ths/concepts.json",
  "fetched_at": "2026-07-29T17:57:54.165335",
  "captured_at": "2026-08-06T15:35:12+08:00",
  "rows": 5542,
  "schema_version": 1,
  "sha256": "…"
}
```
- `fetched_at` = 当前快照数据实际产生时刻：`config.pull.last_run`（ISO）优先，否则 `part.parquet` mtime ISO，否则 = `captured_at`。**`concept_effective_date = date(fetched_at)`**（CONCEPT-07 生效日期）。
- `dimension_field` 自描述（`所属概念` / `所属同花顺行业`），读侧无需再猜字段名。

### 3.2 `backend/app/services/pool_hub.py`（改造，保持零写）

- `_build_concept_map(data_dir, as_of=None) -> tuple[dict, str, str | None, str | None]` 返回 `(concept_map, attribution, effective_date, captured_at)`：
  1. `as_of` 非空 → `concept_history.read_partition(data_dir, "gn_ths", as_of)`；命中且 rows 非空 → 用分区行建 map（`_dimension_values(row[manifest.dimension_field])` + `_symbol_keys`），`attribution="as_of_snapshot"`，`effective_date=as_of`，`captured_at=manifest.captured_at`。
  2. 否则回退当前 ext（**既有逻辑原样**），有概念 config 且 rows 非空 → `"current_snapshot"`；有概念 config 但 rows 空 → `"unavailable"`；无概念 config → `"current_snapshot"`（向后兼容默认）。
- `_project_hub(..., as_of=None)` — 顶部 `concept_map, attribution, effective_date, captured_at = _build_concept_map(data_dir, as_of)`；返回 dict 恒带 `concept_attribution`；`attribution == "as_of_snapshot"` 时追加 `concept_effective_date` / `concept_captured_at`（回退态不追加，保持既有键集）。
- `build_pool_hub(...)` — **不改**（`as_of=None` → 实时视图恒 `current_snapshot`，orchestrator 决策）。
- `build_pool_hub_snapshot(data_dir, as_of, ...)` — 非空态调 `_project_hub(..., as_of=snap["as_of"])`；空态 `:246` **一字不动**。

### 3.3 `backend/app/jobs/daily_pipeline.py`（EOD 钩子）

在 `_pool_eod_persist` 的 `if results:` 块内、`persist_point_snapshot(...)` 之后插入（同步、try/except 非致命）：

```python
from app.services import concept_history
try:
    concept_history.capture(data_dir, str(as_of))   # as_of 是 date 对象，str()=ISO
except Exception as e:  # noqa: BLE001
    logger.warning("概念历史归档失败（不阻断股池持久化）: %s", e)
```

- `_pool_eod_persist` 保持同步：capture 读本地快照零网络，**无需 async**。
- 失败语义：记 warning、不抛、不阻断快照持久化（CONCEPT-01 验收）。

### 3.4 CONCEPT-06 共享 seam（可拆分交付）

- `market_overview_builder._dimension_rank(rows, repo, kind, limit=5, level=None, as_of=None)` — `as_of` 非空时，ext 循环改读 `concept_history.read_partition(data_dir, kind→"gn_ths"/"hy_ths", as_of)`（`kind=="concept"`→`gn_ths`，`"industry"`→`hy_ths`），其余聚合逻辑原样。`build_market_overview(..., as_of=...)` 在 `explicit_as_of` 时把 `as_of` 传给 `:503-504` 两处 `_dimension_rank`。
- `rps_rotation._load_concept_map_df(repo, as_of=None)` — `as_of` 非空时**绕过/按 as_of 复键**模块级 600s 缓存（否则历史日可能拿到最新日 map）；读 `read_partition` 展开成 `(_sym_up, concept)` 对。`build_rps_rotation(repo, days, as_of=None)` 透传。
- 语义备注：RPS 矩阵本身横跨历史日期（日期来自 enriched `change_pct`），`as_of` 指「矩阵使用的概念映射取 D 日分区」，矩阵各历史列仍共用该单日 map（诚实、标注来源）；逐日概念 map 各列独立属未来增强，不在本期。

---

## 4. 读侧 / 写侧契约

### 4.1 写侧契约

| 契约 | 规则 |
|---|---|
| 根目录 | 只写 `data/ext_history/{gn_ths|hy_ths}/date={as_of}/part.parquet` + `manifest.json`（平台自有根，不进 `ext_data`） |
| 日期校验 | 写前 `_DATE_RE.fullmatch` + `date.fromisoformat`；非法 → ValueError（防路径穿越） |
| 原子性 | `temp + os.replace`（镜像 `pool_snapshot.persist_point_snapshot`），同 as_of 幂等重写，无 `.tmp` 残留 |
| 行集 | 分区行 = 当前 ext 快照全行（`cast_df_to_schema` 对齐 ext schema，列序稳定） |
| 诚实 skip | 快照缺失 / 0 行 / 写失败 → 记 warning 不写文件（缺档由读侧回退标注，绝不合成） |
| 幂等 | 同 as_of 重复 capture → 覆盖写，内容 sha256 可对比（OQ-3 探针） |

### 4.2 读侧契约

| 契约 | 规则 |
|---|---|
| 读入点 | `read_partition(data_dir, kind, as_of)` → `{rows, manifest} \| None`；分区缺失/非法 as_of/解析失败 → None（镜像 `load_point_snapshot` 防御语义） |
| as_of 判定 | **分区存在性优先**（glob `date={as_of}/part.parquet`），不依赖 parquet 内 `date` 列（避免 Date vs str 比较坑） |
| 归属状态机 | `as_of_snapshot`（分区命中）→ `current_snapshot`（有概念 config 且当前 rows 非空）→ `unavailable`（有概念 config 但当前 rows 空）→ `current_snapshot`（无概念 config，向后兼容默认）；**空态（无快照）恒 `current_snapshot`** |
| 永不按行混用 | 一次投影一个 attribution（顶层键），绝不逐行标注 |
| 投影键 | `concept_attribution` 恒在；`as_of_snapshot` 时追加 `concept_effective_date`（= 分区日）+ `concept_captured_at`（= manifest） |
| 兼容性 | 无分区路径下行为与现状逐位一致（`test_build_pool_hub_snapshot_has_concept_attribution` :486 等回归锁） |

### 4.3 归属状态机判定明细（保回归绿的关键）

```
空 hub（无缓存/无快照）          → 既有精确 dict（live hub 无 attribution 键；
                                   snapshot 空态恒 current_snapshot）   [回归锁]
有投影数据:
  as_of 分区命中且 rows 非空       → as_of_snapshot (+effective/captured_at)
  无分区，有概念 config，当前行非空 → current_snapshot
  无分区，有概念 config，当前行空   → unavailable
  无分区，无概念 config            → current_snapshot（默认，:486 测试保绿）
```

> 关键：**「无概念 config」≠「unavailable」**。`unavailable` 只在该表概念数据源已安装（`ext_gn_ths` config.json 存在）但当前快照数据缺失/空时触发——这是「功能存在、数据缺失」的真实诚实态。测试夹具 `_write_snapshot`（test_pool_hub.py:227）不写任何 ext_data → 无概念 config → `current_snapshot`，现有断言不动。

---

## 5. 验收口径（per CONCEPT-01..07）

### CONCEPT-01 平台自有历史概念归档（写入侧）
- 交易日 D 跑完 `_pool_eod_persist` → 存在 `data/ext_history/gn_ths/date=D/part.parquet` 与 `hy_ths/date=D/part.parquet`，行数 == 当日当前 ext 快照行数（dry-run 实测 5,542）。
- 无数据日 / 快照缺失 → 诚实 skip，**不写任何文件**。
- 写失败 → 仅 warning，**不阻断**快照持久化（单测注入失败路径断言 `_pool_eod_persist` 仍返回成功）。
- grep 确认写 `ext_history` 的调用只出现在 `concept_history.py` 的 capture/_write_partition（CONCEPT-05）。

### CONCEPT-02 as_of 读侧解析
- 构造 `ext_history/gn_ths/date=D` 分区后，`build_pool_hub_snapshot(data_dir, D)["strategies"][i]["rows"][j]["concept_board"]` 等于 D 日分区映射（分区优先于当前 ext）。
- 无分区 → 行为与现状逐位一致（既有 test_pool_hub.py 回归零改动）。

### CONCEPT-03 诚实归属状态机
- 三态单测各一（`as_of_snapshot` / `current_snapshot` / `unavailable`）+ 空态回归（`current_snapshot`）。
- `test_build_pool_hub_snapshot_has_concept_attribution`（:486）在无分区路径下继续绿。

### CONCEPT-04 前端可见标注
- 历史/当前载荷 `concept_attribution !== "as_of_snapshot"` → 渲染徽标/工具提示「概念归属为当前快照，非该日数据」；`as_of_snapshot` → 「概念按当日快照」+ `concept_effective_date`。
- Playwright：`current_snapshot` 载荷出现徽标文案；`as_of_snapshot` 载荷显示按日文案且**不出现**回退徽标。
- **不触碰 `frontend/src/pages/Watchlist.tsx`**（off-limits 铁律）。

### CONCEPT-05 禁止回填伪造
- grep `ext_history` 写调用只命中 `concept_history.capture` / `_write_partition`。
- 缺分区 → 读侧回退 `current_snapshot`，**永不合成分区、永不伪造历史**。
- POOL-03 AST 守卫扩展（按模块拆分）：`concept_history.py` 只写 `ext_history`（镜像 `_SNAPSHOT_ROOT` 守卫形态）；`pool_hub.py` 仍零写；`api/pool.py` 仍 GET-only。

### CONCEPT-06 共享 seam 扩展到总览/RPS（可拆分）
- `build_market_overview(..., as_of=D)` 的 `concept_rank` / `industry_rank` 由 D 日分区聚合。
- `build_rps_rotation(..., as_of=D)` 的矩阵概念列与 D 日分区一致。
- 若拆分：本阶段交付 seam 原语（`read_partition`）+ `_dimension_rank`/`_load_concept_map_df` 签名扩展（as_of 可选、默认 None 行为不变），总览/RPS 接线可作 CONCEPT-06 独立子任务或后续阶段。

### CONCEPT-07 归档 provenance 元数据
- 每分区旁 `manifest.json` 字段齐全（`source_url` / `fetched_at` / `captured_at` / `rows` / `schema_version` / `sha256` / `dimension_field`）。
- `/api/pool/history` 在 `as_of_snapshot` 时携带 `concept_effective_date`（= 分区日期）与 `concept_captured_at`；前端可显示「概念数据生效日期」。

---

## 6. OQ-3 探针设计（一周逐日 diff）

**目的:** 校准归档策略（每日强制 vs 内容 diff 后写）并验证分区将逐日不同；同时检验上游 `concepts.json` 更新节奏（当前为 [INFERENCE]）。

### 6.1 单次 capture dry-run（已完成，2026-08-06 实测）
- 动作：读当前 `ext_gn_ths` 快照（5,542 行 / 260,465 B）→ 写 `ext_history/gn_ths/date=2026-08-06/part.parquet` → `hive_partitioning=True` 读回。
- 结果：分区 260,465 B；读回自动追加 `date` 列（Date dtype），`date==max` 过滤得全量 5,542 行；symbol join 键齐全。
- 结论：**写路径 shape 验证通过**；读侧应走「分区存在性」而非 `date` 列比较。

### 6.2 一周逐日 diff 探针（operator 部署后跑）
- 落点：`backend/scripts/probe_concept_drift.py`（镜像 `probe_phase13.py` 先例）。
- 每交易日动作：
  1. `concept_history.capture(data_dir, date)`（离线归档）**或** `capture_from_upstream(data_dir, date)`（独立测量上游，二选一可配）。
  2. `partition_sha256(data_dir, "gn_ths", date)` / `("hy_ths", date)`。
  3. 追加 `data/ext_history/_probe/drift.jsonl`：`{date, sha256, rows, effective_date}`。
- 周终报告：去重哈希数、逐日变化天数、相邻分区概念增删样本（前 5 个新增/消失概念）、`effective_date` 分布。
- 决策输入：
  - 哈希每日变化 → 上游活跃 → 每日强制 capture 有实义。
  - 哈希多日不变 → 上游低频更新 → 仍**建议每日强制 capture**（存储 ~64MB/年可忽略，provenance 简单），但 UI 必须依赖 `concept_effective_date` 展示真实生效日（CONCEPT-07）。
- 探针仅读 `data/ext_history/` 与脚本自身 `_probe/` 输出，零副作用于 ext 当前快照 / strategy_cache / screener_results。

---

## 7. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 上游 `concepts.json` 更新节奏未知（可能数日不变） | 中 | OQ-3 探针 + `concept_effective_date` 展示真实生效日（CONCEPT-07） |
| EOD 归档失败 → 当日缺口 | 低-中 | 读侧回退 `current_snapshot`（诚实）；`captured_at`/缺失留痕；capture 幂等可补跑 |
| 实时 hub（手动 ext）与同日分区概念可能不一致 | 低 | 两者均诚实且标注区分（OQ-1 决策保持 hub=current_snapshot） |
| 存量 ~247 个上线前历史日无法获得 PIT 概念 | 高（范围） | 前向范围 + 缺档回退标注；**绝不回填伪造**（CONCEPT-05） |
| POOL-03 AST 守卫需按模块拆分（现只放行 `screener_results`） | 低 | 新守卫镜像 `test_pool_snapshot_writes_only_screener_results` 形态，断言 `_HISTORY_ROOT == "ext_history"` |
| 存储增长 ~64MB/年 | 低 | 相对 enriched 湖（51MiB）+ 快照（79-693MiB）可忽略 |
| parquet `date` 列 = polars `Date` dtype（非 str） | 低 | 读侧「分区存在性」判定，不做 `date` 列字符串比较 |
| `read_partition` 读到半写文件 | 低 | 写侧 temp+os.replace 原子写；读侧解析失败 → None（防御语义） |
| RPS 600s 模块级缓存污染 as_of 读 | 低 | `as_of` 非空绕过/按 as_of 复键缓存（CONCEPT-06） |
| 归档源口径歧义（当前快照 vs 上游重抓） | 低 | 主路径 = 当前快照（离线、与展示一致）；上游重抓仅 OQ-3 探针用；两路径共用 `_write_partition`，切换成本 = 一个调用点 |

---

## 8. 关键锚点（本轮复核，行号以当前仓库为准）

| 锚点 | 位置 | 用途 |
|---|---|---|
| `_concept_preset` | `backend/app/services/ext_presets.py:37-64` | 概念表定义（snapshot, URL, enabled=False） |
| `_industry_preset` | `backend/app/services/ext_presets.py:66-92` | 行业表定义（`所属同花顺行业`） |
| `_flatten_concept_rows` / `_flatten_industry_rows` | `ext_presets.py:117-147` | 上游 schema → 本地 schema（探针复用） |
| `write_ext_parquet` timeseries 分支 | `ext_data.py:467-591`（时序分支 ~:526-541） | 写路径参考（分区/去重/cast） |
| `cast_df_to_schema` | `ext_data.py`（write_ext_parquet 内调用） | 对齐 ext schema 列序 |
| `_ext_files` / `_read_ext_rows` | `market_overview_builder.py:74-80` / `:82-117` | 读侧 hive 分区能力（缺 as_of） |
| `_dimension_field` / `_dimension_values` / `_symbol_keys` | `market_overview_builder.py:121-230` | 维度识别 + join 键提取 |
| `_dimension_rank` | `market_overview_builder.py:243-315` | CONCEPT-06 总览侧（`build_market_overview` :503-504 调用） |
| `_build_concept_map` | `pool_hub.py:38-56` | 概念 join 入口（升级为 as_of） |
| `_project_hub`（concept_board :123 / attribution :182） | `pool_hub.py:96-187` | 投影核心，状态机落点 |
| `build_pool_hub_snapshot`（空态 :246 / 透传 :252-267） | `pool_hub.py:225-267` | 历史投影入口，透传 as_of |
| `build_pool_hub`（空缓存 :210） | `pool_hub.py:198-222` | 实时视图（保持 current_snapshot） |
| `_pool_eod_persist` | `daily_pipeline.py:973-1015` | EOD 钩子（capture 调用点，`if results:` 内） |
| `pool_eod_persist` job 注册 | `daily_pipeline.py:1131-1140` | 调度确认（mon-fri，管道后 +5min） |
| `_run_tracked` | `daily_pipeline.py:723` | 同步单飞（capture 需同步） |
| `_SNAPSHOT_ROOT` / `persist_point_snapshot` | `pool_snapshot.py:29-40` / `:66-122` | 平台自有根 + 原子写先例（镜像） |
| `load_point_snapshot`（存在性判定） | `pool_snapshot.py:124-146` | 读侧「分区存在性」模式 |
| `pool_backfill.run_pool_backfill` | `pool_backfill.py:57-96` | 回填**不**写概念分区（维持） |
| `_load_concept_map_df` | `rps_rotation.py:60-109` | CONCEPT-06 RPS 侧（600s 缓存） |
| `build_rps_rotation`（join :150-165） | `rps_rotation.py:111-200` | CONCEPT-06 RPS 接线 |
| `analyze_rotation_stream` | `concept_rotation_analyzer.py:257-358` | RPS 消费方（保持最新视图） |
| `test_pool_hub.py` 归属/守卫测试 | `:469-494` / `:857-963` | 回归锁 + 守卫形态 |
| `_write_concept_fixture` | `test_pool_hub.py:113-132` | 新测试可复用的 ext 夹具形态 |
| `ConceptChips` / 概念列表头 | `frontend/src/components/pool-hub/StockListTable.tsx:49-56` / `:373` / `:14-15`（列定义） | CONCEPT-04 概念单元格/列头 |
| `AuctionColumnStatusBadge` 渲染位 | `frontend/src/pages/PoolHubPage.tsx:328-333` | CONCEPT-04 徽标放置参照（同上区域） |
| `DateNavigator` | `frontend/src/components/pool-hub/DateNavigator.tsx` / `PoolHubPage.tsx:176` | 历史视图徽标可挂点 |
| `concept_attribution` 类型 | `frontend/src/lib/api.ts:764-766` | 已存在，需消费；追加 `concept_effective_date` / `concept_captured_at` |
| 概念数据实测 | `data/ext_data/ext_gn_ths/part.parquet`（260,465 B, 5,542 行）/ `ext_hy_ths`（同 5,542 行） | 存储/结构事实 |

---

## 9. 测试计划

### 9.1 现有测试（必须保持绿的回归锁）

| 测试 | 位置 | 为何必须绿 |
|---|---|---|
| `test_build_pool_hub_snapshot_missing_available_false` | `test_pool_hub.py:469-483` | 空态精确 dict（`concept_attribution: "current_snapshot"`）一字不动 |
| `test_build_pool_hub_snapshot_has_concept_attribution` | `test_pool_hub.py:486-496` | 无分区路径仍 `current_snapshot`（无概念 config 默认态） |
| `test_build_pool_hub_empty_cache` | `test_pool_hub.py:377-380` | 空缓存精确 dict（无 attribution 键） |
| `test_pool_history_snapshot` | `test_pool_hub.py:775-806` | history 键集含 `concept_attribution`（改造后仍含） |
| `test_pool_history_rejects_bad_as_of` | `test_pool_hub.py:841-847` | as_of 双校验不变 |
| `test_concept_board_join_and_missing_value_dash` 等概念投影测试 | `test_pool_hub.py:288-375` | 实时 hub（as_of=None）行为逐位不变 |
| AST 守卫全套（E1-E6） | `test_pool_hub.py:895-963` | `pool_hub.py` 零写、`pool.py` GET-only 保持 |

### 9.2 新测试（新增，独立文件 `backend/tests/test_concept_history.py` + 少量 pool_hub 扩展）

| 测试 | 断言 |
|---|---|
| `test_capture_writes_hive_partition_and_manifest` | capture 后 `ext_history/gn_ths/date=D/part.parquet` + `manifest.json` 存在；行数 == 快照行数；manifest 字段齐全（source_url/captured_at/fetched_at/rows/schema_version/sha256/dimension_field） |
| `test_capture_rejects_bad_as_of` | 非法 as_of（`2026-8-4`/`../../x`）→ ValueError（防穿越） |
| `test_capture_idempotent_no_tmp_residue` | 同 as_of 两次 capture → 单分区、单 manifest、无 `.tmp` |
| `test_capture_missing_snapshot_honest_skip` | 当前快照缺失/0 行 → 不写文件、不抛、返回 skip 记录 |
| `test_read_partition_missing_returns_none` | 缺分区/非法 as_of/损坏 parquet → None |
| `test_build_pool_hub_snapshot_as_of_snapshot_attribution` | 快照 + D 日分区 → `concept_attribution == "as_of_snapshot"`，`concept_effective_date == D`，行 `concept_board` 来自分区 |
| `test_partition_preferred_over_current_snapshot` | 分区与当前 ext 内容不同 → 投影跟随分区（as_of 优先） |
| `test_attribution_unavailable_when_config_without_data` | 有 `ext_gn_ths` config 但当前快照缺失/空 → `"unavailable"` |
| `test_pool_history_returns_concept_metadata` | API 级：history + 分区 → 载荷含 `concept_effective_date` / `concept_captured_at` |
| `test_concept_history_ast_guard_writes_only_ext_history` | 镜像 `test_pool_snapshot_writes_only_screener_results`：`_HISTORY_ROOT == "ext_history"`，所有含写路径函数引用 `_HISTORY_ROOT` |
| `test_concept_history_no_execution_imports_no_strategy_cache` | 镜像 E1/E3：无执行族 import、无 strategy_cache 引用 |
| 前端（Playwright，CONCEPT-04） | `current_snapshot` 载荷出现徽标文案；`as_of_snapshot` 显示按日文案且无回退徽标（不触碰 Watchlist.tsx） |

> 不新增覆盖：`_dimension_rank`/`_load_concept_map_df` 的 as_of 分支测试归入 CONCEPT-06（若本期拆分则延后）。

---

## 10. 待规划层确认的开放点

1. **OQ-1（沿用）**：实时 hub 保持 `current_snapshot`（本设计默认）；若未来改为同日分区优先，`build_pool_hub` 传 `as_of=cache_as_of` 即可，单点切换。
2. **归档源口径**：本设计主路径 = 读当前 ext 快照行（离线）；若 planner 采纳研究稿「EOD 重抓上游」语义，切 `capture_from_upstream`，写路径/读侧/状态机零改动。
3. **CONCEPT-06 是否本期接线**：seam 原语本期必交付；总览/RPS 接线可作独立子任务或后续阶段（验收口径已分别给出）。
4. **`concept_effective_date` 回退态是否透传**：本设计回退态不追加该键（键集与现状一致）；如需前端统一渲染，可改为恒带（值 null），需同步放宽 history 键集断言。

---

*Phase 28 实现研究完成：2026-08-06*
*Ready for planning: yes*
