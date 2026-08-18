import { type ReactNode, useState } from 'react'
import { ChevronDown } from 'lucide-react'

interface ResearchFoldProps {
  /** localStorage 记忆键;同一键跨会话保持折叠状态 */
  storageKey: string
  title: string
  children: ReactNode
}

/**
 * 回测页研究工具折叠容器:默认折叠,展开状态记忆在 localStorage。
 * 目的:主路径「配置 → 运行回测」保持首屏聚焦,研究面板按需展开。
 */
export function ResearchFold({ storageKey, title, children }: ResearchFoldProps) {
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem(storageKey) === '1' } catch { return false }
  })
  const toggle = () => {
    const next = !open
    setOpen(next)
    try { localStorage.setItem(storageKey, next ? '1' : '0') } catch { /* 隐私模式等场景忽略 */ }
  }
  return (
    <section className="rounded-card border border-border bg-surface/60">
      <button
        onClick={toggle}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left"
      >
        <span className="text-xs font-semibold tracking-wide text-secondary">{title}</span>
        <ChevronDown className={`h-4 w-4 shrink-0 text-muted transition-transform ${open ? '' : '-rotate-90'}`} aria-hidden="true" />
      </button>
      {open && <div className="border-t border-border/60 p-3">{children}</div>}
    </section>
  )
}
