"""Phase 56 SCT-01: Settings API endpoint tests for SCT SendKey.

Tests PUT /preferences/sct-sendkey + POST /sct-test endpoints.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def _isolated_prefs(tmp_path, monkeypatch):
    from app.services import preferences

    path = tmp_path / "preferences.json"
    monkeypatch.setattr(preferences, "_path", lambda: path)
    preferences._invalidate_cache()
    yield path
    preferences._invalidate_cache()


def _make_settings_client(tmp_path: Path, monkeypatch) -> TestClient:
    """Minimal FastAPI app with just the settings router."""
    from app.api import settings as settings_api

    app = FastAPI()
    app.include_router(settings_api.router)
    return TestClient(app)


# ── PUT /preferences/sct-sendkey ────────────────────────────

def test_settings_put_sct_sendkey(_isolated_prefs, tmp_path, monkeypatch):
    client = _make_settings_client(tmp_path, monkeypatch)
    resp = client.put("/api/settings/preferences/sct-sendkey", json={"sendkey": "SCTxxx12345678"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_sct_sendkey"] is True
    masked = body["sct_sendkey"]
    # masked value must not contain the full sendkey in plaintext
    assert "SCTxxx12345678" not in masked
    # but should show first 4 chars (mask format: first4 + dots + last4)
    assert masked.startswith("SCTx")


def test_settings_put_sct_sendkey_empty_clears(_isolated_prefs, tmp_path, monkeypatch):
    from app.services import preferences

    # Set first
    preferences.set_sct_sendkey("SCTsomekey")
    client = _make_settings_client(tmp_path, monkeypatch)
    resp = client.put("/api/settings/preferences/sct-sendkey", json={"sendkey": ""})
    assert resp.status_code == 200
    assert resp.json()["has_sct_sendkey"] is False
    assert preferences.get_sct_sendkey() == ""


# ── POST /sct-test ──────────────────────────────────────────

def test_settings_sct_test_success(_isolated_prefs, tmp_path, monkeypatch):
    import httpx
    from app.services import preferences

    preferences.set_sct_sendkey("SCTtestkey123")

    client = _make_settings_client(tmp_path, monkeypatch)

    # Stub httpx.post so SctChannel doesn't make a real call
    def _fake_post(url, **kwargs):
        return httpx.Response(200, json={"code": 0, "message": "success"})

    monkeypatch.setattr("app.notifications.delivery.httpx.post", _fake_post)

    resp = client.post("/api/settings/sct-test")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_settings_sct_test_no_sendkey(_isolated_prefs, tmp_path, monkeypatch):
    # No sendkey configured
    client = _make_settings_client(tmp_path, monkeypatch)
    resp = client.post("/api/settings/sct-test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "SendKey" in body["error"]
