"""End-to-end tracer proofs for the portfolio optimization + attribution spines.

11-01 walks the Phase 11 spine on a fixture: composite snapshot identity → sample
covariance + PSD gate → min-vol QP → immutable append-only run record with HRP
baseline + PSD provenance → checksum-verified weights artifact read-back.

12-01 walks the Phase 12 attribution spine on the same fixture run: run record →
checksum-verified covariance artifact (covariance_sha256) → exposure + marginal
contribution → HARD sum(MC) == variance reconciliation → O_EXCL analysis artifact
→ append-only evidence row → read-back; a second analysis appends a second row;
the drawdown identity path (underwater curve + empty periods + evidence row) is
wired end-to-end; tampered covariance bytes fail closed with no evidence written.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.portfolio.analyzer import run_attribution, run_drawdown
from app.portfolio.artifacts import ArtifactReadError, ArtifactWriteError, PortfolioArtifactService
from app.portfolio.optimizer import run_optimization
from app.portfolio.repository import PortfolioRepository


def _fixture_long_returns() -> np.ndarray:
    """Deterministic 24-obs x 12-symbol panel aligned to the fixture run universe.

    The fixture run (fixture_mode) uses 12 SYM symbols; the drawdown identity path
    needs returns whose columns align with the run's output weights. A flat
    positive series keeps the underwater curve at 0 everywhere (period_count 0,
    max_depth 0.0) — the identity path proves the wiring, not period detection.
    """
    return np.full((24, 12), 0.001)


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


def test_attribution_spine_end_to_end_on_fixture_run(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
    fixture_attribution_run: dict[str, object],
) -> None:
    """The Phase 12 tracer: run → checksum-bound covariance → attribution → evidence.

    Walks the full spine on a fixture: fixture_attribution_run (min-vol run on the
    fixture composite) → run_attribution reads the run's OWN covariance artifact
    (covariance_sha256 verified) → exposure/MC → hard reconciliation → O_EXCL
    artifact → append-only evidence row. A second run_attribution appends a second
    evidence row (no O_EXCL clash). run_drawdown proves the drawdown identity path
    (underwater + empty periods + evidence row). Tampered covariance bytes fail
    closed (ArtifactReadError) with no evidence row written.
    """
    run = fixture_attribution_run
    run_id = str(run["id"])
    service = PortfolioArtifactService(artifact_root)

    # --- (1) checksum-verified covariance consumption (never a live recompute) ---
    cov_bytes = service.read_artifact(
        run["risk_model_detail"]["covariance_artifact_relative_path"],
        checksum_sha256=run["risk_model_detail"]["covariance_sha256"],
    )
    cov = np.asarray(json.loads(cov_bytes.decode("utf-8")), dtype=float)
    weights = np.asarray(list(run["output_weights"].values()), dtype=float)
    expected_variance = float(weights @ (cov @ weights))

    # --- (2) run_attribution: hard reconciliation on the run's own bytes ---
    evidence = run_attribution(
        run_id, repository=portfolio_repository, artifact_service_root=artifact_root
    )
    assert evidence["attribution_type"] == "exposure_contribution"
    assert evidence["risk_model"] == run["risk_model"]
    assert evidence["reconciliation"] is not None
    assert np.isclose(
        evidence["reconciliation"]["portfolio_variance"], expected_variance, rtol=1e-12
    )
    # evidence reconciliation carries the variance decomposition summary.
    assert (
        abs(
            evidence["reconciliation"]["sum_contributions"]
            - evidence["reconciliation"]["portfolio_variance"]
        )
        <= 1e-12 * expected_variance
    )
    # artifact read-back checksum-verifies and reconciles to the same variance.
    payload = json.loads(
        service.read_artifact(
            evidence["artifact_relative_path"], checksum_sha256=evidence["output_sha256"]
        ).decode("utf-8")
    )
    assert np.isclose(payload["portfolio_variance"], expected_variance, rtol=1e-12)
    assert abs(sum(payload["marginal_contributions"].values()) - expected_variance) <= (
        1e-12 * expected_variance
    )

    # --- (3) append-only: a SECOND run_attribution writes a SECOND evidence row ---
    evidence2 = run_attribution(
        run_id, repository=portfolio_repository, artifact_service_root=artifact_root
    )
    assert evidence2["id"] != evidence["id"]
    rows = portfolio_repository.list_attribution_evidence(run_id=run_id)
    assert len(rows) == 2
    assert {row["id"] for row in rows} == {evidence["id"], evidence2["id"]}

    # --- (4) write_analysis_artifact discipline: O_EXCL + missing namespace ---
    probe = service.write_analysis_artifact(
        run_id, subdir="attribution", filename="probe.json", payload={"probe": 1}
    )
    # a second write to the SAME path fails (O_EXCL) — artifacts are immutable.
    with pytest.raises(ArtifactWriteError):
        service.write_analysis_artifact(
            run_id, subdir="attribution", filename="probe.json", payload={"probe": 1}
        )
    assert json.loads(
        service.read_artifact(probe.relative_path, checksum_sha256=probe.checksum_sha256)
    ) == {"probe": 1}
    # a missing run namespace is never recreated.
    with pytest.raises(ArtifactWriteError):
        service.write_analysis_artifact(
            "f" * 32, subdir="attribution", filename="x.json", payload={}
        )

    # --- (5) drawdown identity path: underwater + empty periods + evidence row ---
    dd = run_drawdown(
        run_id,
        returns=_fixture_long_returns(),
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
    )
    assert dd["attribution_type"] == "drawdown"
    assert dd["risk_model"] == run["risk_model"]
    assert dd["reconciliation"]["period_count"] == 0
    assert dd["reconciliation"]["max_depth"] == 0.0
    dd_payload = json.loads(
        service.read_artifact(
            dd["artifact_relative_path"], checksum_sha256=dd["output_sha256"]
        ).decode("utf-8")
    )
    assert dd_payload["periods"] == []
    assert dd_payload["max_depth"] == 0.0

    # --- (6) tampered covariance bytes fail closed with NO evidence row ---
    cov_path = artifact_root / str(run["risk_model_detail"]["covariance_artifact_relative_path"])
    original = cov_path.read_bytes()
    count_before = len(portfolio_repository.list_attribution_evidence(run_id=run_id))
    cov_path.write_bytes(b"tampered")
    try:
        with pytest.raises(ArtifactReadError):
            run_attribution(
                run_id, repository=portfolio_repository, artifact_service_root=artifact_root
            )
    finally:
        cov_path.write_bytes(original)
    assert len(portfolio_repository.list_attribution_evidence(run_id=run_id)) == count_before
