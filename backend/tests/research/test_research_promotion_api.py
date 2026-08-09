"""Phase 49 wave 2 — principal-scoped promotion ticket API seam (49-02-03).

Covers the inspect + register action surface (AF-REQ-17 SC4): the server-
resolved principal is the only identity source, cross-principal access returns
the same 404 boundary as an unknown resource (T-45-12), and expired/conflicted/
missing tickets map to bounded status codes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import research_promotion
from app.research.admission import ADMISSION_POLICY_VERSION
from app.research.catalog import ExperimentCatalog
from app.research.factor_dsl import DSL_VERSION
from app.research.factor_registry import FactorRegistry
from app.research.repository import ResearchRepository
from app.research.run_contract import freeze_input_snapshot
from tests.api.conftest import DeterministicClock

_FAR_FUTURE = "2099-12-31T23:59:59+00:00"


# ---------------------------------------------------------------------
# Fixtures + frozen-evidence seed (mirrors test_promotion_consume.py).
# ---------------------------------------------------------------------


def _manifest() -> dict[str, Any]:
    return {
        "dsl": {"version": "factor-dsl-v1"},
        "grammar": {"fingerprint": "a" * 64, "version": "grammar-v1"},
        "vocabulary": {"fingerprint": "b" * 64, "size": 64},
        "policy": {"version": ADMISSION_POLICY_VERSION, "thresholds": {"min_ic": 0.02}},
        "budgets": {"max_expressions": 1000, "max_candidates": 200},
        "objective": {"name": "sharpe", "direction": "maximize"},
        "universe": {
            "name": "cn-a-share",
            "asset_type": "stock",
            "membership_fingerprint": "c" * 64,
        },
        "measured_window": {"start": "2020-01-01", "end": "2023-12-31", "calendar": "SSE"},
        "fold_geometry": {"train_size": 120, "gap_size": 5, "test_size": 20, "n_folds": 10},
        "code_manifest": {
            "fingerprint": "d" * 64,
            "build_fingerprint": "e" * 64,
            "dependency_fingerprint": "f" * 64,
        },
        "data_manifest": {"fingerprint": "g" * 64, "partition_fingerprint": "h" * 64},
        "seed": 42,
    }


@pytest.fixture
def clock() -> DeterministicClock:
    return DeterministicClock()


@pytest.fixture
def client(tmp_path: Path, clock: DeterministicClock) -> TestClient:
    repo = ResearchRepository(
        tmp_path / "op.db", clock=clock, artifact_root=tmp_path / "art"
    )
    repo.migrate()
    app = FastAPI()

    @app.middleware("http")
    async def inject_test_principal(request, call_next):
        principal = request.headers.get("X-Test-Principal")
        if principal:
            request.state.reviewer_principal = principal
        return await call_next(request)

    app.state.research_repository = repo
    app.state.factor_registry = FactorRegistry(repo)
    app.state.experiment_catalog = ExperimentCatalog(repo)
    app.include_router(research_promotion.router)
    c = TestClient(app)
    c._repo = repo  # type: ignore[attr-defined]
    c._registry = app.state.factor_registry  # type: ignore[attr-defined]
    c._catalog = app.state.experiment_catalog  # type: ignore[attr-defined]
    return c


def _seed(client: TestClient, *, run_id: str = "run-api") -> str:
    repo: ResearchRepository = client._repo  # type: ignore[attr-defined]
    registry: FactorRegistry = client._registry  # type: ignore[attr-defined]
    snapshot = freeze_input_snapshot(
        manifest=_manifest(), created_at="2026-08-08T00:00:00+00:00"
    )
    repo.create_alpha_run(
        run_id=run_id,
        principal="researcher@example.com",
        idempotency_key=f"idem-{run_id}",
        snapshot=snapshot,
        event_id=f"evt-{run_id}",
    )
    repo.append_candidate_attempt(
        run_id=run_id,
        candidate_id="acand_api",
        attempt_ordinal=1,
        candidate_digest="9" * 64,
        canonical_expression="close",
        ast_signature="ast-close",
        shape_signature="shape-close",
        dsl_version=DSL_VERSION,
        operation="generate",
        seed=0,
        step=0,
        status="admitted",
        reason={"verdict": "admitted"},
    )
    exploratory = registry.create_exploratory_revision(
        run_id=run_id,
        candidate_id="acand_api",
        candidate_digest="9" * 64,
        canonical_expression="close",
        dsl_version=DSL_VERSION,
        fields=("close",),
        step=0,
    )
    repo.insert_admission_verdict(
        revision_id=exploratory.id,
        policy_version=ADMISSION_POLICY_VERSION,
        verdict="admitted",
        reason="all gates passed",
        gates_json=[{"gate": "no_lookahead", "passed": True}],
        candidate_trail_json={
            "provenance": {
                "kind": "alpha_exploratory",
                "run_id": run_id,
                "candidate_id": "acand_api",
                "candidate_digest": "9" * 64,
            }
        },
        resolved_universe_json={"method": "fixture", "membership_fingerprint": "c" * 64},
        input_snapshot_sha256="0" * 64,
    )
    record = repo.record_alpha_fold_evidence(
        run_id=run_id,
        candidate_digest="9" * 64,
        fold_index=9,
        is_oos=True,
        revision_id=exploratory.id,
        train_start="2020-01-01",
        train_end="2022-12-31",
        test_start="2023-01-01",
        test_end="2023-12-31",
        membership_fingerprint="c" * 64,
        declared_fingerprints={"membership": "c" * 64},
        stats={"sharpe": 1.2},
    )
    repo.append_candidate_attempt(
        run_id=run_id,
        candidate_id="acand_api_oos",
        attempt_ordinal=2,
        candidate_digest="9" * 64,
        canonical_expression="close",
        ast_signature="ast-close",
        shape_signature="shape-close",
        dsl_version=DSL_VERSION,
        operation="selection_oos",
        seed=0,
        step=0,
        status="selection_oos",
        reason={"selection_oos": True, "fold_evidence_id": record["id"]},
    )
    return run_id


def _headers(principal: str = "researcher@example.com") -> dict[str, str]:
    return {"X-Test-Principal": principal}


# =====================================================================
# Issue route
# =====================================================================


def test_issue_returns_201_bound_to_server_principal(client: TestClient) -> None:
    _seed(client)
    response = client.post(
        "/api/research/runs/run-api/candidates/acand_api/promotion-ticket",
        headers=_headers(),
        json={"expires_at": _FAR_FUTURE, "idempotency_key": "idem-api-issue-0001"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["run_id"] == "run-api"
    assert body["candidate_id"] == "acand_api"
    assert body["status"] == "issued"
    assert body["reviewer"] == "researcher@example.com"


def test_issue_cross_principal_returns_404_like_unknown_run(client: TestClient) -> None:
    _seed(client)
    # Another principal cannot see the run → same 404 as an unknown run.
    response = client.post(
        "/api/research/runs/run-api/candidates/acand_api/promotion-ticket",
        headers=_headers("intruder@example.com"),
        json={"expires_at": _FAR_FUTURE, "idempotency_key": "idem-api-xpr-0001"},
    )
    assert response.status_code == 404
    # And an unknown run is also 404 with the same shape.
    unknown = client.post(
        "/api/research/runs/no-such-run/candidates/acand_api/promotion-ticket",
        headers=_headers(),
        json={"expires_at": _FAR_FUTURE, "idempotency_key": "idem-api-unk-0001"},
    )
    assert unknown.status_code == 404


def test_issue_unpromotable_candidate_returns_422(client: TestClient) -> None:
    repo: ResearchRepository = client._repo  # type: ignore[attr-defined]
    snapshot = freeze_input_snapshot(
        manifest=_manifest(), created_at="2026-08-08T00:00:00+00:00"
    )
    repo.create_alpha_run(
        run_id="run-bare",
        principal="researcher@example.com",
        idempotency_key="idem-run-bare",
        snapshot=snapshot,
        event_id="evt-run-bare",
    )
    response = client.post(
        "/api/research/runs/run-bare/candidates/missing/promotion-ticket",
        headers=_headers(),
        json={"expires_at": _FAR_FUTURE, "idempotency_key": "idem-api-bare-0001"},
    )
    assert response.status_code == 422


def test_issue_requires_authenticated_principal(client: TestClient) -> None:
    _seed(client)
    response = client.post(
        "/api/research/runs/run-api/candidates/acand_api/promotion-ticket",
        json={"expires_at": _FAR_FUTURE, "idempotency_key": "idem-api-noauth-001"},
    )
    assert response.status_code == 401


# =====================================================================
# Inspect route
# =====================================================================


def test_inspect_returns_projection_for_owner(client: TestClient) -> None:
    _seed(client)
    issued = client.post(
        "/api/research/runs/run-api/candidates/acand_api/promotion-ticket",
        headers=_headers(),
        json={"expires_at": _FAR_FUTURE, "idempotency_key": "idem-api-inspect-001"},
    ).json()
    response = client.get(
        f"/api/research/promotion-tickets/{issued['id']}", headers=_headers()
    )
    assert response.status_code == 200
    assert response.json()["id"] == issued["id"]


def test_inspect_cross_principal_returns_404(client: TestClient) -> None:
    _seed(client)
    issued = client.post(
        "/api/research/runs/run-api/candidates/acand_api/promotion-ticket",
        headers=_headers(),
        json={"expires_at": _FAR_FUTURE, "idempotency_key": "idem-api-inspectx-001"},
    ).json()
    response = client.get(
        f"/api/research/promotion-tickets/{issued['id']}",
        headers=_headers("intruder@example.com"),
    )
    assert response.status_code == 404


def test_inspect_missing_ticket_returns_404(client: TestClient) -> None:
    response = client.get(
        "/api/research/promotion-tickets/aptk_nope", headers=_headers()
    )
    assert response.status_code == 404


# =====================================================================
# Consume (register) route
# =====================================================================


def test_consume_returns_200_with_formal_revision_and_provenance(
    client: TestClient,
) -> None:
    _seed(client)
    issued = client.post(
        "/api/research/runs/run-api/candidates/acand_api/promotion-ticket",
        headers=_headers(),
        json={"expires_at": _FAR_FUTURE, "idempotency_key": "idem-api-consume-001"},
    ).json()
    response = client.post(
        f"/api/research/promotion-tickets/{issued['id']}:consume",
        headers=_headers(),
        json={"idempotency_key": "idem-api-consume-001"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ticket_id"] == issued["id"]
    assert body["revision_number"] == 1
    assert body["provenance"]["kind"] == "alpha_promoted"
    assert body["provenance"]["promotion_ticket_id"] == issued["id"]
    assert body["experiment_id"] is not None


def test_consume_idempotent_returns_same_revision(client: TestClient) -> None:
    _seed(client)
    issued = client.post(
        "/api/research/runs/run-api/candidates/acand_api/promotion-ticket",
        headers=_headers(),
        json={"expires_at": _FAR_FUTURE, "idempotency_key": "idem-api-idem-0001"},
    ).json()
    first = client.post(
        f"/api/research/promotion-tickets/{issued['id']}:consume",
        headers=_headers(),
        json={"idempotency_key": "idem-api-idem-0001"},
    )
    second = client.post(
        f"/api/research/promotion-tickets/{issued['id']}:consume",
        headers=_headers(),
        json={"idempotency_key": "idem-api-idem-0001"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["revision_id"] == second.json()["revision_id"]


def test_consume_missing_ticket_returns_404(client: TestClient) -> None:
    response = client.post(
        "/api/research/promotion-tickets/aptk_nope:consume",
        headers=_headers(),
        json={"idempotency_key": "idem-api-missing-0001"},
    )
    assert response.status_code == 404


def test_consume_conflicted_ticket_returns_409_with_bounded_reason(
    client: TestClient, clock: DeterministicClock
) -> None:
    _seed(client)
    issued = client.post(
        "/api/research/runs/run-api/candidates/acand_api/promotion-ticket",
        headers=_headers(),
        json={"expires_at": clock.now_iso(), "idempotency_key": "idem-api-conflict-001"},
    ).json()
    clock.advance()  # now > expires_at → consume detects expiry
    response = client.post(
        f"/api/research/promotion-tickets/{issued['id']}:consume",
        headers=_headers(),
        json={"idempotency_key": "idem-api-conflict-001"},
    )
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "expired"
    assert "reason" in detail
