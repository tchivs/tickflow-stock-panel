"""scripts/backfill_minute_driver.py 的 hermetic 测试 (MIN-01 CLI 面, 零网络)。

DATA_DIR env 驱动 (镜像 test_verify_auction_backfill._run): 种子 kline_daily (3 symbol)
+ kline_minute 分区 (2 symbol 已覆盖至 end) → 跑 CLI --all → 退出码 0、终态 dict
{"written": 0, "skipped": 2, "symbols_requested": 3}; 未覆盖 symbol 走注入 canned fetch
(模块测试钩子 _fetch, 空响应 → 诚实 0 行不伪 skip), 绝不触发真实网络。
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from datetime import date, datetime
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import backfill_minute_driver as driver  # noqa: E402

_SZ, _SH519, _SH000 = "000001.SZ", "600519.SH", "600000.SH"
_D1, _D2 = date(2026, 8, 3), date(2026, 8, 4)


def _seed_lake(tmp_path: Path) -> None:
    """kline_daily (3 symbol) + kline_minute 分区 (600519.SH / 600000.SH 已覆盖至 _D2)。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    settings.data_dir = data_dir

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    repo = KlineRepository(store)
    try:
        # kline_daily: 3 symbol x 2 交易日
        rows = []
        for sym in (_SZ, _SH519, _SH000):
            for d in (_D1, _D2):
                rows.append({
                    "symbol": sym, "date": d, "open": 10.0, "high": 11.0,
                    "low": 9.5, "close": 10.5, "volume": 1000.0, "amount": 10500.0,
                })
        repo.append_daily(pl.DataFrame(rows))

        # kline_minute: 2 symbol 覆盖至 _D2 (经唯一写面)
        from app.services import kline_sync
        bars = []
        for sym in (_SH519, _SH000):
            for d in (_D1, _D2):
                for i in range(5):
                    bars.append({
                        "symbol": sym,
                        "datetime": datetime(d.year, d.month, d.day, 9, 30 + i),
                        "open": 10.0 + i, "high": 11.0 + i, "low": 9.5 + i,
                        "close": 10.5 + i, "volume": 100.0, "amount": 1050.0,
                    })
        kline_sync._persist_minute_partitions(
            pl.DataFrame(bars).with_columns(pl.col("datetime").cast(pl.Datetime("us"))),
            repo,
        )
    finally:
        store.db.close()


def _run(monkeypatch, tmp_path, *argv, _fetch=None) -> tuple[int, str]:
    """DATA_DIR 指向 tmp 湖, 跑脚本 main(), 返回 (退出码, stdout)。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = driver.main(list(argv), _fetch=_fetch)
    return code, buf.getvalue()


def _empty_fetch(symbols, start_time, end_time):
    """未覆盖 symbol 的 canned 空响应: 诚实 0 行, 不伪 skip 不触网。"""
    return pl.DataFrame()


def test_backfill_driver_all_skipped_honest_zero(tmp_path, monkeypatch):
    """3 symbol 湖, 2 已覆盖 → --all 幂等续跑: exit 0, written 0, skipped 2, requested 3。"""
    _seed_lake(tmp_path)
    ledger = tmp_path / "ledger.json"

    code, out = _run(
        monkeypatch, tmp_path,
        "--all", "--start", "2026-08-03", "--end", "2026-08-04",
        "--out", str(ledger), _fetch=_empty_fetch,
    )
    assert code == 0
    assert "skipped: 2" in out
    assert "[3/3] symbols processed" in out  # 进度行

    result = json.loads(ledger.read_text(encoding="utf-8"))
    assert result["written"] == 0
    assert result["skipped"] == 2
    assert result["symbols_requested"] == 3
    assert "started_at" in result and "finished_at" in result  # 键齐全


def test_backfill_driver_default_dates_from_daily(tmp_path, monkeypatch):
    """无 --start/--end → 缺省窗口 = kline_daily [min, max] (08-03..08-04)。"""
    _seed_lake(tmp_path)

    code, out = _run(monkeypatch, tmp_path, "--all", _fetch=_empty_fetch)
    assert code == 0
    assert "skipped: 2" in out
    assert "requested: 3" in out


def test_backfill_driver_fetch_error_exit_2(tmp_path, monkeypatch):
    """fetch 异常 → fail-closed: exit 2 + stderr traceback, 绝不伪装「该窗口无数据」。"""
    _seed_lake(tmp_path)

    def _boom_fetch(symbols, start_time, end_time):
        raise RuntimeError("Tushare 40203 rate limited")

    code, _ = _run(
        monkeypatch, tmp_path,
        "--all", "--start", "2026-08-03", "--end", "2026-08-04", _fetch=_boom_fetch,
    )
    assert code == 2


def test_backfill_driver_symbols_subset(tmp_path, monkeypatch):
    """--symbols 子集 + 未覆盖 → canned 空响应诚实 0 行, 终态 skipped 0。"""
    _seed_lake(tmp_path)
    ledger = tmp_path / "ledger2.json"

    code, out = _run(
        monkeypatch, tmp_path,
        "--symbols", "000001.SZ", "--start", "2026-08-03", "--end", "2026-08-04",
        "--out", str(ledger), _fetch=_empty_fetch,
    )
    assert code == 0
    result = json.loads(ledger.read_text(encoding="utf-8"))
    assert result["written"] == 0
    assert result["skipped"] == 0  # 空响应不伪 skip
    assert result["symbols_requested"] == 1


def test_backfill_driver_source_label_passthrough(tmp_path, monkeypatch):
    """MIN-03 --source-label 透传: 台账含通道身份 (覆盖 = 源插件深度);
    缺省不传 → 台账 source 诚实 null (不声明)。"""
    _seed_lake(tmp_path)
    ledger = tmp_path / "ledger3.json"

    code, _ = _run(
        monkeypatch, tmp_path,
        "--all", "--start", "2026-08-03", "--end", "2026-08-04",
        "--source-label", "tencent-mkline",
        "--out", str(ledger), _fetch=_empty_fetch,
    )
    assert code == 0
    result = json.loads(ledger.read_text(encoding="utf-8"))
    assert result["source"] == "tencent-mkline"  # 通道身份进台账

    ledger4 = tmp_path / "ledger4.json"
    code, _ = _run(
        monkeypatch, tmp_path,
        "--all", "--start", "2026-08-03", "--end", "2026-08-04",
        "--out", str(ledger4), _fetch=_empty_fetch,
    )
    assert code == 0
    result4 = json.loads(ledger4.read_text(encoding="utf-8"))
    assert result4["source"] is None  # 缺省诚实不声明
