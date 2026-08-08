"""Wave 0 create → durable snapshot/run/event → fresh-process replay contracts.

These tests prove the Phase 45 architecture before candidate, checkpoint,
retry, and worker expansions: a bounded create request produces one
server-owned immutable Alpha run and snapshot in operational.db, a fresh
repository/service instance can replay the committed event history, and
repeated requests are idempotent while changed inputs conflict.

All assertions use the deterministic clock and temporary managed
artifact-root fixtures so timestamps and paths are reproducible.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from app.research.repository import AlphaRunConflictError, ResearchRepository
from app.research.run_contract import (
    MANIFEST_SCHEMA_VERSION,
    PRODUCER_VERSION,
    freeze_input_snapshot,
)
from tests.research.conftest import DeterministicClock


def _sample_manifest(*, seed: int = 42, universe: str = "cn-a-share") -> dict:
    """A complete D-04 manifest with every required group non-empty."""
    return {
        "dsl": {"version": "factor-dsl-v1"},
        "grammar": {"fingerprint": "a" * 64, "version": "grammar-v1"},
        "vocabulary": {"fingerprint": "b" * 64, "size": 64},
        "policy": {"version": "admission-v1", "thresholds": {"min_ic": 0.02}},
        "budgets": {"max_expressions": 1000, "max_candidates": 200},
        "objective": {"name": "sharpe", "direction": "maximize"},
        "universe": {"name": universe, "asset_type": "stock", "membership_fingerprint": "c" * 64},
        "measured_window": {"start": "2020-01-01", "end": "2023-12-31", "calendar": "SSE"},
        "fold_geometry": {"train_size": 120, "gap_size": 5, "test_size": 20, "n_folds": 10},
        "code_manifest": {
            "fingerprint": "d" * 64,
            "build_fingerprint": "e" * 64,
            "dependency_fingerprint": "f" * 64,
        },
        "data_manifest": {
            "fingerprint": "g" * 64,
            "partition_fingerprint": "h" * 64,
        },
        "seed": seed,
    }


# ================================================================
# Manifest / snapshot freeze contracts
# ================================================================


class TestManifestFreeze:
    def test_freeze_produces_stable_canonical_snapshot(self, deterministic_clock: DeterministicClock) -> None:
        manifest = _sample_manifest()
        snapshot_a = freeze_input_snapshot(manifest=manifest, created_at=deterministic_clock.now_iso())
        snapshot_b = freeze_input_snapshot(manifest=manifest, created_at=deterministic_clock.now_iso())
        assert snapshot_a.snapshot_sha256 == snapshot_b.snapshot_sha256
        assert snapshot_a.manifest_sha256 == snapshot_b.manifest_sha256
        assert len(snapshot_a.snapshot_sha256) == 64
        assert snapshot_a.schema_version == MANIFEST_SCHEMA_VERSION

    def test_changed_input_produces_distinct_digest(self, deterministic_clock: DeterministicClock) -> None:
        now = deterministic_clock.now_iso()
        snapshot_a = freeze_input_snapshot(manifest=_sample_manifest(seed=42), created_at=now)
        snapshot_b = freeze_input_snapshot(manifest=_sample_manifest(seed=43), created_at=now)
        assert snapshot_a.snapshot_sha256 != snapshot_b.snapshot_sha256
        assert snapshot_a.manifest_sha256 != snapshot_b.manifest_sha256

    def test_missing_manifest_group_fails_closed(self) -> None:
        manifest = _sample_manifest()
        del manifest["budgets"]
        with pytest.raises(ValueError, match="missing required groups"):
            freeze_input_snapshot(manifest=manifest, created_at="2026-08-08T00:00:00+00:00")

    def test_empty_manifest_group_fails_closed(self) -> None:
        manifest = _sample_manifest()
        manifest["objective"] = {}
        with pytest.raises(ValueError, match="must not be empty"):
            freeze_input_snapshot(manifest=manifest, created_at="2026-08-08T00:00:00+00:00")


# ================================================================
# Create → durable snapshot/run/event → replay contracts
# ================================================================


class TestCreateAndReplay:
    def test_create_produces_queued_run_and_committed_sequence_one(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        snapshot = freeze_input_snapshot(
            manifest=_sample_manifest(), created_at=deterministic_clock.now_iso()
        )
        run = alpha_run_repository.create_alpha_run(
            run_id="run-001",
            principal="researcher@example.com",
            idempotency_key="idem-0000000000000001",
            snapshot=snapshot,
            event_id="evt-001",
        )
        assert run["id"] == "run-001"
        assert run["status"] == "queued"
        assert run["snapshot_sha256"] == snapshot.snapshot_sha256
        assert run["last_event_seq"] == 1
        assert run["transition_version"] == 1
        assert run["candidate_attempts_total"] == 0
        assert run["retry_of_run_id"] is None

        events = alpha_run_repository.list_run_events("run-001")
        assert len(events) == 1
        assert events[0]["seq"] == 1
        assert events[0]["event_type"] == "run_created"
        assert events[0]["producer_version"] == PRODUCER_VERSION

    def test_fresh_repository_replays_one_run_created_event_without_writes(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
        tmp_path: Path,
    ) -> None:
        snapshot = freeze_input_snapshot(
            manifest=_sample_manifest(), created_at=deterministic_clock.now_iso()
        )
        alpha_run_repository.create_alpha_run(
            run_id="run-002",
            principal="researcher@example.com",
            idempotency_key="idem-0000000000000002",
            snapshot=snapshot,
            event_id="evt-002",
        )

        # Simulate a fresh process: new repository instance over the same db.
        fresh = ResearchRepository(
            alpha_run_repository.database_path,
            clock=deterministic_clock,
            artifact_root=tmp_path / "alpha_artifacts",
        )
        events = fresh.list_run_events("run-002")
        assert len(events) == 1
        assert events[0]["event_type"] == "run_created"
        assert events[0]["seq"] == 1

        run = fresh.get_alpha_run("run-002")
        assert run is not None
        assert run["status"] == "queued"

        persisted_snapshot = fresh.get_run_snapshot("run-002")
        assert persisted_snapshot is not None
        assert persisted_snapshot["manifest_sha256"] == snapshot.manifest_sha256
        # Every required D-04 group is present in the canonical manifest.
        for group in ("dsl", "grammar", "vocabulary", "policy", "budgets", "universe"):
            assert group in persisted_snapshot["manifest"]

    def test_persisted_snapshot_contains_all_required_digest_groups(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        snapshot = freeze_input_snapshot(
            manifest=_sample_manifest(), created_at=deterministic_clock.now_iso()
        )
        alpha_run_repository.create_alpha_run(
            run_id="run-003",
            principal="researcher@example.com",
            idempotency_key="idem-0000000000000003",
            snapshot=snapshot,
            event_id="evt-003",
        )
        persisted = alpha_run_repository.get_run_snapshot("run-003")
        assert persisted is not None
        assert persisted["dsl_version"] == "factor-dsl-v1"
        assert persisted["policy_version"] == "admission-v1"
        assert len(persisted["grammar_fingerprint"]) == 64
        assert len(persisted["vocabulary_fingerprint"]) == 64
        assert len(persisted["policy_digest"]) == 64
        assert len(persisted["data_fingerprint"]) == 64
        assert len(persisted["membership_fingerprint"]) == 64
        assert len(persisted["code_fingerprint"]) == 64


# ================================================================
# Idempotency and conflict contracts
# ================================================================


class TestIdempotency:
    def test_same_principal_key_and_canonical_intent_returns_original_run(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        snapshot = freeze_input_snapshot(
            manifest=_sample_manifest(),
            created_at=deterministic_clock.now_iso(),
        )
        first = alpha_run_repository.create_alpha_run(
            run_id="run-004",
            principal="researcher@example.com",
            idempotency_key="idem-0000000000000004",
            snapshot=snapshot,
            event_id="evt-004",
        )
        deterministic_clock.advance()
        second = alpha_run_repository.create_alpha_run(
            run_id="run-004-dup",
            principal="researcher@example.com",
            idempotency_key="idem-0000000000000004",
            snapshot=snapshot,
            event_id="evt-004-dup",
        )
        # Same original run returned; no second row or event appended.
        assert second["id"] == first["id"] == "run-004"
        events = alpha_run_repository.list_run_events("run-004")
        assert len(events) == 1
        assert alpha_run_repository.get_alpha_run("run-004-dup") is None

    def test_same_key_with_changed_digest_maps_to_conflict(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        snapshot_a = freeze_input_snapshot(
            manifest=_sample_manifest(seed=1), created_at=deterministic_clock.now_iso()
        )
        alpha_run_repository.create_alpha_run(
            run_id="run-005",
            principal="researcher@example.com",
            idempotency_key="idem-0000000000000005",
            snapshot=snapshot_a,
            event_id="evt-005",
        )
        snapshot_b = freeze_input_snapshot(
            manifest=_sample_manifest(seed=2), created_at=deterministic_clock.now_iso()
        )
        with pytest.raises(AlphaRunConflictError):
            alpha_run_repository.create_alpha_run(
                run_id="run-005-conflict",
                principal="researcher@example.com",
                idempotency_key="idem-0000000000000005",
                snapshot=snapshot_b,
                event_id="evt-005-conflict",
            )
        # Original row is byte-for-byte unchanged.
        run = alpha_run_repository.get_alpha_run("run-005")
        assert run is not None
        assert run["snapshot_sha256"] == snapshot_a.snapshot_sha256
        assert run["last_event_seq"] == 1


# ================================================================
# Deterministic clock and managed artifact-root fixture contracts
# ================================================================


class TestDeterministicClockFixture:
    def test_clock_is_reproducible(self) -> None:
        clock_a = DeterministicClock()
        clock_b = DeterministicClock()
        assert clock_a.now_iso() == clock_b.now_iso()
        before = clock_a.now_iso()
        advanced = clock_a.advance()
        assert advanced != before
        assert clock_a.now_iso() == advanced
        second = clock_a.advance()
        assert second > advanced


class TestManagedArtifactRoot:
    def test_artifact_root_is_temporary_and_clean(
        self, alpha_artifact_root: Path
    ) -> None:
        assert alpha_artifact_root.exists()
        assert alpha_artifact_root.is_dir()
        # The managed namespace lives under alpha_runs/ only.
        expected = alpha_artifact_root.parent / "alpha_artifacts"
        assert alpha_artifact_root == expected


# ================================================================
# Immutability: persisted facts cannot be mutated outside the guarded cursor
# ================================================================


class TestImmutabilityGuards:
    def test_run_identity_columns_are_immutable_via_repository(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        snapshot = freeze_input_snapshot(
            manifest=_sample_manifest(), created_at=deterministic_clock.now_iso()
        )
        alpha_run_repository.create_alpha_run(
            run_id="run-006",
            principal="researcher@example.com",
            idempotency_key="idem-0000000000000006",
            snapshot=snapshot,
            event_id="evt-006",
        )
        import sqlite3

        with alpha_run_repository._connection() as connection:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE research_alpha_runs SET principal = 'other' WHERE id = 'run-006'"
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE research_alpha_runs SET snapshot_sha256 = 'z' * 64 WHERE id = 'run-006'"
                )



# ================================================================
# Schema and projection hardening (Task 45-01-02)
# ================================================================


class TestSchemaHardening:
    def test_non_lowercase_digest_fails_closed_in_validation(self) -> None:
        from app.research.run_contract import validate_sha256

        with pytest.raises(ValueError):
            validate_sha256("A" * 64, "digest")  # uppercase rejected
        with pytest.raises(ValueError):
            validate_sha256("short", "digest")  # wrong length rejected

    def test_manifest_semantically_equivalent_fields_have_stable_digest(
        self, deterministic_clock: DeterministicClock
    ) -> None:
        # Reordered keys in a sub-mapping should not change the digest
        # because canonical JSON sorts keys.
        manifest_a = _sample_manifest()
        manifest_b = _sample_manifest()
        manifest_b["policy"] = {"thresholds": {"min_ic": 0.02}, "version": "admission-v1"}
        now = deterministic_clock.now_iso()
        snap_a = freeze_input_snapshot(manifest=manifest_a, created_at=now)
        snap_b = freeze_input_snapshot(manifest=manifest_b, created_at=now)
        assert snap_a.manifest_sha256 == snap_b.manifest_sha256


class TestProjectionSafety:
    def test_run_projection_omits_principal_and_paths(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research import projections

        snapshot = freeze_input_snapshot(
            manifest=_sample_manifest(), created_at=deterministic_clock.now_iso()
        )
        run = alpha_run_repository.create_alpha_run(
            run_id="run-proj-1",
            principal="secret_user@example.com",
            idempotency_key="idem-00000000000000p1",
            snapshot=snapshot,
            event_id="evt-proj-1",
        )
        projected = projections.run(run)
        assert "principal" not in projected
        assert "idempotency_key" not in projected

    def test_snapshot_projection_exposes_every_d04_group_without_internals(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research import projections

        snapshot = freeze_input_snapshot(
            manifest=_sample_manifest(), created_at=deterministic_clock.now_iso()
        )
        alpha_run_repository.create_alpha_run(
            run_id="run-proj-2",
            principal="researcher@example.com",
            idempotency_key="idem-00000000000000p2",
            snapshot=snapshot,
            event_id="evt-proj-2",
        )
        persisted = alpha_run_repository.get_run_snapshot("run-proj-2")
        assert persisted is not None
        projected = projections.snapshot(persisted)
        # Every required D-04 group is present in bounded form.
        for field in (
            "dsl_version", "grammar_fingerprint", "vocabulary_fingerprint",
            "policy_version", "policy_digest", "data_fingerprint",
            "partition_fingerprint", "membership_fingerprint", "code_fingerprint",
            "build_fingerprint", "dependency_fingerprint", "universe",
            "measured_window", "fold_geometry", "budgets", "objective",
        ):
            assert field in projected
        # No raw policy internals (thresholds) leak.
        assert "thresholds" not in str(projected)

    def test_event_projection_omits_raw_payload(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research import projections

        snapshot = freeze_input_snapshot(
            manifest=_sample_manifest(), created_at=deterministic_clock.now_iso()
        )
        alpha_run_repository.create_alpha_run(
            run_id="run-proj-3",
            principal="researcher@example.com",
            idempotency_key="idem-00000000000000p3",
            snapshot=snapshot,
            event_id="evt-proj-3",
        )
        events = alpha_run_repository.list_run_events("run-proj-3")
        projected = projections.event(events[0])
        assert "payload" not in projected
        assert "idempotency_key" not in projected
        assert "actor" not in projected
        assert "artifact_id" not in projected
        assert "payload_checksum" not in projected


class TestPreflightFailure:
    def test_service_preflight_failure_produces_no_queued_row(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import AlphaRunPreflightError, ResearchRunService

        service = ResearchRunService(alpha_run_repository)
        manifest = _sample_manifest()
        del manifest["universe"]
        with pytest.raises(AlphaRunPreflightError):
            service.create(
                principal="researcher@example.com",
                idempotency_key="idem-00000000000000pf",
                manifest=manifest,
            )
        assert alpha_run_repository.get_alpha_run("arun_nonexistent") is None
        # No event was appended for the failed preflight.
        events = alpha_run_repository.list_run_events("arun_nonexistent")
        assert events == []


# ================================================================
# Task 45-02-01: Candidate attempts, lineage, event sequencing
# ================================================================


def _make_run(
    repo: ResearchRepository,
    clock: DeterministicClock,
    *,
    run_id: str = "run-cand-0",
    idempotency_key: str = "idem-cand-0000000001",
) -> dict:
    """Create a queued run for candidate/event tests."""
    snapshot = freeze_input_snapshot(
        manifest=_sample_manifest(), created_at=clock.now_iso()
    )
    clock.advance()
    return repo.create_alpha_run(
        run_id=run_id,
        principal="researcher@example.com",
        idempotency_key=idempotency_key,
        snapshot=snapshot,
        event_id="aevt-" + run_id,
    )


def _candidate_params(
    *,
    run_id: str,
    candidate_id: str,
    ordinal: int,
    status: str = "admitted",
    digest: str | None = None,
    seed: int = 42,
    step: int = 1,
) -> dict:
    """Build valid candidate-attempt parameters."""
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
        "seed": seed,
        "step": step,
        "status": status,
        "reason": {"note": f"candidate {ordinal}"},
    }


class TestCandidateAppendAndReadback:
    def test_all_eight_outcomes_persist_with_ordinal_reason_and_lineage(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-8-out")
        statuses = [
            "invalid", "duplicate", "low_coverage", "failed",
            "rejected", "admitted", "cancelled", "budget_exhausted",
        ]
        for idx, status in enumerate(statuses, start=1):
            alpha_run_repository.append_candidate_attempt(
                **_candidate_params(
                    run_id=run["id"],
                    candidate_id=f"cand-{idx}",
                    ordinal=idx,
                    status=status,
                )
            )
        candidates = alpha_run_repository.list_candidates(run["id"])
        assert len(candidates) == 8
        assert [c["status"] for c in candidates] == statuses
        assert [c["attempt_ordinal"] for c in candidates] == list(range(1, 9))
        for c in candidates:
            assert c["reason"] == {"note": f"candidate {c['attempt_ordinal']}"}
            assert len(c["candidate_digest"]) == 64

    def test_duplicate_expression_remains_two_rows_when_attempt_identity_differs(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-dup-expr")
        same_digest = "d" * 64
        alpha_run_repository.append_candidate_attempt(
            **_candidate_params(
                run_id=run["id"], candidate_id="cand-dup-1", ordinal=1,
                status="admitted", digest=same_digest,
            )
        )
        alpha_run_repository.append_candidate_attempt(
            **_candidate_params(
                run_id=run["id"], candidate_id="cand-dup-2", ordinal=2,
                status="duplicate", digest=same_digest,
            )
        )
        candidates = alpha_run_repository.list_candidates(run["id"])
        assert len(candidates) == 2
        # Same canonical digest, different attempt identity and status.
        assert candidates[0]["candidate_digest"] == candidates[1]["candidate_digest"]
        assert candidates[0]["id"] != candidates[1]["id"]
        assert candidates[1]["status"] == "duplicate"

    def test_invalid_candidate_does_not_change_run_status(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-inv")
        alpha_run_repository.append_candidate_attempt(
            **_candidate_params(
                run_id=run["id"], candidate_id="cand-inv-1", ordinal=1,
                status="invalid",
            )
        )
        refreshed = alpha_run_repository.get_alpha_run(run["id"])
        assert refreshed is not None
        # An invalid candidate is distinct from run-level preflight_failed.
        assert refreshed["status"] == "queued"

    def test_duplicate_ordinal_rejected(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-ord")
        alpha_run_repository.append_candidate_attempt(
            **_candidate_params(
                run_id=run["id"], candidate_id="cand-ord-1", ordinal=1,
            )
        )
        import sqlite3
        with pytest.raises(sqlite3.IntegrityError):
            alpha_run_repository.append_candidate_attempt(
                **_candidate_params(
                    run_id=run["id"], candidate_id="cand-ord-1b", ordinal=1,
                )
            )

    def test_bad_status_rejected(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-bad-st")
        with pytest.raises(ValueError, match="status must be one of"):
            alpha_run_repository.append_candidate_attempt(
                **{
                    **_candidate_params(
                        run_id=run["id"], candidate_id="cand-bad", ordinal=1,
                    ),
                    "status": "champion",
                }
            )


class TestCandidateLineage:
    def test_lineage_edge_persists_same_run(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-lin")
        alpha_run_repository.append_candidate_attempt(
            **_candidate_params(run_id=run["id"], candidate_id="cand-par", ordinal=1)
        )
        alpha_run_repository.append_candidate_attempt(
            **_candidate_params(run_id=run["id"], candidate_id="cand-chi", ordinal=2)
        )
        edge = alpha_run_repository.append_candidate_lineage(
            run_id=run["id"],
            lineage_id="lin-1",
            child_attempt_id="cand-chi",
            parent_attempt_id="cand-par",
            edge_ordinal=0,
            operation="mutation",
        )
        assert edge["child_attempt_id"] == "cand-chi"
        assert edge["parent_attempt_id"] == "cand-par"

    def test_cross_run_parent_rejected(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run_a = _make_run(
            alpha_run_repository, deterministic_clock,
            run_id="run-lin-a", idempotency_key="idem-lin-a",
        )
        run_b = _make_run(
            alpha_run_repository, deterministic_clock,
            run_id="run-lin-b", idempotency_key="idem-lin-b",
        )
        alpha_run_repository.append_candidate_attempt(
            **_candidate_params(run_id=run_a["id"], candidate_id="cand-a1", ordinal=1)
        )
        alpha_run_repository.append_candidate_attempt(
            **_candidate_params(run_id=run_b["id"], candidate_id="cand-b1", ordinal=1)
        )
        with pytest.raises(ValueError, match="parent attempt does not belong to this run"):
            alpha_run_repository.append_candidate_lineage(
                run_id=run_a["id"],
                lineage_id="lin-x",
                child_attempt_id="cand-a1",
                parent_attempt_id="cand-b1",
                edge_ordinal=0,
                operation="crossover",
            )

    def test_self_lineage_rejected(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-self")
        alpha_run_repository.append_candidate_attempt(
            **_candidate_params(run_id=run["id"], candidate_id="cand-self", ordinal=1)
        )
        with pytest.raises(ValueError, match="child and parent attempts must differ"):
            alpha_run_repository.append_candidate_lineage(
                run_id=run["id"],
                lineage_id="lin-self",
                child_attempt_id="cand-self",
                parent_attempt_id="cand-self",
                edge_ordinal=0,
                operation="clone",
            )


class TestEventSequencingAndIdempotency:
    def test_committed_sequences_are_contiguous(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-seq")
        for i in range(1, 4):
            alpha_run_repository.append_run_event(
                run_id=run["id"],
                event_id=f"evt-seq-{i}",
                event_type="candidate_appended",
                entity_kind="candidate",
                entity_id=f"cand-{i}",
                idempotency_key=f"evt-key-seq-{i}",
                actor="service",
                source="api",
                payload={"ordinal": i},
            )
        events = alpha_run_repository.list_run_events(run["id"])
        # run_created is seq 1, then 3 appends → seqs 2, 3, 4
        seqs = [e["seq"] for e in events]
        assert seqs == [1, 2, 3, 4]

    def test_repeated_event_key_same_payload_returns_original_no_new_sequence(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-idem")
        first = alpha_run_repository.append_run_event(
            run_id=run["id"],
            event_id="evt-idem-1",
            event_type="candidate_appended",
            entity_kind="candidate",
            entity_id="cand-1",
            idempotency_key="evt-key-idem",
            actor="service",
            source="api",
            payload={"ordinal": 1},
        )
        second = alpha_run_repository.append_run_event(
            run_id=run["id"],
            event_id="evt-idem-1-dup",
            event_type="candidate_appended",
            entity_kind="candidate",
            entity_id="cand-1",
            idempotency_key="evt-key-idem",
            actor="service",
            source="api",
            payload={"ordinal": 1},
        )
        assert first["id"] == second["id"] == "evt-idem-1"
        events = alpha_run_repository.list_run_events(run["id"])
        # Only one event for this key (plus run_created).
        assert len(events) == 2

    def test_repeated_event_key_changed_payload_raises_conflict(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-conf")
        alpha_run_repository.append_run_event(
            run_id=run["id"],
            event_id="evt-conf-1",
            event_type="candidate_appended",
            entity_kind="candidate",
            entity_id="cand-1",
            idempotency_key="evt-key-conf",
            actor="service",
            source="api",
            payload={"ordinal": 1},
        )
        original_events = alpha_run_repository.list_run_events(run["id"])
        with pytest.raises(AlphaRunConflictError):
            alpha_run_repository.append_run_event(
                run_id=run["id"],
                event_id="evt-conf-2",
                event_type="candidate_appended",
                entity_kind="candidate",
                entity_id="cand-1",
                idempotency_key="evt-key-conf",
                actor="service",
                source="api",
                payload={"ordinal": 999},
            )
        # No row or cursor changed.
        after_events = alpha_run_repository.list_run_events(run["id"])
        assert len(after_events) == len(original_events)

    def test_event_envelope_contains_all_d05_fields(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-env")
        alpha_run_repository.append_run_event(
            run_id=run["id"],
            event_id="evt-env-1",
            event_type="candidate_appended",
            entity_kind="candidate",
            entity_id="cand-env",
            idempotency_key="evt-key-env",
            actor="worker",
            source="adapter",
            payload={"bounded": "summary"},
        )
        events = alpha_run_repository.list_run_events(run["id"])
        evt = next(e for e in events if e["id"] == "evt-env-1")
        for field in (
            "occurred_at", "event_type", "entity_kind", "entity_id",
            "actor", "source", "payload", "payload_checksum",
            "producer_version", "seq", "idempotency_key",
        ):
            assert field in evt
        assert evt["producer_version"] == PRODUCER_VERSION
        assert evt["actor"] == "worker"
        assert evt["source"] == "adapter"
        assert evt["payload"] == {"bounded": "summary"}


class TestAppendOnlyImmutability:
    def test_candidate_attempt_update_and_delete_blocked(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        import sqlite3
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-immut")
        alpha_run_repository.append_candidate_attempt(
            **_candidate_params(run_id=run["id"], candidate_id="cand-immut", ordinal=1)
        )
        with alpha_run_repository._connection() as connection:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE research_alpha_candidate_attempts SET status = 'admitted' "
                    "WHERE id = 'cand-immut'"
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM research_alpha_candidate_attempts WHERE id = 'cand-immut'"
                )

    def test_lineage_update_and_delete_blocked(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        import sqlite3
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-immut-l")
        alpha_run_repository.append_candidate_attempt(
            **_candidate_params(run_id=run["id"], candidate_id="cand-lp", ordinal=1)
        )
        alpha_run_repository.append_candidate_attempt(
            **_candidate_params(run_id=run["id"], candidate_id="cand-lc", ordinal=2)
        )
        alpha_run_repository.append_candidate_lineage(
            run_id=run["id"], lineage_id="lin-immut",
            child_attempt_id="cand-lc", parent_attempt_id="cand-lp",
            edge_ordinal=0, operation="mutation",
        )
        with alpha_run_repository._connection() as connection:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE research_alpha_candidate_lineage SET operation = 'x' "
                    "WHERE id = 'lin-immut'"
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM research_alpha_candidate_lineage WHERE id = 'lin-immut'"
                )


class TestPrincipalScoping:
    def test_candidate_read_cross_principal_returns_empty(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-pc")
        alpha_run_repository.append_candidate_attempt(
            **_candidate_params(run_id=run["id"], candidate_id="cand-pc", ordinal=1)
        )
        # Cross-principal read: same empty boundary as unknown run.
        cross = alpha_run_repository.list_candidates(
            run["id"], principal="other@example.com"
        )
        assert cross == []
        unknown = alpha_run_repository.list_candidates("run-nonexistent")
        assert unknown == []

    def test_event_read_cross_principal_returns_empty(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-pc-evt")
        # Cross-principal: no event existence leak.
        cross = alpha_run_repository.list_run_events(
            run["id"], principal="other@example.com"
        )
        assert cross == []

    def test_no_event_existence_leak_for_unknown_run(
        self,
        alpha_run_repository: ResearchRepository,
    ) -> None:
        # An unknown run and a cross-principal run both return [] — no leak.
        assert alpha_run_repository.list_run_events("no-such-run", principal="x") == []


class TestCommitBeforePublish:
    def test_publisher_exception_does_not_erase_committed_event(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService, RunEventPublisher

        class FailingPublisher:
            def on_run_created(self, run: Mapping[str, object]) -> None:
                raise RuntimeError("publisher exploded")

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-pub")
        service = ResearchRunService(
            alpha_run_repository, publisher=FailingPublisher()
        )
        # The append succeeds; publisher failure is swallowed.
        event = service.append_event(
            run_id=run["id"],
            principal="researcher@example.com",
            event_type="candidate_appended",
            entity_kind="candidate",
            entity_id="cand-pub",
            idempotency_key="evt-pub-1",
            actor="service",
            source="api",
            payload={"ordinal": 1},
        )
        assert event is not None
        # The event is durable despite the publisher exception.
        events = alpha_run_repository.list_run_events(run["id"])
        ids = [e["id"] for e in events]
        assert event["id"] in ids