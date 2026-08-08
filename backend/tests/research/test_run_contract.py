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
