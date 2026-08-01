"""Phase 11 样本协方差 + PSD 检查/修复 (PFOL-01)。

职责: 从治理面板的收益率矩阵构建样本协方差; 检查对称矩阵是否半正定 (PSD);
必要时用 eigen_clip 修复并返回完整溯源 (method/epsilon/eigenvalues before/after)。
PSD 修复 NEVER silent —— provenance 是 risk_model_json 的强制字段, optimizer 在
缺少溯源时 fail-closed (pitfall 1/3)。

不知道: 求解逻辑 (optimizer.py)、约束栈 (constraints.py)、行业映射、
市场时间序列 (留在 lake)。
"""
from __future__ import annotations

import numpy as np

from app.portfolio.constraints import PSD_EPSILON_DEFAULT


def sample_covariance(returns: np.ndarray, *, dropna: bool = True) -> np.ndarray:
    """Cross-sectional sample covariance on the common (all-finite) window.

    Args:
        returns: (n_obs, n_assets) 的收益率矩阵。
        dropna: 只保留所有资产都有限的观测行 (公共窗口)。

    Returns:
        (n_assets, n_assets) 样本协方差矩阵。
    """
    if dropna:
        returns = returns[np.all(np.isfinite(returns), axis=1)]
    return np.cov(returns, rowvar=False)


def check_psd(cov: np.ndarray, *, tol: float = 1e-8) -> tuple[float, np.ndarray]:
    """Symmetrize and return (min_eigenvalue, eigenvalues).

    Args:
        cov: 协方差矩阵。
        tol: 判定 PSD 的容差 (数值零)。

    Returns:
        (float(eigvals.min()), eigvals) —— 最小特征值与完整特征值谱。
    """
    sym = (cov + cov.T) / 2.0
    eigvals = np.linalg.eigvalsh(sym)
    return float(eigvals.min()), eigvals


def repair_psd(
    cov: np.ndarray,
    *,
    method: str = "eigen_clip",
    epsilon: float = PSD_EPSILON_DEFAULT,
) -> tuple[np.ndarray, dict]:
    """Eigen-clip PSD repair with mandatory provenance.

    Args:
        cov: 需要修复的协方差矩阵。
        method: 修复方法, 当前支持 ``"eigen_clip"`` (默认) 与 ``"none"``
            (记录为无需修复, 原样返回对称化矩阵)。
        epsilon: 特征值钳位下界。

    Returns:
        (repaired, provenance), 其中 provenance 携带 method / epsilon /
        min_eigenvalue_before / eigenvalues_before / eigenvalues_after;
        method == "none" 时 eigenvalues_after 为 None。
    """
    sym = (cov + cov.T) / 2.0
    eigvals, eigvecs = np.linalg.eigh(sym)

    if method == "none":
        repaired = sym
        eigenvalues_after = None
    elif method == "eigen_clip":
        clipped = np.maximum(eigvals, epsilon)
        repaired = (eigvecs * clipped) @ eigvecs.T
        repaired = (repaired + repaired.T) / 2.0
        eigenvalues_after = np.linalg.eigvalsh(repaired).tolist()
    else:
        raise ValueError(f"unknown PSD repair method: {method}")

    provenance = {
        "method": method,
        "epsilon": epsilon,
        "min_eigenvalue_before": float(eigvals.min()),
        "eigenvalues_before": eigvals.tolist(),
        "eigenvalues_after": eigenvalues_after,
    }
    return repaired, provenance
