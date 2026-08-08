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
from collections.abc import Mapping
from typing import Any

from app.research.repository import AlphaRunConflictError, ResearchRepository
from app.research.run_contract import freeze_input_snapshot


class AlphaRunPreflightError(ValueError):
    """A create request failed preflight (malformed/incomplete run-level input)."""


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

    def replay(self, run_id: str, *, principal: str) -> dict[str, Any] | None:
        """Read-only replay of the frozen snapshot and committed event history.

        Returns ``None`` for unknown or cross-principal runs (same boundary as
        ``get``).  Never writes, resolves current data, or executes work (D-08).
        """
        run = self._repository.get_alpha_run(run_id, principal=principal)
        if run is None:
            return None
        snapshot = self._repository.get_run_snapshot(run_id)
        events = self._repository.list_run_events(run_id)
        return {"run": run, "snapshot": snapshot, "events": events}


class RunEventPublisher:
    """Protocol for an optional post-commit publisher (D-05, D-09)."""

    def on_run_created(self, run: Mapping[str, Any]) -> None: ...
