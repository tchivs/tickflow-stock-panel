"""Explicit operator command for the approved Kronos-mini local supply."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path

import polars as pl

from app.forecast.bootstrap import APPROVED_FORECAST_PROFILES

_CALENDAR_END = date(2027, 12, 31)
_CFETS_2027_PRESET_SOURCE = "https://www.chinamoney.com.cn/chinese/bbjjr/20251219/3254570.html"
_CFETS_2027_CLOSURES = (
    (date(2027, 1, 1), date(2027, 1, 1)),
    (date(2027, 2, 5), date(2027, 2, 12)),
    (date(2027, 4, 5), date(2027, 4, 5)),
    (date(2027, 5, 1), date(2027, 5, 5)),
    (date(2027, 6, 9), date(2027, 6, 9)),
    (date(2027, 9, 15), date(2027, 9, 15)),
    (date(2027, 10, 1), date(2027, 10, 7)),
)


def _cfets_2027_sessions() -> tuple[date, ...]:
    """Return provisional 2027 weekdays published for CFETS cross-year settlement."""
    closures = {
        start + timedelta(days=offset)
        for start, end in _CFETS_2027_CLOSURES
        for offset in range((end - start).days + 1)
    }
    current = date(2027, 1, 1)
    sessions: list[date] = []
    while current <= _CALENDAR_END:
        if current.weekday() < 5 and current not in closures:
            sessions.append(current)
        current += timedelta(days=1)
    return tuple(sessions)


def _digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _copy_verified(source: str, destination: Path, expected: str) -> None:
    candidate = Path(source).resolve(strict=True)
    if candidate.is_symlink() or not candidate.is_file():
        raise RuntimeError("downloaded Forecast asset is not a regular file")
    temporary = destination.with_name(f".{destination.name}.tmp")
    with candidate.open("rb") as reader, temporary.open("xb") as writer:
        shutil.copyfileobj(reader, writer, length=1024 * 1024)
        writer.flush()
        os.fsync(writer.fileno())
    if _digest(temporary) != expected:
        temporary.unlink(missing_ok=True)
        raise RuntimeError("downloaded Forecast asset digest does not match approval")
    temporary.chmod(0o600)
    temporary.replace(destination)


def _provision_repo(
    *, repo_id: str, revision: str, destination: Path, config_digest: str, weight_digest: str
) -> None:
    from huggingface_hub import hf_hub_download

    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    if destination.is_symlink():
        raise RuntimeError("Forecast asset directory must not be a symlink")
    assets = (
        ("config.json", config_digest),
        ("model.safetensors", weight_digest),
    )
    for filename, expected in assets:
        target = destination / filename
        if target.is_file() and not target.is_symlink() and _digest(target) == expected:
            continue
        cached = hf_hub_download(repo_id=repo_id, filename=filename, revision=revision)
        target.unlink(missing_ok=True)
        _copy_verified(cached, target, expected)


def _write_calendar(root: Path) -> None:
    import exchange_calendars as xcals

    calendar = xcals.get_calendar("XSHG", start="2010-01-01", end="2026-12-31")
    dates = [value.date() for value in calendar.sessions]
    dates.extend(_cfets_2027_sessions())
    if not dates or dates[-1] != _CALENDAR_END or len(dates) != len(set(dates)):
        raise RuntimeError("approved CN-A calendar coverage is invalid")
    revision_payload = json.dumps(
        {
            "provider": "exchange_calendars:XSHG",
            "version": xcals.__version__,
            "provisional_2027_provider": "CFETS",
            "provisional_2027_source": _CFETS_2027_PRESET_SOURCE,
            "sessions": [str(value) for value in dates],
        },
        separators=(",", ":"),
    ).encode("utf-8")
    revision = f"xshg-cfets-preset-2027-{sha256(revision_payload).hexdigest()}"
    frame = pl.DataFrame(
        {
            "calendar_id": ["cn-a-v1"] * len(dates),
            "calendar_revision": [revision] * len(dates),
            "market": ["CN-A"] * len(dates),
            "session_id": [f"CNA-{value:%Y%m%d}" for value in dates],
            "trade_date": dates,
            "is_open": [True] * len(dates),
            "sequence": list(range(len(dates))),
        }
    )
    target = root / "cn_a_sessions.parquet"
    temporary = root / ".cn_a_sessions.parquet.tmp"
    frame.write_parquet(temporary)
    temporary.chmod(0o600)
    temporary.replace(target)


def provision(root: Path) -> None:
    configured = Path(root)
    configured.mkdir(mode=0o700, parents=True, exist_ok=True)
    if configured.is_symlink():
        raise RuntimeError("Forecast checkpoint root must not be a symlink")
    configured = configured.resolve(strict=True)
    approved = dict(APPROVED_FORECAST_PROFILES["kronos-mini"])
    _provision_repo(
        repo_id=str(approved["model_repo"]),
        revision=str(approved["model_revision"]),
        destination=configured / "Kronos-mini",
        config_digest=str(approved["model_config_sha256"]),
        weight_digest=str(approved["model_weight_sha256"]),
    )
    _provision_repo(
        repo_id=str(approved["tokenizer_repo"]),
        revision=str(approved["tokenizer_revision"]),
        destination=configured / "Kronos-Tokenizer-2k",
        config_digest=str(approved["tokenizer_config_sha256"]),
        weight_digest=str(approved["tokenizer_weight_sha256"]),
    )
    _write_calendar(configured)
    entry = {
        "catalog_id": "kronos-mini",
        **approved,
        "model_config_file": "config.json",
        "model_weight_file": "model.safetensors",
        "local_model_dir": "Kronos-mini",
        "tokenizer_config_file": "config.json",
        "tokenizer_weight_file": "model.safetensors",
        "local_tokenizer_dir": "Kronos-Tokenizer-2k",
        "allowed_devices": ["cpu", "cuda:0"],
        "explicit_provisioning_only": False,
    }
    manifest = {"schema_version": "forecast-catalog-v1", "entries": [entry]}
    temporary = configured / ".checkpoints.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(configured / "checkpoints.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision approved local Kronos-mini assets")
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    provision(args.root)


if __name__ == "__main__":
    main()
