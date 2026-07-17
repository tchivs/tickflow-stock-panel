"""Focused Forecast API, path artifact, and progress transport contracts."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path

import numpy as np
import polars as pl
import pytest


def _path_tensor(*, horizon: int = 5, features: tuple[str, ...] = ("open", "close")) -> np.ndarray:
    return np.arange(32 * horizon * len(features), dtype=np.float64).reshape(
        32, horizon, len(features)
    )


def _write_paths(
    root: Path,
    *,
    values: np.ndarray | None = None,
    sessions: tuple[str, ...] = tuple(f"CNA-202505{day:02}" for day in range(1, 6)),
    features: tuple[str, ...] = ("open", "close"),
) -> tuple[dict[str, object], dict[str, object], Path]:
    tensor = _path_tensor(horizon=len(sessions), features=features) if values is None else values
    rows = [
        {
            "sample_index": sample_index,
            "horizon_index": horizon_index,
            "session_id": session_id,
            "feature": feature,
            "value": float(tensor[sample_index, horizon_index, feature_index]),
        }
        for sample_index in range(tensor.shape[0])
        for horizon_index, session_id in enumerate(sessions)
        for feature_index, feature in enumerate(features)
    ]
    target = root / "job-1" / "paths.parquet"
    target.parent.mkdir(parents=True)
    pl.DataFrame(rows).write_parquet(target)
    payload = target.read_bytes()
    descriptor: dict[str, object] = {
        "artifact_id": "forecast-job-1",
        "relative_path": "job-1/paths.parquet",
        "schema_version": "forecast-paths-v1",
        "byte_size": len(payload),
        "checksum_sha256": sha256(payload).hexdigest(),
        "sample_count": 32,
        "horizon": len(sessions),
        "feature_count": len(features),
    }
    record: dict[str, object] = {
        "output_artifact_descriptor": descriptor,
        "future_session_ids": list(sessions),
        "sample_count": 32,
        "horizon": len(sessions),
        "validation_warnings": ["bounded_warning"],
    }
    return record, descriptor, target


def test_distinct_complete_path_paging(tmp_path: Path) -> None:
    from app.forecast import projections
    from app.forecast.artifacts import ForecastPathReader

    record, _descriptor, _target = _write_paths(tmp_path)
    reader = ForecastPathReader(tmp_path)
    seen: list[int] = []
    expected_rows_per_path = 5 * 2
    for offset, limit in ((0, 12), (12, 12), (24, 12)):
        rows, total = reader.read_page(record=record, offset=offset, limit=limit)
        indexes = sorted({int(row["path_index"]) for row in rows})
        assert indexes == list(range(offset, min(offset + limit, 32)))
        assert len(rows) == len(indexes) * expected_rows_per_path
        assert all(row["warning_code"] == "bounded_warning" for row in rows)
        seen.extend(indexes)
        assert total == 32
        page = projections.path_page(rows, offset=offset, limit=limit, total=total)
        assert page["total"] == 32
        assert page["has_more"] is (offset + len(indexes) < 32)
        assert len(page["items"]) == len(rows)
    assert seen == list(range(32))


@pytest.mark.parametrize("corruption", ["duplicate", "incomplete", "out_of_range", "symlink"])
def test_corrupt_path_relation_fails_closed(tmp_path: Path, corruption: str) -> None:
    from app.forecast.artifacts import ForecastPathReader

    record, descriptor, target = _write_paths(tmp_path)
    frame = pl.read_parquet(target)
    if corruption == "duplicate":
        frame = pl.concat([frame, frame.head(1)])
    elif corruption == "incomplete":
        frame = frame.slice(1)
    elif corruption == "symlink":
        real_target = target.with_name("real-paths.parquet")
        target.rename(real_target)
        target.symlink_to(real_target.name)
    else:
        frame = frame.with_columns(
            pl.when(pl.int_range(pl.len()) == 0)
            .then(pl.lit(32))
            .otherwise(pl.col("sample_index"))
            .alias("sample_index")
        )
    if corruption != "symlink":
        frame.write_parquet(target)
    payload = target.read_bytes()
    descriptor["byte_size"] = len(payload)
    descriptor["checksum_sha256"] = sha256(payload).hexdigest()

    with pytest.raises(ValueError, match="relation|sample|complete|range|regular"):
        ForecastPathReader(tmp_path).read_page(record=record, offset=0, limit=12)


def test_path_quantile_consistency(tmp_path: Path) -> None:
    from app.forecast.artifacts import ForecastArtifactStore

    paths = _path_tensor()
    supplied = np.quantile(paths, q=(0.10, 0.50, 0.90), axis=0)
    store = ForecastArtifactStore.at(tmp_path)
    bundle = store.persist(
        paths=paths,
        quantiles=supplied,
        future_session_ids=[f"CNA-202505{day:02}" for day in range(1, 6)],
        feature_names=["open", "close"],
        scope={"forecast_id": "forecast-1"},
    )

    persisted = store.load_quantiles(bundle).sort(["quantile", "horizon_index", "feature"])
    expected = np.quantile(paths, q=(0.10, 0.50, 0.90), axis=0)
    by_label = {
        label: persisted.filter(pl.col("quantile") == label)
        .sort(["horizon_index", "feature"])["value"]
        .to_numpy()
        for label in ("P10", "P50", "P90")
    }
    feature_order = sorted(("open", "close"))
    for quantile_index, label in enumerate(("P10", "P50", "P90")):
        expected_values = np.asarray(
            [
                expected[quantile_index, horizon_index, ("open", "close").index(feature)]
                for horizon_index in range(5)
                for feature in feature_order
            ]
        )
        np.testing.assert_allclose(by_label[label], expected_values, rtol=0, atol=1e-12)


def test_quantile_divergence_rejected_before_artifact_commit(tmp_path: Path) -> None:
    from app.forecast.artifacts import ForecastArtifactStore

    paths = _path_tensor()
    divergent = np.quantile(paths, q=(0.10, 0.50, 0.90), axis=0)
    divergent[1, 0, 0] += 0.01
    store = ForecastArtifactStore.at(tmp_path)

    with pytest.raises(ValueError, match="quantile.*diverge"):
        store.persist(
            paths=paths,
            quantiles=divergent,
            future_session_ids=[f"CNA-202505{day:02}" for day in range(1, 6)],
            feature_names=["open", "close"],
            scope={"forecast_id": "forecast-1"},
        )
    assert list(tmp_path.iterdir()) == []


def test_record_scoped_calibration_refresh_never_scans_unrelated_forecasts() -> None:
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    from app.forecast.api import router

    class Scope:
        @staticmethod
        def allows(subject_kind: str, subject_key: str) -> bool:
            return (subject_kind, subject_key) == ("instrument", "600000.SH")

    class Repository:
        records = {
            "record-a": {
                "id": "record-a",
                "instrument_id": "600000.SH",
                "horizon": 20,
            },
            "record-b": {
                "id": "record-b",
                "instrument_id": "000001.SZ",
                "horizon": 60,
            },
        }

        def get_forecast(self, forecast_id: str):
            return self.records.get(forecast_id)

        @staticmethod
        def outcomes_for_forecast(_forecast_id: str):
            return []

        @staticmethod
        def calibration_facts_for_forecast(_forecast_id: str):
            return []

    class Scanner:
        def __init__(self) -> None:
            self.evaluated: list[tuple[str, int, str]] = []
            self.global_scans = 0

        def scan(self, **_kwargs):
            self.global_scans += 1
            raise AssertionError("record endpoint invoked the trusted global scanner path")

        def evaluate(self, *, forecast_id: str, horizon: int, as_of_session_id: str):
            self.evaluated.append((forecast_id, horizon, as_of_session_id))
            return {"status": "not_mature", "forecast_id": forecast_id, "horizon": horizon}

    app = FastAPI()
    app.include_router(router)
    app.state.forecast_repository = Repository()
    scanner = Scanner()
    app.state.forecast_maturity_scanner = scanner
    app.state.forecast_current_session = lambda: "CNA-20250530"
    app.state.resolve_forecast_subject_scope = lambda _request: Scope()

    @app.middleware("http")
    async def bind_principal(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.reviewer_principal = "server-principal"
        return await call_next(request)

    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/forecast/records/record-a/calibration", json={}
    )

    assert response.status_code == 200
    assert scanner.global_scans == 0
    assert scanner.evaluated == [
        ("record-a", 5, "CNA-20250530"),
        ("record-a", 20, "CNA-20250530"),
    ]


def _terminal_sse_repository(tmp_path: Path):
    from app.forecast.repository import ForecastRepository

    repository = ForecastRepository(tmp_path / "operational.db")
    repository.migrate()
    queued = repository.create_or_get_active_job(
        principal="server-principal",
        instrument_id="600000.SH",
        horizon=20,
        catalog_id="kronos-local",
        idempotency_key="sse-job",
        input_fingerprint="a" * 64,
    )
    running = repository.acquire_job(
        job_id=str(queued["id"]),
        expected_status="queued",
        expected_version=int(queued["transition_version"]),
        lease_owner="worker-sse",
        ttl_seconds=30,
    )
    terminal = repository.terminalize(
        job_id=str(running["id"]),
        expected_status="running",
        expected_version=int(running["transition_version"]),
        lease_owner="worker-sse",
        status="validation_failed",
        reason="safe_validation_failed",
    )
    return repository, terminal


def _sse_client(tmp_path: Path):
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    from app.forecast.api import ForecastProgressHub, router

    repository, terminal = _terminal_sse_repository(tmp_path)

    class Scope:
        @staticmethod
        def allows(subject_kind: str, subject_key: str) -> bool:
            return (subject_kind, subject_key) == ("instrument", "600000.SH")

    application = FastAPI()
    application.include_router(router)
    application.state.forecast_repository = repository
    application.state.forecast_progress_hub = ForecastProgressHub()
    application.state.resolve_forecast_subject_scope = lambda _request: Scope()

    @application.middleware("http")
    async def bind_principal(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.reviewer_principal = "server-principal"
        return await call_next(request)

    return TestClient(application), application.state.forecast_progress_hub, terminal


def test_persisted_sse_event_id_tracks_every_job_transition(tmp_path: Path) -> None:
    repository, terminal = _terminal_sse_repository(tmp_path)
    transitions = repository.job_transitions_after(str(terminal["id"]), after_version=-1)
    assert [row["transition_version"] for row in transitions] == [0, 1, 2]
    assert [row["status"] for row in transitions] == [
        "queued",
        "running",
        "validation_failed",
    ]


def test_last_event_id_resume_emits_only_persisted_transitions_after_version(
    tmp_path: Path,
) -> None:
    client, hub, terminal = _sse_client(tmp_path)
    response = client.get(
        f"/api/forecast/jobs/{terminal['id']}/events",
        headers={"Last-Event-ID": "0"},
    )
    assert response.status_code == 200
    ids = [
        line.removeprefix("id: ") for line in response.text.splitlines() if line.startswith("id: ")
    ]
    payloads = [
        __import__("json").loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert ids == ["1", "2"]
    assert [payload["status"] for payload in payloads] == ["running", "validation_failed"]
    assert hub.active_count == 0


def test_last_event_id_resume_rejects_invalid_or_future_versions(tmp_path: Path) -> None:
    client, hub, terminal = _sse_client(tmp_path)
    path = f"/api/forecast/jobs/{terminal['id']}/events"
    assert client.get(path, headers={"Last-Event-ID": "foreign-job:1"}).status_code == 400
    assert client.get(path, headers={"Last-Event-ID": "999"}).status_code == 409
    assert hub.active_count == 0


def test_subscription_limits_are_atomic_per_principal_job_and_server() -> None:
    from app.forecast.api import ForecastProgressHub, ForecastSubscriptionCapacityError

    hub = ForecastProgressHub(
        queue_size=2,
        per_principal_limit=1,
        per_job_limit=1,
        global_limit=1,
    )

    def subscribe(job_id: str):
        try:
            return hub.subscribe(principal="principal-a", job_id=job_id)
        except ForecastSubscriptionCapacityError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        queues = list(pool.map(subscribe, ("job-a", "job-b")))
    assert sum(queue is not None for queue in queues) == 1
    assert hub.active_count == 1
    for job_id, queue in zip(("job-a", "job-b"), queues, strict=True):
        if queue is not None:
            hub.unsubscribe(principal="principal-a", job_id=job_id, queue=queue)
    assert hub.active_count == 0


def test_slow_consumer_cleanup_bounds_queue_and_releases_capacity() -> None:
    from app.forecast.api import ForecastProgressHub

    hub = ForecastProgressHub(
        queue_size=1,
        per_principal_limit=2,
        per_job_limit=2,
        global_limit=2,
    )
    queue = hub.subscribe(principal="principal-a", job_id="job-a")
    base = {
        "id": "job-a",
        "instrument_id": "600000.SH",
        "horizon": 20,
        "catalog_id": "kronos-local",
        "created_at": "2025-04-30T08:00:00Z",
        "updated_at": "2025-04-30T08:00:01Z",
        "attempt": 1,
    }
    hub.publish({**base, "status": "running", "transition_version": 1})
    hub.publish(
        {
            **base,
            "status": "validation_failed",
            "transition_version": 2,
            "terminal_reason": "safe_validation_failed",
        }
    )
    assert len(queue) == 1
    assert queue[0]["stage"] == "transport_overflow"
    assert hub.active_count == 0
    hub.unsubscribe(principal="principal-a", job_id="job-a", queue=queue)
    assert hub.active_count == 0
