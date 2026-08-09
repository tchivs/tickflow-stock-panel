import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Play, Save, Sparkles } from 'lucide-react'
import { api, type FactorEvaluation, type FactorEvaluationRequest, type FactorRevision, type HypothesisDraft, type ResearchExperiment, type SimilarityCandidate } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

const INPUT_CLS = 'w-full rounded-input border border-border bg-base px-2.5 py-1.5 text-xs text-foreground focus:border-accent focus-visible:ring-2 focus-visible:ring-accent/60'
const DEFAULT_EVALUATION: FactorEvaluationRequest = {
  universe: '沪深A股样本', symbols: ['600519.SH', '000001.SZ'], asset_type: 'stock', start: '2024-01-01', end: '2024-06-30',
  forward_return_horizon: 5, rebalance: 'weekly', missing_data_treatment: 'drop', warmup_treatment: 'exclude', warmup_days: 20,
  n_groups: 5, weight: 'equal', fees_pct: 0.0002, slippage_bps: 5,
}

function JsonDetails({ label, value }: { label: string; value: unknown }) {
  return <details className="rounded-btn border border-border bg-base/40 p-2 text-xs"><summary className="cursor-pointer font-medium text-secondary">{label}</summary><pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words text-[11px] text-muted">{JSON.stringify(value, null, 2)}</pre></details>
}

function Evidence({ evaluation, experiment }: { evaluation: FactorEvaluation; experiment: ResearchExperiment }) {
  const ic = evaluation.ic_summary
  const rank = evaluation.rank_ic_summary
  return <section aria-label="研究证据" className="space-y-3 rounded-card border border-border bg-surface p-3">
    <div className="flex flex-wrap items-center justify-between gap-2"><div><h3 className="text-sm font-semibold">已完成的评估证据</h3><p className="text-xs text-muted">完成不等于已保留；未保留的证据不可比较。</p></div><span className="rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-1 text-[11px] text-amber-500">已完成，未保留</span></div>
    <div className="grid gap-2 sm:grid-cols-2"><div className="rounded-btn border border-border p-3"><div className="text-xs font-medium text-secondary">Pearson IC</div><div className="mt-1 font-mono text-lg">{ic?.mean?.toFixed(4) ?? '—'}</div><div className="text-[11px] text-muted">{ic?.observations ?? 0} 个截面观察</div></div><div className="rounded-btn border border-border p-3"><div className="text-xs font-medium text-secondary">RankIC（Spearman）</div><div className="mt-1 font-mono text-lg">{rank?.mean?.toFixed(4) ?? '—'}</div><div className="text-[11px] text-muted">{rank?.observations ?? 0} 个截面观察</div></div></div>
    <div className="grid gap-2 lg:grid-cols-2"><JsonDetails label="已解析配置" value={evaluation.resolved_config} /><JsonDetails label="受治理输入清单" value={evaluation.input_manifest} /><JsonDetails label="预测 / 信号元数据" value={experiment.prediction_signals} /><JsonDetails label="度量与补充证据" value={{ ic_summary: ic, rank_ic_summary: rank, group_stats: evaluation.group_stats, long_short_stats: evaluation.long_short_stats }} /><JsonDetails label="受管工件引用" value={evaluation.artifacts} /><JsonDetails label="模型 / 提供商版本" value={experiment.model_provenance} /></div>
  </section>
}

export function FactorBacktest() {
  const queryClient = useQueryClient()
  const [name, setName] = useState('短期动量')
  const [expression, setExpression] = useState('close / ma20')
  const [description, setDescription] = useState('收盘价相对20日均线')
  const [hypothesis, setHypothesis] = useState('价格相对均线反映趋势强度')
  const [validation, setValidation] = useState<string | null>(null)
  const [similarity, setSimilarity] = useState<SimilarityCandidate[]>([])
  const [saved, setSaved] = useState<FactorRevision | null>(null)
  const [evaluation, setEvaluation] = useState<{ evaluation: FactorEvaluation; experiment: ResearchExperiment } | null>(null)
  const [symbolsText, setSymbolsText] = useState(DEFAULT_EVALUATION.symbols.join(', '))
  const [naturalLanguage, setNaturalLanguage] = useState('寻找价格相对均线的趋势因子')
  const [draft, setDraft] = useState<HypothesisDraft | null>(null)
  const [reviewed, setReviewed] = useState(false)

  const options = useQuery({ queryKey: QK.researchDslOptions, queryFn: api.researchDslOptions })
  const validate = useMutation({ mutationFn: async (candidateExpression: string) => {
    const validated = await api.validateResearchDsl(candidateExpression)
    const similar = await api.researchSimilarity({ expression: validated.normalized_expression })
    return { validated, similar }
  }, onSuccess: ({ validated, similar }) => { setValidation(validated.normalized_expression); setSimilarity(similar.candidates) } })
  const save = useMutation({ mutationFn: () => api.saveResearchFactor({ name, expression, description, hypothesis }), onSuccess: data => { setSaved(data); setValidation(data.canonical_expression); queryClient.invalidateQueries({ queryKey: QK.researchFactors }) } })
  const createDraft = useMutation({ mutationFn: () => api.draftResearchHypothesis(naturalLanguage), onSuccess: data => { setDraft(data); setExpression(data.normalized_expression); setHypothesis(data.hypothesis); setDescription(data.explanation); setReviewed(false); setValidation(null) } })
  const reviewDraft = useMutation({ mutationFn: () => {
    if (!draft) throw new Error('请先生成可审阅草稿')
    return api.saveReviewedHypothesis({ draft_id: draft.draft_id, name, expression: draft.normalized_expression, explanation: draft.explanation, provenance: draft.provenance, reviewed: true, description: draft.explanation })
  }, onSuccess: data => { setSaved(data); queryClient.invalidateQueries({ queryKey: QK.researchFactors }) } })
  const evaluate = useMutation({ mutationFn: () => {
    if (!saved) throw new Error('请先保存并验证因子修订版')
    const symbols = symbolsText.split(',').map(value => value.trim()).filter(Boolean)
    return api.evaluateResearchFactor(saved.id, { ...DEFAULT_EVALUATION, symbols })
  }, onSuccess: data => { setEvaluation(data); queryClient.invalidateQueries({ queryKey: QK.researchExperiments }) } })
  const retain = useMutation({ mutationFn: () => {
    if (!evaluation) throw new Error('没有完成的评估证据可保留')
    return api.retainResearchExperiment(evaluation.experiment.id)
  }, onSuccess: data => { if (evaluation) setEvaluation({ ...evaluation, experiment: data }); queryClient.invalidateQueries({ queryKey: QK.researchExperiments }); queryClient.invalidateQueries({ queryKey: QK.researchComparisonCandidates }) } })

  const validationError = validate.isError ? String(validate.error.message) : null
  const draftError = createDraft.isError ? String(createDraft.error.message) : null
  const canEvaluate = saved !== null && (draft === null || reviewed)
  const retained = evaluation?.experiment.retained_at != null
  const fieldHint = useMemo(() => options.data ? `DSL ${options.data.dsl_version}：${options.data.fields.join('、')}` : '加载 DSL 选项中…', [options.data])

  return <div className="space-y-4">
    <section aria-label="手动因子工作流" className="grid gap-4 rounded-card border border-border bg-surface p-3 xl:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="space-y-3"><div><h2 className="text-sm font-semibold">手动因子定义</h2><p className="mt-0.5 text-xs text-muted">先验证受限 DSL，再保存不可变修订版；相似性只供审阅，绝不阻塞保存。</p></div>
        <label className="block text-xs font-medium text-secondary">因子名称<input aria-label="因子名称" className={`${INPUT_CLS} mt-1`} value={name} onChange={event => setName(event.target.value)} /></label>
        <label className="block text-xs font-medium text-secondary">受限 DSL 表达式<textarea aria-label="受限 DSL 表达式" className={`${INPUT_CLS} mt-1 min-h-16 font-mono`} value={expression} onChange={event => { setExpression(event.target.value); setValidation(null); setSaved(null) }} /></label>
        <p className="text-[11px] text-muted">{fieldHint}</p>
        <label className="block text-xs font-medium text-secondary">说明<input aria-label="因子说明" className={`${INPUT_CLS} mt-1`} value={description} onChange={event => setDescription(event.target.value)} /></label>
        <div className="flex flex-wrap gap-2"><button type="button" onClick={() => validate.mutate(expression)} className="inline-flex items-center gap-1 rounded-btn border border-accent/40 px-3 py-1.5 text-xs text-accent"><CheckCircle2 className="h-3.5 w-3.5" />验证表达式</button><button type="button" disabled={!validation || save.isPending} onClick={() => save.mutate()} className="inline-flex items-center gap-1 rounded-btn bg-accent-solid px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"><Save className="h-3.5 w-3.5" />保存修订版</button></div>
        {validation && <p role="status" className="rounded-btn border border-accent/30 bg-accent/10 px-2 py-1.5 text-xs text-accent">已验证：{validation}</p>}{validationError && <p role="alert" className="rounded-btn border border-danger/30 bg-danger/10 px-2 py-1.5 text-xs text-danger">验证失败：{validationError}</p>}{saved && <p role="status" className="rounded-btn border border-accent/30 bg-accent/10 px-2 py-1.5 text-xs text-accent">已保存修订版 #{saved.revision_number} · {saved.id}</p>}
      </div>
      <aside aria-label="相似因子候选" className="rounded-btn border border-border bg-base/30 p-3"><h3 className="text-xs font-semibold">相似因子候选</h3><p className="mt-1 text-[11px] text-muted">确定性结构、字段和操作符重叠解释。</p><div className="mt-2 space-y-2">{similarity.length === 0 ? <p className="text-xs text-muted">验证后显示候选；没有候选不会阻止保存。</p> : similarity.map(candidate => <div key={candidate.revision.id} className="rounded-btn border border-border p-2 text-xs"><div className="font-medium">{candidate.revision.name} · {candidate.score.toFixed(2)}</div><div className="mt-1 text-muted">{candidate.reason}</div></div>)}</div></aside>
    </section>

    <section aria-label="自然语言假设审阅" className="rounded-card border border-border bg-surface p-3"><div className="flex flex-wrap items-start justify-between gap-2"><div><h2 className="text-sm font-semibold">自然语言假设草稿</h2><p className="text-xs text-muted">草稿仅供审阅，不会持久化、保存或进入比较。</p></div><span className="rounded-full border border-border px-2 py-1 text-[11px] text-muted">{draft ? '草稿：不可比较' : '未创建草稿'}</span></div>
      <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]"><label className="text-xs font-medium text-secondary">研究假设<textarea aria-label="研究假设" className={`${INPUT_CLS} mt-1 min-h-16`} value={naturalLanguage} onChange={event => setNaturalLanguage(event.target.value)} /></label><button type="button" onClick={() => createDraft.mutate()} className="inline-flex h-fit items-center gap-1 rounded-btn border border-accent/40 px-3 py-1.5 text-xs text-accent"><Sparkles className="h-3.5 w-3.5" />生成审阅草稿</button></div>
      {draftError && <p role="alert" className="mt-2 text-xs text-danger">草稿无效：{draftError}</p>}
      {draft && <div className="mt-3 space-y-2 rounded-btn border border-accent/30 bg-accent/5 p-3 text-xs"><div><strong>非持久化表达式：</strong><code>{draft.normalized_expression}</code></div><div><strong>解释：</strong>{draft.explanation}</div><JsonDetails label="模型 / 提供商来源" value={draft.provenance} /><label className="flex items-center gap-2 text-secondary"><input aria-label="我已审阅草稿" type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />我已审阅表达式、解释和模型来源</label><button type="button" disabled={!reviewed || reviewDraft.isPending} onClick={() => reviewDraft.mutate()} className="rounded-btn bg-accent-solid px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40">确认审阅并保存修订版</button></div>}
    </section>

    <section aria-label="评估与保留" className="rounded-card border border-border bg-surface p-3"><div className="flex flex-wrap items-center justify-between gap-2"><div><h2 className="text-sm font-semibold">评估与保留</h2><p className="text-xs text-muted">只有已保存修订版可评估；只有已完成且显式保留的快照可比较。</p></div><span className="text-[11px] text-muted">{saved ? `修订版 ${saved.revision_number}` : '尚未保存'}</span></div><label className="mt-3 block text-xs font-medium text-secondary">受治理标的（逗号分隔）<input aria-label="受治理标的" className={`${INPUT_CLS} mt-1 font-mono`} value={symbolsText} onChange={event => setSymbolsText(event.target.value)} /></label><button type="button" disabled={!canEvaluate || evaluate.isPending} onClick={() => evaluate.mutate()} className="mt-3 inline-flex items-center gap-1 rounded-btn bg-accent-solid px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"><Play className="h-3.5 w-3.5" />运行受治理因子评估</button>{evaluate.isError && <p role="alert" className="mt-2 text-xs text-danger">评估失败：{evaluate.error.message}</p>}{evaluation && <div className="mt-3 space-y-3"><Evidence evaluation={evaluation.evaluation} experiment={evaluation.experiment} />{retained ? <p role="status" className="rounded-btn border border-bull/30 bg-bull/10 px-3 py-2 text-xs text-bull">已保留：此完成快照现在可在比较中选择。</p> : <button type="button" disabled={retain.isPending} onClick={() => retain.mutate()} className="rounded-btn border border-amber-400/40 px-3 py-1.5 text-xs text-amber-500">显式保留此完成证据以供比较</button>}</div>}</section>
  </div>
}
