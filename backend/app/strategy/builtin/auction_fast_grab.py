"""极速抢筹 (STRAT-04) — 集合竞价量比 + 竞价金额强度 + 盘前涨幅甜点区。

第一性原理因子 (非专有配方):
- auction_volume_ratio = 竞价量/前5日均量 (受管列, PIT-safe)
- auction_amount = 竞价金额强度
- open_gap 甜点区 2.8%–3.5%, >7% 风险带剔除

pre_open 窗口: 只引用开盘前可算列 (open_gap/auction_volume_ratio/auction_amount),
禁 EOD 列 (change_pct/vol_ratio_5d/amount/close)。缺竞价列 → 空池 (fail-closed)。
"""
import polars as pl

META = {
    "id": "auction_fast_grab",
    "name": "极速抢筹",
    "time_window": "pre_open",
    "requires_auction_data": True,
    "description": "集合竞价量比(竞价量/前5日均量) + 竞价金额强度 + 盘前涨幅甜点区 2.8%–3.5%、>7% 风险带剔除。需要 probe available 的真实竞价列，缺列即空池",
    "tags": ["竞价", "抢筹", "盘前"],
    "params": [
        {"id": "min_auction_vol_ratio", "label": "最低竞价量比", "type": "float",
         "default": 1.5, "min": 0.5, "max": 5.0, "step": 0.1},
        {"id": "min_auction_amount", "label": "最低竞价金额(元)", "type": "float",
         "default": 2_000_000, "min": 0.0, "max": 100_000_000, "step": 100_000},
        {"id": "sweet_low_pct", "label": "甜点区下限%", "type": "float",
         "default": 2.8, "min": 0.0, "max": 10.0, "step": 0.1},
        {"id": "sweet_high_pct", "label": "甜点区上限%", "type": "float",
         "default": 3.5, "min": 0.0, "max": 10.0, "step": 0.1},
        {"id": "risk_band_gt_pct", "label": "风险带剔除>%", "type": "float",
         "default": 7.0, "min": 0.0, "max": 20.0, "step": 0.5},
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
    # 必需列缺席 → 整池为假 → 空池 (fail-closed, 绝不部分/0 填充; 引擎短路是双保险之一)
    if "auction_volume_ratio" not in df.columns or "auction_amount" not in df.columns:
        return pl.lit(False)
    vol_r = params.get("min_auction_vol_ratio", 1.5)
    amt = params.get("min_auction_amount", 2_000_000)
    sweet_low = params.get("sweet_low_pct", 2.8) / 100.0
    sweet_high = params.get("sweet_high_pct", 3.5) / 100.0
    risk_gt = params.get("risk_band_gt_pct", 7.0) / 100.0
    return (
        (pl.col("open_gap") >= sweet_low)
        & (pl.col("open_gap") <= sweet_high)
        & (pl.col("open_gap") < risk_gt)
        & (pl.col("auction_volume_ratio") >= vol_r)
        & (pl.col("auction_amount") >= amt)
    )
