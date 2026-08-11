"""36-01 FA-01/02/03 + FA-06 回归套件 — 超时豁免 / only-missing / 全量 CLI / EOD 幂等。

Hermetic, 不碰真实数据目录/网络。镜像 test_auction_backfill_honesty.py 的
fixture 形态 (fake provider / _make_env 式 tmp 湖 / 双面 _patch_probe +
_patch_provider + _patch_pacing / 模块对象 monkeypatch, 绝不用 string target);
独立文件, 不 import 32-02 测试模块 (诚实套件约定)。

覆盖 (测试名嵌 token, 供 ``-k`` 过滤):
- timeout/reap (FA-01): create(timeout_s) 内存+磁盘持久化; reap_stale per-job
  优先 (21600 越过 600s 顶 / 缺省仍 600 回收 / 低于缺省的 per-job 也回收);
  API 传 timeout_s=21600。
- only_missing (FA-02): 覆盖预扫描跳过已全覆盖 (requested=0, 零 provider 调用);
  部分残差整窗重拉 merge-upsert 补齐; API body 校验 + 透传; _covered_symbols
  DuckDB 分支在真实湖上验证 (W3: 形状感知 fake db 让 COUNT(*) 分支真被执行)。
- cli (FA-03): hermetic 终态 JSON (8 键) + 退出码 0/1; --help 六旗标; AST
  守卫 (源码零 job 注册表 import/引用)。
- eod (FA-06): 已覆盖 symbol 经同一写缝重写 = 幂等 no-op crop (三层: seam /
  service / EOD 路径), 湖行数不变, 无 .tmp 残留。
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest

# 成功路径终态键集 (W-5): 8 键 set 相等仅限成功路径; fail-closed 另加 "reason" (9 键)。
_SUCCESS_KEYS = {
    "requested", "backfilled_symbols", "rows", "dates", "failed",
    "failed_symbols", "origin", "rpm",
}

# ================================================================
# hermetic fixtures (镜像 test_auction_backfill_honesty.py, 独立文件)
# ================================================================


class _FakeAuctionProvider:
    """逐 symbol 假 provider: rows_by_symbol / exc_by_symbol 注入, calls 记录调用。

    get_auction 兼容两种契约: 回填 1 码/请求 (start_date, end_date) 与 EOD 多码
    (trade_date); 多 symbol 时 concat 各行帧 (与诚实套件单码行为超集一致)。
    """

    name = "fake_auction"

    def __init__(self, rows_by_symbol=None, exc_by_symbol=None):
        self.rows_by_symbol = rows_by_symbol or {}
        self.exc_by_symbol = exc_by_symbol or {}
        self.calls: list[tuple[list[str], object, object]] = []

    def get_auction(self, symbols, start_date=None, end_date=None):
        self.calls.append((list(symbols), start_date, end_date))
        frames = []
        for sym in symbols:
            if sym in self.exc_by_symbol:
                raise self.exc_by_symbol[sym]
            df = self.rows_by_symbol.get(sym)
            if df is not None and not df.is_empty():
                frames.append(df)
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames)


class _FakeDb:
    """最小 db 桩, 形状感知 (W3): COUNT(*) 查询返回 (symbol, count) 行 —
    _covered_symbols 的 DuckDB 分支因此被真实执行; 其余查询返回 DISTINCT
    (symbol,) 行 (universe / _has_daily_rows 同形)。"""

    def __init__(self, symbols, covered_counts=None):
        self._symbols = list(symbols)
        self._counts = dict(covered_counts or {})
        self.count_queries = 0

    def execute(self, sql, *args, **kwargs):
        if "COUNT(*)" in sql:
            self.count_queries += 1
            return _FakeCursor([(s, self._counts.get(s, 0)) for s in self._symbols])
        return _FakeCursor([(s,) for s in self._symbols])


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeRepo:
    """最小 repo 桩: store.data_dir (写湖) + 形状感知 db (覆盖扫描/universe)。"""

    def __init__(self, data_dir, symbols, covered_counts=None):
        self.store = SimpleNamespace(data_dir=data_dir)
        self.db = _FakeDb(symbols, covered_counts=covered_counts)


def _symbol_rows(symbol, dates, vp_by_date=None):
    """每日期 09:25:00 一行的 canonical 帧 (555..565 窗口内, 写缝谓词可过)。"""
    vp = vp_by_date or {}
    cols = {
        "symbol": [symbol] * len(dates),
        "datetime": [datetime(d.year, d.month, d.day, 9, 25) for d in dates],
        "auction_volume": [100] * len(dates),
        "auction_amount": [1000] * len(dates),
    }
    if vp_by_date is not None:
        cols["auction_virtual_price"] = [float(vp.get(d, 10.0)) for d in dates]
    return pl.DataFrame(cols)


def _make_env(tmp_path, daily_dates, symbols, opens=None, covered=None):
    """kline_daily/date=* 分区 (symbol/open 列) + _FakeRepo (镜像 pool_backfill._make_env)。

    covered: {symbol: 对齐窗口内行数} —— 形状感知 fake db 的 COUNT(*) 返回 (W3),
    让 only_missing 覆盖扫描的 DuckDB 分支真实执行。
    """
    opens = opens or {}
    for d in daily_dates:
        part_dir = tmp_path / "kline_daily" / f"date={d.isoformat()}"
        part_dir.mkdir(parents=True, exist_ok=True)
        pl.DataFrame({
            "symbol": list(symbols),
            "open": [float(opens.get(d, 10.0))] * len(symbols),
        }).write_parquet(part_dir / "part.parquet")
    return _FakeRepo(tmp_path, symbols, covered_counts=covered)


def _seed_daily(tmp_path, daily_dates, symbols):
    """真实 kline_daily 分区 (含 date 列 —— _has_daily_rows 真实视图查询需要)。"""
    for d in daily_dates:
        part_dir = tmp_path / "kline_daily" / f"date={d.isoformat()}"
        part_dir.mkdir(parents=True, exist_ok=True)
        pl.DataFrame({
            "symbol": list(symbols),
            "date": [d.isoformat()] * len(symbols),
            "open": [10.0] * len(symbols),
            "high": [11.0] * len(symbols),
            "low": [9.0] * len(symbols),
            "close": [10.5] * len(symbols),
            "volume": [1000] * len(symbols),
            "amount": [10500] * len(symbols),
        }).write_parquet(part_dir / "part.parquet")


def _make_real_env(tmp_path, daily_dates, symbols):
    """真实 DataStore/KlineRepository (CLI 测试 / DuckDB 视图路径 / EOD 三层)。"""
    from app.tickflow.repository import DataStore, KlineRepository

    _seed_daily(tmp_path, daily_dates, symbols)
    store = DataStore(tmp_path)
    repo = KlineRepository(store)
    return repo, store


def _seed_lake(tmp_path, symbol, dates):
    """把 canonical auction 行按日分区预置进 kline_auction 湖 (覆盖状态预置)。"""
    df = _symbol_rows(symbol, dates)
    for d in dates:
        out = tmp_path / "kline_auction" / f"date={d.isoformat()}" / "part.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        day_df = df.filter(pl.col("datetime").dt.date() == d)
        if out.exists():
            day_df = pl.concat([pl.read_parquet(out), day_df])
        day_df = day_df.sort("symbol", "datetime")
        day_df.write_parquet(out)


def _lake_rows(tmp_path, symbol, d) -> pl.DataFrame:
    out = tmp_path / "kline_auction" / f"date={d.isoformat()}" / "part.parquet"
    if not out.exists():
        return pl.DataFrame()
    return pl.read_parquet(out).filter(pl.col("symbol") == symbol)


def _lake_total(tmp_path) -> int:
    """kline_auction 湖全行数 (幂等性断言基准)。"""
    base = tmp_path / "kline_auction"
    if not base.exists():
        return 0
    return sum(pl.read_parquet(p).height for p in base.glob("date=*/*.parquet"))


def _available_verdict():
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
    return AuctionProbeVerdict(
        status=AuctionProbeStatus.available, source="fake", probed_at=None, detail="fake",
    )


def _fail_closed_verdict():
    from app.services.auction_probe import AuctionProbeStatus, AuctionProbeVerdict
    return AuctionProbeVerdict(
        status=AuctionProbeStatus.fail_closed, source="fake", probed_at=None, detail="fake",
    )


def _patch_probe(monkeypatch, verdict) -> None:
    """resolve_auction_probe 钉死 (源模块 + 消费模块双面 patch, 覆盖全部 import 形态)。"""
    from app.services import auction_backfill, auction_sync
    from app.services import auction_probe as _probe_mod
    monkeypatch.setattr(_probe_mod, "resolve_auction_probe", lambda: verdict)
    monkeypatch.setattr(auction_sync, "resolve_auction_probe", lambda: verdict)
    if hasattr(auction_backfill, "resolve_auction_probe"):
        monkeypatch.setattr(auction_backfill, "resolve_auction_probe", lambda: verdict)


def _patch_provider(monkeypatch, provider) -> None:
    """_first_auction_provider 钉死 (服务 + 源模块双面 patch)。"""
    from app.services import auction_backfill, auction_sync
    monkeypatch.setattr(auction_sync, "_first_auction_provider", lambda: provider)
    if hasattr(auction_backfill, "_first_auction_provider"):
        monkeypatch.setattr(auction_backfill, "_first_auction_provider", lambda: provider)


def _patch_pacing(monkeypatch) -> None:
    """中性化 rpm 限速 (模块级 patch: rate_limits._reserve_slot + 服务绑定)。"""
    from app.tickflow import rate_limits
    monkeypatch.setattr(rate_limits, "_reserve_slot", lambda *a, **k: 0.0)
    from app.services import auction_backfill
    if hasattr(auction_backfill, "sleep_between_batches"):
        monkeypatch.setattr(auction_backfill, "sleep_between_batches", lambda *a, **k: None)


def _run_job(monkeypatch, tmp_path, daily_dates, symbols, provider, opens=None,
             covered=None, **kwargs):
    """拼装环境 + patch probe/provider/pacing, 调 run_auction_backfill。"""
    from app.services import auction_backfill

    repo = _make_env(tmp_path, daily_dates, symbols, opens=opens, covered=covered)
    _patch_probe(monkeypatch, _available_verdict())
    _patch_provider(monkeypatch, provider)
    _patch_pacing(monkeypatch)
    term = auction_backfill.run_auction_backfill(repo, symbols=list(symbols), **kwargs)
    return term, repo


# ================================================================
# FA-01 — timeout (job_store 持久化 + API 21600)
# ================================================================


def test_full_backfill_job_store_timeout_s_persisted(tmp_path):
    """FA-01: create(timeout_s=21600) → get()["timeout_s"] == 21600; succeed 后
    磁盘 JSON 仍含 timeout_s; create() 无参 → 键缺省 (600s fallback 语义)。"""
    from app.services.pipeline_jobs import JobStore

    store = JobStore(store_dir=tmp_path)
    job_id, is_new = store.create(timeout_s=21600)
    assert is_new
    assert store.get(job_id)["timeout_s"] == 21600

    store.start(job_id)
    store.succeed(job_id, {"ok": True})
    on_disk = json.loads((tmp_path / f"{job_id}.json").read_text(encoding="utf-8"))
    assert on_disk["timeout_s"] == 21600, "succeed 整 dict 落盘, timeout_s 须随盘保留"
    assert store.get(job_id)["timeout_s"] == 21600

    job_id2, _ = store.create()
    assert "timeout_s" not in store.get(job_id2), "无参 create 不得写 timeout_s 键"


def test_full_backfill_api_passes_timeout_21600(tmp_path, monkeypatch):
    """FA-01: POST /api/kline/auction/backfill → job 记录 timeout_s == 21600。"""
    from app.services import auction_backfill as auction_backfill_mod

    monkeypatch.setattr(
        auction_backfill_mod, "run_auction_backfill",
        lambda repo, **kwargs: _terminal_result(),
    )
    app, client = _make_auction_app(tmp_path)
    with client:
        resp = client.post("/api/kline/auction/backfill", json={})
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]
        j = _wait_job_terminal(job_id)
        assert j is not None and j["status"] == "succeeded"
        assert j["timeout_s"] == 21600


# ================================================================
# FA-01 — reap (per-job 优先 / 缺省 600 / 低于缺省)
# ================================================================


def _backdate(store, job_id, seconds):
    """把 started_at 回拨 fixed offset (确定性, 无 flaky timing)。

    与 start() 文档契约同形: naive UTC + "Z" (reap_stale 按 "…Z" 解析)。
    """
    naive = (datetime.now(UTC) - timedelta(seconds=seconds)).replace(tzinfo=None)
    store._active_jobs[job_id]["started_at"] = naive.isoformat(timespec="seconds") + "Z"


def test_full_backfill_reap_stale_honors_per_job_timeout(tmp_path):
    """FA-01 回归: timeout_s=21600 的 job 运行 601s (> 600s 旧顶) 不被回收。"""
    from app.services.pipeline_jobs import JobStore

    store = JobStore(store_dir=tmp_path)
    job_id, _ = store.create(timeout_s=21600)
    store.start(job_id)
    _backdate(store, job_id, 601)
    store.reap_stale()
    assert store.get(job_id)["status"] == "running", "21600 豁免, 越过旧 600s 自愈顶"


def test_full_backfill_reap_stale_default_600_still_reaps(tmp_path):
    """缺省语义不变: 无 timeout_s 键的 job 运行 601s → 仍按 600s 回收为 failed。"""
    from app.services.pipeline_jobs import JobStore

    store = JobStore(store_dir=tmp_path)
    job_id, _ = store.create()
    store.start(job_id)
    _backdate(store, job_id, 601)
    store.reap_stale()
    assert store.get(job_id)["status"] == "failed"


def test_full_backfill_reap_stale_honors_lower_custom_timeout(tmp_path):
    """per-job 值低于缺省也生效: timeout_s=100, 运行 150s → 回收。"""
    from app.services.pipeline_jobs import JobStore

    store = JobStore(store_dir=tmp_path)
    job_id, _ = store.create(timeout_s=100)
    store.start(job_id)
    _backdate(store, job_id, 150)
    store.reap_stale()
    assert store.get(job_id)["status"] == "failed"


# ================================================================
# PM-01 回归 — label 去重 (同槽位并行写面不相交 job, 互不挤占)
# ================================================================


def test_job_store_create_label_dedup_per_label(tmp_path):
    """label 去重: 同 label 复用; 不同 label 并行互不挤占; label 不污染全局单飞。"""
    from app.services.pipeline_jobs import JobStore

    store = JobStore(store_dir=tmp_path)

    # 同 label: 复用活跃任务 (is_new=False, 同一 job_id)
    pm1, is_new = store.create(label="premarket_pool_preview")
    assert is_new
    pm2, is_new = store.create(label="premarket_pool_preview")
    assert not is_new and pm2 == pm1

    # 不同 label / 全局: 并行创建, 互不挤占
    sc1, is_new = store.create(label="auction_sidecar_capture")
    assert is_new and sc1 != pm1
    glob1, is_new = store.create()
    assert is_new and glob1 not in (pm1, sc1)

    # label 任务不写 _active_id: 全局单飞指针仍指向最后全局 job
    assert store.active_id() == glob1

    # 全局单飞去重仍生效 (同全局 active 复用)
    glob2, is_new = store.create()
    assert not is_new and glob2 == glob1


def test_job_store_label_job_terminal_clears_label_active(tmp_path):
    """同 label 任务结束后可再建 (succeed 整 dict 落盘, label 键随盘保留)。"""
    import json as _json

    from app.services.pipeline_jobs import JobStore

    store = JobStore(store_dir=tmp_path)
    pm, _ = store.create(label="premarket_pool_preview")
    store.start(pm)
    store.succeed(pm, {"as_of": "2026-08-10"})

    on_disk = _json.loads((tmp_path / f"{pm}.json").read_text(encoding="utf-8"))
    assert on_disk["label"] == "premarket_pool_preview", "label 随磁盘 round-trip 保留"

    pm2, is_new = store.create(label="premarket_pool_preview")
    assert is_new and pm2 != pm, "完成后的同 label 可再建"


def test_job_store_reap_stale_covers_labeled_jobs(tmp_path):
    """label 并行 job 卡死同样能被 reap_stale 自愈 (不重启进程不阻塞同 label 去重)。"""
    from app.services.pipeline_jobs import JobStore

    store = JobStore(store_dir=tmp_path)
    pm, _ = store.create(label="premarket_pool_preview")
    store.start(pm)
    _backdate(store, pm, 601)
    store.reap_stale()
    assert store.get(pm)["status"] == "failed"


# ================================================================
# FA-02 — only_missing (覆盖预扫描 / 部分残差 / API 参数)
# ================================================================


def test_full_backfill_only_missing_skips_fully_covered(tmp_path, monkeypatch):
    """FA-02: 全部已覆盖 → requested=0 8 键成功终态, provider 零调用, 湖不变。"""
    d1, d2, d3 = date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)
    symbols = ["A", "B"]
    fake = _FakeAuctionProvider(rows_by_symbol={
        "A": _symbol_rows("A", [d1, d2, d3]),
        "B": _symbol_rows("B", [d1, d2, d3]),
    })

    # 第一遍: 全量写 (无 only_missing)
    term1, _ = _run_job(monkeypatch, tmp_path, [d1, d2, d3], symbols, fake, rpm=10)
    assert term1["backfilled_symbols"] == 2
    assert _lake_total(tmp_path) == 6
    calls_after_first = len(fake.calls)  # 预检 A + 循环 A/B

    # 第二遍: only_missing=True, 两 symbol 均已全覆盖
    repo2 = _make_env(tmp_path, [d1, d2, d3], symbols, covered={"A": 3, "B": 3})
    _patch_probe(monkeypatch, _available_verdict())
    _patch_provider(monkeypatch, fake)
    _patch_pacing(monkeypatch)
    from app.services import auction_backfill
    term2 = auction_backfill.run_auction_backfill(
        repo2, symbols=list(symbols), rpm=10, only_missing=True,
    )
    assert term2 == {
        "requested": 0, "backfilled_symbols": 0, "rows": 0, "dates": 3,
        "failed": 0, "failed_symbols": [], "origin": "backfill", "rpm": 10,
    }
    assert len(fake.calls) == calls_after_first, "全跳过不得有任何 provider 调用 (无预检无循环)"
    assert repo2.db.count_queries == 1, "W3: COUNT(*) 分支须被真实执行"
    assert _lake_total(tmp_path) == 6, "湖行数不变"


def test_full_backfill_only_missing_refetches_partial_residue(tmp_path, monkeypatch):
    """FA-02: 部分覆盖残差整窗重拉 → merge-upsert 补齐; 已全覆盖兄弟跳过。"""
    d1, d2, d3 = date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)
    symbols = ["A", "B", "C"]
    # 预置湖: A 全覆盖 (3 日), B 部分 (2 日), C 空
    _seed_lake(tmp_path, "A", [d1, d2, d3])
    _seed_lake(tmp_path, "B", [d1, d2])
    fake = _FakeAuctionProvider(rows_by_symbol={
        "B": _symbol_rows("B", [d1, d2, d3]),
        "C": _symbol_rows("C", [d1, d2, d3]),
    })
    term, repo = _run_job(
        monkeypatch, tmp_path, [d1, d2, d3], symbols, fake, rpm=10,
        covered={"A": 3, "B": 2, "C": 0}, only_missing=True,
    )
    assert term["requested"] == 2, "分母为过滤后列表 (B, C)"
    assert term["backfilled_symbols"] == 2
    assert term["rows"] == 6
    assert term["failed"] == 0
    assert all("A" not in c[0] for c in fake.calls), "已全覆盖 A 不得被请求 (预检在过滤后)"
    assert repo.db.count_queries == 1, "W3: COUNT(*) 分支须被真实执行"
    # 湖终态: 每 symbol 每日期恰 1 行 (B 残差被 merge-upsert 补齐)
    assert _lake_total(tmp_path) == 9
    for s in symbols:
        for d in (d1, d2, d3):
            assert _lake_rows(tmp_path, s, d).height == 1, f"{s}@{d} 应恰 1 行"


def test_full_backfill_only_missing_api_param_accepted(tmp_path, monkeypatch):
    """FA-02 API: only_missing=true 透传; "yes" → 400; 缺省 → False。"""
    from app.services import auction_backfill as auction_backfill_mod

    captured: dict = {}

    def fake_run(repo, **kwargs):
        captured.clear()
        captured.update(kwargs)
        return _terminal_result()

    monkeypatch.setattr(auction_backfill_mod, "run_auction_backfill", fake_run)
    app, client = _make_auction_app(tmp_path)
    with client:
        resp = client.post(
            "/api/kline/auction/backfill",
            json={"symbols": ["000001.SZ"], "only_missing": True},
        )
        assert resp.status_code == 200
        j = _wait_job_terminal(resp.json()["job_id"])
        assert j is not None and j["status"] == "succeeded"
        assert captured["only_missing"] is True

        resp = client.post(
            "/api/kline/auction/backfill",
            json={"symbols": ["000001.SZ"], "only_missing": "yes"},
        )
        assert resp.status_code == 400, "only_missing 非 bool → 400"

        resp = client.post(
            "/api/kline/auction/backfill", json={"symbols": ["000001.SZ"]},
        )
        assert resp.status_code == 200
        j = _wait_job_terminal(resp.json()["job_id"])
        assert j is not None and j["status"] == "succeeded"
        assert captured["only_missing"] is False


def test_full_backfill_only_missing_covered_duckdb_happy_path(tmp_path):
    """W3/T4: _covered_symbols 在真实 kline_auction 湖上走 DuckDB 视图分支;
    空湖 → 空集 (视图无 parquet → 异常 → 兜底扫描无文件 → 空)。"""
    from app.services.auction_backfill import _covered_symbols
    from app.tickflow.repository import DataStore, KlineRepository

    d1, d2, d3 = date(2026, 8, 3), date(2026, 8, 4), date(2026, 8, 5)
    _seed_lake(tmp_path, "A", [d1, d2, d3])
    _seed_lake(tmp_path, "B", [d1, d2])
    store = DataStore(tmp_path)
    repo = KlineRepository(store)
    try:
        aligned = {d1, d2, d3}
        covered = _covered_symbols(repo, tmp_path, aligned, "2026-08-03", "2026-08-05")
        assert covered == {"A"}, f"恰全覆盖 A, got {covered}"

        empty_store = DataStore(tmp_path / "empty")
        empty_repo = KlineRepository(empty_store)
        try:
            assert _covered_symbols(
                empty_repo, tmp_path / "empty", aligned, "2026-08-03", "2026-08-05",
            ) == set(), "空湖 → 空覆盖集"
        finally:
            empty_store.db.close()
    finally:
        store.db.close()


# ================================================================
# FA-03 — CLI (hermetic JSON / help / AST 守卫)
# ================================================================


def _load_cli():
    import importlib.util

    backend = Path(__file__).resolve().parents[1]
    cli_path = backend / "scripts" / "auction_backfill.py"
    spec = importlib.util.spec_from_file_location("auction_backfill_cli", cli_path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli


def test_full_backfill_cli_writes_terminal_json(tmp_path, monkeypatch):
    """FA-03: DATA_DIR=tmp hermetic 跑 → exit 0, --out JSON 为 8 键终态 dict。"""
    d1 = date(2026, 8, 3)
    _seed_daily(tmp_path, [d1], ["000001.SZ"])
    fake = _FakeAuctionProvider(
        rows_by_symbol={"000001.SZ": _symbol_rows("000001.SZ", [d1])},
    )
    _patch_probe(monkeypatch, _available_verdict())
    _patch_provider(monkeypatch, fake)
    _patch_pacing(monkeypatch)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    cli = _load_cli()
    out = tmp_path / "ledger.json"
    rc = cli.main(["--symbols", "000001.SZ", "--rpm", "10", "--out", str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert set(data) == _SUCCESS_KEYS, f"终态键集漂移: {sorted(data)}"
    assert data["requested"] == 1 and data["backfilled_symbols"] == 1
    assert data["failed_symbols"] == []
    assert _lake_total(tmp_path) == 1, "CLI 经同一写缝落湖"


def test_full_backfill_cli_fail_closed_exit_1(tmp_path, monkeypatch):
    """FA-03: fail-closed (probe 非 available) → exit 1, JSON 带诚实 reason。"""
    _seed_daily(tmp_path, [date(2026, 8, 3)], ["000001.SZ"])
    _patch_probe(monkeypatch, _fail_closed_verdict())
    _patch_pacing(monkeypatch)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    cli = _load_cli()
    out = tmp_path / "ledger-fail.json"
    rc = cli.main(["--symbols", "000001.SZ", "--rpm", "10", "--out", str(out)])
    assert rc == 1, "fail-closed → exit 1"
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["reason"] == "source_unavailable"
    assert data["requested"] == 0 and data["backfilled_symbols"] == 0
    assert not list((tmp_path / "kline_auction").glob("date=*")), "fail-closed 0 写"


def test_full_backfill_cli_help_lists_flags():
    """FA-03: python scripts/auction_backfill.py --help → exit 0, 六旗标齐全。"""
    backend = Path(__file__).resolve().parents[1]
    cli = backend / "scripts" / "auction_backfill.py"
    proc = subprocess.run(
        [sys.executable, str(cli), "--help"],
        capture_output=True, text=True, cwd=str(backend),
    )
    assert proc.returncode == 0, proc.stderr
    for flag in ("--all", "--symbols", "--only-missing", "--rpm", "--out", "--start", "--end"):
        assert flag in proc.stdout, f"help 缺旗标 {flag}"


def test_full_backfill_cli_no_job_store_import():
    """FA-03 AST 守卫: CLI 源码零任务注册表 import/引用 (镜像 POOL-03 E3 形)。"""
    backend = Path(__file__).resolve().parents[1]
    src = (backend / "scripts" / "auction_backfill.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert "job_store" not in src, "源码出现 job_store 引用"
    assert "pipeline_jobs" not in src, "源码出现 pipeline_jobs 引用"
    assert not any("pipeline_jobs" in n for n in imported), f"import 面: {imported}"


# ================================================================
# FA-06 — EOD 交织 (幂等 no-op crop, 36-03 T1 执行)
# ================================================================


def test_full_backfill_eod_interplay_rewrite_idempotent(tmp_path, monkeypatch):
    """FA-06 三层证明: 已覆盖 symbol 经同一写缝重写 = 幂等 no-op crop (湖行数不变)。

    - seam 级: write_auction_partitions 同帧重调 → 分区行数不变, 无 .tmp;
    - service 级: run_auction_backfill 同数据跑两遍 → 湖总行数不变 (merge-upsert
      crop 而非 append);
    - EOD 路径级: sync_and_persist_auction 对已覆盖 symbol → 返回 > 0 但湖不变;
      混合 (已覆盖 + 新 symbol) → 已覆盖行不变, 新行追加。
    """
    from app.services import auction_backfill
    from app.services.auction_sync import sync_and_persist_auction, write_auction_partitions

    d1, d2 = date(2026, 8, 3), date(2026, 8, 4)
    symbols = ["A", "B"]
    repo, store = _make_real_env(tmp_path, [d1, d2], symbols)
    fake = _FakeAuctionProvider(rows_by_symbol={
        "A": _symbol_rows("A", [d1, d2]),
        "B": _symbol_rows("B", [d1, d2]),
    })
    _patch_probe(monkeypatch, _available_verdict())
    _patch_provider(monkeypatch, fake)
    _patch_pacing(monkeypatch)

    try:
        # ---- service 级: 第一遍写满 ----
        term1 = auction_backfill.run_auction_backfill(repo, symbols=list(symbols), rpm=10)
        assert term1["backfilled_symbols"] == 2
        total1 = _lake_total(tmp_path)
        assert total1 == 4

        # ---- seam 级: 同帧重写 → 行数不变, 无 .tmp ----
        written = write_auction_partitions(_symbol_rows("A", [d1, d2]), repo)
        assert written == 2
        assert _lake_total(tmp_path) == total1
        assert not list((tmp_path / "kline_auction").rglob("*.tmp"))

        # ---- service 级: 同数据跑第二遍 → 湖不变 (crop 非 append) ----
        term2 = auction_backfill.run_auction_backfill(repo, symbols=list(symbols), rpm=10)
        assert term2["rows"] > 0, "重取重写, rows 计写窗内行数"
        assert _lake_total(tmp_path) == total1
        assert not list((tmp_path / "kline_auction").rglob("*.tmp"))

        # ---- EOD 路径级: 已覆盖 symbol 重同步 → 返回 > 0 但湖不变 ----
        n = sync_and_persist_auction(["A"], repo, SimpleNamespace(), d1)
        assert n > 0
        assert _lake_total(tmp_path) == total1

        # 混合: 已覆盖 A + 新 symbol C → A 行不变, C 追加
        fake.rows_by_symbol["C"] = _symbol_rows("C", [d1])
        n2 = sync_and_persist_auction(["A", "C"], repo, SimpleNamespace(), d1)
        assert n2 > 0
        assert _lake_total(tmp_path) == total1 + 1
        assert _lake_rows(tmp_path, "A", d1).height == 1
        assert _lake_rows(tmp_path, "C", d1).height == 1
    finally:
        store.db.close()


# ================================================================
# 端点 helpers (镜像 test_auction_backfill.py:505-547)
# ================================================================


def _terminal_result():
    return {
        "requested": 1, "backfilled_symbols": 1, "rows": 1, "dates": 1,
        "failed": 0, "failed_symbols": [], "origin": "backfill", "rpm": 30,
    }


def _make_auction_app(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import auction_backfill as auction_backfill_api

    app = FastAPI()
    app.include_router(auction_backfill_api.router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    return app, TestClient(app)


def _wait_job_terminal(job_id, timeout=5.0):
    import time as _time

    from app.services.pipeline_jobs import job_store

    deadline = _time.time() + timeout
    j = None
    while _time.time() < deadline:
        j = job_store.get(job_id)
        if j is not None and j["status"] in ("succeeded", "failed"):
            return j
        _time.sleep(0.02)
    return j
