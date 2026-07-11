"""PLAN-01 contract: deterministic decision baseline and pre-review persistence."""
from __future__ import annotations

from datetime import date
from decimal import Decimal


def _governed_snapshot() -> dict[str, object]:
    """Fixed historical inputs; no runtime, provider, or persistence dependency."""
    return {
        "symbol": "600000.SH",
        "bars": [
            {
                "trade_date": f"2024-01-{day:02d}",
                "open": "10.00",
                "high": "10.20",
                "low": "9.80",
                "close": "10.00",
            }
            for day in range(2, 23)
        ],
        "factors": {"ma5": "9.90", "ma10": "9.80", "ma20": "9.00"},
        "score": "8.00",
        "market_state": "震荡",
        "position_cap": "0.50",
        "config": {
            "entry_band": ["0.02", "0.03"],
            "stop_k": "1.5",
            "tp_ratios": ["1.5", "3.0"],
            "per_trade_risk_pct": "0.02",
            "rr_threshold": "1.5",
        },
    }


def test_plan_01_fixed_governed_history_produces_a_typed_stable_baseline():
    """The governed snapshot alone fixes every deterministic decision fact."""
    from app.decision.playbook import DecisionBaseline, DecisionPlaybookService

    service = DecisionPlaybookService()
    first = service.build_baseline(
        snapshot=_governed_snapshot(),
        data_as_of=date(2024, 1, 22),
        engine_config_version="playbook-v1",
    )
    second = service.build_baseline(
        snapshot=_governed_snapshot(),
        data_as_of=date(2024, 1, 22),
        engine_config_version="playbook-v1",
    )

    assert isinstance(first, DecisionBaseline)
    assert first == second
    assert first.symbol == "600000.SH"
    assert first.data_as_of == date(2024, 1, 22)
    assert first.engine_config_version == "playbook-v1"
    assert first.action == "突破确认"
    assert first.entry_low == Decimal("9.7000")
    assert first.entry_high == Decimal("10.2000")
    assert first.stop == Decimal("9.1000")
    assert first.target1 == Decimal("11.1000")
    assert first.target2 == Decimal("12.0000")
    assert first.position_pct == Decimal("0.4999")
    assert first.score == Decimal("8.00")
    assert first.risk_reward == Decimal("2.6667")
    assert first.reason_snapshot == {
        "atr": "0.4000",
        "risk_per_share": "0.6000",
        "source": "governed_history",
    }


def test_plan_01_persists_immutable_baseline_and_initial_final_before_review(tmp_path):
    """A provider may only see a durable baseline whose final snapshot starts identical."""
    from app.decision.playbook import DecisionPlaybookService
    from app.operational.repository import OperationalRepository

    repository = OperationalRepository(tmp_path / "operational.db")
    repository.migrate()
    baseline = DecisionPlaybookService().build_baseline(
        snapshot=_governed_snapshot(),
        data_as_of=date(2024, 1, 22),
        engine_config_version="playbook-v1",
    )

    run = repository.persist_decision_baseline(baseline)
    persisted = repository.get_decision_run(run["id"])

    assert persisted["baseline"] == baseline.to_snapshot()
    assert persisted["final"] == baseline.to_snapshot()
    assert persisted["data_as_of"] == "2024-01-22"
    assert persisted["engine_config_version"] == "playbook-v1"
    assert persisted["proposal"] is None
    assert persisted["adjustments"] == []

    # Baseline facts cannot be overwritten once an audit record can reference the run.
    repository.record_adjustment_audit(
        run_id=run["id"],
        field="entry_low",
        proposed_value="9.8000",
        final_value="9.8000",
        disposition="applied",
        rationale="tighten entry",
    )
    try:
        repository.replace_decision_baseline(run["id"], baseline.to_snapshot())
    except ValueError as exc:
        assert "immutable" in str(exc)
    else:
        raise AssertionError("persisted baseline must remain immutable after audit association")
