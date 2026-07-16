"""Opt-in offline regression for a human-approved pinned local Kronos pair."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import resource
import time

import pytest

pytestmark = pytest.mark.kronos_model

SOURCE_REVISION = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"
MINI_REVISION = "f4e68697d9d5aed55cef5c96aabc3376bcad9f81"
MINI_SHA256 = "a7d5f37e2e9fbd9891f7d7d4f72574512dd1f704fee14223e0a8cd0fbf54197c"
TOKENIZER_REVISION = "26966d0035065a0cae0ebad7af8ece35bc1fb51c"
TOKENIZER_SHA256 = "b97ec46b3b72160509e289183eaf7bdf5f0dac5bb9b49522f6d46638a99a8717"


def _approved_path(name: str) -> Path:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"{name} is not configured; approved local Kronos regression is opt-in")
    path = Path(value).resolve()
    if not path.is_dir():
        pytest.fail(f"{name} is configured but is not an approved local directory")
    return path


def test_pinned_local_kronos_mini_regression_denies_network_and_proves_exact_provenance(monkeypatch):
    source_dir = _approved_path("ATHENA_KRONOS_SOURCE_DIR")
    model_dir = _approved_path("ATHENA_KRONOS_MINI_DIR")
    tokenizer_dir = _approved_path("ATHENA_KRONOS_TOKENIZER_2K_DIR")
    upstream = json.loads((source_dir / "UPSTREAM.json").read_text(encoding="utf-8"))
    assert upstream["revision"] == SOURCE_REVISION
    assert hashlib.sha256((model_dir / "model.safetensors").read_bytes()).hexdigest() == MINI_SHA256
    assert hashlib.sha256((tokenizer_dir / "model.safetensors").read_bytes()).hexdigest() == TOKENIZER_SHA256

    from app.forecast.runner import ForecastLimits

    limits = ForecastLimits()
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "POLARS_MAX_THREADS",
        "TORCH_NUM_THREADS",
    ):
        monkeypatch.setenv(name, str(limits.thread_count))
    thread_root = Path("/proc/self/task")
    threads_before = len(tuple(thread_root.iterdir())) if thread_root.is_dir() else 0
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    started_at = time.perf_counter()

    def denied(*_args, **_kwargs):
        raise AssertionError("real-model regression attempted network access")
    monkeypatch.setattr("socket.create_connection", denied)

    from app.forecast.kronos_adapter import ApprovedLocalKronosRegression
    regression = ApprovedLocalKronosRegression(
        source_dir=source_dir,
        source_revision=SOURCE_REVISION,
        model_dir=model_dir,
        model_revision=MINI_REVISION,
        model_sha256=MINI_SHA256,
        tokenizer_dir=tokenizer_dir,
        tokenizer_revision=TOKENIZER_REVISION,
        tokenizer_sha256=TOKENIZER_SHA256,
        device="cpu",
    )
    result = regression.run(seed=20250715, horizon=5, lookback=64, sample_count=32)
    observed_wall_seconds = time.perf_counter() - started_at
    observed_peak_rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    observed_threads = len(tuple(thread_root.iterdir())) if thread_root.is_dir() else 0

    import torch

    resource_observation = {
        "wall_seconds": round(observed_wall_seconds, 3),
        "peak_rss_bytes": observed_peak_rss_bytes,
        "rss_growth_bytes": max(0, observed_peak_rss_bytes - rss_before),
        "os_threads_before": threads_before,
        "os_threads_after": observed_threads,
        "torch_threads": torch.get_num_threads(),
        "policy_wall_seconds": limits.wall_clock_seconds,
        "policy_address_space_bytes": limits.address_space_bytes,
        "policy_threads": limits.thread_count,
    }
    print(f"kronos_resource_observation={json.dumps(resource_observation, sort_keys=True)}")
    assert observed_wall_seconds <= limits.wall_clock_seconds
    assert observed_peak_rss_bytes <= limits.address_space_bytes
    assert torch.get_num_threads() <= limits.thread_count
    assert result.paths.shape == (32, 5, 6)
    assert result.quantiles.shape == (3, 5, 6)
    assert result.provenance == {
        "source_revision": SOURCE_REVISION,
        "model_revision": MINI_REVISION,
        "model_sha256": MINI_SHA256,
        "tokenizer_revision": TOKENIZER_REVISION,
        "tokenizer_sha256": TOKENIZER_SHA256,
    }
