"""Governed source-specific evidence resolution for Thesis conditions."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
import math
from pathlib import Path
import sqlite3
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import polars as pl
from pydantic import ValidationError

from app.theses.conditions import ConditionEvaluator
from app.theses.schemas import (
    ANALYSIS_FIELDS,
    FINANCIAL_FIELDS,
    MARKET_FIELDS,
    EvidenceFact,
    EvidenceStatus,
    ThesisCondition,
)


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


class GovernedMarketReader:
    """Read one allowlisted daily fact from the existing governed K-line repository."""

    def __init__(self, *, repository: Any) -> None:
        self._repository = repository

    def assert_ready(self) -> None:
        if not callable(getattr(self._repository, "get_daily", None)):
            raise RuntimeError("governed market reader is unavailable")

    def __call__(
        self, *, instrument: str, field: str, as_of: date, lookback_days: int
    ) -> Mapping[str, object] | None:
        _reader_request(instrument, field, as_of, lookback_days, MARKET_FIELDS)
        frame = self._repository.get_daily(
            instrument,
            as_of - timedelta(days=lookback_days),
            as_of,
            columns=["date", field],
        )
        if frame is None or frame.is_empty() or not {"date", field}.issubset(frame.columns):
            return None
        rows = (
            frame.select("date", field)
            .drop_nulls()
            .sort("date", descending=True)
            .head(1)
            .to_dicts()
        )
        if not rows:
            return None
        row = rows[0]
        observed = _finite_number(row[field])
        observed_at = _as_date(row["date"])
        return _governed_fact(
            source_id=f"governed-market:{instrument}:{observed_at.isoformat()}:{field}",
            source_payload={
                "source": "governed-market",
                "instrument": instrument,
                "field": field,
                "value": observed,
                "as_of": observed_at.isoformat(),
            },
            value=observed,
            unit=_single_unit(MARKET_FIELDS[field]),
            as_of=observed_at,
        )


class GovernedFinancialReader:
    """Read one allowlisted financial metric through a pushed-down bounded lake scan."""

    def __init__(self, *, data_root: Path) -> None:
        self._data_root = Path(data_root)
        self._metrics_path = self._data_root / "financials" / "metrics" / "part.parquet"

    def assert_ready(self) -> None:
        if not self._data_root.is_dir():
            raise RuntimeError("governed financial reader is unavailable")
        if self._metrics_path.exists():
            pl.scan_parquet(self._metrics_path).collect_schema()

    def __call__(
        self, *, instrument: str, field: str, as_of: date, lookback_days: int
    ) -> Mapping[str, object] | None:
        _reader_request(instrument, field, as_of, lookback_days, FINANCIAL_FIELDS)
        if not self._metrics_path.is_file():
            return None
        scan = pl.scan_parquet(self._metrics_path)
        names = set(scan.collect_schema().names())
        period_field = next(
            (candidate for candidate in ("report_date", "period", "end_date", "date") if candidate in names),
            None,
        )
        if period_field is None or not {"symbol", field}.issubset(names):
            return None
        period = pl.col(period_field).cast(pl.Date, strict=False)
        value = pl.col(field).cast(pl.Float64, strict=False)
        frame = (
            scan.filter(
                (pl.col("symbol") == instrument)
                & period.is_between(as_of - timedelta(days=lookback_days), as_of, closed="both")
                & value.is_finite()
            )
            .select(period.alias("as_of"), value.alias("value"))
            .sort("as_of", descending=True)
            .head(1)
            .collect()
        )
        if frame.is_empty():
            return None
        row = frame.to_dicts()[0]
        observed = _finite_number(row["value"])
        observed_at = _as_date(row["as_of"])
        return _governed_fact(
            source_id=f"governed-financial:metrics:{instrument}:{observed_at.isoformat()}:{field}",
            source_payload={
                "source": "governed-financial-metrics",
                "instrument": instrument,
                "field": field,
                "value": observed,
                "as_of": observed_at.isoformat(),
            },
            value=observed,
            unit=_single_unit(FINANCIAL_FIELDS[field]),
            as_of=observed_at,
        )


class GovernedAnalysisReader:
    """Read the latest immutable analysis score with one bounded operational query."""

    def __init__(self, *, database_path: Path) -> None:
        self._database_path = Path(database_path)

    def assert_ready(self) -> None:
        if not self._database_path.is_file():
            raise RuntimeError("governed analysis reader is unavailable")
        with sqlite3.connect(self._database_path) as connection:
            table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'analysis_reports'"
            ).fetchone()
        if table is None:
            raise RuntimeError("governed analysis reader is unavailable")

    def __call__(
        self, *, instrument: str, field: str, as_of: date, lookback_days: int
    ) -> Mapping[str, object] | None:
        _reader_request(instrument, field, as_of, lookback_days, ANALYSIS_FIELDS)
        earliest = as_of - timedelta(days=lookback_days)
        with sqlite3.connect(self._database_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """SELECT id, version, report_json, created_at
                   FROM analysis_reports
                   WHERE subject_kind = 'instrument' AND subject_key = ?
                     AND date(created_at) BETWEEN ? AND ?
                   ORDER BY version DESC, created_at DESC, id DESC
                   LIMIT 1""",
                (instrument, earliest.isoformat(), as_of.isoformat()),
            ).fetchone()
        if row is None:
            return None
        report = json.loads(row["report_json"])
        if not isinstance(report, Mapping):
            raise ValueError("governed analysis report is malformed")
        generated = report.get("generated")
        perspectives = generated.get("perspectives") if isinstance(generated, Mapping) else None
        if not isinstance(perspectives, list) or not 2 <= len(perspectives) <= 4:
            raise ValueError("governed analysis report is malformed")
        scores = [
            _finite_number(item.get("score"))
            for item in perspectives
            if isinstance(item, Mapping)
        ]
        if len(scores) != len(perspectives) or any(not 0 <= score <= 100 for score in scores):
            raise ValueError("governed analysis report is malformed")
        observed = sum(scores) / len(scores)
        observed_at = _as_date(row["created_at"])
        return _governed_fact(
            source_id=f"analysis-report:{row['id']}:report_score",
            source_payload={
                "source": "immutable-analysis-report",
                "report_id": row["id"],
                "version": row["version"],
                "instrument": instrument,
                "field": field,
                "value": observed,
                "as_of": observed_at.isoformat(),
            },
            value=observed,
            unit=_single_unit(ANALYSIS_FIELDS[field]),
            as_of=observed_at,
        )


def _reader_request(
    instrument: str,
    field: str,
    as_of: date,
    lookback_days: int,
    allowed_fields: Mapping[str, object],
) -> None:
    if not isinstance(instrument, str) or not instrument or len(instrument) > 32:
        raise ValueError("governed instrument is invalid")
    if any(not (character.isalnum() or character in ".-") for character in instrument):
        raise ValueError("governed instrument is invalid")
    if field not in allowed_fields:
        raise ValueError("governed field is invalid")
    if not isinstance(as_of, date) or isinstance(as_of, datetime):
        raise ValueError("governed as_of is invalid")
    if isinstance(lookback_days, bool) or not isinstance(lookback_days, int) or not 1 <= lookback_days <= 3660:
        raise ValueError("governed lookback is invalid")


def _finite_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("governed value is malformed")
    return float(value)


def _single_unit(units: object) -> str:
    if not isinstance(units, frozenset) or len(units) != 1:
        raise RuntimeError("governed unit contract is invalid")
    return next(iter(units))


def _governed_fact(
    *,
    source_id: str,
    source_payload: Mapping[str, object],
    value: float,
    unit: str,
    as_of: date,
) -> dict[str, object]:
    return {
        "source_id": _bounded_text(source_id, "source_id", maximum=256),
        "source_revision": _fingerprint(source_payload),
        "value": value,
        "unit": unit,
        "as_of": as_of,
    }


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
            due = _aware_datetime(due_at).astimezone(ZoneInfo(validated_condition.timezone))
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
                "instrument": resolved_instrument,
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
    else:
        validated = ThesisCondition.model_validate(dict(condition))
    candidate = instrument
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
    return parsed


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
