import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type {
  AnalysisObservationOutcomeInput,
  AnalysisObservationPlan,
  AnalysisSignalHistory,
  AnalysisSubject,
} from '@/lib/api'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

const stateLabels = {
  strengthened: '信号已强化',
  weakened: '信号已弱化',
  falsified: '信号已证伪',
  priced_in: '信号已计价',
} as const

export function LifecyclePanel({
  subject,
  history,
}: {
  subject: AnalysisSubject
  history: AnalysisSignalHistory
}) {
  const queryClient = useQueryClient()
  const serverSubjectKind = subject.kind === 'stock' ? 'instrument' : 'account'
  const invalidate = () => queryClient.invalidateQueries({
    queryKey: QK.analysisSignalHistory(serverSubjectKind, subject.key, history.signal_id),
  })
  const confirm = useMutation({
    mutationFn: (reviewId: string) => api.analysisConfirmReview(reviewId, 60),
    onSuccess: invalidate,
  })
  const reject = useMutation({
    mutationFn: api.analysisRejectReview,
    onSuccess: invalidate,
  })
  const pendingReview = history.reviews.find(
    review => review.id === history.pending_review_id && review.status === 'pending',
  )

  return <section aria-labelledby="lifecycle-heading" className="space-y-4 rounded-card border border-border bg-surface p-4 md:p-6">
    <header>
      <h2 id="lifecycle-heading" className="text-base font-semibold text-foreground">信号生命周期</h2>
      {history.current_state
        ? <p className="mt-1 text-sm text-secondary">当前状态：{stateLabels[history.current_state]}</p>
        : <p className="mt-1 text-sm text-muted">该标的尚无可追溯信号事件</p>}
    </header>
    {pendingReview && <div className="rounded-btn border border-warning/50 bg-warning/10 p-3" aria-label="生命周期人工审阅">
      <p className="text-sm font-semibold text-warning">
        待审生命周期提案：{stateLabels[pendingReview.proposed_state as keyof typeof stateLabels]}
      </p>
      <p className="mt-1 break-words text-sm text-secondary">{pendingReview.rationale ?? '服务端未提供提案理由。'}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => confirm.mutate(pendingReview.id)}
          disabled={confirm.isPending || reject.isPending}
          className="min-h-11 rounded-btn bg-accent px-3 text-sm font-semibold text-white focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base"
        >
          确认服务端审阅
        </button>
        <button
          type="button"
          onClick={() => reject.mutate(pendingReview.id)}
          disabled={confirm.isPending || reject.isPending}
          className="min-h-11 rounded-btn border border-border px-3 text-sm text-secondary focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base"
        >
          拒绝服务端审阅
        </button>
      </div>
    </div>}
    <ReviewHistory reviews={history.reviews} />
    <ObservationPlans plans={history.plans} onRecorded={invalidate} />
    {history.outcome?.status === 'pending'
      ? <p className="text-sm text-warning">结果待观察</p>
      : history.outcome?.status === 'recorded'
        ? <p className="text-sm text-secondary">已记录结果</p>
        : null}
    {history.events.length
      ? <div className="overflow-x-auto">
        <table className="min-w-[720px] text-left text-sm">
          <caption className="caption-top pb-2 text-left text-sm text-muted">信号事件按时间倒序保留</caption>
          <thead className="border-b border-border text-muted">
            <tr>
              <th scope="col" className="p-2">状态</th>
              <th scope="col" className="p-2">事件时间</th>
              <th scope="col" className="p-2">证据摘要</th>
              <th scope="col" className="p-2">来源/核验</th>
            </tr>
          </thead>
          <tbody>{[...history.events]
            .sort((left, right) => right.occurred_at.localeCompare(left.occurred_at))
            .map(event => <tr key={`${event.state}-${event.occurred_at}`} className="border-b border-border/60">
              <th scope="row" className="p-2 font-medium text-foreground">{stateLabels[event.state]}</th>
              <td className="p-2 font-mono text-secondary">{event.occurred_at}</td>
              <td className="p-2 break-words text-secondary">{event.evidence_summary}</td>
              <td className="p-2 text-secondary">{event.source_grade ?? '—'} / {event.cross_check ?? '—'}</td>
            </tr>)}</tbody>
        </table>
      </div>
      : <p className="text-sm text-muted">生成或导入带证据的研究信号后，状态变化和结果会在这里按时间保留。</p>}
  </section>
}

function ReviewHistory({ reviews }: Pick<AnalysisSignalHistory, 'reviews'>) {
  if (!reviews.length) return null
  return <section aria-labelledby="review-history-heading" className="space-y-2">
    <h3 id="review-history-heading" className="text-base font-semibold text-foreground">审阅记录</h3>
    <div className="overflow-x-auto">
      <table className="min-w-[720px] text-left text-sm">
        <caption className="caption-top pb-2 text-left text-sm text-muted">服务端保留的待审、已确认和已拒绝提案</caption>
        <thead className="border-b border-border text-muted">
          <tr>
            <th scope="col" className="p-2">提案状态</th>
            <th scope="col" className="p-2">建议变化</th>
            <th scope="col" className="p-2">证据引用</th>
            <th scope="col" className="p-2">提案理由</th>
            <th scope="col" className="p-2">创建时间</th>
          </tr>
        </thead>
        <tbody>{reviews.map(review => <tr key={review.id} className="border-b border-border/60 align-top">
          <th scope="row" className="p-2 font-medium text-foreground">
            {review.status === 'pending' ? '待审' : review.status === 'confirmed' ? '已确认' : '已拒绝'}
          </th>
          <td className="p-2 text-secondary">{stateLabels[review.proposed_state as keyof typeof stateLabels] ?? review.proposed_state}</td>
          <td className="p-2 text-secondary">{review.evidence_ids.length}</td>
          <td className="p-2 break-words text-secondary">{review.rationale ?? '—'}</td>
          <td className="p-2 font-mono text-secondary">{review.created_at ?? '—'}</td>
        </tr>)}</tbody>
      </table>
    </div>
  </section>
}

function ObservationPlans({
  plans,
  onRecorded,
}: Pick<AnalysisSignalHistory, 'plans'> & { onRecorded: () => Promise<unknown> }) {
  if (!plans.length) return null
  return <section aria-labelledby="observation-plans-heading" className="space-y-2">
    <h3 id="observation-plans-heading" className="text-base font-semibold text-foreground">观察计划与结果</h3>
    {plans.map(plan => <ObservationPlan key={plan.id} plan={plan} onRecorded={onRecorded} />)}
  </section>
}

function ObservationPlan({
  plan,
  onRecorded,
}: {
  plan: AnalysisObservationPlan
  onRecorded: () => Promise<unknown>
}) {
  const [capturing, setCapturing] = useState(false)
  const [status, setStatus] = useState<AnalysisObservationOutcomeInput['status']>('complete')
  const [observedValue, setObservedValue] = useState('')
  const [notes, setNotes] = useState('')
  const record = useMutation({
    mutationFn: (payload: AnalysisObservationOutcomeInput) => api.analysisRecordOutcome(plan.id, payload),
    onSuccess: async () => {
      setCapturing(false)
      setObservedValue('')
      setNotes('')
      await onRecorded()
    },
  })

  const submit = () => {
    const parsed = observedValue.trim() === '' ? null : Number(observedValue)
    if (parsed !== null && !Number.isFinite(parsed)) return
    record.mutate({
      status,
      observed_value: parsed,
      notes: notes.trim(),
    })
  }

  return <div
    role="region"
    aria-label={`${plan.window_days} 个交易日观察计划`}
    className="rounded-btn border border-border bg-base p-3"
  >
    <div className="flex flex-wrap items-start justify-between gap-2">
      <div>
        <p className="text-sm font-semibold text-foreground">{plan.window_days} 个交易日观察计划</p>
        <p className="mt-1 text-sm text-secondary">基准：{plan.benchmark}；评估指标：{plan.metric}</p>
      </div>
      <button
        type="button"
        onClick={() => setCapturing(value => !value)}
        className="min-h-11 rounded-btn border border-border px-3 text-sm font-medium text-secondary focus:ring-2 focus:ring-accent"
        aria-expanded={capturing}
      >
        {capturing ? '取消记录' : '记录观察结果'}
      </button>
    </div>
    {plan.outcomes.length
      ? <ul aria-label="观察结果历史" className="mt-2 space-y-1 text-sm text-secondary">
        {plan.outcomes.map(outcome => <li key={outcome.id} className="break-words">
          {outcome.outcome.status === 'complete' ? '完整结果' : '不完整结果'}：
          {outcome.outcome.observed_value ?? '—'}；{outcome.outcome.notes ?? '无备注'}
          {' '}<span className="font-mono text-muted">{outcome.observed_at}</span>
        </li>)}
      </ul>
      : <p className="mt-2 text-sm text-warning">结果待观察</p>}
    {capturing && <form
      aria-label={`${plan.window_days} 个交易日观察结果录入`}
      className="mt-3 grid gap-3 rounded-btn border border-border bg-surface p-3 sm:grid-cols-2"
      onSubmit={event => {
        event.preventDefault()
        submit()
      }}
    >
      <label className="space-y-1 text-sm text-secondary">
        <span className="block">结果状态</span>
        <select
          value={status}
          onChange={event => setStatus(event.target.value as AnalysisObservationOutcomeInput['status'])}
          className="min-h-11 w-full rounded-btn border border-border bg-base px-3 text-foreground"
        >
          <option value="complete">完整</option>
          <option value="incomplete">不完整</option>
        </select>
      </label>
      <label className="space-y-1 text-sm text-secondary">
        <span className="block">观察值（可选）</span>
        <input
          type="number"
          step="any"
          value={observedValue}
          onChange={event => setObservedValue(event.target.value)}
          className="min-h-11 w-full rounded-btn border border-border bg-base px-3 font-mono text-foreground"
        />
      </label>
      <label className="space-y-1 text-sm text-secondary sm:col-span-2">
        <span className="block">结果备注</span>
        <textarea
          value={notes}
          onChange={event => setNotes(event.target.value)}
          maxLength={1000}
          rows={3}
          className="w-full rounded-btn border border-border bg-base px-3 py-2 text-foreground"
        />
      </label>
      {record.isError && <p role="alert" className="text-sm text-danger sm:col-span-2">观察结果保存失败，请重试。</p>}
      <button
        type="submit"
        disabled={record.isPending}
        className="min-h-11 rounded-btn bg-accent px-3 text-sm font-semibold text-white disabled:opacity-50 sm:col-span-2 sm:justify-self-start"
      >
        {record.isPending ? '正在保存结果' : '保存观察结果'}
      </button>
    </form>}
  </div>
}
