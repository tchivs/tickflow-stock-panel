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


def test_auction_backfill_preflight_source_blocked_zero_writes(env, monkeypatch):
    """HON-01: 预检抛 SourceBlockedError → 终态 reason 恰 "source_blocked", 0 写, R1 零重试。

    消息故意含「带宽」重叠 marker (也在 _RATE_LIMIT_MARKERS) —— 若误入重试面则
    3 次调用 (2h 配额窗 × 5537 symbols 即 DoS); 断言恰 1 次。
    """
    from app.data_providers.base import SourceBlockedError
    from app.services import auction_backfill

    tmp, repo = env
    provider = FakeAuctionProvider(
        exc_by_symbol={"000001.SZ": SourceBlockedError("带宽限制批量请求")},
    )
    _patch_live(monkeypatch, provider)

    result = auction_backfill.run_auction_backfill(repo, symbols=["000001.SZ"])

    assert result["requested"] == 0
    assert result["reason"] == "source_blocked"
    assert result["backfilled_symbols"] == 0
    assert result["failed"] == 0
    assert len(provider.calls) == 1  # 预检 1 次, SourceBlockedError 零重试
    assert not list((tmp / "kline_auction").glob("date=*")), "fail-closed 不得写任何分区"


def test_auction_backfill_source_blocked_recorded(env, monkeypatch):
    """HON-01: 循环内 SourceBlockedError → 台账第三类 reason 恰 "source_blocked" (两键),
    其余 symbol 正常回填; 每 symbol 恰 1 次 provider 调用 (R1 零重试)。"""
    from app.data_providers.base import SourceBlockedError
    from app.services import auction_backfill

    tmp, repo = env
    rows_a = _auction_rows("000001.SZ", [datetime(2026, 8, 4, 9, 25)])
    provider = FakeAuctionProvider(
        rows_by_symbol={"000001.SZ": rows_a},
        exc_by_symbol={"600000.SH": SourceBlockedError("带宽限制批量请求")},
    )
    _patch_live(monkeypatch, provider)

    result = auction_backfill.run_auction_backfill(repo, symbols=["000001.SZ", "600000.SH"])

    assert result["failed"] == 1
    assert result["failed_symbols"] == [{"symbol": "600000.SH", "reason": "source_blocked"}]
    assert result["backfilled_symbols"] == 1
    assert result["rows"] == 1
    assert len(provider.calls) == 3  # 预检 + A + B 各 1 次 (B 零重试)


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


def test_auction_backfill_passes_date_objects_to_provider(env, monkeypatch):
    """provider.get_auction 收到 date 对象 (非 ISO 字符串) — xyz 契约 ``start_date.strftime``。"""
    from datetime import date

    from app.services import auction_backfill

    tmp, repo = env
    seen: list = []

    class DateRecorder(FakeAuctionProvider):
        def get_auction(self, symbols, start_date=None, end_date=None):
            seen.append((list(symbols), start_date, end_date))
            return _auction_rows(symbols[0], [datetime(2026, 8, 4, 9, 25)])

    _patch_live(monkeypatch, DateRecorder())

    result = auction_backfill.run_auction_backfill(repo, symbols=["000001.SZ"])

    assert seen, "应有请求"
    assert result["backfilled_symbols"] == 1
    for _, start_d, end_d in seen:
        assert isinstance(start_d, date) and isinstance(end_d, date), (
            f"provider 需要 date 对象, 收到 {type(start_d).__name__}"
        )


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


# ================================================================
# Task 3 — POST /api/kline/auction/backfill 端点 (AQ-02 触发面)
# ================================================================


def _terminal_result():
    return {
        "requested": 1, "backfilled_symbols": 1, "rows": 1, "dates": 1,
        "failed": 0, "failed_symbols": [], "origin": "backfill", "rpm": 30,
    }


def _make_auction_app(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import auction_backfill as auction_backfill_api

    app = FastAPI()
    app.include_router(auction_backfill_api.router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    return app, TestClient(app)


def _wait_job_terminal(job_id, timeout=5.0):
    import time as _time

    from app.services.pipeline_jobs import job_store

    # 轮询整个窗口: job_store.fail/succeed 是「pop 后写盘」, 并发 get 可能短暂
    # 既不在内存也不在盘 (fail-closed 任务无 await, 该窗口真实存在) —— 首个 poll
    # 不得因瞬时缺失直接返回 None。
    deadline = _time.time() + timeout
    j = None
    while _time.time() < deadline:
        j = job_store.get(job_id)
        if j is not None and j["status"] in ("succeeded", "failed"):
            return j
        _time.sleep(0.02)
    return j


def _wait_slot_free(timeout=5.0):
    import time as _time

    from app.services.pipeline_jobs import release_run_slot, try_acquire_run_slot

    deadline = _time.time() + timeout
    while _time.time() < deadline:
        if try_acquire_run_slot():
            release_run_slot()
            return True
        _time.sleep(0.02)
    return False


def test_auction_backfill_endpoint_singleflight_and_reuse(tmp_path, monkeypatch):
    """AQ-02: 首次 started, 二次复用活跃 job (单飞, 镜像 pool_backfill 端点)。"""
    from app.services import auction_backfill as auction_backfill_mod

    app, client = _make_auction_app(tmp_path)
    release = threading.Event()
    started = threading.Event()

    def fake_run(repo, **kwargs):
        started.set()
        release.wait(timeout=5)
        return _terminal_result()

    monkeypatch.setattr(auction_backfill_mod, "run_auction_backfill", fake_run)

    with client:
        r1 = client.post(
            "/api/kline/auction/backfill", json={"symbols": ["000001.SZ"], "rpm": 30},
        )
        assert r1.status_code == 200
        body1 = r1.json()
        assert body1["status"] == "started"
        job_id = body1["job_id"]
        assert started.wait(timeout=5), "后台任务应已启动"

        r2 = client.post(
            "/api/kline/auction/backfill", json={"symbols": ["000001.SZ"], "rpm": 30},
        )
        assert r2.status_code == 200
        assert r2.json() == {"status": "reused", "job_id": job_id}

        release.set()
        j = _wait_job_terminal(job_id)
        assert j is not None and j["status"] == "succeeded"
        assert j["result"]["origin"] == "backfill"
        assert _wait_slot_free(), "重任务执行槽应已释放"


def test_auction_backfill_endpoint_parameter_validation(tmp_path, monkeypatch):
    """AQ-02 (Pitfall 4): 非法/无界参数一律 400 (防路径穿越与失控长任务)。"""
    from app.services import auction_backfill as auction_backfill_mod

    monkeypatch.setattr(
        auction_backfill_mod, "run_auction_backfill", lambda repo, **kwargs: _terminal_result(),
    )
    app, client = _make_auction_app(tmp_path)

    with client:
        for body in (
            {"start": "2026-8-4"},                          # 非 YYYY-MM-DD
            {"start": "../../x"},                           # 路径穿越形
            {"start": "2026-13-01"},                        # 日历非法 (regex 过, ISO 不过)
            {"start": "2026-08-04", "end": "2026-08-01"},   # start > end
            {"rpm": 0},
            {"rpm": -1},
            {"rpm": 61},
            {"rpm": "30"},                                  # 非 int
            {"rpm": True},                                  # bool 不算 int
            {"symbols": ["000001"]},                        # 无后缀
            {"symbols": ["000001.XX"]},                     # 非法后缀
            {"symbols": ["../../x"]},                       # 路径穿越形
            {"symbols": ["000001.SZ"] * 6001},              # 超上限
        ):
            resp = client.post("/api/kline/auction/backfill", json=body)
            assert resp.status_code == 400, (
                f"body 应 400, got {resp.status_code}"
            )

        # 合法请求 → 200 started, 后台跑完释放槽
        resp = client.post(
            "/api/kline/auction/backfill", json={"symbols": ["000001.SZ"], "rpm": 30},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "started"
        j = _wait_job_terminal(resp.json()["job_id"])
        assert j is not None and j["status"] == "succeeded"
        assert _wait_slot_free()


def test_auction_backfill_endpoint_runs_in_executor_and_succeeds(tmp_path, monkeypatch):
    """AQ-02: 后台 executor 线程执行 (请求内零阻塞), job_store.succeed 被调。"""
    from app.services import auction_backfill as auction_backfill_mod

    app, client = _make_auction_app(tmp_path)
    thread = {"id": threading.main_thread().ident}
    started = threading.Event()
    release = threading.Event()

    def fake_run(repo, **kwargs):
        thread["id"] = threading.get_ident()
        started.set()
        release.wait(timeout=5)
        return _terminal_result()

    monkeypatch.setattr(auction_backfill_mod, "run_auction_backfill", fake_run)

    with client:
        resp = client.post("/api/kline/auction/backfill", json={"symbols": ["000001.SZ"]})
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]
        assert started.wait(timeout=5)
        release.set()
        j = _wait_job_terminal(job_id)
        assert j is not None and j["status"] == "succeeded"
        assert j["result"]["origin"] == "backfill"
        assert thread["id"] != threading.main_thread().ident, "回填应在线程池线程执行"
        assert _wait_slot_free()


def _main_src() -> str:
    backend = Path(__file__).resolve().parents[1]
    return (backend / "app" / "main.py").read_text(encoding="utf-8")


def test_auction_backfill_router_registered_in_main():
    """main.py 结构门: import 面 + include_router (auction_history 之后)。"""
    src = _main_src()
    assert "    auction_backfill,\n" in src
    assert "app.include_router(auction_backfill.router)" in src
    assert src.index("app.include_router(auction_backfill.router)") > src.index(
        "app.include_router(auction_history.router)"
    )


def test_auction_backfill_guest_whitelist_untouched():
    """guest 白名单零改动: 不放行 auction backfill (POST 非 guest 可读)。"""
    src = _main_src()
    block = src.split("_GUEST_READ_GET_PATHS = frozenset({", 1)[1].split("})", 1)[0]
    assert "backfill" not in block


def test_auction_backfill_endpoint_heavy_slot_fail_fast(tmp_path, monkeypatch):
    """R7: 预占重任务槽 → POST → job fail 记录 '已有数据任务在运行' (Test 6 子串断言)。"""
    from app.services import auction_backfill as auction_backfill_mod
    from app.services.pipeline_jobs import release_run_slot, try_acquire_run_slot

    monkeypatch.setattr(
        auction_backfill_mod, "run_auction_backfill", lambda repo, **kwargs: _terminal_result(),
    )
    app, client = _make_auction_app(tmp_path)

    assert try_acquire_run_slot(), "预占重任务执行槽"
    try:
        with client:
            resp = client.post(
                "/api/kline/auction/backfill", json={"symbols": ["000001.SZ"]},
            )
            assert resp.status_code == 200
            job_id = resp.json()["job_id"]
            j = _wait_job_terminal(job_id)
            assert j is not None and j["status"] == "failed"
            assert "已有数据任务在运行" in j["error"]
    finally:
        release_run_slot()


# ================================================================
# Task 1 (41-02) — fail-closed 提前返回终态 emit (HON-02)
# ================================================================


def test_auction_backfill_fail_closed_source_unavailable_emits(env, monkeypatch):
    """HON-02 (tracer 单路径): 探针非 available → fail-closed 也 emit 终态进度行。

    恰 1 行 ``fail-closed: source_unavailable`` (stage auction_backfill, pct 0),
    进度永不冻结; 终态 dict 9 键 (W-5) 形状不变, 0 写。
    """
    from app.services import auction_backfill
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
    from app.services import auction_probe

    tmp, repo = env
    verdict = AuctionProbeVerdict(
        status=AuctionProbeStatus("not_configured"), source="fake", probed_at=None, detail="",
    )
    monkeypatch.setattr(auction_probe, "resolve_auction_probe", lambda: verdict)

    lines: list[tuple] = []
    result = auction_backfill.run_auction_backfill(
        repo, on_progress=lambda stage, pct, msg, **kw: lines.append((stage, pct, msg)),
    )

    assert lines.count(("auction_backfill", 0, "fail-closed: source_unavailable")) == 1
    assert result["reason"] == "source_unavailable"
    assert set(result) == {
        "requested", "backfilled_symbols", "rows", "dates", "failed",
        "failed_symbols", "reason", "origin", "rpm",
    }
    assert not list((tmp / "kline_auction").glob("date=*")), "fail-closed 不得写任何分区"


def test_auction_backfill_fail_closed_five_paths_emit(env, monkeypatch):
    """HON-02: 五条 fail-closed 提前返回路径每条 emit 一行含 reason 的终态进度。

    no_scope / no_provider / 预检异常 / preflight_empty — 每子跑断言 emit 行
    与终态 dict reason 同字面量 (emit 与 _fail_closed 一致性), 且 0 写。
    """
    from app.services import auction_backfill

    tmp, repo = env
    rows = {
        s: _auction_rows(s, [datetime(2026, 8, 4, 9, 25)])
        for s in ("000001.SZ", "600000.SH")
    }

    def run(**kw) -> tuple[list[str], dict]:
        lines: list[str] = []
        result = auction_backfill.run_auction_backfill(
            repo, on_progress=lambda stage, pct, msg, **kw2: lines.append(msg), **kw,
        )
        return lines, result

    # (a) no_scope: 空 symbols → 范围对齐后空 → fail-closed
    _patch_live(monkeypatch, FakeAuctionProvider(rows_by_symbol=rows))
    lines_a, r_a = run(symbols=[])
    assert "fail-closed: no_scope" in lines_a
    assert r_a["reason"] == "no_scope"

    # (b) no_provider: 无可用 provider → fail-closed
    _patch_live(monkeypatch, None)
    lines_b, r_b = run(symbols=["000001.SZ"])
    assert "fail-closed: no_provider" in lines_b
    assert r_b["reason"] == "no_provider"

    # (c) 预检异常 → fail-closed, reason = 截断异常串 (emit 同字面量)
    _patch_live(monkeypatch, FakeAuctionProvider(
        exc_by_symbol={"000001.SZ": RuntimeError("boom preflight")},
    ))
    lines_c, r_c = run(symbols=["000001.SZ"])
    assert "fail-closed: boom preflight" in lines_c
    assert r_c["reason"] == "boom preflight"

    # (d) preflight_empty: 预检空 + 首 symbol 有 kline_daily 覆盖 → fail-closed
    _patch_live(monkeypatch, FakeAuctionProvider())
    lines_d, r_d = run(symbols=["000001.SZ", "600000.SH"])
    assert "fail-closed: preflight_empty" in lines_d
    assert r_d["reason"] == "preflight_empty"

    assert not list((tmp / "kline_auction").glob("date=*")), "fail-closed 不得写任何分区"


# ================================================================
# Task 2 (41-02) — 取消独立 cancelled stage + 回归锁 (HON-02)
# ================================================================


def test_auction_backfill_cancel_emits_cancelled_stage(env, monkeypatch):
    """HON-02: 取消改独立 stage ``cancelled`` + 实际 pct, 绝不 done/100, 无二次 done。

    镜像 test_auction_backfill_cooperative_cancel 双段式: (a) 预置 failed 立即停
    (pct 0), (b) 循环中翻转 (pct 33) — 两段都断言零 done 行、零「回填完成」
    消息 (二次 done bug 修复), 终态 8 键形状不变。
    """
    from app.services import auction_backfill
    from app.services.pipeline_jobs import job_store

    tmp, repo = env
    rows = {
        s: _auction_rows(s, [datetime(2026, 8, 4, 9, 25)])
        for s in ("000001.SZ", "600000.SH", "920146.BJ")
    }

    def run(**kw) -> tuple[list[tuple], dict]:
        lines: list[tuple] = []
        result = auction_backfill.run_auction_backfill(
            repo, on_progress=lambda stage, pct, msg, **kw2: lines.append((stage, pct, msg)),
            **kw,
        )
        return lines, result

    # (a) 预置 failed job → 首迭代即取消 (已处理 0/3, pct 0), 无任何 done 行
    provider = FakeAuctionProvider(rows_by_symbol=rows)
    _patch_live(monkeypatch, provider)
    job_id, _ = job_store.create()
    job_store.fail(job_id, "用户手动取消")
    lines_a, r_a = run(symbols=["000001.SZ", "600000.SH", "920146.BJ"], job_id=job_id)

    assert ("cancelled", 0, "回填被取消 (已处理 0/3)") in lines_a
    assert not [l for l in lines_a if l[0] == "done"], f"取消后不得有 done 行: {lines_a}"
    assert not [l for l in lines_a if "回填完成" in l[2]]
    assert r_a["backfilled_symbols"] == 0
    assert set(r_a) == {
        "requested", "backfilled_symbols", "rows", "dates", "failed",
        "failed_symbols", "origin", "rpm",
    }

    # (b) 循环中 job 翻转 failed → 首 symbol 后即取消 (已处理 1/3, pct 33)
    provider2 = FakeAuctionProvider(rows_by_symbol=rows)
    _patch_live(monkeypatch, provider2)
    n = {"calls": 0}

    def fake_get(job_id2):
        n["calls"] += 1
        if n["calls"] <= 1:
            return {"status": "running"}
        return {"status": "failed"}

    monkeypatch.setattr(job_store, "get", fake_get)
    lines_b, r_b = run(symbols=["000001.SZ", "600000.SH", "920146.BJ"], job_id="job-test")

    assert ("cancelled", 33, "回填被取消 (已处理 1/3)") in lines_b
    assert not [l for l in lines_b if l[0] == "done"], f"取消后不得有 done 行: {lines_b}"
    assert not [l for l in lines_b if "回填完成" in l[2]]
    assert r_b["backfilled_symbols"] == 1
    assert set(r_b) == {
        "requested", "backfilled_symbols", "rows", "dates", "failed",
        "failed_symbols", "origin", "rpm",
    }


def test_auction_backfill_all_empty_progress_and_failed_count(env, monkeypatch):
    """HON-02 回归锁: 全空帧批量 → 每 symbol 一行进度 + 终态 failed 计数正确。

    预检 symbol 选无 kline_daily 覆盖的 920146.BJ (预检通过, 绕开 preflight_empty
    整批返回门) + 其余两个有覆盖 symbol → 循环逐 symbol 空帧 → 各记
    empty_response, 进度行逐 symbol 可见 (进度永不冻结)。
    """
    from app.services import auction_backfill

    tmp, repo = env
    provider = FakeAuctionProvider()  # 全空帧
    _patch_live(monkeypatch, provider)

    lines: list[tuple] = []
    result = auction_backfill.run_auction_backfill(
        repo,
        symbols=["920146.BJ", "000001.SZ", "600000.SH"],
        on_progress=lambda stage, pct, msg, **kw: lines.append((stage, pct, msg)),
    )

    # 起始行 + 每 symbol 一行进度 (3 symbols → 4 行 stage auction_backfill)
    progress = [l for l in lines if l[0] == "auction_backfill"]
    assert len(progress) == 1 + 3, f"应 1 起始 + 3 逐 symbol 进度行: {progress}"
    assert progress[0] == ("auction_backfill", 0, "回填 3 个标的 × 2 日…")
    assert [l[1] for l in progress[1:]] == [33, 66, 100], "逐 symbol pct 应如实推进"

    assert result["requested"] == 3
    assert result["backfilled_symbols"] == 0
    assert result["failed"] == 2
    assert result["failed_symbols"] == [
        {"symbol": "000001.SZ", "reason": "empty_response"},
        {"symbol": "600000.SH", "reason": "empty_response"},
    ]
    done = [l for l in lines if l[0] == "done"]
    assert done == [("done", 100, "回填完成: 0 成功, 2 失败")]
    assert not list((tmp / "kline_auction").glob("date=*")), "全空帧不得写任何分区"
