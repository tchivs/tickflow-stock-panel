"""Phase 46-01: versioned vocabulary + grammar fingerprint authority.

Wave 1 establishes the deterministic grammar/vocabulary fingerprint that every
downstream plan anchors on (AF-REQ-02 SC1): a stable SHA-256 over the complete
restricted Factor DSL vocabulary and the expression-space structural constraints,
server-owned manifest fingerprint population at freeze time, and fail-closed
verification when a stored run's vocabulary no longer matches the live DSL.

The fingerprint is computed from the *live* ``factor_dsl`` module, so the digest
tracks the real grammar (the live ALLOWED_FIELDS has 46 entries, not the 44 the
early narrative cited — plan-check W1).
"""
from __future__ import annotations

import inspect
import re

import pytest

from app.research import alpha_factory, factor_dsl
from app.research.alpha_factory import (
    CANONICAL_FORM,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_NODES,
    FACTORY_VERSION,
    PRNG_ALGORITHM,
    VocabularyMismatchError,
    grammar_fingerprint,
    normalize_manifest_fingerprints,
    verify_vocabulary_fingerprint,
    vocabulary_fingerprint,
)
from app.research.run_contract import digest_bytes, freeze_input_snapshot
from app.research.alpha_factory import AlphaFactory, GenerationResult, candidate_digest
from app.research.alpha_factory import (
    ValidationResult,
    invalid_reason,
    measure_complexity,
    validate_candidate,
    validate_expression_text,
)

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


# ================================================================
# Task 46-01-01: versioned vocabulary + grammar fingerprint
# ================================================================


class TestVersioningConstants:
    def test_factory_version_is_pinned(self) -> None:
        assert FACTORY_VERSION == "alpha-factory-v1"

    def test_prng_algorithm_is_pinned_for_cross_process_replay(self) -> None:
        # Pins the replay PRNG contract consumed by plan 46-02.
        assert PRNG_ALGORITHM == "python-random-MT19937-v1"

    def test_canonical_form_is_pinned(self) -> None:
        assert CANONICAL_FORM == "factor-dsl-canonical-v1"

    def test_default_complexity_limits_are_pinned(self) -> None:
        assert DEFAULT_MAX_DEPTH == 6
        assert DEFAULT_MAX_NODES == 40


class TestVocabularyFingerprint:
    def test_is_stable_lowercase_64_hex(self) -> None:
        first = vocabulary_fingerprint()
        second = vocabulary_fingerprint()
        assert first == second
        assert _HEX64.fullmatch(first)

    def test_equals_direct_digest_of_live_dsl_constants(self) -> None:
        # Proves any field/operator/arity/partition/window change alters the
        # digest, because the fingerprint is exactly digest_bytes over the live
        # DSL constants in a fixed canonical shape.
        expected = digest_bytes({
            "dsl_version": factor_dsl.DSL_VERSION,
            "fields": sorted(factor_dsl.ALLOWED_FIELDS),
            "denied_fields": sorted(factor_dsl.DENIED_FIELDS),
            "binary_operators": ["+", "-", "*", "/"],
            "unary_operators": ["-"],
            "functions": dict(sorted(factor_dsl._FUNCTION_ARITY.items())),
            "partition_semantics": dict(sorted(factor_dsl._FUNCTION_PARTITION.items())),
            "max_rolling_window": factor_dsl.MAX_ROLLING_WINDOW,
        })
        assert vocabulary_fingerprint() == expected

    def test_covers_the_full_live_vocabulary(self) -> None:
        # The live ALLOWED_FIELDS has 46 entries (plan-check W1 corrected the
        # early "44" narrative); the fingerprint reads the live module so it
        # tracks the real grammar rather than a hardcoded count.
        assert len(factor_dsl.ALLOWED_FIELDS) == 46
        assert len(factor_dsl.DENIED_FIELDS) == 8
        assert len(factor_dsl._FUNCTION_ARITY) == 7
        # The grammar is self-consistent by construction.
        assert set(factor_dsl._FUNCTION_ARITY) == set(factor_dsl._FUNCTION_PARTITION)

    def test_is_sensitive_to_field_addition(self) -> None:
        altered = digest_bytes({
            "dsl_version": factor_dsl.DSL_VERSION,
            "fields": sorted(factor_dsl.ALLOWED_FIELDS | {"synthetic_field"}),
            "denied_fields": sorted(factor_dsl.DENIED_FIELDS),
            "binary_operators": ["+", "-", "*", "/"],
            "unary_operators": ["-"],
            "functions": dict(sorted(factor_dsl._FUNCTION_ARITY.items())),
            "partition_semantics": dict(sorted(factor_dsl._FUNCTION_PARTITION.items())),
            "max_rolling_window": factor_dsl.MAX_ROLLING_WINDOW,
        })
        assert altered != vocabulary_fingerprint()

    def test_is_sensitive_to_arity_change(self) -> None:
        functions = {**factor_dsl._FUNCTION_ARITY, "rank": 2}  # arity drift
        altered = digest_bytes({
            "dsl_version": factor_dsl.DSL_VERSION,
            "fields": sorted(factor_dsl.ALLOWED_FIELDS),
            "denied_fields": sorted(factor_dsl.DENIED_FIELDS),
            "binary_operators": ["+", "-", "*", "/"],
            "unary_operators": ["-"],
            "functions": dict(sorted(functions.items())),
            "partition_semantics": dict(sorted(factor_dsl._FUNCTION_PARTITION.items())),
            "max_rolling_window": factor_dsl.MAX_ROLLING_WINDOW,
        })
        assert altered != vocabulary_fingerprint()


class TestGrammarFingerprint:
    def test_is_stable_for_identical_inputs(self) -> None:
        assert grammar_fingerprint(max_depth=6, max_nodes=40) == grammar_fingerprint(max_depth=6, max_nodes=40)

    def test_uses_defaults_when_omitted(self) -> None:
        assert grammar_fingerprint() == grammar_fingerprint(
            max_depth=DEFAULT_MAX_DEPTH, max_nodes=DEFAULT_MAX_NODES
        )

    def test_differs_when_max_depth_changes(self) -> None:
        baseline = grammar_fingerprint(max_depth=6, max_nodes=40)
        assert baseline != grammar_fingerprint(max_depth=8, max_nodes=40)

    def test_differs_when_max_nodes_changes(self) -> None:
        baseline = grammar_fingerprint(max_depth=6, max_nodes=40)
        assert baseline != grammar_fingerprint(max_depth=6, max_nodes=60)

    def test_is_lowercase_64_hex(self) -> None:
        assert _HEX64.fullmatch(grammar_fingerprint())

    def test_differs_from_vocabulary_fingerprint(self) -> None:
        # Grammar and vocabulary are distinct authorities over distinct inputs.
        assert grammar_fingerprint() != vocabulary_fingerprint()


class TestImportDiscipline:
    def test_imports_only_factor_dsl_and_run_contract(self) -> None:
        """alpha_factory holds no evaluation/provider/admission/broker authority."""
        source = inspect.getsource(alpha_factory)
        import_lines = [
            line.strip()
            for line in source.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        forbidden = (
            "broker", "order", "portfolio", "execution", "monitor", "provider",
            "promote", "evaluator", "admission", "run_service", "run_worker",
            "factor_registry", "repository", "polars",
        )
        for line in import_lines:
            for module in forbidden:
                assert module not in line, (
                    f"alpha_factory must not import authority module '{module}': {line}"
                )
        assert any("factor_dsl" in line for line in import_lines)
        assert any("run_contract" in line for line in import_lines)



def _sample_manifest(*, seed: int = 42, universe: str = "cn-a-share") -> dict:
    """A complete D-04 manifest mirroring the Phase 45 contract helper.

    Carries placeholder ``"a"*64`` / ``"b"*64`` fingerprint slots that the
    server-owned normalization must overwrite at freeze time.
    """
    return {
        "dsl": {"version": "factor-dsl-v1"},
        "grammar": {"fingerprint": "a" * 64, "version": "grammar-v1"},
        "vocabulary": {"fingerprint": "b" * 64, "size": 64},
        "policy": {"version": "admission-v1", "thresholds": {"min_ic": 0.02}},
        "budgets": {"max_expressions": 1000, "max_candidates": 200},
        "objective": {"name": "sharpe", "direction": "maximize"},
        "universe": {"name": universe, "asset_type": "stock", "membership_fingerprint": "c" * 64},
        "measured_window": {"start": "2020-01-01", "end": "2023-12-31", "calendar": "SSE"},
        "fold_geometry": {"train_size": 120, "gap_size": 5, "test_size": 20, "n_folds": 10},
        "code_manifest": {
            "fingerprint": "d" * 64,
            "build_fingerprint": "e" * 64,
            "dependency_fingerprint": "f" * 64,
        },
        "data_manifest": {
            "fingerprint": "g" * 64,
            "partition_fingerprint": "h" * 64,
        },
        "seed": seed,
    }


# ================================================================
# Task 46-01-02: server-owned manifest fingerprints + fail-closed verify
# ================================================================


class TestNormalizeManifestFingerprints:
    def test_overwrites_placeholder_with_server_owned_digests(self) -> None:
        manifest = {
            "grammar": {"fingerprint": "a" * 64, "version": "grammar-v1"},
            "vocabulary": {"fingerprint": "b" * 64, "size": 64},
        }
        normalized = normalize_manifest_fingerprints(manifest)
        assert normalized["grammar"]["fingerprint"] == grammar_fingerprint()
        assert normalized["vocabulary"]["fingerprint"] == vocabulary_fingerprint()
        # Every other key is preserved.
        assert normalized["grammar"]["version"] == "grammar-v1"
        assert normalized["vocabulary"]["size"] == 64

    def test_does_not_mutate_caller_mapping(self) -> None:
        manifest = {
            "grammar": {"fingerprint": "a" * 64, "version": "grammar-v1"},
            "vocabulary": {"fingerprint": "b" * 64, "size": 64},
        }
        normalize_manifest_fingerprints(manifest)
        assert manifest["grammar"]["fingerprint"] == "a" * 64
        assert manifest["grammar"]["version"] == "grammar-v1"
        assert manifest["vocabulary"]["fingerprint"] == "b" * 64
        assert manifest["vocabulary"]["size"] == 64

    def test_uses_declared_complexity_limits_when_present(self) -> None:
        manifest = {
            "grammar": {"fingerprint": "a" * 64, "max_depth": 8, "max_nodes": 60},
            "vocabulary": {"fingerprint": "b" * 64},
        }
        normalized = normalize_manifest_fingerprints(manifest)
        assert normalized["grammar"]["fingerprint"] == grammar_fingerprint(max_depth=8, max_nodes=60)
        # Declared limits differ from the defaults, so the digest differs too.
        assert normalized["grammar"]["fingerprint"] != grammar_fingerprint()
        # The declared sub-keys are preserved alongside the server-owned digest.
        assert normalized["grammar"]["max_depth"] == 8
        assert normalized["grammar"]["max_nodes"] == 60


class TestFreezePopulatesServerOwnedFingerprints:
    def test_freeze_overwrites_placeholder_fingerprint_columns(self) -> None:
        # A manifest carrying placeholder "a"*64 / "b"*64 yields server-owned
        # digest columns after freeze.
        snap = freeze_input_snapshot(
            manifest=_sample_manifest(), created_at="2026-08-08T00:00:00+00:00"
        )
        assert snap.manifest["grammar"]["fingerprint"] == grammar_fingerprint()
        assert snap.manifest["vocabulary"]["fingerprint"] == vocabulary_fingerprint()
        # Component digests wrap the fingerprint key (matches _component_digest).
        assert snap.component_digests["grammar"] == digest_bytes(
            {"fingerprint": grammar_fingerprint()}
        )
        assert snap.component_digests["vocabulary"] == digest_bytes(
            {"fingerprint": vocabulary_fingerprint()}
        )

    def test_freeze_fingerprints_deterministic_across_refreeze(self) -> None:
        manifest = _sample_manifest()
        now = "2026-08-08T00:00:00+00:00"
        snap_a = freeze_input_snapshot(manifest=manifest, created_at=now)
        snap_b = freeze_input_snapshot(manifest=manifest, created_at=now)
        assert snap_a.manifest_sha256 == snap_b.manifest_sha256
        assert snap_a.snapshot_sha256 == snap_b.snapshot_sha256
        assert snap_a.component_digests == snap_b.component_digests

    def test_freeze_overrides_forged_client_supplied_fingerprint(self) -> None:
        forged = _sample_manifest()
        forged["grammar"]["fingerprint"] = "0" * 64
        forged["vocabulary"]["fingerprint"] = "1" * 64
        snap = freeze_input_snapshot(manifest=forged, created_at="2026-08-08T00:00:00+00:00")
        assert snap.manifest["grammar"]["fingerprint"] == grammar_fingerprint()
        assert snap.manifest["vocabulary"]["fingerprint"] == vocabulary_fingerprint()
        # The caller's manifest is not mutated by freeze.
        assert forged["grammar"]["fingerprint"] == "0" * 64
        assert forged["vocabulary"]["fingerprint"] == "1" * 64

    def test_changed_seed_still_mints_distinct_snapshot(self) -> None:
        # Normalization is seed-independent, so distinct seeds still produce
        # distinct snapshots (the Phase 45 contract is preserved).
        now = "2026-08-08T00:00:00+00:00"
        snap_a = freeze_input_snapshot(manifest=_sample_manifest(seed=42), created_at=now)
        snap_b = freeze_input_snapshot(manifest=_sample_manifest(seed=43), created_at=now)
        assert snap_a.manifest_sha256 != snap_b.manifest_sha256
        assert snap_a.snapshot_sha256 != snap_b.snapshot_sha256
        # The vocabulary fingerprint is identical (seed-independent).
        assert snap_a.component_digests["vocabulary"] == snap_b.component_digests["vocabulary"]


class TestVerifyVocabularyFingerprint:
    def test_passes_for_live_value(self) -> None:
        # No raise: the frozen value matches the live vocabulary.
        verify_vocabulary_fingerprint(vocabulary_fingerprint())

    def test_rejects_mismatch(self) -> None:
        with pytest.raises(VocabularyMismatchError):
            verify_vocabulary_fingerprint("0" * 64)

    def test_rejects_missing_value(self) -> None:
        with pytest.raises(VocabularyMismatchError):
            verify_vocabulary_fingerprint(None)

    def test_records_frozen_and_live_on_mismatch(self) -> None:
        frozen = "deadbeef" + "0" * 56
        with pytest.raises(VocabularyMismatchError) as exc_info:
            verify_vocabulary_fingerprint(frozen)
        assert exc_info.value.frozen == frozen
        assert exc_info.value.live == vocabulary_fingerprint()

    def test_is_a_value_error_subclass(self) -> None:
        # Fail-closed mismatch is a ValueError so the run-layer can surface it
        # uniformly alongside the other contract validation errors.
        assert issubclass(VocabularyMismatchError, ValueError)



# ================================================================
# Task 46-02-01: deterministic seeded PRNG, seed pool, candidate digest
# ================================================================


def _take(factory: AlphaFactory, k: int) -> list[GenerationResult]:
    return [factory.generate_next() for _ in range(k)]


class TestCandidateDigest:
    def test_is_lowercase_64_hex(self) -> None:
        digest = candidate_digest(
            canonical_expression="open", seed=1, step=0, operation="seed", vocab_version="v"
        )
        assert _HEX64.fullmatch(digest)

    def test_identical_inputs_yield_identical_digest(self) -> None:
        kwargs = dict(canonical_expression="open", seed=1, step=0, operation="seed", vocab_version="v")
        assert candidate_digest(**kwargs) == candidate_digest(**kwargs)

    def test_step_distinguishes_identical_expression(self) -> None:
        shared = dict(canonical_expression="open", seed=1, operation="seed", vocab_version="v")
        assert candidate_digest(step=0, **shared) != candidate_digest(step=1, **shared)

    def test_operation_distinguishes_identical_expression(self) -> None:
        shared = dict(canonical_expression="open", seed=1, step=0, vocab_version="v")
        assert candidate_digest(operation="seed", **shared) != candidate_digest(operation="crossover", **shared)

    def test_vocab_version_distinguishes(self) -> None:
        shared = dict(canonical_expression="open", seed=1, step=0, operation="seed")
        assert candidate_digest(vocab_version="v1", **shared) != candidate_digest(vocab_version="v2", **shared)

    def test_seed_distinguishes(self) -> None:
        shared = dict(canonical_expression="open", step=0, operation="seed", vocab_version="v")
        assert candidate_digest(seed=1, **shared) != candidate_digest(seed=2, **shared)


class TestGenerationResultProvenance:
    def test_digest_property_matches_candidate_digest(self) -> None:
        factory = AlphaFactory(3, max_candidates=1)
        result = factory.generate_next()
        assert result is not None
        assert result.digest == candidate_digest(
            canonical_expression=result.canonical_expression,
            seed=result.seed,
            step=result.step,
            operation=result.operation,
            vocab_version=vocabulary_fingerprint(),
        )

    def test_attempt_ordinal_is_step_plus_one(self) -> None:
        factory = AlphaFactory(3, max_candidates=5)
        results = _take(factory, 5)
        assert [r.attempt_ordinal for r in results] == [1, 2, 3, 4, 5]

    def test_seed_candidate_carries_empty_parent_steps(self) -> None:
        factory = AlphaFactory(3, max_candidates=3)
        for result in _take(factory, 3):
            assert result.parent_steps == ()
            assert result.operation == "seed"
            assert result.seed == 3


class TestSeedPoolValidity:
    def test_every_seed_expression_canonicalizes_and_uses_allowed_fields(self) -> None:
        size = AlphaFactory(1, max_candidates=1).seed_pool_size
        factory = AlphaFactory(1, max_candidates=size)
        results = _take(factory, size)
        assert len(results) == size
        for result in results:
            # Independent re-canonicalization (no second engine) must not raise.
            assert factor_dsl.canonicalize(result.ast) == result.canonical_expression
            features = factor_dsl.extract_features(result.ast)
            assert features.fields <= factor_dsl.ALLOWED_FIELDS
            assert result.operation == "seed"
            assert result.parent_steps == ()

    def test_generate_next_returns_none_past_budget(self) -> None:
        factory = AlphaFactory(1, max_candidates=2)
        assert len(_take(factory, 2)) == 2
        assert factory.generate_next() is None


class TestSeedPoolEnumerationOrder:
    def test_single_fields_then_unary_then_rank_zscore(self) -> None:
        n = len(factor_dsl.ALLOWED_FIELDS)
        fields = sorted(factor_dsl.ALLOWED_FIELDS)
        factory = AlphaFactory(101, max_candidates=4 * n)
        results = _take(factory, 4 * n)
        assert [r.canonical_expression for r in results[:n]] == fields
        assert [r.canonical_expression for r in results[n:2 * n]] == [f"-{name}" for name in fields]
        assert [r.canonical_expression for r in results[2 * n:3 * n]] == [f"rank({name})" for name in fields]
        assert [r.canonical_expression for r in results[3 * n:4 * n]] == [f"zscore({name})" for name in fields]

    def test_rolling_mean_block_uses_legal_windows(self) -> None:
        n = len(factor_dsl.ALLOWED_FIELDS)
        fields = sorted(factor_dsl.ALLOWED_FIELDS)
        windows = (5, 20, 60)
        size = 4 * n + n * len(windows)
        factory = AlphaFactory(101, max_candidates=size)
        results = _take(factory, size)
        rolling = results[4 * n:]
        expected = [f"rolling_mean({name}, {window})" for name in fields for window in windows]
        assert [r.canonical_expression for r in rolling] == expected

    def test_binary_trees_close_the_seed_pool(self) -> None:
        n = len(factor_dsl.ALLOWED_FIELDS)
        fields = sorted(factor_dsl.ALLOWED_FIELDS)
        size = AlphaFactory(101, max_candidates=1).seed_pool_size
        factory = AlphaFactory(101, max_candidates=size)
        tail = _take(factory, size)[4 * n + n * 3:]
        assert len(tail) == 5
        assert tail[0].canonical_expression == f"{fields[0]} + {fields[1]}"
        assert tail[1].canonical_expression == f"{fields[2]} - {fields[3]}"
        assert tail[2].canonical_expression == f"{fields[4]} * {fields[5]}"
        assert tail[3].canonical_expression == f"{fields[0]} * 2"
        assert tail[4].canonical_expression == f"{fields[1]} / 100"

    def test_seed_pool_size_is_vocab_derived(self) -> None:
        n = len(factor_dsl.ALLOWED_FIELDS)
        # 4 field-sized blocks + 3 rolling windows per field + 5 binary trees.
        assert AlphaFactory(1, max_candidates=1).seed_pool_size == 4 * n + 3 * n + 5


class TestPRNGIsolation:
    def test_only_instance_local_random_is_used(self) -> None:
        """No draw comes from the global random module; only random.Random(seed)."""
        source = inspect.getsource(alpha_factory)
        forbidden = (
            "random.random(", "random.choice(", "random.randrange(", "random.randint(",
            "random.uniform(", "random.seed(", "random.sample(", "random.shuffle(",
            "random.getstate(", "random.setstate(",
        )
        for token in forbidden:
            assert token not in source, (
                f"alpha_factory must not draw from the global random module: {token!r}"
            )
        assert "random.Random(" in source


class TestWorkerTimingIndependence:
    def test_two_instances_produce_identical_seed_prefixes(self) -> None:
        n = len(factor_dsl.ALLOWED_FIELDS)
        a = AlphaFactory(99, max_candidates=3 * n)
        b = AlphaFactory(99, max_candidates=3 * n)
        results_a = _take(a, 3 * n)
        results_b = _take(b, 3 * n)
        assert len(results_a) == len(results_b) == 3 * n
        for x, y in zip(results_a, results_b):
            assert x.canonical_expression == y.canonical_expression
            assert x.operation == y.operation
            assert x.parent_steps == y.parent_steps
            assert x.step == y.step
            assert x.digest == y.digest

    def test_replay_to_matches_live_prefix(self) -> None:
        n = len(factor_dsl.ALLOWED_FIELDS)
        live = AlphaFactory(42, max_candidates=2 * n)
        prefix = live.replay_to(n)
        produced = _take(live, n)
        assert [r.canonical_expression for r in prefix] == [r.canonical_expression for r in produced]
        assert [r.operation for r in prefix] == [r.operation for r in produced]
        assert [r.parent_steps for r in prefix] == [r.parent_steps for r in produced]


# ================================================================
# Task 46-02-02: mutation, crossover, lineage, full replay determinism
# ================================================================


def _drain(factory: AlphaFactory) -> list[GenerationResult]:
    results: list[GenerationResult] = []
    while True:
        result = factory.generate_next()
        if result is None:
            return results
        results.append(result)


def _evolution_budget() -> int:
    """A budget large enough to exhaust the seed pool and run both waves."""
    return AlphaFactory(1, max_candidates=1).seed_pool_size + 100


def _has_node(ast: object, kind: type) -> bool:
    return any(isinstance(node, kind) for _, node in alpha_factory._all_paths(ast))  # type: ignore[attr-defined]


class TestEvolutionRespectsBudget:
    def test_generate_next_stops_at_max_candidates(self) -> None:
        budget = _evolution_budget()
        factory = AlphaFactory(7, max_candidates=budget)
        results = _drain(factory)
        assert len(results) == budget
        assert factory.generate_next() is None
        assert factory.step == budget

    def test_steps_are_zero_based_and_contiguous(self) -> None:
        budget = _evolution_budget()
        factory = AlphaFactory(7, max_candidates=budget)
        assert [r.step for r in _drain(factory)] == list(range(budget))


class TestOperationsAndWaves:
    def test_operations_are_within_the_allowed_label_set(self) -> None:
        allowed = {
            "seed", "point_mutation_field", "point_mutation_operator",
            "point_mutation_literal", "subtree_replacement", "crossover",
        }
        factory = AlphaFactory(11, max_candidates=_evolution_budget())
        assert {r.operation for r in _drain(factory)} <= allowed

    def test_seed_pool_then_mutation_wave_then_crossover_wave(self) -> None:
        size = AlphaFactory(1, max_candidates=1).seed_pool_size
        budget = _evolution_budget()
        ops = [r.operation for r in _drain(AlphaFactory(11, max_candidates=budget))]
        assert all(op == "seed" for op in ops[:size])
        mutation_budget = (budget - size) // 2
        mutation_block = ops[size:size + mutation_budget]
        crossover_block = ops[size + mutation_budget:]
        assert mutation_block and crossover_block
        assert all(op not in {"seed", "crossover"} for op in mutation_block)
        assert all(op == "crossover" for op in crossover_block)


class TestEvolutionOutputsCanonicalize:
    def test_every_output_is_a_legal_dsl_ast(self) -> None:
        factory = AlphaFactory(23, max_candidates=_evolution_budget())
        for result in _drain(factory):
            # No second engine: the generator's AST must re-canonicalize and
            # reference only governed numeric fields.
            assert factor_dsl.canonicalize(result.ast) == result.canonical_expression
            assert factor_dsl.extract_features(result.ast).fields <= factor_dsl.ALLOWED_FIELDS


class TestMutationKinds:
    """Deterministic coverage of each mutation operation on applicable parents."""

    def test_point_mutation_field_swaps_a_field(self) -> None:
        factory = AlphaFactory(3, max_candidates=1)
        parent = factory._seed_pool[0]  # single field
        mutated = factory._apply_mutation(parent, "point_mutation_field")
        assert mutated is not None
        assert factor_dsl.canonicalize(mutated) != factor_dsl.canonicalize(parent)

    def test_point_mutation_operator_swaps_a_binary_operator(self) -> None:
        factory = AlphaFactory(3, max_candidates=1)
        parent = next(ast for ast in factory._seed_pool if _has_node(ast, factor_dsl.Binary))
        mutated = factory._apply_mutation(parent, "point_mutation_operator")
        assert mutated is not None
        factor_dsl.canonicalize(mutated)  # must not raise

    def test_point_mutation_literal_changes_a_number(self) -> None:
        factory = AlphaFactory(3, max_candidates=1)
        parent = next(ast for ast in factory._seed_pool if _has_node(ast, factor_dsl.Number))
        mutated = factory._apply_mutation(parent, "point_mutation_literal")
        assert mutated is not None
        factor_dsl.canonicalize(mutated)  # must not raise

    def test_subtree_replacement_replaces_a_node(self) -> None:
        factory = AlphaFactory(3, max_candidates=1)
        parent = factory._seed_pool[0]
        mutated = factory._apply_mutation(parent, "subtree_replacement")
        assert mutated is not None
        factor_dsl.canonicalize(mutated)  # must not raise


class TestLineageInvariants:
    def test_seed_candidates_have_no_parents(self) -> None:
        size = AlphaFactory(1, max_candidates=1).seed_pool_size
        for result in _drain(AlphaFactory(31, max_candidates=size)):
            assert result.parent_steps == ()
            assert result.operation == "seed"

    def test_mutation_has_exactly_one_preceding_parent(self) -> None:
        factory = AlphaFactory(31, max_candidates=_evolution_budget())
        for result in _drain(factory):
            if result.operation in {"seed", "crossover"}:
                continue
            assert len(result.parent_steps) == 1
            assert result.parent_steps[0] < result.step

    def test_crossover_has_two_distinct_preceding_parents(self) -> None:
        factory = AlphaFactory(31, max_candidates=_evolution_budget())
        seen_crossover = False
        for result in _drain(factory):
            if result.operation != "crossover":
                continue
            seen_crossover = True
            assert len(result.parent_steps) == 2
            left, right = result.parent_steps
            assert left != right
            assert left < result.step
            assert right < result.step
        assert seen_crossover

    def test_every_parent_step_was_produced_earlier(self) -> None:
        factory = AlphaFactory(31, max_candidates=_evolution_budget())
        results = _drain(factory)
        produced = {r.step for r in results}
        for result in results:
            for parent in result.parent_steps:
                assert parent in produced
                assert parent < result.step


class TestFullReplayDeterminism:
    def test_two_instances_produce_byte_identical_full_streams(self) -> None:
        budget = _evolution_budget()
        results_a = _drain(AlphaFactory(1234567, max_candidates=budget))
        results_b = _drain(AlphaFactory(1234567, max_candidates=budget))
        assert len(results_a) == len(results_b) == budget
        for x, y in zip(results_a, results_b):
            assert x.step == y.step
            assert x.canonical_expression == y.canonical_expression
            assert x.operation == y.operation
            assert x.parent_steps == y.parent_steps
            assert x.digest == y.digest

    def test_distinct_digest_sequence_is_provenance_encoded(self) -> None:
        budget = _evolution_budget()
        digests = [r.digest for r in _drain(AlphaFactory(1234567, max_candidates=budget))]
        assert len(digests) == len(set(digests)) == budget

    def test_different_seeds_produce_different_streams(self) -> None:
        budget = _evolution_budget()
        a = [r.canonical_expression for r in _drain(AlphaFactory(1, max_candidates=budget))]
        b = [r.canonical_expression for r in _drain(AlphaFactory(2, max_candidates=budget))]
        assert a != b


class TestReplayDeterminism:
    def test_replay_to_reproduces_prefix_into_the_mutation_wave(self) -> None:
        budget = _evolution_budget()
        size = AlphaFactory(1, max_candidates=1).seed_pool_size
        k = size + 30  # well into the mutation wave
        live = AlphaFactory(555, max_candidates=budget)
        prefix = live.replay_to(k)
        produced = _drain(live)[:k]
        assert len(prefix) == k
        for x, y in zip(prefix, produced):
            assert x.canonical_expression == y.canonical_expression
            assert x.operation == y.operation
            assert x.parent_steps == y.parent_steps
            assert x.digest == y.digest

    def test_replay_rebuilds_from_seed_without_serialized_state(self) -> None:
        # A fully-consumed factory still replays the prefix purely from the seed.
        budget = _evolution_budget()
        size = AlphaFactory(1, max_candidates=1).seed_pool_size
        k = size + 10
        advanced = AlphaFactory(999, max_candidates=budget)
        _drain(advanced)
        prefix_from_advanced = advanced.replay_to(k)
        fresh = AlphaFactory(999, max_candidates=budget)
        prefix_fresh = [fresh.generate_next() for _ in range(k)]
        for x, y in zip(prefix_from_advanced, prefix_fresh):
            assert x.canonical_expression == y.canonical_expression
            assert x.parent_steps == y.parent_steps


# ================================================================
# Task 46-03-01: validate every candidate through factor_dsl + complexity
# ================================================================

_TLOC = factor_dsl.SourceLocation(offset=0, line=1, column=1)


def _tfield(name: str) -> factor_dsl.Expression:
    return factor_dsl.Field(name, _TLOC)


def _tnumber(value: float) -> factor_dsl.Expression:
    return factor_dsl.Number(value, _TLOC)


def _nested_binary(depth: int) -> factor_dsl.Expression:
    """Left-nested ``+`` tree of ``depth`` leaves; depth 1 is a single leaf."""
    node: factor_dsl.Expression = _tfield("close")
    for _ in range(depth - 1):
        node = factor_dsl.Binary("+", node, _tfield("open"), _TLOC)
    return node


def _full_binary(depth: int) -> factor_dsl.Expression:
    """Balanced ``+`` tree: ``2**depth - 1`` nodes, depth ``depth``."""
    if depth <= 1:
        return _tfield("close")
    return factor_dsl.Binary("+", _full_binary(depth - 1), _full_binary(depth - 1), _TLOC)


class TestMeasureComplexity:
    def test_single_field_is_depth_one_node_one(self) -> None:
        assert measure_complexity(_tfield("close")) == (1, 1)

    def test_number_literal_is_depth_one_node_one(self) -> None:
        assert measure_complexity(_tnumber(5.0)) == (1, 1)

    def test_binary_expression(self) -> None:
        ast = factor_dsl.Binary("+", _tfield("close"), _tfield("open"), _TLOC)
        assert measure_complexity(ast) == (2, 3)

    def test_unary_expression(self) -> None:
        ast = factor_dsl.Unary("-", _tfield("close"), _TLOC)
        assert measure_complexity(ast) == (2, 2)

    def test_rank_call(self) -> None:
        ast = factor_dsl.Call("rank", (_tfield("close"),), _TLOC)
        assert measure_complexity(ast) == (2, 2)

    def test_rolling_mean_call_counts_every_argument(self) -> None:
        ast = factor_dsl.Call("rolling_mean", (_tfield("close"), _tnumber(20.0)), _TLOC)
        assert measure_complexity(ast) == (2, 3)

    def test_clip_call_counts_three_arguments(self) -> None:
        ast = factor_dsl.Call("clip", (_tfield("close"), _tnumber(1.0), _tnumber(2.0)), _TLOC)
        assert measure_complexity(ast) == (2, 4)

    def test_nested_binary_depth_and_node_count(self) -> None:
        # (close + open) + high  -> depth 3, nodes 5
        ast = factor_dsl.Binary(
            "+",
            factor_dsl.Binary("+", _tfield("close"), _tfield("open"), _TLOC),
            _tfield("high"),
            _TLOC,
        )
        assert measure_complexity(ast) == (3, 5)

    def test_deeply_nested_trees_count(self) -> None:
        assert measure_complexity(_nested_binary(7)) == (7, 13)
        assert measure_complexity(_full_binary(4)) == (4, 15)

    def test_does_not_validate_semantically_invalid_ast(self) -> None:
        # Division by a literal zero and a denied field are DSL rejections, but
        # measure_complexity is a pure structural walk and must not raise.
        div_zero = factor_dsl.Binary("/", _tfield("close"), _tnumber(0.0), _TLOC)
        denied = _tfield("label")
        assert measure_complexity(div_zero) == (2, 3)
        assert measure_complexity(denied) == (1, 1)

    def test_does_not_mutate_ast(self) -> None:
        ast = _nested_binary(4)
        before = factor_dsl.canonicalize(ast)
        measure_complexity(ast)
        assert factor_dsl.canonicalize(ast) == before


class TestValidationResultShape:
    def test_frozen_with_contract_fields(self) -> None:
        result = ValidationResult(
            status="valid",
            canonical_expression="close",
            features=factor_dsl.extract_features(factor_dsl.Field("close", _TLOC)),
            reason={},
        )
        assert result.status == "valid"
        assert result.canonical_expression == "close"
        assert result.features is not None
        assert result.reason == {}
        with pytest.raises(AttributeError):
            result.status = "invalid"  # type: ignore[misc]

    def test_invalid_result_allows_none_features(self) -> None:
        result = ValidationResult(status="invalid", canonical_expression="", features=None, reason={"diagnostic": "x"})
        assert result.features is None
        assert result.status == "invalid"


class TestValidateCandidate:
    def test_valid_single_field_has_features_and_empty_reason(self) -> None:
        result = validate_candidate(_tfield("close"), max_depth=6, max_nodes=40)
        assert result.status == "valid"
        assert result.canonical_expression == "close"
        assert result.features is not None
        assert result.features.fields == frozenset({"close"})
        assert result.reason == {}

    def test_valid_binary_round_trips_through_parse_factor(self) -> None:
        ast = factor_dsl.Binary("+", _tfield("close"), _tfield("open"), _TLOC)
        result = validate_candidate(ast, max_depth=6, max_nodes=40)
        assert result.status == "valid"
        assert result.canonical_expression == "close + open"
        assert result.features.operators == frozenset({"+"})

    def test_invalid_result_carries_no_features(self) -> None:
        result = validate_candidate(_nested_binary(7), max_depth=6, max_nodes=100)
        assert result.status == "invalid"
        assert result.features is None

    def test_excessive_depth_returns_complexity_diagnostic(self) -> None:
        result = validate_candidate(_nested_binary(7), max_depth=6, max_nodes=100)
        assert result.status == "invalid"
        assert result.reason["diagnostic"] == "expression depth 7 exceeds max_depth 6"
        assert result.reason["location"] == "depth 7"
        assert result.reason["dsl_version"] == factor_dsl.DSL_VERSION
        assert result.reason["vocab_version"] == vocabulary_fingerprint()
        assert "raw_expression" in result.reason

    def test_excessive_nodes_returns_complexity_diagnostic(self) -> None:
        # depth 4 (<= 10) so only the node count trips; full binary depth 4 = 15 nodes
        result = validate_candidate(_full_binary(4), max_depth=10, max_nodes=10)
        assert result.status == "invalid"
        assert result.reason["diagnostic"] == "expression nodes 15 exceeds max_nodes 10"
        assert result.reason["location"] == "nodes 15"
        assert result.reason["dsl_version"] == factor_dsl.DSL_VERSION

    def test_within_limits_complexity_is_valid(self) -> None:
        result = validate_candidate(_full_binary(3), max_depth=6, max_nodes=40)
        assert result.status == "valid"
        assert result.features is not None

    def test_complexity_gate_runs_before_semantic_validation(self) -> None:
        # Over-deep AND contains a denied field: complexity is reported, not the
        # DSL error, because measure_complexity is checked first (AF-REQ-03).
        overdeep_denied = factor_dsl.Binary("+", _nested_binary(7), _tfield("label"), _TLOC)
        result = validate_candidate(overdeep_denied, max_depth=6, max_nodes=100)
        assert result.status == "invalid"
        assert result.reason["diagnostic"].startswith("expression depth")

    def test_dsl_rejection_returns_invalid_reason(self) -> None:
        # A denied field is rejected by canonicalize before parse_factor.
        result = validate_candidate(_tfield("label"), max_depth=6, max_nodes=40)
        assert result.status == "invalid"
        assert result.features is None
        assert "label" in result.reason["diagnostic"]
        assert result.reason["dsl_version"] == factor_dsl.DSL_VERSION
        assert result.reason["vocab_version"] == vocabulary_fingerprint()
        assert result.reason["raw_expression"] == ""

    def test_every_factory_output_validates(self) -> None:
        # The generation engine must only ever emit complexity-valid, DSL-valid ASTs.
        factory = AlphaFactory(7, max_candidates=120)
        for result_obj in _drain(factory):
            vr = validate_candidate(result_obj.ast, max_depth=DEFAULT_MAX_DEPTH, max_nodes=DEFAULT_MAX_NODES)
            assert vr.status == "valid", (result_obj.canonical_expression, vr.reason)
            assert vr.features is not None


# ================================================================
# Task 46-03-02: structured invalid diagnostics for every AF-REQ-03 mode
# ================================================================

_DEFAULTS = {"max_depth": DEFAULT_MAX_DEPTH, "max_nodes": DEFAULT_MAX_NODES}


@pytest.mark.parametrize(
    "mode, source, max_depth, max_nodes",
    [
        # --- DSL-validated rejection modes (raised by parse_factor) ---
        ("denied_field", "label", DEFAULT_MAX_DEPTH, DEFAULT_MAX_NODES),
        ("unknown_field", "not_a_field", DEFAULT_MAX_DEPTH, DEFAULT_MAX_NODES),
        ("unknown_function", "foo(close)", DEFAULT_MAX_DEPTH, DEFAULT_MAX_NODES),
        ("invalid_arity", "rank(close, open)", DEFAULT_MAX_DEPTH, DEFAULT_MAX_NODES),
        ("excessive_window", "rolling_mean(close, 500)", DEFAULT_MAX_DEPTH, DEFAULT_MAX_NODES),
        ("nonfinite_literal", "1e999", DEFAULT_MAX_DEPTH, DEFAULT_MAX_NODES),
        ("division_by_literal_zero", "close / 0", DEFAULT_MAX_DEPTH, DEFAULT_MAX_NODES),
        ("reversed_clip_bounds", "clip(close, 5, 1)", DEFAULT_MAX_DEPTH, DEFAULT_MAX_NODES),
        ("malformed_syntax", "close +", DEFAULT_MAX_DEPTH, DEFAULT_MAX_NODES),
        # --- complexity rejection modes (raised here, not by the DSL) ---
        # 7 operands -> depth 7 > max_depth 6; nodes 13 <= 40
        ("excessive_depth", "close + close + close + close + close + close + close", 6, DEFAULT_MAX_NODES),
        # 7 operands -> depth 7 <= 20; nodes 13 > max_nodes 5
        ("excessive_nodes", "close + close + close + close + close + close + close", 20, 5),
    ],
)
def test_each_rejection_mode_is_invalid(mode, source, max_depth, max_nodes) -> None:
    result = validate_expression_text(source, max_depth=max_depth, max_nodes=max_nodes)
    assert result.status == "invalid", (mode, result)
    assert result.features is None
    reason = result.reason
    # Every payload carries the full structured diagnostic (research §4).
    assert reason["diagnostic"], (mode, reason)
    assert reason["location"], (mode, reason)
    assert reason["dsl_version"] == factor_dsl.DSL_VERSION
    assert reason["vocab_version"] == vocabulary_fingerprint()
    assert "raw_expression" in reason


@pytest.mark.parametrize(
    "mode, source",
    [
        ("denied_field", "label"),
        ("unknown_function", "foo(close)"),
        ("invalid_arity", "rank(close, open)"),
        ("excessive_window", "rolling_mean(close, 500)"),
        ("division_by_literal_zero", "close / 0"),
        ("reversed_clip_bounds", "clip(close, 5, 1)"),
        ("malformed_syntax", "close +"),
    ],
)
def test_dsl_error_location_sourced_from_diagnostic_display(mode, source) -> None:
    # The location field comes from FactorDslError.diagnostic.location.display()
    # ("line N, column M") for every DSL-raised error.
    result = validate_expression_text(source, **_DEFAULTS)
    assert result.status == "invalid"
    assert re.match(r"line \d+, column \d+\Z", result.reason["location"]), (mode, result.reason["location"])


def test_complexity_location_names_measured_dimension() -> None:
    # The complexity location comes from the measurement, not a source location.
    deep = validate_expression_text(
        "close + close + close + close + close + close + close", max_depth=6, max_nodes=DEFAULT_MAX_NODES
    )
    assert deep.reason["diagnostic"] == "expression depth 7 exceeds max_depth 6"
    assert deep.reason["location"] == "depth 7"
    wide = validate_expression_text(
        "close + close + close + close + close + close + close", max_depth=20, max_nodes=5
    )
    assert wide.reason["diagnostic"] == "expression nodes 13 exceeds max_nodes 5"
    assert wide.reason["location"] == "nodes 13"


class TestAstOnlyRejectionModes:
    """Two rejection modes are unreachable from text and need a constructed AST.

    * partition semantics: a function present in _FUNCTION_ARITY but absent from
      _FUNCTION_PARTITION -- impossible from text because the two dicts are kept
      in lockstep by an invariant test, so exercised via monkeypatch.
    * unsupported operator: the grammar only tokenizes +-*/(), so an illegal
      operator only arises from a directly-constructed Binary node.
    """

    def test_missing_partition_semantics_is_invalid(self, monkeypatch) -> None:
        monkeypatch.delitem(factor_dsl._FUNCTION_PARTITION, "rank")
        ast = factor_dsl.Call("rank", (_tfield("close"),), _TLOC)
        result = validate_candidate(ast, **_DEFAULTS)
        assert result.status == "invalid"
        assert "partition" in result.reason["diagnostic"].lower()
        assert result.reason["dsl_version"] == factor_dsl.DSL_VERSION
        assert result.reason["vocab_version"] == vocabulary_fingerprint()

    def test_unsupported_binary_operator_is_invalid(self) -> None:
        ast = factor_dsl.Binary("^", _tfield("close"), _tfield("open"), _TLOC)
        result = validate_candidate(ast, **_DEFAULTS)
        assert result.status == "invalid"
        assert "operator" in result.reason["diagnostic"].lower()
        assert result.reason["dsl_version"] == factor_dsl.DSL_VERSION

    def test_unsupported_unary_operator_is_invalid(self) -> None:
        ast = factor_dsl.Unary("~", _tfield("close"), _TLOC)
        result = validate_candidate(ast, **_DEFAULTS)
        assert result.status == "invalid"
        assert "operator" in result.reason["diagnostic"].lower()


class TestInvalidReasonPayload:
    def test_carries_full_diagnostic_payload(self) -> None:
        try:
            factor_dsl.parse_factor("label")
        except factor_dsl.FactorDslError as error:
            payload = invalid_reason(error, "label", vocabulary_fingerprint())
        else:  # pragma: no cover
            raise AssertionError("parse_factor('label') should have raised")
        assert set(payload) == {"diagnostic", "location", "dsl_version", "vocab_version", "raw_expression"}
        assert "label" in payload["diagnostic"]
        assert payload["dsl_version"] == factor_dsl.DSL_VERSION
        assert payload["raw_expression"] == "label"


class TestInvalidCandidatesNeverSuppressed:
    def test_validate_never_raises_or_returns_none_for_rejections(self) -> None:
        # AF-REQ-03 / T-46-09: rejections are durable invalid records, never
        # raised past the boundary or swallowed to None.
        for source in ("label", "foo(close)", "close / 0", "close +", "1e999"):
            result = validate_expression_text(source, **_DEFAULTS)
            assert result is not None
            assert result.status == "invalid"

    def test_valid_expression_text_is_valid(self) -> None:
        for source in ("close", "close + open", "rank(close)", "rolling_mean(close, 20)", "clip(close, 1, 5)"):
            result = validate_expression_text(source, **_DEFAULTS)
            assert result.status == "valid", (source, result)
            assert result.features is not None
            assert result.reason == {}

    def test_invalid_result_round_trips_to_json(self) -> None:
        # The reason payload must be JSON-serializable so the worker loop can
        # persist it verbatim as reason_json (plan 46-04).
        import json

        result = validate_expression_text("foo(close)", **_DEFAULTS)
        encoded = json.dumps(dict(result.reason))
        decoded = json.loads(encoded)
        assert decoded["diagnostic"]
        assert decoded["dsl_version"] == factor_dsl.DSL_VERSION