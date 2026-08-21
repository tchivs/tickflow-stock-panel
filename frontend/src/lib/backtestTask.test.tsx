// Dynamic imports are required because vi.resetModules() invalidates static imports between tests.
// Each test re-imports the module fresh to get isolated module-level state.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import type { ReactNode } from 'react'

// backtestTask uses module-level state, so tests must reset between runs.
// We mock useWsStream.subscribe to capture the handler and simulate WS messages.

async function createWrapper() {
  const { QueryClient, QueryClientProvider } = await import('@tanstack/react-query')
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  }
}

// Mock useWsStream module — capture subscribe handler
let mockUnsub: ReturnType<typeof vi.fn>
let capturedHandler: ((data: Record<string, unknown>, type: string) => void) | null = null
let subscribedChannel: string | null = null

vi.mock('./useWsStream', () => ({
  subscribe: vi.fn((channel: string, handler: (data: Record<string, unknown>, type: string) => void) => {
    subscribedChannel = channel
    capturedHandler = handler
    mockUnsub = vi.fn()
    return mockUnsub
  }),
  request: vi.fn(),
  useWsStream: vi.fn(),
  useWsStreamStatus: vi.fn(() => 'connected' as const),
  setFocusSymbol: vi.fn(),
  clearFocusSymbol: vi.fn(),
  getFocusSymbol: vi.fn(() => null),
  AsyncQueue: vi.fn(),
}))

// Mock global fetch for cancel/start
const mockFetch = vi.fn()

describe('backtestTask', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.useFakeTimers()
    capturedHandler = null
    subscribedChannel = null
    mockUnsub = vi.fn()
    vi.stubGlobal('fetch', mockFetch)
    vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:3011' })
    // Mock localStorage — jsdom's localStorage may not be available after stubGlobal
    const store: Record<string, string> = {}
    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => store[key] ?? null),
      setItem: vi.fn((key: string, value: string) => { store[key] = value }),
      removeItem: vi.fn((key: string) => { delete store[key] }),
      clear: vi.fn(() => { for (const k of Object.keys(store)) delete store[k] }),
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('test_subscribe_run_channel: startBacktest 订阅 run: 频道, 不创建 new EventSource', async () => {
    const { startBacktest, useBacktestTask, clearBacktest } = await import('./backtestTask')
    const { result } = renderHook(() => useBacktestTask(), { wrapper: await createWrapper() })
    expect(result.current).toBeNull()

    // Mock fetch to return a readable stream with SSE job event
    const encoder = new TextEncoder()
    const jobEvent = 'event: job\ndata: {"key":"test_job_key_123"}\n\n'
    mockFetch.mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: vi.fn()
            .mockResolvedValueOnce({ done: false, value: encoder.encode(jobEvent) })
            .mockResolvedValue({ done: true }),
          cancel: vi.fn(),
        }),
      },
    })

    act(() => {
      startBacktest({ strategy_id: 'test_strategy' })
    })

    // Wait for async startBacktestStream to resolve
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    // Should have subscribed to run:{job_key} channel
    expect(subscribedChannel).toBe('run:test_job_key_123')
    // No EventSource should have been created
    expect(capturedHandler).not.toBeNull()

    clearBacktest()
  })

  it('test_job_progress_handler: 收到 job_progress 时更新 current.progress', async () => {
    const { startBacktest, useBacktestTask, clearBacktest } = await import('./backtestTask')
    const { result } = renderHook(() => useBacktestTask(), { wrapper: await createWrapper() })

    const encoder = new TextEncoder()
    const jobEvent = 'event: job\ndata: {"key":"key_456"}\n\n'
    mockFetch.mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: vi.fn()
            .mockResolvedValueOnce({ done: false, value: encoder.encode(jobEvent) })
            .mockResolvedValue({ done: true }),
          cancel: vi.fn(),
        }),
      },
    })

    act(() => {
      startBacktest({ strategy_id: 'test_strategy' })
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    // Simulate WS job_progress message
    act(() => {
      capturedHandler!({ day: 1, total: 10, date: '2024-01-01', equity: 100000 }, 'job_progress')
    })

    expect(result.current?.isPending).toBe(true)
    expect(result.current?.progress).toEqual({ day: 1, total: 10, date: '2024-01-01', equity: 100000 })
    expect(result.current?.reconnecting).toBe(false)

    clearBacktest()
  })

  it('test_job_done_handler: 收到 job_done 时 isPending=false, result 设置, 退订', async () => {
    const { startBacktest, useBacktestTask, clearBacktest } = await import('./backtestTask')
    const { result } = renderHook(() => useBacktestTask(), { wrapper: await createWrapper() })

    const encoder = new TextEncoder()
    const jobEvent = 'event: job\ndata: {"key":"key_789"}\n\n'
    mockFetch.mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: vi.fn()
            .mockResolvedValueOnce({ done: false, value: encoder.encode(jobEvent) })
            .mockResolvedValue({ done: true }),
          cancel: vi.fn(),
        }),
      },
    })

    act(() => {
      startBacktest({ strategy_id: 'test_strategy' })
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    // Simulate WS job_done message with a minimal valid result
    const fakeResult = {
      error: null,
      run_id: 'test_run',
      config: {},
      stats: {},
      equity_curve: [],
      drawdown_curve: [],
      trades: [],
      per_symbol_stats: [],
      strategy_info: {
        id: 'test', name: 'test', description: '',
        entry_signals: [], exit_signals: [],
        stop_loss: null, take_profit: null,
        trailing_stop: null, trailing_take_profit_activate: null,
        trailing_take_profit_drawdown: null,
        score_min: null, score_max: null,
        max_hold_days: null,
        source: 'ai',
      },
      elapsed_ms: 100,
    }
    act(() => {
      capturedHandler!(fakeResult, 'job_done')
    })

    expect(result.current?.isPending).toBe(false)
    expect(result.current?.result).toEqual(fakeResult)
    expect(mockUnsub).toHaveBeenCalled()

    clearBacktest()
  })

  it('test_job_error_handler: 收到 job_error 时 error 设置, 退订', async () => {
    const { startBacktest, useBacktestTask, clearBacktest } = await import('./backtestTask')
    const { result } = renderHook(() => useBacktestTask(), { wrapper: await createWrapper() })

    const encoder = new TextEncoder()
    const jobEvent = 'event: job\ndata: {"key":"key_err"}\n\n'
    mockFetch.mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: vi.fn()
            .mockResolvedValueOnce({ done: false, value: encoder.encode(jobEvent) })
            .mockResolvedValue({ done: true }),
          cancel: vi.fn(),
        }),
      },
    })

    act(() => {
      startBacktest({ strategy_id: 'test_strategy' })
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    act(() => {
      capturedHandler!({ message: '回测出错: 数据不足' }, 'job_error')
    })

    expect(result.current?.isPending).toBe(false)
    expect(result.current?.error).toBe('回测出错: 数据不足')
    expect(mockUnsub).toHaveBeenCalled()

    clearBacktest()
  })

  it('test_cancel_still_post: cancel 调用 fetch POST /api/backtest/strategy/cancel', async () => {
    const { startBacktest, stopBacktest, clearBacktest } = await import('./backtestTask')

    const encoder = new TextEncoder()
    const jobEvent = 'event: job\ndata: {"key":"cancel_key"}\n\n'
    mockFetch.mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: vi.fn()
            .mockResolvedValueOnce({ done: false, value: encoder.encode(jobEvent) })
            .mockResolvedValue({ done: true }),
          cancel: vi.fn(),
        }),
      },
    })

    act(() => {
      startBacktest({ strategy_id: 'test_strategy' })
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    mockFetch.mockClear()
    await act(async () => {
      await stopBacktest()
    })

    // cancel should call fetch POST to /api/backtest/strategy/cancel
    const cancelCall = mockFetch.mock.calls.find(
      (call: unknown[]) => typeof call[0] === 'string' && (call[0] as string).includes('/api/backtest/strategy/cancel'),
    )
    expect(cancelCall).toBeDefined()
    expect(cancelCall?.[1]?.method).toBe('POST')

    clearBacktest()
  })

  it('test_reconnect_resubscribe: localStorage 存 job_key, 刷新后 tryReconnect 重订阅 run:{job_key}', async () => {
    const { startBacktest, tryReconnect, useBacktestTask, clearBacktest } = await import('./backtestTask')
    const { result } = renderHook(() => useBacktestTask(), { wrapper: await createWrapper() })

    const encoder = new TextEncoder()
    const jobEvent = 'event: job\ndata: {"key":"reconnect_key"}\n\n'
    mockFetch.mockResolvedValue({
      ok: true,
      body: {
        getReader: () => ({
          read: vi.fn()
            .mockResolvedValueOnce({ done: false, value: encoder.encode(jobEvent) })
            .mockResolvedValue({ done: true }),
          cancel: vi.fn(),
        }),
      },
    })

    act(() => {
      startBacktest({ strategy_id: 'test_strategy' })
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })

    // job_key should be in localStorage
    expect(localStorage.getItem('backtest_job_key')).toBe('reconnect_key')

    // Simulate page refresh: unsubscribe, reset module state
    capturedHandler = null
    subscribedChannel = null

    act(() => {
      const reconnected = tryReconnect()
      expect(reconnected).toBe(true)
    })

    // Should resubscribe to run:{reconnect_key}
    expect(subscribedChannel).toBe('run:reconnect_key')
    expect(result.current?.isPending).toBe(true)

    clearBacktest()
  })
})
