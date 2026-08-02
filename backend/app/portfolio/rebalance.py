"""A股 RebalancePlan 渲染 — 连续权重 → 100 股手数的批量适配层 (RBAL-01)。

职责: 把 Phase 11 优化 run 的连续 output_weights 经 backtest/engine.py 的
lot 公式 (floor(allocation / (price * (1 + buy_cost_pct)) / 100) * 100)
离散化为 100 股手数 —— 复用既有撮合规则, 绝不另建第二套撮合器。计算现金
残差、换手成本 (MatcherConfig 费用模型)、blocked 剔除、过期时间与离散化
RMSE (simple/weighted), 写出 O_EXCL + fsync + sha256 的不可变计划工件并
绑定 rebalance_plans 行。本模块只渲染研究计划, 不含任何下单/成交路径。

不知道: 求解 (optimizer.py)、风险模型 (risk.py)、账户/持仓管理、HTTP/API、
前端。工件存储复用 portfolio/artifacts.py, 记录复用 portfolio/repository.py。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from app.backtest.engine import MatcherConfig
from app.portfolio.artifacts import PortfolioArtifactService
from app.portfolio.repository import PortfolioRepository

_RMSE_DEFINITIONS = frozenset({"simple", "weighted"})


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _default_expires_at() -> str:
    """expires_at 默认值: now + 7 个日历日 (Claude's Discretion)。"""
    return (datetime.now(UTC) + timedelta(days=7)).isoformat()


@dataclass(frozen=True, slots=True)
class DiscretizationResult:
    """One deterministic A-share lot discretization of continuous target weights."""

    target_weights: dict[str, float]
    discrete_weights: dict[str, float]
    lot_sizes: dict[str, int]
    cash_residue: float
    turnover_cost: float
    blocked_instruments: list[str]
    discretization_rmse: float
    rmse_definition: str


@dataclass(frozen=True, slots=True)
class RebalancePlan:
    """An immutable research-only A-share rebalance plan (RBAL-01)."""

    plan_id: str
    optimization_run_id: str
    input_snapshot_sha256: str
    as_of: str
    target_weights: dict[str, float]
    discrete_weights: dict[str, float]
    lot_sizes: dict[str, int]
    cash_residue: float
    turnover_cost: float
    blocked_instruments: list[str]
    discretization_rmse: float
    rmse_definition: str
    expires_at: str
    output_sha256: str
    artifact_relative_path: str
    created_at: str


def _validate_weights(weights: dict[str, float], *, field: str) -> None:
    """Non-finite weights fail closed (mirror analyzer.py L117-118)."""
    if not weights:
        raise ValueError(f"{field} must not be empty")
    values = np.asarray(list(weights.values()), dtype=float)
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{field} must be finite")


def _round_weights(weights: dict[str, float]) -> dict[str, float]:
    """Round weights to 8 decimals (mirror optimizer._finalize_result L346-349)."""
    return {symbol: round(float(value), 8) for symbol, value in weights.items()}


def discretize_weights(
    *,
    target_weights: dict[str, float],
    prices: dict[str, float],
    equity: float,
    matcher_config: MatcherConfig,
    blocked: set[str] | frozenset[str] | list[str] | tuple[str, ...] | None = None,
    odd_lot_positions: dict[str, int] | None = None,
    min_cash: float = 0.0,
    rmse_definition: str = "simple",
) -> DiscretizationResult:
    """Discretize continuous weights into 100-share A-share lots (RBAL-01).

    现金感知最大权重优先 (largest-weight-first): 按 target value 降序逐标的
    套用 engine.py:1158 的 lot 公式 ``floor(allocation / (price * (1 +
    buy_cost_pct)) / 100) * 100`` —— 复用既有撮合规则, 绝不另建第二套撮合器。
    blocked 标的离散权重恒为 0 并原样记录; 奇股持仓 (odd lot) 在目标低于
    一档时整单卖出 (A 股奇股可卖不可买), 目标仍 ≥ 一档时把奇股余数带进
    目标仓位。现金残差 = equity - Σ share·price·(1 + buy_cost_pct), 绝不
    再分配; 换手成本 = Σ buy_value·buy_cost_pct + Σ sell_value·sell_cost_pct
    (REUSE MatcherConfig 费用模型); RMSE 在完整 universe (含 blocked) 上按
    simple / weighted 两种定义计算。

    Args:
        target_weights: 连续权重 {symbol: weight} (Phase 11 output_weights)。
        prices: {symbol: price} — 每个非 blocked 标的都必须有价格。
        equity: 组合净值 (现金预算 = equity - min_cash)。
        matcher_config: backtest/engine.py 的 MatcherConfig (费用模型复用)。
        blocked: 研究员提供的禁买标的集合 (原样记录, 离散权重 0)。
        odd_lot_positions: {symbol: 当前持仓股数} — 仅用于奇股卖出/余数携带。
        min_cash: 最低现金 (默认 0); 突破 min_cash 的计划把超出部分留在残差。
        rmse_definition: "simple" | "weighted"。

    Returns:
        DiscretizationResult (离散权重 / 手数 / 现金残差 / 换手成本 / RMSE)。

    Raises:
        ValueError: 非有限权重、缺价格、未知 rmse_definition。
    """
    if rmse_definition not in _RMSE_DEFINITIONS:
        raise ValueError(f"unknown rmse_definition: {rmse_definition}")
    _validate_weights(target_weights, field="target_weights")
    if not np.isfinite(equity) or equity <= 0:
        raise ValueError("equity must be a positive finite number")
    if min_cash < 0 or not np.isfinite(min_cash) or min_cash > equity:
        raise ValueError("min_cash must be between zero and equity")

    blocked_set = frozenset(blocked or ())
    blocked_instruments = sorted(blocked_set)
    odd_lots = dict(odd_lot_positions or {})
    for symbol, current in odd_lots.items():
        if not np.isfinite(current) or current < 0 or int(current) != current:
            raise ValueError(f"odd_lot_positions[{symbol}] must be non-negative whole shares")
        odd_lots[symbol] = int(current)
    buy_cost_pct = matcher_config.buy_cost_pct()
    sell_cost_pct = matcher_config.sell_cost_pct()

    # 现金感知最大权重优先: 按 target value (= weight·equity) 降序, 符号名
    # 做确定性 tie-break。金额预算 = equity - min_cash。
    ordered = sorted(target_weights.keys(), key=lambda s: (-target_weights[s], s))
    budget = equity - min_cash
    remaining = budget

    lot_sizes: dict[str, int] = {symbol: 0 for symbol in target_weights}
    for symbol in ordered:
        if symbol in blocked_set:
            continue
        if symbol not in prices:
            raise ValueError(f"missing price for {symbol}")
        price = float(prices[symbol])
        if not np.isfinite(price) or price <= 0:
            raise ValueError(f"invalid price for {symbol}: {price}")
        allocation = min(float(target_weights[symbol]) * equity, remaining)
        if allocation <= 0:
            continue
        shares = int(np.floor(allocation / (price * (1 + buy_cost_pct)) / 100) * 100)
        if shares <= 0:
            continue
        cost = shares * price * (1 + buy_cost_pct)
        if cost > remaining + 1e-6:
            # 现金不足时缩到剩余预算内能买的最大整档 (绝不强买半手)。
            shares = int(np.floor(remaining / (price * (1 + buy_cost_pct)) / 100) * 100)
            if shares <= 0:
                continue
            cost = shares * price * (1 + buy_cost_pct)
        lot_sizes[symbol] = shares
        remaining -= cost

    # 奇股处理: 目标 ≥ 一档时携带余数 (250→150 卖 100 留 50); 目标 < 一档时
    # 整单卖出 (含奇股余数)。new buys (无现有持仓) 保持纯整档。
    for symbol, current in odd_lots.items():
        target = lot_sizes.get(symbol, 0)
        remainder = current % 100
        if remainder == 0:
            continue
        if target == 0:
            continue  # 已整单卖出
        if target < 100:
            lot_sizes[symbol] = 0  # 目标低于一档 → 整单卖出 (奇股可卖)
            continue
        lot_sizes[symbol] = target + remainder

    def _cash_residue() -> float:
        return equity - sum(
            shares * float(prices[symbol]) * (1 + buy_cost_pct)
            for symbol, shares in lot_sizes.items()
            if shares > 0
        )

    # Odd-lot carry can add a remainder after the board-lot budget was
    # allocated. Reduce whole board lots deterministically until min_cash is
    # restored; never create a partial buy to repair the budget.
    while _cash_residue() < min_cash - 1e-9:
        candidates = sorted(
            (symbol for symbol, shares in lot_sizes.items() if shares >= 100),
            key=lambda symbol: (-target_weights[symbol], symbol),
        )
        if not candidates:
            break
        symbol = candidates[0]
        next_lots = lot_sizes[symbol] - 100
        lot_sizes[symbol] = next_lots if next_lots >= 100 else 0

    cash_residue = _cash_residue()

    # 换手成本: 买腿 (target - current > 0) 计 buy_cost_pct, 卖腿计 sell_cost_pct。
    buy_value = 0.0
    sell_value = 0.0
    for symbol, price in prices.items():
        current = odd_lots.get(symbol, 0)
        target = lot_sizes.get(symbol, 0)
        delta = target - current
        if delta > 0:
            buy_value += delta * price
        elif delta < 0:
            sell_value += -delta * price
    turnover_cost = buy_value * buy_cost_pct + sell_value * sell_cost_pct

    # 离散权重 = share·price·(1 + buy_cost_pct) / equity (8 位小数)。
    discrete_weights: dict[str, float] = {}
    for symbol in target_weights:
        shares = lot_sizes.get(symbol, 0)
        if shares > 0:
            discrete_weights[symbol] = round(
                shares * float(prices[symbol]) * (1 + buy_cost_pct) / equity, 8
            )
        else:
            discrete_weights[symbol] = 0.0

    # RMSE: 完整 universe (含 blocked, blocked 诚实地贡献 (w_cont - 0)²)。
    universe = sorted(target_weights.keys())
    w_cont = np.asarray([target_weights[s] for s in universe], dtype=float)
    w_disc = np.asarray([discrete_weights[s] for s in universe], dtype=float)
    diff = w_cont - w_disc
    if rmse_definition == "simple":
        discretization_rmse = float(np.sqrt(np.mean(diff**2)))
    else:
        discretization_rmse = float(np.sqrt(np.mean(w_cont * diff**2)))

    return DiscretizationResult(
        target_weights=_round_weights(target_weights),
        discrete_weights=discrete_weights,
        lot_sizes=lot_sizes,
        cash_residue=cash_residue,
        turnover_cost=turnover_cost,
        blocked_instruments=blocked_instruments,
        discretization_rmse=discretization_rmse,
        rmse_definition=rmse_definition,
    )


def build_rebalance_plan(
    *,
    run_id: str,
    prices: dict[str, float],
    equity: float,
    matcher_config: MatcherConfig,
    blocked: set[str] | frozenset[str] | list[str] | tuple[str, ...] | None = None,
    expires_at: str | None = None,
    repository: PortfolioRepository,
    artifact_service_root: Path,
) -> RebalancePlan:
    """Render an immutable RebalancePlan from a recorded Phase 11 run (RBAL-01).

    加载 run → fail-closed (缺失 / problem_status != optimal / 空
    output_weights → ValueError, 镜像 analyzer.py L92-95) → 离散化 → 写出
    O_EXCL + fsync + sha256 计划工件 → 绑定 rebalance_plans 行
    (optimization_run_id + input_snapshot_sha256 + output_sha256 +
    artifact_relative_path)。expires_at 默认 now + 7 个日历日。

    Args:
        run_id: portfolio_optimization_runs.id。
        prices: {symbol: price}。
        equity: 组合净值。
        matcher_config: backtest/engine.py MatcherConfig (费用模型复用)。
        blocked: 禁买标的集合。
        expires_at: 可选; 默认 now + 7 个日历日。
        repository: PortfolioRepository。
        artifact_service_root: PortfolioArtifactService 工件根。

    Returns:
        RebalancePlan (已写工件 + 已绑定行)。

    Raises:
        ValueError: run 缺失 / 非最优 / 空权重 / 非有限权重。
    """
    run = repository.get_optimization_run(run_id)
    if run is None:
        raise ValueError(f"no optimization run with id {run_id}")
    weights_map = run.get("output_weights")
    if run.get("problem_status") != "optimal" or not weights_map:
        raise ValueError(f"run {run_id} has no output weights (problem_status must be optimal)")
    _validate_weights(weights_map, field="output_weights")

    result = discretize_weights(
        target_weights=weights_map,
        prices=prices,
        equity=equity,
        matcher_config=matcher_config,
        blocked=blocked,
        odd_lot_positions=None,
        min_cash=0.0,
        rmse_definition="simple",
    )

    plan_id = uuid.uuid4().hex
    as_of = str(run["as_of"])
    created_at = _now()
    effective_expires_at = expires_at or _default_expires_at()
    plan_dict = {
        "plan_id": plan_id,
        "optimization_run_id": run_id,
        "input_snapshot_sha256": str(run["input_snapshot_sha256"]),
        "as_of": as_of,
        "target_weights": result.target_weights,
        "discrete_weights": result.discrete_weights,
        "lot_sizes": result.lot_sizes,
        "cash_residue": result.cash_residue,
        "turnover_cost": result.turnover_cost,
        "blocked_instruments": result.blocked_instruments,
        "discretization_rmse": result.discretization_rmse,
        "rmse_definition": result.rmse_definition,
        "expires_at": effective_expires_at,
        "created_at": created_at,
    }

    descriptor = PortfolioArtifactService(artifact_service_root).write_analysis_artifact(
        run_id,
        subdir="rebalance",
        filename=f"rebalance-{plan_id}.json",
        payload=plan_dict,
    )
    record = repository.record_rebalance_plan(
        id=plan_id,
        optimization_run_id=run_id,
        input_snapshot_sha256=str(run["input_snapshot_sha256"]),
        as_of=as_of,
        target_weights_json=result.target_weights,
        discrete_weights_json=result.discrete_weights,
        lot_sizes_json=result.lot_sizes,
        cash_residue=result.cash_residue,
        turnover_cost=result.turnover_cost,
        blocked_instruments_json=result.blocked_instruments,
        discretization_rmse=result.discretization_rmse,
        rmse_definition=result.rmse_definition,
        expires_at=effective_expires_at,
        output_sha256=descriptor.checksum_sha256,
        artifact_relative_path=descriptor.relative_path,
        created_at=created_at,
    )
    return RebalancePlan(
        plan_id=plan_id,
        optimization_run_id=run_id,
        input_snapshot_sha256=str(run["input_snapshot_sha256"]),
        as_of=as_of,
        target_weights=result.target_weights,
        discrete_weights=result.discrete_weights,
        lot_sizes=result.lot_sizes,
        cash_residue=result.cash_residue,
        turnover_cost=result.turnover_cost,
        blocked_instruments=result.blocked_instruments,
        discretization_rmse=result.discretization_rmse,
        rmse_definition=result.rmse_definition,
        expires_at=effective_expires_at,
        output_sha256=record["output_sha256"],
        artifact_relative_path=record["artifact_relative_path"],
        created_at=created_at,
    )


def load_rebalance_plan(
    plan_id: str,
    *,
    repository: PortfolioRepository,
    artifact_service_root: Path,
) -> dict[str, Any]:
    """Checksum-verified read of a RebalancePlan artifact (RBAL-01).

    读取 rebalance_plans 行 → 经 read_artifact(relative_path,
    checksum_sha256=output_sha256) 校验字节 → 返回 {plan, content}。校验和
    不匹配 / 文件缺失时抛 ArtifactReadError。
    """
    row = repository.get_rebalance_plan(plan_id)
    if row is None:
        raise ValueError(f"no rebalance plan with id {plan_id}")
    content = PortfolioArtifactService(artifact_service_root).read_artifact(
        row["artifact_relative_path"], checksum_sha256=row["output_sha256"]
    )
    return {"plan": row, "content": json.loads(content.decode("utf-8"))}
