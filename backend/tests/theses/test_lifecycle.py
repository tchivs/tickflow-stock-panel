"""Strict RED contracts for pending-only thesis invalidation and human review authority."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime

import pytest

DUE_AT = datetime(2026, 7, 1, tzinfo=UTC).isoformat()
FORBIDDEN_ACTIONS = (
    "register_strategy",
    "activate_strategy",
    "create_monitor",
    "create_decision_plan",
    "mutate_portfolio",
    "mutate_position",
    "place_broker_order",
    "publish_market_action",
)


class FixedEvidenceResolver:
    def __init__(self, result: str = "matched") -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def resolve(
        self, *, condition: dict[str, object], due_at: str, instrument: str | None = None
    ) -> dict[str, object]:
        self.calls.append(
            {"condition": deepcopy(condition), "due_at": due_at, "instrument": instrument}
        )
        observed = -0.02 if self.result == "matched" else 0.04
        if self.result in {"insufficient_evidence", "error"}:
            observed = None
        return {
            "result": self.result,
            "observed_value": observed,
            "unit": "ratio",
            "as_of": "2026-06-30",
            "evidence": [] if observed is None else [{
                "source_id": "filing-2026q2",
                "source_revision": "exchange-v1",
                "field": "revenue_growth_yoy",
                "observed_value": observed,
                "unit": "ratio",
                "as_of": "2026-06-30",
            }],
            "evidence_fingerprint": "f" * 64,
        }


class ActionAuditedRepository:
    """Delegates thesis storage while turning accidental trading-domain calls into visible spies."""

    def __init__(self, repository) -> None:
        self.repository = repository
        self.forbidden_calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def __getattr__(self, name: str):
        if name in FORBIDDEN_ACTIONS:
            def forbidden(*args, **kwargs):
                self.forbidden_calls.append((name, args, kwargs))
                return {"unexpected": True}
            return forbidden
        return getattr(self.repository, name)


def _payload() -> dict[str, object]:
    return {
        "instrument": "600519.SH",
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
            "cadence": "quarterly", "timezone": "Asia/Shanghai",
            "description": "Revenue growth turns negative.",
        }],
    }


def _runtime(tmp_path, *, result: str = "matched"):
    from app.theses.repository import ThesisRepository
    from app.theses.schemas import ThesisVersionRequest
    from app.theses.service import ThesisService

    repository = ThesisRepository(tmp_path / "operational.db", now=lambda: DUE_AT)
    version = repository.create_version(
        request=ThesisVersionRequest.model_validate(_payload()), created_by="principal-opaque"
    )
    audited = ActionAuditedRepository(repository)
    resolver = FixedEvidenceResolver(result)
    service = ThesisService(repository=audited, evidence_resolver=resolver)
    return repository, audited, resolver, service, version, version["conditions"][0]


@pytest.mark.parametrize(
    "result",
    ("matched", "not_matched", "insufficient_evidence", "error"),
    ids=("matched", "not-matched", "insufficient", "error"),
)
def test_each_evidence_result_appends_one_exact_immutable_check(tmp_path, result) -> None:
    repository, _audited, _resolver, service, version, condition = _runtime(tmp_path, result=result)

    outcome = service.evaluate_due_condition(condition_id=condition["id"], due_at=DUE_AT)
    checks = repository.list_checks(condition["id"])

    assert checks == [outcome["check"]]
    assert outcome["check"]["version_id"] == version["id"]
    assert outcome["check"]["condition_id"] == condition["id"]
    assert outcome["check"]["due_at"] == DUE_AT
    assert outcome["check"]["result"] == result
    assert outcome["check"]["evidence_fingerprint"] == "f" * 64
    assert outcome["pending"] is not None if result == "matched" else outcome["pending"] is None


def test_matched_check_creates_exactly_one_evidence_linked_pending_conclusion(tmp_path) -> None:
    repository, _audited, resolver, service, version, condition = _runtime(tmp_path)

    first = service.evaluate_due_condition(condition_id=condition["id"], due_at=DUE_AT)
    replay = service.evaluate_due_condition(condition_id=condition["id"], due_at=DUE_AT)

    assert replay == first
    assert first["pending"]["version_id"] == version["id"]
    assert first["pending"]["condition_id"] == condition["id"]
    assert first["pending"]["check_id"] == first["check"]["id"]
    assert first["pending"]["evidence_fingerprint"] == first["check"]["evidence_fingerprint"]
    assert first["pending"]["proposed_state"] == "invalidated"
    assert len(repository.list_pending(version["thesis_id"])) == 1
    assert len(resolver.calls) == 1


def test_not_matched_insufficient_and_error_never_create_pending_or_false_zero(tmp_path) -> None:
    for index, result in enumerate(("not_matched", "insufficient_evidence", "error")):
        repository, _audited, _resolver, service, version, condition = _runtime(tmp_path / str(index), result=result)
        outcome = service.evaluate_due_condition(condition_id=condition["id"], due_at=DUE_AT)
        assert outcome["pending"] is None
        assert repository.list_pending(version["thesis_id"]) == []
        if result in {"insufficient_evidence", "error"}:
            assert outcome["check"]["observed_value"] is None
            assert outcome["check"]["result"] == result
            assert outcome["check"]["result"] not in {False, 0, "not_matched"}


def test_automation_never_changes_official_state_or_opens_dialogs(tmp_path) -> None:
    repository, audited, _resolver, service, version, condition = _runtime(tmp_path)

    outcome = service.evaluate_due_condition(condition_id=condition["id"], due_at=DUE_AT)

    assert outcome["pending"]["status"] == "pending"
    assert service.official_state(version["thesis_id"]) == "active"
    assert repository.list_official_events(version["thesis_id"]) == []
    assert audited.forbidden_calls == []
    assert "dialog" not in repr(outcome).lower()


def test_confirmation_requires_session_derived_server_principal(tmp_path) -> None:
    repository, _audited, _resolver, service, _version, condition = _runtime(tmp_path)
    pending = service.evaluate_due_condition(condition_id=condition["id"], due_at=DUE_AT)["pending"]

    with pytest.raises(ValueError, match=r"principal|authenticated"):
        service.confirm(pending_id=pending["id"], rationale="Reviewed exact evidence.", reviewer_principal=None)
    with pytest.raises(TypeError):
        service.confirm(
            pending_id=pending["id"], rationale="Reviewed exact evidence.", reviewer_principal="opaque",
            official_state="invalidated", evidence_fingerprint="browser-controlled",
        )
    assert repository.list_review_events(pending["id"]) == []


def test_confirmation_revalidates_evidence_and_appends_one_official_event(tmp_path) -> None:
    repository, _audited, resolver, service, version, condition = _runtime(tmp_path)
    pending = service.evaluate_due_condition(condition_id=condition["id"], due_at=DUE_AT)["pending"]

    confirmed = service.confirm(
        pending_id=pending["id"],
        rationale="Reviewed the exact filing and condition result.",
        reviewer_principal="reviewer-principal-opaque",
    )

    assert confirmed["official_state"] == "invalidated"
    assert confirmed["event"]["pending_id"] == pending["id"]
    assert confirmed["event"]["version_id"] == version["id"]
    assert confirmed["event"]["condition_id"] == condition["id"]
    assert confirmed["event"]["check_id"] == pending["check_id"]
    assert confirmed["event"]["evidence_fingerprint"] == "f" * 64
    assert confirmed["event"]["reviewer_principal"] == "reviewer-principal-opaque"
    assert len(repository.list_official_events(version["thesis_id"])) == 1
    assert len(resolver.calls) == 2


def test_confirmation_conflicts_when_governed_evidence_no_longer_matches(tmp_path) -> None:
    repository, _audited, resolver, service, version, condition = _runtime(tmp_path)
    pending = service.evaluate_due_condition(condition_id=condition["id"], due_at=DUE_AT)["pending"]
    resolver.result = "not_matched"

    with pytest.raises(ValueError, match=r"stale|evidence|conflict|match"):
        service.confirm(
            pending_id=pending["id"], rationale="Attempted stale confirmation.",
            reviewer_principal="reviewer-principal-opaque",
        )
    assert service.official_state(version["thesis_id"]) == "active"
    assert repository.list_review_events(pending["id"]) == []


def test_rejection_appends_review_and_preserves_official_state(tmp_path) -> None:
    repository, _audited, _resolver, service, version, condition = _runtime(tmp_path)
    pending = service.evaluate_due_condition(condition_id=condition["id"], due_at=DUE_AT)["pending"]

    rejected = service.reject(
        pending_id=pending["id"], rationale="Evidence is valid but not sufficient to invalidate.",
        reviewer_principal="reviewer-principal-opaque",
    )

    assert rejected["decision"] == "rejected"
    assert rejected["official_state"] == "active"
    assert service.official_state(version["thesis_id"]) == "active"
    assert repository.list_official_events(version["thesis_id"]) == []
    assert repository.list_review_events(pending["id"])[0]["rationale"].startswith("Evidence is valid")


def test_duplicate_or_already_processed_review_is_a_conflict(tmp_path) -> None:
    _repository, _audited, _resolver, service, _version, condition = _runtime(tmp_path)
    pending = service.evaluate_due_condition(condition_id=condition["id"], due_at=DUE_AT)["pending"]
    service.confirm(
        pending_id=pending["id"], rationale="First canonical decision.",
        reviewer_principal="reviewer-principal-opaque",
    )

    for operation in (service.confirm, service.reject):
        with pytest.raises(ValueError, match=r"processed|conflict|immutable|confirmed"):
            operation(
                pending_id=pending["id"], rationale="Replay must fail.",
                reviewer_principal="reviewer-principal-opaque",
            )


def test_old_version_pending_conflicts_after_new_version_becomes_current(tmp_path) -> None:
    repository, _audited, _resolver, service, first, condition = _runtime(tmp_path)
    pending = service.evaluate_due_condition(condition_id=condition["id"], due_at=DUE_AT)["pending"]
    from app.theses.schemas import ThesisRevisionRequest

    revision = ThesisRevisionRequest.model_validate(
        {"expected_predecessor_id": first["id"], "change_reason": "New filing", "rationale": "New current version."}
    )
    repository.revise_version(thesis_id=first["thesis_id"], request=revision, created_by="principal-opaque")

    with pytest.raises(ValueError, match=r"old|current|stale|conflict"):
        service.confirm(
            pending_id=pending["id"], rationale="Old version cannot become official.",
            reviewer_principal="reviewer-principal-opaque",
        )
    assert service.official_state(first["thesis_id"]) == "active"


def test_competing_pending_review_conflicts_after_official_state_changes(tmp_path) -> None:
    repository, _audited, _resolver, service, version, condition = _runtime(tmp_path)
    first_pending = service.evaluate_due_condition(condition_id=condition["id"], due_at=DUE_AT)["pending"]
    second_pending = service.evaluate_due_condition(
        condition_id=condition["id"], due_at="2026-10-01T00:00:00+00:00"
    )["pending"]
    service.confirm(
        pending_id=first_pending["id"], rationale="First valid official event.",
        reviewer_principal="reviewer-principal-opaque",
    )

    with pytest.raises(ValueError, match=r"state|stale|conflict"):
        service.confirm(
            pending_id=second_pending["id"], rationale="Competing event is stale.",
            reviewer_principal="reviewer-principal-opaque",
        )
    assert len(repository.list_official_events(version["thesis_id"])) == 1


def test_review_and_check_history_remain_readable_but_public_projection_is_safe(tmp_path) -> None:
    repository, _audited, _resolver, service, version, condition = _runtime(tmp_path)
    pending = service.evaluate_due_condition(condition_id=condition["id"], due_at=DUE_AT)["pending"]
    service.reject(
        pending_id=pending["id"], rationale="Keep active after human review.",
        reviewer_principal="reviewer-principal-opaque",
    )

    internal = repository.list_review_events(pending["id"])[0]
    assert internal["pending_id"] == pending["id"]
    assert internal["reviewer_principal"] == "reviewer-principal-opaque"
    history = service.history(version["thesis_id"])
    assert history["versions"][0]["conditions"][0]["checks"][0]["evidence_fingerprint"] == "f" * 64
    assert history["pending"][0]["review"]["decision"] == "rejected"
    serialized = repr(history).lower()
    assert "reviewer-principal-opaque" not in serialized
    assert "operational.db" not in serialized
    assert "select " not in serialized
    assert "traceback" not in serialized
    assert "raw_evidence" not in serialized


def test_lifecycle_invokes_zero_strategy_monitor_plan_portfolio_or_broker_actions(tmp_path) -> None:
    _repository, audited, _resolver, service, _version, condition = _runtime(tmp_path)
    pending = service.evaluate_due_condition(condition_id=condition["id"], due_at=DUE_AT)["pending"]
    service.confirm(
        pending_id=pending["id"], rationale="Human confirmation changes thesis state only.",
        reviewer_principal="reviewer-principal-opaque",
    )

    assert audited.forbidden_calls == []


def test_strict_resolver_payload_uses_condition_timezone_and_instrument_identity(tmp_path) -> None:
    from app.theses.evidence import GovernedEvidenceResolver
    from app.theses.repository import ThesisRepository
    from app.theses.schemas import ThesisVersionRequest
    from app.theses.service import ThesisService

    due_at = "2026-07-01T16:00:00+00:00"

    class RecordingReader:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def __call__(
            self, *, instrument: str, field: str, as_of: date, lookback_days: int
        ) -> dict[str, object]:
            self.calls.append(
                {
                    "instrument": instrument,
                    "field": field,
                    "as_of": as_of,
                    "lookback_days": lookback_days,
                }
            )
            return {
                "observed_value": -0.02,
                "unit": "ratio",
                "as_of": as_of,
                "source_id": "filing-2026q2",
                "source_revision": "exchange-v1",
            }

    reader = RecordingReader()
    governed = GovernedEvidenceResolver(
        market_reader=reader,
        financial_reader=reader,
        analysis_reader=reader,
    )

    class CapturingResolver:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def resolve(self, **kwargs: object) -> dict[str, object]:
            self.calls.append(deepcopy(kwargs))
            return governed.resolve(**kwargs)

    repository = ThesisRepository(tmp_path / "operational.db", now=lambda: due_at)
    version = repository.create_version(
        request=ThesisVersionRequest.model_validate(_payload()),
        created_by="principal-opaque",
    )
    resolver = CapturingResolver()
    service = ThesisService(repository=repository, evidence_resolver=resolver)

    outcome = service.evaluate_due_condition(
        condition_id=version["conditions"][0]["id"], due_at=due_at
    )

    assert outcome["check"]["result"] == "matched", (outcome, resolver.calls, reader.calls)
    assert reader.calls == [
        {
            "instrument": "600519.SH",
            "field": "revenue_growth_yoy",
            "as_of": date(2026, 7, 2),
            "lookback_days": 120,
        }
    ]
    assert resolver.calls[0]["instrument"] == "600519.SH"
    assert set(resolver.calls[0]["condition"]) == {
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
    strict_condition = resolver.calls[0]["condition"]
    other_instrument = governed.resolve(
        condition=strict_condition,
        due_at=due_at,
        instrument="000001.SZ",
    )
    assert other_instrument["evidence_fingerprint"] != outcome["check"]["evidence_fingerprint"]


def _pending_history_runtime(tmp_path):
    from app.theses.repository import ThesisRepository
    from app.theses.schemas import ThesisRevisionRequest, ThesisVersionRequest
    from app.theses.service import ThesisService

    repository = ThesisRepository(tmp_path / "operational.db", now=lambda: DUE_AT)
    first = repository.create_version(
        request=ThesisVersionRequest.model_validate(_payload()),
        created_by="principal-opaque",
    )
    service = ThesisService(repository=repository, evidence_resolver=FixedEvidenceResolver())
    first_pending = service.evaluate_due_condition(
        condition_id=first["conditions"][0]["id"], due_at="2026-07-01T00:00:00+00:00"
    )["pending"]

    def revise(predecessor: dict[str, object], label: str) -> dict[str, object]:
        request = ThesisRevisionRequest.model_validate(
            {
                "expected_predecessor_id": predecessor["id"],
                "change_reason": f"{label} filing",
                "rationale": f"{label} governed evidence changed the current version.",
            }
        )
        return repository.revise_version(
            thesis_id=first["thesis_id"], request=request, created_by="principal-opaque"
        )

    second = revise(first, "Second")
    second_pending = service.evaluate_due_condition(
        condition_id=second["conditions"][0]["id"], due_at="2026-07-02T00:00:00+00:00"
    )["pending"]
    service.reject(
        pending_id=second_pending["id"],
        rationale="Governed evidence was reviewed but did not invalidate the thesis.",
        reviewer_principal="reviewer-principal-opaque",
    )
    third = revise(second, "Third")
    current_pending = service.evaluate_due_condition(
        condition_id=third["conditions"][0]["id"], due_at="2026-07-03T00:00:00+00:00"
    )["pending"]
    return repository, service, first_pending, second_pending, current_pending


def test_actionable_pending_contains_only_current_unreviewed_conclusions(tmp_path) -> None:
    _repository, service, first_pending, second_pending, current_pending = _pending_history_runtime(tmp_path)

    page = service.pending_for_instrument("600519.SH", offset=0, limit=10)

    assert [item["id"] for item in page["items"]] == [current_pending["id"]]
    assert page == {
        "items": page["items"],
        "offset": 0,
        "limit": 10,
        "total": 1,
        "has_more": False,
    }
    assert first_pending["id"] not in {item["id"] for item in page["items"]}
    assert second_pending["id"] not in {item["id"] for item in page["items"]}


def test_paged_history_preserves_superseded_reviewed_and_actionable_state(tmp_path) -> None:
    _repository, service, first_pending, second_pending, current_pending = _pending_history_runtime(tmp_path)

    pages = [service.history_for_instrument("600519.SH", offset=offset, limit=1) for offset in range(3)]
    items = [page["items"][0] for page in pages]
    states = {item["id"]: item["state"] for item in items}

    assert all(page["total"] == 3 for page in pages)
    assert [page["has_more"] for page in pages] == [True, True, False]
    assert states == {
        first_pending["id"]: "superseded",
        second_pending["id"]: "rejected",
        current_pending["id"]: "actionable",
    }


def test_paged_history_executes_limit_and_offset_before_materialization(tmp_path) -> None:
    from contextlib import contextmanager

    from app.theses.repository import ThesisRepository
    from app.theses.schemas import ThesisVersionRequest
    from app.theses.service import ThesisService

    class TracingRepository(ThesisRepository):
        def __init__(self, *args, **kwargs) -> None:
            self.statements: list[str] = []
            super().__init__(*args, **kwargs)

        @contextmanager
        def _connection(self):
            with super()._connection() as connection:
                connection.set_trace_callback(self.statements.append)
                yield connection

    repository = TracingRepository(tmp_path / "operational.db", now=lambda: DUE_AT)
    version = repository.create_version(
        request=ThesisVersionRequest.model_validate(_payload()),
        created_by="principal-opaque",
    )
    service = ThesisService(repository=repository, evidence_resolver=FixedEvidenceResolver())
    condition_id = version["conditions"][0]["id"]
    for day in range(1, 4):
        service.evaluate_due_condition(
            condition_id=condition_id,
            due_at=f"2026-07-0{day}T00:00:00+00:00",
        )
    repository.statements.clear()

    page = service.history_for_instrument("600519.SH", offset=1, limit=1)

    assert len(page["items"]) == 1
    assert page["total"] == 3
    bounded_queries = [statement.upper() for statement in repository.statements if "THESIS_PENDING_CONCLUSIONS" in statement.upper()]
    assert any("LIMIT 1 OFFSET 1" in statement for statement in bounded_queries)
