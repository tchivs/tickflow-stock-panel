"""REV-04 复盘集成 — recap_market_stream 面板 delta + 可选 AI 点评 + 调度默认 15:40 全验收。

Hermetic 铁律 (镜像 test_auction_recap.py / test_premarket_pool.py):
- 生产 import 放测试函数内 (仓库约定); build_market_overview / build_auction_recap /
  stream_ai_text / HhxgMarketClient 全 monkeypatch (零网络, 零真实 AI);
- 偏好 (preferences.json) 用 tmp data_dir 隔离 (monkeypatch settings.data_dir);
- 事件序列断言锁定 REV-04 事件序契约: meta → AI delta* → 面板 delta → done;
  全缺席退化 / AI 失败不发面板 / 面板构建异常韧性 为回归锁。

覆盖 (Task 1-3 累计):
- Task 1 (流): 事件序 (验收 1)、全缺席退化逐位一致 (验收 5 回归锁)、AI 失败
  error+return 不发面板 (R8)、as_of 缺失首事件 error、recap_market_once 累积含面板、
  面板构建异常韧性 (流不崩)。
- Task 2 (点评): pref 默认 False + round-trip、PUT/GET 端点、_build_user_prompt 向后
  兼容 + 切片节、护栏行只在开启时追加 (_SYSTEM_PROMPT 不动)、切片与面板同 dict 单源、
  全缺席切片诚实声明。
- Task 3 (调度): 默认 15:40、已存偏好保留、15:00 下限不动、Review.tsx 兜底字面量、
  GET 透传联动、注册消费零改动。
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

FIXED_DATE = date(2026, 8, 6)


# ================================================================
# hermetic helpers (monkeypatch 注入点, 镜像 test_auction_recap helpers)
# ================================================================


def _stub_repo() -> SimpleNamespace:
    """最小 repo 桩 — build_market_overview / build_auction_recap 全被 patch, repo 仅需存在。"""
    return SimpleNamespace(store=SimpleNamespace(data_dir=Path("/nonexistent")))


def _fake_overview(as_of: str | None = "2026-08-06") -> dict:
    """假 overview (镜像 test_hhxg_market.py:158-180 的 overview 形)。"""
    return {
        "as_of": as_of,
        "indices": [],
        "breadth": {},
        "amount": {},
        "limit": {},
        "trend": {},
        "activity": {},
        "emotion": {"score": 60, "label": "强"},
        "concept_rank": None,
        "industry_rank": None,
    }


def _fake_panel(present_blocks: list[str]) -> dict:
    """31-01 契约形 panel dict ({as_of, data_completeness, blocks, built_at})。

    未列出的块为 present:false (含 note/source); present_blocks 里的块为 present:true
    最小可渲染形 (render_auction_recap_markdown 纯函数可安全渲染, 不抛)。
    """
    blocks = {
        "real_auction_activity": {
            "present": False, "note": "当日无竞价湖数据", "source": "kline_auction",
        },
        "open_gap_snapshot": {
            "present": False,
            "note": "当日 enriched 数据缺失, 开盘涨幅快照暂不可用",
            "source": "kline_daily_enriched(open_gap 读时计算)",
        },
        "preopen_signal_quality": {
            "present": False, "note": "当日无盘前预览(no_premarket_preview)", "source": "premarket_results",
        },
    }
    if "real_auction_activity" in present_blocks:
        blocks["real_auction_activity"] = {
            "present": True, "note": "", "source": "kline_auction",
            "total_amount": 1.5e8, "n_symbols": 12, "top_n": [],
        }
    if "open_gap_snapshot" in present_blocks:
        blocks["open_gap_snapshot"] = {
            "present": True, "note": "", "source": "kline_daily_enriched(open_gap 读时计算)",
            "distribution": {"ge2_count": 3, "ge2_pct": 0.3, "ge5_count": 1, "ge5_pct": 0.1},
            "high_open_count": 3, "mean_open_gap": 0.021, "top_n": [],
        }
    if "preopen_signal_quality" in present_blocks:
        blocks["preopen_signal_quality"] = {
            "present": True, "note": "", "source": "premarket_results + kline_daily_enriched(EOD 口径)",
            "strategies": {}, "notes": [],
        }
    if len(present_blocks) == 3:
        completeness = "full"
    elif present_blocks:
        completeness = "partial"
    else:
        completeness = "no_auction_lake"
    return {
        "as_of": FIXED_DATE.isoformat(),
        "data_completeness": completeness,
        "blocks": blocks,
        "built_at": "2026-08-06T15:40:00+08:00",
    }


def _patch_news(monkeypatch) -> None:
    """阻断 hhxg 网络回退 (recap_market_stream 函数内 import, patch 源模块属性)。"""
    from app.services import hhxg_market

    class _NoNews:
        def __init__(self, *a, **k):
            pass

        def snapshot_news(self):
            return None

    monkeypatch.setattr(hhxg_market, "HhxgMarketClient", _NoNews)


def _patch_overview(monkeypatch, as_of: str | None = "2026-08-06") -> None:
    """monkeypatch app.services.market_recap.build_market_overview → 假 overview。"""
    from app.services import market_recap

    monkeypatch.setattr(
        market_recap, "build_market_overview", lambda *a, **k: _fake_overview(as_of),
    )


def _patch_panel(monkeypatch, panel: dict) -> None:
    """monkeypatch build_auction_recap → 假 panel (lazy import 语义: patch 源模块)。"""
    from app.services import auction_recap

    monkeypatch.setattr(auction_recap, "build_auction_recap", lambda *a, **k: panel)


def _patch_panel_error(monkeypatch) -> None:
    """monkeypatch build_auction_recap → 抛异常 (面板构建异常韧性测试)。"""
    from app.services import auction_recap

    def _boom(*a, **k):
        raise RuntimeError("panel build exploded")

    monkeypatch.setattr(auction_recap, "build_auction_recap", _boom)


def _patch_stream_ai(monkeypatch, deltas: list[str], error: bool = False) -> None:
    """monkeypatch stream_ai_text → 假异步生成器 (async for 兼容)。"""
    from app.services import ai_provider

    async def _fake(messages, **kwargs):
        if error:
            raise RuntimeError("AI upstream failed")
        for d in deltas:
            yield d

    monkeypatch.setattr(ai_provider, "stream_ai_text", _fake)


def _capture_stream_ai(monkeypatch, captured: dict) -> None:
    """monkeypatch stream_ai_text → 记录 messages 后 yield 1 段 (护栏/切片断言用)。"""
    from app.services import ai_provider

    async def _capture(messages, **kwargs):
        captured["messages"] = messages
        yield "AI-1"

    monkeypatch.setattr(ai_provider, "stream_ai_text", _capture)


async def _collect(agen) -> list[dict]:
    """异步收集 recap_market_stream 事件序列 (NDJSON → dict)。"""
    events = []
    async for evt in agen:
        events.append(json.loads(evt))
    return events


# ================================================================
# Task 1 — recap_market_stream 面板 delta 垂直切片 (REV-04 验收 1/5)
# ================================================================


async def test_recap_stream_panel_delta_before_done(monkeypatch):
    """REV-04 验收 1: 事件序锁死 meta → AI delta* → 面板 delta → done。

    面板 delta content 含「竞价复盘」表头; done 在最后。
    """
    _patch_overview(monkeypatch)
    _patch_panel(monkeypatch, _fake_panel(["open_gap_snapshot"]))
    _patch_stream_ai(monkeypatch, ["AI-1", "AI-2"])
    _patch_news(monkeypatch)

    from app.services.market_recap import recap_market_stream

    events = await _collect(recap_market_stream(_stub_repo(), as_of=FIXED_DATE))
    types = [e["type"] for e in events]
    assert types == ["meta", "delta", "delta", "delta", "done"]
    assert events[0]["as_of"] == "2026-08-06"
    assert events[1]["content"] == "AI-1"
    assert events[2]["content"] == "AI-2"
    panel_evt = events[3]
    assert panel_evt["type"] == "delta"
    assert "竞价复盘" in panel_evt["content"]
    assert events[4] == {"type": "done"}


async def test_all_blocks_absent_no_panel_delta_pure_ai(monkeypatch):
    """REV-04 验收 5 回归锁: 面板全缺席 → 不 yield 面板 delta, 退化纯 AI。

    recap_market_once 返回 content 与未加面板前逐位一致 (仅 AI 段拼接)。
    """
    _patch_overview(monkeypatch)
    _patch_panel(monkeypatch, _fake_panel([]))
    _patch_stream_ai(monkeypatch, ["AI-1", "AI-2"])
    _patch_news(monkeypatch)

    from app.services.market_recap import recap_market_once, recap_market_stream

    events = await _collect(recap_market_stream(_stub_repo(), as_of=FIXED_DATE))
    types = [e["type"] for e in events]
    assert types == ["meta", "delta", "delta", "done"]
    assert "竞价复盘" not in events[2]["content"]

    content, meta = await recap_market_once(_stub_repo(), as_of=FIXED_DATE)
    assert content == "AI-1AI-2"
    assert meta["as_of"] == "2026-08-06"


async def test_ai_failure_error_return_no_panel(monkeypatch):
    """R8: AI 失败 → error + return, done 与面板 delta 均不出现 (契约保持)。"""
    _patch_overview(monkeypatch)
    _patch_panel(monkeypatch, _fake_panel(["open_gap_snapshot"]))
    _patch_stream_ai(monkeypatch, [], error=True)
    _patch_news(monkeypatch)

    from app.services.market_recap import recap_market_once, recap_market_stream

    events = await _collect(recap_market_stream(_stub_repo(), as_of=FIXED_DATE))
    types = [e["type"] for e in events]
    assert types == ["meta", "error"]
    assert "AI 复盘失败" in events[1]["message"]

    content, meta = await recap_market_once(_stub_repo(), as_of=FIXED_DATE)
    assert content is None
    assert meta["as_of"] == "2026-08-06"


async def test_as_of_missing_first_event_error_no_panel(monkeypatch):
    """as_of 缺失 → 首事件即 error (面板构建不发生), 无 done。"""
    calls: list = []

    from app.services import auction_recap

    def _spy(*a, **k):
        calls.append(a)
        return _fake_panel([])

    monkeypatch.setattr(auction_recap, "build_auction_recap", _spy)
    _patch_overview(monkeypatch, as_of=None)
    _patch_news(monkeypatch)

    from app.services.market_recap import recap_market_stream

    events = await _collect(recap_market_stream(_stub_repo(), as_of=FIXED_DATE))
    assert events[0]["type"] == "error"
    assert "暂无市场数据" in events[0]["message"]
    assert all(e["type"] != "done" for e in events)
    assert calls == []  # 面板构建在 as_of 校验之后, 未触发


async def test_recap_once_content_includes_panel_after_ai(monkeypatch):
    """recap_market_once 累积含面板: content 含 AI 段 + 面板 markdown 段, AI 在前。"""
    _patch_overview(monkeypatch)
    _patch_panel(monkeypatch, _fake_panel(["open_gap_snapshot"]))
    _patch_stream_ai(monkeypatch, ["AI-段1"])
    _patch_news(monkeypatch)

    from app.services.market_recap import recap_market_once

    content, meta = await recap_market_once(_stub_repo(), as_of=FIXED_DATE)
    ai_pos = content.index("AI-段1")
    panel_pos = content.index("## 📊 竞价复盘")
    assert ai_pos < panel_pos
    assert meta["as_of"] == "2026-08-06"
    assert meta["emotion_score"] == 60
    assert meta["emotion_label"] == "强"
    assert "summary" in meta


async def test_panel_build_exception_stream_survives(monkeypatch):
    """面板构建异常韧性: build_auction_recap 抛 → 记日志按无面板处理, 流不崩。"""
    _patch_overview(monkeypatch)
    _patch_panel_error(monkeypatch)
    _patch_stream_ai(monkeypatch, ["AI-1"])
    _patch_news(monkeypatch)

    from app.services.market_recap import recap_market_once, recap_market_stream

    events = await _collect(recap_market_stream(_stub_repo(), as_of=FIXED_DATE))
    types = [e["type"] for e in events]
    assert types == ["meta", "delta", "done"]

    content, meta = await recap_market_once(_stub_repo(), as_of=FIXED_DATE)
    assert content == "AI-1"


# ================================================================
# Task 2 — 可选 AI 点评: pref 默认 False + PUT/GET + _build_user_prompt 可选参
#           + 护栏行 + 切片单源 (REV-04 验收 6 / R9 / R3)
# ================================================================


def _prefs_app(tmp_path, monkeypatch):
    """最小 FastAPI 应用 + settings.router + tmp data_dir 偏好隔离。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import settings as settings_api
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "data_dir", tmp_path / "data")
    app = FastAPI()
    app.include_router(settings_api.router)
    return TestClient(app)


def test_commentary_pref_default_false_roundtrip(tmp_path, monkeypatch):
    """pref 默认 False; set True → get True; set False → False (bool 强制)。"""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "data_dir", tmp_path / "data")

    from app.services import preferences

    assert preferences.get_recap_auction_commentary() is False
    assert preferences.set_recap_auction_commentary(True) is True
    assert preferences.get_recap_auction_commentary() is True
    assert preferences.set_recap_auction_commentary(False) is False
    assert preferences.get_recap_auction_commentary() is False


def test_settings_put_get_commentary(tmp_path, monkeypatch):
    """PUT /preferences/recap-auction-commentary 返回 saved; GET 透传键 (默认 False)。"""
    client = _prefs_app(tmp_path, monkeypatch)

    body = client.get("/api/settings/preferences").json()
    assert body["recap_auction_commentary"] is False

    resp = client.put(
        "/api/settings/preferences/recap-auction-commentary", json={"enabled": True},
    )
    assert resp.status_code == 200
    assert resp.json() == {"recap_auction_commentary": True}

    body2 = client.get("/api/settings/preferences").json()
    assert body2["recap_auction_commentary"] is True


def test_build_user_prompt_backward_compat_and_slice(monkeypatch, tmp_path):
    """R9: 现有 3 参调用输出逐位一致 (无切片节); auction_slice 非 None → 追加切片节在 focus 后。"""
    from app.services.market_recap import _build_user_prompt

    overview = _fake_overview()
    news = [
        {"title": "焦点A", "snippet": "焦点A详情", "source": "hhxg",
         "published_date": "2026-08-02T07:00:00"},
    ]
    # 3 参调用 (镜像 test_hhxg_market.py:158-180) — 无「竞价复盘数据」节
    baseline = _build_user_prompt(overview, news, "")
    assert "## 竞价复盘数据(确定性切片)" not in baseline
    assert "## 近期市场新闻" in baseline
    assert "焦点A" in baseline

    # 带 auction_slice → 切片节存在, 且位于 focus 节之后
    focused = _build_user_prompt(
        overview, news, "关注新能源", auction_slice="SLICE-TEXT",
    )
    assert "## 竞价复盘数据(确定性切片)" in focused
    assert "SLICE-TEXT" in focused
    assert focused.index("本次复盘请特别关注") < focused.index("SLICE-TEXT")


async def test_stream_guardrail_only_when_commentary_on(monkeypatch, tmp_path):
    """R3: 点评开启 → system 末尾追加护栏行 (局部串), user 含切片节; 关闭 → system 原样。"""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "data_dir", tmp_path / "data")

    from app.services import preferences
    from app.services.market_recap import _SYSTEM_PROMPT, recap_market_stream

    captured: dict = {}
    _capture_stream_ai(monkeypatch, captured)
    _patch_overview(monkeypatch)
    _patch_panel(monkeypatch, _fake_panel(["open_gap_snapshot"]))
    _patch_news(monkeypatch)

    # 默认关: system == _SYSTEM_PROMPT 原样, user 无切片节
    await _collect(recap_market_stream(_stub_repo(), as_of=FIXED_DATE))
    sys0 = captured["messages"][0]["content"]
    user0 = captured["messages"][1]["content"]
    assert sys0 == _SYSTEM_PROMPT
    assert "竞价复盘数据(确定性切片)" not in user0

    # 开启: system 末尾追加护栏行, user 含切片节 (面板 present 块 → 切片有值)
    preferences.set_recap_auction_commentary(True)
    await _collect(recap_market_stream(_stub_repo(), as_of=FIXED_DATE))
    sys1 = captured["messages"][0]["content"]
    user1 = captured["messages"][1]["content"]
    assert sys1.startswith(_SYSTEM_PROMPT)
    assert sys1.endswith(
        "竞价数据只引用下方切片中给出的数值;数据缺失时明说「今日无竞价数据」,禁止编造;与确定性面板冲突时以面板为准。"
    )
    assert "## 竞价复盘数据(确定性切片)" in user1
    preferences.set_recap_auction_commentary(False)


async def test_slice_and_panel_single_dict_source(monkeypatch, tmp_path):
    """REV-04 验收 6: build_auction_slice 收到的 panel 与 build_auction_recap 返回同一 dict 对象。"""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "data_dir", tmp_path / "data")

    from app.services import auction_recap, preferences
    from app.services.market_recap import recap_market_stream

    preferences.set_recap_auction_commentary(True)
    panel = _fake_panel(["open_gap_snapshot", "real_auction_activity", "preopen_signal_quality"])
    received: dict = {}
    slice_inputs: list = []

    def _spy_panel(*a, **k):
        received["panel"] = panel
        return panel

    def _spy_slice(p):
        slice_inputs.append(p)
        return "SLICE"

    monkeypatch.setattr(auction_recap, "build_auction_recap", _spy_panel)
    monkeypatch.setattr(auction_recap, "build_auction_slice", _spy_slice)
    _patch_overview(monkeypatch)
    _patch_stream_ai(monkeypatch, ["AI-1"])
    _patch_news(monkeypatch)

    events = await _collect(recap_market_stream(_stub_repo(), as_of=FIXED_DATE))
    # 面板 delta 照常发 (有 present 块)
    assert any(e["type"] == "delta" and "竞价复盘" in e["content"] for e in events)
    # 构造性单源: 切片与渲染共用同一 panel dict 对象
    assert slice_inputs and slice_inputs[0] is received["panel"]
    preferences.set_recap_auction_commentary(False)


async def test_slice_honest_when_panel_all_absent(monkeypatch, tmp_path):
    """全缺席 + 点评开启 → 切片仍构建并显式声明「今日无竞价数据」; user 仍收切片。"""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "data_dir", tmp_path / "data")

    from app.services import preferences
    from app.services.market_recap import recap_market_stream

    preferences.set_recap_auction_commentary(True)
    captured: dict = {}
    _capture_stream_ai(monkeypatch, captured)
    _patch_overview(monkeypatch)
    _patch_panel(monkeypatch, _fake_panel([]))  # 全缺席
    _patch_news(monkeypatch)

    events = await _collect(recap_market_stream(_stub_repo(), as_of=FIXED_DATE))
    types = [e["type"] for e in events]
    assert types == ["meta", "delta", "done"]  # 无面板 delta

    user = captured["messages"][1]["content"]
    assert "## 竞价复盘数据(确定性切片)" in user
    assert "今日无竞价数据" in user  # 诚实声明 (护栏语义)
    sys = captured["messages"][0]["content"]
    assert "禁止编造" in sys  # 护栏行已追加
    preferences.set_recap_auction_commentary(False)


# ================================================================
# Task 3 — 调度默认 15:40: preferences 默认 + Review.tsx 兜底字面量 + 回归
#           (REV-04 验收 7)
# ================================================================

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_review_schedule_default_1540(tmp_path, monkeypatch):
    """无已存偏好 → 默认 {"enabled": False, "hour": 15, "minute": 40}; docstring 注明理由。"""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "data_dir", tmp_path / "data")

    from app.services import preferences

    sched = preferences.get_review_schedule()
    assert sched == {"enabled": False, "hour": 15, "minute": 40}
    assert "15:40" in (preferences.get_review_schedule.__doc__ or "")


def test_review_schedule_saved_pref_retained(tmp_path, monkeypatch):
    """已存偏好保留 (向后兼容铁律): 旧偏好 15:10 → get 仍返回 10, 新默认不覆盖。"""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "data_dir", tmp_path / "data")

    from app.services import preferences

    preferences.set_review_schedule(True, 15, 10)
    sched = preferences.get_review_schedule()
    assert sched == {"enabled": True, "hour": 15, "minute": 10}


def test_review_schedule_floor_unchanged(tmp_path, monkeypatch):
    """15:00 下限不动: 14:59 → clamp 到 15:00; 15:30 原样。"""
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "data_dir", tmp_path / "data")

    from app.services import preferences

    assert preferences.set_review_schedule(True, 14, 59) == {
        "enabled": True, "hour": 15, "minute": 0,
    }
    assert preferences.set_review_schedule(True, 15, 30) == {
        "enabled": True, "hour": 15, "minute": 30,
    }


def test_review_tsx_fallback_literal_1540():
    """Review.tsx:105 兜底字面量 minute 10 → 40 (唯一前端触碰点, 非 Watchlist.tsx)。"""
    src = _REPO_ROOT / "frontend" / "src" / "pages" / "Review.tsx"
    text = src.read_text(encoding="utf-8")
    sched_line = next(
        (ln for ln in text.splitlines() if "reviewSched" in ln and "minute" in ln), "",
    )
    assert "minute: 40" in sched_line
    assert "minute: 10" not in text


def test_get_preferences_schedule_passthrough(tmp_path, monkeypatch):
    """GET /preferences 透传联动: 无偏好 → minute 40; set 旧偏好 → 10。"""
    client = _prefs_app(tmp_path, monkeypatch)

    from app.services import preferences

    assert client.get("/api/settings/preferences").json()["review_schedule"]["minute"] == 40
    preferences.set_review_schedule(True, 15, 10)
    assert client.get("/api/settings/preferences").json()["review_schedule"]["minute"] == 10


def test_review_job_registration_consumes_schedule():
    """注册消费零改动回归: daily_pipeline 仍按 review_sched["hour"]/["minute"] 注册。"""
    src = _REPO_ROOT / "backend" / "app" / "jobs" / "daily_pipeline.py"
    text = src.read_text(encoding="utf-8")
    assert '_register_review_job(scheduler, repo, review_sched["hour"], review_sched["minute"])' in text
