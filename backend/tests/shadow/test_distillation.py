"""Shadow explainable-distillation RED contracts."""

from __future__ import annotations

import json
import math
from copy import deepcopy

import pytest

ALLOWED_FEATURES = ("close_return_5d", "volume_ratio_20d", "intraday_range")


class CandidateRepository:
    def __init__(self) -> None:
        self.evidence = {
            "id": "evidence-set-1",
            "included_batch_ids": ["batch-1", "batch-2"],
            "fingerprint": "e" * 64,
        }
        self.candidates: list[dict[str, object]] = []

    def get_evidence_set(self, evidence_set_id: str):
        return deepcopy(self.evidence) if evidence_set_id == self.evidence["id"] else None

    def append_candidate(self, candidate: dict[str, object]):
        persisted = {"id": f"candidate-{len(self.candidates) + 1}", **deepcopy(candidate)}
        self.candidates.append(persisted)
        return deepcopy(persisted)

    def list_candidates(self):
        return deepcopy(self.candidates)


class GovernedFeatureSource:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.rows = rows or _feature_rows()

    def load(self, *, evidence_set: dict[str, object], feature_names: tuple[str, ...]):
        self.calls.append({"evidence_set": deepcopy(evidence_set), "feature_names": feature_names})
        return deepcopy(self.rows)


def _feature_rows() -> list[dict[str, object]]:
    return [
        {
            "date": "2025-01-02",
            "actual_trade": False,
            "close_return_5d": -0.05,
            "volume_ratio_20d": 0.7,
            "intraday_range": 0.02,
        },
        {
            "date": "2025-01-03",
            "actual_trade": False,
            "close_return_5d": -0.02,
            "volume_ratio_20d": 0.8,
            "intraday_range": 0.03,
        },
        {
            "date": "2025-01-06",
            "actual_trade": True,
            "close_return_5d": 0.04,
            "volume_ratio_20d": 1.7,
            "intraday_range": 0.05,
        },
        {
            "date": "2025-01-07",
            "actual_trade": False,
            "close_return_5d": 0.00,
            "volume_ratio_20d": 1.0,
            "intraday_range": 0.02,
        },
        {
            "date": "2025-01-08",
            "actual_trade": True,
            "close_return_5d": 0.06,
            "volume_ratio_20d": 1.9,
            "intraday_range": 0.06,
        },
        {
            "date": "2025-01-09",
            "actual_trade": False,
            "close_return_5d": -0.01,
            "volume_ratio_20d": 0.9,
            "intraday_range": 0.01,
        },
        {
            "date": "2025-01-10",
            "actual_trade": True,
            "close_return_5d": 0.03,
            "volume_ratio_20d": 1.5,
            "intraday_range": 0.04,
        },
        {
            "date": "2025-01-13",
            "actual_trade": False,
            "close_return_5d": 0.01,
            "volume_ratio_20d": 1.1,
            "intraday_range": 0.02,
        },
    ]


def _distiller(repository=None, source=None):
    from app.shadow.distillation import ShadowDistiller

    repository = repository or CandidateRepository()
    source = source or GovernedFeatureSource()
    return (
        repository,
        source,
        ShadowDistiller(repository=repository, governed_feature_source=source),
    )


def _distill(distiller, **overrides):
    payload = {
        "evidence_set_id": "evidence-set-1",
        "feature_names": ALLOWED_FEATURES,
        "seed": 17,
        "max_depth": 3,
        "min_leaf_support": 2,
        "exit_assumptions": {"kind": "fixed_holding_days", "days": 5},
        "holding_assumptions": {
            "price_adjustment": "unadjusted_execution_vs_forward_adjusted_research"
        },
    }
    payload.update(overrides)
    return distiller.distill(**payload)


def test_distillation_uses_only_server_governed_features_and_deterministic_negatives():
    first_repository, first_source, first_distiller = _distiller()
    second_repository, second_source, second_distiller = _distiller()

    first = _distill(first_distiller)
    second = _distill(second_distiller)

    assert (
        first_source.calls
        == second_source.calls
        == [
            {
                "evidence_set": first_repository.evidence,
                "feature_names": ALLOWED_FEATURES,
            }
        ]
    )
    assert first["rules"] == second["rules"]
    assert first["parameters"] == second["parameters"]
    assert first["class_balance"] == second["class_balance"]
    assert first["negative_sampling"]["seed"] == 17
    assert first["negative_sampling"]["source"] == "governed_non_trade_sessions"
    assert (
        first["negative_sampling"]["selected_dates"]
        == second["negative_sampling"]["selected_dates"]
    )
    assert len(first_repository.list_candidates()) == len(second_repository.list_candidates()) == 1


def test_distillation_enforces_fixed_seed_shallow_depth_leaf_support_and_class_balance():
    from app.shadow.distillation import ShadowDistillationError

    repository, _source, distiller = _distiller()
    candidate = _distill(distiller)

    assert candidate["seed"] == 17
    assert candidate["parameters"]["max_depth"] <= 3
    assert candidate["parameters"]["min_leaf_support"] >= 2
    assert candidate["parameters"]["class_weight"] == "balanced"
    assert candidate["class_balance"]["positive"] == 3
    assert candidate["class_balance"]["negative"] >= 3
    with pytest.raises(ShadowDistillationError, match="max_depth"):
        _distill(distiller, max_depth=4)
    with pytest.raises(ShadowDistillationError, match="leaf"):
        _distill(distiller, min_leaf_support=1)
    with pytest.raises(ShadowDistillationError, match="seed"):
        _distill(distiller, seed=None)
    assert len(repository.list_candidates()) == 1


def test_candidate_is_complete_versioned_attributable_and_explainable():
    repository, _source, distiller = _distiller()
    candidate = _distill(distiller)

    required = {
        "id",
        "distiller_version",
        "rule_schema_version",
        "rules",
        "features",
        "parameters",
        "exit_assumptions",
        "holding_assumptions",
        "source_batch_ids",
        "evidence_set_id",
        "evidence_set_fingerprint",
        "training_window",
        "seed",
        "class_balance",
        "metrics",
        "limitations",
        "created_at",
    }
    assert required.issubset(candidate)
    assert candidate["source_batch_ids"] == repository.evidence["included_batch_ids"]
    assert candidate["evidence_set_fingerprint"] == repository.evidence["fingerprint"]
    assert candidate["features"] == list(ALLOWED_FEATURES)
    assert candidate["training_window"] == {"start": "2025-01-02", "end": "2025-01-13"}
    assert {"support", "precision", "recall"}.issubset(candidate["metrics"])
    assert candidate["limitations"]
    assert any(
        "exit" in limitation.lower() or "holding" in limitation.lower()
        for limitation in candidate["limitations"]
    )
    assert candidate["rules"] and all(rule["conditions"] for rule in candidate["rules"])


def test_rule_validator_rejects_unsupported_fields_operators_and_nonfinite_thresholds():
    from app.shadow.distillation import ShadowDistillationError, ShadowRuleValidator

    validator = ShadowRuleValidator()
    valid = [
        {
            "conditions": [{"field": "close_return_5d", "operator": ">", "threshold": 0.02}],
            "prediction": "entry",
            "support": 3,
            "precision": 1.0,
            "recall": 1.0,
        }
    ]
    assert validator.validate(valid) == valid

    invalid_rules = [
        [
            {
                **valid[0],
                "conditions": [{"field": "browser_alpha", "operator": ">", "threshold": 0.0}],
            }
        ],
        [
            {
                **valid[0],
                "conditions": [{"field": "close_return_5d", "operator": "exec", "threshold": 0.0}],
            }
        ],
        [
            {
                **valid[0],
                "conditions": [
                    {"field": "close_return_5d", "operator": ">", "threshold": math.inf}
                ],
            }
        ],
    ]
    for rules in invalid_rules:
        with pytest.raises(ShadowDistillationError):
            validator.validate(rules)


def test_exported_canonical_rules_replay_equivalently_without_estimator():
    from app.shadow.distillation import ShadowRuleValidator

    _repository, source, distiller = _distiller()
    candidate = _distill(distiller)
    validator = ShadowRuleValidator()

    replay = validator.replay(candidate["rules"], source.rows)

    assert replay == candidate["training_replay"]
    assert candidate["canonical_rules_json"] == json.dumps(
        candidate["rules"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert candidate["rule_fingerprint"]
    assert len(candidate["rule_fingerprint"]) == 64


def test_persisted_candidate_contains_no_estimator_pickle_joblib_source_import_or_callable():
    repository, _source, distiller = _distiller()
    candidate = _distill(distiller)
    persisted = repository.list_candidates()[0]

    def inspect(value: object) -> None:
        assert not callable(value)
        if isinstance(value, dict):
            forbidden = {
                "estimator",
                "model_blob",
                "pickle",
                "joblib",
                "python_source",
                "imports",
                "callable",
            }
            assert forbidden.isdisjoint(key.lower() for key in value)
            for nested in value.values():
                inspect(nested)
        elif isinstance(value, list):
            for nested in value:
                inspect(nested)

    inspect(persisted)
    encoded = json.dumps(persisted, ensure_ascii=False).lower()
    for token in ("pickle", "joblib", "__import__", "python_source", "sklearn.tree._classes"):
        assert token not in encoded
    assert persisted == candidate


def test_invalid_or_insufficient_training_input_creates_no_candidate_fact():
    from app.shadow.distillation import ShadowDistillationError

    invalid_sets = [
        [{**row, "actual_trade": True} for row in _feature_rows()],
        [{**row, "close_return_5d": float("nan")} for row in _feature_rows()],
        _feature_rows()[:3],
    ]
    for rows in invalid_sets:
        repository = CandidateRepository()
        _repository, _source, distiller = _distiller(repository, GovernedFeatureSource(rows))
        with pytest.raises(ShadowDistillationError):
            _distill(distiller)
        assert repository.list_candidates() == []

    repository, _source, distiller = _distiller()
    with pytest.raises(ShadowDistillationError, match="feature"):
        _distill(distiller, feature_names=("close_return_5d", "browser_supplied_signal"))
    assert repository.list_candidates() == []


def _distill_request_payload(**overrides):
    payload = {
        "feature_names": list(ALLOWED_FEATURES),
        "seed": 17,
        "max_depth": 3,
        "min_leaf_support": 2,
        "exit_assumptions": {"kind": "fixed_holding_days", "days": 5},
        "holding_assumptions": {
            "price_adjustment": "unadjusted_execution_vs_forward_adjusted_research"
        },
    }
    payload.update(overrides)
    return payload


def test_bounded_assumption_schema_rejects_extra_recursive_collection_string_and_number():
    from pydantic import ValidationError

    from app.shadow.api import DistillRequest

    valid = _distill_request_payload()
    request = DistillRequest.model_validate(valid)
    assert request.model_dump() == valid
    assert DistillRequest.model_fields["exit_assumptions"].annotation.__name__ == "ExitAssumptions"

    invalid_pairs = (
        (
            {"kind": "fixed_holding_days", "days": 5, "browser_authority": True},
            valid["holding_assumptions"],
        ),
        (
            {"kind": {"level_1": {"level_2": {"level_3": 1}}}, "days": 5},
            valid["holding_assumptions"],
        ),
        ({f"key_{index}": index for index in range(17)}, valid["holding_assumptions"]),
        ({"kind": "fixed_holding_days", "days": list(range(33))}, valid["holding_assumptions"]),
        ({"kind": "fixed_holding_days", "days": 5}, {"price_adjustment": "界" * 43}),
        ({"kind": "fixed_holding_days", "days": math.inf}, valid["holding_assumptions"]),
    )
    for index, (exit_assumptions, holding_assumptions) in enumerate(invalid_pairs):
        try:
            DistillRequest.model_validate(
                _distill_request_payload(
                    exit_assumptions=exit_assumptions,
                    holding_assumptions=holding_assumptions,
                )
            )
        except ValidationError:
            continue
        pytest.fail(f"invalid assumption case {index} was accepted")


def test_assumption_byte_ceiling_preserves_canonical_identity_and_rejects_overruns():
    from app.shadow.schemas import ShadowAssumptionError, validate_assumption_pair

    first = validate_assumption_pair(
        exit_assumptions={"days": 5, "kind": "fixed_holding_days"},
        holding_assumptions={
            "price_adjustment": "unadjusted_execution_vs_forward_adjusted_research"
        },
    )
    replay = validate_assumption_pair(
        exit_assumptions={"kind": "fixed_holding_days", "days": 5},
        holding_assumptions={
            "price_adjustment": "unadjusted_execution_vs_forward_adjusted_research"
        },
    )
    assert first == replay
    assert first.exit_json == '{"days":5,"kind":"fixed_holding_days"}'

    with pytest.raises(ShadowAssumptionError, match="4096"):
        validate_assumption_pair(
            exit_assumptions={
                "kind": "fixed_holding_days",
                "days": 5,
                "padding": ["x" * 124] * 32,
            },
            holding_assumptions=replay.holding,
        )
    with pytest.raises(ShadowAssumptionError, match="8192"):
        validate_assumption_pair(
            exit_assumptions={
                "kind": "fixed_holding_days",
                "days": 5,
                "padding": ["x" * 123] * 32,
            },
            holding_assumptions={
                "price_adjustment": "unadjusted_execution_vs_forward_adjusted_research",
                "padding": ["x" * 122] * 32,
            },
        )


def test_direct_boundary_rejects_oversize_before_distiller_or_repository_work(tmp_path):
    from app.shadow.repository import ShadowRepository, ShadowRepositoryError
    from app.shadow.schemas import ShadowAssumptionError
    from app.shadow.service import ShadowService

    class RecordingDistiller:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def distill(self, **request):
            self.calls.append(deepcopy(request))
            return {"id": "candidate-from-distiller"}

    distiller = RecordingDistiller()
    service = ShadowService(
        repository=CandidateRepository(),
        evaluation_service=object(),  # type: ignore[arg-type]
        distiller=distiller,
    )
    valid = _distill_request_payload()
    assert service.distill_candidate(evidence_set_id="evidence-set-1", **valid)["id"]
    with pytest.raises(ShadowAssumptionError):
        service.distill_candidate(
            evidence_set_id="evidence-set-1",
            **_distill_request_payload(
                exit_assumptions={"kind": "fixed_holding_days", "days": 5, "padding": "x" * 4_097}
            ),
        )
    assert len(distiller.calls) == 1

    repository = ShadowRepository(tmp_path / "operational.db")
    evidence_manifest = {
        "included_batch_ids": ["batch-1"],
        "included_trade_ids": [],
        "exclusions": [],
    }
    evidence_json = json.dumps(
        evidence_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    evidence_fingerprint = __import__("hashlib").sha256(evidence_json.encode()).hexdigest()
    with repository._connection() as connection, connection:
        connection.execute(
            "INSERT INTO shadow_evidence_sets (id, principal, fingerprint, manifest_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                "evidence-set-1",
                "shadow-user-opaque",
                evidence_fingerprint,
                evidence_json,
                "2025-01-01T00:00:00+00:00",
            ),
        )

    rules = [
        {
            "conditions": [{"field": "close_return_5d", "operator": ">", "threshold": 0.02}],
            "prediction": "entry",
            "support": 3,
            "precision": 1.0,
            "recall": 1.0,
        }
    ]
    canonical_rules_json = json.dumps(
        rules, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    candidate = {
        "distiller_version": "shadow-shallow-tree-v1",
        "rule_schema_version": "shadow-entry-rules-v1",
        "rules": rules,
        "features": ["close_return_5d"],
        "parameters": {"max_depth": 1, "min_leaf_support": 2, "class_weight": "balanced"},
        "exit_assumptions": valid["exit_assumptions"],
        "holding_assumptions": valid["holding_assumptions"],
        "source_batch_ids": ["batch-1"],
        "evidence_set_id": "evidence-set-1",
        "evidence_set_fingerprint": evidence_fingerprint,
        "training_window": {"start": "2025-01-01", "end": "2025-01-31"},
        "seed": 17,
        "class_balance": {"positive": 2, "negative": 2},
        "metrics": {"support": 2, "precision": 1.0, "recall": 1.0},
        "limitations": ["research only"],
        "created_at": "2025-01-01T00:00:00+00:00",
        "negative_sampling": {
            "seed": 17,
            "source": "governed_non_trade_sessions",
            "selected_dates": [],
        },
        "canonical_rules_json": canonical_rules_json,
        "rule_fingerprint": __import__("hashlib").sha256(canonical_rules_json.encode()).hexdigest(),
        "training_replay": [True],
    }
    persisted = repository.append_candidate(candidate)
    assert persisted["exit_assumptions"] == valid["exit_assumptions"]
    assert persisted["holding_assumptions"] == valid["holding_assumptions"]

    invalid_candidate = deepcopy(candidate)
    invalid_candidate["seed"] = 18
    invalid_candidate["exit_assumptions"] = {
        "kind": "fixed_holding_days",
        "days": 5,
        "padding": "x" * 4_097,
    }
    with pytest.raises(ShadowRepositoryError, match="assumption"):
        repository.append_candidate(invalid_candidate)
    assert len(repository.list_candidates()) == 1

    with pytest.raises(ShadowAssumptionError):
        from app.shadow import projections

        projections.candidate({**persisted, "holding_assumptions": {"price_adjustment": "x" * 129}})


def _persisted_candidate_fixture(tmp_path):
    from app.shadow.repository import ShadowRepository

    repository = ShadowRepository(tmp_path / "candidate-replay.db")
    evidence_manifest = {
        "included_batch_ids": ["batch-1"],
        "included_trade_ids": [],
        "exclusions": [],
    }
    evidence_json = json.dumps(
        evidence_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    evidence_fingerprint = __import__("hashlib").sha256(evidence_json.encode()).hexdigest()
    with repository._connection() as connection, connection:
        connection.execute(
            "INSERT INTO shadow_evidence_sets (id, principal, fingerprint, manifest_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                "evidence-set-replay",
                "shadow-user-opaque",
                evidence_fingerprint,
                evidence_json,
                "2025-01-01T00:00:00+00:00",
            ),
        )

    rules = [
        {
            "conditions": [{"field": "close_return_5d", "operator": ">", "threshold": 0.02}],
            "prediction": "entry",
            "support": 3,
            "precision": 1.0,
            "recall": 1.0,
        }
    ]
    canonical_rules_json = json.dumps(
        rules, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    candidate = {
        "distiller_version": "shadow-shallow-tree-v1",
        "rule_schema_version": "shadow-entry-rules-v1",
        "rules": rules,
        "features": ["close_return_5d"],
        "parameters": {
            "max_depth": 1,
            "min_leaf_support": 2,
            "class_weight": "balanced",
        },
        "exit_assumptions": {"kind": "fixed_holding_days", "days": 5},
        "holding_assumptions": {
            "price_adjustment": "unadjusted_execution_vs_forward_adjusted_research"
        },
        "source_batch_ids": ["batch-1"],
        "evidence_set_id": "evidence-set-replay",
        "evidence_set_fingerprint": evidence_fingerprint,
        "training_window": {"start": "2025-01-01", "end": "2025-01-31"},
        "seed": 17,
        "class_balance": {"positive": 2, "negative": 2},
        "metrics": {"support": 2, "precision": 1.0, "recall": 1.0},
        "limitations": ["research only"],
        "created_at": "2025-01-01T00:00:00+00:00",
        "negative_sampling": {
            "seed": 17,
            "source": "governed_non_trade_sessions",
            "selected_dates": [],
        },
        "canonical_rules_json": canonical_rules_json,
        "rule_fingerprint": __import__("hashlib").sha256(canonical_rules_json.encode()).hexdigest(),
        "training_replay": [True],
    }
    return repository, candidate


def test_candidate_replay_digest_covers_all_identity_defining_content(tmp_path):
    from app.shadow.repository import ShadowRepositoryError

    repository, candidate = _persisted_candidate_fixture(tmp_path)
    first = repository.append_candidate(deepcopy(candidate))
    assert repository.append_candidate(deepcopy(candidate)) == first

    divergent_candidates = []
    changed = deepcopy(candidate)
    changed["features"] = ["volume_ratio_20d"]
    divergent_candidates.append(changed)
    changed = deepcopy(candidate)
    changed["parameters"]["max_depth"] = 2
    divergent_candidates.append(changed)
    changed = deepcopy(candidate)
    changed["exit_assumptions"]["days"] = 6
    divergent_candidates.append(changed)
    changed = deepcopy(candidate)
    changed["training_window"]["end"] = "2025-02-03"
    divergent_candidates.append(changed)
    changed = deepcopy(candidate)
    changed["negative_sampling"]["selected_dates"] = ["2025-01-03"]
    divergent_candidates.append(changed)
    changed = deepcopy(candidate)
    changed["rules"][0]["conditions"][0]["threshold"] = 0.03
    changed["canonical_rules_json"] = json.dumps(
        changed["rules"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    changed["rule_fingerprint"] = (
        __import__("hashlib").sha256(changed["canonical_rules_json"].encode()).hexdigest()
    )
    divergent_candidates.append(changed)
    changed = deepcopy(candidate)
    changed["rule_fingerprint"] = "f" * 64
    divergent_candidates.append(changed)
    changed = deepcopy(candidate)
    changed["metrics"]["precision"] = 0.5
    divergent_candidates.append(changed)

    for index, divergent in enumerate(divergent_candidates):
        try:
            repository.append_candidate(divergent)
        except ShadowRepositoryError as error:
            assert "conflict" in str(error), f"divergence {index}: {error}"
        else:
            pytest.fail(f"divergence {index} did not conflict")
    assert repository.list_candidates() == [first]
