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
 * 参考模式: stockdb_ws.py 重连/resume 模式。
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
// handler 签名: (data, type) — type 为 WS 消息 type 字段, 供消费方按事件类型分发
const _channelHandlers = new Map<string, Set<(data: Record<string, unknown>, type: string) => void>>()

// ── 频道 → 事件类型映射 (反向路由 T-55-09) ─────────────────────
//
// WS 消息的 type 字段 (如 job_progress) 不以频道名 (如 run:abc) 开头,
// 无法用 startsWith 匹配。这里维护频道前缀 → 事件类型集合的映射,
// onmessage 时按频道前缀查找所属事件类型集, 精确路由。
//
// 静态频道 (quotes/alerts/portfolio/review/depth) 用精确频道名做 key;
// 动态频道 (run:*/analysis:*) 用前缀做 key, 匹配时按前缀查找。

const RUN_CHANNEL_EVENTS = new Set([
  // backtest / optimize / walkforward 任务流
  'job', 'job_progress', 'job_done', 'job_error',
  'progress', 'done', 'error',
  // walkforward plan 流
  'wf_progress', 'wf_done', 'wf_error',
  // forecast 流
  'forecast_progress',
  // mining 流 (terminal 事件类型即状态名)
  'terminal',
  'succeeded', 'succeeded_with_budget_exhausted',
  'failed', 'cancelled', 'interrupted', 'skipped_prerequisite',
  // alpha 流 (research_alpha_sse 的事件类型)
  'run_started', 'run_recovered', 'run_preflight_failed',
  'cancel_requested', 'run_cancelled', 'run_completed', 'run_failed',
  'candidate_appended', 'stage_started', 'stage1_completed', 'stage2_completed',
  'diagnostic', 'worker_noise',
])

const ANALYSIS_CHANNEL_EVENTS = new Set([
  'analysis_meta', 'analysis_delta', 'analysis_done', 'analysis_error',
  'analysis_progress', 'advanced_progress',
])

const REVIEW_CHANNEL_EVENTS = new Set([
  'review_meta', 'review_delta', 'review_done', 'review_error',
  'review_progress',
])

// 静态频道事件类型 (精确匹配)
const STATIC_CHANNEL_EVENTS: Record<string, Set<string>> = {
  quotes: new Set(['quotes_updated', 'strategy_results_updated']),
  alerts: new Set(['strategy_alert']),
  portfolio: new Set(['portfolio_updated']),
  review: REVIEW_CHANNEL_EVENTS,
  depth: new Set(['depth_updated']),
}

// 动态频道前缀 → 事件类型集
const DYNAMIC_PREFIX_EVENTS: Array<{ prefix: string; events: Set<string> }> = [
  { prefix: 'run:', events: RUN_CHANNEL_EVENTS },
  { prefix: 'analysis:', events: ANALYSIS_CHANNEL_EVENTS },
]

/** 判断消息 type 是否属于某频道 (精确路由 T-55-09)。 */
function _typeBelongsToChannel(type: string, channel: string): boolean {
  // 1. 静态频道: 精确匹配
  const staticEvents = STATIC_CHANNEL_EVENTS[channel]
  if (staticEvents) {
    return staticEvents.has(type)
  }
  // 2. 动态频道: 按前缀匹配事件类型集
  for (const { prefix, events } of DYNAMIC_PREFIX_EVENTS) {
    if (channel.startsWith(prefix)) {
      return events.has(type)
    }
  }
  // 3. 兜底: type === channel 或 type 以 channel 开头 (向后兼容)
  return type === channel || type.startsWith(channel)
}

// ── 连接状态 store ─────────────────

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

// ── 连接管理 ──────────────────────────────────────────────────

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

    // 按 type 路由到 channel handler (精确路由 T-55-09)
    for (const [ch, handlers] of _channelHandlers) {
      if (_typeBelongsToChannel(msg.type, ch)) {
        handlers.forEach((fn) => fn(msg.data, msg.type))
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

/** 订阅频道: 注册 handler, 返回 unsubscribe 函数。
 *
 * handler 签名: (data, type) — data 为 WS 消息 data 字段, type 为消息类型字符串。
 * 消费方可按 type 分发 (如 type === 'job_done' / 'job_progress')。
 */
export function subscribe(
  channel: string,
  handler: (data: Record<string, unknown>, type: string) => void,
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

/** 发送 request 消息 (供 ndjson 流使用: 触发后端 LLM 流式生成 → 频道推送)。 */
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

// ── 焦点股票注册 (供行情订阅使用) ─────────────────

let _focusSymbol: string | null = null

/** 注册当前焦点股票 (个股对话框打开时调用)。 */
export function setFocusSymbol(symbol: string): void {
  _focusSymbol = symbol
}

/** 清除焦点股票 (个股对话框关闭时调用)。 */
export function clearFocusSymbol(): void {
  _focusSymbol = null
}

/** 读取当前焦点股票 (供 useWsStream 的 kline invalidation 使用)。 */
export function getFocusSymbol(): string | null {
  return _focusSymbol
}

// ── AsyncQueue: ndjson async generator 缓冲 (Plan 03 Task 2) ─────
//
// ndjson async generator 消费方接口不变 (for await ... of),
// 底层从 fetch+ReadableStream 换成 WS 频道订阅 + 异步队列缓冲。
// push() 入队, close() 标记流结束, async iterator 逐个 yield。

export class AsyncQueue<T = Record<string, unknown>> implements AsyncIterable<T> {
  private _items: T[] = []
  private _resolvers: Array<(value: IteratorResult<T, undefined>) => void> = []
  private _closed = false

  push(item: T): void {
    if (this._closed) return
    if (this._resolvers.length > 0) {
      const resolve = this._resolvers.shift()!
      resolve({ value: item, done: false })
    } else {
      this._items.push(item)
    }
  }

  close(): void {
    if (this._closed) return
    this._closed = true
    // 唤醒所有等待的消费者, 让它们收到 done=true
    for (const resolve of this._resolvers) {
      resolve({ value: undefined, done: true })
    }
    this._resolvers = []
  }

  get closed(): boolean {
    return this._closed
  }

  [Symbol.asyncIterator](): AsyncIterator<T, undefined> {
    const next = (): Promise<IteratorResult<T, undefined>> => {
      if (this._items.length > 0) {
        return Promise.resolve({ value: this._items.shift()!, done: false })
      }
      if (this._closed) {
        return Promise.resolve({ value: undefined, done: true })
      }
      return new Promise<IteratorResult<T, undefined>>((resolve) => {
        this._resolvers.push(resolve)
      })
    }
    return { next }
  }
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
