"""Stage 1 contract for the FactorResearchAgent (AF-REQ-12).

A bounded :class:`StageOneRequest`, a versioned strict (``extra='forbid'``)
output schema, server-side ``parse_factor`` confirmation of every expression,
a transient exploratory proposal store, and a :class:`Stage1Service` that runs
over the Wave 1 provider seam (plan 48-01).

Invariants (research §3, §5.4):

* The provider's raw text is **never** trusted as authority. Every persisted
  expression equals its server-canonicalized form (``parse_factor`` →
  ``canonical_expression``); the raw text is retained only as provenance.
* Unknown or missing fields at **every** nesting level are permanent
  ``schema_violation`` failures — there is no silent truncation repair.
* A Stage 1 result is **transient**: stored only in
  ``research_alpha_proposals`` (exploratory) and the AnalysisRecord. It never
  reaches ``factor_registry`` / the catalog. Promotion is Phase 49 (AF-REQ-15).
* A provider exception never yields a proposal row, and no code path
  synthesizes a fallback draft (SC4, ``hypotheses.py:157-160`` pattern).
* Partial results are distinctly labeled (R2) so a degraded response cannot
  masquerade as a clean complete one.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from app.research import factor_dsl
from app.research.run_contract import (
    MAX_JSON_STRING_CHARS,
    validate_bounded_json,
)

STAGE_ONE_SCHEMA_VERSION = "factor-stage1-v1"
STAGE_ONE_PROMPT_TEMPLATE_VERSION = "factor-stage1-v1"

# Bounded output budget (reusing the MAX_JSON_* discipline, run_contract.py:25-28).
MAX_STAGE1_EXPRESSIONS = 3
MAX_STAGE1_EXPLANATION_CHARS = 2000
MAX_STAGE1_ASSUMPTIONS = 8

_UNCERTAINTY_VALUES: frozenset[str] = frozenset({"low", "medium", "high"})
_TOP_ALLOWED: frozenset[str] = frozenset({"schema_version", "hypotheses"})
_HYPOTHESIS_ALLOWED: frozenset[str] = frozenset({
    "expression", "explanation", "assumptions", "scope", "uncertainty", "evidence_refs",
})
_HYPOTHESIS_REQUIRED: frozenset[str] = frozenset({"expression", "explanation", "uncertainty"})


# ------------------------------------------------------------------
# Bounded request (thesis + permitted grammar/fields/functions)
# ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StageOneRequest:
    """Bounded Stage 1 input: a thesis plus the permitted DSL surface."""

    thesis: str
    permitted_grammar: Mapping[str, Any]
    permitted_fields: frozenset[str]
    permitted_functions: frozenset[str]
    budget_hints: Mapping[str, Any]
    snapshot_ref: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.thesis, str) or not self.thesis.strip():
            raise ValueError("thesis is required")
        if len(self.thesis) > MAX_JSON_STRING_CHARS:
            raise ValueError("thesis exceeds the maximum length")
        if not isinstance(self.permitted_fields, frozenset):
            raise ValueError("permitted_fields must be a frozenset")
        unknown_fields = sorted(set(self.permitted_fields) - factor_dsl.ALLOWED_FIELDS)
        if unknown_fields:
            raise ValueError(
                f"permitted_fields not in DSL allowed set: {', '.join(unknown_fields)}"
            )
        if not isinstance(self.permitted_functions, frozenset):
            raise ValueError("permitted_functions must be a frozenset")
        unknown_functions = sorted(
            set(self.permitted_functions) - set(factor_dsl._FUNCTION_ARITY)
        )
        if unknown_functions:
            raise ValueError(
                f"permitted_functions not in DSL function set: {', '.join(unknown_functions)}"
            )
        for label, value in (
            ("permitted_grammar", self.permitted_grammar),
            ("budget_hints", self.budget_hints),
            ("snapshot_ref", self.snapshot_ref),
        ):
            if not isinstance(value, Mapping):
                raise ValueError(f"{label} must be a mapping")
            validate_bounded_json(value, f"StageOneRequest.{label}")

    def as_request_scope(self) -> dict[str, Any]:
        """Bounded canonical request scope (provenance digest + prompt source)."""
        return {
            "thesis": self.thesis,
            "permitted_grammar": dict(self.permitted_grammar),
            "permitted_fields": sorted(self.permitted_fields),
            "permitted_functions": sorted(self.permitted_functions),
            "budget_hints": dict(self.budget_hints),
            "snapshot_ref": dict(self.snapshot_ref),
        }


# ------------------------------------------------------------------
# Strict versioned output schema (extra='forbid' at every nesting level)
# ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StageOneHypothesis:
    """One decoded (schema-valid) Stage 1 hypothesis, pre server-confirmation."""

    expression: str
    explanation: str
    assumptions: tuple[str, ...]
    scope: str
    uncertainty: Literal["low", "medium", "high"]
    evidence_refs: tuple[str, ...]


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not (text := value.strip()):
        raise ValueError(f"{field} is required")
    return text


def _text_array(value: object, field: str, *, max_items: int | None) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    if max_items is not None and len(value) > max_items:
        raise ValueError(f"{field} exceed the maximum of {max_items}")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field} must be an array of non-empty text")
    return tuple(item.strip() for item in value)


def _decode_hypothesis(item: object, index: int) -> StageOneHypothesis:
    if not isinstance(item, dict):
        raise ValueError(f"stage1 hypothesis[{index}] must be a JSON object")
    unknown = sorted(set(item) - _HYPOTHESIS_ALLOWED)
    missing = sorted(_HYPOTHESIS_REQUIRED - set(item))
    if unknown:
        raise ValueError(
            f"stage1 hypothesis[{index}] has unsupported field(s): {', '.join(unknown)}"
        )
    if missing:
        raise ValueError(
            f"stage1 hypothesis[{index}] is missing field(s): {', '.join(missing)}"
        )
    expression = _required_text(item["expression"], f"stage1 hypothesis[{index}].expression")
    if len(expression) > MAX_STAGE1_EXPLANATION_CHARS:
        raise ValueError(
            f"stage1 hypothesis[{index}].expression exceeds the maximum length"
        )
    explanation = _required_text(
        item["explanation"], f"stage1 hypothesis[{index}].explanation"
    )
    if len(explanation) > MAX_STAGE1_EXPLANATION_CHARS:
        raise ValueError(
            f"stage1 hypothesis[{index}].explanation exceeds the maximum length"
        )
    scope_value = item.get("scope", "")
    if not isinstance(scope_value, str):
        raise ValueError(f"stage1 hypothesis[{index}].scope must be text")
    if len(scope_value) > MAX_STAGE1_EXPLANATION_CHARS:
        raise ValueError(f"stage1 hypothesis[{index}].scope exceeds the maximum length")
    uncertainty = item["uncertainty"]
    if uncertainty not in _UNCERTAINTY_VALUES:
        raise ValueError(
            f"stage1 hypothesis[{index}].uncertainty must be one of low, medium, high"
        )
    assumptions = _text_array(
        item.get("assumptions", []),
        f"stage1 hypothesis[{index}].assumptions",
        max_items=MAX_STAGE1_ASSUMPTIONS,
    )
    evidence_refs = _text_array(
        item.get("evidence_refs", []),
        f"stage1 hypothesis[{index}].evidence_refs",
        max_items=None,
    )
    return StageOneHypothesis(
        expression=expression,
        explanation=explanation,
        assumptions=assumptions,
        scope=scope_value,
        uncertainty=uncertainty,  # type: ignore[arg-type]
        evidence_refs=evidence_refs,
    )


def decode_stage1_payload(raw: str) -> tuple[StageOneHypothesis, ...]:
    """Decode provider text into schema-validated hypotheses.

    Generalizes ``_decode_provider_draft`` (hypotheses.py:80-101) to the
    list-of-expressions Stage 1 schema. Unknown/missing fields at every nesting
    level raise a field-specific ``ValueError`` (the caller classifies it as a
    permanent ``schema_violation`` / ``malformed_json``). Pure: it never calls
    the provider and never mutates its input.
    """
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("provider returned malformed JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("stage1 payload must be a JSON object")
    unknown = sorted(set(payload) - _TOP_ALLOWED)
    missing = sorted(_TOP_ALLOWED - set(payload))
    if unknown:
        raise ValueError(f"stage1 payload has unsupported field(s): {', '.join(unknown)}")
    if missing:
        raise ValueError(f"stage1 payload is missing field(s): {', '.join(missing)}")
    if payload["schema_version"] != STAGE_ONE_SCHEMA_VERSION:
        raise ValueError("stage1 schema_version mismatch")
    hypotheses = payload["hypotheses"]
    if not isinstance(hypotheses, list):
        raise ValueError("stage1 hypotheses must be an array")
    if not hypotheses:
        raise ValueError("stage1 hypotheses must be non-empty")
    if len(hypotheses) > MAX_STAGE1_EXPRESSIONS:
        raise ValueError(
            f"stage1 hypotheses exceed the maximum of {MAX_STAGE1_EXPRESSIONS}"
        )
    return tuple(_decode_hypothesis(item, index) for index, item in enumerate(hypotheses))

# ------------------------------------------------------------------
# Server parse_factor confirmation + transient exploratory proposal store
# ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Stage1Confirmed:
    """Server-confirmed Stage 1 hypotheses with distinct partial labeling (R2)."""

    kept: tuple[StageOneHypothesis, ...]
    dropped: tuple[StageOneHypothesis, ...]
    validation_errors: tuple[Mapping[str, Any], ...]
    all_dropped: bool
    partial: bool


def confirm_stage1_hypotheses(
    hypotheses: Sequence[StageOneHypothesis],
    *,
    repo: Any,
    run_id: str,
    attempt_ordinal: int,
    provenance: Mapping[str, Any],
) -> Stage1Confirmed:
    """Server-confirm every expression and persist transient proposals.

    Mirrors ``FactorHypothesisService.draft`` (hypotheses.py:202-225): for each
    decoded hypothesis run ``parse_factor(expression)``; on success persist the
    server-canonical form (raw retained as provenance only); on ``FactorDslError``
    record a ``status='dropped'`` row + validation error and do NOT abort. The
    valid subset is salvaged but labeled distinctly: when some (not all)
    hypotheses fail, every row carries the distinct ``partial`` flag so a
    degraded response cannot masquerade as a clean complete one (R2). Only when
    ALL hypotheses fail does the caller escalate to permanent failure.
    """
    from app.research.factor_dsl import FactorDslError, parse_factor

    # First pass: parse every expression (no writes) so the partial flag is known
    # before any row is persisted (append-only rows cannot be amended later).
    results: list[tuple[int, StageOneHypothesis, str | None, Mapping[str, Any] | None]] = []
    for ordinal, hypothesis in enumerate(hypotheses, start=1):
        try:
            canonical = parse_factor(hypothesis.expression).canonical_expression
        except FactorDslError as error:
            results.append((
                ordinal,
                hypothesis,
                None,
                {
                    "hypothesis_ordinal": ordinal,
                    "code": "parse_failure",
                    "raw_expression": hypothesis.expression,
                    "detail": str(error),
                },
            ))
        else:
            results.append((ordinal, hypothesis, canonical, None))

    kept = tuple(h for _, h, canonical, _ in results if canonical is not None)
    dropped = tuple(h for _, h, canonical, _ in results if canonical is None)
    errors = tuple(
        error for _, _, _, error in results if error is not None  # type: ignore[misc]
    )
    all_dropped = len(kept) == 0
    partial = (not all_dropped) and len(dropped) > 0
    partial_flag = 1 if partial else 0

    provider = provenance["provider"]
    model = provenance["model"]
    model_version = provenance.get("model_version")

    # Second pass: persist every row with the correct partial flag.
    for ordinal, hypothesis, canonical, error in results:
        if canonical is not None:
            repo.record_stage1_proposal(
                run_id=run_id,
                attempt_ordinal=attempt_ordinal,
                hypothesis_ordinal=ordinal,
                raw_expression=hypothesis.expression,
                canonical_expression=canonical,
                explanation=hypothesis.explanation,
                assumptions=hypothesis.assumptions,
                scope=hypothesis.scope,
                uncertainty=hypothesis.uncertainty,
                evidence_refs=hypothesis.evidence_refs,
                schema_version=STAGE_ONE_SCHEMA_VERSION,
                template_version=STAGE_ONE_PROMPT_TEMPLATE_VERSION,
                provider=provider,
                model=model,
                model_version=model_version,
                status="proposed",
                partial=partial_flag,
            )
        else:
            repo.record_stage1_proposal(
                run_id=run_id,
                attempt_ordinal=attempt_ordinal,
                hypothesis_ordinal=ordinal,
                raw_expression=hypothesis.expression,
                # No canonical form exists for a parse failure; the offending raw
                # text is retained as provenance, status='dropped' discriminates.
                canonical_expression="",
                explanation=hypothesis.explanation,
                assumptions=hypothesis.assumptions,
                scope=hypothesis.scope,
                uncertainty=hypothesis.uncertainty,
                evidence_refs=hypothesis.evidence_refs,
                schema_version=STAGE_ONE_SCHEMA_VERSION,
                template_version=STAGE_ONE_PROMPT_TEMPLATE_VERSION,
                provider=provider,
                model=model,
                model_version=model_version,
                status="dropped",
                partial=partial_flag,
                validation_error=error,
            )

    return Stage1Confirmed(
        kept=kept,
        dropped=dropped,
        validation_errors=errors,
        all_dropped=all_dropped,
        partial=partial,
    )
