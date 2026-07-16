"""Shadow raw-artifact adapter over the shared immutable managed store."""
from __future__ import annotations

from pathlib import Path
import re
import shutil
from typing import Any, Mapping

from app.optional_artifacts import (
    ArtifactDescriptor,
    ManagedArtifactError,
    ManagedImmutableArtifactStore,
)


_BATCH_ID = re.compile(r"[0-9a-f]{32}\Z")


class ShadowArtifactError(RuntimeError):
    """A Shadow raw artifact is unsafe, incomplete, or was tampered with."""


class ShadowArtifactStore:
    """Create one independently verifiable managed namespace per import attempt."""

    SCHEMA_VERSION = "shadow-raw-v1"

    def __init__(self, root: Path) -> None:
        try:
            self._root_store = ManagedImmutableArtifactStore(Path(root))
            self.root = self._root_store.root
        except ManagedArtifactError as error:
            raise ShadowArtifactError("Shadow artifact root is unavailable") from error

    def create(
        self,
        *,
        batch_id: str,
        content: bytes,
        media_type: str,
        source_label: str,
        original_name: str,
    ) -> dict[str, Any]:
        """Finalize raw bytes before the corresponding short database transaction."""
        self._validate_batch_id(batch_id)
        try:
            batch_root = self._contained(self.root / batch_id, allow_missing=True)
            batch_store = ManagedImmutableArtifactStore(batch_root)
            descriptor = batch_store.create_bytes(
                content,
                schema_version=self.SCHEMA_VERSION,
                content_type=media_type,
                scope={
                    "batch_id": batch_id,
                    "source_label": self._bounded(source_label, "source label"),
                    "original_name": self._bounded(original_name, "original name"),
                },
            )
        except (ManagedArtifactError, OSError, ValueError) as error:
            raise ShadowArtifactError("Shadow raw artifact could not be finalized") from error
        public = descriptor.as_dict()
        public["relative_path"] = f'{batch_id}/{descriptor.relative_path}'
        return public

    def load(self, descriptor: Mapping[str, object]) -> bytes:
        """Load raw bytes only after all shared descriptor and payload checks pass."""
        try:
            batch_id, inner = self._inner_descriptor(descriptor)
            store = ManagedImmutableArtifactStore(self._contained(self.root / batch_id, allow_missing=False))
            return store.load_bytes(inner)
        except (ManagedArtifactError, OSError, TypeError, ValueError, KeyError) as error:
            raise ShadowArtifactError("Shadow raw artifact failed integrity verification") from error

    def discard_uncommitted(self, *, batch_id: str, descriptor: Mapping[str, object]) -> None:
        """Remove only a just-created, unreferenced attempt after database failure."""
        try:
            descriptor_batch, _inner = self._inner_descriptor(descriptor)
            if descriptor_batch != batch_id:
                raise ShadowArtifactError("Shadow artifact batch identity mismatch")
            namespace = self._contained(self.root / batch_id, allow_missing=False)
            shutil.rmtree(namespace)
        except ShadowArtifactError:
            raise
        except (ManagedArtifactError, OSError, TypeError, ValueError, KeyError) as error:
            raise ShadowArtifactError("uncommitted Shadow artifact cleanup failed") from error

    def list_temporary_namespaces(self) -> list[str]:
        try:
            return sorted(
                str(path.relative_to(self.root))
                for path in self.root.rglob(".*.tmp")
                if path.exists()
            )
        except OSError as error:
            raise ShadowArtifactError("Shadow artifact root cannot be inspected") from error

    def managed_paths(self) -> list[str]:
        try:
            return sorted(str(path.resolve()) for path in self.root.rglob("*") if path.is_file())
        except OSError as error:
            raise ShadowArtifactError("Shadow artifact root cannot be inspected") from error

    def resolve_for_test(self, relative_path: str) -> Path:
        """Expose a contained payload path to integrity tests, never to public DTOs."""
        return self._contained(self.root / relative_path, allow_missing=False)

    def _inner_descriptor(
        self, descriptor: Mapping[str, object]
    ) -> tuple[str, ArtifactDescriptor]:
        if not isinstance(descriptor, Mapping):
            raise ShadowArtifactError("Shadow artifact descriptor is invalid")
        fields = {
            "artifact_id",
            "relative_path",
            "content_type",
            "byte_size",
            "checksum_sha256",
            "schema_version",
            "scope_sha256",
            "created_at",
        }
        if set(descriptor) != fields:
            raise ShadowArtifactError("Shadow artifact descriptor schema is invalid")
        relative = Path(str(descriptor["relative_path"]))
        if relative.is_absolute() or len(relative.parts) != 3:
            raise ShadowArtifactError("Shadow artifact descriptor path is invalid")
        batch_id, artifact_id, payload_name = relative.parts
        self._validate_batch_id(batch_id)
        if artifact_id != descriptor["artifact_id"] or payload_name != "payload.bin":
            raise ShadowArtifactError("Shadow artifact descriptor identity is invalid")
        values = dict(descriptor)
        values["relative_path"] = f"{artifact_id}/{payload_name}"
        return batch_id, ArtifactDescriptor(**values)

    def _contained(self, path: Path, *, allow_missing: bool) -> Path:
        try:
            resolved = path.resolve(strict=not allow_missing)
            resolved.relative_to(self.root)
            return resolved
        except (OSError, ValueError) as error:
            raise ShadowArtifactError("Shadow artifact path escapes its configured root") from error

    @staticmethod
    def _validate_batch_id(batch_id: object) -> None:
        if not isinstance(batch_id, str) or not _BATCH_ID.fullmatch(batch_id):
            raise ShadowArtifactError("Shadow batch identifier is invalid")

    @staticmethod
    def _bounded(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 512:
            raise ShadowArtifactError(f"Shadow artifact {field} is invalid")
        return value
