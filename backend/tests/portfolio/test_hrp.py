"""RED scaffold for portfolio/hrp.py — deterministic HRP baseline.

Wave 0 (11-02) scaffold: contracts come from RESEARCH.md `## HRP Baseline`; the
module is created by 11-01, so this file is RED until then.
"""
from __future__ import annotations

import numpy as np
from app.portfolio.hrp import hrp_weights, render_baseline

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
