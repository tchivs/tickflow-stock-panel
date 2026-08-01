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
    GET /?cmd=keys&t=<table>:<code>:<prefix>*

    t=日k      daily K        -> list[dict] full OHLCV + snapshot fields
    t=复权      adjustment     -> list[dict] {cum, div, give, mult, trans}
    t=分钟k     minute K       -> list[dict]

Adjustment-factor events are stored under keys ``复权:<code>:YYYYMMDD``. The
``vals`` command returns factor rows without the event date, so the provider
recovers dates via ``keys 复权:<code>:*`` and converts the cumulative ``cum``
ratio into the per-event pre/post ratio the internal pipeline expects.

Weekly/monthly bars are aggregated client-side from daily bars (the KV store
keeps raw daily/minute only); 1/5/15/30/60-minute bars are served directly by
the minute table. Returns ``[]`` for unknown tables/keys; callers treat empty
results as "no data for that window" (chain fallback input).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any

import httpx
import polars as pl

from app.data_providers.base import AssetType, ProviderCapabilities
from app.data_providers.normalizer import normalize_adj_factors, normalize_daily, normalize_instruments

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

# minute frequency -> min-datetime granularity key (server stores raw 1m bars;
# 5/15/30/60 are bucketed client-side).
_MINUTE_UNIT_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}


class FreeStockDBProvider:
    """HTTP client for a free-stockdb server (stockdb C++ query service)."""

    name = "free_stockdb"
    capabilities = ProviderCapabilities(
        instruments=False,
        daily=True,
        adj_factor=True,
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

    def get_weekly(self, symbols: list[str], start_time: datetime | None = None, end_time: datetime | None = None) -> pl.DataFrame:
        """Aggregate daily bars into ISO-week bars client-side."""
        daily = self.get_daily(symbols, start_time, end_time)
        if daily.is_empty():
            return daily
        return _aggregate_period(daily, period="week")

    def get_monthly(self, symbols: list[str], start_time: datetime | None = None, end_time: datetime | None = None) -> pl.DataFrame:
        """Aggregate daily bars into calendar-month bars client-side."""
        daily = self.get_daily(symbols, start_time, end_time)
        if daily.is_empty():
            return daily
        return _aggregate_period(daily, period="month")

    def get_adj_factors(
        self,
        symbols: list[str],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        asset_type: AssetType = "stock",
    ) -> pl.DataFrame:
        if not symbols:
            return pl.DataFrame()
        rows: list[dict[str, Any]] = []
        for symbol in symbols:
            code = str(symbol).split(".")[0]
            # 1. Event dates live in the LevelDB key; recover them via keys.
            keys = self._keys(f"复权:{code}:*")
            if not keys:
                continue
            events: list[tuple[date, float]] = []
            for key in keys:
                event_date = _parse_date(key.rsplit(":", 1)[-1])
                if event_date is None:
                    continue
                if start_time is not None and event_date < start_time.date():
                    continue
                if end_time is not None and event_date > end_time.date():
                    continue
                # 2. Per-date factor value.
                item = self._vals(TABLE_ADJ, f"key:{code}", f"key:{event_date.strftime('%Y%m%d')}")
                if not item or not isinstance(item[0], dict):
                    continue
                cum = float(item[0].get("cum") or 0.0)
                if cum <= 0:
                    continue
                events.append((event_date, cum))
            if not events:
                continue
            events.sort(key=lambda e: e[0])
            # 3. Convert cumulative factor to per-event pre/post ratio.
            prev = 1.0
            for event_date, cum in events:
                if cum <= 0 or prev <= 0:
                    prev = cum
                    continue
                rows.append({
                    "symbol": symbol,
                    "trade_date": event_date,
                    "ex_factor": cum / prev,
                })
                prev = cum
        if not rows:
            return pl.DataFrame()
        return normalize_adj_factors(rows, source=self.name)

    def get_minute(
        self,
        symbols: list[str],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        freq: str = "1m",
    ) -> pl.DataFrame:
        if not symbols:
            return pl.DataFrame()
        bucket_min = _MINUTE_UNIT_MINUTES.get(freq, 1)
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
        raw = pl.concat(frames, how="diagonal_relaxed")
        if bucket_min == 1:
            return raw
        # Bucket 1m bars into the requested interval (5/15/30/60).
        return _bucket_minutes(raw, bucket_min, freq)

    def get_realtime(
        self,
        universes: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    # -- protocol helpers --------------------------------------------------------

    def _keys(self, expr: str, timeout: float | None = None) -> list[str]:
        """cmd=keys with a wildcard returns the matched LevelDB keys (list[str])."""
        try:
            resp = self._client.get(
                self.base_url + "/",
                params={"cmd": "keys", "t": expr},
                timeout=timeout or self._timeout,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:  # noqa: BLE001
            logger.warning("free-stockdb %s keys query failed: %s", expr, e)
            return []
        if isinstance(payload, list):
            return [str(k) for k in payload]
        return []

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
    ts = value.strftime("%Y%m%d%H%M%S")
    if ts.endswith("000000"):
        ts = ts[:8] + ("235959" if end == "end" else "093000")
    return ts[:14]


def _date_key(value: datetime | None) -> str:
    return value.strftime("%Y%m%d") if value else "00000000"


def _aggregate_period(daily: pl.DataFrame, *, period: str) -> pl.DataFrame:
    """Aggregate normalized daily bars into week (ISO) or month bars."""
    if daily.is_empty():
        return daily
    period_expr = (
        pl.col("date").dt.strftime("%G-%V")
        if period == "week"
        else pl.col("date").dt.strftime("%Y-%m")
    )
    df = daily.with_columns(
        period_expr.alias("_period"),
        pl.col("date").cast(pl.Datetime).alias("_dt"),
    )
    grouped = (
        df.group_by(["symbol", "_period"])
        .agg([
            pl.col("_dt").max().dt.date().alias("date"),
            pl.col("open").first(),
            pl.col("high").max(),
            pl.col("low").min(),
            pl.col("close").last(),
            pl.col("volume").sum(),
            pl.col("amount").sum(),
        ])
        .sort(["symbol", "date"])
        .drop("_period")
    )
    keep = [c for c in daily.columns if c in grouped.columns]
    return grouped.select(keep)


def _bucket_minutes(raw: pl.DataFrame, bucket_min: int, freq: str) -> pl.DataFrame:
    """Bucket raw 1-minute bars into the requested interval (5/15/30/60).

    A-share sessions are not contiguous in wall clock (11:30-13:00 lunch).
    Morning bars anchor at 09:30; afternoon bars anchor at 13:00 and their
    bucket ids are offset by the morning bucket count so 11:30 and 13:00 never
    share a bucket.
    """
    if raw.is_empty():
        return raw
    dt = pl.col("datetime")
    hour = dt.dt.hour().cast(pl.Int64)
    minute = dt.dt.minute().cast(pl.Int64)
    morning = (hour < 12) & ((hour > 9) | ((hour == 9) & (minute >= 30)))
    afternoon = hour >= 13
    morning_elapsed = hour * 60 + minute - (9 * 60 + 30)  # 0..120
    afternoon_elapsed = hour * 60 + minute - (13 * 60)  # 0..120
    # Bucket ids: morning 0..M-1, afternoon M..2M-1. Morning elapsed 120 is the
    # final morning minute (11:30) and must stay in morning bucket M-1 (not
    # spill into afternoon's M), so cap the morning bucket index at M-1.
    morning_bucket = pl.min_horizontal(morning_elapsed // bucket_min, 120 // bucket_min - 1)
    bucket = (
        pl.when(morning)
        .then(morning_bucket)
        .otherwise(
            pl.when(afternoon)
            .then(afternoon_elapsed // bucket_min + 120 // bucket_min)
            .otherwise(None)
        )
    )
    df = raw.with_columns(
        bucket.alias("_bucket"),
        dt.dt.date().alias("_date"),
    )
    grouped = (
        df.filter(pl.col("_bucket").is_not_null())
        .group_by(["symbol", "_date", "_bucket"])
        .agg([
            pl.col("datetime").min().alias("datetime"),
            pl.col("open").first(),
            pl.col("high").max(),
            pl.col("low").min(),
            pl.col("close").last(),
            pl.col("volume").sum(),
            pl.col("amount").sum(),
        ])
        .sort(["symbol", "datetime"])
        .drop(["_date", "_bucket"])
        .with_columns(pl.lit(freq).alias("freq"))
    )
    return grouped




def _parse_minute_ts(value: int) -> datetime | None:
    s = str(value)
    if len(s) < 12:
        return None
    try:
        return datetime.strptime(s[:14], "%Y%m%d%H%M%S")
    except ValueError:
        return None
