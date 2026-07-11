import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, History, Layers3 } from 'lucide-react'
import { api, type ResearchExperiment } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

function Subject({ experiment }: { experiment: ResearchExperiment }) {
  return experiment.subject.kind === 'factor'
    ? <>因子修订版 <code>{experiment.subject.revision_id}</code></>
    : <>注册策略 {experiment.subject.id} · {experiment.subject.version}</>
}

function ArtifactList({ experiment }: { experiment: ResearchExperiment }) {
  return <details className="mt-2 text-[11px] text-muted"><summary className="cursor-pointer">工件 {experiment.artifacts.length} 个</summary><ul className="mt-1 space-y-1">{experiment.artifacts.map(artifact => <li key={`${artifact.relative_path}-${artifact.checksum_sha256}`}><code>{artifact.relative_path}</code> · {artifact.content_type} · {artifact.byte_size} B</li>)}</ul></details>
}

export function ResearchLibrary() {
  const queryClient = useQueryClient()
  const [selectedFactorId, setSelectedFactorId] = useState<string | null>(null)
  const factors = useQuery({ queryKey: QK.researchFactors, queryFn: api.researchFactors })
  const revisions = useQuery({ queryKey: QK.researchFactorRevisions(selectedFactorId ?? ''), queryFn: () => api.researchFactorRevisions(selectedFactorId ?? ''), enabled: selectedFactorId !== null })
  const experiments = useQuery({ queryKey: QK.researchExperiments, queryFn: api.researchExperiments })
  const retain = useMutation({ mutationFn: api.retainResearchExperiment, onSuccess: () => { queryClient.invalidateQueries({ queryKey: QK.researchExperiments }); queryClient.invalidateQueries({ queryKey: QK.researchComparisonCandidates }) } })

  return <section aria-label="研究资料库" className="grid gap-4 xl:grid-cols-2">
    <article className="rounded-card border border-border bg-surface p-3"><div className="flex items-center gap-2"><Layers3 className="h-4 w-4 text-accent" /><div><h2 className="text-sm font-semibold">因子资料库</h2><p className="text-xs text-muted">保存的定义显示不可变修订版；相似因子不会自动合并。</p></div></div><div className="mt-3 space-y-2">{factors.isLoading && <p className="text-xs text-muted">加载资料库…</p>}{factors.data?.factors.length === 0 && <p className="text-xs text-muted">尚无保存的因子修订版。</p>}{factors.data?.factors.map(factor => <div key={factor.id} className="rounded-btn border border-border bg-base/25 p-2 text-xs"><div className="flex justify-between gap-2"><strong>{factor.name}</strong><span className="text-muted">修订 {factor.revision_number}</span></div><code className="mt-1 block overflow-x-auto text-[11px] text-accent">{factor.canonical_expression}</code><p className="mt-1 text-muted">{factor.description || factor.hypothesis || '未提供说明'}</p><div className="mt-2 flex items-center justify-between gap-2"><span className="text-[11px] text-muted">DSL {factor.dsl_version} · {factor.created_at}</span><button type="button" onClick={() => setSelectedFactorId(factor.factor_id)} className="rounded-btn border border-border px-2 py-1 text-[11px] text-secondary">查看修订历史</button></div></div>)}</div>{selectedFactorId && <div className="mt-3 rounded-btn border border-border bg-base/30 p-2 text-xs"><div className="flex justify-between gap-2"><strong>不可变修订历史</strong><button type="button" onClick={() => setSelectedFactorId(null)} className="text-muted">关闭</button></div>{revisions.isLoading && <p className="mt-2 text-muted">加载修订历史…</p>}<ol className="mt-2 space-y-1">{revisions.data?.revisions.map(item => <li key={item.id}><span className="text-muted">#{item.revision_number}</span> <code>{item.canonical_expression}</code> <span className="text-muted">· {item.created_at}</span></li>)}</ol></div>}</article>
    <article className="rounded-card border border-border bg-surface p-3"><div className="flex items-center gap-2"><History className="h-4 w-4 text-accent" /><div><h2 className="text-sm font-semibold">实验历史</h2><p className="text-xs text-muted">完成但未保留的快照保留证据，不会进入比较候选。</p></div></div><div className="mt-3 space-y-2">{experiments.isLoading && <p className="text-xs text-muted">加载实验历史…</p>}{experiments.data?.experiments.length === 0 && <p className="text-xs text-muted">尚无实验快照。</p>}{experiments.data?.experiments.map(experiment => <div key={experiment.id} className="rounded-btn border border-border bg-base/25 p-2 text-xs"><div className="flex flex-wrap items-center justify-between gap-2"><strong><Subject experiment={experiment} /></strong><span className={experiment.retained_at ? 'text-bull' : 'text-amber-500'}>{experiment.retained_at ? '已保留' : '完成但未保留'}</span></div><div className="mt-1 text-muted">状态：{experiment.status} · 已验证：{experiment.validated ? '是' : '否'} · {experiment.created_at}</div><div className="mt-1 text-muted">输入：{String(experiment.input_manifest.universe ?? experiment.resolved_config.universe ?? '—')}</div><div className="mt-1 text-muted">模型：{experiment.model_provenance ? `${experiment.model_provenance.provider}/${experiment.model_provenance.model} ${experiment.model_provenance.model_version ?? ''}` : '无模型来源'}</div><ArtifactList experiment={experiment} />{experiment.status === 'completed' && experiment.validated && !experiment.retained_at && <button type="button" disabled={retain.isPending} onClick={() => retain.mutate(experiment.id)} className="mt-2 inline-flex items-center gap-1 rounded-btn border border-amber-400/40 px-2 py-1 text-[11px] text-amber-500"><Archive className="h-3 w-3" />保留以供比较</button>}</div>)}</div></article>
  </section>
}
