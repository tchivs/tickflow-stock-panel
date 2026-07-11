"""PLAN-02 contract: replay is historical, ordered, deterministic, and AI-free."""
from __future__ import annotations

from datetime import date

import pytest


class _GovernedHistory:
    """Unordered rows include one future record that must never influence replay."""

    def __init__(self) -> None:
        self.requested_as_of: list[date] = []

    def decision_rows(self, *, symbols: list[str], as_of: date):
        self.requested_as_of.append(as_of)
        return [
            {
                "symbol": "600000.SH",
                "trade_date": "2024-01-23",
                "close": "999.00",
            },
            {
                "symbol": "600000.SH",
                "trade_date": "2024-01-22",
                "close": "10.00",
            },
            {
                "symbol": "000001.SZ",
                "trade_date": "2024-01-22",
                "close": "8.00",
            },
        ]


class _FailIfReviewInvoked:
    def __init__(self) -> None:
        self.calls = 0

    async def review(self, *_args, **_kwargs):
        self.calls += 1
        raise AssertionError("historical replay must never invoke a review gateway")


def test_plan_02_replay_is_as_of_bounded_ordered_and_hash_stable(tmp_path):
    """Equal requests produce the same persisted hash from only historical governed rows."""
    from app.decision.replay import HistoricalReplayService
    from app.operational.repository import OperationalRepository

    repository = OperationalRepository(tmp_path / "operational.db")
    repository.migrate()
    history = _GovernedHistory()
    service = HistoricalReplayService(repository=repository, governed_history=history)

    first = service.replay(
        symbols=["600000.SH", "000001.SZ"],
        as_of=date(2024, 1, 22),
        engine_config_version="playbook-v1",
    )
    second = service.replay(
        symbols=["600000.SH", "000001.SZ"],
        as_of=date(2024, 1, 22),
        engine_config_version="playbook-v1",
    )

    assert history.requested_as_of == [date(2024, 1, 22), date(2024, 1, 22)]
    assert first["result_hash"] == second["result_hash"]
    assert first["snapshot"] == second["snapshot"]
    assert first["snapshot"]["symbols"] == ["000001.SZ", "600000.SH"]
    assert first["snapshot"]["latest_trade_date"] == "2024-01-22"
    assert first["snapshot"]["created_at"] == "2024-01-22T00:00:00+00:00"

    stored = repository.get_replay_run(first["id"])
    assert stored["as_of"] == "2024-01-22"
    assert stored["result_hash"] == first["result_hash"]
    assert stored["provider"] is None
    assert stored["model"] is None


async def test_plan_02_replay_guard_fails_closed_before_any_review_gateway_can_run(tmp_path):
    """The review entry point itself raises under the replay context-local guard."""
    from app.decision.ai_review import DecisionReviewService
    from app.decision.replay import ReplayAIInvocationError, replay_guard
    from app.operational.repository import OperationalRepository

    repository = OperationalRepository(tmp_path / "operational.db")
    repository.migrate()
    fake_gateway = _FailIfReviewInvoked()
    reviewer = DecisionReviewService(repository=repository, gateway=fake_gateway)

    with replay_guard():
        with pytest.raises(ReplayAIInvocationError, match="replay"):
            await reviewer.review(run_id="historical-run")

    assert fake_gateway.calls == 0
