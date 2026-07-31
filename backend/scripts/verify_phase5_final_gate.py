"""Fail-closed Phase 05 machine-report parser and one-shot final orchestrator.

The legacy parser mode accepts one pytest JUnit report plus one or more
Playwright JSON reports.  The ``orchestrate`` mode is stricter: it freezes a
clean git HEAD/tree, runs exactly four producers into one repository-external
root, validates adjacent provenance sidecars, parses fifteen report-qualified
findings, and atomically updates only the R43/Wave 15 validation scope.

Standard library only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

def _find_phase05_dir(repo_root: Path) -> Path:
    """Resolve the Phase 05 planning directory independent of archival layout."""
    milestones = repo_root / ".planning" / "milestones"
    if milestones.is_dir():
        for candidate in sorted(milestones.iterdir()):
            phase_dir = candidate / "05-optional-enhancements"
            if phase_dir.is_dir():
                return phase_dir
    return repo_root / ".planning" / "phases" / "05-optional-enhancements"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE05_DIR = _find_phase05_dir(_REPO_ROOT)

def _phase05_rel(filename: str) -> str:
    """Phase 05 artifact path relative to repository root."""
    return str((_PHASE05_DIR / filename).relative_to(_REPO_ROOT))

REPORT_LABELS: tuple[str, ...] = (
    "pytest-windows",
    "pytest-linux",
    "playwright-fixture",
    "playwright-real-host",
)
REPORT_FILENAMES: dict[str, str] = {
    "pytest-windows": "pytest-windows.xml",
    "pytest-linux": "pytest-linux.xml",
    "playwright-fixture": "playwright-fixture.json",
    "playwright-real-host": "playwright-real-host.json",
}
RELEVANT_PATHS: tuple[str, ...] = (
    "backend",
    "frontend",
    "backend/scripts/verify_phase5_final_gate.py",
    "backend/tests/test_phase5_final_gate.py",
    _phase05_rel("05-VALIDATION.md"),
    _phase05_rel("05-43-SUMMARY.md"),
    _phase05_rel("05-44-PLAN.md"),
    ".github/workflows/phase5-linux-evidence.yml",
)

# Finding -> (required report label, report kind, exact normalized identity).
REQUIRED_REPORT_NODES: dict[str, tuple[str, str, str]] = {
    "CR-01": (
        "playwright-real-host",
        "playwright",
        "playwright:e2e/phase5-shadow-real-host.spec.ts::"
        "CR-01 real host non-empty Shadow import to evidence distillation and IS-OOS",
    ),
    "CR-02": (
        "pytest-linux",
        "pytest",
        "pytest:tests.forecast.test_calibration::"
        "test_cr02_projection_and_calibration_use_same_verified_parquet_bytes",
    ),
    "CR-03": (
        "pytest-linux",
        "pytest",
        "pytest:tests.forecast.test_api::"
        "test_cr03_same_instrument_cross_principal_matrix_denies_every_surface",
    ),
    "CR-04": (
        "playwright-fixture",
        "playwright",
        "playwright:e2e/phase5-optional-enhancements.spec.ts::"
        "CR-04 calibration outcome identity renders 5 20 60 and fails closed",
    ),
    "CR-05": (
        "pytest-linux",
        "pytest",
        "pytest:tests.forecast.test_runner::"
        "test_cr05_final_input_revalidation_precedes_commit_and_commit_spy_zero",
    ),
    "CR-06": (
        "pytest-linux",
        "pytest",
        "pytest:tests.forecast.test_runner::"
        "test_cr06_normal_leader_exit_reaps_process_group_before_commit",
    ),
    "CR-07": (
        "pytest-linux",
        "pytest",
        "pytest:tests.test_phase5_optional_host::"
        "test_cr07_real_host_queued_restart_executes_once",
    ),
    "WR-01": (
        "pytest-linux",
        "pytest",
        "pytest:tests.forecast.test_runner::"
        "test_wr01_operation_first_replay_race_leaves_no_orphan",
    ),
    "WR-02": (
        "pytest-linux",
        "pytest",
        "pytest:tests.test_phase5_foundation::"
        "test_wr02_parquet_same_open_rejects_toctou",
    ),
    "WR-03": (
        "playwright-fixture",
        "playwright",
        "playwright:e2e/phase5-optional-enhancements.spec.ts::"
        "WR-03 paged Thesis history renders before version page",
    ),
    "R43-CR-01": (
        "pytest-windows",
        "pytest",
        "pytest:tests.advanced.test_sandbox::"
        "test_r43_cr01_positive_interpreter_hold_program_runs_without_python_authority",
    ),
    "R43-CR-02": (
        "pytest-windows",
        "pytest",
        "pytest:tests.forecast.test_runner::"
        "test_r43_cr02_retryable_terminal_matrix_uses_repository_contract",
    ),
    "R43-CR-03": (
        "pytest-windows",
        "pytest",
        "pytest:tests.forecast.test_runner::"
        "test_r43_cr03_owner_first_retry_publishes_once_without_orphan",
    ),
    "R43-CR-04": (
        "pytest-windows",
        "pytest",
        "pytest:tests.test_phase5_optional_host::"
        "test_r43_cr04_host_close_surfaces_unresolved_owner_and_bounded_retry_succeeds",
    ),
    "R43-WR-01": (
        "pytest-windows",
        "pytest",
        "pytest:tests.forecast.test_runner::"
        "test_r43_wr01_windows_fail_closed_and_linux_process_group_nodes_are_explicit",
    ),
}

# Backwards-compatible legacy selector shape used by the historical parser tests.
REQUIRED_NODES: dict[str, tuple[str, str]] = {
    finding: (kind, identity.rsplit("::", 1)[-1])
    for finding, (_label, kind, identity) in REQUIRED_REPORT_NODES.items()
}

OPTIONAL_ABSENT_ALLOWLIST: frozenset[str] = frozenset(
    {
        "test_pinned_local_kronos_mini_regression_denies_network_and_proves_exact_provenance",
        "tests/forecast/test_kronos_regression.py::"
        "test_pinned_local_kronos_mini_regression_denies_network_and_proves_exact_provenance",
        "backend/tests/forecast/test_kronos_regression.py::"
        "test_pinned_local_kronos_mini_regression_denies_network_and_proves_exact_provenance",
    }
)
_PLAYWRIGHT_NON_PASS = frozenset(
    {"failed", "timedOut", "interrupted", "skipped", "flaky"}
)
_BASE_SIDECAR_FIELDS = frozenset(
    {
        "expectedHead",
        "expectedTree",
        "runId",
        "startedAt",
        "producerStartedAt",
        "producerCompletedAt",
        "label",
        "reportPath",
        "reportRoot",
    }
)
GITHUB_REPOSITORY = "tchivs/AthenaQuant"
PHASE5_LINUX_WORKFLOW = ".github/workflows/phase5-linux-evidence.yml"
PHASE5_LINUX_WORKFLOW_NAME = "Phase 5 Linux Evidence"
PHASE5_LINUX_WORKFLOW_EVENTS = frozenset({"push", "workflow_dispatch"})
LINUX_EVIDENCE_SCHEMA = "athena.phase5-linux-evidence/v1"
LINUX_REPORT_MARKER = "not windows_only"
LINUX_NATIVE_MARKER = "linux_process_group"
_LINUX_ATTESTATION_FIELDS = frozenset(
    {
        "schemaVersion",
        "repository",
        "workflow",
        "githubRunId",
        "githubRunAttempt",
        "artifactName",
        "expectedHead",
        "expectedTree",
        "runnerOS",
        "pytestCommand",
        "pytestMarker",
        "nativeMarkerCommand",
        "nativeMarker",
        "startedAt",
        "completedAt",
        "junitSha256",
    }
)
_MAX_ATTESTATION_AGE = timedelta(hours=24)
_MAX_GITHUB_ARTIFACT_BYTES = 128 * 1024 * 1024
_MAX_GITHUB_ARTIFACT_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
_GITHUB_API_TIMEOUT_SECONDS = 60
PRODUCER_TIMEOUT_SECONDS = 30 * 60
_PRODUCER_TERMINATION_GRACE_SECONDS = 10
_WSL_PREFLIGHT_TIMEOUT_SECONDS = 30
_R43_FINDINGS = (
    "R43-CR-01",
    "R43-CR-02",
    "R43-CR-03",
    "R43-CR-04",
    "R43-WR-01",
)
_SCOPED_TASKS = ("05-GC-43-1", "05-GC-43-2", "05-GC-43-3", "05-GC-44-2")
_OPTIONAL_SMOKE = (
    "tests/forecast/test_kronos_regression.py::"
    "test_pinned_local_kronos_mini_regression_denies_network_and_proves_exact_provenance"
)
_BACKEND_TEST_TARGETS: tuple[str, ...] = (
    "tests/shadow",
    "tests/theses",
    "tests/forecast",
    "tests/advanced/test_sandbox.py",
    "tests/test_operational_migrations.py",
    "tests/test_phase5_foundation.py",
    "tests/test_phase5_optional_dependencies.py",
    "tests/test_kronos_vendor_sync.py",
    "tests/test_kronos_provisioner.py",
    "tests/test_phase5_optional_host.py",
)
_WINDOWS_BACKEND_TEST_TARGETS: tuple[str, ...] = (
    "tests/advanced/test_sandbox.py",
    "tests/forecast/test_runner.py",
    "tests/test_operational_migrations.py",
    "tests/test_phase5_optional_host.py",
)
LINUX_NATIVE_PYTEST_COMMAND = (
    "uv run --isolated --frozen --extra dev pytest -p no:cacheprovider "
    "tests/advanced/test_sandbox.py tests/forecast/test_runner.py "
    "tests/test_operational_migrations.py tests/test_phase5_optional_host.py "
    "-m linux_process_group -q"
)
LINUX_REPORT_PYTEST_COMMAND = (
    "uv run --isolated --frozen --extra dev --extra shadow "
    "pytest -p no:cacheprovider "
    "--import-mode=importlib "
    + " ".join(_BACKEND_TEST_TARGETS)
    + f" --deselect={_OPTIONAL_SMOKE} -o xfail_strict=true "
    "-m 'not windows_only' "
    "--junitxml=.phase5-evidence/pytest-linux.xml -x"
)


class ReportError(RuntimeError):
    """A gate input or machine report cannot establish final evidence."""


@dataclass(frozen=True)
class GitProvenance:
    expected_head: str
    expected_tree: str
    phase43_commit: str


@dataclass(frozen=True)
class ProducerSpec:
    label: str
    cwd: Path
    argv: tuple[str, ...]
    env: dict[str, str]
    report_path: Path
    sidecar_path: Path


@dataclass(frozen=True)
class ReportEnvelope:
    label: str
    report_path: Path
    sidecar_path: Path
    expected_head: str
    expected_tree: str
    run_id: str
    started_at: str
    producer_started_at: str
    producer_completed_at: str
    report_root: Path
    external_evidence: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class ReportStats:
    kind: str
    path: str
    discovered: int
    passed: int
    nodes: tuple[str, ...]
    label: str | None = None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_utc(value: datetime | None = None) -> str:
    return (value or _utc_now()).astimezone(UTC).isoformat().replace(
        "+00:00", "Z"
    )


def _parse_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ReportError(f"provenance field {field} is malformed")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReportError(f"provenance field {field} is malformed") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ReportError(f"provenance field {field} must be UTC")
    return parsed.astimezone(UTC)


def _canonical(path: Path) -> Path:
    return path.expanduser().resolve()


def _canonical_from_repo(path: Path, repo_root: Path) -> Path:
    expanded = path.expanduser()
    return (repo_root / expanded if not expanded.is_absolute() else expanded).resolve()



def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _require_file(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise ReportError(f"report is missing or invalid: {path}")


def _git(repo_root: Path, *arguments: str) -> str:
    argv = ["git", *arguments]
    completed = subprocess.run(
        argv,
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ReportError(f"git command failed ({argv!r}): {detail}")
    return completed.stdout.strip()


def _assert_clean_relevant_paths(repo_root: Path) -> None:
    output = _git(
        repo_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        *RELEVANT_PATHS,
    )
    if output:
        raise ReportError(f"relevant pathspec is dirty:\n{output}")


def capture_git_provenance(
    repo_root: Path, phase43_summary: Path
) -> GitProvenance:
    repo_root = _canonical(repo_root)
    summary = _canonical(phase43_summary)
    if not _inside(summary, repo_root) or not summary.is_file():
        raise ReportError("05-43 summary is missing or outside the repository")
    expected_head = _git(repo_root, "rev-parse", "HEAD")
    expected_tree = _git(repo_root, "rev-parse", "HEAD^{tree}")
    summary_relative = summary.relative_to(repo_root).as_posix()
    phase43_commit = _git(
        repo_root, "log", "-n", "1", "--format=%H", "--", summary_relative
    )
    if not phase43_commit:
        raise ReportError("05-43 summary has no committed provenance")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", phase43_commit, expected_head],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if ancestor.returncode != 0:
        raise ReportError(
            "committed 05-43 summary is not an ancestor of expectedHead"
        )
    _assert_clean_relevant_paths(repo_root)
    return GitProvenance(expected_head, expected_tree, phase43_commit)


def assert_git_provenance(repo_root: Path, expected: GitProvenance) -> None:
    repo_root = _canonical(repo_root)
    current_head = _git(repo_root, "rev-parse", "HEAD")
    if current_head != expected.expected_head:
        raise ReportError(
            f"HEAD drift: expected {expected.expected_head}, found {current_head}"
        )
    current_tree = _git(repo_root, "rev-parse", "HEAD^{tree}")
    if current_tree != expected.expected_tree:
        raise ReportError(
            f"tree drift: expected {expected.expected_tree}, found {current_tree}"
        )
    _assert_clean_relevant_paths(repo_root)


def _pytest_argv(report: str, cache: str, marker: str) -> tuple[str, ...]:
    return (
        "uv",
        "run",
        "--isolated",
        "--frozen",
        "--extra",
        "dev",
        "--extra",
        "shadow",
        "pytest",
        *_WINDOWS_BACKEND_TEST_TARGETS,
        "-o",
        "xfail_strict=true",
        "-o",
        f"cache_dir={cache}",
        "-m",
        marker,
        f"--junitxml={report}",
        "-x",
    )


def build_producer_specs(
    repo_root: Path,
    report_root: Path,
    *,
    linux_repo_root: str,
    linux_report_root: str,
    linux_native: bool = False,
) -> tuple[ProducerSpec, ...]:
    repo_root = _canonical(repo_root)
    report_root = _canonical(report_root)
    backend = repo_root / "backend"
    frontend = repo_root / "frontend"
    reports = {
        label: report_root / REPORT_FILENAMES[label] for label in REPORT_LABELS
    }
    common_env = {
        "ATHENA_ALLOW_NETWORK": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    windows = ProducerSpec(
        label="pytest-windows",
        cwd=backend,
        argv=_pytest_argv(
            str(reports["pytest-windows"]),
            str(report_root / "pytest-cache-windows"),
            "not linux_process_group",
        ),
        env={
            **common_env,
            "PYTEST_ADDOPTS": "",
            "TMP": str(report_root / "tmp-windows"),
            "TEMP": str(report_root / "tmp-windows"),
        },
        report_path=reports["pytest-windows"],
        sidecar_path=reports["pytest-windows"].with_name(
            reports["pytest-windows"].name + ".provenance.json"
        ),
    )

    linux_backend = f"{linux_repo_root.rstrip('/')}/backend"
    linux_report = f"{linux_report_root.rstrip('/')}/{REPORT_FILENAMES['pytest-linux']}"
    linux_cache = f"{linux_report_root.rstrip('/')}/pytest-cache-linux"
    linux_tmp = f"{linux_report_root.rstrip('/')}/tmp-linux"
    linux_command_parts = (
        "env",
        "ATHENA_ALLOW_NETWORK=0",
        "PYTHONDONTWRITEBYTECODE=1",
        f"TMPDIR={linux_tmp}",
        "uv",
        "run",
        "--isolated",
        "--frozen",
        "--extra",
        "dev",
        "--extra",
        "shadow",
        "--extra",
        "forecast",
        "pytest",
        "--import-mode=importlib",
        *_BACKEND_TEST_TARGETS,
        f"--deselect={_OPTIONAL_SMOKE}",
        "-o",
        "xfail_strict=true",
        "-o",
        f"cache_dir={linux_cache}",
        "-m",
        "not windows_only",
        f"--junitxml={linux_report}",
        "-x",
    )
    if linux_native:
        linux_argv: tuple[str, ...] = tuple(linux_command_parts)
        linux_cwd = backend
    else:
        linux_command = " ".join(
            shlex.quote(part) for part in linux_command_parts
        )
        linux_argv = (
            "wsl.exe",
            "--exec",
            "bash",
            "-lc",
            f"cd {shlex.quote(linux_backend)} && {linux_command}",
        )
        linux_cwd = repo_root
    linux = ProducerSpec(
        label="pytest-linux",
        cwd=linux_cwd,
        argv=linux_argv,
        env=common_env,
        report_path=reports["pytest-linux"],
        sidecar_path=reports["pytest-linux"].with_name(
            reports["pytest-linux"].name + ".provenance.json"
        ),
    )

    def playwright(
        label: str,
        *,
        config: str | None,
        spec: str,
        project: str,
    ) -> ProducerSpec:
        output = report_root / f"{label}-output"
        playwright_executable = (
            frontend
            / "node_modules"
            / ".bin"
            / ("playwright.cmd" if os.name == "nt" else "playwright")
        )
        argv: list[str] = [str(playwright_executable), "test"]
        if config is not None:
            argv.append(f"--config={config}")
        argv.extend(
            (
                spec,
                f"--project={project}",
                "--reporter=json",
                f"--output={output}",
            )
        )
        report = reports[label]
        return ProducerSpec(
            label=label,
            cwd=frontend,
            argv=tuple(argv),
            env={
                **common_env,
                "CI": "1",
                "PLAYWRIGHT_JSON_OUTPUT_FILE": str(report),
                "PLAYWRIGHT_JSON_OUTPUT_NAME": str(report),
                "PLAYWRIGHT_OUTPUT_DIR": str(output),
                "PLAYWRIGHT_HTML_OUTPUT_DIR": str(report_root / f"{label}-html"),
                "TMP": str(report_root / f"{label}-tmp"),
                "TEMP": str(report_root / f"{label}-tmp"),
            },
            report_path=report,
            sidecar_path=report.with_name(report.name + ".provenance.json"),
        )

    return (
        windows,
        linux,
        playwright(
            "playwright-fixture",
            config=None,
            spec="e2e/phase5-optional-enhancements.spec.ts",
            project="desktop-chromium",
        ),
        playwright(
            "playwright-real-host",
            config="playwright.phase5-real-host.config.ts",
            spec="e2e/phase5-shadow-real-host.spec.ts",
            project="phase5-shadow-real-host",
        ),
    )


def _write_json_fsync(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _terminate_process_tree(process: subprocess.Popen[Any]) -> None:
    if os.name == "nt":
        tree_killed = False
        for attempt in range(2):
            try:
                completed = subprocess.run(
                    (
                        "taskkill",
                        "/PID",
                        str(process.pid),
                        "/T",
                        "/F",
                    ),
                    check=False,
                    capture_output=True,
                    timeout=_PRODUCER_TERMINATION_GRACE_SECONDS,
                )
            except (OSError, subprocess.TimeoutExpired):
                completed = None
            if completed is not None and completed.returncode == 0:
                tree_killed = True
                break
            if attempt == 0:
                try:
                    process.kill()
                except OSError:
                    pass
        if not tree_killed:
            raise ReportError(
                "producer process tree cleanup could not be proven"
            )
        try:
            process.wait(timeout=_PRODUCER_TERMINATION_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=_PRODUCER_TERMINATION_GRACE_SECONDS)
            except subprocess.TimeoutExpired as error:
                raise ReportError(
                    "producer process tree could not be reaped within the "
                    "bounded grace period"
                ) from error
        return

    group_missing = False
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        group_missing = True

    try:
        process.wait(timeout=_PRODUCER_TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        pass

    if not group_missing:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            group_missing = True

    if not group_missing:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            group_missing = True

    try:
        process.wait(timeout=_PRODUCER_TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired as error:
        raise ReportError(
            "producer process tree could not be reaped within the "
            "bounded grace period"
        ) from error

    deadline = time.monotonic() + _PRODUCER_TERMINATION_GRACE_SECONDS
    while not group_missing:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            group_missing = True
            break
        if time.monotonic() >= deadline:
            raise ReportError(
                "producer process tree cleanup could not be proven"
            )
        time.sleep(0.01)


def _run_bounded_producer(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
) -> subprocess.CompletedProcess[Any]:
    process_kwargs: dict[str, Any] = {
        "cwd": cwd,
        "env": env,
    }
    if os.name == "nt":
        process_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        process_kwargs["start_new_session"] = True
    process = subprocess.Popen(argv, **process_kwargs)
    try:
        process.wait(timeout=PRODUCER_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process)
        raise
    return subprocess.CompletedProcess(argv, process.returncode)


def run_producer(
    spec: ProducerSpec,
    provenance: GitProvenance,
    *,
    run_id: str,
    started_at: str,
    runner: Callable[..., subprocess.CompletedProcess[Any]] | None = None,
) -> ReportEnvelope:
    if spec.report_path.exists() or spec.sidecar_path.exists():
        raise ReportError(f"producer target already exists: {spec.report_path}")
    spec.report_path.parent.mkdir(parents=True, exist_ok=True)
    for value in spec.env.values():
        if value and (
            value.startswith(str(spec.report_path.parent))
            or value.startswith(str(spec.report_path.parent).replace("\\", "/"))
        ):
            candidate = Path(value)
            if candidate.suffix == "":
                candidate.mkdir(parents=True, exist_ok=True)
    producer_started = _iso_utc()
    environment = os.environ.copy()
    environment.update(spec.env)
    try:
        if runner is None:
            completed = _run_bounded_producer(
                spec.argv,
                cwd=spec.cwd,
                env=environment,
            )
        else:
            completed = runner(
                spec.argv,
                cwd=spec.cwd,
                env=environment,
                check=False,
                timeout=PRODUCER_TIMEOUT_SECONDS,
            )
    except subprocess.TimeoutExpired as error:
        raise ReportError(
            f"producer {spec.label} timed out after "
            f"{PRODUCER_TIMEOUT_SECONDS} seconds"
        ) from error
    except OSError as error:
        raise ReportError(
            f"producer {spec.label} could not start: {error}"
        ) from error
    producer_completed = _iso_utc()
    if completed.returncode != 0:
        raise ReportError(
            f"producer {spec.label} failed with exit code {completed.returncode}"
        )
    _require_file(spec.report_path)
    payload = {
        "expectedHead": provenance.expected_head,
        "expectedTree": provenance.expected_tree,
        "runId": run_id,
        "startedAt": started_at,
        "producerStartedAt": producer_started,
        "producerCompletedAt": producer_completed,
        "label": spec.label,
        "reportPath": str(_canonical(spec.report_path)),
        "reportRoot": str(_canonical(spec.report_path.parent)),
    }
    _write_json_fsync(spec.sidecar_path, payload)
    return ReportEnvelope(
        label=spec.label,
        report_path=_canonical(spec.report_path),
        sidecar_path=_canonical(spec.sidecar_path),
        expected_head=provenance.expected_head,
        expected_tree=provenance.expected_tree,
        run_id=run_id,
        started_at=started_at,
        producer_started_at=producer_started,
        producer_completed_at=producer_completed,
        report_root=_canonical(spec.report_path.parent),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _require_commit_identity(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ReportError(f"Linux attestation {field} is malformed")
    return value


def _validate_linux_attestation(
    attestation: Mapping[str, Any],
    junit_path: Path,
    provenance: GitProvenance,
    *,
    github_repository: str,
    github_run_id: str,
    now: datetime,
) -> tuple[datetime, datetime]:
    if set(attestation) != _LINUX_ATTESTATION_FIELDS:
        raise ReportError("Linux attestation schema fields mismatch")
    try:
        parsed_run_id = int(github_run_id)
    except (TypeError, ValueError) as error:
        raise ReportError("GitHub run ID is malformed") from error
    if parsed_run_id <= 0 or str(parsed_run_id) != github_run_id:
        raise ReportError("GitHub run ID is malformed")
    expected = {
        "schemaVersion": LINUX_EVIDENCE_SCHEMA,
        "repository": GITHUB_REPOSITORY,
        "workflow": PHASE5_LINUX_WORKFLOW,
        "githubRunId": github_run_id,
        "artifactName": f"phase5-linux-evidence-{github_run_id}",
        "expectedHead": provenance.expected_head,
        "expectedTree": provenance.expected_tree,
        "runnerOS": "Linux",
        "pytestCommand": LINUX_REPORT_PYTEST_COMMAND,
        "pytestMarker": LINUX_REPORT_MARKER,
        "nativeMarkerCommand": LINUX_NATIVE_PYTEST_COMMAND,
        "nativeMarker": LINUX_NATIVE_MARKER,
    }
    if github_repository != GITHUB_REPOSITORY:
        raise ReportError(
            f"GitHub repository must be exactly {GITHUB_REPOSITORY}"
        )
    for field, value in expected.items():
        if attestation.get(field) != value:
            raise ReportError(f"Linux attestation {field} mismatch")
    _require_commit_identity(attestation.get("expectedHead"), "expectedHead")
    _require_commit_identity(attestation.get("expectedTree"), "expectedTree")
    attempt = attestation.get("githubRunAttempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt <= 0:
        raise ReportError("Linux attestation githubRunAttempt is malformed")
    started = _parse_utc(attestation.get("startedAt"), "startedAt")
    completed = _parse_utc(attestation.get("completedAt"), "completedAt")
    if not (
        started <= completed <= now + timedelta(minutes=5)
        and now - completed <= _MAX_ATTESTATION_AGE
    ):
        raise ReportError("Linux attestation is stale or has invalid timestamps")
    reported_hash = attestation.get("junitSha256")
    if (
        not isinstance(reported_hash, str)
        or len(reported_hash) != 64
        or reported_hash != reported_hash.lower()
        or any(character not in "0123456789abcdef" for character in reported_hash)
    ):
        raise ReportError("Linux attestation JUnit SHA-256 is malformed")
    if _sha256(junit_path) != reported_hash:
        raise ReportError("Linux attestation JUnit SHA-256 mismatch")
    return started, completed


def _verify_github_run(
    attestation: Mapping[str, Any],
    provenance: GitProvenance,
    *,
    github_repository: str,
    github_run_id: str,
    runner: Callable[..., subprocess.CompletedProcess[Any]],
) -> dict[str, Any]:
    argv = (
        "gh",
        "api",
        f"repos/{github_repository}/actions/runs/{github_run_id}",
        "--method",
        "GET",
    )
    try:
        completed = runner(
            argv,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GITHUB_API_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReportError(
            "GitHub run verification failed: gh is unavailable or timed out"
        ) from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise ReportError(
            "GitHub run verification failed"
            + (f": {detail}" if detail else "")
        )
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError) as error:
        raise ReportError("GitHub run verification returned malformed JSON") from error
    if not isinstance(payload, dict):
        raise ReportError("GitHub run verification returned malformed JSON")
    repository = payload.get("repository")
    head_commit = payload.get("head_commit")
    workflow_path = payload.get("path")
    checks = {
        "id": payload.get("id") == int(github_run_id),
        "repository": isinstance(repository, dict)
        and repository.get("full_name") == github_repository,
        "head_sha": payload.get("head_sha") == provenance.expected_head,
        "head_tree": isinstance(head_commit, dict)
        and head_commit.get("tree_id") == provenance.expected_tree,
        "status": payload.get("status") == "completed",
        "conclusion": payload.get("conclusion") == "success",
        "event": payload.get("event") in PHASE5_LINUX_WORKFLOW_EVENTS,
        "workflow": isinstance(workflow_path, str)
        and (
            workflow_path == PHASE5_LINUX_WORKFLOW
            or workflow_path.startswith(PHASE5_LINUX_WORKFLOW + "@")
        ),
        "workflow_name": payload.get("name") == PHASE5_LINUX_WORKFLOW_NAME,
        "attempt": payload.get("run_attempt")
        == attestation.get("githubRunAttempt"),
    }
    failed = [field for field, passed in checks.items() if not passed]
    if failed:
        raise ReportError(
            "GitHub run verification mismatch: " + ", ".join(failed)
        )
    return {
        "id": payload["id"],
        "repository": repository["full_name"],
        "headSha": payload["head_sha"],
        "headTree": head_commit["tree_id"],
        "status": payload["status"],
        "conclusion": payload["conclusion"],
        "event": payload["event"],
        "workflow": workflow_path,
        "workflowName": payload["name"],
        "runAttempt": payload["run_attempt"],
        "htmlUrl": payload.get("html_url"),
    }


def _github_artifact_binding(
    provenance: GitProvenance,
    *,
    github_repository: str,
    github_run_id: str,
    runner: Callable[..., subprocess.CompletedProcess[Any]],
    now: datetime,
) -> dict[str, Any]:
    expected_name = f"phase5-linux-evidence-{github_run_id}"
    endpoint = (
        f"repos/{github_repository}/actions/runs/{github_run_id}"
        "/artifacts?per_page=100"
    )
    argv = ("gh", "api", endpoint, "--method", "GET")
    try:
        completed = runner(
            argv,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GITHUB_API_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReportError(
            "GitHub artifact verification failed: gh is unavailable or timed out"
        ) from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise ReportError(
            "GitHub artifact verification failed"
            + (f": {detail}" if detail else "")
        )
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError) as error:
        raise ReportError(
            "GitHub artifact verification returned malformed JSON"
        ) from error
    if not isinstance(payload, dict):
        raise ReportError(
            "GitHub artifact verification returned malformed JSON"
        )
    artifacts = payload.get("artifacts")
    total_count = payload.get("total_count")
    if (
        not isinstance(artifacts, list)
        or not isinstance(total_count, int)
        or isinstance(total_count, bool)
        or total_count != len(artifacts)
        or total_count > 100
    ):
        raise ReportError("GitHub artifact listing is incomplete or malformed")
    matches = [
        artifact
        for artifact in artifacts
        if isinstance(artifact, dict)
        and artifact.get("name") == expected_name
    ]
    if len(matches) != 1:
        raise ReportError(
            "GitHub run must contain exactly one expected Linux artifact"
        )
    artifact = matches[0]
    artifact_id = artifact.get("id")
    size = artifact.get("size_in_bytes")
    digest = artifact.get("digest")
    expires_at = artifact.get("expires_at")
    workflow_run = artifact.get("workflow_run")
    if (
        not isinstance(artifact_id, int)
        or isinstance(artifact_id, bool)
        or artifact_id <= 0
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size <= 0
        or size > _MAX_GITHUB_ARTIFACT_BYTES
        or artifact.get("expired") is not False
        or not isinstance(digest, str)
        or not digest.startswith("sha256:")
        or len(digest) != len("sha256:") + 64
        or any(character not in "0123456789abcdef" for character in digest[7:])
        or not isinstance(workflow_run, dict)
        or workflow_run.get("id") != int(github_run_id)
        or workflow_run.get("head_sha") != provenance.expected_head
    ):
        raise ReportError("GitHub Linux artifact metadata mismatch")
    expiry = _parse_utc(expires_at, "artifact expires_at")
    if expiry <= now:
        raise ReportError("GitHub Linux artifact is expired")
    expected_url = (
        f"https://api.github.com/repos/{github_repository}/"
        f"actions/artifacts/{artifact_id}"
    )
    expected_archive_url = expected_url + "/zip"
    if (
        artifact.get("url") != expected_url
        or artifact.get("archive_download_url") != expected_archive_url
    ):
        raise ReportError("GitHub Linux artifact URL metadata mismatch")
    return {
        "id": artifact_id,
        "name": expected_name,
        "digest": digest,
        "sizeInBytes": size,
        "expiresAt": expires_at,
        "url": expected_url,
        "archiveDownloadUrl": expected_archive_url,
        "workflowRunId": int(github_run_id),
        "headSha": provenance.expected_head,
    }


def _download_github_artifact(
    binding: Mapping[str, Any],
    destination: Path,
    *,
    github_repository: str,
    runner: Callable[..., subprocess.CompletedProcess[Any]],
) -> None:
    artifact_id = binding["id"]
    argv = (
        "gh",
        "api",
        f"repos/{github_repository}/actions/artifacts/{artifact_id}/zip",
        "--method",
        "GET",
        "-H",
        "Accept: application/vnd.github+json",
    )
    try:
        if runner is subprocess.run:
            with destination.open("xb") as stream:
                completed = runner(
                    argv,
                    check=False,
                    stdout=stream,
                    stderr=subprocess.PIPE,
                    timeout=_GITHUB_API_TIMEOUT_SECONDS,
                )
        else:
            completed = runner(
                argv,
                check=False,
                capture_output=True,
                timeout=_GITHUB_API_TIMEOUT_SECONDS,
            )
            archive = completed.stdout
            if not isinstance(archive, bytes):
                raise ReportError("GitHub artifact download was not binary")
            if len(archive) > _MAX_GITHUB_ARTIFACT_BYTES:
                raise ReportError("GitHub artifact download exceeded size limit")
            with destination.open("xb") as stream:
                stream.write(archive)
                stream.flush()
                os.fsync(stream.fileno())
    except (OSError, subprocess.TimeoutExpired) as error:
        destination.unlink(missing_ok=True)
        raise ReportError(
            "GitHub artifact download failed or timed out"
        ) from error
    if completed.returncode != 0:
        destination.unlink(missing_ok=True)
        detail_value = completed.stderr or completed.stdout or b""
        detail = (
            detail_value.decode("utf-8", errors="replace")
            if isinstance(detail_value, bytes)
            else str(detail_value)
        ).strip()
        raise ReportError(
            "GitHub artifact download failed"
            + (f": {detail}" if detail else "")
        )
    if (
        not destination.is_file()
        or destination.stat().st_size != binding["sizeInBytes"]
        or destination.stat().st_size > _MAX_GITHUB_ARTIFACT_BYTES
    ):
        destination.unlink(missing_ok=True)
        raise ReportError("GitHub artifact downloaded size mismatch")
    archive_sha256 = _sha256(destination)
    if f"sha256:{archive_sha256}" != binding["digest"]:
        destination.unlink(missing_ok=True)
        raise ReportError("GitHub artifact downloaded digest mismatch")


def _extract_linux_artifact(archive_path: Path, destination: Path) -> None:
    destination.mkdir()
    try:
        with zipfile.ZipFile(archive_path) as bundle:
            infos = [info for info in bundle.infolist() if not info.is_dir()]
            names = [Path(info.filename).as_posix() for info in infos]
            if (
                len(infos) != 2
                or {Path(name).name for name in names}
                != {"pytest-linux.xml", "attestation.json"}
                or any(name != Path(name).name for name in names)
                or sum(info.file_size for info in infos)
                > _MAX_GITHUB_ARTIFACT_UNCOMPRESSED_BYTES
                or any(
                    Path(name).is_absolute()
                    or ".." in Path(name).parts
                    or info.flag_bits & 0x1
                    or stat.S_ISLNK(info.external_attr >> 16)
                    for name, info in zip(names, infos, strict=True)
                )
            ):
                raise ReportError("GitHub artifact ZIP layout is invalid")
            for info in infos:
                target = destination / Path(info.filename).name
                remaining = info.file_size
                with bundle.open(info) as source, target.open("xb") as stream:
                    while remaining:
                        chunk = source.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise ReportError(
                                "GitHub artifact ZIP member was truncated"
                            )
                        stream.write(chunk)
                        remaining -= len(chunk)
                    if source.read(1):
                        raise ReportError(
                            "GitHub artifact ZIP member exceeded declared size"
                        )
                    stream.flush()
                    os.fsync(stream.fileno())
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        if isinstance(error, ReportError):
            raise
        raise ReportError("GitHub artifact ZIP is malformed") from error


def accept_external_linux_evidence(
    evidence_dir: Path,
    report_root: Path,
    provenance: GitProvenance,
    *,
    local_run_id: str,
    local_started_at: str,
    github_repository: str,
    github_run_id: str,
    repo_root: Path | None = None,
    gh_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    now: datetime | None = None,
    offline_fixture_only: bool = False,
    artifact_binding: Mapping[str, Any] | None = None,
) -> ReportEnvelope:
    if artifact_binding is None and not offline_fixture_only:
        raise ReportError(
            "caller-provided Linux evidence is allowed only in offline fixture mode"
        )
    evidence_root = _canonical(evidence_dir)
    target_root = _canonical(report_root)
    if (
        not evidence_root.is_dir()
        or evidence_root.is_symlink()
        or evidence_root == target_root
    ):
        raise ReportError("external Linux evidence directory is invalid")
    if repo_root is not None and _inside(evidence_root, _canonical(repo_root)):
        raise ReportError("external Linux evidence directory must be repository-external")
    if not target_root.is_dir() or target_root.is_symlink():
        raise ReportError("external Linux target root is invalid")
    if repo_root is not None and _inside(target_root, _canonical(repo_root)):
        raise ReportError("external Linux target root must be repository-external")
    target = target_root / REPORT_FILENAMES["pytest-linux"]
    sidecar = target.with_name(target.name + ".provenance.json")
    if target.exists() or sidecar.exists():
        raise ReportError("external Linux evidence target already exists")
    entries = {entry.name for entry in evidence_root.iterdir()}
    if entries != {"pytest-linux.xml", "attestation.json"}:
        raise ReportError(
            "external Linux evidence directory must contain exactly "
            "pytest-linux.xml and attestation.json"
        )
    source_junit = evidence_root / "pytest-linux.xml"
    source_attestation = evidence_root / "attestation.json"
    _require_file(source_junit)
    _require_file(source_attestation)
    try:
        attestation = json.loads(source_attestation.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReportError("Linux attestation is malformed") from error
    if not isinstance(attestation, dict):
        raise ReportError("Linux attestation is malformed")
    accepted_now = now or _utc_now()
    _validate_linux_attestation(
        attestation,
        source_junit,
        provenance,
        github_repository=github_repository,
        github_run_id=github_run_id,
        now=accepted_now,
    )
    github_run = _verify_github_run(
        attestation,
        provenance,
        github_repository=github_repository,
        github_run_id=github_run_id,
        runner=gh_runner,
    )
    producer_started = _iso_utc()
    try:
        with source_junit.open("rb") as source, target.open("xb") as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
        if _sha256(target) != attestation["junitSha256"]:
            raise ReportError("copied Linux JUnit SHA-256 mismatch")
        producer_completed = _iso_utc()
        external_evidence: dict[str, Any] = {
            "mode": (
                "github-actions-downloaded"
                if artifact_binding is not None
                else "offline-fixture"
            ),
            "sourceEvidenceDir": str(evidence_root),
            "attestation": attestation,
            "githubRun": github_run,
        }
        if artifact_binding is not None:
            external_evidence["githubArtifact"] = dict(artifact_binding)
        payload = {
            "expectedHead": provenance.expected_head,
            "expectedTree": provenance.expected_tree,
            "runId": local_run_id,
            "startedAt": local_started_at,
            "producerStartedAt": producer_started,
            "producerCompletedAt": producer_completed,
            "label": "pytest-linux",
            "reportPath": str(target),
            "reportRoot": str(target_root),
            "externalEvidence": external_evidence,
        }
        _write_json_fsync(sidecar, payload)
    except Exception:
        target.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)
        raise
    return ReportEnvelope(
        label="pytest-linux",
        report_path=target,
        sidecar_path=sidecar,
        expected_head=provenance.expected_head,
        expected_tree=provenance.expected_tree,
        run_id=local_run_id,
        started_at=local_started_at,
        producer_started_at=producer_started,
        producer_completed_at=producer_completed,
        report_root=target_root,
        external_evidence=external_evidence,
    )


def fetch_github_linux_evidence(
    report_root: Path,
    provenance: GitProvenance,
    *,
    local_run_id: str,
    local_started_at: str,
    github_repository: str,
    github_run_id: str,
    repo_root: Path | None = None,
    gh_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    now: datetime | None = None,
) -> ReportEnvelope:
    accepted_now = now or _utc_now()
    target_root = _canonical(report_root)
    if not target_root.is_dir() or target_root.is_symlink():
        raise ReportError("GitHub Linux target root is invalid")
    binding = _github_artifact_binding(
        provenance,
        github_repository=github_repository,
        github_run_id=github_run_id,
        runner=gh_runner,
        now=accepted_now,
    )
    download_root = Path(
        tempfile.mkdtemp(prefix=".github-linux-artifact-", dir=target_root)
    ).resolve()
    archive_path = download_root / "artifact.zip"
    evidence_root = download_root / "extracted"
    try:
        _download_github_artifact(
            binding,
            archive_path,
            github_repository=github_repository,
            runner=gh_runner,
        )
        _extract_linux_artifact(archive_path, evidence_root)
        bound_artifact = {
            **binding,
            "archivePath": str(archive_path),
            "archiveSha256": _sha256(archive_path),
        }
        return accept_external_linux_evidence(
            evidence_root,
            target_root,
            provenance,
            local_run_id=local_run_id,
            local_started_at=local_started_at,
            github_repository=github_repository,
            github_run_id=github_run_id,
            repo_root=repo_root,
            gh_runner=gh_runner,
            now=accepted_now,
            artifact_binding=bound_artifact,
        )
    except Exception:
        shutil.rmtree(download_root, ignore_errors=True)
        raise


def _validate_sidecar_external_evidence(
    value: Any,
    report_path: Path,
    provenance: GitProvenance,
    *,
    now: datetime,
) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "mode",
        "sourceEvidenceDir",
        "attestation",
        "githubRun",
        "githubArtifact",
    }:
        raise ReportError("external Linux sidecar evidence schema mismatch")
    if value.get("mode") != "github-actions-downloaded":
        raise ReportError("external Linux sidecar evidence mode mismatch")
    attestation = value.get("attestation")
    github_run = value.get("githubRun")
    artifact = value.get("githubArtifact")
    if not isinstance(attestation, dict) or set(attestation) != _LINUX_ATTESTATION_FIELDS:
        raise ReportError("external Linux sidecar attestation schema mismatch")
    if not isinstance(github_run, dict) or set(github_run) != {
        "id",
        "repository",
        "headSha",
        "headTree",
        "status",
        "conclusion",
        "event",
        "workflow",
        "workflowName",
        "runAttempt",
        "htmlUrl",
    }:
        raise ReportError("external Linux sidecar GitHub run schema mismatch")
    if not isinstance(artifact, dict) or set(artifact) != {
        "id",
        "name",
        "digest",
        "sizeInBytes",
        "expiresAt",
        "url",
        "archiveDownloadUrl",
        "workflowRunId",
        "headSha",
        "archivePath",
        "archiveSha256",
    }:
        raise ReportError("external Linux sidecar GitHub artifact schema mismatch")
    expected_attestation = {
        "schemaVersion": LINUX_EVIDENCE_SCHEMA,
        "repository": GITHUB_REPOSITORY,
        "workflow": PHASE5_LINUX_WORKFLOW,
        "expectedHead": provenance.expected_head,
        "expectedTree": provenance.expected_tree,
        "runnerOS": "Linux",
        "pytestCommand": LINUX_REPORT_PYTEST_COMMAND,
        "pytestMarker": LINUX_REPORT_MARKER,
        "nativeMarkerCommand": LINUX_NATIVE_PYTEST_COMMAND,
        "nativeMarker": LINUX_NATIVE_MARKER,
    }
    for field, expected in expected_attestation.items():
        if attestation.get(field) != expected:
            raise ReportError(f"external Linux sidecar {field} mismatch")
    completed = _parse_utc(attestation.get("completedAt"), "completedAt")
    if (
        completed > now + timedelta(minutes=5)
        or now - completed > _MAX_ATTESTATION_AGE
    ):
        raise ReportError("external Linux sidecar attestation is stale")
    if _sha256(report_path) != attestation.get("junitSha256"):
        raise ReportError("external Linux sidecar JUnit SHA-256 mismatch")
    expected_run = {
        "id": int(attestation["githubRunId"]),
        "repository": GITHUB_REPOSITORY,
        "headSha": provenance.expected_head,
        "headTree": provenance.expected_tree,
        "status": "completed",
        "conclusion": "success",
        "workflowName": PHASE5_LINUX_WORKFLOW_NAME,
        "runAttempt": attestation["githubRunAttempt"],
    }
    for field, expected in expected_run.items():
        if github_run.get(field) != expected:
            raise ReportError(f"external Linux sidecar GitHub run {field} mismatch")
    if github_run.get("event") not in PHASE5_LINUX_WORKFLOW_EVENTS:
        raise ReportError("external Linux sidecar GitHub run event mismatch")
    workflow = github_run.get("workflow")
    if not isinstance(workflow, str) or not (
        workflow == PHASE5_LINUX_WORKFLOW
        or workflow.startswith(PHASE5_LINUX_WORKFLOW + "@")
    ):
        raise ReportError("external Linux sidecar GitHub run workflow mismatch")
    archive_path = Path(str(artifact.get("archivePath", ""))).resolve()
    source_root = Path(str(value.get("sourceEvidenceDir", ""))).resolve()
    expected_artifact = {
        "name": attestation["artifactName"],
        "digest": f"sha256:{artifact.get('archiveSha256')}",
        "workflowRunId": int(attestation["githubRunId"]),
        "headSha": provenance.expected_head,
    }
    for field, expected in expected_artifact.items():
        if artifact.get(field) != expected:
            raise ReportError(
                f"external Linux sidecar GitHub artifact {field} mismatch"
            )
    if (
        not isinstance(artifact.get("id"), int)
        or isinstance(artifact.get("id"), bool)
        or artifact["id"] <= 0
        or not isinstance(artifact.get("sizeInBytes"), int)
        or artifact["sizeInBytes"] <= 0
        or archive_path.parent != source_root.parent
        or not archive_path.is_file()
        or archive_path.stat().st_size != artifact["sizeInBytes"]
        or _sha256(archive_path) != artifact["archiveSha256"]
        or _parse_utc(artifact.get("expiresAt"), "artifact expiresAt") <= now
    ):
        raise ReportError("external Linux sidecar GitHub artifact binding mismatch")
    return value


def validate_report_envelopes(
    report_paths: Mapping[str, Path],
    report_root: Path,
    provenance: GitProvenance,
    *,
    run_id: str,
    started_at: str,
    repo_root: Path | None = None,
) -> tuple[ReportEnvelope, ...]:
    if set(report_paths) != set(REPORT_LABELS):
        raise ReportError("provenance requires exactly four labeled reports")
    try:
        parsed_run_id = uuid.UUID(run_id)
    except (ValueError, AttributeError) as error:
        raise ReportError("provenance runId is malformed") from error
    if str(parsed_run_id) != run_id:
        raise ReportError("provenance runId is not canonical")
    root = _canonical(report_root)
    if not root.is_dir() or root.is_symlink():
        raise ReportError("canonical report root is missing or invalid")
    if repo_root is not None and _inside(root, _canonical(repo_root)):
        raise ReportError("canonical report root must be repository-external")
    run_started = _parse_utc(started_at, "startedAt")
    now = _utc_now()
    envelopes: list[ReportEnvelope] = []
    prior_started: datetime | None = None
    prior_completed: datetime | None = None

    for label in REPORT_LABELS:
        report = _canonical(report_paths[label])
        expected_report = root / REPORT_FILENAMES[label]
        if report != expected_report or not _inside(report, root):
            raise ReportError(f"report path is not canonical under report root: {report}")
        _require_file(report)
        sidecar = report.with_name(report.name + ".provenance.json")
        _require_file(sidecar)
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ReportError(f"provenance sidecar is malformed: {sidecar}") from error
        expected_sidecar_fields = _BASE_SIDECAR_FIELDS
        if label == "pytest-linux" and isinstance(payload, dict) and "externalEvidence" in payload:
            expected_sidecar_fields = _BASE_SIDECAR_FIELDS | {"externalEvidence"}
        if not isinstance(payload, dict) or set(payload) != expected_sidecar_fields:
            raise ReportError(f"provenance sidecar schema mismatch: {sidecar}")
        expected_fields = {
            "expectedHead": provenance.expected_head,
            "expectedTree": provenance.expected_tree,
            "runId": run_id,
            "startedAt": started_at,
            "label": label,
            "reportPath": str(report),
            "reportRoot": str(root),
        }
        for field, expected in expected_fields.items():
            if payload.get(field) != expected:
                raise ReportError(
                    f"provenance {field} mismatch for label {label}"
                )
        producer_started = _parse_utc(
            payload["producerStartedAt"], "producerStartedAt"
        )
        producer_completed = _parse_utc(
            payload["producerCompletedAt"], "producerCompletedAt"
        )
        if not (run_started <= producer_started <= producer_completed <= now + timedelta(minutes=5)):
            raise ReportError(f"provenance timestamps are invalid for label {label}")
        if prior_started is not None and producer_started < prior_started:
            raise ReportError("provenance producer timestamps are not ordered")
        if prior_completed is not None and producer_completed < prior_completed:
            raise ReportError("provenance producer timestamps are not ordered")
        prior_started = producer_started
        prior_completed = producer_completed
        report_modified = datetime.fromtimestamp(
            report.stat().st_mtime, tz=UTC
        )
        if not (
            producer_started - timedelta(seconds=5)
            <= report_modified
            <= producer_completed + timedelta(seconds=5)
        ):
            raise ReportError(f"report is stale for provenance label {label}")
        external_evidence = None
        if "externalEvidence" in payload:
            if label != "pytest-linux":
                raise ReportError("external evidence is allowed only for pytest-linux")
            external_evidence = _validate_sidecar_external_evidence(
                payload["externalEvidence"],
                report,
                provenance,
                now=now,
            )
        envelopes.append(
            ReportEnvelope(
                label=label,
                report_path=report,
                sidecar_path=sidecar,
                expected_head=provenance.expected_head,
                expected_tree=provenance.expected_tree,
                run_id=run_id,
                started_at=started_at,
                producer_started_at=payload["producerStartedAt"],
                producer_completed_at=payload["producerCompletedAt"],
                report_root=root,
                external_evidence=external_evidence,
            )
        )
    return tuple(envelopes)


def _pytest_nodes(path: Path, label: str | None = None) -> ReportStats:
    _require_file(path)
    try:
        root = ElementTree.parse(path).getroot()
    except (ElementTree.ParseError, OSError) as error:
        raise ReportError("pytest JUnit report is malformed") from error
    discovered = 0
    passed = 0
    nodes: list[str] = []
    for case in root.iter("testcase"):
        classname = case.get("classname")
        name = case.get("name")
        if not classname or not name:
            raise ReportError("pytest JUnit testcase identity is malformed")
        identity = f"pytest:{classname}::{name}"
        discovered += 1
        child_tags = {child.tag for child in list(case)}
        if child_tags & {"failure", "error", "skipped"}:
            raise ReportError(f"pytest testcase did not pass: {classname}::{name}")
        passed += 1
        nodes.append(identity)
    if discovered == 0:
        raise ReportError("pytest JUnit report contains no testcases")
    if discovered != passed:
        raise ReportError(
            f"pytest discovered ({discovered}) != passed ({passed}) in {path}"
        )
    return ReportStats(
        kind="pytest",
        path=str(path),
        discovered=discovered,
        passed=passed,
        nodes=tuple(nodes),
        label=label,
    )


def _playwright_result_ok(results: list[Any]) -> None:
    if not isinstance(results, list) or not results:
        raise ReportError("Playwright testcase has no results")
    if len(results) != 1:
        raise ReportError("Playwright testcase retried, skipped, or has invalid results")
    result = results[0]
    if not isinstance(result, dict):
        raise ReportError("Playwright result entry is malformed")
    if result.get("status") != "passed":
        raise ReportError(
            f"Playwright testcase did not pass (status={result.get('status')!r})"
        )
    retry = result.get("retry")
    if isinstance(retry, int) and retry != 0:
        raise ReportError("Playwright testcase was retried")
    if result.get("error") or result.get("errors"):
        raise ReportError("Playwright testcase carries an error payload")


def _playwright_nodes(path: Path, label: str | None = None) -> ReportStats:
    _require_file(path)
    raw = ""
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            if start < 0 or end <= start:
                raise error
            payload = json.loads(raw[start : end + 1])
        except Exception as nested:
            raise ReportError("Playwright JSON report is malformed") from nested
    if not isinstance(payload, dict) or payload.get("errors") not in (None, []):
        raise ReportError("Playwright JSON report is malformed or carries errors")

    expected_project = {
        "playwright-fixture": "desktop-chromium",
        "playwright-real-host": "phase5-shadow-real-host",
    }.get(label)
    discovered = 0
    passed = 0
    nodes: list[str] = []

    def walk(value: Any, file_hint: str | None = None) -> None:
        nonlocal discovered, passed
        if isinstance(value, list):
            for item in value:
                walk(item, file_hint)
            return
        if not isinstance(value, dict):
            return
        current_file = value.get("file")
        if not isinstance(current_file, str) or not current_file:
            current_file = file_hint
        title = value.get("title")
        tests = value.get("tests")
        if isinstance(tests, list):
            if not isinstance(title, str) or not title or not current_file:
                raise ReportError("Playwright testcase identity is malformed")
            if value.get("ok") is False:
                raise ReportError("Playwright spec did not pass")
            for test in tests:
                if not isinstance(test, dict):
                    raise ReportError("Playwright test entry is malformed")
                discovered += 1
                expected = test.get("expectedStatus")
                if expected not in (None, "passed", "expected"):
                    raise ReportError(
                        f"Playwright testcase expectedStatus is not passed ({expected!r})"
                    )
                project_name = test.get("projectName")
                if expected_project and project_name != expected_project:
                    raise ReportError(
                        f"Playwright report target mismatch for {label}: {project_name!r}"
                    )
                status = test.get("status")
                if status in _PLAYWRIGHT_NON_PASS or (
                    isinstance(status, str)
                    and status not in ("expected", "passed")
                ):
                    raise ReportError(
                        f"Playwright testcase did not pass (status={status!r})"
                    )
                _playwright_result_ok(
                    test.get("results") if isinstance(test.get("results"), list) else []
                )
                outcome = test.get("outcome")
                if isinstance(outcome, str) and outcome not in ("expected", "passed"):
                    raise ReportError(
                        f"Playwright testcase outcome is not clean pass ({outcome!r})"
                    )
                passed += 1
                normalized_file = current_file.replace("\\", "/")
                nodes.append(f"playwright:{normalized_file}::{title}")
        for key in ("suites", "specs"):
            child = value.get(key)
            if isinstance(child, list):
                walk(child, current_file)

    walk(payload)
    if discovered == 0:
        raise ReportError("Playwright JSON report contains no passed tests")
    if discovered != passed:
        raise ReportError(
            f"playwright discovered ({discovered}) != passed ({passed}) in {path}"
        )
    return ReportStats(
        kind="playwright",
        path=str(path),
        discovered=discovered,
        passed=passed,
        nodes=tuple(nodes),
        label=label,
    )


def _collect(
    pytest_junit: Path, playwright_reports: Iterable[Path]
) -> tuple[list[str], list[ReportStats]]:
    stats = [_pytest_nodes(pytest_junit)]
    nodes = list(stats[0].nodes)
    for report in playwright_reports:
        parsed = _playwright_nodes(report)
        stats.append(parsed)
        nodes.extend(parsed.nodes)
    return nodes, stats


def verify(pytest_junit: Path, playwright_reports: list[Path]) -> dict[str, Any]:
    """Historical unlabeled parser retained for 05-29 compatibility."""
    if not playwright_reports:
        raise ReportError("at least one Playwright JSON report is required")
    nodes, stats = _collect(pytest_junit, playwright_reports)
    if len(nodes) != len(set(nodes)):
        raise ReportError("machine reports contain duplicate normalized test identities")
    total_discovered = sum(item.discovered for item in stats)
    total_passed = sum(item.passed for item in stats)
    if total_discovered != total_passed:
        raise ReportError(
            f"aggregate discovered ({total_discovered}) != passed ({total_passed})"
        )
    matches: dict[str, str] = {}
    claimed: set[str] = set()
    for finding, (kind, needle) in REQUIRED_NODES.items():
        candidates = [
            node for node in nodes if node.startswith(f"{kind}:") and needle in node
        ]
        if len(candidates) != 1:
            raise ReportError(
                f"{finding} must match exactly one passed node, found {len(candidates)}"
            )
        if candidates[0] in claimed:
            raise ReportError(
                "machine-report node is assigned to more than one finding: "
                f"{candidates[0]}"
            )
        claimed.add(candidates[0])
        matches[finding] = candidates[0]
    return {
        "status": "passed",
        "discovered": total_discovered,
        "passed": total_passed,
        "reports": [
            {
                "kind": item.kind,
                "path": item.path,
                "discovered": item.discovered,
                "passed": item.passed,
            }
            for item in stats
        ],
        "matches": matches,
    }


def verify_report_envelopes(
    envelopes: Sequence[ReportEnvelope],
) -> dict[str, Any]:
    if tuple(envelope.label for envelope in envelopes) != REPORT_LABELS:
        raise ReportError("parser requires exactly four reports in canonical label order")
    stats: list[ReportStats] = []
    qualified_nodes: list[str] = []
    for envelope in envelopes:
        if envelope.label.startswith("pytest-"):
            parsed = _pytest_nodes(envelope.report_path, envelope.label)
        else:
            parsed = _playwright_nodes(envelope.report_path, envelope.label)
        stats.append(parsed)
        label_nodes = [f"{envelope.label}:{node}" for node in parsed.nodes]
        if len(label_nodes) != len(set(label_nodes)):
            raise ReportError(
                f"machine report {envelope.label} contains duplicate normalized identities"
            )
        qualified_nodes.extend(label_nodes)
    if len(qualified_nodes) != len(set(qualified_nodes)):
        raise ReportError("machine reports contain duplicate report-qualified identities")
    total_discovered = sum(item.discovered for item in stats)
    total_passed = sum(item.passed for item in stats)
    if total_discovered != total_passed:
        raise ReportError(
            f"aggregate discovered ({total_discovered}) != passed ({total_passed})"
        )
    matches: dict[str, str] = {}
    claimed: set[str] = set()
    for finding, (label, _kind, identity) in REQUIRED_REPORT_NODES.items():
        expected = f"{label}:{identity}"
        candidates = [node for node in qualified_nodes if node == expected]
        if len(candidates) != 1:
            raise ReportError(
                f"{finding} must match exactly one passed report-qualified node, "
                f"found {len(candidates)}"
            )
        if expected in claimed:
            raise ReportError(
                f"machine-report node is assigned to more than one finding: {expected}"
            )
        claimed.add(expected)
        matches[finding] = expected
    first = envelopes[0]
    return {
        "status": "passed",
        "expectedHead": first.expected_head,
        "expectedTree": first.expected_tree,
        "runId": first.run_id,
        "startedAt": first.started_at,
        "discovered": total_discovered,
        "passed": total_passed,
        "reports": [
            {
                "label": item.label,
                "kind": item.kind,
                "path": item.path,
                "discovered": item.discovered,
                "passed": item.passed,
            }
            for item in stats
        ],
        "matches": matches,
    }


def _replace_line_once(
    lines: list[str],
    predicate: Callable[[str], bool],
    transform: Callable[[str], str],
    description: str,
) -> None:
    indexes = [index for index, line in enumerate(lines) if predicate(line)]
    if len(indexes) != 1:
        raise ReportError(
            f"validation pending token mismatch for {description}: found {len(indexes)}"
        )
    index = indexes[0]
    lines[index] = transform(lines[index])


def build_scoped_validation_candidate(
    original: str,
    *,
    provenance: GitProvenance,
    run_id: str,
    started_at: str,
    report_root: Path,
    report_paths: Mapping[str, Path],
) -> str:
    if set(report_paths) != set(REPORT_LABELS):
        raise ReportError("scoped updater requires exactly four report paths")
    lines = original.splitlines(keepends=True)
    _replace_line_once(
        lines,
        lambda line: line.rstrip("\r\n") == "r43_wave15_status: pending",
        lambda line: line.replace("pending", "passed", 1),
        "r43_wave15_status",
    )
    for task_id in _SCOPED_TASKS:
        _replace_line_once(
            lines,
            lambda line, task_id=task_id: line.startswith(f"| {task_id} |")
            and "⬜ pending" in line,
            lambda line: line.replace("⬜ pending", "✅ passed", 1),
            task_id,
        )
    for finding in _R43_FINDINGS:
        _replace_line_once(
            lines,
            lambda line, finding=finding: line.startswith(f"| {finding} |")
            and "| ⬜ pending | 05-44 Task 2 same-run parser |" in line,
            lambda line: line.replace("| ⬜ pending |", "| ✅ passed |", 1),
            f"{finding} current evidence",
        )
    for label in REPORT_LABELS:
        report_reference = str(_canonical(report_paths[label]))
        _replace_line_once(
            lines,
            lambda line, label=label: line.startswith(f"| {label} |")
            and line.rstrip("\r\n").endswith("| ⬜ pending |"),
            lambda line, report_reference=report_reference: line.replace(
                "⬜ pending",
                f"✅ passed — `{report_reference}` / run `{run_id}`",
                1,
            ),
            f"{label} current report",
        )

    heading = next(
        (
            index
            for index, line in enumerate(lines)
            if line.rstrip("\r\n") == "### R43 / Wave 15 Gap Closure Sign-Off"
        ),
        None,
    )
    approval = next(
        (
            index
            for index, line in enumerate(lines)
            if line.startswith("**R43 / Wave 15 scoped approval:** pending")
        ),
        None,
    )
    if heading is None or approval is None or approval <= heading:
        raise ReportError("R43/Wave 15 scoped approval section is malformed")
    checkbox_indexes = [
        index
        for index in range(heading + 1, approval)
        if lines[index].startswith("- [ ] ")
    ]
    if len(checkbox_indexes) != 7:
        raise ReportError(
            "validation pending token mismatch for scoped approval checkboxes"
        )
    for index in checkbox_indexes:
        lines[index] = lines[index].replace("- [ ] ", "- [x] ", 1)
    root_reference = str(_canonical(report_root))
    approval_text = (
        "**R43 / Wave 15 scoped approval:** passed — "
        f"run `{run_id}`, expectedHead `{provenance.expected_head}`, "
        f"expectedTree `{provenance.expected_tree}`, startedAt `{started_at}`, "
        f"report root `{root_reference}`. Global/historical state, 05-28 and "
        "05-40 remain unchanged."
    )
    newline = "\n" if lines[approval].endswith("\n") else ""
    lines[approval] = approval_text + newline
    candidate = "".join(lines)
    validate_scoped_validation_candidate(original, candidate)
    return candidate


def _allowed_scoped_line(line: str, *, in_signoff: bool) -> bool:
    if line.rstrip("\r\n") == "r43_wave15_status: pending":
        return True
    if any(
        line.startswith(f"| {task_id} |") and "⬜ pending" in line
        for task_id in _SCOPED_TASKS
    ):
        return True
    if any(
        line.startswith(f"| {finding} |")
        and "| ⬜ pending | 05-44 Task 2 same-run parser |" in line
        for finding in _R43_FINDINGS
    ):
        return True
    if any(
        line.startswith(f"| {label} |")
        and line.rstrip("\r\n").endswith("| ⬜ pending |")
        for label in REPORT_LABELS
    ):
        return True
    if in_signoff and line.startswith("- [ ] "):
        return True
    return line.startswith("**R43 / Wave 15 scoped approval:** pending")


def validate_scoped_validation_candidate(original: str, candidate: str) -> None:
    original_lines = original.splitlines()
    candidate_lines = candidate.splitlines()
    if len(original_lines) != len(candidate_lines):
        raise ReportError("scoped validation allowlist rejects line insertion/deletion")
    try:
        heading = original_lines.index("### R43 / Wave 15 Gap Closure Sign-Off")
        approval = next(
            index
            for index, line in enumerate(original_lines)
            if line.startswith("**R43 / Wave 15 scoped approval:** pending")
        )
    except (ValueError, StopIteration) as error:
        raise ReportError("scoped validation approval section is malformed") from error
    changed = [
        index
        for index, (before, after) in enumerate(
            zip(original_lines, candidate_lines, strict=True)
        )
        if before != after
    ]
    for index in changed:
        if not _allowed_scoped_line(
            original_lines[index], in_signoff=heading < index < approval
        ):
            raise ReportError(
                f"scoped validation allowlist rejects line {index + 1}"
            )
    if len(changed) != 22:
        raise ReportError(
            f"scoped validation partial transition: expected 22 lines, found {len(changed)}"
        )

    original_global_status = next(
        (line for line in original_lines if line.startswith("status: ")), None
    )
    candidate_global_status = next(
        (line for line in candidate_lines if line.startswith("status: ")), None
    )
    if original_global_status not in {"status: pending", "status: validated"}:
        raise ReportError("scoped validation global status is unsupported")
    if candidate_global_status != original_global_status:
        raise ReportError("scoped validation global status must remain unchanged")
    if candidate_lines.count("r43_wave15_status: passed") != 1:
        raise ReportError("scoped validation partial r43_wave15_status transition")
    for task_id in _SCOPED_TASKS:
        rows = [
            line for line in candidate_lines if line.startswith(f"| {task_id} |")
        ]
        if len(rows) != 1 or "✅ passed" not in rows[0]:
            raise ReportError(f"scoped validation partial transition for {task_id}")
    for finding in _R43_FINDINGS:
        rows = [
            line
            for line in candidate_lines
            if line.startswith(f"| {finding} |")
            and "05-44 Task 2 same-run parser" in line
        ]
        if len(rows) != 1 or "| ✅ passed |" not in rows[0]:
            raise ReportError(f"scoped validation partial transition for {finding}")
    for label in REPORT_LABELS:
        rows = [
            line for line in candidate_lines if line.startswith(f"| {label} |")
        ]
        if len(rows) != 1 or "✅ passed" not in rows[0]:
            raise ReportError(f"scoped validation partial transition for {label}")
    scoped = candidate_lines[heading + 1 : approval]
    if sum(line.startswith("- [x] ") for line in scoped) != 7 or any(
        line.startswith("- [ ] ") for line in scoped
    ):
        raise ReportError("scoped validation partial approval transition")
    if not candidate_lines[approval].startswith(
        "**R43 / Wave 15 scoped approval:** passed"
    ):
        raise ReportError("scoped validation partial approval transition")


def atomic_replace_validation(path: Path, candidate: str) -> None:
    path = _canonical(path)
    original = path.read_text(encoding="utf-8")
    validate_scoped_validation_candidate(original, candidate)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(candidate)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _resolve_wsl_path(path: Path) -> str:
    argv = ["wsl.exe", "--exec", "wslpath", "-a", str(_canonical(path))]
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-16-le",
            errors="replace",
            timeout=_WSL_PREFLIGHT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReportError("WSL/Linux producer environment is unavailable") from error
    if completed.returncode != 0 or not completed.stdout.strip():
        detail = (completed.stderr or completed.stdout or "").strip()
        raise ReportError(
            "WSL/Linux producer environment is unavailable"
            + (f": {detail}" if detail else "")
        )
    return completed.stdout.strip().splitlines()[-1]


def orchestrate(
    repo_root: Path,
    validation_path: Path,
    phase43_summary: Path,
    plan_path: Path,
    *,
    linux_evidence_dir: Path | None = None,
    github_run_id: str | None = None,
    github_repository: str = GITHUB_REPOSITORY,
    update_validation: bool = True,
    gh_runner: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
) -> dict[str, Any]:
    repo_root = _canonical(repo_root)
    validation_path = _canonical_from_repo(validation_path, repo_root)
    phase43_summary = _canonical_from_repo(phase43_summary, repo_root)
    plan_path = _canonical_from_repo(plan_path, repo_root)
    phase05_dir = _find_phase05_dir(repo_root)
    expected_plan = (phase05_dir / "05-44-PLAN.md").resolve()
    if plan_path != expected_plan or not plan_path.is_file():
        raise ReportError("05-44 plan path is missing or not canonical")
    expected_validation = (phase05_dir / "05-VALIDATION.md").resolve()
    if validation_path != expected_validation or not validation_path.is_file():
        raise ReportError("05-VALIDATION path is missing or not canonical")
    if linux_evidence_dir is not None:
        raise ReportError(
            "caller-provided Linux evidence is not accepted by orchestrate"
        )
    if github_repository != GITHUB_REPOSITORY:
        raise ReportError(
            f"GitHub repository must be exactly {GITHUB_REPOSITORY}"
        )

    # Preflight freezes the exact committed tree before any producer.
    provenance = capture_git_provenance(repo_root, phase43_summary)
    run_id = str(uuid.uuid4())
    started_at = _iso_utc()
    report_root = (
        Path(tempfile.gettempdir()) / f"athena-phase5-44-{run_id}"
    ).resolve()
    if report_root.exists() or _inside(report_root, repo_root):
        raise ReportError("external GUID report root already exists or is not external")
    report_root.mkdir(parents=True)

    if github_run_id is None:
        if os.name == "nt":
            try:
                linux_repo_root = _resolve_wsl_path(repo_root)
                linux_report_root = _resolve_wsl_path(report_root)
            except ReportError as error:
                raise ReportError(
                    f"{error}; install WSL or pass --github-run-id to use "
                    f"CI-sourced evidence; runId={run_id}; "
                    f"reportRoot={report_root}; "
                    f"expectedHead={provenance.expected_head}; "
                    f"expectedTree={provenance.expected_tree}"
                ) from error
            linux_native = False
        else:
            linux_repo_root = str(repo_root)
            linux_report_root = str(report_root)
            linux_native = True
    else:
        linux_repo_root = "/external-evidence-not-executed"
        linux_report_root = "/external-evidence-not-executed"
        linux_native = False

    specs = build_producer_specs(
        repo_root,
        report_root,
        linux_repo_root=linux_repo_root,
        linux_report_root=linux_report_root,
        linux_native=linux_native,
    )
    run_producer(
        specs[0],
        provenance,
        run_id=run_id,
        started_at=started_at,
    )
    if github_run_id is None:
        run_producer(
            specs[1],
            provenance,
            run_id=run_id,
            started_at=started_at,
        )
    else:
        fetch_github_linux_evidence(
            report_root,
            provenance,
            local_run_id=run_id,
            local_started_at=started_at,
            github_repository=github_repository,
            github_run_id=github_run_id,
            repo_root=repo_root,
            gh_runner=gh_runner,
        )
    for spec in specs[2:]:
        run_producer(
            spec,
            provenance,
            run_id=run_id,
            started_at=started_at,
        )
    report_paths = {spec.label: spec.report_path for spec in specs}
    envelopes = validate_report_envelopes(
        report_paths,
        report_root,
        provenance,
        run_id=run_id,
        started_at=started_at,
        repo_root=repo_root,
    )

    # The parser receives only same-run reports from the still-frozen tree.
    assert_git_provenance(repo_root, provenance)
    verdict = verify_report_envelopes(envelopes)
    verdict_path = report_root / "parser-verdict.json"
    _write_json_fsync(verdict_path, verdict)
    validation_updated = False
    if update_validation:
        original = validation_path.read_text(encoding="utf-8")
        candidate = build_scoped_validation_candidate(
            original,
            provenance=provenance,
            run_id=run_id,
            started_at=started_at,
            report_root=report_root,
            report_paths=report_paths,
        )

        # Final static/postflight assertion. os.replace below is the last mutation.
        assert_git_provenance(repo_root, provenance)
        atomic_replace_validation(validation_path, candidate)
        validation_updated = True
    else:
        assert_git_provenance(repo_root, provenance)
    return {
        **verdict,
        "phase43Commit": provenance.phase43_commit,
        "reportRoot": str(report_root),
        "verdictPath": str(verdict_path),
        "validationUpdated": validation_updated,
    }


def _legacy_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-junit", required=True, type=Path)
    parser.add_argument(
        "--playwright-json",
        required=True,
        type=Path,
        action="append",
        help="Playwright JSON report path (repeatable)",
    )
    args = parser.parse_args(argv)
    result = verify(args.pytest_junit, args.playwright_json)
    print(json.dumps(result, sort_keys=True))
    return 0


def _orchestrate_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--validation-path", required=True, type=Path)
    parser.add_argument("--phase43-summary", required=True, type=Path)
    parser.add_argument("--plan-path", required=True, type=Path)
    parser.add_argument(
        "--evidence-only",
        action="store_true",
        help="regenerate and verify the evidence bundle without rewriting validation history",
    )
    parser.add_argument(
        "--github-run-id",
        help=(
            "optional: successful exact GitHub Actions run whose bound "
            "artifact is downloaded as CI-sourced evidence; omit for local "
            "execution (native Linux or WSL on Windows)"
        ),
    )
    parser.add_argument(
        "--github-repository",
        default=GITHUB_REPOSITORY,
        help=f"must be exactly {GITHUB_REPOSITORY}",
    )
    args = parser.parse_args(argv)
    result = orchestrate(
        args.repo_root,
        args.validation_path,
        args.phase43_summary,
        args.plan_path,
        github_run_id=args.github_run_id,
        github_repository=args.github_repository,
        update_validation=not args.evidence_only,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        if arguments and arguments[0] == "orchestrate":
            return _orchestrate_main(arguments[1:])
        return _legacy_main(arguments)
    except ReportError as error:
        print(f"Phase 05 final gate rejected: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
