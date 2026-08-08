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