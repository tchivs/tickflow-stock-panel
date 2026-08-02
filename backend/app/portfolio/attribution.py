"""Phase 12 风险归因 — 暴露度 + 边际贡献 + 完整报告 + 硬对账 (RSK-01)。

职责: 在协方差矩阵上做纯 numpy 的归因分解 —— 组合方差 wᵀΣw、风险暴露
w·(Σw) (保留符号: 负值 = 分散化贡献, 绝不 abs)、边际贡献
MC_i = w_i·(Σw)_i (与暴露同一乘积向量, 语义为方差分解)、以及 hard 对账
断言 sum(MC) == wᵀΣw (rtol 1e-12 —— 跨模块完整性守卫, 绝不近似)。
attribution_report 组装完整报告: 带符号暴露 + MC + 摘要 (top contributors /
/ diversifiers / instrument count / policy version)。

暴露与边际贡献共享公式 w_i·(Σw)_i (per 12-CONTEXT): 差异是语义 ——
暴露 = 带符号的风险足迹, MC = 方差分解。两者都保留符号: 负值 = 分散化
贡献, 绝不被 abs() 抹去 (sum identity 依赖带符号分量)。

对账失败抛 AssertionError; 非有限输入抛 ValueError (fail closed)。

不知道: 求解逻辑 (optimizer.py)、风险模型构建 (risk.py)、工件存储
(artifacts.py)、仓库 (repository.py)、市场时间序列 (留在 lake)。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np


def _validate(weights: np.ndarray, cov: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fail-closed input gate: 1-D weights, square finite covariance, aligned."""
    w = np.asarray(weights, dtype=float)
    c = np.asarray(cov, dtype=float)
    if w.ndim != 1:
        raise ValueError("weights must be a 1-D array")
    if c.ndim != 2 or c.shape[0] != c.shape[1]:
        raise ValueError("cov must be a square 2-D matrix")
    if c.shape[0] != w.shape[0]:
        raise ValueError("weights and cov dimensions must match")
    if not (np.all(np.isfinite(w)) and np.all(np.isfinite(c))):
        raise ValueError("weights and cov must be finite")
    return w, c


def portfolio_variance(weights: np.ndarray, cov: np.ndarray) -> float:
    """组合方差 wᵀΣw (RSK-01)。

    Args:
        weights: (n,) 权重向量。
        cov: (n, n) 协方差矩阵。

    Returns:
        ``float(weights @ (cov @ weights))``。
    """
    w, c = _validate(weights, cov)
    return float(w @ (c @ w))


def portfolio_exposure(weights: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """风险暴露 w·(Σw), 保留符号 (RSK-01)。

    负分量 = 分散化贡献 (绝不被 abs() 抹去): 暴露是风险足迹, 不是波动幅度。
    """
    w, c = _validate(weights, cov)
    return w * (c @ w)


def marginal_contributions(weights: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """边际贡献 MC_i = w_i·(Σw)_i —— 同一乘积向量, 语义为方差分解 (RSK-01)。"""
    w, c = _validate(weights, cov)
    return w * (c @ w)


def attribution_report(
    weights: np.ndarray,
    symbols: Sequence[str],
    cov: np.ndarray,
) -> dict[str, Any]:
    """完整归因报告: 组合方差 + 带符号暴露 + MC + 摘要 (RSK-01)。

    复用 portfolio_variance / portfolio_exposure / marginal_contributions /
    reconcile_attribution; 保留所有带符号分量 (负 MC = diversifier, 绝不
    abs)。top_contributors 按 |MC| 降序取前 5 —— 排序用绝对值, 但向量本身
    不被 abs() 包装 (sum identity 依赖原始符号)。

    Args:
        weights: (n,) 权重向量。
        symbols: 标的列表 (长度与 weights 一致)。
        cov: (n, n) 协方差矩阵。

    Returns:
        {"portfolio_variance", "exposure" (symbol → float, 带符号),
         "marginal_contributions" (symbol → float), "sum_contributions",
         "reconciliation_error", "summary": {"instrument_count",
         "top_contributors" (|MC| 降序前 5), "diversifiers" (MC < 0),
         "policy_version": "phase-12-attribution-v1"}}。
        对账失败抛 AssertionError (hard)。
    """
    w, c = _validate(weights, cov)
    keys = list(symbols)
    if len(keys) != len(w):
        raise ValueError("symbols length must match weights")

    variance = portfolio_variance(w, c)
    exposure = portfolio_exposure(w, c)  # 带符号 (负值 = 分散化贡献)
    mc = marginal_contributions(w, c)
    reconciliation = reconcile_attribution(w, c, mc, variance, symbols=keys)

    exposure_map = {key: float(value) for key, value in zip(keys, exposure, strict=True)}
    mc_map = reconciliation["marginal_contributions"]
    top_contributors = sorted(keys, key=lambda key: abs(mc_map[key]), reverse=True)[:5]
    diversifiers = [key for key in keys if mc_map[key] < 0]

    return {
        "portfolio_variance": reconciliation["portfolio_variance"],
        "exposure": exposure_map,
        "marginal_contributions": mc_map,
        "sum_contributions": reconciliation["sum_contributions"],
        "reconciliation_error": reconciliation["reconciliation_error"],
        "summary": {
            "instrument_count": len(keys),
            "top_contributors": top_contributors,
            "diversifiers": diversifiers,
            "policy_version": "phase-12-attribution-v1",
        },
    }


def reconcile_attribution(
    weights: np.ndarray,
    cov: np.ndarray,
    marginal_contributions: np.ndarray | None = None,
    variance: float | None = None,
    *,
    symbols: Sequence[str] | None = None,
) -> dict[str, Any]:
    """硬对账: sum(MC) == wᵀΣw (rtol 1e-12) —— 跨模块完整性守卫。

    默认自行计算方差与 MC; 调用方也可传入 ``marginal_contributions`` /
    ``variance`` 显式验证给定分解 (单元测试用扰动 MC 证明 hard assertion)。

    Args:
        weights: (n,) 权重向量。
        cov: (n, n) 协方差矩阵。
        marginal_contributions: 可选 —— 提供的边际贡献向量 (与 weights 同形)。
        variance: 可选 —— 提供的组合方差。
        symbols: 可选 —— 返回 dict 的键 (标的列表); 缺省用 str(index)。

    Returns:
        {"portfolio_variance", "marginal_contributions" (symbol → float),
         "sum_contributions", "reconciliation_error", "max_abs_error"}。
        对账失败抛 AssertionError (hard, 绝不近似)。
    """
    w, c = _validate(weights, cov)
    if marginal_contributions is None:
        mc = w * (c @ w)
    else:
        mc = np.asarray(marginal_contributions, dtype=float)
        if mc.shape != w.shape or not np.all(np.isfinite(mc)):
            raise ValueError("marginal_contributions must be a finite vector shaped like weights")
    if variance is None:
        var = float(w @ (c @ w))
    else:
        var = float(variance)
        if not np.isfinite(var):
            raise ValueError("variance must be finite")

    np.testing.assert_allclose(np.sum(mc), var, rtol=1e-12, atol=1e-15)

    keys = list(symbols) if symbols is not None else [str(i) for i in range(len(w))]
    if len(keys) != len(w):
        raise ValueError("symbols length must match weights")
    sum_contributions = float(np.sum(mc))
    error = float(abs(sum_contributions - var))
    return {
        "portfolio_variance": var,
        "marginal_contributions": {key: float(value) for key, value in zip(keys, mc, strict=True)},
        "sum_contributions": sum_contributions,
        "reconciliation_error": error,
        "max_abs_error": error,
    }
