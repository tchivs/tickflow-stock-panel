"""CONCEPT-01/02/03/05/07 — 概念 PIT 历史归档 + 归属状态机 + EOD 钩子 + AST 守卫。

Hermetic: 全部走 tmp_path, 不触碰真实 data/ 目录; 不 import 其他测试模块;
生产代码 import 一律放测试函数内 (顶层只 import stdlib / polars / pytest)。
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import polars as pl
import pytest

_AS_OF = "2026-08-04"

# 符号映射: X / Y / Z / W (镜像 test_pool_hub)
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
    """写入 hermetic 当前 ext 快照 (config.json + part.parquet)。

    ``rows=[]`` → 只写 config.json, 不写 part.parquet (模拟「配置已安装但数据缺失」)。
    镜像 ``ext_presets._concept_preset`` / ``_industry_preset`` 形状 (snapshot 模式)。
    """
    from app.services.ext_data import ExtConfig, ExtField, PullConfig

    config_id = "ext_gn_ths" if kind == "gn_ths" else "ext_hy_ths"
    field_name = "所属概念" if kind == "gn_ths" else "所属同花顺行业"
    if rows is None:
        rows = [
            {
                "symbol": _SYMBOLS["X"],
                "code": "600000",
                "股票代码": "600000",
                "股票简称": _NAMES["X"],
                field_name: "人工智能",
            },
            {
                "symbol": _SYMBOLS["Y"],
                "code": "600001",
                "股票代码": "600001",
                "股票简称": _NAMES["Y"],
                field_name: "人工智能;新能源",
            },
            {
                "symbol": _SYMBOLS["Z"],
                "code": "600002",
                "股票代码": "600002",
                "股票简称": _NAMES["Z"],
                field_name: "新能源",
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


# ---------------------------------------------------------------------------
# Task 1 — CONCEPT-01/07 写侧 + CONCEPT-02 读侧原语
# ---------------------------------------------------------------------------

def test_capture_writes_partition_and_manifest(tmp_path):
    """CONCEPT-01: capture 写 ext_history/{kind}/date={as_of}/part.parquet + manifest.json。"""
    from app.services.concept_history import capture

    _write_concept_ext(tmp_path, kind="gn_ths")
    _write_concept_ext(tmp_path, kind="hy_ths")

    result = capture(tmp_path, "2026-08-06")

    assert result["as_of"] == "2026-08-06"
    assert result["gn_ths"] == {"written": True, "rows": 3}
    assert result["hy_ths"] == {"written": True, "rows": 3}

    for kind in ("gn_ths", "hy_ths"):
        part = tmp_path / "ext_history" / kind / "date=2026-08-06" / "part.parquet"
        manifest_path = tmp_path / "ext_history" / kind / "date=2026-08-06" / "manifest.json"
        assert part.exists(), f"{kind} part.parquet 缺失"
        assert manifest_path.exists(), f"{kind} manifest.json 缺失"
        df = pl.read_parquet(str(part))
        assert len(df) == 3
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert {
            "as_of", "kind", "dimension_field", "source_url", "fetched_at",
            "captured_at", "rows", "schema_version", "sha256",
        } <= set(manifest)
        assert manifest["as_of"] == "2026-08-06"
        assert manifest["kind"] == kind
        assert manifest["rows"] == 3
        assert re.fullmatch(r"[0-9a-f]{64}", manifest["sha256"])


def test_capture_rejects_bad_as_of(tmp_path):
    """严格日期: 非法 as_of → ValueError (防路径穿越); read_partition 非法 → None。"""
    from app.services.concept_history import capture, read_partition

    _write_concept_ext(tmp_path, kind="gn_ths")
    for bad in ("2026-8-6", "../../x", "2026-08-06T00:00:00"):
        with pytest.raises(ValueError):
            capture(tmp_path, bad)
    assert read_partition(tmp_path, "gn_ths", "2026-8-6") is None


def test_capture_idempotent_no_tmp_residue(tmp_path):
    """幂等/无残留: 同 as_of 两次 capture → 单分区单 manifest, 无 .tmp。"""
    from app.services.concept_history import capture, list_partition_dates, partition_sha256

    _write_concept_ext(tmp_path, kind="gn_ths")
    _write_concept_ext(tmp_path, kind="hy_ths")

    first = capture(tmp_path, "2026-08-06")
    second = capture(tmp_path, "2026-08-06")
    assert first == second
    assert list(tmp_path.rglob("*.tmp")) == []

    for kind in ("gn_ths", "hy_ths"):
        assert list_partition_dates(tmp_path, kind) == ["2026-08-06"]
        sha = partition_sha256(tmp_path, kind, "2026-08-06")
        assert sha and len(sha) == 64
    assert (
        partition_sha256(tmp_path, "gn_ths", "2026-08-06")
        == partition_sha256(tmp_path, "gn_ths", "2026-08-06")
    )


def test_capture_honest_skip(tmp_path):
    """诚实 skip: 快照缺失 / 0 行 → 不写文件, 返回 {written: False, rows: 0} 且不抛。"""
    from app.services.concept_history import capture

    # ext_gn_ths 配置缺失
    _write_concept_ext(tmp_path, kind="hy_ths")
    result = capture(tmp_path, "2026-08-06")
    assert result["gn_ths"] == {"written": False, "rows": 0, "reason": "no config"}
    assert not (tmp_path / "ext_history" / "gn_ths").exists()

    # part.parquet 缺失 (0 行数据) → empty snapshot
    _write_concept_ext(tmp_path, kind="gn_ths", rows=[])
    result2 = capture(tmp_path, "2026-08-06")
    assert result2["gn_ths"]["written"] is False
    assert result2["gn_ths"]["rows"] == 0
    assert not (tmp_path / "ext_history" / "gn_ths" / "date=2026-08-06").exists()


def test_read_partition_primitives(tmp_path):
    """CONCEPT-02 读侧原语: read_partition / list_partition_dates / partition_sha256。"""
    from app.services.concept_history import list_partition_dates, partition_sha256, read_partition

    # 手写分区 + manifest
    part_dir = tmp_path / "ext_history" / "gn_ths" / "date=2026-08-06"
    part_dir.mkdir(parents=True)
    pl.DataFrame(
        [{"symbol": _SYMBOLS["X"], "所属概念": "人工智能"}]
    ).write_parquet(part_dir / "part.parquet")
    (part_dir / "manifest.json").write_text(
        json.dumps({
            "as_of": "2026-08-06",
            "kind": "gn_ths",
            "dimension_field": "所属概念",
            "captured_at": "2026-08-06T10:00:00",
        }),
        encoding="utf-8",
    )

    out = read_partition(tmp_path, "gn_ths", "2026-08-06")
    assert out is not None
    assert out["rows"] == [{"symbol": _SYMBOLS["X"], "所属概念": "人工智能"}]
    assert out["manifest"]["captured_at"] == "2026-08-06T10:00:00"

    # 分区缺失 → None
    assert read_partition(tmp_path, "gn_ths", "2026-08-07") is None

    # manifest 缺失 → 合成缺省 (不抛)
    part_dir2 = tmp_path / "ext_history" / "gn_ths" / "date=2026-08-07"
    part_dir2.mkdir(parents=True)
    pl.DataFrame(
        [{"symbol": _SYMBOLS["X"], "所属概念": "人工智能"}]
    ).write_parquet(part_dir2 / "part.parquet")
    out2 = read_partition(tmp_path, "gn_ths", "2026-08-07")
    assert out2["manifest"] == {"as_of": "2026-08-07", "kind": "gn_ths"}

    # list desc 且排除无 part.parquet 目录
    (tmp_path / "ext_history" / "gn_ths" / "date=2026-08-05").mkdir(parents=True)
    assert list_partition_dates(tmp_path, "gn_ths") == ["2026-08-07", "2026-08-06"]

    # sha256 稳定
    sha = partition_sha256(tmp_path, "gn_ths", "2026-08-06")
    assert sha and len(sha) == 64
    assert partition_sha256(tmp_path, "gn_ths", "missing") is None


def test_capture_from_upstream_writes_partition(tmp_path, monkeypatch):
    """OQ-3: capture_from_upstream 同步抓取 → flatten → 写分区 (共用写路径)。"""
    import httpx

    from app.services.concept_history import capture_from_upstream, read_partition

    _write_concept_ext(tmp_path, kind="gn_ths")
    _write_concept_ext(tmp_path, kind="hy_ths")

    payload = [
        {"symbol": _SYMBOLS["X"], "name": _NAMES["X"], "concepts": ["人工智能"]},
        {"symbol": _SYMBOLS["Y"], "name": _NAMES["Y"], "concepts": ["人工智能", "新能源"]},
    ]

    class _FakeResp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    class _FakeClient:
        def __init__(self, payload):
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return _FakeResp(self._payload)

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _FakeClient(payload))

    result = capture_from_upstream(tmp_path, "2026-08-06")
    assert result["gn_ths"]["written"] is True
    assert result["gn_ths"]["rows"] == 2

    part = read_partition(tmp_path, "gn_ths", "2026-08-06")
    assert part is not None
    rows = part["rows"]
    assert len(rows) == 2
    assert rows[0]["所属概念"] == "人工智能"
    assert rows[1]["所属概念"] == "人工智能;新能源"
    assert rows[0]["symbol"] == _SYMBOLS["X"]


def test_capture_from_upstream_fetch_failure_skips(tmp_path, monkeypatch):
    """OQ-3: 抓取失败 → warning + skip, 不抛不写。"""
    import httpx

    from app.services.concept_history import capture_from_upstream

    _write_concept_ext(tmp_path, kind="gn_ths")
    _write_concept_ext(tmp_path, kind="hy_ths")

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            raise RuntimeError("boom")

    monkeypatch.setattr(httpx, "Client", lambda *a, **k: _FakeClient())

    result = capture_from_upstream(tmp_path, "2026-08-06")
    assert result["gn_ths"]["written"] is False
    assert result["gn_ths"]["rows"] == 0
    assert not (tmp_path / "ext_history" / "gn_ths").exists()


# ---------------------------------------------------------------------------
# Task 2 — CONCEPT-02/03 归属状态机 + CONCEPT-07 API 透传
# ---------------------------------------------------------------------------

def _strategies_by_id(hub: dict) -> dict:
    return {s["id"]: s for s in hub["strategies"]}


def _write_strategy_cache(data_dir: Path) -> None:
    """写入 hermetic 策略缓存 — 单一 as_of, 3 策略 (Y 交叉共振)。"""
    payload = {
        "as_of": _AS_OF,
        "results": {
            "auction_bullish": {
                "total": 2,
                "as_of": _AS_OF,
                "rows": [
                    {
                        "symbol": _SYMBOLS["X"], "name": _NAMES["X"],
                        "open_gap": 3.21, "change_pct": 5.1,
                        "hit_factors": ["竞价多头"],
                    },
                    {
                        "symbol": _SYMBOLS["Y"], "name": _NAMES["Y"],
                        "open_gap": 1.5, "change_pct": 2.3,
                        "hit_factors": ["盘前强势量化", "竞价多头"],
                    },
                ],
            },
            "auction_preopen_quant": {
                "total": 2,
                "as_of": _AS_OF,
                "rows": [
                    {
                        "symbol": _SYMBOLS["Y"], "name": _NAMES["Y"],
                        "open_gap": 1.5, "hit_factors": ["盘前强势量化", "竞价多头"],
                    },
                    {
                        "symbol": _SYMBOLS["Z"], "name": _NAMES["Z"],
                        "open_gap": 0.5, "hit_factors": ["盘前强势量化"],
                    },
                ],
            },
            "auction_early_star": {
                "total": 1,
                "as_of": _AS_OF,
                "rows": [
                    {
                        "symbol": _SYMBOLS["W"], "name": _NAMES["W"],
                        "open_gap": 0.1, "change_pct": 0.9,
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


def _write_snapshot(data_dir: Path, as_of: str = _AS_OF) -> Path:
    """写冻结式点快照 part.json (镜像 test_pool_hub._write_snapshot 默认形状)。"""
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
                    {
                        "symbol": _SYMBOLS["X"], "name": _NAMES["X"],
                        "open_gap": 3.21, "change_pct": 5.1,
                        "hit_factors": ["竞价多头"],
                    },
                    {
                        "symbol": _SYMBOLS["Y"], "name": _NAMES["Y"],
                        "open_gap": 1.5, "change_pct": 2.3,
                        "hit_factors": ["盘前强势量化", "竞价多头"],
                    },
                ],
            },
            "auction_preopen_quant": {
                "total": 2,
                "as_of": as_of,
                "rows": [
                    {
                        "symbol": _SYMBOLS["Y"], "name": _NAMES["Y"],
                        "open_gap": 1.5, "hit_factors": ["盘前强势量化", "竞价多头"],
                    },
                    {
                        "symbol": _SYMBOLS["Z"], "name": _NAMES["Z"],
                        "open_gap": 0.5, "hit_factors": ["盘前强势量化"],
                    },
                ],
            },
            "auction_early_star": {
                "total": 1,
                "as_of": as_of,
                "rows": [
                    {
                        "symbol": _SYMBOLS["W"], "name": _NAMES["W"],
                        "open_gap": 0.1, "change_pct": 0.9,
                        "hit_factors": ["早盘之星"],
                    },
                ],
            },
        },
    }
    path = data_dir / "screener_results" / f"date={as_of}" / "part.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write_partition_fixture(data_dir: Path, as_of: str, field: str, concepts_map: dict) -> None:
    """直接写 ext_history/gn_ths/date={as_of}/part.parquet + manifest.json (读侧用例, 不依赖 capture)。"""
    part_dir = data_dir / "ext_history" / "gn_ths" / f"date={as_of}"
    part_dir.mkdir(parents=True, exist_ok=True)
    rows = [{"symbol": sym, field: ";".join(concepts)} for sym, concepts in concepts_map.items()]
    pl.DataFrame(rows).write_parquet(part_dir / "part.parquet")
    manifest = {
        "as_of": as_of,
        "kind": "gn_ths",
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


def test_build_pool_hub_snapshot_as_of_partition_priority(tmp_path):
    """CONCEPT-02: as_of 分区命中 → 分区优先于当前 ext, 归属 as_of_snapshot + 生效日期。"""
    from app.services.pool_hub import build_pool_hub_snapshot

    _write_strategy_cache(tmp_path)
    _write_concept_ext(tmp_path, kind="gn_ths")  # 当前 ext: X → 人工智能
    _write_snapshot(tmp_path, as_of=_AS_OF)
    # D 日分区: 内容与当前 ext 不同 — X 只有 新能源
    _write_partition_fixture(tmp_path, _AS_OF, "所属概念", {_SYMBOLS["X"]: ["新能源"]})

    hub = build_pool_hub_snapshot(tmp_path, _AS_OF)
    assert hub["concept_attribution"] == "as_of_snapshot"
    assert hub["concept_effective_date"] == _AS_OF
    assert hub["concept_captured_at"] == "2026-08-04T10:00:00"

    strategies = _strategies_by_id(hub)
    x_row = next(r for r in strategies["auction_bullish"]["rows"] if r["symbol"] == _SYMBOLS["X"])
    assert x_row["concept_board"] == ["新能源"]  # 分区优先于当前 ext (人工智能)


def test_attribution_three_state_machine(tmp_path):
    """CONCEPT-03: current_snapshot / unavailable / 无 config 默认 current_snapshot。"""
    from app.services.pool_hub import build_pool_hub_snapshot

    # 有概念 config + 当前行非空 + 无分区 → current_snapshot
    _write_strategy_cache(tmp_path)
    _write_concept_ext(tmp_path, kind="gn_ths")
    _write_snapshot(tmp_path, as_of=_AS_OF)
    hub = build_pool_hub_snapshot(tmp_path, _AS_OF)
    assert hub["concept_attribution"] == "current_snapshot"
    assert "concept_effective_date" not in hub  # 回退态不追加
    assert "concept_captured_at" not in hub

    # 有概念 config 但当前快照缺失 → unavailable
    tmp2 = tmp_path / "empty_concept"
    _write_strategy_cache(tmp2)
    _write_concept_ext(tmp2, kind="gn_ths", rows=[])
    _write_snapshot(tmp2, as_of=_AS_OF)
    hub2 = build_pool_hub_snapshot(tmp2, _AS_OF)
    assert hub2["concept_attribution"] == "unavailable"
    assert "concept_effective_date" not in hub2

    # 无概念 config → current_snapshot (向后兼容默认)
    tmp3 = tmp_path / "no_concept"
    _write_strategy_cache(tmp3)
    _write_snapshot(tmp3, as_of=_AS_OF)
    hub3 = build_pool_hub_snapshot(tmp3, _AS_OF)
    assert hub3["concept_attribution"] == "current_snapshot"


def test_empty_state_regression(tmp_path):
    """空态回归: 无快照 → 精确 dict 一字不动; 空缓存 → 无 attribution 键。"""
    from app.services.pool_hub import build_pool_hub, build_pool_hub_snapshot

    hub = build_pool_hub_snapshot(tmp_path, _AS_OF)
    assert hub == {
        "as_of": None,
        "available": False,
        "strategies": [],
        "resonance_count": 0,
        "updated_at": None,
        "concept_attribution": "current_snapshot",
        "snapshot_origin": None,
    }

    hub2 = build_pool_hub(tmp_path)
    assert hub2 == {"as_of": None, "updated_at": None, "strategies": [], "resonance_count": 0}


def test_pool_history_api_passthrough_as_of_snapshot(tmp_path):
    """CONCEPT-07: /api/pool/history?as_of=D 载荷含 attribution + effective/captured_at (route 零改动)。"""
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import pool as pool_api

    _write_strategy_cache(tmp_path)
    _write_concept_ext(tmp_path, kind="gn_ths")
    _write_snapshot(tmp_path, as_of=_AS_OF)
    _write_partition_fixture(tmp_path, _AS_OF, "所属概念", {_SYMBOLS["X"]: ["新能源"]})

    app = FastAPI()
    app.include_router(pool_api.router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
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


# ---------------------------------------------------------------------------
# Task 3 — CONCEPT-05 AST 守卫 (按模块拆分) + OQ-3 探针脚本
# ---------------------------------------------------------------------------

# 执行族 token: 出现在 import / 引用中即失败 (镜像 test_pool_hub._EXECUTION_TOKEN)
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


def _imported_module_names(source: str) -> list[str]:
    """ast 遍历提取所有 import 模块名 (镜像 test_pool_hub)。"""
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_concept_history_ast_guard_writes_only_ext_history():
    """CONCEPT-05 E2 形: concept_history 只写 ext_history, 所有含写路径函数引用 _HISTORY_ROOT。"""
    backend = Path(__file__).resolve().parents[1]
    src = (backend / "app" / "services" / "concept_history.py").read_text(encoding="utf-8")

    m = re.search(r'_HISTORY_ROOT\s*=\s*"([^"]+)"', src)
    assert m is not None, "concept_history.py 缺少 _HISTORY_ROOT 常量"
    assert m.group(1) == "ext_history"

    tree = ast.parse(src)
    write_funcs = {"replace", "mkdir"}

    def _has_write(node) -> bool:
        for c in ast.walk(node):
            if isinstance(c, ast.Call):
                f = c.func
                if isinstance(f, ast.Attribute) and f.attr in write_funcs:
                    return True
                if isinstance(f, ast.Attribute) and f.attr == "write_parquet":
                    return True
                if isinstance(f, ast.Name) and f.id == "open":
                    return True
        return False

    checked = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and _has_write(node):
            func_src = ast.get_source_segment(src, node) or ""
            assert "_HISTORY_ROOT" in func_src, (
                f"{node.name} 含写路径但未引用 _HISTORY_ROOT (只写 ext_history)"
            )
            checked += 1
    assert checked >= 1, "concept_history.py 未发现任何含写路径函数 (守卫形同虚设)"


def test_concept_history_no_execution_imports_no_strategy_cache():
    """CONCEPT-05 E1/E3 形: 无执行族 import; 无运行时缓存 (strategy_cache) 引用。"""
    backend = Path(__file__).resolve().parents[1]
    src = (backend / "app" / "services" / "concept_history.py").read_text(encoding="utf-8")

    for module in _imported_module_names(src):
        assert not _EXECUTION_TOKEN.search(module), (
            f"concept_history.py 引入了执行族模块: {module}"
        )
    assert "strategy_cache" not in src, "concept_history.py 引用了运行时缓存 (strategy_cache)"
    assert "write_cache" not in src, "concept_history.py 引用了 write_cache"


def test_pool_hub_remains_zero_write():
    """CONCEPT-05 拆分复核: pool_hub.py 仍零写路径 (POOL-03 既有守卫的独立复核)。"""
    backend = Path(__file__).resolve().parents[1]
    src = (backend / "app" / "services" / "pool_hub.py").read_text(encoding="utf-8")
    for pattern in _WRITE_PATTERNS:
        assert not pattern.search(src), f"pool_hub.py 出现写路径: {pattern.pattern}"


def test_probe_concept_drift_script_compiles_and_references():
    """OQ-3 探针: probe_concept_drift.py 存在, 引用 capture/partition_sha256/drift.jsonl/ext_history。"""
    import py_compile

    backend = Path(__file__).resolve().parents[1]
    script = backend / "scripts" / "probe_concept_drift.py"
    assert script.exists(), "probe_concept_drift.py 缺失"
    py_compile.compile(str(script), doraise=True)
    text = script.read_text(encoding="utf-8")
    assert "capture" in text
    assert "partition_sha256" in text
    assert "drift.jsonl" in text
    assert "ext_history" in text


def _write_snapshot_with_origin(data_dir: Path, as_of: str, origin: str) -> Path:
    """写指定 ``snapshot_origin`` 的点快照 (镜像 _write_snapshot 形状, 重写 provenance 键)。"""
    path = _write_snapshot(data_dir, as_of=as_of)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["snapshot_origin"] = origin
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_pool_history_backfilled_date_concept_fallback(tmp_path):
    """PB-03/CONCEPT-05: 回填日概念归属诚实回退 — 无 ext_history 分区 → current_snapshot 且不伪造时间键。

    键集锁: 回退态载荷顶层绝不追加 ``concept_effective_date``/``concept_captured_at``
    (当前概念快照不冒充历史日, CONCEPT-05)。正向对照证明锁非空转: 同 data_dir 建
    ``ext_history/gn_ths/date=D`` 分区 → 同一 as_of 翻转为 as_of_snapshot + 两键出现
    (读侧机制真实, 回退是分区缺失的诚实结果而非功能缺失)。origin 无关性: 回退判定
    只由 ext_history 分区决定, 与快照 snapshot_origin 正交 (backfill/eod 同布置均
    current_snapshot — 回填不特殊化概念语义)。
    """
    from app.services.pool_hub import build_pool_hub_snapshot

    d = "2026-07-27"  # 镜像 33-01 真实回填首日 (端到端同源)

    # 布置 1: 回填快照 (origin=backfill) + 当前 ext config 就位 + 无 ext_history 分区
    # (沙箱状态镜像: ext_data 存在, ext_history 缺失 → 全部回填日 current_snapshot)
    _write_concept_ext(tmp_path, kind="gn_ths")
    _write_snapshot_with_origin(tmp_path, as_of=d, origin="backfill")
    hub = build_pool_hub_snapshot(tmp_path, d)
    assert hub["concept_attribution"] == "current_snapshot"
    assert "concept_effective_date" not in hub  # 键集锁: 回退绝不携带 PIT 时间戳
    assert "concept_captured_at" not in hub

    # 布置 2 (origin 无关性): 换 eod 快照 → 仍 current_snapshot (归属不因回填特殊化)
    _write_snapshot_with_origin(tmp_path, as_of=d, origin="eod")
    hub_eod = build_pool_hub_snapshot(tmp_path, d)
    assert hub_eod["concept_attribution"] == "current_snapshot"
    assert "concept_effective_date" not in hub_eod
    assert "concept_captured_at" not in hub_eod

    # 布置 3 (正向对照): 建 ext_history/gn_ths/date=D 分区 → 同一 as_of 翻转为
    # as_of_snapshot + effective/captured_at 两键出现 (证明键集锁非空转)
    _write_partition_fixture(tmp_path, d, "所属概念", {_SYMBOLS["X"]: ["新能源"]})
    hub_with_partition = build_pool_hub_snapshot(tmp_path, d)
    assert hub_with_partition["concept_attribution"] == "as_of_snapshot"
    assert hub_with_partition["concept_effective_date"] == d
    assert hub_with_partition["concept_captured_at"] == "2026-08-04T10:00:00"
