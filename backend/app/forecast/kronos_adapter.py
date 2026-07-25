"""Pinned local-only Kronos pre-mean adapter and bounded numerical contracts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
import importlib
import importlib.util
from pathlib import Path
import random
import re
import sys
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from app.forecast.artifacts import ForecastArtifactBundle, ForecastArtifactStore


_SAMPLE_COUNT = 32
_QUANTILES = (0.10, 0.50, 0.90)
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class SamplingConfig:
    lookback: int
    seed: int
    temperature: float
    top_k: int
    top_p: float
    sample_count: int = _SAMPLE_COUNT

    def __post_init__(self) -> None:
        if not isinstance(self.lookback, int) or self.lookback <= 0:
            raise ValueError("lookback must be positive")
        if not isinstance(self.seed, int) or self.seed < 0 or self.seed > 2**32 - 1:
            raise ValueError("sampling seed is invalid")
        if not np.isfinite(self.temperature) or self.temperature <= 0 or self.temperature > 10:
            raise ValueError("sampling temperature is invalid")
        if not isinstance(self.top_k, int) or self.top_k < 0 or self.top_k > 65536:
            raise ValueError("sampling top_k is invalid")
        if not np.isfinite(self.top_p) or not 0 < self.top_p <= 1:
            raise ValueError("sampling top_p is invalid")
        if self.sample_count != _SAMPLE_COUNT:
            raise ValueError("Forecast sampling requires exactly 32 paths")

    def frozen(self) -> dict[str, int | float]:
        return {
            "lookback": self.lookback,
            "seed": self.seed,
            "T": self.temperature,
            "top_k": self.top_k,
            "top_p": self.top_p,
            "sample_count": self.sample_count,
        }


@dataclass(frozen=True, slots=True)
class NormalizationStatistics:
    mean: np.ndarray
    scale: np.ndarray


@dataclass(frozen=True, slots=True)
class ForecastValidationWarning:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class LocalModelPair:
    model: object
    tokenizer: object


@dataclass(frozen=True, slots=True)
class KronosForecastResult:
    paths: np.ndarray
    quantiles: np.ndarray
    future_session_ids: tuple[str, ...]
    feature_names: tuple[str, ...]
    sampling: dict[str, int | float]
    validation_warnings: tuple[ForecastValidationWarning, ...]
    artifacts: ForecastArtifactBundle | None = None

    def capped_manifest(self) -> dict[str, object]:
        manifest: dict[str, object] = {
            "sample_count": int(self.paths.shape[0]),
            "horizon": int(self.paths.shape[1]),
            "feature_names": list(self.feature_names),
            "future_session_ids": list(self.future_session_ids),
            "quantile_labels": ["P10", "P50", "P90"],
            "sampling": dict(self.sampling),
            "validation_warnings": [
                {"code": warning.code, "message": warning.message}
                for warning in self.validation_warnings[:64]
            ],
        }
        if self.artifacts is not None:
            manifest["artifacts"] = self.artifacts.capped_manifest()
        return manifest


class KronosPreMeanAdapter:
    """Validates the exact pre-mean sample axis and derives fixed quantiles."""

    def __init__(
        self,
        *,
        inference: Callable[..., object],
        feature_names: Sequence[str],
        artifact_store: ForecastArtifactStore | None = None,
    ) -> None:
        features = tuple(feature_names)
        if not features or len(set(features)) != len(features):
            raise ValueError("Forecast feature schema is invalid")
        self._inference = inference
        self._features = features
        self._artifact_store = artifact_store

    def forecast(
        self,
        *,
        history: np.ndarray,
        future_session_ids: Sequence[str],
        config: SamplingConfig,
        historical_session_ids: Sequence[str] | None = None,
        artifact_scope: Mapping[str, object] | None = None,
    ) -> KronosForecastResult:
        history_values = np.asarray(history, dtype=np.float64)
        if history_values.shape != (config.lookback, len(self._features)):
            raise ValueError("Forecast history shape does not match lookback and features")
        if not np.isfinite(history_values).all():
            raise ValueError("Forecast history must contain finite values")
        sessions = tuple(str(value) for value in future_session_ids)
        if not sessions or len(set(sessions)) != len(sessions):
            raise ValueError("Forecast future session identities are invalid")
        history_sessions = (
            None
            if historical_session_ids is None
            else tuple(str(value) for value in historical_session_ids)
        )
        if history_sessions is not None and len(history_sessions) != config.lookback:
            raise ValueError("Forecast historical sessions do not match lookback")

        raw_paths = self._inference(
            history=history_values,
            historical_session_ids=history_sessions,
            future_session_ids=sessions,
            lookback=config.lookback,
            seed=config.seed,
            T=config.temperature,
            top_k=config.top_k,
            top_p=config.top_p,
            sample_count=config.sample_count,
            feature_names=self._features,
        )
        paths = validate_pre_mean_paths(
            raw_paths,
            horizon=len(sessions),
            feature_count=len(self._features),
            sample_count=config.sample_count,
        )
        quantiles = derive_quantiles(paths)
        warnings = tuple(_validation_warnings(paths, quantiles, self._features))
        artifacts = None
        if self._artifact_store is not None:
            if artifact_scope is None:
                raise ValueError("Forecast artifact scope is required")
            artifacts = self._artifact_store.persist(
                paths=paths,
                quantiles=quantiles,
                future_session_ids=sessions,
                feature_names=self._features,
                scope=artifact_scope,
                warning_codes=tuple(warning.code for warning in warnings),
            )
        return KronosForecastResult(
            paths=paths,
            quantiles=quantiles,
            future_session_ids=sessions,
            feature_names=self._features,
            sampling=config.frozen(),
            validation_warnings=warnings,
            artifacts=artifacts,
        )


def validate_pre_mean_paths(
    paths: object,
    *,
    horizon: int,
    feature_count: int,
    sample_count: int = _SAMPLE_COUNT,
) -> np.ndarray:
    if sample_count != _SAMPLE_COUNT:
        raise ValueError("Forecast output requires exactly 32 samples")
    values = np.asarray(paths)
    expected = (sample_count, horizon, feature_count)
    if values.ndim != 3 or values.shape != expected:
        raise ValueError(f"Forecast sample path shape must be {expected}")
    if not np.issubdtype(values.dtype, np.number):
        raise ValueError("Forecast sample paths must be numeric")
    values = np.asarray(values, dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("Forecast sample paths must contain finite values")
    values.setflags(write=False)
    return values


def derive_quantiles(paths: np.ndarray) -> np.ndarray:
    values = np.asarray(paths, dtype=np.float64)
    if values.ndim != 3 or values.shape[0] != _SAMPLE_COUNT:
        raise ValueError("Forecast quantiles require the complete sample path axis")
    if not np.isfinite(values).all():
        raise ValueError("Forecast quantiles require finite paths")
    quantiles = np.quantile(values, q=_QUANTILES, axis=0)
    quantiles.setflags(write=False)
    return quantiles


def normalize_history(history: np.ndarray) -> tuple[np.ndarray, NormalizationStatistics]:
    values = np.asarray(history, dtype=np.float64)
    if values.ndim != 2 or values.shape[0] == 0 or values.shape[1] == 0:
        raise ValueError("Forecast history must be a non-empty matrix")
    if not np.isfinite(values).all():
        raise ValueError("Forecast history must contain finite values")
    mean = values.mean(axis=0)
    scale = values.std(axis=0) + 1e-5
    normalized = (values - mean) / scale
    return normalized, NormalizationStatistics(mean=mean, scale=scale)


def inverse_normalize_paths(
    paths: np.ndarray, statistics: NormalizationStatistics
) -> np.ndarray:
    values = np.asarray(paths, dtype=np.float64)
    if values.ndim != 3 or values.shape[-1] != statistics.mean.shape[0]:
        raise ValueError("normalized path shape does not match statistics")
    restored = values * statistics.scale + statistics.mean
    if not np.isfinite(restored).all():
        raise ValueError("inverse-normalized paths must be finite")
    return restored


def load_approved_local_pair(
    *,
    model_dir: Path,
    tokenizer_dir: Path,
    loader: Callable[..., object],
    verified: bool,
) -> LocalModelPair:
    """Invoke an injected loader only for a catalog-verified pair in offline mode."""
    if verified is not True:
        raise ValueError("local checkpoint pair has not passed catalog verification")
    model_path = _local_path(model_dir, "model")
    tokenizer_path = _local_path(tokenizer_dir, "tokenizer")
    model = loader(model_path, local_files_only=True, trust_remote_code=False)
    tokenizer = loader(tokenizer_path, local_files_only=True, trust_remote_code=False)
    return LocalModelPair(model=model, tokenizer=tokenizer)


class PinnedLocalKronosRunner:
    """Lazy worker-only runner for one already-verified local checkpoint pair."""

    def __init__(self, *, checkpoint: Any, device: str) -> None:
        if getattr(checkpoint, "local_files_only", None) is not True:
            raise ValueError("Kronos runner requires a local-only checkpoint")
        if getattr(checkpoint, "trust_remote_code", None) is not False:
            raise ValueError("Kronos runner forbids remote code")
        if device not in tuple(getattr(checkpoint, "allowed_devices", ())):
            raise ValueError("Kronos runner device is not approved")
        self._checkpoint = checkpoint
        self._device = device
        self._loaded: LocalModelPair | None = None
        self._sample_from_logits: Callable[..., Any] | None = None

    def __call__(self, **kwargs: object) -> np.ndarray:
        history = np.asarray(kwargs["history"], dtype=np.float64)
        history_sessions = kwargs.get("historical_session_ids")
        future_sessions = kwargs.get("future_session_ids")
        if history_sessions is None or not isinstance(future_sessions, tuple):
            raise ValueError("governed historical and future sessions are required")
        history_stamps = _session_stamps(tuple(str(value) for value in history_sessions))
        future_stamps = _session_stamps(tuple(str(value) for value in future_sessions))
        normalized, statistics = normalize_history(history)
        pair = self._pair()
        if self._sample_from_logits is None:
            raise ValueError("verified Kronos sampler is unavailable")

        import torch

        seed = int(kwargs["seed"])
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        x = torch.from_numpy(normalized.astype(np.float32)[None, ...]).to(self._device)
        x_stamp = torch.from_numpy(history_stamps[None, ...]).to(self._device)
        y_stamp = torch.from_numpy(future_stamps[None, ...]).to(self._device)
        paths = _pinned_pre_mean_inference(
            tokenizer=pair.tokenizer,
            model=pair.model,
            x=x,
            x_stamp=x_stamp,
            y_stamp=y_stamp,
            max_context=int(self._checkpoint.max_context),
            pred_len=len(future_sessions),
            T=float(kwargs["T"]),
            top_k=int(kwargs["top_k"]),
            top_p=float(kwargs["top_p"]),
            sample_count=int(kwargs["sample_count"]),
            sample_from_logits=self._sample_from_logits,
        )
        return inverse_normalize_paths(paths, statistics)

    def _pair(self) -> LocalModelPair:
        if self._loaded is None:
            from app.forecast.catalog import verify_resolved_checkpoint

            verify_resolved_checkpoint(self._checkpoint)
            package, sampler = _load_verified_kronos_package(Path(self._checkpoint.source_dir))
            Kronos = getattr(package, "Kronos", None)
            KronosTokenizer = getattr(package, "KronosTokenizer", None)
            if not callable(Kronos) or not callable(KronosTokenizer):
                raise ValueError("verified Kronos package exports are invalid")

            model = Kronos.from_pretrained(
                str(self._checkpoint.model_dir), local_files_only=True
            )
            tokenizer = KronosTokenizer.from_pretrained(
                str(self._checkpoint.tokenizer_dir), local_files_only=True
            )
            self._loaded = LocalModelPair(model=model, tokenizer=tokenizer)
            self._sample_from_logits = sampler
        return self._loaded


def _pinned_pre_mean_inference(
    *, tokenizer: object, model: object, x: Any, x_stamp: Any, y_stamp: Any,
    max_context: int, pred_len: int, T: float, top_k: int, top_p: float,
    sample_count: int, sample_from_logits: Callable[..., Any],
) -> np.ndarray:
    """Pinned 67b630e seam: return decoded samples before upstream axis-1 mean."""
    import torch
    if sample_count != _SAMPLE_COUNT:
        raise ValueError("Kronos pre-mean inference requires exactly 32 samples")
    with torch.no_grad():
        x = torch.clip(x, -5, 5)
        device = x.device
        x = x.unsqueeze(1).repeat(1, sample_count, 1, 1).reshape(-1, x.size(1), x.size(2)).to(device)
        x_stamp = x_stamp.unsqueeze(1).repeat(1, sample_count, 1, 1).reshape(-1, x_stamp.size(1), x_stamp.size(2)).to(device)
        y_stamp = y_stamp.unsqueeze(1).repeat(1, sample_count, 1, 1).reshape(-1, y_stamp.size(1), y_stamp.size(2)).to(device)
        x_token = tokenizer.encode(x, half=True)
        initial_seq_len = x.size(1)
        batch_size = x_token[0].size(0)
        total_seq_len = initial_seq_len + pred_len
        full_stamp = torch.cat([x_stamp, y_stamp], dim=1)
        generated_pre = x_token[0].new_empty(batch_size, pred_len)
        generated_post = x_token[1].new_empty(batch_size, pred_len)
        pre_buffer = x_token[0].new_zeros(batch_size, max_context)
        post_buffer = x_token[1].new_zeros(batch_size, max_context)
        buffer_len = min(initial_seq_len, max_context)
        if buffer_len > 0:
            start = max(0, initial_seq_len - max_context)
            pre_buffer[:, :buffer_len] = x_token[0][:, start : start + buffer_len]
            post_buffer[:, :buffer_len] = x_token[1][:, start : start + buffer_len]
        for index in range(pred_len):
            current = initial_seq_len + index
            window = min(current, max_context)
            input_tokens = (
                [pre_buffer[:, :window], post_buffer[:, :window]]
                if current <= max_context
                else [pre_buffer, post_buffer]
            )
            context_start = max(0, current - max_context)
            current_stamp = full_stamp[:, context_start:current, :].contiguous()
            s1_logits, context = model.decode_s1(input_tokens[0], input_tokens[1], current_stamp)
            sample_pre = sample_from_logits(
                s1_logits[:, -1, :], temperature=T, top_k=top_k,
                top_p=top_p, sample_logits=True,
            )
            s2_logits = model.decode_s2(context, sample_pre)
            sample_post = sample_from_logits(
                s2_logits[:, -1, :], temperature=T, top_k=top_k,
                top_p=top_p, sample_logits=True,
            )
            generated_pre[:, index] = sample_pre.squeeze(-1)
            generated_post[:, index] = sample_post.squeeze(-1)
            if current < max_context:
                pre_buffer[:, current] = sample_pre.squeeze(-1)
                post_buffer[:, current] = sample_post.squeeze(-1)
            else:
                pre_buffer.copy_(torch.roll(pre_buffer, shifts=-1, dims=1))
                post_buffer.copy_(torch.roll(post_buffer, shifts=-1, dims=1))
                pre_buffer[:, -1] = sample_pre.squeeze(-1)
                post_buffer[:, -1] = sample_post.squeeze(-1)
        full_pre = torch.cat([x_token[0], generated_pre], dim=1)
        full_post = torch.cat([x_token[1], generated_post], dim=1)
        start = max(0, total_seq_len - max_context)
        decoded = tokenizer.decode(
            [
                full_pre[:, start:total_seq_len].contiguous(),
                full_post[:, start:total_seq_len].contiguous(),
            ],
            half=True,
        )
        decoded = decoded.reshape(-1, sample_count, decoded.size(1), decoded.size(2))
        paths = decoded[:, :, -pred_len:, :].cpu().numpy()
    if paths.shape[0] != 1:
        raise ValueError("single-series Kronos inference returned a batch")
    return np.asarray(paths[0], dtype=np.float64)


def _load_verified_kronos_package(source_dir: Path) -> tuple[object, Callable[..., Any]]:
    """Load Kronos only from the catalog-verified source directory."""
    source = source_dir.resolve(strict=True)
    package_name = f"_athena_kronos_{sha256(str(source).encode()).hexdigest()[:16]}"
    for banned in ("app.vendor.kronos", "kronos"):
        preloaded = sys.modules.get(banned)
        if preloaded is None:
            continue
        module_file = getattr(preloaded, "__file__", None)
        if not isinstance(module_file, str):
            raise ValueError("preloaded Kronos module origin is unavailable")
        try:
            Path(module_file).resolve(strict=True).relative_to(source)
        except (OSError, ValueError) as error:
            raise ValueError("import shadow rejected for preloaded Kronos module") from error

    package = sys.modules.get(package_name)
    if package is not None:
        module_file = getattr(package, "__file__", None)
        if not isinstance(module_file, str):
            sys.modules.pop(package_name, None)
            package = None
        else:
            try:
                Path(module_file).resolve(strict=True).relative_to(source)
            except (OSError, ValueError):
                sys.modules.pop(package_name, None)
                package = None

    if package is None:
        init_path = source / "__init__.py"
        if init_path.is_symlink() or not init_path.is_file():
            raise ValueError("verified Kronos package cannot be loaded")
        # Reject sys.path entries that would shadow by same basename outside source.
        for entry in list(sys.path):
            if not entry:
                continue
            try:
                candidate = Path(entry).resolve()
            except OSError:
                continue
            if candidate == source:
                continue
            shadowed = candidate / "kronos.py"
            if shadowed.is_file():
                # Presence alone is fine; loading must not use it.
                pass
        spec = importlib.util.spec_from_file_location(
            package_name,
            init_path,
            submodule_search_locations=[str(source)],
        )
        if spec is None or spec.loader is None:
            raise ValueError("verified Kronos package cannot be loaded")
        package = importlib.util.module_from_spec(spec)
        package.__path__ = [str(source)]  # type: ignore[attr-defined]
        sys.modules[package_name] = package
        try:
            spec.loader.exec_module(package)
        except BaseException:
            sys.modules.pop(package_name, None)
            raise

    # Force submodule load from the verified directory, never from sys.path.
    kronos_path = source / "kronos.py"
    if kronos_path.is_symlink() or not kronos_path.is_file():
        raise ValueError("verified Kronos module is missing")
    module_name = f"{package_name}.kronos"
    existing_module = sys.modules.get(module_name)
    if existing_module is not None:
        module_file = getattr(existing_module, "__file__", None)
        if not isinstance(module_file, str):
            sys.modules.pop(module_name, None)
            existing_module = None
        else:
            try:
                Path(module_file).resolve(strict=True).relative_to(source)
            except (OSError, ValueError):
                sys.modules.pop(module_name, None)
                existing_module = None
    if existing_module is None:
        spec = importlib.util.spec_from_file_location(
            module_name,
            kronos_path,
            submodule_search_locations=[str(source)],
        )
        if spec is None or spec.loader is None:
            raise ValueError("verified Kronos module cannot be loaded")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
    else:
        module = existing_module

    for name, loaded in tuple(sys.modules.items()):
        if name != package_name and not name.startswith(f"{package_name}."):
            continue
        module_file = getattr(loaded, "__file__", None)
        if not isinstance(module_file, str):
            raise ValueError("verified Kronos module origin is unavailable")
        try:
            Path(module_file).resolve(strict=True).relative_to(source)
        except (OSError, ValueError) as error:
            raise ValueError("verified Kronos module origin escaped source directory") from error
    sampler = getattr(module, "sample_from_logits", None)
    if not callable(sampler):
        raise ValueError("verified Kronos sampler is unavailable")
    return package, sampler




def _validation_warnings(
    paths: np.ndarray, quantiles: np.ndarray, features: tuple[str, ...]
) -> list[ForecastValidationWarning]:
    warnings: list[ForecastValidationWarning] = []
    indices = {name: index for index, name in enumerate(features)}
    if {"open", "high", "low", "close"}.issubset(indices):
        open_values = paths[:, :, indices["open"]]
        high_values = paths[:, :, indices["high"]]
        low_values = paths[:, :, indices["low"]]
        close_values = paths[:, :, indices["close"]]
        if np.any(high_values < np.maximum.reduce([open_values, low_values, close_values])) or np.any(
            low_values > np.minimum.reduce([open_values, high_values, close_values])
        ):
            warnings.append(ForecastValidationWarning("ohlc_inconsistent", "sampled OHLC values are economically inconsistent"))
    if "volume" in indices and np.any(paths[:, :, indices["volume"]] < 0):
        warnings.append(ForecastValidationWarning("negative_volume", "sampled volume contains negative values"))
    if "amount" in indices and np.any(paths[:, :, indices["amount"]] < 0):
        warnings.append(ForecastValidationWarning("negative_amount", "sampled amount contains negative values"))
    if np.any(quantiles[0] > quantiles[1]) or np.any(quantiles[1] > quantiles[2]):
        warnings.append(ForecastValidationWarning("quantile_crossing", "derived quantiles cross without value mutation"))
    return warnings


def _local_path(path: Path, field: str) -> Path:
    candidate = Path(path)
    text = str(candidate)
    if text.startswith(("http://", "https://")):
        raise ValueError(f"{field} checkpoint path must be local")
    return candidate


def _session_stamps(session_ids: tuple[str, ...]) -> np.ndarray:
    rows: list[tuple[float, float, float, float, float]] = []
    for session_id in session_ids:
        if len(session_id) != 12 or not session_id.startswith("CNA-") or not session_id[4:].isdigit():
            raise ValueError("governed session identity is invalid")
        value = session_id[4:]
        session_date = date(int(value[:4]), int(value[4:6]), int(value[6:]))
        rows.append((0.0, 0.0, float(session_date.weekday()), float(session_date.day), float(session_date.month)))
    return np.asarray(rows, dtype=np.float32)


@dataclass(frozen=True, slots=True)
class ApprovedRegressionResult:
    paths: np.ndarray
    quantiles: np.ndarray
    provenance: dict[str, str]


@dataclass(frozen=True, slots=True)
class ApprovedLocalKronosRegression:
    """Opt-in offline smoke over exact human-approved local assets."""

    source_dir: Path
    source_revision: str
    model_dir: Path
    model_revision: str
    model_sha256: str
    tokenizer_dir: Path
    tokenizer_revision: str
    tokenizer_sha256: str
    device: str

    def run(self, *, seed: int, horizon: int, lookback: int, sample_count: int) -> ApprovedRegressionResult:
        for revision in (self.source_revision, self.model_revision, self.tokenizer_revision):
            if not _COMMIT.fullmatch(revision):
                raise ValueError("regression revision is not immutable")
        for digest in (self.model_sha256, self.tokenizer_sha256):
            if not _SHA256.fullmatch(digest):
                raise ValueError("regression digest is invalid")
        if _sha256_file(self.model_dir / "model.safetensors") != self.model_sha256 or _sha256_file(
            self.tokenizer_dir / "model.safetensors"
        ) != self.tokenizer_sha256:
            raise ValueError("regression checkpoint digest mismatch")
        from app.forecast.catalog import _verify_source

        source_manifest_sha256, source_file_digests = _verify_source(
            Path(self.source_dir), self.source_revision
        )
        checkpoint = SimpleNamespace(
            local_files_only=True,
            trust_remote_code=False,
            allowed_devices=(self.device,),
            model_dir=self.model_dir,
            tokenizer_dir=self.tokenizer_dir,
            max_context=max(lookback, 64),
            source_dir=Path(self.source_dir),
            source_revision=self.source_revision,
            source_manifest_sha256=source_manifest_sha256,
            source_file_digests=source_file_digests,
            model_config_sha256=_sha256_file(Path(self.model_dir) / "config.json"),
            model_weight_sha256=self.model_sha256,
            tokenizer_config_sha256=_sha256_file(Path(self.tokenizer_dir) / "config.json"),
            tokenizer_weight_sha256=self.tokenizer_sha256,
        )
        runner = PinnedLocalKronosRunner(checkpoint=checkpoint, device=self.device)
        end = date(2025, 4, 30)
        history_dates = tuple(end - timedelta(days=lookback - 1 - index) for index in range(lookback))
        future_dates = tuple(end + timedelta(days=index + 1) for index in range(horizon))
        history_ids = tuple(f"CNA-{value:%Y%m%d}" for value in history_dates)
        future_ids = tuple(f"CNA-{value:%Y%m%d}" for value in future_dates)
        history = np.arange(lookback * 6, dtype=np.float64).reshape(lookback, 6) + 1.0
        paths = runner(
            history=history,
            historical_session_ids=history_ids,
            future_session_ids=future_ids,
            seed=seed,
            T=1.0,
            top_k=0,
            top_p=0.9,
            sample_count=sample_count,
        )

        paths = validate_pre_mean_paths(paths, horizon=horizon, feature_count=6, sample_count=sample_count)
        return ApprovedRegressionResult(
            paths=paths,
            quantiles=derive_quantiles(paths),
            provenance={
                "source_revision": self.source_revision,
                "model_revision": self.model_revision,
                "model_sha256": self.model_sha256,
                "tokenizer_revision": self.tokenizer_revision,
                "tokenizer_sha256": self.tokenizer_sha256,
            },
        )


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
