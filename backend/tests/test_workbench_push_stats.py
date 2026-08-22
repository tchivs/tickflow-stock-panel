"""PA-03: workbench push_stats 统计子项测试。

测试 GET /api/workbench 返回的 push_stats 子项:
  - 空数据库时返回全零统计 (不报错)
  - 插入审计记录后 today 统计正确 (total/sent/failed)
  - 插入 notification_deliveries skipped 记录后 dedup_skipped 正确
  - recent_failures 返回最近 10 条失败记录
"""
from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.workbench import router as workbench_router
from app.operational.repository import OperationalRepository


def _make_app(tmp_path: Path) -> tuple[FastAPI, OperationalRepository]:
    """Create a minimal FastAPI app with migrated operational repo."""
    repo = OperationalRepository(tmp_path / "operational.db")
    repo.migrate()
    app = FastAPI()
    app.include_router(workbench_router)
    app.state.operational = repo
    return app, repo


def _insert_audit_envelope(
    conn: sqlite3.Connection, *, tool: str, error: str | None = None,
) -> None:
    """Insert a tool_call_envelope row directly (bypassing repo for test control)."""
    eid = secrets.token_hex(12)
    row = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM tool_call_envelopes").fetchone()
    seq = int(row[0]) if row else 1
    conn.execute(
        """
        INSERT INTO tool_call_envelopes
            (id, seq, tool, category, params_hash, params_summary, version, scope,
             principal, response_shape, response_summary, raw_hash, duration_ms,
             error, cached, degraded, schema_valid, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            eid, seq, tool, "notification", "0" * 64,
            json.dumps({}), None, "push:test", None, None,
            "sent" if error is None else "failed",
            None, 10.0, error, 0, 0, 1,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


def _insert_notification_delivery(
    repo: OperationalRepository, *, status: str, error: str | None = None, idx: int = 0,
) -> None:
    """Insert a notification_deliveries row via the repository API."""
    event_id = f"evt_{status}_{error or 'none'}_{idx}"
    repo.record_alert_event({
        "id": event_id,
        "rule_id": "rule_01",
        "symbol": "600519.SH",
        "position_id": "pos_01",
        "account_id": "acc_01",
        "severity": "warn",
        "occurred_at": "2026-08-22T01:30:00+00:00",
        "conditions": [],
    })
    repo.create_delivery_outcome(
        event_id=event_id, channel="sct", status=status, error=error,
    )


def test_push_stats_empty_db_returns_zeros(tmp_path):
    """空数据库时返回全零统计 (不报错)。"""
    app, _repo = _make_app(tmp_path)
    client = TestClient(app)
    resp = client.get("/api/workbench")
    assert resp.status_code == 200
    ps = resp.json()["push_stats"]
    assert ps["today"] == {"total": 0, "sent": 0, "failed": 0, "dedup_skipped": 0}
    assert ps["by_tool"] == {}
    assert ps["recent_failures"] == []


def test_push_stats_counts_today(tmp_path):
    """插入 sct/wecom 审计记录后, today 统计正确 (total/sent/failed)。"""
    app, repo = _make_app(tmp_path)
    with repo._connection() as conn:
        _insert_audit_envelope(conn, tool="sct", error=None)        # sent
        _insert_audit_envelope(conn, tool="wecom", error=None)      # sent
        _insert_audit_envelope(conn, tool="sct", error="delivery failed")  # failed
    client = TestClient(app)
    resp = client.get("/api/workbench")
    assert resp.status_code == 200
    ps = resp.json()["push_stats"]
    assert ps["today"]["total"] == 3
    assert ps["today"]["sent"] == 2
    assert ps["today"]["failed"] == 1
    assert "sct" in ps["by_tool"]
    assert ps["by_tool"]["sct"] == {"total": 2, "sent": 1, "failed": 1}
    assert "wecom" in ps["by_tool"]
    assert ps["by_tool"]["wecom"] == {"total": 1, "sent": 1, "failed": 0}


def test_push_stats_dedup_skipped(tmp_path):
    """插入 notification_deliveries skipped 记录后, dedup_skipped 正确。"""
    app, repo = _make_app(tmp_path)
    _insert_notification_delivery(repo, status="skipped", error="dedup", idx=0)
    _insert_notification_delivery(repo, status="skipped", error="dedup", idx=1)
    _insert_notification_delivery(repo, status="sent", error=None, idx=2)
    client = TestClient(app)
    resp = client.get("/api/workbench")
    assert resp.status_code == 200
    ps = resp.json()["push_stats"]
    assert ps["today"]["dedup_skipped"] == 2


def test_push_stats_recent_failures(tmp_path):
    """recent_failures 返回最近 10 条失败记录。"""
    app, repo = _make_app(tmp_path)
    with repo._connection() as conn:
        # Insert 12 failed + 3 sent records
        for i in range(12):
            _insert_audit_envelope(conn, tool="sct", error=f"err_{i}")
        for i in range(3):
            _insert_audit_envelope(conn, tool="wecom", error=None)
    client = TestClient(app)
    resp = client.get("/api/workbench")
    assert resp.status_code == 200
    ps = resp.json()["push_stats"]
    failures = ps["recent_failures"]
    assert len(failures) == 10  # capped at 10
    assert all(f["error"] is not None for f in failures)
    assert all(f["tool"] == "sct" for f in failures)
    # Most recent first (ORDER BY seq DESC)
    assert failures[0]["error"] == "err_11"
