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


def _services(
    tmp_path,
    *,
    quota: int = 2,
    rate_limits: dict[str, int] | None = None,
    instruments: frozenset[str] = frozenset({"600519.SH"}),
):
    from app.advanced.authorization import AdvancedAuthorizationService, OperatorPolicy
    from app.advanced.jobs import AdvancedJobService
    from app.advanced.repository import AdvancedRepository

    clock = FakeClock(datetime(2026, 7, 12, tzinfo=UTC))
    repository = AdvancedRepository(tmp_path / "operational.db", clock=clock)
    repository.migrate()
    configured_rate_limits = rate_limits or {"research_draft": quota}
    policy = OperatorPolicy(
        revision="operator-policy-v1",
        task_types=frozenset(configured_rate_limits),
        markets=frozenset({"CN-A"}),
        instruments=instruments,
        rate_limits=configured_rate_limits,
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


def _authorization(
    authorization,
    *,
    expires_in: timedelta = timedelta(minutes=5),
    task_types: set[str] | None = None,
    instruments: set[str] | None = None,
):
    return authorization.issue(
        principal="server-operator-principal",
        task_types=task_types or {"research_draft"},
        markets={"CN-A"},
        instruments=instruments or {"600519.SH"},
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

    with pytest.raises(ValueError, match=r"expired|revoked|authorization"):
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

    with pytest.raises(ValueError, match=r"scope|task type|authorization"):
        jobs.create_job(
            principal="server-operator-principal",
            request=_request(record["token"], **request_overrides),
        )

    _assert_audit_only(repository, provider, sandbox, reason=reason)


def test_client_authority_fields_are_rejected_before_any_runnable_job_or_sse_work(tmp_path):
    repository, authorization, jobs, provider, sandbox, _clock, _policy = _services(tmp_path)
    record = _authorization(authorization)

    for field in ("principal", "policy", "trusted_job_id", "authority", "allowed_instruments"):
        with pytest.raises(ValueError, match=r"client|authority|unknown"):
            jobs.create_job(
                principal="server-operator-principal",
                request=_request(record["token"], **{field: "browser-controlled"}),
            )

    assert repository.list_runnable_jobs() == []
    assert len(repository.list_security_audits()) == 5
    assert provider.calls == []
    assert sandbox.calls == []


def test_quota_rejection_is_audited_without_creating_work_and_idempotency_consumes_once(tmp_path):
    repository, authorization, jobs, provider, sandbox, clock, _policy = _services(tmp_path, quota=1)
    record = _authorization(authorization)

    first = jobs.create_job(principal="server-operator-principal", request=_request(record["token"]))
    duplicate = jobs.create_job(principal="server-operator-principal", request=_request(record["token"]))

    assert duplicate["id"] == first["id"]
    assert repository.count_rate_consumptions(
        principal="server-operator-principal",
        policy_revision_id=str(repository.get_authorization(str(record["id"]))["policy_revision_id"]),
        task_type="research_draft",
        now=clock.now.isoformat(),
    ) == 1
    assert len(repository.list_runnable_jobs()) == 1
    with pytest.raises(ValueError, match=r"quota|rate"):
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


def test_rate_window_migration_preserves_legacy_accounting_under_unrunnable_identity(tmp_path):
    import sqlite3

    from app.operational.migrations import MIGRATIONS, migrate_operational_db

    database = tmp_path / "legacy-operational.db"
    connection = sqlite3.connect(database)
    try:
        for migration in MIGRATIONS[:-1]:
            connection.executescript(migration)
        connection.execute(f"PRAGMA user_version = {len(MIGRATIONS) - 1}")
        connection.execute(
            """INSERT INTO advanced_policy_revisions
               (id, revision, fingerprint, fact_schema_version, snapshot_json, created_at)
               VALUES ('legacy-policy', 'legacy', 'legacy-fingerprint', 'advanced_policy_snapshot_legacy_v1', '{}', '2026-07-12T00:00:00+00:00')"""
        )
        connection.execute(
            """INSERT INTO advanced_rate_windows
               (id, principal, policy_revision_id, window_started_at, consumed, created_at)
               VALUES ('legacy-rate-window', 'operator', 'legacy-policy', '2026-07-12T00:00:00+00:00', 4, '2026-07-12T00:00:00+00:00')"""
        )
        connection.commit()

        migrate_operational_db(connection)

        row = connection.execute(
            "SELECT task_type, consumed FROM advanced_rate_windows WHERE id = 'legacy-rate-window'"
        ).fetchone()
        assert row == ("__legacy_rate_window__", 4)
        with pytest.raises(sqlite3.IntegrityError, match="immutable window"):
            connection.execute(
                "UPDATE advanced_rate_windows SET task_type = 'experiment' WHERE id = 'legacy-rate-window'"
            )
    finally:
        connection.close()


def test_task_type_rate_windows_are_independent_and_charge_once(tmp_path):
    repository, authorization, _jobs, _provider, _sandbox, clock, _policy = _services(tmp_path, quota=1)
    record = _authorization(authorization)
    policy_revision_id = str(repository.get_authorization(str(record["id"]))["policy_revision_id"])

    for task_type in ("research_draft", "experiment", "strategy_evaluation"):
        job = repository.acquire_authorized_job(
            job_id=f"{task_type}-job",
            authorization_id=str(record["id"]),
            principal="server-operator-principal",
            subject_kind="instrument",
            subject_key="600519.SH",
            task_type=task_type,
            market="CN-A",
            instrument="600519.SH",
            idempotency_key=f"{task_type}-request",
            policy_revision_id=policy_revision_id,
            quota=1,
            now=clock.now.isoformat(),
        )
        assert job is not None
        assert repository.count_rate_consumptions(
            principal="server-operator-principal",
            policy_revision_id=policy_revision_id,
            task_type=task_type,
            now=clock.now.isoformat(),
        ) == 1

    assert repository.acquire_authorized_job(
        job_id="exhausted-experiment-job",
        authorization_id=str(record["id"]),
        principal="server-operator-principal",
        subject_kind="instrument",
        subject_key="600519.SH",
        task_type="experiment",
        market="CN-A",
        instrument="600519.SH",
        idempotency_key="exhausted-experiment-request",
        policy_revision_id=policy_revision_id,
        quota=1,
        now=clock.now.isoformat(),
    ) is None
    assert {job["id"] for job in repository.list_runnable_jobs()} == {
        "research_draft-job",
        "experiment-job",
        "strategy_evaluation-job",
    }


def test_asymmetric_task_quotas_reject_without_work_or_progress_and_leave_research_capacity(tmp_path):
    import asyncio

    rate_limits = {"research_draft": 2, "experiment": 1, "strategy_evaluation": 1}
    instruments = frozenset({"600519.SH", "000001.SZ"})
    repository, authorization, jobs, provider, sandbox, _clock, _policy = _services(
        tmp_path, rate_limits=rate_limits, instruments=instruments
    )
    record = _authorization(
        authorization, task_types=set(rate_limits), instruments=set(instruments)
    )
    progress = Spy()
    workflow = AsyncSpy()
    jobs.set_progress_publisher(progress)
    jobs.set_workflow(workflow)

    experiment = jobs.create_job(
        principal="server-operator-principal",
        request=_request(record["token"], task_type="experiment"),
    )
    strategy = jobs.create_job(
        principal="server-operator-principal",
        request=_request(record["token"], task_type="strategy_evaluation", idempotency_key="strategy-initial"),
    )
    with pytest.raises(ValueError, match="quota|rate"):
        jobs.create_job(
            principal="server-operator-principal",
            request=_request(
                record["token"], task_type="experiment", instrument="000001.SZ", idempotency_key="experiment-exhausted"
            ),
        )
    with pytest.raises(ValueError, match="quota|rate"):
        jobs.create_job(
            principal="server-operator-principal",
            request=_request(
                record["token"], task_type="strategy_evaluation", instrument="000001.SZ", idempotency_key="strategy-exhausted"
            ),
        )

    research_that_runs = jobs.create_job(
        principal="server-operator-principal",
        request=_request(
            record["token"], instrument="000001.SZ", idempotency_key="research-runs-with-independent-capacity"
        ),
    )
    completed = asyncio.run(jobs.run_authorized_job(job_id=research_that_runs["id"]))
    assert completed["status"] == "authorized"
    assert len(workflow.calls) == 1
    assert progress.calls
    progress.calls.clear()

    research = jobs.create_job(
        principal="server-operator-principal",
        request=_request(record["token"], idempotency_key="research-revalidation-denied"),
    )
    with repository._connection() as connection, connection:
        connection.execute(
            "UPDATE advanced_rate_windows SET consumed = consumed + 1 WHERE principal = ? AND task_type = ?",
            ("server-operator-principal", "research_draft"),
        )

    rejected = asyncio.run(jobs.run_authorized_job(job_id=research["id"]))

    assert rejected["status"] == "rejected"
    assert rejected["rejection_reason"] == "quota_exhausted"
    assert {job["id"] for job in repository.list_runnable_jobs()} == {
        experiment["id"],
        strategy["id"],
        research_that_runs["id"],
    }
    assert provider.calls == []
    assert sandbox.calls == []
    assert len(workflow.calls) == 1
    assert progress.calls == []
    assert [audit["reason"] for audit in repository.list_security_audits()] == [
        "quota_exhausted",
        "quota_exhausted",
        "workflow_authorized",
        "quota_exhausted",
    ]


class AsyncSpy:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def ainvoke(self, state: dict[str, object], config: dict[str, object]) -> dict[str, object]:
        self.calls.append({"state": state, "config": config})
        return {}
