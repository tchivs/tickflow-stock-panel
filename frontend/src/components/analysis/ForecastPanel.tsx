import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ChevronLeft, ChevronRight, Copy } from 'lucide-react'
import { useId, useMemo, useState } from 'react'
import type { EChartsOption } from 'echarts'
import { ApiRequestError } from '@/lib/api'
import { useForecastTask } from '@/lib/forecastTask'
import {
  phase5Api,
  type ForecastCalibration,
  type ForecastCatalogEntry,
  type ForecastHorizon,
  type ForecastJob,
  type ForecastPathPoint,
  type ForecastRecord,
} from '@/lib/phase5Api'
import { QK } from '@/lib/queryKeys'
import { useChartTheme } from '@/lib/theme'
import { useECharts } from '@/pages/backtest/charts/useECharts'

const FOCUS = 'focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base'
const BUTTON = `inline-flex min-h-11 items-center justify-center rounded-btn px-3 text-sm ${FOCUS}`
const HORIZONS: ForecastHorizon[] = [5, 20, 60]
const PATH_PAGE_SIZE = 12

type LooseRecord = Record<string, unknown>

interface ForecastPanelProps {
  instrument: string
  title: string
}

interface QuantileRow {
  session: string
  p10: number | null
  p50: number | null
  p90: number | null
  unit: string
}

interface PathRow {
  session: string
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  volume: number | null
}

interface PathView {
  id: string
  index: number
  seedLabel: string
  warnings: string[]
  rows: PathRow[]
}

interface CalibrationView {
  horizon: number
  status: string
  actualSession: string | null
  actualValue: number | null
  targetSession: string | null
  closeMae: number | null
  intervalCoverage: number | boolean | null
  pinballP10: number | null
  pinballP50: number | null
  pinballP90: number | null
  sampleCount: number | null
  coverageStart: string | null
  coverageEnd: string | null
}

function record(value: unknown): LooseRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as LooseRecord : {}
}

function text(value: unknown, fallback = '—'): string {
  return typeof value === 'string' && value.length > 0 ? value : fallback
}

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function dateTime(value: unknown): string {
  if (typeof value !== 'string' || !value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString('zh-CN', { hour12: false })
}

function errorReason(error: unknown): string {
  if (error instanceof ApiRequestError) {
    const detail = record(error.detail)
    return text(detail.reason, text(detail.message, error.message))
  }
  return error instanceof Error ? error.message : '服务暂不可用'
}

function displayTitle(title: string, instrument: string): string {
  const normalized = title.replace(/（([^）]+)）/, ' $1')
  return normalized.includes(instrument) ? normalized : `${normalized} ${instrument}`
}

function catalogProjection(entry: ForecastCatalogEntry): LooseRecord {
  const source = record(entry)
  return {
    id: text(source.catalog_id, entry.catalog_id),
    model: text(source.model, entry.model_repo),
    tokenizer: text(source.tokenizer, entry.tokenizer_repo),
    sourceRevision: text(source.source_revision, entry.source_revision),
    modelRevision: text(source.model_revision, entry.model_revision),
    tokenizerRevision: text(source.tokenizer_revision, entry.tokenizer_revision),
    modelDigest: text(source.model_weight_sha256, text(source.digest, entry.model_weight_sha256)),
    tokenizerDigest: text(source.tokenizer_weight_sha256, entry.tokenizer_weight_sha256),
    pairing: text(source.pairing, entry.pairing),
    maxContext: num(source.max_context) ?? entry.max_context,
    device: text(source.device, entry.allowed_devices?.join('、') || '部署决定'),
    integrity: text(source.integrity, entry.integrity ?? 'unknown'),
    available: source.available !== false && entry.available !== false,
    reason: text(source.reason, entry.reason ?? ''),
  }
}

function quantileRows(sourceRecord: ForecastRecord): QuantileRow[] {
  const source = record(sourceRecord)
  if (Array.isArray(source.quantiles)) {
    return source.quantiles.map((item, index) => {
      const row = record(item)
      return { session: text(row.session, `T+${index + 1}`), p10: num(row.p10), p50: num(row.p50), p90: num(row.p90), unit: text(row.unit, 'CNY') }
    })
  }
  const values = sourceRecord.quantiles ?? {}
  const sessions = sourceRecord.future_session_ids ?? []
  return Object.entries(values).map(([key, value], index) => ({
    session: sessions[index] ?? key,
    p10: num(value.p10),
    p50: num(value.p50),
    p90: num(value.p90),
    unit: 'CNY',
  }))
}

function embeddedPaths(sourceRecord: ForecastRecord): PathView[] {
  const source = record(sourceRecord)
  if (!Array.isArray(source.paths)) return []
  return source.paths.map((item, index) => {
    const path = record(item)
    const rows = Array.isArray(path.rows) ? path.rows.map(rowValue => {
      const row = record(rowValue)
      return { session: text(row.session, '—'), open: num(row.open), high: num(row.high), low: num(row.low), close: num(row.close), volume: num(row.volume) }
    }) : []
    return { id: text(path.id, `path-${index + 1}`), index, seedLabel: text(path.seed_label, `sample-${index + 1}`), warnings: strings(path.warnings), rows }
  })
}

function pathsFromPoints(points: ForecastPathPoint[]): PathView[] {
  const grouped = new Map<number, Map<string, LooseRecord>>()
  for (const point of points) {
    const pathIndex = point.path_index ?? 0
    const session = point.session_id ?? '—'
    const sessionMap = grouped.get(pathIndex) ?? new Map<string, LooseRecord>()
    const row = sessionMap.get(session) ?? { session }
    if (point.feature && point.value != null) row[point.feature] = point.value
    sessionMap.set(session, row)
    grouped.set(pathIndex, sessionMap)
  }
  return [...grouped.entries()].map(([index, rows]) => ({
    id: `path-${index + 1}`,
    index,
    seedLabel: `sample-${index + 1}`,
    warnings: points.filter(item => item.path_index === index && item.warning_code).map(item => item.warning_code as string),
    rows: [...rows.values()].map(row => ({ session: text(row.session), open: num(row.open), high: num(row.high), low: num(row.low), close: num(row.close), volume: num(row.volume) })),
  }))
}

function calibrationViews(recordValue: ForecastRecord, calibrations: ForecastCalibration[]): CalibrationView[] {
  const source = record(recordValue)
  if (Array.isArray(source.calibration)) {
    return source.calibration.map(item => {
      const row = record(item)
      return {
        horizon: num(row.horizon) ?? recordValue.horizon,
        status: text(row.status, 'pending'),
        actualSession: typeof row.actual_session === 'string' ? row.actual_session : null,
        actualValue: num(row.actual_value),
        targetSession: typeof row.target_session === 'string' ? row.target_session : null,
        closeMae: num(row.close_mae),
        intervalCoverage: typeof row.interval_coverage === 'boolean' || typeof row.interval_coverage === 'number' ? row.interval_coverage : null,
        pinballP10: num(row.p10_pinball),
        pinballP50: num(row.p50_pinball),
        pinballP90: num(row.p90_pinball),
        sampleCount: num(row.sample_count),
        coverageStart: typeof row.coverage_start === 'string' ? row.coverage_start : null,
        coverageEnd: typeof row.coverage_end === 'string' ? row.coverage_end : null,
      }
    })
  }
  return calibrations.map(item => ({
    horizon: recordValue.horizon,
    status: item.close_mae == null ? 'pending' : 'evaluated',
    actualSession: null,
    actualValue: null,
    targetSession: recordValue.future_session_ids.at(-1) ?? null,
    closeMae: item.close_mae,
    intervalCoverage: item.p10_p90_interval_covered,
    pinballP10: item.pinball_p10,
    pinballP50: item.pinball_p50,
    pinballP90: item.pinball_p90,
    sampleCount: null,
    coverageStart: item.coverage_start,
    coverageEnd: item.coverage_end,
  }))
}

function recordLabel(value: ForecastRecord): string {
  return text(record(value).label, `预测 ${value.id.slice(0, 8)}`)
}

function recordAsOf(value: ForecastRecord): string {
  return text(record(value).as_of, value.origin_session_id)
}

function recordWarnings(value: ForecastRecord): string[] {
  return strings(record(value).warnings).length ? strings(record(value).warnings) : value.validation_warnings ?? []
}

function recordCheckpoint(value: ForecastRecord): LooseRecord {
  const embedded = record(record(value).checkpoint)
  return Object.keys(embedded).length ? embedded : {
    catalog_id: value.catalog_id,
    source_revision: value.source_revision,
    model_revision: value.model_revision,
    model_digest: value.model_digest_sha256,
    tokenizer_revision: value.tokenizer_revision,
    tokenizer_digest: value.tokenizer_digest_sha256,
  }
}

function recordInput(value: ForecastRecord): LooseRecord {
  const embedded = record(record(value).input)
  return Object.keys(embedded).length ? embedded : { fingerprint: value.input_fingerprint, schema: 'daily OHLCV', coverage_end: value.origin_session_id, session_count: value.lookback }
}

function jobStageLabel(stage: unknown): string {
  const labels: Record<string, string> = {
    validating_checkpoint: '正在验证批准检查点',
    freezing_input: '正在冻结受治理日线',
    generating_paths: '正在生成采样路径',
    computing_quantiles: '正在计算 P10/P50/P90',
    saving_record: '正在保存不可变记录',
    completed: '已完成',
    '已完成': '已完成',
    validation_failed: '验证失败',
    checkpoint_mismatch: '检查点不匹配',
    artifact_failed: '工件校验失败',
    timeout: '超时',
    resource_terminated: '资源终止',
    interrupted: '任务中断',
  }
  return labels[text(stage, '')] ?? text(stage, '等待任务记录')
}

export function ForecastPanel({ instrument, title }: ForecastPanelProps) {
  const queryClient = useQueryClient()
  const headingId = useId()
  const [horizon, setHorizon] = useState<ForecastHorizon>(20)
  const [catalogId, setCatalogId] = useState('')
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [pathPage, setPathPage] = useState(0)
  const [selectedPathIds, setSelectedPathIds] = useState<string[]>([])
  const [pathsOpen, setPathsOpen] = useState(false)
  const [copied, setCopied] = useState<string | null>(null)

  const capabilityQuery = useQuery({ queryKey: QK.phase5Capabilities, queryFn: phase5Api.capabilities, staleTime: 60_000 })
  const catalogQuery = useQuery({ queryKey: QK.forecast.catalog, queryFn: phase5Api.forecastCatalog, placeholderData: keepPreviousData })
  const recordsQuery = useQuery({ queryKey: QK.forecast.records(instrument), queryFn: () => phase5Api.forecastRecords(instrument), placeholderData: keepPreviousData })
  const jobsQuery = useQuery({ queryKey: QK.forecast.jobs(instrument), queryFn: () => phase5Api.forecastJobs(instrument), placeholderData: keepPreviousData })

  const catalogEntries = catalogQuery.data?.entries ?? []
  const selectedCatalog = catalogEntries.find(entry => entry.catalog_id === catalogId) ?? catalogEntries[0]
  const selectedCatalogView = selectedCatalog ? catalogProjection(selectedCatalog) : null
  const createJob = useMutation({
    mutationFn: () => phase5Api.forecastCreateJob(instrument, {
      horizon,
      catalog_id: selectedCatalog!.catalog_id,
      idempotency_key: crypto.randomUUID(),
    }),
    onSuccess: response => {
      setActiveJobId(response.job.id)
      queryClient.setQueryData(QK.forecast.job(instrument, response.job.id), response)
      void queryClient.invalidateQueries({ queryKey: QK.forecast.jobs(instrument) })
      if (response.job.record_id) void queryClient.invalidateQueries({ queryKey: QK.forecast.records(instrument) })
    },
  })
  const records = recordsQuery.data?.records ?? []
  const selectedRecord = records.find(item => item.id === selectedRecordId) ?? records[0]
  const embedded = selectedRecord ? embeddedPaths(selectedRecord) : []
  const pathsQuery = useQuery({
    queryKey: QK.forecast.paths(instrument, selectedRecord?.id ?? 'none', pathPage * PATH_PAGE_SIZE, PATH_PAGE_SIZE),
    queryFn: () => phase5Api.forecastPaths(selectedRecord!.id, pathPage * PATH_PAGE_SIZE, PATH_PAGE_SIZE),
    enabled: !!selectedRecord && embedded.length === 0,
    placeholderData: keepPreviousData,
  })
  const calibrationQuery = useQuery({
    queryKey: QK.forecast.calibration(instrument, selectedRecord?.id ?? 'none'),
    queryFn: () => phase5Api.forecastCalibration(selectedRecord!.id),
    enabled: !!selectedRecord,
    placeholderData: keepPreviousData,
  })
  const task = useForecastTask({ instrument, jobId: activeJobId, enabled: !!activeJobId && createJob.data?.job.status !== 'completed' })

  const capability = capabilityQuery.data?.modules.forecast
  const unavailable = capability?.available === false
  const gateVerified = !!selectedCatalogView && selectedCatalogView.available === true && selectedCatalogView.integrity === 'verified'
  const selectedPathsPage = embedded.length ? embedded.slice(pathPage * PATH_PAGE_SIZE, (pathPage + 1) * PATH_PAGE_SIZE) : pathsFromPoints(pathsQuery.data?.items ?? [])
  const totalPaths = embedded.length || pathsQuery.data?.total || selectedRecord?.sample_count || 0
  const visibleSelectedPaths = selectedPathsPage.filter(item => selectedPathIds.includes(item.id))
  const pathForTable = visibleSelectedPaths[0] ?? selectedPathsPage[0]
  const quantiles = selectedRecord ? quantileRows(selectedRecord) : []
  const calibration = selectedRecord ? calibrationViews(selectedRecord, calibrationQuery.data?.calibration ?? []) : []
  const latestGovernedSession = recordsQuery.data?.latest_governed_session_id
  const selectedRecordAsOf = selectedRecord ? recordAsOf(selectedRecord) : null
  const latestGovernedTime = latestGovernedSession ? Date.parse(latestGovernedSession) : Number.NaN
  const selectedRecordTime = selectedRecordAsOf ? Date.parse(selectedRecordAsOf) : Number.NaN
  const staleRecord = Number.isFinite(latestGovernedTime) && Number.isFinite(selectedRecordTime) && latestGovernedTime > selectedRecordTime


  const taskJob = task.terminalJob ?? createJob.data?.job ?? null
  const progressStage = task.progress?.stage ?? taskJob?.stage
  const showReconnect = task.connection === 'reconnecting' || task.transportError != null
  const historicalTerminalJob = jobsQuery.data?.jobs.find(job => !['queued', 'running', 'completed'].includes(job.status)) ?? null
  const pageCount = Math.max(1, Math.ceil(totalPaths / PATH_PAGE_SIZE))

  function togglePath(id: string) {
    setSelectedPathIds(current => current.includes(id) ? current.filter(item => item !== id) : current.length >= 12 ? current : [...current, id])
  }

  if (capabilityQuery.isLoading && !capability) return <PanelLoading label="正在确认 Kronos 预测能力并读取批准检查点…" />
  if (capabilityQuery.isError && !capability) return <LocalError title="暂时无法确认模块状态" detail={errorReason(capabilityQuery.error)} action="重新确认模块状态" onRetry={() => capabilityQuery.refetch()} />
  if (unavailable) return <section aria-labelledby={headingId} className="rounded-card border border-border bg-surface p-4 sm:p-6"><PanelHeading id={headingId} status="不可用" /><p className="mt-3 max-w-[72ch] text-sm text-foreground">此部署未启用 Kronos 预测，或没有通过完整性校验的批准检查点。现有个股分析、投资论点和 v1 工作流仍可使用。请联系部署维护者预装并批准固定检查点。</p></section>

  return <section aria-labelledby={headingId} className="space-y-6 rounded-card border border-border bg-surface p-4 text-sm text-foreground transition-colors duration-200 motion-reduce:transition-none sm:p-6">
    <header className="space-y-2"><PanelHeading id={headingId} status="可用" /><p className="font-mono text-sm tabular-nums">{displayTitle(title, instrument)}</p><p data-phase5-typography className="max-w-[72ch] text-sm font-normal text-secondary">预测是不确定性研究记录，不会自动改变论点、策略、计划、监控或市场动作。</p></header>

    <section aria-labelledby={`${headingId}-request`} className="space-y-4 rounded-card border border-border bg-elevated p-4">
      <h3 id={`${headingId}-request`} className="text-base font-semibold">预测请求审阅</h3>
      <fieldset><legend className="mb-2 font-semibold">预测范围</legend><div role="radiogroup" aria-label="预测范围" className="grid grid-cols-3 gap-2">{HORIZONS.map(value => <label key={value} className={`flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-btn border px-3 ${horizon === value ? 'border-accent bg-accent/10' : 'border-border bg-surface'} ${FOCUS}`}><input type="radio" name={`${headingId}-horizon`} value={value} checked={horizon === value} onChange={() => setHorizon(value)} className="h-4 w-4" />{value} 个交易日</label>)}</div></fieldset>
      <label className="block font-semibold">批准检查点<select value={selectedCatalog?.catalog_id ?? ''} onChange={event => setCatalogId(event.target.value)} className={`mt-2 min-h-11 w-full rounded-input border border-border bg-surface px-3 text-sm ${FOCUS}`} disabled={!catalogEntries.length}>{catalogEntries.length ? catalogEntries.map(entry => <option key={entry.catalog_id} value={entry.catalog_id}>{text(record(entry).model, entry.model_repo)} · {entry.catalog_id}</option>) : <option value="">没有通过校验的本地检查点</option>}</select></label>
      {catalogQuery.isError && <LocalError title="无法读取批准检查点目录" detail={`无法读取批准检查点目录：${errorReason(catalogQuery.error)}。尚未开始预测，当前标的和 horizon 选择已保留。`} action="重新加载批准检查点目录" onRetry={() => catalogQuery.refetch()} compact />}
      {!catalogQuery.isLoading && !catalogEntries.length && <div role="alert" className="rounded-input border border-warning/50 bg-warning/10 p-3 text-warning">此部署未启用 Kronos 预测，或没有通过完整性校验的批准检查点。现有个股分析、投资论点和 v1 工作流仍可使用。请联系部署维护者预装并批准固定检查点。</div>}
      {selectedCatalogView && <CatalogDetails view={selectedCatalogView} />}
      {selectedCatalogView && !gateVerified && <div role="alert" className="rounded-input border border-danger/50 bg-danger/10 p-3 text-danger"><AlertTriangle className="mr-2 inline h-4 w-4" aria-hidden="true" />完整性校验未通过：{text(selectedCatalogView.reason, String(selectedCatalogView.integrity))}。不能开始任务，也不能绕过本地批准目录。</div>}
      <div className="rounded-input border border-border bg-surface p-3"><p className="font-semibold">开始前确认</p><p className="mt-1 text-secondary">对象 {instrument} · {horizon} 个交易日 · 检查点 {selectedCatalog?.catalog_id ?? '未选择'}。服务端将冻结受治理日线、解析检查点身份并创建新的不可变任务；浏览器不提供量化结果、摘要或官方状态。</p></div>
      <button type="button" onClick={() => createJob.mutate()} disabled={!gateVerified || createJob.isPending || (!!taskJob && (taskJob.status === 'queued' || taskJob.status === 'running'))} className={`${BUTTON} w-full bg-accent font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto`}>{createJob.isPending ? '正在创建预测任务…' : '生成概率预测'}</button>
    </section>

    {(taskJob || progressStage) && <section aria-live="polite" className="rounded-card border border-border p-4"><h3 className="text-base font-semibold">当前任务</h3><p className="mt-2">{taskJob?.id ?? activeJobId} · {jobStageLabel(progressStage)}</p>{showReconnect && <p className="mt-2 text-warning">进度连接已中断，正在按记录状态重新连接。</p>}{taskJob && taskJob.status !== 'completed' && !['queued', 'running'].includes(taskJob.status) && <TerminalError job={taskJob} />}</section>}
    {createJob.isError && <LocalError title="预测未完成" detail={`预测未完成：${errorReason(createJob.error)}。未创建概率预测记录；若服务端已创建任务，其只读状态将通过任务历史恢复。`} action="查看恢复方式" onRetry={() => createJob.mutate()} compact />}

    {recordsQuery.isError && <LocalError title="无法读取概率预测历史" detail={`无法读取概率预测历史：${errorReason(recordsQuery.error)}。此前显示的记录和当前选择保持不变。`} action="重新加载概率预测历史" onRetry={() => recordsQuery.refetch()} compact />}
    {!recordsQuery.isLoading && !selectedRecord ? <div className="rounded-card border border-border p-4"><h3 className="text-base font-semibold">尚无此标的的概率预测</h3><p className="mt-2 text-secondary">选择 5、20 或 60 个交易日与一个已批准检查点，生成包含 P10/P50/P90 和采样路径的不可变记录。</p></div> : null}

    {selectedRecord && <article className="space-y-5" aria-labelledby={`${headingId}-result`}>
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h3 id={`${headingId}-result`} className="text-base font-semibold">{recordLabel(selectedRecord)}</h3><p className="mt-1 text-xs text-secondary">completed · 数据截至 {recordAsOf(selectedRecord)} · {selectedRecord.horizon} 个交易日 · {selectedRecord.sample_count} 个样本</p></div><button type="button" onClick={() => { setHorizon(selectedRecord.horizon); setCatalogId(selectedRecord.catalog_id); createJob.mutate() }} disabled={!gateVerified || createJob.isPending} className={`${BUTTON} border border-border bg-elevated disabled:opacity-50`}>基于相同配置创建新预测</button></div>
      {recordWarnings(selectedRecord).map(warning => <p key={warning} role="alert" className="rounded-input bg-warning/10 p-3 text-warning">validation warning：{warning}</p>)}
      {staleRecord && <p role="status" className="rounded-input border border-warning/50 bg-warning/10 p-3 text-warning">已有更新行情；此预测仍保留其原始数据截至日。</p>}
      <QuantileSummary rows={quantiles} asOf={recordAsOf(selectedRecord)} />
      <ForecastChart rows={quantiles} paths={visibleSelectedPaths} />
      <QuantileTable rows={quantiles} />

      <section aria-labelledby={`${headingId}-paths`} className="space-y-3"><div className="flex flex-wrap items-center justify-between gap-3"><div><h3 id={`${headingId}-paths`} className="text-base font-semibold">{totalPaths || selectedRecord.sample_count} 条采样路径</h3><p className="text-xs text-secondary">最多同时绘制 12 条；所有路径仍可分页检查。</p></div><button type="button" onClick={() => setPathsOpen(value => !value)} aria-expanded={pathsOpen} className={`${BUTTON} border border-border`}>查看采样路径</button></div>
        <fieldset><legend className="mb-2 text-xs text-secondary">选择当前页采样路径</legend><div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{selectedPathsPage.map(path => <label key={path.id} className="flex min-h-11 items-center gap-2 rounded-input border border-border px-3"><input type="checkbox" aria-label={`采样路径 ${path.index + 1}`} checked={selectedPathIds.includes(path.id)} onChange={() => togglePath(path.id)} className="h-4 w-4" /><span>采样路径 {path.index + 1} · {path.seedLabel}</span></label>)}</div></fieldset>
        {pathsQuery.isError && embedded.length === 0 && <LocalError title="预测工件完整性校验失败" detail={`预测工件完整性校验失败：${errorReason(pathsQuery.error)}。失败工件不会作为结果开放；不可用路径不会被伪造。`} action="重新读取已校验工件" onRetry={() => pathsQuery.refetch()} compact />}
        {pathsOpen && <><div className="flex items-center justify-between"><p>共 {totalPaths} 条路径 · 第 {pathPage + 1}/{pageCount} 页</p><div className="flex gap-2"><button type="button" aria-label="上一页采样路径" onClick={() => setPathPage(page => Math.max(0, page - 1))} disabled={pathPage === 0} className={`${BUTTON} min-w-11 border border-border disabled:opacity-40`}><ChevronLeft className="h-4 w-4" aria-hidden="true" /></button><button type="button" aria-label="下一页采样路径" onClick={() => setPathPage(page => Math.min(pageCount - 1, page + 1))} disabled={pathPage >= pageCount - 1} className={`${BUTTON} min-w-11 border border-border disabled:opacity-40`}><ChevronRight className="h-4 w-4" aria-hidden="true" /></button></div></div><PathTable path={pathForTable} /></>}
      </section>

      <details className="rounded-card border border-border p-3"><summary className={`min-h-11 cursor-pointer py-2 font-semibold ${FOCUS}`}>查看检查点与输入谱系</summary><Provenance recordValue={selectedRecord} copied={copied} onCopy={value => { void navigator.clipboard.writeText(value); setCopied(value) }} /></details>
      {calibrationQuery.isError && <LocalError title="受治理实际值不可用" detail={`暂不可评估：${errorReason(calibrationQuery.error)}。原始 P10/P50/P90、采样路径和检查点谱系保持不变。`} action="重新加载校准证据" onRetry={() => calibrationQuery.refetch()} compact />}
      <CalibrationTable rows={calibration} />
    </article>}

    {historicalTerminalJob && historicalTerminalJob.id !== taskJob?.id ? <TerminalError job={historicalTerminalJob} /> : null}
    {jobsQuery.isError && <LocalError title="预测状态连接中断" detail={`预测状态连接中断：${errorReason(jobsQuery.error)}。已显示的历史和最后已知任务阶段将保留；连接中断不代表推理失败，也不会重复启动任务。`} action="重新连接并刷新任务状态" onRetry={() => jobsQuery.refetch()} compact />}
    <ForecastHistory records={records} jobs={jobsQuery.data?.jobs ?? []} selectedRecordId={selectedRecord?.id ?? null} onSelect={id => { setSelectedRecordId(id); setPathPage(0); setSelectedPathIds([]) }} />
  </section>
}


function PanelHeading({ id, status }: { id: string; status: '可用' | '不可用' }) {
  return <div className="flex flex-wrap items-center gap-3"><h2 id={id} data-phase5-typography className="text-base font-semibold">Kronos 概率预测</h2><span data-phase5-typography className={`rounded-full px-2 py-1 text-xs font-normal ${status === '可用' ? 'bg-accent/10 text-accent' : 'bg-warning/10 text-warning'}`}>{status}</span></div>
}

function PanelLoading({ label }: { label: string }) {
  return <div role="status" className="min-h-32 rounded-card border border-border bg-surface p-4 text-sm text-secondary">{label}</div>
}

function LocalError({ title, detail, action, onRetry, compact = false }: { title: string; detail: string; action: string; onRetry: () => void; compact?: boolean }) {
  return <div role="alert" className={`rounded-card border border-danger/50 bg-danger/10 text-sm text-danger ${compact ? 'p-3' : 'p-4'}`}><p className="font-semibold"><AlertTriangle className="mr-2 inline h-4 w-4" aria-hidden="true" />{title}</p><p className="mt-1">{detail}</p><button type="button" onClick={onRetry} className={`${BUTTON} mt-2 border border-danger/50`}>{action}</button></div>
}

function CatalogDetails({ view }: { view: LooseRecord }) {
  return <dl className="grid gap-3 rounded-input border border-border bg-surface p-3 text-xs sm:grid-cols-2 lg:grid-cols-3"><div><dt className="text-secondary">模型 / Tokenizer</dt><dd>{String(view.model)} / {String(view.tokenizer)}</dd></div><div><dt className="text-secondary">不可变 revisions</dt><dd className="break-words font-mono [overflow-wrap:anywhere]">source {String(view.sourceRevision)} · model {String(view.modelRevision)} · tokenizer {String(view.tokenizerRevision)}</dd></div><div><dt className="text-secondary">完整性校验</dt><dd>{view.integrity === 'verified' ? '已通过完整性校验' : String(view.integrity)}</dd></div><div><dt className="text-secondary">模型摘要</dt><dd className="break-words font-mono [overflow-wrap:anywhere]">{String(view.modelDigest)}</dd></div><div><dt className="text-secondary">Tokenizer 摘要</dt><dd className="break-words font-mono [overflow-wrap:anywhere]">{String(view.tokenizerDigest)}</dd></div><div><dt className="text-secondary">pairing / 上下文 / 设备</dt><dd>{String(view.pairing)} · {String(view.maxContext)} · {String(view.device)}</dd></div></dl>
}

function TerminalError({ job }: { job: ForecastJob }) {
  return <div role="alert" className="mt-3 rounded-input bg-danger/10 p-3 text-danger"><p className="font-semibold">预测未完成</p><p>预测未完成：{job.safe_reason ?? job.status}。未创建概率预测记录；此任务已作为只读终态保留。请按错误类型完成下方恢复操作后创建新任务。</p><p className="mt-1">查看恢复方式：检查本地批准目录、受治理输入、worker 资源与工件完整性后创建新任务；不得绕过校验或覆盖本任务。</p></div>
}

function QuantileSummary({ rows, asOf }: { rows: QuantileRow[]; asOf: string }) {
  const last = rows.at(-1)
  const first = rows[0]
  return (
    <section aria-labelledby="forecast-quantile-summary">
      <h3 id="forecast-quantile-summary" className="text-base font-semibold">终点分位数摘要</h3>
      <p className="mt-1 text-xs text-secondary">相对数据截至日 {asOf}；P50 是分位数中位路径，不是确定结果。</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        {(['p10', 'p50', 'p90'] as const).map(key => (
          <div key={key} className="rounded-input border border-border p-3">
            <p className="font-semibold text-foreground">{key.toUpperCase()}</p>
            <p className="mt-1 font-mono text-base tabular-nums">{last?.[key] ?? '—'} {last?.unit ?? 'CNY'}</p>
            <p className="text-xs text-secondary">目标交易日 {last?.session ?? '—'} · 首日 {first?.[key] ?? '—'}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

function ForecastChart({ rows, paths }: { rows: QuantileRow[]; paths: PathView[] }) {
  const theme = useChartTheme()
  const option = useMemo<EChartsOption | null>(() => {
    if (!rows.length) return null
    const p10 = rows.map(item => item.p10)
    const band = rows.map((item, index) => item.p10 == null || item.p90 == null ? null : item.p90 - (p10[index] ?? 0))
    return {
      animation: false,
      grid: { left: 56, right: 24, top: 48, bottom: 42 },
      legend: { top: 4, textStyle: { color: theme.text }, data: ['历史 close', 'P10', 'P10–P90 不确定区间', 'P50', 'P90', 'actual', ...paths.map(path => `采样路径 ${path.index + 1}`)] },
      tooltip: { trigger: 'axis', backgroundColor: theme.tooltipBg, borderColor: theme.tooltipBorder, textStyle: { color: theme.tooltipText } },
      xAxis: { type: 'category', data: rows.map(item => item.session), axisLabel: { color: theme.text }, axisLine: { lineStyle: { color: theme.border } } },
      yAxis: { type: 'value', scale: true, axisLabel: { color: theme.text }, splitLine: { lineStyle: { color: theme.grid } } },
      series: [
        { name: '历史 close', type: 'line', data: [], showSymbol: false, lineStyle: { color: theme.textStrong, width: 1.5 } },
        { name: 'P10', type: 'line', data: p10, stack: 'band', showSymbol: false, lineStyle: { color: theme.text, width: 1, type: 'dashed' } },
        { name: 'P10–P90 不确定区间', type: 'line', data: band, stack: 'band', showSymbol: false, lineStyle: { opacity: 0 }, areaStyle: { color: 'rgba(59,130,246,0.12)' } },
        { name: 'P50', type: 'line', data: rows.map(item => item.p50), showSymbol: false, lineStyle: { color: '#3B82F6', width: 2 } },
        { name: 'P90', type: 'line', data: rows.map(item => item.p90), showSymbol: false, lineStyle: { color: theme.text, width: 1, type: 'dashed' } },
        { name: 'actual', type: 'line', data: [], showSymbol: true, lineStyle: { color: theme.textStrong, width: 1.5 } },
        ...paths.map(path => ({ name: `采样路径 ${path.index + 1}`, type: 'line' as const, data: path.rows.map(item => item.close), showSymbol: false, lineStyle: { color: theme.textStrong, width: 1.5, opacity: 0.55 } })),
      ],
    }
  }, [paths, rows, theme])
  const chartRef = useECharts(option, [rows, paths, theme])
  return <div ref={chartRef} role="img" aria-label="历史 close、P10、P90、P10–P90 不确定区间、P50、actual 与选中采样路径概率图；表格顺序 P10、P50、P90" className="h-[280px] w-full md:h-[320px] xl:h-[360px]" />
}

function QuantileTable({ rows }: { rows: QuantileRow[] }) {
  const descriptionId = useId()
  return <><p id={descriptionId} className="text-xs text-secondary">左右滚动查看完整记录</p><div tabIndex={0} aria-describedby={descriptionId} className={`overflow-x-auto ${FOCUS}`}><table className="min-w-[560px] w-full text-right text-xs"><caption className="sr-only">逐日 P10 P50 P90 分位数</caption><thead className="bg-elevated text-secondary"><tr><th scope="col" className="p-2 text-left">交易日</th><th scope="col" className="p-2">P10</th><th scope="col" className="p-2">P50</th><th scope="col" className="p-2">P90</th><th scope="col" className="p-2">单位</th></tr></thead><tbody>{rows.map(row => <tr key={row.session} className="border-t border-border"><th scope="row" className="p-2 text-left font-normal">{row.session}</th><td className="p-2 font-mono">{row.p10 ?? '—'}</td><td className="p-2 font-mono text-accent">{row.p50 ?? '—'}</td><td className="p-2 font-mono">{row.p90 ?? '—'}</td><td className="p-2">{row.unit}</td></tr>)}</tbody></table></div></>
}

function PathTable({ path }: { path: PathView | undefined }) {
  const descriptionId = useId()
  return <><p id={descriptionId} className="text-xs text-secondary">左右滚动查看完整记录。{path ? `当前 ${path.seedLabel}；${path.warnings.length ? `warning：${path.warnings.join('、')}` : '无 validation warning'}` : '当前页无可读路径。'}</p><div tabIndex={0} aria-describedby={descriptionId} className={`overflow-x-auto ${FOCUS}`}><table className="min-w-[720px] w-full text-right text-xs"><caption className="sr-only">选中采样路径 OHLCV</caption><thead className="bg-elevated text-secondary"><tr><th scope="col" className="p-2 text-left">交易日</th><th scope="col" className="p-2">Open</th><th scope="col" className="p-2">High</th><th scope="col" className="p-2">Low</th><th scope="col" className="p-2">Close</th><th scope="col" className="p-2">Volume</th></tr></thead><tbody>{path?.rows.length ? path.rows.map(row => <tr key={row.session} className="border-t border-border"><th scope="row" className="p-2 text-left font-normal">{row.session}</th><td className="p-2 font-mono">{row.open ?? '—'}</td><td className="p-2 font-mono">{row.high ?? '—'}</td><td className="p-2 font-mono">{row.low ?? '—'}</td><td className="p-2 font-mono">{row.close ?? '—'}</td><td className="p-2 font-mono">{row.volume ?? '—'}</td></tr>) : <tr><td colSpan={6} className="p-4 text-center text-secondary">当前路径工件没有可读数据。</td></tr>}</tbody></table></div></>
}

function Provenance({ recordValue, copied, onCopy }: { recordValue: ForecastRecord; copied: string | null; onCopy: (value: string) => void }) {
  const checkpoint = recordCheckpoint(recordValue)
  const input = recordInput(recordValue)
  const rows = [
    ['Kronos source revision', text(checkpoint.source_revision, recordValue.source_revision)],
    ['model / tokenizer identity', `${text(checkpoint.model, recordValue.catalog_id)} / ${text(checkpoint.tokenizer, recordValue.catalog_id)}`],
    ['model revision', text(checkpoint.model_revision, recordValue.model_revision)],
    ['tokenizer revision', text(checkpoint.tokenizer_revision, recordValue.tokenizer_revision)],
    ['integrity digest', text(checkpoint.digest, text(checkpoint.model_digest, recordValue.model_digest_sha256))],
    ['pairing', text(checkpoint.pairing, '由批准目录固定')],
    ['运行配置', `lookback ${recordValue.lookback} · seed ${recordValue.seed} · T ${recordValue.temperature} · top_k ${recordValue.top_k} · top_p ${recordValue.top_p} · sample_count ${recordValue.sample_count}`],
    ['受治理 input fingerprint', text(input.fingerprint, recordValue.input_fingerprint)],
    ['日历 / session 范围', `${recordValue.calendar_id} @ ${recordValue.calendar_revision} · ${text(input.coverage_start, '—')} – ${text(input.coverage_end, recordValue.origin_session_id)}`],
    ['输入 schema', text(input.schema, 'daily OHLCV')],
    ['artifact descriptor', `${recordValue.output_artifact?.artifact_id ?? '—'} · ${recordValue.output_artifact?.checksum_sha256 ?? recordValue.paths_checksum_sha256}`],
  ]
  return <dl className="mt-3 grid gap-3 text-xs sm:grid-cols-2">{rows.map(([label, value]) => <div key={label}><dt className="text-secondary">{label}</dt><dd className="mt-1 flex items-start gap-1"><code className="break-words font-mono [overflow-wrap:anywhere]">{value}</code><button type="button" aria-label={`复制${label}`} title={`复制${label}`} onClick={() => onCopy(value)} className={`${FOCUS} inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-btn text-accent sm:min-h-0 sm:min-w-0 sm:p-1`}><Copy className="h-4 w-4" aria-hidden="true" /></button>{copied === value && <span role="status" className="sr-only">已复制</span>}</dd></div>)}</dl>
}

function CalibrationTable({ rows }: { rows: CalibrationView[] }) {
  const descriptionId = useId()
  return <section aria-labelledby={`${descriptionId}-heading`} className="space-y-2"><h3 id={`${descriptionId}-heading`} className="text-base font-semibold">追加式校准</h3><p id={descriptionId} className="text-xs text-secondary">左右滚动查看完整记录。校准只追加受治理实际值，不改写原分位数或采样路径。</p><div tabIndex={0} aria-describedby={descriptionId} className={`overflow-x-auto ${FOCUS}`}><table className="min-w-[980px] w-full text-right text-xs"><caption className="sr-only">预测校准证据</caption><thead className="bg-elevated text-secondary"><tr><th scope="col" className="p-2 text-left">范围 / 状态</th><th scope="col" className="p-2">实际交易日 / close</th><th scope="col" className="p-2">Close MAE</th><th scope="col" className="p-2">P10–P90 coverage</th><th scope="col" className="p-2">P10 pinball</th><th scope="col" className="p-2">P50 pinball</th><th scope="col" className="p-2">P90 pinball</th><th scope="col" className="p-2">样本数</th><th scope="col" className="p-2">覆盖期</th></tr></thead><tbody>{rows.length ? rows.map((row, index) => <tr key={`${row.horizon}-${index}`} className="border-t border-border"><th scope="row" className="p-2 text-left font-normal">{row.horizon} 个交易日 · {row.status === 'evaluated' ? '已评估' : row.status === 'pending' ? '未成熟' : '暂不可评估'}</th><td className="p-2">{row.status === 'pending' ? `目标 ${row.targetSession ?? '—'}` : row.status === 'unevaluable' ? '暂不可评估：缺少受治理实际值。' : `${row.actualSession ?? '—'} / ${row.actualValue ?? '—'}`}</td><td className="p-2">{row.closeMae ?? '—'}</td><td className="p-2">{row.intervalCoverage == null ? '—' : `${typeof row.intervalCoverage === 'boolean' ? (row.intervalCoverage ? 100 : 0) : row.intervalCoverage * 100}%`}</td><td className="p-2">{row.pinballP10 ?? '—'}</td><td className="p-2">{row.pinballP50 ?? '—'}</td><td className="p-2">{row.pinballP90 ?? '—'}</td><td className="p-2">{row.sampleCount ?? '—'}</td><td className="p-2">{row.coverageStart && row.coverageEnd ? `${row.coverageStart} – ${row.coverageEnd}` : '—'}</td></tr>) : <tr><td colSpan={9} className="p-4 text-center text-secondary">尚未到达目标交易日，校准将在受治理实际值可用后追加。</td></tr>}</tbody></table></div>{rows.some(row => row.status === 'pending') && <p className="text-warning">尚未到达目标交易日，校准将在受治理实际值可用后追加。</p>}</section>
}

function ForecastHistory({ records, jobs, selectedRecordId, onSelect }: { records: ForecastRecord[]; jobs: ForecastJob[]; selectedRecordId: string | null; onSelect: (id: string) => void }) {
  const descriptionId = useId()
  return <section aria-labelledby={`${descriptionId}-heading`} className="space-y-2"><h3 id={`${descriptionId}-heading`} className="text-base font-semibold">不可变预测与任务历史</h3><p id={descriptionId} className="text-xs text-secondary">左右滚动查看完整记录。失败任务与完成记录均只读保留；只有 completed 任务关联概率结果。</p><div tabIndex={0} aria-describedby={descriptionId} className={`overflow-x-auto ${FOCUS}`}><table className="min-w-[900px] w-full text-left text-xs"><caption className="sr-only">不可变概率预测历史</caption><thead className="bg-elevated text-secondary"><tr><th scope="col" className="p-2">记录 / 状态</th><th scope="col" className="p-2">创建时间</th><th scope="col" className="p-2">as-of / horizon</th><th scope="col" className="p-2">检查点</th><th scope="col" className="p-2">P50 终点</th><th scope="col" className="p-2">样本 / fingerprint</th><th scope="col" className="p-2">详情</th></tr></thead><tbody>{records.map(item => { const rows = quantileRows(item); return <tr key={item.id} className={`border-t border-border ${item.id === selectedRecordId ? 'bg-accent/5' : ''}`}><th scope="row" className="p-2 font-normal">{recordLabel(item)} · completed</th><td className="p-2">{dateTime(item.created_at)}</td><td className="p-2">{recordAsOf(item)} / {item.horizon}</td><td className="p-2">{item.catalog_id}</td><td className="p-2 font-mono">{rows.at(-1)?.p50 ?? '—'}</td><td className="p-2">{item.sample_count}<span className="block break-words font-mono [overflow-wrap:anywhere]">{text(recordInput(item).fingerprint, item.input_fingerprint)}</span></td><td className="p-2"><button type="button" onClick={() => onSelect(item.id)} className={`${BUTTON} min-h-0 py-2 text-accent underline`}>查看不可变记录</button></td></tr> })}{jobs.filter(job => job.status !== 'completed').map(job => <tr key={job.id} className="border-t border-border"><th scope="row" className="p-2 font-normal">{job.id} · {job.status}</th><td className="p-2">{dateTime(job.created_at)}</td><td className="p-2">— / {job.horizon}</td><td className="p-2">{job.catalog_id}</td><td className="p-2">未创建结果</td><td className="p-2">{job.safe_reason ?? '只读终态'}</td><td className="p-2">查看恢复方式</td></tr>)}</tbody></table></div>{jobs.length === 0 && records.length === 0 && <p className="text-secondary">尚无任务或不可变记录。</p>}</section>
}

