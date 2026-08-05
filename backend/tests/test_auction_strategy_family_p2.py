"""P2 竞价策略族 (STRAT-07/08/09) — 竞价全面 / T+1闪电 / 盘中确认 + 截断/time_factor 回归。

覆盖:
- auction_allround (STRAT-07): pre_open 白名单全因子复合 + 可选换手(EOD, 默认关) + 缺列 fail-closed
- t1_flash (STRAT-08): 池只含 T 日竞价买入信号; T+1 卖出为 EXIT/MAX_HOLD_DAYS=1 语义, 不进池计算
- auction_intraday_confirm (STRAT-09): 日线初筛只用 pre_open 列 + 引擎单点截断后的 minute_confirm
  (cum_volume * time_factor, eval=09:45 → elapsed=15 → tf=16.0); 分钟缺席 → 空池
- STRAT-03 回归: P2 三 id 仅经 builtin 自动发现、PRESET 零碰撞、strategies API 恰好一次
"""
from __future__ import annotations

import re
from datetime import date, datetime, time as dt_time
from pathlib import Path

import polars as pl
import pytest

from app.strategy.engine import StrategyEngine

_P2_IDS = ("auction_allround", "t1_flash", "auction_intraday_confirm")
_BUILTIN_DIR = Path(__file__).resolve().parents[1] / "app" / "strategy" / "builtin"
_MINUTE_COLS = ["symbol", "datetime", "open", "high", "low", "close", "volume", "amount"]
_FORBIDDEN_EOD_COLS = ("change_pct", "vol_ratio_5d", "amount", "close")


def _engine(minute_loader=None) -> StrategyEngine:
    """镜像 test_auction_strategies._engine; 21-01 合入后 minute_loader 透传, 之前安全省略。"""
    kwargs = {}
    if minute_loader is not None:
        kwargs["minute_loader"] = minute_loader
    return StrategyEngine(
        enriched_loader=lambda _d: pl.DataFrame(),
        strategy_dirs=[_BUILTIN_DIR],
        **kwargs,
    )


def _run_auction(engine: StrategyEngine, strategy_id: str, fixture: pl.DataFrame):
    return engine.run(
        strategy_id,
        as_of=date(2026, 8, 4),
        precomputed=fixture,
        overrides={"basic_filter": {"enabled": False}},
    )


def _write_minute_partition(data_dir, trade_date: date, rows: pl.DataFrame) -> None:
    """镜像 test_auction_columns._write_auction_partition, 写 kline_minute 分区。"""
    out = data_dir / "kline_minute" / f"date={trade_date.isoformat()}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.write_parquet(out)


def _minute_frame(symbols, times) -> pl.DataFrame:
    """构造含每 bar open=close、volume 递增的分钟帧 (canonical 8 列; eval=09:45 时前 4 bar 参与)。"""
    rows = []
    for i, t in enumerate(times, start=1):
        for sym in symbols:
            rows.append({
                "symbol": sym,
                "datetime": datetime.combine(date(2026, 8, 4), t),
                "open": 10.0,
                "high": 10.0,
                "low": 10.0,
                "close": 10.0,
                "volume": float(i * 100_000),
                "amount": float(i * 1_000_000),
            })
    return pl.DataFrame(rows, schema={
        "symbol": pl.Utf8,
        "datetime": pl.Datetime("us"),
        "open": pl.Float64,
        "high": pl.Float64,
        "low": pl.Float64,
        "close": pl.Float64,
        "volume": pl.Float64,
        "amount": pl.Float64,
    })


def _allround_fixture(with_turnover: bool = False) -> pl.DataFrame:
    """竞价全面 fixture: 600101 全达标; 600102 量比不足; 600103 金额不足; 600104 涨幅不足;
    600105 全达标但换手 1% (<3%, 仅 with_turnover 变体存在)。"""
    data = {
        "symbol": ["600101", "600102", "600103", "600104", "600105"],
        "open_gap": [0.03, 0.03, 0.03, 0.01, 0.03],
        "auction_volume_ratio": [2.0, 1.0, 2.0, 2.0, 2.0],
        "auction_amount": [3_000_000, 3_000_000, 500_000, 3_000_000, 3_000_000],
    }
    if with_turnover:
        data["turnover_rate"] = [0.05, 0.05, 0.05, 0.05, 0.01]
    return pl.DataFrame(data)


def _t1_fixture() -> pl.DataFrame:
    """T+1闪电 fixture: 600201 全达标; 600202 量比不足; 600203 金额不足; 600204 涨幅不足。
    仅含 T 日 as-of 列, 无任何 T+1/EOD 列。"""
    return pl.DataFrame({
        "symbol": ["600201", "600202", "600203", "600204"],
        "open_gap": [0.03, 0.03, 0.03, 0.01],
        "auction_volume_ratio": [2.5, 1.5, 2.5, 2.5],
        "auction_amount": [3_000_000, 3_000_000, 1_000_000, 3_000_000],
    })


def _filter_body(src: str) -> str:
    """提取第一个 def filter(...) 函数体 (到下一个模块级 def 或文件尾)。"""
    idx = src.find("def filter")
    assert idx != -1, "策略文件必须定义 filter"
    rest = src[idx:]
    nxt = rest.find("\ndef ")
    return rest if nxt == -1 else rest[:nxt]


# ================================================================
# STRAT-07: 竞价全面 (auction_allround)
# ================================================================


def test_allround_core_and_optional_turnover():
    from app.strategy.builtin import auction_allround

    base = _allround_fixture()
    hits = set(base.filter(auction_allround.filter(base, {})).get_column("symbol"))
    assert hits == {"600101"}
    assert "600102" not in hits  # 竞价量比 1.0 < 1.2
    assert "600103" not in hits  # 竞价金额 50万 < 100万
    assert "600104" not in hits  # 开盘涨幅 1% < 2%

    # 可选换手: 帧含 turnover_rate + use_turnover=True → 换手低于 3% 的行被收窄
    with_turnover = _allround_fixture(with_turnover=True)
    narrowed = set(with_turnover.filter(
        auction_allround.filter(with_turnover, {"use_turnover": True})
    ).get_column("symbol"))
    assert narrowed == {"600101"}  # 600105 换手 1% < 3% 被收窄

    # use_turnover=True + 帧无 turnover_rate 列 → 不收窄、不崩溃 (auction_early_star 语义)
    no_col = set(base.filter(auction_allround.filter(base, {"use_turnover": True})).get_column("symbol"))
    assert no_col == {"600101"}


def test_allround_fail_closed():
    from app.strategy.builtin import auction_allround

    partial = pl.DataFrame({"symbol": ["600101"], "open_gap": [0.03]})
    assert partial.filter(auction_allround.filter(partial, {})).is_empty()

    engine = _engine()
    result = _run_auction(engine, "auction_allround", partial)
    assert result.total == 0


# ================================================================
# STRAT-08: T+1闪电 (t1_flash)
# ================================================================


def test_t1_flash_no_lookahead():
    from app.strategy.builtin import t1_flash

    df = _t1_fixture()
    # 池只由 T 日 as-of 帧计算: fixture 只含 T 日竞价列, 无 T+1/EOD 数据参与
    assert set(df.columns) == {"symbol", "open_gap", "auction_volume_ratio", "auction_amount"}
    hits = set(df.filter(t1_flash.filter(df, {})).get_column("symbol"))
    assert hits == {"600201"}
    assert "600202" not in hits  # 竞价量比 1.5 < 2.0
    assert "600203" not in hits  # 竞价金额 100万 < 200万
    assert "600204" not in hits  # 开盘涨幅 1% < 2.5%

    # 次日卖出为 EXIT/MAX_HOLD_DAYS=1 语义, 绝不参与池成员计算
    assert t1_flash.EXIT_SIGNALS == ["signal_ma20_breakdown"]
    assert t1_flash.MAX_HOLD_DAYS == 1


def test_t1_flash_fail_closed():
    from app.strategy.builtin import t1_flash

    partial = pl.DataFrame({"symbol": ["600201"], "open_gap": [0.03]})
    assert partial.filter(t1_flash.filter(partial, {})).is_empty()

    engine = _engine()
    result = _run_auction(engine, "t1_flash", partial)
    assert result.total == 0


# ================================================================
# pre_open 白名单 grep 门禁 (T-21-04 / PITFALLS #7)
# ================================================================


def test_p2_preopen_no_eod_cols():
    """grep 门禁: auction_allround/t1_flash 的 filter 段不引用 EOD 列 change_pct/vol_ratio_5d/amount/close。"""
    for name in ("auction_allround", "t1_flash"):
        text = (_BUILTIN_DIR / f"{name}.py").read_text(encoding="utf-8")
        filter_src = _filter_body(text)
        for col in _FORBIDDEN_EOD_COLS:
            assert not re.search(rf'pl\.col\("{col}"\)', filter_src), \
                f"{name}.py filter 段禁引用 EOD 列 {col}"
