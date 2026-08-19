"""金色两点半 (STRAT-06) — 尾盘 14:30 后选股、次日持有; 非竞价窗口。

诚实归类: 尾盘/隔夜 (post_close), id 命名不暗示竞价窗口 (label-drift 防线)。
- T 日涨幅 3%–5% + 收阳 (日线核心池, EOD 列 — post_close 窗口允许)
- 尾盘分钟确认 (14:30–15:00 窗口内 last close >= first open, "尾盘不弱") 为可选增强:
  分钟数据缺席 → 跳过确认保留日线核心池 (minute_confirm_required=False)。

import 偏差 (研究授权): 本文件除 polars 外额外 import datetime 构造分钟帧时间边界
(datetime.combine + trading_minutes_elapsed_from_dt 供 21-02 复用), 零新增运行时依赖。
"""
import polars as pl
from datetime import time as dt_time
from datetime import datetime  # noqa: F401 — 研究授权: 21-02 复用 datetime.combine

META = {
    "asset_types": ["stock"],
    "id": "golden_230",
    "name": "金色两点半",
    "time_window": "post_close",
    "evaluation_time": "15:00",
    "minute_confirm_required": False,
    "description": "尾盘 14:30 后选股、隔夜/次日持有，非竞价窗口；T 日涨幅 3%–5% + 收阳，尾盘分钟确认为可选增强",
    "tags": ["尾盘", "隔夜", "持有"],
    "params": [
        {"id": "use_change_band", "label": "启用涨幅带 3%–5%", "type": "bool",
         "default": True},
        {"id": "require_bullish_candle", "label": "要求收阳", "type": "bool",
         "default": True},
    ],
    "scoring": {"change_pct": 0.5, "amplitude": 0.2, "amount": 0.3},
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
    expr = pl.col("symbol").is_not_null() | pl.col("symbol").is_null()
    if params.get("use_change_band", True):
        expr = expr & (pl.col("change_pct") >= 0.03) & (pl.col("change_pct") <= 0.05)
    if params.get("require_bullish_candle", True):
        expr = expr & (pl.col("close") > pl.col("open"))  # 收阳
    return expr


def minute_confirm(df_minute: pl.DataFrame, params: dict) -> pl.DataFrame:
    """可选增强: 尾盘 14:30–15:00 窗口内 last close >= first open ("尾盘不弱")。

    引擎已单点截断到 15:00; 本函数只收窄到尾盘窗并返回确认帧。无尾盘 bar →
    原样返回 (不收窄, 保留日线核心池)。
    """
    if df_minute is None or df_minute.is_empty():
        return df_minute
    tail = df_minute.filter(pl.col("datetime").dt.time() >= dt_time(14, 30))
    if tail.is_empty():
        return df_minute
    passed = (
        tail.sort(["symbol", "datetime"])
        .group_by("symbol")
        .agg(
            pl.col("close").last().alias("_last_close"),
            pl.col("open").first().alias("_first_open"),
        )
        .filter(pl.col("_last_close") >= pl.col("_first_open"))
    )
    return tail.join(passed, on="symbol", how="inner")
