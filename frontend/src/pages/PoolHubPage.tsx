import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion, useReducedMotion } from 'framer-motion'
import { AlertTriangle, CalendarX, Clock, Loader2, RefreshCw, ScanSearch, Star } from 'lucide-react'
import { api, type PoolHubResponse } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { fmtDate } from '@/lib/format'
import { storage } from '@/lib/storage'
import { usePremarketPool } from '@/lib/useSharedQueries'
import { useWatchlistBatchAdd } from '@/lib/useSharedMutations'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { StrategyCardGrid } from '@/components/pool-hub/StrategyCardGrid'
import { ConceptFilter } from '@/components/pool-hub/ConceptFilter'
import { StockListTable, AuctionColumnStatusBadge, ConceptAttributionBadge } from '@/components/pool-hub/StockListTable'
import { DateNavigator } from '@/components/pool-hub/DateNavigator'
import { GuestModeBanner } from '@/components/pool-hub/GuestModeBanner'

const RESEARCH_FOOTER = '本页面仅用于研究参考，不提供任何交易执行功能。'

export function PoolHubPage() {
  const [activeId, setActiveId] = useState<string | null>(null)
  const [filterText, setFilterText] = useState('')
  const reduceMotion = useReducedMotion()
  // 当前选中日期: null = 最新 (/api/pool/hub); 非 null = 历史快照 (/api/pool/history, PIT-1)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)

  // 有快照的交易日白名单 (FRONT-01): 驱动 DateNavigator ‹ › 步进与下拉 options
  const datesQuery = useQuery({
    queryKey: QK.poolDates,
    queryFn: api.poolDates,
    retry: 1,
  })

  // 单 as_of 载荷 (D-02): 卡片计数与明细行来自同一个 strategies 数组, 永不漂移 (PITFALL #10)。
  // 按 selectedDate 切换数据源: 历史必走 /api/pool/history, 最新走 /api/pool/hub (PIT-1)。
  // placeholderData 同款 Dashboard: 切换日期保留旧数据, 防整页闪空; 副标题以旧载荷真实 as_of 为准 (诚实)。
  const poolQuery = useQuery({
    queryKey: selectedDate ? QK.poolHistory(selectedDate) : QK.poolHub(),
    queryFn: () => (selectedDate ? api.poolHistory(selectedDate) : api.poolHub()),
    retry: 1,
    placeholderData: (prev) => prev,
  })

  // PM-04 盘前预览 (Phase 27): 仅「最新」视图 (selectedDate == null) 启用。
  // 判定: 今日盘前预览 available===true ∧ window==='pre_open' ∧ 今日 EOD 快照未生成 (today ∉ dates)
  // → showPremarket 渲染预览池 (payload 为 hub 同形状, 复用既有渲染);
  //   15:35 EOD 后 (today ∈ dates) → showPremarket false → 回退 /api/pool/hub 既有流。
  const viewingToday = selectedDate == null
  const premarketQuery = usePremarketPool({ enabled: viewingToday })
  const todayStr = fmtDate(new Date())
  const hasTodayEod = (datesQuery.data?.dates ?? []).includes(todayStr)
  const showPremarket = viewingToday
    && premarketQuery.data?.available === true
    && premarketQuery.data.window === 'pre_open'
    && !hasTodayEod
  const showPremarketEmpty = viewingToday
    && premarketQuery.data?.available === false
    && !hasTodayEod
  // 已知策略全集 — 用于把「无持久化结果」的策略渲染成 数据不可用 卡片 (不参与计数/明细)。
  const strategiesQuery = useQuery({
    queryKey: QK.screenerStrategies('stock'),
    queryFn: () => api.screenerStrategies('stock'),
    staleTime: 5 * 60_000,
    retry: 1,
  })

  // PM-04: 预览 payload 是 hub 同形状投影 (27-01 _project_hub) → 既有 asOf/mode/activeStrategy/
  // StrategyCardGrid/ConceptFilter/StockListTable 渲染路径全部复用。
  const data = showPremarket ? (premarketQuery.data as PoolHubResponse) : poolQuery.data
  // 诚实 as_of: 占位期 (key 切换未落地) 显示旧载荷真实 as_of, 绝不伪造目标日期的 as_of (PIT-2/H4)
  const asOf = data?.as_of ?? selectedDate ?? null
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

  // WATCH-03 自选体系 (纯复用): 单一事实来源 = 服务端 watchlist.parquet + 共享 QK.watchlist 缓存。
  // 查询双门控 (RESEARCH D4/P2): mode 由 data?.mode 派生 (未加载回退 vip), 故必须 !!data 且 mode === 'vip'
  // 双条件, 否则 guest 首屏误发 /api/watchlist → 401 → main.tsx 全局跳登录 (最高危)。
  const qc = useQueryClient()
  const [watchlistOnly, setWatchlistOnly] = useState(() => storage.poolWatchlistOnly.get(false))
  const [batchMsg, setBatchMsg] = useState('')
  const watchlist = useQuery({
    queryKey: QK.watchlist,
    queryFn: api.watchlistList,
    enabled: !!data && mode === 'vip',
  })
  // join 键 = 全后缀 symbol 精确全等 (WATCH-03/H6), 无归一化/无 code 匹配
  const watchlistSet = useMemo(
    () => new Set((watchlist.data?.symbols ?? []).map((s: any) => s.symbol)),
    [watchlist.data],
  )
  // 单只星标 toggle (Screener.tsx:440-447 逐字先例) — 成功失效双 key, 跨页一致 (WATCH-03)
  const toggleWatchlist = useMutation({
    mutationFn: ({ symbol, inList }: { symbol: string; inList: boolean }) =>
      inList ? api.watchlistRemove(symbol) : api.watchlistAdd(symbol),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.watchlist })
      qc.invalidateQueries({ queryKey: QK.watchlistEnriched() })
    },
  })
  // WATCH-04 批量加自选 (useWatchlistBatchAdd 已封装双 key 失效): scope = 可见行 filteredRows (display_limit 内, 绝不按 total)
  const batchAdd = useWatchlistBatchAdd()
  // WATCH-04 选择集 (LG-04): join 键 = 全后缀 symbol (与星标/只看自选同键)。
  // Clear-on-change (诚实语义): 策略/筛选/只看自选/日期任一变化 → 清空, 无跨视图 stale selection (T-35-02-05)。
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const handleStrategySelect = (id: string) => {
    setSelected(new Set())
    setActiveId(id)
  }
  const handleFilterChange = (v: string) => {
    setSelected(new Set())
    setFilterText(v)
  }
  const handleClearFilter = () => {
    setSelected(new Set())
    setFilterText('')
  }
  const handleDateChange = (d: string | null) => {
    setSelected(new Set())
    setSelectedDate(d)
  }
  const handleWatchlistOnlyToggle = () => {
    setSelected(new Set())
    const v = !watchlistOnly
    setWatchlistOnly(v)
    storage.poolWatchlistOnly.set(v)
  }
  // 表头全选/全不选可见行: 全选态由 StockListTable 从 rows ∩ selection 派生后回调 toggle
  const handleToggleSelectAll = () => {
    setSelected(prev => {
      const visible = filteredRows.map(r => r.symbol)
      const all = visible.length > 0 && visible.every(s => prev.has(s))
      const next = new Set(prev)
      if (all) {
        for (const s of visible) next.delete(s)
      } else {
        for (const s of visible) next.add(s)
      }
      return next
    })
  }
  const handleToggleSelection = (symbol: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(symbol)) next.delete(symbol)
      else next.add(symbol)
      return next
    })
  }
  const handleBatchAdd = () => {
    // WATCH-04 scope=选中行 (LG-04): 防御性 intersect 可见行 — 勾选行已不在当前可见集 → 剔除; 空选不发请求不 toast
    const symbols = [...selected].filter(s => filteredRows.some(r => r.symbol === s))
    if (!symbols.length) return
    batchAdd.mutate(symbols, {
      onSuccess: (data) => {
        setBatchMsg(`已添加 ${data.added} 只到自选`)
        setTimeout(() => setBatchMsg(''), 3000)
      },
      onError: () => {
        setBatchMsg('批量添加失败')
        setTimeout(() => setBatchMsg(''), 3000)
      },
    })
  }

  const filteredRows = useMemo(() => {
    if (!activeStrategy) return []
    const q = filterText.trim().toLowerCase()
    // 概念子串投影 (既有) + 「只看自选」AND 组合 (WATCH-02) — 结果新数组引用, 绝不原地改 activeStrategy.rows
    let base = q
      ? activeStrategy.rows.filter(r =>
          r.concept_board.some(c => c.toLowerCase().includes(q)),
        )
      : activeStrategy.rows
    if (watchlistOnly) base = base.filter(r => watchlistSet.has(r.symbol))
    return base
  }, [activeStrategy, filterText, watchlistOnly, watchlistSet])

  const pending = poolQuery.isFetching
  const refresh = () => {
    void poolQuery.refetch()
  }
  const errorText = (err: unknown) =>
    err instanceof Error ? err.message : String(err ?? '未知错误')
  // 后台刷新失败但已有载荷 → 行内明细错误 (stale-while-revalidate)
  const drillError = poolQuery.isError && data && activeStrategy ? errorText(poolQuery.error) : null

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
        {/* 日期导航 — 按交易日浏览股池 (FRONT-01); 白名单下标步进, 非交易日物理不可达 (PIT-5) */}
        <DateNavigator
          dates={datesQuery.data?.dates ?? []}
          latest={datesQuery.data?.latest ?? null}
          selectedDate={selectedDate}
          loading={datesQuery.isPending}
          error={datesQuery.isError ? errorText(datesQuery.error) : null}
          onRetry={() => void datesQuery.refetch()}
          onChange={handleDateChange}
        />

        {/* Hub 加载中: 文本 + 骨架占位, 预留布局高度 */}
        {poolQuery.isPending && !data && (
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
        {poolQuery.isError && !data && (
          <div role="alert" className="text-sm text-danger bg-danger/10 border border-danger/30 rounded-btn px-3 py-2">
            <span className="mr-2">股池加载失败：{errorText(poolQuery.error)}。请检查数据源后重试。</span>
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

        {/* PM-04 盘前预览窗口标注 (诚实标注: 预览 ≠ 收盘定稿; degraded → 追加仅派生列警告) */}
        {showPremarket && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs" role="note">
            <span className="inline-flex items-center gap-1.5 font-medium text-accent">
              <Clock className="h-3.5 w-3.5 shrink-0" aria-hidden />
              盘前预览 · 竞价窗口 09:15-09:25 · 非收盘定稿
            </span>
            {premarketQuery.data?.degraded === true && (
              <span className="inline-flex items-center gap-1.5 font-medium text-warning">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden />
                仅派生列 · 竞价数据源未配置
              </span>
            )}
          </div>
        )}

        {/* PM-04 盘前预览诚实空态 (200 语义, 非 404, 非零池伪装): 今日预览尚未生成且今日 EOD 未落 */}
        {showPremarketEmpty && (
          <EmptyState
            icon={CalendarX}
            title="今日盘前预览尚未生成"
            hint="09:26 盘前预览 job 尚未生成今日预览。可查看历史收盘快照或稍后刷新。"
          />
        )}

        {/* 无快照日 (200 语义, PIT-2): 先于零池分支短路 — 独立诚实空态, 绝不伪装零池 */}
        {data && data.available === false && !showPremarketEmpty && (
          <EmptyState
            icon={CalendarX}
            title="该日期无股池快照"
            hint={`${selectedDate ?? ''} 无股池快照（非交易日或尚未生成）。请选择其他日期或返回最新。`}
          />
        )}

        {/* 当日无股池结果 (零池语义, 保留) — available:false 时短路 (PIT-2: 无快照 ≠ 零池); PM-04: 盘前空态优先 */}
        {data && data.available !== false && data.strategies.length === 0 && !showPremarketEmpty && (
          <EmptyState
            icon={ScanSearch}
            title="当日无股池结果"
            hint={`截至 ${asOf ?? '—'}，竞价策略均无命中个股。请先在策略页运行竞价策略，或确认数据日期。`}
          />
        )}

        {/* 有结果: 概念筛选 → 策略卡片 → 钻取明细 (PM-04: 盘前空态优先, 盘前预览缺失时不混排 hub 流) */}
        {data && data.strategies.length > 0 && !showPremarketEmpty && (
          <motion.div
            key={data.as_of ?? 'pool-hub'}
            initial={{ opacity: 0, y: reduceMotion ? 0 : 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: reduceMotion ? 0 : 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="space-y-3"
          >
            <ConceptFilter
              value={filterText}
              onChange={handleFilterChange}
              onClear={handleClearFilter}
            />
            <StrategyCardGrid
              strategies={data.strategies}
              knownStrategies={knownStrategies}
              activeId={activeStrategy?.id ?? null}
              onSelect={handleStrategySelect}
              asOf={asOf}
              counting={pending && !!data}
            />
            {activeStrategy && (
              <section aria-label={`${activeStrategy.name} · 股池明细`} className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-sm font-semibold text-foreground">{activeStrategy.name} · 股池明细</h2>
                  {/* WATCH-02/04 钻取区 header 控件 — 仅 VIP 渲染 (guest 零新控件, H3) */}
                  {mode === 'vip' && (
                    <div className="flex items-center gap-2">
                      {/* 「只看自选」switch (WATCH-02): 双态 + aria + H9 fail-closed 禁用 + storage 持久化; 移动端 44px 触控目标 */}
                      <div className="inline-flex max-md:h-11 max-md:w-11 max-md:items-center max-md:justify-center">
                        <button
                          type="button"
                          role="switch"
                          aria-checked={watchlistOnly}
                          aria-label="只看自选"
                          title={watchlist.isError ? '自选清单加载失败' : '只看自选'}
                          disabled={watchlist.isPending || watchlist.isError}
                          onClick={handleWatchlistOnlyToggle}
                          className={`relative inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors duration-200 disabled:opacity-50 ${watchlistOnly ? 'bg-accent' : 'bg-border'}`}
                        >
                          <span className={'inline-block h-3 w-3 transform rounded-full bg-white shadow transition-transform duration-200 ' + (watchlistOnly ? 'translate-x-3.5' : 'translate-x-0.5')} />
                        </button>
                      </div>
                      {/* 「批量加自选」(WATCH-04, LG-04): scope = 选中行; 空选禁用; watchlistOnly 开启时隐藏 (可见行全在自选, D6) */}
                      {!watchlistOnly && (
                        <button
                          type="button"
                          onClick={handleBatchAdd}
                          disabled={batchAdd.isPending || selected.size === 0}
                          aria-label="批量加自选"
                          title="批量加自选"
                          className="inline-flex items-center gap-1.5 h-9 px-3 rounded-btn border border-border bg-surface text-xs font-medium text-secondary hover:text-accent hover:border-accent/50 transition-colors cursor-pointer disabled:opacity-50 max-md:min-h-11 max-md:min-w-11"
                        >
                          <Star className="h-3.5 w-3.5" aria-hidden />
                          {batchAdd.isPending ? '添加中…' : '批量加自选'}
                        </button>
                      )}
                      {batchMsg && <span role="status" className="text-xs text-accent">{batchMsg}</span>}
                    </div>
                  )}
                </div>
                {/* 竞价列诚实状态徽标 (UI-SPEC §3.3): 仅 VIP 且服务端透传 auction_columns 时渲染 (H3 双轨) */}
                {data?.auction_columns && (
                  <AuctionColumnStatusBadge
                    auctionColumns={data.auction_columns}
                    asOf={asOf}
                    degraded={showPremarket ? premarketQuery.data?.degraded : undefined}
                  />
                )}
                {/* 概念归属诚实徽标 (CONCEPT-04/07): 服务端冻结 attribution 驱动; 载荷缺键 (guest/旧后端) → 零渲染 */}
                {data?.concept_attribution && (
                  <ConceptAttributionBadge
                    attribution={data.concept_attribution}
                    effectiveDate={data.concept_effective_date ?? null}
                  />
                )}
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
                  auctionColumns={data?.auction_columns ?? null}
                  watchlistSet={watchlistSet}
                  onToggleWatchlist={(symbol, inList) => toggleWatchlist.mutate({ symbol, inList })}
                  watchlistPending={toggleWatchlist.isPending || watchlist.isPending || watchlist.isError}
                  watchlistOnly={watchlistOnly}
                  selection={selected}
                  onToggleSelection={handleToggleSelection}
                  onToggleSelectAll={handleToggleSelectAll}
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
