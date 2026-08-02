"""Tests for Tencent ifzq + Sina K-line providers.

All offline — fake transports return canned JSONP/JSON matching the verified
wire shapes. Prefix routing, qfq daily parsing, mkline minute mapping
(1m/5m/15m/30m/60m → m1..m60), and Sina jsonp parsing are covered.
"""
from __future__ import annotations

import json as _json
from datetime import datetime
from typing import Any

from app.data_providers.ifzq_provider import (
    IfzqKlineProvider,
    SinaKlineProvider,
    _norm_symbol,
    _parse_mkline_ts,
    _parse_sina_dt,
    _prefix,
)


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self._text = text

    def raise_for_status(self) -> None:
        return None

    @property
    def text(self) -> str:
        return self._text

    def json(self):
        import json as _json

        return _json.loads(self._text)


class _JsonTransport:
    """Returns canned JSON per URL fragment (mkline/fqkline)."""

    def __init__(self, routes: dict[str, str]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url: str, params: dict[str, Any] | None = None, **kwargs: Any) -> _FakeResponse:
        param = (params or {}).get("param", "")
        self.calls.append(param)
        for fragment, body in self.routes.items():
            if fragment in param:
                return _FakeResponse(body)
        return _FakeResponse('{"code":-1,"msg":"nf"}')

    def close(self) -> None:
        pass


_QFQ_DAILY = {
    "sh600000": {
        "qfqday": [
            ["2026-07-30", "9.26", "9.71", "9.72", "9.25", "1617462.000"],
            ["2026-07-31", "9.59", "9.51", "9.59", "9.28", "1382638.000"],
        ]
    }
}

_MKLINE = {
    "code": 0,
    "data": {
        "sh600000": {
            "m5": [
                ["202607311400", "9.50", "9.51", "9.52", "9.49", "16916.00", {}, "0.51"],
                ["202607311405", "9.51", "9.52", "9.53", "9.50", "18300.00", {}, "0.55"],
            ]
        }
    },
}

_SINA_BODY = (
    "/*<script>location.href='//sina.com';</script>*/\n"
    "var sh600000=(["
    '{"day":"2026-07-31 14:55:00","open":"9.51","high":"9.53","low":"9.50",'
    '"close":"9.52","volume":"2137971","amount":"20320712.2925"},'
    '{"day":"2026-07-31 15:00:00","open":"9.53","high":"9.55","low":"9.51",'
    '"close":"9.51","volume":"3444228","amount":"32786297.5093"}'
    "]);"
)


def _ifzq(routes: dict[str, str]) -> IfzqKlineProvider:
    p = IfzqKlineProvider()
    p._client = _JsonTransport(routes)  # type: ignore[assignment]
    return p


def test_prefix_and_norm() -> None:
    assert _norm_symbol("600000.SH") == "600000"
    assert _prefix("600000") == "sh"
    assert _prefix("000001") == "sz"
    assert _prefix("510300") == "sh"
    assert _prefix("300476") == "sz"


def test_ifzq_daily_parses_qfq() -> None:
    p = _ifzq({"sh600000,day": _json.dumps({"code": 0, "data": _QFQ_DAILY})})
    df = p.get_daily(["600000.SH"], start_time=datetime(2026, 7, 30), end_time=datetime(2026, 7, 31))
    assert df.height == 2
    rows = df.sort("date").to_dicts()
    assert str(rows[0]["date"]) == "2026-07-30"
    assert abs(rows[0]["close"] - 9.71) < 1e-9
    assert rows[0]["volume"] == 1617462 * 100  # 手 → 股


def test_ifzq_minute_maps_freqs() -> None:
    for freq, key in (("1m", "m1"), ("5m", "m5"), ("15m", "m15"), ("30m", "m30"), ("60m", "m60")):
        routes = {key: _json.dumps({"code": 0, "data": {"sh600000": {key: _MKLINE["data"]["sh600000"]["m5"]}}})}
        p = _ifzq(routes)
        df = p.get_minute(["600000.SH"], freq=freq)
        assert df.height == 2, f"{freq} rows"
        assert "datetime" in df.columns
        assert df["freq"].to_list() == [freq, freq]


def test_parse_mkline_ts() -> None:
    ts = _parse_mkline_ts("202607311400")
    assert ts is not None and ts.minute == 0
    assert _parse_mkline_ts("bad") is None

def test_sina_jsonp_parses() -> None:
    class _SinaTransport:
        def get(self, url: str, params: dict[str, Any] | None = None, **kwargs: Any) -> _FakeResponse:
            return _FakeResponse(_SINA_BODY)

        def close(self) -> None:
            pass

    s = SinaKlineProvider()
    s._client = _SinaTransport()  # type: ignore[assignment]
    df = s.get_minute(["600000.SH"], freq="5m")
    assert df.height == 2
    assert str(df["datetime"].min()) == "2026-07-31 14:55:00"


def test_parse_sina_dt() -> None:
    assert _parse_sina_dt("2026-07-31 15:00:00") is not None
    assert _parse_sina_dt("2026-07-31") is not None
    assert _parse_sina_dt(None) is None
