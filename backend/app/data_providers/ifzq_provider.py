"""Sina finance (quotes.sina.cn) K-line data provider.

Third-priority source in the a-stock-data provider policy. Provides raw
(unadjusted) daily/minute K via ``CN_MarketDataService.getKLineData`` with a
Referer header. Complements the chain:
  - daily: Tencent ifzq qfq daily (deep date-window pagination, qfq adjusted)
  - minute: Tencent ifzq mkline (recent ~10 days only, no pagination)
    and Sina getKLineData (scale 5 default; no paging either — both serve a
    trailing window, so historical minute gaps still rely on xyz/free-stockdb)

Endpoints verified live (2026-08):
  https://ifzq.gtimg.cn/appstock/app/kline/mkline?param=<pfx><code>,m5,,<count>
    -> {code:0, data:{<sym>:{m1/m5/m15/m30/m60: [[ts, open, close, high,
       low, volume(手), {}, turnover_base], ...]}}}
    Trailing only; count caps ~320 rows (m5). 第 7 字段是换手率基点不是成交额.
  https://ifzq.gtimg.cn/appstock/app/fqkline/get?param=<pfx><code>,day,
       <start>,<end>,<count>,qfq
    -> {code:0, data:{<sym>:{qfqday: [[date, open, close, high, low, vol(手)], ...]}}}
    Supports date-window pagination (year chunks) for full qfq history.
  https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20<sym>=/
       CN_MarketDataService.getKLineData?symbol=<sym>&scale=5&ma=no&datalen=<n>
    -> /*...*/ var <sym>=([{day, open, high, low, close, volume, amount}, ...]);
    Raw prices (不复权). datalen<=1500 for scale=240 (daily); scale=1/5/15/30/60
    minute bars trailing window only (no paging).

Symbols are normalized to bare 6-digit codes with the a-stock-data prefix
routing (5x/6x/9x→sh, 00/30x→sz, 4x/8x/92x→bj, SH_INDEX whitelist).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any

import httpx
import polars as pl

from app.data_providers.base import ProviderCapabilities

logger = logging.getLogger(__name__)

SH_INDEX = {"000300", "000905", "000016", "000688", "000852", "000010"}

_IFZQ = "https://ifzq.gtimg.cn"
_SINA = "https://quotes.sina.cn"
_TIMEOUT = 10.0
# mkline 单次最大行数 (m5 实测 ~320, 更大被截断)。
_MKLINE_CAP = 800
# fqkline 单年 ~250 行, 一年一窗足够。
_DAILY_YEAR_CHUNK = 366
_SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}

# mkline 频率 → 分钟数 (用于 bucket 校验)
_MKLINE_FREQ_MIN = {"m1": 1, "m5": 5, "m15": 15, "m30": 30, "m60": 60}


def _norm_symbol(symbol: str) -> str:
    s = str(symbol).strip()
    if s.lower().startswith(("sh", "sz", "bj")):
        return s[2:]
    return s.split(".")[0]


def _prefix(code: str) -> str:
    c = code.lower()
    if c.startswith(("sh", "sz", "bj")):
        return c[:2]
    if c.startswith("92"):
        return "bj"
    if c.startswith(("5", "6", "9")):
        return "sh"
    if c.startswith(("4", "8")):
        return "bj"
    if code in SH_INDEX:
        return "sh"
    return "sz"


class IfzqKlineProvider:
    """Tencent ifzq K-line provider: qfq daily (full history) + minute window.

    Implements the MarketDataProvider protocol (daily/minute/adj_factor) so it
    can slot into the provider chain alongside free_stockdb/xyz/tickflow.
    """

    name = "ifzq"
    display_name = "腾讯 ifzq K线 (前复权)"

    capabilities = ProviderCapabilities(
        instruments=False,
        daily=True,
        adj_factor=False,
        minute=True,
        realtime=False,
        financial=False,
    )

    def __init__(self, base_url: str = _IFZQ, timeout: float = _TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    # -- provider surface ------------------------------------------------------

    def get_daily(
        self,
        symbols: list[str],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        asset_type: Any = None,
    ) -> pl.DataFrame:
        frames: list[pl.DataFrame] = []
        for symbol in symbols:
            code = _norm_symbol(symbol)
            if not code:
                continue
            rows = self._fetch_qfq_daily(code, start_time, end_time)
            if rows:
                frames.append(pl.DataFrame(rows))
        if not frames:
            return pl.DataFrame()
        df = pl.concat(frames, how="diagonal_relaxed")
        return self._normalize_daily(df)

    def get_minute(
        self,
        symbols: list[str],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        freq: str = "1m",
    ) -> pl.DataFrame:
        # 内部 freq 是 "1m"/"5m"/"15m"/"30m"/"60m"; ifzq mkline 用 "m1".."m60"。
        mkline_freq = f"m{freq[:-1]}" if freq.endswith("m") else freq
        if mkline_freq not in _MKLINE_FREQ_MIN:
            return pl.DataFrame()
        rows_out: list[dict] = []
        for symbol in symbols:
            code = _norm_symbol(symbol)
            if not code:
                continue
            rows = self._fetch_mkline(code, mkline_freq)
            if not rows:
                continue
            for row in rows:
                if len(row) < 6:
                    continue
                ts = _parse_mkline_ts(row[0])
                if ts is None:
                    continue
                if start_time is not None and ts < start_time:
                    continue
                if end_time is not None and ts > end_time:
                    continue
                rows_out.append({
                    "symbol": symbol,
                    "datetime": ts,
                    "open": _num(row[1]),
                    "close": _num(row[2]),
                    "high": _num(row[3]),
                    "low": _num(row[4]),
                    "volume": _num(row[5]) * 100,  # 手 → 股
                    "amount": 0.0,
                    "freq": freq,
                })
        if not rows_out:
            return pl.DataFrame()
        df = pl.DataFrame(rows_out)
        return df.sort(["symbol", "datetime"])

    def get_adj_factors(self, symbols, start_time=None, end_time=None, asset_type=None) -> pl.DataFrame:
        return pl.DataFrame()

    # -- ifzq protocol ---------------------------------------------------------

    def _fetch_qfq_daily(self, code: str, start_time: datetime | None,
                         end_time: datetime | None) -> list[dict]:
        """前复权日K, 按年分窗拉取 (fqkline 支持日期窗口, 单窗 ~250 行)。"""
        pfx = _prefix(code)
        sym = f"{pfx}{code}"
        # 窗口: 请求区间 + 2 年缓冲 (拉前复权需足够前置除权窗口对齐)。
        end = end_time or datetime.now()
        start = start_time or (end - timedelta(days=3 * 366))
        out: list[dict] = []
        cursor = start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=_DAILY_YEAR_CHUNK), end)
            rows = self._fetch_qfq_window(sym, cursor, chunk_end)
            out.extend(rows)
            cursor = chunk_end + timedelta(days=1)
            if len(out) > 30000:  # 防御
                break
        # 过滤到请求窗口
        s = start_time.date() if start_time else None
        e = end_time.date() if end_time else None
        return [
            r for r in out
            if (s is None or r["date"] >= s) and (e is None or r["date"] <= e)
        ]

    def _fetch_qfq_window(self, sym: str, start: datetime, end: datetime) -> list[dict]:
        url = f"{self.base_url}/appstock/app/fqkline/get"
        params = {"param": f"{sym},day,{start:%Y-%m-%d},{end:%Y-%m-%d},640,qfq"}
        try:
            resp = self._client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            logger.warning("ifzq daily %s failed: %s", sym, e)
            return []
        node = self._extract_node(payload, sym)
        arr = node.get("qfqday") or node.get("day") or []
        rows: list[dict] = []
        for item in arr:
            if len(item) < 6:
                continue
            d = _parse_date(item[0])
            if d is None:
                continue
            rows.append({
                "symbol": sym,
                "date": d,
                "open": _num(item[1]),
                "close": _num(item[2]),
                "high": _num(item[3]),
                "low": _num(item[4]),
                "volume": _num(item[5]) * 100,  # 手 → 股
                "amount": 0.0,
            })
        return rows

    def _fetch_mkline(self, code: str, freq: str) -> list[list[str]]:
        """分钟K 尾部窗口 (无分页, ~320 行 m5)。"""
        pfx = _prefix(code)
        sym = f"{pfx}{code}"
        url = f"{self.base_url}/appstock/app/kline/mkline"
        params = {"param": f"{sym},{freq},,{_MKLINE_CAP}"}
        try:
            resp = self._client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            logger.warning("ifzq minute %s %s failed: %s", sym, freq, e)
            return []
        node = self._extract_node(payload, sym)
        return node.get(freq) or []

    @staticmethod
    def _extract_node(payload: Any, sym: str) -> dict:
        if not isinstance(payload, dict):
            return {}
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            return {}
        node = data.get(sym)
        if isinstance(node, dict):
            return node
        # data 里可能只挂 qt (实时) 而 K 线键是 sym; 回退第一个非 qt 节点
        for key, value in data.items():
            if key != "qt" and isinstance(value, dict):
                return value
        return {}

    @staticmethod
    def _normalize_daily(df: pl.DataFrame) -> pl.DataFrame:
        if df.is_empty():
            return df
        df = df.rename({"symbol": "symbol"})
        return df


# =========================================================================
# Sina getKLineData (不复权) — 备用分钟/日K, 独立 provider 不冲突
# =========================================================================

_SINA_SCALE_MIN = {"1": 1, "5": 5, "15": 15, "30": 30, "60": 60, "240": 240}


class SinaKlineProvider:
    """Sina raw K-line (unadjusted). Trailing window only (no pagination)."""

    name = "sina"
    display_name = "新浪 K线 (不复权)"

    capabilities = ProviderCapabilities(
        instruments=False,
        daily=True,
        adj_factor=False,
        minute=True,
        realtime=False,
        financial=False,
    )

    def __init__(self, base_url: str = _SINA, timeout: float = _TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout, follow_redirects=True,
                                    headers=_SINA_HEADERS)

    def close(self) -> None:
        self._client.close()

    def get_daily(self, symbols, start_time=None, end_time=None, asset_type=None) -> pl.DataFrame:
        return self._kline(symbols, "240", start_time, end_time)

    def get_minute(self, symbols, start_time=None, end_time=None, freq: str = "5m") -> pl.DataFrame:
        scale = str(_MIN_TO_SINA.get(freq, 5))
        return self._kline(symbols, scale, start_time, end_time, freq=freq)

    def _kline(self, symbols, scale: str, start_time, end_time, freq: str | None = None) -> pl.DataFrame:
        frames: list[pl.DataFrame] = []
        for symbol in symbols:
            code = _norm_symbol(symbol)
            if not code:
                continue
            rows = self._fetch(code, scale)
            if not rows:
                continue
            for row in rows:
                ts = _parse_sina_dt(row.get("day"))
                if ts is None:
                    continue
                if start_time is not None and ts < start_time:
                    continue
                if end_time is not None and ts > end_time:
                    continue
                frames.append({
                    "symbol": symbol,
                    "datetime": ts,
                    "open": _num(row.get("open")),
                    "close": _num(row.get("close")),
                    "high": _num(row.get("high")),
                    "low": _num(row.get("low")),
                    "volume": _num(row.get("volume")),
                    "amount": _num(row.get("amount")),
                    "freq": freq or ("1d" if scale == "240" else f"{scale}m"),
                })
        if not frames:
            return pl.DataFrame()
        return pl.DataFrame(frames).sort(["symbol", "datetime"])

    def _fetch(self, code: str, scale: str) -> list[dict]:
        pfx = _prefix(code)
        sym = f"{pfx}{code}"
        url = f"{self.base_url}/cn/api/jsonp_v2.php/var%20{sym}=/CN_MarketDataService.getKLineData"
        params = {"symbol": sym, "scale": scale, "ma": "no", "datalen": "1500"}
        try:
            resp = self._client.get(url, params=params)
            resp.raise_for_status()
            text = resp.text
        except Exception as e:
            logger.warning("sina kline %s scale=%s failed: %s", sym, scale, e)
            return []
        match = re.search(r"\((\[.*\])\s*\)\s*;?", text, re.S)
        if not match:
            return []
        try:
            return json.loads(match.group(1))
        except Exception:
            return []

    def get_adj_factors(self, symbols, start_time=None, end_time=None, asset_type=None) -> pl.DataFrame:
        return pl.DataFrame()


_MIN_TO_SINA = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60, "1d": 240, "day": 240, "daily": 240}


def _num(value: Any) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _parse_date(value: Any) -> datetime.date | None:
    if value is None:
        return None
    text = str(value)[:10]
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_mkline_ts(value: str) -> datetime | None:
    """202607311456 → datetime (精确到分钟)。"""
    s = str(value)[:12]
    try:
        return datetime.strptime(s, "%Y%m%d%H%M")
    except ValueError:
        return None


def _parse_sina_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None
