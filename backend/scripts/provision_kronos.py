"""Explicit operator provisioning for approved, immutable Kronos checkpoints.

This module is deliberately separate from application runtime code. Network access is
possible only through :func:`provision_checkpoint`, after an operator chooses one of the
built-in approved catalog IDs. Verification is always local-only.
"""
from __future__ import annotations

import argparse
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
from typing import Any, Callable, Final, Mapping, Sequence


SOURCE_REPOSITORY: Final = "https://github.com/shiyu-coder/Kronos"
SOURCE_REVISION: Final = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
CATALOG_SCHEMA_VERSION: Final = "forecast-catalog-v1"
EXPECTED_ASSET_FILES: Final = frozenset({"config.json", "model.safetensors"})
_COMMIT_RE: Final = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE: Final = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_PAIRINGS: Final = {"mini": "2k", "small": "base", "base": "base"}

BACKEND_ROOT: Final = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT: Final = BACKEND_ROOT.parent
APPROVAL_SUMMARY: Final = (
    REPOSITORY_ROOT
    / ".planning"
    / "phases"
    / "05-optional-enhancements"
    / "05-01-SUMMARY.md"
)


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
    model_weight_sha256: str
    tokenizer_repo: str
    tokenizer_revision: str
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
        if not _SHA256_RE.fullmatch(self.tokenizer_weight_sha256):
            raise ValueError("tokenizer digest must be a full SHA-256")
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
            "model_weight_file": self.weight_file,
            "model_weight_sha256": self.model_weight_sha256,
            "local_model_dir": self.local_model_dir,
            "tokenizer_repo": self.tokenizer_repo,
            "tokenizer_revision": self.tokenizer_revision,
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
        model_weight_sha256="a7d5f37e2e9fbd9891f7d7d4f72574512dd1f704fee14223e0a8cd0fbf54197c",
        tokenizer_repo="NeoQuasar/Kronos-Tokenizer-2k",
        tokenizer_revision="26966d0035065a0cae0ebad7af8ece35bc1fb51c",
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
        model_weight_sha256="b082dfcbd8e8c142a725c8bbb99781802f38fec81210e13479effb32b3c3e020",
        tokenizer_repo="NeoQuasar/Kronos-Tokenizer-base",
        tokenizer_revision="0e0117387f39004a9016484a186a908917e22426",
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
        model_weight_sha256="abff193acab6db1a0368e9773e75799d11403b6d054ee6d5f0a11aeabc5f4b83",
        tokenizer_repo="NeoQuasar/Kronos-Tokenizer-base",
        tokenizer_revision="0e0117387f39004a9016484a186a908917e22426",
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

_APPROVAL_REQUIRED_STRINGS: Final = (
    "scikit-learn | `1.8.0`",
    "torch | official PyTorch package",
    "einops | `0.8.1`",
    "huggingface-hub | `0.33.1`",
    "safetensors | `0.6.2`",
    "tqdm | keep the compatible existing lock",
    f"Commit: `{SOURCE_REVISION}`",
    "License: MIT",
    "| Kronos-mini | `f4e68697d9d5aed55cef5c96aabc3376bcad9f81` | `a7d5f37e2e9fbd9891f7d7d4f72574512dd1f704fee14223e0a8cd0fbf54197c` | approved default CPU model |",
    "| Kronos-Tokenizer-2k | `26966d0035065a0cae0ebad7af8ece35bc1fb51c` | `b97ec46b3b72160509e289183eaf7bdf5f0dac5bb9b49522f6d46638a99a8717` | approved only with Kronos-mini |",
    "| Kronos-small | `901c26c1332695a2a8f243eb2f37243a37bea320` | `b082dfcbd8e8c142a725c8bbb99781802f38fec81210e13479effb32b3c3e020` | approved optional catalog model |",
    "| Kronos-Tokenizer-base | `0e0117387f39004a9016484a186a908917e22426` | `59d85f6af76a2c3b8240ea06cb21db4213b4eeca053f246b23e29cf832fc6bee` | approved only with small/base family |",
    "| Kronos-base | `2b554741eca47781b64468546e77fef3e85130e6` | `abff193acab6db1a0368e9773e75799d11403b6d054ee6d5f0a11aeabc5f4b83` | approved optional catalog model; explicit operator provisioning only |",
    "Model and tokenizer must match the approved catalog pair and immutable revisions/digests.",
    "Pickle and moving `latest`/branch references are forbidden.",
    "Routine application startup, API requests, worker execution, tests, and model loading are local-only.",
)


def _require_complete_approval() -> None:
    try:
        summary = APPROVAL_SUMMARY.read_text(encoding="utf-8")
        frontmatter = summary.split("---", 2)[1]
    except (OSError, IndexError) as exc:
        raise _error("approved checkpoint record is unavailable") from exc
    metadata = {
        key: value
        for line in frontmatter.splitlines()
        if ": " in line
        for key, value in (line.split(": ", 1),)
    }
    if metadata.get("status") != "complete" or metadata.get("approval") != "approved":
        raise _error("approved checkpoint record is incomplete")
    if metadata.get("approved_at") != "2026-07-16T03:41:52Z":
        raise _error("approved checkpoint record is stale")
    if any(item not in summary for item in _APPROVAL_REQUIRED_STRINGS):
        raise _error("approved checkpoint identities are incomplete")


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


def _verify_asset_directory(directory: Path, expected_digest: str, label: str) -> None:
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
        actual_digest = _sha256(directory / "model.safetensors")
    except OSError as exc:
        raise _error(f"{label} checkpoint is missing or partial") from exc
    if actual_digest != expected_digest:
        raise _error(f"{label} checkpoint digest mismatch")


def _verify_asset_pair(spec: CheckpointSpec, model_dir: Path, tokenizer_dir: Path) -> None:
    _verify_asset_directory(model_dir, spec.model_weight_sha256, "model")
    _verify_asset_directory(tokenizer_dir, spec.tokenizer_weight_sha256, "tokenizer")


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
    _require_complete_approval()
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
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def provision_checkpoint(
    catalog_id: str,
    model_root: Path,
    catalog_path: Path,
    *,
    offline: bool = False,
    downloader: DownloadFile | None = None,
) -> dict[str, Any]:
    """Fetch, verify, and atomically catalog one explicitly selected approved pair."""
    _require_complete_approval()
    spec = _approved_spec(catalog_id)
    root, catalog = _contained_paths(model_root, catalog_path)
    payload = _load_catalog(catalog, required=False)
    updated_payload = _updated_catalog(payload, spec)

    final_model = root / spec.local_model_dir
    final_tokenizer = root / spec.local_tokenizer_dir
    for directory, digest, label in (
        (final_model, spec.model_weight_sha256, "model"),
        (final_tokenizer, spec.tokenizer_weight_sha256, "tokenizer"),
    ):
        if directory.exists() or directory.is_symlink():
            try:
                _verify_asset_directory(directory, digest, label)
            except CheckpointVerificationError as exc:
                raise _error(f"existing {label} checkpoint digest or file mismatch") from exc

    need_model = not final_model.exists()
    need_tokenizer = not final_tokenizer.exists()
    root.mkdir(parents=True, exist_ok=True)
    stage_root = Path(tempfile.mkdtemp(prefix=".kronos-provision-", dir=root))
    promoted: list[Path] = []
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
            _verify_asset_directory(staged_model, spec.model_weight_sha256, "model")
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
                "tokenizer",
            )

        for needed, staged, final, digest, label in (
            (need_model, staged_model, final_model, spec.model_weight_sha256, "model"),
            (
                need_tokenizer,
                staged_tokenizer,
                final_tokenizer,
                spec.tokenizer_weight_sha256,
                "tokenizer",
            ),
        ):
            if not needed:
                continue
            if final.exists() or final.is_symlink():
                _verify_asset_directory(final, digest, label)
            else:
                staged.rename(final)
                promoted.append(final)

        _verify_asset_pair(spec, final_model, final_tokenizer)
        _write_catalog_atomic(catalog, updated_payload)
        return spec.catalog_entry()
    except Exception:
        for directory in reversed(promoted):
            shutil.rmtree(directory, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)


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
