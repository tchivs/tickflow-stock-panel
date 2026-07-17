"""Shadow import RED contracts: local-only, bounded, immutable, and safe by construction."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

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


def _stack(tmp_path):
    from app.shadow.artifacts import ShadowArtifactStore
    from app.shadow.importer import ShadowImporter, ShadowImportLimits
    from app.shadow.repository import ShadowRepository

    repository = ShadowRepository(tmp_path / "operational.db")
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
    return repository, artifacts, importer


def _preview(importer, fixture: str, media_type: str):
    path = FIXTURES / fixture
    return importer.preview(
        filename=fixture,
        media_type=media_type,
        content=path.read_bytes(),
        mapping=MAPPING,
        source_timezone="Asia/Shanghai",
        principal="shadow-user-opaque",
    )


def _confirm(importer, fixture: str, media_type: str, **overrides):
    path = FIXTURES / fixture
    payload = {
        "filename": fixture,
        "media_type": media_type,
        "content": path.read_bytes(),
        "mapping": MAPPING,
        "source_timezone": "Asia/Shanghai",
        "principal": "shadow-user-opaque",
        "source_label": "local-broker-export",
    }
    payload.update(overrides)
    if "preview_identity" not in payload:
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


def _assert_safe_projection(value: object, managed_root: Path) -> None:
    forbidden_keys = {
        "absolute_path",
        "local_path",
        "raw_bytes",
        "account_secret",
        "traceback",
        "exception",
    }
    if isinstance(value, dict):
        assert forbidden_keys.isdisjoint(value)
        for nested in value.values():
            _assert_safe_projection(nested, managed_root)
    elif isinstance(value, list):
        for nested in value:
            _assert_safe_projection(nested, managed_root)
    elif isinstance(value, str):
        assert str(managed_root.resolve()) not in value
        assert "acct-redacted" not in value
        assert "Traceback (most recent call last)" not in value


def test_preview_accepts_only_bounded_local_csv_xlsx_and_preserves_source_values(tmp_path):
    repository, _artifacts, importer = _stack(tmp_path)

    utf8 = _preview(importer, "executions_utf8.csv", "text/csv")
    workbook = _preview(
        importer,
        "executions.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    assert utf8["status"] == workbook["status"] == "preview_ready"
    assert utf8["encoding"] == "utf-8"
    assert len(utf8["rows"]) == len(workbook["rows"]) == 7
    assert utf8["rows"][0]["source_values"]["成交价格"] == "10.50"
    assert utf8["rows"][0]["normalized"]["symbol"] == "600000.SH"
    assert repository.list_import_batches(principal="shadow-user-opaque") == []


def test_preview_normalizes_gb18030_time_and_keeps_partial_and_duplicate_rows(tmp_path):
    _repository, _artifacts, importer = _stack(tmp_path)

    preview = _preview(importer, "executions_gb18030.csv", "text/csv")
    rows = preview["rows"]

    assert preview["encoding"] == "gb18030"
    assert rows[0]["normalized"]["executed_at"] == "2026-01-05T09:31:00+08:00"
    assert rows[0]["source_values"]["成交时间"] == "2026-01-05 09:31:00+08:00"
    assert [row["normalized"]["quantity"] for row in rows[1:3]] == [40.0, 60.0]
    assert rows[3]["row_identity"] != rows[4]["row_identity"]
    assert rows[3]["duplicate_group_hash"] == rows[4]["duplicate_group_hash"]
    assert rows[3]["source_row_ordinal"] != rows[4]["source_row_ordinal"]



def test_preview_identity_binds_exact_transform_and_principal(tmp_path):
    repository, _artifacts, importer = _stack(tmp_path)
    path = FIXTURES / "executions_utf8.csv"
    request = {
        "filename": path.name,
        "media_type": "text/csv",
        "content": path.read_bytes(),
        "mapping": MAPPING,
        "source_timezone": "Asia/Shanghai",
        "principal": "shadow-user-opaque",
    }

    first = importer.preview(**request)
    replay = importer.preview(**request)
    without_optional_mapping = importer.preview(
        **{**request, "mapping": {key: value for key, value in MAPPING.items() if key != "fees"}}
    )
    other_timezone = importer.preview(**{**request, "source_timezone": "UTC"})
    other_principal = importer.preview(**{**request, "principal": "other-shadow-user"})

    assert first["preview_identity"] == replay["preview_identity"]
    assert len(first["preview_identity"]) == 64
    assert {
        without_optional_mapping["preview_identity"],
        other_timezone["preview_identity"],
        other_principal["preview_identity"],
    }.isdisjoint({first["preview_identity"]})
    assert repository.list_import_batches(principal="shadow-user-opaque") == []


def test_confirm_rejects_stale_preview_before_persistence(tmp_path):
    from app.shadow.importer import ShadowImportError

    repository, artifacts, importer = _stack(tmp_path)
    path = FIXTURES / "executions_utf8.csv"
    request = {
        "filename": path.name,
        "media_type": "text/csv",
        "content": path.read_bytes(),
        "mapping": MAPPING,
        "source_timezone": "Asia/Shanghai",
        "principal": "shadow-user-opaque",
    }
    identity = importer.preview(**request)["preview_identity"]
    changed_requests = (
        {**request, "content": request["content"] + b"\n"},
        {**request, "mapping": {key: value for key, value in MAPPING.items() if key != "fees"}},
        {**request, "source_timezone": "UTC"},
    )

    for changed in changed_requests:
        with pytest.raises(ShadowImportError, match="preview identity"):
            importer.confirm_import(
                **changed,
                preview_identity=identity,
                source_label="local-broker-export",
            )

    assert repository.list_import_batches(principal="shadow-user-opaque") == []
    assert artifacts.managed_paths() == []


def test_exact_preview_identity_confirms_immutable_batch(tmp_path):
    repository, _artifacts, importer = _stack(tmp_path)
    path = FIXTURES / "executions_utf8.csv"
    request = {
        "filename": path.name,
        "media_type": "text/csv",
        "content": path.read_bytes(),
        "mapping": MAPPING,
        "source_timezone": "Asia/Shanghai",
        "principal": "shadow-user-opaque",
    }
    identity = importer.preview(**request)["preview_identity"]

    batch = importer.confirm_import(
        **request,
        preview_identity=identity,
        source_label="local-broker-export",
    )

    assert repository.get_import_batch(batch["id"])["id"] == batch["id"]
    assert repository.list_operational_mutations() == []

def test_confirm_rejects_stale_preview_at_api_boundary(tmp_path):
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    from app.shadow.api import router
    from app.shadow.service import ShadowService

    repository, _artifacts, importer = _stack(tmp_path)
    application = FastAPI()

    @application.middleware("http")
    async def bind_principal(request: Request, call_next):
        request.state.reviewer_principal = "shadow-user-opaque"
        return await call_next(request)

    application.include_router(router)
    application.state.shadow_repository = repository
    application.state.shadow_service = ShadowService(
        repository=repository,
        evaluation_service=object(),
        importer=importer,
    )
    path = FIXTURES / "executions_utf8.csv"
    preview_form = {
        "mapping": json.dumps(MAPPING),
        "source_timezone": "Asia/Shanghai",
    }

    with TestClient(application) as client:
        preview_response = client.post(
            "/api/shadow/imports/preview",
            data=preview_form,
            files={"file": (path.name, path.read_bytes(), "text/csv")},
        )
        assert preview_response.status_code == 200
        identity = preview_response.json()["preview"]["preview_identity"]

        response = client.post(
            "/api/shadow/imports/confirm",
            data={
                **preview_form,
                "source_timezone": "UTC",
                "source_label": "local-broker-export",
                "preview_identity": identity,
            },
            files={"file": (path.name, path.read_bytes(), "text/csv")},
        )

    assert response.status_code == 409
    assert repository.list_import_batches(principal="shadow-user-opaque") == []


def test_rejects_extension_media_archive_and_preparse_limits_without_parser_work(tmp_path):
    from app.shadow.importer import ShadowImportError

    repository, artifacts, importer = _stack(tmp_path)
    invalid = [
        ("executions.zip", "application/zip", b"PK\x03\x04archive"),
        ("executions.xlsm", "application/vnd.ms-excel.sheet.macroEnabled.12", b"macro"),
        ("executions.csv", "application/octet-stream", b"a,b\n1,2\n"),
        ("../executions.csv", "text/csv", b"a,b\n1,2\n"),
        ("executions.csv", "text/csv", b"x" * 16_385),
    ]

    for filename, media_type, content in invalid:
        with pytest.raises(ShadowImportError):
            importer.preview(
                filename=filename,
                media_type=media_type,
                content=content,
                mapping=MAPPING,
                source_timezone="Asia/Shanghai",
                principal="shadow-user-opaque",
            )

    assert repository.list_import_batches(principal="shadow-user-opaque") == []
    assert artifacts.list_temporary_namespaces() == []


def test_formula_macro_and_hostile_path_cells_are_never_executed_or_used_as_paths(
    tmp_path, monkeypatch
):
    _repository, artifacts, importer = _stack(tmp_path)
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(os, "system", lambda command: calls.append(("system", command)))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: calls.append(("run", args)))
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: calls.append(("popen", args)))

    preview = _preview(importer, "executions.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    notes = [row["source_values"]["备注"] for row in preview["rows"]]

    assert any(note.startswith("=HYPERLINK(") for note in notes)
    assert any("../../../../etc/passwd" in note and "Auto_Open" in note for note in notes)
    assert calls == []
    assert all(Path(path).resolve().is_relative_to(artifacts.root.resolve()) for path in artifacts.managed_paths())


def test_confirm_creates_atomic_server_owned_artifact_and_safe_projection(tmp_path):
    repository, artifacts, importer = _stack(tmp_path)

    batch = _confirm(importer, "executions_utf8.csv", "text/csv")
    persisted = repository.get_import_batch(batch["id"])
    trades = repository.list_trade_facts(batch_id=batch["id"])
    descriptor = persisted["raw_artifact"]

    assert persisted["status"] == "completed"
    assert persisted["principal"] == "shadow-user-opaque"
    assert len(trades) == 7
    assert descriptor["relative_path"].startswith(f'{batch["id"]}/')
    assert descriptor["byte_size"] == (FIXTURES / "executions_utf8.csv").stat().st_size
    assert len(descriptor["checksum_sha256"]) == 64
    assert artifacts.load(descriptor) == (FIXTURES / "executions_utf8.csv").read_bytes()
    assert artifacts.list_temporary_namespaces() == []
    _assert_safe_projection(batch, artifacts.root)


def test_same_content_retry_and_correction_append_distinct_attributable_batches(tmp_path):
    repository, artifacts, importer = _stack(tmp_path)

    first = _confirm(importer, "executions_utf8.csv", "text/csv")
    repeat = _confirm(importer, "executions_utf8.csv", "text/csv")
    correction = _confirm(
        importer,
        "executions_gb18030.csv",
        "text/csv",
        supersedes_batch_id=first["id"],
    )

    assert len({first["id"], repeat["id"], correction["id"]}) == 3
    assert repeat["same_content_as"] == first["id"]
    assert repeat["raw_artifact"]["relative_path"] != first["raw_artifact"]["relative_path"]
    assert correction["supersedes_batch_id"] == first["id"]
    assert repository.get_import_batch(first["id"])["status"] == "completed"
    assert artifacts.load(first["raw_artifact"]) == (FIXTURES / "executions_utf8.csv").read_bytes()


def test_same_content_lineage_is_principal_scoped(tmp_path):
    _repository, _artifacts, importer = _stack(tmp_path)

    first = _confirm(importer, "executions_utf8.csv", "text/csv")
    other_principal = _confirm(
        importer,
        "executions_utf8.csv",
        "text/csv",
        principal="other-shadow-user",
    )
    same_principal = _confirm(importer, "executions_utf8.csv", "text/csv")

    assert other_principal["same_content_as"] is None
    assert same_principal["same_content_as"] == first["id"]
    assert first["id"] not in json.dumps(other_principal)


def test_unpreviewable_parser_failure_persists_no_import_attempt(tmp_path):
    from app.shadow.importer import ShadowImportError

    repository, artifacts, importer = _stack(tmp_path)

    with pytest.raises(ShadowImportError):
        importer.preview(
            filename="broken.csv",
            media_type="text/csv",
            content=b"\xff\xfe\x00\x80not-csv",
            mapping=MAPPING,
            source_timezone="Asia/Shanghai",
            principal="shadow-user-opaque",
        )

    assert repository.list_import_batches(principal="shadow-user-opaque") == []
    assert artifacts.list_temporary_namespaces() == []


def test_raw_artifact_tamper_and_partial_files_fail_closed(tmp_path):
    from app.shadow.artifacts import ShadowArtifactError

    _repository, artifacts, importer = _stack(tmp_path)
    batch = _confirm(importer, "executions_utf8.csv", "text/csv")
    descriptor = batch["raw_artifact"]
    payload_path = artifacts.resolve_for_test(descriptor["relative_path"])

    payload_path.write_bytes(b"tampered")
    with pytest.raises(ShadowArtifactError):
        artifacts.load(descriptor)

    payload_path.unlink()
    with pytest.raises(ShadowArtifactError):
        artifacts.load(descriptor)


def test_public_import_contract_has_no_broker_manual_or_live_account_authority(tmp_path):
    repository, artifacts, importer = _stack(tmp_path)

    assert not hasattr(importer, "connect_broker")
    assert not hasattr(importer, "create_manual_trade")
    assert not hasattr(importer, "sync_positions")
    assert not hasattr(importer, "place_order")

    batch = _confirm(importer, "executions_utf8.csv", "text/csv")
    serialized = json.dumps(batch, ensure_ascii=False).lower()
    assert "broker_password" not in serialized
    assert "account_secret" not in serialized
    assert "manual_entry" not in serialized
    assert "position_mutation" not in serialized
    _assert_safe_projection(batch, artifacts.root)
    assert repository.list_operational_mutations() == []
