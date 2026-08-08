"""Deterministic Alpha Factory core: vocabulary + grammar fingerprint authority.

Phase 46 Wave 1 establishes the versioned grammar/vocabulary authority that every
downstream plan anchors on (AF-REQ-02 SC1).  This module computes a stable,
deterministic SHA-256 fingerprint over the complete restricted Factor DSL
vocabulary and the expression-space structural constraints, populates the
reserved manifest fingerprint slots server-side at freeze time, and fails closed
when a stored run's vocabulary no longer matches the live DSL.

The module imports only :mod:`factor_dsl` (the single legal grammar) and
:mod:`run_contract` (canonical serialization + digest helpers).  It deliberately
holds no evaluation, provider, admission, broker, repository, or worker
authority (T-46-03; the static guard is tightened in plan 46-04).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from app.research import factor_dsl
from app.research.run_contract import digest_bytes

# Versioning constants pinned for cross-process replay stability (plan 46-02).
FACTORY_VERSION: Final = "alpha-factory-v1"
PRNG_ALGORITHM: Final = "python-random-MT19937-v1"
CANONICAL_FORM: Final = "factor-dsl-canonical-v1"
DEFAULT_MAX_DEPTH: Final = 6
DEFAULT_MAX_NODES: Final = 40

# Operators are pinned here because the DSL exposes them only inline inside
# ``_validate_expression`` (factor_dsl.py) rather than as named constants; a
# future operator must be added to both the validator and this literal so the
# fingerprint tracks it (plan-check W2).
_BINARY_OPERATORS: Final[tuple[str, ...]] = ("+", "-", "*", "/")
_UNARY_OPERATORS: Final[tuple[str, ...]] = ("-",)


def vocabulary_fingerprint() -> str:
    """Deterministic SHA-256 over the complete restricted Factor DSL vocabulary.

    Computed from the *live* ``factor_dsl`` constants, so any change to the
    allowed/denied fields, operators, functions, arity, partition semantics, or
    the max rolling window alters the digest.  A stored run whose vocabulary no
    longer matches the live DSL therefore fails closed on replay instead of
    being silently reinterpreted (AlphaMaster ``FORMULA_VOCAB.verify()`` pattern
    adapted for the existing DSL, not StackVM).
    """
    return digest_bytes({
        "dsl_version": factor_dsl.DSL_VERSION,
        "fields": sorted(factor_dsl.ALLOWED_FIELDS),
        "denied_fields": sorted(factor_dsl.DENIED_FIELDS),
        "binary_operators": list(_BINARY_OPERATORS),
        "unary_operators": list(_UNARY_OPERATORS),
        "functions": dict(sorted(factor_dsl._FUNCTION_ARITY.items())),
        "partition_semantics": dict(sorted(factor_dsl._FUNCTION_PARTITION.items())),
        "max_rolling_window": factor_dsl.MAX_ROLLING_WINDOW,
    })


def grammar_fingerprint(
    *, max_depth: int = DEFAULT_MAX_DEPTH, max_nodes: int = DEFAULT_MAX_NODES
) -> str:
    """Deterministic SHA-256 over the expression-space structural constraints.

    Folds the canonical-form id, the max AST depth, the max node count, and the
    pinned PRNG algorithm id, so any change to the legal candidate space mints a
    new frozen run instead of mutating the original.  Complexity limits are also
    enforced as budgets in plans 46-03/46-04; they live in the fingerprint
    because they define the legal expression space (open-question O1).
    """
    return digest_bytes({
        "canonical_form": CANONICAL_FORM,
        "max_depth": max_depth,
        "max_nodes": max_nodes,
        "prng_algorithm": PRNG_ALGORITHM,
    })


class VocabularyMismatchError(ValueError):
    """A frozen run's vocabulary no longer matches the live Factor DSL.

    Raised on replay/load when the stored ``vocabulary_fingerprint`` differs
    from the value recomputed from the live DSL, so stored canonical
    expressions cannot be silently reinterpreted against a changed grammar
    (T-46-02).  The ``frozen``/``live`` attributes carry both digests for
    structured diagnostics.
    """

    def __init__(self, *, frozen: str | None, live: str) -> None:
        self.frozen = frozen
        self.live = live
        super().__init__(
            "vocabulary fingerprint mismatch: the frozen run's vocabulary no "
            "longer matches the live Factor DSL; refusing to reinterpret stored "
            f"tokens (frozen={frozen!r}, live={live})"
        )


def normalize_manifest_fingerprints(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shallow-copied manifest with server-owned fingerprint slots.

    ``grammar.fingerprint`` is set from the live grammar constraints (honouring
    any declared ``max_depth``/``max_nodes``) and ``vocabulary.fingerprint``
    from the live DSL vocabulary, overriding any client-supplied value so a
    forged manifest fingerprint cannot survive freeze (research Pitfall 5,
    T-46-01).  Every other key is left untouched and the caller's mapping is
    never mutated.
    """
    normalized: dict[str, Any] = dict(manifest)
    grammar = dict(normalized["grammar"])
    grammar["fingerprint"] = grammar_fingerprint(
        max_depth=grammar.get("max_depth", DEFAULT_MAX_DEPTH),
        max_nodes=grammar.get("max_nodes", DEFAULT_MAX_NODES),
    )
    normalized["grammar"] = grammar
    vocabulary = dict(normalized["vocabulary"])
    vocabulary["fingerprint"] = vocabulary_fingerprint()
    normalized["vocabulary"] = vocabulary
    return normalized


def verify_vocabulary_fingerprint(frozen: str | None) -> None:
    """Fail closed unless ``frozen`` matches the live vocabulary fingerprint.

    On replay or load the live vocabulary fingerprint is recomputed and
    compared against the stored value; a missing value or any mismatch means
    stored canonical expressions may reference tokens the live grammar
    interprets differently, so the run fails closed rather than reinterpreting
    stored tokens (T-46-02).
    """
    live = vocabulary_fingerprint()
    if not isinstance(frozen, str) or frozen != live:
        raise VocabularyMismatchError(frozen=frozen, live=live)
