"""Pure fail-closed preflight gate contracts (AF-REQ-11, Phase 48-01-01).

Verifies every AF-REQ-11 capability maps to an observable, independently
failable check with a bounded machine-readable reason, that a failed preflight
makes zero provider calls (SC1), and that folded capabilities expose distinct
sub-reason failure modes (plan-check W2).
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from app.research import factor_dsl
from app.research.preflight import PreflightCheck, PreflightResult, preflight
from app.research.run_contract import ResearchInputSnapshot, freeze_input_snapshot


def _manifest(*, seed: int = 42) -> dict:
    """A complete D-04 manifest that freezes cleanly under the live DSL/admission."""
    return {
        "dsl": {"version": "factor-dsl-v1"},
        "grammar": {"fingerprint": "a" * 64, "version": "grammar-v1"},
        "vocabulary": {"fingerprint": "b" * 64, "size": 64},
        "policy": {"version": "admission-v1", "thresholds": {"min_ic": 0.02}},
        "budgets": {"max_expressions": 1000, "max_candidates": 200},
        "objective": {"name": "sharpe", "direction": "maximize"},
        "universe": {
            "name": "cn-a-share",
            "asset_type": "stock",
            "membership_fingerprint": "c" * 64,
        },
        "measured_window": {"start": "2020-01-01", "end": "2023-12-31", "calendar": "SSE"},
        "fold_geometry": {"train_size": 120, "gap_size": 5, "test_size": 20, "n_folds": 10},
        "code_manifest": {
            "fingerprint": "d" * 64,
            "build_fingerprint": "e" * 64,
            "dependency_fingerprint": "f" * 64,
        },
        "data_manifest": {"fingerprint": "g" * 64, "partition_fingerprint": "h" * 64},
        "seed": seed,
    }


def _snapshot(manifest: dict | None = None) -> ResearchInputSnapshot:
    return freeze_input_snapshot(
        manifest=manifest or _manifest(),
        created_at="2026-08-09T00:00:00+00:00",
    )


def _check_names(result: PreflightResult) -> list[str]:
    return [check.name for check in result.checks]


def _failed_names(result: PreflightResult) -> list[str]:
    return [check.name for check in result.failed()]


# ------------------------------------------------------------------
# Happy path + structure
# ------------------------------------------------------------------


class TestPreflightHappyPath:
    def test_passes_on_a_clean_frozen_snapshot_with_fixture(self) -> None:
        result = preflight(_snapshot(), fixture_selected=True)
        assert result.passed is True
        assert _check_names(result) == [
            "data_availability_freshness",
            "measured_calendar",
            "pit_universe_scope",
            "required_fields_sample_length",
            "dsl_grammar_compatibility",
            "budgets",
            "provider_availability",
            "policy_mode",
        ]
        for check in result.checks:
            assert check.status == "pass"
            assert check.reason is None

    def test_result_is_pure_byte_identical_across_calls(self) -> None:
        snapshot = _snapshot()
        first = preflight(snapshot, fixture_selected=True)
        second = preflight(snapshot, fixture_selected=True)
        assert first == second
        # Tuple of checks compares element-wise (frozen dataclasses + mappings).
        assert first.checks == second.checks


# ------------------------------------------------------------------
# SC1 — a failed preflight makes zero provider calls
# ------------------------------------------------------------------


class TestPreflightNoProviderCallOnFail:
    def test_failed_preflight_never_calls_generate_ai_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services import ai_provider

        calls: list[int] = []

        def _must_not_be_called(*args: object, **kwargs: object) -> object:
            calls.append(1)
            raise AssertionError("preflight must not call the provider")

        monkeypatch.setattr(ai_provider, "generate_ai_text", _must_not_be_called)
        # A snapshot with a tampered policy fingerprint so the gate fails.
        snapshot = _snapshot()
        tampered_manifest = dict(snapshot.manifest)
        policy = dict(tampered_manifest["policy"])
        policy["fingerprint"] = "0" * 64
        tampered_manifest["policy"] = policy
        tampered = replace(snapshot, manifest=tampered_manifest)

        result = preflight(tampered, fixture_selected=True)
        assert result.passed is False
        assert "policy_mode" in _failed_names(result)
        assert calls == []

    def test_provider_availability_fails_without_provider_or_fixture(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services import ai_provider

        monkeypatch.setattr(ai_provider, "ai_configured", lambda provider=None: False)
        monkeypatch.setattr(ai_provider, "current_ai_model", lambda: "")
        result = preflight(_snapshot(), provider=None, fixture_selected=False)
        assert result.passed is False
        assert "provider_availability" in _failed_names(result)
        assert result.failed()[0].reason["code"] == "provider_unavailable"

    def test_provider_availability_passes_with_explicit_fixture(self) -> None:
        result = preflight(_snapshot(), fixture_selected=True)
        assert result.passed is True
        provider_check = next(c for c in result.checks if c.name == "provider_availability")
        assert provider_check.status == "pass"


# ------------------------------------------------------------------
# Independent failure — each capability flips exactly one check
# ------------------------------------------------------------------


class TestPreflightIndependentFailure:
    def test_data_fingerprint_mismatch_flips_only_data_check(self) -> None:
        snapshot = _snapshot()
        tampered = replace(
            snapshot, component_digests={**snapshot.component_digests, "data": "0" * 64}
        )
        result = preflight(tampered, fixture_selected=True)
        assert _failed_names(result) == ["data_availability_freshness"]
        check = result.failed()[0]
        assert check.reason["sub_reason"] == "data_fingerprint"

    def test_partition_fingerprint_mismatch_flips_only_data_check(self) -> None:
        snapshot = _snapshot()
        tampered = replace(
            snapshot, component_digests={**snapshot.component_digests, "partition": "0" * 64}
        )
        result = preflight(tampered, fixture_selected=True)
        assert _failed_names(result) == ["data_availability_freshness"]
        assert result.failed()[0].reason["sub_reason"] == "partition_fingerprint"

    def test_measured_calendar_invalid_flips_only_calendar_check(self) -> None:
        manifest = _manifest()
        manifest["fold_geometry"]["n_folds"] = 0
        result = preflight(_snapshot(manifest), fixture_selected=True)
        assert _failed_names(result) == ["measured_calendar"]
        assert result.failed()[0].reason["code"] == "fold_geometry_invalid"

    def test_membership_fingerprint_mismatch_flips_only_universe_check(self) -> None:
        snapshot = _snapshot()
        tampered = replace(
            snapshot, component_digests={**snapshot.component_digests, "membership": "0" * 64}
        )
        result = preflight(tampered, fixture_selected=True)
        assert _failed_names(result) == ["pit_universe_scope"]
        assert result.failed()[0].reason["code"] == "membership_fingerprint_mismatch"

    def test_sample_too_short_flips_only_required_fields_check(self) -> None:
        manifest = _manifest()
        # Window far shorter than the training fold (120 days).
        manifest["measured_window"] = {"start": "2023-12-30", "end": "2023-12-31", "calendar": "SSE"}
        result = preflight(_snapshot(manifest), fixture_selected=True)
        assert _failed_names(result) == ["required_fields_sample_length"]
        assert result.failed()[0].reason["sub_reason"] == "sample_length"

    def test_no_allowed_fields_flips_only_required_fields_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(factor_dsl, "ALLOWED_FIELDS", frozenset())
        result = preflight(_snapshot(), fixture_selected=True)
        assert _failed_names(result) == ["required_fields_sample_length"]
        assert result.failed()[0].reason["sub_reason"] == "required_fields"

    def test_vocabulary_drift_flips_only_grammar_check(self) -> None:
        snapshot = _snapshot()
        tampered_manifest = dict(snapshot.manifest)
        vocabulary = dict(tampered_manifest["vocabulary"])
        vocabulary["fingerprint"] = "0" * 64
        tampered_manifest["vocabulary"] = vocabulary
        tampered = replace(snapshot, manifest=tampered_manifest)
        result = preflight(tampered, fixture_selected=True)
        assert _failed_names(result) == ["dsl_grammar_compatibility"]
        assert result.failed()[0].reason["sub_reason"] == "vocabulary"

    def test_grammar_drift_flips_only_grammar_check(self) -> None:
        snapshot = _snapshot()
        tampered_manifest = dict(snapshot.manifest)
        grammar = dict(tampered_manifest["grammar"])
        grammar["fingerprint"] = "0" * 64
        tampered_manifest["grammar"] = grammar
        tampered = replace(snapshot, manifest=tampered_manifest)
        result = preflight(tampered, fixture_selected=True)
        assert _failed_names(result) == ["dsl_grammar_compatibility"]
        assert result.failed()[0].reason["sub_reason"] == "grammar"

    def test_budgets_unparseable_flips_only_budgets_check(self) -> None:
        manifest = _manifest()
        manifest["budgets"]["max_candidates"] = 0
        result = preflight(_snapshot(manifest), fixture_selected=True)
        assert _failed_names(result) == ["budgets"]
        assert result.failed()[0].reason["code"] == "budgets_unparseable"

    def test_policy_drift_flips_only_policy_check(self) -> None:
        snapshot = _snapshot()
        tampered_manifest = dict(snapshot.manifest)
        policy = dict(tampered_manifest["policy"])
        policy["fingerprint"] = "0" * 64
        tampered_manifest["policy"] = policy
        tampered = replace(snapshot, manifest=tampered_manifest)
        result = preflight(tampered, fixture_selected=True)
        assert _failed_names(result) == ["policy_mode"]
        assert result.failed()[0].reason["code"] == "policy_mismatch"


# ------------------------------------------------------------------
# Reason shape — bounded, machine-readable
# ------------------------------------------------------------------


class TestPreflightReasonShape:
    def test_failed_reason_is_bounded_mapping(self) -> None:
        snapshot = _snapshot()
        tampered = replace(
            snapshot, component_digests={**snapshot.component_digests, "data": "0" * 64}
        )
        result = preflight(tampered, fixture_selected=True)
        reason = result.failed()[0].reason
        assert isinstance(reason, dict)
        assert "code" in reason
        # No raw text echo beyond bounded scalars.
        assert all(isinstance(k, str) for k in reason)

    def test_preflight_rejects_non_snapshot(self) -> None:
        with pytest.raises(TypeError):
            preflight({"not": "a snapshot"}, fixture_selected=True)  # type: ignore[arg-type]
