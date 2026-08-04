"""Walk-forward SSE endpoint tests (Phase 15, SC3).

Verifies the durable-job SSE contract by calling the endpoint functions
directly (mirroring tests/backtest/test_optimizer_api.py): POST run records
fold progress into the module-level job; GET stream replays the recorded
history then emits a terminal ``done`` event.

The shared-stream fan-out (optimization/plan updates) is covered by the
portfolio panel tests asserting quote_service.notify_quote fires on paper
approve/reject (see test_portfolio_panels.py::test_paper_approve_fans_out).
"""
from __future__ import annotations

import asyncio

from app.api.walkforward_sse import _wf_jobs, stream_walk_forward, run_walk_forward


class _Req:
    def __init__(self, app_state: dict | None = None):
        self.app = type("App", (), {"state": type("State", (), app_state or {})})()


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


def test_walk_forward_stream_replays_history_then_done():
    """GET stream replays recorded fold events, then emits done and closes."""
    _cleanup()
    plan_id = "plan-replay"

    asyncio.run(run_walk_forward(_Req(), plan_id))
    async def _stream():
        response = await stream_walk_forward(_Req(), plan_id)
        parts: list[str] = []
        async for chunk in response.body_iterator:
            parts.append(chunk if isinstance(chunk, str) else chunk.decode("utf-8", errors="replace"))
        return "".join(parts)

    text = asyncio.run(_stream())
    assert "event: progress" in text, "expected replayed fold progress events"
    assert "event: done" in text, "expected terminal done event"
    assert '"is_oos": true' in text, "expected the reserved OOS fold labeled distinctly"


def test_walk_forward_stream_unknown_plan_emits_keepalive_then_replays_after_run():
    """Reconnect contract: an idle stream keeps alive; after run it replays."""
    _cleanup()
    plan_id = "plan-reconnect"

    async def _first_read():
        response = await stream_walk_forward(_Req(), plan_id)
        iterator = response.body_iterator.__aiter__()
        chunk = await asyncio.wait_for(iterator.__anext__(), timeout=3)
        return chunk if isinstance(chunk, str) else chunk.decode("utf-8", errors="replace")

    first = asyncio.run(_first_read())
    assert ": keepalive" in first, "expected keepalive comment while idle"

    asyncio.run(run_walk_forward(_Req(), plan_id))

    async def _second_read():
        response = await stream_walk_forward(_Req(), plan_id)
        parts: list[str] = []
        async for chunk in response.body_iterator:
            parts.append(chunk if isinstance(chunk, str) else chunk.decode("utf-8", errors="replace"))
        return "".join(parts)

    second = asyncio.run(_second_read())
    assert "event: progress" in second
    assert "event: done" in second


