"""End-to-end tracer proof of the Phase 10 spine (FACT-01..06).

One integration test walks the complete vertical slice on a fixture: factor
revision → admission gates → append-only verdict (including a rejection path) →
evaluation with the full monthly evidence set → deterministic composite (equal and
IC-weighted) → catalogued evidence with the new metrics.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from app.research.admission import ADMISSION_POLICY_VERSION, run_admission
from app.research.artifacts import EvaluationArtifactService
from app.research.catalog import ExperimentCatalog
from app.research.evaluation import FactorEvaluationConfig, FactorEvaluationService
from app.research.factor_registry import FactorRegistry
from app.research.models import build_composite
from app.research.repository import ResearchRepository
from tests.research.conftest import StubBacktestEngine

# Hadamard-8 rows 1..7 are mutually orthogonal mean-zero cross-sections.  The
# fixture schedules each trading date's forward return on a rotating Hadamard row,
# so a factor built from ``row(t)`` is exactly orthogonal to the displaced label
# ``row(t+1)`` — the shifted-label leakage gate sees ~0 IC, and the train/val mean
# IC is ~0.8.  This is a deterministic fixture: no RNG state.
_H = np.array(
    [
        [1, 1, 1, 1, 1, 1, 1, 1],
        [1, -1, 1, -1, 1, -1, 1, -1],
        [1, 1, -1, -1, 1, 1, -1, -1],
        [1, -1, -1, 1, 1, -1, -1, 1],
        [1, 1, 1, 1, -1, -1, -1, -1],
        [1, -1, 1, -1, -1, 1, -1, 1],
        [1, 1, -1, -1, -1, -1, 1, 1],
        [1, -1, -1, 1, -1, 1, 1, -1],
    ],
    dtype=float,
)
_HADAMARD_ROWS = _H[1:]  # 7 mean-zero orthogonal rows


def _hadamard_row(index: int) -> np.ndarray:
    return _HADAMARD_ROWS[index % 7]


def _trading_days(n_days: int, *, start: date) -> list[date]:
    days: list[date] = []
    cursor = start
    while len(days) < n_days:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _wide_panel() -> pl.DataFrame:
    """60 trading days x 8 symbols; forward return = 2% * Hadamard row(t)."""
    symbols = [f"{i:06d}.SH" for i in range(1, 9)]
    days = _trading_days(60, start=date(2024, 1, 2))
    n_day = len(days)
    t_idx = np.arange(n_day)
    mixing = 0.5 + 0.8 * np.sin(t_idx / 5.0)  # per-date factor-vs-return alignment
    mixing_two = 0.5 + 0.8 * np.cos(t_idx / 7.0)  # decorrelated from mixing

    returns = np.array([_hadamard_row(t) for t in range(n_day)])
    close = np.zeros((n_day, 8))
    close[0] = 10.0
    for t in range(1, n_day):
        close[t] = close[t - 1] * (1 + 0.02 * returns[t - 1])
    volume = np.array(
        [_hadamard_row(t) + mixing[t] * _hadamard_row(t + 3) for t in range(n_day)]
    )
    momentum_5d = np.array(
        [_hadamard_row(t) + mixing_two[t] * _hadamard_row(t + 2) for t in range(n_day)]
    )

    rows: list[dict] = []
    for t, day in enumerate(days):
        for i, symbol in enumerate(symbols):
            rows.append(
                {
                    "symbol": symbol,
                    "date": day,
                    "close": float(close[t, i]),
                    "volume": float(volume[t, i]),
                    "momentum_5d": float(momentum_5d[t, i]),
                }
            )
    return pl.DataFrame(rows)


def _membership(panel: pl.DataFrame) -> pl.DataFrame:
    return panel.select(["symbol", "date"]).unique()


@pytest.fixture
def pipeline_context(tmp_path: Path):
    repository = ResearchRepository(tmp_path / "operational.db")
    repository.migrate()
    registry = FactorRegistry(repository)
    panel = _wide_panel()
    engine = StubBacktestEngine(panel)
    resolver = _FixtureResolver(_membership(panel))
    artifacts = EvaluationArtifactService(tmp_path / "app-data")
    evaluator = FactorEvaluationService(engine, registry, artifacts, universe_resolver=resolver)
    catalog = ExperimentCatalog(repository)
    return {
        "repo": repository,
        "registry": registry,
        "engine": engine,
        "resolver": resolver,
        "evaluator": evaluator,
        "catalog": catalog,
        "symbols": tuple(sorted(panel["symbol"].unique().to_list())),
        "start": date(2024, 1, 2),
        "end": date(2024, 3, 28),
    }


class _FixtureResolver:
    """Minimal per-date membership resolver bound to the fixture panel."""

    def __init__(self, membership: pl.DataFrame) -> None:
        self.membership = membership

    def resolve_universe_daily(self, *, universe_name, start, end, asset_type="stock"):
        del universe_name, asset_type
        return self.membership.filter(
            (pl.col("date") >= start) & (pl.col("date") <= end)
        )

    def resolve_universe(self, *, universe_name, as_of, asset_type="stock"):
        del universe_name, asset_type
        symbols = frozenset(
            self.membership.filter(pl.col("date") <= as_of)["symbol"].unique().to_list()
        )
        return symbols, "fixture-fingerprint"


def _evaluation_config(ctx, revision_id: str) -> FactorEvaluationConfig:
    return FactorEvaluationConfig(
        factor_revision_id=revision_id,
        universe="fixture-a-share",
        symbols=ctx["symbols"],
        asset_type="stock",
        start=ctx["start"],
        end=ctx["end"],
        forward_return_horizon=1,
        rebalance="daily",
        missing_data_treatment="drop",
        warmup_treatment="exclude",
        warmup_days=3,
        n_groups=2,
        weight="equal",
        fees_pct=0.0,
        slippage_bps=0.0,
    )


def test_admit_evaluate_compose_catalog_spine(pipeline_context) -> None:
    ctx = pipeline_context
    revision_a = ctx["registry"].create_factor(name="Volume", expression="volume")
    revision_b = ctx["registry"].create_factor(name="Momentum", expression="momentum_5d")

    verdict_a = run_admission(
        ctx["repo"],
        engine=ctx["engine"],
        registry=ctx["registry"],
        revision_id=revision_a.id,
        universe="fixture-a-share",
        start=ctx["start"],
        end=ctx["end"],
        universe_resolver=ctx["resolver"],
        horizon=1,
    )
    assert verdict_a["verdict"] == "admitted"
    assert verdict_a["policy_version"] == ADMISSION_POLICY_VERSION
    assert verdict_a["input_snapshot_sha256"] and len(verdict_a["input_snapshot_sha256"]) == 64
    assert verdict_a["gates_json"]
    assert verdict_a["candidate_trail_json"]["gate_results"]
    assert verdict_a["resolved_universe_json"]["membership_fingerprint"]

    result_a = ctx["evaluator"].evaluate(_evaluation_config(ctx, revision_a.id))
    assert result_a.status == "completed"
    assert result_a.icir is not None
    assert result_a.monthly_robustness is not None
    assert result_a.coverage["mean"] is not None
    assert result_a.monthly_ic_series

    snapshot = ctx["catalog"].record_factor_evaluation(result_a)
    assert snapshot.metrics["icir"] == result_a.icir
    assert snapshot.metrics["monthly_robustness"] == result_a.monthly_robustness
    assert snapshot.metrics["coverage"]["mean"] == result_a.coverage["mean"]
    assert snapshot.metrics["monthly_ic_series"]

    # A second admitted factor with decorrelated IC series; catalogued evidence
    # provides the mean-IC weights for the IC-weighted composite.
    verdict_b = run_admission(
        ctx["repo"],
        engine=ctx["engine"],
        registry=ctx["registry"],
        revision_id=revision_b.id,
        universe="fixture-a-share",
        start=ctx["start"],
        end=ctx["end"],
        universe_resolver=ctx["resolver"],
        horizon=1,
    )
    assert verdict_b["verdict"] == "admitted"
    result_b = ctx["evaluator"].evaluate(_evaluation_config(ctx, revision_b.id))
    ctx["catalog"].record_factor_evaluation(result_b)

    equal = build_composite(
        ctx["repo"],
        engine=ctx["engine"],
        registry=ctx["registry"],
        revision_ids=(revision_a.id, revision_b.id),
        weighting="equal",
        universe="fixture-a-share",
        start=ctx["start"],
        end=ctx["end"],
        symbols=ctx["symbols"],
        universe_resolver=ctx["resolver"],
    )
    assert set(equal.weights) == {revision_a.id, revision_b.id}
    assert list(equal.weights.values()) == pytest.approx([0.5, 0.5])
    assert len(equal.input_snapshot_sha256) == 64

    weighted = build_composite(
        ctx["repo"],
        engine=ctx["engine"],
        registry=ctx["registry"],
        revision_ids=(revision_a.id, revision_b.id),
        weighting="ic_weighted",
        universe="fixture-a-share",
        start=ctx["start"],
        end=ctx["end"],
        symbols=ctx["symbols"],
        universe_resolver=ctx["resolver"],
    )
    assert weighted.weighting == "ic_weighted"
    assert sum(weighted.weights.values()) == pytest.approx(1.0)
    assert all(value > 0 for value in weighted.weights.values())
    # weights are proportional to catalogued mean IC, not the equal-weight prior
    assert weighted.weights != equal.weights

    assert ctx["repo"].get_model_definition(equal.model_id) is not None
    assert ctx["repo"].get_model_definition(weighted.model_id) is not None


def test_rejection_path_records_identical_verdict(pipeline_context) -> None:
    ctx = pipeline_context
    # A factor whose expression references only an uninformative rotation (row t+1)
    # has ~0 IC, so the train_ic gate rejects it deterministically.
    revision = ctx["registry"].create_factor(
        name="ZeroIc", expression="volume", provenance={"source": "manual", "ticket": "R-42"}
    )
    # Override the fixture: use the uninformative rotation as the factor column by
    # creating a second revision on a panel where volume carries no signal.
    ctx["engine"].panel = _zero_ic_panel()
    verdict = run_admission(
        ctx["repo"],
        engine=ctx["engine"],
        registry=ctx["registry"],
        revision_id=revision.id,
        universe="fixture-a-share",
        start=ctx["start"],
        end=ctx["end"],
        universe_resolver=None,
        horizon=1,
    )
    assert verdict["verdict"] == "rejected"
    assert verdict["reason"] in {"no_lookahead", "no_label_leakage", "similarity_dedup", "train_ic", "val_ic"}
    assert verdict["gates_json"]
    assert verdict["candidate_trail_json"]["gate_results"]
    trail = verdict["candidate_trail_json"]
    assert trail["provenance"] == {"source": "manual", "ticket": "R-42"}

    with pytest.raises(ValueError, match="already exists"):
        run_admission(
            ctx["repo"],
            engine=ctx["engine"],
            registry=ctx["registry"],
            revision_id=revision.id,
            universe="fixture-a-share",
            start=ctx["start"],
            end=ctx["end"],
            universe_resolver=None,
            horizon=1,
        )


def _zero_ic_panel() -> pl.DataFrame:
    """A panel whose volume column is a future rotation: IC is ~0, rejected at train_ic."""
    symbols = [f"{i:06d}.SH" for i in range(1, 9)]
    days = _trading_days(60, start=date(2024, 1, 2))
    n_day = len(days)
    returns = np.array([_hadamard_row(t) for t in range(n_day)])
    close = np.zeros((n_day, 8))
    close[0] = 10.0
    for t in range(1, n_day):
        close[t] = close[t - 1] * (1 + 0.02 * returns[t - 1])
    # volume is aligned with the NEXT day's return (row t+1), so its IC with the
    # forward return (row t) is ~0.
    volume = np.array([_hadamard_row(t + 1) for t in range(n_day)])
    rows: list[dict] = []
    for t, day in enumerate(days):
        for i, symbol in enumerate(symbols):
            rows.append(
                {
                    "symbol": symbol,
                    "date": day,
                    "close": float(close[t, i]),
                    "volume": float(volume[t, i]),
                }
            )
    return pl.DataFrame(rows)
