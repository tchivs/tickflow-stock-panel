"""Focused contracts for the Phase 1 QuoteService fixture trigger."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import preferences
from app.services.quote_service import QuoteService


def test_phase1_fixture_trigger_is_gated_and_evaluates_without_live_fetch(monkeypatch):
    service = QuoteService()
    calls: list[tuple] = []
    monkeypatch.setattr(service, "_evaluate_monitors", lambda *args: calls.append(args))

    monkeypatch.delenv("PHASE1_FIXTURE_MODE", raising=False)
    with pytest.raises(RuntimeError, match="fixture monitor trigger"):
        service.trigger_phase1_fixture_monitor()
    assert calls == []

    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "true")
    assert service.trigger_phase1_fixture_monitor() == {"triggered": True}
    assert len(calls) == 1
    assert calls[0][0].is_empty()
    assert calls[0][1] is None


def test_phase1_fixture_delivery_uses_internal_receiver_urls_without_credentials(monkeypatch):
    enqueued: list[dict] = []
    service = QuoteService()
    service._app_state = SimpleNamespace(
        notification_delivery=SimpleNamespace(enqueue=lambda **kwargs: enqueued.append(kwargs)),
    )
    engine = SimpleNamespace(rules={
        "fixture_rule": {
            "webhook_channels": ["feishu", "telegram"],
            "bypass_quiet_period": False,
        },
    })
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "yes")
    monkeypatch.setenv("PHASE1_FEISHU_RECEIVER_URL", "http://receiver:8080/feishu")
    monkeypatch.setenv("PHASE1_TELEGRAM_RECEIVER_URL", "http://receiver:8080/telegram")
    monkeypatch.setattr(preferences, "load", lambda: {"notification_quiet_period": False})

    service._maybe_send_webhook(
        [{"id": "fixture_event", "rule_id": "fixture_rule", "severity": "warn"}], engine,
    )

    assert len(enqueued) == 1
    assert [config.channel for config in enqueued[0]["channel_configs"]] == ["feishu", "telegram"]
    assert [config.config for config in enqueued[0]["channel_configs"]] == [
        {"fixture_url": "http://receiver:8080/feishu"},
        {"fixture_url": "http://receiver:8080/telegram"},
    ]
