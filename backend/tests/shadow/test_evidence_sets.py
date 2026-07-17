"""Shadow evidence-set RED contracts for explicit immutable membership."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

FIXTURES = Path(__file__).with_name("fixtures")
MAPPING = {
    "broker_fill_id": "成交编号",
    "symbol": "证券代码",
    "side": "买卖方向",
    "executed_at": "成交时间",
    "quantity": "成交数量",
    "price": "成交价格",
    "fees": "手续费",
    "currency": "币种",
    "account_alias": "账户别名",
}


def _stack(tmp_path, *, evidence_member_limit: int | None = None):
    from app.shadow.artifacts import ShadowArtifactStore
    from app.shadow.importer import ShadowImporter, ShadowImportLimits
    from app.shadow.repository import ShadowRepository

    repository_options = {} if evidence_member_limit is None else {"evidence_member_limit": evidence_member_limit}
    repository = ShadowRepository(tmp_path / "operational.db", **repository_options)
    artifacts = ShadowArtifactStore(tmp_path / "managed-shadow")
    importer = ShadowImporter(
        repository=repository,
        artifact_store=artifacts,
        limits=ShadowImportLimits(
            max_bytes=16_384,
            max_rows=20,
            max_columns=12,
            max_cell_chars=512,
        ),
    )
    return repository, importer


def _confirm(importer, fixture: str = "executions_utf8.csv", **overrides):
    path = FIXTURES / fixture
    payload = {
        "filename": fixture,
        "media_type": "text/csv",
        "content": path.read_bytes(),
        "mapping": MAPPING,
        "source_timezone": "Asia/Shanghai",
        "principal": "shadow-user-opaque",
        "source_label": "local-broker-export",
    }
    payload.update(overrides)
    preview = importer.preview(
        filename=payload["filename"],
        media_type=payload["media_type"],
        content=payload["content"],
        mapping=payload["mapping"],
        source_timezone=payload["source_timezone"],
        principal=payload["principal"],
    )
    payload["preview_identity"] = preview["preview_identity"]
    return importer.confirm_import(**payload)


def test_evidence_set_freezes_exact_batch_trade_manifest_and_stable_fingerprint(tmp_path):
    repository, importer = _stack(tmp_path)
    batch = _confirm(importer)
    trade_ids = [item["id"] for item in repository.list_trade_facts(batch_id=batch["id"])]

    first = repository.create_evidence_set(
        principal="shadow-user-opaque",
        included_batch_ids=[batch["id"]],
        included_trade_ids=list(reversed(trade_ids)),
        exclusions=[],
    )
    replay = repository.create_evidence_set(
        principal="shadow-user-opaque",
        included_batch_ids=[batch["id"]],
        included_trade_ids=trade_ids,
        exclusions=[],
    )

    assert first["included_batch_ids"] == [batch["id"]]
    assert first["included_trade_ids"] == trade_ids
    assert first["fingerprint"] == replay["fingerprint"]
    assert len(first["fingerprint"]) == 64
    assert repository.get_evidence_set(first["id"]) == first


def test_evidence_set_preserves_partial_fills_duplicate_groups_and_row_identity(
    tmp_path, monkeypatch
):
    next_identifier = 100

    def descending_identifier():
        nonlocal next_identifier
        next_identifier -= 1
        return SimpleNamespace(hex=f"{next_identifier:032x}")

    monkeypatch.setattr("app.shadow.importer.uuid4", descending_identifier)
    repository, importer = _stack(tmp_path)
    batch = _confirm(importer)
    trades = repository.list_trade_facts(batch_id=batch["id"])

    evidence = repository.create_evidence_set(
        principal="shadow-user-opaque",
        included_batch_ids=[batch["id"]],
        included_trade_ids=[item["id"] for item in trades],
        exclusions=[],
    )
    resolved = repository.resolve_evidence_trades(evidence_set_id=evidence["id"])

    partials = [item for item in resolved if item["broker_fill_id"] in {"FILL-002", "FILL-003"}]
    missing_ids = [item for item in resolved if item["broker_fill_id"] in {None, ""}]
    assert [item["quantity"] for item in partials] == [40.0, 60.0]
    assert len(missing_ids) == 2
    assert missing_ids[0]["row_identity"] != missing_ids[1]["row_identity"]
    assert missing_ids[0]["duplicate_group_hash"] == missing_ids[1]["duplicate_group_hash"]
    assert len(resolved) == len(trades)


def test_rejected_or_partial_batch_cannot_enter_evidence_set_silently(tmp_path):
    from app.shadow.importer import ShadowImportError

    repository, importer = _stack(tmp_path)
    with pytest.raises(ShadowImportError):
        importer.preview(
            filename="broken.csv",
            media_type="text/csv",
            content=b"\xff\xfe\x00broken",
            mapping=MAPPING,
            source_timezone="Asia/Shanghai",
            principal="shadow-user-opaque",
        )

    assert repository.list_import_batches(principal="shadow-user-opaque") == []
    assert repository.list_evidence_sets(principal="shadow-user-opaque") == []


def test_evidence_exclusions_name_exact_trade_and_nonempty_reason(tmp_path):
    from app.shadow.repository import ShadowEvidenceError

    repository, importer = _stack(tmp_path)
    batch = _confirm(importer)
    trades = repository.list_trade_facts(batch_id=batch["id"])
    excluded = trades[-1]["id"]
    included = [item["id"] for item in trades if item["id"] != excluded]

    evidence = repository.create_evidence_set(
        principal="shadow-user-opaque",
        included_batch_ids=[batch["id"]],
        included_trade_ids=included,
        exclusions=[{"trade_id": excluded, "reason": "hostile note excluded after review"}],
    )

    assert evidence["included_trade_ids"] == included
    assert evidence["exclusions"] == [
        {"trade_id": excluded, "reason": "hostile note excluded after review"}
    ]
    with pytest.raises(ShadowEvidenceError, match="reason"):
        repository.create_evidence_set(
            principal="shadow-user-opaque",
            included_batch_ids=[batch["id"]],
            included_trade_ids=included,
            exclusions=[{"trade_id": excluded, "reason": ""}],
        )


def test_evidence_set_and_membership_reject_direct_update_and_delete(tmp_path):
    repository, importer = _stack(tmp_path)
    batch = _confirm(importer)
    trades = repository.list_trade_facts(batch_id=batch["id"])
    evidence = repository.create_evidence_set(
        principal="shadow-user-opaque",
        included_batch_ids=[batch["id"]],
        included_trade_ids=[item["id"] for item in trades],
        exclusions=[],
    )

    with sqlite3.connect(repository.database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE shadow_evidence_sets SET fingerprint = ? WHERE id = ?",
                ("0" * 64, evidence["id"]),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM shadow_evidence_members WHERE evidence_set_id = ?",
                (evidence["id"],),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM shadow_evidence_sets WHERE id = ?", (evidence["id"],))

    assert repository.get_evidence_set(evidence["id"])["fingerprint"] == evidence["fingerprint"]


def test_correction_creates_new_manifest_while_earlier_evidence_remains_readable_and_safe(tmp_path):
    repository, importer = _stack(tmp_path)
    first_batch = _confirm(importer)
    first_trades = repository.list_trade_facts(batch_id=first_batch["id"])
    first_set = repository.create_evidence_set(
        principal="shadow-user-opaque",
        included_batch_ids=[first_batch["id"]],
        included_trade_ids=[item["id"] for item in first_trades],
        exclusions=[],
    )

    corrected_batch = _confirm(
        importer,
        "executions_gb18030.csv",
        supersedes_batch_id=first_batch["id"],
    )
    corrected_trades = repository.list_trade_facts(batch_id=corrected_batch["id"])
    corrected_set = repository.create_evidence_set(
        principal="shadow-user-opaque",
        included_batch_ids=[corrected_batch["id"]],
        included_trade_ids=[item["id"] for item in corrected_trades],
        exclusions=[],
    )

    assert first_set["id"] != corrected_set["id"]
    assert first_set["fingerprint"] != corrected_set["fingerprint"]
    assert repository.get_evidence_set(first_set["id"]) == first_set
    serialized = json.dumps(corrected_set, ensure_ascii=False).lower()
    assert str(tmp_path.resolve()).lower() not in serialized
    assert "acct-redacted" not in serialized
    assert "raw_bytes" not in serialized
    assert "account_secret" not in serialized


def test_aggregate_member_limit_rejects_before_evidence_materialization(tmp_path):
    from app.shadow.repository import ShadowEvidenceError

    repository, importer = _stack(tmp_path, evidence_member_limit=10)
    first = _confirm(importer)
    second = _confirm(importer, "executions_gb18030.csv")
    trade_ids = [
        item["id"]
        for batch in (first, second)
        for item in repository.list_trade_facts(batch_id=batch["id"])
    ]

    with pytest.raises(ShadowEvidenceError, match="aggregate member limit"):
        repository.create_evidence_set(
            principal="shadow-user-opaque",
            included_batch_ids=[first["id"], second["id"]],
            included_trade_ids=trade_ids,
            exclusions=[],
        )

    assert repository.list_evidence_sets(principal="shadow-user-opaque") == []


def test_repository_pagination_is_owned_deterministic_and_bounded(tmp_path):
    repository, importer = _stack(tmp_path)
    batches = [_confirm(importer) for _ in range(3)]
    _confirm(importer, principal="other-shadow-user")
    evidence_ids: list[str] = []
    for batch in batches[:2]:
        trade_ids = [item["id"] for item in repository.list_trade_facts(batch_id=batch["id"])]
        evidence_ids.append(
            repository.create_evidence_set(
                principal="shadow-user-opaque",
                included_batch_ids=[batch["id"]],
                included_trade_ids=trade_ids,
                exclusions=[],
            )["id"]
        )

    batch_page = repository.page_import_batches(
        principal="shadow-user-opaque", offset=1, limit=1
    )
    evidence_page = repository.page_evidence_sets(
        principal="shadow-user-opaque", offset=0, limit=1
    )

    assert batch_page["total"] == 3
    assert batch_page["has_more"] is True
    assert len(batch_page["items"]) == 1
    assert batch_page["items"][0]["principal"] == "shadow-user-opaque"
    assert batch_page["items"][0]["same_content_as"] in {batch["id"] for batch in batches}
    assert evidence_page["total"] == 2
    assert evidence_page["has_more"] is True
    assert len(evidence_page["items"]) == 1
    assert evidence_page["items"][0]["id"] in evidence_ids


def test_repository_pagination_drives_every_public_shadow_history(tmp_path):
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    from app.shadow.api import router

    class PageOnlyRepository:
        def __init__(self):
            self.calls: list[tuple[str, str, int, int]] = []

        def _page(self, resource: str, principal: str, offset: int, limit: int):
            self.calls.append((resource, principal, offset, limit))
            return {"items": [], "offset": offset, "limit": limit, "total": 0, "has_more": False}

        def page_import_batches(self, *, principal: str, offset: int, limit: int):
            return self._page("batches", principal, offset, limit)

        def page_evidence_sets(self, *, principal: str, offset: int, limit: int):
            return self._page("evidence", principal, offset, limit)

        def page_candidates(self, *, principal: str, offset: int, limit: int):
            return self._page("candidates", principal, offset, limit)

        def page_evaluations(self, *, principal: str, candidate_id, offset: int, limit: int):
            return self._page("evaluations", principal, offset, limit)

        def page_retention_events(self, *, principal: str, candidate_id, offset: int, limit: int):
            return self._page("retentions", principal, offset, limit)

        def __getattr__(self, name: str):
            if name.startswith("list_"):
                raise AssertionError("public history must not call an unbounded list method")
            raise AttributeError(name)

    repository = PageOnlyRepository()
    application = FastAPI()

    @application.middleware("http")
    async def bind_principal(request: Request, call_next):
        request.state.reviewer_principal = "shadow-user-opaque"
        return await call_next(request)

    application.include_router(router)
    application.state.shadow_repository = repository

    with TestClient(application, raise_server_exceptions=False) as client:
        for path in (
            "/api/shadow/batches",
            "/api/shadow/evidence-sets",
            "/api/shadow/candidates",
            "/api/shadow/evaluations",
            "/api/shadow/retentions",
        ):
            response = client.get(path, params={"offset": 50, "limit": 25})
            assert response.status_code == 200, path
            assert response.json()["page"] == {
                "offset": 50,
                "limit": 25,
                "total": 0,
                "has_more": False,
            }

    assert {call[0] for call in repository.calls} == {
        "batches",
        "evidence",
        "candidates",
        "evaluations",
        "retentions",
    }
    assert all(call[1:] == ("shadow-user-opaque", 50, 25) for call in repository.calls)


def test_repository_pagination_filters_candidate_evaluation_and_retention_sql(tmp_path):
    from tests.shadow.test_evaluation_retention import (
        _persisted_retention_fixture,
        _retain,
    )

    repository, service, evaluations = _persisted_retention_fixture(tmp_path)
    retention = _retain(service, evaluations)

    candidate_page = repository.page_candidates(
        principal="shadow-user-opaque", offset=0, limit=10
    )
    evaluation_page = repository.page_evaluations(
        principal="shadow-user-opaque", candidate_id=None, offset=0, limit=10
    )
    retention_page = repository.page_retention_events(
        principal="shadow-user-opaque", candidate_id=None, offset=0, limit=10
    )

    assert [item["id"] for item in candidate_page["items"]] == ["candidate-1"]
    assert {item["id"] for item in evaluation_page["items"]} == {
        evaluations["in_sample"]["id"],
        evaluations["out_of_sample"]["id"],
    }
    assert [item["id"] for item in retention_page["items"]] == [retention["id"]]
    other_pages = (
        repository.page_candidates(
            principal="other-shadow-user", offset=0, limit=10
        ),
        repository.page_evaluations(
            principal="other-shadow-user", candidate_id=None, offset=0, limit=10
        ),
        repository.page_retention_events(
            principal="other-shadow-user", candidate_id=None, offset=0, limit=10
        ),
    )
    assert all(page["items"] == [] and page["total"] == 0 for page in other_pages)
