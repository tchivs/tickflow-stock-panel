"""RED contracts for the deployment-owned, local-only Kronos checkpoint catalog."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SOURCE_REVISION = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
MODEL_REVISIONS = {
    "mini": "f4e68697d9d5aed55cef5c96aabc3376bcad9f81",
    "small": "901c26c1332695a2a8f243eb2f37243a37bea320",
    "base": "base-approved-revision-0000000000000000000000000000000000",
}
TOKENIZER_REVISIONS = {
    "2k": "26966d0035065a0cae0ebad7af8ece35bc1fb51c",
    "base": "0e0117387f39004a9016484a186a908917e22426",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _approved_catalog(tmp_path: Path):
    from app.forecast.catalog import ApprovedCheckpointCatalog

    root = tmp_path / "approved-checkpoints"
    source = root / "source"
    source.mkdir(parents=True)
    (source / "UPSTREAM.json").write_text(json.dumps({"revision": SOURCE_REVISION}), encoding="utf-8")
    profiles: dict[str, dict[str, object]] = {}
    approved: dict[str, dict[str, object]] = {}
    for model_size, tokenizer_size, max_context, devices in (
        ("mini", "2k", 2048, ["cpu", "cuda:0"]),
        ("small", "base", 512, ["cpu", "cuda:0"]),
        ("base", "base", 512, ["cuda:0"]),
    ):
        model_dir = root / f"Kronos-{model_size}"
        tokenizer_dir = root / f"Kronos-Tokenizer-{tokenizer_size}"
        model_dir.mkdir()
        tokenizer_dir.mkdir(exist_ok=True)
        model_weight = model_dir / "model.safetensors"
        tokenizer_weight = tokenizer_dir / "model.safetensors"
        model_weight.write_bytes(f"fixture-model-{model_size}".encode())
        tokenizer_weight.write_bytes(f"fixture-tokenizer-{tokenizer_size}".encode())
        (model_dir / "config.json").write_text("{}", encoding="utf-8")
        (tokenizer_dir / "config.json").write_text("{}", encoding="utf-8")
        catalog_id = f"kronos-{model_size}"
        entry = {
            "catalog_id": catalog_id,
            "source_revision": SOURCE_REVISION,
            "source_dir": "source",
            "model_repo": f"NeoQuasar/Kronos-{model_size}",
            "model_revision": MODEL_REVISIONS[model_size],
            "model_weight_sha256": _sha(model_weight),
            "local_model_dir": f"Kronos-{model_size}",
            "tokenizer_repo": f"NeoQuasar/Kronos-Tokenizer-{tokenizer_size}",
            "tokenizer_revision": TOKENIZER_REVISIONS[tokenizer_size],
            "tokenizer_weight_sha256": _sha(tokenizer_weight),
            "local_tokenizer_dir": f"Kronos-Tokenizer-{tokenizer_size}",
            "pairing": f"{model_size}:{tokenizer_size}",
            "max_context": max_context,
            "allowed_devices": devices,
            "weight_format": "safetensors",
            "trust_remote_code": False,
            "local_files_only": True,
        }
        profiles[catalog_id] = entry
        approved[catalog_id] = dict(entry)
    manifest = root / "catalog.json"
    manifest.write_text(json.dumps({"schema_version": "forecast-catalog-v1", "entries": list(profiles.values())}), encoding="utf-8")
    return ApprovedCheckpointCatalog.from_file(
        manifest_path=manifest,
        approved_root=root,
        approved_profiles=approved,
    ), root, manifest, approved


def test_catalog_accepts_only_official_mini_small_and_base_pairings(tmp_path):
    catalog, _root, _manifest, _approved = _approved_catalog(tmp_path)
    assert catalog.require_local("kronos-mini", device="cpu").pairing == "mini:2k"
    assert catalog.require_local("kronos-small", device="cpu").pairing == "small:base"
    assert catalog.require_local("kronos-base", device="cuda:0").pairing == "base:base"


def test_catalog_preserves_model_size_context_and_device_policy(tmp_path):
    catalog, _root, _manifest, _approved = _approved_catalog(tmp_path)
    assert catalog.require_local("kronos-mini", device="cpu").max_context == 2048
    assert catalog.require_local("kronos-small", device="cpu").max_context == 512
    with pytest.raises(ValueError, match="device"):
        catalog.require_local("kronos-base", device="cpu")


def test_catalog_explicitly_rejects_unapproved_large_model(tmp_path):
    catalog, _root, _manifest, _approved = _approved_catalog(tmp_path)
    with pytest.raises(ValueError, match="not approved"):
        catalog.require_local("kronos-large", device="cuda:0")


def test_catalog_freezes_source_model_and_tokenizer_revisions(tmp_path):
    catalog, _root, _manifest, approved = _approved_catalog(tmp_path)
    resolved = catalog.require_local("kronos-mini", device="cpu")
    assert resolved.source_revision == SOURCE_REVISION
    assert resolved.model_revision == approved["kronos-mini"]["model_revision"]
    assert resolved.tokenizer_revision == approved["kronos-mini"]["tokenizer_revision"]


def test_catalog_rejects_moving_or_non_commit_revisions(tmp_path):
    _catalog, root, manifest, approved = _approved_catalog(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["entries"][0]["model_revision"] = "latest"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    from app.forecast.catalog import ApprovedCheckpointCatalog, ForecastCatalogError
    with pytest.raises(ForecastCatalogError, match="revision"):
        ApprovedCheckpointCatalog.from_file(manifest_path=manifest, approved_root=root, approved_profiles=approved)


def test_catalog_rejects_missing_partial_and_tampered_files(tmp_path):
    _catalog, root, manifest, approved = _approved_catalog(tmp_path)
    (root / "Kronos-mini" / "model.safetensors").write_bytes(b"tampered")
    from app.forecast.catalog import ApprovedCheckpointCatalog, ForecastCatalogError
    with pytest.raises(ForecastCatalogError, match="digest"):
        ApprovedCheckpointCatalog.from_file(manifest_path=manifest, approved_root=root, approved_profiles=approved)
    (root / "Kronos-small" / "config.json").unlink()
    with pytest.raises(ForecastCatalogError, match="missing|partial"):
        ApprovedCheckpointCatalog.from_file(manifest_path=manifest, approved_root=root, approved_profiles=approved)


def test_catalog_rejects_model_tokenizer_pair_mismatch(tmp_path):
    _catalog, root, manifest, approved = _approved_catalog(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["entries"][0]["pairing"] = "mini:base"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    from app.forecast.catalog import ApprovedCheckpointCatalog, ForecastCatalogError
    with pytest.raises(ForecastCatalogError, match="pair"):
        ApprovedCheckpointCatalog.from_file(manifest_path=manifest, approved_root=root, approved_profiles=approved)


def test_catalog_rejects_paths_outside_server_owned_root(tmp_path):
    _catalog, root, manifest, approved = _approved_catalog(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["entries"][0]["local_model_dir"] = "../escaped"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    from app.forecast.catalog import ApprovedCheckpointCatalog, ForecastCatalogError
    with pytest.raises(ForecastCatalogError, match="root|path"):
        ApprovedCheckpointCatalog.from_file(manifest_path=manifest, approved_root=root, approved_profiles=approved)


def test_catalog_rejects_remote_repo_or_url_as_runtime_path(tmp_path):
    _catalog, root, manifest, approved = _approved_catalog(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["entries"][0]["local_model_dir"] = "https://huggingface.co/NeoQuasar/Kronos-mini"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    from app.forecast.catalog import ApprovedCheckpointCatalog, ForecastCatalogError
    with pytest.raises(ForecastCatalogError, match="local|path"):
        ApprovedCheckpointCatalog.from_file(manifest_path=manifest, approved_root=root, approved_profiles=approved)


def test_catalog_rejects_pickle_and_non_safetensors_weights(tmp_path):
    _catalog, root, manifest, approved = _approved_catalog(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["entries"][0]["weight_format"] = "pickle"
    payload["entries"][0]["model_weight_file"] = "pytorch_model.bin"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    from app.forecast.catalog import ApprovedCheckpointCatalog, ForecastCatalogError
    with pytest.raises(ForecastCatalogError, match="safetensors"):
        ApprovedCheckpointCatalog.from_file(manifest_path=manifest, approved_root=root, approved_profiles=approved)


def test_catalog_rejects_remote_code_trust_and_network_fallback(tmp_path):
    _catalog, root, manifest, approved = _approved_catalog(tmp_path)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["entries"][0]["trust_remote_code"] = True
    payload["entries"][0]["local_files_only"] = False
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    from app.forecast.catalog import ApprovedCheckpointCatalog, ForecastCatalogError
    with pytest.raises(ForecastCatalogError, match="remote|local"):
        ApprovedCheckpointCatalog.from_file(manifest_path=manifest, approved_root=root, approved_profiles=approved)


def test_catalog_revalidates_integrity_before_worker_spawn(tmp_path):
    catalog, root, _manifest, _approved = _approved_catalog(tmp_path)
    entry = catalog.require_local("kronos-mini", device="cpu")
    (root / "Kronos-mini" / "model.safetensors").write_bytes(b"changed-after-startup")
    with pytest.raises(ValueError, match="digest"):
        catalog.revalidate_before_spawn(entry)


def test_catalog_probe_never_imports_torch_kronos_or_allocates_model(tmp_path):
    before = set(sys.modules)
    catalog, _root, _manifest, _approved = _approved_catalog(tmp_path)
    catalog.require_local("kronos-mini", device="cpu")
    imported = set(sys.modules) - before
    assert not any(name == "torch" or name.startswith("torch.") for name in imported)
    assert not any("kronos" in name.lower() for name in imported)


def test_catalog_probe_never_calls_network(tmp_path, monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("routine catalog validation attempted network access")
    monkeypatch.setattr("socket.create_connection", denied)
    catalog, _root, _manifest, _approved = _approved_catalog(tmp_path)
    assert catalog.require_local("kronos-mini", device="cpu").local_files_only is True


def test_catalog_absence_returns_typed_forecast_unavailable_state(tmp_path):
    from app.forecast.catalog import ApprovedCheckpointCatalog
    status = ApprovedCheckpointCatalog.probe(
        manifest_path=tmp_path / "missing.json",
        approved_root=tmp_path / "models",
        approved_profiles={},
    )
    assert status.model_dump() == {
        "available": False,
        "code": "forecast_checkpoint_unavailable",
        "reason": "approved local Forecast checkpoint is unavailable",
        "install_hint": "Provision an approved pinned local Kronos pair.",
    }


def test_catalog_unavailable_state_is_sanitized_and_path_free(tmp_path):
    from app.forecast.catalog import ApprovedCheckpointCatalog
    status = ApprovedCheckpointCatalog.probe(
        manifest_path=tmp_path / "secret" / "catalog.json",
        approved_root=tmp_path / "secret",
        approved_profiles={},
    )
    serialized = json.dumps(status.model_dump())
    assert str(tmp_path) not in serialized
    assert "Traceback" not in serialized


def test_default_host_import_does_not_require_forecast_dependencies():
    from app.forecast.catalog import ApprovedCheckpointCatalog

    status = ApprovedCheckpointCatalog.probe(
        manifest_path=Path("missing-forecast-catalog.json"),
        approved_root=Path("missing-forecast-models"),
        approved_profiles={},
    )
    assert status.available is False
    before = set(sys.modules)
    from app import main  # noqa: F401
    imported = set(sys.modules) - before
    assert "torch" not in imported
    assert "huggingface_hub" not in imported
    assert not any(name.startswith("app.vendor.kronos") for name in imported)
