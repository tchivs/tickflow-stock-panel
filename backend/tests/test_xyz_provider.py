"""xyz get_auction 单测 (32-01 AQ-01 提供方) — 无网络, monkeypatch _call_tool。

Hermetic 约定 (镜像 test_auction_sync.py): 生产 import 放测试函数内, 不触碰
真实 MCP 端点与 data/ 目录。覆盖: canonical 映射 (带后缀 symbol)、单日期形式、
单 symbol 守卫 (上游带宽上限)、空载荷诚实降级、无可选列缺列。
"""
from __future__ import annotations

import json
from datetime import date, datetime

import polars as pl
import pytest


def _canned_payload() -> list[dict]:
    """镜像 RESEARCH §1 映射表: 两行 stockdb_get_call_auction 原始行 (ISO time 串)。"""
    return [
        {"code": "000001", "time": "2026-08-04 09:25:00", "volume": 123400, "money": 51234000.0, "current": 10.25},
        {"code": "600000", "time": "2026-08-04 09:25:00", "volume": 56700, "money": 22340000.0, "current": 3.95},
    ]


def _provider_with(payload: str | Exception):
    """构造注入 _call_tool 的 XYZProvider 实例。"""
    from app.data_providers.xyz_provider import XYZProvider

    provider = XYZProvider()

    def fake_call_tool(name, args):
        del name, args
        if isinstance(payload, Exception):
            raise payload
        return payload

    provider._call_tool = fake_call_tool
    return provider


# ================================================================
# Test 1 — canonical 映射: 后缀保持 / datetime / volume / amount / virtual_price
# ================================================================


def test_xyz_get_auction_maps_rows_to_canonical():
    """上游行 → canonical: symbol 带请求后缀, datetime/auction_volume/amount/virtual_price 正确。"""
    provider = _provider_with(json.dumps(_canned_payload()))

    df = provider.get_auction(["000001.SZ"], date(2026, 8, 4))

    assert df.columns == [
        "symbol", "datetime", "auction_volume", "auction_amount", "auction_virtual_price",
    ]
    rows = df.to_dicts()
    assert len(rows) == 2
    # 请求的带后缀 symbol 保持 (非裸码剥离)
    assert rows[0]["symbol"] == "000001.SZ"
    # 未知 code 走 fallback = 原始 code
    assert rows[1]["symbol"] == "600000"
    assert rows[0]["datetime"] == datetime(2026, 8, 4, 9, 25, 0)
    assert rows[0]["auction_volume"] == 123400.0
    assert rows[0]["auction_amount"] == 51234000.0
    assert rows[0]["auction_virtual_price"] == 10.25
    assert rows[1]["auction_volume"] == 56700.0
    assert rows[1]["auction_amount"] == 22340000.0
    assert rows[1]["auction_virtual_price"] == 3.95


# ================================================================
# Test 2 — 单日期形式: end_date is None → start == end (probe 兼容)
# ================================================================


def test_xyz_get_auction_single_date_form():
    """end_date=None → 请求 start_date == end_date == trade_date, security 去后缀。"""
    provider = _provider_with(json.dumps(_canned_payload()))
    captured: list[tuple[str, dict]] = []

    def capture(name, args):
        captured.append((name, args))
        return json.dumps(_canned_payload())

    provider._call_tool = capture

    provider.get_auction(["000001.SZ"], date(2026, 8, 4))
    name, args = captured[0]
    assert name == "stockdb_get_call_auction"
    assert args == {
        "security": ["000001"],
        "start_date": "2026-08-04",
        "end_date": "2026-08-04",
    }

    # 显式 end_date == start_date 同构
    captured.clear()
    provider.get_auction(["000001.SZ"], date(2026, 8, 4), date(2026, 8, 4))
    assert captured[0][1] == {
        "security": ["000001"],
        "start_date": "2026-08-04",
        "end_date": "2026-08-04",
    }


# ================================================================
# Test 3 — 单 symbol 守卫 (AQ-05 上游带宽上限, fail-fast)
# ================================================================


def test_xyz_get_auction_rejects_multi_symbol():
    """多码/空列表 → ValueError fail-fast, 绝不静默截断或批处理。"""
    provider = _provider_with(json.dumps(_canned_payload()))

    with pytest.raises(ValueError):
        provider.get_auction(["000001.SZ", "000002.SZ"], date(2026, 8, 4))
    with pytest.raises(ValueError):
        provider.get_auction([], date(2026, 8, 4))
    with pytest.raises(ValueError):
        provider.get_auction(["000001.SZ"])  # start_date 缺失


# ================================================================
# Test 4 — 空载荷诚实降级: "" / 抛异常 → 空 df 不抛
# ================================================================


def test_xyz_get_auction_empty_payload_on_error():
    """_call_tool 返回 "" → 空 pl.DataFrame() 不抛 (错误吞噬, 镜像 _price_frame)。"""
    provider = _provider_with("")
    df = provider.get_auction(["000001.SZ"], date(2026, 8, 4))
    assert isinstance(df, pl.DataFrame)
    assert df.is_empty()

    # _call_tool 边界抛异常 → 同样空 df 不抛 (诚实降级)
    provider = _provider_with(RuntimeError("upstream timeout"))
    df2 = provider.get_auction(["000001.SZ"], date(2026, 8, 4))
    assert isinstance(df2, pl.DataFrame)
    assert df2.is_empty()


# ================================================================
# Test 5 — 无可选列: 上游不提供 current → 仅 4 canonical 列 (诚实缺列)
# ================================================================


def test_xyz_get_auction_omits_optional_col_when_absent():
    """payload 无 current 字段 → 输出仅 4 canonical 列, 永不 0 填 auction_virtual_price。"""
    payload = [{"code": "000001", "time": "2026-08-04 09:25:00", "volume": 123400, "money": 51234000.0}]
    provider = _provider_with(json.dumps(payload))

    df = provider.get_auction(["000001.SZ"], date(2026, 8, 4))

    assert df.columns == ["symbol", "datetime", "auction_volume", "auction_amount"]
    assert "auction_virtual_price" not in df.columns
    # 诚实: auction_unmatched_volume 上游无此字段, 永不产出
    assert "auction_unmatched_volume" not in df.columns


# ================================================================
# Test 6 — 三态化 (HON-01): HTTP 403 / 配额窗文案 → SourceBlockedError
# ================================================================


def test_xyz_get_auction_http_403_raises_source_blocked():
    """HTTP 403 → SourceBlockedError 上抛 (typed 信号), 绝不塌缩空帧。"""
    import httpx
    from app.data_providers.base import SourceBlockedError
    from app.data_providers.xyz_provider import XYZProvider

    provider = XYZProvider()
    provider._client.post = lambda *a, **k: httpx.Response(
        403, request=httpx.Request("POST", "http://example.com"), text="quota window",
    )

    with pytest.raises(SourceBlockedError):
        provider.get_auction(["000001.SZ"], date(2026, 8, 4))


def test_xyz_get_auction_policy_text_raises_source_blocked():
    """HTTP 200 载荷 error 串含配额窗文案 marker → SourceBlockedError (marker 面)。"""
    import httpx
    from app.data_providers.base import SourceBlockedError
    from app.data_providers.xyz_provider import XYZProvider

    provider = XYZProvider()
    provider._client.post = lambda *a, **k: httpx.Response(
        200, request=httpx.Request("POST", "http://example.com"),
        json={"error": "配额窗口未开放"},
    )

    with pytest.raises(SourceBlockedError):
        provider.get_auction(["000001.SZ"], date(2026, 8, 4))


def test_xyz_get_auction_propagates_source_blocked():
    """_call_tool 抛 SourceBlockedError → get_auction 原样重抛 (绝不吞成空帧)。"""
    from app.data_providers.base import SourceBlockedError

    provider = _provider_with(SourceBlockedError("blocked"))
    with pytest.raises(SourceBlockedError):
        provider.get_auction(["000001.SZ"], date(2026, 8, 4))


def test_xyz_daily_minute_source_blocked_degrades_to_empty():
    """daily/minute 路径 (scope 决策): 上游 403 → 空帧降级不抛 (契约不变)。"""
    import httpx
    from app.data_providers.xyz_provider import XYZProvider

    provider = XYZProvider()
    provider._client.post = lambda *a, **k: httpx.Response(
        403, request=httpx.Request("POST", "http://example.com"), text="quota window",
    )

    df = provider.get_daily(["000001.SZ"])
    assert isinstance(df, pl.DataFrame)
    assert df.is_empty()
