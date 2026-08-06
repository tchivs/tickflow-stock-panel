"""POOL-01/02/03 股池 Hub — 投影服务 + 只读 API + 零执行权限守卫。

- Task 1: ``build_pool_hub`` 投影 — 单一 as_of 计数 + 五列行 + 交叉共振 +
  概念筛选 (hermetic fixture, 不依赖真实数据)。
- Task 2: ``GET /api/pool/hub`` 端点回归。
- Task 3: POOL-03 零执行权限 AST 守卫 (T-18-01) — 任何把 broker/order/execution
  模块引入 pool 特性、新增 mutating 路由、或给投影加写路径的改动都会让本套件失败。
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from types import SimpleNamespace

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import pool as pool_api
from app.services.pool_hub import build_pool_hub

_AS_OF = "2026-08-04"

# 符号映射: X / Y / Z / W
_SYMBOLS = {
    "X": "600000.SH",
    "Y": "600001.SH",
    "Z": "600002.SH",
    "W": "600003.SH",
}

# 持久化行真实名称 (名称投影来源)
_NAMES = {
    "X": "人工智能龙头",
    "Y": "宁德新能源",
    "Z": "新能科技",
    "W": "早盘之星科技",
}


def _write_strategy_cache(data_dir: Path) -> None:
    """写入 hermetic 策略缓存 — 单一 as_of, 3 个竞价策略。

    Y (600001.SH) 同时被 auction_bullish 与 auction_preopen_quant 命中,
    其持久化 hit_factors 是 Phase 17 跨策略聚合后的完整列表 (len=2 → 交叉共振);
    X / Z / W 都是单因子命中。
    """
    payload = {
        "as_of": _AS_OF,
        "results": {
            "auction_bullish": {
                "total": 2,
                "as_of": _AS_OF,
                "rows": [
                    {
                        "symbol": _SYMBOLS["X"],
                        "name": _NAMES["X"],
                        "open_gap": 3.21,
                        "change_pct": 5.1,
                        "hit_factors": ["竞价多头"],
                    },
                    {
                        "symbol": _SYMBOLS["Y"],
                        "name": _NAMES["Y"],
                        "open_gap": 1.5,
                        "change_pct": 2.3,
                        "hit_factors": ["盘前强势量化", "竞价多头"],
                    },
                ],
            },
            "auction_preopen_quant": {
                "total": 2,
                "as_of": _AS_OF,
                "rows": [
                    {
                        "symbol": _SYMBOLS["Y"],
                        "name": _NAMES["Y"],
                        "open_gap": 1.5,
                        "hit_factors": ["盘前强势量化", "竞价多头"],
                    },
                    {
                        "symbol": _SYMBOLS["Z"],
                        "name": _NAMES["Z"],
                        "open_gap": 0.5,
                        # change_pct 缺失 → 前端渲染 —
                        "hit_factors": ["盘前强势量化"],
                    },
                ],
            },
            "auction_early_star": {
                "total": 1,
                "as_of": _AS_OF,
                "rows": [
                    {
                        "symbol": _SYMBOLS["W"],
                        "name": _NAMES["W"],
                        "open_gap": 0.1,
                        "change_pct": 0.9,
                        "hit_factors": ["早盘之星"],
                    },
                ],
            },
        },
        "updated_at": 1722758400000,
    }
    path = data_dir / "user_data" / "strategy_cache.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_concept_fixture(data_dir: Path) -> None:
    """写入 hermetic 概念扩展数据 (ExtConfig snapshot, field=所属概念)。

    X → 人工智能; Y → 人工智能;新能源; Z → 新能源。W 无概念 → 概念板块 [] / —。
    """
    config_dir = data_dir / "ext_data" / "ext_fixture_concept"
    config_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "id": "ext_fixture_concept",
        "label": "概念Fixture",
        "mode": "snapshot",
        "fields": [{"name": "所属概念", "dtype": "string", "label": "所属概念"}],
        "description": "hermetic concept fixture for pool hub",
        "symbol_map": {},
        "code_map": {},
        "created_at": "2026-08-04T00:00:00",
        "updated_at": "2026-08-04T00:00:00",
        "pull": None,
    }
    (config_dir / "config.json").write_text(
        json.dumps(config, ensure_ascii=False), encoding="utf-8"
    )
    df = pl.DataFrame(
        {
            "symbol": [_SYMBOLS["X"], _SYMBOLS["Y"], _SYMBOLS["Z"]],
            "所属概念": ["人工智能", "人工智能;新能源", "新能源"],
        }
    )
    df.write_parquet(config_dir / "part.parquet")


def _strategies_by_id(hub: dict) -> dict[str, dict]:
    return {s["id"]: s for s in hub["strategies"]}


def _write_snapshot(
    data_dir: Path,
    as_of: str = _AS_OF,
    results: dict | None = None,
    computed_at: str = "2026-08-04T15:30:00",
    strategy_version: str = "fp-test",
    origin: str = "eod",
) -> Path:
    """直接写一个合法冻结式点快照 part.json (POOL-05 读路径 fixture)。

    默认 results 与 ``_write_strategy_cache`` 同形状 (3 策略, Y 交叉共振),
    保证 build_pool_hub 与 build_pool_hub_snapshot 投影语义可比。
    ``origin`` 默认 eod; 旧快照兼容用例可用 ``origin=None`` 跳过该键。
    """
    if results is None:
        results = {
            "auction_bullish": {
                "total": 2,
                "as_of": as_of,
                "rows": [
                    {
                        "symbol": _SYMBOLS["X"],
                        "name": _NAMES["X"],
                        "open_gap": 3.21,
                        "change_pct": 5.1,
                        "hit_factors": ["竞价多头"],
                    },
                    {
                        "symbol": _SYMBOLS["Y"],
                        "name": _NAMES["Y"],
                        "open_gap": 1.5,
                        "change_pct": 2.3,
                        "hit_factors": ["盘前强势量化", "竞价多头"],
                    },
                ],
            },
            "auction_preopen_quant": {
                "total": 2,
                "as_of": as_of,
                "rows": [
                    {
                        "symbol": _SYMBOLS["Y"],
                        "name": _NAMES["Y"],
                        "open_gap": 1.5,
                        "hit_factors": ["盘前强势量化", "竞价多头"],
                    },
                    {
                        "symbol": _SYMBOLS["Z"],
                        "name": _NAMES["Z"],
                        "open_gap": 0.5,
                        "hit_factors": ["盘前强势量化"],
                    },
                ],
            },
            "auction_early_star": {
                "total": 1,
                "as_of": as_of,
                "rows": [
                    {
                        "symbol": _SYMBOLS["W"],
                        "name": _NAMES["W"],
                        "open_gap": 0.1,
                        "change_pct": 0.9,
                        "hit_factors": ["早盘之星"],
                    },
                ],
            },
        }
    payload = {
        "as_of": as_of,
        "computed_at": computed_at,
        "strategy_version": strategy_version,
        "snapshot_type": "point",
        "schema_version": 1,
        "results": results,
    }
    # 诚实 provenance: 快照可带 snapshot_origin (HIST-02); 旧快照兼容用例传 None 跳过键
    if origin is not None:
        payload["snapshot_origin"] = origin
    path = data_dir / "screener_results" / f"date={as_of}" / "part.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


# ================================================================
# Task 1 — build_pool_hub 投影
# ================================================================


def test_build_pool_hub_single_as_of_counts_and_columns(tmp_path):
    """单一 as_of 来源: 每策略 total == 持久化行数, 每行恰含六列 + cross_resonance。"""
    _write_strategy_cache(tmp_path)
    _write_concept_fixture(tmp_path)
    hub = build_pool_hub(tmp_path)

    assert hub["as_of"] == _AS_OF
    strategies = _strategies_by_id(hub)
    assert set(strategies) == {"auction_bullish", "auction_preopen_quant", "auction_early_star"}
    assert strategies["auction_bullish"]["total"] == 2
    assert strategies["auction_preopen_quant"]["total"] == 2
    assert strategies["auction_early_star"]["total"] == 1

    expected_keys = {
        "symbol",
        "code",
        "name",
        "open_gap",
        "change_pct",
        "concept_board",
        "hit_factors",
        "cross_resonance",
        # Phase 23 (OQ-2): 竞价列透传 — 行恒含 12 键; 缺列时为 None (诚实缺列)
        "auction_volume",
        "auction_amount",
        "auction_volume_ratio",
        "auction_unmatched_amount",
    }
    for strategy in strategies.values():
        for row in strategy["rows"]:
            assert set(row) == expected_keys
            assert row["code"] == row["symbol"].split(".", 1)[0]

    # Phase 23 (OQ-2): 双路径共享 _project_hub — hub 视图同样携带顶层声明;
    # 默认缓存 raw rows 无竞价列 → real == [] (诚实缺列), open_gap 恒在 derived。
    assert hub["auction_columns"] == {"real": [], "derived": ["open_gap"]}

    # Y 在两个策略下都是 交叉共振 (hit_factors >= 2); X / W 是单因子
    for sid in ("auction_bullish", "auction_preopen_quant"):
        y_row = next(r for r in strategies[sid]["rows"] if r["symbol"] == _SYMBOLS["Y"])
        assert y_row["cross_resonance"] is True
    x_row = next(r for r in strategies["auction_bullish"]["rows"] if r["symbol"] == _SYMBOLS["X"])
    assert x_row["cross_resonance"] is False
    w_row = strategies["auction_early_star"]["rows"][0]
    assert w_row["cross_resonance"] is False

    # 交叉共振计数 = 去重后的共振标的数 (只有 Y)
    assert hub["resonance_count"] == 1


def test_concept_board_join_and_missing_value_dash(tmp_path):
    """概念板块从 ext seam join (确定性排序); 缺失 change_pct → None (前端 —)。"""
    _write_strategy_cache(tmp_path)
    _write_concept_fixture(tmp_path)
    hub = build_pool_hub(tmp_path)
    strategies = _strategies_by_id(hub)

    x_row = next(r for r in strategies["auction_bullish"]["rows"] if r["symbol"] == _SYMBOLS["X"])
    assert x_row["concept_board"] == ["人工智能"]

    y_row = next(r for r in strategies["auction_bullish"]["rows"] if r["symbol"] == _SYMBOLS["Y"])
    assert set(y_row["concept_board"]) == {"人工智能", "新能源"}
    assert y_row["concept_board"] == sorted(y_row["concept_board"])  # 确定性

    z_row = next(r for r in strategies["auction_preopen_quant"]["rows"] if r["symbol"] == _SYMBOLS["Z"])
    assert z_row["change_pct"] is None

    w_row = strategies["auction_early_star"]["rows"][0]
    assert w_row["concept_board"] == []  # W 无概念 → UI 渲染 —


def test_concept_filter_keeps_total_authoritative(tmp_path):
    """概念筛选只收窄 rows; 每策略 total 保持权威全量 (共 M)。"""
    _write_strategy_cache(tmp_path)
    _write_concept_fixture(tmp_path)
    hub = build_pool_hub(tmp_path, concept="新能源")
    strategies = _strategies_by_id(hub)

    assert strategies["auction_bullish"]["total"] == 2
    assert strategies["auction_preopen_quant"]["total"] == 2
    assert strategies["auction_early_star"]["total"] == 1

    bullish_rows = [r["symbol"] for r in strategies["auction_bullish"]["rows"]]
    assert bullish_rows == [_SYMBOLS["Y"]]
    preopen_rows = [r["symbol"] for r in strategies["auction_preopen_quant"]["rows"]]
    assert preopen_rows == [_SYMBOLS["Y"], _SYMBOLS["Z"]]
    assert strategies["auction_early_star"]["rows"] == []


def test_concept_filter_is_case_insensitive(tmp_path):
    """概念筛选大小写不敏感子串: 小写 'ai' 命中 'AI;机器人' 行。"""
    payload = {
        "as_of": _AS_OF,
        "results": {
            "auction_bullish": {
                "total": 2,
                "as_of": _AS_OF,
                "rows": [
                    {"symbol": _SYMBOLS["X"], "open_gap": 1.0, "change_pct": 1.0, "hit_factors": ["竞价多头"]},
                    {"symbol": _SYMBOLS["Y"], "open_gap": 1.0, "change_pct": 1.0, "hit_factors": ["竞价多头"]},
                ],
            },
        },
        "updated_at": 1,
    }
    path = tmp_path / "user_data" / "strategy_cache.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    config_dir = tmp_path / "ext_data" / "ext_fixture_concept"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.json").write_text(
        json.dumps(
            {
                "id": "ext_fixture_concept",
                "label": "概念Fixture",
                "mode": "snapshot",
                "fields": [{"name": "所属概念", "dtype": "string", "label": "所属概念"}],
                "description": "",
                "symbol_map": {},
                "code_map": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    pl.DataFrame(
        {
            "symbol": [_SYMBOLS["X"], _SYMBOLS["Y"]],
            "所属概念": ["AI;机器人", "新能源"],
        }
    ).write_parquet(config_dir / "part.parquet")

    hub = build_pool_hub(tmp_path, concept="  ai  ")
    strategy = hub["strategies"][0]
    assert [r["symbol"] for r in strategy["rows"]] == [_SYMBOLS["X"]]
    assert strategy["total"] == 2  # 筛选不改变权威总数


def test_build_pool_hub_empty_cache(tmp_path):
    """无缓存文件 → 空 Hub (as_of None, strategies [], resonance_count 0)。"""
    hub = build_pool_hub(tmp_path)
    assert hub == {"as_of": None, "updated_at": None, "strategies": [], "resonance_count": 0}


def test_build_pool_hub_sanitizes_nan(tmp_path):
    """NaN / Inf → None, 响应始终 json.dumps 可序列化 (T-18-04)。"""
    payload = {
        "as_of": _AS_OF,
        "results": {
            "auction_bullish": {
                "total": 1,
                "as_of": _AS_OF,
                "rows": [
                    {
                        "symbol": _SYMBOLS["X"],
                        "open_gap": float("nan"),
                        "change_pct": float("inf"),
                        "hit_factors": ["竞价多头"],
                    },
                ],
            },
        },
        "updated_at": 1,
    }
    path = tmp_path / "user_data" / "strategy_cache.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, allow_nan=True), encoding="utf-8")

    hub = build_pool_hub(tmp_path)
    row = hub["strategies"][0]["rows"][0]
    assert row["open_gap"] is None
    assert row["change_pct"] is None
    json.dumps(hub)  # 不抛 → JSON 安全


def test_build_pool_hub_does_not_mutate_cache(tmp_path):
    """投影不修改缓存: 磁盘上的原行不携带任何投影键。"""
    _write_strategy_cache(tmp_path)
    _write_concept_fixture(tmp_path)
    build_pool_hub(tmp_path)

    raw = json.loads(
        (tmp_path / "user_data" / "strategy_cache.json").read_text(encoding="utf-8")
    )
    for result in raw["results"].values():
        for row in result["rows"]:
            assert "concept_board" not in row
            assert "cross_resonance" not in row
            assert "code" not in row


def test_build_pool_hub_echoes_cache_as_of_on_mismatch(tmp_path):
    """调用方传入不一致 as_of → 回显缓存日期, 不伪造第二个日期 (T-18-03)。"""
    _write_strategy_cache(tmp_path)
    hub = build_pool_hub(tmp_path, as_of="2026-01-01")
    assert hub["as_of"] == _AS_OF


# ================================================================
# Task 2 (POOL-05) — build_pool_hub_snapshot 快照投影
# ================================================================


def test_build_pool_hub_snapshot_uses_snapshot_total(tmp_path):
    """Divergence 1: 快照 total 权威 (display_limit 截断后 len(rows) < total)。"""
    from app.services.pool_hub import build_pool_hub_snapshot

    _write_snapshot(
        tmp_path,
        results={
            "auction_bullish": {
                "total": 2,
                "as_of": _AS_OF,
                "rows": [
                    {
                        "symbol": _SYMBOLS["X"],
                        "name": _NAMES["X"],
                        "open_gap": 3.21,
                        "change_pct": 5.1,
                        "hit_factors": ["竞价多头"],
                    },
                ],
            },
        },
    )
    hub = build_pool_hub_snapshot(tmp_path, _AS_OF)
    assert hub["strategies"][0]["total"] == 2
    assert len(hub["strategies"][0]["rows"]) == 1


def test_build_pool_hub_snapshot_missing_available_false(tmp_path):
    """快照缺失 → 诚实空态 (available: False, 非 404 语义)。"""
    from app.services.pool_hub import build_pool_hub_snapshot

    hub = build_pool_hub_snapshot(tmp_path, _AS_OF)
    assert hub == {
        "as_of": None,
        "available": False,
        "strategies": [],
        "resonance_count": 0,
        "updated_at": None,
        "concept_attribution": "current_snapshot",
        # HIST-02 空态: 无快照 → snapshot_origin 诚实 None (非伪造 eod)
        "snapshot_origin": None,
    }


def test_build_pool_hub_snapshot_has_concept_attribution(tmp_path):
    """Divergence 2: 快照投影带 concept_attribution: current_snapshot (诚实标注)。"""
    from app.services.pool_hub import build_pool_hub_snapshot

    _write_snapshot(tmp_path)
    hub = build_pool_hub_snapshot(tmp_path, _AS_OF)
    assert hub["concept_attribution"] == "current_snapshot"
    assert hub["as_of"] == _AS_OF
    assert hub["updated_at"] == "2026-08-04T15:30:00"
    assert len(hub["strategies"]) == 3
    assert hub["resonance_count"] == 1


def test_project_hub_passes_through_auction_columns(tmp_path):
    """OQ-2 透传 round-trip: 快照 raw rows 带竞价数值 → 投影行 4 键 _safe_num 后相等 + 顶层声明精确。"""
    from app.services.pool_hub import build_pool_hub_snapshot

    _write_snapshot(
        tmp_path,
        results={
            "auction_bullish": {
                "total": 1,
                "as_of": _AS_OF,
                "rows": [
                    {
                        "symbol": _SYMBOLS["X"],
                        "name": _NAMES["X"],
                        "open_gap": 3.21,
                        "change_pct": 5.1,
                        "hit_factors": ["竞价多头"],
                        "auction_volume": 1234567.0,
                        "auction_amount": 89012345.0,
                        "auction_volume_ratio": 1.25,
                        "auction_unmatched_amount": 98765.0,
                    },
                ],
            },
        },
    )
    hub = build_pool_hub_snapshot(tmp_path, _AS_OF)
    row = hub["strategies"][0]["rows"][0]
    assert row["auction_volume"] == 1234567.0
    assert row["auction_amount"] == 89012345.0
    assert row["auction_volume_ratio"] == 1.25
    assert row["auction_unmatched_amount"] == 98765.0
    assert hub["auction_columns"] == {
        "real": ["auction_volume", "auction_amount"],
        "derived": ["auction_volume_ratio", "auction_unmatched_amount", "open_gap"],
    }


def test_project_hub_honest_absent_auction_columns(tmp_path):
    """PIT-3 诚实缺列: raw rows 无竞价列 → 投影行 4 键全 None, real == [], derived 不含竞价派生键。"""
    from app.services.pool_hub import build_pool_hub_snapshot

    _write_snapshot(tmp_path)  # 默认夹具无竞价列 (但 open_gap 恒在)
    hub = build_pool_hub_snapshot(tmp_path, _AS_OF)
    for strategy in hub["strategies"]:
        for row in strategy["rows"]:
            assert row["auction_volume"] is None
            assert row["auction_amount"] is None
            assert row["auction_volume_ratio"] is None
            assert row["auction_unmatched_amount"] is None
    assert hub["auction_columns"]["real"] == []
    assert "auction_volume_ratio" not in hub["auction_columns"]["derived"]
    assert "auction_unmatched_amount" not in hub["auction_columns"]["derived"]


def test_project_hub_auction_columns_match_projection_keys(tmp_path):
    """PIT-3 防线: 极端夹具只带 auction_volume 键 → real == ["auction_volume"], 与投影键集一致。"""
    from app.services.pool_hub import build_pool_hub_snapshot

    _write_snapshot(
        tmp_path,
        results={
            "auction_bullish": {
                "total": 1,
                "as_of": _AS_OF,
                "rows": [
                    {
                        "symbol": _SYMBOLS["X"],
                        "name": _NAMES["X"],
                        "open_gap": 1.0,
                        "change_pct": 1.0,
                        "hit_factors": ["竞价多头"],
                        "auction_volume": 100.0,
                    },
                ],
            },
        },
    )
    hub = build_pool_hub_snapshot(tmp_path, _AS_OF)
    assert hub["auction_columns"]["real"] == ["auction_volume"]
    assert "auction_amount" not in hub["auction_columns"]["real"]
    row = hub["strategies"][0]["rows"][0]
    assert row["auction_volume"] == 100.0
    assert row["auction_amount"] is None


# ================================================================
# Task 2 — GET /api/pool/hub 端点回归
# ================================================================


class _FakeRepo:
    """最小 repo 桩: 只需 store.data_dir (与 test_factor_hits 同型)。"""

    def __init__(self, data_dir: Path):
        self.store = SimpleNamespace(data_dir=data_dir)


class _FakeStrategy:
    def __init__(self, name: str):
        self.meta = {"name": name}


class _FakeEngine:
    """注入的伪策略引擎: get(sid).meta['name'] 返回中文显示名。"""

    _NAMES = {
        "auction_bullish": "竞价多头",
        "auction_preopen_quant": "盘前强势量化",
        "auction_early_star": "早盘之星",
    }

    def get(self, sid: str) -> _FakeStrategy:
        return _FakeStrategy(self._NAMES[sid])


def _make_client(tmp_path: Path, engine=None) -> TestClient:
    """最小应用 + 绑定 VIP 会话 principal (端点回归期望 明文 rows; 游客脱敏见 test_guest_masking)。"""
    app = FastAPI()
    app.include_router(pool_api.router)
    app.state.repo = _FakeRepo(tmp_path)
    app.state.strategy_engine = engine

    @app.middleware("http")
    async def bind_vip(request, call_next):
        request.state.reviewer_principal = "reviewer_test"
        return await call_next(request)

    return TestClient(app)


def test_get_pool_hub_returns_single_as_of_payload(tmp_path):
    """GET /api/pool/hub → 200, 单一 as_of, 3 策略, 名称服务端解析。"""
    _write_strategy_cache(tmp_path)
    _write_concept_fixture(tmp_path)
    client = _make_client(tmp_path)

    resp = client.get("/api/pool/hub")
    assert resp.status_code == 200
    body = resp.json()
    assert body["as_of"] == _AS_OF
    assert len(body["strategies"]) == 3

    # engine=None → 名称退化为 sid (不 500)
    by_id = {s["id"]: s["name"] for s in body["strategies"]}
    assert by_id["auction_bullish"] == "auction_bullish"
    assert by_id["auction_preopen_quant"] == "auction_preopen_quant"

    # 注入引擎 → 名称解析为中文显示名 (T-18-02)
    client2 = _make_client(tmp_path, engine=_FakeEngine())
    body2 = client2.get("/api/pool/hub").json()
    by_id2 = {s["id"]: s["name"] for s in body2["strategies"]}
    assert by_id2 == {
        "auction_bullish": "竞价多头",
        "auction_preopen_quant": "盘前强势量化",
        "auction_early_star": "早盘之星",
    }


def test_get_pool_hub_concept_filter_keeps_total(tmp_path):
    """?concept=新能源 → rows 收窄, total 保持权威全量。"""
    _write_strategy_cache(tmp_path)
    _write_concept_fixture(tmp_path)
    client = _make_client(tmp_path)

    resp = client.get("/api/pool/hub", params={"concept": "新能源"})
    assert resp.status_code == 200
    body = resp.json()
    by_id = {s["id"]: s for s in body["strategies"]}
    assert by_id["auction_bullish"]["total"] == 2
    assert [r["symbol"] for r in by_id["auction_bullish"]["rows"]] == [_SYMBOLS["Y"]]
    assert by_id["auction_early_star"]["total"] == 1
    assert by_id["auction_early_star"]["rows"] == []


def test_get_pool_hub_mismatched_as_of_returns_cache_date(tmp_path):
    """?as_of=不一致 → 返回缓存日期 (单一数据源, 不伪造第二个日期)。"""
    _write_strategy_cache(tmp_path)
    client = _make_client(tmp_path)

    resp = client.get("/api/pool/hub", params={"as_of": "2026-01-01"})
    assert resp.status_code == 200
    assert resp.json()["as_of"] == _AS_OF


def test_get_pool_hub_missing_cache_empty(tmp_path):
    """无缓存 → 200 空 Hub。"""
    client = _make_client(tmp_path)
    resp = client.get("/api/pool/hub")
    assert resp.status_code == 200
    assert resp.json() == {"as_of": None, "updated_at": None, "strategies": [], "resonance_count": 0, "mode": "vip"}


def test_get_pool_hub_json_serializable_roundtrip(tmp_path):
    """响应 JSON 安全: json.dumps(resp.json()) 可往返 (T-18-04)。"""
    _write_strategy_cache(tmp_path)
    _write_concept_fixture(tmp_path)
    client = _make_client(tmp_path)

    resp = client.get("/api/pool/hub")
    assert resp.status_code == 200
    payload = resp.json()
    # json.dumps 不抛; 往返后结构一致
    reloaded = json.loads(json.dumps(payload))
    assert reloaded == payload


# ================================================================
# Task 2/3 (POOL-05) — /api/pool/dates + /api/pool/history 端点
# ================================================================


def test_pool_dates_api(tmp_path):
    """GET /api/pool/dates → 排序日期列表 (ISO desc) + HIST-03 缺口信号。

    enriched 4 日 (07-29/08-01/08-02/08-04) − 快照 2 日 (08-01/08-04)
    = 缺口 2 日 (07-29, 08-02), 升序示例。无快照目录 (date=2026-08-02)
    不含 part.json → 不列为快照日期, 但仍是 enriched 缺口。
    """
    client = _make_client(tmp_path)
    _write_snapshot(tmp_path, as_of="2026-08-04")
    _write_snapshot(tmp_path, as_of="2026-08-01")
    (tmp_path / "screener_results" / "date=2026-08-02").mkdir(parents=True)
    # enriched 分区 (纯目录即可 — list_enriched_dates 只 glob date=* 目录)
    for d in ("2026-07-29", "2026-08-01", "2026-08-02", "2026-08-04"):
        (tmp_path / "kline_daily_enriched" / f"date={d}").mkdir(parents=True, exist_ok=True)

    resp = client.get("/api/pool/dates")
    assert resp.status_code == 200
    assert resp.json() == {
        "dates": ["2026-08-04", "2026-08-01"],
        "count": 2,
        "latest": "2026-08-04",
        "backfill_needed": 2,
        "backfill_examples": ["2026-07-29", "2026-08-02"],
    }

    # 无快照 + 无 enriched → 空态
    client2 = _make_client(tmp_path / "empty")
    assert client2.get("/api/pool/dates").json() == {
        "dates": [], "count": 0, "latest": None,
        "backfill_needed": 0, "backfill_examples": [],
    }


def test_pool_dates_backfill_examples_truncated(tmp_path):
    """HIST-03: 缺口 > 5 → backfill_examples 只列升序前 5 个示例日。"""
    client = _make_client(tmp_path)
    # 显式写 6 个升序 enriched 分区, 无任何快照 → 全为缺口
    for d in ("2026-07-25", "2026-07-26", "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30"):
        (tmp_path / "kline_daily_enriched" / f"date={d}").mkdir(parents=True, exist_ok=True)

    resp = client.get("/api/pool/dates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["backfill_needed"] == 6
    assert body["backfill_examples"] == ["2026-07-25", "2026-07-26", "2026-07-27", "2026-07-28", "2026-07-29"]
    assert len(body["backfill_examples"]) == 5


def test_pool_dates_backfill_needed_zero_when_all_covered(tmp_path):
    """集成 (依赖 24-01): enriched 全部已快照 → 缺口归零, 示例空 (回填完成态)。"""
    client = _make_client(tmp_path)
    for d in ("2026-08-01", "2026-08-02", "2026-08-03"):
        (tmp_path / "kline_daily_enriched" / f"date={d}").mkdir(parents=True, exist_ok=True)
        _write_snapshot(tmp_path, as_of=d)

    resp = client.get("/api/pool/dates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["backfill_needed"] == 0
    assert body["backfill_examples"] == []
    assert body["dates"] == ["2026-08-03", "2026-08-02", "2026-08-01"]
    assert body["count"] == 3


def test_pool_history_snapshot(tmp_path):
    """GET /api/pool/history?as_of= 有快照 → 与 hub 同形状, total 权威, 含 mode。"""
    _write_snapshot(
        tmp_path,
        results={
            "auction_bullish": {
                "total": 2,
                "as_of": _AS_OF,
                "rows": [
                    {
                        "symbol": _SYMBOLS["X"],
                        "name": _NAMES["X"],
                        "open_gap": 3.21,
                        "change_pct": 5.1,
                        "hit_factors": ["竞价多头"],
                    },
                ],
            },
        },
    )
    client = _make_client(tmp_path, engine=_FakeEngine())
    resp = client.get("/api/pool/history", params={"as_of": _AS_OF})
    assert resp.status_code == 200
    body = resp.json()
    assert body["as_of"] == _AS_OF
    assert body["mode"] == "vip"
    assert body["strategies"][0]["total"] == 2
    assert len(body["strategies"][0]["rows"]) == 1
    # 与 hub 同形状键集
    assert {
        "as_of", "updated_at", "strategies", "resonance_count", "concept_attribution",
    } <= set(body)


def test_pool_history_snapshot_origin_passthrough(tmp_path):
    """HIST-02 读侧: 快照含 snapshot_origin=backfill → history 投影响应透传 backfill。"""
    _write_snapshot(tmp_path, origin="backfill")
    client = _make_client(tmp_path, engine=_FakeEngine())
    resp = client.get("/api/pool/history", params={"as_of": _AS_OF})
    assert resp.status_code == 200
    assert resp.json()["snapshot_origin"] == "backfill"


def test_pool_history_snapshot_origin_default_eod(tmp_path):
    """Pitfall 5 兼容锁: 旧快照 (无 snapshot_origin 键) → 读侧缺省 eod, 绝不 KeyError。"""
    _write_snapshot(tmp_path, origin=None)  # 旧 payload: 无 origin 键
    client = _make_client(tmp_path, engine=_FakeEngine())
    resp = client.get("/api/pool/history", params={"as_of": _AS_OF})
    assert resp.status_code == 200
    assert resp.json()["snapshot_origin"] == "eod"


def test_pool_history_missing_available_false(tmp_path):
    """快照缺失 → 200 + available False 空态 (非 404)。"""
    client = _make_client(tmp_path)
    resp = client.get("/api/pool/history", params={"as_of": _AS_OF})
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["as_of"] is None
    assert body["strategies"] == []
    assert body["updated_at"] is None
    # HIST-02 空态: 无快照 → snapshot_origin 诚实 None (非伪造 eod)
    assert body["snapshot_origin"] is None


def test_pool_history_rejects_bad_as_of(tmp_path):
    """非法 as_of → 400 (防路径穿越); 缺失 as_of → 200 空态。"""
    client = _make_client(tmp_path)
    for bad in ("2026-8-4", "../../x", "2026-08-4", "2026-13-01"):
        resp = client.get("/api/pool/history", params={"as_of": bad})
        assert resp.status_code == 400, bad
    # 缺失 as_of → 200 空态
    resp = client.get("/api/pool/history")
    assert resp.status_code == 200
    assert resp.json()["available"] is False


# ================================================================
# Task 3 — POOL-03 零执行权限守卫 (T-18-01)
# ================================================================

# 执行族 token: 出现在 pool 特性 import / 路由 / 响应键中即失败
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

_ROUTE_METHODS = ("get", "post", "put", "delete", "patch")


def _feature_sources() -> tuple[str, str, str]:
    backend = Path(__file__).resolve().parents[1]
    service_src = (backend / "app" / "services" / "pool_hub.py").read_text(encoding="utf-8")
    api_src = (backend / "app" / "api" / "pool.py").read_text(encoding="utf-8")
    snapshot_src = (backend / "app" / "services" / "pool_snapshot.py").read_text(encoding="utf-8")
    return service_src, api_src, snapshot_src


def _imported_module_names(source: str) -> list[str]:
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_pool_hub_no_execution_imports():
    """pool_hub.py / pool.py / pool_snapshot.py 不得 import 任何执行族模块 (T-18-01, E1)。"""
    service_src, api_src, snapshot_src = _feature_sources()
    for src in (service_src, api_src, snapshot_src):
        for module in _imported_module_names(src):
            assert not _EXECUTION_TOKEN.search(module), (
                f"pool 特性引入了执行族模块: {module}"
            )


def test_pool_api_is_get_only():
    """pool.py 只允许 GET 路由 (T-18-01, E4)。"""
    _service_src, api_src, _snapshot_src = _feature_sources()
    methods = re.findall(r"@router\.(get|post|put|delete|patch)\b", api_src)
    # 全部路由必须都是 GET (E4): 新增 /dates + /history 也是 GET-only
    assert methods and set(methods) == {"get"}, f"pool API 出现了非 GET 路由: {methods}"


def test_build_pool_hub_has_no_write_path():
    """build_pool_hub 是纯读者: 无写模式 open / write_parquet / os.replace / unlink / mkdir。"""
    service_src, _api_src, _snapshot_src = _feature_sources()
    for pattern in _WRITE_PATTERNS:
        assert not pattern.search(service_src), f"pool_hub.py 出现写路径: {pattern.pattern}"


def test_pool_snapshot_writes_only_screener_results():
    """pool_snapshot 是写入者 (E2): 只写 screener_results/ 湖, 写路径必须经 _SNAPSHOT_ROOT 派生。"""
    _service_src, _api_src, snapshot_src = _feature_sources()
    # 模块常量 _SNAPSHOT_ROOT == "screener_results"
    m = re.search(r'_SNAPSHOT_ROOT\s*=\s*"([^"]+)"', snapshot_src)
    assert m is not None, "pool_snapshot.py 缺少 _SNAPSHOT_ROOT 常量"
    assert m.group(1) == "screener_results"

    tree = ast.parse(snapshot_src)
    write_funcs = {"replace", "mkdir"}

    def _has_write(node) -> bool:
        for c in ast.walk(node):
            if isinstance(c, ast.Call):
                f = c.func
                if isinstance(f, ast.Attribute) and f.attr in write_funcs:
                    return True
                if isinstance(f, ast.Name) and f.id == "open":
                    return True
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and _has_write(node):
            func_src = ast.get_source_segment(snapshot_src, node) or ""
            assert "_SNAPSHOT_ROOT" in func_src, (
                f"{node.name} 含写路径但未引用 _SNAPSHOT_ROOT (只写 screener_results)"
            )


def test_pool_snapshot_never_writes_runtime_cache():
    """pool_snapshot 不 import/reference strategy_cache (运行时缓存隔离, E3)。"""
    _service_src, _api_src, snapshot_src = _feature_sources()
    for module in _imported_module_names(snapshot_src):
        assert "strategy_cache" not in module, (
            f"pool_snapshot.py 引入了运行时缓存模块: {module}"
        )
    assert "strategy_cache.json" not in snapshot_src, "pool_snapshot.py 引用了 strategy_cache.json"
    assert "write_cache" not in snapshot_src, "pool_snapshot.py 引用了 write_cache"


def test_pool_api_no_compute_trigger():
    """pool.py 不得触发任何计算/持久化 (E5): 禁止 run_all/run_preset/write_cache/persist_point_snapshot。"""
    _service_src, api_src, _snapshot_src = _feature_sources()
    for token in ("run_all", "run_preset", "write_cache", "persist_point_snapshot"):
        assert token not in api_src, f"pool.py 出现了计算触发调用: {token}"


def test_screener_run_all_cache_write_is_latest_gated():
    """D6 回归锁 (HIST-04): run_all 段内 strategy_cache.write_cache 受 latest-date 闸门约束。

    手动 run_all 对历史 as_of 写 cache 会把 single-as_of 最新指针改成过去日期,
    /api/pool/hub 回显陈旧日 (ARCHIVE R1) — D6 修复用 ``if is_latest:`` 包住
    write_cache, 快照无条件落盘且 origin 按 eod/backfill 区分。
    作用域限定 ``def run_all`` 函数段 (W-1), 避开 ``_update_single_strategy_cache``
    内 (run_all 之外) 的另一个 ``strategy_cache.write_cache`` 调用点。
    """
    backend = Path(__file__).resolve().parents[1]
    src = (backend / "app" / "api" / "screener.py").read_text(encoding="utf-8")
    run_all_src = src[src.index("def run_all"):]
    assert "if is_latest:" in run_all_src, "run_all 缺少 is_latest 闸门 (D6 修复回退?)"
    # write_cache 必须被 latest_date/is_latest 闸门先约束 (作用域限定 run_all 段)
    assert run_all_src.index("is_latest") < run_all_src.index("strategy_cache.write_cache"), (
        "run_all 的 write_cache 未被 is_latest 闸门包住 (D6 回退)"
    )
    assert run_all_src.index("latest_date") < run_all_src.index("strategy_cache.write_cache"), (
        "run_all 的 write_cache 未先计算 latest_date (D6 回退)"
    )


def _all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _all_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _all_keys(item)


def test_hub_response_has_no_execution_vocabulary(tmp_path):
    """Hub / history / dates 响应键不含 orders/execution/broker/deals 等执行词汇 (E6)。"""
    _write_strategy_cache(tmp_path)
    _write_concept_fixture(tmp_path)
    _write_snapshot(tmp_path)
    client = _make_client(tmp_path)

    hub = build_pool_hub(tmp_path)
    keys = list(_all_keys(hub))
    # POOL-05 新端点响应同受词汇守卫约束
    keys.extend(_all_keys(client.get("/api/pool/history", params={"as_of": _AS_OF}).json()))
    keys.extend(_all_keys(client.get("/api/pool/dates").json()))
    for banned in ("orders", "execution", "broker", "deals"):
        assert banned not in keys, f"pool 响应含执行词汇键: {banned}"
