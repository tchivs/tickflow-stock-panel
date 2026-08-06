"""盘前规则评估适配 (MON-02/05) — 只读内存 payload, 零执行。

铁律 (镜像 premarket_pool.py:1-18):
- 绝不 import 执行族模块 (broker/order/trade/execution/portfolio/position/account/
  transaction) 与 ``strategy_cache``。
- 绝不调 ``strategy_cache.write_cache`` / ``pool_snapshot.persist_point_snapshot`` /
  写 ``screener_results``。
- 绝不写任何文件; 不触碰 ``_strategy_pools`` / ``_latest_strategy_results``。
- 绝不伪造缺失列: 白名单外列丢弃, change_pct 恒 None (盘前帧 EOD 语义无意义, R1)。

本模块只 import stdlib + polars + ``monitor_rules.PREOPEN_ALLOWED_FIELDS`` —
零执行面, 供 30-02 整文件 AST 守卫扫描 (OQ-5/D-06)。零新增运行时依赖。
"""
from __future__ import annotations

import polars as pl

from app.strategy.monitor_rules import PREOPEN_ALLOWED_FIELDS

# 展示列 + 白名单列: 帧重建只保留这些列 (行内残留 close/code/change_pct 被剥离)。
_KEEP_COLUMNS = ("symbol", "name", "hit_factors", *sorted(PREOPEN_ALLOWED_FIELDS))


def build_preopen_frame(payload: dict) -> tuple[pl.DataFrame, dict[str, set[str]]] | None:
    """从盘前预览 payload 重建评估帧 (纯只读, symbol 级去重)。

    - 非 dict payload / ``available is False`` / 无 ``results`` / 无有效行 → None
      (诚实空态, 镜像 premarket_pool available:false 语义);
    - 只保留 _KEEP_COLUMNS 中存在的列, change_pct 强制 None (覆盖行内残留 EOD
      涨跌幅, R1 双保险); close/code 绝不进评估帧 (MON-01 白名单外);
    - source_strategies = 命中该 symbol 的策略 id 排序列表;
    - symbol 级去重 keep=first (多策略命中取首个行, hit_factors 本身跨策略聚合,
      镜像 auction_columns.py unique(keep=first) 语义)。

    Args:
        payload: v2.1 盘前预览 payload (``{available, results: {sid: {rows: [...]}}}``)。

    Returns:
        ``(frame, source_map)`` 或 None; source_map: symbol → {strategy_id, ...}。
    """
    if not isinstance(payload, dict) or payload.get("available") is False:
        return None
    results = payload.get("results")
    if not isinstance(results, dict) or not results:
        return None

    rows: list[dict] = []
    source_map: dict[str, set[str]] = {}
    for sid, result in results.items():
        for row in result.get("rows", []) if isinstance(result, dict) else []:
            # 行不可信 (job 尾段内存 payload): 非 dict / 无 symbol 静默跳过
            if not isinstance(row, dict) or not row.get("symbol"):
                continue
            sym = str(row["symbol"])
            rows.append(row)
            source_map.setdefault(sym, set()).add(str(sid))
    if not rows:
        return None

    normalized: list[dict] = []
    for row in rows:
        sym = str(row["symbol"])
        r = {k: row[k] for k in _KEEP_COLUMNS if k in row}
        r["change_pct"] = None  # 显式「此处无意义」(R1): 覆盖行内残留 EOD 涨跌幅
        r["source_strategies"] = sorted(source_map[sym])
        normalized.append(r)

    frame = pl.DataFrame(normalized).unique(subset=["symbol"], keep="first")
    return frame, source_map


def extract_preopen_metrics(frame: pl.DataFrame, symbol: str) -> dict:
    """提取命中 symbol 的白名单数值 (仅非 None; 缺列/缺值 → 缺键, 诚实)。

    供 evaluate_premarket 事件标注 ``preopen_metrics`` 使用 — 结构化数值给
    UI/飞书模板渲染, 不塞进 message 字符串 (保持 message 稳定可断言)。
    """
    if frame.is_empty() or "symbol" not in frame.columns:
        return {}
    hit = frame.filter(pl.col("symbol").cast(pl.String) == symbol)
    if hit.is_empty():
        return {}
    row = hit.row(0, named=True)
    out: dict = {}
    for field in _KEEP_COLUMNS[3:]:  # 白名单列 (跳过 symbol/name/hit_factors 展示列)
        value = row.get(field)
        if value is not None:
            out[field] = value
    return out
