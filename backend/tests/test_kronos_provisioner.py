"""Focused contracts for explicit, immutable Kronos checkpoint provisioning.

All provisioning tests use local fixture bytes and injected download functions. They never
contact Hugging Face or download a real checkpoint.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import socket
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import provision_kronos as provisioner


SOURCE_REVISION = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
MODEL_BYTES = b"fixture-model-safetensors"
TOKENIZER_BYTES = b"fixture-tokenizer-safetensors"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def fixture_spec(monkeypatch: pytest.MonkeyPatch) -> provisioner.CheckpointSpec:
    approved = provisioner.APPROVED_CHECKPOINTS["kronos-mini"]
    spec = replace(
        approved,
        model_weight_sha256=_sha(MODEL_BYTES),
        tokenizer_weight_sha256=_sha(TOKENIZER_BYTES),
        local_model_dir="Kronos-mini-fixture",
        local_tokenizer_dir="Kronos-Tokenizer-2k-fixture",
    )
    monkeypatch.setattr(
        provisioner,
        "APPROVED_CHECKPOINTS",
        {**provisioner.APPROVED_CHECKPOINTS, spec.catalog_id: spec},
    )
    return spec


def _write_asset(directory: Path, weight: bytes) -> None:
    directory.mkdir(parents=True)
    (directory / "config.json").write_text("{}\n", encoding="utf-8")
    (directory / "model.safetensors").write_bytes(weight)


def _write_valid_install(root: Path, catalog: Path, spec: provisioner.CheckpointSpec) -> None:
    _write_asset(root / spec.local_model_dir, MODEL_BYTES)
    _write_asset(root / spec.local_tokenizer_dir, TOKENIZER_BYTES)
    catalog.write_text(
        json.dumps(
            {
                "schema_version": provisioner.CATALOG_SCHEMA_VERSION,
                "entries": [spec.catalog_entry()],
            }
        ),
        encoding="utf-8",
    )


def _fixture_downloader(tmp_path: Path, calls: list[dict[str, object]]):
    files: dict[tuple[str, str], Path] = {}
    for repo, weight in (
        ("NeoQuasar/Kronos-mini", MODEL_BYTES),
        ("NeoQuasar/Kronos-Tokenizer-2k", TOKENIZER_BYTES),
    ):
        repo_root = tmp_path / repo.replace("/", "--")
        _write_asset(repo_root, weight)
        for name in ("config.json", "model.safetensors"):
            files[(repo, name)] = repo_root / name

    def download(**kwargs):
        calls.append(kwargs)
        return str(files[(kwargs["repo_id"], kwargs["filename"])])

    return download


def test_approved_catalog_contains_exact_human_approved_identities():
    assert set(provisioner.APPROVED_CHECKPOINTS) == {
        "kronos-mini",
        "kronos-small",
        "kronos-base",
    }
    mini = provisioner.APPROVED_CHECKPOINTS["kronos-mini"]
    small = provisioner.APPROVED_CHECKPOINTS["kronos-small"]
    base = provisioner.APPROVED_CHECKPOINTS["kronos-base"]
    assert (mini.model_revision, mini.model_weight_sha256, mini.pairing) == (
        "f4e68697d9d5aed55cef5c96aabc3376bcad9f81",
        "a7d5f37e2e9fbd9891f7d7d4f72574512dd1f704fee14223e0a8cd0fbf54197c",
        "mini:2k",
    )
    assert (small.model_revision, small.model_weight_sha256, small.pairing) == (
        "901c26c1332695a2a8f243eb2f37243a37bea320",
        "b082dfcbd8e8c142a725c8bbb99781802f38fec81210e13479effb32b3c3e020",
        "small:base",
    )
    assert (base.model_revision, base.model_weight_sha256, base.pairing) == (
        "2b554741eca47781b64468546e77fef3e85130e6",
        "abff193acab6db1a0368e9773e75799d11403b6d054ee6d5f0a11aeabc5f4b83",
        "base:base",
    )
    assert mini.tokenizer_repo == "NeoQuasar/Kronos-Tokenizer-2k"
    assert small.tokenizer_repo == base.tokenizer_repo == "NeoQuasar/Kronos-Tokenizer-base"
    assert small.tokenizer_revision == base.tokenizer_revision == (
        "0e0117387f39004a9016484a186a908917e22426"
    )
    assert small.tokenizer_weight_sha256 == base.tokenizer_weight_sha256 == (
        "59d85f6af76a2c3b8240ea06cb21db4213b4eeca053f246b23e29cf832fc6bee"
    )
    assert base.explicit_provisioning_only is True


def test_checkpoint_spec_rejects_moving_revision_wrong_pair_and_pickle():
    approved = provisioner.APPROVED_CHECKPOINTS["kronos-mini"]
    with pytest.raises(ValueError, match="revision"):
        replace(approved, model_revision="latest")
    with pytest.raises(ValueError, match="pair"):
        replace(approved, pairing="mini:base")
    with pytest.raises(ValueError, match="safetensors"):
        replace(approved, weight_file="pytorch_model.bin")


def test_example_catalog_documents_complete_relative_local_profiles():
    example_path = Path("app/forecast/checkpoints.example.json")
    payload = json.loads(example_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == provisioner.CATALOG_SCHEMA_VERSION
    entries = {entry["catalog_id"]: entry for entry in payload["entries"]}
    assert set(entries) == set(provisioner.APPROVED_CHECKPOINTS)
    for catalog_id, spec in provisioner.APPROVED_CHECKPOINTS.items():
        assert entries[catalog_id] == spec.catalog_entry()
        assert not Path(entries[catalog_id]["local_model_dir"]).is_absolute()
        assert not Path(entries[catalog_id]["local_tokenizer_dir"]).is_absolute()
        assert entries[catalog_id]["local_files_only"] is True
        assert entries[catalog_id]["trust_remote_code"] is False
    assert entries["kronos-base"]["explicit_provisioning_only"] is True
    assert all(entry["catalog_id"] != "kronos-large" for entry in payload["entries"])
    assert payload["excluded_profiles"] == [
        {
            "model_size": "large",
            "reason": (
                "Not approved for integrity-pinned provisioning; see the Kronos-large "
                "OPT-OUT in COVERAGE.md."
            ),
        }
    ]


def test_verify_only_succeeds_offline_for_valid_local_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fixture_spec: provisioner.CheckpointSpec,
):
    root = tmp_path / "models"
    root.mkdir()
    catalog = root / "catalog.json"
    _write_valid_install(root, catalog, fixture_spec)

    def denied(*_args, **_kwargs):
        raise AssertionError("verify-only attempted network access")

    monkeypatch.setattr(socket, "create_connection", denied)
    assert provisioner.verify_checkpoint(fixture_spec.catalog_id, root, catalog) == (
        fixture_spec.catalog_entry()
    )
    assert (
        provisioner.main(
            [
                "--verify-only",
                fixture_spec.catalog_id,
                "--model-root",
                str(root),
                "--catalog",
                str(catalog),
            ]
        )
        == 0
    )


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda model, _tokenizer: (model / "model.safetensors").write_bytes(b"tampered"), "digest"),
        (lambda model, _tokenizer: (model / "config.json").unlink(), "partial|missing"),
        (lambda model, _tokenizer: (model / "pytorch_model.bin").write_bytes(b"pickle"), "safetensors|unexpected"),
        (lambda model, _tokenizer: (model / "loader.py").write_text("pass\n"), "unexpected|executable"),
    ],
)
def test_verify_rejects_digest_partial_pickle_and_executable_files(
    tmp_path: Path,
    fixture_spec: provisioner.CheckpointSpec,
    mutation,
    match: str,
):
    root = tmp_path / "models"
    root.mkdir()
    catalog = root / "catalog.json"
    _write_valid_install(root, catalog, fixture_spec)
    mutation(root / fixture_spec.local_model_dir, root / fixture_spec.local_tokenizer_dir)
    with pytest.raises(provisioner.CheckpointVerificationError, match=match):
        provisioner.verify_checkpoint(fixture_spec.catalog_id, root, catalog)


def test_verify_rejects_catalog_pairing_and_revision_mismatch(
    tmp_path: Path,
    fixture_spec: provisioner.CheckpointSpec,
):
    root = tmp_path / "models"
    root.mkdir()
    catalog = root / "catalog.json"
    _write_valid_install(root, catalog, fixture_spec)
    payload = json.loads(catalog.read_text(encoding="utf-8"))
    payload["entries"][0]["pairing"] = "mini:base"
    payload["entries"][0]["model_revision"] = "latest"
    catalog.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(provisioner.CheckpointVerificationError, match="approved|pair|revision"):
        provisioner.verify_checkpoint(fixture_spec.catalog_id, root, catalog)


def test_provision_uses_only_fixed_revisions_allowlisted_files_and_atomic_catalog(
    tmp_path: Path,
    fixture_spec: provisioner.CheckpointSpec,
):
    root = tmp_path / "models"
    catalog = root / "catalog.json"
    calls: list[dict[str, object]] = []
    result = provisioner.provision_checkpoint(
        fixture_spec.catalog_id,
        root,
        catalog,
        downloader=_fixture_downloader(tmp_path / "downloads", calls),
    )
    assert result == fixture_spec.catalog_entry()
    assert provisioner.verify_checkpoint(fixture_spec.catalog_id, root, catalog) == result
    assert {(call["repo_id"], call["filename"]) for call in calls} == {
        (fixture_spec.model_repo, "config.json"),
        (fixture_spec.model_repo, "model.safetensors"),
        (fixture_spec.tokenizer_repo, "config.json"),
        (fixture_spec.tokenizer_repo, "model.safetensors"),
    }
    assert all(call["revision"] in {fixture_spec.model_revision, fixture_spec.tokenizer_revision} for call in calls)
    assert all(call["local_files_only"] is False for call in calls)
    assert all(call["token"] is None for call in calls)
    assert not any(path.name.startswith(".kronos-provision-") for path in root.iterdir())


def test_offline_provisioning_uses_cache_only_without_changing_identity(
    tmp_path: Path,
    fixture_spec: provisioner.CheckpointSpec,
):
    calls: list[dict[str, object]] = []
    root = tmp_path / "models"
    result = provisioner.provision_checkpoint(
        fixture_spec.catalog_id,
        root,
        root / "catalog.json",
        offline=True,
        downloader=_fixture_downloader(tmp_path / "cache", calls),
    )
    assert result == fixture_spec.catalog_entry()
    assert calls and all(call["local_files_only"] is True for call in calls)


def test_provision_rejects_unapproved_large_and_root_escape_before_writing(tmp_path: Path):
    root = tmp_path / "models"
    with pytest.raises(provisioner.CheckpointVerificationError, match="not approved"):
        provisioner.provision_checkpoint("kronos-large", root, root / "catalog.json")
    assert not root.exists()

    outside = tmp_path / "escaped-catalog.json"
    with pytest.raises(provisioner.CheckpointVerificationError, match="root|path"):
        provisioner.provision_checkpoint(
            "kronos-mini",
            root,
            outside,
            downloader=lambda **_kwargs: pytest.fail("download called before path validation"),
        )
    assert not root.exists()
    assert not outside.exists()


def test_existing_mismatched_assets_are_never_overwritten(
    tmp_path: Path,
    fixture_spec: provisioner.CheckpointSpec,
):
    root = tmp_path / "models"
    bad_model = root / fixture_spec.local_model_dir
    _write_asset(bad_model, b"existing-mismatch")
    original = (bad_model / "model.safetensors").read_bytes()
    calls: list[dict[str, object]] = []
    with pytest.raises(provisioner.CheckpointVerificationError, match="existing|digest"):
        provisioner.provision_checkpoint(
            fixture_spec.catalog_id,
            root,
            root / "catalog.json",
            downloader=_fixture_downloader(tmp_path / "downloads", calls),
        )
    assert (bad_model / "model.safetensors").read_bytes() == original
    assert not (root / "catalog.json").exists()


def test_malformed_existing_catalog_blocks_promotion_without_partial_install(
    tmp_path: Path,
    fixture_spec: provisioner.CheckpointSpec,
):
    root = tmp_path / "models"
    root.mkdir()
    catalog = root / "catalog.json"
    catalog.write_text("not-json", encoding="utf-8")
    calls: list[dict[str, object]] = []
    with pytest.raises(provisioner.CheckpointVerificationError, match="catalog"):
        provisioner.provision_checkpoint(
            fixture_spec.catalog_id,
            root,
            catalog,
            downloader=_fixture_downloader(tmp_path / "downloads", calls),
        )
    assert not calls
    assert not (root / fixture_spec.local_model_dir).exists()
    assert not (root / fixture_spec.local_tokenizer_dir).exists()
    assert catalog.read_text(encoding="utf-8") == "not-json"


def test_incomplete_approval_stops_before_download_or_model_root_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    summary = tmp_path / "approval.md"
    summary.write_text("---\nstatus: complete\napproval: approved\n---\n", encoding="utf-8")
    monkeypatch.setattr(provisioner, "APPROVAL_SUMMARY", summary)
    root = tmp_path / "models"
    called = False

    def downloader(**_kwargs):
        nonlocal called
        called = True
        raise AssertionError("download must not run")

    with pytest.raises(provisioner.CheckpointVerificationError, match="approval|approved"):
        provisioner.provision_checkpoint(
            "kronos-mini",
            root,
            root / "catalog.json",
            downloader=downloader,
        )
    assert called is False
    assert not root.exists()


def test_runtime_import_never_invokes_operator_provisioner(monkeypatch: pytest.MonkeyPatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("runtime invoked checkpoint provisioner")

    monkeypatch.setattr(provisioner, "provision_checkpoint", denied)
    import app.main

    importlib.reload(app.main)
