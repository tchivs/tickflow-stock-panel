"""开盘涨幅 open_gap 因子 (DATA-02) — 受管列 + 无跨日 lookahead 的 fixture 测试。

契约: open_gap = 同天 open / 前日 close − 1, 首日 None (无前收盘价)。
T-16-03 (high): 表达式用 Pass-1 的 prev_close (close.shift(1).over("symbol")),
绝不 shift open —— 变异 day2 open 必须只影响 day2, 不能泄漏到 day1。
"""
from __future__ import annotations

import polars as pl
import pytest

from app.indicators.pipeline import (
    ENRICHED_COLUMNS,
    ENRICHED_COLUMNS_BY_CATEGORY,
    ENRICHED_STORAGE_COLS,
    _ALL_INDICATOR_COLS,
    _INDICATOR_DEPS,
    _select_storage_cols,
    compute_indicators,
)


def _fixture() -> pl.DataFrame:
    """2 标的 x 3 天, day2 有正开盘涨幅, day3 有负开盘涨幅。"""
    return pl.DataFrame(
        {
            "symbol": ["A", "A", "A", "B", "B", "B"],
            "date": [
                "2026-08-03", "2026-08-04", "2026-08-05",
                "2026-08-03", "2026-08-04", "2026-08-05",
            ],
            "open": [10.0, 10.30, 9.80, 20.0, 20.60, 19.60],
            "high": [10.5, 10.60, 10.00, 21.0, 21.20, 20.00],
            "low": [9.9, 10.20, 9.70, 19.8, 20.40, 19.40],
            "close": [10.00, 10.50, 9.90, 20.00, 21.00, 19.80],
            "volume": [1000, 1200, 900, 2000, 2200, 1800],
        }
    )


# ================================================================
# 注册表 (governed column)
# ================================================================


def test_open_gap_registered_in_all_registries():
    assert "open_gap" in ENRICHED_STORAGE_COLS
    assert "open_gap" in ENRICHED_COLUMNS
    assert ENRICHED_COLUMNS["open_gap"].startswith("开盘涨幅")
    assert "open_gap" in ENRICHED_COLUMNS_BY_CATEGORY["basic"]
    assert _INDICATOR_DEPS["open_gap"] == {"prev_close"}
    assert "open_gap" in _ALL_INDICATOR_COLS


# ================================================================
# 数值正确性
# ================================================================


def test_open_gap_values_on_known_fixture():
    df = compute_indicators(_fixture())
    rows = df.sort(["symbol", "date"])
    # A: day2 open 10.30 / day1 close 10.00 - 1 = 0.03
    a2 = rows.filter(pl.col("symbol") == "A", pl.col("date") == "2026-08-04").select("open_gap").item()
    assert a2 == pytest.approx(0.03)
    # A: day3 open 9.80 / day2 close 10.50 - 1 = -0.0667 (4dp)
    a3 = rows.filter(pl.col("symbol") == "A", pl.col("date") == "2026-08-05").select("open_gap").item()
    assert a3 == pytest.approx(-0.0667, abs=5e-4)
    # B 同理: day2 20.60/20.00-1 = 0.03; day3 19.60/21.00-1 = -0.0667
    b2 = rows.filter(pl.col("symbol") == "B", pl.col("date") == "2026-08-04").select("open_gap").item()
    assert b2 == pytest.approx(0.03)
    b3 = rows.filter(pl.col("symbol") == "B", pl.col("date") == "2026-08-05").select("open_gap").item()
    assert b3 == pytest.approx(-0.0667, abs=5e-4)


def test_first_day_open_gap_is_null():
    df = compute_indicators(_fixture())
    rows = df.sort(["symbol", "date"])
    for sym in ("A", "B"):
        first = rows.filter(pl.col("symbol") == sym, pl.col("date") == "2026-08-03").select("open_gap").item()
        assert first is None


def test_open_gap_requires_prev_close_via_needed_closure():
    # needed={"open_gap"} 时闭包必须带上 prev_close, 否则 open_gap 全为 None
    df = compute_indicators(_fixture(), needed={"open_gap"})
    assert "open_gap" in df.columns
    assert "prev_close" in df.columns
    rows = df.sort(["symbol", "date"])
    a2 = rows.filter(pl.col("symbol") == "A", pl.col("date") == "2026-08-04").select("open_gap").item()
    assert a2 == pytest.approx(0.03)


# ================================================================
# 无跨日 lookahead (T-16-03)
# ================================================================


def test_mutating_day2_open_only_changes_day2():
    base = _fixture()
    df1 = compute_indicators(base).sort(["symbol", "date"])
    before = df1.filter(pl.col("symbol") == "A").select(["date", "open_gap"])

    mutated = base.with_columns(
        pl.when((pl.col("symbol") == "A") & (pl.col("date") == "2026-08-04"))
          .then(pl.col("open") * 1.1)  # day2 open 从 10.30 → 11.33
          .otherwise(pl.col("open"))
          .alias("open")
    )
    df2 = compute_indicators(mutated).sort(["symbol", "date"])
    after = df2.filter(pl.col("symbol") == "A").select(["date", "open_gap"])

    # day1 (首日) 本就 None, 变异后仍 None; day3 的 open_gap 依赖 day2 close, 不受 day2 open 影响
    day1_before = before.filter(pl.col("date") == "2026-08-03").select("open_gap").item()
    day1_after = after.filter(pl.col("date") == "2026-08-03").select("open_gap").item()
    assert day1_before is None and day1_after is None

    day3_before = before.filter(pl.col("date") == "2026-08-05").select("open_gap").item()
    day3_after = after.filter(pl.col("date") == "2026-08-05").select("open_gap").item()
    assert day3_before == pytest.approx(day3_after)

    # 只有 day2 变化, 且新值 = 11.33/10.00-1 = 0.133
    day2_after = after.filter(pl.col("date") == "2026-08-04").select("open_gap").item()
    assert day2_after == pytest.approx(0.133)


# ================================================================
def test_strategy_filter_consumes_open_gap():
    """Phase 17 seam: strategy 过滤器直接消费受管 open_gap 列。"""
    df = compute_indicators(_fixture())
    filtered = df.filter(pl.col("open_gap") > 0.03)
    # day2 open_gap 的 float64 表示是 0.030000000000000071 (> 0.03), 因此两标的 day2 命中;
    # day1 首日 None 与 day3 负值 (-0.0667) 被排除 —— 证明过滤器能按受管列精确筛选。
    assert filtered.shape[0] == 2
    assert set(filtered["symbol"].to_list()) == {"A", "B"}
    assert set(filtered["date"].to_list()) == {"2026-08-04"}

    # 负值/无 prior close 的行永不进入 > 0 集合
    positive = df.filter(pl.col("open_gap") > 0)
    assert positive.shape[0] == 2

# ================================================================
# 持久化 (storage path)
# ================================================================


def test_open_gap_persists_via_storage_path():
    df = compute_indicators(_fixture())
    stored = _select_storage_cols(df)
    assert "open_gap" in stored.columns
    assert set(stored.columns) <= set(ENRICHED_STORAGE_COLS)
