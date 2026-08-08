import { useCallback, useEffect, useState } from 'react'
import { Check } from 'lucide-react'

// ===== 全局 toast 状态 =====
type ToastItem = { id: number; msg: string; kind: 'error' | 'success' }
let _id = 0
const _listeners: Set<(items: ToastItem[]) => void> = new Set()
let _queue: ToastItem[] = []

function _emit() { _listeners.forEach(fn => fn([..._queue])) }

function toast(msg: string, kind: 'error' | 'success' = 'error') {
  if (_queue.some(item => item.msg === msg && item.kind === kind)) return
  const item = { id: ++_id, msg, kind }
  _queue = [..._queue, item]
  _emit()
  setTimeout(() => { _queue = _queue.filter(t => t.id !== item.id); _emit() }, 4000)
}

export { toast }

// ===== Toast 容器 — 挂在 Layout 最顶层 =====
export function ToastContainer() {
  const [items, setItems] = useState<ToastItem[]>([])

  const sub = useCallback(() => {
    _listeners.add(setItems)
    return () => { _listeners.delete(setItems) }
  }, [])

  useEffect(sub, [sub])

  if (!items.length) return null

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="false"
      className="fixed bottom-4 right-4 z-[9999] flex w-[calc(100vw-2rem)] max-w-[420px] flex-col gap-2 pointer-events-none"
    >
      {items.map(t => (
        <div
          key={t.id}
          className={`pointer-events-auto flex max-w-full items-start gap-2 break-words [overflow-wrap:anywhere] px-4 py-2.5 rounded-lg shadow-lg text-sm font-medium animate-in slide-in-from-bottom-2 fade-in duration-200 ${
            t.kind === 'error'
              ? 'bg-danger/90 text-white'
              : 'bg-elevated text-foreground'
          }`}
        >
          {t.kind === 'success' && <Check className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden="true" />}
          <span>{t.msg}</span>
        </div>
      ))}
    </div>
  )
}
