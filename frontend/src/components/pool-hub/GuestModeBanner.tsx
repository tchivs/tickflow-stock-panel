import { Lock } from 'lucide-react'

// UI-SPEC Copywriting Contract — 游客横幅可访问文本 (aria) 与视觉文案。
// 掩码是数据, 不是文案: 横幅只陈述策略, 不引用掩码串本身 (UI-SPEC Copywriting Contract)。
const BANNER_TITLE = '游客模式：股票代码与名称已脱敏'
const BANNER_BODY = '仅展示涨跌幅与概念板块。'
export const GUEST_BANNER_ACCESSIBLE_TEXT = `${BANNER_TITLE}，${BANNER_BODY}`

/**
 * 游客模式横幅 — 会话策略状态 (非数据状态): 仅当服务端 mode === 'guest' 时渲染。
 * 中性 info 横幅: bg-elevated/60 + border-border + rounded-btn, Lock 图标 aria-hidden,
 * 标题 text-sm text-secondary, 正文 text-xs text-muted, role="status" (polite live region)。
 * 无关闭按钮 — 策略声明, 不是 toast (UI-SPEC Interaction States)。
 */
export function GuestModeBanner() {
  return (
    <div
      role="status"
      aria-label={GUEST_BANNER_ACCESSIBLE_TEXT}
      className="flex items-start gap-2 rounded-btn border border-border bg-elevated/60 px-3 py-2 [overflow-wrap:anywhere]"
    >
      <Lock className="h-3.5 w-3.5 mt-0.5 shrink-0" aria-hidden />
      <div className="min-w-0">
        <p className="text-sm text-secondary">{BANNER_TITLE}</p>
        <p className="text-xs text-muted">{BANNER_BODY}</p>
      </div>
    </div>
  )
}
