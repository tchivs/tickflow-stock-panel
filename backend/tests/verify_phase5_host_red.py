#!/usr/bin/env python3
"""Strict RED verifier for the Phase 05 production optional-host contract.

A successful verifier run means precisely this: all declared tests collect, every
required node ran, and every node failed only because ``app.optional_modules`` has
not been delivered yet.  Arbitrary pytest RED never satisfies the contract.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
TEST_FILE = "tests/test_phase5_optional_host.py"
PARAMETER_IDS = (
    "none",
    "shadow-only",
    "thesis-only",
    "forecast-only",
    "shadow-thesis",
    "shadow-forecast",
    "thesis-forecast",
    "all",
)
EXPECTED_NODES = {
    *(f"{TEST_FILE}::test_real_lifespan_preserves_v1_for_module_combination[{case}]" for case in PARAMETER_IDS),
    f"{TEST_FILE}::test_optional_capability_failures_are_typed_local_and_independent",
    f"{TEST_FILE}::test_optional_routes_reject_browser_authority_and_foreign_ids",
    f"{TEST_FILE}::test_optional_success_failure_and_terminal_paths_call_no_live_actions",
    f"{TEST_FILE}::test_optional_host_uses_one_runtime_database_lake_and_scheduler",
}
ALLOWED_MISSING_SURFACE = re.compile(
    r"(?:"
    r"ModuleNotFoundError: No module named ['\"]app\.optional_modules['\"]"
    r"|ImportError: cannot import name ['\"]optional_modules['\"] from ['\"]app['\"]"
    r"|ImportError: cannot import name ['\"](?:OptionalModuleProbe|build_optional_module_host)['\"] "
    r"from ['\"]app\.optional_modules['\"]"
    r")"
)
FATAL_TOKENS = (
    "ERROR at setup",
    "ERROR at collection",
    "SyntaxError",
    "fixture '却",
    "fixture '",
    "INTERNALERROR",
    "KeyboardInterrupt",
    "TimeoutExpired",
    "XPASS",
    "XFAIL",
    "SKIPPED",
    " PASSED ",
)


def _run(*args: str, timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args],
        cwd=BACKEND_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def _node_lines(output: str) -> set[str]:
    return {
        line.strip()
        for line in output.splitlines()
        if line.strip().startswith(f"{TEST_FILE}::")
    }


def _summary_failures(output: str) -> dict[str, str]:
    failures: dict[str, str] = {}
    for line in output.splitlines():
        match = re.match(rf"FAILED ({re.escape(TEST_FILE)}::\S+) - (.+)", line.strip())
        if match:
            failures[match.group(1)] = match.group(2)
    return failures


def main() -> int:
    try:
        collection = _run("--collect-only", "-q", TEST_FILE)
    except subprocess.TimeoutExpired:
        print("host RED verifier rejected collection timeout", file=sys.stderr)
        return 1
    collected = _node_lines(collection.stdout)
    if collection.returncode != 0:
        print("host RED verifier rejected collection failure:\n" + collection.stdout, file=sys.stderr)
        return 1
    if collected != EXPECTED_NODES:
        print(
            "host RED verifier rejected changed node inventory\n"
            f"missing={sorted(EXPECTED_NODES - collected)}\n"
            f"extra={sorted(collected - EXPECTED_NODES)}\n"
            + collection.stdout,
            file=sys.stderr,
        )
        return 1

    try:
        run = _run("-vv", "--tb=short", "--no-header", TEST_FILE)
    except subprocess.TimeoutExpired:
        print("host RED verifier rejected execution timeout", file=sys.stderr)
        return 1
    output = run.stdout
    if run.returncode != 1:
        print(
            f"host RED verifier expected pytest exit 1, received {run.returncode}\n{output}",
            file=sys.stderr,
        )
        return 1
    fatal = [token for token in FATAL_TOKENS if token in output]
    if fatal:
        print(f"host RED verifier rejected fatal result markers {fatal}\n{output}", file=sys.stderr)
        return 1

    failures = _summary_failures(output)
    if set(failures) != EXPECTED_NODES:
        print(
            "host RED verifier rejected incomplete/changed failure inventory\n"
            f"missing={sorted(EXPECTED_NODES - set(failures))}\n"
            f"extra={sorted(set(failures) - EXPECTED_NODES)}\n"
            + output,
            file=sys.stderr,
        )
        return 1
    unapproved = {
        node: reason for node, reason in failures.items() if not ALLOWED_MISSING_SURFACE.search(reason)
    }
    if unapproved:
        print(f"host RED verifier rejected unapproved failures: {unapproved}\n{output}", file=sys.stderr)
        return 1
    if f"{len(EXPECTED_NODES)} failed" not in output:
        print("host RED verifier rejected missing exact failure count\n" + output, file=sys.stderr)
        return 1

    print(
        f"Phase 05 host RED contract accepted: {len(EXPECTED_NODES)} exact nodes; "
        "only the declared app.optional_modules production seam is missing."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
