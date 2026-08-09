import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bot, Check, CircleAlert, Clock3, RefreshCw, ShieldCheck, Sparkles } from 'lucide-react'
import { Modal } from '@/components/Modal'
import { Skeleton } from '@/components/data/Skeleton'
import {
  api,
  type AdjustmentAudit,
  type DecisionReviewResult,
  type DecisionRun,
  type DecisionRunInput,
  type HistoricalReplay,
  type PlaybookSnapshot,
} from '@/lib/api'
import { QK } from '@/lib/queryKeys'

const AUDIT_FIELDS = [
  { key: 'entry', label: '入场区间' },
  { key: 'stop', label: '止损' },
  { key: 'target1', label: '目标 1' },
  { key: 'target2', label: '目标 2' },
  { key: 'position_pct', label: '仓位' },
  { key: 'action', label: '动作 / 理由' },
] as const

const AUDIT_FIELD_LABELS: Record<string, string> = {
  entry_low: '入场下限',
  entry_high: '入场上限',
  stop: '止损',
  target1: '目标 1',
  target2: '目标 2',
  position_pct: '仓位',
  action: '动作',
  score: '评分',
  risk_reward: '风险收益',
}

const AUDIT_STATUS: Record<AdjustmentAudit['disposition'], { label: string; className: string }> = {
  applied: { label: '已应用', className: 'text-emerald-500' },
  clamped: { label: '已钳制', className: 'text-warning' },
  rejected: { label: '已拒绝', className: 'text-danger' },
}

function price(value: number) {
  return Number.isFinite(value) ? value.toFixed(2) : '—'
}

function valueFor(snapshot: PlaybookSnapshot, key: string) {
  if (key === 'entry') return `${price(snapshot.entry_low)} – ${price(snapshot.entry_high)}`
  if (key === 'position_pct') return `${(snapshot.position_pct * 100).toFixed(1)}%`
  if (key === 'action') {
    return `${snapshot.action} · ${Object.values(snapshot.reason_snapshot).filter(Boolean).join('；') || '—'}`
  }
  const value = snapshot[key as keyof PlaybookSnapshot]
  return typeof value === 'number' ? price(value) : String(value ?? '—')
}

function ReplayResult({ replay }: { replay: HistoricalReplay }) {
  return <div className="mt-3 rounded-btn border border-border bg-base/50 p-3 text-xs">
    <div className="flex items-center gap-1 text-emerald-500">
      <Check className="h-3.5 w-3.5" />已完成 AI 禁用的历史回放
    </div>
    <dl className="mt-2 grid gap-1 text-muted">
      <div>
        <dt className="inline">回放时间：</dt>
        <dd className="inline font-mono text-secondary">{new Date(replay.created_at).toLocaleString('zh-CN')}</dd>
      </div>
      <div>
        <dt className="inline">数据截至：</dt>
        <dd className="inline font-mono text-secondary">{replay.as_of}</dd>
      </div>
      <div>
        <dt className="inline">结果哈希：</dt>
        <dd className="inline break-all font-mono text-secondary">{replay.result_hash}</dd>
      </div>
    </dl>
  </div>
}

function ReviewAndApply({
  run,
  review,
  applying,
  reviewResult,
  onReview,
  onApply,
}: {
  run: DecisionRun
  review: { pending: boolean; error: boolean }
  applying: { pending: boolean; error: boolean }
  reviewResult?: DecisionReviewResult
  onReview: () => void
  onApply: () => void
}) {
  const proposal = run.proposal
  const applied = run.adjustments.length > 0

  return <section aria-labelledby="ai-review-heading" className="rounded-card border border-border bg-base/40 p-3">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 id="ai-review-heading" className="flex items-center gap-1 text-sm font-semibold text-foreground">
          <Bot className="h-4 w-4 text-accent" />AI 辅助审阅
        </h3>
        <p className="mt-1 text-xs text-muted">AI 只能提出数值建议，不会自动改变确定性计划。</p>
      </div>
      <button
        type="button"
        onClick={onReview}
        disabled={review.pending || Boolean(proposal) || applied}
        className="inline-flex min-h-11 items-center gap-1 rounded-btn border border-accent/50 px-3 text-sm font-medium text-accent disabled:opacity-50"
      >
        <Sparkles className="h-4 w-4" />
        {review.pending ? '正在请求 AI 审阅' : proposal ? '已取得 AI 提案' : '请求 AI 审阅'}
      </button>
    </div>
    {review.error && <p role="alert" className="mt-2 text-sm text-danger">AI 审阅请求失败，确定性计划保持不变。</p>}
    {reviewResult?.review_status === 'unavailable' && !proposal && <p className="mt-2 text-sm text-warning">
      AI 审阅当前不可用，确定性计划保持不变。
    </p>}
    {proposal && <div className="mt-3 rounded-btn border border-warning/50 bg-warning/10 p-3" aria-label="尚未应用的 AI 调整提案">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-warning">尚未应用的 AI 调整提案</p>
        <span className="font-mono text-xs text-muted">{proposal.provider} / {proposal.model}</span>
      </div>
      <ul className="mt-2 space-y-2">
        {proposal.adjustments.map((adjustment, index) => <li
          key={`${adjustment.field}-${index}`}
          className="rounded-btn border border-border bg-base/60 px-3 py-2 text-xs"
        >
          <span className="font-mono font-semibold text-foreground">{adjustment.field}</span>
          <span className="ml-2 font-mono text-secondary">→ {adjustment.value}</span>
          <p className="mt-1 break-words text-muted">{adjustment.rationale || '未提供理由'}</p>
        </li>)}
      </ul>
      {!applied && <div className="mt-3">
        <p className="mb-2 text-xs text-warning">需要你显式确认。服务端会逐项应用、钳制或拒绝，AI 没有最终决定权。</p>
        <button
          type="button"
          onClick={onApply}
          disabled={applying.pending || !proposal.adjustments.length}
          className="min-h-11 rounded-btn bg-accent-solid px-3 text-sm font-semibold text-white disabled:opacity-50"
        >
          {applying.pending ? '正在执行受限校验' : '应用受限调整'}
        </button>
      </div>}
      {applying.error && <p role="alert" className="mt-2 text-sm text-danger">受限调整未应用，最终计划保持不变。</p>}
    </div>}
    {applied && <p className="mt-3 flex items-center gap-1 text-sm text-emerald-500">
      <Check className="h-4 w-4" />用户已提交提案，服务端受限校验结果见下方审计。
    </p>}
  </section>
}

function PlaybookDetails({
  run,
  replay,
  replaying,
  replayError,
  replayAsOf,
  setReplayAsOf,
  onReplay,
  review,
  applying,
  reviewResult,
  onReview,
  onApply,
}: {
  run: DecisionRun
  replay?: HistoricalReplay
  replaying: boolean
  replayError: boolean
  replayAsOf: string
  setReplayAsOf: (value: string) => void
  onReplay: () => void
  review: { pending: boolean; error: boolean }
  applying: { pending: boolean; error: boolean }
  reviewResult?: DecisionReviewResult
  onReview: () => void
  onApply: () => void
}) {
  return <div className="space-y-5">
    <section className="grid grid-cols-1 gap-2 border-b border-border pb-4 text-xs text-muted sm:grid-cols-4">
      <div><span className="block">计划 ID</span><span className="break-all font-mono text-secondary">{run.id}</span></div>
      <div><span className="block">数据截至</span><span className="font-mono text-secondary">{run.data_as_of}</span></div>
      <div><span className="block">引擎版本</span><span className="font-mono text-secondary">{run.engine_config_version}</span></div>
      <div><span className="block">计划标的</span><span className="font-mono text-secondary">{run.symbol}</span></div>
    </section>
    <ReviewAndApply
      run={run}
      review={review}
      applying={applying}
      reviewResult={reviewResult}
      onReview={onReview}
      onApply={onApply}
    />
    <section>
      <h3 className="text-sm font-semibold text-foreground">确定性基线与最终计划</h3>
      <div className="mt-2 overflow-hidden rounded-card border border-border">
        <div className="grid grid-cols-[minmax(5rem,1fr)_minmax(0,1.4fr)_minmax(0,1.4fr)] border-b border-border bg-elevated/50 px-3 py-2 text-xs font-medium text-muted">
          <span>字段</span><span>确定性基线</span><span>最终计划</span>
        </div>
        {AUDIT_FIELDS.map(field => <div
          key={field.key}
          className="grid grid-cols-[minmax(5rem,1fr)_minmax(0,1.4fr)_minmax(0,1.4fr)] gap-2 border-b border-border/60 px-3 py-2 text-xs last:border-0"
        >
          <span className="text-muted">{field.label}</span>
          <span className="min-w-0 break-words font-mono text-secondary">{valueFor(run.baseline, field.key)}</span>
          <span className="min-w-0 break-words font-mono text-foreground">{valueFor(run.final, field.key)}</span>
        </div>)}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 rounded-btn bg-base/50 px-3 py-2 text-xs text-muted">
        <span>确定性动作 <strong className="font-mono text-foreground">{run.baseline.action}</strong></span>
        <span>评分 <strong className="font-mono text-foreground">{run.baseline.score}</strong></span>
        <span>风险收益 <strong className="font-mono text-foreground">{run.baseline.risk_reward}</strong></span>
      </div>
    </section>
    <section>
      <h3 className="text-sm font-semibold text-foreground">字段调整审计</h3>
      <div className="mt-2 space-y-2">
        {run.adjustments.length === 0
          ? <p className="rounded-btn border border-border px-3 py-2 text-xs text-muted">尚无已提交的字段调整审计。</p>
          : run.adjustments.map((adjustment, index) => {
            const status = AUDIT_STATUS[adjustment.disposition]
            return <div
              key={`${adjustment.field}-${index}`}
              aria-label={`调整审计 ${adjustment.field}`}
              className="rounded-btn border border-border px-3 py-2 text-xs"
            >
          <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-secondary">
                  {AUDIT_FIELD_LABELS[adjustment.field] ?? adjustment.field}
                  <span className="ml-1 font-mono text-muted">({adjustment.field})</span>
                </span>
                <span className={status.className}>{status.label}</span>
          </div>
              <p className="mt-1 break-words text-muted">
            {adjustment.rationale || '未提供调整理由'}
            {adjustment.proposed_value != null && ` · 提议 ${adjustment.proposed_value}`}
            {adjustment.final_value != null && ` · 最终 ${adjustment.final_value}`}
              </p>
        </div>
          })}
      </div>
    </section>
    <section className="border-t border-border pt-4">
      <h3 className="text-sm font-semibold text-foreground">历史回放</h3>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <label className="space-y-1 text-xs text-muted">
          <span className="block">数据截至</span>
          <input
            type="date"
            aria-label="历史回放数据截至"
            value={replayAsOf}
            onChange={event => setReplayAsOf(event.target.value)}
            max={run.data_as_of}
            className="min-h-11 rounded-btn border border-border bg-base px-2 font-mono text-xs text-foreground"
          />
        </label>
        <button
          type="button"
          disabled={!replayAsOf || replaying}
          onClick={onReplay}
          className="inline-flex min-h-11 items-center gap-1 rounded-btn bg-accent px-3 text-xs font-medium text-base disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${replaying ? 'animate-spin' : ''}`} />
          {replaying ? '正在以历史数据回放；AI 已禁用' : '运行历史回放'}
        </button>
      </div>
      {replaying && <p className="mt-2 flex items-center gap-1 text-xs text-muted">
        <Clock3 className="h-3.5 w-3.5" />正在以历史数据回放；AI 已禁用
      </p>}
      {replayError && <div role="alert" className="mt-2 rounded-btn border border-danger/50 bg-danger/10 p-3 text-sm text-danger">
        <p>历史回放失败；数据截至仍保留为 <span className="font-mono">{replayAsOf}</span>。</p>
        <button
          type="button"
          onClick={onReplay}
          disabled={replaying}
          className="mt-2 min-h-11 rounded-btn border border-danger/50 px-3 text-sm font-semibold disabled:opacity-50"
        >
          重试历史回放
        </button>
      </div>}
      {replay && <ReplayResult replay={replay} />}
    </section>
  </div>
}

export function PlaybookInspector({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient()
  const [runIdInput, setRunIdInput] = useState('')
  const [runId, setRunId] = useState('')
  const runIdRef = useRef('')
  const transitionRef = useRef(0)
  const [transitionId, setTransitionId] = useState(0)
  const [symbol, setSymbol] = useState('')
  const [asOf, setAsOf] = useState('')
  const [replayAsOf, setReplayAsOf] = useState('')
  const playbook = useQuery({
    queryKey: QK.decisionPlaybook(runId),
    queryFn: () => api.decisionRun(runId),
    enabled: Boolean(runId),
  })
  const generate = useMutation({
    mutationFn: (payload: DecisionRunInput) => api.decisionGenerate(payload),
    onSuccess: generated => {
      queryClient.setQueryData(QK.decisionPlaybook(generated.id), generated)
      setRunIdInput(generated.id)
      transitionToRun(generated.id, generated.data_as_of)
    },
  })
  const review = useMutation({
    mutationFn: ({ runId: requestedRunId }: { runId: string; transitionId: number }) =>
      api.decisionReview(requestedRunId),
    onSuccess: async (_result, variables) => {
      const refreshed = await api.decisionRun(variables.runId)
      if (
        runIdRef.current !== variables.runId
        || transitionRef.current !== variables.transitionId
      ) return
      queryClient.setQueryData(QK.decisionPlaybook(variables.runId), refreshed)
    },
  })
  const apply = useMutation({
    mutationFn: ({
      runId: requestedRunId,
      run,
    }: {
      runId: string
      transitionId: number
      run: DecisionRun
    }) => {
      const proposal = Object.fromEntries(
        (run.proposal?.adjustments ?? []).map(adjustment => [
          adjustment.field,
          { value: adjustment.value, rationale: adjustment.rationale },
        ]),
      )
      return api.decisionAdjustments(requestedRunId, proposal)
    },
    onSuccess: (adjusted, variables) => {
      if (
        runIdRef.current !== variables.runId
        || transitionRef.current !== variables.transitionId
      ) return
      queryClient.setQueryData(QK.decisionPlaybook(adjusted.id), adjusted)
    },
  })
  const replay = useMutation({
    mutationFn: ({
      runId: requestedRunId,
      asOf: requestedAsOf,
    }: {
      runId: string
      asOf: string
      transitionId: number
    }) => api.decisionReplay([requestedRunId], requestedAsOf),
  })
  const current = playbook.data

  function transitionToRun(nextRunId: string, cutoff = '') {
    const next = nextRunId.trim()
    const nextTransitionId = transitionRef.current + 1
    runIdRef.current = next
    transitionRef.current = nextTransitionId
    setTransitionId(nextTransitionId)
    setRunId(next)
    setReplayAsOf(cutoff)
    review.reset()
    apply.reset()
    replay.reset()
  }

  const mutationMatchesRun = (
    variables: { runId: string; transitionId: number } | undefined,
    expectedRunId: string,
  ) => variables?.runId === expectedRunId && variables.transitionId === transitionId

  const selectRun = (id: string) => transitionToRun(id)

  return <Modal
    onClose={onClose}
    ariaLabel="决策计划"
    panelClassName="w-[calc(100vw-32px)] max-w-4xl max-h-[90vh] overflow-auto rounded-dialog border border-border bg-surface shadow-xl"
  >
    <div className="sticky top-0 z-10 border-b border-border bg-surface px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-foreground">决策计划</h2>
          <p className="mt-1 text-xs text-muted">先生成确定性计划；AI 只提议，用户显式应用后才能改变最终计划。</p>
        </div>
        <ShieldCheck className="h-5 w-5 shrink-0 text-accent" />
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        <form
          aria-label="生成决策计划"
          onSubmit={event => {
            event.preventDefault()
            generate.mutate({ symbol: symbol.trim(), as_of: asOf })
          }}
          className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 rounded-btn border border-border p-2"
        >
          <label className="space-y-1 text-xs text-muted">
            <span className="block">标的代码</span>
            <input
              value={symbol}
              onChange={event => setSymbol(event.target.value)}
              placeholder="600519.SH"
              className="min-h-11 w-full rounded-btn border border-border bg-base px-3 font-mono text-xs text-foreground"
            />
          </label>
          <label className="space-y-1 text-xs text-muted">
            <span className="block">数据截至</span>
            <input
              type="date"
              value={asOf}
              onChange={event => setAsOf(event.target.value)}
              className="min-h-11 rounded-btn border border-border bg-base px-2 font-mono text-xs text-foreground"
            />
          </label>
          <button
            type="submit"
            disabled={!symbol.trim() || !asOf || generate.isPending}
            className="min-h-11 rounded-btn bg-accent px-3 text-xs font-medium text-base disabled:opacity-50 col-span-2"
          >
            {generate.isPending ? '正在生成确定性计划' : '生成确定性计划'}
          </button>
          {generate.isError && <p role="alert" className="col-span-2 text-xs text-danger">无法生成决策计划，请检查标的和数据日期。</p>}
        </form>
        <form
          aria-label="打开已保存决策计划"
          onSubmit={event => {
            event.preventDefault()
            selectRun(runIdInput)
          }}
          className="flex items-end gap-2 rounded-btn border border-border p-2"
        >
          <label className="min-w-0 flex-1 space-y-1 text-xs text-muted" htmlFor="decision-run-id">
            <span className="block">已保存计划 ID</span>
            <input
              id="decision-run-id"
              value={runIdInput}
              onChange={event => setRunIdInput(event.target.value)}
              placeholder="输入已保存的决策计划 ID"
              className="min-h-11 w-full rounded-btn border border-border bg-base px-3 font-mono text-xs text-foreground"
            />
          </label>
          <button
            type="submit"
            disabled={!runIdInput.trim()}
            className="min-h-11 rounded-btn border border-border px-3 text-xs font-medium text-secondary disabled:opacity-50"
          >
            查看
          </button>
        </form>
      </div>
    </div>
    <div className="p-4">
      {!runId
        ? <div className="py-8 text-center">
          <CircleAlert className="mx-auto h-5 w-5 text-muted" />
          <h3 className="mt-2 text-sm font-medium text-foreground">尚未选择决策计划</h3>
          <p className="mt-1 text-xs text-muted">输入标的与日期生成计划，或打开一个已保存的计划。</p>
        </div>
        : playbook.isLoading && !current
          ? <div className="space-y-3">{Array.from({ length: 6 }, (_, index) => <Skeleton key={index} h="h-10" rounded="rounded-btn" />)}</div>
          : playbook.isError
            ? <div className="space-y-3">
              <p className="text-sm text-danger">无法读取决策计划。请检查数据状态后重新加载决策计划。</p>
              <button onClick={() => playbook.refetch()} className="rounded-btn bg-accent px-3 py-2 text-xs font-medium text-base">重新加载决策计划</button>
            </div>
            : current
              ? (() => {
                const reviewMatches = mutationMatchesRun(review.variables, current.id)
                const applyMatches = mutationMatchesRun(apply.variables, current.id)
                const replayMatches = mutationMatchesRun(replay.variables, current.id)
                const replayCutoff = replayAsOf || current.data_as_of
                return <PlaybookDetails
                run={current}
                  replay={replayMatches ? replay.data : undefined}
                  replaying={replayMatches && replay.isPending}
                  replayError={replayMatches && replay.isError}
                  replayAsOf={replayCutoff}
                setReplayAsOf={setReplayAsOf}
                  onReplay={() => replay.mutate({
                    runId: current.id,
                    asOf: replayCutoff,
                    transitionId,
                  })}
                  review={{
                    pending: reviewMatches && review.isPending,
                    error: reviewMatches && review.isError,
                  }}
                  applying={{
                    pending: applyMatches && apply.isPending,
                    error: applyMatches && apply.isError,
                  }}
                  reviewResult={reviewMatches ? review.data : undefined}
                  onReview={() => review.mutate({
                    runId: current.id,
                    transitionId,
                  })}
                  onApply={() => apply.mutate({
                    runId: current.id,
                    transitionId,
                    run: current,
                  })}
              />
              })()
              : null}
    </div>
  </Modal>
}
