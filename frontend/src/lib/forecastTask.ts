import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { phase5Api, type ForecastJob, type ForecastJobStatus, type ForecastProgressEvent, type ForecastStage } from './phase5Api'
import { QK } from './queryKeys'

const MAX_RECONNECT_ATTEMPTS = 5
const BASE_RECONNECT_DELAY_MS = 500
const SAFE_REFERENCE = /^[A-Za-z0-9._:-]{1,128}$/
const SAFE_INSTRUMENT = /^[0-9A-Z.-]{1,32}$/
const EVENT_KEYS = new Set(['job_id', 'status', 'stage', 'stage_recorded_at', 'safe_reason'])
const FORECAST_STATUSES = new Set<ForecastJobStatus>([
  'queued',
  'running',
  'completed',
  'validation_failed',
  'checkpoint_mismatch',
  'artifact_failed',
  'timeout',
  'resource_terminated',
  'interrupted',
])
const FORECAST_STAGES = new Set<ForecastStage>([
  'validating_checkpoint',
  'freezing_input',
  'generating_paths',
  'computing_quantiles',
  'saving_record',
  'completed',
  'validation_failed',
  'checkpoint_mismatch',
  'artifact_failed',
  'timeout',
  'resource_terminated',
  'interrupted',
])
const TERMINAL_STATUSES = new Set<ForecastJobStatus>([
  'completed',
  'validation_failed',
  'checkpoint_mismatch',
  'artifact_failed',
  'timeout',
  'resource_terminated',
  'interrupted',
])

export type ForecastConnectionState = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'stopped'

export interface ForecastTaskState {
  connection: ForecastConnectionState
  progress: ForecastProgressEvent | null
  terminalJob: ForecastJob | null
  transportError: string | null
  reconnectAttempt: number
}

export interface UseForecastTaskOptions {
  instrument: string
  jobId: string | null
  enabled?: boolean
}

const INITIAL_STATE: ForecastTaskState = {
  connection: 'idle',
  progress: null,
  terminalJob: null,
  transportError: null,
  reconnectAttempt: 0,
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isTerminal(status: ForecastJobStatus): boolean {
  return TERMINAL_STATUSES.has(status)
}

export function parseForecastProgressEvent(raw: string, expectedJobId: string): ForecastProgressEvent | null {
  let value: unknown
  try {
    value = JSON.parse(raw)
  } catch {
    return null
  }
  if (!isRecord(value)) return null
  const keys = Object.keys(value)
  if (keys.some(key => !EVENT_KEYS.has(key))) return null
  if (typeof value.job_id !== 'string' || value.job_id !== expectedJobId || !SAFE_REFERENCE.test(value.job_id)) return null
  if (typeof value.status !== 'string' || !FORECAST_STATUSES.has(value.status as ForecastJobStatus)) return null
  if (typeof value.stage !== 'string' || !FORECAST_STAGES.has(value.stage as ForecastStage)) return null
  if (typeof value.stage_recorded_at !== 'string' || value.stage_recorded_at.length === 0 || value.stage_recorded_at.length > 64) return null
  if (value.safe_reason !== undefined && (typeof value.safe_reason !== 'string' || value.safe_reason.length > 512)) return null
  return {
    job_id: value.job_id,
    status: value.status as ForecastJobStatus,
    stage: value.stage as ForecastStage,
    stage_recorded_at: value.stage_recorded_at,
    ...(typeof value.safe_reason === 'string' ? { safe_reason: value.safe_reason } : {}),
  }
}

export function useForecastTask({ instrument, jobId, enabled = true }: UseForecastTaskOptions): ForecastTaskState {
  const queryClient = useQueryClient()
  const [state, setState] = useState<ForecastTaskState>(INITIAL_STATE)
  const abortRef = useRef<AbortController | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const healthyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reconnectAttemptRef = useRef(0)
  const latestEventIdRef = useRef<string | null>(null)
  const terminalHandledRef = useRef(false)

  useEffect(() => {
    if (!enabled || !jobId || !SAFE_REFERENCE.test(jobId) || !SAFE_INSTRUMENT.test(instrument)) {
      setState(INITIAL_STATE)
      return
    }

    let disposed = false
    const eventStorageKey = `forecast-sse:${instrument}:${jobId}:last-event-id`
    const storedEventId = sessionStorage.getItem(eventStorageKey)
    latestEventIdRef.current = storedEventId && /^(?:0|[1-9][0-9]{0,18})$/.test(storedEventId) ? storedEventId : null
    reconnectAttemptRef.current = 0
    terminalHandledRef.current = false

    const clearHealthyTimer = () => {
      if (healthyTimerRef.current) {
        clearTimeout(healthyTimerRef.current)
        healthyTimerRef.current = null
      }
    }

    const clearTransport = () => {
      abortRef.current?.abort()
      abortRef.current = null
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      clearHealthyTimer()
    }

    const invalidateTerminal = async (job: ForecastJob) => {
      queryClient.setQueryData(QK.forecast.job(instrument, jobId), { job })
      const invalidations: Array<Promise<unknown>> = [
        queryClient.invalidateQueries({ queryKey: QK.forecast.jobsRoot(instrument) }),
      ]
      if (job.record_id) {
        invalidations.push(
          queryClient.invalidateQueries({ queryKey: QK.forecast.recordsRoot(instrument) }),
          queryClient.invalidateQueries({ queryKey: QK.forecast.record(instrument, job.record_id) }),
          queryClient.invalidateQueries({ queryKey: QK.forecast.pathsRoot(instrument, job.record_id) }),
          queryClient.invalidateQueries({ queryKey: QK.forecast.calibration(instrument, job.record_id) }),
        )
      }
      await Promise.all(invalidations)
    }

    const refreshPersistedJob = async (): Promise<ForecastJob | null> => {
      try {
        const response = await queryClient.fetchQuery({
          queryKey: QK.forecast.job(instrument, jobId),
          queryFn: () => phase5Api.forecastJob(jobId),
          staleTime: 0,
        })
        return response.job.instrument === instrument ? response.job : null
      } catch {
        return null
      }
    }

    const finishFromPersisted = async (fallback: ForecastProgressEvent): Promise<boolean> => {
      if (terminalHandledRef.current) return true
      const persisted = await refreshPersistedJob()
      if (disposed) return true
      if (!persisted || !isTerminal(persisted.status)) return false
      terminalHandledRef.current = true
      clearTransport()
      await invalidateTerminal(persisted)
      if (disposed) return true
      setState(previous => ({
        ...previous,
        connection: 'stopped',
        progress: fallback,
        terminalJob: persisted,
        transportError: null,
        reconnectAttempt: reconnectAttemptRef.current,
      }))
      return true
    }

    const scheduleReconnect = async (connect: () => void) => {
      clearHealthyTimer()
      const persisted = await refreshPersistedJob()
      if (disposed) return
      if (persisted && isTerminal(persisted.status)) {
        await finishFromPersisted({
          job_id: persisted.id,
          status: persisted.status,
          stage: persisted.stage,
          stage_recorded_at: persisted.stage_recorded_at,
          ...(persisted.safe_reason ? { safe_reason: persisted.safe_reason } : {}),
        })
        return
      }
      reconnectAttemptRef.current += 1
      if (reconnectAttemptRef.current > MAX_RECONNECT_ATTEMPTS) {
        clearTransport()
        setState(previous => ({
          ...previous,
          connection: 'stopped',
          transportError: '进度连接已中断；最后已知任务阶段已保留。',
          reconnectAttempt: MAX_RECONNECT_ATTEMPTS,
        }))
        return
      }
      const attempt = reconnectAttemptRef.current
      setState(previous => ({ ...previous, connection: 'reconnecting', transportError: null, reconnectAttempt: attempt }))
      reconnectTimerRef.current = setTimeout(connect, Math.min(BASE_RECONNECT_DELAY_MS * 2 ** (attempt - 1), 8_000))
    }

    const acceptFrame = (frame: string): ForecastProgressEvent | null => {
      let eventType = 'message'
      let eventId: string | null = null
      const data: string[] = []
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) eventType = line.slice(6).trim()
        else if (line.startsWith('id:')) eventId = line.slice(3).trim()
        else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
      }
      if ((eventType !== 'forecast_progress' && eventType !== 'done') || !eventId || !/^(?:0|[1-9][0-9]{0,18})$/.test(eventId)) return null
      const previousId = latestEventIdRef.current
      if (previousId != null && BigInt(eventId) <= BigInt(previousId)) return null
      const progress = parseForecastProgressEvent(data.join('\n'), jobId)
      if (!progress) return null
      latestEventIdRef.current = eventId
      sessionStorage.setItem(eventStorageKey, eventId)
      reconnectAttemptRef.current = 0
      clearHealthyTimer()
      setState(previous => ({ ...previous, connection: 'connected', progress, transportError: null, reconnectAttempt: 0 }))
      return progress
    }

    const connect = async () => {
      if (disposed) return
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      setState(previous => ({ ...previous, connection: reconnectAttemptRef.current === 0 ? 'connecting' : 'reconnecting', transportError: null }))
      try {
        const headers = new Headers({ Accept: 'text/event-stream' })
        if (latestEventIdRef.current) headers.set('Last-Event-ID', latestEventIdRef.current)
        const response = await fetch(`/api/forecast/jobs/${encodeURIComponent(jobId)}/stream`, { headers, signal: controller.signal })
        if (!response.ok || !response.body) throw new Error(`Forecast progress stream returned ${response.status}`)
        setState(previous => ({ ...previous, connection: 'connected', transportError: null, reconnectAttempt: reconnectAttemptRef.current }))
        healthyTimerRef.current = setTimeout(() => {
          if (disposed || abortRef.current !== controller) return
          reconnectAttemptRef.current = 0
          setState(previous => ({ ...previous, reconnectAttempt: 0 }))
        }, 10_000)
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        while (!disposed) {
          const chunk = await reader.read()
          if (chunk.done) break
          buffer += decoder.decode(chunk.value, { stream: true }).replace(/\r\n/g, '\n')
          let boundary = buffer.indexOf('\n\n')
          while (boundary >= 0) {
            const frame = buffer.slice(0, boundary)
            buffer = buffer.slice(boundary + 2)
            const progress = acceptFrame(frame)
            if (progress && isTerminal(progress.status) && await finishFromPersisted(progress)) return
            boundary = buffer.indexOf('\n\n')
          }
        }
        if (!disposed) await scheduleReconnect(() => { void connect() })
      } catch (error) {
        if (!disposed && !(error instanceof DOMException && error.name === 'AbortError')) await scheduleReconnect(() => { void connect() })
      }
    }

    setState(INITIAL_STATE)
    void refreshPersistedJob().then(persisted => {
      if (disposed || !persisted) return
      const progress: ForecastProgressEvent = {
        job_id: persisted.id,
        status: persisted.status,
        stage: persisted.stage,
        stage_recorded_at: persisted.stage_recorded_at,
        ...(persisted.safe_reason ? { safe_reason: persisted.safe_reason } : {}),
      }
      setState(previous => ({ ...previous, progress }))
      if (isTerminal(persisted.status)) void finishFromPersisted(progress)
    })
    void connect()

    return () => {
      disposed = true
      clearTransport()
    }
  }, [enabled, instrument, jobId, queryClient])

  return state
}
