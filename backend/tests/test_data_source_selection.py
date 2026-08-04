"""数据源选择白名单 + 链健康检查 回归测试。

覆盖此前缺失的守卫:
1. preferences 白名单必须包含前端 /settings/data-sources 可切换的 builtin 源
   (free_stockdb / xyz), 否则切换保存后被过滤回 tickflow —— 「切换成功但实际
   永远走 tickflow」的假象。
2. chain.health_check 对 tencent 返回 list (非 Polars frame) 必须按 list 判空,
   不能调用 .is_empty() 崩溃 —— 否则腾讯实时源在设置页永远显示 error。
3. provider_chains (per-dataset 有序启用链) 的保存 / 读取 / 排序 / 移除。
"""
from __future__ import annotations

from app.services import preferences


def _clean_whitelist():
    """隔离白名单: 清空已加载的 custom 插件状态后重载, 避免污染同进程其他测试。"""
    from app.data_providers.custom import loader as custom_loader
    custom_loader._PROVIDERS.clear()  # type: ignore[attr-defined]
    custom_loader._PLUGIN_STATUS.clear()  # type: ignore[attr-defined]
    custom_loader._load_builtin_plugins()


def test_builtin_chain_sources_are_swappable(monkeypatch):
    """free_stockdb / xyz / tencent 必须可被选为 daily/minute/realtime 链成员。"""
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


def test_unknown_provider_falls_back_to_builtin_chain(monkeypatch):
    """白名单外的未知源须安全回退: 不再作为首选, 内置链兜底 (tickflow 在链末)。"""
    _clean_whitelist()
    monkeypatch.setattr(preferences, "load", lambda: {"daily_data_provider": "nonexistent"})
    chain = preferences.get_provider_chain("daily")
    assert chain[0] != "nonexistent"
    assert "tickflow" in chain
    assert chain[-1] == "tickflow"


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


def test_set_provider_chain_persists_order_and_legacy(monkeypatch):
    """set_provider_chain 保存有序链, 并把首选同步到旧单值字段。"""
    _clean_whitelist()
    saved: list[dict] = []

    def fake_save(updates: dict) -> dict:
        saved.append(updates)
        return updates

    monkeypatch.setattr(preferences, "save", fake_save)
    monkeypatch.setattr(preferences, "load", lambda: saved[-1] if saved else {})

    chain = preferences.set_provider_chain("daily", ["xyz", "free_stockdb", "tickflow"])
    assert chain == ["xyz", "free_stockdb", "tickflow"]
    # 首选同步到旧单值字段 (兼容层)
    assert preferences.get_daily_data_provider() == "xyz"
    # provider_chains 落盘
    assert saved[-1]["provider_chains"]["daily"] == ["xyz", "free_stockdb", "tickflow"]


def test_set_provider_chain_sanitizes_and_guarantees_tickflow(monkeypatch):
    """白名单外成员被过滤; tickflow 始终作为最终兜底 (链末)。"""
    _clean_whitelist()
    saved: list[dict] = []

    def fake_save(updates: dict) -> dict:
        saved.append(updates)
        return updates

    monkeypatch.setattr(preferences, "save", fake_save)
    monkeypatch.setattr(preferences, "load", lambda: saved[-1] if saved else {})

    chain = preferences.set_provider_chain("daily", ["free_stockdb"])  # 无 tickflow
    assert chain[-1] == "tickflow"
    assert "nonexistent" not in preferences.get_provider_chain("daily")


def test_remove_provider_drops_from_chain(monkeypatch):
    """卸载源时从对应数据集链移除, 首选随之更新。"""
    _clean_whitelist()
    saved: list[dict] = []

    def fake_save(updates: dict) -> dict:
        saved.append(updates)
        return updates

    monkeypatch.setattr(preferences, "save", fake_save)
    monkeypatch.setattr(preferences, "load", lambda: saved[-1] if saved else {})

    preferences.set_provider_chain("daily", ["xyz", "free_stockdb", "tickflow"])
    preferences.remove_provider("daily", "xyz")
    chain = preferences.get_provider_chain("daily")
    assert "xyz" not in chain
    assert chain[0] == "free_stockdb"
