"""竞价全面 — 全因子复合: 开盘涨幅 + 竞价量比 + 竞价金额强度 (pre_open 白名单, 缺列空池)"""
import polars as pl


META = {
    "id": "auction_allround",
    "name": "竞价全面",
    "description": "全因子复合：开盘涨幅 + 竞价量比 + 竞价金额强度；可选换手为盘后参考（EOD 列，默认关）——开启仅在帧已含换手列时收窄，绝不冒充盘前可算",
    "tags": ["竞价", "盘前", "复合"],
    "time_window": "pre_open",
    "requires_auction_data": True,
    "params": [
        {"id": "min_open_gap", "label": "最低开盘涨幅%", "type": "float",
         "default": 2.0, "min": 0.0, "max": 10.0, "step": 0.5},
        {"id": "min_auction_vol_ratio", "label": "最低竞价量比", "type": "float",
         "default": 1.2, "min": 0.0, "max": 10.0, "step": 0.1},
        {"id": "min_auction_amount", "label": "最低竞价金额", "type": "float",
         "default": 1_000_000, "min": 0, "max": 100_000_000, "step": 100_000},
        {"id": "use_turnover", "label": "启用换手参考(盘后EOD)", "type": "bool",
         "default": False},
    ],
    "scoring": {"open_gap": 0.3, "auction_volume_ratio": 0.4, "auction_amount": 0.3},
    "order_by": "score",
    "descending": True,
    "limit": 50,
}

ENTRY_SIGNALS = []
EXIT_SIGNALS = []
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 1
ALERTS = []


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    # pre_open 白名单: 必需竞价列缺席 → 整池为假 → 空池 (fail-closed, 绝不部分/0 填充)
    if "open_gap" not in df.columns or "auction_volume_ratio" not in df.columns or "auction_amount" not in df.columns:
        return pl.lit(False)
    min_gap = params.get("min_open_gap", 2.0) / 100.0
    vol_r = params.get("min_auction_vol_ratio", 1.2)
    amt = params.get("min_auction_amount", 1_000_000)
    expr = (
        (pl.col("open_gap") >= min_gap)
        & (pl.col("auction_volume_ratio") >= vol_r)
        & (pl.col("auction_amount") >= amt)
    )
    # 可选换手: 仅当参数开启且帧已含 EOD 换手列时才收窄 (白名单显式例外, 描述已标注盘后参考)
    if params.get("use_turnover", False) and "turnover_rate" in df.columns:
        expr = expr & (pl.col("turnover_rate") >= 0.03)
    return expr
