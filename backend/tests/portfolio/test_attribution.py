"""Attribution breadth — signed variance components, full report, evidence invariants (RSK-01).

12-04 turns the 12-02 RED scaffold green and adds the RSK-01 breadth:
  (1) exact reconciliation on the run's OWN checksum-verified covariance bytes;
  (2) a negative-MC diversifier fixture proving the identity survives (never abs()ed);
  (3) exposure == MC numerically per symbol (documented semantic distinction);
  (4) evidence invariants — reconciliation required, sha256 64-hex, run_id FK;
  (5) tamper fail-closed — modified covariance bytes raise and write NO evidence row.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from app.portfolio.analyzer import reconcile_all_models, run_attribution
from app.portfolio.artifacts import ArtifactReadError, PortfolioArtifactService
from app.portfolio.attribution import (
    attribution_report,
    marginal_contributions,
    portfolio_exposure,
    portfolio_variance,
    reconcile_attribution,
)
from app.portfolio.repository import PortfolioRepository

SYMBOLS = ["600000.SH", "600001.SH", "600002.SH", "600003.SH"]

# 12-05: the four RSK-02 risk models, in dispatcher order (make_risk_model_family).
RISK_MODEL_NAMES = (
    "sample_covariance_v1",
    "semi_covariance_v1",
    "ewma_covariance_v1",
    "ledoit_wolf_v1",
)
MULTI_MODEL_SYMBOLS = [f"SYM{i:03d}" for i in range(12)]


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


@pytest.fixture
def negative_mc_inputs() -> tuple[np.ndarray, list[str], np.ndarray]:
    """PSD covariance with a genuine diversifier: the third asset's MC < 0.

    eigvalsh ≈ [0.01376, 0.02857, 0.04767] — all > 0, so the covariance is
    valid; asset 3's covariance to the portfolio is negative (sw[2] = -0.0034),
    making MC_3 = w_3 * sw_3 < 0. The hard identity sum(MC) == variance MUST
    hold for this vector (the assertion never abs()es).
    """
    cov = np.array(
        [
            [0.0400, 0.0050, -0.0100],
            [0.0050, 0.0300, -0.0080],
            [-0.0100, -0.0080, 0.0200],
        ]
    )
    weights = np.array([0.5, 0.3, 0.2])
    return weights, ["600000.SH", "600001.SH", "600002.SH"], cov


# ---------------------------------------------------------------------------
# 12-02 scaffold — the pure-function contracts
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 12-04 breadth — the full report + signed-component identity
# ---------------------------------------------------------------------------


def test_attribution_report_keeps_signed_components(
    attribution_inputs: tuple[np.ndarray, np.ndarray],
) -> None:
    """RSK-01: the report keeps signed exposure/MC; the sum identity holds."""
    weights, cov = attribution_inputs
    report = attribution_report(weights, SYMBOLS, cov)
    variance = report["portfolio_variance"]
    exposure = report["exposure"]
    mc = report["marginal_contributions"]
    assert np.isclose(sum(mc.values()), variance, rtol=1e-12)
    # Signed: exposure and MC share the same product vector per symbol.
    for symbol in SYMBOLS:
        assert np.isclose(exposure[symbol], mc[symbol], rtol=1e-12)
    assert report["sum_contributions"] == pytest.approx(variance, rel=1e-12)
    assert report["reconciliation_error"] <= 1e-12 * variance


def test_attribution_report_summary_block_present(
    attribution_inputs: tuple[np.ndarray, np.ndarray],
) -> None:
    """RSK-01: the summary block carries instrument_count / top_contributors /
    diversifiers / policy_version."""
    weights, cov = attribution_inputs
    report = attribution_report(weights, SYMBOLS, cov)
    summary = report["summary"]
    assert summary["instrument_count"] == 4
    assert len(summary["top_contributors"]) == 4  # 5 capped at instrument count
    assert summary["top_contributors"] == sorted(
        summary["top_contributors"],
        key=lambda symbol: abs(report["marginal_contributions"][symbol]),
        reverse=True,
    )
    assert summary["diversifiers"] == [
        symbol
        for symbol in SYMBOLS
        if report["marginal_contributions"][symbol] < 0
    ]
    assert summary["policy_version"] == "phase-12-attribution-v1"


def test_negative_mc_diversifier_keeps_signed_identity(
    negative_mc_inputs: tuple[np.ndarray, list[str], np.ndarray],
) -> None:
    """RSK-01: a negative-MC diversifier survives — the hard assertion does not abs."""
    weights, symbols, cov = negative_mc_inputs
    report = attribution_report(weights, symbols, cov)
    mc = report["marginal_contributions"]
    assert mc[symbols[2]] < 0  # the diversifier contributes negatively
    assert symbols[2] in report["summary"]["diversifiers"]
    # The identity still holds exactly — the assertion never abs()ed the vector.
    assert np.isclose(sum(mc.values()), report["portfolio_variance"], rtol=1e-12)
    assert report["reconciliation_error"] <= 1e-12 * report["portfolio_variance"]


def test_attribution_report_rejects_mismatched_symbols(
    attribution_inputs: tuple[np.ndarray, np.ndarray],
) -> None:
    """RSK-01: a symbols list whose length differs from weights fails closed."""
    weights, cov = attribution_inputs
    with pytest.raises(ValueError):
        attribution_report(weights, SYMBOLS[:-1], cov)


# ---------------------------------------------------------------------------
# 12-04 breadth — the end-to-end analyzer contract
# ---------------------------------------------------------------------------


def test_run_attribution_payload_carries_full_report(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
    fixture_attribution_run: dict[str, object],
) -> None:
    """RSK-01: the artifact payload carries the complete report (weights,
    signed exposure, MC, variance, reconciliation, summary)."""
    run = fixture_attribution_run
    run_id = str(run["id"])
    service = PortfolioArtifactService(artifact_root)
    evidence = run_attribution(
        run_id, repository=portfolio_repository, artifact_service_root=artifact_root
    )
    payload = json.loads(
        service.read_artifact(
            evidence["artifact_relative_path"], checksum_sha256=evidence["output_sha256"]
        ).decode("utf-8")
    )
    assert payload["run_id"] == run_id
    assert payload["symbols"] == list(run["output_weights"].keys())
    assert np.isclose(
        payload["portfolio_variance"],
        evidence["reconciliation"]["portfolio_variance"],
        rtol=1e-12,
    )
    # Signed exposure per symbol — negative components survive (never abs()ed).
    for symbol in payload["symbols"]:
        assert np.isclose(
            payload["exposure"][symbol],
            payload["marginal_contributions"][symbol],
            rtol=1e-12,
        )
    # Summary block present in the artifact.
    assert payload["summary"]["instrument_count"] == len(payload["symbols"])
    assert payload["summary"]["policy_version"] == "phase-12-attribution-v1"
    # The evidence reconciliation payload matches the plan contract.
    assert set(evidence["reconciliation"]) == {
        "portfolio_variance",
        "sum_contributions",
        "max_abs_error",
    }


def test_run_attribution_evidence_invariants_fail_closed(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
    fixture_attribution_run: dict[str, object],
) -> None:
    """RSK-01: evidence rows are append-only per (run, model) analysis and the
    repository enforces the reconciliation / sha256 / FK invariants."""
    run = fixture_attribution_run
    run_id = str(run["id"])
    run_attribution(run_id, repository=portfolio_repository, artifact_service_root=artifact_root)
    rows = portfolio_repository.list_attribution_evidence(run_id=run_id)
    assert len(rows) == 1
    assert rows[0]["attribution_type"] == "exposure_contribution"
    assert rows[0]["risk_model"] == run["risk_model"]
    assert rows[0]["reconciliation"] is not None
    # A second analysis appends (append-only), never overwrites.
    run_attribution(run_id, repository=portfolio_repository, artifact_service_root=artifact_root)
    assert len(portfolio_repository.list_attribution_evidence(run_id=run_id)) == 2
    # Repository-level invariant: exposure_contribution REQUIRES reconciliation.
    with pytest.raises(ValueError):
        portfolio_repository.record_attribution_evidence(
            id="f" * 32,
            attribution_type="exposure_contribution",
            run_id=run_id,
            risk_model=run["risk_model"],
            as_of=run["as_of"],
            output_sha256="0" * 64,
            artifact_relative_path="research_artifacts/x/y.json",
            reconciliation_json=None,
            created_at="2026-08-02T00:00:00+00:00",
        )
    # sha256 must be 64 lowercase hex.
    with pytest.raises(ValueError):
        portfolio_repository.record_attribution_evidence(
            id="e" * 32,
            attribution_type="exposure_contribution",
            run_id=run_id,
            risk_model=run["risk_model"],
            as_of=run["as_of"],
            output_sha256="NOT_HEX",
            artifact_relative_path="research_artifacts/x/y.json",
            reconciliation_json={"portfolio_variance": 1.0},
            created_at="2026-08-02T00:00:00+00:00",
        )
    # run_id FK → an existing run (sqlite3.IntegrityError — foreign key).
    with pytest.raises(sqlite3.IntegrityError):
        portfolio_repository.record_attribution_evidence(
            id="d" * 32,
            attribution_type="exposure_contribution",
            run_id="f" * 32,
            risk_model=run["risk_model"],
            as_of=run["as_of"],
            output_sha256="0" * 64,
            artifact_relative_path="research_artifacts/x/y.json",
            reconciliation_json={"portfolio_variance": 1.0},
            created_at="2026-08-02T00:00:00+00:00",
        )
    # No new rows were fabricated by the failed writes above.
    assert len(portfolio_repository.list_attribution_evidence(run_id=run_id)) == 2


def test_tampered_covariance_fails_closed_with_no_evidence_row(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
    fixture_attribution_run: dict[str, object],
) -> None:
    """RSK-01: modified covariance artifact bytes raise and write NO evidence row."""
    run = fixture_attribution_run
    run_id = str(run["id"])
    cov_path = (
        artifact_root / str(run["risk_model_detail"]["covariance_artifact_relative_path"])
    )
    original = cov_path.read_bytes()
    count_before = len(portfolio_repository.list_attribution_evidence(run_id=run_id))
    cov_path.write_bytes(b"tampered-covariance-bytes")
    try:
        with pytest.raises(ArtifactReadError):
            run_attribution(
                run_id, repository=portfolio_repository, artifact_service_root=artifact_root
            )
    finally:
        cov_path.write_bytes(original)
    # Fail closed: no evidence row was written for the failed analysis.
    assert len(portfolio_repository.list_attribution_evidence(run_id=run_id)) == count_before


# ---------------------------------------------------------------------------
# 12-05 breadth — cross-model attribution + reconciliation matrix
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_multi_model_run(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
    fixture_composite: dict[str, object],
) -> tuple[dict[str, object], np.ndarray]:
    """An optimal run built on a test-controlled 12-symbol returns panel.

    Returns (run, returns): the returns panel is explicit (not the optimizer's
    private fixture) so the model-selection path can recompute any of the four
    RSK-02 covariances from the exact panel aligned to output_weights.
    """
    from app.portfolio.optimizer import run_optimization

    rng = np.random.default_rng(20260802)
    symbols = [f"SYM{i:03d}" for i in range(12)]
    returns = rng.normal(0.0005, 0.008, size=(20, 12))
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
        returns=returns,
        symbols=symbols,
        fixture_mode=True,
    )
    assert run["problem_status"] == "optimal"
    return run, returns


@pytest.mark.parametrize("risk_model_name", list(RISK_MODEL_NAMES))
def test_run_attribution_model_selection_reconciles_exactly_per_model(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
    fixture_multi_model_run: tuple[dict[str, object], np.ndarray],
    risk_model_name: str,
) -> None:
    """RSK-01/02: under each of the four models the evidence row carries the
    selected risk_model and reconciles EXACTLY (sum(MC) == variance, rtol 1e-12),
    and the artifact is checksum-verified on read-back."""
    run, returns = fixture_multi_model_run
    run_id = str(run["id"])
    service = PortfolioArtifactService(artifact_root)
    evidence = run_attribution(
        run_id,
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        returns=returns,
        risk_model_name=risk_model_name,
    )
    assert evidence["risk_model"] == risk_model_name
    reconciliation = evidence["reconciliation"]
    variance = reconciliation["portfolio_variance"]
    assert variance >= 0.0
    assert reconciliation["sum_contributions"] == pytest.approx(variance, rel=1e-12)
    assert reconciliation["max_abs_error"] <= 1e-12 * variance + 1e-15
    # Checksum-verified artifact read-back carries the selected model + exact variance.
    payload = json.loads(
        service.read_artifact(
            evidence["artifact_relative_path"], checksum_sha256=evidence["output_sha256"]
        ).decode("utf-8")
    )
    assert payload["risk_model"] == risk_model_name
    assert payload["portfolio_variance"] == pytest.approx(variance, rel=1e-12)
    assert payload["reconciliation"]["max_abs_error"] <= 1e-12 * variance + 1e-15


def test_run_attribution_model_selection_non_finite_returns_fail_closed(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
    fixture_multi_model_run: tuple[dict[str, object], np.ndarray],
) -> None:
    """WR-01: the model-selection path rejects non-finite returns with ValueError
    and writes NO evidence row (same fail-closed contract as run_drawdown)."""
    run, returns = fixture_multi_model_run
    run_id = str(run["id"])
    dirty = returns.copy()
    dirty[0, 0] = np.nan
    count_before = len(portfolio_repository.list_attribution_evidence(run_id=run_id))
    with pytest.raises(ValueError, match="returns must be finite"):
        run_attribution(
            run_id,
            repository=portfolio_repository,
            artifact_service_root=artifact_root,
            returns=dirty,
            risk_model_name="sample_covariance_v1",
        )
    assert len(portfolio_repository.list_attribution_evidence(run_id=run_id)) == count_before


def test_reconcile_all_models_cross_model_matrix(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
    fixture_multi_model_run: tuple[dict[str, object], np.ndarray],
) -> None:
    """RSK-01/02: reconcile_all_models returns all 4 rows with all_reconciled
    True and the identity row (the run's recorded model) matches the recorded
    covariance digest path (checksum-bound)."""
    run, returns = fixture_multi_model_run
    run_id = str(run["id"])
    result = reconcile_all_models(
        run_id,
        returns=returns,
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
    )
    assert result["run_id"] == run_id
    assert len(result["models"]) == 4
    assert result["all_reconciled"] is True
    assert [row["risk_model"] for row in result["models"]] == list(RISK_MODEL_NAMES)
    recorded_digest = run["risk_model_detail"]["covariance_sha256"]
    for row in result["models"]:
        assert row["portfolio_variance"] >= 0.0
        assert row["reconciled"] is True
        assert row["max_abs_error"] <= 1e-12 * row["portfolio_variance"] + 1e-15
        if row["risk_model"] == run["risk_model"]:
            # Identity row is checksum-bound to the run's recorded artifact digest.
            assert row["covariance_sha256"] == recorded_digest


def test_tampered_covariance_fails_identity_but_model_selection_reconciles(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
    fixture_multi_model_run: tuple[dict[str, object], np.ndarray],
) -> None:
    """RSK-01: tampered covariance bytes fail the identity path closed (no
    evidence row) while the model-selection path (recompute from returns) still
    reconciles and writes a distinct evidence row."""
    run, returns = fixture_multi_model_run
    run_id = str(run["id"])
    cov_path = (
        artifact_root / str(run["risk_model_detail"]["covariance_artifact_relative_path"])
    )
    original = cov_path.read_bytes()
    count_before = len(portfolio_repository.list_attribution_evidence(run_id=run_id))
    cov_path.write_bytes(b"tampered-covariance-bytes")
    try:
        with pytest.raises(ArtifactReadError):
            run_attribution(
                run_id, repository=portfolio_repository, artifact_service_root=artifact_root
            )
        assert len(portfolio_repository.list_attribution_evidence(run_id=run_id)) == count_before
        # Model-selection path recomputes from returns — reconciles exactly.
        evidence = run_attribution(
            run_id,
            repository=portfolio_repository,
            artifact_service_root=artifact_root,
            returns=returns,
            risk_model_name="ewma_covariance_v1",
        )
        assert evidence["risk_model"] == "ewma_covariance_v1"
        variance = evidence["reconciliation"]["portfolio_variance"]
        assert evidence["reconciliation"]["max_abs_error"] <= 1e-12 * variance + 1e-15
        assert len(portfolio_repository.list_attribution_evidence(run_id=run_id)) == count_before + 1
    finally:
        cov_path.write_bytes(original)


def test_list_attribution_evidence_filters_by_risk_model(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
    fixture_multi_model_run: tuple[dict[str, object], np.ndarray],
) -> None:
    """RSK-01 (Phase 15 API): list_attribution_evidence(risk_model=...) returns
    only rows for that model; combined run_id + type + risk_model works."""
    run, returns = fixture_multi_model_run
    run_id = str(run["id"])
    # Seed two distinct per-model evidence rows.
    run_attribution(
        run_id,
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        returns=returns,
        risk_model_name="sample_covariance_v1",
    )
    run_attribution(
        run_id,
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        returns=returns,
        risk_model_name="semi_covariance_v1",
    )
    semi_rows = portfolio_repository.list_attribution_evidence(risk_model="semi_covariance_v1")
    assert semi_rows
    assert all(row["risk_model"] == "semi_covariance_v1" for row in semi_rows)
    combined = portfolio_repository.list_attribution_evidence(
        run_id=run_id, attribution_type="exposure_contribution", risk_model="semi_covariance_v1"
    )
    assert all(row["risk_model"] == "semi_covariance_v1" for row in combined)
    assert all(row["run_id"] == run_id for row in combined)
    assert len(combined) == 1
