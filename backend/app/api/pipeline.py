"""盘后管道 API — 异步触发 + 进度跟踪。"""
from __future__ import annotations

import asyncio
import concurrent.futures as _cf
import logging
import re
from datetime import date as date_type

from fastapi import APIRouter, HTTPException, Request

from app.jobs import daily_pipeline
from app.services.pipeline_jobs import job_store, release_run_slot, try_acquire_run_slot
from app.api.data import invalidate_storage_cache

# 长时间任务专用线程池（隔离于 FastAPI 默认线程池，防止阻塞请求处理）
_long_task_executor = _cf.ThreadPoolExecutor(max_workers=2, thread_name_prefix="long-task")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

@router.get("/phase1-fixture")
def phase1_fixture_status(request: Request) -> dict:
    """Return the isolated fixture-sync report; unavailable in normal runtime."""
    report = getattr(request.app.state, "phase1_fixture_sync", None)
    if report is None:
        raise HTTPException(status_code=404, detail="not found")
    return report



@router.post("/run")
async def run_now(request: Request) -> dict:
    """异步触发盘后管道,立即返回 job_id。客户端轮询 /jobs/{id} 拿进度。

    若已有任务在跑,**返回该任务 id 而不是开新任务**(防止并发拉数据撞限流)。
    但如果该任务已运行超过 10 分钟 (可能因 reload 卡死), 强制标记为失败后重新创建。
    """
    repo = request.app.state.repo
    capset = request.app.state.capabilities

    # 检测卡死的 running job (如 reload 后孤儿 task / 网络读无限阻塞)。
    # reap_stale 会在 /run 和 /jobs/{id} 轮询端点都调用,保证卡死后能自愈。
    job_store.reap_stale()

    # 单飞: 复用任何活跃 (pending∨running) 任务, is_new=False 时不再调度新任务
    job_id, is_new = job_store.create()
    if not is_new:
        return {"job_id": job_id, "reused": True}

    # 在 executor 里跑同步任务(pipeline 内部都是阻塞 IO + CPU)
    async def task() -> None:
        # 重任务执行槽: 防僵尸并发(reap 后线程仍活时新任务不得并行写 parquet)
        if not try_acquire_run_slot():
            job_store.fail(job_id, "已有数据任务在运行(或上一次任务卡死未结束),请稍后再试")
            return
        # 管道运行期间暂停实时行情取数, 防止覆写同一批 parquet 竞态
        qs = getattr(request.app.state, "quote_service", None)
        try:
            job_store.start(job_id)
            loop = asyncio.get_event_loop()

            def progress(stage: str, pct: int, msg: str, stage_pct: int | None = None,
                         skip_log: bool = False) -> None:
                job_store.progress(job_id, stage, pct, msg, stage_pct=stage_pct, skip_log=skip_log)

            def _run() -> dict:
                if qs:
                    with qs.paused():
                        return daily_pipeline.run_now(repo, capset, on_progress=progress)
                return daily_pipeline.run_now(repo, capset, on_progress=progress)

            result = await loop.run_in_executor(_long_task_executor, _run)
            job_store.succeed(job_id, result)
            invalidate_storage_cache()
            repo.refresh_cache()  # 刷新 Polars 缓存
        except Exception as e:  # noqa: BLE001
            logger.exception("pipeline failed")
            job_store.fail(job_id, str(e))
            invalidate_storage_cache()
        finally:
            release_run_slot()

    asyncio.create_task(task())
    return {"job_id": job_id, "reused": False}


@router.post("/backfill")
async def pool_backfill(request: Request) -> dict:
    """批量回填历史股池缺口 — 用户触发, 后台 job, 立即返回 job_id。

    body: ``{ "max_days": int|None, "start": "YYYY-MM-DD"|None, "end": "YYYY-MM-DD"|None }``

    - 运营操作 (写研究快照), **绝不放 /api/pool/*** (POOL-03 E4 GET-only 守卫)。
    - 单飞 (``job_store.create`` pending∨running 去重) + 重任务执行槽互斥
      (``try_acquire_run_slot``, 与 EOD/手动 run_all 并发防护) + 后台 executor
      (``_long_task_executor``, 请求内零阻塞)。
    - 进度经既有 ``GET /api/pipeline/jobs/{id}`` 轮询; 取消经既有
      ``POST /api/pipeline/jobs/{id}/cancel`` (合作式, 每日期查 job 状态)。
    """
    body = await request.json()
    start = body.get("start")
    end = body.get("end")
    max_days = body.get("max_days")

    # 参数校验 (Pitfall 4 / T-24-01-01/02): 防路径穿越与无界长任务
    for name, v in (("start", start), ("end", end)):
        if v is not None:
            if not isinstance(v, str) or not re.fullmatch(r"^\d{4}-\d{2}-\d{2}$", v):
                raise HTTPException(status_code=400, detail=f"{name} 必须为 YYYY-MM-DD")
            try:
                date_type.fromisoformat(v)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"{name} 不是合法日期") from None
    if start and end and str(start) > str(end):
        raise HTTPException(status_code=400, detail="start 不能晚于 end")
    if max_days is not None:
        if (
            not isinstance(max_days, int)
            or isinstance(max_days, bool)
            or not (0 < max_days <= 500)
        ):
            raise HTTPException(status_code=400, detail="max_days 必须为 1~500 的整数")

    repo = request.app.state.repo
    engine = getattr(request.app.state, "strategy_engine", None)

    from app.services.pool_backfill import run_pool_backfill
    from app.services.pipeline_jobs import job_store, release_run_slot, try_acquire_run_slot

    job_store.reap_stale()
    # 单飞: 复用任何活跃 (pending∨running) 任务, is_new=False 时不再调度新任务
    job_id, is_new = job_store.create()
    if not is_new:
        return {"status": "reused", "job_id": job_id}

    async def task() -> None:
        # 重任务执行槽: 与 EOD/手动 run_all 并发写同一 date={d} 分区防护
        if not try_acquire_run_slot():
            job_store.fail(job_id, "已有数据任务在运行(或上一次任务卡死未结束),请稍后再试")
            return
        loop = asyncio.get_event_loop()

        def progress(stage: str, pct: int, msg: str, stage_pct: int | None = None,
                     skip_log: bool = False) -> None:
            job_store.progress(job_id, stage, pct, msg, stage_pct=stage_pct, skip_log=skip_log)

        try:
            job_store.start(job_id)
            result = await loop.run_in_executor(
                _long_task_executor,
                lambda: run_pool_backfill(
                    repo, engine, start=start, end=end, max_days=max_days,
                    on_progress=progress, job_id=job_id,
                ),
            )
            job_store.succeed(job_id, result)
        except Exception as e:  # noqa: BLE001
            logger.exception("pool backfill failed: job_id=%s", job_id)
            job_store.fail(job_id, str(e))
        finally:
            release_run_slot()

    asyncio.create_task(task())
    return {"status": "started", "job_id": job_id}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    # 每次轮询都检查卡死 job — 前端每秒轮询,STALE_JOB_TIMEOUT_S(10min)后必定自愈,
    # 无需用户再次手动点「同步」。
    job_store.reap_stale()
    j = job_store.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    return j


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    """手动取消一个 running 的 job。"""
    j = job_store.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    if j["status"] not in ("running", "pending"):
        raise HTTPException(status_code=400, detail=f"job status is {j['status']}, cannot cancel")
    job_store.fail(job_id, "用户手动取消")
    return {"cancelled": job_id}


@router.get("/jobs")
def list_jobs(limit: int = 20) -> dict:
    return {
        "active_id": job_store.active_id(),
        "jobs": job_store.list_recent(limit=limit),
    }
