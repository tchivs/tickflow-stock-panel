"""Enriched 每日覆盖度 — 揭示「管道跑完但只写了 N 只」的全市场数据缺口。

背景 (M003 数据完整性护栏): 外部 EOD 源故障时, 盘后管道对全市场的写入可能退化为
仅自选股几只, 而全期聚合 (trading_days / symbols_covered / 最新日期) 仍显示健康 —
数据页全绿、股池与梯队以裸零值呈现, 用户会把「数据缺口」误读为「市场真相」。

本模块按日统计 enriched 真实行数, 作为股池 / 梯队 / 看板 / 数据页
「数据不完整」警示的唯一事实源。计数来自存储 (duckdb 视图), 绝不来自任务状态。
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

# 完整性阈值: 单日行数 ≥ 期望全市场的 50% 视为完整。
# 正常 EOD 覆盖 ~5200+/5544 (停牌/新股自然缺失), 源故障退化日仅个位数, 取半宽放。
_COVERAGE_RATIO = 0.5

# 快照 TTL: 近 N 日覆盖条 (数据页) 与 expected_universe 共用一份缓存。
_TTL = 60.0
_snapshot_cache: dict | None = None
_snapshot_ts = float("-inf")
_lock = threading.Lock()


def invalidate_coverage_cache() -> None:
    """enriched 写入后由 invalidate_data_cache 调用, 下次读取重算。"""
    global _snapshot_cache, _snapshot_ts
    with _lock:
        _snapshot_cache = None
        _snapshot_ts = float("-inf")


def _expected_universe(repo) -> int:
    try:
        row = repo.execute_one("SELECT count(DISTINCT symbol) FROM instruments")
        if row and row[0]:
            return int(row[0])
    except Exception as e:  # noqa: BLE001
        logger.debug("coverage expected_universe failed: %s", e)
    return 0


def coverage_snapshot(repo, days: int = 10) -> dict:
    """近 N 交易日覆盖快照: {expected_universe, threshold, days: [{date, rows, complete}]}。

    days 按 enriched 视图真实分区取 (缺数据的交易日天然不在列表中 — 本身即信号)。
    """
    global _snapshot_cache, _snapshot_ts
    now = time.time()
    with _lock:
        if _snapshot_cache is not None and (now - _snapshot_ts) < _TTL:
            return _snapshot_cache

    expected = _expected_universe(repo)
    threshold = int(expected * _COVERAGE_RATIO)
    daily: list[dict] = []
    try:
        rows = repo.execute_all(
            "SELECT date, count(*) AS n FROM kline_enriched "
            "GROUP BY date ORDER BY date DESC LIMIT ?",
            [int(days)],
        )
        daily = [
            {
                "date": str(d),
                "rows": int(n),
                "complete": (n >= threshold) if threshold > 0 else True,
            }
            for d, n in rows
        ]
    except Exception as e:  # noqa: BLE001
        logger.debug("coverage daily group-by failed: %s", e)

    snap = {"expected_universe": expected, "threshold": threshold, "days": daily}
    with _lock:
        _snapshot_cache = snap
        _snapshot_ts = now
    return snap


def coverage_for_date(repo, as_of) -> dict:
    """单日 coverage 对象 (嵌入既有 API 响应的附加字段)。

    {date, rows, expected, complete} — rows 为该日 enriched 真实行数;
    该日无任何行 (快照缺失) 时 rows=0 / complete=False, 诚实回显。
    """
    date_str = str(as_of)
    expected = _expected_universe(repo)
    threshold = int(expected * _COVERAGE_RATIO)
    rows_n = 0
    try:
        row = repo.execute_one(
            "SELECT count(*) FROM kline_enriched WHERE date = ?", [date_str]
        )
        if row and row[0] is not None:
            rows_n = int(row[0])
    except Exception as e:  # noqa: BLE001
        logger.debug("coverage for date %s failed: %s", date_str, e)
    return {
        "date": date_str,
        "rows": rows_n,
        "expected": expected,
        "complete": (rows_n >= threshold) if threshold > 0 else True,
    }
