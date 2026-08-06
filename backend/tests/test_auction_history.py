"""CHART-01 竞价历史只读聚合端点测试 — 末行聚合/诚实空态/400 校验/guest 掩码/probe 透传 + POOL-03 AST 守卫。

Hermetic: 生产 import 放测试函数内 (仓库约定: 模块级不触发 DuckDB 单例)。
probe 判定被 monkeypatch 为固定 verdict; ``kline_auction`` 分区由测试手工写盘
(镜像 test_auction_columns.py:20-61); guest/vip 用 stub 中间件模拟
``request.state.reviewer_principal`` (镜像 test_guest_masking._make_guest_client)。
"""
from __future__ import annotations

import ast
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


# ================================================================
# hermetic helpers
# ================================================================


@pytest.fixture
def repo_env(tmp_path, monkeypatch):
    """隔离的 data_dir + DataStore + KlineRepository (镜像 test_auction_columns.py:20-32)。"""
    from app.config import settings
    data_dir = tmp_path / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)

    from app.tickflow.repository import DataStore, KlineRepository
    store = DataStore(data_dir)
    try:
        yield KlineRepository(store), data_dir
    finally:
        store.db.close()


def _available_verdict():
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
    return AuctionProbeVerdict(
        status=AuctionProbeStatus.available, source="fake", probed_at=None, detail="available",
    )


def _patch_probe(monkeypatch, verdict) -> None:
    """patch 目标是 app.api.auction_history.resolve_auction_probe (本端点直接 import)。"""
    from app.api import auction_history
    monkeypatch.setattr(auction_history, "resolve_auction_probe", lambda: verdict)


def _write_auction_partition(data_dir, trade_date: date, rows: pl.DataFrame) -> None:
    out = data_dir / "kline_auction" / f"date={trade_date.isoformat()}" / "part.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows.write_parquet(out)


def _multi_day_rows(symbol: str, base_date: date, days: int) -> dict[date, pl.DataFrame]:
    """构造每日期 09:16/09:20/09:25 三行 canonical 帧 (镜像 test_auction_sync._rows)。

    末行 (09:25) 值: auction_volume=300, auction_amount=3000; row_count==3。
    """
    times = [(9, 16), (9, 20), (9, 25)]
    out: dict[date, pl.DataFrame] = {}
    for i in range(days):
        d = base_date + timedelta(days=i)
        out[d] = pl.DataFrame({
            "symbol": [symbol] * len(times),
            "datetime": [datetime(d.year, d.month, d.day, h, m) for h, m in times],
            "auction_volume": [100 * (j + 1) for j in range(len(times))],
            "auction_amount": [1000 * (j + 1) for j in range(len(times))],
        })
    return out


def _make_client(repo) -> TestClient:
    """最小 FastAPI 应用 + stub 中间件: cookie ``tf_session == "vip-token"`` → 设
    ``reviewer_principal``, 否则不设 (guest)。"""
    from app.api import auction_history as auction_history_api

    app = FastAPI()
    app.state.repo = repo

    @app.middleware("http")
    async def _stub_auth(request: Request, call_next):
        if request.cookies.get("tf_session") == "vip-token":
            request.state.reviewer_principal = "reviewer_test"
        return await call_next(request)

    app.include_router(auction_history_api.router)
    return TestClient(app)


# ================================================================
# Task 1 — 末行聚合 / 诚实空态 / 校验 400 / guest 掩码 / probe 透传
# ================================================================


def test_last_row_aggregation_across_days(repo_env, monkeypatch):
    """多日分区 → 每交易日取 09:25 末行, rows 按 date 升序, 带 row_count/min/max 标注。"""
    repo, data_dir = repo_env
    _patch_probe(monkeypatch, _available_verdict())
    symbol = "000001.SZ"
    partitions = _multi_day_rows(symbol, date(2026, 8, 1), 4)
    for d, df in partitions.items():
        _write_auction_partition(data_dir, d, df)

    client = _make_client(repo)
    client.cookies.set("tf_session", "vip-token")
    resp = client.get("/api/kline/auction/history", params={"symbol": symbol, "days": 120})

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["mode"] == "vip"
    assert body["coverage"] == 4
    assert [r["date"] for r in body["rows"]] == [
        "2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04",
    ]
    for r in body["rows"]:
        assert r["auction_volume"] == 300   # 09:25 末行 (非 09:16/09:20)
        assert r["auction_amount"] == 3000
        assert r["row_count"] == 3
        assert r["min_datetime"].endswith("09:16:00")
        assert r["max_datetime"].endswith("09:25:00")
    assert body["window"] == "09:15-09:25"
    assert body["unit"] == {"auction_volume": "股", "auction_amount": "元"}


def test_empty_lake_returns_available_false(repo_env, monkeypatch):
    """湖根目录不存在 → 200 {available:false, rows:[]} (绝不 404/500/0 填充)。"""
    repo, _ = repo_env
    _patch_probe(monkeypatch, _available_verdict())

    client = _make_client(repo)
    client.cookies.set("tf_session", "vip-token")
    resp = client.get("/api/kline/auction/history", params={"symbol": "000001.SZ"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["rows"] == []
    assert body["coverage"] == 0
    assert body["mode"] == "vip"
    assert body["probe"]["status"] == "available"


def test_no_symbol_rows_returns_available_false(repo_env, monkeypatch):
    """分区存在但该 symbol 无行 → 200 {available:false, rows:[]}。"""
    repo, data_dir = repo_env
    _patch_probe(monkeypatch, _available_verdict())
    partitions = _multi_day_rows("600000.SH", date(2026, 8, 1), 2)
    for d, df in partitions.items():
        _write_auction_partition(data_dir, d, df)

    client = _make_client(repo)
    client.cookies.set("tf_session", "vip-token")
    resp = client.get("/api/kline/auction/history", params={"symbol": "000001.SZ"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["rows"] == []
    assert body["coverage"] == 0


@pytest.mark.parametrize("status", ["not_configured", "fail_closed", "error"])
def test_probe_non_available_returns_empty_with_status(repo_env, monkeypatch, status):
    """probe 非 available (not_configured/fail_closed/error) → 200 available:false + status 透传。"""
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
    repo, data_dir = repo_env
    # 湖里有数据也应为空 (probe 闸门在分区扫描之前)
    partitions = _multi_day_rows("000001.SZ", date(2026, 8, 1), 2)
    for d, df in partitions.items():
        _write_auction_partition(data_dir, d, df)

    verdict = AuctionProbeVerdict(
        status=AuctionProbeStatus(status), source="fake", probed_at=None, detail=f"{status} detail",
    )
    _patch_probe(monkeypatch, verdict)

    client = _make_client(repo)
    client.cookies.set("tf_session", "vip-token")
    resp = client.get("/api/kline/auction/history", params={"symbol": "000001.SZ"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["rows"] == []
    assert body["probe"]["status"] == status
    assert body["mode"] == "vip"


@pytest.mark.parametrize("bad", ["abc", "000001", "000001.XX", "../../x"])
def test_invalid_symbol_returns_400(repo_env, monkeypatch, bad):
    """非法 symbol → 400 (防注入/路径穿越, 镜像 pool.py 的 as_of 校验)。"""
    repo, _ = repo_env
    _patch_probe(monkeypatch, _available_verdict())

    client = _make_client(repo)
    client.cookies.set("tf_session", "vip-token")
    resp = client.get("/api/kline/auction/history", params={"symbol": bad})

    assert resp.status_code == 400


@pytest.mark.parametrize("bad_days", [0, -5, 121])
def test_invalid_days_returns_400(repo_env, monkeypatch, bad_days):
    """days 越界 (0/-5/121) → 400 (handler 内显式判断, 非 FastAPI 422)。"""
    repo, _ = repo_env
    _patch_probe(monkeypatch, _available_verdict())

    client = _make_client(repo)
    client.cookies.set("tf_session", "vip-token")
    resp = client.get(
        "/api/kline/auction/history",
        params={"symbol": "000001.SZ", "days": bad_days},
    )

    assert resp.status_code == 400


def test_guest_mask_returns_empty_mode_guest(repo_env, monkeypatch):
    """guest (无 reviewer_principal) → 200 {available:false, rows:[], mode:'guest'} 零泄露。"""
    repo, data_dir = repo_env
    _patch_probe(monkeypatch, _available_verdict())
    partitions = _multi_day_rows("000001.SZ", date(2026, 8, 1), 2)
    for d, df in partitions.items():
        _write_auction_partition(data_dir, d, df)

    client = _make_client(repo)  # 无 cookie → guest
    resp = client.get("/api/kline/auction/history", params={"symbol": "000001.SZ"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["rows"] == []
    assert body["mode"] == "guest"
    assert body["coverage"] == 0


def test_vip_gets_real_rows(repo_env, monkeypatch):
    """vip (有 reviewer_principal) → available:true, 行含真实量/额。"""
    repo, data_dir = repo_env
    _patch_probe(monkeypatch, _available_verdict())
    partitions = _multi_day_rows("000001.SZ", date(2026, 8, 1), 2)
    for d, df in partitions.items():
        _write_auction_partition(data_dir, d, df)

    client = _make_client(repo)
    client.cookies.set("tf_session", "vip-token")
    resp = client.get("/api/kline/auction/history", params={"symbol": "000001.SZ"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["mode"] == "vip"
    assert body["rows"][0]["auction_volume"] == 300
    assert body["rows"][0]["auction_amount"] == 3000


# ================================================================
# POOL-03 零执行权限守卫 (镜像 test_pool_hub.py:853-918)
# ================================================================

# 执行族 token: 出现在 auction_history import / 路由 / 响应键中即失败
_EXECUTION_TOKEN = re.compile(
    r"broker|order|execution|trade|portfolio|watchlist|position|account|transaction|下单|委托",
    re.IGNORECASE,
)

_WRITE_PATTERNS = (
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']w"),
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']wb"),
    re.compile(r"open\s*\(\s*[^,)]*,\s*[\"']a"),
    re.compile(r"write_parquet"),
    re.compile(r"os\.replace"),
    re.compile(r"unlink\s*\("),
    re.compile(r"mkdir\s*\("),
)


def _feature_sources() -> str:
    backend = Path(__file__).resolve().parents[1]
    return (backend / "app" / "api" / "auction_history.py").read_text(encoding="utf-8")


def _imported_module_names(source: str) -> list[str]:
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_auction_history_no_execution_imports():
    """auction_history.py 不得 import 任何执行族模块 (T-26-01-03, E4)。"""
    src = _feature_sources()
    for module in _imported_module_names(src):
        assert not _EXECUTION_TOKEN.search(module), (
            f"auction_history 特性引入了执行族模块: {module}"
        )


def test_auction_history_api_is_get_only():
    """auction_history.py 只允许 GET 路由 (T-26-01-03, E4)。"""
    src = _feature_sources()
    methods = re.findall(r"@router\.(get|post|put|delete|patch)\b", src)
    assert methods and set(methods) == {"get"}, f"auction API 出现了非 GET 路由: {methods}"


def test_auction_history_has_no_write_path():
    """auction_history.py 是纯读者: 无写模式 open / write_parquet / os.replace / unlink / mkdir。"""
    src = _feature_sources()
    for pattern in _WRITE_PATTERNS:
        assert not pattern.search(src), f"auction_history.py 出现写路径: {pattern.pattern}"


def test_main_guest_whitelist_and_router_registration():
    """main.py 结构门: guest 白名单 + include_router 两处命中 /api/kline/auction/history。"""
    backend = Path(__file__).resolve().parents[1]
    main_src = (backend / "app" / "main.py").read_text(encoding="utf-8")
    assert main_src.count("/api/kline/auction/history") == 2
    assert "app.include_router(auction_history.router)" in main_src
