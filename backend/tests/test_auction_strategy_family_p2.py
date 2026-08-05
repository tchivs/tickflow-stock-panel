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
    if with_turnover:
        return pl.DataFrame({
            "symbol": ["600101", "600102", "600103", "600104", "600105"],
            "open_gap": [0.03, 0.03, 0.03, 0.01, 0.03],
            "auction_volume_ratio": [2.0, 1.0, 2.0, 2.0, 2.0],
            "auction_amount": [3_000_000, 3_000_000, 500_000, 3_000_000, 3_000_000],
            "turnover_rate": [0.05, 0.05, 0.05, 0.05, 0.01],
        })
    return pl.DataFrame({
        "symbol": ["600101", "600102", "600103", "600104"],
        "open_gap": [0.03, 0.03, 0.03, 0.01],
        "auction_volume_ratio": [2.0, 1.0, 2.0, 2.0],
        "auction_amount": [3_000_000, 3_000_000, 500_000, 3_000_000],
    })



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


# ================================================================
# STRAT-09: 盘中确认 (auction_intraday_confirm) — 截断 + time_factor + fail-closed
# ================================================================


def _intraday_daily_frame() -> pl.DataFrame:
    """盘中确认日线初筛 fixture: 含 auction_volume 通过引擎 requires_auction_data 短路,
    判定完全由 pre_open 可算列 open_gap 决定 (EOD 列缺席不参与)。"""
    return pl.DataFrame({
        "symbol": ["600301", "600302"],
        "open_gap": [0.03, 0.03],
        "auction_volume": [1_000_000, 1_000_000],
    })


def test_intraday_truncation(tmp_path, monkeypatch):
    """引擎单点截断: minute_confirm 只收到 <= evaluation_time=09:45 的 bar; 池成员只来自前 4 bar。
    (T-21-01 "确认时刻之后无输入" 回归)"""
    from app.strategy.builtin import auction_intraday_confirm

    times = [dt_time(9, 30), dt_time(9, 35), dt_time(9, 40), dt_time(9, 45),
             dt_time(9, 50), dt_time(10, 0)]
    frame = _minute_frame(["600301", "600302"], times)
    _write_minute_partition(tmp_path, date(2026, 8, 4), frame)

    orig = auction_intraday_confirm.minute_confirm

    def asserting(df_minute, params):
        if not df_minute.is_empty():
            assert df_minute["datetime"].max().time() <= dt_time(9, 45)
        return orig(df_minute, params)

    monkeypatch.setattr(auction_intraday_confirm, "minute_confirm", asserting)

    # 直接喂未截断帧 (含 10:00 bar) → 断言触发, 证明门禁有效
    with pytest.raises(AssertionError):
        asserting(frame, {})

    # 经引擎: 单点截断后断言静默, 池只来自 09:45 及之前 bar 可达的 symbol
    engine = _engine(minute_loader=lambda syms, d: pl.read_parquet(
        tmp_path / "kline_minute" / f"date={d.isoformat()}" / "part.parquet"))
    result = _run_auction(engine, "auction_intraday_confirm", _intraday_daily_frame())
    assert result.total == 2


def test_time_factor():
    """eval=09:45 → elapsed=15 → time_factor=16.0; minute_confirm 的 volume_scale == cum * 16.0 (T-21-05)."""
    from app.market_time import trading_minutes_elapsed_from_dt
    from app.strategy.builtin import auction_intraday_confirm

    elapsed = trading_minutes_elapsed_from_dt(datetime.combine(date(2026, 8, 4), dt_time(9, 45)))
    assert elapsed == pytest.approx(15.0)
    assert 240.0 / elapsed == pytest.approx(16.0)

    frame = _minute_frame(
        ["600301"], [dt_time(9, 30), dt_time(9, 35), dt_time(9, 40), dt_time(9, 45)]
    )
    out = auction_intraday_confirm.minute_confirm(frame, {})
    row = out.filter(pl.col("symbol") == "600301").to_dicts()[0]
    assert row["volume_scale"] == pytest.approx(float(frame["volume"].sum()) * 16.0)


def test_intraday_minute_absent_empty():
    """minute_confirm_required=True + 空分钟帧 → 空池 (fail-closed)."""
    engine = _engine(minute_loader=lambda syms, d: pl.DataFrame())
    result = _run_auction(engine, "auction_intraday_confirm", _intraday_daily_frame())
    assert result.total == 0


def test_intraday_prefilter_no_eod():
    """日线初筛只认 open_gap (pre_open 可算列); filter 段无 EOD 列引用;
    fixture 缺 EOD 列时池判定完全由 open_gap 决定。"""
    from app.strategy.builtin import auction_intraday_confirm

    text = (_BUILTIN_DIR / "auction_intraday_confirm.py").read_text(encoding="utf-8")
    filter_src = _filter_body(text)
    for col in _FORBIDDEN_EOD_COLS:
        assert not re.search(rf'pl\.col\("{col}"\)', filter_src), \
            f"auction_intraday_confirm.py filter 段禁引用 EOD 列 {col}"

    df = pl.DataFrame({"symbol": ["600301", "600302"], "open_gap": [0.03, 0.01]})
    hits = set(df.filter(auction_intraday_confirm.filter(df, {})).get_column("symbol"))
    assert hits == {"600301"}


# ================================================================
# P2 评分权重 + STRAT-03 注册回归 (与 21-01 的 P1 同形测试互补)
# ================================================================


def test_p2_scoring_weights_sum_to_one():
    """P2 三策略多因子评分权重和恒为 1.0 (PITFALL #7)。"""
    from app.strategy.builtin import auction_allround, auction_intraday_confirm, t1_flash

    for strat in (auction_allround, t1_flash, auction_intraday_confirm):
        assert sum(strat.META["scoring"].values()) == pytest.approx(1.0)


def _fake_repo(tmp_path):
    """最小 repo 桩: 仅提供 strategies 端点用到的 store.data_dir。"""
    from types import SimpleNamespace

    return SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))


def _screener_client(tmp_path):
    """最小 FastAPI + screener.router + 真实 builtin 引擎, 无网络无真实数据湖。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import screener as screener_api

    app = FastAPI()
    app.include_router(screener_api.router)
    app.state.repo = _fake_repo(tmp_path)
    app.state.strategy_engine = _engine()
    return TestClient(app)


def test_no_third_registry_p2(tmp_path):
    """STRAT-03 回归: P2 三 id 仅经 builtin 自动发现; PRESET 零碰撞; strategies API 恰好一次。"""
    engine = _engine()
    listed = {m["id"]: m for m in engine.list_strategies()}
    for sid in _P2_IDS:
        assert sid in listed, f"{sid} 必须由 engine 从 strategy/builtin 自动发现"
        assert listed[sid]["source"] == "builtin"

    from app.services.screener import PRESET_STRATEGIES

    for sid in _P2_IDS:
        assert sid not in PRESET_STRATEGIES

    client = _screener_client(tmp_path)
    resp = client.get("/api/screener/strategies?asset_type=stock")
    assert resp.status_code == 200
    presets = resp.json()["presets"]
    for sid in _P2_IDS:
        entries = [p for p in presets if p["id"] == sid]
        assert len(entries) == 1, f"{sid} 应恰好出现一次, 实际 {len(entries)}"
        assert entries[0]["source"] == "builtin"
    p2_files = {f"{sid}.py" for sid in _P2_IDS}
    for err in resp.json().get("load_errors", []):
        assert err.get("file") not in p2_files
