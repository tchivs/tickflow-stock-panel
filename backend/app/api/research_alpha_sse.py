"""Durable Last-Event-ID stream over the monotonic Alpha event ledger (SC1).

Phase 50-01 (AF-REQ-18).  Phase 55 D-03 removed the SSE endpoint; this module
now provides only the durable-ledger cursor generator (``_stream_events``)
for WS request_dispatcher consumption.

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
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServerSentEvent:
    """Lightweight SSE event container (sse-starlette dependency removed, Phase 55 D-03).

    Preserves the .data/.event/.id/.comment attributes that the durable-ledger
    cursor generator yields; consumed by the WS request_dispatcher and tests.
    """
    data: str | None = None
    event: str | None = None
    id: str | None = None
    comment: str | None = None

from app.research import projections
from app.research.run_contract import TERMINAL_STATUSES
from app.research.run_service import ResearchRunService

router = APIRouter(prefix="/api/research/alpha", tags=["research-alpha-sse"])

_PAGE = 500  # bounded page size for the durable-ledger poll (limits in-flight rows)
_POLL_INTERVAL = 1.0  # seconds between empty-poll keepalives


def _ws_broadcast(request: Request, channel: str, msg_type: str, data: dict) -> None:
    """Phase 55: WS 频道广播 alpha 事件到 run:{run_id} 频道。"""
    from app.ws.broadcast import broadcast_from_thread

    ws_manager = getattr(request.app.state, "ws_manager", None)
    if ws_manager is None:
        return
    broadcast_from_thread(ws_manager, channel, msg_type, data)


def _safe_seq(raw: str | None) -> int:
    """解析 SSE id (seq) 为 int, 非法回退 0。"""
    if raw is None:
        return 0
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return 0


def _parse_sse_data(raw: str) -> dict:
    """解析 SSE data JSON 为 dict, 解析失败回退空 dict。"""
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


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


