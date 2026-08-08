"""Untrusted worker adapter over the server-owned Alpha run service.

``ResearchRunWorkerAdapter`` is a replaceable, untrusted wrapper around the
research run service.  It accepts only server-issued run ID/token, expected
transition version, bounded stage/candidate metadata, bounded progress deltas,
and an idempotency key.  Every callback must supply the opaque server token
plus the expected ``transition_version``; a stale or invalid token/version pair
produces no event, candidate, checkpoint, or progress side effect (D-10,
T-45-08).

The adapter has NO policy, evaluator, provider, OOS, promotion, broker, order,
portfolio, monitor, or live-execution authority or collaborator.  It may only
request transitions, checkpoints, and progress updates through the service seam.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.research.run_service import ResearchRunService


class ResearchRunWorkerAdapter:
    """Token/version-fenced bridge from an untrusted worker to the run service.

    The adapter wraps an optional existing ``JobStore``/worker callback but
    never treats worker memory or terminal JSON files as the run ledger.  All
    authority stays with the server-owned service/repository seam (D-10).
    """

    def __init__(
        self,
        service: "ResearchRunService",
        *,
        principal: str,
        job_store: Any | None = None,
    ) -> None:
        self._service = service
        self._principal = principal
        self._job_store = job_store  # replaceable bookkeeping; never authority

    def report_progress(
        self,
        *,
        run_id: str,
        expected_version: int,
        attempt_token: str | None,
        candidate_attempts_total: int | None = None,
        candidate_attempts_completed: int | None = None,
        folds_total: int | None = None,
        folds_completed: int | None = None,
    ) -> dict[str, Any] | None:
        """Request a bounded progress update through the service seam.

        Requires a valid attempt token plus expected transition version.  A
        stale/invalid token or version fails closed — no counter is updated
        (D-10, D-11, T-45-08).
        """
        if not attempt_token:
            raise ValueError("attempt_token is required for worker callbacks")
        return self._service.update_progress(
            run_id,
            principal=self._principal,
            expected_version=expected_version,
            attempt_token=attempt_token,
            candidate_attempts_total=candidate_attempts_total,
            candidate_attempts_completed=candidate_attempts_completed,
            folds_total=folds_total,
            folds_completed=folds_completed,
        )

    def request_transition(
        self,
        *,
        run_id: str,
        expected_version: int,
        attempt_token: str | None,
        to_status: str,
        terminal_reason: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any] | None:
        """Request a lifecycle transition through the service seam.

        Requires a valid attempt token plus expected transition version.  The
        adapter cannot choose an illegal edge, mutate frozen inputs, bypass
        idempotency, or grant execution/promotion authority (D-10).
        """
        if not attempt_token:
            raise ValueError("attempt_token is required for worker callbacks")
        run = self._service.get(run_id, principal=self._principal)
        if run is None:
            return None
        # Verify token + version before requesting any transition.
        if not self._service._validate_attempt_token(
            run_id, principal=self._principal,
            expected_version=expected_version, attempt_token=attempt_token,
        ):
            return None
        from_status = run["status"]
        return self._service.transition(
            run_id,
            principal=self._principal,
            from_status=from_status,
            to_status=to_status,
            expected_version=expected_version,
            terminal_reason=terminal_reason,
            idempotency_key=idempotency_key,
        )

    def recover_running(
        self,
        *,
        run_id: str,
        attempt_token: str,
        expected_version: int,
        idempotency_key: str | None = None,
    ) -> dict[str, Any] | None:
        """Request server-owned orphan recovery; no stored digest is reversed."""
        return self._service.recover_running_attempt(
            run_id, principal=self._principal, expected_version=expected_version,
            idempotency_key=idempotency_key,
        )

    def append_checkpoint(
        self,
        *,
        run_id: str,
        attempt_token: str,
        expected_version: int,
        checkpoint: dict[str, Any],
        referenced_candidate_ids: list[str] | None = None,
        inline_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Append through the service-owned validation and attempt fence."""
        if not attempt_token:
            return None
        return self._service.append_checkpoint(
            run_id=run_id, principal=self._principal, checkpoint=checkpoint,
            referenced_candidate_ids=referenced_candidate_ids or [],
            inline_summary=inline_summary, expected_version=expected_version,
            attempt_token=attempt_token,
        )
