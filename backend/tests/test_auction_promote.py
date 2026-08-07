"""T-day 提审升湖 (SDC-02) — 撮合行过滤 / 单位映射 / gate fail-closed / 逐日累积幂等 / DATA-06 交叉验证。

Hermetic、零网络: 种子 staging 分区 + manifest + kline_daily 分区 (镜像
test_verify_auction_backfill `_seed_daily` 形态), 复用 write_auction_partitions
(555..565 谓词 + 存在性 crop + merge-upsert 幂等) 与 KlineRepository 真实现。

契约 (43-02-PLAN must_haves):
- 仅撮合行升湖: time∈09:25:00..09:25:59 ∧ num_trades>0 → sort(time) →
  unique(symbol, keep=first) → 单 symbol 单日单行; 虚拟快照行 (num_trades=0) 与
  09:25:01 回显行永不入 canonical。
- 单位映射: auction_volume = vol_hand×100 (股) / auction_amount = price×vol_hand×100
  (元, 闭合 22,639,818) / auction_virtual_price = price; num_trades 只进 manifest 元数据。
- 提审闸门 (Pitfall 6): manifest completeness.ok ∧ reconciliation.closed (当日 staging
  判定); 三拒 fail-closed 带 reason, 绝不静默。
- DATA-06: virtual_price == kline_daily.open (1e-6) 交叉验证; auction_unmatched_volume
  诚实缺列 (tick 源不可得) 绝不产出。

所有生产 import 放测试函数内 (repo 约定, 避免 collection 时导入 DuckDB 单例)。
"""
from __future__ import annotations

import json
from datetime import date, datetime

import polars as pl
import pytest

_DAY = date(2026, 8, 7)
_DAY_PREV = date(2026, 8, 6)
_SYMBOL_PREFIX = "SH600519"
_SYMBOL_SUFFIX = "600519.SH"
_MATCH_PRICE = 1308.66
_MATCH_VOL_HAND = 173
_MATCH_NUM_TRADES = 120
# 契约闭合: 173×100 股 / 173×100×1308.66 元 (live 实测, RESEARCH Pattern 3)
_AMOUNT_CLOSURE = 173 * 100 * 1308.66  # 22,639,818.0


def _tick_row(
    time: str,
    *,
    price: float = _MATCH_PRICE,
    vol_hand: int = _MATCH_VOL_HAND,
    num_trades: int = _MATCH_NUM_TRADES,
    symbol: str = _SYMBOL_PREFIX,
    trade_date: str = "20260807",
    buyorsell: int = 2,
) -> dict:
    """staging 10 列 TickBar 行 (43-01 契约逐字: symbol/trade_date/time/price/vol_hand/
    num_trades/buyorsell/source/fetched_at/ingested_at)。"""
    return {
        "symbol": symbol,
        "trade_date": trade_date,
        "time": time,
        "price": price,
        "vol_hand": vol_hand,
        "num_trades": num_trades,
        "buyorsell": buyorsell,
        "source": "eastmoney",
        "fetched_at": "2026-08-07T09:26:00+00:00",
        "ingested_at": "2026-08-07T09:26:01+00:00",
    }


def _window_rows(*, symbol: str = _SYMBOL_PREFIX, trade_date: str = "20260807") -> list[dict]:
    """代表性竞价窗口: 虚拟快照 (num_trades=0) + 09:25:00 撮合行 + 09:25:01 回显行
    (num_trades=0) + 09:25:04 同值重复撮合行 (num_trades=120)。"""
    return [
        _tick_row("09:15:07", num_trades=0, symbol=symbol, trade_date=trade_date),
        _tick_row("09:20:00", num_trades=0, symbol=symbol, trade_date=trade_date),
        _tick_row("09:24:58", num_trades=0, symbol=symbol, trade_date=trade_date),
        _tick_row("09:25:00", num_trades=_MATCH_NUM_TRADES, symbol=symbol, trade_date=trade_date),
        _tick_row("09:25:01", num_trades=0, symbol=symbol, trade_date=trade_date),  # 回显行
        _tick_row("09:25:04", num_trades=_MATCH_NUM_TRADES, symbol=symbol, trade_date=trade_date),  # 同值重复
    ]


def _seed_staging(data_dir, trade_date: date, rows: list[dict], manifest_patch: dict | None = None) -> None:
    """种子 staging 分区 + manifest (completeness/reconciliation 可由用例覆盖)。"""
    part = data_dir / "tick_staging" / f"date={trade_date.isoformat()}"
    part.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(part / "part.parquet")
    manifest = {
        "trade_date": trade_date.isoformat(),
        "captured_at": "2026-08-07T09:26:00+08:00",
        "pool_size": 1,
        "symbols_ok": [_SYMBOL_PREFIX],
        "symbols_failed": [],
        "completeness": {"ok": True},
        "reconciliation": {"status": "closed"},
    }
    if manifest_patch:
        manifest.update(manifest_patch)
    (part / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")


def _seed_daily(data_dir, trade_date: date, symbols: list[str], open_prices: dict | None = None) -> None:
    """kline_daily/date=* 分区 (symbol/open 列, 镜像 test_verify_auction_backfill `_seed_daily`)。"""
    open_prices = open_prices or {}
    part = data_dir / "kline_daily" / f"date={trade_date.isoformat()}"
    part.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({
        "symbol": list(symbols),
        "open": [float(open_prices.get(s, _MATCH_PRICE)) for s in symbols],
    }).write_parquet(part / "part.parquet")


@pytest.fixture
def repo_env(tmp_path, monkeypatch):
    """tmp 湖 + 真 KlineRepository (镜像 test_auction_sync repo_env 形态)。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    yield data_dir, KlineRepository(store)
    store.db.close()


def _stage_dir(data_dir, trade_date: date):
    return data_dir / "tick_staging" / f"date={trade_date.isoformat()}"


def _canonical_path(data_dir, trade_date: date):
    return data_dir / "kline_auction" / f"date={trade_date.isoformat()}" / "part.parquet"


# ================================================================
# Task 1 — promote_to_canonical 单 symbol 端到端 (撮合行过滤 + 单位映射 + gate)
# ================================================================


def test_promote_single_symbol_writes_canonical(repo_env, tmp_path):
    """撮合行升 canonical: 单行 (17300 股 / 22,639,818 元 / 1308.66), 09:25:00 naive,
    分区无 auction_unmatched_volume 列 (诚实缺列)。"""
    data_dir, repo = repo_env
    _seed_staging(data_dir, _DAY, _window_rows())

    from app.services.auction_promote import promote_to_canonical
    result = promote_to_canonical(_stage_dir(data_dir, _DAY), repo, _DAY)
    assert result["written"] == 1
    assert result["symbols"] == [_SYMBOL_SUFFIX]
    assert result["num_trades_by_symbol"] == {_SYMBOL_SUFFIX: _MATCH_NUM_TRADES}

    out = _canonical_path(data_dir, _DAY)
    assert out.exists()
    df = pl.read_parquet(out)
    assert df.height == 1
    row = df.row(0, named=True)
    assert row["symbol"] == _SYMBOL_SUFFIX
    assert row["auction_volume"] == 17300  # 173×100 股 (手→股 ×100, Pitfall 7)
    assert row["auction_amount"] == pytest.approx(_AMOUNT_CLOSURE)
    assert row["auction_virtual_price"] == pytest.approx(_MATCH_PRICE)
    assert row["datetime"] == datetime(2026, 8, 7, 9, 25, 0)  # 北京墙钟 naive
    assert "auction_unmatched_volume" not in df.columns
    assert not list((data_dir / "kline_auction").rglob("*.tmp"))


def test_promote_excludes_virtual_rows(repo_env, tmp_path):
    """虚拟快照行 (num_trades=0) + 09:25:01 回显行永不入 canonical; 09:25:04 同值
    重复行 dedupe → 单 symbol 单日单行 (written==1)。"""
    data_dir, repo = repo_env
    _seed_staging(data_dir, _DAY, _window_rows())

    from app.services.auction_promote import promote_to_canonical
    result = promote_to_canonical(_stage_dir(data_dir, _DAY), repo, _DAY)
    assert result["written"] == 1

    df = pl.read_parquet(_canonical_path(data_dir, _DAY))
    assert df.height == 1
    assert df["datetime"].to_list() == [datetime(2026, 8, 7, 9, 25, 0)]
    assert df["auction_volume"].to_list() == [17300]


def test_promote_gate_reconciliation_not_closed(repo_env, tmp_path):
    """reconciliation 非 closed (mismatch/pending/缺块) → 0 写 + reason, 不写湖不静默。"""
    data_dir, repo = repo_env
    for patch, reason in [
        ({"reconciliation": {"status": "mismatch"}}, "reconciliation_not_closed"),
        ({"reconciliation": {"status": "pending"}}, "reconciliation_not_closed"),
        ({"reconciliation": {}}, "reconciliation_not_closed"),
    ]:
        _seed_staging(data_dir, _DAY, _window_rows(), manifest_patch=patch)
        from app.services.auction_promote import promote_to_canonical
        result = promote_to_canonical(_stage_dir(data_dir, _DAY), repo, _DAY)
        assert result["written"] == 0
        assert result["reason"] == reason
        lake = data_dir / "kline_auction"
        assert not list(lake.glob("date=*"))


def test_promote_gate_manifest_missing(repo_env, tmp_path):
    """manifest 缺失 → 0 + "manifest_missing" (fail-closed, 绝不静默写湖)。"""
    data_dir, repo = repo_env
    _seed_staging(data_dir, _DAY, _window_rows())
    (_stage_dir(data_dir, _DAY) / "manifest.json").unlink()

    from app.services.auction_promote import promote_to_canonical
    result = promote_to_canonical(_stage_dir(data_dir, _DAY), repo, _DAY)
    assert result["written"] == 0
    assert result["reason"] == "manifest_missing"
    assert not list((data_dir / "kline_auction").glob("date=*"))


def test_promote_gate_completeness_not_ok(repo_env, tmp_path):
    """completeness.ok != True → 0 + "capture_incomplete" (完整性未闭合不升湖)。"""
    data_dir, repo = repo_env
    _seed_staging(data_dir, _DAY, _window_rows(), manifest_patch={"completeness": {"ok": False}})

    from app.services.auction_promote import promote_to_canonical
    result = promote_to_canonical(_stage_dir(data_dir, _DAY), repo, _DAY)
    assert result["written"] == 0
    assert result["reason"] == "capture_incomplete"
    assert not list((data_dir / "kline_auction").glob("date=*"))


def test_promote_no_match_rows_writes_nothing(repo_env, tmp_path):
    """staging 全虚拟快照 (无 num_trades>0 行) → 0 + "no_match_rows", 不写湖。"""
    data_dir, repo = repo_env
    _seed_staging(data_dir, _DAY, [
        _tick_row("09:15:07", num_trades=0),
        _tick_row("09:24:58", num_trades=0),
    ])

    from app.services.auction_promote import promote_to_canonical
    result = promote_to_canonical(_stage_dir(data_dir, _DAY), repo, _DAY)
    assert result["written"] == 0
    assert result["reason"] == "no_match_rows"
    assert not list((data_dir / "kline_auction").glob("date=*"))


# ================================================================
# Task 2 — T-day 逐日累积 + 幂等重跑 (多日期驱动)
# ================================================================


def test_promote_trading_day_two_dates(repo_env, tmp_path):
    """两交易日逐日累积 → 两日分区均存在, 各 1 行 (自 T-day 起每交易日一分区)。"""
    data_dir, repo = repo_env
    _seed_staging(data_dir, _DAY_PREV, _window_rows(trade_date="20260806"))
    _seed_staging(data_dir, _DAY, _window_rows())

    from app.services.auction_promote import promote_trading_day
    result = promote_trading_day(repo, data_dir, [_DAY_PREV, _DAY])
    assert result["promoted_dates"] == ["2026-08-06", "2026-08-07"]
    assert result["skipped"] == []
    assert result["total_written"] == 2

    for d in (_DAY_PREV, _DAY):
        assert pl.read_parquet(_canonical_path(data_dir, d)).height == 1


def test_promote_rerun_idempotent(repo_env, tmp_path):
    """同参数重跑 → written==0 (全部已覆盖, merge-upsert keep=last) + 分区行数不变;
    manifest promoted==true。"""
    data_dir, repo = repo_env
    _seed_staging(data_dir, _DAY, _window_rows())

    from app.services.auction_promote import promote_to_canonical
    stage = _stage_dir(data_dir, _DAY)
    first = promote_to_canonical(stage, repo, _DAY)
    assert first["written"] == 1
    part = _canonical_path(data_dir, _DAY)
    assert pl.read_parquet(part).height == 1

    second = promote_to_canonical(stage, repo, _DAY)
    assert second["written"] == 0
    assert pl.read_parquet(part).height == 1  # 行数不变 (幂等)

    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("promoted") is True


def test_promote_missing_staging_skipped(repo_env, tmp_path):
    """列出的日期无 staging 分区 → 该日 skipped (reason staging_missing), 不写湖不报错。"""
    data_dir, repo = repo_env
    _seed_staging(data_dir, _DAY_PREV, _window_rows(trade_date="20260806"))

    from app.services.auction_promote import promote_trading_day
    result = promote_trading_day(repo, data_dir, [_DAY_PREV, _DAY])
    assert result["promoted_dates"] == ["2026-08-06"]
    assert result["skipped"] == [{"date": "2026-08-07", "reason": "staging_missing"}]
    assert result["total_written"] == 1
    assert not (data_dir / "kline_auction" / "date=2026-08-07").exists()


def test_promote_manifest_updates_promoted_block(repo_env, tmp_path):
    """提审后 manifest 增 promoted 块 (promoted/promoted_at/written/num_trades_by_symbol),
    旧键 (completeness/reconciliation) 保留, 无 .tmp 残留。"""
    data_dir, repo = repo_env
    _seed_staging(data_dir, _DAY, _window_rows())

    from app.services.auction_promote import promote_to_canonical
    stage = _stage_dir(data_dir, _DAY)
    promote_to_canonical(stage, repo, _DAY)

    manifest = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["promoted"] is True
    assert isinstance(manifest["promoted_at"], str) and "T" in manifest["promoted_at"]
    assert manifest["written"] == 1
    assert manifest["num_trades_by_symbol"] == {_SYMBOL_SUFFIX: _MATCH_NUM_TRADES}
    assert manifest["completeness"] == {"ok": True}  # 旧键保留
    assert manifest["reconciliation"] == {"status": "closed"}
    assert not list(stage.glob("*.tmp"))


# ================================================================
# Task 3 — DATA-06 映射 + 交叉验证 (virtual_price vs kline_daily.open 1e-6; unmatched 诚实缺列)
# ================================================================


def test_cross_validate_virtual_price_closed(repo_env, tmp_path):
    """kline_daily.open == 1308.66 (1e-6) → 每 symbol diff≈0, all_ok True (镜像 verify [4])。"""
    data_dir, repo = repo_env
    _seed_staging(data_dir, _DAY, _window_rows())
    _seed_daily(data_dir, _DAY, [_SYMBOL_SUFFIX], {_SYMBOL_SUFFIX: _MATCH_PRICE})

    from app.services.auction_promote import cross_validate_virtual_price, promote_to_canonical
    promote_to_canonical(_stage_dir(data_dir, _DAY), repo, _DAY)

    result = cross_validate_virtual_price(repo, _DAY)
    assert result["all_ok"] is True
    assert result["skipped"] == []
    assert len(result["checked"]) == 1
    row = result["checked"][0]
    assert row["symbol"] == _SYMBOL_SUFFIX
    assert row["virtual_price"] == pytest.approx(_MATCH_PRICE)
    assert row["kline_open"] == pytest.approx(_MATCH_PRICE)
    assert row["diff"] <= 1e-6
    assert row["ok"] is True


def test_cross_validate_virtual_price_drift_reported(repo_env, tmp_path):
    """kline_daily.open=1309.00 → diff=0.34 > 1e-6 → all_ok False + 逐 symbol 诚实报告
    (绝不吞/不猜)。"""
    data_dir, repo = repo_env
    _seed_staging(data_dir, _DAY, _window_rows())
    _seed_daily(data_dir, _DAY, [_SYMBOL_SUFFIX], {_SYMBOL_SUFFIX: 1309.00})

    from app.services.auction_promote import cross_validate_virtual_price, promote_to_canonical
    promote_to_canonical(_stage_dir(data_dir, _DAY), repo, _DAY)

    result = cross_validate_virtual_price(repo, _DAY)
    assert result["all_ok"] is False
    row = result["checked"][0]
    assert row["ok"] is False
    assert row["diff"] == pytest.approx(0.34, abs=1e-6)


def test_cross_validate_missing_daily_skipped(repo_env, tmp_path):
    """无 kline_daily 当日分区 → {"skipped": [symbols], "reason": "no_kline_daily"}
    诚实标注 (交叉验证以数据在场为准)。"""
    data_dir, repo = repo_env
    _seed_staging(data_dir, _DAY, _window_rows())

    from app.services.auction_promote import cross_validate_virtual_price, promote_to_canonical
    promote_to_canonical(_stage_dir(data_dir, _DAY), repo, _DAY)

    result = cross_validate_virtual_price(repo, _DAY)
    assert result["checked"] == []
    assert result["skipped"] == [_SYMBOL_SUFFIX]
    assert result["reason"] == "no_kline_daily"


def test_unmatched_volume_never_emitted(repo_env, tmp_path):
    """promote 后分区列集 == {symbol, datetime, auction_volume, auction_amount,
    auction_virtual_price} — 无 auction_unmatched_volume (tick 源无未匹配量字段,
    诚实缺列绝不 0 填)。"""
    data_dir, repo = repo_env
    _seed_staging(data_dir, _DAY, _window_rows())

    from app.services.auction_promote import promote_to_canonical
    promote_to_canonical(_stage_dir(data_dir, _DAY), repo, _DAY)

    df = pl.read_parquet(_canonical_path(data_dir, _DAY))
    assert df.columns == [
        "symbol", "datetime", "auction_volume", "auction_amount", "auction_virtual_price",
    ]
    assert "auction_unmatched_volume" not in df.columns
