"""WS-02 — 任务流 SSE → WS run: 频道迁移测试。

覆盖 6 处任务流:
  - backtest strategy/optimize/walkforward → run:{job_key} 频道
  - mining → run:{run_id} 频道 (SQLite ledger 回退)
  - alpha → run:{run_id} 频道 (seq 去重)
  - walkforward plan → run:{plan_id} 频道
  - forecast → run:{job_id} 频道 (transition_version seq)
  - 频道所有权验证 (T-55-02): 跨 principal 订阅被拒绝

测试通过直接调用 broadcast_to_channel 模拟任务流广播, 验证订阅连接收到事件。
handler 的频道所有权验证通过 TestClient WS 订阅测试。
"""
from __future__ import annotations

import asyncio
import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import auth
from app.ws.connection_manager import ConnectionManager
from app.ws.handler import ws_stream

COOKIE_NAME = "tf_session"
VALID_TOKEN = "valid-token"
PRINCIPAL_A = "reviewer_alice"
PRINCIPAL_B = "reviewer_bob"


def _setup_app(monkeypatch, principal=PRINCIPAL_A) -> tuple[FastAPI, ConnectionManager, TestClient]:
    """创建带 WS 端点的测试 app。"""
    monkeypatch.setattr(auth, "is_valid_session", lambda token: token == VALID_TOKEN)
    monkeypatch.setattr(
        auth,
        "resolve_authenticated_reviewer",
        lambda token: principal,
    )
    import app.ws.handler as _ws_handler
    monkeypatch.setattr(_ws_handler, "KEEPALIVE_INTERVAL", 9999.0)

    app = FastAPI()
    ws_manager = ConnectionManager()
    app.state.ws_manager = ws_manager
    app.websocket("/ws/stream")(ws_stream)
    client = TestClient(app)
    return app, ws_manager, client


def _broadcast(ws_manager: ConnectionManager, channel: str, msg_type: str, data: dict) -> None:
    """在事件循环中同步执行 broadcast_to_channel。"""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(ws_manager.broadcast_to_channel(channel, msg_type, data))
    finally:
        loop.close()


def test_backtest_progress(monkeypatch):
    """订阅 run:{job_key} 频道后收到 job_progress + job_done。"""
    app, ws_manager, client = _setup_app(monkeypatch)

    job_key = "abc123def456"
    channel = f"run:{job_key}"

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": [channel]})
        ws.receive_json()  # subscribed

        _broadcast(ws_manager, channel, "job_progress", {"day": 10, "total": 100, "equity": 1050000})
        _broadcast(ws_manager, channel, "job_done", {"result": "ok", "sharpe": 1.5})

        msg1 = ws.receive_json()
        assert msg1["type"] == "job_progress"
        assert msg1["seq"] >= 1
        assert msg1["data"]["day"] == 10

        msg2 = ws.receive_json()
        assert msg2["type"] == "job_done"
        assert msg2["seq"] > msg1["seq"]
        assert msg2["data"]["sharpe"] == 1.5


def test_backtest_job_key_first_event(monkeypatch):
    """backtest 启动后首条 WS 消息为 {type:job, data:{key:job_key}} (等价 SSE event:job)。"""
    app, ws_manager, client = _setup_app(monkeypatch)

    job_key = "opt_abc123def"
    channel = f"run:{job_key}"

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": [channel]})
        ws.receive_json()  # subscribed

        _broadcast(ws_manager, channel, "job", {"key": job_key})

        msg = ws.receive_json()
        assert msg["type"] == "job"
        assert msg["data"]["key"] == job_key


def test_optimize_progress(monkeypatch):
    """订阅 run:{opt_job_key} 频道后收到 optimize 进度事件。"""
    app, ws_manager, client = _setup_app(monkeypatch)

    opt_key = "opt_key_abc12"
    channel = f"run:{opt_key}"

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": [channel]})
        ws.receive_json()  # subscribed

        _broadcast(ws_manager, channel, "job_progress", {"done": 5, "total": 20, "best_score": 1.2})

        msg = ws.receive_json()
        assert msg["type"] == "job_progress"
        assert msg["data"]["done"] == 5


def test_walkforward_progress(monkeypatch):
    """订阅 run:{wf_job_key} 频道后收到 walkforward 进度事件。"""
    app, ws_manager, client = _setup_app(monkeypatch)

    wf_key = "wf_key_abc123"
    channel = f"run:{wf_key}"

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": [channel]})
        ws.receive_json()  # subscribed

        _broadcast(ws_manager, channel, "job_progress", {"type": "walkforward_progress", "done": 2, "total": 5})

        msg = ws.receive_json()
        assert msg["type"] == "job_progress"
        assert msg["data"]["total"] == 5


def test_mining_events(monkeypatch):
    """订阅 run:{mining_run_id} 频道后收到 mining progress/terminal 事件。"""
    app, ws_manager, client = _setup_app(monkeypatch)

    run_id = "mining_run_001"
    channel = f"run:{run_id}"

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": [channel]})
        ws.receive_json()  # subscribed

        _broadcast(ws_manager, channel, "progress", {"stage": "scanning", "done": 30, "total": 100})
        _broadcast(ws_manager, channel, "succeeded", {"status": "succeeded", "run_id": run_id})

        msg1 = ws.receive_json()
        assert msg1["type"] == "progress"
        assert msg1["data"]["stage"] == "scanning"

        msg2 = ws.receive_json()
        assert msg2["type"] == "succeeded"
        assert msg2["data"]["status"] == "succeeded"


def test_alpha_events(monkeypatch):
    """订阅 run:{alpha_run_id} 频道后收到 alpha progress/terminal 事件。"""
    app, ws_manager, client = _setup_app(monkeypatch)

    run_id = "alpha_run_042"
    channel = f"run:{run_id}"

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": [channel]})
        ws.receive_json()  # subscribed

        _broadcast(ws_manager, channel, "alpha_progress", {"seq": 1, "stage": "drafting"})
        _broadcast(ws_manager, channel, "alpha_terminal", {"status": "completed", "run_id": run_id})

        msg1 = ws.receive_json()
        assert msg1["type"] == "alpha_progress"
        assert msg1["data"]["stage"] == "drafting"

        msg2 = ws.receive_json()
        assert msg2["type"] == "alpha_terminal"
        assert msg2["data"]["status"] == "completed"


def test_wf_plan_stream(monkeypatch):
    """订阅 run:{plan_id} 频道后收到 walkforward plan progress/done 事件。"""
    app, ws_manager, client = _setup_app(monkeypatch)

    plan_id = "wf_plan_001"
    channel = f"run:{plan_id}"

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": [channel]})
        ws.receive_json()  # subscribed

        _broadcast(ws_manager, channel, "wf_progress", {"fold_index": 0, "total_folds": 5, "is_oos": False})
        _broadcast(ws_manager, channel, "wf_done", {"plan_id": plan_id, "folds": 5})

        msg1 = ws.receive_json()
        assert msg1["type"] == "wf_progress"
        assert msg1["data"]["fold_index"] == 0

        msg2 = ws.receive_json()
        assert msg2["type"] == "wf_done"
        assert msg2["data"]["folds"] == 5


def test_forecast_events(monkeypatch):
    """订阅 run:{forecast_job_id} 频道后收到 forecast 事件; transition_version 保留。"""
    app, ws_manager, client = _setup_app(monkeypatch)

    job_id = "forecast_job_001"
    channel = f"run:{job_id}"

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": [channel]})
        ws.receive_json()  # subscribed

        _broadcast(ws_manager, channel, "forecast_event", {
            "transition_version": 3,
            "status": "running",
            "progress": 0.5,
        })

        msg = ws.receive_json()
        assert msg["type"] == "forecast_event"
        assert msg["data"]["transition_version"] == 3
        assert msg["data"]["progress"] == 0.5


def test_channel_ownership(monkeypatch):
    """T-55-02: principal A 无法订阅 principal B 的 run:{job_key} 频道。

    handler subscribe 分支验证频道所有权: run: 频道需要 conn.principal 对
    run_id 的所有权。本测试通过注入 _running_jobs 模拟所有权。
    """
    import app.api.backtest as bt_mod

    # 模拟 principal B 拥有的 job
    job_key_b = "bob_job_key_01"
    job_b = bt_mod._BacktestJob(job_key_b, principal=PRINCIPAL_B)
    bt_mod._running_jobs[job_key_b] = job_b

    try:
        app, ws_manager, client = _setup_app(monkeypatch, principal=PRINCIPAL_A)

        channel_b = f"run:{job_key_b}"
        with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
            ws.receive_json()  # connected
            # principal A 尝试订阅 principal B 的 run 频道 — 应被拒绝
            ws.send_json({"type": "subscribe", "channels": [channel_b]})
            msg = ws.receive_json()
            # 应收到 error 消息 (频道无权订阅)
            assert msg["type"] == "error"
            assert "无权" in msg["data"]["reason"] or "ownership" in msg["data"]["reason"].lower()
    finally:
        bt_mod._running_jobs.pop(job_key_b, None)


def test_channel_ownership_own_job(monkeypatch):
    """T-55-02: principal 可以订阅自己拥有的 run:{job_key} 频道。"""
    import app.api.backtest as bt_mod

    job_key = "alice_job_key_01"
    job = bt_mod._BacktestJob(job_key, principal=PRINCIPAL_A)
    bt_mod._running_jobs[job_key] = job

    try:
        app, ws_manager, client = _setup_app(monkeypatch, principal=PRINCIPAL_A)

        channel = f"run:{job_key}"
        with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
            ws.receive_json()  # connected
            ws.send_json({"type": "subscribe", "channels": [channel]})
            msg = ws.receive_json()
            # 应成功订阅
            assert msg["type"] == "subscribed"
            assert channel in msg["data"]["channels"]
    finally:
        bt_mod._running_jobs.pop(job_key, None)


def test_static_channels_no_ownership(monkeypatch):
    """静态频道 (quotes/alerts/portfolio/review/depth) 无所有权限制。"""
    app, ws_manager, client = _setup_app(monkeypatch)

    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": ["quotes", "alerts", "portfolio", "review", "depth"]})
        msg = ws.receive_json()
        assert msg["type"] == "subscribed"
        assert set(msg["data"]["channels"]) == {"quotes", "alerts", "portfolio", "review", "depth"}
