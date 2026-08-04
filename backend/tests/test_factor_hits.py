"""STRAT-02 关联因子 — 纯函数聚合 fixture 测试 (Task 1)。

Threat T-17-05: hit_factors 只由服务端 rows 成员关系决定, 不合成、不受客户端影响。
重叠股票池 fixture 锁定"交叉共振"原语: 一个标的同时被两个策略命中时,
它的 hit_factors 携带两个策略的显示名。
"""
from __future__ import annotations

from app.strategy.factor_hits import (
    HIT_FACTORS_COLUMN,
    attach_factor_hits,
    build_factor_hits,
)


def _overlap_results() -> dict[str, dict]:
    """strat_a 命中 X/Y, strat_b 命中 Y/Z — Y 是交叉共振标地。"""
    return {
        "strat_a": {"rows": [{"symbol": "X"}, {"symbol": "Y"}]},
        "strat_b": {"rows": [{"symbol": "Y"}, {"symbol": "Z"}]},
    }


def _overlap_name_for(sid: str) -> str:
    return {"strat_a": "竞价多头", "strat_b": "盘前强势量化"}[sid]


def test_build_factor_hits_overlap_aggregation():
    """重叠标地 Y 携带两个显示名 (交叉共振原语)。"""
    hits = build_factor_hits(_overlap_results(), name_for=_overlap_name_for)
    assert hits == {
        "X": ["竞价多头"],
        # 码点排序: 盘(U+76D8) < 竞(U+7ADE), 故 盘前强势量化 在前
        "Y": ["盘前强势量化", "竞价多头"],
        "Z": ["盘前强势量化"],
    }


def test_build_factor_hits_default_resolver_is_identity():
    """name_for=None 时显示名退化为策略 id, 排序确定。"""
    hits = build_factor_hits(_overlap_results(), name_for=None)
    assert hits == {
        "X": ["strat_a"],
        "Y": ["strat_a", "strat_b"],
        "Z": ["strat_b"],
    }


def test_build_factor_hits_deterministic_order():
    """同输入两次结果一致; 策略以逆序添加时显示名仍按码点排序。"""
    results = _overlap_results()
    first = build_factor_hits(results, name_for=_overlap_name_for)
    reversed_results = {
        "strat_b": results["strat_b"],
        "strat_a": results["strat_a"],
    }
    second = build_factor_hits(reversed_results, name_for=_overlap_name_for)
    assert first == second
    assert list(first["Y"]) == sorted(first["Y"])


def test_build_factor_hits_symbol_with_no_hits_absent():
    """零命中标的不出现在结果 dict 里 (无合成命中)。"""
    results = {"strat_a": {"rows": [{"symbol": "X"}]}}
    hits = build_factor_hits(results, name_for=_overlap_name_for)
    assert "Z" not in hits
    assert "Y" not in hits
    assert hits == {"X": ["竞价多头"]}


def test_attach_factor_hits_adds_column_without_mutation():
    """附加列不改输入; 无命中/无 symbol 的行得到 []。"""
    rows = [
        {"symbol": "X", "close": 10.0},
        {"symbol": "Q", "close": 11.0},
        {"close": 5.0},  # 无 symbol 键
    ]
    original = [dict(r) for r in rows]
    hits = {"X": ["竞价多头"]}

    out = attach_factor_hits(rows, hits)

    assert out[0][HIT_FACTORS_COLUMN] == ["竞价多头"]
    assert out[1][HIT_FACTORS_COLUMN] == []
    assert out[2][HIT_FACTORS_COLUMN] == []
    # 输入不变, 且未被加上 hit_factors 列
    assert rows == original
    assert all(HIT_FACTORS_COLUMN not in r for r in rows)
    # 返回的是新 dict, 不是输入行的引用
    assert out[0] is not rows[0]
