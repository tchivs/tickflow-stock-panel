"""Strict model boundary for server-owned analysis generation."""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from app.analysis.schemas import FrozenEvidenceSnapshot, GeneratedAnalysis
from app.services import ai_provider

Message = dict[str, str]
GenerateText = Callable[..., Awaitable[str]]

_SYSTEM_PROMPT = (
    "You produce bounded investment research JSON only. Use only supplied source_id values. "
    "Do not call tools, browse, place orders, alter source grades, cross-check states, or lifecycle state. "
    "Return exactly the GeneratedAnalysis JSON schema with perspectives, valuation, and ic_memo."
)


def analysis_messages(snapshot: FrozenEvidenceSnapshot) -> list[Message]:
    """Build the complete provider payload from immutable server evidence."""
    payload = {
        "subject_key": snapshot.subject_key,
        "policy_version": snapshot.policy_version,
        "context_status": snapshot.context_status,
        "evidence_fingerprint": snapshot.evidence_fingerprint,
        "sources": [source.model_dump(mode="json") for source in snapshot.sources],
        "material_numbers": [number.model_dump(mode="json") for number in snapshot.material_numbers],
    }
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)},
    ]


class ConfiguredAnalysisAdapter:
    """Configured, transport-injectable adapter that always returns a typed body."""

    def __init__(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        generate_text: GenerateText | None = None,
        timeout: float = 30.0,
        max_tokens: int = 2000,
    ) -> None:
        if timeout <= 0 or max_tokens <= 0:
            raise ValueError("analysis adapter timeout and max_tokens must be positive")
        self.provider = provider or ai_provider.current_ai_provider()
        self.model = model or ai_provider.current_ai_model()
        self._generate_text = generate_text or ai_provider.generate_ai_text
        self.timeout = timeout
        self.max_tokens = max_tokens

    async def ainvoke(self, snapshot: FrozenEvidenceSnapshot) -> GeneratedAnalysis:
        if not self.model:
            raise RuntimeError("configured analysis provider is unavailable")
        try:
            raw = await self._generate_text(
                analysis_messages(snapshot),
                temperature=0,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
            )
        except RuntimeError:
            # The host provider already turns transport errors into safe messages.
            raise
        try:
            return GeneratedAnalysis.model_validate_json(raw)
        except (TypeError, ValueError) as error:
            raise ValueError("generated analysis failed schema validation") from error
