"""CORE-05 contract tests for portfolio updates over WS broadcast (Phase 55).

Portfolio refreshes are pushed through the WS ``portfolio`` channel via
``QuoteService.notify_portfolio_updated`` — the SSE subscriber mode was removed
in Phase 55 D-03. These tests verify the WS fan-out contract: each connected
client receives its own coalesced portfolio update, and account IDs are
preserved.
"""
from __future__ import annotations

from tests.test_ws_quotes import (
    COOKIE_NAME,
    VALID_TOKEN,
    _call_service,
    _setup_app,
)


def test_portfolio_ws_broadcast(monkeypatch):
    """notify_portfolio_updated 触发后, 订阅 portfolio 频道的连接收到 portfolio_updated。"""
    _app, ws_manager, qs, client = _setup_app(monkeypatch)

    with client.websocket_connect(
        "/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}
    ) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": ["portfolio"]})
        ws.receive_json()  # subscribed

        _call_service(qs, "notify_portfolio_updated", ["account_cash", "account_margin"])

        msg = ws.receive_json()
        assert msg["type"] == "portfolio_updated"
        assert msg["data"]["account_ids"] == ["account_cash", "account_margin"]


def test_portfolio_account_ids_preserved_across_calls(monkeypatch):
    """连续两次 notify_portfolio_updated 各自独立广播, 账户 ID 不丢失。"""
    _app, ws_manager, qs, client = _setup_app(monkeypatch)

    with client.websocket_connect(
        "/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}
    ) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": ["portfolio"]})
        ws.receive_json()  # subscribed

        _call_service(qs, "notify_portfolio_updated", ["account_cash"])
        _call_service(qs, "notify_portfolio_updated", ["account_margin", "account_cash"])

        first = ws.receive_json()
        second = ws.receive_json()
        assert first["data"]["account_ids"] == ["account_cash"]
        assert second["data"]["account_ids"] == ["account_margin", "account_cash"]


def test_portfolio_is_only_portfolio_stream_route(monkeypatch):
    """Portfolio refreshes go through the WS channel — no portfolio SSE route remains."""
    from app.api.intraday import router

    routes = {route.path for route in router.routes}
    assert not any("portfolio" in path and "stream" in path for path in routes)
