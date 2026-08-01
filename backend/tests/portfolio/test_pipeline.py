"""End-to-end tracer proof for the Phase 11 optimization spine (11-01).

Walks the full spine on a fixture: composite snapshot identity (recorded in
factor_model_composites) → sample covariance + PSD gate → min-vol QP under the
constraint stack → immutable append-only run record with HRP baseline + PSD
provenance → checksum-verified weights artifact read-back.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.portfolio.artifacts import PortfolioArtifactService
from app.portfolio.optimizer import run_optimization
from app.portfolio.repository import PortfolioRepository


def test_full_pipeline_min_vol_run_is_immutable_and_checksum_bound(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
    fixture_composite: dict[str, object],
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
        snapshot=fixture_composite,
        fixture_mode=True,
    )
    assert run["problem_status"] == "optimal"
    assert run["solver_name"] in ("CLARABEL", "OSQP")
    assert run["solver_version"]
    # 审计根: run 的 input_snapshot_sha256 == 复合快照的 input_snapshot_sha256。
    assert run["input_snapshot_sha256"] == fixture_composite["input_snapshot_sha256"]
    assert len(run["input_snapshot_sha256"]) == 64
    # PSD 溯源永不静默: 要么无需修复 (none), 要么记录了 eigen_clip。
    assert run["risk_model_detail"]["psd_repair"]["method"] in ("none", "eigen_clip")

    weights = run["output_weights"]
    assert sum(weights.values()) <= 1 - 0.05 + 1e-8
    # HRP 基线按 (1 - min_cash) 缩放渲染。
    baseline = run["baseline_weights"]
    assert baseline is not None
    assert abs(sum(baseline.values()) - (1 - 0.05)) < 1e-6

    # 不可变 run 行: get 回读与返回记录一致。
    fetched = portfolio_repository.get_optimization_run(run["id"])
    assert fetched is not None
    assert fetched["output_weights"] == weights
    assert fetched["input_snapshot_sha256"] == fixture_composite["input_snapshot_sha256"]

    # 权重工件 checksum 校验读取 (O_EXCL + fsync + sha256 的读取侧)。
    service = PortfolioArtifactService(artifact_root)
    payload = service.read_artifact(
        run["weights_artifact_relative_path"],
        checksum_sha256=run["output_sha256"],
    )
    assert json.loads(payload.decode("utf-8")) == weights
