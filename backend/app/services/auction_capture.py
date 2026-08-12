"""竞价窗口采集驱动 (SDC-01, 43-01)。

09:26 单次 GET /v1/ticks/{symbol}?date=T 触发服务端 fetch-on-miss 全窗口采集
(kernel/service.py:488-490: 湖缺失 → collect_tick 全窗口一次落盘; 文件存在只读
不刷新) → 三重完整性校验 (归属日==T ∧ 09:25:00 num_trades>0 撮合行 ∧ 窗口 ≥40)
fail-closed → 原子写 ``data/tick_staging/date={T}/part.parquet`` (10 列 TickBar
全保留) + manifest.json。**绝不写 canonical kline_auction** (虚拟量非成交);
**绝不盘中轮询** (轮询 = 600 次 GET 同一份内容 + 60/min 限频打爆, [CRITICAL]
反模式)。

采集池 (A2): 配置白名单 ``auction_sidecar_symbols`` (非空优先) → 缺省 watchlist
自选池; 硬 cap ≤200 (pool-gated, 5537 全量盘中不可行 descope); symbol 归一
suffix→prefix (``stockdb_provider._to_prefix`` 单一事实源), 归一失败 → failed
reason (不猜)。

fail-closed: 任一 symbol 完整性失败 → 该 symbol 不落分区 + reason; 全失败 →
无分区不 mkdir (绝不写半成品)。
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import polars as pl

from app.data_providers.stockdb_provider import _SYMBOL_PREFIX_RE, _to_prefix

logger = logging.getLogger(__name__)

# staging 湖根目录 (相对 data_dir) — 与 canonical kline_auction 物理分离
_STAGING_ROOT = "tick_staging"
# 目录名严格 ^\d{4}-\d{2}-\d{2}$ (防路径穿越, T-27-01-02, 镜像 premarket_snapshot)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# 窗口行数阈值 (3s 快照级 × 10min 理论 ≈200 / 实测 85 的保守阈值, A1)
_WINDOW_MIN_ROWS = 40
# 池硬 cap (A2 pool-gated, 5537 全量盘中不可行 descope)
_POOL_CAP = 200

# staging 10 列 = TickBar 全字段保留 (顺序冻结; 43-02 提审按此读契约)
_STAGING_COLS = [
    "symbol", "trade_date", "time", "price", "vol_hand", "num_trades",
    "buyorsell", "source", "fetched_at", "ingested_at",
]

_SH_TZ = ZoneInfo("Asia/Shanghai")


def _json_default(obj: Any) -> Any:
    """处理 date/datetime 等 JSON 不认识的类型 (镜像 premarket_snapshot._json_default)。"""
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _trade_date_compact(value: Any) -> str:
    """TickBar trade_date → ``YYYYMMDD`` 紧凑形态。

    服务端实测返回 ISO 形态 ``2026-08-11T00:00:00+08:00`` (stockdb_provider.get_ticks
    原始 JSON 未归一化); 夹具/旧路径亦见紧凑 ``20260807``。统一抽前 8 位数字 →
    ``YYYYMMDD``, 两种形态同义 (归属日判定只看日期, 忽略时分秒/时区)。
    空/None/非法 → "" (永不匹配, fail-closed)。
    """
    s = str(value or "").strip()
    if not s:
        return ""
    return "".join(ch for ch in s if ch.isdigit())[:8]


def _validate_tick_window(rows: list[dict], trade_date: str) -> dict:
    """fail-closed 完整性校验 (Pattern 1 骨架): 归属日==T ∧ 09:25:00 撮合行 ∧ 窗口覆盖。

    Args:
        rows: provider.get_ticks 原始返回 (TickBar dict 列表)。
        trade_date: 归属日紧凑形态 (``YYYYMMDD``)。

    Returns:
        {"ok": bool, "window_rows": int, "match_rows": int} — ok 任一条件失败即 False。
    """
    if not rows:
        return {"ok": False, "window_rows": 0, "match_rows": 0}
    r09 = [r for r in rows if "09:15:00" <= str(r.get("time", "")) <= "09:25:04"]
    match = [r for r in r09 if int(r.get("num_trades") or 0) > 0]
    ok = (
        all(_trade_date_compact(r.get("trade_date")) == trade_date for r in rows)  # 归属日==T
        and any(str(r.get("time")) == "09:25:00" for r in match)                    # 09:25 撮合行存在
        and len(r09) >= _WINDOW_MIN_ROWS                                           # 窗口覆盖阈值
    )
    return {"ok": ok, "window_rows": len(r09), "match_rows": len(match)}


def _parse_tz_utc(value: Any) -> datetime | None:
    """ISO 时间串 → aware UTC datetime; 空/None → None。"""
    if value is None or value == "":
        return None
    dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _normalize_rows(rows: list[dict], iso: str) -> list[dict]:
    """TickBar dict → staging 10 列归一化行 (契约单点)。

    trade_date → datetime[us, Asia/Shanghai] aware 00:00; fetched_at/ingested_at →
    datetime[us, UTC] aware; time 保留 str ``HH:MM:SS``; 其余字段数值化。
    """
    trade_dt = datetime.fromisoformat(iso).replace(tzinfo=_SH_TZ)
    out: list[dict] = []
    for r in rows:
        out.append({
            "symbol": str(r.get("symbol")),
            "trade_date": trade_dt,
            "time": str(r.get("time", "")),
            "price": float(r.get("price", 0.0)),
            "vol_hand": int(r.get("vol_hand", 0)),
            "num_trades": int(r.get("num_trades", 0)),
            "buyorsell": int(r.get("buyorsell", 0)),
            "source": str(r.get("source", "")),
            "fetched_at": _parse_tz_utc(r.get("fetched_at")),
            "ingested_at": _parse_tz_utc(r.get("ingested_at")),
        })
    return out


def _write_staging_partition(rows: list[dict], out_dir: Path) -> Path:
    """归一化行 → ``out_dir/part.parquet`` (10 列 schema 冻结, temp + os.replace 原子写)。"""
    df = pl.DataFrame(rows, schema={
        "symbol": pl.Utf8,
        "trade_date": pl.Datetime("us", time_zone="Asia/Shanghai"),
        "time": pl.Utf8,
        "price": pl.Float64,
        "vol_hand": pl.Int64,
        "num_trades": pl.Int64,
        "buyorsell": pl.Int64,
        "source": pl.Utf8,
        "fetched_at": pl.Datetime("us", time_zone="UTC"),
        "ingested_at": pl.Datetime("us", time_zone="UTC"),
    }).select(_STAGING_COLS)
    path = out_dir / "part.parquet"
    tmp = path.with_name(path.name + ".tmp")
    df.write_parquet(tmp)
    os.replace(tmp, path)
    return path


def _write_manifest(out_dir: Path, payload: dict) -> Path:
    """manifest.json 原子写 (temp + os.replace; 镜像 premarket_snapshot)。"""
    path = out_dir / "manifest.json"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    os.replace(tmp, path)
    return path


def resolve_sidecar_pool() -> dict:
    """采集池解析 (A2): 配置白名单 (非空优先) → 缺省 watchlist 自选池; ≤200 硬 cap。

    - 白名单: ``preferences.auction_sidecar_symbols`` (镜像 auction_sync_symbols 形态)。
    - 缺省: ``tickflow.pools.get_pool("watchlist")`` (读 data/user_data/watchlist.parquet)。
    - symbol 归一 suffix→prefix (``_to_prefix`` 单一事实源); 归一失败 → failed
      reason="unparsable_symbol" (不猜)。
    - 结果 > 200 → 截断前 200 + logger.warning 截断注记 (pool-gated; 截断事实由
      调用方 job 进台账, 本函数只负责返回)。

    Returns:
        {"symbols": [...], "pool_size": int (池总数含截断前/归一失败),
         "truncated": bool, "failed": [{symbol, reason}], "source": "whitelist"|"watchlist"}
    """
    from app.services import preferences
    from app.tickflow.pools import get_pool

    raw = preferences.get_auction_sidecar_symbols()
    source = "whitelist" if raw else "watchlist"
    if not raw:
        raw = list(get_pool("watchlist"))

    symbols: list[str] = []
    failed: list[dict] = []
    for s in raw:
        prefix = _to_prefix(str(s).strip())
        if _SYMBOL_PREFIX_RE.match(prefix):
            symbols.append(prefix)
        else:
            failed.append({"symbol": str(s), "reason": "unparsable_symbol"})

    pool_size = len(raw)  # 池总数 = 配置/自选原始条目数 (含归一失败与截断前)
    truncated = False
    if len(symbols) > _POOL_CAP:
        logger.warning(
            "auction sidecar pool (%s) has %d symbols — truncated to %d (pool-gated cap)",
            source, len(symbols), _POOL_CAP,
        )
        symbols = symbols[:_POOL_CAP]
        truncated = True
    return {
        "symbols": symbols, "pool_size": pool_size,
        "truncated": truncated, "failed": failed, "source": source,
    }


def capture_auction_window(
    provider: Any,
    symbols: list[str] | None,
    trade_date: date,
    data_dir: Path,
    *,
    pool: dict | None = None,
) -> dict:
    """逐 symbol GET ticks → 完整性校验 → 归一化 staging 原子写 + manifest (fail-closed)。

    - ``_DATE_RE`` fullmatch 前置守卫 (防路径穿越, T-27-01-01)。
    - ``symbols=None`` → 池解析 (``pool`` 或 ``resolve_sidecar_pool()``); 归一失败
      合并进 failed; manifest ``pool_size`` = 池总数 (含截断前)。
    - 任一 symbol 校验失败 → 该 symbol 不落分区 + reason ("incomplete:…").
    - 全失败 → 不 mkdir 不写分区 (绝不写半成品); 部分成功 → 原子写 part.parquet
      + manifest.json。

    Returns:
        {"requested": int (实际请求数), "ok": int, "failed": [{symbol, reason}]}
    """
    iso = trade_date.isoformat()
    if not _DATE_RE.fullmatch(iso):
        raise ValueError(f"invalid trade_date: {iso!r}")

    if symbols is None:
        pool_info = pool if pool is not None else resolve_sidecar_pool()
        symbols = list(pool_info["symbols"])
        pool_failed: list[dict] = list(pool_info.get("failed", []))
        pool_size = int(pool_info.get("pool_size", len(symbols)))
    else:
        pool_failed = []
        pool_size = len(symbols)

    failed: list[dict] = list(pool_failed)
    ok_rows: list[dict] = []
    symbols_ok: list[str] = []
    completeness: dict[str, dict] = {}
    trade_date_compact = iso.replace("-", "")

    for sym in symbols:
        try:
            rows = provider.get_ticks(sym, trade_date)
        except Exception as e:  # noqa: BLE001 — typed 异常由 provider 上抛, 采集侧记 reason
            failed.append({"symbol": sym, "reason": f"fetch_error:{type(e).__name__}"})
            continue
        check = _validate_tick_window(rows, trade_date_compact)
        completeness[sym] = check
        if not check["ok"]:
            failed.append({
                "symbol": sym,
                "reason": f"incomplete:window_rows={check['window_rows']},match_rows={check['match_rows']}",
            })
            continue
        ok_rows.extend(_normalize_rows(rows, iso))
        symbols_ok.append(sym)

    result = {"requested": len(symbols), "ok": len(symbols_ok), "failed": failed}
    if not ok_rows:
        return result  # fail-closed: 全失败 → 无分区

    out_dir = data_dir / _STAGING_ROOT / f"date={iso}"
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_staging_partition(ok_rows, out_dir)
    _write_manifest(out_dir, {
        "trade_date": iso,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pool_size": pool_size,
        "symbols_ok": symbols_ok,
        "symbols_failed": failed,
        "completeness": {
            "ok": all(c["ok"] for c in completeness.values()),
            "by_symbol": completeness,
        },
    })
    return result
