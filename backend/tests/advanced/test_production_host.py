"""Production-lifespan proofs for advanced research routes."""
from __future__ import annotations

import json
import time
from hashlib import sha256
from types import SimpleNamespace

from fastapi.testclient import TestClient


class _AffirmativeSandboxLauncher:
    """Test-only proven launcher contract; production owns the Linux implementation."""

    terminal_outcome_contract = True

    def capability_probe(self, *, governed_input, workdir):
        del governed_input, workdir
        return SimpleNamespace(
            user_namespace=True,
            mount_namespace=True,
            pid_namespace=True,
            network_namespace=True,
            network_absent=True,
            private_root=True,
            governed_input_read_only=True,
            temporary_workdir_only=True,
            resource_limits=True,
            cleanup_verified=True,
            proof_fingerprint="proof-fixture",
        )

    def spawn(self, **kwargs):
        del kwargs
        return {
            "status": "completed",
            "proof_fingerprint": "proof-fixture",
            "resources": {"wall_clock_seconds": 5, "memory_limit_mb": 128},
            "audit_reference": "runner-fixture",
        }


def _sandbox_submission() -> dict[str, object]:
    source = "def run(panel):\n    return {'signal': 'hold'}\n"
    return {
        "contract": {
            "contract_version": "advanced-strategy-v1",
            "parent_asset_id": "registered-research-asset-v1",
            "declared_inputs": ["governed_panel"],
            "declared_imports": [],
            "timeout_seconds": 5,
            "memory_limit_mb": 128,
            "source_sha256": sha256(source.encode()).hexdigest(),
        },
        "source": source,
    }


def _strategy_scope() -> dict[str, object]:
    return {
        "market": "CN-A",
        "strategy_id": "fixture_momentum",
        "start": "2024-01-02",
        "end": "2024-12-31",
        "symbols": ["600000.SH"],
        "asset_type": "stock",
        "parameters": {"lookback": 20},
    }


def _advanced_host_fixture() -> dict[str, object]:
    return {
        "policy": {
            "version": "advanced_policy_v1",
            "source_profiles": {"operator-research-v1": {"market_scopes": ["CN-A"]}},
            "benchmark_defaults": {"stock": "000300.SH", "etf": "000300.SH", "index": "000001.SH"},
            "benchmark_overrides": ["000300.SH", "000905.SH", "000852.SH"],
            "agent_allowlist": {"research_draft": ["CN-A"], "experiment": ["CN-A"], "strategy_evaluation": ["CN-A"]},
            "rate_limits": {"research_draft": 1, "experiment": 1, "strategy_evaluation": 1},
        },
        "advanced_subjects": ["600000.SH"],
    }


class _DeterministicGovernedCollaborator:
    def run(self, *, specification: dict[str, object]) -> dict[str, object]:
        del specification
        return {
            "governed_input_manifest": {
                "source": "governed_backtest_engine",
                "revision": "fixture-revision",
                "fingerprint": "fixture-fingerprint",
            },
            "asset_version": "fixture-asset-v1",
            "resolved_parameters": {"lookback": 20},
            "environment": {"runner": "fixture"},
            "metrics": {"sharpe": 1.2},
            "artifacts": [{"reference": "fixture-metrics", "checksum": "a" * 64}],
            "evolution_evidence": {
                "split": {
                    "in_sample": {"start": "2024-01-02", "end": "2024-06-30", "metrics": {"sharpe": 1.1}},
                    "out_of_sample": {"start": "2024-07-01", "end": "2024-12-31", "metrics": {"sharpe": 1.2}},
                },
                "robustness_trials": [{"reference": "fixture-trial", "status": "completed", "metrics": {"sharpe": 1.1}, "threshold_met": True}],
                "cost_feasibility": {
                    "fee_model": "cn-a-v1",
                    "commission": 0.0003,
                    "slippage": 0.0005,
                    "capacity_assumptions": {"participation_rate": 0.1},
                    "net_metrics": {"sharpe": 1.05},
                    "capacity_result": "feasible",
                    "threshold_met": True,
                },
            },
        }


class _BlockingGovernedCollaborator:
    def run(self, *, specification: dict[str, object]) -> dict[str, object]:
        del specification
        time.sleep(10)
        return {}


def test_affirmative_isolation_proof_records_one_safe_terminal_sandbox_run(tmp_path):
    from app.advanced.sandbox import CustomStrategySandboxService

    service = CustomStrategySandboxService(
        audit_path=tmp_path / "operational.db",
        governed_input=tmp_path / "governed-data",
        launcher=_AffirmativeSandboxLauncher(),
    )

    result = service.submit(_sandbox_submission())

    assert result == {
        "status": "completed",
        "proof_fingerprint": "proof-fixture",
        "resources": {"wall_clock_seconds": 5, "memory_limit_mb": 128},
        "terminal_reason": None,
        "audit_reference": result["audit_reference"],
        "run_id": result["run_id"],
        "created_at": result["created_at"],
    }
    assert service.public_run(result["run_id"]) == result


def test_main_host_installs_only_the_fail_closed_linux_isolation_launcher(tmp_path, monkeypatch):
    from app.advanced.sandbox import LinuxIsolationLauncher
    from app.config import settings
    from app.services import auth as auth_service
    from tests.test_analysis_host_integration import _write_phase1_fixture

    fixture_dir = tmp_path / "phase1-fixtures"
    data_dir = tmp_path / "governed-data"
    _write_phase1_fixture(fixture_dir)
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "1")
    monkeypatch.setenv("PHASE1_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setattr(settings, "auth_password", "host-test-password")
    monkeypatch.setattr(auth_service, "_configured_cache", None)
    auth_service._sessions.clear()

    from app.main import app

    with TestClient(app):
        service = app.state.advanced_sandbox_service
        assert isinstance(service._launcher, LinuxIsolationLauncher)
        result = service.submit(_sandbox_submission())
        if result["status"] == "rejected":
            assert result["reason"] == "isolation_unavailable"
        else:
            assert result["status"] in {"completed", "failed"}
            assert result["run_id"]
            assert result["proof_fingerprint"]


def _viewpoint_payload(*, instrument: str) -> dict[str, object]:
    return {
        "source_profile": "operator-research-v1",
        "market_scope": "CN-A",
        "asset_type": "stock",
        "instrument": instrument,
        "published_at": "2026-01-02T00:00:00+00:00",
        "direction": "bullish",
        "conclusion": "受控研究观点",
        "rating": "overweight",
        "target_range": [1500, 1600],
        "horizon_days": 60,
        "confidence": "high",
        "evidence": [{"id": "filing-1"}],
        "evaluation_window_days": 60,
    }


def test_main_host_exposes_governed_viewpoint_snapshot_from_the_lifespan(tmp_path, monkeypatch):
    from app.config import settings
    from app.services import auth as auth_service
    from tests.test_analysis_host_integration import _write_phase1_fixture

    fixture_dir = tmp_path / "phase1-fixtures"
    data_dir = tmp_path / "governed-data"
    _write_phase1_fixture(fixture_dir)
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "1")
    monkeypatch.setenv("PHASE1_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setattr(settings, "auth_password", "host-test-password")
    monkeypatch.setattr(auth_service, "_configured_cache", None)
    auth_service._sessions.clear()

    from app.main import app

    with TestClient(app):
        snapshot = app.state.viewpoint_market_snapshot
        assert snapshot.evaluate_viewpoint({
            "instrument": "600000.SH",
            "benchmark": "000300.SH",
            "asset_type": "stock",
            "published_at": "2024-01-02T00:00:00+00:00",
            "evaluation_window_days": 20,
        }) == {"status": "unevaluable", "reason": "missing_price"}


def test_main_host_loads_and_persists_deployment_owned_advanced_fixture(tmp_path, monkeypatch):
    from app.config import settings
    from app.services import auth as auth_service
    from tests.test_analysis_host_integration import _write_phase1_fixture

    fixture_dir = tmp_path / "phase1-fixtures"
    data_dir = tmp_path / "governed-data"
    advanced_fixture = tmp_path / "advanced-host-fixture.json"
    _write_phase1_fixture(fixture_dir)
    advanced_fixture.write_text(json.dumps(_advanced_host_fixture()), encoding="utf-8")
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "1")
    monkeypatch.setenv("PHASE1_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setenv("ADVANCED_HOST_FIXTURE", str(advanced_fixture))
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setattr(settings, "auth_password", "host-test-password")
    monkeypatch.setattr(auth_service, "_configured_cache", None)
    auth_service._sessions.clear()

    from app.main import app

    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"password": "host-test-password"}).status_code == 200
        allowed = client.post("/api/advanced/subjects/600000.SH/jobs", json={"task_type": "research_draft"})
        denied = client.post("/api/advanced/subjects/000001.SZ/jobs", json={"task_type": "research_draft"})

        assert allowed.status_code == 200
        assert denied.status_code == 404
        job = allowed.json()["job"]
        persisted = app.state.advanced_repository.get_job(job["id"])
        assert persisted is not None
        assert persisted["authorization_id"]
        assert app.state.advanced_policy.fingerprint


def test_authenticated_main_host_projects_latest_immutable_viewpoint_evaluation(tmp_path, monkeypatch):
    from app.advanced import api as advanced_api
    from app.advanced.governed_runner import GovernedExperimentRunner
    from app.config import settings
    from app.services import auth as auth_service
    from tests.test_analysis_host_integration import _write_phase1_fixture

    fixture_dir = tmp_path / "phase1-fixtures"
    data_dir = tmp_path / "governed-data"
    _write_phase1_fixture(fixture_dir)
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "1")
    monkeypatch.setenv("PHASE1_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setattr(settings, "auth_password", "host-test-password")
    monkeypatch.setattr(auth_service, "_configured_cache", None)
    auth_service._sessions.clear()

    from app.main import app

    with TestClient(app) as client:
        assert isinstance(app.state.experiment_service.backtest_runner, GovernedExperimentRunner)
        login = client.post("/api/auth/login", json={"password": "host-test-password"})
        assert login.status_code == 200

        app.state.resolve_advanced_subject_scope = lambda _request: advanced_api.AdvancedSubjectScope(
            frozenset({("instrument", "600000.SH")})
        )
        payload = _viewpoint_payload(instrument="600000.SH")
        payload["published_at"] = "2024-01-02T00:00:00+00:00"
        created = client.post("/api/advanced/viewpoints", json=payload)
        assert created.status_code == 200
        version_id = created.json()["viewpoint"]["id"]
        viewpoint_id = created.json()["viewpoint"]["viewpoint_id"]

        revised = client.post(
            f"/api/advanced/viewpoints/{viewpoint_id}/revisions",
            json={"direction": "bearish", "rating": "underweight"},
        )
        assert revised.status_code == 200
        assert revised.json()["viewpoint"]["revision_kind"] == "material_stance_change"
        corrected = client.post(
            f"/api/advanced/viewpoints/{viewpoint_id}/corrections",
            json={"correction_reason": "更正结论中的单位", "conclusion": "修正后的受控研究观点"},
        )
        assert corrected.status_code == 200
        assert corrected.json()["viewpoint"]["revision_kind"] == "correction"

        evaluation_response = client.post(
            f"/api/advanced/viewpoints/versions/{version_id}/evaluate", json={}
        )
        assert evaluation_response.status_code == 200
        assert evaluation_response.json()["viewpoint"]["evaluation"] == {
            "status": "unevaluable",
            "reason": "missing_price",
            "window_days": 60,
            "benchmark": "000300.SH",
            "relative_return": None,
        }

        listed = client.get(f"/api/advanced/viewpoints/{viewpoint_id}/versions")
        assert listed.status_code == 200
        versions = listed.json()["versions"]
        assert [version["revision_kind"] for version in versions] == [
            "correction", "material_stance_change", "initial",
        ]
        evaluation = next(version for version in versions if version["id"] == version_id)["evaluation"]
        assert evaluation == {
            "status": "unevaluable",
            "reason": "missing_price",
            "window_days": 60,
            "benchmark": "000300.SH",
            "relative_return": None,
        }
        assert client.get("/api/advanced/viewpoints?instrument=000001.SZ").status_code == 404


def test_governed_runner_persists_applied_limits_and_completed_feedback(tmp_path):
    from app.advanced.evolution import EvolutionService
    from app.advanced.experiments import ExperimentService
    from app.advanced.governed_runner import GovernedExperimentRunner
    from app.advanced.repository import AdvancedRepository

    repository = AdvancedRepository(tmp_path / "operational.db")
    repository.migrate()
    service = ExperimentService(
        repository=repository,
        backtest_runner=GovernedExperimentRunner(
            collaborator=_DeterministicGovernedCollaborator(),
            wall_clock_seconds=3,
            cpu_seconds=2,
            memory_limit_bytes=512 * 1024 * 1024,
            output_limit_bytes=16 * 1024,
        ),
    )
    specification = service.create_specification(
        research_asset_id="fixture-asset-v1",
        hypothesis="固定运行必须留存受治理证据",
        data_scope=_strategy_scope(),
        method="fixture",
        metrics=["sharpe"],
        success_criteria={"sharpe_gt": 1},
        failure_criteria={"drawdown_lt": -0.2},
    )

    run = service.run_specification(specification_id=specification["id"])

    assert run["status"] == "completed"
    assert service.get_specification(specification["id"])["data_scope"] == _strategy_scope()
    assert run["resources"] == {
        "wall_clock_seconds": 3,
        "cpu_seconds": 2,
        "memory_limit_bytes": 512 * 1024 * 1024,
        "output_limit_bytes": 16 * 1024,
    }
    feedback = service.record_feedback(
        run_id=run["id"], conclusion="supported", notes="受治理完成运行可形成研究反馈。"
    )
    assert feedback["run_id"] == run["id"]
    evolution = EvolutionService(repository=repository, reviewer_resolver=lambda _token: "server-researcher")
    candidate = evolution.create_candidate_from_completed_run(
        completed_run=service.completed_run_evidence(run_id=run["id"]),
        mutation_operation="parameter_adjustment",
        seed=23,
        resolved_configuration={"lookback": 30},
    )
    assert {evolution.evaluate_gate(candidate_id=candidate["id"], gate=gate)["status"] for gate in (
        "contract_sandbox_safety", "provenance", "in_sample_out_of_sample_evidence", "robustness", "cost_feasibility",
    )} == {"passed"}


def test_governed_runner_reaps_blocked_work_and_rejects_feedback(tmp_path):
    from app.advanced.experiments import ExperimentService
    from app.advanced.governed_runner import GovernedExperimentRunner
    from app.advanced.repository import AdvancedRepository

    repository = AdvancedRepository(tmp_path / "operational.db")
    repository.migrate()
    service = ExperimentService(
        repository=repository,
        backtest_runner=GovernedExperimentRunner(
            collaborator=_BlockingGovernedCollaborator(),
            wall_clock_seconds=1,
            cpu_seconds=2,
            memory_limit_bytes=512 * 1024 * 1024,
            output_limit_bytes=16 * 1024,
        ),
    )
    specification = service.create_specification(
        research_asset_id="fixture-asset",
        hypothesis="阻塞工作必须被父进程终止",
        data_scope=_strategy_scope(),
        method="fixture",
        metrics=["sharpe"],
        success_criteria={"sharpe_gt": 1},
        failure_criteria={"drawdown_lt": -0.2},
    )

    run = service.run_specification(specification_id=specification["id"])

    assert run["status"] == "timed_out"
    assert run["constraint_reason"] == "execution exceeded wall-clock budget"
    try:
        service.record_feedback(run_id=run["id"], conclusion="refuted", notes="超时不是研究结论。")
    except ValueError as error:
        assert "completed eligible" in str(error)
    else:  # pragma: no cover - the failure path is the contract under test.
        raise AssertionError("timed-out run accepted feedback")


def test_authorized_main_host_job_runs_fixed_workflow_and_persists_audit(tmp_path, monkeypatch):
    from app.advanced import api as advanced_api
    from app.config import settings
    from app.services import auth as auth_service
    from tests.test_analysis_host_integration import _write_phase1_fixture

    fixture_dir = tmp_path / "phase1-fixtures"
    data_dir = tmp_path / "governed-data"
    _write_phase1_fixture(fixture_dir)
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "1")
    monkeypatch.setenv("PHASE1_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setattr(settings, "auth_password", "host-test-password")
    monkeypatch.setattr(auth_service, "_configured_cache", None)
    auth_service._sessions.clear()

    from app.main import app

    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"password": "host-test-password"})
        assert login.status_code == 200
        app.state.resolve_advanced_subject_scope = lambda _request: advanced_api.AdvancedSubjectScope(
            frozenset({("instrument", "600519.SH")})
        )

        response = client.post(
            "/api/advanced/subjects/600519.SH/jobs",
            json={"task_type": "research_draft"},
        )

        assert response.status_code == 200
        job = response.json()["job"]
        assert job["status"] in {"awaiting_review", "recorded"}
        audit = client.get(f"/api/advanced/audits/{job['audit_reference']}")
        assert audit.status_code == 200
        assert audit.json()["audit"]["decision"] in {"authorized", "recorded"}


def test_main_host_publishes_committed_scoped_advanced_progress_only(tmp_path, monkeypatch):
    from app.advanced import api as advanced_api
    from app.config import settings
    from app.services import auth as auth_service
    from tests.test_analysis_host_integration import _write_phase1_fixture

    fixture_dir = tmp_path / "phase1-fixtures"
    data_dir = tmp_path / "governed-data"
    _write_phase1_fixture(fixture_dir)
    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "1")
    monkeypatch.setenv("PHASE1_FIXTURE_DIR", str(fixture_dir))
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setattr(settings, "auth_password", "host-test-password")
    monkeypatch.setattr(auth_service, "_configured_cache", None)
    auth_service._sessions.clear()

    from app.main import app

    with TestClient(app) as client:
        assert client.post("/api/auth/login", json={"password": "host-test-password"}).status_code == 200
        allowed_scope = advanced_api.AdvancedSubjectScope(frozenset({("instrument", "600519.SH")}))
        denied_scope = advanced_api.AdvancedSubjectScope(frozenset({("instrument", "000001.SZ")}))
        app.state.resolve_advanced_subject_scope = lambda _request: allowed_scope
        allowed = app.state.quote_service.subscribe(advanced_scope=allowed_scope)
        denied = app.state.quote_service.subscribe(advanced_scope=denied_scope)
        try:
            started = client.post(
                "/api/advanced/subjects/600519.SH/jobs", json={"task_type": "research_draft"}
            )
            assert started.status_code == 200
            job = started.json()["job"]
            events = allowed.pop()["advanced_progress"]
            assert events and events[-1]["stage"] == job["stage"]
            assert events[-1]["audit_reference"] == job["audit_reference"]
            assert denied.pop()["advanced_progress"] == []
            persisted = client.get(f"/api/advanced/jobs/{job['id']}")
            audit = client.get(f"/api/advanced/audits/{job['audit_reference']}")
            assert persisted.status_code == audit.status_code == 200
            assert persisted.json()["job"]["stage_recorded_at"] == events[-1]["occurred_at"]
            assert all(set(event) == {
                "job_id", "subject_kind", "subject_key", "stage", "label", "occurred_at", "audit_reference"
            } for event in events)
            for event in events:
                assert "advanced job" in event["label"].lower()

            app.state.resolve_advanced_subject_scope = lambda _request: denied_scope
            rejected = client.post(
                "/api/advanced/subjects/600519.SH/jobs", json={"task_type": "research_draft"}
            )
            assert rejected.status_code == 404
            assert allowed.pop()["advanced_progress"] == []
            assert denied.pop()["advanced_progress"] == []
        finally:
            app.state.quote_service.unsubscribe(allowed)
            app.state.quote_service.unsubscribe(denied)
