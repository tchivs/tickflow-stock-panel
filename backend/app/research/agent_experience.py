"""Read-only ExperienceLibrary seam for the FactorResearchAgent.

Phase 48-04 (AF-REQ-26 §8.2-8.3). Ships the minimal seam needed for the
offline-fixture's known full trace, with one offline-fixture implementation
keyed by ``(factor_family, objective)`` and a valid empty production default.

Scope (research §8.3): a retrieval-by-similarity experience library,
success/failure partitioning, and regime classification are explicitly
DEFERRED. Phase 48 ships only the ``ExperienceLibrary`` protocol so a later
phase can add a populated implementation without touching the Stage 1/2
contracts.

Security contract (SC4): the library is a **read-only** context consulted to
augment the prompt (like ``ai_generator`` reads ``strategy-guide-compact.md``,
ai_generator.py:15). It NEVER becomes a fallback response — a provider failure
still yields zero proposals even when the library is populated.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.research.agent_fixture import FIXTURE_MODEL, FIXTURE_PROVIDER

# Coarse factor families derived from the extract_features field set
# (factor_dsl.py:446-465). A field maps to the family its signal classically
# represents. Price/moving-average fields default to the momentum baseline
# (price-level factors); unmapped fields contribute nothing.
_FACTOR_FIELD_FAMILY: Mapping[str, str] = {
    # momentum / trend
    "momentum_5d": "momentum", "momentum_10d": "momentum",
    "momentum_20d": "momentum", "momentum_30d": "momentum",
    "momentum_60d": "momentum", "change_pct": "momentum",
    "change_amount": "momentum", "high_60d": "momentum", "low_60d": "momentum",
    "prev_close": "momentum", "consecutive_limit_ups": "momentum",
    "consecutive_limit_downs": "momentum", "macd_dif": "momentum",
    "macd_dea": "momentum", "macd_hist": "momentum",
    # mean-reversion / oscillator
    "rsi_6": "mean-reversion", "rsi_14": "mean-reversion",
    "rsi_24": "mean-reversion", "boll_upper": "mean-reversion",
    "boll_lower": "mean-reversion", "kdj_k": "mean-reversion",
    "kdj_d": "mean-reversion", "kdj_j": "mean-reversion",
    # volatility
    "annual_vol_20d": "volatility", "atr_14": "volatility",
    "amplitude": "volatility", "vol_ma5": "volatility",
    "vol_ma10": "volatility", "vol_ratio_5d": "volatility",
    # quality / liquidity
    "turnover_rate": "quality", "amount": "quality", "volume": "quality",
    # generic price level -> momentum baseline
    "open": "momentum", "high": "momentum", "low": "momentum",
    "close": "momentum", "ma5": "momentum", "ma10": "momentum",
    "ma20": "momentum", "ma30": "momentum", "ma60": "momentum",
    "ema5": "momentum", "ema10": "momentum", "ema20": "momentum",
    "ema30": "momentum", "ema60": "momentum",
}

_FAMILIES: tuple[str, ...] = ("momentum", "mean-reversion", "volatility", "quality")
_DEFAULT_FAMILY = "momentum"


def derive_factor_family(permitted_fields: Iterable[str]) -> str:
    """Map a permitted field set to a coarse factor family.

    Counts the family each permitted field belongs to (derived from the
    ``extract_features`` field set, factor_dsl.py:446-465) and returns the
    dominant family. Unmapped or empty field sets default to ``"momentum"``
    (the fixture's known-good family). Deterministic: identical input always
    yields identical output, independent of iteration order (ties resolve to
    declaration order, with ``momentum`` first).
    """
    counts: dict[str, int] = {family: 0 for family in _FAMILIES}
    for field in permitted_fields:
        family = _FACTOR_FIELD_FAMILY.get(str(field))
        if family is not None:
            counts[family] += 1
    best = _DEFAULT_FAMILY
    best_count = 0
    for family in _FAMILIES:  # declaration order breaks ties deterministically
        if counts[family] > best_count:
            best = family
            best_count = counts[family]
    return best


@dataclass(frozen=True, slots=True)
class ExperienceEntry:
    """One read-only experience summary keyed by (factor_family, objective)."""

    factor_family: str
    objective: str
    summary: str
    provider: str
    model: str


@runtime_checkable
class ExperienceLibrary(Protocol):
    """Read-only retrieval of past-experience summaries (never a provider call).

    The protocol is the only contract a later phase implements; the Stage 1/2
    services consume it only to *augment* prompt context. A populated library
    is NEVER a fallback response (SC4): a provider failure yields zero
    proposals regardless of library contents.
    """

    def lookup(
        self, *, factor_family: str, objective: str
    ) -> Sequence[ExperienceEntry]: ...


class EmptyExperienceLibrary:
    """The valid production default: an empty library yields nothing.

    In production the Agent runs without experience context (the library never
    becomes a fallback response, SC4). This implementation makes zero provider
    calls to populate itself.
    """

    def lookup(
        self, *, factor_family: str, objective: str
    ) -> tuple[ExperienceEntry, ...]:
        return ()


class OfflineFixtureExperienceLibrary:
    """Offline-fixture seeded library keyed by (factor_family, objective).

    Seeded by the offline fixture's canned experience (a known-good Stage 1
    proposal summary). READ-ONLY: lookup makes zero provider calls. Returns the
    canned entry for a matching key and nothing otherwise. This satisfies the
    AF-REQ-26 "known full trace" without any provider call to populate it.
    """

    def __init__(self, entries: Iterable[ExperienceEntry] | None = None) -> None:
        if entries is None:
            entries = (
                ExperienceEntry(
                    factor_family="momentum",
                    objective="sharpe",
                    summary=(
                        "Known-good momentum factor: twenty-day price momentum "
                        "as a trend-following cross-sectional signal, retained "
                        "as advisory context only."
                    ),
                    provider=FIXTURE_PROVIDER,
                    model=FIXTURE_MODEL,
                ),
            )
        self._entries: tuple[ExperienceEntry, ...] = tuple(entries)

    def lookup(
        self, *, factor_family: str, objective: str
    ) -> tuple[ExperienceEntry, ...]:
        return tuple(
            entry
            for entry in self._entries
            if entry.factor_family == factor_family and entry.objective == objective
        )


# ``EmptyExperienceLibrary`` and ``OfflineFixtureExperienceLibrary`` satisfy the
# ``ExperienceLibrary`` runtime-checkable protocol via structural lookup().
__all__ = [
    "ExperienceEntry",
    "ExperienceLibrary",
    "EmptyExperienceLibrary",
    "OfflineFixtureExperienceLibrary",
    "derive_factor_family",
]

