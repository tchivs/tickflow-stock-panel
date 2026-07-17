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
