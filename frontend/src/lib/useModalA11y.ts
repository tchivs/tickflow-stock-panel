import { useEffect, useRef } from 'react'

/**
 * 模态对话框无障碍 hook — 给未走 <Modal> 原语的自定义对话框补上:
 *   - 打开时把焦点移入对话框 (initialFocusRef 或首个可聚焦元素)
 *   - Tab / Shift+Tab 焦点陷阱 (焦点不跑出对话框, WCAG 2.1.2)
 *   - ESC 关闭 (可选)
 *   - 卸载时把焦点还给打开前的元素
 *
 * 组件挂载 = 对话框打开 (调用方按 {open && <Dialog/>} 条件挂载)。
 * 对话框面板元素必须是可聚焦容器 (tabIndex={-1}), 否则对无焦点项的空面板回退聚焦面板本身。
 */
export function useModalA11y(
  panelRef: React.RefObject<HTMLElement | null>,
  { onClose, closeOnEscape = true, restoreFocus = true, initialFocusRef, active = true }: {
    onClose?: () => void
    closeOnEscape?: boolean
    restoreFocus?: boolean
    /** 打开时聚焦的元素; 不传则聚焦面板内首个可聚焦元素 */
    initialFocusRef?: React.RefObject<HTMLElement | null>
    /** 对话框是否打开。组件常驻挂载而内容按 open 条件渲染时传 false 禁用 */
    active?: boolean
  } = {},
) {
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  const initialFocusRefRef = useRef(initialFocusRef)
  initialFocusRefRef.current = initialFocusRef

  useEffect(() => {
    if (!active) return
    const prevActive = document.activeElement as HTMLElement | null

    const focusFirst = () => {
      if (initialFocusRefRef.current?.current) {
        initialFocusRefRef.current.current.focus()
        return
      }
      const panel = panelRef.current
      if (!panel) return
      const first = panel.querySelector<HTMLElement>(FOCUSABLE)
      ;(first ?? panel).focus()
    }
    // 等一帧确保内容已挂载
    const raf = requestAnimationFrame(focusFirst)

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && closeOnEscape) {
        e.stopPropagation()
        onCloseRef.current?.()
        return
      }
      if (e.key !== 'Tab') return
      const panel = panelRef.current
      if (!panel) return
      const nodes = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE))
        .filter(el => el.offsetParent !== null || el === document.activeElement)
      if (nodes.length === 0) {
        e.preventDefault()
        panel.focus()
        return
      }
      const first = nodes[0]
      const last = nodes[nodes.length - 1]
      const active = document.activeElement as HTMLElement | null
      if (e.shiftKey) {
        if (active === first || !panel.contains(active)) {
          e.preventDefault()
          last.focus()
        }
      } else if (active === last || !panel.contains(active)) {
        e.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', onKeyDown, true)
    return () => {
      cancelAnimationFrame(raf)
      document.removeEventListener('keydown', onKeyDown, true)
      if (restoreFocus) prevActive?.focus?.()
    }
    // onClose/initialFocus 走 ref; closeOnEscape/restoreFocus 为常量; 仅 active 切换会重建。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active])
}

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')
