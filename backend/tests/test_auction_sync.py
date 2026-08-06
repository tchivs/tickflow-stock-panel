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


def _rows_with_input_cols(*minutes_and_seconds: tuple[int, int]) -> pl.DataFrame:
    """构造带可选委托量输入列的竞价帧 (CHART-03): 4 canonical + auction_unmatched_volume + auction_virtual_price。"""
    return pl.DataFrame({
        "symbol": ["000001"] * len(minutes_and_seconds),
        "datetime": [datetime(2026, 8, 4, 9, m, s) for m, s in minutes_and_seconds],
        "auction_volume": [100 * (i + 1) for i in range(len(minutes_and_seconds))],
        "auction_amount": [1000 * (i + 1) for i in range(len(minutes_and_seconds))],
        "auction_unmatched_volume": [50 * (i + 1) for i in range(len(minutes_and_seconds))],
        "auction_virtual_price": [7.5] * len(minutes_and_seconds),
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

# ================================================================
# Task 2 — 偏好旋钮 + daily_pipeline Step 2.6 stage 闸门
# ================================================================


def test_auction_prefs_round_trip(tmp_path, monkeypatch):
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.services import preferences

    # 默认关闭 (显式开启语义)
    assert preferences.get_auction_sync_enabled() is False
    # 默认空列表 = 全量
    assert preferences.get_auction_sync_symbols() == []

    # 杂乱输入规范化: 逗号/换行拆分、去空白、去空、保序去重
    clean = preferences.set_auction_sync_symbols([" 000001.SZ , 600000.SH\n", "000001.SZ"])
    assert clean == ["000001.SZ", "600000.SH"]
    assert preferences.get_auction_sync_symbols() == clean

    # 字符串形式直接存储, 读取时规范化
    preferences.save({"auction_sync_symbols": " 000001.SZ , 600000.SH\n"})
    assert preferences.get_auction_sync_symbols() == ["000001.SZ", "600000.SH"]

    # 空/纯空白 → []
    assert preferences.set_auction_sync_symbols([", \n", "  "]) == []
    assert preferences.get_auction_sync_symbols() == []


def test_run_auction_sync_gate(tmp_path, monkeypatch):
    """双闸门: 未开启 → 0; 开启但 probe 不可用 → 0; 开启+available → 返回 N。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    try:
        from app.jobs import daily_pipeline
        from app.services import preferences
        from app.tickflow.capabilities import CapabilitySet

        repo = KlineRepository(store)
        capset = CapabilitySet()

        # (a) 未开启 → 0, 湖无分区
        preferences.save({"auction_sync_enabled": False})
        assert daily_pipeline._run_auction_sync(repo, capset, date(2026, 8, 4)) == 0
        lake = data_dir / "kline_auction"
        assert not lake.exists() or not list(lake.glob("date=*"))

        # (b) 开启 + can_sync_auction False → 0
        preferences.save({"auction_sync_enabled": True})
        monkeypatch.setattr(daily_pipeline.auction_sync, "can_sync_auction", lambda capset: False)
        assert daily_pipeline._run_auction_sync(repo, capset, date(2026, 8, 4)) == 0
        assert not lake.exists() or not list(lake.glob("date=*"))

        # (c) 开启 + can_sync_auction True + sync_and_persist_auction 返回 N → 返回 N
        monkeypatch.setattr(daily_pipeline.auction_sync, "can_sync_auction", lambda capset: True)
        monkeypatch.setattr(
            daily_pipeline.auction_sync,
            "sync_and_persist_auction",
            lambda *a, **k: 42,
        )
        assert daily_pipeline._run_auction_sync(repo, capset, date(2026, 8, 4)) == 42
    finally:
        store.db.close()


def test_resolve_auction_symbols_honors_scope(tmp_path, monkeypatch):
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.jobs import daily_pipeline
    from app.services import preferences
    from app.tickflow.capabilities import CapabilitySet

    universe = ["000001.SZ", "600000.SH", "000002.SZ"]
    monkeypatch.setattr(daily_pipeline, "_resolve_universe", lambda capset: list(universe))

    # 空范围 → 全量
    preferences.save({"auction_sync_symbols": []})
    assert daily_pipeline._resolve_auction_symbols(CapabilitySet()) == universe

    # 非空范围 → 限定列表
    preferences.save({"auction_sync_symbols": ["600000.SH"]})
    assert daily_pipeline._resolve_auction_symbols(CapabilitySet()) == ["600000.SH"]

# ================================================================
# Task 3 — kline_auction DuckDB 视图登记 (DataStore 子目录 + rebuild_views + 单视图刷新)
# ================================================================


def test_auction_view_registered(tmp_path, monkeypatch):
    """写湖 → rebuild_views → SELECT * FROM kline_auction 返回该日行。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    try:
        from app.services import auction_sync
        from app.tickflow.capabilities import CapabilitySet

        fake = FakeAuctionProvider(rows=_rows((16, 0), (20, 30)))
        monkeypatch.setattr(auction_sync, "resolve_auction_probe", _available_verdict)
        monkeypatch.setattr(auction_sync, "_first_auction_provider", lambda: fake)

        repo = KlineRepository(store)
        auction_sync.sync_and_persist_auction(
            ["000001"], repo, CapabilitySet(), date(2026, 8, 4),
        )

        repo.rebuild_views()
        rows = repo.db.execute(
            "SELECT symbol, auction_volume, auction_amount FROM kline_auction ORDER BY symbol"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == "000001"
        assert rows[0][1] == 100
        assert repo.db.execute("SELECT count(*) FROM kline_auction").fetchone()[0] > 0
    finally:
        store.db.close()


def test_auction_view_absent_without_lake(tmp_path, monkeypatch):
    """空湖 DataStore → rebuild_views 不抛异常; 竞价湖读路径降级为 0 行。"""
    from duckdb import CatalogException

    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    try:
        repo = KlineRepository(store)
        repo.rebuild_views()  # 空目录下各视图登记降级 (既有语义), 不抛异常
        # 空湖 → kline_auction 视图未挂载; 读路径对缺失视图降级为 0 行
        try:
            count = repo.db.execute("SELECT count(*) FROM kline_auction").fetchone()[0]
        except CatalogException:
            count = 0
        assert count == 0
    finally:
        store.db.close()


# ================================================================
# Task 3 (26-01 CHART-03) — 可选委托量输入列写湖: 6 列保留 / 缺列 4 列 / 旧分区+新列 merge
# ================================================================


def test_sync_writes_partition_with_optional_cols(tmp_path, monkeypatch):
    """CHART-03: 带两可选列 → 分区列 == 4 canonical + 2 optional (6 列) 且末行值保留。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    try:
        from app.services import auction_sync
        from app.tickflow.capabilities import CapabilitySet

        fake = FakeAuctionProvider(rows=_rows_with_input_cols((16, 0), (20, 30), (25, 0)))
        monkeypatch.setattr(auction_sync, "resolve_auction_probe", _available_verdict)
        monkeypatch.setattr(auction_sync, "_first_auction_provider", lambda: fake)

        written = auction_sync.sync_and_persist_auction(
            ["000001", "600000"], KlineRepository(store), CapabilitySet(), date(2026, 8, 4),
        )
        assert written > 0

        out = data_dir / "kline_auction" / "date=2026-08-04" / "part.parquet"
        assert out.exists()
        df = pl.read_parquet(out)
        assert df.columns == auction_sync.CANONICAL_AUCTION_COLS + auction_sync.OPTIONAL_AUCTION_COLS
        # 末行 (09:25) 可选列值保留 (诚实: 源提供才写)
        last = df.sort("datetime").tail(1)
        assert last["auction_unmatched_volume"][0] == 150
        assert last["auction_virtual_price"][0] == 7.5
        assert not list((data_dir / "kline_auction").rglob("*.tmp"))
    finally:
        store.db.close()


def test_sync_partition_merge_old_four_plus_new_six(tmp_path, monkeypatch):
    """CHART-03 R1: 预写 4 列旧分区 + 再 sync 6 列新行同日 → 不抛 SchemaError, 合并列 = 并集。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    try:
        from app.services import auction_sync
        from app.tickflow.capabilities import CapabilitySet

        # 预写 4 列旧分区 (旧行 09:16, 无可选列)
        old_row = pl.DataFrame({
            "symbol": ["000001"],
            "datetime": [datetime(2026, 8, 4, 9, 16)],
            "auction_volume": [100],
            "auction_amount": [1000],
        })
        out = data_dir / "kline_auction" / "date=2026-08-04" / "part.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        old_row.write_parquet(out)

        # 再 sync 6 列新行 (同日 09:25)
        fake = FakeAuctionProvider(rows=_rows_with_input_cols((25, 0)))
        monkeypatch.setattr(auction_sync, "resolve_auction_probe", _available_verdict)
        monkeypatch.setattr(auction_sync, "_first_auction_provider", lambda: fake)

        auction_sync.sync_and_persist_auction(
            ["000001"], KlineRepository(store), CapabilitySet(), date(2026, 8, 4),
        )

        df = pl.read_parquet(out)
        expected = auction_sync.CANONICAL_AUCTION_COLS + auction_sync.OPTIONAL_AUCTION_COLS
        assert set(df.columns) == set(expected)
        # 旧行可选列缺席 (诚实 null), 新行可选列有值
        old = df.filter(pl.col("datetime") == datetime(2026, 8, 4, 9, 16))
        assert old["auction_unmatched_volume"][0] is None
        new = df.filter(pl.col("datetime") == datetime(2026, 8, 4, 9, 25))
        assert new["auction_unmatched_volume"][0] == 50
        assert df.height == 2
        assert not list((data_dir / "kline_auction").rglob("*.tmp"))
    finally:
        store.db.close()


def test_sync_without_optional_cols_stays_four_cols(tmp_path, monkeypatch):
    """CHART-03 R5: 源不提供可选列 → 分区仍 == CANONICAL_AUCTION_COLS 4 列 (向后兼容)。"""
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

        out = data_dir / "kline_auction" / "date=2026-08-04" / "part.parquet"
        assert out.exists()
        df = pl.read_parquet(out)
        assert df.columns == auction_sync.CANONICAL_AUCTION_COLS
        assert "auction_unmatched_volume" not in df.columns
        assert "auction_virtual_price" not in df.columns
    finally:
        store.db.close()


# ================================================================
# Task 2 (32-01 AQ-04) — write_auction_partitions 写缝 (单一写路径, 直接调用形状)
# ================================================================


def test_write_auction_partitions_preserves_suffix_key(tmp_path, monkeypatch):
    """同日碰撞规则: 带后缀 000001.SZ 与裸 000001 在 upsert 键 [symbol, datetime] 下是不同行。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    try:
        from app.services.auction_sync import write_auction_partitions

        df = pl.DataFrame({
            "symbol": ["000001.SZ", "000001", "000001.SZ"],
            "datetime": [
                datetime(2026, 8, 4, 9, 25),
                datetime(2026, 8, 4, 9, 25),
                datetime(2026, 8, 4, 9, 25),
            ],
            "auction_volume": [100, 200, 300],
            "auction_amount": [1000, 2000, 3000],
        })
        repo = KlineRepository(store)
        # 第一次写入: 纯搬移语义, 全新分区原样落 3 行 (无既有分区可合并)
        assert write_auction_partitions(df, repo) == 3
        # 第二次写入: merge-upsert unique([symbol, datetime], keep="last")
        # → 后缀键与裸键互不合并各一行 (同日碰撞规则), 同键同刻保留末值
        assert write_auction_partitions(df, repo) == 3

        out = data_dir / "kline_auction" / "date=2026-08-04" / "part.parquet"
        assert out.exists()
        lake_df = pl.read_parquet(out)
        assert lake_df.height == 2
        suffixed = lake_df.filter(pl.col("symbol") == "000001.SZ")
        assert suffixed.height == 1
        assert suffixed["auction_volume"][0] == 300
        bare = lake_df.filter(pl.col("symbol") == "000001")
        assert bare.height == 1
        assert bare["auction_volume"][0] == 200
        assert not list((data_dir / "kline_auction").rglob("*.tmp"))
    finally:
        store.db.close()


def test_write_auction_partitions_direct_shape(tmp_path, monkeypatch):
    """直接调用 helper: 返回窗口过滤后行数; 空 df → 0 不建分区; 09:30+ → 0 行写。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    try:
        from app.services.auction_sync import write_auction_partitions

        repo = KlineRepository(store)

        # 空 df → 0, 不建 date= 分区 (kline_auction 目录可能由 DataStore 预建)
        assert write_auction_partitions(pl.DataFrame(), repo) == 0
        lake = data_dir / "kline_auction"
        assert not lake.exists() or not list(lake.glob("date=*"))

        # 09:30+ 行 → 窗口谓词结构性排除, 0 行写
        assert write_auction_partitions(_rows((30, 0), (31, 0)), repo) == 0
        lake = data_dir / "kline_auction"
        assert not lake.exists() or not list(lake.glob("date=*"))

        # 窗口内行 → 返回过滤后行数且原子落盘
        written = write_auction_partitions(_rows((16, 0), (20, 30), (25, 0)), repo)
        assert written == 3
        out = data_dir / "kline_auction" / "date=2026-08-04" / "part.parquet"
        assert out.exists()
        assert pl.read_parquet(out).height == 3
        assert not list((data_dir / "kline_auction").rglob("*.tmp"))
    finally:
        store.db.close()
