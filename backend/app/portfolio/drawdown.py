"""Phase 12 回撤 — 水下曲线 + 回撤区间识别 + 逐标的 × 逐段归因 (RSK-03)。

职责: 在组合收益率序列上做纯 numpy 的水下曲线
(equity / running_max(equity) - 1) 与回撤区间识别 (连续低于
-depth_threshold 且长度 >= min_obs 的区间, 每条 {"start_idx", "end_idx",
"depth"})。平序列 / 短序列 / 空序列 → []。阈值是模块常量
(DRAWDOWN_DEPTH_THRESHOLD=0.02, DRAWDOWN_MIN_OBS=2 —— 裁量记录进证据
reconciliation_json)。

drawdown_attribution 对每个已识别的回撤段做逐标的 × 逐段分解:
c_i = Σ_{t in [start,end]} w_i · r_{i,t}, 段收益 = Σ_t Σ_i w_i r_{i,t},
并 HARD 断言 Σ c_i == 段收益 (rtol 1e-10 —— 线性分解, 精确于算术, 绝不
近似; 与 RSK-01 的方差对账对称)。贡献是算术的 (非复利) 设计: 恒等式
Σ c_i == 段收益 在算术上精确成立, 复利会把恒等式变成近似。

不知道: 模拟 (backtest/engine.py 仅作语义参考, 绝不调用)、权重来源
(optimizer.py)、仓库 (repository.py)、工件存储 (artifacts.py)、市场时间序列。
"""

from __future__ import annotations

from collections.abc import Sequence
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


def drawdown_attribution(
    weights: np.ndarray,
    returns: np.ndarray,
    periods: list[dict[str, Any]],
    *,
    symbols: Sequence[str] | None = None,
) -> dict[str, Any]:
    """逐标的 × 逐时间段的回撤归因 (RSK-03)。

    对每个已识别回撤段 {start_idx, end_idx}: 逐标的贡献
    c_i = Σ_{t in [start,end]} w_i · r_{i,t}, 段收益
    = Σ_t Σ_i w_i r_{i,t}, 并 HARD 断言 Σ_i c_i == 段收益 (rtol 1e-10,
    atol 1e-15 —— 线性分解, 精确于算术, 绝不近似; 与 RSK-01 的方差对账
    对称)。贡献是算术的 (非复利) 设计: 恒等式在算术上精确成立, 复利会把
    它变成近似。空 periods → 全零摘要 (identity vacuous)。

    Args:
        weights: (n,) 组合权重 (与 returns 列对齐)。
        returns: (n_obs, n) 标的收益率面板 (列序与 weights 对齐)。
        periods: drawdown_periods 的输出 (含 start_idx / end_idx)。
        symbols: 可选标的列表 (长度与 weights 一致); 缺省用 "SYM000" 风格键。

    Returns:
        {"periods": [{start_idx, end_idx, depth, segment_return,
         contributions: {symbol → float}}], "max_depth": float,
         "longest_period": int (obs), "segment_reconciliation_max_abs_error": float}。
        对账失败抛 AssertionError (hard)。
    """
    w = np.asarray(weights, dtype=float)
    panel = np.asarray(returns, dtype=float)
    if w.ndim != 1:
        raise ValueError("weights must be a 1-D array")
    if panel.ndim != 2 or panel.shape[1] != w.shape[0]:
        raise ValueError("returns must be a 2-D panel whose columns align with weights")
    if not (np.all(np.isfinite(w)) and np.all(np.isfinite(panel))):
        raise ValueError("weights and returns must be finite")
    keys = list(symbols) if symbols is not None else [f"SYM{i:03d}" for i in range(len(w))]
    if len(keys) != len(w):
        raise ValueError("symbols length must match weights")

    max_abs_error = 0.0
    detailed: list[dict[str, Any]] = []
    for period in periods:
        start = int(period["start_idx"])
        end = int(period["end_idx"])
        if start < 0 or end < start or end >= panel.shape[0]:
            raise ValueError("period indices out of bounds for the returns panel")
        segment = panel[start : end + 1, :]  # (n_obs_in_segment, n)
        contributions = w * segment.sum(axis=0)  # c_i = Σ_t w_i r_{i,t}
        # 段收益独立计算: Σ_t Σ_i w_i r_{i,t} == 组合收益率在段内的算术和。
        # 与逐标的路径分开求值, 使断言是真实的恒等式检查 (线性分解, 精确于算术)。
        segment_return = float((w @ segment.T).sum())
        # HARD 恒等式: Σ_i c_i == 段收益 (rtol 1e-10)。
        np.testing.assert_allclose(
            np.sum(contributions), segment_return, rtol=1e-10, atol=1e-15
        )
        error = float(abs(float(np.sum(contributions)) - segment_return))
        max_abs_error = max(max_abs_error, error)
        detailed.append(
            {
                "start_idx": start,
                "end_idx": end,
                "depth": float(period["depth"]),
                "segment_return": segment_return,
                "contributions": {
                    key: float(value) for key, value in zip(keys, contributions, strict=True)
                },
            }
        )

    depths = [float(period["depth"]) for period in detailed]
    lengths = [int(period["end_idx"]) - int(period["start_idx"]) + 1 for period in detailed]
    return {
        "periods": detailed,
        "max_depth": max(depths, default=0.0),
        "longest_period": max(lengths, default=0),
        "segment_reconciliation_max_abs_error": max_abs_error,
    }
