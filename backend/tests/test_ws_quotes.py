"""WS-02 — QuoteService 全事件 WS 频道广播测试。

覆盖 8 类行情事件 (真实调用 QuoteService 方法, 验证 _ws_broadcast 投递):
  - quotes_updated → quotes 频道 (test_ws_endpoint 已覆盖, 此处不重复)
  - strategy_alert → alerts 频道 (_broadcast_alerts)
  - portfolio_updated → portfolio 频道 (notify_portfolio_updated)
  - review_progress → review 频道 (push_review_event)
  - depth_updated → depth 频道 (notify_depth_updated)
  - analysis_progress → analysis:{symbol} 频道 (notify_analysis_progress)
  - advanced_progress → analysis:{symbol} 频道 (notify_advanced_progress)
  - strategy_results_updated → quotes 频道 (notify_strategy_results_updated)

QuoteService 运行在后台线程, _ws_broadcast 通过 run_coroutine_threadsafe
投递到事件循环。测试用后台 run_forever 事件循环线程驱动真实方法,
验证从 QuoteService 方法 → broadcast_to_channel → 订阅连接收到消息的完整链路。
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


def _setup_app(monkeypatch) -> tuple[FastAPI, ConnectionManager, QuoteService, TestClient]:
    """创建带 WS 端点的测试 app + 注入 ws_manager 的 QuoteService。"""
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
    return app, ws_manager, qs, client


class _BackgroundLoop:
    """运行中的后台事件循环, 供 QuoteService._ws_broadcast 的 run_coroutine_threadsafe 投递。

    QuoteService 在测试主线程中同步调用, 其 _ws_broadcast 取 asyncio.get_event_loop()
    并 run_coroutine_threadsafe 投递 — 需要一个正在 run_forever 的 loop。
    """

    def __enter__(self) -> "_BackgroundLoop":
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=2.0)
        self.loop.close()
        asyncio.set_event_loop(None)


def _call_service(qs: QuoteService, method: str, *args, **kwargs) -> None:
    """在后台事件循环环境下调用 QuoteService 方法, 使其 WS 广播真正投递。"""
    with _BackgroundLoop():
        getattr(qs, method)(*args, **kwargs)
        # 给后台 loop 一点时间完成 broadcast_to_channel + send_json
        time.sleep(0.05)


def test_alerts_broadcast(monkeypatch):
    """QuoteService._broadcast_alerts 触发后, 订阅 alerts 频道的连接收到 strategy_alert。"""
    app, ws_manager, qs, client = _setup_app(monkeypatch)

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": ["alerts"]})
        ws.receive_json()  # subscribed

        alerts = [{"symbol": "600519.SH", "pct_chg": 5.2, "level": "info"}]
        _call_service(qs, "_broadcast_alerts", alerts)

        msg = ws.receive_json()
        assert msg["type"] == "strategy_alert"
        assert msg["seq"] >= 1
        assert msg["data"]["alerts"] == alerts


def test_portfolio_broadcast(monkeypatch):
    """QuoteService.notify_portfolio_updated 触发后, 订阅 portfolio 频道的连接收到 portfolio_updated。"""
    app, ws_manager, qs, client = _setup_app(monkeypatch)

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": ["portfolio"]})
        ws.receive_json()  # subscribed

        _call_service(qs, "notify_portfolio_updated", ["acc1"])

        msg = ws.receive_json()
        assert msg["type"] == "portfolio_updated"
        assert msg["seq"] >= 1
        assert msg["data"]["account_ids"] == ["acc1"]


def test_review_broadcast(monkeypatch):
    """QuoteService.push_review_event 触发后, 订阅 review 频道的连接收到 review_progress。"""
    app, ws_manager, qs, client = _setup_app(monkeypatch)

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": ["review"]})
        ws.receive_json()  # subscribed

        review_data = {"stage": "analysis", "progress": 50}
        _call_service(qs, "push_review_event", '{"stage": "analysis", "progress": 50}')

        msg = ws.receive_json()
        assert msg["type"] == "review_progress"
        assert msg["seq"] >= 1
        assert msg["data"] == review_data


def test_depth_broadcast(monkeypatch):
    """QuoteService.notify_depth_updated 触发后, 订阅 depth 频道的连接收到 depth_updated。"""
    app, ws_manager, qs, client = _setup_app(monkeypatch)

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": ["depth"]})
        ws.receive_json()  # subscribed

        _call_service(qs, "notify_depth_updated")

        msg = ws.receive_json()
        assert msg["type"] == "depth_updated"
        assert msg["seq"] >= 1
        assert "ts" in msg["data"]


def test_analysis_progress(monkeypatch):
    """notify_analysis_progress 触发后, 订阅 analysis:{symbol} 频道的连接收到 analysis_progress。"""
    app, ws_manager, qs, client = _setup_app(monkeypatch)

    symbol = "600519.SH"
    channel = f"analysis:{symbol}"

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": [channel]})
        ws.receive_json()  # subscribed

        _call_service(
            qs,
            "notify_analysis_progress",
            run_id="run-123",
            subject_kind="stock",
            subject_key=symbol,
            status="running",
        )

        msg = ws.receive_json()
        assert msg["type"] == "analysis_progress"
        assert msg["seq"] >= 1
        assert msg["data"]["run_id"] == "run-123"
        assert msg["data"]["subject_key"] == symbol


def test_advanced_progress(monkeypatch):
    """notify_advanced_progress 触发后, 订阅 analysis:{symbol} 频道的连接收到 advanced_progress。"""
    app, ws_manager, qs, client = _setup_app(monkeypatch)

    symbol = "600519.SH"
    channel = f"analysis:{symbol}"

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": [channel]})
        ws.receive_json()  # subscribed

        _call_service(
            qs,
            "notify_advanced_progress",
            job_id="job-1",
            subject_kind="stock",
            subject_key=symbol,
            stage="drafted",
            occurred_at="2026-08-21T10:00:00",
            committed=True,
            human_label="初稿完成",
            audit_reference=None,
        )

        msg = ws.receive_json()
        assert msg["type"] == "advanced_progress"
        assert msg["seq"] >= 1
        assert msg["data"]["job_id"] == "job-1"
        assert msg["data"]["subject_key"] == symbol


def test_strategy_results_broadcast(monkeypatch):
    """notify_strategy_results_updated 触发后, 订阅 quotes 频道的连接收到 strategy_results_updated。"""
    app, ws_manager, qs, client = _setup_app(monkeypatch)

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": ["quotes"]})
        ws.receive_json()  # subscribed

        _call_service(qs, "notify_strategy_results_updated")

        msg = ws.receive_json()
        assert msg["type"] == "strategy_results_updated"
        assert msg["seq"] >= 1
        assert "ts" in msg["data"]


def test_multi_channel_one_connection(monkeypatch):
    """一个连接同时订阅 quotes+alerts+portfolio, 各类事件均推送到同一连接 (WS-03 多路复用)。"""
    app, ws_manager, qs, client = _setup_app(monkeypatch)

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": ["quotes", "alerts", "portfolio"]})
        ws.receive_json()  # subscribed

        with _BackgroundLoop():
            # 依次触发三类事件 (走真实 QuoteService 方法)
            qs.notify_strategy_results_updated()
            qs._broadcast_alerts([])
            qs.notify_portfolio_updated(["a1"])
            time.sleep(0.1)

            # 注意: 三个 broadcast 都投递到同一后台 loop, 顺序可能交错;
            # 各自独立校验类型与关键字段, 不做严格顺序断言
            types = set()
            for _ in range(3):
                msg = ws.receive_json()
                types.add(msg["type"])

            assert {"strategy_results_updated", "strategy_alert", "portfolio_updated"} <= types


def test_channel_filtering(monkeypatch):
    """未订阅的频道事件不会推送到该连接 (T-55-05)。"""
    app, ws_manager, qs, client = _setup_app(monkeypatch)

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": ["quotes"]})
        ws.receive_json()  # subscribed

        # 推送 alerts 频道事件 — 连接未订阅, 不应收到
        _call_service(qs, "_broadcast_alerts", [{"symbol": "600519.SH", "level": "info"}])
        # 推送 quotes 频道事件 — 连接已订阅, 应收到
        _call_service(qs, "notify_strategy_results_updated")

        msg = ws.receive_json()
        assert msg["type"] == "strategy_results_updated"
