"""WS-01 — 连接生命周期审计 (ToolCallEnvelope scope=ws)。

测试:
  - 连接建立 + 断连后, ToolCallAuditRepository 有一条 scope="ws" tool="connection" 的记录
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import auth
from app.ws.connection_manager import ConnectionManager
from app.ws.handler import ws_stream
from app.audit.service import set_audit_repo, get_audit_repo
from app.audit.envelope import ToolCallAuditRepository, AuditContext

COOKIE_NAME = "tf_session"
VALID_TOKEN = "valid-token"
VALID_PRINCIPAL = "reviewer_alice"


class _FakeRepo(ToolCallAuditRepository):
    """内存版审计 repo, 仅记录 append 调用。"""

    def __init__(self):
        self._records: list[dict] = []
        self._seq = 0

    def append(self, **kwargs):
        self._seq += 1
        rec = {"seq": self._seq, **kwargs}
        self._records.append(rec)
        return rec

    def list_records(self):
        return list(self._records)


def test_audit_on_connect(monkeypatch):
    """连接建立 + 断连后, 审计 repo 有一条 scope="ws" tool="connection" 的记录。"""
    monkeypatch.setattr(auth, "is_valid_session", lambda token: token == VALID_TOKEN)
    monkeypatch.setattr(
        auth,
        "resolve_authenticated_reviewer",
        lambda token: VALID_PRINCIPAL if token == VALID_TOKEN else None,
    )

    fake_repo = _FakeRepo()
    # 临时替换全局 audit repo
    original = get_audit_repo()
    set_audit_repo(fake_repo)
    try:
        app = FastAPI()
        ws_manager = ConnectionManager()
        app.state.ws_manager = ws_manager
        app.websocket("/ws/stream")(ws_stream)

        client = TestClient(app)
        with client.websocket_connect(
            "/ws/stream", cookies={COOKIE_NAME: VALID_TOKEN}
        ) as ws:
            ws.receive_json()  # connected
            # 断连
        # WebSocketDisconnect 后 handler 的 AuditContext.__exit__ 记录

        ws_records = [r for r in fake_repo.list_records() if r.get("scope") == "ws"]
        assert len(ws_records) >= 1
        rec = ws_records[0]
        assert rec["tool"] == "connection"
        assert rec.get("principal") == VALID_PRINCIPAL
    finally:
        set_audit_repo(original)
