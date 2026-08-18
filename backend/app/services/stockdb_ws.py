"""stockdb WS 实时通道客户端 (M004)。

连接本地 stockdb ``/ws/stream``(服务端 3s 轮询 → 增量推送, seq 全局单调),
X-API-Key header 鉴权。协议(stockdb src/stockdb/api/ws.py, 2026-08 实测):

  发: ``{"op":"subscribe","channel":"quotes"|"depth"|"alerts","symbols":[...]}``
      ``{"op":"unsubscribe",...}`` / ``{"op":"resume","last_seq":N}``
  收: ``{"op":"subscribed","channel",...,"total"}`` — 订阅确认(quotes/depth 随首推全量帧)
      ``{"op":"quotes"|"depth","data":[{"seq","ts","symbol","snap"|"depth"}]}``
      ``{"op":"alerts","data":[{"symbol","pct_chg","last","ts","level"}]}``
      ``{"op":"error","reason":...}``

可靠性: 断线指数退避重连(min(1*2^n,60)+jitter, 与 stockdb ThsPushService 同式);
重连后先 ``resume last_seq`` 补断帧(服务端环缓冲 10k, 过旧自动全量兜底)再全量
重订阅(新连接订阅关系从零开始)。客户端发送侧限频 1 msg/s(服务端 60 msg/min)。

消费方:
  quotes → quote_service(指数实时缓存 + 自选 WS 驱动, S1/T02)
  alerts → 环缓冲(deque 500) + GET /api/intraday/alerts(S3/T01)
  depth  → 预留协议支持, S2 走 HTTP 批量(涨跌停池动态, 按需拉更直接)
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import threading
import time
from collections import deque
from typing import Any, Callable

logger = logging.getLogger(__name__)

# 订阅命令节流间隔(秒) — 服务端消息限频 60 msg/min = 1 msg/s, 留裕量
_SUB_SEND_INTERVAL = 1.2
# alerts 环缓冲容量(前端 since 游标增量拉取的上界)
_ALERTS_RING = 500


def _ws_url(base_url: str) -> str:
    """``http://host:8000`` → ``ws://host:8000/ws/stream``(https → wss)。"""
    u = base_url.rstrip("/")
    if u.startswith("https://"):
        u = "wss://" + u[len("https://"):]
    elif u.startswith("http://"):
        u = "ws://" + u[len("http://"):]
    return u + "/ws/stream"


class StockDBWS:
    """stockdb WS 客户端单例 — 生命周期由 bootstrap 持有(app.state.stockdb_ws)。

    线程模型: ``_run`` 在 asyncio 事件循环; ``set_quotes_symbols``/``status``
    允许任意线程调用(内部 threading.Lock + asyncio.Event 唤醒读循环)。
    回调在事件循环线程执行 — 消费方(quote_service)内部锁为 threading.Lock,
    短临界区跨线程获取安全, 回调内不得阻塞长 IO。
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        self._url = _ws_url(base_url)
        self._api_key = api_key
        self._task: asyncio.Task | None = None
        self._closing = False

        # 期望订阅集(线程安全); 连接后向其收敛
        self._lock = threading.Lock()
        self._wanted: dict[str, set[str]] = {"quotes": set(), "alerts": set(), "depth": set()}
        self._sync_evt: asyncio.Event | None = None

        # 回调: channel -> callable(list[data_items])
        self._handlers: dict[str, Callable[[list[dict]], None]] = {}

        # 状态自省
        self._connected = False
        self._last_seq = 0
        self._last_msg_ts = 0.0
        self._last_msg_at = 0.0
        self._reconnects = 0
        self._subscribed_total = 0
        self._alerts_gate: str = "unknown"  # open|quiet|closed — S3 消费

        # alerts 环缓冲(服务端仅事件推送, 无首推)
        self._ring: deque[dict] = deque(maxlen=_ALERTS_RING)
        self._subscribed_at: dict[str, float] = {}

    # ================================================================ 生命周期

    def start(self) -> None:
        """幂等启动(须在事件循环线程, 如 FastAPI lifespan)。未配 key → no-op。"""
        if not self._api_key:
            logger.info("stockdb WS: 未配置 LOCAL_STOCKDB_API_KEY, 跳过")
            return
        if self._task is not None and not self._task.done():
            return
        self._closing = False
        self._sync_evt = asyncio.Event()
        self._task = asyncio.create_task(self._run())
        logger.info("stockdb WS: 客户端启动 %s", self._url)

    def stop(self) -> None:
        """幂等停止(任意线程; cancel 后由 _run finally 收口)。"""
        self._closing = True
        if self._task is not None:
            self._task.cancel()
        logger.info("stockdb WS: 客户端停止 (reconnects=%d, last_seq=%d)",
                    self._reconnects, self._last_seq)

    # ================================================================ 订阅管理

    def on(self, channel: str, handler: Callable[[list[dict]], None]) -> None:
        """注册频道回调(data item 列表入参)。"""
        self._handlers[channel] = handler

    def set_quotes_symbols(self, symbols: list[str]) -> None:
        """更新 quotes 期望订阅集(任意线程); 变更唤醒读循环增量订阅。"""
        want = set(symbols)
        with self._lock:
            if self._wanted["quotes"] == want:
                return
            self._wanted["quotes"] = want
        self._wake()
        logger.info("stockdb WS: quotes 订阅集更新 → %d 只", len(want))

    # ================================================================ 状态 / alerts

    def status(self) -> dict:
        """连接状态快照(供 /api/intraday/status 与健康判定)。"""
        with self._lock:
            wanted = {ch: len(s) for ch, s in self._wanted.items()}
        now = time.time()
        return {
            "url": self._url,
            "configured": bool(self._api_key),
            "connected": self._connected,
            "reconnects": self._reconnects,
            "last_seq": self._last_seq,
            "last_msg_age_s": round(now - self._last_msg_at, 1) if self._last_msg_at else None,
            "subscribed": self._subscribed_total,
            "wanted": wanted,
            "alerts_gate": self._alerts_gate,
        }

    def is_healthy(self, max_age_s: float = 30.0) -> bool:
        """WS 通道健康: 已连接 + 近期有消息(交易时段 3s 推送; 30s 覆盖静默期裕量)。"""
        if not self._connected or not self._last_msg_at:
            return False
        return (time.time() - self._last_msg_at) <= max_age_s

    # ================================================================ 内部

    def _wake(self) -> None:
        evt = self._sync_evt
        if evt is not None:
            evt.set()

    async def _run(self) -> None:
        """重连循环: 连接 → resume → 全量重订阅 → 读循环分发。"""
        import websockets

        backoff = 0
        try:
            while not self._closing:
                try:
                    async with websockets.connect(
                        self._url,
                        additional_headers={"X-API-Key": self._api_key},
                        ping_interval=20,
                        ping_timeout=20,
                        close_timeout=5,
                    ) as ws:
                        backoff = 0
                        self._connected = True
                        logger.info("stockdb WS: 已连接 %s", self._url)
                        await self._after_connect(ws)
                        await self._read_loop(ws)
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001 — 任何断线都走退避重连
                    self._connected = False
                    backoff += 1
                    delay = min(1.0 * 2 ** min(backoff, 6), 60.0) + random.uniform(0, 0.5)
                    logger.warning("stockdb WS: 连接断开(%s), %.1fs 后第 %d 次重连",
                                   type(e).__name__, delay, backoff)
                    await asyncio.sleep(delay)
                    self._reconnects += 1
        except asyncio.CancelledError:
            pass
        finally:
            self._connected = False

    async def _after_connect(self, ws) -> None:
        """重连后: resume 补断帧(有历史 seq 才有意义) + 重建全部期望订阅。"""
        if self._last_seq > 0:
            try:
                await ws.send(json.dumps({"op": "resume", "last_seq": self._last_seq}))
                logger.info("stockdb WS: resume last_seq=%d", self._last_seq)
            except Exception:  # noqa: BLE001
                pass
        with self._lock:
            wanted = {ch: set(s) for ch, s in self._wanted.items()}
        for channel in ("quotes", "depth", "alerts"):
            syms = sorted(wanted.get(channel, set()))
            if channel == "quotes" and not syms:
                continue  # quotes 需显式标的; alerts/depth 空集=全频道事件
            await self._send_subscribe(ws, channel, syms)
            self._subscribed_at[channel] = time.time()

    async def _send_subscribe(self, ws, channel: str, symbols: list[str]) -> None:
        await ws.send(json.dumps({"op": "subscribe", "channel": channel, "symbols": symbols}))
        await asyncio.sleep(_SUB_SEND_INTERVAL)  # 发送侧限频(1 msg/s)
        self._subscribed_total = sum(len(s) for s in self._wanted.values())

    async def _read_loop(self, ws) -> None:
        """读循环: recv 与订阅变更事件二选一等待, 帧分发 + 收敛订阅集。"""
        while not self._closing:
            recv_task = asyncio.ensure_future(ws.recv())
            evt = self._sync_evt
            sync_task = asyncio.ensure_future(evt.wait()) if evt is not None else None
            try:
                wait_set = {recv_task, sync_task} if sync_task else {recv_task}
                done, _ = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)
                if recv_task in done:
                    raw = recv_task.result()
                    self._dispatch(json.loads(raw))
                if sync_task is not None and sync_task in done:
                    evt.clear()
                    await self._sync_subscriptions(ws)
            finally:
                for t in (recv_task, sync_task):
                    if t is not None and not t.done():
                        t.cancel()

    async def _sync_subscriptions(self, ws) -> None:
        """期望集变更 → 重发 quotes 订阅(服务端 subscribe 幂等覆盖该频道)。"""
        with self._lock:
            syms = sorted(self._wanted["quotes"])
        if not syms:
            return
        try:
            await self._send_subscribe(ws, "quotes", syms)
        except Exception as e:  # noqa: BLE001 — 发送失败留给读循环异常重连
            logger.warning("stockdb WS: 订阅同步失败: %s", e)

    def _dispatch(self, msg: dict) -> None:
        """单帧分发: seq/时间戳推进 + 频道回调 + alerts 入环缓冲。"""
        op = msg.get("op")
        if op == "subscribed":
            logger.info("stockdb WS: subscribed %s (total=%s)", msg.get("channel"), msg.get("total"))
            return
        if op == "error":
            logger.warning("stockdb WS: 服务端 error: %s", msg.get("reason"))
            return
        data = msg.get("data")
        if not isinstance(data, list) or not data:
            return
        now = time.time()
        for item in data:
            seq = item.get("seq")
            if isinstance(seq, int) and seq > self._last_seq:
                self._last_seq = seq
        self._last_msg_ts = now
        self._last_msg_at = now
        if op == "alerts":
            with self._lock:
                for item in data:
                    item.setdefault("seq", self._last_seq)
                    self._ring.append(item)
            self._alerts_gate = "open"  # 帧到达即证明上游推送链路通
        handler = self._handlers.get(op)
        if handler is not None:
            try:
                handler(data)
            except Exception:  # noqa: BLE001 — 回调异常不拖垮读循环
                logger.exception("stockdb WS: %s 回调异常", op)

    def alerts_since(self, since_seq: int = 0, limit: int = 100) -> dict:
        """alerts 环缓冲增量读取(线程安全)。返回 {events, cursor, gate}。

        gate 语义: 有帧到达 = open; 订阅 ≥120s 仍无帧 = closed(上游 THS 门控
        未开, stockdb THS_PUSH_ENABLED=0); 刚订阅 = quiet(等待判定期)。
        """
        with self._lock:
            events = [e for e in self._ring if e.get("seq", 0) > since_seq]
            gate = self._alerts_gate
            sub_at = self._subscribed_at.get("alerts")
        if gate != "open" and sub_at is not None:
            gate = "closed" if (time.time() - sub_at) >= 120 else "quiet"
        events.sort(key=lambda e: e.get("seq", 0))
        return {
            "events": events[-limit:],
            "cursor": self._last_seq,
            "source_gate": gate,
        }
