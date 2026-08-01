"""RED scaffold for the Phase 11 end-to-end optimization pipeline.

Wave 0 (11-02) scaffold: the full spine — composite snapshot → sample
covariance + PSD gate → min-vol QP → immutable run record → checksum-verified
artifacts — is exercised by 11-01's tracer. This file is RED until the
portfolio modules exist.
"""
from __future__ import annotations

from pathlib import Path

from app.portfolio.optimizer import run_optimization

from app.portfolio.repository import PortfolioRepository


def test_full_pipeline_min_vol_run_is_immutable_and_checksum_bound(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
) -> None:
    """The whole spine works on a fixture and lands as an immutable run."""
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
    )
    assert run["problem_status"] == "optimal"
    assert run["solver_name"] in ("CLARABEL", "OSQP")
    assert run["solver_version"]
    assert len(run["input_snapshot_sha256"]) == 64
    weights = run["output_weights"]
    assert sum(weights.values()) <= 1 - 0.05 + 1e-8
    assert run["baseline_weights"] is not None

    fetched = portfolio_repository.get_optimization_run(run["id"])
    assert fetched is not None
    assert fetched["output_weights"] == weights
