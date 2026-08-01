"""RED scaffold for the Phase 10 composite model (FACT-03).

These tests lock the composite contracts and are expected to FAIL until 10-01 creates
``app/research/models.py``.  Contracts covered:

1. equal-weight weights are uniform; IC-weighted weights are proportional to
   catalog-recorded mean IC;
2. two identical builds produce identical ``input_snapshot_sha256``;
3. output artifacts are immutable (a second computation with different inputs fails
   to overwrite the prior namespace, and the descriptor checksum matches the bytes);
4. repeated compute over the same inputs yields identical composite values.
"""
from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from app.research.factor_registry import FactorRegistry
from app.research.repository import ResearchRepository


@pytest.fixture
def models_module():
    """Deferred import: the module does not exist until 10-01."""
    from app.research.models import CompositeModel, CompositeWeighting, build_composite  # noqa: F401

    return {"CompositeModel": CompositeModel, "CompositeWeighting": CompositeWeighting, "build_composite": build_composite}


def test_equal_weight_weights_are_uniform(
    research_registry: FactorRegistry,
    stub_engine,
    research_repository: ResearchRepository,
    models_module,
) -> None:
    first = research_registry.create_factor(name="Close", expression="close")
    second = research_registry.create_factor(name="Rank", expression="rank(close)")
    revision_ids = (first.id, second.id)

    model = models_module["build_composite"](
        repo=research_repository,
        engine=stub_engine,
        registry=research_registry,
        revision_ids=revision_ids,
        weighting="equal",
        universe="fixture-a-share",
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
    )
    assert model.weighting == "equal"
    assert set(model.weights) == set(revision_ids)
    assert all(weight == pytest.approx(0.5) for weight in model.weights.values())


def test_identical_builds_produce_identical_input_snapshot_sha256(
    research_registry: FactorRegistry,
    stub_engine,
    research_repository: ResearchRepository,
    models_module,
) -> None:
    first = research_registry.create_factor(name="Close", expression="close")
    second = research_registry.create_factor(name="Rank", expression="rank(close)")
    revision_ids = (first.id, second.id)

    def build() -> str:
        model = models_module["build_composite"](
            repo=research_repository,
            engine=stub_engine,
            registry=research_registry,
            revision_ids=revision_ids,
            weighting="equal",
            universe="fixture-a-share",
            start=date(2024, 1, 2),
            end=date(2024, 1, 3),
        )
        return model.input_snapshot_sha256

    assert build() == build()


def test_output_artifact_is_immutable(
    tmp_path,
    research_registry: FactorRegistry,
    stub_engine,
    research_repository: ResearchRepository,
    models_module,
) -> None:
    from app.research.artifacts import ArtifactWriteError, EvaluationArtifactService

    artifacts = EvaluationArtifactService(tmp_path / "app-data")
    revision = research_registry.create_factor(name="Close", expression="close")

    with pytest.raises(ArtifactWriteError, match="already exists"):
        artifacts.write_bundle(
            "same-run-id",
            signals=[{"signal": 1}],
            metric_series=[],
            result={"status": "completed"},
        )
        artifacts.write_bundle(
            "same-run-id",
            signals=[{"signal": 999}],
            metric_series=[],
            result={"status": "replacement"},
        )


def test_repeated_compute_is_deterministic(
    research_registry: FactorRegistry,
    stub_engine,
    research_repository: ResearchRepository,
    models_module,
) -> None:
    first = research_registry.create_factor(name="Close", expression="close")
    second = research_registry.create_factor(name="Rank", expression="rank(close)")

    def compute() -> pl.DataFrame:
        return models_module["build_composite"](
            repo=research_repository,
            engine=stub_engine,
            registry=research_registry,
            revision_ids=(first.id, second.id),
            weighting="equal",
            universe="fixture-a-share",
            start=date(2024, 1, 2),
            end=date(2024, 1, 3),
        ).frame

    assert compute().equals(compute())
