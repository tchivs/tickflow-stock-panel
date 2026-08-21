import { useSyncExternalStore } from 'react'
import { api, type MiningResult, type MiningRun, type MiningRunProgress, type MiningRunStatus } from './api'
import * as wsStream from './useWsStream'

export interface MiningTask {
  runId: string | null
  isPending: boolean
  cancelling: boolean
  reconnecting: boolean
  run: MiningRun | null
  progress: MiningRunProgress | null
  result: MiningResult | null
  previousResult: MiningResult | null
  error: string | null
}

const ACTIVE_RUN_KEY = 'mining_active_run_id'
const TERMINAL_STATES = new Set<MiningRunStatus>([
  'succeeded',
  'succeeded_with_budget_exhausted',
  'failed',
  'cancelled',
  'interrupted',
  'skipped_prerequisite',
])
const SUCCESS_STATES = new Set<MiningRunStatus>([
  'succeeded',
  'succeeded_with_budget_exhausted',
])
const STATUS_POLL_INTERVAL_MS = 2000

let current: MiningTask = {
  runId: null,
  isPending: false,
  cancelling: false,
  reconnecting: false,
  run: null,
  progress: null,
  result: null,
  previousResult: null,
  error: null,
}
let unsubFn: (() => void) | null = null
let connectionToken = 0
let statusPoll: {
  runId: string
  token: number
  timer: ReturnType<typeof setTimeout> | null
} | null = null
const listeners = new Set<() => void>()

function emit() {
  listeners.forEach(listener => listener())
}

function update(patch: Partial<MiningTask>) {
  current = { ...current, ...patch }
  emit()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function stopStatusPolling() {
  if (statusPoll?.timer) clearTimeout(statusPoll.timer)
  statusPoll = null
}

function closeEvents() {
  connectionToken += 1
  stopStatusPolling()
  if (unsubFn) {
    unsubFn()
    unsubFn = null
  }
}

// WS 事件 data 载荷与原 SSE event.data 结构相同 (后端广播时直接传 payload)
function wsPayload(data: Record<string, unknown>): Record<string, any> {
  if (data && typeof data === 'object') {
    return data.payload && typeof data.payload === 'object'
      ? { ...data, ...data.payload as Record<string, unknown> }
      : data
  }
  return {}
}

async function refreshTerminalRun(
  runId: string,
  fallbackStatus?: MiningRunStatus,
  knownRun?: MiningRun,
  token = connectionToken,
  fallbackError?: string,
) {
  try {
    const run = knownRun ?? await api.miningRun(runId)
    let result: MiningResult | null = null
    if (SUCCESS_STATES.has(run.status)) {
      result = await api.miningResult(runId)
      if (result.run_id !== runId) throw new Error('任务结果与运行 ID 不匹配')
    }
    if (current.runId !== runId || connectionToken !== token) return
    localStorage.removeItem(ACTIVE_RUN_KEY)
    update({
      run,
      progress: run.progress ?? current.progress,
      result,
      isPending: false,
      cancelling: false,
      reconnecting: false,
      error: run.error || fallbackError || null,
    })
  } catch (error) {
    if (current.runId !== runId || connectionToken !== token) return
    localStorage.removeItem(ACTIVE_RUN_KEY)
    const run = current.run && fallbackStatus
      ? { ...current.run, status: fallbackStatus, error: fallbackError || current.run.error }
      : current.run
    update({
      run,
      result: null,
      isPending: false,
      cancelling: false,
      reconnecting: false,
      error: fallbackStatus === 'cancelled'
        ? '任务已取消'
        : fallbackError || String((error as Error).message || error),
    })
  }
}

function startStatusPolling(runId: string, token: number, restart = false) {
  if (restart) stopStatusPolling()
  if (statusPoll?.runId === runId && statusPoll.token === token) return
  stopStatusPolling()

  const poll = { runId, token, timer: null as ReturnType<typeof setTimeout> | null }
  statusPoll = poll

  const pollStatus = async () => {
    if (
      statusPoll !== poll
      || current.runId !== runId
      || connectionToken !== token
      || !current.isPending
    ) return

    try {
      const run = await api.miningRun(runId)
      if (statusPoll !== poll || current.runId !== runId || connectionToken !== token) return
      update({
        run,
        progress: run.progress ?? current.progress,
        cancelling: current.cancelling || run.status === 'cancelling',
      })
      if (TERMINAL_STATES.has(run.status)) {
        closeEvents()
        const terminalToken = connectionToken
        await refreshTerminalRun(runId, run.status, run, terminalToken)
        return
      }
    } catch {
      // WS keeps reconnecting; polling is only a bounded status fallback.
    }

    if (
      statusPoll !== poll
      || current.runId !== runId
      || connectionToken !== token
      || !current.isPending
    ) return
    poll.timer = setTimeout(() => {
      poll.timer = null
      void pollStatus()
    }, STATUS_POLL_INTERVAL_MS)
  }

  void pollStatus()
}

/** 连接 WS 频道 — 订阅 run:{run_id} */
function connect(runId: string) {
  closeEvents()
  const token = connectionToken
  const channel = `run:${runId}`
  unsubFn = wsStream.subscribe(channel, (data, type) => {
    if (token !== connectionToken) return

    if (type === 'progress') {
      update({
        progress: wsPayload(data) as unknown as MiningRunProgress,
        reconnecting: false,
      })
      if (!current.cancelling) stopStatusPolling()
      return
    }

    // 终端事件: type 即状态名 (succeeded/failed/cancelled/interrupted/...)
    if (TERMINAL_STATES.has(type as MiningRunStatus)) {
      const payload = wsPayload(data)
      const status = (payload.status || type) as MiningRunStatus
      closeEvents()
      const terminalToken = connectionToken
      void refreshTerminalRun(
        runId,
        status,
        undefined,
        terminalToken,
        typeof payload.message === 'string' ? payload.message : undefined,
      )
    }
  })

  // 降级: WS 断连时启动轮询 (Phase 55 迁移后保留的兜底模式)
  // useWsStream 内部退避重连; 当 status === 'disconnected' (重连耗尽) 时启动轮询
  // 这里简化: 直接在订阅后启动轮询作为 fallback, WS 收到消息时停止
  // 但为避免无谓轮询, 仅在 WS 状态非 connected 时启动
  // 实际: useWsStream 断连会自动重连, 这里仅在初次连接前启动一个短轮询兜底
  // 后续 WS 连上后 onmessage 停止轮询
  startStatusPolling(runId, token)
}

export async function startMining(payload: Parameters<typeof api.miningStart>[0]) {
  closeEvents()
  localStorage.removeItem(ACTIVE_RUN_KEY)
  const token = connectionToken
  update({
    runId: null,
    isPending: true,
    cancelling: false,
    reconnecting: false,
    run: null,
    progress: { phase: 'queued', label: '创建任务' },
    result: null,
    previousResult: current.result ?? current.previousResult,
    error: null,
  })
  try {
    const run = await api.miningStart(payload)
    if (connectionToken !== token || current.runId !== null) return
    localStorage.setItem(ACTIVE_RUN_KEY, run.run_id)
    update({
      runId: run.run_id,
      run,
      progress: run.progress ?? current.progress,
      isPending: !TERMINAL_STATES.has(run.status),
    })
    if (TERMINAL_STATES.has(run.status)) {
      await refreshTerminalRun(run.run_id, run.status, run, token)
    } else {
      connect(run.run_id)
    }
  } catch (error) {
    if (connectionToken !== token || current.runId !== null) return
    update({
      isPending: false,
      error: String((error as Error).message || error),
    })
  }
}

export async function cancelMining() {
  if (!current.runId || !current.isPending || current.cancelling) return
  const runId = current.runId
  const token = connectionToken
  update({ cancelling: true, error: null })
  startStatusPolling(runId, token, true)
  try {
    const run = await api.miningCancel(runId)
    if (current.runId !== runId || connectionToken !== token) return
    update({
      run,
      progress: run.progress ?? current.progress,
      cancelling: !TERMINAL_STATES.has(run.status),
    })
    if (TERMINAL_STATES.has(run.status)) {
      closeEvents()
      const terminalToken = connectionToken
      await refreshTerminalRun(runId, run.status, run, terminalToken)
    }
  } catch (error) {
    if (current.runId !== runId || connectionToken !== token) return
    update({
      cancelling: true,
      reconnecting: true,
      error: String((error as Error).message || error),
    })
    startStatusPolling(runId, token, true)
  }
}

export async function attachMiningRun(runId: string): Promise<boolean> {
  closeEvents()
  const token = connectionToken
  const previousResult = current.result ?? current.previousResult
  update({
    runId,
    isPending: true,
    cancelling: false,
    reconnecting: true,
    run: null,
    progress: { phase: 'reconnecting', label: '读取任务状态' },
    result: null,
    previousResult,
    error: null,
  })
  try {
    const run = await api.miningRun(runId)
    if (current.runId !== runId || connectionToken !== token) return false
    update({
      run,
      progress: run.progress ?? null,
      isPending: !TERMINAL_STATES.has(run.status),
      cancelling: run.status === 'cancelling',
      reconnecting: false,
      error: run.error ?? null,
    })
    if (TERMINAL_STATES.has(run.status)) {
      await refreshTerminalRun(runId, run.status, run, token)
    } else {
      localStorage.setItem(ACTIVE_RUN_KEY, runId)
      connect(runId)
    }
    return true
  } catch (error) {
    if (current.runId !== runId || connectionToken !== token) return false
    localStorage.removeItem(ACTIVE_RUN_KEY)
    update({
      isPending: false,
      reconnecting: false,
      error: String((error as Error).message || error),
    })
    return false
  }
}

export function tryReconnectMining(): boolean {
  const runId = localStorage.getItem(ACTIVE_RUN_KEY)
  if (!runId) return false
  void attachMiningRun(runId)
  return true
}

export function clearMiningTask() {
  closeEvents()
  localStorage.removeItem(ACTIVE_RUN_KEY)
  current = {
    runId: null,
    isPending: false,
    cancelling: false,
    reconnecting: false,
    run: null,
    progress: null,
    result: null,
    previousResult: current.result ?? current.previousResult,
    error: null,
  }
  emit()
}

export function useMiningTask(): MiningTask {
  return useSyncExternalStore(subscribe, () => current, () => current)
}
