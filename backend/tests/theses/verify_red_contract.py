#!/usr/bin/env python3
"""Strict Thesis RED-contract verifier.

A zero exit means every declared node collected and failed only because its exact
future ``app.theses`` production boundary is absent. Syntax, collection, fixture,
timeout, crash, assertion, xfail/xpass, inventory drift, and unrelated imports are fatal.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]

GROUPS: dict[str, tuple[str, ...]] = {
    "contracts-versions": (
        "tests/theses/test_contracts.py",
        "tests/theses/test_versions.py",
    ),
    "scheduler-lifecycle": (
        "tests/theses/test_scheduler.py",
        "tests/theses/test_lifecycle.py",
    ),
}

EXPECTED_NODES: dict[str, tuple[str, ...]] = {
    "tests/theses/test_contracts.py": (
        "test_version_draft_requires_complete_anchor_and_condition",
        "test_strict_version_draft_rejects_browser_authority_fields",
        "test_valuation_anchor_rejects_target_or_ai_link_substitutes",
        "test_valuation_anchor_rejects_nonfinite_inverted_and_empty_assumptions",
        "test_condition_ast_accepts_only_fixed_source_field_operator_shape",
        "test_condition_ast_rejects_unknown_source_field_operator_and_oversized_lookback",
        "test_condition_ast_rejects_free_form_sql_python_and_identifier_injection",
        "test_revision_body_requires_expected_predecessor_and_explicit_change_reason",
        "test_review_body_contains_only_pending_id_and_rationale",
        "test_check_result_enum_preserves_missing_evidence_and_safe_error_states",
    ),
    "tests/theses/test_versions.py": (
        "test_create_version_atomically_persists_identity_anchor_condition_and_schedule",
        "test_failed_atomic_version_creation_leaves_no_partial_identity_anchor_or_condition",
        "test_revision_appends_predecessor_and_copies_only_omitted_validated_fields",
        "test_explicit_revision_revalidates_replacement_anchor_and_condition",
        "test_multiple_revisions_preserve_anchor_condition_and_check_history",
        "test_current_version_is_derived_deterministically_from_lineage",
        "test_stale_predecessor_and_identity_change_fail_without_partial_rows",
        "test_version_anchor_condition_and_check_facts_reject_update_and_delete",
        "test_foreign_key_and_cross_thesis_predecessor_tampering_fail",
        "test_historical_projection_is_complete_auditable_and_safe",
    ),
    "tests/theses/test_scheduler.py": (
        "test_each_condition_cadence_advances_its_independent_monotonic_cursor[daily]",
        "test_each_condition_cadence_advances_its_independent_monotonic_cursor[weekly]",
        "test_each_condition_cadence_advances_its_independent_monotonic_cursor[monthly]",
        "test_each_condition_cadence_advances_its_independent_monotonic_cursor[quarterly]",
        "test_bounded_scanner_acquires_due_conditions_in_stable_order",
        "test_duplicate_scanner_calls_return_one_check_per_condition_due_identity",
        "test_two_parallel_acquirers_have_one_lease_and_one_check_winner",
        "test_interruption_before_append_retries_same_due_after_lease_expiry",
        "test_interruption_after_append_reuses_canonical_check_on_restart",
        "test_resolver_failure_appends_safe_error_check_and_advances_by_policy",
        "test_process_restart_recovers_expired_lease_without_duplicate_evidence",
        "test_old_version_conditions_are_excluded_from_new_due_acquisition",
        "test_condition_due_identity_is_unique_and_checks_are_immutable",
    ),
    "tests/theses/test_lifecycle.py": (
        "test_each_evidence_result_appends_one_exact_immutable_check[matched]",
        "test_each_evidence_result_appends_one_exact_immutable_check[not-matched]",
        "test_each_evidence_result_appends_one_exact_immutable_check[insufficient]",
        "test_each_evidence_result_appends_one_exact_immutable_check[error]",
        "test_matched_check_creates_exactly_one_evidence_linked_pending_conclusion",
        "test_not_matched_insufficient_and_error_never_create_pending_or_false_zero",
        "test_automation_never_changes_official_state_or_opens_dialogs",
        "test_confirmation_requires_session_derived_server_principal",
        "test_confirmation_revalidates_evidence_and_appends_one_official_event",
        "test_confirmation_conflicts_when_governed_evidence_no_longer_matches",
        "test_rejection_appends_review_and_preserves_official_state",
        "test_duplicate_or_already_processed_review_is_a_conflict",
        "test_old_version_pending_conflicts_after_new_version_becomes_current",
        "test_competing_pending_review_conflicts_after_official_state_changes",
        "test_review_and_check_history_remain_readable_but_public_projection_is_safe",
        "test_lifecycle_invokes_zero_strategy_monitor_plan_portfolio_or_broker_actions",
    ),
}

ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    "app.theses.schemas": frozenset(
        {
            "ConditionCheckResult",
            "ReviewDecisionRequest",
            "ThesisCondition",
            "ThesisRevisionRequest",
            "ThesisVersionRequest",
            "ValuationAnchor",
        }
    ),
    "app.theses.repository": frozenset({"ThesisRepository"}),
    "app.theses.scheduler": frozenset({"ThesisDueScanner"}),
    "app.theses.service": frozenset({"ThesisService", "ThesisConflictError"}),
}

MISSING_MODULE = re.compile(
    r"^(?:E\s+)?ModuleNotFoundError: No module named "
    r"['\"](?P<module>app\.theses(?:\.[A-Za-z_]\w*)*)['\"]$"
)
MISSING_SYMBOL = re.compile(
    r"^(?:E\s+)?ImportError: cannot import name ['\"](?P<symbol>[A-Za-z_]\w*)['\"] from "
    r"['\"](?P<module>app\.theses(?:\.[A-Za-z_]\w*)*)['\"](?: .*)?$"
)
UNALLOWLISTED_EXCEPTION = re.compile(
    r"(?:AssertionError|SyntaxError|FixtureLookupError|NameError|TypeError|ValueError|"
    r"RuntimeError|TimeoutError|KeyError|sqlite3\.|DatabaseError|IntegrityError|Failed:|XPASS|XFAIL)"
)


class RedContractError(RuntimeError):
    """The RED suite failed outside its exact declared production boundary."""


def _expected_nodes(files: tuple[str, ...]) -> set[str]:
    return {
        f"{file_name}::{test_name}"
        for file_name in files
        for test_name in EXPECTED_NODES[file_name]
    }


def _run_pytest(arguments: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        return subprocess.run(
            [sys.executable, "-m", "pytest", *arguments],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RedContractError(f"pytest exceeded strict {timeout}s timeout") from error


def _collect(files: tuple[str, ...], expected: set[str]) -> None:
    result = _run_pytest(["--collect-only", "-q", "-p", "no:cacheprovider", *files])
    if result.returncode != 0:
        raise RedContractError(f"pytest collection failed:\n{result.stdout}")
    collected = {
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith("tests/theses/") and "::" in line
    }
    if collected != expected:
        raise RedContractError(
            f"node inventory changed; missing={sorted(expected - collected)}, "
            f"extra={sorted(collected - expected)}"
        )


def _is_declared_missing_boundary(text: str) -> bool:
    if UNALLOWLISTED_EXCEPTION.search(text):
        return False
    matches: set[tuple[str, str | None]] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        module_match = MISSING_MODULE.fullmatch(line)
        if module_match:
            matches.add((module_match.group("module"), None))
            continue
        symbol_match = MISSING_SYMBOL.fullmatch(line)
        if symbol_match:
            matches.add((symbol_match.group("module"), symbol_match.group("symbol")))
    if len(matches) != 1:
        return False
    module, symbol = next(iter(matches))
    if symbol is None:
        return module == "app.theses" or module in ALLOWED_IMPORTS
    return symbol in ALLOWED_IMPORTS.get(module, frozenset())


def _validate_failure_classifier() -> None:
    accepted = (
        "ModuleNotFoundError: No module named 'app.theses'",
        "E   ModuleNotFoundError: No module named 'app.theses.schemas'",
        "ImportError: cannot import name 'ThesisRepository' from 'app.theses.repository' (/tmp/repository.py)",
    )
    rejected = (
        "AssertionError: No module named 'app.theses'",
        "SyntaxError: invalid syntax\nModuleNotFoundError: No module named 'app.theses'",
        "FixtureLookupError: fixture 'thesis_repo' not found",
        "ModuleNotFoundError: No module named 'pydantic'",
        "ImportError: cannot import name 'BrokerClient' from 'app.theses.repository'",
        "ImportError: cannot import name 'ThesisRepository' from 'app.shadow.repository'",
        "XPASS app.theses production unexpectedly exists",
    )
    if not all(_is_declared_missing_boundary(item) for item in accepted):
        raise RedContractError("RED failure classifier rejects a declared production boundary")
    if any(_is_declared_missing_boundary(item) for item in rejected):
        raise RedContractError("RED failure classifier accepts an unrelated failure")


def _verify_red(files: tuple[str, ...], expected: set[str]) -> None:
    expected_by_name = {node.rsplit("::", 1)[1]: node for node in expected}
    if len(expected_by_name) != len(expected):
        raise RedContractError("test names must be globally unique within a RED group")

    with tempfile.TemporaryDirectory(prefix="theses-red-contract-") as temporary:
        report = Path(temporary) / "pytest.xml"
        result = _run_pytest(
            [
                "-q",
                "--disable-warnings",
                "--tb=short",
                "-p",
                "no:cacheprovider",
                f"--junitxml={report}",
                *files,
            ]
        )
        if result.returncode != 1:
            raise RedContractError(
                f"pytest must exit 1 for exact expected RED, got {result.returncode}:\n{result.stdout}"
            )
        if not report.is_file():
            raise RedContractError("pytest did not produce its structured failure report")
        try:
            root = ElementTree.parse(report).getroot()
        except ElementTree.ParseError as error:
            raise RedContractError("pytest failure report is not valid XML") from error

        cases = root.findall(".//testcase")
        observed_names = [case.attrib.get("name", "") for case in cases]
        if set(observed_names) != set(expected_by_name) or len(observed_names) != len(expected):
            raise RedContractError(
                f"runtime node set changed: expected={sorted(expected_by_name)}, got={sorted(observed_names)}"
            )

        for case in cases:
            name = case.attrib["name"]
            skipped = case.find("skipped")
            failure = case.find("failure")
            error = case.find("error")
            if skipped is not None:
                raise RedContractError(f"{expected_by_name[name]} was skipped/xfailed")
            if error is not None:
                raise RedContractError(
                    f"{expected_by_name[name]} had infrastructure/collection error: {error.text or ''}"
                )
            if failure is None:
                raise RedContractError(f"{expected_by_name[name]} unexpectedly passed or xpassed")
            failure_text = "\n".join(filter(None, (failure.attrib.get("message"), failure.text)))
            if not _is_declared_missing_boundary(failure_text):
                raise RedContractError(
                    f"{expected_by_name[name]} failed for an unallowlisted reason:\n{failure_text}"
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", choices=(*GROUPS, "all"), required=True)
    arguments = parser.parse_args()

    try:
        _validate_failure_classifier()
        selected = tuple(GROUPS) if arguments.group == "all" else (arguments.group,)
        files = tuple(file_name for group in selected for file_name in GROUPS[group])
        expected = _expected_nodes(files)
        _collect(files, expected)
        _verify_red(files, expected)
    except (OSError, RedContractError) as error:
        print(f"THESIS RED CONTRACT INVALID: {error}", file=sys.stderr)
        return 1

    print(
        f"THESIS RED CONTRACT VALID: {arguments.group} has {len(expected)} exact nodes; "
        "all failures are declared missing app.theses production boundaries"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
