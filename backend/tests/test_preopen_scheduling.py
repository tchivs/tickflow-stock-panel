"""MON-03 — 盘前告警调度接线 (09:26 job 尾段 → evaluate_premarket_alerts → 持久化 → SSE → 投递)。

Task 1 (tracer): MON-03 垂直切片 —
- T12 尾段接线: persist 后同 _run_tracked 单飞内恰一次调用 ``evaluate_premarket_alerts(payload)``,
  传参是**内存 payload 同一对象** (免二次读盘); job result 含 ``preopen_eval`` 键。
- T16 集成: ``QuoteService.evaluate_premarket_alerts`` — 落库 (operational.record_alert_event) →
  SSE (``_preopen_sse_shape`` 增量键) → 投递 (webhook enqueue) 全链; 降级路径
  (operational=None → alert_store.append_many + SSE 仍广播 + 投递跳过)。
- skip 语义: engine 缺失 → ``{skipped: "no monitor engine"}``; payload 非 available →
  ``{skipped: "preview unavailable", degraded: True}``; 均不崩溃。

fixture 复用 test_premarket_pool._FakeRepo/_make_app_state 形 (本文件内自建, 不跨模块
import 其他测试模块); 生产 import 放测试函数内 (hermetic)。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import polars as pl

FIXED_DATE = date(2026, 8, 6)


class _FakeRepo:
    """最小 repo 桩 (与 test_premarket_pool._FakeRepo 同型)。"""

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


def _make_app_state_with_quoteservice(tmp_path: Path, latest, qs) -> SimpleNamespace:
    """扩展 _make_app_state 形 (test_premarket_pool): fake repo + quote_service 属性。

    quote_service 供 _premarket_pool_preview 尾段 (MON-03) 消费; 其余测试直接
    monkeypatch ``premarket_pool.build_premarket_preview``, 不需要真实策略引擎。
    """
    as_of = latest or FIXED_DATE
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
    repo = _FakeRepo(tmp_path, enriched, latest, instruments)
    return SimpleNamespace(repo=repo, strategy_engine=None, quote_service=qs)


def _preopen_payload(degraded: bool = False, probe: dict | None = None) -> dict:
    """一份可评估的盘前预览 payload: available:true, 1 策略 2 行, 仅 000001.SZ 命中 open_gap>=0.05。"""
    return {
        "as_of": FIXED_DATE.isoformat(),
        "available": True,
        "window": "pre_open",
        "computed_at": "2026-08-06T09:26:00",
        "provisional": True,
        "degraded": degraded,
        "probe": probe or {"status": "available", "source": "live", "probed_at": "2026-08-06T09:26:00"},
        "strategy_version": "fingerprint-abc",
        "results": {
            "auction_bullish": {
                "total": 2,
                "as_of": FIXED_DATE.isoformat(),
                "rows": [
                    {"symbol": "000001.SZ", "name": "平安银行", "code": "000001",
                     "open_gap": 0.08, "auction_volume": 100},
                    {"symbol": "600000.SH", "name": "浦发银行", "code": "600000",
                     "open_gap": 0.02, "auction_volume": 50},
                ],
            }
        },
    }


def _preopen_rule() -> dict:
    """一条 preopen 规则: open_gap >= 0.05, scope=all, feishu 投递, 无冷却。"""
    return {
        "id": "mr_preopen_gap5",
        "name": "盘前高开预警",
        "type": "preopen",
        "enabled": True,
        "asset_type": "stock",
        "scope": "all",
        "logic": "and",
        "conditions": [{"field": "open_gap", "op": ">=", "value": 0.05}],
        "cooldown_seconds": 0,
        "severity": "warn",
        "webhook_channels": ["feishu"],
    }


class _RecordingSubscriber:
    """记录 push_alerts 的 SSE 订阅者桩 (镜像 test_notification_delivery._RecordingSubscriber)。"""

    def __init__(self):
        self.alerts: list[list[dict]] = []

    def push_alerts(self, alerts: list[dict]) -> None:
        self.alerts.append(alerts)


# ================================================================
# T12 — 尾段接线: persist 后单飞内恰一次 evaluate_premarket_alerts(内存 payload)
# ================================================================


def test_premarket_tail_hook_evaluates_in_memory_payload_after_persist(tmp_path, monkeypatch):
    """T12 尾段接线: persist 之后恰一次调用, 传参是内存 payload 同一对象 (免二次读盘)。"""
    from app.jobs import daily_pipeline
    from app.services import premarket_pool, premarket_snapshot

    calls: list[tuple[str, dict]] = []
    qs = SimpleNamespace(
        evaluate_premarket_alerts=lambda payload: calls.append(("eval", payload)) or {"events": 1},
    )
    app_state = _make_app_state_with_quoteservice(tmp_path, latest=FIXED_DATE, qs=qs)
    monkeypatch.setattr(daily_pipeline, "_get_app_state", lambda: app_state)
    monkeypatch.setattr(daily_pipeline, "cn_today", lambda: FIXED_DATE)

    payload = _preopen_payload()
    monkeypatch.setattr(premarket_pool, "build_premarket_preview", lambda *a, **k: payload)

    def _fake_persist(data_dir, as_of, p):
        calls.append(("persist", p))

    monkeypatch.setattr(premarket_snapshot, "persist_premarket_snapshot", _fake_persist)

    result = daily_pipeline._premarket_pool_preview()

    assert result["preopen_eval"] == {"events": 1}
    # persist 先于 eval (同一 _run_tracked 单飞内), 两者收到的是同一内存 payload 对象
    assert [kind for kind, _ in calls] == ["persist", "eval"]
    assert calls[0][1] is payload
    assert calls[1][1] is payload


# ================================================================
# T13 — available:false → 不评估不告警 (诚实 skip)
# ================================================================


def test_premarket_tail_hook_skips_when_unavailable(tmp_path, monkeypatch):
    """T13 available:false → 不调 evaluate_premarket_alerts, 不落盘, 不追加 preopen_eval 键。"""
    from app.jobs import daily_pipeline
    from app.services import premarket_pool, premarket_snapshot

    eval_calls: list = []
    qs = SimpleNamespace(evaluate_premarket_alerts=lambda payload: eval_calls.append(payload) or {})
    app_state = _make_app_state_with_quoteservice(tmp_path, latest=FIXED_DATE, qs=qs)
    monkeypatch.setattr(daily_pipeline, "_get_app_state", lambda: app_state)
    monkeypatch.setattr(daily_pipeline, "cn_today", lambda: FIXED_DATE)

    payload = _preopen_payload()
    payload["available"] = False
    monkeypatch.setattr(premarket_pool, "build_premarket_preview", lambda *a, **k: payload)

    persist_calls: list = []
    monkeypatch.setattr(
        premarket_snapshot, "persist_premarket_snapshot",
        lambda data_dir, as_of, p: persist_calls.append(p),
    )

    result = daily_pipeline._premarket_pool_preview()

    assert eval_calls == []          # 不评估
    assert persist_calls == []       # 不落盘
    assert "preopen_eval" not in result
    assert result["as_of"] == "2026-08-06"
    assert result["strategies"] == 1
    assert result["degraded"] is False


# ================================================================
# T14 — 评估失败非致命: 预览 persist 仍成功 + job 正常返回
# ================================================================


def test_premarket_tail_hook_failure_is_non_fatal(tmp_path, monkeypatch):
    """T14 评估异常 → 预览 persist 成功、job 返回成功 dict + preopen_eval.skipped == "evaluation error"。"""
    from app.jobs import daily_pipeline
    from app.services import premarket_pool

    def _boom(payload):
        raise RuntimeError("boom")

    qs = SimpleNamespace(evaluate_premarket_alerts=_boom)
    app_state = _make_app_state_with_quoteservice(tmp_path, latest=FIXED_DATE, qs=qs)
    monkeypatch.setattr(daily_pipeline, "_get_app_state", lambda: app_state)
    monkeypatch.setattr(daily_pipeline, "cn_today", lambda: FIXED_DATE)

    payload = _preopen_payload()
    monkeypatch.setattr(premarket_pool, "build_premarket_preview", lambda *a, **k: payload)

    result = daily_pipeline._premarket_pool_preview()  # 不应上抛

    part = tmp_path / "premarket_results" / f"date={FIXED_DATE}" / "part.json"
    assert part.exists(), "评估失败不阻断预览持久化"
    assert result["as_of"] == "2026-08-06"
    assert result["strategies"] == 1
    assert result["preopen_eval"] == {"skipped": "evaluation error"}


# ================================================================
# T11 — 注册形锁死 (grep 门禁, 镜像 test_premarket_pool) — MON-03
# ================================================================


def test_premarket_job_registration_shape_locked():
    """T11 注册形: 常量/单飞/mon-fri cron 存在, 且尾段接线未新增第二个 premarket job。"""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "app" / "jobs" / "daily_pipeline.py"
    text = src.read_text(encoding="utf-8")

    assert '_PREMARKET_JOB_ID = "premarket_pool_preview"' in text
    assert "_PREMARKET_HOUR, _PREMARKET_MINUTE = 9, 26" in text
    assert "_run_tracked(_premarket_pool_preview" in text
    assert "hour=_PREMARKET_HOUR, minute=_PREMARKET_MINUTE" in text
    assert 'timezone="Asia/Shanghai"' in text
    assert "id=_PREMARKET_JOB_ID" in text
    # 尾段接线不改注册: 仍只有 1 个盘前 job (单飞包装 + 注册各出现恰一次)
    assert text.count("id=_PREMARKET_JOB_ID") == 1
    assert text.count("_run_tracked(_premarket_pool_preview") == 1


# ================================================================
# T15 — 时间无重叠: 09:26 ∉ 连续竞价窗口; 与 EOD 默认不同域 — MON-03
# ================================================================


def test_premarket_time_no_overlap_with_intraday_and_eod():
    """T15 09:26 不在连续竞价 [9:30,11:30]∪[13:00,15:00], 与 EOD 默认 (15,30) 不同域。"""
    from datetime import time as dt_time

    from app.jobs.daily_pipeline import (
        _PREMARKET_HOUR,
        _PREMARKET_JOB_ID,
        _PREMARKET_MINUTE,
    )

    morning = (dt_time(9, 30), dt_time(11, 30))
    afternoon = (dt_time(13, 0), dt_time(15, 0))
    t = dt_time(_PREMARKET_HOUR, _PREMARKET_MINUTE)
    assert not (morning[0] <= t <= morning[1])
    assert not (afternoon[0] <= t <= afternoon[1])
    # EOD 偏好默认 15:30 (偏移域不同): 常量存在且不等于 (15, 30)
    assert (_PREMARKET_HOUR, _PREMARKET_MINUTE) != (15, 30)
    assert _PREMARKET_JOB_ID == "premarket_pool_preview"


# ================================================================
# T16 — QuoteService.evaluate_premarket_alerts 集成: 落库 → SSE → 投递
# ================================================================


def test_evaluate_premarket_alerts_persist_sse_webhook_chain(tmp_path, monkeypatch):
    """T16 集成: 事件落库 (record_alert_event) → WS 广播 (_preopen_sse_shape 增量键) → webhook enqueue。"""
    from app.services import preferences
    from app.services.quote_service import QuoteService
    from app.strategy.monitor import MonitorRuleEngine

    engine = MonitorRuleEngine()
    engine.set_rules([_preopen_rule()])

    recorded: list[dict] = []
    operational = SimpleNamespace(
        record_alert_event=lambda ev: recorded.append(ev) or {
            "id": ev["id"],
            "occurred_at": ev.get("occurred_at") or "2026-08-06T09:26:00+00:00",
        },
    )
    enqueued: list[dict] = []
    delivery = SimpleNamespace(enqueue=lambda **kwargs: enqueued.append(kwargs))

    service = QuoteService()
    service._app_state = SimpleNamespace(
        monitor_engine=engine,
        operational=operational,
        notification_delivery=delivery,
        repo=SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path)),
    )
    # Phase 55: SSE → WS 迁移, 用 broadcast_from_thread 捕获广播
    ws_calls: list[tuple] = []
    monkeypatch.setattr(
        "app.ws.broadcast.broadcast_from_thread",
        lambda mgr, ch, mt, data: ws_calls.append((ch, mt, data)),
    )
    service.attach_ws_manager(object())

    monkeypatch.setenv("PHASE1_FIXTURE_MODE", "yes")
    monkeypatch.setenv("PHASE1_FEISHU_RECEIVER_URL", "http://receiver:8080/feishu")
    monkeypatch.setattr(preferences, "load", lambda: {"notification_quiet_period": False})

    payload = _preopen_payload(degraded=False, probe={"status": "available"})
    result = service.evaluate_premarket_alerts(payload)

    assert result["rules"] == 1
    assert result["events"] == 1
    assert result["degraded"] is False
    assert result["probe_status"] == "available"

    # 落库优先: 事件先经 record_alert_event (全量 dict), 回填 id/occurred_at 后广播
    assert len(recorded) == 1
    ev = recorded[0]
    assert ev["source"] == "preopen"
    assert ev["type"] == "preopen"
    assert ev["window"] == "pre_open"
    assert ev["provisional"] is True
    assert ev["degraded"] is False
    assert ev["probe"]["status"] == "available"
    assert ev["strategy_ids"] == ["auction_bullish"]
    assert ev["preopen_metrics"]["open_gap"] == 0.08

    # WS 广播: _preopen_sse_shape 在既有键集基础上追加 preopen 增量键
    assert len(ws_calls) == 1
    ch, mt, data = ws_calls[0]
    assert ch == "alerts"
    assert mt == "strategy_alert"
    sse = data["alerts"][0]
    for key in ("id", "occurred_at", "source", "rule_id", "symbol", "message",
                "window", "provisional", "degraded", "probe", "strategy_ids", "preopen_metrics"):
        assert key in sse, f"WS 形状缺键: {key}"
    assert sse["source"] == "preopen"
    assert sse["symbol"] == "000001.SZ"
    assert sse["strategy_ids"] == ["auction_bullish"]

    # webhook: 规则带 webhook_channels=["feishu"] → enqueue 恰一次
    assert len(enqueued) == 1
    assert [c.channel for c in enqueued[0]["channel_configs"]] == ["feishu"]
    assert enqueued[0]["event_id"] == sse["id"]


def test_evaluate_premarket_alerts_degraded_without_operational(tmp_path, monkeypatch):
    """T16 降级: operational=None → alert_store.append_many + WS 仍广播 + 投递跳过。"""
    from app.services import alert_store
    from app.services.quote_service import QuoteService
    from app.strategy.monitor import MonitorRuleEngine

    engine = MonitorRuleEngine()
    engine.set_rules([_preopen_rule()])

    enqueued: list[dict] = []
    delivery = SimpleNamespace(enqueue=lambda **kwargs: enqueued.append(kwargs))

    service = QuoteService()
    service._app_state = SimpleNamespace(
        monitor_engine=engine,
        operational=None,
        notification_delivery=delivery,
        repo=SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path)),
    )
    # Phase 55: SSE → WS 迁移
    ws_calls: list[tuple] = []
    monkeypatch.setattr(
        "app.ws.broadcast.broadcast_from_thread",
        lambda mgr, ch, mt, data: ws_calls.append((ch, mt, data)),
    )
    service.attach_ws_manager(object())

    appended: list[tuple] = []
    monkeypatch.setattr(alert_store, "append_many", lambda data_dir, events: appended.append((data_dir, events)))

    payload = _preopen_payload()
    result = service.evaluate_premarket_alerts(payload)

    assert result["events"] == 1
    # 降级写路径: append_many 收到 (data_dir, events)
    assert len(appended) == 1
    assert appended[0][0] == tmp_path
    assert len(appended[0][1]) == 1
    # WS 仍广播
    assert len(ws_calls) == 1
    assert ws_calls[0][0] == "alerts"
    assert ws_calls[0][1] == "strategy_alert"
    # 投递跳过: operational=None 时不走 webhook enqueue
    assert enqueued == []


def test_evaluate_premarket_alerts_skip_semantics(tmp_path):
    """skip 语义: engine 缺失 / payload 非 available → 诚实 skip, 均不崩溃。"""
    from app.services.quote_service import QuoteService
    from app.strategy.monitor import MonitorRuleEngine

    service = QuoteService()
    service._app_state = SimpleNamespace(monitor_engine=None)
    assert service.evaluate_premarket_alerts({}) == {"skipped": "no monitor engine"}

    engine = MonitorRuleEngine()
    engine.set_rules([_preopen_rule()])
    service._app_state = SimpleNamespace(monitor_engine=engine)
    result = service.evaluate_premarket_alerts({"available": False})
    assert result == {"skipped": "preview unavailable", "degraded": True}
