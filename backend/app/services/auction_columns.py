"""竞价列读路径注入 (DATA-04 / DATA-06)。

竞价列是「有才有列」的 probe 门控数据 —— 数值不可从 OHLCV 重算, 存在性是
probe 条件。本模块负责读路径:

  - ``attach_auction_columns``: probe×分区双闸门, 把 kline_auction 湖的真实竞价列
    左联注入日线帧; 任一闸门不通过时原样返回 (列缺席, 诚实缺列而非 500)。
  - ``attach_auction_columns_range``: 区间向量化只读注入原语 (BT-02, 历史闸门 =
    分区存在性, probe 不参与); 一次装载整个 enriched 区间, 逐日注入, 产出
    enabled_dates。回测装载 seam 物理无竞价列 (RESEARCH §1.1), 本原语供只读
    研究报告按日注入, 不触碰 backtest seam (D-08)。
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
_AUCTION_VOLUME_RATIO_COL = "auction_volume_ratio"


def compute_auction_unmatched_amount(df: pl.DataFrame) -> pl.DataFrame:
    """派生竞价未匹配金额 (DATA-06) —— 委托量输入可得时才派生。

    语义 = 虚拟未匹配量(股) × 虚拟参考价(元/股) = 未匹配金额(元) (RESEARCH A1)。
    派生估算列, 非真实成交; 只与真实竞价列分列共存, 永不求和/混排。
    缺少任一输入列 (``auction_unmatched_volume`` / ``auction_virtual_price``) → 原样返回
    (列缺席 → 策略引擎对缺失派生列静默跳过, 回退量比+金额强度)。
    """
    if df is None or df.is_empty():
        return df
    if _AUCTION_UNMATCHED_VOLUME_COL not in df.columns or _AUCTION_VIRTUAL_PRICE_COL not in df.columns:
        return df
    return df.with_columns(
        (pl.col(_AUCTION_UNMATCHED_VOLUME_COL) * pl.col(_AUCTION_VIRTUAL_PRICE_COL)).alias(
            _AUCTION_UNMATCHED_AMOUNT_COL
        )
    )


def _attach_auction_volume_ratio(
    auction: pl.DataFrame,
    trade_date: date,
    repo: KlineRepository,
) -> pl.DataFrame:
    """派生受管列 ``auction_volume_ratio`` = 竞价量 ÷ 前 5 日均量 (不含当日, PIT-safe)。

    分母取 ``repo.get_enriched_history(trade_date, 6)`` 过滤 ``date < trade_date`` 后按
    symbol ``tail(5)`` 的 ``volume`` 均值 —— 只用前日数据, 绝不混入当日 EOD 量
    (内联 ``volume/vol_ratio_5d`` 会引入当日量 → pre_open lookahead, 禁止)。

    无历史缓存或 prior 为空 → 跳过派生, 列缺席 (诚实缺列, 绝不 0 填充)。
    """
    if "auction_volume" not in auction.columns:
        return auction
    hist = repo.get_enriched_history(trade_date, 6)
    if hist is None or hist.is_empty():
        return auction
    prior = hist.filter(pl.col("date") < trade_date).sort(["symbol", "date"])
    if prior.is_empty():
        return auction
    avg = prior.group_by("symbol").agg(
        pl.col("volume").tail(5).mean().alias("_prior_5d_avg_volume")
    )
    return (
        auction.join(avg, on="symbol", how="left")
        .with_columns(
            (pl.col("auction_volume") / pl.col("_prior_5d_avg_volume")).alias(
                _AUCTION_VOLUME_RATIO_COL
            )
        )
        .drop("_prior_5d_avg_volume")
    )


def attach_auction_columns(df: pl.DataFrame, trade_date: date, repo: KlineRepository) -> pl.DataFrame:
    """读路径左联注入竞价列 (probe×分区双闸门)。

    第一闸门 (probe): ``resolve_auction_probe().status == available``, 否则原样返回
    (列缺席, 功能 fail-closed 回退到派生 ``open_gap``, 绝不静默填充)。
    第二闸门 (分区): ``kline_auction/date={trade_date}/part.parquet`` 存在且有行,
    否则原样返回 (诚实按日空态, 非 null-as-present)。

    通过后: 先按 symbol 去重为每 symbol 单行 (防多窗口行 fan-out 把日线帧拉成
    N 行/标的), 再对 df 左联注入真实竞价列 (以及委托量输入可得时派生的
    ``auction_unmatched_amount``)。df 以 symbol 为键、已限定到
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

    # 委托量输入可得时派生估算未匹配金额 (与真实竞价列同帧携带, 独立命名, 永不相加)
    if _AUCTION_UNMATCHED_VOLUME_COL in auction.columns and _AUCTION_VIRTUAL_PRICE_COL in auction.columns:
        auction = compute_auction_unmatched_amount(auction)

    # 派生受管列 auction_volume_ratio = 竞价量 ÷ 前5日均量(不含当日) (Phase 21, PIT-safe);
    # 无历史/prior 为空 → 列缺席 (诚实缺列, 绝不 0 填充)。
    auction = _attach_auction_volume_ratio(auction, trade_date, repo)

    # 真实竞价列裁剪 (canonical 列; 缺列即不注入, 诚实缺列)
    keep = [
        c
        for c in (
            "symbol",
            *_AUCTION_REAL_COLS,
            _AUCTION_UNMATCHED_AMOUNT_COL,
            _AUCTION_VOLUME_RATIO_COL,
        )
        if c in auction.columns
    ]
    auction = auction.select(keep)

    # 防 fan-out: 每 symbol 只保留一行 (20-01 写路径已按 symbol+datetime 去重,
    # 此处对多窗口行再做 symbol 级防御, 锁死日线帧基数不被拉成 N 行/标的)
    auction = auction.unique(subset=["symbol"], keep="last")

    logger.debug(
        "attach_auction_columns: injecting auction columns for %s (%d symbols)",
        trade_date, auction.height,
    )
    return df.join(auction, on="symbol", how="left")


def _dir_date(part_dir) -> date | None:
    """从 ``date=YYYY-MM-DD`` 分区目录名解析日期; 解析失败返回 None (跳过该分区)。

    逐字复制自 ``app/api/auction_history.py:_dir_date`` (auction_history.py:59-66) ——
    两处读路径共用同一严格解析 (T-29-01-01: 目录名只经 ``date.fromisoformat`` 解析,
    解析失败即跳过, 永不进入路径拼接或返回数据)。
    """
    name = part_dir.parent.name
    if not name.startswith("date="):
        return None
    try:
        return date.fromisoformat(name[len("date="):])
    except ValueError:
        return None


def attach_auction_columns_range(
    df: pl.DataFrame,
    start: date,
    end: date,
    repo: KlineRepository,
) -> tuple[pl.DataFrame, list[date]]:
    """区间竞价列注入 (只读研究原语, BT-02)。

    历史闸门 = **分区存在性主闸门** (D-03 / REV-01) —— 与单日版
    ``attach_auction_columns`` 的 probe×分区双闸门是**有意差异**: probe 是 live-source
    探测 (auction_probe.py), 对历史分区存在性无信息量; 历史 as_of 分区存在即真值。
    本函数**不接收 probe**, probe 由端点透传报告, 不参与闸门。

    平台铁律 (镜像单日版 :95-96 注释): 分区不存在 → 诚实按日空态 (列缺席), 绝不做
    null-as-present 伪造竞价列。无分区日不在 ``enabled_dates``; 空分区/坏目录名/
    读盘失败的分区跳过 (fail-closed); 空湖 → ``(df, [])``。

    warmup 契约: 面板须含 ``start`` 前最多 5 个交易日的行 (供首个 enabled 日分母);
    注入后裁剪 ``date >= start``, warmup 行只参与分母, 不出现在结果。调用方未提供
    warmup 行 → 前导日 ``auction_volume_ratio`` 为 null (诚实降级, 不报错)。

    返回 ``(注入后的面板, enabled_dates)`` —— enabled_dates = [start, end] 内非空
    分区日, 排序去重。注入按 (symbol, date) 左联; 分区有行但某 symbol 缺席 → 该行
    竞价列为 null (诚实按标的缺席, 非整日 null-as-present)。
    """
    if df is None or df.is_empty():
        return df, []

    # 防御性排序: get_enriched_range 已排序, 但本函数须自洽 (向量化分母依赖组内日期序)
    df = df.sort(["symbol", "date"])

    # 分区发现 (历史闸门 = 分区存在性; 纯读, 零写): 坏目录名解析失败跳过 (T-29-01-01),
    # 读盘异常跳过 (T-29-01-05 fail-closed), 空分区跳过 (镜像单日版 :119-121)
    base = repo.store.data_dir / "kline_auction"
    frames: list[pl.DataFrame] = []
    enabled_dates: list[date] = []
    for part in sorted(base.glob("date=*/part.parquet")):
        d = _dir_date(part)
        if d is None or not (start <= d <= end):
            continue
        try:
            f = pl.read_parquet(part)
        except Exception:  # noqa: BLE001
            logger.debug("attach_auction_columns_range: skip unreadable partition %s", part)
            continue
        if f.is_empty():
            logger.debug("attach_auction_columns_range: skip empty partition %s", part)
            continue
        if "symbol" not in f.columns:
            logger.debug("attach_auction_columns_range: skip partition missing symbol %s", part)
            continue
        # date 列取自分区目录名 (分区帧本身无 date 列; 4 列旧 / 6 列新 schema 均无)
        f = f.with_columns(pl.lit(d).alias("date"))
        # 防 fan-out: 每分区 symbol 级去重 (多窗口行 → keep="last" = 09:25 最终撮合,
        # 镜像单日版 :146, T-29-01-04)
        f = f.unique(subset=["symbol"], keep="last")
        frames.append(f)
        enabled_dates.append(d)

    if not frames:
        logger.debug("attach_auction_columns_range: no non-empty partitions in [%s, %s]", start, end)
        return df, []

    # 新旧分区 schema 漂移容忍 (4 列旧 / 6 列新) → diagonal_relaxed 并集 (镜像 auction_history)
    auction = pl.concat(frames, how="diagonal_relaxed")

    # 委托量输入可得时派生估算未匹配金额 (镜像单日版 :114-117)
    if _AUCTION_UNMATCHED_VOLUME_COL in auction.columns and _AUCTION_VIRTUAL_PRICE_COL in auction.columns:
        auction = compute_auction_unmatched_amount(auction)

    # keep-list 裁剪 (镜像单日版 :122-128): 只注入存在的列, 诚实缺列
    keep = [
        c
        for c in (
            "symbol",
            "date",
            *_AUCTION_REAL_COLS,
            _AUCTION_UNMATCHED_AMOUNT_COL,
            _AUCTION_VOLUME_RATIO_COL,
        )
        if c in auction.columns
    ]
    auction = auction.select(keep)

    # 左联 (行基数保持 df): 分区有行但某 symbol 缺席 → 该行 null (诚实按标的缺席)
    df = df.join(auction, on=["symbol", "date"], how="left")

    # PIT-safe 向量化分母 (与单日版 _attach_auction_volume_ratio 逐值一致, RESEARCH §2.1.3):
    # 分母 = T 前最近 5 个交易日 volume 均值 (不含当日, 绝不混入当日 EOD 量 → pre_open 无 lookahead);
    # shift(1) 把 volume_{T-1} 移到行 T; rolling_mean(5, min_samples=1) 镜像 tail(5).mean()
    # 的短历史行为 (≤4 个前导交易日 → 可用行均值, 不置 null); 组内首行 shift(1) 为 null →
    # ratio null (诚实, 等价于单日版 prior 空 → 列缺席的语义)。df 已按 symbol,date 排序。
    if "auction_volume" in df.columns and "volume" in df.columns:
        df = df.with_columns(
            (
                pl.col("auction_volume")
                / pl.col("volume").shift(1).rolling_mean(5, min_samples=1).over("symbol")
            ).alias(_AUCTION_VOLUME_RATIO_COL)
        )

    # warmup 裁剪: 前导行仅供分母, 不出现在结果
    df = df.filter(pl.col("date") >= start)

    return df, sorted(enabled_dates)
