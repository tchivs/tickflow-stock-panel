"""RED contracts for two-phase authorization and durable advanced jobs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest


@dataclass
class FakeClock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


class Spy:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def _services(tmp_path, *, quota: int = 2):
    from app.advanced.authorization import AdvancedAuthorizationService, OperatorPolicy
    from app.advanced.jobs import AdvancedJobService
    from app.advanced.repository import AdvancedRepository

    clock = FakeClock(datetime(2026, 7, 12, tzinfo=UTC))
    repository = AdvancedRepository(tmp_path / "operational.db", clock=clock)
    repository.migrate()
    policy = OperatorPolicy(
        revision="operator-policy-v1",
        task_types=frozenset({"research_draft"}),
        markets=frozenset({"CN-A"}),
        instruments=frozenset({"600519.SH"}),
        quota_per_window=quota,
    )
    authorization = AdvancedAuthorizationService(
        repository=repository,
        policy_loader=lambda: policy,
        clock=clock,
    )
    provider = Spy()
    sandbox = Spy()
    jobs = AdvancedJobService(
        repository=repository,
        authorization_service=authorization,
        provider=provider,
        sandbox=sandbox,
        clock=clock,
    )
    return repository, authorization, jobs, provider, sandbox, clock, policy


def _authorization(authorization, *, expires_in: timedelta = timedelta(minutes=5)):
    return authorization.issue(
        principal="server-operator-principal",
        task_types={"research_draft"},
        markets={"CN-A"},
        instruments={"600519.SH"},
        expires_in=expires_in,
    )


def _request(token: str, **overrides: object) -> dict[str, object]:
    request = {
        "authorization_token": token,
        "task_type": "research_draft",
        "market": "CN-A",
        "instrument": "600519.SH",
        "idempotency_key": "client-retry-key-1",
    }
    request.update(overrides)
    return request


def _assert_audit_only(repository, provider: Spy, sandbox: Spy, *, reason: str) -> None:
    assert repository.list_runnable_jobs() == []
    assert len(repository.list_security_audits()) == 1
    audit = repository.list_security_audits()[0]
    assert audit["decision"] == "rejected"
    assert audit["reason"] == reason
    assert "token" not in audit and "policy" not in audit
    assert provider.calls == []
    assert sandbox.calls == []


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda authorization, _clock: authorization.revoke, "authorization_revoked"),
        (lambda _authorization, clock: lambda _token: clock.advance(timedelta(minutes=6)), "authorization_expired"),
    ],
)
def test_expired_or_revoked_authorization_is_rejected_before_job_or_work(tmp_path, mutation, reason):
    repository, authorization, jobs, provider, sandbox, clock, _policy = _services(tmp_path)
    record = _authorization(authorization)
    mutator = mutation(authorization, clock)
    mutator(record["token"])

    with pytest.raises(ValueError, match="expired|revoked|authorization"):
        jobs.create_job(principal="server-operator-principal", request=_request(record["token"]))

    _assert_audit_only(repository, provider, sandbox, reason=reason)


@pytest.mark.parametrize(
    ("request_overrides", "reason"),
    [
        ({"instrument": "000001.SZ"}, "scope_denied"),
        ({"market": "US"}, "scope_denied"),
        ({"task_type": "sandbox_run"}, "task_type_denied"),
    ],
)
def test_out_of_intersection_requests_create_only_redacted_security_audit(tmp_path, request_overrides, reason):
    repository, authorization, jobs, provider, sandbox, _clock, _policy = _services(tmp_path)
    record = _authorization(authorization)

    with pytest.raises(ValueError, match="scope|task type|authorization"):
        jobs.create_job(
            principal="server-operator-principal",
            request=_request(record["token"], **request_overrides),
        )

    _assert_audit_only(repository, provider, sandbox, reason=reason)


def test_client_authority_fields_are_rejected_before_any_runnable_job_or_sse_work(tmp_path):
    repository, authorization, jobs, provider, sandbox, _clock, _policy = _services(tmp_path)
    record = _authorization(authorization)

    for field in ("principal", "policy", "trusted_job_id", "authority", "allowed_instruments"):
        with pytest.raises(ValueError, match="client|authority|unknown"):
            jobs.create_job(
                principal="server-operator-principal",
                request=_request(record["token"], **{field: "browser-controlled"}),
            )

    assert repository.list_runnable_jobs() == []
    assert len(repository.list_security_audits()) == 5
    assert provider.calls == []
    assert sandbox.calls == []


def test_quota_rejection_is_audited_without_creating_work_and_idempotency_consumes_once(tmp_path):
    repository, authorization, jobs, provider, sandbox, _clock, _policy = _services(tmp_path, quota=1)
    record = _authorization(authorization)

    first = jobs.create_job(principal="server-operator-principal", request=_request(record["token"]))
    duplicate = jobs.create_job(principal="server-operator-principal", request=_request(record["token"]))

    assert duplicate["id"] == first["id"]
    assert repository.count_rate_consumptions(principal="server-operator-principal") == 1
    assert len(repository.list_runnable_jobs()) == 1
    with pytest.raises(ValueError, match="quota|rate"):
        jobs.create_job(
            principal="server-operator-principal",
            request=_request(record["token"], idempotency_key="a-distinct-request"),
        )

    audits = repository.list_security_audits()
    assert len(audits) == 1 and audits[0]["reason"] == "quota_exhausted"
    assert provider.calls == []
    assert sandbox.calls == []


def test_worker_revalidates_revocation_and_current_policy_before_provider_or_sandbox_work(tmp_path):
    repository, authorization, jobs, provider, sandbox, _clock, policy = _services(tmp_path)
    record = _authorization(authorization)
    job = jobs.create_job(principal="server-operator-principal", request=_request(record["token"]))

    authorization.revoke(record["token"])
    rejected = jobs.run(job_id=job["id"])

    assert rejected["status"] == "rejected"
    assert rejected["rejection_reason"] == "authorization_revoked"
    assert repository.get_job(job["id"])["status"] == "rejected"
    assert repository.list_security_audits()[-1]["reason"] == "authorization_revoked"
    assert provider.calls == []
    assert sandbox.calls == []

    # Reissuance cannot preserve the original policy snapshot after policy scope contracts.
    fresh = _authorization(authorization)
    queued = jobs.create_job(
        principal="server-operator-principal",
        request=_request(fresh["token"], idempotency_key="policy-change-job"),
    )
    policy.instruments = frozenset()
    policy_rejected = jobs.run(job_id=queued["id"])

    assert policy_rejected["status"] == "rejected"
    assert policy_rejected["rejection_reason"] == "scope_denied"
    assert repository.list_security_audits()[-1]["reason"] == "scope_denied"
    assert provider.calls == []
    assert sandbox.calls == []
