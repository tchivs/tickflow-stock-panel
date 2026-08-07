"""Phase 40 wave 2 (注册) 回归测试: local_stockdb 通道接入既有配置与链机制。

覆盖 LOCAL-02 的可观测验收点 (T1: config 键 + _get_provider 分支/lazy 单例;
T3 追加: 白名单/链首/位置覆盖/health 三态/settings builtin)。
"""
from __future__ import annotations

import polars as pl
import pytest

from app.config import Settings, settings
from app.data_providers import chain
from app.data_providers.stockdb_provider import StockDBProvider, StockDBAuthError


# ── Task 1: config 键 + _get_provider 分支 / lazy 单例 ─────────────────────


def test_config_defaults():
    """config 两键默认值: url=http://127.0.0.1:8000, api_key=""。"""
    s = Settings()
    assert s.local_stockdb_url == "http://127.0.0.1:8000"
    assert s.local_stockdb_api_key == ""


def test_config_env_override(monkeypatch):
    """环境变量 LOCAL_STOCKDB_URL / LOCAL_STOCKDB_API_KEY 覆盖新 Settings 实例。"""
    monkeypatch.delenv("LOCAL_STOCKDB_URL", raising=False)
    monkeypatch.delenv("LOCAL_STOCKDB_API_KEY", raising=False)
    monkeypatch.setenv("LOCAL_STOCKDB_URL", "http://env:8000")
    monkeypatch.setenv("LOCAL_STOCKDB_API_KEY", "env-key")
    s = Settings()
    assert s.local_stockdb_url == "http://env:8000"
    assert s.local_stockdb_api_key == "env-key"


def test_get_provider_local_stockdb_returns_singleton(monkeypatch):
    """_get_provider("local_stockdb") 两次调用返回同一实例 (lazy 单例)。"""
    chain._provider_cache.pop("local_stockdb", None)

    captured: dict = {}

    class _FakeStockDB:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import app.data_providers.stockdb_provider as sp_mod

    monkeypatch.setattr(sp_mod, "StockDBProvider", _FakeStockDB)
    monkeypatch.setattr(chain, "settings", type("S", (), {"local_stockdb_url": "http://u:8000", "local_stockdb_api_key": "k"})())

    a = chain._get_provider("local_stockdb")
    b = chain._get_provider("local_stockdb")
    assert a is b
    assert captured == {"base_url": "http://u:8000", "api_key": "k"}
    chain._provider_cache.pop("local_stockdb", None)


def test_singleton_uses_settings_defaults(monkeypatch):
    """单例构造参数来自 settings.local_stockdb_url / local_stockdb_api_key。"""
    chain._provider_cache.pop("local_stockdb", None)

    import app.data_providers.stockdb_provider as sp_mod

    class _FakeStockDB:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake = _FakeStockDB()
    monkeypatch.setattr(sp_mod, "StockDBProvider", lambda **kw: (fake.kwargs.update(kw) or fake))
    monkeypatch.setattr(
        chain, "settings", type("S", (), {"local_stockdb_url": "http://cfg:8000", "local_stockdb_api_key": "cfg-key"})()
    )

    chain.local_stockdb_provider()
    assert fake.kwargs == {"base_url": "http://cfg:8000", "api_key": "cfg-key"}
    chain._provider_cache.pop("local_stockdb", None)


# ── Task 3: 注册回归 — 白名单 / 链首 / 位置覆盖 / health 三态 / settings builtin ─


def test_local_stockdb_in_whitelist():
    """白名单必须含 local_stockdb — 缺失则 _sanitize_chain 静默过滤回 tickflow
    (「切换成功但实际永远走 tickflow」假象陷阱, LOCAL-02 硬验收)。"""
    from tests.test_data_source_selection import _clean_whitelist

    _clean_whitelist()
    from app.services import preferences

    assert "local_stockdb" in preferences._ALLOWED_DATA_PROVIDERS


def test_set_provider_chain_keeps_local_stockdb_first(monkeypatch):
    """set_provider_chain 保存后 local_stockdb 保持链首且不被白名单过滤。"""
    from tests.test_data_source_selection import _clean_whitelist
    from app.services import preferences

    _clean_whitelist()
    saved: list[dict] = []

    def fake_save(updates: dict) -> dict:
        saved.append(updates)
        return updates

    monkeypatch.setattr(preferences, "save", fake_save)
    monkeypatch.setattr(preferences, "load", lambda: saved[-1] if saved else {})

    chain_list = preferences.set_provider_chain("daily", ["local_stockdb", "tickflow"])
    assert chain_list[0] == "local_stockdb"
    assert saved[-1]["provider_chains"]["daily"][0] == "local_stockdb"
    assert saved[-1]["provider_chains"]["daily"][-1] == "tickflow"


def test_builtin_chain_heads_local_stockdb():
    """内置链 daily/minute 链首均为 local_stockdb (受管源优先)。"""
    assert chain.chain_for("daily")[0] == "local_stockdb"
    assert chain.chain_for("minute")[0] == "local_stockdb"


def test_user_chain_override_position_wins(monkeypatch):
    """用户 provider_chains 覆盖保持原顺序 — 位置配置化, 不自动插链首。"""
    from app.services import preferences

    monkeypatch.setattr(
        preferences,
        "load",
        lambda: {"provider_chains": {"daily": ["xyz", "local_stockdb", "tickflow"]}},
    )
    assert preferences.get_provider_chain("daily") == ["xyz", "local_stockdb", "tickflow"]


def test_health_check_local_stockdb_ok_warn_error(monkeypatch):
    """health_check("local_stockdb") 三态: 非空帧→ok / 空帧→warn / 鉴权异常→error。"""

    class _OkLocal:
        def get_daily(self, symbols):
            return pl.DataFrame({"symbol": ["600519.SH"], "date": ["2026-08-05"]})

    class _EmptyLocal:
        def get_daily(self, symbols):
            return pl.DataFrame()

    class _AuthLocal:
        def get_daily(self, symbols):
            raise StockDBAuthError("stockdb auth failed")

    monkeypatch.setattr(chain, "_get_provider", lambda name: _OkLocal())
    assert chain.health_check("local_stockdb") == "ok"

    monkeypatch.setattr(chain, "_get_provider", lambda name: _EmptyLocal())
    assert chain.health_check("local_stockdb") == "warn"

    monkeypatch.setattr(chain, "_get_provider", lambda name: _AuthLocal())
    assert chain.health_check("local_stockdb") == "error"


def test_settings_builtin_lists_local_stockdb(monkeypatch):
    """/settings/data-sources builtin 含 local_stockdb 条目 (与白名单一致是前端切换前提)。"""
    from app.api import settings as settings_api

    # list_data_sources 内 `from app.data_providers import chain as provider_chain`
    # 是函数级导入 — 直接 patch chain.health_check 防真实 probe 网络。
    monkeypatch.setattr(chain, "health_check", lambda name: "ok")
    sources = settings_api.list_data_sources()
    entry = next(s for s in sources["builtin"] if s["name"] == "local_stockdb")
    assert entry["datasets"] == ["daily", "minute"]
    assert entry["health"] == "ok"
    assert entry["base_url"] == settings.local_stockdb_url
