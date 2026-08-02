"""纸面调仓状态机 — 建议 → 人工审批/驳回 → 纸面成交 (RBAL-02)。

职责: 管理 rebalance 计划的纸面 (paper) 生命周期 —— create_suggestion 记录
``suggested`` 审计事实, approve / reject 是互斥的人工闸门, paper_fill 按
MatcherConfig 费用模型给离散手数计价并记录 ``filled`` 事实。每条迁移都是
append-only 审计事实 (UNIQUE (plan_id, transition) 幂等), 过期计划在创建后
的所有迁移上 fail-closed。

边界契约: 纸面成交只是研究用的审计事实 —— 本模块绝不写 positions, 也不暴露
任何下单/成交路由。全部写入经 repository.record_paper_transition 落到
paper_rebalance_transitions 一张表。

不知道: 求解 (optimizer.py)、风险模型 (risk.py)、账户/持仓管理、HTTP/API、
前端。计划渲染在 portfolio/rebalance.py, 记录在 portfolio/repository.py。
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

from app.backtest.engine import MatcherConfig
from app.portfolio.repository import PortfolioRepository

_TERMINAL_STATES = frozenset({"rejected", "filled"})


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_valid_plan(plan_id: str, *, repository: PortfolioRepository) -> dict[str, object]:
    """Load a plan row; missing plans fail closed."""
    plan = repository.get_rebalance_plan(plan_id)
    if plan is None:
        raise ValueError(f"no rebalance plan with id {plan_id}")
    return plan


def _require_not_expired(plan: dict[str, object]) -> None:
    """Expired plans fail closed on every post-creation transition."""
    expires_at = datetime.fromisoformat(str(plan["expires_at"]))
    if datetime.now(UTC) > expires_at:
        raise ValueError(f"rebalance plan expired at {plan['expires_at']}")


def create_suggestion(plan_id: str, *, repository: PortfolioRepository) -> dict[str, object]:
    """Record the ``suggested`` audit fact for a rebalance plan (RBAL-02).

    幂等: 已存在 ``suggested`` 行时直接返回 (repository 的 UNIQUE
    (plan_id, transition) 键保证)。计划缺失或已过期时 fail-closed。
    """
    plan = _require_valid_plan(plan_id, repository=repository)
    _require_not_expired(plan)
    return repository.record_paper_transition(
        plan_id=plan_id,
        transition="suggested",
        idempotency_key=f"suggest-{plan_id}",
    )


def approve(
    plan_id: str, *, repository: PortfolioRepository, idempotency_key: str
) -> dict[str, object]:
    """The human approval gate — only valid from the ``suggested`` state (RBAL-02).

    已驳回 / 已成交 / 无建议的计划抛 ValueError; 过期计划 fail-closed;
    幂等 (相同 idempotency_key 的重复 approve 返回已有 ``approved`` 行)。
    """
    plan = _require_valid_plan(plan_id, repository=repository)
    _require_not_expired(plan)
    state = repository.get_paper_state(plan_id)
    if state in _TERMINAL_STATES:
        raise ValueError(f"cannot approve a plan in state '{state}'")
    if state not in ("suggested", "approved"):
        raise ValueError("cannot approve a plan that has not been suggested")
    return repository.record_paper_transition(
        plan_id=plan_id,
        transition="approved",
        idempotency_key=idempotency_key,
        previous_state=state,
    )


def reject(
    plan_id: str, *, repository: PortfolioRepository, idempotency_key: str
) -> dict[str, object]:
    """Terminal ``rejected`` transition, mutually exclusive with ``approved`` (RBAL-02).

    仅可从 ``suggested`` 状态驳回; 已审批 / 已成交的计划抛 ValueError;
    幂等 (相同 idempotency_key 的重复 reject 返回已有 ``rejected`` 行)。
    过期计划 fail-closed (与 approve / paper_fill 一致, 逐条迁移把关)。
    """
    plan = _require_valid_plan(plan_id, repository=repository)
    _require_not_expired(plan)
    state = repository.get_paper_state(plan_id)
    if state not in ("suggested", "rejected"):
        raise ValueError("cannot reject a plan that has not been suggested")
    return repository.record_paper_transition(
        plan_id=plan_id,
        transition="rejected",
        idempotency_key=idempotency_key,
        previous_state=state,
    )


def paper_fill(
    plan_id: str,
    *,
    repository: PortfolioRepository,
    prices: dict[str, float],
    matcher_config: MatcherConfig,
) -> dict[str, object]:
    """Value the plan's discrete lots at prices through MatcherConfig fees (RBAL-02).

    仅可从 ``approved`` 状态成交; 记录 ``filled`` 审计事实, 其
    paper_position_delta_json = {symbol: shares} (离散手数原样记录)。计价通过
    MatcherConfig 费用模型 (buy_cost_pct) 给每手数算确定性估值 —— 缺价 /
    非有限 / 非正价格 fail-closed。本函数绝不写 positions —— 唯一写入面是
    repository.record_paper_transition (落到 paper_rebalance_transitions 表)。
    """
    plan = _require_valid_plan(plan_id, repository=repository)
    _require_not_expired(plan)
    state = repository.get_paper_state(plan_id)
    if state not in ("approved", "filled"):
        raise ValueError("cannot paper-fill a plan that has not been approved")
    lot_sizes = plan["lot_sizes"]
    buy_cost_pct = matcher_config.buy_cost_pct()
    valuation: dict[str, float] = {}
    for symbol, shares in lot_sizes.items():
        if symbol not in prices:
            raise ValueError(f"missing price for {symbol}")
        price = float(prices[symbol])
        if not math.isfinite(price) or price <= 0:
            raise ValueError(f"invalid price for {symbol}: {price}")
        valuation[symbol] = round(shares * price * (1 + buy_cost_pct), 4)
    record = repository.record_paper_transition(
        plan_id=plan_id,
        transition="filled",
        idempotency_key=f"fill-{plan_id}",
        previous_state=state,
        paper_position_delta_json=dict(lot_sizes),
    )
    # 计价是审计事实的派生参考 (确定性, 按 MatcherConfig 费用模型); 持久化的
    # paper_position_delta_json 仍是 {symbol: shares}。
    record["fill_valuation"] = valuation
    record["fill_value"] = round(sum(valuation.values()), 4)
    return record
