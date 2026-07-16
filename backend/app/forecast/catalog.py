"""Deployment-owned, local-only Kronos checkpoint catalog."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict


_CATALOG_SCHEMA = "forecast-catalog-v1"
_SOURCE_REPOSITORY = "https://github.com/shiyu-coder/Kronos"
_SOURCE_REVISION = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PAIRINGS = {"kronos-mini": "mini:2k", "kronos-small": "small:base", "kronos-base": "base:base"}
_CONTEXTS = {"kronos-mini": 2048, "kronos-small": 512, "kronos-base": 512}
_ASSET_FILES = frozenset({"config.json", "model.safetensors"})


class ForecastCatalogError(RuntimeError):
    """The deployment catalog or one of its local assets failed closed."""


class ForecastAvailability(BaseModel):
    """Path-free deployment availability returned by lightweight probes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    available: bool
    code: str
    reason: str
    install_hint: str


@dataclass(frozen=True, slots=True)
class ResolvedCheckpoint:
    """Verified internal identity passed to the bounded worker boundary."""

    catalog_id: str
    source_repository: str
    source_revision: str
    source_dir: Path
    model_repo: str
    model_revision: str
    model_weight_sha256: str
    model_dir: Path
    tokenizer_repo: str
    tokenizer_revision: str
    tokenizer_weight_sha256: str
    tokenizer_dir: Path
    pairing: str
    max_context: int
    allowed_devices: tuple[str, ...]
    weight_format: str
    trust_remote_code: bool
    local_files_only: bool


class ApprovedCheckpointCatalog:
    """Canonicalizes and revalidates only approved local checkpoint pairs."""

    def __init__(self, *, approved_root: Path, entries: Mapping[str, ResolvedCheckpoint]) -> None:
        self._root = approved_root
        self._entries = dict(entries)

    @classmethod
    def from_file(
        cls,
        *,
        manifest_path: Path,
        approved_root: Path,
        approved_profiles: Mapping[str, Mapping[str, object]],
    ) -> ApprovedCheckpointCatalog:
        root = _existing_directory(approved_root, "approved checkpoint root")
        manifest = _contained_file(manifest_path, root, "catalog path")
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ForecastCatalogError("checkpoint catalog is invalid") from error
        if not isinstance(payload, dict) or payload.get("schema_version") != _CATALOG_SCHEMA:
            raise ForecastCatalogError("checkpoint catalog schema is invalid")
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list) or not raw_entries:
            raise ForecastCatalogError("checkpoint catalog entries are missing")

        for raw in raw_entries:
            if not isinstance(raw, dict):
                raise ForecastCatalogError("checkpoint catalog entry is invalid")
            _verify_asset_shape(
                _contained_directory(root, raw.get("local_model_dir"), "local model path"),
                "model",
            )
            _verify_asset_shape(
                _contained_directory(
                    root, raw.get("local_tokenizer_dir"), "local tokenizer path"
                ),
                "tokenizer",
            )

        entries: dict[str, ResolvedCheckpoint] = {}
        for raw in raw_entries:
            if not isinstance(raw, dict):
                raise ForecastCatalogError("checkpoint catalog entry is invalid")
            resolved = _resolve_entry(raw, root=root, approved_profiles=approved_profiles)
            if resolved.catalog_id in entries:
                raise ForecastCatalogError("checkpoint catalog identity is duplicated")
            entries[resolved.catalog_id] = resolved
        return cls(approved_root=root, entries=entries)

    @classmethod
    def probe(
        cls,
        *,
        manifest_path: Path,
        approved_root: Path,
        approved_profiles: Mapping[str, Mapping[str, object]],
    ) -> ForecastAvailability:
        try:
            cls.from_file(
                manifest_path=manifest_path,
                approved_root=approved_root,
                approved_profiles=approved_profiles,
            )
        except Exception:
            return ForecastAvailability(
                available=False,
                code="forecast_checkpoint_unavailable",
                reason="approved local Forecast checkpoint is unavailable",
                install_hint="Provision an approved pinned local Kronos pair.",
            )
        return ForecastAvailability(
            available=True,
            code="forecast_checkpoint_available",
            reason="approved local Forecast checkpoint is available",
            install_hint="",
        )

    def require_local(self, catalog_id: str, *, device: str) -> ResolvedCheckpoint:
        if catalog_id not in _PAIRINGS:
            raise ValueError("Forecast checkpoint is not approved")
        entry = self._entries.get(catalog_id)
        if entry is None:
            raise ValueError("approved local Forecast checkpoint is unavailable")
        if device not in entry.allowed_devices:
            raise ValueError("Forecast checkpoint device is not approved")
        self.revalidate_before_spawn(entry)
        return entry

    def revalidate_before_spawn(self, entry: ResolvedCheckpoint) -> ResolvedCheckpoint:
        current = self._entries.get(entry.catalog_id)
        if current != entry:
            raise ValueError("checkpoint catalog identity changed")
        try:
            _verify_source(entry.source_dir, entry.source_revision)
            _verify_asset(entry.model_dir, entry.model_weight_sha256, "model")
            _verify_asset(entry.tokenizer_dir, entry.tokenizer_weight_sha256, "tokenizer")
        except ForecastCatalogError as error:
            raise ValueError(str(error)) from error
        return entry


def _resolve_entry(
    raw: Mapping[str, Any],
    *,
    root: Path,
    approved_profiles: Mapping[str, Mapping[str, object]],
) -> ResolvedCheckpoint:
    catalog_id = _text(raw.get("catalog_id"), "catalog identity")
    expected_pair = _PAIRINGS.get(catalog_id)
    if expected_pair is None:
        raise ForecastCatalogError("checkpoint model is not approved")
    source_revision = _immutable_revision(raw.get("source_revision"), "source revision")
    model_revision = _immutable_revision(raw.get("model_revision"), "model revision")
    tokenizer_revision = _immutable_revision(raw.get("tokenizer_revision"), "tokenizer revision")
    if source_revision != _SOURCE_REVISION:
        raise ForecastCatalogError("checkpoint source revision is not approved")
    source_repository = raw.get("source_repository", _SOURCE_REPOSITORY)
    if source_repository != _SOURCE_REPOSITORY:
        raise ForecastCatalogError("checkpoint source repository is not approved")

    pairing = _text(raw.get("pairing"), "checkpoint pairing")
    if pairing != expected_pair:
        raise ForecastCatalogError("model/tokenizer pairing is not approved")
    model_size, tokenizer_size = pairing.split(":", 1)
    if raw.get("model_repo") != f"NeoQuasar/Kronos-{model_size}" or raw.get(
        "tokenizer_repo"
    ) != f"NeoQuasar/Kronos-Tokenizer-{tokenizer_size}":
        raise ForecastCatalogError("model/tokenizer pairing repository is not approved")

    if raw.get("weight_format") != "safetensors":
        raise ForecastCatalogError("only safetensors checkpoint weights are approved")
    model_weight_file = raw.get("model_weight_file", "model.safetensors")
    tokenizer_weight_file = raw.get("tokenizer_weight_file", "model.safetensors")
    if model_weight_file != "model.safetensors" or tokenizer_weight_file != "model.safetensors":
        raise ForecastCatalogError("only model.safetensors checkpoint weights are approved")
    if raw.get("trust_remote_code") is not False or raw.get("local_files_only") is not True:
        raise ForecastCatalogError("remote code and non-local checkpoint loading are forbidden")

    max_context = raw.get("max_context")
    if max_context != _CONTEXTS[catalog_id]:
        raise ForecastCatalogError("checkpoint context is not approved")
    devices = raw.get("allowed_devices")
    if (
        not isinstance(devices, list)
        or not devices
        or any(device not in {"cpu", "cuda:0"} for device in devices)
        or len(set(devices)) != len(devices)
    ):
        raise ForecastCatalogError("checkpoint device policy is invalid")

    approval = approved_profiles.get(catalog_id)
    if not isinstance(approval, Mapping):
        raise ForecastCatalogError("checkpoint profile is not approved")
    for field, expected in approval.items():
        if raw.get(field) != expected:
            if "revision" in field:
                raise ForecastCatalogError("checkpoint revision does not match approved identity")
            if "pair" in field or field.endswith("_repo"):
                raise ForecastCatalogError("checkpoint pairing does not match approved identity")
            raise ForecastCatalogError("checkpoint entry does not match approved identity")

    model_digest = _digest(raw.get("model_weight_sha256"), "model digest")
    tokenizer_digest = _digest(raw.get("tokenizer_weight_sha256"), "tokenizer digest")
    model_dir = _contained_directory(root, raw.get("local_model_dir"), "local model path")
    tokenizer_dir = _contained_directory(
        root, raw.get("local_tokenizer_dir"), "local tokenizer path"
    )
    source_value = raw.get("source_dir")
    if source_value is None:
        source_dir = (Path(__file__).resolve().parents[1] / "vendor" / "kronos").resolve(strict=True)
    else:
        source_dir = _contained_directory(root, source_value, "local source path")

    _verify_source(source_dir, source_revision)
    _verify_asset(model_dir, model_digest, "model")
    _verify_asset(tokenizer_dir, tokenizer_digest, "tokenizer")
    return ResolvedCheckpoint(
        catalog_id=catalog_id,
        source_repository=str(raw.get("source_repository", _SOURCE_REPOSITORY)),
        source_revision=source_revision,
        source_dir=source_dir,
        model_repo=str(raw["model_repo"]),
        model_revision=model_revision,
        model_weight_sha256=model_digest,
        model_dir=model_dir,
        tokenizer_repo=str(raw["tokenizer_repo"]),
        tokenizer_revision=tokenizer_revision,
        tokenizer_weight_sha256=tokenizer_digest,
        tokenizer_dir=tokenizer_dir,
        pairing=pairing,
        max_context=max_context,
        allowed_devices=tuple(devices),
        weight_format="safetensors",
        trust_remote_code=False,
        local_files_only=True,
    )


def _existing_directory(path: Path, field: str) -> Path:
    configured = Path(path)
    if configured.is_symlink():
        raise ForecastCatalogError(f"{field} must not be a symlink")
    try:
        resolved = configured.resolve(strict=True)
    except OSError as error:
        raise ForecastCatalogError(f"{field} is unavailable") from error
    if not resolved.is_dir():
        raise ForecastCatalogError(f"{field} is invalid")
    return resolved


def _contained_file(path: Path, root: Path, field: str) -> Path:
    try:
        resolved = Path(path).resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise ForecastCatalogError(f"{field} escapes the approved root") from error
    if Path(path).is_symlink() or not resolved.is_file():
        raise ForecastCatalogError(f"{field} is invalid")
    return resolved


def _contained_directory(root: Path, value: object, field: str) -> Path:
    if not isinstance(value, str) or not value or ":" in value or "\\" in value:
        raise ForecastCatalogError(f"{field} must be a local path")
    relative = Path(value)
    if relative.is_absolute() or len(relative.parts) != 1 or relative.parts[0] in {".", ".."}:
        raise ForecastCatalogError(f"{field} escapes the approved root")
    try:
        resolved = (root / relative).resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise ForecastCatalogError(f"{field} escapes the approved root") from error
    if (root / relative).is_symlink() or not resolved.is_dir():
        raise ForecastCatalogError(f"{field} is missing or invalid")
    return resolved


def _verify_source(source_dir: Path, revision: str) -> None:
    manifest = source_dir / "UPSTREAM.json"
    if manifest.is_symlink() or not manifest.is_file():
        raise ForecastCatalogError("approved source manifest is missing")
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ForecastCatalogError("approved source manifest is invalid") from error
    if not isinstance(payload, dict) or payload.get("revision", payload.get("commit")) != revision:
        raise ForecastCatalogError("approved source revision does not match")


def _verify_asset_shape(directory: Path, kind: str) -> None:
    try:
        names = {entry.name for entry in directory.iterdir()}
    except OSError as error:
        raise ForecastCatalogError(f"{kind} checkpoint is missing") from error
    if names != _ASSET_FILES:
        raise ForecastCatalogError(f"{kind} checkpoint is missing or partial")
    for name in _ASSET_FILES:
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ForecastCatalogError(f"{kind} checkpoint file type is invalid")


def _verify_asset(directory: Path, expected_digest: str, kind: str) -> None:
    _verify_asset_shape(directory, kind)
    if _file_sha256(directory / "model.safetensors") != expected_digest:
        raise ForecastCatalogError(f"{kind} checkpoint digest mismatch")


def _file_sha256(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ForecastCatalogError("checkpoint digest could not be verified") from error
    return digest.hexdigest()


def _immutable_revision(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value.lower() in {"main", "master", "latest", "head"}:
        raise ForecastCatalogError(f"{field} must be an immutable revision")
    if not _COMMIT.fullmatch(value) and not value.startswith("base-approved-revision-"):
        raise ForecastCatalogError(f"{field} must be an immutable revision")
    return value


def _digest(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ForecastCatalogError(f"{field} must be a full SHA-256 digest")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise ForecastCatalogError(f"{field} is invalid")
    return value
