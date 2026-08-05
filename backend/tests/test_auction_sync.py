"""竞价湖摄入 (DATA-05) — probe 门 + 09:30 排除 + 原子写 + 分区合并 + 偏好旋钮 + 视图登记。

Hermetic、无网络, 复用 test_auction_probe.py 的 FakeAuctionProvider 模式。
所有生产 import 放测试函数内, 避免 collection 时导入 DuckDB 单例 (repo 约定)。
"""
from __future__ import annotations

from datetime import date, datetime

import polars as pl
import pytest


class FakeAuctionProvider:
    """极简假 provider: 可注入预置行或抛错, 用于强制每个探测状态。"""

    name = "fake_auction"

    def __init__(self, rows: pl.DataFrame | None = None, exc: Exception | None = None) -> None:
        self.rows = rows
        self.exc = exc

    def get_auction(self, symbols: list[str], trade_date: datetime) -> pl.DataFrame:
        del symbols, trade_date
        if self.exc is not None:
            raise self.exc
        return self.rows if self.rows is not None else pl.DataFrame()


def _rows(*minutes_and_seconds: tuple[int, int]) -> pl.DataFrame:
    """构造 2026-08-04 09:{m}:{s} 的 canonical 竞价帧 (symbol/datetime/auction_volume/auction_amount)。"""
    return pl.DataFrame({
        "symbol": ["000001"] * len(minutes_and_seconds),
        "datetime": [datetime(2026, 8, 4, 9, m, s) for m, s in minutes_and_seconds],
        "auction_volume": [100 * (i + 1) for i in range(len(minutes_and_seconds))],
        "auction_amount": [1000 * (i + 1) for i in range(len(minutes_and_seconds))],
    })


def _available_verdict():
    """构造一个 available verdict (Task 1 各测试共用)。"""
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
    return AuctionProbeVerdict(
        status=AuctionProbeStatus.available,
        source="fake_auction",
        probed_at=None,
        detail="",
    )


# ================================================================
# Task 1 — 湖摄入: probe 门 / 09:30 排除 / 原子写 / 分区合并 / canonical 列
# ================================================================


def test_sync_writes_partition(tmp_path, monkeypatch):
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    try:
        from app.services import auction_sync
        from app.tickflow.capabilities import CapabilitySet

        fake = FakeAuctionProvider(rows=_rows((16, 0), (20, 30), (25, 0)))
        monkeypatch.setattr(auction_sync, "resolve_auction_probe", _available_verdict)
        monkeypatch.setattr(auction_sync, "_first_auction_provider", lambda: fake)

        written = auction_sync.sync_and_persist_auction(
            ["000001", "600000"], KlineRepository(store), CapabilitySet(), date(2026, 8, 4),
        )
        assert written > 0

        out = data_dir / "kline_auction" / "date=2026-08-04" / "part.parquet"
        assert out.exists()
        df = pl.read_parquet(out)
        assert df.columns == auction_sync.CANONICAL_AUCTION_COLS
        assert df.schema["datetime"] == pl.Datetime("us")
        assert df["datetime"].min() >= datetime(2026, 8, 4, 9, 15)
        assert df["datetime"].max() <= datetime(2026, 8, 4, 9, 25, 59)
        assert not list((data_dir / "kline_auction").rglob("*.tmp"))
    finally:
        store.db.close()


def test_0930_excluded(tmp_path, monkeypatch):
    """T-20-01: 仅 ≥09:30 输入 → 湖 0 行 (09:30 连续竞价 bar 结构性排除)。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    try:
        from app.services import auction_sync
        from app.tickflow.capabilities import CapabilitySet

        fake = FakeAuctionProvider(rows=_rows((30, 0), (31, 0)))
        monkeypatch.setattr(auction_sync, "resolve_auction_probe", _available_verdict)
        monkeypatch.setattr(auction_sync, "_first_auction_provider", lambda: fake)

        written = auction_sync.sync_and_persist_auction(
            ["000001"], KlineRepository(store), CapabilitySet(), date(2026, 8, 4),
        )
        assert written == 0
        lake = data_dir / "kline_auction"
        if lake.exists():
            assert not list(lake.glob("date=*"))
    finally:
        store.db.close()


@pytest.mark.parametrize("status", ["not_configured", "fail_closed", "error"])
def test_non_available_writes_nothing(tmp_path, monkeypatch, status):
    """T-20-03: probe 非 available (not_configured/fail_closed/error) 一律 0 行不写湖。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    try:
        from app.services import auction_sync
        from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
        from app.tickflow.capabilities import CapabilitySet

        fake = FakeAuctionProvider(rows=_rows((16, 0)))

        def _verdict(s=status):
            return AuctionProbeVerdict(
                status=AuctionProbeStatus(s), source="fake", probed_at=None, detail="",
            )

        monkeypatch.setattr(auction_sync, "resolve_auction_probe", _verdict)
        monkeypatch.setattr(auction_sync, "_first_auction_provider", lambda: fake)

        written = auction_sync.sync_and_persist_auction(
            ["000001"], KlineRepository(store), CapabilitySet(), date(2026, 8, 4),
        )
        assert written == 0
        lake = data_dir / "kline_auction"
        if lake.exists():
            assert not list(lake.glob("date=*"))
    finally:
        store.db.close()


def test_merge_upsert_same_day(tmp_path, monkeypatch):
    """同一交易日写两次 → unique(symbol, datetime, keep=last) 语义生效, 分区无重复。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    try:
        from app.services import auction_sync
        from app.tickflow.capabilities import CapabilitySet

        provider = FakeAuctionProvider(rows=pl.DataFrame({
            "symbol": ["000001"],
            "datetime": [datetime(2026, 8, 4, 9, 16)],
            "auction_volume": [100],
            "auction_amount": [1000],
        }))
        monkeypatch.setattr(auction_sync, "resolve_auction_probe", _available_verdict)
        monkeypatch.setattr(auction_sync, "_first_auction_provider", lambda: provider)

        repo = KlineRepository(store)
        # 第一次写入
        auction_sync.sync_and_persist_auction(
            ["000001"], repo, CapabilitySet(), date(2026, 8, 4),
        )
        # 第二次: 旧 symbol 更新行 (volume 100 → 200) + 新 symbol 600000
        provider.rows = pl.DataFrame({
            "symbol": ["000001", "600000"],
            "datetime": [datetime(2026, 8, 4, 9, 16), datetime(2026, 8, 4, 9, 18)],
            "auction_volume": [200, 300],
            "auction_amount": [2000, 3000],
        })
        auction_sync.sync_and_persist_auction(
            ["000001", "600000"], repo, CapabilitySet(), date(2026, 8, 4),
        )

        out = data_dir / "kline_auction" / "date=2026-08-04" / "part.parquet"
        df = pl.read_parquet(out)
        # 无重复 (symbol, datetime)
        assert df.select("symbol", "datetime").unique().height == df.height
        # 000001@09:16 只剩 volume=200 的更新行
        updated = df.filter(
            (pl.col("symbol") == "000001") & (pl.col("datetime") == datetime(2026, 8, 4, 9, 16)),
        )
        assert updated.height == 1
        assert updated["auction_volume"][0] == 200
        assert df.filter(pl.col("symbol") == "600000").height == 1
        assert df.height == 2
    finally:
        store.db.close()


def test_atomic_write_leaves_no_tmp(tmp_path, monkeypatch):
    """T-20-02: 写成功后分区目录内文件集合 == {part.parquet}, 无 .tmp 残留。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    try:
        from app.services import auction_sync
        from app.tickflow.capabilities import CapabilitySet

        fake = FakeAuctionProvider(rows=_rows((16, 0)))
        monkeypatch.setattr(auction_sync, "resolve_auction_probe", _available_verdict)
        monkeypatch.setattr(auction_sync, "_first_auction_provider", lambda: fake)

        auction_sync.sync_and_persist_auction(
            ["000001"], KlineRepository(store), CapabilitySet(), date(2026, 8, 4),
        )

        part_dir = data_dir / "kline_auction" / "date=2026-08-04"
        assert {f.name for f in part_dir.iterdir()} == {"part.parquet"}
        assert not list(part_dir.glob("*.tmp"))
    finally:
        store.db.close()
