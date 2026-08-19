import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sparkles, LineChart, History as HistoryIcon, Loader2, ExternalLink, Bell, AlertTriangle } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { Modal } from '@/components/Modal'
import { EmptyState } from '@/components/EmptyState'
import { StockFinancialSearch } from '@/components/financials/StockFinancialSearch'
import { StockPreviewDialog } from '@/components/StockPreviewDialog'
import { LastStockChip } from '@/components/LastStockChip'
import { AnalysisKChart, type PriceLevel, type LevelType } from '@/components/stock-analysis/AnalysisKChart'
import { PriceAlertDialog } from '@/components/stock-analysis/PriceAlertDialog'
import { api } from '@/lib/api'
import { useLastStock } from '@/lib/useLastStock'
import { QK } from '@/lib/queryKeys'
import { toast } from '@/components/Toast'
import { AnalysisWorkspace } from '@/components/analysis/AnalysisWorkspace'
import {
  startAnalysis, findTodayReport, useHistoryReports,
  deleteReport, openHistoryReport, loadHistory,
} from '@/lib/stockAnalysisStore'

/**
 * 个股分析页 —— 日 K + 关键价位(压力/支撑/密集区/枢轴/前高前低)+ AI 四维分析。
 *
 * 与财务分析页的区别:
 *  - 以【行情 + 关键价位】为视觉主体(专用日 K 图表,不复用个股对话框图表)
 *  - AI 分析输出客观技术状态与风险提示(非买卖建议、非财务质量评级)
 *  - 报告胶囊用蓝色系,与财务分析(紫色)并存
 */
export function StockAnalysis() {
  const [symbol, setSymbol] = useState<string>('')
  const [name, setName] = useState<string>('')
  const [checking, setChecking] = useState(false)
  const [confirmReport, setConfirmReport] = useState<{ id: string; created_at: string; focus: string } | null>(null)
  const [previewSymbol, setPreviewSymbol] = useState<string | null>(null)
  const analyzeButtonRef = useRef<HTMLButtonElement>(null)
  const [showPriceAlerts, setShowPriceAlerts] = useState(false)
  const { last: lastStock, remember: rememberStock } = useLastStock('stock-analysis')

  // 进入页面立即加载历史报告(供右侧常驻列表)。store 内部有 historyLoaded 去重, 重复调用安全。
  useEffect(() => { loadHistory() }, [])

  // 支持 ?symbol=&name= 直达 (StockPreviewDialog「个股分析」入口): 优先于 localStorage 恢复
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search)
    const s = sp.get('symbol')
    if (s) {
      setSymbol(s)
      setName(sp.get('name') ?? '')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 自动恢复上次选中的股票(切走再回来不丢)。useLastStock 的 last 来自 localStorage, 同步可用。
  useEffect(() => {
    if (!symbol && lastStock) {
      setSymbol(lastStock.symbol)
      setName(lastStock.name)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const onSelect = (sym: string, nm: string) => {
    setSymbol(sym)
    setName(nm)
    setConfirmReport(null)
    setShowPriceAlerts(false)
    rememberStock(sym, nm)
  }

  const closeConfirm = () => {
    setConfirmReport(null)
    requestAnimationFrame(() => analyzeButtonRef.current?.focus())
  }

  const handleAnalyze = async () => {
    if (!symbol || checking) return
    setChecking(true)
    try {
      // 当日已分析过 → 二次确认(查看今日报告 / 重新分析)
      const today = await findTodayReport(symbol)
      if (today) {
        setConfirmReport({ id: today.id, created_at: today.created_at, focus: today.focus })
      } else {
        await doAnalysis()
      }
    } catch {
      await doAnalysis()
    } finally {
      setChecking(false)
    }
  }

  const doAnalysis = async () => {
    const r = await startAnalysis(symbol, name)
    if (r.error) toast(r.error, 'error')
  }

  return (
    <>
      <PageHeader
        title="个股分析"
        subtitle="日 K · 关键价位 · AI 四维分析(技术 / 基本面 / 财务 / 消息面)"
        right={
          <div className="flex items-center gap-2">
            <LastStockChip stock={lastStock} onSelect={onSelect} />
          </div>
        }
      />

      <div className="w-full space-y-6 px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
        {/* 搜索栏 */}
        <div className="flex min-w-0 flex-wrap items-center gap-3">
          <div className="min-w-0 basis-full sm:basis-72 sm:flex-1 sm:max-w-xl">
            <StockFinancialSearch onSelect={onSelect} assetTypes="stock,index" />
          </div>
          {symbol && (
            <>
              <button
                type="button"
                onClick={() => setPreviewSymbol(symbol)}
                title="查看个股日 K 详情"
                className="group flex min-h-11 min-w-0 max-w-full items-center gap-2 rounded-btn px-2 text-sm transition-colors hover:bg-elevated focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base"
              >
                <span className="truncate font-medium text-foreground transition-colors group-hover:text-accent">{name || symbol}</span>
                <span className="shrink-0 font-mono text-[10px] text-muted">{symbol}</span>
                <ExternalLink className="h-3 w-3 shrink-0 text-muted opacity-60 transition-opacity group-hover:opacity-100" aria-hidden="true" />
              </button>
              <button
                type="button"
                ref={analyzeButtonRef}
                onClick={handleAnalyze}
                disabled={checking}
                className="inline-flex min-h-11 items-center gap-1.5 rounded-btn bg-accent-solid px-3 text-xs font-medium text-white transition-colors hover:bg-accent-solid/90 focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base disabled:cursor-not-allowed disabled:opacity-40"
              >
                {checking ? <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />}
                AI 个股分析
              </button>
              <button
                type="button"
                onClick={() => setShowPriceAlerts(true)}
                className="inline-flex min-h-11 items-center gap-1.5 rounded-btn border border-sky-400/25 bg-sky-400/[0.08] px-3 text-xs font-medium text-sky-300 transition-colors hover:border-sky-400/40 hover:bg-sky-400/[0.12] focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base"
                title="设置价格点位提醒"
              >
                <Bell className="h-3.5 w-3.5" aria-hidden="true" />
                点位提醒

              </button>
            </>
          )}
        </div>

        {/* 主体:左侧当前个股看板 + 右侧常驻历史报告 */}
        <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_288px]">
          <div className="min-w-0">
            {!symbol ? (
              <EmptyState
                icon={LineChart}
                title="选择一只股票开始分析"
                hint="搜索代码或名称,查看日 K 与关键价位,并可让 AI 进行技术面 / 基本面 / 财务面 / 消息面四维综合分析。"
              />
            ) : (
              <>
                <StockAnalysisBoard symbol={symbol} />
                <div className="mt-6">
                  <AnalysisWorkspace subject={{ kind: 'stock', key: symbol }} title={`${name || symbol}（${symbol}）`} />
                </div>
              </>
            )}
          </div>
          <HistorySidebar />
        </div>
      </div>

      {/* 二次确认:已有历史报告 */}
      {confirmReport && (
        <ConfirmModal
          report={confirmReport}
          onView={() => { openHistoryReport(confirmReport.id); closeConfirm() }}
          onRedo={async () => { closeConfirm(); await doAnalysis() }}
          onClose={closeConfirm}
        />
      )}

      {/* 个股日 K 详情对话框(点击名称/代码打开) */}
      <StockPreviewDialog
        symbol={previewSymbol}
        name={previewSymbol === symbol ? name : undefined}
        triggerInfo={null}
        onClose={() => setPreviewSymbol(null)}
      />

      {showPriceAlerts && symbol && (
        <PriceAlertDialog
          key={symbol}
          symbol={symbol}
          name={name}
          onClose={() => setShowPriceAlerts(false)}
        />
      )}
    </>
  )
}

// ===== 分析看板:日 K + 关键价位 =====
function StockAnalysisBoard({ symbol }: { symbol: string }) {
  const kline = useQuery({
    queryKey: ['kline', symbol, ''],
    queryFn: () => api.klineDaily(symbol, 250),
    enabled: !!symbol,
    staleTime: 60_000,
  })

  const levelsQ = useQuery({
    queryKey: QK.stockLevels(symbol),
    queryFn: () => api.stockAnalysisLevels(symbol, 250),
    enabled: !!symbol,
    staleTime: 60_000,
  })

  if (kline.isLoading) {
    return <div className="flex items-center justify-center py-20"><Loader2 className="h-5 w-5 animate-spin text-muted" /></div>
  }

  if (kline.isError) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="日 K 数据加载失败"
        hint="请检查网络或数据源配置后重试。"
      />
    )
  }

  const rows = kline.data?.rows ?? []
  if (rows.length === 0) {
    return <EmptyState icon={LineChart} title="暂无日 K 数据" hint="该标的尚未同步日 K,请先在数据页或自选页同步。" />
  }

  const levels = (levelsQ.data?.levels ?? {}) as Record<LevelType, PriceLevel[]>

  // 涨跌色:最后一根 K 线收 vs 前一根收(无前日则按开收判断)
  const last = rows[rows.length - 1]
  const prev = rows[rows.length - 2]
  const curClose = levelsQ.data?.close
  const isUp = prev ? (last.close >= prev.close) : (last.close >= last.open)

  return (
    <div className="rounded-card border border-border/60 bg-surface/40 overflow-hidden">
      <div className="px-4 py-3 border-b border-border/40">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <LineChart className="h-4 w-4 text-sky-400 shrink-0" />
            <span className="text-sm font-medium text-foreground">关键价位分析</span>
          </div>
          <div className="flex items-baseline gap-2 shrink-0">
            <span className="text-[10px] text-muted">{rows.length} 个交易日</span>
            <span className="text-[10px] text-muted/60">·</span>
            <span className="text-[10px] text-muted">当前价</span>
            <span className={`text-base font-mono font-bold ${isUp ? 'text-bull' : 'text-bear'}`}>
              {curClose?.toFixed(2) ?? '—'}
            </span>
          </div>
        </div>
      </div>
      <div className="p-3">
        <AnalysisKChart
          rows={rows}
          levels={levels}
          series={levelsQ.data?.series}
          seriesDates={levelsQ.data?.dates}
          defaultLevelTypes={['sr', 'pivot', 'keltner_s']}
          height={480}
        />
      </div>
    </div>
  )
}

// ===== 左侧常驻:历史报告侧栏(所有股票,按时间倒序平铺) =====
function HistorySidebar() {
  const { reports, loaded } = useHistoryReports()

  return (
    <aside className="self-start xl:sticky xl:top-0">
      <div className="rounded-card border border-border/60 bg-surface/40 overflow-hidden">
        <div className="px-3 py-2.5 border-b border-border/40 flex items-center gap-2">
          <HistoryIcon className="h-3.5 w-3.5 text-sky-400 shrink-0" />
          <span className="text-xs font-medium text-foreground">历史报告</span>
          {loaded && reports.length > 0 && (
            <span className="ml-auto text-[10px] text-muted">{reports.length}</span>
          )}
        </div>

        {!loaded ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-4 w-4 animate-spin text-muted" />
          </div>
        ) : reports.length === 0 ? (
          <div className="px-3 py-10 text-center">
            <p className="text-xs text-muted">还没有任何个股分析报告</p>
            <p className="text-[10px] text-muted/60 mt-1">选一只股票,点「AI 个股分析」生成</p>
          </div>
        ) : (
          <div className="max-h-[calc(100vh-220px)] overflow-y-auto p-2 space-y-1.5">
            {reports.map(r => (
              <div
                key={r.id}
                className="group rounded-lg border border-border/40 bg-elevated/20 p-2.5 hover:border-border hover:bg-elevated/40 transition-colors"
              >
                <div className="flex items-center justify-between gap-2">
                  <button
                    onClick={() => openHistoryReport(r.id)}
                    className="flex-1 text-left min-w-0"
                  >
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="text-xs font-medium text-foreground truncate">{r.name || r.symbol}</span>
                      <span className="text-[10px] font-mono text-muted shrink-0">{r.symbol}</span>
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-[10px] text-muted">
                      <span>{fmtRelative(r.created_at)}</span>
                      {r.close != null && <span className="font-mono">价 {r.close.toFixed(2)}</span>}
                      {r.focus && <span className="text-sky-300/70 truncate">关注: {r.focus}</span>}
                    </div>
                    {r.summary && (
                      <div className="mt-1 text-[11px] text-muted truncate">{r.summary}</div>
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => { deleteReport(r.id); toast('已删除', 'success') }}
                    className="inline-flex min-h-11 min-w-11 shrink-0 items-center justify-center rounded-btn px-2 text-[10px] text-muted transition-colors hover:text-danger focus:opacity-100 focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base sm:min-h-0 sm:min-w-0 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100"
                    title="删除"
                  >
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}

// ===== 二次确认弹窗 =====
function ConfirmModal({ report, onView, onRedo, onClose }: {
  report: { id: string; created_at: string; focus: string }
  onView: () => void
  onRedo: () => void
  onClose: () => void
}) {
  const viewRef = useRef<HTMLButtonElement>(null)
  return (
    <Modal
      onClose={onClose}
      labelledBy="stock-analysis-confirm-title"
      initialFocusRef={viewRef}
      panelClassName="w-[calc(100vw-2rem)] max-w-sm rounded-dialog border border-border bg-surface p-5 shadow-xl"
    >
      <div className="mb-2 flex items-center gap-2">
        <HistoryIcon className="h-4 w-4 text-accent" aria-hidden="true" />
        <h2 id="stock-analysis-confirm-title" className="text-sm font-medium text-foreground">该个股已有分析报告</h2>
      </div>
      <p className="mb-1 text-xs leading-relaxed text-secondary">
        最近一次报告生成于 <span className="text-foreground">{fmtRelative(report.created_at)}</span>。
      </p>
      {report.focus && <p className="mb-1 break-words text-xs text-muted">关注点: {report.focus}</p>}
      <p className="mb-4 text-xs text-secondary">可直接查看历史,或重新生成一份新报告。</p>
      <div className="flex flex-wrap gap-2">
        <button ref={viewRef} type="button" onClick={onView}
          className="inline-flex min-h-11 flex-1 items-center justify-center rounded-btn border border-border bg-elevated px-3 text-xs text-secondary transition-colors hover:text-foreground focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base">
          查看历史
        </button>
        <button type="button" onClick={onRedo}
          className="inline-flex min-h-11 flex-1 items-center justify-center rounded-btn bg-accent-solid px-3 text-xs font-medium text-white transition-colors hover:bg-accent-solid/90 focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base">
          重新分析
        </button>
      </div>
    </Modal>
  )
}

function fmtRelative(iso: string): string {
  try {
    const t = new Date(iso).getTime()
    const diff = Date.now() - t
    if (diff < 60_000) return '刚刚'
    if (diff < 3600_000) return `${Math.floor(diff / 60_000)} 分钟前`
    if (diff < 86400_000) return `${Math.floor(diff / 3600_000)} 小时前`
    if (diff < 7 * 86400_000) return `${Math.floor(diff / 86400_000)} 天前`
    return new Date(iso).toLocaleDateString('zh-CN')
  } catch { return iso }
}
