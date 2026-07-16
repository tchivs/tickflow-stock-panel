"""Deterministic shallow-tree export to replayable allowlisted Shadow rule data."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
import random
from typing import Any, Final, Protocol


ALLOWED_FEATURES: Final[tuple[str, ...]] = (
    "close_return_5d",
    "volume_ratio_20d",
    "intraday_range",
)
_ALLOWED_OPERATORS: Final[frozenset[str]] = frozenset({"<=", ">"})
_RULE_FIELDS: Final[frozenset[str]] = frozenset(
    {"conditions", "prediction", "support", "precision", "recall"}
)
_CONDITION_FIELDS: Final[frozenset[str]] = frozenset(
    {"field", "operator", "threshold"}
)


class ShadowDistillationError(RuntimeError):
    """Distillation cannot produce a safe replayable candidate fact."""


class CandidateRepository(Protocol):
    def get_evidence_set(self, evidence_set_id: str) -> dict[str, object] | None: ...

    def append_candidate(self, candidate: dict[str, object]) -> dict[str, object]: ...


class GovernedFeatureSource(Protocol):
    def load(
        self,
        *,
        evidence_set: dict[str, object],
        feature_names: tuple[str, ...],
    ) -> list[dict[str, object]]: ...


class ShadowRuleValidator:
    """Validate and replay the entire retained candidate representation without ML."""

    def validate(self, rules: object) -> list[dict[str, object]]:
        if not isinstance(rules, list) or not rules or len(rules) > 8:
            raise ShadowDistillationError("candidate rules are invalid")
        for rule in rules:
            if not isinstance(rule, dict) or set(rule) != _RULE_FIELDS:
                raise ShadowDistillationError("candidate rule schema is invalid")
            conditions = rule["conditions"]
            if not isinstance(conditions, list) or not conditions or len(conditions) > 3:
                raise ShadowDistillationError("candidate rule conditions are invalid")
            for condition in conditions:
                if not isinstance(condition, dict) or set(condition) != _CONDITION_FIELDS:
                    raise ShadowDistillationError("candidate rule condition schema is invalid")
                if condition["field"] not in ALLOWED_FEATURES:
                    raise ShadowDistillationError("candidate rule field is unsupported")
                if condition["operator"] not in _ALLOWED_OPERATORS:
                    raise ShadowDistillationError("candidate rule operator is unsupported")
                threshold = condition["threshold"]
                if (
                    isinstance(threshold, bool)
                    or not isinstance(threshold, (int, float))
                    or not math.isfinite(float(threshold))
                ):
                    raise ShadowDistillationError("candidate rule threshold is non-finite")
            if rule["prediction"] != "entry":
                raise ShadowDistillationError("candidate rule prediction is unsupported")
            support = rule["support"]
            if isinstance(support, bool) or not isinstance(support, int) or support < 1:
                raise ShadowDistillationError("candidate rule support is invalid")
            for metric in ("precision", "recall"):
                value = rule[metric]
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or not 0 <= float(value) <= 1
                ):
                    raise ShadowDistillationError("candidate rule metric is invalid")
        return rules

    def replay(
        self,
        rules: object,
        rows: Sequence[Mapping[str, object]],
    ) -> list[bool]:
        validated = self.validate(rules)
        replay: list[bool] = []
        for row in rows:
            if not isinstance(row, Mapping):
                raise ShadowDistillationError("governed feature row is invalid")
            matched = any(self._matches(rule, row) for rule in validated)
            replay.append(matched)
        return replay

    @staticmethod
    def _matches(rule: Mapping[str, object], row: Mapping[str, object]) -> bool:
        conditions = rule["conditions"]
        assert isinstance(conditions, list)
        for condition in conditions:
            assert isinstance(condition, dict)
            field = str(condition["field"])
            value = row.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise ShadowDistillationError("governed feature value is non-finite")
            threshold = float(condition["threshold"])
            if condition["operator"] == "<=" and not float(value) <= threshold:
                return False
            if condition["operator"] == ">" and not float(value) > threshold:
                return False
        return True


class ShadowDistiller:
    """Train an optional bounded estimator, export data immediately, then discard it."""

    DISTILLER_VERSION = "shadow-shallow-tree-v1"
    RULE_SCHEMA_VERSION = "shadow-entry-rules-v1"

    def __init__(
        self,
        *,
        repository: CandidateRepository,
        governed_feature_source: GovernedFeatureSource,
        clock: Any | None = None,
    ) -> None:
        self.repository = repository
        self.governed_feature_source = governed_feature_source
        self._clock = clock or (lambda: datetime.now(UTC))
        self._validator = ShadowRuleValidator()

    def distill(
        self,
        *,
        evidence_set_id: str,
        feature_names: Sequence[str],
        seed: int,
        max_depth: int,
        min_leaf_support: int,
        exit_assumptions: Mapping[str, object],
        holding_assumptions: Mapping[str, object],
    ) -> dict[str, object]:
        features = self._validate_parameters(
            feature_names=feature_names,
            seed=seed,
            max_depth=max_depth,
            min_leaf_support=min_leaf_support,
            exit_assumptions=exit_assumptions,
            holding_assumptions=holding_assumptions,
        )
        evidence = self.repository.get_evidence_set(evidence_set_id)
        if evidence is None:
            raise ShadowDistillationError("evidence set is unavailable")
        fingerprint = evidence.get("fingerprint")
        source_batch_ids = evidence.get("included_batch_ids")
        if (
            not isinstance(fingerprint, str)
            or len(fingerprint) != 64
            or not isinstance(source_batch_ids, list)
            or not source_batch_ids
        ):
            raise ShadowDistillationError("evidence set attribution is invalid")
        try:
            raw_rows = self.governed_feature_source.load(
                evidence_set=evidence,
                feature_names=features,
            )
        except Exception as error:
            raise ShadowDistillationError("governed features are unavailable") from error
        rows = self._validated_rows(raw_rows, features, min_leaf_support)
        positives = [row for row in rows if row["actual_trade"]]
        negatives = [row for row in rows if not row["actual_trade"]]
        if not positives or len(negatives) < min_leaf_support:
            raise ShadowDistillationError("training classes are insufficient")
        selected_negative_count = min(len(negatives), max(len(positives), min_leaf_support))
        selected_negatives = random.Random(seed).sample(negatives, selected_negative_count)
        training_rows = sorted([*positives, *selected_negatives], key=lambda row: str(row["date"]))
        if len(training_rows) < min_leaf_support * 2:
            raise ShadowDistillationError("training rows are insufficient for leaf support")

        estimator, predictions, leaf_ids = self._fit(
            training_rows=training_rows,
            replay_rows=rows,
            features=features,
            seed=seed,
            max_depth=max_depth,
            min_leaf_support=min_leaf_support,
        )
        try:
            rules = self._export_rules(
                estimator=estimator,
                training_rows=training_rows,
                features=features,
                leaf_ids=leaf_ids,
            )
        finally:
            estimator = None
        validated_rules = self._validator.validate(rules)
        replay = self._validator.replay(validated_rules, rows)
        if replay != predictions:
            raise ShadowDistillationError("exported rule replay differs from training decision")
        canonical_rules_json = json.dumps(
            validated_rules,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        actual = [bool(row["actual_trade"]) for row in rows]
        predicted_positive = sum(replay)
        true_positive = sum(prediction and observed for prediction, observed in zip(replay, actual))
        positive_count = sum(actual)
        candidate: dict[str, object] = {
            "distiller_version": self.DISTILLER_VERSION,
            "rule_schema_version": self.RULE_SCHEMA_VERSION,
            "rules": validated_rules,
            "features": list(features),
            "parameters": {
                "max_depth": max_depth,
                "min_leaf_support": min_leaf_support,
                "class_weight": "balanced",
            },
            "exit_assumptions": dict(exit_assumptions),
            "holding_assumptions": dict(holding_assumptions),
            "source_batch_ids": list(source_batch_ids),
            "evidence_set_id": evidence_set_id,
            "evidence_set_fingerprint": fingerprint,
            "training_window": {
                "start": str(rows[0]["date"]),
                "end": str(rows[-1]["date"]),
            },
            "seed": seed,
            "class_balance": {
                "positive": len(positives),
                "negative": len(selected_negatives),
            },
            "metrics": {
                "support": predicted_positive,
                "precision": true_positive / predicted_positive if predicted_positive else 0.0,
                "recall": true_positive / positive_count if positive_count else 0.0,
            },
            "limitations": [
                "Entry behavior is inferred only from the governed visible feature allowlist.",
                "Exit behavior is not inferred; the declared exit assumptions remain authoritative.",
                "Holding behavior and price-adjustment semantics remain explicit assumptions.",
            ],
            "created_at": self._clock().astimezone(UTC).isoformat(),
            "negative_sampling": {
                "seed": seed,
                "source": "governed_non_trade_sessions",
                "selected_dates": [str(row["date"]) for row in selected_negatives],
            },
            "canonical_rules_json": canonical_rules_json,
            "rule_fingerprint": sha256(canonical_rules_json.encode("utf-8")).hexdigest(),
            "training_replay": replay,
        }
        self._assert_data_only(candidate)
        try:
            persisted = self.repository.append_candidate(candidate)
        except ShadowDistillationError:
            raise
        except Exception as error:
            raise ShadowDistillationError("candidate fact could not be persisted") from error
        if not isinstance(persisted, dict):
            raise ShadowDistillationError("persisted candidate fact is invalid")
        return persisted

    @staticmethod
    def _validate_parameters(
        *,
        feature_names: Sequence[str],
        seed: object,
        max_depth: object,
        min_leaf_support: object,
        exit_assumptions: Mapping[str, object],
        holding_assumptions: Mapping[str, object],
    ) -> tuple[str, ...]:
        features = tuple(feature_names)
        if (
            not features
            or len(features) != len(set(features))
            or any(feature not in ALLOWED_FEATURES for feature in features)
        ):
            raise ShadowDistillationError("feature allowlist is invalid")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ShadowDistillationError("seed must be a fixed integer")
        if isinstance(max_depth, bool) or not isinstance(max_depth, int) or not 1 <= max_depth <= 3:
            raise ShadowDistillationError("max_depth must be between 1 and 3")
        if (
            isinstance(min_leaf_support, bool)
            or not isinstance(min_leaf_support, int)
            or min_leaf_support < 2
        ):
            raise ShadowDistillationError("minimum leaf support must be at least 2")
        if not isinstance(exit_assumptions, Mapping) or not exit_assumptions:
            raise ShadowDistillationError("exit assumptions are required")
        if not isinstance(holding_assumptions, Mapping) or not holding_assumptions:
            raise ShadowDistillationError("holding assumptions are required")
        return features

    @staticmethod
    def _validated_rows(
        rows: object,
        features: tuple[str, ...],
        min_leaf_support: int,
    ) -> list[dict[str, object]]:
        if not isinstance(rows, list) or len(rows) < max(4, min_leaf_support * 2):
            raise ShadowDistillationError("training rows are insufficient")
        validated: list[dict[str, object]] = []
        dates: set[str] = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("date"), str):
                raise ShadowDistillationError("governed feature row is invalid")
            if not isinstance(row.get("actual_trade"), bool):
                raise ShadowDistillationError("governed training label is invalid")
            date = str(row["date"])
            if date in dates:
                raise ShadowDistillationError("governed feature dates must be unique")
            dates.add(date)
            for feature in features:
                value = row.get(feature)
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                ):
                    raise ShadowDistillationError("governed feature value is non-finite")
            validated.append(dict(row))
        validated.sort(key=lambda row: str(row["date"]))
        return validated

    @staticmethod
    def _fit(
        *,
        training_rows: list[dict[str, object]],
        replay_rows: list[dict[str, object]],
        features: tuple[str, ...],
        seed: int,
        max_depth: int,
        min_leaf_support: int,
    ) -> tuple[Any, list[bool], list[int]]:
        try:
            from sklearn.tree import DecisionTreeClassifier
        except (ImportError, ModuleNotFoundError) as error:
            raise ShadowDistillationError(
                "approved Shadow distillation dependency is unavailable"
            ) from error
        training_values = [[float(row[name]) for name in features] for row in training_rows]
        training_labels = [bool(row["actual_trade"]) for row in training_rows]
        replay_values = [[float(row[name]) for name in features] for row in replay_rows]
        try:
            estimator = DecisionTreeClassifier(
                random_state=seed,
                max_depth=max_depth,
                min_samples_leaf=min_leaf_support,
                class_weight="balanced",
            )
            estimator.fit(training_values, training_labels)
            predictions = [bool(value) for value in estimator.predict(replay_values).tolist()]
            leaf_ids = [int(value) for value in estimator.apply(training_values).tolist()]
        except Exception as error:
            raise ShadowDistillationError("bounded shallow-tree fitting failed safely") from error
        return estimator, predictions, leaf_ids

    @staticmethod
    def _export_rules(
        *,
        estimator: Any,
        training_rows: list[dict[str, object]],
        features: tuple[str, ...],
        leaf_ids: list[int],
    ) -> list[dict[str, object]]:
        tree = estimator.tree_
        positive_total = sum(bool(row["actual_trade"]) for row in training_rows)
        rules: list[dict[str, object]] = []

        def walk(node: int, conditions: list[dict[str, object]]) -> None:
            left = int(tree.children_left[node])
            right = int(tree.children_right[node])
            if left == right:
                prediction = bool(estimator.classes_[int(tree.value[node][0].argmax())])
                if not prediction or not conditions:
                    return
                indices = [index for index, leaf in enumerate(leaf_ids) if leaf == node]
                support = len(indices)
                positives = sum(bool(training_rows[index]["actual_trade"]) for index in indices)
                rules.append(
                    {
                        "conditions": conditions,
                        "prediction": "entry",
                        "support": support,
                        "precision": positives / support,
                        "recall": positives / positive_total,
                    }
                )
                return
            feature_index = int(tree.feature[node])
            if feature_index < 0 or feature_index >= len(features):
                raise ShadowDistillationError("learner exported an unsupported feature")
            threshold = float(tree.threshold[node])
            if not math.isfinite(threshold):
                raise ShadowDistillationError("learner exported a non-finite threshold")
            condition = {"field": features[feature_index], "threshold": threshold}
            walk(left, [*conditions, {**condition, "operator": "<="}])
            walk(right, [*conditions, {**condition, "operator": ">"}])

        walk(0, [])
        if not rules:
            raise ShadowDistillationError("learner produced no explainable entry rule")
        rules.sort(
            key=lambda rule: json.dumps(
                rule["conditions"], sort_keys=True, separators=(",", ":")
            )
        )
        return rules

    @classmethod
    def _assert_data_only(cls, value: object) -> None:
        if callable(value):
            raise ShadowDistillationError("candidate contains executable state")
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
            if forbidden & {str(key).lower() for key in value}:
                raise ShadowDistillationError("candidate contains forbidden state")
            for nested in value.values():
                cls._assert_data_only(nested)
        elif isinstance(value, (list, tuple)):
            for nested in value:
                cls._assert_data_only(nested)
        elif not isinstance(value, (str, int, float, bool, type(None))):
            raise ShadowDistillationError("candidate contains non-data state")
