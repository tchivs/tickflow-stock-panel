"""Domain-neutral managed immutable artifacts for optional Phase 05 modules."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Callable, Mapping
from uuid import uuid4


_ARTIFACT_ID = re.compile(r"[0-9a-f]{32}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_DESCRIPTOR_FIELDS = {
    "artifact_id",
    "relative_path",
    "content_type",
    "byte_size",
    "checksum_sha256",
    "schema_version",
    "scope_sha256",
    "created_at",
}


class ManagedArtifactError(RuntimeError):
    """A managed artifact was incomplete, unsafe, or failed verification."""


class ManagedArtifactCleanupError(ManagedArtifactError):
    """An invocation-owned temporary namespace requires reconciliation."""

    def __init__(self, artifact_id: str) -> None:
        super().__init__(
            f"managed artifact temporary cleanup failed for {artifact_id}"
        )
        self.artifact_id = artifact_id


@dataclass(frozen=True, slots=True)
class ArtifactDescriptor:
    """Safe public identity and integrity metadata for one immutable payload."""

    artifact_id: str
    relative_path: str
    content_type: str
    byte_size: int
    checksum_sha256: str
    schema_version: str
    scope_sha256: str
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class ManagedImmutableArtifactStore:
    """Atomically promotes verified payloads below one application-owned root."""

    def __init__(self, root: Path) -> None:
        configured_root = Path(root)
        try:
            configured_root.mkdir(parents=True, mode=0o700, exist_ok=True)
            self.root = configured_root.resolve(strict=True)
            if not self.root.is_dir():
                raise ManagedArtifactError("managed artifact root is not a directory")
            self.root.chmod(0o700)
        except ManagedArtifactError:
            raise
        except OSError as error:
            raise ManagedArtifactError("managed artifact root is unavailable") from error

    def create_bytes(
        self,
        payload: bytes,
        *,
        schema_version: str,
        scope: Mapping[str, object],
        content_type: str,
    ) -> ArtifactDescriptor:
        """Create one immutable byte payload in a new server-generated namespace."""
        if not isinstance(payload, bytes):
            raise ManagedArtifactError("artifact payload must be bytes")
        return self._create(
            payload_name="payload.bin",
            schema_version=schema_version,
            scope=scope,
            content_type=content_type,
            writer=lambda path: self._write_exclusive(path, payload),
        )

    def create_parquet(
        self,
        frame: Any,
        *,
        schema_version: str,
        scope: Mapping[str, object],
    ) -> ArtifactDescriptor:
        """Create Parquet and translate the documented Polars exception base."""
        import polars as pl

        def write_parquet(path: Path) -> None:
            if not callable(getattr(frame, "write_parquet", None)):
                raise ManagedArtifactError("artifact frame does not support Parquet output")
            try:
                frame.write_parquet(path)
                path.chmod(0o600)
                self._fsync_file(path)
            except ManagedArtifactError:
                raise
            except (pl.exceptions.PolarsError, OSError, TypeError, ValueError) as error:
                raise ManagedArtifactError("could not write managed Parquet payload") from error

        return self._create(
            payload_name="payload.parquet",
            schema_version=schema_version,
            scope=scope,
            content_type="application/vnd.apache.parquet",
            writer=write_parquet,
        )

    def descriptor(self, artifact_id: str) -> ArtifactDescriptor:
        """Load and independently verify persisted descriptor metadata."""
        descriptor, _scope, _payload_path = self._read_record(artifact_id)
        return descriptor

    def load_bytes(self, descriptor: ArtifactDescriptor) -> bytes:
        """Return bytes only after descriptor, metadata, scope, size, and digest checks."""
        persisted, _scope, payload_path = self._verified_payload(descriptor)
        if persisted.content_type == "application/vnd.apache.parquet":
            raise ManagedArtifactError("Parquet artifacts must use load_parquet")
        try:
            return payload_path.read_bytes()
        except OSError as error:
            raise ManagedArtifactError("managed artifact payload is unavailable") from error

    def load_parquet(self, descriptor: ArtifactDescriptor) -> Any:
        """Return a verified Parquet frame."""
        persisted, _scope, payload_path = self._verified_payload(descriptor)
        if persisted.content_type != "application/vnd.apache.parquet":
            raise ManagedArtifactError("managed artifact is not Parquet")
        try:
            import polars as pl

            return pl.read_parquet(payload_path)
        except (pl.exceptions.PolarsError, OSError, TypeError, ValueError) as error:
            raise ManagedArtifactError("managed Parquet payload could not be decoded") from error

    def _create(
        self,
        *,
        payload_name: str,
        schema_version: str,
        scope: Mapping[str, object],
        content_type: str,
        writer: Callable[[Path], None],
    ) -> ArtifactDescriptor:
        schema = self._nonempty_text(schema_version, "schema version")
        media_type = self._nonempty_text(content_type, "content type")
        scope_object = self._scope_object(scope)
        scope_bytes = self._canonical_json(scope_object)
        scope_digest = sha256(scope_bytes).hexdigest()
        artifact_id = uuid4().hex
        self._validate_artifact_id(artifact_id)
        temporary = self._contained(self.root / f".{artifact_id}.tmp", allow_missing=True)
        final = self._contained(self.root / artifact_id, allow_missing=True)
        if temporary.exists() or final.exists():
            raise ManagedArtifactError("managed artifact namespace collision")

        temporary_created = False
        try:
            temporary.mkdir(mode=0o700, exist_ok=False)
            temporary_created = True
            payload_path = temporary / payload_name
            writer(payload_path)
            if not payload_path.is_file() or payload_path.is_symlink():
                raise ManagedArtifactError("managed artifact payload is incomplete")
            byte_size = payload_path.stat().st_size
            payload_digest = self._file_sha256(payload_path)
            descriptor = ArtifactDescriptor(
                artifact_id=artifact_id,
                relative_path=f"{artifact_id}/{payload_name}",
                content_type=media_type,
                byte_size=byte_size,
                checksum_sha256=payload_digest,
                schema_version=schema,
                scope_sha256=scope_digest,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            metadata = self._canonical_json(
                {"descriptor": descriptor.as_dict(), "scope": scope_object}
            )
            self._write_exclusive(temporary / "metadata.json", metadata)
            self._write_exclusive(
                temporary / "metadata.sha256",
                f"{sha256(metadata).hexdigest()}\n".encode("ascii"),
            )
            self._fsync_directory(temporary)
            if final.exists():
                raise ManagedArtifactError("managed artifact namespace collision")
            temporary.rename(final)
            final.chmod(0o700)
            self._fsync_directory(self.root)
            return descriptor
        except ManagedArtifactError:
            raise
        except (OSError, TypeError, ValueError) as error:
            raise ManagedArtifactError("could not atomically create managed artifact") from error
        finally:
            if temporary_created:
                self._remove_temporary(temporary, artifact_id=artifact_id)

    def _verified_payload(
        self, descriptor: ArtifactDescriptor
    ) -> tuple[ArtifactDescriptor, dict[str, object], Path]:
        if not isinstance(descriptor, ArtifactDescriptor):
            raise ManagedArtifactError("managed artifact descriptor has an invalid type")
        persisted, scope, payload_path = self._read_record(descriptor.artifact_id)
        if persisted != descriptor:
            raise ManagedArtifactError("managed artifact descriptor does not match metadata")
        return persisted, scope, payload_path

    def _read_record(
        self, artifact_id: str
    ) -> tuple[ArtifactDescriptor, dict[str, object], Path]:
        self._validate_artifact_id(artifact_id)
        namespace = self._contained(self.root / artifact_id, allow_missing=False)
        if namespace.is_symlink() or not namespace.is_dir():
            raise ManagedArtifactError("managed artifact namespace is incomplete")
        metadata_path = namespace / "metadata.json"
        digest_path = namespace / "metadata.sha256"
        for path in (metadata_path, digest_path):
            if path.is_symlink() or not path.is_file():
                raise ManagedArtifactError("managed artifact metadata is incomplete")
        try:
            metadata_bytes = metadata_path.read_bytes()
            recorded_digest = digest_path.read_text(encoding="ascii").strip()
        except (OSError, UnicodeError) as error:
            raise ManagedArtifactError("managed artifact metadata is unavailable") from error
        if not _SHA256.fullmatch(recorded_digest) or not self._constant_equal(
            recorded_digest, sha256(metadata_bytes).hexdigest()
        ):
            raise ManagedArtifactError("managed artifact metadata checksum mismatch")
        try:
            metadata = json.loads(metadata_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ManagedArtifactError("managed artifact metadata is invalid") from error
        if not isinstance(metadata, dict) or set(metadata) != {"descriptor", "scope"}:
            raise ManagedArtifactError("managed artifact metadata schema is invalid")
        raw_descriptor = metadata["descriptor"]
        if not isinstance(raw_descriptor, dict) or set(raw_descriptor) != _DESCRIPTOR_FIELDS:
            raise ManagedArtifactError("managed artifact descriptor schema is invalid")
        try:
            descriptor = ArtifactDescriptor(**raw_descriptor)
        except (TypeError, ValueError) as error:
            raise ManagedArtifactError("managed artifact descriptor is invalid") from error
        self._validate_descriptor(descriptor, artifact_id)
        scope = self._scope_object(metadata["scope"])
        scope_digest = sha256(self._canonical_json(scope)).hexdigest()
        if not self._constant_equal(scope_digest, descriptor.scope_sha256):
            raise ManagedArtifactError("managed artifact scope checksum mismatch")
        payload_path = self._contained(self.root / descriptor.relative_path, allow_missing=False)
        if payload_path.parent != namespace or payload_path.is_symlink() or not payload_path.is_file():
            raise ManagedArtifactError("managed artifact payload is incomplete")
        expected_names = {payload_path.name, "metadata.json", "metadata.sha256"}
        try:
            actual_names = {entry.name for entry in namespace.iterdir()}
        except OSError as error:
            raise ManagedArtifactError("managed artifact namespace is unavailable") from error
        if actual_names != expected_names:
            raise ManagedArtifactError("managed artifact namespace contains unexpected files")
        actual_size = payload_path.stat().st_size
        if actual_size != descriptor.byte_size:
            raise ManagedArtifactError("managed artifact payload size mismatch")
        actual_digest = self._file_sha256(payload_path)
        if not self._constant_equal(actual_digest, descriptor.checksum_sha256):
            raise ManagedArtifactError("managed artifact payload checksum mismatch")
        return descriptor, scope, payload_path

    def _validate_descriptor(self, descriptor: ArtifactDescriptor, artifact_id: str) -> None:
        if descriptor.artifact_id != artifact_id:
            raise ManagedArtifactError("managed artifact descriptor identifier mismatch")
        self._validate_artifact_id(descriptor.artifact_id)
        expected_names = {"payload.bin", "payload.parquet"}
        relative = Path(descriptor.relative_path)
        if (
            relative.is_absolute()
            or relative.parts[:1] != (artifact_id,)
            or len(relative.parts) != 2
            or relative.name not in expected_names
        ):
            raise ManagedArtifactError("managed artifact descriptor path is invalid")
        if not isinstance(descriptor.byte_size, int) or descriptor.byte_size < 0:
            raise ManagedArtifactError("managed artifact descriptor size is invalid")
        if not _SHA256.fullmatch(descriptor.checksum_sha256):
            raise ManagedArtifactError("managed artifact payload checksum is invalid")
        if not _SHA256.fullmatch(descriptor.scope_sha256):
            raise ManagedArtifactError("managed artifact scope checksum is invalid")
        self._nonempty_text(descriptor.content_type, "content type")
        self._nonempty_text(descriptor.schema_version, "schema version")
        self._nonempty_text(descriptor.created_at, "created timestamp")

    def _contained(self, path: Path, *, allow_missing: bool) -> Path:
        try:
            resolved = path.resolve(strict=not allow_missing)
            resolved.relative_to(self.root)
            return resolved
        except (OSError, ValueError) as error:
            raise ManagedArtifactError("managed artifact path escapes its configured root") from error

    @staticmethod
    def _scope_object(scope: object) -> dict[str, object]:
        if not isinstance(scope, Mapping):
            raise ManagedArtifactError("artifact scope must be a mapping")
        return dict(scope)

    @staticmethod
    def _canonical_json(value: object) -> bytes:
        try:
            return json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise ManagedArtifactError("artifact metadata must be canonical JSON") from error

    @staticmethod
    def _nonempty_text(value: object, field: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > 512:
            raise ManagedArtifactError(f"managed artifact {field} is invalid")
        return value

    @staticmethod
    def _validate_artifact_id(artifact_id: object) -> None:
        if not isinstance(artifact_id, str) or not _ARTIFACT_ID.fullmatch(artifact_id):
            raise ManagedArtifactError("managed artifact identifier is invalid")

    @staticmethod
    def _write_exclusive(path: Path, payload: bytes) -> None:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise ManagedArtifactError("managed artifact file already exists") from error
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = sha256()
        try:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError as error:
            raise ManagedArtifactError("managed artifact payload could not be verified") from error
        return digest.hexdigest()

    @staticmethod
    def _fsync_file(path: Path) -> None:
        with path.open("rb") as handle:
            os.fsync(handle.fileno())

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _remove_temporary(self, path: Path, *, artifact_id: str) -> None:
        expected = self.root / f".{artifact_id}.tmp"
        if path != expected:
            raise ManagedArtifactCleanupError(artifact_id)
        try:
            if path.exists():
                shutil.rmtree(path)
        except OSError as error:
            raise ManagedArtifactCleanupError(artifact_id) from error

    @staticmethod
    def _constant_equal(left: str, right: str) -> bool:
        from hmac import compare_digest

        return compare_digest(left, right)
