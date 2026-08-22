import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Loader2, Database, BellRing, Send, AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react'
import { useState, type ComponentType } from 'react'
import { fetchWorkbench, type WorkbenchResponse } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { STAGE_LABELS } from '@/components/data/ActiveJobCard'
import { PushQualityPanel } from '@/components/workbench/PushQualityPanel'
import { cn } from '@/lib/cn'
import { formatLogTime } from '@/lib/format'

type IconType = ComponentType<{ className?: string }>

/** 可折叠区域: 标题带图标 + 计数, 点击展开/收起 */
function CollapsibleSection({
  icon: Icon,
  title,
  count,
  badge,
  children,
  defaultOpen = true,
}: {
  icon: IconType
  title: string
  count?: number
  badge?: React.ReactNode
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-t border-border/60 first:border-t-0">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left hover:bg-base/40 transition-colors"
      >
        {open ? <ChevronDown className="h-3 w-3 text-muted shrink-0" /> : <ChevronRight className="h-3 w-3 text-muted shrink-0" />}
        <Icon className="h-3.5 w-3.5 text-accent shrink-0" />
        <span className="text-[11px] font-semibold text-foreground">{title}</span>
        {count != null && count > 0 && (
          <span className="ml-auto rounded-full bg-accent/15 px-1.5 py-0.5 text-[10px] font-mono text-accent">{count}</span>
        )}
        {badge}
      </button>
      {open && <div className="px-2.5 pb-2 pt-0.5">{children}</div>}
    </div>
  )
}

/** 运行中/失败任务区 */
function JobsSection({ jobs }: { jobs: NonNullable<WorkbenchResponse['jobs']> }) {
  if (jobs.running.length === 0 && jobs.failed.length === 0) {
    return <p className="py-1.5 text-center text-[10px] text-muted">暂无运行中或失败任务</p>
  }
  return (
    <div className="space-y-1.5">
      {jobs.running.map(j => (
        <div key={j.id} className="rounded-btn border border-accent/30 bg-accent/5 px-2 py-1.5">
          <div className="flex items-center gap-1.5">
            <Loader2 className="h-3 w-3 animate-spin text-accent shrink-0" />
            <span className="text-[10px] font-medium text-foreground">{STAGE_LABELS[j.stage] ?? j.stage}</span>
            <span className="ml-auto font-mono text-xs font-bold text-accent">{j.progress}%</span>
          </div>
          <div className="mt-1 h-1 rounded-full bg-elevated overflow-hidden">
            <div
              className="h-full bg-accent transition-[width] duration-300"
              style={{ width: `${Math.min(100, Math.max(0, j.progress))}%` }}
            />
          </div>
          {j.stage_pct > 0 && (
            <div className="mt-0.5 flex items-center justify-between">
              <span className="text-[9px] text-muted">当前阶段</span>
              <span className="text-[9px] font-mono text-secondary">{j.stage_pct}%</span>
            </div>
          )}
        </div>
      ))}
      {jobs.failed.map(j => (
        <div key={j.id} className="rounded-btn border border-danger/40 bg-danger/5 px-2 py-1.5">
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-medium text-danger">失败: {STAGE_LABELS[j.stage] ?? j.stage}</span>
            <span className="ml-auto text-[9px] text-muted">{formatLogTime(j.finished_at || j.started_at)}</span>
          </div>
          {j.error && <p className="mt-0.5 text-[9px] leading-relaxed text-secondary line-clamp-2">{j.error}</p>}
        </div>
      ))}
    </div>
  )
}

/** 最近报告区 */
function ReportsSection({ reports }: { reports: NonNullable<WorkbenchResponse['recent_reports']> }) {
  if (reports.items.length === 0) {
    return <p className="py-1.5 text-center text-[10px] text-muted">暂无报告</p>
  }
  return (
    <div className="space-y-1">
      {reports.items.slice(0, 5).map((r, i) => {
        const type = r.type as string
        const symbol = r.symbol as string | undefined
        const name = r.name as string | undefined
        const focus = r.focus as string | undefined
        const label = symbol ?? name ?? focus ?? '报告'
        const typeLabel = type === 'financial' ? '财务' : type === 'market_recap' ? '复盘' : type
        const link = type === 'financial' && symbol
          ? `/financials?symbol=${symbol}`
          : type === 'market_recap' ? '/monitor' : null
        const inner = (
          <>
            <span className="shrink-0 rounded bg-base/60 px-1 text-[9px] text-secondary">{typeLabel}</span>
            <span className="min-w-0 flex-1 truncate text-[10px] text-foreground">{label}</span>
            <span className="shrink-0 text-[9px] text-muted">{formatLogTime(r.created_at)}</span>
          </>
        )
        return link ? (
          <Link key={i} to={link} className="flex items-center gap-1.5 rounded px-1 py-1 hover:bg-base/40 transition-colors">
            {inner}
          </Link>
        ) : (
          <div key={i} className="flex items-center gap-1.5 rounded px-1 py-1 text-muted">
            {inner}
          </div>
        )
      })}
    </div>
  )
}

/** 监控触发区 */
function AlertsSection({ alerts }: { alerts: NonNullable<WorkbenchResponse['recent_alerts']> }) {
  if (alerts.items.length === 0) {
    return <p className="py-1.5 text-center text-[10px] text-muted">暂无触发记录</p>
  }
  const sevCls: Record<string, string> = {
    critical: 'text-danger',
    warn: 'text-amber-500',
    info: 'text-accent',
  }
  return (
    <div className="space-y-1">
      {alerts.items.slice(0, 5).map((a, i) => {
        const symbol = a.symbol as string | undefined
        const name = a.name as string | undefined
        const severity = a.severity as string | undefined
        const message = a.message as string | undefined
        const label = symbol ?? name ?? '市场'
        return (
          <div key={i} className="flex items-start gap-1.5 rounded px-1 py-1">
            <span className={cn('shrink-0 text-[9px] font-mono', sevCls[severity ?? 'info'] ?? 'text-accent')}>
              {severity === 'critical' ? '!!' : severity === 'warn' ? '!' : '*'}
            </span>
            <div className="min-w-0 flex-1">
              <span className="text-[10px] text-foreground">{label}</span>
              {message && <p className="text-[9px] leading-relaxed text-secondary line-clamp-1">{message}</p>}
            </div>
            <span className="shrink-0 text-[9px] text-muted">{formatLogTime(a.occurred_at)}</span>
          </div>
        )
      })}
    </div>
  )
}

/**
 * 工作台面板 (Phase 53 WORK-02)
 *
 * 汇总运行中/失败任务、最近报告、监控触发、推送质量四个折叠区。
 * 各项 fail-soft: 后端返回 null 时显示空状态, 不阻断其他区。
 */
export function WorkbenchPanel() {
  const { data } = useQuery({
    queryKey: QK.workbench,
    queryFn: fetchWorkbench,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
  const jobs = data?.jobs ?? null
  const reports = data?.recent_reports ?? null
  const alerts = data?.recent_alerts ?? null
  const pushStats = data?.push_stats ?? null
  const pushFailed = pushStats?.today.failed ?? 0
  // 四个区都为空时不渲染
  const hasJobs = jobs && (jobs.running.length > 0 || jobs.failed.length > 0)
  const hasReports = reports && reports.items.length > 0
  const hasAlerts = alerts && alerts.items.length > 0
  const hasPush = pushStats && pushStats.today.total > 0
  if (!hasJobs && !hasReports && !hasAlerts && !hasPush) return null

  return (
    <section className="rounded-card border border-border bg-surface/80 p-1.5 shadow-[0_1px_2px_hsl(var(--border)/0.4)] backdrop-blur-sm">
      <div className="mb-1.5 flex items-center gap-1.5 px-1">
        <span className="h-3 w-0.5 rounded-full bg-gradient-to-b from-accent to-accent/30" />
        <span className="text-xs font-semibold text-foreground">今日工作台</span>
      </div>
      <CollapsibleSection
        icon={Loader2}
        title="运行中/失败任务"
        count={(jobs?.running.length ?? 0) + (jobs?.failed.length ?? 0)}
        defaultOpen={!!hasJobs}
      >
        {jobs ? <JobsSection jobs={jobs} /> : <p className="py-1.5 text-center text-[10px] text-muted">任务数据不可用</p>}
      </CollapsibleSection>
      <CollapsibleSection
        icon={Database}
        title="最近报告"
        count={reports?.total ?? 0}
        defaultOpen={!!hasReports}
      >
        {reports ? <ReportsSection reports={reports} /> : <p className="py-1.5 text-center text-[10px] text-muted">报告数据不可用</p>}
      </CollapsibleSection>
      <CollapsibleSection
        icon={BellRing}
        title="监控触发"
        count={alerts?.total ?? 0}
        defaultOpen={!!hasAlerts}
      >
        {alerts ? <AlertsSection alerts={alerts} /> : <p className="py-1.5 text-center text-[10px] text-muted">触发数据不可用</p>}
      </CollapsibleSection>
      {pushStats && (
        <CollapsibleSection
          icon={Send}
          title="推送质量"
          count={pushStats.today.total}
          defaultOpen={pushFailed > 0}
          badge={pushFailed > 0 && (
            <span className="inline-flex items-center gap-0.5 rounded-full bg-red-500/15 px-1.5 py-0.5 text-[10px] font-mono text-bear" title={`推送失败 ${pushFailed} 条`}>
              <AlertTriangle className="h-2.5 w-2.5" />
              {pushFailed}
            </span>
          )}
        >
          <PushQualityPanel stats={pushStats} />
        </CollapsibleSection>
      )}
    </section>
  )
}
