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

from app.research import alpha_factory, factor_dsl
from app.research.alpha_factory import (
    CANONICAL_FORM,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_NODES,
    FACTORY_VERSION,
    PRNG_ALGORITHM,
    grammar_fingerprint,
    vocabulary_fingerprint,
)
from app.research.run_contract import digest_bytes

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
