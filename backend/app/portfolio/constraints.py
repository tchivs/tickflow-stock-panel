"""Phase 11 组合约束栈策略常量 (PFOL-03).

职责: 定义 phase-11-policy-v1 策略常量 —— 单标的权重上限、最低现金、换手惩罚
系数、PSD 修复 epsilon、max-Sharpe 风险厌恶系数, 以及行业上限的 fail-closed
闸门。所有取值会随每条 run 序列化进 constraint_stack_json, 保证策略可审计。

不知道: 求解逻辑 (optimizer.py)、风险模型 (risk.py)、行业映射数据 (尚无治理
行业 JOIN, INDUSTRY_CAP_ENABLED=False)。
"""
from __future__ import annotations

# provenance: "phase-11-policy-v1"
# 单标的权重上限: 任一标的权重不得超过 10% (A 股集中度控制)。
PER_INSTRUMENT_CAP_DEFAULT = 0.10
# 最低现金: cp.sum(w) <= 1 - MIN_CASH_DEFAULT 是现金地板 (下限), 绝非严格等式。
MIN_CASH_DEFAULT = 0.05
# 换手惩罚系数: 往返成本代理 ≈ 佣金双边 2x2bp + 滑点双边 2x5bps = 0.0014,
# 源自 MatcherConfig 费用模型 (backtest/engine.py buy_cost_pct/sell_cost_pct)。
TURNOVER_COEF_DEFAULT = 0.0014
# PSD 修复 epsilon: eigen_clip 钳位到的最小特征值。
PSD_EPSILON_DEFAULT = 1e-10
# max-Sharpe 风险厌恶系数 (仅 objective == "max_sharpe" 时使用)。
MAX_SHARPE_RISK_AVERSION = 1.0
# 换手基准 (turnover_reference) 合法取值: 首次运行用等权 1/n 锚, 后续运行引用
# 先前 run 的校验和绑定权重 (PFOL-03, Phase 14 再平衡继承)。
TURNOVER_REFERENCE_EQUAL_WEIGHT = "equal_weight"
TURNOVER_REFERENCE_RUN_ID = "run_id"
# 行业上限: fail-closed —— 行业 JOIN 未实现前恒为 False; 任何请求都会显式报错。
INDUSTRY_CAP_ENABLED = False

_POLICY_VERSION = "phase-11-policy-v1"


def assert_industry_cap_unavailable(requested: bool) -> None:
    """请求行业上限时 fail-closed, 绝不静默忽略 (PFOL-03 pitfall 8).

    Args:
        requested: 调用方是否请求了行业上限。

    Raises:
        ValueError: 当 requested 为 True 且行业映射尚未治理时, 抛出固定消息
            "industry mapping unavailable"。
    """
    if requested:
        raise ValueError("industry mapping unavailable")
