"""Explicit-declaration offline fixture provider for the FactorResearchAgent.

Phase 48-04 (AF-REQ-26 §6.3). Generalizes ``OfflineFakeHypothesisGateway``
(hypotheses.py:163-187) into a first-class, declared, non-production provider
that produces a known full deterministic trace
(``preflight -> stage1 -> stage2 -> AnalysisRecord``) with zero network/provider
calls.

Security contract (R3 / D-48-04 / SC5):

* **Explicit declaration only.** The fixture activates ONLY on an explicit,
  non-default selector (``is_fixture_explicitly_selected``). A missing or
  erroring production provider NEVER branches to the fixture — that would
  violate SC4's no-fallback invariant. The fixture is a *peer* provider
  selectable only by explicit declaration.
* **Non-production label.** Every fixture AnalysisRecord carries
  ``provider='offline_fixture'`` / ``model='offline-fixture-v1'`` so fixture
  evidence is always visibly non-production.
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from app.research.agent_stage1 import STAGE_ONE_SCHEMA_VERSION
from app.research.agent_stage2 import STAGE_TWO_SCHEMA_VERSION

FIXTURE_PROVIDER = "offline_fixture"
FIXTURE_MODEL = "offline-fixture-v1"
FIXTURE_MODEL_VERSION = "offline-v1"

# The known full trace is a single, deterministic, schema-valid pair of canned
# responses. The fixture never calls the provider; it only returns these bytes.
_FIXTURE_STAGE1_PAYLOAD: dict[str, Any] = {
    "schema_version": STAGE_ONE_SCHEMA_VERSION,
    "hypotheses": [
        {
            "expression": "momentum_20d",
            "explanation": (
                "Twenty-day price momentum as a trend-following factor signal. "
                "Positive recent return predicts short-horizon continuation in "
                "liquid names under the supplied restricted factor DSL."
            ),
            "assumptions": [
                "the trading universe is liquid",
                "no look-ahead in the momentum window",
            ],
            "scope": "daily cross-section over the measured window",
            "uncertainty": "low",
            "evidence_refs": ["thesis", "measured_window"],
        }
    ],
}

_FIXTURE_STAGE2_PAYLOAD: dict[str, Any] = {
    "schema_version": STAGE_TWO_SCHEMA_VERSION,
    # An empty caveats array is schema-valid (decode_stage2_payload bounds the
    # length but does not require non-empty). With no evidence_refs there is no
    # referential-integrity surface, so the fixture trace is byte-identical and
    # cannot spuriously fail on candidate identity across runs.
    "caveats": [],
    "recommendation": {
        "disposition": "retain",
        "rationale": (
            "The momentum proposal is internally consistent with the run "
            "evidence and the frozen admission policy; advisory retain."
        ),
        "follow_up_run_dims": None,
    },
}


def _canonical(payload: Mapping[str, Any]) -> str:
    """Stable serialization of a fixture payload (sorted, compact JSON)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class FixtureTrace:
    """A known full deterministic Agent trace produced by the offline fixture."""

    stage1_raw: str
    stage2_raw: str
    validation_trace: Mapping[str, Any]


def default_fixture() -> FixtureTrace:
    """Return the one known-good full deterministic fixture trace.

    The Stage 1 payload is a momentum proposal that parses under the live
    factor DSL (``momentum_20d`` is an ``ALLOWED_FIELDS`` member); the Stage 2
    payload is a clean advisory recommendation with no mutable field. Both
    match the live schema versions. The ``validation_trace`` is a bounded
    summary of the deterministic validation outcome (provenance only).
    """
    stage1_raw = _canonical(_FIXTURE_STAGE1_PAYLOAD)
    stage2_raw = _canonical(_FIXTURE_STAGE2_PAYLOAD)
    validation_trace: Mapping[str, Any] = {
        "stage1": {
            "hypotheses": len(_FIXTURE_STAGE1_PAYLOAD["hypotheses"]),
            "schema_version": STAGE_ONE_SCHEMA_VERSION,
        },
        "stage2": {
            "caveats": len(_FIXTURE_STAGE2_PAYLOAD["caveats"]),
            "disposition": _FIXTURE_STAGE2_PAYLOAD["recommendation"]["disposition"],
            "schema_version": STAGE_TWO_SCHEMA_VERSION,
        },
        "provider": FIXTURE_PROVIDER,
        "model": FIXTURE_MODEL,
        "factor_family": "momentum",
    }
    return FixtureTrace(
        stage1_raw=stage1_raw,
        stage2_raw=stage2_raw,
        validation_trace=validation_trace,
    )


def is_fixture_explicitly_selected(settings: Mapping[str, Any] | None = None) -> bool:
    """True only when an explicit, non-default fixture selector is declared.

    The fixture is selected by an explicit ``fixture_mode`` flag (truthy) AND a
    non-empty ``fixture_name``. It is NEVER selected by a missing-provider
    fallback (R3): a ``None``/empty/default selector returns ``False`` so a
    misconfigured production run cannot silently pick the fixture.
    """
    if not isinstance(settings, Mapping):
        return False
    mode = settings.get("fixture_mode")
    name = settings.get("fixture_name")
    if not mode:  # falsy / missing / None / 0 / "" / False
        return False
    if not isinstance(name, str) or not name.strip():
        return False
    return True


class OfflineFixtureProvider:
    """A peer offline-fixture transport; it never performs provider I/O.

    The provider is selectable ONLY by explicit declaration (the caller asserts
    ``is_fixture_explicitly_selected`` before constructing/using it). It exposes
    one seam-compatible ``generate_text`` per Agent stage, returning the canned
    bytes from :func:`default_fixture` (or a supplied trace). Mirrors
    ``OfflineFakeHypothesisGateway`` (hypotheses.py:163-187) generalized to the
    full two-stage Agent.
    """

    provider = FIXTURE_PROVIDER
    model = FIXTURE_MODEL
    model_version = FIXTURE_MODEL_VERSION

    def __init__(self, trace: FixtureTrace | None = None) -> None:
        self._trace = trace if trace is not None else default_fixture()

    @property
    def trace(self) -> FixtureTrace:
        return self._trace

    # Explicit-declaration gate (delegating alias for the plan's key_link).
    is_explicitly_selected = staticmethod(is_fixture_explicitly_selected)

    def generate_text_for(
        self, stage: str
    ) -> Callable[..., Awaitable[str]]:
        """Return a seam-compatible ``generate_text`` bound to one fixture stage.

        The returned coroutine ignores its messages/temperature/timeout (the
        fixture is deterministic) and returns the canned bytes for ``stage``
        (``"stage1"`` / ``"stage2"``). It never touches the network.
        """

        async def _generate(*_args: Any, **_kwargs: Any) -> str:
            if stage == "stage1":
                return self._trace.stage1_raw
            if stage == "stage2":
                return self._trace.stage2_raw
            raise ValueError(
                f"offline fixture has no canned response for stage {stage!r}"
            )

        return _generate
