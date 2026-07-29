"""Review-only synchronization for the pinned Kronos inference source.

This module is an operator tool, never a runtime dependency. Network access occurs only
inside :func:`stage_sync`, after the caller explicitly selects ``--stage``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path
from typing import Final, Sequence


SOURCE_REPOSITORY: Final = "https://github.com/shiyu-coder/Kronos"
SOURCE_COMMIT: Final = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
SOURCE_BLOBS: Final = {
    "LICENSE": "88b04125e828241d8aada64bfe7f700bb03bcef8",
    "model/__init__.py": "718d07a21b53b7eff4a6564e6dfcae8ee7e8c6b1",
    "model/kronos.py": "ce4494ee0b3ec8751b09d5488c93bde995e008e0",
    "model/module.py": "f2a05158b48a56e9235426f6583e384360d761f9",
}
VENDORED_FILES: Final = {
    "model/__init__.py": "__init__.py",
    "model/kronos.py": "kronos.py",
    "model/module.py": "module.py",
    "LICENSE": "LICENSE",
}
APPROVED_MODIFICATIONS: Final = {
    "model/__init__.py": [
        "Restricted package exports to Kronos and KronosTokenizer; model_dict, get_model_class, and KronosPredictor export were omitted.",
    ],
    "model/kronos.py": [
        "Removed the sys.path mutation used by the upstream repository layout.",
        "Changed the model.module wildcard import to the package-relative .module import.",
    ],
    "model/module.py": [],
    "LICENSE": [],
}
EXPECTED_VENDORED_SHA256: Final = {
    "__init__.py": "c953ae293af8b789effd503f3f268b4bb4d1f66dd4cab73506548c104a9f8a0e",
    "kronos.py": "53c8907fa05dd88e59ff6a22c365320134df88d3d05e861959bbaf1aeb9022f4",
    "module.py": "a07edbadc0e96804c8158c021bbc6063bb7cc43b34d7fc470d5c8ff2005a409f",
    "LICENSE": "acb2d194d378204e5f2be4dcd24d39ecac437903620c790c3315a96dab388fdc",
}

BACKEND_ROOT: Final = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT: Final = BACKEND_ROOT.parent
VENDOR_ROOT: Final = BACKEND_ROOT / "app" / "vendor" / "kronos"
MANIFEST_NAME: Final = "UPSTREAM.json"


class VendorVerificationError(RuntimeError):
    """The staged or vendored source does not match the approved identity."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324 - Git object identity


def _safe_error(message: str) -> VendorVerificationError:
    return VendorVerificationError(message)


def _transform(source_path: str, source: bytes) -> bytes:
    if source_path == "model/__init__.py":
        return (
            b'"""Reviewed Kronos inference exports."""\n\n'
            b"from .kronos import Kronos, KronosTokenizer\n\n"
            b'__all__ = ["Kronos", "KronosTokenizer"]\n'
        )
    if source_path == "model/kronos.py":
        text = source.decode("utf-8")
        text = text.replace("import sys\n", "")
        text = text.replace('sys.path.append("../")\n', "")
        text = text.replace("from model.module import *", "from .module import *")
        if "sys.path" in text or "from model.module import" in text:
            raise _safe_error("approved import transformation did not converge")
        return text.encode("utf-8")
    return source


def _manifest_for(source_bytes: dict[str, bytes], vendored_bytes: dict[str, bytes]) -> dict:
    return {
        "repository": SOURCE_REPOSITORY,
        "commit": SOURCE_COMMIT,
        "license": "MIT",
        "reviewed_at": "2026-07-16",
        "files": {
            source_path: {
                "destination": VENDORED_FILES[source_path],
                "source_blob_sha1": SOURCE_BLOBS[source_path],
                "source_sha256": _sha256(source_bytes[source_path]),
                "vendored_sha256": _sha256(vendored_bytes[source_path]),
                "approved_modifications": APPROVED_MODIFICATIONS[source_path],
            }
            for source_path in VENDORED_FILES
        },
    }


def _load_manifest(root: Path) -> dict:
    try:
        manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _safe_error("vendor manifest is missing or invalid") from exc
    if not isinstance(manifest, dict):
        raise _safe_error("vendor manifest is invalid")
    return manifest


def _current_manifest_files() -> dict:
    try:
        manifest = _load_manifest(VENDOR_ROOT)
    except VendorVerificationError:
        return {}
    files = manifest.get("files")
    return files if isinstance(files, dict) else {}


MANIFEST_FILES: Final = _current_manifest_files()


def verify_vendor(root: Path = VENDOR_ROOT) -> dict[str, str]:
    """Verify local vendor bytes without network access."""
    manifest = _load_manifest(root)
    if manifest.get("repository") != SOURCE_REPOSITORY or manifest.get("commit") != SOURCE_COMMIT:
        raise _safe_error("vendor source identity mismatch")
    if manifest.get("license") != "MIT":
        raise _safe_error("vendor license identity mismatch")

    records = manifest.get("files")
    if not isinstance(records, dict) or set(records) != set(VENDORED_FILES):
        raise _safe_error("vendor manifest file allowlist mismatch")

    allowed_names = {*VENDORED_FILES.values(), MANIFEST_NAME}
    try:
        actual_names = {path.name for path in root.iterdir() if path.is_file()}
    except OSError as exc:
        raise _safe_error("vendor directory is unavailable") from exc
    unexpected = actual_names - allowed_names
    missing = allowed_names - actual_names
    if unexpected:
        raise _safe_error(f"unexpected vendored file: {sorted(unexpected)[0]}")
    if missing:
        raise _safe_error(f"missing vendored file: {sorted(missing)[0]}")

    verified: dict[str, str] = {}
    for source_path, destination in VENDORED_FILES.items():
        record = records.get(source_path)
        if not isinstance(record, dict):
            raise _safe_error(f"invalid manifest record: {source_path}")
        if record.get("destination") != destination:
            raise _safe_error(f"destination mismatch: {source_path}")
        if record.get("source_blob_sha1") != SOURCE_BLOBS[source_path]:
            raise _safe_error(f"source blob mismatch: {source_path}")
        if record.get("approved_modifications") != APPROVED_MODIFICATIONS[source_path]:
            raise _safe_error(f"approved diff mismatch: {source_path}")
        try:
            digest = _sha256((root / destination).read_bytes())
        except OSError as exc:
            raise _safe_error(f"missing vendored file: {destination}") from exc
        if digest != record.get("vendored_sha256"):
            raise _safe_error(f"vendored digest mismatch: {destination}")
        expected_digest = EXPECTED_VENDORED_SHA256.get(destination)
        if expected_digest and digest != expected_digest:
            raise _safe_error(f"reviewed digest mismatch: {destination}")
        verified[destination] = digest
    return verified


def _download(source_path: str) -> bytes:
    url = (
        "https://raw.githubusercontent.com/shiyu-coder/Kronos/"
        f"{SOURCE_COMMIT}/{source_path}"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "AthenaQuant-Kronos-Review/1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()
    except OSError as exc:
        raise _safe_error(f"source fetch failed: {source_path}") from exc


def stage_sync(destination: Path | None = None) -> Path:
    if destination is not None:
        destination = Path(destination)
        if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
            raise _safe_error("stage target must be an empty review directory")
        parent = destination.parent
    else:
        parent = BACKEND_ROOT
    parent.mkdir(parents=True, exist_ok=True)

    temporary = Path(tempfile.mkdtemp(prefix=".kronos-review-", dir=parent))
    try:
        source_bytes: dict[str, bytes] = {}
        vendored_bytes: dict[str, bytes] = {}
        for source_path, expected_blob in SOURCE_BLOBS.items():
            downloaded = _download(source_path)
            if _git_blob_sha1(downloaded) != expected_blob:
                raise _safe_error(f"source blob mismatch: {source_path}")
            source_bytes[source_path] = downloaded
            vendored_bytes[source_path] = _transform(source_path, downloaded)

        for source_path, destination_name in VENDORED_FILES.items():
            (temporary / destination_name).write_bytes(vendored_bytes[source_path])
        manifest = _manifest_for(source_bytes, vendored_bytes)
        (temporary / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        if destination is None:
            return temporary
        if destination.exists():
            destination.rmdir()
        os.replace(temporary, destination)
        return destination
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def replace_vendor(staged: Path, vendor_root: Path = VENDOR_ROOT) -> None:
    """Atomically promote a preverified review directory after explicit approval."""
    staged = Path(staged)
    verify_vendor(staged)
    vendor_root.parent.mkdir(parents=True, exist_ok=True)
    backup = vendor_root.with_name(f".{vendor_root.name}-backup")
    if backup.exists():
        raise _safe_error("vendor backup already exists")
    if vendor_root.exists():
        os.replace(vendor_root, backup)
    try:
        os.replace(staged, vendor_root)
    except Exception:
        if backup.exists() and not vendor_root.exists():
            os.replace(backup, vendor_root)
        raise
    else:
        shutil.rmtree(backup, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--verify-local", action="store_true")
    action.add_argument("--stage", type=Path, metavar="REVIEW_DIR")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="promote the explicitly staged, verified directory into app/vendor/kronos",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.replace and args.stage is None:
        return 2
    if args.verify_local:
        verify_vendor()
        print("Pinned Kronos vendor verification passed.")
        return 0
    if args.stage is not None:
        staged = stage_sync(args.stage)
        if args.replace:
            replace_vendor(staged, VENDOR_ROOT)
        print("Pinned Kronos source synchronization completed.")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
