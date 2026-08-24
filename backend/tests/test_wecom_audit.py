"""PA-02: WeCom 推送投递审计单元测试。

测试 send_wecom / send_wecom_markdown 每次调用在 tool_call_envelopes 记录
tool=wecom 的审计条目 (成功/失败均记录), 且 get_audit_repo() 返回 None 时不报错。

模式参考: test_ws_audit.py 的 _FakeRepo。
直接 monkeypatch _post_wecom 控制成功/失败, 验证审计调用。
"""
from __future__ import annotations

import pytest

from app.audit.envelope import ToolCallAuditRepository
from app.audit.service import get_audit_repo, set_audit_repo
from app.services import webhook_adapter

_VALID_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key-1234567890"


class _FakeRepo(ToolCallAuditRepository):
    """内存版审计 repo, 仅记录 append 调用。"""

    def __init__(self):
        self._records: list[dict] = []
        self._seq = 0

    def append(self, **kwargs):
        self._seq += 1
        rec = {"seq": self._seq, **kwargs}
        self._records.append(rec)
        return rec

    def list_records(self):
        return list(self._records)


@pytest.fixture
def _audit_repo():
    """注入 FakeRepo 审计单例, 测试后恢复。"""
    fake = _FakeRepo()
    original = get_audit_repo()
    set_audit_repo(fake)
    yield fake
    set_audit_repo(original)


def test_send_wecom_success_records_audit(monkeypatch, _audit_repo):
    """send_wecom 成功时审计记录 tool=wecom, category=notification, error=None。"""
    monkeypatch.setattr(webhook_adapter, "_post_wecom_detail", lambda url, payload: (True, "HTTP 200 errcode=0"))
    result = webhook_adapter.send_wecom(_VALID_URL, "测试标题", "正文")
    assert result is True
    records = _audit_repo.list_records()
    assert len(records) == 1
    rec = records[0]
    assert rec["tool"] == "wecom"
    assert rec["category"] == "notification"
    assert rec["error"] is None
    assert rec["response_summary"] == "HTTP 200 errcode=0"
    assert rec["scope"].startswith("push:测试标题")
    assert rec["duration_ms"] >= 0


def test_send_wecom_failure_records_audit(monkeypatch, _audit_repo):
    """send_wecom 失败时审计记录 tool=wecom, error='wecom delivery failed'。"""
    monkeypatch.setattr(webhook_adapter, "_post_wecom_detail", lambda url, payload: (False, "HTTP 200 errcode=93000 invalid webhook url"))
    result = webhook_adapter.send_wecom(_VALID_URL, "失败标题", "正文")
    assert result is False
    records = _audit_repo.list_records()
    assert len(records) == 1
    rec = records[0]
    assert rec["tool"] == "wecom"
    assert rec["error"] == "wecom delivery failed"
    assert rec["response_summary"] == "HTTP 200 errcode=93000 invalid webhook url"


def test_send_wecom_markdown_success_records_audit(monkeypatch, _audit_repo):
    """send_wecom_markdown 成功时审计记录 tool=wecom。"""
    monkeypatch.setattr(webhook_adapter, "_post_wecom_detail", lambda url, payload: (True, "HTTP 200 errcode=0"))
    result = webhook_adapter.send_wecom_markdown(_VALID_URL, "复盘报告", "## 大盘概览\n\n今日震荡收平。")
    assert result is True
    records = _audit_repo.list_records()
    assert len(records) == 1
    rec = records[0]
    assert rec["tool"] == "wecom"
    assert rec["category"] == "notification"
    assert rec["error"] is None
    assert rec["response_summary"] == "HTTP 200 errcode=0"


def test_send_wecom_no_audit_repo_not_error(monkeypatch):
    """get_audit_repo 返回 None 时不报错 (推送仍正常)。"""
    monkeypatch.setattr(webhook_adapter, "_post_wecom_detail", lambda url, payload: (True, "HTTP 200 errcode=0"))
    original = get_audit_repo()
    set_audit_repo(None)
    try:
        result = webhook_adapter.send_wecom(_VALID_URL, "无审计", "正文")
        assert result is True  # 推送不受影响
    finally:
        set_audit_repo(original)


def test_post_wecom_detail_success_returns_summary(monkeypatch):
    """_post_wecom_detail 成功时返回 (True, 'HTTP 200 errcode=0')。"""
    from unittest.mock import MagicMock

    import httpx

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"errcode": 0, "errmsg": "ok"}
    resp.text = '{"errcode":0,"errmsg":"ok"}'
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: resp)

    ok, summary = webhook_adapter._post_wecom_detail(_VALID_URL, {"msgtype": "text"})
    assert ok is True
    assert "errcode=0" in summary


def test_post_wecom_detail_business_failure_returns_errcode(monkeypatch):
    """_post_wecom_detail 业务失败时返回 (False, 'HTTP 200 errcode=xxx')。"""
    from unittest.mock import MagicMock

    import httpx

    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"errcode": 45009, "errmsg": "frequency limited"}
    resp.text = '{"errcode":45009}'
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: resp)

    ok, summary = webhook_adapter._post_wecom_detail(_VALID_URL, {"msgtype": "text"})
    assert ok is False
    assert "45009" in summary
    assert "frequency limited" in summary


def test_post_wecom_detail_http_error(monkeypatch):
    """_post_wecom_detail HTTP 非200时返回 (False, 'HTTP xxx')。"""
    from unittest.mock import MagicMock

    import httpx

    resp = MagicMock()
    resp.status_code = 500
    resp.text = "Internal Server Error"
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: resp)

    ok, summary = webhook_adapter._post_wecom_detail(_VALID_URL, {"msgtype": "text"})
    assert ok is False
    assert "HTTP 500" in summary


def test_post_wecom_detail_exception(monkeypatch):
    """_post_wecom_detail 网络异常时返回 (False, 'exception: ...')。"""
    import httpx

    def _raise(*a, **kw):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx, "post", _raise)

    ok, summary = webhook_adapter._post_wecom_detail(_VALID_URL, {"msgtype": "text"})
    assert ok is False
    assert "exception" in summary
