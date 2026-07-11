from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import backtest as backtest_api
from app.backtest.strategy import StrategyBacktestResult
from app.research.artifacts import EvaluationArtifactService
from app.research.catalog import ExperimentCatalog
from app.research.repository import ResearchRepository


class StubStrategyEngine:
    def get(self, strategy_id: str):  # type: ignore[no-untyped-def]
        return SimpleNamespace(meta={"version": "fixture-v1"}, source="builtin")


class StubStrategyBacktestService:
    def __init__(self, engine, strategy_engine) -> None:  # type: ignore[no-untyped-def]
        del engine, strategy_engine

    def run(self, config, progress_cb=None, cancel_event=None):  # type: ignore[no-untyped-def]
        del cancel_event
        if progress_cb is not None:
            progress_cb({"day": 1, "total": 1})
        if config.strategy_id == "cancelled":
            return StrategyBacktestResult(run_id="untrusted-run", config={}, error="cancelled")
        if config.strategy_id == "failed":
            return StrategyBacktestResult(run_id="untrusted-run", config={}, error="registered run failed")
        return StrategyBacktestResult(
            run_id="untrusted-run",
            config={
                "symbols": ["000001.SZ"],
                "asset_type": "stock",
                "start": config.start.isoformat(),
                "end": config.end.isoformat(),
            },
            stats={"annual_return": 0.12, "panel_rows": 2},
            equity_curve=[{"date": "2024-01-02", "equity": 1.0}],
            drawdown_curve=[{"date": "2024-01-02", "drawdown": 0.0}],
            benchmark_curve=[{"date": "2024-01-02", "equity": 1.0}],
            trades=[{"symbol": "000001.SZ", "side": "buy"}],
            strategy_info={"id": config.strategy_id, "source": "builtin"},
        )


def _client(tmp_path: Path, monkeypatch) -> TestClient:  # type: ignore[no-untyped-def]
    repository = ResearchRepository(tmp_path / "operational.db")
    repository.migrate()
    app = FastAPI()
    app.include_router(backtest_api.router)
    from app.api.research import router as research_router

    app.include_router(research_router)
    app.state.backtest_engine = object()
    app.state.strategy_engine = StubStrategyEngine()
    app.state.experiment_catalog = ExperimentCatalog(repository)
    app.state.research_artifact_service = EvaluationArtifactService(tmp_path / "app-data")
    app.state.research_strategy_handles = {}
    backtest_api._running_jobs.clear()
    monkeypatch.setattr("app.backtest.strategy.StrategyBacktestService", StubStrategyBacktestService)
    return TestClient(app)


def test_sync_registered_strategy_handoff_uses_server_snapshot_only(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    rejected_metrics = client.post(
        "/api/backtest/strategy/run", json={"strategy_id": "registered", "metrics": {"annual_return": 999}}
    )
    assert rejected_metrics.status_code == 422
    run = client.post("/api/backtest/strategy/run", json={"strategy_id": "registered"})
    assert run.status_code == 200
    handle = run.json()["research_execution_handle"]
    assert len(handle) == 32

    forged = client.post("/api/research/strategy-executions/forged/retain")
    assert forged.status_code == 404
    retained = client.post(f"/api/research/strategy-executions/{handle}/retain")
    assert retained.status_code == 200
    assert retained.json()["metrics"]["stats"] == {"annual_return": 0.12, "panel_rows": 2}
    assert retained.json()["artifacts"]
    assert client.get("/api/research/comparison/candidates").json()["experiments"][0]["id"] == retained.json()["id"]

    stale_handle = run.json()["research_execution_handle"]
    client.app.state.research_strategy_handles.pop(stale_handle)
    assert client.post(f"/api/research/strategy-executions/{stale_handle}/retain").status_code == 404


def test_failed_cancelled_and_sse_strategy_runs_never_bypass_handoff_gates(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    cancelled = client.post("/api/backtest/strategy/run", json={"strategy_id": "cancelled"})
    failed = client.post("/api/backtest/strategy/run", json={"strategy_id": "failed"})
    assert cancelled.status_code == 200 and failed.status_code == 200
    assert client.post(f"/api/research/strategy-executions/{cancelled.json()['research_execution_handle']}/retain").status_code == 409
    assert client.post(f"/api/research/strategy-executions/{failed.json()['research_execution_handle']}/retain").status_code == 409
    assert client.get("/api/research/comparison/candidates").json()["experiments"] == []

    stream = client.get("/api/backtest/strategy/stream?strategy_id=streamed&start=2024-01-02&end=2024-01-03")
    assert stream.status_code == 200
    assert "event: research" in stream.text
    assert "event: done" in stream.text
    matched = re.search(r'event: research\ndata: (\{[^\n]+\})', stream.text)
    assert matched is not None
    streamed_handle = json.loads(matched.group(1))["execution_handle"]
    assert client.post(f"/api/research/strategy-executions/{streamed_handle}/retain").status_code == 200
