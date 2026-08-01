from __future__ import annotations

from datetime import date, timedelta
import json
from hashlib import sha256
from pathlib import Path
import uuid

import numpy as np
import polars as pl
import pytest

from app.backtest.factor import FactorBacktestService, FactorConfig
from app.research.artifacts import ArtifactWriteError, EvaluationArtifactService
from app.research.evaluation import FactorEvaluationConfig, FactorEvaluationService
from app.research.factor_registry import FactorRegistry
from app.research.repository import ResearchRepository


class StubBacktestEngine:
    """A governed-panel boundary substitute; evaluation cannot inspect its source."""

    def __init__(self, panel: pl.DataFrame) -> None:
        self.panel = panel
        self.calls: list[dict] = []

    def load_panel(self, symbols, start, end, *, columns, asset_type):  # type: ignore[no-untyped-def]
        self.calls.append({"symbols": symbols, "start": start, "end": end, "columns": columns, "asset_type": asset_type})
        return self.panel.select([column for column in columns if column in self.panel.columns])


def _registry(tmp_path: Path) -> FactorRegistry:
    repository = ResearchRepository(tmp_path / "operational.db")
    repository.migrate()
    return FactorRegistry(repository)


def _panel() -> pl.DataFrame:
    first = date(2024, 1, 2)
    returns = {"000001.SZ": 0.0, "000002.SZ": 0.5, "000003.SZ": 0.1, "000004.SZ": 0.9}
    factors = {"000001.SZ": 1.0, "000002.SZ": 2.0, "000003.SZ": 3.0, "000004.SZ": 4.0}
    rows: list[dict] = []
    for symbol, value in factors.items():
        rows.append({"symbol": symbol, "date": first, "close": value})
        rows.append({"symbol": symbol, "date": first + timedelta(days=1), "close": value * (1 + returns[symbol])})
    return pl.DataFrame(rows)


def _config(revision_id: str, **overrides: object) -> FactorEvaluationConfig:
    values: dict[str, object] = {
        "factor_revision_id": revision_id,
        "universe": "fixture-a-share",
        "symbols": ("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"),
        "asset_type": "stock",
        "start": date(2024, 1, 2),
        "end": date(2024, 1, 3),
        "forward_return_horizon": 1,
        "rebalance": "daily",
        "missing_data_treatment": "drop",
        "warmup_treatment": "exclude",
        "warmup_days": 3,
        "n_groups": 2,
        "weight": "equal",
        "fees_pct": 0.0002,
        "slippage_bps": 5.0,
    }
    values.update(overrides)
    return FactorEvaluationConfig(**values)  # type: ignore[arg-type]


def test_evaluation_reports_distinct_ic_rankic_and_reproducible_evidence(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    revision = registry.create_factor(name="Close", expression="close", provenance={"author": "fixture"})
    engine = StubBacktestEngine(_panel())
    service = FactorEvaluationService(engine, registry, EvaluationArtifactService(tmp_path / "app-data"))

    result = service.evaluate(_config(revision.id))

    expected_ic = float(np.corrcoef([1.0, 2.0, 3.0, 4.0], [0.0, 0.5, 0.1, 0.9])[0, 1])
    assert result.status == "completed"
    assert result.evaluation_run_id and len(result.evaluation_run_id) == 32
    assert result.factor_revision == {
        "id": revision.id,
        "factor_id": revision.factor_id,
        "revision_number": 1,
        "dsl_version": "factor-dsl-v2",
        "canonical_expression": "close",
        "ast_signature": revision.ast_signature,
    }
    assert result.ic_series[0]["ic"] == pytest.approx(expected_ic)
    assert result.rank_ic_series[0]["rank_ic"] == pytest.approx(0.8)
    assert result.ic_series[0]["ic"] != result.rank_ic_series[0]["rank_ic"]
    assert result.ic_summary["observations"] == 1  # type: ignore[index]
    assert result.rank_ic_summary["observations"] == 1  # type: ignore[index]
    assert result.group_stats and result.long_short_stats
    assert result.resolved_config and result.resolved_config["forward_return_horizon"] == 1
    assert result.input_manifest and result.input_manifest["row_count"] == 8
    assert result.input_manifest["required_source_fields"] == ["symbol", "date", "close"]
    assert result.input_manifest["resolved_symbols"] == sorted(_config(revision.id).symbols)
    assert engine.calls == [{
        "symbols": sorted(_config(revision.id).symbols),
        "start": date(2023, 12, 30),
        "end": date(2024, 1, 3),
        "columns": ["symbol", "date", "close"],
        "asset_type": "stock",
    }]

    assert {artifact.relative_path.split("/")[0] for artifact in result.artifacts} == {"research_artifacts"}
    assert {artifact.evaluation_run_id for artifact in result.artifacts} == {result.evaluation_run_id}
    for artifact in result.artifacts:
        path = tmp_path / "app-data" / artifact.relative_path
        content = path.read_bytes()
        assert path.is_file()
        assert artifact.byte_size == len(content)
        assert artifact.checksum_sha256 == sha256(content).hexdigest()



@pytest.mark.parametrize(
    ("expression", "expected_factors"),
    [
        ("rank(close)", [1.0, 2.0, 1.0, 2.0]),
        ("zscore(close)", [-0.7071067811865475, 0.7071067811865475, -0.7071067811865475, 0.7071067811865475]),
        ("rolling_mean(close, 2)", [10.0, 20.0, 20.0, 30.0]),
    ],
)
def test_evaluation_artifacts_preserve_stateful_factor_partitions(
    tmp_path: Path, expression: str, expected_factors: list[float]
) -> None:
    registry = _registry(tmp_path)
    revision = registry.create_factor(name="Partitioned", expression=expression, provenance={"author": "fixture"})
    panel = pl.DataFrame(
        {
            "symbol": ["B", "A", "B", "A", "B", "A"],
            "date": [
                date(2024, 1, 3),
                date(2024, 1, 2),
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 4),
            ],
            "close": [40.0, 10.0, 20.0, 30.0, 80.0, 50.0],
        }
    )
    engine = StubBacktestEngine(panel)
    service = FactorEvaluationService(engine, registry, EvaluationArtifactService(tmp_path / "app-data"))

    result = service.evaluate(_config(revision.id, symbols=("A", "B")))

    assert result.status == "completed"
    assert result.resolved_config and result.resolved_config["symbols"] == ["A", "B"]
    assert result.input_manifest and result.input_manifest["required_source_fields"] == ["symbol", "date", "close"]
    assert result.ic_series and result.rank_ic_series
    assert engine.calls == [{
        "symbols": ["A", "B"],
        "start": date(2023, 12, 30),
        "end": date(2024, 1, 3),
        "columns": ["symbol", "date", "close"],
        "asset_type": "stock",
    }]

    signals_artifact = next(artifact for artifact in result.artifacts if artifact.relative_path.endswith("signals.json"))
    signals = json.loads((tmp_path / "app-data" / signals_artifact.relative_path).read_text())

    assert [(row["symbol"], row["date"]) for row in signals] == [
        ("A", "2024-01-02"),
        ("B", "2024-01-02"),
        ("A", "2024-01-03"),
        ("B", "2024-01-03"),
    ]
    assert [row["factor"] for row in signals] == pytest.approx(expected_factors)
    assert [row["forward_return"] for row in signals] == pytest.approx([2.0, 1.0, 2.0 / 3.0, 1.0])

def test_invalid_configuration_or_revision_fails_before_governed_load(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    revision = registry.create_factor(name="Close", expression="close")
    engine = StubBacktestEngine(_panel())
    service = FactorEvaluationService(engine, registry, EvaluationArtifactService(tmp_path / "app-data"))

    invalid_horizon = service.evaluate(_config(revision.id, forward_return_horizon=0))
    missing_revision = service.evaluate(_config("missing-revision"))

    assert invalid_horizon.status == "invalid"
    assert "forward_return_horizon" in invalid_horizon.diagnostics[0]
    assert missing_revision.status == "invalid"
    assert "does not exist" in missing_revision.diagnostics[0]
    assert engine.calls == []


def test_empty_governed_data_is_a_non_successful_run_without_artifacts(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    revision = registry.create_factor(name="Close", expression="close")
    engine = StubBacktestEngine(pl.DataFrame({"symbol": [], "date": [], "close": []}))
    service = FactorEvaluationService(engine, registry, EvaluationArtifactService(tmp_path / "app-data"))

    result = service.evaluate(_config(revision.id))

    assert result.status == "failed"
    assert result.evaluation_run_id is not None
    assert result.artifacts == ()
    assert result.diagnostics == ("governed panel is empty",)


def test_artifact_namespace_collision_never_replaces_prior_bytes(tmp_path: Path) -> None:
    artifacts = EvaluationArtifactService(tmp_path / "app-data")
    run_id = uuid.uuid4().hex
    original = artifacts.write_bundle(
        run_id,
        signals=[{"signal": 1}],
        metric_series=[{"ic": 0.1, "rank_ic": 0.2}],
        result={"status": "completed"},
    )
    signal_path = tmp_path / "app-data" / original[0].relative_path
    before = signal_path.read_bytes()

    with pytest.raises(ArtifactWriteError, match="already exists"):
        artifacts.write_bundle(
            run_id,
            signals=[{"signal": 999}],
            metric_series=[],
            result={"status": "replacement"},
        )

    assert signal_path.read_bytes() == before
    assert original[0].checksum_sha256 == sha256(before).hexdigest()


def test_factor_backtest_service_labels_pearson_and_spearman_separately() -> None:
    engine = StubBacktestEngine(_panel())
    result = FactorBacktestService(engine).run(
        FactorConfig(
            factor_name="close",
            symbols=["000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"],
            start=date(2024, 1, 2),
            end=date(2024, 1, 3),
            n_groups=2,
            rebalance="daily",
        )
    )

    assert result.error is None
    assert result.ic_series[0]["ic"] == pytest.approx(float(np.corrcoef([1, 2, 3, 4], [0, 0.5, 0.1, 0.9])[0, 1]), abs=1e-4)
    assert result.rank_ic_series[0]["rank_ic"] == pytest.approx(0.8)
    assert result.ic_mean != result.rank_ic_mean
