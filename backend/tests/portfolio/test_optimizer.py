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
        fixture_mode=True,
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
        fixture_mode=True,
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
        fixture_mode=True,
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
        fixture_mode=True,
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
        fixture_mode=True,
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
        fixture_mode=True,
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
        fixture_mode=True,
    )
    assert run["problem_status"] == "failed"
    assert run["failure_reason"] is not None
    assert "expected-returns" in run["failure_reason"]


def test_indefinite_covariance_records_failed_run_in_orchestrator(
    portfolio_repository, artifact_root, fixture_composite, monkeypatch,
) -> None:
    """CR-02: a deliberately indefinite covariance (bypassing the repair gate)
    must be recorded as a failed run with the DCPError message — never propagated
    out of run_optimization as an unrecorded abort.
    """
    import app.portfolio.optimizer as optimizer_module

    indefinite = np.array([[1.0, 1.2], [1.2, 1.0]])  # min eig < 0, non-PSD

    def _bypass_repair(returns, *, window, epsilon=1e-10, risk_model_name="sample_covariance_v1"):
        # Bypass the PSD gate: hand the indefinite covariance straight to the solver.
        return {"covariance": indefinite, "risk_model_json": {"risk_model": "sample_covariance_v1", "psd_repair": None}}

    monkeypatch.setattr(optimizer_module, "_build_risk_model", _bypass_repair)

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
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
        fixture_mode=True,
    )
    assert run["problem_status"] == "failed"
    assert run["failure_reason"] is not None
    assert "DCP" in run["failure_reason"] or "not PSD" in run["failure_reason"] \
        or "PSD" in run["failure_reason"]
    # No weights persisted for the failed run.
    assert run.get("output_weights") is None
    assert run.get("output_sha256") is None
    # Recorded, not raised.
    fetched = portfolio_repository.get_optimization_run(run["id"])
    assert fetched is not None
    assert fetched["problem_status"] == "failed"


def test_composite_without_real_seam_records_failed_run_no_phantom_row(
    portfolio_repository, artifact_root, monkeypatch,
) -> None:
    """CR-01: composite-zscore-v1 without any checksum-verified snapshot seam must
    record a failed run and MUST NOT write a phantom factor_model_composites row
    with a fabricated output_sha256 pointing at a never-created artifact.
    """
    from app.research.repository import ResearchRepository

    research = ResearchRepository(portfolio_repository.database_path)
    # No model definition and no composite registered — no real seam.
    run = run_optimization(
        {
            "objective": "min_volatility",
            "as_of": "2026-08-01",
            "universe": "cn-a-share",
            "model_id": "ghost-model",
            "expected_return_method": "composite-zscore-v1",
            "render_baselines": True,
            "per_instrument_cap": 0.10,
            "min_cash": 0.05,
            "turnover_coef": 0.0014,
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        fixture_mode=True,
    )
    assert run["problem_status"] == "failed"
    assert run["failure_reason"] is not None
    assert "composite" in run["failure_reason"].lower()
    # No phantom composite row may exist for the ghost model.
    assert research.list_model_composites("ghost-model") == []
    assert research.get_model_definition("ghost-model") is None
    # The failed run's input_snapshot_sha256 is the documented unknown sentinel,
    # never a fabricated valid-looking digest equal to the fixture identity.
    assert run["input_snapshot_sha256"] == "0" * 64


def test_solver_options_unknown_key_rejected() -> None:
    """WR-01: a non-whitelisted solver_options key is rejected by the solver."""
    cov = np.diag([0.04, 0.09])
    with pytest.raises(ValueError, match="not allowed"):
        solve_min_vol(
            cov,
            list(FIXTURE_SYMBOLS),
            per_instrument_cap=1.0,
            min_cash=0.05,
            turnover_coef=0.0,
            w_prev=np.array([0.5, 0.5]),
            solver_options={"not_a_real_option": 1},
        )


def test_solver_options_whitelisted_key_accepted() -> None:
    """WR-01: whitelisted keys pass through the allowlist validation."""
    cov = np.diag([0.04, 0.09])
    result = solve_min_vol(
        cov,
        list(FIXTURE_SYMBOLS),
        per_instrument_cap=1.0,
        min_cash=0.05,
        turnover_coef=0.0,
        w_prev=np.array([0.5, 0.5]),
        solver_options={"solver": "CLARABEL"},
    )
    assert result["status"] == "optimal"
    assert result["options"]["solver"] == "CLARABEL"


def test_run_optimization_requires_returns_and_symbols_without_fixture_mode(
    portfolio_repository, artifact_root, fixture_composite,
) -> None:
    """WR-04: run_optimization without fixture_mode refuses to fall back to fixture
    data — returns/symbols must come from the caller or a governed panel."""
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
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
    )
    assert run["problem_status"] == "failed"
    assert run["failure_reason"] is not None
    assert "returns and symbols are required" in run["failure_reason"]


def test_created_at_is_real_utc_timestamp(
    portfolio_repository, artifact_root, fixture_composite,
) -> None:
    """WR-06: created_at is a valid UTC ISO timestamp close to now(), not a
    hardcoded planning date."""
    import re
    from datetime import UTC, datetime, timedelta

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
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
        fixture_mode=True,
    )
    created = run["created_at"]
    assert "2026-08-01T00:00:00Z" != created  # not the hardcoded planning date
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", created)
    parsed = datetime.fromisoformat(created.replace("Z", "+00:00"))
    assert parsed.tzinfo == UTC
    assert abs(parsed - datetime.now(UTC)) < timedelta(minutes=5)



def test_optimal_inaccurate_status_is_non_optimal_in_orchestrator(
    portfolio_repository, artifact_root, fixture_composite, monkeypatch,
) -> None:
    """Pitfall 4 (CR-03): an optimal_inaccurate solve is recorded as a non-optimal
    solver_error run through the ORCHESTRATOR path — weights are never persisted.

    Drives the real run_optimization branch with a solve that returns the honest
    'optimal_inaccurate' status (simulated by a solver returning partial values).
    The orchestrator must demote it to a solver_error run with a failure_reason,
    output_weights_json None, and no weights artifact — the inaccurate weights are
    never recorded as if exact (previously the orchestrator treated
    optimal_inaccurate as success and persisted the weights).
    """
    import app.portfolio.optimizer as optimizer_module

    def _inaccurate_solve(cov, symbols, *, per_instrument_cap, min_cash, turnover_coef, w_prev):
        # A real solver returning optimal_inaccurate with partial (inaccurate) values.
        return {
            "status": "optimal_inaccurate",
            "weights": {"600000.SH": 0.8, "600001.SH": 0.2},
            "solver_name": "OSQP",
            "solver_version": "0.6.3",
            "options": {"solver": "OSQP", "max_iter": 1},
        }

    monkeypatch.setattr(optimizer_module, "solve_min_vol", _inaccurate_solve)

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
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
        fixture_mode=True,
    )
    # The honest status is demoted to a non-optimal solver_error run, never promoted.
    assert run["problem_status"] == "solver_error"
    assert run["failure_reason"] is not None
    assert "optimal_inaccurate" in run["failure_reason"]
    # No weights artifact; the inaccurate weights are NOT persisted as if exact.
    assert run.get("output_weights") is None
    assert run.get("output_sha256") is None
    assert run.get("weights_artifact_relative_path") is None
    assert run.get("baseline_weights") is None
    # The run row is immutable and retrievable with the honest status.
    fetched = portfolio_repository.get_optimization_run(run["id"])
    assert fetched is not None
    assert fetched["problem_status"] == "solver_error"
    assert fetched["failure_reason"] == run["failure_reason"]


def test_min_vol_is_default_objective() -> None:
    """PFOL-02: min_volatility remains the default objective (kept green from 11-01)."""
    request = OptimizationRequest(as_of="2026-08-01")
    assert request.objective == "min_volatility"


def test_nan_covariance_records_failed_run(
    portfolio_repository, artifact_root, fixture_composite,
) -> None:
    """IN-03: a NaN/Inf covariance (non-finite returns) produces a recorded
    failed run, not an unrecorded abort."""
    nan_returns = np.array(
        [
            [np.nan, np.nan],
            [np.nan, np.nan],
        ]
    )
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
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
        fixture_mode=True,
        returns=nan_returns,
        symbols=["A", "B"],
    )
    assert run["problem_status"] == "failed"
    assert run["failure_reason"] is not None
    assert run.get("output_weights") is None


def test_write_bundle_cleans_up_namespace_on_mid_write_failure(
    artifact_root, monkeypatch,
) -> None:
    """IN-05: a mid-write failure in write_bundle removes the partially-written
    namespace so no orphan partial bundle survives."""
    from app.portfolio.artifacts import PortfolioArtifactService

    service = PortfolioArtifactService(artifact_root)
    run_id = "a" * 32

    real_write = service._write_json

    def _fail_on_covariance(namespace, run_id_, filename, payload):
        if filename == "covariance.json":
            raise OSError("disk full")
        return real_write(namespace, run_id_, filename, payload)

    monkeypatch.setattr(service, "_write_json", _fail_on_covariance)

    namespace = artifact_root / "research_artifacts" / run_id
    with pytest.raises(OSError, match="disk full"):
        service.write_bundle(
            run_id=run_id,
            weights={"A": 1.0},
            baseline_weights={"A": 1.0},
            covariance=np.eye(2),
        )
    # The namespace must be gone — no orphan partial bundle.
    assert not namespace.exists()


def test_min_cash_equality_is_documented_tested_deviation() -> None:
    """WR-05: min-cash is implemented as a strict budget equality
    (sum(w) == 1 - min_cash), a deliberate tested deviation from the RESEARCH.md
    floor (cp.sum(w) <= 1 - min_cash). The floor invariant still holds exactly
    (1 - sum(w) == min_cash), and the fully-deployed contract is preserved."""
    cov = np.diag([0.04, 0.09])
    result = solve_min_vol(
        cov,
        list(FIXTURE_SYMBOLS),
        per_instrument_cap=1.0,
        min_cash=0.05,
        turnover_coef=0.0,
        w_prev=np.array([0.5, 0.5]),
    )
    weights = np.array([result["weights"][s] for s in FIXTURE_SYMBOLS])
    # The cash floor is exactly satisfied (equality), never below.
    assert abs(1.0 - weights.sum() - 0.05) < 1e-8
    assert 1.0 - weights.sum() >= 0.05 - 1e-8
    # Fully deployed inverse-variance contract (the reason equality is locked).
    expected = np.array([0.04**-1, 0.09**-1])
    expected = expected / expected.sum() * (1 - 0.05)
    assert np.allclose([result["weights"][s] for s in FIXTURE_SYMBOLS], expected, atol=1e-4)


# ---------------------------------------------------------------------------
# 11-06: industry-cap fail-closed gate + covariance artifact breadth
# ---------------------------------------------------------------------------


def test_industry_cap_requested_fails_closed_with_failed_run(
    portfolio_repository, artifact_root, fixture_composite,
) -> None:
    """PFOL-03 (pitfall 8): requesting an industry cap records a failed run with
    reason "industry mapping unavailable" — never silently ignored."""
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
            "industry_cap": 0.05,
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
        fixture_mode=True,
    )
    assert run["problem_status"] == "failed"
    assert run["failure_reason"] == "industry mapping unavailable"
    # The failed run still records the requested cap in the constraint stack.
    assert run["constraint_stack"]["industry_cap"] == 0.05


def test_no_industry_cap_records_null_in_constraint_stack(
    portfolio_repository, artifact_root, fixture_composite,
) -> None:
    """PFOL-03: a run without an industry cap records industry_cap: null."""
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
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
        fixture_mode=True,
    )
    assert run["problem_status"] == "optimal"
    assert run["constraint_stack"]["industry_cap"] is None
    assert run["constraint_stack"]["policy_version"] == "phase-11-policy-v1"


def test_successful_run_records_covariance_sha256_and_artifact(
    portfolio_repository, artifact_root, fixture_composite,
) -> None:
    """PFOL-01/04: a successful run's risk_model_json carries covariance_sha256
    (64 hex) + the covariance artifact path, and the artifact checksum-verifies
    against the digest (Phase 12 seam)."""
    from app.portfolio.artifacts import PortfolioArtifactService

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
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        snapshot=fixture_composite,
        fixture_mode=True,
    )
    risk_model = run["risk_model_detail"]
    digest = risk_model["covariance_sha256"]
    assert len(digest) == 64
    assert all(char in "0123456789abcdef" for char in digest)
    relative_path = risk_model["covariance_artifact_relative_path"]
    assert relative_path.startswith(f"research_artifacts/{run['id']}/covariance.json")

    # The covariance artifact checksum-verifies against the recorded digest.
    service = PortfolioArtifactService(artifact_root)
    payload = service.read_artifact(relative_path, checksum_sha256=digest)
    assert payload  # checksum-verified read succeeded


def test_industry_cap_field_on_schema_is_nullable() -> None:
    """V5: industry_cap defaults to None; a requested cap is carried verbatim."""
    request = OptimizationRequest(as_of="2026-08-01")
    assert request.industry_cap is None
    capped = OptimizationRequest(as_of="2026-08-01", industry_cap=0.05)
    assert capped.industry_cap == 0.05
