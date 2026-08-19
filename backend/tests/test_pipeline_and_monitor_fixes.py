"""回归测试: 本轮修复的几处高风险行为(并发单飞 / 重任务槽 / sector fail-closed)。

均为纯逻辑, 不触网, 不依赖真实数据源。
"""
from __future__ import annotations

from types import SimpleNamespace

import polars as pl
import pytest

from app.jobs import daily_pipeline
from app.services import pipeline_jobs, preferences
from app.services.pipeline_jobs import JobStore
from app.services.quote_service import QuoteService
from app.strategy import monitor_rules
from app.strategy.monitor import MonitorRuleEngine

# ── JobStore 单飞 ────────────────────────────────────────────────────────

def test_create_singleflight_dedupes_pending_window(monkeypatch, tmp_path):
    """两次快速 create() 在 pending 窗口内应复用同一 job(is_new=False)。"""
    monkeypatch.setattr(preferences, "load", lambda: {"data_source_job_timeout_s": 3600})
    store = JobStore(store_dir=tmp_path / "jobs")

    jid1, new1 = store.create()
    assert new1 is True
    assert store.get(jid1)["timeout_s"] == 3600

    # 尚未 start(), job 仍是 pending —— 旧实现会在此另起新 job(并发双跑根因)
    jid2, new2 = store.create()
    assert jid2 == jid1
    assert new2 is False

    # start() 后仍复用同一活跃 job
    store.start(jid1)
    jid3, new3 = store.create()
    assert jid3 == jid1
    assert new3 is False


def test_create_new_after_terminal(monkeypatch, tmp_path):
    """job 终态(succeed/fail)后, create() 应给出新 job。"""
    monkeypatch.setattr(preferences, "load", lambda: {"data_source_long_job_timeout_s": 5400})
    store = JobStore(store_dir=tmp_path / "jobs")
    jid1, _ = store.create(long_running=True)
    assert store.get(jid1)["timeout_s"] == 5400
    store.start(jid1)
    store.succeed(jid1, {"ok": True})

    jid2, new2 = store.create()
    assert jid2 != jid1
    assert new2 is True


def test_run_slot_is_exclusive():
    """重任务执行槽同一时刻只允许一个持有者(防僵尸并发)。"""
    assert pipeline_jobs.try_acquire_run_slot() is True
    try:
        # 已被占用, 第二次获取失败
        assert pipeline_jobs.try_acquire_run_slot() is False
    finally:
        pipeline_jobs.release_run_slot()
    # 释放后可再次获取
    assert pipeline_jobs.try_acquire_run_slot() is True
    pipeline_jobs.release_run_slot()
    # 重复释放幂等, 不抛
    pipeline_jobs.release_run_slot()

# ── 监控 sector fail-closed ──────────────────────────────────────────────

def _base_price_rule(scope: str) -> dict:
    return {
        "id": "r_test",
        "name": "t",
        "type": "price",
        "conditions": [{"field": "close", "op": ">", "value": 10}],
        "logic": "and",
        "scope": scope,
    }


def test_validate_rejects_sector_without_name():
    """sector 作用域必须给出板块名/代码, 否则 fail-closed 拒绝。"""
    with pytest.raises(ValueError):
        monitor_rules.validate(_base_price_rule("sector"))
    bad = _base_price_rule("sector")
    bad["sector"] = []
    with pytest.raises(ValueError):
        monitor_rules.validate(bad)


def test_validate_accepts_sector_with_name():
    """sector 作用域给出板块名/代码时合法。"""
    for sector in ("5G", "300843.TI", ["5G", "人工智能"]):
        rule = _base_price_rule("sector")
        rule["sector"] = sector
        monitor_rules.validate(rule)  # 不应抛


def test_validate_accepts_symbols_scope():
    rule = _base_price_rule("symbols")
    rule["symbols"] = ["600000.SH"]
    monitor_rules.validate(rule)  # 不应抛


def test_apply_scope_sector_fails_closed_without_loader():
    """未注入 board loader 时 sector 规则返回空(绝不退化为全市场)。"""
    df = pl.DataFrame({"symbol": ["600000.SH", "000001.SZ"], "close": [10.0, 20.0]})
    engine = MonitorRuleEngine()
    out = engine._apply_scope(df, {"id": "r_old", "scope": "sector", "sector": "5G"})
    assert out.is_empty()

    # 对照: scope=all 返回全量, symbols 过滤子集
    assert engine._apply_scope(df, {"scope": "all"}).height == 2
    picked = engine._apply_scope(
        df, {"scope": "symbols", "symbols": ["600000.SH"]}
    )
    assert picked.height == 1


def test_apply_scope_sector_joins_members():
    """注入 board loader 后 sector 规则只保留板块成员。"""
    df = pl.DataFrame(
        {
            "symbol": ["600000.SH", "000001.SZ", "000016.SZ"],
            "close": [10.0, 20.0, 30.0],
        }
    )

    def loader(sector):
        assert sector == "5G"
        return [{"name": "5G", "members": ["000001", "000016"]}]
    engine = MonitorRuleEngine()
    engine.set_board_loader(loader)
    out = engine._apply_scope(df, {"scope": "sector", "sector": "5G"})
    # 600000.SH 不属于板块; 000001/000016 属于 → 只留这两行。
    assert sorted(out["symbol"].to_list()) == ["000001.SZ", "000016.SZ"]


def test_sector_symbols_extracts_members() -> None:
    """_sector_symbols 从 board dict 提取 6 位代码 (兼容 members/symbols 键)。"""
    from app.strategy.monitor import _sector_symbols

    boards = [
        {"name": "5G", "members": ["000016", "000049", "600000.SH"]},
        {"name": "AI", "symbols": ["000063"]},
        {"name": "junk", "members": ["abc", "12345", ""]},
    ]
    assert _sector_symbols(boards) == {"000016", "000049", "600000", "000063"}

# ── Webhook 推送 (上游 v0.2 用例, 适配我方 delivery-service 架构) ─────────
# 上游原版打桩 quote_service._WEBHOOK_EXECUTOR (线程池直推 feishu/wecom);
# 我方权威实现改为 notification_delivery.enqueue (feishu/telegram, 持久化
# 投递)。此处按我方符号重写, 保留上游用例意图: 按规则勾选渠道投递且标题
# 不含品牌字样。


def test_ladder_webhook_enqueues_configured_channels(monkeypatch):
    calls = []

    class CaptureDelivery:
        def enqueue(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr("app.services.preferences.load", lambda: {})
    monkeypatch.setattr("app.services.preferences.get_feishu_webhook_url", lambda: "https://open.feishu.cn/open-apis/bot/v2/hook/test")
    monkeypatch.setattr("app.services.preferences.get_feishu_webhook_secret", lambda: "secret")

    engine = type("Engine", (), {
        "rules": {
            "r_ladder": {"webhook_channels": ["feishu"]},
            "r_muted": {"webhook_channels": []},
        },
    })()
    service = object.__new__(QuoteService)
    service._app_state = SimpleNamespace(notification_delivery=CaptureDelivery())

    QuoteService._maybe_send_webhook(
        service,
        [
            {
                "id": "evt-1",
                "rule_id": "r_ladder",
                "source": "ladder",
                "symbol": "600000.SH",
                "name": "浦发银行",
                "message": "炸板预警",
            },
            {
                # 未勾选渠道的规则不投递
                "id": "evt-2",
                "rule_id": "r_muted",
                "source": "ladder",
                "symbol": "000001.SZ",
                "name": "平安银行",
                "message": "不应推送",
            },
        ],
        engine,
    )

    assert len(calls) == 1
    assert calls[0]["event_id"] == "evt-1"
    assert [cfg.channel for cfg in calls[0]["channel_configs"]] == ["feishu"]
    dumped = repr(calls)
    assert "TickFlow" not in dumped


def test_ladder_webhook_skips_when_no_channel_configured(monkeypatch):
    calls = []

    class CaptureDelivery:
        def enqueue(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr("app.services.preferences.load", lambda: {})
    # 飞书未配置 + telegram 未配置 -> 不 enqueue
    monkeypatch.setattr("app.services.preferences.get_feishu_webhook_url", lambda: "")

    engine = type("Engine", (), {
        "rules": {"r_ladder": {"webhook_channels": ["feishu"]}},
    })()
    service = object.__new__(QuoteService)
    service._app_state = SimpleNamespace(notification_delivery=CaptureDelivery())

    QuoteService._maybe_send_webhook(
        service,
        [{"id": "evt-1", "rule_id": "r_ladder", "source": "ladder", "message": "炸板预警"}],
        engine,
    )

    assert calls == []


def test_system_notify_titles_use_chinese_source_labels_without_brand(monkeypatch):
    """OS 通知标题含上游中文分类标签 (含 5b4b1d6 的 ladder=连板梯队), 不含品牌字样。"""
    calls = []

    monkeypatch.setattr("app.services.preferences.get_system_notify_enabled", lambda: True)
    monkeypatch.setattr(
        "app.services.notify_adapter.notify", lambda title, body: calls.append((title, body))
    )

    service = object.__new__(QuoteService)
    QuoteService._maybe_send_system_notifications(
        service,
        [
            {"source": "ladder", "symbol": "600000.SH", "name": "浦发银行", "message": "炸板预警"},
            {"source": "sector", "symbol": "", "name": "5G", "message": "板块异动"},
        ],
    )

    titles = [title for title, _ in calls]
    assert titles == ["AthenaQuant · 连板梯队", "AthenaQuant · 板块"]
    assert all("TickFlow" not in title for title in titles)


def test_review_webhooks_use_title_without_brand(monkeypatch):
    calls = []
    monkeypatch.setattr("app.services.preferences.get_review_push_channels", lambda: ["feishu", "wecom"])
    monkeypatch.setattr("app.services.preferences.get_feishu_webhook_url", lambda: "feishu-url")
    monkeypatch.setattr("app.services.preferences.get_feishu_webhook_secret", lambda: "secret")
    monkeypatch.setattr("app.services.preferences.get_wecom_webhook_url", lambda: "wecom-url")
    monkeypatch.setattr(
        "app.services.webhook_adapter.send_feishu_card",
        lambda *args: calls.append(("feishu", args)) or True,
    )
    monkeypatch.setattr(
        "app.services.webhook_adapter.send_wecom_markdown",
        lambda *args: calls.append(("wecom", args)) or True,
    )

    daily_pipeline._maybe_push_review("复盘正文", {"as_of": "2026-07-18"})

    # 我方品牌标题: "AthenaQuant · 每日复盘" (上游去品牌诉求 -> 不含 TickFlow)
    assert [args[1] for _, args in calls] == ["AthenaQuant · 每日复盘"] * 2
    assert all("TickFlow" not in args[1] for _, args in calls)
