"""Tests for the hhxg static-snapshot client and its market-recap injection.

All offline — a fake transport returns canned JSON matching the verified
hhxg.top wire shapes (snapshot/margin/calendar/news). No live network calls.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.services.hhxg_market import SUPPORTED_SCHEMA, HhxgMarketClient


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class _FakeTransport:
    """Serves canned hhxg JSON per path."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url: str, params: dict[str, str] | None = None, **kwargs: Any) -> _FakeResponse:
        path = url.split("hhxg.top")[-1]
        if params:
            path += "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        self.calls.append(path)
        return _FakeResponse(self.routes.get(path, {"success": False}))

    def close(self) -> None:
        pass


_SNAPSHOT = {
    "success": True,
    "data": {
        "meta": {"provider": "hhxg.top", "schema_version": 3},
        "date": "2026-07-31",
        "ai_summary": {"market_state": "放量普涨", "focus_direction": "科技"},
        "market": {"sentiment_index": 72, "sentiment_label": "强"},
        "hot_themes": [{"name": "AI智能体", "limitup_count": 25}],
        "focus_news": [{"t": "2026-08-02T07:04:30", "cat": "焦点", "title": "焦点新闻A"}],
        "macro_news": [{"t": "2026-07-31T23:35:42", "cat": "宏观", "title": "宏观新闻B"}],
    },
}

_MARGIN = {
    "success": True,
    "data": {
        "scope": "margin",
        "schema_version": 2,
        "market": {
            "daily_totals": [
                {"date": "2026-07-30", "rzye_yi": 25659.64, "rqye_yi": 220.0, "rzrqye_yi": 25879.64},
            ]
        },
        "top": {
            "increase_rzye": [{"code": "588000.SH", "name": "科创50", "delta_rzye_yi": 11.98}],
        },
    },
}

_CAL_TRADING = {"success": True, "type": "trading", "month": "2026-08", "data": ["2026-08-03", "2026-08-04"]}
_CAL_UNLOCK = {
    "success": True,
    "type": "unlock",
    "month": "2026-08",
    "data": {"month": "2026-08", "event_count": 1,
             "events": [{"date": "2026-08-03", "type": "unlock", "label": "限售解禁",
                          "description": "某股解禁", "count": 15, "total_value": 132.2}]},
}
_NEWS = {"success": True, "data": {"items": [{"t": "2026-08-02T07:00:00", "cat": "焦点", "title": "快讯X"}]}}


def _client(routes: dict[str, Any]) -> HhxgMarketClient:
    c = HhxgMarketClient(ttl_seconds=3600)
    c._client = _FakeTransport(routes)  # type: ignore[assignment]
    return c


def test_snapshot_parses_and_checks_schema() -> None:
    c = _client({"/api/snapshot": _SNAPSHOT})
    s = c.snapshot()
    assert s is not None
    assert s["date"] == "2026-07-31"
    assert s["market"]["sentiment_label"] == "强"
    assert s["meta"]["schema_version"] == SUPPORTED_SCHEMA


def test_snapshot_news_normalizes_focus_and_macro() -> None:
    c = _client({"/api/snapshot": _SNAPSHOT})
    news = c.snapshot_news()
    assert len(news) == 2
    titles = {n["title"] for n in news}
    assert titles == {"焦点新闻A", "宏观新闻B"}
    assert all(n["source"] == "hhxg" for n in news)


def test_margin_flat_and_rows() -> None:
    c = _client({"/api/margin": _MARGIN})
    payload = c.margin()
    assert payload is not None
    rows = c.margin_rows()
    assert len(rows) == 2  # 1 daily_total + 1 融资净买入
    assert {"daily_total", "融资净买入"} <= {r["scope"] for r in rows}


def test_calendar_trading_returns_dates() -> None:
    c = _client({"/api/calendar?month=2026-08&type=trading": _CAL_TRADING})
    dates = c.calendar("trading", "2026-08")
    assert dates == ["2026-08-03", "2026-08-04"]


def test_calendar_unlock_returns_events() -> None:
    c = _client({"/api/calendar?month=2026-08&type=unlock": _CAL_UNLOCK})
    events = c.calendar_events("unlock", "2026-08")
    assert len(events) == 1
    assert events[0]["label"] == "限售解禁"
    assert events[0]["count"] == 15


def test_news_items_shape() -> None:
    c = _client({"/api/news?limit=3": _NEWS})
    news = c.news(limit=3)
    assert len(news) == 1
    assert news[0]["title"] == "快讯X"
    assert "cat" in news[0]


def test_cache_reuses_transport() -> None:
    c = _client({"/api/snapshot": _SNAPSHOT})
    transport = c._client  # type: ignore[assignment]
    c.snapshot()
    c.snapshot()
    assert transport.calls.count("/api/snapshot") == 1


def test_failure_returns_none() -> None:
    c = _client({})
    assert c.snapshot() is None
    assert c.margin() is None
    assert c.news() == []
    assert c.calendar("trading") == []


def test_recap_prompt_renders_injected_news(monkeypatch: pytest.MonkeyPatch) -> None:
    """_build_user_prompt 渲染 hhxg 归一化的新闻切片。"""
    from app.services import market_recap

    news = [
        {"title": "焦点A", "snippet": "焦点A详情", "source": "hhxg",
         "published_date": "2026-08-02T07:00:00", "category": "焦点"},
    ]
    overview = {"as_of": "2026-07-31", "indices": [], "breadth": {}, "amount": {},
                "limit": {}, "trend": {}, "activity": {},
                "emotion": {"score": 60, "label": "强"},
                "concept_rank": None, "industry_rank": None}
    prompt = market_recap._build_user_prompt(overview, news, "")
    assert "## 近期市场新闻" in prompt
    assert "焦点A" in prompt


def test_recap_falls_back_without_news() -> None:
    from app.services import market_recap

    overview = {"as_of": "2026-07-31", "indices": [], "breadth": {}, "amount": {},
                "limit": {}, "trend": {}, "activity": {},
                "emotion": {"score": 60, "label": "强"},
                "concept_rank": None, "industry_rank": None}
    prompt = market_recap._build_user_prompt(overview, [], "")
    assert "外部新闻源不可用" in prompt
