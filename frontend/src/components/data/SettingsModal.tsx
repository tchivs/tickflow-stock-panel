import { useRef } from 'react'
import { motion } from 'framer-motion'
import { X } from 'lucide-react'
import { useModalA11y } from '@/lib/useModalA11y'

export function SettingsModal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  const panelRef = useRef<HTMLDivElement>(null)
  // 焦点捕获 + Tab 陷阱 + ESC 关闭 + 卸载还原 (WCAG 2.1.2/2.1.1)
  useModalA11y(panelRef, { onClose })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <motion.div
        ref={panelRef}
        tabIndex={-1}
        initial={{ opacity: 0, scale: 0.95, y: 12 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 8 }}
        transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
        className="relative rounded-dialog border border-border bg-surface shadow-2xl mx-4 w-full max-w-md overflow-hidden focus:outline-none"
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
