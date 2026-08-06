"""批量回填服务 — 用户触发的历史快照补齐 (HIST-01)。

复用与 EOD / 手动 run_all 完全相同的 ``ScreenerService.run_all_with_hits`` +
``pool_snapshot.persist_point_snapshot`` 单条代码路径, 每个历史缺口日只落
``screener_results/date={d}/part.json`` (``origin="backfill"``), **绝不调
``strategy_cache.write_cache``** (single-as_of 最新指针, 历史日写入即污染)。

铁律 (HIST-01 / D2 / D5 / HIST-04.3):
- 日期集 = enriched 分区 − 含 part.json 的快照分区 (幂等跳过已快照日)。
- 升序处理 (D5) 摊销 150 日 warmup (screener._compute_enriched_full 慢路径)。
- 合作式取消 (D5): ``job_id`` 对应 job 状态为 ``failed`` → 提前停止。
- 失败日记录并继续 (HIST-04.3), 终态如实反映部分失败。
- 零新增运行时依赖; 只依赖 pool_snapshot / screener / pipeline_jobs。

本模块不 import 执行族模块 (broker/order/trade/execution/portfolio/position/
account/transaction) 与 ``strategy_cache`` — 保持平台一致性 (E1/E3 形)。
"""
from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)


def _noop(stage: str, pct: int, msg: str, **kwargs) -> None:  # noqa: ARG001
    pass


def run_pool_backfill(
    repo,
    engine=None,
    *,
    start: str | None = None,
    end: str | None = None,
    max_days: int | None = None,
    on_progress: Callable | None = None,
    job_id: str | None = None,
) -> dict:
    """批量回填历史缺口: 对每个缺口日 ``run_all_with_hits`` + ``persist_point_snapshot``。

    - 日期集 = ``list_backfill_gaps`` (enriched 分区 − 含 part.json 的快照分区,
      升序); ``start`` / ``end`` (ISO 字符串比较) 与 ``max_days`` 限界。
    - 对每目标日: ``svc.run_all_with_hits(d, engine=engine)`` +
      ``persist_point_snapshot(d, origin="backfill")``。
    - 铁律 (ARCHIVE R1 / D2): **绝不调 strategy_cache.write_cache** — 防污染
      single-as_of 最新指针。
    - 合作式取消 (D5): ``job_id`` 非 None 且对应 job 状态为 ``failed`` → 提前停止。
    - 失败日记录 ``failed_dates`` 并继续 (HIST-04.3); 终态如实反映部分失败。

    Returns:
        ``{"requested": N, "backfilled": N, "failed": N, "failed_dates": [...],
        "origin": "backfill"}`` — requested 为本次限界后的目标缺口数。
    """
    from datetime import date, datetime

    from app.services import pool_snapshot
    from app.services.pipeline_jobs import job_store
    from app.services.screener import ScreenerService

    emit = on_progress or _noop
    svc = ScreenerService(repo)
    data_dir = repo.store.data_dir

    dates = pool_snapshot.list_backfill_gaps(data_dir)
    if start:
        dates = [d for d in dates if d >= start]
    if end:
        dates = [d for d in dates if d <= end]
    if max_days is not None and max_days > 0:
        dates = dates[:max_days]
    if not dates:
        return {
            "requested": 0,
            "backfilled": 0,
            "failed": 0,
            "failed_dates": [],
            "origin": "backfill",
        }

    fingerprint = (
        pool_snapshot.strategy_fingerprint(engine) if engine is not None else "unknown"
    )
    backfilled, failed, failed_dates = 0, 0, []
    emit("pool_backfill", 0, f"回填缺口 {len(dates)} 日…")
    for i, ds in enumerate(dates):
        # 合作式取消 (D5): 前置 job 状态为 failed → 提前停止 (不处理后续日)
        if job_id is not None:
            j = job_store.get(job_id)
            if j is None or j["status"] == "failed":
                emit("done", 100, "回填被取消")
                break
        try:
            results = svc.run_all_with_hits(date.fromisoformat(ds), engine=engine)
            if results:
                # 只落冻结快照, origin="backfill"; 绝不 write_cache (HIST-01.3 / D2)
                pool_snapshot.persist_point_snapshot(
                    data_dir,
                    ds,
                    results,
                    strategy_version=fingerprint,
                    computed_at=datetime.now().isoformat(timespec="seconds"),
                    origin="backfill",
                )
                backfilled += 1
        except Exception as e:  # noqa: BLE001 — 失败日记录并继续 (HIST-04.3)
            logger.exception("pool backfill %s failed: %s", ds, e)
            failed += 1
            failed_dates.append(ds)
        emit(
            "pool_backfill",
            int(100 * (i + 1) / len(dates)),
            f"回填 {ds} ({i + 1}/{len(dates)}, 成功 {backfilled}, 失败 {failed})",
        )
    emit("done", 100, f"回填完成: {backfilled} 成功, {failed} 失败")
    return {
        "requested": len(dates),
        "backfilled": backfilled,
        "failed": failed,
        "failed_dates": failed_dates,
        "origin": "backfill",
    }
