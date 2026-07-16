"""Contracts for the reviewed, pinned Kronos vendor synchronization boundary."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import sync_kronos


SOURCE_COMMIT = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
VENDOR_ROOT = Path(__file__).resolve().parents[1] / "app" / "vendor" / "kronos"
EXPECTED_BLOBS = {
    "LICENSE": "88b04125e828241d8aada64bfe7f700bb03bcef8",
    "model/__init__.py": "718d07a21b53b7eff4a6564e6dfcae8ee7e8c6b1",
    "model/kronos.py": "ce4494ee0b3ec8751b09d5488c93bde995e008e0",
    "model/module.py": "f2a05158b48a56e9235426f6583e384360d761f9",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_sync_boundary_is_hard_coded_to_approved_repository_commit_and_files():
    assert sync_kronos.SOURCE_REPOSITORY == "https://github.com/shiyu-coder/Kronos"
    assert sync_kronos.SOURCE_COMMIT == SOURCE_COMMIT
    assert sync_kronos.VENDORED_FILES == {
        "model/__init__.py": "__init__.py",
        "model/kronos.py": "kronos.py",
        "model/module.py": "module.py",
        "LICENSE": "LICENSE",
    }
    assert sync_kronos.SOURCE_BLOBS == EXPECTED_BLOBS


def test_manifest_records_exact_blob_and_vendored_hashes_with_bounded_diffs():
    manifest = json.loads((VENDOR_ROOT / "UPSTREAM.json").read_text(encoding="utf-8"))
    assert manifest["repository"] == sync_kronos.SOURCE_REPOSITORY
    assert manifest["commit"] == SOURCE_COMMIT
    assert manifest["license"] == "MIT"
    assert manifest["reviewed_at"] == "2026-07-16"
    assert set(manifest["files"]) == set(sync_kronos.VENDORED_FILES)
    for source, destination in sync_kronos.VENDORED_FILES.items():
        record = manifest["files"][source]
        assert record["destination"] == destination
        assert record["source_blob_sha1"] == EXPECTED_BLOBS[source]
        assert record["vendored_sha256"] == _sha(VENDOR_ROOT / destination)
        assert isinstance(record["approved_modifications"], list)
    assert manifest["files"]["model/module.py"]["approved_modifications"] == []
    assert manifest["files"]["LICENSE"]["approved_modifications"] == []
    assert manifest["files"]["model/kronos.py"]["approved_modifications"] == [
        "Removed the sys.path mutation used by the upstream repository layout.",
        "Changed the model.module wildcard import to the package-relative .module import.",
    ]
    assert manifest["files"]["model/__init__.py"]["approved_modifications"] == [
        "Restricted package exports to Kronos and KronosTokenizer; model_dict, get_model_class, and KronosPredictor export were omitted.",
    ]


def test_local_verifier_accepts_only_the_reviewed_vendor_bytes():
    result = sync_kronos.verify_vendor()
    assert result == {destination: _sha(VENDOR_ROOT / destination) for destination in sync_kronos.VENDORED_FILES.values()}


def test_local_verifier_rejects_tampering_without_disclosing_absolute_root(tmp_path):
    copy = tmp_path / "kronos"
    copy.mkdir()
    for path in VENDOR_ROOT.iterdir():
        if path.is_file():
            (copy / path.name).write_bytes(path.read_bytes())
    (copy / "module.py").write_text("tampered\n", encoding="utf-8")

    with pytest.raises(sync_kronos.VendorVerificationError) as raised:
        sync_kronos.verify_vendor(copy)
    assert str(tmp_path) not in str(raised.value)


def test_local_verifier_rejects_unexpected_files(tmp_path):
    copy = tmp_path / "kronos"
    copy.mkdir()
    for path in VENDOR_ROOT.iterdir():
        if path.is_file():
            (copy / path.name).write_bytes(path.read_bytes())
    (copy / "train.py").write_text("raise RuntimeError\n", encoding="utf-8")

    with pytest.raises(sync_kronos.VendorVerificationError, match="unexpected vendored file"):
        sync_kronos.verify_vendor(copy)


def test_vendor_subset_has_only_inference_source_license_and_manifest():
    assert {path.name for path in VENDOR_ROOT.iterdir() if path.is_file()} == {
        "__init__.py",
        "kronos.py",
        "module.py",
        "LICENSE",
        "UPSTREAM.json",
    }
    combined = "\n".join(
        (VENDOR_ROOT / name).read_text(encoding="utf-8")
        for name in ("__init__.py", "kronos.py", "module.py")
    )
    for forbidden in ("qlib", "matplotlib", "comet", "finetune", "akshare"):
        assert forbidden not in combined.lower()
    assert "sys.path" not in (VENDOR_ROOT / "kronos.py").read_text(encoding="utf-8")
    assert "from .module import *" in (VENDOR_ROOT / "kronos.py").read_text(encoding="utf-8")


def test_license_is_exact_upstream_mit_text():
    license_text = (VENDOR_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert license_text.startswith("MIT License\n\nCopyright (c) 2025 ShiYu\n")
    assert license_text.endswith("SOFTWARE.\n")
    assert _sha(VENDOR_ROOT / "LICENSE") == sync_kronos.MANIFEST_FILES["LICENSE"]["vendored_sha256"]


def test_verify_local_path_never_calls_network(monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("network called during local verification")

    monkeypatch.setattr(sync_kronos.urllib.request, "urlopen", denied)
    sync_kronos.verify_vendor()


def test_stage_sync_rejects_wrong_blob_before_writing(monkeypatch, tmp_path):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b"unreviewed"

    monkeypatch.setattr(sync_kronos.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(sync_kronos.VendorVerificationError, match="blob mismatch"):
        sync_kronos.stage_sync(tmp_path / "review")
    assert not (tmp_path / "review").exists()


def test_stage_sync_requires_an_empty_review_directory(tmp_path):
    occupied = tmp_path / "review"
    occupied.mkdir()
    (occupied / "existing").write_text("operator data", encoding="utf-8")
    with pytest.raises(sync_kronos.VendorVerificationError, match="empty review directory"):
        sync_kronos.stage_sync(occupied)
    assert (occupied / "existing").read_text(encoding="utf-8") == "operator data"


def test_cli_defaults_to_no_network_and_requires_explicit_action(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(sync_kronos, "verify_vendor", lambda *_args: calls.append("verify") or {})
    monkeypatch.setattr(sync_kronos, "stage_sync", lambda *_args, **_kwargs: calls.append("stage"))
    assert sync_kronos.main([]) == 2
    assert calls == []
    assert sync_kronos.main(["--verify-local"]) == 0
    assert calls == ["verify"]


def test_replace_requires_explicit_flag_and_preverified_stage(monkeypatch, tmp_path):
    monkeypatch.setattr(sync_kronos, "stage_sync", lambda target: target)
    calls: list[tuple[Path, Path]] = []
    monkeypatch.setattr(sync_kronos, "replace_vendor", lambda staged, vendor: calls.append((staged, vendor)))
    review = tmp_path / "review"
    assert sync_kronos.main(["--stage", str(review)]) == 0
    assert calls == []
    assert sync_kronos.main(["--stage", str(review), "--replace"]) == 0
    assert calls == [(review, sync_kronos.VENDOR_ROOT)]
