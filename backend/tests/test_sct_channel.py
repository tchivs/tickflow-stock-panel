"""Phase 56 SCT-01/02: SctChannel unit tests.

Tests the Server酱 (sct.ftqq.com) notification channel adapter, mirroring
FeishuChannel/TelegramChannel contract tests.
"""
from __future__ import annotations

import httpx
import pytest

from app.notifications.delivery import DeliveryConfig, SctChannel


# ── preferences roundtrip ──────────────────────────────────

@pytest.fixture
def _isolated_prefs(tmp_path, monkeypatch):
    import json
    from app.services import preferences

    path = tmp_path / "preferences.json"
    monkeypatch.setattr(preferences, "_path", lambda: path)
    preferences._invalidate_cache()
    yield path
    preferences._invalidate_cache()


def test_sct_sendkey_roundtrip(_isolated_prefs):
    from app.services import preferences

    preferences.set_sct_sendkey("SCT1234567890abcdef")
    assert preferences.get_sct_sendkey() == "SCT1234567890abcdef"

    preferences.set_sct_sendkey("")
    assert preferences.get_sct_sendkey() == ""


# ── SctChannel construction ────────────────────────────────

def test_sct_channel_rejects_wrong_channel_name():
    with pytest.raises(ValueError, match="SCT"):
        SctChannel(DeliveryConfig(channel="feishu", config={"sendkey": "k"}))


def test_sct_channel_rejects_empty_sendkey(monkeypatch):
    monkeypatch.delenv("PHASE1_FIXTURE_MODE", raising=False)
    with pytest.raises(ValueError, match="sendkey"):
        SctChannel(DeliveryConfig(channel="sct", config={"sendkey": ""}))


# ── SctChannel.deliver ─────────────────────────────────────

_EVENT = {
    "id": "evt_01",
    "source": "alert",
    "symbol": "600519.SH",
    "name": "贵州茅台",
    "message": "price crossed threshold",
}


def _stub_post(monkeypatch, *, status_code=200, json_body=None, exc=None):
    """Replace httpx.post with a stub returning a fixed Response (or raising)."""
    calls: list[dict] = []

    def _fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        if exc is not None:
            raise exc
        return httpx.Response(status_code=status_code, json=json_body)

    monkeypatch.setattr("app.notifications.delivery.httpx.post", _fake_post)
    return calls


def test_sct_channel_deliver_success(monkeypatch):
    _stub_post(monkeypatch, status_code=200, json_body={"code": 0, "message": "success"})
    ch = SctChannel(DeliveryConfig(channel="sct", config={"sendkey": "SCTkey123"}))
    result = ch.deliver(_EVENT)
    assert result == {"status": "sent"}


def test_sct_channel_deliver_code_nonzero_fails(monkeypatch):
    _stub_post(monkeypatch, status_code=200, json_body={"code": 40001, "message": "bad sendkey"})
    ch = SctChannel(DeliveryConfig(channel="sct", config={"sendkey": "SCTkey123"}))
    with pytest.raises(RuntimeError, match="Server酱"):
        ch.deliver(_EVENT)


def test_sct_channel_deliver_http_error(monkeypatch):
    _stub_post(monkeypatch, status_code=500, json_body={"code": 0})
    ch = SctChannel(DeliveryConfig(channel="sct", config={"sendkey": "SCTkey123"}))
    with pytest.raises(RuntimeError, match="HTTP 500"):
        ch.deliver(_EVENT)


def test_sct_channel_safe_error_no_sendkey_leak(monkeypatch):
    import httpx as _httpx

    _stub_post(monkeypatch, exc=_httpx.ConnectTimeout("timed out"))
    ch = SctChannel(DeliveryConfig(channel="sct", config={"sendkey": "SECRET_SENDKEY_abc"}))
    from app.notifications.delivery import _safe_error

    with pytest.raises(Exception):
        ch.deliver(_EVENT)
    # _safe_error must not leak the sendkey
    safe = _safe_error(RuntimeError("timed out with SECRET_SENDKEY_abc"), {"sendkey": "SECRET_SENDKEY_abc"})
    assert "SECRET_SENDKEY_abc" not in safe
