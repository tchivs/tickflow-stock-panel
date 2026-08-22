import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { phase5Api, type ForecastJob, type ForecastJobStatus, type ForecastProgressEvent, type ForecastStage } from './phase5Api'
import { QK } from './queryKeys'
import * as wsStream from './useWsStream'

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

/** 从 WS 频道 data 载荷解析 ForecastProgressEvent */
function parseWsProgress(data: Record<string, unknown>, expectedJobId: string): ForecastProgressEvent | null {
  // WS data 载荷即为 SSE event 的 data (dict), 直接校验
  if (!isRecord(data)) return null
  const raw = JSON.stringify(data)
  return parseForecastProgressEvent(raw, expectedJobId)
}

export function useForecastTask({ instrument, jobId, enabled = true }: UseForecastTaskOptions): ForecastTaskState {
  const queryClient = useQueryClient()
  const [state, setState] = useState<ForecastTaskState>(INITIAL_STATE)
  const terminalHandledRef = useRef(false)

  useEffect(() => {
    if (!enabled || !jobId || !SAFE_REFERENCE.test(jobId) || !SAFE_INSTRUMENT.test(instrument)) {
      setState(INITIAL_STATE)
      return
    }

    let disposed = false
    let unsub: (() => void) | null = null
    terminalHandledRef.current = false

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
      if (unsub) { unsub(); unsub = null }
      await invalidateTerminal(persisted)
      if (disposed) return true
      setState(previous => ({
        ...previous,
        connection: 'stopped',
        progress: fallback,
        terminalJob: persisted,
        transportError: null,
        reconnectAttempt: 0,
      }))
      return true
    }

    setState(previous => ({ ...previous, connection: 'connecting' }))

    // 先检查持久化任务状态
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

    // 订阅 WS 频道 run:{jobId}
    const channel = `run:${jobId}`
    unsub = wsStream.subscribe(channel, (data, type) => {
      if (disposed) return

      // forecast 进度事件: forecast_event (后端 WS 广播) 或 done
      if (type === 'forecast_event' || type === 'done') {
        const progress = parseWsProgress(data, jobId)
        if (!progress) return

        setState(previous => ({
          ...previous,
          connection: 'connected',
          progress,
          transportError: null,
          reconnectAttempt: 0,
        }))

        if (isTerminal(progress.status)) {
          void finishFromPersisted(progress)
        }
      }
    })

    setState(previous => ({ ...previous, connection: 'connected', transportError: null }))

    return () => {
      disposed = true
      if (unsub) { unsub(); unsub = null }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, instrument, jobId, queryClient])

  return state
}
