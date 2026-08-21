"""验证 QuoteService 后台线程 → WS 广播的真实链路。

关键场景: QuoteService._broadcast_quote_updated 由后台轮询线程调用,
_ws_broadcast 通过 bootstrap 捕获的主事件循环 (ws_manager.get_main_loop())
run_coroutine_threadsafe 投递广播。此测试模拟:
  1. bootstrap 设置主循环到 ws_manager
  2. 后台线程调用 QuoteService 方法
  3. WS 客户端收到消息

这验证 Plan 01 遗留 bug 的修复: get_event_loop() 在后台线程抛
RuntimeError, 广播静默失效 → 改为 ws_manager.get_main_loop()。
"""
from __future__ import annotations

import asyncio
import threading
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


def test_quote_service_background_thread_broadcast(monkeypatch):
    """后台线程调用 QuoteService 方法 → WS 客户端收到广播。"""
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

    qs = QuoteService()
    qs.attach_ws_manager(ws_manager)
    qs._symbol_count = 42

    client = TestClient(app)
    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": ["quotes"]})
        ws.receive_json()  # subscribed

        # 模拟 bootstrap: 在一个运行中的事件循环里设置主循环
        main_loop = asyncio.new_event_loop()
        ws_manager.set_main_loop(main_loop)
        main_thread = threading.Thread(target=main_loop.run_forever, daemon=True)
        main_thread.start()
        try:
            # 后台线程调用 QuoteService 方法 (无 get_event_loop, 但 ws_manager 有主循环)
            bg_error: list[Exception] = []

            def _bg():
                try:
                    qs._broadcast_quote_updated()
                except Exception as e:  # noqa: BLE001
                    bg_error.append(e)

            bg = threading.Thread(target=_bg, daemon=True)
            bg.start()
            bg.join(timeout=2.0)

            assert not bg_error, f"后台线程异常: {bg_error}"

            # 等待广播投递
            msg = ws.receive_json()
            assert msg["type"] == "quotes_updated"
            assert msg["data"]["symbol_count"] == 42
        finally:
            main_loop.call_soon_threadsafe(main_loop.stop)
            main_thread.join(timeout=2.0)
            main_loop.close()
