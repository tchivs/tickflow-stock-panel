"""Managed immutable artifact storage for research evaluation evidence."""
from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

_RUN_ID = re.compile(r"[0-9a-f]{32}\Z")


class ArtifactWriteError(RuntimeError):
    """An evidence bundle could not be made durably immutable."""


@dataclass(frozen=True, slots=True)
class ArtifactDescriptor:
    """A content-addressed reference to one managed evaluation artifact."""

    evaluation_run_id: str
    relative_path: str
    content_type: str
    byte_size: int
    checksum_sha256: str
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class EvaluationArtifactService:
    """Writes evaluation evidence below one application-owned data root only."""

    def __init__(self, data_dir: Path) -> None:
        self.root = Path(data_dir).resolve() / "research_artifacts"

    def write_bundle(
        self,
        evaluation_run_id: str,
        *,
        signals: list[Mapping[str, Any]],
        metric_series: list[Mapping[str, Any]],
        result: Mapping[str, Any],
        monthly_series: list[Mapping[str, Any]] | None = None,
    ) -> list[ArtifactDescriptor]:
        """Create an all-new namespace and immutable JSON evidence files.

        Namespace creation and every file use exclusive creation. A collision is a
        failure, never a reason to reuse or overwrite retained evidence.  The
        ``monthly_series`` payload (per-month IC/RankIC/ICIR/robustness rows) is
        written as ``monthly_series.json`` when supplied — additive, existing
        descriptors unchanged.
        """
        namespace = self._namespace(evaluation_run_id)
        try:
            namespace.mkdir(parents=True, exist_ok=False)
        except FileExistsError as error:
            raise ArtifactWriteError(f"artifact namespace already exists for run {evaluation_run_id}") from error
        except OSError as error:
            raise ArtifactWriteError(f"could not create artifact namespace: {error}") from error

        descriptors = [
            self._write_json(namespace, evaluation_run_id, "signals.json", signals),
            self._write_json(namespace, evaluation_run_id, "metric_series.json", metric_series),
            self._write_json(namespace, evaluation_run_id, "result.json", result),
        ]
        if monthly_series is not None:
            descriptors.append(
                self._write_json(namespace, evaluation_run_id, "monthly_series.json", monthly_series)
            )
        return descriptors

    def _namespace(self, evaluation_run_id: str) -> Path:
        if not isinstance(evaluation_run_id, str) or not _RUN_ID.fullmatch(evaluation_run_id):
            raise ArtifactWriteError("evaluation run ID must be an opaque UUID hex value")
        namespace = self.root / evaluation_run_id
        try:
            namespace.relative_to(self.root)
        except ValueError as error:
            raise ArtifactWriteError("artifact namespace escapes the managed root") from error
        return namespace

    def _write_json(
        self,
        namespace: Path,
        evaluation_run_id: str,
        filename: str,
        payload: object,
    ) -> ArtifactDescriptor:
        if filename != Path(filename).name:
            raise ArtifactWriteError("artifact filename must be a managed basename")
        path = namespace / filename
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise ArtifactWriteError("artifact path escapes the managed root") from error

        # Canonical bytes make the checksum independently verifiable and stable.
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise ArtifactWriteError(f"artifact already exists: {filename}") from error
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            # A partial file must not be presented as a completed artifact.
            path.unlink(missing_ok=True)
            raise

        return ArtifactDescriptor(
            evaluation_run_id=evaluation_run_id,
            relative_path=path.relative_to(self.root.parent).as_posix(),
            content_type="application/json",
            byte_size=len(content),
            checksum_sha256=sha256(content).hexdigest(),
            created_at=datetime.now(UTC).isoformat(),
        )



class AlphaArtifactVerificationError(ValueError):
    """A managed Alpha artifact failed read-side verification (fail closed)."""


class AlphaRunArtifactService:
    """Managed artifact storage for Alpha run evidence under ``alpha_runs/``.

    The server derives the content-addressed relative key exactly as
    ``research_artifacts/alpha_runs/{run_id}/{sha256}.json`` from the lowercase
    SHA-256 of the canonical UTF-8 bytes; clients cannot supply or alter the
    path (D-03, T-45-04).
    """

    def __init__(self, data_dir: Path) -> None:
        self.root = Path(data_dir).resolve() / "research_artifacts"

    def write(
        self,
        *,
        run_id: str,
        payload: Mapping[str, Any],
        created_at: str | None = None,
    ) -> dict[str, Any]:
        """Write canonical bytes and return the content-addressed descriptor.

        The bytes are canonical JSON (sorted keys, no whitespace, no NaN).  The
        key is derived from the SHA-256 of those bytes; callers receive the
        exact ``relative_path`` the server computed.  Exclusive creation
        prevents overwriting a retained artifact (T-45-04).
        """
        self._validate_run_id(run_id)
        content = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
        digest = sha256(content).hexdigest()
        namespace = self.root / "alpha_runs" / run_id
        namespace.mkdir(parents=True, exist_ok=True)
        path = namespace / f"{digest}.json"
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise AlphaArtifactVerificationError(
                "artifact path escapes the managed root"
            ) from error
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise ArtifactWriteError(
                f"artifact already exists for run {run_id}: {digest}"
            ) from error
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            path.unlink(missing_ok=True)
            raise
        relative_path = path.relative_to(self.root.parent).as_posix()
        return {
            "relative_path": relative_path,
            "content_type": "application/json",
            "byte_size": len(content),
            "checksum_sha256": digest,
            "created_at": created_at or datetime.now(UTC).isoformat(),
        }

    def verify_artifact(
        self,
        *,
        run_id: str,
        checksum_sha256: str,
        expected_byte_size: int | None = None,
        expected_content_type: str | None = None,
    ) -> dict[str, Any]:
        """Read-side verification of a managed Alpha run artifact.

        Resolves only the server-derived managed relative key and recomputes
        content type, byte size, and lowercase SHA-256.  Missing artifact,
        changed bytes, changed size/type, or a path traversal attempt is
        rejected before any checkpoint/event cursor advancement (D-03, T-45-04).
        """
        self._validate_run_id(run_id)
        if not isinstance(checksum_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum_sha256):
            raise AlphaArtifactVerificationError(
                "checksum_sha256 must be a lowercase SHA-256 hex digest"
            )
        relative_path = f"research_artifacts/alpha_runs/{run_id}/{checksum_sha256}.json"
        managed = self.root.parent / relative_path
        try:
            managed.relative_to(self.root.parent)
        except ValueError as error:
            raise AlphaArtifactVerificationError(
                "artifact path escapes the managed root"
            ) from error
        if not managed.is_file():
            raise AlphaArtifactVerificationError(
                f"artifact not found at managed key: {relative_path}"
            )
        content = managed.read_bytes()
        actual_digest = sha256(content).hexdigest()
        if actual_digest != checksum_sha256:
            raise AlphaArtifactVerificationError(
                "artifact bytes do not match the referenced checksum"
            )
        if expected_byte_size is not None and len(content) != expected_byte_size:
            raise AlphaArtifactVerificationError(
                "artifact byte size does not match the descriptor"
            )
        if expected_content_type is not None and expected_content_type != "application/json":
            raise AlphaArtifactVerificationError(
                "artifact content type does not match the descriptor"
            )
        return {
            "relative_path": relative_path,
            "content_type": "application/json",
            "byte_size": len(content),
            "checksum_sha256": actual_digest,
        }

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        if not isinstance(run_id, str) or not run_id:
            raise AlphaArtifactVerificationError("run_id is required")
        # Path-traversal hardening: no separators or parent references.
        if "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
            raise AlphaArtifactVerificationError("run_id contains invalid path characters")