import { useSyncExternalStore } from 'react'
import * as wsStream from './useWsStream'

/**
 * 参数优化任务管理 (WS 频道模式 + 重连)。镜像 backtestTask, 结果为排名 dict。
 */

export interface OptimizeProgress {
  type: string
  done: number
  total: number
  best_score: number | null
  shared_matrix_bytes?: number
  elapsed_ms?: number
}

export interface OptimizeResultRow {
  params: Record<string, any>
  objective_raw: number | null
  stats?: Record<string, any>
  rank: number
  error?: string
}

export interface OptimizeResult {
  objective: string
  direction: string
  n_combinations: number
  n_completed: number
  best_params: Record<string, any> | null
  best_score: number | null
  results: OptimizeResultRow[]
  requested_max_workers: number
  effective_workers: number
  shared_market_data: boolean
  shared_market_data_bytes: number
  prepare_ms: number
  best_backtest?: Record<string, any> | null
  matrix_compute_cache?: Record<string, any>
  timing_ms?: Record<string, number>
  performance?: Record<string, any>
  worker?: Record<string, any>
  elapsed_ms: number
}

export interface OptimizerTask {
  id: number
  isPending: boolean
  result: OptimizeResult | null
  progress: OptimizeProgress | null
  error: string | null
}

export interface StartOptimizeParams {
  strategy_id: string
  param_grid: Record<string, any>
  objective: string
  direction?: string
  max_workers?: number
  matrix_cache_max_mb?: number
  params?: Record<string, any> | null       // 未扫描参数固定为用户当前值
  overrides?: Record<string, any> | null     // 策略当前的 basic_filter/信号/风控覆盖
  symbols?: string[] | null
  start?: string | null
  end?: string | null
  matching?: string
  fees_pct?: number
  commission_pct?: number
  stamp_tax_pct?: number
  slippage_bps?: number
  max_positions?: number
  max_exposure_pct?: number
  initial_capital?: number
  position_sizing?: string
  mode?: 'position' | 'full'
  holding_days?: number
}

let current: OptimizerTask | null = null
const listeners = new Set<() => void>()
let taskSeq = 0
let unsubFn: (() => void) | null = null
let currentJobKey: string | null = null
let cancelRequested = false      // stop 在拿到 job_key 前被点 -> 收到 job 事件立即补发 cancel

const RECONNECT_KEY = 'optimizer_reconnect'
const JOB_KEY_KEY = 'optimizer_job_key'

function emit() {
  listeners.forEach(fn => fn())
}

function subscribe(fn: () => void) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

/** 构建 POST /optimize/start 的 JSON 参数 */
function buildOptStartParams(params: StartOptimizeParams): Record<string, unknown> {
  return {
    strategy_id: params.strategy_id,
    param_grid: JSON.stringify(params.param_grid),
    objective: params.objective,
    direction: params.direction,
    max_workers: params.max_workers,
    matrix_cache_max_mb: params.matrix_cache_max_mb,
    params: params.params ? JSON.stringify(params.params) : undefined,
    overrides: params.overrides ? JSON.stringify(params.overrides) : undefined,
    symbols: params.symbols?.join(','),
    start: params.start ?? undefined,
    end: params.end ?? undefined,
    matching: params.matching,
    fees_pct: params.fees_pct,
    commission_pct: params.commission_pct,
    stamp_tax_pct: params.stamp_tax_pct,
    slippage_bps: params.slippage_bps,
    max_positions: params.max_positions,
    max_exposure_pct: params.max_exposure_pct,
    initial_capital: params.initial_capital,
    position_sizing: params.position_sizing,
    mode: params.mode,
    holding_days: params.holding_days,
  }
}

function buildQuery(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '') sp.set(k, String(v))
  }
  return sp.toString()
}

/** 退订当前 WS 频道 */
function unsubscribeChannel(): void {
  if (unsubFn) {
    unsubFn()
    unsubFn = null
  }
}

/** 连接 WS 频道 */
function connectChannel(jobKey: string): void {
  const id = current?.id ?? ++taskSeq
  unsubscribeChannel()

  const channel = `run:${jobKey}`
  unsubFn = wsStream.subscribe(channel, (data, type) => {
    if (current?.id !== id) return

    if (type === 'job') {
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
      try {
        const prog = data as unknown as OptimizeProgress
        current = { ...current, progress: prog }
        emit()
      } catch { /* ignore */ }
      return
    }

    if (type === 'job_done' || type === 'done') {
      try {
        const result = data as unknown as OptimizeResult
        current = { ...current, isPending: false, result, error: null }
        emit()
      } catch {
        current = { ...current, isPending: false, error: '结果解析失败' }
        emit()
      }
      unsubscribeChannel()
      currentJobKey = null
      localStorage.removeItem(RECONNECT_KEY)
      localStorage.removeItem(JOB_KEY_KEY)
      return
    }

    if (type === 'job_error' || type === 'error') {
      const msg = (data as Record<string, unknown>)?.message ?? '优化出错'
      current = { ...current, isPending: false, error: typeof msg === 'string' ? msg : '优化出错' }
      emit()
      unsubscribeChannel()
      currentJobKey = null
      localStorage.removeItem(RECONNECT_KEY)
      localStorage.removeItem(JOB_KEY_KEY)
    }
  })
}

/** 调后端 cancel (按回吐的 job_key)。cancel 仍走 POST, 不通过 WS。 */
function postCancel(jobKey: string): void {
  void fetch('/api/backtest/optimize/cancel', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_key: jobKey }),
  }).catch(() => {})
}

/** POST /optimize/start 获取 job_key, 然后订阅 WS 频道 (Phase 55 D-03: SSE 端点已删除) */
async function startOptimizePost(params: Record<string, unknown>, qs: string): Promise<void> {
  try {
    const res = await fetch('/api/backtest/optimize/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    })
    if (!res.ok) {
      const taskId = current?.id
      if (taskId != null && current?.isPending) {
        current = { ...current, isPending: false, error: `优化启动失败: ${res.status}` }
        emit()
      }
      return
    }
    const data = await res.json()
    const key = data?.key
    if (typeof key === 'string' && key) {
      currentJobKey = key
      localStorage.setItem(JOB_KEY_KEY, key)
      if (data?.error) {
        const taskId = current?.id
        if (taskId != null && current?.isPending) {
          current = { ...current, isPending: false, error: data.error }
          emit()
        }
      } else {
        connectChannel(key)
      }
    } else {
      const taskId = current?.id
      if (taskId != null && current?.isPending) {
        current = { ...current, isPending: false, error: '未收到任务 ID' }
        emit()
      }
    }
  } catch {
    const taskId = current?.id
    if (taskId != null && current?.isPending) {
      current = { ...current, isPending: false, error: '优化启动失败' }
      emit()
    }
  }
}

export function startOptimize(params: StartOptimizeParams): void {
  unsubscribeChannel()

  cancelRequested = false
  currentJobKey = null
  const id = ++taskSeq
  current = { id, isPending: true, result: null, progress: null, error: null }
  emit()

  const qs = buildQuery({
    strategy_id: params.strategy_id,
    param_grid: JSON.stringify(params.param_grid),
    objective: params.objective,
    direction: params.direction,
    max_workers: params.max_workers,
    matrix_cache_max_mb: params.matrix_cache_max_mb,
    params: params.params ? JSON.stringify(params.params) : undefined,
    overrides: params.overrides ? JSON.stringify(params.overrides) : undefined,
    symbols: params.symbols?.join(','),
    start: params.start ?? undefined,
    end: params.end ?? undefined,
    matching: params.matching,
    fees_pct: params.fees_pct,
    commission_pct: params.commission_pct,
    stamp_tax_pct: params.stamp_tax_pct,
    slippage_bps: params.slippage_bps,
    max_positions: params.max_positions,
    max_exposure_pct: params.max_exposure_pct,
    initial_capital: params.initial_capital,
    position_sizing: params.position_sizing,
    mode: params.mode,
    holding_days: params.holding_days,
  })

  localStorage.setItem(RECONNECT_KEY, qs)
  void startOptimizePost(buildOptStartParams(params), qs)
}

export function stopOptimize(): void {
  // 竞态: 若刚点开始还没收到 job 事件, job_key 尚未到手。标记 cancelRequested —— 
  // 有 key 则立即取消并关闭; 无 key 则保持连接等 job 事件到达时补发 cancel 再关
  cancelRequested = true
  const jobKey = currentJobKey ?? localStorage.getItem(JOB_KEY_KEY)
  if (jobKey) {
    postCancel(jobKey)
    unsubscribeChannel()
    currentJobKey = null
    localStorage.removeItem(RECONNECT_KEY)
    localStorage.removeItem(JOB_KEY_KEY)
  } else {
    // job_key 始终没到手: 直接退订, 清 localStorage
    unsubscribeChannel()
    localStorage.removeItem(RECONNECT_KEY)
    localStorage.removeItem(JOB_KEY_KEY)
  }
  if (current?.isPending) {
    current = { ...current, isPending: false, error: '已取消' }
    emit()
  }
}

export function clearOptimize(): void {
  unsubscribeChannel()
  currentJobKey = null
  localStorage.removeItem(RECONNECT_KEY)
  localStorage.removeItem(JOB_KEY_KEY)
  current = null
  emit()
}

export function tryReconnectOptimize(): boolean {
  const jobKey = localStorage.getItem(JOB_KEY_KEY)
  if (!jobKey) {
    const qs = localStorage.getItem(RECONNECT_KEY)
    if (!qs) return false
    // Phase 55 D-03: SSE 端点已删除, 无 job_key 时无法用 qs 重启动
    return false
  }
  const id = ++taskSeq
  current = { id, isPending: true, result: null, progress: null, error: null }
  emit()
  connectChannel(jobKey)
  return true
}

export function useOptimizerTask(): OptimizerTask | null {
  return useSyncExternalStore(subscribe, () => current, () => null)
}
