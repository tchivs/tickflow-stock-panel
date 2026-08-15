import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { X, RefreshCw, Clock, Gavel, Zap, ArrowUpRight } from 'lucide-react'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { cnSignal } from '@/lib/signals'
import { StockPanel, getDefaultRange } from '@/components/StockPanel'
import { StockMultiDayIntradayChart } from '@/components/StockMultiDayIntradayChart'
import { DatePicker } from '@/components/DatePicker'
import { RuleEditor } from '@/components/monitor/RuleEditor'
import { PriceAlertDialog } from '@/components/stock-analysis/PriceAlertDialog'
import { buildMonitorPriceLines } from '@/lib/price-alerts'
import { storage } from '@/lib/storage'
import { boardTag } from '@/components/stock-table/primitives'

interface Props {
  symbol: string | null
  name?: string
  onClose: () => void
  /** 触发信息 (来自监控触发记录, 有值时在顶栏下方显示) */
  triggerInfo?: {
    price?: number | null
    changePct?: number | null
    ts?: number
    signals?: string[]
    message?: string
  } | null
}

// ===== 板块标识 (统一由 stock-table/primitives boardTag 提供, 全站唯一实现) =====

// ===== 预设快捷范围（只保留半年和1年） =====
const PRESETS: { label: string; months: number }[] = [
  { label: '半年', months: 6 },
  { label: '1年', months: 12 },
]

interface PriceAlertDraft {
  id: number
  targetPrice: number
  currentPrice: number
}

const INTRADAY_DAY_OPTIONS = [1, 5, 10, 20] as const

function loadIntradayDays(): number {
  const saved = storage.stockPreviewIntradayDays.get(5)
  return INTRADAY_DAY_OPTIONS.includes(saved as typeof INTRADAY_DAY_OPTIONS[number])
    ? (saved as number)
    : 5
}

// 焦点陷阱可选聚焦元素 (同 Modal 原语)
const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export function StockPreviewDialog({ symbol, name, onClose, triggerInfo }: Props) {
  const [showIntraday, setShowIntraday] = useState(false)
  // Phase 26 CHART-02 竞价历史图开关 (与分时独立)
  const [showAuction, setShowAuction] = useState(false)
  const [dateRange, setDateRange] = useState(getDefaultRange)
  const [showMonitorEditor, setShowMonitorEditor] = useState(false)
  const [priceAlertDraft, setPriceAlertDraft] = useState<PriceAlertDraft | null>(null)
  const [intradayDays, setIntradayDays] = useState(loadIntradayDays)
  const qc = useQueryClient()

  const panelRef = useRef<HTMLDivElement>(null)
  const closeBtnRef = useRef<HTMLButtonElement>(null)
  const restoreFocusRef = useRef<HTMLElement | null>(null)

  // 打开: 捕获触发元素并把焦点移入对话框 (关闭按钮)
  useEffect(() => {
    if (!symbol) return
    restoreFocusRef.current = document.activeElement as HTMLElement | null
    closeBtnRef.current?.focus()
  }, [symbol])

  // 关闭: 焦点还给触发元素
  useEffect(() => {
    if (symbol) return
    restoreFocusRef.current?.focus?.()
    restoreFocusRef.current = null
  }, [symbol])

  // Tab / Shift+Tab 焦点陷阱: 焦点不逃出对话框
  const handlePanelKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key !== 'Tab') return
    const panel = panelRef.current
    if (!panel) return
    const focusables = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE))
      .filter(el => el.getClientRects().length > 0)
    if (focusables.length === 0) return
    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }, [])

  const watchlist = useQuery({
    queryKey: QK.watchlist,
    queryFn: api.watchlistList,
    enabled: !!symbol,
  })
  const inWatchlist = (watchlist.data?.symbols ?? []).some((s: any) => s.symbol === symbol)

  // 点位监控: 已启用规则以横虚线显示在日K/分时图上, 双击主图创建/预填
  const monitorRules = useQuery({
    queryKey: QK.monitorRules,
    queryFn: api.monitorRulesList,
    enabled: !!symbol,
  })
  const monitorPriceLines = useMemo(
    () => symbol ? buildMonitorPriceLines(monitorRules.data?.rules ?? [], symbol) : [],
    [monitorRules.data?.rules, symbol],
  )

  const openPriceAlert = (targetPrice: number, currentPrice: number) => {
    setPriceAlertDraft({ id: Date.now(), targetPrice, currentPrice })
  }

  const toggleWatchlist = useMutation({
    mutationFn: () => inWatchlist ? api.watchlistRemove(symbol!) : api.watchlistAdd(symbol!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.watchlist })
      qc.invalidateQueries({ queryKey: QK.watchlistEnriched() })
    },
  })

  // ESC 关闭 (点位编辑弹层打开时由 PriceAlertDialog 自行处理)
  useEffect(() => {
    if (!symbol) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !priceAlertDraft) onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [symbol, onClose, priceAlertDraft])

  const handleRefresh = () => {
    if (!symbol) return
    qc.invalidateQueries({ queryKey: ['kline', symbol!] })
    if (showIntraday) {
      qc.invalidateQueries({ queryKey: ['kline-minute', symbol!] })
    }
  }

  return (
    <AnimatePresence>
      {symbol && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* 遮罩 */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* 弹窗主体 */}
          <motion.div
            ref={panelRef}
            onKeyDown={handlePanelKeyDown}
            role="dialog"
            aria-modal="true"
            aria-label={`个股详情 ${symbol}${name ? ` ${name}` : ''}`}
            tabIndex={-1}
            initial={{ opacity: 0, scale: 0.95, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 8 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="relative w-[92vw] max-w-[1100px] max-h-[95vh] rounded-dialog border border-border bg-base shadow-2xl overflow-hidden flex flex-col"
          >
            {/* 顶栏 */}
            <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 px-5 py-3 border-b border-border shrink-0">
              <div className="flex items-center gap-2 min-w-0">
                {(() => {
                  const board = symbol ? boardTag(symbol) : null
                  return board ? (
                    <span className={`shrink-0 inline-flex items-center justify-center w-[18px] h-[18px] rounded text-[9px] font-bold leading-none border ${board.color}`}>
                      {board.label}
                    </span>
                  ) : null
                })()}
                <span className="font-mono text-sm font-medium text-foreground">{symbol}</span>
                {name && <span className="text-xs text-muted truncate">{name}</span>}
              </div>

              <div className="flex flex-wrap items-center justify-end gap-1.5 max-w-full">
                {/* 升级到个股分析页 (详情漏斗: 预览 → 完整分析) */}
                {symbol && (
                  <Link
                    to={`/stock-analysis?symbol=${encodeURIComponent(symbol)}&name=${encodeURIComponent(name ?? '')}`}
                    onClick={onClose}
                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs text-accent border border-accent/30 bg-accent/10 hover:bg-accent/20 transition-colors"
                  >
                    <ArrowUpRight className="h-3 w-3" aria-hidden />
                    个股分析
                  </Link>
                )}
                {/* 日期范围快捷 */}
                {PRESETS.map(p => {
                  const now = new Date()
                  const s = new Date(now)
                  s.setMonth(s.getMonth() - p.months)
                  const expected = s.toISOString().slice(0, 10)
                  const isActive = dateRange.start === expected
                  return (
                    <button
                      key={p.label}
                      onClick={() => {
                        const end = new Date().toISOString().slice(0, 10)
                        const ns = new Date()
                        ns.setMonth(ns.getMonth() - p.months)
                        setDateRange({ start: ns.toISOString().slice(0, 10), end })
                      }}
                      className={`h-6 max-md:h-9 px-1.5 rounded text-[11px] transition-colors cursor-pointer
                        ${isActive
                          ? 'bg-accent/20 text-accent font-medium border border-accent/30'
                          : 'text-muted hover:text-foreground hover:bg-elevated border border-transparent'
                        }`}
                    >
                      {p.label}
                    </button>
                  )
                })}
                <DatePicker
                  value={dateRange.start}
                  onChange={(v) => setDateRange(prev => ({ ...prev, start: v }))}
                  max={dateRange.end}
                />
                <span className="text-muted/40 text-[10px]">~</span>
                <DatePicker
                  value={dateRange.end}
                  onChange={(v) => setDateRange(prev => ({ ...prev, end: v }))}
                  min={dateRange.start}
                />

                <span className="text-muted/20 mx-0.5">|</span>

                {/* 分时开关 */}
                <button
                  onClick={() => setShowIntraday((v) => !v)}
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs transition-colors ${
                    showIntraday
                      ? 'bg-accent/15 text-accent border border-accent/30'
                      : 'bg-elevated text-secondary border border-border hover:border-accent/30'
                  }`}
                >
                  <Clock className="h-3 w-3" />
                  分时
                </button>

                {/* 分时天数切换 (1/5/10/20 日) */}
                {showIntraday && (
                  <div className="inline-flex h-6 items-center overflow-hidden rounded border border-border bg-elevated">
                    {INTRADAY_DAY_OPTIONS.map(days => (
                      <button
                        key={days}
                        onClick={() => {
                          setIntradayDays(days)
                          storage.stockPreviewIntradayDays.set(days)
                        }}
                        aria-pressed={intradayDays === days}
                        className={`px-1.5 text-[11px] leading-none transition-colors cursor-pointer ${
                          intradayDays === days
                            ? 'bg-accent/15 text-accent'
                            : 'text-muted hover:text-foreground'
                        }`}
                      >
                        {days}日
                      </button>
                    ))}
                  </div>
                )}

                <span className="text-muted/20 mx-0.5">|</span>

                {/* 竞价历史开关 (CHART-02) */}
                <button
                  onClick={() => setShowAuction((v) => !v)}
                  aria-pressed={showAuction}
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs transition-colors ${
                    showAuction
                      ? 'bg-accent/15 text-accent border border-accent/30'
                      : 'bg-elevated text-secondary border border-border hover:border-accent/30'
                  }`}
                >
                  <Gavel className="h-3 w-3" />
                  竞价历史
                </button>

                <span className="text-muted/20 mx-0.5">|</span>

                {/* 刷新 */}
                <button
                  onClick={handleRefresh}
                  className="p-1 max-md:min-h-11 max-md:min-w-11 rounded-btn text-secondary hover:text-foreground hover:bg-elevated transition-colors"
                  aria-label="刷新"
                  title="刷新"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                </button>

                {/* 关闭 */}
                <button
                  ref={closeBtnRef}
                  onClick={onClose}
                  className="p-1 max-md:min-h-11 max-md:min-w-11 rounded-btn text-secondary hover:text-foreground hover:bg-elevated transition-colors"
                  aria-label="关闭"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* 触发信息条 (来自监控触发记录) */}
            {triggerInfo && (
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-amber-400/20 bg-amber-400/[0.06] px-5 py-2 shrink-0">
                {/* 左: 触发标记 + 时间 */}
                <div className="flex items-center gap-2 shrink-0">
                  <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-amber-400">
                    <Zap className="h-3 w-3" aria-hidden />
                    触发
                  </span>
                  {triggerInfo.ts && (
                    <span className="text-[11px] text-secondary font-mono">
                      {new Date(triggerInfo.ts).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                    </span>
                  )}
                </div>

                {/* 中: 价格 + 涨跌幅 */}
                <div className="flex items-center gap-2 shrink-0">
                  {triggerInfo.price != null && (
                    <span className="text-[11px] font-mono text-foreground/80">{triggerInfo.price.toFixed(2)}</span>
                  )}
                  {triggerInfo.changePct != null && (
                    <span className={`text-[11px] font-mono font-medium ${triggerInfo.changePct >= 0 ? 'text-bull' : 'text-bear'}`}>
                      {triggerInfo.changePct >= 0 ? '+' : ''}{(triggerInfo.changePct * 100).toFixed(2)}%
                    </span>
                  )}
                </div>

                {/* 右: 消息 + 信号标签 */}
                <div className="flex items-center gap-2 flex-wrap min-w-0">
                  {triggerInfo.message && (
                    <span className="text-[11px] text-foreground/70 truncate">{triggerInfo.message}</span>
                  )}
                  {triggerInfo.signals && triggerInfo.signals.length > 0 && (
                    <div className="flex items-center gap-1 flex-wrap">
                      {triggerInfo.signals.map((s, j) => (
                        <span key={j} className="rounded bg-accent/10 px-1.5 py-0.5 text-[9px] text-accent/80">{cnSignal(s)}</span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* K 线内容 */}
            <div className="flex-1 overflow-auto p-4">
              {showIntraday && intradayDays > 1 ? (
                <>
                  <StockPanel
                    symbol={symbol}
                    height={420}
                    showIntraday={false}
                    showAuction={false}
                    onSelectDate={() => { if (!showIntraday) setShowIntraday(true) }}
                    dateRange={dateRange}
                    infoBarOnly
                    onMonitor={() => setShowMonitorEditor(true)}
                    inWatchlist={inWatchlist}
                    onToggleWatchlist={() => toggleWatchlist.mutate()}
                  />
                  <StockMultiDayIntradayChart
                    symbol={symbol}
                    days={intradayDays}
                    height={480}
                    refetchIntervalMs={undefined}
                    priceLines={monitorPriceLines}
                    onPriceDoubleClick={openPriceAlert}
                  />
                </>
              ) : (
                <StockPanel
                  symbol={symbol}
                  height={420}
                  showIntraday={showIntraday}
                  showAuction={showAuction}
                  onSelectDate={() => { if (!showIntraday) setShowIntraday(true) }}
                  dateRange={dateRange}
                  priceLines={monitorPriceLines}
                  onPriceDoubleClick={openPriceAlert}
                  onMonitor={() => setShowMonitorEditor(true)}
                  inWatchlist={inWatchlist}
                  onToggleWatchlist={() => toggleWatchlist.mutate()}
                />
              )}
            </div>

            {/* 加监控编辑器弹层 */}
            <AnimatePresence>
              {showMonitorEditor && symbol && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="absolute inset-0 z-20 flex items-start justify-center overflow-auto bg-black/40 p-4"
                  onClick={() => setShowMonitorEditor(false)}
                >
                  <div className="mt-8 w-full max-w-2xl" onClick={e => e.stopPropagation()}>
                    <RuleEditor
                      rule={null}
                      simple
                      preset={{
                        scope: 'symbols',
                        symbols: [symbol],
                        type: 'signal',
                        logic: 'or',
                      }}
                      onClose={() => setShowMonitorEditor(false)}
                      onSaved={() => setShowMonitorEditor(false)}
                    />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        </div>
      )}
      {symbol && priceAlertDraft && (
        <PriceAlertDialog
          key={`${symbol}-${priceAlertDraft.id}`}
          symbol={symbol}
          name={name ?? ''}
          initialTarget={priceAlertDraft.targetPrice}
          initialCurrentPrice={priceAlertDraft.currentPrice}
          onClose={() => setPriceAlertDraft(null)}
        />
      )}
    </AnimatePresence>
  )
}
