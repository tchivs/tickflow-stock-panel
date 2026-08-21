"""WS-01 — WebSocket 端点连接 + Cookie 鉴权 + 多客户端。

测试:
  - 有效 tf_session Cookie 连接收到 {type:"connected", seq:0} 欢迎消息
  - 无 Cookie / 无效 session 的连接被 close(code=4001)
  - 两个 TestClient 同时连接, 各自独立 seq
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ws.connection_manager import ConnectionManager
from app.ws.handler import ws_stream
from app.ws.protocol import make_msg

COOKIE_NAME = "tf_session"
VALID_TOKEN = "valid-token"
VALID_PRINCIPAL = "reviewer_alice"


def _make_app(monkeypatch) -> FastAPI:
    """最小 FastAPI 应用: 注册 /ws/stream, mock Cookie 鉴权。"""
    from app.services import auth

    monkeypatch.setattr(auth, "is_valid_session", lambda token: token == VALID_TOKEN)
    monkeypatch.setattr(
        auth,
        "resolve_authenticated_reviewer",
        lambda token: VALID_PRINCIPAL if token == VALID_TOKEN else None,
    )

    app = FastAPI()
    ws_manager = ConnectionManager()
    app.state.ws_manager = ws_manager
    app.websocket("/ws/stream")(ws_stream)
    return app


def test_ws_auth(monkeypatch):
    """有效 Cookie 连接收到 {type:"connected", seq:0} 欢迎消息。"""
    app = _make_app(monkeypatch)
    client = TestClient(app)
    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        msg = ws.receive_json()
        assert msg["type"] == "connected"
        assert msg["seq"] == 0
        assert "principal" in msg["data"]


def test_ws_reject_no_cookie(monkeypatch):
    """无 Cookie 的连接被 close(code=4001)。"""
    app = _make_app(monkeypatch)
    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/stream") as ws:
            ws.receive_json()


def test_ws_reject_invalid_session(monkeypatch):
    """无效 session 的连接被 close(code=4001)。"""
    app = _make_app(monkeypatch)
    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect(
            "/ws/stream", cookies={COOKIE_NAME: "bogus-token"}
        ) as ws:
            ws.receive_json()


def test_multi_client(monkeypatch):
    """两个 TestClient 同时连接, 各自独立收到推送 (seq 独立递增)。"""
    app = _make_app(monkeypatch)
    client = TestClient(app)

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws_a, \
         client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws_b:
        # 各自收到 connected 消息
        msg_a = ws_a.receive_json()
        msg_b = ws_b.receive_json()
        assert msg_a["type"] == "connected"
        assert msg_b["type"] == "connected"

        # A 订阅 quotes
        ws_a.send_json({"type": "subscribe", "channels": ["quotes"]})
        ack_a = ws_a.receive_json()
        assert ack_a["type"] == "subscribed"

        # B 也订阅 quotes
        ws_b.send_json({"type": "subscribe", "channels": ["quotes"]})
        ack_b = ws_b.receive_json()
        assert ack_b["type"] == "subscribed"

        # 广播一条消息
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                app.state.ws_manager.broadcast_to_channel(
                    "quotes", "quotes_updated", {"ts": 12345, "symbol_count": 10}
                )
            )
        finally:
            loop.close()

        # 各自独立收到, seq 各自从 1 开始
        recv_a = ws_a.receive_json()
        recv_b = ws_b.receive_json()
        assert recv_a["type"] == "quotes_updated"
        assert recv_b["type"] == "quotes_updated"
        assert recv_a["seq"] == 1
        assert recv_b["seq"] == 1
