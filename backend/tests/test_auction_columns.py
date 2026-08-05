"""竞价列读路径注入 (DATA-04 / DATA-06) — 注册纪律 + probe×分区双闸门矩阵。

Hermetic: 所有生产 import 放测试函数内 (仓库约定: 模块级不触发 DuckDB 单例)。
probe 判定被 monkeypatch 为固定 verdict; ``kline_auction`` 分区由测试手工写盘。
"""
from __future__ import annotations

from datetime import date, datetime

import polars as pl
import pytest


# ================================================================
# hermetic helpers
# ================================================================


@pytest.fixture
def repo_env(tmp_path, monkeypatch):
    """隔离的 data_dir + DataStore + KlineRepository (镜像 test_minute_sync_verify)。"""
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


def _daily_frame() -> pl.DataFrame:
    """单日帧: symbol/date/open/close/open_gap。open_gap 恒在, 验证 fail-closed 基准。"""
    return pl.DataFrame({
        "symbol": ["000001", "600000"],
        "date": [date(2026, 8, 4), date(2026, 8, 4)],
        "open": [10.0, 20.0],
        "close": [10.5, 20.5],
        "open_gap": [0.01, 0.02],
    })


def _available_verdict():
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
    return AuctionProbeVerdict(
        status=AuctionProbeStatus.available, source="fake", probed_at=None, detail="available",
    )


def _patch_probe(monkeypatch, verdict) -> None:
    from app.services import auction_columns
    monkeypatch.setattr(auction_columns, "resolve_auction_probe", lambda: verdict)


def _write_auction_partition(data_dir, trade_date: date, rows: pl.DataFrame) -> None:
    out = data_dir / "kline_auction" / f"date={trade_date.isoformat()}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.write_parquet(out)


def _auction_rows() -> pl.DataFrame:
    """canonical 四列 (symbol, datetime, auction_volume, auction_amount), 09:20 窗口内。"""
    return pl.DataFrame({
        "symbol": ["000001", "600000"],
        "datetime": [datetime(2026, 8, 4, 9, 20), datetime(2026, 8, 4, 9, 20)],
        "auction_volume": [8000, 9000],
        "auction_amount": [42000.0, 48000.0],
    })


# ================================================================
# 注册纪律 (硬边界 4)
# ================================================================


def test_registry_discipline():
    """auction_* 三列必须在 ENRICHED_COLUMNS + BY_CATEGORY['auction'], 绝不在存储窄表/计算闭包。"""
    from app.indicators.pipeline import (
        ENRICHED_COLUMNS,
        ENRICHED_COLUMNS_BY_CATEGORY,
        ENRICHED_STORAGE_COLS,
        _ALL_INDICATOR_COLS,
    )
    auction_cols = ["auction_volume", "auction_amount", "auction_unmatched_amount"]
    for c in auction_cols:
        assert c in ENRICHED_COLUMNS, f"{c} 必须注册进 ENRICHED_COLUMNS"
        assert c in ENRICHED_COLUMNS_BY_CATEGORY["auction"], f"{c} 必须属于 BY_CATEGORY['auction']"
        assert c not in ENRICHED_STORAGE_COLS, f"{c} 绝不进存储窄表 (可从 OHLCV 重算)"
        assert c not in _ALL_INDICATOR_COLS, f"{c} 绝不进 compute_indicators 计算闭包"
    # 派生列描述必须带「估算」标注
    assert "估算" in ENRICHED_COLUMNS["auction_unmatched_amount"]


# ================================================================
# probe×分区双闸门矩阵 (硬边界 1 / 5)
# ================================================================


def test_available_with_partition_injects_real_columns(repo_env, monkeypatch):
    repo, data_dir = repo_env
    _patch_probe(monkeypatch, _available_verdict())
    _write_auction_partition(data_dir, date(2026, 8, 4), _auction_rows())

    from app.services.auction_columns import attach_auction_columns
    out = attach_auction_columns(_daily_frame(), date(2026, 8, 4), repo)

    assert "auction_volume" in out.columns
    assert "auction_amount" in out.columns
    assert "open_gap" in out.columns  # fail-closed 基准恒在
    assert out.filter(pl.col("symbol") == "000001").select("auction_volume").item() == 8000
    assert out.filter(pl.col("symbol") == "000001").select("auction_amount").item() == 42000.0
    assert out.filter(pl.col("symbol") == "600000").select("auction_volume").item() == 9000
    assert out.filter(pl.col("symbol") == "600000").select("auction_amount").item() == 48000.0


def test_available_without_partition_keeps_absent(repo_env, monkeypatch):
    """probe available 但无分区 → 诚实按日空态: 列缺席 (非 null 列)。"""
    repo, _ = repo_env
    _patch_probe(monkeypatch, _available_verdict())

    from app.services.auction_columns import attach_auction_columns
    out = attach_auction_columns(_daily_frame(), date(2026, 8, 4), repo)

    assert "auction_volume" not in out.columns
    assert "auction_amount" not in out.columns
    assert "open_gap" in out.columns


def test_non_available_statuses_keep_absent(repo_env, monkeypatch):
    """not_configured / fail_closed / error 三态 → 列缺席 + open_gap 恒在; error 详情 ≤200。"""
    from app.services.auction_probe import (
        _ERROR_DETAIL_MAX,
        AuctionProbeStatus,
        AuctionProbeVerdict,
    )
    repo, _ = repo_env
    error_detail = ("x" * (_ERROR_DETAIL_MAX + 10))[:_ERROR_DETAIL_MAX]  # 沿用 probe 截断原值

    statuses = [
        (AuctionProbeStatus.not_configured, "not configured"),
        (AuctionProbeStatus.fail_closed, "fail closed"),
        (AuctionProbeStatus.error, error_detail),
    ]
    for status, detail in statuses:
        verdict = AuctionProbeVerdict(status=status, source="fake", probed_at=None, detail=detail)
        _patch_probe(monkeypatch, verdict)

        from app.services.auction_columns import attach_auction_columns
        out = attach_auction_columns(_daily_frame(), date(2026, 8, 4), repo)

        assert "auction_volume" not in out.columns
        assert "auction_amount" not in out.columns
        assert "open_gap" in out.columns
        if status == AuctionProbeStatus.error:
            assert len(verdict.detail) <= _ERROR_DETAIL_MAX


def test_partition_empty_keeps_absent(repo_env, monkeypatch):
    """probe available + 分区存在但 0 行 → 列缺席。"""
    repo, data_dir = repo_env
    _patch_probe(monkeypatch, _available_verdict())
    empty = pl.DataFrame(schema={
        "symbol": pl.Utf8,
        "datetime": pl.Datetime("us"),
        "auction_volume": pl.Int64,
        "auction_amount": pl.Float64,
    })
    _write_auction_partition(data_dir, date(2026, 8, 4), empty)

    from app.services.auction_columns import attach_auction_columns
    out = attach_auction_columns(_daily_frame(), date(2026, 8, 4), repo)

    assert "auction_volume" not in out.columns
    assert "auction_amount" not in out.columns


# ================================================================
# 防 fan-out 去重 (WARNING-1)
# ================================================================


def test_partition_multi_row_dedup_no_fanout(repo_env, monkeypatch):
    """分区内同 symbol 多窗口行 (09:16/09:20) → 每 symbol 仅 1 行, 值为去重后 (keep=last)。"""
    repo, data_dir = repo_env
    _patch_probe(monkeypatch, _available_verdict())
    multi = pl.DataFrame({
        "symbol": ["000001", "000001"],
        "datetime": [datetime(2026, 8, 4, 9, 16), datetime(2026, 8, 4, 9, 20)],
        "auction_volume": [7000, 8000],
        "auction_amount": [35000.0, 42000.0],
    })
    _write_auction_partition(data_dir, date(2026, 8, 4), multi)

    from app.services.auction_columns import attach_auction_columns
    df = _daily_frame().filter(pl.col("symbol") == "000001")
    out = attach_auction_columns(df, date(2026, 8, 4), repo)

    assert out.height == 1
    assert out.select("auction_volume").item() == 8000
    assert out.select("auction_amount").item() == 42000.0
