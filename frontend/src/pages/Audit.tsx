/**
 * 审计 (Audit) 页 — 工具调用审计 / Provider Doctor / 数据质量三联视图。
 *
 * - 工具调用: 分页表格 + 筛选器 (category / has_error / degraded / 日期范围) + 摘要统计
 * - Provider Doctor: 每个 provider 一张健康卡片 (ok=green / warn=amber / error=red)
 * - 数据质量: 数据源质量列表 + 告警 Banner
 */
import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Shield,
  Activity,
  Stethoscope,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
  RefreshCw,
  Database,
  Clock,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { cn } from '@/lib/cn'
import { QK } from '@/lib/queryKeys'
import { fmtDate } from '@/lib/format'
import { PageHeader } from '@/components/PageHeader'
import {
  fetchAuditToolCalls,
  fetchAuditSummary,
  fetchProviderDoctor,
  fetchDataQuality,
  type ToolCallEnvelope,
  type ProviderDoctorResponse,
  type DataQualityResponse,
  type AuditHealth,
  type AuditAlertLevel,
  type AuditCategory,
} from '@/lib/api'

// ===== 通用 =====

type TabKey = 'tool-calls' | 'provider-doctor' | 'data-quality'

const TABS: { key: TabKey; label: string; icon: typeof Activity }[] = [
  { key: 'tool-calls', label: '工具调用', icon: Activity },
  { key: 'provider-doctor', label: 'Provider Doctor', icon: Stethoscope },
  { key: 'data-quality', label: '数据质量', icon: Shield },
]

const HEALTH_STYLES: Record<AuditHealth, { dot: string; badge: string; ring: string; text: string; Icon: typeof CheckCircle2 }> = {
  ok: {
    dot: 'bg-emerald-500',
    badge: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
    ring: 'border-emerald-500/40',
    text: 'text-emerald-600 dark:text-emerald-400',
    Icon: CheckCircle2,
  },
  warn: {
    dot: 'bg-amber-500',
    badge: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30',
    ring: 'border-amber-500/40',
    text: 'text-amber-600 dark:text-amber-400',
    Icon: AlertCircle,
  },
  error: {
    dot: 'bg-red-500',
    badge: 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30',
    ring: 'border-red-500/40',
    text: 'text-red-600 dark:text-red-400',
    Icon: XCircle,
  },
}

const HEALTH_LABEL: Record<AuditHealth, string> = { ok: '正常', warn: '警告', error: '异常' }

const ALERT_STYLES: Record<AuditAlertLevel, { cls: string; Icon: typeof CheckCircle2 }> = {
  ok: { cls: 'border-emerald-500/30 bg-emerald-500/5 text-emerald-700 dark:text-emerald-300', Icon: CheckCircle2 },
  warn: { cls: 'border-amber-500/30 bg-amber-500/5 text-amber-700 dark:text-amber-300', Icon: AlertCircle },
  error: { cls: 'border-red-500/30 bg-red-500/5 text-red-700 dark:text-red-300', Icon: AlertTriangle },
}

const CATEGORY_LABEL: Record<AuditCategory, string> = {
  provider: '数据源',
  ai: 'AI',
  notification: '通知',
  external: '外部',
}

const cardCls = 'rounded-card border border-border bg-surface/80 shadow-[0_1px_2px_hsl(var(--border)/0.4)] backdrop-blur-sm'

function HealthBadge({ health, className }: { health: AuditHealth; className?: string }) {
  const s = HEALTH_STYLES[health]
  const Icon = s.Icon
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium', s.badge, className)}>
      <Icon className="h-3.5 w-3.5" />
      {HEALTH_LABEL[health]}
    </span>
  )
}

function LoadingRow({ colSpan, label }: { colSpan: number; label?: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-3 py-8 text-center text-sm text-muted">
        <span className="inline-flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin" />
          {label ?? '加载中...'}
        </span>
      </td>
    </tr>
  )
}

function ErrorRow({ colSpan, message }: { colSpan: number; message: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-3 py-8 text-center text-sm text-red-600 dark:text-red-400">
        <AlertTriangle className="mr-1.5 inline h-4 w-4 align-text-bottom" />
        {message}
      </td>
    </tr>
  )
}

function EmptyRow({ colSpan, label }: { colSpan: number; label: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-3 py-8 text-center text-sm text-muted">{label}</td>
    </tr>
  )
}

function QueryErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex items-center justify-between rounded-card border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-700 dark:text-red-300">
      <span className="inline-flex items-center gap-2">
        <AlertTriangle className="h-4 w-4" />
        {message}
      </span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1.5 rounded-md border border-red-500/30 px-2.5 py-1 text-xs font-medium text-red-700 transition-colors hover:bg-red-500/10 dark:text-red-300"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          重试
        </button>
      )}
    </div>
  )
}

// ===== Tab 1: 工具调用审计 =====

const PAGE_SIZE = 25
const CATEGORY_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: '全部分类' },
  { value: 'provider', label: '数据源' },
  { value: 'ai', label: 'AI' },
  { value: 'notification', label: '通知' },
  { value: 'external', label: '外部' },
]
const BOOL_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'true', label: '是' },
  { value: 'false', label: '否' },
]

function ToolCallRow({ row }: { row: ToolCallEnvelope }) {
  const summary = useMemo(() => {
    const s = row.response_summary
    if (!s || typeof s !== 'object') return ''
    const str = JSON.stringify(s)
    return str.length > 80 ? `${str.slice(0, 80)}…` : str
  }, [row.response_summary])

  return (
    <tr className="border-b border-border last:border-0 hover:bg-muted/40">
      <td className="px-3 py-2 text-xs tabular-nums text-muted">{row.seq}</td>
      <td className="px-3 py-2 text-sm font-medium text-foreground">{row.tool}</td>
      <td className="px-3 py-2 text-xs">
        <span className="rounded bg-muted px-1.5 py-0.5 text-muted">{CATEGORY_LABEL[row.category] ?? row.category}</span>
      </td>
      <td className="max-w-[240px] truncate px-3 py-2 text-xs text-muted" title={summary}>{summary || '—'}</td>
      <td className="px-3 py-2 text-right text-xs tabular-nums text-muted">{row.duration_ms != null ? `${row.duration_ms}ms` : '—'}</td>
      <td className="px-3 py-2 text-xs">
        {row.error ? (
          <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-400" title={row.error}>
            <XCircle className="h-3.5 w-3.5" />
            <span className="max-w-[120px] truncate">{row.error}</span>
          </span>
        ) : (
          <span className="text-muted">—</span>
        )}
      </td>
      <td className="px-3 py-2 text-center text-xs">
        {row.cached ? <span className="text-emerald-600 dark:text-emerald-400">是</span> : <span className="text-muted">否</span>}
      </td>
      <td className="px-3 py-2 text-center text-xs">
        {row.degraded ? <span className="text-amber-600 dark:text-amber-400">是</span> : <span className="text-muted">否</span>}
      </td>
      <td className="whitespace-nowrap px-3 py-2 text-xs text-muted">{fmtDate(row.created_at)}</td>
    </tr>
  )
}

function SummaryStat({ label, value, accent }: { label: string; value: string | number; accent?: string }) {
  return (
    <div className={cn('rounded-lg border border-border bg-surface px-3 py-2.5', accent)}>
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-0.5 text-lg font-semibold tabular-nums text-foreground">{value}</div>
    </div>
  )
}

function ToolCallsTab() {
  const [category, setCategory] = useState('')
  const [hasError, setHasError] = useState('')
  const [degraded, setDegraded] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [offset, setOffset] = useState(0)

  const params = useMemo(() => {
    const p: Record<string, string | number | boolean> = { limit: PAGE_SIZE, offset }
    if (category) p.category = category
    if (hasError) p.has_error = hasError === 'true'
    if (degraded) p.degraded = degraded === 'true'
    if (dateFrom) p.date_from = dateFrom
    if (dateTo) p.date_to = dateTo
    return p
  }, [category, hasError, degraded, dateFrom, dateTo, offset])

  const listQ = useQuery({
    queryKey: QK.auditToolCalls(params),
    queryFn: () => fetchAuditToolCalls(params),
  })
  const summaryQ = useQuery({
    queryKey: QK.auditSummary,
    queryFn: fetchAuditSummary,
  })

  const total = listQ.data?.total ?? 0
  const items = listQ.data?.items ?? []
  const hasPrev = offset > 0
  const hasNext = offset + PAGE_SIZE < total

  function resetAndApply(fn: () => void) {
    setOffset(0)
    fn()
  }

  const selectCls = 'rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40'
  const inputCls = 'rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40'

  return (
    <div className="space-y-4">
      {/* 摘要统计 */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <SummaryStat label="总调用次数" value={summaryQ.data?.total_calls ?? '—'} />
        <SummaryStat label="总错误次数" value={summaryQ.data?.total_errors ?? '—'} accent={summaryQ.data && summaryQ.data.total_errors > 0 ? 'border-red-500/30' : ''} />
        <SummaryStat
          label="错误率"
          value={summaryQ.data ? `${(summaryQ.data.error_rate * 100).toFixed(2)}%` : '—'}
          accent={summaryQ.data && summaryQ.data.error_rate > 0.05 ? 'border-red-500/30' : ''}
        />
        <SummaryStat label="分类数" value={summaryQ.data ? Object.keys(summaryQ.data.by_category).length : '—'} />
      </div>

      {/* 筛选器 */}
      <div className={cn(cardCls, 'p-4')}>
        <div className="flex flex-wrap items-end gap-3">
          <label className="space-y-1 text-sm">
            <span className="text-xs text-muted">分类</span>
            <select className={selectCls} value={category} onChange={e => resetAndApply(() => setCategory(e.target.value))}>
              {CATEGORY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-xs text-muted">有错误</span>
            <select className={selectCls} value={hasError} onChange={e => resetAndApply(() => setHasError(e.target.value))}>
              {BOOL_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-xs text-muted">降级</span>
            <select className={selectCls} value={degraded} onChange={e => resetAndApply(() => setDegraded(e.target.value))}>
              {BOOL_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-xs text-muted">开始日期</span>
            <input type="date" className={cn(inputCls, 'w-[150px]')} value={dateFrom} onChange={e => resetAndApply(() => setDateFrom(e.target.value))} />
          </label>
          <label className="space-y-1 text-sm">
            <span className="text-xs text-muted">结束日期</span>
            <input type="date" className={cn(inputCls, 'w-[150px]')} value={dateTo} onChange={e => resetAndApply(() => setDateTo(e.target.value))} />
          </label>
          {(category || hasError || degraded || dateFrom || dateTo) && (
            <button
              type="button"
              onClick={() => { setCategory(''); setHasError(''); setDegraded(''); setDateFrom(''); setDateTo(''); setOffset(0) }}
              className="rounded-md border border-border px-2.5 py-1.5 text-sm text-muted transition-colors hover:bg-muted"
            >
              清除筛选
            </button>
          )}
        </div>
      </div>

      {/* 表格 */}
      <div className={cn(cardCls, 'overflow-hidden')}>
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="bg-muted/50 text-xs text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">seq</th>
                <th className="px-3 py-2 font-medium">工具</th>
                <th className="px-3 py-2 font-medium">分类</th>
                <th className="px-3 py-2 font-medium">响应摘要</th>
                <th className="px-3 py-2 text-right font-medium">耗时</th>
                <th className="px-3 py-2 font-medium">错误</th>
                <th className="px-3 py-2 text-center font-medium">缓存</th>
                <th className="px-3 py-2 text-center font-medium">降级</th>
                <th className="px-3 py-2 font-medium">时间</th>
              </tr>
            </thead>
            <tbody>
              {listQ.isLoading ? (
                <LoadingRow colSpan={9} />
              ) : listQ.isError ? (
                <ErrorRow colSpan={9} message={listQ.error instanceof Error ? listQ.error.message : '加载失败'} />
              ) : items.length === 0 ? (
                <EmptyRow colSpan={9} label="暂无工具调用记录" />
              ) : (
                items.map(row => <ToolCallRow key={row.id} row={row} />)
              )}
            </tbody>
          </table>
        </div>

        {/* 分页 */}
        <div className="flex items-center justify-between border-t border-border px-3 py-2 text-sm">
          <span className="text-xs text-muted">
            共 {total} 条, 第 {Math.min(offset + 1, total || 0)}-{Math.min(offset + PAGE_SIZE, total)} 条
          </span>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              disabled={!hasPrev || listQ.isFetching}
              onClick={() => setOffset(o => Math.max(0, o - PAGE_SIZE))}
              className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted transition-colors enabled:hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              上一页
            </button>
            <button
              type="button"
              disabled={!hasNext || listQ.isFetching}
              onClick={() => setOffset(o => o + PAGE_SIZE)}
              className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted transition-colors enabled:hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
            >
              下一页
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ===== Tab 2: Provider Doctor =====

function ProviderVerdictCard({ verdict }: { verdict: ProviderDoctorResponse['verdicts'][number] }) {
  const s = HEALTH_STYLES[verdict.health]
  const Icon = s.Icon
  return (
    <div className={cn(cardCls, 'p-4', s.ring)}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={cn('h-2 w-2 shrink-0 rounded-full', s.dot)} />
            <h3 className="truncate text-sm font-semibold text-foreground">{verdict.display_name || verdict.name}</h3>
          </div>
          <p className="mt-0.5 truncate text-xs text-muted">{verdict.name}</p>
        </div>
        <HealthBadge health={verdict.health} />
      </div>

      {verdict.datasets.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {verdict.datasets.map(d => (
            <span key={d} className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted">{d}</span>
          ))}
        </div>
      )}

      {verdict.detail && (
        <p className="mt-3 text-xs leading-relaxed text-muted">{verdict.detail}</p>
      )}

      {verdict.recommendation && (
        <div className={cn('mt-3 flex items-start gap-1.5 rounded-md border p-2 text-xs', s.badge)}>
          <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{verdict.recommendation}</span>
        </div>
      )}
    </div>
  )
}

function ProviderDoctorTab() {
  const q = useQuery({ queryKey: QK.auditProviderDoctor, queryFn: fetchProviderDoctor })

  if (q.isError) {
    return <QueryErrorBanner message={q.error instanceof Error ? q.error.message : '加载 Provider Doctor 失败'} onRetry={() => q.refetch()} />
  }

  const data = q.data
  const verdicts = data?.verdicts ?? []

  return (
    <div className="space-y-4">
      {data && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <SummaryStat label="Provider 总数" value={data.summary.total} />
          <SummaryStat label="正常" value={data.summary.ok} accent="border-emerald-500/30" />
          <SummaryStat label="警告" value={data.summary.warn} accent={data.summary.warn > 0 ? 'border-amber-500/30' : ''} />
          <SummaryStat label="异常" value={data.summary.error} accent={data.summary.error > 0 ? 'border-red-500/30' : ''} />
        </div>
      )}

      {q.isLoading ? (
        <div className={cn(cardCls, 'flex items-center justify-center py-16 text-sm text-muted')}>
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          加载中...
        </div>
      ) : verdicts.length === 0 ? (
        <div className={cn(cardCls, 'flex flex-col items-center justify-center py-16 text-center text-muted')}>
          <Stethoscope className="mb-2 h-8 w-8 opacity-40" />
          <p className="text-sm">暂无 Provider 诊断数据</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {verdicts.map(v => <ProviderVerdictCard key={v.name} verdict={v} />)}
        </div>
      )}
    </div>
  )
}

// ===== Tab 3: 数据质量 =====

function DataQualitySourceCard({ source }: { source: DataQualityResponse['sources'][number] }) {
  const s = HEALTH_STYLES[source.health]
  return (
    <div className={cn(cardCls, 'p-4', s.ring)}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className={cn('h-2 w-2 shrink-0 rounded-full', s.dot)} />
            <h3 className="truncate text-sm font-semibold text-foreground">{source.display_name || source.name}</h3>
          </div>
          <p className="mt-0.5 truncate text-xs text-muted">{source.name}</p>
        </div>
        <HealthBadge health={source.health} />
      </div>

      <div className="mt-3 flex items-center gap-1.5 text-xs text-muted">
        <Clock className="h-3.5 w-3.5" />
        <span>最后同步: {source.last_sync ? fmtDate(source.last_sync) : '—'}</span>
      </div>

      {source.datasets.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {source.datasets.map(d => (
            <span key={d} className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted">{d}</span>
          ))}
        </div>
      )}

      {source.detail && (
        <p className="mt-3 text-xs leading-relaxed text-muted">{source.detail}</p>
      )}
    </div>
  )
}

function DataQualityTab() {
  const q = useQuery({ queryKey: QK.auditDataQuality, queryFn: fetchDataQuality })

  if (q.isError) {
    return <QueryErrorBanner message={q.error instanceof Error ? q.error.message : '加载数据质量失败'} onRetry={() => q.refetch()} />
  }

  const data = q.data
  const alerts = data?.alerts ?? []
  const sources = data?.sources ?? []

  return (
    <div className="space-y-4">
      {/* 告警 Banner */}
      {alerts.length > 0 && (
        <div className="space-y-2">
          {alerts.map((alert, i) => {
            const a = ALERT_STYLES[alert.level]
            const Icon = a.Icon
            return (
              <div key={`${alert.source}-${i}`} className={cn('flex items-start gap-2 rounded-card border px-4 py-3 text-sm', a.cls)}>
                <Icon className="mt-0.5 h-4 w-4 shrink-0" />
                <div className="min-w-0">
                  <span className="font-medium">{alert.source}: </span>
                  <span>{alert.message}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* 摘要 */}
      {data && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <SummaryStat label="数据源总数" value={data.summary.total} />
          <SummaryStat label="正常" value={data.summary.ok} accent="border-emerald-500/30" />
          <SummaryStat label="警告" value={data.summary.warn} accent={data.summary.warn > 0 ? 'border-amber-500/30' : ''} />
          <SummaryStat label="异常" value={data.summary.error} accent={data.summary.error > 0 ? 'border-red-500/30' : ''} />
        </div>
      )}

      {data?.summary.daily_latest_date && (
        <div className={cn(cardCls, 'flex items-center gap-2 px-4 py-2.5 text-sm')}>
          <Database className="h-4 w-4 text-muted" />
          <span className="text-muted">最新数据日期:</span>
          <span className="font-medium tabular-nums text-foreground">{data.summary.daily_latest_date}</span>
        </div>
      )}

      {/* 数据源列表 */}
      {q.isLoading ? (
        <div className={cn(cardCls, 'flex items-center justify-center py-16 text-sm text-muted')}>
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          加载中...
        </div>
      ) : sources.length === 0 ? (
        <div className={cn(cardCls, 'flex flex-col items-center justify-center py-16 text-center text-muted')}>
          <Shield className="mb-2 h-8 w-8 opacity-40" />
          <p className="text-sm">暂无数据质量信息</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {sources.map(src => <DataQualitySourceCard key={src.name} source={src} />)}
        </div>
      )}
    </div>
  )
}

// ===== 主组件 =====

export function Audit() {
  const [tab, setTab] = useState<TabKey>('tool-calls')

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="审计"
        subtitle="工具调用审计 / Provider 诊断 / 数据质量"
        titleExtra={<Shield className="h-6 w-6 text-primary" />}
      />

      {/* Tab 切换 */}
      <div className="flex shrink-0 gap-1 border-b border-border px-3 sm:px-5">
        {TABS.map(t => {
          const Icon = t.icon
          const active = tab === t.key
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(
                'relative inline-flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium transition-colors',
                active ? 'text-primary' : 'text-muted hover:text-foreground',
              )}
            >
              <Icon className="h-4 w-4" />
              {t.label}
              {active && (
                <span className="absolute inset-x-0 -bottom-px h-0.5 rounded-full bg-primary" />
              )}
            </button>
          )
        })}
      </div>

      {/* 内容 */}
      <div className="min-h-0 flex-1 overflow-y-auto p-3 sm:p-5">
        {tab === 'tool-calls' && <ToolCallsTab />}
        {tab === 'provider-doctor' && <ProviderDoctorTab />}
        {tab === 'data-quality' && <DataQualityTab />}
      </div>
    </div>
  )
}
