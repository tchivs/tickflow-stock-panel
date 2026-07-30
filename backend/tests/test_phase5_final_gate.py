"""Synthetic contracts for scripts/verify_phase5_final_gate.py."""
from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import scripts.verify_phase5_final_gate as final_gate
from scripts.verify_phase5_final_gate import (
    GITHUB_REPOSITORY,
    LINUX_EVIDENCE_SCHEMA,
    LINUX_NATIVE_MARKER,
    LINUX_NATIVE_PYTEST_COMMAND,
    LINUX_REPORT_MARKER,
    LINUX_REPORT_PYTEST_COMMAND,
    PHASE5_LINUX_WORKFLOW,
    PHASE5_LINUX_WORKFLOW_NAME,
    RELEVANT_PATHS,
    REPORT_FILENAMES,
    REPORT_LABELS,
    REQUIRED_NODES,
    REQUIRED_REPORT_NODES,
    GitProvenance,
    ReportError,
    _resolve_wsl_path,
    accept_external_linux_evidence,
    assert_git_provenance,
    atomic_replace_validation,
    build_producer_specs,
    build_scoped_validation_candidate,
    capture_git_provenance,
    fetch_github_linux_evidence,
    main,
    run_producer,
    validate_report_envelopes,
    validate_scoped_validation_candidate,
    verify,
    verify_report_envelopes,
)


def _junit(cases: list[tuple[str, str, str | None]]) -> str:
    """cases: (classname, name, bad_tag|None) where bad_tag in failure/error/skipped."""
    parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<testsuites>',
        f'<testsuite name="pytest" tests="{len(cases)}" failures="0" errors="0" skipped="0">',
    ]
    for classname, name, bad in cases:
        parts.append(f'<testcase classname="{classname}" name="{name}" time="0.01">')
        if bad == "failure":
            parts.append('<failure message="boom">boom</failure>')
        elif bad == "error":
            parts.append('<error message="err">err</error>')
        elif bad == "skipped":
            parts.append('<skipped message="skip">skip</skipped>')
        parts.append("</testcase>")
    parts.append("</testsuite></testsuites>")
    return "\n".join(parts)


def _pw_report(*titles: str, status: str = "passed", results: int = 1, outcome: str = "expected") -> dict:
    """Minimal Playwright 1.x JSON reporter shape with one suite/spec per title."""
    specs = []
    for title in titles:
        result_list = [
            {"status": status if status != "flaky" else "passed", "retry": 0 if results == 1 else 1}
            for _ in range(results)
        ]
        if status == "failed":
            result_list = [{"status": "failed", "retry": 0, "error": {"message": "x"}}]
        if status == "skipped":
            result_list = [{"status": "skipped", "retry": 0}]
        if status == "timedOut":
            result_list = [{"status": "timedOut", "retry": 0}]
        if status == "interrupted":
            result_list = [{"status": "interrupted", "retry": 0}]
        if results == 2:
            result_list = [
                {"status": "failed", "retry": 0, "error": {"message": "x"}},
                {"status": "passed", "retry": 1},
            ]
        specs.append(
            {
                "title": title,
                "ok": status == "passed" and results == 1,
                "tests": [
                    {
                        "timeout": 30_000,
                        "expectedStatus": "passed",
                        "projectName": "desktop-chromium",
                        "results": result_list,
                        "status": "expected" if status == "passed" and results == 1 else status,
                        "outcome": outcome if results == 1 and status == "passed" else (
                            "flaky" if results == 2 else "unexpected"
                        ),
                    }
                ],
            }
        )
    return {
        "config": {},
        "suites": [
            {
                "title": "e2e/phase5-optional-enhancements.spec.ts",
                "file": "e2e/phase5-optional-enhancements.spec.ts",
                "specs": specs,
                "suites": [],
            }
        ],
        "errors": [],
    }


def _green_bundle(tmp_path: Path) -> tuple[Path, list[Path]]:
    """One pytest JUnit + two Playwright reports covering every CR/WR once."""
    pytest_cases: list[tuple[str, str, str | None]] = []
    for _finding, (kind, needle) in REQUIRED_NODES.items():
        if kind != "pytest":
            continue
        # classname mirrors real pytest junit (tests.forecast.test_calibration)
        if "calibration" in needle:
            cls = "tests.forecast.test_calibration"
        elif "test_api" in needle or "cross_principal" in needle:
            cls = "tests.forecast.test_api"
        elif "runner" in needle or "cr05" in needle or "cr06" in needle or "wr01" in needle:
            cls = "tests.forecast.test_runner"
        elif "optional_host" in needle or "cr07" in needle:
            cls = "tests.test_phase5_optional_host"
        elif "foundation" in needle or "wr02" in needle:
            cls = "tests.test_phase5_foundation"
        else:
            cls = "tests.misc"
        pytest_cases.append((cls, needle, None))
    # filler backend nodes so discovered>required
    pytest_cases.append(("tests.shadow.test_x", "test_shadow_ok", None))

    junit = tmp_path / "pytest.xml"
    junit.write_text(_junit(pytest_cases), encoding="utf-8")

    fixture_titles = [
        REQUIRED_NODES["CR-04"][1],
        REQUIRED_NODES["WR-03"][1],
        "Shadow evidence rejection preserves selected batches and immutable history",
    ]
    real_titles = [REQUIRED_NODES["CR-01"][1]]

    fixture = tmp_path / "playwright.json"
    real = tmp_path / "playwright-real-host.json"
    fixture.write_text(json.dumps(_pw_report(*fixture_titles)), encoding="utf-8")
    real.write_text(json.dumps(_pw_report(*real_titles)), encoding="utf-8")
    return junit, [fixture, real]


def test_green_reports_map_every_cr_wr_exactly_once(tmp_path: Path) -> None:
    junit, pws = _green_bundle(tmp_path)
    result = verify(junit, pws)
    assert result["status"] == "passed"
    assert result["discovered"] == result["passed"]
    assert set(result["matches"]) == set(REQUIRED_NODES)
    for finding, node in result["matches"].items():
        kind, needle = REQUIRED_NODES[finding]
        assert node.startswith(f"{kind}:")
        assert needle in node


def test_missing_report_fails(tmp_path: Path) -> None:
    junit, _pws = _green_bundle(tmp_path)
    with pytest.raises(ReportError, match="missing or invalid"):
        verify(junit, [tmp_path / "nope.json"])


def test_malformed_junit_fails(tmp_path: Path) -> None:
    bad = tmp_path / "bad.xml"
    bad.write_text("<not-closed", encoding="utf-8")
    fixture = tmp_path / "pw.json"
    fixture.write_text(json.dumps(_pw_report(REQUIRED_NODES["CR-01"][1])), encoding="utf-8")
    with pytest.raises(ReportError, match="malformed"):
        verify(bad, [fixture])


def test_malformed_playwright_fails(tmp_path: Path) -> None:
    junit, _ = _green_bundle(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ReportError, match="malformed"):
        verify(junit, [bad])


def test_skipped_pytest_fails(tmp_path: Path) -> None:
    junit = tmp_path / "pytest.xml"
    junit.write_text(
        _junit(
            [
                (
                    "tests.forecast.test_calibration",
                    "test_cr02_projection_and_calibration_use_same_verified_parquet_bytes",
                    "skipped",
                )
            ]
        ),
        encoding="utf-8",
    )
    pw = tmp_path / "pw.json"
    pw.write_text(json.dumps(_pw_report(REQUIRED_NODES["CR-01"][1])), encoding="utf-8")
    with pytest.raises(ReportError, match="did not pass"):
        verify(junit, [pw])


def test_failed_pytest_fails(tmp_path: Path) -> None:
    junit = tmp_path / "pytest.xml"
    junit.write_text(
        _junit(
            [
                (
                    "tests.forecast.test_runner",
                    "test_cr05_final_input_revalidation_precedes_commit_and_commit_spy_zero",
                    "failure",
                )
            ]
        ),
        encoding="utf-8",
    )
    pw = tmp_path / "pw.json"
    pw.write_text(json.dumps(_pw_report(REQUIRED_NODES["CR-01"][1])), encoding="utf-8")
    with pytest.raises(ReportError, match="did not pass"):
        verify(junit, [pw])


def test_playwright_skipped_fails(tmp_path: Path) -> None:
    junit, pws = _green_bundle(tmp_path)
    bad = tmp_path / "skip.json"
    bad.write_text(
        json.dumps(_pw_report(REQUIRED_NODES["CR-04"][1], status="skipped")),
        encoding="utf-8",
    )
    with pytest.raises(ReportError, match=r"did not pass|skipped"):
        verify(junit, [bad, pws[1]])


def test_playwright_retried_flaky_fails(tmp_path: Path) -> None:
    junit, pws = _green_bundle(tmp_path)
    bad = tmp_path / "flaky.json"
    bad.write_text(
        json.dumps(_pw_report(REQUIRED_NODES["CR-04"][1], results=2, outcome="flaky")),
        encoding="utf-8",
    )
    with pytest.raises(ReportError, match=r"retried|flaky|did not pass|outcome"):
        verify(junit, [bad, pws[1]])


def test_duplicate_normalized_identity_fails(tmp_path: Path) -> None:
    junit, pws = _green_bundle(tmp_path)
    # Duplicate CR-01 title across two playwright reports
    dup = tmp_path / "dup.json"
    dup.write_text(
        json.dumps(_pw_report(REQUIRED_NODES["CR-01"][1])),
        encoding="utf-8",
    )
    with pytest.raises(ReportError, match="duplicate"):
        verify(junit, [pws[0], pws[1], dup])


def test_missing_cr_node_fails(tmp_path: Path) -> None:
    junit, pws = _green_bundle(tmp_path)
    # real-host report without CR-01
    empty_real = tmp_path / "real-empty.json"
    empty_real.write_text(
        json.dumps(_pw_report("unrelated real host scenario")),
        encoding="utf-8",
    )
    with pytest.raises(ReportError, match="CR-01 must match exactly one"):
        verify(junit, [pws[0], empty_real])


def test_duplicate_cr_assignment_fails(tmp_path: Path) -> None:
    """Two different findings must not claim the same node (synthetic clash)."""
    # Build junit where one test name contains two needles — not realistic;
    # instead two CR-04 titles in fixture cause CR-04 count=2.
    junit, pws = _green_bundle(tmp_path)
    multi = tmp_path / "multi.json"
    multi.write_text(
        json.dumps(
            _pw_report(
                REQUIRED_NODES["CR-04"][1],
                REQUIRED_NODES["CR-04"][1] + " again",
                # second still matches needle substring — two candidates
                "prefix " + REQUIRED_NODES["CR-04"][1],
            )
        ),
        encoding="utf-8",
    )
    # Replace fixture so CR-04 matches >1 (title and prefix title both contain needle)
    with pytest.raises(ReportError, match="CR-04 must match exactly one"):
        verify(junit, [multi, pws[1]])


def test_cli_green_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    junit, pws = _green_bundle(tmp_path)
    code = main(
        [
            "--pytest-junit",
            str(junit),
            "--playwright-json",
            str(pws[0]),
            "--playwright-json",
            str(pws[1]),
        ]
    )
    assert code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "passed"
    assert out["discovered"] == out["passed"]


def test_cli_reject_exits_one(tmp_path: Path) -> None:
    code = main(
        [
            "--pytest-junit",
            str(tmp_path / "missing.xml"),
            "--playwright-json",
            str(tmp_path / "missing.json"),
        ]
    )
    assert code == 1


def test_optional_smoke_absent_is_allowed_when_not_collected(tmp_path: Path) -> None:
    """Deselected optional smoke simply does not appear — green bundle has no such node."""
    junit, pws = _green_bundle(tmp_path)
    result = verify(junit, pws)
    assert all(
        "kronos_mini_regression" not in node for node in result["matches"].values()
    )


def test_optional_smoke_collected_as_skip_still_fails(tmp_path: Path) -> None:
    junit = tmp_path / "pytest.xml"
    junit.write_text(
        _junit(
            [
                (
                    "tests.forecast.test_kronos_regression",
                    "test_pinned_local_kronos_mini_regression_denies_network_and_proves_exact_provenance",
                    "skipped",
                ),
                (
                    "tests.forecast.test_calibration",
                    "test_cr02_projection_and_calibration_use_same_verified_parquet_bytes",
                    None,
                ),
            ]
        ),
        encoding="utf-8",
    )
    # Incomplete CR set — will fail either on skip or missing CR; skip must be first.
    pw = tmp_path / "pw.json"
    pw.write_text(json.dumps(_pw_report(REQUIRED_NODES["CR-01"][1])), encoding="utf-8")
    with pytest.raises(ReportError, match="did not pass"):
        verify(junit, [pw])


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "phase5-gate@example.invalid")
    _git(repo, "config", "user.name", "Phase 5 Gate")
    tracked = [
        "backend/scripts/verify_phase5_final_gate.py",
        "backend/tests/test_phase5_final_gate.py",
        "frontend/package.json",
    ]
    tracked.extend(p for p in RELEVANT_PATHS if "05-optional-enhancements" in p)
    for relative in tracked:
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{relative}\n", encoding="utf-8")
    _git(repo, "add", *tracked)
    _git(repo, "commit", "-m", "fixture")
    return repo


def _write_playwright_report(
    path: Path,
    file_name: str,
    titles: list[str],
    *,
    project_name: str = "desktop-chromium",
) -> None:
    payload = _pw_report(*titles)
    payload["suites"][0]["file"] = file_name
    payload["suites"][0]["title"] = file_name
    for spec in payload["suites"][0]["specs"]:
        spec["tests"][0]["projectName"] = project_name
    path.write_text(json.dumps(payload), encoding="utf-8")


def _strict_bundle(
    tmp_path: Path,
) -> tuple[Path, dict[str, Path], GitProvenance, str, str]:
    report_root = tmp_path / "reports"
    report_root.mkdir(parents=True)
    now = datetime.now(UTC)
    started = (now - timedelta(seconds=2)).isoformat().replace("+00:00", "Z")
    producer_started = (now - timedelta(seconds=1)).isoformat().replace(
        "+00:00", "Z"
    )
    producer_completed = now.isoformat().replace("+00:00", "Z")
    provenance = GitProvenance(
        expected_head="a" * 40,
        expected_tree="b" * 40,
        phase43_commit="c" * 40,
    )
    run_id = "11111111-2222-4333-8444-555555555555"
    grouped: dict[str, list[str]] = {label: [] for label in REPORT_LABELS}
    for label, _kind, identity in REQUIRED_REPORT_NODES.values():
        grouped[label].append(identity)

    reports = {
        label: report_root / REPORT_FILENAMES[label] for label in REPORT_LABELS
    }
    for label in ("pytest-windows", "pytest-linux"):
        cases: list[tuple[str, str, str | None]] = []
        for identity in grouped[label]:
            node = identity.removeprefix("pytest:")
            classname, name = node.rsplit("::", 1)
            cases.append((classname, name, None))
        cases.append(("tests.synthetic", f"test_{label.replace('-', '_')}_green", None))
        reports[label].write_text(_junit(cases), encoding="utf-8")

    _write_playwright_report(
        reports["playwright-fixture"],
        "e2e/phase5-optional-enhancements.spec.ts",
        [
            identity.split("::", 1)[1]
            for identity in grouped["playwright-fixture"]
        ],
    )
    _write_playwright_report(
        reports["playwright-real-host"],
        "e2e/phase5-shadow-real-host.spec.ts",
        [
            identity.split("::", 1)[1]
            for identity in grouped["playwright-real-host"]
        ],
        project_name="phase5-shadow-real-host",
    )
    for label, report in reports.items():
        sidecar = report.with_name(report.name + ".provenance.json")
        sidecar.write_text(
            json.dumps(
                {
                    "expectedHead": provenance.expected_head,
                    "expectedTree": provenance.expected_tree,
                    "runId": run_id,
                    "startedAt": started,
                    "producerStartedAt": producer_started,
                    "producerCompletedAt": producer_completed,
                    "label": label,
                    "reportPath": str(report.resolve()),
                    "reportRoot": str(report_root.resolve()),
                }
            ),
            encoding="utf-8",
        )
        timestamp = now.timestamp()
        os.utime(report, (timestamp, timestamp))
    return report_root, reports, provenance, run_id, started


def test_producer_specs_redirect_every_output_to_external_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    (repo / "frontend").mkdir()
    root = tmp_path / "external" / "run"
    root.mkdir(parents=True)

    specs = build_producer_specs(
        repo,
        root,
        linux_repo_root="/mnt/d/source/AthenaQuant",
        linux_report_root="/mnt/c/tmp/athena-phase5-44",
    )

    assert tuple(spec.label for spec in specs) == REPORT_LABELS
    assert all(spec.report_path.parent == root for spec in specs)
    assert all(spec.env["ATHENA_ALLOW_NETWORK"] == "0" for spec in specs)
    windows = specs[0]
    assert "--isolated" in windows.argv and "--frozen" in windows.argv
    assert windows.argv.count("--extra") == 1
    assert "tests/advanced/test_sandbox.py" in windows.argv
    assert "tests/forecast/test_runner.py" in windows.argv
    assert "tests/test_kronos_provisioner.py" not in windows.argv
    assert "--junitxml" in " ".join(windows.argv)
    assert "not linux_process_group" in windows.argv
    linux = specs[1]
    assert linux.argv[:3] == ("wsl.exe", "--exec", "bash")
    assert "--extra shadow" in " ".join(linux.argv)
    assert "--import-mode=importlib" in " ".join(linux.argv)
    assert "not windows_only" in " ".join(linux.argv)
    assert "test_pinned_local_kronos_mini_regression" in " ".join(linux.argv)
    for spec in specs[2:]:
        assert spec.argv[0] == str(
            repo
            / "frontend"
            / "node_modules"
            / ".bin"
            / ("playwright.cmd" if os.name == "nt" else "playwright")
        )
        assert spec.argv[1] == "test"
        assert "--reporter=json" in spec.argv
        assert any(arg.startswith("--output=") for arg in spec.argv)
        assert Path(spec.env["PLAYWRIGHT_JSON_OUTPUT_FILE"]).parent == root

def test_producer_specs_linux_native_runs_directly_without_wsl(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    (repo / "frontend").mkdir()
    root = tmp_path / "external"
    root.mkdir()
    specs = build_producer_specs(
        repo,
        root,
        linux_repo_root="/repo",
        linux_report_root="/reports",
        linux_native=True,
    )
    linux = specs[1]
    assert "wsl.exe" not in linux.argv
    assert linux.cwd == repo / "backend"
    assert linux.argv[0] == "env"
    assert "--import-mode=importlib" in linux.argv
    assert "not windows_only" in linux.argv
    assert "--extra" in linux.argv and "shadow" in linux.argv


def test_run_producer_uses_fake_and_writes_bound_sidecar(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    (repo / "frontend").mkdir()
    root = tmp_path / "external"
    root.mkdir()
    spec = build_producer_specs(
        repo,
        root,
        linux_repo_root="/repo",
        linux_report_root="/reports",
    )[0]
    provenance = GitProvenance("a" * 40, "b" * 40, "c" * 40)

    def fake_runner(
        argv: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
        check: bool,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        assert argv == spec.argv
        assert cwd == spec.cwd
        assert env["ATHENA_ALLOW_NETWORK"] == "0"
        assert check is False
        assert timeout == 30 * 60
        spec.report_path.write_text(
            _junit([("tests.synthetic", "test_fake", None)]), encoding="utf-8"
        )
        return subprocess.CompletedProcess(argv, 0)

    run_producer(
        spec,
        provenance,
        run_id="11111111-2222-4333-8444-555555555555",
        started_at=datetime.now(UTC).isoformat(),
        runner=fake_runner,
    )
    sidecar = json.loads(
        spec.sidecar_path.read_text(encoding="utf-8")
    )
    assert sidecar["label"] == "pytest-windows"
    assert sidecar["expectedHead"] == provenance.expected_head
    assert sidecar["expectedTree"] == provenance.expected_tree
    assert sidecar["reportPath"] == str(spec.report_path.resolve())


def test_run_producer_reports_missing_executable_as_gate_error(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    (repo / "frontend").mkdir()
    root = tmp_path / "external"
    root.mkdir()
    spec = build_producer_specs(
        repo,
        root,
        linux_repo_root="/repo",
        linux_report_root="/reports",
    )[0]
    provenance = GitProvenance("a" * 40, "b" * 40, "c" * 40)

    def missing_runner(
        _argv: tuple[str, ...], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("missing")

    with pytest.raises(ReportError, match="could not start"):
        run_producer(
            spec,
            provenance,
            run_id="11111111-2222-4333-8444-555555555555",
            started_at=datetime.now(UTC).isoformat(),
            runner=missing_runner,
        )


def test_run_producer_translates_bounded_timeout_and_leaves_no_sidecar(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    (repo / "frontend").mkdir()
    root = tmp_path / "external"
    root.mkdir()
    spec = build_producer_specs(
        repo,
        root,
        linux_repo_root="/repo",
        linux_report_root="/reports",
    )[0]
    provenance = GitProvenance("a" * 40, "b" * 40, "c" * 40)

    def timeout_runner(
        argv: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        assert kwargs["timeout"] == 30 * 60
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    with pytest.raises(ReportError, match=r"pytest-windows timed out after 1800"):
        run_producer(
            spec,
            provenance,
            run_id="11111111-2222-4333-8444-555555555555",
            started_at=datetime.now(UTC).isoformat(),
            runner=timeout_runner,
        )
    assert not spec.sidecar_path.exists()


def test_run_producer_default_popen_path_bounds_every_tree_reap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    (repo / "frontend").mkdir()
    root = tmp_path / "external"
    root.mkdir()
    spec = build_producer_specs(
        repo,
        root,
        linux_repo_root="/repo",
        linux_report_root="/reports",
    )[0]
    provenance = GitProvenance("a" * 40, "b" * 40, "c" * 40)
    waits: list[float | None] = []
    killed: list[str] = []

    class FakeProcess:
        pid = 424242
        returncode = -9

        def poll(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            waits.append(timeout)
            assert timeout is not None
            if len(waits) < 3:
                raise subprocess.TimeoutExpired(spec.argv, timeout)
            return self.returncode

        def kill(self) -> None:
            killed.append("process")

    def fake_popen(
        argv: tuple[str, ...], **kwargs: object
    ) -> FakeProcess:
        assert argv == spec.argv
        assert kwargs["cwd"] == spec.cwd
        assert "env" in kwargs
        if os.name == "nt":
            assert kwargs["creationflags"] == subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            assert kwargs["start_new_session"] is True
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    if os.name == "nt":
        def fake_taskkill(
            argv: tuple[str, ...], **kwargs: object
        ) -> subprocess.CompletedProcess[bytes]:
            assert argv == (
                "taskkill",
                "/PID",
                "424242",
                "/T",
                "/F",
            )
            assert kwargs["timeout"] == 10
            killed.append("tree")
            return subprocess.CompletedProcess(argv, 0, b"", b"")

        monkeypatch.setattr(subprocess, "run", fake_taskkill)
    else:
        def fake_killpg(pid: int, sig: int) -> None:
            assert pid == 424242
            if sig == 0 and "SIGKILL" in killed:
                raise ProcessLookupError("process group gone after SIGKILL")
            killed.append(signal.Signals(sig).name if sig else "SIG0")

        monkeypatch.setattr(os, "killpg", fake_killpg)

    with pytest.raises(ReportError, match=r"pytest-windows timed out after 1800"):
        run_producer(
            spec,
            provenance,
            run_id="11111111-2222-4333-8444-555555555555",
            started_at=datetime.now(UTC).isoformat(),
        )
    assert waits == [30 * 60, 10, 10]
    if os.name == "nt":
        assert "tree" in killed
    else:
        assert "SIGKILL" in killed
    assert not spec.sidecar_path.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows taskkill contract")
def test_windows_tree_cleanup_retries_taskkill_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[tuple[str, ...]] = []
    killed: list[str] = []

    class ExitedLeader:
        pid = 424242
        returncode = 0

        def poll(self) -> int:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            assert timeout == 10
            return self.returncode

        def kill(self) -> None:
            killed.append("leader")

    def failed_taskkill(
        argv: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        assert kwargs["timeout"] == 10
        attempts.append(argv)
        return subprocess.CompletedProcess(argv, 128, b"", b"not found")

    monkeypatch.setattr(subprocess, "run", failed_taskkill)

    with pytest.raises(
        ReportError,
        match=r"producer process tree cleanup could not be proven",
    ):
        final_gate._terminate_process_tree(ExitedLeader())

    assert len(attempts) == 2
    assert killed == ["leader"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX process-group contract")
def test_posix_tree_cleanup_reaps_descendant_after_leader_exits(
    tmp_path: Path,
) -> None:
    descendant_pid_path = tmp_path / "descendant.pid"
    child_source = (
        "import signal,time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "while True: time.sleep(1)\n"
    )
    leader_source = (
        "import pathlib,subprocess,sys,time\n"
        f"child=subprocess.Popen([sys.executable,'-c',{child_source!r}])\n"
        f"pathlib.Path({str(descendant_pid_path)!r}).write_text(str(child.pid))\n"
        "while True: time.sleep(1)\n"
    )
    leader = subprocess.Popen(
        [sys.executable, "-c", leader_source],
        start_new_session=True,
    )
    deadline = time.monotonic() + 5
    while not descendant_pid_path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert descendant_pid_path.exists()
    descendant_pid = int(descendant_pid_path.read_text(encoding="utf-8"))

    final_gate._terminate_process_tree(leader)

    assert leader.poll() is not None
    with pytest.raises(ProcessLookupError):
        os.kill(descendant_pid, 0)


def test_documented_command_resolves_planning_paths_from_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    backend = repo / "backend"
    phase_dir = repo / ".planning" / "milestones" / "v1.0-phases" / "05-optional-enhancements"
    phase_dir.mkdir(parents=True)
    backend.mkdir()
    for name in ("05-VALIDATION.md", "05-43-SUMMARY.md", "05-44-PLAN.md"):
        (phase_dir / name).touch()

    class PreflightReached(Exception):
        pass

    def stop_after_preflight(repo_root: Path, summary: Path) -> GitProvenance:
        assert repo_root == repo.resolve()
        assert summary == (phase_dir / "05-43-SUMMARY.md").resolve()
        raise PreflightReached

    monkeypatch.setattr(final_gate, "capture_git_provenance", stop_after_preflight)
    monkeypatch.chdir(backend)

    with pytest.raises(PreflightReached):
        final_gate.orchestrate(
            Path(".."),
            Path(".planning/milestones/v1.0-phases/05-optional-enhancements/05-VALIDATION.md"),
            Path(".planning/milestones/v1.0-phases/05-optional-enhancements/05-43-SUMMARY.md"),
            Path(".planning/milestones/v1.0-phases/05-optional-enhancements/05-44-PLAN.md"),
        )


def test_wsl_path_resolution_decodes_utf16_and_reports_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(
        argv: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        assert argv[:3] == ["wsl.exe", "--exec", "wslpath"]
        assert kwargs["encoding"] == "utf-16-le"
        assert kwargs["errors"] == "replace"
        assert kwargs["timeout"] == 30
        return subprocess.CompletedProcess(
            argv,
            1,
            stdout="用法: wsl.exe [参数]",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(
        ReportError,
        match=r"WSL/Linux producer environment is unavailable.*用法",
    ):
        _resolve_wsl_path(tmp_path)


def test_wsl_path_resolution_timeout_reports_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def timeout_run(argv: list[str], **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout_run)
    with pytest.raises(
        ReportError,
        match=r"WSL/Linux producer environment is unavailable",
    ):
        _resolve_wsl_path(tmp_path)


@pytest.mark.parametrize(
    ("mode", "relative"),
    [
        ("unstaged", "backend/app.py"),
        ("staged", "backend/staged.py"),
        ("untracked", "backend/new.py"),
        ("untracked", "frontend/pnpm-workspace.yaml"),
    ],
)
def test_git_provenance_rejects_dirty_relevant_paths(
    tmp_path: Path, mode: str, relative: str
) -> None:
    repo = _git_repo(tmp_path)
    provenance = capture_git_provenance(
        repo,
        repo / final_gate._phase05_rel("05-43-SUMMARY.md"),
    )
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("dirty\n", encoding="utf-8")
    if mode == "staged":
        _git(repo, "add", relative)

    with pytest.raises(ReportError, match="relevant pathspec is dirty"):
        assert_git_provenance(repo, provenance)


def test_git_provenance_excludes_repository_memory_and_rejects_tree_drift(
    tmp_path: Path,
) -> None:
    repo = _git_repo(tmp_path)
    provenance = capture_git_provenance(
        repo,
        repo / final_gate._phase05_rel("05-43-SUMMARY.md"),
    )
    memory = repo / ".codebase-memory/graph.db.zst"
    memory.parent.mkdir()
    memory.write_text("not part of gate\n", encoding="utf-8")
    assert ".codebase-memory" not in RELEVANT_PATHS
    assert_git_provenance(repo, provenance)

    wrong_tree = GitProvenance(
        provenance.expected_head,
        "0" * 40,
        provenance.phase43_commit,
    )
    with pytest.raises(ReportError, match="tree"):
        assert_git_provenance(repo, wrong_tree)


def test_git_provenance_rejects_head_drift(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path)
    provenance = capture_git_provenance(
        repo,
        repo / final_gate._phase05_rel("05-43-SUMMARY.md"),
    )
    tracked = repo / "backend/scripts/verify_phase5_final_gate.py"
    tracked.write_text("next\n", encoding="utf-8")
    _git(repo, "add", str(tracked.relative_to(repo)))
    _git(repo, "commit", "-m", "drift")
    with pytest.raises(ReportError, match="HEAD"):
        assert_git_provenance(repo, provenance)


def test_four_bound_reports_parse_all_fifteen_findings(tmp_path: Path) -> None:
    root, reports, provenance, run_id, started = _strict_bundle(tmp_path)
    envelopes = validate_report_envelopes(
        reports,
        root,
        provenance,
        run_id=run_id,
        started_at=started,
    )
    result = verify_report_envelopes(envelopes)
    assert result["status"] == "passed"
    assert set(result["matches"]) == set(REQUIRED_REPORT_NODES)
    assert len(result["matches"]) == 15
    assert {report["label"] for report in result["reports"]} == set(REPORT_LABELS)


@pytest.mark.parametrize(
    "field",
    [
        "expectedHead",
        "expectedTree",
        "runId",
        "startedAt",
        "label",
        "reportPath",
        "reportRoot",
    ],
)
def test_sidecar_mismatch_fails_closed(tmp_path: Path, field: str) -> None:
    root, reports, provenance, run_id, started = _strict_bundle(tmp_path)
    report = reports["pytest-windows"]
    sidecar_path = report.with_name(report.name + ".provenance.json")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar[field] = "mismatch"
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    with pytest.raises(
        ReportError,
        match=r"provenance|canonical|label|path|root",
    ):
        validate_report_envelopes(
            reports,
            root,
            provenance,
            run_id=run_id,
            started_at=started,
        )


def test_stale_and_out_of_root_reports_fail_closed(tmp_path: Path) -> None:
    root, reports, provenance, run_id, started = _strict_bundle(tmp_path)
    stale = reports["pytest-linux"]
    old = (datetime.now(UTC) - timedelta(days=2)).timestamp()
    os.utime(stale, (old, old))
    with pytest.raises(ReportError, match="stale"):
        validate_report_envelopes(
            reports, root, provenance, run_id=run_id, started_at=started
        )

    root, reports, provenance, run_id, started = _strict_bundle(tmp_path / "other")
    outside = tmp_path / "outside.xml"
    shutil.copy2(reports["pytest-windows"], outside)
    reports["pytest-windows"] = outside
    with pytest.raises(ReportError, match=r"root|canonical"):
        validate_report_envelopes(
            reports, root, provenance, run_id=run_id, started_at=started
        )


def test_strict_parser_rejects_wrong_report_target_and_duplicate_node(
    tmp_path: Path,
) -> None:
    root, reports, provenance, run_id, started = _strict_bundle(tmp_path)
    real = reports["playwright-real-host"]
    _write_playwright_report(
        real,
        "e2e/phase5-shadow-real-host.spec.ts",
        ["unrelated real host scenario"],
        project_name="phase5-shadow-real-host",
    )
    os.utime(real, None)
    envelopes = validate_report_envelopes(
        reports, root, provenance, run_id=run_id, started_at=started
    )
    with pytest.raises(ReportError, match=r"CR-01.*exactly one"):
        verify_report_envelopes(envelopes)

    root, reports, provenance, run_id, started = _strict_bundle(tmp_path / "duplicate")
    fixture = reports["playwright-fixture"]
    titles = [
        identity.split("::", 1)[1]
        for label, _kind, identity in REQUIRED_REPORT_NODES.values()
        if label == "playwright-fixture"
    ]
    _write_playwright_report(
        fixture,
        "e2e/phase5-optional-enhancements.spec.ts",
        [*titles, titles[0]],
    )
    os.utime(fixture, None)
    envelopes = validate_report_envelopes(
        reports, root, provenance, run_id=run_id, started_at=started
    )
    with pytest.raises(ReportError, match="duplicate"):
        verify_report_envelopes(envelopes)


def _pending_validation_fixture(
    current: str,
    *,
    source_status: str = "validated",
) -> str:
    lines = current.splitlines(keepends=True)
    task_ids = ("05-GC-43-1", "05-GC-43-2", "05-GC-43-3", "05-GC-44-2")
    finding_ids = (
        "R43-CR-01",
        "R43-CR-02",
        "R43-CR-03",
        "R43-CR-04",
        "R43-WR-01",
    )
    report_labels = (
        "pytest-windows",
        "pytest-linux",
        "playwright-fixture",
        "playwright-real-host",
    )
    in_signoff = False
    for index, line in enumerate(lines):
        bare = line.rstrip("\r\n")
        newline = line[len(bare):]
        if bare in {"status: pending", "status: validated"}:
            lines[index] = f"status: {source_status}" + newline
        elif bare == "r43_wave15_status: passed":
            lines[index] = "r43_wave15_status: pending" + newline
        elif any(line.startswith(f"| {task_id} |") for task_id in task_ids):
            lines[index] = line.replace("✅ passed", "⬜ pending", 1)
        elif any(
            line.startswith(f"| {finding} |") for finding in finding_ids
        ) and "| ✅ passed | 05-44 Task 2 same-run parser |" in line:
            lines[index] = line.replace("| ✅ passed |", "| ⬜ pending |", 1)
        elif any(
            line.startswith(f"| {label} |") for label in report_labels
        ) and "✅ passed" in line:
            prefix = line.rsplit("|", 2)[0]
            lines[index] = prefix + "| ⬜ pending |" + newline
        elif bare == "### R43 / Wave 15 Gap Closure Sign-Off":
            in_signoff = True
        elif in_signoff and line.startswith("- [x] "):
            lines[index] = line.replace("- [x] ", "- [ ] ", 1)
        elif line.startswith("**R43 / Wave 15 scoped approval:** passed"):
            lines[index] = (
                "**R43 / Wave 15 scoped approval:** pending" + newline
            )
            in_signoff = False
    return "".join(lines)


@pytest.mark.parametrize("source_status", ["pending", "validated"])
def test_scoped_validation_dry_run_and_atomic_replace(
    tmp_path: Path,
    source_status: str,
) -> None:
    source = final_gate._PHASE05_DIR / "05-VALIDATION.md"
    target = tmp_path / "05-VALIDATION.md"
    target.write_bytes(source.read_bytes())
    original = _pending_validation_fixture(
        target.read_text(encoding="utf-8"),
        source_status=source_status,
    )
    target.write_text(original, encoding="utf-8", newline="")
    provenance = GitProvenance("a" * 40, "b" * 40, "c" * 40)
    original_status_lines = [
        line for line in original.splitlines() if line.startswith("status: ")
    ]
    assert original_status_lines == [f"status: {source_status}"]

    candidate = build_scoped_validation_candidate(
        original,
        provenance=provenance,
        run_id="11111111-2222-4333-8444-555555555555",
        started_at="2026-07-27T00:00:00Z",
        report_root=tmp_path / "reports",
        report_paths={
            label: tmp_path / "reports" / REPORT_FILENAMES[label]
            for label in REPORT_LABELS
        },
    )
    validate_scoped_validation_candidate(original, candidate)
    assert target.read_text(encoding="utf-8") == original
    candidate_status_lines = [
        line for line in candidate.splitlines() if line.startswith("status: ")
    ]
    assert candidate_status_lines == original_status_lines
    assert "r43_wave15_status: passed" in candidate
    assert (
        "05-GC-40-1" in candidate
        and "complete / rejected blocking-human record" in candidate
    )
    assert "approval: rejected" in candidate

    atomic_replace_validation(target, candidate)
    replaced = target.read_text(encoding="utf-8")
    assert replaced == candidate
    assert [
        line for line in replaced.splitlines() if line.startswith("status: ")
    ] == original_status_lines


def test_scoped_validation_rejects_global_diff_and_partial_transition(
    tmp_path: Path,
) -> None:
    source = final_gate._PHASE05_DIR / "05-VALIDATION.md"
    original = _pending_validation_fixture(source.read_text(encoding="utf-8"))
    provenance = GitProvenance("a" * 40, "b" * 40, "c" * 40)
    candidate = build_scoped_validation_candidate(
        original,
        provenance=provenance,
        run_id="11111111-2222-4333-8444-555555555555",
        started_at="2026-07-27T00:00:00Z",
        report_root=tmp_path / "reports",
        report_paths={
            label: tmp_path / "reports" / REPORT_FILENAMES[label]
            for label in REPORT_LABELS
        },
    )
    forbidden = candidate.replace(
        "status: validated\nr43_wave15_status: passed",
        "status: complete\nr43_wave15_status: passed",
        1,
    )
    with pytest.raises(ReportError, match=r"allowlist|global"):
        validate_scoped_validation_candidate(original, forbidden)

    partial = candidate.replace(
        "| R43-CR-04 | ✅ passed |",
        "| R43-CR-04 | ⬜ pending |",
        1,
    )
    with pytest.raises(ReportError, match=r"partial|transition"):
        validate_scoped_validation_candidate(original, partial)


def _linux_evidence(
    tmp_path: Path,
    provenance: GitProvenance,
    *,
    run_id: str = "123456789",
    now: datetime | None = None,
    overrides: dict[str, object] | None = None,
) -> tuple[Path, dict[str, object], datetime]:
    accepted_now = now or datetime.now(UTC)
    evidence = tmp_path / "linux-evidence"
    evidence.mkdir(parents=True)
    junit = evidence / "pytest-linux.xml"
    junit.write_text(
        _junit(
            [
                (
                    "tests.forecast.test_runner",
                    "test_native_linux_process_group",
                    None,
                )
            ]
        ),
        encoding="utf-8",
    )
    started = (accepted_now - timedelta(minutes=3)).isoformat().replace(
        "+00:00", "Z"
    )
    completed = (accepted_now - timedelta(minutes=2)).isoformat().replace(
        "+00:00", "Z"
    )
    attestation: dict[str, object] = {
        "schemaVersion": LINUX_EVIDENCE_SCHEMA,
        "repository": GITHUB_REPOSITORY,
        "workflow": PHASE5_LINUX_WORKFLOW,
        "githubRunId": run_id,
        "githubRunAttempt": 1,
        "artifactName": f"phase5-linux-evidence-{run_id}",
        "expectedHead": provenance.expected_head,
        "expectedTree": provenance.expected_tree,
        "runnerOS": "Linux",
        "pytestCommand": LINUX_REPORT_PYTEST_COMMAND,
        "pytestMarker": LINUX_REPORT_MARKER,
        "nativeMarkerCommand": LINUX_NATIVE_PYTEST_COMMAND,
        "nativeMarker": LINUX_NATIVE_MARKER,
        "startedAt": started,
        "completedAt": completed,
        "junitSha256": hashlib.sha256(junit.read_bytes()).hexdigest(),
    }
    if overrides:
        attestation.update(overrides)
    (evidence / "attestation.json").write_text(
        json.dumps(attestation),
        encoding="utf-8",
    )
    return evidence, attestation, accepted_now


def _github_run_payload(
    provenance: GitProvenance,
    attestation: dict[str, object],
    *,
    event: str = "push",
    overrides: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": int(str(attestation["githubRunId"])),
        "repository": {"full_name": GITHUB_REPOSITORY},
        "head_sha": provenance.expected_head,
        "head_commit": {"tree_id": provenance.expected_tree},
        "status": "completed",
        "conclusion": "success",
        "event": event,
        "path": f"{PHASE5_LINUX_WORKFLOW}@refs/heads/gsd/v1.0-milestone",
        "name": PHASE5_LINUX_WORKFLOW_NAME,
        "run_attempt": attestation["githubRunAttempt"],
        "html_url": "https://github.com/tchivs/AthenaQuant/actions/runs/123456789",
    }
    if overrides:
        payload.update(overrides)
    return payload


def _fake_gh_runner(
    payload: dict[str, object] | None,
    *,
    returncode: int = 0,
) -> object:
    def runner(
        argv: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        assert argv == (
            "gh",
            "api",
            "repos/tchivs/AthenaQuant/actions/runs/123456789",
            "--method",
            "GET",
        )
        assert kwargs["check"] is False
        assert kwargs["capture_output"] is True
        assert kwargs["encoding"] == "utf-8"
        return subprocess.CompletedProcess(
            argv,
            returncode,
            stdout=json.dumps(payload) if payload is not None else "",
            stderr="gh failure" if returncode else "",
        )

    return runner


def _artifact_archive(evidence: Path) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(
            "pytest-linux.xml",
            (evidence / "pytest-linux.xml").read_bytes(),
        )
        archive.writestr(
            "attestation.json",
            (evidence / "attestation.json").read_bytes(),
        )
    return output.getvalue()


def test_linux_artifact_extraction_rejects_nested_and_oversized_members(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested = tmp_path / "nested.zip"
    with zipfile.ZipFile(nested, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("nested/pytest-linux.xml", b"<testsuites/>")
        archive.writestr("attestation.json", b"{}")
    with pytest.raises(ReportError, match="ZIP layout"):
        final_gate._extract_linux_artifact(
            nested,
            tmp_path / "nested-output",
        )

    oversized = tmp_path / "oversized.zip"
    with zipfile.ZipFile(
        oversized, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.writestr("pytest-linux.xml", b"x" * 32)
        archive.writestr("attestation.json", b"{}")
    monkeypatch.setattr(
        final_gate,
        "_MAX_GITHUB_ARTIFACT_UNCOMPRESSED_BYTES",
        16,
    )
    with pytest.raises(ReportError, match="ZIP layout"):
        final_gate._extract_linux_artifact(
            oversized,
            tmp_path / "oversized-output",
        )


def _fake_github_artifact_runner(
    run_payload: dict[str, object],
    artifact_payload: dict[str, object],
    archive: bytes,
) -> object:
    def runner(
        argv: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        endpoint = argv[2]
        if endpoint.endswith("/actions/runs/123456789"):
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(run_payload),
                stderr="",
            )
        if endpoint.endswith("/actions/runs/123456789/artifacts?per_page=100"):
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=json.dumps(
                    {"total_count": 1, "artifacts": [artifact_payload]}
                ),
                stderr="",
            )
        if endpoint.endswith(
            f"/actions/artifacts/{artifact_payload['id']}/zip"
        ):
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout=archive,
                stderr=b"",
            )
        raise AssertionError(f"unexpected GitHub endpoint: {endpoint}")

    return runner


def test_github_linux_evidence_downloads_exact_bound_artifact(
    tmp_path: Path,
) -> None:
    provenance = GitProvenance("a" * 40, "b" * 40, "c" * 40)
    evidence, attestation, now = _linux_evidence(tmp_path, provenance)
    archive = _artifact_archive(evidence)
    artifact_id = 24680
    artifact_digest = "sha256:" + hashlib.sha256(archive).hexdigest()
    artifact = {
        "id": artifact_id,
        "name": "phase5-linux-evidence-123456789",
        "size_in_bytes": len(archive),
        "expired": False,
        "expires_at": (now + timedelta(days=1)).isoformat().replace(
            "+00:00", "Z"
        ),
        "digest": artifact_digest,
        "url": (
            "https://api.github.com/repos/tchivs/AthenaQuant/"
            f"actions/artifacts/{artifact_id}"
        ),
        "archive_download_url": (
            "https://api.github.com/repos/tchivs/AthenaQuant/"
            f"actions/artifacts/{artifact_id}/zip"
        ),
        "workflow_run": {
            "id": 123456789,
            "head_sha": provenance.expected_head,
        },
    }
    report_root = tmp_path / "gate-owned"
    report_root.mkdir()
    envelope = fetch_github_linux_evidence(
        report_root,
        provenance,
        local_run_id="11111111-2222-4333-8444-555555555555",
        local_started_at=now.isoformat(),
        github_repository=GITHUB_REPOSITORY,
        github_run_id="123456789",
        repo_root=tmp_path / "repository",
        gh_runner=_fake_github_artifact_runner(
            _github_run_payload(provenance, attestation),
            artifact,
            archive,
        ),  # type: ignore[arg-type]
        now=now,
    )
    assert envelope.report_path.read_bytes() == (
        evidence / "pytest-linux.xml"
    ).read_bytes()
    sidecar = json.loads(envelope.sidecar_path.read_text(encoding="utf-8"))
    binding = sidecar["externalEvidence"]["githubArtifact"]
    assert binding["id"] == artifact_id
    assert binding["digest"] == artifact_digest
    assert binding["archiveSha256"] == artifact_digest.removeprefix("sha256:")
    assert Path(
        sidecar["externalEvidence"]["sourceEvidenceDir"]
    ).is_relative_to(report_root)


@pytest.mark.parametrize(
    "artifact_override",
    [
        {"expired": True},
        {"expires_at": "2020-01-01T00:00:00Z"},
        {"digest": "sha256:" + "0" * 64},
    ],
)
def test_github_linux_evidence_rejects_untrusted_artifact_metadata(
    tmp_path: Path,
    artifact_override: dict[str, object],
) -> None:
    provenance = GitProvenance("a" * 40, "b" * 40, "c" * 40)
    evidence, attestation, now = _linux_evidence(tmp_path, provenance)
    archive = _artifact_archive(evidence)
    artifact_id = 24680
    artifact: dict[str, object] = {
        "id": artifact_id,
        "name": "phase5-linux-evidence-123456789",
        "size_in_bytes": len(archive),
        "expired": False,
        "expires_at": (now + timedelta(days=1)).isoformat().replace(
            "+00:00", "Z"
        ),
        "digest": "sha256:" + hashlib.sha256(archive).hexdigest(),
        "url": (
            "https://api.github.com/repos/tchivs/AthenaQuant/"
            f"actions/artifacts/{artifact_id}"
        ),
        "archive_download_url": (
            "https://api.github.com/repos/tchivs/AthenaQuant/"
            f"actions/artifacts/{artifact_id}/zip"
        ),
        "workflow_run": {
            "id": 123456789,
            "head_sha": provenance.expected_head,
        },
    }
    artifact.update(artifact_override)
    report_root = tmp_path / "gate-owned"
    report_root.mkdir()
    with pytest.raises(ReportError, match=r"artifact|digest|expired"):
        fetch_github_linux_evidence(
            report_root,
            provenance,
            local_run_id="11111111-2222-4333-8444-555555555555",
            local_started_at=now.isoformat(),
            github_repository=GITHUB_REPOSITORY,
            github_run_id="123456789",
            gh_runner=_fake_github_artifact_runner(
                _github_run_payload(provenance, attestation),
                artifact,
                archive,
            ),  # type: ignore[arg-type]
            now=now,
        )
    assert not (report_root / "pytest-linux.xml").exists()


@pytest.mark.parametrize("github_event", ["push", "workflow_dispatch"])
def test_external_linux_evidence_is_attested_copied_and_sidecar_bound(
    tmp_path: Path, github_event: str,
) -> None:
    provenance = GitProvenance("a" * 40, "b" * 40, "c" * 40)
    evidence, attestation, now = _linux_evidence(tmp_path, provenance)
    report_root = tmp_path / "external-run"
    report_root.mkdir()
    local_started = (now - timedelta(minutes=1)).isoformat().replace(
        "+00:00", "Z"
    )
    payload = _github_run_payload(provenance, attestation, event=github_event)

    envelope = accept_external_linux_evidence(
        evidence,
        report_root,
        provenance,
        local_run_id="11111111-2222-4333-8444-555555555555",
        local_started_at=local_started,
        github_repository=GITHUB_REPOSITORY,
        github_run_id="123456789",
        repo_root=tmp_path / "repository",
        gh_runner=_fake_gh_runner(payload),  # type: ignore[arg-type]
        now=now,
        offline_fixture_only=True,
    )

    assert envelope.label == "pytest-linux"
    assert envelope.report_path == report_root / "pytest-linux.xml"
    assert envelope.report_path.read_bytes() == (
        evidence / "pytest-linux.xml"
    ).read_bytes()
    sidecar = json.loads(envelope.sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["runId"] == "11111111-2222-4333-8444-555555555555"
    assert sidecar["expectedHead"] == provenance.expected_head
    assert sidecar["expectedTree"] == provenance.expected_tree
    assert sidecar["externalEvidence"]["attestation"] == attestation
    assert sidecar["externalEvidence"]["githubRun"]["conclusion"] == "success"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schemaVersion", "forged/v1"),
        ("repository", "attacker/AthenaQuant"),
        ("workflow", ".github/workflows/forged.yml"),
        ("githubRunId", "987654321"),
        ("expectedHead", "d" * 40),
        ("expectedTree", "e" * 40),
        ("runnerOS", "Windows"),
        ("pytestCommand", "pytest tests/forecast"),
        ("pytestMarker", "linux_process_group"),
        ("nativeMarkerCommand", "pytest -q"),
        ("nativeMarker", "not windows_only"),
        ("junitSha256", "0" * 64),
    ],
)
def test_external_linux_evidence_rejects_forged_attestation(
    tmp_path: Path, field: str, value: object
) -> None:
    provenance = GitProvenance("a" * 40, "b" * 40, "c" * 40)
    evidence, attestation, now = _linux_evidence(
        tmp_path,
        provenance,
        overrides={field: value},
    )
    report_root = tmp_path / "external-run"
    report_root.mkdir()
    with pytest.raises(ReportError, match=r"attestation|GitHub run"):
        accept_external_linux_evidence(
            evidence,
            report_root,
            provenance,
            local_run_id="11111111-2222-4333-8444-555555555555",
            local_started_at=now.isoformat(),
            github_repository=GITHUB_REPOSITORY,
            github_run_id="123456789",
            gh_runner=_fake_gh_runner(
                _github_run_payload(provenance, attestation)
            ),  # type: ignore[arg-type]
            now=now,
            offline_fixture_only=True,
        )
    assert not (report_root / "pytest-linux.xml").exists()


def test_external_linux_evidence_rejects_stale_attestation(
    tmp_path: Path,
) -> None:
    provenance = GitProvenance("a" * 40, "b" * 40, "c" * 40)
    now = datetime.now(UTC)
    old_started = (now - timedelta(hours=26)).isoformat().replace(
        "+00:00", "Z"
    )
    old_completed = (now - timedelta(hours=25)).isoformat().replace(
        "+00:00", "Z"
    )
    evidence, attestation, _ = _linux_evidence(
        tmp_path,
        provenance,
        now=now,
        overrides={"startedAt": old_started, "completedAt": old_completed},
    )
    report_root = tmp_path / "external-run"
    report_root.mkdir()
    with pytest.raises(ReportError, match="stale"):
        accept_external_linux_evidence(
            evidence,
            report_root,
            provenance,
            local_run_id="11111111-2222-4333-8444-555555555555",
            local_started_at=now.isoformat(),
            github_repository=GITHUB_REPOSITORY,
            github_run_id="123456789",
            gh_runner=_fake_gh_runner(
                _github_run_payload(provenance, attestation)
            ),  # type: ignore[arg-type]
            now=now,
            offline_fixture_only=True,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"head_sha": "d" * 40},
        {"head_commit": {"tree_id": "e" * 40}},
        {"conclusion": "failure"},
        {"status": "in_progress"},
        {"event": "schedule"},
        {"path": ".github/workflows/forged.yml@refs/heads/main"},
        {"name": "Forged Workflow"},
        {"repository": {"full_name": "attacker/AthenaQuant"}},
        {"run_attempt": 2},
    ],
)
def test_external_linux_evidence_rejects_mismatched_github_run(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    provenance = GitProvenance("a" * 40, "b" * 40, "c" * 40)
    evidence, attestation, now = _linux_evidence(tmp_path, provenance)
    report_root = tmp_path / "external-run"
    report_root.mkdir()
    payload = _github_run_payload(
        provenance,
        attestation,
        overrides=overrides,
    )
    with pytest.raises(ReportError, match="GitHub run verification mismatch"):
        accept_external_linux_evidence(
            evidence,
            report_root,
            provenance,
            local_run_id="11111111-2222-4333-8444-555555555555",
            local_started_at=now.isoformat(),
            github_repository=GITHUB_REPOSITORY,
            github_run_id="123456789",
            gh_runner=_fake_gh_runner(payload),  # type: ignore[arg-type]
            now=now,
            offline_fixture_only=True,
        )
    assert not (report_root / "pytest-linux.xml").exists()


def test_external_linux_evidence_rejects_gh_failure_and_preexisting_target(
    tmp_path: Path,
) -> None:
    provenance = GitProvenance("a" * 40, "b" * 40, "c" * 40)
    evidence, attestation, now = _linux_evidence(tmp_path, provenance)
    report_root = tmp_path / "external-run"
    report_root.mkdir()
    with pytest.raises(ReportError, match="GitHub run verification failed"):
        accept_external_linux_evidence(
            evidence,
            report_root,
            provenance,
            local_run_id="11111111-2222-4333-8444-555555555555",
            local_started_at=now.isoformat(),
            github_repository=GITHUB_REPOSITORY,
            github_run_id="123456789",
            gh_runner=_fake_gh_runner(None, returncode=1),  # type: ignore[arg-type]
            now=now,
            offline_fixture_only=True,
        )

    target = report_root / "pytest-linux.xml"
    target.write_text("preexisting", encoding="utf-8")
    with pytest.raises(ReportError, match="target already exists"):
        accept_external_linux_evidence(
            evidence,
            report_root,
            provenance,
            local_run_id="11111111-2222-4333-8444-555555555555",
            local_started_at=now.isoformat(),
            github_repository=GITHUB_REPOSITORY,
            github_run_id="123456789",
            gh_runner=_fake_gh_runner(
                _github_run_payload(provenance, attestation)
            ),  # type: ignore[arg-type]
            now=now,
            offline_fixture_only=True,
        )


def test_github_linux_workflow_matches_attestation_contract() -> None:
    workflow = (
        Path(__file__).parents[2]
        / ".github/workflows/phase5-linux-evidence.yml"
    ).read_text(encoding="utf-8")
    assert "name: Phase 5 Linux Evidence" in workflow
    assert "push:" in workflow
    assert "- gsd/v1.0-milestone" in workflow
    assert "workflow_dispatch:" in workflow
    assert "commit_sha:" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "ref: ${{ env.TARGET_SHA }}" in workflow
    assert LINUX_NATIVE_PYTEST_COMMAND in workflow
    assert LINUX_REPORT_PYTEST_COMMAND in workflow
    assert '"runnerOS": os.environ["RUNNER_OS"]' in workflow
    assert '"junitSha256": report_hash' in workflow
    assert "if-no-files-found: error" in workflow
    assert "overwrite: false" in workflow
    assert "actions/checkout@v4" not in workflow
    assert "astral-sh/setup-uv@v6" not in workflow
    assert "actions/upload-artifact@v4" not in workflow
    assert (
        "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683"
        " # v4.2.2"
    ) in workflow
    assert (
        "astral-sh/setup-uv@e92bafb6253dcd438e0484186d7669ea7a8ca1cc"
        " # v6.4.3"
    ) in workflow
    assert (
        "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
        " # v4.6.2"
    ) in workflow
