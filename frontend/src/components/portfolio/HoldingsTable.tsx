import { Archive, BellRing, Pencil, RadioTower } from 'lucide-react'
import type { PortfolioPosition } from '@/lib/api'

interface HoldingsTableProps {
  holdings: PortfolioPosition[]
  accountNames: ReadonlyMap<number, string>
  activeRuleCounts?: ReadonlyMap<number, number>
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

export function HoldingsTable({ holdings, accountNames, activeRuleCounts, onEdit, onArchive, onMonitor }: HoldingsTableProps) {
  return (
    <div className="hidden min-w-0 md:block">
      <table className="w-full table-fixed border-collapse text-sm">
        <thead className="sticky top-0 z-10 bg-surface text-xs text-muted shadow-[0_1px_0_hsl(var(--border))]">
          <tr>
            <Header className="w-[19%] text-left">标的</Header>
            <Header className="hidden w-[11%] text-left xl:table-cell">账户</Header>
            <Header className="hidden w-[7%] text-left xl:table-cell">风格</Header>
            <Header className="w-[12%] text-right xl:w-[7%]">数量</Header>
            <Header className="hidden w-[9%] text-right xl:table-cell">成本价</Header>
            <Header className="w-[13%] text-right xl:w-[9%]">最新价</Header>
            <Header className="w-[14%] text-right xl:w-[10%]">市值</Header>
            <Header className="w-[15%] text-right xl:w-[11%]">未实现盈亏</Header>
            <Header className="w-[11%] text-left xl:w-[8%]">监控</Header>
            <Header className="hidden w-[9%] text-left xl:table-cell">更新</Header>
            <Header className="w-[12%] text-right xl:w-[6%]">操作</Header>
          </tr>
        </thead>
        <tbody>
          {holdings.map(holding => {
            const latestPrice = holding.market_value == null || holding.quantity <= 0 ? null : holding.market_value / holding.quantity
            const pnlClass = holding.unrealized_pnl == null ? 'text-muted' : holding.unrealized_pnl >= 0 ? 'text-bull' : 'text-bear'
            const accountName = accountNames.get(holding.account_id) ?? `账户 ${holding.account_id}`
            const activeRules = activeRuleCounts?.get(holding.id) ?? 0
            return (
              <tr key={holding.id} className="border-b border-border align-middle hover:bg-elevated/50">
                <th scope="row" className="min-w-0 px-2 py-2 text-left font-normal">
                  <span className="num block truncate font-semibold text-foreground" title={holding.instrument_symbol}>{holding.instrument_symbol}</span>
                  <span className="mt-1 block truncate text-xs text-secondary xl:hidden" title={`${accountName} · ${styleLabel[holding.trading_style]}`}>{accountName} · {styleLabel[holding.trading_style]}</span>
                </th>
                <td className="hidden truncate px-2 py-2 text-secondary xl:table-cell" title={accountName}>{accountName}</td>
                <td className="hidden px-2 py-2 text-secondary xl:table-cell">{styleLabel[holding.trading_style]}</td>
                <td className="num px-2 py-2 text-right text-foreground">{money(holding.quantity)}</td>
                <td className="num hidden px-2 py-2 text-right text-foreground xl:table-cell">{money(holding.cost_price)}</td>
                <td className="px-2 py-2 text-right">
                  <span className="num text-foreground">{latestPrice == null ? '—' : money(latestPrice)}</span>
                  <span className={`mt-1 block truncate text-xs xl:hidden ${holding.source === 'unavailable' ? 'text-muted' : holding.fresh ? 'text-secondary' : 'text-warning'}`} title={freshness(holding)}>{freshness(holding)}</span>
                </td>
                <td className="num px-2 py-2 text-right text-foreground">{money(holding.market_value)}</td>
                <td className={`num px-2 py-2 text-right ${pnlClass}`}>{signedMoney(holding.unrealized_pnl)}</td>
                <td className="px-2 py-2">
                  <button type="button" onClick={() => onMonitor(holding)} className="inline-flex max-w-full items-center gap-1 truncate text-secondary hover:text-accent" title="前往持仓监控" aria-label={`查看 ${holding.instrument_symbol} 的持仓监控`}>
                    <BellRing className="h-3.5 w-3.5 shrink-0" /><span className="truncate">{activeRules} 条启用</span>
                  </button>
                </td>
                <td className={`hidden whitespace-nowrap px-2 py-2 text-xs xl:table-cell ${holding.source === 'unavailable' ? 'text-muted' : holding.fresh ? 'text-secondary' : 'text-warning'}`}>{freshness(holding)}</td>
                <td className="px-2 py-2 text-right"><div className="flex justify-end gap-0.5"><Action label="编辑持仓" onClick={() => onEdit(holding)}><Pencil className="h-4 w-4" /></Action><Action label="归档持仓" onClick={() => onArchive(holding)}><Archive className="h-4 w-4" /></Action><Action label="前往持仓监控" onClick={() => onMonitor(holding)}><RadioTower className="h-4 w-4" /></Action></div></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function Header({ children, className }: { children: React.ReactNode; className: string }) {
  return <th scope="col" className={`px-2 py-2 font-normal ${className}`}>{children}</th>
}

function Action({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" title={label} aria-label={label} onClick={onClick} className="grid h-8 w-8 place-items-center rounded-btn text-muted hover:bg-base hover:text-foreground">{children}</button>
}
