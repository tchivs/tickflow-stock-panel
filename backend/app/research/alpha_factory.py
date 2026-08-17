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
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Final, Literal

from app.research import factor_dsl
from app.research.factor_dsl import Expression, FactorFeatures
from app.research.factor_registry import _jaccard
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

# Literals and functions used by the evolution phase.  Every safe literal is a
# positive finite integer inside the legal rolling window range (1..252) and
# non-zero, so a mutated/grafted literal canonicalizes except for the rare
# clip-bound-ordering case, which ``factor_dsl.canonicalize`` rejects (retry).
_SAFE_LITERALS: Final[tuple[float, ...]] = (1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0)
# v3 (Alpha158 移植): 时序算子进入演化空间。ref/rolling_* 窗口参数用
# _SEED_ROLLING_WINDOWS 采样 (全部落在 1..252 合法区), rolling_quantile 的
# 分位数参数单独走 (0,1) 开区间字面量, 保证 by-construction 合法。
_V3_WINDOWED_UNARY: Final[tuple[str, ...]] = (
    "ref", "rolling_std", "rolling_sum", "rolling_min", "rolling_max",
)
_QUANTILE_LITERALS: Final[tuple[float, ...]] = (0.25, 0.5, 0.75)
_FUNCTION_CHOICES: Final[tuple[str, ...]] = (
    "abs", "sign", "log1p", "rank", "zscore", "rolling_mean", "clip",
    *_V3_WINDOWED_UNARY, "rolling_quantile", "rolling_corr", "max", "min",
)

def _build_v3_seeds() -> tuple[Expression, ...]:
    """v3 时序种子块: 核心字段 x 全部新算子形态, by-construction 合法。"""
    seeds: list[Expression] = []
    for name in ("close", "volume"):
        for operator in _V3_WINDOWED_UNARY:
            for window in _SEED_ROLLING_WINDOWS:
                seeds.append(factor_dsl.Call(
                    operator,
                    (factor_dsl.Field(name, _LOC), factor_dsl.Number(float(window), _LOC)),
                    _LOC,
                ))
    for name in ("close", "volume"):
        for quantile in (0.25, 0.75):
            seeds.append(factor_dsl.Call(
                "rolling_quantile",
                (factor_dsl.Field(name, _LOC), factor_dsl.Number(20.0, _LOC),
                 factor_dsl.Number(quantile, _LOC)),
                _LOC,
            ))
    seeds.append(factor_dsl.Call(
        "rolling_corr",
        (factor_dsl.Field("close", _LOC), factor_dsl.Field("volume", _LOC),
         factor_dsl.Number(20.0, _LOC)),
        _LOC,
    ))
    seeds.append(factor_dsl.Call("max", (factor_dsl.Field("high", _LOC), factor_dsl.Field("close", _LOC)), _LOC))
    seeds.append(factor_dsl.Call("min", (factor_dsl.Field("low", _LOC), factor_dsl.Field("close", _LOC)), _LOC))
    return tuple(seeds)


_V3_SEEDS: Final[tuple[Expression, ...]] = _build_v3_seeds()
_MUTATION_KINDS: Final[tuple[str, ...]] = (
    "point_mutation_field",
    "point_mutation_operator",
    "point_mutation_literal",
    "subtree_replacement",
)
# Bounded retry budget before falling back to a guaranteed-valid operation.
_MAX_EVOLVE_ATTEMPTS: Final[int] = 16


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


# --- AST traversal / rebuild helpers -----------------------------------------
# Every Factor DSL node is a frozen dataclass, so mutation / crossover rebuild
# only the path from the edited position to the root and share unchanged
# subtrees by reference (no deep copy needed).


def _children(node: Expression) -> tuple[Expression, ...]:
    if isinstance(node, factor_dsl.Unary):
        return (node.operand,)
    if isinstance(node, factor_dsl.Binary):
        return (node.left, node.right)
    if isinstance(node, factor_dsl.Call):
        return node.arguments
    return ()


def _all_paths(
    node: Expression, prefix: tuple[int, ...] = ()
) -> Iterator[tuple[tuple[int, ...], Expression]]:
    """Yield ``(path, node)`` for every node; ``path`` is a tuple of child indices."""
    yield prefix, node
    for index, child in enumerate(_children(node)):
        yield from _all_paths(child, prefix + (index,))


def _node_at(node: Expression, path: tuple[int, ...]) -> Expression:
    for index in path:
        node = _children(node)[index]
    return node


def _replace_child(node: Expression, index: int, new_child: Expression) -> Expression:
    if isinstance(node, factor_dsl.Unary):
        return replace(node, operand=new_child)
    if isinstance(node, factor_dsl.Binary):
        return replace(node, left=new_child) if index == 0 else replace(node, right=new_child)
    if isinstance(node, factor_dsl.Call):
        arguments = list(node.arguments)
        arguments[index] = new_child
        return replace(node, arguments=tuple(arguments))
    raise TypeError("expression node has no replaceable children")


def _replace_at(node: Expression, path: tuple[int, ...], new_subtree: Expression) -> Expression:
    """Return a new AST with ``new_subtree`` substituted at ``path``."""
    if not path:
        return new_subtree
    index = path[0]
    rebuilt_child = _replace_at(_children(node)[index], path[1:], new_subtree)
    return _replace_child(node, index, rebuilt_child)


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
        """Produce the next candidate, or ``None`` once the budget is hit.

        The stream is: seed pool (frozen enumeration), then a mutation wave,
        then a crossover wave, each filling the remaining candidate budget.
        Every output is a legal DSL AST re-canonicalized through
        ``factor_dsl.canonicalize`` (the single validator).
        """
        if self._step >= self._max_candidates:
            return None
        result = self._produce(self._step)
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
    def seed(self) -> int:
        """The frozen seed this factory is deterministically driven from."""
        return self._seed

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
        (3) ``rank``/``zscore`` of single fields, (4) v3 time-series seeds
        (core fields x new operators x legal windows — placed before the
        rolling_mean block so the default 256-candidate budget covers the
        full live vocabulary), (5) ``rolling_mean`` variants over a field
        with legal windows, (6) small binary trees over field/field and
        field/literal.  Every emitted node is a legal DSL AST, so each
        canonicalizes without raising.
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
        # (4) v3 时序种子: 全部新算子形态, by-construction 合法
        yield from _V3_SEEDS
        # (5) rolling_mean variants over a field with legal windows
        for name in fields:
            for window in _SEED_ROLLING_WINDOWS:
                yield factor_dsl.Call(
                    "rolling_mean",
                    (factor_dsl.Field(name, _LOC), factor_dsl.Number(float(window), _LOC)),
                    _LOC,
                )
        # (6) small binary trees over field/field and field/literal
        if count >= 2:
            yield factor_dsl.Binary("+", factor_dsl.Field(fields[0], _LOC), factor_dsl.Field(fields[1], _LOC), _LOC)
        if count >= 4:
            yield factor_dsl.Binary("-", factor_dsl.Field(fields[2], _LOC), factor_dsl.Field(fields[3], _LOC), _LOC)
        if count >= 6:
            yield factor_dsl.Binary("*", factor_dsl.Field(fields[4], _LOC), factor_dsl.Field(fields[5], _LOC), _LOC)
        yield factor_dsl.Binary("*", factor_dsl.Field(fields[0], _LOC), factor_dsl.Number(2.0, _LOC), _LOC)
        denom_source = fields[1] if count >= 2 else fields[0]
        yield factor_dsl.Binary("/", factor_dsl.Field(denom_source, _LOC), factor_dsl.Number(100.0, _LOC), _LOC)

    # -- evolution: mutation + crossover --------------------------------

    def _produce(self, step: int) -> GenerationResult:
        """Dispatch one step: seed pool, then mutation wave, then crossover wave.

        After the seed pool the remaining budget is split evenly: the first
        half is mutation, the second half is crossover.  The split depends on
        the frozen budget (part of the spec), so ``replay_to`` preserves the
        budget to reproduce the exact dispatch.
        """
        if step < len(self._seed_pool):
            return self._produce_seed(step)
        # Mutation needs >= 1 parent; crossover needs >= 2 distinct parents.
        if len(self._results) < 2:
            return self._produce_mutation(step)
        remaining = self._max_candidates - len(self._seed_pool)
        mutation_budget = max(0, remaining) // 2
        rel = step - len(self._seed_pool)
        if rel < mutation_budget:
            return self._produce_mutation(step)
        return self._produce_crossover(step)

    def _produce_mutation(self, step: int) -> GenerationResult:
        for _ in range(_MAX_EVOLVE_ATTEMPTS):
            parent_step = self._rng.randrange(len(self._results))
            parent = self._results[parent_step]
            kind = self._rng.choice(_MUTATION_KINDS)
            mutated = self._apply_mutation(parent.ast, kind)
            if mutated is None:
                continue
            try:
                canonical = factor_dsl.canonicalize(mutated)
            except factor_dsl.FactorDslError:
                continue
            return GenerationResult(
                step=step,
                operation=kind,
                ast=mutated,
                canonical_expression=canonical,
                parent_steps=(parent.step,),
                seed=self._seed,
            )
        # Guaranteed-valid fallback: swap one field in a field-bearing parent.
        parent_step, mutated = self._fallback_field_swap()
        canonical = factor_dsl.canonicalize(mutated)
        return GenerationResult(
            step=step,
            operation="point_mutation_field",
            ast=mutated,
            canonical_expression=canonical,
            parent_steps=(self._results[parent_step].step,),
            seed=self._seed,
        )

    def _apply_mutation(self, ast: Expression, kind: str) -> Expression | None:
        if kind == "point_mutation_field":
            return self._mutate_field(ast)
        if kind == "point_mutation_operator":
            return self._mutate_operator(ast)
        if kind == "point_mutation_literal":
            return self._mutate_literal(ast)
        if kind == "subtree_replacement":
            return self._mutate_subtree(ast)
        raise ValueError(f"unknown mutation kind {kind!r}")

    def _mutate_field(self, ast: Expression) -> Expression | None:
        paths = [path for path, node in _all_paths(ast) if isinstance(node, factor_dsl.Field)]
        if not paths:
            return None
        path = self._rng.choice(paths)
        current = _node_at(ast, path)
        others = [name for name in self._fields_sorted if name != current.name]
        if not others:
            return None
        return _replace_at(ast, path, factor_dsl.Field(self._rng.choice(others), _LOC))

    def _mutate_operator(self, ast: Expression) -> Expression | None:
        paths = [path for path, node in _all_paths(ast) if isinstance(node, factor_dsl.Binary)]
        if not paths:
            return None
        path = self._rng.choice(paths)
        current = _node_at(ast, path)
        others = [operator for operator in _BINARY_OPERATORS if operator != current.operator]
        return _replace_at(ast, path, replace(current, operator=self._rng.choice(others)))

    def _mutate_literal(self, ast: Expression) -> Expression | None:
        paths = [path for path, node in _all_paths(ast) if isinstance(node, factor_dsl.Number)]
        if not paths:
            return None
        path = self._rng.choice(paths)
        current = _node_at(ast, path)
        # 分位数参数域 (0,1) 与窗口/clip 域不同: rolling_quantile 第 3 参
        # 只能在 _QUANTILE_LITERALS 里变异, 否则必然非法。
        parent = _node_at(ast, path[:-1]) if len(path) >= 2 else None
        domain = _SAFE_LITERALS
        if (
            isinstance(parent, factor_dsl.Call)
            and parent.name == "rolling_quantile"
            and path[-1] == 2
        ):
            domain = _QUANTILE_LITERALS
        others = [value for value in domain if value != current.value]
        new_value = self._rng.choice(others) if others else self._rng.choice(domain)
        return _replace_at(ast, path, factor_dsl.Number(new_value, _LOC))

    def _mutate_subtree(self, ast: Expression) -> Expression | None:
        paths = [path for path, _ in _all_paths(ast)]
        if not paths:
            return None
        path = self._rng.choice(paths)
        depth = min(self._max_depth, 3)
        return _replace_at(ast, path, self._random_subtree(depth))

    def _fallback_field_swap(self) -> tuple[int, Expression]:
        """Deterministic, PRNG-free guaranteed-valid mutation (rarely reached)."""
        for parent_step in range(len(self._results)):
            ast = self._results[parent_step].ast
            fields = [(path, node) for path, node in _all_paths(ast) if isinstance(node, factor_dsl.Field)]
            if not fields:
                continue
            path, node = fields[0]
            position = self._fields_sorted.index(node.name)
            new_name = self._fields_sorted[(position + 1) % len(self._fields_sorted)]
            return parent_step, _replace_at(ast, path, factor_dsl.Field(new_name, _LOC))
        # The frontier always contains step 0 (a single field); unreachable.
        raise AssertionError("no field-bearing parent in frontier")

    def _produce_crossover(self, step: int) -> GenerationResult:
        for _ in range(_MAX_EVOLVE_ATTEMPTS):
            a = self._rng.randrange(len(self._results))
            b = self._rng.randrange(len(self._results))
            if a == b:
                continue
            parent_a = self._results[a]
            parent_b = self._results[b]
            child = self._graft(parent_a.ast, parent_b.ast)
            if child is None:
                continue
            try:
                canonical = factor_dsl.canonicalize(child)
            except factor_dsl.FactorDslError:
                continue
            return GenerationResult(
                step=step,
                operation="crossover",
                ast=child,
                canonical_expression=canonical,
                parent_steps=(parent_a.step, parent_b.step),
                seed=self._seed,
            )
        # Guaranteed-valid fallback: graft a field from parent 1 into parent 0.
        a, b, child = self._fallback_graft()
        canonical = factor_dsl.canonicalize(child)
        return GenerationResult(
            step=step,
            operation="crossover",
            ast=child,
            canonical_expression=canonical,
            parent_steps=(self._results[a].step, self._results[b].step),
            seed=self._seed,
        )

    def _graft(self, ast_a: Expression, ast_b: Expression) -> Expression | None:
        a_paths = [path for path, _ in _all_paths(ast_a)]
        b_nodes = [node for _, node in _all_paths(ast_b)]
        if not a_paths or not b_nodes:
            return None
        a_path = self._rng.choice(a_paths)
        b_node = self._rng.choice(b_nodes)
        # Immutable nodes: sharing B's subtree by reference is safe.
        return _replace_at(ast_a, a_path, b_node)

    def _fallback_graft(self) -> tuple[int, int, Expression]:
        """Deterministic, PRNG-free guaranteed-valid crossover (rarely reached)."""
        a, b = 0, 1
        b_fields = [node for _, node in _all_paths(self._results[b].ast) if isinstance(node, factor_dsl.Field)]
        graft = b_fields[0] if b_fields else factor_dsl.Field(self._fields_sorted[0], _LOC)
        return a, b, graft

    def _random_subtree(self, depth: int) -> Expression:
        """Build a bounded random legal subtree; re-canonicalized by the caller."""
        if depth <= 0:
            if self._rng.random() < 0.75:
                return factor_dsl.Field(self._rng.choice(self._fields_sorted), _LOC)
            return factor_dsl.Number(self._rng.choice(_SAFE_LITERALS), _LOC)
        roll = self._rng.random()
        if roll < 0.4:
            return factor_dsl.Field(self._rng.choice(self._fields_sorted), _LOC)
        if roll < 0.5:
            return factor_dsl.Number(self._rng.choice(_SAFE_LITERALS), _LOC)
        if roll < 0.6:
            return factor_dsl.Unary("-", self._random_subtree(depth - 1), _LOC)
        if roll < 0.85:
            operator = self._rng.choice(_BINARY_OPERATORS)
            return factor_dsl.Binary(
                operator, self._random_subtree(depth - 1), self._random_subtree(depth - 1), _LOC
            )
        return self._random_call(self._rng.choice(_FUNCTION_CHOICES), depth)

    def _random_call(self, name: str, depth: int) -> Expression:
        if name in ("abs", "sign", "log1p", "rank", "zscore"):
            return factor_dsl.Call(name, (self._random_subtree(depth - 1),), _LOC)
        if name in ("rolling_mean", *_V3_WINDOWED_UNARY):
            # 窗口字面量取自 _SEED_ROLLING_WINDOWS, 全部在合法窗口区。
            window = float(self._rng.choice(_SEED_ROLLING_WINDOWS))
            return factor_dsl.Call(
                name,
                (self._random_subtree(depth - 1), factor_dsl.Number(window, _LOC)),
                _LOC,
            )
        if name == "rolling_quantile":
            window = float(self._rng.choice(_SEED_ROLLING_WINDOWS))
            quantile = self._rng.choice(_QUANTILE_LITERALS)
            return factor_dsl.Call(
                "rolling_quantile",
                (self._random_subtree(depth - 1), factor_dsl.Number(window, _LOC),
                 factor_dsl.Number(quantile, _LOC)),
                _LOC,
            )
        if name == "rolling_corr":
            window = float(self._rng.choice(_SEED_ROLLING_WINDOWS))
            return factor_dsl.Call(
                "rolling_corr",
                (self._random_subtree(depth - 1), self._random_subtree(depth - 1),
                 factor_dsl.Number(window, _LOC)),
                _LOC,
            )
        if name in ("max", "min"):
            # 逐点二元: 无窗口参数。
            return factor_dsl.Call(
                name,
                (self._random_subtree(depth - 1), self._random_subtree(depth - 1)),
                _LOC,
            )
        # clip(expr, low, high) with low <= high by construction.
        low = self._rng.choice(_SAFE_LITERALS)
        highs = [value for value in _SAFE_LITERALS if value >= low]
        high = self._rng.choice(highs) if highs else low
        return factor_dsl.Call(
            "clip",
            (self._random_subtree(depth - 1), factor_dsl.Number(low, _LOC), factor_dsl.Number(high, _LOC)),
            _LOC,
        )



# ---------------------------------------------------------------------------
# Phase 46 Wave 3 (AF-REQ-03 SC3): validate-before-evaluate boundary
# ---------------------------------------------------------------------------
#
# Every candidate AST must pass through the existing factor_dsl parse /
# canonicalize boundary before it can enter the candidate ledger (T-46-07).
# This is the single validation surface plan 46-04's worker loop consumes; it
# reuses parse_factor / canonicalize / extract_features with no second parser,
# evaluator, or provider (D-01, D-08).  The complexity limits (depth and node
# count) are the one rejection mode the DSL validator does not raise on its own
# (research §4), so measure_complexity enforces them here.


def measure_complexity(ast: Expression) -> tuple[int, int]:
    """Return ``(depth, node_count)`` for ``ast`` by a pure structural walk.

    No validation and no Polars: this counts AST nodes and nesting depth so the
    complexity budget can reject over-deep / over-wide expressions that the DSL
    validator does not enforce on its own (research §4).  Leaves have depth 1;
    the root path ``()`` has length 0, so depth is one greater than the longest
    child path.  The AST is never mutated or re-validated.
    """
    paths = list(_all_paths(ast))
    node_count = len(paths)
    depth = (max((len(path) for path, _ in paths), default=0)) + 1
    return depth, node_count


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of ``validate_candidate``: valid, or an explicit invalid record.

    ``reason`` is empty for valid results and carries a structured diagnostic
    payload (``diagnostic`` / ``location`` / ``dsl_version`` / ``vocab_version`` /
    ``raw_expression``) for invalid results; the worker loop persists it verbatim
    as the candidate attempt's ``reason_json`` column.
    """

    status: Literal["valid", "invalid"]
    canonical_expression: str
    features: FactorFeatures | None
    reason: Mapping[str, Any]


def invalid_reason(
    error: factor_dsl.FactorDslError, raw_expression: str, vocab_version: str
) -> dict[str, Any]:
    """Build the structured diagnostic payload for a DSL-rejected expression.

    Maps directly to the ``reason_json`` column (research §4).  The rejected raw
    expression is intentional provenance for an explicit invalid record, not a
    principal/secret/path leak (T-46-08).
    """
    return {
        "diagnostic": str(error.diagnostic.message),
        "location": error.diagnostic.location.display(),
        "dsl_version": factor_dsl.DSL_VERSION,
        "vocab_version": vocab_version,
        "raw_expression": raw_expression,
    }


def _dimension_exceeded_reason(
    *,
    measured_name: str,
    measured: int,
    limit_name: str,
    limit: int,
    raw_expression: str,
    vocab_version: str,
) -> dict[str, Any]:
    """Complexity diagnostic for an AST depth/node count over the frozen limit.

    The DSL validator does not enforce depth or node counts, so this is the one
    rejection mode raised here rather than by factor_dsl (research §4).
    """
    return {
        "diagnostic": f"expression {measured_name} {measured} exceeds {limit_name} {limit}",
        "location": f"{measured_name} {measured}",
        "dsl_version": factor_dsl.DSL_VERSION,
        "vocab_version": vocab_version,
        "raw_expression": raw_expression,
    }


def validate_candidate(
    ast: Expression, *, max_depth: int, max_nodes: int
) -> ValidationResult:
    """Validate ``ast`` through the Factor DSL before it can enter the ledger.

    Complexity is the gate: depth/node count over the frozen limits is rejected
    first (AF-REQ-03), since the DSL validator does not enforce those.  Surviving
    expressions are canonicalized (which validates semantics) and then re-parsed
    through ``parse_factor`` so the canonical form round-trips through the single
    text entry point -- there is no second expression engine (D-01, D-08).

    Invalid candidates are never suppressed (T-46-09): they are explicit records
    the worker loop persists with ``status="invalid"``, consuming the declared
    budget.
    """
    vocab_version = vocabulary_fingerprint()
    depth, nodes = measure_complexity(ast)
    if depth > max_depth:
        return ValidationResult(
            status="invalid",
            canonical_expression="",
            features=None,
            reason=_dimension_exceeded_reason(
                measured_name="depth",
                measured=depth,
                limit_name="max_depth",
                limit=max_depth,
                raw_expression="",
                vocab_version=vocab_version,
            ),
        )
    if nodes > max_nodes:
        return ValidationResult(
            status="invalid",
            canonical_expression="",
            features=None,
            reason=_dimension_exceeded_reason(
                measured_name="nodes",
                measured=nodes,
                limit_name="max_nodes",
                limit=max_nodes,
                raw_expression="",
                vocab_version=vocab_version,
            ),
        )
    try:
        canonical_expression = factor_dsl.canonicalize(ast)
    except factor_dsl.FactorDslError as error:
        return ValidationResult(
            status="invalid",
            canonical_expression="",
            features=None,
            reason=invalid_reason(error, "", vocab_version),
        )
    # Re-parse the canonical text through the single text entry point so there is
    # no second expression engine (D-01): the canonical form must round-trip.
    try:
        parsed = factor_dsl.parse_factor(canonical_expression)
    except factor_dsl.FactorDslError as error:
        return ValidationResult(
            status="invalid",
            canonical_expression=canonical_expression,
            features=None,
            reason=invalid_reason(error, canonical_expression, vocab_version),
        )
    return ValidationResult(
        status="valid",
        canonical_expression=parsed.canonical_expression,
        features=parsed.features,
        reason={},
    )


def validate_expression_text(
    source: str, *, max_depth: int, max_nodes: int
) -> ValidationResult:
    """Validate arbitrary source text for the per-mode AF-REQ-03 tests.

    Parses ``source`` via ``parse_factor`` (the single text entry point) and
    returns ``invalid`` through the same ``invalid_reason`` path on
    ``FactorDslError``, with complexity measured on the parsed AST.  Plan 46-04's
    worker loop drives ``validate_candidate`` on ASTs; this helper exists so the
    rejection modes can be exercised from readable expression text.
    """
    vocab_version = vocabulary_fingerprint()
    try:
        parsed = factor_dsl.parse_factor(source)
    except factor_dsl.FactorDslError as error:
        return ValidationResult(
            status="invalid",
            canonical_expression=source,
            features=None,
            reason=invalid_reason(error, source, vocab_version),
        )
    depth, nodes = measure_complexity(parsed.expression)
    if depth > max_depth:
        return ValidationResult(
            status="invalid",
            canonical_expression=parsed.canonical_expression,
            features=None,
            reason=_dimension_exceeded_reason(
                measured_name="depth",
                measured=depth,
                limit_name="max_depth",
                limit=max_depth,
                raw_expression=parsed.canonical_expression,
                vocab_version=vocab_version,
            ),
        )
    if nodes > max_nodes:
        return ValidationResult(
            status="invalid",
            canonical_expression=parsed.canonical_expression,
            features=None,
            reason=_dimension_exceeded_reason(
                measured_name="nodes",
                measured=nodes,
                limit_name="max_nodes",
                limit=max_nodes,
                raw_expression=parsed.canonical_expression,
                vocab_version=vocab_version,
            ),
        )
    return ValidationResult(
        status="valid",
        canonical_expression=parsed.canonical_expression,
        features=parsed.features,
        reason={},
    )


# ---------------------------------------------------------------------------
# Phase 46 Wave 3 (AF-REQ-19 SC4): structural diversity without silent merging
# ---------------------------------------------------------------------------
#
# Diversity is *recorded beside* each candidate — it is never used to silently
# merge or drop similar expressions (research Pitfall 3).  Exact structural
# duplicates get a ``duplicate`` status but remain one-row-per-attempt; a valid
# novel candidate gets ``generated``.  IC-series correlation requires evaluation
# and is Phase 47's responsibility, so it is never computed here (D-01, D-08).

ALPHA_GENERATION_STATUSES: Final[tuple[str, ...]] = (
    "invalid", "duplicate", "generated", "budget_exhausted",
)


def diversity_summary(
    candidate_features: FactorFeatures,
    population_features: Sequence[FactorFeatures],
) -> dict[str, Any]:
    """Record the structural diversity of a candidate against the run population.

    For the new candidate against the already-produced population of the same
    run, reports the maximum Jaccard field overlap, maximum operator/function
    overlap, whether any exact AST-signature duplicate exists, and whether any
    shape-signature match exists — reusing :func:`factor_registry._jaccard` so
    there is one similarity definition (research §5).

    The ``most_similar_step`` is the 0-based step index of the highest-scoring
    population member (exact > shape > field/operator overlap), or ``None`` when
    the population is empty.  Nothing is merged or dropped.
    """
    field_overlap = 0.0
    operator_function_overlap = 0.0
    exact_structural_match = False
    shape_match = False
    most_similar_step: int | None = None
    best_score = -1.0
    for step, other in enumerate(population_features):
        fo = _jaccard(candidate_features.fields, other.fields)
        ofo = _jaccard(candidate_features.operator_function_set, other.operator_function_set)
        exact = candidate_features.structural_signature == other.structural_signature
        shape = candidate_features.shape_signature == other.shape_signature
        if fo > field_overlap:
            field_overlap = fo
        if ofo > operator_function_overlap:
            operator_function_overlap = ofo
        if exact:
            exact_structural_match = True
        if shape:
            shape_match = True
        score = (1.0 if exact else 0.0) + (0.5 if shape else 0.0) + 0.25 * (fo + ofo)
        if score > best_score:
            best_score = score
            most_similar_step = step
    return {
        "field_overlap": field_overlap,
        "operator_function_overlap": operator_function_overlap,
        "exact_structural_match": exact_structural_match,
        "shape_match": shape_match,
        "most_similar_step": most_similar_step,
        "population_size": len(population_features),
    }


def classify_candidate(
    validation: ValidationResult, diversity: Mapping[str, Any]
) -> str:
    """Classify one candidate into its Phase-46 generation status.

    * ``invalid`` — the candidate failed validation (AF-REQ-03).
    * ``duplicate`` — an exact structural signature match exists in the
      population; the candidate is retained as its own attempt row, never
      silently merged or dropped (AF-REQ-19 / research Pitfall 3).
    * ``generated`` — a valid novel candidate pending Phase-47 evaluation.

    No IC-series correlation, coverage, or admission verdict is computed — those
    are Phase 47's responsibility (open-question O4).
    """
    if validation.status == "invalid":
        return "invalid"
    if diversity.get("exact_structural_match"):
        return "duplicate"
    return "generated"


# ---------------------------------------------------------------------------
# Phase 46 Wave 3 (AF-REQ-23 SC4): server-side budget guard + driver loop
# ---------------------------------------------------------------------------
#
# Candidate-count, expression-count, wall-clock, and (structural) memory budgets
# are enforced server-side at the top of every step.  Exhausting any budget is a
# *normal* terminal — the run transitions to ``completed`` (never ``failed``)
# with a ``terminal_reason`` naming the exhausted budget (research §6).  The
# loop persists one candidate per step through the token-fenced worker adapter;
# parallelism cannot change order, winner, or replay (T-46-11, T-46-12).


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    """Frozen budget envelope parsed from the run manifest (research §6).

    ``max_candidates`` is the hard candidate-count ceiling.  ``max_expressions``
    caps the unique-expression frontier (``None`` = unbounded).
    ``max_wallclock_seconds`` caps wall-clock via ``time.monotonic()`` (``None``
    = unbounded).  ``max_depth``/``max_nodes`` bound memory structurally (O1).
    """

    max_candidates: int
    max_expressions: int | None
    max_wallclock_seconds: float | None
    max_depth: int
    max_nodes: int

    @classmethod
    def from_manifest(cls, manifest: Mapping[str, Any]) -> "BudgetLimits":
        """Parse the frozen budget envelope from a D-04 manifest."""
        budgets = manifest.get("budgets") if isinstance(manifest, Mapping) else None
        if not isinstance(budgets, Mapping):
            raise ValueError("manifest budgets group is required")
        max_candidates = budgets.get("max_candidates")
        if type(max_candidates) is not int or max_candidates < 1:
            raise ValueError("budgets.max_candidates must be a positive integer")
        max_expressions = budgets.get("max_expressions")
        if max_expressions is not None and (
            type(max_expressions) is not int or max_expressions < 1
        ):
            raise ValueError("budgets.max_expressions must be a positive integer or null")
        max_wallclock = budgets.get("max_wallclock_seconds")
        if max_wallclock is not None and (
            type(max_wallclock) not in (int, float) or max_wallclock <= 0
        ):
            raise ValueError("budgets.max_wallclock_seconds must be a positive number or null")
        max_depth = DEFAULT_MAX_DEPTH
        max_nodes = DEFAULT_MAX_NODES
        grammar = manifest.get("grammar")
        if isinstance(grammar, Mapping):
            gd = grammar.get("max_depth")
            if gd is not None:
                if type(gd) is not int or gd < 1:
                    raise ValueError("grammar.max_depth must be a positive integer")
                max_depth = gd
            gn = grammar.get("max_nodes")
            if gn is not None:
                if type(gn) is not int or gn < 1:
                    raise ValueError("grammar.max_nodes must be a positive integer")
                max_nodes = gn
        return cls(
            max_candidates=max_candidates,
            max_expressions=max_expressions,
            max_wallclock_seconds=float(max_wallclock) if max_wallclock is not None else None,
            max_depth=max_depth,
            max_nodes=max_nodes,
        )


class BudgetGuard:
    """Server-side budget enforcement checked at the top of each step.

    The guard is checked *before* generating each candidate (research Pitfall 4)
    so a worker can never run past a budget.  Exhaustion returns the budget
    name; the driver loop records a ``budget_exhausted`` candidate and requests
    a normal ``completed`` terminal.
    """

    def __init__(
        self, limits: BudgetLimits, *, monotonic: Callable[[], float] = time.monotonic
    ) -> None:
        self._limits = limits
        self._monotonic = monotonic
        self._start = monotonic()
        self._unique_expressions: set[str] = set()

    @property
    def limits(self) -> BudgetLimits:
        return self._limits

    @property
    def unique_expression_count(self) -> int:
        return len(self._unique_expressions)

    def record_expression(self, canonical_expression: str) -> None:
        """Track one unique canonical expression against the expression budget."""
        self._unique_expressions.add(canonical_expression)

    def exhausted(self, *, candidates: int) -> str | None:
        """Return the name of the first exhausted budget, or ``None``.

        Checked at the TOP of each step before generating.  Candidate-count is
        first (the primary ceiling); wall-clock second; expression-count third.
        Memory is bounded structurally by depth/node limits + the bounded
        candidate frontier (no runtime check, research §6).
        """
        if candidates >= self._limits.max_candidates:
            return "candidate_count"
        if self._limits.max_wallclock_seconds is not None:
            if self._monotonic() - self._start >= self._limits.max_wallclock_seconds:
                return "wallclock"
        if (
            self._limits.max_expressions is not None
            and len(self._unique_expressions) >= self._limits.max_expressions
        ):
            return "expression_count"
        return None

    @staticmethod
    def terminal_reason(budget_name: str) -> str:
        return f"{budget_name}_budget_exhausted"


def _empty_diversity(population_size: int) -> dict[str, Any]:
    """Diversity summary for a candidate whose features cannot be extracted."""
    return {
        "field_overlap": 0.0,
        "operator_function_overlap": 0.0,
        "exact_structural_match": False,
        "shape_match": False,
        "most_similar_step": None,
        "population_size": population_size,
    }


def drive_alpha_generation(
    factory: AlphaFactory,
    *,
    limits: BudgetLimits,
    adapter: Any,
    run_id: str,
    attempt_token: str,
    expected_version: int,
    _monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Drive the deterministic factory through the token-fenced worker adapter.

    Runs one candidate per step: generate → validate → record diversity →
    persist via the token-fenced adapter (candidate + lineage + progress) →
    repeat until a budget is exhausted.  Each candidate — invalid, duplicate,
    generated — is retained as its own attempt row.  Budget exhaustion records a
    final ``budget_exhausted`` candidate and requests a normal ``completed``
    transition (never ``failed``) with a ``terminal_reason`` naming the budget.

    ``adapter`` is a structural sink exposing ``append_candidate``,
    ``append_candidate_lineage``, ``report_progress``, and
    ``request_transition`` (the Phase 45 worker adapter contract).  This module
    never imports the adapter's concrete type, so no evaluation/provider/
    admission/broker authority leaks in (T-46-14).

    Returns a summary dict with ``candidates_produced``, ``terminal_reason``,
    ``unique_expression_count``, and ``population_size``.
    """
    guard = BudgetGuard(limits, monotonic=_monotonic)
    population: list[FactorFeatures] = []
    produced: list[tuple[GenerationResult, str]] = []
    terminal_reason = BudgetGuard.terminal_reason("candidate_count")
    # update_progress increments transition_version on every call, so the
    # driver tracks the live version for all subsequent token-fenced callbacks
    # (append_candidate / append_candidate_lineage / request_transition).
    version = expected_version

    def _report_progress(completed: int) -> None:
        nonlocal version
        result = adapter.report_progress(
            run_id=run_id, expected_version=version,
            attempt_token=attempt_token,
            candidate_attempts_total=limits.max_candidates,
            candidate_attempts_completed=completed,
        )
        if result is not None:
            version = int(result["transition_version"])

    while True:
        budget_name = guard.exhausted(candidates=len(produced))
        if budget_name is not None:
            terminal_reason = BudgetGuard.terminal_reason(budget_name)
            if budget_name != "candidate_count":
                marker_ordinal = len(produced) + 1
                adapter.append_candidate(
                    run_id=run_id, expected_version=version,
                    attempt_token=attempt_token,
                    candidate_id=f"acand_budget_{run_id}",
                    attempt_ordinal=marker_ordinal,
                    candidate_digest=digest_bytes(
                        {"run_id": run_id, "budget": budget_name,
                         "step": factory.step, "seed": factory.seed}
                    ),
                    canonical_expression="",
                    ast_signature="",
                    shape_signature="",
                    dsl_version=factor_dsl.DSL_VERSION,
                    operation="budget_exhausted",
                    seed=factory.seed,
                    step=factory.step,
                    status="budget_exhausted",
                    reason={"budget": budget_name, "terminal_reason": terminal_reason},
                )
                _report_progress(marker_ordinal)
            break

        result = factory.generate_next()
        if result is None:
            break

        validation = validate_candidate(
            result.ast, max_depth=limits.max_depth, max_nodes=limits.max_nodes
        )
        features = validation.features
        if features is None:
            # Complexity-invalid: the AST is valid DSL, just too complex, so
            # features can be extracted for signatures (no depth/node gate).
            try:
                features = factor_dsl.extract_features(result.ast)
            except factor_dsl.FactorDslError:
                features = None

        if features is not None:
            diversity = diversity_summary(features, population)
        else:
            diversity = _empty_diversity(len(population))

        status = classify_candidate(validation, diversity)
        if validation.status == "valid":
            guard.record_expression(result.canonical_expression)

        candidate_id = f"acand_{run_id}_{result.digest}"
        if validation.status == "invalid":
            reason: dict[str, Any] = dict(validation.reason)
        else:
            reason = {"diversity": diversity}
        canonical_expr = validation.canonical_expression or result.canonical_expression
        ast_sig = features.structural_signature if features is not None else result.digest
        shape_sig = features.shape_signature if features is not None else result.digest

        adapter.append_candidate(
            run_id=run_id, expected_version=version,
            attempt_token=attempt_token,
            candidate_id=candidate_id, attempt_ordinal=result.attempt_ordinal,
            candidate_digest=result.digest, canonical_expression=canonical_expr,
            ast_signature=ast_sig, shape_signature=shape_sig,
            dsl_version=factor_dsl.DSL_VERSION, operation=result.operation,
            seed=result.seed, step=result.step, status=status, reason=reason,
        )

        for edge_ordinal, parent_step in enumerate(result.parent_steps):
            adapter.append_candidate_lineage(
                run_id=run_id, expected_version=version,
                attempt_token=attempt_token,
                lineage_id=f"alin_{run_id}_{result.digest}_{edge_ordinal}",
                child_attempt_id=candidate_id,
                parent_attempt_id=produced[parent_step][1],
                edge_ordinal=edge_ordinal, operation=result.operation,
            )

        _report_progress(result.attempt_ordinal)

        if features is not None:
            population.append(features)
        produced.append((result, candidate_id))

    adapter.request_transition(
        run_id=run_id, expected_version=version,
        attempt_token=attempt_token,
        to_status="completed", terminal_reason=terminal_reason,
    )
    return {
        "candidates_produced": len(produced),
        "terminal_reason": terminal_reason,
        "unique_expression_count": guard.unique_expression_count,
        "population_size": len(population),
    }