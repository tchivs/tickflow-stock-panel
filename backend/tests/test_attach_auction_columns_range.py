"""区间竞价列注入原语 ``attach_auction_columns_range`` (BT-02) — 端到端注入 / 空态 / date 键。

Hermetic: 所有生产 import 放测试函数内 (仓库约定: 模块级不触发 DuckDB 单例);
``kline_auction`` 分区由测试手工写盘; 区间原语**不消费 probe** (历史闸门 = 分区存在性,
D-03 / REV-01), 因此本文件不 monkeypatch probe —— 单日版等价性比较 (Task 2) 才需要。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import polars as pl
import pytest


# ================================================================
# hermetic helpers (镜像 test_auction_columns.py repo_env / _write_auction_partition)
# ================================================================


@pytest.fixture
def repo_env(tmp_path, monkeypatch):
    """隔离的 data_dir + DataStore + KlineRepository (镜像 test_auction_columns.py:20-32)。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    repo = KlineRepository(store)
    try:
        yield repo, data_dir
    finally:
        store.db.close()


def _write_auction_partition(data_dir, trade_date: date, rows: pl.DataFrame) -> None:
    """手工写盘 kline_auction/date=YYYY-MM-DD/part.parquet (镜像 :54-58)。"""
    out = data_dir / "kline_auction" / f"date={trade_date.isoformat()}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.write_parquet(out)


def _multi_day_panel(start: date, days: int = 5) -> pl.DataFrame:
    """多日 enriched 面板: 2 symbols × 连续自然日 (测试即交易日), 确定性 volume。

    volume(第 i 日) = 100000 × (1 + i × 0.1) → 前导日均量可手算 (W2: 1-4 日前导短历史
    用 hand-computed 断言, 不做 <1e-9 面板裁剪等价比较)。
    """
    rows = []
    for i in range(days):
        d = start + timedelta(days=i)
        vol = 100000.0 * (1 + i * 0.1)
        for sym in ("000001", "600000"):
            rows.append({
                "symbol": sym,
                "date": d,
                "open": 10.0 if sym == "000001" else 20.0,
                "close": 10.5 if sym == "000001" else 20.5,
                "volume": vol,
                "amount": vol * 10.0,
                "open_gap": 0.01,
                "change_pct": 0.02,
                "vol_ratio_5d": 1.0,
            })
    return pl.DataFrame(rows)


def _auction_rows(
    trade_date: date,
    symbol_volume: dict[str, tuple[float, float]],
    n_rows: int = 1,
) -> pl.DataFrame:
    """canonical 四列 (symbol, datetime, auction_volume, auction_amount)。

    ``symbol_volume``: {symbol: (auction_volume, auction_amount)}; ``n_rows`` > 1 时
    同一 symbol 写多窗口行 (09:16/09:20/09:25 形), 末行 = 09:25 最终撮合 (keep="last" 语义)。
    """
    _WINDOW_MINUTES = (16, 20, 25)
    rows = []
    for sym, (av, aa) in symbol_volume.items():
        for k in range(n_rows):
            rows.append({
                "symbol": sym,
                "datetime": datetime(trade_date.year, trade_date.month, trade_date.day, 9, _WINDOW_MINUTES[k]),
                "auction_volume": av,
                "auction_amount": aa,
            })
    return pl.DataFrame(rows)


# ================================================================
# Task 1 — Test 1: 端到端注入 (BT-02 主路径, tracer 垂直切片)
# ================================================================


def test_range_end_to_end_injection(repo_env):
    """多分区注入 + enabled_dates + warmup 裁剪 + 无分区日诚实空值。"""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env

    # 面板: 07-27..08-01 (6 日, 含 start=07-29 前 2 个 warmup 前导 + 1 个无分区日 08-01)
    panel = _multi_day_panel(start=date(2026, 7, 27), days=6)

    # 分区: 07-29 (A 2 窗口行 / B 1 行), 07-30 (各 1 行), 07-31 (A 3 窗口行 / B 1 行)
    _write_auction_partition(
        data_dir, date(2026, 7, 29),
        _auction_rows(date(2026, 7, 29), {"000001": (8000.0, 42000.0), "600000": (9000.0, 48000.0)}, n_rows=2),
    )
    _write_auction_partition(
        data_dir, date(2026, 7, 30),
        _auction_rows(date(2026, 7, 30), {"000001": (8100.0, 42500.0), "600000": (9100.0, 48500.0)}),
    )
    _write_auction_partition(
        data_dir, date(2026, 7, 31),
        _auction_rows(date(2026, 7, 31), {"000001": (8200.0, 43000.0), "600000": (9200.0, 49000.0)}, n_rows=3),
    )

    injected, enabled_dates = attach_auction_columns_range(
        panel, start=date(2026, 7, 29), end=date(2026, 7, 31), repo=repo,
    )

    # enabled_dates = 排序去重的非空分区日 (08-01 无分区 → 不在其中)
    assert enabled_dates == [date(2026, 7, 29), date(2026, 7, 30), date(2026, 7, 31)]

    # warmup 裁剪: 注入后无 date < start 行 (07-27/07-28 仅供分母, 不出现在结果)
    assert injected["date"].min() >= date(2026, 7, 29)
    assert injected.height == 4 * 2  # 07-29..08-01 × 2 symbols, 无 fan-out

    # 注入日带真实竞价列 + 派生 ratio 列
    for col in ("auction_volume", "auction_amount", "auction_volume_ratio"):
        assert col in injected.columns

    # 多窗口行去重: 07-31 A 取 09:25 末行值
    a0731 = injected.filter(
        (pl.col("symbol") == "000001") & (pl.col("date") == date(2026, 7, 31))
    )
    assert a0731.height == 1
    assert a0731.select("auction_amount").item() == 43000.0

    # 无分区日 (08-01) → auction 列 null (诚实按日空态, 绝无 null-as-present)
    aug01 = injected.filter(pl.col("date") == date(2026, 8, 1))
    assert aug01.height == 2
    assert aug01.select(pl.col("auction_volume").null_count()).item() == 2
    assert aug01.select(pl.col("auction_volume_ratio").null_count()).item() == 2

    # 首个 enabled 日 (07-29) ratio = 竞价量 ÷ 前 2 日 volume 均值 (hand-computed, W2)
    # 前导: 07-27 vol=100000, 07-28 vol=110000 → 均值 105000
    a0729 = injected.filter(
        (pl.col("symbol") == "000001") & (pl.col("date") == date(2026, 7, 29))
    )
    assert a0729.select("auction_volume_ratio").item() == pytest.approx(8000.0 / 105000.0, rel=1e-9)
    b0729 = injected.filter(
        (pl.col("symbol") == "600000") & (pl.col("date") == date(2026, 7, 29))
    )
    assert b0729.select("auction_volume_ratio").item() == pytest.approx(9000.0 / 105000.0, rel=1e-9)


# ================================================================
# Task 1 — Test 2: 空态 (平台铁律: 绝无异常 / 绝无 null-as-present)
# ================================================================


def test_range_empty_lake_returns_df_and_empty_dates(repo_env):
    """无 kline_auction 目录 → (df, []), 面板原样返回, 无 auction 列。"""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env
    panel = _multi_day_panel(start=date(2026, 7, 29), days=3)

    injected, enabled_dates = attach_auction_columns_range(
        panel, start=date(2026, 7, 29), end=date(2026, 7, 31), repo=repo,
    )

    assert enabled_dates == []
    assert "auction_volume" not in injected.columns
    assert injected.height == panel.height
    # 函数防御性 sort(["symbol","date"]) → 顺序与输入可能不同; 集合语义相等即可
    assert sorted(injected["symbol"].to_list()) == sorted(panel["symbol"].to_list())


def test_range_no_partitions_returns_df_and_empty_dates(repo_env):
    """目录存在但无 date=* 分区 → (df, [])."""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env
    (data_dir / "kline_auction").mkdir(parents=True, exist_ok=True)
    panel = _multi_day_panel(start=date(2026, 7, 29), days=3)

    injected, enabled_dates = attach_auction_columns_range(
        panel, start=date(2026, 7, 29), end=date(2026, 7, 31), repo=repo,
    )

    assert enabled_dates == []
    assert "auction_volume" not in injected.columns


def test_range_empty_panel_returns_df_and_empty_dates(repo_env):
    """df 为空 → (df, []) 绝无异常。"""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env
    _write_auction_partition(
        data_dir, date(2026, 7, 29),
        _auction_rows(date(2026, 7, 29), {"000001": (8000.0, 42000.0)}),
    )

    empty = pl.DataFrame()
    injected, enabled_dates = attach_auction_columns_range(
        empty, start=date(2026, 7, 29), end=date(2026, 7, 31), repo=repo,
    )

    assert enabled_dates == []
    assert injected.height == 0


# ================================================================
# Task 1 — Test 3: date 列键 (分区帧无 date 列 → join 键 ["symbol","date"] 有效)
# ================================================================


def test_range_date_key_join_no_fanout(repo_env):
    """canonical 4 列分区 (无 date 列) → date 取自分区目录名, join 基数 = 面板行数。"""
    from app.services.auction_columns import attach_auction_columns_range

    repo, data_dir = repo_env
    panel = _multi_day_panel(start=date(2026, 7, 29), days=3)

    # 单分区 2 行/symbol (多窗口行) — 去重后每 (symbol, date) 仅 1 行 → 无 fan-out
    _write_auction_partition(
        data_dir, date(2026, 7, 30),
        _auction_rows(date(2026, 7, 30), {"000001": (8100.0, 42500.0), "600000": (9100.0, 48500.0)}, n_rows=2),
    )

    injected, enabled_dates = attach_auction_columns_range(
        panel, start=date(2026, 7, 29), end=date(2026, 7, 31), repo=repo,
    )

    assert enabled_dates == [date(2026, 7, 30)]
    assert injected.height == panel.height  # 行基数不变
    assert injected.filter(pl.col("date") == date(2026, 7, 30)).height == 2
    # 注入值 = 末行 (n_rows=2 → datetime 09:16/09:20, keep="last" = 09:20 行值)
    a0730 = injected.filter(
        (pl.col("symbol") == "000001") & (pl.col("date") == date(2026, 7, 30))
    )
    assert a0730.height == 1
    assert a0730.select("auction_amount").item() == 42500.0
