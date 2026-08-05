"""盘中确认 — 09:30–10:00 分钟帧截断到 evaluation_time=09:45 复评 (引擎单点截断, 绝不 lookahead)"""
import polars as pl
from datetime import datetime, time as dt_time

from app.market_time import trading_minutes_elapsed_from_dt


META = {
    "id": "auction_intraday_confirm",
    "name": "盘中确认",
    "description": "日线初筛（开盘涨幅 >= 2%）后，消费引擎截断到 evaluation_time=09:45 的 09:30–10:00 分钟帧复评：盘中累计量 × time_factor 折算全天量级 + 不破开盘价；分钟数据缺席 → 空池，绝不 lookahead",
    "tags": ["竞价", "盘中", "分钟确认"],
    "time_window": "intraday",
    "evaluation_time": "09:45",
    "requires_auction_data": True,
    "minute_confirm_required": True,
    "params": [
        {"id": "min_open_gap", "label": "最低开盘涨幅%", "type": "float",
         "default": 2.0, "min": 0.0, "max": 10.0, "step": 0.5},
        {"id": "min_volume_scale", "label": "折算全天最低量级", "type": "float",
         "default": 10_000_000, "min": 0, "max": 100_000_000, "step": 100_000},
        {"id": "require_above_open", "label": "要求不破开盘价", "type": "bool",
         "default": True},
    ],
    "scoring": {"open_gap": 1.0},
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
    """日线初筛 — 只允许 pre_open 可算列 (open_gap); EOD 列一票否决 (T-21-01/PITFALLS #7)."""
    if "open_gap" not in df.columns:
        return pl.lit(False)
    min_gap = params.get("min_open_gap", 2.0) / 100.0
    return pl.col("open_gap") >= min_gap


def minute_confirm(df_minute: pl.DataFrame, params: dict) -> pl.DataFrame:
    """引擎已单点截断 datetime.time() <= evaluation_time=09:45; 只消费帧内统计.

    time_factor = 240 / trading_minutes_elapsed_from_dt(evaluation_time) (market_time 折算),
    eval=09:45 → elapsed=15 → time_factor=16.0. 确认条件: 盘中累计量 × time_factor >= 阈值
    且 (require_above_open 时) 截至 eval 的收盘不低于开盘 (量价齐升/不破开盘价)。
    """
    if df_minute.is_empty():
        return df_minute
    eval_date = df_minute["datetime"].min().date()
    elapsed = trading_minutes_elapsed_from_dt(datetime.combine(eval_date, dt_time(9, 45)))
    time_factor = 240.0 / elapsed if elapsed > 0 else 1.0
    min_volume_scale = float(params.get("min_volume_scale", 10_000_000))
    require_above_open = bool(params.get("require_above_open", True))

    frame = (
        df_minute.sort(["symbol", "datetime"])
        .group_by("symbol")
        .agg(
            pl.col("volume").sum().alias("cum_volume"),
            pl.col("close").sort_by("datetime").last().alias("last_close"),
            pl.col("open").sort_by("datetime").first().alias("first_open"),
        )
        .with_columns((pl.col("cum_volume") * time_factor).alias("volume_scale"))
        .filter(pl.col("volume_scale") >= min_volume_scale)
    )
    if require_above_open:
        frame = frame.filter(pl.col("last_close") >= pl.col("first_open"))
    return frame
