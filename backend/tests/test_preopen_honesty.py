"""MON-04/MON-06 — 盘前告警诚实接线: round-trip 保真 + guest 掩码快照。

Task 2:
- T17 round-trip (MON-04): ``record_alert_event`` → ``get_alert_event`` 全字段保真 —
  window/provisional/degraded/probe/strategy_ids/preopen_metrics/conditions 逐键相等
  (event_json 全量快照, 不改表)。
- T18 mask_guest_alert 快照 (MON-06): symbol/name/code → ******; 剥离
  open_gap/auction_*/preopen_metrics/probe; 保留 message/severity/window/provisional/
  degraded/rule_name/conditions/occurred_at/rule_id/source/type; 输入 dict 不被修改
  (纯拷贝)。

镜像 test_guest_masking 结构 (字段集合断言风格); 生产 import 放测试函数内 (hermetic)。
"""
from __future__ import annotations


def _preopen_event() -> dict:
    """一条完整的 preopen 告警事件 (含 code 预览行键 + 全部 MON-03/04 增量键)。"""
    return {
        "id": "ev_preopen_000001",
        "occurred_at": "2026-08-06T09:26:00+00:00",
        "rule_id": "mr_preopen_gap5",
        "rule_name": "盘前高开预警",
        "source": "preopen",
        "type": "preopen",
        "window": "pre_open",
        "provisional": True,
        "degraded": False,
        "probe": {"status": "available", "source": "live", "probed_at": "2026-08-06T09:26:00"},
        "strategy_ids": ["auction_bullish"],
        "preopen_metrics": {"open_gap": 0.08, "auction_volume": 100},
        "symbol": "000001.SZ",
        "name": "平安银行",
        "code": "000001",
        "open_gap": 0.08,
        "auction_volume": 100,
        "auction_amount": 5e7,
        "auction_volume_ratio": 3.2,
        "auction_unmatched_amount": 1e6,
        "message": "盘前 open_gap>=0.05",
        "severity": "warn",
        "conditions": [{"field": "open_gap", "op": ">=", "value": 0.05}],
    }


# ================================================================
# T17 — record_alert_event → get_alert_event round-trip (MON-04)
# ================================================================


def test_alert_event_roundtrip_preserves_preopen_fields(tmp_path):
    """T17 round-trip: event_json 全量快照 — preopen 专属字段逐键保真。"""
    from app.operational.repository import OperationalRepository

    repo = OperationalRepository(tmp_path / "operational.db")
    repo.migrate()

    event = _preopen_event()
    persisted = repo.record_alert_event(event)
    loaded = repo.get_alert_event(persisted["id"])

    assert loaded is not None
    assert loaded["id"] == event["id"]
    for key in (
        "rule_id", "source", "type", "symbol", "name", "severity", "message",
        "window", "provisional", "degraded", "probe", "strategy_ids",
        "preopen_metrics", "conditions",
    ):
        assert loaded[key] == event[key], f"round-trip 丢失/篡改: {key}"
    assert loaded["probe"] == event["probe"]          # dict 等值
    assert loaded["conditions"] == event["conditions"]  # list 等值
    assert loaded["preopen_metrics"] == event["preopen_metrics"]


def test_alert_event_roundtrip_degraded_probe_frozen_snapshot(tmp_path):
    """T17 降级态保真: degraded:true + probe 冻结快照 round-trip 后仍在事件中 (绝不静默 0 填)。"""
    from app.operational.repository import OperationalRepository

    repo = OperationalRepository(tmp_path / "operational.db")
    repo.migrate()

    event = _preopen_event()
    event["degraded"] = True
    event["probe"] = {"status": "fail_closed", "detail": "no auction partition"}
    event["open_gap"] = 0.08  # 降级时 open_gap 规则仍可命中, 事件带 degraded 标注

    persisted = repo.record_alert_event(event)
    loaded = repo.get_alert_event(persisted["id"])

    assert loaded["degraded"] is True
    assert loaded["probe"]["status"] == "fail_closed"


# ================================================================
# T18 — mask_guest_alert 快照 (MON-06, 防御性 DTO 边界)
# ================================================================


def test_mask_guest_alert_snapshot():
    """T18: 身份 ******、竞价值/探测信息剥离、白名单保留、输入不被修改。"""
    from app.services.guest_masking import MASKED_IDENTITY, mask_guest_alert

    event = _preopen_event()
    before = dict(event)

    masked = mask_guest_alert(event)

    # 身份 → MASKED_IDENTITY
    assert masked["symbol"] == MASKED_IDENTITY
    assert masked["name"] == MASKED_IDENTITY
    assert masked["code"] == MASKED_IDENTITY

    # 竞价值 / 探测快照绝不带出
    for key in (
        "open_gap", "auction_volume", "auction_amount", "auction_volume_ratio",
        "auction_unmatched_amount", "preopen_metrics", "probe",
    ):
        assert key not in masked, f"guest 可见面泄露竞价值: {key}"

    # 盘前文案/状态标注 (非 PII) 保留
    for key in (
        "message", "severity", "window", "provisional", "degraded", "rule_name",
        "conditions", "occurred_at", "rule_id", "source", "type",
    ):
        assert key in masked, f"白名单字段被剥离: {key}"
    assert masked["message"] == event["message"]
    assert masked["severity"] == event["severity"]
    assert masked["conditions"] == event["conditions"]

    # 纯拷贝: 输入不被修改
    assert event == before


def test_mask_guest_alert_missing_keys_tolerated():
    """T18 防御性: 缺白名单键不崩溃 (仅保留事件中存在的白名单键 + 身份三键)。"""
    from app.services.guest_masking import MASKED_IDENTITY, mask_guest_alert

    minimal = {"rule_id": "r1", "source": "preopen", "type": "preopen", "message": "盘前触发"}
    masked = mask_guest_alert(minimal)

    assert masked == {
        "rule_id": "r1",
        "source": "preopen",
        "type": "preopen",
        "message": "盘前触发",
        "symbol": MASKED_IDENTITY,
        "name": MASKED_IDENTITY,
        "code": MASKED_IDENTITY,
    }
