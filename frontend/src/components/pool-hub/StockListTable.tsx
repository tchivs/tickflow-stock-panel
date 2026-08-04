import { useState } from 'react'
import { Loader2, RotateCcw } from 'lucide-react'
import { cn } from '@/lib/cn'
import type { PoolHubRow, PoolHubStrategy } from '@/lib/api'
import { boardTag } from '@/components/stock-table/primitives'
import { fmtPct, priceColorClass } from '@/lib/format'

// 复用既有标签处理: 关联因子 = 策略名 amber 标签; 概念板块 = 概念 chips
const STRATEGY_TAG_CLS = 'inline-block px-1.5 py-px rounded text-[10px] font-medium leading-tight bg-amber-500/10 text-amber-600 border border-amber-500/20'
const CONCEPT_CHIP_CLS = 'inline-block max-w-40 truncate px-1.5 py-px rounded text-[10px] font-medium leading-tight bg-elevated text-secondary border border-border'
const RESONANCE_BADGE_CLS = 'inline-block px-1.5 py-px rounded text-[10px] font-semibold leading-tight bg-accent/10 text-accent border border-accent/30'

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
}: StockListTableProps) {
  if (!strategy) return null
  const filterActive = filterText.trim().length > 0
  const columns = mode === 'guest' ? GUEST_COLUMNS : VIP_COLUMNS

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

      {/* 空态: 概念筛选无匹配 */}
      {!loading && !error && filterActive && rows.length === 0 && (
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
      {!loading && !error && !filterActive && rows.length === 0 && (
        <div className="flex flex-col items-center gap-1 py-10 text-center">
          <p className="text-xs text-secondary">该策略当日无命中个股。</p>
        </div>
      )}

      {/* 表 */}
      {!loading && !error && rows.length > 0 && (
        <div className="rounded-card border border-border overflow-x-auto">
          <table className="w-full text-sm" style={{ minWidth: 720 }}>
            <thead className="bg-elevated">
              <tr className="text-left text-secondary">
                {columns.map(c => (
                  <th key={c} scope="col" className="px-3 py-2.5 font-medium whitespace-nowrap">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => {
                const board = boardTag(row.symbol)
                const cross = row.cross_resonance
                const isGuest = mode === 'guest'
                // 游客行 key = 策略作用域序号 — 绝不用脱敏 symbol (T-19-10 duplicate-key 防御)
                const rowKey = isGuest ? `${strategy.id}-${index}` : row.symbol
                return (
                  <tr
                    key={rowKey}
                    className={cn(
                      'border-t border-border hover:bg-elevated/50 transition-colors duration-150 ease-smooth',
                      cross && 'bg-accent/[0.06]',
                    )}
                  >
                    <td className={cn('px-4 py-2 whitespace-nowrap', cross && 'border-l-2 border-accent/60')}>
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
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      {isGuest ? (
                        /* 游客 名称: 服务端脱敏值原样渲染 (mono muted), 永不空/— */
                        <span className="num tabular-nums text-muted">{row.name}</span>
                      ) : row.name ? (
                        <span className="block max-w-40 truncate text-foreground">{row.name}</span>
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
