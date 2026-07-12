import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'
import { useEffect, useId, useRef, useState } from 'react'
import { AlertTriangle, RefreshCw, Sparkles } from 'lucide-react'
import type { AnalysisRequestSubject, AnalysisSubject } from '@/lib/api'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { AnalysisStatus } from './AnalysisStatus'
import { EvidencePanel } from './EvidencePanel'
import { LifecyclePanel } from './LifecyclePanel'
import { ReportPanel } from './ReportPanel'

type Tab = 'report' | 'evidence' | 'lifecycle'
const tabs: Array<{ id: Tab; label: string }> = [{ id: 'report', label: '分析结论' }, { id: 'evidence', label: '来源与核验' }, { id: 'lifecycle', label: '信号历史' }]

export function AnalysisWorkspace({ subject, title }: { subject: AnalysisSubject; title: string }) {
  const storageKey = `analysis-workspace:${subject.kind}:${subject.key}`
  // UI subjects remain stock/portfolio; the established API authorizes instrument/account.
  const serverSubject: AnalysisRequestSubject = { kind: subject.kind === 'stock' ? 'instrument' : 'account', key: subject.key }
  const [selectedReportId, setSelectedReportId] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>(() => (sessionStorage.getItem(`${storageKey}:tab`) as Tab | null) ?? 'report')
  const scrollPosition = useRef(0)
  const ids = useId()
  const reportsQuery = useQuery({ queryKey: QK.analysisReports(subject.kind, subject.key), queryFn: () => api.analysisReports(serverSubject), placeholderData: keepPreviousData })
  const latestReport = reportsQuery.data?.reports.find(report => report.id === selectedReportId) ?? reportsQuery.data?.reports[0]
  const reportQuery = useQuery({ queryKey: QK.analysisReport(subject.kind, subject.key, latestReport?.id ?? 'none'), queryFn: () => api.analysisReport(latestReport!.id), enabled: !!latestReport, placeholderData: keepPreviousData })
  const evidenceQuery = useQuery({ queryKey: QK.analysisEvidence(subject.kind, subject.key, latestReport?.id ?? 'none'), queryFn: () => api.analysisEvidence(latestReport!.id), enabled: !!latestReport, placeholderData: keepPreviousData })
  const signalId = reportQuery.data?.report?.signal_id
  const historyQuery = useQuery({ queryKey: QK.analysisSignalHistory(subject.kind, subject.key, signalId ?? 'none'), queryFn: () => api.analysisSignalHistory(signalId!), enabled: !!signalId, placeholderData: keepPreviousData })
  const startRun = useMutation({ mutationFn: () => api.analysisStartRun(serverSubject), onSuccess: result => { setSelectedReportId(current => current); sessionStorage.setItem(`${storageKey}:run`, result.run.id) } })
  const activeRun = startRun.data?.run

  useEffect(() => { sessionStorage.setItem(`${storageKey}:tab`, tab) }, [storageKey, tab])
  useEffect(() => () => sessionStorage.setItem(`${storageKey}:scroll`, String(scrollPosition.current)), [storageKey])

  function onTabKeyDown(event: React.KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const next = (index + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length
    setTab(tabs[next].id)
    document.getElementById(`${ids}-${tabs[next].id}`)?.focus()
  }

  const retryLabel = reportsQuery.isError ? '重新加载分析报告' : '重新生成含证据说明的分析'
  return <section aria-label={`${title} 分析工作区`} className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-surface p-4">
      <div><h2 className="text-base font-semibold text-foreground">分析结论与证据状态</h2><p className="mt-1 text-sm text-secondary">{title}</p><AnalysisStatus run={activeRun} /></div>
      <button type="button" onClick={() => startRun.mutate()} disabled={startRun.isPending || activeRun?.status === 'queued' || activeRun?.status === 'running'} className="inline-flex min-h-11 items-center gap-2 rounded-btn bg-accent px-3 text-sm font-semibold text-white focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base disabled:opacity-60"><Sparkles className="h-4 w-4" aria-hidden="true" />{startRun.isPending || activeRun?.status === 'running' ? '正在整理来源与生成分析…' : retryLabel}</button>
    </div>
    {reportsQuery.isError && !reportsQuery.data ? <div role="alert" className="rounded-card border border-danger/50 bg-danger/10 p-4 text-sm text-danger">无法读取分析报告。请检查服务连接后重新加载分析报告。<button type="button" onClick={() => reportsQuery.refetch()} className="ml-2 underline">重新加载分析报告</button></div> : !latestReport && !reportsQuery.isLoading ? <div className="rounded-card border border-border bg-surface p-4"><p className="text-sm font-semibold text-foreground">尚无含证据说明的分析报告</p><p className="mt-1 text-sm text-secondary">选择标的或账户后生成分析；报告会保留生成时间、来源限制和可审阅证据。</p></div> : <><div role="tablist" aria-label="分析详情" className="flex overflow-x-auto border-b border-border">{tabs.map((item, index) => <button key={item.id} id={`${ids}-${item.id}`} type="button" role="tab" aria-selected={tab === item.id} aria-controls={`${ids}-${item.id}-panel`} tabIndex={tab === item.id ? 0 : -1} onClick={() => setTab(item.id)} onKeyDown={event => onTabKeyDown(event, index)} className={`min-h-11 shrink-0 px-4 text-sm outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base ${tab === item.id ? 'border-b-2 border-accent font-semibold text-foreground' : 'text-secondary'}`}>{item.label}</button>)}</div>
      {reportsQuery.isError && reportsQuery.data && <p role="status" className="text-sm text-warning">刷新分析报告失败，正在显示上次结果。<button type="button" onClick={() => reportsQuery.refetch()} className="ml-2 text-accent underline">重新加载分析报告</button></p>}
      <div id={`${ids}-${tab}-panel`} role="tabpanel" aria-labelledby={`${ids}-${tab}`} onScroll={event => { scrollPosition.current = event.currentTarget.scrollTop }}>
        {tab === 'report' && (reportQuery.data?.report ? <ReportPanel report={reportQuery.data.report} evidence={evidenceQuery.data} /> : <PanelState loading={reportQuery.isLoading} error={reportQuery.isError} onRetry={() => reportQuery.refetch()} label="分析报告" />)}
        {tab === 'evidence' && (evidenceQuery.data ? <EvidencePanel evidence={evidenceQuery.data} /> : <PanelState loading={evidenceQuery.isLoading} error={evidenceQuery.isError} onRetry={() => evidenceQuery.refetch()} label="来源与核验记录" />)}
        {tab === 'lifecycle' && (historyQuery.data ? <LifecyclePanel subject={subject} history={historyQuery.data} /> : <PanelState loading={historyQuery.isLoading} error={historyQuery.isError} onRetry={() => historyQuery.refetch()} label="信号历史" />)}
      </div></>}
  </section>
}

function PanelState({ loading, error, onRetry, label }: { loading: boolean; error: boolean; onRetry: () => void; label: string }) {
  if (loading) return <div role="status" className="min-h-28 rounded-card border border-border bg-surface p-4 text-sm text-muted">正在读取{label}…</div>
  if (error) return <div role="alert" className="rounded-card border border-danger/50 bg-danger/10 p-4 text-sm text-danger"><AlertTriangle className="mr-2 inline h-4 w-4" aria-hidden="true" />无法读取{label}。<button type="button" onClick={onRetry} className="ml-2 inline-flex items-center gap-1 underline"><RefreshCw className="h-3 w-3" aria-hidden="true" />重新加载</button></div>
  return <div className="rounded-card border border-border bg-surface p-4 text-sm text-muted">暂无{label}。</div>
}
