"""股池 Hub 投影服务 — POOL-01/02/03 后端。

只读投影契约 (D-01/D-02/D-03/D-04):
- 从 strategy_cache 读取单一 as_of 的策略结果 (其 ``results`` 形状即
  ``screener_results/`` 持久化形状), 卡片 ``total`` 与明细 ``rows`` 来自同一次
  读取, 永不漂移 (PITFALL #10, D-02)。
- 每行投影出六列: code / 名称 (name) / 开盘涨幅 (open_gap) / 涨跌幅 (change_pct) /
  概念板块 (concept_board) / 关联因子 (hit_factors), 外加服务端计算的
  交叉共振 (cross_resonance = len(hit_factors) >= 2, D-03)。
- 概念筛选是当前 as_of 池上的投影: 只收窄 rows, ``total`` 保持权威全量 (D-04)。
- 本模块不 import 任何 broker/order/execution/trade/portfolio 模块, 也没有任何
  写路径 — POOL-03 零执行权限由 ``tests/test_pool_hub.py`` 的 AST 守卫锁定。
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

from app.services import strategy_cache
from app.services.ext_data import ExtConfigStore
from app.services.market_overview_builder import (
    _dimension_field,
    _dimension_values,
    _read_ext_rows,
    _symbol_keys,
)

# 概念维度关键字 — 与 market_overview_builder._dimension_field 的 "concept" 分支一致
_CONCEPT_DIMENSION = "concept"


def _safe_num(value: Any) -> float | None:
    """JSON 消毒: NaN / Inf → None (镜像 ``screener._safe`` 的数值语义)。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return float(value)
    return value


def _build_concept_map(data_dir: Path) -> dict[str, list[str]]:
    """从 ext concept seam 构建 ``{SYMBOL_UPPER: sorted[概念]}`` 映射 (D-04)。

    复用 overview/ConceptAnalysis 的读取 seam — 无新概念数据源:
    ``_dimension_field`` / ``_read_ext_rows`` / ``_dimension_values`` / ``_symbol_keys``。
    没有 concept 维度配置或数据缺失时返回空 dict — 概念板块渲染为 ``[]`` / ``—``,
    绝不崩溃 (T-18-05)。
    """
    concept_map: dict[str, set[str]] = {}
    for config in ExtConfigStore(data_dir).load_all():
        field = _dimension_field(config, _CONCEPT_DIMENSION)
        if field is None:
            continue
        rows = _read_ext_rows(data_dir, config, field)
        for row in rows:
            concepts = _dimension_values(row.get(field))
            if not concepts:
                continue
            for key in _symbol_keys(row, config):
                concept_map.setdefault(key, set()).update(concepts)
    return {symbol: sorted(names) for symbol, names in concept_map.items()}


def build_pool_hub(
    data_dir: Path,
    as_of: str | None = None,
    concept: str | None = None,
    name_for: Callable[[str], str] | None = None,
) -> dict:
    """构建单一 as_of 的股池 Hub 投影 (POOL-01/02)。

    读取 ``strategy_cache.read_cache(data_dir)`` — 单一 as_of 的权威来源。若缓存为
    None, 返回空 Hub。``as_of`` 以缓存为准 (调用方传入不一致的日期时仍以缓存日期
    回显, 不伪造第二个日期); ``concept`` 只收窄 ``rows``, ``total`` 保持权威全量。

    Args:
        data_dir: 数据根目录 (含 user_data/strategy_cache.json 与 ext_data/)。
        as_of: 调用方期望日期; 与缓存 as_of 一致才回显, 否则回显缓存日期。
        concept: 概念筛选 (大小写不敏感子串); None/空串 = 不过滤。
        name_for: ``(sid) -> 策略显示名``; None 时退化为 sid。
    """
    cache = strategy_cache.read_cache(data_dir)
    if cache is None:
        return {"as_of": None, "updated_at": None, "strategies": [], "resonance_count": 0}

    cache_as_of = cache.get("as_of")
    # 单一数据源: 始终回显缓存日期; 调用方日期仅在完全一致时被采纳 (等价于回显)。
    resolved_as_of = as_of if (as_of and as_of == cache_as_of) else cache_as_of

    concept_map = _build_concept_map(data_dir)
    resolver = name_for if name_for is not None else (lambda sid: sid)

    needle = concept.strip().lower() if concept else ""

    strategies: list[dict[str, Any]] = []
    resonance_symbols: set[str] = set()

    results = cache.get("results", {})
    for sid, result in results.items():
        rows = result.get("rows", []) if isinstance(result, dict) else []
        if not isinstance(rows, list):
            rows = []
        total = len(rows)
        projected_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("symbol"):
                continue
            symbol = str(row["symbol"])
            hit_factors = list(row.get("hit_factors") or [])
            cross_resonance = len(hit_factors) >= 2
            if cross_resonance:
                resonance_symbols.add(symbol)
            projected = {
                "symbol": symbol,
                "code": symbol.split(".", 1)[0],
                "name": str(row.get("name") or ""),
                "open_gap": _safe_num(row.get("open_gap")),
                "change_pct": _safe_num(row.get("change_pct")),
                "concept_board": concept_map.get(symbol.upper(), []),
                "hit_factors": hit_factors,
                "cross_resonance": cross_resonance,
            }
            # 概念筛选: 大小写不敏感子串匹配概念板块; 只收窄 rows (total 不变)
            if needle and not any(needle in c.lower() for c in projected["concept_board"]):
                continue
            projected_rows.append(projected)

        strategies.append(
            {
                "id": sid,
                "name": resolver(sid),
                "total": total,
                "rows": projected_rows,
            }
        )

    return {
        "as_of": str(resolved_as_of),
        "updated_at": cache.get("updated_at"),
        "strategies": strategies,
        "resonance_count": len(resonance_symbols),
    }
