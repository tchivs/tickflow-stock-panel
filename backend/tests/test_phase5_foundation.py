"""Focused contracts for the shared Phase 05 foundation."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.operational.migrations import MIGRATIONS, migrate_operational_db


PHASE5_TABLES = {
    "shadow_import_batches",
    "shadow_trade_facts",
    "shadow_evidence_sets",
    "shadow_evidence_batches",
    "shadow_evidence_members",
    "shadow_evidence_exclusions",
    "shadow_candidates",
    "shadow_candidate_runs",
    "shadow_candidate_evaluations",
    "shadow_retention_events",
    "theses",
    "thesis_versions",
    "thesis_valuation_anchors",
    "thesis_conditions",
    "thesis_condition_schedules",
    "thesis_condition_checks",
    "thesis_pending_conclusions",
    "thesis_review_events",
    "forecast_jobs",
    "forecast_global_leases",
    "forecast_records",
    "forecast_outcomes",
    "forecast_calibration_facts",
}

IMMUTABLE_PHASE5_TABLES = PHASE5_TABLES - {
    "thesis_condition_schedules",
    "forecast_jobs",
    "forecast_global_leases",
}


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _phase4_database(path: Path) -> sqlite3.Connection:
    connection = _connect(path)
    for version, migration in enumerate(MIGRATIONS[:-1], start=1):
        connection.executescript(migration)
        connection.execute(f"PRAGMA user_version = {version}")
    connection.execute(
        "INSERT INTO advanced_policy_revisions "
        "(id, revision, fingerprint, fact_schema_version, snapshot_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            "preserved-policy",
            "phase-4",
            "a" * 64,
            "advanced_policy_snapshot_v1",
            "{}",
            "2026-07-15T00:00:00Z",
        ),
    )
    connection.commit()
    return connection


def _phase5_table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
        if row[0] in PHASE5_TABLES
    }


def _insert_thesis_graph(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO theses (id, instrument, created_by, created_at) VALUES (?, ?, ?, ?)",
        ("thesis-1", "600519.SH", "principal-1", "2026-07-16T00:00:00Z"),
    )
    connection.execute(
        """INSERT INTO thesis_versions
           (id, thesis_id, version, predecessor_id, core_judgment, rationale,
            change_reason, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "version-1",
            "thesis-1",
            1,
            None,
            "Pricing power remains durable.",
            "Governed filing evidence.",
            "Initial thesis record",
            "principal-1",
            "2026-07-16T00:00:00Z",
        ),
    )
    connection.execute(
        """INSERT INTO thesis_conditions
           (id, version_id, copied_from_condition_id, source_kind, field, operator,
            threshold_json, unit, lookback_days, cadence, timezone, description, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "condition-1",
            "version-1",
            None,
            "financial",
            "revenue_growth_yoy",
            "lt",
            "0.0",
            "ratio",
            120,
            "quarterly",
            "Asia/Shanghai",
            "Revenue growth turns negative.",
            "2026-07-16T00:00:00Z",
        ),
    )
    connection.execute(
        """INSERT INTO thesis_condition_schedules
           (condition_id, active, next_due_at, lease_owner, lease_until,
            last_attempt_at, transition_version, created_at, updated_at)
           VALUES (?, 1, ?, NULL, NULL, NULL, 0, ?, ?)""",
        (
            "condition-1",
            "2026-07-17T00:00:00Z",
            "2026-07-16T00:00:00Z",
            "2026-07-16T00:00:00Z",
        ),
    )


def _insert_forecast_job(connection: sqlite3.Connection) -> None:
    connection.execute(
        """INSERT INTO forecast_jobs
           (id, principal, instrument_id, horizon, catalog_id, idempotency_key,
            input_fingerprint, status, transition_version, retry_of_job_id, attempt,
            lease_owner, lease_until, terminal_reason, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', 0, NULL, 1, NULL, NULL, NULL, ?, ?)""",
        (
            "job-1",
            "principal-1",
            "instrument-600000",
            20,
            "kronos-mini",
            "request-key-1",
            "b" * 64,
            "2026-07-16T00:00:00Z",
            "2026-07-16T00:00:00Z",
        ),
    )


def test_migration_upgrades_phase4_and_fresh_databases_without_losing_rows(tmp_path: Path) -> None:
    upgraded = _phase4_database(tmp_path / "upgraded.db")
    fresh = _connect(tmp_path / "fresh.db")

    migrate_operational_db(upgraded)
    migrate_operational_db(fresh)

    expected_version = len(MIGRATIONS)
    assert upgraded.execute("PRAGMA user_version").fetchone()[0] == expected_version
    assert fresh.execute("PRAGMA user_version").fetchone()[0] == expected_version
    assert _phase5_table_names(upgraded) == PHASE5_TABLES
    assert _phase5_table_names(fresh) == PHASE5_TABLES
    assert upgraded.execute(
        "SELECT revision FROM advanced_policy_revisions WHERE id = 'preserved-policy'"
    ).fetchone() == ("phase-4",)

    migrate_operational_db(upgraded)
    assert upgraded.execute("PRAGMA user_version").fetchone()[0] == expected_version
    assert _phase5_table_names(upgraded) == PHASE5_TABLES


def test_migration_installs_update_and_delete_guards_for_every_fact(tmp_path: Path) -> None:
    connection = _connect(tmp_path / "operational.db")
    migrate_operational_db(connection)
    trigger_names = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        )
    }

    for table in IMMUTABLE_PHASE5_TABLES:
        assert f"{table}_no_update" in trigger_names
        assert f"{table}_no_delete" in trigger_names


def test_migration_restricts_orphans_and_direct_fact_mutation(tmp_path: Path) -> None:
    connection = _connect(tmp_path / "operational.db")
    migrate_operational_db(connection)

    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """INSERT INTO shadow_trade_facts
               (id, batch_id, row_identity, duplicate_group_hash, broker_fill_id,
                account_alias, symbol, side, executed_at, quantity, price, fees,
                currency, source_row_ordinal, source_values_json,
                normalized_payload_json, created_at)
               VALUES (?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "trade-orphan",
                "missing-batch",
                "row-1",
                "c" * 64,
                "opaque-account",
                "600000.SH",
                "buy",
                "2026-07-16T01:00:00Z",
                10.0,
                12.5,
                0.2,
                "CNY",
                1,
                "{}",
                "{}",
                "2026-07-16T01:00:00Z",
            ),
        )

    _insert_thesis_graph(connection)
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        connection.execute(
            "UPDATE thesis_versions SET core_judgment = ? WHERE id = ?",
            ("tampered", "version-1"),
        )
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        connection.execute("DELETE FROM thesis_conditions WHERE id = ?", ("condition-1",))


def test_migration_allows_only_monotonic_schedule_cursor_updates(tmp_path: Path) -> None:
    connection = _connect(tmp_path / "operational.db")
    migrate_operational_db(connection)
    _insert_thesis_graph(connection)

    connection.execute(
        """UPDATE thesis_condition_schedules
           SET lease_owner = ?, lease_until = ?, transition_version = 1, updated_at = ?
           WHERE condition_id = ?""",
        (
            "scanner-1",
            "2026-07-17T00:01:00Z",
            "2026-07-16T00:01:00Z",
            "condition-1",
        ),
    )
    connection.execute(
        """UPDATE thesis_condition_schedules
           SET next_due_at = ?, lease_owner = NULL, lease_until = NULL,
               last_attempt_at = ?, transition_version = 2, updated_at = ?
           WHERE condition_id = ?""",
        (
            "2026-10-17T00:00:00Z",
            "2026-07-17T00:00:30Z",
            "2026-07-17T00:00:30Z",
            "condition-1",
        ),
    )

    with pytest.raises(sqlite3.DatabaseError, match="monotonic|cursor"):
        connection.execute(
            """UPDATE thesis_condition_schedules
               SET next_due_at = ?, transition_version = 3, updated_at = ?
               WHERE condition_id = ?""",
            (
                "2026-01-01T00:00:00Z",
                "2026-07-17T00:01:00Z",
                "condition-1",
            ),
        )
    with pytest.raises(sqlite3.DatabaseError, match="monotonic|cursor"):
        connection.execute(
            """UPDATE thesis_condition_schedules
               SET active = 1, transition_version = 7, updated_at = ?
               WHERE condition_id = ?""",
            ("2026-07-17T00:01:00Z", "condition-1"),
        )


def test_migration_enforces_forecast_job_state_machine_and_column_guard(tmp_path: Path) -> None:
    connection = _connect(tmp_path / "operational.db")
    migrate_operational_db(connection)
    _insert_forecast_job(connection)

    with pytest.raises(sqlite3.DatabaseError, match="transition"):
        connection.execute(
            """UPDATE forecast_jobs
               SET status = 'completed', transition_version = 1, updated_at = ?
               WHERE id = 'job-1'""",
            ("2026-07-16T00:01:00Z",),
        )
    with pytest.raises(sqlite3.DatabaseError, match="immutable|cursor"):
        connection.execute(
            """UPDATE forecast_jobs
               SET horizon = 5, status = 'running', transition_version = 1,
                   lease_owner = 'worker-1', lease_until = ?, updated_at = ?
               WHERE id = 'job-1'""",
            ("2026-07-16T00:02:00Z", "2026-07-16T00:01:00Z"),
        )

    connection.execute(
        """UPDATE forecast_jobs
           SET status = 'running', transition_version = 1,
               lease_owner = 'worker-1', lease_until = ?, updated_at = ?
           WHERE id = 'job-1'""",
        ("2026-07-16T00:02:00Z", "2026-07-16T00:01:00Z"),
    )
    connection.execute(
        """UPDATE forecast_jobs
           SET status = 'completed', transition_version = 2,
               lease_owner = NULL, lease_until = NULL, updated_at = ?
           WHERE id = 'job-1'""",
        ("2026-07-16T00:02:00Z",),
    )
    with pytest.raises(sqlite3.DatabaseError, match="transition|immutable"):
        connection.execute(
            """UPDATE forecast_jobs
               SET status = 'running', transition_version = 3, updated_at = ?
               WHERE id = 'job-1'""",
            ("2026-07-16T00:03:00Z",),
        )
    with pytest.raises(sqlite3.DatabaseError, match="immutable"):
        connection.execute("DELETE FROM forecast_jobs WHERE id = 'job-1'")


def test_artifact_bytes_are_atomic_root_contained_and_descriptor_verified(
    tmp_path: Path,
) -> None:
    import stat
    from app.optional_artifacts import ManagedImmutableArtifactStore

    store = ManagedImmutableArtifactStore(tmp_path / "managed")
    descriptor = store.create_bytes(
        b"immutable phase 05 payload",
        schema_version="phase5-test-v1",
        scope={"instrument_id": "instrument-600000", "horizon": 20},
        content_type="application/octet-stream",
    )

    assert not Path(descriptor.relative_path).is_absolute()
    assert str(tmp_path) not in repr(descriptor)
    assert descriptor == store.descriptor(descriptor.artifact_id)
    assert store.load_bytes(descriptor) == b"immutable phase 05 payload"
    assert (store.root / descriptor.relative_path).resolve().is_relative_to(store.root)
    payload_path = store.root / descriptor.relative_path
    assert stat.S_IMODE(store.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(payload_path.stat().st_mode) == 0o600
    assert stat.S_IMODE((payload_path.parent / "metadata.json").stat().st_mode) == 0o600
    assert not list(store.root.glob(".*.tmp"))


def test_artifact_collision_escape_partial_and_tamper_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    from app import optional_artifacts
    from app.optional_artifacts import ManagedArtifactError, ManagedImmutableArtifactStore

    class FixedId:
        hex = "1" * 32

    monkeypatch.setattr(optional_artifacts, "uuid4", lambda: FixedId())
    store = ManagedImmutableArtifactStore(tmp_path / "managed")
    descriptor = store.create_bytes(
        b"canonical",
        schema_version="phase5-test-v1",
        scope={"kind": "shadow"},
        content_type="application/octet-stream",
    )
    with pytest.raises(ManagedArtifactError, match="exists|collision"):
        store.create_bytes(
            b"replacement",
            schema_version="phase5-test-v1",
            scope={"kind": "shadow"},
            content_type="application/octet-stream",
        )
    assert store.load_bytes(descriptor) == b"canonical"

    with pytest.raises(ManagedArtifactError, match="identifier|managed|descriptor"):
        store.descriptor("../escape")
    with pytest.raises(ManagedArtifactError, match="managed|descriptor|path"):
        store.load_bytes(replace(descriptor, relative_path="../outside.bin"))

    payload_path = store.root / descriptor.relative_path
    payload_path.write_bytes(b"tampered")
    with pytest.raises(ManagedArtifactError, match="checksum|size|tamper"):
        store.load_bytes(descriptor)

    partial_id = "2" * 32
    partial = store.root / partial_id
    partial.mkdir()
    (partial / "payload.bin").write_bytes(b"partial")
    with pytest.raises(ManagedArtifactError, match="metadata|incomplete"):
        store.descriptor(partial_id)


def test_artifact_metadata_scope_and_parquet_payload_are_verified(tmp_path: Path) -> None:
    import json

    import polars as pl

    from app.optional_artifacts import ManagedArtifactError, ManagedImmutableArtifactStore

    store = ManagedImmutableArtifactStore(tmp_path / "managed")
    frame = pl.DataFrame({"session_id": ["S1", "S2"], "close": [10.0, 11.0]})
    descriptor = store.create_parquet(
        frame,
        schema_version="governed-panel-v1",
        scope={"instrument_id": "instrument-600000", "sessions": ["S1", "S2"]},
    )
    assert store.load_parquet(descriptor).equals(frame)

    namespace = (store.root / descriptor.relative_path).parent
    metadata_path = namespace / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["scope"] = {"instrument_id": "foreign"}
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ManagedArtifactError, match="metadata|scope|checksum"):
        store.descriptor(descriptor.artifact_id)


def test_polars_error_cleanup_translates_with_cause_and_preserves_final_assets(
    tmp_path: Path,
) -> None:
    import polars as pl

    from app.optional_artifacts import ManagedArtifactError, ManagedImmutableArtifactStore

    store = ManagedImmutableArtifactStore(tmp_path / "managed")
    shared = store.create_bytes(
        b"shared-immutable",
        schema_version="phase5-test-v1",
        scope={"kind": "shared"},
        content_type="application/octet-stream",
    )

    class FailingFrame:
        @staticmethod
        def write_parquet(path: Path) -> None:
            path.write_bytes(b"partial-sensitive-parquet")
            raise pl.exceptions.ComputeError("injected parquet compute failure")

    with pytest.raises(ManagedArtifactError, match="Parquet") as caught:
        store.create_parquet(
            FailingFrame(),
            schema_version="governed-panel-v1",
            scope={"instrument_id": "instrument-600000"},
        )

    assert isinstance(caught.value.__cause__, pl.exceptions.PolarsError)
    assert list(store.root.glob(".*.tmp")) == []
    assert store.load_bytes(shared) == b"shared-immutable"



def test_polars_error_cleanup_translates_read_failure_without_deleting_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import polars as pl

    from app.optional_artifacts import ManagedArtifactError, ManagedImmutableArtifactStore

    store = ManagedImmutableArtifactStore(tmp_path / "managed")
    descriptor = store.create_parquet(
        pl.DataFrame({"session_id": ["S1"], "close": [10.0]}),
        schema_version="governed-panel-v1",
        scope={"instrument_id": "instrument-600000"},
    )
    payload_path = store.root / descriptor.relative_path
    final_bytes = payload_path.read_bytes()

    def fail_read(_path: Path):
        raise pl.exceptions.ComputeError("injected parquet read failure")

    monkeypatch.setattr(pl, "read_parquet", fail_read)
    with pytest.raises(ManagedArtifactError, match="decoded") as caught:
        store.load_parquet(descriptor)

    assert isinstance(caught.value.__cause__, pl.exceptions.PolarsError)
    assert payload_path.read_bytes() == final_bytes
    assert list(store.root.glob(".*.tmp")) == []


def test_managed_artifact_temp_finally_cleans_metadata_failure_without_touching_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.optional_artifacts import ManagedArtifactError, ManagedImmutableArtifactStore

    store = ManagedImmutableArtifactStore(tmp_path / "managed")
    final = store.create_bytes(
        b"committed-final",
        schema_version="phase5-test-v1",
        scope={"kind": "shared"},
        content_type="application/octet-stream",
    )
    original_write = store._write_exclusive

    def fail_metadata(path: Path, payload: bytes) -> None:
        if path.name == "metadata.json":
            raise OSError("injected metadata failure")
        original_write(path, payload)

    monkeypatch.setattr(store, "_write_exclusive", fail_metadata)
    with pytest.raises(ManagedArtifactError, match="atomically create"):
        store.create_bytes(
            b"invocation-owned",
            schema_version="phase5-test-v1",
            scope={"kind": "failed"},
            content_type="application/octet-stream",
        )

    assert list(store.root.glob(".*.tmp")) == []
    assert store.load_bytes(final) == b"committed-final"


def test_managed_artifact_temp_finally_surfaces_attributable_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import optional_artifacts
    from app.optional_artifacts import (
        ManagedArtifactCleanupError,
        ManagedArtifactError,
        ManagedImmutableArtifactStore,
    )

    store = ManagedImmutableArtifactStore(tmp_path / "managed")
    final = store.create_bytes(
        b"committed-final",
        schema_version="phase5-test-v1",
        scope={"kind": "shared"},
        content_type="application/octet-stream",
    )
    original_write = store._write_exclusive

    def fail_metadata(path: Path, payload: bytes) -> None:
        if path.name == "metadata.json":
            raise ManagedArtifactError("injected writer failure")
        original_write(path, payload)

    def fail_cleanup(_path: Path) -> None:
        raise OSError("injected cleanup failure")

    monkeypatch.setattr(store, "_write_exclusive", fail_metadata)
    monkeypatch.setattr(optional_artifacts.shutil, "rmtree", fail_cleanup)
    with pytest.raises(ManagedArtifactCleanupError, match="temporary cleanup") as caught:
        store.create_bytes(
            b"invocation-owned",
            schema_version="phase5-test-v1",
            scope={"kind": "failed"},
            content_type="application/octet-stream",
        )

    assert len(caught.value.artifact_id) == 32
    assert isinstance(caught.value.__cause__, OSError)
    assert (store.root / f".{caught.value.artifact_id}.tmp").is_dir()
    assert store.load_bytes(final) == b"committed-final"


def test_optional_identity_is_independent_lazy_cached_and_light(tmp_path: Path) -> None:
    import sys

    before = set(sys.modules)
    from app.optional_modules import (
        OptionalModuleName,
        OptionalModuleServices,
        OptionalModuleStatus,
        build_optional_module_host,
    )
    imported = set(sys.modules) - before
    assert not {"sklearn", "torch", "huggingface_hub", "kronos"}.intersection(imported)

    class FakeFactory:
        def __init__(self, name: OptionalModuleName, available: bool) -> None:
            self.name = name
            self.is_available = available
            self.probes = 0
            self.creates = 0
            self.closes = 0
            self.received: OptionalModuleServices | None = None

        def probe(self) -> OptionalModuleStatus:
            self.probes += 1
            if self.is_available:
                return OptionalModuleStatus.ready(self.name)
            return OptionalModuleStatus.unavailable(self.name)

        def create(self, services: OptionalModuleServices) -> object:
            self.creates += 1
            self.received = services
            return {"module": self.name.value}

        def close(self, service: object) -> None:
            self.closes += 1

    shadow = FakeFactory(OptionalModuleName.SHADOW, True)
    thesis = FakeFactory(OptionalModuleName.THESIS, False)
    host = build_optional_module_host(
        database_path=tmp_path / "operational.db",
        data_root=tmp_path / "governed-data",
        factories={OptionalModuleName.SHADOW: shadow, OptionalModuleName.THESIS: thesis},
    )

    assert host.status(OptionalModuleName.SHADOW).available is True
    assert host.status(OptionalModuleName.SHADOW).available is True
    assert shadow.probes == 1
    assert thesis.probes == 0
    assert host.status(OptionalModuleName.THESIS).available is False
    assert host.status(OptionalModuleName.FORECAST).available is False
    assert thesis.probes == 1
    assert host.service(OptionalModuleName.THESIS) is None
    assert thesis.creates == 0
    assert host.service(OptionalModuleName.SHADOW) == {"module": "shadow"}
    assert host.service(OptionalModuleName.SHADOW) == {"module": "shadow"}
    assert shadow.creates == 1
    assert shadow.received is not None
    assert shadow.received.database_path == host.database_path
    host.close()
    assert shadow.closes == 1


def test_optional_identity_probe_failure_is_sanitized_and_local(tmp_path: Path) -> None:
    from app.optional_modules import (
        OptionalModuleName,
        OptionalModuleServices,
        OptionalModuleStatus,
        build_optional_module_host,
    )

    class BrokenFactory:
        def probe(self) -> OptionalModuleStatus:
            raise RuntimeError("password=secret path=/tmp/private/checkpoint")

        def create(self, services: OptionalModuleServices) -> object:
            raise AssertionError("unavailable factory must not initialize")

        def close(self, service: object) -> None:
            raise AssertionError("unavailable factory has no service")

    class ReadyFactory:
        def probe(self) -> OptionalModuleStatus:
            return OptionalModuleStatus.ready(OptionalModuleName.THESIS)

        def create(self, services: OptionalModuleServices) -> object:
            return object()

        def close(self, service: object) -> None:
            return None

    host = build_optional_module_host(
        database_path=tmp_path / "operational.db",
        data_root=tmp_path / "governed-data",
        factories={
            OptionalModuleName.SHADOW: BrokenFactory(),
            OptionalModuleName.THESIS: ReadyFactory(),
        },
    )
    broken = host.status(OptionalModuleName.SHADOW)
    assert broken.available is False
    assert broken.code == "shadow_probe_failed"
    assert "secret" not in repr(broken).lower()
    assert "/tmp/" not in repr(broken)
    assert host.status(OptionalModuleName.THESIS).available is True



def test_wr02_parquet_same_open_rejects_toctou(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """WR-02: TOCTOU swap after open cannot make Polars decode replacement bytes."""
    import os
    import polars as pl
    from app.optional_artifacts import ManagedArtifactError, ManagedImmutableArtifactStore

    store = ManagedImmutableArtifactStore(tmp_path / "managed")
    original = pl.DataFrame({"session_id": ["ORIG"], "close": [1.0]})
    replacement = pl.DataFrame({"session_id": ["SWAP"], "close": [99.0]})
    descriptor = store.create_parquet(
        original, schema_version="governed-panel-v1", scope={"kind": "toctou"}
    )
    payload_path = store.root / descriptor.relative_path
    replacement_bytes = (tmp_path / "replacement.parquet")
    replacement.write_parquet(replacement_bytes)

    real_open = os.open
    opened: list[int] = []

    def swapping_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        try:
            if Path(path).resolve() == payload_path.resolve():
                opened.append(fd)
                # Replace directory entry after the handle is open.
                os.replace(replacement_bytes, payload_path)
        except Exception:
            pass
        return fd

    monkeypatch.setattr(os, "open", swapping_open)
    try:
        frame = store.load_parquet(descriptor)
    except ManagedArtifactError:
        # Fail-closed is acceptable.
        assert opened, "expected same-open path to open the payload"
        return
    # If decode succeeds it must be the original frame, never the replacement.
    assert frame["session_id"].to_list() == ["ORIG"]
    assert frame["close"].to_list() == [1.0]


def test_parquet_same_open_and_unbound_discard_reference_safe(tmp_path: Path) -> None:
    import polars as pl
    from app.optional_artifacts import (
        ManagedArtifactError,
        ManagedImmutableArtifactStore,
    )

    store = ManagedImmutableArtifactStore(tmp_path / "managed")
    shared = store.create_bytes(
        b"shared-final",
        schema_version="phase5-test-v1",
        scope={"kind": "shared"},
        content_type="application/octet-stream",
    )
    frame = pl.DataFrame({"session_id": ["S1", "S2"], "close": [1.0, 2.0]})
    owned = store.create_parquet(
        frame, schema_version="governed-panel-v1", scope={"kind": "owned"}
    )
    loaded = store.load_parquet(owned)
    assert loaded.equals(frame)

    # Discard refuses non-owned descriptors.
    with pytest.raises(ManagedArtifactError, match="invocation-owned|referenced"):
        store.discard_unbound_invocation_owned(
            shared, owned_artifact_ids={owned.artifact_id}, is_referenced=lambda _aid: False
        )
    assert store.load_bytes(shared) == b"shared-final"

    # Discard refuses referenced owned artifacts.
    with pytest.raises(ManagedArtifactError, match="referenced|invocation"):
        store.discard_unbound_invocation_owned(
            owned, owned_artifact_ids={owned.artifact_id}, is_referenced=lambda _aid: True
        )
    assert store.load_parquet(owned).equals(frame)

    # Discard removes only the invocation-owned unbound namespace.
    store.discard_unbound_invocation_owned(
        owned, owned_artifact_ids={owned.artifact_id}, is_referenced=lambda _aid: False
    )
    assert not (store.root / owned.artifact_id).exists()
    assert store.load_bytes(shared) == b"shared-final"
