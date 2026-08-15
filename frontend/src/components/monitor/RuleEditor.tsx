import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Save, X, Plus, Search, Building2, ChartNoAxesCombined, Check, Tags } from 'lucide-react'
import { api, genRuleId, type MonitorRule, type MonitorCondition, type SectorKind, type SectorMonitorTarget } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { SignalPicker } from '@/components/screener/SignalPicker'
import { usePreferences } from '@/lib/useSharedQueries'

interface Props {
  /** 编辑现有规则;null=新建 */
  rule: MonitorRule | null
  /** 新建时的预填值 (如个股弹窗传入 symbol/scope) */
  preset?: Partial<MonitorRule>
  /** 极简模式: 个股场景, 隐藏 type/scope/阈值等, 只显示信号点选 */
  simple?: boolean
  onClose: () => void
  onSaved?: () => void
}

const TYPE_DEFAULT_NAME: Record<string, string> = {
  signal: '个股信号监控', price: '价格监控', market: '市场异动监控', strategy: '策略监控', position: '持仓监控', sector: '板块监控',
  // 盘前异动 (preopen): 类型下拉由 /options types 驱动自动出现, 此处只供空名默认
  preopen: '盘前异动',
}

// 板块监控对象分类 (type=sector): 与后端 SECTOR_KINDS / SectorMonitorService 对齐。
const SECTOR_KIND_OPTIONS: Array<{ key: SectorKind; label: string; icon: typeof ChartNoAxesCombined }> = [
  { key: 'index', label: '大盘指数', icon: ChartNoAxesCombined },
  { key: 'concept', label: '概念题材', icon: Tags },
  { key: 'industry', label: '行业板块', icon: Building2 },
]

// 告警投递渠道白名单 — 与后端 monitor_rules.DELIVERY_CHANNELS 对齐。
// 旧规则里已下线的 wecom 渠道在装载草稿时剥离, 避免出现"看不见也取消不掉"的隐形渠道。
const RULE_DELIVERY_CHANNELS = ['feishu', 'telegram']

const emptyRule = (preset?: Partial<MonitorRule>): MonitorRule => ({
  id: genRuleId(),
  name: '',
  enabled: true,
  type: 'signal',
  asset_type: 'stock',
  scope: 'symbols',
  symbols: [],
  sector: null,
  sector_kind: 'index',
  sector_targets: [],
  sector_trigger: 'change_pct',
  threshold_pct: 1,
  window_minutes: 5,
  strategy_id: null,
  direction: 'entry',
  conditions: [],
  logic: 'or',
  cooldown_seconds: 3600,
  severity: 'info',
  message: '',
  ...preset,
})

export function RuleEditor({ rule, preset, simple, onClose, onSaved }: Props) {
  const qc = useQueryClient()
  const options = useQuery({ queryKey: QK.monitorRuleOptions, queryFn: api.monitorRuleOptions })
  const { data: prefs } = usePreferences()
  const feishuConfigured = !!(prefs?.feishu_webhook_url)
  // 投递适配器 token/chat_id 缺一不可, 只配一半仍会被跳过 — 就绪判定必须两者同时存在。
  const telegramConfigured = !!(prefs?.telegram_bot_token && prefs?.telegram_chat_id)
  const [editing] = useState(!!rule)
  // 新建规则: 预填全局「默认推送渠道」(多选数组), preset 显式指定时以 preset 为准。
  // 编辑规则: 沿用规则自身配置, 仅做兼容规范化 (剥离下线渠道、持仓 ID 统一为数字)。
  const [draft, setDraft] = useState<MonitorRule>(
    rule
      ? {
          ...rule,
          conditions: rule.conditions.map(c => ({ ...c })),
          sector_targets: rule.sector_targets?.map(target => ({ ...target })) ?? [],
          webhook_channels: (rule.webhook_channels ?? []).filter(c => RULE_DELIVERY_CHANNELS.includes(c)),
          // 后端接受 str|int 持仓 ID; 统一为数字, 保证与持仓列表的勾选匹配、避免混型重复。
          position_ids: (rule.position_ids ?? []).map(Number),
        }
      : {
          ...emptyRule(preset),
          webhook_channels: (preset?.webhook_channels ?? prefs?.webhook_default_channels ?? []).filter(c => RULE_DELIVERY_CHANNELS.includes(c)),
        },
  )
  const holdings = useQuery({
    queryKey: QK.portfolioHoldings(),
    queryFn: () => api.portfolioHoldings(),
    enabled: draft.type === 'position',
  })
  const accounts = useQuery({
    queryKey: QK.portfolioAccounts(),
    queryFn: () => api.portfolioAccounts(),
    enabled: draft.type === 'position',
  })
  const accountNames = new Map((accounts.data?.accounts ?? []).map(account => [account.id, account.name]))
  // 规则引用、但当前持仓列表中不存在的持仓 (通常已归档/删除): 明确显示并允许一键移除,
  // 避免计数包含"幽灵持仓"、用户却无处取消勾选。
  const holdingIds = new Set((holdings.data?.positions ?? []).map(position => position.id))
  const unavailablePositionIds = holdings.data ? (draft.position_ids ?? []).map(Number).filter(id => !holdingIds.has(id)) : []
  const assetType = draft.asset_type ?? 'stock'
  // 策略列表跟随资产类型: ETF 只列技术类策略。
  const strategies = useQuery({
    queryKey: QK.screenerStrategies(assetType),
    queryFn: () => api.screenerStrategies(assetType),
  })
  const [error, setError] = useState('')
  const [symbolQuery, setSymbolQuery] = useState('')
  const [sectorQuery, setSectorQuery] = useState('')
  const [industryLevel, setIndustryLevel] = useState<1 | 2 | 3>(() => {
    const level = rule?.sector_targets?.[0]?.level
    return level === 1 || level === 3 ? level : 2
  })
  // ETF 规则时标的搜索一并搜出 ETF。
  const symbolAssetTypes = assetType === 'etf' ? 'stock,etf' : 'stock'
  const symbolSearch = useQuery({
    queryKey: QK.instrumentSearch(symbolQuery, symbolAssetTypes),
    queryFn: () => api.instrumentSearch(symbolQuery, 20, symbolAssetTypes),
    enabled: symbolQuery.length > 0,
  })

  const save = useMutation({
    mutationFn: () => {
      const d = { ...draft }
      // name 为空时用默认名
      if (!d.name.trim()) {
        const base = TYPE_DEFAULT_NAME[d.type] ?? '监控规则'
        d.name = d.type === 'sector' && d.sector_targets?.length
          ? `${base} · ${d.sector_targets[0].name}${d.sector_targets.length > 1 ? ` 等${d.sector_targets.length}个` : ''}`
          : d.scope === 'symbols' && d.symbols.length > 0
            ? `${base} · ${d.symbols[0]}${d.symbols.length > 1 ? ` 等${d.symbols.length}只` : ''}`
            : base
      }
      if (d.type === 'strategy') {
        if (!d.strategy_id) throw new Error('策略监控必须选择一个策略')
      } else if (d.type === 'sector') {
        // 板块规则作用域恒为全市场, 由 sector_targets 圈定对象; 清空 conditions。
        d.scope = 'all'
        d.symbols = []
        d.conditions = []
        if (!d.sector_targets?.length) throw new Error('请选择至少一个监控对象')
        if ((d.threshold_pct ?? 0) <= 0 || (d.threshold_pct ?? 0) > 20) throw new Error('阈值必须大于 0 且不超过 20%')
      } else {
        if (d.conditions.length === 0) throw new Error('至少选择一个触发条件')
        for (const c of d.conditions) {
          if (!c.field || !c.op) throw new Error('条件填写不完整')
          if (c.op !== 'truth' && (c.value === null || c.value === undefined)) throw new Error('阈值条件需要数值')
        }
      }
      if (d.type !== 'sector' && d.scope === 'symbols' && d.symbols.length === 0) throw new Error('请选择至少一只股票')
      if (d.scope === 'positions' && !(d.position_ids?.length)) throw new Error('请选择至少一笔持仓')
      return api.monitorRuleSave(d)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.monitorRules })
      onSaved?.()
      onClose()
    },
    onError: err => setError(String((err as any)?.message ?? err)),
  })
  const changeType = (type: MonitorRule['type']) => {
    setDraft(d => type === 'position'
      ? { ...d, type, scope: 'positions', symbols: [] }
      : type === 'sector'
        ? { ...d, type, scope: 'all', symbols: [], conditions: [], position_ids: [] }
        : { ...d, type, scope: d.scope === 'positions' ? 'symbols' : d.scope, position_ids: d.scope === 'positions' ? [] : d.position_ids },
    )
  }

  const selectSectorKind = (kind: SectorKind) => {
    setDraft(d => ({ ...d, sector_kind: kind, sector_targets: [] }))
    setSectorQuery('')
  }

  const toggleSectorTarget = (target: SectorMonitorTarget) => {
    setDraft(d => {
      const current = d.sector_targets ?? []
      if (current.some(item => item.key === target.key)) {
        return { ...d, sector_targets: current.filter(item => item.key !== target.key) }
      }
      if (current.length >= 20) return d
      return { ...d, sector_targets: [...current, target] }
    })
  }

  const togglePosition = (positionId: number) => setDraft(d => {
    const selected = d.position_ids ?? []
    return { ...d, position_ids: selected.includes(positionId) ? selected.filter(id => id !== positionId) : [...selected, positionId] }
  })

  // 条件编辑
  const updateCond = (idx: number, patch: Partial<MonitorCondition>) =>
    setDraft(d => ({ ...d, conditions: d.conditions.map((c, i) => i === idx ? { ...c, ...patch } : c) }))
  const addCond = (op: 'truth' | 'threshold') =>
    setDraft(d => ({
      ...d,
      conditions: [...d.conditions, op === 'truth'
        ? { field: 'signal_volume_surge', op: 'truth' }
        // simple 模式(个股弹窗)默认现价; 完整模式默认 RSI 超卖;
        // preopen 默认 open_gap (竞价白名单字段 — 否则保存必被后端白名单拒绝)
        : { field: draft.type === 'preopen' ? 'open_gap' : (simple ? 'close' : 'rsi_14'), op: '<', value: simple ? 0 : 30 }],
    }))
  const removeCond = (idx: number) =>
    setDraft(d => ({ ...d, conditions: d.conditions.filter((_, i) => i !== idx) }))

  const addSymbol = (sym: string) => {
    if (!draft.symbols.includes(sym)) {
      setDraft(d => ({ ...d, symbols: [...d.symbols, sym] }))
    }
    setSymbolQuery('')
  }

  // 勾选/取消勾选某个推送渠道 (飞书 / 企业微信 各自独立)
  const toggleChannel = (ch: string) =>
    setDraft(d => {
      const cur = d.webhook_channels ?? []
      return { ...d, webhook_channels: cur.includes(ch) ? cur.filter(c => c !== ch) : [...cur, ch] }
    })

  // preopen 只能用竞价白名单字段 (后端 PREOPEN_ALLOWED_FIELDS — 禁 EOD 列);
  // 旧 /options 缺 preopen_threshold_fields 键 → 回退空数组零崩溃
  const thresholdFields = draft.type === 'preopen'
    ? (options.data?.preopen_threshold_fields ?? [])
    : (options.data?.threshold_fields ?? [])
  const operators = options.data?.operators ?? ['>', '>=', '<', '<=', '==', '!=']
  const selectedSignals = draft.conditions.filter(c => c.op === 'truth').map(c => c.field)
  const thresholdConds = draft.conditions.filter(c => c.op !== 'truth')

  const onSignalPickerChange = (next: string[]) => {
    const nonTruthConds = draft.conditions.filter(c => c.op !== 'truth')
    const truthConds: MonitorCondition[] = next.map(field => ({ field, op: 'truth' }))
    setDraft(d => ({ ...d, conditions: [...nonTruthConds, ...truthConds] }))
  }

  // ── 极简模式: 只显示信号点选 + 可选描述 ──
  if (simple) {
    return (
      <div className="rounded-card border border-border bg-surface p-5 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-medium text-foreground">{editing ? '编辑监控' : '加入监控'}</h3>
          <button onClick={onClose} className="rounded p-1 text-muted hover:bg-elevated hover:text-foreground cursor-pointer max-md:min-h-11 max-md:min-w-11">
            <X className="h-4 w-4" />
          </button>
        </div>

        {draft.symbols.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {draft.symbols.map(s => (
              <span key={s} className="rounded bg-elevated px-1.5 py-0.5 text-[10px] text-secondary font-mono">{s}</span>
            ))}
          </div>
        )}

        <div>
          <div className="mb-1.5 text-[11px] text-muted">选择触发信号 (任一命中即报警)</div>
          <SignalPicker signals={selectedSignals} onChange={onSignalPickerChange} kind="entry" />
        </div>

        {/* 价位条件 (阈值) — 与信号共存, 可选添加 */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-muted">价位条件 (可选)</span>
            <button onClick={() => addCond('threshold')} className="inline-flex items-center gap-1 text-[11px] text-accent hover:text-accent/80 cursor-pointer">
              <Plus className="h-3 w-3" />添加价位
            </button>
          </div>
          {thresholdConds.length > 0 && (
            <div className="space-y-1.5">
              {thresholdConds.map((c, i) => {
                const realIdx = draft.conditions.indexOf(c)
                return (
                  <div key={i} className="flex items-center gap-1.5">
                    <span className="text-[10px] text-muted/60 w-6 text-right shrink-0">{i === 0 && selectedSignals.length === 0 ? '当' : draft.logic === 'and' ? '且' : '或'}</span>
                    <select value={c.field} onChange={e => updateCond(realIdx, { field: e.target.value })} aria-label={`条件 ${i + 1} 字段`} className="flex-1 h-7 px-1.5 rounded bg-base border border-border text-[11px] text-foreground focus:border-accent/50 focus-visible:ring-2 focus-visible:ring-accent/60">
                      {thresholdFields.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}
                    </select>
                    <select value={c.op} onChange={e => updateCond(realIdx, { op: e.target.value })} aria-label={`条件 ${i + 1} 操作符`} className="w-12 h-7 px-1 rounded bg-base border border-border text-[11px] font-mono text-foreground text-center focus:border-accent/50 focus-visible:ring-2 focus-visible:ring-accent/60">
                      {operators.map(op => <option key={op} value={op}>{op}</option>)}
                    </select>
                    <input type="number" value={c.value ?? 0} onChange={e => updateCond(realIdx, { value: parseFloat(e.target.value) })} step="any" aria-label={`条件 ${i + 1} 阈值`} className="w-24 h-7 px-1.5 rounded bg-base border border-border text-[11px] font-mono text-foreground text-center focus:border-accent/50 focus-visible:ring-2 focus-visible:ring-accent/60" />
                    <button onClick={() => removeCond(realIdx)} aria-label={`删除条件 ${i + 1}`} className="p-1 rounded text-muted hover:text-danger hover:bg-danger/10 cursor-pointer">
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <label className="space-y-1.5">
          <span className="text-[11px] text-muted">备注 (可选)</span>
          <input value={draft.message} onChange={e => setDraft(d => ({ ...d, message: e.target.value }))} placeholder="给这条监控加个备注" className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground" />
        </label>

        {error && <div className="rounded-btn border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">{error}</div>}

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-1.5 rounded-btn bg-elevated text-secondary text-xs cursor-pointer">取消</button>
          <button onClick={() => save.mutate()} disabled={save.isPending} className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-btn bg-accent text-base text-xs font-medium disabled:opacity-50 cursor-pointer">
            <Save className="h-3.5 w-3.5" />加入监控
          </button>
        </div>
      </div>
    )
  }

  // ── 完整模式: 监控页新建/编辑 ──
  return (
    <div className="rounded-card border border-border bg-surface p-5 space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-medium text-foreground">{editing ? '编辑监控规则' : '新建监控规则'}</h3>
          <p className="mt-1 text-[11px] text-muted">规则标识自动生成,描述为可选。</p>
        </div>
        <button onClick={onClose} className="rounded p-1 text-muted hover:bg-elevated hover:text-foreground cursor-pointer max-md:min-h-11 max-md:min-w-11">
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* 资产类型: 股票 / ETF (个股极简模式不显示; 板块规则无资产维度) */}
      {!simple && draft.type !== 'sector' && (
        <div className="space-y-1.5">
          <span className="text-[11px] text-muted">资产类型</span>
          <div className="inline-flex h-9 rounded-btn border border-border overflow-hidden">
            {(['stock', 'etf'] as const).map(t => (
              <button
                key={t}
                type="button"
                onClick={() => setDraft(d => ({ ...d, asset_type: t, strategy_id: null, symbols: [] }))}
                className={`h-full px-4 text-xs font-medium transition-colors cursor-pointer
                  ${assetType === t ? 'bg-accent/10 text-accent' : 'text-muted hover:text-foreground'}`}
              >
                {t === 'stock' ? '股票' : 'ETF'}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 描述 (可选) + 类型 */}
      {/* 基本信息与监控范围 */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <label className="space-y-1.5 md:col-span-2">
          <span className="text-[11px] text-muted">描述 (可选)</span>
          <input value={draft.name} onChange={e => setDraft(d => ({ ...d, name: e.target.value }))} placeholder="留空用默认名称" className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground" />
        </label>
        <label className="space-y-1.5">
          <span className="text-[11px] text-muted">监控类型</span>
          <select value={draft.type} onChange={e => changeType(e.target.value as MonitorRule['type'])} className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground">
            {(options.data?.types ?? []).map(t => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
        </label>
      </div>

      {draft.type === 'position' ? (
        <fieldset className="space-y-2">
          <legend className="text-[11px] text-muted">监控范围 · 持仓</legend>
          <p className="text-[10px] text-muted">选择需要监控的持仓；每项明确显示标的与账户。</p>
          <div className="max-h-44 space-y-1 overflow-auto rounded-btn border border-border bg-base p-2" aria-describedby="position-selection-help">
            {holdings.isLoading ? <span className="block px-2 py-2 text-xs text-muted">正在加载持仓…</span> : (holdings.data?.positions ?? []).length === 0 ? <span className="block px-2 py-2 text-xs text-warning">暂无可选择持仓，请先添加持仓。</span> : (holdings.data?.positions ?? []).map(position => (
              <label key={position.id} className="flex min-h-9 cursor-pointer items-center gap-2 rounded px-2 text-xs hover:bg-elevated">
                <input type="checkbox" checked={(draft.position_ids ?? []).includes(position.id)} onChange={() => togglePosition(position.id)} className="h-4 w-4 accent-accent" />
                <span className="font-mono text-foreground">{position.instrument_symbol}</span>
                <span className="min-w-0 truncate text-secondary">{accountNames.get(position.account_id) ?? `账户 ${position.account_id}`}</span>
              </label>
            ))}
          </div>
          <p id="position-selection-help" className="text-[10px] text-muted">已选择 {(draft.position_ids ?? []).length} 笔持仓。</p>
          {unavailablePositionIds.length > 0 && (
            <p className="text-[10px] text-warning">
              {unavailablePositionIds.length} 笔已选持仓不在当前列表 (可能已归档或删除)，保存后仍会保留。
              <button
                type="button"
                onClick={() => setDraft(d => ({ ...d, position_ids: (d.position_ids ?? []).map(Number).filter(id => holdingIds.has(id)) }))}
                className="ml-1 text-accent hover:text-accent/80"
              >
                移除失效持仓
              </button>
            </p>
          )}
        </fieldset>
      ) : draft.type === 'sector' ? (
        <div className="space-y-4 border-t border-border/60 pt-4">
          <div className="space-y-1.5">
            <span className="text-[11px] text-muted">板块分类</span>
            <div className="grid grid-cols-3 gap-1.5">
              {SECTOR_KIND_OPTIONS.map(option => {
                const Icon = option.icon
                const active = (draft.sector_kind ?? 'index') === option.key
                return (
                  <button
                    key={option.key}
                    type="button"
                    aria-pressed={active}
                    onClick={() => selectSectorKind(option.key)}
                    className={`inline-flex h-9 items-center justify-center gap-1.5 rounded-btn border text-xs font-medium transition-colors cursor-pointer ${
                      active ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border bg-base text-secondary hover:border-accent/25'
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {option.label}
                  </button>
                )
              })}
            </div>
          </div>

          {(draft.sector_kind ?? 'index') === 'industry' && (
            <div className="space-y-1.5">
              <span className="text-[11px] text-muted">行业层级</span>
              <div className="inline-flex h-8 overflow-hidden rounded-btn border border-border bg-base">
                {([1, 2, 3] as const).map(level => (
                  <button
                    key={level}
                    type="button"
                    aria-pressed={industryLevel === level}
                    onClick={() => {
                      setIndustryLevel(level)
                      setDraft(d => ({ ...d, sector_targets: [] }))
                    }}
                    className={`px-3 text-[11px] transition-colors cursor-pointer ${
                      industryLevel === level ? 'bg-accent/10 text-accent' : 'text-muted hover:text-foreground'
                    }`}
                  >
                    {level}级
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[11px] text-muted">监控对象</span>
              <span className="text-[10px] font-mono text-muted">{draft.sector_targets?.length ?? 0}/20</span>
            </div>
            {(draft.sector_targets?.length ?? 0) > 0 && (
              <div className="flex flex-wrap gap-1">
                {draft.sector_targets?.map(target => (
                  <span key={target.key} className="inline-flex items-center gap-1 rounded bg-accent/8 px-1.5 py-1 text-[10px] text-accent">
                    {target.name}
                    <button type="button" onClick={() => toggleSectorTarget(target)} title="移除" className="text-accent/60 hover:text-danger cursor-pointer">
                      <X className="h-2.5 w-2.5" />
                    </button>
                  </span>
                ))}
              </div>
            )}
            <label className="relative block">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted" />
              <input
                value={sectorQuery}
                onChange={event => setSectorQuery(event.target.value)}
                placeholder={`搜索${SECTOR_KIND_OPTIONS.find(option => option.key === draft.sector_kind)?.label ?? '板块'}`}
                className="h-9 w-full rounded-btn border border-border bg-base pl-8 pr-3 text-xs text-foreground placeholder:text-muted/50 focus:border-accent/50 focus:outline-none"
              />
            </label>
            <div className="grid max-h-48 grid-cols-1 gap-1 overflow-y-auto pr-1 sm:grid-cols-2">
              {(() => {
                const sectorTargets = options.data?.sector_targets?.[draft.sector_kind ?? 'index'] ?? []
                const visible = sectorTargets.filter(target => {
                  if ((draft.sector_kind ?? 'index') === 'industry' && target.level !== industryLevel) return false
                  const query = sectorQuery.trim().toLowerCase()
                  if (!query) return true
                  return `${target.name} ${target.symbol ?? ''} ${target.value ?? ''}`.toLowerCase().includes(query)
                }).slice(0, 100)
                if (visible.length === 0) {
                  return (
                    <div className="col-span-full rounded-btn border border-dashed border-border py-6 text-center text-xs text-muted">
                      {options.isLoading ? '正在加载...' : '没有可用的监控对象'}
                    </div>
                  )
                }
                return visible.map(target => {
                  const selected = draft.sector_targets?.some(item => item.key === target.key) ?? false
                  const unavailable = !target.available || (target.kind !== 'index' && target.member_count < 5)
                  const targetLabel = target.kind === 'industry'
                    ? (target.value ?? target.name).replaceAll('-', ' / ')
                    : target.name
                  return (
                    <button
                      key={target.key}
                      type="button"
                      disabled={unavailable}
                      aria-pressed={selected}
                      onClick={() => toggleSectorTarget(target)}
                      title={!target.available ? '请先在实时监控设置中加入该指数' : target.member_count < 5 ? '有效成分少于 5 只' : targetLabel}
                      className={`flex h-9 min-w-0 items-center gap-2 rounded-btn border px-2.5 text-left transition-colors ${
                        unavailable
                          ? 'cursor-not-allowed border-border/40 bg-base/40 text-muted/40'
                          : selected
                            ? 'cursor-pointer border-accent/40 bg-accent/10 text-accent'
                            : 'cursor-pointer border-border bg-base text-secondary hover:border-accent/25 hover:text-foreground'
                      }`}
                    >
                      <span className="min-w-0 flex-1 truncate text-[11px]">{targetLabel}</span>
                      {target.symbol && <span className="shrink-0 font-mono text-[9px] opacity-60">{target.symbol}</span>}
                      {target.kind !== 'index' && <span className="shrink-0 font-mono text-[9px] opacity-60">{target.member_count}</span>}
                      <span className={`grid h-4 w-4 shrink-0 place-items-center rounded-full border ${selected ? 'border-accent bg-accent text-white' : 'border-border text-transparent'}`}>
                        <Check className="h-2.5 w-2.5" />
                      </span>
                    </button>
                  )
                })
              })()}
            </div>
          </div>

          <div className="grid gap-3 border-t border-border/60 pt-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <span className="text-[11px] text-muted">触发方式</span>
              <div className="grid h-9 grid-cols-2 overflow-hidden rounded-btn border border-border bg-base">
                {([
                  ['change_pct', '涨跌幅到达'],
                  ['momentum', '快速异动'],
                ] as const).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={(draft.sector_trigger ?? 'change_pct') === key}
                    onClick={() => setDraft(d => ({ ...d, sector_trigger: key }))}
                    className={`text-[11px] font-medium transition-colors cursor-pointer ${
                      (draft.sector_trigger ?? 'change_pct') === key ? 'bg-accent/10 text-accent' : 'text-muted hover:text-foreground'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-1.5">
              <span className="text-[11px] text-muted">方向</span>
              <div className="grid h-9 grid-cols-2 overflow-hidden rounded-btn border border-border bg-base">
                {([
                  ['up', draft.sector_trigger === 'momentum' ? '快速上涨' : '上涨'],
                  ['down', draft.sector_trigger === 'momentum' ? '快速下跌' : '下跌'],
                ] as const).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    aria-pressed={draft.direction === key}
                    onClick={() => setDraft(d => ({ ...d, direction: key }))}
                    className={`text-[11px] font-medium transition-colors cursor-pointer ${
                      draft.direction === key ? 'bg-accent/10 text-accent' : 'text-muted hover:text-foreground'
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            {draft.sector_trigger === 'momentum' && (
              <label className="space-y-1.5">
                <span className="text-[11px] text-muted">统计窗口</span>
                <select
                  value={draft.window_minutes ?? 5}
                  onChange={event => setDraft(d => ({ ...d, window_minutes: Number(event.target.value) as MonitorRule['window_minutes'] }))}
                  className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground"
                >
                  {[1, 3, 5, 10, 15].map(window => <option key={window} value={window}>{window} 分钟</option>)}
                </select>
              </label>
            )}
            <label className="space-y-1.5">
              <span className="text-[11px] text-muted">{draft.sector_trigger === 'momentum' ? '窗口变化阈值' : '板块涨跌幅阈值'}</span>
              <span className="relative block">
                <input
                  type="number"
                  min="0.01"
                  max="20"
                  step="0.1"
                  value={draft.threshold_pct ?? 1}
                  onChange={event => setDraft(d => ({ ...d, threshold_pct: Number(event.target.value) }))}
                  className="h-9 w-full rounded-btn border border-border bg-base pl-3 pr-8 text-xs font-mono text-foreground"
                />
                <span className="absolute right-3 top-2.5 text-xs text-muted">%</span>
              </span>
            </label>
          </div>
          {(draft.sector_kind ?? 'index') !== 'index' && (
            <div className="flex flex-wrap gap-1.5 text-[9px] text-muted">
              <span className="rounded bg-elevated px-1.5 py-0.5">等权平均</span>
              <span className="rounded bg-elevated px-1.5 py-0.5">行情覆盖 ≥ 80%</span>
              <span className="rounded bg-elevated px-1.5 py-0.5">有效成分 ≥ 5</span>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          <span className="text-[11px] text-muted">作用范围</span>
          <div className="flex flex-wrap items-center gap-2">
            <select value={draft.scope} onChange={e => setDraft(d => ({ ...d, scope: e.target.value as MonitorRule['scope'] }))} className="h-9 w-32 rounded-btn border border-border bg-base px-3 text-xs text-foreground">
              {/* positions 有专属选择器; sector 后端 fail-closed (板块 JOIN 未实现), 均不下拉可选 */}
              {(options.data?.scopes ?? []).filter(scope => scope.key !== 'positions' && scope.key !== 'sector').map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
            {draft.scope === 'symbols' && (
              <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
                {draft.symbols.map(sym => <span key={sym} className="inline-flex items-center gap-1 rounded bg-elevated px-1.5 py-0.5 text-[10px] text-secondary">{sym}<button type="button" onClick={() => setDraft(d => ({ ...d, symbols: d.symbols.filter(s => s !== sym) }))} className="text-muted hover:text-danger"><X className="h-2.5 w-2.5" /></button></span>)}
                <div className="relative">
                  <input value={symbolQuery} onChange={e => setSymbolQuery(e.target.value)} placeholder="搜索股票..." aria-label="搜索股票" className="h-7 w-32 rounded border border-border bg-base pl-6 pr-2 text-[11px] text-foreground focus:border-accent/50 focus-visible:ring-2 focus-visible:ring-accent/60" />
                  <Search className="absolute left-1.5 top-1.5 h-3.5 w-3.5 text-muted" />
                  {symbolSearch.data && symbolSearch.data.results.length > 0 && <div className="absolute z-10 mt-1 max-h-48 w-48 overflow-auto rounded border border-border bg-surface shadow-lg">{symbolSearch.data.results.map(r => <button type="button" key={r.symbol} onClick={() => addSymbol(r.symbol)} className="block w-full px-2 py-1 text-left text-[11px] hover:bg-elevated"><span className="font-mono text-foreground/80">{r.symbol}</span><span className="ml-1 text-muted">{r.name}</span></button>)}</div>}
                </div>
              </div>
            )}
            {draft.scope === 'all' && <span className="text-[11px] text-muted">对全市场所有股票生效</span>}
          </div>
        </div>
      )}

      {/* 触发条件 (非 strategy / sector) */}
      {draft.type !== 'strategy' && draft.type !== 'sector' && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[11px] text-muted">触发条件</span>
            <div className="flex items-center gap-2">
              <select value={draft.logic} onChange={e => setDraft(d => ({ ...d, logic: e.target.value as MonitorRule['logic'] }))} aria-label="条件逻辑" className="h-7 rounded border border-border bg-base px-1.5 text-[11px] text-foreground">
                {(options.data?.logics ?? []).map(l => <option key={l.key} value={l.key}>{l.label}</option>)}
              </select>
              {/* preopen 帧无布尔信号列 (op=truth 后端拒绝) — 隐藏信号点选入口 */}
              {draft.type !== 'preopen' && (
                <button onClick={() => addCond('truth')} className="inline-flex items-center gap-1 text-[11px] text-accent hover:text-accent/80 cursor-pointer">
                  <Plus className="h-3 w-3" />信号条件
                </button>
              )}
              <button onClick={() => addCond('threshold')} className="inline-flex items-center gap-1 text-[11px] text-accent hover:text-accent/80 cursor-pointer">
                <Plus className="h-3 w-3" />阈值条件
              </button>
            </div>
          </div>

          {draft.type !== 'preopen' && (selectedSignals.length > 0 || (options.data?.builtin_signals ?? []).length > 0) ? (
            <div>
              <div className="mb-1.5 text-[10px] text-muted/70">信号条件 (点选)</div>
              <SignalPicker signals={selectedSignals} onChange={onSignalPickerChange} kind="entry" />
            </div>
          ) : null}

          {thresholdConds.length > 0 && (
            <div className="space-y-1.5">
              {thresholdConds.map((c, i) => {
                const realIdx = draft.conditions.indexOf(c)
                return (
                  <div key={i} className="flex items-center gap-1.5">
                    <span className="text-[10px] text-muted/60 w-6 text-right shrink-0">{i === 0 && selectedSignals.length === 0 ? '当' : draft.logic === 'and' ? '且' : '或'}</span>
                    <select value={c.field} onChange={e => updateCond(realIdx, { field: e.target.value })} aria-label={`条件 ${i + 1} 字段`} className="w-32 h-7 px-1.5 rounded bg-base border border-border text-[11px] text-foreground focus:border-accent/50 focus-visible:ring-2 focus-visible:ring-accent/60">
                      {thresholdFields.map(f => <option key={f.key} value={f.key}>{f.label}</option>)}
                    </select>
                    <select value={c.op} onChange={e => updateCond(realIdx, { op: e.target.value })} aria-label={`条件 ${i + 1} 操作符`} className="w-12 h-7 px-1 rounded bg-base border border-border text-[11px] font-mono text-foreground text-center focus:border-accent/50 focus-visible:ring-2 focus-visible:ring-accent/60">
                      {operators.map(op => <option key={op} value={op}>{op}</option>)}
                    </select>
                    <input type="number" value={c.value ?? 0} onChange={e => updateCond(realIdx, { value: parseFloat(e.target.value) })} step="any" aria-label={`条件 ${i + 1} 阈值`} className="w-24 h-7 px-1.5 rounded bg-base border border-border text-[11px] font-mono text-foreground text-center focus:border-accent/50 focus-visible:ring-2 focus-visible:ring-accent/60" />
                    <button onClick={() => removeCond(realIdx)} aria-label={`删除条件 ${i + 1}`} className="p-1 rounded text-muted hover:text-danger hover:bg-danger/10 cursor-pointer">
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                )
              })}
            </div>
          )}

          {draft.conditions.length === 0 && (
            <div className="rounded border border-dashed border-border px-3 py-4 text-center text-[11px] text-muted">
              {draft.type === 'preopen' ? '点击上方「阈值条件」添加触发规则' : '点击上方「信号条件」或「阈值条件」添加触发规则'}
            </div>
          )}
        </div>
      )}

      {/* strategy 类型: 选策略 + 方向 */}
      {draft.type === 'strategy' && (
        <div className="space-y-2">
          <span className="text-[11px] text-muted">策略与方向</span>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            <label className="md:col-span-2 space-y-1.5">
              <span className="text-[10px] text-muted/70">选择策略</span>
              <select
                value={draft.strategy_id ?? ''}
                onChange={e => setDraft(d => ({ ...d, strategy_id: e.target.value || null }))}
                className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground"
              >
                <option value="">— 请选择 —</option>
                {(strategies.data?.presets ?? []).map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </label>
            <label className="space-y-1.5">
              <span className="text-[10px] text-muted/70">触发方向</span>
              <select
                value={draft.direction}
                onChange={e => setDraft(d => ({ ...d, direction: e.target.value as MonitorRule['direction'] }))}
                className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground"
              >
                {(options.data?.directions ?? []).map(d => <option key={d.key} value={d.key}>{d.label}</option>)}
              </select>
            </label>
          </div>
          <p className="text-[10px] leading-4 text-muted/70">
            策略监控自动评估策略的买卖信号。entry=买入信号,exit=卖出信号,both=两者都报。作用范围建议用「全市场」。
          </p>
        </div>
      )}

      {/* 通知与时间 */}
      <section className="space-y-3 rounded-btn border border-border/40 bg-base/40 p-3">
        <h3 className="text-[11px] font-medium text-foreground">通知与时间</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="space-y-1.5"><span className="text-[11px] text-muted">严重级别</span><select value={draft.severity} onChange={e => setDraft(d => ({ ...d, severity: e.target.value as MonitorRule['severity'] }))} className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground">{(options.data?.severities ?? []).map(s => <option key={s.key} value={s.key}>{s.label}</option>)}</select></label>
          <label className="space-y-1.5"><span className="text-[11px] text-muted">冷却期（秒）</span><input type="number" value={draft.cooldown_seconds} onChange={e => setDraft(d => ({ ...d, cooldown_seconds: parseInt(e.target.value) || 0 }))} min={0} className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground" /></label>
          <label className="space-y-1.5"><span className="text-[11px] text-muted">生效开始时间</span><input type="time" value={draft.active_time_start ?? ''} onChange={e => setDraft(d => ({ ...d, active_time_start: e.target.value || null, active_time_end: e.target.value ? (d.active_time_end ?? '23:59') : null }))} className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground" /></label>
          <label className="space-y-1.5"><span className="text-[11px] text-muted">生效结束时间</span><input type="time" value={draft.active_time_end ?? ''} onChange={e => setDraft(d => ({ ...d, active_time_end: e.target.value || null, active_time_start: e.target.value ? (d.active_time_start ?? '00:00') : null }))} className="h-9 w-full rounded-btn border border-border bg-base px-3 text-xs text-foreground" /></label>
        </div>
        <label className="flex cursor-pointer items-start gap-2 text-xs text-secondary"><input type="checkbox" checked={draft.bypass_quiet_period ?? false} onChange={e => setDraft(d => ({ ...d, bypass_quiet_period: e.target.checked }))} className="mt-0.5 h-4 w-4 accent-accent" /><span><span className="block text-foreground">高优先级可绕过静默时段</span><span className="mt-1 block text-[10px] text-muted">规则命中始终会保存；静默时段只影响外部投递。</span></span></label>
        <div className="space-y-2 border-t border-border/60 pt-3">
          <span className="text-[11px] text-muted">投递渠道</span>
          <label className="flex cursor-pointer items-center gap-2 text-xs"><input type="checkbox" checked={(draft.webhook_channels ?? []).includes('feishu')} onChange={() => toggleChannel('feishu')} className="h-4 w-4 accent-accent" /><span className="text-foreground">飞书</span><span className={`ml-auto text-[10px] ${feishuConfigured ? 'text-emerald-500' : 'text-warning'}`}>{feishuConfigured ? '已配置' : '未配置'}</span></label>
          <label className="flex cursor-pointer items-center gap-2 text-xs"><input type="checkbox" checked={(draft.webhook_channels ?? []).includes('telegram')} onChange={() => toggleChannel('telegram')} className="h-4 w-4 accent-accent" /><span className="text-foreground">Telegram</span><span className={`ml-auto text-[10px] ${telegramConfigured ? 'text-emerald-500' : 'text-warning'}`}>{telegramConfigured ? '已配置' : '未配置'}</span></label>
          {(draft.webhook_channels ?? []).some(channel => (channel === 'feishu' && !feishuConfigured) || (channel === 'telegram' && !telegramConfigured)) && <p className="text-[10px] text-warning">所选渠道尚未配置，<Link to="/settings?tab=monitoring" className="text-accent hover:text-accent/80">前往设置</Link></p>}
        </div>
      </section>
      {error && <div className="rounded-btn border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">{error}</div>}

      <div className="flex justify-end gap-2">
        <button onClick={onClose} className="px-4 py-1.5 rounded-btn bg-elevated text-secondary text-xs cursor-pointer">返回监控中心</button>
        <button onClick={() => save.mutate()} disabled={save.isPending} className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-btn bg-accent text-base text-xs font-medium disabled:opacity-50 cursor-pointer">
          <Save className="h-3.5 w-3.5" />{save.isPending ? '正在保存…' : '保存规则'}
        </button>
      </div>
    </div>
  )
}
