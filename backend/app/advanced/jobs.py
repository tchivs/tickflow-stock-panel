"""Durable advanced-job creation and just-in-time authorization revalidation."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from pydantic import ValidationError

from app.advanced.authorization import AdvancedAuthorizationService
from app.advanced.repository import AdvancedRepository
from app.advanced.schemas import AuthorizationTaskRequest


class WorkInvoker(Protocol):
    def __call__(self, **kwargs: object) -> None: ...


class AdvancedJobService:
    """Creates jobs only after authorization and rechecks before invoking work."""

    def __init__(
        self,
        *,
        repository: AdvancedRepository,
        authorization_service: AdvancedAuthorizationService,
        provider: WorkInvoker,
        sandbox: WorkInvoker,
        clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._authorization = authorization_service
        self._provider = provider
        self._sandbox = sandbox
        self._clock = clock

    def create_job(self, *, principal: str, request: dict[str, object]) -> dict[str, object]:
        authorization_id: str | None = None
        try:
            parsed = AuthorizationTaskRequest.model_validate(request)
            record = self._authorization.validate_token(
                token=parsed.authorization_token,
                principal=principal,
                task_type=parsed.task_type,
                market=parsed.market,
                instrument=parsed.instrument,
            )
            authorization_id = str(record["id"])
            policy = self._authorization.current_policy()
            policy_record = self._repository.record_policy_revision(
                revision=policy.revision,
                fingerprint=policy.fingerprint,
                snapshot=policy.snapshot(),
            )
            job = self._repository.acquire_authorized_job(
                job_id=str(uuid4()),
                authorization_id=authorization_id,
                principal=principal,
                subject_kind="instrument",
                subject_key=parsed.instrument,
                task_type=parsed.task_type,
                market=parsed.market,
                instrument=parsed.instrument,
                idempotency_key=parsed.idempotency_key,
                policy_revision_id=str(policy_record["id"]),
                quota=policy.quota_per_window,
                now=self._now().isoformat(),
            )
            if job is None:
                raise ValueError("quota exhausted")
            return job
        except (ValidationError, ValueError) as error:
            reason = self._safe_reason(error)
            self._repository.append_security_audit(
                decision="rejected", reason=reason, authorization_id=authorization_id
            )
            raise ValueError(reason.replace("_", " ")) from error

    def run(self, *, job_id: str) -> dict[str, object]:
        job = self._repository.get_job(job_id)
        if job is None:
            raise ValueError("advanced job is unknown")
        try:
            self._authorization.validate_record(
                record=self._repository.get_authorization(str(job["authorization_id"])) or {},
                principal=str(job["principal"]),
                task_type=str(job["task_type"]),
                market=str(job["market"]),
                instrument=str(job["instrument"]),
            )
            policy = self._authorization.current_policy()
            if not self._repository.quota_is_current(
                principal=str(job["principal"]), quota=policy.quota_per_window, now=self._now().isoformat()
            ):
                raise ValueError("quota exhausted")
        except ValueError as error:
            reason = self._safe_reason(error)
            audit = self._repository.append_security_audit(
                decision="rejected", reason=reason, authorization_id=str(job["authorization_id"]), job_id=job_id
            )
            return self._repository.transition_job(
                job_id=job_id,
                from_status=str(job["status"]),
                to_status="rejected",
                stage="rejected",
                rejection_reason=reason,
                audit_reference=str(audit["reference"]),
            )

        transitioned = self._repository.transition_job(
            job_id=job_id,
            from_status=str(job["status"]),
            to_status="authorized",
            stage="authorized",
        )
        self._provider(job_id=job_id, task_type=transitioned["task_type"])
        return transitioned

    def _now(self) -> datetime:
        return self._clock().astimezone(UTC)

    @staticmethod
    def _safe_reason(error: Exception) -> str:
        if isinstance(error, ValidationError):
            fields = {str(item["loc"][-1]) for item in error.errors()}
            if "task_type" in fields:
                return "task_type_denied"
            if {"market", "instrument"} & fields:
                return "scope_denied"
            if fields - {"authorization_token", "idempotency_key"}:
                return "client_authority_denied"
        message = str(error).lower()
        if "revoked" in message:
            return "authorization_revoked"
        if "expired" in message:
            return "authorization_expired"
        if "quota" in message or "rate" in message:
            return "quota_exhausted"
        if "task type" in message:
            return "task_type_denied"
        if "scope" in message:
            return "scope_denied"
        if "extra" in message or "authority" in message:
            return "client_authority_denied"
        return "authorization_denied"
