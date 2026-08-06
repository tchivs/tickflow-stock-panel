"""竞价复盘只读端点 (REV-05) — GET /api/market-recap/auction 集成测试。

镜像 test_auction_history.py:79-92 的 guest/vip stub 中间件 + test_auction_recap.py
的 hermetic fixture (手工写盘 kline_auction 分区 / premarket_results 预览 /
_FakeRepo enriched 桩); probe verdict 经 auction_recap 模块 resolve 点注入。

覆盖 (REV-05 验收 1-5):
- as_of 严格双重校验: 合法 → 200; 非 ISO/半角/含注入串 → 400 invalid as_of (绝不 500);
- 诚实空态: 无分区 + 无预览 + enriched 空 → 200 available:false (绝不 404/500/0 填);
- 正常装配与 REV-04 面板同源: 200 dict 含 as_of/data_completeness/blocks/built_at +
  available:true + markdown (含「确定性数据，非 AI 生成」标记);
- guest 掩码 (R12 DTO): per-symbol 身份 '******' + 竞价值剥离 + 聚合保留 +
  probe 剥离 + 无 markdown; vip → 明文;
- as_of 缺省 → ScreenerService.latest_date() 解析; latest None → 诚实空态。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import polars as pl
import pytest

FIXED_DATE = date(2026, 8, 6)


# ================================================================
# hermetic helpers (镜像 test_auction_recap.py + test_auction_history.py)
# ================================================================


@pytest.fixture
def repo_env(tmp_path, monkeypatch):
    """隔离的 data_dir + DataStore + KlineRepository (镜像 test_auction_recap.py:37-47)。"""
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


class _FakeRepo:
    """最小 repo 桩 (镜像 test_auction_recap.py:_FakeRepo)。"""

    def __init__(self, data_dir, enriched=None, latest=None, instruments=None, range_panel=None):
        from types import SimpleNamespace

        self.store = SimpleNamespace(data_dir=data_dir)
        self._enriched = enriched
        self._latest = latest
        self._instruments = instruments if instruments is not None else pl.DataFrame()
        self._range_panel = range_panel

    def get_enriched_latest_asset(self, asset_type):
        return self._enriched, self._latest

    def get_instruments_asset(self, asset_type):
        return self._instruments

    def get_enriched_history(self, target_date, lookback_days):
        return None

    def get_enriched_range(self, start, end, symbols=None, columns=None):
        df = self._range_panel
        if df is None:
            return None
        df = df.filter((pl.col("date") >= start) & (pl.col("date") <= end))
        return df.sort(["symbol", "date"])


def _eod_frame(as_of=FIXED_DATE):
    """EOD enriched 帧 (change_pct/close/open 手算口径; 镜像 test_auction_recap.py)。"""
    return pl.DataFrame({
        "symbol": ["000001", "600000", "000002"],
        "name": ["平安银行", "浦发银行", "万科A"],
        "date": [as_of] * 3,
        "open": [10.0, 20.0, 30.0],
        "close": [10.6, 20.2, 29.5],
        "prev_close": [10.0, 20.0, 30.0],
        "volume": [100000.0, 200000.0, 300000.0],
        "amount": [1e6, 2e6, 3e6],
        "open_gap": [0.05, 0.02, 0.01],
        "change_pct": [0.06, 0.01, -0.017],
    })


def _write_auction_partition(data_dir, trade_date: date, rows: pl.DataFrame) -> None:
    """手工写盘 kline_auction/date=YYYY-MM-DD/part.parquet (镜像 :42-58)。"""
    out = data_dir / "kline_auction" / f"date={trade_date.isoformat()}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.write_parquet(out)


def _auction_rows(trade_date, symbol_volume):
    """canonical 分区行: 09:16/09:20/09:25 窗口行, 末行 = 09:25 最终撮合。"""
    _WINDOW_MINUTES = (16, 20, 25)
    rows = []
    for sym, (av, aa) in symbol_volume.items():
        for k in range(3):
            rows.append({
                "symbol": sym,
                "datetime": datetime(trade_date.year, trade_date.month, trade_date.day, 9, _WINDOW_MINUTES[k]),
                "auction_volume": av,
                "auction_amount": aa,
            })
    return pl.DataFrame(rows)


def _fake_verdict(status: str, source: str | None = None) -> dict:
    """AuctionProbeVerdict.to_dict 同形 dict (hermetic, 镜像 test_auction_recap.py)。"""
    return {
        "status": status,
        "source": source,
        "probed_at": "2026-08-06T09:26:00+00:00",
        "window": "09:15-09:25",
        "fallback": "open_gap",
        "detail": "hermetic verdict",
    }


def _write_premarket_preview(data_dir, today, payload):
    """经 persist_premarket_snapshot 写盘 (镜像 test_auction_recap.py:166-169)。"""
    from app.services.premarket_snapshot import persist_premarket_snapshot

    persist_premarket_snapshot(data_dir, today.isoformat(), payload)


def _preview_payload(today):
    """可持久化的盘前预览 payload — 2 竞价族策略 + 1 非族策略。"""
    return {
        "as_of": today.isoformat(),
        "available": True,
        "window": "pre_open",
        "computed_at": "2026-08-06T09:26:00",
        "provisional": True,
        "degraded": False,
        "probe": _fake_verdict("available"),
        "strategy_version": "fingerprint-abc",
        "results": {
            "auction_bullish": {
                "total": 2,
                "as_of": today.isoformat(),
                "rows": [
                    {"symbol": "000001", "name": "平安银行", "open_gap": 0.05, "change_pct": 0.051,
                     "hit_factors": ["竞价多头", "盘前强势"]},
                    {"symbol": "600000", "name": "浦发银行", "open_gap": 0.02, "change_pct": 0.021,
                     "hit_factors": ["竞价多头"]},
                ],
            },
            "golden_230": {
                "total": 1,
                "as_of": today.isoformat(),
                "rows": [
                    {"symbol": "000002", "name": "万科A", "open_gap": 0.01, "change_pct": 0.012,
                     "hit_factors": ["金色两点半"]},
                ],
            },
            "custom_a": {
                "total": 1,
                "as_of": today.isoformat(),
                "rows": [
                    {"symbol": "300001", "name": "创业板票", "open_gap": 0.03, "change_pct": 0.031,
                     "hit_factors": ["自定义"]},
                ],
            },
        },
    }


def _make_client(repo, engine=None):
    """最小 FastAPI 应用 + stub 中间件: cookie ``tf_session == "vip-token"`` → 设
    ``reviewer_principal``, 否则不设 (guest) (镜像 test_auction_history.py:79-92)。"""
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    from app.api import market_recap_auction as market_recap_auction_api

    app = FastAPI()
    app.state.repo = repo
    app.state.strategy_engine = engine

    @app.middleware("http")
    async def _stub_auth(request: Request, call_next):
        if request.cookies.get("tf_session") == "vip-token":
            request.state.reviewer_principal = "reviewer_test"
        return await call_next(request)

    app.include_router(market_recap_auction_api.router)
    return TestClient(app)


def _full_fixture(data_dir, as_of=None):
    """分区 + 预览 + enriched 三源齐备 (REV-05 验收 4 同源装配 fixture)。

    as_of 缺省 = FIXED_DATE 前一交易日 (历史日: probe 不参与闸门); 预览与 enriched
    均以 as_of 同日写盘 (预览装载按 as_of 分区匹配, 三源同日才得 full)。
    """
    as_of = as_of or (FIXED_DATE - timedelta(days=1))  # 历史日: probe 不参与闸门
    _write_auction_partition(
        data_dir, as_of,
        _auction_rows(as_of, {"000001": (8000.0, 42000.0), "600000": (9000.0, 48000.0)}),
    )
    _write_premarket_preview(data_dir, as_of, _preview_payload(as_of))
    instruments = pl.DataFrame({
        "symbol": ["000001", "600000"],
        "name": ["平安银行", "浦发银行"],
    })
    repo = _FakeRepo(
        data_dir, enriched=_eod_frame(as_of=as_of), latest=as_of, instruments=instruments,
    )
    return repo, as_of


# ================================================================
# Test 1 — as_of 严格双重校验 (REV-05 验收 2, T-31-03-01)
# ================================================================


def test_as_of_valid_returns_200(repo_env):
    """合法 as_of → 200; 非法格式全部 400 invalid as_of 且绝不 500 (路径穿越防线)。"""
    repo, data_dir = repo_env
    client = _make_client(repo)

    ok = client.get("/api/market-recap/auction", params={"as_of": "2026-08-06"})
    assert ok.status_code == 200

    for bad in ("20260806", "2026-08-06;rm -rf", "not-a-date", "2026/08/06", "2026-08-06T00:00:00"):
        resp = client.get("/api/market-recap/auction", params={"as_of": bad})
        assert resp.status_code == 400, f"as_of={bad!r} 应为 400"
        assert resp.json()["detail"] == "invalid as_of"


# ================================================================
# Test 2 — 诚实空态 (REV-05 验收 3)
# ================================================================


def test_empty_returns_available_false(repo_env):
    """无分区 + 无预览 + enriched 空 → 200 available:false 诚实空态 (绝不 404/500/0 填)。"""
    repo, data_dir = repo_env
    repo = _FakeRepo(data_dir, enriched=pl.DataFrame(), latest=FIXED_DATE)
    client = _make_client(repo)

    resp = client.get("/api/market-recap/auction", params={"as_of": "2026-08-06"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["blocks"] == {}
    assert body["reason"]
    assert isinstance(body["data_completeness"], str) and body["data_completeness"]
    assert "as_of" in body


# ================================================================
# Test 3 — 正常装配 (REV-05 验收 4 同源: 与 REV-04 面板同一装配函数)
# ================================================================


def test_full_assembly_vip(repo_env):
    """vip: 分区+预览+enriched → 200 dict 含 as_of/data_completeness/blocks
    (real_auction_activity present)/built_at + available:true + markdown 确定性标记。"""
    from app.services.auction_recap import render_auction_recap_markdown

    repo, data_dir = repo_env
    repo_full, as_of = _full_fixture(data_dir)
    client = _make_client(repo_full, engine=None)
    client.cookies.set("tf_session", "vip-token")

    resp = client.get("/api/market-recap/auction", params={"as_of": as_of.isoformat()})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["as_of"] == as_of.isoformat()
    assert body["data_completeness"] == "full"
    assert body["blocks"]["real_auction_activity"]["present"] is True
    assert body["blocks"]["real_auction_activity"]["top_n"][0]["symbol"] == "600000"
    assert "built_at" in body
    md = body["markdown"]
    assert "确定性数据，非 AI 生成" in md
    # 与 REV-04 面板同源: markdown 由同一渲染纯函数产出
    assert md == render_auction_recap_markdown(
        {k: v for k, v in body.items() if k != "available" and k != "markdown"},
    )


# ================================================================
# Test 4 — guest 掩码 (REV-05 验收 5, R12 DTO 锁定, T-31-03-02)
# ================================================================


def test_guest_masking(repo_env):
    """guest: per-symbol 身份 '******' + 竞价值剥离 + 聚合保留 + probe 剥离 + 无 markdown;
    vip → 明文 symbol + 竞价值 + probe (若有)。"""
    repo, data_dir = repo_env
    repo_full, as_of = _full_fixture(data_dir)
    client = _make_client(repo_full)

    # guest (无 cookie)
    resp = client.get("/api/market-recap/auction", params={"as_of": as_of.isoformat()})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert "markdown" not in body  # 掩码视图无渲染文本, 诚实
    blk = body["blocks"]["real_auction_activity"]
    assert blk["present"] is True
    # 聚合统计保留 (非 PII, 镜像 mask_guest_alert 语义)
    assert blk["n_symbols"] == 2
    assert blk["total_amount"] == pytest.approx(42000.0 + 48000.0)
    for t in blk["top_n"]:
        assert t["symbol"] == "******"
        assert t["name"] == "******"
        assert t["code"] == "******"
        assert "auction_amount" not in t
        assert "open_gap" not in t
        assert "auction_volume_ratio" not in t
    # probe verdict 剥离 (镜像 mask_guest_alert 剥 probe 先例)
    assert "probe" not in blk
    # 状态标注与 data_completeness 保留
    assert body["data_completeness"] == "full"
    sig = body["blocks"]["preopen_signal_quality"]
    assert sig["present"] is True
    assert sig["provisional"] is True
    assert "probe" not in sig
    for sid, st in sig["strategies"].items():
        assert "display_name" in st
        assert "n" in st
    og = body["blocks"]["open_gap_snapshot"]
    assert og["present"] is True
    for t in og["top_n"]:
        assert t["symbol"] == "******"
        assert t["name"] == "******"
        assert "open_gap" not in t
    assert og["high_open_count"] == 2  # 聚合保留

    # vip → 明文 symbol + 竞价值 + probe (若有)
    client.cookies.set("tf_session", "vip-token")
    resp2 = client.get("/api/market-recap/auction", params={"as_of": as_of.isoformat()})
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["markdown"]
    blk2 = body2["blocks"]["real_auction_activity"]
    assert blk2["top_n"][0]["symbol"] == "600000"
    assert "auction_amount" in blk2["top_n"][0]
    assert body2["blocks"]["open_gap_snapshot"]["top_n"][0]["symbol"] == "000001"


# ================================================================
# Test 5 — as_of 缺省 → latest_date (REV-05 缺省口径)
# ================================================================


def test_as_of_default_latest_date(repo_env, monkeypatch):
    """无 as_of 参数 → ScreenerService.latest_date() 解析; latest None → 诚实空态。"""
    from app.services.screener import ScreenerService

    repo, data_dir = repo_env
    repo_full, as_of = _full_fixture(data_dir)
    client = _make_client(repo_full)
    client.cookies.set("tf_session", "vip-token")

    monkeypatch.setattr(ScreenerService, "latest_date", lambda self: as_of)
    resp = client.get("/api/market-recap/auction")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["as_of"] == as_of.isoformat()
    assert body["blocks"]["real_auction_activity"]["present"] is True

    # latest None (无数据日) → 200 诚实空态 (绝不 500)
    repo_empty = _FakeRepo(data_dir, enriched=pl.DataFrame(), latest=None)
    client2 = _make_client(repo_empty)
    client2.cookies.set("tf_session", "vip-token")
    monkeypatch.setattr(ScreenerService, "latest_date", lambda self: None)
    resp2 = client2.get("/api/market-recap/auction")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["available"] is False
    assert body2["blocks"] == {}
