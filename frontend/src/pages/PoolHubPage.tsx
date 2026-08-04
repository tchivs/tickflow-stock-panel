import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion, useReducedMotion } from 'framer-motion'
import { Loader2, RefreshCw, ScanSearch } from 'lucide-react'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { StrategyCardGrid } from '@/components/pool-hub/StrategyCardGrid'
import { ConceptFilter } from '@/components/pool-hub/ConceptFilter'
import { StockListTable } from '@/components/pool-hub/StockListTable'
import { GuestModeBanner } from '@/components/pool-hub/GuestModeBanner'

const RESEARCH_FOOTER = '本页面仅用于研究参考，不提供任何交易执行功能。'

export function PoolHubPage() {
  const [activeId, setActiveId] = useState<string | null>(null)
  const [filterText, setFilterText] = useState('')
  const reduceMotion = useReducedMotion()

  // 单 as_of 载荷 (D-02): 卡片计数与明细行来自同一个 strategies 数组, 永不漂移 (PITFALL #10)。
  const hubQuery = useQuery({
    queryKey: QK.poolHub(),
    queryFn: () => api.poolHub(),
    retry: 1,
  })
  // 已知策略全集 — 用于把「无持久化结果」的策略渲染成 数据不可用 卡片 (不参与计数/明细)。
  const strategiesQuery = useQuery({
    queryKey: QK.screenerStrategies('stock'),
    queryFn: () => api.screenerStrategies('stock'),
    staleTime: 5 * 60_000,
    retry: 1,
  })

  const data = hubQuery.data
  const asOf = data?.as_of ?? null
  // 服务端声明的展示模式 (GUEST-01): 只消费 server mode, 绝不从行值推导;
  // 缺失/未知 mode 安全回退 vip — 页面默认不明文掩码。
  const mode = data?.mode === 'guest' ? 'guest' : 'vip'
  // 默认选中第一个策略, 进入页面即可看到明细表
  const activeStrategy =
    data?.strategies.find(s => s.id === activeId) ?? data?.strategies[0] ?? null

  const knownStrategies = useMemo(() => {
    const map = new Map<string, string>()
    for (const p of strategiesQuery.data?.presets ?? []) map.set(p.id, p.name)
    for (const s of data?.strategies ?? []) map.set(s.id, s.name)
    return Array.from(map, ([id, name]) => ({ id, name }))
  }, [strategiesQuery.data, data])

  const filteredRows = useMemo(() => {
    if (!activeStrategy) return []
    const q = filterText.trim().toLowerCase()
    if (!q) return activeStrategy.rows
    return activeStrategy.rows.filter(r =>
      r.concept_board.some(c => c.toLowerCase().includes(q)),
    )
  }, [activeStrategy, filterText])

  const pending = hubQuery.isFetching
  const refresh = () => {
    void hubQuery.refetch()
  }
  const errorText = (err: unknown) =>
    err instanceof Error ? err.message : String(err ?? '未知错误')
  // 后台刷新失败但已有载荷 → 行内明细错误 (stale-while-revalidate)
  const drillError = hubQuery.isError && data && activeStrategy ? errorText(hubQuery.error) : null

  return (
    <>
      <PageHeader
        title="股池"
        subtitle={asOf ? `竞价策略 · 数据日期 ${asOf} · 仅研究参考` : '竞价策略 · 仅研究参考'}
        right={
          <button
            onClick={refresh}
            disabled={pending}
            title="重新读取当前数据日期的股池"
            className="inline-flex items-center gap-1.5 h-9 px-3 rounded-btn
              border border-border bg-surface text-xs font-medium text-secondary
              hover:text-accent hover:border-accent/50 transition-colors cursor-pointer
              disabled:opacity-50 disabled:cursor-wait max-md:min-h-11 max-md:min-w-11"
          >
            {pending
              ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />
              : <RefreshCw className="h-3.5 w-3.5" aria-hidden />}
            刷新股池
          </button>
        }
      />

      <div className="px-4 py-4 space-y-3 sm:px-6 lg:px-8">
        {/* Hub 加载中: 文本 + 骨架占位, 预留布局高度 */}
        {hubQuery.isPending && !data && (
          <div role="status" className="flex flex-col gap-3" aria-live="polite">
            <div className="flex items-center gap-2 text-sm text-muted">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              股池加载中…
            </div>
            <div className="flex flex-wrap gap-2">
              {[0, 1, 2].map(i => (
                <div key={i} className="w-44 h-20 rounded-card border border-border bg-surface animate-pulse" />
              ))}
            </div>
          </div>
        )}

        {/* Hub 加载失败: 危险色容器 + 重试 */}
        {hubQuery.isError && !data && (
          <div role="alert" className="text-sm text-danger bg-danger/10 border border-danger/30 rounded-btn px-3 py-2">
            <span className="mr-2">股池加载失败：{errorText(hubQuery.error)}。请检查数据源后重试。</span>
            <button
              onClick={refresh}
              className="inline-flex items-center h-6 px-2 rounded text-xs font-medium
                bg-surface border border-border text-secondary hover:text-accent hover:border-accent/50 transition-colors cursor-pointer"
            >
              重试
            </button>
          </div>
        )}

        {/* 游客模式横幅 — 会话策略状态: 加载/错误时 mode 未知, 不渲染 (无闪烁) */}
        {data && mode === 'guest' && <GuestModeBanner />}

        {/* 当日无股池结果 */}
        {data && data.strategies.length === 0 && (
          <EmptyState
            icon={ScanSearch}
            title="当日无股池结果"
            hint={`截至 ${asOf ?? '—'}，竞价策略均无命中个股。请先在策略页运行竞价策略，或确认数据日期。`}
          />
        )}

        {/* 有结果: 概念筛选 → 策略卡片 → 钻取明细 */}
        {data && data.strategies.length > 0 && (
          <motion.div
            key={data.as_of ?? 'pool-hub'}
            initial={{ opacity: 0, y: reduceMotion ? 0 : 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: reduceMotion ? 0 : 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="space-y-3"
          >
            <ConceptFilter
              value={filterText}
              onChange={setFilterText}
              onClear={() => setFilterText('')}
            />
            <StrategyCardGrid
              strategies={data.strategies}
              knownStrategies={knownStrategies}
              activeId={activeStrategy?.id ?? null}
              onSelect={setActiveId}
              asOf={asOf}
              counting={pending && !!data}
            />
            {activeStrategy && (
              <section aria-label={`${activeStrategy.name} · 股池明细`} className="space-y-3">
                <h2 className="text-sm font-semibold text-foreground">{activeStrategy.name} · 股池明细</h2>
                <StockListTable
                  mode={mode}
                  strategy={activeStrategy}
                  rows={filteredRows}
                  filterText={filterText}
                  total={activeStrategy.total}
                  loading={pending && !!data}
                  error={drillError}
                  onRetry={refresh}
                  onClearFilter={() => setFilterText('')}
                  resonanceCount={data.resonance_count}
                />
              </section>
            )}
          </motion.div>
        )}

        {/* 研究参考声明 (POOL-03) */}
        <footer className="pt-4 text-xs text-muted">{RESEARCH_FOOTER}</footer>
      </div>
    </>
  )
}
