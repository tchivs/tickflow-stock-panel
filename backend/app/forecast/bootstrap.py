"""Operator-controlled production assembly for local Forecast inference."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import polars as pl

from app.forecast.artifacts import ForecastArtifactStore
from app.forecast.calendar import GovernedTradingCalendar
from app.forecast.catalog import ApprovedCheckpointCatalog
from app.forecast.kronos_adapter import PinnedLocalKronosRunner, derive_quantiles

_APPROVED_MINI = {
    "source_repository": "https://github.com/shiyu-coder/Kronos",
    "source_revision": "67b630e67f6a18c9e9be918d9b4337c960db1e9a",
    "model_repo": "NeoQuasar/Kronos-mini",
    "model_revision": "f4e68697d9d5aed55cef5c96aabc3376bcad9f81",
    "model_config_sha256": "70daca2cb11e3a979dd6b8ac12ee08e2aace877acf28f5b8dfb4fe5609736201",
    "model_weight_sha256": "a7d5f37e2e9fbd9891f7d7d4f72574512dd1f704fee14223e0a8cd0fbf54197c",
    "tokenizer_repo": "NeoQuasar/Kronos-Tokenizer-2k",
    "tokenizer_revision": "26966d0035065a0cae0ebad7af8ece35bc1fb51c",
    "tokenizer_config_sha256": "0b30a443affb03e05a876a083857de9164f899feb7b4d261da02c485c9a3e3b6",
    "tokenizer_weight_sha256": "b97ec46b3b72160509e289183eaf7bdf5f0dac5bb9b49522f6d46638a99a8717",
    "pairing": "mini:2k",
    "max_context": 2048,
    "weight_format": "safetensors",
    "trust_remote_code": False,
    "local_files_only": True,
}
APPROVED_FORECAST_PROFILES: Mapping[str, Mapping[str, object]] = {
    "kronos-mini": _APPROVED_MINI,
}


@dataclass(frozen=True, slots=True)
class LocalKronosForecastWorker:
    """Run one verified local checkpoint and persist bounded immutable artifacts."""

    catalog: ApprovedCheckpointCatalog
    output_root: Path
    device: str

    def __call__(
        self,
        *,
        job: Mapping[str, object],
        context: Mapping[str, object],
        limits: Mapping[str, int],
    ) -> dict[str, object]:
        del limits
        handle = context.get("input_artifact_handle")
        if not isinstance(handle, Mapping) or handle.get("writable") is not False:
            raise RuntimeError("Forecast sealed input is unavailable")
        payload = handle.get("payload")
        checksum = handle.get("checksum_sha256")
        if (
            not isinstance(payload, bytes)
            or not isinstance(checksum, str)
            or sha256(payload).hexdigest() != checksum
        ):
            raise RuntimeError("Forecast sealed input integrity check failed")

        features = context.get("feature_schema")
        historical_sessions = context.get("historical_session_ids")
        future_sessions = context.get("future_session_ids")
        immutable = context.get("immutable_record")
        if (
            not isinstance(features, list)
            or not all(isinstance(value, str) and value for value in features)
            or not isinstance(historical_sessions, list)
            or not isinstance(future_sessions, list)
            or not isinstance(immutable, Mapping)
        ):
            raise RuntimeError("Forecast worker context is invalid")
        try:
            frame = pl.read_parquet(BytesIO(payload))
            history = frame.select(features).to_numpy()
        except (OSError, TypeError, ValueError, pl.exceptions.PolarsError) as error:
            raise RuntimeError("Forecast sealed input cannot be decoded") from error

        checkpoint = self.catalog.require_local(str(job.get("catalog_id")), device=self.device)
        paths = PinnedLocalKronosRunner(checkpoint=checkpoint, device=self.device)(
            history=history,
            historical_session_ids=tuple(str(value) for value in historical_sessions),
            future_session_ids=tuple(str(value) for value in future_sessions),
            seed=int(immutable["seed"]),
            T=float(immutable["temperature"]),
            top_k=int(immutable["top_k"]),
            top_p=float(immutable["top_p"]),
            sample_count=int(immutable["sample_count"]),
        )
        bundle = ForecastArtifactStore.at(self.output_root).persist(
            paths=paths,
            quantiles=derive_quantiles(paths),
            future_session_ids=tuple(str(value) for value in future_sessions),
            feature_names=tuple(features),
            scope={
                "forecast_id": str(job["id"]),
                "horizon": int(job["horizon"]),
                "input_fingerprint": str(job["input_fingerprint"]),
            },
        )
        return {"output_descriptor": bundle.capped_manifest(), "validation_warnings": []}


def build_production_forecast_components(
    *, checkpoint_root: Path, data_root: Path, device: str
) -> dict[str, object]:
    """Assemble Forecast only from a fully verified operator-owned local supply."""
    root = Path(checkpoint_root).resolve(strict=True)
    manifest_path = root / "checkpoints.json"
    calendar_path = root / "cn_a_sessions.parquet"
    catalog = ApprovedCheckpointCatalog.from_file(
        manifest_path=manifest_path,
        approved_root=root,
        approved_profiles=APPROVED_FORECAST_PROFILES,
    )
    calendar = GovernedTradingCalendar.from_parquet(calendar_path)
    output_root = Path(data_root) / "forecast-outputs"
    output_root.mkdir(parents=True, exist_ok=True)
    return {
        "catalog": catalog,
        "calendar": calendar,
        "worker": LocalKronosForecastWorker(
            catalog=catalog,
            output_root=output_root,
            device=device,
        ),
        "device": device,
        "catalog_entries": catalog.public_entries(),
        "output_root": output_root,
    }
