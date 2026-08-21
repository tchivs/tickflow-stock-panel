"""Phase 55-04: SSE 代码完全删除验证 (WS-02 闭环, D-03 无回退路径).

Verifies that all SSE/ndjson endpoint code has been deleted from backend/app/,
the sse-starlette dependency removed from pyproject.toml, the test_phase50_guard
baseline updated, and WS broadcast paths still work.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_APP = _BACKEND / "app"
_API = _APP / "api"


def _grep_count(directory: Path, pattern: str) -> int:
    """Count occurrences of a regex pattern in .py files under directory (excluding __pycache__)."""
    result = subprocess.run(
        ["grep", "-rc", "--include=*.py", pattern, str(directory)],
        capture_output=True, text=True,
    )
    total = 0
    for line in result.stdout.strip().splitlines():
        if ":" in line:
            try:
                total += int(line.rsplit(":", 1)[1])
            except ValueError:
                pass
    return total


def _grep_count_file(path: Path, pattern: str) -> int:
    """Count occurrences of a regex pattern in a single file."""
    result = subprocess.run(
        ["grep", "-c", pattern, str(path)],
        capture_output=True, text=True,
    )
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


class TestSseCodeRemoved:
    """All SSE/ndjson endpoint code must be deleted from backend/app/."""

    def test_no_event_source_response(self) -> None:
        """No EventSourceResponse usage remains in backend/app/."""
        assert _grep_count(_APP, "EventSourceResponse") == 0, (
            "EventSourceResponse still found in backend/app/ — SSE code not fully removed"
        )

    def test_no_sse_starlette_import(self) -> None:
        """No sse_starlette import remains in backend/app/."""
        assert _grep_count(_APP, r"from sse_starlette\|import sse_starlette") == 0, (
            "sse_starlette import still found in backend/app/ — SSE dependency not removed"
        )

    def test_no_text_event_stream(self) -> None:
        """No text/event-stream media_type remains in backend/app/ (except external API headers)."""
        # Exclude data_providers which use text/event-stream in Accept headers for external APIs
        result = subprocess.run(
            ["grep", "-rc", "--include=*.py", "text/event-stream", str(_APP)],
            capture_output=True, text=True,
        )
        total = 0
        for line in result.stdout.strip().splitlines():
            if ":" in line and "data_providers" not in line:
                try:
                    total += int(line.rsplit(":", 1)[1])
                except ValueError:
                    pass
        assert total == 0, (
            "text/event-stream still found in backend/app/ (excluding external API headers) — SSE endpoint not fully removed"
        )

    def test_no_ndjson_endpoint(self) -> None:
        """No application/x-ndjson media_type remains in backend/app/api/ endpoints."""
        assert _grep_count(_API, "application/x-ndjson") == 0, (
            "application/x-ndjson still found in backend/app/api/ — ndjson endpoint not removed"
        )


class TestSseStarletteDependencyRemoved:
    """sse-starlette dependency must be removed from pyproject.toml."""

    def test_sse_starlette_not_in_pyproject(self) -> None:
        """sse-starlette must not appear in pyproject.toml."""
        pyproject = _BACKEND / "pyproject.toml"
        assert _grep_count_file(pyproject, "sse-starlette") == 0, (
            "sse-starlette still in pyproject.toml — dependency not removed (D-03)"
        )


class TestPhase50GuardUpdated:
    """test_phase50_guard.py baseline must remove sse-starlette references."""

    def test_test_guard_updated(self) -> None:
        """test_phase50_guard.py must not contain sse-starlette or EventSourceResponse."""
        guard = _BACKEND / "tests" / "test_phase50_guard.py"
        assert _grep_count_file(guard, "sse-starlette") == 0, (
            "sse-starlette still in test_phase50_guard.py — baseline not updated"
        )
        assert _grep_count_file(guard, "EventSourceResponse") == 0, (
            "EventSourceResponse still in test_phase50_guard.py — assertions not updated"
        )


class TestQuoteSubscriberRemoved:
    """QuoteSubscriber SSE subscriber mode must be deleted from QuoteService."""

    def test_quote_subscriber_removed(self) -> None:
        """QuoteSubscriber class must be removed from quote_service.py."""
        qs = _APP / "services" / "quote_service.py"
        assert _grep_count_file(qs, "QuoteSubscriber") == 0, (
            "QuoteSubscriber still in quote_service.py — SSE subscriber mode not removed"
        )

    def test_subscribe_unsubscribe_removed(self) -> None:
        """subscribe/unsubscribe SSE methods must be removed from quote_service.py."""
        qs = _APP / "services" / "quote_service.py"
        assert _grep_count_file(qs, "def subscribe") == 0, (
            "subscribe() method still in quote_service.py — SSE subscriber not removed"
        )
        assert _grep_count_file(qs, "def unsubscribe") == 0, (
            "unsubscribe() method still in quote_service.py — SSE subscriber not removed"
        )

    def test_subscribers_set_removed(self) -> None:
        """_subscribers set must be removed from quote_service.py."""
        qs = _APP / "services" / "quote_service.py"
        assert _grep_count_file(qs, "_subscribers") == 0, (
            "_subscribers set still in quote_service.py — SSE subscriber state not removed"
        )


class TestWsBroadcastStillWorks:
    """WS broadcast paths must not be affected by SSE deletion."""

    def test_ws_broadcast_in_quote_service(self) -> None:
        """QuoteService must still have WS broadcast calls."""
        qs = _APP / "services" / "quote_service.py"
        count = _grep_count_file(qs, "broadcast_to_channel")
        assert count >= 1, (
            f"broadcast_to_channel not found in quote_service.py — WS broadcast broken (found {count})"
        )

    def test_ws_broadcast_in_backtest(self) -> None:
        """backtest.py must still have WS broadcast calls."""
        bt = _API / "backtest.py"
        count = _grep_count_file(bt, "_ws_broadcast")
        assert count >= 3, (
            f"_ws_broadcast calls in backtest.py < 3 — WS broadcast may be broken (found {count})"
        )
