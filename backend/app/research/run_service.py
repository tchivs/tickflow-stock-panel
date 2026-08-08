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

import secrets
import uuid
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from app.research.repository import AlphaRunConflictError, ResearchRepository
from app.research.run_contract import freeze_input_snapshot

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
    ) -> None:
        self._repository = repository
        self._publisher = publisher

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
        result = self._repository.transition_alpha_run(
            run_id=run_id,
            principal=principal,
            from_status=from_status,
            to_status=to_status,
            expected_version=expected_version,
            event_id=event_id,
            event_type=event_type,
            idempotency_key=key,
            terminal_reason=terminal_reason,
            extra_payload=extra_payload,
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
        key = idempotency_key or f"cancel-{run['status']}-{expected_version}"
        event_id = "aevt_" + uuid.uuid4().hex
        return self._repository.cancel_alpha_run(
            run_id=run_id,
            principal=principal,
            expected_version=expected_version,
            event_id=event_id,
            idempotency_key=key,
        )

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
        run = self._repository.get_alpha_run(run_id, principal=principal)
        if run is None or run["status"] != "running":
            return False
        if run["transition_version"] != expected_version:
            return False
        # Find the run_started event carrying this version's token digest.
        events = self._repository.list_run_events(
            run_id, after_seq=0, limit=500, principal=principal
        )
        candidate_digest = attempt_token_digest(attempt_token)
        for event in reversed(events):
            if event["event_type"] == "run_started":
                stored = event["payload"].get("attempt_token_digest")
                return stored == candidate_digest
        return False

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
        """Persist bounded server-owned progress counters (D-11).

        Validates the attempt token plus expected version before persisting any
        counter.  Only non-``None`` counters are updated; each must be a
        non-negative integer.  This does NOT evaluate folds — it persists
        declared totals and completed counts reported by a worker.  Returns
        ``None`` for unknown/cross-principal/stale/token-mismatch (fail closed,
        T-45-08).
        """
        from app.research.run_contract import validate_progress_counters

        validate_progress_counters(
            candidate_attempts_total=candidate_attempts_total,
            candidate_attempts_completed=candidate_attempts_completed,
            folds_total=folds_total,
            folds_completed=folds_completed,
        )
        if not self._validate_attempt_token(
            run_id, principal=principal,
            expected_version=expected_version, attempt_token=attempt_token,
        ):
            return None
        return self._repository.update_progress(
            run_id=run_id,
            principal=principal,
            expected_version=expected_version,
            candidate_attempts_total=candidate_attempts_total,
            candidate_attempts_completed=candidate_attempts_completed,
            folds_total=folds_total,
            folds_completed=folds_completed,
        )

    def get(self, run_id: str, *, principal: str) -> dict[str, Any] | None:
        """Return one principal-scoped run row, or ``None`` for unknown/cross-principal."""
        return self._repository.get_alpha_run(run_id, principal=principal)

    def replay(
        self, run_id: str, *, principal: str, include_candidates: bool = False
    ) -> dict[str, Any] | None:
        """Read-only replay of the frozen snapshot and committed facts.

        Returns ``None`` for unknown or cross-principal runs (same boundary as
        ``get``).  Never writes, resolves current data, or executes work (D-08).
        When ``include_candidates`` is true, the replay also returns the
        candidate-attempt ledger in ordinal order — deterministic and
        read-only.
        """
        run = self._repository.get_alpha_run(run_id, principal=principal)
        if run is None:
            return None
        snapshot = self._repository.get_run_snapshot(run_id)
        events = self._repository.list_run_events(run_id, principal=principal)
        result: dict[str, Any] = {"run": run, "snapshot": snapshot, "events": events}
        if include_candidates:
            result["candidates"] = self._repository.list_candidates(
                run_id, principal=principal
            )
        return result

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
        """Append one principal-scoped lifecycle event with commit-before-publish.

        Returns ``None`` for unknown or cross-principal runs.  The repository
        allocates a contiguous sequence under ``BEGIN IMMEDIATE`` and commits
        before this method returns; any optional publisher notification runs
        only after the transaction succeeds (D-05, T-45-03).
        """
        run = self._repository.get_alpha_run(run_id, principal=principal)
        if run is None:
            return None
        event_id = "aevt_" + uuid.uuid4().hex
        event = self._repository.append_run_event(
            run_id=run_id,
            event_id=event_id,
            event_type=event_type,
            entity_kind=entity_kind,
            entity_id=entity_id,
            idempotency_key=idempotency_key,
            actor=actor,
            source=source,
            payload=payload,
            artifact_id=artifact_id,
        )
        if self._publisher is not None:
            try:
                self._publisher.on_run_created(run)
            except Exception:  # noqa: BLE001
                pass  # best-effort; committed event is not rolled back
        return event

    def append_candidate(
        self,
        *,
        run_id: str,
        principal: str,
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
        """Append one candidate-attempt fact, principal-scoped.

        Returns ``None`` for unknown or cross-principal runs.  Every outcome
        (invalid, duplicate, low_coverage, failed, rejected, admitted,
        cancelled, budget_exhausted) is a durable fact; no expression
        uniqueness rule erases a duplicate attempt (AF-REQ-04, D-05).
        """
        run = self._repository.get_alpha_run(run_id, principal=principal)
        if run is None:
            return None
        return self._repository.append_candidate_attempt(
            run_id=run_id,
            candidate_id=candidate_id,
            attempt_ordinal=attempt_ordinal,
            candidate_digest=candidate_digest,
            canonical_expression=canonical_expression,
            ast_signature=ast_signature,
            shape_signature=shape_signature,
            dsl_version=dsl_version,
            operation=operation,
            seed=seed,
            step=step,
            status=status,
            reason=reason,
            evidence_artifact_id=evidence_artifact_id,
        )

    def validate_checkpoint(
        self,
        *,
        run_id: str,
        principal: str,
        checkpoint: Mapping[str, Any],
        referenced_candidate_ids: Sequence[str] | None = None,
        inline_summary: Mapping[str, Any] | None = None,
        artifact_service: "AlphaRunArtifactService | None" = None,
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
        from app.research.run_contract import checkpoint_state_checksum

        run = self._repository.get_alpha_run(run_id, principal=principal)
        if run is None:
            raise AlphaCheckpointValidationError("run not found for principal")
        if checkpoint["snapshot_sha256"] != run["snapshot_sha256"]:
            raise AlphaCheckpointValidationError("snapshot digest mismatch (stale cursor)")
        if checkpoint["manifest_sha256"] != run["manifest_sha256"]:
            raise AlphaCheckpointValidationError("manifest digest mismatch (stale cursor)")

        committed_seq = int(checkpoint["committed_event_seq"])
        if run["last_event_seq"] < committed_seq:
            raise AlphaCheckpointValidationError(
                "checkpoint references a future event sequence"
            )
        events = self._repository.list_run_events(
            run_id, after_seq=0, limit=committed_seq + 1, principal=principal
        )
        actual_seqs = {evt["seq"] for evt in events}
        expected_seqs = set(range(1, committed_seq + 1))
        if committed_seq > 0 and not expected_seqs.issubset(actual_seqs):
            raise AlphaCheckpointValidationError(
                "committed event sequence is not contiguous"
            )

        candidate_ids = list(referenced_candidate_ids or [])
        if candidate_ids:
            present = {
                str(c["id"]) for c in self._repository.list_candidates(run_id, principal=principal)
            }
            missing = [cid for cid in candidate_ids if cid not in present]
            if missing:
                raise AlphaCheckpointValidationError(
                    "checkpoint references missing candidate(s)"
                )

        frontier_artifact_id = checkpoint.get("frontier_artifact_id")
        if frontier_artifact_id is not None and artifact_service is not None:
            artifact_row = self._get_artifact(frontier_artifact_id, run_id)
            if artifact_row is None:
                raise AlphaCheckpointValidationError("frontier artifact reference missing")
            try:
                artifact_service.verify_artifact(
                    run_id=run_id,
                    checksum_sha256=artifact_row["checksum_sha256"],
                    expected_byte_size=artifact_row["byte_size"],
                    expected_content_type=artifact_row["content_type"],
                )
            except Exception as error:
                raise AlphaCheckpointValidationError(
                    f"frontier artifact verification failed: {error}"
                ) from error

        expected_checksum = checkpoint_state_checksum(
            run_id=run_id,
            checkpoint_version=int(checkpoint["checkpoint_version"]),
            committed_event_seq=committed_seq,
            stage=str(checkpoint["stage"]),
            snapshot_sha256=checkpoint["snapshot_sha256"],
            manifest_sha256=checkpoint["manifest_sha256"],
            referenced_candidate_ids=candidate_ids,
            inline_summary=inline_summary,
            frontier_artifact_id=frontier_artifact_id,
        )
        if expected_checksum != checkpoint["state_checksum"]:
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

    def validate_inline_checkpoint_payload(self, payload_bytes: bytes) -> None:
        """Reject inline checkpoint payloads over 16 KiB or non-canonical JSON (D-07, T-45-05).

        Inline checkpoint JSON is bounded at 16 KiB UTF-8; larger state must
        use a verified managed artifact reference plus a bounded summary.
        Pickle, executable state, raw data frames, and prompts are excluded.
        """
        import json

        from app.research.run_contract import MAX_INLINE_CHECKPOINT_BYTES

        if not isinstance(payload_bytes, (bytes, bytearray)):
            raise AlphaCheckpointValidationError("inline payload must be bytes")
        if len(payload_bytes) > MAX_INLINE_CHECKPOINT_BYTES:
            raise AlphaCheckpointValidationError(
                "inline checkpoint payload exceeds 16 KiB bound"
            )
        try:
            decoded = payload_bytes.decode("utf-8")
            json.loads(decoded)
        except (UnicodeDecodeError, ValueError) as error:
            raise AlphaCheckpointValidationError(
                "inline checkpoint payload is not canonical UTF-8 JSON"
            ) from error


class RunEventPublisher:
    """Protocol for an optional post-commit publisher (D-05, D-09)."""

    def on_run_created(self, run: Mapping[str, Any]) -> None: ...
