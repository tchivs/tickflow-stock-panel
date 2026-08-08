import { useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { X } from 'lucide-react'

export function SettingsModal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const panel = panelRef.current
    if (panel) {
      const firstFocusable = panel.querySelector<HTMLElement>(
        'button, input, select, textarea, [href], [tabindex]:not([tabindex="-1"])'
      )
      firstFocusable?.focus()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <motion.div
        ref={panelRef}
        initial={{ opacity: 0, scale: 0.95, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 8 }}
        transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
        className="relative rounded-card border border-border bg-surface shadow-2xl mx-4 w-full max-w-md overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-border">
          <h3 className="text-sm font-medium text-foreground">{title}</h3>
          <button onClick={onClose} aria-label="关闭" className="p-0.5 rounded hover:bg-elevated text-secondary">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="p-5">
          {children}
        </div>
      </motion.div>
    </div>
  )
}
