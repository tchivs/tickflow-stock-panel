"""Local stockdb (docker :8000) market data provider.

HTTP adapter for the local stockdb service: X-API-Key header auth over the
REST batch endpoints ``/v1/daily`` / ``/v1/minute``. Mirrors
FreeStockDBProvider's httpx client pattern but with typed error
classification — never the catch-all empty-frame swallow (PITFALLS P2) — and
single-point normalization of the three wire differences (measured
2026-08-07, see .planning/phases/40-stockdb-local-channel/RESEARCH.md):

  * symbol prefix form ``SH600519`` -> lake suffix form ``600519.SH``
  * ``volume_hand`` (手) is identity (x1) — the lake stores 手, never x100
  * aware Asia/Shanghai ``date``/``bar_time`` -> naive lake wall clock

Wire contract: batch endpoints return ``{sym: [bars]}`` with <=200 symbols
per request; daily window includes the end date; minute window excludes the
end date (must pass ``end + 1day``); 401/429/400 classified by status code
only (body is log-only, Pitfall 5).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any

import httpx
import polars as pl

from app.config import settings
from app.data_providers.base import ProviderCapabilities
from app.data_providers.normalizer import normalize_daily
from app.tickflow.rate_limits import chunked, sleep_between_batches

logger = logging.getLogger(__name__)

# 服务端 freq 为 int 枚举 (kernel/minute.py)
_MINUTE_UNIT = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}

_SYMBOL_PREFIX_RE = re.compile(r"^(SH|SZ|BJ)(\d{6})$")
_SYMBOL_SUFFIX_RE = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$")

# provenance 列 — 湖无 provenance 列铁律, 丢弃 (通道身份进日志)
_PROVENANCE_COLS = ("source", "fetched_at", "ingested_at", "schema_version")


def _to_suffix(symbol: str) -> str:
    """``SH600519`` -> ``600519.SH``; 已规范/裸码原样透传."""
    m = _SYMBOL_PREFIX_RE.match(symbol)
    return f"{m.group(2)}.{m.group(1)}" if m else symbol


def _to_prefix(symbol: str) -> str:
    """``600519.SH`` -> ``SH600519``; 已前缀形态/裸码原样透传."""
    m = _SYMBOL_SUFFIX_RE.match(symbol)
    return f"{m.group(2)}{m.group(1)}" if m else symbol


class StockDBAuthError(Exception):
    """401 — credential/config error, never retried."""


class StockDBRateLimited(Exception):
    """429 after honoring Retry-After once — surfaced, never faked as empty."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"stockdb rate limited (retry_after={retry_after})")
        self.retry_after = retry_after


class StockDBBadRequest(Exception):
    """400 — programming error (bad adjust/freq/batch size)."""


def _parse_retry_after(resp: httpx.Response) -> float:
    """Retry-After 头优先, 回退 body ``retry_after``, 再缺省 1s."""
    header = resp.headers.get("Retry-After")
    if header is not None:
        try:
            return float(header)
        except ValueError:
            pass
    try:
        body = resp.json()
    except ValueError:
        return 1.0
    if isinstance(body, dict):
        try:
            return float(body.get("retry_after", 1.0))
        except (TypeError, ValueError):
            return 1.0
    return 1.0


class StockDBProvider:
    """HTTP client for the local stockdb service (docker :8000)."""

    name = "local_stockdb"
    capabilities = ProviderCapabilities(
        instruments=False,
        daily=True,
        adj_factor=False,
        minute=True,
        realtime=False,
        financial=False,
        auction=False,  # 诚实声明无竞价 -> auction_probe 按 capabilities.auction 枚举排除
    )

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        timeout: float = 20.0,
        rpm: int = 120,
        batch_size: int = 200,
    ) -> None:
        self.base_url = (base_url or getattr(settings, "local_stockdb_url", "")).rstrip("/")
        self.api_key = api_key or getattr(settings, "local_stockdb_api_key", "")
        self.rpm = rpm
        self.batch_size = batch_size
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    # -- wire helpers ---------------------------------------------------------

    def _get_json(self, path: str, params: dict[str, Any]) -> Any:
        """唯一请求面: X-API-Key header-only (禁 URL 传参), 按状态码 typed 分类.

        401 -> StockDBAuthError (不重试); 429 -> 按 Retry-After sleep 后重试
        1 次, 仍 429 -> StockDBRateLimited 上抛 (绝不伪装空帧); 400 ->
        StockDBBadRequest; 其余 raise_for_status; 200 返回 json。
        """
        resp = self._client.get(
            self.base_url + path, params=params, headers={"X-API-Key": self.api_key}
        )
        if resp.status_code == 429:
            retry_after = _parse_retry_after(resp)
            time.sleep(retry_after)
            resp = self._client.get(
                self.base_url + path, params=params, headers={"X-API-Key": self.api_key}
            )
            if resp.status_code == 429:
                raise StockDBRateLimited(_parse_retry_after(resp))
        if resp.status_code == 401:
            raise StockDBAuthError(f"stockdb auth failed: {resp.text[:200]}")
        if resp.status_code == 400:
            raise StockDBBadRequest(resp.text[:200])
        resp.raise_for_status()
        return resp.json()

    # -- normalization (三差异唯一转换点) --------------------------------------

    def _map_daily_row(self, bar: dict) -> dict:
        """stockdb 日K bar -> 湖内规范行 (symbol 后缀 / volume 恒等 x1 / date naive)."""
        return {
            "symbol": _to_suffix(str(bar.get("symbol"))),
            "date": datetime.fromisoformat(bar["date"]).date(),
            "open": float(bar["open"]),
            "high": float(bar["high"]),
            "low": float(bar["low"]),
            "close": float(bar["close"]),
            "volume": float(bar["volume_hand"]),  # 恒等 x1 — 湖实测 = 手, 绝不 x100
            "amount": float(bar["amount_yuan"]) if bar.get("amount_yuan") is not None else None,
        }

    def _map_minute_row(self, bar: dict, freq: str) -> dict:
        """stockdb 分钟 bar -> 规范行 (bar_time aware -> naive 北京墙钟)."""
        return {
            "symbol": _to_suffix(str(bar.get("symbol"))),
            "datetime": datetime.fromisoformat(bar["bar_time"]).replace(tzinfo=None),
            "open": float(bar["open"]),
            "high": float(bar["high"]),
            "low": float(bar["low"]),
            "close": float(bar["close"]),
            "volume": float(bar["volume_hand"]),  # 与 daily 湖同口径 (手, 恒等)
            "amount": float(bar["amount_yuan"]) if bar.get("amount_yuan") is not None else None,
            "freq": freq,
        }

    # -- public provider surface ----------------------------------------------

    def get_daily(
        self,
        symbols: list[str],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        asset_type: str = "stock",
        **kwargs: Any,
    ) -> pl.DataFrame:
        if not symbols:
            return pl.DataFrame()
        rows: list[dict] = []
        for i, chunk in enumerate(chunked(list(symbols), self.batch_size)):
            sleep_between_batches(i, self.rpm)  # rpm=120 对齐服务端 daily 档位
            payload = self._get_json("/v1/daily", {
                "symbols": ",".join(_to_prefix(s) for s in chunk),
                "start": start_time.strftime("%Y-%m-%d") if start_time else None,
                "end": end_time.strftime("%Y-%m-%d") if end_time else None,
                "adjust": "none",  # 原始价进湖, 复权读取时算
            })
            for sym, bars in payload.items():  # 批响应 = {sym: [bars]} (实测)
                rows.extend(self._map_daily_row(b) for b in bars)
        if not rows:
            return pl.DataFrame()
        return normalize_daily(rows, source=self.name)  # cast + filter_halt_days + 规范列裁剪

    def get_minute(
        self,
        symbols: list[str],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        freq: str = "1m",
        **kwargs: Any,
    ) -> pl.DataFrame:
        if not symbols:
            return pl.DataFrame()
        # 端日语义 (Pitfall 3): 服务端分钟窗口不含 end 日 -> 传 end+1day
        end_param: str | None = None
        if end_time is not None:
            end_param = (end_time + timedelta(days=1)).strftime("%Y-%m-%d")
        rows: list[dict] = []
        for i, chunk in enumerate(chunked(list(symbols), self.batch_size)):
            sleep_between_batches(i, self.rpm)  # rpm=120 对齐服务端 minute 档位
            payload = self._get_json("/v1/minute", {
                "symbols": ",".join(_to_prefix(s) for s in chunk),
                "start": start_time.strftime("%Y-%m-%d") if start_time else None,
                "end": end_param,
                "freq": _MINUTE_UNIT.get(freq, 1),  # 服务端 freq 为 int 枚举
            })
            for sym, bars in payload.items():
                rows.extend(self._map_minute_row(b, freq) for b in bars)
        if not rows:
            return pl.DataFrame()
        return pl.DataFrame(rows).select(
            ["symbol", "datetime", "open", "high", "low", "close", "volume", "amount", "freq"]
        )
