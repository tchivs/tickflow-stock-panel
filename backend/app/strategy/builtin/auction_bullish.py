"""竞价多头 — 开盘涨幅 + 日涨幅双动量, 第一性原理阈值筛选"""
import polars as pl

META = {
    "asset_types": ["stock"],
    "id": "auction_bullish",
    "name": "竞价多头",
    "description": "开盘涨幅 (open/prev_close−1) 与日涨幅 (change_pct) 双动量同时达标",
    "tags": ["竞价", "高开", "动量"],
    "params": [
        {"id": "min_open_gap", "label": "最低开盘涨幅%", "type": "float",
         "default": 2.0, "min": 0.0, "max": 10.0, "step": 0.5},
        {"id": "min_change", "label": "最低日涨幅%", "type": "float",
         "default": 2.0, "min": 0.0, "max": 10.0, "step": 0.5},
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
    min_gap = params.get("min_open_gap", 2.0) / 100.0
    min_chg = params.get("min_change", 2.0) / 100.0
    return (
        pl.col("symbol").is_not_null()
        & (pl.col("open_gap") >= min_gap)
        & (pl.col("change_pct") >= min_chg)
    )
