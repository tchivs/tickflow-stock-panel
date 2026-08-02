"""RED scaffold for portfolio/risk.py — sample covariance + PSD check/repair.

Wave 0 (11-02) scaffold: these contracts come from RESEARCH.md `## PSD
Check/Repair`; the module they import is created by 11-01, so this file is
provably RED until then.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from app.portfolio.risk import check_psd, repair_psd, sample_covariance


def test_sample_covariance_matches_numpy_reference(fixture_returns: np.ndarray) -> None:
    """PFOL-01: sample covariance on the common all-finite window matches np.cov."""
    cov = sample_covariance(fixture_returns)
    expected = np.cov(fixture_returns, rowvar=False)
    assert np.allclose(cov, expected)


def test_check_psd_reports_true_min_eigenvalue() -> None:
    """A deliberately indefinite matrix reports its true (negative) min eigenvalue."""
    indefinite = np.array([[1.0, 1.2], [1.2, 1.0]])
    minimum, eigvals = check_psd(indefinite)
    assert minimum < 0.0
    assert np.isclose(minimum, float(eigvals.min()))


def test_check_psd_accepts_psd_matrix() -> None:
    psd = np.array([[2.0, 0.0], [0.0, 1.0]])
    minimum, _ = check_psd(psd)
    assert minimum >= 0.0


def test_repair_psd_returns_psd_matrix_and_provenance() -> None:
    """PFOL-01: eigen_clip repair returns a PSD matrix plus the full provenance dict."""
    indefinite = np.array([[1.0, 1.2], [1.2, 1.0]])
    repaired, provenance = repair_psd(indefinite)
    assert np.linalg.eigvalsh(repaired).min() >= -1e-9
    for key in ("method", "epsilon", "eigenvalues_before", "eigenvalues_after"):
        assert key in provenance
    assert provenance["method"] == "eigen_clip"


def test_repair_psd_method_none_records_no_after_spectrum() -> None:
    repaired, provenance = repair_psd(np.eye(2), method="none")
    assert provenance["method"] == "none"
    assert provenance["eigenvalues_after"] is None
    assert np.allclose(repaired, np.eye(2))


def test_never_silent_repair_is_rejected_without_provenance() -> None:
    """PFOL-01: a covariance that needed repair but lacks provenance fails closed."""
    from app.portfolio.optimizer import ensure_psd_provenance

    indefinite = np.array([[1.0, 1.2], [1.2, 1.0]])
    with pytest.raises(ValueError, match="PSD repair provenance missing"):
        ensure_psd_provenance(indefinite, {}, epsilon=1e-10)


# ---------------------------------------------------------------------------
# 11-06: covariance sha256 — deterministic identity + checksum-verified round-trip
# ---------------------------------------------------------------------------


def test_covariance_sha256_is_deterministic_and_discriminating() -> None:
    """PFOL-01: identical matrices hash to identical 64-hex digests; different
    matrices differ (canonical 8-decimal identity)."""
    from app.portfolio.risk import covariance_sha256

    cov = np.array([[0.04, 0.01], [0.01, 0.03]])
    first = covariance_sha256(cov)
    second = covariance_sha256(cov.copy())
    assert first == second
    assert len(first) == 64
    assert all(char in "0123456789abcdef" for char in first)
    # 8-decimal canonical: a 1e-9 perturbation is below the rounding resolution.
    assert covariance_sha256(cov + 1e-9) == first
    # A material difference changes the digest.
    assert covariance_sha256(cov + 0.01) != first


def test_covariance_sha256_digest_roundtrips_through_covariance_artifact(
    artifact_root,
) -> None:
    """PFOL-01/04: the repaired covariance's digest round-trips through the
    covariance.json artifact — write_bundle bytes hash to the same sha256, so
    Phase 12 can checksum-verify the artifact against risk_model_json."""
    from app.portfolio.artifacts import PortfolioArtifactService
    from app.portfolio.risk import covariance_sha256

    indefinite = np.array([[1.0, 1.2], [1.2, 1.0]])
    repaired, _ = repair_psd(indefinite)
    digest = covariance_sha256(repaired)

    service = PortfolioArtifactService(artifact_root)
    descriptors = service.write_bundle(
        run_id="a" * 32,
        weights={"A": 0.5, "B": 0.5},
        baseline_weights={"A": 0.5, "B": 0.5},
        covariance=repaired,
    )
    covariance_descriptor = next(d for d in descriptors if d.relative_path.endswith("covariance.json"))
    assert covariance_descriptor.checksum_sha256 == digest

    payload = service.read_artifact(
        covariance_descriptor.relative_path, checksum_sha256=digest
    )
    matrix = np.asarray(json.loads(payload.decode("utf-8")), dtype=float)
    assert covariance_sha256(matrix) == digest


# ---------------------------------------------------------------------------
# 12-02: RSK-02 new-model RED cases (semi / EWMA / Ledoit-Wolf) — green in 12-03
# ---------------------------------------------------------------------------


def test_semi_covariance_matches_manual_below_mean_reference(
    fixture_returns: np.ndarray,
) -> None:
    """RSK-02: semi_covariance equals the manual below-mean reference.

    Benchmark "mean" = row-wise mean (cross-sectional mean per observation);
    drops are the below-benchmark co-movements, normalized by the subset
    observation count (12-CONTEXT / 12-03 contract).
    """
    from app.portfolio.risk import semi_covariance

    cov = semi_covariance(fixture_returns, benchmark="mean")
    benchmark = fixture_returns.mean(axis=1, keepdims=True)
    drops = np.minimum(fixture_returns - benchmark, 0.0)
    expected = drops.T @ drops / drops.shape[0]
    assert np.allclose(cov, expected, rtol=1e-10)


def test_semi_covariance_zero_benchmark_uses_below_zero_subset(
    fixture_returns: np.ndarray,
) -> None:
    """RSK-02: benchmark="zero" restricts to below-zero co-movement."""
    from app.portfolio.risk import semi_covariance

    cov = semi_covariance(fixture_returns, benchmark="zero")
    drops = np.minimum(fixture_returns, 0.0)
    expected = drops.T @ drops / drops.shape[0]
    assert np.allclose(cov, expected, rtol=1e-10)


def test_ewma_covariance_lambda_one_recovers_sample_covariance(
    fixture_returns: np.ndarray,
) -> None:
    """RSK-02: EWMA lam=1.0 recovers the sample covariance on demeaned data."""
    from app.portfolio.risk import ewma_covariance

    demeaned = fixture_returns - fixture_returns.mean(axis=0)
    cov = ewma_covariance(demeaned, lam=1.0)
    expected = np.cov(demeaned, rowvar=False)
    assert np.allclose(cov, expected, rtol=1e-8)


def test_ewma_covariance_matches_hand_computed_recursion() -> None:
    """RSK-02: EWMA lam=0.94 matches a hand-computed 2-step recursion.

    Start Sigma_1 = outer(r_1, r_1); recurse Sigma_t = lam*Sigma_{t-1} +
    (1 - lam)*outer(r_t, r_t) (12-CONTEXT RiskMetrics formula).
    """
    from app.portfolio.risk import ewma_covariance

    returns = np.array([[0.010, 0.012], [0.011, 0.013]])
    cov = ewma_covariance(returns, lam=0.94)
    r0, r1 = returns[0], returns[1]
    expected = 0.94 * np.outer(r0, r0) + (1 - 0.94) * np.outer(r1, r1)
    assert np.allclose(cov, expected, rtol=1e-10)


def test_ledoit_wolf_covariance_returns_psd_with_shrinkage(
    fixture_returns: np.ndarray,
) -> None:
    """RSK-02: Ledoit-Wolf returns (PSD matrix, shrinkage/sklearn_version)."""
    from app.portfolio.risk import ledoit_wolf_covariance

    cov, meta = ledoit_wolf_covariance(fixture_returns)
    assert np.linalg.eigvalsh(cov).min() >= -1e-9
    assert np.allclose(cov, cov.T, rtol=1e-12)
    assert 0.0 < meta["shrinkage"] <= 1.0
    assert meta["sklearn_version"]


def test_make_risk_model_family_dispatches_all_four_models(
    fixture_returns: np.ndarray,
) -> None:
    """RSK-02: make_risk_model_family returns covariance + provenance for 4 models."""
    from app.portfolio.risk import make_risk_model_family

    for name in (
        "sample_covariance_v1",
        "semi_covariance_v1",
        "ewma_covariance_v1",
        "ledoit_wolf_v1",
    ):
        block = make_risk_model_family(fixture_returns, risk_model_name=name)
        assert "covariance" in block
        json_ = block["risk_model_json"]
        assert json_["risk_model"] == name
        assert json_["dropna"] is True
        assert json_["psd_repair"]["method"] in ("none", "eigen_clip")
        # 完整 PSD 溯源: epsilon + eigenvalues before/after 永不缺失 (never silent)。
        assert "epsilon" in json_["psd_repair"]
        assert "eigenvalues_before" in json_["psd_repair"]
        assert "eigenvalues_after" in json_["psd_repair"]
        assert len(json_["covariance_sha256"]) == 64
        # 模型参数: benchmark/lam/shrinkage 按模型记录。
        params = json_["model_params"]
        if name == "semi_covariance_v1":
            assert params["benchmark"] == "mean"
        elif name == "ewma_covariance_v1":
            assert params["lam"] == 0.94
        elif name == "ledoit_wolf_v1":
            assert 0.0 < params["shrinkage"] <= 1.0
            assert params["sklearn_version"]


def test_make_risk_model_family_rejects_unknown_name() -> None:
    """RSK-02: an unknown risk-model name raises ValueError."""
    from app.portfolio.risk import make_risk_model_family

    with pytest.raises(ValueError):
        make_risk_model_family(np.eye(2), risk_model_name="black_litterman_v1")


def test_risk_module_import_does_not_load_sklearn() -> None:
    """RSK-02: importing app.portfolio.risk must NOT load sklearn (lazy boundary)."""
    import subprocess
    import sys
    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[2]
    code = "import sys; import app.portfolio.risk; print('sklearn' in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(backend_root),
    )
    assert result.stdout.strip() == "False"
