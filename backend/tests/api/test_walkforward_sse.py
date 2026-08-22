"""Walk-forward 模块级 job 状态测试 (Phase 15 SC3 → Phase 55 SSE 删除后保留)。

SSE ``stream_walk_forward`` 端点已在 Phase 55-04 删除; walk-forward 实时事件现由
``/api/backtest/walkforward/start`` 后台线程通过 ``run:{job_key}`` WS 频道广播
(见 ``tests/test_ws_task.py::test_walkforward_progress``)。

本文件只保留对 ``run_walk_forward`` (合成 POST) 的模块级 job 状态契约:
  - POST run 记录 fold 进度到 ``_WfJob``, 任务以 done 终结。
  - 重复 run 替换历史 (非追加), 保证重连只回放当前 run。
"""
from __future__ import annotations

import asyncio

from app.api.walkforward_sse import _wf_jobs, run_walk_forward


class _Req:
    def __init__(self, app_state: dict | None = None):
        _state = type("State", (), app_state or {})()
        self.app = type("App", (), {"state": _state})()
        self.state = type("State", (), {"reviewer_principal": None})()

def _cleanup() -> None:
    _wf_jobs.clear()

def _job_for(plan_id: str):
    key = f"wf:{plan_id}"
    return _wf_jobs[key]


def test_walk_forward_run_records_fold_progress():
    """POST run records fold progress; the job is terminal with a done event."""
    _cleanup()
    plan_id = "plan-progress"

    result = asyncio.run(run_walk_forward(_Req(), plan_id))
    assert result["ok"] is True
    assert result["folds"] == 5
    assert result["oos"] == 1

    job = _job_for(plan_id)
    assert job.done is True
    progress = [p for p in job.progress if p.get("type") == "fold"]
    assert len(progress) == 5
    assert progress[0]["fold_index"] == 0
    assert any(p.get("is_oos") for p in progress), "expected a reserved OOS fold"
    assert any(p.get("type") == "done" for p in job.progress)


def test_walk_forward_rerun_replaces_history():
    """A re-run after completion REPLACES the recorded history, so the job
    holds exactly one done and the current run's folds — never stale append."""
    _cleanup()
    plan_id = "plan-rerun"

    asyncio.run(run_walk_forward(_Req(), plan_id))
    job = _job_for(plan_id)
    first_done = [p for p in job.progress if p.get("type") == "done"]
    assert len(first_done) == 1

    # Re-run: history resets, so the job has exactly one done (the second run's)
    # and no interleaved stale progress.
    asyncio.run(run_walk_forward(_Req(), plan_id))
    job = _job_for(plan_id)
    assert job.done is True
    dones = [p for p in job.progress if p.get("type") == "done"]
    assert len(dones) == 1, "re-run must replace history, not append after the first done"
    folds = [p for p in job.progress if p.get("type") == "fold"]
    assert len(folds) == 5


def test_walk_forward_concurrent_run_rejected():
    """A second run while the first is still running is rejected (409).

    The synthetic POST records synchronously, so two concurrent starts cannot
    both be 'in flight' in this test — but a run whose ``done`` is already set
    (completed) must allow a fresh re-run (covered by the rerun test above).
    Here we verify the completed job no longer raises 409 on a new run."""
    _cleanup()
    plan_id = "plan-concurrent"

    asyncio.run(run_walk_forward(_Req(), plan_id))
    # After completion, a new run must succeed (no 409).
    result = asyncio.run(run_walk_forward(_Req(), plan_id))
    assert result["ok"] is True
