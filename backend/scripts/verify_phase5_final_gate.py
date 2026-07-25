"""Fail-closed Phase 05 final gate: parse pytest JUnit + Playwright JSON reports.

Rejects missing/malformed reports, any failure/error/skipped/xfail/xpass/retry/flaky
result, duplicate normalized identities, discovered≠passed counts, and any CR-01..07 /
WR-01..03 primary node that is missing, zero, or duplicated.

The only node that may be *absent* is the optional real-model Kronos smoke (must not
appear as a collected skip/xfail/xpass). Standard library only.
"""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


# Finding → (report kind, exact title / function-name needle).
REQUIRED_NODES: dict[str, tuple[str, str]] = {
    "CR-01": (
        "playwright",
        "CR-01 real host non-empty Shadow import to evidence distillation and IS-OOS",
    ),
    "CR-02": (
        "pytest",
        "test_cr02_projection_and_calibration_use_same_verified_parquet_bytes",
    ),
    "CR-03": (
        "pytest",
        "test_cr03_same_instrument_cross_principal_matrix_denies_every_surface",
    ),
    "CR-04": (
        "playwright",
        "CR-04 calibration outcome identity renders 5 20 60 and fails closed",
    ),
    "CR-05": (
        "pytest",
        "test_cr05_final_input_revalidation_precedes_commit_and_commit_spy_zero",
    ),
    "CR-06": (
        "pytest",
        "test_cr06_normal_leader_exit_reaps_process_group_before_commit",
    ),
    "CR-07": (
        "pytest",
        "test_cr07_real_host_queued_restart_executes_once",
    ),
    "WR-01": (
        "pytest",
        "test_wr01_operation_first_replay_race_leaves_no_orphan",
    ),
    "WR-02": (
        "pytest",
        "test_wr02_parquet_same_open_rejects_toctou",
    ),
    "WR-03": (
        "playwright",
        "WR-03 paged Thesis history renders before version page",
    ),
}

# May be absent (deselected). If collected in any non-passed status, still fails.
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
    {
        "failed",
        "timedOut",
        "interrupted",
        "skipped",
        "flaky",  # status sometimes used; also inferred from retries
    }
)


class ReportError(RuntimeError):
    """A machine report cannot establish the required final evidence."""


@dataclass(frozen=True)
class ReportStats:
    kind: str
    path: str
    discovered: int
    passed: int
    nodes: tuple[str, ...]


def _require_file(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise ReportError(f"report is missing or invalid: {path}")


def _is_optional_absent_node(identity: str) -> bool:
    bare = identity.split("::")[-1]
    if bare in OPTIONAL_ABSENT_ALLOWLIST:
        return True
    for allowed in OPTIONAL_ABSENT_ALLOWLIST:
        if allowed in identity:
            return True
    return False


def _pytest_nodes(path: Path) -> ReportStats:
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
            # Optional smoke must not appear as skip/xfail either.
            raise ReportError(f"pytest testcase did not pass: {classname}::{name}")
        # xfail_strict turns XPASS into failure (already failure tag). Bare pass only.
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
    )


def _playwright_result_ok(results: list[Any]) -> None:
    if not isinstance(results, list) or len(results) == 0:
        raise ReportError("Playwright testcase has no results")
    if len(results) != 1:
        raise ReportError("Playwright testcase retried, skipped, or has invalid results")
    result = results[0]
    if not isinstance(result, dict):
        raise ReportError("Playwright result entry is malformed")
    status = result.get("status")
    if status != "passed":
        raise ReportError(f"Playwright testcase did not pass (status={status!r})")
    # Defensive: retry markers inside a single result
    retry = result.get("retry")
    if isinstance(retry, int) and retry != 0:
        raise ReportError("Playwright testcase was retried")
    error = result.get("error")
    if error:
        raise ReportError("Playwright testcase carries an error payload")


def _playwright_nodes(path: Path) -> ReportStats:
    _require_file(path)
    try:
        raw = path.read_text(encoding="utf-8")
        # Some invocations redirect mixed stdout; take the outermost JSON object.
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        # Retry: first '{' to last '}'
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            if start < 0 or end <= start:
                raise error
            payload = json.loads(raw[start : end + 1])
        except Exception as nested:
            raise ReportError("Playwright JSON report is malformed") from nested

    if not isinstance(payload, dict):
        raise ReportError("Playwright JSON report is malformed")

    discovered = 0
    passed = 0
    nodes: list[str] = []

    def walk(value: Any, lineage: tuple[str, ...] = ()) -> None:
        nonlocal discovered, passed
        if isinstance(value, list):
            for item in value:
                walk(item, lineage)
            return
        if not isinstance(value, dict):
            return

        title = value.get("title")
        current = lineage + ((title,) if isinstance(title, str) and title else ())

        # Spec-level tests array (Playwright 1.x JSON reporter).
        tests = value.get("tests")
        if isinstance(tests, list):
            for test in tests:
                if not isinstance(test, dict):
                    raise ReportError("Playwright test entry is malformed")
                expected = test.get("expectedStatus")
                if expected is not None and expected not in ("passed", "expected"):
                    # unexpected expectedStatus (skip) is not green
                    if expected == "skipped":
                        raise ReportError("Playwright testcase expectedStatus is skipped")
                results = test.get("results")
                status = test.get("status")
                discovered += 1
                if status in _PLAYWRIGHT_NON_PASS or (
                    isinstance(status, str) and status not in (None, "expected", "passed")
                ):
                    # "expected" means matched expectedStatus=passed in some versions
                    if status not in (None, "expected", "passed"):
                        raise ReportError(
                            f"Playwright testcase did not pass (status={status!r})"
                        )
                try:
                    _playwright_result_ok(results if isinstance(results, list) else [])
                except ReportError:
                    raise
                # outcome field on test
                outcome = test.get("outcome")
                if isinstance(outcome, str) and outcome not in ("expected", "passed"):
                    # flaky / unexpected / skipped
                    raise ReportError(
                        f"Playwright testcase outcome is not clean pass ({outcome!r})"
                    )
                passed += 1
                nodes.append(f"playwright:{' :: '.join(current)}")

        for key in ("suites", "specs"):
            child = value.get(key)
            if isinstance(child, list):
                walk(child, current)

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
    )


def _collect(
    pytest_junit: Path, playwright_reports: Iterable[Path]
) -> tuple[list[str], list[ReportStats]]:
    stats: list[ReportStats] = []
    pytest_stats = _pytest_nodes(pytest_junit)
    stats.append(pytest_stats)
    nodes: list[str] = list(pytest_stats.nodes)
    for report in playwright_reports:
        pw = _playwright_nodes(report)
        stats.append(pw)
        nodes.extend(pw.nodes)
    return nodes, stats


def verify(pytest_junit: Path, playwright_reports: list[Path]) -> dict[str, Any]:
    if not playwright_reports:
        raise ReportError("at least one Playwright JSON report is required")

    nodes, stats = _collect(pytest_junit, playwright_reports)

    if len(nodes) != len(set(nodes)):
        raise ReportError("machine reports contain duplicate normalized test identities")

    total_discovered = sum(s.discovered for s in stats)
    total_passed = sum(s.passed for s in stats)
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
        node = candidates[0]
        if node in claimed:
            raise ReportError(
                f"machine-report node is assigned to more than one finding: {node}"
            )
        claimed.add(node)
        matches[finding] = node

    return {
        "status": "passed",
        "discovered": total_discovered,
        "passed": total_passed,
        "reports": [
            {
                "kind": s.kind,
                "path": s.path,
                "discovered": s.discovered,
                "passed": s.passed,
            }
            for s in stats
        ],
        "matches": matches,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pytest-junit", required=True, type=Path)
    parser.add_argument(
        "--playwright-json",
        required=True,
        type=Path,
        action="append",
        help="Playwright JSON report path (repeatable; fixture + real-host)",
    )
    args = parser.parse_args(argv)
    try:
        result = verify(args.pytest_junit, args.playwright_json)
    except ReportError as error:
        print(f"Phase 05 final gate rejected: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
