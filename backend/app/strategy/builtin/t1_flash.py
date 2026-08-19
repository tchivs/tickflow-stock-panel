"""T+1闪电 — 竞价买入信号 (开盘涨幅 + 竞价量比 + 竞价金额强度); 次日早盘分钟K卖出为 EXIT 语义, 池只含 T 日信号"""
import polars as pl


META = {
    "asset_types": ["stock"],
    "id": "t1_flash",
    "name": "T+1闪电",
    "description": "竞价买入信号（开盘涨幅 + 竞价量比 + 竞价金额强度），次日早盘分钟 K 卖出为 EXIT 语义，池只含 T 日信号、无 lookahead",
    "tags": ["竞价", "T+1", "短线"],
    "time_window": "pre_open",
    "requires_auction_data": True,
    "params": [
        {"id": "min_open_gap", "label": "最低开盘涨幅%", "type": "float",
         "default": 2.5, "min": 0.0, "max": 10.0, "step": 0.5},
        {"id": "min_auction_vol_ratio", "label": "最低竞价量比", "type": "float",
         "default": 2.0, "min": 0.0, "max": 10.0, "step": 0.1},
        {"id": "min_auction_amount", "label": "最低竞价金额", "type": "float",
         "default": 2_000_000, "min": 0, "max": 100_000_000, "step": 100_000},
    ],
    "scoring": {"open_gap": 0.3, "auction_volume_ratio": 0.4, "auction_amount": 0.3},
    "order_by": "score",
    "descending": True,
    "limit": 50,
}

ENTRY_SIGNALS = []
# T+1 次日早盘卖出确认 → EXIT 语义, 绝不参与池成员计算 (T-21-08)
EXIT_SIGNALS = ["signal_ma20_breakdown"]
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 1
ALERTS = []


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    # 池只由 T 日 as-of 帧计算 (pre_open 白名单, 禁 EOD 列); 缺竞价列 → 空池
    if "open_gap" not in df.columns or "auction_volume_ratio" not in df.columns or "auction_amount" not in df.columns:
        return pl.lit(False)
    min_gap = params.get("min_open_gap", 2.5) / 100.0
    vol_r = params.get("min_auction_vol_ratio", 2.0)
    amt = params.get("min_auction_amount", 2_000_000)
    return (
        (pl.col("open_gap") >= min_gap)
        & (pl.col("auction_volume_ratio") >= vol_r)
        & (pl.col("auction_amount") >= amt)
    )
