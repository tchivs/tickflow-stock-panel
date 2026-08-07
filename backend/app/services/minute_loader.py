"""分钟确认加载器工厂 (MN-01, Phase 38)。

make_minute_loader(data_dir) -> Callable[[list[str], date], pl.DataFrame]:
供 StrategyEngine minute_loader 注入点 (engine.py:154/163) 使用。

契约:
- 读 data_dir/kline_minute/date={as_of}/part.parquet (canonical 列, kline_sync.py:535-538);
- 过滤候选 symbols (is_in) + sort(["symbol", "datetime"]) — 与既有测试内联 loader 语义一致;
- 缺分区 → canonical 列集空帧 (fail-closed, 确定性); 损坏分区 → warning + 空帧 (fail-closed, 不静默);
- 只读: 本模块零写面 (不 mkdir / 不 write / 不创建 kline_minute 目录)。
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import polars as pl

from app.services.kline_sync import CANONICAL_MINUTE_COLS

logger = logging.getLogger(__name__)


def _empty_minute_frame() -> pl.DataFrame:
    """空分钟帧: 列 = canonical 列集 (引擎只消费 .is_empty(), dtype 中立)。"""
    return pl.DataFrame(schema=CANONICAL_MINUTE_COLS)


def make_minute_loader(data_dir: Path):
    """工厂: 返回 (candidates: list[str], as_of: date) -> pl.DataFrame 的只读 loader。"""

    def _load(candidates: list[str], as_of: date) -> pl.DataFrame:
        part = Path(data_dir) / "kline_minute" / f"date={as_of.isoformat()}" / "part.parquet"
        if not part.exists():
            return _empty_minute_frame()  # 缺分区 → 空帧 fail-closed
        try:
            frame = pl.read_parquet(part)
        except Exception:  # noqa: BLE001 — 损坏分区 → 空帧 fail-closed (warning 可见, 不静默)
            logger.warning("minute partition read failed, fail-closed empty: %s", part)
            return _empty_minute_frame()
        if frame.is_empty():
            return frame
        if candidates:
            frame = frame.filter(pl.col("symbol").is_in(candidates))
        frame = frame.sort(["symbol", "datetime"])
        keep = [c for c in CANONICAL_MINUTE_COLS if c in frame.columns]
        return frame.select(keep)

    return _load
