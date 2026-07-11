import { Archive, BellRing, Pencil, RadioTower } from 'lucide-react'
import type { PortfolioPosition } from '@/lib/api'

interface HoldingCardProps {
  holding: PortfolioPosition
  accountName: string
  activeRuleCount?: number
  onEdit: (holding: PortfolioPosition) => void
  onArchive: (holding: PortfolioPosition) => void
  onMonitor: (holding: PortfolioPosition) => void
}

const styleLabel: Record<PortfolioPosition['trading_style'], string> = {
  short: '短线',
  swing: '波段',
  long: '长线',
}

function money(value: number | null) {
  return value == null ? '—' : value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function signedMoney(value: number | null) {
  if (value == null) return '—'
  return `${value > 0 ? '+' : ''}${money(value)}`
}

function freshness(holding: PortfolioPosition) {
  if (holding.source === 'unavailable') return '暂无法估值'
  if (holding.source === 'shared_quote' && holding.fresh) return `实时 · ${time(holding.as_of)}`
  if (holding.source === 'governed_close') return `收盘 · ${date(holding.as_of)}`
  return `报价可能已过期 · ${time(holding.as_of)}`
}

function date(value: string | null) {
  return value ? value.slice(0, 10) : '—'
}

function time(value: string | null) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleTimeString('zh-CN', { hour12: false })
}

export function HoldingCard({ holding, accountName, activeRuleCount = 0, onEdit, onArchive, onMonitor }: HoldingCardProps) {
  const latestPrice = holding.market_value == null || holding.quantity <= 0 ? null : holding.market_value / holding.quantity
  const pnlClass = holding.unrealized_pnl == null ? 'text-muted' : holding.unrealized_pnl >= 0 ? 'text-bull' : 'text-bear'

  return (
    <article aria-label={`持仓 ${holding.instrument_symbol}`} className="min-w-0 rounded-card border border-border bg-surface p-4">
      <div className="flex min-w-0 items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="num truncate text-sm font-semibold text-foreground" title={holding.instrument_symbol}>{holding.instrument_symbol}</h2>
          <p className="mt-1 truncate text-xs text-secondary" title={accountName}>{accountName}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="num text-sm font-semibold text-foreground">{latestPrice == null ? '—' : money(latestPrice)}</p>
          <p className={`mt-1 whitespace-nowrap text-xs ${holding.source === 'unavailable' ? 'text-muted' : holding.fresh ? 'text-secondary' : 'text-warning'}`}>{freshness(holding)}</p>
        </div>
      </div>
      <dl className="mt-4 grid grid-cols-3 gap-2 border-y border-border py-3">
        <Value label="成本" value={money(holding.cost_price)} />
        <Value label="市值" value={money(holding.market_value)} />
        <Value label="未实现盈亏" value={signedMoney(holding.unrealized_pnl)} valueClass={pnlClass} />
      </dl>
      <div className="mt-3 flex min-w-0 items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2 text-xs text-secondary">
          <span className="whitespace-nowrap">{styleLabel[holding.trading_style]}</span>
          <span className="inline-flex min-w-0 items-center gap-1 whitespace-nowrap"><BellRing className="h-3.5 w-3.5" />{activeRuleCount} 条启用</span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Action label="编辑持仓" onClick={() => onEdit(holding)}><Pencil className="h-4 w-4" /></Action>
          <Action label="归档持仓" onClick={() => onArchive(holding)}><Archive className="h-4 w-4" /></Action>
          <Action label="前往持仓监控" onClick={() => onMonitor(holding)}><RadioTower className="h-4 w-4" /></Action>
        </div>
      </div>
    </article>
  )
}

function Value({ label, value, valueClass = 'text-foreground' }: { label: string; value: string; valueClass?: string }) {
  return <div className="min-w-0"><dt className="text-xs text-muted">{label}</dt><dd className={`num mt-1 overflow-hidden text-ellipsis whitespace-nowrap text-sm ${valueClass}`}>{value}</dd></div>
}

function Action({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" title={label} aria-label={label} onClick={onClick} className="grid min-h-11 min-w-11 place-items-center rounded-btn text-muted hover:bg-elevated hover:text-foreground">{children}</button>
}
