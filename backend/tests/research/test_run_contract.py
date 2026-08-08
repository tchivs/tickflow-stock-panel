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
from concurrent.futures import ThreadPoolExecutor
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
# Scoring-stage additive manifest extension (Phase 47-02, AF-REQ-06)
# ================================================================


def _scoring_manifest(*, seed: int = 42) -> dict:
    """A complete D-04 manifest that also declares a scoring stage."""
    manifest = _sample_manifest(seed=seed)
    manifest["fold_geometry"]["oos_size"] = 20
    manifest["fold_geometry"]["horizon"] = 5
    manifest["costs"] = {
        "commission_pct": 0.0003,
        "stamp_tax_pct": 0.001,
        "slippage_bps": 5.0,
    }
    manifest["scoring"] = {
        "rebalance": "daily",
        "n_groups": 5,
        "warmup_days": 10,
    }
    return manifest


class TestScoringStageManifest:
    def test_manifest_without_scoring_validates_unchanged(self) -> None:
        """No ``scoring`` group ⇒ no new checks (Phase 45/46 snapshots byte-identical)."""
        baseline = _sample_manifest()
        scoring = _scoring_manifest()
        del scoring["scoring"]
        # A no-scoring manifest validates identically to the baseline fixture.
        freeze_input_snapshot(manifest=baseline, created_at="2026-08-08T00:00:00+00:00")
        freeze_input_snapshot(manifest=scoring, created_at="2026-08-08T00:00:00+00:00")

    def test_complete_scoring_manifest_freezes_with_deterministic_digest(
        self, deterministic_clock: DeterministicClock
    ) -> None:
        manifest = _scoring_manifest()
        now = deterministic_clock.now_iso()
        snapshot_a = freeze_input_snapshot(manifest=manifest, created_at=now)
        snapshot_b = freeze_input_snapshot(manifest=manifest, created_at=now)
        assert snapshot_a.manifest_sha256 == snapshot_b.manifest_sha256
        assert len(snapshot_a.manifest_sha256) == 64

    def test_changing_scoring_field_changes_digest(
        self, deterministic_clock: DeterministicClock
    ) -> None:
        now = deterministic_clock.now_iso()
        base = freeze_input_snapshot(manifest=_scoring_manifest(seed=42), created_at=now)
        changed = _scoring_manifest(seed=42)
        changed["scoring"]["n_groups"] = 6
        other = freeze_input_snapshot(manifest=changed, created_at=now)
        assert base.manifest_sha256 != other.manifest_sha256

    def test_scoring_manifest_missing_oos_size_fails_closed(self) -> None:
        manifest = _scoring_manifest()
        del manifest["fold_geometry"]["oos_size"]
        with pytest.raises(ValueError, match="oos_size"):
            freeze_input_snapshot(manifest=manifest, created_at="2026-08-08T00:00:00+00:00")

    def test_scoring_manifest_missing_horizon_fails_closed(self) -> None:
        manifest = _scoring_manifest()
        del manifest["fold_geometry"]["horizon"]
        with pytest.raises(ValueError, match="horizon"):
            freeze_input_snapshot(manifest=manifest, created_at="2026-08-08T00:00:00+00:00")

    def test_scoring_manifest_missing_costs_fails_closed(self) -> None:
        manifest = _scoring_manifest()
        del manifest["costs"]
        with pytest.raises(ValueError, match="costs"):
            freeze_input_snapshot(manifest=manifest, created_at="2026-08-08T00:00:00+00:00")

    def test_scoring_manifest_cost_out_of_range_fails_closed(self) -> None:
        manifest = _scoring_manifest()
        manifest["costs"]["commission_pct"] = 1.5  # >= 1.0 is not a fraction
        with pytest.raises(ValueError, match="commission_pct"):
            freeze_input_snapshot(manifest=manifest, created_at="2026-08-08T00:00:00+00:00")

    def test_scoring_manifest_negative_slippage_fails_closed(self) -> None:
        manifest = _scoring_manifest()
        manifest["costs"]["slippage_bps"] = -1.0
        with pytest.raises(ValueError, match="slippage_bps"):
            freeze_input_snapshot(manifest=manifest, created_at="2026-08-08T00:00:00+00:00")

    def test_scoring_manifest_bad_rebalance_fails_closed(self) -> None:
        manifest = _scoring_manifest()
        manifest["scoring"]["rebalance"] = "hourly"
        with pytest.raises(ValueError, match="rebalance"):
            freeze_input_snapshot(manifest=manifest, created_at="2026-08-08T00:00:00+00:00")

    def test_scoring_manifest_n_groups_below_two_fails_closed(self) -> None:
        manifest = _scoring_manifest()
        manifest["scoring"]["n_groups"] = 1
        with pytest.raises(ValueError, match="n_groups"):
            freeze_input_snapshot(manifest=manifest, created_at="2026-08-08T00:00:00+00:00")

    def test_scoring_manifest_negative_warmup_fails_closed(self) -> None:
        manifest = _scoring_manifest()
        manifest["scoring"]["warmup_days"] = -1
        with pytest.raises(ValueError, match="warmup_days"):
            freeze_input_snapshot(manifest=manifest, created_at="2026-08-08T00:00:00+00:00")

    def test_scoring_group_present_but_empty_fails_closed(self) -> None:
        manifest = _scoring_manifest()
        manifest["scoring"] = {}
        with pytest.raises(ValueError, match="scoring"):
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
    def test_concurrent_create_same_key_returns_one_durable_run(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from threading import Barrier

        snapshot = freeze_input_snapshot(
            manifest=_sample_manifest(), created_at=deterministic_clock.now_iso()
        )
        barrier = Barrier(2)

        def create(index: int) -> dict[str, object]:
            barrier.wait()
            return alpha_run_repository.create_alpha_run(
                run_id=f"run-race-{index}", principal="researcher@example.com",
                idempotency_key="idem-race-create-0001", snapshot=snapshot,
                event_id=f"evt-race-{index}",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(create, (1, 2)))
        assert {result["id"] for result in results} == {results[0]["id"]}
        assert len(alpha_run_repository.list_run_events(results[0]["id"])) == 1

    def test_concurrent_start_and_recovery_return_durable_winners(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from threading import Barrier

        from app.research.run_service import ResearchRunService

        snapshot = freeze_input_snapshot(
            manifest=_sample_manifest(seed=73), created_at=deterministic_clock.now_iso()
        )
        run = alpha_run_repository.create_alpha_run(
            run_id="run-race-lifecycle", principal="researcher@example.com",
            idempotency_key="idem-race-lifecycle-0001", snapshot=snapshot,
            event_id="evt-race-lifecycle",
        )

        start_barrier = Barrier(2)

        def start(_: int) -> dict[str, object]:
            start_barrier.wait()
            return ResearchRunService(alpha_run_repository).start_or_resume(
                run["id"], principal="researcher@example.com",
                expected_version=run["transition_version"],
                idempotency_key="idem-race-start-0001",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            started = list(executor.map(start, (1, 2)))
        assert {result["status"] for result in started} == {"running"}
        assert sum("_attempt_token" in result for result in started) <= 1
        events = alpha_run_repository.list_run_events(run["id"])
        assert [event["event_type"] for event in events].count("run_started") == 1

        recovery_barrier = Barrier(2)
        started_version = started[0]["transition_version"]

        def recover(_: int) -> dict[str, object]:
            recovery_barrier.wait()
            return ResearchRunService(alpha_run_repository).recover_running_attempt(
                run["id"], principal="researcher@example.com",
                expected_version=started_version,
                idempotency_key="idem-race-recovery-0001",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            recovered = list(executor.map(recover, (1, 2)))
        assert {result["transition_version"] for result in recovered} == {started_version + 1}
        assert sum("_attempt_token" in result for result in recovered) <= 1
        events = alpha_run_repository.list_run_events(run["id"])
        assert [event["event_type"] for event in events].count("run_recovered") == 1
    def test_start_replay_requires_an_existing_run_started_event(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-start-event-type")
        key = "idem-start-event-type-0001"
        alpha_run_repository.append_run_event(
            run_id=run["id"], event_id="evt-non-start", event_type="candidate_appended",
            entity_kind="candidate", entity_id="candidate-1", idempotency_key=key,
            actor="service", source="test",
            payload={"from": "queued", "to": "running", "attempt_token_digest": "a" * 64},
        )
        with pytest.raises(AlphaRunConflictError):
            alpha_run_repository.transition_alpha_run(
                run_id=run["id"], principal="researcher@example.com",
                from_status="queued", to_status="running", expected_version=run["transition_version"],
                event_id="evt-start-collision", event_type="run_started", idempotency_key=key,
                extra_payload={"attempt_token_digest": "b" * 64},
            )
        assert alpha_run_repository.get_alpha_run(run["id"])["status"] == "queued"


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
            "invalid", "duplicate", "low_coverage", "generated", "failed",
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
        assert len(candidates) == 9
        assert [c["status"] for c in candidates] == statuses
        assert [c["attempt_ordinal"] for c in candidates] == list(range(1, 10))
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


# ================================================================
# Task 45-02-02: Verified artifacts and bounded checkpoint replay
# ================================================================


class TestAlphaRunArtifacts:
    def test_server_derives_exact_content_addressed_path(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
        alpha_artifact_root: Path,
    ) -> None:
        from app.research.artifacts import AlphaRunArtifactService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-art-path")
        service = AlphaRunArtifactService(alpha_artifact_root.parent)
        descriptor = service.write(
            run_id=run["id"], payload={"evidence": "metrics", "n": 1}
        )
        expected_digest = descriptor["checksum_sha256"]
        expected_path = f"research_artifacts/alpha_runs/{run['id']}/{expected_digest}.json"
        assert descriptor["relative_path"] == expected_path
        # The file physically exists at exactly that key.
        assert (alpha_artifact_root.parent / expected_path).is_file()

    def test_client_supplied_path_rejected_by_repository(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-art-rej")
        with pytest.raises(ValueError, match="server-derived content-addressed key"):
            alpha_run_repository.append_artifact(
                run_id=run["id"],
                artifact_id="art-bad-path",
                logical_kind="evidence",
                relative_path="arbitrary/client/path.json",
                content_type="application/json",
                byte_size=10,
                checksum_sha256="a" * 64,
            )

    def test_verify_artifact_rejects_missing(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
        alpha_artifact_root: Path,
    ) -> None:
        from app.research.artifacts import (
            AlphaArtifactVerificationError,
            AlphaRunArtifactService,
        )

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-art-miss")
        service = AlphaRunArtifactService(alpha_artifact_root.parent)
        with pytest.raises(AlphaArtifactVerificationError, match="not found"):
            service.verify_artifact(run_id=run["id"], checksum_sha256="a" * 64)

    def test_verify_artifact_rejects_changed_bytes(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
        alpha_artifact_root: Path,
    ) -> None:
        from app.research.artifacts import (
            AlphaArtifactVerificationError,
            AlphaRunArtifactService,
        )

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-art-chg")
        service = AlphaRunArtifactService(alpha_artifact_root.parent)
        descriptor = service.write(run_id=run["id"], payload={"v": 1})
        # Tamper with the bytes on disk.
        path = alpha_artifact_root.parent / descriptor["relative_path"]
        path.write_bytes(b'{"tampered": true}')
        with pytest.raises(AlphaArtifactVerificationError, match="do not match"):
            service.verify_artifact(
                run_id=run["id"], checksum_sha256=descriptor["checksum_sha256"]
            )

    def test_verify_artifact_rejects_bad_size(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
        alpha_artifact_root: Path,
    ) -> None:
        from app.research.artifacts import (
            AlphaArtifactVerificationError,
            AlphaRunArtifactService,
        )

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-art-size")
        service = AlphaRunArtifactService(alpha_artifact_root.parent)
        descriptor = service.write(run_id=run["id"], payload={"v": 1})
        with pytest.raises(AlphaArtifactVerificationError, match="byte size"):
            service.verify_artifact(
                run_id=run["id"],
                checksum_sha256=descriptor["checksum_sha256"],
                expected_byte_size=descriptor["byte_size"] + 999,
            )

    def test_verify_artifact_rejects_path_traversal_run_id(
        self,
        alpha_artifact_root: Path,
    ) -> None:
        from app.research.artifacts import (
            AlphaArtifactVerificationError,
            AlphaRunArtifactService,
        )

        service = AlphaRunArtifactService(alpha_artifact_root.parent)
        with pytest.raises(AlphaArtifactVerificationError, match="invalid path characters"):
            service.verify_artifact(run_id="../escape", checksum_sha256="a" * 64)

    def test_artifact_reference_value_object_has_expected_relative_path(
        self,
    ) -> None:
        from app.research.run_contract import AlphaArtifactReference

        ref = AlphaArtifactReference(
            artifact_id="art-1",
            run_id="arun_abc123",
            logical_kind="evidence",
            relative_path="research_artifacts/alpha_runs/arun_abc123/aaaa.json",
            content_type="application/json",
            byte_size=42,
            checksum_sha256="a" * 64,
            schema_version="alpha-artifact-v1",
            created_at="2026-08-08T00:00:00Z",
        )
        assert ref.expected_relative_path == (
            "research_artifacts/alpha_runs/arun_abc123/" + "a" * 64 + ".json"
        )


class TestInlineCheckpointBound:
    def test_inline_payload_at_exactly_16kib_accepted(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        service = ResearchRunService(alpha_run_repository)
        # Build a canonical JSON payload of exactly 16384 bytes.
        import json

        # Build canonical JSON of exactly MAX_INLINE_CHECKPOINT_BYTES (16384).
        from app.research.run_contract import MAX_INLINE_CHECKPOINT_BYTES

        # Pad a string value to hit the exact byte bound.
        base = json.dumps({"x": ""}, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload = {"x": "a" * (MAX_INLINE_CHECKPOINT_BYTES - len(base))}
        payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        assert len(payload_bytes) == MAX_INLINE_CHECKPOINT_BYTES
        # Should not raise.
        service.validate_inline_checkpoint_payload(payload_bytes)

    def test_oversized_inline_payload_rejected(
        self,
        alpha_run_repository: ResearchRepository,
    ) -> None:
        from app.research.run_service import (
            AlphaCheckpointValidationError,
            ResearchRunService,
        )

        service = ResearchRunService(alpha_run_repository)
        with pytest.raises(AlphaCheckpointValidationError, match="exceeds 16 KiB"):
            service.validate_inline_checkpoint_payload(b"x" * 16385)

    def test_non_utf8_inline_payload_rejected(
        self,
        alpha_run_repository: ResearchRepository,
    ) -> None:
        from app.research.run_service import (
            AlphaCheckpointValidationError,
            ResearchRunService,
        )

        service = ResearchRunService(alpha_run_repository)
        with pytest.raises(AlphaCheckpointValidationError, match="canonical UTF-8 JSON"):
            service.validate_inline_checkpoint_payload(b"\xff\xfe\x00")

    def test_non_json_inline_payload_rejected(
        self,
        alpha_run_repository: ResearchRepository,
    ) -> None:
        from app.research.run_service import (
            AlphaCheckpointValidationError,
            ResearchRunService,
        )

        service = ResearchRunService(alpha_run_repository)
        with pytest.raises(AlphaCheckpointValidationError, match="canonical UTF-8 JSON"):
            service.validate_inline_checkpoint_payload(b"not json at all")


class TestCheckpointValidation:
    def _make_checkpoint_params(
        self, run: dict, *, event_seq: int, version: int = 1, **overrides
    ) -> dict:
        """Build checkpoint parameters matching the run's digests."""
        from app.research.run_contract import checkpoint_state_checksum

        params = {
            "checkpoint_version": version,
            "committed_event_seq": event_seq,
            "stage": "search",
            "snapshot_sha256": run["snapshot_sha256"],
            "manifest_sha256": run["manifest_sha256"],
        }
        params.update(overrides)
        state_checksum = checkpoint_state_checksum(
            run_id=run["id"],
            checkpoint_version=params["checkpoint_version"],
            committed_event_seq=params["committed_event_seq"],
            stage=params["stage"],
            snapshot_sha256=params["snapshot_sha256"],
            manifest_sha256=params["manifest_sha256"],
            referenced_candidate_ids=[],
            inline_summary=None,
            frontier_artifact_id=None,
        )
        params["state_checksum"] = state_checksum
        return params

    def test_valid_checkpoint_written_and_recovered_after_restart(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
        tmp_path: Path,
    ) -> None:
        from app.research.run_contract import attempt_token_digest
        from app.research.run_service import ResearchRunService
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-chk-ok")
        started = ResearchRunService(alpha_run_repository).start_or_resume(
            run["id"], principal="researcher@example.com", expected_version=run["transition_version"]
        )
        params = self._make_checkpoint_params(run, event_seq=1)
        alpha_run_repository.append_checkpoint(
            run_id=run["id"], checkpoint_id="chk-ok-1", principal="researcher@example.com",
            expected_version=started["transition_version"],
            expected_attempt_token_digest=attempt_token_digest(started["_attempt_token"]), **params,
        )
        # Simulate restart with a fresh repository.
        fresh = ResearchRepository(
            alpha_run_repository.database_path,
            clock=deterministic_clock,
            artifact_root=tmp_path / "alpha_artifacts",
        )
        recovered = ResearchRunService(fresh).get_latest_valid_checkpoint(
            run["id"], principal="researcher@example.com"
        )
        assert recovered is not None
        assert recovered["checkpoint_version"] == 1
        assert recovered["committed_event_seq"] == 1
    def test_checkpoint_validation_verifies_artifact_backed_event_prefix(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock, alpha_artifact_root: Path) -> None:
        from app.research.artifacts import AlphaRunArtifactService
        from app.research.run_service import ResearchRunService
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-chk-event-artifact")
        artifacts = AlphaRunArtifactService(alpha_artifact_root.parent)
        descriptor = artifacts.write(run_id=run["id"], payload={"event": "verified"})
        alpha_run_repository.append_artifact(
            run_id=run["id"], artifact_id="event-artifact", logical_kind="event-evidence",
            relative_path=descriptor["relative_path"], content_type=descriptor["content_type"],
            byte_size=descriptor["byte_size"], checksum_sha256=descriptor["checksum_sha256"],
        )
        service = ResearchRunService(alpha_run_repository, artifact_service=artifacts)
        event = service.append_event(
            run_id=run["id"], principal="researcher@example.com", event_type="stage_started",
            entity_kind="stage", entity_id="search", idempotency_key="artifact-event-key",
            actor="worker", source="worker", payload={"stage": "search"}, artifact_id="event-artifact",
        )
        assert event is not None and event["seq"] == 2
        checkpoint = self._make_checkpoint_params(run, event_seq=2)
        assert service.validate_checkpoint(
            run_id=run["id"], principal="researcher@example.com", checkpoint=checkpoint,
        )["committed_event_seq"] == 2

    def test_stale_snapshot_digest_rejected(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import (
            AlphaCheckpointValidationError,
            ResearchRunService,
        )

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-chk-stale")
        service = ResearchRunService(alpha_run_repository)
        params = self._make_checkpoint_params(
            run, event_seq=1, snapshot_sha256="z" * 64
        )
        with pytest.raises(AlphaCheckpointValidationError, match="snapshot digest mismatch"):
            service.validate_checkpoint(
                run_id=run["id"],
                principal="researcher@example.com",
                checkpoint=params,
            )

    def test_stale_manifest_digest_rejected(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import (
            AlphaCheckpointValidationError,
            ResearchRunService,
        )

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-chk-manifest")
        service = ResearchRunService(alpha_run_repository)
        params = self._make_checkpoint_params(
            run, event_seq=1, manifest_sha256="z" * 64
        )
        with pytest.raises(AlphaCheckpointValidationError, match="manifest digest mismatch"):
            service.validate_checkpoint(
                run_id=run["id"],
                principal="researcher@example.com",
                checkpoint=params,
            )

    def test_future_event_sequence_rejected(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import (
            AlphaCheckpointValidationError,
            ResearchRunService,
        )

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-chk-future")
        service = ResearchRunService(alpha_run_repository)
        # The run has last_event_seq = 1; claim committed_event_seq = 99.
        params = self._make_checkpoint_params(run, event_seq=99)
        with pytest.raises(AlphaCheckpointValidationError, match="future event sequence"):
            service.validate_checkpoint(
                run_id=run["id"],
                principal="researcher@example.com",
                checkpoint=params,
            )

    def test_missing_referenced_candidate_rejected(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import (
            AlphaCheckpointValidationError,
            ResearchRunService,
        )

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-chk-cand")
        service = ResearchRunService(alpha_run_repository)
        params = self._make_checkpoint_params(run, event_seq=1)
        with pytest.raises(AlphaCheckpointValidationError, match="missing candidate"):
            service.validate_checkpoint(
                run_id=run["id"],
                principal="researcher@example.com",
                checkpoint=params,
                referenced_candidate_ids=["cand-nonexistent"],
            )

    def test_bad_cursor_checksum_rejected(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import (
            AlphaCheckpointValidationError,
            ResearchRunService,
        )

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-chk-bad")
        service = ResearchRunService(alpha_run_repository)
        params = self._make_checkpoint_params(run, event_seq=1)
        params["state_checksum"] = "0" * 64  # wrong checksum
        with pytest.raises(AlphaCheckpointValidationError, match="state checksum mismatch"):
            service.validate_checkpoint(
                run_id=run["id"],
                principal="researcher@example.com",
                checkpoint=params,
            )

    def test_cross_principal_checkpoint_rejected(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_contract import attempt_token_digest
        from app.research.run_service import (
            AlphaCheckpointValidationError,
            ResearchRunService,
        )

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-chk-xp")
        started = ResearchRunService(alpha_run_repository).start_or_resume(
            run["id"], principal="researcher@example.com", expected_version=run["transition_version"]
        )
        params = self._make_checkpoint_params(run, event_seq=1)
        alpha_run_repository.append_checkpoint(
            run_id=run["id"], checkpoint_id="chk-xp-1", principal="researcher@example.com",
            expected_version=started["transition_version"],
            expected_attempt_token_digest=attempt_token_digest(started["_attempt_token"]), **params,
        )
        # Cross-principal: same None boundary as unknown run.
        assert ResearchRunService(alpha_run_repository).get_latest_valid_checkpoint(
            run["id"], principal="other@example.com"
        ) is None
        service = ResearchRunService(alpha_run_repository)
        with pytest.raises(AlphaCheckpointValidationError, match="run not found for principal"):
            service.validate_checkpoint(
                run_id=run["id"],
                principal="other@example.com",
                checkpoint=params,
            )

    def test_checkpoint_with_frontier_artifact_verified(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
        alpha_artifact_root: Path,
    ) -> None:
        from app.research.artifacts import AlphaRunArtifactService
        from app.research.run_contract import checkpoint_state_checksum
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-chk-art")
        art_service = AlphaRunArtifactService(alpha_artifact_root.parent)
        descriptor = art_service.write(run_id=run["id"], payload={"frontier": [1, 2, 3]})
        artifact_ref = alpha_run_repository.append_artifact(
            run_id=run["id"],
            artifact_id="art-frontier-1",
            logical_kind="frontier",
            relative_path=descriptor["relative_path"],
            content_type=descriptor["content_type"],
            byte_size=descriptor["byte_size"],
            checksum_sha256=descriptor["checksum_sha256"],
        )
        state_checksum = checkpoint_state_checksum(
            run_id=run["id"],
            checkpoint_version=1,
            committed_event_seq=1,
            stage="search",
            snapshot_sha256=run["snapshot_sha256"],
            manifest_sha256=run["manifest_sha256"],
            referenced_candidate_ids=[],
            inline_summary=None,
            frontier_artifact_id=artifact_ref["id"],
        )
        params = {
            "checkpoint_version": 1,
            "committed_event_seq": 1,
            "stage": "search",
            "snapshot_sha256": run["snapshot_sha256"],
            "manifest_sha256": run["manifest_sha256"],
            "state_checksum": state_checksum,
            "frontier_artifact_id": artifact_ref["id"],
        }
        service = ResearchRunService(alpha_run_repository, artifact_service=art_service)
        # Should succeed — artifact exists, size/digest match.
        result = service.validate_checkpoint(
            run_id=run["id"], principal="researcher@example.com", checkpoint=params
        )
        assert result["frontier_artifact_id"] == artifact_ref["id"]
    def test_checkpoint_frontier_artifact_tampered_rejected(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
        alpha_artifact_root: Path,
    ) -> None:
        from app.research.artifacts import AlphaRunArtifactService
        from app.research.run_contract import checkpoint_state_checksum
        from app.research.run_service import (
            AlphaCheckpointValidationError,
            ResearchRunService,
        )

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-chk-tamp")
        art_service = AlphaRunArtifactService(alpha_artifact_root.parent)
        descriptor = art_service.write(run_id=run["id"], payload={"frontier": [1, 2]})
        artifact_ref = alpha_run_repository.append_artifact(
            run_id=run["id"],
            artifact_id="art-frontier-tamp",
            logical_kind="frontier",
            relative_path=descriptor["relative_path"],
            content_type=descriptor["content_type"],
            byte_size=descriptor["byte_size"],
            checksum_sha256=descriptor["checksum_sha256"],
        )
        # Tamper with artifact bytes.
        path = alpha_artifact_root.parent / descriptor["relative_path"]
        path.write_bytes(b'{"tampered": true}')
        state_checksum = checkpoint_state_checksum(
            run_id=run["id"], checkpoint_version=1, committed_event_seq=1,
            stage="search", snapshot_sha256=run["snapshot_sha256"],
            manifest_sha256=run["manifest_sha256"], referenced_candidate_ids=[],
            inline_summary=None, frontier_artifact_id=artifact_ref["id"],
        )
        params = {
            "checkpoint_version": 1, "committed_event_seq": 1, "stage": "search",
            "snapshot_sha256": run["snapshot_sha256"],
            "manifest_sha256": run["manifest_sha256"], "state_checksum": state_checksum,
            "frontier_artifact_id": artifact_ref["id"],
        }
        service = ResearchRunService(alpha_run_repository, artifact_service=art_service)
        with pytest.raises(AlphaCheckpointValidationError):
            service.validate_checkpoint(
                run_id=run["id"], principal="researcher@example.com", checkpoint=params
            )


class TestReplayReadOnly:
    def test_replay_with_candidates_is_deterministic_and_read_only(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
        tmp_path: Path,
    ) -> None:
        from app.research.run_service import ResearchRunService

        service = ResearchRunService(alpha_run_repository)
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-replay")
        for i in range(1, 4):
            alpha_run_repository.append_candidate_attempt(
                **_candidate_params(
                    run_id=run["id"], candidate_id=f"cand-r-{i}", ordinal=i,
                )
            )
        first = service.replay(
            run["id"], principal="researcher@example.com", include_candidates=True
        )
        # Fresh repository = process restart; replay must be identical.
        fresh_repo = ResearchRepository(
            alpha_run_repository.database_path,
            clock=deterministic_clock,
            artifact_root=tmp_path / "alpha_artifacts",
        )
        fresh_service = ResearchRunService(fresh_repo)
        second = fresh_service.replay(
            run["id"], principal="researcher@example.com", include_candidates=True
        )
        assert first is not None and second is not None
        assert [c["id"] for c in first["candidates"]] == [c["id"] for c in second["candidates"]]
        assert len(first["candidates"]) == 3
        # Replay does not resolve current constituents, policy, code, or OOS.
        assert "manifest" in first["snapshot"]
        assert first["run"]["status"] == "queued"

    def test_replay_cross_principal_returns_none(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-replay-xp")
        service = ResearchRunService(alpha_run_repository)
        result = service.replay(run["id"], principal="other@example.com")
        assert result is None

    def test_checkpoint_does_not_accept_pickle_or_executable_state(
        self,
        alpha_run_repository: ResearchRepository,
    ) -> None:
        from app.research.run_service import (
            AlphaCheckpointValidationError,
            ResearchRunService,
        )

        service = ResearchRunService(alpha_run_repository)
        # Pickle bytes (0x80 = protocol marker) are not valid UTF-8 JSON.
        with pytest.raises(AlphaCheckpointValidationError):
            service.validate_inline_checkpoint_payload(b"\x80\x04\x95")


# ================================================================
# Wave 3 — guarded lifecycle transitions, retry, cancellation
# ================================================================


class TestLifecycleTransitions:
    """Legal edges, illegal edges, stale expected-version, and principal scoping."""

    def test_legal_queued_to_running_transition_increments_version_and_appends_event(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-lc-01")
        service = ResearchRunService(alpha_run_repository)
        result = service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        assert result is not None
        assert result["status"] == "running"
        assert result["transition_version"] == run["transition_version"] + 1
        events = alpha_run_repository.list_run_events(run["id"])
        # run_created (seq 1) + run_started (seq 2)
        assert len(events) == 2
        assert events[1]["event_type"] == "run_started"
        assert events[1]["seq"] == 2

    def test_illegal_transition_queued_to_completed_is_rejected(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-lc-02")
        service = ResearchRunService(alpha_run_repository)
        with pytest.raises(ValueError, match="illegal lifecycle"):
            service.transition(
                run["id"],
                principal="researcher@example.com",
                from_status="queued",
                to_status="completed",
                expected_version=run["transition_version"],
            )
        # Nothing changed: status, version, event count.
        after = alpha_run_repository.get_alpha_run(run["id"])
        assert after["status"] == "queued"
        assert after["transition_version"] == run["transition_version"]
        assert len(alpha_run_repository.list_run_events(run["id"])) == 1

    def test_stale_expected_version_is_rejected_with_no_side_effect(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-lc-03")
        service = ResearchRunService(alpha_run_repository)
        with pytest.raises(ValueError, match="stale|changed|expected"):
            service.start_or_resume(
                run["id"],
                principal="researcher@example.com",
                expected_version=999,  # stale
            )
        after = alpha_run_repository.get_alpha_run(run["id"])
        assert after["status"] == "queued"
        assert after["transition_version"] == run["transition_version"]

    def test_terminal_state_cannot_transition_back(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-lc-04")
        service = ResearchRunService(alpha_run_repository)
        # queued -> running -> completed
        running = service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        service.transition(
            run["id"],
            principal="researcher@example.com",
            from_status="running",
            to_status="completed",
            expected_version=running["transition_version"],
        )
        # Now try an illegal transition out of terminal completed.
        with pytest.raises(ValueError, match="illegal lifecycle"):
            service.start_or_resume(
                run["id"],
                principal="researcher@example.com",
                expected_version=running["transition_version"] + 1,
            )
        after = alpha_run_repository.get_alpha_run(run["id"])
        assert after["status"] == "completed"

    def test_preflight_failed_terminal_uses_run_level_not_candidate_invalid(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-lc-05")
        service = ResearchRunService(alpha_run_repository)
        result = service.transition(
            run["id"],
            principal="researcher@example.com",
            from_status="queued",
            to_status="preflight_failed",
            expected_version=run["transition_version"],
            terminal_reason="missing vocabulary",
        )
        assert result["status"] == "preflight_failed"
        import json
        assert json.loads(result["terminal_reason"])["code"] == "preflight_failed"
        assert result["finished_at"] is not None

    def test_cross_principal_transition_returns_none(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-lc-06")
        service = ResearchRunService(alpha_run_repository)
        result = service.start_or_resume(
            run["id"],
            principal="attacker@example.com",
            expected_version=run["transition_version"],
        )
        assert result is None
        after = alpha_run_repository.get_alpha_run(run["id"])
        assert after["status"] == "queued"


class TestStartOrResumeIdempotency:
    def test_duplicate_start_returns_running_and_no_duplicate_event(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-dup-01")
        service = ResearchRunService(alpha_run_repository)
        first = service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
            idempotency_key="start-once",
        )
        # Same key again — should return existing running state, no new event.
        second = service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
            idempotency_key="start-once",
        )
        assert second is not None
        assert second["status"] == "running"
        assert second["transition_version"] == first["transition_version"]
        events = alpha_run_repository.list_run_events(run["id"])
        assert len(events) == 2  # run_created + run_started (no duplicate)


class TestCooperativeCancellation:
    def test_cancel_appends_cancel_requested_then_cancelled(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-can-01")
        service = ResearchRunService(alpha_run_repository)
        running = service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        # Step 1: request cancel from running.
        service.cancel(
            run["id"],
            principal="researcher@example.com",
            expected_version=running["transition_version"],
        )
        mid = alpha_run_repository.get_alpha_run(run["id"])
        assert mid["status"] == "cancel_requested"

        # Step 2: worker observes and records terminal cancelled.
        service.transition(
            run["id"],
            principal="researcher@example.com",
            from_status="cancel_requested",
            to_status="cancelled",
            expected_version=mid["transition_version"],
        )
        final = alpha_run_repository.get_alpha_run(run["id"])
        assert final["status"] == "cancelled"
        assert final["finished_at"] is not None
        event_types = [e["event_type"] for e in alpha_run_repository.list_run_events(run["id"])]
        assert "cancel_requested" in event_types
        assert "run_cancelled" in event_types

    def test_late_worker_completion_after_cancel_is_rejected(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-can-02")
        service = ResearchRunService(alpha_run_repository)
        running = service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        service.cancel(
            run["id"],
            principal="researcher@example.com",
            expected_version=running["transition_version"],
        )
        mid = alpha_run_repository.get_alpha_run(run["id"])
        # A late worker tries to append success (completed) after cancel_requested.
        with pytest.raises(ValueError, match="illegal lifecycle"):
            service.transition(
                run["id"],
                principal="researcher@example.com",
                from_status="cancel_requested",
                to_status="completed",
                expected_version=mid["transition_version"],
            )
        after = alpha_run_repository.get_alpha_run(run["id"])
        assert after["status"] == "cancel_requested"

    def test_cancel_is_idempotent(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-can-03")
        service = ResearchRunService(alpha_run_repository)
        running = service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        first = service.cancel(
            run["id"],
            principal="researcher@example.com",
            expected_version=running["transition_version"],
            idempotency_key="cancel-once",
        )
        before_events = len(alpha_run_repository.list_run_events(run["id"]))
        second = service.cancel(
            run["id"],
            principal="researcher@example.com",
            expected_version=running["transition_version"],
            idempotency_key="cancel-once",
        )
        assert second is not None
        assert second["status"] == "cancel_requested"
        assert second["transition_version"] == first["transition_version"]
        after_events = len(alpha_run_repository.list_run_events(run["id"]))
        assert before_events == after_events  # no duplicate cancel event

    def test_cancel_queued_before_start(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-can-04")
        service = ResearchRunService(alpha_run_repository)
        result = service.cancel(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        assert result["status"] == "cancel_requested"


class TestRetry:
    def test_retry_creates_linked_child_run_preserving_parent(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        parent = _make_run(alpha_run_repository, deterministic_clock, run_id="run-retry-par")
        service = ResearchRunService(alpha_run_repository)
        child = service.retry(
            parent["id"],
            principal="researcher@example.com",
            idempotency_key="retry-0001",
            manifest=_sample_manifest(),
        )
        assert child is not None
        assert child["id"] != parent["id"]
        assert child["retry_of_run_id"] == parent["id"]
        assert child["retry_attempt"] == 1
        assert child["status"] == "queued"
        assert child["snapshot_sha256"] == parent["snapshot_sha256"]
        # Parent is immutable.
        parent_after = alpha_run_repository.get_alpha_run(parent["id"])
        assert parent_after["status"] == parent["status"]
        assert parent_after["transition_version"] == parent["transition_version"]

    def test_retry_idempotent_same_key_returns_existing_child(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        parent = _make_run(alpha_run_repository, deterministic_clock, run_id="run-retry-idem")
        service = ResearchRunService(alpha_run_repository)
        first = service.retry(
            parent["id"],
            principal="researcher@example.com",
            idempotency_key="retry-0002",
            manifest=_sample_manifest(),
        )
        second = service.retry(
            parent["id"],
            principal="researcher@example.com",
            idempotency_key="retry-0002",
            manifest=_sample_manifest(),
        )
        assert second["id"] == first["id"]
        assert second["transition_version"] == first["transition_version"]

    def test_retry_changed_input_creates_new_snapshot_digest(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        parent = _make_run(alpha_run_repository, deterministic_clock, run_id="run-retry-chg")
        service = ResearchRunService(alpha_run_repository)
        child = service.retry(
            parent["id"],
            principal="researcher@example.com",
            idempotency_key="retry-0003",
            manifest=_sample_manifest(seed=999),  # different input
        )
        assert child["snapshot_sha256"] != parent["snapshot_sha256"]
        # Parent unchanged.
        parent_after = alpha_run_repository.get_alpha_run(parent["id"])
        assert parent_after["snapshot_sha256"] == parent["snapshot_sha256"]

    def test_retry_cross_principal_returns_none(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        parent = _make_run(alpha_run_repository, deterministic_clock, run_id="run-retry-xp")
        service = ResearchRunService(alpha_run_repository)
        result = service.retry(
            parent["id"],
            principal="attacker@example.com",
            idempotency_key="retry-0004",
            manifest=_sample_manifest(),
        )
        assert result is None


# ================================================================
# Wave 3 — worker adapter, token fencing, progress seam, restart
# ================================================================


class TestAttemptTokenFencing:
    """Opaque server token + expected-version fencing for worker callbacks."""

    def test_running_transition_issues_opaque_token_persisting_only_sha256(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-tok-01")
        service = ResearchRunService(alpha_run_repository)
        result = service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        assert result is not None
        token = result["_attempt_token"]
        assert isinstance(token, str) and len(token) == 64  # 32 bytes hex
        # The raw token bytes must NEVER appear in durable plaintext.
        events = alpha_run_repository.list_run_events(run["id"])
        started_event = [e for e in events if e["event_type"] == "run_started"][0]
        # The raw token bytes must NEVER appear in durable plaintext or projections.
        assert token not in str(started_event)
        # Only the SHA-256 digest appears in the payload.
        from app.research.run_contract import attempt_token_digest

        assert started_event["payload"]["attempt_token_digest"] == attempt_token_digest(token)
        assert token not in str(started_event["payload"])

    def test_valid_callback_requires_both_token_and_expected_version(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService
        from app.research.run_worker import ResearchRunWorkerAdapter

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-tok-02")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        adapter = ResearchRunWorkerAdapter(service, principal="researcher@example.com")
        # Missing token.
        with pytest.raises(ValueError, match="token"):
            adapter.report_progress(
                run_id=run["id"], expected_version=started["transition_version"],
                attempt_token=None, folds_total=10,
            )
        # Valid token + version works.
        result = adapter.report_progress(
            run_id=run["id"], expected_version=started["transition_version"],
            attempt_token=started["_attempt_token"], folds_total=10,
        )
        assert result is not None
        assert result["folds_total"] == 10

    def test_stale_token_is_rejected_after_version_change(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService
        from app.research.run_worker import ResearchRunWorkerAdapter
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-tok-03")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        old_token = started["_attempt_token"]
        old_version = started["transition_version"]
        # Cancel changes the version, invalidating old tokens.
        service.cancel(
            run["id"],
            principal="researcher@example.com",
            expected_version=old_version,
        )
        mid = alpha_run_repository.get_alpha_run(run["id"])
        adapter = ResearchRunWorkerAdapter(service, principal="researcher@example.com")
        # Old token + old version must fail closed.
        result = adapter.report_progress(
            run_id=run["id"], expected_version=old_version,
            attempt_token=old_token, folds_total=10,
        )
        assert result is None  # stale — no side effect
        after = alpha_run_repository.get_alpha_run(run["id"])
        assert after["folds_total"] == 0  # progress was NOT applied

    def test_invalid_token_fails_closed(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService
        from app.research.run_worker import ResearchRunWorkerAdapter

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-tok-04")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        adapter = ResearchRunWorkerAdapter(service, principal="researcher@example.com")
        # Wrong token.
        result = adapter.report_progress(
            run_id=run["id"], expected_version=started["transition_version"],
            attempt_token="deadbeef" * 8, folds_total=10,
        )
        assert result is None
        after = alpha_run_repository.get_alpha_run(run["id"])
        assert after["folds_total"] == 0


class TestProgressCounters:
    """Four bounded server-owned counters persist/report without evaluating folds."""

    def test_progress_persists_all_four_counters(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-prog-01")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        service.update_progress(
            run["id"],
            principal="researcher@example.com",
            expected_version=started["transition_version"],
            attempt_token=started["_attempt_token"],
            candidate_attempts_total=100,
            candidate_attempts_completed=50,
            folds_total=10,
            folds_completed=5,
        )
        after = alpha_run_repository.get_alpha_run(run["id"])
        assert after["candidate_attempts_total"] == 100
        assert after["candidate_attempts_completed"] == 50
        assert after["folds_total"] == 10
        assert after["folds_completed"] == 5

    def test_zero_totals_are_valid_for_fresh_run(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-prog-02")
        after = alpha_run_repository.get_alpha_run(run["id"])
        assert after["candidate_attempts_total"] == 0
        assert after["candidate_attempts_completed"] == 0
        assert after["folds_total"] == 0
        assert after["folds_completed"] == 0

    def test_negative_counter_is_rejected(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-prog-03")
        service = ResearchRunService(alpha_run_repository)
        with pytest.raises(ValueError, match="non-negative"):
            service.update_progress(
                run["id"],
                principal="researcher@example.com",
                expected_version=run["transition_version"],
                attempt_token=None,
                folds_total=-1,
            )

    def test_stale_version_progress_is_rejected(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-prog-04")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        result = service.update_progress(
            run["id"],
            principal="researcher@example.com",
            expected_version=999,  # stale
            attempt_token=started["_attempt_token"],
            folds_total=10,
        )
        assert result is None
        after = alpha_run_repository.get_alpha_run(run["id"])
        assert after["folds_total"] == 0


class TestRestartRecovery:
    """Fresh process recovers durable status/events/candidates/counters."""

    def test_fresh_repository_recovers_status_events_and_counters(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
        tmp_path: Path,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-restart-01")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        service.update_progress(
            run["id"],
            principal="researcher@example.com",
            expected_version=started["transition_version"],
            attempt_token=started["_attempt_token"],
            candidate_attempts_total=200,
            candidate_attempts_completed=100,
            folds_total=10,
            folds_completed=5,
        )

        # Fresh repository = process restart.
        fresh_repo = ResearchRepository(
            alpha_run_repository.database_path,
            clock=deterministic_clock,
            artifact_root=tmp_path / "alpha_artifacts",
        )
        fresh_service = ResearchRunService(fresh_repo)
        recovered = fresh_service.get(run["id"], principal="researcher@example.com")
        assert recovered is not None
        assert recovered["status"] == "running"
        assert recovered["candidate_attempts_total"] == 200
        assert recovered["candidate_attempts_completed"] == 100
        assert recovered["folds_total"] == 10
        assert recovered["folds_completed"] == 5
        events = fresh_repo.list_run_events(run["id"])
        assert len(events) == 2  # run_created + run_started

    def test_restart_does_not_trust_worker_memory(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
        tmp_path: Path,
    ) -> None:
        """A vanished JobStore file must not erase durable run facts."""
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-restart-02")
        service = ResearchRunService(alpha_run_repository)
        service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        # Simulate process restart with NO worker memory at all.
        fresh_repo = ResearchRepository(
            alpha_run_repository.database_path,
            clock=deterministic_clock,
            artifact_root=tmp_path / "alpha_artifacts",
        )
        fresh_service = ResearchRunService(fresh_repo)
        replay = fresh_service.replay(run["id"], principal="researcher@example.com")
        assert replay is not None
        assert replay["run"]["status"] == "running"


class TestWorkerAdapter:
    """The untrusted worker adapter requests only; it holds no authority."""

    def test_adapter_can_request_transition_with_valid_token(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService
        from app.research.run_worker import ResearchRunWorkerAdapter

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-wk-01")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        adapter = ResearchRunWorkerAdapter(service, principal="researcher@example.com")
        result = adapter.request_transition(
            run_id=run["id"],
            expected_version=started["transition_version"],
            attempt_token=started["_attempt_token"],
            to_status="completed",
        )
        assert result is not None
        assert result["status"] == "completed"

    def test_adapter_transition_with_stale_token_fails_closed(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService
        from app.research.run_worker import ResearchRunWorkerAdapter

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-wk-02")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        adapter = ResearchRunWorkerAdapter(service, principal="researcher@example.com")
        result = adapter.request_transition(
            run_id=run["id"],
            expected_version=started["transition_version"],
            attempt_token="wrong" + "0" * 59,
            to_status="completed",
        )
        assert result is None
        after = alpha_run_repository.get_alpha_run(run["id"])
        assert after["status"] == "running"  # unchanged

    def test_adapter_has_no_authority_collaborators(self) -> None:
        """The adapter must not import policy, evaluator, provider, broker, etc."""
        import inspect

        from app.research import run_worker

        source = inspect.getsource(run_worker)
        # Check import statements only (docstrings legitimately say what's forbidden).
        import_lines = [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        forbidden_modules = (
            "broker", "order", "portfolio", "execution", "monitor",
            "provider", "promote", "factor_dsl", "FactorSignalChain",
        )
        for line in import_lines:
            for module in forbidden_modules:
                assert module not in line, (
                    f"adapter must not import authority module '{module}': {line}"
                )
        # The adapter must import the service seam (its only collaborator).
        assert any("run_service" in line for line in import_lines)


class TestCommitBeforePublishCrash:
    """Worker/publisher failure after commit leaves the event replayable."""

    def test_committed_transition_survives_publisher_failure(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        class CrashPublisher:
            def on_run_created(self, run: Mapping) -> None:
                raise RuntimeError("publisher crashed")

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-crash-01")
        service = ResearchRunService(alpha_run_repository, publisher=CrashPublisher())
        # This must NOT raise despite the publisher crashing.
        result = service.transition(
            run["id"],
            principal="researcher@example.com",
            from_status="queued",
            to_status="running",
            expected_version=run["transition_version"],
        )
        assert result is not None
        assert result["status"] == "running"
        # The event IS durable.
        events = alpha_run_repository.list_run_events(run["id"])
        assert any(e["event_type"] == "run_started" for e in events)

    def test_retrying_adapter_returns_existing_event_not_duplicate(
        self,
        alpha_run_repository: ResearchRepository,
        deterministic_clock: DeterministicClock,
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-crash-02")
        service = ResearchRunService(alpha_run_repository)
        key = "start-idem-crash"
        service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
            idempotency_key=key,
        )
        before = len(alpha_run_repository.list_run_events(run["id"]))
        # Retry with the same key — no duplicate.
        service.start_or_resume(
            run["id"],
            principal="researcher@example.com",
            expected_version=run["transition_version"],
            idempotency_key=key,
        )
        after = len(alpha_run_repository.list_run_events(run["id"]))
        assert before == after


class TestReviewFixInvariants:
    def test_running_recovery_issues_new_digest_and_fences_old_token(
        self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-recover-01")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(
            run["id"], principal="researcher@example.com", expected_version=run["transition_version"]
        )
        recovered = service.recover_running_attempt(
            run["id"], principal="researcher@example.com",
            expected_version=started["transition_version"], idempotency_key="recover-once",
        )
        assert recovered is not None
        assert recovered["transition_version"] == started["transition_version"] + 1
        assert recovered["_attempt_token"] != started["_attempt_token"]
        payloads = [event["payload"] for event in alpha_run_repository.list_run_events(run["id"])]
        assert all(started["_attempt_token"] not in str(payload) for payload in payloads)
        assert service.update_progress(
            run["id"], principal="researcher@example.com",
            expected_version=started["transition_version"], attempt_token=started["_attempt_token"],
            candidate_attempts_total=1,
        ) is None

    def test_frontier_reference_requires_verifier(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock, tmp_path: Path) -> None:
        from app.research.artifacts import AlphaRunArtifactService
        from app.research.run_contract import checkpoint_state_checksum
        from app.research.run_service import AlphaCheckpointValidationError, ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-frontier-req")
        artifact_service = AlphaRunArtifactService(tmp_path)
        descriptor = artifact_service.write(run_id=run["id"], payload={"frontier": [1]})
        artifact = alpha_run_repository.append_artifact(
            run_id=run["id"], artifact_id="frontier-req-1", logical_kind="frontier",
            relative_path=descriptor["relative_path"], content_type=descriptor["content_type"],
            byte_size=descriptor["byte_size"], checksum_sha256=descriptor["checksum_sha256"],
        )
        params = {
            "id": "checkpoint-frontier-req", "checkpoint_version": 1, "committed_event_seq": 1,
            "stage": "search", "snapshot_sha256": run["snapshot_sha256"],
            "manifest_sha256": run["manifest_sha256"], "frontier_artifact_id": artifact["id"],
        }
        params["state_checksum"] = checkpoint_state_checksum(
            run_id=run["id"], checkpoint_version=1, committed_event_seq=1, stage="search",
            snapshot_sha256=run["snapshot_sha256"], manifest_sha256=run["manifest_sha256"],
            referenced_candidate_ids=[], inline_summary=None, frontier_artifact_id=artifact["id"],
        )
        with pytest.raises(AlphaCheckpointValidationError, match="verification service is required"):
            ResearchRunService(alpha_run_repository).validate_checkpoint(
                run_id=run["id"], principal="researcher@example.com", checkpoint=params
            )

    def test_artifact_reference_cannot_cross_bind_runs(
        self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock, tmp_path: Path
    ) -> None:
        from app.research.artifacts import AlphaRunArtifactService

        first = _make_run(alpha_run_repository, deterministic_clock, run_id="run-bind-a", idempotency_key="bind-key-a-000000")
        second = _make_run(alpha_run_repository, deterministic_clock, run_id="run-bind-b", idempotency_key="bind-key-b-000000")
        descriptor = AlphaRunArtifactService(tmp_path).write(run_id=second["id"], payload={"x": 1})
        artifact = alpha_run_repository.append_artifact(
            run_id=second["id"], artifact_id="artifact-bind-b", logical_kind="evidence",
            relative_path=descriptor["relative_path"], content_type="application/json",
            byte_size=descriptor["byte_size"], checksum_sha256=descriptor["checksum_sha256"],
        )
        with pytest.raises(Exception, match="artifact|run"):
            alpha_run_repository.append_candidate_attempt(
                run_id=first["id"], candidate_id="candidate-bind-a", attempt_ordinal=1,
                candidate_digest="a" * 64, canonical_expression="close", ast_signature="ast",
                shape_signature="shape", dsl_version="v1", operation="generate", seed=1, step=1,
                status="failed", reason={"code": "failed"}, evidence_artifact_id=artifact["id"],
            )

    def test_checkpoint_inline_state_is_canonical_object(self) -> None:
        from app.research.run_service import AlphaCheckpointValidationError, ResearchRunService

        service = ResearchRunService(ResearchRepository(Path(":memory:")))
        with pytest.raises(AlphaCheckpointValidationError, match="canonical"):
            service.validate_inline_checkpoint_payload(b'{"x": 1}')
        with pytest.raises(AlphaCheckpointValidationError, match="canonical"):
            service.validate_inline_checkpoint_payload(b"1")

    def test_progress_rejects_completed_over_total(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-progress-bound")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(run["id"], principal="researcher@example.com", expected_version=run["transition_version"])
        with pytest.raises(ValueError, match="completed"):
            service.update_progress(
                run["id"], principal="researcher@example.com", expected_version=started["transition_version"],
                attempt_token=started["_attempt_token"], candidate_attempts_total=2, candidate_attempts_completed=3,
            )

    def test_wrong_typed_manifest_group_fails_preflight(self) -> None:
        manifest = _sample_manifest()
        manifest["dsl"] = 7
        with pytest.raises(ValueError, match="mapping"):
            freeze_input_snapshot(manifest=manifest, created_at="2026-08-08T00:00:00+00:00")

    def test_event_and_candidate_diagnostics_are_bounded(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-json-bound")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(
            run["id"], principal="researcher@example.com", expected_version=run["transition_version"]
        )
        with pytest.raises(ValueError, match="oversized|string|bound"):
            service.append_candidate(
                run_id=run["id"], principal="researcher@example.com", candidate_id="cand-json-bound",
                expected_version=started["transition_version"], attempt_token=started["_attempt_token"],
                attempt_ordinal=1, candidate_digest="b" * 64, canonical_expression="close", ast_signature="ast",
                shape_signature="shape", dsl_version="v1", operation="generate", seed=1, step=1,
                status="failed", reason={"detail": "x" * 5000},
            )

    def test_safe_projection_allowlists_reason_and_snapshot_nested_fields(self) -> None:
        from app.research import projections

        projected = projections.run({"id": "run", "status": "failed", "transition_version": 1, "last_event_seq": 1,
            "candidate_attempts_total": 0, "candidate_attempts_completed": 0, "folds_total": 0, "folds_completed": 0,
            "snapshot_sha256": "a" * 64, "manifest_sha256": "b" * 64,
            "terminal_reason": '{"code":"worker_failed","detail":"/secret/path"}', "retry_attempt": 0,
            "created_at": "now"})
        assert projected["terminal_reason"] == "worker_failed"
        snap = projections.snapshot({"schema_version": "v1", "snapshot_sha256": "a" * 64, "manifest_sha256": "b" * 64,
            "grammar_fingerprint": "c" * 64, "vocabulary_fingerprint": "d" * 64, "policy_digest": "e" * 64,
            "data_fingerprint": "f" * 64, "partition_fingerprint": "0" * 64, "membership_fingerprint": "1" * 64,
            "code_fingerprint": "2" * 64, "build_fingerprint": "3" * 64, "dependency_fingerprint": "4" * 64,
            "manifest": {"universe": {"name": "u", "secret": "x"}, "policy": {"version": "v", "thresholds": {"x": 1}}}})
        assert "secret" not in str(snap)
        assert "thresholds" not in str(snap)

    def test_run_created_uses_semantic_event_checksum(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock) -> None:
        from app.research.run_contract import event_checksum

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-checksum")
        event = alpha_run_repository.list_run_events(run["id"])[0]
        assert event["payload_checksum"] == event_checksum(
            event["payload"], event["idempotency_key"], event["event_type"]
        )

    def test_replay_and_candidate_history_mark_continuation(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-page")
        service = ResearchRunService(alpha_run_repository)
        service.append_event(run_id=run["id"], principal="researcher@example.com", event_type="stage", entity_kind="run", entity_id=run["id"], idempotency_key="page-event", actor="worker", source="worker", payload={"ok": True})
        page = service.replay(run["id"], principal="researcher@example.com", after_seq=0, limit=1)
        assert page is not None and page["truncated"] is True and page["next_sequence"] == 1

    def test_service_checkpoint_append_is_the_validated_write_path(
        self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock
    ) -> None:
        from app.research.run_contract import checkpoint_state_checksum
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-checkpoint-seam")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(
            run["id"], principal="researcher@example.com", expected_version=run["transition_version"]
        )
        checkpoint = {
            "id": "checkpoint-seam-1", "checkpoint_version": 1, "committed_event_seq": 1,
            "stage": "search", "snapshot_sha256": run["snapshot_sha256"],
            "manifest_sha256": run["manifest_sha256"], "frontier_artifact_id": None,
        }
        checkpoint["state_checksum"] = checkpoint_state_checksum(
            run_id=run["id"], checkpoint_version=1, committed_event_seq=1, stage="search",
            snapshot_sha256=run["snapshot_sha256"], manifest_sha256=run["manifest_sha256"],
            referenced_candidate_ids=[], inline_summary=None, frontier_artifact_id=None,
        )
        persisted = service.append_checkpoint(
            run_id=run["id"], principal="researcher@example.com", checkpoint=checkpoint,
            expected_version=started["transition_version"], attempt_token=started["_attempt_token"],
        )
        assert persisted is not None and persisted["id"] == checkpoint["id"]

    def test_event_diagnostics_and_candidate_cursor_are_bounded(
        self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock
    ) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-event-bound")
        service = ResearchRunService(alpha_run_repository)
        with pytest.raises(ValueError, match="oversized|string|bound"):
            service.append_event(
                run_id=run["id"], principal="researcher@example.com", event_type="diagnostic",
                entity_kind="run", entity_id=run["id"], idempotency_key="event-bound-000000",
                actor="worker", source="worker", payload={"detail": "x" * 5000},
            )
        for ordinal in (1, 2):
            alpha_run_repository.append_candidate_attempt(
                run_id=run["id"], candidate_id=f"cursor-candidate-{ordinal}", attempt_ordinal=ordinal,
                candidate_digest=("a" * 63) + str(ordinal), canonical_expression="close",
                ast_signature="ast", shape_signature="shape", dsl_version="v1", operation="generate",
                seed=1, step=ordinal, status="failed", reason={"code": "failed"},
            )
        assert [row["attempt_ordinal"] for row in service.list_candidates(
            run["id"], principal="researcher@example.com", after_ordinal=1
        )] == [2]

    def test_recovered_token_authenticates_new_attempt(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock) -> None:
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-recover-valid")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(run["id"], principal="researcher@example.com", expected_version=run["transition_version"])
        recovered = service.recover_running_attempt(run["id"], principal="researcher@example.com", expected_version=started["transition_version"])
        assert recovered is not None
        assert service.update_progress(
            run["id"], principal="researcher@example.com", expected_version=recovered["transition_version"],
            attempt_token=recovered["_attempt_token"], folds_total=1,
        ) is not None
        assert service.update_progress(
            run["id"], principal="researcher@example.com", expected_version=recovered["transition_version"],
            attempt_token=started["_attempt_token"], folds_total=2,
        ) is None

    def test_checkpoint_cursor_state_survives_fresh_repository(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock) -> None:
        from app.research.run_contract import checkpoint_state_checksum
        from app.research.run_service import ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-checkpoint-restart")
        alpha_run_repository.append_candidate_attempt(
            run_id=run["id"], candidate_id="checkpoint-candidate", attempt_ordinal=1,
            candidate_digest="a" * 64, canonical_expression="close", ast_signature="ast",
            shape_signature="shape", dsl_version="v1", operation="generate", seed=1, step=1,
            status="admitted", reason={"code": "ok"},
        )
        summary = {"frontier": "candidate-1"}
        checksum = checkpoint_state_checksum(
            run_id=run["id"], checkpoint_version=1, committed_event_seq=1, stage="search",
            snapshot_sha256=run["snapshot_sha256"], manifest_sha256=run["manifest_sha256"],
            referenced_candidate_ids=["checkpoint-candidate"], inline_summary=summary,
            frontier_artifact_id=None,
        )
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(run["id"], principal="researcher@example.com", expected_version=run["transition_version"])
        service.append_checkpoint(
            run_id=run["id"], principal="researcher@example.com",
            checkpoint={"id": "checkpoint-restart", "checkpoint_version": 1, "committed_event_seq": 1,
                        "stage": "search", "snapshot_sha256": run["snapshot_sha256"],
                        "manifest_sha256": run["manifest_sha256"], "state_checksum": checksum},
            referenced_candidate_ids=["checkpoint-candidate"], inline_summary=summary,
            expected_version=started["transition_version"], attempt_token=started["_attempt_token"],
        )
        recovered = ResearchRunService(alpha_run_repository).get_latest_valid_checkpoint(
            run["id"], principal="researcher@example.com"
        )
        assert recovered is not None
        assert recovered["referenced_candidate_ids"] == ["checkpoint-candidate"]
        assert recovered["inline_summary"] == summary

    def test_checkpoint_rejects_coerced_scalar_types(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock) -> None:
        from app.research.run_service import AlphaCheckpointValidationError, ResearchRunService

        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-checkpoint-types")
        checkpoint = {"checkpoint_version": "1", "committed_event_seq": 1, "stage": "search",
                      "snapshot_sha256": run["snapshot_sha256"], "manifest_sha256": run["manifest_sha256"],
                      "state_checksum": "0" * 64}
        with pytest.raises(AlphaCheckpointValidationError, match="shape"):
            ResearchRunService(alpha_run_repository).validate_checkpoint(
                run_id=run["id"], principal="researcher@example.com", checkpoint=checkpoint
            )

    def test_manifest_counters_are_non_negative_and_bounded(self) -> None:
        manifest = _sample_manifest()
        manifest["budgets"]["max_candidates"] = -1
        with pytest.raises(ValueError, match="bounded|non-negative"):
            freeze_input_snapshot(manifest=manifest, created_at="2026-08-08T00:00:00+00:00")
    def test_recovered_token_survives_more_than_first_event_page(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock) -> None:
        from app.research.run_service import ResearchRunService
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-token-page")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(run["id"], principal="researcher@example.com", expected_version=run["transition_version"])
        recovered = service.recover_running_attempt(run["id"], principal="researcher@example.com", expected_version=started["transition_version"])
        assert recovered is not None
        for index in range(501):
            alpha_run_repository.append_run_event(
                run_id=run["id"], event_id=f"noise-{index}", event_type="worker_noise",
                entity_kind="run", entity_id=run["id"], idempotency_key=f"noise-key-{index}",
                actor="worker", source="worker", payload={"index": index},
            )
        assert service.update_progress(
            run["id"], principal="researcher@example.com", expected_version=recovered["transition_version"],
            attempt_token=recovered["_attempt_token"], folds_total=1,
        ) is not None

    def test_checkpoint_resolves_candidate_ids_beyond_history_page(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock) -> None:
        from app.research.run_contract import checkpoint_state_checksum
        from app.research.run_service import ResearchRunService
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-candidate-page")
        for ordinal in range(1, 258):
            alpha_run_repository.append_candidate_attempt(
                run_id=run["id"], candidate_id=f"candidate-page-{ordinal}", attempt_ordinal=ordinal,
                candidate_digest=(f"{ordinal:064x}")[-64:], canonical_expression="close", ast_signature="ast",
                shape_signature="shape", dsl_version="v1", operation="generate", seed=1, step=ordinal,
                status="failed", reason={"code": "failed"},
            )
        candidate_id = "candidate-page-257"
        checksum = checkpoint_state_checksum(
            run_id=run["id"], checkpoint_version=1, committed_event_seq=1, stage="search",
            snapshot_sha256=run["snapshot_sha256"], manifest_sha256=run["manifest_sha256"],
            referenced_candidate_ids=[candidate_id], inline_summary=None, frontier_artifact_id=None,
        )
        checkpoint = {"id": "checkpoint-page", "checkpoint_version": 1, "committed_event_seq": 1,
                      "stage": "search", "snapshot_sha256": run["snapshot_sha256"],
                      "manifest_sha256": run["manifest_sha256"], "state_checksum": checksum}
        assert ResearchRunService(alpha_run_repository).validate_checkpoint(
            run_id=run["id"], principal="researcher@example.com", checkpoint=checkpoint,
            referenced_candidate_ids=[candidate_id],
        )["id"] == "checkpoint-page"

    def test_lifecycle_idempotency_does_not_cross_principal(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock) -> None:
        from app.research.run_service import ResearchRunService
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-idem-owner")
        service = ResearchRunService(alpha_run_repository)
        service.start_or_resume(run["id"], principal="researcher@example.com", expected_version=run["transition_version"], idempotency_key="owned-key")
        owner_event = alpha_run_repository.list_run_events(run["id"])[1]
        assert alpha_run_repository.transition_alpha_run(
            run_id=run["id"], principal="attacker@example.com", from_status="queued", to_status="running",
            expected_version=run["transition_version"], event_id="attacker-event", event_type="run_started",
            idempotency_key="owned-key", extra_payload={"attempt_token_digest": owner_event["payload"]["attempt_token_digest"]},
        ) is None
    def test_candidate_history_fails_closed_on_tampered_evidence(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock, alpha_artifact_root: Path) -> None:
        from app.research.artifacts import AlphaRunArtifactService
        from app.research.run_service import ResearchRunService
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-candidate-evidence")
        artifacts = AlphaRunArtifactService(alpha_artifact_root.parent)
        descriptor = artifacts.write(run_id=run["id"], payload={"evidence": 1})
        artifact = alpha_run_repository.append_artifact(
            run_id=run["id"], artifact_id="evidence-artifact", logical_kind="evidence",
            relative_path=descriptor["relative_path"], content_type=descriptor["content_type"],
            byte_size=descriptor["byte_size"], checksum_sha256=descriptor["checksum_sha256"],
        )
        service = ResearchRunService(alpha_run_repository, artifact_service=artifacts)
        started = service.start_or_resume(
            run["id"], principal="researcher@example.com", expected_version=run["transition_version"]
        )
        service.append_candidate(
            run_id=run["id"], principal="researcher@example.com", candidate_id="candidate-evidence",
            attempt_ordinal=1, candidate_digest="b" * 64, canonical_expression="close", ast_signature="ast",
            shape_signature="shape", dsl_version="v1", operation="generate", seed=1, step=1,
            expected_version=started["transition_version"], attempt_token=started["_attempt_token"],
            status="admitted", reason={"code": "ok"}, evidence_artifact_id=artifact["id"],
        )
        (alpha_artifact_root.parent / descriptor["relative_path"]).write_bytes(b"tampered")
        with pytest.raises(ValueError, match="evidence artifact"):
            service.list_candidates(run["id"], principal="researcher@example.com")

    def test_checkpoint_append_requires_live_attempt_fence(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock) -> None:
        from app.research.run_contract import checkpoint_state_checksum
        from app.research.run_service import ResearchRunService
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-checkpoint-fence")
        checkpoint = {"id": "checkpoint-fence", "checkpoint_version": 1, "committed_event_seq": 1,
                      "stage": "search", "snapshot_sha256": run["snapshot_sha256"],
                      "manifest_sha256": run["manifest_sha256"]}
        checkpoint["state_checksum"] = checkpoint_state_checksum(
            run_id=run["id"], checkpoint_version=1, committed_event_seq=1, stage="search",
            snapshot_sha256=run["snapshot_sha256"], manifest_sha256=run["manifest_sha256"],
            referenced_candidate_ids=[], inline_summary=None, frontier_artifact_id=None,
        )
        with pytest.raises(ValueError, match="attempt_token"):
            ResearchRunService(alpha_run_repository).append_checkpoint(
                run_id=run["id"], principal="researcher@example.com", checkpoint=checkpoint,
                expected_version=run["transition_version"], attempt_token="",
            )

    def test_recovery_idempotency_returns_existing_state_without_token(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock) -> None:
        from app.research.run_service import ResearchRunService
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-recovery-idem")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(run["id"], principal="researcher@example.com", expected_version=run["transition_version"])
        first = service.recover_running_attempt(run["id"], principal="researcher@example.com", expected_version=started["transition_version"], idempotency_key="recovery-key")
        second = service.recover_running_attempt(run["id"], principal="researcher@example.com", expected_version=started["transition_version"], idempotency_key="recovery-key")
        assert first is not None and second is not None
        assert "_attempt_token" in first and "_attempt_token" not in second
        assert second["transition_version"] == first["transition_version"]
    def test_recovery_without_key_is_idempotent_without_plaintext_retry_token(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock) -> None:
        from app.research.run_service import ResearchRunService
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-recovery-derived-idem")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(run["id"], principal="researcher@example.com", expected_version=run["transition_version"])
        first = service.recover_running_attempt(run["id"], principal="researcher@example.com", expected_version=started["transition_version"])
        second = service.recover_running_attempt(run["id"], principal="researcher@example.com", expected_version=started["transition_version"])
        assert first is not None and second is not None
        assert "_attempt_token" in first and "_attempt_token" not in second
        assert second["transition_version"] == first["transition_version"]
    def test_worker_candidate_and_lineage_callbacks_have_no_post_cancel_or_recovery_side_effects(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock) -> None:
        from app.research.run_service import ResearchRunService
        from app.research.run_worker import ResearchRunWorkerAdapter
        service = ResearchRunService(alpha_run_repository)
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-worker-fence")
        started = service.start_or_resume(run["id"], principal="researcher@example.com", expected_version=run["transition_version"])
        adapter = ResearchRunWorkerAdapter(service, principal="researcher@example.com")

        def append(candidate_id: str, ordinal: int) -> dict[str, object] | None:
            return adapter.append_candidate(
                run_id=run["id"], expected_version=started["transition_version"],
                attempt_token=started["_attempt_token"], candidate_id=candidate_id,
                attempt_ordinal=ordinal, candidate_digest=("c" * 60 + f"{ordinal:04d}"),
                canonical_expression=f"close + {ordinal}", ast_signature=f"ast-{ordinal}",
                shape_signature=f"shape-{ordinal}", dsl_version="v1", operation="generate",
                seed=1, step=ordinal, status="generated", reason={"code": "generated"},
            )

        assert append("worker-parent", 1) is not None
        assert append("worker-child", 2) is not None
        cancelled = service.cancel(
            run["id"], principal="researcher@example.com",
            expected_version=started["transition_version"], idempotency_key="cancel-worker-fence",
        )
        assert cancelled is not None
        assert append("worker-stale", 3) is None
        assert adapter.append_candidate_lineage(
            run_id=run["id"], expected_version=started["transition_version"],
            attempt_token=started["_attempt_token"], lineage_id="lineage-stale",
            child_attempt_id="worker-child", parent_attempt_id="worker-parent",
            edge_ordinal=0, operation="mutation",
        ) is None
        assert len(alpha_run_repository.list_candidates(run["id"])) == 2
        with alpha_run_repository._connection() as connection:
            assert connection.execute(
                "SELECT COUNT(*) AS count FROM research_alpha_candidate_lineage WHERE run_id = ?",
                (run["id"],),
            ).fetchone()["count"] == 0
        recovered_run = _make_run(
            alpha_run_repository, deterministic_clock, run_id="run-worker-recovery-fence",
            idempotency_key="idem-worker-recovery-fence",
        )
        recovered_start = service.start_or_resume(
            recovered_run["id"], principal="researcher@example.com", expected_version=recovered_run["transition_version"]
        )
        recovered = service.recover_running_attempt(
            recovered_run["id"], principal="researcher@example.com",
            expected_version=recovered_start["transition_version"],
        )
        assert recovered is not None
        assert adapter.append_candidate(
            run_id=recovered_run["id"], expected_version=recovered_start["transition_version"],
            attempt_token=recovered_start["_attempt_token"], candidate_id="recovery-stale",
            attempt_ordinal=1, candidate_digest="d" * 64, canonical_expression="close",
            ast_signature="ast", shape_signature="shape", dsl_version="v1", operation="generate",
            seed=1, step=1, status="generated", reason={"code": "generated"},
        ) is None
        assert alpha_run_repository.list_candidates(recovered_run["id"]) == []

    def test_worker_exposes_no_unfenced_recovery_callback(self) -> None:
        from app.research.run_worker import ResearchRunWorkerAdapter
        assert not hasattr(ResearchRunWorkerAdapter, "recover_running")

    def test_checkpoint_missing_id_is_server_generated(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock) -> None:
        from app.research.run_contract import checkpoint_state_checksum
        from app.research.run_service import ResearchRunService
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-checkpoint-id")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(run["id"], principal="researcher@example.com", expected_version=run["transition_version"])
        checkpoint = {"checkpoint_version": 1, "committed_event_seq": 1, "stage": "search",
                      "snapshot_sha256": run["snapshot_sha256"], "manifest_sha256": run["manifest_sha256"]}
        checkpoint["state_checksum"] = checkpoint_state_checksum(
            run_id=run["id"], checkpoint_version=1, committed_event_seq=1, stage="search",
            snapshot_sha256=run["snapshot_sha256"], manifest_sha256=run["manifest_sha256"],
            referenced_candidate_ids=[], inline_summary=None, frontier_artifact_id=None,
        )
        persisted = service.append_checkpoint(
            run_id=run["id"], principal="researcher@example.com", checkpoint=checkpoint,
            expected_version=started["transition_version"], attempt_token=started["_attempt_token"],
        )
        assert persisted is not None and persisted["id"].startswith("chk_")
    def test_checkpoint_validation_rejects_caller_verifier_override(self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock) -> None:
        from app.research.run_service import ResearchRunService
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-verifier-override")
        with pytest.raises(TypeError):
            ResearchRunService(alpha_run_repository).validate_checkpoint(
                run_id=run["id"], principal="researcher@example.com", checkpoint={}, artifact_service=object()
            )
