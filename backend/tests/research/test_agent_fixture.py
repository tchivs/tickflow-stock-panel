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


# ==================================================================
# 48-04-02 -- ExperienceLibrary seam (AF-REQ-26 §8.2-8.3)
# ==================================================================


class TestDeriveFactorFamily:
    @pytest.mark.parametrize(
        "fields,expected",
        [
            ({"momentum_20d", "close"}, "momentum"),
            ({"momentum_5d", "momentum_60d"}, "momentum"),
            ({"rsi_14", "boll_upper"}, "mean-reversion"),
            ({"annual_vol_20d", "atr_14"}, "volatility"),
            ({"turnover_rate", "amount"}, "quality"),
        ],
    )
    def test_family_derived_from_permitted_fields(self, fields, expected) -> None:
        from app.research.agent_experience import derive_factor_family

        assert derive_factor_family(fields) == expected

    def test_empty_or_unknown_fields_default_momentum(self) -> None:
        from app.research.agent_experience import derive_factor_family

        assert derive_factor_family([]) == "momentum"
        assert derive_factor_family({"not_a_real_field"}) == "momentum"

    def test_dominant_family_wins_on_tie_break(self) -> None:
        from app.research.agent_experience import derive_factor_family

        # Two momentum + one volatility -> momentum dominates.
        assert derive_factor_family({"momentum_20d", "close", "atr_14"}) == "momentum"


class TestEmptyExperienceLibrary:
    def test_empty_lookup_yields_nothing(self) -> None:
        from app.research.agent_experience import EmptyExperienceLibrary

        lib = EmptyExperienceLibrary()
        assert lib.lookup(factor_family="momentum", objective="sharpe") == ()

    def test_empty_library_makes_no_provider_call(self, monkeypatch) -> None:
        from app.services import ai_provider

        monkeypatch.setattr(ai_provider, "generate_ai_text", _raise_network_call)
        from app.research.agent_experience import EmptyExperienceLibrary

        lib = EmptyExperienceLibrary()
        # Lookup completes without invoking the provider (read-only seam).
        assert lib.lookup(factor_family="momentum", objective="sharpe") == ()


class TestOfflineFixtureExperienceLibrary:
    def test_matching_key_returns_canned_entry(self) -> None:
        from app.research.agent_experience import (
            ExperienceEntry,
            OfflineFixtureExperienceLibrary,
        )

        lib = OfflineFixtureExperienceLibrary()
        entries = lib.lookup(factor_family="momentum", objective="sharpe")
        assert entries
        assert isinstance(entries[0], ExperienceEntry)
        assert entries[0].factor_family == "momentum"
        assert entries[0].objective == "sharpe"
        assert entries[0].provider == "offline_fixture"

    def test_non_matching_key_returns_nothing(self) -> None:
        from app.research.agent_experience import OfflineFixtureExperienceLibrary

        lib = OfflineFixtureExperienceLibrary()
        assert lib.lookup(factor_family="volatility", objective="sharpe") == ()
        assert lib.lookup(factor_family="momentum", objective="max_drawdown") == ()

    def test_offline_library_makes_no_provider_call(self, monkeypatch) -> None:
        from app.services import ai_provider

        monkeypatch.setattr(ai_provider, "generate_ai_text", _raise_network_call)
        from app.research.agent_experience import OfflineFixtureExperienceLibrary

        lib = OfflineFixtureExperienceLibrary()
        assert lib.lookup(factor_family="momentum", objective="sharpe")


class TestExperienceLibraryNoFallback:
    async def test_populated_library_is_not_a_fallback_response(self, tmp_path) -> None:
        # SC4: a provider failure still yields ZERO proposals even when the
        # library is populated. The library only AUGMENTS prompt context.
        from app.research.agent_provider import AgentProviderSeam, ProviderCallError
        from app.research.agent_experience import OfflineFixtureExperienceLibrary
        from app.research.agent_stage1 import Stage1Service

        async def _boom(*_args, **_kwargs) -> str:
            raise RuntimeError("upstream error")

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)
        lib = OfflineFixtureExperienceLibrary()  # populated
        seam = AgentProviderSeam(generate_text=_boom)
        # The library is wired as experience context, but the provider still fails.
        service = Stage1Service(
            provider="openai", model="gpt-x", model_version="v1",
            experience_context=lib,
        )
        with pytest.raises(ProviderCallError):
            await service.run(
                request=_stage1_request(), seam=seam, repo=repo, run_id=run_id
            )
        assert repo.list_stage1_proposals(run_id) == []

    def test_protocol_contract_allows_later_implementation(self) -> None:
        # The protocol is the only contract; a later phase can add a populated
        # implementation without touching agent_stage1/stage2.
        from app.research.agent_experience import (
            ExperienceEntry,
            ExperienceLibrary,
        )

        class _Custom(ExperienceLibrary):
            def lookup(self, *, factor_family, objective):
                return (
                    ExperienceEntry(
                        factor_family=factor_family,
                        objective=objective,
                        summary="custom",
                        provider="custom",
                        model="custom-v1",
                    ),
                )

        assert _Custom().lookup(factor_family="x", objective="y")


# ==================================================================
# 48-04-03 -- resume-from-checkpoint + e2e fixture-mode run (AF-REQ-21 §6.1)
# ==================================================================


async def _run_fixture(
    repo, run_id, started, *, stop_after_stage=None, fixture=None, settings=None
):
    from app.research.agent_fixture import OfflineFixtureProvider
    from app.research.run_service import ResearchRunService

    service = ResearchRunService(repo)
    from app.research.agent_orchestrator import run_fixture_mode as _rfm
    return await _rfm(service,
        run_id,
        principal="researcher@example.com",
        snapshot=_snapshot(),
        request=_stage1_request(),
        snapshot_ref={
            "snapshot_sha256": started["snapshot_sha256"],
            "manifest_sha256": started["manifest_sha256"],
        },
        settings=settings or _settings(),
        attempt_token=started["_attempt_token"],
        fixture=fixture or OfflineFixtureProvider(),
        stop_after_stage=stop_after_stage,
    )


class TestResumeAgentStage:
    def test_resume_no_checkpoint_returns_stage1(self, tmp_path) -> None:
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        service = ResearchRunService(repo)
        stage = service.resume_agent_stage(
            run_id,
            principal="researcher@example.com",
            expected_version=started["transition_version"],
            attempt_token=started["_attempt_token"],
        )
        assert stage == "stage1"

    async def test_resume_after_stage1_returns_stage2(self, tmp_path) -> None:
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        # Run preflight + stage1 + the stage1 boundary checkpoint, then stop.
        await _run_fixture(repo, run_id, started, stop_after_stage="stage1")
        service = ResearchRunService(repo)
        # Refresh the run row (version advanced when stage1 boundary committed).
        run = repo.get_alpha_run(run_id, principal="researcher@example.com")
        # resume reads the stage2_pending checkpoint cursor and reports stage2.
        stage = service.resume_agent_stage(
            run_id,
            principal="researcher@example.com",
            expected_version=run["transition_version"],
            attempt_token=started["_attempt_token"],
        )
        assert stage == "stage2"

    def test_resume_stale_token_rejected(self, tmp_path) -> None:
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        service = ResearchRunService(repo)
        with pytest.raises(ValueError, match="token"):
            service.resume_agent_stage(
                run_id,
                principal="researcher@example.com",
                expected_version=started["transition_version"],
                attempt_token="a-stale-token-not-the-current-one",
            )

    def test_resume_non_running_run_rejected(self, tmp_path) -> None:
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        run_id = _make_run(repo)  # still queued, never started
        service = ResearchRunService(repo)
        run = repo.get_alpha_run(run_id, principal="researcher@example.com")
        with pytest.raises(ValueError, match="running"):
            service.resume_agent_stage(
                run_id,
                principal="researcher@example.com",
                expected_version=run["transition_version"],
                attempt_token="anything",
            )


class TestFixtureModeRunE2E:
    async def test_e2e_fixture_run_full_trace_non_production(self, tmp_path) -> None:
        from app.research.agent_fixture import FIXTURE_PROVIDER

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        result = await _run_fixture(repo, run_id, started)
        assert result["stage"] == "complete"
        # preflight passed, stage1 + stage2 ran.
        attempts1 = repo.list_analysis_attempts(run_id, stage="stage1")
        attempts2 = repo.list_analysis_attempts(run_id, stage="stage2")
        assert attempts1 and attempts2
        # Every fixture AnalysisRecord is labeled non-production.
        for a in attempts1 + attempts2:
            assert a["provider"] == FIXTURE_PROVIDER
        # A validated stage2 row + the stage2 checkpoint exist.
        assert any(a["outcome"] == "validated" for a in attempts2)
        from app.research.run_service import ResearchRunService

        checkpoint = ResearchRunService(repo).get_latest_valid_checkpoint(
            run_id, principal="researcher@example.com"
        )
        assert checkpoint is not None and checkpoint["stage"] == "stage2"

    async def test_e2e_fixture_run_is_resumable_no_duplicate_side_effects(
        self, tmp_path
    ) -> None:
        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        # Run 1: preflight + stage1 + stage1 boundary, then stop.
        await _run_fixture(repo, run_id, started, stop_after_stage="stage1")
        proposals_after_stage1 = repo.list_stage1_proposals(run_id)
        assert proposals_after_stage1
        stage1_proposal_count = len(proposals_after_stage1)
        # Run 2: resume from the stage2_pending cursor and run ONLY stage2.
        run = repo.get_alpha_run(run_id, principal="researcher@example.com")
        started2 = dict(run)
        started2["_attempt_token"] = started["_attempt_token"]
        result = await _run_fixture(repo, run_id, started2)
        assert result["stage"] == "complete"
        # Stage 1 proposals were NOT recomputed (append-only idempotent read).
        assert len(repo.list_stage1_proposals(run_id)) == stage1_proposal_count
        # Stage 2 ran exactly once (one validated row).
        attempts2 = repo.list_analysis_attempts(run_id, stage="stage2")
        assert sum(1 for a in attempts2 if a["outcome"] == "validated") == 1

    async def test_e2e_fixture_run_byte_identical_across_two_runs(self, tmp_path) -> None:
        from app.research.agent_fixture import OfflineFixtureProvider

        def _checksums(repo, run_id):
            rows = repo.list_analysis_attempts(run_id)
            return {
                "stage1_response": next(
                    (r["response_sha256"] for r in rows if r["stage"] == "stage1"), None
                ),
                "stage1_request": next(
                    (r["request_scope_sha256"] for r in rows if r["stage"] == "stage1"), None
                ),
                "stage2_response": next(
                    (r["response_sha256"] for r in rows if r["stage"] == "stage2"), None
                ),
                "stage2_parsed": next(
                    (r["parsed_output_sha256"] for r in rows if r["stage"] == "stage2"), None
                ),
            }

        # Run A.
        repo_a = ResearchRepository(tmp_path / "a.db")
        repo_a.migrate()
        started_a = _make_started_run(repo_a, run_id="run-a")
        await _run_fixture(repo_a, "run-a", started_a, fixture=OfflineFixtureProvider())
        sums_a = _checksums(repo_a, "run-a")
        # Run B (independent DB, same fixture + request).
        repo_b = ResearchRepository(tmp_path / "b.db")
        repo_b.migrate()
        started_b = _make_started_run(repo_b, run_id="run-b")
        await _run_fixture(repo_b, "run-b", started_b, fixture=OfflineFixtureProvider())
        sums_b = _checksums(repo_b, "run-b")
        # The fixture produces byte-identical AnalysisRecord traces.
        assert sums_a == sums_b

    async def test_e2e_fixture_requires_explicit_selector(self, tmp_path) -> None:
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        service = ResearchRunService(repo)
        with pytest.raises(ValueError, match="explicit"):
            from app.research.agent_orchestrator import run_fixture_mode as _rfm2
            await _rfm2(service,
                run_id,
                principal="researcher@example.com",
                snapshot=_snapshot(),
                request=_stage1_request(),
                snapshot_ref={
                    "snapshot_sha256": started["snapshot_sha256"],
                    "manifest_sha256": started["manifest_sha256"],
                },
                settings={},  # no explicit selector -> fail closed
                attempt_token=started["_attempt_token"],
            )

    async def test_e2e_fixture_run_idempotent_full(self, tmp_path) -> None:
        # Re-running a completed fixture run is a no-op (no duplicate rows).
        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        await _run_fixture(repo, run_id, started)
        attempts_before = len(repo.list_analysis_attempts(run_id))
        proposals_before = len(repo.list_stage1_proposals(run_id))
        run = repo.get_alpha_run(run_id, principal="researcher@example.com")
        started2 = dict(run)
        started2["_attempt_token"] = started["_attempt_token"]
        result = await _run_fixture(repo, run_id, started2)
        assert result["stage"] == "complete"
        assert len(repo.list_analysis_attempts(run_id)) == attempts_before
        assert len(repo.list_stage1_proposals(run_id)) == proposals_before


class TestFixtureModeRunResumeBoundaryTokenFence:
    async def test_stage2_boundary_with_stale_token_rejected_on_resume(
        self, tmp_path
    ) -> None:
        # After resume fences the old token, a Stage 2 boundary written under
        # the stale token is rejected by expected_attempt_token_digest.
        from app.research.run_service import ResearchRunService

        repo = ResearchRepository(tmp_path / "operational.db")
        repo.migrate()
        started = _make_started_run(repo)
        run_id = started["id"]
        await _run_fixture(repo, run_id, started, stop_after_stage="stage1")
        service = ResearchRunService(repo)
        run = repo.get_alpha_run(run_id, principal="researcher@example.com")
        # Recover fences the original token; the recovered token is fresh.
        recovered = service.recover_running_attempt(
            run_id,
            principal="researcher@example.com",
            expected_version=run["transition_version"],
        )
        assert recovered is not None
        # The OLD token is now stale; resume_agent_stage rejects it.
        with pytest.raises(ValueError, match="token"):
            service.resume_agent_stage(
                run_id,
                principal="researcher@example.com",
                expected_version=run["transition_version"],
                attempt_token=started["_attempt_token"],
            )
