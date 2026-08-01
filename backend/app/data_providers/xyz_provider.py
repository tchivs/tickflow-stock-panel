"""xyz (a.123128.xyz) remote market-data provider via its online MCP endpoint.

The xyz service exposes the full free-stockdb SDK (2005-present history) over a
remote JSON-RPC MCP endpoint (https://a.123128.xyz homepage, 07-27 entry):

    {"mcpServers": {"stockdb": {"url": "http://8.138.149.215:7898/mcp"}}}

This provider is the historical complement for minute K (and daily) that the
self-hosted free-stockdb HTTP server lacks (it only carries synced recent
data). It implements the JSON-RPC 2.0 streamable MCP client for the tools we
consume: stockdb_get_price (bars window) and stockdb_get_bars.

Protocol facts verified live against the endpoint:
  - POST JSON-RPC; respond with a single JSON object (HTTP, not stdio).
  - tools/call -> {"jsonrpc":"2.0","result":{"content":[{"type":"text","text":"<payload>"}]}}
    where <payload> is a Python-repr-ish JSON list of row dicts.
  - stockdb_get_price arguments: security (list[str] REQUIRED), start_date,
    end_date (YYYY-MM-DD), frequency ('1d'/'1m'/'5m'/...), fq ('pre'/'post'/None).
    Do NOT pass ``fields`` — the endpoint returns 请求参数错误 when fields is set.
  - Rows: {"time": "YYYY-MM-DDTHH:MM:SS", "code": str, "open"/"high"/"low"/"close",
    "volume", "money", ...}.
  - stockdb_get_bars: security (list), count, unit ('1d'/'1m'/...), end_dt.
    Rows: {"date": "YYYY-MM-DDTHH:MM:SS", "open", "high", "low", "close", ...}.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any

import httpx
import polars as pl

from app.data_providers.base import AssetType, ProviderCapabilities

logger = logging.getLogger(__name__)

_DEFAULT_MCP_URL = "http://8.138.149.215:7898/mcp"


class XYZProvider:
    """HTTP JSON-RPC MCP client for the xyz stockdb online endpoint."""

    name = "xyz"
    capabilities = ProviderCapabilities(
        instruments=True,
        daily=True,
        adj_factor=False,
        minute=True,
        realtime=False,
        financial=False,
    )

    def __init__(self, mcp_url: str = _DEFAULT_MCP_URL, timeout: float = 8.0) -> None:
        self.mcp_url = mcp_url
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)
        self._request_id = 0

    def close(self) -> None:
        self._client.close()

    # -- provider surface -------------------------------------------------------

    def get_daily(
        self,
        symbols: list[str],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        asset_type: AssetType = "stock",
    ) -> pl.DataFrame:
        return self._price_frame(symbols, start_time, end_time, frequency="1d")

    def get_minute(
        self,
        symbols: list[str],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        freq: str = "1m",
    ) -> pl.DataFrame:
        return self._price_frame(symbols, start_time, end_time, frequency=freq)

    def get_adj_factors(
        self,
        symbols: list[str],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        asset_type: AssetType = "stock",
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def get_instruments(self, asset_type: AssetType = "stock") -> pl.DataFrame:
        return pl.DataFrame()

    def get_realtime(
        self,
        universes: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    # -- MCP protocol -----------------------------------------------------------

    def _price_frame(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        frequency: str,
    ) -> pl.DataFrame:
        if not symbols:
            return pl.DataFrame()
        args: dict[str, Any] = {"security": [str(s).split(".")[0] for s in symbols], "frequency": frequency}
        if start_time is not None:
            args["start_date"] = start_time.strftime("%Y-%m-%d")
        if end_time is not None:
            args["end_date"] = end_time.strftime("%Y-%m-%d")
        payload = self._call_tool("stockdb_get_price", args)
        rows = _parse_payload(payload)
        if not rows:
            return pl.DataFrame()
        frames: list[pl.DataFrame] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ts = row.get("time") or row.get("date")
            if not ts:
                continue
            dt = _parse_iso(ts)
            if dt is None:
                continue
            symbol = str(row.get("code") or symbols[0]).split(".")[0]
            frames.append(pl.DataFrame({
                "symbol": [symbol],
                "datetime": [dt],
                "open": [_num(row.get("open"))],
                "high": [_num(row.get("high"))],
                "low": [_num(row.get("low"))],
                "close": [_num(row.get("close"))],
                "volume": [_num(row.get("volume"))],
                "amount": [_num(row.get("money"))],
                "freq": [frequency],
            }))
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames, how="diagonal_relaxed")

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        self._request_id += 1
        body = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        try:
            resp = self._client.post(
                self.mcp_url,
                headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
                json=body,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            logger.warning("xyz %s failed: %s", name, e)
            return ""
        if "error" in data:
            logger.warning("xyz %s error: %s", name, data["error"])
            return ""
        content = (data.get("result") or {}).get("content") or []
        texts = [c.get("text", "") for c in content if isinstance(c, dict)]
        return "\n".join(texts)


def _parse_payload(text: str) -> list[Any]:
    """Parse the MCP tool payload. The endpoint returns a Python-repr-ish list;
    it is JSON when well-formed, otherwise fall back to a tolerant parse."""
    text = text.strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Some endpoints wrap the repr in quotes or return a single quoted string.
    try:
        return json.loads(text.replace("'", '"'))
    except json.JSONDecodeError:
        return []


def _parse_iso(value: str) -> datetime | None:
    value = str(value).strip()
    if not value:
        return None
    value = value.replace("Z", "")
    try:
        return datetime.fromisoformat(value[:19])
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d")
        except ValueError:
            return None


def _num(value: Any) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
