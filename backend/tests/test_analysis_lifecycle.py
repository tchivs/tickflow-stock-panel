"""Wave 0 contracts for attributable, human-confirmed signal lifecycle history."""
from __future__ import annotations

import pytest


def _lifecycle(tmp_path):
    from app.analysis.lifecycle import LifecycleRuleService
    from app.analysis.repository import AnalysisRepository

    repository = AnalysisRepository(tmp_path / "operational.db")
    repository.migrate()
    return repository, LifecycleRuleService(repository=repository)


def test_lifecycle_rules_require_attributable_state_specific_evidence(tmp_path):
    _repository, service = _lifecycle(tmp_path)

    assert service.propose(
        subject_key="600519.SH", prior_state="active", next_state="strengthened", evidence=[]
    ) is None
    assert service.propose(
        subject_key="600519.SH", prior_state="active", next_state="priced_in", evidence=[{"id": "a"}]
    ) is None


def test_lifecycle_confirmation_requires_server_resolved_reviewer_and_creates_one_plan(tmp_path):
    repository, service = _lifecycle(tmp_path)
    proposal = service.propose(
        subject_key="600519.SH",
        prior_state="active",
        next_state="weakened",
        evidence=[{"id": "filing", "independence_group": "exchange"}],
    )

    with pytest.raises(ValueError, match="reviewer principal"):
        service.confirm(review_id=proposal["id"], reviewer_principal=None, window_days=20)

    confirmed = service.confirm(
        review_id=proposal["id"], reviewer_principal="reviewer-principal-opaque", window_days=20
    )
    assert confirmed["official_state"] == "weakened"
    assert len(repository.list_observation_plans(proposal["id"])) == 1
    with pytest.raises(ValueError, match="immutable|confirmed"):
        service.confirm(
            review_id=proposal["id"], reviewer_principal="reviewer-principal-opaque", window_days=20
        )


def test_lifecycle_rejection_and_outcomes_append_without_changing_official_state(tmp_path):
    repository, service = _lifecycle(tmp_path)
    proposal = service.propose(
        subject_key="600519.SH",
        prior_state="active",
        next_state="falsified",
        evidence=[{"id": "cross-check", "independent_contradiction": True}],
    )

    rejected = service.reject(review_id=proposal["id"], reviewer_principal="reviewer-principal-opaque")

    assert rejected["official_state"] == "active"
    assert repository.list_events(subject_key="600519.SH") == []
