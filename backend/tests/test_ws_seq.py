"""WS-02 骨架 — seq 环形缓冲区 + resume 重放 + 溢出淘汰。

测试:
  - 连接收 3 条消息 (seq 1,2,3), 断连后重连发 resume last_seq=1, 收到 seq 2,3 重放 + resumed replayed:2
  - 推入 1001 条消息后, replay_after(0) 只返回最近 1000 条 (deque maxlen=1000)
"""
from __future__ import annotations

from collections import deque

from app.ws.connection_manager import WsConnection
from app.ws.protocol import make_msg, RING_SIZE


def test_ring_buffer_replay():
    """WsConnection.replay_after: seq > last_seq 的消息按序重放。"""
    conn = WsConnection.__new__(WsConnection)
    conn.seq = 0
    conn._ring = deque(maxlen=RING_SIZE)
    # 模拟 3 条消息
    for i in range(1, 4):
        seq = conn.next_seq()
        msg = make_msg("quotes_updated", seq, {"ts": i * 1000})
        conn.push_to_ring(msg)

    replay = conn.replay_after(1)
    assert len(replay) == 2
    assert [m["seq"] for m in replay] == [2, 3]


def test_ring_overflow():
    """推入 1001 条消息后, replay_after(0) 只返回最近 1000 条。"""
    conn = WsConnection.__new__(WsConnection)
    conn.seq = 0
    conn._ring = deque(maxlen=RING_SIZE)
    for i in range(1, RING_SIZE + 2):
        seq = conn.next_seq()
        conn.push_to_ring(make_msg("ping", seq, {}))

    replay = conn.replay_after(0)
    assert len(replay) == RING_SIZE
    # 最旧的 (seq=1) 已被淘汰, 最新的 seq=1001 仍在
    assert replay[0]["seq"] == 2  # seq 1 被淘汰
    assert replay[-1]["seq"] == RING_SIZE + 1


def test_resume_replay_via_ws(monkeypatch):
    """端到端: 断连后重连发 resume, 收到重放消息。"""
    import pytest
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.services import auth
    from app.ws.connection_manager import ConnectionManager
    from app.ws.handler import ws_stream

    COOKIE_NAME = "tf_session"
    VALID_TOKEN = "valid-token"
    VALID_PRINCIPAL = "reviewer_alice"

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

    # 第一次连接: 订阅 quotes, 收 2 条推送, 断连
    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws:
        ws.receive_json()  # connected
        ws.send_json({"type": "subscribe", "channels": ["quotes"]})
        ws.receive_json()  # subscribed

        import asyncio

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                ws_manager.broadcast_to_channel("quotes", "quotes_updated", {"ts": 1})
            )
            loop.run_until_complete(
                ws_manager.broadcast_to_channel("quotes", "quotes_updated", {"ts": 2})
            )
        finally:
            loop.close()

        msg1 = ws.receive_json()
        msg2 = ws.receive_json()
        assert msg1["seq"] == 1
        assert msg2["seq"] == 2
        last_seq = msg2["seq"]
    # 连接关闭 — WsConnection 留在 _connections 中

    # 第二次连接: 发 resume last_seq=1, 应收到 seq 2 重放 + resumed replayed:1
    with client.websocket_connect("/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}) as ws2:
        ws2.receive_json()  # connected
        ws2.send_json({"type": "subscribe", "channels": ["quotes"]})
        ws2.receive_json()  # subscribed
        ws2.send_json({"type": "resume", "last_seq": 1})
        # 收到重放 + resumed
        replayed = []
        # 读取消息直到 resumed
        for _ in range(10):
            msg = ws2.receive_json()
            if msg["type"] == "resumed":
                assert msg["data"]["replayed"] >= 1
                break
            replayed.append(msg)
        assert any(m["seq"] == 2 for m in replayed)
