import { RotateCcw, X } from 'lucide-react'

interface ConceptFilterProps {
  value: string
  onChange: (v: string) => void
  onClear: () => void
}

const HELP_ID = 'pool-concept-filter-help'

/**
 * 概念筛选 — 纯客户端投影 (D-04): 只在已加载的单 as_of 载荷内筛选,
 * 输入绝不触发第二次 fetch。研究只读面, 无执行操作。
 */
export function ConceptFilter({ value, onChange, onClear }: ConceptFilterProps) {
  const active = value.trim().length > 0
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-2 min-w-0">
        <label
          htmlFor="pool-concept-filter"
          className="shrink-0 text-xs font-medium text-secondary whitespace-nowrap"
        >
          概念筛选
        </label>
        <div className="relative min-w-0">
          <input
            id="pool-concept-filter"
            type="text"
            value={value}
            onChange={e => onChange(e.target.value)}
            placeholder="输入概念名筛选…"
            aria-describedby={HELP_ID}
            spellCheck={false}
            className="h-9 w-48 rounded-input bg-base border border-border px-2 pr-8 text-sm text-foreground
              placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2
              focus:ring-offset-base max-md:h-11 max-md:w-44 transition-colors duration-150 ease-smooth"
            style={{ overflowWrap: 'anywhere' }}
          />
          {active && (
            <button
              type="button"
              onClick={onClear}
              aria-label="清除概念筛选"
              title="清除概念筛选"
              className="absolute right-1 top-1/2 -translate-y-1/2 inline-flex items-center justify-center
                h-6 w-6 rounded text-muted hover:text-foreground hover:bg-elevated
                max-md:h-11 max-md:w-11 transition-colors cursor-pointer"
            >
              <X className="h-3.5 w-3.5" aria-hidden />
            </button>
          )}
        </div>
      </div>

      {active && (
        <button
          type="button"
          onClick={onClear}
          className="inline-flex items-center gap-1 h-9 px-2 rounded text-xs text-muted
            hover:bg-danger/10 hover:text-danger transition-colors cursor-pointer
            max-md:min-h-11 max-md:min-w-11"
        >
          <RotateCcw className="h-3 w-3" aria-hidden />
          清除筛选
        </button>
      )}

      <p id={HELP_ID} className="sr-only">
        输入概念名可在当前股池内按概念板块筛选个股
      </p>
    </div>
  )
}
