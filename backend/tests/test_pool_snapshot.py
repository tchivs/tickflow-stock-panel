"""POOL-04/05 冻结式点快照服务 — 单元测试 (hermetic, 不碰真实数据目录)。

- 快照 round-trip / 原子 / 幂等 / 空策略保留 / 策略指纹 / 日期列表 / as_of 校验。
- Task 4: run_all 落快照钩子 + ``run_all_with_hits`` 共享核心形状。
"""
from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

_AS_OF = "2026-08-04"
_SNAPSHOT_ROOT = "screener_results"


def _snapshot_path(data_dir: Path, as_of: str) -> Path:
    return data_dir / _SNAPSHOT_ROOT / f"date={as_of}" / "part.json"


def _default_results(as_of: str = _AS_OF) -> dict:
    return {
        "auction_bullish": {
            "total": 2,
            "as_of": as_of,
            "rows": [
                {"symbol": "600000.SH", "name": "人工智能龙头", "open_gap": 3.21,
                 "change_pct": 5.1, "hit_factors": ["竞价多头"]},
                {"symbol": "600001.SH", "name": "宁德新能源", "open_gap": 1.5,
                 "change_pct": 2.3, "hit_factors": ["盘前强势量化", "竞价多头"]},
            ],
        },
        "auction_early_star": {
            "total": 1,
            "as_of": as_of,
            "rows": [
                {"symbol": "600003.SH", "name": "早盘之星科技", "open_gap": 0.1,
                 "change_pct": 0.9, "hit_factors": ["早盘之星"]},
            ],
        },
    }


def _write_snapshot_payload(
    data_dir: Path,
    as_of: str = _AS_OF,
    results: dict | None = None,
    strategy_version: str = "v-test",
    computed_at: str = "2026-08-04T15:30:00",
) -> Path:
    """直接写一个合法 part.json (供读路径测试)。"""
    payload = {
        "as_of": as_of,
        "computed_at": computed_at,
        "strategy_version": strategy_version,
        "snapshot_type": "point",
        "schema_version": 1,
        "results": results if results is not None else _default_results(as_of),
    }
    path = _snapshot_path(data_dir, as_of)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _canned_results(as_of: str = _AS_OF) -> dict:
    return {
        "strat_a": {
            "total": 2,
            "as_of": as_of,
            "rows": [
                {"symbol": "000001", "name": "平安银行", "close": 10.0,
                 "change_pct": 0.05, "hit_factors": ["策略Alpha", "策略Beta"]},
                {"symbol": "600000", "name": "浦发银行", "close": 11.0,
                 "change_pct": 0.03, "hit_factors": ["策略Alpha"]},
            ],
        },
        "strat_b": {
            "total": 1,
            "as_of": as_of,
            "rows": [
                {"symbol": "000001", "name": "平安银行", "close": 10.0,
                 "change_pct": 0.05, "hit_factors": ["策略Alpha", "策略Beta"]},
            ],
        },
    }


def _write_canned_strategy(d: Path, sid: str, name: str, min_change: float) -> None:
    """写入一个自包含的 canned builtin 策略文件 (无外部依赖)。"""
    (d / f"{sid}.py").write_text(
        f'''"""canned {sid} for pool_snapshot regression (hermetic)."""
import polars as pl

META = {{
    "id": "{sid}",
    "name": "{name}",
    "description": "canned",
    "tags": [],
    "params": [],
    "scoring": {{}},
    "order_by": "change_pct",
    "descending": True,
    "limit": 100,
}}

BASIC_FILTER = {{"enabled": False}}


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return pl.col("change_pct") > {min_change}
''',
        encoding="utf-8",
    )


class _FakeRepo:
    """最小 repo 桩 (与 test_factor_hits 同型)。"""

    def __init__(self, data_dir, enriched, latest, instruments=None):
        self.store = SimpleNamespace(data_dir=data_dir)
        self._enriched = enriched
        self._latest = latest
        self._instruments = instruments if instruments is not None else pl.DataFrame()

    def get_enriched_latest_asset(self, asset_type):
        return self._enriched, self._latest

    def get_instruments_asset(self, asset_type):
        return self._instruments

    def get_enriched_history(self, target_date, lookback_days):
        return None


# ================================================================
# Task 1 — 点快照服务 (POOL-04)
# ================================================================


def test_snapshot_roundtrip_no_ever_rows(tmp_path):
    """POOL-04 铁律: part.json 精确含元数据 + 当次 results, 绝无 union 键; round-trip 精确。"""
    from app.services.pool_snapshot import load_point_snapshot, persist_point_snapshot

    results = _canned_results()
    path = persist_point_snapshot(
        tmp_path, _AS_OF, results,
        strategy_version="fp123", computed_at="2026-08-04T15:30:00",
    )
    assert path == _snapshot_path(tmp_path, _AS_OF)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload) == {
        "as_of", "computed_at", "strategy_version",
        "snapshot_type", "schema_version", "results",
    }
    assert "today_ever_rows" not in payload
    assert "today_ever_matched" not in payload
    assert payload["as_of"] == _AS_OF
    assert payload["computed_at"] == "2026-08-04T15:30:00"
    assert payload["strategy_version"] == "fp123"
    assert payload["snapshot_type"] == "point"
    assert payload["schema_version"] == 1

    loaded = load_point_snapshot(tmp_path, _AS_OF)
    assert loaded is not None
    assert loaded["results"] == results


def test_snapshot_atomic_and_idempotent(tmp_path):
    """原子写无 .tmp 残留; 同 as_of 二次 persist 幂等覆盖为最新内容。"""
    from app.services.pool_snapshot import load_point_snapshot, persist_point_snapshot

    first = _canned_results()
    persist_point_snapshot(tmp_path, _AS_OF, first, strategy_version="v1",
                           computed_at="2026-08-04T10:00:00")
    part_dir = tmp_path / _SNAPSHOT_ROOT / f"date={_AS_OF}"
    assert list(part_dir.glob("*.tmp")) == []

    second = {
        "strat_a": {
            "total": 1, "as_of": _AS_OF,
            "rows": [{"symbol": "600000", "name": "浦发银行", "change_pct": 0.03}],
        }
    }
    persist_point_snapshot(tmp_path, _AS_OF, second, strategy_version="v2",
                           computed_at="2026-08-04T15:30:00")
    loaded = load_point_snapshot(tmp_path, _AS_OF)
    assert loaded["results"] == second
    assert loaded["strategy_version"] == "v2"
    assert list(part_dir.glob("*.tmp")) == []


def test_snapshot_preserves_empty_strategy(tmp_path):
    """Pitfall 2: total=0 空策略 round-trip 后仍存在 (卡片不消失)。"""
    from app.services.pool_snapshot import load_point_snapshot, persist_point_snapshot

    results = {
        "strat_empty": {"total": 0, "as_of": _AS_OF, "rows": []},
        "strat_nonempty": {
            "total": 1, "as_of": _AS_OF,
            "rows": [{"symbol": "000001", "name": "平安银行", "change_pct": 0.05}],
        },
    }
    persist_point_snapshot(tmp_path, _AS_OF, results, strategy_version="v1",
                           computed_at="2026-08-04T15:30:00")
    loaded = load_point_snapshot(tmp_path, _AS_OF)
    assert "strat_empty" in loaded["results"]
    assert loaded["results"]["strat_empty"]["total"] == 0
    assert loaded["results"]["strat_empty"]["rows"] == []
    assert loaded["results"]["strat_nonempty"]["total"] == 1


def test_strategy_fingerprint_stability_and_sensitivity(tmp_path):
    """指纹: 同 engine 两次稳定; 源码字节变化 / meta 声明变化 → 指纹变化。"""
    from app.services.pool_snapshot import strategy_fingerprint
    from app.strategy.engine import StrategyEngine

    strat_dir = tmp_path / "strategies"
    strat_dir.mkdir()
    _write_canned_strategy(strat_dir, "strat_a", "策略Alpha", 0.02)
    engine = StrategyEngine(
        enriched_loader=lambda _d: pl.DataFrame(), strategy_dirs=[strat_dir]
    )

    fp1 = strategy_fingerprint(engine)
    fp2 = strategy_fingerprint(engine)
    assert fp1 == fp2

    src = strat_dir / "strat_a.py"
    original = src.read_text(encoding="utf-8")

    # 源码内容变化 → 指纹变化
    src.write_text(original + "\n# source touch\n", encoding="utf-8")
    engine.reload()
    fp_source = strategy_fingerprint(engine)
    assert fp_source != fp1

    # meta 声明变化 (恢复源码字节, 只改 name) → 指纹变化
    src.write_text(original.replace('"name": "策略Alpha"', '"name": "策略阿尔法"'),
                   encoding="utf-8")
    engine.reload()
    fp_meta = strategy_fingerprint(engine)
    assert fp_meta != fp1
    assert fp_meta != fp_source


def test_list_snapshot_dates_sorted_desc_and_filters(tmp_path):
    """日期列表: ISO desc; 无 part.json 的 date=* 目录排除; root 不存在 → []。"""
    from app.services.pool_snapshot import list_snapshot_dates

    _write_snapshot_payload(tmp_path, as_of="2026-08-04")
    _write_snapshot_payload(tmp_path, as_of="2026-08-01")
    (tmp_path / _SNAPSHOT_ROOT / "date=2026-08-02").mkdir(parents=True)

    assert list_snapshot_dates(tmp_path) == ["2026-08-04", "2026-08-01"]

    shutil.rmtree(tmp_path / _SNAPSHOT_ROOT)
    assert list_snapshot_dates(tmp_path) == []


def test_persist_rejects_invalid_as_of(tmp_path):
    """as_of 严格校验 (防路径穿越): 非法 → persist ValueError, load 返回 None。"""
    from app.services.pool_snapshot import load_point_snapshot, persist_point_snapshot

    results = _canned_results()
    for bad in ("2026-8-4", "../x", "2026-08-4", ""):
        with pytest.raises(ValueError):
            persist_point_snapshot(tmp_path, bad, results, strategy_version="v1",
                                   computed_at="2026-08-04T15:30:00")
        assert load_point_snapshot(tmp_path, bad) is None
    # 日历非法但 regex 通过 (2026-13-01): persist 只做格式校验 (regex), 日历校验在
    # API 层 date.fromisoformat; load 在文件不存在时返回 None。
    assert load_point_snapshot(tmp_path, "2026-13-01") is None
    assert load_point_snapshot(tmp_path, None) is None  # type: ignore[arg-type]


# ================================================================
# Task 4 — run_all 落快照钩子 + 共享核心 (POOL-04 调用点 1)
# ================================================================


def _run_all_app(tmp_path, strat_ids, as_of=date(2026, 8, 4)):
    """最小 FastAPI + canned 策略装配, 返回 (client, resp, engine)。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import screener as screener_api
    from app.strategy.engine import StrategyEngine

    strat_dir = tmp_path / "strategies"
    strat_dir.mkdir()
    _write_canned_strategy(strat_dir, "strat_a", "策略Alpha", 0.02)

    enriched = pl.DataFrame(
        {
            "symbol": ["000001", "600000", "000002", "300001"],
            "name": ["平安银行", "浦发银行", "万科A", "创业板票"],
            "date": [as_of] * 4,
            "close": [10.0, 11.0, 12.0, 13.0],
            "prev_close": [9.5, 10.6, 11.8, 12.9],
            "change_pct": [0.05, 0.03, 0.012, 0.005],
            "amount": [5e8, 6e8, 7e8, 8e8],
        }
    )
    instruments = pl.DataFrame(
        {
            "symbol": ["000001", "600000", "000002", "300001"],
            "name": ["平安银行", "浦发银行", "万科A", "创业板票"],
        }
    )
    engine = StrategyEngine(
        enriched_loader=lambda _d: pl.DataFrame(), strategy_dirs=[strat_dir]
    )
    repo = _FakeRepo(tmp_path, enriched, as_of, instruments)

    app = FastAPI()
    app.include_router(screener_api.router)
    app.state.repo = repo
    app.state.strategy_engine = engine

    client = TestClient(app)
    resp = client.post(
        "/api/screener/run_all",
        json={"as_of": "2026-08-04", "strategy_ids": strat_ids},
    )
    return client, resp, engine


def test_run_all_persists_point_snapshot(tmp_path):
    """POOL-04 调用点 1: run_all 后 part.json 存在, 含 point 元数据, 无 union 键。"""
    from app.services.pool_snapshot import load_point_snapshot

    client, resp, engine = _run_all_app(tmp_path, ["strat_a"])
    assert resp.status_code == 200

    snap = load_point_snapshot(tmp_path, "2026-08-04")
    assert snap is not None
    assert snap["snapshot_type"] == "point"
    assert snap["schema_version"] == 1
    assert isinstance(snap["strategy_version"], str) and len(snap["strategy_version"]) == 16
    assert snap["computed_at"]
    assert "today_ever_rows" not in snap
    assert "today_ever_matched" not in snap
    assert "strat_a" in snap["results"]
    assert all("hit_factors" in r for r in snap["results"]["strat_a"]["rows"])


def test_run_all_with_hits_shared_core_shape(tmp_path):
    """共享核心: run_all_with_hits 返回与路由同形 results dict (含 hit_factors)。"""
    from app.services.screener import ScreenerService

    client, resp, engine = _run_all_app(tmp_path, ["strat_a"])
    assert resp.status_code == 200

    repo = client.app.state.repo
    results = ScreenerService(repo).run_all_with_hits(
        date(2026, 8, 4), ["strat_a"], engine=engine
    )
    assert "strat_a" in results
    assert results["strat_a"]["total"] == 2
    assert results["strat_a"]["as_of"] == "2026-08-04"
    for r in results["strat_a"]["rows"]:
        assert "hit_factors" in r
