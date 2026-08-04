import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, FlaskConical, GitBranch, CheckCircle2 } from 'lucide-react'
import { api, type WfPlanDTO, type WfFoldDTO, type WfSearchRunDTO, type WfValidatedStrategyDTO, type WfEnsembleDTO } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'

export function WalkForward() {
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null)

  const plansQuery = useQuery({
    queryKey: QK.panelWfPlans(),
    queryFn: () => api.listWfPlans(),
  })

  const selectedPlan = plansQuery.data?.find(plan => plan.id === selectedPlanId) ?? plansQuery.data?.[0] ?? null
  const activePlanId = selectedPlan?.id

  const foldsQuery = useQuery({
    queryKey: QK.panelWfFolds(activePlanId ?? undefined),
    queryFn: () => api.listWfFolds({ plan_id: activePlanId ?? undefined }),
    enabled: !!activePlanId,
  })

  const searchRunsQuery = useQuery({
    queryKey: QK.panelWfSearchRuns(activePlanId ?? undefined),
    queryFn: () => api.listWfSearchRuns({ plan_id: activePlanId ?? undefined }),
    enabled: !!activePlanId,
  })

  const validatedQuery = useQuery({
    queryKey: QK.panelWfValidated(),
    queryFn: () => api.listWfValidated(),
  })

  const ensemblesQuery = useQuery({
    queryKey: QK.panelWfEnsembles(),
    queryFn: () => api.listWfEnsembles(),
  })

  return (
    <>
      <PageHeader
        title="滚动前推验证"
        subtitle="训练 / 测试 / 间隔 · 保留 OOS · 参数搜索 · 集成"
      />
      <div className="px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
          {/* Plan list */}
          <section className="rounded-card border border-border bg-surface">
            <div className="border-b border-border px-3 py-2 text-xs font-semibold text-secondary">
              验证计划 {plansQuery.data ? `(${plansQuery.data.length})` : ''}
            </div>
            <div className="max-h-[calc(100vh-16rem)] overflow-auto p-2 space-y-1">
              {plansQuery.data?.length === 0 && (
                <EmptyState icon={GitBranch} title="暂无验证计划" hint="运行滚动前推验证后，计划会显示在这里。" />
              )}
              {plansQuery.data?.map(plan => (
                <button
                  key={plan.id}
                  onClick={() => setSelectedPlanId(plan.id)}
                  className={`w-full rounded-lg px-3 py-2 text-left transition-colors ${selectedPlan?.id === plan.id ? 'bg-accent/10 border border-accent/25' : 'border border-transparent hover:bg-elevated/60'}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-mono text-xs font-medium text-foreground">{plan.id}</span>
                    {plan.pinned && <span className="shrink-0 rounded bg-accent/15 px-1.5 py-px text-[9px] font-medium text-accent">已固定</span>}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[10px] text-muted">
                    <span>{plan.n_folds} 折</span>
                    <span>训练 {plan.train_size}</span>
                    <span>测试 {plan.test_size}</span>
                    {plan.gap > 0 && <span>间隔 {plan.gap}</span>}
                  </div>
                </button>
              ))}
            </div>
          </section>

          {/* Detail */}
          <section className="min-w-0 space-y-4">
            {!selectedPlan ? (
              <div className="flex items-center justify-center rounded-card border border-border bg-surface py-20">
                <div className="text-center">
                  <GitBranch className="mx-auto h-8 w-8 text-muted/40" />
                  <p className="mt-3 text-sm text-secondary">选择左侧验证计划查看详情</p>
                  <p className="mt-1 text-xs text-muted">折拆分、保留 OOS、参数搜索与集成</p>
                </div>
              </div>
            ) : (
              <>
                <PlanHeader plan={selectedPlan} />
                <FoldsSection planId={selectedPlan.id} folds={foldsQuery.data ?? []} loading={foldsQuery.isLoading} />
                <SearchRunsSection runs={searchRunsQuery.data ?? []} loading={searchRunsQuery.isLoading} />
                <ValidatedSection rows={validatedQuery.data ?? []} loading={validatedQuery.isLoading} />
                <EnsemblesSection rows={ensemblesQuery.data ?? []} loading={ensemblesQuery.isLoading} />
              </>
            )}
          </section>
        </div>
      </div>
    </>
  )
}

function PlanHeader({ plan }: { plan: WfPlanDTO }) {
  return (
    <div className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-mono text-sm font-semibold text-foreground">{plan.id}</h2>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
            <span>{plan.n_folds} 折滚动</span>
            <span>训练窗 {plan.train_size}</span>
            <span>测试窗 {plan.test_size}</span>
            {plan.gap > 0 && <span>间隙 {plan.gap}</span>}
            {plan.strategy_id && <span className="font-mono">{plan.strategy_id}</span>}
          </div>
        </div>
        {plan.oos_start && (
          <div className="rounded-btn border border-warning/30 bg-warning/5 px-2.5 py-1.5 text-right">
            <div className="text-[9px] font-medium uppercase tracking-wider text-warning/80">保留 OOS（仅评估一次）</div>
            <div className="mt-0.5 font-mono text-[10px] text-secondary">{plan.oos_start} → {plan.oos_end ?? '—'}</div>
          </div>
        )}
      </div>
    </div>
  )
}

function FoldsSection({ planId, folds, loading }: { planId: string; folds: WfFoldDTO[]; loading: boolean }) {
  const [expanded, setExpanded] = useState(true)
  const oosFolds = folds.filter(fold => fold.is_oos)
  const selectionFolds = folds.filter(fold => !fold.is_oos)

  return (
    <section className="rounded-card border border-border bg-surface">
      <button onClick={() => setExpanded(v => !v)} className="flex min-h-11 w-full items-center gap-2 px-3 text-left text-xs font-semibold text-foreground hover:bg-elevated/40 transition-colors">
        {expanded ? <ChevronDown className="h-3.5 w-3.5 text-muted" /> : <ChevronRight className="h-3.5 w-3.5 text-muted" />}
        折拆分
        <span className="ml-auto text-[10px] font-normal text-muted">{selectionFolds.length} 选择折 · {oosFolds.length} 保留 OOS</span>
      </button>
      {expanded && (
        <div className="border-t border-border p-3">
          {loading && <div className="py-6 text-center text-xs text-muted">加载中…</div>}
          {folds.length === 0 && !loading && <div className="py-6 text-center text-xs text-muted">计划 {planId} 暂无折记录</div>}
          <div className="space-y-1.5">
            {selectionFolds.map(fold => (
              <div key={fold.id} className="flex flex-wrap items-center gap-2 rounded-btn bg-elevated/30 px-2.5 py-1.5 text-[11px]">
                <span className="font-mono font-medium text-secondary">折 {fold.fold_index}</span>
                <span className="text-muted">训练</span>
                <span className="font-mono text-secondary">{fold.train_start} → {fold.train_end}</span>
                <span className="text-muted">测试</span>
                <span className="font-mono text-secondary">{fold.test_start} → {fold.test_end}</span>
              </div>
            ))}
            {oosFolds.map(fold => (
              <div key={fold.id} className="flex flex-wrap items-center gap-2 rounded-btn border border-warning/30 bg-warning/5 px-2.5 py-1.5 text-[11px]">
                <span className="font-mono font-medium text-warning">保留 OOS</span>
                <span className="text-muted">仅评估一次 — 不参与选择</span>
                <span className="ml-auto font-mono text-secondary">{fold.test_start} → {fold.test_end}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

function SearchRunsSection({ runs, loading }: { runs: WfSearchRunDTO[]; loading: boolean }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <section className="rounded-card border border-border bg-surface">
      <button onClick={() => setExpanded(v => !v)} className="flex min-h-11 w-full items-center gap-2 px-3 text-left text-xs font-semibold text-foreground hover:bg-elevated/40 transition-colors">
        {expanded ? <ChevronDown className="h-3.5 w-3.5 text-muted" /> : <ChevronRight className="h-3.5 w-3.5 text-muted" />}
        参数搜索（OOS 评分）
        <span className="ml-auto text-[10px] font-normal text-muted">{runs.length} 次</span>
      </button>
      {expanded && (
        <div className="border-t border-border p-3">
          {loading && <div className="py-4 text-center text-xs text-muted">加载中…</div>}
          {runs.length === 0 && !loading && <div className="py-4 text-center text-xs text-muted">暂无参数搜索运行</div>}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-[10px] text-muted">
                <tr>
                  <th className="px-2 py-1 font-medium">运行</th>
                  <th className="px-2 py-1 font-medium">试验数</th>
                  <th className="px-2 py-1 text-right font-medium">最优 OOS 得分</th>
                </tr>
              </thead>
              <tbody>
                {runs.map(run => (
                  <tr key={run.id} className="border-t border-border/50">
                    <td className="px-2 py-1.5 font-mono text-secondary">{run.id.slice(0, 12)}</td>
                    <td className="px-2 py-1.5 tabular-nums">{run.n_trials}</td>
                    <td className="px-2 py-1.5 text-right font-mono tabular-nums text-accent">{run.best_score != null ? run.best_score.toFixed(4) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  )
}

function ValidatedSection({ rows, loading }: { rows: WfValidatedStrategyDTO[]; loading: boolean }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <section className="rounded-card border border-border bg-surface">
      <button onClick={() => setExpanded(v => !v)} className="flex min-h-11 w-full items-center gap-2 px-3 text-left text-xs font-semibold text-foreground hover:bg-elevated/40 transition-colors">
        {expanded ? <ChevronDown className="h-3.5 w-3.5 text-muted" /> : <ChevronRight className="h-3.5 w-3.5 text-muted" />}
        已验证策略
        <span className="ml-auto text-[10px] font-normal text-muted">{rows.length}</span>
      </button>
      {expanded && (
        <div className="border-t border-border p-3">
          {loading && <div className="py-4 text-center text-xs text-muted">加载中…</div>}
          {rows.length === 0 && !loading && <div className="py-4 text-center text-xs text-muted">暂无已验证策略</div>}
          <div className="space-y-1.5">
            {rows.map(row => (
              <div key={row.id} className="flex flex-wrap items-center gap-2 rounded-btn bg-elevated/30 px-2.5 py-1.5 text-[11px]">
                {row.validated ? <CheckCircle2 className="h-3.5 w-3.5 text-bear" /> : <FlaskConical className="h-3.5 w-3.5 text-warning" />}
                <span className="font-mono text-secondary">{row.strategy_id}</span>
                <span className={row.validated ? 'text-bear' : 'text-warning'}>{row.validated ? '通过' : '未通过'}</span>
                {row.oos_score != null && <span className="ml-auto font-mono tabular-nums text-accent">OOS {row.oos_score.toFixed(4)}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

function EnsemblesSection({ rows, loading }: { rows: WfEnsembleDTO[]; loading: boolean }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <section className="rounded-card border border-border bg-surface">
      <button onClick={() => setExpanded(v => !v)} className="flex min-h-11 w-full items-center gap-2 px-3 text-left text-xs font-semibold text-foreground hover:bg-elevated/40 transition-colors">
        {expanded ? <ChevronDown className="h-3.5 w-3.5 text-muted" /> : <ChevronRight className="h-3.5 w-3.5 text-muted" />}
        集成
        <span className="ml-auto text-[10px] font-normal text-muted">{rows.length}</span>
      </button>
      {expanded && (
        <div className="border-t border-border p-3">
          {rows.length === 0 && !loading && <div className="py-4 text-center text-xs text-muted">暂无集成输出</div>}
          <div className="space-y-1.5">
            {rows.map(row => (
              <div key={row.id} className="flex flex-wrap items-center gap-2 rounded-btn bg-elevated/30 px-2.5 py-1.5 text-[11px]">
                <span className="font-medium text-foreground">{row.name}</span>
                <span className="rounded bg-elevated px-1.5 py-px text-[9px] text-muted">{row.method}</span>
                <span className="ml-auto font-mono text-muted">{row.strategy_ids?.length ?? 0} 个策略</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
