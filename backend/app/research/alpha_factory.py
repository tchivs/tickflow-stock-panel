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
