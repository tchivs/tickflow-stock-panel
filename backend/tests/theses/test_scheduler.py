"""Strict RED contracts for bounded, restart-safe per-condition thesis checks."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta

import pytest

NOW = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
DUE_AT = NOW.isoformat()


class FixedEvidenceResolver:
    def __init__(self, *, result: str = "not_matched", fail: Exception | None = None) -> None:
        self.result = result
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    def resolve(
        self, *, condition: dict[str, object], due_at: str, instrument: str | None = None
    ) -> dict[str, object]:
        self.calls.append({"condition": condition, "due_at": due_at, "instrument": instrument})
        if self.fail is not None:
            raise self.fail
        observed = -0.02 if self.result == "matched" else 0.04
        return {
            "result": self.result,
            "observed_value": observed if self.result not in {"insufficient_evidence", "error"} else None,
            "unit": "ratio",
            "as_of": "2026-06-30",
            "evidence": [{"source_id": "filing-2026q2", "field": "revenue_growth_yoy", "observed_value": observed}],
            "evidence_fingerprint": "e" * 64,
        }


def _payload(cadence: str = "daily", *, instrument: str = "600519.SH") -> dict[str, object]:
    return {
        "instrument": instrument,
        "core_judgment": "Pricing power supports durable free cash flow.",
        "rationale": "Governed filing evidence supports the judgment.",
        "change_reason": "Initial thesis record",
        "anchors": [{
            "method": "discounted_cash_flow", "currency": "CNY", "as_of": date(2026, 6, 30),
            "low": 1420.0, "high": 1680.0,
            "assumptions": [{"name": "discount_rate", "value": 0.085, "unit": "ratio"}],
            "limitations": ["Terminal-value sensitivity remains material."],
        }],
        "conditions": [{
            "source_kind": "financial", "field": "revenue_growth_yoy", "operator": "lt",
            "threshold": 0.0, "unit": "ratio", "lookback_days": 120,
            "cadence": cadence, "timezone": "Asia/Shanghai",
            "description": "Revenue growth turns negative.",
        }],
    }


def _runtime(tmp_path, *, cadence: str = "daily", resolver: FixedEvidenceResolver | None = None, limit: int = 8):
    from app.theses.repository import ThesisRepository
    from app.theses.schemas import ThesisVersionRequest
    from app.theses.scheduler import ThesisDueScanner
    from app.theses.service import ThesisService

    repository = ThesisRepository(tmp_path / "operational.db", now=lambda: DUE_AT)
    request = ThesisVersionRequest.model_validate(_payload(cadence))
    version = repository.create_version(request=request, created_by="principal-opaque")
    evidence = resolver or FixedEvidenceResolver()
    service = ThesisService(repository=repository, evidence_resolver=evidence)
    scanner = ThesisDueScanner(repository=repository, service=service, batch_limit=limit, lease_seconds=60)
    return repository, service, scanner, evidence, version, version["conditions"][0]


@pytest.mark.parametrize(
    ("cadence", "minimum_delta"),
    (("daily", timedelta(days=1)), ("weekly", timedelta(days=7)), ("monthly", timedelta(days=28)), ("quarterly", timedelta(days=89))),
    ids=("daily", "weekly", "monthly", "quarterly"),
)
def test_each_condition_cadence_advances_its_independent_monotonic_cursor(tmp_path, cadence, minimum_delta) -> None:
    repository, _service, scanner, _resolver, _version, condition = _runtime(tmp_path, cadence=cadence)
    before = repository.get_schedule(condition["id"])

    checks = scanner.scan_once(now=NOW, owner="scanner-a")
    after = repository.get_schedule(condition["id"])

    assert len(checks) == 1
    assert checks[0]["condition_id"] == condition["id"]
    assert checks[0]["due_at"] == before["next_due_at"]
    assert datetime.fromisoformat(after["next_due_at"]) >= NOW + minimum_delta
    assert after["lease_owner"] is None
    assert after["lease_until"] is None


def test_bounded_scanner_acquires_due_conditions_in_stable_order(tmp_path) -> None:
    repository, _service, scanner, _resolver, first_version, _condition = _runtime(tmp_path, limit=2)
    from app.theses.schemas import ThesisVersionRequest

    created = [first_version]
    for index in range(1, 4):
        created.append(
            repository.create_version(
                request=ThesisVersionRequest.model_validate(_payload(instrument=f"60051{index}.SH")),
                created_by="principal-opaque",
            )
        )

    first_batch = scanner.scan_once(now=NOW, owner="scanner-a")
    second_batch = scanner.scan_once(now=NOW, owner="scanner-a")

    assert len(first_batch) == 2
    assert len(second_batch) == 2
    expected_ids = sorted(version["conditions"][0]["id"] for version in created)
    assert [check["condition_id"] for check in first_batch + second_batch] == expected_ids


def test_duplicate_scanner_calls_return_one_check_per_condition_due_identity(tmp_path) -> None:
    repository, _service, scanner, resolver, _version, condition = _runtime(tmp_path)

    first = scanner.scan_once(now=NOW, owner="scanner-a")
    second = scanner.scan_once(now=NOW, owner="scanner-a")

    assert len(first) == 1
    assert second == []
    assert len(repository.list_checks(condition["id"])) == 1
    assert len(resolver.calls) == 1


def test_two_parallel_acquirers_have_one_lease_and_one_check_winner(tmp_path) -> None:
    repository, service, _scanner, resolver, _version, condition = _runtime(tmp_path)
    from app.theses.scheduler import ThesisDueScanner

    scanners = [
        ThesisDueScanner(repository=repository, service=service, batch_limit=1, lease_seconds=60)
        for _ in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(scanner.scan_once, now=NOW, owner=f"scanner-{index}") for index, scanner in enumerate(scanners)]
    results = [future.result() for future in futures]

    assert sorted(len(result) for result in results) == [0, 1]
    assert len(repository.list_checks(condition["id"])) == 1
    assert len(resolver.calls) == 1


def test_interruption_before_append_retries_same_due_after_lease_expiry(tmp_path) -> None:
    repository, service, scanner, _resolver, _version, condition = _runtime(tmp_path)
    original = service.evaluate_due_condition

    def interrupt(*, condition_id: str, due_at: str):
        raise InterruptedError(f"crash before append for {condition_id}@{due_at}")

    service.evaluate_due_condition = interrupt
    with pytest.raises(InterruptedError):
        scanner.scan_once(now=NOW, owner="scanner-crashed")
    assert repository.list_checks(condition["id"]) == []

    service.evaluate_due_condition = original
    restarted = scanner.scan_once(now=NOW + timedelta(seconds=61), owner="scanner-restarted")
    assert len(restarted) == 1
    assert restarted[0]["due_at"] == DUE_AT
    assert len(repository.list_checks(condition["id"])) == 1


def test_interruption_after_append_reuses_canonical_check_on_restart(tmp_path) -> None:
    repository, service, scanner, resolver, _version, condition = _runtime(tmp_path)
    original = service.evaluate_due_condition

    def interrupt_after(*, condition_id: str, due_at: str):
        original(condition_id=condition_id, due_at=due_at)
        raise InterruptedError("crash after append before cursor advance")

    service.evaluate_due_condition = interrupt_after
    with pytest.raises(InterruptedError):
        scanner.scan_once(now=NOW, owner="scanner-crashed")
    assert len(repository.list_checks(condition["id"])) == 1

    service.evaluate_due_condition = original
    restarted = scanner.scan_once(now=NOW + timedelta(seconds=61), owner="scanner-restarted")
    assert len(restarted) == 1
    assert restarted[0] == repository.list_checks(condition["id"])[0]
    assert len(resolver.calls) == 1
    assert datetime.fromisoformat(repository.get_schedule(condition["id"])["next_due_at"]) > NOW


def test_resolver_failure_appends_safe_error_check_and_advances_by_policy(tmp_path) -> None:
    resolver = FixedEvidenceResolver(fail=RuntimeError("database password=secret local=/tmp/operational.db"))
    repository, _service, scanner, _resolver, _version, condition = _runtime(tmp_path, resolver=resolver)

    checks = scanner.scan_once(now=NOW, owner="scanner-a")

    assert len(checks) == 1
    assert checks[0]["result"] == "error"
    assert checks[0]["observed_value"] is None
    assert checks[0]["evidence"] == []
    assert "password" not in repr(checks[0]).lower()
    assert "/tmp/" not in repr(checks[0])
    assert datetime.fromisoformat(repository.get_schedule(condition["id"])["next_due_at"]) > NOW


def test_process_restart_recovers_expired_lease_without_duplicate_evidence(tmp_path) -> None:
    repository, _service, _scanner, _resolver, _version, condition = _runtime(tmp_path)
    acquired = repository.acquire_due_conditions(
        now=NOW, owner="dead-process", lease_until=NOW + timedelta(seconds=60), limit=1
    )
    assert [item["condition_id"] for item in acquired] == [condition["id"]]

    from app.theses.repository import ThesisRepository
    from app.theses.scheduler import ThesisDueScanner
    from app.theses.service import ThesisService

    restarted_repository = ThesisRepository(repository.database_path, now=lambda: (NOW + timedelta(seconds=61)).isoformat())
    resolver = FixedEvidenceResolver()
    restarted = ThesisDueScanner(
        repository=restarted_repository,
        service=ThesisService(repository=restarted_repository, evidence_resolver=resolver),
        batch_limit=1,
        lease_seconds=60,
    )
    checks = restarted.scan_once(now=NOW + timedelta(seconds=61), owner="new-process")
    assert len(checks) == 1
    assert checks[0]["condition_id"] == condition["id"]
    assert len(restarted_repository.list_checks(condition["id"])) == 1


def test_old_version_conditions_are_excluded_from_new_due_acquisition(tmp_path) -> None:
    repository, service, scanner, resolver, first, old_condition = _runtime(tmp_path)
    from app.theses.schemas import ThesisRevisionRequest

    revision = ThesisRevisionRequest.model_validate(
        {"expected_predecessor_id": first["id"], "change_reason": "Filing update", "rationale": "Current evidence changed."}
    )
    second = repository.revise_version(thesis_id=first["thesis_id"], request=revision, created_by="principal-opaque")

    checks = scanner.scan_once(now=NOW, owner="scanner-a")

    assert [check["condition_id"] for check in checks] == [second["conditions"][0]["id"]]
    assert repository.list_checks(old_condition["id"]) == []
    assert all(call["instrument"] == "600519.SH" for call in resolver.calls)
    assert all(
        set(call["condition"])
        == {
            "source_kind",
            "field",
            "operator",
            "threshold",
            "unit",
            "lookback_days",
            "cadence",
            "timezone",
            "description",
        }
        for call in resolver.calls
    )
    assert repository.get_schedule(old_condition["id"])["active"] is False


def test_condition_due_identity_is_unique_and_checks_are_immutable(tmp_path) -> None:
    import sqlite3

    repository, _service, scanner, _resolver, _version, condition = _runtime(tmp_path)
    canonical = scanner.scan_once(now=NOW, owner="scanner-a")[0]

    assert repository.append_condition_check(
        version_id=canonical["version_id"], condition_id=condition["id"], due_at=canonical["due_at"],
        result=canonical["result"], evidence_fingerprint=canonical["evidence_fingerprint"],
        evidence=canonical["evidence"], checked_at=canonical["checked_at"],
    ) == canonical
    with sqlite3.connect(repository.database_path) as connection:
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            connection.execute("UPDATE thesis_condition_checks SET result = 'matched' WHERE id = ?", (canonical["id"],))
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            connection.execute("DELETE FROM thesis_condition_checks WHERE id = ?", (canonical["id"],))
