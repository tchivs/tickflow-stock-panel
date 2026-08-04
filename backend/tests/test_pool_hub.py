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
                        "open_gap": 3.21,
                        "change_pct": 5.1,
                        "hit_factors": ["竞价多头"],
                    },
                    {
                        "symbol": _SYMBOLS["Y"],
                        "open_gap": 1.5,
                        "change_pct": 2.3,
                        "hit_factors": ["竞价多头", "盘前强势量化"],
                    },
                ],
            },
            "auction_preopen_quant": {
                "total": 2,
                "as_of": _AS_OF,
                "rows": [
                    {
                        "symbol": _SYMBOLS["Y"],
                        "open_gap": 1.5,
                        "change_pct": 2.3,
                        "hit_factors": ["竞价多头", "盘前强势量化"],
                    },
                    {
                        "symbol": _SYMBOLS["Z"],
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


# ================================================================
# Task 1 — build_pool_hub 投影
# ================================================================


def test_build_pool_hub_single_as_of_counts_and_columns(tmp_path):
    """单一 as_of 来源: 每策略 total == 持久化行数, 每行恰含五列 + cross_resonance。"""
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
        "open_gap",
        "change_pct",
        "concept_board",
        "hit_factors",
        "cross_resonance",
    }
    for strategy in strategies.values():
        for row in strategy["rows"]:
            assert set(row) == expected_keys
            assert row["code"] == row["symbol"].split(".", 1)[0]

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
    app = FastAPI()
    app.include_router(pool_api.router)
    app.state.repo = _FakeRepo(tmp_path)
    app.state.strategy_engine = engine
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
    assert resp.json() == {"as_of": None, "updated_at": None, "strategies": [], "resonance_count": 0}


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


def _feature_sources() -> tuple[str, str]:
    backend = Path(__file__).resolve().parents[1]
    service_src = (backend / "app" / "services" / "pool_hub.py").read_text(encoding="utf-8")
    api_src = (backend / "app" / "api" / "pool.py").read_text(encoding="utf-8")
    return service_src, api_src


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
    """pool_hub.py / pool.py 不得 import 任何执行族模块 (T-18-01)。"""
    service_src, api_src = _feature_sources()
    for src in (service_src, api_src):
        for module in _imported_module_names(src):
            assert not _EXECUTION_TOKEN.search(module), (
                f"pool 特性引入了执行族模块: {module}"
            )


def test_pool_api_is_get_only():
    """pool.py 只允许 GET 路由 (T-18-01)。"""
    _service_src, api_src = _feature_sources()
    methods = re.findall(r"@router\.(get|post|put|delete|patch)\b", api_src)
    assert methods == ["get"], f"pool API 出现了非 GET 路由: {methods}"


def test_build_pool_hub_has_no_write_path():
    """build_pool_hub 是纯读者: 无写模式 open / write_parquet / os.replace / unlink / mkdir。"""
    service_src, _api_src = _feature_sources()
    for pattern in _WRITE_PATTERNS:
        assert not pattern.search(service_src), f"pool_hub.py 出现写路径: {pattern.pattern}"


def _all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _all_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _all_keys(item)


def test_hub_response_has_no_execution_vocabulary(tmp_path):
    """Hub 响应键不含 orders/execution/broker/deals 等执行词汇。"""
    _write_strategy_cache(tmp_path)
    _write_concept_fixture(tmp_path)
    hub = build_pool_hub(tmp_path)
    keys = list(_all_keys(hub))
    for banned in ("orders", "execution", "broker", "deals"):
        assert banned not in keys, f"Hub 响应含执行词汇键: {banned}"
