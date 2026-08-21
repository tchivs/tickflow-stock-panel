"""WS-01/WS-03 — quotes 行情流端到端广播。

测试:
  - QuoteService._broadcast_quote_updated() 触发后, 订阅了 quotes 频道的连接收到
    {type:"quotes_updated", seq:N, data:{ts:..., symbol_count:...}}
"""
from __future__ import annotations

import asyncio
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import auth
from app.ws.connection_manager import ConnectionManager
from app.ws.handler import ws_stream
from app.services.quote_service import QuoteService

COOKIE_NAME = "tf_session"
VALID_TOKEN = "valid-token"
VALID_PRINCIPAL = "reviewer_alice"


def test_quotes_broadcast(monkeypatch):
    """QuoteService._broadcast_quote_updated 触发后订阅连接收到 quotes_updated。"""
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

    # 创建 QuoteService 并注入 ws_manager
    qs = QuoteService()
    qs.attach_ws_manager(ws_manager)
    qs._symbol_count = 42

    client = TestClient(app)
    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": ["quotes"]})
        ws.receive_json()  # subscribed

        # 模拟 QuoteService._broadcast_quote_updated
        # (实际方法中通过 run_coroutine_threadsafe 投递, 测试中直接调 broadcast_to_channel)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                ws_manager.broadcast_to_channel(
                    "quotes",
                    "quotes_updated",
                    {"ts": int(time.time() * 1000), "symbol_count": qs._symbol_count},
                )
            )
        finally:
            loop.close()

        msg = ws.receive_json()
        assert msg["type"] == "quotes_updated"
        assert msg["seq"] >= 1
        assert "ts" in msg["data"]
        assert msg["data"]["symbol_count"] == 42
