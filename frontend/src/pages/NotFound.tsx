import { Link } from 'react-router-dom'
import { Logo } from '../components/Logo'

export function NotFound() {
  return (
    <div className="min-h-screen bg-base flex flex-col items-center justify-center gap-4 px-4 text-center">
      <Logo size={40} className="text-foreground" />
      <div>
        <h1 className="text-sm font-semibold text-foreground">404 · 页面不存在</h1>
        <p className="mt-1 text-xs text-muted">地址可能已变更,或该页面从未存在。</p>
      </div>
      <Link
        to="/"
        className="rounded-btn border border-border bg-surface px-4 py-2 text-xs font-medium text-foreground transition-colors hover:border-accent/50 hover:text-accent"
      >
        返回看板
      </Link>
    </div>
  )
}
