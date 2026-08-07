"""Phase 40 wave 2 (注册) 回归测试: local_stockdb 通道接入既有配置与链机制。

覆盖 LOCAL-02 的可观测验收点 (T1: config 键 + _get_provider 分支/lazy 单例;
T3 追加: 白名单/链首/位置覆盖/health 三态/settings builtin)。
"""
from __future__ import annotations

import polars as pl
import pytest

from app.config import Settings
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
