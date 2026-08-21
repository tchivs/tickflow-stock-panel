"""WS-02 — ndjson LLM 流迁移测试 (request 消息 + 频道流式推送)。

覆盖 5 处 ndjson 流:
  - financials → analysis:{symbol} 频道 (analysis_meta → analysis_delta → analysis_done)
  - stock_analysis → analysis:{symbol} 频道
  - market_recap → review 频道 (review_meta → review_delta → review_done)
  - rps rotation → review 频道
  - strategy build → analysis:{strategy_id} 频道

dispatcher 在后台 task 中运行: 先发 analysis_meta/review_meta, 然后逐 ndjson chunk
广播为 analysis_delta/review_delta, 最后发 analysis_done/review_done。
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import auth
from app.ws.connection_manager import ConnectionManager
from app.ws.handler import ws_stream

COOKIE_NAME = "tf_session"
VALID_TOKEN = "valid-token"
VALID_PRINCIPAL = "reviewer_alice"


def _setup_app(monkeypatch) -> tuple[FastAPI, ConnectionManager, TestClient]:
    """创建带 WS 端点和 request dispatcher 的测试 app。"""
    monkeypatch.setattr(auth, "is_valid_session", lambda token: token == VALID_TOKEN)
    monkeypatch.setattr(
        auth,
        "resolve_authenticated_reviewer",
        lambda token: VALID_PRINCIPAL,
    )
    import app.ws.handler as _ws_handler
    monkeypatch.setattr(_ws_handler, "KEEPALIVE_INTERVAL", 9999.0)

    app = FastAPI()
    ws_manager = ConnectionManager()
    app.state.ws_manager = ws_manager
    app.websocket("/ws/stream")(ws_stream)

    client = TestClient(app)
    return app, ws_manager, client


def _collect_stream(ws, done_type: str) -> list[dict]:
    """收集 WS 消息直到收到 done 类型。返回 delta 列表。"""
    deltas = []
    while True:
        msg = ws.receive_json()
        if msg["type"] == done_type:
            break
        deltas.append(msg)
    return deltas


def test_financials_request(monkeypatch):
    """客户端发 request 消息触发 financials LLM 流, 通过 analysis:{symbol} 频道推送。"""
    app, ws_manager, client = _setup_app(monkeypatch)

    symbol = "600519.SH"
    channel = f"analysis:{symbol}"

    async def _mock_stream(data_dir, sym, focus):
        yield json.dumps({"type": "meta", "symbol": sym, "summary": "test"})
        yield json.dumps({"type": "delta", "content": "chunk1"})
        yield json.dumps({"type": "delta", "content": "chunk2"})
        yield json.dumps({"type": "done"})

    monkeypatch.setattr(
        "app.services.financial_analyzer.analyze_financials_stream",
        _mock_stream,
    )
    monkeypatch.setattr(
        "app.ws.request_dispatcher._data_dir",
        lambda app_state: "/tmp",
    )

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": [channel]})
        ws.receive_json()  # subscribed

        ws.send_json({
            "type": "request",
            "channel": channel,
            "params": {"source": "financial", "symbol": symbol, "focus": "盈利能力"},
        })

        msg_meta = ws.receive_json()
        assert msg_meta["type"] == "analysis_meta"
        assert msg_meta["data"]["symbol"] == symbol

        deltas = _collect_stream(ws, "analysis_done")
        # 4 个 ndjson chunk: meta + delta×2 + done, 全部广播为 analysis_delta
        assert len(deltas) == 4
        for d in deltas:
            assert d["type"] == "analysis_delta"


def test_stock_analysis_request(monkeypatch):
    """channel:"analysis:{symbol}", params:{source:"stock"} 触发 stock_analysis 流。"""
    app, ws_manager, client = _setup_app(monkeypatch)

    symbol = "000001.SZ"
    channel = f"analysis:{symbol}"

    async def _mock_stream(repo, data_dir, sym, focus):
        yield json.dumps({"type": "meta", "symbol": sym})
        yield json.dumps({"type": "delta", "content": "分析中"})
        yield json.dumps({"type": "done"})

    monkeypatch.setattr(
        "app.api.stock_analysis.analyze_stock_stream",
        _mock_stream,
    )
    monkeypatch.setattr(
        "app.ws.request_dispatcher._data_dir",
        lambda app_state: "/tmp",
    )
    monkeypatch.setattr(
        "app.ws.request_dispatcher._repo",
        lambda app_state: None,
    )

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": [channel]})
        ws.receive_json()  # subscribed

        ws.send_json({
            "type": "request",
            "channel": channel,
            "params": {"source": "stock", "symbol": symbol},
        })

        msg_meta = ws.receive_json()
        assert msg_meta["type"] == "analysis_meta"

        deltas = _collect_stream(ws, "analysis_done")
        # 3 个 ndjson chunk: meta + delta + done
        assert len(deltas) == 3


def test_market_recap_request(monkeypatch):
    """channel:"review", params:{kind:"market_recap"} 触发 market_recap 流。"""
    app, ws_manager, client = _setup_app(monkeypatch)

    channel = "review"

    async def _mock_stream(repo, qs, ds, as_of, focus):
        yield json.dumps({"type": "meta", "as_of": "2026-08-21"})
        yield json.dumps({"type": "delta", "content": "复盘"})
        yield json.dumps({"type": "done"})

    monkeypatch.setattr(
        "app.api.market_recap.recap_market_stream",
        _mock_stream,
    )
    monkeypatch.setattr(
        "app.ws.request_dispatcher._repo",
        lambda app_state: None,
    )

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": [channel]})
        ws.receive_json()  # subscribed

        ws.send_json({
            "type": "request",
            "channel": channel,
            "params": {"kind": "market_recap", "focus": ""},
        })

        msg_meta = ws.receive_json()
        assert msg_meta["type"] == "review_meta", f"got {msg_meta}"

        deltas = _collect_stream(ws, "review_done")
        # 3 个 ndjson chunk
        assert len(deltas) == 3
        for d in deltas:
            assert d["type"] == "review_delta"


def test_rps_request(monkeypatch):
    """channel:"review", params:{kind:"rps"} 触发 rps rotation 流。"""
    app, ws_manager, client = _setup_app(monkeypatch)

    channel = "review"

    async def _mock_stream(repo, days, focus, qs, ds, kind, level):
        yield json.dumps({"type": "meta", "days": days})
        yield json.dumps({"type": "delta", "content": "轮动"})
        yield json.dumps({"type": "done"})

    monkeypatch.setattr(
        "app.api.rps.analyze_rotation_stream",
        _mock_stream,
    )
    monkeypatch.setattr(
        "app.ws.request_dispatcher._repo",
        lambda app_state: None,
    )

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": [channel]})
        ws.receive_json()  # subscribed

        ws.send_json({
            "type": "request",
            "channel": channel,
            "params": {"kind": "rps", "days": 14},
        })

        msg_meta = ws.receive_json()
        assert msg_meta["type"] == "review_meta"

        deltas = _collect_stream(ws, "review_done")
        assert len(deltas) == 3


def test_strategy_build_request(monkeypatch):
    """channel:"analysis:{strategy_id}", params:{strategy_id,step} 触发 strategy build 流。"""
    app, ws_manager, client = _setup_app(monkeypatch)

    strategy_id = "my_strategy_001"
    channel = f"analysis:{strategy_id}"

    class _MockGen:
        async def stream(self, prompt):
            yield "生成中"
        def validate_code(self, code):
            return {"code": "def strategy(): pass", "error": None}
        def needs_structural_repair(self, result):
            return False

    monkeypatch.setattr(
        "app.api.strategy.AIStrategyGenerator",
        lambda: _MockGen(),
    )
    monkeypatch.setattr(
        "app.api.strategy._build_prompt",
        lambda req: "test prompt",
    )

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": [channel]})
        ws.receive_json()  # subscribed

        ws.send_json({
            "type": "request",
            "channel": channel,
            "params": {"strategy_id": strategy_id, "step": 1},
        })

        msg_meta = ws.receive_json()
        assert msg_meta["type"] == "analysis_meta"

        deltas = _collect_stream(ws, "analysis_done")
        # 1 个 delta chunk (生成中)
        assert len(deltas) == 1
        assert deltas[0]["type"] == "analysis_delta"


def test_request_error(monkeypatch):
    """LLM 生成失败时推送 error 消息; 连接不中断。"""
    app, ws_manager, client = _setup_app(monkeypatch)

    symbol = "600519.SH"
    channel = f"analysis:{symbol}"

    async def _mock_stream(data_dir, sym, focus):
        yield json.dumps({"type": "meta", "symbol": sym})
        yield json.dumps({"type": "error", "message": "LLM 超时"})

    monkeypatch.setattr(
        "app.services.financial_analyzer.analyze_financials_stream",
        _mock_stream,
    )
    monkeypatch.setattr(
        "app.ws.request_dispatcher._data_dir",
        lambda app_state: "/tmp",
    )

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": [channel]})
        ws.receive_json()  # subscribed

        ws.send_json({
            "type": "request",
            "channel": channel,
            "params": {"source": "financial", "symbol": symbol},
        })

        msg_meta = ws.receive_json()
        assert msg_meta["type"] == "analysis_meta"

        # 2 个 ndjson chunk: meta + error, 全部广播为 analysis_delta
        deltas = _collect_stream(ws, "analysis_done")
        assert len(deltas) == 2

        # 连接仍然存活 — 可以继续订阅其他频道
        ws.send_json({"type": "subscribe", "channels": ["quotes"]})
        msg = ws.receive_json()
        assert msg["type"] == "subscribed"


def test_request_while_subscribed(monkeypatch):
    """同一连接先订阅 quotes 频道再发 request, 两者并行推送不冲突。"""
    app, ws_manager, client = _setup_app(monkeypatch)

    symbol = "600519.SH"
    analysis_channel = f"analysis:{symbol}"

    async def _mock_stream(data_dir, sym, focus):
        yield json.dumps({"type": "meta", "symbol": sym})
        yield json.dumps({"type": "delta", "content": "chunk"})
        yield json.dumps({"type": "done"})

    monkeypatch.setattr(
        "app.services.financial_analyzer.analyze_financials_stream",
        _mock_stream,
    )
    monkeypatch.setattr(
        "app.ws.request_dispatcher._data_dir",
        lambda app_state: "/tmp",
    )

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": ["quotes", analysis_channel]})
        ws.receive_json()  # subscribed

        ws.send_json({
            "type": "request",
            "channel": analysis_channel,
            "params": {"source": "financial", "symbol": symbol},
        })

        msg_meta = ws.receive_json()
        assert msg_meta["type"] == "analysis_meta"

        deltas = _collect_stream(ws, "analysis_done")
        assert len(deltas) == 3
