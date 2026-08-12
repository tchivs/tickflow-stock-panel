import { useEffect, useRef, useState, Suspense } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { useQuoteStream, useQuoteStreamStatus } from '@/lib/useQuoteStream'
import { ToastContainer } from '@/components/Toast'
import { AlertToastContainer } from '@/components/AlertToast'
import { AiAnalysisHost } from '@/components/financials/AiAnalysisHost'
import { AiReportBubble } from '@/components/financials/AiReportBubble'
import { StockAnalysisHost } from '@/components/stock-analysis/StockAnalysisHost'
import { StockAnalysisBubble } from '@/components/stock-analysis/StockAnalysisBubble'
import {
  useCapabilities,
  useSettings,
  usePreferences,
  useQuoteStatus,
  useVersion,
} from '@/lib/useSharedQueries'
import {
  useToggleRealtimeQuotes,
} from '@/lib/useSharedMutations'
import { QK } from '@/lib/queryKeys'
import { tierRank } from '@/lib/capability-labels'
import { providerDatasets, providerDisplayName, isNonTickflow } from '@/lib/dataSources'
import {
  Star,
  ScanSearch,
  History,
  FileText,
  Settings,
  Database,
  Loader2,
  LayoutDashboard,
  Tags,
  TrendingUp,
  Flame,
  BarChart3,
  Sparkles,
  Layers3,
  Landmark,
  Cable,
  RadioTower,
  CheckCircle2,
  ShieldCheck,
  BookOpenCheck,
  ExternalLink,
  Sun,
  Moon,
  X,
  WifiOff,
  Menu,
  WalletCards,
} from 'lucide-react'
import { Logo } from './Logo'
import { api, type IndexQuote } from '@/lib/api'
import { cn } from '@/lib/cn'
import { toggleTheme, useTheme } from '@/lib/theme'
import { setCurrentTotal as setAlertTotal, useUnreadAlerts } from '@/lib/monitorBadge'

// 品牌色 — 只用于 logo / brand 区域,不影响功能语义色
const BRAND = '#8B5CF6'
const TICKFLOW_REGISTER_URL = 'https://tickflow.org/auth/register?ref=V3KDKGXPEA'

const CORE_INDEXES = [
  { symbol: '000001.SH', name: '上证指数' },
  { symbol: '399001.SZ', name: '深证成指' },
  { symbol: '399006.SZ', name: '创业板指' },
  { symbol: '000680.SH', name: '科创综指' },
] as const

type CoreIndex = (typeof CORE_INDEXES)[number]

const nav = [
  { to: '/',                label: '看板',     icon: LayoutDashboard },
  { to: '/watchlist',  label: '自选',   icon: Star },
  { to: '/screener',   label: '策略',   icon: ScanSearch },
  { to: '/pool-hub',    label: '股池',   icon: Layers3 },
  { to: '/backtest',   label: '回测',   icon: History },
  { to: '/stock-analysis',    label: '个股分析', icon: TrendingUp },
  { to: '/limit-ladder', label: '连板梯队', icon: Flame },
  { to: '/concept-analysis', label: '概念分析', icon: Layers3 },
  { to: '/industry-analysis', label: '行业分析', icon: Landmark },
  { to: '/financials', label: '财务分析', icon: FileText },
  { to: '/portfolio', label: '投资组合', icon: WalletCards },
  { to: '/monitor', label: '监控中心', icon: RadioTower },
  { to: '/review',      label: '复盘',   icon: BookOpenCheck },
  { to: '/indices', label: '指数', icon: BarChart3 },
  { to: '/trading', label: '交易', icon: Cable },
  { to: '/data',       label: '数据',   icon: Database },
] as const

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

/** 亮/暗主题切换 — 状态存 localStorage, 生效见 lib/theme.ts */
function ThemeToggle() {
  const theme = useTheme()
  const dark = theme === 'dark'
  return (
    <button
      onClick={() => toggleTheme()}
      className="flex items-center justify-center rounded-btn p-2 text-foreground/80 transition-colors duration-150 ease-smooth hover:bg-elevated hover:text-foreground cursor-pointer"
      title={dark ? '切换到亮色模式' : '切换到暗色模式'}
    >
      {dark ? <Sun className="h-4 w-4 shrink-0" /> : <Moon className="h-4 w-4 shrink-0" />}
    </button>
  )
}

function fmtIndexValue(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return Number(v).toFixed(2)
}

function fmtIndexPct(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return '--'
  return `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}%`
}

function indexPctClass(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return 'text-muted'
  const n = Number(v)
  if (n === 0) return 'text-foreground'
  return n > 0 ? 'text-bull' : 'text-bear'
}

/** 监控中心未读徽标 — 仅在非监控页且有未读时显示。 */
function MonitorBadge({ active }: { active: boolean }) {
  const unread = useUnreadAlerts()
  // 尊重用户设置: 可在菜单设置里关闭数字提示
  const badgeEnabled = (() => {
    try { return localStorage.getItem('monitor_badge_enabled') !== '0' } catch { return true }
  })()
  if (active || unread <= 0 || !badgeEnabled) return null
  return (
    <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[9px] font-bold text-white animate-pulse">
      {unread > 99 ? '99+' : unread}
    </span>
  )
}

function SidebarIndexQuotes({ rows, items }: { rows: IndexQuote[] | undefined; items: CoreIndex[] }) {
  if (items.length === 0) return null
  const quoteBySymbol = new Map((rows ?? []).map(q => [q.symbol, q]))
  return (
    <div className="mt-2 grid grid-cols-2 gap-1.5">
      {items.map(item => {
        const q = quoteBySymbol.get(item.symbol)
        const value = q?.last_price ?? q?.close
        const pct = q?.change_pct
        return (
          <NavLink
            key={item.symbol}
            to={`/indices?symbol=${encodeURIComponent(item.symbol)}`}
            className="block rounded bg-elevated/60 px-2 py-1.5 transition-colors hover:bg-elevated"
            title={`${item.name} ${item.symbol}`}
          >
            <div className="flex items-center justify-between gap-1">
              <span className="text-[10px] text-secondary">{item.name}</span>
              <span className={`text-[10px] font-mono ${indexPctClass(pct)}`}>{fmtIndexPct(pct)}</span>
            </div>
            <div className={`mt-0.5 truncate font-mono text-[10px] ${indexPctClass(pct)}`}>
              {fmtIndexValue(value)}
            </div>
          </NavLink>
        )
      })}
    </div>
  )
}

// ===== 账户与授权卡片 =====
function AccessBadge({ hasTickflowKey, sourceCount }: { hasTickflowKey: boolean; sourceCount: number }) {
  const status = hasTickflowKey
    ? 'TickFlow 已连接'
    : sourceCount > 0
      ? `${sourceCount} 个数据源已接入`
      : '本地模式'
  const statusColor = hasTickflowKey ? 'bg-accent' : sourceCount > 0 ? 'bg-bull' : 'bg-warning'

  return (
    <NavLink
      to="/settings?tab=data-sources"
      className="mt-2.5 group block -mx-2.5"
      title="账户与数据源设置"
    >
      <div className="relative rounded-lg border border-border bg-surface px-3 py-2 transition-colors hover:border-accent/40">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-accent/10 text-accent ring-1 ring-accent/20">
            <ShieldCheck className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-medium text-foreground">账户与授权</span>
              <span className={`h-1.5 w-1.5 rounded-full ${statusColor}`} />
            </div>
            <div className="mt-0.5 truncate text-[10px] leading-tight text-muted">
              {status}
            </div>
          </div>
          <Settings className="h-3 w-3 shrink-0 text-muted group-hover:text-blue-300 transition-colors" />
        </div>

      </div>
    </NavLink>
  )
}

function AIConfigBadge({ configured, model }: { configured?: boolean; model?: string }) {
  return (
    <NavLink
      to="/settings?tab=ai"
      className="mt-2 group block -mx-2.5"
      title="AI 配置"
    >
      <div className="relative rounded-lg border border-border bg-surface px-3 py-2 transition-colors hover:border-accent/40">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-purple-400/10 text-purple-300 ring-1 ring-purple-400/20">
            <Sparkles className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-medium text-foreground">AI 配置</span>
              <span className={`h-1.5 w-1.5 rounded-full ${configured ? 'bg-accent' : 'bg-warning'}`} />
            </div>
            <div className="mt-0.5 truncate text-[10px] leading-tight text-muted">
              {configured ? (model || '已接入模型') : '接入策略生成模型'}
            </div>
          </div>
          <Settings className="h-3 w-3 text-muted group-hover:text-purple-300 transition-colors" />
        </div>
      </div>
    </NavLink>
  )
}

export function Layout() {
  // ===== 共享 hooks (替代内联 useQuery) =====
  const { data: caps } = useCapabilities()
  const { data: settingsState } = useSettings()
  const { data: versionData } = useVersion()
  const { data: prefs } = usePreferences()
  // 数据源列表 (用于实时行情状态显示当前数据源名称)
  const { data: dataSources } = useQuery({
    queryKey: QK.dataSources,
    queryFn: api.dataSources,
    staleTime: 60_000,
  })
  // poll=true: 全局唯一开启条件轮询 (非交易时段 60s 兜底, 交易时段靠 SSE)
  const { data: quoteStatus } = useQuoteStatus({ poll: true })
  const { data: analysisMenus } = useQuery({
    queryKey: QK.analysisMenus,
    queryFn: api.analysisMenus,
  })

  // 数据同步状态轮询: 有活跃 job 时「数据」菜单项显示转圈
  const { data: pipelineJobs } = useQuery({
    queryKey: QK.pipelineJobs,
    queryFn: () => api.pipelineJobs(1),
    refetchInterval: (query) => (query.state.data?.active_id ? 2000 : 15000),
    // 后台不轮询 (与 Dashboard MonitorWidget 同一先例): 切走标签页暂停, 回到前台恢复
  })
  const isDataSyncing = !!pipelineJobs?.active_id

  // 数据同步完成的"瞬时反馈": isDataSyncing 从 true→false 时显示绿色对勾,
  // 闪烁约 3 秒后自动消失。
  const [dataSyncJustDone, setDataSyncJustDone] = useState(false)
  const prevSyncingRef = useRef(false)
  useEffect(() => {
    // 仅在"刚结束"(true→false)且非首次挂载时触发
    if (prevSyncingRef.current && !isDataSyncing) {
      setDataSyncJustDone(true)
      const t = setTimeout(() => setDataSyncJustDone(false), 3000)
      prevSyncingRef.current = isDataSyncing
      return () => clearTimeout(t)
    }
    prevSyncingRef.current = isDataSyncing
  }, [isDataSyncing])

  const qc = useQueryClient()
  const navigate = useNavigate()
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const drawerRef = useRef<HTMLElement>(null)
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches,
  )
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  useEffect(() => {
    const media = window.matchMedia('(max-width: 767px)')
    const syncViewport = () => {
      setIsMobile(media.matches)
      if (!media.matches) setMobileNavOpen(false)
    }
    syncViewport()
    media.addEventListener('change', syncViewport)
    return () => media.removeEventListener('change', syncViewport)
  }, [])

  useEffect(() => {
    if (!isMobile || !mobileNavOpen) return
    const drawer = drawerRef.current
    if (!drawer) return
    const returnFocus = menuButtonRef.current

    const focusFirst = () => {
      const first = drawer.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)
      ;(first ?? drawer).focus()
    }
    const frame = requestAnimationFrame(focusFirst)
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        setMobileNavOpen(false)
        return
      }
      if (event.key !== 'Tab') return
      const focusable = Array.from(drawer.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
        .filter(element => element.offsetParent !== null || element === document.activeElement)
      if (focusable.length === 0) {
        event.preventDefault()
        drawer.focus()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      const activeElement = document.activeElement
      if (event.shiftKey && (activeElement === first || !drawer.contains(activeElement))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (activeElement === last || !drawer.contains(activeElement))) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown, true)
    return () => {
      cancelAnimationFrame(frame)
      document.removeEventListener('keydown', onKeyDown, true)
      returnFocus?.focus()
    }
  }, [isMobile, mobileNavOpen])

  const version = versionData?.version
  const realtimeEnabled = prefs?.realtime_quotes_enabled ?? false
  // Free 档监控限制提示: 可手动关闭, 不持久化 (刷新后恢复显示)
  const [dismissFreeHint, setDismissFreeHint] = useState(false)
  const indicesPinned = prefs?.indices_nav_pinned ?? true
  const sidebarIndexSymbols = prefs?.sidebar_index_symbols ?? CORE_INDEXES.map(p => p.symbol)
  const sidebarIndexes = CORE_INDEXES.filter(item => sidebarIndexSymbols.includes(item.symbol))
  // 卡片数据：固定显示时也拉取（即使实时行情关闭）
  const showSidebarQuotes = indicesPinned || realtimeEnabled
  const { data: sidebarIndexQuotes } = useQuery({
    queryKey: [...QK.indexQuotes, 'sidebar', sidebarIndexSymbols.join(',')] as const,
    queryFn: () => api.indexQuotes(sidebarIndexes.map(p => p.symbol)),
    enabled: showSidebarQuotes && sidebarIndexes.length > 0,
    placeholderData: (prev) => prev,
  })

  // SSE: 行情更新时自动刷新相关 queries + 告警通知
  useQuoteStream(realtimeEnabled, prefs?.sse_refresh_pages)
  // 实时 SSE 连接状态 — 断开时底部显示提示, 提示可能漏策略告警
  const streamStatus = useQuoteStreamStatus()

  const toggleQuote = useToggleRealtimeQuotes()
  const isRunning = quoteStatus?.running ?? false
  const isTrading = quoteStatus?.is_trading_hours ?? false
  // 管道/数据修正运行期间实时行情被临时暂停 — 此时禁止开启
  const isPaused = quoteStatus?.paused ?? false
  const tier = tierRank(caps?.label ?? '')
  const isNoneTier = tier < 0
  const isWatchlistMode = tier === 0
  const realtimeModeLabel = isWatchlistMode ? '自选股' : '全市场'
  // 当前实时行情数据源名称 (非 tickflow 时显示源名)
  const realtimeProvider = prefs?.realtime_data_provider
  const realtimeProviderName = realtimeProvider && realtimeProvider !== 'tickflow'
    ? providerDisplayName(dataSources, realtimeProvider)
    : null

  // 当前日K首选源 (用于菜单底部状态条)。优先读取新配置链，兼容旧单值字段。
  const activeProvider = prefs?.provider_chains?.daily?.[0] || prefs?.daily_data_provider || ''
  const activeProviderName = activeProvider
    ? providerDisplayName(dataSources, activeProvider)
    : '未配置'
  const activeProviderDatasets = providerDatasets(dataSources, activeProvider)
  const isAlternativeActive = isNonTickflow(activeProvider)

  // 轮询触发记录总数 → 更新监控中心徽标 (每 15 秒)
  const alertsTotalQuery = useQuery({
    queryKey: ['alerts-total'],
    queryFn: () => api.alertsList({ days: 7, limit: 1 }),
    refetchInterval: 15000,
    // 后台不轮询 — 徽标仅前台活跃时刷新, 回到前台自动恢复
    select: (data) => data.total,
  })
  // 只在拿到真实总数时同步徽标 (避免 data=undefined 时传 0 重置 lastSeen)
  const alertsTotal = alertsTotalQuery.data
  useEffect(() => {
    if (alertsTotal != null) setAlertTotal(alertsTotal)
  }, [alertsTotal])

  // 合并内置页面 + 可见的扩展分析菜单
  const analysisNav = (analysisMenus?.items ?? [])
    .filter(m => m.visible)
    .map(m => ({ to: `/analysis/${m.id}`, label: m.label, icon: m.icon === 'tags' ? Tags : BarChart3 }))

  const allNav = [...nav, ...analysisNav]
  const savedOrder = prefs?.nav_order ?? []

  const navItems = savedOrder.length > 0
    ? (() => {
        const byTo = new Map(allNav.map(n => [n.to, n]))
        const ordered = savedOrder
          .map(id => byTo.get(id) ?? byTo.get(`/analysis/${id}`))
          .filter(Boolean)
        const seen = new Set(ordered.map(n => n!.to))
        return [...ordered as typeof allNav, ...allNav.filter(n => !seen.has(n.to))]
      })()
    : allNav

  const hiddenIds = new Set(prefs?.nav_hidden ?? [])
  const visibleNavItems = navItems.filter(n => !hiddenIds.has(n.to) && !hiddenIds.has(n.to.replace(/^\/analysis\//, '')))

  const handleToggle = async (enabled: boolean) => {
    // 开启时重新校验档位
    if (enabled) {
      const fresh = await qc.fetchQuery({
        queryKey: QK.capabilities,
        queryFn: api.capabilities,
      })
      const freshTier = tierRank(fresh.label ?? '')
      if (freshTier < 0) return
      if (freshTier === 0 && (prefs?.realtime_watchlist_symbols?.length ?? 0) === 0) {
        navigate('/watchlist')
        return
      }
    }
    await toggleQuote.mutateAsync(enabled)
    // 仅在交易时段立即获取一次行情
    if (enabled && isTrading) {
      api.intradayRefresh().catch(() => {})
    }
  }

  return (
    <div className="h-screen bg-base text-foreground overflow-hidden md:grid md:grid-cols-[14rem_1fr]">
      {/* 跳转链接 (WCAG 2.4.1 Bypass Blocks): 首个可聚焦元素, 键盘用户跳过侧边导航直达内容 */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[9999] focus:rounded-btn focus:bg-accent-solid focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-white focus:shadow-lg"
      >
        跳到主要内容
      </a>
      {isMobile && mobileNavOpen && (
        <button
          type="button"
          aria-label="关闭导航菜单"
          className="fixed inset-0 z-40 bg-black/50"
          onClick={() => setMobileNavOpen(false)}
        />
      )}
      <aside
        ref={drawerRef}
        role={isMobile && mobileNavOpen ? 'dialog' : undefined}
        aria-modal={isMobile && mobileNavOpen ? true : undefined}
        aria-label={isMobile && mobileNavOpen ? '主导航' : undefined}
        aria-hidden={isMobile && !mobileNavOpen ? true : undefined}
        tabIndex={isMobile && mobileNavOpen ? -1 : undefined}
        className={cn(
          'border-r border-border bg-surface flex flex-col h-full min-h-0 overflow-hidden',
          'fixed inset-y-0 left-0 z-50 w-[calc(100vw-2rem)] max-w-56 transition-transform duration-150 md:static md:w-auto md:max-w-none md:translate-x-0',
          isMobile && !mobileNavOpen ? '-translate-x-full invisible' : 'translate-x-0',
        )}
      >
        <div className="px-5 py-5 border-b border-border shrink-0">
          {/* Brand block — 原创 logo + 等宽 wordmark */}
          <div className="flex items-center gap-2.5">
            <Logo
              size={28}
              className="shrink-0 drop-shadow-[0_0_8px_rgba(139,92,246,0.5)]"
              style={{ color: BRAND }}
            />
            <div
              className="font-mono font-bold text-[13px] tracking-[0.06em] text-foreground leading-tight"
              style={{ textShadow: `0 0 10px ${BRAND}44` }}
            >
              <div>AthenaQuant</div>
              <div>Research Terminal</div>
            </div>
          </div>

          <div className="mt-2.5 text-[10px] uppercase tracking-[0.22em] text-secondary">
            Quant · Research Terminal
          </div>

          <div
            className="mt-3 h-px"
            style={{ background: `linear-gradient(90deg, ${BRAND}88, transparent 80%)` }}
          />

          <AccessBadge
            hasTickflowKey={settingsState?.mode !== 'none'}
            sourceCount={
              new Set([
                ...(dataSources?.builtin ?? []).map(source => source.name),
                ...(dataSources?.plugins ?? []).filter(plugin => plugin.available).map(plugin => plugin.name),
                ...(dataSources?.custom ?? []).map(source => source.name),
              ]).size
            }
          />
          <AIConfigBadge
            configured={settingsState?.ai_configured ?? settingsState?.has_ai_key}
            model={settingsState?.ai_model}
          />
        </div>

        <nav id="workspace-navigation" className="flex-1 min-h-0 overflow-y-auto px-2 py-3 space-y-0.5">
          {visibleNavItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => { if (isMobile) setMobileNavOpen(false) }}
              className={({ isActive }) =>
                cn(
                  'flex min-h-11 items-center gap-3 px-3 rounded-btn text-sm transition-colors duration-150 ease-smooth',
                  isActive
                    ? 'bg-elevated text-foreground font-medium'
                    : 'text-foreground/80 hover:bg-elevated hover:text-foreground',
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className="h-4 w-4 shrink-0" />
                  <span className="flex-1">{label}</span>
                  {/* 个股分析 Beta 标识 */}
                  {to === '/stock-analysis' && (
                    <span className="inline-flex items-center rounded-full border border-amber-400/30 bg-amber-400/10 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-400 shrink-0">
                      Beta
                    </span>
                  )}
                  {/* 数据同步状态: 同步中转圈, 刚完成显示绿色对勾闪烁 3 秒 */}
                  {to === '/data' && isDataSyncing && (
                    <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-accent" />
                  )}
                  {to === '/data' && !isDataSyncing && dataSyncJustDone && (
                    <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-bull animate-pulse" />
                  )}
                  {/* 监控中心徽标: 仅非监控页且有未读时显示 */}
                  {to === '/monitor' && <MonitorBadge active={isActive} />}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* 数据源状态条 */}
        <button
          onClick={() => navigate('/settings?tab=data-sources')}
          className="mx-2 mb-1 flex min-h-11 items-center gap-2 rounded-btn px-2.5 text-left transition-colors hover:bg-elevated/60 shrink-0 group"
          title="数据源设置"
        >
          <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${
            isAlternativeActive ? 'bg-accent/15' : 'bg-elevated'
          }`}>
            <Database className={`h-3 w-3 ${isAlternativeActive ? 'text-accent' : 'text-muted'}`} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-medium text-secondary truncate group-hover:text-foreground transition-colors">
                {activeProviderName}
              </span>
              {activeProvider && (
                <span className="shrink-0 rounded bg-accent/15 px-1 py-px text-[8px] font-semibold uppercase tracking-wider text-accent">
                  {isAlternativeActive ? '首选' : '回退'}
                </span>
              )}
            </div>
            <div className="mt-0.5 flex gap-0.5">
              {(['daily', 'adj_factor', 'realtime', 'minute'] as const).map(ds => {
                const active = activeProviderDatasets.includes(ds)
                return (
                  <span
                    key={ds}
                    title={ds}
                    className={`h-1 flex-1 rounded-full transition-colors ${
                      active ? 'bg-accent/60' : 'bg-muted/20'
                    }`}
                  />
                )
              })}
            </div>
          </div>
        </button>

        {/* 全局行情开关 */}
        <div className="border-t border-border px-3 py-2.5 shrink-0">
          {isNoneTier && !realtimeProviderName ? (
            <div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-secondary truncate">实时行情</span>
                <span className="text-[10px] text-accent/70 font-medium bg-accent/10 px-1.5 py-0.5 rounded">
                  Free+
                </span>
              </div>
              <div className="mt-1.5 text-[10px] leading-snug text-muted">
                免费注册
                <a
                  href={TICKFLOW_REGISTER_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="mx-1 inline-flex items-baseline gap-0.5 text-accent/80 hover:text-accent hover:underline"
                >
                  TickFlow
                  <ExternalLink className="h-2.5 w-2.5 self-center" />
                </a>
                开启个股监控
              </div>
            </div>
          ) : (
            /* Starter+ — 开关 + 跳转设置 */
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 min-w-0">
                <span className={`inline-block h-1.5 w-1.5 rounded-full shrink-0 ${
                  realtimeEnabled && isRunning && isTrading
                    ? 'bg-accent animate-pulse'
                    : realtimeEnabled
                      ? 'bg-warning/60'
                      : 'bg-muted'
                }`} />
                <span className="text-xs text-secondary truncate">
                  实时行情 · {realtimeProviderName || realtimeModeLabel}
                </span>
                <button
                  onClick={() => navigate('/settings?tab=monitoring')}
                  className="text-secondary hover:text-foreground transition-colors shrink-0"
                  title="实时监控设置"
                >
                  <Settings className="h-3 w-3" />
                </button>
              </div>
              <button
                onClick={() => handleToggle(!realtimeEnabled)}
                disabled={toggleQuote.isPending || isPaused}
                title={isPaused ? '数据同步运行中，实时行情已临时暂停' : undefined}
                className={`relative inline-flex h-4 w-7 items-center rounded-full shrink-0 transition-colors duration-200 ${
                  realtimeEnabled
                    ? 'bg-accent shadow-[0_0_6px_rgba(59,130,246,0.3)]'
                    : 'bg-elevated'
                } ${toggleQuote.isPending || isPaused ? 'opacity-50' : 'cursor-pointer'}`}
              >
                <span className={`inline-block h-3 w-3 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                  realtimeEnabled ? 'translate-x-[14px]' : 'translate-x-0.5'
                }`} />
              </button>
            </div>
          )}

          {/* 状态提示 */}
          {realtimeEnabled && (!isNoneTier || realtimeProviderName) && (
            <div className="mt-1.5 text-[10px] leading-snug space-y-0.5">
              {isWatchlistMode && !dismissFreeHint && !realtimeProviderName && (
                <div className="flex items-start gap-1 text-amber-400/80">
                  <span className="flex-1">监控自选股前 5 只，全市场监控需 Starter+</span>
                  <button
                    onClick={() => setDismissFreeHint(true)}
                    className="text-amber-400/50 hover:text-amber-400 shrink-0 transition-colors"
                    title="关闭提示"
                  >
                    <X className="h-2.5 w-2.5" />
                  </button>
                </div>
              )}
              {isPaused ? (
                <div className="text-warning/80">数据同步运行中，实时行情已临时暂停</div>
              ) : isRunning && isTrading ? (
                <div className="text-accent">行情运行中</div>
              ) : realtimeEnabled && !isTrading ? (
                <div className="text-warning/70">非交易时段，将在交易时间自动开启</div>
              ) : null}
            </div>
          )}
          {showSidebarQuotes && !isWatchlistMode && !isNoneTier && (
            <SidebarIndexQuotes rows={sidebarIndexQuotes?.rows} items={sidebarIndexes} />
          )}
        </div>

        <div className="border-t border-border px-2 py-3 shrink-0">
          <div className="flex items-center gap-1">
            <ThemeToggle />
            <NavLink
              onClick={() => { if (isMobile) setMobileNavOpen(false) }}
              to="/settings"
              className={({ isActive }) =>
                cn(
                  'flex min-h-11 flex-1 items-center justify-between gap-3 px-3 rounded-btn text-sm transition-colors duration-150 ease-smooth',
                  isActive
                    ? 'bg-elevated text-foreground font-medium'
                    : 'text-foreground/80 hover:bg-elevated hover:text-foreground',
                )
              }
            >
              <span className="flex items-center gap-3">
                <Settings className="h-4 w-4 shrink-0" />
                <span>设置</span>
              </span>
              <span className="font-mono text-[10px] text-muted/50 select-none">
                {version ?? ''}
              </span>
            </NavLink>
          </div>
        </div>
      </aside>

      <motion.main
        id="main-content"
        tabIndex={-1}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
        className="h-full overflow-auto pt-14 scrollbar-gutter-stable md:pt-0"
      >
        <button
          ref={menuButtonRef}
          type="button"
          aria-label="打开导航菜单"
          aria-expanded={mobileNavOpen}
          aria-controls="workspace-navigation"
          className="fixed left-3 top-3 z-30 inline-flex h-11 w-11 items-center justify-center rounded-btn border border-border bg-surface text-foreground shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent md:hidden"
          onClick={() => setMobileNavOpen(true)}
        >
          <Menu className="h-5 w-5" />
        </button>
        {streamStatus === 'reconnecting' && (
          <div
            role="status"
            aria-live="polite"
            className="fixed bottom-4 left-1/2 z-[9998] flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-warning/30 bg-warning/10 px-2.5 py-1 text-[11px] font-medium text-warning shadow-lg backdrop-blur-md"
          >
            <WifiOff className="h-3 w-3 shrink-0 animate-pulse" />
            与服务连接已断开 · 正在重连
          </div>
        )}
        <Suspense
          fallback={
            <div className="flex items-center justify-center py-24">
              <Loader2 className="h-5 w-5 animate-spin text-muted" />
            </div>
          }
        >
          <Outlet />
        </Suspense>
      </motion.main>
      <ToastContainer />
      <AlertToastContainer />
      <AiAnalysisHost />
      <AiReportBubble />
      <StockAnalysisHost />
      <StockAnalysisBubble />
    </div>
  )
}
