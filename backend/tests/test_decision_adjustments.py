"""PLAN-02 contract: field-bounded adjustments preserve deterministic facts."""
from __future__ import annotations

from datetime import date
from decimal import Decimal


def _baseline():
    from app.decision.playbook import DecisionBaseline

    return DecisionBaseline(
        symbol="600000.SH",
        entry_low=Decimal("9.7000"),
        entry_high=Decimal("10.2000"),
        stop=Decimal("9.1000"),
        target1=Decimal("11.1000"),
        target2=Decimal("12.0000"),
        position_pct=Decimal("0.4999"),
        action="突破确认",
        score=Decimal("8.00"),
        risk_reward=Decimal("2.6667"),
        reason_snapshot={"source": "governed_history"},
        data_as_of=date(2024, 1, 22),
        engine_config_version="playbook-v1",
    )


def _persisted_run(tmp_path):
    from app.operational.repository import OperationalRepository

    repository = OperationalRepository(tmp_path / "operational.db")
    repository.migrate()
    return repository, repository.persist_decision_baseline(_baseline())


def test_plan_02_applies_only_allowlisted_fields_and_audits_every_disposition(tmp_path):
    """Each proposal field is applied, clamped, or rejected without AI authority."""
    from app.decision.adjustments import DecisionAdjustmentService

    repository, run = _persisted_run(tmp_path)
    result = DecisionAdjustmentService(repository).apply(
        run_id=run["id"],
        proposal={
            "entry_low": {"value": "9.8000", "rationale": "wait for confirmation"},
            "stop": {"value": "99.0000", "rationale": "invalid wide stop"},
            "action": {"value": "放弃", "rationale": "AI must not choose action"},
            "score": {"value": "0", "rationale": "AI must not change score"},
            "risk_reward": {"value": "0", "rationale": "AI must not change reward"},
        },
    )

    assert result["final"]["entry_low"] == Decimal("9.8000")
    assert result["final"]["stop"] != Decimal("99.0000")
    assert result["final"]["stop"] >= Decimal("9.1000")
    assert result["final"]["action"] == "突破确认"
    assert result["final"]["score"] == Decimal("8.00")
    assert result["final"]["risk_reward"] == Decimal("2.6667")

    audit = {record["field"]: record for record in result["audit"]}
    assert audit["entry_low"] == {
        "field": "entry_low",
        "proposed_value": "9.8000",
        "final_value": "9.8000",
        "disposition": "applied",
        "rationale": "wait for confirmation",
    }
    assert audit["stop"]["disposition"] == "clamped"
    assert audit["stop"]["proposed_value"] == "99.0000"
    assert audit["stop"]["final_value"] != "99.0000"
    for forbidden in ("action", "score", "risk_reward"):
        assert audit[forbidden]["disposition"] == "rejected"
        assert audit[forbidden]["final_value"] is None

    assert repository.get_decision_run(run["id"])["adjustments"] == result["audit"]


def test_plan_02_rejects_unknown_or_non_numeric_fields_without_mutating_final_snapshot(tmp_path):
    """Untrusted proposal data stays auditable but cannot alter the persisted plan."""
    from app.decision.adjustments import DecisionAdjustmentService

    repository, run = _persisted_run(tmp_path)
    result = DecisionAdjustmentService(repository).apply(
        run_id=run["id"],
        proposal={
            "made_up_field": {"value": "1", "rationale": "unknown field"},
            "target1": {"value": "not-a-number", "rationale": "malformed numeric value"},
        },
    )

    assert result["final"] == _baseline().to_snapshot()
    audit = {record["field"]: record for record in result["audit"]}
    assert audit["made_up_field"]["disposition"] == "rejected"
    assert audit["target1"]["disposition"] == "rejected"
    assert all(record["final_value"] is None for record in audit.values())
