import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { BACKOFF_STEPS, isWsMessage } from './wsProtocol'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'

// useWsStream uses module-level state (global single connection D-09),
// so tests must be carefully ordered to avoid cross-test interference.

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  }
}

describe('wsProtocol', () => {
  describe('BACKOFF_STEPS', () => {
    it('has 6 exponential backoff steps ending at 30000', () => {
      expect(BACKOFF_STEPS).toEqual([1000, 2000, 4000, 8000, 16000, 30000])
    })
  })

  describe('isWsMessage', () => {
    it('accepts a valid WsMessage', () => {
      const msg: unknown = { type: 'quotes_updated', seq: 1, data: { ts: 123 } }
      expect(isWsMessage(msg)).toBe(true)
    })

    it('rejects null', () => {
      expect(isWsMessage(null)).toBe(false)
    })

    it('rejects non-objects', () => {
      expect(isWsMessage('hello')).toBe(false)
      expect(isWsMessage(42)).toBe(false)
      expect(isWsMessage(undefined)).toBe(false)
      expect(isWsMessage([])).toBe(false)
    })

    it('rejects objects with missing fields', () => {
      expect(isWsMessage({ type: 'test' })).toBe(false)
      expect(isWsMessage({ type: 'test', seq: 1 })).toBe(false)
      expect(isWsMessage({ seq: 1, data: {} })).toBe(false)
    })

    it('rejects wrong types for fields', () => {
      expect(isWsMessage({ type: 123, seq: 1, data: {} })).toBe(false)
      expect(isWsMessage({ type: 'test', seq: 'abc', data: {} })).toBe(false)
    })

    it('accepts empty data object', () => {
      expect(isWsMessage({ type: 'ping', seq: 0, data: {} })).toBe(true)
    })
  })
})

// ── useWsStream tests ────────────────────────────────────────────
// These tests exercise the global WS hook's subscribe/unsubscribe/status/seq/routing.
// We mock WebSocket to avoid real network connections.

describe('useWsStream', () => {
  let mockWs: {
    onopen: (() => void) | null
    onmessage: ((e: { data: string }) => void) | null
    onclose: (() => void) | null
    onerror: (() => void) | null
    send: ReturnType<typeof vi.fn>
    close: ReturnType<typeof vi.fn>
    readyState: number
  }

  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()

    mockWs = {
      onopen: null,
      onmessage: null,
      onclose: null,
      onerror: null,
      send: vi.fn(),
      close: vi.fn(),
      readyState: 1, // OPEN
    }

    const WSConstructor = Object.assign(vi.fn(() => mockWs), { OPEN: 1, CLOSED: 3 })
    vi.stubGlobal('WebSocket', WSConstructor)
    vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:3011' })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // Helper: import fresh module + render hook with provider, trigger onopen
  async function setupHook() {
    const mod = await import('./useWsStream')
    const wrapper = createWrapper()
    const result = renderHook(() => mod.useWsStream(true), { wrapper })
    mockWs.onopen!()
    return { mod, result }
  }

  // Helper: disconnect + flush reconnect timer + trigger onopen
  function reconnect() {
    mockWs.onclose!()
    vi.advanceTimersByTime(BACKOFF_STEPS[0] + 1)
    mockWs.onopen!()
  }

  it('test_subscribe_unsubscribe: subscribe sends subscribe message, unsubscribe sends unsubscribe', async () => {
    const { mod, result } = await setupHook()
    mockWs.send.mockClear()

    const unsub = mod.subscribe('quotes', () => {})
    expect(mockWs.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'subscribe', channels: ['quotes'] }),
    )

    unsub()
    expect(mockWs.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'unsubscribe', channels: ['quotes'] }),
    )

    result.unmount()
  })

  it('test_backoff_sequence: reconnect uses exponential backoff', async () => {
    const { result } = await setupHook()
    const setTimeoutSpy = vi.spyOn(global, 'setTimeout')

    mockWs.onclose!()
    expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), BACKOFF_STEPS[0])

    setTimeoutSpy.mockRestore()
    result.unmount()
  })

  it('test_resume_on_reconnect: reconnect sends resume with last_seq', async () => {
    const { result } = await setupHook()
    mockWs.send.mockClear()

    // Simulate receiving a message with seq=5
    mockWs.onmessage!({ data: JSON.stringify({ type: 'quotes_updated', seq: 5, data: {} }) })

    // Simulate disconnect + reconnect
    reconnect()

    // Should have sent resume with last_seq=5
    expect(mockWs.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'resume', last_seq: 5 }),
    )

    result.unmount()
  })

  it('test_resubscribe_on_reconnect: reconnect resubscribes all channels', async () => {
    const { mod, result } = await setupHook()
    mockWs.send.mockClear()

    const unsub = mod.subscribe('quotes', () => {})
    expect(mockWs.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'subscribe', channels: ['quotes'] }),
    )

    // Disconnect + reconnect
    reconnect()

    // Should resubscribe quotes
    expect(mockWs.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'subscribe', channels: ['quotes'] }),
    )

    unsub()
    result.unmount()
  })

  it('test_seq_advancement: seq advances forward, never backward', async () => {
    const { result } = await setupHook()
    mockWs.send.mockClear()

    // Receive seq=5
    mockWs.onmessage!({ data: JSON.stringify({ type: 'ping', seq: 5, data: {} }) })

    // Receive seq=3 (old) — should not affect internal _seq
    mockWs.onmessage!({ data: JSON.stringify({ type: 'ping', seq: 3, data: {} }) })

    // Disconnect + reconnect — resume should use last_seq=5 (not 3)
    reconnect()

    expect(mockWs.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'resume', last_seq: 5 }),
    )

    result.unmount()
  })

  it('test_message_routing: handler called when message type matches channel', async () => {
    const { mod, result } = await setupHook()
    const handler = vi.fn()
    mockWs.send.mockClear()

    const unsub = mod.subscribe('quotes', handler)

    // Receive a quotes_updated message
    const data = { ts: 12345, symbol_count: 10 }
    mockWs.onmessage!({
      data: JSON.stringify({ type: 'quotes_updated', seq: 1, data }),
    })

    // handler 签名 (data, type) — 消费方按事件类型分发
    expect(handler).toHaveBeenCalledWith(data, 'quotes_updated')

    unsub()
    result.unmount()
  })

  it('test_status_store: useWsStreamStatus returns disconnected initially, then connected', async () => {
    const mod = await import('./useWsStream')
    const wrapper = createWrapper()

    const statusHook = renderHook(() => mod.useWsStreamStatus(), { wrapper })
    expect(statusHook.result.current).toBe('disconnected')

    const streamHook = renderHook(() => mod.useWsStream(true), { wrapper })
    mockWs.onopen!()

    statusHook.rerender()
    expect(statusHook.result.current).toBe('connected')

    streamHook.unmount()
    statusHook.unmount()
  })
})

// ── AsyncQueue + ndjson stream tests (Plan 03 Task 2) ──────────────

describe('AsyncQueue', () => {
  it('test_async_queue_basic: push and iterate items in order', async () => {
    const { AsyncQueue } = await import('./useWsStream')
    const queue = new AsyncQueue<{ type: string; content?: string }>()
    queue.push({ type: 'meta' })
    queue.push({ type: 'delta', content: 'a' })
    queue.push({ type: 'done' })
    queue.close()

    const results: { type: string; content?: string }[] = []
    for await (const item of queue) {
      results.push(item)
    }
    expect(results).toEqual([
      { type: 'meta' },
      { type: 'delta', content: 'a' },
      { type: 'done' },
    ])
  })

  it('test_async_queue_close_stops_iteration: close after push yields all items then ends', async () => {
    const { AsyncQueue } = await import('./useWsStream')
    const queue = new AsyncQueue<number>()
    queue.push(1)
    queue.push(2)
    queue.close()

    const results: number[] = []
    for await (const item of queue) {
      results.push(item)
    }
    expect(results).toEqual([1, 2])
  })

  it('test_async_queue_async_push: push after consumer starts waiting', async () => {
    const { AsyncQueue } = await import('./useWsStream')
    const queue = new AsyncQueue<string>()

    const consume = (async () => {
      const items: string[] = []
      for await (const item of queue) {
        items.push(item)
      }
      return items
    })()

    queue.push('hello')
    queue.push('world')
    queue.close()

    const items = await consume
    expect(items).toEqual(['hello', 'world'])
  })

  it('test_async_queue_close_wakes_waiting_consumer: close with no items ends iteration', async () => {
    const { AsyncQueue } = await import('./useWsStream')
    const queue = new AsyncQueue<number>()

    const consume = (async () => {
      const items: number[] = []
      for await (const item of queue) {
        items.push(item)
      }
      return items
    })()

    queue.close()
    const items = await consume
    expect(items).toEqual([])
  })

  it('test_async_queue_push_after_close_ignored: push after close does nothing', async () => {
    const { AsyncQueue } = await import('./useWsStream')
    const queue = new AsyncQueue<number>()
    queue.close()
    queue.push(42)

    const items: number[] = []
    for await (const item of queue) {
      items.push(item)
    }
    expect(items).toEqual([])
  })
})

describe('useWsStream channel routing (run/analysis/review)', () => {
  let mockWs: {
    onopen: (() => void) | null
    onmessage: ((e: { data: string }) => void) | null
    onclose: (() => void) | null
    onerror: (() => void) | null
    send: ReturnType<typeof vi.fn>
    close: ReturnType<typeof vi.fn>
    readyState: number
  }

  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()
    mockWs = {
      onopen: null, onmessage: null, onclose: null, onerror: null,
      send: vi.fn(), close: vi.fn(), readyState: 1,
    }
    const WSConstructor = Object.assign(vi.fn(() => mockWs), { OPEN: 1, CLOSED: 3 })
    vi.stubGlobal('WebSocket', WSConstructor)
    vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:3011' })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  async function setupHook() {
    const mod = await import('./useWsStream')
    const wrapper = createWrapper()
    const result = renderHook(() => mod.useWsStream(true), { wrapper })
    mockWs.onopen!()
    return { mod, result }
  }

  it('test_run_channel_routing: job_progress routes to run:{id} channel', async () => {
    const { mod, result } = await setupHook()
    const handler = vi.fn()

    const unsub = mod.subscribe('run:abc123', handler)
    mockWs.onmessage!({ data: JSON.stringify({ type: 'job_progress', seq: 1, data: { day: 1 } }) })
    expect(handler).toHaveBeenCalledWith({ day: 1 }, 'job_progress')

    handler.mockClear()
    mockWs.onmessage!({ data: JSON.stringify({ type: 'quotes_updated', seq: 2, data: {} }) })
    expect(handler).not.toHaveBeenCalled()

    unsub()
    result.unmount()
  })

  it('test_analysis_channel_routing: analysis_delta routes to analysis:{symbol} channel', async () => {
    const { mod, result } = await setupHook()
    const handler = vi.fn()

    const unsub = mod.subscribe('analysis:600519.SH', handler)
    mockWs.onmessage!({ data: JSON.stringify({ type: 'analysis_delta', seq: 1, data: { content: 'chunk' } }) })
    expect(handler).toHaveBeenCalledWith({ content: 'chunk' }, 'analysis_delta')

    handler.mockClear()
    mockWs.onmessage!({ data: JSON.stringify({ type: 'job_progress', seq: 2, data: {} }) })
    expect(handler).not.toHaveBeenCalled()

    unsub()
    result.unmount()
  })

  it('test_review_channel_routing: review_delta routes to review channel', async () => {
    const { mod, result } = await setupHook()
    const handler = vi.fn()

    const unsub = mod.subscribe('review', handler)
    mockWs.onmessage!({ data: JSON.stringify({ type: 'review_delta', seq: 1, data: { content: 'text' } }) })
    expect(handler).toHaveBeenCalledWith({ content: 'text' }, 'review_delta')

    unsub()
    result.unmount()
  })

  it('test_static_channel_routing: strategy_alert routes to alerts channel', async () => {
    const { mod, result } = await setupHook()
    const handler = vi.fn()

    const unsub = mod.subscribe('alerts', handler)
    mockWs.onmessage!({ data: JSON.stringify({ type: 'strategy_alert', seq: 1, data: { alert: 'test' } }) })
    expect(handler).toHaveBeenCalledWith({ alert: 'test' }, 'strategy_alert')

    unsub()
    result.unmount()
  })

  it('test_request_sends_message: request sends {type:"request", channel, params}', async () => {
    const { mod, result } = await setupHook()
    mockWs.send.mockClear()

    mod.request('analysis:600519.SH', { symbol: '600519.SH', focus: '盈利' })
    expect(mockWs.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'request', channel: 'analysis:600519.SH', params: { symbol: '600519.SH', focus: '盈利' } }),
    )

    result.unmount()
  })
})
