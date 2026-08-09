"""Linux-native Tushare Pro provider.

The provider uses Tushare's JSON HTTP API directly, so it does not require the
Windows client or the optional tushare Python package. Minute and realtime
data intentionally remain on the existing providers; this plugin fills the
financial-data and reference-data gap.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import polars as pl

from app.data_providers.normalizer import normalize_adj_factors, normalize_daily

_API_URL = "https://api.tushare.pro"
_BATCH_SIZE = 100
_TIMEOUT = 30.0
_FINANCIAL_APIS = {
    "metrics": "fina_indicator",
    "income": "income",
    "balance_sheet": "balancesheet",
    "cash_flow": "cashflow",
}


def _token() -> str:
    value = os.getenv("TUSHARE_TOKEN", "").strip()
    if value:
        return value
    for path in (Path.cwd() / ".env", Path(__file__).resolve().parents[4] / ".env"):
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                text = line.strip()
                if text and not text.startswith("#") and "=" in text:
                    key, value = text.split("=", 1)
                    if key.strip() == "TUSHARE_TOKEN":
                        return value.strip().strip("\"'")
        except OSError:
            continue
    return ""


def availability() -> tuple[bool, str]:
    """Return plugin readiness without making a paid/API request."""
    return (True, "token configured") if _token() else (False, "未设置 TUSHARE_TOKEN")


class TushareProvider:
    name = "tushare"
    builtin = True

    def __init__(self, token: str | None = None, api_url: str = _API_URL) -> None:
        self._token = (token or _token()).strip()
        self._api_url = api_url
        self._client = httpx.Client(timeout=_TIMEOUT)

    def close(self) -> None:
        self._client.close()

    def get_daily(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: str = "stock",  # noqa: ARG002
        on_chunk_done=None,
    ) -> pl.DataFrame:
        rows: list[dict[str, Any]] = []
        chunks = list(_chunks(symbols))
        for index, chunk in enumerate(chunks):
            rows.extend(self._request_rows("daily", self._symbol_params(chunk, start_time, end_time)))
            if on_chunk_done:
                on_chunk_done(index + 1, len(chunks))
        if not rows:
            return pl.DataFrame()
        mapped = []
        for row in rows:
            item = dict(row)
            item["symbol"] = _symbol(item.get("ts_code"))
            item.pop("ts_code", None)
            item["date"] = _date_value(item.pop("trade_date", None))
            volume = item.pop("vol", None)
            amount = item.pop("amount", None)
            if volume is not None:
                item["volume"] = _number(volume) * 100
            if amount is not None:
                item["amount"] = _number(amount) * 1000
            mapped.append(item)
        return normalize_daily(mapped, source=self.name)

    def get_adj_factors(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: str = "stock",  # noqa: ARG002
        on_chunk_done=None,
    ) -> pl.DataFrame:
        rows: list[dict[str, Any]] = []
        chunks = list(_chunks(symbols))
        for index, chunk in enumerate(chunks):
            rows.extend(self._request_rows("adj_factor", self._symbol_params(chunk, start_time, end_time)))
            if on_chunk_done:
                on_chunk_done(index + 1, len(chunks))
        if not rows:
            return pl.DataFrame()
        mapped = [
            {
                "symbol": _symbol(row.get("ts_code")),
                "trade_date": _date_value(row.get("trade_date")),
                "ex_factor": row.get("adj_factor"),
            }
            for row in rows
        ]
        frame = normalize_adj_factors(mapped, source=self.name)
        if frame.is_empty():
            return frame
        return (
            frame.sort(["symbol", "trade_date"])
            .with_columns(
                (
                    pl.col("ex_factor")
                    / pl.col("ex_factor").shift(1).over("symbol")
                )
                .fill_null(1.0)
                .alias("ex_factor")
            )
        )

    def get_instruments(self, asset_type: str = "stock") -> list[dict]:
        if asset_type != "stock":
            return []
        rows = self._request_rows(
            "stock_basic",
            {"exchange": "", "list_status": "L", "fields": "ts_code,name,exchange,list_date"},
        )
        out = []
        for row in rows:
            symbol = _symbol(row.get("ts_code"))
            if not symbol:
                continue
            out.append({
                "symbol": symbol,
                "name": row.get("name") or symbol,
                "code": symbol.split(".")[0],
                "exchange": row.get("exchange"),
                "region": "CN",
                "type": "stock",
                "ext": {"listing_date": row.get("list_date")},
            })
        return out

    def get_financials(
        self,
        table: str,
        symbols: list[str],
        latest_only: bool = True,
    ) -> pl.DataFrame:
        api_name = _FINANCIAL_APIS.get(table)
        if api_name is None:
            raise ValueError(f"unsupported financial table: {table}")
        rows: list[dict[str, Any]] = []
        for chunk in _chunks(symbols):
            rows.extend(self._request_rows(api_name, {"ts_code": ",".join(_tushare_symbol(s) for s in chunk)}))
        if not rows:
            return pl.DataFrame()
        frame = pl.DataFrame(rows).rename({"ts_code": "symbol"}) if "ts_code" in rows[0] else pl.DataFrame(rows)
        if "symbol" in frame.columns:
            frame = frame.with_columns(
                pl.col("symbol").map_elements(_symbol, return_dtype=pl.String).alias("symbol")
            )
        if latest_only and "end_date" in frame.columns:
            frame = (
                frame.with_columns(pl.col("end_date").cast(pl.String))
                .sort(["symbol", "end_date"])
                .unique(subset=["symbol"], keep="last")
            )
        return frame

    def _symbol_params(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"ts_code": ",".join(_tushare_symbol(s) for s in symbols)}
        if start_time:
            params["start_date"] = start_time.strftime("%Y%m%d")
        if end_time:
            params["end_date"] = end_time.strftime("%Y%m%d")
        return params

    def _request_rows(self, api_name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if not self._token:
            raise RuntimeError("TUSHARE_TOKEN 未设置")
        response = self._client.post(
            self._api_url,
            json={"api_name": api_name, "token": self._token, "params": params, "fields": ""},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(f"Tushare {api_name} failed: {payload.get('msg', 'unknown error')}")
        data = payload.get("data") or {}
        fields = data.get("fields") or []
        return [dict(zip(fields, item)) for item in (data.get("items") or [])]


def _chunks(symbols: list[str], size: int = _BATCH_SIZE):
    clean = [str(symbol) for symbol in symbols if str(symbol).strip()]
    for index in range(0, len(clean), size):
        yield clean[index:index + size]


def _tushare_symbol(value: str) -> str:
    text = str(value).strip().upper()
    if "." in text:
        code, exchange = text.split(".", 1)
        return f"{code}.{exchange}"
    if text.startswith(("SH", "SZ", "BJ")):
        return f"{text[2:]}.{text[:2]}"
    if text.startswith(("5", "6", "9")):
        return f"{text}.SH"
    if text.startswith(("4", "8")):
        return f"{text}.BJ"
    return f"{text}.SZ"


def _symbol(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().upper()
    return text if "." in text else _tushare_symbol(text)


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _date_value(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text or None
