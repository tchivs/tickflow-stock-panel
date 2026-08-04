"""早盘之星 — 开盘涨幅或日涨幅任一达标, 概念板块佐证可选 (enriched 暂无概念列时默认关闭)"""
import polars as pl

META = {
    "id": "auction_early_star",
    "name": "早盘之星",
    "description": "早盘之星 — 开盘涨幅或日涨幅任一达标, 概念板块佐证可选 (enriched 暂无概念列时默认关闭)",
    "tags": ["竞价", "早盘", "概念"],
    "params": [
        {"id": "min_open_gap", "label": "最低开盘涨幅%", "type": "float",
         "default": 1.5, "min": 0.0, "max": 10.0, "step": 0.5},
        {"id": "min_change", "label": "最低日涨幅%", "type": "float",
         "default": 3.0, "min": 0.0, "max": 10.0, "step": 0.5},
        {"id": "use_concept_corroboration", "label": "启用概念板块佐证", "type": "bool",
         "default": False},
    ],
    "scoring": {"open_gap": 0.5, "change_pct": 0.5},
    "order_by": "score",
    "descending": True,
    "limit": 50,
}

ENTRY_SIGNALS = []
EXIT_SIGNALS = []
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 10
ALERTS = []


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    min_gap = params.get("min_open_gap", 1.5) / 100.0
    min_chg = params.get("min_change", 3.0) / 100.0
    expr = (
        pl.col("symbol").is_not_null()
        & ((pl.col("open_gap") >= min_gap) | (pl.col("change_pct") >= min_chg))
    )
    # 概念板块佐证: 仅当参数开启且受管 enriched 实际含 concept_board 列时才收窄。
    # enriched 暂未提供该列 → 保持基础 OR 组合, 不崩溃、不收窄。
    if params.get("use_concept_corroboration", False) and "concept_board" in df.columns:
        expr = expr & pl.col("concept_board").is_not_null()
    return expr
