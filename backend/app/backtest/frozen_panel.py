"""Immutable, checksum-verified Polars panels for governed backtest workers."""
from __future__ import annotations

import json
import re
import shutil
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import polars as pl

_SCHEMA_VERSION = "frozen-panel-artifact-v1"
_ARTIFACT_ID = re.compile(r"^[0-9a-f]{32}$")


class FrozenPanelArtifactError(ValueError):
    """Raised when a frozen panel is absent, malformed, or tampered with."""


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _checksum(value: bytes) -> str:
    return sha256(value).hexdigest()


class FrozenPanelArtifactStore:
    """Persist governed panels under a server-owned root and verify every read."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def create(self, *, scope: Mapping[str, object], panel: pl.DataFrame) -> dict[str, str]:
        if panel.is_empty():
            raise FrozenPanelArtifactError("cannot freeze an empty governed panel")

        self.root.mkdir(parents=True, exist_ok=True)
        artifact_id = uuid4().hex
        artifact_dir = self.root / artifact_id
        temporary_dir = self.root / f".{artifact_id}.tmp"
        scope_checksum = _checksum(_canonical_json(dict(scope)))

        try:
            temporary_dir.mkdir()
            panel_path = temporary_dir / "panel.parquet"
            panel.write_parquet(panel_path)
            panel_checksum = _checksum(panel_path.read_bytes())
            metadata_base = {
                "schema_version": _SCHEMA_VERSION,
                "artifact_id": artifact_id,
                "scope_checksum": scope_checksum,
                "panel_checksum": panel_checksum,
            }
            metadata = {
                **metadata_base,
                "metadata_checksum": _checksum(_canonical_json(metadata_base)),
            }
            (temporary_dir / "metadata.json").write_bytes(_canonical_json(metadata))
            temporary_dir.rename(artifact_dir)
        except Exception as error:
            shutil.rmtree(temporary_dir, ignore_errors=True)
            raise FrozenPanelArtifactError("could not persist frozen governed panel") from error

        return metadata

    def load(
        self,
        *,
        reference: Mapping[str, object],
        expected_scope: Mapping[str, object],
    ) -> pl.DataFrame:
        normalized = self._validate_reference(reference)
        artifact_dir = self.root / normalized["artifact_id"]
        metadata_path = artifact_dir / "metadata.json"
        panel_path = artifact_dir / "panel.parquet"
        if not metadata_path.is_file() or not panel_path.is_file():
            raise FrozenPanelArtifactError("frozen governed panel is incomplete")

        try:
            metadata_value: Any = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FrozenPanelArtifactError("frozen governed panel metadata is invalid") from error
        if not isinstance(metadata_value, dict):
            raise FrozenPanelArtifactError("frozen governed panel metadata is invalid")
        metadata = self._validate_reference(metadata_value)
        if metadata != normalized:
            raise FrozenPanelArtifactError("frozen governed panel reference does not match metadata")

        metadata_base = {key: metadata[key] for key in metadata if key != "metadata_checksum"}
        if _checksum(_canonical_json(metadata_base)) != metadata["metadata_checksum"]:
            raise FrozenPanelArtifactError("frozen governed panel metadata checksum does not match")
        if _checksum(_canonical_json(dict(expected_scope))) != metadata["scope_checksum"]:
            raise FrozenPanelArtifactError("frozen governed panel scope does not match")

        try:
            panel_bytes = panel_path.read_bytes()
        except OSError as error:
            raise FrozenPanelArtifactError("frozen governed panel is unreadable") from error
        if _checksum(panel_bytes) != metadata["panel_checksum"]:
            raise FrozenPanelArtifactError("frozen governed panel checksum does not match")
        try:
            return pl.read_parquet(panel_path)
        except Exception as error:
            raise FrozenPanelArtifactError("frozen governed panel payload is invalid") from error

    @staticmethod
    def _validate_reference(reference: Mapping[str, object]) -> dict[str, str]:
        required = {
            "schema_version",
            "artifact_id",
            "scope_checksum",
            "panel_checksum",
            "metadata_checksum",
        }
        if set(reference) != required:
            raise FrozenPanelArtifactError("frozen governed panel reference has invalid fields")
        normalized = {key: value for key, value in reference.items() if isinstance(value, str)}
        if len(normalized) != len(required):
            raise FrozenPanelArtifactError("frozen governed panel reference has invalid values")
        if normalized["schema_version"] != _SCHEMA_VERSION:
            raise FrozenPanelArtifactError("frozen governed panel schema version is unsupported")
        if not _ARTIFACT_ID.fullmatch(normalized["artifact_id"]):
            raise FrozenPanelArtifactError("frozen governed panel artifact identifier is invalid")
        for key in ("scope_checksum", "panel_checksum", "metadata_checksum"):
            if not re.fullmatch(r"[0-9a-f]{64}", normalized[key]):
                raise FrozenPanelArtifactError("frozen governed panel checksum is invalid")
        return normalized
