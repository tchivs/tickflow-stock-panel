import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type AdvancedCandidate, type AdvancedExecutionEvidence, type AdvancedExperimentFeedback, type AdvancedResearchAssetBinding, type AdvancedSandboxRun, type AdvancedSandboxValidation } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

const GATE_LABELS = {
  contract_sandbox_safety: '合同/沙箱安全',
  provenance: '来源完整性',
  in_sample_out_of_sample_evidence: '样本内与样本外',
  robustness: '稳健性',
  cost_feasibility: '成本与可实现性',
} as const

const feedbackLabels: Record<AdvancedExperimentFeedback['conclusion'], string> = {
  supported: '支持', refuted: '证伪', inconclusive: '无结论', needs_replication: '需要复现',
}

const controlClass = 'min-h-11 rounded-btn border border-border bg-base px-3 py-2 text-xs text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface disabled:cursor-not-allowed disabled:opacity-45'
const primaryClass = `${controlClass} border-accent bg-accent-solid text-white hover:bg-accent-solid/90`

function serialize(value: Record<string, string | number | boolean | null> | null | undefined) {
  return Object.entries(value ?? {}).map(([key, item]) => `${key}: ${String(item)}`).join(' · ') || '无额外受控参数'
}

function parseParameters(value: string) {
  if (!value.trim()) return {}
  const parsed: unknown = JSON.parse(value)
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object' || Object.values(parsed).some(item => item !== null && !['string', 'number', 'boolean'].includes(typeof item))) {
    throw new Error('参数必须是仅含字符串、数值、布尔值或 null 的对象。')
  }
  return parsed as Record<string, string | number | boolean | null>
}

async function sourceHash(source: string) {
  const bytes = new TextEncoder().encode(source)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return [...new Uint8Array(digest)].map(item => item.toString(16).padStart(2, '0')).join('')
}

function ExecutionEvidence({ evidence }: { evidence: AdvancedExecutionEvidence }) {
  const windows = [['聚合', evidence.aggregate], ['样本内', evidence.in_sample], ['样本外', evidence.out_of_sample]] as const
  return <dl aria-label="受控执行证据" className="space-y-1 text-xs text-secondary">{windows.map(([label, item]) => <div key={label}><dt className="inline font-medium text-foreground">{label}：</dt><dd className="inline">合格买入 {item.eligible_buy_count}；完成交易 {item.completed_trade_count}{item.window && `；${item.window.start} 至 ${item.window.end}`}</dd></div>)}</dl>
}

export function AdvancedResearchPanels({ binding, bindingError }: { binding: AdvancedResearchAssetBinding | null; bindingError: string | null }) {
  const queryClient = useQueryClient()
  const researchAssetId = binding?.research_asset_id ?? null
  const assetKey = researchAssetId ?? 'none'
  const [hypothesis, setHypothesis] = useState('')
  const [method, setMethod] = useState('bounded-backtest')
  const [metrics, setMetrics] = useState('sharpe')
  const [criteria, setCriteria] = useState('风险调整收益达到受控阈值')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [symbols, setSymbols] = useState('')
  const [assetType, setAssetType] = useState<'stock' | 'etf' | 'index'>('stock')
  const [parameters, setParameters] = useState('{}')
  const [scopeError, setScopeError] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<Record<string, AdvancedExperimentFeedback['conclusion']>>({})
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [candidateForPromotion, setCandidateForPromotion] = useState<string | null>(null)
  const [rationale, setRationale] = useState('')
  const [promotionStatus, setPromotionStatus] = useState<string | null>(null)
  const [source, setSource] = useState('')
  const [sandboxResult, setSandboxResult] = useState<AdvancedSandboxValidation | null>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const promotionTriggerRef = useRef<HTMLButtonElement | null>(null)
  const promotionReasonRef = useRef<HTMLTextAreaElement>(null)
  const failureRef = useRef<HTMLDivElement>(null)
  const dialogHeadingRef = useRef<HTMLHeadingElement>(null)

  const invalidateExperiments = () => queryClient.invalidateQueries({ queryKey: QK.advancedExperiments(assetKey) })
  const invalidateCandidates = () => queryClient.invalidateQueries({ queryKey: QK.advancedCandidates(assetKey) })
  const invalidateSandboxRuns = () => queryClient.invalidateQueries({ queryKey: QK.advancedSandboxRuns(assetKey) })
  const experiments = useQuery({ queryKey: QK.advancedExperiments(assetKey), queryFn: api.advancedExperiments, enabled: Boolean(binding) })
  const candidates = useQuery({ queryKey: QK.advancedCandidates(assetKey), queryFn: api.advancedCandidates, enabled: Boolean(binding) })
  const sandboxHistory = useQuery({ queryKey: QK.advancedSandboxValidations, queryFn: api.advancedSandboxValidations, enabled: Boolean(binding) })
  const sandboxRuns = useQuery({ queryKey: QK.advancedSandboxRuns(assetKey), queryFn: api.advancedSandboxRuns, enabled: Boolean(binding) })
  const createSpec = useMutation({ mutationFn: api.advancedCreateExperiment, onSuccess: invalidateExperiments })
  const runExperiment = useMutation({ mutationFn: api.advancedRunExperiment, onSuccess: invalidateExperiments })
  const retryExperiment = useMutation({ mutationFn: api.advancedRetryExperiment, onSuccess: invalidateExperiments })
  const recordFeedback = useMutation({ mutationFn: ({ runId, conclusion, comment }: { runId: string; conclusion: AdvancedExperimentFeedback['conclusion']; comment: string }) => api.advancedRecordFeedback(runId, conclusion, comment), onSuccess: invalidateExperiments })
  const createCandidate = useMutation({ mutationFn: (runId: string) => api.advancedCreateCandidate({ completed_run_id: runId, mutation_operation: 'adjust_signal_threshold', seed: 0, resolved_configuration: { entry_signal_threshold: 1 } }), onSuccess: invalidateCandidates })
  const evaluateGate = useMutation({ mutationFn: ({ candidateId, gate }: { candidateId: string; gate: keyof typeof GATE_LABELS }) => api.advancedEvaluateCandidateGate(candidateId, gate), onSuccess: (_, { candidateId }) => { queryClient.invalidateQueries({ queryKey: QK.advancedCandidate(assetKey, candidateId) }); invalidateCandidates() } })
  const promote = useMutation({ mutationFn: ({ candidateId, reason }: { candidateId: string; reason: string }) => api.advancedPromoteCandidate(candidateId, reason), onSuccess: ({ registered_strategy }) => { invalidateCandidates(); setCandidateForPromotion(null); setRationale(''); setPromotionStatus(`已注册研究策略：${registered_strategy.id}（${registered_strategy.status}）`) } })
  const submitSandbox = useMutation({
    mutationFn: async () => {
      if (!researchAssetId) throw new Error('请先选择受控研究策略。')
      const hash = await sourceHash(source)
      return api.advancedSubmitSandbox({ contract: { contract_version: 'advanced-strategy-v1', parent_asset_id: researchAssetId, declared_inputs: ['governed_panel'], declared_imports: [], timeout_seconds: 5, memory_limit_mb: 128, source_sha256: hash }, source })
    },
    onSuccess: result => { setSandboxResult(result.validation ?? null); setSource(''); queryClient.invalidateQueries({ queryKey: QK.advancedSandboxValidations }); invalidateSandboxRuns() },
  })
  const openPromotion = (candidateId: string, trigger: HTMLButtonElement) => {
    promotionTriggerRef.current = trigger
    setCandidateForPromotion(candidateId)
  }

  const closePromotion = () => {
    setCandidateForPromotion(null)
    requestAnimationFrame(() => promotionTriggerRef.current?.focus())
  }
  const handlePromotionKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      closePromotion()
      return
    }
    if (event.key !== 'Tab' || !dialogRef.current) return
    const controls = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(
      'button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )).filter(control => !control.hasAttribute('hidden'))
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

  useEffect(() => { if (candidateForPromotion) promotionReasonRef.current?.focus() }, [candidateForPromotion])
  useEffect(() => { if (sandboxResult?.status !== 'validated') failureRef.current?.focus() }, [sandboxResult])

  // Advanced research is supplementary to backtesting. A malformed or partial
  // optional response must not take the whole workbench down while it loads.
  const specifications = Array.isArray(experiments.data?.specifications) ? experiments.data.specifications : []
  const runs = Array.isArray(experiments.data?.runs) ? experiments.data.runs : []
  const feedbackItems = Array.isArray(experiments.data?.feedback) ? experiments.data.feedback : []
  const candidateItems = Array.isArray(candidates.data?.candidates) ? candidates.data.candidates : []
  const sandboxValidations = Array.isArray(sandboxHistory.data?.validations) ? sandboxHistory.data.validations : []
  const sandboxRunItems = Array.isArray(sandboxRuns.data?.runs) ? sandboxRuns.data.runs : []
  const feedbackByRun = new Set(feedbackItems.map(item => item.run_id))
  const sandboxFailure = sandboxResult?.status !== 'validated' ? sandboxResult : sandboxValidations.find(item => item.status !== 'validated')
  const currentCandidate = candidateItems.find(candidate => candidate.id === candidateForPromotion)

  return <div className="space-y-8" aria-label="高级研究工作流">
    {!binding && <p role="alert" className="rounded-card border border-danger/30 bg-danger/10 p-3 text-xs text-danger">{bindingError ?? '服务器研究资产绑定不可用；高级研究操作已禁用。'}</p>}
    {binding && <section aria-label="服务器研究资产绑定" className="rounded-card border border-border bg-base/30 p-3 text-xs text-secondary"><p className="font-medium text-foreground">服务器解析的研究资产</p><dl className="mt-2 grid gap-1 sm:grid-cols-2"><div><dt className="inline text-muted">策略：</dt><dd className="inline font-mono">{binding.strategy_id}</dd></div><div><dt className="inline text-muted">因子：</dt><dd className="inline">{binding.factor_name}</dd></div><div className="sm:col-span-2"><dt className="inline text-muted">不可变资产：</dt><dd className="inline break-all font-mono">{binding.research_asset_id}</dd></div></dl></section>}
    {promotionStatus && <p role="status" className="rounded-card border border-success/30 bg-success/10 p-3 text-xs text-success">{promotionStatus}</p>}
    <section aria-labelledby="advanced-experiment-heading" className="border-t border-border pt-6">
      <h2 id="advanced-experiment-heading" className="text-base font-semibold text-foreground">实验规格与运行</h2>
      <p className="mt-1 max-w-[65ch] text-xs text-muted">规格提交后冻结；每次重试都会保留为新的受限运行。</p>
      <form className="mt-4 grid gap-3 md:grid-cols-2" onSubmit={event => {
        event.preventDefault()
        if (!binding || !researchAssetId) return
        try {
          const parsedParameters = parseParameters(parameters)
          setScopeError(null)
          createSpec.mutate({ research_asset_id: researchAssetId, hypothesis, data_scope: { market: 'CN-A', strategy_id: binding!.strategy_id, start, end, symbols: symbols.split(',').map(item => item.trim()).filter(Boolean) || undefined, asset_type: assetType, parameters: parsedParameters }, method, metrics: metrics.split(',').map(item => item.trim()).filter(Boolean), success_criteria: { summary: criteria }, failure_criteria: { summary: '不满足受控成功标准' } })
        } catch (error) { setScopeError(error instanceof Error ? error.message : '参数无效。') }
      }}>
        <label className="text-xs text-secondary">假设<textarea required value={hypothesis} onChange={event => setHypothesis(event.target.value)} className={`${controlClass} mt-1 min-h-20 w-full`} /></label>
        <div className="text-xs text-secondary">策略 ID<span aria-label="服务器策略 ID" className={`${controlClass} mt-1 block w-full cursor-default bg-elevated/50 font-mono`}>{binding?.strategy_id ?? '未解析'}</span></div>
        <label className="text-xs text-secondary">开始日期<input aria-label="开始日期" required type="date" value={start} onChange={event => setStart(event.target.value)} className={`${controlClass} mt-1 w-full`} /></label>
        <label className="text-xs text-secondary">结束日期<input aria-label="结束日期" required type="date" value={end} onChange={event => setEnd(event.target.value)} className={`${controlClass} mt-1 w-full`} /></label>
        <label className="text-xs text-secondary">标的代码（可选，逗号分隔）<input aria-label="标的代码（可选，逗号分隔）" value={symbols} onChange={event => setSymbols(event.target.value)} className={`${controlClass} mt-1 w-full`} /></label>
        <label className="text-xs text-secondary">资产类型<select aria-label="资产类型" value={assetType} onChange={event => setAssetType(event.target.value as typeof assetType)} className={`${controlClass} mt-1 w-full`}><option value="stock">股票</option><option value="etf">ETF</option><option value="index">指数</option></select></label>
        <label className="text-xs text-secondary">参数（可选 JSON）<textarea aria-label="参数（可选 JSON）" value={parameters} onChange={event => setParameters(event.target.value)} className={`${controlClass} mt-1 min-h-20 w-full font-mono`} /></label>
        <label className="text-xs text-secondary">方法<input required value={method} onChange={event => setMethod(event.target.value)} className={`${controlClass} mt-1 w-full`} /></label>
        <label className="text-xs text-secondary">指标<input required value={metrics} onChange={event => setMetrics(event.target.value)} className={`${controlClass} mt-1 w-full`} /></label>
        <label className="text-xs text-secondary md:col-span-2">成功/失败标准<input required value={criteria} onChange={event => setCriteria(event.target.value)} className={`${controlClass} mt-1 w-full`} /></label>
        <div className="md:col-span-2"><button type="submit" disabled={!researchAssetId || createSpec.isPending} className={primaryClass}>{createSpec.isPending ? '正在冻结实验规格…' : '新建实验规格'}</button>{(createSpec.isError || scopeError) && <p role="alert" className="mt-2 text-xs text-danger">无法创建实验规格：{scopeError ?? createSpec.error?.message ?? '请求未完成'}</p>}</div>
      </form>
      {specifications.map(spec => <article key={spec.id} className="mt-4 rounded-card border border-border bg-base/30 p-3 text-xs"><div className="flex flex-wrap items-center justify-between gap-2"><strong>不可变规格 v{spec.version}</strong><button className={controlClass} type="button" onClick={() => runExperiment.mutate(spec.id)}>运行受限实验</button></div><p className="mt-2 break-words text-secondary">{spec.hypothesis}</p><details className="mt-2"><summary className="min-h-11 cursor-pointer py-2 text-accent">查看证据与审计</summary><p>范围：{serialize(spec.data_scope.parameters)}；策略：{spec.data_scope.strategy_id}；期间：{spec.data_scope.start} 至 {spec.data_scope.end}</p></details></article>)}
      {runs.length === 0 && <p className="mt-4 text-xs text-muted">尚无实验规格</p>}
      <div className="mt-4 overflow-x-auto" tabIndex={0} aria-describedby="experiment-runs-scroll-instruction">
        <p id="experiment-runs-scroll-instruction" className="mb-2 text-xs text-muted">左右滚动查看完整记录</p>
        <table className="min-w-[920px] text-left text-xs"><caption className="sr-only">实验运行清单</caption><thead><tr className="border-b border-border"><th scope="col">状态</th><th scope="col">受治理指纹</th><th scope="col">独立执行证据</th><th scope="col">参数与资源</th><th scope="col">操作</th></tr></thead><tbody>{runs.map(run => {
          const completed = run.status === 'completed'
          const feedbackEligible = completed && !feedbackByRun.has(run.id)
          return <tr key={run.id} className="border-b border-border/60 align-top"><td className="py-2">{completed ? <span role="status">已完成</span> : `运行未完成：${run.constraint_reason ?? run.status}`}</td><td className="py-2 font-mono break-all">{run.governed_fingerprint}</td><td className="py-2">{completed && <ExecutionEvidence evidence={run.execution_evidence} />}</td><td className="py-2">{serialize(run.parameters)}；{serialize(run.resource_limits)}；工件 {run.artifact_count}</td><td className="py-2"><button type="button" className={controlClass} onClick={() => retryExperiment.mutate(run.id)}>以新运行重试</button>{completed && <button type="button" className={`${controlClass} ml-2`} onClick={() => createCandidate.mutate(run.id)}>创建演化候选</button>}<fieldset className="mt-2"><legend>记录研究反馈</legend>{(Object.keys(feedbackLabels) as AdvancedExperimentFeedback['conclusion'][]).map(value => <label key={value} className="mr-3 inline-flex min-h-11 items-center gap-1"><input type="radio" disabled={!feedbackEligible} checked={feedback[run.id] === value} onChange={() => setFeedback(current => ({ ...current, [run.id]: value }))} name={`feedback-${run.id}`} />{feedbackLabels[value]}</label>)}<input aria-label={`运行 ${run.id} 的反馈说明`} disabled={!feedbackEligible} value={notes[run.id] ?? ''} onChange={event => setNotes(current => ({ ...current, [run.id]: event.target.value }))} className={`${controlClass} mt-1`} /><button type="button" disabled={!feedbackEligible || !feedback[run.id] || !(notes[run.id] ?? '').trim()} onClick={() => recordFeedback.mutate({ runId: run.id, conclusion: feedback[run.id]!, comment: notes[run.id] })} className={`${controlClass} mt-1`}>记录研究反馈</button>{!feedbackEligible && <p className="mt-1 text-muted">此运行未完成或已有反馈，不能记录新的研究反馈。</p>}</fieldset></td></tr>
        })}</tbody></table>
      </div>
    </section>

    <section aria-labelledby="advanced-evolution-heading" className="border-t border-border pt-6"><h2 id="advanced-evolution-heading" className="text-base font-semibold">演化候选与门禁</h2><p className="mt-1 text-xs text-warning">排序不代表可晋级；所有门禁必须独立通过。</p>{candidateItems.map(candidate => <CandidateCard key={candidate.id} candidate={candidate} onEvaluate={gate => evaluateGate.mutate({ candidateId: candidate.id, gate })} onPromote={trigger => openPromotion(candidate.id, trigger)} />)}</section>

    <section aria-labelledby="advanced-sandbox-heading" className="border-t border-border pt-6"><h2 id="advanced-sandbox-heading" className="text-base font-semibold">自定义策略沙箱</h2><p className="mt-1 text-xs text-muted">合同与源码在同一受限请求中提交；提交后浏览器不会保留源码。</p><label className="mt-3 block text-xs text-secondary">受限策略源码<textarea value={source} onChange={event => setSource(event.target.value)} className={`${controlClass} mt-1 min-h-28 w-full font-mono`} /></label><details className="mt-2 text-xs"><summary className="min-h-11 cursor-pointer py-2 text-accent">查看机器可读合同</summary><p>允许输入：governed_panel；超时：5 秒；内存：128 MB。AST、导入、超时和内存均由服务端验证。</p></details><button type="button" disabled={!researchAssetId || !source || submitSandbox.isPending} onClick={() => submitSandbox.mutate()} className={`${primaryClass} mt-3`}>{submitSandbox.isPending ? '正在检查策略合同与限制…' : '验证并运行受限策略'}</button>{sandboxFailure && <div ref={failureRef} tabIndex={-1} role="alert" className="mt-3 text-xs text-danger">{sandboxFailure.status === 'constraint_failed' ? '沙箱已终止' : '策略未运行'}：{sandboxFailure.reason}。审计参考：{sandboxFailure.audit_reference}</div>}<SandboxRunTable runs={sandboxRunItems} /></section>

    {candidateForPromotion && <div role="dialog" aria-modal="true" aria-labelledby="promotion-dialog-title" className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" onKeyDown={handlePromotionKeyDown}><div ref={dialogRef} className="w-full max-w-lg rounded-dialog border border-border bg-surface p-5"><h3 id="promotion-dialog-title" ref={dialogHeadingRef} tabIndex={-1} className="text-base font-semibold focus:outline-none">确认晋级为研究策略</h3><p className="mt-2 text-xs text-secondary">候选 {currentCandidate?.parent_version ?? '当前版本'} 已由五项门禁审阅。晋级只注册研究策略版本，不会启用监控、创建交易计划或执行市场动作。</p><label className="mt-4 block text-xs">批准理由（至少 10 个字符）<textarea ref={promotionReasonRef} value={rationale} onChange={event => setRationale(event.target.value)} className={`${controlClass} mt-1 min-h-24 w-full`} /></label>{promote.isError && <p role="alert" className="mt-2 text-xs text-danger">晋级未记录：状态已变化，请重新查看门禁。</p>}<div className="mt-4 flex flex-wrap justify-end gap-2"><button type="button" className={controlClass} onClick={closePromotion}>返回候选</button><button type="button" disabled={rationale.trim().length < 10 || promote.isPending} onClick={() => promote.mutate({ candidateId: candidateForPromotion, reason: rationale })} className={primaryClass}>确认晋级为研究策略</button></div></div></div>}
  </div>
}

function CandidateCard({ candidate, onEvaluate, onPromote }: { candidate: AdvancedCandidate; onEvaluate: (gate: keyof typeof GATE_LABELS) => void; onPromote: (trigger: HTMLButtonElement) => void }) {
  const allPassed = candidate.gates.length === 5 && candidate.gates.every(gate => gate.status === 'passed')
  return <article className="mt-4 rounded-card border border-border p-3 text-xs"><p>父策略 {candidate.parent_version}；变异 {candidate.mutation}；种子 {candidate.seed}；配置 {serialize(candidate.resolved_config)}</p><div className="mt-3 overflow-x-auto" tabIndex={0} aria-describedby={`gate-scroll-instruction-${candidate.id}`}><p id={`gate-scroll-instruction-${candidate.id}`} className="mb-2 text-xs text-muted">左右滚动查看完整记录</p><table className="min-w-[620px] text-left"><caption className="sr-only">晋级门禁</caption><thead><tr><th scope="col">门禁</th><th scope="col">状态</th><th scope="col">受控证据</th><th scope="col">操作</th></tr></thead><tbody>{Object.entries(GATE_LABELS).map(([key, label]) => { const gate = candidate.gates.find(item => item.name === key || item.name === label); return <tr key={key} className="border-t border-border/60"><th scope="row" className="py-2">{label}</th><td className="py-2">{gate?.status === 'passed' ? '通过' : gate?.status === 'failed' ? '未通过' : '缺少证据'}</td><td className="py-2 break-words">{gate?.evidence ?? '尚无受控证据'}</td><td className="py-2"><button type="button" className={controlClass} disabled={!!gate} onClick={() => onEvaluate(key as keyof typeof GATE_LABELS)}>评估门禁：{label}</button></td></tr> })}</tbody></table></div><button type="button" disabled={!allPassed} onClick={event => onPromote(event.currentTarget)} className={`${primaryClass} mt-3`}>批准晋级为研究策略</button></article> }

function SandboxRunTable({ runs }: { runs: AdvancedSandboxRun[] }) {
  if (!runs.length) return <p className="mt-4 text-xs text-muted">暂无终态沙箱运行记录</p>
  return <div className="mt-4 overflow-x-auto" tabIndex={0} aria-describedby="sandbox-runs-scroll-instruction">
    <p id="sandbox-runs-scroll-instruction" className="mb-2 text-xs text-muted">左右滚动查看完整记录</p>
    <table className="min-w-[680px] text-left text-xs"><caption className="mb-2 text-left text-sm font-semibold text-foreground">终态沙箱运行</caption><thead><tr className="border-b border-border"><th scope="col">状态</th><th scope="col">安全原因</th><th scope="col">Proof 指纹</th><th scope="col">资源摘要</th><th scope="col">时间与审计</th></tr></thead><tbody>{runs.map(run => <tr key={run.run_id} className="border-b border-border/60"><td className="py-2">{run.status === 'completed' ? <span role="status">已完成</span> : '沙箱已终止'}</td><td className="py-2">{run.terminal_reason ?? '未提供安全原因'}</td><td className="py-2 font-mono break-all">{run.proof_fingerprint ?? '未提供'}</td><td className="py-2">{serialize(run.resources)}</td><td className="py-2">{run.created_at}<details><summary className="cursor-pointer text-accent">查看证据与审计</summary><p className="mt-1">审计参考：{run.audit_reference ?? '未提供'}</p></details></td></tr>)}</tbody></table>
  </div>
}
