"""Wave 0 contracts for attributable, human-confirmed signal lifecycle history."""
from __future__ import annotations

import pytest


def _lifecycle(tmp_path, reviewer_resolver=None):
    from app.analysis.lifecycle import LifecycleRuleService
    from app.analysis.repository import AnalysisRepository

    repository = AnalysisRepository(tmp_path / "operational.db")
    repository.migrate()
    return repository, LifecycleRuleService(repository=repository, reviewer_resolver=reviewer_resolver)


def test_lifecycle_rules_require_attributable_state_specific_evidence(tmp_path):
    _repository, service = _lifecycle(tmp_path)

    assert service.propose(
        subject_key="600519.SH", prior_state="active", next_state="strengthened", evidence=[]
    ) is None
    assert service.propose(
        subject_key="600519.SH", prior_state="active", next_state="priced_in", evidence=[{"id": "a"}]
    ) is None


def test_lifecycle_rules_require_independent_contradiction_and_price_event_context(tmp_path):
    _repository, service = _lifecycle(tmp_path)

    assert service.propose(
        subject_key="600519.SH",
        prior_state="active",
        next_state="strengthened",
        evidence=[{"id": "repost", "independence_group": "same-publisher", "attributable": False}],
    ) is None
    assert service.propose(
        subject_key="600519.SH",
        prior_state="active",
        next_state="falsified",
        evidence=[{"id": "contradiction", "independent_contradiction": False}],
    ) is None
    assert service.propose(
        subject_key="600519.SH",
        prior_state="active",
        next_state="priced_in",
        evidence=[{"id": "event", "independence_group": "exchange"}],
    ) is None

    strengthened = service.propose(
        subject_key="600519.SH",
        prior_state="active",
        next_state="strengthened",
        evidence=[{"id": "filing", "independence_group": "exchange", "occurred_at": "2026-07-12T00:00:00+00:00"}],
    )
    falsified = service.propose(
        subject_key="600519.SH",
        prior_state="active",
        next_state="falsified",
        evidence=[{"id": "cross-checked", "independent_contradiction": True, "occurred_at": "2026-07-12T00:00:00+00:00"}],
    )
    priced_in = service.propose(
        subject_key="600519.SH",
        prior_state="active",
        next_state="priced_in",
        evidence=[{"id": "price-event", "price_context": "close=100", "event_context": "earnings", "occurred_at": "2026-07-12T00:00:00+00:00"}],
    )

    assert strengthened is not None
    assert strengthened["evidence_ids"] == ["filing"]
    assert falsified is not None
    assert priced_in is not None


def test_lifecycle_confirmation_requires_server_resolved_reviewer_and_creates_one_plan(tmp_path):
    repository, service = _lifecycle(
        tmp_path, reviewer_resolver=lambda token: "reviewer-principal-opaque" if token == "session-token" else None
    )
    proposal = service.propose(
        subject_key="600519.SH",
        prior_state="active",
        next_state="weakened",
        evidence=[{"id": "filing", "independence_group": "exchange"}],
    )

    with pytest.raises(ValueError, match="reviewer principal"):
        service.confirm(review_id=proposal["id"], session_token=None, window_days=20, benchmark="CSI300", metric="excess_return")

    confirmed = service.confirm(
        review_id=proposal["id"], session_token="session-token", window_days=20, benchmark="CSI300", metric="excess_return"
    )
    assert confirmed["official_state"] == "weakened"
    assert len(repository.list_observation_plans(proposal["id"])) == 1
    with pytest.raises(ValueError, match=r"immutable|confirmed"):
        service.confirm(
            review_id=proposal["id"], session_token="session-token", window_days=20, benchmark="CSI300", metric="excess_return"
        )


def test_lifecycle_rejection_and_outcomes_append_without_changing_official_state(tmp_path):
    repository, service = _lifecycle(tmp_path, reviewer_resolver=lambda _token: "reviewer-principal-opaque")
    proposal = service.propose(
        subject_key="600519.SH",
        prior_state="active",
        next_state="falsified",
        evidence=[{"id": "cross-check", "independent_contradiction": True}],
    )

    rejected = service.reject(review_id=proposal["id"], session_token="session-token")

    assert rejected["official_state"] == "active"
    assert repository.list_events(subject_key="600519.SH") == []


def test_confirmed_review_cannot_be_rejected_after_its_event_is_recorded(tmp_path):
    _repository, service = _lifecycle(tmp_path, reviewer_resolver=lambda _token: "reviewer-principal-opaque")
    proposal = service.propose(
        subject_key="600519.SH",
        prior_state="active",
        next_state="weakened",
        evidence=[{"id": "filing", "independence_group": "exchange"}],
    )
    service.confirm(
        review_id=proposal["id"], session_token="token", window_days=20, benchmark="CSI300", metric="excess_return"
    )

    with pytest.raises(ValueError, match="confirmed"):
        service.reject(review_id=proposal["id"], session_token="token")


def test_confirm_rechecks_current_state_and_writes_exactly_one_immutable_plan(tmp_path):
    repository, service = _lifecycle(tmp_path, reviewer_resolver=lambda _token: "reviewer-principal-opaque")
    first = service.propose(
        subject_key="600519.SH",
        prior_state="active",
        next_state="weakened",
        evidence=[{"id": "filing", "independence_group": "exchange"}],
    )
    stale = service.propose(
        subject_key="600519.SH",
        prior_state="active",
        next_state="strengthened",
        evidence=[{"id": "other-filing", "independence_group": "exchange"}],
    )

    confirmed = service.confirm(
        review_id=first["id"], session_token="token", window_days=60, benchmark="CSI300", metric="excess_return"
    )
    assert confirmed["official_state"] == "weakened"
    assert len(repository.list_observation_plans(first["id"])) == 1
    with pytest.raises(ValueError, match="current state"):
        service.confirm(
            review_id=stale["id"], session_token="token", window_days=120, benchmark="CSI300", metric="max_drawdown"
        )
    with pytest.raises(ValueError, match="immutable"):
        repository.replace_observation_plan(
            plan_id=repository.list_observation_plans(first["id"])[0]["id"], window_days=120
        )


def test_outcomes_append_only_under_existing_plan_and_reviewer_identity_cannot_be_injected(tmp_path):
    repository, service = _lifecycle(tmp_path, reviewer_resolver=lambda _token: "reviewer-principal-opaque")
    proposal = service.propose(
        subject_key="600519.SH",
        prior_state="active",
        next_state="weakened",
        evidence=[{"id": "filing", "independence_group": "exchange"}],
    )
    confirmed = service.confirm(
        review_id=proposal["id"], session_token="token", window_days=20, benchmark="CSI300", metric="excess_return"
    )
    outcome = service.append_outcome(
        plan_id=confirmed["plan"]["id"], outcome={"status": "incomplete", "observed_value": None}
    )

    assert outcome["outcome"]["status"] == "incomplete"
    assert len(repository.list_observation_outcomes(confirmed["plan"]["id"])) == 1
    with pytest.raises(TypeError):
        service.confirm(
            review_id=proposal["id"], session_token="token", window_days=20,
            benchmark="CSI300", metric="excess_return", reviewer_principal="browser-controlled"
        )


def test_auth_persists_an_opaque_reviewer_principal_for_valid_sessions(tmp_path, monkeypatch):
    from app.services import auth

    path = tmp_path / "auth.json"
    monkeypatch.setattr(auth, "_path", lambda: path)
    monkeypatch.setattr(auth, "_configured_cache", None)
    auth._sessions.clear()
    auth.set_password("secure-password")
    token = auth.verify_and_create_session("secure-password")

    assert token is not None
    principal = auth.resolve_authenticated_reviewer(token)
    assert principal is not None
    assert principal != token
    auth._sessions.clear()
    auth._restore_sessions()
    assert auth.resolve_authenticated_reviewer(token) == principal
