"""CONCEPT-01/02/03/05/07 — 概念 PIT 历史归档 + 归属状态机 + EOD 钩子 + AST 守卫。

Hermetic: 全部走 tmp_path, 不触碰真实 data/ 目录; 不 import 其他测试模块;
生产代码 import 一律放测试函数内 (顶层只 import stdlib / polars / pytest)。
"""
from __future__ import annotations

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
