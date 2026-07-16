"""RED contracts for durable Forecast CAS jobs and bounded spawned inference."""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
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
    repository = ForecastRepository(tmp_path / "operational.db")
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


def _descriptor(tmp_path: Path) -> dict[str, object]:
    artifact = tmp_path / "forecast-output.parquet"
    artifact.write_bytes(b"verified-forecast-output")
    from hashlib import sha256
    return {
        "artifact_id": "artifact-1",
        "relative_path": "forecast/artifact-1/output.parquet",
        "schema_version": "forecast-output-v1",
        "byte_size": artifact.stat().st_size,
        "checksum_sha256": sha256(artifact.read_bytes()).hexdigest(),
        "sample_count": 32,
        "horizon": 20,
        "feature_count": 6,
    }


def _commit(repository, job, tmp_path: Path, *, owner: str = "worker-1"):
    return repository.commit_completed_forecast(
        job_id=job["id"],
        expected_status="running",
        expected_version=job["transition_version"],
        lease_owner=owner,
        output_descriptor=_descriptor(tmp_path),
        immutable_record={
            "instrument_id": "instrument-600000",
            "horizon": 20,
            "catalog_id": "kronos-mini",
            "input_fingerprint": "a" * 64,
            "sample_count": 32,
            "source_revision": "67b630e67f6a18c9e9be918d9b4337c960db1e9a",
            "model_revision": "f4e68697d9d5aed55cef5c96aabc3376bcad9f81",
            "tokenizer_revision": "26966d0035065a0cae0ebad7af8ece35bc1fb51c",
        },
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


def _runner(tmp_path: Path, **overrides):
    from app.forecast.runner import ForecastRunner, ForecastRunnerLimits
    repository = _repository(tmp_path)
    boundaries = {
        "reauthorize": CountingBoundary(),
        "catalog_revalidate": CountingBoundary(),
        "input_revalidate": CountingBoundary(),
        "worker": CountingBoundary(),
        "artifact_verify": CountingBoundary(),
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
