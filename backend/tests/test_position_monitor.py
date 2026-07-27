"""CORE-04 contract tests for holding-aware rules in the existing Monitor domain."""
from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import pytest

from app.operational.repository import OperationalRepository
from app.strategy import monitor_rules
from app.strategy.monitor import MonitorRuleEngine


def _quote_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": ["600519.SH"],
            "close": [1600.0],
            "change_pct": [0.04],
        }
    )


def _position_rule(**overrides) -> dict:
    rule = {
        "id": "position_rule",
        "name": "Moutai position limit",
        "type": "position",
        "scope": "positions",
        "position_ids": ["position_cash", "position_margin"],
        "conditions": [{"field": "change_pct", "op": ">=", "value": 0.03}],
        "logic": "and",
        "cooldown_seconds": 300,
        "active_time_start": "09:30",
        "active_time_end": "15:00",
        "bypass_quiet_period": False,
        "webhook_channels": ["feishu", "telegram"],
        "severity": "warn",
        "enabled": True,
    }
    rule.update(overrides)
    return rule


def _position_projection() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "position_id": ["position_cash", "position_margin"],
            "account_id": ["cash", "margin"],
            "symbol": ["600519.SH", "600519.SH"],
            "close": [1600.0, 1600.0],
            "change_pct": [0.04, 0.04],
            "valuation_source": ["shared_quote", "shared_quote"],
            "valuation_as_of": ["2026-07-10T01:30:00+00:00", "2026-07-10T01:30:00+00:00"],
        }
    )


def test_position_rule_requires_explicit_position_scope_schedule_and_approved_channels():
    valid = monitor_rules.normalize(_position_rule())
    monitor_rules.validate(valid)

    for invalid, expected in [
        (_position_rule(position_ids=[]), "position_ids"),
        (_position_rule(scope="symbols"), "scope"),
        (_position_rule(active_time_start="15:00", active_time_end="09:30"), "active"),
        (_position_rule(webhook_channels=["https://untrusted.example"]), "channel"),
    ]:
        with pytest.raises(ValueError, match=expected):
            monitor_rules.validate(monitor_rules.normalize(invalid))


def test_position_rules_preserve_generic_symbol_deduplication_and_scope_each_holding():
    """A generic rule fires once per symbol; a position rule keeps account/position context."""
    generic_rule = {
        "id": "generic_price_rule",
        "name": "Moutai price limit",
        "type": "price",
        "scope": "symbols",
        "symbols": ["600519.SH"],
        "conditions": [{"field": "change_pct", "op": ">=", "value": 0.03}],
        "cooldown_seconds": 0,
        "enabled": True,
    }
    engine = MonitorRuleEngine(
        clock=lambda: datetime(2026, 7, 10, 10, 0, tzinfo=UTC)
    )
    engine.set_rules([generic_rule, _position_rule(cooldown_seconds=0)])

    generic_events = engine.evaluate(_quote_frame())
    position_events = engine.evaluate_positions(_position_projection())

    assert [event["rule_id"] for event in generic_events] == ["generic_price_rule"]
    assert {event["position_id"] for event in position_events} == {
        "position_cash", "position_margin",
    }
    assert {event["account_id"] for event in position_events} == {"cash", "margin"}
    assert {event["valuation_source"] for event in position_events} == {"shared_quote"}
    assert {event["valuation_as_of"] for event in position_events} == {
        "2026-07-10T01:30:00+00:00"
    }


def test_position_rule_cooldown_and_active_time_suppress_only_the_matching_position_events():
    clock = [datetime(2026, 7, 10, 10, 0, tzinfo=UTC)]
    engine = MonitorRuleEngine(clock=lambda: clock[0])
    engine.set_rules([_position_rule()])

    first = engine.evaluate_positions(_position_projection())
    assert len(first) == 2
    assert engine.evaluate_positions(_position_projection()) == []

    clock[0] = datetime(2026, 7, 10, 10, 6, tzinfo=UTC)
    assert len(engine.evaluate_positions(_position_projection())) == 2

    clock[0] = datetime(2026, 7, 10, 15, 1, tzinfo=UTC)
    assert engine.evaluate_positions(_position_projection()) == []


def test_accepted_position_event_persists_immutable_condition_and_valuation_context(tmp_path):
    repository = OperationalRepository(tmp_path / "operational.db")
    repository.migrate()
    event = {
        "id": "event_01",
        "rule_id": "position_rule",
        "position_id": "position_cash",
        "account_id": "cash",
        "symbol": "600519.SH",
        "severity": "warn",
        "conditions": [{"field": "change_pct", "op": ">=", "value": 0.03}],
        "valuation_source": "shared_quote",
        "valuation_as_of": "2026-07-10T01:30:00+00:00",
        "occurred_at": "2026-07-10T01:30:00+00:00",
    }

    repository.record_alert_event(event)
    event["conditions"][0]["value"] = 0.99
    event["valuation_source"] = "mutated"

    persisted = repository.get_alert_event("event_01")
    assert persisted["id"] == "event_01"
    assert persisted["conditions"] == [{"field": "change_pct", "op": ">=", "value": 0.03}]
    assert persisted["valuation_source"] == "shared_quote"
    assert persisted["valuation_as_of"] == "2026-07-10T01:30:00+00:00"
