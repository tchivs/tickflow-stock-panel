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
