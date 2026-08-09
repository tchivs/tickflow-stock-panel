"""Tushare provider tests without network access."""
from __future__ import annotations

from datetime import date, datetime

import polars as pl

from app.plugins.tushare import provider as tp
from app.plugins.tushare.provider import TushareProvider


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _Client:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def post(self, url, json):
        self.calls.append((url, json))
        return _Response(self.responses[json["api_name"]])

    def close(self):
        pass


def _provider(responses):
    provider = TushareProvider(token="TOKEN", api_url="http://fixture")
    provider._client = _Client(responses)
    return provider


def test_daily_maps_tushare_units_and_symbols():
    provider = _provider({
        "daily": {"code": 0, "data": {
            "fields": ["ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"],
            "items": [["600519.SH", "20260807", 1300, 1310, 1290, 1305, 12.5, 88.0]],
        }},
    })
    frame = provider.get_daily(["600519.SH"], datetime(2026, 8, 1), datetime(2026, 8, 7))
    assert frame.to_dicts() == [{
        "symbol": "600519.SH", "date": date(2026, 8, 7),
        "open": 1300.0, "high": 1310.0, "low": 1290.0, "close": 1305.0,
        "volume": 1250.0, "amount": 88000.0,
    }]


def test_adj_factor_converts_cumulative_factor():
    provider = _provider({
        "adj_factor": {"code": 0, "data": {
            "fields": ["ts_code", "trade_date", "adj_factor"],
            "items": [["600519.SH", "20260806", 2.0], ["600519.SH", "20260807", 2.2]],
        }},
    })
    frame = provider.get_adj_factors(["600519.SH"], None, None)
    assert frame.schema["trade_date"] == pl.Date
    assert frame["ex_factor"].to_list() == [1.0, 1.1]


def test_financial_table_maps_api_and_keeps_latest_row():
    provider = _provider({
        "income": {"code": 0, "data": {
            "fields": ["ts_code", "end_date", "revenue"],
            "items": [["600519.SH", "20251231", 100], ["600519.SH", "20260331", 110]],
        }},
    })
    frame = provider.get_financials("income", ["600519.SH"], latest_only=True)
    assert frame.to_dicts() == [{"symbol": "600519.SH", "end_date": "20260331", "revenue": 110}]


def test_instruments_maps_stock_basic():
    provider = _provider({
        "stock_basic": {"code": 0, "data": {
            "fields": ["ts_code", "name", "exchange", "list_date"],
            "items": [["600519.SH", "贵州茅台", "SSE", "20010827"]],
        }},
    })
    rows = provider.get_instruments()
    assert rows[0]["symbol"] == "600519.SH"
    assert rows[0]["ext"]["listing_date"] == "20010827"


def test_availability_requires_token(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    monkeypatch.setattr(tp.Path, "exists", lambda self: False)
    assert tp.availability() == (False, "未设置 TUSHARE_TOKEN")


def test_plugin_manifest_is_linux_native():
    manifest = tp.Path(__file__).parents[1] / "app" / "plugins" / "tushare" / "plugin.yaml"
    assert manifest.exists()
    text = manifest.read_text(encoding="utf-8")
    assert "runtime: none" in text
    assert "financial" in text
