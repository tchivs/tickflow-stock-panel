"""Pinned local supply manifest and optional dependency boundary tests for Phase 05."""
from __future__ import annotations

import sys
import tomllib

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SUPPLY_MANIFEST = (
    REPOSITORY_ROOT
    / ".planning"
    / "phases"
    / "05-optional-enhancements"
    / "05-01-SUMMARY.md"
)
SOURCE_COMMIT = "67b630e67f6a18c9e9be918d9b4337c960db1e9a"


def _assert_pinned_supply_manifest(summary: str) -> None:
    required_package_rows = (
        "| scikit-learn | `1.8.0`",
        "| torch | official PyTorch package",
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
        *required_package_rows,
        *required_source,
        *required_checkpoints,
        *required_policy,
    ):
        assert expected in summary, f"missing pinned supply manifest entry: {expected}"

def test_complete_optional_supply_manifest_is_present() -> None:
    _assert_pinned_supply_manifest(SUPPLY_MANIFEST.read_text(encoding="utf-8"))




def _project_and_lock() -> tuple[dict, dict]:
    backend = REPOSITORY_ROOT / "backend"
    project = tomllib.loads((backend / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((backend / "uv.lock").read_text(encoding="utf-8"))
    return project, lock


def test_supply_manifest_check_rejects_missing_or_moving_identities() -> None:
    manifest = SUPPLY_MANIFEST.read_text(encoding="utf-8")
    hostile_records = {
        "missing-package": manifest.replace(
            "| safetensors | `0.6.2`", "| safetensors | rejected", 1
        ),
        "moving-source": manifest.replace(SOURCE_COMMIT, "main"),
        "network-policy": manifest.replace(
            "Routine application startup, API requests, worker execution, tests, and model loading are local-only.",
            "Routine application startup, API requests, worker execution, tests, and model loading may use a network fallback.",
            1,
        ),
    }
    for label, hostile in hostile_records.items():
        try:
            _assert_pinned_supply_manifest(hostile)
        except AssertionError:
            continue
        raise AssertionError(f"hostile supply manifest unexpectedly passed: {label}")


def test_forecast_torch_exact_pin_and_extra_isolation() -> None:
    project, lock = _project_and_lock()
    extras = project["project"]["optional-dependencies"]
    assert extras["shadow"] == ["scikit-learn==1.8.0"]
    assert extras["forecast"] == [
        "torch==2.13.0",
        "einops==0.8.1",
        "huggingface-hub==0.33.1",
        "safetensors==0.6.2",
    ]
    sources = project["tool"]["uv"]["sources"]
    assert sources["torch"] == {"index": "pytorch-cpu"}
    indexes = {item["name"]: item["url"] for item in project["tool"]["uv"]["index"]}
    assert indexes["pytorch-cpu"] == "https://download.pytorch.org/whl/cpu"
    packages = {package["name"]: package for package in lock["package"]}
    torch_pkg = packages["torch"]
    assert torch_pkg["version"] in {"2.13.0", "2.13.0+cpu"}
    assert torch_pkg["source"]["registry"] == "https://download.pytorch.org/whl/cpu"
    assert not any(package["name"].startswith("nvidia-") for package in lock["package"])
    assert extras["legacy-cpu"] == ["polars[rtcompat]>=1.0"]
    assert extras["backtest"] == ["vectorbt>=0.26"]
    assert extras["desktop"] == ["pywebview>=5.0"]
    assert extras["dev"] == [
        "pytest>=8.0",
        "pytest-asyncio>=0.23",
        "ruff>=0.5",
        "mypy>=1.10",
    ]


def test_base_extra_independent() -> None:
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
    assert {item["version"] for item in torch_packages} == {"2.13.0", "2.13.0+cpu"}
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
    """Base package import must not pull optional heavy deps in a clean interpreter.

    Suite-level pollution from prior Shadow/Forecast tests can leave sklearn in
    sys.modules of the parent process; the contract is cold-import isolation.
    """
    import os
    import subprocess

    script = (
        "import sys\n"
        "import app\n"
        "assert app is not None\n"
        "missing = [name for name in ('torch', 'sklearn', 'huggingface_hub') "
        "if name in sys.modules]\n"
        "raise SystemExit(0 if not missing else f'loaded:{missing}')\n"
    )
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        env=env,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


if __name__ == "__main__":
    test_complete_optional_supply_manifest_is_present()
    print("Phase 05 optional supply manifest: complete and pinned")
