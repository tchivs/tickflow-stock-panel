"""RED scaffold for portfolio/optimizer.py — min-vol QP + PSD gate.

Wave 0 (11-02) scaffold: contracts come from RESEARCH.md `## cvxpy QP
Formulation`; the module is created by 11-01, so this file is RED until then.
"""
from __future__ import annotations

import numpy as np
import pytest
from app.portfolio.optimizer import ensure_psd_provenance, solve_min_vol

FIXTURE_SYMBOLS = ("600000.SH", "600001.SH")


def test_min_vol_two_asset_matches_analytical() -> None:
    """PFOL-02: uncorrelated 2-asset min-vol matches the inverse-variance solution."""
    cov = np.diag([0.04, 0.09])  # sd1=0.2, sd2=0.3
    result = solve_min_vol(
        cov,
        list(FIXTURE_SYMBOLS),
        per_instrument_cap=1.0,
        min_cash=0.05,
        turnover_coef=0.0,
        w_prev=np.array([0.5, 0.5]),
    )
    weights = result["weights"]
    expected = np.array([0.04**-1, 0.09**-1])
    expected = expected / expected.sum() * (1 - 0.05)
    assert np.allclose([weights[s] for s in FIXTURE_SYMBOLS], expected, atol=1e-4)


def test_cap_and_min_cash_are_active_constraints() -> None:
    """PFOL-03: no weight exceeds the cap and cash floor is respected."""
    cov = np.array([[0.04, 0.01], [0.01, 0.03]])
    result = solve_min_vol(
        cov,
        list(FIXTURE_SYMBOLS),
        per_instrument_cap=0.60,
        min_cash=0.05,
        turnover_coef=0.0,
        w_prev=np.array([0.5, 0.5]),
    )
    weights = np.array([result["weights"][s] for s in FIXTURE_SYMBOLS])
    assert weights.max() <= 0.60 + 1e-8
    assert weights.min() >= -1e-8
    assert 1 - weights.sum() >= 0.05 - 1e-8
    assert weights.sum() <= 1 + 1e-8


def test_turnover_penalty_shifts_toward_w_prev() -> None:
    cov = np.diag([0.04, 0.09])
    w_prev = np.array([0.9, 0.1])
    no_turnover = solve_min_vol(
        cov, list(FIXTURE_SYMBOLS), per_instrument_cap=1.0, min_cash=0.0,
        turnover_coef=0.0, w_prev=w_prev,
    )["weights"]
    with_turnover = solve_min_vol(
        cov, list(FIXTURE_SYMBOLS), per_instrument_cap=1.0, min_cash=0.0,
        turnover_coef=0.5, w_prev=w_prev,
    )["weights"]
    no_t = np.array([no_turnover[s] for s in FIXTURE_SYMBOLS])
    with_t = np.array([with_turnover[s] for s in FIXTURE_SYMBOLS])
    assert np.linalg.norm(with_t - w_prev) < np.linalg.norm(no_t - w_prev)


def test_non_psd_covariance_without_provenance_fails_closed() -> None:
    """PFOL-03: a non-PSD covariance without provenance is rejected, never silent."""
    indefinite = np.array([[1.0, 1.2], [1.2, 1.0]])
    with pytest.raises(ValueError, match="PSD repair provenance missing"):
        ensure_psd_provenance(indefinite, {}, epsilon=1e-10)


def test_deterministic_solves() -> None:
    cov = np.array([[0.04, 0.01], [0.01, 0.03]])
    kwargs = dict(
        cov=cov, symbols=list(FIXTURE_SYMBOLS), per_instrument_cap=0.60,
        min_cash=0.05, turnover_coef=0.0, w_prev=np.array([0.5, 0.5]),
    )
    first = solve_min_vol(**kwargs)
    second = solve_min_vol(**kwargs)
    assert first["weights"] == second["weights"]
    assert first["options"] == second["options"]


def test_non_optimal_status_recorded_as_is() -> None:
    """PFOL-04: a non-optimal solve status is carried verbatim, never promoted.

    cap 0.30 x 2 assets < 0.95 budget -> infeasible under the budget equality;
    the dict records the real solver status, not a fabricated 'optimal'.
    """
    cov = np.diag([0.04, 0.09])
    result = solve_min_vol(
        cov, list(FIXTURE_SYMBOLS), per_instrument_cap=0.30,
        min_cash=0.05, turnover_coef=0.0, w_prev=np.array([0.5, 0.5]),
    )
    assert result["status"] == "infeasible"
    assert result["weights"] == {}
    assert result["options"]["solver"] == "CLARABEL"
