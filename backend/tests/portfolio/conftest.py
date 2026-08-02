"""Shared fixtures for the Phase 11 portfolio-optimization test suite.

Fixtures 提供 11-01 需要关闭的合同面: 治理面板边界替身 (StubBacktestEngine)、
确定性收益率矩阵 (已知协方差)、临时 operational.db 上的 PortfolioRepository、
以及 PortfolioArtifactService 的工件根目录。11-02 只搭建骨架; 测试文件在
模块缺失时是 RED, 由 11-01 转绿。
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from app.portfolio.repository import PortfolioRepository
from app.research.repository import ResearchRepository

FIXTURE_SYMBOLS = ("600000.SH", "600001.SH", "600002.SH", "600003.SH")


class StubBacktestEngine:
    """A governed-panel boundary substitute; portfolio code cannot inspect its source."""

    def __init__(self, panel: pl.DataFrame) -> None:
        self.panel = panel
        self.calls: list[dict[str, object]] = []

    def load_panel(self, symbols, start, end, *, columns, asset_type):  # type: ignore[no-untyped-def]
        self.calls.append(
            {
                "symbols": tuple(symbols) if symbols is not None else None,
                "start": start,
                "end": end,
                "columns": tuple(columns),
                "asset_type": asset_type,
            }
        )
        return self.panel.select([column for column in columns if column in self.panel.columns])


@pytest.fixture
def fixture_panel() -> pl.DataFrame:
    """A two-date, four-symbol panel with deterministic close and forward returns."""
    first = date(2024, 1, 2)
    returns = {"600000.SH": 0.0, "600001.SH": 0.5, "600002.SH": 0.1, "600003.SH": 0.9}
    factors = {"600000.SH": 1.0, "600001.SH": 2.0, "600002.SH": 3.0, "600003.SH": 4.0}
    rows: list[dict[str, object]] = []
    for symbol, value in factors.items():
        rows.append({"symbol": symbol, "date": first, "close": value})
        rows.append(
            {
                "symbol": symbol,
                "date": first + timedelta(days=1),
                "close": value * (1 + returns[symbol]),
            }
        )
    return pl.DataFrame(rows)


@pytest.fixture
def fixture_returns() -> np.ndarray:
    """Deterministic returns matrix with a known (PSD) covariance structure.

    Two highly correlated assets plus two orthogonal ones: the correlation
    pattern lets HRP cluster ordering tests assert adjacency of the pair.
    """
    rows = np.array(
        [
            [0.010, 0.012, 0.008, 0.006],
            [0.011, 0.013, 0.007, 0.005],
            [0.012, 0.014, 0.009, 0.007],
            [0.009, 0.011, 0.010, 0.004],
            [0.013, 0.015, 0.006, 0.008],
            [0.010, 0.012, 0.011, 0.006],
        ]
    )
    return rows


@pytest.fixture
def portfolio_repository(tmp_path: Path) -> PortfolioRepository:
    repository = PortfolioRepository(tmp_path / "operational.db")
    repository.migrate()
    return repository


@pytest.fixture
def artifact_root(tmp_path: Path) -> Path:
    """App-data root for PortfolioArtifactService (11-01's write_bundle)."""
    return tmp_path / "app-data"


@pytest.fixture
def fixture_composite(
    portfolio_repository: PortfolioRepository, artifact_root: Path
) -> dict[str, object]:
    """A recorded composite model + snapshot identity for the tracer pipeline.

    Mirrors the Phase 10 seam: a factor_model_models definition plus one
    factor_model_composites row; ``input_snapshot_sha256`` is the audit root the
    run row must equal. Writes the composite artifact under the app-data root so
    the checksum-verified snapshot binding (11-05/11-06) reads real bytes.
    """

    artifact_dir = Path(artifact_root) / "research_artifacts" / ("0" * 32)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    signals = [
        {"symbol": "600000.SH", "date": "2026-08-01", "composite": 0.5},
        {"symbol": "600001.SH", "date": "2026-08-01", "composite": 0.25},
    ]
    payload = json.dumps(
        signals, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    artifact_path = artifact_dir / "signals.json"
    artifact_path.write_bytes(payload)
    output_sha256 = hashlib.sha256(payload).hexdigest()

    research = ResearchRepository(portfolio_repository.database_path)
    research.insert_model_definition(
        model_id="composite-model-v1",
        name="fixture composite model",
        weighting="equal",
        revision_ids=[],
        weights={},
        input_snapshot_sha256="f" * 64,
    )
    research.insert_model_composite(
        model_id="composite-model-v1",
        output_sha256=output_sha256,
        artifact_relative_path=f"research_artifacts/{'0' * 32}/signals.json",
        input_snapshot_sha256="f" * 64,
    )
    return {"model_id": "composite-model-v1", "input_snapshot_sha256": "f" * 64}


@pytest.fixture
def fixture_returns_long() -> np.ndarray:
    """Deterministic 24-obs x 4-symbol returns with a CONSTRUCTED drawdown segment.

    A seeded 24 x 4 matrix whose obs 8-11 form a portfolio dip (approx -5% then
    -4% before recovery) so 12-06's period detection has a known target. The
    equal-weight portfolio return at obs 8 ~ -0.05 and obs 9 ~ -0.04 drive the
    underwater curve below the 2% depth threshold; obs 12-13 recover (the
    underwater curve returns to 0 exactly at obs 13).
    """
    rng = np.random.default_rng(20260802)
    rows = rng.normal(0.0005, 0.001, size=(24, 4))
    # Constructed drawdown segment: obs 8-9 deep negative dip, obs 10-11 partial
    # recovery, obs 12-13 recovery above the prior peak.
    rows[8] = [-0.050, -0.049, -0.051, -0.050]
    rows[9] = [-0.040, -0.039, -0.041, -0.040]
    rows[10] = [0.005, 0.006, 0.004, 0.005]
    rows[11] = [-0.010, -0.009, -0.011, -0.010]
    rows[12] = [0.090, 0.091, 0.089, 0.090]
    rows[13] = [0.040, 0.041, 0.039, 0.040]
    return rows


@pytest.fixture
def fixture_attribution_run(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
    fixture_composite: dict[str, object],
) -> dict[str, object]:
    """A recorded min-vol run on the fixture composite for the attribution spine.

    Mirrors the Phase 11 tracer pipeline: records one optimal run via
    ``run_optimization`` (fixture_mode=True) bound to the fixture composite
    identity, and returns the run record (weights + checksum-bound covariance
    artifact). 12-01/12-04/12-06 consume this as the attribution input.
    """
    from app.portfolio.optimizer import run_optimization

    request = {
        "objective": "min_volatility",
        "as_of": "2026-08-01",
        "universe": "cn-a-share",
        "model_id": "composite-model-v1",
        "expected_return_method": "composite-zscore-v1",
        "render_baselines": True,
        "per_instrument_cap": 0.10,
        "min_cash": 0.05,
        "turnover_coef": 0.0014,
    }
    run = run_optimization(
        request,
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
        fixture_mode=True,
    )
    assert run["problem_status"] == "optimal"
    return run


@pytest.fixture
def fixture_rebalance_run(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
    fixture_composite: dict[str, object],
) -> dict[str, object]:
    """A recorded optimal Phase 11 run for the RebalancePlan spine (14-01/14-02).

    Mirrors ``fixture_attribution_run``: one optimal min-vol run bound to the
    fixture composite identity via ``run_optimization`` (fixture_mode=True).
    ``build_rebalance_plan`` (14-01) consumes its ``output_weights``; the
    repository-level 14-02 cases consume its ``id`` + ``input_snapshot_sha256``
    to record rebalance_plans rows.
    """
    from app.portfolio.optimizer import run_optimization

    request = {
        "objective": "min_volatility",
        "as_of": "2026-08-01",
        "universe": "cn-a-share",
        "model_id": "composite-model-v1",
        "expected_return_method": "composite-zscore-v1",
        "render_baselines": True,
        "per_instrument_cap": 0.10,
        "min_cash": 0.05,
        "turnover_coef": 0.0014,
    }
    run = run_optimization(
        request,
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
        fixture_mode=True,
    )
    assert run["problem_status"] == "optimal"
    return run


@pytest.fixture
def fixture_prices() -> dict[str, float]:
    """Deterministic {symbol: price} for FIXTURE_SYMBOLS (14-01/14-03 lot-sizing)."""
    return {
        "600000.SH": 10.0,
        "600001.SH": 20.0,
        "600002.SH": 15.0,
        "600003.SH": 30.0,
    }


@pytest.fixture
def fixture_plan_inputs(
    fixture_prices: dict[str, float],
) -> dict[str, object]:
    """Researcher-provided RebalancePlan inputs: equity, blocked set, fees, odd lots.

    The lot-sizing adapter (14-01/14-03) consumes these: a blocked symbol
    (``600002.SH``), one odd-lot position (``600001.SH`` at 150 = one 100-share
    board lot + a 50-share odd remainder, so odd-lot sell is testable), and the
    MatcherConfig fee model the adapter reuses from backtest/engine.py.
    """
    from app.backtest.engine import MatcherConfig

    return {
        "equity": 1_000_000.0,
        "blocked": {"600002.SH"},
        "matcher_config": MatcherConfig(
            commission_pct=0.0003, stamp_tax_pct=0.001, slippage_bps=5.0
        ),
        "odd_lot_positions": {"600001.SH": 150},
        "min_cash": 50_000.0,
    }
