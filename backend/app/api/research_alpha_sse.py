"""Durable Last-Event-ID SSE stream over the monotonic Alpha event ledger (SC1).

Phase 50-01 (AF-REQ-18).  This module is a NEW sibling of ``research_alpha.py``
(Phase 45 explicitly defers SSE to Phase 50 — ``test_phase45_guard.py:198-206``
asserts ``StreamingResponse``/``text/event-stream`` absent from
``research_alpha.py``; that assertion stays GREEN unamended because this file
is out of its module scope).

Design — the decisive difference from ``walkforward_sse.py``:

* **Zero module-level mutable state.**  The cursor is recovered from the
  durable SQLite ledger via the ``Last-Event-ID`` request header (native
  ``EventSource`` sends it on every reconnect), NOT from a module-level dict.
  A server restart mid-stream resumes exactly where the client's last-
  acknowledged ``seq`` left off.
* **Read-only.**  The generator calls only ``service.list_events`` +
  ``service.get``; it writes nothing.  Writes still flow exclusively through
  ``run_service`` (the sole lifecycle writer).
* **Terminal termination.**  When the run reaches a terminal status
  (``completed``/``failed``/``cancelled``/``preflight_failed``) the stream
  emits a ``terminal`` event and stops polling.
* **Bounded polling fallback.**  ``GET /runs/{id}/progress`` and
  ``GET /runs/{id}/events?after_sequence=`` remain the bounded-poll path
  (SC1 is "SSE *or* bounded polling").
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request
from sse_starlette import EventSourceResponse, ServerSentEvent

from app.research import projections
from app.research.run_contract import TERMINAL_STATUSES
from app.research.run_service import ResearchRunService

router = APIRouter(prefix="/api/research/alpha", tags=["research-alpha-sse"])

_PAGE = 500  # bounded page size for the durable-ledger poll (limits in-flight rows)
_POLL_INTERVAL = 1.0  # seconds between empty-poll keepalives


def _service(request: Request) -> ResearchRunService:
    """Resolve the shared run service from ``app.state`` (mirrors research_alpha)."""
    service = getattr(request.app.state, "research_run_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="research run service not initialized")
    return service


def _principal(request: Request) -> str:
    """Resolve the server-owned principal (the only identity source, T-45-12)."""
    principal = getattr(request.state, "reviewer_principal", None)
    if not isinstance(principal, str) or not principal:
        raise HTTPException(status_code=401, detail="authenticated principal required")
    return principal


def _parse_last_event_id(raw: str | None) -> int:
    """Resolve the cursor from the ``Last-Event-ID`` header (resume from k).

    Native ``EventSource`` sends ``Last-Event-ID: <seq>`` on every reconnect.
    If present and a valid non-negative int ``k``, start from ``after_seq = k``
    (the client's last-acknowledged seq); else ``after_seq = 0``.
    """
    if raw is None:
        return 0
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


async def _stream_events(
    service: ResearchRunService,
    run_id: str,
    principal: str,
    cursor: int,
    *,
    page: int = _PAGE,
    poll_interval: float = _POLL_INTERVAL,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncIterator[ServerSentEvent]:
    """Durable-ledger cursor generator — zero module-level state (SC1).

    Polls ``service.list_events(run_id, after_seq=cursor, limit=page)`` from the
    append-only monotonic ledger, emits one ``ServerSentEvent`` per row with
    ``id=<seq>`` + ``event=<event_type>``, advances ``cursor = last_seq``,
    emits a ``: ping`` keepalive on empty polls, and TERMINATES on a terminal
    run status.  The cursor is recovered purely from the durable ledger +
    ``Last-Event-ID`` — a restart resumes exactly where the client left off.
    """
    while True:
        if is_disconnected is not None and await is_disconnected():
            return
        events = service.list_events(
            run_id, principal=principal, after_seq=cursor, limit=page,
        )
        if events:
            for event in events:
                cursor = int(event["seq"])
                yield ServerSentEvent(
                    data=json.dumps(projections.event(event)),
                    event=str(event["event_type"]),
                    id=str(cursor),
                )
            continue  # drain the next page immediately (bounded in-flight)
        # Empty poll: check terminal status, then keepalive.
        current = service.get(run_id, principal=principal)
        if current is not None and current["status"] in TERMINAL_STATUSES:
            yield ServerSentEvent(
                data=json.dumps({"status": current["status"], "run_id": run_id}),
                event="terminal",
                id=str(cursor),
            )
            return
        yield ServerSentEvent(comment="ping")
        await asyncio.sleep(poll_interval)


@router.get("/runs/{run_id}/stream")
async def stream_run_events(request: Request, run_id: str) -> EventSourceResponse:
    """Durable ``Last-Event-ID`` SSE stream over the monotonic event ledger.

    Resumes from the client's last-acknowledged ``seq`` on reconnect/restart,
    holds no module-level state, and terminates on terminal run status.  The
    bounded-poll fallback (``GET /progress``, ``GET /events?after_sequence=``)
    remains available.
    """
    service = _service(request)
    principal = _principal(request)
    run = service.get(run_id, principal=principal)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    cursor = _parse_last_event_id(request.headers.get("last-event-id"))
    return EventSourceResponse(
        _stream_events(
            service, run_id, principal, cursor,
            is_disconnected=request.is_disconnected,
        ),
        # The generator owns the keepalive cadence; disable the library's
        # automatic ping so the two never compete.
        ping=None,
    )
