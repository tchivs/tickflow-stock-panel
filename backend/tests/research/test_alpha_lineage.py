"""Phase 50-01 — lineage read projection + evidence classification + SSE-read surface.

Covers:
  * ``repository.list_run_lineage`` / ``service.list_lineage`` (50-01-01, SC2 read half)
  * ``projections.lineage`` / ``projections.evidence_classification`` + DTOs (50-01-02, SC4)
  * ``GET /runs/{id}/lineage`` + ``GET /runs/{id}/candidates/{cid}/evidence-classification``
    (50-01-03, read surface)

The lineage table (``research_alpha_candidate_lineage``) is append-only with
no UPDATE/DELETE triggers (``migrations.py``); this plan adds the missing READ
projection.  Cross-principal reads return the same empty boundary as an
unknown run (T-45-12).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import research_alpha
from app.research import projections
from app.research.repository import ResearchRepository
from app.research.run_contract import freeze_input_snapshot
from app.research.run_service import ResearchRunService
from tests.research.conftest import DeterministicClock

_PRINCIPAL = "researcher@example.com"


# ---------------------------------------------------------------------
# Helpers (mirrors test_run_contract.py minimal seed shapes).
# ---------------------------------------------------------------------


def _sample_manifest(*, seed: int = 42) -> dict[str, Any]:
    return {
        "dsl": {"version": "factor-dsl-v1"},
        "grammar": {"fingerprint": "a" * 64, "version": "grammar-v1"},
        "vocabulary": {"fingerprint": "b" * 64, "size": 64},
        "policy": {"version": "admission-v1", "thresholds": {"min_ic": 0.02}},
        "budgets": {"max_expressions": 1000, "max_candidates": 200},
        "objective": {"name": "sharpe", "direction": "maximize"},
        "universe": {"name": "cn-a-share", "asset_type": "stock", "membership_fingerprint": "c" * 64},
        "measured_window": {"start": "2020-01-01", "end": "2023-12-31", "calendar": "SSE"},
        "fold_geometry": {"train_size": 120, "gap_size": 5, "test_size": 20, "n_folds": 10},
        "code_manifest": {"fingerprint": "d" * 64, "build_fingerprint": "e" * 64, "dependency_fingerprint": "f" * 64},
        "data_manifest": {"fingerprint": "g" * 64, "partition_fingerprint": "h" * 64},
        "seed": seed,
    }


def _make_run(
    repo: ResearchRepository,
    clock: DeterministicClock,
    *,
    run_id: str = "run-lin-0",
    idempotency_key: str = "idem-lin-0000000001",
    principal: str = _PRINCIPAL,
) -> dict[str, Any]:
    snapshot = freeze_input_snapshot(manifest=_sample_manifest(), created_at=clock.now_iso())
    clock.advance()
    return repo.create_alpha_run(
        run_id=run_id, principal=principal, idempotency_key=idempotency_key,
        snapshot=snapshot, event_id="aevt-" + run_id,
    )


def _candidate_params(
    *, run_id: str, candidate_id: str, ordinal: int, digest: str | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "candidate_id": candidate_id,
        "attempt_ordinal": ordinal,
        "candidate_digest": digest or ("a" * 60 + f"{ordinal:04d}"),
        "canonical_expression": f"rank(close) + {ordinal}",
        "ast_signature": f"ast-{ordinal}",
        "shape_signature": f"shape-{ordinal}",
        "dsl_version": "factor-dsl-v1",
        "operation": "generate",
        "seed": 42,
        "step": ordinal,
        "status": "admitted",
        "reason": {"note": f"candidate {ordinal}"},
    }


def _seed_lineage(
    repo: ResearchRepository, clock: DeterministicClock, *, run_id: str = "run-lin-seed"
) -> dict[str, Any]:
    """Seed a run with two candidates + one mutation lineage edge; return the run row."""
    run = _make_run(repo, clock, run_id=run_id)
    repo.append_candidate_attempt(**_candidate_params(run_id=run["id"], candidate_id="cand-par", ordinal=1))
    repo.append_candidate_attempt(**_candidate_params(run_id=run["id"], candidate_id="cand-chi", ordinal=2))
    repo.append_candidate_lineage(
        run_id=run["id"], lineage_id="lin-1",
        child_attempt_id="cand-chi", parent_attempt_id="cand-par",
        edge_ordinal=0, operation="mutation",
    )
    return run


# ================================================================
# Task 50-01-01: repository.list_run_lineage + service.list_lineage
# ================================================================


class TestListRunLineageRepository:
    def test_list_lineage_ordered_edges_with_joined_candidates(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-ord")
        repo = alpha_run_repository
        for ordinal in (1, 2, 3):
            repo.append_candidate_attempt(
                **_candidate_params(run_id=run["id"], candidate_id=f"c-{ordinal}", ordinal=ordinal)
            )
        # Insert edges out of order; read must return by edge_ordinal then id.
        repo.append_candidate_lineage(
            run_id=run["id"], lineage_id="lin-b",
            child_attempt_id="c-3", parent_attempt_id="c-2",
            edge_ordinal=1, operation="crossover",
        )
        repo.append_candidate_lineage(
            run_id=run["id"], lineage_id="lin-a",
            child_attempt_id="c-2", parent_attempt_id="c-1",
            edge_ordinal=0, operation="mutation",
        )
        edges = repo.list_run_lineage(run["id"])
        assert [e["lineage_id"] for e in edges] == ["lin-a", "lin-b"]
        first = edges[0]
        assert first["edge_ordinal"] == 0
        assert first["operation"] == "mutation"
        # Joined child + parent carry the bounded candidate fields.
        for field in ("canonical_expression", "operation", "seed", "step", "status", "candidate_digest", "dsl_version", "attempt_ordinal"):
            assert field in first["child"]
            assert field in first["parent"]
        assert first["child"]["attempt_ordinal"] == 2
        assert first["parent"]["attempt_ordinal"] == 1

    def test_principal_fence_cross_principal_returns_empty(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _seed_lineage(alpha_run_repository, deterministic_clock, run_id="run-pc")
        cross = alpha_run_repository.list_run_lineage(run["id"], principal="attacker@example.com")
        assert cross == []
        # Same boundary as a genuinely unknown run.
        unknown = alpha_run_repository.list_run_lineage("run-nonexistent")
        assert unknown == []

    def test_list_lineage_is_read_only(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _seed_lineage(alpha_run_repository, deterministic_clock, run_id="run-ro")
        before = alpha_run_repository.list_run_lineage(run["id"])
        alpha_run_repository.list_run_lineage(run["id"], principal=_PRINCIPAL)
        # Re-read: identical — no INSERT/UPDATE/DELETE side effect.
        after = alpha_run_repository.list_run_lineage(run["id"])
        assert before == after
        assert len(after) == 1


class TestListLineageService:
    def test_service_list_lineage_delegates_with_principal_fence(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _seed_lineage(alpha_run_repository, deterministic_clock, run_id="run-svc")
        service = ResearchRunService(alpha_run_repository)
        edges = service.list_lineage(run["id"], principal=_PRINCIPAL)
        assert len(edges) == 1
        assert edges[0]["operation"] == "mutation"
        # Cross-principal: empty boundary, never a leak.
        assert service.list_lineage(run["id"], principal="other@example.com") == []
        # Unknown run: empty.
        assert service.list_lineage("no-such-run", principal=_PRINCIPAL) == []


# ================================================================
# Task 50-01-02: projections.lineage + projections.evidence_classification
# ================================================================

_DECLARED_KEYS = ("panel", "membership", "source_field", "warmup", "missing_data", "signal")


def _full_declared_fingerprints() -> dict[str, str]:
    return {k: "a" * 64 for k in _DECLARED_KEYS}


def _snapshot_record(*, measured_window: dict | None = None) -> dict[str, Any]:
    return {
        "manifest": {
            "measured_window": measured_window or {"start": "2020-01-01", "end": "2023-12-31", "calendar": "SSE"},
        },
    }


def _fold_evidence(
    *,
    coverage: float | None = 0.95,
    declared: dict[str, str] | None = None,
    is_oos: bool = False,
) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    if coverage is not None:
        stats["coverage"] = coverage
    return {
        "declared_fingerprints": declared if declared is not None else _full_declared_fingerprints(),
        "stats": stats,
        "is_oos": int(is_oos),
        "fold_index": 0,
    }


def _candidate(*, status: str = "admitted") -> dict[str, Any]:
    return {
        "id": "cand-1",
        "attempt_ordinal": 1,
        "candidate_digest": "d" * 64,
        "canonical_expression": "rank(close)",
        "dsl_version": "factor-dsl-v1",
        "operation": "generate",
        "seed": 42,
        "step": 1,
        "status": status,
        "created_at": "2026-08-09T00:00:00+00:00",
    }


class TestLineageProjection:
    def test_lineage_exposes_bounded_fields_only(self) -> None:
        edge = {
            "lineage_id": "lin-1",
            "edge_ordinal": 0,
            "operation": "mutation",
            "created_at": "2026-08-09T00:00:00+00:00",
            "child": _candidate(status="admitted"),
            "parent": _candidate(status="admitted"),
        }
        projected = projections.lineage(edge)
        assert projected["lineage_id"] == "lin-1"
        assert projected["edge_ordinal"] == 0
        assert projected["operation"] == "mutation"
        assert projected["child"]["canonical_expression"] == "rank(close)"
        assert projected["parent"]["canonical_expression"] == "rank(close)"
        # Deny-by-default: no raw reason/payload internals leak.
        assert "reason" not in projected["child"]
        assert "reason_json" not in projected["child"]


class TestEvidenceClassification:
    def test_clean_when_all_signals_clear(self) -> None:
        result = projections.evidence_classification(
            _snapshot_record(), _candidate(status="admitted"),
            _fold_evidence(coverage=0.95), fixture_flag=False,
        )
        assert result["cache_state"] == "fresh"
        assert result["missing_fields"] == []
        assert result["membership_coverage"] == 0.95
        assert result["evidence_role"] == "selection_fold"
        assert result["fixture"] is False
        assert result["clean"] is True
        assert result["data_date"] == "2020-01-01/2023-12-31"
        assert result["source_label"] == "a" * 64

    def test_stale_cache_when_partial_fingerprints(self) -> None:
        partial = {k: "a" * 64 for k in _DECLARED_KEYS[:3]}  # only 3 of 6
        result = projections.evidence_classification(
            _snapshot_record(), _candidate(),
            _fold_evidence(coverage=0.95, declared=partial), fixture_flag=False,
        )
        assert result["cache_state"] == "stale"
        assert result["clean"] is False

    def test_degraded_cache_when_no_fold_evidence(self) -> None:
        result = projections.evidence_classification(
            _snapshot_record(), _candidate(), None, fixture_flag=False,
        )
        assert result["cache_state"] == "degraded"
        assert result["membership_coverage"] == 0.0
        assert result["clean"] is False

    def test_non_empty_missing_fields_flips_clean(self) -> None:
        declared = {**_full_declared_fingerprints(), "missing_fields": ["close", "volume"]}
        result = projections.evidence_classification(
            _snapshot_record(), _candidate(),
            _fold_evidence(coverage=0.95, declared=declared), fixture_flag=False,
        )
        assert result["missing_fields"] == ["close", "volume"]
        assert result["clean"] is False

    def test_low_coverage_flips_clean(self) -> None:
        result = projections.evidence_classification(
            _snapshot_record(), _candidate(),
            _fold_evidence(coverage=0.4), fixture_flag=False,
        )
        assert result["membership_coverage"] < 0.9
        assert result["clean"] is False

    def test_fixture_flag_flips_clean(self) -> None:
        result = projections.evidence_classification(
            _snapshot_record(), _candidate(),
            _fold_evidence(coverage=0.95), fixture_flag=True,
        )
        assert result["fixture"] is True
        assert result["clean"] is False

    def test_final_blind_unavailable_for_blocked_candidate(self) -> None:
        result = projections.evidence_classification(
            _snapshot_record(), _candidate(status="rejected"),
            _fold_evidence(coverage=0.95), fixture_flag=False,
        )
        assert result["evidence_role"] == "final_blind_unavailable"
        assert result["clean"] is False

    def test_selection_oos_role(self) -> None:
        result = projections.evidence_classification(
            _snapshot_record(), _candidate(status="selection_oos"),
            _fold_evidence(coverage=0.95, is_oos=True), fixture_flag=False,
        )
        assert result["evidence_role"] == "selection_oos"
        # selection_oos with all signals clear is clean.
        assert result["clean"] is True

    def test_exploratory_role_when_no_fold_evidence(self) -> None:
        # No fold evidence + admitted candidate (not blocked) → exploratory.
        result = projections.evidence_classification(
            _snapshot_record(), _candidate(status="admitted"), None, fixture_flag=False,
        )
        assert result["evidence_role"] == "exploratory"

    def test_deterministic_output_for_known_fingerprints(self) -> None:
        snap = _snapshot_record()
        cand = _candidate()
        fe = _fold_evidence(coverage=0.92)
        first = projections.evidence_classification(snap, cand, fe, fixture_flag=False)
        second = projections.evidence_classification(snap, cand, fe, fixture_flag=False)
        assert first == second

    def test_coverage_clamped_to_unit_interval(self) -> None:
        result = projections.evidence_classification(
            _snapshot_record(), _candidate(),
            _fold_evidence(coverage=1.5), fixture_flag=False,
        )
        assert result["membership_coverage"] == 1.0


# ================================================================
# Task 50-01-03: GET /runs/{id}/lineage + evidence-classification endpoints
# ================================================================


@pytest.fixture
def lineage_client(
    tmp_path: Path, deterministic_clock: DeterministicClock,
) -> TestClient:
    """Minimal FastAPI app with the Alpha router + service (principal via header)."""
    repository = ResearchRepository(
        tmp_path / "op.db", clock=deterministic_clock, artifact_root=tmp_path / "art",
    )
    repository.migrate()
    app = FastAPI()

    @app.middleware("http")
    async def inject_test_principal(request, call_next):
        principal = request.headers.get("X-Test-Principal")
        if principal:
            request.state.reviewer_principal = principal
        return await call_next(request)

    app.state.research_run_service = ResearchRunService(repository)
    app.state.research_repository = repository
    app.include_router(research_alpha.router)
    client = TestClient(app)
    client._repo = repository  # type: ignore[attr-defined]
    client._clock = deterministic_clock  # type: ignore[attr-defined]
    return client


def _seed_run_with_candidate_and_evidence(
    client: TestClient, *, run_id: str = "run-api", candidate_id: str = "cand-api"
) -> str:
    repo: ResearchRepository = client._repo  # type: ignore[attr-defined]
    clock: DeterministicClock = client._clock  # type: ignore[attr-defined]
    run = _make_run(repo, clock, run_id=run_id)
    repo.append_candidate_attempt(**_candidate_params(
        run_id=run["id"], candidate_id=candidate_id, ordinal=1,
    ))
    repo.record_alpha_fold_evidence(
        run_id=run["id"], candidate_digest="a" * 60 + "0001",
        fold_index=0, is_oos=False, revision_id="rev-1",
        train_start="2020-01-01", train_end="2020-06-30",
        test_start="2020-07-01", test_end="2020-12-31",
        membership_fingerprint="a" * 64,
        declared_fingerprints={
            "panel": "p" * 64, "membership": "m" * 64,
            "source_field": "s" * 64, "warmup": "w" * 64,
            "missing_data": "d" * 64, "signal": "g" * 64,
        },
        stats={"coverage": 0.95, "mean_ic": 0.03},
    )
    return run["id"]


class TestLineageEndpoint:
    def test_lineage_endpoint_returns_ordered_edges(self, lineage_client: TestClient) -> None:
        repo: ResearchRepository = lineage_client._repo  # type: ignore[attr-defined]
        clock: DeterministicClock = lineage_client._clock  # type: ignore[attr-defined]
        run = _seed_lineage(repo, clock, run_id="run-ep")
        resp = lineage_client.get(
            f"/api/research/alpha/runs/{run['id']}/lineage",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == run["id"]
        assert len(body["edges"]) == 1
        edge = body["edges"][0]
        assert edge["operation"] == "mutation"
        assert edge["child"]["canonical_expression"].startswith("rank(close)")
        assert edge["parent"]["canonical_expression"].startswith("rank(close)")

    def test_lineage_endpoint_unknown_run_404(self, lineage_client: TestClient) -> None:
        resp = lineage_client.get(
            "/api/research/alpha/runs/no-such-run/lineage",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 404

    def test_lineage_endpoint_cross_principal_empty_not_403(
        self, lineage_client: TestClient
    ) -> None:
        repo: ResearchRepository = lineage_client._repo  # type: ignore[attr-defined]
        clock: DeterministicClock = lineage_client._clock  # type: ignore[attr-defined]
        run = _seed_lineage(repo, clock, run_id="run-xp")
        # Cross-principal: same 404 boundary as an unknown run — never a 403 leak
        # (mirrors list_events/list_candidates: service.get returns None for both).
        resp = lineage_client.get(
            f"/api/research/alpha/runs/{run['id']}/lineage",
            headers={"X-Test-Principal": "attacker@example.com"},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] != "forbidden"


class TestEvidenceClassificationEndpoint:
    def test_evidence_classification_returns_clean_flag(
        self, lineage_client: TestClient
    ) -> None:
        run_id = _seed_run_with_candidate_and_evidence(lineage_client)
        resp = lineage_client.get(
            f"/api/research/alpha/runs/{run_id}/candidates/cand-api/evidence-classification",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["cache_state"] == "fresh"
        assert body["membership_coverage"] == 0.95
        assert body["evidence_role"] == "selection_fold"
        assert body["fixture"] is False
        assert body["clean"] is True
        assert body["data_date"] == "2020-01-01/2023-12-31"

    def test_evidence_classification_unknown_run_404(self, lineage_client: TestClient) -> None:
        resp = lineage_client.get(
            "/api/research/alpha/runs/no-such-run/candidates/x/evidence-classification",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 404

    def test_evidence_classification_unknown_candidate_404(
        self, lineage_client: TestClient
    ) -> None:
        run_id = _seed_run_with_candidate_and_evidence(lineage_client)
        resp = lineage_client.get(
            f"/api/research/alpha/runs/{run_id}/candidates/no-such-candidate/evidence-classification",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 404

    def test_evidence_classification_cross_principal_404(
        self, lineage_client: TestClient
    ) -> None:
        run_id = _seed_run_with_candidate_and_evidence(lineage_client)
        resp = lineage_client.get(
            f"/api/research/alpha/runs/{run_id}/candidates/cand-api/evidence-classification",
            headers={"X-Test-Principal": "attacker@example.com"},
        )
        assert resp.status_code == 404
