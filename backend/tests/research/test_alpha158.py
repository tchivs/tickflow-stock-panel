"""Alpha158 语料测试 — 数量/唯一性/可解析/关键公式数值语义。"""
from __future__ import annotations

import polars as pl
import pytest

from app.research.alpha158 import build_alpha158, provenance
from app.research.factor_dsl import DSL_VERSION, compile_factor, parse_factor


def test_corpus_size_and_uniqueness() -> None:
    factors = build_alpha158()
    assert len(factors) == 128
    names = [f.name for f in factors]
    assert len(set(names)) == len(names)
    # canonical expression 唯一 → 导入器幂等键无碰撞
    canonicals = [parse_factor(f.expression).canonical_expression for f in factors]
    assert len(set(canonicals)) == len(canonicals)


def test_every_expression_parses_and_compiles_under_live_dsl() -> None:
    for factor in build_alpha158():
        parsed = parse_factor(factor.expression)
        assert parsed.dsl_version == DSL_VERSION
        compile_factor(factor.expression)


def test_corpus_covers_expected_operator_families() -> None:
    factors = build_alpha158()
    names = {f.name for f in factors}
    # 每个保留家族 x 每个窗口都在场
    for d in (5, 10, 20, 30, 60):
        for family in ("ROC", "MA", "STD", "MAX", "MIN", "QTLU", "QTLD", "RSV", "CORR", "CORD",
                       "CNTP", "CNTN", "CNTD", "SUMP", "SUMN", "SUMD", "VMA", "VSTD", "WVMA",
                       "VSUMP", "VSUMN", "VSUMD"):
            assert f"{family}{d}" in names, f"missing {family}{d}"
    for kbar in ("KMID", "KLEN", "KMID2", "KUP", "KUP2", "KLOW", "KLOW2", "KSFT", "KSFT2"):
        assert kbar in names
    for price in ("OPEN0", "HIGH0", "LOW0", "VWAP0"):
        assert price in names
    for vol in ("VOLUME0", "VOLUME1", "VOLUME2", "VOLUME3", "VOLUME4"):
        assert vol in names
    # 主动排除的滚动回归/极值下标家族不在场
    for excluded in ("BETA5", "RSQR5", "RESI5", "RANK5", "IMAX5", "IMIN5", "IMXD5"):
        assert excluded not in names


def _series() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "symbol": ["a"] * 5,
            "date": list(range(5)),
            "open": [10.0, 11.0, 12.0, 13.0, 14.0],
            "high": [12.0, 13.0, 14.0, 15.0, 16.0],
            "low": [9.0, 10.0, 11.0, 12.0, 13.0],
            "close": [11.0, 12.0, 13.0, 14.0, 15.0],
            "volume": [100.0, 200.0, 300.0, 400.0, 500.0],
            "amount": [110_000.0, 240_000.0, 390_000.0, 560_000.0, 750_000.0],
        }
    )


def _eval(name: str) -> list:
    expr = next(f.expression for f in build_alpha158() if f.name == name)
    return _series().select(compile_factor(expr).alias("f")).get_column("f").to_list()


def test_kmid_kup_klow_pointwise_semantics() -> None:
    # 第 1 日: open=11 high=13 low=10 close=12 (用第 2 行, 索引 1)
    kmid = _eval("KMID")
    assert kmid[1] == (12.0 - 11.0) / 11.0
    kup = _eval("KUP")
    assert kup[1] == (13.0 - max(11.0, 12.0)) / 11.0
    klow = _eval("KLOW")
    assert klow[1] == (min(11.0, 12.0) - 10.0) / 11.0

def test_vwap_uses_hand_unit_correction() -> None:
    vwap = _eval("VWAP0")
    # amount(元)/(volume(手)x100)/close; 1e-12 护栏带来浮点尾差
    assert vwap[0] == pytest.approx(1.0, abs=1e-12)


def test_roc_rsv_cntp_partial_window_semantics() -> None:
    # ROC5 = ref(close,5)/close: 序列仅 5 行 → 全 None (lag 无值)
    roc5 = _eval("ROC5")
    assert all(v is None for v in roc5)
    # RSV5 无 ref: min_samples=1 下部分窗口即可计算, 首行即有值
    rsv5 = _eval("RSV5")
    assert rsv5[0] is not None
    # 手算索引 2: (close-min(low 可用))/(max(high 可用)-min(low 可用))
    lo = min(9.0, 10.0, 11.0)
    hi = max(12.0, 13.0, 14.0)
    assert rsv5[2] == pytest.approx((13.0 - lo) / (hi - lo + 1e-12))
    # CNTP5: 索引 0 的 ref(close,1) 为 null → null; 连涨日 → 1.0
    cntp5 = _eval("CNTP5")
    assert cntp5[0] is None
    assert all(abs(v - 1.0) < 1e-9 for v in cntp5[1:])
    cntd5 = _eval("CNTD5")
    assert all(abs(v - 1.0) < 1e-9 for v in cntd5[1:])


def test_provenance_is_complete() -> None:
    meta = provenance()
    assert meta["source"].startswith("microsoft/qlib")
    assert meta["license"] == "MIT"
    assert "loader.py" in meta["url"]
