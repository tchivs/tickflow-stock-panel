"""数据源选择白名单 + 链健康检查 回归测试。

覆盖两个此前缺失的守卫:
1. preferences 白名单必须包含前端 /settings/data-sources 可切换的 builtin 源
   (free_stockdb / xyz), 否则切换保存后被过滤回 tickflow —— 「切换成功但实际
   永远走 tickflow」的假象。
2. chain.health_check 对 tencent 返回 list (非 Polars frame) 必须按 list 判空,
   不能调用 .is_empty() 崩溃 —— 否则腾讯实时源在设置页永远显示 error。
"""
from __future__ import annotations

from app.services import preferences


def _clean_whitelist():
    """隔离白名单: 不依赖已加载的 custom 插件状态。"""
    from app.data_providers.custom import loader as custom_loader
    custom_loader._PROVIDERS.clear()  # type: ignore[attr-defined]
    custom_loader._PLUGIN_STATUS.clear()  # type: ignore[attr-defined]


def test_builtin_chain_sources_are_swappable(monkeypatch):
    """free_stockdb / xyz 必须可被选中为 daily/minute provider。"""
    _clean_whitelist()
    saved: list[dict] = []

    def fake_save(updates: dict) -> dict:
        saved.append(updates)
        return updates

    monkeypatch.setattr(preferences, "save", fake_save)
    monkeypatch.setattr(preferences, "load", lambda: saved[-1] if saved else {})

    preferences.save({"daily_data_provider": "free_stockdb"})
    assert preferences.get_daily_data_provider() == "free_stockdb", (
        "free_stockdb 被白名单过滤回 tickflow —— 前端切换将假成功"
    )

    preferences.save({"minute_data_provider": "xyz"})
    assert preferences.get_minute_data_provider() == "xyz"

    preferences.save({"realtime_data_provider": "tencent"})
    assert preferences.get_realtime_data_provider() == "tencent"


def test_unknown_provider_falls_back_to_tickflow(monkeypatch):
    """白名单外的未知源仍须安全回退 tickflow。"""
    _clean_whitelist()
    monkeypatch.setattr(preferences, "load", lambda: {"daily_data_provider": "nonexistent"})
    assert preferences.get_daily_data_provider() == "tickflow"


def test_health_check_tencent_handles_list_return(monkeypatch):
    """Tencent get_realtime 返回 list[dict]; health_check 必须按 list 判空。"""
    from app.data_providers import chain

    class FakeTencent:
        def get_realtime(self, symbols=None):
            return [{"symbol": "000001", "last_price": 10.0}]

    monkeypatch.setattr(chain, "_get_provider", lambda name: FakeTencent())
    assert chain.health_check("tencent") == "ok"


def test_health_check_tencent_empty_list_warns(monkeypatch):
    from app.data_providers import chain

    class EmptyTencent:
        def get_realtime(self, symbols=None):
            return []

    monkeypatch.setattr(chain, "_get_provider", lambda name: EmptyTencent())
    assert chain.health_check("tencent") == "warn"


def test_build_chain_puts_selected_source_first():
    """用户选择的源 (custom 或 builtin) 必须排在链首, 且不重复。"""
    from app.services import kline_sync

    assert kline_sync._build_chain("daily", "xyz") == ["xyz", "free_stockdb", "ifzq", "tickflow"]
    assert kline_sync._build_chain("daily", "free_stockdb") == ["free_stockdb", "ifzq", "xyz", "tickflow"]
    # custom 源不在内置链里 → 置顶 + 内置链跟随
    assert kline_sync._build_chain("daily", "mycustom") == ["mycustom", "free_stockdb", "ifzq", "xyz", "tickflow"]
    # tickflow 选择 → 内置链原样返回 (免费源先于付费)
    assert kline_sync._build_chain("daily", "tickflow") == ["free_stockdb", "ifzq", "xyz", "tickflow"]
    # minute 链含 sina
    assert kline_sync._build_chain("minute", "ifzq") == ["ifzq", "free_stockdb", "sina", "xyz", "tickflow"]
