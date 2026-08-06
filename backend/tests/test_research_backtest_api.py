"""竞价回测结果查询端点测试 (BT-09) — hermetic: tmp data_dir 手工写 backtest_results 湖
(34-01 布局逐字: run_id={id}/part.parquet + manifest.json), 零网络, 不触碰 data/。

镜像 test_auction_validation_report.py 端点形 (TestClient + stub auth + router include);
端点只读 ``settings.data_dir`` → monkeypatch 到 tmp_path。生产 import 全放测试函数内
(仓库约定: 模块级不触发 DuckDB 单例)。
"""
from __future__ import annotations

import json
from datetime import date

import polars as pl
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


def _make_client() -> TestClient:
    """最小 FastAPI 应用 + stub auth + include research_backtest router (镜像
    test_auction_validation_report.py:641-656 形)。"""
    from app.api import research_backtest as research_backtest_api

    app = FastAPI()
    app.state.repo = None
    app.state.strategy_engine = None

    @app.middleware("http")
    async def _stub_auth(request: Request, call_next):
        if request.cookies.get("tf_session") == "vip-token":
            request.state.reviewer_principal = "reviewer_test"
        return await call_next(request)

    app.include_router(research_backtest_api.router)
    return TestClient(app)


@pytest.fixture
def lake(tmp_path, monkeypatch):
    """tmp data_dir (monkeypatch settings.data_dir) — 端点只读湖面, 零网络。"""
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return tmp_path


def _seed_run(data_dir, run_id: str, manifest: dict, rows: pl.DataFrame) -> None:
    """手工写盘 34-01 布局: backtest_results/run_id={id}/part.parquet + manifest.json。"""
    run_dir = data_dir / "backtest_results" / f"run_id={run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    rows.write_parquet(run_dir / "part.parquet")
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )


def _seed_vectorbt_flat_file(data_dir, run_id: str = "abc123") -> None:
    """vectorbt 平面文件先例 (services/backtest.py:358-371): run_id={id}.parquet,
    无 manifest —— 列运行端点必须诚实跳过。"""
    out = data_dir / "backtest_results" / f"run_id={run_id}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"run_id": [run_id], "stats_json": ["{}"], "n_trades": [0]}).write_parquet(out)


def _manifest(run_id: str, created_at: str, strategies: list[dict], per_date: list[dict] | None = None) -> dict:
    """34-01 manifest 骨架 (字段集逐字: run_id/origin/strategy_version/created_at/
    window/strategies/params/coverage/per_date/minute_note/fingerprint)。"""
    return {
        "run_id": run_id,
        "origin": "research",
        "strategy_version": "7affa346e5e586c5",
        "created_at": created_at,
        "window": {
            "requested_start": "2026-07-01", "requested_end": "2026-08-05",
            "effective_start": "2026-07-01", "effective_end": "2026-08-05",
        },
        "strategies": strategies,
        "params": {},
        "coverage": {
            "dates": {"auction_enabled_count": 26, "enriched_count": 26, "coverage_ratio": 1.0},
            "symbols": {
                "auction_symbol_count": 2, "enriched_symbol_count": 5293,
                "symbol_coverage_ratio": 2 / 5293, "auction_rows_present": 52,
                "auction_rows_expected": 5293 * 26,
            },
        },
        "per_date": per_date or [{"date": "2026-08-01", "n_screened": 100, "n_hits": 5}],
        "minute_note": "kline_minute 历史 CLOSED (BT-10)",
        "fingerprint": f"fp-{run_id}",
    }


def _rows(rows: list[dict]) -> pl.DataFrame:
    """长格式命中行帧 (34-01 _ROW_SCHEMA 逐字 17 列); as_of 传 date。"""
    return pl.DataFrame({
        "run_id": [r["run_id"] for r in rows],
        "strategy": [r["strategy"] for r in rows],
        "branch": [r["branch"] for r in rows],
        "as_of": [r["as_of"] for r in rows],
        "symbol": [r["symbol"] for r in rows],
        "entry_open": [r.get("entry_open", 10.0) for r in rows],
        "open_t1": [r.get("open_t1", 10.2) for r in rows],
        "close_t1": [r.get("close_t1", 10.5) for r in rows],
        "next_day_open_ret": [r.get("next_day_open_ret", 0.02) for r in rows],
        "next_day_close_ret": [r.get("next_day_close_ret", 0.05) for r in rows],
        "open_gap_outcome": [r.get("open_gap_outcome", 0.01) for r in rows],
        "outcome_missing": [r.get("outcome_missing", False) for r in rows],
        "params_json": [r.get("params_json", "{}") for r in rows],
        "strategy_version": [r.get("strategy_version", "7affa346e5e586c5") for r in rows],
        "origin": [r.get("origin", "research") for r in rows],
        "minute_confirm": [r.get("minute_confirm", "not_applied") for r in rows],
        "created_at": [r.get("created_at", "2026-08-06T00:00:00+00:00") for r in rows],
    })


def test_backtest_query_list_and_detail(lake, monkeypatch):
    """列运行: 两 run 目录 (异 run_id/created_at) + 1 vectorbt 平面文件 → runs==2
    (平面诚实跳过), count==2, created_at 降序, 字段集完整; 详情: manifest 回显 +
    stats.n_rows==行数 + sample≤20; 空湖 → {runs:[], count:0} 200。"""
    d1, d2, d3 = date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)
    _seed_run(
        lake, "aaaa1111bbbb",
        _manifest("aaaa1111bbbb", "2026-08-06T10:00:00+00:00",
                  [{"id": "golden_230", "branch": "eod"}],
                  per_date=[{"date": d1.isoformat(), "n_screened": 20, "n_hits": 3}]),
        _rows([
            {"run_id": "aaaa1111bbbb", "strategy": "golden_230", "branch": "eod", "as_of": d1, "symbol": "000001.SZ"},
            {"run_id": "aaaa1111bbbb", "strategy": "golden_230", "branch": "eod", "as_of": d2, "symbol": "000001.SZ"},
            {"run_id": "aaaa1111bbbb", "strategy": "golden_230", "branch": "eod", "as_of": d3, "symbol": "000001.SZ"},
        ]),
    )
    _seed_run(
        lake, "cccc3333dddd",
        _manifest("cccc3333dddd", "2026-08-05T09:00:00+00:00",
                  [{"id": "auction_fast_grab", "branch": "real"}],
                  per_date=[{"date": d1.isoformat(), "n_screened": 2, "n_hits": 1}]),
        _rows([
            {"run_id": "cccc3333dddd", "strategy": "auction_fast_grab", "branch": "real", "as_of": d1, "symbol": "000001.SZ"},
            {"run_id": "cccc3333dddd", "strategy": "auction_fast_grab", "branch": "real", "as_of": d2, "symbol": "000002.SZ"},
        ]),
    )
    _seed_vectorbt_flat_file(lake)

    client = _make_client()

    resp = client.get("/api/research/backtest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2  # vectorbt 平面文件诚实跳过
    assert [r["run_id"] for r in body["runs"]] == ["aaaa1111bbbb", "cccc3333dddd"]  # created_at 降序
    item = body["runs"][0]
    assert set(item) == {"run_id", "created_at", "origin", "strategy_version", "window",
                         "n_strategies", "n_hits", "coverage"}
    assert item["n_strategies"] == 1
    assert item["n_hits"] == 3
    assert item["coverage"]["symbols"]["auction_symbol_count"] == 2
    assert item["origin"] == "research"
    assert item["strategy_version"] == "7affa346e5e586c5"

    resp = client.get("/api/research/backtest/aaaa1111bbbb")
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["manifest"]["run_id"] == "aaaa1111bbbb"
    assert detail["manifest"]["window"]["effective_end"] == "2026-08-05"
    assert detail["stats"]["n_rows"] == 3
    assert detail["stats"]["n_hits"] == 3
    assert len(detail["sample"]) == 3  # ≤20
    assert detail["sample"][0]["strategy"] == "golden_230"
    assert detail["sample"][0]["as_of"] == "2026-08-01"  # date 序列化 ISO
    dates = {pd["date"] for pd in detail["stats"]["per_date"]}
    assert dates == {"2026-08-01", "2026-08-02", "2026-08-03"}
    strategies = {ps["strategy"] for ps in detail["stats"]["per_strategy"]}
    assert strategies == {"golden_230"}

    # 空湖 → 200 诚实空 (绝不 404/500)
    empty_dir = lake / "empty_lake"
    empty_dir.mkdir()
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", empty_dir)
    resp = client.get("/api/research/backtest")
    assert resp.status_code == 200
    assert resp.json() == {"runs": [], "count": 0}


def test_backtest_query_filters(lake, monkeypatch):
    """列运行 ?strategy=/?branch= 过滤 + 详情谓词下推 (strategy/branch/as_of/symbol)
    → stats.n_rows 精确收缩 (手算子集)。"""
    d1, d2, d3 = date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)
    rows = (
        [{"run_id": "aaaa1111bbbb", "strategy": "golden_230", "branch": "eod", "as_of": d, "symbol": s}
         for d in (d1, d2, d3) for s in ("000001.SZ", "000002.SZ")]
        + [{"run_id": "aaaa1111bbbb", "strategy": "auction_bullish", "branch": "eod", "as_of": d, "symbol": "000001.SZ"}
           for d in (d1, d2, d3)]
        + [{"run_id": "aaaa1111bbbb", "strategy": "auction_fast_grab", "branch": "real", "as_of": d1, "symbol": s}
           for s in ("000001.SZ", "000002.SZ")]
    )
    _seed_run(
        lake, "aaaa1111bbbb",
        _manifest(
            "aaaa1111bbbb", "2026-08-06T10:00:00+00:00",
            [
                {"id": "golden_230", "branch": "eod"},
                {"id": "auction_bullish", "branch": "eod"},
                {"id": "auction_fast_grab", "branch": "real"},
            ],
        ),
        _rows(rows),
    )
    _seed_run(
        lake, "cccc3333dddd",
        _manifest("cccc3333dddd", "2026-08-05T09:00:00+00:00",
                  [{"id": "auction_alpha", "branch": "derived"}]),
        _rows([
            {"run_id": "cccc3333dddd", "strategy": "auction_alpha", "branch": "derived", "as_of": d1, "symbol": "000001.SZ"},
        ]),
    )
    client = _make_client()

    # 列运行过滤: ?strategy= 只留含该策略的 run; ?branch= 只留含该 branch 的 run
    resp = client.get("/api/research/backtest", params={"strategy": "auction_bullish"})
    assert resp.status_code == 200
    assert [r["run_id"] for r in resp.json()["runs"]] == ["aaaa1111bbbb"]
    assert resp.json()["count"] == 1

    resp = client.get("/api/research/backtest", params={"strategy": "auction_alpha"})
    assert [r["run_id"] for r in resp.json()["runs"]] == ["cccc3333dddd"]

    resp = client.get("/api/research/backtest", params={"branch": "real"})
    assert [r["run_id"] for r in resp.json()["runs"]] == ["aaaa1111bbbb"]

    resp = client.get("/api/research/backtest", params={"branch": "eod"})
    assert resp.json()["count"] == 1  # 只有 aaaa 含 eod 策略 (cccc 是 derived)

    resp = client.get("/api/research/backtest", params={"branch": "nonexistent"})
    assert resp.json() == {"runs": [], "count": 0}

    # 详情谓词下推: 手算子集
    base = "/api/research/backtest/aaaa1111bbbb"

    resp = client.get(base, params={"strategy": "auction_bullish"})
    assert resp.json()["stats"]["n_rows"] == 3  # 3 日 × 1 symbol

    resp = client.get(base, params={"strategy": "golden_230", "symbol": "000001.SZ"})
    assert resp.json()["stats"]["n_rows"] == 3  # 3 日 × 1 symbol

    resp = client.get(base, params={"branch": "real"})
    assert resp.json()["stats"]["n_rows"] == 2  # d1 × 2 symbol

    resp = client.get(base, params={"as_of": "2026-08-02"})
    assert resp.json()["stats"]["n_rows"] == 3  # golden×2 + bullish×1 (d2 无 real 行)

    resp = client.get(base, params={"strategy": "golden_230", "branch": "eod",
                                     "as_of": "2026-08-01", "symbol": "000002.SZ"})
    assert resp.json()["stats"]["n_rows"] == 1

    resp = client.get(base, params={"symbol": "no_such_symbol"})
    assert resp.json()["stats"]["n_rows"] == 0
    assert resp.json()["stats"]["n_hits"] == 0

    # 详情 per_strategy/per_date 与谓词一致
    resp = client.get(base, params={"branch": "eod"})
    detail = resp.json()
    assert detail["stats"]["n_rows"] == 9  # golden 6 + bullish 3
    assert {ps["strategy"] for ps in detail["stats"]["per_strategy"]} == {"golden_230", "auction_bullish"}
    assert {ps["branch"] for ps in detail["stats"]["per_strategy"]} == {"eod"}


def test_backtest_query_unknown_run_404(lake):
    """未知 run_id → 404 RESEARCH_BACKTEST; 坏格式 run_id → 400 (T-34-03-06)。"""
    client = _make_client()

    resp = client.get("/api/research/backtest/000000000000")  # 格式合法但不存在
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "RESEARCH_BACKTEST"
    assert resp.json()["detail"]["message"] == "run not found"

    resp = client.get("/api/research/backtest/NOT_A_RUN_ID")  # 非 12-hex
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "RESEARCH_BACKTEST"

    resp = client.get("/api/research/backtest/aaaa1111bbbb", params={"as_of": "2026-99-99"})
    assert resp.status_code == 422  # 坏日期 → FastAPI 422 (Query date 形)


def test_backtest_query_skips_vectorbt_flat_files(lake):
    """仅 vectorbt 平面文件 (run_id={id}.parquet, 无 manifest) → 诚实跳过, runs 空
    (200, 绝不误读/不报错), 与既有湖共存。"""
    _seed_vectorbt_flat_file(lake)
    _seed_vectorbt_flat_file(lake, run_id="feed00")

    client = _make_client()
    resp = client.get("/api/research/backtest")
    assert resp.status_code == 200
    assert resp.json() == {"runs": [], "count": 0}

    resp = client.get("/api/research/backtest/abc123000000")
    assert resp.status_code == 404  # 平面文件不是 research 运行, 诚实 not-found
