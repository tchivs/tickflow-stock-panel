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


def _monthly_panel() -> pl.DataFrame:
    """A two-calendar-month fixture with deterministic per-date IC values."""
    d1, d2, d3, d4 = date(2024, 1, 2), date(2024, 1, 3), date(2024, 2, 1), date(2024, 2, 2)
    closes = {
        "000001.SZ": (1.0, 1.5, 2.0, 3.0),
        "000002.SZ": (2.0, 2.6, 4.0, 3.0),
        "000003.SZ": (3.0, 3.6, 6.0, 3.0),
        "000004.SZ": (4.0, 4.4, 8.0, 3.0),
    }
    rows: list[dict] = []
    for symbol, values in closes.items():
        for day, value in zip((d1, d2, d3, d4), values):
            rows.append({"symbol": symbol, "date": day, "close": value, "ma20": 1.0})
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


def test_evidence_metrics_match_numpy_reference(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    revision = registry.create_factor(name="Close", expression="close")
    engine = StubBacktestEngine(_monthly_panel())
    service = FactorEvaluationService(engine, registry, EvaluationArtifactService(tmp_path / "app-data"))

    result = service.evaluate(_config(revision.id, end=date(2024, 2, 2)))

    assert result.status == "completed"
    assert result.icir is not None
    assert result.monthly_robustness is not None
    assert result.coverage["mean"] is not None

    monthly: dict[str, list[float]] = {}
    for row in result.ic_series:
        monthly.setdefault(str(row["date"])[:7], []).append(float(row["ic"]))
    ic_monthly = np.array([float(np.mean(monthly[month])) for month in sorted(monthly)])
    assert result.icir == pytest.approx(float(np.mean(ic_monthly) / np.std(ic_monthly)))
    assert result.monthly_robustness == pytest.approx(float(np.mean(ic_monthly > 0)))
    assert len(result.monthly_ic_series) == len(ic_monthly)
    for entry, month in zip(result.monthly_ic_series, sorted(monthly)):
        assert entry["month"] == month
        assert entry["ic_monthly"] == pytest.approx(float(np.mean(monthly[month])))


def test_coverage_is_computed_pre_filter_on_resolved_universe(tmp_path: Path) -> None:
    """Non-finite factor rows make coverage < 1.0, proving it is not post-filter."""
    registry = _registry(tmp_path)
    revision = registry.create_factor(name="CloseMa20", expression="close / ma20")
    panel = _monthly_panel().with_columns(
        pl.when((pl.col("symbol") == "000003.SZ") & (pl.col("date") == date(2024, 2, 1)))
        .then(0.0)
        .otherwise(pl.col("ma20"))
        .alias("ma20")
    )
    engine = StubBacktestEngine(panel)
    service = FactorEvaluationService(engine, registry, EvaluationArtifactService(tmp_path / "app-data"))

    result = service.evaluate(_config(revision.id, end=date(2024, 2, 2)))

    assert result.status == "completed"
    assert result.coverage["mean"] is not None
    assert result.coverage["mean"] < 1.0
    series_by_date = {entry["date"]: entry["coverage"] for entry in result.coverage["coverage_series"]}
    assert series_by_date["2024-02-01"] == pytest.approx(3.0 / 4.0)
    assert series_by_date["2024-01-02"] == pytest.approx(1.0)


def test_evaluation_manifest_records_universe_resolution_fingerprint(tmp_path: Path) -> None:
    """Every completed evaluation manifest carries a universe_resolution block."""
    from app.research.universe import UniverseResolver

    repository = ResearchRepository(tmp_path / "operational.db")
    repository.migrate()
    for symbol in ("000001.SZ", "000002.SZ", "000003.SZ", "000004.SZ"):
        repository.insert_universe_membership(
            universe_name="fixture-a-share",
            symbol=symbol,
            asset_type="stock",
            effective_date="2024-01-01",
            state="listed",
            source="instruments-sync",
            provenance_json={},
        )
    registry = FactorRegistry(repository)
    revision = registry.create_factor(name="Close", expression="close")
    engine = StubBacktestEngine(_panel())
    service = FactorEvaluationService(
        engine,
        registry,
        EvaluationArtifactService(tmp_path / "app-data"),
        universe_resolver=UniverseResolver(repository),
    )

    result = service.evaluate(_config(revision.id))

    assert result.status == "completed"
    assert result.input_manifest is not None
    block = result.input_manifest["universe_resolution"]
    assert block["method"] == "factor_universe_membership/v1"
    assert len(block["membership_fingerprint"]) == 64
    assert block["per_date_symbol_counts"]["min"] >= 1
    assert block["excluded_delisted"] == []


def test_evaluation_manifest_config_symbols_fallback_when_no_resolver(tmp_path: Path) -> None:
    """Without a resolver the manifest records the config-symbols fallback."""
    registry = _registry(tmp_path)
    revision = registry.create_factor(name="Close", expression="close")
    engine = StubBacktestEngine(_panel())
    service = FactorEvaluationService(engine, registry, EvaluationArtifactService(tmp_path / "app-data"))

    result = service.evaluate(_config(revision.id))

    assert result.status == "completed"
    block = result.input_manifest["universe_resolution"]  # type: ignore[index]
    assert block["method"] == "config-symbols"
    assert len(block["membership_fingerprint"]) == 64
    assert block["per_date_symbol_counts"] == {"min": 4, "median": 4.0, "max": 4}


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
