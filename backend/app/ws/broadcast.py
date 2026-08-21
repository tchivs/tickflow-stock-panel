"""线程安全的 WS 频道广播辅助 (Phase 55, Plan 02)。

后台线程 (backtest job 线程 / mining worker / QuoteService 轮询) 无法直接
await ``broadcast_to_channel`` — 需通过 ``asyncio.run_coroutine_threadsafe``
投递到主事件循环。此模块统一该逻辑:

  - 优先使用 bootstrap 捕获的主循环 (``ws_manager.get_main_loop()``);
  - 无主循环 (测试/未接入) 时降级为当前线程 ``get_event_loop``;
  - 任何失败静默跳过 (广播是尽力而为, 不阻断任务线程)。

用法::

    from app.ws.broadcast import broadcast_from_thread
    broadcast_from_thread(ws_manager, f"run:{job_key}", "job_progress", data)
"""
from __future__ import annotations

import asyncio
from typing import Any


def broadcast_from_thread(
    ws_manager: Any,
    channel: str,
    msg_type: str,
    data: dict,
) -> None:
    """从任意线程向 WS 频道广播 (尽力而为, 不抛异常)。"""
    if ws_manager is None:
        return
    loop = getattr(ws_manager, "get_main_loop", lambda: None)()
    if loop is None:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return
    if loop.is_closed():
        return
    try:
        asyncio.run_coroutine_threadsafe(
            ws_manager.broadcast_to_channel(channel, msg_type, data),
            loop,
        )
    except (RuntimeError, ValueError):
        # 主循环已关闭/调度失败: 广播尽力而为, 不影响任务线程
        return
