"""RED scaffold for portfolio/risk.py — sample covariance + PSD check/repair.

Wave 0 (11-02) scaffold: these contracts come from RESEARCH.md `## PSD
Check/Repair`; the module they import is created by 11-01, so this file is
provably RED until then.
"""
from __future__ import annotations

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
