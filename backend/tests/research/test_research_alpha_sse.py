"""Phase 50-01-04 — durable Last-Event-ID SSE stream over the monotonic ledger.

Covers SC1 (AF-REQ-18):
  * Fresh connect emits every ledger event from seq 1 in order (id=<seq>).
  * ``Last-Event-ID: k`` reconnect resumes from seq k+1 (no dup, no gap).
  * Restart resume: a fresh service instance (zero module state) + Last-Event-ID
    resumes from k+1 — the cursor is recovered purely from the durable ledger.
  * Terminal status terminates the stream with a ``terminal`` event.
  * Keepalive (``: ping``) on empty polls.
  * Zero module-level mutable state.
  * The generator writes nothing — only ``list_events`` + ``get``.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import research_alpha_sse
from app.api.research_alpha_sse import _parse_last_event_id, _stream_events
from app.research.repository import ResearchRepository
from app.research.run_contract import freeze_input_snapshot
from app.research.run_service import ResearchRunService
from tests.research.conftest import DeterministicClock

_PRINCIPAL = "researcher@example.com"


# ---------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------


def _manifest(*, seed: int = 42) -> dict[str, Any]:
    return {
        "dsl": {"version": "factor-dsl-v1"},
        "grammar": {"fingerprint": "a" * 64, "version": "grammar-v1"},
        "vocabulary": {"fingerprint": "b" * 64, "size": 64},
        "policy": {"version": "admission-v1", "thresholds": {"min_ic": 0.02}},
        "budgets": {"max_expressions": 1000, "max_candidates": 200},
        "objective": {"name": "sharpe", "direction": "maximize"},
        "universe": {"name": "cn-a-share", "asset_type": "stock", "membership_fingerprint": "c" * 64},
        "measured_window": {"start": "2020-01-01", "end": "2023-12-31", "calendar": "SSE"},
        "fold_geometry": {"train_size": 120, "gap_size": 5, "test_size": 20, "n_folds": 10},
        "code_manifest": {"fingerprint": "d" * 64, "build_fingerprint": "e" * 64, "dependency_fingerprint": "f" * 64},
        "data_manifest": {"fingerprint": "g" * 64, "partition_fingerprint": "h" * 64},
        "seed": seed,
    }


def _make_run(
    repo: ResearchRepository, clock: DeterministicClock, *, run_id: str,
) -> dict[str, Any]:
    snapshot = freeze_input_snapshot(manifest=_manifest(), created_at=clock.now_iso())
    clock.advance()
    return repo.create_alpha_run(
        run_id=run_id, principal=_PRINCIPAL,
        idempotency_key=f"idem-{run_id}", snapshot=snapshot,
        event_id=f"aevt-{run_id}",
    )


def _make_terminal_run(
    repo: ResearchRepository, clock: DeterministicClock, *, run_id: str,
    extra_events: int = 0,
) -> str:
    """Create a run, start it, append optional events, then complete it."""
    run = _make_run(repo, clock, run_id=run_id)
    service = ResearchRunService(repo)
    started = service.start_or_resume(
        run["id"], principal=_PRINCIPAL, expected_version=run["transition_version"],
    )
    assert started is not None
    for i in range(extra_events):
        service.append_event(
            run_id=run["id"], principal=_PRINCIPAL,
            event_type="candidate_appended", entity_kind="candidate",
            entity_id=f"cand-{i}", idempotency_key=f"evt-{run_id}-{i}",
            actor="worker", source="adapter", payload={"ordinal": i},
        )
    completed = service.transition(
        run["id"], principal=_PRINCIPAL,
        from_status="running", to_status="completed",
        expected_version=started["transition_version"],
    )
    assert completed is not None
    return run["id"]


@pytest.fixture
def sse_client(
    tmp_path: Path, deterministic_clock: DeterministicClock,
) -> TestClient:
    repository = ResearchRepository(
        tmp_path / "op.db", clock=deterministic_clock, artifact_root=tmp_path / "art",
    )
    repository.migrate()
    app = FastAPI()

    @app.middleware("http")
    async def inject_test_principal(request, call_next):
        principal = request.headers.get("X-Test-Principal")
        if principal:
            request.state.reviewer_principal = principal
        return await call_next(request)

    app.state.research_run_service = ResearchRunService(repository)
    app.include_router(research_alpha_sse.router)
    client = TestClient(app)
    client._repo = repository  # type: ignore[attr-defined]
    client._clock = deterministic_clock  # type: ignore[attr-defined]
    return client


def _parse_sse(text: str) -> list[dict[str, str]]:
    """Parse SSE-formatted text into a list of event dicts."""
    events: list[dict[str, str]] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        entry: dict[str, str] = {}
        for line in block.split("\n"):
            if line.startswith(":"):
                entry["comment"] = line[1:].strip()
            elif ":" in line:
                field, _, value = line.partition(":")
                # SSE spec: a leading space after the colon is stripped.
                entry[field] = value[1:] if value.startswith(" ") else value
        events.append(entry)
    return events


# ---------------------------------------------------------------------
# Last-Event-ID parsing
# ---------------------------------------------------------------------


class TestParseLastEventId:
    def test_none_returns_zero(self) -> None:
        assert _parse_last_event_id(None) == 0

    def test_valid_int(self) -> None:
        assert _parse_last_event_id("5") == 5

    def test_negative_clamped_to_zero(self) -> None:
        assert _parse_last_event_id("-3") == 0
    def test_invalid_falls_back_to_zero(self) -> None:
        assert _parse_last_event_id("abc") == 0
        assert _parse_last_event_id("") == 0


# ---------------------------------------------------------------------
# Fresh connect / reconnect / restart-resume via the generator
# ---------------------------------------------------------------------


class TestStreamFreshAndReconnect:
    async def test_fresh_connect_emits_all_events_in_order(
        self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock,
    ) -> None:
        run_id = _make_terminal_run(
            alpha_run_repository, deterministic_clock, run_id="run-fresh", extra_events=2,
        )
        service = ResearchRunService(alpha_run_repository)
        sse_events: list[Any] = []
        async for sse in _stream_events(service, run_id, _PRINCIPAL, 0, poll_interval=0.001):
            sse_events.append(sse)
        # run_created(1) + run_started(2) + candidate_appended(3) + candidate_appended(4)
        # + run_completed(5) + terminal
        ids = [s.id for s in sse_events if s.id is not None]
        assert ids == ["1", "2", "3", "4", "5", "5"]
        event_types = [s.event for s in sse_events]
        assert event_types[-1] == "terminal"
        assert "run_created" in event_types
        assert "run_completed" in event_types

    async def test_last_event_id_resumes_from_k_plus_1(
        self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock,
    ) -> None:
        run_id = _make_terminal_run(
            alpha_run_repository, deterministic_clock, run_id="run-resume", extra_events=2,
        )
        service = ResearchRunService(alpha_run_repository)
        # Resume from seq 3 → should see seq 4, 5, terminal (no dup of 1/2/3).
        sse_events: list[Any] = []
        async for sse in _stream_events(service, run_id, _PRINCIPAL, 3, poll_interval=0.001):
            sse_events.append(sse)
        ids = [s.id for s in sse_events if s.id is not None]
        assert "1" not in ids
        assert "2" not in ids
        assert "3" not in ids
        assert ids[-1] == "5"  # terminal carries the last cursor

    async def test_restart_resume_zero_module_state(
        self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock,
        tmp_path: Path,
    ) -> None:
        """A fresh service instance (simulating a restart) + Last-Event-ID resumes."""
        run_id = _make_terminal_run(
            alpha_run_repository, deterministic_clock, run_id="run-restart", extra_events=1,
        )
        # Simulate a process restart: a brand-new service over the same durable db.
        fresh_service = ResearchRunService(alpha_run_repository)
        assert fresh_service is not alpha_run_repository  # different instance
        sse_events: list[Any] = []
        async for sse in _stream_events(
            fresh_service, run_id, _PRINCIPAL, 2, poll_interval=0.001,
        ):
            sse_events.append(sse)
        ids = [s.id for s in sse_events if s.id is not None]
        # Resumed from seq 2 → sees seq 3 (candidate), 4 (completed), terminal.
        assert "1" not in ids
        assert "2" not in ids
        assert ids[-1] == "4"


# ---------------------------------------------------------------------
# Terminal termination + keepalive
# ---------------------------------------------------------------------


class TestTerminalAndKeepalive:
    async def test_terminal_status_emits_terminal_event_and_stops(
        self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock,
    ) -> None:
        run_id = _make_terminal_run(
            alpha_run_repository, deterministic_clock, run_id="run-term",
        )
        service = ResearchRunService(alpha_run_repository)
        sse_events: list[Any] = []
        async for sse in _stream_events(service, run_id, _PRINCIPAL, 0, poll_interval=0.001):
            sse_events.append(sse)
        # The last event must be the terminal marker.
        assert sse_events[-1].event == "terminal"
        payload = json.loads(sse_events[-1].data)
        assert payload["status"] == "completed"

    async def test_keepalive_on_empty_poll(
        self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock,
    ) -> None:
        run = _make_run(alpha_run_repository, deterministic_clock, run_id="run-ka")
        service = ResearchRunService(alpha_run_repository)
        started = service.start_or_resume(
            run["id"], principal=_PRINCIPAL, expected_version=run["transition_version"],
        )
        assert started is not None
        # The run is running (non-terminal) with only run_created + run_started.
        # After draining those, the generator enters the keepalive loop.
        seen_ping = False
        count = 0
        async for sse in _stream_events(service, run["id"], _PRINCIPAL, 0, poll_interval=0.001):
            count += 1
            if sse.comment == "ping":
                seen_ping = True
                break
            if count > 20:
                break
        assert seen_ping, "expected a keepalive ping comment after draining events"


# ---------------------------------------------------------------------
# No module-level mutable state + write-safety
# ---------------------------------------------------------------------


class TestNoModuleStateAndWriteSafety:
    def test_no_module_level_mutable_state(self) -> None:
        """The SSE module must hold zero module-level dict/list/set of cursors."""
        source = inspect.getsource(research_alpha_sse)
        # No module-level assignment to a mutable container (dict/list/set/{}).
        for line in source.split("\n"):
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#") or stripped.startswith('"""'):
                continue
            # Module-level = no leading whitespace.
            if line[:1] not in ("", " ") and not line.startswith(" "):
                for token in (" = {}", " = []", " = dict(", " = list(", " = set("):
                    assert token not in line, (
                        f"research_alpha_sse: module-level mutable state detected: {line!r}"
                    )

    async def test_generator_calls_no_write_methods(
        self, alpha_run_repository: ResearchRepository, deterministic_clock: DeterministicClock,
    ) -> None:
        """The generator must only call list_events + get (read-only)."""
        run_id = _make_terminal_run(
            alpha_run_repository, deterministic_clock, run_id="run-ro-gen",
        )

        class _RaisingWriteService:
            """Wraps the real service; any write-method call raises."""
            def __init__(self, inner: ResearchRunService) -> None:
                self._inner = inner

            def list_events(self, *args: Any, **kwargs: Any) -> Any:
                return self._inner.list_events(*args, **kwargs)

            def get(self, *args: Any, **kwargs: Any) -> Any:
                return self._inner.get(*args, **kwargs)

            def __getattr__(self, name: str) -> Any:
                def _boom(*args: Any, **kwargs: Any) -> None:
                    raise AssertionError(
                        f"SSE generator must not call write method '{name}'"
                    )
                return _boom

        fake = _RaisingWriteService(ResearchRunService(alpha_run_repository))
        # If the generator calls any write method, _boom raises AssertionError.
        async for _sse in _stream_events(fake, run_id, _PRINCIPAL, 0, poll_interval=0.001):
            pass  # drain to terminal


# ---------------------------------------------------------------------
# Endpoint-level tests via TestClient
# ---------------------------------------------------------------------


class TestStreamEndpoint:
    def test_stream_fresh_connect_endpoint(
        self, sse_client: TestClient,
    ) -> None:
        repo: ResearchRepository = sse_client._repo  # type: ignore[attr-defined]
        clock: DeterministicClock = sse_client._clock  # type: ignore[attr-defined]
        run_id = _make_terminal_run(repo, clock, run_id="run-ep-fresh")
        resp = sse_client.get(
            f"/api/research/alpha/runs/{run_id}/stream",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        ids = [e.get("id") for e in events if e.get("id")]
        # run_created(1) + run_started(2) + run_completed(3) + terminal
        assert ids[-1] == "3"
        assert events[-1].get("event") == "terminal"

    def test_stream_last_event_id_endpoint(
        self, sse_client: TestClient,
    ) -> None:
        repo: ResearchRepository = sse_client._repo  # type: ignore[attr-defined]
        clock: DeterministicClock = sse_client._clock  # type: ignore[attr-defined]
        run_id = _make_terminal_run(repo, clock, run_id="run-ep-lei")
        resp = sse_client.get(
            f"/api/research/alpha/runs/{run_id}/stream",
            headers={"X-Test-Principal": _PRINCIPAL, "Last-Event-ID": "2"},
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        ids = [e.get("id") for e in events if e.get("id")]
        # Resumed from seq 2 → only seq 3 + terminal (no 1 or 2).
        assert "1" not in ids
        assert "2" not in ids
        assert "3" in ids

    def test_stream_unknown_run_404(self, sse_client: TestClient) -> None:
        resp = sse_client.get(
            "/api/research/alpha/runs/no-such-run/stream",
            headers={"X-Test-Principal": _PRINCIPAL},
        )
        assert resp.status_code == 404

    def test_stream_cross_principal_404(self, sse_client: TestClient) -> None:
        repo: ResearchRepository = sse_client._repo  # type: ignore[attr-defined]
        clock: DeterministicClock = sse_client._clock  # type: ignore[attr-defined]
        run_id = _make_terminal_run(repo, clock, run_id="run-ep-xp")
        resp = sse_client.get(
            f"/api/research/alpha/runs/{run_id}/stream",
            headers={"X-Test-Principal": "attacker@example.com"},
        )
        assert resp.status_code == 404
