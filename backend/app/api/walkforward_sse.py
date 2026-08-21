"""Walk-forward SSE streaming endpoint (Phase 15, SC3).

Mirrors the durable ``_BacktestJob`` pattern in ``backtest.py``: a module-level
``_wf_jobs`` dict keyed by plan_id, progress history replayable on reconnect,
TTL cleanup, thread-safe.  A ``POST run`` simulates a walk-forward execution
(fold-by-fold progress recorded into the job); ``GET stream`` replays the
recorded history then pushes live events.

Zero-execution-UI gate: this module only streams progress — it never writes to
a live path.  The ``run`` endpoint records fold progress into the module-level
job state only.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/research/wf", tags=["research-panels"])


def _ws_broadcast(request: Request, channel: str, msg_type: str, data: dict) -> None:
    """Phase 55: WS 频道广播 walk-forward 事件到 run:{plan_id} 频道。"""
    from app.ws.broadcast import broadcast_from_thread

    ws_manager = getattr(request.app.state, "ws_manager", None)
    if ws_manager is None:
        return
    broadcast_from_thread(ws_manager, channel, msg_type, data)


class _WfJob:
    """One walk-forward job's state, kept module-level for reconnect replay.

    A job exists from the FIRST stream connect (idle placeholder, ``started``
    False) so a run started later lands in the SAME object every connected
    stream already holds — never a per-stream copy that would miss the run.
    """

    __slots__ = ("key", "progress", "result", "error", "done", "started", "created_ts", "finish_ts", "principal")

    def __init__(self, key: str):
        self.key = key
        self.progress: list[dict] = []   # fold progress history (replay on reconnect)
        self.result: dict | None = None
        self.error = None
        self.done = False
        self.started = False
        self.created_ts: float = time.time()
        self.finish_ts: float = 0.0
        self.principal: str | None = None  # T-55-02: 频道所有权验证


# Module-level job table: plan_id -> _WfJob
_wf_jobs: dict[str, _WfJob] = {}
_wf_jobs_lock = threading.Lock()
_WF_JOB_TTL = 300  # keep completed jobs for 5 minutes
_WF_IDLE_TTL = 300  # idle placeholders (connected stream, never run) also expire


def _cleanup_stale_wf_jobs() -> None:
    now = time.time()
    with _wf_jobs_lock:
        stale = [
            k
            for k, j in _wf_jobs.items()
            if (j.done and now - j.finish_ts > _WF_JOB_TTL)
            or (not j.started and now - j.created_ts > _WF_IDLE_TTL)
        ]
        for k in stale:
            _wf_jobs.pop(k, None)


def _job_key(plan_id: str, run_key: str | None) -> str:
    """Deterministic per-plan key so POST run and GET stream address the same job.

    A plan maps to one durable job (mirroring backtest's per-request key); a
    re-run after completion reuses the row.  ``run_key`` is reserved for
    future multi-run plans.
    """
    return f"wf:{plan_id}"


@router.post("/plans/{plan_id}/run")
async def run_walk_forward(request: Request, plan_id: str) -> dict:
    """Record a walk-forward execution and stream fold progress into the job.

    Simulates fold-by-fold progress (fold_index / total_folds / status / oos)
    recorded into the module-level job so the SSE endpoint can replay it.  In a
    production wiring this would drive the real Phase 13 walk-forward service;
    the SSE contract is identical.
    """
    _cleanup_stale_wf_jobs()
    key = _job_key(plan_id, None)

    with _wf_jobs_lock:
        job = _wf_jobs.get(key)
        if job is None:
            job = _WfJob(key)
            _wf_jobs[key] = job
        elif job.started and not job.done:
            raise HTTPException(status_code=409, detail="walk-forward already running for this plan")
        else:
            # Re-run after completion (or an idle placeholder a stream
            # registered earlier): the fresh run REPLACES the recorded
            # history.  Without this reset, a re-run's folds would append
            # after the first run's ``done`` event — every stream client
            # closes at the first ``done`` and the re-run never surfaces
            # (and a reconnect would replay stale history).
            job.progress.clear()
            job.done = False
            job.finish_ts = 0.0
            job.error = None
            job.result = None
        job.started = True

    total_folds = 5
    oos = total_folds - 1

    def _record() -> None:
        for fold in range(total_folds):
            is_oos = fold == oos
            job.progress.append({
                "type": "fold",
                "plan_id": plan_id,
                "fold_index": fold,
                "total_folds": total_folds,
                "is_oos": is_oos,
                "status": "running",
                "ts": time.time(),
            })
            time.sleep(0.05)
        job.progress.append({
            "type": "done",
            "plan_id": plan_id,
            "fold_index": total_folds,
            "total_folds": total_folds,
            "status": "completed",
            "ts": time.time(),
        })
        job.done = True
        job.finish_ts = time.time()
        job.result = {"plan_id": plan_id, "folds": total_folds, "oos": 1}

    # Record synchronously (small synthetic workload) so the test can read the
    # stream immediately; real runs would dispatch to a worker thread.
    await asyncio.to_thread(_record)

    return {"ok": True, "key": key, "plan_id": plan_id, "folds": total_folds, "oos": 1}


@router.get("/plans/{plan_id}/stream")
async def stream_walk_forward(request: Request, plan_id: str):
    """SSE stream: replay recorded fold progress, then push live events.

    Event types:
      - progress: {type: "fold", fold_index, total_folds, is_oos, status}
      - done: {type: "done", plan_id}
      - error: {message}
    """
    key = _job_key(plan_id, None)
    ws_channel = f"run:{plan_id}"

    def event_generator():
        _cleanup_stale_wf_jobs()
        with _wf_jobs_lock:
            job = _wf_jobs.get(key)
            if job is None:
                # No run has started for this plan yet — register a SHARED
                # idle placeholder so a later POST run records into the very
                # object this stream is already watching (a per-stream local
                # copy would never see the run's progress).
                job = _WfJob(key)
                _wf_jobs[key] = job

        cursor = 0
        try:
            while True:
                prog = list(job.progress)
                while cursor < len(prog):
                    msg = prog[cursor]
                    cursor += 1
                    if msg.get("type") == "done":
                        _ws_broadcast(request, ws_channel, "wf_done", msg)
                        yield f"event: done\ndata: {json.dumps(msg, ensure_ascii=False, default=str)}\n\n"
                        return
                    _ws_broadcast(request, ws_channel, "wf_progress", msg)
                    yield f"event: progress\ndata: {json.dumps(msg, ensure_ascii=False, default=str)}\n\n"

                if job.error is not None:
                    _ws_broadcast(request, ws_channel, "wf_error", {"message": job.error})
                    yield f"event: error\ndata: {json.dumps({'message': job.error})}\n\n"
                    return
                yield ": keepalive\n\n"
                time.sleep(0.5)
        except GeneratorExit:
            return

    return StreamingResponse(event_generator(), media_type="text/event-stream")
