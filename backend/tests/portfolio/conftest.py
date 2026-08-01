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
