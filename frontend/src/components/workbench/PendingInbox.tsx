import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { fetchWorkbench } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cn } from '@/lib/cn'

type PendingType = 'lifecycle' | 'promotion' | 'signal' | 'paper_rebalance'

const TYPE_META: Record<PendingType, { label: string; cls: string }> = {
  lifecycle:      { label: '生命周期',  cls: 'bg-accent/15 text-accent' },
  promotion:     { label: '因子晋升',  cls: 'bg-violet-500/15 text-violet-600 dark:text-violet-400' },
  signal:         { label: '信号',      cls: 'bg-amber-500/15 text-amber-600 dark:text-amber-400' },
  paper_rebalance:{ label: '纸面调仓', cls: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400' },
}

/** 待确认收件箱分组行 */
function PendingGroup({
  type,
  items,
  defaultOpen,
}: {
  type: PendingType
  items: Array<Record<string, unknown> & { type: string; link: string }>
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen ?? false)
  const meta = TYPE_META[type]
  return (
    <div className="border-t border-border/60 first:border-t-0">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left hover:bg-base/40 transition-colors"
      >
        {open ? <ChevronDown className="h-3 w-3 text-muted shrink-0" /> : <ChevronRight className="h-3 w-3 text-muted shrink-0" />}
        <span className="text-[11px] font-semibold text-foreground">{meta.label}</span>
        <span className={cn('ml-auto rounded-full px-1.5 py-0.5 text-[10px] font-mono', meta.cls)}>{items.length}</span>
      </button>
      {open && items.length > 0 && (
        <div className="space-y-0.5 px-2.5 pb-2 pt-0.5">
          {items.map((it, i) => {
            const symbol = it.symbol as string | undefined
            const name = it.name as string | undefined
            const canonical = it.canonical_expression as string | undefined
            const label = symbol ?? name ?? canonical ?? meta.label
            return (
              <Link
                key={i}
                to={it.link}
                className="flex items-center gap-1.5 rounded px-1 py-1 text-[10px] text-foreground hover:bg-base/40 transition-colors"
              >
                <span className="h-1 w-1 rounded-full bg-accent/60 shrink-0" />
                <span className="min-w-0 flex-1 truncate">{label}</span>
              </Link>
            )
          })}
        </div>
      )}
      {open && items.length === 0 && (
        <p className="px-2.5 pb-2 pt-0.5 text-center text-[10px] text-muted">暂无待确认</p>
      )}
    </div>
  )
}

/**
 * 待确认收件箱 (Phase 53 WORK-03)
 *
 * 四类待办分组: 生命周期 / 因子晋升 / 信号 / 纸面调仓。
 * 显示各类计数 badge 和可跳转链接, 顶部汇总总数。
 */
export function PendingInbox() {
  const { data } = useQuery({
    queryKey: QK.workbench,
    queryFn: fetchWorkbench,
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  const pending = data?.pending ?? null
  if (!pending || pending.counts.total === 0) return null

  const groups: Record<PendingType, Array<Record<string, unknown> & { type: string; link: string }>> = {
    lifecycle: [],
    promotion: [],
    signal: [],
    paper_rebalance: [],
  }
  for (const it of pending.items) {
    const t = it.type as PendingType
    if (t in groups) groups[t].push(it)
  }

  // 默认展开第一类有数据的分组
  const firstNonEmpty = (Object.keys(groups) as PendingType[]).find(t => groups[t].length > 0)

  return (
    <section className="rounded-card border border-border bg-surface/80 p-1.5 shadow-[0_1px_2px_hsl(var(--border)/0.4)] backdrop-blur-sm">
      <div className="mb-1.5 flex items-center gap-1.5 px-1">
        <span className="h-3 w-0.5 rounded-full bg-gradient-to-b from-accent to-accent/30" />
        <span className="text-xs font-semibold text-foreground">待确认收件箱</span>
        <span className="ml-auto rounded-full bg-accent/15 px-1.5 py-0.5 text-[10px] font-mono text-accent">
          {pending.counts.total}
        </span>
      </div>
      {(Object.keys(TYPE_META) as PendingType[]).map(type => (
        <PendingGroup
          key={type}
          type={type}
          items={groups[type]}
          defaultOpen={type === firstNonEmpty}
        />
      ))}
    </section>
  )
}

