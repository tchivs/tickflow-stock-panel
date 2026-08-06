"""R13 pipeline→refresh 配方回归 (LG-01) — 确定性, 零网络, 零调度器; run_now 恒 stub。

锁死 ce5c705/9aa96ed 的 finally 语义: 盘后管道 ``_pipeline_then_refresh`` 无论成功还是
阶段软失败, ``repo.refresh_cache()`` 必在 finally 执行, 已落盘的日K/enriched 刷进内存
缓存; 否则 live_agg 的昨日连板数等基准列停留在旧交易日, 次日开盘连板梯队整体少算一档。

recap 消费侧语义 (EOD/pre-EOD) 已由 test_auction_recap.py 锁死, 本文件零新增 recap 测试
(跨链引用, 保持 recap 侧零改动):
  - 15:40 Block 3 change_pct 从 EOD 帧计算            test_auction_recap.py:541-559
  - 15:10 pre-EOD 省略 close 统计 + EOD-pending 注记   test_auction_recap.py:636-643
  - pre_eod / no_auction_lake 标签判别                test_auction_recap.py:275-295

运行边界:
  - 恒 stub ``daily_pipeline.run_now`` (网络绑定), 从不触发真实同步。
  - 从不启动调度器: ``AsyncIOScheduler`` 用 fake 替换捕获 ``add_job``, 从
    ``daily_pipeline`` job 的闭包里提取 ``_pipeline_then_refresh`` (W-2)。
  - ``qs.paused()`` 用 fake 上下文管理器镜像生产契约 (quote_service.py:308-316)。
  - ``refresh_cache`` 用真实 DataStore+KlineRepository (tmp_path), 真读 parquet
    (镜像 test_minute_sync_verify._seed_daily_lake 配方), 绝不触碰真实 data/ 湖。
  - fixture 保持 1 标的 × 2 日, ms 级; 禁 ``background=True``; DataStore db 在 finally close。
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import polars as pl
import pytest

# 生产 import 放测试函数内 (repo 惯例 — 模块收集期不 import DuckDB 单例)。


class _FakeQuoteService:
    """fake quote_service, 镜像生产 ``QuoteService.paused()`` 契约 (quote_service.py:308-316):

    进入暂停 → yield → finally 恢复 (无论正常结束还是异常)。记录进入/退出次数供断言。
    """

    def __init__(self) -> None:
        self.pause_count = 0
        self.resume_count = 0

    @contextmanager
    def paused(self):
        self.pause_count += 1
        try:
            yield
        finally:
            self.resume_count += 1


_T1 = date(2026, 8, 3)
_T = date(2026, 8, 4)


def _eod_frame(d: date, close: float, symbol: str = "000001.SZ") -> pl.DataFrame:
    """单标的 EOD enriched 帧 (列 ⊆ ENRICHED_STORAGE_COLS, indicators/pipeline.py:57-71)。"""
    return pl.DataFrame({
        "symbol": [symbol],
        "date": [d],
        "open": [close - 0.2],
        "high": [close + 0.2],
        "low": [close - 0.5],
        "close": [close],
        "volume": [1000.0],
        "amount": [close * 1000.0],
        "raw_close": [close],
        "raw_high": [close + 0.2],
        "raw_low": [close - 0.5],
        "turnover_rate": [0.01],
        "consecutive_limit_ups": [0],
        "consecutive_limit_downs": [0],
        "quote_ts": [1754300000000],
    })


def _seed_lake(repo, *, prev_close: float, eod_close: float) -> date:
    """播种 2 日日K + 2 日 enriched (T-1, T), T 的 EOD close 与 T-1 互异。

    返回最新 enriched 日期 T。镜像 test_minute_sync_verify._seed_daily_lake 配方
    (append_daily/append_enriched 走 repo 自己的写助手, refresh_cache 真读 parquet)。
    """
    daily = pl.DataFrame({
        "symbol": ["000001.SZ", "000001.SZ"],
        "date": [_T1, _T],
        "open": [10.0, 10.2],
        "high": [11.0, 11.2],
        "low": [9.5, 9.7],
        "close": [prev_close, eod_close],
        "volume": [1000.0, 1200.0],
        "amount": [10500.0, 12960.0],
    })
    repo.append_daily(daily)
    repo.append_enriched(_eod_frame(_T1, prev_close))
    repo.append_enriched(_eod_frame(_T, eod_close))
    # DataStore 空目录启动时 DuckDB 视图注册被跳过 (glob 无文件会抛 IOException);
    # 数据落盘后重新注册, 镜像生产「同步写入后刷新视图」机制 (repository.py:160-161 注释)。
    repo.store._register_views()
    return _T


def _capture_pipeline_fn(monkeypatch, repo, capset):
    """fake AsyncIOScheduler 捕获 add_job → 从 daily_pipeline job 闭包提取 _pipeline_then_refresh。

    ``_pipeline_then_refresh`` 是 ``start_scheduler`` 内的闭包 (daily_pipeline.py:1115-1136),
    通过 ``scheduler.add_job(lambda: _run_tracked(_pipeline_then_refresh, "daily_pipeline"))``
    注册; 用 fake scheduler 捕获该 lambda, 再从 ``__closure__`` 提取目标函数体 (W-2)。
    返回的闭包函数持有 start_scheduler 参数 repo/capset 单元格。
    """
    from app.jobs import daily_pipeline

    captured: dict[str, object] = {}

    class _FakeScheduler:
        def __init__(self, **kwargs) -> None:
            pass

        def add_job(self, func, **kwargs):
            captured[kwargs["id"]] = func
            return None

        def start(self) -> None:
            return None

    monkeypatch.setattr(daily_pipeline, "AsyncIOScheduler", _FakeScheduler)
    daily_pipeline.start_scheduler(repo, capset)

    job = captured.get("daily_pipeline")
    assert job is not None, "daily_pipeline job 未注册到 fake scheduler"
    for cell in job.__closure__ or ():
        inner = getattr(cell, "cell_contents", None)
        if getattr(inner, "__name__", None) == "_pipeline_then_refresh":
            return inner
    raise AssertionError("闭包中未找到 _pipeline_then_refresh")


def _make_app_state(repo, capset, qs) -> SimpleNamespace:
    """构造 fake app_state: _pipeline_then_refresh 只消费 capabilities + quote_service。"""
    return SimpleNamespace(repo=repo, capabilities=capset, quote_service=qs)


def test_pipeline_then_refresh_refreshes_cache_on_success(tmp_path, monkeypatch):
    """成功路径: _pipeline_then_refresh 后 finally 必刷缓存 (R13, ce5c705 核心)。

    stub ``run_now`` (零网络) 返回 {"ok": True} 且先落盘 EOD 帧; spy 包
    ``repo.refresh_cache`` → 断言返回值原样返回、spy 被调 ≥1、刷新后
    latest-day enriched 资产持有今日 EOD close (15:30/run-now 配方)。
    """
    from app.jobs import daily_pipeline
    from app.tickflow.capabilities import CapabilitySet
    from app.tickflow.repository import DataStore, KlineRepository

    store = DataStore(tmp_path / "data")
    repo = KlineRepository(store)
    try:
        t = _seed_lake(repo, prev_close=10.5, eod_close=10.8)
        capset = CapabilitySet()
        qs = _FakeQuoteService()
        app_state = _make_app_state(repo, capset, qs)
        monkeypatch.setattr(daily_pipeline, "_get_app_state", lambda: app_state)

        def stubbed_run_now(repo, capset, on_progress=None):
            repo.append_enriched(_eod_frame(t, 11.5))  # 管道落盘新 EOD 帧
            return {"ok": True}

        monkeypatch.setattr(daily_pipeline, "run_now", stubbed_run_now)
        pipeline_fn = _capture_pipeline_fn(monkeypatch, repo, capset)

        calls: list[int] = []
        original_refresh = repo.refresh_cache

        def spy_refresh(*args, **kwargs):
            calls.append(1)
            return original_refresh(*args, **kwargs)

        monkeypatch.setattr(repo, "refresh_cache", spy_refresh)

        result = pipeline_fn()
        assert result == {"ok": True}          # 返回值原样上抛
        assert calls                            # finally 必刷缓存 (成功路径语义)
        assert qs.pause_count == 1 and qs.resume_count == 1  # qs.paused() 包裹 run_now

        # 刷新后 latest-day enriched 资产持有今日 EOD close
        df, cache_date = repo.get_enriched_latest_asset("stock")
        assert cache_date == t
        assert list(df["close"]) == [11.5]
        assert repo.enriched_latest_date() == t
    finally:
        store.db.close()


def test_pipeline_then_refresh_refreshes_cache_in_finally_on_stage_error(tmp_path, monkeypatch):
    """阶段软失败下 finally 仍刷缓存 (9aa96ed 「部分成功也生效」) 且异常继续上抛。

    stub ``run_now`` 先播种 enriched 分区再抛 ``PipelineStageError`` (daily_pipeline.py:36);
    ``pytest.raises`` 包裹调用; 异常后 ``get_enriched_latest_asset("stock")`` 返回 (df, T)
    —— 已落盘的日K/enriched 即便管道部分失败也刷进内存缓存。
    """
    from app.jobs import daily_pipeline
    from app.tickflow.capabilities import CapabilitySet
    from app.tickflow.repository import DataStore, KlineRepository

    store = DataStore(tmp_path / "data")
    repo = KlineRepository(store)
    try:
        _seed_lake(repo, prev_close=10.5, eod_close=10.8)
        capset = CapabilitySet()
        qs = _FakeQuoteService()
        app_state = _make_app_state(repo, capset, qs)
        monkeypatch.setattr(daily_pipeline, "_get_app_state", lambda: app_state)

        def staged_run_now(repo, capset, on_progress=None):
            # 模拟部分成功: 新 EOD 帧已落盘, 但某阶段软失败 → 抛 PipelineStageError
            repo.append_enriched(_eod_frame(_T, 11.2))
            raise daily_pipeline.PipelineStageError(["sync_kline failed"])

        monkeypatch.setattr(daily_pipeline, "run_now", staged_run_now)
        pipeline_fn = _capture_pipeline_fn(monkeypatch, repo, capset)

        with pytest.raises(daily_pipeline.PipelineStageError):
            pipeline_fn()

        assert qs.pause_count == 1 and qs.resume_count == 1  # paused 包裹在异常下也恢复

        # finally 刷缓存生效: 部分成功也生效 (9aa96ed)
        df, cache_date = repo.get_enriched_latest_asset("stock")
        assert cache_date == _T
        assert list(df["close"]) == [11.2]
        assert repo.enriched_latest_date() == _T
    finally:
        store.db.close()


def test_refresh_cache_loads_latest_enriched_eod_frame(tmp_path):
    """refresh_cache 真实加载最新 EOD enriched 帧 (cache_date==T, close==EOD closes)。

    直接调 ``repo.refresh_cache()`` (不经 _pipeline_then_refresh), 断言缓存从真实 parquet
    加载: ``get_enriched_latest_asset("stock")`` → cache_date == T 且 df.close == EOD closes;
    ``enriched_latest_date() == T`` (repository.py:1118-1120)。recap 15:40 Block 3 的
    EOD change_pct 由此帧驱动 (消费语义锁于 test_auction_recap.py:541-559)。
    """
    from app.tickflow.repository import DataStore, KlineRepository

    store = DataStore(tmp_path / "data")
    repo = KlineRepository(store)
    try:
        t = _seed_lake(repo, prev_close=10.5, eod_close=10.8)
        assert repo.enriched_latest_date() is None  # 冷启动: 缓存为空

        repo.refresh_cache(background=False)

        df, cache_date = repo.get_enriched_latest_asset("stock")
        assert cache_date == t
        assert list(df["close"]) == [10.8]          # EOD close, 与前日 10.5 互异
        assert repo.enriched_latest_date() == t
    finally:
        store.db.close()
