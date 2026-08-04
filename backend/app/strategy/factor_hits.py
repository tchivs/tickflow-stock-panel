"""关联因子 (STRAT-02) — 纯函数聚合: 从策略族结果统计每个标的被哪些策略命中。

该模块无 I/O、不 import 任何策略文件, 是 Phase 18 交叉共振(交叉共振)消费的可复用契约:

    build_factor_hits(results, name_for) -> {symbol: sorted[display names]}
    attach_factor_hits(rows, hits)      -> rows + hit_factors 列 (不改输入)

Threat T-17-05: 聚合只读服务端 `rows` 的 symbol 成员关系, 不合成任何命中 —
一个标的只有在该策略自己的结果行里出现, 才会进入该策略的 hit_factors。
"""
from __future__ import annotations

from typing import Callable

# 关联因子列名 — 结果行上的常量 key
HIT_FACTORS_COLUMN = "hit_factors"


def build_factor_hits(
    results: dict[str, dict],
    name_for: Callable[[str], str] | None = None,
) -> dict[str, list[str]]:
    """从策略族结果聚合 关联因子。

    Args:
        results: ``{strategy_id: {"rows": [{"symbol": ...}, ...]}}`` —
                 run_all 消毒后的 API 结果形状 (也即 Phase 18 ``screener_results/`` 持久化形状)。
        name_for: ``(sid) -> 策略显示名``; None 时退化为 identity (显示名 = 策略 id)。

    Returns:
        ``{symbol: sorted[display names]}`` — 确定性排序 (按码点字典序, 中文名同样确定)。
        没有任何策略命中的 symbol 不出现在结果 dict 里 (零命中 → 缺席)。
    """
    resolver = name_for if name_for is not None else (lambda sid: sid)
    hits: dict[str, set[str]] = {}
    for sid, result in results.items():
        rows = result.get("rows", []) if isinstance(result, dict) else []
        for row in rows:
            symbol = row.get("symbol")
            if symbol is None:
                continue
            hits.setdefault(symbol, set()).add(resolver(sid))
    return {symbol: sorted(names) for symbol, names in hits.items()}


def attach_factor_hits(
    rows: list[dict],
    hits: dict[str, list[str]],
) -> list[dict]:
    """给结果行附加 hit_factors 列, 不修改输入行。

    Args:
        rows: 策略结果行 (``list[dict]``)。
        hits: ``build_factor_hits`` 的返回值。

    Returns:
        新行列表: 每行多一个 ``HIT_FACTORS_COLUMN`` (``list[str]``, 无命中/无 symbol 时为 ``[]``)。
    """
    return [
        {**row, HIT_FACTORS_COLUMN: hits.get(row.get("symbol"), [])}
        for row in rows
    ]
