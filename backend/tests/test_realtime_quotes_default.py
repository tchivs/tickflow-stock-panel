"""实时行情 default-on 契约: 有可用实时源时默认开启, 停机不抹除开关。

- get_realtime_quotes_enabled: 无显式配置 → 源可用(档位≠none)默认 True;
  显式配置过则尊重用户选择。
- QuoteService.stop(): 停机路径不落盘关闭偏好; disable() 显式关闭才持久化 false。
"""
from __future__ import annotations

import json

from app.services import preferences
from app.services.quote_service import QuoteService


def _point_prefs_at(tmp_path) -> None:
    """把 preferences 读写指到临时文件, 隔离真实 data/user_data/preferences.json。"""
    target = tmp_path / "preferences.json"
    preferences._path = lambda: target  # type: ignore[method-assign]
    return target


def test_realtime_default_on_when_source_available(monkeypatch, tmp_path):
    _point_prefs_at(tmp_path)  # 文件不存在 → 无显式配置
    monkeypatch.setattr(
        QuoteService, "is_realtime_allowed", classmethod(lambda cls: True),
    )
    assert preferences.get_realtime_quotes_enabled() is True


def test_realtime_default_off_when_no_source(monkeypatch, tmp_path):
    _point_prefs_at(tmp_path)
    monkeypatch.setattr(
        QuoteService, "is_realtime_allowed", classmethod(lambda cls: False),
    )
    assert preferences.get_realtime_quotes_enabled() is False


def test_realtime_explicit_pref_wins_over_source(monkeypatch, tmp_path):
    target = _point_prefs_at(tmp_path)
    target.write_text(json.dumps({"realtime_quotes_enabled": False}), encoding="utf-8")
    monkeypatch.setattr(
        QuoteService, "is_realtime_allowed", classmethod(lambda cls: True),
    )
    # 显式 False 优先于源可用性
    assert preferences.get_realtime_quotes_enabled() is False

    target.write_text(json.dumps({"realtime_quotes_enabled": True}), encoding="utf-8")
    monkeypatch.setattr(
        QuoteService, "is_realtime_allowed", classmethod(lambda cls: False),
    )
    # 显式 True 在无源时仍返回 True (开关态不凭空翻转; boot_check 会强制停轮询)
    assert preferences.get_realtime_quotes_enabled() is True


def test_quote_service_stop_does_not_persist_disable_does(monkeypatch):
    """stop() 停机路径不落盘关闭偏好; disable() 显式关闭才持久化 false。"""
    service = QuoteService()
    saved: list[bool] = []
    monkeypatch.setattr(QuoteService, "_save_enabled", staticmethod(lambda v: saved.append(v)))

    service.stop()
    assert saved == []

    service.disable()
    assert saved == [False]


def test_quote_service_enable_persists_true(monkeypatch):
    """enable() 落盘 True —— 默认开启在 boot_check→start() 后固化, 停机不再回退。"""
    service = QuoteService()
    saved: list[bool] = []
    monkeypatch.setattr(QuoteService, "_save_enabled", staticmethod(lambda v: saved.append(v)))
    monkeypatch.setattr(
        QuoteService, "is_realtime_allowed", classmethod(lambda cls: True),
    )
    monkeypatch.setattr(QuoteService, "_clamp_interval", lambda self, i: 6.0)

    assert service.enable() is True
    assert saved == [True]


# ================================================================
# 实时源连通性门控 (自适应默认开启的探测态)
# ================================================================

def test_boot_check_adaptive_default_probes_without_persisting(monkeypatch, tmp_path):
    """无显式偏好 + 档位允许 → start(persist=False) 进入探测态, 不落盘 true。"""
    _point_prefs_at(tmp_path)  # 无偏好文件
    monkeypatch.setattr(QuoteService, "is_realtime_allowed", classmethod(lambda cls: True))
    started: list[bool] = []
    monkeypatch.setattr(
        QuoteService, "start",
        lambda self, interval=0.0, *, persist=True: started.append(persist),
    )
    service = QuoteService()
    service.boot_check()
    assert started == [False]
    assert service._awaiting_confirm is True
    assert service._probe_failures == 0


def test_boot_check_explicit_pref_persists_true(monkeypatch, tmp_path):
    """显式偏好 true → start(persist=True), 无探测态。"""
    target = _point_prefs_at(tmp_path)
    target.write_text(json.dumps({"realtime_quotes_enabled": True}), encoding="utf-8")
    monkeypatch.setattr(QuoteService, "is_realtime_allowed", classmethod(lambda cls: True))
    started: list[bool] = []
    monkeypatch.setattr(
        QuoteService, "start",
        lambda self, interval=0.0, *, persist=True: started.append(persist),
    )
    service = QuoteService()
    service.boot_check()
    assert started == [True]
    assert service._awaiting_confirm is False


def test_probe_confirms_on_first_success(monkeypatch):
    service = QuoteService()
    service._awaiting_confirm = True
    saved: list[bool] = []
    monkeypatch.setattr(QuoteService, "_save_enabled", staticmethod(lambda v: saved.append(v)))

    service._resolve_probe(status="ok", ok=True)
    assert saved == [True]
    assert service._awaiting_confirm is False
    assert service._probe_failures == 0


def test_probe_auto_disables_after_max_consecutive_errors(monkeypatch):
    service = QuoteService()
    service._awaiting_confirm = True
    saved: list[bool] = []
    monkeypatch.setattr(QuoteService, "_save_enabled", staticmethod(lambda v: saved.append(v)))

    service._resolve_probe(status="error", ok=False)
    service._resolve_probe(status="error", ok=False)
    assert service._awaiting_confirm is True          # 未达阈值
    assert saved == []
    service._resolve_probe(status="error", ok=False)  # 达阈值
    assert saved == [False]
    assert service._awaiting_confirm is False
    assert service._enabled is False
    assert service._running is False


def test_probe_ignores_empty_and_skip(monkeypatch):
    """源可达但空数据 / 配置跳过 → 不计数, 保持探测态 (避免盘前空响应误禁)。"""
    service = QuoteService()
    service._awaiting_confirm = True
    saved: list[bool] = []
    monkeypatch.setattr(QuoteService, "_save_enabled", staticmethod(lambda v: saved.append(v)))

    service._resolve_probe(status="empty", ok=False)
    service._resolve_probe(status="skip", ok=False)
    assert service._awaiting_confirm is True
    assert service._probe_failures == 0
    assert saved == []


def test_fetch_quotes_feeds_probe_error_status(monkeypatch):
    service = QuoteService()
    service._awaiting_confirm = True
    monkeypatch.setattr(QuoteService, "realtime_mode", classmethod(lambda cls: "watchlist"))
    monkeypatch.setattr(QuoteService, "_fetch_watchlist_quotes", lambda self: "error")

    assert service._fetch_quotes() is False
    assert service._probe_failures == 1


def test_fetch_quotes_confirms_on_success(monkeypatch):
    import time as _time

    service = QuoteService()
    service._awaiting_confirm = True
    saved: list[bool] = []
    monkeypatch.setattr(QuoteService, "_save_enabled", staticmethod(lambda v: saved.append(v)))
    monkeypatch.setattr(QuoteService, "realtime_mode", classmethod(lambda cls: "watchlist"))

    def fake_fetch(self):
        self._fetched_at = _time.time() * 1000
        return "ok"

    monkeypatch.setattr(QuoteService, "_fetch_watchlist_quotes", fake_fetch)
    assert service._fetch_quotes() is True
    assert saved == [True]
    assert service._awaiting_confirm is False


def test_has_realtime_quotes_pref(tmp_path):
    target = _point_prefs_at(tmp_path)
    assert preferences.has_realtime_quotes_pref() is False
    target.write_text(json.dumps({"realtime_quotes_enabled": False}), encoding="utf-8")
    assert preferences.has_realtime_quotes_pref() is True


def test_disable_clears_probe_state(monkeypatch):
    service = QuoteService()
    service._awaiting_confirm = True
    service._probe_failures = 2
    saved: list[bool] = []
    monkeypatch.setattr(QuoteService, "_save_enabled", staticmethod(lambda v: saved.append(v)))

    service.disable()
    assert service._awaiting_confirm is False
    assert service._probe_failures == 0
    assert saved == [False]
