import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Clock3, Copy, ShieldAlert } from 'lucide-react'
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ApiRequestError } from '@/lib/api'
import {
  phase5Api,
  type ThesisCadence,
  type ThesisCondition,
  type ThesisConditionInput,
  type ThesisPending,
  type ThesisRevisionInput,
  type ThesisValuationAnchorInput,
  type ThesisVersion,
  type ThesisVersionInput,
} from '@/lib/phase5Api'
import { QK } from '@/lib/queryKeys'

const FOCUS = 'focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base'
const INPUT = `min-h-11 w-full rounded-input border border-border bg-base px-3 py-2 text-sm text-foreground ${FOCUS}`
const BUTTON = `inline-flex min-h-11 items-center justify-center rounded-btn px-3 text-sm ${FOCUS}`
const CADENCES: Array<{ value: ThesisCadence; label: string }> = [
  { value: 'daily', label: '每日' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
  { value: 'quarterly', label: '每季度' },
]
const CHECK_LABELS = {
  matched: '命中',
  not_matched: '未命中',
  insufficient_evidence: '证据不足',
  error: '检查错误',
} as const

type ReviewAction = 'confirm' | 'reject'
type LooseRecord = Record<string, unknown>

interface ThesisPanelProps {
  instrument: string
  title: string
}

interface AnchorDraft {
  method: string
  currency: string
  asOf: string
  low: string
  high: string
  assumption: string
  limitation: string
}

interface ConditionDraft {
  sourceKind: ThesisConditionInput['source_kind']
  field: string
  operator: ThesisConditionInput['operator']
  threshold: string
  unit: string
  lookbackDays: string
  cadence: ThesisCadence
  description: string
}

interface VersionDraft {
  coreJudgment: string
  rationale: string
  changeReason: string
  anchor: AnchorDraft
  conditions: ConditionDraft[]
}

function record(value: unknown): LooseRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as LooseRecord : {}
}

function text(value: unknown, fallback = '—'): string {
  return typeof value === 'string' && value.length > 0 ? value : fallback
}

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function dateTime(value: unknown): string {
  if (typeof value !== 'string' || !value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString('zh-CN', { hour12: false })
}

function errorReason(error: unknown): string {
  if (error instanceof ApiRequestError) {
    const detail = record(error.detail)
    return text(detail.reason, text(detail.message, error.message))
  }
  return error instanceof Error ? error.message : '服务暂不可用'
}

function displayTitle(title: string, instrument: string): string {
  const normalized = title.replace(/（([^）]+)）/, ' $1')
  return normalized.includes(instrument) ? normalized : `${normalized} ${instrument}`
}

function officialState(version: ThesisVersion | undefined): string {
  const source = record(version)
  return text(source.official_state, text(source.official_status, '未记录'))
}

function versionAssumptions(version: ThesisVersion): string[] {
  const first = version.anchors[0]
  if (!first) return []
  return (first.assumptions as unknown[]).map(item => typeof item === 'string' ? item : `${text(record(item).name, '假设')} ${record(item).value ?? ''} ${text(record(item).unit, '')}`.trim())
}

function conditionSchedule(condition: ThesisCondition): LooseRecord {
  const source = record(condition)
  return record(source.schedule ?? { next_due_at: source.next_due_at, active: true })
}

function draftFromVersion(version?: ThesisVersion): VersionDraft {
  const anchor = version?.anchors[0]
  const assumption = version ? versionAssumptions(version)[0] ?? '' : ''
  const conditions = version?.conditions.length ? version.conditions.map(item => {
    const source = record(item)
    const rawThreshold = source.threshold
    return {
      sourceKind: item.source_kind,
      field: item.field,
      operator: item.operator,
      threshold: Array.isArray(rawThreshold) ? rawThreshold.join(',') : String(rawThreshold ?? ''),
      unit: item.unit,
      lookbackDays: String(item.lookback_days ?? source.lookback ?? 1),
      cadence: item.cadence,
      description: item.description || text(source.name, item.field),
    }
  }) : [{ sourceKind: 'market', field: 'close', operator: 'lt', threshold: '', unit: 'CNY', lookbackDays: '20', cadence: 'weekly', description: '' } satisfies ConditionDraft]
  return {
    coreJudgment: version?.core_judgment ?? '',
    rationale: version?.rationale ?? '',
    changeReason: version ? '' : '建立首版研究账本',
    anchor: {
      method: anchor?.method ?? 'DCF',
      currency: anchor?.currency ?? 'CNY',
      asOf: anchor?.as_of ?? new Date().toISOString().slice(0, 10),
      low: anchor ? String(anchor.low) : '',
      high: anchor ? String(anchor.high) : '',
      assumption,
      limitation: anchor?.limitations[0] ?? '',
    },
    conditions,
  }
}

function toConditionInput(draft: ConditionDraft): ThesisConditionInput {
  const parts = draft.threshold.split(',').map(value => Number(value.trim()))
  return {
    source_kind: draft.sourceKind,
    field: draft.field.trim(),
    operator: draft.operator,
    threshold: draft.operator === 'between' ? [parts[0], parts[1]] : parts[0],
    unit: draft.unit.trim(),
    lookback_days: Number(draft.lookbackDays),
    cadence: draft.cadence,
    timezone: 'Asia/Shanghai',
    description: draft.description.trim(),
  }
}

function toAnchorInput(draft: AnchorDraft): ThesisValuationAnchorInput {
  return {
    method: draft.method.trim(),
    currency: draft.currency.trim(),
    as_of: draft.asOf,
    low: Number(draft.low),
    high: Number(draft.high),
    assumptions: [{ name: draft.assumption.trim(), value: 1, unit: 'reviewed' }],
    limitations: draft.limitation.trim() ? [draft.limitation.trim()] : [],
  }
}

export function ThesisPanel({ instrument, title }: ThesisPanelProps) {
  const queryClient = useQueryClient()
  const headingId = useId()
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null)
  const [checkConditionId, setCheckConditionId] = useState('all')
  const [editing, setEditing] = useState(false)
  const [reviewingDraft, setReviewingDraft] = useState(false)
  const [draft, setDraft] = useState<VersionDraft>(() => draftFromVersion())
  const [draftError, setDraftError] = useState<string | null>(null)
  const [creationConfirmOpen, setCreationConfirmOpen] = useState(false)
  const [reviewTarget, setReviewTarget] = useState<{ pending: ThesisPending; action: ReviewAction } | null>(null)
  const [rationale, setRationale] = useState('')
  const [conflict, setConflict] = useState(false)
  const lowRef = useRef<HTMLInputElement>(null)
  const firstFieldRef = useRef<HTMLTextAreaElement>(null)

  const capabilityQuery = useQuery({ queryKey: QK.capabilities, queryFn: phase5Api.capabilities, staleTime: 60_000 })
  const versionsQuery = useQuery({ queryKey: QK.thesis.versions(instrument), queryFn: () => phase5Api.thesisVersions(instrument), placeholderData: keepPreviousData })
  const checksQuery = useQuery({ queryKey: QK.thesis.checks(instrument), queryFn: () => phase5Api.thesisChecks(instrument), placeholderData: keepPreviousData })
  const pendingQuery = useQuery({ queryKey: QK.thesis.pending(instrument), queryFn: () => phase5Api.thesisPending(instrument), placeholderData: keepPreviousData })

  const versions = versionsQuery.data?.versions ?? []
  const currentVersionId = versionsQuery.data?.current_version_id ?? versions[0]?.id ?? null
  const selectedVersion = versions.find(item => item.id === (selectedVersionId ?? currentVersionId)) ?? versions[0]
  const pendingItems = pendingQuery.data?.pending ?? []
  const checks = (checksQuery.data?.checks ?? []).filter(item => checkConditionId === 'all' || item.condition_id === checkConditionId)
  const capability = capabilityQuery.data?.modules.thesis
  const unavailable = capability?.available === false
  const knownConditions = useMemo(() => versions.flatMap(item => item.conditions).filter((item, index, all) => all.findIndex(other => other.id === item.id) === index), [versions])

  const invalidateLocal = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: QK.thesis.versions(instrument) }),
      queryClient.invalidateQueries({ queryKey: QK.thesis.checks(instrument) }),
      queryClient.invalidateQueries({ queryKey: QK.thesis.pending(instrument) }),
      queryClient.invalidateQueries({ queryKey: QK.thesis.history(instrument) }),
    ])
  }

  const createVersion = useMutation({
    mutationFn: () => {
      const anchor = toAnchorInput(draft.anchor)
      const conditions = draft.conditions.map(toConditionInput)
      if (selectedVersion) {
        const input: ThesisRevisionInput = {
          expected_predecessor_id: selectedVersion.id,
          change_reason: draft.changeReason.trim(),
          core_judgment: draft.coreJudgment.trim(),
          rationale: draft.rationale.trim(),
          anchors: [anchor],
          conditions,
        }
        return phase5Api.thesisReviseVersion(selectedVersion.id, input)
      }
      const input: ThesisVersionInput = {
        instrument,
        core_judgment: draft.coreJudgment.trim(),
        rationale: draft.rationale.trim(),
        change_reason: draft.changeReason.trim(),
        anchors: [anchor],
        conditions,
      }
      return phase5Api.thesisCreateVersion(instrument, input)
    },
    onSuccess: async response => {
      setSelectedVersionId(response.version.id)
      setEditing(false)
      setReviewingDraft(false)
      setCreationConfirmOpen(false)
      await invalidateLocal()
    },
  })

  const reviewMutation = useMutation({
    mutationFn: ({ pending, action }: { pending: ThesisPending; action: ReviewAction }) => action === 'confirm'
      ? phase5Api.thesisConfirm(pending.id, rationale)
      : phase5Api.thesisReject(pending.id, rationale),
    onSuccess: async () => {
      setConflict(false)
      setReviewTarget(null)
      setRationale('')
      await invalidateLocal()
    },
    onError: async error => {
      if (error instanceof ApiRequestError && error.status === 409) {
        setConflict(true)
        await invalidateLocal()
      }
    },
  })

  function beginDraft(base?: ThesisVersion) {
    setDraft(draftFromVersion(base))
    setDraftError(null)
    setReviewingDraft(false)
    setEditing(true)
    requestAnimationFrame(() => firstFieldRef.current?.focus())
  }

  function validateDraft() {
    if (!draft.coreJudgment.trim() || !draft.rationale.trim() || !draft.changeReason.trim()) {
      setDraftError('请完整填写核心判断、理由和版本变更理由。')
      firstFieldRef.current?.focus()
      return
    }
    if (!draft.anchor.method.trim() || !draft.anchor.currency.trim() || !draft.anchor.asOf || !draft.anchor.assumption.trim()) {
      setDraftError('估值方法、币种、截至日和至少一条估值假设均为必填。')
      lowRef.current?.focus()
      return
    }
    if (!Number.isFinite(Number(draft.anchor.low)) || !Number.isFinite(Number(draft.anchor.high))) {
      setDraftError('估值下限和上限必须是有效数字。')
      lowRef.current?.focus()
      return
    }
    if (Number(draft.anchor.high) < Number(draft.anchor.low)) {
      setDraftError('估值上限不得低于下限。')
      lowRef.current?.focus()
      return
    }
    if (draft.conditions.some(item => !item.field.trim() || !item.unit.trim() || !item.description.trim() || !Number.isFinite(Number(item.lookbackDays)) || item.threshold.split(',').some(value => !Number.isFinite(Number(value.trim()))))) {
      setDraftError('每个失效条件都必须包含结构字段、阈值、单位、lookback、说明和独立检查周期。')
      return
    }
    setDraftError(null)
    setReviewingDraft(true)
  }

  if (capabilityQuery.isLoading && !capability) return <PanelLoading label="正在确认投资论点模块并读取不可变版本…" />
  if (capabilityQuery.isError && !capability) return <LocalError title="暂时无法确认模块状态" detail={errorReason(capabilityQuery.error)} action="重新确认模块状态" onRetry={() => capabilityQuery.refetch()} />
  if (unavailable) return <section aria-labelledby={headingId} className="rounded-card border border-border bg-surface p-4 sm:p-6"><PanelHeading id={headingId} title="投资论点" status="不可用" /><p className="mt-3 max-w-[72ch] text-sm text-foreground">此部署未启用投资论点模块。当前分析报告、证据和信号历史仍可使用。请联系部署维护者启用投资论点可选依赖并恢复条件检查调度。</p></section>

  return <section aria-labelledby={headingId} className="space-y-6 rounded-card border border-border bg-surface p-4 text-sm text-foreground sm:p-6">
    <header className="space-y-2">
      <PanelHeading id={headingId} title="投资论点" status="可用" />
      <p className="font-mono text-sm tabular-nums">{displayTitle(title, instrument)}</p>
      <p className="max-w-[72ch] text-sm text-secondary">自动检查只能提出待确认结论，不能替你改变论点状态。</p>
    </header>

    {pendingItems.map(item => <PendingConclusion key={item.id} pending={item} version={versions.find(version => version.id === item.version_id)} checks={checksQuery.data?.checks ?? []} onReview={action => { setConflict(false); setReviewTarget({ pending: item, action }) }} />)}
    {conflict && <div role="alert" className="rounded-card border border-danger/50 bg-danger/10 p-4 text-danger">结论未记录：状态已变化，请重新查看当前论点。</div>}

    {versionsQuery.isError && <LocalError title="无法读取投资论点" detail={`无法读取投资论点：${errorReason(versionsQuery.error)}。已显示的版本、待确认结论和检查历史将保留，当前官方状态不会改变。`} action="重新加载投资论点" onRetry={() => versionsQuery.refetch()} compact />}

    {!versionsQuery.isLoading && versions.length === 0 && !editing ? <div className="rounded-card border border-border bg-elevated p-4">
      <h3 className="text-base font-semibold">尚无投资论点</h3>
      <p className="mt-2 max-w-[72ch] text-secondary">为当前标的记录核心判断、带假设的估值区间和可定期检查的失效条件。</p>
      <button type="button" onClick={() => beginDraft()} className={`${BUTTON} mt-4 bg-accent font-semibold text-white`}>创建第一版投资论点</button>
    </div> : null}

    {selectedVersion && <article className="space-y-4" aria-labelledby={`${headingId}-current`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h3 id={`${headingId}-current`} className="text-base font-semibold">{selectedVersion.id === currentVersionId ? '当前官方版本' : `论点版本 ${selectedVersion.version}`}</h3><p className="mt-1 text-xs text-secondary">版本 {selectedVersion.version} · 官方状态 {officialState(selectedVersion)} · 创建于 {dateTime(selectedVersion.created_at)}</p></div>
        <button type="button" onClick={() => beginDraft(selectedVersion)} className={`${BUTTON} border border-border bg-elevated text-foreground hover:border-accent`}>基于此版本创建新版本</button>
      </div>
      {selectedVersion.id !== currentVersionId && <p className="rounded-input bg-warning/10 p-3 text-warning"><Clock3 className="mr-2 inline h-4 w-4" aria-hidden="true" />历史版本，不再执行定期检查</p>}
      <div className="grid gap-4 xl:grid-cols-2">
        <div><h4 className="font-semibold">核心判断与理由</h4><p className="mt-2 max-w-[72ch] whitespace-pre-wrap break-words">{selectedVersion.core_judgment}</p><p className="mt-2 max-w-[72ch] whitespace-pre-wrap break-words text-secondary">{selectedVersion.rationale}</p><p className="mt-2 text-xs text-muted">版本变更理由：{selectedVersion.change_reason}</p></div>
        <div><h4 className="font-semibold">完整估值区间与假设</h4>{selectedVersion.anchors.map((anchor, index) => <div key={`${anchor.method}-${index}`} className="mt-2 border-t border-border pt-2 first:border-t-0 first:pt-0"><p className="font-mono text-sm tabular-nums">{anchor.method} · {anchor.currency} {anchor.low}–{anchor.high} · 截至 {anchor.as_of}</p><ul className="mt-1 list-disc space-y-1 pl-5">{versionAssumptions(selectedVersion).map(item => <li key={item}>{item}</li>)}</ul>{anchor.limitations.map(item => <p key={item} className="mt-1 text-secondary">限制：{item}</p>)}</div>)}</div>
      </div>
      <ConditionsTable conditions={selectedVersion.conditions} current={selectedVersion.id === currentVersionId} />
    </article>}

    {editing && <VersionForm draft={draft} setDraft={setDraft} error={draftError} reviewing={reviewingDraft} lowRef={lowRef} firstFieldRef={firstFieldRef} onReview={validateDraft} onCancel={() => { setEditing(false); setReviewingDraft(false) }} onConfirm={() => setCreationConfirmOpen(true)} />}

    <section aria-labelledby={`${headingId}-checks`} className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3"><div><h3 id={`${headingId}-checks`} className="text-base font-semibold">追加式证据检查历史</h3><p className="mt-1 text-xs text-secondary">检查结果只追加，不覆盖；证据不足不等于未命中。</p></div><label className="text-xs text-secondary">按条件筛选<select value={checkConditionId} onChange={event => setCheckConditionId(event.target.value)} className={`${INPUT} mt-1 min-w-52`}><option value="all">全部条件</option>{knownConditions.map(item => <option key={item.id} value={item.id}>{text(record(item).name, item.description || item.field)}</option>)}</select></label></div>
      {checksQuery.isError && <LocalError title="无法读取投资论点" detail={`无法读取投资论点：${errorReason(checksQuery.error)}。已显示的版本、待确认结论和检查历史将保留，当前官方状态不会改变。`} action="重新加载投资论点" onRetry={() => checksQuery.refetch()} compact />}
      <ChecksTable checks={checks} versions={versions} />
    </section>

    <VersionsTable versions={versions} currentVersionId={currentVersionId} selectedVersionId={selectedVersion?.id ?? null} onSelect={setSelectedVersionId} />

    {creationConfirmOpen && createPortal(<FocusDialog title="创建不可变论点版本" initialFocus="cancel" onClose={() => setCreationConfirmOpen(false)}>
      <p>创建后，旧版本及其检查历史会继续保留；新版本条件从各自 cadence 开始。该记录不能被覆盖或删除。</p>
      {createVersion.isError && <div role="alert" className="mt-3 rounded-input bg-danger/10 p-3 text-danger"><strong>无法创建不可变论点版本</strong><p>无法创建不可变论点版本：{errorReason(createVersion.error)}。</p><p>已填写的表单和审阅内容保留；既有版本与当前官方状态保持不变。本次未创建新版本；失败提交不作为论点版本写入，也不改写任何既有只读版本。</p></div>}
      <div className="mt-4 flex flex-wrap justify-end gap-2"><button type="button" data-dialog-cancel onClick={() => setCreationConfirmOpen(false)} className={`${BUTTON} border border-border`}>返回审阅</button><button type="button" onClick={() => createVersion.mutate()} disabled={createVersion.isPending} className={`${BUTTON} bg-accent font-semibold text-white disabled:opacity-60`}>{createVersion.isPending ? '正在创建不可变版本…' : '创建不可变论点版本'}</button></div>
    </FocusDialog>, document.body)}

    {reviewTarget && createPortal(<ReviewDialog target={reviewTarget} instrumentTitle={title} versions={versions} rationale={rationale} setRationale={setRationale} mutation={reviewMutation} onClose={() => setReviewTarget(null)} />, document.body)}
  </section>
}

function PanelHeading({ id, title, status }: { id: string; title: string; status: '可用' | '不可用' }) {
  return <div className="flex flex-wrap items-center gap-3"><h2 id={id} data-phase5-typography className="text-base font-semibold">{title}</h2><span className={`rounded-full px-2 py-1 text-xs ${status === '可用' ? 'bg-accent/10 text-accent' : 'bg-warning/10 text-warning'}`}>{status}</span></div>
}

function PanelLoading({ label }: { label: string }) {
  return <div role="status" className="min-h-32 rounded-card border border-border bg-surface p-4 text-sm text-secondary">{label}</div>
}

function LocalError({ title, detail, action, onRetry, compact = false }: { title: string; detail: string; action: string; onRetry: () => void; compact?: boolean }) {
  return <div role="alert" className={`rounded-card border border-danger/50 bg-danger/10 text-sm text-danger ${compact ? 'p-3' : 'p-4'}`}><p className="font-semibold"><AlertTriangle className="mr-2 inline h-4 w-4" aria-hidden="true" />{title}</p><p className="mt-1">{detail}</p><button type="button" onClick={onRetry} className={`${BUTTON} mt-2 border border-danger/50`}>{action}</button></div>
}

function PendingConclusion({ pending, version, checks, onReview }: { pending: ThesisPending; version?: ThesisVersion; checks: Array<{ id: string; observed_value: number | null; evidence_fingerprint: string; checked_at: string }>; onReview: (action: ReviewAction) => void }) {
  const source = record(pending)
  const check = checks.find(item => item.id === pending.check_id)
  const observed = numberValue(source.observed_value) ?? check?.observed_value
  return <aside className="space-y-3 rounded-card border border-warning/50 bg-warning/10 p-4" aria-labelledby={`pending-${pending.id}`}>
    <h3 id={`pending-${pending.id}`} className="text-base font-semibold text-warning"><ShieldAlert className="mr-2 inline h-5 w-5" aria-hidden="true" />待确认失效结论</h3>
    <p className="font-semibold">当前官方状态未改变，等待你的确认。</p>
    <dl className="grid gap-2 text-sm sm:grid-cols-2"><div><dt className="text-xs text-secondary">命中条件</dt><dd>{text(source.condition_name, pending.condition_id)}</dd></div><div><dt className="text-xs text-secondary">版本与检查</dt><dd>版本 {version?.version ?? pending.version_id} · {pending.check_id}</dd></div><div><dt className="text-xs text-secondary">观测值 / 阈值</dt><dd className="font-mono tabular-nums">{observed ?? '证据不足'} / {typeof source.threshold === 'number' || typeof source.threshold === 'string' ? source.threshold : '—'} {text(source.unit, '')}</dd></div><div><dt className="text-xs text-secondary">证据与时间</dt><dd>{text(source.evidence_label, '受治理证据')} · {dateTime(source.evidence_at ?? check?.checked_at)}</dd></div></dl>
    <p className="break-words font-mono text-xs [overflow-wrap:anywhere]">fingerprint: {text(source.evidence_fingerprint, check?.evidence_fingerprint ?? pending.evidence_fingerprint)}</p>
    <div className="flex flex-wrap gap-2"><button type="button" onClick={() => onReview('confirm')} className={`${BUTTON} bg-danger font-semibold text-white`}>确认论点失效</button><button type="button" onClick={() => onReview('reject')} className={`${BUTTON} border border-border bg-surface`}>驳回待确认结论</button></div>
  </aside>
}

function ConditionsTable({ conditions, current }: { conditions: ThesisCondition[]; current: boolean }) {
  const descriptionId = useId()
  return <div><p id={descriptionId} className="mb-2 text-xs text-secondary">左右滚动查看完整记录</p><div tabIndex={0} aria-describedby={descriptionId} className={`overflow-x-auto ${FOCUS}`}><table className="min-w-[900px] w-full text-left text-xs"><caption className="sr-only">结构化失效条件</caption><thead className="bg-elevated text-secondary"><tr><th scope="col" className="p-2">条件</th><th scope="col" className="p-2">来源 / 字段</th><th scope="col" className="p-2">运算 / 阈值</th><th scope="col" className="p-2">lookback</th><th scope="col" className="p-2">独立检查周期</th><th scope="col" className="p-2">时区</th><th scope="col" className="p-2">下次检查</th></tr></thead><tbody>{conditions.map(condition => { const schedule = conditionSchedule(condition); return <tr key={condition.id} className="border-t border-border"><th scope="row" className="p-2 font-normal">{text(record(condition).name, condition.description || condition.id)}</th><td className="p-2">{condition.source_kind} / {condition.field}</td><td className="p-2 font-mono">{condition.operator} {Array.isArray(condition.threshold) ? condition.threshold.join('–') : condition.threshold} {condition.unit}</td><td className="p-2">{condition.lookback_days ?? record(condition).lookback} 日</td><td className="p-2">{CADENCES.find(item => item.value === condition.cadence)?.label ?? condition.cadence}</td><td className="p-2">{condition.timezone}</td><td className="p-2">{current && schedule.active !== false ? dateTime(schedule.next_due_at) : '历史版本，不再执行'}</td></tr> })}</tbody></table></div></div>
}

function ChecksTable({ checks, versions }: { checks: Array<{ id: string; condition_id: string; version_id: string; due_at: string; checked_at: string; result: keyof typeof CHECK_LABELS; observed_value: number | null; evidence_fingerprint: string; evidence?: unknown[]; safe_reason?: string | null }>; versions: ThesisVersion[] }) {
  const descriptionId = useId()
  return <><p id={descriptionId} className="text-xs text-secondary">左右滚动查看完整记录</p><div tabIndex={0} aria-describedby={descriptionId} className={`overflow-x-auto ${FOCUS}`}><table className="min-w-[960px] w-full text-left text-xs"><caption className="sr-only">投资论点证据检查历史</caption><thead className="bg-elevated text-secondary"><tr><th scope="col" className="p-2">结果</th><th scope="col" className="p-2">条件</th><th scope="col" className="p-2">到期时间</th><th scope="col" className="p-2">检查时间</th><th scope="col" className="p-2">观测值</th><th scope="col" className="p-2">证据</th><th scope="col" className="p-2">版本</th><th scope="col" className="p-2">检查周期</th></tr></thead><tbody>{checks.length ? checks.map(check => { const source = record(check); const version = versions.find(item => item.id === check.version_id); const condition = version?.conditions.find(item => item.id === check.condition_id); const evidence = Array.isArray(check.evidence) && check.evidence.length ? check.evidence.map(item => text(record(item).source_id, text(record(item).source_kind, '受治理证据'))).join('、') : text(source.evidence_label, check.safe_reason ?? '受治理证据'); return <tr key={check.id} className="border-t border-border"><th scope="row" className="p-2 font-normal">{CHECK_LABELS[check.result]}</th><td className="p-2">{text(record(condition).name, condition?.description || check.condition_id)}</td><td className="p-2">{dateTime(check.due_at)}</td><td className="p-2">{dateTime(check.checked_at)}</td><td className="p-2 font-mono">{check.observed_value == null ? '—' : `${check.observed_value} ${text(source.unit, condition?.unit ?? '')}`}</td><td className="p-2"><span>{evidence}</span><span className="mt-1 block break-words font-mono [overflow-wrap:anywhere]">{check.evidence_fingerprint}</span></td><td className="p-2">{version ? `版本 ${version.version}` : check.version_id}</td><td className="p-2">{text(source.cadence, condition?.cadence ?? '—')}</td></tr> }) : <tr><td colSpan={8} className="p-4 text-center text-secondary">尚无追加式检查记录。</td></tr>}</tbody></table></div></>
}

function VersionsTable({ versions, currentVersionId, selectedVersionId, onSelect }: { versions: ThesisVersion[]; currentVersionId: string | null; selectedVersionId: string | null; onSelect: (id: string) => void }) {
  const descriptionId = useId()
  return <section aria-labelledby={`${descriptionId}-heading`} className="space-y-2"><h3 id={`${descriptionId}-heading`} className="text-base font-semibold">不可变版本时间线</h3><p id={descriptionId} className="text-xs text-secondary">左右滚动查看完整记录</p><div tabIndex={0} aria-describedby={descriptionId} className={`overflow-x-auto ${FOCUS}`}><table className="min-w-[800px] w-full text-left text-xs"><caption className="sr-only">投资论点版本历史</caption><thead className="bg-elevated text-secondary"><tr><th scope="col" className="p-2">版本</th><th scope="col" className="p-2">前序版本</th><th scope="col" className="p-2">创建时间</th><th scope="col" className="p-2">变更理由</th><th scope="col" className="p-2">估值锚 / 条件</th><th scope="col" className="p-2">当时官方状态</th><th scope="col" className="p-2">详情</th></tr></thead><tbody>{versions.map(version => <tr key={version.id} className={`border-t border-border ${version.id === selectedVersionId ? 'bg-accent/5' : ''}`}><th scope="row" className="p-2 font-normal">版本 {version.version}{version.id === currentVersionId ? '（当前）' : ''}</th><td className="p-2 font-mono">{version.predecessor_id ?? '首版'}</td><td className="p-2">{dateTime(version.created_at)}</td><td className="max-w-[40ch] break-words p-2">{version.change_reason}</td><td className="p-2">{version.anchors.length} / {version.conditions.length}</td><td className="p-2">{officialState(version)}</td><td className="p-2"><button type="button" onClick={() => onSelect(version.id)} className={`${BUTTON} min-h-0 py-2 text-accent underline`}>查看完整版本</button></td></tr>)}</tbody></table></div></section>
}

function VersionForm({ draft, setDraft, error, reviewing, lowRef, firstFieldRef, onReview, onCancel, onConfirm }: { draft: VersionDraft; setDraft: React.Dispatch<React.SetStateAction<VersionDraft>>; error: string | null; reviewing: boolean; lowRef: React.RefObject<HTMLInputElement>; firstFieldRef: React.RefObject<HTMLTextAreaElement>; onReview: () => void; onCancel: () => void; onConfirm: () => void }) {
  const updateAnchor = (field: keyof AnchorDraft, value: string) => setDraft(current => ({ ...current, anchor: { ...current.anchor, [field]: value } }))
  const updateCondition = (index: number, field: keyof ConditionDraft, value: string) => setDraft(current => ({ ...current, conditions: current.conditions.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item) }))
  return <section aria-labelledby="thesis-version-form" className="space-y-4 rounded-card border border-border bg-elevated p-4"><h3 id="thesis-version-form" className="text-base font-semibold">创建下一版不可变论点</h3>{error && <div role="alert" className="rounded-input bg-danger/10 p-3 text-danger">{error}</div>}
    <div className="grid gap-4 lg:grid-cols-2"><label>核心判断<textarea ref={firstFieldRef} value={draft.coreJudgment} onChange={event => setDraft(current => ({ ...current, coreJudgment: event.target.value }))} className={`${INPUT} mt-1 min-h-28`} /></label><label>判断理由<textarea value={draft.rationale} onChange={event => setDraft(current => ({ ...current, rationale: event.target.value }))} className={`${INPUT} mt-1 min-h-28`} /></label></div>
    <fieldset className="grid gap-3 rounded-card border border-border p-3 sm:grid-cols-2 lg:grid-cols-4"><legend className="px-1 font-semibold">估值锚</legend><label>估值方法<input value={draft.anchor.method} onChange={event => updateAnchor('method', event.target.value)} className={`${INPUT} mt-1`} /></label><label>估值币种<input value={draft.anchor.currency} onChange={event => updateAnchor('currency', event.target.value)} className={`${INPUT} mt-1`} /></label><label>估值截至日<input type="date" value={draft.anchor.asOf} onChange={event => updateAnchor('asOf', event.target.value)} className={`${INPUT} mt-1`} /></label><span /><label>估值下限<input ref={lowRef} type="number" value={draft.anchor.low} onChange={event => updateAnchor('low', event.target.value)} className={`${INPUT} mt-1`} /></label><label>估值上限<input type="number" value={draft.anchor.high} onChange={event => updateAnchor('high', event.target.value)} className={`${INPUT} mt-1`} /></label><label className="sm:col-span-2">估值假设（至少一条）<input value={draft.anchor.assumption} onChange={event => updateAnchor('assumption', event.target.value)} className={`${INPUT} mt-1`} /></label><label className="sm:col-span-2 lg:col-span-4">估值限制<input value={draft.anchor.limitation} onChange={event => updateAnchor('limitation', event.target.value)} className={`${INPUT} mt-1`} /></label></fieldset>
    <fieldset className="space-y-3 rounded-card border border-border p-3"><legend className="px-1 font-semibold">结构化失效条件与独立检查周期</legend>{draft.conditions.map((condition, index) => <div key={index} className="grid gap-3 border-t border-border pt-3 first:border-t-0 first:pt-0 sm:grid-cols-2 lg:grid-cols-4"><label>条件 {index + 1} 说明<input value={condition.description} onChange={event => updateCondition(index, 'description', event.target.value)} className={`${INPUT} mt-1`} /></label><label>字段<input value={condition.field} onChange={event => updateCondition(index, 'field', event.target.value)} className={`${INPUT} mt-1`} /></label><label>阈值<input value={condition.threshold} onChange={event => updateCondition(index, 'threshold', event.target.value)} className={`${INPUT} mt-1`} /></label><label>单位<input value={condition.unit} onChange={event => updateCondition(index, 'unit', event.target.value)} className={`${INPUT} mt-1`} /></label><label>条件 {index + 1} 检查周期<select value={condition.cadence} onChange={event => updateCondition(index, 'cadence', event.target.value)} className={`${INPUT} mt-1`}>{CADENCES.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label>lookback（日）<input type="number" min="1" value={condition.lookbackDays} onChange={event => updateCondition(index, 'lookbackDays', event.target.value)} className={`${INPUT} mt-1`} /></label><label>来源类型<select value={condition.sourceKind} onChange={event => updateCondition(index, 'sourceKind', event.target.value)} className={`${INPUT} mt-1`}><option value="market">市场</option><option value="financial">财务</option><option value="analysis">分析</option></select></label><label>运算符<select value={condition.operator} onChange={event => updateCondition(index, 'operator', event.target.value)} className={`${INPUT} mt-1`}><option value="lt">小于</option><option value="lte">小于等于</option><option value="gt">大于</option><option value="gte">大于等于</option><option value="eq">等于</option><option value="between">区间</option></select></label></div>)}</fieldset>
    <label>版本变更理由<textarea value={draft.changeReason} onChange={event => setDraft(current => ({ ...current, changeReason: event.target.value }))} className={`${INPUT} mt-1 min-h-20`} /></label>
    {reviewing && <div className="rounded-card border border-accent/40 bg-accent/5 p-3"><h4 className="font-semibold">创建前审阅摘要</h4><p className="mt-1">核心判断、1 个估值区间、{draft.conditions.length} 个结构化条件与各自检查周期将写入新版本；旧版本和检查历史保持不变。</p></div>}
    <div className="flex flex-wrap justify-end gap-2"><button type="button" onClick={onCancel} className={`${BUTTON} border border-border`}>暂不处理</button>{reviewing ? <button type="button" onClick={onConfirm} className={`${BUTTON} bg-accent font-semibold text-white`}>创建不可变论点版本</button> : <button type="button" onClick={onReview} className={`${BUTTON} bg-accent font-semibold text-white`}>进入审阅</button>}</div>
  </section>
}

function ReviewDialog({ target, instrumentTitle, versions, rationale, setRationale, mutation, onClose }: { target: { pending: ThesisPending; action: ReviewAction }; instrumentTitle: string; versions: ThesisVersion[]; rationale: string; setRationale: (value: string) => void; mutation: ReturnType<typeof useMutation<{ review: unknown; official_status: string }, Error, { pending: ThesisPending; action: ReviewAction }>>; onClose: () => void }) {
  const version = versions.find(item => item.id === target.pending.version_id)
  const title = target.action === 'confirm' ? '确认论点失效' : '驳回待确认结论'
  const normalizedTitle = instrumentTitle.replace(/（([^）]+)）/, '（$1）')
  return <FocusDialog title={title} initialFocus="textarea" onClose={onClose}>
    <p>{target.action === 'confirm' ? `确认将 ${normalizedTitle} 的论点版本 ${version?.version ?? target.pending.version_id} 记录为已失效？命中条件与证据会永久保留；此操作不会执行交易或修改其他研究对象。` : '驳回后，当前官方状态保持不变；条件、检查记录和证据仍会永久保留。'}</p>
    <label className="mt-4 block">{target.action === 'confirm' ? '确认理由（至少 10 个字符）' : '驳回理由（至少 10 个字符）'}<textarea data-dialog-textarea value={rationale} onChange={event => setRationale(event.target.value)} className={`${INPUT} mt-1 min-h-28`} /></label>
    {mutation.isError && !(mutation.error instanceof ApiRequestError && mutation.error.status === 409) && <div role="alert" className="mt-3 rounded-input bg-danger/10 p-3 text-danger"><strong>无法确认论点操作结果</strong><p>确认或驳回请求的传输状态不确定：{errorReason(mutation.error)}。已填写的理由保留。</p><p>不得假定服务端未处理本次请求；重试前必须重新读取当前论点及待确认结论，并以服务端当前记录为准。</p></div>}
    <div className="mt-4 flex flex-wrap justify-end gap-2"><button type="button" onClick={onClose} className={`${BUTTON} border border-border`}>暂不处理</button><button type="button" onClick={() => mutation.mutate(target)} disabled={rationale.trim().length < 10 || mutation.isPending} className={`${BUTTON} ${target.action === 'confirm' ? 'bg-danger text-white' : 'bg-accent text-white'} font-semibold disabled:opacity-50`}>{mutation.isPending ? '正在记录人工决定…' : title}</button></div>
  </FocusDialog>
}

function FocusDialog({ title, initialFocus, onClose, children }: { title: string; initialFocus: 'textarea' | 'cancel'; onClose: () => void; children: React.ReactNode }) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const returnFocus = useRef(document.activeElement as HTMLElement | null)
  useEffect(() => {
    const selector = initialFocus === 'textarea' ? '[data-dialog-textarea]' : '[data-dialog-cancel]'
    requestAnimationFrame(() => dialogRef.current?.querySelector<HTMLElement>(selector)?.focus())
    return () => returnFocus.current?.focus()
  }, [initialFocus])
  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') { event.preventDefault(); onClose(); return }
    if (event.key !== 'Tab') return
    const focusables = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>('button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled])') ?? [])
    if (!focusables.length) return
    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
  }
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-base/80 p-4"><div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="phase5-dialog-title" onKeyDown={onKeyDown} className="max-h-[calc(100vh-2rem)] w-full max-w-xl overflow-y-auto rounded-dialog border border-border bg-surface p-4 text-sm text-foreground sm:p-6"><h2 id="phase5-dialog-title" className="text-base font-semibold">{title}</h2><div className="mt-3">{children}</div></div></div>
}

export function CopyableId({ value, label = '复制标识' }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  return <span className="inline-flex max-w-full items-start gap-1"><code className="break-words font-mono text-xs [overflow-wrap:anywhere]">{value}</code><button type="button" aria-label={label} title={label} onClick={() => { void navigator.clipboard.writeText(value); setCopied(true) }} className={`${FOCUS} inline-flex min-h-11 min-w-11 items-center justify-center rounded-btn text-accent sm:min-h-0 sm:min-w-0 sm:p-1`}><Copy className="h-4 w-4" aria-hidden="true" /></button>{copied && <span role="status" className="sr-only">已复制</span>}</span>
}
