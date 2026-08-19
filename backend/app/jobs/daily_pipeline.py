"""盘后管道 + 盘前维表同步。

调度:
  09:10 盘前 — 同步个股维表 instruments (全量覆盖)
  15:30 盘后 — 日K同步 + 增量除权因子 + enriched 计算 + 刷新视图

盘后同步策略:
  日 K: QuoteService 交易时段已实时落盘 → 有数据时跳过 batch,首次拉 1 年区间
  除权因子: 从已有数据最新日期的下一天开始增量获取,避免重复拉取和计算
"""
from __future__ import annotations

import logging
import time as _time
from collections.abc import Callable
from datetime import date
from pathlib import Path

import polars as pl
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.indicators.pipeline import run_pipeline
from app.config import settings
from app.market_time import cn_today
from app.services import auction_sync, index_sync, instrument_sync, kline_sync, preferences as _prefs
from app.tickflow.capabilities import Cap, CapabilitySet
from app.tickflow.pools import DEMO_SYMBOLS, get_pool
from app.tickflow.repository import KlineRepository

logger = logging.getLogger(__name__)

ProgressCb = Callable[..., None]


class PipelineStageError(RuntimeError):
    """管道有阶段软失败(数据可能陈旧)时抛出, 让上层 job_store 把任务标记为 failed。

    这些阶段单独 try/except 吞掉异常以不中断整条管道, 但一旦失败即代表对应数据陈旧。
    抛出前进度协议已走完(done/100), 故前端进度条正常收尾, 仅终态如实反映为 failed ——
    不再"部分失败却报成功"。
    """

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("盘后管道部分阶段失败: " + "; ".join(errors))


def _noop(stage: str, pct: int, msg: str, **kwargs) -> None:  # noqa: ARG001
    pass

# EOD 源就绪竞态重试 (sync_daily): 今日日K 行数不足时延迟重拉。
_EOD_SOURCE_RETRY_MAX = 3
_EOD_SOURCE_RETRY_WAIT_MIN = 3

# 残写 enriched 分区自愈 (compute_enriched): 自选实时写盘会让「今日」分区提前
# 存在(仅几行), 方向检测按「分区存在性」判新日期 → 永不算新 → EOD enriched 跳过。
# 按行数比对最近 N 个共同日期: enriched 明显薄于同日 daily(源故障/竞态残写)
# → 删该分区, 让其自然进入 new_dates 走增量重算。
_STALE_ENRICHED_CHECK_DAYS = 10
_STALE_ENRICHED_RATIO = 0.5


def _eod_complete_threshold(repo) -> int:
    """今日日K「基本完整」行数阈值: 全市场标的数 × 0.5 (与 coverage 口径一致)。"""
    try:
        row = repo.execute_one("SELECT count(DISTINCT symbol) FROM instruments")
        if row and row[0]:
            return int(int(row[0]) * 0.5)
    except Exception as e:  # noqa: BLE001
        logger.debug("eod threshold instruments count failed: %s", e)
    return 0


def _partition_row_counts(repo, view: str) -> dict[str, int]:
    """{date_iso: rows} — duckdb 视图按日计数 (失败返回空, 调用方自然跳过自愈)。"""
    try:
        rows = repo.execute_all(f"SELECT date, count(*) FROM {view} GROUP BY date")  # noqa: S608
        return {str(d): int(n) for d, n in rows}
    except Exception as e:  # noqa: BLE001
        logger.debug("partition row counts (%s) failed: %s", view, e)
        return {}


def fixture_provider_enabled() -> bool:
    """Whether the isolated Phase 1 acceptance provider was explicitly enabled."""
    import os

    return os.environ.get("PHASE1_FIXTURE_MODE", "").strip().lower() in {"1", "true", "yes"}


def run_phase1_fixture_sync(
    data_dir: Path, *, readiness: "AdvancedFixtureReadiness | None" = None
) -> dict:
    """Write the read-only acceptance fixture through the normal governed lake path."""
    import os

    from app.contracts.market_data import AdvancedFixtureReadiness, FixtureContractError
    from app.contracts.validator import validate_market_data_contract
    from app.data_providers.fixture_provider import FixtureProvider
    from app.tickflow.repository import DataStore

    if not fixture_provider_enabled():
        raise RuntimeError("D-13 fixture mode requires PHASE1_FIXTURE_MODE=1")
    fixture_dir = os.environ.get("PHASE1_FIXTURE_DIR")
    if not fixture_dir:
        raise RuntimeError("D-13 fixture mode requires PHASE1_FIXTURE_DIR")

    provider = FixtureProvider(Path(fixture_dir))
    if readiness is not None and not isinstance(readiness, AdvancedFixtureReadiness):
        raise FixtureContractError("fixture_readiness has an invalid descriptor type")
    if os.environ.get("ADVANCED_HOST_FIXTURE", "").strip():
        if readiness is None:
            raise FixtureContractError("advanced host requires a validated fixture_readiness descriptor")
        provider.preflight_advanced_host(readiness)
    elif readiness is not None:
        raise FixtureContractError("fixture_readiness is only valid for advanced host fixtures")
    store = DataStore(Path(data_dir))
    repo = KlineRepository(store)
    stages: list[str] = []

    def emit(stage: str, pct: int, message: str) -> None:
        logger.info("fixture sync %s (%d%%): %s", stage, pct, message)
        stages.append(stage)

    try:
        emit("sync_instruments", 10, "writing fixture instruments")
        instruments = provider.get_instruments("stock")
        instruments_path = store.data_dir / "instruments" / "instruments.parquet"
        repo._atomic_write_parquet(instruments.unique(subset=["symbol"]).sort("symbol"), instruments_path)

        symbols = instruments["symbol"].to_list()
        emit("sync_daily", 35, "writing fixture daily bars")
        daily = provider.get_daily(symbols, None, None, "stock")
        repo.append_daily(daily)

        emit("sync_index_daily", 42, "writing fixture index daily bars")
        repo.append_index_daily(provider.get_index_daily([], None, None))

        emit("sync_adj", 50, "writing fixture adjustment factors")
        factors = provider.get_adj_factors(symbols, None, None, "stock").rename({"adj_factor": "ex_factor"})
        factors_path = store.data_dir / "adj_factor" / "all.parquet"
        repo._atomic_write_parquet(
            factors.unique(subset=["symbol", "trade_date"], keep="last").sort(["symbol", "trade_date"]),
            factors_path,
        )

        emit("sync_financials", 60, "writing fixture financial records")
        financials = provider.get_financials()
        financials_path = store.data_dir / "financials" / "metrics" / "part.parquet"
        repo._atomic_write_parquet(financials, financials_path)

        emit("compute_enriched", 80, "computing governed enriched data")
        run_pipeline(data_dir=store.data_dir)

        emit("refresh_views", 90, "refreshing DuckDB views")
        _refresh_views(repo)
        repo.refresh_cache()

        validate_market_data_contract(store.data_dir)
        emit("done", 100, "fixture synchronization complete")
        return {"provider": provider.name, "stages": stages}
    finally:
        store.db.close()


def _invalidate(table: str | None = None) -> None:
    """stage 写完调用,让 /api/data/status 只重算被影响的那张表。"""
    from app.api.data import invalidate_data_cache
    invalidate_data_cache(table)


def _resolve_universe(capset: CapabilitySet, repo=None) -> list[str]:
    """解析标的池 — 以 CN_Equity_A (沪深京A股 ~5522只) 为主。

    有 batch 能力 → 直接拉 CN_Equity_A universe
    其他用户 → 用 instruments parquet + watchlist 兜底

    repo 传入时过滤自选兜底里的指数 symbol (指数日K走独立 kline_index_* 存储,
    进股票池会污染 kline_daily/kline_minute)。ETF 刻意保留 (既有行为)。
    """
    if capset.has(Cap.KLINE_DAILY_BATCH):
        try:
            all_a = get_pool("CN_Equity_A", refresh=True)
            if all_a:
                return sorted(all_a)
        except Exception as e:  # noqa: BLE001
            logger.warning("CN_Equity_A pool unavailable, fallback: %s", e)

    # Free 用户兜底: instruments parquet + watchlist + demo
    base: set[str] = set(DEMO_SYMBOLS)
    base.update(get_pool("watchlist"))
    d = Path(settings.data_dir)
    inst_path = d / "instruments" / "instruments.parquet"
    if inst_path.exists():
        try:
            inst = pl.read_parquet(inst_path, columns=["symbol"])
            base.update(inst["symbol"].to_list())
        except Exception as e:  # noqa: BLE001
            logger.warning("instruments supplement failed: %s", e)
    # 过滤自选兜底里的指数 symbol (指数日K走独立 kline_index_* 存储,
    # 进股票池会污染 kline_daily/kline_minute)。ETF 刻意保留 (既有行为)。
    if repo is not None:
        base -= set(repo.get_index_symbol_set())
    return sorted(base)


def run_instruments_sync(repo: KlineRepository) -> dict:
    """盘前同步个股维表。

    维表含当日涨跌停价 (limit_up/down), 同步完成后刷新 enriched 内存缓存,
    确保跨天后连板梯队/选股等读到的是基于最新维表的数据 (而非前一交易日残留)。
    """
    rows = instrument_sync.sync_instruments(repo.store.data_dir)
    _refresh_instruments_view(repo)
    _invalidate("instruments")
    # 维表更新后重建 enriched 缓存 (clear + refresh, 与设置页「清理并刷新」同等效果)
    if rows > 0:
        repo.clear_cache()
        repo.refresh_cache()
    return {"instruments_rows": rows}


def run_now(
    repo: KlineRepository,
    capset: CapabilitySet,
    on_progress: ProgressCb | None = None,
    override_start_date: _date | None = None,
) -> dict:
    """立即执行一次盘后管道,支持进度回调。

    跳过的 stage **不 emit**,避免前端把"无 capability"的卡片错误标记为 active/done。
    result 里带 skipped_stages 列表供前端展示。

    override_start_date: 传入时强制走 batch 拉取分支,用该日期作为日K/除权/指数的
        拉取起点(到今天),用于「数据修正/补数据」场景。None 时走原有自动判定逻辑。
    """
    emit = on_progress or _noop
    skipped: list[str] = []
    # 阶段软失败累积: 下列阶段 try/except 吞异常以不中断管道, 但失败即代表数据可能陈旧。
    # 管道末尾若非空则抛 PipelineStageError, 让任务终态如实标记为 failed(而非误报成功)。
    stage_errors: list[str] = []

    # Step 0: 先同步个股维表, 再解析标的池 — 确保标的池基于最新 instruments
    emit("sync_instruments", 2, "同步个股维表…")
    inst_rows = instrument_sync.sync_instruments(repo.store.data_dir)
    if inst_rows > 0:
        _refresh_instruments_view(repo)
    emit("sync_instruments", 8, f"个股维表同步完成,{inst_rows} 只标的")
    _invalidate("instruments")

    emit("resolve_universe", 9, "解析标的池…")
    universe = _resolve_universe(capset, repo)
    emit("resolve_universe", 10, f"标的池规模:{len(universe)} 只")

    # Step 1: 日 K 同步
    #   override_start_date 传入 → 强制 batch 拉取 [override_start_date ~ today] (数据修正)
    #   付费档 + 今天有数据 → 实时行情接口拉一次覆写（1请求全市场）
    #   有历史数据 → batch K-line API 补齐缺口
    #   无任何数据 → batch K-line API 拉首次 1 年
    from datetime import date as _date, timedelta as _td, datetime as _dt
    latest_daily = repo.latest_daily_date()
    today = _date.today()
    today_exists = latest_daily and latest_daily >= today
    new_daily_days = 0
    # 日K范围拉取的起点(分支3补缺口/分支4首次/数据修正); 实时增量/跳过时为 None。
    # 供 Step 1.5 除权因子回溯范围对齐: 范围拉取→用日K范围, 非范围→最近N天兜底。
    daily_range_start: _date | None = None

    # A 股日K拉取开关(默认开);关闭时跳过日K同步,保留已有数据。
    # 数据修正(override_start_date)时即使关闭开关也强制拉取 — 修正就是来补数据的。
    pull_a_share = _prefs.get_pipeline_pull_a_share()
    if not pull_a_share and not override_start_date:
        emit("sync_daily", 45, "已跳过 A 股日K同步(拉取内容未勾选)")
        logger.info("sync_daily: skipped (pipeline_pull_a_share=False)")
    elif override_start_date:
        # 数据修正: 强制用传入日期作起点 batch 拉取, 忽略实时行情覆写分支。
        start_date = override_start_date
        daily_range_start = start_date
        emit("sync_daily", 12, f"获取日K [{start_date} ~ {today}]…")
        logger.info("sync_daily: [%s ~ %s] repair/override", start_date, today)

        def _daily_chunk_progress(cur: int, tot: int) -> None:
            emit("sync_daily", 12 + int(33 * cur / tot),
                 f"日K 批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)
        written_daily = kline_sync.sync_and_persist_daily_batch(
            universe, repo, capset,
            start_date=_dt.combine(start_date, _dt.min.time()),
            end_date=_dt.combine(today, _dt.min.time()),
            on_chunk_done=_daily_chunk_progress,
        )
        gap_days = (today - start_date).days
        new_daily_days = gap_days
        emit("sync_daily", 45, f"日K 完成,覆盖 {gap_days} 天")
        logger.info("sync_daily: [%s ~ %s] done, %d days", start_date, today, gap_days)
    elif today_exists and capset.has(Cap.QUOTE_POOL) and _prefs.get_daily_data_provider() == "tickflow":
        # 付费档:今天有数据(QuoteService 已落盘)→ 实时行情覆写,确保最新。
        # free/none 档无 quote.pool 能力,即便今天已有数据(如从 expert 降级),
        # 也降级到下方 batch 路径刷新,避免调用无权限的实时行情接口。
        emit("sync_daily", 12, f"获取日K [{today} ~ {today}] 实时行情…")
        written_daily = kline_sync.sync_daily_by_quotes(repo)
        new_daily_days = 1
        emit("sync_daily", 45, f"日K 完成,{written_daily} 只标的")
        logger.info("sync_daily: [%s ~ %s] live quotes, %d symbols", today, today, written_daily)
    elif latest_daily:
        # 有历史 → batch 补齐缺口。
        # 也覆盖"今天已有数据但无实时行情权限(free/none)"的降级场景:
        #   此时 start_date = latest_daily = today,batch 刷新当天日K。
        start_date = latest_daily
        daily_range_start = start_date
        emit("sync_daily", 12, f"获取日K [{start_date} ~ {today}]…")
        logger.info("sync_daily: [%s ~ %s] %s", start_date, today,
                    "refresh today" if today_exists else "gap fill")

        def _daily_chunk_progress(cur: int, tot: int) -> None:
            emit("sync_daily", 12 + int(33 * cur / tot),
                 f"日K 批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)
        def _pull_daily() -> int:
            return kline_sync.sync_and_persist_daily_batch(
                universe, repo, capset,
                start_date=_dt.combine(start_date, _dt.min.time()),
                end_date=_dt.combine(today, _dt.min.time()),
                on_chunk_done=_daily_chunk_progress,
            )
        written_daily = _pull_daily()
        # EOD 源就绪竞态护栏 (2026-08-18 实例): stockdb 15:30 起才开始当日 EOD
        # 采集, 管道同刻拉取拿到空 → 今日 daily 仍是自选残写几行, enriched 随之
        # 跳过。今日行数不足时延迟重拉, 等 EOD 源就绪; 重试耗尽仍薄 → 照常走
        # 下方流程 (M003 coverage 横幅如实示警, 次日管道经 B 层自愈补齐)。
        if start_date == today:
            for attempt in range(1, _EOD_SOURCE_RETRY_MAX + 1):
                try:
                    row = repo.execute_one(
                        "SELECT count(*) FROM kline_daily WHERE date = ?", [today.isoformat()])
                    n_today = int(row[0]) if row else 0
                except Exception:  # noqa: BLE001
                    break
                if n_today >= _eod_complete_threshold(repo):
                    break
                emit("sync_daily", 12 + int(30 * attempt / (_EOD_SOURCE_RETRY_MAX + 1)),
                     f"今日日K仅 {n_today} 只, 等待 EOD 源就绪重拉 ({attempt}/{_EOD_SOURCE_RETRY_MAX})")
                logger.info("sync_daily: 今日日K仅 %d 只 (阈值 %d), %d 分钟后重拉 (%d/%d)",
                            n_today, _eod_complete_threshold(repo),
                            _EOD_SOURCE_RETRY_WAIT_MIN, attempt, _EOD_SOURCE_RETRY_MAX)
                _time.sleep(_EOD_SOURCE_RETRY_WAIT_MIN * 60)
                written_daily = _pull_daily()
        gap_days = (today - start_date).days
        new_daily_days = gap_days
        emit("sync_daily", 45, f"日K 完成,覆盖 {gap_days} 天")
        logger.info("sync_daily: [%s ~ %s] done, %d days", start_date, today, gap_days)
    else:
        # 首次：无任何数据 → batch 拉 1 年
        start_date = today - _td(days=365)
        daily_range_start = start_date
        emit("sync_daily", 12, f"获取日K [{start_date} ~ {today}]…")
        logger.info("sync_daily: [%s ~ %s] initial fetch", start_date, today)

        def _daily_chunk_progress(cur: int, tot: int) -> None:
            emit("sync_daily", 12 + int(33 * cur / tot),
                 f"日K 批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)
        written_daily = kline_sync.sync_and_persist_daily_batch(
            universe, repo, capset,
            start_date=_dt.combine(start_date, _dt.min.time()),
            end_date=_dt.combine(today, _dt.min.time()),
            on_chunk_done=_daily_chunk_progress,
        )
        new_daily_days = 365
        emit("sync_daily", 45, "日K 完成")
        logger.info("sync_daily: [%s ~ %s] done", start_date, today)
    _invalidate("daily")

    # 单标的新鲜度: 全局 max(date) 会被任一有今日数据的标的"拉高", 掩盖停牌/复牌/
    # 一直拉失败而掉队的个股缺口(全局判据只刷"今天", 永不回补掉队标的的历史缺口)。
    # 这里检测并**可见化**(WARNING + 计入结果), 让掉队标的不再隐形。
    # (自动回补暂不做 —— 需带退市判定, 否则对已退市标的每轮空拉浪费 API 额度。)
    lagging_symbols: list[str] = []
    if pull_a_share and latest_daily:
        try:
            lagging_symbols = repo.symbols_lagging(today, min_gap_days=3)
            if lagging_symbols:
                logger.warning("日K新鲜度: %d 只标的落后 >3 日 (停牌/退市/拉取失败; 样例: %s)",
                               len(lagging_symbols), lagging_symbols[:10])
        except Exception as e:  # noqa: BLE001
            logger.warning("laggard detection failed: %s", e)
            stage_errors.append(f"laggard detection: {e}")

    # Step 1.5: 同步除权因子 — 范围与日K拉取方式对齐
    #   日K范围拉取(补缺口/首次) → 除权用日K范围 [daily_range_start, now]
    #     首次会覆盖整个日K区间内的历史除权事件; 补缺口天然只增量(起点=latest_daily≈昨天)
    #   日K实时增量/跳过(分支2/分支1) → 除权兜底拉最近 30 天, 补可能遗漏的新除权
    #     (这两类分支不拉历史日K, 除权不能用日K范围, 只能兜底最近几日)
    written_adj = 0
    affected_symbols: list[str] = []
    can_sync_adj = kline_sync.can_sync_adj_factor(capset)
    if can_sync_adj:
        from datetime import datetime, timedelta
        adj_end = datetime.now()
        if daily_range_start is not None:
            adj_start = datetime.combine(daily_range_start, datetime.min.time())
        else:
            # 日K实时增量/跳过时, 除权兜底拉最近 N 天, 覆盖周末/长假/停机期间的新除权事件。
            # 15 天: 覆盖春节/国庆最长约10天长假 + 故障恢复缓冲; sync_adj_factor 内部 merge+unique 幂等, 多拉无副作用。
            adj_start = adj_end - timedelta(days=15)
        adj_start_str = adj_start.strftime("%Y-%m-%d")
        adj_end_str = adj_end.strftime("%Y-%m-%d")
        emit("sync_adj", 50, f"获取除权因子 [{adj_start_str} ~ {adj_end_str}]…")
        logger.info("sync_adj: [%s ~ %s] start", adj_start_str, adj_end_str)

        def _adj_chunk_progress(cur: int, tot: int) -> None:
            emit("sync_adj", 50 + int(10 * cur / tot),
                 f"除权因子批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)
        written_adj, affected_symbols = kline_sync.sync_adj_factor(
            universe, repo, capset,
            start_time=adj_start, end_time=adj_end,
            on_chunk_done=_adj_chunk_progress,
        )
        if affected_symbols:
            _refresh_single_view(repo, "adj_factor")
            emit("sync_adj", 60, f"除权因子完成,新增 {len(affected_symbols)} 只个股")
            logger.info("sync_adj: [%s ~ %s] done, %d symbols", adj_start_str, adj_end_str, len(affected_symbols))
        else:
            emit("sync_adj", 60, "除权因子完成,无新增")
            logger.info("sync_adj: [%s ~ %s] no new factors", adj_start_str, adj_end_str)
        _invalidate("adj_factor")
    else:
        skipped.append("sync_adj")
        logger.info("sync_adj skipped: no ADJ_FACTOR capability")

    # Step 2: 计算 enriched
    #   判断策略:
    #     - 首次 (enriched 目录不存在) → 全量
    #     - 往前扩展历史 (新日期 < enriched 已有最早日期) → 全量
    #       前面的除权因子会改变累积因子链,影响后面所有日期的复权价格
    #     - 往后新增日期 (新日期 > enriched 已有最晚日期)
    #       → 增量补新区块(所有标的) + 受除权影响个股全日期重算
    #     - 无新日期 + 有新除权因子 → 增量: 只重算受影响个股的全部日期
    #     - 无新日期 + 无变化 → 跳过
    enriched_dir = repo.store.data_dir / "kline_daily_enriched"
    enriched_exists = enriched_dir.exists() and any(enriched_dir.glob("date=*"))
    daily_dir = repo.store.data_dir / "kline_daily"
    daily_days = len(list(daily_dir.glob("date=*"))) if daily_dir.exists() else 0
    prev_enriched_days = len(list(enriched_dir.glob("date=*"))) if enriched_exists else 0

    # 数据修正 (override_start_date): 修正范围内的 enriched 分区是旧口径数据
    # (典型: 破损日的 5 行残写), 而下方方向检测按「分区存在性」判新日期,
    # 分区已存在 → new_dates 为空 → 跳过重算, 修正永远到不了 enriched。
    # 先删 [start, today] 范围内的 stale 分区, 让方向检测自然走增量重算。
    if override_start_date is not None and enriched_exists:
        import shutil
        removed = 0
        for part in enriched_dir.glob("date=*"):
            try:
                part_date = date.fromisoformat(part.stem.split("=")[1])
            except ValueError:
                continue
            if part_date >= override_start_date:
                shutil.rmtree(part, ignore_errors=True)
                removed += 1
        if removed:
            logger.info("compute_enriched: repair mode removed %d stale enriched partitions >= %s",
                        removed, override_start_date)
            enriched_exists = enriched_dir.exists() and any(enriched_dir.glob("date=*"))
            prev_enriched_days = len(list(enriched_dir.glob("date=*"))) if enriched_exists else 0

    # 残写自愈 (B 层): daily/enriched 分区都在但 enriched 明显薄于同日 daily
    # (自选残写/源故障) → 方向检测判不出新日期, EOD enriched 永远跳过。
    # 删薄分区, 让其自然进入 new_dates。放在 days 计数之后、方向检测之前,
    # 删除会同步刷新 prev_enriched_days 以触发下方 daily_days > prev 判定。
    if enriched_exists:
        daily_counts = _partition_row_counts(repo, "kline_daily")
        enriched_counts = _partition_row_counts(repo, "kline_enriched")
        if daily_counts and enriched_counts:
            common = sorted(set(daily_counts) & set(enriched_counts))[-_STALE_ENRICHED_CHECK_DAYS:]
            stale = [d for d in common
                     if enriched_counts[d] < daily_counts[d] * _STALE_ENRICHED_RATIO]
            if stale:
                import shutil
                for d in stale:
                    shutil.rmtree(enriched_dir / f"date={d}", ignore_errors=True)
                logger.info(
                    "compute_enriched: removed %d thin enriched partitions "
                    "(enriched << daily, dates=%s)",
                    len(stale), ",".join(stale))
                enriched_exists = enriched_dir.exists() and any(enriched_dir.glob("date=*"))
                prev_enriched_days = len(list(enriched_dir.glob("date=*"))) if enriched_exists else 0

    # 判断新日期方向: 找 daily 和 enriched 的日期集合做比较
    forward_incremental = False
    backward_extension = False

    if daily_days > prev_enriched_days and enriched_exists:
        daily_dates = sorted(d.stem.split("=")[1] for d in daily_dir.glob("date=*"))
        enriched_dates = sorted(d.stem.split("=")[1] for d in enriched_dir.glob("date=*"))
        earliest_enriched = enriched_dates[0]
        latest_enriched = enriched_dates[-1]
        new_dates = set(daily_dates) - set(enriched_dates)
        if new_dates:
            # 有新日期早于 enriched 最早日期 → 往前扩展
            if any(d < earliest_enriched for d in new_dates):
                backward_extension = True
            # 有新日期晚于 enriched 最晚日期 → 往后新增
            if any(d > latest_enriched for d in new_dates):
                forward_incremental = True

    def _enriched_batch_progress(cur: int, tot: int) -> None:
        emit("compute_enriched", 65 + int(23 * cur / tot),
             f"计算指标 批次 {cur}/{tot}", stage_pct=int(100 * cur / tot), skip_log=True)

    if not enriched_exists or backward_extension:
        # 首次 或 往前扩展 → 全量
        emit("compute_enriched", 65, "全量计算 enriched…")
        logger.info("compute_enriched: full rebuild (first=%s, backward=%s, daily=%d, enriched=%d)",
                    not enriched_exists, backward_extension, daily_days, prev_enriched_days)
        written_enriched = run_pipeline(on_batch_done=_enriched_batch_progress)
        new_enriched_days = len(list(enriched_dir.glob("date=*")))
        emit("compute_enriched", 88, f"enriched 完成,覆盖 {new_enriched_days} 天")
        logger.info("compute_enriched: full rebuild done, %d days", new_enriched_days)
    elif forward_incremental:
        # 往后新增日期: 增量补新区块 + 受影响个股全日期重算
        symbols_to_recompute = list(set(affected_symbols)) if affected_symbols else []
        emit("compute_enriched", 65,
             f"增量计算 enriched (新日期 + {len(symbols_to_recompute)} 只个股重算)…"
             if symbols_to_recompute else "增量计算 enriched (新日期)…")
        logger.info("compute_enriched: forward incremental, %d symbols to recompute",
                    len(symbols_to_recompute))
        written_enriched = run_pipeline(
            new_dates_only=True,
            symbols=symbols_to_recompute or None,
            on_batch_done=_enriched_batch_progress,
        )
        new_enriched_days = len(list(enriched_dir.glob("date=*")))
        emit("compute_enriched", 88, f"enriched 完成,覆盖 {new_enriched_days} 天")
        logger.info("compute_enriched: forward incremental done, %d days", new_enriched_days)
    elif affected_symbols:
        # 无新日期,仅除权因子变更 → 只重算受影响个股的全部日期
        emit("compute_enriched", 65, f"增量计算 enriched ({len(affected_symbols)} 只个股)…")
        logger.info("compute_enriched: adj_factor incremental, %d symbols", len(affected_symbols))
        written_enriched = run_pipeline(symbols=affected_symbols, on_batch_done=_enriched_batch_progress)
        emit("compute_enriched", 88, f"enriched 完成,{len(affected_symbols)} 只个股")
    else:
        written_enriched = 0
        logger.info("compute_enriched: skip (no new daily, no adj_factor changes)")
    _refresh_single_view(repo, "kline_enriched")
    _invalidate("enriched")

    # Step 2.3: 指数 / ETF 同步 — 物理分开存储；ETF 可复权，指数不复权。
    written_index_daily = 0
    written_etf_daily = 0
    index_count = 0
    etf_count = 0
    etf_adj_symbols = 0
    pull_index = _prefs.get_pipeline_pull_index()
    pull_etf = _prefs.get_pipeline_pull_etf()

    if kline_sync.can_sync_daily(capset) and (pull_index or pull_etf):
        _types = []
        if pull_index:
            _types.append("指数")
        if pull_etf:
            _types.append("ETF")
        emit("sync_index", 88, f"同步{'+'.join(_types)}日K…")
        # 子阶段进度分配: 88.0(开始) → 89.0(完成), 指数占前半, ETF 占后半
        try:
            if pull_index:
                emit("sync_index", 88, "同步指数维表…")
                index_count = index_sync.sync_index_instruments(repo, pull_index=True, pull_etf=False)
                emit("sync_index", 88, f"指数维表完成,{index_count} 只")
                index_dir = repo.store.data_dir / "kline_index_enriched"
                index_dates = sorted(
                    d.name[5:] for d in index_dir.glob("date=*")
                    if d.is_dir() and d.name.startswith("date=")
                ) if index_dir.exists() else []
                # 数据修正模式下用传入起点; 否则用本地指数最新日期补到今天
                if override_start_date:
                    index_start = override_start_date
                else:
                    index_start = _date.fromisoformat(index_dates[-1]) if index_dates else today - _td(days=365)

                def _index_chunk(cur: int, tot: int) -> None:
                    emit("sync_index", 88, f"指数日K批次 {cur}/{tot}",
                         stage_pct=int(100 * cur / tot) if tot else 100, skip_log=cur < tot)

                written_index_daily = index_sync.sync_and_persist_index_daily(
                    repo,
                    capset,
                    start_date=_dt.combine(index_start, _dt.min.time()),
                    end_date=_dt.combine(today, _dt.min.time()),
                    on_chunk_done=_index_chunk,
                )
                emit("sync_index", 88, f"指数日K完成,{written_index_daily} 行")
                _invalidate("index_instruments")
                _invalidate("index_daily")
                _invalidate("index_enriched")

            if pull_etf:
                emit("sync_index", 88, "同步 ETF 维表…")
                etf_count = index_sync.sync_etf_instruments(repo)
                emit("sync_index", 88, f"ETF 维表完成,{etf_count} 只")
                etf_symbols: list[str] = []
                etf_inst = repo.get_etf_instruments()
                if not etf_inst.is_empty() and "symbol" in etf_inst.columns:
                    etf_symbols = sorted(set(etf_inst["symbol"].to_list()))
                if etf_symbols and kline_sync.can_sync_adj_factor(capset):
                    try:
                        emit("sync_index", 88, "同步 ETF 除权因子…")
                        from datetime import datetime, timedelta
                        adj_end = datetime.now()
                        adj_path = repo.store.data_dir / "adj_factor_etf" / "all.parquet"
                        fallback_start = adj_end - timedelta(days=30)
                        adj_start = fallback_start
                        if adj_path.exists():
                            max_date = pl.scan_parquet(adj_path).select(pl.col("trade_date").max()).collect().item()
                            if max_date is not None:
                                if isinstance(max_date, str):
                                    adj_start = datetime.combine(_date.fromisoformat(max_date), datetime.min.time())
                                elif isinstance(max_date, datetime):
                                    adj_start = datetime.combine(max_date.date(), datetime.min.time())
                                else:
                                    adj_start = datetime.combine(max_date, datetime.min.time())
                        _, affected_etfs = index_sync.sync_etf_adj_factor(
                            etf_symbols,
                            repo,
                            capset,
                            start_time=adj_start,
                            end_time=adj_end,
                        )
                        etf_adj_symbols = len(affected_etfs)
                        emit("sync_index", 88, f"ETF 除权因子完成,{etf_adj_symbols} 只")
                    except Exception as e:  # noqa: BLE001
                        logger.warning("ETF adj_factor skipped: %s", e)
                        stage_errors.append(f"ETF adj_factor: {e}")
                etf_dir = repo.store.data_dir / "kline_etf_enriched"
                etf_dates = sorted(
                    d.name[5:] for d in etf_dir.glob("date=*")
                    if d.is_dir() and d.name.startswith("date=")
                ) if etf_dir.exists() else []
                etf_start = _date.fromisoformat(etf_dates[-1]) if etf_dates else today - _td(days=365)

                def _etf_chunk(cur: int, tot: int) -> None:
                    emit("sync_index", 88, f"ETF 日K批次 {cur}/{tot}",
                         stage_pct=int(100 * cur / tot) if tot else 100, skip_log=cur < tot)

                written_etf_daily = index_sync.sync_and_persist_etf_daily(
                    repo,
                    capset,
                    start_date=_dt.combine(etf_start, _dt.min.time()),
                    end_date=_dt.combine(today, _dt.min.time()),
                    on_chunk_done=_etf_chunk,
                )
                emit("sync_index", 88, f"ETF 日K完成,{written_etf_daily} 行")
                _invalidate("etf_instruments")
                _invalidate("etf_daily")

            repo.refresh_index_views()
            emit(
                "sync_index",
                89,
                f"同步完成,指数 {index_count} 只/{written_index_daily} 行, ETF {etf_count} 只/{written_etf_daily} 行"
                + (f", ETF复权 {etf_adj_symbols} 只" if etf_adj_symbols else ""),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("sync_index/etf failed: %s", e)
            emit("sync_index", 89, f"指数/ETF同步失败:{e}")
            stage_errors.append(f"index/etf sync: {e}")
    else:
        skipped.append("sync_index")

    # Step 2.5: 分钟 K 同步(可选) — 未启用或无 capability 时静默跳过(不 emit)
    from app.services import preferences
    minute_on = preferences.get_minute_sync_enabled()
    minute_days = preferences.get_minute_sync_days()
    written_minute = 0
    if minute_on and kline_sync.can_sync_minute(capset):
        minute_start = today - _td(days=minute_days)
        emit("sync_minute", 90, f"获取分钟K [{minute_start} ~ {today}]…")
        logger.info("sync_minute: [%s ~ %s] start", minute_start, today)
        minute_symbols = _resolve_minute_symbols(capset, repo)
        def _minute_chunk_progress(cur: int, tot: int, seg_label: str = "") -> None:
            emit("sync_minute", 90 + int(3 * cur / tot),
                 f"分钟K 批次 {cur}/{tot}" + (f" [{seg_label}]" if seg_label else ""),
                 stage_pct=int(100 * cur / tot), skip_log=True)
        written_minute = kline_sync.sync_and_persist_minute(
            minute_symbols, repo, capset, days=minute_days,
            on_chunk_done=_minute_chunk_progress,
        )
        minute_dir = repo.store.data_dir / "kline_minute"
        minute_cover_days = len(list(minute_dir.glob("date=*"))) if minute_dir.exists() else 0
        emit("sync_minute", 93, f"分钟K完成,覆盖 {minute_cover_days} 天")
        logger.info("sync_minute: [%s ~ %s] done, %d days", minute_start, today, minute_cover_days)
        _invalidate("minute")
    else:
        skipped.append("sync_minute")
        if minute_on:
            logger.info("sync_minute skipped: selected provider has no minute dataset")
        else:
            logger.info("sync_minute skipped: user disabled")

    # Step 2.6: 竞价同步(可选) — 用户显式开启 + probe available 时写湖并刷新视图;
    # 未开启或 probe 不可用时静默跳过 (计入 skipped, 不 emit、不写湖、从不静默填湖)。
    written_auction = _run_auction_sync(repo, capset, today)
    if written_auction > 0:
        auction_dir = repo.store.data_dir / "kline_auction"
        auction_cover_days = len(list(auction_dir.glob("date=*"))) if auction_dir.exists() else 0
        emit("sync_auction", 94, f"竞价数据完成,覆盖 {auction_cover_days} 天")
        logger.info("sync_auction: done, %d rows, %d days", written_auction, auction_cover_days)
        _invalidate("auction")
        _refresh_single_view(repo, "kline_auction")
    else:
        skipped.append("sync_auction")
    # Step 2.6: 市场环境(regime) 增量计算 — enriched 已就绪后聚合环境指标。
    # 双检测(缺口+stale), 自动补算遗漏/被覆写的日。软失败: 不阻断主管道。
    # 默认关闭: regime 是本地聚合计算(非拉取), 首次/regime 表为空时需全量回填
    # 多日, 内存与耗时较高。用户可在数据页「市场环境」卡片设置里开启自动计算,
    # 或直接在该页面点「重算」手动触发(不受此开关影响)。
    regime_days = 0
    from app.services import preferences as _prefs_regime
    if not _prefs_regime.get_pipeline_regime_enabled():
        skipped.append("regime")
        logger.info("compute_regime skipped: user disabled (pipeline_regime_enabled=False)")
    else:
        try:
            emit("compute_regime", 90, "计算市场环境…")
            from app.services import regime_builder
            from app.api.regime import invalidate_regime_cache
            new_regime = regime_builder.compute_regime_incremental(repo, repo.store.data_dir)
            regime_days = new_regime.height if not new_regime.is_empty() else 0
            if regime_days:
                invalidate_regime_cache()
                logger.info("compute_regime: %d days", regime_days)
            emit("compute_regime", 92, f"市场环境 {regime_days} 天")
            # 阶段切换推送监控通知 (软失败, 不影响管道): 末两日阶段不同 = 今日发生切换。
            # 切入退潮/冰点为风险信号, 用 warn 级别; 其余 info。
            if regime_days:
                try:
                    _push_phase_change_alert(repo.store.data_dir)
                except Exception as e:
                    logger.warning("phase change alert failed (soft): %s", e)
        except Exception as e:  # noqa: BLE001
            logger.warning("compute_regime failed (soft): %s", e)
            stage_errors.append(f"compute_regime: {e}")
            skipped.append("regime")

    # Step 2.7: 市场主线(概念/行业涨停梯队聚合) 增量计算 — regime 同开关。
    # 只窄扫连板 >=1 的行, 增量通常 1 天, 开销可忽略。软失败: 不阻断主管道。
    mainline_rows = 0
    if not _prefs_regime.get_pipeline_regime_enabled():
        skipped.append("mainline")
    else:
        try:
            emit("compute_mainline", 93, "计算市场主线…")
            from app.services import market_mainline
            for _kind in ("concept", "industry"):
                rows = market_mainline.compute_mainline_incremental(
                    repo, repo.store.data_dir, kind=_kind
                )
                mainline_rows += rows.height if not rows.is_empty() else 0
            if mainline_rows:
                logger.info("compute_mainline: %d rows", mainline_rows)
            emit("compute_mainline", 94, f"市场主线 {mainline_rows} 行")
        except Exception as e:
            logger.warning("compute_mainline failed (soft): %s", e)
            stage_errors.append(f"compute_mainline: {e}")
            skipped.append("mainline")

    # Step 3: 刷新视图
    emit("refresh_views", 95, "刷新 DuckDB 视图…")
    _refresh_views(repo)

    emit("done", 100, "完成")
    _invalidate(None)  # 兜底:全清

    result = {
        "universe_size": len(universe),
        "daily_days": new_daily_days,
        "adj_factor_symbols": len(affected_symbols),
        "enriched_days": written_enriched,
        "index_count": index_count,
        "index_daily_rows": written_index_daily,
        "etf_count": etf_count,
        "etf_daily_rows": written_etf_daily,
        "etf_adj_factor_symbols": etf_adj_symbols,
        "minute_rows": written_minute,
        "auction_rows": written_auction,
        "regime_days": regime_days,
        "mainline_rows": mainline_rows,
        "lagging_symbols": len(lagging_symbols),
        "skipped_stages": skipped,
        "stage_errors": stage_errors,
    }

    # 有阶段软失败: 进度协议已走完(done/100, 前端进度条正常收尾), 但数据可能陈旧,
    # 抛出让上层 job_store 把终态标记为 failed —— 不再"部分失败却报成功"。
    if stage_errors:
        raise PipelineStageError(stage_errors)

    return result


def _refresh_views(repo: KlineRepository) -> None:
    """刷新所有 DuckDB 视图 —— 委托给 repository 的唯一权威实现 rebuild_views()。"""
    repo.rebuild_views()


def _refresh_single_view(repo: KlineRepository, name: str) -> None:
    """刷新单个 DuckDB 视图。"""
    d = repo.store.data_dir.as_posix()
    paths = {
        "kline_daily": f"{d}/kline_daily/**/*.parquet",
        "kline_enriched": f"{d}/kline_daily_enriched/**/*.parquet",
        "kline_index_daily": f"{d}/kline_index_daily/**/*.parquet",
        "kline_index_enriched": f"{d}/kline_index_enriched/**/*.parquet",
        "kline_etf_daily": f"{d}/kline_etf_daily/**/*.parquet",
        "kline_etf_enriched": f"{d}/kline_etf_enriched/**/*.parquet",
        "kline_etf_minute": f"{d}/kline_etf_minute/**/*.parquet",
        "kline_minute": f"{d}/kline_minute/**/*.parquet",
        "kline_auction": f"{d}/kline_auction/**/*.parquet",
        "adj_factor": f"{d}/adj_factor/**/*.parquet",
        "adj_factor_etf": f"{d}/adj_factor_etf/**/*.parquet",
        "instruments": f"{d}/instruments/**/*.parquet",
        "instruments_index": f"{d}/instruments_index/**/*.parquet",
        "instruments_etf": f"{d}/instruments_etf/**/*.parquet",
    }
    path = paths.get(name)
    if not path:
        return
    try:
        repo.db.execute(
            f"CREATE OR REPLACE VIEW {name} AS "
            f"SELECT * FROM read_parquet('{path}', union_by_name=true)"
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("refresh view %s failed: %s", name, e)


def _resolve_minute_symbols(capset: CapabilitySet, repo=None) -> list[str]:
    """分钟 K 同步标的 — 默认与日K共用同一标的池。

    运算符可通过 minute_sync_symbols 偏好限定同步范围 (空列表 = 全量, 默认行为不变),
    用于廉价的验证/spot 同步 (research PITFALLS.md pitfall 3)。
    """
    scoped = _prefs.get_minute_sync_symbols()
    if scoped:
        return scoped
    return _resolve_universe(capset, repo)


def _resolve_auction_symbols(capset: CapabilitySet) -> list[str]:
    """竞价同步标的 — 默认与日K共用同一标的池。

    运算符可通过 auction_sync_symbols 偏好限定同步范围 (空列表 = 全量, 镜像 minute)。
    """
    scoped = _prefs.get_auction_sync_symbols()
    if scoped:
        return scoped
    return _resolve_universe(capset)


def _run_auction_sync(repo: KlineRepository, capset: CapabilitySet, trade_date: date) -> int:
    """Step 2.6 竞价同步 stage 闸门 — 返回写入行数, 0 = 跳过。

    双闸门: 偏好显式开启 (auction_sync_enabled, 默认 False) + probe available。
    未开启或 probe 不可用时返回 0 (不 emit、不写湖、从不静默填湖)。
    """
    if not _prefs.get_auction_sync_enabled():
        return 0
    if not auction_sync.can_sync_auction(capset):
        return 0
    return auction_sync.sync_and_persist_auction(
        _resolve_auction_symbols(capset), repo, capset, trade_date=trade_date,
    )


def _refresh_instruments_view(repo: KlineRepository) -> None:
    """单独刷新 instruments 视图。"""
    d = repo.store.data_dir.as_posix()
    try:
        repo.db.execute(
            f"CREATE OR REPLACE VIEW instruments AS "
            f"SELECT * FROM read_parquet('{d}/instruments/**/*.parquet', union_by_name=true)"
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("refresh instruments view failed: %s", e)


def _push_phase_change_alert(data_dir) -> None:
    """情绪周期阶段切换 → 推送监控通知(SSE toast + 监控中心)。

    阶段切换(如 退潮→冰点)是重要的市场信号, 原先只有打开市场环境页才能看到。
    复用 quote_service.push_alerts 广播通道; 未发生切换静默返回。
    """
    from app.services.market_phase import PHASE_LABELS
    from app.services.regime_builder import latest_phase_transition

    tr = latest_phase_transition(data_dir)
    if not tr:
        return
    prev, cur, d = tr
    msg = f"情绪周期阶段切换: {PHASE_LABELS.get(prev, prev)} → {PHASE_LABELS.get(cur, cur)} ({d})"
    severity = "warn" if cur in ("ebb", "ice") else "info"
    app_state = _get_app_state()
    qs = getattr(app_state, "quote_service", None) if app_state else None
    if qs:
        qs.push_alerts([{
            "source": "market",
            "type": "phase_change",
            "message": msg,
            "severity": severity,
        }])
    logger.info("phase change alert: %s (severity=%s)", msg, severity)


def _run_tracked(fn, job_label: str, *, independent: bool = False) -> bool:
    """调度触发时包装 JobStore 跟踪，确保同步历史有记录。

    单飞: 若已有活跃(pending∨running)任务(手动同步中), 本次调度直接跳过, 不并发。
    重任务执行槽: 再挡一层僵尸并发(reap 后线程仍活时不得并行写 parquet)。

    independent=True: 该 job 的写面与其它重任务**不相交** (如盘前预览只写
    ``premarket_results/`` 独立根, 绝不写 strategy_cache/screener_results), 因此:
    - 只按 ``label`` 去重 (同任务不重入), 不占全局单飞 — 同槽位 (09:26) 竞价采集
      不再把它静默挤掉;
    - 不占全局重任务槽 (无共享 parquet 写面, 并行不损坏数据)。
    调用方必须确保该 job 确实只写自身独立根, 否则不得置 True (镜像
    premarket_pool.py 铁律: 零写共享湖/缓存)。
    返回 True 仅表示任务已成功并且执行槽已释放。
    """
    from app.services.pipeline_jobs import job_store, release_run_slot, try_acquire_run_slot

    if independent:
        job_id, is_new = job_store.create(label=job_label)
        if not is_new:
            logger.info("scheduled %s 跳过: 同任务活跃 (job_id=%s)", job_label, job_id)
            return False
    else:
        job_id, is_new = job_store.create()
        if not is_new:
            logger.info("scheduled %s 跳过: 已有活跃任务在运行 (job_id=%s)", job_label, job_id)
            return False
        if not try_acquire_run_slot():
            logger.warning("scheduled %s 跳过: 重任务执行槽被占用(疑似上次任务卡死)", job_label)
            job_store.fail(job_id, f"scheduled {job_label} skipped: 已有数据任务在运行")
            return False

    def progress(stage: str, pct: int, msg: str, stage_pct: int | None = None,
                 skip_log: bool = False) -> None:
        job_store.progress(job_id, stage, pct, msg, stage_pct=stage_pct, skip_log=skip_log)

    succeeded = False
    try:
        job_store.start(job_id)
        result = fn(on_progress=progress)
        job_store.succeed(job_id, result)
        succeeded = True
        logger.info("scheduled %s completed: job_id=%s", job_label, job_id)
    except Exception:
        logger.exception("scheduled %s failed: job_id=%s", job_label, job_id)
        job_store.fail(job_id, f"scheduled {job_label} failed")
    finally:
        if not independent:
            release_run_slot()
    return succeeded


def _scheduled_pipeline_task(pipeline_fn) -> None:
    """Run weekly mining only after the tracked daily pipeline has fully succeeded."""
    if not _run_tracked(pipeline_fn, "daily_pipeline"):
        return
    try:
        from app.services.mining_schedule import run_weekly_mining

        result = run_weekly_mining(_get_app_state())
        logger.info("scheduled mining result: %s", result)
    except Exception:
        logger.exception("scheduled mining enqueue failed; daily pipeline remains succeeded")


# ================================================================
# 定时复盘 (AI 大盘复盘报告)
# ================================================================

REVIEW_JOB_ID = "scheduled_review"


async def _run_scheduled_review(repo) -> None:
    """定时复盘 job: 流式生成复盘 → 实时推 SSE(开着页面可见) → 落盘归档 → 推飞书。

    与手动「生成复盘」体验一致: 流式事件经 quote_service.push_review_event →
    /api/intraday/stream 的 review_progress 事件 → 前端 reviewStore, 用户开着复盘页
    即可看到报告边生成边显示, 切走再回来也能看到生成中/已生成。
    LLM 偶发断流(peer closed connection)时自动重试最多 2 次。
    任何异常都吞掉只记日志, 绝不影响调度器主循环。
    """
    import json

    try:
        from app.services import market_recap_reports
        from app import secrets_store as ss

        # AI Key 未配置时跳过(避免每日报错刷日志)
        if not ss.get_ai_key():
            logger.info("scheduled review skipped: AI key not configured")
            return

        app_state = _get_app_state()
        quote_service = getattr(app_state, "quote_service", None) if app_state else None
        depth_service = getattr(app_state, "depth_service", None) if app_state else None

        content, meta = await _stream_review_with_retry(repo, quote_service, depth_service)
        if not content:
            logger.warning("scheduled review produced no content (meta=%s)", meta)
            # 通知前端进入 error 态(若有页面在听)
            if quote_service:
                quote_service.push_review_event(json.dumps(
                    {"type": "error", "message": "复盘生成失败,请稍后手动重试"},
                    ensure_ascii=False))
            return

        # 落盘: 与手动生成完全相同的归档格式
        market_recap_reports.save_report({
            "as_of": meta.get("as_of"),
            "focus": "",
            "content": content,
            "summary": meta.get("summary", ""),
            "emotion_score": meta.get("emotion_score"),
            "emotion_label": meta.get("emotion_label", ""),
        })
        logger.info("scheduled review saved: as_of=%s", meta.get("as_of"))

        # 通知前端: 生成完成且已归档(archived=true 让前端只刷新列表, 不重复归档)
        if quote_service:
            quote_service.push_review_event(json.dumps(
                {"type": "done", "archived": True}, ensure_ascii=False))

        # 推送到飞书(可选): 运行时读取配置, 用户改设置下次触发即生效。
        # 失败静默降级, 不影响已归档的报告。
        _maybe_push_review(content, meta)
    except Exception as e:  # noqa: BLE001
        logger.exception("scheduled review failed: %s", e)
        # 兜底: 异常时通知前端停止「生成中」状态, 避免页面卡在 streaming
        try:
            app_state = _get_app_state()
            qs = getattr(app_state, "quote_service", None) if app_state else None
            if qs:
                import json as _json
                qs.push_review_event(_json.dumps(
                    {"type": "error", "message": "复盘生成异常,请稍后手动重试"},
                    ensure_ascii=False))
        except Exception:  # noqa: BLE001
            pass


async def _stream_review_with_retry(repo, quote_service, depth_service) -> tuple[str, dict]:
    """流式生成复盘, 每个事件推 SSE + 累积内容。LLM 断流时最多重试 2 次。

    返回 (content, meta)。重试时推一个 retry 事件让前端清空已累积内容重新开始。
    成功(收到 done/无 error)或耗尽重试后返回。
    """
    import asyncio
    import json
    from app.services.market_recap import recap_market_stream

    max_attempts = 3  # 初次 + 2 次重试
    last_meta: dict = {}
    content_parts: list[str] = []

    for attempt in range(1, max_attempts + 1):
        content_parts = []  # 每次重试重新累积
        failed = False
        try:
            async for evt_json in recap_market_stream(repo, quote_service, depth_service):
                evt = json.loads(evt_json)
                t = evt.get("type")

                # 推给前端(让开着页面的用户实时看到, 与手动一致)
                if quote_service:
                    quote_service.push_review_event(evt_json)

                if t == "meta":
                    last_meta = evt
                elif t == "delta" and evt.get("content"):
                    content_parts.append(evt["content"])
                elif t == "error":
                    failed = True
                    logger.warning("scheduled review stream error (attempt %d/%d): %s",
                                   attempt, max_attempts, evt.get("message"))
                    break  # 触发重试
                elif t == "done":
                    # 正常完成
                    return "".join(content_parts), last_meta
            # 流自然结束(无 done 事件)且有内容, 视为成功
            if content_parts and not failed:
                return "".join(content_parts), last_meta
        except Exception as e:  # noqa: BLE001
            # LLM 断流等异常(httpx.RemoteProtocolError)落到这里
            failed = True
            logger.warning("scheduled review stream exception (attempt %d/%d): %s",
                           attempt, max_attempts, e)

        # 失败: 决定是否重试
        if attempt < max_attempts:
            logger.info("scheduled review retrying in 3s (attempt %d → %d)", attempt, attempt + 1)
            # 通知前端: 即将重试, 清空已累积内容重新开始
            if quote_service:
                quote_service.push_review_event(json.dumps(
                    {"type": "retry", "attempt": attempt + 1}, ensure_ascii=False))
            await asyncio.sleep(3)

    # 耗尽重试, 返回已累积内容(可能为空)和最后 meta
    return "".join(content_parts), last_meta


def _maybe_push_review(content: str, meta: dict) -> None:
    """复盘报告归档后, 按 review_push_channels 选定的外部工具逐个推送完整报告。

    定时生成与手动生成共用本函数 (手动归档端点 POST /api/market-recap/reports 也会调用)。
    channels 为空则不推送; 'feishu' 复用监控中心的全局飞书 Webhook 通道。
    推送失败静默降级 (Webhook 是辅助通道), 不影响已归档的报告。
    """
    try:
        from app.services import preferences, webhook_adapter

        channels = preferences.get_review_push_channels()
        if not channels:
            return

        emotion = f"{meta.get('emotion_label') or ''}".strip()
        as_of = meta.get("as_of") or ""
        subtitle = as_of + (f" · 情绪 {emotion}" if emotion else "")

        for ch in channels:
            if ch == "feishu":
                url = preferences.get_feishu_webhook_url()
                if not url:
                    logger.info("review push(feishu) skipped: webhook not configured")
                    continue
                secret = preferences.get_feishu_webhook_secret()
                ok = webhook_adapter.send_feishu_card(
                    url, "AthenaQuant · 每日复盘", subtitle, content, secret
                )
                logger.info("review push(feishu) %s", "sent" if ok else "failed")
            elif ch == "wecom":
                url = preferences.get_wecom_webhook_url()
                if not url:
                    logger.info("review push(wecom) skipped: webhook not configured")
                    continue
                # 企业微信 markdown 标题已含一级标题, subtitle 拼到正文首行
                full_body = (f"**{subtitle}**\n\n{content}" if subtitle else content)
                ok = webhook_adapter.send_wecom_markdown(
                    url, "AthenaQuant · 每日复盘", full_body
                )
                logger.info("review push(wecom) %s", "sent" if ok else "failed")
            # 未来更多渠道在此追加分支
    except Exception as e:  # noqa: BLE001
        logger.warning("review push error: %s", e)


def _register_review_job(scheduler, repo, hour: int, minute: int) -> None:
    """注册/更新定时复盘 job(工作日 mon-fri, Asia/Shanghai)。

    供 start_scheduler(启动时) 和 settings API(改时间时) 共用。
    用 replace_existing=True, 重复注册只更新 trigger。

    注意: _run_scheduled_review 是协程函数, 必须把函数对象本身(配合 args)传给
    add_job, 而非用 lambda 包裹 —— 否则 APScheduler 会把 lambda 当同步函数在线程池
    执行, 仅得到一个未 await 的协程对象, 复盘实际不会运行。
    """
    scheduler.add_job(
        _run_scheduled_review,
        args=[repo],
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=hour, minute=minute,
                            timezone="Asia/Shanghai"),
        id=REVIEW_JOB_ID,
        misfire_grace_time=7200,  # 复盘非关键, 允许 2 小时内补跑
        replace_existing=True,
    )


# ================================================================
# 盘后股池 EOD 持久化 (POOL-06)
# ================================================================

# 盘后管道完成后偏移几分钟再跑股池持久化, 确保当日 enriched 已落盘。
_POOL_EOD_JOB_ID = "pool_eod_persist"
_POOL_EOD_OFFSET_MIN = 5

# 盘前预览 job (PM-01): 09:25 集合竞价撮合定盘后 09:26 生成盘前预览股池。
# 固定 09:26 (mon-fri, Asia/Shanghai) — 位于 09:25 撮合定盘后 / 09:30 连续竞价前,
# open 已定盘, open_gap 与 EOD 口径一致; 不开放偏好配置 (09:25 是硬边界)。
_PREMARKET_JOB_ID = "premarket_pool_preview"
_PREMARKET_HOUR, _PREMARKET_MINUTE = 9, 26


def _pool_eod_persist(on_progress=None) -> dict:
    """盘后 EOD job: 经 service 级共享核心预生成当日冻结快照 + 刷新最新指针。

    每交易日盘后(管道完成后 +5min)直调 ``ScreenerService.run_all_with_hits``
    跑全部策略, 先 ``strategy_cache.write_cache`` 刷新最新指针(顺带修复陈旧
    as_of), 再 ``pool_snapshot.persist_point_snapshot`` 落冻结式点快照。

    - 绝不 HTTP 自调 POST /api/screener/run_all (service 级共享核心, 单条代码路径)。
    - 无数据日/无 app state → 诚实 skip, 不写任何文件 (首个历史日请求只读快照,
      不触发请求内重算)。
    - 与手动 run_all 的并发写防护由调用方 ``_run_tracked`` 单飞保证。
    """
    from datetime import datetime

    from app.services import pool_snapshot, strategy_cache
    from app.services.screener import ScreenerService

    app_state = _get_app_state()
    if app_state is None:
        return {"as_of": None, "skipped": "no app state"}
    repo = app_state.repo
    svc = ScreenerService(repo)
    as_of = svc.latest_date()
    if as_of is None:
        return {"as_of": None, "skipped": "no data date"}

    emit = on_progress or _noop
    emit("pool_eod_persist", 0, f"股池 EOD 持久化 {as_of}: 运行全部策略…")
    data_dir = repo.store.data_dir
    results = svc.run_all_with_hits(as_of, engine=getattr(app_state, "strategy_engine", None))
    if results:
        # 先刷新最新指针, 再落冻结快照 (与手动 run_all 调用点 1 顺序一致)。
        strategy_cache.write_cache(data_dir, str(as_of), results)
        pool_snapshot.persist_point_snapshot(
            data_dir,
            str(as_of),
            results,
            strategy_version=pool_snapshot.strategy_fingerprint(app_state.strategy_engine),
            computed_at=datetime.now().isoformat(timespec="seconds"),
        )
        # CONCEPT-01: 概念/行业历史归档 (读本地快照零网络, 同步; 失败不阻断股池持久化)。
        from app.services import concept_history

        try:
            concept_history.capture(data_dir, str(as_of))  # as_of 是 date 对象, str()=ISO
        except Exception as e:  # noqa: BLE001
            logger.warning("概念历史归档失败（不阻断股池持久化）: %s", e)
    emit("done", 100, f"股池 EOD 持久化完成, {len(results)} 个策略")
    return {"as_of": str(as_of), "strategies": len(results)}


def _premarket_pool_preview(on_progress=None) -> dict:
    """盘前预览 job: 09:26 生成今日盘前股池到独立 ``premarket_results/date={T}/part.json``。

    - 复用 ``ScreenerService.run_all_with_hits`` 单条代码路径 (与 EOD/回填同源),
      as_of = 今日 T (北京时间); 经 ``build_premarket_preview`` 构造 payload。
    - **绝不调 strategy_cache.write_cache / pool_snapshot.persist_point_snapshot**
      (PM-01 铁律, 镜像 pool_backfill.py:1-11) — strategy_cache.json 的 as_of 与
      screener_results/date=* 在本 job 运行后不被改动。
    - 无 app state / 无 enriched 基准日 → 诚实 skip, 不写任何文件 (镜像
      _pool_eod_persist 966-975 skip 语义)。
    - 与手动 run_all / EOD job 的并发写防护由调用方 ``_run_tracked`` 单飞保证。
    """
    from app.services import premarket_pool, premarket_snapshot
    from app.services.screener import ScreenerService

    app_state = _get_app_state()
    if app_state is None:
        return {"as_of": None, "skipped": "no app state"}
    repo = app_state.repo
    svc = ScreenerService(repo)
    if svc.latest_date() is None:
        return {"as_of": None, "skipped": "no data date"}

    today = cn_today()
    emit = on_progress or _noop
    emit(_PREMARKET_JOB_ID, 0, f"盘前预览 {today}: 运行全部策略…")
    data_dir = repo.store.data_dir
    payload = premarket_pool.build_premarket_preview(
        repo,
        engine=getattr(app_state, "strategy_engine", None),
        as_of=today,
    )
    result: dict = {
        "as_of": str(today),
        "strategies": len(payload.get("results", {})),
        "degraded": payload.get("degraded"),
    }
    # 只在 available 时落盘 (空帧/无 live 缓存 → available:false → 不写文件, 诚实 skip)
    if payload.get("available"):
        premarket_snapshot.persist_premarket_snapshot(data_dir, str(today), payload)
        # MON-03: 盘前告警评估尾段 — 与 persist 同一 _run_tracked 单飞内, 内存直取
        # payload (免二次读盘); 失败不阻断预览持久化/成功返回 (镜像 _pool_eod_persist
        # concept_history 非致命 try/except 风格)。payload.available:false 路径不评估
        # 不告警 (既有 if 守卫天然覆盖), 也不追加 preopen_eval 键。
        try:
            qs = getattr(app_state, "quote_service", None)
            if qs is not None and callable(getattr(qs, "evaluate_premarket_alerts", None)):
                result_extra = qs.evaluate_premarket_alerts(payload) or {}
            else:
                logger.info("盘前告警评估跳过: quote_service 未装配")
                result_extra = {"skipped": "quote_service not assembled"}
        except Exception as e:  # noqa: BLE001
            logger.warning("盘前告警评估失败 (不阻断预览持久化): %s", e)
            result_extra = {"skipped": "evaluation error"}
        result["preopen_eval"] = result_extra
    emit("done", 100, f"盘前预览完成, {len(payload.get('results', {}))} 个策略")
    return result


# ================================================================
# 竞价采集 sidecar (SDC-01..03) — 09:26 采集 / 09:40 对账 / EOD 15:40 提审
# ================================================================

# 09:26 与盘前预览同槽位不同 id (APScheduler 多 job 并发合法, 互不干扰);
# 09:40 对账时 09:30 bar 已由服务端分钟采集产出 (数据在场判定交易日);
# EOD 15:40 提审 (EOD 后宽窗口)。
_SIDECAR_CAPTURE_JOB_ID = "auction_sidecar_capture"
_SIDECAR_CAPTURE_HOUR, _SIDECAR_CAPTURE_MINUTE = 9, 26
_SIDECAR_RECONCILE_JOB_ID = "auction_sidecar_reconcile"
_SIDECAR_RECONCILE_HOUR, _SIDECAR_RECONCILE_MINUTE = 9, 40
_SIDECAR_PROMOTE_JOB_ID = "auction_sidecar_promote"
_SIDECAR_PROMOTE_HOUR, _SIDECAR_PROMOTE_MINUTE = 15, 40

# 懒构造 provider 单例: app.state 无 provider 面, StockDBProvider 默认从 settings
# 注入 base_url/api_key。构造失败 → job 抛异常 → _run_tracked 标记 failed (不吞)。
_sidecar_provider = None


def _get_sidecar_provider():
    global _sidecar_provider
    if _sidecar_provider is None:
        from app.data_providers.stockdb_provider import StockDBProvider

        _sidecar_provider = StockDBProvider()
    return _sidecar_provider


def _sidecar_failed_symbols(pool) -> list[str]:
    """池解析 failed 列表 ({symbol, reason} dict 或 str) → symbol 字符串列表。"""
    if not isinstance(pool, dict):
        return []
    failed = pool.get("failed") or []
    return [f.get("symbol") if isinstance(f, dict) else str(f) for f in failed]


def _sidecar_capture(on_progress=None) -> dict:
    """09:26 竞价采集 job: fetch-on-miss 单次 GET 全窗口 → staging 原子写 + 台账。

    - 绝不盘中轮询: 服务端湖文件缺失 → 首 GET 触发全窗口采集, 文件存在后永不刷新;
    - 完整性 fail-closed 在 capture_auction_window 内 (归属日/撮合行/窗口阈值三拒,
      全失败 → 无分区); 终态 → auction_sidecar_ledger.append_ledger (W-5 键集);
    - 告警由 09:40 对账 job 判定 (09:26 时点 09:30 bar 未产出, 无法确认交易日)。
    """
    from app.services import auction_capture, auction_sidecar_ledger

    app_state = _get_app_state()
    if app_state is None:
        return {"job": _SIDECAR_CAPTURE_JOB_ID, "skipped": "no app state"}
    repo = app_state.repo
    data_dir = repo.store.data_dir
    today = cn_today()
    emit = on_progress or _noop
    emit(_SIDECAR_CAPTURE_JOB_ID, 0, f"竞价采集 {today}: 解析采集池…")

    pool = auction_capture.resolve_sidecar_pool()
    symbols = pool["symbols"] if isinstance(pool, dict) else list(pool)
    failed_symbols = _sidecar_failed_symbols(pool)
    if not symbols:
        entry = {
            "job": _SIDECAR_CAPTURE_JOB_ID,
            "trade_date": today.isoformat(),
            "requested": 0,
            "ok": 0,
            "failed_symbols": failed_symbols,
        }
        entry["reason"] = "no_pool"
        auction_sidecar_ledger.append_ledger(data_dir, entry)
        emit("done", 100, "竞价采集跳过: 采集池为空")
        return entry

    emit(_SIDECAR_CAPTURE_JOB_ID, 30,
         f"采集池 {len(symbols)} symbol, 触发 fetch-on-miss 全窗口采集…")
    result = auction_capture.capture_auction_window(
        _get_sidecar_provider(), symbols, today, data_dir,
    )
    result_failed = result.get("failed") or []
    entry = {
        "job": _SIDECAR_CAPTURE_JOB_ID,
        "trade_date": today.isoformat(),
        "requested": result.get("requested", len(symbols)),
        "ok": result.get("ok", 0),
        "failed_symbols": [f.get("symbol") if isinstance(f, dict) else str(f)
                           for f in result_failed],
    }
    if entry["ok"] == 0:
        entry["reason"] = "capture_all_failed"
    auction_sidecar_ledger.append_ledger(data_dir, entry)
    emit("done", 100, f"竞价采集完成: ok={entry['ok']}/{entry['requested']}")
    return entry


def _sidecar_reconcile(on_progress=None) -> dict:
    """09:40 对账 job: 09:25 撮合行 vs 09:30 bar 三重闭合 + 诚实门告警 + 台账。

    - 交易日判定 = 数据在场 (reconcile_window.trading_day_confirmed — 09:30 bar
      存在, AQ 无日历服务 Q6/A5); 非交易日 → 台账 skipped_no_data, 零告警;
    - 告警 (SDC-03「09:26 后缺失可告」): 交易日 ∧ 09:26 采集缺失/不完整 →
      auction_sidecar_capture_missing; 对账 mismatch → auction_sidecar_reconcile_fail;
    - 内部 09:45 重试由 reconcile_window 实现 (09:30 bar 缺失 → 300s 重试 1 次 →
      pending, A5)。
    """
    from app.services import auction_capture, auction_reconcile, auction_sidecar_ledger

    app_state = _get_app_state()
    if app_state is None:
        return {"job": _SIDECAR_RECONCILE_JOB_ID, "skipped": "no app state"}
    repo = app_state.repo
    data_dir = repo.store.data_dir
    today = cn_today()
    emit = on_progress or _noop
    emit(_SIDECAR_RECONCILE_JOB_ID, 0, f"竞价对账 {today}: 09:25 撮合行 vs 09:30 bar…")

    result = auction_reconcile.reconcile_window(_get_sidecar_provider(), data_dir, today)
    trading_day = bool(result.get("trading_day_confirmed", False))

    entry = {
        "job": _SIDECAR_RECONCILE_JOB_ID,
        "trade_date": today.isoformat(),
        "requested": 0,
        "ok": 0,
        "failed_symbols": [],
    }
    checks = result.get("checks") or {}
    if isinstance(checks, dict) and checks:
        entry["requested"] = len(checks)
        entry["ok"] = sum(
            1 for c in checks.values() if isinstance(c, dict) and c.get("status") == "closed"
        )
        entry["failed_symbols"] = [
            sym for sym, c in checks.items()
            if not (isinstance(c, dict) and c.get("status") == "closed")
        ]
    status = result.get("status")
    if not trading_day:
        entry["skipped"] = "no_data"
        auction_sidecar_ledger.append_ledger(data_dir, entry)
        emit("done", 100, f"竞价对账 {today}: 非交易日 (无 09:30 bar), 静默跳过")
        return entry
    if status == "mismatch":
        entry["reason"] = "reconcile_mismatch"
    elif status in ("staging_missing", "pending"):
        entry["reason"] = status

    capture_state = auction_sidecar_ledger.read_sidecar_capture_state(data_dir, today)
    if capture_state is None:
        # 09:26 采集分区/manifest 缺失 (采集 job 未跑或全失败未落盘) — 交易日上按池
        # 解析给 requested 提示, ok=0 → capture_missing 告警 (缺失可告)。
        pool = auction_capture.resolve_sidecar_pool()
        symbols = pool["symbols"] if isinstance(pool, dict) else list(pool)
        capture_state = {
            "requested": len(symbols),
            "ok": 0,
            "failed_symbols": _sidecar_failed_symbols(pool),
            "completeness_ok": False,
        }
    events = auction_sidecar_ledger.evaluate_sidecar_alerts(
        data_dir, today.isoformat(), capture_state, result, trading_day,
    )
    entry["events"] = [e["rule_id"] for e in events] if events else []
    auction_sidecar_ledger.append_ledger(data_dir, entry)
    emit("done", 100, f"竞价对账完成: status={status}, 告警={len(events)}")
    return entry


def _sidecar_promote(on_progress=None) -> dict:
    """EOD 15:40 提审 job: 对账 closed 的当日 staging 仅撮合行升 canonical + 台账。

    - 提审闸门在 promote_trading_day 内 (staging manifest completeness.ok ∧
      reconciliation.closed — Pitfall 6: 不用 xyz probe); 闸门不过 → 0 写 + reason;
    - 虚拟快照行 (num_trades=0) 永不入湖 (43-02 谓词 + 提审过滤双保险)。
    """
    from app.services import auction_promote, auction_sidecar_ledger

    app_state = _get_app_state()
    if app_state is None:
        return {"job": _SIDECAR_PROMOTE_JOB_ID, "skipped": "no app state"}
    repo = app_state.repo
    data_dir = repo.store.data_dir
    today = cn_today()
    emit = on_progress or _noop
    emit(_SIDECAR_PROMOTE_JOB_ID, 0, f"竞价提审 {today}: 对账 closed → 仅撮合行升 canonical…")

    result = auction_promote.promote_trading_day(repo, data_dir, [today])
    promoted = today.isoformat() in (result.get("promoted_dates") or [])
    entry = {
        "job": _SIDECAR_PROMOTE_JOB_ID,
        "trade_date": today.isoformat(),
        "requested": 1,
        "ok": 1 if promoted else 0,
        "failed_symbols": [],
    }
    if not promoted:
        skipped = result.get("skipped") or []
        reasons = [s.get("reason") if isinstance(s, dict) else str(s) for s in skipped]
        entry["reason"] = reasons[0] if reasons else "not_promoted"
    auction_sidecar_ledger.append_ledger(data_dir, entry)
    emit("done", 100, f"竞价提审完成: written={result.get('total_written', 0)}")
    return entry


def start_scheduler(repo: KlineRepository, capset: CapabilitySet) -> AsyncIOScheduler:
    """启动调度器。

    工作日 09:10 — 同步个股维表
    工作日 HH:MM — 盘后管道（时间由用户偏好决定，默认 15:30）
    工作日 HH:MM+5 — 盘后股池 EOD 持久化（管道完成后预生成冻结快照）
    """
    from app.services import preferences
    sched = preferences.get_pipeline_schedule()
    inst_sched = preferences.get_instruments_schedule()

    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")

    # 盘前: 同步 instruments（时间由偏好决定）
    def _instruments_task(on_progress=None):
        emit = on_progress or _noop
        emit("sync_instruments", 0, "同步个股维表…")
        result = run_instruments_sync(repo)
        emit("done", 100, f"个股维表同步完成,{result.get('instruments_rows', 0)} 只标的")
        return result


    scheduler.add_job(
        lambda: _run_tracked(_instruments_task, "instruments_sync"),
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=inst_sched["hour"], minute=inst_sched["minute"],
                            timezone="Asia/Shanghai"),
        id="pre_market_instruments",
        misfire_grace_time=1800,
        replace_existing=True,
    )

    # 盘后: 日 K + enriched（时间由偏好决定）
    def _pipeline_then_refresh(on_progress=None):
        # 与手动触发 (/api/pipeline/run) 对齐: 管道落盘后重建 Polars 内存缓存,
        # 否则 live_agg 的昨日连板数等基准列会停留在旧交易日, 次日开盘连板梯队
        # 整体少算一档 (仅手动触发或重启才会刷缓存, cron 调度路径此前漏了这步)。
        # 用 app.state 上的**实时** capset(周期重探会热更新它), 而非启动时捕获的
        # 旧 capset —— 否则 Key 中途过期/续费后, 调度管道仍按旧档位打端点。
        app_state = _get_app_state()
        capset_live = getattr(app_state, "capabilities", None) or capset
        # 管道运行期间暂停实时行情取数, 防止覆写同一批 parquet 竞态
        qs = getattr(app_state, "quote_service", None)
        try:
            if qs:
                with qs.paused():
                    result = run_now(repo, capset_live, on_progress=on_progress)
            else:
                result = run_now(repo, capset_live, on_progress=on_progress)
        finally:
            # 即便有阶段软失败(run_now 末尾抛 PipelineStageError), 已落盘的日K/enriched
            # 仍需刷进内存缓存, 否则 live_agg 基准列停留在旧交易日。放 finally 保证部分
            # 成功也生效; 随后异常继续上抛, 由 _run_tracked 标记任务 failed。
            repo.refresh_cache()
        return result

    scheduler.add_job(
        lambda: _scheduled_pipeline_task(_pipeline_then_refresh),
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=sched["hour"], minute=sched["minute"],
                            timezone="Asia/Shanghai"),
        id="daily_pipeline",
        misfire_grace_time=3600,
        replace_existing=True,
    )

    # 盘后: 股池 EOD 持久化 (管道完成 +5min, 每交易日预生成冻结快照)。
    # 复用 _run_tracked 单飞, 与手动 run_all 并发写防护 (T-22-02-01)。
    pool_minute = sched["minute"] + _POOL_EOD_OFFSET_MIN
    pool_hour = sched["hour"] + (pool_minute // 60)
    pool_minute %= 60

    scheduler.add_job(
        lambda: _run_tracked(_pool_eod_persist, "pool_eod_persist"),
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=pool_hour, minute=pool_minute,
                            timezone="Asia/Shanghai"),
        id=_POOL_EOD_JOB_ID,
        misfire_grace_time=3600,
        replace_existing=True,
    )

    # 盘前: 09:26 盘前预览 (PM-01) — 09:25 集合竞价撮合定盘后 / 09:30 连续竞价前。
    # 固定 09:26 (mon-fri, Asia/Shanghai); 独立存储 premarket_results/date={T}/part.json,
    # 绝不写 strategy_cache / screener_results。independent=True: 只按 label 去重且
    # 不占全局重任务槽 — 与同 09:26 竞价采集 (写 kline_auction 暂存) 写面不相交,
    # 两 job 并行合法 (互不挤占, 不再被全局单飞静默跳过; 与手动 run_all / EOD 的
    # 并发写防护不适用 — 预览零共享写面)。盘前窗口窄, misfire_grace_time 短于 EOD 的 3600。
    scheduler.add_job(
        lambda: _run_tracked(_premarket_pool_preview, "premarket_pool_preview",
                             independent=True),
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=_PREMARKET_HOUR, minute=_PREMARKET_MINUTE,
                            timezone="Asia/Shanghai"),
        id=_PREMARKET_JOB_ID,
        misfire_grace_time=1800,
        replace_existing=True,
    )

    # 盘中/盘后: 竞价采集 sidecar 三 job (SDC-01..03)。
    #   09:26 采集 — 与盘前预览同槽位不同 id (APScheduler 多 job 并发合法);
    #     fetch-on-miss 单次 GET 全窗口 → staging 原子写 + manifest (fail-closed:
    #     不完整 → 无分区, 不伪造);
    #   09:40 对账 — 09:30 bar 数据在场判定交易日 → 三重闭合 + 诚实门告警
    #     (auction_sidecar_capture_missing / auction_sidecar_reconcile_fail);
    #   EOD 15:40 提审 — 对账 closed → 仅 09:25 撮合行升 canonical (虚拟行永不入湖)。
    # 盘前窗口窄 (09:26/09:40), misfire_grace_time=1800 镜像 premarket 09:26 job;
    # EOD 后 15:40 宽窗口 3600。全部 _run_tracked 单飞 + replace_existing。
    scheduler.add_job(
        lambda: _run_tracked(_sidecar_capture, _SIDECAR_CAPTURE_JOB_ID),
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=_SIDECAR_CAPTURE_HOUR, minute=_SIDECAR_CAPTURE_MINUTE,
                            timezone="Asia/Shanghai"),
        id=_SIDECAR_CAPTURE_JOB_ID,
        misfire_grace_time=1800,
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _run_tracked(_sidecar_reconcile, _SIDECAR_RECONCILE_JOB_ID),
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=_SIDECAR_RECONCILE_HOUR, minute=_SIDECAR_RECONCILE_MINUTE,
                            timezone="Asia/Shanghai"),
        id=_SIDECAR_RECONCILE_JOB_ID,
        misfire_grace_time=1800,
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: _run_tracked(_sidecar_promote, _SIDECAR_PROMOTE_JOB_ID),
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=_SIDECAR_PROMOTE_HOUR, minute=_SIDECAR_PROMOTE_MINUTE,
                            timezone="Asia/Shanghai"),
        id=_SIDECAR_PROMOTE_JOB_ID,
        misfire_grace_time=3600,
        replace_existing=True,
    )

    # 盘后: 五档盘口 sealed 定版(时间由偏好决定, 默认15:02, 范围15:01~18:00)
    depth_sched = preferences.get_depth_finalize_time()

    def _depth_finalize():
        depth_svc = getattr(_get_app_state(), "depth_service", None) if _get_app_state() else None
        if depth_svc:
            depth_svc.finalize()

    scheduler.add_job(
        _depth_finalize,
        trigger=CronTrigger(day_of_week="mon-fri",
                            hour=depth_sched["hour"], minute=depth_sched["minute"],
                            timezone="Asia/Shanghai"),
        id="depth_finalize",
        misfire_grace_time=3600,
        replace_existing=True,
    )

    # 周期性能力重探: 付费 Key 中途过期/续费无需重启即可被发现。
    # 只热更新 app.state.capabilities(API 端点、盘后管道 _pipeline_then_refresh 均读它);
    # 档位变化记 WARNING, 让「Key 失效」在日志/前端可见, 不再静默按旧档位打 403 端点。
    def _reprobe_capabilities():
        from app.tickflow.policy import detect_capabilities, tier_label
        app_state = _get_app_state()
        if app_state is None:
            return
        try:
            old = getattr(app_state, "capabilities", None)
            old_n = len(old.all()) if old else -1
            new_capset = detect_capabilities(force=True)
            app_state.capabilities = new_capset
            new_n = len(new_capset.all())
            if old_n != new_n:
                logger.warning(
                    "能力集变化: %d → %d capabilities (档位=%s)。Key 过期/续费或端点波动, "
                    "已热更新 app.state.capabilities。", old_n, new_n, tier_label(),
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("周期能力重探失败(保留现有能力集): %s", e)

    scheduler.add_job(
        _reprobe_capabilities,
        trigger=IntervalTrigger(minutes=60),
        id="reprobe_capabilities",
        misfire_grace_time=600,
        replace_existing=True,
    )

    # 定时复盘 (AI 大盘复盘报告): 工作日到点自动生成并归档。
    # 默认关闭 —— 仅当用户在复盘页开启时才注册 job。
    # 复用 recap_market_once(非流式) + market_recap_reports.save_report(落盘)。
    # quote_service / depth_service 通过 _get_app_state() 延迟取用。
    review_sched = preferences.get_review_schedule()
    if review_sched["enabled"]:
        _register_review_job(scheduler, repo, review_sched["hour"], review_sched["minute"])
        logger.info("scheduled_review enabled @%02d:%02d mon-fri",
                    review_sched["hour"], review_sched["minute"])

    scheduler.start()
    logger.info("scheduler started; instruments@%02d:%02d, pipeline@%02d:%02d, depth@%02d:%02d mon-fri",
                inst_sched["hour"], inst_sched["minute"], sched["hour"], sched["minute"],
                depth_sched["hour"], depth_sched["minute"])
    return scheduler


# app_state 延迟引用(start_scheduler 在 lifespan 早期调用, app.state 可能还没就绪)
_app_state_ref = None


def set_app_state(app_state) -> None:
    """lifespan 注册 app.state 引用, 供 scheduled job 访问 depth_service 等单例。"""
    global _app_state_ref
    _app_state_ref = app_state


def _get_app_state():
    return _app_state_ref
