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
