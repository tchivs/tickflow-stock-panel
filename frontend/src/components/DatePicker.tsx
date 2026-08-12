import { useState, useRef, useEffect, useMemo, type KeyboardEvent } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Calendar, ChevronLeft, ChevronRight } from 'lucide-react'

interface DatePickerProps {
  value: string          // YYYY-MM-DD
  onChange: (v: string) => void
  min?: string
  max?: string
  placeholder?: string
  className?: string
  buttonClassName?: string
  align?: 'left' | 'right'
}

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

function pad(n: number) { return String(n).padStart(2, '0') }
function toDateStr(y: number, m: number, d: number) {
  return `${y}-${pad(m + 1)}-${pad(d)}`
}
function todayStr() {
  const date = new Date()
  return toDateStr(date.getFullYear(), date.getMonth(), date.getDate())
}
function viewDate(value: string, min?: string, max?: string) {
  const source = value || max || min || todayStr()
  return {
    year: Number(source.slice(0, 4)),
    month: Number(source.slice(5, 7)) - 1,
  }
}

// ===== APG 日期网格方向键导航辅助 (周一为一周首日) =====
function parseDateStr(ds: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ds)
  if (!m) return null
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
}
function addDays(d: Date, n: number) {
  const x = new Date(d)
  x.setDate(d.getDate() + n)
  return x
}
function addMonths(d: Date, n: number) {
  // 切月后按目标月最后一天夹紧 (1/31 + 1月 → 2/28)
  const x = new Date(d.getFullYear(), d.getMonth() + n, 1)
  const last = new Date(x.getFullYear(), x.getMonth() + 1, 0).getDate()
  x.setDate(Math.min(d.getDate(), last))
  return x
}
function startOfWeek(d: Date) { return addDays(d, -(d.getDay() + 6) % 7) }
function endOfWeek(d: Date) { return addDays(startOfWeek(d), 6) }

export function DatePicker({
  value,
  onChange,
  min,
  max,
  placeholder = '选择日期',
  className = '',
  buttonClassName = '',
  align = 'right',
}: DatePickerProps) {
  const [open, setOpen] = useState(false)
  const [showYearPicker, setShowYearPicker] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  // 当前显示的月份
  const [viewYear, setViewYear] = useState(() => viewDate(value, min, max).year)
  const [viewMonth, setViewMonth] = useState(() => viewDate(value, min, max).month)

  // 当 value 外部变化时同步 view
  useEffect(() => {
    const next = viewDate(value, min, max)
    setViewYear(next.year)
    setViewMonth(next.month)
  }, [value, min, max])

  // 点击外部关闭
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const today = todayStr()

  const prevMonth = () => {
    if (viewMonth === 0) { setViewMonth(11); setViewYear(viewYear - 1) }
    else setViewMonth(viewMonth - 1)
  }
  const nextMonth = () => {
    if (viewMonth === 11) { setViewMonth(0); setViewYear(viewYear + 1) }
    else setViewMonth(viewMonth + 1)
  }

  // ===== APG 网格 roving tabindex: 只让「当前焦点日」进 Tab 序, 方向键在 42 格内移动 =====
  const [focusDate, setFocusDate] = useState<string>(() => value || todayStr())
  const cellRefs = useRef<(HTMLButtonElement | null)[]>([])
  const pendingFocus = useRef<string | null>(null)

  const cells = useMemo(() => {
    // 构建日历格子: 周一为第一天
    const firstDay = new Date(viewYear, viewMonth, 1).getDay()
    const offset = firstDay === 0 ? 6 : firstDay - 1          // 周一=0
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate()
    const prevMonthDays = new Date(viewYear, viewMonth, 0).getDate()
    const nextCells: { day: number; cur: boolean; dateStr: string; disabled: boolean }[] = []

    // 上月尾部
    for (let i = offset - 1; i >= 0; i--) {
      const d = prevMonthDays - i
      const m = viewMonth === 0 ? 11 : viewMonth - 1
      const y = viewMonth === 0 ? viewYear - 1 : viewYear
      const ds = toDateStr(y, m, d)
      nextCells.push({ day: d, cur: false, dateStr: ds, disabled: !!min && ds < min || !!max && ds > max })
    }
    // 当月
    for (let d = 1; d <= daysInMonth; d++) {
      const ds = toDateStr(viewYear, viewMonth, d)
      nextCells.push({ day: d, cur: true, dateStr: ds, disabled: !!min && ds < min || !!max && ds > max })
    }
    // 下月头部 — 补齐到 6 行 × 7 = 42
    const remain = 42 - nextCells.length
    for (let d = 1; d <= remain; d++) {
      const m = viewMonth === 11 ? 0 : viewMonth + 1
      const y = viewMonth === 11 ? viewYear + 1 : viewYear
      const ds = toDateStr(y, m, d)
      nextCells.push({ day: d, cur: false, dateStr: ds, disabled: !!min && ds < min || !!max && ds > max })
    }
    return nextCells
  }, [viewYear, viewMonth, min, max])

  // 打开时把焦点放到「选中日 || 今天 || 首个可用日」; 切月/箭头移动后聚焦 pendingFocus
  useEffect(() => {
    if (!open) return
    const inView = (ds: string) => cells.some(c => c.dateStr === ds && !c.disabled)
    const target = pendingFocus.current
      ?? (value && inView(value) ? value : undefined)
      ?? (inView(today) ? today : undefined)
      ?? cells.find(c => !c.disabled)?.dateStr
      ?? ''
    pendingFocus.current = null
    setFocusDate(target)
  }, [open, value, viewYear, viewMonth, today, cells])

  // roving tabindex 目标变化或切换月份后, 把 DOM 焦点移过去 (含从年份视图返回)
  useEffect(() => {
    if (!open || showYearPicker) return
    const idx = cells.findIndex(c => c.dateStr === focusDate)
    if (idx >= 0) cellRefs.current[idx]?.focus()
  }, [open, focusDate, viewYear, viewMonth, showYearPicker, cells])

  const onGridKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      // 内层弹层优先消费 Escape, 避免外层对话框一并关闭
      e.stopPropagation()
      setOpen(false)
      triggerRef.current?.focus()
      return
    }
    const fd = parseDateStr(focusDate)
    if (!fd) return
    let next: Date | null = null
    switch (e.key) {
      case 'ArrowLeft':  next = addDays(fd, -1); break
      case 'ArrowRight': next = addDays(fd, 1); break
      case 'ArrowUp':    next = addDays(fd, -7); break
      case 'ArrowDown':  next = addDays(fd, 7); break
      case 'Home':       next = startOfWeek(fd); break
      case 'End':        next = endOfWeek(fd); break
      case 'PageUp':     next = addMonths(fd, -1); break
      case 'PageDown':   next = addMonths(fd, 1); break
      default: return
    }
    if (!next) return
    e.preventDefault()
    const ds = toDateStr(next.getFullYear(), next.getMonth(), next.getDate())
    const inView = cells.some(c => c.dateStr === ds)
    if (!inView) {
      // 目标出了当前 42 格 → 先切月份, 渲染后由 focusDate effect 聚焦
      setViewYear(next.getFullYear())
      setViewMonth(next.getMonth())
    }
    pendingFocus.current = ds
    setFocusDate(ds)
  }

  // ===== 年份选择网格 APG 导航 (4 列 × 3 行; 箭头/Home/End/PageUp/PageDown; 焦点出批平移 12 年) =====
  const YEAR_BATCH = 12
  const [focusYear, setFocusYear] = useState<number>(() => viewYear)
  const yearRefs = useRef<(HTMLButtonElement | null)[]>([])
  const pendingYearFocus = useRef<number | null>(null)
  // 同 commit 内直接落焦点, 避免「open-effect setState → focus-move 读到旧值」的竞态
  const pendingYearDomFocus = useRef<number | null>(null)
  // 同步镜像 focusYear: 键盘处理器不依赖尚未提交的 state 闭包
  const focusYearRef = useRef<number>(viewYear)
  const moveYearFocus = (y: number) => { focusYearRef.current = y; setFocusYear(y) }

  // 打开年份选择时, 聚焦「选中年 (若在批内) || 当前 viewYear」
  useEffect(() => {
    if (!open || !showYearPicker) return
    const batchStart = viewYear - (YEAR_BATCH / 2 - 1)
    const batchEnd = viewYear + YEAR_BATCH / 2
    const selected = Number(value.slice(0, 4))
    const target = pendingYearFocus.current
      ?? (selected >= batchStart && selected <= batchEnd ? selected : viewYear)
    pendingYearFocus.current = null
    pendingYearDomFocus.current = target
    moveYearFocus(target)
  }, [open, showYearPicker, viewYear, value])

  // roving tabindex 目标变化或批窗口平移后, 把 DOM 焦点移过去 (优先 pending 目标)
  useEffect(() => {
    if (!open || !showYearPicker) return
    const target = pendingYearDomFocus.current ?? focusYear
    pendingYearDomFocus.current = null
    const idx = target - (viewYear - (YEAR_BATCH / 2 - 1))
    if (idx >= 0 && idx < YEAR_BATCH) yearRefs.current[idx]?.focus()
  }, [open, showYearPicker, focusYear, viewYear])

  const onYearKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      // 内层年份视图优先消费: 回日视图, 不透传到外层对话框
      e.stopPropagation()
      setShowYearPicker(false)
      return
    }
    const cur = focusYearRef.current
    let next: number | null = null
    switch (e.key) {
      case 'ArrowLeft':  next = cur - 1; break
      case 'ArrowRight': next = cur + 1; break
      case 'ArrowUp':    next = cur - 4; break
      case 'ArrowDown':  next = cur + 4; break
      case 'Home':       next = viewYear - (YEAR_BATCH / 2 - 1); break
      case 'End':        next = viewYear + YEAR_BATCH / 2; break
      case 'PageUp':     next = cur - YEAR_BATCH; break
      case 'PageDown':   next = cur + YEAR_BATCH; break
      default: return
    }
    e.preventDefault()
    const batchStart = viewYear - (YEAR_BATCH / 2 - 1)
    const batchEnd = viewYear + YEAR_BATCH / 2
    if (next < batchStart || next > batchEnd) {
      // 焦点出批 → 平移 12 年批窗口使 next 落在批内, 渲染后聚焦 (进入侧: 首位/末位)
      setViewYear(next < batchStart ? next + (YEAR_BATCH / 2 - 1) : next - YEAR_BATCH / 2)
      pendingYearFocus.current = next
      moveYearFocus(next)
    } else {
      moveYearFocus(next)
    }
  }

  // 构建日历格子: 周一为第一天
  const displayLabel = value || placeholder

  return (
    <div ref={ref} className={`relative inline-flex ${className}`}>
      {/* 触发按钮 */}
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="dialog"
        className={`inline-flex items-center gap-1.5 h-7 max-md:min-h-11 px-2.5 rounded-input border border-border
          bg-elevated hover:border-accent/50 text-xs text-foreground num
          focus:border-accent/60 focus-visible:ring-2 focus-visible:ring-accent/60 transition-colors duration-150 cursor-pointer ${buttonClassName}`}
      >
        <Calendar className="h-3.5 w-3.5 text-accent" />
        <span className={value ? undefined : 'text-muted'}>{displayLabel}</span>
      </button>

      {/* 弹出日历 */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.97 }}
            transition={{ duration: 0.15, ease: [0.16, 1, 0.3, 1] }}
            className={`absolute ${align === 'left' ? 'left-0' : 'right-0'} top-full mt-1.5 z-50 w-[260px] rounded-card border border-border
              bg-surface shadow-[0_8px_30px_rgba(0,0,0,0.4)] p-3`}
            role="group"
            aria-label={showYearPicker ? '选择年份' : '选择日期'}
          >
            {/* 月份导航 */}
            <div className="flex items-center justify-between mb-2">
              <button
                type="button"
                onClick={showYearPicker ? () => setViewYear(viewYear - 12) : prevMonth}
                aria-label={showYearPicker ? '上一批年份' : '上个月'}
                className="p-1 rounded-btn hover:bg-elevated text-secondary hover:text-foreground transition-colors"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setShowYearPicker(v => !v)}
                className="text-sm font-medium text-foreground num hover:text-accent transition-colors cursor-pointer"
              >
                {showYearPicker
                  ? `${viewYear - 5} - ${viewYear + 6}`
                  : `${viewYear} 年 ${viewMonth + 1} 月`
                }
              </button>
              <button
                type="button"
                onClick={showYearPicker ? () => setViewYear(viewYear + 12) : nextMonth}
                aria-label={showYearPicker ? '下一批年份' : '下个月'}
                className="p-1 rounded-btn hover:bg-elevated text-secondary hover:text-foreground transition-colors"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>

            {showYearPicker ? (
              /* 年份选择网格 — APG grid: 箭头/Home/End/PageUp/PageDown 移动 roving tabindex, Enter/Space 原生选中 */
              <div className="grid grid-cols-4 gap-1" onKeyDown={onYearKeyDown}>
                {Array.from({ length: 12 }, (_, i) => viewYear - 5 + i).map((y, i) => {
                  const isSelected = y === Number(value.slice(0, 4))
                  const isThisYear = y === new Date().getFullYear()
                  const isFocus = y === focusYear
                  return (
                    <button
                      key={y}
                      ref={el => { yearRefs.current[i] = el }}
                      type="button"
                      tabIndex={isFocus ? 0 : -1}
                      onClick={() => {
                        setViewYear(y)
                        setShowYearPicker(false)
                        // 焦点回到新月份网格: 若 value 同年仍可见则保持, 否则落 1 号
                        const keep = value && Number(value.slice(0, 4)) === y ? value : toDateStr(y, viewMonth, 1)
                        pendingFocus.current = keep
                        setFocusDate(keep)
                      }}
                      aria-current={isSelected ? 'true' : undefined}
                      className={`h-8 text-xs rounded-btn transition-colors duration-100
                        ${isSelected ? 'bg-accent-solid text-white font-bold' : ''}
                        ${isThisYear && !isSelected ? 'border border-accent/40' : ''}
                        ${!isSelected ? 'hover:bg-elevated cursor-pointer text-foreground' : ''}
                      `}
                    >
                      {y}
                    </button>
                  )
                })}
              </div>
            ) : (
              <>
                {/* 星期头 */}
                <div className="grid grid-cols-7 text-center text-[10px] text-muted mb-1">
                  {WEEKDAYS.map((w) => (
                    <div key={w}>{w}</div>
                  ))}
                </div>

                {/* 日期格子 — APG grid: 方向键/Home/End/PageUp/PageDown 移动 roving tabindex */}
                <div className="grid grid-cols-7 gap-px" onKeyDown={onGridKeyDown}>
                  {cells.map((c, i) => {
                    const isSelected = c.dateStr === value
                    const isToday = c.dateStr === today
                    const isFocus = c.dateStr === focusDate
                    return (
                      <button
                        key={i}
                        ref={el => { cellRefs.current[i] = el }}
                        type="button"
                        disabled={c.disabled}
                        tabIndex={isFocus ? 0 : -1}
                        aria-label={`${c.dateStr.slice(0, 4)}年${Number(c.dateStr.slice(5, 7))}月${c.day}日`}
                        aria-current={isSelected ? 'date' : undefined}
                        onClick={() => {
                          if (!c.disabled) {
                            setFocusDate(c.dateStr)
                            onChange(c.dateStr)
                            setOpen(false)
                          }
                        }}
                        className={`
                      h-7 w-full text-xs rounded-btn transition-colors duration-100
                      ${c.cur ? 'text-foreground' : 'text-muted/40'}
                      ${isSelected ? 'bg-accent-solid text-white font-bold' : ''}
                      ${isToday && !isSelected ? 'border border-accent/40' : ''}
                      ${!isSelected && !c.disabled ? 'hover:bg-elevated' : ''}
                      ${c.disabled ? 'opacity-20 cursor-not-allowed' : 'cursor-pointer'}
                    `}
                      >
                        {c.day}
                      </button>
                )
              })}
            </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
