import { useQuery } from '@tanstack/react-query'
import { Loader2, AlertTriangle, GitCompareArrows, AlertOctagon, ArrowUpCircle, ArrowDownCircle } from 'lucide-react'
import { fetchConflicts, type ConflictResponse } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

/**
 * Phase 54 (MON-05) — 冲突观点与失败路径。
 *
 * 从 /api/report-ops/conflicts 拉取多空冲突观点 (bullish/bearish) + 失败路径
 * (数据源不可用 / 步骤失败), 以对比卡片 + 列表展示。
 *
 * 冲突: bullish (红, A 股红涨) vs bearish (绿) 对比展示
 * 失败路径: step + reason + data_source 列表
 */
interface Props {
  runId?: string
  reportType?: string
  reportId?: string
}

export function ConflictPaths({ runId, reportType, reportId }: Props) {
  const params = { run_id: runId, report_type: reportType, report_id: reportId }
  const query = useQuery<ConflictResponse>({
    queryKey: QK.reportOps({ ...params, _t: 'conflicts' }),
    queryFn: () => fetchConflicts(params as { run_id?: string; report_type?: string; report_id?: string }),
    enabled: !!(runId || (reportType && reportId)),
  })

  if (query.isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-card border border-border bg-surface/60 px-4 py-8">
        <Loader2 className="h-4 w-4 animate-spin text-accent" />
        <span className="text-xs text-muted">加载冲突分析…</span>
      </div>
    )
  }

  if (query.isError) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-card border border-danger/30 bg-danger/5 px-4 py-8 text-xs text-danger">
        <AlertTriangle className="h-4 w-4" />
        冲突分析加载失败
      </div>
    )
  }

  const data = query.data
  const conflicts = data?.conflicts ?? []
  const failurePaths = data?.failure_paths ?? []

  if (!query.data || (conflicts.length === 0 && failurePaths.length === 0)) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-card border border-dashed border-border/50 bg-surface/40 px-4 py-8 text-center">
        <GitCompareArrows className="h-6 w-6 text-muted/40" />
        <span className="text-xs text-muted">暂无冲突观点与失败路径</span>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* 冲突观点 */}
      {conflicts.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-medium text-secondary">
            <GitCompareArrows className="h-3.5 w-3.5 text-accent" />
            多空冲突观点
          </div>
          {conflicts.map((c, i) => (
            <div
              key={i}
              className="grid grid-cols-1 gap-px overflow-hidden rounded-card border border-border/60 sm:grid-cols-2"
            >
              {/* 看多 (A 股惯例: 红为涨/看多) */}
              <div className="bg-red-500/5 px-3 py-2.5">
                <div className="flex items-center gap-1 text-[10px] font-medium text-red-600 dark:text-red-400">
                  <ArrowUpCircle className="h-3 w-3" />
                  看多
                </div>
                <p className="mt-1 text-xs leading-relaxed text-foreground/90">{c.bullish}</p>
              </div>
              {/* 看空 (绿) */}
              <div className="bg-emerald-500/5 px-3 py-2.5">
                <div className="flex items-center gap-1 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                  <ArrowDownCircle className="h-3 w-3" />
                  看空
                </div>
                <p className="mt-1 text-xs leading-relaxed text-foreground/90">{c.bearish}</p>
              </div>
              {c.source && (
                <div className="bg-elevated/30 px-3 py-1.5 text-[9px] text-muted sm:col-span-2">
                  来源: {c.source}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 失败路径 */}
      {failurePaths.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-medium text-secondary">
            <AlertOctagon className="h-3.5 w-3.5 text-danger" />
            失败路径
          </div>
          <div className="space-y-1.5">
            {failurePaths.map((p, i) => (
              <div
                key={i}
                className="rounded-card border border-danger/30 bg-danger/5 px-3 py-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-foreground">{p.step}</span>
                  {p.data_source && (
                    <span className="shrink-0 rounded bg-danger/10 px-1.5 py-0.5 text-[9px] text-danger">
                      {p.data_source}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-[11px] text-secondary">{p.reason}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
