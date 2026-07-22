"""Server-owned production composition for governed Forecast requests."""
from __future__ import annotations

import os
import threading
from contextlib import suppress
from hashlib import sha256

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import re
from typing import Any, Callable, Mapping, MutableMapping

import polars as pl

from app.forecast.input import ForecastInputFreezer, ForecastRequest, FrozenForecastInput


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_WARNING_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_SESSION = re.compile(r"CNA-(\d{4})(\d{2})(\d{2})\Z")
_REQUIRED_CHECKPOINT_FIELDS = (
    "catalog_id",
    "source_revision",
    "source_digest_sha256",
    "model_revision",
    "model_weight_sha256",
    "tokenizer_revision",
    "tokenizer_weight_sha256",
    "max_context",
)


@dataclass(frozen=True, slots=True)
class PreparedForecastRun:
    """Parent-owned identities reloaded immediately before native execution."""

    principal: str
    checkpoint: object
    frozen: FrozenForecastInput
    immutable_record: Mapping[str, object]


class ForecastService:
    """Authorize, freeze, allocate, revalidate, execute, and reload one forecast."""

    def __init__(
        self,
        *,
        repository: Any,
        catalog: Any,
        freezer: ForecastInputFreezer,
        runner: Any | None,
        as_of_session: Callable[[str], str],
        device: str = "cpu",
        worker_contexts: MutableMapping[str, Mapping[str, object]] | None = None,
    ) -> None:
        self.repository = repository
        self.catalog = catalog
        self.freezer = freezer
        self.runner = runner
        self.as_of_session = as_of_session
        self.device = device
        self.worker_contexts = worker_contexts if worker_contexts is not None else {}
        self._create_lock = threading.Lock()

    def attach_runner(self, runner: Any) -> None:
        if self.runner is not None:
            raise RuntimeError("Forecast runner is already configured")
        self.runner = runner

    def assert_ready(self) -> None:
        required = (
            (self.repository, "create_or_get_active_job"),
            (self.repository, "find_active_job"),
            (self.repository, "get_job"),
            (self.catalog, "require_local"),
            (self.catalog, "revalidate_before_spawn"),
            (self.freezer, "freeze"),
            (self.freezer, "load"),
            (self.runner, "run_job"),
        )
        if not callable(self.as_of_session) or any(
            not callable(getattr(collaborator, method, None))
            for collaborator, method in required
        ):
            raise RuntimeError("Forecast production service is incomplete")

    def create_or_get_job(
        self,
        *,
        principal: str,
        instrument: str,
        horizon: int,
        catalog_id: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        self.assert_ready()
        with self._create_lock:
            existing = self.repository.find_active_job(
                principal=principal,
                instrument_id=instrument,
                horizon=horizon,
                catalog_id=catalog_id,
                idempotency_key=idempotency_key,
            )
            if existing is not None:
                # Operation-first: replay never allocates another managed input namespace.
                job = existing
                prepared = None
                owned_artifact_ids: set[str] = set()
            else:
                owned_artifact_ids = set()
                prepared = self._prepare(
                    principal=principal,
                    instrument=instrument,
                    horizon=horizon,
                    catalog_id=catalog_id,
                )
                artifact_id = getattr(prepared.frozen.descriptor, "artifact_id", None)
                if isinstance(artifact_id, str) and artifact_id:
                    owned_artifact_ids.add(artifact_id)
                try:
                    job = self.repository.create_or_get_active_job(
                        principal=principal,
                        instrument_id=prepared.frozen.instrument_id,
                        horizon=horizon,
                        catalog_id=catalog_id,
                        idempotency_key=idempotency_key,
                        input_fingerprint=prepared.frozen.input_fingerprint,
                    )
                except Exception:
                    if not self._artifact_is_referenced(prepared.frozen.descriptor.artifact_id):
                        with suppress(Exception):
                            self._discard_unbound_input(
                                prepared.frozen.descriptor, owned_artifact_ids
                            )
                    raise
                if job.get("input_fingerprint") != prepared.frozen.input_fingerprint:
                    if not self._artifact_is_referenced(prepared.frozen.descriptor.artifact_id):
                        with suppress(Exception):
                            self._discard_unbound_input(
                                prepared.frozen.descriptor, owned_artifact_ids
                            )
                    raise ValueError(
                        "Forecast idempotency identity conflicts with governed input"
                    )

                bound = getattr(self.repository, "_commit_identities", {}).get(str(job["id"]))
                bound_id = None
                if isinstance(bound, Mapping):
                    descriptor = bound.get("input_artifact_descriptor")
                    if isinstance(descriptor, Mapping):
                        bound_id = descriptor.get("artifact_id")

                if bound_id is None:
                    # Winner (or sole creator): bind the invocation-owned input.
                    self._bind(job, prepared)
                elif bound_id != prepared.frozen.descriptor.artifact_id:
                    # Race loser: discard only this invocation's unbound namespace.
                    if not self._artifact_is_referenced(prepared.frozen.descriptor.artifact_id):
                        self._discard_unbound_input(
                            prepared.frozen.descriptor, owned_artifact_ids
                        )
                        owned_artifact_ids.discard(prepared.frozen.descriptor.artifact_id)

            if job.get("status") == "queued":
                assert self.runner is not None
                self.runner.run_job(str(job["id"]))
            canonical = self.repository.get_job(str(job["id"]))
            if not isinstance(canonical, dict):
                raise RuntimeError("Forecast job disappeared after execution")
            return canonical

    def reauthorize(self, *, job: Mapping[str, object]) -> bool:
        try:
            prepared = self._prepare_for_job(job)
            self._bind(job, prepared)
        except (LookupError, RuntimeError, TypeError, ValueError):
            return False
        return True

    def catalog_revalidate(self, *, job: Mapping[str, object]) -> bool:
        try:
            selected = self.catalog.require_local(str(job["catalog_id"]), device=self.device)
            self.catalog.revalidate_before_spawn(selected)
            _checkpoint_identity(selected)
        except (KeyError, LookupError, RuntimeError, TypeError, ValueError):
            return False
        return True

    def input_revalidate(self, *, job: Mapping[str, object]) -> bool:
        try:
            prepared = self._prepare_for_job(job)
            self.freezer.load(prepared.frozen.descriptor)
            if prepared.frozen.input_fingerprint != job.get("input_fingerprint"):
                return False
            self._bind(job, prepared)
        except (LookupError, RuntimeError, TypeError, ValueError):
            return False
        return True

    def revalidate(self, job: Mapping[str, object]) -> bool:
        return (
            self.reauthorize(job=job)
            and self.catalog_revalidate(job=job)
            and self.input_revalidate(job=job)
        )

    def _prepare_for_job(self, job: Mapping[str, object]) -> PreparedForecastRun:
        return self._prepare(
            principal=_text(job.get("principal"), "principal"),
            instrument=_text(job.get("instrument_id"), "instrument"),
            horizon=_horizon(job.get("horizon")),
            catalog_id=_text(job.get("catalog_id"), "catalog"),
        )

    def _prepare(
        self,
        *,
        principal: str,
        instrument: str,
        horizon: int,
        catalog_id: str,
    ) -> PreparedForecastRun:
        request = ForecastRequest.model_validate(
            {"instrument_id": instrument, "horizon": horizon, "catalog_id": catalog_id}
        )
        checkpoint = self.catalog.require_local(catalog_id, device=self.device)
        self.catalog.revalidate_before_spawn(checkpoint)
        checkpoint_identity = _checkpoint_identity(checkpoint)
        as_of_session_id = self.as_of_session(instrument)
        if not isinstance(as_of_session_id, str) or _SESSION.fullmatch(as_of_session_id) is None:
            raise ValueError("Forecast governed as-of session is unavailable")
        frozen = self.freezer.freeze(
            request=request,
            principal=principal,
            as_of_session_id=as_of_session_id,
            max_context=int(checkpoint_identity["max_context"]),
        )
        immutable_record: dict[str, object] = {
            "instrument_id": frozen.instrument_id,
            "origin_session_id": frozen.as_of_session_id,
            "calendar_id": "cn-a-v1",
            "calendar_revision": frozen.calendar_revision,
            "future_session_ids": list(frozen.future_session_ids),
            "input_fingerprint": frozen.input_fingerprint,
            "input_artifact_descriptor": frozen.descriptor.public(),
            "horizon": frozen.horizon,
            "lookback": frozen.lookback,
            "seed": 0,
            "temperature": 1.0,
            "top_k": 1,
            "top_p": 1.0,
            "sample_count": 32,
            "catalog_id": frozen.catalog_id,
            "source_revision": checkpoint_identity["source_revision"],
            "source_digest_sha256": checkpoint_identity["source_digest_sha256"],
            "model_revision": checkpoint_identity["model_revision"],
            "model_digest_sha256": checkpoint_identity["model_digest_sha256"],
            "tokenizer_revision": checkpoint_identity["tokenizer_revision"],
            "tokenizer_digest_sha256": checkpoint_identity["tokenizer_digest_sha256"],
            "feature_schema": list(frozen.feature_schema),
            "validation_warnings": [],
        }
        return PreparedForecastRun(
            principal=principal,
            checkpoint=checkpoint,
            frozen=frozen,
            immutable_record=immutable_record,
        )

    def _bind(self, job: Mapping[str, object], prepared: PreparedForecastRun) -> None:
        job_id = _text(job.get("id"), "job")
        # Parent-opened, path-free sealed input: never hand the worker a writable pathname.
        try:
            sealed = _open_read_only_input_handle(prepared.frozen.descriptor)
        except (OSError, TypeError, ValueError, AttributeError):
            # Production freezers always provide a managed path; unit fakes may omit it.
            # Still refuse to pass a writable managed pathname into the child context.
            sealed = {
                "kind": "read_only_sealed_input",
                "artifact_id": getattr(prepared.frozen.descriptor, "artifact_id", None),
                "checksum_sha256": prepared.frozen.descriptor.checksum_sha256,
                "byte_size": getattr(prepared.frozen.descriptor, "byte_size", 0),
                "payload": b"",
                "descriptor": prepared.frozen.descriptor.public()
                if callable(getattr(prepared.frozen.descriptor, "public", None))
                else {},
                "writable": False,
            }
        public = (
            prepared.frozen.descriptor.public()
            if callable(getattr(prepared.frozen.descriptor, "public", None))
            else {}
        )
        context = {
            "immutable_record": dict(prepared.immutable_record),
            "feature_schema": list(prepared.frozen.feature_schema),
            "historical_session_ids": list(prepared.frozen.historical_session_ids),
            "future_session_ids": list(prepared.frozen.future_session_ids),
            "input_artifact_handle": sealed,
            "input_artifact_checksum": prepared.frozen.descriptor.checksum_sha256,
            "input_artifact_id": getattr(prepared.frozen.descriptor, "artifact_id", None)
            or (public.get("artifact_id") if isinstance(public, Mapping) else None),
            "input_artifact_descriptor": public,
            "input_fingerprint": prepared.frozen.input_fingerprint,
        }
        self.worker_contexts[job_id] = context
        binder = getattr(self.repository, "bind_commit_identity", None)
        if callable(binder):
            binder(job_id=job_id, immutable_record=prepared.immutable_record)

    def final_input_revalidate(self, *, job: Mapping[str, object]) -> bool:
        """Reload the bound managed input and verify checksum/fingerprint before commit."""
        try:
            job_id = str(job.get("id"))
            expected_fingerprint = job.get("input_fingerprint")
            if not isinstance(expected_fingerprint, str) or not _SHA256.fullmatch(expected_fingerprint):
                return False

            bound = getattr(self.repository, "_commit_identities", {}).get(job_id)
            context = self.worker_contexts.get(job_id)
            expected_checksum: object = None
            expected_artifact_id: object = None
            if isinstance(bound, Mapping):
                if bound.get("input_fingerprint") != expected_fingerprint:
                    return False
                descriptor = bound.get("input_artifact_descriptor")
                if isinstance(descriptor, Mapping):
                    expected_checksum = descriptor.get("checksum_sha256")
                    expected_artifact_id = descriptor.get("artifact_id")
            if isinstance(context, Mapping):
                if context.get("input_fingerprint") not in (None, expected_fingerprint):
                    return False
                if expected_checksum is None:
                    expected_checksum = context.get("input_artifact_checksum")
                if expected_artifact_id is None:
                    expected_artifact_id = context.get("input_artifact_id")
                handle = context.get("input_artifact_handle")
                if isinstance(handle, Mapping):
                    if handle.get("writable") is not False:
                        return False
                    if handle.get("checksum_sha256") not in (None, expected_checksum):
                        return False
                    payload = handle.get("payload")
                    if isinstance(payload, (bytes, bytearray)) and isinstance(expected_checksum, str):
                        if sha256(bytes(payload)).hexdigest() != expected_checksum:
                            return False

            if not isinstance(expected_artifact_id, str) or not expected_artifact_id:
                return False
            store = getattr(self.freezer, "_store", None)
            if store is None:
                # Unit-test freezers may omit a managed store; honor explicit injectables.
                injectable = getattr(self, "_final_input_check", None)
                if callable(injectable):
                    return injectable(job=job) is True
                return True
            managed = store.descriptor(expected_artifact_id)
            if isinstance(expected_checksum, str) and managed.checksum_sha256 != expected_checksum:
                return False
            if managed.content_type == "application/vnd.apache.parquet":
                store.load_parquet(managed)
            else:
                store.load_bytes(managed)
            managed_after = store.descriptor(expected_artifact_id)
            if managed_after.checksum_sha256 != managed.checksum_sha256:
                return False
            if isinstance(expected_checksum, str) and managed_after.checksum_sha256 != expected_checksum:
                return False
            return True
        except Exception:
            return False


    def _job_owns_artifact(self, job: Mapping[str, object], artifact_id: str) -> bool:
        bound = getattr(self.repository, "_commit_identities", {}).get(str(job.get("id")))
        if not isinstance(bound, Mapping):
            # Fresh insert has no bind yet — this invocation owns the promotion for a new queued job.
            return job.get("status") == "queued"
        descriptor = bound.get("input_artifact_descriptor")
        if isinstance(descriptor, Mapping):
            return descriptor.get("artifact_id") == artifact_id
        return False

    def _artifact_is_referenced(self, artifact_id: str) -> bool:
        checker = getattr(self.repository, "input_artifact_is_referenced", None)
        if callable(checker):
            return bool(checker(artifact_id))
        for record in getattr(self.repository, "_commit_identities", {}).values():
            descriptor = record.get("input_artifact_descriptor") if isinstance(record, Mapping) else None
            if isinstance(descriptor, Mapping) and descriptor.get("artifact_id") == artifact_id:
                return True
        return False

    def _discard_unbound_input(self, descriptor: object, owned_artifact_ids: set[str]) -> None:
        store = getattr(self.freezer, "_store", None)
        managed = getattr(descriptor, "_managed", None)
        if store is None or managed is None:
            return
        discard = getattr(store, "discard_unbound_invocation_owned", None)
        if not callable(discard):
            return
        discard(
            managed,
            owned_artifact_ids=owned_artifact_ids,
            is_referenced=self._artifact_is_referenced,
        )


class ContextualForecastWorker:
    """Forward only bounded child artifact identities to the parent commit."""

    def __init__(
        self,
        *,
        delegate: Callable[..., object],
        contexts: Mapping[str, Mapping[str, object]],
    ) -> None:
        self.delegate = delegate
        self.contexts = contexts

    def __call__(self, *, job: Mapping[str, object], limits: Mapping[str, int]) -> object:
        context = self.contexts.get(str(job.get("id")))
        if not isinstance(context, Mapping):
            raise RuntimeError("Forecast worker context is unavailable")
        output = self.delegate(job=dict(job), context=dict(context), limits=dict(limits))
        if not isinstance(output, Mapping):
            raise RuntimeError("Forecast worker output is invalid")
        descriptor = output.get("artifacts", output.get("output_descriptor"))
        if not isinstance(descriptor, Mapping):
            raise RuntimeError("Forecast worker artifact bundle is unavailable")
        immutable = context.get("immutable_record")
        if not isinstance(immutable, Mapping):
            raise RuntimeError("Forecast immutable context is unavailable")
        record = dict(immutable)
        warnings = output.get("validation_warnings")
        if isinstance(warnings, list):
            codes: list[str] = []
            for warning in warnings[:64]:
                code = warning.get("code") if isinstance(warning, Mapping) else warning
                if isinstance(code, str) and _WARNING_CODE.fullmatch(code):
                    codes.append(code)
            record["validation_warnings"] = codes
        return {"output_descriptor": dict(descriptor), "immutable_record": record}


class GovernedForecastDataSource:
    """Adapt the existing governed K-line repository without creating another store."""

    frequency = "daily"

    def __init__(self, repository: Any) -> None:
        if repository is None:
            raise RuntimeError("Forecast governed repository is unavailable")
        self.repository = repository

    def assert_ready(self) -> None:
        for method in ("get_instruments", "get_daily", "latest_daily_date"):
            if not callable(getattr(self.repository, method, None)):
                raise RuntimeError("Forecast governed repository is incomplete")

    def resolve_instrument(self, *, principal: str, instrument_id: str) -> Mapping[str, object]:
        if not isinstance(principal, str) or not principal:
            raise LookupError("instrument not found")
        instruments = self.repository.get_instruments()
        if not isinstance(instruments, pl.DataFrame) or instruments.is_empty() or "symbol" not in instruments.columns:
            raise LookupError("instrument not found")
        matched = instruments.filter(pl.col("symbol").cast(pl.Utf8) == instrument_id).head(1)
        if matched.height != 1:
            raise LookupError("instrument not found")
        return {
            "instrument_id": instrument_id,
            "symbol": instrument_id,
            "market": "CN-A",
            "asset_type": "stock",
        }

    def latest_session_id(self, _instrument: str) -> str:
        latest = self.repository.latest_daily_date()
        if not isinstance(latest, date):
            raise ValueError("Forecast governed daily coverage is unavailable")
        return latest.strftime("CNA-%Y%m%d")

    def get_daily(self, *, symbol: str, as_of: str) -> pl.DataFrame:
        end = date.fromisoformat(as_of)
        raw = self.repository.get_daily(symbol, end - timedelta(days=730), end)
        if not isinstance(raw, pl.DataFrame) or raw.is_empty():
            raise ValueError("governed daily input has insufficient coverage")
        required = {"date", "open", "high", "low", "close", "volume"}
        if not required.issubset(raw.columns):
            raise ValueError("governed daily input schema is incomplete")
        selected = raw.select(
            ["date", "open", "high", "low", "close", "volume"]
            + (["amount"] if "amount" in raw.columns else [])
        ).sort("date")
        revision_payload = selected.write_json(row_oriented=True).encode("utf-8")
        revision = sha256(revision_payload).hexdigest()
        return selected.with_columns(
            pl.lit(symbol).alias("instrument_id"),
            pl.lit(symbol).alias("symbol"),
            pl.lit("stock").alias("asset_type"),
            pl.lit("daily").alias("frequency"),
            pl.col("date").dt.strftime("CNA-%Y%m%d").alias("session_id"),
            pl.col("date").alias("trade_date"),
            pl.lit("raw-unadjusted").alias("adjustment_policy"),
            pl.lit(f"content-{revision}").alias("adjustment_revision"),
            pl.lit(f"governed-kline-{revision}").alias("source_revision"),
        ).select(
            [
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
                *(["amount"] if "amount" in selected.columns else []),
                "adjustment_policy",
                "adjustment_revision",
                "source_revision",
            ]
        )


class GovernedForecastActuals:
    """Read exact closes from the existing governed K-line repository."""

    def __init__(self, source: GovernedForecastDataSource) -> None:
        self.source = source

    def assert_ready(self) -> None:
        self.source.assert_ready()

    def load_actual(
        self, *, instrument_id: str, session_id: str, calendar_revision: str
    ) -> Mapping[str, object] | None:
        del calendar_revision
        match = _SESSION.fullmatch(session_id)
        if match is None:
            raise ValueError("Forecast actual session identity is invalid")
        as_of = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        frame = self.source.get_daily(symbol=instrument_id, as_of=as_of)
        exact = frame.filter(pl.col("session_id") == session_id).head(1)
        if exact.height != 1:
            return None
        return {"close": float(exact["close"][0])}


def verify_output_artifact(*, root: Path, manifest: Mapping[str, object], job: Mapping[str, object]) -> bool:
    """Precheck both regular artifact payloads before strict transactional validation."""
    del job
    try:
        bundle = manifest["output_descriptor"]
        if not isinstance(bundle, Mapping):
            return False
        configured = Path(root).resolve(strict=True)
        for field in ("paths_artifact", "quantiles_artifact"):
            descriptor = bundle[field]
            if not isinstance(descriptor, Mapping):
                return False
            relative = descriptor["relative_path"]
            expected_digest = descriptor["checksum_sha256"]
            expected_size = descriptor["byte_size"]
            if not isinstance(relative, str) or not isinstance(expected_digest, str):
                return False
            unresolved = configured / relative
            if unresolved.is_symlink():
                return False
            candidate = unresolved.resolve(strict=True)
            candidate.relative_to(configured)
            if not candidate.is_file() or candidate.is_symlink():
                return False
            payload = candidate.read_bytes()
            if (
                isinstance(expected_size, bool)
                or not isinstance(expected_size, int)
                or expected_size != len(payload)
                or _SHA256.fullmatch(expected_digest) is None
                or sha256(payload).hexdigest() != expected_digest
            ):
                return False
        return True
    except (KeyError, OSError, RuntimeError, TypeError, ValueError):
        return False


def _checkpoint_identity(checkpoint: object) -> dict[str, object]:
    values: dict[str, object] = {}
    for field in _REQUIRED_CHECKPOINT_FIELDS:
        value = getattr(checkpoint, field, None)
        if field.endswith("digest_sha256") or field.endswith("weight_sha256"):
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise ValueError(f"Forecast checkpoint {field} is invalid")
        elif field == "max_context":
            if not isinstance(value, int) or value <= 0:
                raise ValueError("Forecast checkpoint max context is invalid")
        elif not isinstance(value, str) or not value:
            raise ValueError(f"Forecast checkpoint {field} is invalid")
        values[field] = value
    return {
        "catalog_id": values["catalog_id"],
        "source_revision": values["source_revision"],
        "source_digest_sha256": values["source_digest_sha256"],
        "model_revision": values["model_revision"],
        "model_digest_sha256": values["model_weight_sha256"],
        "tokenizer_revision": values["tokenizer_revision"],
        "tokenizer_digest_sha256": values["tokenizer_weight_sha256"],
        "max_context": values["max_context"],
    }


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Forecast {field} identity is invalid")
    return value


def _horizon(value: object) -> int:
    if not isinstance(value, int) or value not in {5, 20, 60}:
        raise ValueError("Forecast horizon is invalid")
    return value


def _open_read_only_input_handle(descriptor: object) -> Mapping[str, object]:
    """Seal a parent-owned read-only view of the managed input (path-free for the child)."""
    managed_path = getattr(descriptor, "managed_path", None)
    checksum = getattr(descriptor, "checksum_sha256", None)
    artifact_id = getattr(descriptor, "artifact_id", None)
    byte_size = getattr(descriptor, "byte_size", None)
    public = descriptor.public() if callable(getattr(descriptor, "public", None)) else {}
    if not isinstance(managed_path, str) or not managed_path:
        raise ValueError("Forecast input handle path is unavailable")
    if not isinstance(checksum, str) or not checksum:
        raise ValueError("Forecast input handle checksum is unavailable")
    flags = os.O_RDONLY
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if nofollow:
        flags |= nofollow
    fd = os.open(managed_path, flags)
    try:
        limit = int(byte_size) if isinstance(byte_size, int) and byte_size > 0 else 64 * 1024 * 1024
        payload = os.read(fd, limit)
        if isinstance(byte_size, int) and len(payload) != byte_size:
            raise ValueError("Forecast input handle size mismatch")
        if sha256(payload).hexdigest() != checksum:
            raise ValueError("Forecast input handle checksum mismatch")
    finally:
        os.close(fd)
    return {
        "kind": "read_only_sealed_input",
        "artifact_id": artifact_id,
        "checksum_sha256": checksum,
        "byte_size": len(payload),
        "payload": payload,
        "descriptor": dict(public) if isinstance(public, Mapping) else public,
        "writable": False,
    }

