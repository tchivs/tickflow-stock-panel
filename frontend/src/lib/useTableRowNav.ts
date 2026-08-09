import { useEffect, useRef } from 'react'

/**
 * APG 风格行级 roving-tabindex 键盘导航 (数据网格方向键, WCAG 2.1.1)。
 *
 * 语义: 表格的「行」是 Tab 焦点停靠点 — 一次 Tab 进表停到当前行; ↑/↓/Home/End/
 * PageUp/PageDown 在行间移动 (Page 步长 10); Tab 继续走行内按钮。保留原生表格语义
 * (role=row/cell 不变), 不改 role, 不加 aria-activedescendant。
 *
 * 挂接:
 *   const { tbodyRef, onRowFocus, onRowKeyDown } = useTableRowNav(rows)
 *   <tbody ref={tbodyRef}> <tr onFocus={onRowFocus} onKeyDown={onRowKeyDown}> …
 *
 * tabIndex 全部由本 hook 命令式维护 (不在 JSX 声明), 避免 React 每次重渲染把
 * roving 停靠点重置回首行。rows 变更时重建停靠点: 保留仍在视图内的当前行, 否则回首行。
 */
export const TABLE_ROW_NAV_KEYS = 'ArrowUp ArrowDown Home End PageUp PageDown'

const PAGE_STEP = 10

export function useTableRowNav<T extends HTMLElement>(rows: unknown[]) {
  const tbodyRef = useRef<T>(null)

  // rows 变化后重建 roving 停靠点 (tab 停靠保持/回退首行)。
  useEffect(() => {
    const tbody = tbodyRef.current
    if (!tbody) return
    const trs = Array.from(tbody.querySelectorAll<HTMLTableRowElement>('tr'))
    if (trs.length === 0) return
    const current = trs.find(tr => tr.tabIndex === 0)
    const target = current ?? trs[0]
    for (const tr of trs) tr.tabIndex = tr === target ? 0 : -1
  }, [rows])

  // 行内任意元素获得焦点 (含行内按钮被点击/Tab 到) → 该行成为 roving 停靠点。
  const onRowFocus = (e: React.FocusEvent<HTMLTableRowElement>) => {
    const tbody = tbodyRef.current
    if (!tbody) return
    const self = e.currentTarget
    for (const tr of tbody.querySelectorAll<HTMLTableRowElement>('tr')) {
      tr.tabIndex = tr === self ? 0 : -1
    }
  }

  const onRowKeyDown = (e: React.KeyboardEvent<HTMLTableRowElement>) => {
    const tbody = tbodyRef.current
    if (!tbody) return
    const trs = Array.from(tbody.querySelectorAll<HTMLTableRowElement>('tr'))
    const idx = trs.indexOf(e.currentTarget)
    if (idx < 0) return
    let next: number | null = null
    switch (e.key) {
      case 'ArrowDown':  next = Math.min(idx + 1, trs.length - 1); break
      case 'ArrowUp':    next = Math.max(idx - 1, 0); break
      case 'Home':       next = 0; break
      case 'End':        next = trs.length - 1; break
      case 'PageDown':   next = Math.min(idx + PAGE_STEP, trs.length - 1); break
      case 'PageUp':     next = Math.max(idx - PAGE_STEP, 0); break
      default: return
    }
    e.preventDefault()
    const target = trs[next]
    if (!target) return
    for (const tr of trs) tr.tabIndex = tr === target ? 0 : -1
    target.focus()
  }

  return { tbodyRef, onRowFocus, onRowKeyDown }
}
