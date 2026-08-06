"""Phase 30 preopen 规则监控 — T1-T10 (MON-01 / MON-02 / 引擎层 MON-04)。

盘前规则 (type=preopen) 校验 / 盘前帧重建 (build_preopen_frame) / 隔离评估入口
(evaluate_premarket) / 事件标注 / 盘中跳过 (D-03 回归锁) / cooldown / 降级
fail-closed / 按标的缺席诚实。

约定 (镜像 tests/test_monitor_etf.py): 引擎直构 ``MonitorRuleEngine()``, 不注入
handler/clock; 生产 import 放测试函数内 (hermetic, 模块无 import 副作用)。
"""
from __future__ import annotations

import pytest


# ── helpers (测试基础设施, 无生产 import) ──────────────────
def _engine():
    """构造隔离的 MonitorRuleEngine (直构, 无 handler/clock 注入)。"""
    from app.strategy.monitor import MonitorRuleEngine

    return MonitorRuleEngine()


def _preopen_rule(rid, field, op, value, *, scope="all", symbols=None, cooldown=0, **overrides):
    rule = {
        "id": rid,
        "name": f"盘前{field}{op}{value}",
        "type": "preopen",
        "scope": scope,
        "logic": "and",
        "conditions": [{"field": field, "op": op, "value": value}],
        "cooldown_seconds": cooldown,
        "enabled": True,
        "severity": "warn",
    }
    if symbols is not None:
        rule["symbols"] = symbols
    rule.update(overrides)
    return rule


def _preopen_payload(rows=None, *, degraded=False, probe=None, available=True, results=None):
    """盘前预览 payload。默认把同一批行包进 strat_a/strat_b 两个策略 (模拟多策略命中)。"""
    if results is None:
        results = {
            "strat_a": {"rows": list(rows or [])},
            "strat_b": {"rows": list(rows or [])},
        }
    return {
        "as_of": "2026-08-06",
        "available": available,
        "window": "pre_open",
        "provisional": True,
        "degraded": degraded,
        "probe": probe if probe is not None else {"status": "available", "source": "test"},
        "results": results,
    }


def _intraday_df():
    """盘中 enriched 帧 (含 open_gap 与 rsi_14 — 预演 open_gap 规则若盘中求值会误触发)。"""
    import polars as pl

    return pl.DataFrame({
        "symbol": ["000001.SZ"],
        "close": [10.0],
        "change_pct": [0.01],
        "open_gap": [0.06],
        "rsi_14": [30.0],
    })


def _signal_rule(rid, sym="000001.SZ"):
    return {
        "id": rid, "name": rid, "type": "signal", "scope": "symbols",
        "symbols": [sym], "logic": "and",
        "conditions": [{"field": "rsi_14", "op": "<", "value": 40}],
        "cooldown_seconds": 0, "enabled": True,
    }


# ── T1 正例 (MON-01): 白名单字段 × 数值 OPS validate 通过 ──
def test_preopen_validate_whitelist_positive():
    from app.strategy import monitor_rules

    fields = [
        "open_gap", "auction_volume", "auction_amount",
        "auction_volume_ratio", "auction_unmatched_amount",
    ]
    ops = [">", ">=", "<", "<=", "==", "!="]
    op_suffix = {">": "gt", ">=": "gte", "<": "lt", "<=": "lte", "==": "eq", "!=": "ne"}
    for field in fields:
        value = 100 if field in ("auction_volume", "auction_amount", "auction_unmatched_amount") else 0.05
        for op in ops:
            monitor_rules.validate(_preopen_rule(f"r_{field}_{op_suffix[op]}", field, op, value))
            monitor_rules.validate(_preopen_rule(
                f"r_{field}_{op_suffix[op]}_sym", field, op, value,
                scope="symbols", symbols=["000001.SZ"],
            ))
    # scope=all 规则 normalize → validate 往返 (保存语义, 不落盘)
    saved = monitor_rules.normalize(_preopen_rule("mr_preopen_gap5", "open_gap", ">=", 0.05))
    monitor_rules.validate(saved)
    assert saved["type"] == "preopen"


# ── T3 (MON-01): normalize 默认值零改动 ──
def test_preopen_normalize_defaults():
    from app.strategy import monitor_rules

    r = monitor_rules.normalize({"id": "mr_preopen_gap5", "name": "盘前高开预警", "type": "preopen"})
    assert r["severity"] == "info"
    assert r["cooldown_seconds"] == 3600
    assert r["logic"] == "and"
    assert r["asset_type"] == "stock"
    assert r["scope"] == "symbols"
    assert r["enabled"] is True


# ── T4 核心 (MON-02): 帧构建 — 去重 / change_pct=None / source_strategies ──
def test_build_preopen_frame_dedup_and_columns():
    from app.strategy.preopen_eval import build_preopen_frame

    row_a = {
        "symbol": "000001.SZ", "name": "平安银行", "open_gap": 0.06,
        "change_pct": 0.05, "close": 10.5, "code": "000001", "hit_factors": ["A"],
    }
    row_a2 = {"symbol": "000001.SZ", "open_gap": 0.06}
    row_b = {"symbol": "600000.SH", "name": "浦发银行", "open_gap": -0.02}
    payload = _preopen_payload(results={
        "strat_a": {"rows": [row_a]},
        "strat_b": {"rows": [row_a2, row_b]},
    })

    built = build_preopen_frame(payload)
    assert built is not None
    frame, source_map = built

    assert frame.height == 2  # 000001.SZ 去重后单行 (keep=first)
    assert "change_pct" in frame.columns
    assert all(v is None for v in frame["change_pct"].to_list())
    assert "close" not in frame.columns
    assert "code" not in frame.columns
    assert "open_gap" in frame.columns

    assert source_map["000001.SZ"] == {"strat_a", "strat_b"}
    assert source_map["600000.SH"] == {"strat_b"}

    by_sym = {r["symbol"]: r for r in frame.to_dicts()}
    assert by_sym["000001.SZ"]["source_strategies"] == ["strat_a", "strat_b"]
    assert by_sym["600000.SH"]["source_strategies"] == ["strat_b"]


# ── T5 核心 (MON-02): 事件字段标注 ──
def test_preopen_event_fields():
    from app.strategy import monitor_rules

    eng = _engine()
    rule = _preopen_rule("mr_preopen_gap5", "open_gap", ">=", 0.05, cooldown=0)
    monitor_rules.validate(rule)
    eng.set_rules([rule])

    row_a = {"symbol": "000001.SZ", "name": "平安银行", "open_gap": 0.06}
    row_b = {"symbol": "600000.SH", "name": "浦发银行", "open_gap": -0.02}
    probe = {"status": "available", "source": "auction", "probed_at": "09:25:01"}
    payload = _preopen_payload(results={
        "strat_a": {"rows": [row_a]},
        "strat_b": {"rows": [row_b]},
    }, degraded=False, probe=probe)

    events = eng.evaluate_premarket(payload)
    assert len(events) == 1
    ev = events[0]

    assert ev["source"] == "preopen"
    assert ev["type"] == "preopen"
    assert ev["window"] == "pre_open"
    assert ev["provisional"] is True
    assert ev["degraded"] is False
    assert ev["probe"] == probe
    assert ev["symbol"] == "000001.SZ"
    assert ev["strategy_ids"] == ["strat_a"]
    assert ev["change_pct"] is None
    assert ev["price"] is None
    assert ev["preopen_metrics"]["open_gap"] == 0.06
    assert ev["conditions"] == rule["conditions"]

    for key in ("id", "ts", "occurred_at", "rule_id", "rule_name", "severity", "message"):
        assert key in ev
    assert ev["rule_id"] == "mr_preopen_gap5"


# ── T6 (D-03 回归锁): evaluate() 盘中跳过 preopen ──
def test_evaluate_intraday_skips_preopen_rules():
    eng = _engine()
    pre = _preopen_rule("mr_preopen_gap5", "open_gap", ">=", 0.05)
    sig = _signal_rule("r_sig")
    eng.set_rules([pre, sig])

    events = eng.evaluate(_intraday_df())
    assert any(e["rule_id"] == "r_sig" for e in events)  # 盘中 signal 规则正常触发
    assert all(e["rule_id"] != "mr_preopen_gap5" for e in events)  # preopen 绝不盘中求值

    # preopen-only 引擎: 盘中 evaluate 恒 0 事件
    eng2 = _engine()
    eng2.set_rules([_preopen_rule("mr_preopen_only", "open_gap", ">=", 0.05)])
    assert eng2.evaluate(_intraday_df()) == []


# ── T6 空态 (诚实): 无结果/不可用/空行 → [] ──
def test_evaluate_premarket_empty_states():
    eng = _engine()
    eng.set_rules([_preopen_rule("r1", "open_gap", ">=", 0.05)])

    assert eng.evaluate_premarket({}) == []
    assert eng.evaluate_premarket({"available": False, "degraded": True, "results": {"a": {"rows": []}}}) == []
    assert eng.evaluate_premarket({"available": True, "results": {}}) == []
    assert eng.evaluate_premarket({"available": True, "results": {"a": {"rows": []}}}) == []
