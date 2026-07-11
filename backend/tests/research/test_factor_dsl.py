from __future__ import annotations

import pytest
import polars as pl

from app.research.factor_dsl import FactorDslError, compile_factor, parse_factor


@pytest.mark.parametrize(
    "source, expected",
    [
        ("__import__('os')", "unsupported character"),
        ("close.real", "unsupported character"),
        ("close[0]", "unsupported character"),
        ("unknown_field + close", "unknown governed numeric field"),
        ("unknown(close)", "unknown factor function"),
        ("abs(close, open)", "expects 1 argument"),
        ("rolling_mean(close, 0)", "window must be an integer"),
        ("close / 0", "division by a literal zero"),
        ("close +", "expected a numeric literal"),
    ],
)
def test_rejects_unsafe_or_invalid_syntax_before_compilation(source: str, expected: str) -> None:
    with pytest.raises(FactorDslError, match=expected):
        compile_factor(source)


def test_equivalent_text_has_canonical_expression_and_signature() -> None:
    first = parse_factor("( close + (ma20 * 2.0) )")
    second = parse_factor("close+ma20*2")

    assert first.canonical_expression == "close + ma20 * 2"
    assert first.canonical_expression == second.canonical_expression
    assert first.features.structural_signature == second.features.structural_signature
    assert first.features.shape_signature == second.features.shape_signature


def test_compiler_uses_only_governed_dependencies() -> None:
    parsed = parse_factor("clip(log1p(close / prev_close), -1, 1) + rolling_mean(volume, 2)")
    expression = parsed.compile()
    frame = pl.DataFrame({"close": [11.0, 12.0, 13.0], "prev_close": [10.0, 11.0, 12.0], "volume": [100.0, 200.0, 300.0]})

    result = frame.select(expression.alias("factor"))

    assert parsed.referenced_fields == {"close", "prev_close", "volume"}
    assert result.columns == ["factor"]
    assert result.height == 3
