"""Proposal-only natural-language factor hypothesis drafting.

This module deliberately has no registry, evaluator, catalog, artifact, request, or
filesystem collaborator.  A provider may propose text only; the application owns
all validation, review, persistence, and execution transitions elsewhere.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.research.factor_dsl import FactorDslError, parse_factor
from app.services import ai_provider

HYPOTHESIS_PROMPT_TEMPLATE_VERSION = "factor-hypothesis-v1"
GenerateText = Callable[..., Awaitable[str]]


class HypothesisUnavailableError(RuntimeError):
    """No configured provider is allowed to draft a hypothesis."""


class FactorHypothesisGateway(Protocol):
    """Narrow proposal boundary: hypothesis text/options in, draft JSON text out."""

    provider: str
    model: str
    model_version: str | None

    async def draft(self, hypothesis: str, options: Mapping[str, Any]) -> str: ...


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not (text := value.strip()):
        raise ValueError(f"{field} is required")
    return text


def _safe_options(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("hypothesis options must be an object")
    allowed = {"intent", "asset_type", "notes"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"unsupported hypothesis option(s): {', '.join(unknown)}")
    options: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"hypothesis option {key} must be non-empty text")
        options[key] = item.strip()
    return options


def _messages(hypothesis: str, options: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Return JSON only. The object must contain exactly expression, explanation, and optional assumptions. "
                "expression must use only the supplied restricted factor DSL: governed numeric fields, + - * /, "
                "and abs, sign, log1p, clip, rank, zscore, rolling_mean. Do not include markdown, code, "
                "imports, Python, or any other keys. assumptions, when supplied, must be an array of text."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"hypothesis": hypothesis, "options": dict(options)}, sort_keys=True, separators=(",", ":")
            ),
        },
    ]


def _decode_provider_draft(raw: str) -> tuple[str, str, tuple[str, ...]]:
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("provider returned malformed JSON draft") from error
    if not isinstance(payload, dict):
        raise ValueError("provider draft must be a JSON object")
    allowed = {"expression", "explanation", "assumptions"}
    unknown = sorted(set(payload) - allowed)
    missing = sorted({"expression", "explanation"} - set(payload))
    if unknown:
        raise ValueError(f"provider draft has unsupported field(s): {', '.join(unknown)}")
    if missing:
        raise ValueError(f"provider draft is missing field(s): {', '.join(missing)}")
    expression = _required_text(payload["expression"], "provider draft expression")
    explanation = _required_text(payload["explanation"], "provider draft explanation")
    assumptions_value = payload.get("assumptions", [])
    if not isinstance(assumptions_value, list) or any(
        not isinstance(item, str) or not item.strip() for item in assumptions_value
    ):
        raise ValueError("provider draft assumptions must be an array of non-empty text")
    return expression, explanation, tuple(item.strip() for item in assumptions_value)


@dataclass(frozen=True, slots=True)
class HypothesisDraft:
    """Validated but non-persistent draft requiring an explicit later review."""

    draft_id: str
    hypothesis: str
    expression: str
    normalized_expression: str
    explanation: str
    assumptions: tuple[str, ...]
    provenance: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "hypothesis": self.hypothesis,
            "expression": self.expression,
            "normalized_expression": self.normalized_expression,
            "explanation": self.explanation,
            "assumptions": list(self.assumptions),
            "provenance": dict(self.provenance),
        }


class ConfiguredFactorHypothesisGateway:
    """Host-configured provider adapter with no authority beyond text generation."""

    def __init__(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        model_version: str | None = None,
        generate_text: GenerateText | None = None,
    ) -> None:
        self.provider = provider or ai_provider.current_ai_provider()
        self.model = model or ai_provider.current_ai_model()
        self.model_version = model_version
        self._generate_text = generate_text or ai_provider.generate_ai_text

    @classmethod
    def from_current_configuration(cls) -> ConfiguredFactorHypothesisGateway | None:
        provider = ai_provider.current_ai_provider()
        if provider != ai_provider.OPENAI_COMPAT_PROVIDER or not ai_provider.ai_configured(provider):
            return None
        model = ai_provider.current_ai_model()
        if not model:
            return None
        return cls(provider=provider, model=model)

    async def draft(self, hypothesis: str, options: Mapping[str, Any]) -> str:
        if self.provider != ai_provider.OPENAI_COMPAT_PROVIDER or not self.model:
            raise HypothesisUnavailableError("configured hypothesis provider is unavailable")
        try:
            return await self._generate_text(_messages(hypothesis, options), temperature=0, max_tokens=600, timeout=30)
        except Exception as error:  # Provider failures are an availability boundary, never a fallback draft.
            raise HypothesisUnavailableError("configured hypothesis provider is unavailable") from error


class OfflineFakeHypothesisGateway:
    """Deterministic test-only text source; it never performs provider I/O."""

    def __init__(
        self,
        *,
        raw_response: str | None = None,
        error: Exception | None = None,
        provider: str = "offline_fake",
        model: str = "offline-fixture",
        model_version: str | None = "offline-v1",
    ) -> None:
        self.provider = provider
        self.model = model
        self.model_version = model_version
        self._raw_response = raw_response or json.dumps(
            {"expression": "close / ma20", "explanation": "Deterministic fixture hypothesis.", "assumptions": []}
        )
        self._error = error

    async def draft(self, hypothesis: str, options: Mapping[str, Any]) -> str:
        del hypothesis, options
        if self._error is not None:
            raise self._error
        return self._raw_response


class FactorHypothesisService:
    """Creates parser-confirmed transient drafts and verifies explicit reviews."""

    def __init__(self, gateway: FactorHypothesisGateway | None = None) -> None:
        self._gateway = gateway
        self._issued: dict[str, HypothesisDraft] = {}

    async def draft(self, *, hypothesis: str, options: Mapping[str, Any] | None = None) -> HypothesisDraft:
        text = _required_text(hypothesis, "hypothesis")
        safe_options = _safe_options(options)
        if self._gateway is None:
            raise HypothesisUnavailableError("configured hypothesis provider is unavailable")
        raw = await self._gateway.draft(text, safe_options)
        expression, explanation, assumptions = _decode_provider_draft(raw)
        try:
            parsed = parse_factor(expression)
        except FactorDslError as error:
            raise ValueError(f"provider draft has invalid factor DSL: {error}") from error
        generated_at = datetime.now(UTC).isoformat()
        draft = HypothesisDraft(
            draft_id=uuid.uuid4().hex,
            hypothesis=text,
            expression=expression,
            normalized_expression=parsed.canonical_expression,
            explanation=explanation,
            assumptions=assumptions,
            provenance={
                "provider": self._gateway.provider,
                "model": self._gateway.model,
                "model_version": self._gateway.model_version,
                "prompt_template_version": HYPOTHESIS_PROMPT_TEMPLATE_VERSION,
                "generated_at": generated_at,
            },
        )
        self._issued[draft.draft_id] = draft
        return draft

    def reviewed_draft(
        self,
        *,
        draft_id: str,
        expression: str,
        explanation: str,
        provenance: Mapping[str, Any],
    ) -> HypothesisDraft:
        """Revalidate an issued draft before a route may create an immutable revision."""
        issued = self._issued.get(_required_text(draft_id, "draft_id"))
        if issued is None:
            raise ValueError("hypothesis draft is unknown or expired")
        parsed = parse_factor(_required_text(expression, "reviewed expression"))
        if parsed.canonical_expression != issued.normalized_expression:
            raise ValueError("reviewed expression does not match the issued draft")
        if _required_text(explanation, "reviewed explanation") != issued.explanation:
            raise ValueError("reviewed explanation does not match the issued draft")
        if not isinstance(provenance, Mapping) or dict(provenance) != dict(issued.provenance):
            raise ValueError("reviewed provenance does not match the issued draft")
        return issued
