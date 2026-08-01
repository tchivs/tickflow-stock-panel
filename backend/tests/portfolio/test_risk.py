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
