"""Immutable sampled-path and quantile artifacts for Forecast runs."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import numpy as np
import polars as pl

from app.optional_artifacts import ArtifactDescriptor, ManagedImmutableArtifactStore

_PATH_SCHEMA = "forecast-paths-v1"
_QUANTILE_SCHEMA = "forecast-quantiles-v1"
_QUANTILE_LABELS = ("P10", "P50", "P90")


@dataclass(frozen=True, slots=True)
class ForecastArtifactBundle:
    """Verified identities for the full path tensor and its derived quantiles."""

    paths: ArtifactDescriptor
    quantiles: ArtifactDescriptor
    path_shape: tuple[int, int, int]
    quantile_shape: tuple[int, int, int]
    warning_codes: tuple[str, ...]

    def capped_manifest(self) -> dict[str, object]:
        return {
            "paths_artifact": self.paths.as_dict(),
            "quantiles_artifact": self.quantiles.as_dict(),
            "path_shape": list(self.path_shape),
            "quantile_shape": list(self.quantile_shape),
            "sample_count": self.path_shape[0],
            "quantile_labels": list(_QUANTILE_LABELS),
            "warning_codes": list(self.warning_codes[:64]),
        }


_WARNING_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_PATH_COLUMNS = {"sample_index", "session_id", "feature", "value"}
_QUANTILE_RTOL = 1e-12
_QUANTILE_ATOL = 1e-12


class ForecastPathReader:
    """Verify one immutable path relation before returning complete sampled paths."""

    def __init__(self, root: Path) -> None:
        configured = Path(root)
        self.root = configured.resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("Forecast output root is not a directory")

    def read_page(
        self, *, record: Mapping[str, object], offset: int, limit: int
    ) -> tuple[list[dict[str, object]], int]:
        if (
            isinstance(offset, bool)
            or not isinstance(offset, int)
            or offset < 0
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 500
        ):
            raise ValueError("Forecast path page is invalid")
        descriptor = record.get("output_artifact_descriptor")
        if not isinstance(descriptor, Mapping):
            raise ValueError("Forecast output descriptor is unavailable")
        relative = descriptor.get("relative_path")
        if (
            not isinstance(relative, str)
            or not relative
            or relative in {".", ".."}
            or "\\" in relative
            or ":" in relative
            or Path(relative).is_absolute()
            or Path(relative).as_posix() != relative
            or any(part in {"", ".", ".."} for part in Path(relative).parts)
        ):
            raise ValueError("Forecast output descriptor path is invalid")
        unresolved = self.root / relative
        if unresolved.is_symlink():
            raise ValueError("Forecast output artifact is not a regular non-symlink file")
        try:
            candidate = unresolved.resolve(strict=True)
            candidate.relative_to(self.root)
        except (OSError, ValueError) as error:
            raise ValueError("Forecast output artifact escapes its managed root") from error
        if candidate == self.root or not candidate.is_file():
            raise ValueError("Forecast output artifact is not a regular file")

        expected_checksum = descriptor.get("checksum_sha256")
        expected_size = descriptor.get("byte_size")
        if (
            descriptor.get("schema_version") != _PATH_SCHEMA
            or not isinstance(expected_checksum, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_checksum) is None
            or isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size <= 0
        ):
            raise ValueError("Forecast output descriptor identity is invalid")
        payload = candidate.read_bytes()
        if len(payload) != expected_size or sha256(payload).hexdigest() != expected_checksum:
            raise ValueError("Forecast output artifact checksum or size mismatch")
        try:
            frame = pl.read_parquet(BytesIO(payload))
        except (pl.exceptions.PolarsError, OSError, TypeError, ValueError) as error:
            raise ValueError("Forecast path artifact cannot be decoded") from error
        return self._validated_page(
            frame=frame,
            descriptor=descriptor,
            record=record,
            offset=offset,
            limit=limit,
        )

    @staticmethod
    def _validated_page(
        *,
        frame: pl.DataFrame,
        descriptor: Mapping[str, object],
        record: Mapping[str, object],
        offset: int,
        limit: int,
    ) -> tuple[list[dict[str, object]], int]:
        columns = set(frame.columns)
        if not _PATH_COLUMNS.issubset(columns) or not columns.issubset(
            _PATH_COLUMNS | {"horizon_index"}
        ):
            raise ValueError("Forecast path relation schema is invalid")
        sample_count = descriptor.get("sample_count")
        horizon = descriptor.get("horizon")
        feature_count = descriptor.get("feature_count")
        if (
            sample_count != 32
            or record.get("sample_count") != 32
            or isinstance(horizon, bool)
            or not isinstance(horizon, int)
            or horizon != record.get("horizon")
            or isinstance(feature_count, bool)
            or not isinstance(feature_count, int)
            or feature_count <= 0
        ):
            raise ValueError("Forecast path descriptor shape is invalid")
        sessions = record.get("future_session_ids")
        if (
            not isinstance(sessions, list)
            or len(sessions) != horizon
            or len(set(sessions)) != horizon
            or not all(isinstance(item, str) and item for item in sessions)
        ):
            raise ValueError("Forecast path sessions are invalid")
        rows = frame.to_dicts()
        features = sorted(
            {row.get("feature") for row in rows if isinstance(row.get("feature"), str)}
        )
        if len(features) != feature_count or any(not feature for feature in features):
            raise ValueError("Forecast path features are invalid")
        expected_size = 32 * horizon * feature_count
        if len(rows) != expected_size:
            raise ValueError("Forecast path relation is incomplete")

        session_position = {session: index for index, session in enumerate(sessions)}
        feature_position = {feature: index for index, feature in enumerate(features)}
        relation: dict[tuple[int, str, str], float] = {}
        for row in rows:
            sample = row.get("sample_index")
            session = row.get("session_id")
            feature = row.get("feature")
            value = row.get("value")
            if (
                isinstance(sample, bool)
                or not isinstance(sample, int)
                or not 0 <= sample < 32
                or session not in session_position
                or feature not in feature_position
                or isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not np.isfinite(float(value))
            ):
                raise ValueError("Forecast path relation contains an out-of-range value")
            horizon_index = row.get("horizon_index")
            if horizon_index is not None and horizon_index != session_position[session]:
                raise ValueError("Forecast path relation has an inconsistent horizon index")
            identity = (sample, session, feature)
            if identity in relation:
                raise ValueError("Forecast path relation contains a duplicate identity")
            relation[identity] = float(value)
        expected = {
            (sample, session, feature)
            for sample in range(32)
            for session in sessions
            for feature in features
        }
        if relation.keys() != expected:
            raise ValueError("Forecast path relation is not a complete Cartesian relation")

        warnings = record.get("validation_warnings", [])
        if not isinstance(warnings, list) or any(
            not isinstance(code, str) or _WARNING_CODE.fullmatch(code) is None for code in warnings
        ):
            raise ValueError("Forecast path warning code is invalid")
        warning_code = warnings[0] if warnings else ""
        selected = range(offset, min(offset + limit, 32))
        page = [
            {
                "path_index": sample,
                "session_id": session,
                "feature": feature,
                "value": relation[(sample, session, feature)],
                "warning_code": warning_code,
            }
            for sample in selected
            for session in sessions
            for feature in features
        ]
        return page, 32


class ForecastArtifactStore:
    """Persists all validated paths before exposing derived quantiles."""

    def __init__(self, store: ManagedImmutableArtifactStore) -> None:
        self._store = store

    @classmethod
    def at(cls, root) -> ForecastArtifactStore:
        return cls(ManagedImmutableArtifactStore(root))

    def persist(
        self,
        *,
        paths: np.ndarray,
        quantiles: np.ndarray,
        future_session_ids: Sequence[str],
        feature_names: Sequence[str],
        scope: Mapping[str, object],
        warning_codes: Sequence[str] = (),
    ) -> ForecastArtifactBundle:
        path_values = np.asarray(paths, dtype=np.float64)
        supplied_quantiles = np.asarray(quantiles, dtype=np.float64)
        if path_values.ndim != 3 or path_values.shape[0] != 32:
            raise ValueError("Forecast paths must have shape [32,horizon,feature]")
        expected_quantile_shape = (3, path_values.shape[1], path_values.shape[2])
        if supplied_quantiles.shape != expected_quantile_shape:
            raise ValueError("Forecast quantiles have an invalid shape")
        if not np.isfinite(path_values).all() or not np.isfinite(supplied_quantiles).all():
            raise ValueError("Forecast artifacts must contain finite values")
        quantile_values = np.asarray(
            np.quantile(path_values, q=(0.10, 0.50, 0.90), axis=0), dtype=np.float64
        )
        if not np.allclose(
            supplied_quantiles,
            quantile_values,
            rtol=_QUANTILE_RTOL,
            atol=_QUANTILE_ATOL,
            equal_nan=False,
        ):
            raise ValueError("Forecast supplied quantiles diverge from the complete path tensor")
        sessions = tuple(future_session_ids)
        features = tuple(feature_names)
        if len(sessions) != path_values.shape[1] or len(set(sessions)) != len(sessions):
            raise ValueError("Forecast artifact sessions do not match the horizon")
        if len(features) != path_values.shape[2] or len(set(features)) != len(features):
            raise ValueError("Forecast artifact features do not match the tensor")

        path_frame = _paths_frame(path_values, sessions, features)
        paths_descriptor = self._store.create_parquet(
            path_frame,
            schema_version=_PATH_SCHEMA,
            scope={**dict(scope), "kind": "sampled_paths", "shape": list(path_values.shape)},
        )
        quantile_frame = _quantiles_frame(quantile_values, sessions, features)
        quantiles_descriptor = self._store.create_parquet(
            quantile_frame,
            schema_version=_QUANTILE_SCHEMA,
            scope={
                **dict(scope),
                "kind": "path_axis_quantiles",
                "source_paths_sha256": paths_descriptor.checksum_sha256,
                "shape": list(quantile_values.shape),
            },
        )
        return ForecastArtifactBundle(
            paths=paths_descriptor,
            quantiles=quantiles_descriptor,
            path_shape=path_values.shape,
            quantile_shape=quantile_values.shape,
            warning_codes=tuple(str(code) for code in warning_codes[:64]),
        )

    def load_paths(self, bundle: ForecastArtifactBundle) -> pl.DataFrame:
        if not isinstance(bundle, ForecastArtifactBundle):
            raise ValueError("Forecast artifact bundle is invalid")
        return self._store.load_parquet(bundle.paths)

    def load_quantiles(self, bundle: ForecastArtifactBundle) -> pl.DataFrame:
        if not isinstance(bundle, ForecastArtifactBundle):
            raise ValueError("Forecast artifact bundle is invalid")
        return self._store.load_parquet(bundle.quantiles)


def _paths_frame(
    values: np.ndarray,
    sessions: tuple[str, ...],
    features: tuple[str, ...],
) -> pl.DataFrame:
    samples, horizon, feature_count = values.shape
    return pl.DataFrame(
        {
            "sample_index": np.repeat(np.arange(samples, dtype=np.int16), horizon * feature_count),
            "horizon_index": np.tile(
                np.repeat(np.arange(horizon, dtype=np.int16), feature_count), samples
            ),
            "session_id": np.tile(np.repeat(np.asarray(sessions), feature_count), samples),
            "feature": np.tile(np.asarray(features), samples * horizon),
            "value": values.reshape(-1),
        }
    )


def _quantiles_frame(
    values: np.ndarray,
    sessions: tuple[str, ...],
    features: tuple[str, ...],
) -> pl.DataFrame:
    quantile_count, horizon, feature_count = values.shape
    return pl.DataFrame(
        {
            "quantile": np.repeat(np.asarray(_QUANTILE_LABELS), horizon * feature_count),
            "horizon_index": np.tile(
                np.repeat(np.arange(horizon, dtype=np.int16), feature_count), quantile_count
            ),
            "session_id": np.tile(np.repeat(np.asarray(sessions), feature_count), quantile_count),
            "feature": np.tile(np.asarray(features), quantile_count * horizon),
            "value": values.reshape(-1),
        }
    )
