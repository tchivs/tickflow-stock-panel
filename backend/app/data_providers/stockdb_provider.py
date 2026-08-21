"""Local stockdb (docker :8000) market data provider.

HTTP adapter for the local stockdb service: X-API-Key header auth over the
REST batch endpoints ``/v1/query/daily`` / ``/v1/minute`` plus the optional
derived-data endpoints ``/v1/indicators/{symbol}`` and ``/v1/push/alerts``.
The current
``/v1/query/daily`` response uses StockDB's ``DataResponse`` envelope
(``ok/state/data`` plus quality metadata); the parser keeps the data plane
backward-compatible with the earlier wrapped response and rejects explicit
unavailable/invalid states instead of returning a false empty frame.
Mirrors FreeStockDBProvider's httpx client pattern but with typed error
classification — never the catch-all empty-frame swallow (PITFALLS P2) — and
single-point normalization of the three wire differences (measured
2026-08-07, see .planning/phases/40-stockdb-local-channel/RESEARCH.md):

  * symbol prefix form ``SH600519`` -> lake suffix form ``600519.SH``
  * ``volume_hand`` (手) is identity (x1) — the lake stores 手, never x100
  * aware Asia/Shanghai ``date``/``bar_time`` -> naive lake wall clock

Wire contract: daily returns a ``DataResponse`` whose ``data`` is
``{sym: [bars]}`` with <=200 symbols per request; minute batch currently
returns ``{sym: [bars]}`` (and the parser also accepts a DataResponse envelope);
daily window includes the end date; minute window excludes the end date (must
pass ``end + 1day``); 401/429/400 classified by status code only (body is
log-only, Pitfall 5).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timedelta
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

# tick 端点档位 60/min/key (实测, routes.py:607-620) — 与 daily/minute 的 120/min 分桶
_TICKS_RPM = 60

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


class StockDBProtocolError(Exception):
    """200 response does not match the StockDB wire contract."""


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

    @staticmethod
    def _extract_symbol_bars(payload: Any) -> dict[str, Any]:
        """Return the symbol map from direct or current ``DataResponse`` payloads.

        ``state=empty`` remains a valid zero-row result. Explicit service
        failure states must surface as protocol errors so provider-chain code
        can decide whether to fall back, rather than mistaking an outage for a
        legitimate data vacuum.
        """
        if isinstance(payload, dict) and "data" in payload:
            state = payload.get("state")
            if payload.get("ok") is False or state in {"unavailable", "invalid"}:
                raise StockDBProtocolError(f"stockdb response state={state!r}")
            payload = payload["data"]
        if not isinstance(payload, dict) or any(
            not isinstance(bars, list) for bars in payload.values()
        ):
            raise StockDBProtocolError("stockdb response data must be a symbol mapping")
        return payload

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
            payload = self._extract_symbol_bars(self._get_json("/v1/query/daily", {
                "symbols": ",".join(_to_prefix(s) for s in chunk),
                "start": start_time.strftime("%Y-%m-%d") if start_time else None,
                "end": end_time.strftime("%Y-%m-%d") if end_time else None,
                "adjust": "none",  # 原始价进湖, 复权读取时算
            }))
            for _sym, bars in payload.items():  # 新协议 data = {sym: [bars]}
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
            payload = self._extract_symbol_bars(self._get_json("/v1/minute", {
                "symbols": ",".join(_to_prefix(s) for s in chunk),
                "start": start_time.strftime("%Y-%m-%d") if start_time else None,
                "end": end_param,
                "freq": _MINUTE_UNIT.get(freq, 1),  # 服务端 freq 为 int 枚举
            }))
            for _sym, bars in payload.items():
                rows.extend(self._map_minute_row(b, freq) for b in bars)
        if not rows:
            return pl.DataFrame()
        return pl.DataFrame(rows).select(
            ["symbol", "datetime", "open", "high", "low", "close", "volume", "amount", "freq"]
        )

    def get_indicators(
        self,
        symbol: str,
        name: str = "ma",
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        adjust: str = "none",
        **params: int | float,
    ) -> list[dict[str, Any]]:
        """Read StockDB's derived daily indicators without changing the lake."""
        query: dict[str, Any] = {
            "name": name,
            "start": start_time.strftime("%Y-%m-%d") if start_time else None,
            "end": end_time.strftime("%Y-%m-%d") if end_time else None,
            "adjust": adjust,
            **params,
        }
        payload = self._get_json(f"/v1/indicators/{_to_prefix(symbol)}", query)
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise StockDBProtocolError("stockdb indicators response must be a list of objects")
        return payload

    def get_push_alerts(
        self, *, threshold: float = 5.0, limit: int = 100
    ) -> list[dict[str, Any]] | None:
        """Read optional THS push alerts; 404 means the upstream feature is disabled."""
        try:
            payload = self._get_json(
                "/v1/push/alerts", {"threshold": threshold, "limit": limit}
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        if not isinstance(payload, dict) or not isinstance(payload.get("alerts"), list):
            raise StockDBProtocolError("stockdb push alerts response must contain alerts[]")
        alerts = payload["alerts"]
        if any(not isinstance(alert, dict) for alert in alerts):
            raise StockDBProtocolError("stockdb push alerts must contain objects")
        return alerts

    def get_ticks(self, symbol: str, trade_date: date) -> list[dict]:
        """GET /v1/ticks/{symbol}?date=YYYYMMDD — 单 symbol 全天分笔 (原始 TickBar list)。

        服务端 fetch-on-miss (kernel/service.py:488-490): 湖文件缺失 → 全窗口一次
        采集落盘; 文件存在 → 只读不刷新。一次 GET 即决定当日文件内容 → **请求必带
        ?date=T** (09:15 前无 date 服务端回退上一交易日, Pitfall 3)。60/min 档位
        用进程级共享限速器对齐 (tick 服务端档位, 与 daily/minute 的 120/min 分桶)。
        返回原始 JSON list (TickBar dict 原样, 零归一化) — 归一化交给采集层
        (staging 契约单点)。typed 异常 (401/429/400) 走 ``_get_json`` 唯一请求面。
        """
        sleep_between_batches(0, _TICKS_RPM)
        payload = self._get_json(f"/v1/ticks/{_to_prefix(symbol)}", {
            "date": trade_date.strftime("%Y%m%d"),
        })
        return payload if isinstance(payload, list) else []
