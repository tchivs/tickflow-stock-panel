"""Deterministic, evidence-gated signal lifecycle proposals."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.analysis.repository import AnalysisRepository


_PROPOSABLE_STATES = frozenset({"strengthened", "weakened", "falsified", "priced_in"})


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


class LifecycleRuleService:
    """Create reviewable suggestions without granting them lifecycle authority."""

    def __init__(self, *, repository: AnalysisRepository, rule_version: str = "lifecycle-v1") -> None:
        self._repository = repository
        self._rule_version = rule_version

    def propose(
        self,
        *,
        subject_key: str,
        prior_state: str,
        next_state: str,
        evidence: Sequence[Mapping[str, Any]],
        invalidation_conditions: Sequence[str] = (),
        subject_kind: str = "instrument",
    ) -> dict[str, Any] | None:
        """Return an immutable proposal only when server-owned evidence meets its gate."""
        if next_state not in _PROPOSABLE_STATES or not subject_key or not prior_state:
            return None
        if self._repository.current_lifecycle_state(subject_kind=subject_kind, subject_key=subject_key) != prior_state:
            return None
        frozen_evidence = [dict(item) for item in evidence if isinstance(item, Mapping)]
        if not frozen_evidence or not self._eligible(next_state, frozen_evidence, invalidation_conditions):
            return None
        evidence_ids = [item.get("id") for item in frozen_evidence]
        if any(not isinstance(identifier, str) or not identifier.strip() for identifier in evidence_ids):
            return None
        occurred_at = [item.get("occurred_at") for item in frozen_evidence if isinstance(item.get("occurred_at"), str)]
        recorded_at = _timestamp()
        return self._repository.append_lifecycle_proposal(
            subject_kind=subject_kind,
            subject_key=subject_key,
            prior_state=prior_state,
            proposed_state=next_state,
            evidence={
                "evidence_ids": evidence_ids,
                "evidence": frozen_evidence,
                "rule_version": self._rule_version,
                "rationale": f"{next_state} threshold satisfied by frozen server evidence",
                "occurred_at": min(occurred_at) if occurred_at else recorded_at,
                "recorded_at": recorded_at,
            },
        )

    @staticmethod
    def _eligible(
        next_state: str, evidence: Sequence[dict[str, Any]], invalidation_conditions: Sequence[str]
    ) -> bool:
        attributable = [item for item in evidence if item.get("attributable", True) is not False]
        if next_state in {"strengthened", "weakened"}:
            return bool(attributable)
        if next_state == "falsified":
            has_condition = any(isinstance(condition, str) and condition.strip() for condition in invalidation_conditions)
            has_independent_contradiction = any(
                item.get("independent_contradiction") is True for item in attributable
            )
            return has_condition or has_independent_contradiction
        return any(
            isinstance(item.get("price_context"), str)
            and item["price_context"].strip()
            and isinstance(item.get("event_context"), str)
            and item["event_context"].strip()
            for item in attributable
        )
