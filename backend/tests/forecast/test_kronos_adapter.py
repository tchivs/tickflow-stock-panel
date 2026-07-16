"""RED contracts for the pinned pre-mean Kronos adapter and quantile axis."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "sample_paths.npy"
FEATURES = ("open", "high", "low", "close", "volume", "amount")


class FixedPreMeanInference:
    def __init__(self, paths: np.ndarray | None = None) -> None:
        self.paths = np.load(FIXTURE) if paths is None else paths
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs):
        self.calls.append(dict(kwargs))
        return self.paths.copy()


def _config(**overrides):
    from app.forecast.kronos_adapter import SamplingConfig
    payload = {
        "lookback": 64,
        "seed": 20250715,
        "temperature": 1.0,
        "top_k": 0,
        "top_p": 0.9,
        "sample_count": 32,
    }
    payload.update(overrides)
    return SamplingConfig(**payload)


def _adapter(paths: np.ndarray | None = None):
    from app.forecast.kronos_adapter import KronosPreMeanAdapter
    inference = FixedPreMeanInference(paths)
    return KronosPreMeanAdapter(inference=inference, feature_names=FEATURES), inference


def test_sample_fixture_is_exact_pre_mean_32_by_60_by_6_tensor():
    from app.forecast.kronos_adapter import validate_pre_mean_paths
    paths = np.load(FIXTURE)
    validated = validate_pre_mean_paths(paths, horizon=60, feature_count=6, sample_count=32)
    assert validated.shape == (32, 60, 6)
    assert validated.dtype == np.float64


def test_sampling_configuration_freezes_seed_temperature_topk_topp_and_count():
    adapter, inference = _adapter()
    result = adapter.forecast(history=np.ones((64, 6)), future_session_ids=[f"S{i:02}" for i in range(60)], config=_config())
    assert result.sampling == {
        "lookback": 64,
        "seed": 20250715,
        "T": 1.0,
        "top_k": 0,
        "top_p": 0.9,
        "sample_count": 32,
    }
    assert inference.calls[0]["sample_count"] == 32


def test_sampling_configuration_rejects_any_count_other_than_32():
    for sample_count in (0, 1, 12, 31, 33, 64):
        with pytest.raises(ValueError, match="32"):
            _config(sample_count=sample_count)


def test_adapter_retains_all_paths_before_upstream_mean():
    adapter, _inference = _adapter()
    result = adapter.forecast(history=np.ones((64, 6)), future_session_ids=[f"S{i:02}" for i in range(60)], config=_config())
    np.testing.assert_array_equal(result.paths, np.load(FIXTURE))
    assert result.paths.shape == (32, 60, 6)


def test_adapter_quantiles_are_computed_over_path_axis_zero():
    from app.forecast.kronos_adapter import derive_quantiles
    paths = np.load(FIXTURE)
    quantiles = derive_quantiles(paths)
    np.testing.assert_allclose(quantiles, np.quantile(paths, q=[0.10, 0.50, 0.90], axis=0))
    assert quantiles.shape == (3, 60, 6)


def test_mean_path_cannot_substitute_for_probabilistic_quantiles():
    from app.forecast.kronos_adapter import derive_quantiles, validate_pre_mean_paths
    paths = np.load(FIXTURE)
    mean_path = paths.mean(axis=0)
    with pytest.raises(ValueError, match="sample|shape"):
        validate_pre_mean_paths(mean_path, horizon=60, feature_count=6, sample_count=32)
    actual = derive_quantiles(paths)
    fake = np.stack([mean_path, mean_path, mean_path])
    assert not np.allclose(actual, fake)


def test_adapter_rejects_wrong_path_horizon_and_feature_shapes():
    from app.forecast.kronos_adapter import validate_pre_mean_paths
    paths = np.load(FIXTURE)
    for invalid in (paths[:31], paths[:, :59], paths[:, :, :5], paths.reshape(32, -1)):
        with pytest.raises(ValueError, match="shape|32"):
            validate_pre_mean_paths(invalid, horizon=60, feature_count=6, sample_count=32)


def test_adapter_rejects_nan_and_infinite_outputs():
    from app.forecast.kronos_adapter import validate_pre_mean_paths
    paths = np.load(FIXTURE)
    for value in (float("nan"), float("inf"), float("-inf")):
        invalid = paths.copy()
        invalid[0, 0, 0] = value
        with pytest.raises(ValueError, match="finite"):
            validate_pre_mean_paths(invalid, horizon=60, feature_count=6, sample_count=32)


def test_adapter_warns_for_ohlc_and_negative_volume_without_mutation():
    paths = np.load(FIXTURE)
    invalid = paths.copy()
    invalid[0, 0, 1] = invalid[0, 0, 2] - 1.0
    invalid[1, 0, 4] = -10.0
    adapter, _inference = _adapter(invalid)
    result = adapter.forecast(history=np.ones((64, 6)), future_session_ids=[f"S{i:02}" for i in range(60)], config=_config())
    assert {warning.code for warning in result.validation_warnings} >= {"ohlc_inconsistent", "negative_volume"}
    np.testing.assert_array_equal(result.paths, invalid)


def test_adapter_warns_for_quantile_crossing_without_reordering(monkeypatch):
    import app.forecast.kronos_adapter as module
    crossed = np.zeros((3, 60, 6), dtype=np.float64)
    crossed[0] = 3.0
    crossed[1] = 2.0
    crossed[2] = 1.0
    monkeypatch.setattr(module, "derive_quantiles", lambda _paths: crossed.copy())
    adapter, _inference = _adapter()
    result = adapter.forecast(history=np.ones((64, 6)), future_session_ids=[f"S{i:02}" for i in range(60)], config=_config())
    assert any(warning.code == "quantile_crossing" for warning in result.validation_warnings)
    np.testing.assert_array_equal(result.quantiles, crossed)


def test_adapter_preserves_normalization_and_inverse_normalization():
    from app.forecast.kronos_adapter import normalize_history, inverse_normalize_paths
    history = np.arange(64 * 6, dtype=np.float64).reshape(64, 6) + 1.0
    normalized, statistics = normalize_history(history)
    restored = inverse_normalize_paths(np.broadcast_to(normalized[-1], (32, 60, 6)), statistics)
    np.testing.assert_allclose(restored[0, 0], history[-1], rtol=1e-7, atol=1e-7)
    assert np.isfinite(normalized).all()


def test_adapter_loads_only_verified_local_assets_without_remote_code_or_network(tmp_path, monkeypatch):
    from app.forecast.kronos_adapter import load_approved_local_pair
    def denied(*_args, **_kwargs):
        raise AssertionError("adapter attempted network access")
    monkeypatch.setattr("socket.create_connection", denied)
    calls: list[dict[str, object]] = []
    def loader(path, **kwargs):
        calls.append({"path": path, **kwargs})
        return object()
    pair = load_approved_local_pair(
        model_dir=tmp_path / "model",
        tokenizer_dir=tmp_path / "tokenizer",
        loader=loader,
        verified=True,
    )
    assert pair.model is not None and pair.tokenizer is not None
    assert all(call.get("local_files_only") is True for call in calls)
    assert all(call.get("trust_remote_code") in (None, False) for call in calls)


def test_adapter_result_manifest_is_bounded_and_contains_no_model_or_local_path():
    adapter, _inference = _adapter()
    result = adapter.forecast(history=np.ones((64, 6)), future_session_ids=[f"S{i:02}" for i in range(60)], config=_config())
    manifest = result.capped_manifest()
    serialized = json.dumps(manifest)
    assert len(serialized.encode()) < 16 * 1024
    assert "local_" not in serialized
    assert "model_object" not in serialized
    assert "paths" not in manifest
    assert manifest["sample_count"] == 32
