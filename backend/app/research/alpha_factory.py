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

import random
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from typing import Any, Final

from app.research import factor_dsl
from app.research.factor_dsl import Expression
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


# ---------------------------------------------------------------------------
# Phase 46 Wave 2 (AF-REQ-02 SC2): deterministic seeded generation engine
# ---------------------------------------------------------------------------

# Shared, immutable source location for every generator-built node.  The
# canonical serializer only reads locations for diagnostics, so a single
# sentinel is safe and keeps generated nodes allocation-light.
_LOC = factor_dsl.SourceLocation(offset=0, line=1, column=1)

# Frozen rolling windows used by the seed-pool enumeration (O3).  Every value is
# a positive integer inside the legal ``rolling_mean`` window range, so a
# rolling_mean seed canonicalizes by construction.
_SEED_ROLLING_WINDOWS: Final[tuple[int, ...]] = (5, 20, 60)


def candidate_digest(
    *,
    canonical_expression: str,
    seed: int,
    step: int,
    operation: str,
    vocab_version: str,
) -> str:
    """Provenance-encoding lowercase SHA-256 over one candidate's identity.

    The digest folds in ``step`` and ``operation`` so two structurally
    identical expressions emitted at different steps (or via different
    operations) get distinct digests, while the same frozen inputs always
    reproduce the same digest sequence (AF-REQ-02 SC2; matches the
    one-row-per-attempt model in ``repository.append_candidate_attempt``).
    """
    return digest_bytes(
        {
            "expression": canonical_expression,
            "vocab_version": vocab_version,
            "seed": seed,
            "step": step,
            "operation": operation,
        }
    )


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """One deterministic candidate: AST plus provenance, reproducible from the seed.

    ``step`` is the 0-based attempt ordinal (``attempt_ordinal == step + 1``).
    ``parent_steps`` is empty for seed candidates, a single preceding step for
    mutations, and two distinct preceding steps for crossovers.
    """

    step: int
    operation: str
    ast: Expression
    canonical_expression: str
    parent_steps: tuple[int, ...]
    seed: int

    @property
    def digest(self) -> str:
        """Stable SHA-256 over this candidate's full provenance identity."""
        return candidate_digest(
            canonical_expression=self.canonical_expression,
            seed=self.seed,
            step=self.step,
            operation=self.operation,
            vocab_version=vocabulary_fingerprint(),
        )

    @property
    def attempt_ordinal(self) -> int:
        """1-based ordinal matching ``repository.append_candidate_attempt``."""
        return self.step + 1


class AlphaFactory:
    """Deterministic seeded candidate-generation engine over the Factor DSL.

    Given a frozen seed and complexity limits, the factory emits a bounded,
    canonical candidate stream whose expressions, digests, operation labels,
    parent/child lineage, and ordering are reproducible from the seed alone
    (AF-REQ-02 SC2).

    All nondeterministic draws come from a single instance-local
    ``random.Random(seed)``; the global :mod:`random` module is never drawn
    from, so worker timing cannot perturb the sequence (T-46-04 / T-46-05).

    The factory builds legal Factor DSL AST nodes and feeds every output
    through ``factor_dsl.canonicalize`` (the single validator / serializer —
    no second expression engine). Validation-as-rejection (plan 46-03) and
    diversity/budget/worker persistence (plan 46-04) layer on top.
    """

    def __init__(
        self,
        seed: int,
        *,
        max_depth: int = DEFAULT_MAX_DEPTH,
        max_nodes: int = DEFAULT_MAX_NODES,
        max_candidates: int = 256,
    ) -> None:
        if max_depth < 1:
            raise ValueError("max_depth must be >= 1")
        if max_nodes < 1:
            raise ValueError("max_nodes must be >= 1")
        if max_candidates < 1:
            raise ValueError("max_candidates must be >= 1")
        self._seed = int(seed)
        self._max_depth = int(max_depth)
        self._max_nodes = int(max_nodes)
        self._max_candidates = int(max_candidates)
        # Single instance-local PRNG (T-46-04): the global random module is
        # never drawn from, so the whole stream is reproducible from the seed.
        self._rng = random.Random(self._seed)
        self._fields_sorted: list[str] = sorted(factor_dsl.ALLOWED_FIELDS)
        # The seed pool is a pure deterministic enumeration that consumes NO
        # PRNG draws, so the mutation/crossover draw sequence (task 46-02-02)
        # is independent of the seed-pool size.
        self._seed_pool: list[Expression] = list(self._iter_seed_pool())
        self._results: list[GenerationResult] = []
        self._step = 0

    # -- public API -------------------------------------------------------

    def generate_next(self) -> GenerationResult | None:
        """Produce the next seed candidate, or ``None`` once the budget is hit.

        Evolution (mutation / crossover) is added in task 46-02-02; until then
        generation stops at the seed-pool boundary or the candidate budget,
        whichever comes first.
        """
        if self._step >= self._max_candidates:
            return None
        if self._step >= len(self._seed_pool):
            return None
        result = self._produce_seed(self._step)
        self._results.append(result)
        self._step += 1
        return result

    def replay_to(self, k: int) -> list[GenerationResult]:
        """Re-derive the first ``k`` candidates from the frozen seed.

        No PRNG state is serialized: a fresh factory is rebuilt from the seed
        and replayed, so the result equals the live stream's prefix for any
        ``k`` regardless of how far this instance has advanced (O2).
        """
        if k < 0:
            raise ValueError("k must be non-negative")
        replay = AlphaFactory(
            self._seed,
            max_depth=self._max_depth,
            max_nodes=self._max_nodes,
            max_candidates=self._max_candidates,
        )
        return [replay.generate_next() for _ in range(min(k, self._max_candidates))]

    @property
    def step(self) -> int:
        """Number of candidates produced so far (next step index)."""
        return self._step

    @property
    def seed_pool_size(self) -> int:
        """Size of the deterministic seed-pool enumeration (vocab-derived)."""
        return len(self._seed_pool)

    # -- seed-pool generation --------------------------------------------

    def _produce_seed(self, step: int) -> GenerationResult:
        ast = self._seed_pool[step]
        canonical = factor_dsl.canonicalize(ast)
        return GenerationResult(
            step=step,
            operation="seed",
            ast=ast,
            canonical_expression=canonical,
            parent_steps=(),
            seed=self._seed,
        )

    def _iter_seed_pool(self) -> Iterator[Expression]:
        """Frozen seed-pool enumeration order (O3); consumes NO PRNG draws.

        Order: (1) single allowed fields, (2) unary negation of fields,
        (3) ``rank``/``zscore`` of single fields, (4) ``rolling_mean`` variants
        over a field with legal windows, (5) small binary trees over
        field/field and field/literal.  Every emitted node is a legal DSL AST,
        so each canonicalizes without raising.
        """
        fields = self._fields_sorted
        count = len(fields)
        # (1) single allowed fields
        for name in fields:
            yield factor_dsl.Field(name, _LOC)
        # (2) unary negation of fields
        for name in fields:
            yield factor_dsl.Unary("-", factor_dsl.Field(name, _LOC), _LOC)
        # (3) rank / zscore of single fields
        for name in fields:
            yield factor_dsl.Call("rank", (factor_dsl.Field(name, _LOC),), _LOC)
        for name in fields:
            yield factor_dsl.Call("zscore", (factor_dsl.Field(name, _LOC),), _LOC)
        # (4) rolling_mean variants over a field with legal windows
        for name in fields:
            for window in _SEED_ROLLING_WINDOWS:
                yield factor_dsl.Call(
                    "rolling_mean",
                    (factor_dsl.Field(name, _LOC), factor_dsl.Number(float(window), _LOC)),
                    _LOC,
                )
        # (5) small binary trees over field/field and field/literal
        if count >= 2:
            yield factor_dsl.Binary("+", factor_dsl.Field(fields[0], _LOC), factor_dsl.Field(fields[1], _LOC), _LOC)
        if count >= 4:
            yield factor_dsl.Binary("-", factor_dsl.Field(fields[2], _LOC), factor_dsl.Field(fields[3], _LOC), _LOC)
        if count >= 6:
            yield factor_dsl.Binary("*", factor_dsl.Field(fields[4], _LOC), factor_dsl.Field(fields[5], _LOC), _LOC)
        yield factor_dsl.Binary("*", factor_dsl.Field(fields[0], _LOC), factor_dsl.Number(2.0, _LOC), _LOC)
        denom_source = fields[1] if count >= 2 else fields[0]
        yield factor_dsl.Binary("/", factor_dsl.Field(denom_source, _LOC), factor_dsl.Number(100.0, _LOC), _LOC)
