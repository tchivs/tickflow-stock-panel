"""AQ-02/03/05 竞价历史回填 — 单元测试 (hermetic, 不碰真实数据目录/网络)。

- 探针/预检 fail-closed 0 写 (AQ-03a); kline_daily 分区对齐 (范围 ∩ + 写边界 is_in, AQ-03b);
- per-symbol 失败台账 (empty_response / 截断 reason, AQ-03c); 限界 / 幂等 / 单码请求 (AQ-05);
- 限速 (sleep_between_batches) / 合作取消 / 原子无 .tmp / 09:30 排除 / 缺列诚实 (AQ-04/05);
- 端点: 单飞复用 / 参数校验 400 / executor 后台 / main.py 注册 / guest 白名单不动 / 重槽互斥 (AQ-02)。

fixture 形: test_auction_sync 的 DataStore/FakeAuctionProvider + test_pool_backfill 的
端点测试形 (job_store 全局单例 + 轮询 helper)。生产 import 放测试函数内 (repo 约定)。
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest


class FakeAuctionProvider:
    """极简假 provider: rows_by_symbol / exc_by_symbol 注入, calls 记录每次调用 symbols。"""

    name = "fake_auction"

    def __init__(self, rows_by_symbol=None, exc_by_symbol=None):
        self.rows_by_symbol = rows_by_symbol or {}
        self.exc_by_symbol = exc_by_symbol or {}
        self.calls: list[list[str]] = []

    def get_auction(self, symbols, start_date=None, end_date=None):
        del start_date, end_date
        self.calls.append(list(symbols))
        sym = symbols[0]
        if sym in self.exc_by_symbol:
            raise self.exc_by_symbol[sym]
        return self.rows_by_symbol.get(sym, pl.DataFrame())


def _available_verdict():
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
    return AuctionProbeVerdict(
        status=AuctionProbeStatus.available, source="fake_auction", probed_at=None, detail="",
    )


def _auction_rows(symbol, dtimes, *, virtual_price=None, unmatched=False):
    """构造 canonical 竞价帧 (symbol/datetime/auction_volume/auction_amount [+可选列])。"""
    data = {
        "symbol": [symbol] * len(dtimes),
        "datetime": dtimes,
        "auction_volume": [100 * (i + 1) for i in range(len(dtimes))],
        "auction_amount": [1000 * (i + 1) for i in range(len(dtimes))],
    }
    if unmatched:
        data["auction_unmatched_volume"] = [50 * (i + 1) for i in range(len(dtimes))]
    if virtual_price is not None:
        data["auction_virtual_price"] = [virtual_price] * len(dtimes)
    return pl.DataFrame(data)


@pytest.fixture
def env(tmp_path):
    """kline_daily 分区 (每分区每 symbol 1 行真实日K形) + 真实 DataStore/KlineRepository。

    对齐判定按分区目录名; DISTINCT universe / coverage 查询经 DuckDB 视图
    (repository.py:162-164 union_by_name=true 同源语义)。
    """
    from app.tickflow.repository import DataStore, KlineRepository

    dates = ["2026-08-04", "2026-08-05"]
    symbols = ("000001.SZ", "600000.SH")
    for d in dates:
        part_dir = tmp_path / "kline_daily" / f"date={d}"
        part_dir.mkdir(parents=True, exist_ok=True)
        rows = [
            {"symbol": sym, "date": d, "open": 10.0, "high": 11.0, "low": 9.5,
             "close": 10.5, "volume": 1000, "amount": 10500}
            for sym in symbols
        ]
        pl.DataFrame(rows).write_parquet(part_dir / "part.parquet")
    store = DataStore(tmp_path)
    repo = KlineRepository(store)
    yield tmp_path, repo
    store.db.close()


@pytest.fixture(autouse=True)
def _neutralize_pacing(monkeypatch):
    """job 测试默认不真实限速 (rpm 由 pacing 专项测试锁定); 记录调用供专项断言。

    W-3: 补丁打在模块级属性 ``app.services.auction_backfill.sleep_between_batches``
    (服务模块级 import 才有此属性) —— 函数内 import 的重绑定会让补丁失效。
    """
    from app.services import auction_backfill

    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        auction_backfill, "sleep_between_batches",
        lambda i, rpm: calls.append((i, rpm)),
    )
    return calls


def _patch_live(monkeypatch, provider):
    """探针 available + 指定 provider (job 测试公共接线)。"""
    from app.services import auction_probe, auction_sync

    monkeypatch.setattr(auction_probe, "resolve_auction_probe", _available_verdict)
    monkeypatch.setattr(auction_sync, "_first_auction_provider", lambda: provider)


# ================================================================
# Task 1 — 探针闸门 / 范围对齐 / 预检 / 串行循环 / 终态 dict (AQ-02/03)
# ================================================================


@pytest.mark.parametrize("status", ["not_configured", "fail_closed", "error"])
def test_auction_backfill_source_down_zero_writes(tmp_path, monkeypatch, env, status):
    """AQ-03a: probe 非 available → fail-closed 0 写 (kline_auction 目录不创建)。"""
    from app.services import auction_backfill
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
    from app.services import auction_probe

    tmp, repo = env
    verdict = AuctionProbeVerdict(
        status=AuctionProbeStatus(status), source="fake", probed_at=None, detail="",
    )
    monkeypatch.setattr(auction_probe, "resolve_auction_probe", lambda: verdict)

    result = auction_backfill.run_auction_backfill(repo)

    assert result == {
        "requested": 0, "backfilled_symbols": 0, "rows": 0, "dates": 0,
        "failed": 0, "failed_symbols": [], "reason": "source_unavailable",
        "origin": "backfill", "rpm": 30,
    }
    assert not list((tmp / "kline_auction").glob("date=*")), "fail-closed 不得写任何分区"


def test_auction_backfill_preflight_exception_zero_writes(env, monkeypatch):
    """AQ-03a: 预检 get_auction 抛异常 → fail-closed (reason 截断 200), 0 写。"""
    from app.services import auction_backfill

    tmp, repo = env
    provider = FakeAuctionProvider(
        exc_by_symbol={"000001.SZ": RuntimeError("boom preflight")},
    )
    _patch_live(monkeypatch, provider)

    result = auction_backfill.run_auction_backfill(repo, symbols=["000001.SZ"])

    assert result["requested"] == 0
    assert result["reason"] == "boom preflight"
    assert result["backfilled_symbols"] == 0
    assert result["failed"] == 0
    assert not list((tmp / "kline_auction").glob("date=*")), "fail-closed 不得写任何分区"


def test_auction_backfill_preflight_empty_zero_writes(env, monkeypatch):
    """AQ-03a: 预检空但首 symbol 范围内有 kline_daily 行 → preflight_empty fail-closed, 0 写。"""
    from app.services import auction_backfill

    tmp, repo = env
    provider = FakeAuctionProvider()  # 全部空
    _patch_live(monkeypatch, provider)

    result = auction_backfill.run_auction_backfill(repo)

    assert result["requested"] == 0
    assert result["reason"] == "preflight_empty"
    assert result["backfilled_symbols"] == 0
    assert not list((tmp / "kline_auction").glob("date=*")), "fail-closed 不得写任何分区"


def test_auction_backfill_only_writes_kline_daily_aligned_dates(env, monkeypatch):
    """AQ-03b (承重): 只写 kline_daily 分区对齐日期 — 08-03 无分区 → 绝不 phantom-write。"""
    from app.services import auction_backfill

    tmp, repo = env
    rows = _auction_rows("000001.SZ", [
        datetime(2026, 8, 3, 9, 25),  # 无 kline_daily 分区 → 写边界 is_in 过滤
        datetime(2026, 8, 4, 9, 25),
        datetime(2026, 8, 5, 9, 25),
    ])
    provider = FakeAuctionProvider(rows_by_symbol={"000001.SZ": rows})
    _patch_live(monkeypatch, provider)

    result = auction_backfill.run_auction_backfill(
        repo, symbols=["000001.SZ"], start="2026-08-01", end="2026-08-05",
    )

    assert (tmp / "kline_auction" / "date=2026-08-04" / "part.parquet").exists()
    assert (tmp / "kline_auction" / "date=2026-08-05" / "part.parquet").exists()
    assert not (tmp / "kline_auction" / "date=2026-08-03").exists()
    assert pl.read_parquet(tmp / "kline_auction" / "date=2026-08-04" / "part.parquet").height == 1
    assert pl.read_parquet(tmp / "kline_auction" / "date=2026-08-05" / "part.parquet").height == 1
    assert result["rows"] == 2
    assert result["dates"] == 2
    assert result["failed"] == 0
    assert result["backfilled_symbols"] == 1
    assert result["origin"] == "backfill"
    assert result["rpm"] == 30


def test_auction_backfill_per_symbol_failure_recorded(env, monkeypatch):
    """AQ-03c: A 成功 / B 抛异常 → B 进台账 (reason 截断 200), A 已写, 失败不阻断。"""
    from app.services import auction_backfill

    tmp, repo = env
    rows_a = _auction_rows("000001.SZ", [datetime(2026, 8, 4, 9, 25)])
    provider = FakeAuctionProvider(
        rows_by_symbol={"000001.SZ": rows_a},
        exc_by_symbol={"600000.SH": RuntimeError("x" * 500)},
    )
    _patch_live(monkeypatch, provider)

    result = auction_backfill.run_auction_backfill(repo, symbols=["000001.SZ", "600000.SH"])

    assert result["failed"] == 1
    assert result["failed_symbols"] == [{"symbol": "600000.SH", "reason": "x" * 200}]
    assert result["backfilled_symbols"] == 1
    assert result["rows"] == 1
    assert result["origin"] == "backfill"
    assert result["rpm"] == 30
    df = pl.read_parquet(tmp / "kline_auction" / "date=2026-08-04" / "part.parquet")
    assert df.filter(pl.col("symbol") == "000001.SZ").height == 1


def test_auction_backfill_empty_response_recorded(env, monkeypatch):
    """AQ-03c: symbol B 上游空但 B 范围内有 kline_daily 行 → empty_response 台账。"""
    from app.services import auction_backfill

    tmp, repo = env
    rows_a = _auction_rows("000001.SZ", [datetime(2026, 8, 4, 9, 25)])
    provider = FakeAuctionProvider(rows_by_symbol={"000001.SZ": rows_a})  # B 空
    _patch_live(monkeypatch, provider)

    result = auction_backfill.run_auction_backfill(repo, symbols=["000001.SZ", "600000.SH"])

    assert result["failed"] == 1
    assert result["failed_symbols"] == [{"symbol": "600000.SH", "reason": "empty_response"}]
    assert result["backfilled_symbols"] == 1
    assert result["rows"] == 1


def test_auction_backfill_bounds(env, monkeypatch):
    """AQ-05: 子集 symbols + start/end 收窄日期集; 空范围 → no_scope 0 写短终态。"""
    from app.services import auction_backfill

    tmp, repo = env
    rows = _auction_rows("000001.SZ", [
        datetime(2026, 8, 4, 9, 25),
        datetime(2026, 8, 5, 9, 25),
    ])
    provider = FakeAuctionProvider(rows_by_symbol={"000001.SZ": rows})
    _patch_live(monkeypatch, provider)

    # start=end=08-04: 日期集收窄到 1 日; 08-05 行被写边界 is_in 过滤 (绝不 phantom-write)
    result = auction_backfill.run_auction_backfill(
        repo, symbols=["000001.SZ"], start="2026-08-04", end="2026-08-04",
    )
    assert result["requested"] == 1
    assert result["dates"] == 1
    assert result["rows"] == 1
    assert result["backfilled_symbols"] == 1
    assert result["failed"] == 0
    df = pl.read_parquet(tmp / "kline_auction" / "date=2026-08-04" / "part.parquet")
    assert df.height == 1
    assert not (tmp / "kline_auction" / "date=2026-08-05").exists()
    assert len(provider.calls) == 2  # 预检 + 循环, 均单码
    assert all(len(c) == 1 for c in provider.calls)

    # 空范围 → no_scope fail-closed, 0 写
    result2 = auction_backfill.run_auction_backfill(
        repo, symbols=["000001.SZ"], start="2026-09-01", end="2026-09-30",
    )
    assert result2["requested"] == 0
    assert result2["reason"] == "no_scope"
    assert result2["backfilled_symbols"] == 0


def test_auction_backfill_idempotent_rerun(env, monkeypatch):
    """AQ-04: 同数据跑两次 → 分区行数不变 (merge-upsert keep=last 只填缺口, 无重复)。"""
    from app.services import auction_backfill

    tmp, repo = env
    rows = _auction_rows("000001.SZ", [datetime(2026, 8, 4, 9, 25)])
    provider = FakeAuctionProvider(rows_by_symbol={"000001.SZ": rows})
    _patch_live(monkeypatch, provider)

    r1 = auction_backfill.run_auction_backfill(repo, symbols=["000001.SZ"])
    r2 = auction_backfill.run_auction_backfill(repo, symbols=["000001.SZ"])

    df = pl.read_parquet(tmp / "kline_auction" / "date=2026-08-04" / "part.parquet")
    assert df.height == 1
    assert r1["rows"] == 1
    assert r2["rows"] == 1


def test_auction_backfill_one_symbol_per_request(env, monkeypatch):
    """AQ-05: 每 provider 调用 symbols 恰 1 元素; universe = 湖 DISTINCT 开工时取一次。"""
    from app.services import auction_backfill

    tmp, repo = env
    rows = {
        s: _auction_rows(s, [datetime(2026, 8, 4, 9, 25)])
        for s in ("000001.SZ", "600000.SH")
    }
    provider = FakeAuctionProvider(rows_by_symbol=rows)
    _patch_live(monkeypatch, provider)

    result = auction_backfill.run_auction_backfill(repo)

    assert result["requested"] == 2
    assert result["backfilled_symbols"] == 2
    assert provider.calls, "应有请求"
    assert all(len(c) == 1 for c in provider.calls)
    assert len(provider.calls) == 3  # 预检 + 每 symbol 各 1 次


# ================================================================
# Task 2 — 限速 / 合作取消 / 写缝不变式经 job 回归 (AQ-04/05)
# ================================================================


def test_auction_backfill_rate_limit_pacing(env, monkeypatch, _neutralize_pacing):
    """AQ-05: sleep_between_batches 每 symbol 调用且 (i, rpm) 参数透传 (W-3 模块级补丁)。"""
    from app.services import auction_backfill

    tmp, repo = env
    calls = _neutralize_pacing
    rows = {
        s: _auction_rows(s, [datetime(2026, 8, 4, 9, 25)])
        for s in ("000001.SZ", "600000.SH", "920146.BJ")
    }
    provider = FakeAuctionProvider(rows_by_symbol=rows)
    _patch_live(monkeypatch, provider)

    result = auction_backfill.run_auction_backfill(
        repo, symbols=["000001.SZ", "600000.SH", "920146.BJ"], rpm=30,
    )
    assert calls == [(0, 30), (1, 30), (2, 30)]
    assert result["rpm"] == 30

    # 非默认 rpm 透传 (服务层信任参数; 1..60 由端点校验)
    calls.clear()
    auction_backfill.run_auction_backfill(repo, symbols=["000001.SZ"], rpm=10)
    assert calls == [(0, 10)]


def test_auction_backfill_cooperative_cancel(env, monkeypatch):
    """AQ-05: job failed → 剩余 symbol 不请求 (预置 failed 立即停 + 循环中翻转镜像 pool_backfill)。"""
    from app.services import auction_backfill
    from app.services.pipeline_jobs import job_store

    tmp, repo = env
    rows = {
        s: _auction_rows(s, [datetime(2026, 8, 4, 9, 25)])
        for s in ("000001.SZ", "600000.SH", "920146.BJ")
    }
    provider = FakeAuctionProvider(rows_by_symbol=rows)
    _patch_live(monkeypatch, provider)

    # (a) 预置 failed job → 循环首迭代即停 (仅预检 1 次请求), 终态形状完整 (W-5 成功 8 键)
    job_id, _ = job_store.create()
    job_store.fail(job_id, "用户手动取消")
    result = auction_backfill.run_auction_backfill(
        repo, symbols=["000001.SZ", "600000.SH", "920146.BJ"], job_id=job_id,
    )
    assert result["requested"] == 3
    assert result["failed"] == 0
    assert result["backfilled_symbols"] == 0
    assert len(provider.calls) < 3  # 只到预检
    assert set(result) == {
        "requested", "backfilled_symbols", "rows", "dates", "failed",
        "failed_symbols", "origin", "rpm",
    }

    # (b) 循环中 job 翻转 failed → 首 symbol 后即停 (镜像 test_pool_backfill_cooperative_cancel)
    provider2 = FakeAuctionProvider(rows_by_symbol=rows)
    _patch_live(monkeypatch, provider2)
    n = {"calls": 0}

    def fake_get(job_id2):
        n["calls"] += 1
        if n["calls"] <= 1:
            return {"status": "running"}
        return {"status": "failed"}

    monkeypatch.setattr(job_store, "get", fake_get)

    result2 = auction_backfill.run_auction_backfill(
        repo, symbols=["000001.SZ", "600000.SH", "920146.BJ"], job_id="job-test",
    )
    assert result2["requested"] == 3
    assert result2["failed"] == 0
    assert result2["backfilled_symbols"] == 1
    assert len(provider2.calls) == 2  # 预检 + 首 symbol; 剩余 2 个不被请求


def test_auction_backfill_atomic_no_tmp_left(env, monkeypatch):
    """AQ-04: 写多 symbol 后 kline_auction 下无 *.tmp 残留 (镜像 test_atomic_write_leaves_no_tmp)。"""
    from app.services import auction_backfill

    tmp, repo = env
    rows = {
        s: _auction_rows(s, [datetime(2026, 8, 4, 9, 25)])
        for s in ("000001.SZ", "600000.SH")
    }
    provider = FakeAuctionProvider(rows_by_symbol=rows)
    _patch_live(monkeypatch, provider)

    auction_backfill.run_auction_backfill(repo)

    assert not list((tmp / "kline_auction").rglob("*.tmp"))
    for part in (tmp / "kline_auction").glob("date=*/part.parquet"):
        assert not part.with_name(part.name + ".tmp").exists()


def test_auction_backfill_0930_excluded(env, monkeypatch):
    """09:30+ 连续竞价 bar 不写 (写缝 555..565 谓词经 job 复验, 镜像 test_0930_excluded)。"""
    from app.services import auction_backfill

    tmp, repo = env
    rows = _auction_rows("000001.SZ", [
        datetime(2026, 8, 4, 9, 30),
        datetime(2026, 8, 4, 9, 31),
    ])
    provider = FakeAuctionProvider(rows_by_symbol={"000001.SZ": rows})
    _patch_live(monkeypatch, provider)

    result = auction_backfill.run_auction_backfill(repo, symbols=["000001.SZ"])

    assert result["rows"] == 0
    assert result["backfilled_symbols"] == 1  # symbol 已处理, 窗口过滤 0 行 (诚实)
    lake = tmp / "kline_auction"
    if lake.exists():
        assert not list(lake.glob("date=*"))


def test_auction_backfill_unmatched_col_absent(env, monkeypatch):
    """AQ-04: 上游无 unmatched 列 → 分区无 auction_unmatched_volume/amount, 绝无 0 填列。"""
    from app.services import auction_backfill

    tmp, repo = env
    provider = FakeAuctionProvider(rows_by_symbol={
        "000001.SZ": _auction_rows("000001.SZ", [datetime(2026, 8, 4, 9, 25)]),
        "600000.SH": _auction_rows(
            "600000.SH", [datetime(2026, 8, 4, 9, 25)], virtual_price=7.5,
        ),
    })
    _patch_live(monkeypatch, provider)

    auction_backfill.run_auction_backfill(repo, symbols=["000001.SZ", "600000.SH"])

    df = pl.read_parquet(tmp / "kline_auction" / "date=2026-08-04" / "part.parquet")
    cols = set(df.columns)
    assert "auction_unmatched_volume" not in cols
    assert "auction_unmatched_amount" not in cols
    assert "auction_volume" in cols and "auction_amount" in cols
    assert "auction_virtual_price" in cols  # 600000.SH 提供 → 透传 (诚实缺列不 0 填)
    assert df.height == 2
