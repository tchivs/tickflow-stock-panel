"""Tencent finance (qt.gtimg.cn) realtime A-share quote provider.

Free, no-IP-block HTTP endpoint (GBK, ``~``-delimited 88 fields). This is the
second-priority source in the a-stock-data provider policy (mootdx first,
Tencent second, Eastmoney last — Tencent's PE/PB/mcap/turnover/limit fields
cover most realtime needs without Eastmoney's rate-limiting).

Adapter is modeled on a-stock-data's ``tencent_quote()`` (prefix routing,
field indices, stale-quote detection), extended with:
  - batch chunking (全市场 ~5500 symbols in chunks, one request per chunk)
  - symbol normalization from ``603196.SH``/``SH603196``/``603196`` forms
  - output normalized to the quote_service records shape
    (symbol/name/last_price/prev_close/open/high/low/volume/amount/change_pct/
    change_amount/amplitude/turnover_rate/timestamp/session)
  - ``is_stale`` flag for migrated BSE old-segment (43/83/87) or halted codes
    that Tencent still answers with frozen quotes (vol 0, price==prev_close)
"""
from __future__ import annotations

import logging

import httpx

from app.data_providers.base import ProviderCapabilities

logger = logging.getLogger(__name__)

# 沪指数白名单: 000xxx 但属沪市指数, 不能落到 sz (会返回空或错票)。
SH_INDEX = {"000300", "000905", "000016", "000688", "000852", "000010"}
# 北交所老号段 (多数已迁 920xxx, 老码会返回僵尸报价)。
BSE_OLD_SEGMENTS = {"43", "83", "87"}

_QUOTE_URL = "https://qt.gtimg.cn/q="
# 单请求代码数上限 (URL 长度 / 响应体积平衡; 实测 300 只安全)。
_BATCH = 200
# 腾讯对连续 5000+ 请求限流(非封 IP), 但实时轮询是低 QPS, 无需节流。
_TIMEOUT = 10.0


def _norm_symbol(symbol: str) -> str:
    """任意写法 → 6 位裸代码 (603196.SH / SH603196 / 603196 均支持)。"""
    s = str(symbol).strip()
    if s.lower().startswith(("sh", "sz", "bj")):
        return s[2:]
    return s.split(".")[0]


def _prefix(code: str) -> str:
    """6 位代码 → sh/sz/bj 前缀 (与 a-stock-data get_prefix 一致)。"""
    c = code.lower()
    if c.startswith(("sh", "sz", "bj")):
        return c[:2]
    if c.startswith("92"):
        return "bj"
    if c.startswith(("5", "6", "9")):
        return "sh"
    if c.startswith(("4", "8")):
        return "bj"
    if code in SH_INDEX:
        return "sh"
    return "sz"


class TencentRealtimeProvider:
    """Free realtime quotes from qt.gtimg.cn, normalized for quote_service."""

    name = "tencent"
    display_name = "腾讯实时 (免费)"
    capabilities = ProviderCapabilities(
        instruments=False,
        daily=False,
        adj_factor=False,
        minute=False,
        realtime=True,
        financial=False,
    )

    def __init__(self, base_url: str = _QUOTE_URL, timeout: float = _TIMEOUT,
                 batch: int = _BATCH) -> None:
        self.base_url = base_url
        self._timeout = timeout
        self._batch = batch
        self._client = httpx.Client(timeout=timeout, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def get_realtime(
        self,
        universes: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> list[dict]:
        """Fetch realtime quotes.

        ``symbols``: list of any symbol form (``603196.SH``/``SH603196``/``603196``).
        ``universes``: accepted for signature parity; Tencent has no universe
        concept, so a universe name maps to nothing (caller passes symbols).
        Returns quote_service-shaped records.
        """
        if not symbols:
            return []
        # 去重 + 归一化 + 分批
        unique: dict[str, str] = {}
        for symbol in symbols:
            code = _norm_symbol(symbol)
            if code:
                unique.setdefault(code, symbol)
        codes = list(unique)
        records: list[dict] = []
        for i in range(0, len(codes), self._batch):
            chunk = codes[i:i + self._batch]
            records.extend(self._fetch_chunk(chunk))
        return records

    def _fetch_chunk(self, codes: list[str]) -> list[dict]:
        """单批: 拼 URL → GBK 解码 → 逐行解析为 quote_service records。"""
        prefixed = [f"{_prefix(c)}{c}" for c in codes]
        try:
            resp = self._client.get(self.base_url + ",".join(prefixed))
            resp.raise_for_status()
            text = resp.content.decode("gbk", errors="replace")
        except Exception as e:
            logger.warning("tencent realtime chunk %d codes failed: %s", len(codes), e)
            return []
        records: list[dict] = []
        for line in text.strip().split(";"):
            if not line.strip() or "=" not in line or '"' not in line:
                continue
            key = line.split("=")[0].rsplit("_", 1)[-1]  # 去 v_ 前缀
            vals = line.split('"')[1].split("~")
            if len(vals) < 53:
                continue
            rec = self._parse_vals(key, vals)
            if rec is not None:
                records.append(rec)
        return records

    @staticmethod
    def _parse_vals(key: str, f: list[str]) -> dict | None:
        """腾讯字段 → quote_service record。索引见 a-stock-data 实测校准表。"""
        price = _num(f[3])
        prev_close = _num(f[4])
        open_ = _num(f[5])
        high = _num(f[33])
        low = _num(f[34])
        volume_lots = _num(f[36])  # 手
        amount_wan = _num(f[37])   # 万元
        change_amt = _num(f[31])
        change_pct = _num(f[32])
        # 腾讯 32 是涨跌幅%(如 -2.06), 内部 enriched 用小数制 (0.0206), 转小数。
        if change_amt == 0 and price > 0 and prev_close > 0:
            change_amt = price - prev_close
        if change_pct == 0 and change_amt != 0 and prev_close > 0:
            change_pct = change_amt / prev_close
        else:
            change_pct = change_pct / 100.0
        turnover_pct = _num(f[38])  # 换手率%(4.55), 转小数 0.0455

        # 僵尸报价检测: 成交量 0 且 现价==昨收 → 废码/停牌, 不用于估值。
        is_stale = volume_lots == 0 and price == prev_close and price > 0
        stale_reason = ""
        if is_stale:
            if key[2:4] in BSE_OLD_SEGMENTS:
                stale_reason = "北交所老号段,多数已迁 920xxx,请按名称反查现行代码"
            else:
                stale_reason = "成交量为 0(停牌/未开盘/废码),报价非当日真实成交"

        code = key[2:]  # 去 sh/sz/bj 前缀
        return {
            "symbol": code,
            "name": f[1],
            "last_price": price,
            "prev_close": prev_close,
            "open": open_,
            "high": high,
            "low": low,
            "volume": volume_lots * 100,        # 手 → 股
            "amount": amount_wan * 10000,       # 万 → 元
            "change_pct": change_pct,
            "change_amount": change_amt,
            "amplitude": _num(f[43]) / 100.0,   # 振幅% → 小数
            "turnover_rate": turnover_pct / 100.0,
            "pe_ttm": _num(f[39]),
            "pb": _num(f[46]),
            "float_mcap_yi": _num(f[44]),
            "mcap_yi": _num(f[45]),
            "limit_up": _num(f[47]),
            "limit_down": _num(f[48]),
            "vol_ratio": _num(f[49]),
            "timestamp": _parse_ts(f[30]),
            "session": "realtime",
            "is_stale": is_stale,
            "stale_reason": stale_reason,
        }


def _num(value: str | None) -> float:
    try:
        return float(value) if value else 0.0
    except (TypeError, ValueError):
        return 0.0


def _parse_ts(value: str | None) -> int | None:
    """20260731161454 → Unix 毫秒 (本地时区解释为 Asia/Shanghai 近似)。"""
    if not value or len(value) < 14:
        return None
    try:
        import time as _time
        return int(_time.mktime(_time.strptime(value, "%Y%m%d%H%M%S")) * 1000)
    except ValueError:
        return None
