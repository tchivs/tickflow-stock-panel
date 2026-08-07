"""local_stockdb 全链写路径冒烟 (LOCAL-04 铁律)。

证明 local_stockdb 经既有 kline_sync 路径真实贯通:
  chain → fetch_with_chain (链首) → repo.append_daily (merge-upsert) → 湖 parquet。

配方镜像 test_daily_pipeline_refresh (tmp_path 真 repo + 零网络, 禁 background=True):
  - fake local provider 提供规范帧 (2 标的 × 2 日, symbol 后缀形态);
  - monkeypatch chain._get_provider (按 name 分派) + preferences.get_provider_chain
    恒 ["local_stockdb"] → 只走本地通道, 其余源不触网;
  - 断言: 行数可观测、二次幂等 (unique(subset=["symbol","date"], keep="last")),
    湖 schema 无 provenance 列 (铁律), 通道身份进链日志 (caplog)。

kline_sync.py 零改动 (git diff --name-only 复核)。
"""
from __future__ import annotations

import logging
from datetime import date, datetime

import polars as pl
import pytest

# 生产 import 放测试函数内 (repo 惯例 — 模块收集期不 import DuckDB 单例)。

# 湖内规范日K列 (normalizer 裁剪后的存储面; 无 provenance 列 — LOCAL-04 铁律)。
_CANONICAL_DAILY_COLS = {"symbol", "date", "open", "high", "low", "close", "volume", "amount", "quote_ts"}
_PROVENANCE_COLS = {"source", "fetched_at", "schema_version", "volume_hand", "ingested_at"}

_SYMBOLS = ["600519.SH", "000001.SZ"]
_DATES = [date(2024, 1, 2), date(2024, 1, 3)]


class _FakeLocalProvider:
    """fake local_stockdb provider — 镜像 test_provider_chain._FakeProvider 面。

    get_daily 返回规范帧 (后缀形态 symbol); 其余源由调用侧 monkeypatch 抛错/空。
    """

    name = "local_stockdb"

    def __init__(self, frame: pl.DataFrame) -> None:
        self._frame = frame

    def get_daily(self, symbols, start_time=None, end_time=None, **kwargs):  # noqa: ARG002
        return self._frame

    def get_minute(self, symbols, start_time=None, end_time=None, **kwargs):  # noqa: ARG002
        return pl.DataFrame()


def _local_frame() -> pl.DataFrame:
    """规范帧: 2 标的 × 2 日 (symbol 后缀形态, 湖内规范列, 无 provenance 列)。"""
    rows = []
    for sym in _SYMBOLS:
        for d in _DATES:
            rows.append({
                "symbol": sym,
                "date": d,
                "open": 1300.0,
                "high": 1334.0,
                "low": 1303.0,
                "close": 1306.45,
                "volume": 42689.0,
                "amount": 5.56e9,
            })
    return pl.DataFrame(rows)


def _make_repo(tmp_path):
    """tmp_path 真 repo (DataStore + KlineRepository), 绝不触碰真实 data/ 湖。"""
    from app.tickflow.repository import DataStore, KlineRepository

    store = DataStore(tmp_path / "data")
    return KlineRepository(store), store


def _patch_chain_to_local(monkeypatch: pytest.MonkeyPatch, provider) -> None:
    """链解析 → 只走 fake local 通道: _get_provider 按 name 分派, 默认链恒 [local_stockdb]。"""
    from app.data_providers import chain as provider_chain
    from app.services import preferences

    def _fake_get(name: str):
        if name == "local_stockdb":
            return provider
        raise AssertionError(f"链不应触达其他源: {name}")

    monkeypatch.setattr(provider_chain, "_get_provider", _fake_get)
    monkeypatch.setattr(preferences, "get_provider_chain", lambda ds: ["local_stockdb"])


def _lake_rows(data_dir) -> int:
    """kline_daily 分区 parquet 总行数 (date=*/*.parquet glob)。"""
    return sum(
        pl.read_parquet(p).height
        for p in sorted((data_dir / "kline_daily").glob("date=*/*.parquet"))
    )


def _lake_columns(data_dir) -> set[str]:
    cols: set[str] = set()
    for p in sorted((data_dir / "kline_daily").glob("date=*/*.parquet")):
        cols |= set(pl.scan_parquet(p).schema.keys())  # type: ignore[attr-defined]
    return cols


def test_local_channel_writes_via_existing_append_daily(tmp_path, monkeypatch):
    """全链冒烟: fake local 链首 → fetch_with_chain → repo.append_daily → 湖行数可观测。"""
    from app.services import kline_sync
    from app.tickflow.capabilities import CapabilitySet

    _patch_chain_to_local(monkeypatch, _FakeLocalProvider(_local_frame()))
    repo, store = _make_repo(tmp_path)
    try:
        written = kline_sync.sync_and_persist_daily_batch(
            symbols=_SYMBOLS,
            repo=repo,
            capset=CapabilitySet(),
            count=2,
            start_date=datetime(2024, 1, 2),
            end_date=datetime(2024, 1, 3),
        )
        assert written == len(_SYMBOLS) * len(_DATES) == 4
        assert _lake_rows(store.data_dir) == written, "返回行数 != 湖内落盘行数"
    finally:
        store.db.close()


def test_local_channel_write_is_idempotent(tmp_path, monkeypatch):
    """二次运行幂等: merge-upsert (unique subset=["symbol","date"], keep="last") → 行数不变。"""
    from app.services import kline_sync
    from app.tickflow.capabilities import CapabilitySet

    _patch_chain_to_local(monkeypatch, _FakeLocalProvider(_local_frame()))
    repo, store = _make_repo(tmp_path)
    try:
        kwargs = dict(
            symbols=_SYMBOLS,
            repo=repo,
            capset=CapabilitySet(),
            count=2,
            start_date=datetime(2024, 1, 2),
            end_date=datetime(2024, 1, 3),
        )
        first = kline_sync.sync_and_persist_daily_batch(**kwargs)
        second = kline_sync.sync_and_persist_daily_batch(**kwargs)
        assert first == second == 4
        assert _lake_rows(store.data_dir) == 4, "重复同步后湖内行数必须不变 (幂等)"
    finally:
        store.db.close()


def test_lake_schema_has_no_provenance_columns(tmp_path, monkeypatch):
    """LOCAL-04 铁律: 湖 parquet schema 无 provenance 列, 列集 ⊆ 湖内规范列。"""
    from app.services import kline_sync
    from app.tickflow.capabilities import CapabilitySet

    _patch_chain_to_local(monkeypatch, _FakeLocalProvider(_local_frame()))
    repo, store = _make_repo(tmp_path)
    try:
        written = kline_sync.sync_and_persist_daily_batch(
            symbols=_SYMBOLS,
            repo=repo,
            capset=CapabilitySet(),
            count=2,
            start_date=datetime(2024, 1, 2),
            end_date=datetime(2024, 1, 3),
        )
        assert written > 0
        cols = _lake_columns(store.data_dir)
        assert cols <= _CANONICAL_DAILY_COLS, f"湖出现了规范列之外: {cols - _CANONICAL_DAILY_COLS}"
        assert not (cols & _PROVENANCE_COLS), (
            f"湖被污染 provenance 列: {cols & _PROVENANCE_COLS} — 通道身份只进日志, 湖无 provenance 列 (铁律)"
        )
    finally:
        store.db.close()


def test_channel_identity_in_chain_log(tmp_path, monkeypatch, caplog):
    """通道身份可观测: 链日志行含 "chain[daily]: provider local_stockdb added N rows"。"""
    from app.services import kline_sync
    from app.tickflow.capabilities import CapabilitySet

    _patch_chain_to_local(monkeypatch, _FakeLocalProvider(_local_frame()))
    repo, store = _make_repo(tmp_path)
    try:
        with caplog.at_level(logging.INFO, logger="app.data_providers.chain"):
            written = kline_sync.sync_and_persist_daily_batch(
                symbols=_SYMBOLS,
                repo=repo,
                capset=CapabilitySet(),
                count=2,
                start_date=datetime(2024, 1, 2),
                end_date=datetime(2024, 1, 3),
            )
        assert written > 0
        identity_rows = [
            r.message for r in caplog.records
            if "chain[daily]" in r.message and "local_stockdb" in r.message
        ]
        assert identity_rows, "链日志缺少 local_stockdb 通道身份行"
        assert any(f"added {written} rows" in m for m in identity_rows)
    finally:
        store.db.close()
