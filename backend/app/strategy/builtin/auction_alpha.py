"""竞价阿尔法 (STRAT-05) — 竞价量/额强度综合; probe available 消费真实竞价列, 否则派生回退。

第一性原理因子 (非专有配方):
- 真列分支: auction_volume_ratio / open_gap / auction_amount (probe available, 真实竞价列)
- 派生分支: open_gap / vol_ratio_5d / amount (REQUIREMENTS 授权派生回退; 永不与真列混用)

两分支按列存在性互斥 (镜像 auction_early_star), 同帧绝不混用。scoring 声明超集
权重和=1.0, 引擎对缺失列静默跳过 + 权重归一化兜底。

pre_open 窗口: 禁 EOD 列 change_pct/close (lookahead)。
"""
import polars as pl

META = {
    "asset_types": ["stock"],
    "id": "auction_alpha",
    "name": "竞价阿尔法",
    "time_window": "pre_open",
    "requires_auction_data": False,
    "description": "probe available 消费真实竞价列 (竞价量比 + 竞价金额), 否则 fail-closed 回退派生因子 (open_gap + 量比/金额强度); 真实/派生分支永不混用",
    "tags": ["竞价", "阿尔法", "盘前"],
    "params": [
        {"id": "min_auction_vol_ratio", "label": "真列分支最低竞价量比", "type": "float",
         "default": 1.0, "min": 0.0, "max": 10.0, "step": 0.1},
        {"id": "min_real_gap_pct", "label": "真列分支最低开盘涨幅%", "type": "float",
         "default": 1.5, "min": 0.0, "max": 10.0, "step": 0.1},
        {"id": "min_derived_gap_pct", "label": "派生分支最低开盘涨幅%", "type": "float",
         "default": 2.0, "min": 0.0, "max": 10.0, "step": 0.1},
        {"id": "min_vol_ratio_5d", "label": "派生分支最低量比", "type": "float",
         "default": 1.2, "min": 0.0, "max": 10.0, "step": 0.1},
        {"id": "min_amount", "label": "派生分支最低成交额(元)", "type": "float",
         "default": 1_000_000, "min": 0.0, "max": 100_000_000, "step": 100_000},
    ],
    "scoring": {
        "open_gap": 0.25,
        "auction_volume_ratio": 0.25,
        "auction_amount": 0.25,
        "vol_ratio_5d": 0.15,
        "amount": 0.10,
    },
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
    # 真列分支: probe available → 消费真实竞价列
    if "auction_volume_ratio" in df.columns and "auction_amount" in df.columns:
        min_vol_r = params.get("min_auction_vol_ratio", 1.0)
        min_gap = params.get("min_real_gap_pct", 1.5) / 100.0
        return (
            (pl.col("auction_volume_ratio") >= min_vol_r)
            & (pl.col("open_gap") >= min_gap)
            & (pl.col("auction_amount") >= 1_000_000)
        )
    # 派生分支: 竞价列缺席 → fail-closed 回退 open_gap + 量比/金额强度 (永不与真列混用)
    min_gap = params.get("min_derived_gap_pct", 2.0) / 100.0
    min_vol = params.get("min_vol_ratio_5d", 1.2)
    min_amt = params.get("min_amount", 1_000_000)
    return (
        (pl.col("open_gap") >= min_gap)
        & (pl.col("vol_ratio_5d") >= min_vol)
        & (pl.col("amount") >= min_amt)
    )
