"""43-01 三重对账契约测试 (hermetic, 零网络, 种子 staging + canned 分钟 fetch).

契约面 (43-01-PLAN):
- 三重闭合: 09:25 price/vol vs 09:30 bar close/volume — price 1e-6 / vol 恒等 (手) /
  amount 仅 OHLC 全等时派生 (173×100×1308.66 == 22,639,818, 实测锚定)。
- mismatch 语义: price/vol 任一不等 → "mismatch"; amount UNKNOWN (OHLC 不全等)
  不视为 closed (绝不猜, Pitfall 7)。
- end=T+1 端日语义: 记录型分钟 fetch 断言请求 start=T 00:00 / end=T+1 00:00
  (Phase 40 Pitfall 3)。
- 09:30 bar 缺失 → retry_sleep 重试 1 次 (注入 0) → pending (A5, 不误报 mismatch)。
- manifest.reconciliation 原子更新: 读旧 manifest → 增 reconciliation 块 → 旧键保留。

所有生产 import 延迟到测试函数内 (repo 约定)。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl
import pytest

_T = date(2026, 8, 7)
_ISO = "2026-08-07"
_SH_TZ = ZoneInfo("Asia/Shanghai")

_STAGING_SCHEMA = {
    "symbol": pl.Utf8,
    "trade_date": pl.Datetime("us", time_zone="Asia/Shanghai"),
    "time": pl.Utf8,
    "price": pl.Float64,
    "vol_hand": pl.Int64,
    "num_trades": pl.Int64,
    "buyorsell": pl.Int64,
    "source": pl.Utf8,
    "fetched_at": pl.Datetime("us", time_zone="UTC"),
    "ingested_at": pl.Datetime("us", time_zone="UTC"),
}


def _match_row(symbol: str = "SH600519", price: float = 1308.66,
               vol_hand: int = 173, num_trades: int = 120) -> dict:
    """staging 09:25:00 撮合行 (10 列, 镜像 capture 归一化形态)。"""
    return {
        "symbol": symbol,
        "trade_date": datetime(2026, 8, 7, tzinfo=_SH_TZ),
        "time": "09:25:00", "price": price, "vol_hand": vol_hand,
        "num_trades": num_trades, "buyorsell": 2, "source": "eastmoney",
        "fetched_at": datetime(2026, 8, 7, 1, 26, 11, tzinfo=timezone.utc),
        "ingested_at": None,
    }


def _seed_staging(data_dir: Path, rows: list[dict], manifest: dict | None = None) -> None:
    """直接写 staging 分区 (date={T}/part.parquet + manifest.json)。"""
    out_dir = data_dir / "tick_staging" / f"date={_ISO}"
    out_dir.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows, schema=_STAGING_SCHEMA).write_parquet(out_dir / "part.parquet")
    m = manifest if manifest is not None else {
        "trade_date": _ISO,
        "captured_at": "2026-08-07T01:26:00+00:00",
        "pool_size": 1,
        "symbols_ok": [rows[0]["symbol"]],
        "symbols_failed": [],
        "completeness": {"ok": True, "by_symbol": {rows[0]["symbol"]: {"ok": True}}},
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8",
    )


class _RecordingMinuteFetch:
    """记录 (symbols, start_time, end_time); 按用例返回 09:30 bar / 缺失 / OHLC 不全等。"""

    def __init__(self, bar_mode: str = "closed", retry_behavior: str = "always_present"):
        self.calls: list[tuple[list[str], datetime, datetime]] = []
        self.bar_mode = bar_mode  # "closed" | "non_closed_ohlc" | "missing"
        self.retry_behavior = retry_behavior  # "always_present" | "always_missing" | "missing_then_present"

    def get_minute(self, symbols, start_time=None, end_time=None):
        self.calls.append((list(symbols), start_time, end_time))
        if self.retry_behavior == "always_missing":
            return pl.DataFrame()
        if self.retry_behavior == "missing_then_present" and len(self.calls) == 1:
            return pl.DataFrame()
        return self._frame()

    def _frame(self) -> pl.DataFrame:
        if self.bar_mode == "missing":
            return pl.DataFrame()
        if self.bar_mode == "non_closed_ohlc":
            row = {"symbol": "600519.SH", "datetime": datetime(2026, 8, 7, 9, 30),
                   "open": 1308.66, "high": 1308.70, "low": 1308.55, "close": 1308.66,
                   "volume": 173, "amount": None, "freq": "1m"}
        else:  # closed anchor (实测 OHLC 全等 1308.66 / 173 手)
            row = {"symbol": "600519.SH", "datetime": datetime(2026, 8, 7, 9, 30),
                   "open": 1308.66, "high": 1308.66, "low": 1308.66, "close": 1308.66,
                   "volume": 173, "amount": None, "freq": "1m"}
        return pl.DataFrame([row])


@pytest.fixture
def reconcile_env(tmp_path, monkeypatch):
    """隔离的 data_dir (monkeypatch settings.data_dir)。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)
    return data_dir


# ============================================================
# reconcile_match: 三重闭合 / mismatch / amount UNKNOWN
# ============================================================


def test_reconcile_closed_anchor():
    """实测锚定: 173×100×1308.66 == 22,639,818 (price 1e-6 / vol 恒等 / amount 派生)。"""
    from app.services.auction_reconcile import reconcile_match

    match = {"price": 1308.66, "vol_hand": 173}
    bar = {"open": 1308.66, "high": 1308.66, "low": 1308.66,
           "close": 1308.66, "volume": 173}
    res = reconcile_match(match, bar)
    assert res["status"] == "closed"
    assert res["checks"]["price_eq"] is True
    assert res["checks"]["vol_eq"] is True
    assert res["checks"]["amount_closure"] is True
    assert 173 * 100 * 1308.66 == pytest.approx(22_639_818.0, rel=1e-6)
    assert res["amount_derived"] is True


def test_reconcile_price_mismatch():
    from app.services.auction_reconcile import reconcile_match

    match = {"price": 1308.66, "vol_hand": 173}
    bar = {"open": 1308.00, "high": 1308.00, "low": 1308.00,
           "close": 1308.00, "volume": 173}
    res = reconcile_match(match, bar)
    assert res["checks"]["price_eq"] is False
    assert res["status"] == "mismatch"


def test_reconcile_volume_mismatch():
    from app.services.auction_reconcile import reconcile_match

    match = {"price": 1308.66, "vol_hand": 173}
    bar = {"open": 1308.66, "high": 1308.66, "low": 1308.66,
           "close": 1308.66, "volume": 172}
    res = reconcile_match(match, bar)
    assert res["checks"]["vol_eq"] is False
    assert res["status"] == "mismatch"


def test_reconcile_amount_unknown_non_closed_ohlc():
    """OHLC 不全等 → amount UNKNOWN (不猜); price/vol 全等仍不算 closed。"""
    from app.services.auction_reconcile import reconcile_match

    match = {"price": 1308.66, "vol_hand": 173}
    bar = {"open": 1308.66, "high": 1308.70, "low": 1308.55,
           "close": 1308.66, "volume": 173}
    res = reconcile_match(match, bar)
    assert res["checks"]["price_eq"] is True
    assert res["checks"]["vol_eq"] is True
    assert res["checks"]["amount_closure"] is False
    assert res["checks"]["amount_reason"] == "ohlc_not_closed"
    assert res["amount_derived"] is False
    assert res["status"] == "mismatch"  # amount UNKNOWN 不视为 closed (Pitfall 7)


# ============================================================
# reconcile_window: end=T+1 / 重试 pending / staging_missing / manifest 更新
# ============================================================


def test_reconcile_window_uses_minute_end_plus_1(reconcile_env):
    """记录型 fetch 断言请求 start=T 00:00 / end=T+1 00:00 (Phase 40 Pitfall 3)。"""
    from app.services.auction_reconcile import reconcile_window

    _seed_staging(reconcile_env, [_match_row()])
    fetch = _RecordingMinuteFetch(bar_mode="closed")
    res = reconcile_window(fetch, reconcile_env, _T, retry_sleep=0)
    assert res["status"] == "closed"
    assert res["trading_day_confirmed"] is True
    assert res["amount_derived_symbols"] == ["SH600519"]
    assert fetch.calls == [(["600519.SH"], datetime(2026, 8, 7, 0, 0), datetime(2026, 8, 8, 0, 0))]


def test_reconcile_window_retry_then_pending(reconcile_env):
    """09:30 bar 缺失 → 重试 1 次 (sleep 注入 0) → 仍无 → pending (A5, 不误报 mismatch)。"""
    from app.services.auction_reconcile import reconcile_window

    _seed_staging(reconcile_env, [_match_row()])
    fetch = _RecordingMinuteFetch(retry_behavior="always_missing")
    res = reconcile_window(fetch, reconcile_env, _T, retry_sleep=0)
    assert res["status"] == "pending"
    assert res["reason"] == "no_0930_bar"
    assert res["checks"]["SH600519"] == {"status": "pending", "reason": "no_0930_bar"}
    assert res["trading_day_confirmed"] is False
    assert len(fetch.calls) == 2  # 恰重试 1 次

    manifest = json.loads((reconcile_env / "tick_staging" / f"date={_ISO}" / "manifest.json").read_text())
    assert manifest["reconciliation"]["status"] == "pending"
    assert manifest["reconciliation"]["reason"] == "no_0930_bar"


def test_reconcile_window_retry_recovers(reconcile_env):
    """首取缺失 → 重试后 09:30 bar 在场 → closed (重试是恢复路径非误报)。"""
    from app.services.auction_reconcile import reconcile_window

    _seed_staging(reconcile_env, [_match_row()])
    fetch = _RecordingMinuteFetch(retry_behavior="missing_then_present")
    res = reconcile_window(fetch, reconcile_env, _T, retry_sleep=0)
    assert res["status"] == "closed"
    assert len(fetch.calls) == 2


def test_reconcile_window_staging_missing(reconcile_env):
    """无 staging / 无撮合行 / manifest 缺失 → staging_missing (诚实不伪造, 零 fetch)。"""
    from app.services.auction_reconcile import reconcile_window

    fetch = _RecordingMinuteFetch()
    res = reconcile_window(fetch, reconcile_env, _T, retry_sleep=0)
    assert res == {
        "status": "staging_missing", "checks": {},
        "trading_day_confirmed": False, "amount_derived_symbols": [],
    }
    assert fetch.calls == []  # 无 staging → 不发任何请求


def test_reconcile_window_manifest_preserves_old_keys(reconcile_env):
    """manifest 原子更新: 旧键保留 + reconciliation 块追加 (43-02 提审 gate 输入)。"""
    from app.services.auction_reconcile import reconcile_window

    _seed_staging(reconcile_env, [_match_row()])
    fetch = _RecordingMinuteFetch(bar_mode="closed")
    res = reconcile_window(fetch, reconcile_env, _T, retry_sleep=0)
    assert res["status"] == "closed"

    manifest = json.loads((reconcile_env / "tick_staging" / f"date={_ISO}" / "manifest.json").read_text())
    for key in ("trade_date", "captured_at", "pool_size", "symbols_ok",
                "symbols_failed", "completeness"):
        assert key in manifest  # 旧键保留
    rec = manifest["reconciliation"]
    assert rec["status"] == "closed"
    assert rec["trading_day_confirmed"] is True
    assert rec["amount_derived_symbols"] == ["SH600519"]
    assert rec["checks"]["SH600519"]["checks"]["amount_closure"] is True


def test_reconcile_window_mismatch_per_symbol(reconcile_env):
    """bar 价格不等 → mismatch 记入 reconciliation (43-02 gate 拒绝前置)。"""
    from app.services.auction_reconcile import reconcile_window

    _seed_staging(reconcile_env, [_match_row()])
    fetch = _RecordingMinuteFetch(bar_mode="non_closed_ohlc")
    res = reconcile_window(fetch, reconcile_env, _T, retry_sleep=0)
    assert res["status"] == "mismatch"
    assert res["trading_day_confirmed"] is True  # 09:30 bar 在场 ⇒ 交易日
    assert res["checks"]["SH600519"]["status"] == "mismatch"
