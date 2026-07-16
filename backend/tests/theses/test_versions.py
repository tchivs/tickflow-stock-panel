"""Strict RED contracts for immutable thesis versions and auditable lineage."""
from __future__ import annotations

import sqlite3
from datetime import date

import pytest
from pydantic import ValidationError


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "instrument": "600519.SH",
        "core_judgment": "Pricing power supports durable free cash flow.",
        "rationale": "Audited distribution and margin evidence support the judgment.",
        "change_reason": "Initial thesis record",
        "anchors": [
            {
                "method": "discounted_cash_flow",
                "currency": "CNY",
                "as_of": date(2026, 6, 30),
                "low": 1420.0,
                "high": 1680.0,
                "assumptions": [{"name": "discount_rate", "value": 0.085, "unit": "ratio"}],
                "limitations": ["Terminal-value sensitivity remains material."],
            }
        ],
        "conditions": [
            {
                "source_kind": "financial",
                "field": "revenue_growth_yoy",
                "operator": "lt",
                "threshold": 0.0,
                "unit": "ratio",
                "lookback_days": 120,
                "cadence": "quarterly",
                "timezone": "Asia/Shanghai",
                "description": "Revenue growth turns negative.",
            }
        ],
    }
    payload.update(overrides)
    return payload


def _repository(tmp_path):
    from app.theses.repository import ThesisRepository

    return ThesisRepository(tmp_path / "operational.db")


def _create(repository, **overrides: object):
    from app.theses.schemas import ThesisVersionRequest

    request = ThesisVersionRequest.model_validate(_payload(**overrides))
    return repository.create_version(request=request, created_by="principal-opaque")


def _revise(repository, first: dict[str, object], **overrides: object):
    from app.theses.schemas import ThesisRevisionRequest

    payload: dict[str, object] = {
        "expected_predecessor_id": first["id"],
        "change_reason": "New filing changed a bounded assumption.",
    }
    payload.update(overrides)
    request = ThesisRevisionRequest.model_validate(payload)
    return repository.revise_version(
        thesis_id=first["thesis_id"], request=request, created_by="principal-opaque"
    )


def test_create_version_atomically_persists_identity_anchor_condition_and_schedule(tmp_path) -> None:
    repository = _repository(tmp_path)

    version = _create(repository)
    persisted = repository.get_version(version["id"])

    assert persisted is not None
    assert persisted["thesis_id"] == version["thesis_id"]
    assert persisted["version"] == 1
    assert persisted["predecessor_id"] is None
    assert persisted["instrument"] == "600519.SH"
    assert persisted["core_judgment"] == "Pricing power supports durable free cash flow."
    assert persisted["change_reason"] == "Initial thesis record"
    assert len(persisted["anchors"]) == 1
    assert persisted["anchors"][0]["assumptions"] == [
        {"name": "discount_rate", "value": 0.085, "unit": "ratio"}
    ]
    assert len(persisted["conditions"]) == 1
    assert persisted["conditions"][0]["cadence"] == "quarterly"
    assert persisted["conditions"][0]["timezone"] == "Asia/Shanghai"
    schedule = repository.get_schedule(persisted["conditions"][0]["id"])
    assert schedule["condition_id"] == persisted["conditions"][0]["id"]
    assert schedule["next_due_at"] is not None


def test_failed_atomic_version_creation_leaves_no_partial_identity_anchor_or_condition(tmp_path) -> None:
    repository = _repository(tmp_path)
    from app.theses.schemas import ThesisVersionRequest

    with pytest.raises(ValidationError):
        ThesisVersionRequest.model_validate(_payload(anchors=[]))
    with pytest.raises(ValidationError):
        ThesisVersionRequest.model_validate(_payload(conditions=[]))

    assert repository.list_for_instrument("600519.SH") == []
    with sqlite3.connect(repository.database_path) as connection:
        for table in ("theses", "thesis_versions", "thesis_valuation_anchors", "thesis_conditions"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_revision_appends_predecessor_and_copies_only_omitted_validated_fields(tmp_path) -> None:
    repository = _repository(tmp_path)
    first = _create(repository)

    second = _revise(
        repository,
        first,
        core_judgment="Pricing power persists, but the valuation margin narrowed.",
        rationale="The new filing supports operations but raises the starting valuation.",
    )

    assert second["version"] == 2
    assert second["predecessor_id"] == first["id"]
    assert second["core_judgment"].endswith("margin narrowed.")
    assert second["anchors"] == first["anchors"]
    assert second["conditions"] != first["conditions"]
    assert [item["field"] for item in second["conditions"]] == ["revenue_growth_yoy"]
    assert second["conditions"][0]["copied_from_condition_id"] == first["conditions"][0]["id"]
    assert repository.get_version(first["id"]) == first


def test_explicit_revision_revalidates_replacement_anchor_and_condition(tmp_path) -> None:
    repository = _repository(tmp_path)
    first = _create(repository)

    with pytest.raises(ValidationError):
        _revise(repository, first, anchors=[{"target_price": 1600.0}])
    with pytest.raises(ValidationError):
        _revise(repository, first, conditions=[{"expression": "close < 1"}])

    versions = repository.list_versions(first["thesis_id"])
    assert [item["id"] for item in versions] == [first["id"]]


def test_multiple_revisions_preserve_anchor_condition_and_check_history(tmp_path) -> None:
    repository = _repository(tmp_path)
    first = _create(repository)
    condition = first["conditions"][0]
    check = repository.append_condition_check(
        version_id=first["id"],
        condition_id=condition["id"],
        due_at="2026-07-01T00:00:00+00:00",
        result="not_matched",
        evidence_fingerprint="a" * 64,
        evidence=[{"source_id": "filing-2026q2", "as_of": "2026-06-30", "observed_value": 0.04}],
        checked_at="2026-07-01T00:01:00+00:00",
    )
    second = _revise(repository, first, rationale="First evidence review retained the thesis.")
    third = _revise(repository, second, core_judgment="Margins weakened enough to narrow conviction.")

    history = repository.list_versions(first["thesis_id"])
    assert [item["version"] for item in history] == [3, 2, 1]
    assert history[-1]["anchors"] == first["anchors"]
    assert repository.list_checks(condition["id"]) == [check]
    assert repository.get_version(first["id"])["conditions"][0]["id"] == condition["id"]
    assert third["predecessor_id"] == second["id"]


def test_current_version_is_derived_deterministically_from_lineage(tmp_path) -> None:
    repository = _repository(tmp_path)
    first = _create(repository)
    second = _revise(repository, first, rationale="Second version rationale.")
    third = _revise(repository, second, rationale="Third version rationale.")

    assert repository.current_version(first["thesis_id"])["id"] == third["id"]
    assert repository.current_version_for_instrument("600519.SH")["id"] == third["id"]
    assert repository.list_versions(first["thesis_id"])[-1]["id"] == first["id"]


def test_stale_predecessor_and_identity_change_fail_without_partial_rows(tmp_path) -> None:
    repository = _repository(tmp_path)
    first = _create(repository)
    second = _revise(repository, first, rationale="Current version.")

    with pytest.raises(ValueError, match=r"stale|predecessor|conflict"):
        _revise(repository, first, rationale="Stale concurrent edit.")
    with pytest.raises(ValidationError):
        _revise(repository, second, instrument="000001.SZ")

    assert [item["id"] for item in repository.list_versions(first["thesis_id"])] == [second["id"], first["id"]]


def test_version_anchor_condition_and_check_facts_reject_update_and_delete(tmp_path) -> None:
    repository = _repository(tmp_path)
    first = _create(repository)
    condition = first["conditions"][0]
    check = repository.append_condition_check(
        version_id=first["id"], condition_id=condition["id"],
        due_at="2026-07-01T00:00:00+00:00", result="insufficient_evidence",
        evidence_fingerprint="b" * 64, evidence=[], checked_at="2026-07-01T00:01:00+00:00",
    )

    mutations = (
        ("UPDATE thesis_versions SET core_judgment = 'tampered' WHERE id = ?", first["id"]),
        ("DELETE FROM thesis_versions WHERE id = ?", first["id"]),
        ("UPDATE thesis_valuation_anchors SET high = 1 WHERE version_id = ?", first["id"]),
        ("DELETE FROM thesis_valuation_anchors WHERE version_id = ?", first["id"]),
        ("UPDATE thesis_conditions SET field = 'close' WHERE id = ?", condition["id"]),
        ("DELETE FROM thesis_conditions WHERE id = ?", condition["id"]),
        ("UPDATE thesis_condition_checks SET result = 'matched' WHERE id = ?", check["id"]),
        ("DELETE FROM thesis_condition_checks WHERE id = ?", check["id"]),
    )
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for statement, identifier in mutations:
            with pytest.raises(sqlite3.DatabaseError, match=r"immutable|restricted"):
                connection.execute(statement, (identifier,))


def test_foreign_key_and_cross_thesis_predecessor_tampering_fail(tmp_path) -> None:
    repository = _repository(tmp_path)
    first = _create(repository)
    other = _create(repository, instrument="000001.SZ")

    with sqlite3.connect(repository.database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO thesis_conditions (id, version_id, source_kind, field, operator, threshold_json, unit, lookback_days, cadence, timezone, description, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("orphan", "missing-version", "market", "close", "lt", "1", "CNY", 1, "daily", "Asia/Shanghai", "orphan", "2026-07-01T00:00:00+00:00"),
            )
    from app.theses.schemas import ThesisRevisionRequest
    request = ThesisRevisionRequest.model_validate(
        {"expected_predecessor_id": other["id"], "change_reason": "Cross-thesis tamper"}
    )
    with pytest.raises(ValueError, match=r"predecessor|thesis|conflict"):
        repository.revise_version(thesis_id=first["thesis_id"], request=request, created_by="principal-opaque")


def test_historical_projection_is_complete_auditable_and_safe(tmp_path) -> None:
    repository = _repository(tmp_path)
    first = _create(repository)
    second = _revise(repository, first, rationale="Updated with a new filing.")

    history = repository.list_versions(first["thesis_id"])
    assert {item["id"] for item in history} == {first["id"], second["id"]}
    for version in history:
        assert {"id", "thesis_id", "instrument", "version", "predecessor_id", "core_judgment", "rationale", "change_reason", "anchors", "conditions", "created_at"} <= set(version)
        serialized = repr(version).lower()
        assert "operational.db" not in serialized
        assert "select " not in serialized
        assert "principal-opaque" not in serialized
        assert "traceback" not in serialized
