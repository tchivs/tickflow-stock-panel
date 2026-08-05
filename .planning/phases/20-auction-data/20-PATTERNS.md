# Phase 20: 竞价数据层 (Auction Data) - Pattern Map

**Mapped:** 2026-08-05
**Files analyzed:** 8 (6 修改 / 2 新增)
**Analogs found:** 8 / 8

> 本文件把 Phase 20 的每个新建/修改文件映射到仓库内最接近的既有实现,并给出可直接复制/镜像的具体代码段(带文件路径与行号)。probe 门控的竞价数据路径在仓库中已有 DATA-03 落地代码(`auction_probe` / `test_auction_probe` / provider `_normalize_auction`),本期的湖摄入、受管列登记、偏好旋钮、管道 stage、视图重建全部可镜像既有 seam,无"无类比"硬骨头。

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/app/services/auction_sync.py` (new) | service | batch (lake ingest) | `kline_sync.sync_and_persist_minute` + `_atomic_write_parquet` (kline_sync.py:73-84, 829-926) | exact |
| `backend/app/indicators/pipeline.py` (modified) | config/registry | transform | `ENRICHED_COLUMNS` / `ENRICHED_COLUMNS_BY_CATEGORY` (pipeline.py:57-179) | exact |
| `backend/tests/test_auction_sync.py` (new) | test | batch | `test_auction_probe.py` `FakeAuctionProvider` fixture (25-57) | role-match |
| `backend/tests/test_auction_columns.py` (new) | test | transform | `test_auction_probe.py` 四状态 hermetic 判定 (65-128) | role-match |
| `backend/app/services/preferences.py` (modified) | config | CRUD | `get_minute_sync_enabled` / `get_minute_sync_days` / `get_minute_sync_symbols` (89-126) | exact |
| `backend/app/jobs/daily_pipeline.py` (modified) | job | batch | Step 2.5 `sync_minute` (561-588) + `_resolve_minute_symbols` (656-665) + `_refresh_single_view` (626-653) | exact |
| `backend/app/tickflow/repository.py` (modified) | repository | CRUD | `rebuild_views` views dict (1649-1682) | exact |
| `backend/app/api/data.py` (modified) | controller/API | request-response | `_SCHEMA_VIEWS` / `_TABLE_FIELD_DESC` (725-818) | exact |

## Pattern Assignments

### 1. `backend/app/services/auction_sync.py` (new, service / batch lake ingest)

**Analog:** `kline_sync.py` — `sync_and_persist_minute` (829-926) + `_atomic_write_parquet` (73-84) + `can_sync_minute` 能力门 (53-59)

**Imports pattern** (kline_sync.py:8-21) — 镜像模块头:
```python
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, timedelta

import polars as pl

from app.indicators.pipeline import filter_halt_days
from app.services import preferences
from app.tickflow.capabilities import Cap, CapabilitySet
from app.tickflow.client import get_client
from app.tickflow.rate_limits import chunked, resolve_limit, sleep_between_batches
from app.tickflow.repository import KlineRepository

logger = logging.getLogger(__name__)
```

**原子写 helper — 直接复用语义** (kline_sync.py:73-84; repository 版 1684-1694 同语义):
```python
def _atomic_write_parquet(df: pl.DataFrame, out) -> None:
    """先写临时文件再原子替换, 避免进程中断留下损坏的 parquet。…"""
    tmp = out.with_name(out.name + ".tmp")
    df.write_parquet(tmp)
    tmp.replace(out)  # 同目录 rename, POSIX/NTFS 均为原子操作
```
> `auction_sync` **禁止另造写路径**;镜像 `_atomic_write_parquet`(或直接 import kline_sync 的版本)。

**核心批量同步签名** (kline_sync.py:829-840) — `sync_and_persist_auction` 按同形签名:
```python
def sync_and_persist_minute(
    symbols: list[str],
    repo: KlineRepository,
    capset: CapabilitySet,
    days: int = 5,
    on_chunk_done: Callable[[int, int], None] | None = None,
) -> int:
    """同步分钟 K 并存到 Parquet(仅 raw,不前复权)。返回写入行数。…"""
```

**按日分区 + merge-upsert 循环** (kline_sync.py:892-912) — `kline_auction/date={d}/part.parquet` 直接镜像:
```python
# 按日期分区写: data/kline_minute/date={YYYY-MM-DD}/part.parquet
df = df.with_columns(pl.col("datetime").dt.date().alias("_trade_date"))
written = 0
for day_df in df.partition_by("_trade_date"):
    trade_date = day_df["_trade_date"][0]
    out = repo.store.data_dir / "kline_minute" / f"date={trade_date}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        existing = pl.read_parquet(out)
        day_df = pl.concat([existing, day_df.drop("_trade_date")]).unique(
            subset=["symbol", "datetime"], keep="last",
        )
    else:
        day_df = day_df.drop("_trade_date")
    day_df = day_df.sort("symbol", "datetime")
    _atomic_write_parquet(day_df, out)
    written += day_df.height
```

**能力门 → 竞价门(divergence)** — `can_sync_minute` (kline_sync.py:53-59) 是 provider/capability 判定;`auction_sync` 换成 probe 判定:
```python
def can_sync_minute(capset: CapabilitySet) -> bool:
    """Whether the selected minute provider or TickFlow can fetch minute data."""
    provider_name = preferences.get_minute_data_provider()
    return (
        get_custom_data_provider("minute", provider_name) is not None
        or capset.has(Cap.KLINE_MINUTE_BATCH)
    )
```
```python
# auction_sync 生产侧闸门 — 权威唯一: resolve_auction_probe().status == "available"
verdict = resolve_auction_probe()
if verdict.status != AuctionProbeStatus.available:
    return 0                      # fail-closed: 不写湖
```

**窗口谓词(单一事实源)** — 写湖过滤器必须与 provider 归一化同一谓词 (custom/provider.py:149-160):
```python
@staticmethod
def _normalize_auction(df: pl.DataFrame) -> pl.DataFrame:
    """把映射后的 df 裁剪为 auction canonical 列, 只保留 09:15–09:25 窗口内行。"""
    if df.is_empty():
        return df
    if "datetime" in df.columns:
        if df.schema["datetime"] != pl.Datetime("us"):
            df = df.with_columns(pl.col("datetime").cast(pl.Datetime("us"), strict=False))
        _mins = pl.col("datetime").dt.hour().cast(pl.Int32) * 60 + pl.col("datetime").dt.minute().cast(pl.Int32)
        df = df.filter((_mins >= 555) & (_mins <= 565))
    keep = [c for c in ("symbol", "datetime", "auction_volume", "auction_amount") if c in df.columns]
    return df.select(keep) if keep else pl.DataFrame()
```
> canonical 列:`symbol, datetime, auction_volume, auction_amount`。窗口常量以 `auction_probe.py:23-24` 的 `_WINDOW_START_MIN = 555` / `_WINDOW_END_MIN = 565` 为权威。

**Provider 取数 seam** — `get_auction` (custom/provider.py:129-147) 已是既有实现;`auction_sync` 通过 `_first_auction_provider()`(枚举候选源,镜像 `auction_probe._default_sources` auction_probe.py:86-114)取 provider。

---

### 2. `backend/app/indicators/pipeline.py` (modified, registry)

**Analog:** 模块内 `ENRICHED_STORAGE_COLS` (57-67) + `ENRICHED_COLUMNS` (75-161) + `ENRICHED_COLUMNS_BY_CATEGORY` (164-179) + `_ALL_INDICATOR_COLS`/`_resolve_needed` (308-335)

**注册表条目格式** (pipeline.py:75-95) — 新增两列沿同形 dict[str, str] 中文描述:
```python
ENRICHED_COLUMNS: dict[str, dict[str, str]] = {
    # ── 存储列 (parquet 持久化) ──────────────────────────
    "symbol":                  "股票代码",
    "date":                    "交易日期",
    ...
    "open_gap":                "开盘涨幅 (open/prev_close−1, 小数)",
    # ── JOIN 列 (由 repository 从 instruments 表补充) ───
    "name":                    "股票名称 (来自 instruments)",
    ...
}
```
```python
# 新增 (DATA-04):
#   "auction_volume": "竞价量 (集合竞价撮合成交量, 单位: 股; 仅 probe available 时存在)",
#   "auction_amount": "竞价金额 (集合竞价撮合成交额, 单位: 元; 仅 probe available 时存在)",
```

**分类表条目格式** (pipeline.py:164-179):
```python
ENRICHED_COLUMNS_BY_CATEGORY: dict[str, list[str]] = {
    "basic":    ["prev_close", "change_pct", "change_amount", "amplitude", "open_gap"],
    "signals":  [k for k in ENRICHED_COLUMNS if k.startswith("signal_")],
    "join":     ["name", "total_shares", "float_shares"],
    # 新增: "auction": ["auction_volume", "auction_amount"],
}
```

**存储窄表(divergence: 不进)** (pipeline.py:57-67) — 竞价列**绝不**加入此列表:
```python
ENRICHED_STORAGE_COLS = [
    "symbol", "date",
    "open", "high", "low", "close",          # 前复权
    "volume", "amount",
    "raw_close", "raw_high", "raw_low",       # 不复权原始价
    "turnover_rate",                           # 依赖当时的 float_shares, 不可回推
    "consecutive_limit_ups",                   # 递推状态, 需从历史 cum_sum
    "consecutive_limit_downs",
    "quote_ts",                                # 行情时间戳(ms): 盘后校验/量比折算/跨天完整性
    "open_gap",                                # 开盘涨幅 (open/prev_close−1), 同天 open/前日 close
]
```

**计算闭包(divergence: 不进)** (pipeline.py:308-335) — `auction_*` 不可从 OHLCV 重算,混入会破坏 `_resolve_needed` 的"计算闭包=可重算"不变量;在 `_ALL_INDICATOR_COLS` 上方加注释:
```python
#  "auction_* 列不由 compute_indicators 计算, 由读路径从 kline_auction 湖左联注入; 缺列即 probe 不可用。"
_ALL_INDICATOR_COLS: frozenset[str] = frozenset({
    "prev_close", "ma5", "ma10", "ma20", "ma30", "ma60",
    ...
})
```

---

### 3. `backend/tests/test_auction_sync.py` (new) + `backend/tests/test_auction_columns.py` (new)

**Analog:** `test_auction_probe.py` — `FakeAuctionProvider` hermetic fixture + 四状态回归

**Imports + 假 provider 模式** (test_auction_probe.py:1-22, 25-37):
```python
from app.api import data as data_api
from app.services.auction_probe import (
    FAIL_CLOSED_DETAIL,
    NOT_CONFIGURED_DETAIL,
    AuctionProbeStatus,
    resolve_auction_probe,
)

class FakeAuctionProvider:
    """极简假 provider: 可注入预置行或抛错, 用于强制每个探测状态。"""
    name = "fake_auction"

    def __init__(self, rows: pl.DataFrame | None = None, exc: Exception | None = None) -> None:
        self.rows = rows
        self.exc = exc

    def get_auction(self, symbols: list[str], trade_date: datetime) -> pl.DataFrame:
        if self.exc is not None:
            raise self.exc
        return self.rows if self.rows is not None else pl.DataFrame()
```

**行构造 + probe 注入 helper** (test_auction_probe.py:40-57):
```python
def _rows(*minutes_and_seconds: tuple[int, int]) -> pl.DataFrame:
    """构造 probe 行, 时间 = 2026-08-04 09:{m}:{s}。"""
    return pl.DataFrame({
        "symbol": ["000001"] * len(minutes_and_seconds),
        "datetime": [datetime(2026, 8, 4, 9, m, s) for m, s in minutes_and_seconds],
        "auction_volume": [100] * len(minutes_and_seconds),
    })

def _probe(provider: FakeAuctionProvider) -> dict:
    return resolve_auction_probe(
        source_resolver=lambda: [provider],
        fetcher=lambda p, symbols, trade_date: p.get_auction(symbols, trade_date),
    ).to_dict()
```

**09:30 结构性排除回归模板** (test_auction_probe.py:82-87) — `test_auction_sync.py::test_0930_excluded` 沿此形态:
```python
def test_0930_only_rows_are_fail_closed_never_available():
    """T-16-01: 09:30+ 连续竞价 bar 永远不能产生 available。"""
    verdict = _probe(FakeAuctionProvider(rows=_rows((30, 0), (31, 0))))
    assert verdict["status"] == "fail_closed"
    assert verdict["detail"] == FAIL_CLOSED_DETAIL
```

**probe 状态 × 列矩阵回归模板** (test_auction_probe.py:108-128) — `test_auction_columns.py` 沿此形态遍历状态:
```python
def test_verdict_window_and_fallback_are_fixed_for_every_status():
    """每个状态都携带固定的 window="09:15-09:25" 与 fallback="open_gap"。"""
    ...
        assert verdict["fallback"] == "open_gap"

def test_all_0930_rows_can_never_produce_available():
    """结构性守卫: 全部 >= 09:30 的行只能 fail_closed, 永不 available。"""
    ...
        assert verdict["status"] != "available"
```
> `test_auction_columns.py` 新增矩阵:available → 注入真实列;not_configured / fail_closed / error → 缺列 + `open_gap` 恒在;error 详情 ≤200 字符 (`_ERROR_DETAIL_MAX`, auction_probe.py:30)。

---

### 4. `backend/app/services/preferences.py` (modified, config / CRUD)

**Analog:** minute 偏好旋钮 — `get_minute_sync_enabled` (89-90) + `get_minute_sync_days` (98-99) + `_normalize_symbol_list` (101-115) + `get_minute_sync_symbols` (117-119) + `set_minute_sync_symbols` (122-126)

**布尔开关 + 天数 clamp** (preferences.py:89-99) — `auction_sync_enabled` / `auction_sync_days` 镜像:
```python
def get_minute_sync_enabled() -> bool:
    return load().get("minute_sync_enabled", False)

def get_minute_sync_days() -> int:
    return max(1, min(30, load().get("minute_sync_days", 5)))
```

**标的列表规范化 + get/set** (preferences.py:101-126) — `auction_sync_symbols` 镜像:
```python
def _normalize_symbol_list(value) -> list[str]:
    """规范化标的列表: 按逗号/换行拆分、去空白、去空、保序去重。"""
    if value is None:
        return []
    ...

def get_minute_sync_symbols() -> list[str]:
    """可选分钟 K 同步标的范围; 空列表 = 全量标的池 (research pitfall 3)。"""
    return _normalize_symbol_list(load().get("minute_sync_symbols", []))

def set_minute_sync_symbols(symbols: list[str]) -> list[str]:
    """保存分钟 K 同步标的范围, 返回规范化后的列表; 空列表 = 全量。"""
    clean = _normalize_symbol_list(symbols)
    save({"minute_sync_symbols": clean})
    return clean
```
> 新增 knob:`get_auction_sync_enabled()`(默认 False,镜像 minute 的"显式开启"语义)+ `get_auction_sync_symbols()` / `set_auction_sync_symbols()`。probe `available` 是必要非充分条件。

---

### 5. `backend/app/jobs/daily_pipeline.py` (modified, job / batch)

**Analog:** Step 2.5 `sync_minute` (561-588) + `_resolve_minute_symbols` (656-665) + `_refresh_single_view` (626-653)

**模块级偏好 import** (daily_pipeline.py:24):
```python
from app.services import index_sync, instrument_sync, kline_sync, preferences as _prefs
```

**管道 stage 模板 (Step 2.6 镜像 Step 2.5)** (daily_pipeline.py:561-588):
```python
# Step 2.5: 分钟 K 同步(可选) — 未启用或无 capability 时静默跳过(不 emit)
from app.services import preferences
minute_on = preferences.get_minute_sync_enabled()
minute_days = preferences.get_minute_sync_days()
written_minute = 0
if minute_on and kline_sync.can_sync_minute(capset):
    minute_start = today - _td(days=minute_days)
    emit("sync_minute", 90, f"获取分钟K [{minute_start} ~ {today}]…")
    logger.info("sync_minute: [%s ~ %s] start", minute_start, today)
    minute_symbols = _resolve_minute_symbols(capset)
    def _minute_chunk_progress(cur: int, tot: int) -> None:
        emit("sync_minute", 90 + int(3 * cur / tot),
             f"分钟K 批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)
    written_minute = kline_sync.sync_and_persist_minute(
        minute_symbols, repo, capset, days=minute_days,
        on_chunk_done=_minute_chunk_progress,
    )
    minute_dir = repo.store.data_dir / "kline_minute"
    minute_cover_days = len(list(minute_dir.glob("date=*"))) if minute_dir.exists() else 0
    emit("sync_minute", 93, f"分钟K完成,覆盖 {minute_cover_days} 天")
    logger.info("sync_minute: [%s ~ %s] done, %d days", minute_start, today, minute_cover_days)
    _invalidate("minute")
else:
    skipped.append("sync_minute")
    if minute_on:
        logger.info("sync_minute skipped: selected provider has no minute dataset")
    else:
        logger.info("sync_minute skipped: user disabled")
```
> Step 2.6 差异:门控 = `get_auction_sync_enabled()` **且** `resolve_auction_probe().status == "available"`;写后 `_invalidate("auction")` + 视图刷新。进度百分比沿 Stage 布局微调(插在 Step 2.5 与 Step 3 之间)。

**标的范围解析** (daily_pipeline.py:656-665) — `_resolve_auction_symbols` 镜像:
```python
def _resolve_minute_symbols(capset: CapabilitySet) -> list[str]:
    """分钟 K 同步标的 — 默认与日K共用同一标的池。…"""
    scoped = _prefs.get_minute_sync_symbols()
    if scoped:
        return scoped
    return _resolve_universe(capset)
```

**单视图刷新(路径表)** (daily_pipeline.py:626-653) — `kline_auction` 视图在此登记:
```python
def _refresh_single_view(repo: KlineRepository, name: str) -> None:
    """刷新单个 DuckDB 视图。"""
    d = repo.store.data_dir.as_posix()
    paths = {
        "kline_daily": f"{d}/kline_daily/**/*.parquet",
        ...
        "kline_minute": f"{d}/kline_minute/**/*.parquet",
        # 新增: "kline_auction": f"{d}/kline_auction/**/*.parquet",
    }
    path = paths.get(name)
    if not path:
        return
    try:
        repo.db.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_parquet('{path}', union_by_name=true)"
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("refresh view %s failed: %s", name, e)
```

---

### 6. `backend/app/tickflow/repository.py` (modified, repository / CRUD)

**Analog:** `rebuild_views` (1649-1682) — 唯一权威视图重建入口

**视图重建 dict** (repository.py:1649-1682) — `kline_auction` 加入 views dict:
```python
def rebuild_views(self) -> None:
    """重建全部 13 张 parquet 视图并重挂 unified 视图 —— 唯一权威实现。…"""
    d = self.store.data_dir.as_posix()
    views = {
        "kline_daily": f"{d}/kline_daily/**/*.parquet",
        ...
        "kline_minute": f"{d}/kline_minute/**/*.parquet",
        "adj_factor": f"{d}/adj_factor/**/*.parquet",
        # 新增: "kline_auction": f"{d}/kline_auction/**/*.parquet",
    }
    for name, path in views.items():
        try:
            with self._lock:
                self.db.execute(
                    f"CREATE OR REPLACE VIEW {name} AS "
                    f"SELECT * FROM read_parquet('{path}', union_by_name=true)"
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("rebuild view %s failed: %s", name, e)
    with self._lock:
        self.store._register_unified_views()
```

**原子写(同语义,静态方法)** (repository.py:1684-1694):
```python
@staticmethod
def _atomic_write_parquet(df: pl.DataFrame, out: Path) -> None:
    """先写临时文件再原子替换, 避免进程中断留下损坏的 parquet。…"""
    tmp = out.with_name(out.name + ".tmp")
    df.write_parquet(tmp)
    tmp.replace(out)  # 同目录 rename, POSIX/NTFS 均为原子操作
```

---

### 7. `backend/app/api/data.py` (modified, controller / request-response)

**Analog:** `_SCHEMA_VIEWS` / `_TABLE_FIELD_DESC` (725-818) + `auction-probe` 端点 (626-650)

**Data 页 schema 登记** (data.py:725-768) — `kline_auction` 字段描述镜像 `kline_minute`:
```python
_TABLE_FIELD_DESC: dict[str, dict[str, str]] = {
    ...
    "kline_minute": {
        "symbol": "股票代码",
        "datetime": "分钟时间戳",
        "open": "开盘价",
        "high": "最高价",
        "low": "最低价",
        "close": "收盘价",
        "volume": "成交量",
        "amount": "成交额",
    },
    # 新增 "kline_auction":
    #   symbol / datetime / auction_volume("竞价量, 单位: 股") / auction_amount("竞价金额, 单位: 元")
}
```

**视图名登记** (data.py:806-818):
```python
_SCHEMA_VIEWS: dict[str, str] = {
    "daily": "kline_daily",
    ...
    "minute": "kline_minute",
    # 新增: "auction": "kline_auction",
}
```

**probe 端点(既有,不改语义)** (data.py:626-650) — 生产侧闸门已在端点层暴露:
```python
@router.get("/auction-probe")
def auction_probe() -> dict:
    """竞价数据探测 — 服务端权威判定, 30s TTL 缓存。"""
    global _auction_probe_cache, _auction_probe_cache_ts
    now = time.time()
    if _auction_probe_cache is not None and (now - _auction_probe_cache_ts) < _AUCTION_PROBE_TTL:
        return _auction_probe_cache
    from app.services.auction_probe import resolve_auction_probe
    verdict = resolve_auction_probe().to_dict()
    _auction_probe_cache = verdict
    _auction_probe_cache_ts = now
    return verdict
```

---

## Shared Patterns

### Probe 门控(生产侧 + 读路径唯一闸门)
**Source:** `backend/app/services/auction_probe.py:139-185` (`resolve_auction_probe`)
**Apply to:** `auction_sync.py`(写湖)、读路径左联(注入)、`daily_pipeline.py` Step 2.6
```python
verdict = resolve_auction_probe()
if verdict.status != AuctionProbeStatus.available:
    return 0   # fail-closed: 不写湖 / 缺列
```
状态枚举 `AuctionProbeStatus: not_configured / available / fail_closed / error`(auction_probe.py:33-37);`_ERROR_DETAIL_MAX = 200`(auction_probe.py:30);`NOT_CONFIGURED_DETAIL` / `FAIL_CLOSED_DETAIL` 文案逐字(auction_probe.py:26-27)。

### 窗口谓词 555..565(单一事实源)
**Source:** `custom/provider.py:149-160`(`_normalize_auction`)与 `auction_probe.py:23-24`(`_WINDOW_START_MIN`/`_WINDOW_END_MIN`)
**Apply to:** `auction_sync` 写湖过滤器、`test_auction_sync.py::test_0930_excluded`
`(mins >= 555) & (mins <= 565)` → 09:30 连续竞价 bar 结构性排除,湖内物理无位置。

### 原子写 Parquet
**Source:** `kline_sync.py:73-84` / `repository.py:1684-1694`(同语义,`.tmp` + `replace`)
**Apply to:** `auction_sync` 湖写入;禁止另造写路径。

### 视图重建
**Source:** `repository.py:1649-1682`(`rebuild_views` 权威)+ `daily_pipeline.py:626-653` / `extend_history.py:68-87`(`_refresh_single_view` 路径表)
**Apply to:** `kline_auction` 视图登记;所有路径表同步补 `"kline_auction"` 条目。

### 偏好旋钮模式
**Source:** `preferences.py:89-126`(布尔开关 + `max/min` clamp + `_normalize_symbol_list`)
**Apply to:** `auction_sync_enabled` / `auction_sync_symbols`;`load()/save()` 合并写 JSON。

## Divergences(竞价特有差异,planner 须注意)

1. **生产侧闸门是 probe 而非 capability:** `auction_sync` 准入 = `resolve_auction_probe().status == "available"`,不是 `can_sync_minute` 的 provider/capability 判定(kline_sync.py:53-59);且 `auction_sync_enabled` 偏好(默认 False)是必要非充分条件(A3, RESEARCH.md:351)。
2. **单位 canonical 股/元:** `auction_volume` 单位股、`auction_amount` 单位元;换算在 `get_auction` / `_normalize_auction` provider 边界完成(custom/provider.py:149-160),越界只认 canonical;fixture 锁定 1 手=100 股(RESEARCH.md:365)。
3. **不进 `ENRICHED_STORAGE_COLS`:** 竞价列只登记 `ENRICHED_COLUMNS` + `ENRICHED_COLUMNS_BY_CATEGORY["auction"]`,绝不加入 pipeline.py:57-67 那 15 列存储窄表(不可从 OHLCV 重算)。
4. **不进 `_ALL_INDICATOR_COLS` 计算闭包:** 破坏 `_resolve_needed` 的"计算闭包=可重算"不变量(pipeline.py:308-335)。
5. **读路径左联而非物化:** 数值在服务层按 `(probe available && kline_auction/date={d} 分区存在且有行)` 左联注入;不在 `compute_indicators` 内计算(RESEARCH.md:375)。
6. **`_refresh_single_view` 路径表有 3 份拷贝:** `daily_pipeline.py:629-643`、`extend_history.py:71-77`(仅 5 表子集)、`api/kline.py:617-618`(复用 daily_pipeline)。`kline_auction` 视图需在 `rebuild_views`(权威)与各 paths 表同步登记,或收敛为单一来源。
7. **按日分区存在性叠加:** 全局 `available` 只证明探测日可用;列注入还要 `date={d}` 分区存在且有行,无分区日期诚实缺列(PITFALL 4, RESEARCH.md:252-256)。

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `backend/tests/test_auction_columns.py` | test | transform | 无现成"probe 状态 × 列返回"矩阵测试;但 hermetic fixture 模式完整复用 `test_auction_probe.py`(四状态 + FakeAuctionProvider),属 role-match 而非无类比 |

其余 7 个文件均有 exact analog;无需要 RESEARCH.md 兜底的 no-analog。

## Metadata

**Analog search scope:** `backend/app/services/`、`backend/app/jobs/`、`backend/app/indicators/`、`backend/app/tickflow/`、`backend/app/api/`、`backend/app/data_providers/custom/`、`backend/tests/`
**Files scanned:** 11 (kline_sync.py, pipeline.py, auction_probe.py, preferences.py, daily_pipeline.py, repository.py, data.py, extend_history.py, custom/provider.py, test_auction_probe.py, api/kline.py)
**Pattern extraction date:** 2026-08-05
**Line numbers verified against live code:** 全部 excerpt 行号在本 session 逐行读取确认。
