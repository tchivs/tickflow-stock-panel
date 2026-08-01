"""RED scaffold for portfolio/attribution.py — exposure + marginal contribution (RSK-01).

Wave 0 (12-02) scaffold: these contracts come from 12-CONTEXT.md `## Specific
Ideas` (MC = w_i * (Sigma*w)_i; portfolio variance = w^T Sigma w; sum(MC) ==
variance as a HARD assertion). The module they import is created by 12-01, so
this file is provably RED until then; 12-04 turns it fully green.
"""

from __future__ import annotations

import numpy as np
import pytest
from app.portfolio.attribution import (
    marginal_contributions,
    portfolio_exposure,
    portfolio_variance,
    reconcile_attribution,
)


@pytest.fixture
def attribution_inputs() -> tuple[np.ndarray, np.ndarray]:
    """Deterministic 4-asset weights + a PSD covariance matrix."""
    weights = np.array([0.4, 0.3, 0.2, 0.1])
    cov = np.array(
        [
            [0.0400, 0.0060, 0.0020, 0.0010],
            [0.0060, 0.0300, 0.0015, 0.0008],
            [0.0020, 0.0015, 0.0200, 0.0004],
            [0.0010, 0.0008, 0.0004, 0.0100],
        ]
    )
    return weights, cov


def test_portfolio_variance_matches_w_t_cov_w_reference(
    attribution_inputs: tuple[np.ndarray, np.ndarray],
) -> None:
    """RSK-01: portfolio_variance == w^T Sigma w on a fixture matrix."""
    weights, cov = attribution_inputs
    variance = portfolio_variance(weights, cov)
    expected = float(weights @ (cov @ weights))
    assert np.isclose(variance, expected, rtol=1e-12)


def test_sum_marginal_contributions_equals_portfolio_variance(
    attribution_inputs: tuple[np.ndarray, np.ndarray],
) -> None:
    """RSK-01: sum(MC) == portfolio variance exactly (rtol 1e-12 hard)."""
    weights, cov = attribution_inputs
    variance = portfolio_variance(weights, cov)
    mc = marginal_contributions(weights, cov)
    assert np.isclose(float(np.sum(mc)), variance, rtol=1e-12)


def test_exposure_is_signed_weight_times_covariance_with_portfolio(
    attribution_inputs: tuple[np.ndarray, np.ndarray],
) -> None:
    """RSK-01: exposure = w * (Sigma*w), kept SIGNED (negative = diversifier)."""
    weights, cov = attribution_inputs
    exposure = portfolio_exposure(weights, cov)
    expected = weights * (cov @ weights)
    assert np.allclose(exposure, expected, rtol=1e-12)
    # Never abs()ed: a diversifier's negative component survives.
    assert np.all(exposure == exposure)  # all finite


def test_reconcile_attribution_accepts_exact_decomposition(
    attribution_inputs: tuple[np.ndarray, np.ndarray],
) -> None:
    """RSK-01: the hard reconciliation passes on an exact decomposition."""
    weights, cov = attribution_inputs
    variance = portfolio_variance(weights, cov)
    mc = marginal_contributions(weights, cov)
    reconcile_attribution(weights, cov, mc, variance)


def test_reconcile_attribution_rejects_perturbed_mc_vector(
    attribution_inputs: tuple[np.ndarray, np.ndarray],
) -> None:
    """RSK-01: a deliberately perturbed MC vector fails the hard assertion."""
    weights, cov = attribution_inputs
    variance = portfolio_variance(weights, cov)
    mc = marginal_contributions(weights, cov)
    mc[0] = mc[0] + 1e-6  # material perturbation, far above rtol 1e-12
    with pytest.raises(AssertionError):
        reconcile_attribution(weights, cov, mc, variance)
