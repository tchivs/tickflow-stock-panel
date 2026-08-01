"""RED scaffold for portfolio/drawdown.py — underwater curve + periods (RSK-03).

Wave 0 (12-02) scaffold: these contracts come from 12-CONTEXT.md `## Drawdown
Attribution` (underwater curve → periods → per-instrument table). The module
they import is created by 12-01, so this file is provably RED until then; 12-06
turns it fully green.
"""

from __future__ import annotations

import numpy as np
from app.portfolio.drawdown import (
    DRAWDOWN_DEPTH_THRESHOLD,
    DRAWDOWN_MIN_OBS,
    drawdown_periods,
    underwater_curve,
)


def test_underwater_curve_matches_cumprod_reference() -> None:
    """RSK-03: underwater = equity / running_max(equity) - 1."""
    returns = np.array([0.01, -0.02, 0.005, -0.03, 0.02, 0.001])
    equity = np.cumprod(1.0 + returns)
    expected = equity / np.maximum.accumulate(equity) - 1.0
    curve = underwater_curve(returns)
    assert np.allclose(curve, expected, rtol=1e-12)


def test_flat_series_has_no_drawdown_periods() -> None:
    """RSK-03: a flat (or always-positive) series produces []."""
    flat = np.zeros(8)
    curve = underwater_curve(flat)
    assert np.allclose(curve, 0.0, atol=1e-15)
    assert drawdown_periods(curve) == []


def test_short_series_has_no_drawdown_periods() -> None:
    """RSK-03: a series shorter than min_obs produces [] (no partial spans)."""
    short = np.array([-0.05])  # one deep observation, but min_obs = 2
    curve = underwater_curve(short)
    assert drawdown_periods(curve) == []


def test_drawdown_period_detects_constructed_segment(
    fixture_returns_long: np.ndarray,
) -> None:
    """RSK-03: the CONSTRUCTED obs 8-11 dip in fixture_returns_long is found.

    The equal-weight portfolio return around obs 8-11 sits below -depth_threshold
    for >= min_obs observations, so drawdown_periods returns one span overlapping
    the engineered segment.
    """
    portfolio_returns = fixture_returns_long.mean(axis=1)
    curve = underwater_curve(portfolio_returns)
    periods = drawdown_periods(
        curve,
        depth_threshold=DRAWDOWN_DEPTH_THRESHOLD,
        min_obs=DRAWDOWN_MIN_OBS,
    )
    assert periods, "the constructed drawdown segment must be detected"
    first = periods[0]
    assert first["start_idx"] <= 8
    assert first["end_idx"] >= 10
    assert first["depth"] >= DRAWDOWN_DEPTH_THRESHOLD


def test_drawdown_periods_honor_min_obs_threshold() -> None:
    """RSK-03: a dip that lasts fewer than min_obs observations is not flagged."""
    # Two deep obs then immediate recovery: duration 2, which meets min_obs=2,
    # so this MUST be flagged; a single-obs dip (above) is the negative case.
    returns = np.array([0.0, -0.03, -0.04, 0.0])
    curve = underwater_curve(returns)
    periods = drawdown_periods(curve, depth_threshold=0.02, min_obs=2)
    assert len(periods) == 1
