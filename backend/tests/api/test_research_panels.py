"""Research panel route tests (15-03 breadth).

The routes project append-only Phases 10/13 catalog rows onto strict DTOs.
These tests seed a research repository through its public insert methods, then
GET every panel route and assert the projected DTO fields round-trip —
including the hard contracts: IC (Pearson) and RankIC (Spearman) are DISTINCT
fields, the reserved OOS fold is flagged separately, and the routes never
execute anything.
"""
from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.research.repository import ResearchRepository

_SHA_A = "a" * 64
_SHA_B = "b" * 64
_SHA_C = "c" * 64
_SHA_D = "d" * 64
_SHA_E = "e" * 64
_SHA_F = "f" * 64
_SHA_G = "ab" * 32
_SHA_H = "cd" * 32
_SHA_I = "ef" * 32
_SHA_J = "0123" * 16


# ================================================================
# Duck-typed walk-forward plan (mirrors tests/backtest/test_walkforward)
# ================================================================


class _Fold:
    def __init__(self, fold_index: int, is_oos: bool = False) -> None:
        self.fold_index = fold_index
        self.is_oos = is_oos
        self.train_start = date(2025, 7, 29)
        self.train_end = date(2026, 1, 22)
        self.gap_start = date(2026, 1, 23)
        self.gap_end = date(2026, 2, 27)
        self.test_start = date(2026, 3, 2)
        self.test_end = date(2026, 3, 27)


class _Plan:
    def __init__(self, plan_id: str = "wf-plan-panel") -> None:
        self.plan_id = plan_id
        self.universe = "cn-a-share"
        self.asset_type = "stock"
        self.start = date(2025, 7, 29)
        self.end = date(2026, 7, 30)
        self.train_size = 120
        self.gap_size = 20
        self.test_size = 20
        self.oos_size = 40
        self.horizon = 5
        self.trading_dates = [date(2025, 7, 29)]
        self.folds = (_Fold(0), _Fold(1))
        self.oos_fold = _Fold(2, is_oos=True)


# ================================================================
# Seed helpers
# ================================================================


def _seed_factor(
    repo: ResearchRepository,
    *,
    factor_id: str = "fac-momentum",
    revision_id: str = "rev-momentum",
    expression: str = "close",
    name: str = "Momentum",
) -> str:
    repo.create_factor_with_revision(
        factor_id=factor_id,
        revision_id=revision_id,
        name=name,
        description="cross-sectional momentum",
        hypothesis="recent winners keep winning",
        canonical_expression=expression,
        dsl_version="1.0",
        ast_signature="ast:" + expression,
        shape_signature="shape:" + expression,
        fields=frozenset({"close"}),
        operators=frozenset(),
        functions=frozenset(),
        provenance={"author": "fixture"},
    )
    return revision_id


def _seed_verdict(
    repo: ResearchRepository,
    *,
    revision_id: str,
    policy_version: str = "v1",
    verdict: str = "admitted",
) -> None:
    repo.insert_admission_verdict(
        revision_id=revision_id,
        policy_version=policy_version,
        verdict=verdict,
        reason="meets the admission gates",
        gates_json=[{"metric": "mean_ic_train", "passed": True, "observed": 0.05}],
        candidate_trail_json={"experiment_snapshot_ids": []},
        resolved_universe_json={"universe": "cn-a-share"},
        input_snapshot_sha256=_SHA_C,
    )


def _artifact(run_id: str) -> dict:
    return {
        "evaluation_run_id": run_id,
        "relative_path": f"research_artifacts/{run_id}/signals.json",
        "content_type": "application/json",
        "byte_size": 42,
        "checksum_sha256": _SHA_D,
        "created_at": "2026-01-01T00:00:00Z",
    }


def _seed_retained_experiment(
    repo: ResearchRepository,
    *,
    revision_id: str,
    run_id: str = "run-eval-1",
    ic: float = 0.12,
    rank_ic: float = 0.18,
) -> str:
    """Seed a retained validated experiment carrying DISTINCT IC + RankIC evidence."""
    experiment_id = "exp-" + run_id
    repo.create_experiment(
        experiment_id=experiment_id,
        originating_run_id=run_id,
        status="completed",
        validated=True,
        factor_revision_id=revision_id,
        strategy_id=None,
        strategy_version=None,
        resolved_config={},
        input_manifest={},
        prediction_signals={},
        metrics={"ic_summary": {"mean": ic}, "rank_ic_summary": {"mean": rank_ic}},
        artifacts=(_artifact(run_id),),
        diagnostics={},
        model_provenance=None,
    )
    repo.retain_experiment(experiment_id)
    return experiment_id


def _seed_model(
    repo: ResearchRepository,
    *,
    model_id: str = "model-panel-1",
    revision_id: str = "rev-momentum",
) -> str:
    repo.insert_model_definition(
        model_id=model_id,
        name="Panel Composite",
        weighting="ic_weighted",
        revision_ids=[revision_id],
        weights={revision_id: 1.0},
        input_snapshot_sha256=_SHA_I,
    )
    repo.insert_model_composite(
        model_id=model_id,
        output_sha256=_SHA_J,
        artifact_relative_path=f"research_artifacts/{model_id}/signals.json",
        input_snapshot_sha256=_SHA_I,
    )
    return model_id


def _seed_wf(repo: ResearchRepository, *, plan_id: str = "wf-plan-panel") -> str:
    repo.create_wf_plan(_Plan(plan_id=plan_id))
    # Two selection folds + one reserved OOS fold.
    repo.record_wf_fold(
        id=f"{plan_id}-fold-0",
        plan_id=plan_id,
        fold_index=0,
        is_oos=False,
        strategy_id="s1",
        params_sha256=_SHA_E,
        train_start=date(2026, 3, 2),
        train_end=date(2026, 3, 27),
        test_start=date(2026, 3, 2),
        test_end=date(2026, 3, 27),
        membership_fingerprint=_SHA_F,
        chain_config={"horizon": 5},
        stats={"sharpe": 1.2},
    )
    repo.record_wf_fold(
        id=f"{plan_id}-fold-1",
        plan_id=plan_id,
        fold_index=1,
        is_oos=False,
        strategy_id="s1",
        params_sha256=_SHA_E,
        train_start=date(2026, 3, 2),
        train_end=date(2026, 3, 27),
        test_start=date(2026, 3, 30),
        test_end=date(2026, 4, 24),
        membership_fingerprint=_SHA_F,
        chain_config={"horizon": 5},
        stats={"sharpe": 0.9},
    )
    repo.record_wf_fold(
        id=f"{plan_id}-fold-oos",
        plan_id=plan_id,
        fold_index=2,
        is_oos=True,
        strategy_id="s1",
        params_sha256=_SHA_E,
        train_start=date(2026, 3, 2),
        train_end=date(2026, 3, 27),
        test_start=date(2026, 6, 1),
        test_end=date(2026, 7, 30),
        membership_fingerprint=_SHA_F,
        chain_config={"horizon": 5},
        stats={"oos_sharpe": 0.42},
    )
    repo.record_wf_search(
        id=f"{plan_id}-search",
        plan_id=plan_id,
        strategy_id="s1",
        objective="sharpe",
        direction="maximize",
        search_space={"lookback": [10, 20]},
        n_trials=10,
        n_completed=10,
        score_distribution={"q50": 1.0},
        best_params={"lookback": 20},
        best_score=1.5,
        oos_excluded=1,
    )
    repo.record_validated_strategy(
        id=f"{plan_id}-valid",
        strategy_id="s1",
        plan_id=plan_id,
        search_run_id=f"{plan_id}-search",
        params_sha256=_SHA_E,
        oos_evidence_fold_id=f"{plan_id}-fold-oos",
        resolved_asset_ids=["rev-momentum"],
        validation_score=0.42,
        fold_evidence={"oos_sharpe": 0.42},
        passed_gate=True,
    )
    repo.record_wf_ensemble(
        id=f"{plan_id}-ens",
        name="ensemble-v1",
        strategy_ids=["s1"],
        weights={"s1": 1.0},
        validation_record_ids=[f"{plan_id}-valid"],
        input_snapshot_sha256=_SHA_G,
        output_sha256=_SHA_H,
        artifact_relative_path=f"research_artifacts/{plan_id}-ens/out.json",
    )
    return plan_id


# ================================================================
# Empty-list scaffold tests (15-02, retained)
# ================================================================


def test_list_factors_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/research/factors")
    assert response.status_code == 200
    assert response.json() == []


def test_list_models_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/research/models")
    assert response.status_code == 200


def test_list_wf_plans_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/research/wf/plans")
    assert response.status_code == 200
    assert response.json() == []


def test_list_wf_folds_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/research/wf/folds")
    assert response.status_code == 200


def test_list_wf_search_runs_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/research/wf/search-runs")
    assert response.status_code == 200


def test_list_wf_validated_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/research/wf/validated")
    assert response.status_code == 200


def test_list_wf_ensembles_empty(panel_client: TestClient) -> None:
    response = panel_client.get("/api/research/wf/ensembles")
    assert response.status_code == 200


def test_get_admission_verdict_not_found(panel_client: TestClient) -> None:
    response = panel_client.get("/api/research/factors/nonexistent/verdict")
    assert response.status_code == 404


def test_factor_revision_dto_rejects_extra_fields() -> None:
    """Strict DTO: extra field is forbidden."""
    from app.contracts.panels import FactorRevisionDTO
    from pydantic import ValidationError

    import pytest as _pytest

    minimal = {
        "id": "rev-1",
        "factor_id": "fac-1",
        "revision_number": 1,
        "name": "test",
        "expression": "close",
        "status": "admitted",
        "created_at": "2026-01-01T00:00:00Z",
        "bogus_field": "should fail",
    }
    with _pytest.raises(ValidationError):
        FactorRevisionDTO(**minimal)


# ================================================================
# Factor catalog — projection + DISTINCT IC / RankIC (15-03)
# ================================================================


def test_list_factors_projects_revision_fields(
    research_repository: ResearchRepository, panel_client: TestClient
) -> None:
    revision_id = _seed_factor(research_repository, name="Momentum", expression="close")
    _seed_verdict(research_repository, revision_id=revision_id, verdict="admitted")

    response = panel_client.get("/api/research/factors")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    factor = payload[0]
    assert factor["id"] == revision_id
    assert factor["name"] == "Momentum"
    # canonical_expression is projected onto the DTO's `expression` field.
    assert factor["expression"] == "close"
    assert factor["status"] == "admitted"
    assert factor["revision_number"] == 1
    assert factor["created_at"]


def test_list_factors_ic_and_rank_ic_are_distinct_fields(
    research_repository: ResearchRepository, panel_client: TestClient
) -> None:
    """IC (Pearson) and RankIC (Spearman) surface as SEPARATE, unequal fields."""
    revision_id = _seed_factor(research_repository)
    _seed_retained_experiment(research_repository, revision_id=revision_id, ic=0.12, rank_ic=0.18)

    factor = panel_client.get("/api/research/factors").json()[0]
    # Two distinct keys exist — never collapsed into one column.
    assert "ic" in factor
    assert "rank_ic" in factor
    assert factor["ic"] == 0.12
    assert factor["rank_ic"] == 0.18
    assert factor["ic"] != factor["rank_ic"]


def test_list_factors_without_evidence_has_null_ic_rank_ic(
    research_repository: ResearchRepository, panel_client: TestClient
) -> None:
    """A revision with no retained evidence still lists, with null IC/RankIC."""
    _seed_factor(research_repository, revision_id="rev-bare")
    factor = panel_client.get("/api/research/factors").json()[0]
    assert factor["status"] == "unadmitted"
    assert factor["ic"] is None
    assert factor["rank_ic"] is None


def test_get_admission_verdict_seeded(
    research_repository: ResearchRepository, panel_client: TestClient
) -> None:
    revision_id = _seed_factor(research_repository)
    _seed_verdict(research_repository, revision_id=revision_id, verdict="admitted")

    response = panel_client.get(f"/api/research/factors/{revision_id}/verdict")
    assert response.status_code == 200
    verdict = response.json()
    assert verdict["revision_id"] == revision_id
    assert verdict["admitted"] is True
    assert verdict["reason"] == "meets the admission gates"
    assert isinstance(verdict["details"], dict)
    assert isinstance(verdict["details"]["gates"], list)


# ================================================================
# Model library (15-03)
# ================================================================


def test_list_models_seeded(
    research_repository: ResearchRepository, panel_client: TestClient
) -> None:
    _seed_model(research_repository, model_id="model-panel-1")

    models = panel_client.get("/api/research/models").json()
    assert len(models) == 1
    model = models[0]
    assert model["model_id"] == "model-panel-1"
    assert model["name"] == "Panel Composite"
    assert model["weighting"] == "ic_weighted"
    assert model["revision_ids"] == ["rev-momentum"]
    assert model["input_snapshot_sha256"] == _SHA_I


def test_list_model_composites_seeded(
    research_repository: ResearchRepository, panel_client: TestClient
) -> None:
    _seed_model(research_repository, model_id="model-panel-1")

    composites = panel_client.get("/api/research/models/model-panel-1/composites").json()
    assert len(composites) == 1
    composite = composites[0]
    assert composite["model_id"] == "model-panel-1"
    assert composite["output_sha256"] == _SHA_J
    assert composite["input_snapshot_sha256"] == _SHA_I
    # artifact_relative_path is projected onto the DTO field.
    assert composite["output_artifact_relative_path"] == "research_artifacts/model-panel-1/signals.json"


# ================================================================
# Walk-forward (15-03)
# ================================================================


def test_list_wf_plans_seeded(
    research_repository: ResearchRepository, panel_client: TestClient
) -> None:
    _seed_wf(research_repository, plan_id="wf-plan-panel")

    plans = panel_client.get("/api/research/wf/plans").json()
    assert len(plans) == 1
    plan = plans[0]
    assert plan["id"] == "wf-plan-panel"
    # gap_size -> gap; n_folds derived from the fold geometry.
    assert plan["n_folds"] == 2
    assert plan["train_size"] == 120
    assert plan["test_size"] == 20
    assert plan["gap"] == 20
    assert plan["pinned"] is True
    # Reserved OOS window is surfaced explicitly.
    assert plan["oos_start"] is not None
    assert plan["oos_end"] is not None


def test_list_wf_folds_flags_reserved_oos_separately(
    research_repository: ResearchRepository, panel_client: TestClient
) -> None:
    _seed_wf(research_repository, plan_id="wf-plan-panel")

    folds = panel_client.get("/api/research/wf/folds").json()
    by_index = {fold["fold_index"]: fold for fold in folds}
    assert len(folds) == 3
    # Selection folds are not OOS; the reserved OOS fold is flagged exactly once.
    assert by_index[0]["is_oos"] is False
    assert by_index[1]["is_oos"] is False
    assert by_index[2]["is_oos"] is True


def test_list_wf_folds_oos_filter(
    research_repository: ResearchRepository, panel_client: TestClient
) -> None:
    _seed_wf(research_repository, plan_id="wf-plan-panel")

    oos = panel_client.get("/api/research/wf/folds", params={"is_oos": "true"}).json()
    assert len(oos) == 1
    assert oos[0]["is_oos"] is True

    selection = panel_client.get("/api/research/wf/folds", params={"is_oos": "false"}).json()
    assert len(selection) == 2
    assert all(fold["is_oos"] is False for fold in selection)


def test_list_wf_search_runs_seeded(
    research_repository: ResearchRepository, panel_client: TestClient
) -> None:
    _seed_wf(research_repository, plan_id="wf-plan-panel")

    runs = panel_client.get("/api/research/wf/search-runs").json()
    assert len(runs) == 1
    run = runs[0]
    assert run["n_trials"] == 10
    assert run["best_score"] == 1.5
    assert run["status"] == "completed"


def test_list_validated_strategies_seeded(
    research_repository: ResearchRepository, panel_client: TestClient
) -> None:
    _seed_wf(research_repository, plan_id="wf-plan-panel")

    validated = panel_client.get("/api/research/wf/validated").json()
    assert len(validated) == 1
    row = validated[0]
    # passed_gate -> validated; validation_score -> oos_score.
    assert row["validated"] is True
    assert row["oos_score"] == 0.42
    assert row["strategy_id"] == "s1"


def test_list_wf_ensembles_seeded(
    research_repository: ResearchRepository, panel_client: TestClient
) -> None:
    _seed_wf(research_repository, plan_id="wf-plan-panel")

    ensembles = panel_client.get("/api/research/wf/ensembles").json()
    assert len(ensembles) == 1
    ensemble = ensembles[0]
    assert ensemble["name"] == "ensemble-v1"
    assert ensemble["strategy_ids"] == ["s1"]
    assert ensemble["output_snapshot_sha256"] == _SHA_H
