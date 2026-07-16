"""Strict exact-inventory verifier for intentionally RED Forecast contracts."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"

CATALOG = (
    "test_catalog_accepts_only_official_mini_small_and_base_pairings",
    "test_catalog_preserves_model_size_context_and_device_policy",
    "test_catalog_explicitly_rejects_unapproved_large_model",
    "test_catalog_freezes_source_model_and_tokenizer_revisions",
    "test_catalog_rejects_moving_or_non_commit_revisions",
    "test_catalog_rejects_missing_partial_and_tampered_files",
    "test_catalog_rejects_model_tokenizer_pair_mismatch",
    "test_catalog_rejects_paths_outside_server_owned_root",
    "test_catalog_rejects_remote_repo_or_url_as_runtime_path",
    "test_catalog_rejects_pickle_and_non_safetensors_weights",
    "test_catalog_rejects_remote_code_trust_and_network_fallback",
    "test_catalog_revalidates_integrity_before_worker_spawn",
    "test_catalog_probe_never_imports_torch_kronos_or_allocates_model",
    "test_catalog_probe_never_calls_network",
    "test_catalog_absence_returns_typed_forecast_unavailable_state",
    "test_catalog_unavailable_state_is_sanitized_and_path_free",
    "test_default_host_import_does_not_require_forecast_dependencies",
)
INPUT = (
    "test_calendar_resolves_exact_governed_5_20_and_60_future_sessions",
    "test_calendar_rejects_insufficient_future_session_coverage",
    "test_calendar_never_approximates_weekdays_or_external_holidays",
    "test_request_accepts_only_5_20_and_60_horizons",
    "test_request_forbids_browser_fingerprint_digest_scope_and_paths",
    "test_input_authorizes_one_persisted_stock_instrument",
    "test_input_rejects_index_etf_intraday_and_portfolio_batch",
    "test_input_requires_governed_daily_ohlcv_and_preserves_optional_amount",
    "test_input_rejects_missing_required_columns_without_synthesizing_values",
    "test_input_rejects_duplicate_unsorted_and_nonfinite_rows",
    "test_input_enforces_as_of_boundary_without_future_leakage",
    "test_input_rejects_insufficient_lookback_and_catalog_context",
    "test_input_freezes_adjustment_calendar_schema_and_session_provenance",
    "test_input_fingerprint_is_server_derived_complete_and_deterministic",
    "test_input_artifact_is_atomic_immutable_and_checksum_verified",
    "test_input_artifact_descriptor_is_root_contained_and_public_path_free",
)
ADAPTER = (
    "test_sample_fixture_is_exact_pre_mean_32_by_60_by_6_tensor",
    "test_sampling_configuration_freezes_seed_temperature_topk_topp_and_count",
    "test_sampling_configuration_rejects_any_count_other_than_32",
    "test_adapter_retains_all_paths_before_upstream_mean",
    "test_adapter_quantiles_are_computed_over_path_axis_zero",
    "test_mean_path_cannot_substitute_for_probabilistic_quantiles",
    "test_adapter_rejects_wrong_path_horizon_and_feature_shapes",
    "test_adapter_rejects_nan_and_infinite_outputs",
    "test_adapter_warns_for_ohlc_and_negative_volume_without_mutation",
    "test_adapter_warns_for_quantile_crossing_without_reordering",
    "test_adapter_preserves_normalization_and_inverse_normalization",
    "test_adapter_loads_only_verified_local_assets_without_remote_code_or_network",
    "test_adapter_result_manifest_is_bounded_and_contains_no_model_or_local_path",
)
RUNNER = (
    "test_same_idempotency_key_returns_same_active_job",
    "test_idempotency_identity_includes_authorized_request_scope",
    "test_job_state_machine_rejects_illegal_cas_transition",
    "test_job_cas_rejects_stale_transition_version",
    "test_job_lease_requires_owner_and_unexpired_heartbeat",
    "test_global_inference_lease_allows_exactly_one_parallel_winner",
    "test_two_parallel_job_acquisitions_have_one_cas_winner",
    "test_explicit_retry_creates_new_job_and_lineage",
    "test_retry_never_reuses_completed_forecast_record",
    "test_interruption_before_artifact_creates_no_forecast",
    "test_interruption_after_temp_artifact_creates_no_forecast_and_cleans_temp",
    "test_interruption_immediately_before_commit_creates_no_forecast",
    "test_completed_commit_atomically_creates_one_immutable_forecast",
    "test_parallel_completed_commits_return_one_canonical_forecast",
    "test_terminal_jobs_and_forecasts_are_immutable",
    "test_restart_requeues_only_valid_never_started_queued_jobs",
    "test_restart_terminalizes_expired_running_job_without_native_resume",
    "test_restart_returns_completed_record_without_rewriting_it",
    "test_runner_revalidates_authority_catalog_and_input_before_spawn",
    "test_runner_uses_spawned_parent_owned_process_group_and_one_item_queue",
    "test_runner_enforces_wall_cpu_address_thread_output_and_manifest_bounds",
    "test_runner_timeout_kills_reaps_descendants_and_cleans_temporary_files",
    "test_runner_rejects_tampered_or_oversized_manifest_without_record",
    "test_runner_maps_worker_failures_to_safe_path_free_terminal_reasons",
    "test_runner_lost_lease_rejects_late_output_and_creates_no_record",
    "test_runner_success_commits_once_and_never_invokes_downstream_authority",
)
CALIBRATION = (
    "test_maturity_resolves_nth_session_from_original_frozen_calendar_identity",
    "test_not_yet_mature_horizon_appends_no_terminal_outcome",
    "test_mature_outcome_appends_actual_session_and_fingerprint",
    "test_calibration_computes_close_mae_interval_coverage_and_pinball_losses",
    "test_calibration_fact_records_schema_sample_count_and_coverage_period",
    "test_partial_maturity_evaluates_only_due_horizons",
    "test_missing_or_nonfinite_actual_appends_unevaluable_never_zero",
    "test_duplicate_evaluation_returns_canonical_fact_without_reread",
    "test_two_parallel_scanners_append_one_outcome_and_calibration_fact",
    "test_interruption_before_terminal_append_is_retryable_without_partial_fact",
    "test_restart_releases_expired_scan_lease_and_reuses_terminal_fact",
    "test_calibration_never_rewrites_forecast_paths_quantiles_provenance_or_time",
    "test_calibration_invokes_zero_thesis_strategy_plan_monitor_position_or_broker_actions",
)
REGRESSION = ("test_pinned_local_kronos_mini_regression_denies_network_and_proves_exact_provenance",)

FILES = {
    "catalog": "tests/forecast/test_catalog.py",
    "input": "tests/forecast/test_input.py",
    "adapter": "tests/forecast/test_kronos_adapter.py",
    "runner": "tests/forecast/test_runner.py",
    "regression": "tests/forecast/test_kronos_regression.py",
    "calibration": "tests/forecast/test_calibration.py",
}
NAMES = {
    "catalog": CATALOG,
    "input": INPUT,
    "adapter": ADAPTER,
    "runner": RUNNER,
    "regression": REGRESSION,
    "calibration": CALIBRATION,
}
GROUPS = {
    "catalog-input": ("catalog", "input"),
    "adapter-runner": ("adapter", "runner", "regression"),
    "calibration": ("calibration",),
    "all": ("catalog", "input", "adapter", "runner", "regression", "calibration"),
}
ALLOWED_MISSING = {
    "catalog": ("No module named 'app.forecast", "app.forecast.catalog", "ApprovedCheckpointCatalog", "ForecastCatalogError"),
    "input": ("No module named 'app.forecast", "app.forecast.calendar", "app.forecast.input", "GovernedTradingCalendar", "ForecastInputFreezer", "ForecastRequest"),
    "adapter": ("No module named 'app.forecast", "app.forecast.kronos_adapter", "SamplingConfig", "KronosPreMeanAdapter", "validate_pre_mean_paths", "derive_quantiles", "normalize_history", "load_approved_local_pair"),
    "runner": ("No module named 'app.forecast", "app.forecast.repository", "app.forecast.runner", "ForecastRepository", "ForecastRunner", "FixedWorker", "BlockingWorker", "CrashingWorker"),
    "regression": ("No module named 'app.forecast", "app.forecast.kronos_adapter", "ApprovedLocalKronosRegression"),
    "calibration": ("No module named 'app.forecast", "app.forecast.repository", "app.forecast.calibration", "ForecastRepository", "ForecastMaturityScanner"),
}


def _nodeids(parts: tuple[str, ...]) -> set[str]:
    return {f"{FILES[part]}::{name}" for part in parts for name in NAMES[part]}


def _part_for(nodeid: str) -> str:
    for part, filename in FILES.items():
        if nodeid.startswith(filename + "::"):
            return part
    raise ValueError(f"unowned node: {nodeid}")


def _validate_fixtures() -> None:
    import numpy as np
    import polars as pl

    daily = pl.read_parquet(FIXTURES / "governed_daily.parquet")
    required_daily = {
        "case_id", "instrument_id", "symbol", "asset_type", "frequency", "session_id", "trade_date",
        "open", "high", "low", "close", "volume", "amount", "adjustment_policy", "adjustment_revision", "source_revision",
    }
    if set(daily.columns) != required_daily or not {"valid", "duplicate", "gap", "after-as-of"}.issubset(set(daily["case_id"])):
        raise SystemExit("fixture failure: governed_daily.parquet schema/cases changed")
    sessions = pl.read_parquet(FIXTURES / "cn_a_sessions.parquet")
    if set(sessions.columns) != {"calendar_id", "calendar_revision", "market", "session_id", "trade_date", "is_open", "sequence"}:
        raise SystemExit("fixture failure: cn_a_sessions.parquet schema changed")
    if sessions.filter(pl.col("calendar_id") == "cn-a-v1").height < 60:
        raise SystemExit("fixture failure: governed CN-A calendar lacks 60 future sessions")
    paths = np.load(FIXTURES / "sample_paths.npy", allow_pickle=False)
    if paths.shape != (32, 60, 6) or paths.dtype != np.float64 or not np.isfinite(paths).all():
        raise SystemExit("fixture failure: sample_paths.npy is not finite float64 [32,60,6]")
    quantiles = np.quantile(paths, [0.1, 0.5, 0.9], axis=0)
    if np.allclose(quantiles, np.stack([paths.mean(axis=0)] * 3)):
        raise SystemExit("fixture failure: path quantiles do not detect averaged-path substitution")
    actuals = pl.read_parquet(FIXTURES / "maturity_actuals.parquet")
    required_actuals = {
        "instrument_id", "calendar_revision", "session_id", "horizon", "status", "close",
        "actual_fingerprint", "coverage_start", "coverage_end", "source_revision",
    }
    if set(actuals.columns) != required_actuals or not {"available", "partial", "missing"}.issubset(set(actuals["status"])):
        raise SystemExit("fixture failure: maturity_actuals.parquet schema/cases changed")


class CapturePlugin:
    def __init__(self) -> None:
        self.collected: list[str] = []
        self.collection_failures: list[dict[str, str]] = []
        self.reports: list[dict[str, Any]] = []

    def pytest_collection_modifyitems(self, items) -> None:  # type: ignore[no-untyped-def]
        self.collected = [item.nodeid for item in items]

    def pytest_collectreport(self, report) -> None:  # type: ignore[no-untyped-def]
        if report.failed:
            self.collection_failures.append({"nodeid": report.nodeid, "detail": str(report.longrepr)})

    def pytest_runtest_logreport(self, report) -> None:  # type: ignore[no-untyped-def]
        self.reports.append({
            "nodeid": report.nodeid,
            "when": report.when,
            "outcome": report.outcome,
            "detail": getattr(report, "longreprtext", str(report.longrepr) if report.longrepr else ""),
            "wasxfail": bool(getattr(report, "wasxfail", False)),
        })


def _child_run(parts: tuple[str, ...], result_path: Path) -> None:
    import pytest

    plugin = CapturePlugin()
    arguments = [FILES[part] for part in parts] + ["-q", "--tb=short", "-p", "no:cacheprovider"]
    exit_code = int(pytest.main(arguments, plugins=[plugin]))
    result_path.write_text(json.dumps({
        "exit_code": exit_code,
        "collected": plugin.collected,
        "collection_failures": plugin.collection_failures,
        "reports": plugin.reports,
    }), encoding="utf-8")


def _verify(group: str) -> None:
    _validate_fixtures()
    parts = GROUPS[group]
    expected = _nodeids(parts)
    with tempfile.TemporaryDirectory(prefix="forecast-red-contract-") as temporary:
        result_path = Path(temporary) / "result.json"
        command = [sys.executable, str(Path(__file__).resolve()), "--_child", group, "--_result", str(result_path)]
        try:
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=45, check=False)
        except subprocess.TimeoutExpired as error:
            raise SystemExit(f"fatal timeout while executing {group}: {error}") from error
        if completed.returncode != 0 or not result_path.is_file():
            raise SystemExit(
                f"fatal pytest crash for {group} (exit {completed.returncode})\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
            )
        result = json.loads(result_path.read_text(encoding="utf-8"))
    if result["collection_failures"]:
        raise SystemExit(f"fatal collection failure: {result['collection_failures']}")
    actual = set(result["collected"])
    if actual != expected:
        raise SystemExit(
            "fatal node inventory drift\n"
            f"missing: {sorted(expected - actual)}\n"
            f"extra: {sorted(actual - expected)}"
        )
    if result["exit_code"] != 1:
        raise SystemExit(f"fatal pytest exit {result['exit_code']}; RED suite must fail only at declared production symbols")
    call_reports = {report["nodeid"]: report for report in result["reports"] if report["when"] == "call"}
    setup_failures = [report for report in result["reports"] if report["when"] != "call" and report["outcome"] == "failed"]
    if setup_failures:
        raise SystemExit(f"fatal fixture/setup/teardown failure: {setup_failures}")
    if set(call_reports) != expected:
        raise SystemExit(f"fatal missing call reports: {sorted(expected - set(call_reports))}")
    accepted_failures: list[str] = []
    accepted_skips: list[str] = []
    for nodeid in sorted(expected):
        report = call_reports[nodeid]
        if report["wasxfail"]:
            raise SystemExit(f"fatal xfail/xpass at {nodeid}")
        if report["outcome"] == "passed":
            raise SystemExit(f"fatal unexpected pass at {nodeid}")
        part = _part_for(nodeid)
        if report["outcome"] == "skipped":
            if part != "regression" or "is not configured" not in report["detail"]:
                raise SystemExit(f"fatal unexpected skip at {nodeid}: {report['detail']}")
            accepted_skips.append(nodeid)
            continue
        if report["outcome"] != "failed":
            raise SystemExit(f"fatal unexpected outcome at {nodeid}: {report['outcome']}")
        detail = report["detail"]
        if not ("ModuleNotFoundError" in detail or "ImportError" in detail):
            raise SystemExit(f"fatal non-import RED failure at {nodeid}:\n{detail}")
        if not any(token in detail for token in ALLOWED_MISSING[part]):
            raise SystemExit(f"fatal unrelated import failure at {nodeid}:\n{detail}")
        accepted_failures.append(nodeid)
    print(
        f"RED CONTRACT VERIFIED [{group}]: {len(actual)} exact nodes; "
        f"{len(accepted_failures)} declared missing-symbol failures; {len(accepted_skips)} approved offline skip."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", choices=tuple(GROUPS), default="all")
    parser.add_argument("--_child", choices=tuple(GROUPS))
    parser.add_argument("--_result", type=Path)
    arguments = parser.parse_args()
    if arguments._child:
        if arguments._result is None:
            raise SystemExit("child result path is required")
        _child_run(GROUPS[arguments._child], arguments._result)
        return
    _verify(arguments.group)


if __name__ == "__main__":
    main()
