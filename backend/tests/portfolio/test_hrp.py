"""RED scaffold for portfolio/hrp.py — deterministic HRP baseline.

Wave 0 (11-02) scaffold: contracts come from RESEARCH.md `## HRP Baseline`; the
module is created by 11-01, so this file is RED until then.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.portfolio.hrp import hrp_portfolio, hrp_weights, render_baseline
from app.portfolio.repository import PortfolioRepository

# Two highly correlated assets (600000/600001) + one orthogonal (600002).
HRP_FIXTURE_COV = np.array(
    [
        [0.04, 0.0396, 0.0001],
        [0.0396, 0.05, 0.0002],
        [0.0001, 0.0002, 0.01],
    ]
)


def test_cluster_ordering_groups_correlated_pair() -> None:
    """PFOL-02: quasi-diagonal leaves order the correlated pair adjacently.

    Assets 0 and 1 (600000/600001) are highly correlated; the single-linkage
    quasi-diagonalization must place them as adjacent leaves.
    """
    from scipy.cluster.hierarchy import leaves_list, linkage
    from scipy.spatial.distance import squareform

    weights = hrp_weights(HRP_FIXTURE_COV)
    assert weights.shape == (3,)
    assert np.all(weights >= 0.0)

    d = np.sqrt(np.diag(HRP_FIXTURE_COV))
    corr = np.clip(HRP_FIXTURE_COV / np.outer(d, d), -1.0, 1.0)
    dist = squareform(np.sqrt((1.0 - corr) / 2.0), checks=False)
    link = linkage(dist, method="single", optimal_ordering=True)
    order = leaves_list(link).astype(int)
    position = {leaf: i for i, leaf in enumerate(order)}
    assert abs(position[0] - position[1]) == 1


def test_hrp_weights_sum_to_one() -> None:
    weights = hrp_weights(HRP_FIXTURE_COV)
    assert abs(weights.sum() - 1.0) < 1e-8


def test_render_baseline_scales_by_one_minus_min_cash() -> None:
    weights = hrp_weights(HRP_FIXTURE_COV)
    scaled = render_baseline(weights, min_cash=0.05)
    assert abs(scaled.sum() - 0.95) < 1e-8
    assert np.all(scaled <= weights + 1e-12)


def test_hrp_deterministic_across_calls() -> None:
    first = hrp_weights(HRP_FIXTURE_COV)
    second = hrp_weights(HRP_FIXTURE_COV)
    assert np.array_equal(first, second)


def test_hrp_weights_in_unit_bounds() -> None:
    weights = hrp_weights(HRP_FIXTURE_COV)
    assert np.all(weights >= 0.0) and np.all(weights <= 1.0)


# ---------------------------------------------------------------------------
# 11-03 objective path: hrp_portfolio as a first-class auditable objective
# ---------------------------------------------------------------------------

HRP_SYMBOLS = ["600000.SH", "600001.SH", "600002.SH"]


def test_hrp_portfolio_scales_to_one_minus_min_cash() -> None:
    """PFOL-02: hrp_portfolio renders weights scaled by (1 - min_cash), in [0, 1]."""
    out = hrp_portfolio(HRP_FIXTURE_COV, min_cash=0.05, symbols=HRP_SYMBOLS)
    weights = out["weights"]
    assert len(weights) == 3
    assert abs(sum(weights.values()) - 0.95) < 1e-8
    assert all(0.0 <= w <= 1.0 for w in weights.values())
    # 与 render_baseline 直接调用完全一致 (同一渲染契约)。
    expected = render_baseline(hrp_weights(HRP_FIXTURE_COV), min_cash=0.05).round(8)
    assert list(weights.values()) == expected.tolist()


def test_hrp_portfolio_is_auditable_without_solver() -> None:
    """PFOL-02/04: the objective record is optimal with solver_name="n/a" — no solver."""
    out = hrp_portfolio(HRP_FIXTURE_COV, min_cash=0.05, symbols=HRP_SYMBOLS)
    assert out["status"] == "optimal"
    assert out["solver_name"] == "n/a"


def test_hrp_portfolio_deterministic_across_calls() -> None:
    """Identical inputs → identical weights (determinism contract, PFOL-02)."""
    first = hrp_portfolio(HRP_FIXTURE_COV, min_cash=0.05, symbols=HRP_SYMBOLS)["weights"]
    second = hrp_portfolio(HRP_FIXTURE_COV, min_cash=0.05, symbols=HRP_SYMBOLS)["weights"]
    assert first == second


def test_hrp_portfolio_rejects_indefinite_covariance() -> None:
    """Pitfall 9: a negative diagonal breaks _cluster_weights — fail closed."""
    indefinite = np.array([[1.0, 1.2], [1.2, 1.0]])
    with pytest.raises(ValueError, match="PSD repair provenance missing"):
        hrp_portfolio(indefinite, min_cash=0.05, symbols=["A", "B"])


def test_hrp_portfolio_rejects_symbol_length_mismatch() -> None:
    """symbols length must match the covariance dimension."""
    with pytest.raises(ValueError, match="symbols length must match covariance dimension"):
        hrp_portfolio(HRP_FIXTURE_COV, min_cash=0.05, symbols=["only-one"])


def test_hrp_objective_run_record_shape(
    portfolio_repository: PortfolioRepository,
    artifact_root: Path,
) -> None:
    """An objective="hrp" run row records solver_name="n/a" + optimal, no solver version."""
    from app.portfolio.optimizer import run_optimization

    # 3 标的 ↔ 3 资产收益率矩阵 (与 HRP_SYMBOLS 对齐, 协方差数值 PSD)。
    returns = np.array(
        [
            [0.010, 0.012, 0.008],
            [0.011, 0.013, 0.007],
            [0.012, 0.014, 0.009],
            [0.009, 0.011, 0.010],
            [0.013, 0.015, 0.006],
            [0.010, 0.012, 0.011],
        ]
    )
    run = run_optimization(
        {
            "objective": "hrp",
            "as_of": "2026-08-01",
            "universe": "cn-a-share",
            "expected_return_method": "none",
            "render_baselines": True,
            "per_instrument_cap": 0.10,
            "min_cash": 0.05,
            "turnover_coef": 0.0014,
        },
        repository=portfolio_repository,
        artifact_service_root=artifact_root,
        returns=returns,
        symbols=list(HRP_SYMBOLS),
    )
    assert run["objective"] == "hrp"
    assert run["problem_status"] == "optimal"
    assert run["solver_name"] == "n/a"
    assert run["solver_version"] == "n/a"
    assert run["solver_options"] == {}
    assert run["baseline_weights"] == run["output_weights"]
    # 不可变: 回读一致。
    fetched = portfolio_repository.get_optimization_run(run["id"])
    assert fetched is not None
    assert fetched["objective"] == "hrp"
    assert fetched["solver_name"] == "n/a"
    assert fetched["output_weights"] == run["output_weights"]
