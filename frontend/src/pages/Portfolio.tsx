import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Archive, ChevronDown, CircleHelp, ClipboardList, PieChart, Plus, RefreshCw, Settings2, SlidersHorizontal, WalletCards } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type PortfolioPosition } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { AccountDialog } from '@/components/portfolio/AccountDialog'
import { HoldingCard } from '@/components/portfolio/HoldingCard'
import { HoldingDialog } from '@/components/portfolio/HoldingDialog'
import { HoldingsTable } from '@/components/portfolio/HoldingsTable'
import { EmptyState } from '@/components/EmptyState'
import { PageHeader } from '@/components/PageHeader'
import { Skeleton } from '@/components/data/Skeleton'
import { toast } from '@/components/Toast'
import { AnalysisWorkspace } from '@/components/analysis/AnalysisWorkspace'

function money(value: number | null | undefined) {
  return value == null ? '—' : value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function signedMoney(value: number | null | undefined) {
  if (value == null) return '—'
  return `${value > 0 ? '+' : ''}${money(value)}`
}

function freshness(holdings: PortfolioPosition[]) {
  if (holdings.length === 0) return { label: '暂无法估值', className: 'text-muted', detail: '当前没有可估值持仓。' }
  if (holdings.some(holding => holding.source === 'unavailable')) return { label: '暂无法估值', className: 'text-muted', detail: '至少一笔持仓没有共享报价或最新治理收盘价。' }
  if (holdings.some(holding => holding.source !== 'shared_quote' || !holding.fresh)) {
    const asOf = holdings.find(holding => holding.source !== 'shared_quote' || !holding.fresh)?.as_of?.slice(0, 10) ?? '—'
    return { label: `收盘 · ${asOf}`, className: 'text-warning', detail: '价格来自最新治理收盘价，不是实时行情。' }
  }
  const asOf = holdings[0]?.as_of
  const time = asOf ? new Date(asOf).toLocaleTimeString('zh-CN', { hour12: false }) : '—'
  return { label: `实时 · ${time}`, className: 'text-secondary', detail: '价格来自共享实时行情快照。' }
}

export function Portfolio() {
  const navigate = useNavigate()
  const [showArchived, setShowArchived] = useState(false)
  const [selectedAccountId, setSelectedAccountId] = useState<number | undefined>()
  const [accountDialog, setAccountDialog] = useState<'create' | 'edit' | null>(null)
  const [holdingDialog, setHoldingDialog] = useState<PortfolioPosition | 'create' | null>(null)

  const accountsQuery = useQuery({
    queryKey: QK.portfolioAccounts(showArchived),
    queryFn: () => api.portfolioAccounts(showArchived),
    placeholderData: keepPreviousData,
  })
  const summaryQuery = useQuery({
    queryKey: QK.portfolioSummary(selectedAccountId),
    queryFn: () => api.portfolioSummary(selectedAccountId),
    placeholderData: keepPreviousData,
  })
  const holdingsQuery = useQuery({
    queryKey: QK.portfolioHoldings(selectedAccountId),
    queryFn: () => api.portfolioHoldings(selectedAccountId),
    placeholderData: keepPreviousData,
  })
  const rulesQuery = useQuery({ queryKey: QK.monitorRules, queryFn: api.monitorRulesList, staleTime: 30_000 })

  const accounts = useMemo(() => accountsQuery.data?.accounts ?? [], [accountsQuery.data?.accounts])
  const holdings = useMemo(() => [...(holdingsQuery.data?.positions ?? [])].sort((left, right) => {
    const accountOrder = left.account_id - right.account_id
    return accountOrder || left.instrument_symbol.localeCompare(right.instrument_symbol)
  }), [holdingsQuery.data?.positions])
  const accountNames = useMemo(() => new Map(accounts.map(account => [account.id, account.name])), [accounts])
  const activeRuleCounts = useMemo(() => {
    const counts = new Map<number, number>()
    for (const rule of rulesQuery.data?.rules ?? []) {
      if (!rule.enabled) continue
      for (const positionId of rule.position_ids ?? []) {
        const id = Number(positionId)
        counts.set(id, (counts.get(id) ?? 0) + 1)
      }
    }
    return counts
  }, [rulesQuery.data?.rules])
  const summary = summaryQuery.data
  const freshnessState = freshness(summary?.positions ?? holdings)
  const selectedAccount = selectedAccountId == null ? null : accounts.find(account => account.id === selectedAccountId) ?? null
  const hasAccounts = accounts.some(account => !account.archived_at)
  const isInitialLoading = accountsQuery.isLoading || summaryQuery.isLoading || holdingsQuery.isLoading
  const isError = accountsQuery.isError || summaryQuery.isError || holdingsQuery.isError

  function openNewHolding() {
    if (!hasAccounts) {
      toast('请先新建账户，再添加持仓。', 'error')
      return
    }
    setHoldingDialog('create')
  }

  function retry() {
    accountsQuery.refetch()
    summaryQuery.refetch()
    holdingsQuery.refetch()
  }

  return (
    <div className="min-w-0 pb-8">
      <PageHeader
        title="投资组合"
        className="flex-wrap max-md:px-4"
        right={
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => setAccountDialog('create')} className="inline-flex min-h-8 items-center gap-1.5 rounded-btn border border-border bg-elevated px-3 text-sm text-secondary hover:text-foreground max-md:min-h-11"><Plus className="h-4 w-4" />新建账户</button>
            <button type="button" onClick={openNewHolding} className="inline-flex min-h-10 items-center gap-1.5 rounded-btn bg-accent-solid px-3 text-sm font-semibold text-white disabled:opacity-60 max-md:min-h-11"><Plus className="h-4 w-4" />添加持仓</button>
          </div>
        }
      />
      <nav aria-label="组合研究面板" className="flex flex-wrap items-center gap-2 border-y border-border px-5 py-2 max-md:px-4">
        <span className="text-xs text-muted">研究面板:</span>
        <button type="button" onClick={() => navigate('/portfolio/optimization')} className="inline-flex min-h-8 items-center gap-1.5 rounded-btn border border-border bg-surface px-3 text-xs font-medium text-secondary hover:bg-elevated hover:text-foreground max-md:min-h-11"><SlidersHorizontal className="h-3.5 w-3.5" />优化运行</button>
        <button type="button" onClick={() => navigate('/portfolio/risk-attribution')} className="inline-flex min-h-8 items-center gap-1.5 rounded-btn border border-border bg-surface px-3 text-xs font-medium text-secondary hover:bg-elevated hover:text-foreground max-md:min-h-11"><PieChart className="h-3.5 w-3.5" />风险归因</button>
        <button type="button" onClick={() => navigate('/portfolio/rebalance-plan')} className="inline-flex min-h-8 items-center gap-1.5 rounded-btn border border-border bg-surface px-3 text-xs font-medium text-secondary hover:bg-elevated hover:text-foreground max-md:min-h-11"><ClipboardList className="h-3.5 w-3.5" />再平衡计划</button>
      </nav>
      <div className="space-y-5 p-5 max-md:p-4">
        {isInitialLoading && !summary ? <PortfolioSkeleton /> : isError && !summary ? (
          <div className="rounded-card border border-border bg-surface">
            <EmptyState title="无法读取投资组合。请检查服务连接后重新加载投资组合。" hint="" />
            <div className="flex justify-center pb-8"><button type="button" onClick={retry} className="inline-flex min-h-10 items-center gap-1.5 rounded-btn bg-accent-solid px-4 text-sm font-semibold text-white"><RefreshCw className="h-4 w-4" />重新加载投资组合</button></div>
          </div>
        ) : (
          <>
            <section aria-label="投资组合汇总" className="rounded-card border border-border bg-surface">
              <div className="flex min-w-0 flex-col gap-4 p-4 lg:flex-row lg:items-stretch lg:p-6">
                <dl className="grid min-w-0 flex-1 grid-cols-2 gap-y-4 sm:grid-cols-4 sm:gap-0">
                  <Metric label="总资产" value={money(summary?.total_assets)} strong subline={freshnessState.label} />
                  <Metric label="可用资金" value={money(summary?.available_funds)} subline="账户可用资金" />
                  <Metric label="持仓市值" value={money(summary?.market_value)} subline={freshnessState.label} />
                  <Metric label="未实现盈亏" value={signedMoney(summary?.unrealized_pnl)} valueClass={summary?.unrealized_pnl == null ? 'text-muted' : summary.unrealized_pnl >= 0 ? 'text-bull' : 'text-bear'} subline={freshnessState.label} />
                </dl>
                <button type="button" title={freshnessState.detail} aria-label={`估值新鲜度：${freshnessState.detail}`} className={`inline-flex h-fit items-center gap-1.5 self-start rounded-btn border border-border bg-base px-2.5 py-1.5 text-xs ${freshnessState.className}`}><CircleHelp className="h-3.5 w-3.5" />{freshnessState.label}</button>
              </div>
            </section>
            <section aria-label="账户与持仓" className="space-y-3">
              <div className="flex flex-col gap-2 border-y border-border py-3 sm:flex-row sm:flex-wrap sm:items-center">
                <label className="relative w-full sm:min-w-0 sm:flex-1 sm:max-w-xs" htmlFor="portfolio-account-filter">
                  <span className="sr-only">选择账户</span>
                  <select id="portfolio-account-filter" aria-label="选择账户" value={selectedAccountId ?? ''} onChange={event => setSelectedAccountId(event.target.value ? Number(event.target.value) : undefined)} disabled={accountsQuery.isLoading} className="h-8 w-full appearance-none rounded-btn border border-border bg-surface px-3 pr-8 text-sm text-foreground outline-none focus:border-accent focus:ring-2 focus:ring-accent/30 max-md:min-h-11">
                    <option value="">全部账户{accounts.length ? ` · ${accounts.length}` : ''}</option>
                    {accounts.map(account => <option key={account.id} value={account.id}>{account.name}{account.archived_at ? '（已归档）' : ''}</option>)}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
                </label>
                <div className="grid grid-cols-2 gap-2 sm:contents">
                  <button type="button" onClick={() => setAccountDialog(selectedAccount ? 'edit' : 'create')} className="inline-flex min-h-8 items-center justify-center gap-1.5 rounded-btn border border-border px-3 text-sm text-secondary hover:bg-elevated hover:text-foreground max-md:min-h-11"><Settings2 className="h-4 w-4" />管理账户</button>
                  <button type="button" aria-pressed={showArchived} onClick={() => setShowArchived(value => !value)} className="inline-flex min-h-8 items-center justify-center gap-1.5 rounded-btn px-2 text-sm text-muted hover:bg-elevated hover:text-secondary max-md:min-h-11"><Archive className="h-4 w-4" />{showArchived ? '隐藏已归档' : '显示已归档'}</button>
                </div>
                <span className="text-xs text-muted sm:ml-auto">{freshnessState.label === '暂无法估值' ? '— 暂无法估值' : freshnessState.label.startsWith('实时') ? '● 实时行情' : '● 最新治理收盘价'}</span>
              </div>
              {isError && summary && <p role="status" className="text-sm text-warning">刷新投资组合失败，正在显示上次结果。<button type="button" onClick={retry} className="ml-2 text-accent underline">重新加载投资组合</button></p>}
              {holdingsQuery.isLoading && holdings.length === 0 ? <HoldingSkeletons /> : holdings.length === 0 ? (
                <div className="rounded-card border border-border bg-surface">
                  <EmptyState icon={WalletCards} title="还没有持仓" hint="先新建账户，再添加第一笔持仓。" />
                  <div className="flex justify-center pb-8"><button type="button" onClick={openNewHolding} className="inline-flex min-h-10 items-center gap-1.5 rounded-btn bg-accent-solid px-4 text-sm font-semibold text-white"><Plus className="h-4 w-4" />添加持仓</button></div>
                </div>
              ) : (
                <>
                  <HoldingsTable holdings={holdings} accountNames={accountNames} activeRuleCounts={activeRuleCounts} onEdit={setHoldingDialog} onArchive={setHoldingDialog} onMonitor={holding => navigate(`/monitor?position_id=${holding.id}`)} />
                  <div className="space-y-2 md:hidden">{holdings.map(holding => <HoldingCard key={holding.id} holding={holding} accountName={accountNames.get(holding.account_id) ?? `账户 ${holding.account_id}`} activeRuleCount={activeRuleCounts.get(holding.id) ?? 0} onEdit={setHoldingDialog} onArchive={setHoldingDialog} onMonitor={item => navigate(`/monitor?position_id=${item.id}`)} />)}</div>
                </>
              )}
            </section>
            <section aria-label="账户分析" className="space-y-3">
              {selectedAccount ? <AnalysisWorkspace subject={{ kind: 'portfolio', key: String(selectedAccount.id) }} title={selectedAccount.name} /> : <div className="rounded-card border border-border bg-surface p-4"><h2 className="text-base font-semibold text-foreground">分析结论与证据状态</h2><p className="mt-1 text-sm text-secondary">选择标的或账户后开始证据分析</p><p className="mt-1 text-sm text-muted">分析会显示来源质量、材料数字核验、报告理由与信号历史。</p></div>}
            </section>
          </>
        )}
      </div>
      {accountDialog && <AccountDialog account={accountDialog === 'edit' ? selectedAccount : null} onClose={() => setAccountDialog(null)} />}
      {holdingDialog && <HoldingDialog holding={holdingDialog === 'create' ? null : holdingDialog} accounts={accounts} initialAccountId={selectedAccountId} onClose={() => setHoldingDialog(null)} />}
    </div>
  )
}

function Metric({ label, value, subline, strong, valueClass = 'text-foreground' }: { label: string; value: string; subline: string; strong?: boolean; valueClass?: string }) {
  return <div className="min-w-0 px-3 first:pl-0 sm:border-r sm:border-border sm:last:border-r-0 sm:last:pr-0"><dt className="text-xs text-muted">{label}</dt><dd className={`num mt-1 overflow-hidden text-ellipsis whitespace-nowrap font-semibold ${strong ? 'text-xl' : 'text-base'} ${valueClass}`}>{value}</dd><p className="mt-1 truncate text-xs text-secondary" title={subline}>{subline}</p></div>
}

function PortfolioSkeleton() {
  return <><section className="rounded-card border border-border bg-surface p-5"><div className="grid grid-cols-2 gap-5 sm:grid-cols-4">{Array.from({ length: 4 }, (_, index) => <div key={index} className="space-y-2"><Skeleton w="w-16" h="h-3" /><Skeleton w="w-24" h="h-5" /><Skeleton w="w-20" h="h-3" /></div>)}</div></section><HoldingSkeletons /></>
}

function HoldingSkeletons() {
  return <div className="space-y-2">{Array.from({ length: 8 }, (_, index) => <div key={index} className="h-14 rounded-card border border-border bg-surface px-3 py-3"><Skeleton h="h-3" /></div>)}</div>
}
