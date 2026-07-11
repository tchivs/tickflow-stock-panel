from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.research import router
from app.config import settings
from app.research.artifacts import EvaluationArtifactService
from app.research.catalog import ExperimentCatalog
from app.research.evaluation import FactorEvaluationService
from app.research.factor_registry import FactorRegistry
from app.research.hypotheses import FactorHypothesisService, OfflineFakeHypothesisGateway
from app.research.repository import ResearchRepository


class StubBacktestEngine:
    def __init__(self, panel: pl.DataFrame) -> None:
        self.panel = panel
        self.calls: list[dict] = []

    def load_panel(self, symbols, start, end, *, columns, asset_type):  # type: ignore[no-untyped-def]
        self.calls.append({"symbols": symbols, "start": start, "end": end, "columns": columns, "asset_type": asset_type})
        return self.panel.select([column for column in columns if column in self.panel.columns])


def _panel() -> pl.DataFrame:
    start = date(2024, 1, 2)
    returns = {"000001.SZ": 0.0, "000002.SZ": 0.5, "000003.SZ": 0.1, "000004.SZ": 0.9}
    rows: list[dict] = []
    for index, (symbol, forward_return) in enumerate(returns.items(), start=1):
        rows.extend(
            [
                {"symbol": symbol, "date": start, "close": float(index)},
                {"symbol": symbol, "date": start + timedelta(days=1), "close": float(index) * (1 + forward_return)},
            ]
        )
    return pl.DataFrame(rows)


def _client(tmp_path: Path) -> TestClient:
    database = ResearchRepository(tmp_path / "operational.db")
    database.migrate()
    registry = FactorRegistry(database)
    app = FastAPI()
    app.include_router(router)
    app.state.factor_registry = registry
    app.state.experiment_catalog = ExperimentCatalog(database)
    app.state.research_artifact_service = EvaluationArtifactService(tmp_path / "app-data")
    app.state.factor_evaluation_service = FactorEvaluationService(
        StubBacktestEngine(_panel()), registry, app.state.research_artifact_service
    )
    app.state.factor_hypothesis_service = FactorHypothesisService(
        OfflineFakeHypothesisGateway(
            raw_response='{"expression":"close","explanation":"Governed close momentum.","assumptions":["fixture panel"]}'
        )
    )
    app.state.research_strategy_handles = {}
    return TestClient(app)


def _evaluation_payload(*, universe: str) -> dict:
    return {
        "universe": universe,
        "symbols": ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"],
        "asset_type": "stock",
        "start": "2024-01-02",
        "end": "2024-01-03",
        "forward_return_horizon": 1,
        "rebalance": "daily",
        "missing_data_treatment": "drop",
        "warmup_treatment": "exclude",
        "warmup_days": 0,
        "n_groups": 2,
        "weight": "equal",
        "fees_pct": 0.0002,
        "slippage_bps": 5,
    }


def test_manual_factor_validation_similarity_evaluation_retention_and_comparison(tmp_path: Path) -> None:
    client = _client(tmp_path)

    invalid = client.post("/api/research/dsl/validate", json={"expression": "__import__('os')"})
    assert invalid.status_code == 400
    first = client.post("/api/research/factors", json={"name": "Close", "expression": "close", "hypothesis": "manual"})
    assert first.status_code == 200
    second = client.post("/api/research/factors", json={"name": "Close ratio", "expression": "close / ma20"})
    assert second.status_code == 200
    similar = client.post("/api/research/factors/similarity", json={"expression": "close"})
    assert similar.status_code == 200
    assert similar.json()["candidates"][0]["reason"] == "exact AST structural signature"

    factor = first.json()
    run = client.post(f"/api/research/factor-revisions/{factor['id']}/evaluate", json=_evaluation_payload(universe="fixture-a"))
    assert run.status_code == 200
    experiment = run.json()["experiment"]
    assert experiment["retained_at"] is None
    assert client.get("/api/research/comparison/candidates").json()["experiments"] == []
    assert client.post(f"/api/research/experiments/{experiment['id']}/retain").status_code == 200

    second_run = client.post(
        f"/api/research/factor-revisions/{second.json()['id']}/evaluate", json=_evaluation_payload(universe="fixture-b")
    )
    assert second_run.status_code == 409  # the panel deliberately does not supply ma20
    revision = client.post(
        f"/api/research/factors/{second.json()['factor_id']}/revisions",
        json={"name": "Close ratio", "expression": "close", "description": "safe revision", "hypothesis": "manual"},
    )
    assert revision.status_code == 200
    second_run = client.post(
        f"/api/research/factor-revisions/{revision.json()['id']}/evaluate", json=_evaluation_payload(universe="fixture-b")
    )
    assert second_run.status_code == 200
    second_experiment = second_run.json()["experiment"]
    assert client.post(f"/api/research/experiments/{second_experiment['id']}/retain").status_code == 200

    comparison = client.post(
        "/api/research/comparison", json={"experiment_ids": [experiment["id"], second_experiment["id"]]}
    )
    assert comparison.status_code == 200
    assert comparison.json()["warnings"] == ["universe differs"]
    assert "winner" not in comparison.json()
    assert len(client.get("/api/research/experiments").json()["experiments"]) == 2


def test_hypothesis_requires_issued_review_before_provenance_bound_factor_revision(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path)
    monkeypatch.setattr(settings, "backtest_range_guard", True)

    draft = client.post("/api/research/hypotheses/drafts", json={"hypothesis": "close momentum", "options": {"asset_type": "stock"}})
    assert draft.status_code == 200
    draft_payload = draft.json()
    assert draft_payload["normalized_expression"] == "close"
    assert draft_payload["provenance"]["provider"] == "offline_fake"

    impersonation = client.post(
        "/api/research/factors",
        json={"name": "Forged", "expression": "close", "provenance": draft_payload["provenance"]},
    )
    assert impersonation.status_code == 422
    unissued = client.post(
        "/api/research/hypotheses/reviewed-factor",
        json={
            "draft_id": "0" * 32,
            "name": "Reviewed",
            "expression": "close",
            "explanation": draft_payload["explanation"],
            "provenance": draft_payload["provenance"],
            "reviewed": True,
        },
    )
    assert unissued.status_code == 400
    promoted = client.post(
        "/api/research/hypotheses/reviewed-factor",
        json={
            "draft_id": draft_payload["draft_id"],
            "name": "Reviewed",
            "expression": draft_payload["expression"],
            "explanation": draft_payload["explanation"],
            "provenance": draft_payload["provenance"],
            "reviewed": True,
        },
    )
    assert promoted.status_code == 200
    assert promoted.json()["provenance"]["source"] == "reviewed_hypothesis"

    direct_retain = client.post("/api/research/experiments/not-a-run/retain")
    assert direct_retain.status_code == 404
    over_limit = _evaluation_payload(universe="fixture")
    over_limit["start"] = "2020-01-01"
    guarded = client.post(f"/api/research/factor-revisions/{promoted.json()['id']}/evaluate", json=over_limit)
    assert guarded.status_code == 400
