"""Tests for the multi-source provider chain resolver and its providers.

These tests use local fakes only — no live network calls. The chain resolver,
gap-merge semantics, and both new providers (free-stockdb HTTP, xyz MCP) are
covered against mocked transport responses matching the verified wire shapes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import polars as pl
import pytest

from app.data_providers import chain
from app.data_providers.free_stockdb_provider import FreeStockDBProvider, _parse_date, _parse_minute_ts
from app.data_providers.xyz_provider import XYZProvider, _parse_iso, _parse_payload


# ---------------------------------------------------------------------------
# chain.fetch_with_chain — gap merge + fallback
# ---------------------------------------------------------------------------


class _FakeProvider:
    def __init__(self, name: str, frames: dict[str, pl.DataFrame], raises: bool = False) -> None:
        self.name = name
        self._frames = frames
        self._raises = raises

    def get_daily(self, symbols, start_time=None, end_time=None, **kwargs):  # noqa: ARG002
        if self._raises:
            raise RuntimeError("boom")
        return self._frames.get("daily", pl.DataFrame())

    def get_minute(self, symbols, start_time=None, end_time=None, **kwargs):  # noqa: ARG002
        if self._raises:
            raise RuntimeError("boom")
        return self._frames.get("minute", pl.DataFrame())


def _daily_rows(dates: list[str]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": ["000001"] * len(dates),
            "date": [datetime.strptime(d, "%Y-%m-%d").date() for d in dates],
            "open": [1.0] * len(dates),
            "high": [1.1] * len(dates),
            "low": [0.9] * len(dates),
            "close": [1.0] * len(dates),
            "volume": [100.0] * len(dates),
            "amount": [1000.0] * len(dates),
        }
    )


def test_chain_merges_gaps_across_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    """Complementary sources merge by (symbol, date); overlapping rows dedupe."""
    a = _FakeProvider("a", {"daily": _daily_rows(["2024-01-02", "2024-01-03"])})
    b = _FakeProvider("b", {"daily": _daily_rows(["2024-01-03", "2024-01-04"])})

    def fake_get(name: str):
        return {"a": a, "b": b}[name]

    monkeypatch.setattr(chain, "_get_provider", fake_get)
    merged = chain.fetch_with_chain("daily", lambda p: p.get_daily(["000001"]), providers=["a", "b"])
    assert merged.height == 3
    dates = sorted(merged["date"].cast(pl.Utf8).to_list())
    assert dates == ["2024-01-02", "2024-01-03", "2024-01-04"]


def test_chain_skips_failing_provider_and_uses_next(monkeypatch: pytest.MonkeyPatch) -> None:
    """A provider that raises is skipped; the next provider fills the window."""
    good = _FakeProvider("good", {"daily": _daily_rows(["2024-01-02"])})
    bad = _FakeProvider("bad", {}, raises=True)

    def fake_get(name: str):
        return {"good": good, "bad": bad}[name]

    monkeypatch.setattr(chain, "_get_provider", fake_get)
    merged = chain.fetch_with_chain("daily", lambda p: p.get_daily(["000001"]), providers=["bad", "good"])
    assert merged.height == 1


def test_chain_returns_empty_when_all_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    empty = _FakeProvider("empty", {})
    monkeypatch.setattr(chain, "_get_provider", lambda name: empty)
    assert chain.fetch_with_chain("daily", lambda p: p.get_daily(["000001"]), providers=["empty"]).is_empty()


# ---------------------------------------------------------------------------
# FreeStockDBProvider — HTTP protocol mapping
# ---------------------------------------------------------------------------


class _FakeTransport:
    """Returns canned free-stockdb JSON per table."""

    def __init__(self, tables: dict[str, Any]) -> None:
        self.tables = tables

    def get(self, url: str, params: dict[str, Any] | None = None, timeout: float | None = None):  # noqa: ARG002
        table = (params or {}).get("t", "")
        payload = self.tables.get(table, [])
        return _FakeResponse(payload)

    def close(self) -> None:
        pass


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


def test_free_stockdb_daily_normalizes(monkeypatch: pytest.MonkeyPatch) -> None:
    tables = {
        "日k": [
            {"code": "000001", "date": 20240102, "open": 7.88, "high": 7.91, "low": 7.86, "close": 7.87,
             "volume": 100000, "amount": 800000, "name": "平安银行", "pre_close": 7.9, "pct_chg": -0.4},
        ]
    }
    provider = FreeStockDBProvider(base_url="http://fake")
    provider._client = _FakeTransport(tables)  # type: ignore[assignment]
    df = provider.get_daily(["000001"], start_time=datetime(2024, 1, 2), end_time=datetime(2024, 1, 2))
    assert df.height == 1
    row = df.to_dicts()[0]
    assert row["symbol"] == "000001"
    assert str(row["date"]) == "2024-01-02"
    assert row["close"] == 7.87


def test_free_stockdb_minute_parses_14_digit_ts(monkeypatch: pytest.MonkeyPatch) -> None:
    tables = {
        "分钟k": [
            {"code": "000001", "date": 20240102093100, "open": 7.88, "high": 7.91, "low": 7.86, "close": 7.87,
             "volume": 1000, "amount": 8000},
        ]
    }
    provider = FreeStockDBProvider(base_url="http://fake")
    provider._client = _FakeTransport(tables)  # type: ignore[assignment]
    df = provider.get_minute(["000001"], start_time=datetime(2024, 1, 2), end_time=datetime(2024, 1, 2))
    assert df.height == 1
    row = df.to_dicts()[0]
    assert str(row["datetime"]) == "2024-01-02 09:31:00"
    assert row["freq"] == "1m"


def test_free_stockdb_adj_factor_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """The deployed HTTP build has no usable adjustment factor; chain falls back."""
    provider = FreeStockDBProvider(base_url="http://fake")
    provider._client = _FakeTransport({"复权": [{"cum": 1.41}]})  # type: ignore[assignment]
    assert provider.get_adj_factors(["000001"]).is_empty()


# ---------------------------------------------------------------------------
# XYZProvider — MCP JSON-RPC mapping
# ---------------------------------------------------------------------------


class _FakeMCPClient:
    """Returns a canned tools/call result for stockdb_get_price."""

    def __init__(self, payload: str) -> None:
        self._payload = payload

    def post(self, url: str, headers: dict[str, str] | None = None, json: dict[str, Any] | None = None, timeout: float | None = None):  # noqa: ARG002
        return _FakeMCPResponse(self._payload)

    def close(self) -> None:
        pass


class _FakeMCPResponse:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "result": {"content": [{"type": "text", "text": self._payload}]}}


def test_xyz_minute_history_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = (
        '[{"time": "2024-01-02T09:31:00", "code": "000001", "open": 7.88, "high": 7.91,'
        ' "low": 7.86, "close": 7.87, "volume": 5899529, "money": 46514749}]'
    )
    provider = XYZProvider(mcp_url="http://fake/mcp")
    provider._client = _FakeMCPClient(payload)  # type: ignore[assignment]
    df = provider.get_minute(["000001"], start_time=datetime(2024, 1, 2), end_time=datetime(2024, 1, 3))
    assert df.height == 1
    row = df.to_dicts()[0]
    assert row["symbol"] == "000001"
    assert str(row["datetime"]) == "2024-01-02 09:31:00"
    assert row["amount"] == 46514749.0


def test_xyz_mcp_error_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = XYZProvider(mcp_url="http://fake/mcp")

    class _ErrResp:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"jsonrpc": "2.0", "error": {"code": -32602, "message": "bad params"}}

    class _ErrClient:
        def post(self, *a, **k):  # noqa: ARG002
            return _ErrResp()

        def close(self) -> None:
            pass

    provider._client = _ErrClient()  # type: ignore[assignment]
    assert provider.get_minute(["000001"]).is_empty()


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def test_parse_date_handles_int_and_str() -> None:
    assert _parse_date(20240102).isoformat() == "2024-01-02"
    assert _parse_date("20240102").isoformat() == "2024-01-02"
    assert _parse_date("2024-01-02").isoformat() == "2024-01-02"
    assert _parse_date(None) is None


def test_parse_minute_ts() -> None:
    dt = _parse_minute_ts(20240102093100)
    assert dt is not None and dt.strftime("%Y%m%d%H%M%S") == "20240102093100"
    assert _parse_minute_ts(123) is None


def test_parse_payload_tolerant() -> None:
    assert _parse_payload('[{"time": "2024-01-02T00:00:00"}]') == [{"time": "2024-01-02T00:00:00"}]
    # Python repr with single quotes is tolerated
    assert _parse_payload("[{'time': '2024-01-02'}]") == [{"time": "2024-01-02"}]
    assert _parse_payload("") == []


def test_parse_iso() -> None:
    assert _parse_iso("2024-01-02T09:31:00").isoformat() == "2024-01-02T09:31:00"
    assert _parse_iso("2024-01-02").isoformat() == "2024-01-02T00:00:00"
    assert _parse_iso("") is None


def test_free_stockdb_adj_factor_keys_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """keys recovers event dates; cumulative cum converts to per-event ratio."""
    keys = ["复权:000001:20240102", "复权:000001:20240110"]
    vals = {"复权": [{"cum": 1.2}]}  # same value returned for both dates

    class _AdjTransport:
        def __init__(self) -> None:
            self._tables = vals

        def get(self, url: str, params: dict[str, Any] | None = None, timeout: float | None = None):  # noqa: ARG002
            if (params or {}).get("cmd") == "keys":
                return _FakeResponse(keys)
            return _FakeResponse(self._tables.get((params or {}).get("t", ""), []))

        def close(self) -> None:
            pass

    provider = FreeStockDBProvider(base_url="http://fake")
    provider._client = _AdjTransport()  # type: ignore[assignment]
    df = provider.get_adj_factors(["000001"])
    assert df.height == 2
    rows = df.sort("trade_date").to_dicts()
    # cum 1.2 / prev 1.0 -> 1.2 for the first event, then 1.2/1.2 -> 1.0
    assert rows[0]["trade_date"].isoformat() == "2024-01-02"
    assert abs(rows[0]["ex_factor"] - 1.2) < 1e-9
    assert abs(rows[1]["ex_factor"] - 1.0) < 1e-9


def test_free_stockdb_boards_fetch_members(monkeypatch: pytest.MonkeyPatch) -> None:
    """板块 values are read via the shared category-name k1, not the full key."""
    keys = [
        "板块:概念_5G:300843.TI",
        "板块:概念_人工智能:302035.TI",
        "板块:申万一级_电子:801080.SL",
    ]

    class _BoardTransport:
        def get(self, url: str, params: dict[str, Any] | None = None, timeout: float | None = None):
            if (params or {}).get("cmd") == "keys":
                return _FakeResponse(keys)
            cat = (params or {}).get("k1", "").removeprefix("key:")
            payload = {
                "概念_5G": [{"code": "300843.TI", "name": "5G", "category": "概念",
                             "group": "特色指数列表", "source": "ths",
                             "symbols": ["000016", "000049", "000063"]}],
                "概念_人工智能": [{"code": "302035.TI", "name": "人工智能", "category": "概念",
                                   "group": "特色指数列表", "source": "ths",
                                   "symbols": ["000016", "000032"]}],
                "申万一级_电子": [{"code": "801080.SL", "name": "电子", "category": "申万一级",
                                    "group": "申万行业指数列表", "source": "sw",
                                    "symbols": ["000020", "000021"]}],
            }
            return _FakeResponse(payload.get(cat, []))

        def close(self) -> None:
            pass

    provider = FreeStockDBProvider(base_url="http://fake")
    provider._client = _BoardTransport()  # type: ignore[assignment]

    # Substring filter: 5G matches only 概念_5G.
    df = provider.get_boards(["5G"])
    assert df.height == 1
    row = df.to_dicts()[0]
    assert row["symbol"] == "300843.TI"
    assert row["name"] == "5G"
    assert row["category"] == "概念"
    assert row["members"] == ["000016", "000049", "000063"]

    # Empty filter returns every board; member codes stay strings.
    all_ = provider.get_boards()
    assert all_.height == 3
    assert all_["members"].dtype == pl.List(pl.String)
    boards_by_name = {r["name"]: r["members"] for r in all_.to_dicts()}
    assert boards_by_name["电子"] == ["000020", "000021"]


def test_free_stockdb_boards_by_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """按板块指数代码反查: keys 尾部匹配 + category-name 取数。"""
    keys = [
        "板块:概念_5G:300843.TI",
        "板块:概念_人工智能:302035.TI",
        "板块:申万一级_电子:801080.SL",
    ]

    class _CodeTransport:
        def get(self, url: str, params: dict[str, Any] | None = None, timeout: float | None = None):
            if (params or {}).get("cmd") == "keys":
                return _FakeResponse(keys)
            cat = (params or {}).get("k1", "").removeprefix("key:")
            payload = {
                "概念_5G": [{"code": "300843.TI", "name": "5G", "category": "概念",
                             "group": "特色指数列表", "source": "ths",
                             "symbols": ["000016", "000049", "000063"]}],
                "概念_人工智能": [{"code": "302035.TI", "name": "人工智能", "category": "概念",
                                   "group": "特色指数列表", "source": "ths",
                                   "symbols": ["000016", "000032"]}],
            }
            return _FakeResponse(payload.get(cat, []))

        def close(self) -> None:
            pass

    provider = FreeStockDBProvider(base_url="http://fake")
    provider._client = _CodeTransport()  # type: ignore[assignment]

    # 完整代码与裸代码均命中。
    df = provider.get_board_by_codes(["300843.TI"])
    assert df.height == 1
    assert df.to_dicts()[0]["name"] == "5G"
    df2 = provider.get_board_by_codes(["300843"])
    assert df2.height == 1
    assert df2.to_dicts()[0]["name"] == "5G"

    # 未知代码 → 空。
    assert provider.get_board_by_codes(["999999"]).is_empty()


def test_free_stockdb_board_cache_reuses_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """板块 keys 只枚举一次; TTL 内复用; clear 后重新枚举。"""
    keys = ["板块:概念_5G:300843.TI", "板块:概念_人工智能:302035.TI"]
    call_log: list[str] = []

    class _CacheTransport:
        def get(self, url: str, params: dict[str, Any] | None = None, timeout: float | None = None):
            cmd = (params or {}).get("cmd")
            if cmd == "keys":
                call_log.append("keys")
                return _FakeResponse(keys)
            cat = (params or {}).get("k1", "").removeprefix("key:")
            call_log.append(f"vals:{cat}")
            payload = {
                "概念_5G": [{"code": "300843.TI", "name": "5G", "category": "概念",
                             "group": "特色指数列表", "source": "ths",
                             "symbols": ["000016"]}],
                "概念_人工智能": [{"code": "302035.TI", "name": "人工智能", "category": "概念",
                                    "group": "特色指数列表", "source": "ths",
                                    "symbols": ["000032"]}],
            }
            return _FakeResponse(payload.get(cat, []))

        def close(self) -> None:
            pass

    provider = FreeStockDBProvider(base_url="http://fake", board_ttl_seconds=3600)
    provider._client = _CacheTransport()  # type: ignore[assignment]

    provider.get_board_by_codes(["300843.TI"])
    provider.get_board_by_codes(["300843.TI"])  # 命中 keys + vals 缓存
    provider.get_board_by_codes(["302035.TI"])  # keys 缓存, 仅新 vals
    assert call_log == ["keys", "vals:概念_5G", "vals:概念_人工智能"]

    provider.clear_board_cache()
    call_log.clear()
    provider.get_board_by_codes(["300843.TI"])
    assert call_log == ["keys", "vals:概念_5G"]


def test_bucket_minutes_session_alignment() -> None:
    from datetime import datetime

    from app.data_providers.free_stockdb_provider import _bucket_minutes

    rows = []
    # Morning 09:30-09:34 + lunch boundary 11:30 + afternoon 13:00-13:04
    for ts in ["2026-07-28 09:30:00", "2026-07-28 09:31:00", "2026-07-28 09:32:00",
               "2026-07-28 09:33:00", "2026-07-28 09:34:00",
               "2026-07-28 11:30:00", "2026-07-28 13:00:00", "2026-07-28 13:04:00"]:
        rows.append({
            "symbol": "000001",
            "datetime": datetime.fromisoformat(ts),
            "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5,
            "volume": 100.0, "amount": 1000.0, "freq": "1m",
        })
    buckets = _bucket_minutes(pl.DataFrame(rows), 5, "5m").sort("datetime")
    times = [r["datetime"].strftime("%H:%M") for r in buckets.to_dicts()]
    # 09:30 bucket holds 09:30-09:34; 11:30 and 13:00-13:04 form separate buckets.
    assert times == ["09:30", "11:30", "13:00"]
