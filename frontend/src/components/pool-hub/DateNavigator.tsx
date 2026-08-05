import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react'

export interface DateNavigatorProps {
  /** 有快照的交易日全集 (ISO desc) — GET /api/pool/dates 白名单, 非交易日不在其中 */
  dates: string[]
  /** 服务端声明的最近快照日 (dates[0]); null = 无任何快照 */
  latest: string | null
  /** 当前选中日期; null = 最新 (回 /api/pool/hub) */
  selectedDate: string | null
  /** datesQuery 加载中 → 「加载日期中…」 + 禁用步进 */
  loading?: boolean
  /** datesQuery 失败 → 行内 role="alert" + 重试 */
  error?: string | null
  onRetry: () => void
  /** 步进/下拉/「最新」唯一出口: null = 回最新 */
  onChange: (date: string | null) => void
}

/**
 * DateNavigator — 按交易日浏览股池快照 (FRONT-01/OQ-1/OQ-4)。
 * 受控只读组件, 无内部数据获取: 白名单 `dates` 下标步进, 非交易日物理不可达 (PIT-5);
 * ‹ › 严格在数组下标内移动, `idx === -1` (当前 as_of 不在列表) 双禁用不猜测。
 */
export function DateNavigator({
  dates,
  latest,
  selectedDate,
  loading = false,
  error = null,
  onRetry,
  onChange,
}: DateNavigatorProps) {
  const currentAsOf = selectedDate ?? latest ?? null
  const idx = currentAsOf ? dates.indexOf(currentAsOf) : -1

  // dates 为降序 (最新在前): ‹ 更早一日 = idx+1; › 更近一日 = idx-1。
  // 边界 (最旧/最新) 与 idx === -1 (当前 as_of 不在列表) 一律禁用, 绝不静默跳日。
  const prevDisabled = loading || dates.length === 0 || idx === dates.length - 1 || idx === -1
  const nextDisabled = loading || dates.length === 0 || idx === 0 || idx === -1

  const stepButtonCls =
    'inline-flex items-center justify-center h-9 w-9 rounded-btn border border-border bg-surface ' +
    'text-secondary hover:text-accent hover:border-accent/50 transition-colors cursor-pointer ' +
    'disabled:opacity-50 disabled:cursor-not-allowed max-md:min-h-11 max-md:min-w-11'

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => {
          if (!prevDisabled) onChange(dates[idx + 1])
        }}
        disabled={prevDisabled}
        aria-label="上一个交易日"
        aria-disabled={prevDisabled}
        className={stepButtonCls}
      >
        <ChevronLeft className="h-4 w-4" aria-hidden />
      </button>

      <select
        aria-label="选择日期"
        value={currentAsOf ?? ''}
        onChange={e => onChange(e.target.value || null)}
        disabled={loading || dates.length === 0}
        className="h-9 rounded-input border border-border bg-surface px-3 text-xs text-foreground num
          disabled:opacity-50 disabled:cursor-not-allowed max-md:min-h-11"
      >
        {dates.length === 0 ? (
          <option value="">暂无历史日期</option>
        ) : (
          dates.map(d => (
            <option key={d} value={d}>{d}</option>
          ))
        )}
      </select>

      <button
        type="button"
        onClick={() => {
          if (!nextDisabled) onChange(dates[idx - 1])
        }}
        disabled={nextDisabled}
        aria-label="下一个交易日"
        aria-disabled={nextDisabled}
        className={stepButtonCls}
      >
        <ChevronRight className="h-4 w-4" aria-hidden />
      </button>

      {selectedDate !== null && (
        <button
          type="button"
          onClick={() => onChange(null)}
          title="返回最新股池"
          className="inline-flex items-center h-9 px-3 rounded-btn border border-border bg-surface
            text-xs font-medium text-accent hover:border-accent/50 transition-colors cursor-pointer
            max-md:min-h-11 max-md:min-w-11"
        >
          最新
        </button>
      )}

      {loading && (
        <span role="status" aria-live="polite" className="inline-flex items-center gap-1.5 text-xs text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
          加载日期中…
        </span>
      )}

      {error && !loading && (
        <div role="alert" className="inline-flex items-center gap-2 text-xs text-danger bg-danger/10 border border-danger/30 rounded-btn px-2 py-1">
          <span>日期列表加载失败：{error}</span>
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex items-center h-6 px-2 rounded text-xs font-medium
              bg-surface border border-border text-secondary hover:text-accent hover:border-accent/50 transition-colors cursor-pointer"
          >
            重试
          </button>
        </div>
      )}
    </div>
  )
}
