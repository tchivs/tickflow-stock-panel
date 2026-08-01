from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from app.research.factor_dsl import (
    _FUNCTION_ARITY,
    _FUNCTION_PARTITION,
    DENIED_FIELDS,
    SHIFTED_LABEL_MAX_ABS_IC,
    FactorDslError,
    compile_factor,
    parse_factor,
    shifted_label_ic,
)


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
    frame = pl.DataFrame(
        {
            "symbol": ["A", "A", "A"],
            "date": ["2024-01-02", "2024-01-03", "2024-01-04"],
            "close": [11.0, 12.0, 13.0],
            "prev_close": [10.0, 11.0, 12.0],
            "volume": [100.0, 200.0, 300.0],
        }
    )

    result = frame.select(expression.alias("factor"))
    assert parsed.referenced_fields == {"close", "prev_close", "volume"}
    assert result.columns == ["factor"]
    assert result.height == 3


def test_compiler_partitions_stateful_functions_by_date_or_symbol() -> None:
    frame = pl.DataFrame(
        {
            "symbol": ["B", "A", "B", "A"],
            "date": ["2024-01-03", "2024-01-02", "2024-01-02", "2024-01-03"],
            "close": [40.0, 10.0, 20.0, 30.0],
        }
    ).sort(["symbol", "date"])

    rank = frame.with_columns(parse_factor("rank(close)").compile().alias("factor"))["factor"].to_list()
    zscore = frame.with_columns(parse_factor("zscore(close)").compile().alias("factor"))["factor"].to_list()
    rolling_mean = frame.with_columns(parse_factor("rolling_mean(close, 2)").compile().alias("factor"))["factor"].to_list()

    assert rank == [1.0, 1.0, 2.0, 2.0]
    assert zscore == pytest.approx([-0.7071067811865475, -0.7071067811865475, 0.7071067811865475, 0.7071067811865475])
    assert rolling_mean == pytest.approx([10.0, 20.0, 20.0, 30.0])


def test_function_partition_table_is_consistent_with_arity() -> None:
    """Every arity-registered operator must declare a partition context (FACT-04)."""
    assert set(_FUNCTION_ARITY) == set(_FUNCTION_PARTITION)


@pytest.mark.parametrize("field", sorted(DENIED_FIELDS))
def test_denied_label_identity_fields_raise_specific_diagnostic(field: str) -> None:
    with pytest.raises(FactorDslError, match="denied label/identity field"):
        parse_factor(field)


def test_denied_label_field_is_identified_inside_a_composite_expression() -> None:
    with pytest.raises(FactorDslError, match="denied label/identity field 'label'"):
        parse_factor("close + label")
    with pytest.raises(FactorDslError, match="denied label/identity field 'date'"):
        parse_factor("date")
    with pytest.raises(FactorDslError, match="denied label/identity field 'symbol'"):
        parse_factor("symbol")


def test_effective_partition_context_is_union_of_leaf_contexts() -> None:
    assert parse_factor("zscore(close) + rolling_mean(volume, 2)").features.partition_context == {
        "per_date", "per_symbol"
    }
    assert parse_factor("abs(close)").features.partition_context == {"pointwise"}
    assert parse_factor("close").features.partition_context == {"pointwise"}
    assert parse_factor("rank(close) + abs(volume)").features.partition_context == {"per_date", "pointwise"}


def _leakage_panel() -> pl.DataFrame:
    """Deterministic panel where prices cross zero so ``sign`` is non-constant."""
    rng = np.random.default_rng(20260801)
    n_symbols = 40
    n_dates = 400
    rows: list[dict] = []
    start = date(2023, 1, 2)
    for symbol_index in range(n_symbols):
        symbol = f"S{symbol_index:03d}"
        values = np.clip(np.cumsum(rng.normal(0.0, 0.02, n_dates)), -0.5, 2.0)
        for day, price in enumerate(values):
            rows.append({
                "symbol": symbol,
                "date": (start + timedelta(days=day)).isoformat(),
                "close": float(price),
            })
    return pl.DataFrame(rows).sort(["symbol", "date"])


@pytest.mark.parametrize("expression", [
    "abs(close)",
    "sign(close)",
    "log1p(close)",
    "clip(close, 0, 1000)",
    "rank(close)",
    "zscore(close)",
    "rolling_mean(close, 5)",
])
def test_shifted_label_ic_collapses_for_clean_factors(expression: str) -> None:
    """A clean factor has no information about the misaligned label window (FACT-04)."""
    panel = _leakage_panel().with_columns(parse_factor(expression).compile().cast(pl.Float64).alias("_factor"))
    assert shifted_label_ic(panel, horizon=1) <= SHIFTED_LABEL_MAX_ABS_IC


def test_shifted_label_ic_blocks_a_lookahead_expression() -> None:
    """A factor embedding the displaced label's own window shows nonzero IC."""
    panel = _leakage_panel().with_columns(
        (
            pl.col("close").shift(-2).over("symbol")
            / pl.col("close").shift(-1).over("symbol")
            - 1.0
        ).alias("_factor")
    )
    assert shifted_label_ic(panel, horizon=1) > SHIFTED_LABEL_MAX_ABS_IC


def test_shifted_label_ic_is_inf_for_an_empty_cross_section() -> None:
    panel = pl.DataFrame({"symbol": [], "date": [], "close": [], "_factor": []})
    assert shifted_label_ic(panel, horizon=1) == float("inf")

