import { useMemo } from 'react'
import { cn } from '@/lib/cn'
import type { PoolHubStrategy } from '@/lib/api'

interface KnownStrategy {
  id: string
  name: string
}

interface StrategyCardGridProps {
  /** 股池载荷里的策略 (计数与明细同源, PITFALL #10) */
  strategies: PoolHubStrategy[]
  /** 已知策略全集 (preset 列表); 缺失的策略渲染 数据不可用 */
  knownStrategies: KnownStrategy[]
  activeId: string | null
  onSelect: (id: string) => void
  asOf: string | null
  /** hub 正在重取 — 计数位展示 股池统计中… 且禁点 */
  counting: boolean
}

/**
 * 股池策略卡片网格 — 只读研究面 (POOL-03): 卡片仅用于钻取, 不暴露任何
 * run/settings/execute 操作。四态: 统计中 / 无命中 / 数据不可用 / active。
 */
export function StrategyCardGrid({
  strategies,
  knownStrategies,
  activeId,
  onSelect,
  asOf,
  counting,
}: StrategyCardGridProps) {
  const hubById = useMemo(() => new Map(strategies.map(s => [s.id, s])), [strategies])
  // 已知全集 = presets ∪ payload, payload 名优先 (策略名可能与 preset 不同)
  const knownById = useMemo(() => {
    const map = new Map<string, string>()
    for (const k of knownStrategies) map.set(k.id, k.name)
    for (const s of strategies) map.set(s.id, s.name)
    return map
  }, [knownStrategies, strategies])

  const cards = Array.from(knownById, ([id, name]) => ({ id, name }))
  // payload 里的策略即使 preset 缺失也要渲染 (保持计数与明细同源)
  for (const s of strategies) {
    if (!knownById.has(s.id)) cards.push({ id: s.id, name: s.name })
  }

  return (
    <section aria-label="策略卡片">
      <div className="flex flex-wrap gap-2">
        {cards.map(card => {
          const hub = hubById.get(card.id)
          const unavailable = !hub
          const active = activeId === card.id
          const disabled = counting || unavailable
          return (
            <span
              key={card.id}
              className={cn('inline-block', unavailable && 'cursor-not-allowed')}
              title={unavailable ? `该策略无 ${asOf ?? '—'} 的持久化结果` : undefined}
            >
              <button
                type="button"
                onClick={() => onSelect(card.id)}
                disabled={disabled}
                aria-disabled={unavailable}
                aria-pressed={active}
                className={cn(
                  'flex flex-col items-start gap-1 w-44 p-3 rounded-card border text-left',
                  'transition-colors duration-150 ease-smooth',
                  active
                    ? 'border-accent bg-accent/5'
                    : 'border-border bg-surface hover:border-accent/40',
                  unavailable && 'opacity-40',
                  disabled && 'cursor-not-allowed',
                )}
              >
                <span className="w-full text-sm font-semibold truncate text-foreground">{card.name}</span>
                <span
                  className={cn(
                    'text-xs',
                    active ? 'text-accent' : 'text-secondary',
                    unavailable && 'text-warning',
                    counting && 'text-muted font-mono',
                  )}
                >
                  {counting
                    ? '股池统计中…'
                    : unavailable
                      ? '数据不可用'
                      : hub!.total === 0
                        ? '当日无命中'
                        : <>当日池 <span className="num tabular-nums">{hub!.total}</span> 只</>}
                </span>
              </button>
            </span>
          )
        })}
      </div>
    </section>
  )
}
