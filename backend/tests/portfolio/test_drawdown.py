"""Drawdown attribution breadth — per-instrument x per-segment decomposition (RSK-03).

12-06 turns the 12-02 RED scaffold green and adds the RSK-03 breadth:
  (1) the underwater curve matches the cumprod reference;
  (2) drawdown_periods finds exactly the CONSTRUCTED segment in
      fixture_returns_long with the expected {start_idx, end_idx, depth};
  (3) the segment identity — per-instrument contributions sum to the segment
      return to rtol 1e-10 (HARD, symmetric with RSK-01's variance
      reconciliation; never approximate);
  (4) thresholds — a sub-threshold dip is NOT flagged; a flat series → no periods;
  (5) end-to-end run_drawdown on a fixture run writes the drawdown.json artifact
      (checksum-verified read-back) + the evidence row with
      attribution_type="drawdown" and the reconciliation payload
      (period_count / max_depth / longest_period / segment_max_abs_error /
      depth_threshold / min_obs — module constants, not magic literals);
  (6) a second run_drawdown appends a SECOND evidence row (append-only);
  (7) non-finite returns fail closed with ValueError and write NO evidence row.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from app.portfolio.analyzer import run_drawdown
from app.portfolio.artifacts import PortfolioArtifactService
from app.portfolio.drawdown import (
    DRAWDOWN_DEPTH_THRESHOLD,
    DRAWDOWN_MIN_OBS,
    drawdown_attribution,
    drawdown_periods,
    underwater_curve,
)
from app.portfolio.repository import PortfolioRepository


def _tiled_long_returns() -> np.ndarray:
    """fixture_returns_long tiled to 12 columns, aligned to the fixture run.

    The fixture run (fixture_mode) optimizes 12 SYM symbols; fixture_returns_long
    is a 24-obs x 4-symbol panel. Tiling each column 3x preserves the constructed
    obs 8-11 drawdown segment for every symbol while aligning the panel's columns
    to the run's output_weights.
    """
    from tests.portfolio.conftest import FIXTURE_SYMBOLS

    assert len(FIXTURE_SYMBOLS) == 4
    rng = np.random.default_rng(20260802)
    rows = rng.normal(0.0005, 0.001, size=(24, 4))
    rows[8] = [-0.050, -0.049, -0.051, -0.050]
    rows[9] = [-0.040, -0.039, -0.041, -0.040]
    rows[10] = [0.005, 0.006, 0.004, 0.005]
    rows[11] = [-0.010, -0.009, -0.011, -0.010]
    rows[12] = [0.090, 0.091, 0.089, 0.090]
    rows[13] = [0.040, 0.041, 0.039, 0.040]
    return np.repeat(rows, 3, axis=1)


# ---------------------------------------------------------------------------
# 12-02 scaffold — underwater curve + period detection
# ---------------------------------------------------------------------------


def test_underwater_curve_matches_cumprod_reference() -> None:
    """RSK-03: underwater = equity / running_max(equity) - 1."""
    returns = np.array([0.01, -0.02, 0.005, -0.03, 0.02, 0.001])
    equity = np.cumprod(1.0 + returns)
    expected = equity / np.maximum.accumulate(equity) - 1.0
    curve = underwater_curve(returns)
    assert np.allclose(curve, expected, rtol=1e-12)


def test_flat_series_has_no_drawdown_periods() -> None:
    """RSK-03: a flat (or always-positive) series produces []"""
    flat = np.zeros(8)
    curve = underwater_curve(flat)
    assert np.allclose(curve, 0.0, atol=1e-15)
    assert drawdown_periods(curve) == []


def test_underwater_curve_rejects_returns_at_or_below_minus_one() -> None:
    """WR-02: a return of -1.0 (or lower) drives equity to zero/negative — the
    resulting NaN/infinite underwater curve is rejected with ValueError instead
    of being silently skipped by drawdown_periods."""
    with pytest.raises(ValueError, match=r"greater than -1\.0"):
        underwater_curve(np.array([0.0, -1.0]))
    with pytest.raises(ValueError, match=r"greater than -1\.0"):
        underwater_curve(np.array([0.5, -1.5]))
    # The boundary: a -0.999... return stays finite and is accepted.
    curve = underwater_curve(np.array([0.0, -0.9999, 0.5]))
    assert np.all(np.isfinite(curve))


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


def test_drawdown_periods_honor_depth_threshold() -> None:
    """RSK-03: a shallow dip below the 2% depth threshold is NOT flagged."""
    # -1% then -0.5% cumulates to ~ -1.5% underwater — above the 2% threshold
    # even across two observations, so drawdown_periods returns [].
    returns = np.array([0.0, -0.01, -0.005, 0.0, 0.0])
    curve = underwater_curve(returns)
    assert curve.min() > -DRAWDOWN_DEPTH_THRESHOLD
    assert drawdown_periods(curve, depth_threshold=0.02, min_obs=2) == []


# ---------------------------------------------------------------------------
# 12-06 breadth — per-instrument x per-segment decomposition
# ---------------------------------------------------------------------------


def test_drawdown_attribution_segment_identity_holds_exactly(
    fixture_returns_long: np.ndarray,
) -> None:
    """RSK-03: per-instrument contributions sum EXACTLY to the segment return.

    The hard assertion is rtol 1e-10 (linear decomposition, exact in arithmetic)
    — never approximate, symmetric with RSK-01's variance reconciliation.
    """
    weights = np.full(4, 0.25)
    symbols = ["600000.SH", "600001.SH", "600002.SH", "600003.SH"]
    portfolio_returns = fixture_returns_long.mean(axis=1)
    periods = drawdown_periods(underwater_curve(portfolio_returns))
    result = drawdown_attribution(weights, fixture_returns_long, periods, symbols=symbols)

    assert result["periods"], "the constructed segment must be attributed"
    for period in result["periods"]:
        assert period["start_idx"] == 8
        assert period["end_idx"] == 11
        # The identity: sum(c_i) == segment_return, asserted hard inside the
        # function; re-assert here at rtol 1e-10 to lock the contract.
        assert np.isclose(
            sum(period["contributions"].values()),
            period["segment_return"],
            rtol=1e-10,
            atol=1e-15,
        )
        assert period["segment_return"] < 0
    # Summary block: max depth from the segment, longest period in observations.
    assert result["max_depth"] >= DRAWDOWN_DEPTH_THRESHOLD
    assert result["longest_period"] == 4
    assert result["segment_reconciliation_max_abs_error"] == pytest.approx(0.0, abs=1e-15)


def test_drawdown_attribution_empty_periods_is_vacuous() -> None:
    """RSK-03: empty periods produce a zero summary (the identity is vacuous)."""
    weights = np.full(4, 0.25)
    returns = np.zeros((10, 4))
    result = drawdown_attribution(weights, returns, [], symbols=["a", "b", "c", "d"])
    assert result == {
        "periods": [],
        "max_depth": 0.0,
        "longest_period": 0,
        "segment_reconciliation_max_abs_error": 0.0,
    }


def test_drawdown_attribution_rejects_misaligned_inputs() -> None:
    """RSK-03: misaligned panels / symbols fail closed with ValueError."""
    weights = np.full(4, 0.25)
    returns = np.zeros((10, 3))
    with pytest.raises(ValueError):
        drawdown_attribution(weights, returns, [], symbols=["a", "b", "c"])
    with pytest.raises(ValueError):
        drawdown_attribution(np.full(4, 0.25), np.zeros((10, 4)), [], symbols=["a", "b"])


# ---------------------------------------------------------------------------
# 12-06 breadth — end-to-end run_drawdown on a fixture run
# ---------------------------------------------------------------------------


def test_run_drawdown_full_report_and_evidence_on_fixture_run(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
    fixture_attribution_run: dict[str, object],
) -> None:
    """RSK-03: run_drawdown writes the full per-segment report artifact +
    append-only evidence row; the segment identity is asserted before any write."""
    run = fixture_attribution_run
    run_id = str(run["id"])
    service = PortfolioArtifactService(artifact_root)
    returns = _tiled_long_returns()

    dd = run_drawdown(
        run_id,
        returns=returns,
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
    )
    assert dd["attribution_type"] == "drawdown"
    assert dd["risk_model"] == run["risk_model"]
    # Reconciliation payload: period_count / max_depth / longest_period /
    # segment_max_abs_error / module threshold constants.
    assert dd["reconciliation"]["period_count"] == 1
    assert dd["reconciliation"]["max_depth"] >= DRAWDOWN_DEPTH_THRESHOLD
    assert dd["reconciliation"]["longest_period"] == 4
    assert dd["reconciliation"]["segment_max_abs_error"] == pytest.approx(0.0, abs=1e-15)
    assert dd["reconciliation"]["depth_threshold"] == DRAWDOWN_DEPTH_THRESHOLD
    assert dd["reconciliation"]["min_obs"] == DRAWDOWN_MIN_OBS

    # Artifact read-back checksum-verifies and carries the full report.
    payload = json.loads(
        service.read_artifact(
            dd["artifact_relative_path"], checksum_sha256=dd["output_sha256"]
        ).decode("utf-8")
    )
    assert payload["run_id"] == run_id
    assert payload["symbols"] == list(run["output_weights"].keys())
    assert len(payload["underwater"]) == returns.shape[0]
    assert len(payload["periods"]) == 1
    period = payload["periods"][0]
    assert period["start_idx"] == 8
    assert period["end_idx"] == 11
    assert period["depth"] >= DRAWDOWN_DEPTH_THRESHOLD
    # The per-segment identity survives the artifact round-trip.
    assert np.isclose(
        sum(period["contributions"].values()),
        period["segment_return"],
        rtol=1e-10,
        atol=1e-15,
    )
    assert payload["max_depth"] == pytest.approx(dd["reconciliation"]["max_depth"], rel=1e-12)
    assert payload["longest_period"] == 4
    assert payload["depth_threshold"] == DRAWDOWN_DEPTH_THRESHOLD
    assert payload["min_obs"] == DRAWDOWN_MIN_OBS


def test_run_drawdown_appends_second_evidence_row(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
    fixture_attribution_run: dict[str, object],
) -> None:
    """RSK-03: a second run_drawdown appends a SECOND evidence row (append-only)."""
    run = fixture_attribution_run
    run_id = str(run["id"])
    returns = _tiled_long_returns()

    first = run_drawdown(
        run_id,
        returns=returns,
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
    )
    second = run_drawdown(
        run_id,
        returns=returns,
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
    )
    assert second["id"] != first["id"]
    rows = portfolio_repository.list_attribution_evidence(run_id=run_id)
    drawdown_rows = [row for row in rows if row["attribution_type"] == "drawdown"]
    assert {row["id"] for row in drawdown_rows} == {first["id"], second["id"]}


def test_run_drawdown_non_finite_returns_fail_closed(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
    fixture_attribution_run: dict[str, object],
) -> None:
    """RSK-03: non-finite returns raise ValueError and write NO evidence row."""
    run = fixture_attribution_run
    run_id = str(run["id"])
    returns = _tiled_long_returns()
    returns[0, 0] = np.nan

    count_before = len(portfolio_repository.list_attribution_evidence(run_id=run_id))
    with pytest.raises(ValueError):
        run_drawdown(
            run_id,
            returns=returns,
            repository=portfolio_repository,
            artifact_service_root=artifact_root,
        )
    assert len(portfolio_repository.list_attribution_evidence(run_id=run_id)) == count_before
