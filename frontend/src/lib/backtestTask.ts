import { useSyncExternalStore } from 'react'
import type { StrategyBacktestResult } from './api'
import * as wsStream from './useWsStream'

/**
 * 全局回测任务管理 (WS 频道模式 + 任务缓存 + 重连支持)。
 *
 * 特性:
 * - 实时进度: useWsStream.subscribe(`run:${job_key}`) 监听后端 WS 频道, 推送 day/total/equity
 * - 可取消: POST /strategy/cancel/{job_key}, 后端 cancel_event (cancel 仍走 POST, 不通过 WS)
 * - 切页/刷新保持: 后端按参数 hash 缓存任务, 重连不重启
 *   - 切页: 模块级 store 保持, WS 频道随组件卸载退订, 回来后重订阅
 *   - 刷新: localStorage 存 job_key, 刷新后通过 useWsStream 重订阅 run:{job_key}
 */

export interface BacktestProgress {
  day: number
  total: number
  date: string
  equity: number
}

export interface BacktestTask {
  id: number
  isPending: boolean
  result: StrategyBacktestResult | null
  progress: BacktestProgress | null
  error: string | null
  /** 仅由匹配的服务端 research/done SSE 事件提供的策略研究执行句柄。 */
  researchExecutionHandle: string | null
  /** 连接中断、正在有界重连中 (UI 显示"连接中断，重试中") */
  reconnecting: boolean
}

let current: BacktestTask | null = null
const listeners = new Set<() => void>()
let taskSeq = 0
let unsubFn: (() => void) | null = null
let currentJobKey: string | null = null
let cancelRequested = false

const RECONNECT_KEY = 'backtest_reconnect'
const JOB_KEY_KEY = 'backtest_job_key'

function emit() {
  listeners.forEach(fn => fn())
}

function subscribe(fn: () => void) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

function getSnapshot() {
  return current
}

function getServerSnapshot() {
  return null
}

function cancelServerTask(qs: string): void {
  void fetch('/api/backtest/strategy/cancel', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ qs }),
  }).catch(() => {})
}

/** 查询字符串构建 */
function buildQuery(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '') sp.set(k, String(v))
  }
  return sp.toString()
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value)
}

function isNullableFiniteNumber(value: unknown): boolean {
  return value === null || isFiniteNumber(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string')
}

function isStrategyInfo(value: unknown): boolean {
  if (!isRecord(value)) return false
  return typeof value.id === 'string' && value.id.trim().length > 0
    && typeof value.name === 'string' && value.name.trim().length > 0
    && typeof value.description === 'string'
    && isStringArray(value.entry_signals)
    && isStringArray(value.exit_signals)
    && isNullableFiniteNumber(value.stop_loss)
    && isNullableFiniteNumber(value.take_profit)
    && isNullableFiniteNumber(value.trailing_stop)
    && isNullableFiniteNumber(value.trailing_take_profit_activate)
    && isNullableFiniteNumber(value.trailing_take_profit_drawdown)
    && isNullableFiniteNumber(value.score_min)
    && isNullableFiniteNumber(value.score_max)
    && isNullableFiniteNumber(value.max_hold_days)
    && typeof value.source === 'string' && value.source.trim().length > 0
}

function isEquityPoint(value: unknown): boolean {
  return isRecord(value) && typeof value.date === 'string' && isFiniteNumber(value.value)
    && (value.cash === undefined || isFiniteNumber(value.cash))
    && (value.positions === undefined || isFiniteNumber(value.positions))
    && (value.exposure === undefined || isFiniteNumber(value.exposure))
}

function isDrawdownPoint(value: unknown): boolean {
  return isRecord(value) && typeof value.date === 'string' && isFiniteNumber(value.value)
}

function isBenchmarkPoint(value: unknown): boolean {
  return isRecord(value) && typeof value.date === 'string' && isFiniteNumber(value.value)
    && (value.close === undefined || isFiniteNumber(value.close))
    && (value.name === undefined || typeof value.name === 'string')
    && (value.symbol === undefined || typeof value.symbol === 'string')
}

function isStrategyTrade(value: unknown): boolean {
  return isRecord(value) && typeof value.symbol === 'string' && typeof value.entry_date === 'string'
    && typeof value.exit_date === 'string' && isFiniteNumber(value.entry_price)
    && isFiniteNumber(value.exit_price) && isFiniteNumber(value.pnl_pct)
    && isFiniteNumber(value.duration) && typeof value.exit_reason === 'string'
    && (value.name === undefined || typeof value.name === 'string')
    && (value.shares === undefined || isFiniteNumber(value.shares))
    && (value.lots === undefined || isFiniteNumber(value.lots))
    && (value.position_pct === undefined || isFiniteNumber(value.position_pct))
    && (value.entry_value === undefined || isFiniteNumber(value.entry_value))
    && (value.exit_value === undefined || isFiniteNumber(value.exit_value))
    && (value.pnl_amount === undefined || isFiniteNumber(value.pnl_amount))
    && (value.entry_score === undefined || isNullableFiniteNumber(value.entry_score))
    && (value.entry_signal_date === undefined || value.entry_signal_date === null || typeof value.entry_signal_date === 'string')
    && (value.exit_signal_date === undefined || value.exit_signal_date === null || typeof value.exit_signal_date === 'string')
    && (value.blocked_exit_days === undefined || isFiniteNumber(value.blocked_exit_days))
}

function isPerSymbolStats(value: unknown): boolean {
  return isRecord(value) && typeof value.symbol === 'string' && isFiniteNumber(value.n_trades)
    && isFiniteNumber(value.total_return) && isFiniteNumber(value.win_rate)
    && isFiniteNumber(value.best) && isFiniteNumber(value.worst)
}

function isStrategyBacktestResult(value: unknown): value is StrategyBacktestResult {
  if (!isRecord(value)) return false
  return (typeof value.error === 'string' || value.error === null)
    && typeof value.run_id === 'string' && value.run_id.trim().length > 0
    && isRecord(value.config)
    && isRecord(value.stats)
    && Array.isArray(value.equity_curve) && value.equity_curve.every(isEquityPoint)
    && Array.isArray(value.drawdown_curve) && value.drawdown_curve.every(isDrawdownPoint)
    && (value.benchmark_curve === undefined || (Array.isArray(value.benchmark_curve) && value.benchmark_curve.every(isBenchmarkPoint)))
    && Array.isArray(value.trades) && value.trades.every(isStrategyTrade)
    && Array.isArray(value.per_symbol_stats) && value.per_symbol_stats.every(isPerSymbolStats)
    && isStrategyInfo(value.strategy_info)
    && isFiniteNumber(value.elapsed_ms)
}

/** 退订当前 WS 频道订阅 */
function unsubscribeChannel(): void {
  if (unsubFn) {
    unsubFn()
    unsubFn = null
  }
}

/** 连接 WS 频道 (新建或重连都用这个) */
function connectChannel(jobKey: string): void {
  const id = current?.id ?? ++taskSeq

  // 退订旧频道
  unsubscribeChannel()

  const channel = `run:${jobKey}`
  unsubFn = wsStream.subscribe(channel, (data, type) => {
    if (current?.id !== id || !current.isPending) return

    if (type === 'job') {
      // 后端回吐 job_key — 存下供 cancel 引用
      const key = data.key
      if (typeof key === 'string' && key) {
        currentJobKey = key
        localStorage.setItem(JOB_KEY_KEY, key)
        // 竞态修复: stop 在拿到 key 前被点过 -> 补发 cancel
        if (cancelRequested) {
          postCancel(key)
          unsubscribeChannel()
          currentJobKey = null
          localStorage.removeItem(RECONNECT_KEY)
          localStorage.removeItem(JOB_KEY_KEY)
        }
      }
      return
    }

    if (type === 'job_progress' || type === 'progress') {
      const d = data as unknown
      if (!isRecord(d) || typeof d.day !== 'number' || !Number.isFinite(d.day)
        || typeof d.total !== 'number' || !Number.isFinite(d.total) || (d.total as number) <= 0
        || typeof d.date !== 'string' || typeof d.equity !== 'number' || !Number.isFinite(d.equity)) return
      const prog = d as unknown as BacktestProgress
      current = { ...current, progress: prog, reconnecting: false }
      emit()
      return
    }

    if (type === 'research') {
      const handle = (data as Record<string, unknown>)?.execution_handle
      if (typeof handle !== 'string' || !handle.trim()) return
      current = { ...current, researchExecutionHandle: handle }
      emit()
      return
    }

    if (type === 'job_done' || type === 'done') {
      const payload = data as unknown
      if (!isStrategyBacktestResult(payload)) {
        current = { ...current, isPending: false, result: null, error: '结果解析失败', reconnecting: false, researchExecutionHandle: null }
        emit()
      } else {
        const terminalError = typeof payload.error === 'string' && payload.error.trim()
        current = {
          ...current,
          isPending: false,
          result: payload,
          error: terminalError || null,
          reconnecting: false,
          researchExecutionHandle: terminalError ? null : current.researchExecutionHandle,
        }
        emit()
      }
      unsubscribeChannel()
      currentJobKey = null
      localStorage.removeItem(RECONNECT_KEY)
      localStorage.removeItem(JOB_KEY_KEY)
      return
    }

    if (type === 'job_error' || type === 'error') {
      const msg = (data as Record<string, unknown>)?.message ?? '回测出错'
      current = { ...current, isPending: false, error: typeof msg === 'string' ? msg : '回测出错', reconnecting: false, researchExecutionHandle: null }
      emit()
      unsubscribeChannel()
      currentJobKey = null
      localStorage.removeItem(RECONNECT_KEY)
      localStorage.removeItem(JOB_KEY_KEY)
      return
    }
  })
}

/** 调后端 cancel (按 job_key 或 qs)。cancel 仍走 POST, 不通过 WS。 */
function postCancel(jobKey: string): void {
  void fetch('/api/backtest/strategy/cancel', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_key: jobKey }),
  }).catch(() => {})
}

/** 启动一次回测任务 */
export function startBacktest(params: {
  strategy_id: string
  symbols?: string[] | null
  start?: string | null
  end?: string | null
  matching?: string
  entry_fill?: string
  exit_fill?: string
  fees_pct?: number
  commission_pct?: number
  stamp_tax_pct?: number
  slippage_bps?: number
  max_positions?: number
  max_exposure_pct?: number
  initial_capital?: number
  position_sizing?: string
  params?: Record<string, any> | null
  overrides?: Record<string, any> | null
  mode?: 'position' | 'full'
  holding_days?: number
  asset_type?: 'stock' | 'etf'
  minute_fill?: boolean
  regime_filter?: { states?: string[]; min_score?: number } | null
}): void {
  const previousQs = localStorage.getItem(RECONNECT_KEY)

  // 取消之前的任务状态
  unsubscribeChannel()
  // Closing WS subscription alone leaves the daemon job running on the server.
  // Cancel the previous job without awaiting it so a new run cannot race it.
  if (previousQs) cancelServerTask(previousQs)

  cancelRequested = false
  currentJobKey = null

  const id = ++taskSeq
  current = { id, isPending: true, result: null, progress: null, error: null, reconnecting: false, researchExecutionHandle: null }
  emit()

  const qs = buildQuery({
    strategy_id: params.strategy_id,
    symbols: params.symbols?.join(','),
    start: params.start ?? undefined,
    end: params.end ?? undefined,
    matching: params.matching,
    entry_fill: params.entry_fill,
    exit_fill: params.exit_fill,
    fees_pct: params.fees_pct,
    commission_pct: params.commission_pct,
    stamp_tax_pct: params.stamp_tax_pct,
    slippage_bps: params.slippage_bps,
    max_positions: params.max_positions,
    max_exposure_pct: params.max_exposure_pct,
    initial_capital: params.initial_capital,
    position_sizing: params.position_sizing,
    params: params.params ? JSON.stringify(params.params) : undefined,
    overrides: params.overrides ? JSON.stringify(params.overrides) : undefined,
    mode: params.mode,
    holding_days: params.holding_days,
    asset_type: params.asset_type,
    minute_fill: params.minute_fill,
    regime_filter: params.regime_filter ? JSON.stringify(params.regime_filter) : undefined,
  })

  // 存 reconnect 信息 (刷新后用) — 存 qs, 连接后拿到 job_key 再存 job_key
  localStorage.setItem(RECONNECT_KEY, qs)

  // 用 fetch GET stream 短暂获取 job_key (后端 SSE 端点首个 job 事件回吐 key),
  // 然后关闭 fetch, 切到 WS run:{job_key} 频道订阅。
  // 这是 fetch + ReadableStream, 不创建 EventSource。
  void startBacktestStream(qs)
}

/** GET stream 获取 job_key, 然后订阅 WS 频道 */
async function startBacktestStream(qs: string): Promise<void> {
  try {
    const res = await fetch(`/api/backtest/strategy/stream?${qs}`, {
      headers: { Accept: 'text/event-stream' },
    })
    if (!res.ok || !res.body) {
      // 后端不可用, 走错误态
      const taskId = current?.id
      if (taskId != null && current?.isPending) {
        current = { ...current, isPending: false, error: `回测启动失败: ${res.status}`, reconnecting: false, researchExecutionHandle: null }
        emit()
      }
      return
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let gotJobKey = false
    while (!gotJobKey) {
      const chunk = await reader.read()
      if (chunk.done) break
      buffer += decoder.decode(chunk.value, { stream: true })
      // 解析 SSE 事件: "event: job\ndata: {\"key\":\"...\"}\n\n"
      let boundary = buffer.indexOf('\n\n')
      while (boundary >= 0) {
        const frame = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        // 提取 event 和 data
        let eventType = 'message'
        const dataLines: string[] = []
        for (const line of frame.split('\n')) {
          if (line.startsWith('event:')) eventType = line.slice(6).trim()
          else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
        }
        if (eventType === 'job') {
          try {
            const key = JSON.parse(dataLines.join('\n'))?.key
            if (typeof key === 'string' && key) {
              gotJobKey = true
              currentJobKey = key
              localStorage.setItem(JOB_KEY_KEY, key)
              localStorage.setItem(RECONNECT_KEY, qs)
              // 关闭 fetch, 切到 WS 频道
              reader.cancel()
              connectChannel(key)
              break
            }
          } catch { /* ignore */ }
        }
        boundary = buffer.indexOf('\n\n')
      }
    }
    if (!gotJobKey) {
      reader.cancel()
      const taskId = current?.id
      if (taskId != null && current?.isPending) {
        current = { ...current, isPending: false, error: '未收到任务 ID', reconnecting: false, researchExecutionHandle: null }
        emit()
      }
    }
  } catch {
    const taskId = current?.id
    if (taskId != null && current?.isPending) {
      current = { ...current, isPending: false, error: '回测启动失败', reconnecting: false, researchExecutionHandle: null }
      emit()
    }
  }
}

/** 停止当前回测任务 (调后端 cancel, 后端 cancel_event → 停止计算) */
export async function stopBacktest(): Promise<void> {
  const jobKey = currentJobKey ?? localStorage.getItem(JOB_KEY_KEY)
  const qs = localStorage.getItem(RECONNECT_KEY)
  const taskId = current?.id

  cancelRequested = true

  // Mark the local task before awaiting the network request. This prevents a
  // quick rerun from being cancelled by a late response from the old request.
  if (current?.isPending && current.id === taskId) {
    current = { ...current, isPending: false, error: '已取消', reconnecting: false, researchExecutionHandle: null }
    emit()
  }

  if (jobKey) {
    postCancel(jobKey)
  } else if (qs) {
    // job_key 未到手 (job 事件未达): 用 qs 调 cancel
    await fetch('/api/backtest/strategy/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ qs }),
    }).catch(() => {})
  }

  unsubscribeChannel()
  currentJobKey = null
  localStorage.removeItem(RECONNECT_KEY)
  localStorage.removeItem(JOB_KEY_KEY)
}

/** 清除任务状态 (隐藏提示) */
export function clearBacktest(): void {
  unsubscribeChannel()
  currentJobKey = null
  localStorage.removeItem(RECONNECT_KEY)
  localStorage.removeItem(JOB_KEY_KEY)
  current = null
  emit()
}

/** 恢复: 从 localStorage 读取 job_key, 重新订阅 WS 频道 (刷新后调用) */
export function tryReconnect(): boolean {
  const jobKey = localStorage.getItem(JOB_KEY_KEY)
  if (!jobKey) {
    // 没有 job_key, 尝试用 qs 重新启动 (旧路径)
    const qs = localStorage.getItem(RECONNECT_KEY)
    if (!qs) return false
    const id = ++taskSeq
    current = { id, isPending: true, result: null, progress: null, error: null, reconnecting: false, researchExecutionHandle: null }
    emit()
    void startBacktestStream(qs)
    return true
  }
  // 有 job_key, 直接重订阅 WS 频道
  const id = ++taskSeq
  current = { id, isPending: true, result: null, progress: null, error: null, reconnecting: false, researchExecutionHandle: null }
  emit()
  connectChannel(jobKey)
  return true
}

/** React hook: 读取当前全局回测任务状态 */
export function useBacktestTask(): BacktestTask | null {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}
