"""MON-07 后端 — GET /api/monitor-rules/options 外露 preopen 类型 + preopen_threshold_fields。

Task 3:
- T20: ``types`` 含 ``{key: "preopen", label: "盘前异动"}``; ``preopen_threshold_fields``
  键集 == 5 白名单字段 (open_gap/auction_volume/auction_amount/auction_volume_ratio/
  auction_unmatched_amount), 每个字段带中文 label (ENRICHED_COLUMNS 非空);
  既有键 (threshold_fields/builtin_signals/custom_signals/operators/scopes/logics/
  severities/directions) 保持存在且 preopen 不污染 threshold_fields (EOD 字段如
  change_pct 仍在 threshold_fields, 不在 preopen_threshold_fields)。

镜像 test_premarket_pool._make_premarket_client 形 (FastAPI TestClient + stub app.state);
生产 import 放测试函数内 (hermetic)。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def _make_options_client(tmp_path: Path):
    """最小 FastAPI 应用 + monitor_rules router (get_options 只读 app.state.repo.store.data_dir)。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import monitor_rules as monitor_rules_api

    app = FastAPI()
    app.include_router(monitor_rules_api.router)
    app.state.repo = SimpleNamespace(store=SimpleNamespace(data_dir=tmp_path))
    app.state.strategy_engine = None
    return TestClient(app)


def test_options_expose_preopen_type_and_threshold_fields(tmp_path):
    """T20: preopen 类型 + 5 字段白名单 (中文标签) + 既有键不污染。"""
    client = _make_options_client(tmp_path)

    resp = client.get("/api/monitor-rules/options")
    assert resp.status_code == 200
    body = resp.json()

    # types 含 preopen (盘前异动)
    assert {"key": "preopen", "label": "盘前异动"} in body["types"]

    # preopen_threshold_fields: 精确 5 键集合 + 中文标签非空
    preopen_fields = body["preopen_threshold_fields"]
    assert {f["key"] for f in preopen_fields} == {
        "open_gap", "auction_volume", "auction_amount",
        "auction_volume_ratio", "auction_unmatched_amount",
    }
    assert len(preopen_fields) == 5
    for field in preopen_fields:
        assert field["label"], f"字段 {field['key']} 缺中文标签"
        assert field["label"] != field["key"], f"字段 {field['key']} 未命中 ENRICHED_COLUMNS 中文标签"

    # 既有键保持存在
    for key in ("threshold_fields", "builtin_signals", "custom_signals", "operators",
                "scopes", "logics", "severities", "directions"):
        assert key in body, f"options 缺既有键: {key}"

    # preopen 不污染 threshold_fields: EOD 字段仍在 threshold_fields, 不在 preopen 白名单
    threshold_keys = {f["key"] for f in body["threshold_fields"]}
    assert "change_pct" in threshold_keys
    assert "close" in threshold_keys
    assert "open_gap" not in threshold_keys
    assert "auction_volume" not in threshold_keys
