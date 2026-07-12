import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, type AdvancedExperimentFeedback, type AdvancedSandboxValidation } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

const GATE_LABELS: Record<string, string> = {
  contract_sandbox_safety: '合同/沙箱安全',
  provenance: '来源完整性',
  in_sample_out_of_sample_evidence: '样本内与样本外',
  robustness: '稳健性',
  cost_feasibility: '成本与可实现性',
}

const feedbackLabels: Record<AdvancedExperimentFeedback['conclusion'], string> = {
  supported: '支持', refuted: '证伪', inconclusive: '无结论', needs_replication: '需要复现',
}

const controlClass = 'min-h-11 rounded-btn border border-border bg-base px-3 py-2 text-xs text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface disabled:cursor-not-allowed disabled:opacity-45'
const primaryClass = `${controlClass} border-accent bg-accent text-white hover:bg-accent/90`

function serialize(value: Record<string, string | number | boolean>) {
  return Object.entries(value).map(([key, item]) => `${key}: ${String(item)}`).join(' · ') || '无额外受控参数'
}

async function sourceHash(source: string) {
  const bytes = new TextEncoder().encode(source)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  return [...new Uint8Array(digest)].map(item => item.toString(16).padStart(2, '0')).join('')
}

export function AdvancedResearchPanels({ researchAssetId }: { researchAssetId: string | null }) {
  const queryClient = useQueryClient()
  const [hypothesis, setHypothesis] = useState('')
  const [dataScope, setDataScope] = useState('CN-A')
  const [method, setMethod] = useState('bounded-backtest')
  const [metrics, setMetrics] = useState('sharpe')
  const [criteria, setCriteria] = useState('风险调整收益达到受控阈值')
  const [feedback, setFeedback] = useState<Record<string, AdvancedExperimentFeedback['conclusion']>>({})
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [candidateForPromotion, setCandidateForPromotion] = useState<string | null>(null)
  const [rationale, setRationale] = useState('')
  const [source, setSource] = useState('')
  const [sandboxResult, setSandboxResult] = useState<AdvancedSandboxValidation | null>(null)
  const dialogHeadingRef = useRef<HTMLHeadingElement>(null)
  const failureRef = useRef<HTMLDivElement>(null)

  const experiments = useQuery({ queryKey: QK.advancedExperiments(researchAssetId ?? 'none'), queryFn: api.advancedExperiments })
  const candidates = useQuery({ queryKey: QK.advancedCandidates, queryFn: api.advancedCandidates })
  const sandboxHistory = useQuery({ queryKey: QK.advancedSandboxValidations, queryFn: api.advancedSandboxValidations })
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: QK.advancedExperiments(researchAssetId ?? 'none') })
    queryClient.invalidateQueries({ queryKey: QK.advancedCandidates })
    queryClient.invalidateQueries({ queryKey: QK.advancedSandboxValidations })
  }
  const createSpec = useMutation({ mutationFn: api.advancedCreateExperiment, onSuccess: invalidate })
  const runExperiment = useMutation({ mutationFn: api.advancedRunExperiment, onSuccess: invalidate })
  const retryExperiment = useMutation({ mutationFn: api.advancedRetryExperiment, onSuccess: invalidate })
  const recordFeedback = useMutation({ mutationFn: ({ runId, conclusion, comment }: { runId: string; conclusion: AdvancedExperimentFeedback['conclusion']; comment: string }) => api.advancedRecordFeedback(runId, conclusion, comment), onSuccess: invalidate })
  const promote = useMutation({ mutationFn: ({ candidateId, reason }: { candidateId: string; reason: string }) => api.advancedPromoteCandidate(candidateId, reason), onSuccess: () => { invalidate(); setCandidateForPromotion(null); setRationale('') } })
  const submitSandbox = useMutation({
    mutationFn: async () => {
      if (!researchAssetId) throw new Error('请先选择受控研究策略。')
      const hash = await sourceHash(source)
      return api.advancedSubmitSandbox({ contract: { contract_version: 'advanced-strategy-v1', parent_asset_id: researchAssetId, declared_inputs: ['governed_panel'], declared_imports: [], timeout_seconds: 5, memory_limit_mb: 128, source_sha256: hash }, source })
    },
    onSuccess: result => { setSandboxResult(result.validation); setSource(''); invalidate() },
  })

  useEffect(() => { if (candidateForPromotion) dialogHeadingRef.current?.focus() }, [candidateForPromotion])
  useEffect(() => { if (sandboxResult?.status !== 'validated') failureRef.current?.focus() }, [sandboxResult])

  const runs = experiments.data?.runs ?? []
  const feedbackByRun = new Set((experiments.data?.feedback ?? []).map(item => item.run_id))
  const sandboxFailure = sandboxResult?.status !== 'validated' ? sandboxResult : sandboxHistory.data?.validations.find(item => item.status !== 'validated')

  return <div className="space-y-8" aria-label="高级研究工作流">
    <section aria-labelledby="advanced-experiment-heading" className="border-t border-border pt-6">
      <h2 id="advanced-experiment-heading" className="text-base font-semibold text-foreground">实验规格与运行</h2>
      <p className="mt-1 max-w-[65ch] text-xs text-muted">规格提交后冻结；每次重试都会保留为新的受限运行。</p>
      <form className="mt-4 grid gap-3 md:grid-cols-2" onSubmit={event => { event.preventDefault(); if (!researchAssetId) return; createSpec.mutate({ research_asset_id: researchAssetId, hypothesis, data_scope: { market: dataScope }, method, metrics: metrics.split(',').map(item => item.trim()).filter(Boolean), success_criteria: { summary: criteria }, failure_criteria: { summary: '不满足受控成功标准' } }) }}>
        <label className="text-xs text-secondary">假设<textarea required value={hypothesis} onChange={event => setHypothesis(event.target.value)} className={`${controlClass} mt-1 min-h-20`} /></label>
        <label className="text-xs text-secondary">数据范围<select value={dataScope} onChange={event => setDataScope(event.target.value)} className={`${controlClass} mt-1`}><option>CN-A</option></select></label>
        <label className="text-xs text-secondary">方法<input required value={method} onChange={event => setMethod(event.target.value)} className={`${controlClass} mt-1`} /></label>
        <label className="text-xs text-secondary">指标<input required value={metrics} onChange={event => setMetrics(event.target.value)} className={`${controlClass} mt-1`} /></label>
        <label className="text-xs text-secondary md:col-span-2">成功/失败标准<input required value={criteria} onChange={event => setCriteria(event.target.value)} className={`${controlClass} mt-1`} /></label>
        <div className="md:col-span-2"><button type="submit" disabled={!researchAssetId || createSpec.isPending} className={primaryClass}>{createSpec.isPending ? '正在冻结实验规格…' : '新建实验规格'}</button>{createSpec.isError && <p role="alert" className="mt-2 text-xs text-danger">无法创建实验规格：{createSpec.error.message}</p>}</div>
      </form>
      {experiments.data?.specifications.map(spec => <article key={spec.id} className="mt-4 rounded-card border border-border bg-base/30 p-3 text-xs"><div className="flex flex-wrap items-center justify-between gap-2"><strong>不可变规格 v{spec.version}</strong><button className={controlClass} type="button" onClick={() => runExperiment.mutate(spec.id)}>运行受限实验</button></div><p className="mt-2 break-words text-secondary">{spec.hypothesis}</p><details className="mt-2"><summary className="min-h-11 cursor-pointer py-2 text-accent">查看证据与审计</summary><p>范围：{serialize(spec.data_scope)}；方法：{spec.method}；指标：{spec.metrics.join('、')}</p></details></article>)}
      {runs.length === 0 && <p className="mt-4 text-xs text-muted">尚无实验规格</p>}
      <div className="mt-4 overflow-x-auto" tabIndex={0}><p className="mb-2 text-xs text-muted">左右滚动查看完整记录</p><table className="min-w-[760px] text-left text-xs"><caption className="sr-only">实验运行清单</caption><thead><tr className="border-b border-border"><th scope="col">状态</th><th scope="col">受治理指纹</th><th scope="col">资产版本</th><th scope="col">资源/工件</th><th scope="col">操作</th></tr></thead><tbody>{runs.map(run => { const eligible = run.status === 'completed' && !feedbackByRun.has(run.id); return <tr key={run.id} className="border-b border-border/60 align-top"><td className="py-2">{run.status === 'completed' ? '已完成' : `运行未完成：${run.constraint_reason ?? run.status}`}</td><td className="py-2 font-mono break-all">{run.governed_fingerprint}</td><td className="py-2">{run.asset_version ?? '未提供'}</td><td className="py-2">{serialize(run.resource_limits)}；工件 {run.artifact_count}</td><td className="py-2"><button type="button" className={controlClass} onClick={() => retryExperiment.mutate(run.id)}>以新运行重试</button><fieldset className="mt-2"><legend>记录研究反馈</legend>{(Object.keys(feedbackLabels) as AdvancedExperimentFeedback['conclusion'][]).map(value => <label key={value} className="mr-3 inline-flex min-h-11 items-center gap-1"><input type="radio" disabled={!eligible} checked={feedback[run.id] === value} onChange={() => setFeedback(current => ({ ...current, [run.id]: value }))} name={`feedback-${run.id}`} />{feedbackLabels[value]}</label>)}<input aria-label={`运行 ${run.id} 的反馈说明`} disabled={!eligible} value={notes[run.id] ?? ''} onChange={event => setNotes(current => ({ ...current, [run.id]: event.target.value }))} className={`${controlClass} mt-1`} /><button type="button" disabled={!eligible || !feedback[run.id] || !(notes[run.id] ?? '').trim()} onClick={() => recordFeedback.mutate({ runId: run.id, conclusion: feedback[run.id]!, comment: notes[run.id] })} className={`${controlClass} mt-1`}>记录研究反馈</button>{!eligible && <p className="mt-1 text-muted">此运行未完成，不能记录研究反馈。</p>}</fieldset></td></tr> })}</tbody></table></div>
    </section>

    <section aria-labelledby="advanced-evolution-heading" className="border-t border-border pt-6"><h2 id="advanced-evolution-heading" className="text-base font-semibold">演化候选与门禁</h2><p className="mt-1 text-xs text-warning">排序不代表可晋级；所有门禁必须独立通过。</p>{(candidates.data?.candidates ?? []).map(candidate => { const gates = candidate.gates; const allPassed = gates.length === 5 && gates.every(gate => gate.status === 'passed'); return <article key={candidate.id} className="mt-4 rounded-card border border-border p-3 text-xs"><p>父策略 {candidate.parent_version}；变异 {candidate.mutation}；种子 {candidate.seed}</p><div className="mt-3 overflow-x-auto" tabIndex={0}><table className="min-w-[620px] text-left"><caption className="sr-only">晋级门禁</caption><thead><tr><th scope="col">门禁</th><th scope="col">状态</th><th scope="col">受控证据</th></tr></thead><tbody>{Object.entries(GATE_LABELS).map(([key, label]) => { const gate = gates.find(item => item.name === key || item.name === label); return <tr key={key} className="border-t border-border/60"><th scope="row" className="py-2">{label}</th><td className="py-2">{gate?.status === 'passed' ? '通过' : gate?.status === 'failed' ? '未通过' : '缺少证据'}</td><td className="py-2 break-words">{gate?.evidence ?? '尚无受控证据'}</td></tr> })}</tbody></table></div><button type="button" disabled={!allPassed} onClick={() => setCandidateForPromotion(candidate.id)} className={`${primaryClass} mt-3`}>批准晋级为研究策略</button></article> })}</section>

    <section aria-labelledby="advanced-sandbox-heading" className="border-t border-border pt-6"><h2 id="advanced-sandbox-heading" className="text-base font-semibold">自定义策略沙箱</h2><p className="mt-1 text-xs text-muted">合同与源码在同一受限请求中提交；提交后浏览器不会保留源码。</p><label className="mt-3 block text-xs text-secondary">受限策略源码<textarea value={source} onChange={event => setSource(event.target.value)} className={`${controlClass} mt-1 min-h-28 font-mono`} /></label><details className="mt-2 text-xs"><summary className="min-h-11 cursor-pointer py-2 text-accent">查看机器可读合同</summary><p>允许输入：governed_panel；超时：5 秒；内存：128 MB。AST、导入、超时和内存均由服务端验证。</p></details><button type="button" disabled={!researchAssetId || !source || submitSandbox.isPending} onClick={() => submitSandbox.mutate()} className={`${primaryClass} mt-3`}>{submitSandbox.isPending ? '正在检查策略合同与限制…' : '验证并运行受限策略'}</button>{sandboxFailure && <div ref={failureRef} tabIndex={-1} role="alert" className="mt-3 text-xs text-danger">{sandboxFailure.status === 'constraint_failed' ? '沙箱已终止' : '策略未运行'}：{sandboxFailure.reason}。审计参考：{sandboxFailure.audit_reference}</div>}{sandboxResult?.status === 'validated' && <p role="status" className="mt-3 text-xs text-secondary">沙箱验证已记录：{sandboxResult.source_sha256}</p>}</section>

    {candidateForPromotion && <div role="dialog" aria-modal="true" aria-labelledby="promotion-dialog-title" className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4" onKeyDown={event => { if (event.key === 'Escape') setCandidateForPromotion(null) }}><div className="w-full max-w-lg rounded-dialog border border-border bg-surface p-5"><h3 id="promotion-dialog-title" ref={dialogHeadingRef} tabIndex={-1} className="text-base font-semibold focus:outline-none">确认晋级为研究策略</h3><p className="mt-2 text-xs text-secondary">晋级只注册研究策略版本，不会启用监控、创建交易计划或执行市场动作。</p><label className="mt-4 block text-xs">批准理由（至少 10 个字符）<textarea autoFocus value={rationale} onChange={event => setRationale(event.target.value)} className={`${controlClass} mt-1 min-h-24`} /></label>{promote.isError && <p role="alert" className="mt-2 text-xs text-danger">晋级未记录：状态已变化，请重新查看门禁。</p>}<div className="mt-4 flex flex-wrap justify-end gap-2"><button type="button" className={controlClass} onClick={() => setCandidateForPromotion(null)}>返回候选</button><button type="button" disabled={rationale.trim().length < 10 || promote.isPending} onClick={() => promote.mutate({ candidateId: candidateForPromotion, reason: rationale })} className={primaryClass}>确认晋级为研究策略</button></div></div></div>}
  </div>
}
