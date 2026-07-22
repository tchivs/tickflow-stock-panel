"""RED contracts for owned repository-bounded Thesis ledger routes."""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.theses.api import SubjectScope, router


class PagingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int, int]] = []

    def _page(self, resource: str, instrument: str, offset: int, limit: int) -> dict[str, Any]:
        self.calls.append((resource, instrument, offset, limit))
        return {
            "items": [{"id": f"{resource}-{offset}", "instrument": instrument}],
            "offset": offset,
            "limit": limit,
            "total": 5,
            "has_more": offset + limit < 5,
        }

    def versions_for_instrument(self, instrument: str, *, offset: int, limit: int) -> dict[str, Any]:
        return self._page("versions", instrument, offset, limit)

    def checks_for_instrument(self, instrument: str, *, offset: int, limit: int) -> dict[str, Any]:
        return self._page("checks", instrument, offset, limit)

    def pending_for_instrument(self, instrument: str, *, offset: int, limit: int) -> dict[str, Any]:
        return self._page("pending", instrument, offset, limit)

    def history_for_instrument(self, instrument: str, *, offset: int, limit: int) -> dict[str, Any]:
        return self._page("history", instrument, offset, limit)


def _client(*, allowed: frozenset[str] = frozenset({"600000.SH"})) -> tuple[TestClient, PagingService]:
    app = FastAPI()
    app.include_router(router)
    service = PagingService()
    app.state.thesis_service = service
    app.state.resolve_thesis_subject_scope = lambda _request: SubjectScope(allowed)

    @app.middleware("http")
    async def server_principal(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.reviewer_principal = "server-principal"
        return await call_next(request)

    return TestClient(app), service


def _assert_page(response, *, resource: str, offset: int, limit: int) -> None:
    assert response.status_code == 200
    assert response.json() == {
        "items": [{"id": f"{resource}-{offset}", "instrument": "600000.SH"}],
        "offset": offset,
        "limit": limit,
        "total": 5,
        "has_more": offset + limit < 5,
    }


def test_versions_page_passes_bounded_offset_and_limit_to_owned_service() -> None:
    client, service = _client()

    response = client.get("/api/theses/instruments/600000.SH/versions?offset=2&limit=1")

    _assert_page(response, resource="versions", offset=2, limit=1)
    assert service.calls == [("versions", "600000.SH", 2, 1)]
    assert client.get("/api/theses/instruments/600000.SH/versions?limit=101").status_code == 422


def test_checks_page_passes_bounded_offset_and_limit_to_owned_service() -> None:
    client, service = _client()

    response = client.get("/api/theses/instruments/600000.SH/checks?offset=1&limit=2")

    _assert_page(response, resource="checks", offset=1, limit=2)
    assert service.calls == [("checks", "600000.SH", 1, 2)]


def test_actionable_pending_page_passes_bounded_offset_and_limit_to_owned_service() -> None:
    client, service = _client()

    response = client.get("/api/theses/instruments/600000.SH/pending?offset=3&limit=1")

    _assert_page(response, resource="pending", offset=3, limit=1)
    assert service.calls == [("pending", "600000.SH", 3, 1)]


def test_all_version_history_page_is_bounded_and_reports_has_more() -> None:
    client, service = _client()

    response = client.get("/api/theses/instruments/600000.SH/history?offset=2&limit=2")

    _assert_page(response, resource="history", offset=2, limit=2)
    assert service.calls == [("history", "600000.SH", 2, 2)]


def test_ownership_before_pagination_rejects_foreign_instrument_without_querying_service() -> None:
    client, service = _client(allowed=frozenset({"600000.SH"}))

    response = client.get("/api/theses/instruments/000001.SZ/history?offset=0&limit=1")

    assert response.status_code == 404
    assert service.calls == []


def _payload(instrument: str = "600000.SH") -> dict[str, object]:
    from datetime import date

    return {
        "instrument": instrument,
        "core_judgment": "Pricing power supports durable free cash flow.",
        "rationale": "Governed filing evidence supports the judgment.",
        "change_reason": "Initial thesis record",
        "anchors": [
            {
                "method": "discounted_cash_flow",
                "currency": "CNY",
                "as_of": date(2026, 6, 30),
                "low": 1420.0,
                "high": 1680.0,
                "assumptions": [{"name": "discount_rate", "value": 0.085, "unit": "ratio"}],
                "limitations": ["Terminal-value sensitivity remains material."],
            }
        ],
        "conditions": [
            {
                "source_kind": "financial",
                "field": "revenue_growth_yoy",
                "operator": "lt",
                "threshold": 0.0,
                "unit": "ratio",
                "lookback_days": 120,
                "cadence": "quarterly",
                "timezone": "Asia/Shanghai",
                "description": "Revenue growth turns negative.",
            }
        ],
    }


def _repository_client(tmp_path, *, instrument: str = "600000.SH", allowed: frozenset[str] | None = None):
    from app.theses.repository import ThesisRepository
    from app.theses.schemas import ThesisRevisionRequest, ThesisVersionRequest
    from app.theses.service import ThesisService

    repository = ThesisRepository(tmp_path / "operational.db", now=lambda: "2026-07-01T00:00:00+00:00")
    first = repository.create_version(
        request=ThesisVersionRequest.model_validate(_payload(instrument)),
        created_by="principal-opaque",
    )
    old_condition = first["conditions"][0]
    old_check = repository.append_condition_check(
        version_id=first["id"],
        condition_id=old_condition["id"],
        due_at="2026-04-01T00:00:00+00:00",
        result="matched",
        evidence_fingerprint="a" * 64,
        evidence=[
            {
                "source_id": "filing-old",
                "source_revision": "v1",
                "source_kind": "financial",
                "field": "revenue_growth_yoy",
                "observed_value": -0.02,
                "unit": "ratio",
                "as_of": "2026-03-31",
            }
        ],
        checked_at="2026-04-01T00:05:00+00:00",
        observed_value=-0.02,
    )
    from uuid import uuid4

    pending_id = uuid4().hex
    with repository._connection() as connection, connection:
        connection.execute(
            """INSERT INTO thesis_pending_conclusions
               (id, thesis_id, version_id, condition_id, check_id,
                evidence_fingerprint, proposed_state, reason, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'invalidated', ?, 'pending', ?)""",
            (
                pending_id,
                first["thesis_id"],
                first["id"],
                old_condition["id"],
                old_check["id"],
                "a" * 64,
                "Structured condition matched governed evidence.",
                "2026-04-01T00:05:00+00:00",
            ),
        )
    second = repository.revise_version(
        thesis_id=first["thesis_id"],
        request=ThesisRevisionRequest.model_validate(
            {
                "expected_predecessor_id": first["id"],
                "change_reason": "Append newer evidence version",
                "rationale": "Second immutable version for ownership tests.",
            }
        ),
        created_by="principal-opaque",
    )
    service = ThesisService(repository=repository, evidence_resolver=None)
    app = FastAPI()
    app.include_router(router)
    app.state.thesis_service = service
    app.state.resolve_thesis_subject_scope = lambda _request: SubjectScope(
        allowed if allowed is not None else frozenset({instrument})
    )

    @app.middleware("http")
    async def server_principal(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.reviewer_principal = "server-principal"
        return await call_next(request)

    return TestClient(app), {
        "first": first,
        "second": second,
        "old_check": old_check,
        "old_pending_id": pending_id,
        "instrument": instrument,
    }


def _assert_safe_identity(item: dict[str, Any], *, instrument: str, version: dict[str, Any]) -> None:
    assert item["instrument"] == instrument
    assert item["thesis_id"] == version["thesis_id"]
    assert item["version_id"] == version["id"]
    assert item["version"] == version["version"]
    assert item["version_created_at"] == version["created_at"]
    assert item["version_official_state"] in {"active", "invalidated"}
    serialized = repr(item).lower()
    assert "principal-opaque" not in serialized
    assert "server-principal" not in serialized
    assert "reviewer" not in serialized or "reviewer_principal" not in serialized
    assert "operational.db" not in serialized
    assert "select " not in serialized


def test_ledger_row_identity_present_without_versions_page(tmp_path) -> None:
    client, state = _repository_client(tmp_path)
    instrument = state["instrument"]
    first = state["first"]

    checks = client.get(f"/api/theses/instruments/{instrument}/checks?offset=0&limit=10")
    history = client.get(f"/api/theses/instruments/{instrument}/history?offset=0&limit=10")

    assert checks.status_code == 200
    assert history.status_code == 200
    check_items = checks.json()["items"]
    history_items = history.json()["items"]
    assert len(check_items) == 1
    assert len(history_items) == 1
    _assert_safe_identity(check_items[0], instrument=instrument, version=first)
    assert check_items[0]["id"] == state["old_check"]["id"]
    assert check_items[0]["version_id"] == first["id"]
    assert check_items[0]["version"] == 1
    _assert_safe_identity(history_items[0], instrument=instrument, version=first)
    assert history_items[0]["id"] == state["old_pending_id"]
    assert history_items[0]["version"] == 1
    assert history_items[0]["state"] == "superseded"


def test_old_version_ledger_rows_remain_authorized_after_revision(tmp_path) -> None:
    client, state = _repository_client(tmp_path)
    instrument = state["instrument"]
    first = state["first"]
    second = state["second"]

    checks = client.get(f"/api/theses/instruments/{instrument}/checks?offset=0&limit=50").json()
    history = client.get(f"/api/theses/instruments/{instrument}/history?offset=0&limit=50").json()

    assert checks["total"] == 1
    assert history["total"] == 1
    assert checks["items"][0]["version_id"] == first["id"]
    assert checks["items"][0]["version"] == 1
    assert checks["items"][0]["version_id"] != second["id"]
    assert history["items"][0]["version_id"] == first["id"]
    assert history["items"][0]["version"] == 1
    assert history["has_more"] is False
    assert checks["has_more"] is False


def test_ownership_before_pagination_rejects_foreign_instrument_on_repository_pages(
    tmp_path,
) -> None:
    client, _state = _repository_client(tmp_path, allowed=frozenset({"600000.SH"}))

    response = client.get("/api/theses/instruments/000001.SZ/checks?offset=0&limit=1")
    history = client.get("/api/theses/instruments/000001.SZ/history?offset=0&limit=1")

    assert response.status_code == 404
    assert history.status_code == 404
