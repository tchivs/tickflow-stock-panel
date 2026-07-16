"""Governed source-specific evidence resolution for Thesis conditions."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
import json
import math
from typing import Any, Protocol

from pydantic import ValidationError

from app.theses.conditions import ConditionEvaluator
from app.theses.schemas import EvidenceFact, EvidenceStatus, ThesisCondition


class GovernedSourceReader(Protocol):
    """Narrow read-only source boundary owned by the deployment."""

    def __call__(
        self,
        *,
        instrument: str,
        field: str,
        as_of: date,
        lookback_days: int,
    ) -> Mapping[str, object] | None: ...


class GovernedEvidenceResolver:
    """Resolve typed facts through fixed market, financial, and analysis readers."""

    def __init__(
        self,
        *,
        market_reader: GovernedSourceReader,
        financial_reader: GovernedSourceReader,
        analysis_reader: GovernedSourceReader,
        evaluator: ConditionEvaluator | None = None,
    ) -> None:
        self._readers: dict[str, GovernedSourceReader] = {
            "market": market_reader,
            "financial": financial_reader,
            "analysis": analysis_reader,
        }
        self._evaluator = evaluator or ConditionEvaluator()

    def resolve(
        self,
        *,
        condition: ThesisCondition | Mapping[str, object],
        due_at: str,
        instrument: str | None = None,
    ) -> dict[str, object]:
        """Resolve and evaluate one condition without accepting evidence authority."""
        try:
            validated_condition, resolved_instrument = _validated_inputs(condition, instrument)
            due = _aware_datetime(due_at)
        except (TypeError, ValueError, ValidationError):
            fingerprint = _fingerprint({"status": "error", "reason": "invalid_resolution_request"})
            return _result(
                result="error",
                observed_value=None,
                unit=None,
                as_of=None,
                evidence=[],
                fingerprint=fingerprint,
                reason="invalid_resolution_request",
            )

        reader = self._readers[validated_condition.source_kind]
        try:
            raw = reader(
                instrument=resolved_instrument,
                field=validated_condition.field,
                as_of=due.date(),
                lookback_days=validated_condition.lookback_days,
            )
        except Exception:
            return self._non_observation(
                condition=validated_condition,
                instrument=resolved_instrument,
                due=due,
                status=EvidenceStatus.ERROR,
                reason="governed_source_error",
            )
        if raw is None:
            return self._non_observation(
                condition=validated_condition,
                instrument=resolved_instrument,
                due=due,
                status=EvidenceStatus.MISSING,
                reason="missing_evidence",
            )

        try:
            observed = raw.get("observed_value", raw.get("value"))
            if isinstance(observed, bool) or not isinstance(observed, (int, float)) or not math.isfinite(observed):
                raise ValueError("observed value is malformed")
            evidence_as_of = _as_date(raw.get("as_of"))
            earliest = due.date() - timedelta(days=validated_condition.lookback_days)
            if evidence_as_of > due.date() or evidence_as_of < earliest:
                return self._non_observation(
                    condition=validated_condition,
                    instrument=resolved_instrument,
                    due=due,
                    status=EvidenceStatus.MISSING,
                    reason="stale_evidence",
                )
            unit = raw.get("unit")
            if unit != validated_condition.unit:
                raise ValueError("evidence unit mismatch")
            source_id = _bounded_text(raw.get("source_id"), "source_id", maximum=256)
            source_revision = _bounded_text(raw.get("source_revision"), "source_revision", maximum=128)
            bounded = {
                "source_id": source_id,
                "source_revision": source_revision,
                "source_kind": validated_condition.source_kind,
                "field": validated_condition.field,
                "observed_value": float(observed),
                "unit": unit,
                "as_of": evidence_as_of.isoformat(),
            }
            fingerprint = _fingerprint(bounded)
            fact = EvidenceFact(
                status=EvidenceStatus.OBSERVED,
                source_kind=validated_condition.source_kind,
                source_id=source_id,
                as_of=evidence_as_of,
                observed_value=float(observed),
                unit=unit,
                source_revision=source_revision,
                evidence_fingerprint=fingerprint,
            )
            evaluation = self._evaluator.evaluate(condition=validated_condition, evidence=fact)
            return _result(
                result=evaluation.result.value,
                observed_value=evaluation.observed_value,
                unit=unit,
                as_of=evidence_as_of.isoformat(),
                evidence=[bounded],
                fingerprint=fingerprint,
                reason=evaluation.safe_reason,
            )
        except (TypeError, ValueError, ValidationError):
            return self._non_observation(
                condition=validated_condition,
                instrument=resolved_instrument,
                due=due,
                status=EvidenceStatus.ERROR,
                reason="malformed_evidence",
            )

    def _non_observation(
        self,
        *,
        condition: ThesisCondition,
        instrument: str,
        due: datetime,
        status: EvidenceStatus,
        reason: str,
    ) -> dict[str, object]:
        payload = {
            "status": status.value,
            "source_kind": condition.source_kind,
            "instrument": instrument,
            "field": condition.field,
            "due_at": due.isoformat(),
            "reason": reason,
        }
        fingerprint = _fingerprint(payload)
        fact = EvidenceFact(
            status=status,
            source_kind=condition.source_kind,
            source_id=f"{condition.source_kind}:{instrument}:{condition.field}:{status.value}",
            evidence_fingerprint=fingerprint,
            safe_reason=reason,
        )
        evaluation = self._evaluator.evaluate(condition=condition, evidence=fact)
        return _result(
            result=evaluation.result.value,
            observed_value=None,
            unit=None,
            as_of=None,
            evidence=[],
            fingerprint=fingerprint,
            reason=evaluation.safe_reason,
        )


def _validated_inputs(
    condition: ThesisCondition | Mapping[str, object], instrument: str | None
) -> tuple[ThesisCondition, str]:
    if isinstance(condition, ThesisCondition):
        validated = condition
        embedded_instrument = None
    else:
        values = dict(condition)
        embedded_instrument = values.pop("instrument", None)
        values.pop("id", None)
        values.pop("version_id", None)
        values.pop("copied_from_condition_id", None)
        validated = ThesisCondition.model_validate(values)
    candidate = instrument if instrument is not None else embedded_instrument
    if not isinstance(candidate, str) or not (resolved := candidate.strip().upper()):
        raise ValueError("instrument is required for governed evidence resolution")
    if len(resolved) > 32 or any(not (character.isalnum() or character in ".-") for character in resolved):
        raise ValueError("instrument is invalid")
    return validated, resolved


def _aware_datetime(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("due_at must be an ISO timestamp")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("due_at must include a timezone")
    return parsed.astimezone(UTC)


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ValueError("evidence as_of is required")


def _bounded_text(value: object, field: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()) or len(normalized) > maximum:
        raise ValueError(f"{field} must be bounded text")
    if any(ord(character) < 32 for character in normalized):
        raise ValueError(f"{field} contains control characters")
    return normalized


def _fingerprint(value: object) -> str:
    serialized = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _result(
    *,
    result: str,
    observed_value: float | None,
    unit: str | None,
    as_of: str | None,
    evidence: list[dict[str, object]],
    fingerprint: str,
    reason: str | None,
) -> dict[str, object]:
    return {
        "result": result,
        "observed_value": observed_value,
        "unit": unit,
        "as_of": as_of,
        "evidence": evidence,
        "evidence_fingerprint": fingerprint,
        "safe_reason": reason,
    }
