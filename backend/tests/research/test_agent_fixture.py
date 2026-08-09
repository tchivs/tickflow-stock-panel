"""Offline fixture provider + ExperienceLibrary + resume-from-checkpoint tests.

Phase 48-04 (AF-REQ-21 recovery, AF-REQ-26 offline fixture). Covers:
* 48-04-01 -- explicit-declaration offline fixture provider + known full
  deterministic trace. Non-production label; never an implicit production
  fallback (R3 / D-48-04 / SC5).
* 48-04-02 -- ExperienceLibrary protocol + offline-fixture implementation +
  valid empty production default. Read-only seam; never a fallback response (SC4).
* 48-04-03 -- resume-from-checkpoint wiring (Phase 45 cursor reuse) + the
  end-to-end deterministic, resumable, non-production fixture-mode run.
"""
from __future__ import annotations

import json

import pytest

from app.research.repository import ResearchRepository
from app.research.run_contract import freeze_input_snapshot


# ------------------------------------------------------------------
# Shared fixtures (mirror test_agent_stage1/2.py conventions)
# ------------------------------------------------------------------


def _manifest(*, seed: int = 42) -> dict:
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


def _snapshot(*, seed: int = 42):
    return freeze_input_snapshot(
        manifest=_manifest(seed=seed), created_at="2026-08-09T00:00:00+00:00"
    )


def _make_run(repo: ResearchRepository, *, run_id: str = "run-fixture") -> str:
    snapshot = _snapshot()
    repo.create_alpha_run(
        run_id=run_id,
        principal="researcher@example.com",
        idempotency_key=f"idem-{run_id}",
        snapshot=snapshot,
        event_id=f"evt-{run_id}",
    )
    return run_id


def _make_started_run(repo: ResearchRepository, *, run_id: str = "run-fixture") -> dict:
    from app.research.run_service import ResearchRunService

    _make_run(repo, run_id=run_id)
    run = repo.get_alpha_run(run_id, principal="researcher@example.com")
    assert run is not None
    started = ResearchRunService(repo).start_or_resume(
        run_id, principal="researcher@example.com",
        expected_version=run["transition_version"],
    )
    assert started is not None
    return started


def _stage1_request():
    from app.research.agent_stage1 import StageOneRequest

    return StageOneRequest(
        thesis="Twenty-day momentum as a trend-following signal.",
        permitted_grammar={"max_depth": 4, "max_nodes": 12, "fingerprint": "a" * 64},
        permitted_fields=frozenset({"momentum_20d", "close"}),
        permitted_functions=frozenset({"rolling_mean"}),
        budget_hints={"max_expressions": 3, "max_explanation_chars": 2000},
        snapshot_ref={"snapshot_sha256": "1" * 64, "manifest_sha256": "2" * 64},
    )


def _settings(**overrides) -> dict:
    base = {"fixture_mode": True, "fixture_name": "momentum"}
    base.update(overrides)
    return base


# ==================================================================
# 48-04-01 -- explicit-declaration offline fixture provider (AF-REQ-26 §6.3)
# ==================================================================


class TestFixtureExplicitSelection:
    def test_explicit_selector_returns_true(self) -> None:
        from app.research.agent_fixture import is_fixture_explicitly_selected

        assert is_fixture_explicitly_selected(
            {"fixture_mode": True, "fixture_name": "momentum"}
        )
        assert is_fixture_explicitly_selected(
            {"fixture_mode": "1", "fixture_name": "momentum"}
        )

    @pytest.mark.parametrize(
        "settings",
        [
            None,
            {},
            {"fixture_mode": False, "fixture_name": "momentum"},
            {"fixture_mode": True, "fixture_name": ""},
            {"fixture_mode": True, "fixture_name": None},
            {"fixture_mode": True},
            {"fixture_name": "momentum"},  # missing the mode flag
            {"fixture_mode": 0, "fixture_name": "momentum"},
        ],
    )
    def test_missing_or_default_selector_returns_false(self, settings) -> None:
        from app.research.agent_fixture import is_fixture_explicitly_selected

        # A missing/default selector is NEVER an implicit fixture selection (R3).
        assert is_fixture_explicitly_selected(settings) is False


class TestFixtureConstants:
    def test_provider_and_model_constants(self) -> None:
        from app.research.agent_fixture import FIXTURE_MODEL, FIXTURE_PROVIDER

        assert FIXTURE_PROVIDER == "offline_fixture"
        assert FIXTURE_MODEL == "offline-fixture-v1"

    def test_default_fixture_shape(self) -> None:
        from app.research.agent_fixture import FixtureTrace, default_fixture

        trace = default_fixture()
        assert isinstance(trace, FixtureTrace)
        assert isinstance(trace.stage1_raw, str) and trace.stage1_raw
        assert isinstance(trace.stage2_raw, str) and trace.stage2_raw
        assert isinstance(trace.validation_trace, dict)

    def test_default_fixture_stage1_decodes_and_parses(self) -> None:
        from app.research.agent_fixture import default_fixture
        from app.research.agent_stage1 import (
            STAGE_ONE_SCHEMA_VERSION,
            decode_stage1_payload,
        )

        trace = default_fixture()
        hypotheses = decode_stage1_payload(trace.stage1_raw)
        assert hypotheses  # non-empty
        # The fixture's Stage 1 schema version matches the live contract.
        assert json.loads(trace.stage1_raw)["schema_version"] == STAGE_ONE_SCHEMA_VERSION
        # Every expression is a single server-confirmable field.
        from app.research.factor_dsl import parse_factor

        for hyp in hypotheses:
            assert parse_factor(hyp.expression).canonical_expression

    def test_default_fixture_stage2_decodes(self) -> None:
        from app.research.agent_fixture import default_fixture
        from app.research.agent_stage2 import (
            STAGE_TWO_SCHEMA_VERSION,
            decode_stage2_payload,
        )

        trace = default_fixture()
        caveats, recommendation = decode_stage2_payload(trace.stage2_raw)
        assert json.loads(trace.stage2_raw)["schema_version"] == STAGE_TWO_SCHEMA_VERSION
        # The default fixture is a clean deterministic trace (advisory only).
        assert recommendation.disposition in ("retain", "inspect")


class TestFixtureProviderDeterministicTrace:
    def test_generate_text_returns_canned_response_per_stage(self) -> None:
        import asyncio

        from app.research.agent_fixture import OfflineFixtureProvider, default_fixture

        provider = OfflineFixtureProvider()
        trace = default_fixture()
        gen1 = provider.generate_text_for("stage1")
        gen2 = provider.generate_text_for("stage2")
        assert asyncio.run(gen1([], temperature=0.0, max_tokens=1, timeout=1.0)) == trace.stage1_raw
        assert asyncio.run(gen2([], temperature=0.0, max_tokens=1, timeout=1.0)) == trace.stage2_raw

    def test_generate_text_unknown_stage_raises(self) -> None:
        import asyncio

        from app.research.agent_fixture import OfflineFixtureProvider

        provider = OfflineFixtureProvider()
        with pytest.raises(ValueError):
            asyncio.run(provider.generate_text_for("stage9")())

    def test_provider_never_performs_network_io(self, monkeypatch) -> None:
        # A fixture transport must never reach the real provider client.
        from app.services import ai_provider

        monkeypatch.setattr(ai_provider, "generate_ai_text", _raise_network_call)
        monkeypatch.setattr(ai_provider, "stream_ai_text", _raise_network_call)

        import asyncio

        from app.research.agent_fixture import OfflineFixtureProvider

        provider = OfflineFixtureProvider()
        # No exception -> the fixture returned its canned text without the network.
        out = asyncio.run(provider.generate_text_for("stage1")())
        assert isinstance(out, str)


class TestFixtureNonProductionLabel:
    def test_stage1_proposals_labeled_offline_fixture(self, tmp_path) -> None:
        from app.research.agent_fixture import (
            FIXTURE_MODEL,
            FIXTURE_PROVIDER,
            OfflineFixtureProvider,
        )
        from app.research.agent_provider import AgentProviderSeam
        from app.research.agent_stage1 import Stage1Service

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        provider = OfflineFixtureProvider()
        seam = AgentProviderSeam(generate_text=provider.generate_text_for("stage1"))
        service = Stage1Service(
            provider=FIXTURE_PROVIDER, model=FIXTURE_MODEL, model_version="offline-v1"
        )
        import asyncio

        asyncio.run(
            service.run(request=_stage1_request(), seam=seam, repo=repo, run_id=run_id)
        )
        proposals = repo.list_stage1_proposals(run_id)
        assert proposals
        assert all(p["provider"] == FIXTURE_PROVIDER for p in proposals)
        assert all(p["model"] == FIXTURE_MODEL for p in proposals)
        attempts = repo.list_analysis_attempts(run_id, stage="stage1")
        assert attempts
        assert all(a["provider"] == FIXTURE_PROVIDER for a in attempts)


class TestFixtureNeverImplicitFallback:
    def test_production_missing_provider_fails_availability_without_selector(
        self, monkeypatch
    ) -> None:
        # With NO real provider and NO explicit fixture selector, preflight
        # provider_availability FAILS (R3 / D-48-04).
        from app.research import preflight as preflight_mod
        from app.research.agent_fixture import is_fixture_explicitly_selected

        monkeypatch.setattr(
            "app.services.ai_provider.ai_configured", lambda provider=None: False
        )
        monkeypatch.setattr("app.services.ai_provider.current_ai_model", lambda: "")
        result = preflight_mod.preflight(
            _snapshot(), provider=None, fixture_selected=is_fixture_explicitly_selected(None)
        )
        provider_check = next(
            c for c in result.checks if c.name == "provider_availability"
        )
        assert provider_check.status == "fail"
        assert not result.passed

    def test_fixture_selector_passes_availability_without_provider(
        self, monkeypatch
    ) -> None:
        from app.research import preflight as preflight_mod
        from app.research.agent_fixture import is_fixture_explicitly_selected

        monkeypatch.setattr(
            "app.services.ai_provider.ai_configured", lambda provider=None: False
        )
        monkeypatch.setattr("app.services.ai_provider.current_ai_model", lambda: "")
        settings = _settings()
        result = preflight_mod.preflight(
            _snapshot(),
            provider=None,
            fixture_selected=is_fixture_explicitly_selected(settings),
        )
        provider_check = next(
            c for c in result.checks if c.name == "provider_availability"
        )
        assert provider_check.status == "pass"

    async def test_production_provider_error_never_switches_to_fixture(
        self, tmp_path
    ) -> None:
        # A production provider error raises; the fixture is NEVER selected as a
        # fallback branch (SC4 no-fallback). Zero proposal rows.
        from app.research.agent_provider import AgentProviderSeam, ProviderCallError
        from app.research.agent_stage1 import Stage1Service

        async def _boom(*_args, **_kwargs) -> str:
            raise RuntimeError("upstream production error")

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        seam = AgentProviderSeam(generate_text=_boom)
        service = Stage1Service(provider="openai", model="gpt-x", model_version="v1")
        with pytest.raises(ProviderCallError):
            await service.run(
                request=_stage1_request(), seam=seam, repo=repo, run_id=run_id
            )
        assert repo.list_stage1_proposals(run_id) == []
        # No fixture row was synthesized.
        attempts = repo.list_analysis_attempts(run_id, stage="stage1")
        assert all(a["provider"] != "offline_fixture" for a in attempts)




# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------


async def _raise_network_call(*_args, **_kwargs):
    raise AssertionError("fixture/experience seam must not perform provider I/O")
