"""Supply-chain approval and optional dependency boundary tests for Phase 05."""
from __future__ import annotations

import sys
import tomllib

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
APPROVAL_SUMMARY = (
    REPOSITORY_ROOT
    / ".planning"
    / "phases"
    / "05-optional-enhancements"
    / "05-01-SUMMARY.md"
)
SOURCE_COMMIT = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"


def _assert_complete_approval(summary: str) -> None:
    frontmatter = summary.split("---", 2)[1]
    metadata = {
        key: value
        for line in frontmatter.splitlines()
        if ": " in line
        for key, value in (line.split(": ", 1),)
    }
    assert metadata.get("status") == "complete"
    assert metadata.get("approval") == "approved"
    assert metadata.get("approved_at") == "2026-07-16T03:41:52Z"
    required_metadata = (
        "Decision: `approved` for every listed package, source, model, tokenizer, digest, and local-only loading policy",
    )
    required_package_rows = (
        "| scikit-learn | `1.8.0`",
        "| torch | official PyTorch package; resolve and lock a compatible `>=2,<3` Linux CPU wheel",
        "| einops | `0.8.1`",
        "| huggingface-hub | `0.33.1`",
        "| safetensors | `0.6.2`",
        "| tqdm | keep the compatible existing lock (`4.67.3` at review time)",
    )
    required_source = (
        f"Commit: `{SOURCE_COMMIT}`",
        "Vendored subset: `model/__init__.py`, `model/kronos.py`, `model/module.py`, plus `LICENSE` and `UPSTREAM.json`",
        "License: MIT",
    )
    required_checkpoints = (
        "`f4e68697d9d5aed55cef5c96aabc3376bcad9f81` | `a7d5f37e2e9fbd9891f7d7d4f72574512dd1f704fee14223e0a8cd0fbf54197c`",
        "`26966d0035065a0cae0ebad7af8ece35bc1fb51c` | `b97ec46b3b72160509e289183eaf7bdf5f0dac5bb9b49522f6d46638a99a8717`",
        "`901c26c1332695a2a8f243eb2f37243a37bea320` | `b082dfcbd8e8c142a725c8bbb99781802f38fec81210e13479effb32b3c3e020`",
        "`0e0117387f39004a9016484a186a908917e22426` | `59d85f6af76a2c3b8240ea06cb21db4213b4eeca053f246b23e29cf832fc6bee`",
    )
    required_policy = (
        "Provisioning may access the network only through an explicit operator action.",
        "Routine application startup, API requests, worker execution, tests, and model loading are local-only.",
        "`trust_remote_code` is forbidden.",
        "Pickle and moving `latest`/branch references are forbidden.",
    )

    for expected in (
        *required_metadata,
        *required_package_rows,
        *required_source,
        *required_checkpoints,
        *required_policy,
    ):
        assert expected in summary, f"missing approved supply-chain record: {expected}"

def test_complete_optional_supply_chain_approval_is_present() -> None:
    _assert_complete_approval(APPROVAL_SUMMARY.read_text(encoding="utf-8"))




def _project_and_lock() -> tuple[dict, dict]:
    backend = REPOSITORY_ROOT / "backend"
    project = tomllib.loads((backend / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((backend / "uv.lock").read_text(encoding="utf-8"))
    return project, lock


def test_approval_check_rejects_partial_rejected_and_stale_records() -> None:
    approved = APPROVAL_SUMMARY.read_text(encoding="utf-8")
    hostile_records = {
        "partial": approved.replace("approval: approved", "approval: partial", 1),
        "rejected-package": approved.replace(
            "| safetensors | `0.6.2`", "| safetensors | rejected", 1
        ),
        "moving-source": approved.replace(SOURCE_COMMIT, "main"),
        "stale": approved.replace(
            "approved_at: 2026-07-16T03:41:52Z",
            "approved_at: 2025-07-16T03:41:52Z",
            1,
        ),
        "network-policy": approved.replace(
            "local-only loading policy", "network fallback policy", 1
        ),
    }
    for label, hostile in hostile_records.items():
        try:
            _assert_complete_approval(hostile)
        except AssertionError:
            continue
        raise AssertionError(f"hostile approval unexpectedly passed: {label}")


def test_shadow_and_forecast_extras_are_exact_and_independent() -> None:
    project, _lock = _project_and_lock()
    extras = project["project"]["optional-dependencies"]
    assert extras["shadow"] == ["scikit-learn==1.8.0"]
    assert extras["forecast"] == [
        "torch>=2,<3",
        "einops==0.8.1",
        "huggingface-hub==0.33.1",
        "safetensors==0.6.2",
    ]
    assert extras["legacy-cpu"] == ["polars[rtcompat]>=1.0"]
    assert extras["backtest"] == ["vectorbt>=0.26"]
    assert extras["desktop"] == ["pywebview>=5.0"]
    assert extras["dev"] == [
        "pytest>=8.0",
        "pytest-asyncio>=0.23",
        "ruff>=0.5",
        "mypy>=1.10",
    ]


def test_base_dependencies_do_not_select_optional_heavy_packages() -> None:
    project, _lock = _project_and_lock()
    base_names = {
        dependency.split("[", 1)[0].split(";", 1)[0].split("=", 1)[0].strip().lower()
        for dependency in project["project"]["dependencies"]
    }
    assert base_names.isdisjoint(
        {"scikit-learn", "torch", "einops", "huggingface-hub", "safetensors"}
    )


def test_lock_contains_only_approved_optional_identities_and_hashes() -> None:
    project, lock = _project_and_lock()
    packages = lock["package"]
    by_name: dict[str, list[dict]] = {}
    for package in packages:
        by_name.setdefault(package["name"], []).append(package)

    for name, version in {
        "scikit-learn": "1.8.0",
        "einops": "0.8.1",
        "huggingface-hub": "0.33.1",
        "safetensors": "0.6.2",
        "tqdm": "4.67.3",
    }.items():
        matches = by_name[name]
        assert {item["version"] for item in matches} == {version}
        assert all(item.get("wheels") or item.get("sdist") for item in matches)

    assert project["tool"]["uv"]["sources"]["torch"] == {"index": "pytorch-cpu"}
    torch_packages = by_name["torch"]
    assert torch_packages
    assert all(
        item["source"]["registry"] == "https://download.pytorch.org/whl/cpu"
        for item in torch_packages
    )
    linux_wheels = [
        wheel
        for item in torch_packages
        for wheel in item.get("wheels", [])
        if "linux" in wheel["url"] or "manylinux" in wheel["url"]
    ]
    assert linux_wheels
    assert all("%2Bcpu" in wheel["url"] for wheel in linux_wheels)
    assert not any(package["name"].startswith("nvidia-") for package in packages)


def test_project_lock_metadata_keeps_extras_separate_and_approved() -> None:
    _project, lock = _project_and_lock()
    root = next(
        package for package in lock["package"] if package["name"] == "tickflow-stock-panel-backend"
    )
    assert root["optional-dependencies"]["shadow"] == [{"name": "scikit-learn"}]
    forecast = root["optional-dependencies"]["forecast"]
    assert {entry["name"] for entry in forecast} == {
        "torch",
        "einops",
        "huggingface-hub",
        "safetensors",
    }
    assert "matplotlib" not in {entry["name"] for entry in forecast}


def test_importing_base_app_does_not_load_optional_packages() -> None:
    import app

    assert app is not None
    assert "torch" not in sys.modules
    assert "sklearn" not in sys.modules
    assert "huggingface_hub" not in sys.modules


if __name__ == "__main__":
    test_complete_optional_supply_chain_approval_is_present()
    print("Phase 05 optional supply-chain approval: complete and approved")