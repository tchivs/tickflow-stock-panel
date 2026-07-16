import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, FileUp, LoaderCircle, ShieldCheck } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode, type RefObject } from 'react'
import { ApiRequestError } from '@/lib/api'
import {
  phase5Api,
  type SafeJson,
  type ShadowBatch,
  type ShadowCandidate,
  type ShadowEvaluation,
  type ShadowEvaluationSummary,
  type ShadowImportMapping,
  type ShadowRule,
} from '@/lib/phase5Api'
import { QK } from '@/lib/queryKeys'

const PAGE_SIZE = 50
const CONTROL_CLASS = 'min-h-11 rounded-input border border-border bg-base px-3 py-2 text-sm text-foreground transition-colors duration-150 ease-smooth focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none'
const BUTTON_CLASS = 'inline-flex min-h-11 items-center justify-center gap-2 rounded-btn border border-border bg-base px-3 py-2 text-sm text-foreground transition-colors duration-150 ease-smooth hover:bg-elevated focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none'
const PRIMARY_CLASS = `${BUTTON_CLASS} border-accent bg-accent font-semibold text-white hover:bg-accent/90`
const TABLE_HEADER_CLASS = 'border-b border-border bg-elevated/60 text-left text-xs font-normal text-secondary'
const TABLE_CELL_CLASS = 'border-b border-border/60 px-3 py-2 align-top text-xs'

const DEFAULT_MAPPING: ShadowImportMapping = {
  symbol: 'symbol',
  side: 'side',
  executed_at: 'time',
  quantity: 'quantity',
  price: 'price',
  fees: 'fees',
  currency: 'currency',
  broker_fill_id: 'fill_id',
}

const MAPPING_FIELDS: Array<{ key: keyof ShadowImportMapping; label: string; required: boolean; unit: string }> = [
  { key: 'symbol', label: '标的', required: true, unit: '市场代码' },
  { key: 'side', label: '方向', required: true, unit: '买入/卖出' },
  { key: 'executed_at', label: '成交时间', required: true, unit: 'Asia/Shanghai' },
  { key: 'quantity', label: '数量', required: true, unit: '股' },
  { key: 'price', label: '价格', required: true, unit: '每股价格' },
  { key: 'fees', label: '费用', required: false, unit: '币种金额' },
  { key: 'currency', label: '币种', required: false, unit: 'ISO 币种' },
  { key: 'broker_fill_id', label: '成交 ID', required: false, unit: '来源标识' },
]

interface ConfirmationDialogProps {
  open: boolean
  title: string
  description: ReactNode
  confirmLabel: string
  pending: boolean
  triggerRef: RefObject<HTMLButtonElement | null>
  children?: ReactNode
  onClose: () => void
  onConfirm: () => void
}

function ConfirmationDialog({ open, title, description, confirmLabel, pending, triggerRef, children, onClose, onConfirm }: ConfirmationDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const cancelRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (open) cancelRef.current?.focus()
  }, [open])

  if (!open) return null

  const close = () => {
    onClose()
    requestAnimationFrame(() => triggerRef.current?.focus())
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      close()
      return
    }
    if (event.key !== 'Tab' || !dialogRef.current) return
    const controls = Array.from(dialogRef.current.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'))
    if (!controls.length) return
    const first = controls[0]
    const last = controls[controls.length - 1]
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="shadow-confirmation-title" className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" onKeyDown={handleKeyDown}>
      <div ref={dialogRef} className="max-h-[calc(100vh-2rem)] w-full max-w-xl overflow-y-auto rounded-dialog border border-border bg-surface p-5">
        <h3 id="shadow-confirmation-title" className="text-base font-semibold text-foreground">{title}</h3>
        <div className="mt-3 max-w-[70ch] text-sm leading-relaxed text-secondary">{description}</div>
        {children}
        <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <button ref={cancelRef} type="button" className={BUTTON_CLASS} onClick={close}>返回审阅</button>
          <button type="button" className={PRIMARY_CLASS} disabled={pending} onClick={onConfirm}>{pending ? '正在记录…' : confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}

function safeReason(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  return '请求未完成'
}

function displayTime(value: string | undefined): string {
  if (!value) return '未记录'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function boundedJson(value: SafeJson | undefined): string {
  if (value === undefined || value === null) return '未提供'
  const text = JSON.stringify(value)
  return text.length > 2_000 ? `${text.slice(0, 2_000)}…` : text
}

function statusText(status: string): string {
  if (status === 'completed') return '已完成'
  if (status === 'passed') return '通过'
  if (status === 'failed') return '未通过'
  if (status === 'retained_research_only') return '已保留为研究候选'
  if (status === 'timeout') return 'timeout（超时终止）'
  if (status === 'resource_terminated') return 'resource_terminated（资源终止）'
  return status || '未记录'
}

function percent(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : '未提供'
}

function decimal(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(4) : '未提供'
}

function batchCounts(batch: ShadowBatch): { total: number; valid: number; invalid: number } {
  return {
    total: batch.total_rows ?? batch.source_row_count,
    valid: batch.valid_rows ?? batch.normalized_row_count,
    invalid: batch.invalid_rows ?? batch.rejected_row_count,
  }
}

function candidateRules(candidate: ShadowCandidate): ShadowRule[] {
  return Array.isArray(candidate.rules) ? candidate.rules.filter((rule): rule is ShadowRule => typeof rule === 'object' && rule !== null && !Array.isArray(rule)) : []
}

function ruleExpression(rule: ShadowRule): string {
  if (rule.if) return `${rule.if}${rule.then ? ` → ${rule.then}` : ''}`
  const conditions = rule.conditions?.map(condition => `${condition.field ?? '字段'} ${condition.operator ?? ''} ${condition.threshold ?? ''}`).join(' 且 ')
  return `${conditions || '规则未提供'}${rule.prediction ? ` → ${rule.prediction}` : ''}`
}

interface RenderEvaluation {
  id: string
  split: 'in_sample' | 'out_of_sample'
  status: string
  start: string
  end: string
  precision?: number | null
  recall?: number | null
  coverage?: number | null
  trades?: number | null
  totalReturn?: number | null
  drawdown?: number | null
  costs?: number | null
  afterCost?: number | null
  consistency?: number | null
  adjustment?: string | null
  artifact?: string
  terminalReason?: string | null
}

function windowValue(value: SafeJson, key: string): string {
  return value && typeof value === 'object' && !Array.isArray(value) && typeof value[key] === 'string' ? value[key] : '未提供'
}

function evaluationRow(evaluation: ShadowEvaluation): RenderEvaluation {
  return {
    id: evaluation.id,
    split: evaluation.split_kind === 'out_of_sample' ? 'out_of_sample' : 'in_sample',
    status: evaluation.status,
    start: windowValue(evaluation.window, 'start'),
    end: windowValue(evaluation.window, 'end'),
    precision: evaluation.metrics.precision,
    recall: evaluation.metrics.recall,
    coverage: evaluation.metrics.coverage,
    trades: evaluation.metrics.candidate_trades,
    totalReturn: evaluation.metrics.total_return,
    drawdown: evaluation.metrics.max_drawdown,
    costs: evaluation.metrics.costs,
    consistency: evaluation.metrics.actual_trade_consistency,
    adjustment: evaluation.adjustment_policy,
    artifact: evaluation.artifact.artifact_id,
    terminalReason: evaluation.terminal_reason,
  }
}

function embeddedEvaluationRow(split: RenderEvaluation['split'], summary: ShadowEvaluationSummary): RenderEvaluation {
  return {
    id: summary.run_id ?? `${split}-embedded`,
    split,
    status: summary.status ?? 'unknown',
    start: summary.start ?? '未提供',
    end: summary.end ?? '未提供',
    precision: summary.precision,
    recall: summary.recall,
    coverage: summary.coverage,
    trades: summary.trades,
    totalReturn: summary.return,
    drawdown: summary.drawdown,
    afterCost: summary.after_cost,
    consistency: summary.actual_consistency,
  }
}

function Pagination({ page, offset, onOffset }: { page: { has_more: boolean; total: number } | undefined; offset: number; onOffset: (offset: number) => void }) {
  if (!page || (offset === 0 && !page.has_more)) return null
  return (
    <nav aria-label="Shadow 历史分页" className="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs text-secondary">
      <span>共 {page.total} 条不可变记录；当前从第 {offset + 1} 条开始。</span>
      <div className="flex gap-2">
        <button type="button" className={BUTTON_CLASS} disabled={offset === 0} onClick={() => onOffset(Math.max(0, offset - PAGE_SIZE))}>上一页</button>
        <button type="button" className={BUTTON_CLASS} disabled={!page.has_more} onClick={() => onOffset(offset + PAGE_SIZE)}>下一页</button>
      </div>
    </nav>
  )
}

function OverflowTable({ instructionId, children }: { instructionId: string; children: ReactNode }) {
  return (
    <>
      <p id={instructionId} className="mb-2 text-xs text-secondary">左右滚动查看完整记录</p>
      <div className="overflow-x-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface" tabIndex={0} aria-describedby={instructionId}>
        {children}
      </div>
    </>
  )
}

export function ShadowAccount() {
  const queryClient = useQueryClient()
  const [batchOffset, setBatchOffset] = useState(0)
  const [evidenceOffset, setEvidenceOffset] = useState(0)
  const [candidateOffset, setCandidateOffset] = useState(0)
  const [evaluationOffset, setEvaluationOffset] = useState(0)
  const [retentionOffset, setRetentionOffset] = useState(0)
  const [file, setFile] = useState<File | null>(null)
  const [mapping, setMapping] = useState<ShadowImportMapping>(DEFAULT_MAPPING)
  const [sourceTimezone, setSourceTimezone] = useState('Asia/Shanghai')
  const [sourceLabel, setSourceLabel] = useState('本地券商导出')
  const [selectedBatchIds, setSelectedBatchIds] = useState<Set<string>>(() => new Set())
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null)
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null)
  const [importConfirmationOpen, setImportConfirmationOpen] = useState(false)
  const [retainConfirmationOpen, setRetainConfirmationOpen] = useState(false)
  const [statusMessage, setStatusMessage] = useState<string | null>(null)
  const [retentionRationale, setRetentionRationale] = useState('保留为只读 Shadow 研究候选，继续审阅其证据边界。')
  const [inSampleStart, setInSampleStart] = useState('2024-01-02')
  const [inSampleEnd, setInSampleEnd] = useState('2024-06-28')
  const [outSampleStart, setOutSampleStart] = useState('2024-07-01')
  const [outSampleEnd, setOutSampleEnd] = useState('2024-12-31')
  const importTriggerRef = useRef<HTMLButtonElement>(null)
  const retainTriggerRef = useRef<HTMLButtonElement>(null)
  const errorRef = useRef<HTMLDivElement>(null)

  const capabilityQuery = useQuery({ queryKey: QK.phase5Capabilities, queryFn: phase5Api.capabilities, placeholderData: keepPreviousData })
  const batchesQuery = useQuery({ queryKey: QK.shadow.batches(batchOffset, PAGE_SIZE), queryFn: () => phase5Api.shadowBatches(batchOffset, PAGE_SIZE), placeholderData: keepPreviousData })
  const evidenceQuery = useQuery({ queryKey: QK.shadow.evidenceSets(evidenceOffset, PAGE_SIZE), queryFn: () => phase5Api.shadowEvidenceSets(evidenceOffset, PAGE_SIZE), placeholderData: keepPreviousData })
  const candidatesQuery = useQuery({ queryKey: QK.shadow.candidates(candidateOffset, PAGE_SIZE), queryFn: () => phase5Api.shadowCandidates(candidateOffset, PAGE_SIZE), placeholderData: keepPreviousData })
  const evaluationsQuery = useQuery({ queryKey: QK.shadow.evaluations(null, evaluationOffset, PAGE_SIZE), queryFn: () => phase5Api.shadowEvaluations(undefined, evaluationOffset, PAGE_SIZE), placeholderData: keepPreviousData })
  const retentionsQuery = useQuery({ queryKey: QK.shadow.retentions(null, retentionOffset, PAGE_SIZE), queryFn: () => phase5Api.shadowRetentions(undefined, retentionOffset, PAGE_SIZE), placeholderData: keepPreviousData })

  const capability = capabilityQuery.data?.modules?.shadow
  const batches = Array.isArray(batchesQuery.data?.batches) ? batchesQuery.data.batches : []
  const evidenceSets = Array.isArray(evidenceQuery.data?.evidence_sets) ? evidenceQuery.data.evidence_sets : []
  const candidates = Array.isArray(candidatesQuery.data?.candidates) ? candidatesQuery.data.candidates : []
  const evaluations = Array.isArray(evaluationsQuery.data?.evaluations) ? evaluationsQuery.data.evaluations : []
  const retentions = Array.isArray(retentionsQuery.data?.retentions) ? retentionsQuery.data.retentions : []
  const currentEvidence = evidenceSets.find(item => item.id === selectedEvidenceId) ?? evidenceSets[0] ?? null
  const currentCandidate = candidates.find(item => item.id === selectedCandidateId) ?? candidates[0] ?? null
  const actualEvaluationRows = currentCandidate ? evaluations.filter(item => item.candidate_id === currentCandidate.id).map(evaluationRow) : []
  const embeddedEvaluationRows = currentCandidate ? [
    ...(currentCandidate.in_sample ? [embeddedEvaluationRow('in_sample', currentCandidate.in_sample)] : []),
    ...(currentCandidate.out_of_sample ? [embeddedEvaluationRow('out_of_sample', currentCandidate.out_of_sample)] : []),
  ] : []
  const evaluationRows = actualEvaluationRows.length ? actualEvaluationRows : embeddedEvaluationRows
  const inSample = evaluationRows.find(item => item.split === 'in_sample')
  const outOfSample = evaluationRows.find(item => item.split === 'out_of_sample')
  const retainable = inSample?.status === 'passed' && outOfSample?.status === 'passed'
  const retained = currentCandidate ? retentions.find(item => item.candidate_id === currentCandidate.id) : undefined
  const newestBatchTime = batches[0]?.created_at ? Date.parse(batches[0].created_at) : 0
  const evidenceTime = currentEvidence?.created_at ? Date.parse(currentEvidence.created_at) : 0
  const staleEvidence = Boolean(currentCandidate && currentEvidence && batches[0] && (newestBatchTime > evidenceTime || !currentEvidence.included_batch_ids.includes(batches[0].id)))
  const loadFailed = batchesQuery.isError || evidenceQuery.isError || candidatesQuery.isError || evaluationsQuery.isError || retentionsQuery.isError

  const invalidateBatches = () => queryClient.invalidateQueries({ queryKey: QK.shadow.batches() })
  const invalidateEvidence = () => queryClient.invalidateQueries({ queryKey: QK.shadow.evidenceSets() })
  const invalidateCandidates = () => queryClient.invalidateQueries({ queryKey: QK.shadow.candidates() })
  const invalidateEvaluations = () => queryClient.invalidateQueries({ queryKey: QK.shadow.evaluations(null) })
  const invalidateRetentions = () => queryClient.invalidateQueries({ queryKey: QK.shadow.retentions(null) })

  const previewImport = useMutation({
    mutationFn: phase5Api.shadowPreviewImport,
    onSuccess: preview => setStatusMessage(`已解析 ${file?.name ?? '成交日志'}；预览 ${preview.sample_rows.length || preview.rows?.length || 0} 行。`),
    onError: () => requestAnimationFrame(() => errorRef.current?.focus()),
  })
  const confirmImport = useMutation({
    mutationFn: phase5Api.shadowConfirmImport,
    onSuccess: ({ batch }) => {
      setImportConfirmationOpen(false)
      setStatusMessage(`不可变批次 ${batch.label ?? batch.id} 已追加；旧批次未改变。`)
      setSelectedBatchIds(new Set([batch.id]))
      void invalidateBatches()
    },
  })
  const createEvidence = useMutation({
    mutationFn: phase5Api.shadowCreateEvidenceSet,
    onSuccess: ({ evidence_set }) => {
      setSelectedEvidenceId(evidence_set.id)
      setStatusMessage(`证据集已冻结：${evidence_set.id}。后续变更需创建新证据集。`)
      void invalidateEvidence()
    },
  })
  const distillCandidate = useMutation({
    mutationFn: ({ evidenceSetId }: { evidenceSetId: string }) => phase5Api.shadowDistill(evidenceSetId, {
      feature_names: ['close_return_5d', 'volume_ratio_20d', 'intraday_range'],
      max_depth: 3,
      min_samples_leaf: 20,
      min_support: 10,
      min_precision: 0.55,
      seed: 17,
      training_window: { start: inSampleStart, end: outSampleEnd },
      exit_assumptions: { max_holding_sessions: 20, exit_on_rule_break: true },
      holding_assumptions: { position_sizing: 'equal_weight', overlapping_positions: false },
    }),
    onSuccess: ({ candidate }) => {
      setSelectedCandidateId(candidate.id)
      setStatusMessage(`已创建可解释候选 ${candidate.label ?? candidate.id}。`)
      void invalidateCandidates()
    },
  })
  const evaluateCandidate = useMutation({
    mutationFn: ({ evidenceSetId, candidateId }: { evidenceSetId: string; candidateId: string }) => phase5Api.shadowEvaluate(evidenceSetId, candidateId, {
      in_sample_window: { start: inSampleStart, end: inSampleEnd },
      out_of_sample_window: { start: outSampleStart, end: outSampleEnd },
      adjustment_policy: 'governed_adjusted_daily',
      cost_policy: { commission_bps: 3, slippage_bps: 5, stamp_duty_bps: 5 },
    }),
    onSuccess: () => {
      setStatusMessage('样本内与样本外评估已分别记录。')
      void Promise.all([invalidateEvaluations(), invalidateCandidates()])
    },
  })
  const retryEvaluation = useMutation({
    mutationFn: phase5Api.shadowRetryEvaluation,
    onSuccess: () => {
      setStatusMessage('已创建新的评估运行；失败运行保持只读。')
      void invalidateEvaluations()
    },
  })
  const retainCandidate = useMutation({
    mutationFn: ({ evidenceSetId, candidateId, inSampleId, outSampleId }: { evidenceSetId: string; candidateId: string; inSampleId: string; outSampleId: string }) => phase5Api.shadowRetain(evidenceSetId, candidateId, {
      in_sample_evaluation_id: inSampleId,
      out_of_sample_evaluation_id: outSampleId,
      rationale: retentionRationale,
    }),
    onSuccess: () => {
      setRetainConfirmationOpen(false)
      setStatusMessage('Shadow 研究候选已保留；未注册或启用策略。')
      void invalidateRetentions()
    },
  })

  const chooseFile = (nextFile: File | null) => {
    setFile(nextFile)
    if (!nextFile) return
    setStatusMessage(`已选择 ${nextFile.name}（${Math.ceil(nextFile.size / 1024)} KB），正在解析日志…`)
    previewImport.mutate({ file: nextFile, mapping, source_timezone: sourceTimezone })
  }

  const evidenceBatchIds = selectedBatchIds.size ? Array.from(selectedBatchIds) : batches.filter(batch => batch.status === 'completed').slice(0, 1).map(batch => batch.id)

  return (
    <section role="region" aria-labelledby="shadow-account-heading" className="rounded-card border border-border bg-surface p-4 text-sm lg:p-6">
      <header className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 id="shadow-account-heading" className="text-base font-semibold text-foreground">Shadow 成交证据与策略候选</h2>
            {capabilityQuery.isLoading ? (
              <span role="status" className="inline-flex items-center gap-1 text-xs text-secondary"><LoaderCircle aria-hidden="true" className="h-4 w-4 motion-safe:animate-spin motion-reduce:animate-none" />正在确认模块状态</span>
            ) : capability?.available ? (
              <span role="status" className="inline-flex items-center gap-1 text-xs text-foreground"><CheckCircle2 aria-hidden="true" className="h-4 w-4 text-accent" />可用</span>
            ) : (
              <span role="status" className="inline-flex items-center gap-1 text-xs text-warning"><AlertTriangle aria-hidden="true" className="h-4 w-4" />不可用</span>
            )}
          </div>
          <p className="mt-2 max-w-[70ch] text-sm leading-relaxed text-secondary">仅从本地实际成交日志形成研究证据，不连接券商、不同步持仓、不执行交易。</p>
        </div>
        <ShieldCheck aria-hidden="true" className="h-5 w-5 shrink-0 text-secondary" />
      </header>

      {capabilityQuery.isError && !capabilityQuery.data ? (
        <div ref={errorRef} tabIndex={-1} role="alert" className="mt-4 rounded-card border border-warning/40 bg-warning/10 p-4 focus:outline-none">
          <h3 className="text-base font-semibold">暂时无法确认模块状态</h3>
          <p className="mt-1 text-sm text-secondary">Shadow 状态读取失败；既有回测和研究内容仍可使用。</p>
          <button type="button" className={`${BUTTON_CLASS} mt-3`} onClick={() => capabilityQuery.refetch()}>重新确认 Shadow 状态</button>
        </div>
      ) : null}

      {capability && !capability.available ? (
        <div className="mt-4 rounded-card border border-warning/40 bg-warning/10 p-4">
          <p className="max-w-[70ch] text-sm leading-relaxed text-foreground">此部署未启用 Shadow 蒸馏模块。现有回测、研究库和 v1 工作流仍可使用。请联系部署维护者启用 Shadow 可选依赖。</p>
          <p className="mt-2 text-xs text-secondary">{capability.reason}</p>
        </div>
      ) : null}

      {capability?.available ? (
        <div className="mt-6 space-y-8">
          {statusMessage ? <p role="status" aria-live="polite" className="rounded-card border border-accent/40 bg-accent/10 p-3 text-sm text-foreground">{statusMessage}</p> : null}

          {loadFailed ? (
            <div ref={errorRef} tabIndex={-1} role="alert" className="rounded-card border border-danger/40 bg-danger/10 p-4 focus:outline-none">
              <h3 className="text-base font-semibold">无法加载 Shadow 记录</h3>
              <p className="mt-1 text-sm">无法加载 Shadow 记录：{safeReason(batchesQuery.error ?? evidenceQuery.error ?? candidatesQuery.error ?? evaluationsQuery.error ?? retentionsQuery.error)}。</p>
              <p className="mt-1 text-sm text-secondary">此前显示的批次不会被清空，当前批次、证据集或候选选择保持不变。本次加载失败不创建运行记录，也不改变任何既有只读终态记录。</p>
              <button type="button" className={`${BUTTON_CLASS} mt-3`} onClick={() => Promise.all([batchesQuery.refetch(), evidenceQuery.refetch(), candidatesQuery.refetch(), evaluationsQuery.refetch(), retentionsQuery.refetch()])}>重新加载 Shadow 记录</button>
            </div>
          ) : null}

          <section aria-labelledby="shadow-import-heading">
            <h3 id="shadow-import-heading" className="text-base font-semibold">1 选择日志 → 2 映射与预览 → 3 确认不可变导入</h3>
            <p className="mt-2 max-w-[70ch] text-sm text-secondary">支持 CSV 与 XLSX；文件大小上限 8 MB、预览行数最多 50 行，源时区固定审阅为 Asia/Shanghai。文件仅发送到当前自托管服务，不提供手工逐笔录入。</p>
            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <label className="text-sm text-secondary">选择本地成交日志
                <input aria-label="选择本地成交日志" type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className={`${CONTROL_CLASS} mt-1 block w-full cursor-pointer file:mr-3 file:rounded-btn file:border-0 file:bg-accent file:px-3 file:py-2 file:text-sm file:font-semibold file:text-white`} onChange={event => chooseFile(event.target.files?.[0] ?? null)} />
              </label>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="text-sm text-secondary">来源标签
                  <input value={sourceLabel} maxLength={256} className={`${CONTROL_CLASS} mt-1 w-full`} onChange={event => setSourceLabel(event.target.value)} />
                </label>
                <label className="text-sm text-secondary">源时区
                  <select value={sourceTimezone} className={`${CONTROL_CLASS} mt-1 w-full`} onChange={event => setSourceTimezone(event.target.value)}><option value="Asia/Shanghai">Asia/Shanghai</option></select>
                </label>
              </div>
            </div>

            {previewImport.isPending ? (
              <div aria-label="Shadow 映射正在加载" className="mt-4 h-48 animate-pulse rounded-card border border-border bg-elevated/50 motion-reduce:animate-none" />
            ) : null}
            {previewImport.isError ? (
              <div ref={errorRef} tabIndex={-1} role="alert" className="mt-4 rounded-card border border-danger/40 bg-danger/10 p-4 focus:outline-none">
                <p className="font-semibold">无法解析成交日志：{safeReason(previewImport.error)}。请检查格式、字段映射和源时区后重试。</p>
                <button type="button" className={`${BUTTON_CLASS} mt-3`} disabled={!file} onClick={() => file && previewImport.mutate({ file, mapping, source_timezone: sourceTimezone })}>按当前映射重新解析</button>
              </div>
            ) : null}

            {previewImport.data ? (
              <div className="mt-5 space-y-5">
                <div>
                  <p className="mb-2 text-xs text-secondary">仅为预览；重复组和 partial fill（部分成交）不会自动删除或合并。</p>
                  <OverflowTable instructionId="shadow-mapping-scroll-instruction">
                    <table className="min-w-[760px] w-full">
                      <caption className="sr-only">Shadow 字段映射预览</caption>
                      <thead className={TABLE_HEADER_CLASS}><tr><th scope="col" className="px-3 py-2">目标字段</th><th scope="col" className="px-3 py-2">来源列</th><th scope="col" className="px-3 py-2">样例值</th><th scope="col" className="px-3 py-2">单位与时区</th><th scope="col" className="px-3 py-2">状态</th></tr></thead>
                      <tbody>{MAPPING_FIELDS.map(field => {
                        const fixtureMapping = previewImport.data.mapping?.find(item => item.target === field.key)
                        const sampleRow = previewImport.data.sample_rows[0] ?? previewImport.data.rows?.[0]
                        const sample = fixtureMapping?.sample ?? sampleRow?.[field.key as keyof typeof sampleRow]
                        return <tr key={field.key}><th scope="row" className={`${TABLE_CELL_CLASS} font-normal text-foreground`}>{field.label} {field.required ? '（必需）' : '（可选）'}</th><td className={TABLE_CELL_CLASS}><input aria-label={`${field.label}来源列`} value={mapping[field.key] ?? ''} className={`${CONTROL_CLASS} w-full min-w-40`} onChange={event => setMapping(previous => ({ ...previous, [field.key]: event.target.value || null }))} /></td><td className={`${TABLE_CELL_CLASS} font-mono`}>{String(sample ?? '未提供')}</td><td className={TABLE_CELL_CLASS}>{field.unit}</td><td className={TABLE_CELL_CLASS}>{mapping[field.key] ? '已映射' : field.required ? '缺少必需映射' : '可选缺失'}</td></tr>
                      })}</tbody>
                    </table>
                  </OverflowTable>
                </div>

                <div>
                  <OverflowTable instructionId="shadow-preview-scroll-instruction">
                    <table className="min-w-[760px] w-full">
                      <caption className="sr-only">Shadow 成交日志仅为预览</caption>
                      <thead className={TABLE_HEADER_CLASS}><tr><th scope="col" className="px-3 py-2">标的</th><th scope="col" className="px-3 py-2">方向</th><th scope="col" className="px-3 py-2">成交时间</th><th scope="col" className="px-3 py-2 text-right">数量</th><th scope="col" className="px-3 py-2 text-right">价格</th><th scope="col" className="px-3 py-2">重复组</th></tr></thead>
                      <tbody>{(previewImport.data.sample_rows.length ? previewImport.data.sample_rows : previewImport.data.rows ?? []).map((row, index) => <tr key={`${row.source_row_ordinal ?? index}-${row.broker_fill_id ?? ''}`}><td className={`${TABLE_CELL_CLASS} font-mono`}>{row.symbol ?? '未提供'}</td><td className={TABLE_CELL_CLASS}>{row.side ?? '未提供'}</td><td className={`${TABLE_CELL_CLASS} font-mono`}>{row.executed_at ?? '未提供'}</td><td className={`${TABLE_CELL_CLASS} text-right font-mono tabular-nums`}>{row.quantity ?? '未提供'}</td><td className={`${TABLE_CELL_CLASS} text-right font-mono tabular-nums`}>{row.price ?? '未提供'}</td><td className={`${TABLE_CELL_CLASS} break-words font-mono`}>{row.duplicate_group_hash ?? '无'}</td></tr>)}</tbody>
                    </table>
                  </OverflowTable>
                </div>
                <button ref={importTriggerRef} type="button" className={PRIMARY_CLASS} disabled={!file || !sourceLabel || confirmImport.isPending} onClick={() => setImportConfirmationOpen(true)}>确认不可变导入</button>
              </div>
            ) : null}
          </section>

          <section aria-labelledby="shadow-batches-heading" className="border-t border-border pt-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div><h3 id="shadow-batches-heading" className="text-base font-semibold">不可变导入批次</h3><p className="mt-1 text-xs text-secondary">每次导入追加新行；无编辑、覆盖或删除。</p></div>
              {batchesQuery.isFetching ? <span role="status" className="text-xs text-secondary">正在刷新批次历史…</span> : null}
            </div>
            {batchesQuery.isLoading && !batches.length ? <div className="mt-4 h-40 animate-pulse rounded-card bg-elevated/50 motion-reduce:animate-none" /> : null}
            {!batchesQuery.isLoading && batches.length === 0 ? (
              <div className="mt-4 py-6 text-center"><FileUp aria-hidden="true" className="mx-auto h-8 w-8 text-secondary" /><h4 className="mt-3 text-base font-semibold">尚无 Shadow 成交批次</h4><p className="mx-auto mt-2 max-w-[65ch] text-sm text-secondary">选择本地真实成交日志，完成字段映射后会追加一条不可变导入记录。</p></div>
            ) : null}
            {batches.length ? (
              <div className="mt-4">
                <OverflowTable instructionId="shadow-batches-scroll-instruction">
                  <table className="min-w-[1120px] w-full">
                    <caption className="sr-only">Shadow 不可变导入批次</caption>
                    <thead className={TABLE_HEADER_CLASS}><tr><th scope="col" className="px-3 py-2">纳入</th><th scope="col" className="px-3 py-2">批次与原文件</th><th scope="col" className="px-3 py-2">来源/导入人</th><th scope="col" className="px-3 py-2">创建时间</th><th scope="col" className="px-3 py-2">内容摘要/映射</th><th scope="col" className="px-3 py-2">总行/有效/诊断</th><th scope="col" className="px-3 py-2">谱系</th><th scope="col" className="px-3 py-2">状态与诊断</th></tr></thead>
                    <tbody>{batches.map(batch => {
                      const counts = batchCounts(batch)
                      return <tr key={batch.id}><td className={TABLE_CELL_CLASS}><input aria-label={`纳入批次 ${batch.label ?? batch.id}`} type="checkbox" className="h-5 w-5 accent-accent" checked={selectedBatchIds.has(batch.id)} onChange={event => setSelectedBatchIds(previous => { const next = new Set(previous); if (event.target.checked) next.add(batch.id); else next.delete(batch.id); return next })} /></td><th scope="row" className={`${TABLE_CELL_CLASS} min-w-56 font-normal`}><span className="block font-semibold text-foreground">{batch.label ?? batch.source_label}</span><span className="mt-1 block break-words">{batch.original_filename ?? '服务端未投影原文件名'}</span><span className="mt-1 block break-all font-mono">{batch.id}</span></th><td className={TABLE_CELL_CLASS}>{batch.source_label}<br />{batch.imported_by ?? '服务端会话身份'}</td><td className={`${TABLE_CELL_CLASS} font-mono`}>{displayTime(batch.created_at)}</td><td className={TABLE_CELL_CLASS}><span className="block break-all font-mono">{batch.content_digest ?? batch.content_sha256}</span><span className="mt-1 block">映射 {batch.mapping_version}</span></td><td className={`${TABLE_CELL_CLASS} font-mono tabular-nums`}>{counts.total} / {counts.valid} / {counts.invalid}<br />重复组 {batch.duplicate_groups ?? '未提供'}；partial fill {batch.partial_fills ?? '未提供'}</td><td className={TABLE_CELL_CLASS}>{batch.same_content_as ? <>same content：<span className="break-all font-mono">{batch.same_content_as}</span></> : batch.supersedes_batch_id ? <>修正自 <span className="break-all font-mono">{batch.supersedes_batch_id}</span></> : '首个批次'}</td><td className={TABLE_CELL_CLASS}>{statusText(batch.status)}{counts.invalid > 0 ? <p className="mt-1 text-warning">导入包含需要处理的诊断：{counts.valid} 行有效，{counts.invalid} 行未纳入。</p> : null}<details className="mt-1"><summary className="min-h-11 cursor-pointer py-2 text-accent">查看导入诊断</summary>{batch.diagnostics.length ? <ul className="space-y-1">{batch.diagnostics.map((diagnostic, index) => <li key={`${diagnostic.code ?? 'diagnostic'}-${index}`} className="max-w-[65ch] break-words">{diagnostic.message}</li>)}</ul> : <p>无服务端诊断。</p>}</details></td></tr>
                    })}</tbody>
                  </table>
                </OverflowTable>
                <Pagination page={batchesQuery.data?.page} offset={batchOffset} onOffset={setBatchOffset} />
              </div>
            ) : null}
          </section>

          {batches.length ? (
            <section aria-labelledby="shadow-evidence-heading" className="border-t border-border pt-6">
              <h3 id="shadow-evidence-heading" className="text-base font-semibold">冻结证据集</h3>
              {!currentEvidence ? <div className="mt-4"><h4 className="text-base font-semibold">尚未创建 Shadow 证据集</h4><p className="mt-2 max-w-[70ch] text-sm text-secondary">已有完成的成交批次，但尚未冻结用于候选蒸馏的证据。请选择要纳入的已完成批次和排除项；创建后证据集不可修改。</p><p className="mt-2 text-xs text-secondary">未勾选时将纳入当前页最近的已完成批次；重复组与 partial fill 保持原样。</p></div> : null}
              {currentEvidence ? <div className="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]"><div className="rounded-card border border-border bg-base/30 p-4"><label className="text-sm text-secondary">当前只读证据集<select className={`${CONTROL_CLASS} mt-1 w-full`} value={currentEvidence.id} onChange={event => setSelectedEvidenceId(event.target.value)}>{evidenceSets.map(item => <option key={item.id} value={item.id}>{item.id}</option>)}</select></label><dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2"><div><dt className="text-secondary">纳入批次 / 成交</dt><dd>{currentEvidence.included_batch_ids.length || currentEvidence.batch_count || 0} / {currentEvidence.included_trade_count || currentEvidence.trade_count || 0}</dd></div><div><dt className="text-secondary">重复组 / partial fill</dt><dd>{currentEvidence.duplicate_groups ?? '未提供'} / {currentEvidence.partial_fills ?? '未提供'}</dd></div><div className="sm:col-span-2"><dt className="text-secondary">冻结 fingerprint</dt><dd className="break-all font-mono" style={{ overflowWrap: 'anywhere' }}>{currentEvidence.fingerprint}</dd></div></dl></div>{staleEvidence ? <p className="rounded-card border border-warning/40 bg-warning/10 p-4 text-sm text-foreground">存在较新成交批次；当前候选仍基于已冻结证据。</p> : null}</div> : null}
              <button type="button" className={`${PRIMARY_CLASS} mt-4`} disabled={!evidenceBatchIds.length || createEvidence.isPending} onClick={() => createEvidence.mutate({ included_batch_ids: evidenceBatchIds, included_trade_ids: [], exclusions: [] })}>{createEvidence.isPending ? '正在冻结证据集…' : '创建新证据集'}</button>
              {createEvidence.isError ? <p role="alert" className="mt-2 text-sm text-danger">无法创建证据集：{safeReason(createEvidence.error)}。批次选择保持不变。</p> : null}
              <Pagination page={evidenceQuery.data?.page} offset={evidenceOffset} onOffset={setEvidenceOffset} />
            </section>
          ) : null}

          {currentEvidence ? (
            <section aria-labelledby="shadow-candidate-heading" className="border-t border-border pt-6">
              <h3 id="shadow-candidate-heading" className="text-base font-semibold">可解释策略候选</h3>
              {!currentCandidate ? <div className="mt-4"><h4 className="text-base font-semibold">尚无 Shadow 策略候选</h4><p className="mt-2 max-w-[70ch] text-sm text-secondary">当前证据集已冻结，但尚未生成可解释候选。开始蒸馏后，候选将记录规则、参数、来源、限制和独立样本内/样本外评估。</p><button type="button" className={`${PRIMARY_CLASS} mt-4`} disabled={distillCandidate.isPending} onClick={() => distillCandidate.mutate({ evidenceSetId: currentEvidence.id })}>{distillCandidate.isPending ? '正在蒸馏候选…' : '开始候选蒸馏'}</button></div> : null}
              {distillCandidate.isError ? <div role="alert" className="mt-4 rounded-card border border-danger/40 bg-danger/10 p-4"><h4 className="text-base font-semibold">Shadow 候选蒸馏失败</h4><p className="mt-1">Shadow 候选蒸馏失败：{safeReason(distillCandidate.error)}。</p><p className="mt-1 text-secondary">本次未创建候选，冻结证据集及其 fingerprint 保持不变。失败运行作为只读终态保留；重试必须基于相同冻结证据集创建新运行，不复用或覆盖失败运行。</p><button type="button" className={`${BUTTON_CLASS} mt-3`} onClick={() => distillCandidate.mutate({ evidenceSetId: currentEvidence.id })}>基于相同证据集创建新蒸馏运行</button></div> : null}

              {currentCandidate ? (
                <article className="mt-4 space-y-5">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between"><label className="text-sm text-secondary">当前只读候选<select value={currentCandidate.id} className={`${CONTROL_CLASS} mt-1 w-full min-w-64`} onChange={event => setSelectedCandidateId(event.target.value)}>{candidates.map(item => <option key={item.id} value={item.id}>{item.label ?? item.id}</option>)}</select></label><p className="text-xs text-secondary">资格：{retainable ? '服务端证据满足保留前提' : '尚不具备保留资格'}</p></div>
                  {!distillCandidate.isError ? <button type="button" className={BUTTON_CLASS} disabled={distillCandidate.isPending} onClick={() => distillCandidate.mutate({ evidenceSetId: currentEvidence.id })}>{distillCandidate.isPending ? '正在蒸馏候选…' : '基于相同证据集创建新蒸馏运行'}</button> : null}
                  <OverflowTable instructionId="shadow-rules-scroll-instruction">
                    <table className="min-w-[980px] w-full">
                      <caption className="sr-only">Shadow 候选规则与限制</caption>
                      <thead className={TABLE_HEADER_CLASS}><tr><th scope="col" className="px-3 py-2">if / then 进入规则</th><th scope="col" className="px-3 py-2">特征</th><th scope="col" className="px-3 py-2">支持度 / precision / recall</th><th scope="col" className="px-3 py-2">参数</th><th scope="col" className="px-3 py-2">退出/持有假设</th><th scope="col" className="px-3 py-2">seed / class balance</th><th scope="col" className="px-3 py-2">来源与限制</th></tr></thead>
                      <tbody>{candidateRules(currentCandidate).map((rule, index) => <tr key={`${currentCandidate.id}-rule-${index}`}><th scope="row" className={`${TABLE_CELL_CLASS} max-w-sm break-words font-normal`}>{ruleExpression(rule)}</th><td className={TABLE_CELL_CLASS}>{currentCandidate.features.join('、')}</td><td className={`${TABLE_CELL_CLASS} font-mono tabular-nums`}>{rule.support ?? '未提供'} / {percent(rule.precision)} / {percent(rule.recall)}</td><td className={`${TABLE_CELL_CLASS} max-w-xs break-words font-mono`}>{boundedJson(currentCandidate.parameters)}</td><td className={`${TABLE_CELL_CLASS} max-w-xs break-words`}>{boundedJson(currentCandidate.exit_assumptions)}；{boundedJson(currentCandidate.holding_assumptions)}{currentCandidate.assumptions?.length ? `；${currentCandidate.assumptions.join('；')}` : ''}</td><td className={`${TABLE_CELL_CLASS} break-words font-mono`}>seed {currentCandidate.seed ?? '未提供'}；class balance {boundedJson(currentCandidate.class_balance)}</td><td className={`${TABLE_CELL_CLASS} max-w-xs break-words`}>批次 {currentCandidate.source_batch_ids.join('、')}；{currentCandidate.limitations.join('；')}</td></tr>)}</tbody>
                    </table>
                  </OverflowTable>
                  <details><summary className="min-h-11 cursor-pointer py-2 text-accent">查看规则与限制</summary><dl className="grid gap-2 text-xs sm:grid-cols-2"><div><dt className="text-secondary">Evidence fingerprint</dt><dd className="break-all font-mono" style={{ overflowWrap: 'anywhere' }}>{currentCandidate.evidence_fingerprint ?? currentCandidate.evidence_set_fingerprint}</dd></div><div><dt className="text-secondary">Rule fingerprint</dt><dd className="break-all font-mono" style={{ overflowWrap: 'anywhere' }}>{currentCandidate.rule_fingerprint ?? '未提供'}</dd></div><div><dt className="text-secondary">训练窗口</dt><dd className="font-mono">{boundedJson(currentCandidate.training_window)}</dd></div><div><dt className="text-secondary">蒸馏 / 规则版本</dt><dd>{currentCandidate.distiller_version || '未提供'} / {currentCandidate.rule_schema_version || '未提供'}</dd></div></dl></details>
                  <Pagination page={candidatesQuery.data?.page} offset={candidateOffset} onOffset={setCandidateOffset} />
                </article>
              ) : null}
            </section>
          ) : null}

          {currentCandidate ? (
            <section aria-labelledby="shadow-evaluation-heading" className="border-t border-border pt-6">
              <h3 id="shadow-evaluation-heading" className="text-base font-semibold">独立样本内 / 样本外评估</h3>
              <p className="mt-2 text-sm text-secondary">必须先完成相互独立的样本内与样本外评估，且两者均通过。</p>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <label className="text-xs text-secondary">样本内开始<input type="date" value={inSampleStart} className={`${CONTROL_CLASS} mt-1 w-full`} onChange={event => setInSampleStart(event.target.value)} /></label>
                <label className="text-xs text-secondary">样本内结束<input type="date" value={inSampleEnd} className={`${CONTROL_CLASS} mt-1 w-full`} onChange={event => setInSampleEnd(event.target.value)} /></label>
                <label className="text-xs text-secondary">样本外开始<input type="date" value={outSampleStart} className={`${CONTROL_CLASS} mt-1 w-full`} onChange={event => setOutSampleStart(event.target.value)} /></label>
                <label className="text-xs text-secondary">样本外结束<input type="date" value={outSampleEnd} className={`${CONTROL_CLASS} mt-1 w-full`} onChange={event => setOutSampleEnd(event.target.value)} /></label>
              </div>
              <button type="button" className={`${BUTTON_CLASS} mt-3`} disabled={evaluateCandidate.isPending} onClick={() => evaluateCandidate.mutate({ evidenceSetId: currentCandidate.evidence_set_id, candidateId: currentCandidate.id })}>{evaluateCandidate.isPending ? '正在分别评估…' : '创建新的样本内与样本外评估'}</button>
              {evaluationRows.length ? (
                <div className="mt-4">
                  <OverflowTable instructionId="shadow-evaluations-scroll-instruction">
                    <table className="min-w-[1220px] w-full">
                      <caption className="sr-only">Shadow 样本内与样本外证据</caption>
                      <thead className={TABLE_HEADER_CLASS}><tr><th scope="col" className="px-3 py-2">范围与状态</th><th scope="col" className="px-3 py-2">不重叠窗口</th><th scope="col" className="px-3 py-2">precision / recall / coverage</th><th scope="col" className="px-3 py-2">候选成交</th><th scope="col" className="px-3 py-2">收益 / 回撤 / 成本后</th><th scope="col" className="px-3 py-2">实际成交一致度</th><th scope="col" className="px-3 py-2">调整与成本口径</th><th scope="col" className="px-3 py-2">工件 / 终态</th></tr></thead>
                      <tbody>{evaluationRows.map(row => <tr key={row.id}><th scope="row" className={`${TABLE_CELL_CLASS} font-normal`}><span className="block font-semibold">{row.split === 'in_sample' ? '样本内' : '样本外'}</span>{statusText(row.status)}</th><td className={`${TABLE_CELL_CLASS} font-mono`}>{row.start} 至 {row.end}</td><td className={`${TABLE_CELL_CLASS} font-mono tabular-nums`}>{percent(row.precision)} / {percent(row.recall)} / {percent(row.coverage)}</td><td className={`${TABLE_CELL_CLASS} text-right font-mono tabular-nums`}>{row.trades ?? '未提供'}</td><td className={`${TABLE_CELL_CLASS} font-mono tabular-nums`}>{percent(row.totalReturn)} / {percent(row.drawdown)} / {row.afterCost !== undefined ? percent(row.afterCost) : decimal(row.costs)}</td><td className={`${TABLE_CELL_CLASS} font-mono tabular-nums`}>{percent(row.consistency)}</td><td className={TABLE_CELL_CLASS}>{row.adjustment ?? '受治理调整口径'}；成本后指标已单列</td><td className={`${TABLE_CELL_CLASS} break-words`}>{row.artifact ?? '工件入口未投影'}{row.terminalReason ? <p className="mt-1 text-danger">{row.terminalReason}</p> : null}</td></tr>)}</tbody>
                    </table>
                  </OverflowTable>
                  <details className="mt-2"><summary className="min-h-11 cursor-pointer py-2 text-accent">查看样本内与样本外证据</summary><p className="max-w-[70ch] text-sm text-secondary">完整评估历史按候选、冻结 evidence fingerprint 和不可变运行 ID 保留。全样本指标不替代两个独立窗口。</p></details>
                </div>
              ) : <p className="mt-4 text-sm text-warning">尚无独立评估记录；当前候选不能保留。</p>}

              {evaluateCandidate.isError ? <div role="alert" className="mt-4 rounded-card border border-danger/40 bg-danger/10 p-4"><h4 className="text-base font-semibold">Shadow 样本内/样本外评估失败</h4><p className="mt-1">Shadow 样本内/样本外评估失败：{safeReason(evaluateCandidate.error)}。</p><p className="mt-1 text-secondary">本次不产生保留资格；候选和既有评估记录保持不变。失败运行作为只读终态保留；重试必须创建新评估运行，不复用或覆盖失败运行。</p><button type="button" className={`${BUTTON_CLASS} mt-3`} onClick={() => evaluateCandidate.mutate({ evidenceSetId: currentCandidate.evidence_set_id, candidateId: currentCandidate.id })}>创建新评估运行</button></div> : null}
              {actualEvaluationRows.filter(row => row.status !== 'passed' && row.status !== 'completed').map(row => <div key={`${row.id}-terminal`} className="mt-4 rounded-card border border-danger/40 bg-danger/10 p-4"><h4 className="text-base font-semibold">Shadow 样本内/样本外评估失败</h4><p className="mt-1 break-words">{statusText(row.status)}：{row.terminalReason ?? '运行未产生可保留评估证据'}。</p><p className="mt-1 text-secondary">失败运行只读保留；重试创建新评估运行。</p><button type="button" className={`${BUTTON_CLASS} mt-3`} disabled={retryEvaluation.isPending} onClick={() => retryEvaluation.mutate(row.id)}>创建新评估运行</button></div>)}
              <Pagination page={evaluationsQuery.data?.page} offset={evaluationOffset} onOffset={setEvaluationOffset} />

              <div className="mt-5 border-t border-border pt-5">
                <button ref={retainTriggerRef} type="button" className={PRIMARY_CLASS} disabled={!retainable || Boolean(retained) || retainCandidate.isPending} onClick={() => setRetainConfirmationOpen(true)}>保留为 Shadow 研究候选</button>
                {!retainable ? <p className="mt-2 text-sm text-warning">必须先完成相互独立的样本内与样本外评估，且两者均通过。</p> : null}
                {retained ? <p role="status" className="mt-2 text-sm text-foreground">已保留为研究候选：{retained.id}。不会注册或启用策略。</p> : null}
                {retainCandidate.isError ? <p role="alert" className="mt-2 text-sm text-danger">保留请求未完成：{safeReason(retainCandidate.error)}。候选、评估与理由均保持不变。</p> : null}
              </div>
            </section>
          ) : null}

          {retentions.length ? (
            <section aria-labelledby="shadow-retentions-heading" className="border-t border-border pt-6">
              <h3 id="shadow-retentions-heading" className="text-base font-semibold">Shadow 保留历史</h3>
              <div className="mt-4"><OverflowTable instructionId="shadow-retentions-scroll-instruction"><table className="min-w-[900px] w-full"><caption className="sr-only">Shadow 研究候选保留历史</caption><thead className={TABLE_HEADER_CLASS}><tr><th scope="col" className="px-3 py-2">状态</th><th scope="col" className="px-3 py-2">候选 / 证据集</th><th scope="col" className="px-3 py-2">样本内 / 样本外</th><th scope="col" className="px-3 py-2">理由</th><th scope="col" className="px-3 py-2">创建时间</th></tr></thead><tbody>{retentions.map(retention => <tr key={retention.id}><td className={TABLE_CELL_CLASS}>{statusText(retention.status)}</td><th scope="row" className={`${TABLE_CELL_CLASS} font-normal`}><span className="break-all font-mono">{retention.candidate_id}</span><br /><span className="break-all font-mono">{retention.evidence_set_id}</span></th><td className={`${TABLE_CELL_CLASS} font-mono`}>{retention.in_sample_evaluation_id}<br />{retention.out_of_sample_evaluation_id}</td><td className={`${TABLE_CELL_CLASS} max-w-[65ch] break-words`}>{retention.rationale ?? '研究用途保留'}</td><td className={`${TABLE_CELL_CLASS} font-mono`}>{displayTime(retention.created_at)}</td></tr>)}</tbody></table></OverflowTable><Pagination page={retentionsQuery.data?.page} offset={retentionOffset} onOffset={setRetentionOffset} /></div>
            </section>
          ) : null}
        </div>
      ) : null}

      <ConfirmationDialog open={importConfirmationOpen} title="确认不可变导入" confirmLabel="确认不可变导入" pending={confirmImport.isPending} triggerRef={importTriggerRef} onClose={() => setImportConfirmationOpen(false)} onConfirm={() => file && confirmImport.mutate({ file, mapping, source_timezone: sourceTimezone, source_label: sourceLabel })} description={<dl className="grid gap-2"><div><dt className="font-semibold text-foreground">原文件名</dt><dd className="break-words">{file?.name ?? '未选择'}</dd></div><div><dt className="font-semibold text-foreground">来源标签 / 时区</dt><dd>{sourceLabel} / {sourceTimezone}</dd></div><div><dt className="font-semibold text-foreground">映射 / 行数</dt><dd className="break-words">{JSON.stringify(mapping)} / {previewImport.data?.source_row_count ?? '以服务端确认为准'}</dd></div><div><dt className="font-semibold text-foreground">不可覆写</dt><dd>确认后追加新的不可变批次；不会覆盖、删除或修改任何旧批次，也不会激活策略或执行交易。</dd></div></dl>} />

      <ConfirmationDialog open={retainConfirmationOpen} title="保留为 Shadow 研究候选" confirmLabel="保留为 Shadow 研究候选" pending={retainCandidate.isPending} triggerRef={retainTriggerRef} onClose={() => setRetainConfirmationOpen(false)} onConfirm={() => currentCandidate && inSample && outOfSample && retainCandidate.mutate({ evidenceSetId: currentCandidate.evidence_set_id, candidateId: currentCandidate.id, inSampleId: inSample.id, outSampleId: outOfSample.id })} description={<>确认保留候选 {currentCandidate?.label ?? currentCandidate?.id}？系统将记录冻结证据集和样本内/样本外评估；不会注册或启用策略，也不会创建监控、计划或市场动作。</>}>
        <label className="mt-4 block text-sm text-secondary">保留理由（至少 10 个字符）<textarea value={retentionRationale} minLength={10} maxLength={4_000} className={`${CONTROL_CLASS} mt-1 min-h-24 w-full`} onChange={event => setRetentionRationale(event.target.value)} /></label>
      </ConfirmationDialog>
    </section>
  )
}
