"""Phase 50-02 — branch replay + clone overridable manifest dimensions.

Covers:
  * ``service.replay_branch`` (50-02-03, SC2 branch replay)
  * ``service.clone_run`` / ``projections.clone_diff`` (50-02-04, SC2 clone)

Branch replay re-derives the PRNG frontier from the frozen seed via
``AlphaFactory(seed).replay_to(parent_step + 1)`` (the proven determinism
contract, alpha_factory.py:349-365), asserts the re-derived prefix equals the
parent's first ``parent_step + 1`` candidates, then continues generation into a
NEW immutable child run through the EXISTING ``create()`` path — no second
generation path (risk #2).  The child shares the parent's frozen manifest
digests; the parent is never mutated.

Clone deep-merges ONLY declared ``scoring``/``costs``/``budgets`` overrides into
the existing immutable ``create()``.  ``seed``/``universe`` are rejected
(``CloneOverrideForbidden`` → 422).  An unchanged manifest hashes identically
and returns the parent id (unchanged-inputs-keep-their-hashes); a changed
digested dimension produces a new run id (risk #5).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import research_alpha
from app.research import projections
from app.research.alpha_factory import AlphaFactory
from app.research.repository import ResearchRepository
from app.research.run_contract import freeze_input_snapshot
from app.research.run_service import CloneOverrideForbidden, ResearchRunService
from tests.research.conftest import DeterministicClock

_PRINCIPAL = "researcher@example.com"


# ---------------------------------------------------------------------
# Manifest / seeding helpers.
# ---------------------------------------------------------------------


def _sample_manifest(*, seed: int = 42, scoring: bool = False) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "dsl": {"version": "factor-dsl-v1"},
        "grammar": {"fingerprint": "a" * 64, "version": "grammar-v1"},
        "vocabulary": {"fingerprint": "b" * 64, "size": 64},
        "policy": {"version": "admission-v1", "thresholds": {"min_ic": 0.02}},
        "budgets": {"max_expressions": 1000, "max_candidates": 64},
        "objective": {"name": "sharpe", "direction": "maximize"},
        "universe": {"name": "cn-a-share", "asset_type": "stock", "membership_fingerprint": "c" * 64},
        "measured_window": {"start": "2020-01-01", "end": "2023-12-31", "calendar": "SSE"},
        "fold_geometry": {"train_size": 120, "gap_size": 5, "test_size": 20, "n_folds": 10},
        "code_manifest": {"fingerprint": "d" * 64, "build_fingerprint": "e" * 64, "dependency_fingerprint": "f" * 64},
        "data_manifest": {"fingerprint": "g" * 64, "partition_fingerprint": "h" * 64},
        "seed": seed,
    }
    if scoring:
        manifest["fold_geometry"].update({"oos_size": 20, "horizon": 5})
        manifest["scoring"] = {"rebalance": "daily", "n_groups": 5, "warmup_days": 10}
        manifest["costs"] = {"commission_pct": 0.0003, "stamp_tax_pct": 0.001, "slippage_bps": 5.0}
    return manifest


def _make_run(
    repo: ResearchRepository,
    clock: DeterministicClock,
    *,
    run_id: str = "run-rep-0",
    idempotency_key: str = "idem-rep-0000000001",
    principal: str = _PRINCIPAL,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = freeze_input_snapshot(
        manifest=manifest or _sample_manifest(), created_at=clock.now_iso(),
    )
    clock.advance()
    return repo.create_alpha_run(
        run_id=run_id, principal=principal, idempotency_key=idempotency_key,
        snapshot=snapshot, event_id="aevt-" + run_id,
    )


def _persist_factory_candidates(
    repo: ResearchRepository, *, run_id: str, count: int, seed: int = 42,
    tamper_step: int | None = None,
) -> list[dict[str, Any]]:
    """Generate ``count`` candidates from a deterministic factory and persist them."""
    factory = AlphaFactory(seed, max_candidates=64)
    persisted: list[dict[str, Any]] = []
    for ordinal in range(1, count + 1):
        result = factory.generate_next()
        assert result is not None
        digest = result.digest
        if tamper_step is not None and result.step == tamper_step:
            digest = "0" * 63 + "1"  # a valid-shape but wrong digest
        repo.append_candidate_attempt(
            run_id=run_id,
            candidate_id=f"cand-{result.step}",
            attempt_ordinal=ordinal,
            candidate_digest=digest,
            canonical_expression=result.canonical_expression,
            ast_signature=f"ast-{result.step}",
            shape_signature=f"shape-{result.step}",
            dsl_version="factor-dsl-v1",
            operation=result.operation,
            seed=seed,
            step=result.step,
            status="generated",
            reason={"note": f"factory candidate {result.step}"},
        )
        persisted.append({"step": result.step, "digest": result.digest, "result": result})
    return persisted


# ================================================================
# Task 50-02-03: service.replay_branch — seed re-derivation into a child run
# ================================================================


class TestReplayBranchService:
    def test_replay_branch_creates_child_with_shared_digests(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-rb-1")
        persisted = _persist_factory_candidates(
            alpha_run_repository, run_id=run["id"], count=4, seed=42,
        )
        service = ResearchRunService(alpha_run_repository)
        result = service.replay_branch(
            run["id"], principal=_PRINCIPAL, parent_step=2,
            idempotency_key="idem-replay-branch-0001",
        )
        assert result is not None
        # NEW child run id, distinct from the parent.
        assert result["child_run_id"] != run["id"]
        assert result["parent_run_id"] == run["id"]
        assert result["parent_step"] == 2
        # The child shares the parent's frozen snapshot/manifest digests.
        assert result["shared_snapshot_sha256"] == run["snapshot_sha256"]
        assert result["shared_manifest_sha256"] == run["manifest_sha256"]
        # The re-derived prefix equals the parent's first parent_step+1 candidates.
        assert result["replayed_prefix_digests"] == [p["digest"] for p in persisted[:3]]

    def test_replay_branch_determinism_assertion_raises_on_mismatch(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-rb-mm")
        # Persist candidates but tamper one digest → the re-derived prefix cannot match.
        _persist_factory_candidates(
            alpha_run_repository, run_id=run["id"], count=3, seed=42, tamper_step=1,
        )
        service = ResearchRunService(alpha_run_repository)
        with pytest.raises(ValueError, match="determinism"):
            service.replay_branch(
                run["id"], principal=_PRINCIPAL, parent_step=2,
                idempotency_key="idem-replay-branch-mm01",
            )

    def test_replay_branch_idempotent_same_key_same_child(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-rb-idem")
        _persist_factory_candidates(alpha_run_repository, run_id=run["id"], count=3, seed=42)
        service = ResearchRunService(alpha_run_repository)
        key = "idem-replay-branch-idem01"
        first = service.replay_branch(
            run["id"], principal=_PRINCIPAL, parent_step=1, idempotency_key=key,
        )
        second = service.replay_branch(
            run["id"], principal=_PRINCIPAL, parent_step=1, idempotency_key=key,
        )
        assert first is not None and second is not None
        # Exactly-once: the same idempotency key returns the same child run.
        assert first["child_run_id"] == second["child_run_id"]

    def test_replay_branch_parent_step_out_of_range(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-rb-oor")
        _persist_factory_candidates(alpha_run_repository, run_id=run["id"], count=2, seed=42)
        service = ResearchRunService(alpha_run_repository)
        with pytest.raises(ValueError, match="out of range"):
            service.replay_branch(
                run["id"], principal=_PRINCIPAL, parent_step=5,
                idempotency_key="idem-replay-branch-oor01",
            )

    def test_replay_branch_cross_principal_returns_none(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-rb-xp")
        _persist_factory_candidates(alpha_run_repository, run_id=run["id"], count=2, seed=42)
        service = ResearchRunService(alpha_run_repository)
        assert service.replay_branch(
            run["id"], principal="attacker@example.com", parent_step=0,
            idempotency_key="idem-replay-branch-xp001",
        ) is None

    def test_replay_branch_parent_never_mutated(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-rb-pm")
        _persist_factory_candidates(alpha_run_repository, run_id=run["id"], count=3, seed=42)
        service = ResearchRunService(alpha_run_repository)
        before = alpha_run_repository.get_alpha_run(run["id"], principal=_PRINCIPAL)
        before_candidates = alpha_run_repository.list_candidates(
            run["id"], principal=_PRINCIPAL, artifact_service=None,
        )
        service.replay_branch(
            run["id"], principal=_PRINCIPAL, parent_step=1,
            idempotency_key="idem-replay-branch-pm001",
        )
        after = alpha_run_repository.get_alpha_run(run["id"], principal=_PRINCIPAL)
        after_candidates = alpha_run_repository.list_candidates(
            run["id"], principal=_PRINCIPAL, artifact_service=None,
        )
        # The parent run row + candidate ledger are byte-identical before/after.
        assert before == after
        assert before_candidates == after_candidates

    def test_replay_branch_uses_existing_create_path(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
        monkeypatch,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-rb-wp")
        _persist_factory_candidates(alpha_run_repository, run_id=run["id"], count=2, seed=42)
        service = ResearchRunService(alpha_run_repository)
        # The child run MUST be created through the existing create() path —
        # no second generation path.  Track that create() was the entry point.
        created_ids: list[str] = []
        original_create = service.create

        def _spy_create(*args, **kwargs):
            child = original_create(*args, **kwargs)
            created_ids.append(child["id"])
            return child

        monkeypatch.setattr(service, "create", _spy_create)
        result = service.replay_branch(
            run["id"], principal=_PRINCIPAL, parent_step=0,
            idempotency_key="idem-replay-branch-wp001",
        )
        assert result is not None
        assert created_ids == [result["child_run_id"]]


# ---------------------------------------------------------------------
# API surface for replay-branch.
# ---------------------------------------------------------------------


@pytest.fixture
def replay_client(
    tmp_path: Path, deterministic_clock: DeterministicClock,
) -> TestClient:
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


class TestReplayBranchEndpoint:
    def test_replay_branch_creates_child(self, replay_client: TestClient) -> None:
        repo: ResearchRepository = replay_client._repo  # type: ignore[attr-defined]
        clock: DeterministicClock = replay_client._clock  # type: ignore[attr-defined]
        run = _make_run(repo, clock, run_id="run-rb-api")
        _persist_factory_candidates(repo, run_id=run["id"], count=3, seed=42)
        resp = replay_client.post(
            f"/api/research/alpha/runs/{run['id']}/replay-branch",
            json={"idempotency_key": "idem-replay-branch-api001", "parent_step": 1},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["parent_run_id"] == run["id"]
        assert body["child_run_id"] != run["id"]
        assert body["shared_manifest_sha256"] == run["manifest_sha256"]
        assert len(body["replayed_prefix_digests"]) == 2

    def test_replay_branch_unknown_run_404(self, replay_client: TestClient) -> None:
        resp = replay_client.post(
            "/api/research/alpha/runs/no-such-run/replay-branch",
            json={"idempotency_key": "idem-replay-branch-unk001", "parent_step": 0},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 404

    def test_replay_branch_out_of_range_422(self, replay_client: TestClient) -> None:
        repo: ResearchRepository = replay_client._repo  # type: ignore[attr-defined]
        clock: DeterministicClock = replay_client._clock  # type: ignore[attr-defined]
        run = _make_run(repo, clock, run_id="run-rb-api-oor")
        _persist_factory_candidates(repo, run_id=run["id"], count=1, seed=42)
        resp = replay_client.post(
            f"/api/research/alpha/runs/{run['id']}/replay-branch",
            json={"idempotency_key": "idem-replay-branch-api002", "parent_step": 9},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 422


# ================================================================
# Task 50-02-04: service.clone_run + projections.clone_diff (SC2 clone)
# ================================================================


class TestCloneRunService:
    def test_clone_overriding_cost_produces_new_run_with_diff(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(
            alpha_run_repository, deterministic_clock, run_id="run-cl-1",
            manifest=_sample_manifest(seed=7, scoring=True),
        )
        service = ResearchRunService(alpha_run_repository)
        result = service.clone_run(
            run["id"], principal=_PRINCIPAL,
            overrides={"costs": {"commission_pct": 0.0005}},
            idempotency_key="idem-clone-cost-000001",
        )
        assert result is not None
        # A changed digested dimension produces a NEW run id + a field-level diff.
        assert result["clone_run_id"] != run["id"]
        assert result["changed_dimensions"] == ["costs.commission_pct"]
        assert result["no_op"] is False
        # The override perturbs the canonical digest (risk #5).
        assert result["clone_manifest_sha256"] != result["parent_manifest_sha256"]
        assert result["parent_manifest_sha256"] == run["manifest_sha256"]

    def test_clone_overriding_scoring_produces_new_run(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(
            alpha_run_repository, deterministic_clock, run_id="run-cl-sc",
            manifest=_sample_manifest(seed=7, scoring=True),
        )
        service = ResearchRunService(alpha_run_repository)
        result = service.clone_run(
            run["id"], principal=_PRINCIPAL,
            overrides={"scoring": {"n_groups": 10}},
            idempotency_key="idem-clone-scoring-001",
        )
        assert result is not None
        assert result["clone_run_id"] != run["id"]
        assert result["changed_dimensions"] == ["scoring.n_groups"]
        assert result["clone_manifest_sha256"] != result["parent_manifest_sha256"]

    def test_no_op_clone_returns_parent_id(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(
            alpha_run_repository, deterministic_clock, run_id="run-cl-noop",
            manifest=_sample_manifest(seed=7, scoring=True),
        )
        service = ResearchRunService(alpha_run_repository)
        # Empty overrides → unchanged-inputs-keep-their-hashes → parent id.
        result = service.clone_run(
            run["id"], principal=_PRINCIPAL, overrides={},
            idempotency_key="idem-clone-noop-00001",
        )
        assert result is not None
        assert result["clone_run_id"] == run["id"]
        assert result["changed_dimensions"] == []
        assert result["no_op"] is True
        assert result["clone_manifest_sha256"] == result["parent_manifest_sha256"]

    def test_no_op_clone_with_same_value_returns_parent_id(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(
            alpha_run_repository, deterministic_clock, run_id="run-cl-sv",
            manifest=_sample_manifest(seed=7, scoring=True),
        )
        service = ResearchRunService(alpha_run_repository)
        # Override to the SAME value → no actual change → parent id.
        result = service.clone_run(
            run["id"], principal=_PRINCIPAL,
            overrides={"costs": {"commission_pct": 0.0003}},
            idempotency_key="idem-clone-sameval-001",
        )
        assert result is not None
        assert result["clone_run_id"] == run["id"]
        assert result["changed_dimensions"] == []
        assert result["no_op"] is True

    def test_seed_override_forbidden(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(
            alpha_run_repository, deterministic_clock, run_id="run-cl-seed",
            manifest=_sample_manifest(seed=7, scoring=True),
        )
        service = ResearchRunService(alpha_run_repository)
        with pytest.raises(CloneOverrideForbidden):
            service.clone_run(
                run["id"], principal=_PRINCIPAL,
                overrides={"seed": 999},
                idempotency_key="idem-clone-seed-0001",
            )

    def test_universe_override_forbidden(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(
            alpha_run_repository, deterministic_clock, run_id="run-cl-uni",
            manifest=_sample_manifest(seed=7, scoring=True),
        )
        service = ResearchRunService(alpha_run_repository)
        with pytest.raises(CloneOverrideForbidden):
            service.clone_run(
                run["id"], principal=_PRINCIPAL,
                overrides={"universe": {"name": "other"}},
                idempotency_key="idem-clone-uni-000001",
            )

    def test_clone_parent_never_mutated(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(
            alpha_run_repository, deterministic_clock, run_id="run-cl-pm",
            manifest=_sample_manifest(seed=7, scoring=True),
        )
        before_snapshot = alpha_run_repository.get_run_snapshot(run["id"])
        service = ResearchRunService(alpha_run_repository)
        service.clone_run(
            run["id"], principal=_PRINCIPAL,
            overrides={"budgets": {"max_candidates": 100}},
            idempotency_key="idem-clone-pm-000001",
        )
        after_snapshot = alpha_run_repository.get_run_snapshot(run["id"])
        # The parent's frozen snapshot/manifest is byte-identical before/after.
        assert before_snapshot == after_snapshot

    def test_clone_idempotent_same_key_same_clone(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(
            alpha_run_repository, deterministic_clock, run_id="run-cl-idem",
            manifest=_sample_manifest(seed=7, scoring=True),
        )
        service = ResearchRunService(alpha_run_repository)
        key = "idem-clone-idemp-00001"
        first = service.clone_run(
            run["id"], principal=_PRINCIPAL,
            overrides={"costs": {"slippage_bps": 10.0}},
            idempotency_key=key,
        )
        second = service.clone_run(
            run["id"], principal=_PRINCIPAL,
            overrides={"costs": {"slippage_bps": 10.0}},
            idempotency_key=key,
        )
        assert first is not None and second is not None
        assert first["clone_run_id"] == second["clone_run_id"]

    def test_clone_cross_principal_returns_none(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(
            alpha_run_repository, deterministic_clock, run_id="run-cl-xp",
            manifest=_sample_manifest(seed=7, scoring=True),
        )
        service = ResearchRunService(alpha_run_repository)
        assert service.clone_run(
            run["id"], principal="attacker@example.com",
            overrides={"costs": {"commission_pct": 0.0005}},
            idempotency_key="idem-clone-xp-000001",
        ) is None


class TestCloneDiffProjection:
    def test_clone_diff_exposes_bounded_fields(self) -> None:
        record = {
            "parent_run_id": "arun-parent", "clone_run_id": "arun-clone",
            "parent_manifest_sha256": "a" * 64, "clone_manifest_sha256": "b" * 64,
            "changed_dimensions": ["costs.commission_pct"], "no_op": False,
            "secret_internal": "should-not-leak",
        }
        projected = projections.clone_diff(record)
        assert projected["parent_run_id"] == "arun-parent"
        assert projected["clone_run_id"] == "arun-clone"
        assert projected["changed_dimensions"] == ["costs.commission_pct"]
        assert projected["no_op"] is False
        assert "secret_internal" not in projected


class TestCloneEndpoint:
    def test_clone_returns_new_run_with_diff(self, replay_client: TestClient) -> None:
        repo: ResearchRepository = replay_client._repo  # type: ignore[attr-defined]
        clock: DeterministicClock = replay_client._clock  # type: ignore[attr-defined]
        run = _make_run(
            repo, clock, run_id="run-cl-api", manifest=_sample_manifest(seed=7, scoring=True),
        )
        resp = replay_client.post(
            f"/api/research/alpha/runs/{run['id']}/clone",
            json={"idempotency_key": "idem-clone-api-000001",
                  "overrides": {"costs": {"commission_pct": 0.0005}}},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["clone_run_id"] != run["id"]
        assert body["changed_dimensions"] == ["costs.commission_pct"]
        assert body["no_op"] is False

    def test_clone_no_op_returns_parent_id(self, replay_client: TestClient) -> None:
        repo: ResearchRepository = replay_client._repo  # type: ignore[attr-defined]
        clock: DeterministicClock = replay_client._clock  # type: ignore[attr-defined]
        run = _make_run(
            repo, clock, run_id="run-cl-api-noop", manifest=_sample_manifest(seed=7, scoring=True),
        )
        resp = replay_client.post(
            f"/api/research/alpha/runs/{run['id']}/clone",
            json={"idempotency_key": "idem-clone-api-noop1", "overrides": {}},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["clone_run_id"] == run["id"]
        assert body["no_op"] is True

    def test_clone_seed_override_422(self, replay_client: TestClient) -> None:
        repo: ResearchRepository = replay_client._repo  # type: ignore[attr-defined]
        clock: DeterministicClock = replay_client._clock  # type: ignore[attr-defined]
        run = _make_run(
            repo, clock, run_id="run-cl-api-seed", manifest=_sample_manifest(seed=7, scoring=True),
        )
        resp = replay_client.post(
            f"/api/research/alpha/runs/{run['id']}/clone",
            json={"idempotency_key": "idem-clone-api-seed1",
                  "overrides": {"seed": 999}},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 422
        assert resp.json()["detail"]["code"] == "CloneOverrideForbidden"

    def test_clone_unknown_run_404(self, replay_client: TestClient) -> None:
        resp = replay_client.post(
            "/api/research/alpha/runs/no-such-run/clone",
            json={"idempotency_key": "idem-clone-api-unk001", "overrides": {}},
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 404
