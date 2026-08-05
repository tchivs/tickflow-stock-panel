"""竞价数据湖摄入服务 (DATA-05)。

把真实 09:15–09:25 集合竞价撮合行按日分区原子写入独立湖
``data/kline_auction/date={d}/part.parquet``。写湖唯一准入闸门是
``resolve_auction_probe().status == available`` —— probe 非 available 时
返回 0 行、不写湖 (fail-closed)。09:30 起的连续竞价 bar 在写湖过滤器处与
provider 归一化同一 555..565 谓词双重排除 (09:30 bar 在湖物理上无存放位置)。

读路径 (kline_auction 视图 left-join 注入竞价列) 属 20-02, 本模块不建。
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

import polars as pl

from app.services.auction_probe import (
    AuctionProbeStatus,
    resolve_auction_probe,
)
from app.tickflow.capabilities import CapabilitySet
from app.tickflow.repository import KlineRepository

logger = logging.getLogger(__name__)

# 集合竞价窗口分钟边界 —— 与 auction_probe.py:23-24 逐字一致 (单一事实源)
_WINDOW_START_MIN = 9 * 60 + 15
_WINDOW_END_MIN = 9 * 60 + 25

# canonical 列 —— 与 custom/provider.py _normalize_auction 的裁剪集一致
CANONICAL_AUCTION_COLS = [
    "symbol", "datetime", "auction_volume", "auction_amount",
]


def _atomic_write_parquet(df: pl.DataFrame, out) -> None:
    """先写临时文件再原子替换, 避免进程中断留下损坏的 parquet。

    与 kline_sync._atomic_write_parquet / repository._atomic_write_parquet 同语义:
    临时文件后缀 .tmp 不匹配 *.parquet glob, 不会被扫描误读; 同目录 rename
    在 POSIX/NTFS 上均为原子操作。auction_sync 写湖只走本路径。
    """
    tmp = out.with_name(out.name + ".tmp")
    df.write_parquet(tmp)
    tmp.replace(out)  # 同目录 rename, POSIX/NTFS 均为原子操作


def _first_auction_provider() -> Any | None:
    """枚举竞价数据候选源, 返回第一个或 None。

    复用 auction_probe._default_sources 的判定逻辑: (a) 配置了 auction 数据集的
    自定义源; (b) 声明 auction 能力的内置源。只取第一个, 与探测判定使用的
    candidates[0] 保持一致 (探测与写湖必须落到同一数据源)。
    """
    from app.data_providers import chain as provider_chain
    from app.data_providers import custom as custom_sources

    for name in sorted(custom_sources.names()):
        if custom_sources.provider_has_dataset(name, "auction"):
            try:
                return custom_sources.get_provider(name)
            except Exception:  # noqa: BLE001
                continue

    known: set[str] = set()
    for ds_names in provider_chain._BUILTIN_CHAIN.values():  # noqa: SLF001
        known.update(ds_names)
    for name in sorted(known):
        try:
            provider = provider_chain._get_provider(name)  # noqa: SLF001
        except Exception:  # noqa: BLE001
            continue
        if getattr(getattr(provider, "capabilities", None), "auction", False):
            return provider
    return None


def can_sync_auction(capset: CapabilitySet) -> bool:
    """Whether the auction probe reports available.

    签名保留 ``capset`` 以与 ``can_sync_minute`` (kline_sync.py:53-59) 对齐,
    但闸门是 probe 判定而非 capability (RESEARCH Divergence 1)。
    """
    del capset  # 闸门是 probe 而非 capability
    return resolve_auction_probe().status == AuctionProbeStatus.available


def sync_and_persist_auction(
    symbols: list[str],
    repo: KlineRepository,
    capset: CapabilitySet,
    trade_date: date,
) -> int:
    """同步集合竞价匹配数据并按日分区原子写入 kline_auction 湖。

    返回窗口过滤后的总行数; 0 = 跳过/无数据。probe 非 available 时 fail-closed
    不写湖; 09:30+ 连续竞价 bar 由 555..565 窗口谓词结构性排除。
    """
    del capset  # 签名对齐 can_sync_minute; 写湖闸门是 probe
    verdict = resolve_auction_probe()
    if verdict.status != AuctionProbeStatus.available:
        return 0

    provider = _first_auction_provider()
    if provider is None:
        return 0

    df = provider.get_auction(symbols, trade_date)
    if df.is_empty():
        return 0

    # 写湖过滤器 —— 与 provider._normalize_auction (custom/provider.py:149-160)
    # 同一 555..565 谓词 (单一事实源, PATTERNS Shared Patterns)。09:30 连续竞价
    # bar 在此被结构性排除。
    if "datetime" in df.columns:
        if df.schema["datetime"] != pl.Datetime("us"):
            df = df.with_columns(
                pl.col("datetime").cast(pl.Datetime("us"), strict=False),
            )
        _mins = (
            pl.col("datetime").dt.hour().cast(pl.Int32) * 60
            + pl.col("datetime").dt.minute().cast(pl.Int32)
        )
        df = df.filter((_mins >= _WINDOW_START_MIN) & (_mins <= _WINDOW_END_MIN))

    # canonical 裁剪
    keep = [c for c in CANONICAL_AUCTION_COLS if c in df.columns]
    if not keep:
        return 0
    df = df.select(keep)

    # 按日分区合并写 (镜像 sync_and_persist_minute 的 kline_sync.py:892-912):
    # data/kline_auction/date={YYYY-MM-DD}/part.parquet, merge-upsert 幂等。
    df = df.with_columns(pl.col("datetime").dt.date().alias("_trade_date"))
    for day_df in df.partition_by("_trade_date"):
        trade_date_part = day_df["_trade_date"][0]
        out = (
            repo.store.data_dir
            / "kline_auction"
            / f"date={trade_date_part}"
            / "part.parquet"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            existing = pl.read_parquet(out)
            day_df = pl.concat([existing, day_df.drop("_trade_date")]).unique(
                subset=["symbol", "datetime"], keep="last",
            )
        else:
            day_df = day_df.drop("_trade_date")
        day_df = day_df.sort("symbol", "datetime")
        _atomic_write_parquet(day_df, out)

    logger.info(
        "auction synced: %d rows, %d symbols",
        df.height, len(symbols),
    )
    return df.height
