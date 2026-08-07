"""xyz (a.123128.xyz) remote market-data provider via its online MCP endpoint.

The xyz service exposes the full free-stockdb SDK (2005-present history) over a
remote JSON-RPC MCP endpoint (https://a.123128.xyz homepage, 07-27 entry):

    {"mcpServers": {"stockdb": {"url": "http://8.138.149.215:7898/mcp"}}}

This provider is the historical complement for minute K (and daily) that the
self-hosted free-stockdb HTTP server lacks (it only carries synced recent
data). It implements the JSON-RPC 2.0 streamable MCP client for the tools we
consume: stockdb_get_price (bars window) and stockdb_get_bars.

Protocol facts verified live against the endpoint:
  - POST JSON-RPC; respond with a single JSON object (HTTP, not stdio).
  - tools/call -> {"jsonrpc":"2.0","result":{"content":[{"type":"text","text":"<payload>"}]}}
    where <payload> is a Python-repr-ish JSON list of row dicts.
  - stockdb_get_price arguments: security (list[str] REQUIRED), start_date,
    end_date (YYYY-MM-DD), frequency ('1d'/'1m'/'5m'/...), fq ('pre'/'post'/None).
    Do NOT pass ``fields`` — the endpoint returns 请求参数错误 when fields is set.
  - Rows: {"time": "YYYY-MM-DDTHH:MM:SS", "code": str, "open"/"high"/"low"/"close",
    "volume", "money", ...}.
  - stockdb_get_bars: security (list), count, unit ('1d'/'1m'/...), end_dt.
    Rows: {"date": "YYYY-MM-DDTHH:MM:SS", "open", "high", "low", "close", ...}.
  - stockdb_get_call_auction: security (list — 恰 1 码/请求, 上游带宽限制批量
    请求), start_date, end_date (YYYY-MM-DD). 同样 Do NOT pass ``fields``.
    Rows: {"code": str, "time": "YYYY-MM-DDTHH:MM:SS", "volume", "money",
    "current", ...}. 上游只发 09:25:00 集合竞价撮合行。
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import date, datetime
from typing import Any

import httpx
import polars as pl

from app.data_providers.base import AssetType, ProviderCapabilities, SourceBlockedError

logger = logging.getLogger(__name__)

_DEFAULT_MCP_URL = "http://8.138.149.215:7898/mcp"

# 策略封锁文案 markers (HON-01 双信号分类器文案面; HTTP 403 为状态码面)。
# 配额窗 2h 复现时按真实响应体回填定稿 (RESEARCH UNKNOWN flag)。
_POLICY_BLOCK_MARKERS = ("配额", "带宽", "限速", "限流", "频率", "频繁", "forbidden", "blocked", "denied")


def _is_policy_block(status: int, text: str) -> bool:
    """双信号分类器: HTTP 403 或文案命中策略封锁 markers → True。

    状态码面 (403) 与文案面 (200 载荷内 error 串等) 互斥取或; 其余 4xx/5xx
    与超时/连接错误不命中 → 空帧契约不变 (Test 4 :126-137 保持绿)。
    """
    if status == 403:
        return True
    lowered = text.lower()
    return any(m in lowered for m in _POLICY_BLOCK_MARKERS)


class XYZProvider:
    """HTTP JSON-RPC MCP client for the xyz stockdb online endpoint."""

    name = "xyz"
    capabilities = ProviderCapabilities(
        instruments=True,
        daily=True,
        adj_factor=False,
        minute=True,
        realtime=False,
        financial=False,
        auction=True,
    )

    def __init__(self, mcp_url: str = _DEFAULT_MCP_URL, timeout: float = 8.0) -> None:
        self.mcp_url = mcp_url
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)
        self._request_id = 0

    def close(self) -> None:
        self._client.close()

    # -- provider surface -------------------------------------------------------

    def get_daily(
        self,
        symbols: list[str],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        asset_type: AssetType = "stock",
    ) -> pl.DataFrame:
        return self._price_frame(symbols, start_time, end_time, frequency="1d")

    def get_minute(
        self,
        symbols: list[str],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        freq: str = "1m",
    ) -> pl.DataFrame:
        return self._price_frame(symbols, start_time, end_time, frequency=freq)

    def get_adj_factors(
        self,
        symbols: list[str],
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        asset_type: AssetType = "stock",
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def get_instruments(self, asset_type: AssetType = "stock") -> pl.DataFrame:
        return pl.DataFrame()

    def get_realtime(
        self,
        universes: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> pl.DataFrame:
        return pl.DataFrame()

    # -- MCP protocol -----------------------------------------------------------

    def _price_frame(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        frequency: str,
    ) -> pl.DataFrame:
        if not symbols:
            return pl.DataFrame()
        args: dict[str, Any] = {"security": [str(s).split(".")[0] for s in symbols], "frequency": frequency}
        if start_time is not None:
            args["start_date"] = start_time.strftime("%Y-%m-%d")
        if end_time is not None:
            args["end_date"] = end_time.strftime("%Y-%m-%d")
        try:
            payload = self._call_tool("stockdb_get_price", args)
        except SourceBlockedError as e:
            # daily/minute 路径 (scope 决策): 策略封锁 → 空帧降级保留, 契约不变
            logger.warning("xyz %s source blocked (daily/minute 空帧降级): %s", frequency, e)
            return pl.DataFrame()
        rows = _parse_payload(payload)
        if not rows:
            return pl.DataFrame()
        frames: list[pl.DataFrame] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ts = row.get("time") or row.get("date")
            if not ts:
                continue
            dt = _parse_iso(ts)
            if dt is None:
                continue
            symbol = str(row.get("code") or symbols[0]).split(".")[0]
            frames.append(pl.DataFrame({
                "symbol": [symbol],
                "datetime": [dt],
                "open": [_num(row.get("open"))],
                "high": [_num(row.get("high"))],
                "low": [_num(row.get("low"))],
                "close": [_num(row.get("close"))],
                "volume": [_num(row.get("volume"))],
                "amount": [_num(row.get("money"))],
                "freq": [frequency],
            }))
        if not frames:
            return pl.DataFrame()
        return pl.concat(frames, how="diagonal_relaxed")

    def get_auction(
        self,
        symbols: list[str],
        start_date: date | datetime | None = None,
        end_date: date | datetime | None = None,
    ) -> pl.DataFrame:
        """拉取集合竞价撮合行 (stockdb_get_call_auction) 并映射为 canonical 子集列。

        契约:
          - 每次请求恰 1 个 symbol —— 上游带宽上限 (批量请求返回错误
            「带宽限制批量请求, 检测到 N 个代码」); 多码/空列表 → ValueError
            fail-fast, 绝不静默截断或批处理。
          - 不传 ``fields`` 参数 —— 上游返回 请求参数错误 (probe #2 实测)。
          - ``end_date is None`` → 单交易日形式 (start_date == end_date ==
            trade_date), 兼容 auction_probe._default_fetcher 与 custom/provider
            的单 date 调用; 范围形式 (backfill 路径) 由两端显式传入。
          - 返回 symbol 带请求后缀 (``000001.SZ``), 与 kline_daily 一致 ——
            kline_auction merge-upsert 键 [symbol, datetime] 要求后缀一致, 否则
            回填行与 EOD 行同股两键 (同日碰撞规则)。
        网络错误 → _call_tool 返回 "" (或异常) → 空 pl.DataFrame() 不抛; 空 vs
        宕机由调用方闸门区分 (诚实 fail-closed)。策略封锁 (HTTP 403 / 配额窗) →
        _call_tool 抛 SourceBlockedError → 原样上抛 (typed 信号直达调用方,
        绝不吞成空帧 —— 36-03 事故链闭环)。
        """
        if len(symbols) != 1:
            raise ValueError(
                f"stockdb_get_call_auction 每次仅支持 1 个代码, 收到 {len(symbols)} 个"
            )
        if start_date is None:
            raise ValueError("get_auction 需要 start_date (单日期形式下即交易日)")
        if end_date is None:
            start_date = end_date = start_date

        args: dict[str, Any] = {
            "security": [str(symbols[0]).split(".")[0]],
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
        }
        try:
            payload = self._call_tool("stockdb_get_call_auction", args)
        except SourceBlockedError:
            # 策略封锁信号直达调用方 (台账/终态/verify 门/探针判定), 绝不吞成空帧
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("xyz stockdb_get_call_auction failed: %s", e)
            return pl.DataFrame()
        rows = _parse_payload(payload)
        if not rows:
            return pl.DataFrame()

        suffix_map = {str(s).split(".")[0]: str(s) for s in symbols}
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            ts = row.get("time")
            if not ts:
                continue
            dt = _parse_iso(ts)
            if dt is None:
                continue
            code = str(row.get("code") or "")
            record = {
                "symbol": suffix_map.get(code.split(".")[0], code),
                "datetime": dt,
                "auction_volume": _num(row.get("volume")),
                "auction_amount": _num(row.get("money")),
            }
            # 可选列: 上游提供才产出 (诚实缺列不 0 填)
            if row.get("current") is not None:
                record["auction_virtual_price"] = _num(row.get("current"))
            out.append(record)

        if not out:
            return pl.DataFrame()
        return pl.DataFrame(out)

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        self._request_id += 1
        body = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        try:
            resp = self._client.post(
                self.mcp_url,
                headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
                json=body,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else 0
            text = e.response.text if e.response is not None else str(e)
            if _is_policy_block(status, text):
                raise SourceBlockedError(f"xyz {name} source blocked (HTTP {status})") from e
            logger.warning("xyz %s failed: HTTP %s", name, status)
            return ""
        except Exception as e:  # noqa: BLE001
            logger.warning("xyz %s failed: %s", name, e)
            return ""
        if "error" in data:
            err_text = str(data["error"])
            if _is_policy_block(200, err_text):
                raise SourceBlockedError(f"xyz {name} source blocked: {err_text[:200]}")
            logger.warning("xyz %s error: %s", name, data["error"])
            return ""
        content = (data.get("result") or {}).get("content") or []
        texts = [c.get("text", "") for c in content if isinstance(c, dict)]
        return "\n".join(texts)


def _parse_payload(text: str) -> list[Any]:
    """Parse the MCP tool payload. The endpoint returns a Python-repr-ish list;
    it is JSON when well-formed, otherwise fall back to a tolerant parse."""
    text = text.strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Some endpoints wrap the repr in quotes or return a single quoted string.
    try:
        return json.loads(text.replace("'", '"'))
    except json.JSONDecodeError:
        return []


def _parse_iso(value: str) -> datetime | None:
    value = str(value).strip()
    if not value:
        return None
    value = value.replace("Z", "")
    try:
        return datetime.fromisoformat(value[:19])
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d")
        except ValueError:
            return None


def _num(value: Any) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0
