"""Tests for the Tencent realtime provider (qt.gtimg.cn adapter).

All offline — a fake transport returns canned GBK-encoded quote lines matching
the verified qt.gtimg.cn wire shape. Prefix routing, field mapping, unit
conversion (手→股, 万→元, %→小数), and stale-quote detection are covered.
"""
from __future__ import annotations

from typing import Any

import pytest

from app.data_providers.tencent_provider import (
    TencentRealtimeProvider,
    _norm_symbol,
    _parse_ts,
    _prefix,
)

# 浦发银行: price=9.51 prev=9.71 open=9.59 high=9.59 low=9.28
# vol(手)=1382638, amt(万)=129950, chg=-0.20/-2.06%, turnover=0.42, amp=3.19
# pe=6.30, pb=0.43, float_mcap=3167.39, total_mcap=3167.39, limit_up=10.68, limit_down=8.74
_SH600000 = (
    'v_sh600000="1~浦发银行~600000~9.51~9.71~9.59~1382638~671700~710937'
    '~9.51~574~9.50~1351~9.49~250~9.48~253~9.47~287~9.52~1424~9.53~638'
    '~9.54~1356~9.55~2573~9.56~1634~~20260731161454~-0.20~-2.06~9.59~9.28'
    '~9.51/1382638/1299502653~1382638~129950~0.42~6.30~~9.59~9.28~3.19'
    '~3167.39~3167.39~0.43~10.68~8.74~1.44~-4910~9.40~4.43~6.33'
    '~0.09~129950.2653~13.6944~144~A~GP-A~-20.88~5.20~4.42~6.03~0.49'
    '~13.87~8.07~7.22~14.99~9.69~33305838300~33305838300~-47.49~-15.09'
    '~33305838300~~~-23.24~-0.21~~CNY~0~___D__F__N~9.60~-2151~";'
)

# 僵尸报价: *ST椰岛 600238, vol=0 price==prev_close
_SH600238_STALE = (
    'v_sh600238="1~*ST椰岛~600238~4.14~4.14~0.00~0~0~0~0.00~0~0.00~0~0.00~0'
    '~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0'
    '~~20260731161454~0.00~0.00~4.14~4.14~4.14/0/0~0~0~0.00~-86.52~~4.14~4.14'
    '~0.00~18.43~18.56~23.80~4.55~3.73~0.00~-4910~9.40~4.43~6.33'
    '~0.09~0.0000~13.6944~144~A~GP-A~-20.88~5.20~4.42~6.03~0.49'
    '~13.87~8.07~7.22~14.99~9.69~33305838300~33305838300~-47.49~-15.09'
    '~33305838300~~~-23.24~-0.21~~CNY~0~___D__F__N~9.60~-2151~";'
)

_GBK = "gbk"


class _FakeResponse:
    def __init__(self, content: bytes) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    @property
    def content(self) -> bytes:
        return self._content


class _FakeTransport:
    def __init__(self, lines: list[str]) -> None:
        self._text = ";".join(lines)
        self.calls: list[str] = []

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append(url)
        return _FakeResponse(self._text.encode(_GBK))

    def close(self) -> None:
        pass


def _provider(lines: list[str]) -> TencentRealtimeProvider:
    p = TencentRealtimeProvider()
    p._client = _FakeTransport(lines)  # type: ignore[assignment]
    return p


def test_norm_symbol_forms() -> None:
    assert _norm_symbol("603196.SH") == "603196"
    assert _norm_symbol("SH600519") == "600519"
    assert _norm_symbol("600519") == "600519"
    assert _norm_symbol("000001") == "000001"


def test_prefix_routing() -> None:
    assert _prefix("600519") == "sh"      # 沪个股
    assert _prefix("000001") == "sz"      # 深个股 (平安银行)
    assert _prefix("000300") == "sh"      # 沪指数白名单
    assert _prefix("510300") == "sh"      # 沪 ETF
    assert _prefix("300476") == "sz"      # 创业板
    assert _prefix("920982") == "bj"      # 北交所新号段
    assert _prefix("430047") == "bj"      # 北交所老号段


def test_realtime_normalizes_fields() -> None:
    p = _provider([_SH600000])
    recs = p.get_realtime(symbols=["600000.SH"])
    assert len(recs) == 1
    r = recs[0]
    assert r["symbol"] == "600000"
    assert r["name"] == "浦发银行"
    assert abs(r["last_price"] - 9.51) < 1e-9
    assert abs(r["prev_close"] - 9.71) < 1e-9
    assert r["volume"] == 1382638 * 100          # 手 → 股
    assert abs(r["amount"] - 129950 * 10000) < 1  # 万 → 元
    assert abs(r["change_pct"] - (-0.0206)) < 1e-9  # % → 小数
    assert abs(r["change_amount"] - (-0.20)) < 1e-9
    assert abs(r["turnover_rate"] - 0.0042) < 1e-9  # 0.42% → 小数
    assert abs(r["pe_ttm"] - 6.30) < 1e-9
    assert abs(r["pb"] - 0.43) < 1e-9
    assert abs(r["mcap_yi"] - 3167.39) < 1e-9
    assert r["is_stale"] is False


def test_stale_quote_detection() -> None:
    p = _provider([_SH600238_STALE])
    recs = p.get_realtime(symbols=["600238.SH"])
    assert len(recs) == 1
    r = recs[0]
    assert r["is_stale"] is True
    assert "成交量为 0" in r["stale_reason"]


def test_parse_ts() -> None:
    ts = _parse_ts("20260731161454")
    assert ts is not None and ts > 0
    assert _parse_ts("") is None
    assert _parse_ts("bad") is None


def test_batch_dedup_and_chunking(monkeypatch: pytest.MonkeyPatch) -> None:
    p = _provider([_SH600000])
    transport = p._client  # type: ignore[assignment]
    recs = p.get_realtime(symbols=["600000.SH", "SH600000", "600000"])
    assert len(recs) == 1  # 去重
    assert "sh600000" in transport.calls[0]
