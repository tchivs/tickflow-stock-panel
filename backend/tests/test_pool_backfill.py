"""HIST-01/02 批量回填服务 — 单元测试 (hermetic, 不 import 其他测试模块)。

- 回放: 缺口日逐日 run_all_with_hits → 冻结快照 (origin="backfill"), 升序。
- D2 铁律: 回填**绝不**写 strategy_cache.json (byte-identical 断言锁死)。
- 幂等跳过已快照日; 限界 (max_days/start/end); 合作式取消 (D5); 失败日继续 (HIST-04.3)。

fixture 复用 test_pool_eod_job / test_pool_snapshot 的 _FakeRepo 形 (本文件内自建)。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

_GAP_DATES = ["2026-08-01", "2026-08-02", "2026-08-03"]


def _canned_results(as_of: str) -> dict:
    return {
        "strat_a": {
            "total": 2,
            "as_of": as_of,
            "rows": [
                {"symbol": "000001", "name": "平安银行", "close": 10.0,
                 "change_pct": 0.05, "hit_factors": ["策略Alpha"]},
                {"symbol": "600000", "name": "浦发银行", "close": 11.0,
                 "change_pct": 0.03, "hit_factors": ["策略Alpha"]},
            ],
        },
    }


class _FakeRepo:
    """最小 repo 桩 (与 test_pool_eod_job._FakeRepo 同型, 追加 enriched_latest_date)。"""

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

    def enriched_latest_date(self):
        return self._latest


def _make_env(tmp_path, enriched_dates, snapshot_dates=()):
    """构造 enriched 分区目录 + (可选) 既有快照, 返回 (tmp_path, _FakeRepo)。"""
    for d in enriched_dates:
        (tmp_path / "kline_daily_enriched" / f"date={d}").mkdir(parents=True, exist_ok=True)
    for d in snapshot_dates:
        part = tmp_path / "screener_results" / f"date={d}" / "part.json"
        part.parent.mkdir(parents=True, exist_ok=True)
        part.write_text(json.dumps({"as_of": d, "results": {}}), encoding="utf-8")
    repo = _FakeRepo(tmp_path, pl.DataFrame(), date(2026, 8, 4))
    return repo


def _write_strategy_cache(data_dir, content: bytes) -> Path:
    p = data_dir / "user_data" / "strategy_cache.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


# ================================================================
# HIST-01 回放
# ================================================================


def test_pool_backfill_replays_gaps_ascending(tmp_path, monkeypatch):
    """Test 1: 3 个缺口日全部回填, origin=backfill, 调用顺序升序。"""
    from app.services import pool_snapshot
    from app.services.pool_backfill import run_pool_backfill
    from app.services.screener import ScreenerService

    repo = _make_env(tmp_path, _GAP_DATES)

    seen: list[str] = []

    def fake_run(self, as_of, strategy_ids=None, engine=None):
        seen.append(as_of.isoformat())
        return _canned_results(as_of.isoformat())

    monkeypatch.setattr(ScreenerService, "run_all_with_hits", fake_run)

    result = run_pool_backfill(repo)

    assert result == {
        "requested": 3, "backfilled": 3, "failed": 0,
        "failed_dates": [], "origin": "backfill",
    }
    assert seen == ["2026-08-01", "2026-08-02", "2026-08-03"]  # 升序 (D5)
    for d in _GAP_DATES:
        snap = pool_snapshot.load_point_snapshot(tmp_path, d)
        assert snap is not None
        assert snap["snapshot_origin"] == "backfill"
        assert snap["strategy_version"] == "unknown"  # engine=None → unknown


def test_backfill_never_touches_strategy_cache(tmp_path, monkeypatch):
    """Test 2 (D2 铁律): 回填前后 strategy_cache.json byte-identical; 不存在则不创建。"""
    from app.services.pool_backfill import run_pool_backfill
    from app.services.screener import ScreenerService

    repo = _make_env(tmp_path, _GAP_DATES)
    cache_path = _write_strategy_cache(
        tmp_path, b'{"as_of":"2026-08-04","results":{},"updated_at":123}'
    )
    before = cache_path.read_bytes()

    monkeypatch.setattr(
        ScreenerService, "run_all_with_hits",
        lambda self, as_of, strategy_ids=None, engine=None: _canned_results(as_of.isoformat()),
    )
    result = run_pool_backfill(repo)

    assert result["backfilled"] == 3
    assert cache_path.read_bytes() == before, "回填路径绝不得改写 strategy_cache.json"

    # 不存在 strategy_cache.json 时, 回填也不得创建它
    cache_path.unlink()
    run_pool_backfill(repo)
    assert not cache_path.exists()


def test_pool_backfill_idempotent_skips_existing_snapshots(tmp_path, monkeypatch):
    """Test 3 (幂等): 已快照日跳过; 二次全量跑 requested=0。"""
    from app.services.pool_backfill import run_pool_backfill
    from app.services.screener import ScreenerService

    repo = _make_env(tmp_path, _GAP_DATES, snapshot_dates=("2026-08-02",))

    seen: list[str] = []
    monkeypatch.setattr(
        ScreenerService, "run_all_with_hits",
        lambda self, as_of, strategy_ids=None, engine=None: (
            seen.append(as_of.isoformat()) or _canned_results(as_of.isoformat())
        ),
    )

    result = run_pool_backfill(repo)
    assert result["requested"] == 2
    assert result["backfilled"] == 2
    assert seen == ["2026-08-01", "2026-08-03"]  # 已快照日 08-02 被跳过

    second = run_pool_backfill(repo)
    assert second["requested"] == 0
    assert second["backfilled"] == 0


def test_pool_backfill_bounds(tmp_path, monkeypatch):
    """Test 4 (限界): max_days / start / end 只回填目标子集。"""
    from app.services.pool_backfill import run_pool_backfill
    from app.services.screener import ScreenerService

    all_dates = ["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"]
    monkeypatch.setattr(
        ScreenerService, "run_all_with_hits",
        lambda self, as_of, strategy_ids=None, engine=None: _canned_results(as_of.isoformat()),
    )

    # max_days=2 → 前 2 个缺口日 (升序)
    repo = _make_env(tmp_path / "m1", all_dates)
    r = run_pool_backfill(repo, max_days=2)
    assert r["requested"] == 2
    assert (tmp_path / "m1" / "screener_results" / "date=2026-08-01" / "part.json").exists()
    assert (tmp_path / "m1" / "screener_results" / "date=2026-08-02" / "part.json").exists()
    assert not (tmp_path / "m1" / "screener_results" / "date=2026-08-03" / "part.json").exists()

    # start="2026-08-02" → 只回填 ≥ 该日
    repo = _make_env(tmp_path / "m2", all_dates)
    r = run_pool_backfill(repo, start="2026-08-02")
    assert r["requested"] == 3
    assert (tmp_path / "m2" / "screener_results" / "date=2026-08-01" / "part.json").exists() is False
    assert (tmp_path / "m2" / "screener_results" / "date=2026-08-02" / "part.json").exists()

    # end="2026-08-02" → 只回填 ≤ 该日
    repo = _make_env(tmp_path / "m3", all_dates)
    r = run_pool_backfill(repo, end="2026-08-02")
    assert r["requested"] == 2
    assert (tmp_path / "m3" / "screener_results" / "date=2026-08-02" / "part.json").exists()
    assert not (tmp_path / "m3" / "screener_results" / "date=2026-08-03" / "part.json").exists()


def test_pool_backfill_cooperative_cancel(tmp_path, monkeypatch):
    """Test 5 (D5 合作式取消): job 状态变 failed → 提前停止, 不处理后续日。"""
    from app.services.pool_backfill import run_pool_backfill
    from app.services.pipeline_jobs import job_store
    from app.services.screener import ScreenerService

    dates = ["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05"]
    repo = _make_env(tmp_path, dates)

    seen: list[str] = []
    monkeypatch.setattr(
        ScreenerService, "run_all_with_hits",
        lambda self, as_of, strategy_ids=None, engine=None: (
            seen.append(as_of.isoformat()) or _canned_results(as_of.isoformat())
        ),
    )

    calls = {"n": 0}

    def fake_get(job_id):
        calls["n"] += 1
        if calls["n"] <= 2:  # 前 2 次迭代 job 仍 running
            return {"status": "running"}
        return {"status": "failed"}  # 第 3 次迭代起 job 已 failed

    monkeypatch.setattr(job_store, "get", fake_get)

    result = run_pool_backfill(repo, job_id="job-test")
    assert result["backfilled"] == 2
    assert result["backfilled"] < len(dates)
    assert seen == ["2026-08-01", "2026-08-02"]  # 只处理了前 2 日
    assert not (tmp_path / "screener_results" / "date=2026-08-03" / "part.json").exists()


def test_pool_backfill_failed_days_continue(tmp_path, monkeypatch):
    """Test 6 (失败继续, HIST-04.3): 某日抛异常 → 记 failed_dates, 其余日正常回填。"""
    from app.services.pool_backfill import run_pool_backfill
    from app.services.screener import ScreenerService

    repo = _make_env(tmp_path, _GAP_DATES)

    def fake_run(self, as_of, strategy_ids=None, engine=None):
        if as_of.isoformat() == "2026-08-02":
            raise RuntimeError("boom")
        return _canned_results(as_of.isoformat())

    monkeypatch.setattr(ScreenerService, "run_all_with_hits", fake_run)

    result = run_pool_backfill(repo)
    assert result["requested"] == 3
    assert result["backfilled"] == 2
    assert result["failed"] == 1
    assert result["failed_dates"] == ["2026-08-02"]
    assert (tmp_path / "screener_results" / "date=2026-08-01" / "part.json").exists()
    assert not (tmp_path / "screener_results" / "date=2026-08-02" / "part.json").exists()
    assert (tmp_path / "screener_results" / "date=2026-08-03" / "part.json").exists()


# ================================================================
# Task 3 — POST /api/pipeline/backfill 端点 (D1/D5)
# ================================================================


def _make_backfill_app(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import pipeline as pipeline_api

    app = FastAPI()
    app.include_router(pipeline_api.router)
    app.state.repo = _FakeRepo(tmp_path, pl.DataFrame(), date(2026, 8, 4))
    app.state.strategy_engine = None
    return app, TestClient(app)


def _wait_job_terminal(job_id, timeout=5.0):
    import time

    from app.services.pipeline_jobs import job_store

    deadline = time.time() + timeout
    while time.time() < deadline:
        j = job_store.get(job_id)
        if j is None or j["status"] in ("succeeded", "failed"):
            return j
        time.sleep(0.02)
    return job_store.get(job_id)


def _wait_slot_free(timeout=5.0):
    import time

    from app.services.pipeline_jobs import release_run_slot, try_acquire_run_slot

    deadline = time.time() + timeout
    while time.time() < deadline:
        if try_acquire_run_slot():
            release_run_slot()
            return True
        time.sleep(0.02)
    return False


def test_backfill_endpoint_singleflight_and_reuse(tmp_path, monkeypatch):
    """Test 1 (D1/D5): 首次触发 started, 二次触发复用活跃 job (单飞)。"""
    import threading

    from app.services import pool_backfill as pool_backfill_mod

    app, client = _make_backfill_app(tmp_path)

    release = threading.Event()
    started = threading.Event()

    def fake_run(repo, engine=None, **kwargs):
        started.set()
        release.wait(timeout=5)
        return {"requested": 0, "backfilled": 0, "failed": 0, "failed_dates": [],
                "origin": "backfill"}

    monkeypatch.setattr(pool_backfill_mod, "run_pool_backfill", fake_run)

    with client:
        r1 = client.post("/api/pipeline/backfill", json={"max_days": 2})
        assert r1.status_code == 200
        body1 = r1.json()
        assert body1["status"] == "started"
        job_id = body1["job_id"]
        assert started.wait(timeout=5), "后台任务应已启动"

        r2 = client.post("/api/pipeline/backfill", json={"max_days": 2})
        assert r2.status_code == 200
        assert r2.json() == {"status": "reused", "job_id": job_id}

        release.set()
        j = _wait_job_terminal(job_id)
        assert j is not None and j["status"] == "succeeded"
        assert _wait_slot_free(), "重任务执行槽应已释放"


def test_backfill_endpoint_parameter_validation(tmp_path, monkeypatch):
    """Test 2 (D5/Pitfall 4): 非法/无界参数一律 400 (防路径穿越与失控长任务)。"""
    from app.services import pool_backfill as pool_backfill_mod

    monkeypatch.setattr(
        pool_backfill_mod, "run_pool_backfill",
        lambda repo, engine=None, **kwargs: {"requested": 0, "backfilled": 0,
                                             "failed": 0, "failed_dates": [],
                                             "origin": "backfill"},
    )
    app, client = _make_backfill_app(tmp_path)

    with client:
        for body in (
            {"start": "2026-8-1"},                       # 非 YYYY-MM-DD
            {"end": "08/01/2026"},                      # 非 ISO
            {"start": "2026-08-04", "end": "2026-08-01"},  # start > end
            {"start": "2026-13-01"},                    # 日历非法 (regex 过, ISO 不过)
            {"max_days": 0},
            {"max_days": -1},
            {"max_days": 501},
            {"max_days": "2"},                          # 非 int
            {"max_days": True},                          # bool 不算 int
        ):
            resp = client.post("/api/pipeline/backfill", json=body)
            assert resp.status_code == 400, f"body={body} 应 400, got {resp.status_code}"


def test_backfill_endpoint_runs_in_executor_and_succeeds(tmp_path, monkeypatch):
    """Test 3 (D5): 后台 executor 线程执行 (请求内零阻塞), job_store.succeed 被调。"""
    import threading

    from app.services import pool_backfill as pool_backfill_mod

    app, client = _make_backfill_app(tmp_path)

    thread = {"id": threading.main_thread().ident}
    started = threading.Event()
    release = threading.Event()

    def fake_run(repo, engine=None, **kwargs):
        thread["id"] = threading.get_ident()
        started.set()
        release.wait(timeout=5)
        return {"requested": 1, "backfilled": 1, "failed": 0, "failed_dates": [],
                "origin": "backfill"}

    monkeypatch.setattr(pool_backfill_mod, "run_pool_backfill", fake_run)

    with client:
        resp = client.post("/api/pipeline/backfill", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "started"
        job_id = body["job_id"]
        assert started.wait(timeout=5)
        release.set()
        j = _wait_job_terminal(job_id)
        assert j is not None and j["status"] == "succeeded"
        assert j["result"]["backfilled"] == 1
        assert thread["id"] != threading.main_thread().ident, "回填应在线程池线程执行"
        assert _wait_slot_free()


# ================================================================
# Task 2 — POST /api/pipeline/backfill 端点集成 (PB-01)
# ================================================================


def _make_backfill_pool_app(tmp_path):
    """镜像 _make_backfill_app + pool 双 router (GET /api/pool/dates 缺口断言)。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import pipeline as pipeline_api
    from app.api import pool as pool_api

    app = FastAPI()
    app.include_router(pipeline_api.router)
    app.include_router(pool_api.router)
    app.state.repo = _FakeRepo(tmp_path, pl.DataFrame(), date(2026, 8, 4))
    app.state.strategy_engine = None
    return app, TestClient(app)


def test_backfill_endpoint_subset_bounds_integration(tmp_path, monkeypatch):
    """Test 1 (PB-01): 端点 + executor 路径 + 真 run_pool_backfill, start/end/max_days 组合限界。

    enriched 8 日 (08-01..08-08), POST {start:08-02, end:08-08, max_days:5} → 恰 5 个缺口日
    升序落盘 (08-02..08-06), 全部 origin=backfill + strategy_version=unknown (engine=None),
    08-07/08-08 分区不存在; 终态 6 键精确集。
    """
    from app.services import pool_snapshot
    from app.services.screener import ScreenerService

    dates = [f"2026-08-{d:02d}" for d in range(1, 9)]  # 08-01..08-08
    _make_env(tmp_path, dates)

    seen: list[str] = []
    monkeypatch.setattr(
        ScreenerService, "run_all_with_hits",
        lambda self, as_of, strategy_ids=None, engine=None: (
            seen.append(as_of.isoformat()) or _canned_results(as_of.isoformat())
        ),
    )

    app, client = _make_backfill_app(tmp_path)
    with client:
        resp = client.post(
            "/api/pipeline/backfill",
            json={"start": "2026-08-02", "end": "2026-08-08", "max_days": 5},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "started"
        j = _wait_job_terminal(body["job_id"])
        assert j is not None and j["status"] == "succeeded"
        assert _wait_slot_free()

    # 限界: start 下界 + max_days 前 5 个缺口日, 升序 (D5)
    assert seen == ["2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"]
    for d in ("2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"):
        assert (tmp_path / "screener_results" / f"date={d}" / "part.json").exists()
    for d in ("2026-08-07", "2026-08-08"):
        assert not (tmp_path / "screener_results" / f"date={d}" / "part.json").exists()

    # provenance: origin=backfill + strategy_version=unknown (engine=None 直调语义)
    for d in ("2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"):
        snap = pool_snapshot.load_point_snapshot(tmp_path, d)
        assert snap is not None
        assert snap["snapshot_origin"] == "backfill"
        assert snap["strategy_version"] == "unknown"

    # 终态 6 键精确集
    assert set(j["result"].keys()) == {"requested", "backfilled", "failed",
                                       "failed_dates", "origin"}
    assert j["result"]["requested"] == 5
    assert j["result"]["backfilled"] == 5
    assert j["result"]["failed"] == 0
    assert j["result"]["failed_dates"] == []
    assert j["result"]["origin"] == "backfill"


def test_backfill_endpoint_never_touches_strategy_cache(tmp_path, monkeypatch):
    """Test 2 (D2 铁律上移端点面): 经端点 (executor 路径) 跑子集, cache byte-identical; 不存在则不创建。"""
    from app.services.screener import ScreenerService

    _make_env(tmp_path, _GAP_DATES)
    cache_path = _write_strategy_cache(
        tmp_path, b'{"as_of":"2026-08-04","results":{},"updated_at":123}'
    )
    before = cache_path.read_bytes()

    monkeypatch.setattr(
        ScreenerService, "run_all_with_hits",
        lambda self, as_of, strategy_ids=None, engine=None: _canned_results(as_of.isoformat()),
    )

    app, client = _make_backfill_app(tmp_path)
    with client:
        resp = client.post("/api/pipeline/backfill", json={"max_days": 2})
        assert resp.status_code == 200
        j = _wait_job_terminal(resp.json()["job_id"])
        assert j is not None and j["status"] == "succeeded"
        assert j["result"]["backfilled"] == 2
        assert _wait_slot_free()

    assert cache_path.read_bytes() == before, "端点回填路径绝不得改写 strategy_cache.json"

    # 不存在 strategy_cache.json 时, 端点回填也不得创建它
    cache_path.unlink()
    with client:
        resp = client.post("/api/pipeline/backfill", json={"max_days": 2})
        assert resp.status_code == 200
        j = _wait_job_terminal(resp.json()["job_id"])
        assert j is not None and j["status"] == "succeeded"
        assert _wait_slot_free()
    assert not cache_path.exists()


def test_backfill_endpoint_idempotent_rerun_subset(tmp_path, monkeypatch):
    """Test 3 (PB-01 幂等): 端点二跑同参数 → requested:0; /api/pool/dates 缺口如实递减。"""
    from app.services.screener import ScreenerService

    dates = [f"2026-08-{d:02d}" for d in range(1, 8)]  # 7 日 08-01..08-07
    _make_env(tmp_path, dates)

    monkeypatch.setattr(
        ScreenerService, "run_all_with_hits",
        lambda self, as_of, strategy_ids=None, engine=None: _canned_results(as_of.isoformat()),
    )

    app, client = _make_backfill_pool_app(tmp_path)
    with client:
        # 一跑 max_days=5 → 回填前 5 个缺口日
        resp = client.post("/api/pipeline/backfill", json={"max_days": 5})
        assert resp.status_code == 200
        j1 = _wait_job_terminal(resp.json()["job_id"])
        assert j1 is not None and j1["status"] == "succeeded"
        assert j1["result"]["backfilled"] == 5
        assert _wait_slot_free()

        # 一跑后: /api/pool/dates count==5, backfill_needed==2 (7−5)
        d1 = client.get("/api/pool/dates")
        assert d1.status_code == 200
        assert d1.json()["count"] == 5
        assert d1.json()["backfill_needed"] == 2

        # 二跑同参数 → 缺口差集语义: 只补剩余缺口 (08-06/08-07), 绝不重跑已快照日
        resp2 = client.post("/api/pipeline/backfill", json={"max_days": 5})
        assert resp2.status_code == 200
        j2 = _wait_job_terminal(resp2.json()["job_id"])
        assert j2 is not None and j2["status"] == "succeeded"
        assert j2["result"]["requested"] == 2
        assert j2["result"]["backfilled"] == 2
        assert _wait_slot_free()

        # 三跑同参数 → 全部覆盖, requested:0 (完全幂等)
        resp3 = client.post("/api/pipeline/backfill", json={"max_days": 5})
        assert resp3.status_code == 200
        j3 = _wait_job_terminal(resp3.json()["job_id"])
        assert j3 is not None and j3["status"] == "succeeded"
        assert j3["result"]["requested"] == 0
        assert j3["result"]["backfilled"] == 0
        assert _wait_slot_free()

        # GET /api/pool/dates: 一跑后 count==5, backfill_needed==2 (7−5)
        d = client.get("/api/pool/dates")
        assert d.status_code == 200
        body = d.json()
        assert body["count"] == 7
        assert body["backfill_needed"] == 0


# ================================================================
# Task 3 — 竞价稀疏湖诚实行数 (PB-01, 三态 probe 注入)
# ================================================================

_AUCTION_DATE = date(2026, 8, 5)
_AUCTION_SYMBOLS = ["000001.SZ", "000002.SZ", "600000.SH", "600001.SH", "600002.SH"]


def _write_canned_auction_strategy(d: Path, sid: str, name: str,
                                   requires_auction_data: bool, filter_body: str) -> None:
    """写入自包含 canned 竞价策略 (镜像 test_pool_eod_job._write_canned_strategy 形, META 追加键)。"""
    (d / f"{sid}.py").write_text(
        f'''"""canned {sid} for auction sparse-lake honesty (hermetic)."""
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
    "requires_auction_data": {requires_auction_data},
}}

BASIC_FILTER = {{"enabled": False}}


def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    {filter_body}
''',
        encoding="utf-8",
    )


def _auction_env(tmp_path):
    """稀疏竞价湖环境: 5-symbol enriched 帧 + 仅 2-symbol 的 kline_auction 分区 + canned 策略目录。

    - enriched 帧: 5 symbols (000001.SZ/000002.SZ/600000.SH/600001.SH/600002.SH),
      派生列 change_pct/open_gap 齐; change_pct: 0.05/0.03/0.04/0.01/0.025。
    - kline_auction/date=D/part.parquet: 仅 000001.SZ/000002.SZ 有行 (canonical 列),
      auction_volume 50000/1 → auction_volume_ratio 50.0/0.001 (前 5 日均量 1000)。
    - 返回 (repo, engine, as_of); repo.get_enriched_history 返回前 5 日帧供 ratio 分母。
    """
    from datetime import datetime, timedelta

    from app.strategy.engine import StrategyEngine

    as_of = _AUCTION_DATE
    enriched = pl.DataFrame(
        {
            "symbol": _AUCTION_SYMBOLS,
            "name": ["平安银行", "万科A", "浦发银行", "华夏银行", "民生银行"],
            "date": [as_of] * 5,
            "close": [10.0, 11.0, 12.0, 13.0, 14.0],
            "prev_close": [9.5, 10.6, 11.5, 12.9, 13.7],
            "change_pct": [0.05, 0.03, 0.04, 0.01, 0.025],
            "open_gap": [0.04, 0.02, 0.03, 0.005, 0.015],
        }
    )
    auction_dir = tmp_path / "kline_auction" / f"date={as_of.isoformat()}"
    auction_dir.mkdir(parents=True, exist_ok=True)
    auction = pl.DataFrame(
        {
            "symbol": ["000001.SZ", "000002.SZ"],
            "datetime": [datetime(2026, 8, 5, 9, 20), datetime(2026, 8, 5, 9, 21)],
            "auction_volume": [50000, 1],
            "auction_amount": [5.0e6, 1.0e4],
            "auction_virtual_price": [10.0, 10.5],
        }
    )
    auction.write_parquet(auction_dir / "part.parquet")

    # 前 5 日均量分母 (PIT-safe: 只用 < trade_date 的历史)
    hist = pl.DataFrame(
        {
            "symbol": _AUCTION_SYMBOLS * 5,
            "date": [as_of - timedelta(days=i) for i in range(1, 6)] * len(_AUCTION_SYMBOLS),
            "volume": [1000.0] * (5 * len(_AUCTION_SYMBOLS)),
        }
    )

    repo = _FakeRepo(tmp_path, enriched, as_of)
    repo.get_enriched_history = lambda target_date, lookback_days: hist

    strat_dir = tmp_path / "strategies"
    strat_dir.mkdir()
    _write_canned_auction_strategy(
        strat_dir, "auction_required", "竞价必需", True,
        'return pl.col("auction_volume_ratio") > 0.01',
    )
    _write_canned_auction_strategy(
        strat_dir, "alpha_branch", "竞价分支", False,
        'if "auction_volume_ratio" in df.columns:\n'
        '        return pl.col("auction_volume_ratio") > 0.01\n'
        '    return pl.col("change_pct") > 0.02',
    )
    engine = StrategyEngine(
        enriched_loader=lambda _d: pl.DataFrame(),
        strategy_dirs=[strat_dir],
    )
    return repo, engine, as_of


def test_backfill_auction_sparse_lake_honest_rows(tmp_path, monkeypatch):
    """PB-01 竞价稀疏湖诚实行数 (三态注入, W-3): available → ≤2 symbols; fail_closed/error → 0 行 (引擎短路); alpha 分支列集互斥。"""
    import app.services.auction_columns as auction_columns_mod
    from app.services.auction_probe import AuctionProbeStatus
    from app.services.screener import ScreenerService

    repo, engine, as_of = _auction_env(tmp_path)
    svc = ScreenerService(repo)

    def _probe(status):
        monkeypatch.setattr(
            auction_columns_mod, "resolve_auction_probe",
            lambda: SimpleNamespace(status=status),
        )

    # 态① probe available → 竞价列注入: 000001.SZ ratio=50 过阈值, 000002.SZ ratio=0.001 不过,
    # 其余 3 码竞价列 null (比较恒假) — 稀疏诚实, 绝不产生全市场规模结果
    _probe(AuctionProbeStatus.available)
    res_avail = svc.run_all_with_hits(
        as_of, ["auction_required", "alpha_branch"], engine=engine
    )

    req = res_avail["auction_required"]
    assert req["total"] == 1
    for r in req["rows"]:
        assert r["symbol"] in {"000001.SZ", "000002.SZ"}, "其余 3 码竞价列 null, 不得命中"

    alpha_avail = res_avail["alpha_branch"]
    assert alpha_avail["total"] == 1
    assert {r["symbol"] for r in alpha_avail["rows"]} <= {"000001.SZ", "000002.SZ"}
    assert all("auction_volume_ratio" in r and "auction_amount" in r
               for r in alpha_avail["rows"])

    # 态② probe fail_closed → 列缺席: requires_auction_data 策略 total==0 (引擎短路, 非 0 行伪造)
    _probe(AuctionProbeStatus.fail_closed)
    res_fc = svc.run_all_with_hits(
        as_of, ["auction_required", "alpha_branch"], engine=engine
    )
    assert res_fc["auction_required"]["total"] == 0
    assert res_fc["auction_required"]["rows"] == []

    alpha_fc = res_fc["alpha_branch"]
    assert alpha_fc["total"] == 4  # 派生分支: change_pct>0.02 → 000001/000002/600000.SH/600002.SH
    for r in alpha_fc["rows"]:
        assert "auction_volume_ratio" not in r, "派生分支不得携带竞价列"
        assert "change_pct" in r
        assert r["symbol"] in _AUCTION_SYMBOLS

    # 态③ probe error → 与 fail_closed 同语义 (列缺席, 短路 0 行)
    _probe(AuctionProbeStatus.error)
    res_err = svc.run_all_with_hits(
        as_of, ["auction_required", "alpha_branch"], engine=engine
    )
    assert res_err["auction_required"]["total"] == 0
    assert res_err["alpha_branch"]["total"] == 4

    # 分支列集互斥 (alpha 分支锁): 同一策略 available 下走真列分支, fail_closed 下走派生分支 — 绝不混标
    avail_cols = {k for r in alpha_avail["rows"] for k in r}
    fc_cols = {k for r in alpha_fc["rows"] for k in r}
    assert "auction_volume_ratio" in avail_cols and "auction_amount" in avail_cols
    assert "auction_volume_ratio" not in fc_cols and "auction_amount" not in fc_cols
