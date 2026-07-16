#!/usr/bin/env python3
"""Strict Shadow RED-contract verifier.

A zero exit means every declared node collected and failed only because its exact
future ``app.shadow`` production boundary is absent. Any other RED is rejected.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[2]
SHADOW_ROOT = Path(__file__).resolve().parent
FIXTURE_ROOT = SHADOW_ROOT / "fixtures"

GROUPS: dict[str, tuple[str, ...]] = {
    "import-evidence": (
        "tests/shadow/test_imports.py",
        "tests/shadow/test_evidence_sets.py",
    ),
    "distillation-evaluation": (
        "tests/shadow/test_distillation.py",
        "tests/shadow/test_evaluation_retention.py",
    ),
}

EXPECTED_NODES: dict[str, tuple[str, ...]] = {
    "tests/shadow/test_imports.py": (
        "test_preview_accepts_only_bounded_local_csv_xlsx_and_preserves_source_values",
        "test_preview_normalizes_gb18030_time_and_keeps_partial_and_duplicate_rows",
        "test_rejects_extension_media_archive_and_preparse_limits_without_parser_work",
        "test_formula_macro_and_hostile_path_cells_are_never_executed_or_used_as_paths",
        "test_confirm_creates_atomic_server_owned_artifact_and_safe_projection",
        "test_same_content_retry_and_correction_append_distinct_attributable_batches",
        "test_parser_failure_records_safe_diagnostic_and_cleans_temporary_paths",
        "test_raw_artifact_tamper_and_partial_files_fail_closed",
        "test_public_import_contract_has_no_broker_manual_or_live_account_authority",
    ),
    "tests/shadow/test_evidence_sets.py": (
        "test_evidence_set_freezes_exact_batch_trade_manifest_and_stable_fingerprint",
        "test_evidence_set_preserves_partial_fills_duplicate_groups_and_row_identity",
        "test_rejected_or_partial_batch_cannot_enter_evidence_set_silently",
        "test_evidence_exclusions_name_exact_trade_and_nonempty_reason",
        "test_evidence_set_and_membership_reject_direct_update_and_delete",
        "test_correction_creates_new_manifest_while_earlier_evidence_remains_readable_and_safe",
    ),
    "tests/shadow/test_distillation.py": (
        "test_distillation_uses_only_server_governed_features_and_deterministic_negatives",
        "test_distillation_enforces_fixed_seed_shallow_depth_leaf_support_and_class_balance",
        "test_candidate_is_complete_versioned_attributable_and_explainable",
        "test_rule_validator_rejects_unsupported_fields_operators_and_nonfinite_thresholds",
        "test_exported_canonical_rules_replay_equivalently_without_estimator",
        "test_persisted_candidate_contains_no_estimator_pickle_joblib_source_import_or_callable",
        "test_invalid_or_insufficient_training_input_creates_no_candidate_fact",
    ),
    "tests/shadow/test_evaluation_retention.py": (
        "test_evaluation_freezes_separate_chronological_nonoverlapping_is_and_oos_runs",
        "test_each_split_records_independent_fingerprint_artifact_status_and_complete_metrics",
        "test_full_sample_random_or_overlapping_windows_cannot_substitute_for_two_splits",
        "test_failure_timeout_and_resource_retry_append_a_new_run_without_partial_evidence",
        "test_retention_requires_canonical_passing_terminal_is_and_oos_for_same_candidate",
        "test_duplicate_retention_is_replay_safe_and_atomic",
        "test_failed_timeout_resource_or_oos_fail_evaluations_are_ineligible",
        "test_retention_invokes_zero_strategy_monitor_plan_position_ledger_broker_or_market_actions",
        "test_evaluation_and_retention_projections_hide_paths_secrets_tracebacks_and_client_verdicts",
    ),
}

FIXTURE_HASHES = {
    "executions_utf8.csv": "9ccd5d7774337bce433b59fb6eb8750ba50b2ecc9dfd7ed3362b21dad050712b",
    "executions_gb18030.csv": "f18f011fe8ea66793502aaaafd867f29acc55a82c58e8bfa3e078c9abe6d697c",
    "executions.xlsx": "c38619d497c6d863db5dcf23c8b54ec11d8fe10332de952116bcde6b059bb972",
}

ALLOWED_IMPORTS: dict[str, frozenset[str]] = {
    "app.shadow.importer": frozenset({"ShadowImporter", "ShadowImportLimits", "ShadowImportError"}),
    "app.shadow.artifacts": frozenset({"ShadowArtifactStore", "ShadowArtifactError"}),
    "app.shadow.repository": frozenset({"ShadowRepository", "ShadowEvidenceError"}),
    "app.shadow.distillation": frozenset({"ShadowDistiller", "ShadowDistillationError", "ShadowRuleValidator"}),
    "app.shadow.evaluation": frozenset({"ShadowEvaluationService", "ShadowEvaluationError"}),
    "app.shadow.service": frozenset({"ShadowService", "ShadowRetentionError"}),
}

MISSING_MODULE = re.compile(
    r"^(?:E\s+)?ModuleNotFoundError: No module named "
    r"['\"](?P<module>app\.shadow(?:\.[A-Za-z_]\w*)*)['\"]$"
)
MISSING_SYMBOL = re.compile(
    r"^(?:E\s+)?ImportError: cannot import name ['\"](?P<symbol>[A-Za-z_]\w*)['\"] from "
    r"['\"](?P<module>app\.shadow(?:\.[A-Za-z_]\w*)*)['\"](?: .*)?$"
)
UNALLOWLISTED_EXCEPTION = re.compile(
    r"(?:AssertionError|SyntaxError|FixtureLookupError|NameError|TypeError|ValueError|"
    r"RuntimeError|TimeoutError|Failed:|XPASS|XFAIL)"
)


class RedContractError(RuntimeError):
    pass


def _expected_nodes(files: tuple[str, ...]) -> set[str]:
    return {
        f"{file_name}::{test_name}"
        for file_name in files
        for test_name in EXPECTED_NODES[file_name]
    }


def _validate_fixtures() -> None:
    actual_names = {path.name for path in FIXTURE_ROOT.iterdir() if path.is_file()}
    if actual_names != set(FIXTURE_HASHES):
        raise RedContractError(
            f"fixture inventory changed: expected {sorted(FIXTURE_HASHES)}, got {sorted(actual_names)}"
        )
    for name, expected_hash in FIXTURE_HASHES.items():
        actual_hash = hashlib.sha256((FIXTURE_ROOT / name).read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise RedContractError(f"fixture digest changed for {name}: {actual_hash}")

    expected_header = [
        "成交编号", "证券代码", "买卖方向", "成交时间", "成交数量",
        "成交价格", "手续费", "币种", "账户别名", "备注",
    ]
    decoded: list[list[list[str]]] = []
    for name, encoding in (("executions_utf8.csv", "utf-8"), ("executions_gb18030.csv", "gb18030")):
        rows = list(csv.reader(io.StringIO((FIXTURE_ROOT / name).read_bytes().decode(encoding))))
        if rows[0] != expected_header or len(rows) != 8 or any(len(row) != 10 for row in rows):
            raise RedContractError(f"fixture shape invalid for {name}")
        decoded.append(rows)
    if decoded[0] != decoded[1]:
        raise RedContractError("UTF-8 and GB18030 fixtures do not describe identical executions")
    body = decoded[0][1:]
    if [body[1][4], body[2][4]] != ["40", "60"]:
        raise RedContractError("partial-fill fixture rows changed")
    if body[3][0] or body[4][0] or body[3][1:9] != body[4][1:9]:
        raise RedContractError("duplicate-without-fill-id fixture rows changed")
    if not body[5][9].startswith("=HYPERLINK("):
        raise RedContractError("formula-shaped data fixture disappeared")
    if "../../../../etc/passwd" not in body[6][9] or "Auto_Open" not in body[6][9] or len(body[6][9]) < 300:
        raise RedContractError("hostile path/macro/long-cell fixture disappeared")

    with zipfile.ZipFile(FIXTURE_ROOT / "executions.xlsx") as workbook:
        names = set(workbook.namelist())
        required = {"[Content_Types].xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml"}
        if not required.issubset(names):
            raise RedContractError("XLSX fixture package is incomplete")
        if any(Path(name).is_absolute() or ".." in Path(name).parts for name in names):
            raise RedContractError("XLSX fixture has an unsafe member path")
        if any("vbaProject" in name for name in names):
            raise RedContractError("XLSX fixture unexpectedly contains a macro project")
        if sum(item.file_size for item in workbook.infolist()) > 1_000_000:
            raise RedContractError("XLSX fixture exceeds the bounded package size")
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
        namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        texts = [node.text or "" for node in sheet.findall(".//x:t", namespace)]
        if sheet.findall(".//x:f", namespace):
            raise RedContractError("XLSX fixture contains executable formula nodes")
        if not any(text.startswith("=HYPERLINK(") for text in texts):
            raise RedContractError("XLSX formula-shaped literal is missing")
        if not any("Auto_Open" in text and "../../../../etc/passwd" in text for text in texts):
            raise RedContractError("XLSX hostile literal is missing")


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
    result = _run_pytest(["--collect-only", "-q", *files])
    if result.returncode != 0:
        raise RedContractError(f"pytest collection failed:\n{result.stdout}")
    collected = {
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith("tests/shadow/") and "::" in line
    }
    if collected != expected:
        missing = sorted(expected - collected)
        extra = sorted(collected - expected)
        raise RedContractError(f"node inventory changed; missing={missing}, extra={extra}")


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
        return module == "app.shadow" or module in ALLOWED_IMPORTS
    return symbol in ALLOWED_IMPORTS.get(module, frozenset())


def _validate_failure_classifier() -> None:
    accepted = (
        "ModuleNotFoundError: No module named 'app.shadow'",
        "E   ModuleNotFoundError: No module named 'app.shadow.importer'",
        "ImportError: cannot import name 'ShadowImporter' from 'app.shadow.importer' (/tmp/importer.py)",
    )
    rejected = (
        "AssertionError: No module named 'app.shadow'",
        "SyntaxError: invalid syntax\nModuleNotFoundError: No module named 'app.shadow'",
        "FixtureLookupError: fixture 'shadow_repo' not found",
        "ModuleNotFoundError: No module named 'sklearn'",
        "ImportError: cannot import name 'BrokerClient' from 'app.shadow.importer'",
        "XPASS app.shadow production unexpectedly exists",
    )
    if not all(_is_declared_missing_boundary(item) for item in accepted):
        raise RedContractError("RED failure classifier rejects a declared production boundary")
    if any(_is_declared_missing_boundary(item) for item in rejected):
        raise RedContractError("RED failure classifier accepts an unrelated failure")


def _verify_red(files: tuple[str, ...], expected: set[str]) -> None:
    expected_by_name = {node.rsplit("::", 1)[1]: node for node in expected}
    if len(expected_by_name) != len(expected):
        raise RedContractError("test names must be globally unique within a RED group")

    with tempfile.TemporaryDirectory(prefix="shadow-red-contract-") as temporary:
        report = Path(temporary) / "pytest.xml"
        result = _run_pytest([
            "-q", "--disable-warnings", "--tb=short", f"--junitxml={report}", *files,
        ])
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
    args = parser.parse_args()

    try:
        _validate_failure_classifier()
        _validate_fixtures()
        selected = tuple(GROUPS) if args.group == "all" else (args.group,)
        files = tuple(file_name for group in selected for file_name in GROUPS[group])
        expected = _expected_nodes(files)
        _collect(files, expected)
        _verify_red(files, expected)
    except (OSError, RedContractError, zipfile.BadZipFile) as error:
        print(f"SHADOW RED CONTRACT INVALID: {error}", file=sys.stderr)
        return 1

    print(
        f"SHADOW RED CONTRACT VALID: {args.group} has {len(expected)} exact nodes; "
        "all failures are declared missing app.shadow production boundaries"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
