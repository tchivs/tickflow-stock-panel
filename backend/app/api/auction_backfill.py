"""AQ-02 竞价历史回填触发端点 — POST /api/kline/auction/backfill。

运营操作 (写 kline_auction 湖), 独立模块独立 router —— **绝不放
api/auction_history.py** (POOL-03 GET-only 守卫, 本模块只做触发不做读聚合)。
镜像 api/pipeline.py:90-166 的端点生命周期: 参数校验 (Pitfall 4 防路径穿越/
无界长任务) → 单飞 (``job_store.create`` pending∨running 去重) → 重任务执行槽
(``try_acquire_run_slot``, 与 EOD/手动 run_all 并发写防护, R7) → 后台 executor
(``_long_task_executor``, 请求内零阻塞) → ``succeed/fail`` → ``invalidate_storage_cache``。

进度经既有 ``GET /api/pipeline/jobs/{id}`` 轮询 (stage ``auction_backfill``);
取消经既有 ``POST /api/pipeline/jobs/{id}/cancel`` (合作式, 每 symbol 查 job 状态)。
零执行族 import (broker/order/trade/execution/portfolio/position/account/
transaction) —— 32-03 AST 守卫目标。
"""
from __future__ import annotations

import asyncio
import concurrent.futures as _cf
import logging
import re
from datetime import date as date_type

from fastapi import APIRouter, HTTPException, Request

from app.api.auction_history import _SYMBOL_RE
from app.api.data import invalidate_storage_cache
from app.services.pipeline_jobs import job_store, release_run_slot, try_acquire_run_slot

# 长时间任务专用线程池 (隔离于 FastAPI 默认线程池, 镜像 pipeline.py:17)
_long_task_executor = _cf.ThreadPoolExecutor(max_workers=2, thread_name_prefix="long-task")

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/kline/auction", tags=["kline"])

# symbols 子集上限 (防无界长任务, T-32-02-02)
_MAX_SYMBOLS = 6000


@router.post("/backfill")
async def auction_backfill(request: Request) -> dict:
    """异步触发竞价历史回填, 立即返回 job_id; 客户端轮询 /api/pipeline/jobs/{id}。

    body: ``{"symbols": list|null, "start": "YYYY-MM-DD"|null, "end": "YYYY-MM-DD"|null,
    "rpm": int|30|null, "only_missing": bool|false|null}`` → ``{"status": "started"|"reused",
    "job_id": "..."}``。

    - 校验 (镜像 pipeline.py:104-122): 日期 ``^\\d{4}-\\d{2}-\\d{2}$`` +
      ``date.fromisoformat``; ``start <= end``; rpm int 且非 bool, 1..60; symbols
      可选, 每项 ``_SYMBOL_RE`` fullmatch (``^\\d{6}\\.(SH|SZ|BJ)$``), 上限
      ``_MAX_SYMBOLS``; only_missing 必须为 bool。非法一律 400 (防路径穿越 /
      注入 / 无界长任务)。
    - 单飞: 复用任何活跃 (pending∨running) 任务, ``is_new=False`` 时不再调度新任务。
    - FA-01 超时豁免: ``create(timeout_s=21600)`` (6h) —— 全量回填实测 3.5-5.5h,
      缺省 600s 自愈回收不再误杀; 合作式取消不变 (每 symbol 查 job 状态)。
    - FA-02: ``only_missing`` 透传服务层, 覆盖预扫描跳过已全覆盖标的 (顶补续跑)。
    - 重任务槽: ``try_acquire_run_slot`` 失败 (运行中的 pool backfill / EOD) →
      job fail 记录 ``"已有数据任务在运行"`` (R7 同族重任务互斥, 正确且有意)。
    - 后台执行: ``_long_task_executor`` 线程池跑 ``run_auction_backfill``;
      succeed 后 ``invalidate_storage_cache()`` 清读缓存 (镜像 pipeline run_now)。
    """
    body = await request.json()
    symbols = body.get("symbols")
    start = body.get("start")
    end = body.get("end")
    rpm = body.get("rpm", 30)
    only_missing = body.get("only_missing", False)

    # 参数校验 (Pitfall 4 / T-32-02-01/02): 防路径穿越与无界长任务
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
    if not isinstance(rpm, int) or isinstance(rpm, bool) or not (1 <= rpm <= 60):
        raise HTTPException(status_code=400, detail="rpm 必须为 1~60 的整数")
    if not isinstance(only_missing, bool):
        raise HTTPException(status_code=400, detail="only_missing 必须为布尔值")
    if symbols is not None:
        if not isinstance(symbols, list) or not all(isinstance(s, str) for s in symbols):
            raise HTTPException(status_code=400, detail="symbols 必须为字符串数组")
        if len(symbols) > _MAX_SYMBOLS:
            raise HTTPException(status_code=400, detail=f"symbols 最多 {_MAX_SYMBOLS} 个")
        for s in symbols:
            if not _SYMBOL_RE.fullmatch(s):
                raise HTTPException(status_code=400, detail=f"非法 symbol: {s}")

    repo = request.app.state.repo

    from app.services.auction_backfill import run_auction_backfill

    job_store.reap_stale()
    # 单飞: 复用任何活跃 (pending∨running) 任务, is_new=False 时不再调度新任务
    # FA-01: 6h 豁免覆盖实测 3.5-5.5h 全量回填 + 裕量; 缺省 600s 自愈回收对
    # EOD/手动 run_all (分钟级) 语义不变 —— 池回填 /run 与管道 /run 端点不传。
    job_id, is_new = job_store.create(timeout_s=21600)
    if not is_new:
        return {"status": "reused", "job_id": job_id}

    async def task() -> None:
        # 重任务执行槽: 与 EOD/手动 run_all/pool backfill 并发写防护 (R7)
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
                lambda: run_auction_backfill(
                    repo, symbols=symbols, start=start, end=end, rpm=rpm,
                    only_missing=only_missing,
                    on_progress=progress, job_id=job_id,
                ),
            )
            job_store.succeed(job_id, result)
            invalidate_storage_cache()
        except Exception as e:  # noqa: BLE001
            logger.exception("auction backfill failed: job_id=%s", job_id)
            job_store.fail(job_id, str(e))
        finally:
            release_run_slot()

    asyncio.create_task(task())
    return {"status": "started", "job_id": job_id}
