"""竞价历史回填服务 (AQ-02/03/05) — 运营触发 (operator-triggered), 镜像 pool_backfill 任务形。

诚实闸门 (AQ-03):
- 探针 available + 预检可达才写湖 (任何闸门失败 → 0 写 fail-closed, 绝不伪造成 0 行数据);
- 只写 kline_daily 已对齐日期 (范围 = 分区目录 ∩ [start,end]; 写边界
  ``datetime.date().is_in(aligned_dates)`` —— 上游多返回的日期绝不 phantom-write);
- per-symbol 失败台账 ``failed_symbols: [{symbol, reason}]`` 如实反映部分失败
  (empty_response / 异常串前 200 字, 镜像 auction_probe._ERROR_DETAIL_MAX)。

铁律:
- **绝不 consult ``auction_sync_enabled`` 偏好** (preferences.py:129-132 默认 False;
  定时 EOD 路径保持双闸门关闭; 本任务镜像 pool_backfill 偏好无关)。
- 写湖唯一经 ``auction_sync.write_auction_partitions`` (单一写路径, 32-01);
  ``origin="backfill"`` 只存在于终态 dict —— 湖无 provenance 列 (AQ-01..06 不加,
  provenance 即分区存在性)。
- 每 symbol 串行 1 请求 (上游带宽上限); ``sleep_between_batches(i, rpm)`` 限速。
- 上游显式 429/限速异常 → 指数退避重试 (R1)。
- 本模块不 import 执行族模块 (broker/order/trade/execution/portfolio/position/
  account/transaction) 与 ``strategy_cache`` (E1/E3 形, 32-03 守卫目标)。

终态 dict 键集契约 (W-5):
- 成功 (8 键): ``requested`` / ``backfilled_symbols`` / ``rows`` / ``dates`` /
  ``failed`` / ``failed_symbols`` / ``origin`` / ``rpm``。
- fail-closed (9 键): 上述 8 键 + ``reason`` (source_unavailable / no_provider /
  preflight_empty / no_scope / 预检异常串前 200 字)。
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import date

import polars as pl

from app.tickflow.rate_limits import sleep_between_batches
from app.tickflow.repository import KlineRepository

logger = logging.getLogger(__name__)

# 上游限速信号 (R1): 显式 429 / 限速文案 → 指数退避重试
_RATE_LIMIT_MARKERS = ("429", "rate limit", "rate_limit", "限速", "带宽")
_RETRY_ATTEMPTS = 2  # 初始请求 + 2 次重试
_RETRY_BASE_WAIT_S = 2.0
_ERROR_DETAIL_MAX = 200  # 镜像 auction_probe._ERROR_DETAIL_MAX


def _noop(stage: str, pct: int, msg: str, **kwargs) -> None:  # noqa: ARG001
    pass


def _fail_closed(rpm: int, reason: str) -> dict:
    """fail-closed 终态 (9 键, W-5 契约): 一律 0 写, reason 参数化。"""
    return {
        "requested": 0,
        "backfilled_symbols": 0,
        "rows": 0,
        "dates": 0,
        "failed": 0,
        "failed_symbols": [],
        "reason": reason,
        "origin": "backfill",
        "rpm": rpm,
    }


def _lake_distinct_symbols(repo: KlineRepository, data_dir) -> list[str]:
    """universe = kline_daily 湖去重 symbol, 开工时取一次 (多小时任务不随并发新增分区漂移)。

    首选 DuckDB 视图 (repository.py:162-164, union_by_name=true 容忍 schema drift);
    视图缺失/异常 → polars 列限扫描兜底 (R6); 都失败 → 空 (no_scope fail-closed)。
    """
    try:
        rows = repo.db.execute("SELECT DISTINCT symbol FROM kline_daily").fetchall()
        return sorted(str(r[0]) for r in rows if r[0])
    except Exception:  # noqa: BLE001
        pass
    try:
        df = (
            pl.scan_parquet(str(data_dir / "kline_daily" / "**" / "*.parquet"))
            .select("symbol")
            .unique()
            .collect()
        )
        return sorted(str(s) for s in df["symbol"].to_list() if s)
    except Exception:  # noqa: BLE001
        return []


def _has_daily_rows(repo: KlineRepository, sym: str, start_d: str, end_d: str) -> bool:
    """该 symbol 在 [start_d, end_d] (ISO) 内是否有 kline_daily 行 —— 空 vs 宕机启发式 (RESEARCH §8a)。"""
    try:
        row = repo.db.execute(
            "SELECT 1 FROM kline_daily WHERE symbol = ? AND date >= ? AND date <= ? LIMIT 1",
            [sym, start_d, end_d],
        ).fetchone()
        return row is not None
    except Exception:  # noqa: BLE001
        return False


def _fetch_auction(provider, sym: str, start_d, end_d) -> pl.DataFrame:
    """单 symbol 拉取 (恰 1 码/请求); 上游显式 429/限速异常 → 指数退避重试 (R1)。

    ``start_d``/``end_d`` 为 ``datetime.date`` 对象 (provider 契约
    ``start_date.strftime`` —— xyz_provider.get_auction:189)。
    """
    wait = _RETRY_BASE_WAIT_S
    for attempt in range(_RETRY_ATTEMPTS + 1):
        try:
            return provider.get_auction([sym], start_d, end_d)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if attempt >= _RETRY_ATTEMPTS or not any(
                m in msg for m in _RATE_LIMIT_MARKERS
            ):
                raise
            logger.warning("auction backfill rate-limited (%s), retry %d", msg, attempt + 1)
            time.sleep(wait)
            wait *= 2
    raise AssertionError("unreachable")


def run_auction_backfill(
    repo: KlineRepository,
    *,
    symbols: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    rpm: int = 30,
    on_progress: Callable | None = None,
    job_id: str | None = None,
) -> dict:
    """竞价历史批量回填: 探针闸门 → 范围对齐 → 预检 → 每 symbol 串行限速循环 → 终态 dict。

    - 探针闸门 (AQ-03a): ``resolve_auction_probe().status == available`` 才可能写湖;
      非 available → 0 写 fail-closed (``reason="source_unavailable"``)。绝不 consult
      ``auction_sync_enabled`` 偏好 (EOD 定时路径保持双闸门关闭)。
    - 范围对齐 (AQ-03b): dates = ``data/kline_daily/date=*`` 物理分区目录 (ISO 字典序)
      ∩ [start,end]; symbols = ``symbols`` 子集参数或 kline_daily 湖 DISTINCT (开工一次)。
      写边界 ``datetime.date().is_in(aligned_dates)`` 过滤 —— 上游多返回的日期绝不
      phantom-write。
    - 预检可达性 (AQ-03a): 循环前一次真实 ``get_auction([symbols[0]], ...)``; 异常或
      「有 kline_daily 覆盖却空」→ 0 写 fail-closed。
    - 串行循环 (AQ-05): 每 symbol 1 请求; ``sleep_between_batches(i, rpm)`` 限速
      (rpm 1..60 由端点校验 —— 服务层信任参数, 直接调用方自负其责); 合作式取消
      (job 状态 failed → 提前停止); 进度 ``emit("auction_backfill", pct, ...)``。
    - 失败台账 (AQ-03c): 上游空且该 symbol 范围内有 kline_daily 行 →
      ``empty_response``; 异常 → ``reason = str(e)[:200]``。部分失败如实反映。

    Returns:
        终态 dict (W-5 键集契约, 见模块 docstring): 成功 8 键 / fail-closed 9 键。
    """
    from app.services.auction_probe import AuctionProbeStatus, resolve_auction_probe
    from app.services.auction_sync import _first_auction_provider, write_auction_partitions
    from app.services.pipeline_jobs import job_store

    emit = on_progress or _noop

    # AQ-03a 探针闸门: 非 available → 0 写 fail-closed
    if resolve_auction_probe().status != AuctionProbeStatus.available:
        return _fail_closed(rpm, "source_unavailable")

    # AQ-03b 范围对齐: dates = kline_daily 物理分区目录 ∩ [start,end] (ISO 字典序)
    data_dir = repo.store.data_dir
    daily_base = data_dir / "kline_daily"
    aligned_dates: list[str] = []
    if daily_base.is_dir():
        aligned_dates = sorted(
            d.name[len("date="):]
            for d in daily_base.glob("date=*")
            if d.is_dir() and d.name.startswith("date=")
        )
    if start:
        aligned_dates = [d for d in aligned_dates if d >= start]
    if end:
        aligned_dates = [d for d in aligned_dates if d <= end]

    # universe 开工时取一次 (AQ-05): 子集参数或湖 DISTINCT
    if symbols is None:
        symbols = _lake_distinct_symbols(repo, data_dir)
    if not symbols or not aligned_dates:
        return _fail_closed(rpm, "no_scope")

    provider = _first_auction_provider()
    if provider is None:
        return _fail_closed(rpm, "no_provider")

    # 有效范围 (provider 要求 start_date 非 None; aligned_dates 此处非空)。
    # provider 契约是 date 对象 (get_auction 内 strftime) —— 只转换一次。
    eff_start = start or aligned_dates[0]
    eff_end = end or aligned_dates[-1]
    eff_start_date = date.fromisoformat(eff_start)
    eff_end_date = date.fromisoformat(eff_end)

    # AQ-03a 预检可达性: 循环前一次真实请求; 异常 / 空且有本地覆盖 → 0 写 fail-closed
    try:
        pre = _fetch_auction(provider, symbols[0], eff_start_date, eff_end_date)
    except Exception as e:  # noqa: BLE001
        logger.exception("auction backfill preflight failed: %s", e)
        return _fail_closed(rpm, str(e)[:_ERROR_DETAIL_MAX])
    if pre.is_empty() and _has_daily_rows(repo, symbols[0], eff_start, eff_end):
        return _fail_closed(rpm, "preflight_empty")

    aligned_date_set = {date.fromisoformat(d) for d in aligned_dates}
    requested = len(symbols)
    backfilled = rows = failed = 0
    failed_symbols: list[dict[str, str]] = []

    emit("auction_backfill", 0, f"回填 {requested} 个标的 × {len(aligned_dates)} 日…")
    for i, sym in enumerate(symbols):
        # AQ-05 限速: 共享 _reserve_slot 节流 (每 symbol 1 请求, rpm 默认 30)
        sleep_between_batches(i, rpm)
        # 合作式取消 (镜像 pool_backfill.py:88-91): job failed → 提前停止
        if job_id is not None:
            j = job_store.get(job_id)
            if j is None or j["status"] == "failed":
                emit("done", 100, "回填被取消")
                break
        try:
            df = _fetch_auction(provider, sym, eff_start_date, eff_end_date)
            if df.is_empty():
                # 空 vs 宕机 (RESEARCH §8a): 该 symbol 范围内有 kline_daily 行 → 如实记 empty_response
                if _has_daily_rows(repo, sym, eff_start, eff_end):
                    failed += 1
                    failed_symbols.append({"symbol": sym, "reason": "empty_response"})
                continue
            # AQ-03b 写边界对齐 (承重): 上游多返回的日期绝不 phantom-write
            if "datetime" in df.columns:
                df = df.filter(pl.col("datetime").dt.date().is_in(aligned_date_set))
            if df.is_empty():
                if _has_daily_rows(repo, sym, eff_start, eff_end):
                    failed += 1
                    failed_symbols.append({"symbol": sym, "reason": "empty_response"})
                continue
            # 写湖唯一经 write_auction_partitions (单一写路径, 32-01)
            written = write_auction_partitions(df, repo)
            backfilled += 1
            rows += written  # 窗口过滤后行数; 0 → 仍记 backfilled, rows 不加 (诚实)
        except Exception as e:  # noqa: BLE001
            logger.exception("auction backfill %s failed: %s", sym, e)
            failed += 1
            failed_symbols.append({"symbol": sym, "reason": str(e)[:_ERROR_DETAIL_MAX]})
        emit(
            "auction_backfill",
            int(100 * (i + 1) / requested),
            f"{i + 1}/{requested} (成功 {backfilled}, 失败 {failed})",
            stage_pct=int(100 * (i + 1) / requested),
        )
    emit("done", 100, f"回填完成: {backfilled} 成功, {failed} 失败")
    return {
        "requested": requested,
        "backfilled_symbols": backfilled,
        "rows": rows,
        "dates": len(aligned_dates),
        "failed": failed,
        "failed_symbols": failed_symbols,
        "origin": "backfill",
        "rpm": rpm,
    }
