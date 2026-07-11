import { useState, useRef, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { RadioTower, Plus, Trash2, Settings2, Zap, Bell, ListChecks, BellRing, TrendingUp, TrendingDown, Flame, Check, Clock3, AlertTriangle, Moon } from 'lucide-react'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { Skeleton } from '@/components/data/Skeleton'
import { Modal } from '@/components/Modal'
import { api, type MonitorRule, type AlertEvent, type MonitorCondition, type DeliveryStatus, type DeliveryOutcome } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { fmtPrice, fmtPct } from '@/lib/format'
import { cn } from '@/lib/cn'
import { cnSignal } from '@/lib/signals'
import { boardTag } from '@/components/stock-table/primitives'
import { markSeen, resetBadge, leaveMonitorPage } from '@/lib/monitorBadge'
import { RuleEditor } from '@/components/monitor/RuleEditor'
import { DeliveryDetailDialog } from '@/components/monitor/DeliveryDetailDialog'
import { StockPreviewDialog } from '@/components/StockPreviewDialog'

const TYPE_LABEL: Record<string, string> = {
  position: '持仓', signal: '信号', price: '价格', market: '市场', strategy: '策略',
}

/** 严重级别 → 左侧色条 + 图标 */
const SEVERITY_CONFIG: Record<string, { bar: string; icon: any; iconCls: string }> = {
  info:     { bar: 'bg-accent/40',       icon: Bell,        iconCls: 'text-accent' },
  warn:     { bar: 'bg-warning',          icon: TrendingUp,  iconCls: 'text-warning' },
  critical: { bar: 'bg-danger',           icon: Flame,       iconCls: 'text-danger' },
}
const SOURCE_BADGE_STYLE: Record<string, string> = {
  position: 'bg-accent/10 text-accent border-accent/20',
  strategy: 'bg-amber-400/10 text-amber-400 border-amber-400/20',
  signal:   'bg-accent/10 text-accent border-accent/20',
  price:    'bg-emerald-400/10 text-emerald-400 border-emerald-400/20',
  market:   'bg-purple-500/10 text-purple-400 border-purple-500/20',
}

const DELIVERY_LABEL: Record<DeliveryStatus, { label: string; icon: typeof Check; className: string }> = {
  pending: { label: '待投递', icon: Clock3, className: 'text-muted' },
  sent: { label: '已发送', icon: Check, className: 'text-emerald-500' },
  failed: { label: '投递失败', icon: AlertTriangle, className: 'text-danger' },
  skipped: { label: '已跳过', icon: Moon, className: 'text-warning' },
}

/**
 * 渲染策略类消息 — 策略名黄色、新入选绿、移出红、其余白色。
 */
function renderMessage(source: string, message: string) {
  if (source !== 'strategy') {
    return <span className="text-secondary">{message}</span>
  }
  const m = message.match(/^(策略「)([^」]+)(」)(新入选|移出)( .*)$/)
  if (!m) return <span className="text-foreground">{message}</span>
  const [, pre, strategyName, mid, direction, post] = m
  return (
    <>
      <span className="text-foreground/80">{pre}</span>
      <span className="text-amber-400 font-medium">{strategyName}</span>
      <span className="text-foreground/80">{mid}</span>
      <span className={direction === '新入选' ? 'text-emerald-400 font-medium' : 'text-danger font-medium'}>{direction}</span>
      <span className="text-foreground/80">{post}</span>
    </>
  )
}

export function Monitor() {
  const qc = useQueryClient()
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<MonitorRule | null>(null)

  // 触发记录: 类型、严重级别与投递状态均来自持久化历史。
  const [filter, setFilter] = useState<'all' | 'position' | 'strategy' | 'signal' | 'price' | 'market'>('all')
  const [severity, setSeverity] = useState<'all' | 'info' | 'warn' | 'critical'>('all')
  const [delivery, setDelivery] = useState<'all' | DeliveryStatus>('all')
  const [deliveryEventId, setDeliveryEventId] = useState<string | null>(null)
  const [confirmClear, setConfirmClear] = useState(false)
  const [confirmClearRules, setConfirmClearRules] = useState(false)
  const alertsQuery = useQuery({
    queryKey: QK.alerts(
      filter === 'all' ? undefined : filter,
      severity === 'all' ? undefined : severity,
      delivery === 'all' ? undefined : delivery,
    ),
    queryFn: () => api.alertsList({
      days: 7, limit: 500,
      source: filter === 'all' ? undefined : filter,
      severity: severity === 'all' ? undefined : severity,
      delivery_status: delivery === 'all' ? undefined : delivery,
    }),
    placeholderData: previous => previous,
    // 新告警靠 SSE 失效推送; 但 pending→sent/failed 的投递状态迁移没有 SSE 事件,
    // 只要列表里还有待投递的行就保持轮询, 全部尘埃落定后停止。
    refetchInterval: query => {
      const alerts = query.state.data?.alerts ?? []
      return alerts.some(ev => (ev.deliveries ?? []).some(d => d.status === 'pending')) ? 10000 : false
    },
  })
  const total = alertsQuery.data?.total ?? 0

  // 规则个数
  const rulesQuery = useQuery({ queryKey: QK.monitorRules, queryFn: api.monitorRulesList })
  const rulesCount = rulesQuery.data?.rules.length ?? 0

  // 清除全部规则 (逐条删除)
  const clearRulesMut = useMutation({
    mutationFn: async () => {
      const rules = rulesQuery.data?.rules ?? []
      await Promise.all(rules.map(r => api.monitorRuleDelete(r.id)))
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.monitorRules })
      setConfirmClearRules(false)
    },
  })

  // 进入监控页: 清零未读徽标 + 记录"进入时刻", 之后新增的记录会闪烁
  // 离开监控页: 停止同步, 之后新增才计入未读
  const enterTsRef = useRef<number>(Date.now())
  useEffect(() => {
    enterTsRef.current = Date.now()
    markSeen()
    return () => leaveMonitorPage()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="flex flex-col h-full">
      <PageHeader title="监控中心" subtitle="实时信号与规则管理" />
      <div className="flex-1 min-h-0 px-4 py-4 sm:px-5">
        <div className="mx-auto flex h-full max-w-7xl flex-col gap-4 md:flex-row">
          <section aria-label="触发记录" className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-card border border-border bg-surface/40">
            <div className="flex flex-wrap items-center gap-2 border-b border-border/60 bg-surface/60 px-3 py-3">
              <SectionHeader icon={BellRing} title="触发记录" />
              <div className="order-3 flex w-full flex-wrap items-center gap-1 md:order-none md:w-auto" aria-label="告警类型筛选">
                {(['all', 'position', 'price', 'signal', 'market', 'strategy'] as const).map(value => <button key={value} type="button" aria-pressed={filter === value} onClick={() => setFilter(value)} className={cn('min-h-8 rounded-btn px-2 text-xs', filter === value ? 'bg-accent/15 text-accent' : 'text-muted hover:bg-elevated hover:text-secondary')}>{value === 'all' ? '全部' : TYPE_LABEL[value]}</button>)}
              </div>
              <label className="sr-only" htmlFor="monitor-severity">严重级别</label>
              <select id="monitor-severity" value={severity} onChange={event => setSeverity(event.target.value as typeof severity)} className="h-8 rounded-btn border border-border bg-base px-2 text-xs text-secondary"><option value="all">全部级别</option><option value="info">普通</option><option value="warn">警告</option><option value="critical">重要</option></select>
              <label className="sr-only" htmlFor="monitor-delivery">投递状态</label>
              <select id="monitor-delivery" value={delivery} onChange={event => setDelivery(event.target.value as typeof delivery)} className="h-8 rounded-btn border border-border bg-base px-2 text-xs text-secondary"><option value="all">全部投递</option><option value="pending">待投递</option><option value="sent">已发送</option><option value="failed">投递失败</option><option value="skipped">已跳过</option></select>
              <div className="ml-auto flex items-center gap-2">
                <span className="rounded-md bg-elevated/50 px-1.5 py-0.5 text-[10px] font-medium text-muted">{total}</span>
                {total > 0 && <button onClick={() => setConfirmClear(true)} className="inline-flex min-h-8 items-center gap-1 rounded-btn px-2 text-xs text-muted hover:bg-danger/10 hover:text-danger"><Trash2 className="h-3 w-3" />清空</button>}
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-3">
              <AlertsList alertsQuery={alertsQuery} confirmClear={confirmClear} setConfirmClear={setConfirmClear} total={total} enterTs={enterTsRef.current} onDelivery={setDeliveryEventId} />
            </div>
          </section>

          {/* 右栏: 监控规则 */}
          <section aria-label="监控规则" className="flex min-h-0 w-full flex-col overflow-hidden rounded-card border border-border bg-surface/40 md:w-[400px] md:shrink-0">
            <div className="flex items-center gap-3 border-b border-border/60 bg-surface/60 px-4 py-2.5">
              <SectionHeader icon={ListChecks} title="监控规则" />
              <span className="rounded-md bg-elevated/50 px-1.5 py-0.5 text-[10px] font-medium text-muted">{rulesCount}</span>
              <div className="ml-auto flex items-center gap-1">
                <button
                  onClick={() => { setEditingRule(null); setEditorOpen(true) }}
                  title="新建规则"
                  className="inline-flex h-6 w-6 items-center justify-center rounded-lg border border-border/60 bg-surface text-muted transition-all hover:border-accent/40 hover:text-accent hover:shadow-sm cursor-pointer"
                >
                  <Plus className="h-3.5 w-3.5" />
                </button>
                <button
                  onClick={() => setConfirmClearRules(true)}
                  disabled={rulesCount === 0}
                  title="清除全部规则"
                  className="inline-flex h-6 w-6 items-center justify-center rounded-lg border border-border/60 bg-surface text-muted transition-all hover:border-danger/40 hover:text-danger disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-3.5">
              <RulesList
                rulesQuery={rulesQuery}
                onEdit={(r) => { setEditingRule(r); setEditorOpen(true) }}
              />
            </div>
          </section>
        </div>
      </div>

      <RuleEditorDialog
        open={editorOpen}
        rule={editingRule}
        onClose={() => { setEditorOpen(false); setEditingRule(null) }}
      />
      {deliveryEventId && <DeliveryDetailDialog eventId={deliveryEventId} onClose={() => setDeliveryEventId(null)} />}

      <ConfirmDialog
        open={confirmClearRules}
        title="清除全部监控规则?"
        message={`将删除全部 ${rulesCount} 条规则,此操作不可撤销。`}
        confirmText="清除"
        danger
        onCancel={() => setConfirmClearRules(false)}
        onConfirm={() => clearRulesMut.mutate()}
        pending={clearRulesMut.isPending}
      />
    </div>
  )
}

function SectionHeader({ icon: Icon, title }: { icon: any; title: string }) {
  return (
    <div className="flex items-center gap-1.5 shrink-0">
      <Icon className="h-4 w-4 text-accent" />
      <h2 className="text-sm font-semibold text-foreground whitespace-nowrap">{title}</h2>
    </div>
  )
}

// ── 触发记录列表 ──────────────────────────────────────
function AlertsList({ alertsQuery, confirmClear, setConfirmClear, total, enterTs, onDelivery }: {
  alertsQuery: ReturnType<typeof useQuery>
  confirmClear: boolean
  setConfirmClear: (v: boolean) => void
  total: number
  enterTs: number
  onDelivery: (eventId: string) => void
}) {
  const qc = useQueryClient()
  const [confirmTs, setConfirmTs] = useState<number | null>(null)
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [previewEv, setPreviewEv] = useState<AlertEvent | null>(null)

  const clearMut = useMutation({
    mutationFn: api.alertsClear,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['alerts'] }); setConfirmClear(false); resetBadge() },
  })
  const delMut = useMutation({
    mutationFn: (ts: number) => api.alertDelete(ts),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })

  // 点击删除: 第一次进入确认态, 第二次真删, 3 秒后自动复位
  const handleClickDelete = (ts: number) => {
    if (confirmTs === ts) {
      // 第二次点击 → 真删
      if (resetTimer.current) clearTimeout(resetTimer.current)
      setConfirmTs(null)
      delMut.mutate(ts)
    } else {
      // 第一次点击 → 进入确认态, 3 秒后自动复位
      setConfirmTs(ts)
      if (resetTimer.current) clearTimeout(resetTimer.current)
      resetTimer.current = setTimeout(() => setConfirmTs(null), 3000)
    }
  }

  const events = (alertsQuery.data as any)?.alerts ?? []

  return (
    <div className="space-y-3">
      {alertsQuery.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} h="h-14" rounded="rounded-card" />
          ))}
        </div>
      ) : events.length === 0 ? (
        <EmptyState
          icon={Bell}
          title="暂无触发记录"
          hint="监控规则命中后,触发记录会出现在这里。可在右侧配置规则,或在个股详情页加入监控。"
        />
      ) : (
        <div className="space-y-2">
              {events
                .filter((ev: any) => !(ev.source === 'strategy' && !ev.symbol))
                .map((ev: any, i: number) => {
            const sev = SEVERITY_CONFIG[ev.severity ?? 'info'] ?? SEVERITY_CONFIG.info
            const SevIcon = sev.icon
            const isNew = ev.ts > enterTs
            // 摘要徽标取最需要关注的一条: 失败 > 待投递 > 已发送 > 已跳过;
            // 多渠道且有已发送时显示 x/y 计数, 混合结果 (如 1 发送 + 1 跳过) 不会被首条掩盖。
            const outcomes: DeliveryOutcome[] = ev.deliveries ?? []
            const primaryDelivery = outcomes.find(outcome => outcome.status === 'failed')
              ?? outcomes.find(outcome => outcome.status === 'pending')
              ?? outcomes.find(outcome => outcome.status === 'sent')
              ?? outcomes[0]
            return (
              <motion.div
                key={`${ev.ts}-${i}`}
                initial={isNew ? { opacity: 0, y: -8, scale: 0.98 } : { opacity: 0, y: 4 }}
                animate={isNew ? {
                  opacity: [0, 1, 1, 0.85, 1],
                  scale: [0.98, 1, 1, 1.01, 1],
                  y: [-8, 0, 0, 0, 0],
                } : { opacity: 1, y: 0 }}
                transition={isNew ? { duration: 1.2, times: [0, 0.2, 0.5, 0.75, 1] } : { duration: 0.2, delay: Math.min(i * 0.02, 0.2) }}
                className={cn(
                  'group relative flex items-start gap-3 overflow-hidden rounded-lg border bg-surface pl-3.5 pr-3 py-2.5 shadow-sm transition-all duration-200 hover:border-border hover:shadow-md hover:shadow-black/10 hover:-translate-y-px',
                  isNew ? 'border-accent/60 ring-1 ring-accent/30' : 'border-border/50',
                )}
              >
                <div className={cn('absolute left-0 top-0 h-full w-0.5', sev.bar)} />
                <div className={cn('mt-px shrink-0', sev.iconCls)}>
                  <SevIcon className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  {ev.source === 'strategy' ? (() => {
                    const sm = ev.message?.match(/策略「([^」]+)」/)
                    const sname = sm ? sm[1] : ''
                    const isNew = ev.type === 'new_entry'
                    const _pct = ev.change_pct ?? 0
                    return (
                      <>
                        <div className="flex items-center gap-2 flex-wrap">
                          {ev.symbol && (() => {
                            const board = boardTag(ev.symbol)
                            return (
                              <button
                                onClick={() => setPreviewEv(ev)}
                                className="inline-flex items-center gap-1.5 rounded hover:bg-elevated/50 px-1 -mx-1 transition-colors cursor-pointer"
                                title="点击查看日K"
                              >
                                <span className="font-mono text-xs font-medium text-foreground hover:text-accent">{ev.symbol}</span>
                                {board && (
                                  <span className={`inline-flex items-center justify-center h-3.5 w-3.5 rounded text-[8px] font-bold leading-none border ${board.color}`}>
                                    {board.label}
                                  </span>
                                )}
                                {ev.name && <span className="text-xs text-secondary truncate max-w-[8rem] hover:text-foreground">{ev.name}</span>}
                              </button>
                            )
                          })()}
                          {ev.price != null && (
                            <span className={cn('inline-flex items-center gap-0.5 text-[11px] font-mono', _pct >= 0 ? 'text-danger' : 'text-bear')}>
                              {_pct >= 0 ? <TrendingUp className="h-2.5 w-2.5" /> : <TrendingDown className="h-2.5 w-2.5" />}
                              {fmtPrice(ev.price)}
                            </span>
                          )}
                          {ev.change_pct != null && (
                            <span className={cn('text-[11px] font-mono font-medium',
                              _pct >= 0 ? 'text-danger' : 'text-bear')}>
                              {fmtPct(_pct)}
                            </span>
                          )}
                          <span className={cn('rounded border px-1.5 py-0.5 text-[9px] font-medium', SOURCE_BADGE_STYLE.strategy)}>
                            {sname}
                          </span>
                        </div>
                        <div className="mt-1 flex items-center gap-1.5">
                          <span className={cn('text-[11px] font-medium', isNew ? 'text-danger' : 'text-emerald-400')}>
                            {isNew ? '进入' : '移出'}
                          </span>
                          <span className="text-[11px] text-foreground/80">策略</span>
                          <span className="text-[11px] font-medium text-amber-400">「{sname}」</span>
                        </div>
                      </>
                    )
                  })() : (
                    <>
                      <div className="flex items-center gap-2 flex-wrap">
                        {ev.symbol && (() => {
                          const board = boardTag(ev.symbol)
                          return (
                            <button
                              onClick={() => setPreviewEv(ev)}
                              className="inline-flex items-center gap-1.5 rounded hover:bg-elevated/50 px-1 -mx-1 transition-colors cursor-pointer"
                              title="点击查看日K"
                            >
                              <span className="font-mono text-xs font-medium text-foreground hover:text-accent">{ev.symbol}</span>
                              {board && (
                                <span className={`inline-flex items-center justify-center h-3.5 w-3.5 rounded text-[8px] font-bold leading-none border ${board.color}`}>
                                  {board.label}
                                </span>
                              )}
                              {ev.name && <span className="text-xs text-secondary truncate max-w-[8rem] hover:text-foreground">{ev.name}</span>}
                            </button>
                          )
                        })()}
                        {ev.price != null && (
                          <span className={cn('inline-flex items-center gap-0.5 text-[11px] font-mono', (ev.change_pct ?? 0) >= 0 ? 'text-danger' : 'text-bear')}>
                            {(ev.change_pct ?? 0) >= 0 ? <TrendingUp className="h-2.5 w-2.5" /> : <TrendingDown className="h-2.5 w-2.5" />}
                            {fmtPrice(ev.price)}
                          </span>
                        )}
                        {ev.change_pct != null && (
                          <span className={cn('text-[11px] font-mono font-medium',
                            ev.change_pct >= 0 ? 'text-danger' : 'text-bear')}>
                            {fmtPct(ev.change_pct)}
                          </span>
                        )}
                        <span className={cn('rounded border px-1.5 py-0.5 text-[9px] font-medium', SOURCE_BADGE_STYLE[ev.source] ?? 'bg-elevated text-muted border-border')}>
                          {(() => {
                            // 优先用规则名 (如 "策略监控 · 空中加油" → "空中加油"); 退回到 type 标签
                            const rn = ev.rule_name ?? ''
                            const dotIdx = rn.indexOf(' · ')
                            return dotIdx >= 0 ? rn.slice(dotIdx + 3) : (rn || (TYPE_LABEL[ev.source] ?? ev.source))
                          })()}
                        </span>
                      </div>
                      {/* 详情行: 命中条件 (signal/price/market) + 当前价 / 或默认消息 */}
                      {(ev.conditions && ev.conditions.length > 0) ? (
                        <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[11px]">
                          <span className="text-muted">命中</span>
                          {ev.conditions.map((c: MonitorCondition, ci: number) => (
                            <span key={ci} className="inline-flex items-center gap-0.5">
                              {ci > 0 && <span className="text-secondary">{ev.logic === 'or' ? '或' : '且'}</span>}
                              {c.op === 'truth' ? (
                                <span className="text-accent/80">{cnSignal(c.field)}</span>
                              ) : (
                                <span className="text-foreground/80 font-mono">{cnSignal(c.field)}{c.op}{c.value}</span>
                              )}
                            </span>
                          ))}
                          {ev.price != null && (
                            <>
                              <span className="text-muted">·</span>
                              <span className="text-muted">现价</span>
                              <span className="font-mono text-foreground/90">{fmtPrice(ev.price)}</span>
                            </>
                          )}
                        </div>
                      ) : (
                        <div className="mt-1 flex items-center gap-2">
                          <span className="text-[11px]">{renderMessage(ev.source, ev.message)}</span>
                        </div>
                      )}
                      {ev.signals && ev.signals.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {ev.signals.map((s: string, j: number) => (
                            <span key={j} className="rounded bg-accent/8 px-1.5 py-0.5 text-[9px] text-accent/70">{cnSignal(s)}</span>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                  <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[10px] text-muted">
                    {ev.account_id != null && <span>账户 {ev.account_id}</span>}
                    {ev.position_id != null && <span>持仓 {ev.position_id}</span>}
                    {ev.valuation_source && <span>估值来源 {ev.valuation_source === 'shared_quote' ? '共享报价' : ev.valuation_source === 'governed_close' ? '治理收盘价' : '暂无法估值'}</span>}
                    {ev.valuation_as_of && <time className="font-mono">{ev.valuation_as_of}</time>}
                  </div>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <span className="text-[10px] text-muted/60 font-mono">
                    {new Date(ev.occurred_at ?? ev.ts).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                  </span>
                  {/* 无 primaryDelivery = 规则未配置外部渠道, 永远不会有投递记录 — 不渲染任何状态,
                      避免误导性的常驻「待投递」。 */}
                  {primaryDelivery && (() => {
                    const meta = DELIVERY_LABEL[primaryDelivery.status]
                    const Icon = meta.icon
                    return ev.id ? <button type="button" onClick={() => onDelivery(ev.id)} className={`inline-flex min-h-7 items-center gap-1 rounded-btn px-1.5 text-[10px] ${meta.className} hover:bg-elevated`} title="查看投递详情"><Icon className="h-3 w-3" />{outcomes.length > 1 && primaryDelivery.status === 'sent' ? `${outcomes.filter(outcome => outcome.status === 'sent').length}/${outcomes.length} 已发送` : meta.label}</button> : <span className={`inline-flex items-center gap-1 text-[10px] ${meta.className}`}><Icon className="h-3 w-3" />{meta.label}</span>
                  })()}

                  {confirmTs === ev.ts ? (
                    // 确认态: 红色实心按钮 (原删除图标位置), 再点确认删除
                    <button
                      onClick={() => handleClickDelete(ev.ts)}
                      title="再次点击确认删除"
                      className="inline-flex items-center gap-1 rounded-md bg-danger/15 px-1.5 py-0.5 text-[10px] font-medium text-danger border border-danger/30 animate-pulse cursor-pointer"
                    >
                      <Trash2 className="h-2.5 w-2.5" />确认
                    </button>
                  ) : (
                    <button
                      onClick={() => handleClickDelete(ev.ts)}
                      disabled={delMut.isPending}
                      title="删除"
                      className="rounded p-1 text-muted/0 transition-colors group-hover:text-muted/40 hover:!text-danger hover:bg-danger/10 cursor-pointer"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  )}
                </div>
              </motion.div>
            )
          })}
        </div>
      )}

      <ConfirmDialog
        open={confirmClear}
        title="清空全部触发记录?"
        message={`将删除全部 ${total} 条记录,此操作不可撤销。`}
        confirmText="清空"
        danger
        onCancel={() => setConfirmClear(false)}
        onConfirm={() => clearMut.mutate()}
        pending={clearMut.isPending}
      />

      <StockPreviewDialog
        symbol={previewEv?.symbol ?? null}
        name={previewEv?.name ?? undefined}
        triggerInfo={previewEv ? {
          price: previewEv.price ?? null,
          changePct: previewEv.change_pct ?? null,
          ts: previewEv.ts,
          signals: previewEv.signals,
          message: previewEv.message,
        } : null}
        onClose={() => setPreviewEv(null)}
      />
    </div>
  )
}

// ── 监控规则列表 ──────────────────────────────────────
function RulesList({ rulesQuery, onEdit }: {
  rulesQuery: ReturnType<typeof useQuery>
  onEdit: (rule: MonitorRule) => void
}) {
  const qc = useQueryClient()
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [previewSymbol, setPreviewSymbol] = useState<string | null>(null)
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const rules: MonitorRule[] = (rulesQuery.data as any)?.rules ?? []

  // 收集所有规则的股票代码, 批量查名称
  const allSymbols = useMemo(() => {
    const set = new Set<string>()
    for (const r of rules) {
      if (r.scope === 'symbols') r.symbols.forEach(s => set.add(s))
    }
    return Array.from(set)
  }, [rules])
  const namesQuery = useQuery({
    queryKey: ['instrument-names', allSymbols.join(',')],
    queryFn: () => api.instrumentNames(allSymbols),
    enabled: allSymbols.length > 0,
    staleTime: 300000,
  })
  const symbolNames = namesQuery.data?.names ?? {}

  const del = useMutation({
    mutationFn: api.monitorRuleDelete,
    onSuccess: () => qc.invalidateQueries({ queryKey: QK.monitorRules }),
  })
  const toggleEnabled = (rule: MonitorRule) => {
    api.monitorRuleSave({ ...rule, enabled: !rule.enabled }).then(() =>
      qc.invalidateQueries({ queryKey: QK.monitorRules }),
    )
  }

  // 点击删除: 第一次进入确认态, 第二次真删, 3 秒后自动复位
  const handleClickDelete = (id: string) => {
    if (confirmId === id) {
      if (resetTimer.current) clearTimeout(resetTimer.current)
      setConfirmId(null)
      del.mutate(id)
    } else {
      setConfirmId(id)
      if (resetTimer.current) clearTimeout(resetTimer.current)
      resetTimer.current = setTimeout(() => setConfirmId(null), 3000)
    }
  }

  return (
    <div className="space-y-2.5">
      {rulesQuery.isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} h="h-16" rounded="rounded-card" />
          ))}
        </div>
      ) : rules.length === 0 ? (
        <EmptyState
          icon={RadioTower}
          title="暂无监控规则"
          hint="点击标题栏「+」新建规则,或在个股详情页点「加监控」快速添加。"
        />
      ) : (
        rules.map(r => {
          // 名称截取: "策略监控 · MACD金叉" → "MACD金叉", "个股信号监控 · 300750.SZ" → "个股信号监控"
          const dotIdx = r.name.indexOf(' · ')
          const displayName = dotIdx >= 0 ? r.name.slice(dotIdx + 3) : r.name
          return (
            <motion.div
              key={r.id}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
              className={cn(
                'group relative overflow-hidden rounded-lg border pl-3.5 pr-2.5 py-2 shadow-sm transition-all duration-200 hover:shadow-md hover:shadow-black/10',
                r.enabled
                  ? 'border-border/50 bg-surface hover:border-accent/30'
                  : 'border-border/30 bg-surface/40 opacity-70 hover:opacity-100',
              )}
            >
              {/* 左侧状态条 */}
              <div className={cn('absolute left-0 top-0 h-full w-0.5', r.enabled ? 'bg-accent/50' : 'bg-border')} />

              {/* 第一行: 分类标签 + 名称 + 操作按钮 */}
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span className={cn('shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold', SOURCE_BADGE_STYLE[r.type] ?? 'bg-elevated text-muted')}>
                    {TYPE_LABEL[r.type]}
                  </span>
                  {/* 个股类型: 直接显示可点击的代码+名称; 其他类型显示规则名 */}
                  {r.scope === 'symbols' && r.symbols.length > 0 ? (
                    <button
                      onClick={() => setPreviewSymbol(r.symbols[0])}
                      className="inline-flex items-center gap-1 min-w-0 hover:bg-elevated/50 rounded px-0.5 transition-colors cursor-pointer"
                      title={`查看 ${r.symbols[0]} 日K`}
                    >
                      <span className="font-mono text-xs font-medium text-foreground hover:text-accent">{r.symbols[0]}</span>
                      {symbolNames[r.symbols[0]] && <span className="text-xs text-secondary truncate">{symbolNames[r.symbols[0]]}</span>}
                    </button>
                  ) : (
                    <h3 className={cn('text-xs font-medium truncate', r.enabled ? 'text-foreground' : 'text-muted')}>{displayName}</h3>
                  )}
                  {!r.enabled && <span className="shrink-0 text-[9px] text-secondary">· 停用</span>}
                </div>
                <div className="flex items-center gap-0.5 shrink-0">
                  <button
                    onClick={() => toggleEnabled(r)}
                    title={r.enabled ? '停用' : '启用'}
                    className={cn(
                      'p-1 rounded-md transition-all cursor-pointer',
                      r.enabled ? 'text-accent hover:bg-accent/10' : 'text-muted hover:bg-elevated hover:text-accent',
                    )}
                  >
                    <Zap className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => onEdit(r)}
                    className="p-1 rounded-md text-secondary transition-all hover:bg-accent/10 hover:text-accent cursor-pointer"
                    title="编辑"
                  >
                    <Settings2 className="h-3.5 w-3.5" />
                  </button>
                  {confirmId === r.id ? (
                    <button
                      onClick={() => handleClickDelete(r.id)}
                      title="再次点击确认删除"
                      className="inline-flex items-center gap-1 rounded-md bg-danger/15 px-1.5 py-0.5 text-[9px] font-medium text-danger border border-danger/30 animate-pulse cursor-pointer"
                    >
                      <Trash2 className="h-2.5 w-2.5" />确认
                    </button>
                  ) : (
                    <button
                      onClick={() => handleClickDelete(r.id)}
                      disabled={del.isPending}
                      className="p-1 rounded-md text-secondary transition-all hover:bg-danger/10 hover:text-danger cursor-pointer"
                      title="删除"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>

              {/* 第二行: 策略类型显示选股池变更监控 */}
              {r.type === 'strategy' && r.strategy_id ? (
                <div className="mt-0.5 flex items-center gap-2 pl-0.5">
                  <span className="text-[9px] text-secondary">选股池变更监控</span>
                </div>
              ) : r.conditions.length > 0 && (
                <div className="mt-0.5 flex items-center gap-1 pl-0.5">
                  <span className="text-[9px] text-secondary shrink-0">条件</span>
                  <span className="min-w-0 flex flex-wrap items-center gap-x-1 gap-y-0.5 text-[9px]">
                    {r.conditions.slice(0, 3).map((c, i) => (
                      <span key={i} className="inline-flex items-center gap-0.5">
                        {i > 0 && <span className="text-secondary">{r.logic === 'and' ? '且' : '或'}</span>}
                        {c.op === 'truth' ? (
                          <span className="text-accent/80">{cnSignal(c.field)}</span>
                        ) : (
                          <span className="text-foreground/80 font-mono">{cnSignal(c.field)}{c.op}{c.value}</span>
                        )}
                      </span>
                    ))}
                    {r.conditions.length > 3 && <span className="text-secondary">+{r.conditions.length - 3}</span>}
                  </span>
                </div>
              )}
            </motion.div>
          )
        })
      )}

      <StockPreviewDialog
        symbol={previewSymbol}
        name={previewSymbol ? symbolNames[previewSymbol] : undefined}
        onClose={() => setPreviewSymbol(null)}
      />
    </div>
  )
}

// ── 规则编辑对话框 ────────────────────────────────────
function RuleEditorDialog({ open, rule, onClose }: { open: boolean; rule: MonitorRule | null; onClose: () => void }) {
  if (!open) return null
  return <Modal onClose={onClose} ariaLabel="监控规则" panelClassName="w-[calc(100vw-32px)] max-w-2xl max-h-[90vh] overflow-auto rounded-card border border-border bg-surface shadow-xl"><RuleEditor rule={rule} onClose={onClose} onSaved={onClose} /></Modal>
}

// ── 确认对话框 ────────────────────────────────────────
function ConfirmDialog({ open, title, message, confirmText, danger, pending, onCancel, onConfirm }: {
  open: boolean
  title: string
  message: string
  confirmText?: string
  danger?: boolean
  pending?: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  if (!open) return null
  return <Modal onClose={onCancel} ariaLabel={title} panelClassName="w-[calc(100vw-32px)] max-w-sm rounded-card border border-border bg-surface p-5 shadow-xl"><h3 className="text-sm font-medium text-foreground">{title}</h3><p className="mt-1.5 text-xs text-muted">{message}</p><div className="mt-4 flex justify-end gap-2"><button onClick={onCancel} className="px-3 py-1.5 rounded-btn bg-elevated text-secondary text-xs">取消</button><button onClick={onConfirm} disabled={pending} className={cn('px-3 py-1.5 rounded-btn text-xs font-medium disabled:opacity-50', danger ? 'bg-danger text-base' : 'bg-accent text-base')}>{confirmText ?? '确定'}</button></div></Modal>
}
