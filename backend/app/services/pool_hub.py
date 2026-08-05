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

共享投影核心 (POOL-05):
- ``_project_hub`` 纯函数同时服务 ``build_pool_hub`` (运行时缓存最新视图) 与
  ``build_pool_hub_snapshot`` (冻结式点快照历史视图), 历史/最新双路径语义
  bit-identical。
- ``total`` 权威 = ``result.get("total", len(rows))`` (display_limit 截断后
  len(rows) ≤ total, Divergence 1)。
- 概念归属只实时 join 当前 ext (历史 ext 分区不存在), 响应显式标注
  ``concept_attribution: "current_snapshot"``, 不冻结今日标签到历史日 (Divergence 2)。
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

from app.services import pool_snapshot, strategy_cache
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


def _project_hub(
    results: dict,
    resolved_as_of: str | None,
    updated_at: Any,
    concept: str | None,
    name_for: Callable[[str], str] | None,
    data_dir: Path,
) -> dict:
    """共享投影核心: results 行集 → Hub 形状 (六列 + 交叉共振 + 概念筛选)。

    - ``total`` 权威 = ``result.get("total", len(rows))`` (display_limit 截断后
      len(rows) ≤ total, 快照/缓存均显式存 total)。
    - 概念筛选 (needle 大小写不敏感子串) 只收窄 rows, ``total`` 不变 (D-04)。
    - 返回 dict 带 ``concept_attribution: "current_snapshot"`` (实时 join 当前 ext,
      不冻结历史标签, T-22-06)。
    """
    concept_map = _build_concept_map(data_dir)
    resolver = name_for if name_for is not None else (lambda sid: sid)

    needle = concept.strip().lower() if concept else ""

    strategies: list[dict[str, Any]] = []
    resonance_symbols: set[str] = set()

    for sid, result in results.items():
        rows = result.get("rows", []) if isinstance(result, dict) else []
        if not isinstance(rows, list):
            rows = []
        total = result.get("total", len(rows)) if isinstance(result, dict) else len(rows)
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
        "updated_at": updated_at,
        "strategies": strategies,
        "resonance_count": len(resonance_symbols),
        "concept_attribution": "current_snapshot",
    }


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

    return _project_hub(
        cache.get("results", {}),
        resolved_as_of,
        cache.get("updated_at"),
        concept,
        name_for,
        data_dir,
    )


def build_pool_hub_snapshot(
    data_dir: Path,
    as_of: str,
    concept: str | None = None,
    name_for: Callable[[str], str] | None = None,
) -> dict:
    """从冻结式点快照构建 Hub 形状投影 (历史 as_of 只读视图, POOL-05)。

    - 快照缺失 → 诚实空态 ``available: False`` (200 语义, 非 404)。
    - 快照存在 → 与 ``build_pool_hub`` 同形状投影 (``total`` 权威), ``updated_at``
      取快照 ``computed_at`` (诚实区分计算时刻)。

    Args:
        data_dir: 数据根目录 (含 screener_results/ 快照湖)。
        as_of: 期望历史交易日 (``YYYY-MM-DD``)。
        concept: 概念筛选 (大小写不敏感子串); None/空串 = 不过滤。
        name_for: ``(sid) -> 策略显示名``; None 时退化为 sid。
    """
    snap = pool_snapshot.load_point_snapshot(data_dir, as_of)
    if snap is None:
        return {
            "as_of": None,
            "available": False,
            "strategies": [],
            "resonance_count": 0,
            "updated_at": None,
            "concept_attribution": "current_snapshot",
        }
    return _project_hub(
        snap["results"],
        snap["as_of"],
        snap["computed_at"],
        concept,
        name_for,
        data_dir,
    )
