"""Free-stockdb (hello245m/free-stockdb) market data provider.

Wraps the HTTP KV protocol served by the stockdb server. The server is a
LevelDB-backed single-port query service; data itself must first be synced
into ``./data`` by the companion ``stockdb_updater`` (see docs/DATA_SOURCE.md).
This provider talks only to the running server and normalizes its responses
into the internal provider schemas.

Wire protocol (verified against the running server at 152.53.204.161:7899):

    GET /?cmd=vals&t=<table>&k1=key:<code>&k2=all:
    GET /?cmd=vals&t=<table>&k1=key:<code>&k2=key:<date>
    GET /?cmd=vals&t=<table>&k1=key:<code>&k2=fwd:<start>,<end>

    t=日k      daily K        -> list[dict] full OHLCV + snapshot fields
    t=复权      adjustment     -> list[dict] {cum, div, give, mult, trans}
    t=分钟k     minute K       -> list[dict]

Returns ``[]`` for unknown tables/keys on this server build; callers must
treat empty results as "no data for that window" (chain fallback input).
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import httpx
import polars as pl

from app.data_providers.base import AssetType, ProviderCapabilities
from app.data_providers.normalizer import normalize_daily, normalize_instruments

logger = logging.getLogger(__name__)

# Server response shapes (verified live):
#   daily row: {code, date(int yyyymmdd), open, high, low, close, volume, amount,
#               name, pre_close, pct_chg, pe_ttm, pb, total_mv, float_mv,
#               turnover, vol_ratio, is_st, amplitude}
#   adj row:   {cum, div, give, mult, trans}   (no date inside the row; key carries it)

TABLE_DAILY = "日k"
TABLE_ADJ = "复权"
TABLE_MINUTE = "分钟k"
TABLE_INSTRUMENTS = "股票代码"

_DAILY_FIELD_MAP = {
    "code": "symbol",
    "date": "date",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "amount": "amount",
}
_DAILY_EXTRA = ("name", "pre_close", "pct_chg", "pe_ttm", "pb", "total_mv", "turnover")


class FreeStockDBProvider:
    """HTTP client for a free-stockdb server (stockdb C++ query service).

    Capability notes (this server build):
      - daily: full history via ``vals 日k``.
      - minute: only dates already synced into the server's ``./data``.
      - adj_factor: unavailable over HTTP — the deployed build returns factor
        rows without their event date (date lives in the LevelDB key, which the
        HTTP layer drops), and ``cum`` is cumulative while the internal
        ``ex_factor`` is a per-event pre/post ratio. The chain layer falls back
        to TickFlow for adjustment factors.
      - realtime/financial/instruments: not exposed over HTTP on this build.
    """

    name = "free_stockdb"
    capabilities = ProviderCapabilities(
        instruments=False,
        daily=True,
        adj_factor=False,
        minute=True,
        realtime=False,
        financial=False,
    )

    def __init__(self, base_url: str = "http://127.0.0.1:7899", timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    # -- public provider surface (MarketDataProvider-compatible) -----------------

    def get_instruments(self, asset_type: AssetType = "stock") -> pl.DataFrame:
        return pl.DataFrame()

    def get_daily(
        self,
        symbols: list[str],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        asset_type: AssetType = "stock",
    ) -> pl.DataFrame:
        if not symbols:
            return pl.DataFrame()
        frames: list[pl.DataFrame] = []
        for symbol in symbols:
            rows = self._vals_range(TABLE_DAILY, symbol, start_time, end_time)
            if not rows:
                continue
            mapped = [self._map_daily_row(r) for r in rows if isinstance(r, dict)]
            if mapped:
                frames.append(pl.DataFrame(mapped))
        if not frames:
            return pl.DataFrame()
        return normalize_daily(pl.concat(frames, how="diagonal_relaxed"), source=self.name)

    def get_adj_factors(
        self,
        symbols: list[str],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        asset_type: AssetType = "stock",
    ) -> pl.DataFrame:
        # Not usable over HTTP on this server build; chain falls back to TickFlow.
        return pl.DataFrame()

    def get_minute(
        self,
        symbols: list[str],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        freq: str = "1m",
    ) -> pl.DataFrame:
        if not symbols:
            return pl.DataFrame()
        frames: list[pl.DataFrame] = []
        for symbol in symbols:
            rows = self._vals_minute(TABLE_MINUTE, symbol, start_time, end_time)
            if not rows:
                continue
            for r in rows:
                if not isinstance(r, dict):
                    continue
                dt_int = r.get("date")
                if dt_int is None:
                    continue
                dt = _parse_minute_ts(int(dt_int))
                if dt is None:
                    continue
                frames.append(pl.DataFrame({
                    "symbol": [symbol],
                    "datetime": [dt],
                    "open": [float(r.get("open") or 0.0)],
                    "high": [float(r.get("high") or 0.0)],
                    "low": [float(r.get("low") or 0.0)],
                    "close": [float(r.get("close") or 0.0)],
                    "volume": [float(r.get("volume") or 0.0)],
                    "amount": [float(r.get("amount") or 0.0)],
                    "freq": [freq],
                }))
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames, how="diagonal_relaxed")

    def get_realtime(
        self,
        universes: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    # -- protocol helpers --------------------------------------------------------

    def _vals(self, table: str, k1: str, k2: str, timeout: float | None = None) -> list[Any]:
        try:
            resp = self._client.get(
                self.base_url + "/",
                params={"cmd": "vals", "t": table, "k1": k1, "k2": k2},
                timeout=timeout or self._timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:  # noqa: BLE001
            logger.warning("free-stockdb %s query failed: %s", table, e)
            return []
        if isinstance(payload, list):
            return payload
        return []

    def _vals_minute(self, table: str, symbol: str, start_time: datetime | None, end_time: datetime | None) -> list[Any]:
        code = str(symbol).split(".")[0]
        s = _minute_ts(start_time, end="start") if start_time else "00000000000000"
        e = _minute_ts(end_time, end="end") if end_time else "99999999999999"
        return self._vals(table, f"key:{code}", f"fwd:{s},{e}")

    def _vals_range(
        self,
        table: str,
        symbol: str,
        start_time: datetime | None,
        end_time: datetime | None,
        *,
        minute: bool = False,
    ) -> list[Any]:
        if minute:
            return self._vals_minute(table, symbol, start_time, end_time)
        code = str(symbol).split(".")[0]
        if start_time is None and end_time is None:
            return self._vals(table, f"key:{code}", "all:")
        s = _date_key(start_time) if start_time else "00000000"
        e = _date_key(end_time) if end_time else "99999999"
        return self._vals(table, f"key:{code}", f"fwd:{s},{e}")

    @staticmethod
    def _map_daily_row(row: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for src, dst in _DAILY_FIELD_MAP.items():
            if src in row:
                out[dst] = row[src]
        for field in _DAILY_EXTRA:
            if field in row:
                out[field] = row[field]
        raw_date = out.get("date")
        if raw_date is not None:
            parsed = _parse_date(raw_date)
            if parsed is not None:
                out["date"] = parsed.isoformat()
        return out


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value)[:10]
    if not text:
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _minute_ts(value: datetime | None, *, end: str) -> str:
    if value is None:
        return "99999999999999" if end == "end" else "00000000000000"
    # Protocol expects a 14-digit timestamp (YYYYMMDDHHMMSS). When the caller
    # supplies a date-only datetime, expand it to cover the whole session.
    ts = value.strftime("%Y%m%d%H%M%S")
    if ts.endswith("000000"):
        ts = ts[:8] + ("235959" if end == "end" else "093000")
    return ts[:14]


def _parse_minute_ts(value: int) -> datetime | None:
    s = str(value)
    if len(s) < 12:
        return None
    try:
        return datetime.strptime(s[:14], "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _date_key(value: datetime | None) -> str:
    return value.strftime("%Y%m%d") if value else "00000000"

