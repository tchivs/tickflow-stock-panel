"""Server-owned Alpha run service: the only lifecycle writer.

``ResearchRunService`` is the policy/lifecycle owner for Phase 45 runs.  It
resolves the server principal from host context, freezes the D-04 input
snapshot, delegates the atomic snapshot/run/event transaction to the
repository, and exposes read-only replay.  It commits the durable fact and
event before returning; any optional publisher notification runs only after
commit (D-05, D-09).

The service does not import provider, factor evaluation, OOS, promotion,
broker, order, portfolio, monitor, or live-execution collaborators.
"""
from __future__ import annotations

import json
import secrets
import uuid
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from app.research.run_contract import (
    TERMINAL_STATUSES,
    attempt_token_digest,
    canonical_json,
    freeze_input_snapshot,
    validate_bounded_json,
    validate_progress_counters,
)

if TYPE_CHECKING:
    from app.research.artifacts import AlphaRunArtifactService

# Event-type mapping for each lifecycle target status (D-06).
_EVENT_TYPES: dict[str, str] = {
    "running": "run_started",
    "preflight_failed": "run_preflight_failed",
    "cancel_requested": "cancel_requested",
    "cancelled": "run_cancelled",
    "completed": "run_completed",
    "failed": "run_failed",
}


def _event_type_for(to_status: str) -> str:
    """Map a lifecycle target status to its durable event type."""
    return _EVENT_TYPES.get(to_status, f"run_{to_status}")


def _generate_attempt_token() -> str:
    """Generate an opaque server-owned attempt token (32 bytes, hex-encoded).

    Only its SHA-256 digest is persisted; the raw token is returned to the
    worker adapter and never appears in durable plaintext or projections
    (D-10, T-45-08).
    """
    return secrets.token_hex(32)

_SAFE_REASON_CODES = frozenset({
    "preflight_failed", "worker_failed", "artifact_failed", "checkpoint_invalid",
    "cancelled", "completed", "failed", "budget_exhausted",
})


def _safe_terminal_reason(reason: str | Mapping[str, Any] | None, *, status: str) -> str | None:
    """Return bounded machine-readable terminal state, never raw worker text."""
    if reason is None:
        return None
    if isinstance(reason, Mapping):
        code = reason.get("code")
        detail = reason.get("detail", "")
    else:
        code = None
        detail = reason
    code = str(code).strip() if isinstance(code, str) else ""
    if code not in _SAFE_REASON_CODES:
        code = "preflight_failed" if status == "preflight_failed" else "worker_failed"
    detail = " ".join(str(detail).split())
    # Paths, traceback-like diagnostics, and control characters never cross the boundary.
    detail = detail.replace("/", " ").replace("\\", " ")[:256]
    return canonical_json({"code": code, "detail": detail})




class AlphaRunPreflightError(ValueError):
    """A create request failed preflight (malformed/incomplete run-level input)."""


class AlphaCheckpointValidationError(ValueError):
    """A recovery checkpoint cursor failed fail-closed validation (D-07, T-45-05)."""


class ResearchRunService:
    """Server-owned create/get/replay service seam for Alpha runs."""

    def __init__(
        self,
        repository: ResearchRepository,
        *,
        publisher: "RunEventPublisher | None" = None,
        artifact_service: "AlphaRunArtifactService | None" = None,
    ) -> None:
        self._repository = repository
        self._publisher = publisher
        self._artifact_service = artifact_service

    def create(
        self,
        *,
        principal: str,
        idempotency_key: str,
        manifest: Mapping[str, Any],
        snapshot: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Freeze a server-owned snapshot and commit the queued run + event.

        Validates bounded intent, freezes the canonical D-04 snapshot, and
        delegates the atomic transaction to the repository.  A preflight
        failure (missing manifest groups, malformed input) raises
        ``AlphaRunPreflightError`` and produces no queued row.  Idempotent
        repeats return the original run; conflicting digests raise
        ``AlphaRunConflictError``.
        """
        occurred_at = self._repository._now()
        try:
            frozen = freeze_input_snapshot(
                manifest=manifest, snapshot=snapshot, created_at=occurred_at
            )
        except ValueError as error:
            raise AlphaRunPreflightError(str(error)) from error

        run_id = "arun_" + uuid.uuid4().hex
        event_id = "aevt_" + uuid.uuid4().hex
        run = self._repository.create_alpha_run(
            run_id=run_id,
            principal=principal,
            idempotency_key=idempotency_key,
            snapshot=frozen,
            event_id=event_id,
        )
        # Publisher notification runs only after the transaction commits (D-05).
        if self._publisher is not None:
            try:
                self._publisher.on_run_created(run)
            except Exception:  # noqa: BLE001
                pass  # best-effort; committed facts are not rolled back
        return run

    # ----------------------------------------------------------------
    # Lifecycle matrix and guarded transitions (D-06, T-45-06/07/12)
    # ----------------------------------------------------------------

    #: Explicit legal lifecycle edges; every other transition is rejected.
    LIFECYCLE_EDGES: dict[str, frozenset[str]] = {
        "queued": frozenset({"running", "preflight_failed", "cancel_requested", "failed"}),
        "running": frozenset({"cancel_requested", "completed", "failed"}),
        "cancel_requested": frozenset({"cancelled", "failed"}),
    }

    def _is_legal_edge(self, from_status: str, to_status: str) -> bool:
        return to_status in self.LIFECYCLE_EDGES.get(from_status, frozenset())

    def transition(
        self,
        run_id: str,
        *,
        principal: str,
        from_status: str,
        to_status: str,
        expected_version: int,
        terminal_reason: str | None = None,
        idempotency_key: str | None = None,
        extra_payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Perform one guarded lifecycle transition atomically.

        Validates the edge against the legal matrix, then delegates to the
        repository's guarded SQL update + event append.  Illegal edges raise
        ``ValueError``; stale expected-version or cross-principal access
        returns ``None`` with no side effect (D-06, T-45-06).
        """
        if not self._is_legal_edge(from_status, to_status):
            raise ValueError(
                f"illegal lifecycle transition: {from_status} -> {to_status}"
            )
        if expected_version < 0:
            raise ValueError("expected_version must be non-negative")
        key = idempotency_key or f"transition-{from_status}-{to_status}-{expected_version}"
        event_id = "aevt_" + uuid.uuid4().hex
        event_type = _event_type_for(to_status)
        safe_reason = _safe_terminal_reason(terminal_reason, status=to_status)
        result = self._repository.transition_alpha_run(
            run_id=run_id, principal=principal, from_status=from_status,
            to_status=to_status, expected_version=expected_version,
            event_id=event_id, event_type=event_type, idempotency_key=key,
            terminal_reason=safe_reason, extra_payload=extra_payload,
        )
        if result is None:
            # Distinguish unknown/cross-principal (None) from stale version/status.
            run = self._repository.get_alpha_run(run_id, principal=principal)
            if run is None:
                return None
            raise ValueError(
                "stale expected_version or run status changed; refresh and retry"
            )
        return result

    def start_or_resume(
        self,
        run_id: str,
        *,
        principal: str,
        expected_version: int,
        idempotency_key: str | None = None,
    ) -> dict[str, Any] | None:
        """Transition ``queued → running``, issuing an opaque attempt token.

        Returns the updated run row with a server-generated ``attempt_token``
        (in the ``_attempt_token`` key, for the worker adapter only) or
        ``None`` for unknown/cross-principal runs.  Only the token's SHA-256 is
        durable, embedded in the ``run_started`` event payload (D-10, T-45-08).
        A duplicate start of an already-running run returns existing running
        state without reissuing a token (D-06); a terminal run raises
        ``ValueError`` (illegal lifecycle).
        """
        from app.research.run_contract import TERMINAL_STATUSES, attempt_token_digest

        run = self._repository.get_alpha_run(run_id, principal=principal)
        if run is None:
            return None
        if run["status"] == "running":
            return run  # idempotent: already started, no new event/token
        if run["status"] in TERMINAL_STATUSES:
            raise ValueError(
                f"illegal lifecycle transition: {run['status']} -> running"
            )
        token = _generate_attempt_token()
        token_digest = attempt_token_digest(token)
        result = self.transition(
            run_id,
            principal=principal,
            from_status="queued",
            to_status="running",
            expected_version=expected_version,
            idempotency_key=idempotency_key,
            extra_payload={"attempt_token_digest": token_digest},
        )
        if result is None:
            return None
        if result.pop("_start_idempotent_replay", False):
            return result
        result["_attempt_token"] = token
        return result


    def recover_running_attempt(
        self,
        run_id: str,
        *,
        principal: str,
        expected_version: int,
        idempotency_key: str | None = None,
    ) -> dict[str, Any] | None:
        """Fence a possibly orphaned running worker and issue a fresh token.

        The old digest is never used to derive plaintext.  Recovery increments
        the durable transition version and stores only the new digest atomically.
        """
        run = self._repository.get_alpha_run(run_id, principal=principal)
        if run is None:
            return None
        if run["status"] != "running":
            raise ValueError("only a running attempt can be recovered")
        recovery_key = idempotency_key or f"recover-{expected_version}"
        existing = self._repository.get_idempotent_lifecycle_state(
            run_id, principal=principal, idempotency_key=recovery_key,
            event_type="run_recovered",
        )
        if existing is not None:
            return existing
        token = _generate_attempt_token()
        result = self._repository.recover_alpha_run(
            run_id=run_id, principal=principal, expected_version=expected_version,
            event_id="aevt_" + uuid.uuid4().hex,
            idempotency_key=recovery_key,
            token_digest=attempt_token_digest(token),
        )
        if result is None:
            return None
        if result.pop("_recovery_idempotent_replay", False):
            return result
        result["_attempt_token"] = token
        return result
    def cancel(
        self,
        run_id: str,
        *,
        principal: str,
        expected_version: int,
        idempotency_key: str | None = None,
    ) -> dict[str, Any] | None:
        """Idempotently request cooperative cancellation.

        Appends ``cancel_requested`` and transitions ``queued``/``running`` to
        ``cancel_requested``.  Terminal runs return current state with no new
        event (D-07).
        """
        run = self._repository.get_alpha_run(run_id, principal=principal)
        if run is None:
            return None
        if run["status"] in ("cancel_requested", "cancelled", "completed", "failed", "preflight_failed"):
            return run
        if run["transition_version"] != expected_version:
            raise ValueError("stale expected_version; refresh and retry")
        key = idempotency_key or f"cancel-{run['status']}-{expected_version}"
        event_id = "aevt_" + uuid.uuid4().hex
        result = self._repository.cancel_alpha_run(
            run_id=run_id,
            principal=principal,
            expected_version=expected_version,
            event_id=event_id,
            idempotency_key=key,
        )
        if result is not None and result["status"] == run["status"] and result["transition_version"] == run["transition_version"]:
            return None
        return result

    def retry(
        self,
        run_id: str,
        *,
        principal: str,
        idempotency_key: str,
        manifest: Mapping[str, Any],
        snapshot: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Create a linked child run, preserving the immutable parent.

        A retry either resumes a valid checkpoint (Phase 48) or creates a new
        linked child run with ``retry_of_run_id`` set to the parent.  The
        parent's status/facts are never mutated.  Returns ``None`` for
        unknown/cross-principal parents (D-07, T-45-12).
        """
        occurred_at = self._repository._now()
        try:
            frozen = freeze_input_snapshot(
                manifest=manifest, snapshot=snapshot, created_at=occurred_at
            )
        except ValueError as error:
            raise AlphaRunPreflightError(str(error)) from error
        child_run_id = "arun_" + uuid.uuid4().hex
        child_event_id = "aevt_" + uuid.uuid4().hex
        return self._repository.retry_alpha_run(
            run_id=run_id,
            principal=principal,
            idempotency_key=idempotency_key,
            snapshot=frozen,
            child_run_id=child_run_id,
            child_event_id=child_event_id,
        )

    def _validate_attempt_token(
        self,
        run_id: str,
        *,
        principal: str,
        expected_version: int,
        attempt_token: str | None,
    ) -> bool:
        """Validate an opaque attempt token plus expected transition version.

        Only the SHA-256 of the token is durable (in the ``run_started`` event
        payload); the raw token is never persisted.  Cancel, terminal
        transition, retry, or any version change invalidates older tokens
        (D-10, T-45-08).  Returns ``True`` only if both the token digest and
        the expected version match the current running state.
        """
        from app.research.run_contract import attempt_token_digest

        if not attempt_token:
            return False
        candidate_digest = attempt_token_digest(attempt_token)
        stored = self._repository.get_current_attempt_digest(
            run_id, principal=principal, expected_version=expected_version
        )
        return stored == candidate_digest

    def _progress_limits(self, run_id: str) -> tuple[int, int]:
        snapshot = self._repository.get_run_snapshot(run_id)
        manifest = snapshot.get("manifest", {}) if snapshot else {}
        budgets = manifest.get("budgets") if isinstance(manifest, Mapping) else None
        geometry = manifest.get("fold_geometry") if isinstance(manifest, Mapping) else None
        candidate_limit = budgets.get("max_candidates") if isinstance(budgets, Mapping) else None
        fold_limit = geometry.get("n_folds") if isinstance(geometry, Mapping) else None
        if type(candidate_limit) is not int or candidate_limit < 0 or candidate_limit > 1_000_000_000:
            raise ValueError("frozen max_candidates budget is invalid")
        if type(fold_limit) is not int or fold_limit < 0 or fold_limit > 1_000_000_000:
            raise ValueError("frozen n_folds budget is invalid")
        return candidate_limit, fold_limit

    def update_progress(
        self,
        run_id: str,
        *,
        principal: str,
        expected_version: int,
        attempt_token: str | None = None,
        candidate_attempts_total: int | None = None,
        candidate_attempts_completed: int | None = None,
        folds_total: int | None = None,
        folds_completed: int | None = None,
    ) -> dict[str, Any] | None:
        """Persist monotonic counters within the frozen run budget."""
        validate_progress_counters(
            candidate_attempts_total=candidate_attempts_total,
            candidate_attempts_completed=candidate_attempts_completed,
            folds_total=folds_total, folds_completed=folds_completed,
        )
        if not self._validate_attempt_token(
            run_id, principal=principal, expected_version=expected_version,
            attempt_token=attempt_token,
        ):
            return None
        run = self._repository.get_alpha_run(run_id, principal=principal)
        if run is None:
            return None
        candidate_limit, fold_limit = self._progress_limits(run_id)
        proposed = {
            "candidate_attempts_total": candidate_attempts_total,
            "candidate_attempts_completed": candidate_attempts_completed,
            "folds_total": folds_total, "folds_completed": folds_completed,
        }
        limits = {
            "candidate_attempts_total": candidate_limit,
            "candidate_attempts_completed": candidate_limit,
            "folds_total": fold_limit, "folds_completed": fold_limit,
        }
        for name, value in proposed.items():
            if value is not None and value > limits[name]:
                raise ValueError(f"{name} exceeds the frozen run budget")
            if value is not None and value < int(run[name]):
                raise ValueError(f"{name} cannot decrease")
        candidate_total = candidate_attempts_total if candidate_attempts_total is not None else int(run["candidate_attempts_total"])
        candidate_completed = candidate_attempts_completed if candidate_attempts_completed is not None else int(run["candidate_attempts_completed"])
        fold_total = folds_total if folds_total is not None else int(run["folds_total"])
        fold_completed = folds_completed if folds_completed is not None else int(run["folds_completed"])
        if candidate_completed > candidate_total or fold_completed > fold_total:
            raise ValueError("completed progress cannot exceed its total")
        return self._repository.update_progress(
            run_id=run_id, principal=principal, expected_version=expected_version,
            candidate_attempts_total=candidate_attempts_total,
            candidate_attempts_completed=candidate_attempts_completed,
            folds_total=folds_total, folds_completed=folds_completed,
        )

    def get(self, run_id: str, *, principal: str) -> dict[str, Any] | None:
        """Return one principal-scoped durable run row."""
        return self._repository.get_alpha_run(run_id, principal=principal)
    def replay(
        self,
        run_id: str,
        *,
        principal: str,
        include_candidates: bool = False,
        after_seq: int = 0,
        limit: int = 500,
    ) -> dict[str, Any] | None:
        """Read-only replay with explicit continuation markers."""
        run = self._repository.get_alpha_run(run_id, principal=principal)
        if run is None:
            return None
        if after_seq < 0 or limit < 1 or limit > 5000:
            raise ValueError("replay pagination bounds are invalid")
        snapshot = self._repository.get_run_snapshot(run_id)
        events = self._repository.list_run_events(
            run_id, after_seq=after_seq, limit=limit, principal=principal,
            artifact_service=self._artifact_service,
        )
        last_seq = int(events[-1]["seq"]) if events else after_seq
        truncated = bool(events) and len(events) >= limit and last_seq < int(run["last_event_seq"])
        result: dict[str, Any] = {
            "run": run, "snapshot": snapshot, "events": events,
            "events_after_sequence": after_seq,
            "next_sequence": last_seq if truncated else None,
            "truncated": truncated,
        }
        if include_candidates:
            result["candidates"] = self._repository.list_candidates(
                run_id, principal=principal, artifact_service=self._artifact_service
            )
        return result

    def list_events(
        self,
        run_id: str,
        *,
        principal: str,
        after_seq: int = 0,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        return self._repository.list_run_events(
            run_id, after_seq=after_seq, limit=limit, principal=principal,
            artifact_service=self._artifact_service,
        )

    def list_candidates(
        self,
        run_id: str,
        *,
        principal: str,
        after_ordinal: int = 0,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Return bounded, ordered candidate-attempt history scoped to ``principal``.

        Every attempted candidate — including invalid, duplicate, failed, and
        rejected outcomes — is retained in ordinal order (AF-REQ-04).
        Cross-principal reads return the same empty boundary as an unknown run.
        """
        return self._repository.list_candidates(
            run_id, after_ordinal=after_ordinal, limit=limit, principal=principal,
            artifact_service=self._artifact_service,
        )

    def append_event(
        self,
        *,
        run_id: str,
        principal: str,
        event_type: str,
        entity_kind: str,
        entity_id: str,
        idempotency_key: str,
        actor: str,
        source: str,
        payload: Mapping[str, Any],
        artifact_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Append one principal-scoped lifecycle event after validation."""
        validate_bounded_json(payload, "event payload")
        run = self._repository.get_alpha_run(run_id, principal=principal)
        if run is None:
            return None
        if artifact_id is not None:
            self._verify_artifact_reference(run_id, artifact_id)
        event = self._repository.append_run_event(
            run_id=run_id, event_id="aevt_" + uuid.uuid4().hex,
            event_type=event_type, entity_kind=entity_kind, entity_id=entity_id,
            idempotency_key=idempotency_key, actor=actor, source=source,
            payload=payload, artifact_id=artifact_id,
            artifact_verified=artifact_id is not None,
        )
        if self._publisher is not None:
            try:
                self._publisher.on_run_created(run)
            except Exception:  # noqa: BLE001
                pass
        return event

    def append_candidate(
        self,
        *,
        run_id: str,
        principal: str,
        expected_version: int,
        attempt_token: str,
        candidate_id: str,
        attempt_ordinal: int,
        candidate_digest: str,
        canonical_expression: str,
        ast_signature: str,
        shape_signature: str,
        dsl_version: str,
        operation: str,
        seed: int,
        step: int,
        status: str,
        reason: Mapping[str, Any],
        evidence_artifact_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Append a candidate under one atomic running-attempt fence."""
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("expected_version is required for candidate append")
        if type(attempt_token) is not str or not attempt_token:
            raise ValueError("attempt_token is required for candidate append")
        if evidence_artifact_id is not None:
            self._verify_artifact_reference(run_id, evidence_artifact_id)
        return self._repository.append_candidate_attempt(
            run_id=run_id, candidate_id=candidate_id, attempt_ordinal=attempt_ordinal,
            candidate_digest=candidate_digest, canonical_expression=canonical_expression,
            ast_signature=ast_signature, shape_signature=shape_signature,
            dsl_version=dsl_version, operation=operation, seed=seed, step=step,
            status=status, reason=reason, evidence_artifact_id=evidence_artifact_id,
            artifact_verified=evidence_artifact_id is not None, principal=principal,
            expected_version=expected_version,
            expected_attempt_token_digest=attempt_token_digest(attempt_token),
        )

    def append_candidate_lineage(
        self,
        *,
        run_id: str,
        principal: str,
        expected_version: int,
        attempt_token: str,
        lineage_id: str,
        child_attempt_id: str,
        parent_attempt_id: str,
        edge_ordinal: int,
        operation: str,
    ) -> dict[str, Any] | None:
        """Append lineage under one atomic running-attempt fence."""
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("expected_version is required for lineage append")
        if type(attempt_token) is not str or not attempt_token:
            raise ValueError("attempt_token is required for lineage append")
        return self._repository.append_candidate_lineage(
            run_id=run_id, lineage_id=lineage_id, child_attempt_id=child_attempt_id,
            parent_attempt_id=parent_attempt_id, edge_ordinal=edge_ordinal,
            operation=operation, principal=principal, expected_version=expected_version,
            expected_attempt_token_digest=attempt_token_digest(attempt_token),
        )

    def append_artifact(
        self,
        *,
        run_id: str,
        principal: str,
        artifact_id: str,
        logical_kind: str,
        descriptor: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """Verify managed bytes before recording an artifact descriptor."""
        if self._repository.get_alpha_run(run_id, principal=principal) is None:
            return None
        verifier = self._artifact_service
        if verifier is None:
            raise AlphaCheckpointValidationError("artifact verification service is required")
        try:
            checksum = descriptor["checksum_sha256"]
            expected_path = f"research_artifacts/alpha_runs/{run_id}/{checksum}.json"
            if descriptor.get("relative_path") != expected_path:
                raise ValueError("artifact key does not match run-bound checksum")
            verifier.verify_artifact(
                run_id=run_id, checksum_sha256=checksum,
                expected_byte_size=descriptor.get("byte_size"),
                expected_content_type=descriptor.get("content_type"),
            )
        except Exception as error:
            raise AlphaCheckpointValidationError("artifact verification failed") from error
        return self._repository.append_artifact(
            run_id=run_id, artifact_id=artifact_id, logical_kind=logical_kind,
            relative_path=descriptor["relative_path"], content_type=descriptor["content_type"],
            byte_size=descriptor["byte_size"], checksum_sha256=descriptor["checksum_sha256"],
            artifact_service=verifier,
        )
    def append_checkpoint(
        self,
        *,
        run_id: str,
        principal: str,
        checkpoint: Mapping[str, Any],
        referenced_candidate_ids: Sequence[str] = (),
        inline_summary: Mapping[str, Any] | None = None,
        expected_version: int,
        attempt_token: str,
    ) -> dict[str, Any] | None:
        """Validate and atomically persist a live-attempt recovery cursor."""
        if type(expected_version) is not int or expected_version < 0:
            raise ValueError("expected_version is required for checkpoint append")
        if type(attempt_token) is not str or not attempt_token:
            raise ValueError("attempt_token is required for checkpoint append")
        validated = self.validate_checkpoint(
            run_id=run_id, principal=principal, checkpoint=checkpoint,
            referenced_candidate_ids=referenced_candidate_ids,
            inline_summary=inline_summary,
        )
        expected_digest = attempt_token_digest(attempt_token)
        return self._repository.append_checkpoint(
            run_id=run_id, checkpoint_id=str(validated.get("id", checkpoint.get("id"))),
            checkpoint_version=validated["checkpoint_version"],
            committed_event_seq=validated["committed_event_seq"], stage=validated["stage"],
            snapshot_sha256=validated["snapshot_sha256"], manifest_sha256=validated["manifest_sha256"],
            state_checksum=validated["state_checksum"], frontier_artifact_id=validated.get("frontier_artifact_id"),
            principal=principal, referenced_candidate_ids=referenced_candidate_ids,
            inline_summary=inline_summary, expected_version=expected_version,
            expected_attempt_token_digest=expected_digest,
        )

    def append_stage_boundary(
        self,
        repo: Any,
        *,
        run_id: str,
        after_stage: str,
        event_id: str,
        event_type: str,
        idempotency_key: str,
        actor: str,
        source: str,
        payload: Mapping[str, Any],
        committed_event_seq: int,
        checkpoint_stage: str,
        snapshot_sha256: str,
        manifest_sha256: str,
        state_checksum: str,
        principal: str,
        expected_version: int,
        expected_attempt_token_digest: str,
        referenced_candidate_ids: Sequence[str] = (),
        inline_summary: Mapping[str, Any] | None = None,
        frontier_artifact_id: str | None = None,
    ) -> dict[str, Any]:
        """Append a stage's terminal event + checkpoint in one transaction.

        Phase 48-03 (AF-REQ-21 §6.2). Validates the bounded payload + inline
        summary, pins the stage->checkpoint mapping (Stage 1 boundary ->
        ``stage2_pending``; Stage 2 boundary -> ``stage2``, terminal for the
        Agent), recomputes the checkpoint version + state checksum and asserts
        the caller-supplied checksum matches (fail-closed on drift), then
        delegates the atomic event+checkpoint transaction to
        :meth:`ResearchRepository.append_stage_boundary`. The repository fence
        re-checks the attempt token, version, snapshot/manifest binding, and
        event-sequence contiguity under ``BEGIN IMMEDIATE``.
        """
        from app.research.run_contract import (
            MAX_INLINE_CHECKPOINT_BYTES,
            checkpoint_state_checksum,
        )

        if after_stage not in ("stage1", "stage2"):
            raise ValueError("after_stage must be 'stage1' or 'stage2'")
        expected_checkpoint_stage = "stage2_pending" if after_stage == "stage1" else "stage2"
        if checkpoint_stage != expected_checkpoint_stage:
            raise ValueError(
                f"checkpoint_stage must be '{expected_checkpoint_stage}' for "
                f"after_stage='{after_stage}'"
            )
        if event_type not in ("stage1_completed", "stage2_completed"):
            raise ValueError("event_type must be 'stage1_completed' or 'stage2_completed'")
        validate_bounded_json(payload, "stage boundary payload")
        if inline_summary is not None:
            validate_bounded_json(
                inline_summary,
                "stage boundary inline summary",
                max_bytes=MAX_INLINE_CHECKPOINT_BYTES,
            )
        checkpoint_version = repo.next_checkpoint_version(run_id)
        expected_checksum = checkpoint_state_checksum(
            run_id=run_id,
            checkpoint_version=checkpoint_version,
            committed_event_seq=committed_event_seq,
            stage=checkpoint_stage,
            snapshot_sha256=snapshot_sha256,
            manifest_sha256=manifest_sha256,
            referenced_candidate_ids=tuple(referenced_candidate_ids),
            inline_summary=inline_summary,
            frontier_artifact_id=frontier_artifact_id,
        )
        if expected_checksum != state_checksum:
            raise AlphaCheckpointValidationError(
                "stage boundary state checksum mismatch"
            )
        checkpoint_id = "chk_" + uuid.uuid4().hex
        return repo.append_stage_boundary(
            run_id=run_id,
            event_id=event_id,
            event_type=event_type,
            entity_kind="run",
            entity_id=run_id,
            idempotency_key=idempotency_key,
            actor=actor,
            source=source,
            payload=payload,
            committed_event_seq=committed_event_seq,
            checkpoint_id=checkpoint_id,
            checkpoint_version=checkpoint_version,
            checkpoint_stage=checkpoint_stage,
            snapshot_sha256=snapshot_sha256,
            manifest_sha256=manifest_sha256,
            state_checksum=state_checksum,
            principal=principal,
            expected_version=expected_version,
            expected_attempt_token_digest=expected_attempt_token_digest,
            referenced_candidate_ids=referenced_candidate_ids,
            inline_summary=inline_summary,
            frontier_artifact_id=frontier_artifact_id,
        )

    def validate_checkpoint(
        self,
        *,
        run_id: str,
        principal: str,
        checkpoint: Mapping[str, Any],
        referenced_candidate_ids: Sequence[str] | None = None,
        inline_summary: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Fail-closed validation of a recovery checkpoint cursor (D-07).

        Verifies: run identity matches; snapshot and manifest digests match the
        frozen run; event sequence exists and is contiguous through the
        checkpoint; referenced candidate IDs belong to the run; artifact (when
        present) exists, size matches, and SHA-256 matches; checkpoint state
        checksum recomputes.  Missing, stale, future, non-contiguous, or
        mismatched cursors raise ``AlphaCheckpointValidationError`` without
        advancing status, event sequence, or cursor (T-45-05).
        """
        from app.research.run_contract import MAX_INLINE_CHECKPOINT_BYTES, checkpoint_state_checksum
        run = self._repository.get_alpha_run(run_id, principal=principal)
        if run is None:
            raise AlphaCheckpointValidationError("run not found for principal")
        normalized_checkpoint = dict(checkpoint)
        checkpoint_id = normalized_checkpoint.get("id")
        if checkpoint_id is None:
            normalized_checkpoint["id"] = "chk_" + uuid.uuid4().hex
        elif type(checkpoint_id) is not str or not checkpoint_id:
            raise AlphaCheckpointValidationError("checkpoint id must be a non-empty string")
        checkpoint = normalized_checkpoint
        try:
            raw_version = checkpoint["checkpoint_version"]
            raw_seq = checkpoint["committed_event_seq"]
            stage = checkpoint["stage"]
            snapshot_sha256 = checkpoint["snapshot_sha256"]
            manifest_sha256 = checkpoint["manifest_sha256"]
            state_checksum = checkpoint["state_checksum"]
            if type(raw_version) is not int or type(raw_seq) is not int:
                raise TypeError("checkpoint integer fields must be exact integers")
            if type(stage) is not str or type(snapshot_sha256) is not str:
                raise TypeError("checkpoint text fields must be exact strings")
            if type(manifest_sha256) is not str or type(state_checksum) is not str:
                raise TypeError("checkpoint text fields must be exact strings")
            checkpoint_version = raw_version
            committed_seq = raw_seq
        except (KeyError, TypeError, ValueError) as error:
            raise AlphaCheckpointValidationError("checkpoint shape is invalid") from error
        if checkpoint_version <= 0 or committed_seq < 0 or not 1 <= len(stage) <= 128:
            raise AlphaCheckpointValidationError("checkpoint bounds are invalid")
        if snapshot_sha256 != run["snapshot_sha256"]:
            raise AlphaCheckpointValidationError("snapshot digest mismatch (stale cursor)")
        if manifest_sha256 != run["manifest_sha256"]:
            raise AlphaCheckpointValidationError("manifest digest mismatch (stale cursor)")
        if inline_summary is not None:
            try:
                if not isinstance(inline_summary, Mapping):
                    raise ValueError("inline checkpoint summary must be an object")
                validate_bounded_json(
                    inline_summary, "inline checkpoint summary", max_bytes=MAX_INLINE_CHECKPOINT_BYTES
                )
            except ValueError as error:
                raise AlphaCheckpointValidationError(str(error)) from error
        if run["last_event_seq"] < committed_seq:
            raise AlphaCheckpointValidationError("checkpoint references a future event sequence")
        if committed_seq > 100_000:
            raise AlphaCheckpointValidationError("checkpoint event sequence exceeds validation bound")
        events = self._repository.list_run_events(
            run_id,
            after_seq=0,
            limit=max(1, committed_seq),
            principal=principal,
            artifact_service=self._artifact_service,
        )
        actual_seqs = {evt["seq"] for evt in events}
        expected_seqs = set(range(1, committed_seq + 1))
        if not expected_seqs.issubset(actual_seqs):
            raise AlphaCheckpointValidationError("committed event sequence is not contiguous")
        candidate_ids = list(referenced_candidate_ids or [])
        if len(candidate_ids) > 256 or any(type(cid) is not str or not cid for cid in candidate_ids):
            raise AlphaCheckpointValidationError("checkpoint candidate references are invalid")
        if len(set(candidate_ids)) != len(candidate_ids):
            raise AlphaCheckpointValidationError("checkpoint candidate references must be ordered and unique")
        if candidate_ids:
            present = self._repository.candidate_ids_for_run(
                run_id, candidate_ids, principal=principal
            )
            if any(cid not in present for cid in candidate_ids):
                raise AlphaCheckpointValidationError("checkpoint references missing candidate(s)")
        frontier_artifact_id = checkpoint.get("frontier_artifact_id")
        if frontier_artifact_id is not None:
            if type(frontier_artifact_id) is not str or not frontier_artifact_id:
                raise AlphaCheckpointValidationError("frontier artifact reference is invalid")
            verifier = self._artifact_service
            if verifier is None:
                raise AlphaCheckpointValidationError("frontier artifact verification service is required")
            artifact_row = self._get_artifact(frontier_artifact_id, run_id)
            if artifact_row is None:
                raise AlphaCheckpointValidationError("frontier artifact reference missing")
            if artifact_row["relative_path"] != (
                f"research_artifacts/alpha_runs/{run_id}/{artifact_row['checksum_sha256']}.json"
            ):
                raise AlphaCheckpointValidationError("frontier artifact managed key mismatch")
            try:
                verifier.verify_artifact(
                    run_id=run_id, checksum_sha256=artifact_row["checksum_sha256"],
                    expected_byte_size=artifact_row["byte_size"],
                    expected_content_type=artifact_row["content_type"],
                )
            except Exception as error:
                raise AlphaCheckpointValidationError("frontier artifact verification failed") from error
        expected_checksum = checkpoint_state_checksum(
            run_id=run_id, checkpoint_version=checkpoint_version,
            committed_event_seq=committed_seq, stage=stage,
            snapshot_sha256=snapshot_sha256, manifest_sha256=manifest_sha256,
            referenced_candidate_ids=candidate_ids, inline_summary=inline_summary,
            frontier_artifact_id=frontier_artifact_id,
        )
        if expected_checksum != state_checksum:
            raise AlphaCheckpointValidationError("checkpoint state checksum mismatch")
        return dict(checkpoint)

    def _get_artifact(
        self, artifact_id: str, run_id: str
    ) -> dict[str, Any] | None:
        with self._repository._connection() as connection:
            row = connection.execute(
                "SELECT * FROM research_alpha_artifacts WHERE id = ? AND run_id = ?",
                (artifact_id, run_id),
            ).fetchone()
        return None if row is None else dict(row)

    def get_latest_valid_checkpoint(self, run_id: str, *, principal: str) -> dict[str, Any] | None:
        """Read and validate the newest durable cursor before recovery use."""
        raw = self._repository._get_latest_checkpoint_unvalidated(run_id, principal=principal)
        if raw is None:
            return None
        return self.validate_checkpoint(
            run_id=run_id, principal=principal, checkpoint=raw,
            referenced_candidate_ids=raw.get("referenced_candidate_ids", []),
            inline_summary=raw.get("inline_summary", {}),
        )

    def _verify_artifact_reference(self, run_id: str, artifact_id: str) -> None:
        verifier = self._artifact_service
        if verifier is None:
            raise AlphaCheckpointValidationError("artifact verification service is required")
        row = self._get_artifact(artifact_id, run_id)
        if row is None or row["relative_path"] != (
            f"research_artifacts/alpha_runs/{run_id}/{row['checksum_sha256']}.json" if row else ""
        ):
            raise AlphaCheckpointValidationError("artifact reference is missing or unbound")
        try:
            verifier.verify_artifact(
                run_id=run_id, checksum_sha256=row["checksum_sha256"],
                expected_byte_size=row["byte_size"], expected_content_type=row["content_type"],
            )
        except Exception as error:
            raise AlphaCheckpointValidationError("artifact verification failed") from error
    def validate_inline_checkpoint_payload(self, payload_bytes: bytes) -> None:
        """Reject inline checkpoint payloads over 16 KiB or non-canonical JSON (D-07, T-45-05).

        Inline checkpoint JSON is bounded at 16 KiB UTF-8; larger state must
        use a verified managed artifact reference plus a bounded summary.
        Pickle, executable state, raw data frames, and prompts are excluded.
        """
        import json
        from app.research.run_contract import MAX_INLINE_CHECKPOINT_BYTES, canonical_json
        if not isinstance(payload_bytes, (bytes, bytearray)):
            raise AlphaCheckpointValidationError("inline payload must be bytes")
        if len(payload_bytes) > MAX_INLINE_CHECKPOINT_BYTES:
            raise AlphaCheckpointValidationError("inline checkpoint payload exceeds 16 KiB bound")
        try:
            decoded = bytes(payload_bytes).decode("utf-8")
            parsed = json.loads(decoded)
            if not isinstance(parsed, dict):
                raise ValueError("inline checkpoint state must be a JSON object")
            canonical = canonical_json(parsed).encode("utf-8")
            if canonical != bytes(payload_bytes):
                raise ValueError("inline checkpoint JSON is not canonical")
        except (UnicodeDecodeError, ValueError, TypeError) as error:
            raise AlphaCheckpointValidationError(
                "inline checkpoint payload is not canonical UTF-8 JSON"
            ) from error
    # ----------------------------------------------------------------
    # Phase 48-04: resume-from-checkpoint + offline-fixture run mode
    # ----------------------------------------------------------------

    def resume_agent_stage(
        self,
        run_id: str,
        *,
        principal: str,
        expected_version: int,
        attempt_token: str,
    ) -> str:
        """Read the Phase 45 cursor and report the Agent stage to resume at.

        Phase 48-04 (AF-REQ-21 §6.1). Reuses the existing checkpoint/event
        cursor — it introduces NO new Agent/validation framework (ROADMAP.md:71).
        Validates the run is ``running`` and the caller holds the current
        attempt token (only the current worker may resume), then reads the
        latest valid checkpoint's ``stage`` discriminator and maps it to the
        next Agent stage to execute:

        * no / early checkpoint -> ``"stage1"`` (preflight already passed at run
          start; Stage 1 has not committed its boundary yet).
        * ``stage2_pending`` -> ``"stage2"`` (Stage 1 boundary committed; resume
          runs ONLY Stage 2).
        * ``stage2`` -> ``"complete"`` (terminal for the Agent; nothing to do).

        Resume does NOT recompute committed candidate/OOS/promotion evidence:
        those are append-only idempotent (repository.py:2250-2358, 1078-1135) and
        Stage 2 reads them rather than recomputing. Token re-fencing is the
        orchestrator's job via :meth:`recover_running_attempt`; a checkpoint
        written under a stale token is rejected by ``append_stage_boundary``'s
        ``expected_attempt_token_digest`` fence (repository.py).
        """
        run = self._repository.get_alpha_run(run_id, principal=principal)
        if run is None:
            raise ValueError("run not found for principal")
        if run["status"] != "running":
            raise ValueError("only a running attempt can be resumed")
        if not self._validate_attempt_token(
            run_id,
            principal=principal,
            expected_version=expected_version,
            attempt_token=attempt_token,
        ):
            raise ValueError("invalid or stale attempt token")
        checkpoint = self.get_latest_valid_checkpoint(run_id, principal=principal)
        if checkpoint is None:
            return "stage1"
        stage = checkpoint["stage"]
        if stage == "stage2_pending":
            return "stage2"
        if stage == "stage2":
            return "complete"
        # Any earlier/unknown cursor (e.g. a preflight checkpoint) -> start at Stage 1.
        return "stage1"

    # Phase 48 fixture-mode orchestration moved to agent_orchestrator.py to
    # keep this Phase 45 module free of provider/stage imports (boundary
    # guard ``test_phase45_guard.py`` prohibits the ``provider`` token).
    # Callers use ``agent_orchestrator.run_fixture_mode(service, ...)``.


class RunEventPublisher:
    """Protocol for an optional post-commit publisher (D-05, D-09)."""

    def on_run_created(self, run: Mapping[str, Any]) -> None: ...
