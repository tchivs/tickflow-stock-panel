"""Configured, proposal-only AI review for persisted deterministic playbooks."""
from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from app.decision.adjustments import ALLOWED_ADJUSTMENT_FIELDS
from app.services import ai_provider


Message = dict[str, str]
GenerateText = Callable[..., Awaitable[str]]


class AIReviewGateway(Protocol):
    """Proposal-only review collaborator; implementations never mutate a decision run."""

    provider: str
    model: str

    async def propose(self, baseline: dict[str, Any]) -> dict[str, Any]: ...


def _numeric_string(value: Any) -> str:
    try:
        numeric = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("review adjustment value must be numeric") from error
    if not numeric.is_finite():
        raise ValueError("review adjustment value must be finite")
    return str(value)


def _typed_proposal(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"adjustments"}:
        raise ValueError("review response must contain only adjustments")
    adjustments = value["adjustments"]
    if not isinstance(adjustments, list):
        raise ValueError("review adjustments must be a list")

    typed: list[dict[str, str]] = []
    seen: set[str] = set()
    for adjustment in adjustments:
        if not isinstance(adjustment, dict) or set(adjustment) != {"field", "value", "rationale"}:
            raise ValueError("review adjustment has an invalid shape")
        field = adjustment["field"]
        rationale = adjustment["rationale"]
        if not isinstance(field, str) or field not in ALLOWED_ADJUSTMENT_FIELDS or field in seen:
            raise ValueError("review adjustment field is not allowed")
        if not isinstance(rationale, str):
            raise ValueError("review adjustment rationale must be text")
        seen.add(field)
        typed.append({"field": field, "value": _numeric_string(adjustment["value"]), "rationale": rationale})
    return {"adjustments": typed}


def _review_messages(baseline: dict[str, Any]) -> list[Message]:
    fields = {
        field: str(baseline[field])
        for field in sorted(ALLOWED_ADJUSTMENT_FIELDS)
        if field in baseline
    }
    return [
        {
            "role": "system",
            "content": (
                "Return JSON only. The JSON object must be exactly "
                '{"adjustments":[{"field":"entry_low","value":"numeric","rationale":"text"}]}. '
                "Allowed fields are entry_low, entry_high, stop, target1, target2, and position_pct. "
                "Do not return action, score, risk_reward, or any other field."
            ),
        },
        {"role": "user", "content": json.dumps({"baseline": fields}, sort_keys=True, separators=(",", ":"))},
    ]


class ConfiguredAIReviewGateway:
    """OpenAI-compatible proposal gateway backed by the host's configured provider."""

    def __init__(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        generate_text: GenerateText | None = None,
    ) -> None:
        self.provider = provider or ai_provider.current_ai_provider()
        self.model = model or ai_provider.current_ai_model()
        self._generate_text = generate_text or ai_provider.generate_ai_text

    @classmethod
    def from_current_configuration(cls) -> ConfiguredAIReviewGateway | None:
        provider = ai_provider.current_ai_provider()
        if provider != ai_provider.OPENAI_COMPAT_PROVIDER or not ai_provider.ai_configured(provider):
            return None
        model = ai_provider.current_ai_model()
        if not model:
            return None
        return cls(provider=provider, model=model)

    async def propose(self, baseline: dict[str, Any]) -> dict[str, Any]:
        if self.provider != ai_provider.OPENAI_COMPAT_PROVIDER or not self.model:
            raise RuntimeError("configured review provider is unavailable")
        raw = await self._generate_text(_review_messages(baseline), temperature=0, max_tokens=600, timeout=120)
        try:
            return _typed_proposal(json.loads(raw))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("configured review returned malformed output") from error


class OfflineFakeReviewGateway:
    """Deterministic test collaborator; never performs provider I/O."""

    def __init__(
        self,
        *,
        proposal: dict[str, Any] | None = None,
        raw_response: str | None = None,
        error: Exception | None = None,
        provider: str = "offline_fake",
        model: str = "offline-fixture",
    ) -> None:
        self.provider = provider
        self.model = model
        self._proposal = proposal
        self._raw_response = raw_response
        self._error = error

    async def propose(self, baseline: dict[str, Any]) -> dict[str, Any]:
        del baseline
        if self._error is not None:
            raise self._error
        if self._raw_response is not None:
            return _typed_proposal(json.loads(self._raw_response))
        return _typed_proposal(self._proposal if self._proposal is not None else {"adjustments": []})


class DecisionReviewService:
    """Persist a typed optional proposal without granting it decision authority."""

    def __init__(
        self,
        *,
        repository: Any,
        gateway: AIReviewGateway | None = None,
        fixture_compose: bool | None = None,
    ) -> None:
        self._repository = repository
        self._gateway = gateway
        self._fixture_compose = (
            os.environ.get("PHASE1_FIXTURE_MODE", "").strip().lower() in {"1", "true", "yes"}
            if fixture_compose is None
            else fixture_compose
        )

    async def review(self, *, run_id: str) -> dict[str, Any]:
        from app.decision.replay import assert_review_allowed

        assert_review_allowed()
        run = self._repository.get_decision_run(run_id)
        if run is None:
            raise ValueError("decision run not found")
        unavailable = {"review_status": "unavailable", "final": run["final"]}
        if self._fixture_compose or self._gateway is None or run["proposal"] is not None:
            return unavailable
        try:
            proposal = await self._gateway.propose(run["baseline"])
            self._repository.record_ai_review_proposal(
                run_id=run_id,
                provider=self._gateway.provider,
                model=self._gateway.model,
                proposal=proposal,
            )
        except (RuntimeError, ValueError, TypeError):
            return unavailable
        persisted = self._repository.get_decision_run(run_id)
        assert persisted is not None
        return {"review_status": "available", "final": persisted["final"]}
