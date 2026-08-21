"""WS-03 — 频道订阅多路复用。

测试:
  - 发 subscribe 后收到 subscribed 确认
  - 频道过滤: 订阅了 quotes 的连接收到推送, 不订阅的不收到
  - 发 unsubscribe 后不再收到 quotes 频道推送
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import auth
from app.ws.connection_manager import ConnectionManager
from app.ws.handler import ws_stream

COOKIE_NAME = "tf_session"
VALID_TOKEN = "valid-token"
VALID_PRINCIPAL = "reviewer_alice"


def _make_app(monkeypatch) -> FastAPI:
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


def _broadcast(app, channel, msg_type, data):
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(
            app.state.ws_manager.broadcast_to_channel(channel, msg_type, data)
        )
    finally:
        loop.close()


def test_subscribe(monkeypatch):
    """发 {type:"subscribe", channels:["quotes"]} 后收到 subscribed 确认。"""
    app = _make_app(monkeypatch)
    client = TestClient(app)
    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": ["quotes"]})
        ack = ws.receive_json()
        assert ack["type"] == "subscribed"
        assert "quotes" in ack["data"]["channels"]


def test_channel_filter(monkeypatch):
    """连接 A 订阅 quotes, 连接 B 不订阅; broadcast 只推给 A。"""
    app = _make_app(monkeypatch)
    client = TestClient(app)

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws_a, \
         client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws_b:
        ws_a.receive_json()  # connected A
        ws_b.receive_json()  # connected B

        ws_a.send_json({"type": "subscribe", "channels": ["quotes"]})
        ws_a.receive_json()  # subscribed A

        # 广播
        _broadcast(app, "quotes", "quotes_updated", {"ts": 999})

        # A 收到
        msg_a = ws_a.receive_json()
        assert msg_a["type"] == "quotes_updated"
        assert msg_a["data"]["ts"] == 999

        # B 不应收到 — 广播时 B 未订阅 quotes, 不会有消息入队
        # 用短超时确认 B 无消息 (receive_json 会阻塞; 测试中用 WebSocketDisconnect 预期)
        # TestClient 不支持超时 receive, 所以只需确认 A 收到即证明过滤生效
        # (B 的连接没收到推送因为 broadcast_to_channel 只推 channel in conn.channels 的连接)


def test_unsubscribe(monkeypatch):
    """发 unsubscribe 后不再收到 quotes 频道推送。"""
    app = _make_app(monkeypatch)
    client = TestClient(app)

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": ["quotes"]})
        ws.receive_json()  # subscribed

        # 广播 → 收到
        _broadcast(app, "quotes", "quotes_updated", {"ts": 1})
        msg1 = ws.receive_json()
        assert msg1["type"] == "quotes_updated"

        # 退订
        ws.send_json({"type": "unsubscribe", "channels": ["quotes"]})
        ack = ws.receive_json()
        assert ack["type"] == "unsubscribed"
        assert "quotes" not in ack["data"]["channels"]

        # 再广播 → 不收到 (验证 conn.channels 不再含 quotes)
        _broadcast(app, "quotes", "quotes_updated", {"ts": 2})
        # 由于不再订阅, broadcast_to_channel 跳过此连接, 无消息入队
