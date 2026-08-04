"""竞价数据探测 (DATA-03) — 服务端权威判定 + 诚实标签回归。

T-16-01 (critical): ``available`` 只能由落在 [09:15:00, 09:25:59] 窗口内的
被观测时间戳产生; 09:30 起的连续竞价 bar 永远不可能是 集合竞价 数据。
T-16-02 (high): 判定完全服务端计算, 前端只映射服务端 status。
"""
from __future__ import annotations

from datetime import datetime

import polars as pl
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import data as data_api
from app.services.auction_probe import (
    FAIL_CLOSED_DETAIL,
    NOT_CONFIGURED_DETAIL,
    AuctionProbeStatus,
    resolve_auction_probe,
)


class FakeAuctionProvider:
    """极简假 provider: 可注入预置行或抛错, 用于强制每个探测状态。"""

    name = "fake_auction"

    def __init__(self, rows: pl.DataFrame | None = None, exc: Exception | None = None) -> None:
        self.rows = rows
        self.exc = exc

    def get_auction(self, symbols: list[str], trade_date: datetime) -> pl.DataFrame:
        if self.exc is not None:
            raise self.exc
        return self.rows if self.rows is not None else pl.DataFrame()


def _rows(*minutes_and_seconds: tuple[int, int]) -> pl.DataFrame:
    """构造 probe 行, 时间 = 2026-08-04 09:{m}:{s}。"""
    return pl.DataFrame(
        {
            "symbol": ["000001"] * len(minutes_and_seconds),
            "datetime": [
                datetime(2026, 8, 4, 9, m, s) for m, s in minutes_and_seconds
            ],
            "auction_volume": [100] * len(minutes_and_seconds),
        }
    )


def _probe(provider: FakeAuctionProvider) -> dict:
    return resolve_auction_probe(
        source_resolver=lambda: [provider],
        fetcher=lambda p, symbols, trade_date: p.get_auction(symbols, trade_date),
    ).to_dict()


# ================================================================
# 四个状态 (hermetic)
# ================================================================


def test_no_source_is_not_configured():
    verdict = resolve_auction_probe(source_resolver=lambda: []).to_dict()
    assert verdict["status"] == "not_configured"
    assert verdict["source"] is None
    assert verdict["window"] == "09:15-09:25"
    assert verdict["fallback"] == "open_gap"
    assert verdict["detail"] == NOT_CONFIGURED_DETAIL


def test_in_window_rows_are_available():
    verdict = _probe(FakeAuctionProvider(rows=_rows((16, 0), (20, 0))))
    assert verdict["status"] == "available"
    assert verdict["window"] == "09:15-09:25"
    assert verdict["fallback"] == "open_gap"
    assert verdict["source"] == "fake_auction"


def test_0930_only_rows_are_fail_closed_never_available():
    """T-16-01: 09:30+ 连续竞价 bar 永远不能产生 available。"""
    verdict = _probe(FakeAuctionProvider(rows=_rows((30, 0), (35, 0))))
    assert verdict["status"] == "fail_closed"
    assert verdict["status"] != "available"
    assert verdict["detail"] == FAIL_CLOSED_DETAIL


def test_empty_rows_are_fail_closed():
    verdict = _probe(FakeAuctionProvider(rows=pl.DataFrame()))
    assert verdict["status"] == "fail_closed"


def test_raising_provider_is_error():
    verdict = _probe(FakeAuctionProvider(exc=RuntimeError("upstream timeout")))
    assert verdict["status"] == "error"
    assert "upstream timeout" in verdict["detail"]
    # T-16-05: error detail 是有界的
    assert len(verdict["detail"]) <= 200


# ================================================================
# 诚实标签回归 (DATA-03 / T-16-01) —— 09:30 bar 永不是集合竞价数据
# ================================================================


def test_verdict_window_and_fallback_are_fixed_for_every_status():
    """每个状态都携带固定的 window="09:15-09:25" 与 fallback="open_gap"。"""
    cases = {
        "not_configured": lambda: resolve_auction_probe(source_resolver=lambda: []).to_dict(),
        "available": lambda: _probe(FakeAuctionProvider(rows=_rows((16, 0)))),
        "fail_closed": lambda: _probe(FakeAuctionProvider(rows=_rows((31, 0)))),
        "error": lambda: _probe(FakeAuctionProvider(exc=RuntimeError("boom"))),
    }
    for status, build in cases.items():
        verdict = build()
        assert verdict["status"] == status
        assert verdict["window"] == "09:15-09:25"
        assert verdict["fallback"] == "open_gap"


def test_all_0930_rows_can_never_produce_available():
    """结构性守卫: 全部 >= 09:30 的行只能 fail_closed, 永不 available。"""
    for rows in [_rows((30, 0)), _rows((31, 0), (35, 0))]:
        verdict = _probe(FakeAuctionProvider(rows=rows))
        assert verdict["status"] == "fail_closed"
        assert verdict["status"] != "available"


def test_fail_closed_detail_matches_approved_copy_verbatim():
    """fail-closed 详情串在服务端逐字匹配批准文案, 诚实标签不可漂移。"""
    verdict = _probe(FakeAuctionProvider(rows=_rows((30, 0))))
    assert verdict["detail"] == (
        "平台未检测到可用的集合竞价匹配数据，已退化到派生开盘涨幅因子"
        "（open / prev_close − 1）。09:30 起的连续竞价 bar 不会被标记为集合竞价数据。"
    )


def test_not_configured_detail_matches_approved_copy_verbatim():
    verdict = resolve_auction_probe(source_resolver=lambda: []).to_dict()
    assert verdict["detail"] == (
        "尚未配置竞价数据源；配置后平台将自动探测 9:15–9:25 "
        "集合竞价匹配数据的可用性。"
    )


# ================================================================
# FastAPI endpoints
# ================================================================


@pytest.fixture(autouse=True)
def _reset_probe_cache():
    data_api._auction_probe_cache = None
    data_api._auction_probe_cache_ts = 0.0
    yield


@pytest.fixture
def probe_client() -> TestClient:
    app = FastAPI()
    app.include_router(data_api.router)
    return TestClient(app)


def test_get_auction_probe_returns_verdict_json(probe_client: TestClient):
    resp = probe_client.get("/api/data/auction-probe")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {str(s) for s in AuctionProbeStatus}
    assert body["window"] == "09:15-09:25"
    assert body["fallback"] == "open_gap"


def test_redetect_bypasses_cache(probe_client: TestClient, monkeypatch):
    import app.services.auction_probe as ap

    first = ap.AuctionProbeVerdict(
        status=ap.AuctionProbeStatus.not_configured,
        source=None,
        probed_at=None,
        detail="first",
    )
    second = ap.AuctionProbeVerdict(
        status=ap.AuctionProbeStatus.available,
        source="fake_auction",
        probed_at="2026-08-04T00:00:00+00:00",
        detail="second",
    )
    monkeypatch.setattr(ap, "resolve_auction_probe", lambda **kw: first)
    assert probe_client.get("/api/data/auction-probe").json()["status"] == "not_configured"

    # GET 走 30s TTL 缓存, 即使服务端判定已变化仍返回旧判定
    monkeypatch.setattr(ap, "resolve_auction_probe", lambda **kw: second)
    assert probe_client.get("/api/data/auction-probe").json()["status"] == "not_configured"

    # POST/redetect 绕过缓存, 返回新鲜判定
    fresh = probe_client.post("/api/data/auction-probe/redetect").json()
    assert fresh["status"] == "available"
    assert fresh["source"] == "fake_auction"
