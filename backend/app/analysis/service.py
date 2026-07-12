"""Server-owned orchestration for immutable analysis report generation."""
from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Mapping, Sequence
from time import monotonic
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.analysis.evidence import EvidencePreparationService
from app.analysis.schemas import (
    AnalysisReport,
    FrozenEvidenceSnapshot,
    GeneratedAnalysis,
    SignalLifecycleState,
)

_SCHEMA_VERSION = "analysis-v1"
_PROMPT_VERSION = "analysis-prompt-v1"
_MAX_SCHEMA_ATTEMPTS = 3
_SAFE_VALIDATION_FAILURE = "analysis validation failed; manual review required"
_SAFE_PROVIDER_FAILURE = "analysis provider unavailable; manual review required"
_SAFE_CONFIGURATION_FAILURE = "analysis execution is unavailable; manual review required"

EvidenceLoader = Callable[[str, str, str], Sequence[Mapping[str, Any]]]
AuthorizeSubject = Callable[[str, str], None]
LifecycleSnapshotLoader = Callable[[str, str], SignalLifecycleState]


class AnalysisService:
    """Freeze, validate, and append reports without giving the model persistence authority."""

    def __init__(
        self,
        *,
        repository: Any,
        evidence_preparer: EvidencePreparationService | None,
        graph: Any,
        evidence_loader: EvidenceLoader | None = None,
        authorize_subject: AuthorizeSubject | None = None,
        lifecycle_snapshot_loader: LifecycleSnapshotLoader | None = None,
        lifecycle_rule_service: Any | None = None,
    ) -> None:
        self._repository = repository
        self._evidence_preparer = evidence_preparer
        self._graph = graph
        self._evidence_loader = evidence_loader
        self._authorize_subject = authorize_subject
        self._lifecycle_snapshot_loader = lifecycle_snapshot_loader
        self._lifecycle_rule_service = lifecycle_rule_service

    async def start_run(self, *, subject_kind: str, subject_key: str, focus: str) -> dict[str, Any]:
        self._validate_request(subject_kind=subject_kind, subject_key=subject_key, focus=focus)
        if self._authorize_subject is not None:
            self._authorize_subject(subject_kind, subject_key)

        requested_run_id = str(uuid4())
        run = self._repository.acquire_run(
            run_id=requested_run_id,
            subject_kind=subject_kind,
            subject_key=subject_key,
            focus=focus,
        )
        if run["id"] != requested_run_id:
            return run
        if self._graph is None or self._evidence_preparer is None or self._evidence_loader is None:
            return self._repository.record_run_failure(
                run["id"],
                _SAFE_CONFIGURATION_FAILURE,
                audit_metadata=self._failure_metadata(
                    snapshot=None,
                    attempts=0,
                    elapsed=0,
                    category="configuration",
                ),
            )

        self._repository.mark_run_running(run["id"])
        started = monotonic()
        snapshot: FrozenEvidenceSnapshot | None = None
        try:
            records = self._evidence_loader(subject_kind, subject_key, focus)
            if inspect.isawaitable(records):
                records = await records
            snapshot = self._evidence_preparer.freeze(subject_key=subject_key, records=records)
            self._repository.record_frozen_snapshot(run_id=run["id"], snapshot=snapshot)
            if snapshot.context_status != "ready":
                raise ValueError("analysis generation requires ready frozen evidence")

            lifecycle = self._lifecycle_snapshot(subject_kind, subject_key)
            generated, attempts = await self._generate_validated_body(run_id=run["id"], snapshot=snapshot)
            report = AnalysisReport(
                generated=generated,
                evidence_snapshot=snapshot,
                lifecycle=lifecycle,
                run_id=run["id"],
                report_version=len(self._repository.list_reports(subject_kind, subject_key)) + 1,
                schema_version=_SCHEMA_VERSION,
                generation_metadata=self._generation_metadata(
                    snapshot=snapshot, attempts=attempts, elapsed=monotonic() - started
                ),
            )
            persisted_report = self._repository.append_validated_report(
                subject_kind=subject_kind,
                subject_key=subject_key,
                report=report,
                run_id=run["id"],
            )
            completed = self._repository.complete_run(
                run["id"],
                audit_metadata=self._generation_metadata(
                    snapshot=snapshot, attempts=attempts, elapsed=monotonic() - started
                ),
            )
            self._evaluate_lifecycle_proposal(
                subject_kind=subject_kind,
                subject_key=subject_key,
                run_id=run["id"],
                report_id=persisted_report["id"],
            )
            return completed
        except (ValidationError, ValueError):
            return self._repository.record_run_failure(
                run["id"],
                _SAFE_VALIDATION_FAILURE,
                audit_metadata=self._failure_metadata(
                    snapshot=snapshot,
                    attempts=_MAX_SCHEMA_ATTEMPTS,
                    elapsed=monotonic() - started,
                    category="validation",
                ),
            )
        except (RuntimeError, TypeError):
            return self._repository.record_run_failure(
                run["id"],
                _SAFE_PROVIDER_FAILURE,
                audit_metadata=self._failure_metadata(
                    snapshot=snapshot,
                    attempts=1,
                    elapsed=monotonic() - started,
                    category="provider",
                ),
            )

    async def _generate_validated_body(
        self, *, run_id: str, snapshot: FrozenEvidenceSnapshot
    ) -> tuple[GeneratedAnalysis, int]:
        for attempt in range(1, _MAX_SCHEMA_ATTEMPTS + 1):
            try:
                result = await self._graph.ainvoke(
                    {"frozen_evidence": snapshot},
                    {"configurable": {"thread_id": run_id}},
                )
                return GeneratedAnalysis.model_validate(result["generated_body"]), attempt
            except (ValidationError, ValueError, KeyError) as error:
                if attempt == _MAX_SCHEMA_ATTEMPTS:
                    raise ValueError("generated analysis remained invalid") from error
                await asyncio.sleep(0)
        raise AssertionError("schema attempt loop must return or raise")

    def _lifecycle_snapshot(self, subject_kind: str, subject_key: str) -> SignalLifecycleState:
        if self._lifecycle_snapshot_loader is not None:
            return self._lifecycle_snapshot_loader(subject_kind, subject_key)
        # Lifecycle integration is intentionally deferred; this is a read-only server snapshot.
        return SignalLifecycleState(
            signal_id=f"{subject_kind}:{subject_key}", current_state="active", history=()
        )

    def _evaluate_lifecycle_proposal(
        self, *, subject_kind: str, subject_key: str, run_id: str, report_id: str
    ) -> None:
        if self._lifecycle_rule_service is None:
            return
        try:
            self._lifecycle_rule_service.evaluate_completed_analysis(
                subject_kind=subject_kind,
                subject_key=subject_key,
                run_id=run_id,
                report_id=report_id,
            )
        except (RuntimeError, TypeError, ValueError):
            # A proposal is non-authoritative; its failure cannot invalidate a persisted report/run.
            return

    def _generation_metadata(
        self, *, snapshot: FrozenEvidenceSnapshot, attempts: int, elapsed: float
    ) -> dict[str, object]:
        adapter = getattr(self._graph, "adapter", None)
        return {
            "attempts": attempts,
            "adapter": adapter.__class__.__name__ if adapter is not None else self._graph.__class__.__name__,
            "model": getattr(adapter, "model", None),
            "provider": getattr(adapter, "provider", None),
            "prompt_version": _PROMPT_VERSION,
            "schema_version": _SCHEMA_VERSION,
            "evidence_fingerprint": snapshot.evidence_fingerprint,
            "elapsed_ms": round(elapsed * 1000),
        }

    def _failure_metadata(
        self,
        *,
        snapshot: FrozenEvidenceSnapshot | None,
        attempts: int,
        elapsed: float,
        category: str,
    ) -> dict[str, object]:
        adapter = getattr(self._graph, "adapter", None)
        metadata: dict[str, object] = {
            "error_category": category,
            "attempts": attempts,
            "adapter": adapter.__class__.__name__ if adapter is not None else self._graph.__class__.__name__,
            "model": getattr(adapter, "model", None),
            "provider": getattr(adapter, "provider", None),
            "prompt_version": _PROMPT_VERSION,
            "schema_version": _SCHEMA_VERSION,
            "elapsed_ms": round(elapsed * 1000),
        }
        if snapshot is not None:
            metadata["evidence_fingerprint"] = snapshot.evidence_fingerprint
        return metadata

    @staticmethod
    def _validate_request(*, subject_kind: str, subject_key: str, focus: str) -> None:
        if not isinstance(subject_kind, str) or not subject_kind.strip() or len(subject_kind) > 64:
            raise ValueError("analysis subject_kind is invalid")
        if not isinstance(subject_key, str) or not subject_key.strip() or len(subject_key) > 128:
            raise ValueError("analysis subject_key is invalid")
        if not isinstance(focus, str) or len(focus) > 256:
            raise ValueError("analysis focus is invalid")
