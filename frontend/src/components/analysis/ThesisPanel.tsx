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
  type ThesisConditionOperator,
  type ThesisCheck,
  type ThesisPending,
  type ThesisRevisionInput,
  type ThesisSourceKind,
  type ThesisValuationAnchorInput,
  type ThesisVersion,
  type ThesisVersionInput,
} from '@/lib/phase5Api'
import { QK } from '@/lib/queryKeys'

const FOCUS = 'focus:outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base'
const INPUT = `min-h-11 w-full rounded-input border border-border bg-base px-3 py-2 text-sm text-foreground ${FOCUS}`
const BUTTON = `inline-flex min-h-11 items-center justify-center rounded-btn px-3 text-sm ${FOCUS}`
const VERSION_PAGE_SIZE = 25
const LEDGER_PAGE_SIZE = 50
const VALUATION_METHODS = [
  { value: 'dcf', label: 'DCF' },
  { value: 'ddm', label: 'DDM' },
  { value: 'relative', label: '相对估值' },
  { value: 'asset_based', label: '资产基础法' },
] as const
const VALUATION_METHOD_PATTERN = /^[a-z][a-z0-9_]*$/
const ASSUMPTION_NAME_PATTERN = /^[A-Za-z][A-Za-z0-9_.-]*$/
const VALUATION_UNIT_PATTERN = /^[A-Za-z][A-Za-z0-9_/%.-]*$/
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
const SOURCE_LABELS: Record<ThesisSourceKind, string> = {
  market: '市场',
  financial: '财务',
  analysis: '分析',
}
const OPERATOR_LABELS: Record<ThesisConditionOperator, string> = {
  lt: '小于',
  lte: '小于等于',
  gt: '大于',
  gte: '大于等于',
  eq: '等于',
  between: '区间',
}
const ALL_OPERATORS = Object.keys(OPERATOR_LABELS) as ThesisConditionOperator[]
const CONDITION_REGISTRY: Record<ThesisSourceKind, {
  fields: Array<{ value: string; label: string; units: string[] }>
  operators: ThesisConditionOperator[]
}> = {
  market: {
    fields: [
      { value: 'close', label: '收盘价', units: ['CNY'] },
      { value: 'open', label: '开盘价', units: ['CNY'] },
      { value: 'high', label: '最高价', units: ['CNY'] },
      { value: 'low', label: '最低价', units: ['CNY'] },
      { value: 'volume', label: '成交量', units: ['shares'] },
      { value: 'amount', label: '成交额', units: ['CNY'] },
    ],
    operators: ALL_OPERATORS,
  },
  financial: {
    fields: [
      { value: 'revenue_growth_yoy', label: '营收同比增长', units: ['ratio'] },
      { value: 'net_income_growth_yoy', label: '净利润同比增长', units: ['ratio'] },
      { value: 'gross_margin', label: '毛利率', units: ['ratio'] },
      { value: 'roe', label: '净资产收益率', units: ['ratio'] },
    ],
    operators: ALL_OPERATORS,
  },
  analysis: {
    fields: [{ value: 'report_score', label: '报告评分', units: ['score'] }],
    operators: ALL_OPERATORS,
  },
}
const FORM_ERROR_ID = 'thesis-version-form-error'

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
  assumptions: AssumptionDraft[]
  limitations: string[]
}

interface AssumptionDraft {
  name: string
  value: string
  unit: string
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
  anchors: AnchorDraft[]
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

function versionAssumptions(anchor: ThesisVersion['anchors'][number]): string[] {
  return (anchor.assumptions as unknown[]).map(item => typeof item === 'string' ? item : `${text(record(item).name, '假设')} ${record(item).value ?? ''} ${text(record(item).unit, '')}`.trim())
}

function valuationMethodLabel(method: string): string {
  return VALUATION_METHODS.find(item => item.value === method)?.label ?? method
}

function conditionSchedule(condition: ThesisCondition): LooseRecord {
  const source = record(condition)
  return record(source.schedule ?? { next_due_at: source.next_due_at, active: true })
}

function normalizeOperator(value: unknown): ThesisConditionInput['operator'] {
  if (value === '<') return 'lt'
  if (value === '<=') return 'lte'
  if (value === '>') return 'gt'
  if (value === '>=') return 'gte'
  if (value === '=') return 'eq'
  return value === 'lt' || value === 'lte' || value === 'gt' || value === 'gte' || value === 'eq' || value === 'between' ? value : 'lt'
}

function draftFromVersion(version?: ThesisVersion): VersionDraft {
  const conditions = version?.conditions.length ? version.conditions.map(item => {
    const source = record(item)
    const rawThreshold = source.threshold
    const registry = CONDITION_REGISTRY[item.source_kind]
    const field = registry.fields.find(candidate => candidate.value === item.field) ?? registry.fields[0]
    const operator = normalizeOperator(source.operator)
    return {
      sourceKind: item.source_kind,
      field: field.value,
      operator: registry.operators.includes(operator) ? operator : registry.operators[0],
      threshold: Array.isArray(rawThreshold) ? rawThreshold.join(',') : String(rawThreshold ?? ''),
      unit: field.units.includes(item.unit) ? item.unit : field.units[0],
      lookbackDays: String(item.lookback_days ?? source.lookback ?? 1),
      cadence: item.cadence,
      description: item.description || text(source.name, item.field),
    }
  }) : [{ sourceKind: 'market', field: 'close', operator: 'lt', threshold: '', unit: 'CNY', lookbackDays: '20', cadence: 'weekly', description: '' } satisfies ConditionDraft]
  return {
    coreJudgment: version?.core_judgment ?? '',
    rationale: version?.rationale ?? '',
    changeReason: version ? '' : '建立首版研究账本',
    anchors: version?.anchors.length ? version.anchors.map(anchor => ({
      method: anchor.method,
      currency: anchor.currency,
      asOf: anchor.as_of,
      low: String(anchor.low),
      high: String(anchor.high),
      assumptions: (anchor.assumptions as unknown[]).map(item => {
        const assumption = record(item)
        return {
          name: typeof item === 'string' ? item : text(assumption.name, ''),
          value: assumption.value == null ? '' : String(assumption.value),
          unit: text(assumption.unit, ''),
        }
      }),
      limitations: anchor.limitations.length ? [...anchor.limitations] : [''],
    })) : [{
      method: 'dcf',
      currency: 'CNY',
      asOf: new Date().toISOString().slice(0, 10),
      low: '',
      high: '',
      assumptions: [{ name: 'revenue_growth', value: '', unit: 'percent' }],
      limitations: [''],
    }],
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
    assumptions: draft.assumptions.map(assumption => ({
      name: assumption.name.trim(),
      value: Number(assumption.value),
      unit: assumption.unit.trim(),
    })),
    limitations: draft.limitations.map(item => item.trim()).filter(Boolean),
  }
}

function mergeById<T extends { id: string }>(current: T[], incoming: T[], reset: boolean): T[] {
  const values = reset ? [] : [...current]
  for (const item of incoming) {
    const index = values.findIndex(existing => existing.id === item.id)
    if (index >= 0) values[index] = item
    else values.push(item)
  }
  return values
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
  const [draftErrorTarget, setDraftErrorTarget] = useState<string | null>(null)
  const [creationConfirmOpen, setCreationConfirmOpen] = useState(false)
  const [reviewTarget, setReviewTarget] = useState<{ pending: ThesisPending; action: ReviewAction } | null>(null)
  const [rationale, setRationale] = useState('')
  const [conflict, setConflict] = useState(false)
  const [versionOffset, setVersionOffset] = useState(0)
  const [checkOffset, setCheckOffset] = useState(0)
  const [pendingOffset, setPendingOffset] = useState(0)
  const [historyOffset, setHistoryOffset] = useState(0)
  const [loadedVersions, setLoadedVersions] = useState<ThesisVersion[]>([])
  const [loadedChecks, setLoadedChecks] = useState<ThesisCheck[]>([])
  const [loadedPending, setLoadedPending] = useState<ThesisPending[]>([])
  const [loadedHistory, setLoadedHistory] = useState<ThesisPending[]>([])
  const [foreignLedgerRejected, setForeignLedgerRejected] = useState(false)
  const lowRef = useRef<HTMLInputElement>(null)
  const firstFieldRef = useRef<HTMLTextAreaElement>(null)

  const capabilityQuery = useQuery({ queryKey: QK.phase5Capabilities, queryFn: phase5Api.capabilities, staleTime: 60_000 })
  const versionsQuery = useQuery({ queryKey: QK.thesis.versions(instrument, versionOffset, VERSION_PAGE_SIZE), queryFn: () => phase5Api.thesisVersions(instrument, versionOffset, VERSION_PAGE_SIZE), placeholderData: keepPreviousData })
  const checksQuery = useQuery({ queryKey: QK.thesis.checks(instrument, checkOffset, LEDGER_PAGE_SIZE), queryFn: () => phase5Api.thesisChecks(instrument, checkOffset, LEDGER_PAGE_SIZE), placeholderData: keepPreviousData })
  const pendingQuery = useQuery({ queryKey: QK.thesis.pending(instrument, pendingOffset, LEDGER_PAGE_SIZE), queryFn: () => phase5Api.thesisPending(instrument, pendingOffset, LEDGER_PAGE_SIZE), placeholderData: keepPreviousData })
  const historyQuery = useQuery({ queryKey: QK.thesis.history(instrument, historyOffset, LEDGER_PAGE_SIZE), queryFn: () => phase5Api.thesisHistory(instrument, historyOffset, LEDGER_PAGE_SIZE), placeholderData: keepPreviousData })
  const missingSelectedVersionId = selectedVersionId && !loadedVersions.some(item => item.id === selectedVersionId) ? selectedVersionId : null
  const versionDetailQuery = useQuery({
    queryKey: QK.thesis.version(instrument, missingSelectedVersionId ?? 'none'),
    queryFn: async () => {
      const response = await phase5Api.thesisVersion(missingSelectedVersionId!)
      if (response.version.instrument !== instrument) throw new Error('论点版本对象与当前标的不一致。')
      return response.version
    },
    enabled: Boolean(missingSelectedVersionId),
    retry: false,
  })

  useEffect(() => {
    const detail = versionDetailQuery.data
    if (!detail || detail.instrument !== instrument) return
    setLoadedVersions(current => mergeById(current, [detail], false))
  }, [instrument, versionDetailQuery.data])

  const versions = loadedVersions.filter(item => item.instrument === instrument)
  const versionById = new Map(versions.map(item => [item.id, item]))
  const currentVersion = versions.reduce<ThesisVersion | undefined>(
    (latest, item) => !latest || item.version > latest.version ? item : latest,
    undefined,
  )
  const currentVersionId = currentVersion?.id ?? null
  const selectedVersion = versions.find(item => item.id === (selectedVersionId ?? currentVersionId)) ?? versions[0]
  const pendingItems = loadedPending.filter(item =>
    item.instrument === instrument
    && item.status === 'pending'
    && typeof item.version === 'number'
    && Boolean(item.version_id)
    && Boolean(item.thesis_id),
  )
  const checks = loadedChecks.filter(item =>
    item.instrument === instrument
    && typeof item.version === 'number'
    && Boolean(item.version_id)
    && (checkConditionId === 'all' || item.condition_id === checkConditionId),
  )
  const historyItems = loadedHistory.filter(item =>
    item.instrument === instrument
    && typeof item.version === 'number'
    && Boolean(item.version_id)
    && Boolean(item.thesis_id),
  )
  const capability = capabilityQuery.data?.modules?.thesis
  const unavailable = capability?.available === false
  const knownConditions = useMemo(() => versions.flatMap(item => item.conditions).filter((item, index, all) => all.findIndex(other => other.id === item.id) === index), [versions])

  useEffect(() => {
    const page = versionsQuery.data
    if (!page || page.offset !== versionOffset) return
    setLoadedVersions(current => mergeById(current, page.items.filter(item => item.instrument === instrument), page.offset === 0))
  }, [instrument, versionOffset, versionsQuery.data])
  useEffect(() => {
    const page = checksQuery.data
    if (!page || page.offset !== checkOffset) return
    if (page.items.some(item => item.instrument !== instrument)) setForeignLedgerRejected(true)
    setLoadedChecks(current => mergeById(
      current,
      page.items.filter(item => item.instrument === instrument && typeof item.version === 'number' && Boolean(item.version_id)),
      page.offset === 0,
    ))
  }, [instrument, checkOffset, checksQuery.data])
  useEffect(() => {
    const page = pendingQuery.data
    if (!page || page.offset !== pendingOffset) return
    if (page.items.some(item => item.instrument !== instrument)) setForeignLedgerRejected(true)
    setLoadedPending(current => mergeById(
      current,
      page.items.filter(item => item.instrument === instrument && typeof item.version === 'number' && Boolean(item.version_id)),
      page.offset === 0,
    ))
  }, [instrument, pendingOffset, pendingQuery.data])
  useEffect(() => {
    const page = historyQuery.data
    if (!page || page.offset !== historyOffset) return
    if (page.items.some(item => item.instrument !== instrument)) setForeignLedgerRejected(true)
    setLoadedHistory(current => mergeById(
      current,
      page.items.filter(item => item.instrument === instrument && typeof item.version === 'number' && Boolean(item.version_id)),
      page.offset === 0,
    ))
  }, [instrument, historyOffset, historyQuery.data])

  useEffect(() => {
    setSelectedVersionId(null)
    setVersionOffset(0)
    setCheckOffset(0)
    setPendingOffset(0)
    setHistoryOffset(0)
    setLoadedVersions([])
    setLoadedChecks([])
    setLoadedPending([])
    setLoadedHistory([])
    setForeignLedgerRejected(false)
    setCheckConditionId('all')
    setEditing(false)
    setReviewingDraft(false)
    setDraft(draftFromVersion())
    setDraftError(null)
    setDraftErrorTarget(null)
    setCreationConfirmOpen(false)
    setReviewTarget(null)
    setRationale('')
    setConflict(false)
  }, [instrument])

  const invalidateLocal = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: QK.thesis.versionsRoot(instrument) }),
      queryClient.invalidateQueries({ queryKey: QK.thesis.checksRoot(instrument) }),
      queryClient.invalidateQueries({ queryKey: QK.thesis.pendingRoot(instrument) }),
      queryClient.invalidateQueries({ queryKey: QK.thesis.historyRoot(instrument) }),
    ])
  }

  const createVersion = useMutation({
    mutationFn: async () => {
      const anchors = draft.anchors.map(toAnchorInput)
      const conditions = draft.conditions.map(toConditionInput)
      if (selectedVersion && !currentVersion) throw new Error('当前论点版本未完整加载。')
      const response = selectedVersion
        ? await phase5Api.thesisReviseVersion(currentVersion!.id, {
          expected_predecessor_id: currentVersion!.id,
          change_reason: draft.changeReason.trim(),
          core_judgment: draft.coreJudgment.trim(),
          rationale: draft.rationale.trim(),
          anchors,
          conditions,
        } satisfies ThesisRevisionInput)
        : await phase5Api.thesisCreateVersion(instrument, {
          instrument,
          core_judgment: draft.coreJudgment.trim(),
          rationale: draft.rationale.trim(),
          change_reason: draft.changeReason.trim(),
          anchors,
          conditions,
        } satisfies ThesisVersionInput)
      if (response.version.instrument !== instrument) throw new Error('论点响应对象与当前标的不一致。')
      return response
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
    mutationFn: ({ pending, action }: { pending: ThesisPending; action: ReviewAction }) => {
      if (
        pending.instrument !== instrument
        || pending.thesis_id === ''
        || pending.status !== 'pending'
        || typeof pending.version !== 'number'
      ) {
        throw new Error('待确认结论与当前标的不一致。')
      }
      const version = versionById.get(pending.version_id)
      if (version && (version.instrument !== instrument || version.thesis_id !== pending.thesis_id)) {
        throw new Error('待确认结论与当前标的不一致。')
      }
      return action === 'confirm'
        ? phase5Api.thesisConfirm(pending.id, rationale)
        : phase5Api.thesisReject(pending.id, rationale)
    },
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
    setDraftErrorTarget(null)
    setReviewingDraft(false)
    setEditing(true)
    requestAnimationFrame(() => firstFieldRef.current?.focus())
  }

  function failDraft(message: string, target: string) {
    setDraftError(message)
    setDraftErrorTarget(target)
    requestAnimationFrame(() => document.getElementById(target)?.focus())
  }

  function validateDraft() {
    if (!draft.coreJudgment.trim()) {
      failDraft('请完整填写核心判断、理由和版本变更理由。', 'thesis-core-judgment')
      return
    }
    if (!draft.rationale.trim()) {
      failDraft('请完整填写核心判断、理由和版本变更理由。', 'thesis-rationale')
      return
    }
    for (const [anchorIndex, anchor] of draft.anchors.entries()) {
      const method = anchor.method.trim()
      if (!VALUATION_METHOD_PATTERN.test(method)) {
        failDraft('估值方法必须是以小写字母开头、仅含小写字母、数字和下划线的标识。', `thesis-anchor-${anchorIndex}-method`)
        return
      }
      if (!anchor.currency.trim()) {
        failDraft('每个估值锚的币种均为必填。', `thesis-anchor-${anchorIndex}-currency`)
        return
      }
      if (!anchor.asOf) {
        failDraft('每个估值锚的截至日均为必填。', `thesis-anchor-${anchorIndex}-as-of`)
        return
      }
      if (anchor.assumptions.length === 0) {
        failDraft('每个估值锚必须至少包含一个估值假设。', `thesis-anchor-${anchorIndex}-low`)
        return
      }
      for (const [assumptionIndex, assumption] of anchor.assumptions.entries()) {
        const name = assumption.name.trim()
        if (!ASSUMPTION_NAME_PATTERN.test(name)) {
          failDraft('估值假设名称必须以字母开头，且仅含字母、数字、下划线、点或连字符。', `thesis-anchor-${anchorIndex}-assumption-${assumptionIndex}-name`)
          return
        }
        if (!assumption.value.trim() || !Number.isFinite(Number(assumption.value))) {
          failDraft('估值假设数值必须是有效数字。', `thesis-anchor-${anchorIndex}-assumption-${assumptionIndex}-value`)
          return
        }
        if (!VALUATION_UNIT_PATTERN.test(assumption.unit.trim())) {
          failDraft('估值假设单位必须以字母开头，且仅含受支持的单位字符。', `thesis-anchor-${anchorIndex}-assumption-${assumptionIndex}-unit`)
          return
        }
        if (anchor.assumptions.slice(0, assumptionIndex).some(item => item.name.trim() === name)) {
          failDraft('同一估值锚内的估值假设名称不得重复。', `thesis-anchor-${anchorIndex}-assumption-${assumptionIndex}-name`)
          return
        }
      }
      const limitationIndex = anchor.limitations.findIndex(item => item.trim())
      if (limitationIndex < 0) {
        failDraft('每个估值锚必须至少填写一项非空估值限制。', `thesis-anchor-${anchorIndex}-limitation-0`)
        return
      }
      if (!anchor.low.trim() || !anchor.high.trim() || !Number.isFinite(Number(anchor.low)) || !Number.isFinite(Number(anchor.high))) {
        failDraft('每个估值锚的下限和上限必须是有效数字。', !anchor.low.trim() || !Number.isFinite(Number(anchor.low)) ? `thesis-anchor-${anchorIndex}-low` : `thesis-anchor-${anchorIndex}-high`)
        return
      }
      if (Number(anchor.high) < Number(anchor.low)) {
        failDraft('估值上限不得低于下限。', `thesis-anchor-${anchorIndex}-low`)
        return
      }
    }
    for (const [conditionIndex, condition] of draft.conditions.entries()) {
      if (!condition.field.trim() || !condition.unit.trim() || !condition.description.trim()) {
        const target = !condition.description.trim()
          ? `thesis-condition-${conditionIndex}-description`
          : !condition.field.trim()
            ? `thesis-condition-${conditionIndex}-field`
            : `thesis-condition-${conditionIndex}-unit`
        failDraft('每个失效条件都必须包含结构字段、阈值、单位、lookback、说明和独立检查周期。', target)
        return
      }
      const lookback = Number(condition.lookbackDays)
      const thresholds = condition.threshold.split(',').map(value => value.trim())
      if (condition.operator === 'between') {
        if (thresholds.length !== 2 || thresholds.some(value => !value || !Number.isFinite(Number(value)))) {
          failDraft('区间阈值必须恰好包含两个有限数字。', `thesis-condition-${conditionIndex}-threshold`)
          return
        }
        if (Number(thresholds[0]) > Number(thresholds[1])) {
          failDraft('区间下限必须小于或等于上限。', `thesis-condition-${conditionIndex}-threshold`)
          return
        }
      } else if (thresholds.length !== 1 || !thresholds[0] || !Number.isFinite(Number(thresholds[0]))) {
        failDraft('条件阈值必须是一个有限数字。', `thesis-condition-${conditionIndex}-threshold`)
        return
      }
      if (!Number.isInteger(lookback) || lookback <= 0) {
        failDraft('lookback 必须是正整数。', `thesis-condition-${conditionIndex}-lookback`)
        return
      }
    }
    if (!draft.changeReason.trim()) {
      failDraft('请完整填写核心判断、理由和版本变更理由。', 'thesis-change-reason')
      return
    }
    setDraftError(null)
    setDraftErrorTarget(null)
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

    {foreignLedgerRejected && <LocalError title="论点账本身份不完整" detail="收到与当前标的不一致的检查或历史记录，已拒绝渲染。请重新加载当前标的的投资论点。" action="重新加载投资论点" onRetry={() => { setForeignLedgerRejected(false); void invalidateLocal() }} compact />}
    {pendingItems.map(item => <PendingConclusion key={item.id} pending={item} version={versions.find(version => version.id === item.version_id)} checks={loadedChecks} onReview={action => { setConflict(false); setReviewTarget({ pending: item, action }) }} />)}
    {pendingQuery.data?.has_more && <button type="button" onClick={() => setPendingOffset(pendingQuery.data.offset + pendingQuery.data.items.length)} className={`${BUTTON} border border-border`}>加载更多待确认结论</button>}
    {pendingQuery.isError && <LocalError title="无法读取投资论点" detail={`无法读取投资论点：${errorReason(pendingQuery.error)}。已显示的版本、待确认结论和检查历史将保留，当前官方状态不会改变。`} action="重新加载投资论点" onRetry={() => pendingQuery.refetch()} compact />}
    {conflict && <div role="alert" className="rounded-card border border-danger/50 bg-danger/10 p-4 text-danger">结论未记录：状态已变化，请重新查看当前论点。</div>}

    {versionsQuery.isError && <LocalError title="无法读取投资论点" detail={`无法读取投资论点：${errorReason(versionsQuery.error)}。已显示的版本、待确认结论和检查历史将保留，当前官方状态不会改变。`} action="重新加载投资论点" onRetry={() => versionsQuery.refetch()} compact />}
    {versionDetailQuery.isError && <LocalError title="版本详情未完整加载" detail={`已显示的检查与历史记录仍保留。版本详情加载失败：${errorReason(versionDetailQuery.error)}。`} action="重新加载版本详情" onRetry={() => versionDetailQuery.refetch()} compact />}
    {versionDetailQuery.isFetching && missingSelectedVersionId && <p role="status" className="text-sm text-secondary">正在加载所选版本详情…</p>}

    {!versionsQuery.isLoading && versions.length === 0 && !editing ? <div className="rounded-card border border-border bg-elevated p-4">
      <h3 className="text-base font-semibold">尚无投资论点</h3>
      <p className="mt-2 max-w-[72ch] text-secondary">为当前标的记录核心判断、带假设的估值区间和可定期检查的失效条件。</p>
      <button type="button" onClick={() => beginDraft()} className={`${BUTTON} mt-4 bg-accent-solid font-semibold text-white`}>创建第一版投资论点</button>
    </div> : null}

    {selectedVersion && <article className="space-y-4" aria-labelledby={`${headingId}-current`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><h3 id={`${headingId}-current`} className="text-base font-semibold">{selectedVersion.id === currentVersionId ? '当前官方版本' : `论点版本 ${selectedVersion.version}`}</h3><p className="mt-1 text-xs text-secondary">版本 {selectedVersion.version} · 官方状态 {officialState(selectedVersion)} · 创建于 {dateTime(selectedVersion.created_at)}</p></div>
        <button type="button" onClick={() => beginDraft(selectedVersion)} className={`${BUTTON} border border-border bg-elevated text-foreground hover:border-accent`}>基于此版本创建新版本</button>
      </div>
      {selectedVersion.id !== currentVersionId && <p className="rounded-input bg-warning/10 p-4 text-warning"><Clock3 className="mr-2 inline h-4 w-4" aria-hidden="true" />历史版本，不再执行定期检查</p>}
      <div className="grid gap-4 xl:grid-cols-2">
        <div><h4 className="font-semibold">核心判断与理由</h4><p className="mt-2 max-w-[72ch] whitespace-pre-wrap break-words">{selectedVersion.core_judgment}</p><p className="mt-2 max-w-[72ch] whitespace-pre-wrap break-words text-secondary">{selectedVersion.rationale}</p><p className="mt-2 text-xs text-muted">版本变更理由：{selectedVersion.change_reason}</p></div>
        <div><h4 className="font-semibold">完整估值区间与假设</h4>{selectedVersion.anchors.map((anchor, index) => <div key={`${anchor.method}-${index}`} className="mt-2 border-t border-border pt-2 first:border-t-0 first:pt-0"><p className="font-mono text-sm tabular-nums">{valuationMethodLabel(anchor.method)} · {anchor.currency} {anchor.low}–{anchor.high} · 截至 {anchor.as_of}</p><ul className="mt-1 list-disc space-y-1 pl-5">{versionAssumptions(anchor).map(item => <li key={item}>{item}</li>)}</ul>{anchor.limitations.map(item => <p key={item} className="mt-1 text-secondary">限制：{item}</p>)}</div>)}</div>
      </div>
      <ConditionsTable conditions={selectedVersion.conditions} checks={loadedChecks} current={selectedVersion.id === currentVersionId} />
    </article>}

    {editing && <VersionForm draft={draft} setDraft={setDraft} error={draftError} errorTarget={draftErrorTarget} reviewing={reviewingDraft} lowRef={lowRef} firstFieldRef={firstFieldRef} onReview={validateDraft} onCancel={() => { setEditing(false); setReviewingDraft(false) }} onConfirm={() => setCreationConfirmOpen(true)} />}

    <section aria-labelledby={`${headingId}-checks`} className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-4"><div><h3 id={`${headingId}-checks`} className="text-base font-semibold">追加式证据检查历史</h3><p className="mt-1 text-xs text-secondary">检查结果只追加，不覆盖；证据不足不等于未命中。</p></div><label className="text-xs text-secondary">按条件筛选<select value={checkConditionId} onChange={event => setCheckConditionId(event.target.value)} className={`${INPUT} mt-1 min-w-52`}><option value="all">全部条件</option>{knownConditions.map(item => <option key={item.id} value={item.id}>{text(record(item).name, item.description || item.field)}</option>)}</select></label></div>
      {checksQuery.isError && <LocalError title="无法读取投资论点" detail={`无法读取投资论点：${errorReason(checksQuery.error)}。已显示的版本、待确认结论和检查历史将保留，当前官方状态不会改变。`} action="重新加载投资论点" onRetry={() => checksQuery.refetch()} compact />}
      <ChecksTable checks={checks} versions={versions} />
      {checksQuery.data?.has_more && <button type="button" onClick={() => setCheckOffset(checksQuery.data.offset + checksQuery.data.items.length)} className={`${BUTTON} border border-border`}>加载更多检查记录</button>}
    </section>

    <VersionsTable versions={versions} currentVersionId={currentVersionId} selectedVersionId={selectedVersion?.id ?? null} onSelect={setSelectedVersionId} />
    {versionsQuery.data?.has_more && <button type="button" onClick={() => setVersionOffset(versionsQuery.data.offset + versionsQuery.data.items.length)} className={`${BUTTON} border border-border`}>加载更多论点版本</button>}

    <ThesisHistoryTable items={historyItems} />
    {historyQuery.data?.has_more && <button type="button" onClick={() => setHistoryOffset(historyQuery.data.offset + historyQuery.data.items.length)} className={`${BUTTON} border border-border`}>加载更多论点历史</button>}
    {historyQuery.isError && <LocalError title="无法读取投资论点历史" detail={`无法读取投资论点历史：${errorReason(historyQuery.error)}。已加载的不可变记录保持可读。`} action="重新加载论点历史" onRetry={() => historyQuery.refetch()} compact />}

    {creationConfirmOpen && createPortal(<FocusDialog title="创建不可变论点版本" initialFocus="cancel" onClose={() => setCreationConfirmOpen(false)}>
      <p>创建后，旧版本及其检查历史会继续保留；新版本条件从各自 cadence 开始。该记录不能被覆盖或删除。</p>
      {createVersion.isError && <div role="alert" className="mt-4 rounded-input bg-danger/10 p-4 text-danger"><strong>无法创建不可变论点版本</strong><p>无法创建不可变论点版本：{errorReason(createVersion.error)}。</p><p>已填写的表单和审阅内容保留；既有版本与当前官方状态保持不变。本次未创建新版本；失败提交不作为论点版本写入，也不改写任何既有只读版本。</p></div>}
      <div className="mt-4 flex flex-wrap justify-end gap-2"><button type="button" data-dialog-cancel onClick={() => setCreationConfirmOpen(false)} className={`${BUTTON} border border-border`}>返回审阅</button><button type="button" onClick={() => createVersion.mutate()} disabled={createVersion.isPending} className={`${BUTTON} bg-accent-solid font-semibold text-white disabled:opacity-60`}>{createVersion.isPending ? '正在创建不可变版本…' : '创建不可变论点版本'}</button></div>
    </FocusDialog>, document.body)}

    {reviewTarget && createPortal(<ReviewDialog target={reviewTarget} instrumentTitle={title} versions={versions} rationale={rationale} setRationale={setRationale} mutation={reviewMutation} onClose={() => setReviewTarget(null)} />, document.body)}
  </section>
}

function PanelHeading({ id, title, status }: { id: string; title: string; status: '可用' | '不可用' }) {
  return <div className="flex flex-wrap items-center gap-4"><h2 id={id} data-phase5-typography className="text-base font-semibold">{title}</h2><span className={`rounded-full border px-2 py-1 text-xs ${status === '可用' ? 'border-border bg-elevated text-secondary' : 'border-warning/50 bg-warning/10 text-warning'}`}>{status}</span></div>
}

function PanelLoading({ label }: { label: string }) {
  return <div role="status" className="min-h-32 rounded-card border border-border bg-surface p-4 text-sm text-secondary">{label}</div>
}

function LocalError({ title, detail, action, onRetry }: { title: string; detail: string; action: string; onRetry: () => void; compact?: boolean }) {
  return <div role="alert" className="rounded-card border border-danger/50 bg-danger/10 p-4 text-sm text-danger"><p className="font-semibold"><AlertTriangle className="mr-2 inline h-4 w-4" aria-hidden="true" />{title}</p><p className="mt-1">{detail}</p><button type="button" onClick={onRetry} className={`${BUTTON} mt-2 border border-danger/50`}>{action}</button></div>
}

function PendingConclusion({ pending, version, checks, onReview }: { pending: ThesisPending; version?: ThesisVersion; checks: Array<{ id: string; observed_value: number | null; evidence_fingerprint: string; checked_at: string }>; onReview: (action: ReviewAction) => void }) {
  const source = record(pending)
  const check = checks.find(item => item.id === pending.check_id)
  const observed = numberValue(source.observed_value) ?? check?.observed_value
  return <aside className="space-y-3 rounded-card border border-warning/50 bg-warning/10 p-4" aria-labelledby={`pending-${pending.id}`}>
    <h3 id={`pending-${pending.id}`} className="text-base font-semibold text-warning"><ShieldAlert className="mr-2 inline h-5 w-5" aria-hidden="true" />待确认失效结论</h3>
    <p className="font-semibold">当前官方状态未改变，等待你的确认。</p>
    <dl className="grid gap-2 text-sm sm:grid-cols-2"><div><dt className="text-xs text-secondary">命中条件</dt><dd>{text(source.condition_name, pending.condition_id)}</dd></div><div><dt className="text-xs text-secondary">版本与检查</dt><dd>版本 {version?.version ?? pending.version ?? pending.version_id} · {pending.check_id}</dd></div><div><dt className="text-xs text-secondary">观测值 / 阈值</dt><dd className="font-mono tabular-nums">{observed ?? '证据不足'} / {typeof source.threshold === 'number' || typeof source.threshold === 'string' ? source.threshold : '—'} {text(source.unit, '')}</dd></div><div><dt className="text-xs text-secondary">证据与时间</dt><dd>{text(source.evidence_label, '受治理证据')} · {dateTime(source.evidence_at ?? check?.checked_at)}</dd></div></dl>
    <p className="break-words font-mono text-xs [overflow-wrap:anywhere]">fingerprint: {text(source.evidence_fingerprint, check?.evidence_fingerprint ?? pending.evidence_fingerprint)}</p>
    <div className="flex flex-wrap gap-2"><button type="button" onClick={() => onReview('confirm')} className={`${BUTTON} bg-danger font-semibold text-white`}>确认论点失效</button><button type="button" onClick={() => onReview('reject')} className={`${BUTTON} border border-border bg-surface`}>驳回待确认结论</button></div>
  </aside>
}

function ConditionsTable({ conditions, checks, current }: { conditions: ThesisCondition[]; checks: ThesisCheck[]; current: boolean }) {
  const descriptionId = useId()
  return <div><p id={descriptionId} className="mb-2 text-xs text-secondary">左右滚动查看完整记录</p><div tabIndex={0} aria-describedby={descriptionId} className={`overflow-x-auto ${FOCUS}`}><table className="min-w-[1040px] w-full text-left text-xs"><caption className="sr-only">结构化失效条件</caption><thead className="bg-elevated text-secondary"><tr><th scope="col" className="p-2">条件</th><th scope="col" className="p-2">来源 / 字段</th><th scope="col" className="p-2">运算 / 阈值</th><th scope="col" className="p-2">lookback</th><th scope="col" className="p-2">独立检查周期</th><th scope="col" className="p-2">时区</th><th scope="col" className="p-2">最近检查</th><th scope="col" className="p-2">下次检查</th></tr></thead><tbody>{conditions.map(condition => {
    const schedule = conditionSchedule(condition)
    const conditionChecks = [...(condition.checks ?? []), ...checks.filter(check => check.condition_id === condition.id)]
    const latestCheck = conditionChecks.reduce<ThesisCheck | undefined>((latest, check) =>
      !latest || new Date(check.checked_at).valueOf() > new Date(latest.checked_at).valueOf() ? check : latest
    , undefined)
    const nextDue = typeof schedule.next_due_at === 'string' ? new Date(schedule.next_due_at) : null
    const latestAt = latestCheck ? new Date(latestCheck.checked_at) : null
    const overdue = current
      && schedule.active !== false
      && nextDue !== null
      && !Number.isNaN(nextDue.valueOf())
      && nextDue.valueOf() < Date.now()
      && (!latestAt || Number.isNaN(latestAt.valueOf()) || latestAt.valueOf() < nextDue.valueOf())
    return <tr key={condition.id} className="border-t border-border"><th scope="row" className="p-2 font-normal">{text(record(condition).name, condition.description || condition.id)}</th><td className="p-2">{condition.source_kind} / {condition.field}</td><td className="p-2 font-mono">{condition.operator} {Array.isArray(condition.threshold) ? condition.threshold.join('–') : condition.threshold} {condition.unit}</td><td className="p-2">{condition.lookback_days ?? record(condition).lookback} 日</td><td className="p-2">{CADENCES.find(item => item.value === condition.cadence)?.label ?? condition.cadence}</td><td className="p-2">{condition.timezone}</td><td className="p-2">{latestCheck ? <>最近检查：{CHECK_LABELS[latestCheck.result]}<span className="mt-1 block text-secondary">{dateTime(latestCheck.checked_at)}</span></> : '尚无检查结果'}</td><td className="p-2">{current && schedule.active !== false ? <>{dateTime(schedule.next_due_at)}{overdue && <span className="mt-1 block text-warning">检查已逾期，等待调度恢复。</span>}</> : '历史版本，不再执行'}</td></tr>
  })}</tbody></table></div></div>
}

function ChecksTable({ checks, versions }: { checks: ThesisCheck[]; versions: ThesisVersion[] }) {
  const descriptionId = useId()
  return <><p id={descriptionId} className="text-xs text-secondary">左右滚动查看完整记录</p><div tabIndex={0} aria-describedby={descriptionId} className={`overflow-x-auto ${FOCUS}`}><table className="min-w-[960px] w-full text-left text-xs"><caption className="sr-only">投资论点证据检查历史</caption><thead className="bg-elevated text-secondary"><tr><th scope="col" className="p-2">结果</th><th scope="col" className="p-2">条件</th><th scope="col" className="p-2">到期时间</th><th scope="col" className="p-2">检查时间</th><th scope="col" className="p-2">观测值</th><th scope="col" className="p-2">证据</th><th scope="col" className="p-2">版本</th><th scope="col" className="p-2">检查周期</th></tr></thead><tbody>{checks.length ? checks.map(check => { const source = record(check); const version = versions.find(item => item.id === check.version_id); const condition = version?.conditions.find(item => item.id === check.condition_id); const evidence = Array.isArray(check.evidence) && check.evidence.length ? check.evidence.map(item => text(record(item).source_id, text(record(item).source_kind, '受治理证据'))).join('、') : text(source.evidence_label, check.safe_reason ?? '受治理证据'); return <tr key={check.id} className="border-t border-border"><th scope="row" className="p-2 font-normal">{CHECK_LABELS[check.result]}</th><td className="p-2">{text(record(condition).name, condition?.description || check.condition_id)}</td><td className="p-2">{dateTime(check.due_at)}</td><td className="p-2">{dateTime(check.checked_at)}</td><td className="p-2 font-mono">{check.observed_value == null ? '—' : `${check.observed_value} ${text(source.unit, condition?.unit ?? '')}`}</td><td className="p-2"><span>{evidence}</span><span className="mt-1 block break-words font-mono [overflow-wrap:anywhere]">{check.evidence_fingerprint}</span></td><td className="p-2">{typeof check.version === 'number' ? `版本 ${check.version}` : version ? `版本 ${version.version}` : check.version_id}</td><td className="p-2">{text(source.cadence, condition?.cadence ?? '—')}</td></tr> }) : <tr><td colSpan={8} className="p-4 text-center text-secondary">尚无追加式检查记录。</td></tr>}</tbody></table></div></>
}

function VersionsTable({ versions, currentVersionId, selectedVersionId, onSelect }: { versions: ThesisVersion[]; currentVersionId: string | null; selectedVersionId: string | null; onSelect: (id: string) => void }) {
  const descriptionId = useId()
  return <section aria-labelledby={`${descriptionId}-heading`} className="space-y-2"><h3 id={`${descriptionId}-heading`} className="text-base font-semibold">不可变版本时间线</h3><p id={descriptionId} className="text-xs text-secondary">左右滚动查看完整记录</p><div tabIndex={0} aria-describedby={descriptionId} className={`overflow-x-auto ${FOCUS}`}><table className="min-w-[800px] w-full text-left text-xs"><caption className="sr-only">投资论点版本历史</caption><thead className="bg-elevated text-secondary"><tr><th scope="col" className="p-2">编号</th><th scope="col" className="p-2">前序记录</th><th scope="col" className="p-2">创建时间</th><th scope="col" className="p-2">变更理由</th><th scope="col" className="p-2">估值锚 / 条件</th><th scope="col" className="p-2">当时官方状态</th><th scope="col" className="p-2">详情</th></tr></thead><tbody>{versions.map(version => <tr key={version.id} className={`border-t border-border ${version.id === selectedVersionId ? 'bg-accent/5' : ''}`}><th scope="row" className="p-2 font-normal">版本 {version.version}{version.id === currentVersionId ? '（当前）' : ''}</th><td className="p-2 font-mono">{version.predecessor_id ?? '首版'}</td><td className="p-2">{dateTime(version.created_at)}</td><td className="max-w-[40ch] break-words p-2">{version.change_reason}</td><td className="p-2">{version.anchors.length} / {version.conditions.length}</td><td className="p-2">{officialState(version)}</td><td className="p-2"><button type="button" onClick={() => onSelect(version.id)} className={`${BUTTON} min-h-0 py-2 text-accent underline`}>查看完整版本</button></td></tr>)}</tbody></table></div></section>
}

function ThesisHistoryTable({ items }: { items: ThesisPending[] }) {
  const descriptionId = useId()
  const stateLabel = (item: ThesisPending) => {
    const state = item.state ?? item.status
    if (state === 'actionable' || state === 'pending') return '待确认'
    if (state === 'superseded') return '已被后续版本取代'
    if (state === 'confirmed') return '已确认'
    if (state === 'rejected') return '已驳回'
    return state
  }
  return <section aria-labelledby={`${descriptionId}-heading`} className="space-y-2"><h3 id={`${descriptionId}-heading`} className="text-base font-semibold">不可变论点结论历史</h3><p id={descriptionId} className="text-xs text-secondary">左右滚动查看完整记录。待确认、已取代与人工决定均只读保留。</p><div tabIndex={0} aria-describedby={descriptionId} className={`overflow-x-auto ${FOCUS}`}><table className="min-w-[760px] w-full text-left text-xs"><caption className="sr-only">不可变论点结论历史</caption><thead className="bg-elevated text-secondary"><tr><th scope="col" className="p-2">记录</th><th scope="col" className="p-2">状态</th><th scope="col" className="p-2">版本 / 条件</th><th scope="col" className="p-2">证据</th><th scope="col" className="p-2">创建时间</th></tr></thead><tbody>{items.length ? items.map(item => <tr key={item.id} className="border-t border-border"><th scope="row" className="p-2 font-mono font-normal">{item.id}</th><td className="p-2">{stateLabel(item)}</td><td className="p-2">{typeof item.version === 'number' ? `版本 ${item.version}` : item.version_id} / {item.condition_id}</td><td className="p-2 font-mono [overflow-wrap:anywhere]">{item.evidence_fingerprint}</td><td className="p-2">{dateTime(item.created_at)}</td></tr>) : <tr><td colSpan={5} className="p-3 text-secondary">暂无不可变论点结论历史。</td></tr>}</tbody></table></div></section>
}

function VersionForm({ draft, setDraft, error, errorTarget, reviewing, lowRef, firstFieldRef, onReview, onCancel, onConfirm }: { draft: VersionDraft; setDraft: React.Dispatch<React.SetStateAction<VersionDraft>>; error: string | null; errorTarget: string | null; reviewing: boolean; lowRef: React.RefObject<HTMLInputElement>; firstFieldRef: React.RefObject<HTMLTextAreaElement>; onReview: () => void; onCancel: () => void; onConfirm: () => void }) {
  const [dependencyStatus, setDependencyStatus] = useState('')
  const updateAnchor = (index: number, field: keyof Omit<AnchorDraft, 'assumptions' | 'limitations'>, value: string) => setDraft(current => ({ ...current, anchors: current.anchors.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item) }))
  const updateAssumption = (anchorIndex: number, assumptionIndex: number, field: keyof AssumptionDraft, value: string) => setDraft(current => ({ ...current, anchors: current.anchors.map((anchor, itemIndex) => itemIndex === anchorIndex ? { ...anchor, assumptions: anchor.assumptions.map((assumption, valueIndex) => valueIndex === assumptionIndex ? { ...assumption, [field]: value } : assumption) } : anchor) }))
  const updateLimitation = (anchorIndex: number, limitationIndex: number, value: string) => setDraft(current => ({ ...current, anchors: current.anchors.map((anchor, itemIndex) => itemIndex === anchorIndex ? { ...anchor, limitations: anchor.limitations.map((limitation, valueIndex) => valueIndex === limitationIndex ? value : limitation) } : anchor) }))
  const updateCondition = (index: number, field: keyof ConditionDraft, value: string) => setDraft(current => ({ ...current, conditions: current.conditions.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item) }))
  const fieldProps = (id: string) => ({
    id,
    'aria-invalid': errorTarget === id ? true : undefined,
    'aria-describedby': error && errorTarget === id ? FORM_ERROR_ID : undefined,
  })
  const changeSource = (index: number, sourceKind: ThesisSourceKind) => {
    const registry = CONDITION_REGISTRY[sourceKind]
    const field = registry.fields[0]
    setDraft(current => ({
      ...current,
      conditions: current.conditions.map((item, itemIndex) => itemIndex === index ? {
        ...item,
        sourceKind,
        field: field.value,
        unit: field.units[0],
        operator: registry.operators[0],
        threshold: '',
      } : item),
    }))
    setDependencyStatus(`条件 ${index + 1} 来源已改为${SOURCE_LABELS[sourceKind]}；字段、单位、运算符和阈值已按兼容选项重置。`)
  }
  const changeField = (index: number, value: string) => {
    setDraft(current => ({
      ...current,
      conditions: current.conditions.map((item, itemIndex) => {
        if (itemIndex !== index) return item
        const field = CONDITION_REGISTRY[item.sourceKind].fields.find(candidate => candidate.value === value)
        return field ? { ...item, field: value, unit: field.units[0], threshold: '' } : item
      }),
    }))
    setDependencyStatus(`条件 ${index + 1} 字段已更新；单位和阈值已同步为兼容值。`)
  }
  const changeOperator = (index: number, operator: ThesisConditionOperator) => {
    setDraft(current => ({
      ...current,
      conditions: current.conditions.map((item, itemIndex) => itemIndex === index
        ? { ...item, operator, threshold: '' }
        : item),
    }))
    setDependencyStatus(`条件 ${index + 1} 运算符已更新；阈值已清空，请重新填写。`)
  }
  return <section aria-labelledby="thesis-version-form" className="space-y-4 rounded-card border border-border bg-elevated p-4"><h3 id="thesis-version-form" className="text-base font-semibold">创建下一版不可变论点</h3>{error && <div id={FORM_ERROR_ID} role="alert" className="rounded-input bg-danger/10 p-4 text-danger">{error}</div>}
    {dependencyStatus && <p role="status" aria-live="polite" className="rounded-input border border-border bg-surface p-4 text-secondary">{dependencyStatus}</p>}
    <div className="grid gap-4 lg:grid-cols-2"><label htmlFor="thesis-core-judgment">核心判断<textarea {...fieldProps('thesis-core-judgment')} ref={firstFieldRef} value={draft.coreJudgment} onChange={event => setDraft(current => ({ ...current, coreJudgment: event.target.value }))} className={`${INPUT} mt-1 min-h-28`} /></label><label htmlFor="thesis-rationale">判断理由<textarea {...fieldProps('thesis-rationale')} value={draft.rationale} onChange={event => setDraft(current => ({ ...current, rationale: event.target.value }))} className={`${INPUT} mt-1 min-h-28`} /></label></div>
    {draft.anchors.map((anchor, anchorIndex) => {
      const methodOptions = VALUATION_METHODS.some(item => item.value === anchor.method)
        ? VALUATION_METHODS
        : [{ value: anchor.method, label: valuationMethodLabel(anchor.method) }, ...VALUATION_METHODS]
      return <fieldset key={anchorIndex} className="grid gap-4 rounded-card border border-border p-4 sm:grid-cols-2 lg:grid-cols-4"><legend className="px-1 font-normal">估值锚 {anchorIndex + 1}</legend><label htmlFor={`thesis-anchor-${anchorIndex}-method`}>估值方法<select {...fieldProps(`thesis-anchor-${anchorIndex}-method`)} value={anchor.method} onChange={event => updateAnchor(anchorIndex, 'method', event.target.value)} className={`${INPUT} mt-1`}>{methodOptions.map(method => <option key={method.value} value={method.value}>{method.label}</option>)}</select></label><label htmlFor={`thesis-anchor-${anchorIndex}-currency`}>估值币种<input {...fieldProps(`thesis-anchor-${anchorIndex}-currency`)} value={anchor.currency} onChange={event => updateAnchor(anchorIndex, 'currency', event.target.value)} className={`${INPUT} mt-1`} /></label><label htmlFor={`thesis-anchor-${anchorIndex}-as-of`}>估值截至日<input {...fieldProps(`thesis-anchor-${anchorIndex}-as-of`)} type="date" value={anchor.asOf} onChange={event => updateAnchor(anchorIndex, 'asOf', event.target.value)} className={`${INPUT} mt-1`} /></label><span /><label htmlFor={`thesis-anchor-${anchorIndex}-low`}>估值下限<input {...fieldProps(`thesis-anchor-${anchorIndex}-low`)} ref={anchorIndex === 0 ? lowRef : undefined} type="number" value={anchor.low} onChange={event => updateAnchor(anchorIndex, 'low', event.target.value)} className={`${INPUT} mt-1`} /></label><label htmlFor={`thesis-anchor-${anchorIndex}-high`}>估值上限<input {...fieldProps(`thesis-anchor-${anchorIndex}-high`)} type="number" value={anchor.high} onChange={event => updateAnchor(anchorIndex, 'high', event.target.value)} className={`${INPUT} mt-1`} /></label>{anchor.assumptions.map((assumption, assumptionIndex) => <div key={assumptionIndex} className="contents"><label htmlFor={`thesis-anchor-${anchorIndex}-assumption-${assumptionIndex}-name`} className="sm:col-span-2">估值假设 {assumptionIndex + 1}<input {...fieldProps(`thesis-anchor-${anchorIndex}-assumption-${assumptionIndex}-name`)} value={assumption.name} onChange={event => updateAssumption(anchorIndex, assumptionIndex, 'name', event.target.value)} placeholder="revenue_growth" className={`${INPUT} mt-1`} /></label><label htmlFor={`thesis-anchor-${anchorIndex}-assumption-${assumptionIndex}-value`}>假设数值<input {...fieldProps(`thesis-anchor-${anchorIndex}-assumption-${assumptionIndex}-value`)} type="number" value={assumption.value} onChange={event => updateAssumption(anchorIndex, assumptionIndex, 'value', event.target.value)} className={`${INPUT} mt-1`} /></label><label htmlFor={`thesis-anchor-${anchorIndex}-assumption-${assumptionIndex}-unit`}>假设单位<input {...fieldProps(`thesis-anchor-${anchorIndex}-assumption-${assumptionIndex}-unit`)} value={assumption.unit} onChange={event => updateAssumption(anchorIndex, assumptionIndex, 'unit', event.target.value)} placeholder="percent" className={`${INPUT} mt-1`} /></label></div>)}{anchor.limitations.map((limitation, limitationIndex) => <label key={limitationIndex} htmlFor={`thesis-anchor-${anchorIndex}-limitation-${limitationIndex}`} className="sm:col-span-2">估值限制 {limitationIndex + 1}<input {...fieldProps(`thesis-anchor-${anchorIndex}-limitation-${limitationIndex}`)} value={limitation} onChange={event => updateLimitation(anchorIndex, limitationIndex, event.target.value)} className={`${INPUT} mt-1`} /></label>)}</fieldset>
    })}
    <fieldset className="space-y-4 rounded-card border border-border p-4"><legend className="px-1 font-normal">结构化失效条件与独立检查周期</legend>{draft.conditions.map((condition, index) => {
      const registry = CONDITION_REGISTRY[condition.sourceKind]
      const selectedField = registry.fields.find(item => item.value === condition.field) ?? registry.fields[0]
      return <div key={index} className="grid gap-4 border-t border-border pt-4 first:border-t-0 first:pt-0 sm:grid-cols-2 lg:grid-cols-4"><label htmlFor={`thesis-condition-${index}-description`}>条件 {index + 1} 说明<input {...fieldProps(`thesis-condition-${index}-description`)} value={condition.description} onChange={event => updateCondition(index, 'description', event.target.value)} className={`${INPUT} mt-1`} /></label><label htmlFor={`thesis-condition-${index}-field`}>字段<select {...fieldProps(`thesis-condition-${index}-field`)} value={selectedField.value} onChange={event => changeField(index, event.target.value)} className={`${INPUT} mt-1`}>{registry.fields.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label htmlFor={`thesis-condition-${index}-threshold`}>阈值<input {...fieldProps(`thesis-condition-${index}-threshold`)} value={condition.threshold} onChange={event => updateCondition(index, 'threshold', event.target.value)} className={`${INPUT} mt-1`} /></label><label htmlFor={`thesis-condition-${index}-unit`}>单位<select {...fieldProps(`thesis-condition-${index}-unit`)} value={condition.unit} onChange={event => updateCondition(index, 'unit', event.target.value)} className={`${INPUT} mt-1`}>{selectedField.units.map(unit => <option key={unit} value={unit}>{unit}</option>)}</select></label><label htmlFor={`thesis-condition-${index}-cadence`}>条件 {index + 1} 检查周期<select {...fieldProps(`thesis-condition-${index}-cadence`)} value={condition.cadence} onChange={event => updateCondition(index, 'cadence', event.target.value)} className={`${INPUT} mt-1`}>{CADENCES.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label htmlFor={`thesis-condition-${index}-lookback`}>lookback（日）<input {...fieldProps(`thesis-condition-${index}-lookback`)} type="number" min="1" value={condition.lookbackDays} onChange={event => updateCondition(index, 'lookbackDays', event.target.value)} className={`${INPUT} mt-1`} /></label><label htmlFor={`thesis-condition-${index}-source`}>来源类型<select {...fieldProps(`thesis-condition-${index}-source`)} value={condition.sourceKind} onChange={event => changeSource(index, event.target.value as ThesisSourceKind)} className={`${INPUT} mt-1`}>{Object.entries(SOURCE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label htmlFor={`thesis-condition-${index}-operator`}>运算符<select {...fieldProps(`thesis-condition-${index}-operator`)} value={condition.operator} onChange={event => changeOperator(index, event.target.value as ThesisConditionOperator)} className={`${INPUT} mt-1`}>{registry.operators.map(operator => <option key={operator} value={operator}>{OPERATOR_LABELS[operator]}</option>)}</select></label></div>
    })}</fieldset>
    <label htmlFor="thesis-change-reason">版本变更理由<textarea {...fieldProps('thesis-change-reason')} value={draft.changeReason} onChange={event => setDraft(current => ({ ...current, changeReason: event.target.value }))} className={`${INPUT} mt-1 min-h-20`} /></label>
    {reviewing && <div className="rounded-card border border-accent/40 bg-accent/5 p-4"><h4 className="font-semibold">创建前审阅摘要</h4><p className="mt-1">核心判断、{draft.anchors.length} 个估值区间、{draft.conditions.length} 个结构化条件与各自检查周期将写入新版本；旧版本和检查历史保持不变。</p></div>}
    <div className="flex flex-wrap justify-end gap-2"><button type="button" onClick={onCancel} className={`${BUTTON} border border-border`}>暂不处理</button>{reviewing ? <button type="button" onClick={onConfirm} className={`${BUTTON} bg-accent-solid font-semibold text-white`}>创建不可变论点版本</button> : <button type="button" onClick={onReview} className={`${BUTTON} bg-accent-solid font-semibold text-white`}>进入审阅</button>}</div>
  </section>
}

function ReviewDialog({ target, instrumentTitle, versions, rationale, setRationale, mutation, onClose }: { target: { pending: ThesisPending; action: ReviewAction }; instrumentTitle: string; versions: ThesisVersion[]; rationale: string; setRationale: (value: string) => void; mutation: ReturnType<typeof useMutation<{ review: unknown; official_status: string }, Error, { pending: ThesisPending; action: ReviewAction }>>; onClose: () => void }) {
  const version = versions.find(item => item.id === target.pending.version_id)
  const title = target.action === 'confirm' ? '确认论点失效' : '驳回待确认结论'
  const normalizedTitle = instrumentTitle.replace(/（([^）]+)）/, '（$1）')
  return <FocusDialog title={title} initialFocus="textarea" onClose={onClose}>
    <p>{target.action === 'confirm' ? `确认将 ${normalizedTitle}的论点版本 ${version?.version ?? target.pending.version ?? target.pending.version_id} 记录为已失效？命中条件与证据会永久保留；此操作不会执行交易或修改其他研究对象。` : '驳回后，当前官方状态保持不变；条件、检查记录和证据仍会永久保留。'}</p>
    <label className="mt-4 block">{target.action === 'confirm' ? '确认理由（至少 10 个字符）' : '驳回理由（至少 10 个字符）'}<textarea data-dialog-textarea value={rationale} onChange={event => setRationale(event.target.value)} className={`${INPUT} mt-1 min-h-28`} /></label>
    {mutation.isError && !(mutation.error instanceof ApiRequestError && mutation.error.status === 409) && <div role="alert" className="mt-4 rounded-input bg-danger/10 p-4 text-danger"><strong>无法确认论点操作结果</strong><p>确认或驳回请求的传输状态不确定：{errorReason(mutation.error)}。已填写的理由保留。</p><p>不得假定服务端未处理本次请求；重试前必须重新读取当前论点及待确认结论，并以服务端当前记录为准。</p></div>}
    <div className="mt-4 flex flex-wrap justify-end gap-2"><button type="button" onClick={onClose} className={`${BUTTON} border border-border`}>暂不处理</button><button type="button" onClick={() => mutation.mutate(target)} disabled={rationale.trim().length < 10 || mutation.isPending} className={`${BUTTON} ${target.action === 'confirm' ? 'bg-danger text-white' : 'bg-accent-solid text-white'} font-semibold disabled:opacity-50`}>{mutation.isPending ? '正在记录人工决定…' : title}</button></div>
  </FocusDialog>
}

function FocusDialog({ title, initialFocus, onClose, children }: { title: string; initialFocus: 'textarea' | 'cancel'; onClose: () => void; children: React.ReactNode }) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const returnFocus = useRef(document.activeElement as HTMLElement | null)
  useEffect(() => {
    const restoreFocus = returnFocus.current
    const selector = initialFocus === 'textarea' ? '[data-dialog-textarea]' : '[data-dialog-cancel]'
    requestAnimationFrame(() => dialogRef.current?.querySelector<HTMLElement>(selector)?.focus())
    return () => restoreFocus?.focus()
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
