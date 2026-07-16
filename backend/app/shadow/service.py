"""Research-only Shadow workflow orchestration and retention authority."""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Protocol

from app.shadow.evaluation import ShadowEvaluationService


class ShadowRetentionError(ValueError):
    """A candidate lacks canonical immutable evidence required for retention."""


class ShadowWorkflowRepository(Protocol):
    def get_candidate(self, candidate_id: str) -> dict[str, object] | None: ...

    def get_evidence_set(self, evidence_set_id: str) -> dict[str, object] | None: ...

    def get_evaluation(self, evaluation_id: str) -> dict[str, object] | None: ...

    def append_retention_event(self, payload: dict[str, object]) -> dict[str, object]: ...


class ShadowService:
    """Coordinate immutable Shadow facts without any completed-v1 action dependency."""

    def __init__(
        self,
        *,
        repository: ShadowWorkflowRepository,
        evaluation_service: ShadowEvaluationService,
    ) -> None:
        self.repository = repository
        self.evaluation_service = evaluation_service

    def retain_candidate(
        self,
        *,
        candidate_id: str,
        evidence_set_id: str,
        in_sample_evaluation_id: str,
        out_of_sample_evaluation_id: str,
        reviewer_principal: str,
        rationale: str,
    ) -> dict[str, object]:
        candidate_key = self._text(candidate_id, "candidate identifier", 128)
        evidence_key = self._text(evidence_set_id, "evidence identifier", 128)
        in_sample_key = self._text(
            in_sample_evaluation_id, "in-sample evaluation identifier", 128
        )
        out_of_sample_key = self._text(
            out_of_sample_evaluation_id, "out-of-sample evaluation identifier", 128
        )
        if in_sample_key == out_of_sample_key:
            raise ShadowRetentionError("retention requires two independent evaluations")
        principal = self._text(reviewer_principal, "reviewer principal", 128)
        reason = self._text(rationale, "retention rationale", 4_000)
        if len(reason) < 10:
            raise ShadowRetentionError("retention rationale is too short")

        # These are canonical repository reloads, not browser-provided snapshots.  The
        # concrete repository repeats the checks inside its append transaction so a
        # stale request cannot race a different persisted identity.
        candidate = self.repository.get_candidate(candidate_key)
        evidence = self.repository.get_evidence_set(evidence_key)
        in_sample = self.repository.get_evaluation(in_sample_key)
        out_of_sample = self.repository.get_evaluation(out_of_sample_key)
        self._require_eligible(
            candidate=candidate,
            evidence=evidence,
            in_sample=in_sample,
            out_of_sample=out_of_sample,
            candidate_id=candidate_key,
            evidence_set_id=evidence_key,
        )

        return self.repository.append_retention_event(
            {
                "candidate_id": candidate_key,
                "evidence_set_id": evidence_key,
                "evidence_set_fingerprint": str(evidence["fingerprint"]),
                "in_sample_evaluation_id": in_sample_key,
                "out_of_sample_evaluation_id": out_of_sample_key,
                "reviewer_principal": principal,
                "rationale": reason,
            }
        )

    @staticmethod
    def _require_eligible(
        *,
        candidate: Mapping[str, object] | None,
        evidence: Mapping[str, object] | None,
        in_sample: Mapping[str, object] | None,
        out_of_sample: Mapping[str, object] | None,
        candidate_id: str,
        evidence_set_id: str,
    ) -> None:
        if candidate is None or evidence is None or in_sample is None or out_of_sample is None:
            raise ShadowRetentionError("canonical Shadow retention evidence is unavailable")
        fingerprint = evidence.get("fingerprint")
        if (
            candidate.get("id") != candidate_id
            or candidate.get("evidence_set_id") != evidence_set_id
            or candidate.get("evidence_set_fingerprint") != fingerprint
        ):
            raise ShadowRetentionError("candidate evidence attribution is invalid")
        for evaluation, split_kind in (
            (in_sample, "in_sample"),
            (out_of_sample, "out_of_sample"),
        ):
            if (
                evaluation.get("candidate_id") != candidate_id
                or evaluation.get("evidence_set_id") != evidence_set_id
                or evaluation.get("evidence_set_fingerprint") != fingerprint
                or evaluation.get("split_kind") != split_kind
                or evaluation.get("status") != "passed"
                or not isinstance(evaluation.get("metrics"), Mapping)
            ):
                raise ShadowRetentionError(
                    "retention requires canonical passing IS and OOS evaluations"
                )
        in_window = ShadowService._window(in_sample.get("window"))
        out_window = ShadowService._window(out_of_sample.get("window"))
        if in_window[1] >= out_window[0]:
            raise ShadowRetentionError("retention evaluation windows overlap")
        if in_sample.get("governed_fingerprint") == out_of_sample.get(
            "governed_fingerprint"
        ):
            raise ShadowRetentionError("retention requires independently frozen inputs")

    @staticmethod
    def _window(value: object) -> tuple[date, date]:
        if not isinstance(value, Mapping):
            raise ShadowRetentionError("retention evaluation window is invalid")
        start, end = value.get("start"), value.get("end")
        if not isinstance(start, str) or not isinstance(end, str):
            raise ShadowRetentionError("retention evaluation window is invalid")
        try:
            start_date, end_date = date.fromisoformat(start), date.fromisoformat(end)
        except ValueError as error:
            raise ShadowRetentionError("retention evaluation window is invalid") from error
        if start_date > end_date:
            raise ShadowRetentionError("retention evaluation window is invalid")
        return start_date, end_date

    @staticmethod
    def _text(value: object, field: str, maximum: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
            raise ShadowRetentionError(f"{field} is invalid")
        return value.strip()
