"""Shadow chronological evaluation and research-only retention RED contracts."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

IS_WINDOW = {"start": "2024-01-02", "end": "2024-06-28"}
OOS_WINDOW = {"start": "2024-07-01", "end": "2024-12-31"}
ADJUSTMENT_POLICY = "forward_adjusted_research_vs_unadjusted_execution"
COST_POLICY = {"commission_bps": 3.0, "slippage_bps": 5.0, "stamp_duty_bps": 5.0}
METRICS = {
    "precision": 0.72,
    "recall": 0.65,
    "coverage": 0.18,
    "candidate_trades": 24,
    "total_return": 0.11,
    "max_drawdown": -0.07,
    "costs": 0.012,
    "actual_trade_consistency": 0.68,
}
FORBIDDEN_ACTIONS = (
    "register_strategy", "activate_strategy", "create_monitor", "create_decision_plan",
    "mutate_position", "append_manual_ledger", "place_broker_order", "publish_market_action",
    "create_playbook",
)


class EvaluationRepository:
    def __init__(self) -> None:
        self.candidate = {
            "id": "candidate-1",
            "evidence_set_id": "evidence-set-1",
            "evidence_set_fingerprint": "e" * 64,
            "rules": [{"conditions": [{"field": "close_return_5d", "operator": ">", "threshold": 0.02}], "prediction": "entry"}],
            "limitations": ["Execution prices are unadjusted while governed research features are forward adjusted."],
        }
        self.evidence = {
            "id": "evidence-set-1",
            "fingerprint": "e" * 64,
            "included_batch_ids": ["batch-1"],
        }
        self.evaluations: list[dict[str, object]] = []
        self.retentions: list[dict[str, object]] = []
        self.forbidden_calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def get_candidate(self, candidate_id: str):
        return deepcopy(self.candidate) if candidate_id == self.candidate["id"] else None

    def get_evidence_set(self, evidence_set_id: str):
        return deepcopy(self.evidence) if evidence_set_id == self.evidence["id"] else None

    def append_evaluation_attempt(self, payload: dict[str, object]):
        record = {"id": f"evaluation-{len(self.evaluations) + 1}", "status": "running", **deepcopy(payload)}
        self.evaluations.append(record)
        return deepcopy(record)

    def complete_evaluation(self, evaluation_id: str, terminal: dict[str, object]):
        record = next(item for item in self.evaluations if item["id"] == evaluation_id)
        record.update(deepcopy(terminal))
        return deepcopy(record)

    def get_evaluation(self, evaluation_id: str):
        found = next((item for item in self.evaluations if item["id"] == evaluation_id), None)
        return deepcopy(found)

    def list_evaluations(self):
        return deepcopy(self.evaluations)

    def append_retention_event(self, payload: dict[str, object]):
        existing = next(
            (
                item for item in self.retentions
                if item["candidate_id"] == payload["candidate_id"]
                and item["in_sample_evaluation_id"] == payload["in_sample_evaluation_id"]
                and item["out_of_sample_evaluation_id"] == payload["out_of_sample_evaluation_id"]
            ),
            None,
        )
        if existing:
            return deepcopy(existing)
        event = {"id": f"retention-{len(self.retentions) + 1}", "status": "retained_research_only", **deepcopy(payload)}
        self.retentions.append(event)
        return deepcopy(event)

    def list_retention_events(self):
        return deepcopy(self.retentions)

    def __getattr__(self, name: str):
        if name in FORBIDDEN_ACTIONS:
            def forbidden(*args, **kwargs):
                self.forbidden_calls.append((name, args, kwargs))
                return {"unexpected": True}
            return forbidden
        raise AttributeError(name)


class FeatureFreezer:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def freeze(self, *, evidence_set, split_kind, window, adjustment_policy):
        call = {
            "evidence_set": deepcopy(evidence_set),
            "split_kind": split_kind,
            "window": deepcopy(window),
            "adjustment_policy": adjustment_policy,
        }
        self.calls.append(call)
        index = len(self.calls)
        return {
            "artifact": {
                "relative_path": f"evaluation-input-{index}/panel.parquet",
                "checksum_sha256": str(index) * 64,
            },
            "governed_fingerprint": chr(96 + index) * 64,
            "window": deepcopy(window),
            "split_kind": split_kind,
        }


class BoundedRunner:
    def __init__(self, outcomes: list[dict[str, object]] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.outcomes = list(outcomes or [])

    def run(self, *, candidate, frozen_input, cost_policy):
        self.calls.append({
            "candidate": deepcopy(candidate),
            "frozen_input": deepcopy(frozen_input),
            "cost_policy": deepcopy(cost_policy),
        })
        if self.outcomes:
            return deepcopy(self.outcomes.pop(0))
        return {"status": "passed", "metrics": deepcopy(METRICS), "worker_resources": {"bounded": True}}


def _services(repository=None, freezer=None, runner=None):
    from app.shadow.evaluation import ShadowEvaluationService
    from app.shadow.service import ShadowService

    repository = repository or EvaluationRepository()
    freezer = freezer or FeatureFreezer()
    runner = runner or BoundedRunner()
    evaluator = ShadowEvaluationService(repository=repository, feature_freezer=freezer, runner=runner)
    service = ShadowService(repository=repository, evaluation_service=evaluator)
    return repository, freezer, runner, evaluator, service


def _evaluate(evaluator, **overrides):
    payload = {
        "candidate_id": "candidate-1",
        "evidence_set_id": "evidence-set-1",
        "in_sample_window": IS_WINDOW,
        "out_of_sample_window": OOS_WINDOW,
        "split_policy": "chronological",
        "adjustment_policy": ADJUSTMENT_POLICY,
        "cost_policy": COST_POLICY,
    }
    payload.update(overrides)
    return evaluator.evaluate_candidate(**payload)


def _retain(service, evaluations, **overrides):
    payload = {
        "candidate_id": "candidate-1",
        "evidence_set_id": "evidence-set-1",
        "in_sample_evaluation_id": evaluations["in_sample"]["id"],
        "out_of_sample_evaluation_id": evaluations["out_of_sample"]["id"],
        "reviewer_principal": "shadow-reviewer-opaque",
        "rationale": "Both immutable chronological windows passed the declared research thresholds.",
    }
    payload.update(overrides)
    return service.retain_candidate(**payload)


def test_evaluation_freezes_separate_chronological_nonoverlapping_is_and_oos_runs():
    repository, freezer, runner, evaluator, _service = _services()
    result = _evaluate(evaluator)

    assert [call["split_kind"] for call in freezer.calls] == ["in_sample", "out_of_sample"]
    assert [call["window"] for call in freezer.calls] == [IS_WINDOW, OOS_WINDOW]
    assert IS_WINDOW["end"] < OOS_WINDOW["start"]
    assert result["in_sample"]["id"] != result["out_of_sample"]["id"]
    assert result["in_sample"]["governed_fingerprint"] != result["out_of_sample"]["governed_fingerprint"]
    assert result["in_sample"]["artifact"] != result["out_of_sample"]["artifact"]
    assert len(runner.calls) == len(repository.list_evaluations()) == 2


def test_each_split_records_independent_fingerprint_artifact_status_and_complete_metrics():
    _repository, _freezer, _runner, evaluator, _service = _services()
    result = _evaluate(evaluator)

    required_metrics = {
        "precision", "recall", "coverage", "candidate_trades", "total_return",
        "max_drawdown", "costs", "actual_trade_consistency",
    }
    for split_kind in ("in_sample", "out_of_sample"):
        evaluation = result[split_kind]
        assert evaluation["split_kind"] == split_kind
        assert evaluation["status"] == "passed"
        assert required_metrics == set(evaluation["metrics"])
        assert evaluation["governed_fingerprint"]
        assert evaluation["artifact"]["checksum_sha256"]
        assert evaluation["adjustment_policy"] == ADJUSTMENT_POLICY
        assert evaluation["cost_policy"] == COST_POLICY
        assert evaluation["candidate_id"] == "candidate-1"
        assert evaluation["evidence_set_fingerprint"] == "e" * 64


def test_full_sample_random_or_overlapping_windows_cannot_substitute_for_two_splits():
    from app.shadow.evaluation import ShadowEvaluationError

    repository, freezer, runner, evaluator, _service = _services()
    invalid = [
        {"split_policy": "random"},
        {"in_sample_window": {"start": "2024-01-02", "end": "2024-12-31"}, "out_of_sample_window": OOS_WINDOW},
        {"in_sample_window": IS_WINDOW, "out_of_sample_window": IS_WINDOW},
        {"out_of_sample_window": None, "full_sample_metrics": METRICS},
    ]
    for overrides in invalid:
        with pytest.raises((ShadowEvaluationError, TypeError)):
            _evaluate(evaluator, **overrides)
    assert repository.list_evaluations() == []
    assert freezer.calls == []
    assert runner.calls == []


def test_failure_timeout_and_resource_retry_append_a_new_run_without_partial_evidence():
    repository = EvaluationRepository()
    runner = BoundedRunner([
        {"status": "timeout", "reason": "bounded worker timed out"},
        {"status": "passed", "metrics": METRICS, "worker_resources": {"bounded": True}},
        {"status": "passed", "metrics": METRICS, "worker_resources": {"bounded": True}},
    ])
    _repository, _freezer, _runner, evaluator, _service = _services(repository=repository, runner=runner)

    first = _evaluate(evaluator)
    assert first["in_sample"]["status"] == "timeout"
    assert "metrics" not in first["in_sample"]
    retry = evaluator.retry_evaluation(evaluation_id=first["in_sample"]["id"])

    assert retry["id"] != first["in_sample"]["id"]
    assert retry["retry_of_evaluation_id"] == first["in_sample"]["id"]
    assert retry["status"] == "passed"
    assert repository.get_evaluation(first["in_sample"]["id"])["status"] == "timeout"
    assert len(repository.list_evaluations()) == 3


def test_retention_requires_canonical_passing_terminal_is_and_oos_for_same_candidate():
    repository, _freezer, _runner, evaluator, service = _services()
    evaluations = _evaluate(evaluator)
    retained = _retain(service, evaluations)

    assert retained["status"] == "retained_research_only"
    assert retained["candidate_id"] == "candidate-1"
    assert retained["evidence_set_id"] == "evidence-set-1"
    assert retained["evidence_set_fingerprint"] == "e" * 64
    assert retained["in_sample_evaluation_id"] == evaluations["in_sample"]["id"]
    assert retained["out_of_sample_evaluation_id"] == evaluations["out_of_sample"]["id"]
    assert retained["reviewer_principal"] == "shadow-reviewer-opaque"
    assert repository.list_retention_events() == [retained]


def test_duplicate_retention_is_replay_safe_and_atomic():
    repository, _freezer, _runner, evaluator, service = _services()
    evaluations = _evaluate(evaluator)

    first = _retain(service, evaluations)
    replay = _retain(service, evaluations)

    assert replay == first
    assert len(repository.list_retention_events()) == 1
    assert set(repository.list_retention_events()[0]).issuperset({
        "candidate_id", "evidence_set_id", "evidence_set_fingerprint",
        "in_sample_evaluation_id", "out_of_sample_evaluation_id", "reviewer_principal", "rationale",
    })


def test_failed_timeout_resource_or_oos_fail_evaluations_are_ineligible():
    from app.shadow.service import ShadowRetentionError

    statuses = ("failed", "timeout", "resource_exhausted")
    for status in statuses:
        repository = EvaluationRepository()
        runner = BoundedRunner([
            {"status": "passed", "metrics": METRICS},
            {"status": status, "reason": "safe terminal failure"},
        ])
        _repository, _freezer, _runner, evaluator, service = _services(repository=repository, runner=runner)
        evaluations = _evaluate(evaluator)
        with pytest.raises(ShadowRetentionError):
            _retain(service, evaluations)
        assert repository.list_retention_events() == []

    repository, _freezer, _runner, evaluator, service = _services()
    evaluations = _evaluate(evaluator)
    repository.evaluations[1]["metrics"]["precision"] = 0.0
    repository.evaluations[1]["status"] = "failed_gate"
    with pytest.raises(ShadowRetentionError):
        _retain(service, evaluations)
    assert repository.list_retention_events() == []


def test_retention_invokes_zero_strategy_monitor_plan_position_ledger_broker_or_market_actions():
    repository, _freezer, _runner, evaluator, service = _services()
    evaluations = _evaluate(evaluator)

    retained = _retain(service, evaluations)

    assert retained["status"] == "retained_research_only"
    assert repository.forbidden_calls == []
    assert all(not hasattr(service, name) for name in FORBIDDEN_ACTIONS)
    serialized = json.dumps(retained, ensure_ascii=False).lower()
    for token in ("activation", "monitor_id", "decision_plan_id", "position_id", "broker_order_id", "market_action"):
        assert token not in serialized


def test_evaluation_and_retention_projections_hide_paths_secrets_tracebacks_and_client_verdicts(tmp_path):
    repository, _freezer, _runner, evaluator, service = _services()
    evaluations = _evaluate(evaluator)
    retained = _retain(service, evaluations)

    serialized = json.dumps({"evaluations": evaluations, "retained": retained}, ensure_ascii=False).lower()
    assert str(tmp_path.resolve()).lower() not in serialized
    for token in ("account_secret", "raw_bytes", "traceback", "exception", "browser_verdict", "client_eligible"):
        assert token not in serialized
    with pytest.raises(TypeError):
        service.retain_candidate(
            candidate_id="candidate-1",
            evidence_set_id="evidence-set-1",
            in_sample_evaluation_id=evaluations["in_sample"]["id"],
            out_of_sample_evaluation_id=evaluations["out_of_sample"]["id"],
            reviewer_principal="browser-controlled",
            rationale="Browser eligibility and principal must never be authoritative.",
            client_eligible=True,
            browser_verdict="pass",
        )
    assert len(repository.list_retention_events()) == 1
