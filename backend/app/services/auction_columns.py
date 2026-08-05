"""竞价列读路径注入 (DATA-04 / DATA-06)。

竞价列是「有才有列」的 probe 门控数据 —— 数值不可从 OHLCV 重算, 存在性是
probe 条件。本模块负责读路径:

  - ``attach_auction_columns``: probe×分区双闸门, 把 kline_auction 湖的真实竞价列
    左联注入日线帧; 任一闸门不通过时原样返回 (列缺席, 诚实缺列而非 500)。
  - ``compute_auction_unmatched_amount``: 委托量输入可得时派生估算未匹配金额
    (DATA-06, Task 3 实现)。

写路径 (auction_sync) 属 20-01, 本模块绝不写湖。
"""
from __future__ import annotations

import logging
from datetime import date

import polars as pl

from app.services.auction_probe import AuctionProbeStatus, resolve_auction_probe
from app.tickflow.repository import KlineRepository

logger = logging.getLogger(__name__)

# 派生未匹配金额 (DATA-06) 输入列: 虚拟未匹配量(股) × 虚拟参考价(元/股) = 未匹配金额(元)
_AUCTION_UNMATCHED_VOLUME_COL = "auction_unmatched_volume"
_AUCTION_VIRTUAL_PRICE_COL = "auction_virtual_price"
_AUCTION_UNMATCHED_AMOUNT_COL = "auction_unmatched_amount"

# kline_auction 湖 canonical 列 (与 20-01 写路径一致); 派生列在输入可得时同帧携带
_AUCTION_REAL_COLS = ("auction_volume", "auction_amount")


def attach_auction_columns(df: pl.DataFrame, trade_date: date, repo: KlineRepository) -> pl.DataFrame:
    """读路径左联注入竞价列 (probe×分区双闸门)。

    第一闸门 (probe): ``resolve_auction_probe().status == available``, 否则原样返回
    (列缺席, 功能 fail-closed 回退到派生 ``open_gap``, 绝不静默填充)。
    第二闸门 (分区): ``kline_auction/date={trade_date}/part.parquet`` 存在且有行,
    否则原样返回 (诚实按日空态, 非 null-as-present)。

    通过后: 先按 symbol 去重为每 symbol 单行 (防多窗口行 fan-out 把日线帧拉成
    N 行/标的), 再对 df 左联注入真实竞价列。df 以 symbol 为键、已限定到
    trade_date; 分区内有行但某 symbol 缺席 → 该 symbol 列值为 null
    (诚实按标的缺席, 非整日 null-as-present)。
    """
    if df is None or df.is_empty():
        return df

    # 第一闸门: probe 必须 available
    if resolve_auction_probe().status != AuctionProbeStatus.available:
        logger.debug("attach_auction_columns: probe non-available, auction columns absent")
        return df

    # 第二闸门: 目标日分区存在且有行
    part = repo.store.data_dir / "kline_auction" / f"date={trade_date.isoformat()}" / "part.parquet"
    if not part.exists():
        logger.debug("attach_auction_columns: no partition for %s, columns absent", trade_date)
        return df

    auction = pl.read_parquet(part)
    if auction.is_empty():
        logger.debug("attach_auction_columns: partition empty for %s, columns absent", trade_date)
        return df

    # 真实竞价列裁剪 (canonical 列; 缺列即不注入, 诚实缺列)
    keep = [c for c in ("symbol", *_AUCTION_REAL_COLS) if c in auction.columns]
    auction = auction.select(keep)

    # 防 fan-out: 每 symbol 只保留一行 (20-01 写路径已按 symbol+datetime 去重,
    # 此处对多窗口行再做 symbol 级防御, 锁死日线帧基数不被拉成 N 行/标的)
    auction = auction.unique(subset=["symbol"], keep="last")

    logger.debug(
        "attach_auction_columns: injecting auction columns for %s (%d symbols)",
        trade_date, auction.height,
    )
    return df.join(auction, on="symbol", how="left")
