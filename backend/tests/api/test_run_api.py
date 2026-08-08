"""Wave 0 strict route contract coverage for governed Alpha runs.

These tests verify the typed create/get/replay routes enforce server-owned
authority, principal scoping, strict DTO rejection, and safe projections.
Unknown and cross-principal runs return the identical 404 boundary.
"""
from __future__ import annotations

from typing import Any

import pytest

from tests.api.conftest import alpha_manifest


def _create_request_body(*, seed: int = 42, key: str = "idem-0000000000000001") -> dict[str, Any]:
    return {"idempotency_key": key, "manifest": alpha_manifest(seed=seed)}


def _request_with_principal(client: pytest.Any, body: dict[str, Any], principal: str = "researcher@example.com"):
    """POST create with a server-resolved principal injected via middleware state."""
    # TestClient doesn't run the auth middleware, so we patch request.state directly
    # by pre-setting the principal on the app's route handler via a wrapper.
    # Instead, we use the repository directly to simulate the middleware.
    return client


class TestCreateRun:
    def test_create_returns_server_generated_id_queued_status_and_committed_sequence(
        self, alpha_client: pytest.Any
    ) -> None:
        response = alpha_client.post(
            "/api/research/alpha/runs",
            json=_create_request_body(),
            headers={"X-Test-Principal": "researcher@example.com"},
        )
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["id"].startswith("arun_")
        assert data["status"] == "queued"
        assert data["last_event_seq"] == 1
        assert data["transition_version"] == 1
        assert len(data["snapshot_sha256"]) == 64
        assert len(data["manifest_sha256"]) == 64

    def test_create_rejects_undeclared_authority_fields(self, alpha_client: pytest.Any) -> None:
        body = _create_request_body()
        body["status"] = "running"  # client cannot set status
        response = alpha_client.post(
            "/api/research/alpha/runs",
            json=body,
            headers={"X-Test-Principal": "researcher@example.com"},
        )
        assert response.status_code == 422

    def test_create_with_incomplete_manifest_returns_preflight_failed(
        self, alpha_client: pytest.Any
    ) -> None:
        body = _create_request_body()
        del body["manifest"]["budgets"]
        response = alpha_client.post(
            "/api/research/alpha/runs",
            json=body,
            headers={"X-Test-Principal": "researcher@example.com"},
        )
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["status"] == "preflight_failed"
        assert "reason" in detail

    def test_create_is_idempotent_for_same_key_and_canonical_intent(
        self, alpha_client: pytest.Any
    ) -> None:
        headers = {"X-Test-Principal": "researcher@example.com"}
        first = alpha_client.post(
            "/api/research/alpha/runs",
            json=_create_request_body(key="idem-0000000000000002"),
            headers=headers,
        )
        assert first.status_code == 201
        second = alpha_client.post(
            "/api/research/alpha/runs",
            json=_create_request_body(key="idem-0000000000000002"),
            headers=headers,
        )
        assert second.status_code == 201
        assert first.json()["id"] == second.json()["id"]


class TestGetRun:
    def test_get_returns_safe_projection_without_principal(
        self, alpha_client: pytest.Any
    ) -> None:
        create = alpha_client.post(
            "/api/research/alpha/runs",
            json=_create_request_body(key="idem-0000000000000003"),
            headers={"X-Test-Principal": "researcher@example.com"},
        )
        run_id = create.json()["id"]
        response = alpha_client.get(
            f"/api/research/alpha/runs/{run_id}",
            headers={"X-Test-Principal": "researcher@example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "principal" not in data
        assert data["id"] == run_id

    def test_unknown_run_returns_404(self, alpha_client: pytest.Any) -> None:
        response = alpha_client.get(
            "/api/research/alpha/runs/arun_nonexistent",
            headers={"X-Test-Principal": "researcher@example.com"},
        )
        assert response.status_code == 404

    def test_cross_principal_run_returns_same_404_boundary(
        self, alpha_client: pytest.Any
    ) -> None:
        create = alpha_client.post(
            "/api/research/alpha/runs",
            json=_create_request_body(key="idem-0000000000000004"),
            headers={"X-Test-Principal": "alice@example.com"},
        )
        run_id = create.json()["id"]
        # A different principal gets the same 404, no existence oracle.
        response = alpha_client.get(
            f"/api/research/alpha/runs/{run_id}",
            headers={"X-Test-Principal": "bob@example.com"},
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestReplayRun:
    def test_replay_returns_run_snapshot_and_one_run_created_event(
        self, alpha_client: pytest.Any
    ) -> None:
        create = alpha_client.post(
            "/api/research/alpha/runs",
            json=_create_request_body(key="idem-0000000000000005"),
            headers={"X-Test-Principal": "researcher@example.com"},
        )
        run_id = create.json()["id"]
        response = alpha_client.get(
            f"/api/research/alpha/runs/{run_id}/replay",
            headers={"X-Test-Principal": "researcher@example.com"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["run"]["id"] == run_id
        assert data["snapshot"]["schema_version"] == "alpha-manifest-v1"
        assert len(data["events"]) == 1
        assert data["events"][0]["event_type"] == "run_created"
        assert data["events"][0]["seq"] == 1
        # Safe snapshot exposes all D-04 groups without policy internals.
        assert "dsl_version" in data["snapshot"]
        assert "policy_version" in data["snapshot"]
        assert "policy_digest" in data["snapshot"]
        # No raw policy internals (thresholds) leak.
        assert "thresholds" not in str(data["snapshot"])

    def test_replay_unknown_run_returns_404(self, alpha_client: pytest.Any) -> None:
        response = alpha_client.get(
            "/api/research/alpha/runs/arun_missing/replay",
            headers={"X-Test-Principal": "researcher@example.com"},
        )
        assert response.status_code == 404

    def test_replay_cross_principal_returns_same_404(
        self, alpha_client: pytest.Any
    ) -> None:
        create = alpha_client.post(
            "/api/research/alpha/runs",
            json=_create_request_body(key="idem-0000000000000006"),
            headers={"X-Test-Principal": "alice@example.com"},
        )
        run_id = create.json()["id"]
        response = alpha_client.get(
            f"/api/research/alpha/runs/{run_id}/replay",
            headers={"X-Test-Principal": "bob@example.com"},
        )
        assert response.status_code == 404


class TestStrictDTORejection:
    def test_create_rejects_short_idempotency_key(self, alpha_client: pytest.Any) -> None:
        body = _create_request_body(key="short")
        response = alpha_client.post(
            "/api/research/alpha/runs",
            json=body,
            headers={"X-Test-Principal": "researcher@example.com"},
        )
        assert response.status_code == 422

    def test_create_rejects_empty_manifest(self, alpha_client: pytest.Any) -> None:
        response = alpha_client.post(
            "/api/research/alpha/runs",
            json={"idempotency_key": "idem-0000000000000007", "manifest": {}},
            headers={"X-Test-Principal": "researcher@example.com"},
        )
        assert response.status_code == 422
