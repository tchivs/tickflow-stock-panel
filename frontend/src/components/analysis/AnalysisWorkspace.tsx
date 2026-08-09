import { useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useId, useRef, useState } from 'react'
import { AlertTriangle, RefreshCw, Sparkles } from 'lucide-react'
import type { AnalysisRequestSubject, AnalysisSubject } from '@/lib/api'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { AnalysisStatus } from './AnalysisStatus'
import { EvidencePanel } from './EvidencePanel'
import { LifecyclePanel } from './LifecyclePanel'
import { ReportPanel } from './ReportPanel'
import { ForecastPanel } from './ForecastPanel'
import { ThesisPanel } from './ThesisPanel'
import { ViewpointPanel } from '../advanced/ViewpointPanel'

type Tab = 'report' | 'evidence' | 'lifecycle' | 'thesis' | 'forecast'
const coreTabs: Array<{ id: Tab; label: string }> = [{ id: 'report', label: '分析结论' }, { id: 'evidence', label: '来源与核验' }, { id: 'lifecycle', label: '信号历史' }]
const stockTabs: Array<{ id: Tab; label: string }> = [...coreTabs, { id: 'thesis', label: '投资论点' }, { id: 'forecast', label: '概率预测' }]

export function AnalysisWorkspace({ subject, title }: { subject: AnalysisSubject; title: string }) {
  const storageKey = `analysis-workspace:${subject.kind}:${subject.key}`
  const workspaceTabs = subject.kind === 'stock' ? stockTabs : coreTabs
  // UI subjects remain stock/portfolio; all server cache and SSE identities use instrument/account.
  const serverSubject: AnalysisRequestSubject = { kind: subject.kind === 'stock' ? 'instrument' : 'account', key: subject.key }
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>(() => readStoredTab(storageKey, workspaceTabs))
  const scrollPositions = useRef<Partial<Record<Tab, number>>>({})
  const activeStorageKey = useRef(storageKey)
  const ids = useId()
  const reportsQuery = useQuery({ queryKey: QK.analysisReports(serverSubject.kind, serverSubject.key), queryFn: () => api.analysisReports(serverSubject) })
  const reports = (reportsQuery.data?.reports ?? []).filter(report => canonicalSubjectKind(report.subject.kind) === serverSubject.kind && report.subject.key === serverSubject.key)
  const latestReport = reports.find(report => report.id === selectedReportId) ?? reports[0]
  const reportQuery = useQuery({ queryKey: QK.analysisReport(serverSubject.kind, serverSubject.key, latestReport?.id ?? 'none'), queryFn: () => api.analysisReport(latestReport!.id), enabled: !!latestReport })
  const activeReport = reportQuery.data?.report && canonicalSubjectKind(reportQuery.data.report.subject.kind) === serverSubject.kind && reportQuery.data.report.subject.key === serverSubject.key ? reportQuery.data.report : null
  const evidenceQuery = useQuery({ queryKey: QK.analysisEvidence(serverSubject.kind, serverSubject.key, latestReport?.id ?? 'none'), queryFn: () => api.analysisEvidence(latestReport!.id), enabled: !!latestReport })
  const activeEvidence = evidenceQuery.data?.report_id === latestReport?.id ? evidenceQuery.data : undefined
  const signalId = activeReport?.signal_id
  const historyQuery = useQuery({ queryKey: QK.analysisSignalHistory(serverSubject.kind, serverSubject.key, signalId ?? 'none'), queryFn: () => api.analysisSignalHistory(signalId!), enabled: !!signalId })
  const startRun = useMutation({ mutationFn: () => api.analysisStartRun(serverSubject), onSuccess: result => { setSelectedReportId(current => current); sessionStorage.setItem(`${storageKey}:run`, result.run.id) } })
  const activeRun = startRun.data?.run

  useEffect(() => {
    activeStorageKey.current = storageKey
    setSelectedReportId(null)
    setTab(readStoredTab(storageKey, workspaceTabs))
    scrollPositions.current = {}
    startRun.reset()
  // startRun is stable for the mounted mutation observer; subject identity owns this reset.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey])
  useEffect(() => {
    if (activeStorageKey.current === storageKey) sessionStorage.setItem(`${storageKey}:tab`, tab)
  }, [storageKey, tab])
  useEffect(() => {
    if (workspaceTabs.some(item => item.id === tab)) return
    setTab('report')
  }, [tab, workspaceTabs])
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const panel = document.getElementById(`${ids}-${tab}-panel`)
      if (panel) panel.scrollTop = Number(sessionStorage.getItem(`${storageKey}:scroll:${tab}`)) || 0
    })
    return () => cancelAnimationFrame(frame)
  }, [ids, storageKey, tab])

  function onTabKeyDown(event: React.KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const next = (index + (event.key === 'ArrowRight' ? 1 : workspaceTabs.length - 1)) % workspaceTabs.length
    setTab(workspaceTabs[next].id)
    document.getElementById(`${ids}-${workspaceTabs[next].id}`)?.focus()
  }

  const retryLabel = reportsQuery.isError ? '重新加载分析报告' : '重新生成含证据说明的分析'
  return <section aria-label={`${title} 分析工作区`} className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-surface p-4">
      <div><h2 className="text-base font-semibold text-foreground">分析结论与证据状态</h2><p className="mt-1 text-sm text-secondary">{title}</p><AnalysisStatus run={activeRun} /></div>
      <button type="button" onClick={() => startRun.mutate()} disabled={startRun.isPending || activeRun?.status === 'queued' || activeRun?.status === 'running'} className="inline-flex min-h-11 items-center gap-2 rounded-btn bg-accent-solid px-3 text-sm font-semibold text-white focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base disabled:opacity-60"><Sparkles className="h-4 w-4" aria-hidden="true" />{startRun.isPending || activeRun?.status === 'running' ? '正在整理来源与生成分析…' : retryLabel}</button>
    </div>
    <ViewpointPanel subject={subject} serverSubject={serverSubject} />
    {subject.kind !== 'stock' && reportsQuery.isError && !reportsQuery.data ? <div role="alert" className="rounded-card border border-danger/50 bg-danger/10 p-4 text-sm text-danger">无法读取分析报告。请检查服务连接后重新加载分析报告。<button type="button" onClick={() => reportsQuery.refetch()} className="ml-2 underline">重新加载分析报告</button></div> : subject.kind !== 'stock' && !latestReport && !reportsQuery.isLoading ? <div className="rounded-card border border-border bg-surface p-4"><p className="text-sm font-semibold text-foreground">尚无含证据说明的分析报告</p><p className="mt-1 text-sm text-secondary">选择标的或账户后生成分析；报告会保留生成时间、来源限制和可审阅证据。</p></div> : <>
      {subject.kind === 'stock' && !latestReport && !reportsQuery.isLoading && <div className="rounded-card border border-border bg-surface p-4"><p className="text-sm font-semibold text-foreground">尚无含证据说明的分析报告</p><p className="mt-1 text-sm text-secondary">既有报告为空不会阻止读取独立的投资论点或概率预测记录。</p></div>}
      <div role="tablist" aria-label="分析详情" className="flex overflow-x-auto border-b border-border">{workspaceTabs.map((item, index) => <button key={item.id} id={`${ids}-${item.id}`} type="button" role="tab" aria-selected={tab === item.id} aria-controls={`${ids}-${item.id}-panel`} tabIndex={tab === item.id ? 0 : -1} onClick={() => setTab(item.id)} onKeyDown={event => onTabKeyDown(event, index)} className={`min-h-11 shrink-0 whitespace-nowrap px-4 text-sm outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base ${tab === item.id ? 'border-b-2 border-accent font-semibold text-foreground' : 'text-secondary'}`}>{item.label}</button>)}</div>
      {reportsQuery.isError && reportsQuery.data && <p role="status" className="text-sm text-warning">刷新分析报告失败，正在显示上次结果。<button type="button" onClick={() => reportsQuery.refetch()} className="ml-2 text-accent underline">重新加载分析报告</button></p>}
      <div id={`${ids}-report-panel`} role="tabpanel" aria-labelledby={`${ids}-report`} hidden={tab !== 'report'} onScroll={event => { scrollPositions.current.report = event.currentTarget.scrollTop; sessionStorage.setItem(`${storageKey}:scroll:report`, String(event.currentTarget.scrollTop)) }}>
        {activeReport ? <ReportPanel report={activeReport} evidence={activeEvidence} /> : <PanelState loading={reportQuery.isLoading || reportsQuery.isLoading} error={reportQuery.isError || reportsQuery.isError} onRetry={() => { void reportsQuery.refetch(); void reportQuery.refetch() }} label="分析报告" />}
      </div>
      <div id={`${ids}-evidence-panel`} role="tabpanel" aria-labelledby={`${ids}-evidence`} hidden={tab !== 'evidence'} onScroll={event => { scrollPositions.current.evidence = event.currentTarget.scrollTop; sessionStorage.setItem(`${storageKey}:scroll:evidence`, String(event.currentTarget.scrollTop)) }}>
        {activeEvidence ? <EvidencePanel evidence={activeEvidence} /> : <PanelState loading={evidenceQuery.isLoading || reportsQuery.isLoading} error={evidenceQuery.isError || reportsQuery.isError} onRetry={() => { void reportsQuery.refetch(); void evidenceQuery.refetch() }} label="来源与核验记录" />}
      </div>
      <div id={`${ids}-lifecycle-panel`} role="tabpanel" aria-labelledby={`${ids}-lifecycle`} hidden={tab !== 'lifecycle'} onScroll={event => { scrollPositions.current.lifecycle = event.currentTarget.scrollTop; sessionStorage.setItem(`${storageKey}:scroll:lifecycle`, String(event.currentTarget.scrollTop)) }}>
        {historyQuery.data ? <LifecyclePanel subject={subject} history={historyQuery.data} /> : <PanelState loading={historyQuery.isLoading || reportsQuery.isLoading} error={historyQuery.isError || reportsQuery.isError} onRetry={() => { void reportsQuery.refetch(); void historyQuery.refetch() }} label="信号历史" />}
      </div>
      {subject.kind === 'stock' && <div id={`${ids}-thesis-panel`} role="tabpanel" aria-labelledby={`${ids}-thesis`} hidden={tab !== 'thesis'} onScroll={event => { scrollPositions.current.thesis = event.currentTarget.scrollTop; sessionStorage.setItem(`${storageKey}:scroll:thesis`, String(event.currentTarget.scrollTop)) }}><ThesisPanel key={`instrument:${subject.key}`} instrument={subject.key} title={title} /></div>}
      {subject.kind === 'stock' && <div id={`${ids}-forecast-panel`} role="tabpanel" aria-labelledby={`${ids}-forecast`} hidden={tab !== 'forecast'} onScroll={event => { scrollPositions.current.forecast = event.currentTarget.scrollTop; sessionStorage.setItem(`${storageKey}:scroll:forecast`, String(event.currentTarget.scrollTop)) }}><ForecastPanel key={`instrument:${subject.key}`} instrument={subject.key} title={title} /></div>}
    </>}
  </section>
}

function canonicalSubjectKind(kind: string): AnalysisRequestSubject['kind'] | null {
  if (kind === 'stock' || kind === 'instrument') return 'instrument'
  if (kind === 'portfolio' || kind === 'account') return 'account'
  return null
}

function readStoredTab(storageKey: string, tabs: Array<{ id: Tab }>): Tab {
  const stored = sessionStorage.getItem(`${storageKey}:tab`) as Tab | null
  return stored && tabs.some(item => item.id === stored) ? stored : 'report'
}

function PanelState({ loading, error, onRetry, label }: { loading: boolean; error: boolean; onRetry: () => void; label: string }) {
  if (loading) return <div role="status" className="min-h-28 rounded-card border border-border bg-surface p-4 text-sm text-muted">正在读取{label}…</div>
  if (error) return <div role="alert" className="rounded-card border border-danger/50 bg-danger/10 p-4 text-sm text-danger"><AlertTriangle className="mr-2 inline h-4 w-4" aria-hidden="true" />无法读取{label}。<button type="button" onClick={onRetry} className="ml-2 inline-flex items-center gap-1 underline"><RefreshCw className="h-3 w-3" aria-hidden="true" />重新加载</button></div>
  return <div className="rounded-card border border-border bg-surface p-4 text-sm text-muted">暂无{label}。</div>
}
