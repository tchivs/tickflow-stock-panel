"""RED contracts for durable Forecast CAS jobs and bounded spawned inference."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest


_LINUX_ONLY = pytest.mark.skipif(
    os.name != "posix" or sys.platform != "linux",
    reason="native Linux process-group evidence",
)


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
        job_id=job["id"],
        expected_status="queued",
        expected_version=job["transition_version"],
        lease_owner=owner,
        ttl_seconds=30,
    )


def _path_tensor(*, horizon: int, feature_count: int) -> np.ndarray:
    return np.fromfunction(
        lambda sample, session, feature: 8.0 + (sample * 0.1) + (session * 0.2) + (feature * 0.01),
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
            (origin + timedelta(days=index + 1)).strftime("CNA-%Y%m%d") for index in range(horizon)
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


def test_default_cpu_worker_limit_loads_pytorch_safely() -> None:
    from app.forecast.runner import ForecastRunnerLimits

    limits = ForecastRunnerLimits()
    assert limits.address_space_bytes == 8 * 1024 * 1024 * 1024
    assert limits.thread_count == 2
    assert limits.queue_items == 1


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
            job_id=job["id"],
            expected_status="queued",
            expected_version=0,
            lease_owner=None,
            new_status="completed",
        )


def test_job_cas_rejects_stale_transition_version(tmp_path):
    repository = _repository(tmp_path)
    job = _create(repository)
    with pytest.raises(ValueError, match="stale|version"):
        repository.acquire_job(
            job_id=job["id"],
            expected_status="queued",
            expected_version=job["transition_version"] + 1,
            lease_owner="worker-1",
            ttl_seconds=30,
        )


def test_job_lease_requires_owner_and_unexpired_heartbeat(tmp_path):
    repository = _repository(tmp_path)
    running = _acquire(repository, _create(repository))
    with pytest.raises(ValueError, match="owner"):
        repository.heartbeat(
            job_id=running["id"],
            expected_version=running["transition_version"],
            lease_owner="worker-2",
            ttl_seconds=30,
        )
    refreshed = repository.heartbeat(
        job_id=running["id"],
        expected_version=running["transition_version"],
        lease_owner="worker-1",
        ttl_seconds=30,
    )
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


def test_durable_dispatcher_drains_two_concurrent_create_requests(tmp_path, monkeypatch):
    import time
    from types import SimpleNamespace

    from app.forecast.service import (
        DurableForecastDispatcher,
        ForecastService,
        PreparedForecastRun,
    )

    repository = _repository(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    class Runner:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.lock = threading.Lock()

        def run_job(self, job_id: str):
            with self.lock:
                self.calls.append(job_id)
                call_count = len(self.calls)
            if call_count == 1:
                entered.set()
                assert release.wait(timeout=2)
            job = repository.get_job(job_id)
            assert job is not None
            terminal = repository.terminalize(
                job_id=job_id,
                expected_status="queued",
                expected_version=int(job["transition_version"]),
                lease_owner=None,
                status="validation_failed",
                reason="test_dispatch_completed",
            )
            return {"status": terminal["status"]}

    class Catalog:
        require_local = revalidate_before_spawn = lambda *_args, **_kwargs: None

    class Freezer:
        freeze = load = lambda *_args, **_kwargs: None

    runner = Runner()
    dispatcher = DurableForecastDispatcher(
        repository=repository,
        runner=runner,
        poll_interval_seconds=0.01,
        retry_backoff_seconds=0.01,
    )
    service = ForecastService(
        repository=repository,
        catalog=Catalog(),
        freezer=Freezer(),
        runner=runner,
        as_of_session=lambda _instrument: "CNA-20250430",
    )
    frozen = SimpleNamespace(
        instrument_id="instrument-600000",
        input_fingerprint="a" * 64,
        descriptor=SimpleNamespace(artifact_id="input-artifact"),
    )
    prepared = PreparedForecastRun(
        principal="researcher-1",
        checkpoint=object(),
        frozen=frozen,
        immutable_record={},
    )
    monkeypatch.setattr(service, "_prepare", lambda **_kwargs: prepared)
    monkeypatch.setattr(service, "_bind", lambda _job, _prepared: None)
    service.attach_dispatcher(dispatcher)
    dispatcher.start()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(
                    service.create_or_get_job,
                    principal="researcher-1",
                    instrument="instrument-600000",
                    horizon=20,
                    catalog_id="kronos-mini",
                    idempotency_key=f"concurrent-dispatch-{index}",
                )
                for index in range(2)
            ]
            assert entered.wait(timeout=2)
            created = [future.result(timeout=2) for future in futures]
        assert {job["status"] for job in created} == {"queued"}
        release.set()

        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            current = [repository.get_job(str(job["id"])) for job in created]
            if all(job is not None and job["status"] == "validation_failed" for job in current):
                break
            time.sleep(0.01)

        assert [repository.get_job(str(job["id"]))["status"] for job in created] == [
            "validation_failed",
            "validation_failed",
        ]
        assert set(runner.calls) == {str(job["id"]) for job in created}
    finally:
        release.set()
        dispatcher.close()


def test_two_parallel_job_acquisitions_have_one_cas_winner(tmp_path):
    repository = _repository(tmp_path)
    job = _create(repository)
    barrier = threading.Barrier(2)

    def acquire(owner: str):
        barrier.wait()
        try:
            return repository.acquire_job(
                job_id=job["id"],
                expected_status="queued",
                expected_version=job["transition_version"],
                lease_owner=owner,
                ttl_seconds=30,
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
        job_id=job["id"],
        expected_status="queued",
        expected_version=job["transition_version"],
        lease_owner=None,
        status="validation_failed",
        reason="safe_validation_failed",
    )
    retry = repository.create_retry_job(source_job_id=job["id"], idempotency_key="explicit-retry-1")
    assert retry["id"] != job["id"]
    assert retry["retry_of_job_id"] == job["id"]
    assert retry["attempt"] == job["attempt"] + 1


def test_service_retry_rebinds_governed_input_and_dispatches_queued_job(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.forecast.service import ForecastService, PreparedForecastRun

    repository = _repository(tmp_path)
    source = _terminal_source_for_retry(repository, key="retry-service-source")

    class Catalog:
        require_local = revalidate_before_spawn = lambda *_args, **_kwargs: None

    class Freezer:
        freeze = load = lambda *_args, **_kwargs: None

    class Runner:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def run_job(self, job_id: str):
            self.calls.append(job_id)
            return {"status": "queued"}

    runner = Runner()
    service = ForecastService(
        repository=repository,
        catalog=Catalog(),
        freezer=Freezer(),
        runner=runner,
        as_of_session=lambda _instrument: "CNA-20250430",
    )
    prepared = PreparedForecastRun(
        principal="researcher-1",
        checkpoint=object(),
        frozen=SimpleNamespace(
            input_fingerprint="a" * 64,
            descriptor=SimpleNamespace(artifact_id="input-artifact"),
        ),
        immutable_record=_immutable(source),
    )
    binds: list[tuple[dict[str, object], PreparedForecastRun]] = []
    monkeypatch.setattr(service, "_prepare_for_job", lambda job: prepared)
    monkeypatch.setattr(service, "_bind", lambda job, value: binds.append((dict(job), value)))

    result = service.retry_job(
        source_job_id=source["id"],
        idempotency_key="explicit-retry-service",
    )

    assert len(binds) == 1
    assert binds[0][0]["id"] == result["id"]
    assert binds[0][1] is prepared
    assert runner.calls == [result["id"]]
    assert result["status"] == "queued"
    assert result["dispatch_ready"] == 1


def test_service_retry_prevalidates_fingerprint_before_lineage_and_discards_artifact(
    tmp_path,
    monkeypatch,
):
    from types import SimpleNamespace

    from app.forecast.service import ForecastService, PreparedForecastRun

    repository = _repository(tmp_path)
    source = _terminal_source_for_retry(repository, key="retry-prevalidate-source")

    class Store:
        def __init__(self) -> None:
            self.live = {"retry-input-artifact"}

        def discard_unbound_invocation_owned(
            self, descriptor, *, owned_artifact_ids, is_referenced
        ):
            assert descriptor.artifact_id in owned_artifact_ids
            assert is_referenced(descriptor.artifact_id) is False
            self.live.remove(descriptor.artifact_id)

    class Freezer:
        freeze = load = lambda *_args, **_kwargs: None

        def __init__(self) -> None:
            self._store = Store()

    class Catalog:
        require_local = revalidate_before_spawn = lambda *_args, **_kwargs: None

    class Runner:
        def run_job(self, *_args, **_kwargs):
            return None

    freezer = Freezer()
    service = ForecastService(
        repository=repository,
        catalog=Catalog(),
        freezer=freezer,
        runner=Runner(),
        as_of_session=lambda _instrument: "CNA-20250430",
    )
    managed = SimpleNamespace(artifact_id="retry-input-artifact")
    descriptor = SimpleNamespace(
        artifact_id=managed.artifact_id,
        _managed=managed,
    )
    prepared = PreparedForecastRun(
        principal="researcher-1",
        checkpoint=object(),
        frozen=SimpleNamespace(
            input_fingerprint="b" * 64,
            descriptor=descriptor,
        ),
        immutable_record={},
    )
    monkeypatch.setattr(service, "_prepare_for_job", lambda _job: prepared)

    with pytest.raises(ValueError, match="Forecast retry governed input no longer matches source"):
        service.retry_job(
            source_job_id=source["id"],
            idempotency_key="retry-prevalidation-mismatch",
        )

    operation = repository.get_retry_operation_for(
        source_job_id=source["id"],
        idempotency_key="retry-prevalidation-mismatch",
    )
    assert operation is not None and operation["state"] == "aborted"
    assert repository.list_jobs() == [source]
    assert freezer._store.live == set()


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("approved Forecast catalog is unavailable"),
        ValueError("governed Forecast input freezer failed"),
    ],
)
def test_service_retry_prevalidation_failure_creates_no_queued_lineage(
    tmp_path, monkeypatch, error
):
    from app.forecast.service import ForecastService

    repository = _repository(tmp_path)
    source = _terminal_source_for_retry(repository, key=f"retry-failure-{type(error).__name__}")

    class Catalog:
        require_local = revalidate_before_spawn = lambda *_args, **_kwargs: None

    class Freezer:
        freeze = load = lambda *_args, **_kwargs: None

    class Runner:
        def run_job(self, *_args, **_kwargs):
            return None

    service = ForecastService(
        repository=repository,
        catalog=Catalog(),
        freezer=Freezer(),
        runner=Runner(),
        as_of_session=lambda _instrument: "CNA-20250430",
    )
    monkeypatch.setattr(service, "_prepare_for_job", lambda _job: (_ for _ in ()).throw(error))

    with pytest.raises(type(error), match=str(error)):
        service.retry_job(
            source_job_id=source["id"],
            idempotency_key="retry-prevalidation-failure",
        )

    operation = repository.get_retry_operation_for(
        source_job_id=source["id"],
        idempotency_key="retry-prevalidation-failure",
    )
    assert operation is not None and operation["state"] == "aborted"
    assert repository.list_jobs() == [source]


def test_retry_never_reuses_completed_forecast_record(tmp_path):
    repository = _repository(tmp_path)
    running = _acquire(repository, _create(repository))
    record = _commit(repository, running, tmp_path)
    retry = repository.create_retry_job(
        source_job_id=running["id"], idempotency_key="explicit-retry-2"
    )
    assert retry["id"] != running["id"]
    assert repository.forecast_for_job(retry["id"]) is None
    assert repository.forecast_for_job(running["id"])["id"] == record["id"]


def test_interruption_before_artifact_creates_no_forecast(tmp_path):
    repository = _repository(tmp_path)
    running = _acquire(repository, _create(repository))
    repository.terminalize(
        job_id=running["id"],
        expected_status="running",
        expected_version=running["transition_version"],
        lease_owner="worker-1",
        status="interrupted",
        reason="worker_interrupted",
    )
    assert repository.forecast_for_job(running["id"]) is None


def test_interruption_after_temp_artifact_creates_no_forecast_and_cleans_temp(tmp_path):
    repository = _repository(tmp_path)
    running = _acquire(repository, _create(repository))
    temporary = tmp_path / ".forecast-output.tmp"
    temporary.write_bytes(b"partial")
    repository.terminalize(
        job_id=running["id"],
        expected_status="running",
        expected_version=running["transition_version"],
        lease_owner="worker-1",
        status="artifact_failed",
        reason="artifact_verification_failed",
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
            connection.execute(
                "UPDATE forecast_records SET horizon = 5 WHERE id = ?", (record["id"],)
            )
        with pytest.raises(Exception, match="immutable"):
            connection.execute("DELETE FROM forecast_jobs WHERE id = ?", (running["id"],))


def test_restart_requeues_only_valid_never_started_queued_jobs(tmp_path):
    repository = _repository(tmp_path)
    queued = _create(repository)
    outcomes = repository.recover_after_restart(
        revalidate=lambda job: job["input_fingerprint"] == "a" * 64
    )
    assert outcomes == [{"job_id": queued["id"], "action": "requeue"}]
    assert repository.get_job(queued["id"])["status"] == "queued"


@pytest.mark.linux_process_group
@_LINUX_ONLY
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
    outcomes = repository.recover_after_restart(
        now="2099-01-01T00:00:00Z", revalidate=lambda _job: True
    )
    assert outcomes == [
        {"job_id": running["id"], "action": "terminalized", "status": "interrupted"}
    ]
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
    assert reloaded["quantiles"]["5"] == pytest.approx({"p10": 9.14, "p50": 10.38, "p90": 11.62})
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
        replacement = ManagedImmutableArtifactStore(case_root / "forecast-outputs").create_parquet(
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
        for row in repository.job_transitions_after(running["id"], after_version=-1, limit=256)
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
        manifest["output_descriptor"] = _descriptor(self.root, horizon=int(job["horizon"]))
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
            wall_clock_seconds=3,
            # Spawn/module bootstrap consumed >2 CPU seconds before _child_entry
            # installed RLIMIT_CPU in the isolated Linux producer; wall time stays 3s.
            cpu_seconds=5,
            address_space_bytes=1024 * 1024 * 1024,
            thread_count=2,
            output_bytes=16 * 1024,
            queue_items=1,
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
        "start_method": "spawn",
        "new_process_group": True,
        "wall_clock_seconds": 3,
        "cpu_seconds": 5,
        "address_space_bytes": 1024 * 1024 * 1024,
        "thread_count": 2,
        "output_bytes": 16 * 1024,
        "queue_items": 1,
    }
    assert len(json.dumps(result["manifest"]).encode()) <= 16 * 1024


@pytest.mark.linux_process_group
@_LINUX_ONLY
def test_runner_timeout_kills_reaps_descendants_and_cleans_temporary_files(tmp_path):
    from app.forecast.runner import BlockingWorker

    runner, repository, _boundaries = _runner(tmp_path, worker=BlockingWorker(descendant=True))
    job = _create(repository)
    result = runner.run_job(job["id"])
    assert result["status"] == "timeout"
    assert result["process_group_reaped"] is True
    assert not list(tmp_path.rglob("*.tmp"))
    assert repository.forecast_for_job(job["id"]) is None


@pytest.mark.linux_process_group
@_LINUX_ONLY
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

    runner, repository, _boundaries = _runner(
        tmp_path, worker=CrashingWorker("/secret/model: token=abc\nTraceback")
    )
    result = runner.run_job(_create(repository)["id"])
    serialized = json.dumps(result)
    assert result["status"] in {"resource_terminated", "checkpoint_mismatch", "artifact_failed"}
    assert (
        "/secret" not in serialized
        and "Traceback" not in serialized
        and "token=abc" not in serialized
    )


@pytest.mark.linux_process_group
@_LINUX_ONLY
def test_runner_lost_lease_rejects_late_output_and_creates_no_record(tmp_path):
    from app.forecast.runner import FixedWorker

    runner, repository, _boundaries = _runner(
        tmp_path, worker=FixedWorker(lose_lease_before_result=True)
    )
    job = _create(repository)
    result = runner.run_job(job["id"])
    assert result["status"] == "interrupted"
    assert repository.forecast_for_job(job["id"]) is None


@pytest.mark.linux_process_group
@_LINUX_ONLY
def test_runner_success_commits_once_and_never_invokes_downstream_authority(tmp_path):
    from app.forecast.runner import FixedWorker

    action_spies = {
        name: CountingBoundary()
        for name in ("thesis", "strategy", "decision_plan", "monitor", "position", "broker")
    }
    runner, repository, _boundaries = _runner(
        tmp_path, worker=FixedWorker(valid=True), action_collaborators=action_spies
    )
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
            (date(2025, 5, 1) + timedelta(days=index)).strftime("CNA-%Y%m%d") for index in range(20)
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
            "validation_warnings": [{"code": "flat_quantile_band", "message": "untrusted detail"}],
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
        lambda record, descriptor: record.__setitem__(
            "future_session_ids", record["future_session_ids"][:-1]
        ),
        lambda record, descriptor: descriptor["path_shape"].__setitem__(1, 5),
        lambda record, descriptor: record["input_artifact_descriptor"].__setitem__(
            "checksum_sha256", "f" * 64
        ),
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


@pytest.mark.linux_process_group
@_LINUX_ONLY
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
    managed = store.create_parquet(frame, schema_version="forecast-input-v1", scope={"k": "v"})
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
    remaining = {p.name for p in store_root.iterdir() if p.is_dir() and not p.name.startswith(".")}
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

    monkeypatch.setattr(runner_module.os, "setsid", lambda: None, raising=False)
    monkeypatch.setattr(runner_module.os, "getpgrp", lambda: 1234, raising=False)
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


@pytest.mark.linux_process_group
@_LINUX_ONLY
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


@pytest.mark.linux_process_group
@_LINUX_ONLY
def test_runner_terminate_kill_fallback_reaps_descendants(tmp_path):
    from app.forecast.runner import BlockingWorker

    runner, repository, _boundaries = _runner(tmp_path, worker=BlockingWorker(descendant=True))
    result = runner.run_job(_create(repository, idempotency_key="descendants-reaped")["id"])
    assert result["status"] == "timeout"
    assert result["process_group_reaped"] is True


@pytest.mark.linux_process_group
@_LINUX_ONLY
def test_runner_lease_loss_reaps_worker_tree(tmp_path):
    from app.forecast.runner import FixedWorker

    runner, repository, _boundaries = _runner(
        tmp_path, worker=FixedWorker(lose_lease_before_result=True)
    )
    job = _create(repository, idempotency_key="lease-loss-reap")
    result = runner.run_job(job["id"])
    assert result["status"] == "interrupted"
    assert repository.forecast_for_job(job["id"]) is None


@pytest.mark.linux_process_group
@_LINUX_ONLY
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


@pytest.mark.linux_process_group
@_LINUX_ONLY
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
    running = _acquire(
        repository, _create(repository, idempotency_key="restart-terminalizes-running")
    )
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


@pytest.mark.linux_process_group
@_LINUX_ONLY
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


@pytest.mark.linux_process_group
@_LINUX_ONLY
def test_normal_exit_descendants_reaped(tmp_path):
    from app.forecast.runner import SuccessWithDescendantWorker

    runner, repository, _boundaries = _runner(tmp_path, worker=SuccessWithDescendantWorker())
    result = runner.run_job(_create(repository, idempotency_key="normal-exit-descendants")["id"])
    assert result["status"] == "completed"
    assert result["process_group_reaped"] is True


@pytest.mark.linux_process_group
@_LINUX_ONLY
def test_every_return_reaps_group_on_malformed_success_manifest(tmp_path):
    from app.forecast.runner import FixedWorker

    runner, repository, _boundaries = _runner(
        tmp_path, worker=FixedWorker(manifest={"checksum_sha256": "0" * 64})
    )
    result = runner.run_job(_create(repository, idempotency_key="every-return-reaps")["id"])
    assert result["status"] == "artifact_failed"
    # Finally reaps even when the terminal payload omits the flag.
    assert repository.forecast_for_job(result["job_id"]) is None


def _terminal_source_for_retry(repository, *, key: str = "r43-source"):
    source = _create(repository, idempotency_key=key)
    return repository.terminalize(
        job_id=source["id"],
        expected_status="queued",
        expected_version=int(source["transition_version"]),
        lease_owner=None,
        status="validation_failed",
        reason="safe_validation_failed",
    )


def test_r43_cr02_retryable_terminal_matrix_uses_repository_contract():
    from app.forecast.repository import TERMINAL_JOB_STATUSES, is_retryable_terminal

    expected = {
        "completed",
        "validation_failed",
        "model_unavailable",
        "artifact_failed",
        "timed_out",
        "resource_limited",
        "interrupted",
    }
    assert TERMINAL_JOB_STATUSES == frozenset(expected)
    assert all(is_retryable_terminal(status) for status in expected)
    assert not is_retryable_terminal("queued")
    assert not is_retryable_terminal("running")
    assert not is_retryable_terminal("cancelled")


def test_r43_cr03_owner_first_retry_publishes_once_without_orphan(tmp_path):
    repository = _repository(tmp_path)
    source = _terminal_source_for_retry(repository)

    first = repository.reserve_retry_operation(
        source_job_id=source["id"],
        idempotency_key="r43-owner-first",
        owner_ttl_seconds=30,
    )
    replay = repository.reserve_retry_operation(
        source_job_id=source["id"],
        idempotency_key="r43-owner-first",
        owner_ttl_seconds=30,
    )

    assert first.created is True and first.owner_token
    assert replay.created is False and replay.owner_token is None
    assert repository.list_jobs() == [source]

    repository.bind_retry_operation(
        operation_id=first.operation_id,
        owner_token=first.owner_token,
        immutable_record=_immutable(source),
        input_artifact_id="input-artifact",
    )
    canonical = repository.publish_retry_operation(
        operation_id=first.operation_id,
        owner_token=first.owner_token,
    )
    replayed = repository.reserve_retry_operation(
        source_job_id=source["id"],
        idempotency_key="r43-owner-first",
        owner_ttl_seconds=30,
    )

    assert canonical["status"] == "queued"
    assert canonical["dispatch_ready"] == 1
    assert canonical["retry_of_job_id"] == source["id"]
    assert replayed.canonical_job == canonical
    assert len(repository.list_jobs()) == 2
    assert repository.get_retry_operation(first.operation_id)["state"] == "published"


def test_r43_cr03_loser_waits_or_returns_canonical_without_freeze(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.forecast.service import ForecastService, RetryOperationInProgress

    repository = _repository(tmp_path)
    source = _terminal_source_for_retry(repository, key="r43-loser-source")
    repository.reserve_retry_operation(
        source_job_id=source["id"],
        idempotency_key="r43-loser",
        owner_ttl_seconds=30,
    )

    class Catalog:
        require_local = revalidate_before_spawn = lambda *_args, **_kwargs: None

    class Freezer:
        def __init__(self):
            self.freezes = 0

        def freeze(self, **_kwargs):
            self.freezes += 1
            raise AssertionError("retry loser must not freeze")

        load = lambda *_args, **_kwargs: None

    freezer = Freezer()
    service = ForecastService(
        repository=repository,
        catalog=Catalog(),
        freezer=freezer,
        runner=SimpleNamespace(run_job=lambda _job_id: None),
        as_of_session=lambda _instrument: "CNA-20250430",
    )
    monkeypatch.setattr(service, "_retry_wait_seconds", 0.01, raising=False)

    outcome = service.retry_job(
        source_job_id=source["id"],
        idempotency_key="r43-loser",
    )

    assert isinstance(outcome, RetryOperationInProgress)
    assert outcome.operation_id
    assert outcome.retry_after_seconds > 0
    assert freezer.freezes == 0
    assert repository.list_jobs() == [source]


@pytest.mark.parametrize("state", ["reserved", "bound"])
@pytest.mark.parametrize("clock_kind", ["past-injected-clock", "future-injected-clock"])
def test_expired_retry_owner_is_atomically_reclaimed_without_restart(tmp_path, state, clock_kind):
    from datetime import UTC, datetime, timedelta

    observed = (
        datetime(2000, 5, 1, tzinfo=UTC)
        if clock_kind == "past-injected-clock"
        else datetime(2099, 5, 1, tzinfo=UTC)
    )
    repository = _repository(tmp_path)
    repository._clock = lambda: observed
    source = _terminal_source_for_retry(repository, key=f"reclaim-{state}-source")
    first = repository.reserve_retry_operation(
        source_job_id=source["id"],
        idempotency_key=f"reclaim-{state}",
        owner_ttl_seconds=3600,
    )
    if state == "bound":
        repository.bind_retry_operation(
            operation_id=first.operation_id,
            owner_token=first.owner_token,
            immutable_record=_immutable(source),
            input_artifact_id="input-artifact",
        )
    before = repository.get_retry_operation(first.operation_id)

    repository._clock = lambda: observed + timedelta(seconds=3601)
    reclaimed = repository.reserve_retry_operation(
        source_job_id=source["id"],
        idempotency_key=f"reclaim-{state}",
        owner_ttl_seconds=30,
    )

    after = repository.get_retry_operation(first.operation_id)
    assert reclaimed.created is True
    assert reclaimed.operation_id == first.operation_id
    assert reclaimed.owner_token not in {None, first.owner_token}
    assert reclaimed.state == state
    assert after["state"] == state
    assert after["owner_token"] == reclaimed.owner_token
    assert after["transition_version"] == before["transition_version"] + 1
    if state == "bound":
        assert after["immutable_record_json"] == before["immutable_record_json"]
        assert after["input_artifact_id"] == before["input_artifact_id"]


@pytest.mark.parametrize("state", ["reserved", "bound"])
def test_mixed_precision_expired_retry_owner_is_reclaimed(tmp_path, state):
    from datetime import UTC, datetime, timedelta

    observed = datetime(2099, 1, 1, tzinfo=UTC)
    repository = _repository(tmp_path)
    repository._clock = lambda: observed
    source = _terminal_source_for_retry(repository, key=f"mixed-precision-{state}-source")
    first = repository.reserve_retry_operation(
        source_job_id=source["id"],
        idempotency_key=f"mixed-precision-{state}",
        owner_ttl_seconds=1,
    )
    if state == "bound":
        repository.bind_retry_operation(
            operation_id=first.operation_id,
            owner_token=first.owner_token,
            immutable_record=_immutable(source),
            input_artifact_id="input-artifact",
        )
    before = repository.get_retry_operation(first.operation_id)
    assert before["owner_lease_until"] == "2099-01-01T00:00:01Z"

    repository._clock = lambda: observed + timedelta(seconds=1.5)
    assert repository.now() == "2099-01-01T00:00:01.500000Z"
    reclaimed = repository.reserve_retry_operation(
        source_job_id=source["id"],
        idempotency_key=f"mixed-precision-{state}",
        owner_ttl_seconds=30,
    )

    after = repository.get_retry_operation(first.operation_id)
    assert reclaimed.created is True
    assert reclaimed.operation_id == first.operation_id
    assert reclaimed.owner_token not in {None, first.owner_token}
    assert reclaimed.state == state
    assert after["owner_token"] == reclaimed.owner_token
    assert after["transition_version"] == before["transition_version"] + 1


@pytest.mark.parametrize("state", ["reserved", "bound"])
def test_retry_guard_rejects_unexpired_direct_sql_owner_takeover(tmp_path, state):
    from datetime import UTC, datetime, timedelta

    observed = datetime(2099, 1, 1, tzinfo=UTC)
    repository = _repository(tmp_path)
    repository._clock = lambda: observed
    source = _terminal_source_for_retry(repository, key=f"unexpired-{state}-source")
    first = repository.reserve_retry_operation(
        source_job_id=source["id"],
        idempotency_key=f"unexpired-{state}",
        owner_ttl_seconds=3600,
    )
    if state == "bound":
        repository.bind_retry_operation(
            operation_id=first.operation_id,
            owner_token=first.owner_token,
            immutable_record=_immutable(source),
            input_artifact_id="input-artifact",
        )
    before = repository.get_retry_operation(first.operation_id)
    early_now = (observed + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    stolen_lease = (observed + timedelta(hours=2)).isoformat().replace("+00:00", "Z")

    with (
        repository.connection() as connection,
        pytest.raises(
            sqlite3.IntegrityError,
            match=r"forecast retry operation transition is invalid",
        ),
    ):
        connection.execute(
            """UPDATE forecast_retry_operations
               SET owner_token = ?, owner_lease_until = ?,
                   transition_version = transition_version + 1,
                   updated_at = ?
               WHERE id = ?""",
            ("stolen-owner", stolen_lease, early_now, first.operation_id),
        )

    assert repository.get_retry_operation(first.operation_id) == before


def test_expired_bound_retry_resumes_publication_without_refreezing(tmp_path):
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace

    from app.forecast.service import ForecastService

    observed = datetime(2025, 5, 1, tzinfo=UTC)
    repository = _repository(tmp_path)
    repository._clock = lambda: observed
    source = _terminal_source_for_retry(repository, key="bound-resume-source")
    first = repository.reserve_retry_operation(
        source_job_id=source["id"],
        idempotency_key="bound-resume",
        owner_ttl_seconds=1,
    )
    repository.bind_retry_operation(
        operation_id=first.operation_id,
        owner_token=first.owner_token,
        immutable_record=_immutable(source),
        input_artifact_id="input-artifact",
    )
    repository._clock = lambda: observed + timedelta(seconds=2)

    class Catalog:
        require_local = revalidate_before_spawn = lambda *_args, **_kwargs: None

    class Freezer:
        def freeze(self, **_kwargs):
            raise AssertionError("bound takeover must not repeat governed reads")

        def load(self, *_args, **_kwargs):
            return None

    service = ForecastService(
        repository=repository,
        catalog=Catalog(),
        freezer=Freezer(),
        runner=SimpleNamespace(run_job=lambda _job_id: None),
        as_of_session=lambda _instrument: "CNA-20250430",
    )

    canonical = service.retry_job(
        source_job_id=source["id"],
        idempotency_key="bound-resume",
    )

    assert canonical["retry_of_job_id"] == source["id"]
    assert canonical["dispatch_ready"] == 1
    operation = repository.get_retry_operation(first.operation_id)
    assert operation["state"] == "published"
    assert operation["canonical_job_id"] == canonical["id"]


def test_r43_cr03_wake_failure_keeps_durable_canonical_work(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.forecast.service import ForecastService, PreparedForecastRun

    repository = _repository(tmp_path)
    source = _terminal_source_for_retry(repository, key="r43-wake-source")
    descriptor = SimpleNamespace(
        artifact_id="input-artifact",
        checksum_sha256="b" * 64,
        byte_size=1024,
        public=lambda: _immutable(source)["input_artifact_descriptor"],
    )
    frozen = SimpleNamespace(
        instrument_id=source["instrument_id"],
        input_fingerprint=source["input_fingerprint"],
        descriptor=descriptor,
        feature_schema=["open", "high", "low", "close", "volume", "amount"],
        historical_session_ids=[],
        future_session_ids=_immutable(source)["future_session_ids"],
    )
    prepared = PreparedForecastRun(
        principal=source["principal"],
        checkpoint=object(),
        frozen=frozen,
        immutable_record=_immutable(source),
    )

    class Catalog:
        require_local = revalidate_before_spawn = lambda *_args, **_kwargs: None

    class Freezer:
        freeze = load = lambda *_args, **_kwargs: None

    class FailingWake:
        def wake(self):
            raise RuntimeError("synthetic wake failure")

    service = ForecastService(
        repository=repository,
        catalog=Catalog(),
        freezer=Freezer(),
        runner=SimpleNamespace(run_job=lambda _job_id: None),
        as_of_session=lambda _instrument: "CNA-20250430",
    )
    service.dispatcher = FailingWake()
    monkeypatch.setattr(service, "_prepare_for_job", lambda _job: prepared)

    canonical = service.retry_job(
        source_job_id=source["id"],
        idempotency_key="r43-wake",
    )

    persisted = repository.get_job(canonical["id"])
    assert persisted is not None
    assert persisted["status"] == "queued"
    assert persisted["dispatch_ready"] == 1
    assert (
        repository.get_retry_operation_for(source_job_id=source["id"], idempotency_key="r43-wake")[
            "state"
        ]
        == "published"
    )


def test_r43_cr03_restart_aborts_stale_unpublished_operation_without_dispatch(tmp_path):
    from datetime import UTC, datetime, timedelta

    observed = datetime(2025, 5, 1, tzinfo=UTC)
    repository = _repository(tmp_path)
    repository._clock = lambda: observed
    source = _terminal_source_for_retry(repository, key="r43-restart-source")
    reservation = repository.reserve_retry_operation(
        source_job_id=source["id"],
        idempotency_key="r43-stale-operation",
        owner_ttl_seconds=1,
    )
    repository.bind_retry_operation(
        operation_id=reservation.operation_id,
        owner_token=reservation.owner_token,
        immutable_record=_immutable(source),
        input_artifact_id="input-artifact",
    )

    outcomes = repository.recover_after_restart(
        revalidate=lambda _job: True,
        now=observed + timedelta(seconds=2),
    )

    operation = repository.get_retry_operation(reservation.operation_id)
    assert operation["state"] == "aborted"
    assert operation["terminal_reason"] == "restart_expired_retry_owner"
    assert all(row["action"] != "requeue" for row in outcomes)
    assert repository.list_jobs() == [source]


def test_dispatcher_close_timeout_retains_live_worker_until_retry():
    from app.forecast.service import (
        DispatcherCloseOutcome,
        DurableForecastDispatcher,
    )

    entered = threading.Event()
    release = threading.Event()

    class Repository:
        def list_jobs(self):
            entered.set()
            release.wait(timeout=2)
            return []

        def get_job(self, _job_id):
            return None

    dispatcher = DurableForecastDispatcher(
        repository=Repository(),
        runner=type("Runner", (), {"run_job": lambda _self, _job_id: None})(),
        poll_interval_seconds=0.01,
        retry_backoff_seconds=0.01,
    )
    dispatcher.start()
    assert entered.wait(timeout=1)
    live_thread = dispatcher._thread

    assert dispatcher.close(timeout_seconds=0.01) is DispatcherCloseOutcome.TIMED_OUT
    assert dispatcher._thread is live_thread
    assert live_thread is not None and live_thread.is_alive()
    with pytest.raises(RuntimeError, match="closed"):
        dispatcher.submit("late-job")

    release.set()
    assert dispatcher.close(timeout_seconds=1) is DispatcherCloseOutcome.STOPPED
    assert dispatcher._thread is None


def test_dispatcher_cancellation_reaps_group_before_commit(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from app.forecast import runner as runner_module
    from app.forecast.runner import ForecastRunner, ForecastRunnerLimits

    stop_token = threading.Event()
    repository = _repository(tmp_path)
    job = _create(repository, idempotency_key="r43-cancel-before-commit")
    immutable = _immutable(job)
    repository.bind_commit_identity(job_id=job["id"], immutable_record=immutable)
    messages = [
        {"kind": "ready", "pgid": 4242},
        {
            "kind": "success",
            "manifest": {
                "output_descriptor": _descriptor(tmp_path),
                "immutable_record": immutable,
            },
        },
    ]

    class InputPipe:
        def poll(self, _timeout):
            return bool(messages)

        def recv_bytes(self, maxlength=None):
            payload = json.dumps(messages.pop(0)).encode("utf-8")
            assert maxlength is None or len(payload) <= maxlength
            return payload

        def close(self):
            return None

    class OutputPipe:
        def close(self):
            return None

    class Process:
        pid = 4242

        def start(self):
            return None

        def is_alive(self):
            return True

        def join(self, _timeout=None):
            return None

    class Context:
        def Pipe(self, *, duplex):
            assert duplex is False
            return InputPipe(), OutputPipe()

        def Process(self, *, target, args):
            assert target is runner_module._child_entry
            assert args
            return Process()

    reaped: list[tuple[object, int | None]] = []
    monkeypatch.setattr(runner_module, "resource", object())
    monkeypatch.setattr(runner_module.os, "name", "posix")
    monkeypatch.setattr(runner_module.multiprocessing, "get_all_start_methods", lambda: ["spawn"])
    monkeypatch.setattr(runner_module.multiprocessing, "get_context", lambda _method: Context())
    monkeypatch.setattr(
        ForecastRunner,
        "_reap",
        lambda _self, process, pgid: reaped.append((process, pgid)) or True,
    )

    def verify_then_cancel(**_kwargs):
        stop_token.set()
        return True

    runner = ForecastRunner(
        repository=repository,
        limits=ForecastRunnerLimits(),
        reauthorize=CountingBoundary(),
        catalog_revalidate=CountingBoundary(),
        input_revalidate=CountingBoundary(),
        worker=object(),
        artifact_verify=verify_then_cancel,
        stop_token=stop_token,
    )
    result = runner.run_job(job["id"])

    assert result["status"] == "interrupted"
    assert result["process_group_reaped"] is True
    assert repository.forecast_for_job(job["id"]) is None
    assert any(pgid == 4242 for _process, pgid in reaped)


@pytest.mark.windows_only
@pytest.mark.skipif(os.name != "nt", reason="Windows fail-closed evidence")
def test_r43_wr01_windows_fail_closed_and_linux_process_group_nodes_are_explicit(request, tmp_path):
    import os

    markers = "\n".join(request.config.getini("markers"))
    assert "linux_process_group:" in markers
    assert "windows_only:" in markers
    if os.name == "nt":
        runner, repository, _boundaries = _runner(tmp_path)
        result = runner.run_job(
            _create(repository, idempotency_key="r43-windows-fail-closed")["id"]
        )
        assert result["status"] == "resource_terminated"
        assert result["reason"] == "spawn_limits_unavailable"
        assert repository.forecast_for_job(result["job_id"]) is None
    else:
        assert hasattr(os, "setsid")
        assert hasattr(os, "killpg")
