"""RED contracts for immutable experiment specifications, runs, and feedback."""
from __future__ import annotations

import pickle
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


class FakeGovernedBacktest:
    """Returns compact governed metadata, never a raw market series."""

    def __init__(self, *, terminal_status: str = "completed", constraint_reason: str | None = None):
        self.terminal_status = terminal_status
        self.constraint_reason = constraint_reason
        self.calls: list[dict[str, object]] = []

    def run(self, *, specification: dict[str, object]) -> dict[str, object]:
        self.calls.append(specification)
        return {
            "status": self.terminal_status,
            "constraint_reason": self.constraint_reason,
            "governed_input_manifest": {
                "source": "governed_backtest_engine",
                "revision": "governed-revision-v1",
                "fingerprint": "governed-fingerprint-v1",
                "observed_start": "2025-01-02",
                "observed_end": "2025-12-31",
            },
            "asset_version": "factor-revision-7",
            "resolved_parameters": {"lookback": 20, "threshold": 1.5},
            "environment": {"python": "3.11", "runner": "bounded-backtest-v1"},
            "resources": {"timeout_seconds": 30, "memory_limit_mb": 512},
            "metrics": {"sharpe": 1.2, "out_of_sample_return": 0.08},
            "artifacts": [{"reference": "research_artifacts/run-1/metrics.json", "checksum": "a" * 64}],
            # This sentinel proves persistence stores only metadata, not a price series.
            "raw_market_series": [{"date": "2025-01-02", "close": 10.0}],
        }


def _service(tmp_path, runner=None, binding_resolver=None):
    from app.advanced.experiments import ExperimentService
    from app.advanced.repository import AdvancedRepository

    repository = AdvancedRepository(tmp_path / "operational.db")
    repository.migrate()
    resolver = binding_resolver or (
        lambda research_asset_id: {
            "strategy_id": "momentum_breakout",
            "research_asset_id": research_asset_id,
            "revision": research_asset_id,
        }
    )
    return repository, ExperimentService(
        repository=repository,
        backtest_runner=runner or FakeGovernedBacktest(),
        binding_resolver=resolver,
    )


def test_strategy_backtest_collaborator_is_spawn_serializable_without_duckdb_connection(tmp_path):
    from app.advanced.governed_runner import StrategyBacktestExperimentCollaborator

    collaborator = StrategyBacktestExperimentCollaborator(data_dir=tmp_path)

    assert pickle.loads(pickle.dumps(collaborator))._data_dir == str(tmp_path)



def test_strategy_backtest_collaborator_derives_split_evidence_from_distinct_governed_windows(tmp_path, monkeypatch):
    from app.advanced.governed_runner import StrategyBacktestExperimentCollaborator

    class RecordingBacktest:
        def __init__(self) -> None:
            self.configs: list[object] = []

        def run(self, config):
            self.configs.append(config)
            index = len(self.configs)
            return SimpleNamespace(
                run_id=f"governed-window-{index}",
                config={"params": config.params},
                stats={"sharpe": (99.0, 1.1, 2.2)[index - 1]},
                error=None,
                governed_input_manifest={"fingerprint": f"window-fingerprint-{index}"},
            )

    backtest = RecordingBacktest()
    collaborator = StrategyBacktestExperimentCollaborator(data_dir=tmp_path)
    monkeypatch.setattr(collaborator, "_service", lambda: backtest)
    result = collaborator.run(
        specification={
            "research_asset_id": "strategy-parent-v4",
            "bound_strategy_id": "momentum_breakout",
            "data_scope": {
                "strategy_id": "momentum_breakout",
                "start": "2024-01-01",
                "end": "2024-12-31",
                "symbols": ["600000.SH"],
                "asset_type": "stock",
                "parameters": {"lookback": 20},
            },
        }
    )

    assert [(config.start.isoformat(), config.end.isoformat()) for config in backtest.configs] == [
        ("2024-01-01", "2024-12-31"),
        ("2024-01-01", "2024-07-01"),
        ("2024-07-02", "2024-12-31"),
    ]
    split = result["evolution_evidence"]["split"]
    assert split["in_sample"] == {
        "start": "2024-01-01",
        "end": "2024-07-01",
        "metrics": {"sharpe": 1.1, "eligible_buy_count": 0, "completed_trade_count": 0},
        "evaluation": {
            "run_id": "governed-window-2",
            "governed_input_fingerprint": "window-fingerprint-2",
            "window": {"start": "2024-01-01", "end": "2024-07-01"},
            "artifact": {
                "reference": "strategy-backtest:governed-window-2:metrics",
                "checksum": "f570450ca70605eecdda86313575118904ccc6811f8948973dbf281e26c86b9f",
            },
        },
    }
    assert split["out_of_sample"]["metrics"] == {
        "sharpe": 2.2,
        "eligible_buy_count": 0,
        "completed_trade_count": 0,
    }
    assert split["out_of_sample"]["evaluation"]["run_id"] == "governed-window-3"


def test_strategy_backtest_collaborator_prepares_parent_frozen_panels_and_child_consumes_them(tmp_path, monkeypatch):
    from app.advanced.governed_runner import StrategyBacktestExperimentCollaborator

    class ParentBacktest:
        def __init__(self) -> None:
            self.frozen_scopes: list[dict[str, object]] = []

        def freeze_panel_artifact(self, config, store):
            self.frozen_scopes.append({"start": config.start.isoformat(), "end": config.end.isoformat()})
            return {"artifact_id": f"artifact-{len(self.frozen_scopes)}", "scope_checksum": "a" * 64}

    class ChildBacktest:
        def __init__(self) -> None:
            self.artifact_references: list[object] = []

        def run(self, config):
            self.artifact_references.append(config.frozen_panel_artifact)
            index = len(self.artifact_references)
            return SimpleNamespace(
                run_id=f"frozen-window-{index}",
                config={"params": config.params},
                stats={"sharpe": float(index)},
                error=None,
                governed_input_manifest={"fingerprint": f"frozen-fingerprint-{index}"},
            )

    parent, child = ParentBacktest(), ChildBacktest()
    collaborator = StrategyBacktestExperimentCollaborator(data_dir=tmp_path)
    monkeypatch.setattr(collaborator, "_service", lambda: parent)
    prepared = collaborator.prepare(specification={
        "research_asset_id": "strategy-parent-v4",
        "bound_strategy_id": "momentum_breakout",
        "data_scope": {
            "strategy_id": "momentum_breakout", "start": "2024-01-01", "end": "2024-12-31",
            "symbols": ["600000.SH"], "asset_type": "stock", "parameters": {"lookback": 20},
        },
    })
    monkeypatch.setattr(collaborator, "_service", lambda: child)

    collaborator.run(specification=prepared)

    assert parent.frozen_scopes == [
        {"start": "2024-01-01", "end": "2024-12-31"},
        {"start": "2024-01-01", "end": "2024-07-01"},
        {"start": "2024-07-02", "end": "2024-12-31"},
    ]
    assert child.artifact_references == [
        {"artifact_id": "artifact-1", "scope_checksum": "a" * 64},
        {"artifact_id": "artifact-2", "scope_checksum": "a" * 64},
        {"artifact_id": "artifact-3", "scope_checksum": "a" * 64},
    ]

def _specification(service, **overrides):
    payload = {
        "research_asset_id": "factor-value-v7",
        "hypothesis": "低估值与盈利质量组合在样本外保持正向超额收益",
        "data_scope": {
            "market": "CN-A",
            "strategy_id": "momentum_breakout",
            "start": "2024-01-01",
            "end": "2025-12-31",
            "symbols": ["600000.SH"],
            "asset_type": "stock",
            "parameters": {"lookback": 20, "enabled": True},
        },
        "method": "cross-sectional-long-short",
        "metrics": ["sharpe", "out_of_sample_return"],
        "success_criteria": {"out_of_sample_return_gt": 0.03},
        "failure_criteria": {"max_drawdown_lt": -0.2},
    }
    payload.update(overrides)
    return service.create_specification(**payload)


def test_experiment_specification_freezes_reproducible_research_contract_and_is_immutable(tmp_path):
    repository, service = _service(tmp_path)
    specification = _specification(service)

    assert specification["version"] == 1
    assert specification["hypothesis"].startswith("低估值")
    assert specification["data_scope"] == {
        "market": "CN-A",
        "strategy_id": "momentum_breakout",
        "start": "2024-01-01",
        "end": "2025-12-31",
        "symbols": ["600000.SH"],
        "asset_type": "stock",
        "parameters": {"lookback": 20, "enabled": True},
    }
    assert specification["method"] == "cross-sectional-long-short"
    assert specification["metrics"] == ["sharpe", "out_of_sample_return"]
    assert specification["success_criteria"] == {"out_of_sample_return_gt": 0.03}
    assert specification["failure_criteria"] == {"max_drawdown_lt": -0.2}

    with (
        sqlite3.connect(repository.database_path) as connection,
        pytest.raises(sqlite3.DatabaseError, match="immutable"),
    ):
        connection.execute(
            "UPDATE advanced_experiment_specs SET hypothesis = 'after-the-fact rewrite' WHERE id = ?",
            (specification["id"],),
        )



def _experiment_evidence_counts(repository):
    tables = (
        "advanced_experiment_specs",
        "advanced_experiment_runs",
        "advanced_sandbox_validations",
        "advanced_sandbox_runs",
        "advanced_experiment_feedback",
        "advanced_strategy_candidates",
        "advanced_promotion_gates",
        "advanced_promotions",
        "advanced_jobs",
    )
    with sqlite3.connect(repository.database_path) as connection:
        return {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}


def test_server_resolved_binding_is_immutable_and_denials_precede_all_experiment_evidence(tmp_path):
    runner = FakeGovernedBacktest()
    repository, service = _service(tmp_path, runner)

    specification = _specification(service)

    assert specification["bound_strategy_id"] == "momentum_breakout"
    assert specification["data_scope"]["strategy_id"] == "momentum_breakout"
    assert _experiment_evidence_counts(repository)["advanced_experiment_specs"] == 1

    baseline = _experiment_evidence_counts(repository)
    with pytest.raises(ValueError, match=r"binding|bound strategy"):
        _specification(service, data_scope=_strategy_scope(strategy_id="different_installed_strategy"))
    assert _experiment_evidence_counts(repository) == baseline
    assert runner.calls == []

    unbound_repository, unbound_service = _service(tmp_path / "unbound", FakeGovernedBacktest(), lambda _asset_id: None)
    with pytest.raises(ValueError, match=r"binding|bound strategy"):
        _specification(unbound_service)
    assert _experiment_evidence_counts(unbound_repository) == {
        table: 0 for table in _experiment_evidence_counts(unbound_repository)
    }


def test_legacy_specifications_remain_readable_but_lack_executable_binding(tmp_path):
    repository, service = _service(tmp_path)
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute(
            """INSERT INTO advanced_experiment_specs (
                id, research_asset_id, version, supersedes_specification_id, hypothesis,
                data_scope_json, method, metrics_json, success_criteria_json,
                failure_criteria_json, created_at, owner_principal
            ) VALUES (?, ?, 1, NULL, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "legacy-spec", "legacy-asset", "legacy", '{"asset_type":"stock","end":"2024-12-31","market":"CN-A","parameters":{},"start":"2024-01-01","strategy_id":"momentum_breakout","symbols":null}',
                "bounded", '["sharpe"]', '{"sharpe_gt":1}', '{"drawdown_lt":-0.2}', repository.now(), "legacy-owner",
            ),
        )

    legacy = service.get_specification("legacy-spec")

    assert legacy is not None
    assert legacy["bound_strategy_id"] is None
    with pytest.raises(ValueError, match=r"binding|bound strategy"):
        service.run_specification(specification_id="legacy-spec")


def test_runner_rejects_divergent_persisted_binding_before_loading_or_spawning(tmp_path, monkeypatch):
    from app.advanced import governed_runner

    collaborator = governed_runner.StrategyBacktestExperimentCollaborator(data_dir=tmp_path)
    service_calls: list[object] = []
    monkeypatch.setattr(collaborator, "_service", lambda: service_calls.append(object()))
    divergent = {
        "research_asset_id": "asset-owned",
        "bound_strategy_id": "server-owned-strategy",
        "data_scope": _strategy_scope(strategy_id="browser-selected-strategy"),
    }

    with pytest.raises(ValueError, match="bound strategy"):
        collaborator.run(specification=divergent)
    assert service_calls == []

    spawned: list[object] = []
    monkeypatch.setattr(governed_runner.multiprocessing, "get_context", lambda *_args: spawned.append(object()))
    terminal = governed_runner.GovernedExperimentRunner(collaborator=collaborator).run(specification=divergent)

    assert terminal["status"] == "validation_failed"
    assert spawned == []
    assert service_calls == []


def test_service_rechecks_persisted_binding_before_runner_or_terminal_evidence(tmp_path):
    runner = FakeGovernedBacktest()
    binding = {"strategy_id": "momentum_breakout"}
    repository, service = _service(
        tmp_path,
        runner,
        lambda asset_id: {**binding, "research_asset_id": asset_id, "revision": asset_id},
    )
    specification = _specification(service)
    baseline = _experiment_evidence_counts(repository)
    binding["strategy_id"] = "replacement-strategy"

    with pytest.raises(ValueError, match=r"binding|bound strategy"):
        service.run_specification(specification_id=specification["id"])

    assert runner.calls == []
    assert _experiment_evidence_counts(repository) == baseline

def test_completed_run_records_server_derived_manifest_without_raw_market_series(tmp_path):
    runner = FakeGovernedBacktest()
    repository, service = _service(tmp_path, runner)
    specification = _specification(service)

    run = service.run_specification(specification_id=specification["id"])

    assert len(runner.calls) == 1
    assert run["status"] == "completed"
    assert run["specification_id"] == specification["id"]
    assert run["governed_input_manifest"] == {
        "source": "governed_backtest_engine",
        "revision": "governed-revision-v1",
        "fingerprint": "governed-fingerprint-v1",
        "observed_start": "2025-01-02",
        "observed_end": "2025-12-31",
    }
    assert run["asset_version"] == "factor-revision-7"
    assert run["resolved_parameters"] == {"lookback": 20, "threshold": 1.5}
    assert run["environment"] == {"python": "3.11", "runner": "bounded-backtest-v1"}
    assert run["resources"] == {"timeout_seconds": 30, "memory_limit_mb": 512}
    assert run["artifacts"] == [{"reference": "research_artifacts/run-1/metrics.json", "checksum": "a" * 64}]
    with sqlite3.connect(repository.database_path) as connection:
        stored = connection.execute("SELECT run_json FROM advanced_experiment_runs WHERE id = ?", (run["id"],)).fetchone()[0]
    assert "raw_market_series" not in stored
    assert "\"close\":10.0" not in stored


@pytest.mark.parametrize(
    ("status", "constraint_reason"),
    [
        ("validation_failed", "contract field is invalid"),
        ("timed_out", "execution exceeded bounded timeout"),
        ("resource_limited", "memory ceiling reached"),
    ],
)
def test_constraint_failures_are_auditable_but_ineligible_for_feedback(tmp_path, status, constraint_reason):
    _repository, service = _service(tmp_path, FakeGovernedBacktest(terminal_status=status, constraint_reason=constraint_reason))
    specification = _specification(service)

    run = service.run_specification(specification_id=specification["id"])

    assert run["status"] == status
    assert run["constraint_reason"] == constraint_reason
    assert run["diagnostic"] == {"summary": constraint_reason, "raw_output": None}
    with pytest.raises(ValueError, match=r"completed|eligible"):
        service.record_feedback(
            run_id=run["id"],
            conclusion="refuted",
            notes="失败是运行约束, 不构成研究结论。",
        )
    assert service.list_feedback(run_id=run["id"]) == []


def test_completed_run_accepts_exactly_one_append_only_structured_feedback(tmp_path):
    repository, service = _service(tmp_path)
    run = service.run_specification(specification_id=_specification(service)["id"])

    feedback = service.record_feedback(
        run_id=run["id"],
        conclusion="needs_replication",
        notes="样本外收益达标但需要独立窗口复现。",
    )

    assert feedback["run_id"] == run["id"]
    assert feedback["conclusion"] == "needs_replication"
    assert feedback["metrics"] == {"sharpe": 1.2, "out_of_sample_return": 0.08}
    assert feedback["artifacts"] == [{"reference": "research_artifacts/run-1/metrics.json", "checksum": "a" * 64}]
    with pytest.raises(ValueError, match=r"already|one feedback"):
        service.record_feedback(run_id=run["id"], conclusion="supported", notes="不得覆盖已有结论")
    with (
        sqlite3.connect(repository.database_path) as connection,
        pytest.raises(sqlite3.DatabaseError, match="immutable"),
    ):
        connection.execute("DELETE FROM advanced_experiment_feedback WHERE id = ?", (feedback["id"],))


def test_retry_appends_a_new_run_and_configuration_change_appends_a_new_specification_version(tmp_path):
    _repository, service = _service(tmp_path, FakeGovernedBacktest(terminal_status="timed_out", constraint_reason="timeout"))
    original = _specification(service)
    failed_run = service.run_specification(specification_id=original["id"])

    retry = service.retry_run(run_id=failed_run["id"])
    changed = service.retry_run(
        run_id=failed_run["id"],
        specification_changes={
            "data_scope": {
                "market": "CN-A",
                "strategy_id": "momentum_breakout",
                "start": "2023-01-01",
                "end": "2025-12-31",
                "asset_type": "stock",
                "parameters": {},
            }
        },
    )

    assert retry["id"] != failed_run["id"]
    assert retry["specification_id"] == original["id"]
    assert changed["id"] != failed_run["id"]
    assert changed["specification_id"] != original["id"]
    changed_specification = service.get_specification(changed["specification_id"])
    assert changed_specification["version"] == 2
    assert changed_specification["supersedes_specification_id"] == original["id"]
    assert service.get_run(failed_run["id"])["status"] == "timed_out"


class _ExperimentApiService:
    def __init__(self) -> None:
        self.created: list[dict[str, object]] = []
        self.feedback: list[dict[str, str]] = []

    def create_specification(self, **payload: object) -> dict[str, object]:
        self.created.append(payload)
        return {"id": "spec-owned", "research_asset_id": "asset-owned", "version": 1}

    def get_specification(self, specification_id: str) -> dict[str, object] | None:
        if specification_id == "spec-owned":
            return {"id": specification_id, "research_asset_id": "asset-owned", "owner_principal": "server-researcher"}
        return {"id": specification_id, "research_asset_id": "asset-other", "owner_principal": "other-researcher"}

    def get_run(self, run_id: str) -> dict[str, object] | None:
        if run_id == "run-owned":
            return {"id": run_id, "specification_id": "spec-owned", "status": "completed"}
        return None

    def record_feedback(self, *, run_id: str, conclusion: str, notes: str) -> dict[str, str]:
        self.feedback.append({"run_id": run_id, "conclusion": conclusion, "notes": notes})
        return {"id": "feedback-owned", "run_id": run_id, "conclusion": conclusion}


def _strategy_scope(**overrides: object) -> dict[str, object]:
    scope: dict[str, object] = {
        "market": "CN-A",
        "strategy_id": "momentum_breakout",
        "start": "2024-01-01",
        "end": "2025-12-31",
        "symbols": ["600000.SH", "000001.SZ"],
        "asset_type": "stock",
        "parameters": {"lookback": 20, "stop_loss": 0.08, "enabled": True},
    }
    scope.update(overrides)
    return scope


def test_experiment_api_uses_server_owner_for_append_only_specifications_and_feedback():
    from app.advanced import api as advanced_api

    service = _ExperimentApiService()
    app = FastAPI()
    app.include_router(advanced_api.router)
    app.state.experiment_service = service
    app.state.resolve_advanced_research_asset = lambda _request, asset_id: asset_id == "asset-owned"
    app.state.resolve_advanced_research_asset_binding = lambda _request, asset_id: (
        {"research_asset_id": asset_id, "strategy_id": "momentum_breakout", "revision": asset_id}
        if asset_id == "asset-owned" else None
    )

    @app.middleware("http")
    async def authenticated(request: Request, call_next):
        request.state.reviewer_principal = "server-researcher"
        return await call_next(request)

    client = TestClient(app)
    payload = {
        "research_asset_id": "asset-owned",
        "hypothesis": "受控假设",
        "data_scope": _strategy_scope(),
        "method": "bounded-method",
        "metrics": ["sharpe"],
        "success_criteria": {"sharpe_gt": 1},
        "failure_criteria": {"drawdown_lt": -0.2},
    }

    assert client.post("/api/advanced/experiments/specifications", json={**payload, "owner_principal": "browser"}).status_code == 422
    created = client.post("/api/advanced/experiments/specifications", json=payload)
    assert created.status_code == 200
    assert service.created == [{**payload, "owner_principal": "server-researcher"}]
    assert client.get("/api/advanced/experiments/specifications/spec-other").status_code == 404
    feedback = client.post(
        "/api/advanced/experiments/runs/run-owned/feedback",
        json={"conclusion": "supported", "notes": "完整运行可追加研究结论。"},
    )
    assert feedback.status_code == 200
    assert service.feedback == [{"run_id": "run-owned", "conclusion": "supported", "notes": "完整运行可追加研究结论。"}]
    assert client.patch("/api/advanced/experiments/specifications/spec-owned", json={}).status_code == 405


def test_experiment_api_denies_mismatched_persisted_binding_before_service_creation():
    from app.advanced import api as advanced_api

    service = _ExperimentApiService()
    app = FastAPI()
    app.include_router(advanced_api.router)
    app.state.experiment_service = service
    app.state.resolve_advanced_research_asset = lambda _request, asset_id: asset_id == "asset-owned"
    app.state.resolve_advanced_research_asset_binding = lambda _request, asset_id: (
        {"research_asset_id": asset_id, "strategy_id": "momentum_breakout", "revision": asset_id}
        if asset_id == "asset-owned" else None
    )

    @app.middleware("http")
    async def authenticated(request: Request, call_next):
        request.state.reviewer_principal = "server-researcher"
        return await call_next(request)

    payload = {
        "research_asset_id": "asset-owned",
        "hypothesis": "受控假设",
        "data_scope": _strategy_scope(strategy_id="different_installed_strategy"),
        "method": "bounded-method",
        "metrics": ["sharpe"],
        "success_criteria": {"sharpe_gt": 1},
        "failure_criteria": {"drawdown_lt": -0.2},
    }
    client = TestClient(app)

    denied = client.post("/api/advanced/experiments/specifications", json=payload)

    assert denied.status_code == 404
    assert denied.json() == {"detail": "advanced experiment not found"}
    assert service.created == []

    matching = client.post(
        "/api/advanced/experiments/specifications",
        json={**payload, "data_scope": _strategy_scope()},
    )

    assert matching.status_code == 200
    assert service.created == [{**payload, "data_scope": _strategy_scope(), "owner_principal": "server-researcher"}]


def test_experiment_api_mismatch_creates_no_immutable_or_governed_side_effects(tmp_path):
    from app.advanced import api as advanced_api

    runner = FakeGovernedBacktest()
    repository, service = _service(tmp_path, runner)
    app = FastAPI()
    app.include_router(advanced_api.router)
    app.state.experiment_service = service
    app.state.resolve_advanced_research_asset = lambda _request, asset_id: asset_id == "asset-owned"
    app.state.resolve_advanced_research_asset_binding = lambda _request, asset_id: (
        {"research_asset_id": asset_id, "strategy_id": "momentum_breakout", "revision": asset_id}
        if asset_id == "asset-owned" else None
    )

    @app.middleware("http")
    async def authenticated(request: Request, call_next):
        request.state.reviewer_principal = "server-researcher"
        return await call_next(request)

    denied = TestClient(app).post(
        "/api/advanced/experiments/specifications",
        json={
            "research_asset_id": "asset-owned",
            "hypothesis": "受控假设",
            "data_scope": _strategy_scope(strategy_id="different_installed_strategy"),
            "method": "bounded-method",
            "metrics": ["sharpe"],
            "success_criteria": {"sharpe_gt": 1},
            "failure_criteria": {"drawdown_lt": -0.2},
        },
    )

    assert denied.status_code == 404
    assert _experiment_evidence_counts(repository) == {
        table: 0 for table in _experiment_evidence_counts(repository)
    }
    assert runner.calls == []
    assert repository.list_runnable_jobs() == []
    assert repository.list_sandbox_validations() == []
    assert repository.list_sandbox_runs() == []


@pytest.mark.parametrize(
    "scope",
    [
        _strategy_scope(strategy_id=""),
        _strategy_scope(start="not-a-date"),
        _strategy_scope(start="2025-12-31", end="2024-01-01"),
        _strategy_scope(symbols=["invalid symbol"]),
        _strategy_scope(asset_type="crypto"),
        _strategy_scope(parameters={"nested": {"not": "scalar"}}),
    ],
)
def test_experiment_api_rejects_invalid_frozen_strategy_scope_before_service_call(scope):
    from app.advanced import api as advanced_api

    service = _ExperimentApiService()
    app = FastAPI()
    app.include_router(advanced_api.router)
    app.state.experiment_service = service
    app.state.resolve_advanced_research_asset = lambda _request, asset_id: asset_id == "asset-owned"

    @app.middleware("http")
    async def authenticated(request: Request, call_next):
        request.state.reviewer_principal = "server-researcher"
        return await call_next(request)

    response = TestClient(app).post(
        "/api/advanced/experiments/specifications",
        json={
            "research_asset_id": "asset-owned",
            "hypothesis": "受控假设",
            "data_scope": scope,
            "method": "bounded-method",
            "metrics": ["sharpe"],
            "success_criteria": {"sharpe_gt": 1},
            "failure_criteria": {"drawdown_lt": -0.2},
        },
    )

    assert response.status_code == 422
    assert service.created == []
