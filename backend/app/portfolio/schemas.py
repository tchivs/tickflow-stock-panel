"""Phase 11 优化请求 DTO + solver 选项白名单 (V5 输入校验, PFOL-02/03).

职责: 定义 OptimizationRequest 严格 Pydantic 模型 (objective 默认 min_volatility,
baselines 默认渲染, 枚举/日期校验), 以及 SOLVER_OPTIONS_ALLOWLIST —— solve()
唯一可接受的选项面。

不知道: 求解逻辑 (optimizer.py)、风险模型 (risk.py)、约束栈默认值
(constraints.py 才是 phase-11-policy-v1 的权威来源)。
"""
from __future__ import annotations

from datetime import date
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

Objective = Literal["min_volatility", "hrp", "max_sharpe"]

# solve() 唯一可接受的选项面: 不在白名单内的键直接拒绝 (V5)。
SOLVER_OPTIONS_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        "solver",
        "solver_path",
        "eps_abs",
        "eps_rel",
        "tol_gap_abs",
        "tol_gap_rel",
        "max_iter",
        "polish",
        "verbose",
    }
)


class OptimizationRequest(BaseModel):
    """Strict input DTO for one optimization run (frozen, V5 validated)."""

    model_config = ConfigDict(frozen=True)

    objective: Objective = "min_volatility"  # min-vol 是默认 (PFOL-02)
    as_of: date
    universe: str = "cn-a-share"
    model_id: str | None = None  # expected_return_method == composite-zscore-v1 时必填 (仓库层强制)
    expected_return_method: Literal["composite-zscore-v1", "none"] = "composite-zscore-v1"
    render_baselines: bool = True  # 默认渲染基线 (PFOL-02)
    per_instrument_cap: float = Field(default=0.10, gt=0.0, le=1.0)
    min_cash: float = Field(default=0.05, ge=0.0, lt=1.0)
    turnover_coef: float = Field(default=0.0014, ge=0.0)
    turnover_reference: Literal["equal_weight", "run_id"] = "equal_weight"
    w_prev_run_id: str | None = None
