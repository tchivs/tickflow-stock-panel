"""GUEST-01 游客脱敏 — 服务端权威 DTO 边界 + 真实中间件端点测试 (Task 1)。

Task 1 (tracer): 经由真实 ``auth_middleware`` 的垂直切片 —
- ``mask_guest_hub`` 纯变换单元测试 (代码/名称/代码掩码, open_gap 省略, 市场因子保留);
- 端点测试: 无 cookie → ``mode: "guest"`` 脱敏; 有效 cookie → ``mode: "vip"`` 明文;
  无效 cookie → guest; 非游客面 401。

Task 2/3 的 GUEST-02 显示层证明与游客面安全守卫在后续提交追加 (同一文件)。
"""
from __future__ import annotations

import ast
import copy
import json
import re
from pathlib import Path
from types import SimpleNamespace

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import pool as pool_api
from app.api import screener as screener_api
from app.services.guest_masking import MASKED_IDENTITY, mask_guest_hub

from app.services.pool_hub import build_pool_hub

_AS_OF = "2026-08-04"
# 符号映射: X / Y / Z / W
_SYMBOLS = {
    "X": "600000.SH",
    "Y": "600001.SH",
    "Z": "600002.SH",
    "W": "600003.SH",
}

# 持久化行真实名称 (名称投影来源; 与 test_pool_hub 同值)
_NAMES = {
    "X": "人工智能龙头",
    "Y": "宁德新能源",
    "Z": "新能科技",
    "W": "早盘之星科技",
}


def _write_strategy_cache(data_dir: Path) -> None:
    """写入 hermetic 策略缓存 — 单一 as_of, 3 个竞价策略 (含真实名称)。"""
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
    """写入 hermetic 概念扩展数据 (ExtConfig snapshot, field=所属概念)。"""
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


class _FakeRepo:
    """最小 repo 桩: 只需 store.data_dir (与 test_pool_hub 同型)。"""

    def __init__(self, data_dir: Path):
        self.store = SimpleNamespace(data_dir=data_dir)


def _make_guest_client(tmp_path: Path, monkeypatch, engine=None) -> TestClient:
    """最小 FastAPI 应用 + 真实 ``auth_middleware`` + 股池/策略路由。

    ``is_configured`` 固定为 True, 因此会话判定走 cookie 分支:
    - 无 cookie / 无效会话 → 游客分支 (仅两个只读 GET 放行);
    - 有效会话 → 设置 reviewer_principal (VIP)。
    """
    from app.main import auth_middleware
    from app.services import auth as auth_service

    monkeypatch.setattr(auth_service, "is_configured", lambda: True)

    app = FastAPI()
    app.middleware("http")(auth_middleware)
    app.include_router(pool_api.router)
    app.include_router(screener_api.router)
    app.state.repo = _FakeRepo(tmp_path)
    app.state.strategy_engine = engine
    return TestClient(app)


def _sample_hub() -> dict:
    """一份 明文 Hub (与 build_pool_hub 投影形状一致), 供纯变换单元测试。"""
    return {
        "as_of": _AS_OF,
        "updated_at": 1722758400000,
        "resonance_count": 1,
        "strategies": [
            {
                "id": "auction_bullish",
                "name": "竞价多头",
                "total": 1,
                "rows": [
                    {
                        "symbol": _SYMBOLS["X"],
                        "code": "600000",
                        "name": _NAMES["X"],
                        "open_gap": 3.21,
                        "change_pct": 5.1,
                        "concept_board": ["人工智能"],
                        "hit_factors": ["竞价多头"],
                        "cross_resonance": False,
                    }
                ],
            }
        ],
    }


# ================================================================
# Task 1 — mask_guest_hub 纯变换单元测试
# ================================================================


def test_mask_guest_hub_masks_identity_and_keeps_market_factors():
    """游客行: code/name/symbol == ******, open_gap 省略, 涨跌幅/概念/关联因子保留。"""
    masked = mask_guest_hub(_sample_hub())
    row = masked["strategies"][0]["rows"][0]

    assert row["code"] == "******"
    assert row["name"] == "******"
    assert row["symbol"] == "******"
    assert "open_gap" not in row
    assert row["change_pct"] == 5.1
    assert row["concept_board"] == ["人工智能"]
    assert row["hit_factors"] == ["竞价多头"]
    assert row["cross_resonance"] is False


def test_mask_guest_hub_preserves_strategy_and_top_level():
    """策略 name/total 与顶层 as_of/updated_at/resonance_count 不变。"""
    hub = _sample_hub()
    masked = mask_guest_hub(hub)

    assert masked["as_of"] == hub["as_of"]
    assert masked["updated_at"] == hub["updated_at"]
    assert masked["resonance_count"] == hub["resonance_count"]
    strategy = masked["strategies"][0]
    assert strategy["id"] == "auction_bullish"
    assert strategy["name"] == "竞价多头"
    assert strategy["total"] == 1
    assert len(strategy["rows"]) == 1


def test_mask_guest_hub_does_not_mutate_input():
    """纯拷贝: 输入 hub 不被修改 (GUEST-02 — 掩码绝不触碰服务层/持久化结果)。"""
    hub = _sample_hub()
    before = copy.deepcopy(hub)
    mask_guest_hub(hub)
    assert hub == before


# ================================================================
# Task 1 — 端点测试 (真实 auth_middleware)
# ================================================================


def test_guest_no_cookie_returns_masked_hub(tmp_path, monkeypatch):
    """无 cookie → 200, mode == "guest", 每行 code/name/symbol 脱敏, 无 open_gap。"""
    _write_strategy_cache(tmp_path)
    _write_concept_fixture(tmp_path)
    client = _make_guest_client(tmp_path, monkeypatch)

    resp = client.get("/api/pool/hub")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "guest"
    assert body["as_of"] == _AS_OF
    assert len(body["strategies"]) == 3
    for strategy in body["strategies"]:
        for row in strategy["rows"]:
            assert row["code"] == "******"
            assert row["name"] == "******"
            assert row["symbol"] == "******"
            assert "open_gap" not in row


def test_vip_valid_cookie_returns_clear_hub(tmp_path, monkeypatch):
    """有效 tf_session cookie → 200, mode == "vip", 真实 code/name/open_gap 明文。"""
    from app.services import auth as auth_service

    _write_strategy_cache(tmp_path)
    _write_concept_fixture(tmp_path)
    monkeypatch.setattr(auth_service, "is_valid_session", lambda token: True)
    monkeypatch.setattr(auth_service, "resolve_authenticated_reviewer", lambda token: "reviewer_test")
    client = _make_guest_client(tmp_path, monkeypatch)
    client.cookies.set("tf_session", "valid-token")

    resp = client.get("/api/pool/hub")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "vip"
    bullish = next(s for s in body["strategies"] if s["id"] == "auction_bullish")
    x_row = next(r for r in bullish["rows"] if r["symbol"] == _SYMBOLS["X"])
    assert x_row["code"] == "600000"
    assert x_row["name"] == _NAMES["X"]
    assert x_row["open_gap"] == 3.21
    assert x_row["change_pct"] == 5.1


def test_invalid_cookie_returns_guest(tmp_path, monkeypatch):
    """无效/过期 cookie → 200 guest (不泄露身份, 不 401)。"""
    from app.services import auth as auth_service

    _write_strategy_cache(tmp_path)
    monkeypatch.setattr(auth_service, "is_valid_session", lambda token: False)
    client = _make_guest_client(tmp_path, monkeypatch)
    client.cookies.set("tf_session", "stale-token")

    resp = client.get("/api/pool/hub")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "guest"
    row = body["strategies"][0]["rows"][0]
    assert row["code"] == "******"


# ================================================================
# Task 2 — GUEST-02 显示层证明
# ================================================================


def test_build_pool_hub_rows_stay_unmasked(tmp_path):
    """服务层恒明文 (GUEST-02): build_pool_hub 行带真实 code/name/open_gap。"""
    _write_strategy_cache(tmp_path)
    _write_concept_fixture(tmp_path)
    hub = build_pool_hub(tmp_path)

    assert hub["as_of"] == _AS_OF
    for strategy in hub["strategies"]:
        for row in strategy["rows"]:
            assert row["code"] != "******"
            assert row["name"] != "******"
            assert row["name"]  # 名称投影有值
            assert "open_gap" in row


def test_guest_mask_does_not_mutate_cache_or_hub(tmp_path):
    """掩码是纯序列化拷贝: 原 hub 与磁盘 strategy_cache.json 仍含真实身份。"""
    _write_strategy_cache(tmp_path)
    _write_concept_fixture(tmp_path)
    hub = build_pool_hub(tmp_path)
    before = copy.deepcopy(hub)

    masked = mask_guest_hub(hub)
    assert hub == before  # 输入 hub 未被修改

    # 磁盘缓存仍明文 (含真实 symbol/name/open_gap)
    raw = json.loads(
        (tmp_path / "user_data" / "strategy_cache.json").read_text(encoding="utf-8")
    )
    x_row = raw["results"]["auction_bullish"]["rows"][0]
    assert x_row["symbol"] == _SYMBOLS["X"]
    assert x_row["name"] == _NAMES["X"]
    assert x_row["open_gap"] == 3.21

    # 掩码输出确实不含真实身份
    masked_row = masked["strategies"][0]["rows"][0]
    assert masked_row["symbol"] == MASKED_IDENTITY


# ================================================================
# Task 2 — guest_masking.py 隔离守卫 (AST, 镜像 POOL-03)
# ================================================================

_GUEST_BANNED_IMPORT = re.compile(
    r"engine|strategy_cache|persistence|parquet|broker|order|execution|portfolio|"
    r"watchlist|position|account|trade",
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


def _guest_masking_source() -> str:
    backend = Path(__file__).resolve().parents[1]
    return (backend / "app" / "services" / "guest_masking.py").read_text(encoding="utf-8")


def _imported_module_names(source: str) -> list[str]:
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_guest_masking_imports_no_engine_or_persistence():
    """guest_masking.py 不得 import 任何 engine/persistence/execution 模块 (GUEST-02)。"""
    src = _guest_masking_source()
    for module in _imported_module_names(src):
        assert not _GUEST_BANNED_IMPORT.search(module), (
            f"guest_masking.py 引入了禁用模块: {module}"
        )


def test_guest_masking_has_no_write_path():
    """掩码是纯读者/拷贝器: 无写模式 open / write_parquet / os.replace / unlink / mkdir。"""
    src = _guest_masking_source()
    for pattern in _WRITE_PATTERNS:
        assert not pattern.search(src), f"guest_masking.py 出现写路径: {pattern.pattern}"
