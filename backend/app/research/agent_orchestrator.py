"""Phase 48 Agent orchestrator — fixture-mode run + stage-1 boundary.

This module lives OUTSIDE the Phase 45 guard scope so it may import
``agent_provider`` / ``agent_fixture`` / ``agent_stage1`` / ``agent_stage2``
without tripping the Phase 45 research-only boundary guard
(``test_phase45_guard.py`` prohibits the ``provider`` token in any Phase 45
module source).
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Mapping

from app.research.agent_fixture import (
    FIXTURE_MODEL,
    FIXTURE_MODEL_VERSION,
    FIXTURE_PROVIDER,
    OfflineFixtureProvider,
    is_fixture_explicitly_selected,
)
from app.research.agent_provider import AgentProviderSeam
from app.research.agent_stage1 import Stage1Service
from app.research.agent_stage2 import Stage2Service
from app.research.preflight import preflight
from app.research.run_contract import (
    attempt_token_digest,
    checkpoint_state_checksum,
)

if TYPE_CHECKING:
    from app.research.run_service import ResearchRunService


async def run_fixture_mode(
    service: "ResearchRunService",
    run_id: str,
    *,
    principal: str,
    snapshot: Any,
    request: Any,
    snapshot_ref: Mapping[str, Any],
    settings: Mapping[str, Any] | None,
    attempt_token: str,
    fixture: Any | None = None,
    stop_after_stage: str | None = None,
) -> dict[str, Any]:
    """Run the deterministic offline-fixture Agent trace end-to-end.

    Phase 48-04 (AF-REQ-26). Orchestrates the full
    ``preflight -> stage1 -> stage2 -> AnalysisRecord`` chain over the
    fixture's canned responses with ZERO provider I/O, labeled
    non-production (``provider='offline_fixture'``) in every AnalysisRecord.

    Fail-closed gate: if the fixture is not explicitly selected
    (:func:`is_fixture_explicitly_selected`) this raises — the fixture is
    NEVER an implicit production fallback (R3 / D-48-04).

    Resumable: reads the checkpoint cursor via ``service.resume_agent_stage``
    and runs ONLY the stage(s) whose boundary is not yet committed.
    """
    if not is_fixture_explicitly_selected(settings):
        raise ValueError(
            "fixture mode requires an explicit non-default selector"
        )
    fixture = fixture if fixture is not None else OfflineFixtureProvider()
    repo = service._repository  # noqa: SLF001 — same-package service seam

    # 1. Preflight — the fixture gate passes because the fixture is explicit.
    preflight_result = preflight(snapshot, fixture_selected=True)
    if not preflight_result.passed:
        return {"stage": "preflight_failed", "preflight": preflight_result}

    run = repo.get_alpha_run(run_id, principal=principal)
    if run is None:
        raise ValueError("run not found for principal")
    if run["status"] != "running":
        raise ValueError("only a running run can execute fixture mode")

    result: dict[str, Any] = {"preflight_passed": True}

    # 2. Determine where to resume.
    stage = service.resume_agent_stage(
        run_id,
        principal=principal,
        expected_version=run["transition_version"],
        attempt_token=attempt_token,
    )

    if stage == "stage1":
        seam1 = AgentProviderSeam(
            generate_text=fixture.generate_text_for("stage1")
        )
        stage1_service = Stage1Service(
            provider=FIXTURE_PROVIDER,
            model=FIXTURE_MODEL,
            model_version=FIXTURE_MODEL_VERSION,
        )
        stage1_result = await stage1_service.run(
            request=request, seam=seam1, repo=repo, run_id=run_id
        )
        proposals_count = len(stage1_result.confirmed.kept)
        result["stage1"] = {
            "attempt_ordinal": stage1_result.attempt_ordinal,
            "proposals": proposals_count,
            "partial": stage1_result.partial,
        }
        run_after = repo.get_alpha_run(run_id, principal=principal)
        committed_event_seq = int(run_after["last_event_seq"]) + 1
        _append_stage1_boundary(
            service,
            repo,
            run_id,
            principal=principal,
            expected_version=run_after["transition_version"],
            attempt_token=attempt_token,
            run=run_after,
            committed_event_seq=committed_event_seq,
            proposals_count=proposals_count,
        )
        stage = "stage2"
        if stop_after_stage == "stage1":
            result["stage"] = "stage2_pending"
            return result

    if stage == "stage2":
        run_now = repo.get_alpha_run(run_id, principal=principal)
        seam2 = AgentProviderSeam(
            generate_text=fixture.generate_text_for("stage2")
        )
        stage2_service = Stage2Service(
            provider=FIXTURE_PROVIDER,
            model=FIXTURE_MODEL,
            model_version=FIXTURE_MODEL_VERSION,
        )
        await stage2_service.run(
            snapshot_ref=snapshot_ref,
            seam=seam2,
            repo=repo,
            run_id=run_id,
            run_service=service,
            principal=principal,
            expected_version=run_now["transition_version"],
            attempt_token=attempt_token,
        )
        result["stage"] = "complete"
        return result

    result["stage"] = "complete"
    return result


def _append_stage1_boundary(
    service: "ResearchRunService",
    repo: Any,
    run_id: str,
    *,
    principal: str,
    expected_version: int,
    attempt_token: str,
    run: Mapping[str, Any],
    committed_event_seq: int,
    proposals_count: int,
) -> dict[str, Any]:
    """Append the Stage 1 terminal event + ``stage2_pending`` checkpoint."""
    checkpoint_version = repo.next_checkpoint_version(run_id)
    inline_summary = {"stage": "stage1", "proposals": int(proposals_count)}
    state_checksum = checkpoint_state_checksum(
        run_id=run_id,
        checkpoint_version=checkpoint_version,
        committed_event_seq=committed_event_seq,
        stage="stage2_pending",
        snapshot_sha256=run["snapshot_sha256"],
        manifest_sha256=run["manifest_sha256"],
        referenced_candidate_ids=(),
        inline_summary=inline_summary,
        frontier_artifact_id=None,
    )
    return service.append_stage_boundary(
        repo,
        run_id=run_id,
        after_stage="stage1",
        event_id="aevt_" + uuid.uuid4().hex,
        event_type="stage1_completed",
        idempotency_key="stage1-boundary-" + uuid.uuid4().hex,
        actor="service",
        source="agent",
        payload={"stage": "stage1", "proposals": int(proposals_count)},
        committed_event_seq=committed_event_seq,
        checkpoint_stage="stage2_pending",
        snapshot_sha256=run["snapshot_sha256"],
        manifest_sha256=run["manifest_sha256"],
        state_checksum=state_checksum,
        principal=principal,
        expected_version=expected_version,
        expected_attempt_token_digest=attempt_token_digest(attempt_token),
        referenced_candidate_ids=(),
        inline_summary=inline_summary,
    )
