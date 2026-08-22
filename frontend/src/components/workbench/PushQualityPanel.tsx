import { Send, AlertTriangle, BellOff } from 'lucide-react'
import { formatLogTime } from '@/lib/format'
import { cn } from '@/lib/cn'
import type { WorkbenchResponse } from '@/lib/api'

type PushStats = NonNullable<WorkbenchResponse['push_stats']>

const TOOL_BADGE: Record<string, string> = {
  connection: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  sct: 'bg-purple-500/10 text-purple-600 dark:text-purple-400',
  wecom: 'bg-green-500/10 text-green-600 dark:text-green-400',
  feishu: 'bg-orange-500/10 text-orange-600 dark:text-orange-400',
  telegram: 'bg-cyan-500/10 text-cyan-600 dark:text-cyan-400',
}

const TOOL_LABEL: Record<string, string> = {
  connection: 'WS',
  sct: 'Server酱',
  wecom: '企微',
  feishu: '飞书',
  telegram: 'TG',
}

/**
 * 推送质量面板 (Phase 58 PA-03, D-04)
 *
 * 渲染今日推送统计: 成功/失败/去重跳过数字卡片 + 最近失败列表。
 * 失败告警 badge 由 WorkbenchPanel 的 CollapsibleSection 渲染。
 * push_stats 为 null 或 total=0 时不渲染。
 */
export function PushQualityPanel({ stats }: { stats: PushStats }) {
  const { today, recent_failures } = stats

  if (today.total === 0) {
    return <p className="py-1.5 text-center text-[10px] text-muted">今日暂无推送</p>
  }

  return (
    <div className="space-y-1.5">
      {/* 数字卡片 */}
      <div className="grid grid-cols-3 gap-1">
        <StatCell icon={<Send className="h-2.5 w-2.5" />} label="成功" value={today.sent} cls="text-bull" />
        <StatCell icon={<AlertTriangle className="h-2.5 w-2.5" />} label="失败" value={today.failed} cls="text-bear" />
        <StatCell icon={<BellOff className="h-2.5 w-2.5" />} label="去重跳过" value={today.dedup_skipped} cls="text-warning" />
      </div>

      {/* 最近失败列表 */}
      {recent_failures.length > 0 && (
        <div className="space-y-1">
          <div className="text-[9px] text-muted">最近失败</div>
          {recent_failures.slice(0, 10).map((f, i) => (
            <div key={i} className="flex items-start gap-1.5 rounded px-1 py-0.5">
              <span className={cn('shrink-0 rounded px-1 py-0.5 text-[9px] font-medium', TOOL_BADGE[f.tool] ?? 'bg-muted text-muted')}>
                {TOOL_LABEL[f.tool] ?? f.tool}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[9px] leading-relaxed text-secondary" title={f.error}>{f.error}</p>
              </div>
              <span className="shrink-0 text-[9px] text-muted">{formatLogTime(f.created_at)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function StatCell({ icon, label, value, cls }: { icon: React.ReactNode; label: string; value: number; cls: string }) {
  return (
    <div className="rounded-btn border border-border/60 bg-base/40 px-1.5 py-1">
      <div className="flex items-center gap-0.5 text-[9px] text-muted">
        {icon}
        <span>{label}</span>
      </div>
      <div className={cn('mt-0.5 text-sm font-bold tabular-nums', cls)}>{value}</div>
    </div>
  )
}
