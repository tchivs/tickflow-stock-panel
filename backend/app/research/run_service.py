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

import uuid
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from app.research.repository import AlphaRunConflictError, ResearchRepository
from app.research.run_contract import freeze_input_snapshot

if TYPE_CHECKING:
    from app.research.artifacts import AlphaRunArtifactService


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
        events = self._repository.list_run_events(
            run_id, after_seq=0, limit=committed_seq + 1, principal=principal
        )
        actual_seqs = {evt["seq"] for evt in events}
        expected_seqs = set(range(1, committed_seq + 1))
        if committed_seq > 0 and not expected_seqs.issubset(actual_seqs):
            raise AlphaCheckpointValidationError(
                "committed event sequence is not contiguous"
            )
        if run["last_event_seq"] < committed_seq:
            raise AlphaCheckpointValidationError(
                "checkpoint references a future event sequence"
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
            artifact_service.verify_artifact(
                run_id=run_id,
                checksum_sha256=artifact_row["checksum_sha256"],
                expected_byte_size=artifact_row["byte_size"],
                expected_content_type=artifact_row["content_type"],
            )

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
