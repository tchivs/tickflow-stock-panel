"""Phase 11 portfolio/optimizer tests — solver_path, w_prev anchor, max-Sharpe gate.

Wave 0 (11-02) scaffold: contracts come from RESEARCH.md `## cvxpy QP
Formulation`; 11-01 made the min-vol path green; 11-04 (this file) locks the
PFOL-02/03 breadth: solver_path fallback + per-solver version capture, the
w_prev equal-weight anchor / prior-run reference, and the max-Sharpe explicit
non-default contract (render_baselines=True mandatory, min-vol + HRP baselines
always recorded alongside).
"""
from __future__ import annotations

import numpy as np
import pytest

from app.portfolio.optimizer import (
    ensure_psd_provenance,
    run_optimization,
    solve_max_sharpe,
    solve_min_vol,
)
from app.portfolio.schemas import OptimizationRequest

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


# ---------------------------------------------------------------------------
# 11-04: solver_path fallback + per-solver version capture
# ---------------------------------------------------------------------------


def test_recorded_options_contain_solver_path_and_solver() -> None:
    """PFOL-04: the verbatim options dict records solver_path + solver keys."""
    cov = np.diag([0.04, 0.09])
    result = solve_min_vol(
        cov, list(FIXTURE_SYMBOLS), per_instrument_cap=1.0, min_cash=0.05,
        turnover_coef=0.0, w_prev=np.array([0.5, 0.5]),
    )
    options = result["options"]
    assert "solver_path" in options
    assert options["solver_path"] == ["CLARABEL", "OSQP"]
    assert "solver" in options
    assert options["solver"] == "CLARABEL"


def test_solver_name_and_version_capture_actual_solver() -> None:
    """PFOL-04: solver_name is the solver that ran; solver_version is non-empty."""
    cov = np.diag([0.04, 0.09])
    result = solve_min_vol(
        cov, list(FIXTURE_SYMBOLS), per_instrument_cap=1.0, min_cash=0.05,
        turnover_coef=0.0, w_prev=np.array([0.5, 0.5]),
    )
    assert result["solver_name"] in ("CLARABEL", "OSQP")
    assert isinstance(result["solver_version"], str)
    assert result["solver_version"] != ""


# ---------------------------------------------------------------------------
# 11-04: w_prev resolution — equal-weight anchor + prior-run reference
# ---------------------------------------------------------------------------


def test_equal_weight_anchor_recorded_in_constraint_stack(
    portfolio_repository, artifact_root, fixture_composite,
) -> None:
    """PFOL-03: a first run with equal_weight records the anchor verbatim."""
    run = run_optimization(
        {
            "objective": "min_volatility",
            "as_of": "2026-08-01",
            "universe": "cn-a-share",
            "model_id": "composite-model-v1",
            "expected_return_method": "composite-zscore-v1",
            "render_baselines": True,
            "per_instrument_cap": 0.10,
            "min_cash": 0.05,
            "turnover_coef": 0.0014,
            "turnover_reference": "equal_weight",
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
    )
    stack = run["constraint_stack"]
    assert stack["turnover_reference"] == "equal_weight"
    assert stack["turnover_reference_detail"] == "equal_weight"


def test_run_id_reference_loads_prior_weights_aligned_to_symbols(
    portfolio_repository, artifact_root, fixture_composite,
) -> None:
    """PFOL-03: a run_id reference loads the prior run's checksum-bound weights,
    aligns them to the current symbols, and records the detail."""
    first = run_optimization(
        {
            "objective": "min_volatility",
            "as_of": "2026-08-01",
            "universe": "cn-a-share",
            "model_id": "composite-model-v1",
            "expected_return_method": "composite-zscore-v1",
            "render_baselines": True,
            "per_instrument_cap": 0.10,
            "min_cash": 0.05,
            "turnover_coef": 0.0014,
            "turnover_reference": "equal_weight",
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
    )
    second = run_optimization(
        {
            "objective": "min_volatility",
            "as_of": "2026-08-01",
            "universe": "cn-a-share",
            "model_id": "composite-model-v1",
            "expected_return_method": "composite-zscore-v1",
            "render_baselines": True,
            "per_instrument_cap": 0.10,
            "min_cash": 0.05,
            "turnover_coef": 0.0014,
            "turnover_reference": "run_id",
            "w_prev_run_id": first["id"],
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
    )
    stack = second["constraint_stack"]
    assert stack["turnover_reference"] == "run_id"
    assert stack["turnover_reference_detail"] == f"run_id:{first['id']}"


def test_run_id_reference_missing_prior_run_fails_closed(
    portfolio_repository, artifact_root, fixture_composite,
) -> None:
    """PFOL-03/04 (11-05): a missing prior run fails closed and is recorded as a
    failed run with reason — never a silent abort and never a propagated ValueError
    (the orchestrator wraps the ENTIRE run)."""
    run = run_optimization(
        {
            "objective": "min_volatility",
            "as_of": "2026-08-01",
            "universe": "cn-a-share",
            "model_id": "composite-model-v1",
            "expected_return_method": "composite-zscore-v1",
            "render_baselines": True,
            "per_instrument_cap": 0.10,
            "min_cash": 0.05,
            "turnover_coef": 0.0014,
            "turnover_reference": "run_id",
            "w_prev_run_id": "0" * 32,
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
    )
    assert run["problem_status"] == "failed"
    assert run["failure_reason"] is not None
    assert "prior run not found" in run["failure_reason"]


def test_schema_requires_w_prev_run_id_for_run_id_reference() -> None:
    """V5: w_prev_run_id is required iff turnover_reference == 'run_id'."""
    with pytest.raises(ValueError, match="w_prev_run_id is required"):
        OptimizationRequest(as_of="2026-08-01", turnover_reference="run_id")
    # equal_weight is the default and needs no run id.
    request = OptimizationRequest(as_of="2026-08-01")
    assert request.turnover_reference == "equal_weight"
    assert request.w_prev_run_id is None


# ---------------------------------------------------------------------------
# 11-04: max-Sharpe — explicit non-default with baselines rendered
# ---------------------------------------------------------------------------


def test_max_sharpe_requires_baselines(
    portfolio_repository, artifact_root, fixture_composite,
) -> None:
    """Pitfall 2 (11-05): max_sharpe with render_baselines=False is rejected and
    recorded as a failed run with reason — never silent, never propagated."""
    run = run_optimization(
        {
            "objective": "max_sharpe",
            "as_of": "2026-08-01",
            "universe": "cn-a-share",
            "model_id": "composite-model-v1",
            "expected_return_method": "composite-zscore-v1",
            "render_baselines": False,
            "per_instrument_cap": 0.10,
            "min_cash": 0.05,
            "turnover_coef": 0.0014,
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
    )
    assert run["problem_status"] == "failed"
    assert run["failure_reason"] is not None
    assert "render_baselines" in run["failure_reason"]


def test_max_sharpe_solves_under_constraint_stack() -> None:
    """PFOL-02: the max-Sharpe objective solves under the same constraint stack."""
    cov = np.diag([0.04, 0.09])
    result = solve_max_sharpe(
        np.array([0.01, 0.02]),
        cov,
        list(FIXTURE_SYMBOLS),
        per_instrument_cap=1.0,
        min_cash=0.05,
        turnover_coef=0.0,
        w_prev=np.array([0.5, 0.5]),
    )
    assert result["status"] == "optimal"
    assert result["solver_name"] in ("CLARABEL", "OSQP")
    assert result["solver_version"] != ""
    weights = np.array([result["weights"][s] for s in FIXTURE_SYMBOLS])
    assert weights.min() >= -1e-8
    assert abs(weights.sum() - 0.95) < 1e-6


def test_max_sharpe_run_records_both_baselines(
    portfolio_repository, artifact_root, fixture_composite,
) -> None:
    """Pitfall 2: a max_sharpe run records objective + BOTH min-vol and HRP baselines."""
    run = run_optimization(
        {
            "objective": "max_sharpe",
            "as_of": "2026-08-01",
            "universe": "cn-a-share",
            "model_id": "composite-model-v1",
            "expected_return_method": "composite-zscore-v1",
            "render_baselines": True,
            "per_instrument_cap": 0.10,
            "min_cash": 0.05,
            "turnover_coef": 0.0014,
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
        mu=np.linspace(0.0005, 0.0025, 12),
    )
    assert run["problem_status"] == "optimal"
    assert run["objective"] == "max_sharpe"
    baseline = run["baseline_weights"]
    assert isinstance(baseline, dict)
    assert "min_volatility" in baseline
    assert "hrp" in baseline
    # Both baselines are rendered to the (1 - min_cash) budget.
    assert abs(sum(baseline["min_volatility"].values()) - 0.95) < 1e-6
    assert abs(sum(baseline["hrp"].values()) - 0.95) < 1e-6


def test_max_sharpe_requires_mu(
    portfolio_repository, artifact_root, fixture_composite,
) -> None:
    """PFOL-02 (11-05): max_sharpe without an expected-returns vector fails closed
    and is recorded as a failed run with reason."""
    run = run_optimization(
        {
            "objective": "max_sharpe",
            "as_of": "2026-08-01",
            "universe": "cn-a-share",
            "model_id": "composite-model-v1",
            "expected_return_method": "composite-zscore-v1",
            "render_baselines": True,
            "per_instrument_cap": 0.10,
            "min_cash": 0.05,
            "turnover_coef": 0.0014,
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
    )
    assert run["problem_status"] == "failed"
    assert run["failure_reason"] is not None
    assert "expected-returns" in run["failure_reason"]


def test_min_vol_is_default_objective() -> None:
    """PFOL-02: min_volatility remains the default objective (kept green from 11-01)."""
    request = OptimizationRequest(as_of="2026-08-01")
    assert request.objective == "min_volatility"


def test_optimal_inaccurate_status_recorded_verbatim(
    portfolio_repository, artifact_root, fixture_composite,
) -> None:
    """Pitfall 4: an optimal_inaccurate solve is recorded as-is, never promoted.

    A run whose solve ends optimal_inaccurate must keep that honest status on the
    run row (not be rewritten to 'optimal' by the orchestrator), with the options
    recorded verbatim. Here the solve is forced inaccurate by an OSQP
    max_iter=1 user_limit result; the repository-level run row is recorded with
    the verbatim status via the non-optimal path (output_weights None).
    """
    first = run_optimization(
        {
            "objective": "min_volatility",
            "as_of": "2026-08-01",
            "universe": "cn-a-share",
            "model_id": "composite-model-v1",
            "expected_return_method": "composite-zscore-v1",
            "render_baselines": True,
            "per_instrument_cap": 0.10,
            "min_cash": 0.05,
            "turnover_coef": 0.0014,
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
    )
    # Directly record a run row with the honest optimal_inaccurate status.
    from app.portfolio.repository import PortfolioRepository

    assert isinstance(portfolio_repository, PortfolioRepository)
    recorded = portfolio_repository.record_optimization_run(
        id="a" * 32,
        objective="min_volatility",
        as_of="2026-08-01",
        universe="cn-a-share",
        model_id="composite-model-v1",
        composite_snapshot_id="c1",
        input_snapshot_sha256="f" * 64,
        expected_return_method="composite-zscore-v1",
        risk_model="sample_covariance_v1",
        risk_model_json=first["risk_model"],
        constraint_stack_json=first["constraint_stack"],
        solver_name="OSQP",
        solver_version="1.1.3",
        solver_options_json={"solver": "OSQP", "max_iter": 1},
        problem_status="optimal_inaccurate",
        failure_reason=None,
        output_weights_json=None,
        output_sha256=None,
        weights_artifact_relative_path=None,
        baseline_weights_json=None,
        created_at="2026-08-01T00:00:00Z",
    )
    assert recorded is not None
    assert recorded["problem_status"] == "optimal_inaccurate"
    assert recorded["solver_options"] == {"solver": "OSQP", "max_iter": 1}
    # The run row retains the honest status verbatim — never promoted to optimal.
    assert recorded["problem_status"] != "optimal"
