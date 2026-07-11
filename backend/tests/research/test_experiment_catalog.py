from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from app.backtest.strategy import StrategyBacktestResult
from app.research.artifacts import ArtifactDescriptor
from app.research.catalog import ExperimentCatalog, FactorEvidencePackage
from app.research.evaluation import FactorEvaluationResult
from app.research.factor_registry import FactorRegistry
from app.research.repository import ResearchRepository


def _catalog(tmp_path: Path) -> tuple[ExperimentCatalog, FactorRegistry]:
    repository = ResearchRepository(tmp_path / "operational.db")
    repository.migrate()
    return ExperimentCatalog(repository), FactorRegistry(repository)


def _artifact(tmp_path: Path, run_id: str, name: str = "signals.json") -> ArtifactDescriptor:
    content = b'{"signal":"buy"}'
    path = tmp_path / "research_artifacts" / run_id / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return ArtifactDescriptor(
        evaluation_run_id=run_id,
        relative_path=f"research_artifacts/{run_id}/{name}",
        content_type="application/json",
        byte_size=len(content),
        checksum_sha256=sha256(content).hexdigest(),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _factor_package(tmp_path: Path, revision_id: str, *, run_id: str = "a" * 32) -> FactorEvidencePackage:
    return FactorEvidencePackage(
        evaluation_run_id=run_id,
        factor_revision_id=revision_id,
        resolved_config={
            "universe": ["000001.SZ"],
            "start": "2025-01-01",
            "end": "2025-01-31",
            "forward_return_horizon": 5,
        },
        input_manifest={"revision": "governed-v1", "fingerprint": "f" * 64, "rows": 40},
        prediction_signals={"signals_artifact": f"research_artifacts/{run_id}/signals.json"},
        metrics={"ic_summary": {"mean": 0.12}, "rank_ic_summary": {"mean": 0.18}},
        artifacts=(_artifact(tmp_path, run_id),),
        diagnostics={"validated_by": "factor-evaluator"},
        model_provenance=None,
    )


def test_completed_factor_snapshot_is_immutable_and_retention_is_explicit_once(tmp_path: Path) -> None:
    catalog, registry = _catalog(tmp_path)
    factor = registry.create_factor(name="Momentum", expression="close / ma20")
    package = _factor_package(tmp_path, factor.id)
    saved = catalog.record_factor_evaluation(
        FactorEvaluationResult(
            evaluation_run_id=package.evaluation_run_id,
            status="completed",
            factor_revision={"id": factor.id},
            resolved_config=package.resolved_config,
            input_manifest=package.input_manifest,
            ic_summary=package.metrics["ic_summary"],
            rank_ic_summary=package.metrics["rank_ic_summary"],
            artifacts=package.artifacts,
            diagnostics=("factor evidence validated",),
        )
    )

    assert saved.retained_at is None
    assert catalog.list_comparison_candidates() == []
    artifact_path = tmp_path / saved.artifacts[0].relative_path
    artifact_bytes = artifact_path.read_bytes()
    snapshot = saved.as_dict()

    registry.revise_factor(factor.factor_id, expression="close / ma60")
    assert catalog.get(saved.id).as_dict() == snapshot  # type: ignore[union-attr]
    assert artifact_path.read_bytes() == artifact_bytes
    assert sha256(artifact_bytes).hexdigest() == saved.artifacts[0].checksum_sha256

    retained = catalog.retain(saved.id)
    assert retained.retained_at is not None
    with pytest.raises(ValueError, match="already been retained"):
        catalog.retain(saved.id)
    assert [candidate.id for candidate in catalog.list_comparison_candidates()] == [saved.id]


def test_artifacts_require_unique_managed_paths_bound_to_their_run(tmp_path: Path) -> None:
    catalog, registry = _catalog(tmp_path)
    factor = registry.create_factor(name="Momentum", expression="close / ma20")
    package = _factor_package(tmp_path, factor.id)
    artifact = package.artifacts[0]

    with pytest.raises(ValueError, match="bound to its originating run ID"):
        catalog.record_factor_evidence(
            replace(package, artifacts=(replace(artifact, evaluation_run_id="b" * 32),))
        )
    with pytest.raises(ValueError, match="managed relative path"):
        catalog.record_factor_evidence(
            replace(package, artifacts=(replace(artifact, relative_path="outside/signals.json"),))
        )
    with pytest.raises(ValueError, match="unique"):
        catalog.record_factor_evidence(replace(package, artifacts=(artifact, artifact)))


def test_diagnostics_and_unretained_results_never_become_comparison_candidates(tmp_path: Path) -> None:
    catalog, registry = _catalog(tmp_path)
    factor = registry.create_factor(name="Momentum", expression="close / ma20")
    unretained = catalog.record_factor_evidence(_factor_package(tmp_path, factor.id))
    diagnostic_ids = [
        catalog.record_diagnostic(
            originating_run_id=run_id,
            status=status,
            validated=False,
            factor_revision_id=factor.id,
            diagnostics={"reason": status},
        ).id
        for status, run_id in (("draft", "b" * 32), ("failed", "c" * 32), ("cancelled", "d" * 32), ("invalid", "e" * 32))
    ]

    assert catalog.list_comparison_candidates() == []
    with pytest.raises(ValueError, match="not a retained completed validated result"):
        catalog.compare([unretained.id, diagnostic_ids[0]])
    catalog.retain(unretained.id)
    for experiment_id in diagnostic_ids:
        with pytest.raises(ValueError, match="only completed validated experiments"):
            catalog.retain(experiment_id)
        with pytest.raises(ValueError, match="not a retained completed validated result"):
            catalog.compare([unretained.id, experiment_id])


def test_registered_strategy_snapshot_and_comparison_expose_deltas_without_winner(tmp_path: Path) -> None:
    catalog, registry = _catalog(tmp_path)
    factor = registry.create_factor(name="Momentum", expression="close / ma20")
    factor_snapshot = catalog.retain(catalog.record_factor_evidence(_factor_package(tmp_path, factor.id)).id)

    strategy_result = StrategyBacktestResult(
        run_id="f" * 32,
        config={
            "symbols": ["000002.SZ"],
            "start": "2025-02-01",
            "end": "2025-02-28",
            "forward_return_horizon": 10,
        },
        stats={"annual_return": 0.21},
        trades=[{"symbol": "000002.SZ", "side": "buy"}],
        strategy_info={"id": "registered-mean-reversion", "source": "builtin"},
    )
    strategy_snapshot = catalog.record_strategy_backtest(
        strategy_result,
        strategy_id="registered-mean-reversion",
        strategy_version="v3",
        input_manifest={"revision": "governed-v1", "fingerprint": "0" * 64, "rows": 50},
        artifacts=(_artifact(tmp_path, strategy_result.run_id, "result.json"),),
        model_provenance={
            "provider": "local-reviewer",
            "model": "model-x",
            "model_version": "2026-01",
            "provenance": {"mode": "reviewed"},
        },
    )
    strategy_result.stats["annual_return"] = 999
    strategy_result.strategy_info["source"] = "mutated"
    retained_strategy = catalog.retain(strategy_snapshot.id)

    comparison = catalog.compare([factor_snapshot.id, retained_strategy.id])
    rendered = comparison.as_dict()
    assert [snapshot["id"] for snapshot in rendered["experiments"]] == [factor_snapshot.id, retained_strategy.id]
    assert retained_strategy.metrics["stats"] == {"annual_return": 0.21}
    assert retained_strategy.diagnostics["strategy_source"] == "builtin"
    assert set(rendered["deltas"]) == {
        "resolved_configuration",
        "governed_data_input",
        "predictions_signals",
        "metrics",
        "artifact_descriptors",
        "provider_model_version",
    }
    assert all(not delta["equal"] for delta in rendered["deltas"].values())
    assert rendered["warnings"] == [
        "universe differs",
        "date window differs",
        "forward-return horizon differs",
        "governed data manifest revision/fingerprint differs",
    ]
    assert "winner" not in rendered
    assert "ranking" not in rendered


def test_strategy_comparison_warns_only_for_changed_governed_identity(tmp_path: Path) -> None:
    catalog, _ = _catalog(tmp_path)

    def retain(run_id: str, revision: str, fingerprint: str):
        result = StrategyBacktestResult(
            run_id=run_id,
            config={
                "symbols": ["000001.SZ"],
                "asset_type": "stock",
                "start": "2025-01-01",
                "end": "2025-01-31",
                "forward_return_horizon": 5,
            },
            stats={"annual_return": 0.12, "panel_rows": 50},
            trades=[{"symbol": "000001.SZ", "side": "buy"}],
            strategy_info={"id": "registered-mean-reversion", "source": "builtin"},
            governed_input_manifest={"revision": revision, "fingerprint": fingerprint},
        )
        snapshot = catalog.record_strategy_backtest(
            result,
            strategy_id="registered-mean-reversion",
            strategy_version="v3",
            input_manifest={
                "source": "governed_backtest_engine",
                "revision": revision,
                "fingerprint": fingerprint,
                "rows": 50,
            },
            artifacts=(_artifact(tmp_path, run_id, "result.json"),),
        )
        return catalog.retain(snapshot.id)

    baseline = retain("a" * 32, "governed-v1", "1" * 64)
    changed = retain("b" * 32, "governed-v2", "2" * 64)

    comparison = catalog.compare([baseline.id, changed.id]).as_dict()
    assert comparison["warnings"] == ["governed data manifest revision/fingerprint differs"]
    assert comparison["deltas"]["governed_data_input"]["equal"] is False
    governed_values = comparison["deltas"]["governed_data_input"]["values"]
    assert governed_values[baseline.id] == {
        "source": "governed_backtest_engine", "revision": "governed-v1", "fingerprint": "1" * 64, "rows": 50
    }
    assert governed_values[changed.id] == {
        "source": "governed_backtest_engine", "revision": "governed-v2", "fingerprint": "2" * 64, "rows": 50
    }
    assert "winner" not in comparison
    assert "ranking" not in comparison

    identical = retain("c" * 32, "governed-v1", "1" * 64)
    assert catalog.compare([baseline.id, identical.id]).as_dict()["warnings"] == []
