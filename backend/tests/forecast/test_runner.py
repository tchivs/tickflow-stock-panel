"""RED contracts for durable Forecast CAS jobs and bounded spawned inference."""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

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


def _descriptor(tmp_path: Path, *, horizon: int = 20, feature_count: int = 6) -> dict[str, object]:
    artifact = tmp_path / "forecast-outputs" / "forecast" / "artifact-1" / "output.parquet"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"verified-forecast-output")
    from hashlib import sha256

    return {
        "artifact_id": "artifact-1",
        "relative_path": "forecast/artifact-1/output.parquet",
        "schema_version": "forecast-output-v1",
        "byte_size": artifact.stat().st_size,
        "checksum_sha256": sha256(artifact.read_bytes()).hexdigest(),
        "sample_count": 32,
        "horizon": horizon,
        "feature_count": feature_count,
    }


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
        descriptor = manifest["output_descriptor"]
        target = self.root / "forecast-outputs" / descriptor["relative_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"verified-runner-output")
        from hashlib import sha256

        payload = target.read_bytes()
        descriptor["byte_size"] = len(payload)
        descriptor["checksum_sha256"] = sha256(payload).hexdigest()
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
            wall_clock_seconds=3, cpu_seconds=2, address_space_bytes=512 * 1024 * 1024,
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
        "cpu_seconds": 2, "address_space_bytes": 512 * 1024 * 1024,
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
    for manifest in ({"checksum_sha256": "0" * 64}, {"payload": "x" * (17 * 1024)}):
        runner, repository, _boundaries = _runner(tmp_path, worker=FixedWorker(manifest=manifest))
        job = _create(repository, idempotency_key=f"manifest-{len(json.dumps(manifest))}")
        result = runner.run_job(job["id"])
        assert result["status"] == "artifact_failed"
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



def test_commit_rejects_missing_or_divergent_provenance_and_shape(tmp_path):
    cases = (
        lambda record, descriptor: record.pop("source_digest_sha256"),
        lambda record, descriptor: record.__setitem__("catalog_id", "kronos-small"),
        lambda record, descriptor: record.__setitem__("temperature", float("nan")),
        lambda record, descriptor: record.__setitem__("future_session_ids", record["future_session_ids"][:-1]),
        lambda record, descriptor: descriptor.__setitem__("horizon", 5),
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
        descriptor["relative_path"] = relative_path
        if symlink:
            outside = case_root / "outside.parquet"
            outside.write_bytes(b"verified-forecast-output")
            link = case_root / "forecast-outputs" / relative_path
            link.parent.mkdir(parents=True, exist_ok=True)
            link.unlink(missing_ok=True)
            link.symlink_to(outside)
        if checksum is not None:
            descriptor["checksum_sha256"] = checksum
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
