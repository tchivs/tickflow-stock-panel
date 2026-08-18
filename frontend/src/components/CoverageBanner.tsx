import { AlertTriangle } from 'lucide-react'
import type { CoverageInfo } from '../lib/api'

/**
 * 数据不完整横幅 (M003): 当日 enriched 仅覆盖部分标的 (外部源故障/管道退化) 时,
 * 替代「裸零值」呈现 — 让用户一眼看出这是数据缺口, 不是市场真相。
 *
 * 完整时 (complete=true) 与字段缺失 (旧后端) 均不渲染, 零视觉变化。
 */
export function CoverageBanner({ coverage, subject = '全市场结果' }: { coverage?: CoverageInfo | null; subject?: string }) {
  if (!coverage || coverage.complete) return null
  return (
    <div
      role="status"
      className="mb-3 flex items-start gap-2 rounded-card border border-amber-500/30 bg-amber-500/8 px-3 py-2 text-[11px] leading-relaxed"
    >
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
      <div className="min-w-0 flex-1 text-secondary">
        当日数据不完整:{coverage.date} 仅覆盖 <strong className="text-foreground">{coverage.rows}</strong> 只(全市场约 {coverage.expected} 只),
        {subject}不可用,「无命中/暂无数据」是数据缺口而非市场真相。
        <span className="ml-1 text-muted">等待盘后数据管道补齐后自动恢复</span>
      </div>
    </div>
  )
}
