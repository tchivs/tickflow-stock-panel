"""RED contracts for constrained strategy evolution and registered-only promotion."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
import pytest


GATES = (
    "contract_sandbox_safety",
    "provenance",
    "in_sample_out_of_sample_evidence",
    "robustness",
    "cost_feasibility",
)


class Spy:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def __call__(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))


def _service(tmp_path, *, principal_resolver=lambda token: "researcher-principal-opaque" if token == "session-token" else None):
    from app.advanced.evolution import EvolutionService
    from app.advanced.repository import AdvancedRepository

    repository = AdvancedRepository(tmp_path / "operational.db")
    repository.migrate()
    monitor = Spy()
    decision_plan = Spy()
    broker = Spy()
    execution = Spy()
    service = EvolutionService(
        repository=repository,
        reviewer_resolver=principal_resolver,
        monitoring_activator=monitor,
        decision_plan_service=decision_plan,
        broker_adapter=broker,
        execution_adapter=execution,
    )
    return repository, service, (monitor, decision_plan, broker, execution)


def _candidate(service, **overrides):
    payload = {
        "parent_research_asset": {"id": "strategy-parent-v4", "validated": True, "version": "4"},
        "mutation_operation": "adjust_signal_threshold",
        "seed": 17,
        "resolved_configuration": {"lookback": 20, "entry_zscore": 1.5, "cost_model": "cn-a-v1"},
    }
    payload.update(overrides)
    return service.create_candidate(**payload)


def _pass_all_gates(service, candidate_id: str) -> None:
    for gate in GATES:
        service.record_gate(candidate_id=candidate_id, gate=gate, status="passed", evidence={"reference": f"evidence-{gate}"})


def test_candidate_requires_validated_parent_allowed_mutation_seed_and_resolved_configuration(tmp_path):
    _repository, service, _spies = _service(tmp_path)

    candidate = _candidate(service)

    assert candidate["parent_research_asset_id"] == "strategy-parent-v4"
    assert candidate["parent_version"] == "4"
    assert candidate["mutation_operation"] == "adjust_signal_threshold"
    assert candidate["seed"] == 17
    assert candidate["resolved_configuration"] == {"lookback": 20, "entry_zscore": 1.5, "cost_model": "cn-a-v1"}
    with pytest.raises(ValueError, match="validated"):
        _candidate(service, parent_research_asset={"id": "unvalidated", "validated": False, "version": "1"})
    with pytest.raises(ValueError, match="mutation"):
        _candidate(service, mutation_operation="arbitrary_python")
    with pytest.raises(ValueError, match="seed|configuration"):
        _candidate(service, seed=None, resolved_configuration={})


@pytest.mark.parametrize("failed_gate", GATES)
def test_every_independent_gate_is_required_and_aggregate_score_never_authorizes_promotion(tmp_path, failed_gate):
    _repository, service, spies = _service(tmp_path)
    candidate = _candidate(service)
    for gate in GATES:
        service.record_gate(
            candidate_id=candidate["id"],
            gate=gate,
            status="failed" if gate == failed_gate else "passed",
            evidence={"reference": f"evidence-{gate}"},
        )

    with pytest.raises(ValueError, match="gates"):
        service.approve(candidate_id=candidate["id"], session_token="session-token", rationale="五项门禁中的一项尚未通过，不能登记为研究策略。", aggregate_score=99.9)

    assert all(not spy.calls for spy in spies)
    assert service.list_registered_strategies() == []


def test_approval_requires_server_resolved_researcher_and_nontrivial_rationale(tmp_path):
    _repository, service, spies = _service(tmp_path)
    candidate = _candidate(service)
    _pass_all_gates(service, candidate["id"])

    with pytest.raises(ValueError, match="researcher principal"):
        service.approve(candidate_id=candidate["id"], session_token=None, rationale="所有门禁已通过，批准保留研究策略版本。")
    with pytest.raises(ValueError, match="rationale"):
        service.approve(candidate_id=candidate["id"], session_token="session-token", rationale="ok")

    promoted = service.approve(
        candidate_id=candidate["id"],
        session_token="session-token",
        rationale="所有独立门禁均有可追溯证据，批准注册为可复用研究策略版本。",
    )

    assert promoted["approval"]["researcher_principal"] == "researcher-principal-opaque"
    assert promoted["approval"]["rationale"].startswith("所有独立门禁")
    assert promoted["registered_strategy"]["status"] == "registered_research_only"
    assert all(not spy.calls for spy in spies)


def test_promotion_is_replay_safe_and_competing_approval_returns_safe_conflict(tmp_path):
    repository, service, spies = _service(tmp_path)
    candidate = _candidate(service)
    _pass_all_gates(service, candidate["id"])

    first = service.approve(
        candidate_id=candidate["id"],
        session_token="session-token",
        rationale="证据、稳健性与成本假设均已独立复核，批准登记研究策略。",
    )
    with pytest.raises(ValueError, match="already|state changed|conflict"):
        service.approve(
            candidate_id=candidate["id"],
            session_token="session-token",
            rationale="重复请求不得创建第二个策略版本。",
        )

    assert len(service.list_registered_strategies()) == 1
    assert service.list_registered_strategies()[0]["id"] == first["registered_strategy"]["id"]
    assert repository.count_promotions(candidate_id=candidate["id"]) == 1
    assert all(not spy.calls for spy in spies)


def test_promotion_api_derives_principal_from_request_state_and_rejects_client_authority(tmp_path):
    from app.advanced import api as advanced_api

    _repository, service, _spies = _service(tmp_path)
    candidate = _candidate(service)
    _pass_all_gates(service, candidate["id"])
    app = FastAPI()
    app.include_router(advanced_api.router)
    app.state.evolution_service = service
    app.state.resolve_advanced_research_asset = lambda _request, asset_id: asset_id == "strategy-parent-v4"

    @app.middleware("http")
    async def authenticated_researcher(request: Request, call_next):
        request.state.reviewer_principal = "researcher-principal-from-server"
        return await call_next(request)

    client = TestClient(app)
    injected = client.post(
        f"/api/advanced/evolution/candidates/{candidate['id']}/promote",
        json={"rationale": "服务端身份才是权威，客户端不得注入批准主体。", "reviewer_principal": "browser-controlled"},
    )
    assert injected.status_code == 422

    approved = client.post(
        f"/api/advanced/evolution/candidates/{candidate['id']}/promote",
        json={"rationale": "服务端解析研究员身份，五项门禁通过后仅登记研究策略版本。"},
    )
    assert approved.status_code == 200
    assert approved.json()["approval"]["researcher_principal"] == "researcher-principal-from-server"
    assert approved.json()["registered_strategy"]["status"] == "registered_research_only"


def _completed_run_evidence() -> dict[str, object]:
    return {
        "run": {
            "id": "completed-run-1",
            "specification_id": "specification-1",
            "status": "completed",
            "governed_fingerprint": "f" * 64,
            "asset_version": "strategy-parent-v4",
            "resolved_parameters": {"lookback": 20},
            "metrics": {"sharpe": 1.2, "out_of_sample_return": 0.08},
            "artifacts": [{"reference": "governed-artifact", "checksum": "a" * 64}],
            "evolution_evidence": {
                "split": {
                    "in_sample": {"start": "2024-01-01", "end": "2024-06-30", "metrics": {"sharpe": 1.1}},
                    "out_of_sample": {"start": "2024-07-01", "end": "2024-12-31", "metrics": {"sharpe": 1.2}},
                },
                "robustness_trials": [{"reference": "trial-1", "status": "completed", "metrics": {"sharpe": 1.1}, "threshold_met": True}],
                "cost_feasibility": {
                    "fee_model": "cn-a-v1",
                    "commission": 0.0003,
                    "slippage": 0.0005,
                    "capacity_assumptions": {"max_notional": 1000000},
                    "net_metrics": {"sharpe": 1.05},
                    "capacity_result": "feasible",
                    "threshold_met": True,
                },
            },
            "sandbox_validation": {"id": "validation-1", "parent_asset_id": "strategy-parent-v4", "status": "validated"},
            "sandbox_run": {"id": "sandbox-run-1", "validation_id": "validation-1", "status": "completed"},
        },
        "specification": {
            "id": "specification-1",
            "version": 2,
            "research_asset_id": "strategy-parent-v4",
            "data_scope": {"start": "2024-01-01", "end": "2024-12-31"},
        },
    }


def test_completed_run_candidate_reloads_all_server_owned_evidence_and_gate_verdicts(tmp_path):
    _repository, service, _spies = _service(tmp_path)

    candidate = service.create_candidate_from_completed_run(
        completed_run=_completed_run_evidence(),
        mutation_operation="parameter_adjustment",
        seed=23,
        resolved_configuration={"lookback": 30},
    )

    assert candidate["parent_research_asset_id"] == "strategy-parent-v4"
    assert candidate["resolved_configuration"]["source_run"]["id"] == "completed-run-1"
    for gate in GATES:
        recorded = service.evaluate_gate(candidate_id=candidate["id"], gate=gate)
        assert recorded["status"] == "passed"
        assert set(recorded["evidence"]) == {"summary"}
    with pytest.raises(ValueError, match="already"):
        service.evaluate_gate(candidate_id=candidate["id"], gate="provenance")


class _ExperimentEvidenceService:
    def get_run(self, run_id: str) -> dict[str, object] | None:
        evidence = _completed_run_evidence()
        return evidence["run"] if run_id == "completed-run-1" else None

    def get_specification(self, specification_id: str) -> dict[str, object] | None:
        evidence = _completed_run_evidence()
        specification = evidence["specification"]
        if specification_id == "specification-1":
            return {**specification, "owner_principal": "server-researcher"}
        return None

    def completed_run_evidence(self, *, run_id: str) -> dict[str, object]:
        if run_id != "completed-run-1":
            raise ValueError("candidate requires a completed governed experiment run")
        return _completed_run_evidence()


def test_evolution_api_accepts_only_completed_run_input_and_server_derived_gate_actions(tmp_path):
    from app.advanced import api as advanced_api

    _repository, evolution, spies = _service(tmp_path)
    app = FastAPI()
    app.include_router(advanced_api.router)
    app.state.evolution_service = evolution
    app.state.experiment_service = _ExperimentEvidenceService()
    app.state.resolve_advanced_research_asset = lambda _request, asset_id: asset_id == "strategy-parent-v4"

    @app.middleware("http")
    async def authenticated(request: Request, call_next):
        request.state.reviewer_principal = "server-researcher"
        return await call_next(request)

    client = TestClient(app)
    payload = {
        "completed_run_id": "completed-run-1",
        "mutation_operation": "parameter_adjustment",
        "seed": 23,
        "resolved_configuration": {"lookback": 30},
    }
    assert client.post("/api/advanced/evolution/candidates", json={**payload, "evidence_reference": "browser"}).status_code == 422
    created = client.post("/api/advanced/evolution/candidates", json=payload)
    assert created.status_code == 200
    candidate_id = created.json()["candidate"]["id"]
    assert "source_run" not in created.json()["candidate"]["resolved_config"]
    for gate in GATES:
        assert client.post(f"/api/advanced/evolution/candidates/{candidate_id}/gates/{gate}", json={"status": "passed"}).status_code == 422
        response = client.post(f"/api/advanced/evolution/candidates/{candidate_id}/gates/{gate}", json={})
        assert response.status_code == 200
        assert response.json()["gate"]["status"] == "passed"
    promoted = client.post(
        f"/api/advanced/evolution/candidates/{candidate_id}/promote",
        json={"rationale": "五项服务端证据均已复核，明确批准注册研究策略版本。"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["registered_strategy"]["status"] == "registered_research_only"
    assert all(not spy.calls for spy in spies)
