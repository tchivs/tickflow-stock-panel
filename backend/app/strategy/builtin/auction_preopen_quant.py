"""盘前强势量化 — 开盘涨幅 + 量比双阈值, 集合竞价活跃度代理"""
import polars as pl

META = {
    "asset_types": ["stock"],
    "id": "auction_preopen_quant",
    "name": "盘前强势量化",
    "description": "盘前强度量化 — 开盘涨幅 + 量比 (成交量/5日均量) 双阈值, 集合竞价活跃度代理",
    "tags": ["竞价", "量比", "盘前"],
    "params": [
        {"id": "min_open_gap", "label": "最低开盘涨幅%", "type": "float",
         "default": 3.0, "min": 0.0, "max": 10.0, "step": 0.5},
        {"id": "min_vol_ratio", "label": "最低量比", "type": "float",
         "default": 1.5, "min": 0.0, "max": 10.0, "step": 0.5},
    ],
    "scoring": {"open_gap": 0.4, "vol_ratio_5d": 0.6},
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
    min_gap = params.get("min_open_gap", 3.0) / 100.0
    min_vol = params.get("min_vol_ratio", 1.5)
    return (
        pl.col("symbol").is_not_null()
        & (pl.col("open_gap") >= min_gap)
        & (pl.col("vol_ratio_5d") >= min_vol)
    )
