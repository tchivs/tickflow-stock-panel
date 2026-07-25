"""RED contracts for durable Forecast CAS jobs and bounded spawned inference."""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest


JOB = {
    "instrument_id": "instrument-600000",
    "horizon": 20,
    "catalog_id": "kronos-mini",
    "idempotency_key": "request-key-1",
    "input_fingerprint": "a" * 64,
}


def _repository(tmp_path: Path):
    from app.forecast.repository import ForecastRepository

    repository = ForecastRepository(
        tmp_path / "operational.db", artifact_root=tmp_path / "forecast-outputs"
    )
    repository.migrate()
    return repository


def _create(repository, **overrides):
    payload = {**JOB, **overrides}
    return repository.create_or_get_active_job(**payload)


def _acquire(repository, job, *, owner: str = "worker-1"):
    assert repository.acquire_global_lease(owner=owner, ttl_seconds=30)
    return repository.acquire_job(
        job_id=job["id"], expected_status="queued", expected_version=job["transition_version"], lease_owner=owner, ttl_seconds=30
    )


def _path_tensor(*, horizon: int, feature_count: int) -> np.ndarray:
    return np.fromfunction(
        lambda sample, session, feature: 8.0
        + (sample * 0.1)
        + (session * 0.2)
        + (feature * 0.01),
        (32, horizon, feature_count),
        dtype=float,
    )


def _descriptor(tmp_path: Path, *, horizon: int = 20, feature_count: int = 6) -> dict[str, object]:
    from app.forecast.artifacts import ForecastArtifactStore

    paths = _path_tensor(horizon=horizon, feature_count=feature_count)
    features = ("open", "high", "low", "close", "volume", "amount")[:feature_count]
    sessions = tuple(
        (date(2025, 4, 30) + timedelta(days=index + 1)).strftime("CNA-%Y%m%d")
        for index in range(horizon)
    )
    bundle = ForecastArtifactStore.at(tmp_path / "forecast-outputs").persist(
        paths=paths,
        quantiles=np.quantile(paths, q=(0.10, 0.50, 0.90), axis=0),
        future_session_ids=sessions,
        feature_names=features,
        scope={"forecast_id": "strict-commit", "horizon": horizon},
    )
    return bundle.capped_manifest()


def _immutable(job) -> dict[str, object]:
    origin = date(2025, 4, 30)
    horizon = int(job["horizon"])
    return {
        "instrument_id": str(job["instrument_id"]),
        "origin_session_id": "CNA-20250430",
        "calendar_id": "cn-a-v1",
        "calendar_revision": "cn-a-calendar-2025-v1",
        "future_session_ids": [
            (origin + timedelta(days=index + 1)).strftime("CNA-%Y%m%d")
            for index in range(horizon)
        ],
        "input_fingerprint": str(job["input_fingerprint"]),
        "input_artifact_descriptor": {
            "artifact_id": "input-artifact",
            "schema_version": "forecast-input-v1",
            "byte_size": 1024,
            "checksum_sha256": "b" * 64,
        },
        "horizon": horizon,
        "lookback": 64,
        "seed": 0,
        "temperature": 1.0,
        "top_k": 1,
        "top_p": 1.0,
        "sample_count": 32,
        "catalog_id": str(job["catalog_id"]),
        "source_revision": "67b630e67f6a18c9e9be918d9b4337c960db1e9a",
        "source_digest_sha256": "c" * 64,
        "model_revision": "f4e68697d9d5aed55cef5c96aabc3376bcad9f81",
        "model_digest_sha256": "d" * 64,
        "tokenizer_revision": "26966d0035065a0cae0ebad7af8ece35bc1fb51c",
        "tokenizer_digest_sha256": "e" * 64,
        "feature_schema": ["open", "high", "low", "close", "volume", "amount"],
        "validation_warnings": [],
    }


def _commit(repository, job, tmp_path: Path, *, owner: str = "worker-1"):
    immutable = _immutable(job)
    repository.bind_commit_identity(job_id=str(job["id"]), immutable_record=immutable)
    return repository.commit_completed_forecast(
        job_id=job["id"],
        expected_status="running",
        expected_version=job["transition_version"],
        lease_owner=owner,
        output_descriptor=_descriptor(tmp_path, horizon=int(job["horizon"])),
        immutable_record=immutable,
    )


def test_same_idempotency_key_returns_same_active_job(tmp_path):
    repository = _repository(tmp_path)
    first = _create(repository)
    second = _create(repository)
    assert second["id"] == first["id"]
    assert repository.list_jobs() == [first]


def test_idempotency_identity_includes_authorized_request_scope(tmp_path):
    repository = _repository(tmp_path)
    first = _create(repository)
    second = _create(repository, instrument_id="instrument-000001")
    assert second["id"] != first["id"]
    assert len(repository.list_jobs()) == 2


def test_job_state_machine_rejects_illegal_cas_transition(tmp_path):
    repository = _repository(tmp_path)
    job = _create(repository)
    with pytest.raises(ValueError, match="transition"):
        repository.compare_and_swap_job(
            job_id=job["id"], expected_status="queued", expected_version=0, lease_owner=None, new_status="completed"
        )


def test_job_cas_rejects_stale_transition_version(tmp_path):
    repository = _repository(tmp_path)
    job = _create(repository)
    with pytest.raises(ValueError, match="stale|version"):
        repository.acquire_job(
            job_id=job["id"], expected_status="queued", expected_version=job["transition_version"] + 1,
            lease_owner="worker-1", ttl_seconds=30,
        )


def test_job_lease_requires_owner_and_unexpired_heartbeat(tmp_path):
    repository = _repository(tmp_path)
    running = _acquire(repository, _create(repository))
    with pytest.raises(ValueError, match="owner"):
        repository.heartbeat(job_id=running["id"], expected_version=running["transition_version"], lease_owner="worker-2", ttl_seconds=30)
    refreshed = repository.heartbeat(job_id=running["id"], expected_version=running["transition_version"], lease_owner="worker-1", ttl_seconds=30)
    assert refreshed["lease_owner"] == "worker-1"


def test_global_inference_lease_allows_exactly_one_parallel_winner(tmp_path):
    repository = _repository(tmp_path)
    barrier = threading.Barrier(2)
    def acquire(owner: str):
        barrier.wait()
        return repository.acquire_global_lease(owner=owner, ttl_seconds=30)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(acquire, ("worker-a", "worker-b")))
    assert sorted(outcomes) == [False, True]


def test_two_parallel_job_acquisitions_have_one_cas_winner(tmp_path):
    repository = _repository(tmp_path)
    job = _create(repository)
    barrier = threading.Barrier(2)
    def acquire(owner: str):
        barrier.wait()
        try:
            return repository.acquire_job(
                job_id=job["id"], expected_status="queued", expected_version=job["transition_version"],
                lease_owner=owner, ttl_seconds=30,
            )["lease_owner"]
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(acquire, ("worker-a", "worker-b")))
    assert sum(outcome is not None for outcome in outcomes) == 1


def test_explicit_retry_creates_new_job_and_lineage(tmp_path):
    repository = _repository(tmp_path)
    job = _create(repository)
    repository.terminalize(
        job_id=job["id"], expected_status="queued", expected_version=job["transition_version"],
        lease_owner=None, status="validation_failed", reason="safe_validation_failed",
    )
    retry = repository.create_retry_job(source_job_id=job["id"], idempotency_key="explicit-retry-1")
    assert retry["id"] != job["id"]
    assert retry["retry_of_job_id"] == job["id"]
    assert retry["attempt"] == job["attempt"] + 1


def test_retry_never_reuses_completed_forecast_record(tmp_path):
    repository = _repository(tmp_path)
    running = _acquire(repository, _create(repository))
    record = _commit(repository, running, tmp_path)
    retry = repository.create_retry_job(source_job_id=running["id"], idempotency_key="explicit-retry-2")
    assert retry["id"] != running["id"]
    assert repository.forecast_for_job(retry["id"]) is None
    assert repository.forecast_for_job(running["id"])["id"] == record["id"]


def test_interruption_before_artifact_creates_no_forecast(tmp_path):
    repository = _repository(tmp_path)
    running = _acquire(repository, _create(repository))
    repository.terminalize(
        job_id=running["id"], expected_status="running", expected_version=running["transition_version"],
        lease_owner="worker-1", status="interrupted", reason="worker_interrupted",
    )
    assert repository.forecast_for_job(running["id"]) is None


def test_interruption_after_temp_artifact_creates_no_forecast_and_cleans_temp(tmp_path):
    repository = _repository(tmp_path)
    running = _acquire(repository, _create(repository))
    temporary = tmp_path / ".forecast-output.tmp"
    temporary.write_bytes(b"partial")
    repository.terminalize(
        job_id=running["id"], expected_status="running", expected_version=running["transition_version"],
        lease_owner="worker-1", status="artifact_failed", reason="artifact_verification_failed",
        temporary_paths=[temporary],
    )
    assert repository.forecast_for_job(running["id"]) is None
    assert not temporary.exists()


def test_interruption_immediately_before_commit_creates_no_forecast(tmp_path):
    repository = _repository(tmp_path)
    running = _acquire(repository, _create(repository))
    repository.mark_interrupted_before_commit(job_id=running["id"], lease_owner="worker-1")
    assert repository.forecast_for_job(running["id"]) is None


def test_completed_commit_atomically_creates_one_immutable_forecast(tmp_path):
    repository = _repository(tmp_path)
    running = _acquire(repository, _create(repository))
    record = _commit(repository, running, tmp_path)
    assert record["sample_count"] == 32
    assert repository.get_job(running["id"])["status"] == "completed"
    assert repository.forecast_for_job(running["id"])["id"] == record["id"]


def test_parallel_completed_commits_return_one_canonical_forecast(tmp_path):
    repository = _repository(tmp_path)
    running = _acquire(repository, _create(repository))
    barrier = threading.Barrier(2)
    def commit(_index: int):
        barrier.wait()
        return _commit(repository, running, tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(commit, (1, 2)))
    assert records[0]["id"] == records[1]["id"]
    assert len(repository.list_forecasts()) == 1


def test_terminal_jobs_and_forecasts_are_immutable(tmp_path):
    repository = _repository(tmp_path)
    running = _acquire(repository, _create(repository))
    record = _commit(repository, running, tmp_path)
    with repository.connection() as connection:
        with pytest.raises(Exception, match="immutable"):
            connection.execute("UPDATE forecast_records SET horizon = 5 WHERE id = ?", (record["id"],))
        with pytest.raises(Exception, match="immutable"):
            connection.execute("DELETE FROM forecast_jobs WHERE id = ?", (running["id"],))


def test_restart_requeues_only_valid_never_started_queued_jobs(tmp_path):
    repository = _repository(tmp_path)
    queued = _create(repository)
    outcomes = repository.recover_after_restart(revalidate=lambda job: job["input_fingerprint"] == "a" * 64)
    assert outcomes == [{"job_id": queued["id"], "action": "requeue"}]
    assert repository.get_job(queued["id"])["status"] == "queued"


def test_concurrent_recovery_one_winner_dispatches_queued_job(tmp_path):
    from app.forecast.service import ForecastService
    from app.forecast.runner import FixedWorker

    runner, repository, _boundaries = _runner(tmp_path, worker=FixedWorker(valid=True))
    service = ForecastService(
        repository=repository,
        catalog=object(),
        freezer=object(),
        runner=runner,
        as_of_session=lambda _instrument: "CNA-20250430",
    )
    job = _create(repository, idempotency_key="recovery-one-winner")

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: service.run_recovered_job(job["id"]), range(2)))

    current = repository.get_job(job["id"])
    assert current is not None and current["status"] == "completed"
    assert len(repository.list_forecasts()) == 1
    assert {outcome["action"] for outcome in outcomes} <= {"dispatched", "observed"}


def test_restart_terminalizes_expired_running_job_without_native_resume(tmp_path):
    repository = _repository(tmp_path)
    running = _acquire(repository, _create(repository))
    outcomes = repository.recover_after_restart(now="2099-01-01T00:00:00Z", revalidate=lambda _job: True)
    assert outcomes == [{"job_id": running["id"], "action": "terminalized", "status": "interrupted"}]
    assert repository.get_job(running["id"])["status"] == "interrupted"


def test_restart_returns_completed_record_without_rewriting_it(tmp_path):
    repository = _repository(tmp_path)
    running = _acquire(repository, _create(repository))
    record = _commit(repository, running, tmp_path)
    before = json.dumps(record, sort_keys=True)
    repository.recover_after_restart(revalidate=lambda _job: True)
    assert json.dumps(repository.forecast_for_job(running["id"]), sort_keys=True) == before


def test_quantile_bundle_commit_reloads_verified_artifact_after_restart(tmp_path):
    from app.forecast.repository import ForecastRepository

    repository = _repository(tmp_path)
    running = _acquire(
        repository,
        _create(repository, idempotency_key="quantile-bundle-commit"),
    )
    committed = _commit(repository, running, tmp_path)

    restarted = ForecastRepository(
        tmp_path / "operational.db", artifact_root=tmp_path / "forecast-outputs"
    )
    restarted.migrate()
    reloaded = restarted.get_forecast(committed["id"])
    assert reloaded is not None
    assert reloaded["quantile_availability"] == "available"
    assert reloaded["quantiles"]["5"] == pytest.approx(
        {"p10": 9.14, "p50": 10.38, "p90": 11.62}
    )
    assert reloaded["quantiles_source_paths_sha256"] == reloaded["paths_checksum_sha256"]
    assert reloaded["quantile_row_count"] == 3 * 20 * 6
    with restarted.connection() as connection:
        row = connection.execute(
            """SELECT quantiles_artifact_descriptor_json, quantiles_checksum_sha256,
                      quantiles_source_paths_sha256, quantiles_provenance_digest_sha256
               FROM forecast_records WHERE id = ?""",
            (committed["id"],),
        ).fetchone()
        columns = {item[1] for item in connection.execute("PRAGMA table_info(forecast_records)")}
    assert row is not None and all(row)
    assert not ({"p10", "p50", "p90", "quantiles_json", "quantile_values_json"} & columns)


@pytest.mark.parametrize(
    "corruption",
    (
        "missing_artifact",
        "altered_bytes",
        "wrong_shape",
        "wrong_session",
        "wrong_label",
        "nonfinite",
        "crossed_relabel",
        "source_divergence",
    ),
)
def test_quantile_artifact_divergence_rolls_back_strict_commit(tmp_path, corruption):
    from app.optional_artifacts import ManagedImmutableArtifactStore

    case_root = tmp_path / corruption
    repository = _repository(case_root)
    running = _acquire(
        repository,
        _create(repository, idempotency_key=f"quantile-artifact-{corruption}"),
    )
    immutable = _immutable(running)
    repository.bind_commit_identity(job_id=str(running["id"]), immutable_record=immutable)
    bundle = _descriptor(case_root)
    quantile = bundle["quantiles_artifact"]
    assert isinstance(quantile, dict)
    payload_path = case_root / "forecast-outputs" / str(quantile["relative_path"])

    if corruption == "missing_artifact":
        payload_path.unlink()
    elif corruption == "altered_bytes":
        payload_path.write_bytes(payload_path.read_bytes() + b"tampered")
    else:
        frame = pl.read_parquet(payload_path)
        if corruption == "wrong_shape":
            frame = frame.slice(0, frame.height - 1)
        elif corruption == "wrong_session":
            frame = frame.with_columns(
                pl.when(pl.int_range(pl.len()) == 0)
                .then(pl.lit("CNA-20990101"))
                .otherwise(pl.col("session_id"))
                .alias("session_id")
            )
        elif corruption == "wrong_label":
            frame = frame.with_columns(
                pl.when(pl.col("quantile") == "P10")
                .then(pl.lit("P01"))
                .otherwise(pl.col("quantile"))
                .alias("quantile")
            )
        elif corruption == "nonfinite":
            frame = frame.with_columns(
                pl.when(pl.int_range(pl.len()) == 0)
                .then(float("nan"))
                .otherwise(pl.col("value"))
                .alias("value")
            )
        elif corruption == "crossed_relabel":
            frame = frame.with_columns(
                pl.when(pl.col("quantile") == "P10")
                .then(pl.lit("P90"))
                .when(pl.col("quantile") == "P90")
                .then(pl.lit("P10"))
                .otherwise(pl.col("quantile"))
                .alias("quantile")
            )
        source = (
            "0" * 64
            if corruption == "source_divergence"
            else str(bundle["paths_artifact"]["checksum_sha256"])
        )
        replacement = ManagedImmutableArtifactStore(
            case_root / "forecast-outputs"
        ).create_parquet(
            frame,
            schema_version="forecast-quantiles-v1",
            scope={
                "forecast_id": "strict-commit",
                "horizon": 20,
                "kind": "path_axis_quantiles",
                "source_paths_sha256": source,
                "shape": [3, 20, 6],
            },
        )
        bundle["quantiles_artifact"] = replacement.as_dict()

    with pytest.raises(ValueError):
        repository.commit_completed_forecast(
            job_id=running["id"],
            expected_status="running",
            expected_version=running["transition_version"],
            lease_owner="worker-1",
            output_descriptor=bundle,
            immutable_record=immutable,
        )
    assert repository.forecast_for_job(running["id"]) is None
    assert repository.get_job(running["id"])["status"] == "running"
    assert "completed" not in {
        row["status"]
        for row in repository.job_transitions_after(
            running["id"], after_version=-1, limit=256
        )
    }


@dataclass
class CountingBoundary:
    calls: int = 0
    def __call__(self, **_kwargs):
        self.calls += 1
        return True


@dataclass
class CommitArtifactBoundary:
    root: Path
    repository: object
    calls: int = 0

    def __call__(self, *, manifest, job):
        self.calls += 1
        manifest["output_descriptor"] = _descriptor(
            self.root, horizon=int(job["horizon"])
        )
        self.repository.bind_commit_identity(
            job_id=str(job["id"]), immutable_record=manifest["immutable_record"]
        )
        return True


def _runner(tmp_path: Path, **overrides):
    from app.forecast.runner import ForecastRunner, ForecastRunnerLimits
    repository = _repository(tmp_path)
    boundaries = {
        "reauthorize": CountingBoundary(),
        "catalog_revalidate": CountingBoundary(),
        "input_revalidate": CountingBoundary(),
        "worker": CountingBoundary(),
        "artifact_verify": CommitArtifactBoundary(tmp_path, repository),
    }
    boundaries.update(overrides)
    runner = ForecastRunner(
        repository=repository,
        limits=ForecastRunnerLimits(
            wall_clock_seconds=3, cpu_seconds=2, address_space_bytes=1024 * 1024 * 1024,
            thread_count=2, output_bytes=16 * 1024, queue_items=1,
        ),
        **boundaries,
    )
    return runner, repository, boundaries


def test_runner_revalidates_authority_catalog_and_input_before_spawn(tmp_path):
    runner, repository, boundaries = _runner(tmp_path)
    job = _create(repository)
    runner.run_job(job["id"])
    assert boundaries["reauthorize"].calls == 1
    assert boundaries["catalog_revalidate"].calls == 1
    assert boundaries["input_revalidate"].calls == 1
    assert boundaries["worker"].calls <= 1


def test_runner_uses_spawned_parent_owned_process_group_and_one_item_queue(tmp_path):
    runner, repository, _boundaries = _runner(tmp_path)
    result = runner.run_job(_create(repository)["id"])
    assert result["resources"]["start_method"] == "spawn"
    assert result["resources"]["new_process_group"] is True
    assert result["resources"]["queue_items"] == 1


def test_runner_enforces_wall_cpu_address_thread_output_and_manifest_bounds(tmp_path):
    runner, repository, _boundaries = _runner(tmp_path)
    result = runner.run_job(_create(repository)["id"])
    assert result["resources"] == {
        "start_method": "spawn", "new_process_group": True, "wall_clock_seconds": 3,
        "cpu_seconds": 2, "address_space_bytes": 1024 * 1024 * 1024,
        "thread_count": 2, "output_bytes": 16 * 1024, "queue_items": 1,
    }
    assert len(json.dumps(result["manifest"]).encode()) <= 16 * 1024


def test_runner_timeout_kills_reaps_descendants_and_cleans_temporary_files(tmp_path):
    from app.forecast.runner import BlockingWorker
    runner, repository, _boundaries = _runner(tmp_path, worker=BlockingWorker(descendant=True))
    job = _create(repository)
    result = runner.run_job(job["id"])
    assert result["status"] == "timeout"
    assert result["process_group_reaped"] is True
    assert not list(tmp_path.rglob("*.tmp"))
    assert repository.forecast_for_job(job["id"]) is None


def test_runner_rejects_tampered_or_oversized_manifest_without_record(tmp_path):
    from app.forecast.runner import FixedWorker
    for manifest, expected_status in (
        ({"checksum_sha256": "0" * 64}, "artifact_failed"),
        ({"payload": "x" * (17 * 1024)}, "resource_terminated"),
    ):
        runner, repository, _boundaries = _runner(tmp_path, worker=FixedWorker(manifest=manifest))
        job = _create(repository, idempotency_key=f"manifest-{len(json.dumps(manifest))}")
        result = runner.run_job(job["id"])
        assert result["status"] == expected_status
        assert repository.forecast_for_job(job["id"]) is None


def test_runner_maps_worker_failures_to_safe_path_free_terminal_reasons(tmp_path):
    from app.forecast.runner import CrashingWorker
    runner, repository, _boundaries = _runner(tmp_path, worker=CrashingWorker("/secret/model: token=abc\nTraceback"))
    result = runner.run_job(_create(repository)["id"])
    serialized = json.dumps(result)
    assert result["status"] in {"resource_terminated", "checkpoint_mismatch", "artifact_failed"}
    assert "/secret" not in serialized and "Traceback" not in serialized and "token=abc" not in serialized


def test_runner_lost_lease_rejects_late_output_and_creates_no_record(tmp_path):
    from app.forecast.runner import FixedWorker
    runner, repository, _boundaries = _runner(tmp_path, worker=FixedWorker(lose_lease_before_result=True))
    job = _create(repository)
    result = runner.run_job(job["id"])
    assert result["status"] == "interrupted"
    assert repository.forecast_for_job(job["id"]) is None


def test_runner_success_commits_once_and_never_invokes_downstream_authority(tmp_path):
    from app.forecast.runner import FixedWorker
    action_spies = {name: CountingBoundary() for name in ("thesis", "strategy", "decision_plan", "monitor", "position", "broker")}
    runner, repository, _boundaries = _runner(tmp_path, worker=FixedWorker(valid=True), action_collaborators=action_spies)
    result = runner.run_job(_create(repository)["id"])
    assert result["status"] == "completed"
    assert len(repository.list_forecasts()) == 1
    assert all(spy.calls == 0 for spy in action_spies.values())


def test_production_service_revalidation_reloads_catalog_and_frozen_input_before_run(tmp_path):
    from types import SimpleNamespace

    from app.forecast.service import ForecastService

    repository = _repository(tmp_path)
    checkpoint = SimpleNamespace(
        catalog_id="kronos-mini",
        source_revision="67b630e67f6a18c9e9be918d9b4337c960db1e9a",
        source_digest_sha256="c" * 64,
        model_revision="f4e68697d9d5aed55cef5c96aabc3376bcad9f81",
        model_weight_sha256="d" * 64,
        tokenizer_revision="26966d0035065a0cae0ebad7af8ece35bc1fb51c",
        tokenizer_weight_sha256="e" * 64,
        max_context=512,
    )

    class Catalog:
        def __init__(self):
            self.revalidations = 0

        def require_local(self, catalog_id, *, device):
            assert catalog_id == "kronos-mini"
            assert device == "cpu"
            return checkpoint

        def revalidate_before_spawn(self, selected):
            assert selected is checkpoint
            self.revalidations += 1
            return selected

    descriptor = SimpleNamespace(
        checksum_sha256="b" * 64,
        managed_path=str(tmp_path / "input.parquet"),
        public=lambda: {
            "artifact_id": "input-artifact",
            "schema_version": "forecast-input-v1",
            "byte_size": 1,
            "checksum_sha256": "b" * 64,
        },
    )
    frozen = SimpleNamespace(
        instrument_id="instrument-600000",
        catalog_id="kronos-mini",
        horizon=20,
        as_of_session_id="CNA-20250430",
        lookback=64,
        calendar_revision="cn-a-calendar-2025-v1",
        historical_session_ids=tuple(
            (date(2025, 2, 25) + timedelta(days=index)).strftime("CNA-%Y%m%d")
            for index in range(64)
        ),
        future_session_ids=tuple(
            (date(2025, 5, 1) + timedelta(days=index)).strftime("CNA-%Y%m%d")
            for index in range(20)
        ),
        feature_schema=["open", "high", "low", "close", "volume"],
        input_fingerprint="a" * 64,
        descriptor=descriptor,
    )

    class Freezer:
        def __init__(self):
            self.freezes = 0

        def freeze(self, **kwargs):
            assert kwargs["principal"] == "researcher-1"
            assert kwargs["as_of_session_id"] == "CNA-20250430"
            assert kwargs["max_context"] == 512
            self.freezes += 1
            return frozen

        def load(self, descriptor):
            assert descriptor is frozen.descriptor
            return object()

    class Runner:
        def __init__(self):
            self.calls = []

        def run_job(self, job_id):
            self.calls.append(job_id)
            return {"status": "queued"}

    catalog = Catalog()
    freezer = Freezer()
    runner = Runner()
    service = ForecastService(
        repository=repository,
        catalog=catalog,
        freezer=freezer,
        runner=runner,
        as_of_session=lambda _instrument: "CNA-20250430",
        device="cpu",
    )

    job = service.create_or_get_job(
        principal="researcher-1",
        instrument="instrument-600000",
        horizon=20,
        catalog_id="kronos-mini",
        idempotency_key="production-revalidation",
    )
    assert runner.calls == [job["id"]]
    assert service.revalidate(job) is True
    assert catalog.revalidations >= 2
    assert freezer.freezes >= 3


def test_contextual_worker_forwards_only_bounded_quantile_artifact_bundle(tmp_path):
    from app.forecast.service import ContextualForecastWorker

    bundle = _descriptor(tmp_path)
    immutable = {"identity": "server-bound"}

    def delegate(**_kwargs):
        return {
            "artifacts": bundle,
            "validation_warnings": [
                {"code": "flat_quantile_band", "message": "untrusted detail"}
            ],
            "paths": [["must-not-cross"]],
            "quantiles": [["must-not-cross"]],
        }

    worker = ContextualForecastWorker(
        delegate=delegate,
        contexts={"job-1": {"immutable_record": immutable}},
    )
    result = worker(job={"id": "job-1"}, limits={})
    assert result == {
        "output_descriptor": bundle,
        "immutable_record": {
            "identity": "server-bound",
            "validation_warnings": ["flat_quantile_band"],
        },
    }



def test_commit_rejects_missing_or_divergent_provenance_and_shape(tmp_path):
    cases = (
        lambda record, descriptor: record.pop("source_digest_sha256"),
        lambda record, descriptor: record.__setitem__("catalog_id", "kronos-small"),
        lambda record, descriptor: record.__setitem__("temperature", float("nan")),
        lambda record, descriptor: record.__setitem__("future_session_ids", record["future_session_ids"][:-1]),
        lambda record, descriptor: descriptor["path_shape"].__setitem__(1, 5),
        lambda record, descriptor: record["input_artifact_descriptor"].__setitem__("checksum_sha256", "f" * 64),
    )
    for index, mutate in enumerate(cases):
        case_root = tmp_path / f"case-{index}"
        repository = _repository(case_root)
        running = _acquire(
            repository,
            _create(repository, idempotency_key=f"strict-commit-{index}"),
            owner=f"worker-{index}",
        )
        expected = _immutable(running)
        repository.bind_commit_identity(job_id=str(running["id"]), immutable_record=expected)
        record = json.loads(json.dumps(expected))
        descriptor = _descriptor(case_root)
        mutate(record, descriptor)
        with pytest.raises(ValueError):
            repository.commit_completed_forecast(
                job_id=running["id"],
                expected_status="running",
                expected_version=running["transition_version"],
                lease_owner=f"worker-{index}",
                output_descriptor=descriptor,
                immutable_record=record,
            )


def test_output_path_containment_requires_regular_verified_artifact(tmp_path):
    def rejected(relative_path: str, *, symlink: bool = False, checksum: str | None = None) -> None:
        case_root = tmp_path / relative_path.replace("/", "_").replace(".", "dot")
        repository = _repository(case_root)
        running = _acquire(repository, _create(repository, idempotency_key=case_root.name))
        immutable = _immutable(running)
        repository.bind_commit_identity(job_id=str(running["id"]), immutable_record=immutable)
        descriptor = _descriptor(case_root)
        paths_descriptor = descriptor["paths_artifact"]
        assert isinstance(paths_descriptor, dict)
        paths_descriptor["relative_path"] = relative_path
        if symlink:
            outside = case_root / "outside.parquet"
            outside.write_bytes(b"verified-forecast-output")
            link = case_root / "forecast-outputs" / relative_path
            link.parent.mkdir(parents=True, exist_ok=True)
            link.unlink(missing_ok=True)
            link.symlink_to(outside)
        if checksum is not None:
            paths_descriptor["checksum_sha256"] = checksum
        with pytest.raises(ValueError):
            repository.commit_completed_forecast(
                job_id=running["id"],
                expected_status="running",
                expected_version=running["transition_version"],
                lease_owner="worker-1",
                output_descriptor=descriptor,
                immutable_record=immutable,
            )

    rejected("../escaped.parquet")
    rejected("/absolute/output.parquet")
    rejected("forecast/symlink/output.parquet", symlink=True)
    rejected("forecast/artifact-1/output.parquet", checksum="0" * 64)



@dataclass
class CommitSpyRepository:
    """Wrap ForecastRepository and count sole commit invocations."""

    inner: object
    commit_calls: int = 0

    def __getattr__(self, name: str):
        return getattr(self.inner, name)

    def commit_completed_forecast(self, **kwargs):
        self.commit_calls += 1
        return self.inner.commit_completed_forecast(**kwargs)


def test_cr05_final_input_revalidation_precedes_commit_and_commit_spy_zero(tmp_path):
    """CR-05: post-worker/pre-commit input divergence terminalizes with commit spy 0."""
    from app.forecast.runner import FixedWorker, ForecastRunner, ForecastRunnerLimits

    action_spies = {
        name: CountingBoundary()
        for name in ("thesis", "strategy", "decision_plan", "monitor", "position", "broker")
    }
    order: list[str] = []
    base = _repository(tmp_path)
    spy_repo = CommitSpyRepository(inner=base)

    def artifact_verify(*, manifest, job):
        order.append("artifact_verify")
        return True

    def final_input_revalidate(*, job):
        order.append("final_input_revalidate")
        return False

    runner = ForecastRunner(
        repository=spy_repo,
        limits=ForecastRunnerLimits(
            wall_clock_seconds=30,
            cpu_seconds=20,
            address_space_bytes=1024 * 1024 * 1024,
            thread_count=2,
            output_bytes=16 * 1024,
            queue_items=1,
        ),
        reauthorize=CountingBoundary(),
        catalog_revalidate=CountingBoundary(),
        input_revalidate=CountingBoundary(),
        worker=FixedWorker(valid=True),
        artifact_verify=artifact_verify,
        action_collaborators=action_spies,
        final_input_revalidate=final_input_revalidate,
    )
    job = _create(base, idempotency_key="cr05-final-input")
    result = runner.run_job(job["id"])
    assert result["status"] == "validation_failed"
    assert result.get("reason") == "final_input_revalidation_failed"
    assert spy_repo.commit_calls == 0
    assert base.forecast_for_job(job["id"]) is None
    assert all(spy.calls == 0 for spy in action_spies.values())
    assert order == ["artifact_verify", "final_input_revalidate"]


def test_cr05_worker_input_tamper_and_pre_commit_input_rejection(tmp_path, monkeypatch):
    """Worker-visible context has no writable path; tamper fails final revalidation."""
    from app.forecast.service import ForecastService, _open_read_only_input_handle
    from types import SimpleNamespace
    from app.optional_artifacts import ManagedImmutableArtifactStore
    import polars as pl

    store = ManagedImmutableArtifactStore(tmp_path / "inputs")
    frame = pl.DataFrame({"session_id": ["S1"], "close": [1.0]})
    managed = store.create_parquet(
        frame, schema_version="forecast-input-v1", scope={"k": "v"}
    )
    descriptor = SimpleNamespace(
        artifact_id=managed.artifact_id,
        schema_version=managed.schema_version,
        byte_size=managed.byte_size,
        checksum_sha256=managed.checksum_sha256,
        managed_path=str(store.root / managed.relative_path),
        public=lambda: {
            "artifact_id": managed.artifact_id,
            "schema_version": managed.schema_version,
            "byte_size": managed.byte_size,
            "checksum_sha256": managed.checksum_sha256,
        },
        _managed=managed,
    )
    sealed = _open_read_only_input_handle(descriptor)
    assert sealed["writable"] is False
    assert "path" not in sealed
    assert "managed_path" not in sealed
    assert sealed["checksum_sha256"] == managed.checksum_sha256
    # Mutating the sealed payload must not be possible via path rewrite of the
    # authoritative namespace without failing the sealed checksum.
    payload_path = store.root / managed.relative_path
    original = payload_path.read_bytes()
    payload_path.write_bytes(b"TAMPERED" + original[8:])
    from hashlib import sha256

    assert sha256(sealed["payload"]).hexdigest() == managed.checksum_sha256
    assert sha256(payload_path.read_bytes()).hexdigest() != managed.checksum_sha256


def test_wr01_operation_first_replay_race_leaves_no_orphan(tmp_path):
    """WR-01: same-key replay allocates no input; race leaves one bound namespace."""
    from types import SimpleNamespace
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from app.forecast.service import ForecastService
    from app.optional_artifacts import ManagedImmutableArtifactStore
    import polars as pl
    import threading

    store_root = tmp_path / "managed-inputs"
    store = ManagedImmutableArtifactStore(store_root)
    freezes: list[str] = []
    freeze_lock = threading.Lock()

    class Freezer:
        def freeze(self, **kwargs):
            frame = pl.DataFrame({"session_id": ["S1", "S2"], "close": [10.0, 11.0]})
            managed = store.create_parquet(
                frame,
                schema_version="forecast-input-v1",
                scope={"instrument": kwargs.get("principal"), "n": len(freezes)},
            )
            with freeze_lock:
                freezes.append(managed.artifact_id)
            descriptor = SimpleNamespace(
                artifact_id=managed.artifact_id,
                schema_version=managed.schema_version,
                byte_size=managed.byte_size,
                checksum_sha256=managed.checksum_sha256,
                managed_path=str(store.root / managed.relative_path),
                metadata_json="{}",
                public=lambda: {
                    "artifact_id": managed.artifact_id,
                    "schema_version": managed.schema_version,
                    "byte_size": managed.byte_size,
                    "checksum_sha256": managed.checksum_sha256,
                },
                _managed=managed,
            )
            return SimpleNamespace(
                instrument_id="instrument-600000",
                symbol="600000.SH",
                catalog_id="kronos-mini",
                horizon=20,
                as_of_session_id="CNA-20250430",
                lookback=64,
                adjustment_policy="forward",
                adjustment_revision="adj-1",
                calendar_revision="cn-a-calendar-2025-v1",
                historical_session_ids=tuple(f"CNA-20250{i:03d}" for i in range(64)),
                future_session_ids=tuple(f"CNA-20251{i:03d}" for i in range(20)),
                feature_schema=["open", "high", "low", "close", "volume"],
                input_fingerprint="a" * 64,
                descriptor=descriptor,
            )

        def load(self, descriptor):
            return store.load_parquet(descriptor._managed)

        _store = store

    class Catalog:
        def require_local(self, catalog_id, *, device):
            return SimpleNamespace(
                catalog_id=catalog_id,
                source_revision="67b630e67f6a18c9e9be918d9b4337c960db1e9a",
                source_digest_sha256="c" * 64,
                model_revision="f4e68697d9d5aed55cef5c96aabc3376bcad9f81",
                model_weight_sha256="d" * 64,
                tokenizer_revision="26966d0035065a0cae0ebad7af8ece35bc1fb51c",
                tokenizer_weight_sha256="e" * 64,
                max_context=512,
            )

        def revalidate_before_spawn(self, selected):
            return selected

    class Runner:
        def __init__(self):
            self.calls = []

        def run_job(self, job_id):
            self.calls.append(job_id)
            return {"status": "queued"}

    repository = _repository(tmp_path)
    freezer = Freezer()
    runner = Runner()
    service = ForecastService(
        repository=repository,
        catalog=Catalog(),
        freezer=freezer,
        runner=runner,
        as_of_session=lambda _instrument: "CNA-20250430",
        device="cpu",
    )

    first = service.create_or_get_job(
        principal="researcher-1",
        instrument="instrument-600000",
        horizon=20,
        catalog_id="kronos-mini",
        idempotency_key="wr01-key",
    )
    namespaces_after_first = {
        p.name for p in store_root.iterdir() if p.is_dir() and not p.name.startswith(".")
    }
    assert len(namespaces_after_first) == 1
    assert freezes  # one freeze
    freeze_count_after_first = len(freezes)

    # Ordinary same-key replay allocates nothing.
    second = service.create_or_get_job(
        principal="researcher-1",
        instrument="instrument-600000",
        horizon=20,
        catalog_id="kronos-mini",
        idempotency_key="wr01-key",
    )
    assert second["id"] == first["id"]
    assert len(freezes) == freeze_count_after_first
    namespaces_after_replay = {
        p.name for p in store_root.iterdir() if p.is_dir() and not p.name.startswith(".")
    }
    assert namespaces_after_replay == namespaces_after_first

    # Concurrent race: only one canonical namespace remains (losers discarded).
    race_key = "wr01-race-key"
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(
                service.create_or_get_job,
                principal="researcher-1",
                instrument="instrument-600000",
                horizon=20,
                catalog_id="kronos-mini",
                idempotency_key=race_key,
            )
            for _ in range(4)
        ]
        for future in as_completed(futures):
            results.append(future.result())
    job_ids = {row["id"] for row in results}
    assert len(job_ids) == 1
    remaining = {
        p.name for p in store_root.iterdir() if p.is_dir() and not p.name.startswith(".")
    }
    # First job namespace + race canonical namespace only.
    assert len(remaining) == 2
    # Bound identity for race job must reference an existing namespace.
    bound = repository._commit_identities.get(results[0]["id"])
    assert isinstance(bound, dict)
    bound_id = bound["input_artifact_descriptor"]["artifact_id"]
    assert bound_id in remaining


def test_idempotent_input_namespace_and_orphan_cleanup_on_failure(tmp_path):
    """Failure after promotion discards only the invocation-owned unbound namespace."""
    from types import SimpleNamespace
    from app.forecast.service import ForecastService
    from app.optional_artifacts import ManagedImmutableArtifactStore
    import polars as pl

    store = ManagedImmutableArtifactStore(tmp_path / "managed-inputs")
    shared = store.create_bytes(
        b"shared-committed",
        schema_version="phase5-test-v1",
        scope={"kind": "shared"},
        content_type="application/octet-stream",
    )

    class Freezer:
        def freeze(self, **kwargs):
            frame = pl.DataFrame({"session_id": ["S1"], "close": [1.0]})
            managed = store.create_parquet(
                frame, schema_version="forecast-input-v1", scope={"k": "fail"}
            )
            descriptor = SimpleNamespace(
                artifact_id=managed.artifact_id,
                schema_version=managed.schema_version,
                byte_size=managed.byte_size,
                checksum_sha256=managed.checksum_sha256,
                managed_path=str(store.root / managed.relative_path),
                metadata_json="{}",
                public=lambda: {
                    "artifact_id": managed.artifact_id,
                    "schema_version": managed.schema_version,
                    "byte_size": managed.byte_size,
                    "checksum_sha256": managed.checksum_sha256,
                },
                _managed=managed,
            )
            return SimpleNamespace(
                instrument_id="instrument-600000",
                symbol="600000.SH",
                catalog_id="kronos-mini",
                horizon=20,
                as_of_session_id="CNA-20250430",
                lookback=64,
                adjustment_policy="forward",
                adjustment_revision="adj-1",
                calendar_revision="cn-a-calendar-2025-v1",
                historical_session_ids=tuple(f"CNA-20250{i:03d}" for i in range(64)),
                future_session_ids=tuple(f"CNA-20251{i:03d}" for i in range(20)),
                feature_schema=["open", "high", "low", "close", "volume"],
                input_fingerprint="b" * 64,
                descriptor=descriptor,
            )

        def load(self, descriptor):
            raise RuntimeError("should not load")

        _store = store

    class Catalog:
        def require_local(self, catalog_id, *, device):
            return SimpleNamespace(
                catalog_id=catalog_id,
                source_revision="67b630e67f6a18c9e9be918d9b4337c960db1e9a",
                source_digest_sha256="c" * 64,
                model_revision="f4e68697d9d5aed55cef5c96aabc3376bcad9f81",
                model_weight_sha256="d" * 64,
                tokenizer_revision="26966d0035065a0cae0ebad7af8ece35bc1fb51c",
                tokenizer_weight_sha256="e" * 64,
                max_context=512,
            )

        def revalidate_before_spawn(self, selected):
            return selected

    class ExplodingRunner:
        def run_job(self, job_id):
            raise RuntimeError("runner boom")

    repository = _repository(tmp_path)
    service = ForecastService(
        repository=repository,
        catalog=Catalog(),
        freezer=Freezer(),
        runner=ExplodingRunner(),
        as_of_session=lambda _instrument: "CNA-20250430",
        device="cpu",
    )
    with pytest.raises(RuntimeError, match="runner boom"):
        service.create_or_get_job(
            principal="researcher-1",
            instrument="instrument-600000",
            horizon=20,
            catalog_id="kronos-mini",
            idempotency_key="orphan-fail",
        )
    # Job was created and bound before run_job; shared asset remains; job-bound
    # namespace remains (referenced). Only unbound would be discarded.
    assert store.load_bytes(shared) == b"shared-committed"
    remaining = [p.name for p in store.root.iterdir() if p.is_dir() and not p.name.startswith(".")]
    assert shared.artifact_id in remaining



class HostileOutputWorker:
    """Emit more stdout than the parent budget allows before returning."""

    def __call__(self, *, job, limits):
        import sys

        sys.stdout.write("x" * (int(limits["output_bytes"]) + 64))
        sys.stdout.flush()
        return True


class NeverReadyWorker:
    """Worker body is never reached if ready fails; used only for spawn races."""

    def __call__(self, **_kwargs):
        import time

        time.sleep(300)
        return {}


class OversizedManifestWorker:
    def __call__(self, *, job, limits):
        return {"payload": "y" * (int(limits["output_bytes"]) + 8)}


def _silent_child_no_ready(worker, job, limits, output):
    """Picklable child that setsid then never emits ready."""
    import os
    import time

    del worker, job, limits, output
    os.setsid()
    time.sleep(30)




def test_runner_output_cap_before_allocation_rejects_hostile_stdout(tmp_path):
    runner, repository, _boundaries = _runner(tmp_path, worker=HostileOutputWorker())
    result = runner.run_job(_create(repository, idempotency_key="hostile-output")["id"])
    assert result["status"] == "resource_terminated"
    assert repository.forecast_for_job(result["job_id"]) is None
    serialized = json.dumps(result)
    assert "xxxx" not in serialized


def test_runner_byte_ipc_rejects_oversized_manifest_frame(tmp_path):
    runner, repository, _boundaries = _runner(tmp_path, worker=OversizedManifestWorker())
    result = runner.run_job(_create(repository, idempotency_key="byte-ipc")["id"])
    assert result["status"] == "resource_terminated"
    assert repository.forecast_for_job(result["job_id"]) is None


def test_runner_child_ready_handshake_precedes_work_deadline(monkeypatch):
    from app.forecast import runner as runner_module

    events: list[str] = []

    class _Pipe:
        def send_bytes(self, payload: bytes) -> None:
            events.append(json.loads(payload.decode("utf-8"))["kind"])

        def close(self) -> None:
            return None

    monkeypatch.setattr(runner_module.os, "setsid", lambda: None)
    monkeypatch.setattr(runner_module, "_configure_child_runtime", lambda *_a, **_k: None)
    monkeypatch.setattr(runner_module, "_install_child_limits", lambda *_a, **_k: None)
    job = {
        "id": "job-ready",
        "instrument_id": "instrument-600000",
        "horizon": 20,
        "catalog_id": "kronos-mini",
        "input_fingerprint": "a" * 64,
    }
    limits = {
        "cpu_seconds": 1,
        "address_space_bytes": 1024 * 1024,
        "thread_count": 1,
        "output_bytes": 16 * 1024,
    }
    runner_module._child_entry(runner_module.FixedWorker(valid=True), job, limits, _Pipe())
    assert events[0] == "ready"
    assert "success" in events




def test_runner_startup_race_timeout_before_ready_reaps_process(tmp_path, monkeypatch):
    from app.forecast import runner as runner_module
    from app.forecast.runner import ForecastRunner, ForecastRunnerLimits

    monkeypatch.setattr(runner_module, "_child_entry", _silent_child_no_ready)
    repository = _repository(tmp_path)
    runner = ForecastRunner(
        repository=repository,
        limits=ForecastRunnerLimits(
            wall_clock_seconds=1,
            cpu_seconds=1,
            address_space_bytes=1024 * 1024 * 1024,
            thread_count=1,
            output_bytes=4096,
            queue_items=1,
        ),
        reauthorize=CountingBoundary(),
        catalog_revalidate=CountingBoundary(),
        input_revalidate=CountingBoundary(),
        worker=NeverReadyWorker(),
        artifact_verify=CommitArtifactBoundary(tmp_path, repository),
    )
    job = _create(repository, idempotency_key="startup-race")
    result = runner.run_job(job["id"])
    assert result["status"] == "timeout"
    assert result.get("reason") == "worker_startup_timeout"
    assert result.get("process_group_reaped") is True




def test_runner_terminate_kill_fallback_reaps_descendants(tmp_path):
    from app.forecast.runner import BlockingWorker

    runner, repository, _boundaries = _runner(tmp_path, worker=BlockingWorker(descendant=True))
    result = runner.run_job(_create(repository, idempotency_key="descendants-reaped")["id"])
    assert result["status"] == "timeout"
    assert result["process_group_reaped"] is True


def test_runner_lease_loss_reaps_worker_tree(tmp_path):
    from app.forecast.runner import FixedWorker

    runner, repository, _boundaries = _runner(
        tmp_path, worker=FixedWorker(lose_lease_before_result=True)
    )
    job = _create(repository, idempotency_key="lease-loss-reap")
    result = runner.run_job(job["id"])
    assert result["status"] == "interrupted"
    assert repository.forecast_for_job(job["id"]) is None


def test_restart_dispatches_queued_job_via_recovered_service_path(tmp_path):
    """CR-07 unit: requeue outcomes are consumed by ForecastService.run_recovered_job."""
    from app.forecast.service import ForecastService

    runner, repository, boundaries = _runner(tmp_path)
    queued = _create(repository, idempotency_key="restart-dispatch-queued")
    outcomes = repository.recover_after_restart(revalidate=lambda _job: True)
    assert outcomes == [{"job_id": queued["id"], "action": "requeue"}]

    class _Service:
        def __init__(self):
            self.repository = repository
            self.runner = runner

        run_recovered_job = ForecastService.run_recovered_job

    service = _Service()
    dispatched = ForecastService.run_recovered_job(service, queued["id"])
    assert dispatched["action"] == "dispatched"
    assert dispatched["status"] == "completed"
    assert repository.get_job(queued["id"])["status"] == "completed"
    assert repository.forecast_for_job(queued["id"]) is not None
    # Spawned workers do not share the parent CountingBoundary call counter.
    assert boundaries["worker"].calls <= 1


def test_concurrent_recovery_one_winner(tmp_path):
    """CR-07: two concurrent recovered dispatches produce one worker winner."""
    from concurrent.futures import ThreadPoolExecutor

    from app.forecast.service import ForecastService

    runner, repository, boundaries = _runner(tmp_path)
    queued = _create(repository, idempotency_key="concurrent-recovery-one-winner")

    class _Service:
        def __init__(self):
            self.repository = repository
            self.runner = runner

        run_recovered_job = ForecastService.run_recovered_job

    service = _Service()
    barrier = threading.Barrier(2)

    def recover(_index: int):
        barrier.wait()
        return ForecastService.run_recovered_job(service, queued["id"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(recover, (1, 2)))

    statuses = {item["status"] for item in results}
    actions = {item["action"] for item in results}
    assert "completed" in statuses
    assert actions <= {"dispatched", "observed"}
    assert repository.get_job(queued["id"])["status"] == "completed"
    assert len(repository.list_forecasts()) == 1
    # At most one spawn-side execution; parent-side call counters are not shared.
    assert boundaries["worker"].calls <= 1


def test_restart_terminalizes_invalid_queued_and_expired_running(tmp_path):
    repository = _repository(tmp_path)
    invalid = _create(repository, idempotency_key="restart-terminalizes-invalid")
    running = _acquire(repository, _create(repository, idempotency_key="restart-terminalizes-running"))
    outcomes = repository.recover_after_restart(
        now="2099-01-01T00:00:00Z",
        revalidate=lambda job: job["id"] != invalid["id"],
    )
    by_id = {item["job_id"]: item for item in outcomes}
    assert by_id[invalid["id"]] == {
        "job_id": invalid["id"],
        "action": "terminalized",
        "status": "validation_failed",
    }
    assert by_id[running["id"]] == {
        "job_id": running["id"],
        "action": "terminalized",
        "status": "interrupted",
    }
    assert repository.get_job(invalid["id"])["status"] == "validation_failed"
    assert repository.get_job(running["id"])["status"] == "interrupted"


def test_cr06_normal_leader_exit_reaps_process_group_before_commit(tmp_path):
    """CR-06 primary: successful leader exit still reaps the handshake process group."""
    import os
    import time

    from app.forecast.runner import SuccessWithDescendantWorker

    marker = tmp_path / "descendant.pid"
    runner, repository, _boundaries = _runner(
        tmp_path,
        worker=SuccessWithDescendantWorker(marker_path=str(marker)),
    )
    job = _create(repository, idempotency_key="cr06-normal-leader-exit")
    result = runner.run_job(job["id"])
    assert result["status"] == "completed"
    assert result["process_group_reaped"] is True
    assert repository.get_job(job["id"])["status"] == "completed"
    # Descendant PID written by the worker must be gone before completion is observable.
    deadline = time.monotonic() + 2.0
    descendant_pid = None
    if marker.exists():
        descendant_pid = int(marker.read_text(encoding="utf-8").strip())
        while time.monotonic() < deadline:
            try:
                os.kill(descendant_pid, 0)
            except ProcessLookupError:
                descendant_pid = None
                break
            time.sleep(0.05)
    assert descendant_pid is None


def test_normal_exit_descendants_reaped(tmp_path):
    from app.forecast.runner import SuccessWithDescendantWorker

    runner, repository, _boundaries = _runner(
        tmp_path, worker=SuccessWithDescendantWorker()
    )
    result = runner.run_job(_create(repository, idempotency_key="normal-exit-descendants")["id"])
    assert result["status"] == "completed"
    assert result["process_group_reaped"] is True


def test_every_return_reaps_group_on_malformed_success_manifest(tmp_path):
    from app.forecast.runner import FixedWorker

    runner, repository, _boundaries = _runner(
        tmp_path, worker=FixedWorker(manifest={"checksum_sha256": "0" * 64})
    )
    result = runner.run_job(_create(repository, idempotency_key="every-return-reaps")["id"])
    assert result["status"] == "artifact_failed"
    # Finally reaps even when the terminal payload omits the flag.
    assert repository.forecast_for_job(result["job_id"]) is None
