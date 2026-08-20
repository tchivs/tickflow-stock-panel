"""全局实时行情服务。

集中管理全市场行情拉取 + enriched 缓存，供盘中选股、自选股等所有模块复用。

架构:
  - 后台线程轮询 TickFlow get_by_universes(["CN_Equity_A", "CN_Index"])
  - 拉取行情 → 写 kline_daily (不复权) + 增量计算 enriched → 写盘 + 更新缓存
  - _enriched_cache 是唯一的盘中数据源 (OHLCV + 全套技术指标)
  - _live_agg_cache 是递推状态 (只加载一次, 盘中不变)

数据流 (每轮 ~15s):
  1. API 拉取 → raw_records (临时变量)
  2. raw_records → 写 kline_daily (不复权原始价格)
  3. raw_records → 更新 _enriched_cache 的 OHLCV
  4. 增量计算 enriched 指标 (~50ms)
  5. 写 kline_daily_enriched + 替换 _enriched_cache
  6. 通知 SSE

生命周期:
  - 服务启动时读取 preferences，若 enabled 则自动启动线程
  - 运行中可通过 API 切换开关
  - 关闭时停止线程
"""
from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import date, time as dt_time
from typing import Any

import polars as pl

from app.market_time import cn_now, cn_today
from app.parquet import scan_daily_parquet
from app.strategy.intraday_signals import IntradaySignalEvaluator

logger = logging.getLogger(__name__)



class QuoteSubscriber:
    """一个 SSE 连接对应一个订阅者: 独立事件 + 独立队列。

    此前四个通道共用服务级 Event + pending 列表, pop 是「取走」语义:
    多客户端 (多标签页/多设备) 时告警只会被先醒来的连接消费, 其余永远
    收不到; 共享 Event 的 clear/wait 也存在互相吞信号的竞态。
    改为每连接独立订阅者后, 事件对所有客户端广播。
    """

    def __init__(
        self,
        max_alerts: int = 1000,
        max_reviews: int = 200,
        analysis_scope: Any | None = None,
        max_analysis_progress: int = 200,
        advanced_scope: Any | None = None,
        max_advanced_progress: int = 200,
    ) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._max_alerts = max_alerts
        self._max_reviews = max_reviews
        self._max_analysis_progress = max_analysis_progress
        self._max_advanced_progress = max_advanced_progress
        self._analysis_scope = analysis_scope
        self._advanced_scope = advanced_scope
        self._quote_updated = False
        self._strategy_results_updated = False
        self._depth_updated = False
        self._portfolio_account_ids: list[str] = []
        self._alerts: list[dict] = []
        self._reviews: list[str] = []
        self._analysis_progress: list[dict[str, str]] = []
        self._advanced_progress: list[dict[str, str]] = []

    # ── 消费侧 (SSE generator 线程) ──────────────────────
    def wait(self, timeout: float = 5.0) -> bool:
        """阻塞等待任一通道有新信号。"""
        return self._event.wait(timeout=timeout)

    def pop(self) -> dict:
        """原子取走全部待推送内容并复位事件。"""
        with self._lock:
            out = {
                "quote_updated": self._quote_updated,
                "strategy_results_updated": self._strategy_results_updated,
                "depth_updated": self._depth_updated,
                "portfolio_updated": bool(self._portfolio_account_ids),
                "portfolio_account_ids": self._portfolio_account_ids,
                "alerts": self._alerts,
                "reviews": self._reviews,
                "analysis_progress": self._analysis_progress,
                "advanced_progress": self._advanced_progress,
            }
            self._quote_updated = False
            self._strategy_results_updated = False
            self._depth_updated = False
            self._alerts = []
            self._reviews = []
            self._analysis_progress = []
            self._advanced_progress = []
            self._portfolio_account_ids = []
            self._event.clear()
            return out

    # ── 生产侧 (行情轮询 / depth / 复盘线程) ─────────────
    def push_alerts(self, alerts: list[dict]) -> None:
        with self._lock:
            self._alerts.extend(alerts)
            if len(self._alerts) > self._max_alerts:  # 背压: 丢弃最旧
                self._alerts = self._alerts[-self._max_alerts:]
            self._event.set()

    def push_review(self, event_json: str) -> None:
        with self._lock:
            self._reviews.append(event_json)
            if len(self._reviews) > self._max_reviews:
                self._reviews = self._reviews[-self._max_reviews:]
            self._event.set()

    def clear_alerts(self) -> None:
        with self._lock:
            self._alerts = []
            if (
                not self._quote_updated
                and not self._strategy_results_updated
                and not self._depth_updated
                and not self._reviews
                and not self._analysis_progress
                and not self._advanced_progress
                and not self._portfolio_account_ids
            ):
                self._event.clear()

    def notify_quote(self) -> None:
        with self._lock:
            self._quote_updated = True
            self._event.set()

    def notify_strategy_results(self) -> None:
        with self._lock:
            self._strategy_results_updated = True
            self._event.set()

    def notify_depth(self) -> None:
        with self._lock:
            self._depth_updated = True
            self._event.set()

    def notify_portfolio_updated(self, account_ids: list[str | int]) -> None:
        with self._lock:
            for account_id in account_ids:
                normalized = str(account_id)
                if normalized and normalized not in self._portfolio_account_ids:
                    self._portfolio_account_ids.append(normalized)
            if self._portfolio_account_ids:
                self._event.set()

    def push_analysis_progress(self, progress: dict[str, str]) -> None:
        """Queue only persisted coarse state for the server-bound subject scope."""
        scope = self._analysis_scope
        if scope is None or not scope.allows(progress["subject_kind"], progress["subject_key"]):
            return
        with self._lock:
            self._analysis_progress.append(progress)
            if len(self._analysis_progress) > self._max_analysis_progress:
                self._analysis_progress = self._analysis_progress[-self._max_analysis_progress:]
            self._event.set()

    def push_advanced_progress(self, progress: dict[str, str]) -> None:
        """Queue only committed, allowlisted advanced state for the bound scope."""
        scope = self._advanced_scope
        if scope is None or not scope.allows(progress["subject_kind"], progress["subject_key"]):
            return
        with self._lock:
            self._advanced_progress.append(progress)
            if len(self._advanced_progress) > self._max_advanced_progress:
                self._advanced_progress = self._advanced_progress[-self._max_advanced_progress:]
            self._event.set()



# 落盘节流间隔: last_fetch_ms 仅在进程重启后用于显示"最后获取时间"(运行中读内存值),
# 每 30s 持久化一次足够, 避免 expert 档每秒一轮的全量 preferences 重写磁盘。
_LAST_FETCH_WRITE_INTERVAL_MS = 30_000.0
_last_fetch_written_at_ms: float = 0.0


def _persist_last_fetch(fetched_at_ms: float) -> None:
    """把"最后获取"时间戳持久化到 preferences, 使进程重启后仍可显示。

    放在锁外调用 (IO); 失败不影响主流程 (内存值已更新, 下次 fetch 再写)。
    距上次成功落盘不足 30s 时跳过 (节流只影响落盘频率, 内存值不受影响)。
    """
    global _last_fetch_written_at_ms
    if (fetched_at_ms - _last_fetch_written_at_ms) < _LAST_FETCH_WRITE_INTERVAL_MS:
        return
    try:
        from app.services import preferences
        preferences.save({"last_fetch_ms": round(fetched_at_ms, 0)})
        _last_fetch_written_at_ms = fetched_at_ms
    except Exception as e:  # noqa: BLE001
        logger.debug("last_fetch_ms 持久化失败 (不影响行情): %s", e)


def _monitor_name_map(repo) -> dict[str, str]:
    """监控回填用的 symbol → name 映射 (股票 + ETF + 指数, 股票优先)。

    走 repo.get_name_map() 的进程内 memo (三份 instruments 维表刷新时失效),
    避免每轮监控对 ~7000 行维表 iter_rows 重建。过滤空名称与旧行为一致。
    """
    return {s: n for s, n in repo.get_name_map().items() if n}


class QuoteService:
    """全局实时行情服务 — 单例。"""

    CORE_INDEX_SYMBOLS = ("000001.SH", "399001.SZ", "399006.SZ", "000680.SH")

    # 档位 → 最小轮询间隔 (秒)
    TIER_MIN_INTERVAL = {
        "expert": 1.0,
        "pro": 3.0,
        "starter": 6.0,
        "free": 6.0,
    }
    DEFAULT_INTERVAL = 6.0
    MAX_INTERVAL = 60.0
    # 自适应默认开启的连通性探测: 无显式偏好时先验证实时源能拉到数据再持久化 true;
    # 连续 PROBE_MAX_FAILURES 次源连接错误 → 自动禁用并持久化 false。见 _resolve_probe。
    PROBE_MAX_FAILURES = 3

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # 串行化行情拉取: 手动 POST /refresh 与后台轮询线程可能并发调用
        # _fetch_quotes, 两者同时写同一批 parquet/缓存会互相覆盖
        self._fetch_lock = threading.Lock()
        self._running = False
        self._enabled = False      # 全局开关 (持久化到 preferences)
        # 暂停态: 盘后管道/数据修正运行期间临时暂停取数, 防止与管道写同一批 parquet 竞态。
        # 与 _enabled 不同 — pause 不改 preferences、不 stop 线程, 仅让轮询循环跳过取数;
        # 进程重启后 _paused 归零, 从 preferences 恢复真实开关态, 无"假关闭"副作用。
        self._paused = False
        self._interval = self.DEFAULT_INTERVAL
        self._thread: threading.Thread | None = None
        self._repo = None          # 延迟注入, 避免循环导入
        # SSE 订阅者集合: 每个 /stream 连接一个 QuoteSubscriber, 事件广播到所有订阅者
        self._subscribers: set[QuoteSubscriber] = set()
        self._strategy_monitor = None            # 延迟注入
        self._app_state = None                   # 延迟注入 (FastAPI app.state)

        # 拉取元信息 (给 SSE / status 用)
        self._fetch_time: float = 0.0       # perf_counter (用于计算 quote_age_ms)
        self._fetch_ms: float = 0.0         # 拉取耗时 (毫秒)
        # _fetched_at 持久化到 preferences: 进程重启后仍能显示"最后获取"时间,
        # 不因关闭开关/重启而归零 (数据页卡片常驻显示, 方便判断上次拉取时刻)。
        try:
            from app.services import preferences as _prefs
            self._fetched_at: float = float(_prefs.load().get("last_fetch_ms", 0.0))
        except Exception:  # noqa: BLE001
            self._fetched_at = 0.0      # 拉取完成的 Unix 时间戳 (毫秒)
        self._symbol_count: int = 0
        self._index_symbol_count: int = 0
        self._etf_symbol_count: int = 0
        self._index_quotes_cache: pl.DataFrame | None = None
        self._intraday_signal_evaluator = IntradaySignalEvaluator()
        self._intraday_signal_bucket: dict[str, str] = {}
        # 午休/收盘最终同步状态: 到边界后必须成功拉取一版行情, 再进入休盘态。
        self._final_sync_done: set[tuple[date, str]] = set()
        self._final_sync_failed: dict[tuple[date, str], str] = {}
        # 自适应默认开启的探测态: True 表示线程在跑但尚未确认实时源连通,
        # 首次成功拉取 → 持久化 true; 连续错误达阈值 → _auto_disable。
        self._awaiting_confirm = False
        self._probe_failures = 0
        # stockdb WS 实时通道 (M004): None = 未接入; attach 后由 WS 推送驱动
        # 自选实时 + 指数实时, WS 断线自动回退腾讯 HTTP 轮询
        self._ws = None
        self._ws_last_submitted: set[str] = set()

    # ================================================================
    # 生命周期
    # ================================================================

    def start(self, interval: float = 0.0, *, persist: bool = True) -> None:
        """启动后台行情轮询线程。

        persist=False: 自适应默认开启的探测期 —— 线程照常跑, 但不落盘 true,
        待首次拉取确认实时源连通后由 _resolve_probe 持久化。显式开启(boot_check
        读到显式偏好 / enable())走 persist=True 直接落盘。
        """
        if self._running:
            return
        if interval <= 0:
            from app.services import preferences
            interval = preferences.get_realtime_quote_interval()
        self._interval = self._clamp_interval(interval)
        self._running = True
        self._enabled = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        if persist:
            self._save_enabled(True)
        logger.info("行情服务已启动, 轮询间隔 %.1fs", self._interval)

    def stop(self) -> None:
        """停止后台行情轮询线程（进程停机/内部停止）—— 不落盘关闭偏好。

        显式用户关闭走 disable()（持久化 false）；停机路径（main.py shutdown）
        只 stop() 不触碰偏好 —— 否则每次重启都把 realtime_quotes_enabled 抹成
        false，实时行情变会话级、用户选择被静默丢弃。
        """
        self._running = False
        self._enabled = False
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
        logger.info("行情服务已停止")

    def enable(self) -> bool:
        """开启自动行情 (不立即启动线程，等下一个交易时段)。

        none 档无实时行情权限,拒绝开启并返回 False;
        free 档开启自选股实时,starter+ 开启全市场实时。返回值表示是否真正开启。
        """
        if not self.is_realtime_allowed():
            logger.warning("实时行情开启被拒:当前档位(none)无实时行情权限")
            return False
        # 用户显式开启: 结束自适应探测态, 直接落盘 true。
        self._awaiting_confirm = False
        self._probe_failures = 0
        self._enabled = True
        self._save_enabled(True)
        if not self._running:
            from app.services import preferences
            self._interval = self._clamp_interval(preferences.get_realtime_quote_interval())
            self._running = True
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()
        logger.info("行情服务已启用, 轮询间隔 %.1fs", self._interval)
        return True

    def disable(self) -> None:
        """关闭自动行情（用户显式关闭, 持久化 false）。"""
        self._awaiting_confirm = False
        self._probe_failures = 0
        self.stop()
        self._save_enabled(False)
        logger.info("行情服务已关闭")

    # ================================================================
    # 临时暂停 (盘后管道/数据修正期间, 防止写盘竞态)
    # ================================================================

    def pause(self) -> None:
        """临时暂停行情轮询取数 (不关闭线程、不改 preferences)。

        用于盘后管道/数据修正运行期间, 防止实时行情覆写管道正在写的 parquet。
        与 stop() 的区别: 线程继续存活但跳过 _fetch_quotes; preferences 开关态不变,
        管道结束调用 resume() 即恢复。线程级检查, 即时生效, 无 join 等待。
        """
        self._paused = True
        logger.info("行情轮询已临时暂停 (管道/修正运行中)")

    def resume(self) -> None:
        """恢复暂停的行情轮询取数 (对应 pause)。"""
        self._paused = False
        logger.info("行情轮询已恢复")

    def is_paused(self) -> bool:
        """是否处于临时暂停态 (管道运行期间)。"""
        return self._paused

    @contextmanager
    def paused(self):
        """上下文管理器: 进入时暂停轮询取数, 退出时(含异常)自动恢复。

        供盘后管道/数据修正复用:
            with quote_service.paused():
                run_pipeline(...)
        无论正常结束还是异常/crash, finally 都会 resume (除非进程直接被 kill)。
        """
        self.pause()
        try:
            yield
        finally:
            self.resume()

    def boot_check(self) -> None:
        """启动时检查 preferences，若 enabled 则自动启动。

        none 档无实时行情权限:即使 preferences 标记为 enabled,
        也不启动,并同步 preferences 为关闭(避免 UI 误显示已开启)。

        自适应默认(无显式偏好): start(persist=False) 进入探测态, 不立刻落盘 true;
        首次成功拉取确认实时源连通后持久化, 连续失败则自动禁用。
        """
        from app.services import preferences
        if not self.is_realtime_allowed():
            if preferences.get_realtime_quotes_enabled():
                self._save_enabled(False)
            logger.info("实时行情未启动:当前档位(none)无实时行情权限")
            return
        enabled = preferences.get_realtime_quotes_enabled()
        if enabled:
            explicit = preferences.has_realtime_quotes_pref()
            self.start(persist=explicit)
            if not explicit:
                self._awaiting_confirm = True
                self._probe_failures = 0
                logger.info(
                    "实时行情按自适应默认开启, 等待实时源连通确认(最多 %d 次连续失败)",
                    self.PROBE_MAX_FAILURES,
                )

    def set_repo(self, repo) -> None:
        """注入 KlineRepository, 用于实时落盘。"""
        self._repo = repo

    def set_app_state(self, app_state) -> None:
        """注入 FastAPI app.state, 用于获取 strategy_monitor 等单例。"""
        self._app_state = app_state

    def set_interval(self, interval: float) -> float:
        """运行时更新轮询间隔（立即生效）。"""
        clamped = self._clamp_interval(interval)
        self._interval = clamped
        from app.services import preferences
        preferences.set_realtime_quote_interval(clamped)
        logger.info("轮询间隔已更新为 %.1fs", clamped)
        return clamped

    def get_min_interval(self) -> float:
        """返回当前档位允许的最小间隔。"""
        return self._tier_min_interval()

    # ================================================================
    # SSE 订阅管理 — 每个 /stream 连接一个订阅者, 事件广播
    # ================================================================

    def subscribe(
        self, *, analysis_scope: Any | None = None, advanced_scope: Any | None = None
    ) -> QuoteSubscriber:
        """注册一个 SSE 订阅者 (连接建立时调用)。"""
        sub = QuoteSubscriber(analysis_scope=analysis_scope, advanced_scope=advanced_scope)
        with self._lock:
            self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: QuoteSubscriber) -> None:
        """注销订阅者 (连接断开时调用)。"""
        with self._lock:
            self._subscribers.discard(sub)

    def _snapshot_subscribers(self) -> list[QuoteSubscriber]:
        with self._lock:
            return list(self._subscribers)

    def _broadcast_quote_updated(self) -> None:
        # 实时行情刷新后清空总览聚合缓存, 使看板 (overview-market) 在 SSE 触发的
        # 重取中拿到最新指数/聚合值。与 _broadcast 同时进行, 与侧栏 /intraday/indices
        # (无缓存, 直读实时缓存) 行为对齐, 避免看板落后于侧栏。
        # 延迟导入规避 services <-> api 层循环依赖。
        from app.api.overview import invalidate_overview_cache

        invalidate_overview_cache()
        for sub in self._snapshot_subscribers():
            sub.notify_quote()

    def notify_strategy_results_updated(self) -> None:
        """策略监控完成实时结果更新后调用，仅刷新策略页结果缓存。"""
        for sub in self._snapshot_subscribers():
            sub.notify_strategy_results()

    def notify_depth_updated(self) -> None:
        """五档盘口修正完成后调用: 通知 SSE 推送 depth_updated, 触发连板梯队刷新。

        与行情/告警通道独立 — 只刷新连板梯队, 不连带刷新 watchlist 等。
        """
        for sub in self._snapshot_subscribers():
            sub.notify_depth()

    def _broadcast_alerts(self, alerts: list[dict]) -> None:
        for sub in self._snapshot_subscribers():
            sub.push_alerts(alerts)

    def notify_portfolio_updated(self, account_ids: list[str | int]) -> None:
        """Fan out coalesced account changes through the existing SSE subscribers."""
        for sub in self._snapshot_subscribers():
            sub.notify_portfolio_updated(account_ids)

    def notify_analysis_progress(
        self, *, run_id: str, subject_kind: str, subject_key: str, status: str
    ) -> None:
        """Fan out a durable run state only to matching server-authorized scopes."""
        progress = {
            "run_id": run_id,
            "subject_kind": subject_kind,
            "subject_key": subject_key,
            "status": status,
        }
        for sub in self._snapshot_subscribers():
            sub.push_analysis_progress(progress)

    def notify_advanced_progress(
        self,
        *,
        job_id: str,
        subject_kind: str,
        subject_key: str,
        stage: str,
        occurred_at: str,
        committed: bool,
        human_label: str,
        audit_reference: str | None,
    ) -> None:
        """Publish a committed durable advanced-job stage without graph/provider data."""
        allowed_stages = {
            "authorized",
            "frozen",
            "drafted",
            "gates_complete",
            "awaiting_review",
            "recorded",
            "rejected",
        }
        if (
            not committed
            or stage not in allowed_stages
            or not all(isinstance(value, str) and value for value in (job_id, subject_kind, subject_key, occurred_at, human_label))
            or len(human_label) > 256
            or (audit_reference is not None and (not isinstance(audit_reference, str) or not audit_reference))
        ):
            return
        progress = {
            "job_id": job_id,
            "subject_kind": subject_kind,
            "subject_key": subject_key,
            "stage": stage,
            "label": human_label,
            "occurred_at": occurred_at,
            "audit_reference": audit_reference,
        }
        for sub in self._snapshot_subscribers():
            sub.push_advanced_progress(progress)


    def persist_stream_and_enqueue_alerts(
        self,
        *,
        events: list[dict],
        repository,
        delivery_service,
        channel_configs,
        quiet_period: bool = False,
        bypass_quiet_period: bool = False,
    ) -> list[dict]:
        """Keep accepted alerts durable and visible before external delivery starts."""
        persisted_events: list[dict] = []
        for event in events:
            persisted = repository.record_alert_event(event)
            event["id"] = persisted["id"]
            event["occurred_at"] = persisted["occurred_at"]
            persisted_events.append(event)
        if not persisted_events:
            return []
        self._broadcast_alerts(persisted_events)
        for event in persisted_events:
            delivery_service.enqueue(
                event_id=event["id"],
                channel_configs=channel_configs,
                quiet_period=quiet_period,
                bypass_quiet_period=bypass_quiet_period,
            )
        return persisted_events

    def push_alerts(self, alerts: list[dict]) -> None:
        self._broadcast_alerts(alerts)

    def clear_pending_alerts(self) -> None:
        for sub in self._snapshot_subscribers():
            sub.clear_alerts()

    def push_review_event(self, event_json: str) -> None:
        """广播一条复盘进度事件(JSON 字符串), 唤醒所有 SSE generator。

        事件格式与 recap_market_stream 的产出一致(meta/delta/error/done),
        前端 reviewStore 直接消费。背压在订阅者队列内做 (丢弃最旧)。
        """
        for sub in self._snapshot_subscribers():
            sub.push_review(event_json)

    # ================================================================
    # 档位感知间隔限制
    # ================================================================

    @staticmethod
    def _current_tier() -> str:
        """获取当前档位名（小写）。"""
        from app.tickflow.policy import tier_label
        return tier_label().split()[0].split("+")[0].strip().lower()

    @classmethod
    def realtime_mode(cls) -> str:
        """当前实时行情模式: none / watchlist / full_market。

        腾讯源免费无需 key, 恒为 full_market (全市场实时, 无档位限制);
        TickFlow 才按档位区分 none/free→watchlist/starter+→full_market。
        """
        from app.services import preferences
        if preferences.get_realtime_data_provider() != "tickflow":
            return "full_market"
        tier = cls._current_tier()
        if tier == "none":
            return "none"
        if tier == "free":
            return "watchlist"
        return "full_market"

    @classmethod
    def is_realtime_allowed(cls) -> bool:
        """当前档位是否允许使用实时行情。"""
        return cls.realtime_mode() != "none"

    @classmethod
    def _tier_min_interval(cls) -> float:
        tier = cls._current_tier()
        return cls.TIER_MIN_INTERVAL.get(tier, cls.DEFAULT_INTERVAL)

    def _clamp_interval(self, interval: float) -> float:
        return max(self._tier_min_interval(), min(self.MAX_INTERVAL, interval))

    # ================================================================
    # 行情数据访问
    # ================================================================

    def get_enriched_today(self) -> tuple[pl.DataFrame, date | None]:
        """返回今天 enriched 数据 + 日期 (线程安全)。

        所有页面统一通过此方法获取实时行情 + 技术指标。
        """
        if not self._repo:
            return pl.DataFrame(), None
        return self._repo.get_enriched_latest()

    def get_quotes_compat(self) -> pl.DataFrame:
        """兼容接口: 返回行情 DataFrame (用于盘中选股等需要 last_price/prev_close 的场景)。

        从 _enriched_cache 取 today 的数据, 只选行情基础列, 补上 last_price 别名。
        不返回指标列, 避免 JOIN live_agg 时列名冲突。
        """
        df, _ = self.get_enriched_today()
        if df.is_empty():
            return df

        # 只取盘中选股需要的行情基础列
        keep = [c for c in [
            "symbol", "close", "open", "high", "low", "volume", "amount",
            "prev_close", "change_pct", "change_amount", "amplitude", "turnover_rate",
        ] if c in df.columns]
        df = df.select(keep)

        # enriched 的 close 等价于 last_price
        if "close" in df.columns and "last_price" not in df.columns:
            df = df.with_columns(pl.col("close").alias("last_price"))
        return df

    def get_index_quotes(self, symbols: list[str] | None = None) -> pl.DataFrame:
        """返回实时指数行情缓存。不会触发 TickFlow 请求。"""
        with self._lock:
            df = self._index_quotes_cache.clone() if self._index_quotes_cache is not None else pl.DataFrame()
        if df.is_empty():
            return df
        if symbols:
            return df.filter(pl.col("symbol").is_in(symbols))
        return df

    def status(self) -> dict:
        """返回行情服务状态。"""
        from app.services import preferences
        age = (time.perf_counter() - self._fetch_time) * 1000 if self._fetch_time else -1
        mode = self.realtime_mode()
        phase = self._market_phase()
        final_key = self._final_sync_key(phase)
        final_done = bool(final_key and final_key in self._final_sync_done)
        final_failed = self._final_sync_failed.get(final_key) if final_key else None
        return {
            "enabled": self._enabled,
            "running": self._running,
            "paused": self._paused,
            "mode": mode,
            "realtime_allowed": mode != "none",
            "watchlist_symbol_count": len(preferences.get_realtime_watchlist_symbols()),
            "interval_s": self._interval,
            "symbol_count": self._symbol_count,
            "index_symbol_count": self._index_symbol_count,
            "etf_symbol_count": self._etf_symbol_count,
            "quote_age_ms": round(age, 0) if age >= 0 else None,
            # 交易时段 = 连续竞价; polling_window 另行返回,避免午休/收盘缓冲误显示为交易中。
            "is_trading_hours": self._is_continuous_trading(),
            "is_polling_window": self._should_poll_for_phase(phase),
            "market_phase": phase,
            "final_sync_done": final_done,
            "final_sync_failed": final_failed,
            "last_fetch_ms": round(self._fetched_at, 0) if self._fetched_at else None,
        }

    def refresh(self) -> dict:
        """手动触发一次行情拉取。"""
        self._fetch_quotes()
        return self.status()

    def trigger_phase1_fixture_monitor(self) -> dict[str, bool]:
        """Evaluate persisted fixture data without opening the live quote path."""
        if os.environ.get("PHASE1_FIXTURE_MODE", "").strip().lower() not in {"1", "true", "yes"}:
            raise RuntimeError("fixture monitor trigger is unavailable outside Phase 1 acceptance")
        self._evaluate_monitors(pl.DataFrame(), None)
        return {"triggered": True}

    # ================================================================
    # 后台轮询
    # ================================================================

    def _poll_loop(self) -> None:
        while self._running and self._enabled:
            try:
                # 管道/数据修正运行期间临时暂停取数, 防止与管道写同一批 parquet 竞态。
                # 线程继续存活 + 分片 sleep, resume() 后即时恢复, 无需重启线程。
                if not self._paused:
                    phase = self._market_phase()
                    # WS 订阅集对齐 (自选增删后 1 周期内生效; 幂等)
                    self._sync_ws_subscriptions()
                    if self._should_fetch_for_phase(phase):
                        is_final = phase in {"morning_final", "close_final"}
                        ok = self._fetch_quotes(final=is_final)
                        if is_final:
                            key = self._final_sync_key(phase)
                            if key and ok:
                                self._final_sync_done.add(key)
                                self._final_sync_failed.pop(key, None)
                                logger.info("%s 最终行情同步完成, 进入休盘态", "午休" if phase == "morning_final" else "收盘")
                            elif key:
                                self._final_sync_failed[key] = "fetch_failed"
                                logger.warning("%s 最终行情同步失败, 将继续重试", "午休" if phase == "morning_final" else "收盘")
                    else:
                        logger.debug("非轮询阶段(%s), 跳过行情轮询", phase)
            except Exception as e:  # noqa: BLE001
                logger.warning("行情轮询异常: %s", e)

            waited = 0.0
            while self._running and self._enabled and waited < self._interval:
                time.sleep(0.5)
                waited += 0.5
    # ================================================================
    # stockdb WS 实时通道 (M004)
    # ================================================================

    # 核心指数显示名 (WS snap 无 name 字段, 前端指数卡需要)
    _CORE_INDEX_NAMES = {
        "000001.SH": "上证指数",
        "399001.SZ": "深证成指",
        "399006.SZ": "创业板指",
        "000680.SH": "科创综指",
    }

    def attach_stockdb_ws(self, ws) -> None:
        """接入 WS 客户端: 注册 quotes 回调 + 立即对齐订阅集 (bootstrap 启动时)。"""
        self._ws = ws
        ws.on("quotes", self._on_ws_quotes)
        self._sync_ws_subscriptions()

    def _ws_index_symbol_set(self) -> set[str]:
        """指数判定集: 核心指数 ∪ 本地指数维表 (后缀形态)。"""
        syms = set(self.CORE_INDEX_SYMBOLS)
        if self._repo is not None:
            try:
                syms.update(self._repo.get_index_symbol_set() or [])
            except Exception:  # noqa: BLE001 — 维表不可得时只按核心指数判
                pass
        return syms

    def _sync_ws_subscriptions(self) -> None:
        """WS quotes 订阅集 = 核心指数 ∪ 自选 (≤200, 服务端单客户端上限)。

        幂等: 集合未变化不发命令。由轮询循环每周期调用 (自选增删后 1 个周期内生效)。
        """
        if self._ws is None:
            return
        from app.services import preferences
        want = set(self.CORE_INDEX_SYMBOLS)
        try:
            want.update(preferences.get_realtime_watchlist_symbols() or [])
        except Exception:  # noqa: BLE001
            pass
        if want and want != self._ws_last_submitted:
            self._ws_last_submitted = set(want)
            from app.data_providers.stockdb_provider import _to_prefix
            self._ws.set_quotes_symbols(sorted(_to_prefix(s) for s in want))

    def _on_ws_quotes(self, data: list[dict]) -> None:
        """WS quotes 批量帧回调 (asyncio 线程): 指数与自选股票分流。"""
        index_syms = self._ws_index_symbol_set()
        index_records: list[dict] = []
        stock_records: list[dict] = []
        for item in data:
            snap = item.get("snap") or {}
            sym_raw = str(item.get("symbol") or snap.get("symbol") or "")
            if not sym_raw:
                continue
            from app.data_providers.stockdb_provider import _to_suffix
            sym = _to_suffix(sym_raw)
            last = snap.get("last")
            prev = snap.get("prev_close")
            if last is None or prev is None:
                continue
            change = snap.get("change")
            if change is None:
                change = float(last) - float(prev)
            record = {
                "symbol": sym,
                "name": self._CORE_INDEX_NAMES.get(sym),
                "last_price": last,
                "prev_close": prev,
                "open": snap.get("open"),
                "high": snap.get("high"),
                "low": snap.get("low"),
                "volume": snap.get("volume_hand"),
                "amount": snap.get("amount_yuan"),
                # stockdb pct_chg 为百分数 (-0.02 = -0.02%) → AQ 小数制契约
                "change_pct": (snap.get("pct_chg") / 100.0) if snap.get("pct_chg") is not None else None,
                "change_amount": change,
            }
            ts = snap.get("bar_time")
            if ts:
                try:
                    from datetime import datetime as _dt
                    record["timestamp"] = int(_dt.fromisoformat(ts).timestamp() * 1000)
                except ValueError:
                    pass
            if sym in index_syms:
                index_records.append(record)
            else:
                stock_records.append(record)
        if index_records:
            self._apply_ws_index_records(index_records)
        if stock_records:
            self._process_watchlist_records(stock_records, t0=time.perf_counter(),
                                            now_ts=time.perf_counter(), from_ws=True)

    def _apply_ws_index_records(self, records: list[dict]) -> None:
        """WS 指数帧 → 实时指数缓存 (upsert, 不清自选缓存, 不落股票 parquet)。"""
        new_df = self._build_index_quotes(records)
        if new_df.is_empty():
            return
        with self._lock:
            old = self._index_quotes_cache
            merged = (pl.concat([old, new_df]).unique(subset=["symbol"], keep="last")
                      if old is not None and not old.is_empty() else new_df)
            self._index_quotes_cache = merged
            self._index_symbol_count = merged.height
            self._fetch_time = time.perf_counter()
            self._fetched_at = time.time() * 1000
        logger.debug("WS 指数实时: %d 只 (缓存共 %d)", len(records), merged.height)

    def _fetch_quotes(self, *, final: bool = False) -> bool:
        """按当前档位拉取行情。加锁串行化 (后台轮询 vs 手动 refresh)。返回本轮是否成功更新。"""
        with self._fetch_lock:
            before = self._fetched_at
            if final:
                logger.info("最终行情同步开始")
            if self.realtime_mode() == "watchlist":
                status = self._fetch_watchlist_quotes()
            else:
                status = self._fetch_full_market_quotes()
            ok = self._fetched_at > before
        # 自适应默认探测(仅探测期): 成功→持久化 true; 连续源错误→自动禁用。
        self._resolve_probe(status=status, ok=ok)
        return ok

    # ================================================================
    # 自适应默认开启的连通性探测 (实时源连通性门控)
    # ================================================================

    def _resolve_probe(self, *, status: str, ok: bool) -> None:
        """自适应默认开启的连通性判定(仅探测期有效, 其余状态无操作)。

        - ok: 拉到数据 → 实时源连通, 持久化 true, 退出探测态。
        - status == "error": 源连接错误(网络/鉴权/服务端) → 累计;
          连续 PROBE_MAX_FAILURES 次 → _auto_disable 自动禁用并持久化 false。
        - empty/skip: 源可达但暂无数据 / 配置未拉取, 不计数, 保持探测。
        """
        if not self._awaiting_confirm:
            return
        if ok:
            self._awaiting_confirm = False
            self._probe_failures = 0
            self._save_enabled(True)
            logger.info("实时源连通确认: 自适应默认开启已生效并持久化")
            return
        if status == "error":
            self._probe_failures += 1
            logger.warning(
                "实时源连接失败 %d/%d 次, 连续失败将自动禁用实时行情",
                self._probe_failures, self.PROBE_MAX_FAILURES,
            )
            if self._probe_failures >= self.PROBE_MAX_FAILURES:
                self._auto_disable()

    def _auto_disable(self) -> None:
        """实时源持续不可达 → 自动禁用并持久化 false。

        从轮询线程内调用: 只关标志、不 join 自身线程, 轮询循环自然退出。
        """
        self._awaiting_confirm = False
        self._probe_failures = 0
        self._enabled = False
        self._running = False
        self._save_enabled(False)
        logger.warning("实时源不可达, 已自动禁用实时行情(可在设置中手动重新开启)")

    def _all_market_symbols(self) -> list[str]:
        """全市场股票 + 指数 + ETF 代码 (instruments 表, 去重后带交易所后缀)。"""
        if not self._repo:
            return []
        symbols: set[str] = set()
        try:
            inst = self._repo.get_instruments()
            if not inst.is_empty() and "symbol" in inst.columns:
                symbols.update(inst["symbol"].cast(pl.Utf8).to_list())
        except Exception as e:
            logger.warning("all_market_symbols instruments: %s", e)
        try:
            idx = self._repo.get_index_instruments()
            if not idx.is_empty() and "symbol" in idx.columns:
                symbols.update(idx["symbol"].cast(pl.Utf8).to_list())
        except Exception as e:
            logger.warning("all_market_symbols index: %s", e)
        try:
            etf = self._repo.get_etf_instruments()
            if not etf.is_empty() and "symbol" in etf.columns:
                symbols.update(etf["symbol"].cast(pl.Utf8).to_list())
        except Exception as e:
            logger.warning("all_market_symbols etf: %s", e)
        return sorted(symbols)

    def _fetch_full_market_quotes(self) -> str:
        """拉取全市场行情 → 写 daily + 计算 enriched + 更新缓存。

        返回状态: "ok"=已取数更新; "empty"=源可达但无数据; "error"=源连接错误;
        "skip"=配置原因未拉取(无代码/无key), 不计入连通性失败。供 _resolve_probe 判定。
        """
        from app.services import preferences

        provider_name = preferences.get_realtime_data_provider()
        if provider_name != "tickflow":
            from app.data_providers import custom as custom_sources
            if custom_sources.provider_has_dataset(provider_name, "realtime"):
                try:
                    t0 = time.perf_counter()
                    now_ts = time.perf_counter()
                    records = custom_sources.get_provider(provider_name).get_realtime()
                except Exception as e:
                    logger.warning("自定义实时行情拉取失败: %s", e)
                    return "error"
                if not records:
                    logger.warning("自定义实时行情数据为空")
                    return "empty"
                self._process_full_market_records(records, t0=t0, now_ts=now_ts)
                return "ok"
            if provider_name == "tencent":
                # 腾讯实时: 免费不封 IP, 从 instruments 拿全市场代码分批拉取。
                from app.data_providers import chain as provider_chain

                symbols = self._all_market_symbols()
                if not symbols:
                    logger.warning("腾讯实时拉取失败: 无 instruments 代码")
                    return "skip"
                try:
                    t0 = time.perf_counter()
                    now_ts = time.perf_counter()
                    provider = provider_chain.tencent_provider()
                    records = provider.get_realtime(symbols=symbols)
                except Exception as e:  # noqa: BLE001
                    logger.warning("腾讯实时拉取失败: %s", e)
                    return "error"
                if not records:
                    logger.warning("腾讯实时数据为空")
                    return "empty"
                self._process_full_market_records(records, t0=t0, now_ts=now_ts)
                return "ok"
            # 自定义源未配置 realtime → 回退 TickFlow

        from app.tickflow.client import get_paid_realtime_client

        tf = get_paid_realtime_client()
        if tf is None:
            logger.warning("实时行情拉取失败:未配置付费服务器 API Key")
            return "skip"
        t0 = time.perf_counter()
        now_ts = time.perf_counter()

        try:
            from app.services import preferences
            all_index_symbols = set(self._repo.get_index_symbol_set()) if self._repo else set()
            core_index_symbols = set(preferences.get_realtime_index_symbols() or self.CORE_INDEX_SYMBOLS)
            all_index_symbols.update(core_index_symbols)
            # 指数监控规则标的并入轮询 (mode=core 时 quotes.get 显式拉取覆盖; mode=all 被 CN_Index 全覆盖)
            monitor_index_symbols: set[str] = set()
            engine = getattr(self._app_state, "monitor_engine", None) if self._app_state else None
            if engine:
                for _r in list(engine.rules.values()):
                    if _r.get("enabled", True) and _r.get("asset_type") == "index" and _r.get("scope") == "symbols":
                        monitor_index_symbols.update(s for s in _r.get("symbols", []) if s)
            all_index_symbols.update(monitor_index_symbols)
            all_etf_symbols = set()
            if self._repo:
                etf_inst = self._repo.get_etf_instruments()
                if not etf_inst.is_empty() and "symbol" in etf_inst.columns:
                    all_etf_symbols = set(etf_inst["symbol"].cast(pl.Utf8).to_list())

            universes: list[str] = []
            if preferences.get_realtime_pull_stock():
                universes.append("CN_Equity_A")
            if preferences.get_realtime_pull_etf() and all_etf_symbols:
                universes.append("CN_ETF")
            if preferences.get_realtime_pull_index() and preferences.get_realtime_index_mode() == "all":
                universes.append("CN_Index")

            resp = []
            if universes:
                _u0 = time.perf_counter()
                logger.info("拉取全市场行情 (universes=%s, SDK超时=30s×重试3)", universes)
                resp.extend(tf.quotes.get_by_universes(universes=universes) or [])
                logger.info("全市场行情拉取完成: %d 条 (%.2fs)", len(resp), time.perf_counter() - _u0)
            if preferences.get_realtime_pull_index() and preferences.get_realtime_index_mode() == "core":
                _i0 = time.perf_counter()
                _core_syms = sorted(core_index_symbols | monitor_index_symbols)
                resp.extend(tf.quotes.get(symbols=_core_syms) or [])
                logger.info("核心指数行情拉取完成: %d 只 (%.2fs)", len(_core_syms), time.perf_counter() - _i0)
        except Exception as e:  # noqa: BLE001
            logger.warning("行情拉取失败 (%.2fs): %s", time.perf_counter() - t0, e)
            return "error"

        if not resp:
            logger.warning("行情数据为空")
            return "empty"

        # ---- 解析 API 响应 (临时变量, 用完丢弃) ----
        records = []
        for q in resp:
            ext = q.get("ext") or {}
            last_price = q.get("last_price")
            prev_close = q.get("prev_close")
            change_amount = ext.get("change_amount")
            change_pct = ext.get("change_pct")
            if change_amount is None and last_price is not None and prev_close is not None:
                change_amount = float(last_price) - float(prev_close)
            if change_pct is None and change_amount is not None and prev_close not in (None, 0):
                # 与 API ext.change_pct 同为小数制 (0.0366 = 3.66%),
                # enriched 全项目约定小数 (见 pipeline.py), 此处不可乘 100
                change_pct = float(change_amount) / float(prev_close)
            records.append({
                "symbol": q.get("symbol"),
                "name": q.get("name") or ext.get("name"),
                "last_price": last_price,
                "prev_close": prev_close,
                "open": q.get("open"),
                "high": q.get("high"),
                "low": q.get("low"),
                "volume": q.get("volume"),
                "amount": q.get("amount"),
                "change_pct": change_pct,
                "change_amount": change_amount,
                "amplitude": ext.get("amplitude"),
                "turnover_rate": ext.get("turnover_rate"),
                "timestamp": q.get("timestamp"),
                "session": q.get("session"),
            })

        self._process_full_market_records(records, t0=t0, now_ts=now_ts)
        return "ok"

    def _process_full_market_records(self, records: list[dict], *, t0: float, now_ts: float) -> None:
        """把全市场 records 写盘并增量计算 enriched。"""
        from app.services import preferences
        all_index_symbols = set(self._repo.get_index_symbol_set()) if self._repo else set()
        core_index_symbols = set(preferences.get_realtime_index_symbols() or self.CORE_INDEX_SYMBOLS)
        all_index_symbols.update(core_index_symbols)
        all_etf_symbols = set()
        if self._repo:
            etf_inst = self._repo.get_etf_instruments()
            if not etf_inst.is_empty() and "symbol" in etf_inst.columns:
                all_etf_symbols = set(etf_inst["symbol"].cast(pl.Utf8).to_list())

        if not records:
            logger.warning("行情数据为空")
            return

        index_records = [r for r in records if r.get("symbol") in all_index_symbols]
        etf_records = [r for r in records if r.get("symbol") in all_etf_symbols]
        stock_records = [
            r for r in records
            if r.get("symbol") not in all_index_symbols and r.get("symbol") not in all_etf_symbols
        ]

        fetch_ms = (time.perf_counter() - t0) * 1000
        fetched_at = time.time() * 1000

        # ---- 更新元信息 ----
        with self._lock:
            self._fetch_time = now_ts
            self._fetch_ms = fetch_ms
            self._fetched_at = fetched_at
            self._symbol_count = len(stock_records)
            self._index_symbol_count = len(index_records)
            self._etf_symbol_count = len(etf_records)
            self._index_quotes_cache = self._build_index_quotes(index_records)

        _persist_last_fetch(fetched_at)
        logger.info("行情刷新: %d 只股票, %d 只ETF, %d 只指数, 耗时 %.0fms", len(stock_records), len(etf_records), len(index_records), fetch_ms)
        # ---- 写 kline_daily (不复权原始价格, 只有 OHLCV) ----
        daily_df = self._build_daily(stock_records)
        if not daily_df.is_empty() and self._repo:
            try:
                self._repo.flush_live_daily(daily_df)
            except Exception as e:  # noqa: BLE001
                logger.warning("日K写盘失败: %s", e)

        etf_daily_df = self._build_daily(etf_records)
        if not etf_daily_df.is_empty() and self._repo:
            try:
                self._repo.flush_live_daily_asset("etf", etf_daily_df)
            except Exception as e:  # noqa: BLE001
                logger.warning("ETF 日K写盘失败: %s", e)

        # ---- 构建 API 直接值的补充表 (不写 daily, 只用于 enriched 计算) ----
        quote_extra = self._build_quote_extra(stock_records)
        etf_quote_extra = self._build_quote_extra(etf_records)

        # ---- 增量计算 enriched + 写盘 + 更新缓存 ----
        if not daily_df.is_empty() and self._repo:
            self._flush_live_enriched(daily_df, quote_extra, asset_type="stock")
        if not etf_daily_df.is_empty() and self._repo:
            self._flush_live_enriched(etf_daily_df, etf_quote_extra, asset_type="etf")
        # ---- 指数: 仅有指数监控规则时才写盘 (无规则零成本) ----
        # mode=all (完整 CN_Index universe) → flush 覆盖; mode=core (部分标的) → merge 不截断分区
        engine = getattr(self._app_state, "monitor_engine", None) if self._app_state else None
        if engine and engine.has_asset_rules("index") and self._repo:
            index_daily_df = self._build_daily(index_records)
            if not index_daily_df.is_empty():
                use_flush = preferences.get_realtime_index_mode() == "all"
                try:
                    if use_flush:
                        self._repo.flush_live_daily_asset("index", index_daily_df)
                    else:
                        self._repo.merge_live_daily_asset("index", index_daily_df)
                except Exception as e:  # noqa: BLE001
                    logger.warning("指数日K写盘失败: %s", e)
                self._flush_live_enriched(index_daily_df, self._build_quote_extra(index_records), asset_type="index", merge=not use_flush)

        # stockdb WS 推送驱动时跳过腾讯 HTTP 轮询 (M004): WS 健康 = 近 30s 有帧,
        # 断线/静默自动回退本路径。收盘 final 定版不受影响 (边界后 WS 静默 → 回退)。
        if self._ws is not None and self._ws.is_healthy():
            logger.debug("自选实时由 stockdb WS 推送驱动, 跳过 HTTP 轮询")
            return "ok"

        # ---- 通知 SSE ----
        self._broadcast_quote_updated()

        # ---- 策略监控 + 告警评估 ----
        self._evaluate_monitors(daily_df, quote_extra)

    def _process_watchlist_records(self, records: list[dict], *, t0: float, now_ts: float,
                                   from_ws: bool = False) -> None:
        """自选实时 records → 元信息 + 日K写盘 + enriched + 通知。

        from_ws=True (stockdb WS 推送帧): 指数缓存由 _apply_ws_index_records
        独立维护, 此处不清 (腾讯 HTTP 全量刷新模式才需要清过期指数缓存)。
        """
        if not records:
            logger.warning("自选实时行情数据为空")
            return
        fetch_ms = (time.perf_counter() - t0) * 1000
        fetched_at = time.time() * 1000

        # 资产分流 (upstream 接枝): ETF/指数进自选时按各自资产落盘, 不污染股票表。
        index_set = self._repo.get_index_symbol_set() if self._repo else set()
        etf_set = self._repo.get_etf_symbol_set() if self._repo else set()
        index_records, etf_records, stock_records = self._split_records_by_asset(
            records, index_set, etf_set)

        with self._lock:
            self._fetch_time = now_ts
            self._fetch_ms = fetch_ms
            self._fetched_at = fetched_at
            self._symbol_count = len(stock_records)
            self._etf_symbol_count = len(etf_records)
            if not from_ws:
                # 腾讯 HTTP 全量刷新模式: 指数记录可来自监控规则标的, 重建缓存;
                # WS 模式指数计数/缓存由 _apply_ws_index_records 维护, 不覆盖
                self._index_symbol_count = len(index_records)
                self._index_quotes_cache = (
                    self._build_index_quotes(index_records) if index_records else None)

        _persist_last_fetch(fetched_at)
        logger.info("自选实时刷新(%s): %d 只股票, %d 只ETF, %d 只指数, 耗时 %.0fms",
                    "ws" if from_ws else "http", len(stock_records),
                    len(etf_records), len(index_records), fetch_ms)

        daily_df = self._build_daily(stock_records)
        quote_extra = self._build_quote_extra(stock_records)
        if not daily_df.is_empty() and self._repo:
            try:
                self._repo.merge_live_daily_asset("stock", daily_df)
            except Exception as e:  # noqa: BLE001
                logger.warning("自选实时日K写盘失败: %s", e)
            self._flush_live_enriched(daily_df, quote_extra, asset_type="stock", merge=True)

        etf_daily_df = self._build_daily(etf_records)
        if not etf_daily_df.is_empty() and self._repo:
            try:
                self._repo.merge_live_daily_asset("etf", etf_daily_df)
            except Exception as e:  # noqa: BLE001
                logger.warning("自选实时 ETF 日K写盘失败: %s", e)
            self._flush_live_enriched(etf_daily_df, self._build_quote_extra(etf_records),
                                      asset_type="etf", merge=True)

        if not from_ws and index_records:
            # HTTP 回退路径才落指数日K (WS 模式指数走 _apply_ws_index_records)
            index_daily_df = self._build_daily(index_records)
            if not index_daily_df.is_empty() and self._repo:
                try:
                    self._repo.merge_live_daily_asset("index", index_daily_df)
                except Exception as e:  # noqa: BLE001
                    logger.warning("自选实时指数日K写盘失败: %s", e)
                self._flush_live_enriched(index_daily_df,
                                          self._build_quote_extra(index_records),
                                          asset_type="index", merge=True)

        self._broadcast_quote_updated()
        self._evaluate_monitors(daily_df, quote_extra)

    def _fetch_watchlist_quotes(self) -> str:
        """自选股实时: 免费档最多 5 个; 腾讯源无需付费 key。

        返回状态: "ok"=已取数更新; "empty"=源可达但无数据; "error"=源连接错误;
        "skip"=配置原因未拉取(无标的/无key), 不计入连通性失败。供 _resolve_probe 判定。
        """
        from app.services import preferences
        symbols = preferences.get_realtime_watchlist_symbols()
        # 指数监控规则标的并入轮询 (与股票共享 batch 额度)
        engine = getattr(self._app_state, "monitor_engine", None) if self._app_state else None
        if engine:
            for _r in list(engine.rules.values()):
                if _r.get("enabled", True) and _r.get("asset_type") == "index" and _r.get("scope") == "symbols":
                    for _s in _r.get("symbols", []):
                        if _s and _s not in symbols:
                            symbols.append(_s)
        if not symbols:
            logger.info("自选实时未配置标的, 跳过行情拉取")
            return "skip"

        # stockdb WS 推送驱动时跳过 HTTP 轮询 (M004): WS 健康 = 近 30s 有推送帧。
        # 断线/静默自动回退腾讯 HTTP; 收盘 final 定版不受影响 (边界后 WS 静默 → 回退)。
        if self._ws is not None and self._ws.is_healthy():
            logger.debug("自选实时由 stockdb WS 推送驱动, 跳过 HTTP 轮询")
            return "ok"

        provider_name = preferences.get_realtime_data_provider()
        if provider_name == "tencent":
            from app.data_providers import chain as provider_chain

            t0 = time.perf_counter()
            now_ts = time.perf_counter()
            try:
                provider = provider_chain.tencent_provider()
                records = provider.get_realtime(symbols=symbols)
            except Exception as e:
                logger.warning("腾讯自选实时拉取失败: %s", e)
                return "error"
            if not records:
                logger.warning("腾讯自选实时数据为空")
                return "empty"
            self._process_watchlist_records(records, t0=t0, now_ts=now_ts)
            return "ok"

        from app.tickflow.capabilities import Cap
        from app.tickflow.policy import detect_capabilities
        from app.tickflow.rate_limits import chunked, resolve_limit, sleep_between_batches
        from app.tickflow.client import get_paid_realtime_client

        tf = get_paid_realtime_client()
        if tf is None:
            logger.warning("自选实时拉取失败:未配置付费服务器 API Key")
            return "skip"

        # 按 capability batch 上限分批: 股票+指数共享额度, 超过上限会导致整轮失败
        capset = detect_capabilities()
        lim = resolve_limit(capset, Cap.QUOTE_BY_SYMBOL, default_batch=5)
        batches = chunked(symbols, lim.batch)

        t0 = time.perf_counter()
        now_ts = time.perf_counter()
        resp = []
        for i, batch in enumerate(batches):
            sleep_between_batches(i, lim.rpm)
            try:
                resp.extend(tf.quotes.get(symbols=batch) or [])
            except Exception as e:  # noqa: BLE001
                logger.warning("自选实时批次 %d/%d 拉取失败: %s", i + 1, len(batches), e)

        if not resp:
            logger.warning("自选实时行情数据为空")
            return "empty"

        records = []
        for q in resp:
            ext = q.get("ext") or {}
            last_price = q.get("last_price")
            prev_close = q.get("prev_close")
            change_amount = ext.get("change_amount")
            change_pct = ext.get("change_pct")
            if change_amount is None and last_price is not None and prev_close is not None:
                change_amount = float(last_price) - float(prev_close)
            if change_pct is None and change_amount is not None and prev_close not in (None, 0):
                # 小数制, 与 ext.change_pct / enriched 口径一致 (不乘 100)
                change_pct = float(change_amount) / float(prev_close)
            records.append({
                "symbol": q.get("symbol"),
                "name": q.get("name") or ext.get("name"),
                "last_price": last_price,
                "prev_close": prev_close,
                "open": q.get("open"),
                "high": q.get("high"),
                "low": q.get("low"),
                "volume": q.get("volume"),
                "amount": q.get("amount"),
                "change_pct": change_pct,
                "change_amount": change_amount,
                "amplitude": ext.get("amplitude"),
                "turnover_rate": ext.get("turnover_rate"),
                "timestamp": q.get("timestamp"),
                "session": q.get("session"),
            })

        self._process_watchlist_records(records, t0=t0, now_ts=now_ts)
        return "ok"


    # ================================================================
    # 工具
    # ================================================================

    @staticmethod
    def _split_records_by_asset(
        records: list[dict], index_set: set[str], etf_set: set[str],
    ) -> tuple[list[dict], list[dict], list[dict]]:
        """把行情 records 按资产拆成 (index, etf, stock)。判定顺序与 resolve_asset_type 一致: 先 ETF 后指数。"""
        index_records: list[dict] = []
        etf_records: list[dict] = []
        stock_records: list[dict] = []
        for r in records:
            sym = r.get("symbol")
            if sym in etf_set:
                etf_records.append(r)
            elif sym in index_set:
                index_records.append(r)
            else:
                stock_records.append(r)
        return index_records, etf_records, stock_records

    @staticmethod
    def _build_daily(records: list[dict]) -> pl.DataFrame:
        """将 API records 转为日K格式 DataFrame (OHLCV + quote_ts, 写 kline_daily 用)。"""
        if not records:
            return pl.DataFrame()
        df = pl.DataFrame(records)
        cols_map = {
            "symbol": "symbol",
            "last_price": "close",
            "open": "open",
            "high": "high",
            "low": "low",
            "volume": "volume",
            "amount": "amount",
            "timestamp": "quote_ts",
        }
        select_exprs = []
        for src, dst in cols_map.items():
            if src in df.columns:
                select_exprs.append(pl.col(src).cast(pl.Int64, strict=False).alias(dst)
                                     if dst == "quote_ts" else pl.col(src).alias(dst))
        if not select_exprs:
            return pl.DataFrame()
        result = df.select(select_exprs).with_columns(
            pl.lit(cn_today()).cast(pl.Date).alias("date"),
        )
        # 修复: API 在非交易时段可能返回 open/high/low=0 或 null,
        # 导致蜡烛从 0 开始。用 close 填充这些异常值。
        for col in ("open", "high", "low"):
            if col in result.columns:
                result = result.with_columns(
                    pl.when((pl.col(col) == 0) | pl.col(col).is_null())
                    .then(pl.col("close"))
                    .otherwise(pl.col(col))
                    .alias(col)
                )
        return result

    @staticmethod
    def _build_quote_extra(records: list[dict]) -> pl.DataFrame:
        """构建 API 直接提供的补充字段 (不写 daily, 只传给 enriched 计算)。

        包含: prev_close, change_pct, change_amount, amplitude, turnover_rate。
        """
        if not records:
            return pl.DataFrame()
        df = pl.DataFrame(records)
        keep = [c for c in [
            "symbol", "prev_close", "change_pct", "change_amount",
            "amplitude", "turnover_rate",
        ] if c in df.columns]
        if not keep or "symbol" not in keep:
            return pl.DataFrame()
        out = df.select(keep)
        # 实时 API 的 turnover_rate 入口契约为小数制(0.05 = 5%).
        # enriched 内部统一存百分数值(5 = 5%), 后续页面/筛选直接展示和比较。
        if "turnover_rate" in out.columns:
            out = out.with_columns((pl.col("turnover_rate").cast(pl.Float64, strict=False) * 100).alias("turnover_rate"))
        return out

    @staticmethod
    def _build_index_quotes(records: list[dict]) -> pl.DataFrame:
        """构建指数实时行情缓存，不落股票 parquet。

        注意: API 返回的 change_pct/amplitude 是小数 (0.0366 = 3.66%),
        统一转成百分比输出, 与 _fallback_index_quotes_from_daily 口径一致
        (前端指数侧不×100, 直接 toFixed(2)% 展示)。
        """
        if not records:
            return pl.DataFrame()
        df = pl.DataFrame(records)
        keep = [c for c in [
            "symbol", "name", "last_price", "prev_close", "open", "high", "low",
            "volume", "amount", "change_pct", "change_amount", "amplitude", "timestamp", "session",
        ] if c in df.columns]
        if not keep or "symbol" not in keep:
            return pl.DataFrame()
        df = df.select(keep)
        # 自定义源可能不提供 change_pct/change_amount, 按 last_price/prev_close 补算
        # (TickFlow 路径在 _fetch_full_market_quotes 已算好, 此处只补缺失的)
        if "change_pct" not in df.columns and "last_price" in df.columns and "prev_close" in df.columns:
            # prev_close=0 → inf (非合法 JSON), prev_close=null → null; 用 when 守护
            df = df.with_columns(
                pl.when(pl.col("prev_close") != 0)
                .then((pl.col("last_price") - pl.col("prev_close")) / pl.col("prev_close"))
                .otherwise(None)
                .alias("change_pct")
            )
        if "change_amount" not in df.columns and "last_price" in df.columns and "prev_close" in df.columns:
            df = df.with_columns(
                (pl.col("last_price") - pl.col("prev_close")).alias("change_amount")
            )
        # change_pct / amplitude: 小数 → 百分比 (统一指数展示口径)
        for col in ("change_pct", "amplitude"):
            if col in df.columns:
                df = df.with_columns((pl.col(col).cast(pl.Float64) * 100).alias(col))
        if "last_price" in df.columns and "close" not in df.columns:
            df = df.with_columns(pl.col("last_price").alias("close"))
        return df

    @staticmethod
    def _market_phase() -> str:
        """A股行情轮询阶段(北京时间)。

        final 阶段用于午休/收盘定版: 需要至少成功拉取一版边界后的行情, 才算进入休盘。
        """
        now = cn_now()
        if now.weekday() >= 5:
            return "closed"
        t = now.time()
        if dt_time(9, 15) <= t < dt_time(9, 30):
            return "preopen"
        if dt_time(9, 30) <= t < dt_time(11, 30):
            return "morning"
        if dt_time(11, 30) <= t < dt_time(12, 55):
            return "morning_final"
        if dt_time(12, 55) <= t < dt_time(13, 0):
            return "pre_afternoon"
        if dt_time(13, 0) <= t < dt_time(15, 0):
            return "afternoon"
        if t >= dt_time(15, 0):
            return "close_final"
        return "closed"

    @staticmethod
    def _final_sync_key(phase: str) -> tuple[date, str] | None:
        if phase == "morning_final":
            return (cn_today(), "morning")
        if phase == "close_final":
            return (cn_today(), "close")
        return None

    def _should_poll_for_phase(self, phase: str) -> bool:
        """是否处于会主动拉行情的阶段。final 阶段成功后即停止。"""
        if phase in {"preopen", "morning", "pre_afternoon", "afternoon"}:
            return True
        key = self._final_sync_key(phase)
        return bool(key and key not in self._final_sync_done)

    def _should_fetch_for_phase(self, phase: str) -> bool:
        return self._should_poll_for_phase(phase)

    def _is_trading_hours(self) -> bool:
        """行情轮询窗口(兼容旧调用): 包含盘前预热和未完成的午休/收盘定版。"""
        return self._should_poll_for_phase(self._market_phase())

    @staticmethod
    def _is_continuous_trading() -> bool:
        """A股连续竞价时段(北京时间): 9:30-11:30 / 13:00-15:00, 仅工作日。

        比 _is_trading_hours 严格: 排除 9:15-9:30 集合竞价(指示价, 非成交价)、
        午间与 15:00 后收盘缓冲。监控评估只在此窗口进行, 不对竞价/收盘后的陈旧价告警。
        (节假日由 _evaluate_monitors 里的「快照日期=当日」新鲜度判据兜底, 无需交易日历。)
        """
        now = cn_now()
        t = now.time()
        morning = dt_time(9, 30) <= t <= dt_time(11, 30)
        afternoon = dt_time(13, 0) <= t <= dt_time(15, 0)
        return now.weekday() < 5 and (morning or afternoon)

    @staticmethod
    def _save_enabled(enabled: bool) -> None:
        from app.services import preferences
        preferences.save({"realtime_quotes_enabled": enabled})

    # ================================================================
    # 策略监控
    # ================================================================

    def _evaluate_monitors(self, daily_df: pl.DataFrame, quote_extra: pl.DataFrame | None) -> None:
        """行情更新后评估统一监控规则引擎,并刷新策略结果缓存。"""
        try:
            # 仅在「交易日 + 连续竞价时段」评估监控 —— 避开集合竞价指示价、盘前/收盘后
            # 缓冲。轮询窗口(_is_trading_hours)更宽是为盘前预热/收盘捕捉, 但告警不应
            # 基于这些非连续竞价价格。
            fixture_mode = os.environ.get("PHASE1_FIXTURE_MODE", "").strip().lower() in {"1", "true", "yes"}
            if not fixture_mode and not self._is_continuous_trading():
                return
            # 获取 enriched 数据 (刚算好的)
            enriched_today, enriched_date = self.get_enriched_today()
            # 股票快照就绪 = 非空 + 日期为当日。未就绪时仅跳过股票轮,
            # ETF/指数轮有各自的空表+日期守卫, 不受影响 (纯指数行情/自选场景可独立评估)。
            # fixture 模式豁免日期判据 (验收夹具数据日期不一定是当日)。
            stock_ready = (not enriched_today.is_empty()) and (
                fixture_mode or enriched_date == cn_today())
            if not stock_ready:
                logger.debug("股票快照未就绪(空=%s, 日期=%s), 跳过股票轮",
                             enriched_today.is_empty(), enriched_date)

            all_alerts: list[dict] = []
            rule_events: list[dict] = []
            engine = None

            # 通用监控规则评估 (统一引擎: signal/price/market/strategy)
            if self._app_state:
                engine = getattr(self._app_state, "monitor_engine", None)
                if engine and engine.rule_count > 0:
                    # 预构建 symbol → name 映射 (enriched 已 drop name 列, 引擎触发时回填用)。
                    # 股票 + ETF + 指数三表合并走 _monitor_name_map -> repo.get_name_map()
                    # 的进程内 memo, 避免每轮监控对 ~7000 行维表 iter_rows 重建。
                    try:
                        name_map = _monitor_name_map(self._app_state.repo)
                        if name_map:
                            engine.set_name_map(name_map)
                    except Exception as e:  # noqa: BLE001
                        logger.debug("name_map 构建失败 (不影响监控): %s", e)
                    # 股票轮: 快照未就绪时跳过 (ladder 封单也依赖股票快照日期, 一并跳过)
                    if stock_ready:
                        eval_df = enriched_today
                        if engine.has_rule_type("ladder"):
                            eval_df = self._inject_sealed_vol(enriched_today, enriched_date)
                        eval_df = self._inject_intraday_signals(eval_df, engine, "stock")
                        rule_events = engine.evaluate(eval_df, asset_type="stock")
                        if engine.consume_strategy_result_updates():
                            self.notify_strategy_results_updated()
                    # 板块规则轮: 股票 enriched 快照 + 实时指数快照按板块聚合评估。
                    # 独立 try - 板块轮任何异常都不得丢弃本轮已算出的股票告警。
                    if engine.has_rule_type("sector"):
                        try:
                            index_df = self.get_index_quotes()
                            # 本仓库指数缓存 change_pct 为百分比 (3.66 = 3.66%),
                            # 板块聚合统一用小数口径 (与股票 enriched change_pct 一致)。
                            if not index_df.is_empty() and "change_pct" in index_df.columns:
                                index_df = index_df.with_columns(
                                    (pl.col("change_pct") / 100).alias("change_pct")
                                )
                            rule_events = rule_events + engine.evaluate_sectors(
                                enriched_today if stock_ready else pl.DataFrame(), index_df,
                            )
                        except Exception as e:  # noqa: BLE001
                            logger.warning("板块监控评估失败 (不影响通用规则): %s", e)
                    # ETF 规则轮: 股票快照不含 ETF, 用 ETF enriched 快照单独评估。
                    # 独立 try —— ETF 轮任何异常都不得丢弃本轮已算出的股票告警。
                    # refresh=False —— 不在轮询线程上触发 ETF 冷缓存的同步重算 (缓存由 ETF 实时
                    # flush 焐热; 未焐热说明无 ETF 实时数据, 跳过本轮 ETF 评估)。
                    if engine.has_asset_rules("etf") and self._repo is not None:
                        try:
                            etf_enriched, _ = self._repo.get_enriched_latest_asset("etf", refresh=False)
                            if not etf_enriched.is_empty():
                                etf_enriched = self._inject_intraday_signals(etf_enriched, engine, "etf")
                                rule_events = rule_events + engine.evaluate(
                                    etf_enriched, asset_type="etf", reset_strategy_results=False,
                                )
                        except Exception as e:  # noqa: BLE001
                            logger.warning("ETF 监控评估失败 (不影响股票告警): %s", e)
                    # 指数规则轮: 复刻 ETF 轮。快照由指数实时 flush 焐热;
                    # refresh=False 冷缓存不同步重算; 显式日期守卫防陈旧 parquet 误告警
                    # (ETF 轮靠空表隐式跳过, 指数轮更显式, 行为等价)。
                    if engine.has_asset_rules("index") and self._repo is not None:
                        try:
                            index_enriched, index_date = self._repo.get_enriched_latest_asset("index", refresh=False)
                            if not index_enriched.is_empty() and index_date == cn_today():
                                index_enriched = self._inject_intraday_signals(index_enriched, engine, "index")
                                rule_events = rule_events + engine.evaluate(
                                    index_enriched, asset_type="index", reset_strategy_results=False,
                                )
                        except Exception as e:  # noqa: BLE001
                            logger.warning("指数监控评估失败 (不影响股票/ETF 告警): %s", e)
                    if rule_events:
                        rule_events = self._format_extension_notifications(rule_events)
                    # Generic rules consume the deduplicated quote frame above. Position rules
                    # run afterwards against one explicit, shared-quote valuation per holding.
                    if engine.has_rule_type("position"):
                        try:
                            portfolio_service = getattr(self._app_state, "portfolio_service", None)
                            valued_positions = portfolio_service.valued_positions() if portfolio_service else []
                            projection = [
                                {
                                    "position_id": position["position_id"],
                                    "account_id": position["account_id"],
                                    "symbol": position["instrument_symbol"],
                                    "close": float(position["market_value"]) / float(position["quantity"]),
                                    "valuation_source": position["source"],
                                    "valuation_as_of": position["as_of"],
                                }
                                for position in valued_positions
                                if position.get("market_value") is not None and float(position["quantity"]) > 0
                            ]
                            if projection:
                                rule_events.extend(engine.evaluate_positions(pl.DataFrame(projection)))
                        except Exception as e:  # noqa: BLE001
                            logger.warning("持仓监控评估失败 (不影响通用规则): %s", e)
                    if rule_events:
                        # Durable operational history is the authoritative handoff boundary:
                        # no event is broadcast or delivered until its immutable snapshot exists.
                        operational = getattr(self._app_state, "operational", None)
                        persisted_events: list[dict] = []
                        if operational is None:
                            logger.error("告警未持久化: operational repository 未初始化")
                        else:
                            for event in rule_events:
                                try:
                                    persisted = operational.record_alert_event(event)
                                    event["id"] = persisted["id"]
                                    event["occurred_at"] = persisted["occurred_at"]
                                    persisted_events.append(event)
                                except Exception as e:  # noqa: BLE001
                                    logger.warning("告警持久化失败,跳过广播和投递: %s", e)
                        rule_events = persisted_events
                    if rule_events:
                        # 转为 SSE 推送格式 (兼容旧 alert schema)
                        for ev in rule_events:
                            alert = {
                                "id": ev["id"],
                                "occurred_at": ev["occurred_at"],
                                "source": ev["source"],
                                "type": ev["type"],
                                "rule_id": ev.get("rule_id"),
                                "strategy_id": ev.get("strategy_id") if ev["source"] == "strategy" else None,
                                "symbol": ev["symbol"],
                                "name": ev["name"],
                                "message": ev["message"],
                                "price": ev["price"],
                                "change_pct": ev["change_pct"],
                                "signals": ev["signals"],
                                "severity": ev.get("severity", "info"),
                                "conditions": ev.get("conditions") or [],
                                "logic": ev.get("logic") or "and",
                                "account_id": ev.get("account_id"),
                                "position_id": ev.get("position_id"),
                                "valuation_source": ev.get("valuation_source"),
                                "valuation_as_of": ev.get("valuation_as_of"),
                            }
                            for key in (
                                "sector_kind", "sector_key", "sector_name",
                                "sector_source_field", "sector_value", "sector_level",
                                "window_change_pct", "coverage_ratio", "valid_count",
                                "total_count", "up_count", "down_count", "leader",
                            ):
                                if key in ev:
                                    alert[key] = ev[key]
                            all_alerts.append(alert)

            # 策略页实时回显: 不写文件 (实时行情每轮更新 enriched, 写文件会被 read_cache
            # 的 mtime 校验判过期, 反复读不到)。监控引擎本轮已算出的结果存在内存
            # (latest_strategy_results), 由 /api/screener/cached 端点直接叠加读取。

            # 广播到所有 SSE 订阅者 (背压保护在订阅者队列内做)
            if all_alerts:
                # 按 symbol 富化行业/概念 ext 字段, 使 toast + 触发记录统一展示板块标签。
                self._enrich_alerts_ext(all_alerts)
                self._broadcast_alerts(all_alerts)
                logger.info("监控评估完成: %d 条通知", len(all_alerts))

                # 系统通知 (可选通道, 由 preferences 开关控制)。
                # cooldown 去重已在 MonitorRuleEngine 做过, 这里只负责转发。
                self._maybe_send_system_notifications(all_alerts)

            # Webhook 推送 (飞书等外部 IM, 由规则 webhook_channels 指定渠道)。
            # 紧随系统通知, 同样静默降级不阻断主流程。
            if rule_events:
                self._maybe_send_webhook(rule_events, engine)

        except Exception as e:  # noqa: BLE001
            logger.warning("监控评估失败: %s", e)

    # ================================================================
    # 盘前告警评估 (MON-03) — 09:26 盘前预览 job 尾段的唯一触发点
    # ================================================================

    def evaluate_premarket_alerts(self, payload: dict) -> dict:
        """盘前告警评估 + 持久化 + SSE + 飞书 (MON-03)。零盘中耦合。

        仅由 09:26 盘前预览 job 尾段 (daily_pipeline._premarket_pool_preview)
        触发 — 与盘中 _evaluate_monitors 互斥 (09:26 ∉ 连续竞价窗口): 无时间 gate
        (不调 _is_continuous_trading), 评估窗口由调度器独占, 盘中轮询线程经
        evaluate() 跳过集 {position, preopen} 天然隔离。

        序列镜像 _evaluate_monitors 的持久化优先 (record_alert_event 落库成功才
        广播/投递; 落库失败跳过广播 — 不可审计事件不出现在 SSE/投递面); operational
        未初始化 → 降级 alert_store.append_many (jsonl 写路径) + 跳过投递。
        """
        engine = getattr(self._app_state, "monitor_engine", None)
        if engine is None:
            return {"skipped": "no monitor engine"}
        if not payload or not payload.get("available"):
            return {"skipped": "preview unavailable", "degraded": True}

        events = engine.evaluate_premarket(payload)

        # 持久化优先 (镜像 _evaluate_monitors): 落库成功才广播/投递
        operational = getattr(self._app_state, "operational", None)
        persisted: list[dict] = []
        if operational is None:
            logger.error("告警未持久化: operational repository 未初始化")
            from app.services import alert_store
            alert_store.append_many(self._app_state.repo.store.data_dir, events)
            persisted = events  # 降级写路径 (jsonl): 仍广播, 跳过投递
        else:
            for ev in events:
                try:
                    persisted_ev = operational.record_alert_event(ev)
                    ev["id"] = persisted_ev["id"]
                    ev["occurred_at"] = persisted_ev["occurred_at"]
                    persisted.append(ev)
                except Exception as e:  # noqa: BLE001
                    logger.warning("盘前告警持久化失败,跳过广播和投递: %s", e)

        if persisted:
            self._broadcast_alerts([self._preopen_sse_shape(ev) for ev in persisted])
            self._maybe_send_webhook(persisted, engine)

        return {
            "rules": engine.rule_count,
            "events": len(persisted),
            "degraded": bool(payload.get("degraded")),
            "probe_status": (payload.get("probe") or {}).get("status"),
        }

    @staticmethod
    def _preopen_sse_shape(ev: dict) -> dict:
        """盘前告警 SSE 形状: 既有 SSE 键集 + preopen 增量键 (纯增量, 旧客户端忽略未知键)。

        与 _evaluate_monitors 的 SSE dict 组装键集逐键一致, 另追加 window/provisional/
        degraded/probe/strategy_ids/preopen_metrics (MON-03/04) — 兼容旧客户端。
        """
        return {
            "id": ev["id"],
            "occurred_at": ev["occurred_at"],
            "source": ev["source"],
            "type": ev["type"],
            "rule_id": ev.get("rule_id"),
            "strategy_id": ev.get("rule_id") if ev["source"] == "strategy" else None,
            "symbol": ev["symbol"],
            "name": ev["name"],
            "message": ev["message"],
            "price": ev["price"],
            "change_pct": ev["change_pct"],
            "signals": ev["signals"],
            "severity": ev.get("severity", "info"),
            "conditions": ev.get("conditions") or [],
            "logic": ev.get("logic") or "and",
            "account_id": ev.get("account_id"),
            "position_id": ev.get("position_id"),
            "valuation_source": ev.get("valuation_source"),
            "valuation_as_of": ev.get("valuation_as_of"),
            # ── preopen 增量键 (MON-03/04): 旧客户端忽略未知键, 兼容 ──
            "window": ev.get("window"),
            "provisional": ev.get("provisional"),
            "degraded": ev.get("degraded"),
            "probe": ev.get("probe"),
            "strategy_ids": ev.get("strategy_ids"),
            "preopen_metrics": ev.get("preopen_metrics"),
        }
    def _format_extension_notifications(self, events: list[dict]) -> list[dict]:
        """Apply optional copy formatters after evaluation and before every output channel."""
        registry = (
            getattr(self._app_state, "extension_registry", None)
            if self._app_state is not None
            else None
        )
        if registry is None or not registry.has_notification_formatters:
            return events

        from app.extensions.contracts import (
            BACKEND_EXTENSION_API_VERSION,
            NotificationFormatContext,
        )

        formatted_events: list[dict] = []
        for event in events:
            formatted = dict(event)
            context = NotificationFormatContext(
                api_version=BACKEND_EXTENSION_API_VERSION,
            )
            for registered in registry.notification_formatters():
                try:
                    message = registered.implementation.format_message(dict(formatted), context)
                    if not isinstance(message, str):
                        raise TypeError("notification formatter must return str")
                    formatted["message"] = message
                except Exception as exc:
                    logger.warning(
                        "notification formatter failed %s: %s",
                        registered.implementation_id,
                        exc,
                    )
            formatted_events.append(formatted)
        return formatted_events

    def _enrich_alerts_ext(self, alerts: list[dict]) -> None:
        """就地给告警事件按 symbol 追加行业/概念 ext 字段。

        读 preferences.get_monitor_ext_fields() 取字段配置, 用 screener._load_ext_value_maps
        (带 parquet mtime 缓存) 富化。富化失败静默降级 (告警照常推送, 只是没标签)。
        每条事件新增 {configId}__{fieldName} 键 (与 watchlist/screener 输出约定一致)。
        """
        if not alerts or not self._app_state or self._repo is None:
            return
        try:
            from app.services import preferences
            fields = preferences.get_monitor_ext_fields()
            # 新结构 {field, maxTags, hiddenIndices}, 后端只需 .field
            parts = []
            for key in ("concept", "industry"):
                item = fields.get(key)
                if isinstance(item, dict) and item.get("field"):
                    parts.append(item["field"])
                elif isinstance(item, str) and item:
                    parts.append(item)  # 兼容旧格式
            if not parts:
                return
            ext_columns = ",".join(parts)
            from app.api.screener import _load_ext_value_maps
            value_maps = _load_ext_value_maps(self._repo, ext_columns)
            if not value_maps:
                return
            for ev in alerts:
                sym = ev.get("symbol")
                if not sym:
                    continue
                for out_col, vmap in value_maps.items():
                    ev[out_col] = vmap.get(str(sym))
        except Exception as e:  # noqa: BLE001
            logger.debug("告警 ext 富化失败 (不影响推送): %s", e)

    def _inject_intraday_signals(self, enriched: pl.DataFrame, engine, asset_type: str) -> pl.DataFrame:
        """每分钟为分时信号规则批量获取一次数据并注入临时布尔列。"""
        get_symbols = getattr(engine, "intraday_signal_symbols", None)
        if not callable(get_symbols):
            return enriched
        symbols = get_symbols(asset_type)
        if not symbols:
            return enriched

        now = cn_now()
        bucket = now.strftime("%Y%m%d%H%M")
        if self._intraday_signal_bucket.get(asset_type) == bucket:
            return self._intraday_signal_evaluator.inject(enriched, [])
        self._intraday_signal_bucket[asset_type] = bucket

        from app.services.kline_sync import (
            fetch_intraday_monitor_batch,
            intraday_monitor_support,
        )

        capset = getattr(self._app_state, "capabilities", None)
        support = intraday_monitor_support(capset)
        if not support["available"] or len(symbols) > int(support["max_symbols"]):
            return self._intraday_signal_evaluator.inject(enriched, [])

        minute_df = fetch_intraday_monitor_batch(sorted(symbols), capset, now=now)
        prev_close: dict[str, float] = {}
        available_cols = set(enriched.columns)
        for row in enriched.filter(pl.col("symbol").is_in(sorted(symbols))).iter_rows(named=True):
            symbol = str(row.get("symbol") or "")
            reference = row.get("prev_close") if "prev_close" in available_cols else None
            if reference is None and "close" in available_cols and "change_pct" in available_cols:
                close = row.get("close")
                change_pct = row.get("change_pct")
                if close is not None and change_pct is not None and float(change_pct) > -1:
                    reference = float(close) / (1.0 + float(change_pct))
            if symbol and reference is not None:
                prev_close[symbol] = float(reference)

        signals = self._intraday_signal_evaluator.evaluate(
            minute_df,
            symbols=symbols,
            prev_close=prev_close,
            asset_type=asset_type,
            now=now,
        )
        return self._intraday_signal_evaluator.inject(enriched, signals)

    def _inject_sealed_vol(self, enriched_today: pl.DataFrame, enriched_date) -> pl.DataFrame:
        """从 depth_service 取封单量, 作为临时列 _sealed_vol 注入 enriched 副本。

        涨停封单(买一量) + 跌停封单(卖一量)合并, 供 ladder 规则评估。
        depth 未就绪时返回原 df (不注入, ladder 规则安全降级不触发)。
        """
        try:
            depth_svc = getattr(self._app_state, "depth_service", None)
            if not depth_svc:
                return enriched_today
            # enriched_date 可能是 date 或字符串, 统一为 date
            from datetime import date as date_cls
            target_date = enriched_date if isinstance(enriched_date, date_cls) else date_cls.fromisoformat(str(enriched_date))
            # 取涨停 + 跌停封单, 合并 {symbol: vol}
            up_map = depth_svc.get_sealed_map(target_date, is_down=False)
            down_map = depth_svc.get_sealed_map(target_date, is_down=True)
            sealed: dict[str, int] = {}
            for m in (up_map, down_map):
                for sym, info in m.items():
                    vol = (info or {}).get("vol")
                    if vol and vol > 0:
                        sealed[sym] = vol  # 后者覆盖前者 (同 symbol 不可能在涨跌停都封单)
            if not sealed:
                return enriched_today
            # 构造 (symbol, _sealed_vol) DataFrame, join 到 enriched 副本
            sealed_df = pl.DataFrame({
                "symbol": list(sealed.keys()),
                "_sealed_vol": list(sealed.values()),
            })
            # 若已有残留列先移除 (避免重复 join 报错)
            df = enriched_today.drop("_sealed_vol") if "_sealed_vol" in enriched_today.columns else enriched_today
            return df.join(sealed_df, on="symbol", how="left")
        except Exception as e:  # noqa: BLE001
            logger.debug("封单注入失败 (ladder 规则将不触发): %s", e)
            return enriched_today

    def _maybe_send_webhook(self, rule_events: list[dict], engine) -> None:
        """Enqueue approved, durable Feishu and Telegram delivery after SSE fan-out."""
        try:

            from app.notifications.delivery import DeliveryConfig
            from app.services import preferences

            delivery_service = getattr(self._app_state, "notification_delivery", None)
            if delivery_service is None:
                return
            fixture_mode = os.environ.get("PHASE1_FIXTURE_MODE", "").strip().lower() in {"1", "true", "yes"}
            configured = preferences.load()
            rules = engine.rules if engine is not None else {}
            for event in rule_events:
                rule = rules.get(event.get("rule_id")) or {}
                requested = set(rule.get("webhook_channels") or [])
                channel_configs: list[DeliveryConfig] = []
                if fixture_mode:
                    if "feishu" in requested:
                        channel_configs.append(DeliveryConfig(
                            channel="feishu",
                            config={"fixture_url": os.environ.get("PHASE1_FEISHU_RECEIVER_URL", "")},
                        ))
                    if "telegram" in requested:
                        channel_configs.append(DeliveryConfig(
                            channel="telegram",
                            config={"fixture_url": os.environ.get("PHASE1_TELEGRAM_RECEIVER_URL", "")},
                        ))
                else:
                    feishu_url = preferences.get_feishu_webhook_url()
                    if "feishu" in requested and feishu_url:
                        channel_configs.append(DeliveryConfig(
                            channel="feishu",
                            config={"webhook": feishu_url, "secret": preferences.get_feishu_webhook_secret()},
                        ))
                    telegram_token = str(configured.get("telegram_bot_token") or "").strip()
                    telegram_chat_id = str(configured.get("telegram_chat_id") or "").strip()
                    if "telegram" in requested and telegram_token and telegram_chat_id:
                        channel_configs.append(DeliveryConfig(
                            channel="telegram",
                            config={"bot_token": telegram_token, "chat_id": telegram_chat_id},
                        ))
                if not channel_configs:
                    continue
                delivery_service.enqueue(
                    event_id=event["id"],
                    channel_configs=channel_configs,
                    quiet_period=bool(configured.get("notification_quiet_period", False)),
                    bypass_quiet_period=(
                        event.get("severity") == "critical"
                        and bool(rule.get("bypass_quiet_period", False))
                    ),
                )
        except Exception as error:  # noqa: BLE001 - delivery must not escape monitor evaluation
            logger.warning("notification delivery enqueue failed: %s", error)

    def _maybe_send_system_notifications(self, all_alerts: list[dict]) -> None:
        """把告警转发到操作系统通知中心 (由 preferences 开关控制)。

        - 开关关闭: 直接返回
        - 开关开启: 逐条发系统通知; 失败静默, 不阻断主流程
        - 去重: 复用 MonitorRuleEngine 的 cooldown, 此处不重复去重
        - 批量策略事件 (symbol="") 聚合为一条通知, 避免刷屏
        """
        try:
            from app.services import preferences
            from app.services import notify_adapter

            if not preferences.get_system_notify_enabled():
                return

            for ev in all_alerts:
                # 通知标题: 用 source 分类 (策略/信号/价格/异动)
                source = ev.get("source", "")
                source_label = {
                    "strategy": "策略", "signal": "信号",
                    "price": "价格", "market": "异动", "sector": "板块",
                    "ladder": "连板梯队",
                }.get(source, source or "通知")

                name = ev.get("name") or ""
                symbol = ev.get("symbol") or ""
                message = ev.get("message") or ""

                # 正文: 优先用现成 message, 拼上 symbol/name 让用户一眼定位
                if symbol:
                    body = f"{symbol} {name} {message}".strip()
                else:
                    body = message or name

                title = f"AthenaQuant · {source_label}"
                notify_adapter.notify(title, body)
        except Exception as e:  # noqa: BLE001
            logger.debug("系统通知发送异常 (不影响告警主流程): %s", e)

    @staticmethod
    def _get_strategy_monitor():
        """获取 StrategyMonitorService — 不再使用, 改用 _app_state 注入。"""
        return None

    # ================================================================
    # enriched 增量计算
    # ================================================================

    def _flush_live_enriched(self, daily_df: pl.DataFrame, quote_extra: pl.DataFrame = None, asset_type: str = "stock", merge: bool = False) -> None:
        """增量计算今天的 enriched: 用昨天的递推状态 + 今天 OHLCV → 只算今天 5500 行。

        quote_extra: API 直接提供的补充字段 (prev_close, change_pct 等),
                     不写 daily, 直接传给 compute_enriched_today 避免重复计算。
        """
        try:
            today = cn_today()
            t0 = time.perf_counter()

            # ---- 尝试增量路径 ----
            live_agg = self._repo.get_live_agg() if asset_type == "stock" else pl.DataFrame()
            prev_enriched, prev_date = (
                self._repo.get_enriched_latest()
                if asset_type == "stock"
                else self._repo.get_enriched_latest_asset(asset_type)
            )

            use_incremental = (
                asset_type == "stock"
                and not live_agg.is_empty()
                and not prev_enriched.is_empty()
                and prev_date is not None
            )

            if use_incremental:
                from app.indicators.pipeline import compute_enriched_today
                from app.market_time import trading_minutes_elapsed_from_ts, trading_minutes_elapsed
                instruments = self._repo.get_instruments()
                # 将 API 直接提供的补充字段 JOIN 到 daily_df
                today_ohlcv = daily_df
                if quote_extra is not None and not quote_extra.is_empty():
                    today_ohlcv = daily_df.join(quote_extra, on="symbol", how="left")
                # 量比时间折算: 优先用行情 quote_ts (真实成交时间), 缺失则兜底服务端时间
                elapsed_minutes: float | None = None
                if "quote_ts" in daily_df.columns and not daily_df.is_empty():
                    valid_ts = daily_df["quote_ts"].drop_nulls()
                    if not valid_ts.is_empty():
                        elapsed_minutes = trading_minutes_elapsed_from_ts(valid_ts.median())
                if elapsed_minutes is None:
                    elapsed_minutes = trading_minutes_elapsed()
                enriched_today = compute_enriched_today(
                    live_agg=live_agg,
                    prev_enriched=prev_enriched,
                    today_ohlcv=today_ohlcv,
                    instruments=instruments,
                    elapsed_minutes=elapsed_minutes,
                )
                if enriched_today.is_empty():
                    logger.warning("增量计算结果为空, 回退到全量计算")
                    use_incremental = False

            # ---- 全量回退路径 ----
            if not use_incremental:
                from datetime import timedelta
                from app.indicators.pipeline import compute_enriched

                logger.info("enriched 全量计算 (live_agg=%s, 上次日期=%s)",
                            "ok" if not live_agg.is_empty() else "空", prev_date)

                cutoff = today - timedelta(days=90)
                table = {"etf": "kline_etf_daily", "index": "kline_index_daily"}.get(asset_type, "kline_daily")
                daily_glob = str(self._repo.store.data_dir / table / "**" / "*.parquet")
                ohlcv_cols = ["symbol", "date", "open", "high", "low", "close", "volume", "amount", "quote_ts"]
                hist_df = (
                    scan_daily_parquet(daily_glob)
                    .filter(pl.col("date") >= cutoff)
                    .sort(["symbol", "date"])
                    .collect()
                )
                if hist_df.is_empty():
                    return

                hist_cols = [c for c in ohlcv_cols if c in hist_df.columns]
                hist_df = hist_df.select(hist_cols).filter(pl.col("date") != today)
                daily_ohlcv = daily_df.select([c for c in ohlcv_cols if c in daily_df.columns])
                full_df = pl.concat([hist_df, daily_ohlcv], how="diagonal_relaxed")
                full_df = full_df.sort(["symbol", "date"])

                factor_dir = {"stock": "adj_factor", "etf": "adj_factor_etf"}.get(asset_type)
                factor_path = self._repo.store.data_dir / factor_dir / "all.parquet" if factor_dir else None
                factors = pl.DataFrame()
                if factor_path and factor_path.exists():
                    try:
                        factors = pl.read_parquet(factor_path)
                    except Exception:
                        pass
                instruments = self._repo.get_instruments() if asset_type == "stock" else None

                enriched_full = compute_enriched(
                    full_df,
                    factors=factors,
                    instruments=instruments,
                    historical_shares=(
                        self._repo.get_historical_shares()
                        if asset_type == "stock"
                        else None
                    ),
                )
                enriched_today = enriched_full.filter(pl.col("date") == today)

            if enriched_today.is_empty():
                return

            # ---- 写盘 + 更新缓存 ----
            if merge:
                self._repo.merge_live_enriched_asset(asset_type, enriched_today)
            else:
                self._repo.flush_live_enriched_asset(asset_type, enriched_today)

            elapsed = time.perf_counter() - t0
            mode_label = "增量" if use_incremental else "全量"
            logger.info("enriched %s: %d 只, %s, 耗时 %.0fms",
                        mode_label, len(enriched_today), today, elapsed * 1000)
        except Exception as e:  # noqa: BLE001
            logger.warning("enriched 计算失败: %s", e)
