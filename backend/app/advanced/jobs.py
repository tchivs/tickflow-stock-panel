"""Durable advanced-job creation and just-in-time authorization revalidation."""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import uuid4

from pydantic import ValidationError

from app.advanced.authorization import AdvancedAuthorizationService
from app.advanced.repository import AdvancedRepository
from app.advanced.schemas import AuthorizationTaskRequest


class WorkInvoker(Protocol):
    def __call__(self, **kwargs: object) -> None: ...


class AdvancedWorkflow(Protocol):
    async def ainvoke(self, state: dict[str, object], config: dict[str, object]) -> dict[str, object]: ...


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
        workflow: AdvancedWorkflow | None = None,
        progress_publisher: Callable[..., None] | None = None,
    ) -> None:
        self._repository = repository
        self._authorization = authorization_service
        self._provider = provider
        self._sandbox = sandbox
        self._clock = clock
        self._workflow = workflow
        self._progress_publisher = progress_publisher
        self._before_execution_hook: Callable[[dict[str, object]], None] | None = None

    def set_workflow(self, workflow: AdvancedWorkflow) -> None:
        self._workflow = workflow

    def set_progress_publisher(self, publisher: Callable[..., None]) -> None:
        self._progress_publisher = publisher

    def set_before_execution_hook(self, hook: Callable[[dict[str, object]], None]) -> None:
        """Install a deployment-owned lifecycle hook before execution-start revalidation."""
        self._before_execution_hook = hook

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

    def create_session_bound_job(self, *, principal: str, task_type: str, instrument: str) -> dict[str, object]:
        """Start a task from server-held session authority, never a browser token."""
        authorization = self._authorization.issue(
            principal=principal,
            task_types={task_type},
            markets={"CN-A"},
            instruments={instrument},
            expires_in=timedelta(minutes=5),
        )
        return self.create_job(
            principal=principal,
            request={
                "authorization_token": authorization["token"],
                "task_type": task_type,
                "market": "CN-A",
                "instrument": instrument,
                "idempotency_key": str(uuid4()),
            },
        )

    def prepare_to_start(self, *, job_id: str) -> dict[str, object]:
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
            rejected, _audit = self._repository.transition_job_with_audit(
                job_id=job_id,
                from_status=str(job["status"]),
                to_status="rejected",
                stage="rejected",
                decision="rejected",
                reason=reason,
                authorization_id=str(job["authorization_id"]),
                rejection_reason=reason,
            )
            self._publish(rejected)
            return rejected

        transitioned = self._advance(
            job_id=job_id,
            from_status=str(job["status"]),
            to_status="authorized",
            stage="authorized",
            reason="workflow_authorized",
        )
        return transitioned

    def run(self, *, job_id: str) -> dict[str, object]:
        """Legacy synchronous provider seam retained for existing focused contracts."""
        transitioned = self.prepare_to_start(job_id=job_id)
        if transitioned["status"] == "rejected":
            return transitioned
        self._provider(job_id=job_id, task_type=transitioned["task_type"])
        return transitioned

    async def run_authorized_job(self, *, job_id: str) -> dict[str, object]:
        """Revalidate and run the fixed server-bound workflow exactly once per job."""
        existing = self._repository.get_job(job_id)
        if existing is None:
            raise ValueError("advanced job is unknown")
        if existing["status"] != "queued":
            return existing
        if self._before_execution_hook is not None:
            self._before_execution_hook(existing)
        prepared = self.prepare_to_start(job_id=job_id)
        if prepared["status"] == "rejected":
            return prepared
        if self._workflow is None:
            return self._reject_after_failure(prepared, "workflow_unavailable")
        try:
            result = await self._workflow.ainvoke(
                {
                    "job_id": str(prepared["id"]),
                    "authorization_id": str(prepared["authorization_id"]),
                    "subject_ref": f"{prepared['subject_kind']}:{prepared['subject_key']}",
                },
                {"configurable": {"thread_id": f"advanced-job-{prepared['id']}"}},
            )
            if result.get("__interrupt__"):
                return self._advance(
                    job_id=job_id,
                    from_status="gates_complete",
                    to_status="awaiting_review",
                    stage="awaiting_review",
                    reason="workflow_awaiting_review",
                )
            return self._repository.get_job(job_id) or prepared
        except Exception:
            latest = self._repository.get_job(job_id) or prepared
            return self._reject_after_failure(latest, "workflow_failed")

    def advance_workflow_stage(self, *, job_id: str, from_status: str, to_status: str, stage: str) -> dict[str, object]:
        return self._advance(job_id=job_id, from_status=from_status, to_status=to_status, stage=stage, reason=f"workflow_{stage}")

    def record_workflow_outcome(self, *, job_id: str, outcome_type: str) -> dict[str, object]:
        current = self._repository.get_job(job_id)
        if current is None:
            raise ValueError("advanced job is unknown")
        if outcome_type == "rejected":
            return self._advance(job_id=job_id, from_status=str(current["status"]), to_status="rejected", stage="rejected", reason="workflow_rejected", decision="rejected")
        return self._advance(job_id=job_id, from_status=str(current["status"]), to_status="recorded", stage="recorded", reason="workflow_recorded", decision="recorded")

    def get_job(self, job_id: str) -> dict[str, object] | None:
        return self._repository.get_job(job_id)

    def get_job_by_audit_reference(self, reference: str) -> dict[str, object] | None:
        return self._repository.get_job_by_audit_reference(reference)

    def get_audit(self, reference: str) -> dict[str, object] | None:
        return self._repository.get_security_audit(reference)

    def _advance(self, *, job_id: str, from_status: str, to_status: str, stage: str, reason: str, decision: str = "authorized") -> dict[str, object]:
        current = self._repository.get_job(job_id)
        if current is None:
            raise ValueError("advanced job is unknown")
        job, _audit = self._repository.transition_job_with_audit(
            job_id=job_id,
            from_status=from_status,
            to_status=to_status,
            stage=stage,
            decision=decision,
            reason=reason,
            authorization_id=str(current["authorization_id"]),
            rejection_reason=reason if decision == "rejected" else None,
        )
        self._publish(job)
        return job

    def _reject_after_failure(self, job: dict[str, object], reason: str) -> dict[str, object]:
        if job["status"] in {"recorded", "rejected"}:
            return job
        return self._advance(job_id=str(job["id"]), from_status=str(job["status"]), to_status="rejected", stage="rejected", reason=reason, decision="rejected")

    def _publish(self, job: dict[str, object]) -> None:
        if self._progress_publisher is None:
            return
        self._progress_publisher(
            job_id=str(job["id"]), subject_kind=str(job["subject_kind"]), subject_key=str(job["subject_key"]),
            stage=str(job["stage"]), occurred_at=str(job["stage_recorded_at"]), committed=True,
            human_label=f"Advanced job {job['stage']}", audit_reference=job.get("audit_reference") if isinstance(job.get("audit_reference"), str) else None,
        )

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
