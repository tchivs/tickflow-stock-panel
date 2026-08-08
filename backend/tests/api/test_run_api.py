"""Typed API tests for governed Alpha run history/progress/retry/cancel (45-04-01).

These tests prove the Phase 45 API seam is one typed, principal-scoped JSON
contract for create/inspect/replay/retry/cancel/event-history/candidate-history/
progress. Every read/write resolves the server principal from host context;
cross-principal access returns the same 404 boundary as an unknown run
(T-45-12). API responses redact raw paths, principal, token plaintext, policy
internals, and unbounded diagnostics (T-45-08). Idempotency keys do not append
duplicate side-effect events (T-45-10).
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.research.repository import ResearchRepository
from app.research.run_service import ResearchRunService
from tests.api.conftest import alpha_manifest

_PRINCIPAL = "researcher@example.com"
_OTHER_PRINCIPAL = "attacker@example.com"


def _create_run(
    client: TestClient,
    *,
    manifest: dict[str, Any] | None = None,
    idempotency_key: str = "idem-api-000000000001",
    principal: str = _PRINCIPAL,
) -> dict[str, Any]:
    """POST /api/research/alpha/runs and return the JSON run body."""
    response = client.post(
        "/api/research/alpha/runs",
        json={"idempotency_key": idempotency_key, "manifest": manifest or alpha_manifest()},
        headers={"X-Test-Principal": principal},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _start_run(client: TestClient, run: dict[str, Any], *, principal: str = _PRINCIPAL) -> dict[str, Any]:
    """Start a run through the service seam (worker-owned path; not an API route in Phase 45)."""
    repository: ResearchRepository = client._alpha_repository  # type: ignore[attr-defined]
    service = ResearchRunService(repository)
    started = service.start_or_resume(
        run["id"],
        principal=principal,
        expected_version=run["transition_version"],
    )
    assert started is not None
    return dict(started)


# ================================================================
# Strict DTO / validation boundary (T-45-10)
# ================================================================


class TestStrictDtoBoundary:
    def test_create_rejects_extra_authority_field(self, alpha_client: TestClient) -> None:
        """Client-supplied status/snapshot_digest/event_seq must be rejected."""
        response = alpha_client.post(
            "/api/research/alpha/runs",
            json={
                "idempotency_key": "idem-strict-0000000001",
                "manifest": alpha_manifest(),
                "status": "running",  # authority field — rejected
            },
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 422

    def test_retry_rejects_extra_field(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-strict-0000000002")
        response = alpha_client.post(
            f"/api/research/alpha/runs/{run['id']}/retry",
            json={
                "idempotency_key": "idem-retry-00000000001",
                "manifest": alpha_manifest(seed=99),
                "snapshot_sha256": "0" * 64,  # authority field — rejected
            },
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 422

    def test_progress_update_rejects_extra_field(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-strict-0000000003")
        started = _start_run(alpha_client, run)
        response = alpha_client.post(
            f"/api/research/alpha/runs/{run['id']}/progress",
            json={
                "expected_version": started["transition_version"],
                "attempt_token": started["_attempt_token"],
                "folds_total": 10,
                "transition_version": 999,  # authority field — rejected
            },
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 422

    def test_cancel_rejects_status_field(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-strict-0000000004")
        response = alpha_client.post(
            f"/api/research/alpha/runs/{run['id']}/cancel",
            json={"expected_version": run["transition_version"], "status": "cancelled"},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 422


# ================================================================
# API status and 503 boundary
# ================================================================


class TestApiStatusBoundary:
    def test_503_when_service_not_initialized(self) -> None:
        from fastapi import FastAPI

        from app.api import research_alpha

        app = FastAPI()
        app.include_router(research_alpha.router)
        client = TestClient(app)
        response = client.get(
            "/api/research/alpha/runs/any",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 503

    def test_401_when_no_principal(self, alpha_client: TestClient) -> None:
        response = alpha_client.get("/api/research/alpha/runs/any")
        assert response.status_code == 401


# ================================================================
# Retry route (AF-REQ-16, D-06/D-07)
# ================================================================


class TestRetryRoute:
    def test_retry_creates_linked_child_preserving_parent(self, alpha_client: TestClient) -> None:
        parent = _create_run(alpha_client, idempotency_key="idem-retry-00000000001")
        response = alpha_client.post(
            f"/api/research/alpha/runs/{parent['id']}/retry",
            json={
                "idempotency_key": "idem-retry-child-00001",
                "manifest": alpha_manifest(seed=99),
            },
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 201, response.text
        child = response.json()
        assert child["id"] != parent["id"]
        assert child["retry_of_run_id"] == parent["id"]
        assert child["retry_attempt"] == 1
        assert child["status"] == "queued"
        # Parent is unchanged.
        parent_after = alpha_client.get(
            f"/api/research/alpha/runs/{parent['id']}",
            headers={"X-Test-Principal": _PRINCIPAL},
        ).json()
        assert parent_after["status"] == "queued"
        assert parent_after["retry_attempt"] == 0

    def test_retry_idempotent_same_key_returns_existing_child(self, alpha_client: TestClient) -> None:
        parent = _create_run(alpha_client, idempotency_key="idem-retry-00000000002")
        body = {
            "idempotency_key": "idem-retry-child-00002",
            "manifest": alpha_manifest(seed=99),
        }
        first = alpha_client.post(
            f"/api/research/alpha/runs/{parent['id']}/retry",
            json=body,
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert first.status_code == 201
        second = alpha_client.post(
            f"/api/research/alpha/runs/{parent['id']}/retry",
            json=body,
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert second.status_code == 201
        assert second.json()["id"] == first.json()["id"]

    def test_retry_unknown_run_returns_404(self, alpha_client: TestClient) -> None:
        response = alpha_client.post(
            "/api/research/alpha/runs/arun_nonexistent/retry",
            json={
                "idempotency_key": "idem-retry-unknown-001",
                "manifest": alpha_manifest(),
            },
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 404

    def test_retry_cross_principal_returns_404(self, alpha_client: TestClient) -> None:
        parent = _create_run(alpha_client, idempotency_key="idem-retry-00000000003")
        response = alpha_client.post(
            f"/api/research/alpha/runs/{parent['id']}/retry",
            json={
                "idempotency_key": "idem-retry-xp-000001",
                "manifest": alpha_manifest(),
            },
            headers={"X-Test-Principal": _OTHER_PRINCIPAL},
        )
        assert response.status_code == 404

    def test_retry_preflight_failure_returns_422(self, alpha_client: TestClient) -> None:
        parent = _create_run(alpha_client, idempotency_key="idem-retry-00000000004")
        bad_manifest = alpha_manifest()
        del bad_manifest["universe"]
        response = alpha_client.post(
            f"/api/research/alpha/runs/{parent['id']}/retry",
            json={
                "idempotency_key": "idem-retry-pf-000001",
                "manifest": bad_manifest,
            },
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 422
    def test_retry_same_key_with_changed_manifest_returns_409(self, alpha_client: TestClient) -> None:
        parent = _create_run(alpha_client, idempotency_key="idem-retry-00000000005")
        body = {
            "idempotency_key": "idem-retry-child-conflict-001",
            "manifest": alpha_manifest(seed=99),
        }
        first = alpha_client.post(
            f"/api/research/alpha/runs/{parent['id']}/retry",
            json=body,
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert first.status_code == 201
        changed = {**body, "manifest": alpha_manifest(seed=100)}
        second = alpha_client.post(
            f"/api/research/alpha/runs/{parent['id']}/retry",
            json=changed,
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert second.status_code == 409



# ================================================================
# Cancel route (AF-REQ-16, D-07)
# ================================================================


class TestCancelRoute:
    def test_cancel_queued_run_appends_cancel_requested(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-cancel-0000000001")
        response = alpha_client.post(
            f"/api/research/alpha/runs/{run['id']}/cancel",
            json={"expected_version": run["transition_version"]},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 200, response.text
        cancelled = response.json()
        assert cancelled["status"] == "cancel_requested"
        assert cancelled["transition_version"] == run["transition_version"] + 1

    def test_cancel_is_idempotent_no_duplicate_event(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-cancel-0000000002")
        body = {"expected_version": run["transition_version"], "idempotency_key": "cancel-key-000000001"}
        first = alpha_client.post(
            f"/api/research/alpha/runs/{run['id']}/cancel",
            json=body,
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert first.status_code == 200
        version_after_first = first.json()["transition_version"]
        # Repeat with the same idempotency key — no new event.
        second = alpha_client.post(
            f"/api/research/alpha/runs/{run['id']}/cancel",
            json=body,
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert second.status_code == 200
        assert second.json()["transition_version"] == version_after_first
        events = alpha_client.get(
            f"/api/research/alpha/runs/{run['id']}/events",
            headers={"X-Test-Principal": _PRINCIPAL},
        ).json()
        cancel_events = [e for e in events if e["event_type"] == "cancel_requested"]
        assert len(cancel_events) == 1

    def test_cancel_terminal_returns_current_state(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-cancel-0000000003")
        # Transition to a terminal state via the service seam.
        repository: ResearchRepository = alpha_client._alpha_repository  # type: ignore[attr-defined]
        service = ResearchRunService(repository)
        service.transition(
            run["id"],
            principal=_PRINCIPAL,
            from_status="queued",
            to_status="failed",
            expected_version=run["transition_version"],
            terminal_reason="boom",
        )
        terminal = service.get(run["id"], principal=_PRINCIPAL)
        assert terminal is not None
        response = alpha_client.post(
            f"/api/research/alpha/runs/{run['id']}/cancel",
            json={"expected_version": terminal["transition_version"]},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "failed"

    def test_cancel_unknown_run_returns_404(self, alpha_client: TestClient) -> None:
        response = alpha_client.post(
            "/api/research/alpha/runs/arun_nonexistent/cancel",
            json={"expected_version": 1},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 404

    def test_cancel_cross_principal_returns_404(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-cancel-0000000004")
        response = alpha_client.post(
            f"/api/research/alpha/runs/{run['id']}/cancel",
            json={"expected_version": run["transition_version"]},
            headers={"X-Test-Principal": _OTHER_PRINCIPAL},
        )
        assert response.status_code == 404
    def test_cancel_stale_version_returns_409(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-cancel-0000000005")
        response = alpha_client.post(
            f"/api/research/alpha/runs/{run['id']}/cancel",
            json={"expected_version": run["transition_version"] - 1},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 409


# ================================================================
# Event history route (D-09, T-45-11)
# ================================================================


class TestEventHistoryRoute:
    def test_events_ordered_by_monotonic_sequence(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-event-0000000001")
        repository: ResearchRepository = alpha_client._alpha_repository  # type: ignore[attr-defined]
        service = ResearchRunService(repository)
        started = service.start_or_resume(
            run["id"], principal=_PRINCIPAL, expected_version=run["transition_version"],
        )
        # Append extra events to build a longer history.
        service.append_event(
            run_id=run["id"], principal=_PRINCIPAL, event_type="stage_started",
            entity_kind="stage", entity_id="stage-1", idempotency_key="evt-extra-1",
            actor="worker", source="worker", payload={"stage": "generation"},
        )
        response = alpha_client.get(
            f"/api/research/alpha/runs/{run['id']}/events",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 200, response.text
        events = response.json()
        seqs = [e["seq"] for e in events]
        assert seqs == sorted(seqs)
        assert seqs[0] == 1  # run_created
        assert len(events) >= 3
        # No raw payload internals.
        for evt in events:
            assert "payload" not in evt
            assert "idempotency_key" not in evt
            assert "actor" not in evt

    def test_events_after_sequence_filter(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-event-0000000002")
        repository: ResearchRepository = alpha_client._alpha_repository  # type: ignore[attr-defined]
        service = ResearchRunService(repository)
        service.start_or_resume(
            run["id"], principal=_PRINCIPAL, expected_version=run["transition_version"],
        )
        response = alpha_client.get(
            f"/api/research/alpha/runs/{run['id']}/events?after_sequence=1",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 200
        events = response.json()
        assert all(e["seq"] > 1 for e in events)
        assert len(events) == 1  # run_started only

    def test_events_bounded_limit(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-event-0000000003")
        repository: ResearchRepository = alpha_client._alpha_repository  # type: ignore[attr-defined]
        service = ResearchRunService(repository)
        for i in range(1, 6):
            service.append_event(
                run_id=run["id"], principal=_PRINCIPAL, event_type="candidate_appended",
                entity_kind="candidate", entity_id=f"cand-{i}", idempotency_key=f"evt-lim-{i}",
                actor="worker", source="worker", payload={"ordinal": i},
            )
        response = alpha_client.get(
            f"/api/research/alpha/runs/{run['id']}/events?limit=3",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 200
        assert len(response.json()) == 3

    def test_events_unknown_run_returns_404(self, alpha_client: TestClient) -> None:
        response = alpha_client.get(
            "/api/research/alpha/runs/arun_nonexistent/events",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 404

    def test_events_cross_principal_returns_404(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-event-0000000004")
        response = alpha_client.get(
            f"/api/research/alpha/runs/{run['id']}/events",
            headers={"X-Test-Principal": _OTHER_PRINCIPAL},
        )
        assert response.status_code == 404


# ================================================================
# Candidate history route (AF-REQ-04)
# ================================================================


class TestCandidateHistoryRoute:
    def _seed_candidates(self, client: TestClient, run_id: str) -> None:
        repository: ResearchRepository = client._alpha_repository  # type: ignore[attr-defined]
        statuses = ["invalid", "duplicate", "generated", "failed", "admitted", "rejected"]
        for idx, status in enumerate(statuses, start=1):
            repository.append_candidate_attempt(
                run_id=run_id,
                candidate_id=f"cand-api-{idx}",
                attempt_ordinal=idx,
                candidate_digest="a" * 60 + f"{idx:04d}",
                canonical_expression=f"rank(close) + {idx}",
                ast_signature=f"ast-{idx}",
                shape_signature=f"shape-{idx}",
                dsl_version="factor-dsl-v1",
                operation="generate",
                seed=42,
                step=idx,
                status=status,
                reason={"note": f"candidate {idx}"},
            )

    def test_candidates_retain_all_attempt_statuses(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-cand-0000000001")
        self._seed_candidates(alpha_client, run["id"])
        response = alpha_client.get(
            f"/api/research/alpha/runs/{run['id']}/candidates",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 200, response.text
        candidates = response.json()
        assert len(candidates) == 6
        statuses = [c["status"] for c in candidates]
        assert statuses == ["invalid", "duplicate", "generated", "failed", "admitted", "rejected"]
        ordinals = [c["attempt_ordinal"] for c in candidates]
        assert ordinals == [1, 2, 3, 4, 5, 6]
        # No raw reason internals or evidence paths leaked.
        for cand in candidates:
            assert "reason" not in cand
            assert "evidence_artifact_id" not in cand

    def test_candidates_bounded_limit(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-cand-0000000002")
        self._seed_candidates(alpha_client, run["id"])
        response = alpha_client.get(
            f"/api/research/alpha/runs/{run['id']}/candidates?limit=2",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_candidates_unknown_run_returns_404(self, alpha_client: TestClient) -> None:
        response = alpha_client.get(
            "/api/research/alpha/runs/arun_nonexistent/candidates",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 404

    def test_candidates_cross_principal_returns_404(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-cand-0000000003")
        response = alpha_client.get(
            f"/api/research/alpha/runs/{run['id']}/candidates",
            headers={"X-Test-Principal": _OTHER_PRINCIPAL},
        )
        assert response.status_code == 404


# ================================================================
# Progress route (D-11, T-45-08)
# ================================================================


class TestProgressRoute:
    def test_progress_returns_four_counters(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-prog-0000000001")
        started = _start_run(alpha_client, run)
        alpha_client.post(
            f"/api/research/alpha/runs/{run['id']}/progress",
            json={
                "expected_version": started["transition_version"],
                "attempt_token": started["_attempt_token"],
                "candidate_attempts_total": 100,
                "candidate_attempts_completed": 50,
                "folds_total": 10,
                "folds_completed": 5,
            },
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        response = alpha_client.get(
            f"/api/research/alpha/runs/{run['id']}/progress",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 200, response.text
        progress = response.json()
        assert progress["candidate_attempts_total"] == 100
        assert progress["candidate_attempts_completed"] == 50
        assert progress["folds_total"] == 10
        assert progress["folds_completed"] == 5

    def test_progress_fresh_run_has_zero_counters(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-prog-0000000002")
        response = alpha_client.get(
            f"/api/research/alpha/runs/{run['id']}/progress",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 200
        progress = response.json()
        assert progress["candidate_attempts_total"] == 0
        assert progress["candidate_attempts_completed"] == 0
        assert progress["folds_total"] == 0
        assert progress["folds_completed"] == 0

    def test_progress_update_requires_valid_token(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-prog-0000000003")
        started = _start_run(alpha_client, run)
        response = alpha_client.post(
            f"/api/research/alpha/runs/{run['id']}/progress",
            json={
                "expected_version": started["transition_version"],
                "attempt_token": "deadbeef" * 8,  # invalid token
                "folds_total": 10,
            },
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 409

    def test_progress_update_stale_version_returns_409(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-prog-0000000004")
        started = _start_run(alpha_client, run)
        response = alpha_client.post(
            f"/api/research/alpha/runs/{run['id']}/progress",
            json={
                "expected_version": 999,  # stale
                "attempt_token": started["_attempt_token"],
                "folds_total": 10,
            },
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 409

    def test_progress_unknown_run_returns_404(self, alpha_client: TestClient) -> None:
        response = alpha_client.get(
            "/api/research/alpha/runs/arun_nonexistent/progress",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert response.status_code == 404

    def test_progress_cross_principal_returns_404(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-prog-0000000005")
        response = alpha_client.get(
            f"/api/research/alpha/runs/{run['id']}/progress",
            headers={"X-Test-Principal": _OTHER_PRINCIPAL},
        )
        assert response.status_code == 404


# ================================================================
# Redaction — no principal, token, path, or secret leakage (T-45-08)
# ================================================================


class TestRedaction:
    def test_run_projection_has_no_principal(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-redact-000000001")
        response = alpha_client.get(
            f"/api/research/alpha/runs/{run['id']}",
            headers={"X-Test-Principal": _PRINCIPAL},
        ).json()
        assert "principal" not in response
        assert _PRINCIPAL not in str(response)

    def test_progress_has_no_token_plaintext(self, alpha_client: TestClient) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-redact-000000002")
        started = _start_run(alpha_client, run)
        token = started["_attempt_token"]
        alpha_client.post(
            f"/api/research/alpha/runs/{run['id']}/progress",
            json={
                "expected_version": started["transition_version"],
                "attempt_token": token,
                "folds_total": 10,
            },
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        progress = alpha_client.get(
            f"/api/research/alpha/runs/{run['id']}/progress",
            headers={"X-Test-Principal": _PRINCIPAL},
        ).json()
        assert "_attempt_token" not in progress
        assert token not in str(progress)


# ================================================================
# Fresh-process replay through the API (D-08)
# ================================================================


class TestRestartReplay:
    def test_progress_readable_after_fresh_service_instance(
        self,
        alpha_client: TestClient,
        panel_db: Any,
        tmp_path: Any,
    ) -> None:
        run = _create_run(alpha_client, idempotency_key="idem-restart-00000001")
        started = _start_run(alpha_client, run)
        alpha_client.post(
            f"/api/research/alpha/runs/{run['id']}/progress",
            json={
                "expected_version": started["transition_version"],
                "attempt_token": started["_attempt_token"],
                "candidate_attempts_total": 50,
                "candidate_attempts_completed": 25,
                "folds_total": 10,
                "folds_completed": 5,
            },
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        # Simulate a fresh process: rebuild the service from the same DB path.
        fresh_repository = ResearchRepository(
            panel_db,
            clock=alpha_client._alpha_clock,  # type: ignore[attr-defined]
            artifact_root=tmp_path / "alpha_artifacts_fresh",
        )
        fresh_service = ResearchRunService(fresh_repository)
        fresh_run = fresh_service.get(run["id"], principal=_PRINCIPAL)
        assert fresh_run is not None
        assert fresh_run["candidate_attempts_total"] == 50
        assert fresh_run["folds_completed"] == 5
