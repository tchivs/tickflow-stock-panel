"""Parent-side freezer for authorized governed Forecast inputs."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol

import numpy as np
import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from app.forecast.calendar import GovernedTradingCalendar
from app.optional_artifacts import (
    ArtifactDescriptor as ManagedDescriptor,
    ManagedArtifactError,
    ManagedImmutableArtifactStore,
)


_REQUIRED_COLUMNS = {
    "instrument_id",
    "symbol",
    "asset_type",
    "frequency",
    "session_id",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "adjustment_policy",
    "adjustment_revision",
    "source_revision",
}
_FEATURES = ("open", "high", "low", "close", "volume")
_SCHEMA_VERSION = "forecast-input-v1"
_CALENDAR_ID = "cn-a-v1"
_DEFAULT_LOOKBACK = 64


class ForecastRequest(BaseModel):
    """The browser selects only an existing object, horizon, and catalog identity."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    instrument_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    horizon: Literal[5, 20, 60]
    catalog_id: str = Field(min_length=1, max_length=128, pattern=r"^kronos-[a-z]+$")


class GovernedForecastRepository(Protocol):
    def resolve_instrument(self, *, principal: str, instrument_id: str) -> Mapping[str, object]: ...

    def get_daily(self, *, symbol: str, as_of: str) -> pl.DataFrame: ...


@dataclass(frozen=True, slots=True)
class ForecastInputDescriptor:
    artifact_id: str
    schema_version: str
    byte_size: int
    checksum_sha256: str
    managed_path: str
    metadata_json: str
    _managed: ManagedDescriptor

    def public(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "schema_version": self.schema_version,
            "byte_size": self.byte_size,
            "checksum_sha256": self.checksum_sha256,
        }


@dataclass(frozen=True, slots=True)
class FrozenForecastInput:
    instrument_id: str
    symbol: str
    catalog_id: str
    horizon: int
    as_of_session_id: str
    lookback: int
    adjustment_policy: str
    adjustment_revision: str
    calendar_revision: str
    historical_session_ids: tuple[str, ...]
    future_session_ids: tuple[str, ...]
    feature_schema: list[str]
    input_fingerprint: str
    descriptor: ForecastInputDescriptor


class ForecastInputFreezer:
    """Authorizes, validates, fingerprints, and atomically freezes one daily series."""

    def __init__(
        self,
        *,
        repository: GovernedForecastRepository,
        calendar: GovernedTradingCalendar,
        artifact_root: Path,
    ) -> None:
        self._repository = repository
        self._calendar = calendar
        self._store = ManagedImmutableArtifactStore(Path(artifact_root))

    def freeze(
        self,
        *,
        request: ForecastRequest,
        principal: str,
        as_of_session_id: str,
        lookback: int = _DEFAULT_LOOKBACK,
        max_context: int = 512,
    ) -> FrozenForecastInput:
        if not isinstance(request, ForecastRequest):
            raise ValueError("Forecast request is invalid")
        if not isinstance(principal, str) or not principal:
            raise LookupError("instrument not found")
        if not isinstance(lookback, int) or lookback <= 0:
            raise ValueError("lookback must be positive")
        if not isinstance(max_context, int) or lookback > max_context:
            raise ValueError("lookback exceeds approved model context")

        instrument = self._repository.resolve_instrument(
            principal=principal, instrument_id=request.instrument_id
        )
        instrument_id = _mapping_text(instrument, "instrument_id")
        symbol = _mapping_text(instrument, "symbol")
        if instrument_id != request.instrument_id:
            raise LookupError("instrument not found")
        if instrument.get("market") != "CN-A" or instrument.get("asset_type") != "stock":
            raise ValueError("Forecast input must be one persisted CN-A stock")
        if getattr(self._repository, "frequency", "daily") != "daily":
            raise ValueError("Forecast input must use governed daily data")

        frame = self._repository.get_daily(
            symbol=symbol, as_of=_session_id_to_date(as_of_session_id)
        )
        validated, feature_schema, adjustment_policy, adjustment_revision, source_revision = (
            _validate_daily_frame(
                frame,
                instrument_id=instrument_id,
                symbol=symbol,
                as_of_session_id=as_of_session_id,
            )
        )
        if validated.height < lookback:
            raise ValueError("insufficient governed lookback coverage")
        historical = validated.tail(lookback)
        if historical["session_id"][-1] != as_of_session_id:
            raise ValueError("as-of session is absent from governed daily coverage")

        future = self._calendar.future_sessions(
            calendar_id=_CALENDAR_ID,
            after_session_id=as_of_session_id,
            count=request.horizon,
        )
        calendar_revision = self._calendar.revision(_CALENDAR_ID)
        historical_ids = tuple(str(value) for value in historical["session_id"].to_list())
        future_ids = tuple(session.session_id for session in future)
        payload_frame = historical.select(["session_id", "trade_date", *feature_schema])

        fingerprint_payload: dict[str, object] = {
            "schema_version": _SCHEMA_VERSION,
            "instrument_id": instrument_id,
            "symbol": symbol,
            "market": "CN-A",
            "asset_type": "stock",
            "frequency": "daily",
            "catalog_id": request.catalog_id,
            "horizon": request.horizon,
            "as_of_session_id": as_of_session_id,
            "lookback": lookback,
            "feature_schema": feature_schema,
            "adjustment_policy": adjustment_policy,
            "adjustment_revision": adjustment_revision,
            "source_revision": source_revision,
            "calendar_id": _CALENDAR_ID,
            "calendar_revision": calendar_revision,
            "historical_session_ids": list(historical_ids),
            "future_session_ids": list(future_ids),
        }
        canonical_payload = _canonical_json(fingerprint_payload)
        input_fingerprint = sha256(canonical_payload).hexdigest()
        managed = self._store.create_parquet(
            payload_frame,
            schema_version=_SCHEMA_VERSION,
            scope={
                "input_fingerprint": input_fingerprint,
                "fingerprint_payload": fingerprint_payload,
            },
        )
        metadata_json = _canonical_json(
            {"fingerprint_payload": fingerprint_payload}
        ).decode("utf-8")
        descriptor = ForecastInputDescriptor(
            artifact_id=managed.artifact_id,
            schema_version=managed.schema_version,
            byte_size=managed.byte_size,
            checksum_sha256=managed.checksum_sha256,
            managed_path=str(self._store.root / managed.relative_path),
            metadata_json=metadata_json,
            _managed=managed,
        )
        return FrozenForecastInput(
            instrument_id=instrument_id,
            symbol=symbol,
            catalog_id=request.catalog_id,
            horizon=request.horizon,
            as_of_session_id=as_of_session_id,
            lookback=lookback,
            adjustment_policy=adjustment_policy,
            adjustment_revision=adjustment_revision,
            calendar_revision=calendar_revision,
            historical_session_ids=historical_ids,
            future_session_ids=future_ids,
            feature_schema=feature_schema,
            input_fingerprint=input_fingerprint,
            descriptor=descriptor,
        )

    def load(self, descriptor: ForecastInputDescriptor) -> pl.DataFrame:
        if not isinstance(descriptor, ForecastInputDescriptor):
            raise ValueError("Forecast input descriptor is invalid")
        try:
            return self._store.load_parquet(descriptor._managed)
        except ManagedArtifactError as error:
            raise ValueError("Forecast input checksum verification failed") from error


def _validate_daily_frame(
    frame: object,
    *,
    instrument_id: str,
    symbol: str,
    as_of_session_id: str,
) -> tuple[pl.DataFrame, list[str], str, str, str]:
    if not isinstance(frame, pl.DataFrame):
        raise ValueError("governed daily input is invalid")
    missing = sorted(_REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(f"governed daily input is missing required column {missing[0]}")
    if frame.is_empty():
        raise ValueError("governed daily input has insufficient coverage")
    if frame["session_id"].n_unique() != frame.height or frame["trade_date"].n_unique() != frame.height:
        raise ValueError("governed daily input contains duplicate sessions")
    dates = frame["trade_date"].to_list()
    if dates != sorted(dates):
        raise ValueError("governed daily input must be sorted")
    if any(str(value) > as_of_session_id for value in frame["session_id"].to_list()):
        raise ValueError("governed daily input crosses the as-of boundary")

    for field, expected in (
        ("instrument_id", instrument_id),
        ("symbol", symbol),
        ("asset_type", "stock"),
        ("frequency", "daily"),
    ):
        values = frame[field].unique().to_list()
        if values != [expected]:
            raise ValueError(f"governed daily {field} scope is invalid")

    required_values = frame.select([*_FEATURES]).to_numpy()
    if not np.isfinite(required_values).all():
        raise ValueError("governed daily OHLCV values must be finite")
    feature_schema = list(_FEATURES)
    if "amount" in frame.columns:
        non_null_amount = frame["amount"].drop_nulls().to_numpy()
        if not np.isfinite(non_null_amount).all():
            raise ValueError("governed daily amount values must be finite")
        feature_schema.append("amount")

    adjustment_policy = _single_text(frame, "adjustment_policy")
    adjustment_revision = _single_text(frame, "adjustment_revision")
    source_revision = _single_text(frame, "source_revision")
    if adjustment_policy != "raw-unadjusted":
        raise ValueError("Forecast adjustment policy is not governed")
    return frame, feature_schema, adjustment_policy, adjustment_revision, source_revision


def _single_text(frame: pl.DataFrame, field: str) -> str:
    values = frame[field].unique().to_list()
    if len(values) != 1 or not isinstance(values[0], str) or not values[0]:
        raise ValueError(f"governed daily {field} is invalid")
    return values[0]


def _mapping_text(value: Mapping[str, object], field: str) -> str:
    candidate = value.get(field)
    if not isinstance(candidate, str) or not candidate:
        raise LookupError("instrument not found")
    return candidate


def _session_id_to_date(session_id: str) -> str:
    if (
        not isinstance(session_id, str)
        or not session_id.startswith("CNA-")
        or len(session_id) != 12
        or not session_id[4:].isdigit()
    ):
        raise ValueError("as-of session identity is invalid")
    value = session_id[4:]
    return f"{value[:4]}-{value[4:6]}-{value[6:]}"


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("Forecast input provenance is not canonical JSON") from error
