import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, ClipboardList, CheckCircle2, XCircle, Clock, ThumbsUp, ThumbsDown } from 'lucide-react'
import { api, type RebalancePlanDTO } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { toast } from '@/components/Toast'

const TRANSITION_LABEL: Record<string, string> = {
  suggested: '建议',
  approved: '已审批',
  rejected: '已驳回',
  filled: '已记录',
}

function stateMeta(state: string | null): { label: string; className: string; dot: string } {
  switch (state) {
    case 'approved':
      return { label: '已审批', className: 'text-foreground border-border bg-elevated', dot: 'bg-foreground' }
    case 'rejected':
      return { label: '已驳回', className: 'text-danger border-danger/30 bg-danger/10', dot: 'bg-danger' }
    case 'filled':
      return { label: '已记录', className: 'text-secondary border-border bg-elevated', dot: 'bg-muted' }
    case 'suggested':
    case null:
    default:
      return { label: state === null ? '待审批' : '建议', className: 'text-accent border-accent/30 bg-accent/10', dot: 'bg-accent' }
  }
}

function fmtPct(v: number): string {
  return `${(v * 100).toFixed(2)}%`
}

export function RebalancePlan() {
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const listQuery = useQuery({
    queryKey: QK.rebalancePlans(undefined),
    queryFn: () => api.listRebalancePlans(),
  })

  const plans = listQuery.data ?? []

  return (
    <>
      <PageHeader
        title="再平衡计划"
        subtitle="不可变计划 · 目标 vs 离散权重 · 纸面审批台账（只读审计,无下单）"
      />

      <div className="px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
          {/* Plan list */}
          <section className="rounded-card border border-border bg-surface">
            <div className="border-b border-border px-3 py-2 text-xs font-semibold text-secondary">
              再平衡计划 {listQuery.data ? `(${listQuery.data.length})` : ''}
            </div>
            <div className="max-h-[calc(100vh-16rem)] overflow-auto p-2 space-y-1">
              {listQuery.isLoading && <div className="px-3 py-6 text-center text-xs text-muted">加载中…</div>}
              {listQuery.isError && !listQuery.data && (
                <div role="alert" className="rounded-btn border border-danger/30 bg-danger/10 px-3 py-3 text-xs text-danger">
                  再平衡计划加载失败：{listQuery.error instanceof Error ? listQuery.error.message : String(listQuery.error ?? '未知错误')}
                  <button type="button" onClick={() => listQuery.refetch()} className="ml-2 inline-flex items-center rounded-btn border border-danger/30 bg-danger/10 px-2 py-1 text-xs font-medium text-danger hover:bg-danger/20 max-md:min-h-11 max-md:min-w-11">重试</button>
                </div>
              )}
              {listQuery.data?.length === 0 && (
                <EmptyState icon={ClipboardList} title="暂无再平衡计划" hint="对优化权重做离散化后,计划会出现在这里。" />
              )}
              {plans.map(plan => (
                <PlanListItem
                  key={plan.id}
                  plan={plan}
                  active={selectedId === plan.id}
                  onClick={() => setSelectedId(plan.id)}
                />
              ))}
            </div>
          </section>

          {/* Plan detail */}
          <section className="min-w-0">
            {!selectedId ? (
              <div className="flex items-center justify-center rounded-card border border-border bg-surface py-20">
                <div className="text-center">
                  <ClipboardList className="mx-auto h-8 w-8 text-muted/40" />
                  <p className="mt-3 text-sm text-secondary">选择左侧计划查看权重与审批台账</p>
                  <p className="mt-1 text-xs text-muted">目标/离散权重、手数、现金残差与纸面状态机</p>
                </div>
              </div>
            ) : (
              <PlanDetail key={selectedId} planId={selectedId} />
            )}
          </section>
        </div>
      </div>
    </>
  )
}

function PlanListItem({ plan, active, onClick }: { plan: RebalancePlanDTO; active: boolean; onClick: () => void }) {
  // 列表不实时拉取 paper 状态 — 状态断言只在详情页展示, 避免列表显示误导性的
  // "待审批"(实际可能已审批/驳回)。这里只给一个中性的 paper 审计入口指示。
   return (
     <button
       onClick={onClick}
       className={`w-full rounded-lg px-3 py-2 text-left transition-colors ${active ? 'bg-accent/10 border border-accent/25' : 'border border-transparent hover:bg-elevated/60'}`}
     >
       <div className="flex items-center justify-between gap-2">
         <span className="truncate text-xs font-medium text-foreground">{plan.id}</span>
        <span className="shrink-0 rounded border border-border bg-elevated px-1 py-px text-[9px] font-medium text-muted">paper 审计</span>
       </div>
       <div className="mt-1 flex items-center gap-2 text-[10px] text-muted">
         <span className="font-mono">{plan.as_of}</span>
         <span>·</span>
         <span>RMSE {plan.discretization_rmse.toExponential(2)}</span>
       </div>
       <div className="mt-0.5 flex items-center gap-2 text-[10px]">
         <span className="rounded border border-border bg-elevated px-1 py-px font-medium text-secondary">到期 {plan.expires_at.slice(0, 10)}</span>
       </div>
     </button>
   )
 }

function PlanDetail({ planId }: { planId: string }) {
  const qc = useQueryClient()
  const [expanded, setExpanded] = useState<'blocked' | 'lots' | null>(null)

  const planQuery = useQuery({
    queryKey: ['rebalance-plan', planId],
    queryFn: () => api.listRebalancePlans().then(rows => rows.find(r => r.id === planId) ?? null),
  })
  const paperQuery = useQuery({
    queryKey: QK.paperState(planId),
    queryFn: () => api.getPaperState(planId),
  })

  const invalidatePaper = () => qc.invalidateQueries({ queryKey: QK.paperState(planId) })

  const approve = useMutation({
    mutationFn: () => api.approveRebalance(planId, `paper-approve-${planId}`),
    onSuccess: result => { toast(result.idempotent ? '审批已记录（幂等重放）' : '已审批', 'success'); invalidatePaper() },
    onError: () => toast('审批失败', 'error'),
  })
  const reject = useMutation({
    mutationFn: () => api.rejectRebalance(planId, `paper-reject-${planId}`),
    onSuccess: result => { toast(result.idempotent ? '驳回已记录（幂等重放）' : '已驳回', 'success'); invalidatePaper() },
    onError: () => toast('驳回失败', 'error'),
  })

  if (planQuery.isLoading || !planQuery.data) {
    return <div className="rounded-card border border-border bg-surface p-6 text-center text-sm text-muted">加载计划详情…</div>
  }
  const plan = planQuery.data
  const state = paperQuery.data?.current_state ?? null
  const meta = stateMeta(state)
  // 审批/驳回仅在"未决"阶段(无转移或 suggested)可用 —— 一旦 approved/rejected 即冻结。
  const actionable = state === null || state === 'suggested'
  const transitions = paperQuery.data?.transitions ?? []

  const target = plan.target_weights ?? {}
  const discrete = plan.discrete_weights ?? {}
  const symbols = Array.from(new Set([...Object.keys(target), ...Object.keys(discrete)])).sort()

  const toggle = (key: 'blocked' | 'lots') => setExpanded(prev => prev === key ? null : key)

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="rounded-card border border-border bg-surface p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="font-mono text-sm font-semibold text-foreground">{plan.id}</h2>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
              <span>截至 {plan.as_of}</span>
              <span>·</span>
              <span className="font-mono">run {plan.optimization_run_id}</span>
              <span>·</span>
              <span>到期 {plan.expires_at}</span>
            </div>
          </div>
          <div className="text-right">
            <div className="font-mono text-[10px] text-muted">output_sha256</div>
            <div className="font-mono text-[10px] text-secondary">{plan.output_sha256.slice(0, 16)}…</div>
          </div>
        </div>
      </div>

      {/* Paper state machine — audit ledger, never a live order path */}
      <div className="rounded-card border border-border bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 rounded border px-2 py-1 text-xs font-medium ${meta.className}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
              {meta.label}
            </span>
            <span className="text-[10px] text-muted">纸面状态机 · 仅审计,不可下单</span>
          </div>
          {actionable && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => approve.mutate()}
                disabled={approve.isPending}
                className="inline-flex min-h-8 items-center gap-1.5 rounded-btn border border-accent/40 bg-accent/10 px-3 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
              >
                <ThumbsUp className="h-3.5 w-3.5" />
                {approve.isPending ? '记录中…' : '审批'}
              </button>
              <button
                onClick={() => reject.mutate()}
                disabled={reject.isPending}
                className="inline-flex min-h-8 items-center gap-1.5 rounded-btn border border-danger/40 bg-danger/10 px-3 text-xs font-medium text-danger transition-colors hover:bg-danger/20 disabled:opacity-50"
              >
                <ThumbsDown className="h-3.5 w-3.5" />
                {reject.isPending ? '记录中…' : '驳回'}
              </button>
            </div>
          )}
        </div>

        {/* Append-only transition ledger */}
        <div className="mt-3">
          <div className="text-[10px] font-medium text-muted">状态转移台账（append-only）</div>
          {transitions.length === 0 ? (
            <p className="mt-2 text-xs text-muted">暂无转移记录 —— 计划处于待审批状态。</p>
          ) : (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-[10px] text-muted">
                  <tr>
                    <th className="px-2 py-1 font-medium">转移</th>
                    <th className="px-2 py-1 font-medium">前一状态</th>
                    <th className="px-2 py-1 font-medium">幂等键</th>
                    <th className="px-2 py-1 font-medium">时间</th>
                  </tr>
                </thead>
                <tbody>
                  {transitions.map(t => (
                    <tr key={t.id} className="border-t border-border/50">
                      <td className="px-2 py-1.5">
                        <TransitionBadge transition={t.transition} />
                      </td>
                      <td className="px-2 py-1.5 text-secondary">{t.previous_state ? TRANSITION_LABEL[t.previous_state] ?? t.previous_state : '—'}</td>
                      <td className="px-2 py-1.5 font-mono text-muted">{t.idempotency_key}</td>
                      <td className="px-2 py-1.5 font-mono text-muted">{t.created_at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Target vs discrete weights */}
      <div className="rounded-card border border-border bg-surface p-4">
        <h3 className="text-sm font-semibold text-foreground">权重：目标 vs 离散</h3>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-[10px] text-muted">
              <tr>
                <th className="px-2 py-1 font-medium">标的</th>
                <th className="px-2 py-1 text-right font-medium">目标</th>
                <th className="px-2 py-1 text-right font-medium">离散</th>
                <th className="px-2 py-1 text-right font-medium">偏差</th>
              </tr>
            </thead>
            <tbody>
              {symbols.map(symbol => {
                const t = typeof target[symbol] === 'number' ? (target[symbol] as number) : null
                const d = typeof discrete[symbol] === 'number' ? (discrete[symbol] as number) : null
                const delta = t !== null && d !== null ? d - t : null
                return (
                  <tr key={symbol} className="border-t border-border/50">
                    <td className="px-2 py-1.5 font-mono text-secondary">{symbol}</td>
                    <td className="px-2 py-1.5 text-right font-mono tabular-nums text-foreground">{t !== null ? fmtPct(t) : '—'}</td>
                    <td className="px-2 py-1.5 text-right font-mono tabular-nums text-foreground">{d !== null ? fmtPct(d) : '—'}</td>
                    <td className={`px-2 py-1.5 text-right font-mono tabular-nums ${delta !== null && delta < 0 ? 'text-bear' : delta !== null && delta > 0 ? 'text-bull' : 'text-muted'}`}>
                      {delta !== null ? fmtPct(delta) : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Discretization metrics */}
      <div className="rounded-card border border-border bg-surface p-4">
        <h3 className="text-sm font-semibold text-foreground">离散化指标</h3>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Metric label="现金残差" value={plan.cash_residue.toExponential(2)} />
          <Metric label="换手成本" value={plan.turnover_cost.toExponential(2)} />
          <Metric label="离散 RMSE" value={plan.discretization_rmse.toExponential(2)} />
          <Metric label="RMSE 定义" value={plan.rmse_definition} />
        </div>
      </div>

      {/* Expandable: lot sizes + blocked instruments */}
      <div className="space-y-2">
        <ExpandableSection title="手数（lot sizes）" expanded={expanded === 'lots'} onClick={() => toggle('lots')}>
          <pre className="overflow-x-auto whitespace-pre-wrap break-words text-[11px] text-secondary">{JSON.stringify(plan.lot_sizes ?? {}, null, 2)}</pre>
        </ExpandableSection>
        <ExpandableSection title={`受限标的（blocked）${plan.blocked_instruments && Object.keys(plan.blocked_instruments).length ? ` · ${Object.keys(plan.blocked_instruments).length}` : ''}`} expanded={expanded === 'blocked'} onClick={() => toggle('blocked')}>
          <pre className="overflow-x-auto whitespace-pre-wrap break-words text-[11px] text-secondary">{JSON.stringify(plan.blocked_instruments ?? {}, null, 2)}</pre>
        </ExpandableSection>
      </div>

      <div className="text-[10px] text-muted">
        input_snapshot: <span className="font-mono">{plan.input_snapshot_sha256.slice(0, 16)}…</span>
        {plan.artifact_relative_path && (
          <>
            {' · '}
            artifact: <span className="font-mono">{plan.artifact_relative_path}</span>
          </>
        )}
      </div>
    </div>
  )
}

function TransitionBadge({ transition }: { transition: string }) {
  const icon = transition === 'approved' ? <CheckCircle2 className="h-3 w-3 text-foreground" />
    : transition === 'rejected' ? <XCircle className="h-3 w-3 text-danger" />
    : <Clock className="h-3 w-3 text-muted" />
  return (
    <span className="inline-flex items-center gap-1 text-secondary">
      {icon}
      {TRANSITION_LABEL[transition] ?? transition}
    </span>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-btn border border-border bg-elevated/40 px-3 py-2">
      <div className="text-[10px] text-muted">{label}</div>
      <div className="mt-1 font-mono text-sm font-semibold text-foreground tabular-nums">{value}</div>
    </div>
  )
}

function ExpandableSection({ title, expanded, onClick, children }: { title: string; expanded: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-border bg-surface">
      <button onClick={onClick} className="flex min-h-11 w-full items-center gap-2 px-3 text-left text-xs font-medium text-foreground hover:bg-elevated/40 transition-colors">
        {expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted" />}
        {title}
      </button>
      {expanded && <div className="border-t border-border px-3 py-3">{children}</div>}
    </div>
  )
}
