"""三重对账 (SDC-01, 43-01)。

staged 09:25 撮合行 vs stockdb ``/v1/minute`` 09:30 bar (两条独立端点互证):
price 1e-6 / vol 恒等 (手) / amount 仅 OHLC 全等时派生 (实测 173×100×1308.66
= 22,639,818; 非全等 → amount UNKNOWN, 绝不猜, Pitfall 7)。mismatch → 不升
canonical 前置 (43-02 提审 gate); 09:30 bar 缺失 → 300s 重试 1 次 → 仍无 →
pending (A5, 不误报 mismatch)。

对账读 stockdb 直连 (09:40 时点 AQ kline_minute 湖无当日分区, Pitfall 4);
``end=T+1`` 端日语义 (Phase 40 Pitfall 3, provider 内置)。对账结果原子写回
``date={T}/manifest.json`` 的 ``reconciliation`` 块 (旧键保留), 供 43-02 提审
gate 与 43-03 告警判定消费。
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl

from app.data_providers.stockdb_provider import _to_suffix
from app.services.auction_capture import _DATE_RE, _STAGING_ROOT

logger = logging.getLogger(__name__)

# 对账容差 — 镜像 verify_auction_backfill [4] 既有 1e-6 断言
_PRICE_TOL = 1e-6


def reconcile_match(match: dict, bar: dict, tol: float = _PRICE_TOL) -> dict:
    """三重闭合: 09:25 撮合行 vs 分钟 09:30 bar。

    Args:
        match: staged 09:25 撮合行 ``{"price", "vol_hand"}`` (元 / 手)。
        bar: 分钟 09:30 行 canonical 列 (``close``/``volume`` 元/手, Phase 40 契约
            volume 恒等 ×1; 对账字段以 provider.get_minute canonical 列名为准)。

    Returns:
        {"status": "closed"|"mismatch", "checks": {price_eq, vol_eq, amount_closure[, amount_reason]},
         "amount_derived": bool} — amount 仅 OHLC 全等时派生 (42-02 规则, 契约 22,639,818);
         OHLC 不全等 → amount UNKNOWN (amount_reason="ohlc_not_closed"), 绝不猜 (Pitfall 7)。
    """
    price = float(match["price"])
    vol_hand = int(match["vol_hand"])
    close = float(bar["close"])
    volume = int(bar["volume"])
    checks = {
        "price_eq": abs(price - close) <= tol,
        "vol_eq": vol_hand == volume,
    }
    ohlc_closed = (
        float(bar["open"]) == float(bar["high"]) == float(bar["low"]) == close
    )
    if ohlc_closed:
        # 纯净竞价 bar (OHLC 全等) 才派生 amount: 09:25 price×vol×100 == 09:30 volume×close×100
        checks["amount_closure"] = abs(price * vol_hand * 100 - volume * close * 100) <= tol
    else:
        checks["amount_closure"] = False
        checks["amount_reason"] = "ohlc_not_closed"
    return {
        "status": "closed" if all(checks.values()) else "mismatch",
        "checks": checks,
        "amount_derived": ohlc_closed,
    }


def _fetch_0930_bar(provider: Any, symbol: str, trade_date: date, retry_sleep: float) -> dict | None:
    """GET /v1/minute 09:30 bar (end=T+1 端日语义, provider 内置); 缺失 → 重试 1 次。"""
    start = datetime.combine(trade_date, datetime.min.time())
    end = datetime.combine(trade_date + timedelta(days=1), datetime.min.time())
    for attempt in (0, 1):
        df = provider.get_minute([symbol], start_time=start, end_time=end)
        if df is not None and not df.is_empty():
            bar09 = df.filter(
                (pl.col("datetime").dt.hour() == 9) & (pl.col("datetime").dt.minute() == 30)
            )
            if not bar09.is_empty():
                return bar09.sort("datetime").head(1).to_dicts()[0]
        if attempt == 0 and retry_sleep > 0:
            time.sleep(retry_sleep)
    return None


def _update_manifest_reconciliation(stage_dir: Path, payload: dict) -> Path:
    """读旧 manifest.json → 增 ``reconciliation`` 块 → temp + os.replace 原子更新 (旧键保留)。"""
    path = stage_dir / "manifest.json"
    if not path.exists():
        return path  # 旧 manifest 缺失 → 不伪造 (调用方已判 staging_missing)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return path
    manifest["reconciliation"] = payload
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def reconcile_window(
    provider: Any,
    data_dir: Path,
    trade_date: date,
    *,
    retry_sleep: float = 300.0,
) -> dict:
    """读 staging 09:25 撮合行 → 逐 symbol 09:30 bar 三重对账 → manifest.reconciliation。

    - 无 staging / 无撮合行 / manifest 缺失 → {"status": "staging_missing", "checks": {}}
      (诚实不伪造, 供 43-03 告警判定)。
    - 09:30 bar 缺失 → sleep(retry_sleep) 重试 1 次 (测试注入 0) → 仍无 → per-symbol
      pending + 顶层 {"status": "pending", "reason": "no_0930_bar"} (A5)。

    Returns:
        {"status": "closed"|"mismatch"|"pending"|"staging_missing",
         "checks": {symbol: reconcile_match 结果 | {"status": "pending", "reason": …}},
         "trading_day_confirmed": bool (09:30 bar 存在 — 43-03 交易日数据在场判定同源),
         "amount_derived_symbols": [symbol, …]}
    """
    iso = trade_date.isoformat()
    if not _DATE_RE.fullmatch(iso):
        raise ValueError(f"invalid trade_date: {iso!r}")

    stage_dir = data_dir / _STAGING_ROOT / f"date={iso}"
    manifest_path = stage_dir / "manifest.json"
    part_path = stage_dir / "part.parquet"
    if not manifest_path.exists() or not part_path.exists():
        return {
            "status": "staging_missing", "checks": {},
            "trading_day_confirmed": False, "amount_derived_symbols": [],
        }

    df = pl.read_parquet(part_path)
    matches = df.filter((pl.col("time") == "09:25:00") & (pl.col("num_trades") > 0))
    if matches.is_empty():
        return {
            "status": "staging_missing", "checks": {},
            "trading_day_confirmed": False, "amount_derived_symbols": [],
        }

    checks: dict[str, dict] = {}
    trading_day_confirmed = False
    amount_derived_symbols: list[str] = []
    for sym in sorted(matches["symbol"].unique().to_list()):
        row = matches.filter(pl.col("symbol") == sym).sort("time").head(1).to_dicts()[0]
        match = {"price": float(row["price"]), "vol_hand": int(row["vol_hand"])}
        bar = _fetch_0930_bar(provider, _to_suffix(sym), trade_date, retry_sleep)
        if bar is None:
            checks[sym] = {"status": "pending", "reason": "no_0930_bar"}
            continue
        trading_day_confirmed = True
        res = reconcile_match(match, bar)
        checks[sym] = res
        if res["amount_derived"]:
            amount_derived_symbols.append(sym)

    if all(c.get("status") == "closed" for c in checks.values()):
        status = "closed"
    elif any(c.get("status") == "pending" for c in checks.values()):
        status = "pending"
    else:
        status = "mismatch"

    result = {
        "status": status,
        "checks": checks,
        "trading_day_confirmed": trading_day_confirmed,
        "amount_derived_symbols": amount_derived_symbols,
    }
    if status == "pending":
        result["reason"] = "no_0930_bar"
    _update_manifest_reconciliation(stage_dir, result)
    return result
