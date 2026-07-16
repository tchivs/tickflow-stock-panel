"""Server-authoritative Thesis checks, pending conclusions, and human reviews."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
import json
from typing import Any

from app.theses import projections
from app.theses.schemas import ConditionCheckResult, ThesisRevisionRequest, ThesisVersionRequest


class ThesisConflictError(ValueError):
    """A typed immutable-lifecycle conflict requiring the caller to refresh."""


class ThesisService:
    """Coordinate governed evidence with append-only Thesis lifecycle facts."""

    def __init__(self, *, repository: Any, evidence_resolver: Any) -> None:
        self._repository = repository
        self._evidence_resolver = evidence_resolver

    def create_version(
        self, *, request: ThesisVersionRequest, created_by: str
    ) -> dict[str, Any]:
        return self._repository.create_version(request=request, created_by=created_by)

    def revise_version(
        self,
        *,
        thesis_id: str,
        request: ThesisRevisionRequest,
        created_by: str,
    ) -> dict[str, Any]:
        return self._repository.revise_version(
            thesis_id=thesis_id,
            request=request,
            created_by=created_by,
        )

    def get_version(self, version_id: str) -> dict[str, Any] | None:
        return self._repository.get_version(version_id)

    def get_pending(self, pending_id: str) -> dict[str, Any] | None:
        return self._repository.get_pending(pending_id)

    def versions_for_instrument(self, instrument: str) -> list[dict[str, Any]]:
        current = self._repository.current_version_for_instrument(instrument)
        if current is None:
            return []
        return self._repository.list_versions(current["thesis_id"])

    def version_projection(self, record: Mapping[str, Any]) -> dict[str, Any]:
        schedules: dict[str, Mapping[str, Any] | None] = {}
        checks: dict[str, Sequence[Mapping[str, Any]]] = {}
        for condition in record["conditions"]:
            condition_id = str(condition["id"])
            schedules[condition_id] = self._repository.get_schedule(condition_id)
            checks[condition_id] = self._repository.list_checks(condition_id)
        return projections.version(record, schedules=schedules, checks=checks)

    def checks_for_instrument(self, instrument: str) -> list[dict[str, Any]]:
        checks = [
            projections.check(item)
            for version in self.versions_for_instrument(instrument)
            for condition in version["conditions"]
            for item in self._repository.list_checks(condition["id"])
        ]
        return sorted(checks, key=lambda item: (item["due_at"], item["id"]), reverse=True)

    def pending_for_instrument(self, instrument: str) -> list[dict[str, Any]]:
        current = self._repository.current_version_for_instrument(instrument)
        if current is None:
            return []
        return [
            projections.pending(
                item,
                review=(reviews[0] if (reviews := self._repository.list_review_events(item["id"])) else None),
            )
            for item in self._repository.list_pending(current["thesis_id"])
        ]

    def history_for_instrument(self, instrument: str) -> dict[str, Any] | None:
        current = self._repository.current_version_for_instrument(instrument)
        return None if current is None else self.history(current["thesis_id"])

    def evaluate_due_condition(self, *, condition_id: str, due_at: str) -> dict[str, Any]:
        """Append one canonical due check and only a matched pending conclusion."""
        canonical = self._repository.condition_outcome(condition_id, due_at)
        if canonical is not None:
            return canonical
        condition = self._repository.get_condition(condition_id)
        if condition is None:
            raise ThesisConflictError("thesis condition not found")
        current = self._repository.current_version(condition["thesis_id"])
        if current is None or current["id"] != condition["version_id"]:
            raise ThesisConflictError("old thesis version condition conflict")
        resolved = self._resolve(condition=condition, due_at=due_at)
        return self._repository.append_condition_outcome(
            condition_id=condition_id,
            due_at=due_at,
            result=resolved["result"],
            evidence_fingerprint=resolved["evidence_fingerprint"],
            evidence=resolved["evidence"],
            checked_at=self._repository.now(),
            observed_value=resolved["observed_value"],
            safe_reason=resolved["safe_reason"],
        )

    def confirm(
        self,
        *,
        pending_id: str,
        rationale: str,
        reviewer_principal: str | None,
    ) -> dict[str, Any]:
        """Revalidate governed evidence before appending one official invalidation."""
        principal = _principal(reviewer_principal)
        reason = _rationale(rationale)
        pending = self._reviewable_pending(pending_id)
        refreshed = self._resolve(condition=pending["condition"], due_at=pending["due_at"])
        if (
            refreshed["result"] != ConditionCheckResult.MATCHED.value
            or refreshed["evidence_fingerprint"] != pending["evidence_fingerprint"]
        ):
            raise ThesisConflictError("pending evidence is stale or no longer matches")
        event = self._repository.append_review_event(
            pending_id=pending_id,
            decision="confirmed",
            reviewer_principal=principal,
            rationale=reason,
        )
        return {"decision": "confirmed", "official_state": "invalidated", "event": event}

    def reject(
        self,
        *,
        pending_id: str,
        rationale: str,
        reviewer_principal: str | None,
    ) -> dict[str, Any]:
        """Append one rejection while preserving the derived official state."""
        principal = _principal(reviewer_principal)
        reason = _rationale(rationale)
        pending = self._reviewable_pending(pending_id)
        event = self._repository.append_review_event(
            pending_id=pending_id,
            decision="rejected",
            reviewer_principal=principal,
            rationale=reason,
        )
        return {
            "decision": "rejected",
            "official_state": self.official_state(pending["thesis_id"]),
            "event": event,
        }

    def official_state(self, thesis_id: str) -> str:
        current = self._repository.current_version(thesis_id)
        if current is None:
            raise ValueError("thesis not found")
        return str(current["official_state"])

    def history(self, thesis_id: str) -> dict[str, Any]:
        """Return a complete allowlisted immutable audit projection."""
        versions = self._repository.list_versions(thesis_id)
        schedules: dict[str, Mapping[str, Any] | None] = {}
        checks: dict[str, Sequence[Mapping[str, Any]]] = {}
        for version in versions:
            for condition in version["conditions"]:
                condition_id = str(condition["id"])
                schedules[condition_id] = self._repository.get_schedule(condition_id)
                checks[condition_id] = self._repository.list_checks(condition_id)
        pending_records = self._repository.list_pending(thesis_id)
        reviews = {
            str(item["id"]): self._repository.list_review_events(item["id"])
            for item in pending_records
        }
        return projections.history(
            thesis_id=thesis_id,
            official_state=self.official_state(thesis_id),
            versions=versions,
            schedules=schedules,
            checks=checks,
            pending_records=pending_records,
            reviews=reviews,
            official_events=self._repository.list_official_events(thesis_id),
        )

    def _reviewable_pending(self, pending_id: str) -> dict[str, Any]:
        pending = self._repository.get_pending(pending_id)
        if pending is None:
            raise ValueError("pending thesis conclusion not found")
        if self._repository.list_review_events(pending_id):
            raise ThesisConflictError("pending thesis conclusion already processed conflict")
        current = self._repository.current_version(pending["thesis_id"])
        if current is None or current["id"] != pending["version_id"]:
            raise ThesisConflictError("old thesis version pending conflict")
        if current["official_state"] != "active":
            raise ThesisConflictError("thesis official state changed conflict")
        return pending

    def _resolve(self, *, condition: Mapping[str, Any], due_at: str) -> dict[str, Any]:
        try:
            payload = self._evidence_resolver.resolve(condition=dict(condition), due_at=due_at)
            if not isinstance(payload, Mapping):
                raise ValueError("resolver response is invalid")
            result = ConditionCheckResult(payload.get("result")).value
            fingerprint = payload.get("evidence_fingerprint")
            if not isinstance(fingerprint, str) or len(fingerprint) != 64 or any(
                character not in "0123456789abcdef" for character in fingerprint
            ):
                raise ValueError("resolver fingerprint is invalid")
            evidence_value = payload.get("evidence", [])
            if not isinstance(evidence_value, Sequence) or isinstance(evidence_value, (str, bytes)):
                raise ValueError("resolver evidence is invalid")
            evidence = [dict(item) for item in evidence_value if isinstance(item, Mapping)]
            if len(evidence) != len(evidence_value):
                raise ValueError("resolver evidence is invalid")
            observed = payload.get("observed_value")
            if result in {ConditionCheckResult.INSUFFICIENT_EVIDENCE.value, ConditionCheckResult.ERROR.value}:
                observed = None
            safe_reason = payload.get("safe_reason")
            if safe_reason is not None and (not isinstance(safe_reason, str) or len(safe_reason) > 500):
                raise ValueError("resolver reason is invalid")
            return {
                "result": result,
                "observed_value": observed,
                "evidence_fingerprint": fingerprint,
                "evidence": evidence,
                "safe_reason": safe_reason,
            }
        except Exception:
            fingerprint = _safe_error_fingerprint(condition_id=str(condition.get("id", "")), due_at=due_at)
            return {
                "result": ConditionCheckResult.ERROR.value,
                "observed_value": None,
                "evidence_fingerprint": fingerprint,
                "evidence": [],
                "safe_reason": "governed_evidence_check_error",
            }



def _principal(value: str | None) -> str:
    if not isinstance(value, str) or not (principal := value.strip()):
        raise ValueError("authenticated reviewer principal is required")
    if len(principal) > 256:
        raise ValueError("reviewer principal exceeds its bound")
    return principal


def _rationale(value: str) -> str:
    if not isinstance(value, str) or not (reason := value.strip()):
        raise ValueError("review rationale is required")
    if len(reason) > 4_000:
        raise ValueError("review rationale exceeds its bound")
    return reason


def _safe_error_fingerprint(*, condition_id: str, due_at: str) -> str:
    payload = json.dumps(
        {"condition_id": condition_id, "due_at": due_at, "status": "error"},
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()
