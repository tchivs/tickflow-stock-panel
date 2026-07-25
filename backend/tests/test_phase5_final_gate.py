"""Synthetic contracts for scripts/verify_phase5_final_gate.py."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from scripts.verify_phase5_final_gate import (
    REQUIRED_NODES,
    ReportError,
    main,
    verify,
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
    for finding, (kind, needle) in REQUIRED_NODES.items():
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
    junit, pws = _green_bundle(tmp_path)
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
    with pytest.raises(ReportError, match="did not pass|skipped"):
        verify(junit, [bad, pws[1]])


def test_playwright_retried_flaky_fails(tmp_path: Path) -> None:
    junit, pws = _green_bundle(tmp_path)
    bad = tmp_path / "flaky.json"
    bad.write_text(
        json.dumps(_pw_report(REQUIRED_NODES["CR-04"][1], results=2, outcome="flaky")),
        encoding="utf-8",
    )
    with pytest.raises(ReportError, match="retried|flaky|did not pass|outcome"):
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
