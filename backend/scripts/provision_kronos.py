"""Explicit operator provisioning for approved, immutable Kronos checkpoints.

This module is deliberately separate from application runtime code. Network access is
possible only through :func:`provision_checkpoint`, after an operator chooses one of the
built-in approved catalog IDs. Verification is always local-only.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Final, Iterator, Mapping, Sequence


SOURCE_REPOSITORY: Final = "https://github.com/shiyu-coder/Kronos"
SOURCE_REVISION: Final = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
CATALOG_SCHEMA_VERSION: Final = "forecast-catalog-v1"
EXPECTED_ASSET_FILES: Final = frozenset({"config.json", "model.safetensors"})
_COMMIT_RE: Final = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_PAIRINGS: Final = {"mini": "2k", "small": "base", "base": "base"}

BACKEND_ROOT: Final = Path(__file__).resolve().parents[1]


class CheckpointVerificationError(RuntimeError):
    """An asset, catalog, path, or approval identity failed closed."""


def _error(message: str) -> CheckpointVerificationError:
    return CheckpointVerificationError(message)


def _validate_local_name(value: str, field: str) -> None:
    path = Path(value)
    if (
        not value
        or path.is_absolute()
        or len(path.parts) != 1
        or path.parts[0] in {".", ".."}
        or ":" in value
        or "\\" in value
    ):
        raise ValueError(f"{field} must be one relative directory under the model root")


@dataclass(frozen=True, slots=True)
class CheckpointSpec:
    """Immutable approved identity and local catalog policy for one model pair."""

    catalog_id: str
    model_repo: str
    model_revision: str
    model_config_sha256: str
    model_weight_sha256: str
    tokenizer_repo: str
    tokenizer_revision: str
    tokenizer_config_sha256: str
    tokenizer_weight_sha256: str
    pairing: str
    max_context: int
    allowed_devices: tuple[str, ...]
    local_model_dir: str
    local_tokenizer_dir: str
    explicit_provisioning_only: bool = False
    weight_file: str = "model.safetensors"
    config_file: str = "config.json"

    def __post_init__(self) -> None:
        if not self.catalog_id.startswith("kronos-"):
            raise ValueError("catalog id is invalid")
        model_size = self.catalog_id.removeprefix("kronos-")
        tokenizer_size = _EXPECTED_PAIRINGS.get(model_size)
        if tokenizer_size is None:
            raise ValueError("model is not approved")
        if self.pairing != f"{model_size}:{tokenizer_size}":
            raise ValueError("model/tokenizer pairing is not approved")
        if self.model_repo != f"NeoQuasar/Kronos-{model_size}":
            raise ValueError("model repository is not approved")
        if self.tokenizer_repo != f"NeoQuasar/Kronos-Tokenizer-{tokenizer_size}":
            raise ValueError("tokenizer repository is not approved")
        if not _COMMIT_RE.fullmatch(self.model_revision):
            raise ValueError("model revision must be an immutable commit")
        if not _COMMIT_RE.fullmatch(self.tokenizer_revision):
            raise ValueError("tokenizer revision must be an immutable commit")
        if not _SHA256_RE.fullmatch(self.model_weight_sha256):
            raise ValueError("model digest must be a full SHA-256")
        if not _SHA256_RE.fullmatch(self.model_config_sha256):
            raise ValueError("model config digest must be a full SHA-256")
        if not _SHA256_RE.fullmatch(self.tokenizer_weight_sha256):
            raise ValueError("tokenizer digest must be a full SHA-256")
        if not _SHA256_RE.fullmatch(self.tokenizer_config_sha256):
            raise ValueError("tokenizer config digest must be a full SHA-256")
        if self.weight_file != "model.safetensors":
            raise ValueError("only model.safetensors weights are approved")
        if self.config_file != "config.json":
            raise ValueError("only the approved JSON config is allowed")
        if self.max_context <= 0 or not self.allowed_devices:
            raise ValueError("context and device policy must be explicit")
        _validate_local_name(self.local_model_dir, "local model directory")
        _validate_local_name(self.local_tokenizer_dir, "local tokenizer directory")

    def catalog_entry(self) -> dict[str, Any]:
        """Return the complete deployment catalog record for this identity."""
        return {
            "catalog_id": self.catalog_id,
            "source_repository": SOURCE_REPOSITORY,
            "source_revision": SOURCE_REVISION,
            "model_repo": self.model_repo,
            "model_revision": self.model_revision,
            "model_config_file": self.config_file,
            "model_config_sha256": self.model_config_sha256,
            "model_weight_file": self.weight_file,
            "model_weight_sha256": self.model_weight_sha256,
            "local_model_dir": self.local_model_dir,
            "tokenizer_repo": self.tokenizer_repo,
            "tokenizer_revision": self.tokenizer_revision,
            "tokenizer_config_file": self.config_file,
            "tokenizer_config_sha256": self.tokenizer_config_sha256,
            "tokenizer_weight_file": self.weight_file,
            "tokenizer_weight_sha256": self.tokenizer_weight_sha256,
            "local_tokenizer_dir": self.local_tokenizer_dir,
            "pairing": self.pairing,
            "max_context": self.max_context,
            "allowed_devices": list(self.allowed_devices),
            "weight_format": "safetensors",
            "trust_remote_code": False,
            "local_files_only": True,
            "explicit_provisioning_only": self.explicit_provisioning_only,
        }


_APPROVED_CHECKPOINTS = {
    "kronos-mini": CheckpointSpec(
        catalog_id="kronos-mini",
        model_repo="NeoQuasar/Kronos-mini",
        model_revision="f4e68697d9d5aed55cef5c96aabc3376bcad9f81",
        model_config_sha256="70daca2cb11e3a979dd6b8ac12ee08e2aace877acf28f5b8dfb4fe5609736201",
        model_weight_sha256="a7d5f37e2e9fbd9891f7d7d4f72574512dd1f704fee14223e0a8cd0fbf54197c",
        tokenizer_repo="NeoQuasar/Kronos-Tokenizer-2k",
        tokenizer_revision="26966d0035065a0cae0ebad7af8ece35bc1fb51c",
        tokenizer_config_sha256="0b30a443affb03e05a876a083857de9164f899feb7b4d261da02c485c9a3e3b6",
        tokenizer_weight_sha256="b97ec46b3b72160509e289183eaf7bdf5f0dac5bb9b49522f6d46638a99a8717",
        pairing="mini:2k",
        max_context=2048,
        allowed_devices=("cpu", "cuda:0"),
        local_model_dir="Kronos-mini",
        local_tokenizer_dir="Kronos-Tokenizer-2k",
    ),
    "kronos-small": CheckpointSpec(
        catalog_id="kronos-small",
        model_repo="NeoQuasar/Kronos-small",
        model_revision="901c26c1332695a2a8f243eb2f37243a37bea320",
        model_config_sha256="5e0f6a605d5f81b5c9b559fe5cf716a1acb041c744e6f41bd05b097b7a685396",
        model_weight_sha256="b082dfcbd8e8c142a725c8bbb99781802f38fec81210e13479effb32b3c3e020",
        tokenizer_repo="NeoQuasar/Kronos-Tokenizer-base",
        tokenizer_revision="0e0117387f39004a9016484a186a908917e22426",
        tokenizer_config_sha256="2366e7ccfec76cbc19cf3c4c1b9c5d901be336ca1e83f2d2292c9bff381b77a2",
        tokenizer_weight_sha256="59d85f6af76a2c3b8240ea06cb21db4213b4eeca053f246b23e29cf832fc6bee",
        pairing="small:base",
        max_context=512,
        allowed_devices=("cpu", "cuda:0"),
        local_model_dir="Kronos-small",
        local_tokenizer_dir="Kronos-Tokenizer-base",
    ),
    "kronos-base": CheckpointSpec(
        catalog_id="kronos-base",
        model_repo="NeoQuasar/Kronos-base",
        model_revision="2b554741eca47781b64468546e77fef3e85130e6",
        model_config_sha256="77ebc3038b647709b92be002f801d72e1a385f4c8c2c5aa1cc6cf21fcfe44eb2",
        model_weight_sha256="abff193acab6db1a0368e9773e75799d11403b6d054ee6d5f0a11aeabc5f4b83",
        tokenizer_repo="NeoQuasar/Kronos-Tokenizer-base",
        tokenizer_revision="0e0117387f39004a9016484a186a908917e22426",
        tokenizer_config_sha256="2366e7ccfec76cbc19cf3c4c1b9c5d901be336ca1e83f2d2292c9bff381b77a2",
        tokenizer_weight_sha256="59d85f6af76a2c3b8240ea06cb21db4213b4eeca053f246b23e29cf832fc6bee",
        pairing="base:base",
        max_context=512,
        allowed_devices=("cuda:0",),
        local_model_dir="Kronos-base",
        local_tokenizer_dir="Kronos-Tokenizer-base",
        explicit_provisioning_only=True,
    ),
}
APPROVED_CHECKPOINTS: Final[Mapping[str, CheckpointSpec]] = MappingProxyType(
    _APPROVED_CHECKPOINTS
)

def _approved_spec(catalog_id: str) -> CheckpointSpec:
    try:
        return APPROVED_CHECKPOINTS[catalog_id]
    except KeyError as exc:
        raise _error("checkpoint catalog item is not approved") from exc


def _contained_paths(model_root: Path, catalog_path: Path) -> tuple[Path, Path]:
    root = Path(model_root).expanduser().resolve(strict=False)
    candidate = Path(catalog_path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    catalog = candidate.resolve(strict=False)
    try:
        catalog.relative_to(root)
    except ValueError as exc:
        raise _error("catalog path must remain under the model root") from exc
    if catalog == root:
        raise _error("catalog path must name a file under the model root")
    return root, catalog


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_asset_directory(
    directory: Path,
    expected_weight_digest: str,
    expected_config_digest: str,
    label: str,
) -> None:
    if not directory.is_dir() or directory.is_symlink():
        raise _error(f"{label} checkpoint is missing or partial")
    try:
        children = list(directory.iterdir())
    except OSError as exc:
        raise _error(f"{label} checkpoint is unavailable") from exc
    names = {child.name for child in children}
    missing = EXPECTED_ASSET_FILES - names
    unexpected = names - EXPECTED_ASSET_FILES
    if missing:
        raise _error(f"{label} checkpoint is missing or partial")
    if unexpected:
        raise _error(f"unexpected or executable {label} checkpoint file")
    for child in children:
        if child.is_symlink() or not child.is_file():
            raise _error(f"unexpected {label} checkpoint file type")
    try:
        config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _error(f"{label} JSON config is invalid") from exc
    if not isinstance(config, dict):
        raise _error(f"{label} JSON config is invalid")
    try:
        actual_config_digest = _sha256(directory / "config.json")
        actual_weight_digest = _sha256(directory / "model.safetensors")
    except OSError as exc:
        raise _error(f"{label} checkpoint is missing or partial") from exc
    if actual_config_digest != expected_config_digest:
        raise _error(f"{label} config digest mismatch")
    if actual_weight_digest != expected_weight_digest:
        raise _error(f"{label} checkpoint digest mismatch")


def _verify_asset_pair(spec: CheckpointSpec, model_dir: Path, tokenizer_dir: Path) -> None:
    _verify_asset_directory(
        model_dir,
        spec.model_weight_sha256,
        spec.model_config_sha256,
        "model",
    )
    _verify_asset_directory(
        tokenizer_dir,
        spec.tokenizer_weight_sha256,
        spec.tokenizer_config_sha256,
        "tokenizer",
    )


def _load_catalog(catalog_path: Path, *, required: bool) -> dict[str, Any]:
    if not catalog_path.exists():
        if required:
            raise _error("checkpoint catalog is missing")
        return {"schema_version": CATALOG_SCHEMA_VERSION, "entries": []}
    if catalog_path.is_symlink() or not catalog_path.is_file():
        raise _error("checkpoint catalog file type is invalid")
    try:
        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _error("checkpoint catalog is invalid") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != CATALOG_SCHEMA_VERSION:
        raise _error("checkpoint catalog schema is invalid")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not all(isinstance(entry, dict) for entry in entries):
        raise _error("checkpoint catalog entries are invalid")
    seen: set[str] = set()
    for entry in entries:
        catalog_id = entry.get("catalog_id")
        if not isinstance(catalog_id, str) or catalog_id in seen:
            raise _error("checkpoint catalog identities are invalid")
        spec = _approved_spec(catalog_id)
        if entry != spec.catalog_entry():
            raise _error("checkpoint catalog entry does not match approved identity")
        seen.add(catalog_id)
    return payload


def _catalog_entry(payload: Mapping[str, Any], catalog_id: str) -> dict[str, Any]:
    for entry in payload["entries"]:
        if entry.get("catalog_id") == catalog_id:
            return entry
    raise _error("approved checkpoint is absent from the deployment catalog")


def verify_checkpoint(
    catalog_id: str,
    model_root: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    """Verify an installed approved checkpoint pair without network access."""
    spec = _approved_spec(catalog_id)
    root, catalog = _contained_paths(model_root, catalog_path)
    payload = _load_catalog(catalog, required=True)
    entry = _catalog_entry(payload, catalog_id)
    if entry != spec.catalog_entry():
        raise _error("checkpoint catalog entry does not match approved pairing or revision")
    _verify_asset_pair(
        spec,
        root / spec.local_model_dir,
        root / spec.local_tokenizer_dir,
    )
    return dict(entry)


DownloadFile = Callable[..., str]


def _download_file(**kwargs: Any) -> str:
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise _error("Forecast provisioning dependencies are unavailable") from exc
    try:
        return hf_hub_download(**kwargs)
    except Exception as exc:
        raise _error("approved checkpoint fetch failed") from exc


def _download_asset(
    *,
    repo_id: str,
    revision: str,
    destination: Path,
    cache_dir: Path,
    offline: bool,
    downloader: DownloadFile,
) -> None:
    destination.mkdir()
    for filename in sorted(EXPECTED_ASSET_FILES):
        try:
            downloaded = Path(
                downloader(
                    repo_id=repo_id,
                    filename=filename,
                    revision=revision,
                    cache_dir=str(cache_dir),
                    local_files_only=offline,
                    token=None,
                )
            )
            if not downloaded.is_file():
                raise OSError("downloaded asset is not a regular file")
            shutil.copyfile(downloaded, destination / filename)
        except CheckpointVerificationError:
            raise
        except Exception as exc:
            raise _error("approved checkpoint fetch was incomplete") from exc


def _updated_catalog(payload: Mapping[str, Any], spec: CheckpointSpec) -> dict[str, Any]:
    entries = [dict(entry) for entry in payload["entries"]]
    expected = spec.catalog_entry()
    for entry in entries:
        if entry.get("catalog_id") == spec.catalog_id:
            if entry != expected:
                raise _error("existing catalog entry conflicts with approved identity")
            return {"schema_version": CATALOG_SCHEMA_VERSION, "entries": entries}
    entries.append(expected)
    entries.sort(key=lambda entry: entry["catalog_id"])
    return {"schema_version": CATALOG_SCHEMA_VERSION, "entries": entries}


def _write_catalog_atomic(catalog_path: Path, payload: Mapping[str, Any]) -> None:
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{catalog_path.name}.",
        suffix=".tmp",
        dir=catalog_path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, catalog_path)
        directory = os.open(catalog_path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


@contextmanager
def _catalog_lock(catalog_path: Path) -> Iterator[None]:
    """Serialize local catalog publication and shared-asset promotion."""
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = catalog_path.parent / f".{catalog_path.name}.lock"
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _provision_checkpoint_locked(
    spec: CheckpointSpec,
    root: Path,
    catalog: Path,
    *,
    offline: bool,
    downloader: DownloadFile | None,
) -> dict[str, Any]:
    """Provision one identity while holding the catalog publication lock."""
    payload = _load_catalog(catalog, required=False)
    updated_payload = _updated_catalog(payload, spec)

    final_model = root / spec.local_model_dir
    final_tokenizer = root / spec.local_tokenizer_dir
    for directory, weight_digest, config_digest, label in (
        (final_model, spec.model_weight_sha256, spec.model_config_sha256, "model"),
        (
            final_tokenizer,
            spec.tokenizer_weight_sha256,
            spec.tokenizer_config_sha256,
            "tokenizer",
        ),
    ):
        if directory.exists() or directory.is_symlink():
            try:
                _verify_asset_directory(directory, weight_digest, config_digest, label)
            except CheckpointVerificationError as exc:
                raise _error(f"existing {label} checkpoint digest or file mismatch") from exc

    need_model = not final_model.exists()
    need_tokenizer = not final_tokenizer.exists()
    stage_root = Path(tempfile.mkdtemp(prefix=".kronos-provision-", dir=root))
    download = downloader or _download_file
    try:
        staged_model = stage_root / "model"
        staged_tokenizer = stage_root / "tokenizer"
        cache = stage_root / "cache"
        if need_model:
            _download_asset(
                repo_id=spec.model_repo,
                revision=spec.model_revision,
                destination=staged_model,
                cache_dir=cache,
                offline=offline,
                downloader=download,
            )
            _verify_asset_directory(
                staged_model,
                spec.model_weight_sha256,
                spec.model_config_sha256,
                "model",
            )
        if need_tokenizer:
            _download_asset(
                repo_id=spec.tokenizer_repo,
                revision=spec.tokenizer_revision,
                destination=staged_tokenizer,
                cache_dir=cache,
                offline=offline,
                downloader=download,
            )
            _verify_asset_directory(
                staged_tokenizer,
                spec.tokenizer_weight_sha256,
                spec.tokenizer_config_sha256,
                "tokenizer",
            )

        for needed, staged, final, weight_digest, config_digest, label in (
            (
                need_model,
                staged_model,
                final_model,
                spec.model_weight_sha256,
                spec.model_config_sha256,
                "model",
            ),
            (
                need_tokenizer,
                staged_tokenizer,
                final_tokenizer,
                spec.tokenizer_weight_sha256,
                spec.tokenizer_config_sha256,
                "tokenizer",
            ),
        ):
            if not needed:
                continue
            if final.exists() or final.is_symlink():
                _verify_asset_directory(final, weight_digest, config_digest, label)
            else:
                staged.rename(final)

        _verify_asset_pair(spec, final_model, final_tokenizer)
        _write_catalog_atomic(catalog, updated_payload)
        return spec.catalog_entry()
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)


def provision_checkpoint(
    catalog_id: str,
    model_root: Path,
    catalog_path: Path,
    *,
    offline: bool = False,
    downloader: DownloadFile | None = None,
) -> dict[str, Any]:
    """Fetch, verify, and atomically catalog one explicitly selected approved pair."""
    spec = _approved_spec(catalog_id)
    root, catalog = _contained_paths(model_root, catalog_path)
    root.mkdir(parents=True, exist_ok=True)
    with _catalog_lock(catalog):
        return _provision_checkpoint_locked(
            spec,
            root,
            catalog,
            offline=offline,
            downloader=downloader,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--provision", metavar="CATALOG_ID")
    action.add_argument("--verify-only", metavar="CATALOG_ID")
    parser.add_argument("--model-root", required=True, type=Path)
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="provision only from the local Hugging Face cache; verification is always offline",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.verify_only:
            verify_checkpoint(args.verify_only, args.model_root, args.catalog)
            print(f"Approved checkpoint verification passed: {args.verify_only}")
        else:
            provision_checkpoint(
                args.provision,
                args.model_root,
                args.catalog,
                offline=args.offline,
            )
            print(f"Approved checkpoint provisioning completed: {args.provision}")
    except CheckpointVerificationError as exc:
        print(f"Checkpoint operation rejected: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
