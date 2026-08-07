"""MIN-01 回填驱动契约测试 (hermetic, 零网络, canned 夹具注入 fetch).

契约面 (42-01-PLAN):
- 端到端: 单 symbol 落盘 kline_minute/date=* 分区, canonical 列集, 每日期首根 09:30 anchor。
- 幂等双保险: 重跑同参 → 已覆盖 symbol 全部 skip, written==0, 分区行数/文件字节不变
  (merge-upsert unique keep=last 原子写)。
- 增量续跑: per-symbol latest + [latest+1day, end] 窗口, 部分覆盖只拉缺口。
- 空态诚实: 空响应 → 0 行不落盘不伪 skip (下次重跑重试)。
- fetch 异常 fail-closed: 上抛不吞 (绝不伪装「该窗口无数据」)。
- 全宇宙动态解析: kline_daily DISTINCT symbol 运行期解析, 非硬编码。

所有生产 import 延迟到测试函数内 (repo 约定: 集合期不碰 DuckDB 单例)。
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path

import polars as pl
import pytest

_FIXTURES = Path(__file__).parent / "fixtures" / "stockdb"
_FIXTURE = "minute_backfill_20260803_20260804.json"

_SZ, _SH519, _SH000 = "000001.SZ", "600519.SH", "600000.SH"


def _load_fixture(name: str = _FIXTURE) -> dict:
    """读夹具 JSON (镜像 test_stockdb_provider._load_fixture)。"""
    with open(_FIXTURES / name, encoding="utf-8") as fh:
        return json.load(fh)


def _to_suffix(prefix_symbol: str) -> str:
    """``SH600519`` -> ``600519.SH`` (镜像 stockdb_provider._to_suffix 语义)。"""
    return f"{prefix_symbol[2:]}.{prefix_symbol[:2]}"


def _canned_fetch(name: str = _FIXTURE):
    """零网络 canned fetch: 按 (symbols, [start, end]) 窗口从夹具过滤, 归一 canonical 列集。"""
    fixture = _load_fixture(name)

    def fetch(symbols, start_time, end_time):
        rows = []
        for prefix, bars in fixture.items():
            sym = _to_suffix(prefix)
            if sym not in symbols:
                continue
            for bar in bars:
                bar_dt = datetime.fromisoformat(bar["bar_time"]).replace(tzinfo=None)
                if start_time <= bar_dt <= end_time:
                    rows.append({
                        "symbol": sym,
                        "datetime": bar_dt,
                        "open": float(bar["open"]),
                        "high": float(bar["high"]),
                        "low": float(bar["low"]),
                        "close": float(bar["close"]),
                        "volume": float(bar["volume_hand"]),  # 恒等手, 与 provider 同口径
                        "amount": float(bar["amount_yuan"]),
                    })
        if not rows:
            return pl.DataFrame()
        return pl.DataFrame(rows).with_columns(pl.col("datetime").cast(pl.Datetime("us")))

    return fetch


class _RecordingFetch:
    """记录每次调用 (symbols, start_time, end_time) 的 canned fetch 包装。"""

    def __init__(self, name: str = _FIXTURE):
        self.calls: list[tuple[list[str], datetime, datetime]] = []
        self._inner = _canned_fetch(name)

    def __call__(self, symbols, start_time, end_time):
        self.calls.append((list(symbols), start_time, end_time))
        return self._inner(symbols, start_time, end_time)


@pytest.fixture
def repo_env(tmp_path, monkeypatch):
    """隔离的 data_dir + DataStore + KlineRepository (镜像 test_auction_validation_report)。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    repo = KlineRepository(store)
    try:
        yield repo, data_dir
    finally:
        store.db.close()


def _seed_daily(repo, symbols: list[str], dates: list[date]) -> None:
    """kline_daily 种子 (镜像 test_minute_sync_verify._seed_daily_lake)。"""
    rows = []
    for sym in symbols:
        for d in dates:
            rows.append({
                "symbol": sym,
                "date": d,
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "volume": 1000.0,
                "amount": 10500.0,
            })
    repo.append_daily(pl.DataFrame(rows))


def _minute_frame(symbols, days: list[date], start_price: float = 10.0) -> pl.DataFrame:
    """canonical 分钟帧: 每 symbol × 每日 09:30..09:34 五根。"""
    rows = []
    for sym in symbols:
        price = start_price
        for d in days:
            for i in range(5):
                rows.append({
                    "symbol": sym,
                    "datetime": datetime(d.year, d.month, d.day, 9, 30 + i),
                    "open": price + i,
                    "high": price + i + 1,
                    "low": price + i - 0.5,
                    "close": price + i + 0.5,
                    "volume": 100.0,
                    "amount": 1050.0,
                })
    return pl.DataFrame(rows).with_columns(pl.col("datetime").cast(pl.Datetime("us")))


# ============================================================
# Task 1: 端到端落盘 / 重跑跳过 / upsert 幂等
# ============================================================


def test_backfill_minute_history_persists_partitions(repo_env):
    """单 symbol 组端到端: 分区落盘 + canonical 列集 + 每日期首根 09:30 anchor。"""
    from app.services import kline_sync
    repo, data_dir = repo_env

    written, skipped = kline_sync.backfill_minute_history(
        [_SH519, _SH000], date(2026, 8, 3), date(2026, 8, 4), repo,
        fetch=_canned_fetch(),
    )
    assert skipped == []
    assert written == 20  # 2 symbols x 2 交易日 x 5 根

    for day in (date(2026, 8, 3), date(2026, 8, 4)):
        out = data_dir / "kline_minute" / f"date={day}" / "part.parquet"
        assert out.exists()
        df = pl.read_parquet(out)
        assert df.columns == kline_sync.CANONICAL_MINUTE_COLS
        assert df.schema["datetime"] == pl.Datetime("us")
        # 每日期首根 == 09:30 (湖 anchor 约定)
        firsts = (
            df.sort(["symbol", "datetime"])
            .group_by("symbol")
            .agg(pl.col("datetime").first().alias("first_bar"))
        )
        assert set(firsts["first_bar"].to_list()) == {
            datetime(day.year, day.month, day.day, 9, 30)
        }


def test_backfill_minute_history_rerun_skips_covered(repo_env):
    """重跑同参 → 已覆盖 symbol 全部 skip, written==0, 分区文件 sha256 与首跑一致。"""
    from app.services import kline_sync
    repo, data_dir = repo_env

    fetch = _canned_fetch()
    first_written, first_skipped = kline_sync.backfill_minute_history(
        [_SH519, _SH000], date(2026, 8, 3), date(2026, 8, 4), repo, fetch=fetch,
    )
    assert first_written == 20 and first_skipped == []

    before = {
        p.relative_to(data_dir): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((data_dir / "kline_minute").rglob("*.parquet"))
    }
    assert before  # 分区存在

    second_written, second_skipped = kline_sync.backfill_minute_history(
        [_SH519, _SH000], date(2026, 8, 3), date(2026, 8, 4), repo, fetch=fetch,
    )
    assert second_written == 0
    assert second_skipped == [_SH519, _SH000]

    after = {
        p.relative_to(data_dir): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((data_dir / "kline_minute").rglob("*.parquet"))
    }
    assert after == before  # merge-upsert 幂等: 文件字节不变


def test_persist_minute_partitions_idempotent_upsert(repo_env):
    """同帧写两遍 → 行数不变 (unique subset=[symbol, datetime] keep=last); written = 增量。"""
    from app.services import kline_sync
    repo, data_dir = repo_env

    frame = _minute_frame([_SH519, _SH000], [date(2026, 8, 3)])
    n1 = kline_sync._persist_minute_partitions(frame, repo)
    assert n1 == 10  # 首写: 全部为新增
    n2 = kline_sync._persist_minute_partitions(frame, repo)
    assert n2 == 0  # 重写同帧: 零新增 (upsert 去重)

    total = sum(
        pl.read_parquet(p).height for p in (data_dir / "kline_minute").rglob("*.parquet")
    )
    assert total == 10  # 分区行数不变 (幂等)


# ============================================================
# Task 2: 增量窗口 / 空态 / 进度 / 异常 / universe 动态解析
# ============================================================


def test_backfill_incremental_only_gap_window(repo_env):
    """部分覆盖只拉缺口: A 已覆盖至 08-04 → 收到 [08-05, 08-05] (latest+1day);
    B 无覆盖 → 收到 [start_date, end_date] 全窗。"""
    from app.services import kline_sync
    repo, _ = repo_env

    # 种子 A 已覆盖 08-03..08-04 (经唯一写面 + 视图刷新)
    kline_sync._persist_minute_partitions(
        _minute_frame([_SH519], [date(2026, 8, 3), date(2026, 8, 4)]), repo,
    )
    kline_sync._refresh_minute_view(repo)

    rec = _RecordingFetch()
    kline_sync.backfill_minute_history(
        [_SH519, _SH000], date(2026, 8, 3), date(2026, 8, 5), repo, fetch=rec,
    )

    by_symbol = {tuple(c[0]): c for c in rec.calls}
    assert len(rec.calls) == 2

    a_call = by_symbol[(_SH519,)]
    assert a_call[1] == datetime(2026, 8, 5)  # start == latest+1day
    assert a_call[2] == datetime(2026, 8, 5, 23, 59, 59)  # end 端日含全天

    b_call = by_symbol[(_SH000,)]
    assert b_call[1] == datetime(2026, 8, 3)  # 无覆盖 → 全窗起点
    assert b_call[2] == datetime(2026, 8, 5, 23, 59, 59)


def test_backfill_empty_fetch_is_honest_zero(repo_env):
    """空响应 → written 0、无分区落盘、不伪 skip 不伪 written; 下次重跑重试。"""
    from app.services import kline_sync
    repo, data_dir = repo_env

    def _empty_fetch(symbols, start_time, end_time):
        return pl.DataFrame()

    written, skipped = kline_sync.backfill_minute_history(
        [_SH519], date(2026, 8, 3), date(2026, 8, 4), repo, fetch=_empty_fetch,
    )
    assert written == 0
    assert skipped == []  # 空响应不伪 skip: 下次重跑重试
    assert not list((data_dir / "kline_minute").rglob("*.parquet"))

    # 重跑 (有数据) → 正常落盘, 证明空态不毒化后续
    written2, _ = kline_sync.backfill_minute_history(
        [_SH519], date(2026, 8, 3), date(2026, 8, 4), repo, fetch=_canned_fetch(),
    )
    assert written2 == 10


def test_backfill_progress_callback_counts(repo_env):
    """2 symbol → on_symbol_done 恰被调 2 次, 参数 (1,2) 与 (2,2)。"""
    from app.services import kline_sync
    repo, _ = repo_env

    calls: list[tuple[int, int]] = []
    kline_sync.backfill_minute_history(
        [_SH519, _SH000], date(2026, 8, 3), date(2026, 8, 4), repo,
        fetch=_canned_fetch(), on_symbol_done=lambda i, t: calls.append((i, t)),
    )
    assert calls == [(1, 2), (2, 2)]


def test_backfill_fetch_error_fail_closed(repo_env):
    """fetch 抛异常 → 原样上抛 (绝不吞成空帧/伪 skip)。"""
    from app.services import kline_sync
    repo, _ = repo_env

    def _boom_fetch(symbols, start_time, end_time):
        raise RuntimeError("Tushare 40203 rate limited")

    with pytest.raises(RuntimeError, match="40203"):
        kline_sync.backfill_minute_history(
            [_SH519], date(2026, 8, 3), date(2026, 8, 4), repo, fetch=_boom_fetch,
        )


def test_resolve_minute_universe_dynamic(repo_env):
    """全宇宙 = kline_daily DISTINCT symbol 运行期动态解析 (非硬编码常数)。"""
    from app.services import kline_sync
    repo, _ = repo_env

    _seed_daily(repo, [_SH000, _SH519, _SZ], [date(2026, 8, 3)])
    assert kline_sync._resolve_minute_universe(repo) == [_SZ, _SH000, _SH519]  # 排序
