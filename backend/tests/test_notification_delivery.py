"""CORE-04 contract tests for bounded, credential-safe notification delivery."""
from __future__ import annotations

from datetime import datetime, timezone
from threading import Event
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.alerts import router as alerts_router

import pytest

from app.notifications.delivery import (
    DeliveryConfig,
    FeishuChannel,
    NotificationDeliveryService,
    TelegramChannel,
)
from app.operational.repository import OperationalRepository
from app.services.quote_service import QuoteService


class _RecordingSubscriber:
    def __init__(self):
        self.alerts: list[dict] = []

    def push_alerts(self, alerts: list[dict]) -> None:
        self.alerts.extend(alerts)


def _event() -> dict:
    return {
        "id": "alert_01",
        "rule_id": "position_rule",
        "symbol": "600519.SH",
        "position_id": "position_01",
        "account_id": "account_01",
        "severity": "warn",
        "message": "price crossed threshold",
        "occurred_at": "2026-07-10T01:30:00+00:00",
    }


def test_event_persists_and_streams_before_slow_delivery_completes(tmp_path):
    """Network delivery starts only after the alert is durable and observable on the shared stream."""
    repository = OperationalRepository(tmp_path / "operational.db")
    repository.migrate()
    delivery_started = Event()
    release_delivery = Event()

    class _SlowChannel:
        name = "feishu"

        def deliver(self, event):
            delivery_started.set()
            assert release_delivery.wait(timeout=0.25)
            return {"status": "sent"}

    service = QuoteService()
    subscriber = _RecordingSubscriber()
    service._snapshot_subscribers = lambda: [subscriber]
    delivery = NotificationDeliveryService(
        repository=repository,
        channels={"feishu": _SlowChannel()},
        max_workers=1,
    )

    service.persist_stream_and_enqueue_alerts(
        events=[_event()],
        repository=repository,
        delivery_service=delivery,
        channel_configs=[DeliveryConfig(channel="feishu", config={"webhook": "token"})],
    )

    assert repository.get_alert_event("alert_01")["id"] == "alert_01"
    assert subscriber.alerts == [_event()]
    assert delivery_started.wait(timeout=0.25) is True
    assert repository.list_delivery_outcomes("alert_01") == [
        {"channel": "feishu", "status": "pending", "error": None}
    ]

    release_delivery.set()
    delivery.drain(timeout=0.25)
    assert repository.list_delivery_outcomes("alert_01") == [
        {"channel": "feishu", "status": "sent", "error": None}
    ]


def test_delivery_rejects_arbitrary_origins_times_out_and_redacts_sensitive_failures(tmp_path):
    repository = OperationalRepository(tmp_path / "operational.db")
    repository.migrate()

    with pytest.raises(ValueError, match="Feishu"):
        FeishuChannel(DeliveryConfig(channel="feishu", config={"webhook": "https://evil.example/hook"}))
    with pytest.raises(ValueError, match="Telegram"):
        TelegramChannel(
            DeliveryConfig(
                channel="telegram",
                config={"bot_token": "secret-token", "chat_id": "chat", "url": "https://evil.example"},
            )
        )

    class _TimeoutChannel:
        name = "telegram"

        def deliver(self, event):
            raise TimeoutError("https://api.telegram.org/botsecret-token/sendMessage timed out")

    delivery = NotificationDeliveryService(
        repository=repository,
        channels={"telegram": _TimeoutChannel()},
        max_workers=1,
        timeout_seconds=0.01,
    )
    repository.record_alert_event(_event())
    delivery.enqueue(
        event_id="alert_01",
        channel_configs=[DeliveryConfig(channel="telegram", config={"bot_token": "secret-token", "chat_id": "chat"})],
    )
    delivery.drain(timeout=0.25)

    outcome = repository.list_delivery_outcomes("alert_01")[0]
    assert outcome["status"] == "failed"
    assert "secret-token" not in outcome["error"]
    assert "api.telegram.org" not in outcome["error"]

def test_fixture_delivery_accepts_only_internal_receiver_urls(monkeypatch):
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "true")

    feishu = FeishuChannel(
        DeliveryConfig(channel="feishu", config={"fixture_url": "http://receiver:8080/feishu"}),
    )
    telegram = TelegramChannel(
        DeliveryConfig(channel="telegram", config={"fixture_url": "http://receiver:8080/telegram"}),
    )

    assert feishu._fixture_url == "http://receiver:8080/feishu"
    assert telegram._fixture_url == "http://receiver:8080/telegram"
    with pytest.raises(ValueError, match="internal receiver"):
        FeishuChannel(
            DeliveryConfig(channel="feishu", config={"fixture_url": "https://outside.example/hook"}),
        )


def test_quiet_period_records_skipped_outcome_but_cooldown_non_event_has_no_delivery(tmp_path):
    repository = OperationalRepository(tmp_path / "operational.db")
    repository.migrate()
    delivery = NotificationDeliveryService(repository=repository, channels={}, max_workers=1)

    repository.record_alert_event(_event())
    delivery.enqueue(
        event_id="alert_01",
        channel_configs=[DeliveryConfig(channel="feishu", config={})],
        quiet_period=True,
        bypass_quiet_period=False,
    )

    assert repository.list_delivery_outcomes("alert_01") == [
        {"channel": "feishu", "status": "skipped", "error": "quiet_period"}
    ]
    assert repository.get_alert_event("alert_01")["id"] == "alert_01"
    assert repository.list_delivery_outcomes("cooldown_suppressed") == []

def test_operational_alert_history_filters_and_delivery_detail_are_safe(tmp_path):
    repository = OperationalRepository(tmp_path / "operational.db")
    repository.migrate()
    repository.record_alert_event({
        **_event(),
        "source": "position",
        "type": "position",
        "name": "贵州茅台",
        "valuation_source": "shared_quote",
        "valuation_as_of": "2026-07-10T01:30:00+00:00",
    })
    repository.create_delivery_outcome(
        event_id="alert_01", channel="telegram", status="failed", error="delivery failed",
    )
    app = FastAPI()
    app.include_router(alerts_router)
    app.state.operational = repository
    client = TestClient(app)

    history = client.get("/api/alerts?severity=warn&delivery_status=failed")
    assert history.status_code == 200
    event = history.json()["alerts"][0]
    assert event["id"] == "alert_01"
    assert event["deliveries"][0]["status"] == "failed"
    assert event["deliveries"][0]["error"] == "delivery failed"

    detail = client.get("/api/alerts/alert_01/deliveries")
    assert detail.status_code == 200
    assert detail.json()["deliveries"] == event["deliveries"]
    assert set(detail.json()["deliveries"][0]) == {
        "channel", "status", "error", "created_at", "updated_at",
    }
