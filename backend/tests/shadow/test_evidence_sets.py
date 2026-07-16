"""Shadow evidence-set RED contracts for explicit immutable membership."""
from __future__ import annotations

import json
import sqlite3
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
    from app.shadow.repository import ShadowRepository
    from app.shadow.artifacts import ShadowArtifactStore
    from app.shadow.importer import ShadowImporter, ShadowImportLimits

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
    assert first["included_trade_ids"] == sorted(trade_ids)
    assert first["fingerprint"] == replay["fingerprint"]
    assert len(first["fingerprint"]) == 64
    assert repository.get_evidence_set(first["id"]) == first


def test_evidence_set_preserves_partial_fills_duplicate_groups_and_row_identity(tmp_path):
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
    from app.shadow.repository import ShadowEvidenceError

    repository, importer = _stack(tmp_path)
    rejected = importer.confirm_import(
        filename="broken.csv",
        media_type="text/csv",
        content=b"\xff\xfe\x00broken",
        mapping=MAPPING,
        source_timezone="Asia/Shanghai",
        principal="shadow-user-opaque",
        source_label="local-broker-export",
    )

    assert rejected["status"] == "rejected"
    with pytest.raises(ShadowEvidenceError, match="completed batch"):
        repository.create_evidence_set(
            principal="shadow-user-opaque",
            included_batch_ids=[rejected["id"]],
            included_trade_ids=[],
            exclusions=[],
        )
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

    assert evidence["included_trade_ids"] == sorted(included)
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
