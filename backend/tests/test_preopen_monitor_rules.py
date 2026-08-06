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


# ── T4 边界 (MON-02): 帧构建健壮性 ──
def test_build_preopen_frame_edge_rows():
    from app.strategy.preopen_eval import build_preopen_frame

    eng = _engine()
    eng.set_rules([_preopen_rule("r1", "open_gap", ">=", 0.05)])

    # (a) 非 dict 行 / 无 symbol 行 → 静默跳过, 不崩
    junk_payload = _preopen_payload(results={
        "s1": {"rows": ["junk", None, {"symbol": None, "open_gap": 0.9}, {"no_symbol": 1}]},
    })
    assert build_preopen_frame(junk_payload) is None
    assert eng.evaluate_premarket(junk_payload) == []

    # (b) 多策略同 symbol → frame 单行 keep=first (首个策略的行值)
    row_first = {"symbol": "000001.SZ", "name": "A银行", "open_gap": 0.06, "hit_factors": ["first"]}
    row_second = {"symbol": "000001.SZ", "name": "A银行", "open_gap": 0.09, "hit_factors": ["second"]}
    payload2 = _preopen_payload(results={
        "s1": {"rows": [row_first]},
        "s2": {"rows": [row_second]},
    })
    frame2, _ = build_preopen_frame(payload2)
    assert frame2.height == 1
    row2 = frame2.to_dicts()[0]
    assert row2["hit_factors"] == ["first"]
    assert row2["open_gap"] == 0.06
    assert row2["source_strategies"] == ["s1", "s2"]

    # (c) 行内残留 change_pct/close/code → frame 无 close/code 列且 change_pct 全 None
    payload3 = _preopen_payload(results={
        "s1": {"rows": [{"symbol": "000001.SZ", "open_gap": 0.05, "change_pct": 0.03, "close": 10.0, "code": "000001"}]},
    })
    frame3, _ = build_preopen_frame(payload3)
    assert "close" not in frame3.columns
    assert "code" not in frame3.columns
    assert all(v is None for v in frame3["change_pct"].to_list())

    # (d) 无 results 键 / 空 results / available:false → evaluate_premarket []
    assert eng.evaluate_premarket({"available": True}) == []
    assert eng.evaluate_premarket({"available": True, "results": {}}) == []
    assert eng.evaluate_premarket({"available": False, "results": {"a": {"rows": [row_first]}}}) == []


# ── T7 隔离断言 (MON-02 核心验收): 策略池三属性零变化 ──
def test_evaluate_premarket_isolation_from_strategy_pools():
    eng = _engine()
    pre = _preopen_rule("mr_preopen_gap5", "open_gap", ">=", 0.05)
    strat_rule = {
        "id": "mr_strategy_x", "name": "s", "type": "strategy",
        "strategy_id": "does_not_exist", "scope": "all",
        "cooldown_seconds": 0, "enabled": True,
    }
    eng.set_rules([pre, strat_rule])

    payload = _preopen_payload([{"symbol": "000001.SZ", "name": "A银行", "open_gap": 0.06}])

    before_pools = dict(eng._strategy_pools)
    before_latest = dict(eng.latest_strategy_results())
    before_building = dict(eng._building_strategy_results)

    events = eng.evaluate_premarket(payload)

    assert events, "preopen 规则应命中"
    assert all(e["rule_id"] != "mr_strategy_x" for e in events)  # 策略规则不参与
    assert eng._strategy_pools == before_pools
    assert eng.latest_strategy_results() == before_latest
    assert eng._building_strategy_results == before_building


# ── T8 cooldown (MON-02): 复用 _last_fire 冷却域 ──
def test_evaluate_premarket_cooldown():
    eng = _engine()
    rule_cd = _preopen_rule("r_cd", "open_gap", ">=", 0.05, cooldown=3600)
    # 异 rule_id + 自身 cooldown=0: 不受 r_cd 冷却影响, 仍独立触发
    rule_cd2 = _preopen_rule("r_cd2", "open_gap", ">=", 0.05, cooldown=0)
    rule_0 = _preopen_rule("r_cd0", "open_gap", ">=", 0.05, cooldown=0)
    eng.set_rules([rule_cd, rule_cd2, rule_0])

    payload = _preopen_payload([{"symbol": "000001.SZ", "name": "A银行", "open_gap": 0.06}])

    events1 = eng.evaluate_premarket(payload)
    assert len(events1) == 3
    # 同 (rule_id, symbol) 冷却期内不重复触发 (r_cd 被自己冷却);
    # 异 rule_id 同 symbol 的规则不受影响 (r_cd2/r_cd0 仍触发)
    events2 = eng.evaluate_premarket(payload)
    assert len(events2) == 2
    ids2 = {e["rule_id"] for e in events2}
    assert "r_cd" not in ids2
    assert "r_cd2" in ids2
    assert "r_cd0" in ids2

    # 严格版: 单条 cooldown=3600 规则 → 第一次命中 1 事件, 立即第二次 0 事件
    eng1 = _engine()
    eng1.set_rules([_preopen_rule("r_cd_solo", "open_gap", ">=", 0.05, cooldown=3600)])
    assert len(eng1.evaluate_premarket(payload)) == 1
    assert eng1.evaluate_premarket(payload) == []

    # cooldown=0: 重复调用均触发
    eng3 = _engine()
    eng3.set_rules([_preopen_rule("r0", "open_gap", ">=", 0.05, cooldown=0)])
    assert len(eng3.evaluate_premarket(payload)) == 1
    assert len(eng3.evaluate_premarket(payload)) == 1


# ── T10 按标的缺席诚实 (MON-04): null-as-absent, 非 null-as-present ──
def test_preopen_absent_symbol_not_hit():
    from app.strategy.preopen_eval import build_preopen_frame, extract_preopen_metrics

    eng = _engine()
    eng.set_rules([_preopen_rule("r_vol", "auction_volume", ">=", 1000)])
    payload = _preopen_payload(results={
        "s1": {"rows": [
            {"symbol": "A.SZ", "name": "A", "auction_volume": 1500},
            {"symbol": "B.SZ", "name": "B", "auction_volume": None},
        ]},
    })

    events = eng.evaluate_premarket(payload)
    assert {e["symbol"] for e in events} == {"A.SZ"}  # B 缺席不命中
    assert events[0]["preopen_metrics"]["auction_volume"] == 1500

    frame, _ = build_preopen_frame(payload)
    assert "auction_volume" not in extract_preopen_metrics(frame, "B.SZ")


# ── T2 负例全量 (MON-01): 白名单外 EOD 字段 / truth / 非法 op / 非数字 value ──
def test_preopen_validate_negative_cases():
    from app.strategy import monitor_rules

    # EOD 列 (白名单外) → ValueError 含「白名单」
    for field in ("change_pct", "close", "vol_ratio_5d", "amount"):
        with pytest.raises(ValueError, match="白名单"):
            monitor_rules.validate(_preopen_rule(f"r_eod_{field}", field, ">=", 0.05))

    # op=truth 显式拒绝 (D2)
    with pytest.raises(ValueError, match="truth"):
        monitor_rules.validate(_preopen_rule("r_truth", "open_gap", "truth", None))

    # 白名单外字段 + 数值 op (如盘中指标 rsi_14) → 拒绝
    with pytest.raises(ValueError, match="白名单"):
        monitor_rules.validate(_preopen_rule("r_offwl", "rsi_14", ">=", 0.05))

    # value 非数字
    with pytest.raises(ValueError, match="数字"):
        monitor_rules.validate(_preopen_rule("r_str_val", "open_gap", ">=", "0.05"))

    # conditions 空 / 超过 8 条
    empty = _preopen_rule("r_empty", "open_gap", ">=", 0.05)
    empty["conditions"] = []
    with pytest.raises(ValueError, match="conditions"):
        monitor_rules.validate(empty)
    many = _preopen_rule("r_many", "open_gap", ">=", 0.05)
    many["conditions"] = [{"field": "open_gap", "op": ">=", "value": 0.01}] * 9
    with pytest.raises(ValueError, match="conditions"):
        monitor_rules.validate(many)

    # scope 仅 symbols/all (D3)
    for scope in ("sector", "positions"):
        with pytest.raises(ValueError, match="symbols/all"):
            monitor_rules.validate(_preopen_rule("r_scope", "open_gap", ">=", 0.05, scope=scope))

    # 白名单字段 + 非法 op
    with pytest.raises(ValueError, match="op"):
        monitor_rules.validate(_preopen_rule("r_badop", "open_gap", "between", 0.05))


# ── T9 降级 fail-closed (MON-04): 缺列不 0 填、不派生兜底 ──
def test_preopen_degraded_fail_closed():
    eng = _engine()
    vol_rule = _preopen_rule("r_vol", "auction_volume", ">=", 1000)
    gap_rule = _preopen_rule("r_gap", "open_gap", ">=", 0.05)
    eng.set_rules([vol_rule, gap_rule])

    probe = {"status": "fallback", "source": "prev_close", "probed_at": "09:25:01"}
    # degraded + 无 auction_* 列 → auction 规则 fail-closed 0 命中;
    # open_gap 规则仍可命中且事件带 degraded=True + probe 透传
    payload = _preopen_payload(
        [{"symbol": "000001.SZ", "name": "A银行", "open_gap": 0.06}],
        degraded=True, probe=probe,
    )
    events = eng.evaluate_premarket(payload)
    assert len(events) == 1
    ev = events[0]
    assert ev["rule_id"] == "r_gap"
    assert ev["degraded"] is True
    assert ev["probe"] == probe

    # available:false → [] 且不产生任何事件
    eng2 = _engine()
    eng2.set_rules([gap_rule])
    assert eng2.evaluate_premarket({
        "available": False, "degraded": True,
        "results": {"a": {"rows": [{"symbol": "000001.SZ", "open_gap": 0.06}]}},
    }) == []


# ── message (MON-04): 盘前前缀, price/pct 恒 None 不加尾缀 ──
def test_preopen_event_message():
    eng = _engine()
    rule = _preopen_rule("mr_preopen_gap5", "open_gap", ">=", 0.05)
    eng.set_rules([rule])
    payload = _preopen_payload([{"symbol": "000001.SZ", "name": "A银行", "open_gap": 0.06}])

    events = eng.evaluate_premarket(payload)
    assert len(events) == 1
    ev = events[0]

    cond_text = eng._format_conditions_text(rule, rule["conditions"])
    assert cond_text
    assert ev["message"] == f"盘前 {cond_text}"
    assert ev["message"].startswith("盘前")
    assert "现价" not in ev["message"]  # price 恒 None, 诚实不加价
    assert "open_gap" in ev["message"] and "0.05" in ev["message"]


# ── helper 等价 (MON-01): 抽取后既有 signal/price/market 校验行为不变 ──
def test_validate_helpers_keep_existing_behavior():
    from app.strategy import monitor_rules

    # 合法 signal 规则 (truth + 阈值) 仍通过
    monitor_rules.validate({
        "id": "r_sig_ok", "name": "s", "type": "signal", "scope": "all",
        "conditions": [
            {"field": "signal_ma_golden_5_20", "op": "truth"},
            {"field": "rsi_14", "op": "<", "value": 40},
        ],
        "logic": "and",
    })
    # 合法 price/market 规则仍通过
    monitor_rules.validate({
        "id": "r_price_ok", "name": "p", "type": "price", "scope": "all",
        "conditions": [{"field": "change_pct", "op": ">=", "value": 0.05}],
    })
    # 负例同款 ValueError (消息不变)
    with pytest.raises(ValueError, match="conditions 不能为空"):
        monitor_rules.validate({"id": "r1", "name": "x", "type": "signal", "scope": "all", "conditions": []})
    with pytest.raises(ValueError, match="conditions 最多 8 条"):
        monitor_rules.validate({
            "id": "r2", "name": "x", "type": "signal", "scope": "all",
            "conditions": [{"field": "rsi_14", "op": "<", "value": 1}] * 9,
        })
    with pytest.raises(ValueError, match="logic"):
        monitor_rules.validate({
            "id": "r3", "name": "x", "type": "price", "scope": "all", "logic": "xor",
            "conditions": [{"field": "close", "op": ">", "value": 1}],
        })
    with pytest.raises(ValueError, match="信号列"):
        monitor_rules.validate({
            "id": "r4", "name": "x", "type": "signal", "scope": "all",
            "conditions": [{"field": "close", "op": "truth"}],
        })
    with pytest.raises(ValueError, match="白名单"):
        monitor_rules.validate({
            "id": "r5", "name": "x", "type": "price", "scope": "all",
            "conditions": [{"field": "open_gap", "op": ">", "value": 0.05}],
        })
    with pytest.raises(ValueError, match="op"):
        monitor_rules.validate({
            "id": "r6", "name": "x", "type": "market", "scope": "all",
            "conditions": [{"field": "close", "op": "between", "value": 1}],
        })
