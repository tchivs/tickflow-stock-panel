"""DSL v3 新算子测试 — 边界/分区语义/数值 parity/序列化。"""
from __future__ import annotations

import polars as pl
import pytest

from app.research.factor_dsl import (
    _FUNCTION_ARITY,
    _FUNCTION_PARTITION,
    FactorDslError,
    compile_factor,
    parse_factor,
)


def _panel() -> pl.DataFrame:
    """两个 symbol x 6 日, 保证 per_symbol 分区可检验跨标的污染。"""
    return pl.DataFrame(
        {
            "symbol": ["a"] * 6 + ["b"] * 6,
            "date": sorted(list(range(6)) * 2),
            "close": [1.0, 2.0, 4.0, 8.0, 4.0, 6.0, 10.0, 5.0, 3.0, 9.0, 6.0, 12.0],
            "volume": [100.0, 200.0, 150.0, 300.0, 250.0, 50.0, 10.0, 20.0, 15.0, 30.0, 25.0, 5.0],
        }
    )


@pytest.mark.parametrize(
    "source, expected",
    [
        ("ref(close, 0)", "window must be an integer from 1 to 252"),
        ("ref(close, 253)", "window must be an integer from 1 to 252"),
        ("ref(close, 2.5)", "window must be an integer"),
        ("rolling_std(close, close)", "window must be an integer"),
        ("rolling_quantile(close, 5, 0)", "quantile must be strictly between"),
        ("rolling_quantile(close, 5, 1.0)", "quantile must be strictly between"),
        ("rolling_quantile(close, 5, close)", "quantile must be a numeric literal"),
        ("rolling_corr(close, volume)", "expects 3 arguments"),
        ("max(close)", "expects 2 arguments"),
    ],
)
def test_rejects_invalid_v3_calls(source: str, expected: str) -> None:
    with pytest.raises(FactorDslError, match=expected):
        compile_factor(source)


def test_v3_tables_stay_consistent() -> None:
    assert set(_FUNCTION_ARITY) == set(_FUNCTION_PARTITION)


def test_ref_shifts_within_symbol_partition() -> None:
    out = _panel().with_columns(compile_factor("ref(close, 2)").alias("f"))
    a = out.filter(pl.col("symbol") == "a").get_column("f").to_list()
    b = out.filter(pl.col("symbol") == "b").get_column("f").to_list()
    # 头部 null 属于同一 symbol 的 lag, 不允许从另一 symbol 借值
    assert a == [None, None, 1.0, 2.0, 4.0, 8.0]
    assert b == [None, None, 10.0, 5.0, 3.0, 9.0]


def test_rolling_corr_matches_manual_computation() -> None:
    out = _panel().with_columns(compile_factor("rolling_corr(close, volume, 3)").alias("f"))
    got = out.filter(pl.col("symbol") == "a").get_column("f").to_list()
    close = [1.0, 2.0, 4.0, 8.0, 4.0, 6.0]
    volume = [100.0, 200.0, 150.0, 300.0, 250.0, 50.0]
    # min_samples=1: 头 1 个样本 (无法算) 为 None; 2 个样本起取窗口内可得样本
    expected: list[float | None] = [None]
    for i in range(1, 6):
        lo = max(0, i - 2)
        cs, vs = close[lo : i + 1], volume[lo : i + 1]
        mc, mv = sum(cs) / len(cs), sum(vs) / len(vs)
        cov = sum((c - mc) * (v - mv) for c, v in zip(cs, vs, strict=True))
        sc = sum((c - mc) ** 2 for c in cs) ** 0.5
        sv = sum((v - mv) ** 2 for v in vs) ** 0.5
        expected.append(cov / (sc * sv))
    assert got == pytest.approx(expected, abs=1e-9)


def test_rolling_std_sum_min_max_quantile_parity() -> None:
    import statistics

    out = _panel().with_columns(
        compile_factor("rolling_std(close, 3)").alias("std"),
        compile_factor("rolling_sum(close, 3)").alias("sum"),
        compile_factor("rolling_min(close, 3)").alias("min"),
        compile_factor("rolling_max(close, 3)").alias("max"),
        compile_factor("rolling_quantile(close, 3, 0.5)").alias("qtl"),
    ).filter(pl.col("symbol") == "a")
    close = [1.0, 2.0, 4.0, 8.0, 4.0, 6.0]
    assert out.get_column("std").to_list()[2:] == pytest.approx(
        [statistics.stdev(close[i - 2 : i + 1]) for i in range(2, 6)], abs=1e-9
    )
    assert out.get_column("sum").to_list()[2:] == [7.0, 14.0, 16.0, 18.0]
    assert out.get_column("min").to_list()[2:] == [1.0, 2.0, 4.0, 4.0]
    assert out.get_column("max").to_list()[2:] == [4.0, 8.0, 8.0, 8.0]
    assert out.get_column("qtl").to_list()[2:] == [2.0, 4.0, 4.0, 6.0]


def test_pointwise_max_min_no_partition() -> None:
    out = _panel().with_columns(
        compile_factor("max(open_alias_ignored, close)".replace("open_alias_ignored", "volume")).alias("mx"),
        compile_factor("min(volume, close)").alias("mn"),
    )
    assert out.get_column("mx").to_list() == _panel().with_columns(
        pl.max_horizontal(pl.col("volume"), pl.col("close")).alias("mx")
    ).get_column("mx").to_list()
    assert out.get_column("mn").to_list()[0] == 1.0  # min(100, 1)


def test_v3_canonical_serialization_roundtrip() -> None:
    sources = [
        "ref(close,5)/close",
        "rolling_corr(close,log1p(volume),10)",
        "rolling_quantile(close,5,0.8)/close",
        "max(close-ref(close,1),0)",
        "(max(open,close)-low)/open",
    ]
    for source in sources:
        canonical = parse_factor(source).canonical_expression
        assert parse_factor(canonical).canonical_expression == canonical
        assert parse_factor("  " + source.replace(" ", "") + "  ").canonical_expression == canonical


def test_v3_partition_context_propagates_to_features() -> None:
    pointwise = parse_factor("max(close, volume)").features.partition_context
    assert pointwise == frozenset({"pointwise"})
    stateful = parse_factor("rolling_corr(close, volume, 5)").features.partition_context
    assert stateful == frozenset({"per_symbol"})
