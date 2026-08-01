"""Phase 11 确定性 HRP 基线 (PFOL-02)。

职责: 基于 scipy.cluster.hierarchy (single linkage + optimal_ordering) 的
quasi-diagonalization + 递归二分逆方差分配, 输出确定性的全投资 HRP 权重;
render_baseline 按 (1 - min_cash) 缩放, 使与 QP 解的比较口径一致。

不知道: 求解逻辑 (optimizer.py)、约束栈 (constraints.py)、行业映射;
scipy 仅用于聚类, 绝不充当通用优化器。
"""
from __future__ import annotations

import numpy as np
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.spatial.distance import squareform


def _cov_to_corr(cov: np.ndarray) -> np.ndarray:
    d = np.sqrt(np.diag(cov))
    corr = cov / np.outer(d, d)
    return np.clip(corr, -1.0, 1.0)


def _cluster_weights(cov: np.ndarray, idx: np.ndarray) -> np.ndarray:
    sub = cov[np.ix_(idx, idx)]
    inv_diag = 1.0 / np.diag(sub)  # inverse-variance within cluster
    return inv_diag / inv_diag.sum()


def _cluster_variance(cov: np.ndarray, idx: np.ndarray, w: np.ndarray) -> float:
    sub = cov[np.ix_(idx, idx)]
    return float(w @ sub @ w)


def _recursive_bisect(
    cov: np.ndarray,
    order: np.ndarray,
    left: int = 0,
    right: int | None = None,
    out: np.ndarray | None = None,
) -> np.ndarray:
    if right is None:
        right = len(order)
    if out is None:
        out = np.ones(len(order))
    if right - left <= 1:
        return out
    mid = (left + right) // 2
    l_idx, r_idx = order[left:mid], order[mid:right]
    w_l, w_r = _cluster_weights(cov, l_idx), _cluster_weights(cov, r_idx)
    v_l, v_r = _cluster_variance(cov, l_idx, w_l), _cluster_variance(cov, r_idx, w_r)
    alpha = 1.0 - v_l / (v_l + v_r)  # more weight to lower-variance cluster
    out[l_idx] *= alpha
    out[r_idx] *= 1.0 - alpha
    _recursive_bisect(cov, order, left, mid, out)
    _recursive_bisect(cov, order, mid, right, out)
    return out


def hrp_weights(cov: np.ndarray) -> np.ndarray:
    """Deterministic hierarchical risk parity weights over ``cov``.

    前置条件: cov 必须已通过 PSD gate (正对角线), 否则 _cluster_weights 的
    逆方差在负对角线上失去意义 (pitfall 9)。

    Returns:
        (n,) 全投资权重向量 (sum == 1), 纯 NumPy 递归, 确定性。
    """
    corr = _cov_to_corr(cov)
    dist = squareform(np.sqrt((1.0 - corr) / 2.0), checks=False)
    link = linkage(dist, method="single", optimal_ordering=True)  # quasi-diagonalization
    order = leaves_list(link).astype(int)  # scipy.cluster.hierarchy.leaves_list
    return _recursive_bisect(cov, order)


def render_baseline(weights: np.ndarray, *, min_cash: float) -> np.ndarray:
    """Scale a full-investment HRP vector by ``(1 - min_cash)``.

    使 HRP 基线与含现金地板的 QP 解口径一致 (apples-to-apples, PFOL-02)。
    """
    return weights * (1.0 - min_cash)
