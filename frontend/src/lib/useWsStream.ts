/** 全局单连接 WebSocket hook (D-09)。
 *
 * 整个前端只开一个 WebSocket 连接 (/ws/stream), 所有流共享,
 * 通过 subscribe/unsubscribe 频道切换。
 *
 * 断连后指数退避重连 (D-13: 1s→2s→4s→8s→16s→30s),
 * 重连后发送 resume 恢复 seq + 重订阅所有频道。
 *
 * 连接状态 (connected/reconnecting/disconnected) 通过 useWsStreamStatus() 对外可见。
 *
 * 参考模式: useQuoteStream.ts 状态 store + stockdb_ws.py 重连/resume 模式。
 */
import { useEffect, useSyncExternalStore } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { BACKOFF_STEPS, FAILS_BEFORE_TOAST, isWsMessage, type WsMessage, type WsStatus } from './wsProtocol'
import { WS_INVALIDATE_PREFIXES } from './queryKeys'
import { toast } from '@/components/Toast'

// ── 模块级状态 (全局单连接 D-09) ──────────────────────────────

let _ws: WebSocket | null = null
let _seq = 0
let _backoffIndex = 0
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null
let _toastFired = false

// 频道 handler 注册表: channel → Set<handler>
const _channelHandlers = new Map<string, Set<(data: Record<string, unknown>) => void>>()

// ── 连接状态 store (仿 useQuoteStream.ts:41-78) ─────────────────

let _streamStatus: WsStatus = 'disconnected'
const _statusListeners = new Set<() => void>()

function _emitStatus(): void {
  _statusListeners.forEach((fn) => fn())
}

function _setStatus(s: WsStatus): void {
  if (_streamStatus === s) return
  _streamStatus = s
  _emitStatus()
}

function _subscribeStatus(fn: () => void): () => void {
  _statusListeners.add(fn)
  return () => { _statusListeners.delete(fn) }
}

function _getStatus(): WsStatus {
  return _streamStatus
}

/** React hook: 读取全局 WS 连接状态 */
export function useWsStreamStatus(): WsStatus {
  return useSyncExternalStore(_subscribeStatus, _getStatus, () => 'disconnected' as const)
}

// ── 连接管理 ──────────────────────────────────────────────���───

function _connect(): void {
  const wsUrl = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/stream`
  _ws = new WebSocket(wsUrl)

  _ws.onopen = (): void => {
    _setStatus('connected')
    _backoffIndex = 0
    if (_toastFired) {
      toast('实时连接已恢复', 'success')
    }
    _toastFired = false

    // 重连后发送 resume (D-06)
    if (_seq > 0) {
      _ws!.send(JSON.stringify({ type: 'resume', last_seq: _seq }))
    }
    // 重订阅所有频道
    const channels = Array.from(_channelHandlers.keys())
    if (channels.length > 0) {
      _ws!.send(JSON.stringify({ type: 'subscribe', channels }))
    }
  }

  _ws.onmessage = (e: MessageEvent): void => {
    let msg: unknown
    try {
      msg = JSON.parse(e.data)
    } catch {
      return
    }
    if (!isWsMessage(msg)) return

    // seq 推进: 只前进, 不后退
    if (typeof msg.seq === 'number' && msg.seq > _seq) {
      _seq = msg.seq
    }

    // 按 type 路由到 channel handler
    for (const [ch, handlers] of _channelHandlers) {
      if (msg.type === ch || msg.type.startsWith(ch)) {
        handlers.forEach((fn) => fn(msg.data))
      }
    }

    // React Query invalidation (复用 WS_INVALIDATE_PREFIXES 逻辑)
    _invalidateQueries(msg)
  }

  _ws.onclose = (): void => {
    _ws = null
    _scheduleReconnect()
  }

  _ws.onerror = (): void => {
    // onerror 后浏览器会触发 onclose
  }
}

function _scheduleReconnect(): void {
  if (_backoffIndex >= BACKOFF_STEPS.length) {
    _setStatus('disconnected')
    return
  }

  _setStatus('reconnecting')
  const delay = BACKOFF_STEPS[_backoffIndex]
  _backoffIndex++

  if (_backoffIndex >= FAILS_BEFORE_TOAST && !_toastFired) {
    _toastFired = true
    toast('实时连接已断开，正在重连…', 'error')
  }

  _reconnectTimer = setTimeout(_connect, delay)
}

// ── React Query invalidation ──────────────────────────────────

let _qc: ReturnType<typeof useQueryClient> | null = null

function _invalidateQueries(msg: WsMessage): void {
  if (!_qc) return
  // quotes_updated → 行情相关 queries
  if (msg.type === 'quotes_updated') {
    _qc.invalidateQueries({
      predicate: (query) =>
        WS_INVALIDATE_PREFIXES.some(
          (prefix) => String(query.queryKey[0]).startsWith(prefix),
        ),
    })
  }
}

// ── 公开 API ──────────────────────────────────────────────────

/** 订阅频道: 注册 handler, 返回 unsubscribe 函数。 */
export function subscribe(
  channel: string,
  handler: (data: Record<string, unknown>) => void,
): () => void {
  let handlers = _channelHandlers.get(channel)
  if (!handlers) {
    handlers = new Set()
    _channelHandlers.set(channel, handlers)
  }
  handlers.add(handler)

  // 若 WS 已连接且频道未订阅, 发送 subscribe
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify({ type: 'subscribe', channels: [channel] }))
  }

  return () => {
    handlers!.delete(handler)
    if (handlers!.size === 0) {
      _channelHandlers.delete(channel)
    }
    if (_ws && _ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ type: 'unsubscribe', channels: [channel] }))
    }
  }
}

/** 退订频道。 */
export function unsubscribe(channel: string): void {
  _channelHandlers.delete(channel)
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify({ type: 'unsubscribe', channels: [channel] }))
  }
}

/** 发送 request 消息 (供 Plan 03 ndjson 流使用)。 */
export function request(channel: string, params: Record<string, unknown>): void {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify({ type: 'request', channel, params }))
  }
}

/** 手动重连 (供 disconnected banner "重新连接" 按钮使用)。 */
export function _reconnect(): void {
  _backoffIndex = 0
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer)
    _reconnectTimer = null
  }
  if (_ws) {
    _ws.close()
    _ws = null
  }
  _connect()
}

/** 获取当前 backoff 步长 (秒), 供 UI 显示倒计时。 */
export function getCurrentBackoffSeconds(): number {
  if (_backoffIndex === 0 || _backoffIndex > BACKOFF_STEPS.length) return 0
  return BACKOFF_STEPS[Math.min(_backoffIndex - 1, BACKOFF_STEPS.length - 1)] / 1000
}

/** 全局单连接 WS hook — 在顶层 Layout 中调用一次。 */
export function useWsStream(
  enabled: boolean,
  // refreshPages: 保留给后续 Plan 02/03 按页面配置过滤 invalidation (当前全量刷新)
  _refreshPages?: Record<string, boolean>,
): void {
  const qc = useQueryClient()
  _qc = qc

  useEffect(() => {
    if (enabled) {
      _connect()
    }

    return (): void => {
      if (_reconnectTimer) {
        clearTimeout(_reconnectTimer)
        _reconnectTimer = null
      }
      if (_ws) {
        _ws.close()
        _ws = null
      }
      _setStatus('disconnected')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled])
}
