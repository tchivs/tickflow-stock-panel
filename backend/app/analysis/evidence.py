"""Deterministic, read-only preparation of governed analysis evidence."""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
from typing import Any, Iterable, Mapping

from pydantic import BaseModel

from app.analysis.schemas import (
    FrozenEvidenceSnapshot,
    FrozenEvidenceSource,
    MaterialNumberObservation,
    TruncatedProvenance,
)


_GRADE_BY_ORIGIN = {
    "exchange-filing": "A",
    "regulatory-filing": "A",
    "audited-financials": "A",
    "issuer-presentation": "B",
    "governed-market-data": "B",
    "media-summary": "C",
}


def _mapping(record: Mapping[str, Any] | BaseModel) -> Mapping[str, Any]:
    if isinstance(record, BaseModel):
        return record.model_dump(mode="python")
    if isinstance(record, Mapping):
        return record
    raise ValueError("governed evidence record must be a mapping")


def _text(record: Mapping[str, Any], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"governed evidence {field} is required")
    return value.strip()


def _date_value(record: Mapping[str, Any], field: str) -> date | datetime:
    value = record.get(field)
    if isinstance(value, (date, datetime)):
        return value
    raise ValueError(f"governed evidence {field} is required")


def _unit(value: str) -> str:
    return "_".join(value.strip().replace("/", "_").split()).replace("__", "_")


def _definition(value: str) -> str:
    return "_".join(value.strip().lower().replace("-", " ").split())


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


class EvidencePreparationService:
    """Freeze governed records and fail closed when comparison support is absent."""

    def __init__(self, *, policy_version: str = "evidence-v1") -> None:
        if not policy_version.strip():
            raise ValueError("evidence policy_version is required")
        self.policy_version = policy_version

    def freeze(
        self,
        *,
        subject_key: str,
        records: Iterable[Mapping[str, Any] | BaseModel],
    ) -> FrozenEvidenceSnapshot:
        """Create a hash-addressed snapshot without retaining raw source content."""
        if not isinstance(subject_key, str) or not subject_key.strip():
            raise ValueError("analysis subject_key is required")
        normalized = [self._normalize(_mapping(record)) for record in records]
        if not normalized:
            return FrozenEvidenceSnapshot(
                subject_key=subject_key.strip(),
                policy_version=self.policy_version,
                context_status="context_insufficient",
                evidence_fingerprint=_fingerprint({"subject_key": subject_key.strip(), "policy": self.policy_version}),
            )

        normalized.sort(key=lambda item: item["source"].source_id)
        sources = tuple(item["source"] for item in normalized)
        material_numbers = tuple(self._number_observation(item, normalized) for item in normalized)
        serializable = {
            "subject_key": subject_key.strip(),
            "policy_version": self.policy_version,
            "sources": [source.model_dump(mode="json") for source in sources],
            "material_numbers": [number.model_dump(mode="json") for number in material_numbers],
        }
        return FrozenEvidenceSnapshot(
            subject_key=subject_key.strip(),
            policy_version=self.policy_version,
            context_status="ready",
            sources=sources,
            material_numbers=material_numbers,
            evidence_fingerprint=_fingerprint(serializable),
        )

    def _normalize(self, record: Mapping[str, Any]) -> dict[str, Any]:
        origin = _text(record, "origin").lower()
        source_id = _text(record, "source_id")
        value = record.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("governed evidence value must be numeric")
        retrieved_at = _date_value(record, "retrieved_at")
        if isinstance(retrieved_at, date) and not isinstance(retrieved_at, datetime):
            retrieved_at = datetime.combine(retrieved_at, datetime.min.time(), tzinfo=timezone.utc)
        as_of = _date_value(record, "as_of")
        if isinstance(as_of, datetime):
            as_of = as_of.date()
        raw_content = record.get("content")
        content_hash = sha256(str(raw_content).encode("utf-8")).hexdigest() if raw_content is not None else None
        source = FrozenEvidenceSource(
            source_id=source_id,
            grade=_GRADE_BY_ORIGIN.get(origin, "C"),
            origin=origin,
            independence_group=_text(record, "independence_group").lower(),
            retrieved_at=retrieved_at,
            as_of=as_of,
            period=_text(record, "period"),
            unit=_unit(_text(record, "unit")),
            definition=_definition(_text(record, "definition")),
            provenance=TruncatedProvenance(
                source_locator=str(record.get("source_locator") or source_id),
                content_sha256=content_hash,
                truncated=True,
                truncation_reason="raw_governed_content_excluded" if raw_content is not None else None,
            ),
        )
        return {"source": source, "value": float(value), "number_id": str(record.get("number_id") or source.definition)}

    @staticmethod
    def _number_observation(item: Mapping[str, Any], all_items: list[dict[str, Any]]) -> MaterialNumberObservation:
        source: FrozenEvidenceSource = item["source"]
        peers = [
            candidate for candidate in all_items
            if candidate["number_id"] == item["number_id"]
            and candidate["source"].source_id != source.source_id
            and candidate["source"].independence_group != source.independence_group
        ]
        peer_ids = tuple(sorted(candidate["source"].source_id for candidate in peers))
        if not peers:
            status, reason = "unresolved", "no_independent_peer"
        elif any(
            candidate["source"].unit != source.unit
            or candidate["source"].period != source.period
            or candidate["source"].definition != source.definition
            for candidate in peers
        ):
            status, reason = "unresolved", "unit_period_or_definition_mismatch"
        elif any(candidate["value"] != item["value"] for candidate in peers):
            status, reason = "conflicting", "independent_values_conflict"
        else:
            status, reason = "confirmed", None
        return MaterialNumberObservation(
            number_id=item["number_id"],
            source_id=source.source_id,
            value=item["value"],
            unit=source.unit,
            period=source.period,
            definition=source.definition,
            status=status,
            peer_source_ids=peer_ids,
            comparison_reason=reason,
        )
