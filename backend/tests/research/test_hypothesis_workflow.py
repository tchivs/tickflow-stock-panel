from __future__ import annotations

import asyncio

import pytest

from app.research.hypotheses import (
    FactorHypothesisService,
    HypothesisUnavailableError,
    OfflineFakeHypothesisGateway,
)


def test_valid_draft_is_parser_confirmed_and_carries_provenance() -> None:
    service = FactorHypothesisService(
        OfflineFakeHypothesisGateway(
            raw_response='{"expression":"close / ma20","explanation":"Medium-term momentum.","assumptions":["ma20 is governed"]}'
        )
    )

    draft = asyncio.run(service.draft(hypothesis="Find medium-term momentum", options={"asset_type": "stock"}))

    assert draft.expression == "close / ma20"
    assert draft.normalized_expression == "close / ma20"
    assert draft.provenance["provider"] == "offline_fake"
    assert draft.provenance["model"] == "offline-fixture"
    assert draft.provenance["model_version"] == "offline-v1"
    assert draft.provenance["prompt_template_version"] == "factor-hypothesis-v1"
    assert draft.provenance["generated_at"]


def test_malformed_or_unsafe_provider_draft_is_rejected_without_fallback() -> None:
    malformed = FactorHypothesisService(OfflineFakeHypothesisGateway(raw_response="not-json"))
    unsafe = FactorHypothesisService(
        OfflineFakeHypothesisGateway(raw_response='{"expression":"__import__(\\\"os\\\")","explanation":"unsafe"}')
    )

    with pytest.raises(ValueError, match="malformed JSON"):
        asyncio.run(malformed.draft(hypothesis="anything"))
    with pytest.raises(ValueError, match="invalid factor DSL"):
        asyncio.run(unsafe.draft(hypothesis="anything"))


def test_review_verification_rejects_impersonated_or_modified_draft() -> None:
    service = FactorHypothesisService(OfflineFakeHypothesisGateway())
    draft = asyncio.run(service.draft(hypothesis="momentum"))

    assert service.reviewed_draft(
        draft_id=draft.draft_id,
        expression=draft.expression,
        explanation=draft.explanation,
        provenance=draft.provenance,
    ) == draft
    with pytest.raises(ValueError, match="does not match"):
        service.reviewed_draft(
            draft_id=draft.draft_id,
            expression="close / ma60",
            explanation=draft.explanation,
            provenance=draft.provenance,
        )
    with pytest.raises(ValueError, match="unknown or expired"):
        service.reviewed_draft(
            draft_id="f" * 32,
            expression=draft.expression,
            explanation=draft.explanation,
            provenance=draft.provenance,
        )


def test_unavailable_provider_returns_actionable_error() -> None:
    with pytest.raises(HypothesisUnavailableError, match="unavailable"):
        asyncio.run(FactorHypothesisService().draft(hypothesis="momentum"))
