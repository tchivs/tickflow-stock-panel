"""SDC-03 台账 + 诚实门告警 + 交易日判定契约 — 零网络 hermetic。

覆盖:
  - W-5 终态键集 (成功 7 键 / fail-closed + reason 8 键) + 滚动清理 + job 过滤查询
  - 告警链: 交易日 ∧ 采集缺失 → auction_sidecar_capture_missing; mismatch →
    auction_sidecar_reconcile_fail (alerts.jsonl 落盘断言)
  - 非交易日 (无 09:30 bar) → 零告警 + 台账 skipped_no_data; 正常日零噪声
  - 交易日判定 = 数据在场 (09:30 bar) + 重试 1 次语义 (A5)
  - staging manifest → capture 终态推导 (09:40 告警判定输入)
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from app.market_time import cn_now

_RULE_CAPTURE_MISSING = "auction_sidecar_capture_missing"
_RULE_RECONCILE_FAIL = "auction_sidecar_reconcile_fail"
_T = date(2026, 8, 7)


class _FakeMinuteProvider:
    """按脚本返回 get_minute 帧 (镜像 provider 输出: symbol 后缀形态 + naive 北京墙钟 datetime)。

    帧序列耗尽后返回空帧。记录每次 (symbols, start_time, end_time) 调用。
    """

    def __init__(self, *frames) -> None:
        self._frames = list(frames)
        self.calls: list[tuple] = []

    def get_minute(self, symbols, start_time=None, end_time=None, freq="1m", **kwargs):
        self.calls.append((list(symbols), start_time, end_time))
        if self._frames:
            return self._frames.pop(0)
        return pl.DataFrame()


def _bar_frame(symbol: str = "600519.SH", close: float = 1308.66) -> pl.DataFrame:
    """09:30 集合竞价统计 bar (镜像 provider 分钟行形状)。"""
    return pl.DataFrame({
        "symbol": [symbol],
        "datetime": [datetime(2026, 8, 7, 9, 30)],
        "open": [close],
        "high": [close],
        "low": [close],
        "close": [close],
        "volume": [173.0],
        "amount": [22639818.0],
        "freq": ["1m"],
    })


def _alerts(data_dir: Path) -> list[dict]:
    from app.services import alert_store

    return alert_store.list_recent(data_dir, days=30, limit=500)


def _sidecar_alert_rules(data_dir: Path) -> list[str]:
    return [ev.get("rule_id") for ev in _alerts(data_dir) if ev.get("source") == "auction_sidecar"]


# ================================================================
# 台账 (Task 1)
# ================================================================


def test_ledger_append_success_shape(tmp_path):
    """成功态 7 键逐字断言 (W-5): {job, trade_date, requested, ok, failed_symbols, started_at, finished_at}。"""
    from app.services import auction_sidecar_ledger

    data_dir = tmp_path / "data"
    auction_sidecar_ledger.append_ledger(data_dir, {
        "job": "auction_sidecar_capture",
        "trade_date": "2026-08-07",
        "requested": 1,
        "ok": 1,
        "failed_symbols": [],
    })
    rows = auction_sidecar_ledger.list_ledger(data_dir)
    assert len(rows) == 1
    row = rows[0]
    assert set(row.keys()) == {
        "job", "trade_date", "requested", "ok", "failed_symbols", "started_at", "finished_at",
    }
    assert row["job"] == "auction_sidecar_capture"
    assert row["trade_date"] == "2026-08-07"
    assert row["requested"] == 1 and row["ok"] == 1
    assert row["failed_symbols"] == []
    assert isinstance(row["started_at"], str) and isinstance(row["finished_at"], str)


def test_ledger_append_fail_closed_reason(tmp_path):
    """ok==0 → 键集含 reason (fail-closed 8 键, 自动补) — 失败态绝不无因; 显式 reason 优先。"""
    from app.services import auction_sidecar_ledger

    data_dir = tmp_path / "data"
    auction_sidecar_ledger.append_ledger(data_dir, {
        "job": "auction_sidecar_capture",
        "trade_date": "2026-08-07",
        "requested": 200,
        "ok": 0,
        "failed_symbols": ["SH600000"],
    })
    row = auction_sidecar_ledger.list_ledger(data_dir)[0]
    assert set(row.keys()) == {
        "job", "trade_date", "requested", "ok", "failed_symbols",
        "started_at", "finished_at", "reason",
    }
    assert row["reason"] == "fail_closed"

    # 显式 reason 不被自动补覆盖
    auction_sidecar_ledger.append_ledger(data_dir, {
        "job": "auction_sidecar_capture",
        "trade_date": "2026-08-06",
        "requested": 1,
        "ok": 0,
        "failed_symbols": [],
        "reason": "capture_all_failed",
    })
    by_date = {r["trade_date"]: r for r in auction_sidecar_ledger.list_ledger(data_dir)}
    assert by_date["2026-08-06"]["reason"] == "capture_all_failed"


def test_ledger_rolling_prune(tmp_path, monkeypatch):
    """滚动清理: 超 MAX_RECORDS 按时间清旧行 (镜像 alert_store), 不无限膨胀。"""
    from app.services import auction_sidecar_ledger

    monkeypatch.setattr(auction_sidecar_ledger, "MAX_RECORDS", 5)
    monkeypatch.setattr(auction_sidecar_ledger, "PRUNE_EVERY", 1)
    data_dir = tmp_path / "data"
    base = cn_now()
    for i in range(8):
        started = (base - timedelta(minutes=8 - i)).isoformat(timespec="seconds")
        auction_sidecar_ledger.append_ledger(data_dir, {
            "job": "auction_sidecar_capture",
            "trade_date": "2026-08-07",
            "requested": 1,
            "ok": 1,
            "failed_symbols": [],
            "started_at": started,
            "finished_at": started,
        })
    rows = auction_sidecar_ledger.list_ledger(data_dir, days=30)
    assert len(rows) == 5  # 上限内, 最旧 3 行被清
    kept = [r["started_at"] for r in rows]
    assert (base - timedelta(minutes=8)).isoformat(timespec="seconds") not in kept  # 最旧已清
    assert (base - timedelta(minutes=1)).isoformat(timespec="seconds") in kept      # 最新保留


def test_ledger_list_recent_filters(tmp_path):
    """list_ledger 按 job 过滤 + 时间倒序返回。"""
    from app.services import auction_sidecar_ledger

    data_dir = tmp_path / "data"
    base = cn_now()
    started_at: list[str] = []
    for i, job in enumerate([
        "auction_sidecar_capture",
        "auction_sidecar_reconcile",
        "auction_sidecar_capture",
    ]):
        started = (base - timedelta(minutes=i + 1)).isoformat(timespec="seconds")
        started_at.append(started)
        auction_sidecar_ledger.append_ledger(data_dir, {
            "job": job,
            "trade_date": "2026-08-07",
            "requested": 1,
            "ok": 1,
            "failed_symbols": [],
            "started_at": started,
            "finished_at": started,
        })
    caps = auction_sidecar_ledger.list_ledger(data_dir, job="auction_sidecar_capture")
    assert len(caps) == 2
    assert [r["job"] for r in caps] == ["auction_sidecar_capture", "auction_sidecar_capture"]
    assert caps[0]["started_at"] == started_at[0]  # 倒序: 最新在前
    assert caps[1]["started_at"] == started_at[2]


# ================================================================
# 交易日判定 + 告警接线 (Task 2)
# ================================================================


def test_trading_day_confirmed_by_0930_bar(tmp_path):
    """交易日判定 = 数据在场 (09:30 bar): 直接命中 → True; 首查缺失重试后存在 → True
    (重试 1 次, A5); 恒缺失 → False; 请求窗口端日语义 (start=T 00:00, end=T+1 00:00)。"""
    from app.services import auction_sidecar_ledger

    p1 = _FakeMinuteProvider(_bar_frame())
    assert auction_sidecar_ledger.confirm_trading_day(p1, _T, retry_sleep=0.0) is True
    assert len(p1.calls) == 1
    assert p1.calls[0][1] == datetime(2026, 8, 7, 0, 0)
    assert p1.calls[0][2] == datetime(2026, 8, 8, 0, 0)

    p2 = _FakeMinuteProvider(pl.DataFrame(), _bar_frame())
    assert auction_sidecar_ledger.confirm_trading_day(p2, _T, retry_sleep=0.0) is True
    assert len(p2.calls) == 2  # 重试 1 次

    p3 = _FakeMinuteProvider(pl.DataFrame(), pl.DataFrame())
    assert auction_sidecar_ledger.confirm_trading_day(p3, _T, retry_sleep=0.0) is False
    assert len(p3.calls) == 2


def test_alert_capture_missing_on_trading_day(tmp_path):
    """交易日确认 ∧ 采集缺失/不完整 (ok < requested) → auction_sidecar_capture_missing
    落 alerts.jsonl (SDC-03「09:26 后缺失可告」)。"""
    from app.services import auction_sidecar_ledger

    data_dir = tmp_path / "data"
    events = auction_sidecar_ledger.evaluate_sidecar_alerts(
        data_dir,
        "2026-08-07",
        capture={"requested": 200, "ok": 150, "failed_symbols": ["SH600000"], "completeness_ok": False},
        reconcile={"status": "closed", "checks": {"SH600519": {"status": "closed"}}},
        trading_day=True,
    )
    assert [e["rule_id"] for e in events] == [_RULE_CAPTURE_MISSING]
    assert _RULE_CAPTURE_MISSING in _sidecar_alert_rules(data_dir)
    ev = [e for e in _alerts(data_dir) if e.get("rule_id") == _RULE_CAPTURE_MISSING][0]
    assert ev["source"] == "auction_sidecar"
    assert ev["trade_date"] == "2026-08-07"
    assert ev["requested"] == 200 and ev["ok"] == 150
    assert ev["failed_symbols"] == ["SH600000"]
    assert isinstance(ev["ts"], int)


def test_alert_reconcile_fail_on_mismatch(tmp_path):
    """对账 mismatch → auction_sidecar_reconcile_fail (采集完整时仅此一告警)。"""
    from app.services import auction_sidecar_ledger

    data_dir = tmp_path / "data"
    events = auction_sidecar_ledger.evaluate_sidecar_alerts(
        data_dir,
        "2026-08-07",
        capture={"requested": 200, "ok": 200, "failed_symbols": []},
        reconcile={"status": "mismatch", "checks": {"SH600519": {"status": "mismatch"}}},
        trading_day=True,
    )
    assert [e["rule_id"] for e in events] == [_RULE_RECONCILE_FAIL]
    ev = [e for e in _alerts(data_dir) if e.get("rule_id") == _RULE_RECONCILE_FAIL][0]
    assert ev["source"] == "auction_sidecar"
    assert ev["checks"] == {"SH600519": {"status": "mismatch"}}


def test_no_alert_on_non_trading_day(tmp_path):
    """非交易日 (无 09:30 bar) → 零告警 + 台账 skipped_no_data (假日不告警风暴)。"""
    from app.services import auction_sidecar_ledger

    data_dir = tmp_path / "data"
    assert auction_sidecar_ledger.confirm_trading_day(
        _FakeMinuteProvider(pl.DataFrame(), pl.DataFrame()), _T, retry_sleep=0.0,
    ) is False
    events = auction_sidecar_ledger.evaluate_sidecar_alerts(
        data_dir,
        "2026-08-07",
        capture={"requested": 200, "ok": 0, "failed_symbols": ["SH600000"]},
        reconcile={"status": "staging_missing", "checks": {}},
        trading_day=False,
    )
    assert events == []
    assert _sidecar_alert_rules(data_dir) == []

    auction_sidecar_ledger.append_ledger(data_dir, {
        "job": "auction_sidecar_reconcile",
        "trade_date": "2026-08-07",
        "requested": 0,
        "ok": 0,
        "failed_symbols": [],
        "skipped": "no_data",
    })
    row = auction_sidecar_ledger.list_ledger(data_dir)[0]
    assert row["skipped"] == "no_data"
    assert "reason" not in row


def test_no_alert_when_capture_complete(tmp_path):
    """交易日 ∧ 采集完整 ∧ 对账 closed → 零告警 (正常日静默, 不产生噪声事件)。"""
    from app.services import auction_sidecar_ledger

    data_dir = tmp_path / "data"
    events = auction_sidecar_ledger.evaluate_sidecar_alerts(
        data_dir,
        "2026-08-07",
        capture={"requested": 200, "ok": 200, "failed_symbols": []},
        reconcile={"status": "closed", "checks": {"SH600519": {"status": "closed"}}},
        trading_day=True,
    )
    assert events == []
    assert _sidecar_alert_rules(data_dir) == []


def test_read_capture_state_from_manifest(tmp_path):
    """staging manifest → capture 终态推导 (09:40 告警判定输入); 无 manifest → None。"""
    from app.services import auction_sidecar_ledger

    data_dir = tmp_path / "data"
    assert auction_sidecar_ledger.read_sidecar_capture_state(data_dir, _T) is None

    stage = data_dir / "tick_staging" / "date=2026-08-07"
    stage.mkdir(parents=True)
    (stage / "manifest.json").write_text(json.dumps({
        "trade_date": "2026-08-07",
        "pool_size": 200,
        "symbols_ok": ["SH600519"],
        "symbols_failed": [{"symbol": "SH600000", "reason": "incomplete:window_rows=10"}],
        "completeness": {"ok": False, "by_symbol": {}},
    }), encoding="utf-8")

    state = auction_sidecar_ledger.read_sidecar_capture_state(data_dir, _T)
    assert state == {
        "requested": 200,
        "ok": 1,
        "failed_symbols": ["SH600000"],
        "completeness_ok": False,
    }
