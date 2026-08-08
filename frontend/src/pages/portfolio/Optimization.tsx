import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Layers, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react'
import { api, type OptimizationRunDTO } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'

export function Optimization() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [objectiveFilter, setObjectiveFilter] = useState<string | undefined>(undefined)

  const runsQuery = useQuery({
    queryKey: QK.optimizationRuns(objectiveFilter),
    queryFn: () => api.listOptimizationRuns({ objective: objectiveFilter }),
  })

  const runQuery = useQuery({
    queryKey: QK.optimizationRun(selectedRunId ?? ''),
    queryFn: () => api.getOptimizationRun(selectedRunId!),
    enabled: !!selectedRunId,
  })

  return (
    <>
      <PageHeader
        title="优化运行"
        subtitle="不可变优化记录 · 基线对比 · 约束/风险模型审计"
        right={
          <div className="flex items-center gap-2">
            {(['min_volatility', 'hrp', 'max_sharpe'] as const).map(obj => (
              <button
                key={obj}
                onClick={() => { setObjectiveFilter(obj === objectiveFilter ? undefined : obj); setSelectedRunId(null) }}
                className={`min-h-8 rounded-btn px-3 text-xs font-medium transition-colors ${
                  objectiveFilter === obj
                    ? 'bg-accent/15 text-accent'
                    : 'border border-border bg-surface text-secondary hover:text-foreground'
                }`}
              >
                {obj === 'min_volatility' ? '最小波动' : obj === 'hrp' ? 'HRP' : '最大夏普'}
              </button>
            ))}
          </div>
        }
      />

      <div className="px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
          {/* Run list */}
          <section className="rounded-card border border-border bg-surface">
            <div className="border-b border-border px-3 py-2 text-xs font-semibold text-secondary">
              运行记录 {runsQuery.data ? `(${runsQuery.data.length})` : ''}
            </div>
            <div className="max-h-[calc(100vh-16rem)] overflow-auto p-2 space-y-1">
              {runsQuery.isLoading && <div className="px-3 py-6 text-center text-xs text-muted">加载中…</div>}
              {runsQuery.isError && !runsQuery.data && (
                <div role="alert" className="rounded-btn border border-danger/30 bg-danger/10 px-3 py-3 text-xs text-danger">
                  优化记录加载失败：{runsQuery.error instanceof Error ? runsQuery.error.message : String(runsQuery.error ?? '未知错误')}
                  <button type="button" onClick={() => runsQuery.refetch()} className="ml-2 inline-flex items-center rounded-btn border border-danger/30 bg-danger/10 px-2 py-1 text-xs font-medium text-danger hover:bg-danger/20 max-md:min-h-11 max-md:min-w-11">重试</button>
                </div>
              )}
              {runsQuery.data?.length === 0 && (
                <EmptyState icon={Layers} title="暂无优化运行" hint="在回测工作台运行策略后,优化记录会出现在这里。" />
              )}
              {runsQuery.data?.map(run => (
                <RunListItem
                  key={run.id}
                  run={run}
                  active={selectedRunId === run.id}
                  onClick={() => setSelectedRunId(run.id)}
                />
              ))}
            </div>
          </section>

          {/* Run detail */}
          <section className="min-w-0">
            {!selectedRunId ? (
              <div className="flex items-center justify-center rounded-card border border-border bg-surface py-20">
                <div className="text-center">
                  <Layers className="mx-auto h-8 w-8 text-muted/40" />
                  <p className="mt-3 text-sm text-secondary">选择左侧运行记录查看详情</p>
                  <p className="mt-1 text-xs text-muted">权重、基线对比、约束栈和风险模型审计</p>
                </div>
              </div>
            ) : runQuery.isLoading ? (
              <div className="rounded-card border border-border bg-surface p-6 text-center text-sm text-muted">加载运行详情…</div>
            ) : runQuery.data ? (
              <RunDetail run={runQuery.data} />
            ) : null}
          </section>
        </div>
      </div>
    </>
  )
}

function RunListItem({ run, active, onClick }: { run: OptimizationRunDTO; active: boolean; onClick: () => void }) {
  const isFailed = run.problem_status !== 'optimal'
  const objectiveLabel = run.objective === 'min_volatility' ? '最小波动' : run.objective === 'hrp' ? 'HRP' : '最大夏普'

  return (
    <button
      onClick={onClick}
      className={`w-full rounded-lg px-3 py-2 text-left transition-colors ${active ? 'bg-accent/10 border border-accent/25' : 'border border-transparent hover:bg-elevated/60'}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs font-medium text-foreground">{run.id}</span>
        {isFailed ? (
          <XCircle className="h-3.5 w-3.5 shrink-0 text-danger" />
        ) : (
          <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-accent" />
        )}
      </div>
      <div className="mt-1 flex items-center gap-2 text-[10px] text-muted">
        <span className="rounded bg-elevated px-1.5 py-px font-medium">{objectiveLabel}</span>
        <span className="font-mono">{run.as_of}</span>
        <span className={`font-medium ${isFailed ? 'text-danger' : 'text-accent'}`}>{isFailed ? run.problem_status : '最优'}</span>
      </div>
    </button>
  )
}

function RunDetail({ run }: { run: OptimizationRunDTO }) {
  const [expanded, setExpanded] = useState<'constraints' | 'solver' | 'risk' | null>('constraints')
  const isFailed = run.problem_status !== 'optimal'
  const objectiveLabel = run.objective === 'min_volatility' ? '最小波动' : run.objective === 'hrp' ? 'HRP' : '最大夏普'
  const hasBaselines = run.baseline_weights != null && Object.keys(run.baseline_weights).length > 0

  const toggle = (key: 'constraints' | 'solver' | 'risk') => setExpanded(prev => prev === key ? null : key)

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="rounded-card border border-border bg-surface p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="font-mono text-sm font-semibold text-foreground">{run.id}</h2>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
              <span className="rounded bg-elevated px-1.5 py-0.5 font-medium">{objectiveLabel}</span>
              <span>截至 {run.as_of}</span>
              <span>·</span>
              <span>{run.universe}</span>
              <span>·</span>
              <span className={`font-medium ${isFailed ? 'text-danger' : 'text-accent'}`}>{isFailed ? run.problem_status : '最优'}</span>
            </div>
          </div>
          <div className="text-right">
            <div className="font-mono text-[10px] text-muted">input_snapshot</div>
            <div className="font-mono text-[10px] text-secondary">{run.input_snapshot_sha256.slice(0, 16)}…</div>
          </div>
        </div>

        {isFailed && run.failure_reason && (
          <div className="mt-3 flex items-start gap-2 rounded-btn border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
            <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" />
            <span>{run.failure_reason}</span>
          </div>
        )}
      </div>

      {/* Weights + Baselines */}
      {!isFailed && run.output_weights && (
        <div className="rounded-card border border-border bg-surface p-4">
          <h3 className="text-sm font-semibold text-foreground">
            权重 {hasBaselines && <span className="ml-1 text-[10px] font-normal text-muted">（含基线对比 — 绝不单独展示"最优"）</span>}
          </h3>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-[10px] text-muted">
                <tr>
                  <th className="px-2 py-1 font-medium">标的</th>
                  <th className="px-2 py-1 text-right font-medium">{objectiveLabel}</th>
                  {hasBaselines && <th className="px-2 py-1 text-right font-medium">最小波动基线</th>}
                  {hasBaselines && run.objective === 'max_sharpe' && <th className="px-2 py-1 text-right font-medium">HRP 基线</th>}
                </tr>
              </thead>
              <tbody>
                {Object.entries(run.output_weights).map(([symbol, weight]) => (
                  <tr key={symbol} className="border-t border-border/50">
                    <td className="px-2 py-1.5 font-mono text-secondary">{symbol}</td>
                    <td className="px-2 py-1.5 text-right font-mono font-semibold text-foreground tabular-nums">{(weight * 100).toFixed(2)}%</td>
                    {hasBaselines && (
                      <td className="px-2 py-1.5 text-right font-mono text-secondary tabular-nums">
                        {run.baseline_weights && symbol in run.baseline_weights
                          ? `${((run.baseline_weights[symbol] as number) * 100).toFixed(2)}%`
                          : '—'}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Expandable audit sections */}
      <div className="space-y-2">
        <ExpandableSection title="约束栈" expanded={expanded === 'constraints'} onClick={() => toggle('constraints')}>
          <pre className="overflow-x-auto whitespace-pre-wrap break-words text-[11px] text-secondary">{JSON.stringify(run.constraint_stack ?? {}, null, 2)}</pre>
        </ExpandableSection>
        <ExpandableSection title={`求解器 · ${run.solver_name} ${run.solver_version}`} expanded={expanded === 'solver'} onClick={() => toggle('solver')}>
          <pre className="overflow-x-auto whitespace-pre-wrap break-words text-[11px] text-secondary">{JSON.stringify(run.solver_options ?? {}, null, 2)}</pre>
        </ExpandableSection>
        <ExpandableSection title={`风险模型 · ${run.risk_model}`} expanded={expanded === 'risk'} onClick={() => toggle('risk')}>
          <pre className="overflow-x-auto whitespace-pre-wrap break-words text-[11px] text-secondary">{JSON.stringify(run.risk_model_detail ?? {}, null, 2)}</pre>
        </ExpandableSection>
      </div>

      <div className="text-[10px] text-muted">
        output_sha256: <span className="font-mono">{run.output_sha256.slice(0, 16)}…</span>
        {' · '}
        created: <span className="font-mono">{run.created_at}</span>
      </div>
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
