"""CONCEPT-06 共享 seam — _dimension_rank / _load_concept_map_df / build_rps_rotation as_of 分支测试。

Hermetic: 全部走 tmp_path, 不触碰真实 data/ 目录; 生产代码 import 一律放测试函数内
(顶层只 import stdlib / polars / pytest)。
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

_AS_OF = "2026-08-04"

# 符号映射: X / Y / Z (镜像 test_concept_history)
_SYMBOLS = {
    "X": "600000.SH",
    "Y": "600001.SH",
    "Z": "600002.SH",
    "W": "600003.SH",
}

_NAMES = {
    "X": "人工智能龙头",
    "Y": "宁德新能源",
    "Z": "新能科技",
    "W": "早盘之星科技",
}


# ---------------------------------------------------------------------------
# Hermetic fixtures (写侧)
# ---------------------------------------------------------------------------

def _write_concept_ext(data_dir: Path, kind: str = "gn_ths", rows: list[dict] | None = None) -> None:
    """写入 hermetic 当前 ext 快照 (config.json + part.parquet)。镜像 test_concept_history。"""
    from app.services.ext_data import ExtConfig, ExtField, PullConfig

    config_id = "ext_gn_ths" if kind == "gn_ths" else "ext_hy_ths"
    field_name = "所属概念" if kind == "gn_ths" else "所属同花顺行业"
    if rows is None:
        rows = [
            {
                "symbol": _SYMBOLS["X"], "code": "600000", "股票代码": "600000",
                "股票简称": _NAMES["X"], field_name: "人工智能",
            },
            {
                "symbol": _SYMBOLS["Y"], "code": "600001", "股票代码": "600001",
                "股票简称": _NAMES["Y"], field_name: "人工智能;新能源",
            },
            {
                "symbol": _SYMBOLS["Z"], "code": "600002", "股票代码": "600002",
                "股票简称": _NAMES["Z"], field_name: "新能源",
            },
        ]
    config = ExtConfig(
        id=config_id,
        label="扩展概念" if kind == "gn_ths" else "扩展行业",
        mode="snapshot",
        fields=[
            ExtField("symbol", "string", "标的代码"),
            ExtField("code", "string", "代码"),
            ExtField("股票代码", "string", "股票代码"),
            ExtField("股票简称", "string", "股票简称"),
            ExtField(field_name, "string", field_name),
        ],
        description="hermetic concept fixture",
        symbol_map={"type": "mapped", "col": "股票代码"},
        code_map={"type": "computed", "from": "symbol", "method": "strip_exchange"},
        pull=PullConfig(url="https://example.com/concepts.json", enabled=False),
    )
    cfg_dir = data_dir / "ext_data" / config_id
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(
        json.dumps(config.to_dict(), ensure_ascii=False), encoding="utf-8"
    )
    if rows:
        pl.DataFrame(rows).write_parquet(cfg_dir / "part.parquet")


def _write_partition_fixture(data_dir: Path, kind: str, as_of: str, field: str, rows: list[dict]) -> None:
    """直写 ext_history/{kind}/date={as_of}/part.parquet + manifest.json (读侧用例, 不依赖 capture)。"""
    part_dir = data_dir / "ext_history" / kind / f"date={as_of}"
    part_dir.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(part_dir / "part.parquet")
    manifest = {
        "as_of": as_of,
        "kind": kind,
        "dimension_field": field,
        "source_url": "https://example.com/concepts.json",
        "fetched_at": "2026-08-04T09:00:00",
        "captured_at": "2026-08-04T10:00:00",
        "rows": len(rows),
        "schema_version": 1,
        "sha256": "abc123",
    }
    (part_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )


def _overview_rows() -> list[dict]:
    """_dimension_rank 输入: 总览行 (quote_map 源)。X 大涨(+5.1%), Y 下跌(-2.0%), Z 中涨(+3.0%)。"""
    return [
        {"symbol": _SYMBOLS["X"], "name": _NAMES["X"], "change_pct": 0.051, "amount": 1_000_000.0, "volume": 100_000.0},
        {"symbol": _SYMBOLS["Y"], "name": _NAMES["Y"], "change_pct": -0.02, "amount": 500_000.0, "volume": 80_000.0},
        {"symbol": _SYMBOLS["Z"], "name": _NAMES["Z"], "change_pct": 0.03, "amount": 300_000.0, "volume": 60_000.0},
    ]


def _enriched_hist_frame() -> pl.DataFrame:
    """含 _AS_OF 日 + 前几日行的 enriched 历史帧 (symbol/date/change_pct/窄列)。

    每 symbol 的 change_pct 与 _overview_rows() 一致: X 大涨(+5.1%), Y 下跌(-2.0%),
    Z 中涨(+3.0%) — 让 build_market_overview 聚合出的 leading 顺序可区分。
    """
    change_by_sym = {
        _SYMBOLS["X"]: 0.051,
        _SYMBOLS["Y"]: -0.02,
        _SYMBOLS["Z"]: 0.03,
    }
    rows: list[dict] = []
    for d in (date(2026, 7, 30), date(2026, 7, 31), date(2026, 8, 3), date(2026, 8, 4)):
        for sym in (_SYMBOLS["X"], _SYMBOLS["Y"], _SYMBOLS["Z"]):
            rows.append({
                "symbol": sym,
                "date": d,
                "change_pct": change_by_sym[sym],
                "close": 10.0,
                "amount": 100_000.0,
                "volume": 100_000.0,
                "turnover_rate": 0.02,
                "vol_ratio_5d": 1.0,
                "consecutive_limit_ups": 0,
                "signal_limit_up": False,
                "signal_broken_limit_up": False,
                "signal_limit_down": False,
                "high_60d": 12.0,
                "low_60d": 8.0,
                "ma5": 10.0,
                "ma20": 10.0,
                "ma60": 10.0,
                "signal_n_day_high": False,
                "signal_n_day_low": False,
            })
    return pl.DataFrame(rows)


class _FakeOverviewRepo:
    """最小总览 repo 桩: ScreenerService 读历史缓存 + store.data_dir + 指数回退空。"""

    def __init__(self, data_dir: Path, hist_frame: pl.DataFrame | None):
        self.store = SimpleNamespace(data_dir=data_dir)
        self._hist = hist_frame
        self._instruments = pl.DataFrame()
        self._enriched_cache_date = date(2026, 8, 4)

    def get_enriched_latest_asset(self, asset_type):
        return None, None

    def get_instruments_asset(self, asset_type):
        return self._instruments

    def get_enriched_history(self, target_date, lookback_days):
        return self._hist

    def enriched_latest_date(self):
        return self._enriched_cache_date

    def execute_all(self, sql, params=None):
        return []


class _FakeRpsRepo:
    """最小 RPS repo 桩: _enriched_history_cache + get_enriched_range + store.data_dir。"""

    def __init__(self, data_dir: Path, hist_frame: pl.DataFrame | None):
        self.store = SimpleNamespace(data_dir=data_dir)
        self._enriched_history_cache = hist_frame

    def get_enriched_range(self, start, end, symbols=None, columns=None):
        cache = self._enriched_history_cache
        if cache is None or cache.is_empty() or "date" not in cache.columns:
            return None
        df = cache.filter((pl.col("date") >= start) & (pl.col("date") <= end))
        if df.is_empty():
            return df
        if symbols is not None:
            df = df.filter(pl.col("symbol").is_in(symbols))
        if columns and not df.is_empty():
            existing = [c for c in columns if c in df.columns]
            if "symbol" not in existing and "symbol" in df.columns:
                existing.insert(0, "symbol")
            if "date" not in existing and "date" in df.columns:
                existing.insert(1, "date")
            df = df.select(existing)
        return df.sort(["symbol", "date"])


def _rps_hist_frame() -> pl.DataFrame:
    """RPS 输入: 多交易日 change_pct 帧 (symbol/date/change_pct)。"""
    rows = []
    for d in (date(2026, 7, 30), date(2026, 7, 31), date(2026, 8, 3), date(2026, 8, 4)):
        for sym, chg in ((_SYMBOLS["X"], 0.051), (_SYMBOLS["Y"], -0.02), (_SYMBOLS["Z"], 0.03)):
            rows.append({"symbol": sym, "date": d, "change_pct": chg})
    return pl.DataFrame(rows)


def _write_strategy_cache(data_dir: Path) -> None:
    """写入 hermetic 策略缓存 — 单一 as_of, 3 策略 (镜像 test_concept_history)。"""
    payload = {
        "as_of": _AS_OF,
        "results": {
            "auction_bullish": {
                "total": 2,
                "as_of": _AS_OF,
                "rows": [
                    {"symbol": _SYMBOLS["X"], "name": _NAMES["X"], "open_gap": 3.21, "change_pct": 5.1, "hit_factors": ["竞价多头"]},
                    {"symbol": _SYMBOLS["Y"], "name": _NAMES["Y"], "open_gap": 1.5, "change_pct": 2.3, "hit_factors": ["盘前强势量化", "竞价多头"]},
                ],
            },
            "auction_preopen_quant": {
                "total": 2,
                "as_of": _AS_OF,
                "rows": [
                    {"symbol": _SYMBOLS["Y"], "name": _NAMES["Y"], "open_gap": 1.5, "hit_factors": ["盘前强势量化", "竞价多头"]},
                    {"symbol": _SYMBOLS["Z"], "name": _NAMES["Z"], "open_gap": 0.5, "hit_factors": ["盘前强势量化"]},
                ],
            },
            "auction_early_star": {
                "total": 1,
                "as_of": _AS_OF,
                "rows": [
                    {"symbol": _SYMBOLS["W"], "name": "早盘之星科技", "open_gap": 0.1, "change_pct": 0.9, "hit_factors": ["早盘之星"]},
                ],
            },
        },
        "updated_at": 1722758400000,
    }
    path = data_dir / "user_data" / "strategy_cache.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_snapshot(data_dir: Path, as_of: str = _AS_OF) -> Path:
    """写冻结式点快照 part.json (镜像 test_concept_history)。"""
    payload = {
        "as_of": as_of,
        "computed_at": "2026-08-04T15:30:00",
        "strategy_version": "fp-test",
        "snapshot_type": "point",
        "schema_version": 1,
        "snapshot_origin": "eod",
        "results": {
            "auction_bullish": {
                "total": 2,
                "as_of": as_of,
                "rows": [
                    {"symbol": _SYMBOLS["X"], "name": _NAMES["X"], "open_gap": 3.21, "change_pct": 5.1, "hit_factors": ["竞价多头"]},
                    {"symbol": _SYMBOLS["Y"], "name": _NAMES["Y"], "open_gap": 1.5, "change_pct": 2.3, "hit_factors": ["盘前强势量化", "竞价多头"]},
                ],
            },
            "auction_preopen_quant": {
                "total": 2,
                "as_of": as_of,
                "rows": [
                    {"symbol": _SYMBOLS["Y"], "name": _NAMES["Y"], "open_gap": 1.5, "hit_factors": ["盘前强势量化", "竞价多头"]},
                    {"symbol": _SYMBOLS["Z"], "name": _NAMES["Z"], "open_gap": 0.5, "hit_factors": ["盘前强势量化"]},
                ],
            },
            "auction_early_star": {
                "total": 1,
                "as_of": as_of,
                "rows": [
                    {"symbol": _SYMBOLS["W"], "name": "早盘之星科技", "open_gap": 0.1, "change_pct": 0.9, "hit_factors": ["早盘之星"]},
                ],
            },
        },
    }
    path = data_dir / "screener_results" / f"date={as_of}" / "part.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _reset_rps_caches() -> None:
    """清空 RPS 模块级缓存 (600s 概念映射 + 120s 结果缓存), 防跨测试污染。"""
    from app.services import rps_rotation

    rps_rotation._map_cache.clear()
    rps_rotation._map_ts.clear()
    rps_rotation._cache.clear()
    rps_rotation._cache_ts.clear()


# ---------------------------------------------------------------------------
# Task 1 — CONCEPT-06 总览 seam: _dimension_rank as_of + build_market_overview 接线
# ---------------------------------------------------------------------------

def test_dimension_rank_as_of_partition_priority(tmp_path):
    """CONCEPT-06: _dimension_rank(..., as_of=D) 由 D 日概念分区聚合; 无 as_of 走当前 ext → 结果不同。"""
    from app.services.market_overview_builder import _dimension_rank

    _write_concept_ext(tmp_path, kind="gn_ths")  # 当前 ext: X→人工智能, Y→人工智能;新能源, Z→新能源
    # D 日分区: 内容与当前 ext 不同 — X/Y→新能源, Z→半导体
    _write_partition_fixture(tmp_path, "gn_ths", _AS_OF, "所属概念", [
        {"symbol": _SYMBOLS["X"], "所属概念": "新能源"},
        {"symbol": _SYMBOLS["Y"], "所属概念": "新能源"},
        {"symbol": _SYMBOLS["Z"], "所属概念": "半导体"},
    ])
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    rows = _overview_rows()

    as_of_rank = _dimension_rank(rows, repo, "concept", as_of=_AS_OF)
    current_rank = _dimension_rank(rows, repo, "concept")

    # as_of → 半导体 avg=+3.0% 领先; 当前 ext → 人工智能 avg=(+5.1-2.0)/2=+1.55% 领先
    assert as_of_rank["leading"][0]["name"] == "半导体"
    assert current_rank["leading"][0]["name"] == "人工智能"
    assert [x["name"] for x in as_of_rank["leading"]] != [x["name"] for x in current_rank["leading"]]


def test_dimension_rank_industry_maps_to_hy_ths(tmp_path):
    """CONCEPT-06: _dimension_rank(kind='industry', as_of=D) 读 hy_ths 分区聚合。"""
    from app.services.market_overview_builder import _dimension_rank

    _write_concept_ext(tmp_path, kind="gn_ths")  # 概念表 (industry 应忽略)
    _write_concept_ext(tmp_path, kind="hy_ths", rows=[
        {"symbol": _SYMBOLS["X"], "code": "600000", "股票代码": "600000", "股票简称": _NAMES["X"], "所属同花顺行业": "银行"},
        {"symbol": _SYMBOLS["Y"], "code": "600001", "股票代码": "600001", "股票简称": _NAMES["Y"], "所属同花顺行业": "银行"},
        {"symbol": _SYMBOLS["Z"], "code": "600002", "股票代码": "600002", "股票简称": _NAMES["Z"], "所属同花顺行业": "券商"},
    ])
    # D 日行业分区: 内容与当前 ext 不同
    _write_partition_fixture(tmp_path, "hy_ths", _AS_OF, "所属同花顺行业", [
        {"symbol": _SYMBOLS["X"], "所属同花顺行业": "半导体"},
        {"symbol": _SYMBOLS["Y"], "所属同花顺行业": "半导体"},
        {"symbol": _SYMBOLS["Z"], "所属同花顺行业": "光伏"},
    ])
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    rows = _overview_rows()

    as_of_rank = _dimension_rank(rows, repo, "industry", level=2, as_of=_AS_OF)
    current_rank = _dimension_rank(rows, repo, "industry", level=2)

    # as_of → hy_ths 分区: 半导体 avg=+1.55%, 光伏 avg=+3.0% → 光伏领先
    assert as_of_rank["leading"][0]["name"] == "光伏"
    # 当前 ext hy_ths: 银行 avg=+1.55%, 券商 avg=+3.0% → 券商领先
    assert current_rank["leading"][0]["name"] == "券商"


def test_build_market_overview_as_of_wiring(tmp_path):
    """CONCEPT-06: build_market_overview(as_of=D) concept/industry_rank 由 D 日分区; as_of=None 用当前 ext。"""
    from app.services.market_overview_builder import build_market_overview

    _write_concept_ext(tmp_path, kind="gn_ths")
    _write_concept_ext(tmp_path, kind="hy_ths", rows=[
        {"symbol": _SYMBOLS["X"], "code": "600000", "股票代码": "600000", "股票简称": _NAMES["X"], "所属同花顺行业": "银行"},
        {"symbol": _SYMBOLS["Y"], "code": "600001", "股票代码": "600001", "股票简称": _NAMES["Y"], "所属同花顺行业": "银行"},
        {"symbol": _SYMBOLS["Z"], "code": "600002", "股票代码": "600002", "股票简称": _NAMES["Z"], "所属同花顺行业": "券商"},
    ])
    _write_partition_fixture(tmp_path, "gn_ths", _AS_OF, "所属概念", [
        {"symbol": _SYMBOLS["X"], "所属概念": "新能源"},
        {"symbol": _SYMBOLS["Y"], "所属概念": "新能源"},
        {"symbol": _SYMBOLS["Z"], "所属概念": "半导体"},
    ])
    _write_partition_fixture(tmp_path, "hy_ths", _AS_OF, "所属同花顺行业", [
        {"symbol": _SYMBOLS["X"], "所属同花顺行业": "半导体"},
        {"symbol": _SYMBOLS["Y"], "所属同花顺行业": "半导体"},
        {"symbol": _SYMBOLS["Z"], "所属同花顺行业": "光伏"},
    ])

    repo = _FakeOverviewRepo(tmp_path, _enriched_hist_frame())

    overview_as_of = build_market_overview(repo, as_of=date(2026, 8, 4))
    assert overview_as_of["concept_rank"]["leading"][0]["name"] == "半导体"
    assert overview_as_of["industry_rank"]["leading"][0]["name"] == "光伏"

    overview_latest = build_market_overview(repo)
    assert overview_latest["concept_rank"]["leading"][0]["name"] == "人工智能"
    assert overview_latest["industry_rank"]["leading"][0]["name"] == "券商"


def test_overview_api_as_of_partition(tmp_path):
    """CONCEPT-06 API: GET /api/overview/market?as_of=D → concept_rank 由分区聚合; 无 as_of → 现状。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import overview as overview_api

    _write_concept_ext(tmp_path, kind="gn_ths")
    _write_partition_fixture(tmp_path, "gn_ths", _AS_OF, "所属概念", [
        {"symbol": _SYMBOLS["X"], "所属概念": "新能源"},
        {"symbol": _SYMBOLS["Y"], "所属概念": "新能源"},
        {"symbol": _SYMBOLS["Z"], "所属概念": "半导体"},
    ])

    app = FastAPI()
    app.include_router(overview_api.router)
    app.state.repo = _FakeOverviewRepo(tmp_path, _enriched_hist_frame())
    app.state.quote_service = None
    app.state.depth_service = None

    overview_api.invalidate_overview_cache()
    client = TestClient(app)

    resp = client.get("/api/overview/market", params={"as_of": _AS_OF})
    assert resp.status_code == 200
    assert resp.json()["concept_rank"]["leading"][0]["name"] == "半导体"

    overview_api.invalidate_overview_cache()
    resp2 = client.get("/api/overview/market")
    assert resp2.status_code == 200
    assert resp2.json()["concept_rank"]["leading"][0]["name"] == "人工智能"


# ---------------------------------------------------------------------------
# Task 2 — CONCEPT-06 RPS seam: _load_concept_map_df as_of + build_rps_rotation 透传 + API
# ---------------------------------------------------------------------------

def test_load_concept_map_df_as_of_branch(tmp_path):
    """CONCEPT-06: _load_concept_map_df(repo, as_of=D) 返回 D 日分区 map; 600s 缓存零污染。"""
    from app.services.rps_rotation import _load_concept_map_df

    _reset_rps_caches()
    _write_concept_ext(tmp_path, kind="gn_ths")  # 当前 ext: X→人工智能, Y→人工智能;新能源, Z→新能源
    _write_partition_fixture(tmp_path, "gn_ths", _AS_OF, "所属概念", [
        {"symbol": _SYMBOLS["X"], "所属概念": "新能源"},
        {"symbol": _SYMBOLS["Y"], "所属概念": "新能源"},
        {"symbol": _SYMBOLS["Z"], "所属概念": "半导体"},
    ])
    repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))

    map_as_of, count_as_of = _load_concept_map_df(repo, as_of=_AS_OF)
    assert count_as_of == 2  # 新能源 + 半导体
    assert set(map_as_of["concept"].to_list()) == {"新能源", "半导体"}

    # 缓存零污染: 无 as_of 调用仍走当前 ext (人工智能/新能源), 不返回分区内容
    map_latest, count_latest = _load_concept_map_df(repo)
    assert set(map_latest["concept"].to_list()) == {"人工智能", "新能源"}
    assert count_latest == 2


def test_build_rps_rotation_as_of_passthrough(tmp_path):
    """CONCEPT-06: build_rps_rotation(repo, days, as_of=D) 由 D 日分区 join; 无 as_of 用当前 ext。"""
    from app.services.rps_rotation import build_rps_rotation

    _reset_rps_caches()
    _write_concept_ext(tmp_path, kind="gn_ths")
    _write_partition_fixture(tmp_path, "gn_ths", _AS_OF, "所属概念", [
        {"symbol": _SYMBOLS["X"], "所属概念": "新能源"},
        {"symbol": _SYMBOLS["Y"], "所属概念": "新能源"},
        {"symbol": _SYMBOLS["Z"], "所属概念": "半导体"},
    ])
    repo = _FakeRpsRepo(tmp_path, _rps_hist_frame())

    rotation_as_of = build_rps_rotation(repo, days=7, as_of=_AS_OF)
    assert rotation_as_of["concept_count"] == 2
    as_of_concepts = {name for col in rotation_as_of["columns"].values() for name, _ in col}
    assert "半导体" in as_of_concepts
    assert "人工智能" not in as_of_concepts

    rotation_latest = build_rps_rotation(repo, days=7)
    assert rotation_latest["concept_count"] == 2
    latest_concepts = {name for col in rotation_latest["columns"].values() for name, _ in col}
    assert "人工智能" in latest_concepts
    assert "半导体" not in latest_concepts


def test_rps_api_as_of_query(tmp_path):
    """CONCEPT-06 API: GET /api/rps/rotation?as_of=D → 200 分区 columns; 非法 as_of → 400; 无 as_of → 200。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import rps as rps_api

    _reset_rps_caches()
    _write_concept_ext(tmp_path, kind="gn_ths")
    _write_partition_fixture(tmp_path, "gn_ths", _AS_OF, "所属概念", [
        {"symbol": _SYMBOLS["X"], "所属概念": "新能源"},
        {"symbol": _SYMBOLS["Y"], "所属概念": "新能源"},
        {"symbol": _SYMBOLS["Z"], "所属概念": "半导体"},
    ])
    app = FastAPI()
    app.include_router(rps_api.router)
    app.state.repo = _FakeRpsRepo(tmp_path, _rps_hist_frame())

    client = TestClient(app)

    resp = client.get("/api/rps/rotation", params={"as_of": _AS_OF})
    assert resp.status_code == 200
    body = resp.json()
    as_of_concepts = {name for col in body["columns"].values() for name, _ in col}
    assert "半导体" in as_of_concepts
    assert "人工智能" not in as_of_concepts

    for bad in ("2026-8-4", "../../x"):
        bad_resp = client.get("/api/rps/rotation", params={"as_of": bad})
        assert bad_resp.status_code == 400, f"as_of={bad} 应 400"

    latest = client.get("/api/rps/rotation")
    assert latest.status_code == 200
    latest_concepts = {name for col in latest.json()["columns"].values() for name, _ in col}
    assert "人工智能" in latest_concepts


def test_concept07_history_passthrough_verify(tmp_path):
    """CONCEPT-07 复验: /api/pool/history?as_of=D 载荷含 effective/captured_at (28-01 不回退); overview as_of 冒烟。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import overview as overview_api
    from app.api import pool as pool_api

    _reset_rps_caches()
    _write_strategy_cache(tmp_path)
    _write_concept_ext(tmp_path, kind="gn_ths")
    _write_snapshot(tmp_path, as_of=_AS_OF)
    _write_partition_fixture(tmp_path, "gn_ths", _AS_OF, "所属概念", [
        {"symbol": _SYMBOLS["X"], "所属概念": "新能源"},
        {"symbol": _SYMBOLS["Y"], "所属概念": "新能源"},
        {"symbol": _SYMBOLS["Z"], "所属概念": "半导体"},
    ])

    app = FastAPI()
    app.include_router(pool_api.router)
    app.include_router(overview_api.router)
    app.state.repo = _FakeOverviewRepo(tmp_path, _enriched_hist_frame())
    app.state.strategy_engine = None

    @app.middleware("http")
    async def bind_vip(request, call_next):
        request.state.reviewer_principal = "reviewer_test"
        return await call_next(request)

    client = TestClient(app)

    resp = client.get("/api/pool/history", params={"as_of": _AS_OF})
    assert resp.status_code == 200
    body = resp.json()
    assert body["concept_attribution"] == "as_of_snapshot"
    assert body["concept_effective_date"] == _AS_OF
    assert body["concept_captured_at"] == "2026-08-04T10:00:00"

    overview_api.invalidate_overview_cache()
    resp2 = client.get("/api/overview/market", params={"as_of": _AS_OF})
    assert resp2.status_code == 200
    assert resp2.json()["concept_rank"]["leading"][0]["name"] == "半导体"

