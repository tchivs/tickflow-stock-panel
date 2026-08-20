import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowUpRight } from 'lucide-react'
import { fetchWorkbench, type WorkbenchResponse } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

/**
 * 数据质量 Banner (Phase 53 WORK-01)
 *
 * 仅当 data_quality 非 null 且存在告警 (alerts) 或整体非 healthy 时渲染,
 * 风格对齐 CoverageBanner 的横幅样式。
 * 健康或无数据时返回 null, 不占用布局空间。
 */
export function DataQualityBanner() {
  const { data } = useQuery({
    queryKey: QK.workbench,
    queryFn: fetchWorkbench,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  const dq: WorkbenchResponse['data_quality'] = data?.data_quality ?? null
  if (!dq) return null
  // healthy 且无告警 -> 不渲染
  if (dq.summary.overall === 'healthy' && (!dq.alerts || dq.alerts.length === 0)) return null

  const hasError = dq.alerts.some(a => a.level === 'error') || dq.summary.overall === 'unavailable'
  const borderCls = hasError
    ? 'border-red-500/30 bg-red-500/8'
    : 'border-amber-500/30 bg-amber-500/8'
  const Icon = hasError ? AlertTriangle : AlertTriangle

  const overallLabel = dq.summary.overall === 'unavailable' ? '不可用' : dq.summary.overall === 'degraded' ? '降级' : '需关注'

  return (
    <div
      role="status"
      className={`mb-3 flex items-start gap-2 rounded-card border ${borderCls} px-3 py-2 text-[11px] leading-relaxed`}
    >
      <Icon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${hasError ? 'text-red-500' : 'text-amber-500'}`} />
      <div className="min-w-0 flex-1 text-secondary">
        <div className="flex items-center gap-1.5">
          <span className="font-medium text-foreground">数据质量:{overallLabel}</span>
          {dq.summary.error > 0 && (
            <span className="rounded bg-red-500/10 px-1 text-red-600 dark:text-red-400">异常 {dq.summary.error}</span>
          )}
          {dq.summary.warn > 0 && (
            <span className="rounded bg-amber-500/10 px-1 text-amber-600 dark:text-amber-400">警告 {dq.summary.warn}</span>
          )}
          {dq.summary.ok > 0 && (
            <span className="rounded bg-emerald-500/10 px-1 text-emerald-600 dark:text-emerald-400">正常 {dq.summary.ok}</span>
          )}
          {dq.summary.daily_latest_date && (
            <span className="ml-auto text-muted">数据日期:{dq.summary.daily_latest_date}</span>
          )}
        </div>
        {dq.alerts.length > 0 && (
          <ul className="mt-1 space-y-0.5">
            {dq.alerts.slice(0, 3).map((a, i) => (
              <li key={i} className="flex items-start gap-1">
                <span className={`shrink-0 font-mono ${a.level === 'error' ? 'text-red-600 dark:text-red-400' : 'text-amber-600 dark:text-amber-400'}`}>
                  [{a.level === 'error' ? '异常' : '警告'}]
                </span>
                <span className="min-w-0 flex-1">{a.message}</span>
              </li>
            ))}
            {dq.alerts.length > 3 && (
              <li className="text-muted">还有 {dq.alerts.length - 3} 条告警</li>
            )}
          </ul>
        )}
      </div>
      <Link
        to="/audit"
        className="inline-flex shrink-0 items-center gap-0.5 rounded text-muted hover:text-accent hover:bg-accent/10 transition-colors"
        title="查看数据质量详情"
      >
        <ArrowUpRight className="h-3.5 w-3.5" />
      </Link>
    </div>
  )
}
