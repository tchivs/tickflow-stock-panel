"""全量模拟 (full mode) 尾部执行回归测试。"""
from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from app.backtest.engine import BacktestEngine, MatcherConfig


def _panel_with_tail(symbols: list[str], n_data_days: int) -> pl.DataFrame:
    start = date(2024, 1, 1)
    rows = []
    for sym in symbols:
        for i in range(n_data_days):
            px = 10.0 + i
            rows.append({
                "symbol": sym,
                "date": start + timedelta(days=i),
                "open": px,
                "high": px,
                "low": px,
                "close": px,
                "volume": 100_000,
                "signal_limit_up": False,
                "signal_limit_down": False,
            })
    return pl.DataFrame(rows).sort(["symbol", "date"])


def test_full_simulation_executes_signal_at_tail():
    """信号集中在正式区间最后一天时, tail 数据应允许次日开盘买入并按策略退出。"""
    n_days = 6
    panel = _panel_with_tail(["A"], n_days + 3)

    start = date(2024, 1, 1)
    end = start + timedelta(days=n_days - 1)
    entry_vals = []
    for row in panel.select(["symbol", "date"]).iter_rows(named=True):
        entry_vals.append(row["date"] == end)
    entry_mask = pl.Series(entry_vals, dtype=pl.Boolean)
    exit_mask = pl.Series([False] * len(panel), dtype=pl.Boolean)

    result = BacktestEngine(repo=None).simulate_independent_candidates(  # type: ignore[arg-type]
        panel,
        entry_mask,
        exit_mask,
        MatcherConfig(matching="open_t+1", fees_pct=0, slippage_bps=0, max_hold_days=2),
    )

    assert not result.stats.get("error"), f"unexpected error: {result.stats.get('error')}"
    assert result.stats.get("full_kind") == "candidate_execution"
    assert result.stats.get("n_candidates") == 1
    assert result.stats.get("n_trades") == 1
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_signal_date == str(end)
    assert trade.entry_date == str(end + timedelta(days=1))
    assert trade.exit_reason == "max_hold"


def test_full_close_t_entry_trailing_stop_ignores_pre_entry_high():
    """全量模式 close_t 建仓: 信号日收盘成交, 当日盘中高点发生在建仓之前,
    不应计入移损峰值 (否则 12 的虚假峰值 → 11.4 移损线, 次日开盘 11 即触发)。"""
    start = date(2024, 1, 1)
    rows = []
    for i in range(4):
        if i == 0:
            o, h, l, c = 10.0, 12.0, 9.8, 11.0
        elif i == 1:
            o, h, l, c = 11.0, 11.0, 10.4, 10.4
        else:
            o = h = l = c = 10.4
        rows.append({
            "symbol": "A",
            "date": start + timedelta(days=i),
            "open": o, "high": h, "low": l, "close": c,
            "volume": 100_000,
            "signal_limit_up": False,
            "signal_limit_down": False,
        })
    panel = pl.DataFrame(rows)

    entry_mask = pl.Series([True, False, False, False], dtype=pl.Boolean)
    exit_mask = pl.Series([False] * 4, dtype=pl.Boolean)

    result = BacktestEngine(repo=None).simulate_independent_candidates(  # type: ignore[arg-type]
        panel,
        entry_mask,
        exit_mask,
        MatcherConfig(matching="close_t", fees_pct=0, slippage_bps=0, trailing_stop_pct=0.05),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "trailing_stop"
    assert trade.exit_price == 10.45


def test_full_pending_signal_exit_does_not_bypass_stop_loss():
    """全量模式挂单待执行不清空风控: 信号离场被跌停挡住后, 次日跳空跌破止损线,
    应以止损价(开盘)成交, 而不是按挂单等到收盘。"""
    start = date(2024, 1, 1)
    rows = []
    for i in range(4):
        if i == 0:
            o = h = l = c = 10.0
            ld = False
        elif i == 1:
            o = h = l = c = 10.0
            ld = True   # 信号日一价跌停 → 收盘离场被挡, 挂单待执行
        elif i == 2:
            o, h, l, c = 8.5, 8.7, 8.4, 8.0   # 跳空跌破止损线 9.0
            ld = False
        else:
            o = h = l = c = 8.0
            ld = False
        rows.append({
            "symbol": "A",
            "date": start + timedelta(days=i),
            "open": o, "high": h, "low": l, "close": c,
            "volume": 100_000,
            "signal_limit_up": False,
            "signal_limit_down": ld,
        })
    panel = pl.DataFrame(rows)

    entry_mask = pl.Series([True, False, False, False], dtype=pl.Boolean)
    exit_mask = pl.Series([False, True, False, False], dtype=pl.Boolean)

    result = BacktestEngine(repo=None).simulate_independent_candidates(  # type: ignore[arg-type]
        panel,
        entry_mask,
        exit_mask,
        MatcherConfig(matching="close_t", fees_pct=0, slippage_bps=0, stop_loss_pct=0.1),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.exit_price == 8.5            # 开盘价成交, 而非收盘 8.0
    assert trade.blocked_exit_days == 1


def test_full_risk_exit_blocked_by_limit_down_counts_once():
    """全量模式风控触发当日被跌停挡住: blocked_exit_days 与 sell_limit_down 只计一次,
    不应再被随后的挂单出场重复计数。"""
    start = date(2024, 1, 1)
    rows = []
    for i in range(4):
        if i == 0:
            o = h = l = c = 10.0
            ld = False
        elif i == 1:
            o = h = l = c = 8.9   # 一价跌停, 跌破止损线 9.0, 但无法卖出
            ld = True
        else:
            o = h = l = c = 8.5
            ld = False
        rows.append({
            "symbol": "A",
            "date": start + timedelta(days=i),
            "open": o, "high": h, "low": l, "close": c,
            "volume": 100_000,
            "signal_limit_up": False,
            "signal_limit_down": ld,
        })
    panel = pl.DataFrame(rows)

    entry_mask = pl.Series([True, False, False, False], dtype=pl.Boolean)
    exit_mask = pl.Series([False] * 4, dtype=pl.Boolean)

    result = BacktestEngine(repo=None).simulate_independent_candidates(  # type: ignore[arg-type]
        panel,
        entry_mask,
        exit_mask,
        MatcherConfig(matching="close_t", fees_pct=0, slippage_bps=0, stop_loss_pct=0.1),
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.exit_reason == "stop_loss"
    assert trade.blocked_exit_days == 1
    assert result.stats["execution"]["sell_limit_down"] == 1


def test_full_trigger_signal_ids_resolve_at_signal_row():
    """全量模式 open_t+1 口径: 具体触发信号在「信号行」解析, 而非成交行。

    覆盖两类回归:
    - entry_idx 来自 np.flatnonzero 是 numpy.int64, _resolve_signal_id 必须能索引 polars;
    - open_t+1 下信号在成交日的前一行, 解析需回到 signal row (idx-1)。
    """
    start = date(2024, 1, 1)
    rows = []
    for i in range(6):
        px = 10.0 + i
        rows.append({
            "symbol": "A",
            "date": start + timedelta(days=i),
            "open": px, "high": px, "low": px, "close": px,
            "volume": 100_000,
            "signal_limit_up": False,
            "signal_limit_down": False,
            "signal_buy": i == 0,      # day0 买入信号 → day1 开盘成交
            "signal_sell": i == 2,     # day2 卖出信号 → day3 开盘离场
        })
    panel = pl.DataFrame(rows)

    entry_mask = pl.Series(panel["signal_buy"], dtype=pl.Boolean)
    exit_mask = pl.Series(panel["signal_sell"], dtype=pl.Boolean)

    result = BacktestEngine(repo=None).simulate_independent_candidates(  # type: ignore[arg-type]
        panel,
        entry_mask,
        exit_mask,
        MatcherConfig(matching="open_t+1", fees_pct=0, slippage_bps=0),
        entry_signal_ids=["signal_buy"],
        exit_signal_ids=["signal_sell"],
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_signal_id == "signal_buy", trade
    assert trade.exit_reason == "signal"
    assert trade.exit_signal_id == "signal_sell", trade
    assert str(trade.entry_date) == str(start + timedelta(days=1))
    assert str(trade.exit_date) == str(start + timedelta(days=3))


def test_full_trigger_signal_ids_close_t_same_row():
    """全量模式 close_t 口径: 信号行 == 成交行, 具体触发信号在同一天解析。"""
    start = date(2024, 1, 1)
    rows = []
    for i in range(4):
        px = 10.0 + i
        rows.append({
            "symbol": "A",
            "date": start + timedelta(days=i),
            "open": px, "high": px, "low": px, "close": px,
            "volume": 100_000,
            "signal_limit_up": False,
            "signal_limit_down": False,
            "signal_buy": i == 0,
            "signal_sell": i == 1,
        })
    panel = pl.DataFrame(rows)

    entry_mask = pl.Series(panel["signal_buy"], dtype=pl.Boolean)
    exit_mask = pl.Series(panel["signal_sell"], dtype=pl.Boolean)

    result = BacktestEngine(repo=None).simulate_independent_candidates(  # type: ignore[arg-type]
        panel,
        entry_mask,
        exit_mask,
        MatcherConfig(matching="close_t", fees_pct=0, slippage_bps=0),
        entry_signal_ids=["signal_buy"],
        exit_signal_ids=["signal_sell"],
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_signal_id == "signal_buy", trade
    assert trade.exit_reason == "signal"
    assert trade.exit_signal_id == "signal_sell", trade
    assert str(trade.entry_date) == str(start)
    assert str(trade.exit_date) == str(start + timedelta(days=1))
