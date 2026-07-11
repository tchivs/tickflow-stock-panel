"""PLAN-02 contract: configured review remains optional, typed, and provenance-audited."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest


def _baseline():
    from app.decision.playbook import DecisionBaseline

    return DecisionBaseline(
        symbol="600000.SH",
        entry_low=Decimal("9.7000"),
        entry_high=Decimal("10.2000"),
        stop=Decimal("9.1000"),
        target1=Decimal("11.1000"),
        target2=Decimal("12.0000"),
        position_pct=Decimal("0.4999"),
        action="突破确认",
        score=Decimal("8.00"),
        risk_reward=Decimal("2.6667"),
        reason_snapshot={"source": "governed_history"},
        data_as_of=date(2024, 1, 22),
        engine_config_version="playbook-v1",
    )


def _run(tmp_path):
    from app.operational.repository import OperationalRepository

    repository = OperationalRepository(tmp_path / "operational.db")
    repository.migrate()
    return repository, repository.persist_decision_baseline(_baseline())


async def test_plan_02_configured_openai_compatible_review_persists_typed_proposal_provenance(
    tmp_path,
):
    """Injected transport proves the configured gateway needs neither network nor credentials."""
    from app.decision.ai_review import ConfiguredAIReviewGateway, DecisionReviewService

    observed_messages = []

    async def offline_transport(messages, **_kwargs):
        observed_messages.extend(messages)
        return (
            '{"adjustments":[{"field":"entry_low","value":"9.8000",'
            '"rationale":"wait for confirmation"}]}'
        )

    repository, run = _run(tmp_path)
    gateway = ConfiguredAIReviewGateway(
        provider="openai_compat",
        model="offline-contract-model",
        generate_text=offline_transport,
    )

    response = await DecisionReviewService(repository=repository, gateway=gateway).review(
        run_id=run["id"]
    )

    assert observed_messages
    assert response["review_status"] == "available"
    assert response["final"] == _baseline().to_snapshot()
    assert repository.get_decision_run(run["id"])["proposal"] == {
        "provider": "openai_compat",
        "model": "offline-contract-model",
        "adjustments": [
            {
                "field": "entry_low",
                "value": "9.8000",
                "rationale": "wait for confirmation",
            }
        ],
    }


async def test_plan_02_offline_fake_gateway_returns_the_same_typed_proposal_without_network(tmp_path):
    """The explicit fake is the only provider-like collaborator permitted in offline tests."""
    from app.decision.ai_review import DecisionReviewService, OfflineFakeReviewGateway

    repository, run = _run(tmp_path)
    gateway = OfflineFakeReviewGateway(
        proposal={
            "adjustments": [
                {
                    "field": "position_pct",
                    "value": "0.4000",
                    "rationale": "reduce exposure",
                }
            ]
        },
        provider="offline_fake",
        model="fixture-v1",
    )

    response = await DecisionReviewService(repository=repository, gateway=gateway).review(
        run_id=run["id"]
    )

    assert response["review_status"] == "available"
    assert repository.get_decision_run(run["id"])["proposal"]["provider"] == "offline_fake"
    assert repository.get_decision_run(run["id"])["proposal"]["model"] == "fixture-v1"


@pytest.mark.parametrize(
    "gateway",
    [None, "malformed", "failed"],
)
async def test_plan_02_unavailable_review_preserves_and_returns_the_deterministic_baseline(
    tmp_path, gateway
):
    """No unavailable path may change the baseline or leave a partial proposal record."""
    from app.decision.ai_review import DecisionReviewService, OfflineFakeReviewGateway

    repository, run = _run(tmp_path)
    if gateway == "malformed":
        gateway = OfflineFakeReviewGateway(raw_response="not-json")
    elif gateway == "failed":
        gateway = OfflineFakeReviewGateway(error=RuntimeError("provider unavailable"))

    response = await DecisionReviewService(
        repository=repository,
        gateway=gateway,
        fixture_compose=gateway is None,
    ).review(run_id=run["id"])

    assert response == {
        "review_status": "unavailable",
        "final": _baseline().to_snapshot(),
    }
    persisted = repository.get_decision_run(run["id"])
    assert persisted["final"] == _baseline().to_snapshot()
    assert persisted["proposal"] is None
