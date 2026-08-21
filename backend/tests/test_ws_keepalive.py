"""WS-04 — 应用层 keepalive 心跳。

测试:
  - 连接建立后, keepalive interval 内收到 {type:"ping", seq:N, data:{}}
  - 测试中用 monkeypatch 缩短 interval 避免等 30s
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import auth
from app.ws.connection_manager import ConnectionManager
from app.ws.handler import ws_stream
import app.ws.handler as handler_mod

COOKIE_NAME = "tf_session"
VALID_TOKEN = "valid-token"
VALID_PRINCIPAL = "reviewer_alice"


def test_ping(monkeypatch):
    """连接建立后 keepalive interval 内收到 ping 消息 (缩短 interval 到 0.1s)。"""
    monkeypatch.setattr(handler_mod, "KEEPALIVE_INTERVAL", 0.1)
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

    client = TestClient(app)
    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        # 在 1s 内应收到 ping
        msg = ws.receive_json()
        assert msg["type"] == "ping"
        assert msg["seq"] >= 1
        assert msg["data"] == {}
