import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { AnalysisSignalHistory, AnalysisSubject } from '@/lib/api'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

const stateLabels = { strengthened: '信号已强化', weakened: '信号已弱化', falsified: '信号已证伪', priced_in: '信号已计价' } as const

export function LifecyclePanel({ subject, history }: { subject: AnalysisSubject; history: AnalysisSignalHistory }) {
  const queryClient = useQueryClient()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: QK.analysisSignalHistory(subject.kind, subject.key, history.signal_id) })
  const confirm = useMutation({ mutationFn: (reviewId: string) => api.analysisConfirmReview(reviewId, 60), onSuccess: invalidate })
  const reject = useMutation({ mutationFn: api.analysisRejectReview, onSuccess: invalidate })
  const reviewId = (history as AnalysisSignalHistory & { pending_review_id?: string }).pending_review_id
  const outcome = history.outcome
  return <section aria-labelledby="lifecycle-heading" className="space-y-4 rounded-card border border-border bg-surface p-4 md:p-6">
    <header><h2 id="lifecycle-heading" className="text-base font-semibold text-foreground">信号生命周期</h2>{history.current_state ? <p className="mt-1 text-sm text-secondary">当前状态：{stateLabels[history.current_state]}</p> : <p className="mt-1 text-sm text-muted">该标的尚无可追溯信号事件</p>}</header>
    {reviewId && <div className="flex flex-wrap gap-2" aria-label="生命周期人工审阅"><button type="button" onClick={() => confirm.mutate(reviewId)} disabled={confirm.isPending || reject.isPending} className="min-h-11 rounded-btn bg-accent px-3 text-sm font-semibold text-white focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base">确认服务端审阅</button><button type="button" onClick={() => reject.mutate(reviewId)} disabled={confirm.isPending || reject.isPending} className="min-h-11 rounded-btn border border-border px-3 text-sm text-secondary focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base">拒绝服务端审阅</button></div>}
    {outcome?.status === 'pending' ? <p className="text-sm text-warning">结果待观察</p> : outcome?.status === 'recorded' ? <p className="text-sm text-secondary">已记录结果</p> : null}
    {outcome?.missing_fields?.length ? <p className="text-sm text-warning">结果记录不完整：{outcome.missing_fields.join('、')}。</p> : null}
    {history.events.length ? <div className="overflow-x-auto"><table className="min-w-[720px] text-left text-sm"><caption className="caption-top pb-2 text-left text-sm text-muted">信号事件按时间倒序保留</caption><thead className="border-b border-border text-muted"><tr><th scope="col" className="p-2">状态</th><th scope="col" className="p-2">事件时间</th><th scope="col" className="p-2">证据摘要</th><th scope="col" className="p-2">来源/核验</th></tr></thead><tbody>{[...history.events].sort((left, right) => right.occurred_at.localeCompare(left.occurred_at)).map(event => <tr key={`${event.state}-${event.occurred_at}`} className="border-b border-border/60"><th scope="row" className="p-2 font-medium text-foreground">{stateLabels[event.state]}</th><td className="p-2 font-mono text-secondary">{event.occurred_at}</td><td className="p-2 break-words text-secondary">{event.evidence_summary}</td><td className="p-2 text-secondary">{event.source_grade ?? '—'} / {event.cross_check ?? '—'}</td></tr>)}</tbody></table></div> : <p className="text-sm text-muted">生成或导入带证据的研究信号后，状态变化和结果会在这里按时间保留。</p>}
  </section>
}
