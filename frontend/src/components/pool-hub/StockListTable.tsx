import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, CheckCircle2, Loader2, RotateCcw, Star } from 'lucide-react'
import { cn } from '@/lib/cn'
import type { AuctionColumnsDecl, PoolHubRow, PoolHubStrategy } from '@/lib/api'
import { boardTag } from '@/components/stock-table/primitives'
import { fmtBigNum, fmtPct, isToday, priceColorClass } from '@/lib/format'
import { useAuctionProbe, useQuoteStatus } from '@/lib/useSharedQueries'
import { TABLE_ROW_NAV_KEYS, useTableRowNav } from '@/lib/useTableRowNav'

// 复用既有标签处理: 关联因子 = 策略名 amber 标签; 概念板块 = 概念 chips
const STRATEGY_TAG_CLS = 'inline-block px-1.5 py-px rounded text-[10px] font-medium leading-tight bg-amber-500/10 text-amber-600 border border-amber-500/20'
const CONCEPT_CHIP_CLS = 'inline-block max-w-40 truncate px-1.5 py-px rounded text-[10px] font-medium leading-tight bg-elevated text-secondary border border-border'
const RESONANCE_BADGE_CLS = 'inline-block px-1.5 py-px rounded text-[10px] font-semibold leading-tight bg-accent/10 text-accent border border-accent/30'

// 概念归属徽标文案 (CONCEPT-04) — e2e 断言共享同一字面量 (独立 spec 复制, 不 import 跨文件耦合)
const CONCEPT_ATTRIBUTION_WARNING_TEXT = '概念归属为当前快照，非该日数据'
const CONCEPT_ATTRIBUTION_AS_OF_TEXT = '概念按当日快照'
const CONCEPT_EFFECTIVE_DATE_LABEL = '概念数据生效日期'

const GUEST_COLUMNS = ['代码', '名称', '涨跌幅', '概念板块', '关联因子'] as const
const VIP_COLUMNS = ['代码', '名称', '开盘涨幅', '涨跌幅', '概念板块', '关联因子'] as const

interface StockListTableProps {
  /** 当前选中的策略 (计数与行同源) */
  strategy: PoolHubStrategy | null
  /** 服务端声明的展示模式 (GUEST-01): guest 隐藏 开盘涨幅, 代码/名称 渲染脱敏值原样 */
  mode: 'guest' | 'vip'
  /** 客户端概念投影后的行 */
  rows: PoolHubRow[]
  /** 筛选词 (非空 = 筛选激活) */
  filterText: string
  /** 权威总数 M (策略 total) — 筛选不改变它, 卡片与明细永不漂移 */
  total: number
  /** 明细区加载中 (hub 重取) */
  loading: boolean
  /** 明细区错误 (后台刷新失败但已有载荷) */
  error: string | null
  onRetry: () => void
  onClearFilter: () => void
  /** 全池交叉共振股数 (服务端派生) */
  resonanceCount: number
  /** 服务端冻结的竞价列存在性声明 (OQ-2/H1); null/guest → 不渲染竞价列, 表结构既有不变 */
  auctionColumns?: AuctionColumnsDecl | null
  /** 自选集合 (服务端 watchlist 投影, join 键 = row.symbol 全等, WATCH-03/H6) */
  watchlistSet: Set<string>
  /** 单行星标切换回调 (symbol, inList) → 上层 mutation */
  onToggleWatchlist: (symbol: string, inList: boolean) => void
  /** 自选加载/切换 pending 或 error — 星标与开关禁用 (H9 fail-closed) */
  watchlistPending: boolean
  /** 「只看自选」过滤激活 (WATCH-02) */
  watchlistOnly: boolean
  // ===== WATCH-04 批量选择 (LG-04) — 复选框列 VIP-only, join 键 = 全后缀 symbol (与星标同键) =====
  /** 选中 symbol 集合 (行 checkbox 态; 表头全选态由本组件从 rows ∩ selection 派生) */
  selection: Set<string>
  /** 单行勾选切换 (symbol) */
  onToggleSelection: (symbol: string) => void
  /** 表头 全选/全不选 可见行 */
  onToggleSelectAll: () => void
  /** 点击股票名称 → 打开个股详情弹窗 (Watchlist 同款交互; guest 脱敏名不触发) */
  onPreview: (symbol: string, name: string) => void
}

/** 概念板块 chips — 首 3 个 + `+{N}` 展开/收起, 绝不截断标签中间 */
function ConceptChips({ concepts }: { concepts: string[] }) {
  const [expanded, setExpanded] = useState(false)
  if (concepts.length === 0) return <span className="text-muted">—</span>
  const visible = expanded ? concepts : concepts.slice(0, 3)
  const hidden = concepts.length - visible.length
  return (
    <div className="flex flex-wrap gap-0.5">
      {visible.map(c => (
        <span key={c} className={CONCEPT_CHIP_CLS}>{c}</span>
      ))}
      {hidden > 0 && !expanded && (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="inline-block px-1.5 py-px rounded text-[10px] font-medium leading-tight text-accent bg-accent/10 hover:bg-accent/20 transition-colors cursor-pointer"
        >
          +{hidden}
        </button>
      )}
      {expanded && concepts.length > 3 && (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="inline-block px-1.5 py-px rounded text-[10px] font-medium leading-tight text-muted hover:text-foreground transition-colors cursor-pointer"
        >
          收起
        </button>
      )}
    </div>
  )
}

function PctCell({ value }: { value: number | null }) {
  if (value == null || Number.isNaN(value)) return <span className="text-muted">—</span>
  return (
    <span className={cn('num tabular-nums', priceColorClass(value))}>
      {fmtPct(value)}
    </span>
  )
}

/** 大数单元格 (竞价量/金额/未匹配金额): fmtBigNum 万/亿, 右对齐, 不套涨跌色 (H2/PIT-4) */
function BigNumCell({ value }: { value: number | null | undefined }) {
  if (value == null || Number.isNaN(value)) return <span className="text-muted">—</span>
  return <span className="num tabular-nums">{fmtBigNum(value)}</span>
}

/** 竞价量比单元格: 倍数 (×) 非百分比 — toFixed(2)+'×', 不用 fmtPct (OQ-7) */
function RatioCell({ value }: { value: number | null | undefined }) {
  if (value == null || Number.isNaN(value)) return <span className="text-muted">—</span>
  return <span className="num tabular-nums">{value.toFixed(2)}×</span>
}

/**
 * AuctionColumnStatusBadge — 竞价列诚实状态徽标 (UI-SPEC §3.3/§4.3, H3 双轨)。
 * 冻结列存在性 (auction_columns.real) 驱动主徽标; 实时 probe/时段只驱动
 * warning 分支与盘前 secondary 行 — 历史快照不因今日 probe 状态被重写。
 */
export function AuctionColumnStatusBadge({
  auctionColumns,
  asOf,
  degraded,
}: {
  /** 服务端冻结的竞价列存在性声明; null = 无竞价列契约 (guest/后端未透传) → 不渲染 */
  auctionColumns: AuctionColumnsDecl | null
  /** 当前载荷 as_of (用于「盘前」判定: 查看日 == 今日) */
  asOf: string | null
  /** PM-04 盘前预览降级标志 — 服务端冻结 probe 非 available 时由页面透传, 强制诚实警告分支,
   *  不依赖 live probe (预览 payload 的冻结判定驱动); 历史/收盘视图不传 → 行为不变 */
  degraded?: boolean
}) {
  const probe = useAuctionProbe()
  const quoteStatus = useQuoteStatus()

  if (!auctionColumns) return null

  const realCols = auctionColumns.real ?? []
  const hasReal = realCols.some(c => c === 'auction_volume' || c === 'auction_amount')
  const probeAvailable = probe.data?.status === 'available'
  const viewingToday = asOf != null && isToday(asOf)
  const tradingHours = quoteStatus.data?.is_trading_hours ?? false

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      {degraded ? (
        <span className="inline-flex items-center gap-1.5 font-medium text-warning">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden />
          仅展示派生列 · 竞价数据源未配置
        </span>
      ) : hasReal ? (
        <span className="inline-flex items-center gap-1.5 font-medium text-accent">
          <CheckCircle2 className="h-3.5 w-3.5 shrink-0" aria-hidden />
          竞价数据可用 · 窗口 09:15-09:25
        </span>
      ) : probeAvailable ? (
        <span className="inline-flex items-center gap-1.5 font-medium text-warning">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden />
          该快照计算时无真实竞价数据，仅展示派生列
        </span>
      ) : (
        <span className="inline-flex items-center gap-1.5 font-medium text-warning">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden />
          竞价数据未接入，仅展示派生列
        </span>
      )}
      {viewingToday && !tradingHours && (
        <span className="inline-flex items-center gap-1.5 text-secondary">
          <span className="h-1.5 w-1.5 rounded-full bg-muted" aria-hidden />
          盘前/休市 · 竞价窗口 09:15-09:25 未开始
        </span>
      )}
    </div>
  )
}

/**
 * ConceptAttributionBadge — 概念归属诚实徽标 (CONCEPT-04/07)。
 * 服务端冻结的 concept_attribution 驱动 (28-01 `_project_hub`), 前端零推断 (PIT-3 纪律):
 * as_of_snapshot → 「概念按当日快照」+ 概念数据生效日期 (分区日);
 * 其余 (current_snapshot / unavailable / 未知) → 诚实警告「概念归属为当前快照，非该日数据」。
 * 顶层元素 (detail header), 绝不按行标注; 载荷缺 attribution (guest 掩码/旧后端) → 零渲染, 向后兼容。
 */
export function ConceptAttributionBadge({
  attribution,
  effectiveDate,
}: {
  attribution?: string | null
  effectiveDate?: string | null
}) {
  if (!attribution) return null
  if (attribution === 'as_of_snapshot') {
    return (
      <span className="inline-flex items-center gap-1.5 font-medium text-accent" role="note">
        <CheckCircle2 className="h-3.5 w-3.5 shrink-0" aria-hidden />
        {CONCEPT_ATTRIBUTION_AS_OF_TEXT}
        {effectiveDate ? ` · ${CONCEPT_EFFECTIVE_DATE_LABEL} ${effectiveDate}` : ''}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 font-medium text-warning" role="note">
      <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden />
      {CONCEPT_ATTRIBUTION_WARNING_TEXT}
    </span>
  )
}

/**
 * 股池钻取明细表 — 研究只读面 (POOL-03): 无任何行内编辑/交易操作。
 * 表头精确 代码 | 开盘涨幅 | 涨跌幅 | 概念板块 | 关联因子;
 * 交叉共振行 = 服务端 cross_resonance → accent 底色 + 左边框 + `交叉共振 · {N} 策略` 徽标。
 */
export function StockListTable({
  strategy,
  mode,
  rows,
  filterText,
  total,
  loading,
  error,
  onRetry,
  onClearFilter,
  resonanceCount,
  auctionColumns = null,
  watchlistSet,
  onToggleWatchlist,
  watchlistPending,
  watchlistOnly,
  selection,
  onToggleSelection,
  onToggleSelectAll,
  onPreview,
}: StockListTableProps) {
  const conceptActive = filterText.trim().length > 0
  const filterActive = conceptActive || watchlistOnly
  const columns = mode === 'guest' ? GUEST_COLUMNS : VIP_COLUMNS

  // 数据网格方向键行导航 (APG roving-tabindex) — ↑/↓/Home/End/PageUp/PageDown 行间移动。
  // 必须在任何条件 return 之前调用 (rules of hooks)。
  const { tbodyRef, onRowFocus, onRowKeyDown } = useTableRowNav<HTMLTableSectionElement>(rows)

  // WATCH-04 表头全选三态 (LG-04): 以「可见行」(rows prop = 页面 filteredRows) 为界 —
  // 勾选行已不在可见集不计入, 与 handleBatchAdd 防御性 intersect 同语义。
  const visibleSymbols = rows.map(r => r.symbol)
  const selectedVisibleCount = visibleSymbols.filter(s => selection.has(s)).length
  const allSelected = rows.length > 0 && selectedVisibleCount === rows.length
  const someSelected = selectedVisibleCount > 0 && !allSelected
  // indeterminate 视觉经 DOM 属性 (React 无 indeterminate prop); aria-checked="mixed" 显式同步 (P1 可访问名)
  const selectAllRef = useRef<HTMLInputElement>(null)
  useEffect(() => {
    if (selectAllRef.current) selectAllRef.current.indeterminate = someSelected && !allSelected
  }, [someSelected, allSelected])
  // WATCH-04 表头全选 checkbox (VIP-only 列): aria-checked 三态; 仅一个分支渲染 (grouped/单行 二选一)
  const selectAllControl = (
    <input
      type="checkbox"
      ref={selectAllRef}
      aria-label="全选"
      aria-checked={allSelected ? 'true' : someSelected ? 'mixed' : 'false'}
      checked={allSelected}
      onChange={onToggleSelectAll}
      title="全选"
      className="h-4 w-4 cursor-pointer"
    />
  )

  if (!strategy) return null

  // 竞价列分组 (OQ-2/H1): 列存在性完全由服务端 auction_columns 声明驱动, 绝不从行值推导 (PIT-3)。
  // real 组整组同存同隐; open_gap 已留基础列「开盘涨幅」渲染, 不搬入派生组不重复渲染 (OQ-5)。
  const realCols = auctionColumns?.real ?? []
  const derivedCols = auctionColumns?.derived ?? []
  const hasReal = realCols.some(c => c === 'auction_volume' || c === 'auction_amount')
  const hasDerived = derivedCols.some(c => c === 'auction_volume_ratio' || c === 'auction_unmatched_amount')
  const hasAuctionCols = hasReal || hasDerived
  // guest/无声明 → 既有单行表头, 无竞价列无分组无徽标 (H7); 两者皆无可渲染列 → 等同无竞价列
  const grouped = mode === 'vip' && hasAuctionCols

  return (
    <div className="space-y-2">
      {/* 明细加载中 — 保留表头高度, 避免跳版 */}
      {loading && (
        <div
          role="status"
          aria-live="polite"
          className="flex min-h-16 items-center gap-2 text-sm text-muted"
        >
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          股池明细加载中…
        </div>
      )}

      {/* 明细加载失败 — 行内 alert + 重试 */}
      {!loading && error && (
        <div role="alert" className="flex items-center gap-2 text-sm text-danger bg-danger/10 border border-danger/30 rounded-btn px-3 py-2">
          <span className="mr-1">股池明细加载失败：{error}。请重试。</span>
          <button
            onClick={onRetry}
            className="inline-flex items-center h-6 px-2 rounded text-xs font-medium
              bg-surface border border-border text-secondary hover:text-accent hover:border-accent/50 transition-colors cursor-pointer"
          >
            重试
          </button>
        </div>
      )}

      {/* 空态: 只看自选无匹配 (WATCH-02, UI-SPEC §3.3 顺序 1 — 优先于概念空态, P4 防线: 不插值 filterText) */}
      {!loading && !error && watchlistOnly && rows.length === 0 && (
        <div className="flex flex-col items-center gap-1 py-10 text-center">
          <p className="text-sm font-medium text-foreground">自选清单中无该策略个股</p>
          <p className="text-xs text-secondary">试试关闭「只看自选」或切换策略。</p>
        </div>
      )}

      {/* 空态: 概念筛选无匹配 */}
      {!loading && !error && conceptActive && rows.length === 0 && (
        <div className="flex flex-col items-center gap-1 py-10 text-center">
          <p className="text-sm font-medium text-foreground">无符合「{filterText.trim()}」的个股</p>
          <p className="text-xs text-secondary">试试切换其他概念或清除筛选。</p>
          <button
            type="button"
            onClick={onClearFilter}
            className="mt-2 inline-flex items-center gap-1 h-9 px-3 rounded-btn text-xs font-medium
              border border-border bg-surface text-secondary hover:bg-danger/10 hover:text-danger transition-colors cursor-pointer"
          >
            <RotateCcw className="h-3 w-3" aria-hidden />
            清除筛选
          </button>
        </div>
      )}

      {/* 空态: 策略当日无命中 */}
      {!loading && !error && !conceptActive && !watchlistOnly && rows.length === 0 && (
        <div className="flex flex-col items-center gap-1 py-10 text-center">
          <p className="text-xs text-secondary">该策略当日无命中个股。</p>
        </div>
      )}

      {/* 表 */}
      {!loading && !error && rows.length > 0 && (
        <div className="rounded-card border border-border overflow-x-auto">
          <table className="w-full text-sm" style={{ minWidth: grouped ? 940 : 720 }} aria-keyshortcuts={TABLE_ROW_NAV_KEYS}>
            <thead className="bg-elevated">
              {grouped ? (
                /* 两行分组表头 (UI-SPEC §3.2): 基础列 rowSpan=2 + 真实集合竞价/派生·虚拟成交 colSpan=2 组带 */
                <>
                  <tr className="text-left text-secondary">
                    {mode === 'vip' && (
                      <th key="__select_all__" rowSpan={2} scope="col" className="w-10 px-2 py-2.5 text-center">
                        {selectAllControl}
                      </th>
                    )}
                    {columns.map(c => (
                      <th key={c} rowSpan={2} scope="col" className="px-3 py-2.5 font-medium whitespace-nowrap">{c}</th>
                    ))}
                    {hasReal && (
                      <th colSpan={2} scope="colgroup"
                        title="集合竞价撮合成交（09:15-09:25），仅在快照计算时竞价数据可用且分区有行时存在。"
                        className="px-3 py-2 font-semibold text-accent bg-accent/[0.06] border-t border-accent/30 text-center text-xs whitespace-nowrap">
                        真实集合竞价
                      </th>
                    )}
                    {hasDerived && (
                      <th colSpan={2} scope="colgroup"
                        title="由竞价量与历史均量、委托量输入派生的估算值，非真实成交。"
                        className="px-3 py-2 font-medium text-secondary bg-elevated text-center text-xs whitespace-nowrap">
                        派生 · 虚拟成交
                      </th>
                    )}
                  </tr>
                  <tr className="text-left text-secondary">
                    {hasReal && (
                      <>
                        <th scope="col" title="竞价量 = 集合竞价撮合成交量（单位：股）。" className="px-3 py-2 font-medium whitespace-nowrap text-xs">竞价量（股）</th>
                        <th scope="col" title="竞价金额 = 集合竞价撮合成交额（单位：元）。" className="px-3 py-2 font-medium whitespace-nowrap text-xs">竞价金额（元）</th>
                      </>
                    )}
                    {hasDerived && (
                      <>
                        <th scope="col" title="竞价量 ÷ 前 5 日均量（不含当日）。" className="px-3 py-2 font-medium whitespace-nowrap text-xs">竞价量比（×）</th>
                        <th scope="col" title="虚拟未匹配量 × 虚拟参考价的估算值，非真实成交金额。" className="px-3 py-2 font-medium whitespace-nowrap text-xs">虚拟未匹配金额（元·估算）</th>
                      </>
                    )}
                  </tr>
                </>
              ) : (
                <tr className="text-left text-secondary">
                  {mode === 'vip' && (
                    <th key="__select_all__" scope="col" className="w-10 px-2 py-2.5 text-center">
                      {selectAllControl}
                    </th>
                  )}
                  {columns.map(c => (
                    <th key={c} scope="col" className="px-3 py-2.5 font-medium whitespace-nowrap">{c}</th>
                  ))}
                </tr>
              )}
            </thead>
            <tbody ref={tbodyRef}>
              {rows.map((row, index) => {
                const board = boardTag(row.symbol)
                const cross = row.cross_resonance
                const isGuest = mode === 'guest'
                // WATCH-01 星标成员资格: join 键 = 全后缀 symbol 精确全等 (WATCH-03/H6), 无归一化/无 code 匹配
                const inList = watchlistSet.has(row.symbol)
                // 游客行 key = 策略作用域序号 — 绝不用脱敏 symbol (T-19-10 duplicate-key 防御)
                const rowKey = isGuest ? `${strategy.id}-${index}` : row.symbol
                return (
                  <tr
                    key={rowKey}
                    onFocus={onRowFocus}
                    onKeyDown={onRowKeyDown}
                    className={cn(
                      'border-t border-border hover:bg-elevated/50 transition-colors duration-150 ease-smooth focus-visible:bg-elevated/60 focus-visible:[outline-offset:-2px]',
                      cross && 'bg-accent/[0.06]',
                    )}
                  >
                    {!isGuest && (
                      /* WATCH-04 行选择 checkbox (LG-04, VIP-only — 镜像星标 VIP-only 规则; guest 零控件) */
                      <td className={cn('px-2 py-2 text-center', cross && 'border-l-2 border-accent/60')}>
                        <input
                          type="checkbox"
                          aria-label={`选择${row.code}`}
                          checked={selection.has(row.symbol)}
                          onChange={() => onToggleSelection(row.symbol)}
                          title={`选择${row.code}`}
                          className="h-4 w-4 cursor-pointer"
                        />
                      </td>
                    )}
                    {/* 交叉共振左边框标记挂在行首 td (VIP = 复选框格, guest = 代码格) — 行左缘视觉位置稳定 */}
                    <td className={cn('px-4 py-2 whitespace-nowrap', isGuest && cross && 'border-l-2 border-accent/60')}>
                      {isGuest ? (
                        /* 游客 代码: 服务端脱敏值原样渲染 (mono muted), 无板块标识 */
                        <span className="num tabular-nums text-muted">{row.code}</span>
                      ) : (
                        <div className="flex items-center gap-2">
                          {board ? (
                            <span className={`shrink-0 inline-flex items-center justify-center w-[18px] h-[18px] rounded text-[9px] font-bold leading-none border ${board.color}`}>
                              {board.label}
                            </span>
                          ) : (
                            <span className="shrink-0 w-[18px]" />
                          )}
                          <span className="num tabular-nums text-secondary">{row.code}</span>
                          {/* WATCH-01 VIP 星标: 在自选实心 amber / 不在空心 muted; icon-only 必须可访问名 (P1) */}
                          <button
                            type="button"
                            onClick={() => onToggleWatchlist(row.symbol, inList)}
                            disabled={watchlistPending}
                            aria-label={inList ? '移出自选' : '加入自选'}
                            title={inList ? '移出自选' : '加入自选'}
                            className="p-1 max-md:h-11 max-md:w-11 rounded-btn transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            <Star
                              className={'h-3.5 w-3.5 ' + (inList ? 'text-[#FACC15]' : 'text-muted hover:text-foreground hover:bg-elevated')}
                              fill={inList ? 'currentColor' : 'none'}
                              aria-hidden
                            />
                          </button>
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {isGuest ? (
                        /* 游客 名称: 服务端脱敏值原样渲染 (mono muted), 永不空/—, 无预览 affordance */
                        <span className="num tabular-nums text-muted">{row.name}</span>
                      ) : row.name ? (
                        /* VIP 名称: 可点击按钮 → onPreview 打开个股详情 (Watchlist 同款 hover 变色) */
                        <button
                          type="button"
                          onClick={() => onPreview(row.symbol, row.name)}
                          aria-label={`查看 ${row.name} 详情`}
                          title={`查看 ${row.name} 详情`}
                          className="flex items-center text-left min-w-0 max-w-40 group"
                        >
                          <span className="block max-w-40 truncate text-foreground group-hover:text-accent transition-colors duration-150">
                            {row.name}
                          </span>
                        </button>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                    {/* 开盘涨幅 — 仅 VIP: 游客整列不渲染 (UI-SPEC guest contract) */}
                    {!isGuest && <td className="px-3 py-2"><PctCell value={row.open_gap} /></td>}
                    <td className="px-3 py-2"><PctCell value={row.change_pct} /></td>
                    <td className="px-3 py-2"><ConceptChips concepts={row.concept_board} /></td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-0.5 items-center">
                        {row.hit_factors.length > 0
                          ? row.hit_factors.map(f => (
                              <span key={f} className={STRATEGY_TAG_CLS}>{f}</span>
                            ))
                          : <span className="text-muted">—</span>}
                        {cross && (
                          <span className={RESONANCE_BADGE_CLS}>
                            交叉共振 · <span className="num tabular-nums">{row.hit_factors.length}</span> 策略
                          </span>
                        )}
                      </div>
                    </td>
                    {/* 竞价列 (VIP + 服务端声明): 真实组 (股/元) + 派生组 (×/估算), 紧跟基础列末尾, 无涨跌色 (H2) */}
                    {!isGuest && hasReal && (
                      <>
                        <td className="px-3 py-2 text-right"><BigNumCell value={row.auction_volume} /></td>
                        <td className="px-3 py-2 text-right"><BigNumCell value={row.auction_amount} /></td>
                      </>
                    )}
                    {!isGuest && hasDerived && (
                      <>
                        <td className="px-3 py-2 text-right"><RatioCell value={row.auction_volume_ratio} /></td>
                        <td className="px-3 py-2 text-right"><BigNumCell value={row.auction_unmatched_amount} /></td>
                      </>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* footer meta: 计数 + 交叉共振 legend (研究只读) */}
      {!loading && !error && (
        <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-xs text-muted">
          <span>
            {filterActive ? (
              <>筛选后 <span className="num tabular-nums">{rows.length}</span> 只 / 共 <span className="num tabular-nums">{total}</span> 只</>
            ) : (
              <>共 <span className="num tabular-nums">{total}</span> 只</>
            )}
          </span>
          <span className="text-right">
            {resonanceCount > 0 ? (
              '交叉共振：被 ≥2 个竞价策略同时命中的个股'
            ) : (
              <>今日无交叉共振 · 暂无个股被 ≥2 个竞价策略同时命中。</>
            )}
          </span>
        </div>
      )}
    </div>
  )
}
