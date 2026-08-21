"""WebSocket /ws/stream 端点处理。

D-11: Cookie session 鉴权 (复用 auth.is_valid_session + resolve_authenticated_reviewer)
D-12 修正: 应用层 keepalive (非协议层 ping_interval)
T-55-01: Cookie 鉴权 + close(4001) 拒绝
T-55-04: MAX_CHANNELS_PER_CONNECTION 限制
T-55-05: 频道过滤 (broadcast_to_channel 只推已订阅频道)
"""
from __future__ import annotations

import asyncio

from fastapi import WebSocket, WebSocketDisconnect

from app.api.auth import COOKIE_NAME
from app.services import auth
from app.ws.protocol import KEEPALIVE_INTERVAL, MAX_CHANNELS_PER_CONNECTION, make_msg


async def ws_stream(websocket: WebSocket) -> None:
    """WebSocket /ws/stream 端点。

    流程: Cookie 鉴权 → accept → connected 欢迎消息 → keepalive + 消息循环 → 审计
    """
    from app.ws.connection_manager import ConnectionManager
    from app.audit.service import get_audit_repo
    from app.audit.envelope import AuditContext

    # ── Cookie 鉴权 (T-55-01) ──────────────────────────────────
    token = websocket.cookies.get(COOKIE_NAME)
    if not token or not auth.is_valid_session(token):
        await websocket.close(code=4001, reason="未登录或会话已过期")
        return
    principal = auth.resolve_authenticated_reviewer(token)
    if not principal:
        await websocket.close(code=4001, reason="principal 解析失败")
        return

    # ── 接受连接 ────────────────────────────────────────────────
    manager: ConnectionManager = websocket.app.state.ws_manager
    conn = await manager.connect(websocket, principal)

    # ── 发送欢迎消息 ────────────────────────────────────────────
    await conn.ws.send_json(make_msg("connected", 0, {"principal": principal}))

    # ── 启动 keepalive task (D-12 修正) ────────────────────────
    keepalive_task = asyncio.create_task(_keepalive(conn, KEEPALIVE_INTERVAL))

    # ── 审计 + 消息循环 ─────────────────────────────────────────
    repo = get_audit_repo()
    try:
        if repo is not None:
            with AuditContext(
                repo,
                tool="connection",
                category="external",
                params={"channels": []},
                scope="ws",
                principal=principal,
            ) as audit:
                try:
                    await _message_loop(conn)
                    audit.set_response(shape="ws", summary="connection closed normally")
                except WebSocketDisconnect:
                    audit.set_response(shape="ws", summary="client disconnected")
        else:
            await _message_loop(conn)
    except WebSocketDisconnect:
        pass
    finally:
        keepalive_task.cancel()
        try:
            await keepalive_task
        except asyncio.CancelledError:
            pass
        manager.disconnect(conn)


async def _message_loop(conn) -> None:
    """客户端消息分发循环。"""
    while True:
        try:
            msg = await conn.ws.receive_json()
        except WebSocketDisconnect:
            raise
        except Exception:  # noqa: BLE001 — JSON 解析失败等
            await conn.ws.send_json(
                make_msg("error", 0, {"reason": "invalid message format"})
            )
            continue

        msg_type = msg.get("type")
        if msg_type == "subscribe":
            channels = msg.get("channels", [])
            if not isinstance(channels, list):
                await conn.ws.send_json(
                    make_msg("error", 0, {"reason": "channels must be a list"})
                )
                continue
            # T-55-04: DoS 防护 — 限制每连接频道数
            new_channels = [c for c in channels if c not in conn.channels]
            if len(conn.channels) + len(new_channels) > MAX_CHANNELS_PER_CONNECTION:
                await conn.ws.send_json(
                    make_msg("error", 0, {
                        "reason": f"max {MAX_CHANNELS_PER_CONNECTION} channels per connection"
                    })
                )
                continue
            conn.channels.update(channels)
            await conn.ws.send_json(
                make_msg("subscribed", 0, {"channels": sorted(conn.channels)})
            )
        elif msg_type == "unsubscribe":
            channels = msg.get("channels", [])
            if not isinstance(channels, list):
                await conn.ws.send_json(
                    make_msg("error", 0, {"reason": "channels must be a list"})
                )
                continue
            conn.channels.difference_update(channels)
            await conn.ws.send_json(
                make_msg("unsubscribed", 0, {"channels": sorted(conn.channels)})
            )
        elif msg_type == "resume":
            last_seq = msg.get("last_seq", 0)
            if not isinstance(last_seq, int):
                last_seq = 0
            replay = conn.replay_after(last_seq)
            for m in replay:
                await conn.ws.send_json(m)
            await conn.ws.send_json(
                make_msg("resumed", 0, {"replayed": len(replay)})
            )
        elif msg_type == "request":
            # 保留给 Plan 02 ndjson 流; 此 plan 留 dispatch 分支但 no-op
            pass
        else:
            await conn.ws.send_json(
                make_msg("error", 0, {"reason": f"unknown type: {msg_type}"})
            )


async def _keepalive(conn, interval: float = 30.0) -> None:
    """应用层心跳: 每 interval 秒发一次 ping 消息 (D-12 修正)。

    Starlette WebSocket 无内置 ping_interval, 用应用层 JSON ping 替代。
    ping 也入环形缓冲区, 断连重连后可通过 resume 补收。
    """
    while True:
        await asyncio.sleep(interval)
        try:
            seq = conn.next_seq()
            msg = make_msg("ping", seq, {})
            conn.push_to_ring(msg)
            await conn.ws.send_json(msg)
        except Exception:  # noqa: BLE001 — 连接断开, 退出心跳
            break
