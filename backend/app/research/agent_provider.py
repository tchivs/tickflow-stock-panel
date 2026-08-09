"""Agent provider seam + failure taxonomy for the FactorResearchAgent.

Phase 48 (AF-REQ-14). This module owns the boundary between the deterministic
research pipeline and the untrusted LLM provider:

* :data:`FAILURE_CLASSES` — the canonical failure taxonomy (research §7.1).
* :class:`ProviderFailure` / :func:`classify_provider_failure` — deterministic
  classification of any provider error into a transient/permanent class.
* :func:`retry_policy` — the bounded retry decision (transient only).
* :class:`ProviderCallError` / :class:`AnalysisAttempt` / :class:`AgentProviderSeam`
  — the transport wrapper with bounded retry, cooperative cancellation,
  raw-response capture (checksum-by-default), and one ``AnalysisRecord`` row per
  attempt. The seam has NO branch that synthesizes a fallback draft (SC4): the
  only success path is a real provider response.
"""
from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from app.research.run_contract import canonical_bounded_json, validate_bounded_json

FAILURE_CLASSES: frozenset[str] = frozenset({
    "malformed_json",
    "schema_violation",
    "parse_failure",
    "timeout",
    "rate_limited",
    "unavailable",
    "refused",
    "partial",
    "cancelled",
})

# (transient, terminal) per failure class, derived from research §7.1.
_FAILURE_PROPS: dict[str, tuple[bool, bool]] = {
    "malformed_json": (False, True),
    "schema_violation": (False, True),
    "parse_failure": (False, True),
    "timeout": (True, False),
    "rate_limited": (True, False),
    "unavailable": (True, False),
    "refused": (False, True),
    "partial": (False, False),
    "cancelled": (False, True),
}

_RETRYABLE_CLASSES: frozenset[str] = frozenset({"timeout", "rate_limited", "unavailable"})

_REASON_MSG_LIMIT = 200
_SCHEMA_MARKERS: tuple[str, ...] = (
    "unsupported field",
    "missing field",
    "unexpected field",
    "unknown key",
    "must be a json object",
    "schema",
    "extra field",
)

@dataclass(frozen=True, slots=True)
class ProviderFailure:
    """One classified provider failure with bounded machine-readable reason."""

    klass: str
    transient: bool
    terminal: bool
    reason: Mapping[str, Any]
    http_status: int | None

@dataclass(frozen=True, slots=True)
class RetryDecision:
    """Bounded retry policy for one failure class."""

    should_retry: bool
    max_retries: int
    base_delay: float
    factor: float
    cap: float


_RETRY_TRANSIENT = RetryDecision(should_retry=True, max_retries=3, base_delay=1.0, factor=2.0, cap=30.0)
_RETRY_NONE = RetryDecision(should_retry=False, max_retries=0, base_delay=0.0, factor=0.0, cap=0.0)


def _extract_http_status(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        if response is not None:
            status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _bounded_reason(klass: str, exc: BaseException, http_status: int | None) -> Mapping[str, Any]:
    payload: dict[str, Any] = {"class": klass, "exception": type(exc).__name__}
    message = str(exc)
    if message:
        payload["message"] = message[:_REASON_MSG_LIMIT]
    if http_status is not None:
        payload["http_status"] = http_status
    validate_bounded_json(payload, f"provider failure {klass}")
    return payload


def _has_schema_marker(exc: BaseException) -> bool:
    if getattr(exc, "provider_schema_error", False):
        return True
    text = str(exc).lower()
    return any(marker in text for marker in _SCHEMA_MARKERS)


def classify_provider_failure(
    exc: BaseException, *, raw_response: str | None = None
) -> ProviderFailure:
    """Deterministically classify a provider error (research §7.1).

    Pure over ``(exc class, http status, raw_response)``: the same inputs always
    yield the same :class:`ProviderFailure`. Ordering honours the type hierarchy
    (``JSONDecodeError`` and ``FactorDslError`` are ``ValueError`` subclasses, so
    they are matched before the generic schema-marker branch).
    """
    # Explicit override lets Stage services tag a precise class.
    override = getattr(exc, "provider_failure_class", None)
    if isinstance(override, str) and override in FAILURE_CLASSES:
        transient, terminal = _FAILURE_PROPS[override]
        return ProviderFailure(
            klass=override,
            transient=transient,
            terminal=terminal,
            reason=_bounded_reason(override, exc, _extract_http_status(exc)),
            http_status=_extract_http_status(exc),
        )

    http_status = _extract_http_status(exc)
    class_name = type(exc).__name__

    if isinstance(exc, json.JSONDecodeError):
        klass = "malformed_json"
    elif _is_factor_dsl_error(exc):
        klass = "parse_failure"
    elif isinstance(exc, ValueError) and _has_schema_marker(exc):
        klass = "schema_violation"
    elif http_status in (408, 504) or "Timeout" in class_name:
        klass = "timeout"
    elif http_status == 429:
        klass = "rate_limited"
    elif http_status in (500, 502, 503) or "Connection" in class_name:
        klass = "unavailable"
    elif http_status in (400, 401, 403, 404):
        klass = "refused"
    elif raw_response is not None and getattr(exc, "partial_failure", False):
        klass = "partial"
    else:
        # Unknown transport error: treat as transient so a genuine blip is
        # retried (bounded), then fails terminally. Never a fallback.
        klass = "unavailable"

    transient, terminal = _FAILURE_PROPS[klass]
    return ProviderFailure(
        klass=klass,
        transient=transient,
        terminal=terminal,
        reason=_bounded_reason(klass, exc, http_status),
        http_status=http_status,
    )


def retry_policy(failure: ProviderFailure) -> RetryDecision:
    """Transient classes retry with bounded exponential backoff; all else do not."""
    if failure.klass in _RETRYABLE_CLASSES:
        return _RETRY_TRANSIENT
    return _RETRY_NONE


def _is_factor_dsl_error(exc: BaseException) -> bool:
    try:
        from app.research.factor_dsl import FactorDslError
    except Exception:  # pragma: no cover - DSL is always importable in-app
        return False
    return isinstance(exc, FactorDslError)


def _sha256_hex(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------
# Provider call error + analysis attempt value object
# ------------------------------------------------------------------


class ProviderCallError(RuntimeError):
    """A provider call that failed terminally (or was cancelled).

    Carries the classified :class:`ProviderFailure` so callers can record a
    terminal reason and never need to re-classify.
    """

    def __init__(self, failure: ProviderFailure) -> None:
        self.failure = failure
        super().__init__(f"provider call failed: {failure.klass}")


@dataclass(frozen=True, slots=True)
class AnalysisAttempt:
    """A successful provider call result plus attempt identity."""

    raw: str | None
    attempt_ordinal: int
    stage: str
    provider: str
    model: str
    response_sha256: str | None
    response_byte_size: int | None


# ------------------------------------------------------------------
# AgentProviderSeam — retry / backoff / cancellation / no fallback
# ------------------------------------------------------------------


class AgentProviderSeam:
    """Wrap an injectable provider call with bounded retry and full audit.

    The seam is the only path from the deterministic pipeline to the provider.
    It owns retry timing/backoff (the SDK retry stays OFF), cooperative
    cancellation, raw-response capture (checksum-by-default), and one
    ``AnalysisRecord`` row per attempt. There is NO ``except`` branch that
    returns a synthesized payload: the only success path is a real response
    (SC4, hypotheses.py:157-160 pattern).
    """

    def __init__(
        self,
        *,
        generate_text: Callable[..., Awaitable[str]] | None = None,
        record_analysis_attempt: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        if generate_text is None:
            from app.services import ai_provider

            generate_text = ai_provider.generate_ai_text
        if record_analysis_attempt is None:
            # Lazy default: bound to a repository instance at call time via `repo`.
            record_analysis_attempt = None
        self._generate_text = generate_text
        self._record_analysis_attempt = record_analysis_attempt

    async def request(
        self,
        *,
        stage: str,
        messages: Sequence[Mapping[str, str]],
        request_payload: Mapping[str, Any],
        repo: Any,
        run_id: str,
        schema_version: str,
        template_version: str,
        provider: str,
        model: str,
        model_version: str | None,
        cancel_check: Callable[[], bool] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        retain_raw_artifact_service: Any | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1200,
        timeout: float = 120.0,
    ) -> AnalysisAttempt:
        request_scope_sha256 = _sha256_hex(
            canonical_bounded_json(request_payload, "request scope")
        )
        recorder = self._record_analysis_attempt or getattr(repo, "record_analysis_attempt")
        attempt_ordinal = 0
        while True:
            attempt_ordinal += 1
            start = monotonic()
            try:
                raw = await self._generate_text(
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
            except BaseException as exc:  # noqa: BLE001 - classify every provider error.
                latency_ms = int((monotonic() - start) * 1000)
                failure = classify_provider_failure(exc, raw_response=None)
                # Cooperative cancellation is checked before any retry.
                if cancel_check is not None and cancel_check():
                    cancel_failure = ProviderFailure(
                        klass="cancelled",
                        transient=False,
                        terminal=True,
                        reason=_bounded_reason("cancelled", exc, None),
                        http_status=None,
                    )
                    recorder(
                        run_id=run_id,
                        stage=stage,
                        attempt_ordinal=attempt_ordinal,
                        template_version=template_version,
                        schema_version=schema_version,
                        provider=provider,
                        model=model,
                        model_version=model_version,
                        request_scope_sha256=request_scope_sha256,
                        failure_class="cancelled",
                        cancelled=1,
                        retries=attempt_ordinal - 1,
                        latency_ms=latency_ms,
                        outcome="cancelled",
                    )
                    raise ProviderCallError(cancel_failure) from exc
                decision = retry_policy(failure)
                recorder(
                    run_id=run_id,
                    stage=stage,
                    attempt_ordinal=attempt_ordinal,
                    template_version=template_version,
                    schema_version=schema_version,
                    provider=provider,
                    model=model,
                    model_version=model_version,
                    request_scope_sha256=request_scope_sha256,
                    failure_class=failure.klass,
                    failure_reason=failure.reason,
                    retries=attempt_ordinal - 1,
                    latency_ms=latency_ms,
                    outcome="failed",
                )
                if decision.should_retry and attempt_ordinal <= decision.max_retries:
                    import random

                    delay = min(
                        decision.cap,
                        decision.base_delay * decision.factor ** (attempt_ordinal - 1),
                    ) * (0.5 + random.random())
                    await sleep(delay)
                    continue
                raise ProviderCallError(failure) from exc

            # Success path — the ONLY way to return a payload.
            latency_ms = int((monotonic() - start) * 1000)
            response_sha256 = _sha256_hex(raw)
            response_byte_size = len(raw.encode("utf-8"))
            response_artifact_id = None
            if retain_raw_artifact_service is not None:
                response_artifact_id = retain_raw_artifact_service.store(
                    run_id=run_id,
                    stage=stage,
                    raw=raw,
                    checksum_sha256=response_sha256,
                    byte_size=response_byte_size,
                )
            recorder(
                run_id=run_id,
                stage=stage,
                attempt_ordinal=attempt_ordinal,
                template_version=template_version,
                schema_version=schema_version,
                provider=provider,
                model=model,
                model_version=model_version,
                request_scope_sha256=request_scope_sha256,
                response_sha256=response_sha256,
                response_byte_size=response_byte_size,
                response_artifact_id=response_artifact_id,
                parsed_output_sha256=None,  # set by the Stage service after parsing.
                retries=attempt_ordinal - 1,
                latency_ms=latency_ms,
                outcome="proposed" if stage == "stage1" else "validated",
            )
            return AnalysisAttempt(
                raw=raw,
                attempt_ordinal=attempt_ordinal,
                stage=stage,
                provider=provider,
                model=model,
                response_sha256=response_sha256,
                response_byte_size=response_byte_size,
            )
