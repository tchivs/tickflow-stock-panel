# Phase 26: 历史竞价图 + 派生列复活 (Auction History Chart) - Pattern Map

**Mapped:** 2026-08-06
**Files analyzed:** 17（11 修改 / 6 新建）
**Analogs found:** 17 / 17（in-file exact 11 / 外部 exact 3 / 外部 role-match 3；另有 5 处「复用既有、零新增」见 Reuse）

> 本文件把 Phase 26（CHART-01..03）的每个新建/修改文件映射到仓库内最接近的既有实现，并给出可直接复制/镜像的具体代码段（带文件路径与行号，全部在本 session 逐行读取确认）。Research 依据：`.planning/research/v2.1-depth/CHART.md`（湖 = `symbol/datetime/auction_volume/auction_amount` 四列；当前 **0 分区**；`auction_unmatched_amount` 读路径派生已实现但写路径裁剪 → 恒缺席）。
>
> **一句话总结:** CHART-01 是纯后端只读聚合——在 `kline.py` 加一个 `GET /api/kline/auction/history?symbol=&days=`，数据源走已登记的 `kline_auction` DuckDB 视图（`repository.py:162-163`），镜像 `pool.py` 的 `available:false` 诚实空态（200 非 404）与 `auction_columns.py` 的 probe×分区双闸门 + 末行去重；CHART-02 是纯前端——新 `AuctionHistoryChart.tsx` 镜像 `EChartsIntraday` 的 init/resize/dispose + `useChartTheme` 生命周期，柱(量)+线(额)双轴镜像 `EChartsCandlestick` 的 volume bar + 多 yAxis，挂进 `StockPreviewDialog` 的「分时」toggle 旁作为第三开关；CHART-03 是后端写路径最小改动——把 `_normalize_auction`（`custom/provider.py:159`）与 `sync_and_persist_auction`（`auction_sync.py:129`）的裁剪集从「4 列」扩为「4 必需 + 2 可选」（`auction_unmatched_volume`/`auction_virtual_price`），源提供时才保留，读路径 `compute_auction_unmatched_amount`（`auction_columns.py:35-51`）自动激活。**零新 npm/pip 依赖，不触碰 `Watchlist.tsx`。**
>
> **给 planner 的第一优先级决策点:**
> 1. **CHART-01 严禁复制 `kline.get_daily` 的空库 live-fetch 兜底**（`kline.py:159-181` 在 enriched 空时调 `sync_daily_batch` 实时拉取）。CHART-01 是 POOL-03 零执行权的只读聚合——空湖必须 `available:false` 诚实返回，**绝不**触发任何同步/回填/写路径。这是本阶段最容易踩的坑（analog 恰好是反面教材）。
> 2. **行粒度「末行 vs 求和」要作为显式设计决策写进验收**（research OQ-3）：默认每交易日取窗口末行（09:25 最终撮合，镜像 `auction_columns.py:146` 的 `unique(subset=["symbol"], keep="last")`），同时返回每日期 `row_count` + `min/max datetime` 供前端标注粒度；若真实源是逐分钟累计快照，「末行」即最终撮合，若是独立行则求和才是总量——需在接入真实源后按源语义钉死。
> 3. **CHART-02 e2e 必须 mock `/api/kline/auction/history`**（`pool-hub.spec.ts` 的 `installShell` 已把 `**/api/**` 全 mock 成 500，新路由不注册会大声失败）——在 `installShell` 里注册该路由 + 各用例按需覆盖（后注册优先）。
> 4. **CHART-03 向后兼容断言**：源不提供可选列 → 分区仍 4 列；提供 → 分区 5-6 列。既有 `test_auction_sync.py`/`test_auction_columns.py`/`test_auction_strategy_family.py` 全套 `-x -q` 必须全绿（无回归）。

## 关键约束与危险区（先读）

| 边界 | 位置 | 本阶段影响 |
|---|---|---|
| **POOL-03 零执行权（后端 AST 守卫）** | `backend/app/api/pool.py:1-7` 模块 docstring；`backend/tests/test_pool_hub.py`（T-18-01 E4/E5） | CHART-01 端点必须 GET-only：不写库、不调 broker、不触发任何计算/持久化。**kline.get_daily 的空库 live-fetch（`kline.py:159-181`）是反面教材，CHART-01 禁止复制** |
| **`available:false` 诚实空态（200 非 404）** | `backend/app/api/pool.py:88`（`get_pool_history` docstring）+ `:100-107` as_of 双重校验 | CHART-01 空湖/缺 symbol → 200 `{available:false, rows:[]}`，绝不 500、绝不 0 填充 |
| **probe×分区双闸门** | `backend/app/services/auction_columns.py:93-107`（第一闸门 probe available、第二闸门分区存在且有行） | CHART-01 服务与 CHART-03 读路径都沿用；probe 非 available → 诚实空态（列缺席/空响应） |
| **`Watchlist.tsx` 用户未提交改动** | `frontend/src/pages/Watchlist.tsx`（1346 行，未提交） | **绝不修改/提交/read 内容**；CHART-02 只新增组件 + 改 `StockPreviewDialog`/`StockPanel`/`lib`，零 Watchlist 依赖 |
| **零新 npm/pip 依赖** | `frontend/package.json`（echarts + echarts-for-react + lightweight-charts 在册）；CHART.md 结论 | CHART-02 只用既有 ECharts 基建；后端只用既有 seams（`run_all_with_hits`/`attach_auction_columns`/`/api/watchlist` 等） |
| **前端验证 = build + e2e，无 vitest** | 项目约束 | CHART-02 验收 = `npm run build` 全绿 + Playwright e2e（mock 图/空态/probe） |
| **派生列与真实列永不相加（Phase 23 分组回归）** | `auction_columns.py:35-51`（compute 独立命名）；`pipeline.py:158-161`（估算标注）；`test_auction_columns.py` `test_unmatched_proxy_never_mixed_with_real` | CHART-03 扩列后不得把 `auction_unmatched_amount` 混入真实列求和/图表；CHART-02 只画真实 `auction_volume/auction_amount` |
| **当前环境湖 0 分区** | CHART.md §1.4（`data/kline_auction` 不存在） | CHART-01/02 验收用 fixture/mock，不依赖真实数据；UI 必须诚实空态「无历史竞价数据 · 需配置集合竞价数据源」 |
| **guest 掩码只属股池 Hub 面** | `pool.py:110-113` `mask_guest_hub`；`services/guest_masking.py` | CHART-01 按 symbol 取历史竞价序列，非股池行集——**不要**把 `mask_guest_hub`/guest 面逻辑复制进 CHART-01/02 |
| **`_table_cache`/`_compute_storage` 不跟踪 auction** | `data.py:33-44`、`data.py:484-533` | research 标注为小改、非必需；仅当 CHART-01 暴露 coverage 天数时才把 `kline_auction` 纳入 storage 统计，否则不动（防范围蔓延） |
| **schema 面字段描述** | `data.py:725` `_TABLE_FIELD_DESC`、`:769-774` `kline_auction`、`:812-825` `_SCHEMA_VIEWS`；`pipeline.py:158-161` `ENRICHED_COLUMNS` | CHART-03 扩列 → 同步补 `kline_auction` 字段描述（可选列 + 派生列带「估算」标注）；`ENRICHED_COLUMNS` 已有 `auction_unmatched_amount` 估算描述（`pipeline.py:160`） |

## File Classification（目标文件 → analogs）

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality | 关键差异 |
|---|---|---|---|---|---|
| `backend/app/api/kline.py` (modified) | controller/route | request-response（GET-only） | `kline.py:127-189 get_daily`（symbol+days Query 形态）+ `pool.py:79-113 get_pool_history`（available:false + as_of 校验） | role-match | 新端点挂同一 `/api/kline` 前缀；**禁 live-fetch 兜底**（get_daily 空库会调 sync，CHART-01 必须纯读）；`days` 上限 120（get_daily 是 2000） |
| `backend/app/services/auction_history.py` (new) | service | read aggregation（batch/CRUD-read） | `auction_columns.py:89-151 attach_auction_columns`（probe×分区双闸门 + 末行去重）+ `auction_sync.py:90-144`（窗口过滤 + 按日分区） | role-match | 按 symbol 拉多日序列而非左联日线帧；每交易日取末行（09:25）；返回 `row_count`/`min/max datetime` 供粒度标注；不写湖 |
| `backend/tests/test_auction_history.py` (new) | test | hermetic unit | `test_auction_columns.py:20-32,58-61`（repo_env + `_write_auction_partition`）+ `test_auction_sync.py:14-25,30-42`（FakeAuctionProvider + `_rows`） | exact | 新增：多日聚合末行语义断言 + 空湖/缺 symbol → available:false 且 200 + 非法 symbol/days → 400 |
| `backend/app/data_providers/custom/provider.py` (modified) | provider | file-I/O + normalize | `provider.py:150-160 _normalize_auction`（keep 裁剪集） | exact (in-file) | keep 集从 `("symbol","datetime","auction_volume","auction_amount")` 扩为 4 必需 + 2 可选；源不提供 → 缺席（向后兼容） |
| `backend/app/services/auction_sync.py` (modified) | service | file-I/O + write | `auction_sync.py:33-36 CANONICAL_AUCTION_COLS` + `:129 keep` 裁剪 | exact (in-file) | 同一「4 必需 + 2 可选」扩列；`_atomic_write_parquet` + merge-upsert（`:37-48,135-144`）与窗口谓词（`:29-30,107-117`）不变 |
| `backend/app/services/auction_columns.py` (modified) | service | read join | `auction_columns.py:35-51 compute_auction_unmatched_amount` + `:139-143 keep`（已含派生列） | exact (in-file) | 读路径已能在输入列可得时激活派生；主要验证 keep 列表已携带 `auction_unmatched_amount`（**已含**），可选列不注入日线帧、仅派生产物注入 |
| `backend/app/api/data.py` (modified) | config/schema | request-response | `data.py:769-774 _TABLE_FIELD_DESC["kline_auction"]` + `:812-825 _SCHEMA_VIEWS` | exact (in-file) | `kline_auction` 描述扩为 4 + 2 可选 + 派生列带「估算」标注；`_SCHEMA_VIEWS["auction"]` 已有（`:822`） |
| `backend/app/indicators/pipeline.py` (modified) | config/schema | n/a | `pipeline.py:158-161`（auction 列注册）+ `:184` `BY_CATEGORY["auction"]` | exact (in-file) | `auction_unmatched_amount` 估算描述已存在（`:160`）；可补 2 个输入源列描述（源列，非展示列） |
| `backend/tests/test_auction_sync.py` (modified) | test | hermetic | `test_auction_sync.py:30-42 _rows`（canonical 3 行 fixture） | exact (in-file) | 新增 fixture：带 `auction_unmatched_volume/auction_virtual_price` → 断言分区含这两列；不带 → 仍 4 列 |
| `backend/tests/test_auction_columns.py` (modified) | test | hermetic | `test_auction_columns.py:58-61 _write_auction_partition` + `:35-45 _daily_frame` + `:25-51 compute_auction_unmatched_amount` | exact (in-file) | 新增：分区含输入列 → `attach_auction_columns` 输出含 `auction_unmatched_amount`（=乘积, 估算）；缺输入列 → 原样缺列 |
| `frontend/src/components/AuctionHistoryChart.tsx` (new) | component | render（chart） | `EChartsIntraday.tsx:407-591`（init/resize/dispose + buildOption + useChartTheme）+ `EChartsCandlestick.tsx:107-117`（volume bar series）+ `EChartsCandlestick.tsx:658-677`（多 yAxis） | exact | 柱(量)+线(额)双 y 轴，category date x 轴；诚实空态 + 「09:15-09:25」窗口标注；零新依赖 |
| `frontend/src/components/StockPreviewDialog.tsx` (modified) | component | render | `StockPreviewDialog.tsx:42`（showIntraday state）+ `:162-167`（分时 toggle 按钮）+ `:238-240`（传 StockPanel） | exact (in-file) | 新增 `showAuction` state + 第三 toggle（分时/竞价历史）；不触碰 Watchlist |
| `frontend/src/components/StockPanel.tsx` (modified) | component | render | `StockPanel.tsx:153-163`（showIntraday 条件渲染 StockIntradayChart） | exact (in-file) | 新增 `showAuction` prop + 条件渲染 `AuctionHistoryChart`；与分时并列或替换 |
| `frontend/src/lib/api.ts` (modified) | utility/client | request-response | `api.ts:1918-1930 klineDaily`（GET + symbol/days/dateRange）+ `api.ts:22-45 request` helper | exact (in-file) | 新增 `auctionHistory(symbol, days)` 类型化方法；走既有 `request`（401 不弹 toast 由全局拦截） |
| `frontend/src/lib/queryKeys.ts` (modified) | config | n/a | `queryKeys.ts` `QK.kline`/`QK.klineMinute` 工厂 | exact (in-file) | 新增 `QK.auctionHistory(symbol, days)` |
| `frontend/src/lib/useSharedQueries.ts` (modified) | hook | request-response | `useSharedQueries.ts:85-91 useAuctionProbe`（useQuery 封装） | role-match | 新增 `useAuctionHistory(symbol, days)`；历史不可变 → `staleTime` 大（如 `5 * 60_000`） |
| `frontend/e2e/auction-history.spec.ts` (new) | test | e2e mock + assert | `pool-hub.spec.ts:268-309 installShell` + `:261-262 unhandled` + auction fixtures `:127-184` + json route override | exact | 新 spec：mock `/api/kline/auction/history` 三态（有数据 / available:false / probe 非 available）；从股池钻取打开弹窗走竞价历史 tab |

## Pattern Assignments

### 1. `backend/app/api/kline.py` (modified, controller / GET-only request-response)

**Analogs:** `kline.py:127-189 get_daily`（同前缀 Query 形态）+ `pool.py:79-113 get_pool_history`（available:false + 参数校验）。

**Router + 只读端点骨架（复制 kline.py:15 的 router，端点体镜像 pool.py 的校验与空态）:**
```python
# kline.py:15 — 复用同一 router (prefix /api/kline)
router = APIRouter(prefix="/api/kline", tags=["kline"])

# 新增 @router.get("/auction/history") — 只读聚合 (POOL-03: GET-only 零执行)
# 参考 pool.py:22 的 as_of 校验 → 换 symbol 格式校验 (全限定 symbol, 如 000001.SZ):
@router.get("/auction/history")
def get_auction_history(
    request: Request,
    symbol: str = Query(..., description="标的代码,如 000001.SZ"),
    days: int = Query(30, ge=1, le=120, description="回看交易日数 (1..120)"),
):
    # 空湖/该 symbol 无行 → 200 {available:false, rows:[]} (镜像 pool.py:88, 绝不 404/500)
    ...
```

**as_of 严格双重校验（复制 pool.py:100-107，防非法输入进文件系统/查询）:**
```python
# pool.py:100-107
if not _AS_OF_RE.fullmatch(as_of):
    raise HTTPException(status_code=400, detail="invalid as_of")
try:
    date_type.fromisoformat(as_of)
except ValueError:
    raise HTTPException(status_code=400, detail="invalid as_of")
# CHART-01 同理: symbol 非空 + 正则 `^[A-Z0-9]+\.[A-Z]{2}$` 校验; days ge/le 由 Query 约束
```

**空态响应契约（镜像 pool.py:79-113 的 `available:false` 语义）:**
```python
# pool.py:88 — 快照缺失 → available: False 空态 (200, 非 404)
# CHART-01: 湖 0 分区 / 该 symbol 无行 / probe 非 available → 一律:
#   {"symbol": ..., "available": False, "probe": {...}, "coverage": 0, "rows": []}
```

**调用 service（镜像 pool.py:107 `build_pool_hub_snapshot(data_dir, as_of, ...)` 的服务隔离）:**
```python
# CHART-01 建议把聚合逻辑放进新 service auction_history.py, 端点只做参数校验 + 组装响应
rows, coverage = auction_history.fetch_symbol_history(repo, symbol, days)
return {
    "symbol": symbol,
    "name": _get_stock_info(repo, symbol).get("name"),   # 复用 kline.py:94-102
    "available": coverage > 0,
    "probe": resolve_auction_probe().to_dict(),          # 复用 data.py:626-638 的判定
    "coverage": coverage,
    "window": "09:15-09:25",
    "rows": rows,                                        # [{date, auction_volume, auction_amount, row_count, min_datetime, max_datetime}]
    "unit": {"auction_volume": "股", "auction_amount": "元"},
}
```

### 2. `backend/app/services/auction_history.py` (new, service / read aggregation)

**Analog:** `auction_columns.py:89-151 attach_auction_columns`（双闸门 + 末行去重）+ `auction_sync.py:90-144`（窗口过滤 + 日期分区）。

**模块 docstring 纪律（镜像 auction_columns.py:1-14 / auction_sync.py:1-12: 声明读/写边界）:**
```python
"""竞价历史只读聚合 (CHART-01)。

只读 kline_auction 湖 (DuckDB 视图, repository.py:162-163), 按 symbol 拉多日
窗口末行 (09:25 最终撮合) 序列。GET-only 零执行: 绝不写湖/不触发同步/不回填。
probe 非 available 或湖空 → 诚实空态 (available:false, 非 404/500)。
"""
from __future__ import annotations
import logging
from datetime import date
import polars as pl
from app.services.auction_probe import AuctionProbeStatus, resolve_auction_probe
from app.tickflow.repository import KlineRepository
logger = logging.getLogger(__name__)
```

**probe×分区双闸门（复制 auction_columns.py:93-107 的判定结构，改为聚合视图）:**
```python
# auction_columns.py:93-107 — 双闸门原样 (第一闸门 probe, 第二闸门分区存在且有行)
if resolve_auction_probe().status != AuctionProbeStatus.available:
    ...  # 返回 available:false
# 第二闸门: 湖根目录存在且含 kline_auction/**/*.parquet
```

**按 symbol 过滤 + 按日聚合末行（核心: 镜像 auction_columns.py:146 的 keep="last" 去重）:**
```python
# auction_columns.py:146 — 末行语义 (每 symbol 保留最后一行 = 09:25 最终撮合)
auction = auction.unique(subset=["symbol"], keep="last")

# CHART-01 扩展为按 date 分组后取末行 + 返回窗口信息:
#   df = repo.execute(... "SELECT * FROM kline_auction WHERE symbol = ?" ...) 或按分区 read_parquet
#   df = df.with_columns(pl.col("datetime").dt.date().alias("date"))   # 镜像 auction_sync.py:136
#   grouped = df.group_by("date").agg(
#       pl.col("auction_volume").last().alias("auction_volume"),        # 窗口末行 (09:25)
#       pl.col("auction_amount").last().alias("auction_amount"),
#       pl.len().alias("row_count"),
#       pl.col("datetime").min().alias("min_datetime"),
#       pl.col("datetime").max().alias("max_datetime"),
#   ).sort("date")  # 升序 (research: 按 date 升序聚合)
```

**窗口边界复用（单一事实源, 复制 auction_sync.py:29-30, 勿重新定义）:**
```python
# auction_sync.py:29-30 — 与 auction_probe.py:23-24 逐字一致
_WINDOW_START_MIN = 9 * 60 + 15
_WINDOW_END_MIN = 9 * 60 + 25
```

### 3. `backend/tests/test_auction_history.py` (new, test / hermetic)

**Analog:** `test_auction_columns.py:20-32,58-61` + `test_auction_sync.py:14-25,30-42`。

**Hermetic repo_env（复制 test_auction_columns.py:20-32）:**
```python
@pytest.fixture
def repo_env(tmp_path, monkeypatch):
    """隔离的 data_dir + DataStore + KlineRepository (镜像 test_minute_sync_verify)。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)
    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    try:
        yield KlineRepository(store), data_dir
    finally:
        store.db.close()
```

**写分区 helper（复制 test_auction_columns.py:58-61）+ 多日 fixture:**
```python
def _write_auction_partition(data_dir, trade_date: date, rows: pl.DataFrame) -> None:
    out = data_dir / "kline_auction" / f"date={trade_date.isoformat()}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.write_parquet(out)

# 多日 fixture: 每日期写 2-3 行 (09:16/09:20/09:25), 断言聚合只取 09:25 末行
```

**probe patch（复制 test_auction_columns.py:43-46 `_patch_probe`）+ available verdict:**
```python
def _available_verdict():
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
    return AuctionProbeVerdict(status=AuctionProbeStatus.available, source="fake", probed_at=None, detail="")
```

**验收用例:** 有分区 → 正确聚合（末行语义）; 空湖/缺 symbol → `available:false` 且 200; 非法 symbol / days 越界 → 400; GET-only 守卫（无写/执行 import，镜像 `test_pool_hub.py` 的 POOL-03 AST 守卫风格）。

### 4. `backend/app/data_providers/custom/provider.py` (modified, provider / normalize)

**Analog（in-file）:** `provider.py:150-160 _normalize_auction`。

**扩列（唯一改动; 源不提供可选列 → 缺席, 向后兼容）:**
```python
# provider.py:150-160 现状 (canonical 4 列裁剪)
@staticmethod
def _normalize_auction(df: pl.DataFrame) -> pl.DataFrame:
    if df.is_empty():
        return df
    if "datetime" in df.columns:
        if df.schema["datetime"] != pl.Datetime("us"):
            df = df.with_columns(pl.col("datetime").cast(pl.Datetime("us"), strict=False))
        _mins = pl.col("datetime").dt.hour().cast(pl.Int32) * 60 + pl.col("datetime").dt.minute().cast(pl.Int32)
        df = df.filter((_mins >= 555) & (_mins <= 565))
    # CHART-03: 扩为 4 必需 + 2 可选 (源提供才保留)
    keep = [c for c in (
        "symbol", "datetime", "auction_volume", "auction_amount",
        "auction_unmatched_volume", "auction_virtual_price",
    ) if c in df.columns]
    return df.select(keep) if keep else pl.DataFrame()
```

### 5. `backend/app/services/auction_sync.py` (modified, service / write)

**Analog（in-file）:** `auction_sync.py:33-36 CANONICAL_AUCTION_COLS` + `:129 keep`。

**扩列（与 provider 裁剪集保持单一事实源一致——两处都改, 且注释互相引用）:**
```python
# auction_sync.py:33-36 现状
CANONICAL_AUCTION_COLS = [
    "symbol", "datetime", "auction_volume", "auction_amount",
]
# CHART-03: 扩为「4 必需 + 2 可选」— 注释: 与 custom/provider.py _normalize_auction 裁剪集逐字一致
CANONICAL_AUCTION_COLS = [
    "symbol", "datetime", "auction_volume", "auction_amount",
    "auction_unmatched_volume", "auction_virtual_price",   # 可选: 源提供才保留 (CHART-03)
]

# auction_sync.py:129 — keep 过滤本身不变 (天然向后兼容: 缺列即不保留)
keep = [c for c in CANONICAL_AUCTION_COLS if c in df.columns]
```

**不变的部分（写湖 merge-upsert + 原子写, 直接复用, 勿改）:** `_atomic_write_parquet`（`:37-48`）+ 按日分区合并 `unique(subset=["symbol","datetime"], keep="last")` + `.tmp` rename（`:135-144`）。

### 6. `backend/app/services/auction_columns.py` (modified, service / read join)

**Analog（in-file）:** `auction_columns.py:35-51 compute_auction_unmatched_amount` + `:139-143 keep`。

**读路径派生激活（已实现, 验证 keep 已携带派生列; 可选输入列本身不注入日线帧）:**
```python
# auction_columns.py:35-51 — 派生估算 (输入可得才派生, 缺列原样返回)
def compute_auction_unmatched_amount(df: pl.DataFrame) -> pl.DataFrame:
    if df is None or df.is_empty():
        return df
    if _AUCTION_UNMATCHED_VOLUME_COL not in df.columns or _AUCTION_VIRTUAL_PRICE_COL not in df.columns:
        return df
    return df.with_columns(
        (pl.col(_AUCTION_UNMATCHED_VOLUME_COL) * pl.col(_AUCTION_VIRTUAL_PRICE_COL)).alias(
            _AUCTION_UNMATCHED_AMOUNT_COL
        )
    )

# auction_columns.py:139-143 — keep 已含派生列 (CHART-03 写路径保留输入列后自动点亮):
keep = [c for c in (
    "symbol",
    *_AUCTION_REAL_COLS,                 # auction_volume, auction_amount
    _AUCTION_UNMATCHED_AMOUNT_COL,       # 派生估算 (输入可得时存在)
    _AUCTION_VOLUME_RATIO_COL,
) if c in auction.columns]
```

**本文件实际改动量:** 极小——主要验证/注释 `_AUCTION_REAL_COLS` 旁注明「4 必需 + 2 可选」写路径契约即可；派生逻辑无需改动。

### 7. `backend/app/api/data.py` (modified, schema/config)

**Analog（in-file）:** `data.py:769-774` + `:812-825`。

**`_TABLE_FIELD_DESC["kline_auction"]` 扩列（复制 :769-774 现状 + 追加 2 可选 + 派生估算标注）:**
```python
# data.py:769-774 现状
"kline_auction": {
    "symbol": "股票代码",
    "datetime": "竞价时间戳 (09:15-09:25)",
    "auction_volume": "竞价量, 单位: 股",
    "auction_amount": "竞价金额, 单位: 元",
},
# CHART-03: 追加 (源提供时存在; 派生列带「估算」)
#   "auction_unmatched_volume": "虚拟未匹配量 (股, 源提供时存在; 估算输入列)",
#   "auction_virtual_price":    "虚拟参考价 (元/股, 源提供时存在; 估算输入列)",
#   "auction_unmatched_amount": "派生未匹配金额 (估算, 非真实成交; 输入列可得时存在)",
```
`_SCHEMA_VIEWS`（`:812-825`）已有 `"auction": "kline_auction"`（`:822`）——无需改。

### 8. `backend/app/indicators/pipeline.py` (modified, schema/config)

**Analog（in-file）:** `pipeline.py:158-161` + `:184`。

```python
# pipeline.py:158-161 现状 (auction 组, 估算标注已存在)
"auction_volume":          "竞价量 (集合竞价撮合成交量, 单位: 股; 仅 probe available 时存在)",
"auction_amount":          "竞价金额 (集合竞价撮合成交额, 单位: 元; 仅 probe available 时存在)",
"auction_unmatched_amount": "派生未匹配金额 (估算, 非真实成交; 委托量输入可得时存在)",
"auction_volume_ratio": "竞价量比 (竞价量/前5日均量(不含当日), 仅 probe available 且分区有行时存在)",
# CHART-03: 可在 :158 前追加 2 个源输入列描述 (源列, 非展示列), 保持「估算」标注纪律
```
`BY_CATEGORY["auction"]`（`:184`）已含 4 展示列——源输入列是否入 category 由 planner 决定（建议不入, 避免 UI 误列）。

### 9. `backend/tests/test_auction_sync.py` (modified, test / hermetic)

**Analog（in-file）:** `test_auction_sync.py:14-25 FakeAuctionProvider` + `:30-42 _rows`。

**新 fixture（带可选输入列）:**
```python
# test_auction_sync.py:30-42 的 _rows 加一个带可选列的变体:
def _rows_with_input_cols(*minutes_and_seconds: tuple[int, int]) -> pl.DataFrame:
    return pl.DataFrame({
        "symbol": ["000001"] * len(minutes_and_seconds),
        "datetime": [datetime(2026, 8, 4, 9, m, s) for m, s in minutes_and_seconds],
        "auction_volume": [100 * (i + 1) for i in range(len(minutes_and_seconds))],
        "auction_amount": [1000 * (i + 1) for i in range(len(minutes_and_seconds))],
        "auction_unmatched_volume": [50 * (i + 1) for i in range(len(minutes_and_seconds))],
        "auction_virtual_price": [7.5] * len(minutes_and_seconds),
    })
```
**验收:** 带可选列写湖 → 分区列含 5-6 列；不带 → 分区仍 `CANONICAL_AUCTION_COLS` 4 列（向后兼容）。

### 10. `backend/tests/test_auction_columns.py` (modified, test / hermetic)

**Analog（in-file）:** `test_auction_columns.py:58-61 _write_auction_partition` + `:35-45 _daily_frame` + 既有 `test_unmatched_proxy_input_present/absent`。

**新验收（写路径 → 读路径端到端派生激活）:**
```python
# 分区带 auction_unmatched_volume + auction_virtual_price → attach_auction_columns 输出含
# auction_unmatched_amount == 乘积 (估算); 缺输入列 → 原样缺列 (既有 test_unmatched_proxy_* 已覆盖纯函数,
# 此处补 分区→attach 的端到端)。
```

### 11. `frontend/src/components/AuctionHistoryChart.tsx` (new, component / chart render)

**Analog:** `EChartsIntraday.tsx:407-591`（生命周期 + buildOption + useChartTheme）+ `EChartsCandlestick.tsx:107-117`（bar series）+ `EChartsCandlestick.tsx:658-677`（双 yAxis）。

**Imports + 主题（复制 EChartsIntraday.tsx:1-12）:**
```tsx
import { useEffect, useMemo, useRef, useState } from 'react'
import * as echarts from 'echarts'
import type { ECharts, EChartsOption } from 'echarts'
import type { AuctionHistoryRow } from '@/lib/api'
import { useChartTheme, type ChartTheme } from '@/lib/theme'
```

**ECharts 生命周期（复制 EChartsIntraday.tsx:446-520 的 init/ResizeObserver/dispose 骨架）:**
```tsx
// EChartsIntraday.tsx 同款: containerRef + chartRef + ResizeObserver
const containerRef = useRef<HTMLDivElement>(null)
const chartRef = useRef<ECharts | null>(null)
const roRef = useRef<ResizeObserver | null>(null)
const ct = useChartTheme()

useEffect(() => {
  const el = containerRef.current
  if (!el) return
  let chart = chartRef.current
  if (!chart) {
    chart = echarts.init(el, undefined, { renderer: 'canvas' })
    chartRef.current = chart
    roRef.current = new ResizeObserver(() => chart!.resize())
    roRef.current.observe(el)
  }
  if (rows.length > 0) {
    chart.setOption(buildOption(rows, ct), true)
  } else {
    chart.clear()   // 空态不渲染零值柱
  }
}, [rows, ct, height])

useEffect(() => {
  return () => {
    roRef.current?.disconnect()
    chartRef.current?.dispose()
    chartRef.current = null
    roRef.current = null
  }
}, [])
```

**双轴 option（柱=竞价量, 线=竞价金额; 镜像 EChartsCandlestick.tsx:658-677 的多 yAxis 结构）:**
```ts
// EChartsCandlestick.tsx:658-677 的多 yAxis (gridIndex + axisLabel 主题色) 结构 →
// CHART-02: 一个 category xAxis (date), 两个 yAxis:
//   yAxis[0] = 竞价量(股, 柱, 左轴)  yAxis[1] = 竞价金额(元, 线, 右轴)
// series: [{ name:'竞价量', type:'bar',  yAxisIndex:0, data: volume },
//          { name:'竞价金额', type:'line', yAxisIndex:1, data: amount }]
// 轴标签单位由 axisLabel.formatter 承载 (股/元), 不混排派生列
```

**诚实空态 + 窗口标注（镜像 StockIntradayChart.tsx:36-43 的空态文案 + EmptyState.tsx）:**
```tsx
// rows 空 或 available===false:
//   <EmptyState icon={BarChart3} title="无历史竞价数据"
//     hint="需配置集合竞价数据源并开启 EOD 竞价同步 · 窗口 09:15-09:25" />
// probe 非 available 时窗口标注降级为「窗口 09:15-09:25（数据源未配置）」
```

### 12. `frontend/src/components/StockPreviewDialog.tsx` (modified, component / render)

**Analog（in-file）:** `StockPreviewDialog.tsx:42,162-167,238-240`。

**第三 toggle state（复制 :42 的 showIntraday 模式）:**
```tsx
// StockPreviewDialog.tsx:42 — 加同款
const [showAuction, setShowAuction] = useState(false)
```

**toggle 按钮（复制 :162-167 的「分时」按钮形态, 换图标/文案）:**
```tsx
// StockPreviewDialog.tsx:162-167 — 镜像「分时」按钮
<button
  onClick={() => setShowAuction((v) => !v)}
  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs transition-colors ${
    showAuction
      ? 'bg-accent/15 text-accent border border-accent/30'
      : 'bg-elevated text-secondary border border-border hover:border-accent/30'
  }`}
>
  <Gavel className="h-3 w-3" />
  竞价历史
</button>
```

**传 props（复制 :238-240 的 showIntraday 透传）:** `showAuction={showAuction}` 传给 `StockPanel`。

### 13. `frontend/src/components/StockPanel.tsx` (modified, component / render)

**Analog（in-file）:** `StockPanel.tsx:153-163`。

**新增 prop + 条件渲染（复制 :153-163 的 StockIntradayChart 条件块）:**
```tsx
// StockPanel.tsx:19 附近 Props 加 showAuction?: boolean
// StockPanel.tsx:153-163 旁并列:
{showAuction && (
  <AuctionHistoryChart symbol={symbol} height={height} className="flex-1 min-w-0 border-l border-border pl-3" />
)}
```

### 14. `frontend/src/lib/api.ts` (modified, utility/client)

**Analog（in-file）:** `api.ts:1918-1930 klineDaily` + `:22-45 request`。

**新方法（复制 klineDaily 的 GET 形态）:**
```ts
// api.ts:1918-1930 klineDaily 结构 → auctionHistory
export interface AuctionHistoryRow {
  date: string
  auction_volume: number | null
  auction_amount: number | null
  row_count: number
  min_datetime?: string | null
  max_datetime?: string | null
}

auctionHistory: (symbol: string, days = 30) =>
  request<{
    symbol: string
    name?: string
    available: boolean
    probe: AuctionProbeVerdict          // 复用 api.ts:67-70 已有接口
    coverage: number
    window: string
    rows: AuctionHistoryRow[]
    unit?: { auction_volume: string; auction_amount: string }
  }>(`/api/kline/auction/history?symbol=${encodeURIComponent(symbol)}&days=${days}`),
```

### 15. `frontend/src/lib/queryKeys.ts` (modified, config)

**Analog（in-file）:** `queryKeys.ts` `QK.kline`/`QK.klineMinute`。

```ts
// queryKeys.ts — Kline 段 (同 QK.kline 工厂模式)
auctionHistory: (symbol: string, days: number) => ['kline-auction-history', symbol, days] as const,
```
**注意:** 历史竞价数据不可变——不要加入 `SSE_INVALIDATE_PREFIXES`（`:172-183`），避免行情 tick 无效刷新。

### 16. `frontend/src/lib/useSharedQueries.ts` (modified, hook)

**Analog:** `useSharedQueries.ts:85-91 useAuctionProbe`。

```ts
// useSharedQueries.ts — 镜像 useAuctionProbe 的 useQuery 封装
export function useAuctionHistory(symbol: string, days = 30) {
  return useQuery({
    queryKey: QK.auctionHistory(symbol, days),
    queryFn: () => api.auctionHistory(symbol, days),
    enabled: !!symbol,
    staleTime: 5 * 60_000,   // 历史不可变, 大幅 stale
  })
}
```

### 17. `frontend/e2e/auction-history.spec.ts` (new, test / e2e mock)

**Analog:** `pool-hub.spec.ts:268-309 installShell` + `:261-262 unhandled` + `:127-184` auction fixtures + `json()` route override（后注册优先）。

**Shell + 三态 mock（复制 installShell 骨架, 追加本端点路由）:**
```ts
// pool-hub.spec.ts:268-309 — installShell 复制, 增:
await page.route('**/api/kline/auction/history**', route => {
  const symbol = new URL(route.request().url()).searchParams.get('symbol') ?? ''
  const body = symbol === '300750.SZ'
    ? auctionHistoryPayload         // 有数据: rows 多日 + available:true + probe available
    : emptyHistoryPayload           // available:false + rows:[]
  return json(route, body)
})
```
**用例:** 有数据 → 图渲染 + 轴标签单位（`股`/`元`）; mock 空/`available:false` → 诚实空态文案可见; mock probe 非 available → 空态 + 窗口标注; 打开个股弹窗（从 pool-hub 钻取）→ 竞价历史 tab 可见（`test.skip(project !== DESKTOP_PROJECT)` 沿用 pool-hub.spec 惯例）。

## Shared Patterns

### 后端: probe×分区双闸门
**Source:** `auction_columns.py:93-107`。**Apply to:** `auction_history.py`（CHART-01）、`auction_columns.py`（CHART-03 读路径验证）。
```python
if resolve_auction_probe().status != AuctionProbeStatus.available:
    return <honest-empty>
part = repo.store.data_dir / "kline_auction" / f"date={trade_date.isoformat()}" / "part.parquet"
if not part.exists() or pl.read_parquet(part).is_empty():
    return <honest-empty>
```

### 后端: 诚实空态 `available:false` (200, 非 404/500)
**Source:** `pool.py:79-113 get_pool_history`（`:88` 语义 + `:100-107` 校验）。**Apply to:** CHART-01 端点。
```python
# 快照/湖缺失 → available: False 空态 (200); 非法参数 → 400 (绝不把非法输入带进文件系统)
```

### 后端: 写湖原子写 + merge-upsert
**Source:** `auction_sync.py:37-48` + `:135-144`。**Apply to:** CHART-03（写路径不变, 仅扩列）。
```python
tmp = out.with_name(out.name + ".tmp"); df.write_parquet(tmp); tmp.replace(out)
day_df = pl.concat([existing, day_df]).unique(subset=["symbol", "datetime"], keep="last")
```

### 后端: hermetic 测试
**Source:** `test_auction_columns.py:20-32,58-61` + `test_auction_sync.py:14-25,30-42`。**Apply to:** `test_auction_history.py` + 两个既有测试扩展。模式 = `tmp_path + monkeypatch(settings.data_dir)` + `_write_auction_partition`/`FakeAuctionProvider` + 生产 import 放测试函数内（避免 collection 时导入 DuckDB 单例）。

### 前端: ECharts 生命周期
**Source:** `EChartsIntraday.tsx:446-520`。**Apply to:** `AuctionHistoryChart.tsx`。模式 = `echarts.init(el, undefined, {renderer:'canvas'})` + `ResizeObserver(chart.resize)` + `setOption(option, true)` + 卸载 `dispose`；画布不吃 CSS 变量 → 统一 `useChartTheme()`（`lib/theme.ts`）。

### 前端: React Query 查询链路
**Source:** `api.ts:22-45 request` + `:1918-1930 klineDaily` + `queryKeys.ts` + `useSharedQueries.ts:85-91 useAuctionProbe`。**Apply to:** CHART-02 全链路。模式 = `QK` 工厂 → `api.<method>` 类型化 → `useQuery({queryKey, queryFn, enabled, staleTime})`。

### 前端: e2e installShell mock
**Source:** `pool-hub.spec.ts:268-309`。**Apply to:** `auction-history.spec.ts`。模式 = `page.route('**/api/**', unhandled)` 兜底 + 具体路由后注册覆盖 + `test.skip(project !== DESKTOP_PROJECT)`。

## 复用什么 / 避开什么

### 复用什么（零新增）
| 复用点 | 位置 | 用途 |
|---|---|---|
| `kline_auction` DuckDB 视图 | `repository.py:162-163` | CHART-01 数据源（`read_parquet('{d}/kline_auction/**/*.parquet', union_by_name=true)`） |
| `resolve_auction_probe()` + `/api/data/auction-probe` 30s TTL | `auction_probe.py` + `data.py:55-58,626-638` | CHART-01 响应 `probe` + 空态判定 |
| `attach_auction_columns` 双闸门 + `compute_auction_unmatched_amount` | `auction_columns.py:89-151,35-51` | CHART-03 读路径派生已实现, 只缺写路径保留输入列 |
| 原子写 + merge-upsert | `auction_sync.py:37-48,135-144` | CHART-03 写湖路径原样 |
| POOL-03 GET-only + available:false | `pool.py:1-7,88,100-107` | CHART-01 端点纪律 |
| ECharts in-tree + `useChartTheme` + `EmptyState` | `frontend/package.json`; `lib/theme.ts`; `components/EmptyState.tsx` | CHART-02 图 + 空态 |
| hermetic 测试 helper | `test_auction_columns.py:58-61`; `test_auction_sync.py:14-42` | CHART-01/03 测试 |
| e2e installShell + json route override | `pool-hub.spec.ts:268-309,261-262` | CHART-02 e2e |

### 避开什么
1. **CHART-04 虚拟成交实时列 — 本期只研究不实现**（research OQ-1, 阻塞于外部实时竞价源）。不建盘前轮询/SSE 推送/新数据源接入；`_run_auction_sync` 的 probe 双闸门已有, 不加实时回填路径。
2. **`frontend/src/pages/Watchlist.tsx` — 用户未提交改动, 绝不修改/提交**（只可 grep 契约）。
3. **guest 掩码（`mask_guest_hub` / `guest_masking.py`）** — CHART-01 按 symbol 取历史序列, 非股池行集；前端弹窗在 VIP 上下文。不要复制 guest 面逻辑。
4. **Phase 23「派生·虚拟成交」分组回归** — 派生列与真实列分列共存、永不相加（`auction_columns.py:35-51` + `pipeline.py:160` 估算标注 + `test_auction_columns.py test_unmatched_proxy_never_mixed_with_real`）；CHART-02 只画真实 `auction_volume/auction_amount`。
5. **0 填充 / 404** — 空湖/缺 symbol → 200 `available:false` + 诚实空态；列缺席不 null-as-present、不 0 填。
6. **空湖 live-fetch 兜底** — `kline.get_daily` 的 `sync_daily_batch` 兜底（`kline.py:159-181`）是反面教材；CHART-01 严禁复制。
7. **`_table_cache`/`_compute_storage` 非必需改动** — 仅当 CHART-01 暴露 coverage 天数时把 `kline_auction` 纳入 storage 统计（`data.py:484-533`）, 否则不动。
8. **零新 npm/pip 依赖** — echarts/echarts-for-react 在册; 后端只用既有 seams。

## 命名与约定

- **后端 service 家族:** 新服务命名 `auction_history.py`, 加入既有 `auction_*` 家族（`auction_columns.py` / `auction_sync.py` / `auction_probe.py`）; 模块 docstring 声明读/写边界 + probe 门控（镜像 `auction_columns.py:1-14`）。
- **端点:** `GET /api/kline/auction/history?symbol=&days=` 挂 `kline.py`（prefix `/api/kline`, tags=["kline"], `kline.py:15`）; `days` 约束 `ge=1, le=120`; 响应含 `available/probe/coverage/window/rows/unit`, `rows` 按 `date` 升序。
- **窗口边界单一事实源:** `_WINDOW_START_MIN/_WINDOW_END_MIN`（`auction_sync.py:29-30` / `auction_probe.py:23-24` 逐字一致）——CHART-01 复用, 勿重新定义。
- **canonical 列语义:** 「4 必需 + 2 可选」; 可选列源不提供即缺席（诚实缺列）; 派生 `auction_unmatched_amount` 恒带「估算」标注（`pipeline.py:160` / `data.py:769-774`）。
- **前端:** 组件 `AuctionHistoryChart.tsx`（与 `StockIntradayChart`/`StockDailyKChart` 命名对齐）; hook `useAuctionHistory`（若走 `useSharedQueries.ts`）; key `QK.auctionHistory(symbol, days)`; api 方法 `auctionHistory(symbol, days)`。
- **测试:** 新建 `test_auction_history.py`; 扩展 `test_auction_sync.py`/`test_auction_columns.py`; 全 hermetic, 命令 `cd backend && .venv/bin/python -m pytest tests/test_auction_history.py -x -q` 与三套回归 `-x -q` 全绿。
- **e2e:** 新建 `frontend/e2e/auction-history.spec.ts`（复用 `pool-hub.spec.ts` 的 installShell 风格）; 前端验证 = `npm run build` + Playwright e2e; 不碰 `Watchlist.tsx`。

## Metadata

**Analog search scope:** `backend/app/api/`（kline.py, pool.py, data.py, routes.py）; `backend/app/services/`（auction_columns.py, auction_sync.py, pool_hub.py, extend_history.py）; `backend/app/data_providers/custom/provider.py`; `backend/app/tickflow/repository.py`; `backend/app/indicators/pipeline.py`; `backend/tests/`（test_auction_columns.py, test_auction_sync.py, test_auction_strategy_family.py）; `frontend/src/components/`（StockPreviewDialog.tsx, StockPanel.tsx, EChartsIntraday.tsx, EChartsCandlestick.tsx, StockIntradayChart.tsx, EmptyState.tsx）; `frontend/src/lib/`（api.ts, queryKeys.ts, useSharedQueries.ts, theme.ts）; `frontend/e2e/pool-hub.spec.ts`。
**Files scanned:** ~25（含只读结构确认）
**Pattern extraction date:** 2026-08-06
**约束遵守:** 只读研究; 未修改任何源码（仅产出本 PATTERNS.md）; `Watchlist.tsx` 未 read/修改（仅从 Phase 25 PATTERNS 引用既有契约）。
