"""竞价采集 sidecar 台账 — JSONL 追加 + 滚动清理 + W-5 终态键集 (SDC-03)。

职责:
  - 每 sidecar job (09:26 采集 / 09:40 对账 / EOD 15:40 提审) 跑完追加一行终态
    dict — W-5 键集: {job, trade_date, requested, ok, failed_symbols,
    reason?, started_at, finished_at}
  - 提供查询 (按 job 过滤、时间倒序、限量)
  - 滚动清理: 保留近 MAX_DAYS 天 + 上限 MAX_RECORDS 条 (镜像 alert_store.py:1-41)

键形纪律 (测试逐键断言):
  - 成功态 7 键: {job, trade_date, requested, ok, failed_symbols, started_at, finished_at}
  - fail-closed 追加 reason (8 键): ok==0 且未显式给 reason/skipped → 自动补
    "fail_closed" — ok==0 ⇒ reason 在场的键形不变量
  - 非交易日行追加 skipped ("no_data") — 与 reason 互斥 (假日不告警风暴)
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from app.market_time import cn_now

logger = logging.getLogger(__name__)

# 保留策略 (镜像 alert_store)
MAX_DAYS = 7
MAX_RECORDS = 5000
# 每隔多少次写入触发一次清理 (避免每次写都 prune)
PRUNE_EVERY = 20

_lock = threading.Lock()
_write_count = 0

# 告警 rule_id (逐字可断言)
RULE_CAPTURE_MISSING = "auction_sidecar_capture_missing"
RULE_RECONCILE_FAIL = "auction_sidecar_reconcile_fail"

# 交易日判定探针 (分钟 09:30 bar 存在 ⇒ 交易日; 数据在场判定, Q6/A5)
_BAR_PROBE_SYMBOL = "SH600519"
_BAR_TIME = datetime.min.time().replace(hour=9, minute=30)


def _path(data_dir: Path) -> Path:
    p = data_dir / "user_data" / "auction_sidecar_ledger.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _record_time(ev: dict) -> datetime | None:
    """台账行时间键 (started_at/finished_at, isoformat) → datetime; 解析失败 → None。"""
    for k in ("started_at", "finished_at"):
        v = ev.get(k)
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v)
            except ValueError:
                continue
    return None


def append_ledger(data_dir: Path, event: dict) -> None:
    """追加一行终态记录 (持锁写, JSONL append)。

    自动补 ``started_at``/``finished_at`` (CN 墙钟 isoformat seconds, 调用方可显式传入);
    ``ok==0`` 且无 ``reason``/``skipped`` → 自动补 ``reason="fail_closed"``
    (fail-closed 键形不变量: 失败态自带原因, 绝不无因失败)。
    """
    record = dict(event)
    now = cn_now().isoformat(timespec="seconds")
    record.setdefault("started_at", now)
    record.setdefault("finished_at", now)
    if record.get("ok") == 0 and "reason" not in record and "skipped" not in record:
        record["reason"] = "fail_closed"
    line = json.dumps(record, ensure_ascii=False)
    with _lock:
        p = _path(data_dir)
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        global _write_count
        _write_count += 1
        if _write_count >= PRUNE_EVERY:
            _write_count = 0
            _prune_locked(p)


def list_ledger(
    data_dir: Path,
    days: int = MAX_DAYS,
    limit: int = 100,
    job: str | None = None,
) -> list[dict]:
    """读取近 N 天台账行, 按时间倒序, 支持按 job 过滤。

    持锁读: prune 会整文件重写, 无锁读可能读到截断内容 (镜像 alert_store.list_recent)。
    """
    cutoff = cn_now() - timedelta(days=days)
    out: list[dict] = []
    p = _path(data_dir)
    if not p.exists():
        return []
    try:
        with _lock, p.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("auction_sidecar_ledger 跳过损坏行: %.80s", line)
                    continue
                t = _record_time(ev)
                if t is not None and t < cutoff:
                    continue
                if job is not None and ev.get("job") != job:
                    continue
                out.append(ev)
    except OSError as e:
        logger.warning("auction_sidecar_ledger read failed: %s", e)
        return []
    out.sort(key=lambda ev: _record_time(ev) or datetime.min, reverse=True)
    return out[:limit]


def read_sidecar_capture_state(data_dir: Path, trade_date: date | str) -> dict | None:
    """读 staging manifest 推导 09:26 采集终态 (供 09:40 告警判定); 无 manifest → None。

    返回键形与 ``evaluate_sidecar_alerts`` 的 capture 入参一致:
    {"requested", "ok", "failed_symbols", "completeness_ok"}。
    """
    if isinstance(trade_date, date):
        trade_date = trade_date.isoformat()
    p = data_dir / "tick_staging" / f"date={trade_date}" / "manifest.json"
    if not p.exists():
        return None
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("sidecar capture manifest 读取失败: %s", e)
        return None
    ok_list = m.get("symbols_ok") or []
    failed_list = m.get("symbols_failed") or []
    completeness = m.get("completeness") or {}
    pool_size = m.get("pool_size")
    failed_symbols = [
        f.get("symbol") if isinstance(f, dict) else str(f) for f in failed_list
    ] if isinstance(failed_list, list) else []
    return {
        "requested": pool_size if isinstance(pool_size, int) else len(ok_list) + len(failed_symbols),
        "ok": len(ok_list) if isinstance(ok_list, list) else 0,
        "failed_symbols": failed_symbols,
        "completeness_ok": completeness.get("ok") is True,
    }


def confirm_trading_day(
    provider,
    trade_date: date,
    probe_symbol: str = _BAR_PROBE_SYMBOL,
    retry_sleep: float = 300.0,
) -> bool:
    """交易日判定 — 数据在场 (分钟 09:30 bar 存在), AQ 无日历服务缺口下的诚实方案。

    09:30 bar 缺失 → ``sleep(retry_sleep)`` 重试 1 次 (服务端分钟采集 fetch-on-miss
    时延, A5; 测试注入 retry_sleep=0) → 仍无 → False。与 43-01 reconcile 的
    ``trading_day_confirmed`` 同源同判定点。
    """
    start = datetime.combine(trade_date, datetime.min.time())
    end = start + timedelta(days=1)
    for attempt in range(2):
        df = provider.get_minute([probe_symbol], start_time=start, end_time=end)
        if _has_0930_bar(df, probe_symbol):
            return True
        if attempt == 0:
            time.sleep(retry_sleep)
    return False


def _has_0930_bar(df, probe_symbol: str) -> bool:
    """分钟帧中 09:30 bar 存在性 (provider 输出 symbol 为后缀形态, datetime naive 北京墙钟)。"""
    if df is None or df.is_empty():
        return False
    if "datetime" not in df.columns:
        return False
    import polars as pl

    sel = df.filter(pl.col("datetime").dt.time() == _BAR_TIME)
    if probe_symbol and "symbol" in df.columns:
        from app.data_providers.stockdb_provider import _to_suffix

        sel = sel.filter(pl.col("symbol") == _to_suffix(probe_symbol))
    return not sel.is_empty()


def evaluate_sidecar_alerts(
    data_dir: Path,
    trade_date: str,
    capture: dict | None,
    reconcile: dict | None,
    trading_day: bool,
) -> list[dict]:
    """诚实门告警判定 (纯函数, 镜像 30-03 evaluate_premarket 可测形态)。

    触发 (SDC-03「09:26 后缺失可告」):
      - 交易日 ∧ 采集缺失/不完整 (ok < requested) → ``auction_sidecar_capture_missing``
        {ts, rule_id, source, trade_date, requested, ok, failed_symbols}
      - 交易日 ∧ 对账 mismatch → ``auction_sidecar_reconcile_fail``
        {ts, rule_id, source, trade_date, checks}
    非交易日 → 零告警 (调用方先记台账 skipped_no_data; 假日不告警风暴)。

    返回已触发事件列表 (供台账行透传); 事件经 alert_store.append 落
    ``data/user_data/alerts.jsonl`` (/api/alerts 查询面既有)。
    """
    from app.services import alert_store

    events: list[dict] = []
    if not trading_day:
        return events
    if capture is not None and capture.get("ok", 0) < capture.get("requested", 0):
        ev = {
            "ts": int(time.time() * 1000),
            "rule_id": RULE_CAPTURE_MISSING,
            "source": "auction_sidecar",
            "trade_date": trade_date,
            "requested": capture.get("requested"),
            "ok": capture.get("ok"),
            "failed_symbols": capture.get("failed_symbols", []),
        }
        alert_store.append(data_dir, ev)
        events.append(ev)
    if reconcile is not None and reconcile.get("status") == "mismatch":
        ev = {
            "ts": int(time.time() * 1000),
            "rule_id": RULE_RECONCILE_FAIL,
            "source": "auction_sidecar",
            "trade_date": trade_date,
            "checks": reconcile.get("checks", {}),
        }
        alert_store.append(data_dir, ev)
        events.append(ev)
    return events


def _prune_locked(p: Path) -> None:
    """(调用方需持锁) 保留近 MAX_DAYS 天 + 上限 MAX_RECORDS 条 (取交集, 镜像 alert_store)。"""
    if not p.exists():
        return
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        if not lines:
            return
        cutoff = cn_now() - timedelta(days=MAX_DAYS)
        kept: list[str] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = _record_time(ev)
            if t is not None and t < cutoff:
                continue
            kept.append(line)
        if len(kept) > MAX_RECORDS:
            kept = kept[-MAX_RECORDS:]
        tmp = p.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(kept) + "\n", encoding="utf-8")
        tmp.replace(p)  # 原子写 (T-43-03-03)
    except OSError as e:
        logger.warning("auction_sidecar_ledger prune write failed: %s", e)
