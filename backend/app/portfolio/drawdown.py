"""Phase 12 回撤 — 水下曲线 + 回撤区间识别 (RSK-03, 12-01 身份路径)。

职责: 在组合收益率序列上做纯 numpy 的水下曲线
(equity / running_max(equity) - 1) 与回撤区间识别 (连续低于
-depth_threshold 且长度 >= min_obs 的区间, 每条 {"start_idx", "end_idx",
"depth"})。平序列 / 短序列 / 空序列 → []。阈值是模块常量
(DRAWDOWN_DEPTH_THRESHOLD=0.02, DRAWDOWN_MIN_OBS=2 —— 裁量记录进证据
reconciliation_json)。

不知道: 模拟 (backtest/engine.py 仅作语义参考, 绝不调用)、权重来源
(optimizer.py)、仓库 (repository.py)、工件存储 (artifacts.py)、市场时间序列。
"""
from __future__ import annotations

from typing import Any

import numpy as np

DRAWDOWN_DEPTH_THRESHOLD = 0.02
DRAWDOWN_MIN_OBS = 2


def underwater_curve(portfolio_returns: np.ndarray) -> np.ndarray:
    """水下曲线 = equity / running_max(equity) - 1 (RSK-03)。

    Args:
        portfolio_returns: (n_obs,) 组合收益率序列。

    Returns:
        (n_obs,) 水下曲线 (<= 0, 首个观测恒为 0)。
    """
    returns = np.asarray(portfolio_returns, dtype=float)
    if returns.ndim != 1:
        raise ValueError("portfolio_returns must be a 1-D series")
    if not np.all(np.isfinite(returns)):
        raise ValueError("portfolio_returns must be finite")
    if returns.size == 0:
        return np.empty(0, dtype=float)
    equity = np.cumprod(1.0 + returns)
    return equity / np.maximum.accumulate(equity) - 1.0


def drawdown_periods(
    underwater: np.ndarray,
    *,
    depth_threshold: float = DRAWDOWN_DEPTH_THRESHOLD,
    min_obs: int = DRAWDOWN_MIN_OBS,
) -> list[dict[str, Any]]:
    """识别水下曲线中深度 >= depth_threshold 且持续 >= min_obs 的区间。

    Args:
        underwater: (n_obs,) 水下曲线 (underwater_curve 的输出)。
        depth_threshold: 回撤深度阈值 (正数, 如 0.02 = 2%)。
        min_obs: 最短持续观测数。

    Returns:
        [{"start_idx", "end_idx", "depth"}], depth 为区间内最大回撤幅度
        (正数 = -min(underwater)); 平 / 短 / 空序列 → []。
    """
    curve = np.asarray(underwater, dtype=float)
    if curve.ndim != 1:
        raise ValueError("underwater must be a 1-D series")
    if not depth_threshold > 0:
        raise ValueError("depth_threshold must be positive")
    if min_obs < 1:
        raise ValueError("min_obs must be a positive integer")
    active = curve < -depth_threshold
    periods: list[dict[str, Any]] = []
    start: int | None = None
    for index, flagged in enumerate(active):
        if flagged and start is None:
            start = index
        elif not flagged and start is not None:
            end = index - 1
            length = end - start + 1
            if length >= min_obs:
                depth = float(-curve[start : end + 1].min())
                periods.append({"start_idx": int(start), "end_idx": int(end), "depth": depth})
            start = None
    if start is not None:
        end = len(curve) - 1
        length = end - start + 1
        if length >= min_obs:
            depth = float(-curve[start : end + 1].min())
            periods.append({"start_idx": int(start), "end_idx": int(end), "depth": depth})
    return periods
