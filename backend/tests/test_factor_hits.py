"""STRAT-02 关联因子 — 纯函数聚合 fixture + screener run_all API 回归。

Threat T-17-05: hit_factors 只由服务端 rows 成员关系决定, 不合成、不受客户端影响。
重叠股票池 fixture 锁定"交叉共振"原语: 一个标的同时被两个策略命中时,
它的 hit_factors 携带两个策略的显示名。
Threat T-17-06: 显示名来自引擎 META, 未知 id 退化为策略 id (绝不 500)。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import polars as pl

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


# ================================================================
# screener run_all API 回归 (Task 2)
# ================================================================


class _FakeRepo:
    """最小 repo 桩 (与 test_screener_etf._FakeRepo 同型)。"""

    def __init__(self, data_dir, enriched, latest, instruments=None):
        self.store = SimpleNamespace(data_dir=data_dir)
        self._enriched = enriched
        self._latest = latest
        self._instruments = instruments if instruments is not None else pl.DataFrame()

    def get_enriched_latest_asset(self, asset_type):
        return self._enriched, self._latest

    def get_instruments_asset(self, asset_type):
        return self._instruments

    def get_enriched_history(self, target_date, lookback_days):
        return None


def _write_canned_strategy(d: Path, sid: str, name: str, min_change: float) -> None:
    """写入一个自包含的 canned builtin 策略文件 (无外部依赖)。"""
    (d / f"{sid}.py").write_text(
        f'''"""canned {sid} for factor_hits regression (hermetic)."""
import polars as pl

META = {{
    "id": "{sid}",
    "name": "{name}",
    "description": "canned",
    "tags": [],
    "params": [],
    "scoring": {{}},
    "order_by": "change_pct",
    "descending": True,
    "limit": 100,
}}

BASIC_FILTER = {{"enabled": False}}


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return pl.col("change_pct") > {min_change}
''',
        encoding="utf-8",
    )


def test_run_all_rows_carry_hit_factors(tmp_path):
    """T-17-05/T-17-06: run_all 每行附加 hit_factors, total/as_of 不变。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import screener as screener_api
    from app.strategy.engine import StrategyEngine

    strat_dir = tmp_path / "strategies"
    strat_dir.mkdir()
    # change_pct: 000001=5% (双策略命中), 600000=3% (仅 strat_a),
    # 000002=1.2% / 300001=0.5% (不被任一策略命中)
    _write_canned_strategy(strat_dir, "strat_a", "策略Alpha", 0.02)
    _write_canned_strategy(strat_dir, "strat_b", "策略Beta", 0.04)

    as_of = date(2026, 8, 4)
    enriched = pl.DataFrame(
        {
            "symbol": ["000001", "600000", "000002", "300001"],
            "name": ["平安银行", "浦发银行", "万科A", "创业板票"],
            "date": [as_of] * 4,
            "close": [10.0, 11.0, 12.0, 13.0],
            "prev_close": [9.5, 10.6, 11.8, 12.9],
            "change_pct": [0.05, 0.03, 0.012, 0.005],
            "amount": [5e8, 6e8, 7e8, 8e8],
        }
    )
    instruments = pl.DataFrame(
        {
            "symbol": ["000001", "600000", "000002", "300001"],
            "name": ["平安银行", "浦发银行", "万科A", "创业板票"],
        }
    )

    engine = StrategyEngine(
        enriched_loader=lambda _d: pl.DataFrame(),
        strategy_dirs=[strat_dir],
    )
    repo = _FakeRepo(tmp_path, enriched, as_of, instruments)

    app = FastAPI()
    app.include_router(screener_api.router)
    app.state.repo = repo
    app.state.strategy_engine = engine

    resp = TestClient(app).post(
        "/api/screener/run_all",
        json={"as_of": "2026-08-04", "strategy_ids": ["strat_a", "strat_b"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["as_of"] == "2026-08-04"

    results = body["results"]
    assert set(results.keys()) == {"strat_a", "strat_b"}
    ra, rb = results["strat_a"], results["strat_b"]

    # 向后兼容: total/as_of 保持原值
    assert ra["as_of"] == "2026-08-04"
    assert rb["as_of"] == "2026-08-04"
    assert ra["total"] == 2
    assert rb["total"] == 1

    both = sorted(["策略Alpha", "策略Beta"])
    # strat_a: 000001 (双命中) + 600000 (仅 strat_a)
    rows_a = {r["symbol"]: r for r in ra["rows"]}
    assert set(rows_a) == {"000001", "600000"}
    assert rows_a["000001"][HIT_FACTORS_COLUMN] == both
    assert rows_a["600000"][HIT_FACTORS_COLUMN] == ["策略Alpha"]

    # strat_b: 000001 (双命中) — 与 strat_a 的 000001 行携带完全相同的两个名字
    rows_b = {r["symbol"]: r for r in rb["rows"]}
    assert set(rows_b) == {"000001"}
    assert rows_b["000001"][HIT_FACTORS_COLUMN] == both

    # 未被任一策略命中的 symbol 不在响应里
    seen = set(rows_a) | set(rows_b)
    assert "000002" not in seen
    assert "300001" not in seen
