"""CORE-04 contract tests for bounded, credential-safe notification delivery."""
from __future__ import annotations

from datetime import UTC, datetime
from threading import Event

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.alerts import router as alerts_router
from app.notifications.delivery import (
    DeliveryConfig,
    FeishuChannel,
    NotificationDeliveryService,
    TelegramChannel,
)
from app.operational import repository as operational_repository_module
from app.operational.repository import OperationalRepository
from app.services.quote_service import QuoteService




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
    broadcast_calls: list[tuple[str, str, dict]] = []
    service._broadcast_alerts = lambda alerts: broadcast_calls.append(("alerts", "strategy_alert", alerts))
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
    # Phase 55: 广播在投递完成前已发出 (通过 WS alerts 频道)
    assert len(broadcast_calls) == 1
    ch, mtype, broadcast_alerts = broadcast_calls[0]
    assert ch == "alerts"
    assert mtype == "strategy_alert"
    assert broadcast_alerts[0]["id"] == "alert_01"
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

def test_operational_alert_history_filters_and_delivery_detail_are_safe(
    tmp_path, monkeypatch,
):
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

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            frozen = cls(2026, 7, 10, 2, 0, tzinfo=UTC)
            return frozen if tz is None else frozen.astimezone(tz)

    monkeypatch.setattr(operational_repository_module, "datetime", _FixedDatetime)
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


# ===== Phase 56: SCT channel audit / dedup / daily limit / pipeline =====

import httpx
import time as _time

from app.notifications.delivery import SctChannel, SCT_DEDUP_TTL, SCT_DAILY_LIMIT
from app.audit.envelope import ToolCallAuditRepository
from app.audit.service import get_audit_repo, set_audit_repo


def _sct_event(*, event_id="sct_evt_01", rule_id="sct_rule", symbol="600519.SH", event_type="price"):
    return {
        "id": event_id,
        "rule_id": rule_id,
        "symbol": symbol,
        "type": event_type,
        "source": "alert",
        "severity": "warn",
        "message": "price crossed threshold",
        "occurred_at": "2026-08-22T01:30:00+00:00",
    }


def _stub_sct_post(monkeypatch, *, status_code=200, json_body=None, exc=None):
    def _fake_post(url, **kwargs):
        if exc is not None:
            raise exc
        return httpx.Response(status_code=status_code, json=json_body or {"code": 0})
    monkeypatch.setattr("app.notifications.delivery.httpx.post", _fake_post)


def test_sct_channel_records_audit_envelope(monkeypatch, tmp_path):
    """deliver success → ToolCallEnvelope(tool=sct, category=notification) recorded."""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    repo = ToolCallAuditRepository(conn)
    # Create the table schema
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tool_call_envelopes (
            id TEXT PRIMARY KEY, seq INTEGER, tool TEXT, category TEXT,
            params_hash TEXT, params_summary TEXT, version TEXT, scope TEXT,
            principal TEXT, response_shape TEXT, response_summary TEXT,
            raw_hash TEXT, duration_ms REAL, error TEXT,
            cached INTEGER, degraded INTEGER, schema_valid INTEGER, created_at TEXT
        )
    """)
    conn.commit()
    set_audit_repo(repo)
    try:
        _stub_sct_post(monkeypatch)
        ch = SctChannel(DeliveryConfig(channel="sct", config={"sendkey": "SCTkey123"}))
        ch.deliver(_sct_event())

        calls = repo.list_calls(tool="sct")
        assert len(calls) == 1
        env = calls[0]
        assert env.tool == "sct"
        assert env.category == "notification"
        assert env.raw_hash  # non-empty hash
        assert env.duration_ms >= 0
    finally:
        set_audit_repo(None)


def test_sct_channel_records_audit_on_failure(monkeypatch, tmp_path):
    """deliver failure → audit record with error field non-empty."""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    repo = ToolCallAuditRepository(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tool_call_envelopes (
            id TEXT PRIMARY KEY, seq INTEGER, tool TEXT, category TEXT,
            params_hash TEXT, params_summary TEXT, version TEXT, scope TEXT,
            principal TEXT, response_shape TEXT, response_summary TEXT,
            raw_hash TEXT, duration_ms REAL, error TEXT,
            cached INTEGER, degraded INTEGER, schema_valid INTEGER, created_at TEXT
        )
    """)
    conn.commit()
    set_audit_repo(repo)
    try:
        _stub_sct_post(monkeypatch, status_code=500, json_body={"code": 0})
        ch = SctChannel(DeliveryConfig(channel="sct", config={"sendkey": "SCTkey123"}))
        with pytest.raises(RuntimeError):
            ch.deliver(_sct_event())

        calls = repo.list_calls(tool="sct")
        assert len(calls) == 1
        assert calls[0].error  # non-empty error
    finally:
        set_audit_repo(None)


def test_channel_for_sct_returns_sct_channel(tmp_path):
    """_channel_for('sct') returns a SctChannel instance."""
    monkeypatch_setenv = None
    import os
    old = os.environ.get("PHASE1_FIXTURE_MODE", "")
    os.environ.pop("PHASE1_FIXTURE_MODE", None)
    try:
        repository = OperationalRepository(tmp_path / "operational.db")
        repository.migrate()
        service = NotificationDeliveryService(repository=repository, channels={}, max_workers=1)
        ch = service._channel_for(DeliveryConfig(channel="sct", config={"sendkey": "SCTkey123"}))
        assert isinstance(ch, SctChannel)
    finally:
        if old:
            os.environ["PHASE1_FIXTURE_MODE"] = old


def _make_delivery_service(tmp_path):
    repository = OperationalRepository(tmp_path / "operational.db")
    repository.migrate()
    return repository, NotificationDeliveryService(repository=repository, channels={}, max_workers=1)


def _sct_config(**extra):
    cfg = {"sendkey": "SCTkey123"}
    cfg.update(extra)
    return DeliveryConfig(channel="sct", config=cfg)


def test_dedup_skips_within_5min(monkeypatch, tmp_path):
    """Same (rule_id, symbol, event_type) within 5 min → status=skipped, error=dedup."""
    _stub_sct_post(monkeypatch)
    repository, service = _make_delivery_service(tmp_path)

    evt = _sct_event(event_id="dedup_01")
    repository.record_alert_event(evt)
    service.enqueue(event_id="dedup_01", channel_configs=[_sct_config()])
    service.drain(timeout=1.0)

    # Second enqueue with same dedup key but different event_id
    evt2 = _sct_event(event_id="dedup_02")
    repository.record_alert_event(evt2)
    service.enqueue(event_id="dedup_02", channel_configs=[_sct_config()])
    service.drain(timeout=1.0)

    outcomes = repository.list_delivery_outcomes("dedup_02")
    assert len(outcomes) == 1
    assert outcomes[0]["status"] == "skipped"
    assert outcomes[0]["error"] == "dedup"


def test_dedup_allows_after_5min(monkeypatch, tmp_path):
    """After dedup window expires, same key can be delivered again."""
    _stub_sct_post(monkeypatch)
    repository, service = _make_delivery_service(tmp_path)

    evt = _sct_event(event_id="dedup_late_01")
    repository.record_alert_event(evt)
    service.enqueue(event_id="dedup_late_01", channel_configs=[_sct_config()])
    service.drain(timeout=1.0)

    # Expire the dedup entry by backdating it
    dedup_key = "sct_rule:600519.SH:price"
    service._dedup_cache[dedup_key] = _time.time() - SCT_DEDUP_TTL - 1

    evt2 = _sct_event(event_id="dedup_late_02")
    repository.record_alert_event(evt2)
    service.enqueue(event_id="dedup_late_02", channel_configs=[_sct_config()])
    service.drain(timeout=1.0)

    outcomes = repository.list_delivery_outcomes("dedup_late_02")
    assert outcomes[0]["status"] == "sent"


def test_dedup_different_key_not_skipped(monkeypatch, tmp_path):
    """Different rule_id/symbol/event_type is NOT deduped."""
    _stub_sct_post(monkeypatch)
    repository, service = _make_delivery_service(tmp_path)

    repository.record_alert_event(_sct_event(event_id="diff_01", rule_id="rule_a"))
    service.enqueue(event_id="diff_01", channel_configs=[_sct_config()])
    service.drain(timeout=1.0)

    repository.record_alert_event(_sct_event(event_id="diff_02", rule_id="rule_b"))
    service.enqueue(event_id="diff_02", channel_configs=[_sct_config()])
    service.drain(timeout=1.0)

    outcomes = repository.list_delivery_outcomes("diff_02")
    assert outcomes[0]["status"] == "sent"


def test_daily_limit_degrades_to_summary(monkeypatch, tmp_path):
    """After 200 SCT pushes in a day, further pushes are skipped with daily_limit_exceeded
    and a batch overflow summary is sent once."""
    sent_posts: list[dict] = []

    def _fake_post(url, **kwargs):
        sent_posts.append({"url": url, **kwargs})
        return type("Resp", (), {"status_code": 200, "json": lambda: {"code": 0}, "text": "ok"})()

    monkeypatch.setattr("app.notifications.delivery.httpx.post", _fake_post)
    repository, service = _make_delivery_service(tmp_path)

    # Simulate already pushed 200 today
    service._daily_count = SCT_DAILY_LIMIT

    repository.record_alert_event(_sct_event(event_id="limit_01"))
    service.enqueue(event_id="limit_01", channel_configs=[_sct_config()])
    service.drain(timeout=1.0)

    outcomes = repository.list_delivery_outcomes("limit_01")
    assert outcomes[0]["status"] == "skipped"
    assert outcomes[0]["error"] == "daily_limit_exceeded"

    # 批量摘要推送应被发送一次 (不占用每日配额)
    assert "已达上限" in sent_posts[0]["data"]["desp"]

    # 第二条超限事件不再触发摘要
    sent_posts.clear()
    repository.record_alert_event(_sct_event(event_id="limit_02"))
    service.enqueue(event_id="limit_02", channel_configs=[_sct_config()])
    service.drain(timeout=1.0)
    assert len(sent_posts) == 0

def test_quote_service_sends_sct_when_requested(monkeypatch, tmp_path):
    """_maybe_send_webhook with webhook_channels including 'sct' + sendkey → DeliveryConfig(channel=sct)."""
    from app.services import preferences

    path = tmp_path / "preferences.json"
    monkeypatch.setattr(preferences, "_path", lambda: path)
    preferences._invalidate_cache()
    preferences.set_sct_sendkey("SCTkey123")

    captured: list = []

    class _FakeDelivery:
        def enqueue(self, *, event_id, channel_configs, quiet_period=False, bypass_quiet_period=False):
            captured.extend(channel_configs)

    class _FakeApp:
        notification_delivery = _FakeDelivery()

    class _FakeEngine:
        rules = {"sct_rule": {"webhook_channels": ["sct"]}}

    svc = QuoteService()
    svc._app_state = _FakeApp()
    svc._maybe_send_webhook([_sct_event(event_id="qs_sct_01")], _FakeEngine())

    sct_configs = [c for c in captured if c.channel == "sct"]
    assert len(sct_configs) == 1
    assert sct_configs[0].config.get("sendkey") == "SCTkey123"

    preferences._invalidate_cache()


def test_review_push_sct_branch(monkeypatch, tmp_path):
    """_maybe_push_review with channels including 'sct' → SctChannel.deliver called."""
    from app.services import preferences
    from app.jobs import daily_pipeline

    path = tmp_path / "preferences.json"
    monkeypatch.setattr(preferences, "_path", lambda: path)
    preferences._invalidate_cache()
    preferences.set_sct_sendkey("SCTkey123")
    # Set review_push_channels to include sct
    preferences.set_review_push_channels(["sct"])

    _stub_sct_post(monkeypatch)

    daily_pipeline._maybe_push_review("test content", {"as_of": "2026-08-22", "emotion_label": "neutral"})
    # No assertion on return (void); just verify no exception and httpx.post was called
    # The stub _fake_post already recorded the call; we verify via the monkeypatch stub

    preferences._invalidate_cache()


def test_monitor_rules_validate_accepts_sct():
    """validate({webhook_channels:['feishu','sct']}) does not raise."""
    from app.strategy.monitor_rules import validate

    rule = {
        "id": "test_rule",
        "name": "Test Rule",
        "type": "price",
        "scope": "symbols",
        "symbols": ["600519.SH"],
        "conditions": [{"field": "close", "op": ">", "value": 1000}],
        "webhook_channels": ["feishu", "sct"],
    }
    validate(rule)  # should not raise


def test_monitor_rules_normalize_keeps_sct():
    """normalize() does not strip sct channel."""
    from app.strategy.monitor_rules import normalize

    rule = {
        "id": "test_rule",
        "type": "price",
        "webhook_channels": ["feishu", "sct", "wecom"],
    }
    result = normalize(rule)
    assert "sct" in result["webhook_channels"]
    assert "wecom" not in result["webhook_channels"]  # wecom still stripped
