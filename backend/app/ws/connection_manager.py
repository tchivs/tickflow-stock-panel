"""WebSocket ConnectionManager + WsConnection。

D-06: 每连接维护 seq 计数器 + 环形缓冲区 (deque maxlen=1000)
D-10: 适配 QuoteService 广播模式 → WS 双向通信 + 频道订阅语义

Per-principal seq + ring buffer (Pitfall 2): 每个 principal 维护独立的 seq 计数器
和环形缓冲区, 跨重连持久 — 断连后重连发 resume 可从上次的 seq 继续。
不同 principal 的 seq 独立 (不共享)。
"""
from __future__ import annotations

import asyncio
from collections import deque
from typing import TYPE_CHECKING

from app.ws.protocol import RING_SIZE, make_msg

if TYPE_CHECKING:
    from fastapi import WebSocket


class WsConnection:
    """一个 WS 连接的状态: 频道订阅集 + seq + 环形缓冲区。

    seq 和 _ring 引用 ConnectionManager 中 per-principal 的持久缓冲区,
    断连重连后同一 principal 的连接继承上次的 seq 和 ring。
    """

    def __init__(self, ws: "WebSocket", principal: str) -> None:
        self.ws = ws
        self.principal = principal
        self.channels: set[str] = set()
        self.seq: int = 0
        self._ring: deque[dict] = deque(maxlen=RING_SIZE)  # D-06: 1000 条环形缓冲

    def next_seq(self) -> int:
        """递增并返回此连接的下一个 seq (per-principal, Pitfall 2)。"""
        self.seq += 1
        return self.seq

    def push_to_ring(self, msg: dict) -> None:
        """推入环形缓冲区 (溢出自动淘汰最旧)。"""
        self._ring.append(msg)

    def replay_after(self, last_seq: int) -> list[dict]:
        """重放 seq > last_seq 的消息 (按 seq 排序)。"""
        return [m for m in self._ring if m.get("seq", 0) > last_seq]


class ConnectionManager:
    """管理所有活跃 WS 连接, 支持频道订阅广播。

    维护 per-principal 的 seq + 环形缓冲区, 跨重连持久。
    """

    def __init__(self) -> None:
        self._connections: list[WsConnection] = []
        # per-principal 持久状态 (跨重连)
        self._principal_rings: dict[str, deque[dict]] = {}
        self._principal_seq: dict[str, int] = {}
        # 主事件循环引用 (bootstrap lifespan 捕获, 供后台线程 run_coroutine_threadsafe 投递)
        self._main_loop: asyncio.AbstractEventLoop | None = None

    def set_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """记录主事件循环 (bootstrap lifespan 内调用)。

        后台线程 (QuoteService 轮询 / backtest job 线程) 无法直接 await,
        需通过 run_coroutine_threadsafe 投递到主循环 — 必须先拿到引用。
        """
        self._main_loop = loop

    def get_main_loop(self) -> asyncio.AbstractEventLoop | None:
        return self._main_loop

    async def connect(self, ws: "WebSocket", principal: str) -> WsConnection:
        """接受 WS 握手, 创建 WsConnection 并加入连接列表。

        若同一 principal 之前有连接 (已断连), 恢复其 seq 和 ring buffer。
        """
        await ws.accept()
        conn = WsConnection(ws, principal)
        # 恢复 per-principal 持久状态
        if principal in self._principal_rings:
            conn._ring = self._principal_rings[principal]
            conn.seq = self._principal_seq[principal]
        else:
            # 首次连接: 注册 ring 和 seq 到 manager
            self._principal_rings[principal] = conn._ring
            self._principal_seq[principal] = 0
        self._connections.append(conn)
        return conn

    def disconnect(self, conn: WsConnection) -> None:
        """从连接列表移除, 保存 per-principal 状态供重连恢复。"""
        self._principal_rings[conn.principal] = conn._ring
        self._principal_seq[conn.principal] = conn.seq
        try:
            self._connections.remove(conn)
        except ValueError:
            pass  # 已被移除

    async def broadcast_to_channel(
        self, channel: str, msg_type: str, data: dict
    ) -> None:
        """只推送给订阅了指定频道的连接 (T-55-05: 信息泄露防护)。

        每个连接独立递增 seq, 独立入环形缓冲区。
        发送失败的连接静默跳过 (由 handler 清理)。
        """
        for conn in list(self._connections):
            if channel in conn.channels:
                seq = conn.next_seq()
                msg = make_msg(msg_type, seq, data)
                conn.push_to_ring(msg)
                try:
                    await conn.ws.send_json(msg)
                except Exception:  # noqa: BLE001 — 连接断开由 handler 清理
                    pass
