"""Phase 52: 全局审计服务单例。

由 bootstrap 在启动时注入 ToolCallAuditRepository 实例,
各调用方通过 get_audit_repo() 获取, 如果未注入则返回 None (无审计)。
"""
from __future__ import annotations

from app.audit.envelope import ToolCallAuditRepository

_audit_repo: ToolCallAuditRepository | None = None


def set_audit_repo(repo: ToolCallAuditRepository | None) -> None:
    """由 bootstrap 在启动时调用。"""
    global _audit_repo
    _audit_repo = repo


def get_audit_repo() -> ToolCallAuditRepository | None:
    """获取全局审计 repository, 未注入时返回 None。"""
    return _audit_repo
