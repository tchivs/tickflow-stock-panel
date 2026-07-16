"""Fixed condition dispatch over validated, typed Thesis evidence."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Final

from app.theses.schemas import (
    ConditionCheckResult,
    ConditionEvaluation,
    EvidenceFact,
    EvidenceStatus,
    ThesisCondition,
)


_SCALAR_OPERATORS: Final[dict[str, Callable[[float, float], bool]]] = {
    "lt": lambda observed, threshold: observed < threshold,
    "lte": lambda observed, threshold: observed <= threshold,
    "gt": lambda observed, threshold: observed > threshold,
    "gte": lambda observed, threshold: observed >= threshold,
    "eq": lambda observed, threshold: observed == threshold,
}


class ConditionEvaluator:
    """Evaluate only the declared Thesis AST; never execute request text."""

    def evaluate(
        self,
        *,
        condition: ThesisCondition | Mapping[str, object],
        evidence: EvidenceFact | Mapping[str, object],
    ) -> ConditionEvaluation:
        return evaluate_condition(condition=condition, evidence=evidence)

    def __call__(
        self,
        *,
        condition: ThesisCondition | Mapping[str, object],
        evidence: EvidenceFact | Mapping[str, object],
    ) -> ConditionEvaluation:
        return self.evaluate(condition=condition, evidence=evidence)


def evaluate_condition(
    *,
    condition: ThesisCondition | Mapping[str, object],
    evidence: EvidenceFact | Mapping[str, object],
) -> ConditionEvaluation:
    """Return a deterministic safe result for one validated condition/evidence pair."""
    validated_condition = (
        condition if isinstance(condition, ThesisCondition) else ThesisCondition.model_validate(dict(condition))
    )
    validated_evidence = evidence if isinstance(evidence, EvidenceFact) else EvidenceFact.model_validate(dict(evidence))

    if validated_evidence.status is EvidenceStatus.MISSING:
        return ConditionEvaluation(
            result=ConditionCheckResult.INSUFFICIENT_EVIDENCE,
            observed_value=None,
            evidence_fingerprint=validated_evidence.evidence_fingerprint,
            safe_reason=validated_evidence.safe_reason or "missing_evidence",
        )
    if validated_evidence.status is EvidenceStatus.ERROR:
        return ConditionEvaluation(
            result=ConditionCheckResult.ERROR,
            observed_value=None,
            evidence_fingerprint=validated_evidence.evidence_fingerprint,
            safe_reason=validated_evidence.safe_reason or "evidence_error",
        )
    if validated_evidence.source_kind != validated_condition.source_kind:
        return _safe_error(validated_evidence, "evidence_source_mismatch")
    if validated_evidence.unit != validated_condition.unit:
        return _safe_error(validated_evidence, "evidence_unit_mismatch")

    observed = validated_evidence.observed_value
    assert observed is not None
    threshold = validated_condition.threshold
    try:
        if validated_condition.operator == "between":
            assert isinstance(threshold, tuple)
            matched = threshold[0] <= observed <= threshold[1]
        else:
            assert not isinstance(threshold, tuple)
            matched = _SCALAR_OPERATORS[validated_condition.operator](observed, threshold)
    except (ArithmeticError, KeyError, TypeError, ValueError):
        return _safe_error(validated_evidence, "condition_evaluation_error")

    return ConditionEvaluation(
        result=ConditionCheckResult.MATCHED if matched else ConditionCheckResult.NOT_MATCHED,
        observed_value=observed,
        evidence_fingerprint=validated_evidence.evidence_fingerprint,
        safe_reason=None,
    )


def _safe_error(evidence: EvidenceFact, reason: str) -> ConditionEvaluation:
    return ConditionEvaluation(
        result=ConditionCheckResult.ERROR,
        observed_value=None,
        evidence_fingerprint=evidence.evidence_fingerprint,
        safe_reason=reason,
    )
