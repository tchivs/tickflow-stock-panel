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

import json
import uuid
from datetime import date
from hashlib import sha256

import polars as pl
import pytest

from app.research.artifacts import ArtifactWriteError, EvaluationArtifactService
from app.research.catalog import ExperimentCatalog, FactorEvidencePackage
from app.research.factor_registry import FactorRegistry
from app.research.repository import ResearchRepository
from tests.research.conftest import FIXTURE_SYMBOLS


@pytest.fixture
def models_module():
    """Deferred import: the module does not exist until 10-01."""
    from app.research.models import CompositeModel, CompositeWeighting, build_composite

    return {"CompositeModel": CompositeModel, "CompositeWeighting": CompositeWeighting, "build_composite": build_composite}


def _fixture_artifacts(tmp_path) -> EvaluationArtifactService:
    return EvaluationArtifactService(tmp_path / "app-data")


def _record_mean_ic(
    research_repository: ResearchRepository,
    research_registry: FactorRegistry,
    revision_id: str,
    *,
    mean: float,
    universe: str = "fixture-a-share",
    start: date = date(2024, 1, 2),
    end: date = date(2024, 1, 3),
) -> None:
    """Record catalogued evaluation evidence carrying the given mean IC."""
    catalog = ExperimentCatalog(research_repository)
    catalog.record_factor_evidence(
        FactorEvidencePackage(
            evaluation_run_id=uuid.uuid4().hex,
            factor_revision_id=revision_id,
            resolved_config={
                "universe": universe,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "forward_return_horizon": 1,
            },
            input_manifest={"revision": "governed-v1", "fingerprint": "f" * 64, "rows": 8},
            prediction_signals={"signals_artifact": "research_artifacts/f/signals.json"},
            metrics={"ic_summary": {"mean": mean}, "rank_ic_summary": {"mean": 0.1}},
            artifacts=(),
            diagnostics={},
            model_provenance=None,
        )
    )


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
        symbols=FIXTURE_SYMBOLS,
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
            symbols=FIXTURE_SYMBOLS,
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
    """A second computation cannot overwrite the prior namespace (O_EXCL)."""
    artifacts = _fixture_artifacts(tmp_path)
    first = research_registry.create_factor(name="Close", expression="close")
    second = research_registry.create_factor(name="Rank", expression="rank(close)")

    model = models_module["build_composite"](
        repo=research_repository,
        engine=stub_engine,
        registry=research_registry,
        revision_ids=(first.id, second.id),
        weighting="equal",
        universe="fixture-a-share",
        symbols=FIXTURE_SYMBOLS,
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        artifact_service=artifacts,
    )
    rows = research_repository.list_model_composites(model.model_id)
    assert len(rows) == 1
    row = rows[0]
    # The descriptor checksum matches the bytes on disk.
    path = tmp_path / "app-data" / row["artifact_relative_path"]
    assert sha256(path.read_bytes()).hexdigest() == row["output_sha256"]
    # A different computation writing to the SAME namespace is blocked by O_EXCL:
    # the retained evidence is never overwritten (T-10-04).
    with pytest.raises(ArtifactWriteError, match="already exists"):
        artifacts.write_bundle(
            model.model_id,
            signals=[{"symbol": "000001.SZ", "date": "2024-01-02", "composite": 999.0}],
            metric_series=[],
            result={"status": "replacement"},
        )


def test_output_artifact_checksum_matches_bytes(
    tmp_path,
    research_registry: FactorRegistry,
    stub_engine,
    research_repository: ResearchRepository,
    models_module,
) -> None:
    """The persisted composite row's output_sha256 matches the artifact bytes."""
    artifacts = _fixture_artifacts(tmp_path)
    first = research_registry.create_factor(name="Close", expression="close")
    second = research_registry.create_factor(name="Rank", expression="rank(close)")
    model = models_module["build_composite"](
        repo=research_repository,
        engine=stub_engine,
        registry=research_registry,
        revision_ids=(first.id, second.id),
        weighting="equal",
        universe="fixture-a-share",
        symbols=FIXTURE_SYMBOLS,
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        artifact_service=artifacts,
    )
    rows = research_repository.list_model_composites(model.model_id)
    assert len(rows) == 1
    row = rows[0]
    path = tmp_path / "app-data" / row["artifact_relative_path"]
    assert path.read_bytes()  # artifact exists on disk
    assert row["output_sha256"] == sha256(path.read_bytes()).hexdigest()
    assert row["input_snapshot_sha256"] == model.input_snapshot_sha256


def test_ic_weighted_weights_are_proportional_to_catalogued_mean_ic(
    research_registry: FactorRegistry,
    stub_engine,
    research_repository: ResearchRepository,
    models_module,
) -> None:
    """w_r / w_s == mean_ic_r / mean_ic_s from the catalog-recorded evidence."""
    first = research_registry.create_factor(name="Close", expression="close")
    second = research_registry.create_factor(name="Rank", expression="rank(close)")
    _record_mean_ic(research_repository, research_registry, first.id, mean=0.03)
    _record_mean_ic(research_repository, research_registry, second.id, mean=0.06)

    model = models_module["build_composite"](
        repo=research_repository,
        engine=stub_engine,
        registry=research_registry,
        revision_ids=(first.id, second.id),
        weighting="ic_weighted",
        universe="fixture-a-share",
        symbols=FIXTURE_SYMBOLS,
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
    )
    ratio = model.weights[first.id] / model.weights[second.id]
    assert ratio == pytest.approx(0.03 / 0.06)
    assert sum(model.weights.values()) == pytest.approx(1.0)


def test_ic_weighted_fails_closed_when_recorded_mean_ic_is_missing(
    research_registry: FactorRegistry,
    stub_engine,
    research_repository: ResearchRepository,
    models_module,
) -> None:
    """A revision without recorded evidence fails closed, never equal-weight."""
    first = research_registry.create_factor(name="Close", expression="close")
    second = research_registry.create_factor(name="Rank", expression="rank(close)")
    _record_mean_ic(research_repository, research_registry, first.id, mean=0.03)

    with pytest.raises(ValueError, match="no recorded evaluation evidence"):
        models_module["build_composite"](
            repo=research_repository,
            engine=stub_engine,
            registry=research_registry,
            revision_ids=(first.id, second.id),
            weighting="ic_weighted",
            universe="fixture-a-share",
            symbols=FIXTURE_SYMBOLS,
            start=date(2024, 1, 2),
            end=date(2024, 1, 3),
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
            symbols=FIXTURE_SYMBOLS,
            start=date(2024, 1, 2),
            end=date(2024, 1, 3),
        ).frame

    assert compute().equals(compute())


def test_equal_weight_composite_matches_numeric_reference(
    research_registry: FactorRegistry,
    stub_engine,
    research_repository: ResearchRepository,
    models_module,
) -> None:
    """CR-01: equal-weight composite == mean of the per-revision z-scores.

    The documented formula is ``composite = mean_r z_r``.  A regression once
    pre-multiplied each z-score by 1/n and then mean-averaged the already-
    weighted columns, yielding ``mean(z)/n`` (bias factor 0.5 for n=2).  Assert
    the composite VALUES against an independent numeric reference computed from
    the raw chain z-scores, not just the weights.
    """
    from app.research.signal_chain import FactorSignalChain, SignalChainConfig

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
        symbols=FIXTURE_SYMBOLS,
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
    )

    chain = FactorSignalChain(stub_engine, research_registry, None)
    zframes = []
    for revision_id in revision_ids:
        signal = chain.compute(
            revision_id=revision_id,
            config=SignalChainConfig(
                universe="fixture-a-share",
                symbols=(),
                asset_type="stock",
                start=date(2024, 1, 2),
                end=date(2024, 1, 3),
                warmup_days=0,
                forward_return_horizon=1,
            ),
        )
        zframes.append(
            signal.frame.select(
                [pl.col("symbol"), pl.col("date"), pl.col("_zscore").alias(f"z_{revision_id}")]
            )
        )
    reference = zframes[0].join(zframes[1], on=["symbol", "date"], how="inner")
    reference = reference.with_columns(
        ((pl.col(f"z_{revision_ids[0]}") + pl.col(f"z_{revision_ids[1]}")) / 2).alias(
            "expected_composite"
        )
    ).select(["symbol", "date", "expected_composite"])

    observed = model.frame.sort(["date", "symbol"])
    reference = reference.sort(["date", "symbol"])
    assert observed.height == reference.height
    for row in reference.iter_rows(named=True):
        observed_value = observed.filter(
            (pl.col("symbol") == row["symbol"]) & (pl.col("date") == row["date"])
        ).select(pl.col("composite")).item()
        assert observed_value == pytest.approx(row["expected_composite"], abs=1e-9)


def test_build_composite_requires_symbols_or_resolver(
    research_registry: FactorRegistry,
    stub_engine,
    research_repository: ResearchRepository,
    models_module,
) -> None:
    """WR-04: omitted symbols fail closed instead of falling back to DSL fields.

    ``revision.fields`` are governed column names, not tickers; a composite
    built with the old fallback requested ``load_panel`` for "close"/"rank"
    and produced garbage (masked by the stub engine).  Omitting symbols with no
    resolver must raise, and a resolver-provided universe is accepted.
    """
    first = research_registry.create_factor(name="Close", expression="close")
    second = research_registry.create_factor(name="Rank", expression="rank(close)")
    revision_ids = (first.id, second.id)

    with pytest.raises(ValueError, match="symbols are required"):
        models_module["build_composite"](
            repo=research_repository,
            engine=stub_engine,
            registry=research_registry,
            revision_ids=revision_ids,
            weighting="equal",
            universe="fixture-a-share",
            start=date(2024, 1, 2),
            end=date(2024, 1, 3),
        )

    # With a universe resolver providing membership, symbols resolve from it.
    from tests.research.conftest import StubUniverseResolver

    membership = pl.DataFrame(
        {
            "symbol": ["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"] * 2,
            "date": [date(2024, 1, 2)] * 4 + [date(2024, 1, 3)] * 4,
        }
    )
    resolver = StubUniverseResolver(membership)
    model = models_module["build_composite"](
        repo=research_repository,
        engine=stub_engine,
        registry=research_registry,
        revision_ids=revision_ids,
        weighting="equal",
        universe="fixture-a-share",
        universe_resolver=resolver,
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
    )
    assert model.frame.height > 0


def test_composite_snapshot_consumption_matches_artifact_bytes(
    tmp_path,
    research_registry: FactorRegistry,
    stub_engine,
    research_repository: ResearchRepository,
    models_module,
) -> None:
    """Cross-module (11-05): the optimizer consumes the composite BY SNAPSHOT.

    RESEARCH.md `## Input Snapshot Binding` integrity check 2: library composite
    used as expected returns == artifact bytes verified by output_sha256, and the
    run's audit root ``input_snapshot_sha256`` == the factor_model_composites
    row's ``input_snapshot_sha256``. build_composite records the frozen artifact;
    load_composite_snapshot (portfolio) reads exactly those bytes.
    """
    from app.portfolio.snapshot import load_composite_snapshot

    artifacts = _fixture_artifacts(tmp_path)
    first = research_registry.create_factor(name="Close", expression="close")
    second = research_registry.create_factor(name="Rank", expression="rank(close)")
    model = models_module["build_composite"](
        repo=research_repository,
        engine=stub_engine,
        registry=research_registry,
        revision_ids=(first.id, second.id),
        weighting="equal",
        universe="fixture-a-share",
        symbols=FIXTURE_SYMBOLS,
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        artifact_service=artifacts,
    )

    rows = research_repository.list_model_composites(model.model_id)
    assert len(rows) == 1
    row = rows[0]

    # 快照绑定: catalog 接缝 + 真实 artifact 字节 (checksum 验证) → as_of 横截面。
    # 复合帧只含 2024-01-02 的横截面 (面板末日因 forward_return 丢弃)。
    catalog = ExperimentCatalog(research_repository)
    snapshot = load_composite_snapshot(
        catalog,
        model_id=model.model_id,
        as_of=date(2024, 1, 2),
        data_dir=tmp_path / "app-data",
    )

    # 审计根: run 的 input_snapshot_sha256 == 复合行 input_snapshot_sha256。
    assert snapshot["input_snapshot_sha256"] == row["input_snapshot_sha256"]
    assert snapshot["input_snapshot_sha256"] == model.input_snapshot_sha256

    # 横截面 == artifact 字节里 [symbol, date, composite] 在 as_of 的取值。
    artifact_payload = json.loads(
        (tmp_path / "app-data" / row["artifact_relative_path"]).read_bytes()
    )
    expected = {
        item["symbol"]: float(item["composite"])
        for item in artifact_payload
        if item["date"] == "2024-01-02"
    }
    assert set(snapshot["symbols"]) == set(expected)
    assert {s: float(mu) for s, mu in zip(snapshot["symbols"], snapshot["mu"], strict=True)} == expected
    # 工件字节的 sha256 与记录的 output_sha256 一致 (checksum 验证)。
    artifact_bytes = (tmp_path / "app-data" / row["artifact_relative_path"]).read_bytes()
    assert sha256(artifact_bytes).hexdigest() == row["output_sha256"]
