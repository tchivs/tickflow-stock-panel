"""策略构建流 WS 契约测试 (Phase 55: SSE → WS request dispatcher 迁移)。

旧 SSE ``build_strategy_stream`` 端点已在 Phase 55-04 删除; 策略构建流现由
``app.ws.request_dispatcher._dispatch_strategy_build`` 在 WS ``analysis:{strategy_id}``
频道上推送 ``analysis_meta`` → ``analysis_delta`` (逐 chunk) → ``analysis_done`` (含结果)。

本测试直接驱动 dispatcher, 验证与旧 SSE 流等价的契约:
  - meta/delta/done 事件顺序与内容。
  - result 元数据规范化 (id/name 来自 BuildRequest, 而非 AI 生成)。
  - 缺失 META 时单次结构修复。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.ws.request_dispatcher import _dispatch_strategy_build

STREAM_CODE = '''"""测试策略"""
import polars as pl

META = {
    "id": "wrong",
    "name": "旧名",
    "description": "旧描述",
    "tags": ["测试"],
    "params": [],
    "scoring": {},
}

ENTRY_SIGNALS = []
EXIT_SIGNALS = []
STOP_LOSS = -0.05
MAX_HOLD_DAYS = 20

RULES = """
1. 测试规则一
2. 测试规则二
3. 测试规则三
"""

def filter(df: pl.DataFrame, params: dict) -> pl.Expr:
    return pl.lit(True)
'''


class _RecordingManager:
    """捕获所有频道广播, 按到达顺序记录 (channel, msg_type, data)。"""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    async def broadcast_to_channel(self, channel: str, msg_type: str, data: dict) -> None:
        self.events.append((channel, msg_type, data))


def _build_params(**overrides: Any) -> dict:
    base = {
        "step": 1,
        "name": "新策略",
        "description": "新描述",
        "direction": "long",
        "rules": "1. 规则一\n2. 规则二\n3. 规则三",
        "strategy_id": "ai_streamed",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_strategy_build_emits_meta_delta_done(monkeypatch):
    """WS dispatcher 推送 analysis_meta → analysis_delta(s) → analysis_done,
    result 元数据用 BuildRequest 的 name/strategy_id 规范化。"""
    from app.api import strategy as strategy_mod
    from app.strategy.ai_generator import AIStrategyGenerator

    async def fake_stream(self, prompt):
        yield STREAM_CODE[:40]
        yield STREAM_CODE[40:]

    monkeypatch.setattr(AIStrategyGenerator, "stream", fake_stream)
    monkeypatch.setattr(
        strategy_mod, "_build_prompt", lambda req: "prompt"
    )

    manager = _RecordingManager()
    channel = "analysis:ai_streamed"
    await _dispatch_strategy_build(manager, channel, _build_params())

    types = [t for _, t, _ in manager.events]
    assert types[0] == "analysis_meta"
    assert types[-1] == "analysis_done"
    assert all(t == "analysis_delta" for t in types[1:-1])

    meta = manager.events[0][2]
    assert meta["strategy_id"] == "ai_streamed"
    assert meta["step"] == 1
    assert meta["name"] == "新策略"

    result = manager.events[-1][2]["result"]
    assert result["valid"] is True
    assert result["meta"]["id"] == "ai_streamed"
    assert result["meta"]["name"] == "新策略"
    assert '"id": "ai_streamed"' in result["code"]


@pytest.mark.asyncio
async def test_strategy_build_repairs_missing_meta_once(monkeypatch):
    """AI 生成代码缺失 META 时, dispatcher 触发单次结构修复, done 携带修复后结果。"""
    from app.api import strategy as strategy_mod
    from app.strategy.ai_generator import AIStrategyGenerator

    calls = 0

    async def fake_stream(self, prompt):
        yield "import polars as pl\n\ndef filter(df, params):\n    return pl.lit(True)\n"

    async def fake_repair(self, code, error):
        nonlocal calls
        calls += 1
        return self.validate_code(STREAM_CODE)

    monkeypatch.setattr(AIStrategyGenerator, "stream", fake_stream)
    monkeypatch.setattr(AIStrategyGenerator, "repair_code", fake_repair)
    monkeypatch.setattr(
        strategy_mod, "_build_prompt", lambda req: "prompt"
    )

    manager = _RecordingManager()
    channel = "analysis:ai_repaired"
    await _dispatch_strategy_build(manager, channel, _build_params(strategy_id="ai_repaired", name="修复后策略"))

    result = manager.events[-1][2]["result"]
    assert calls == 1
    assert result["valid"] is True
    assert result["meta"]["id"] == "ai_repaired"
    assert result["meta"]["name"] == "修复后策略"
