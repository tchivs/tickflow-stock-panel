"""RED contracts for the pinned pre-mean Kronos adapter and quantile axis."""
from __future__ import annotations

import hashlib

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


def _write_verified_source(root: Path) -> Path:
    source = root / "source"
    source.mkdir(parents=True)
    files = {
        "LICENSE": b"MIT\n",
        "__init__.py": (
            b"from .kronos import Kronos, KronosTokenizer, sample_from_logits\n"
            b"__all__ = ['Kronos', 'KronosTokenizer', 'sample_from_logits']\n"
        ),
        "kronos.py": (
            b"class Kronos:\n"
            b"    @classmethod\n"
            b"    def from_pretrained(cls, path, local_files_only=True):\n"
            b"        return cls()\n"
            b"class KronosTokenizer:\n"
            b"    @classmethod\n"
            b"    def from_pretrained(cls, path, local_files_only=True):\n"
            b"        return cls()\n"
            b"def sample_from_logits(*args, **kwargs):\n"
            b"    raise RuntimeError('sampler-not-for-unit')\n"
        ),
        "module.py": b"# helper\n",
    }
    for name, content in files.items():
        (source / name).write_bytes(content)
    import hashlib
    import json

    (source / "UPSTREAM.json").write_text(
        json.dumps(
            {
                "revision": "67b630e67f6a18c9e9be918d9b4337c960db1e9a",
                "files": {
                    name: {
                        "destination": name,
                        "vendored_sha256": hashlib.sha256(content).hexdigest(),
                    }
                    for name, content in files.items()
                },
            }
        ),
        encoding="utf-8",
    )
    return source


def _checkpoint_for_source(source: Path, model_dir: Path, tokenizer_dir: Path):
    from types import SimpleNamespace

    from app.forecast.catalog import _verify_source

    model_dir.mkdir(parents=True, exist_ok=True)
    tokenizer_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    (model_dir / "model.safetensors").write_bytes(b"model")
    (tokenizer_dir / "config.json").write_text("{}", encoding="utf-8")
    (tokenizer_dir / "model.safetensors").write_bytes(b"tok")
    manifest_sha, file_digests = _verify_source(
        source, "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
    )
    return SimpleNamespace(
        local_files_only=True,
        trust_remote_code=False,
        allowed_devices=("cpu",),
        model_dir=model_dir,
        tokenizer_dir=tokenizer_dir,
        max_context=64,
        source_dir=source,
        source_revision="67b630e67f6a18c9e9be918d9b4337c960db1e9a",
        source_manifest_sha256=manifest_sha,
        source_file_digests=file_digests,
        model_config_sha256=hashlib.sha256(b"{}").hexdigest(),
        model_weight_sha256=hashlib.sha256(b"model").hexdigest(),
        tokenizer_config_sha256=hashlib.sha256(b"{}").hexdigest(),
        tokenizer_weight_sha256=hashlib.sha256(b"tok").hexdigest(),
    )


def test_adapter_loads_from_verified_source_directory(tmp_path):
    from app.forecast.kronos_adapter import PinnedLocalKronosRunner, _load_verified_kronos_package

    source = _write_verified_source(tmp_path)
    package, sampler = _load_verified_kronos_package(source)
    assert callable(getattr(package, "Kronos", None))
    assert callable(sampler)
    module_file = Path(package.__file__).resolve()
    assert module_file.is_relative_to(source.resolve())

    checkpoint = _checkpoint_for_source(source, tmp_path / "model", tmp_path / "tokenizer")
    runner = PinnedLocalKronosRunner(checkpoint=checkpoint, device="cpu")
    pair = runner._pair()
    assert pair.model is not None and pair.tokenizer is not None


def test_adapter_import_shadow_rejected_for_preloaded_module(tmp_path, monkeypatch):
    import sys
    import types

    from app.forecast.kronos_adapter import _load_verified_kronos_package

    source = _write_verified_source(tmp_path)
    shadow = types.ModuleType("app.vendor.kronos")
    shadow.__file__ = str(tmp_path / "evil" / "kronos.py")
    (tmp_path / "evil").mkdir()
    (tmp_path / "evil" / "kronos.py").write_text("raise SystemExit('shadow')\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, "app.vendor.kronos", shadow)
    with pytest.raises(ValueError, match="import shadow rejected|origin"):
        _load_verified_kronos_package(source)


def test_adapter_child_revalidates_bytes_before_load(tmp_path):
    from app.forecast.kronos_adapter import PinnedLocalKronosRunner

    source = _write_verified_source(tmp_path)
    checkpoint = _checkpoint_for_source(source, tmp_path / "model", tmp_path / "tokenizer")
    (source / "kronos.py").write_bytes(b"print('tampered')\n")
    runner = PinnedLocalKronosRunner(checkpoint=checkpoint, device="cpu")
    with pytest.raises(Exception, match="digest|source"):
        runner._pair()


def test_approved_local_regression_constructs_verified_checkpoint_before_model_load(
    tmp_path, monkeypatch
):
    from app.forecast import kronos_adapter

    source = _write_verified_source(tmp_path)
    model_dir = tmp_path / "approved-model"
    tokenizer_dir = tmp_path / "approved-tokenizer"
    checkpoint = _checkpoint_for_source(source, model_dir, tokenizer_dir)
    captured: list[object] = []

    class LocalRunner:
        def __init__(self, *, checkpoint, device):
            assert device == "cpu"
            captured.append(checkpoint)

        def __call__(self, **kwargs):
            return np.ones((kwargs["sample_count"], len(kwargs["future_session_ids"]), 6))

    monkeypatch.setattr(kronos_adapter, "PinnedLocalKronosRunner", LocalRunner)
    regression = kronos_adapter.ApprovedLocalKronosRegression(
        source_dir=source,
        source_revision=checkpoint.source_revision,
        model_dir=model_dir,
        model_revision="f4e68697d9d5aed55cef5c96aabc3376bcad9f81",
        model_sha256=checkpoint.model_weight_sha256,
        tokenizer_dir=tokenizer_dir,
        tokenizer_revision="26966d0035065a0cae0ebad7af8ece35bc1fb51c",
        tokenizer_sha256=checkpoint.tokenizer_weight_sha256,
        device="cpu",
    )

    result = regression.run(seed=20250715, horizon=5, lookback=64, sample_count=32)

    assert result.paths.shape == (32, 5, 6)
    assert len(captured) == 1
    assert captured[0].local_files_only is True
    assert captured[0].trust_remote_code is False
    assert captured[0].model_weight_sha256 == checkpoint.model_weight_sha256

