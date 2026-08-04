import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Layers, FlaskConical } from 'lucide-react'
import { api, type FactorRevisionDTO, type ModelDefinitionDTO } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'

export function ModelLibrary() {
  const [activeTab, setActiveTab] = useState<'factors' | 'models'>('factors')

  return (
    <>
      <PageHeader
        title="模型库"
        subtitle="已准入因子 · 多因子模型 · IC / RankIC 独立展示"
        right={
          <div className="flex items-center gap-1 rounded-btn border border-border bg-surface p-0.5">
            <button
              onClick={() => setActiveTab('factors')}
              className={`min-h-8 rounded-btn px-3 text-xs font-medium ${activeTab === 'factors' ? 'bg-accent/15 text-accent' : 'text-muted hover:text-secondary'}`}
            >
              因子目录
            </button>
            <button
              onClick={() => setActiveTab('models')}
              className={`min-h-8 rounded-btn px-3 text-xs font-medium ${activeTab === 'models' ? 'bg-accent/15 text-accent' : 'text-muted hover:text-secondary'}`}
            >
              组合模型
            </button>
          </div>
        }
      />
      <div className="px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
        {activeTab === 'factors' ? <FactorCatalog /> : <ModelCatalog />}
      </div>
    </>
  )
}

function FactorCatalog() {
  const factorsQuery = useQuery({
    queryKey: QK.panelFactors(),
    queryFn: () => api.listFactors(),
  })

  return (
    <section className="rounded-card border border-border bg-surface">
      <div className="border-b border-border px-4 py-2.5 text-xs font-semibold text-secondary">
        已准入因子 {factorsQuery.data ? `(${factorsQuery.data.length})` : ''}
        <span className="ml-2 font-normal text-muted">IC 与 RankIC 为独立指标，绝不合并</span>
      </div>
      {factorsQuery.isLoading && <div className="px-4 py-10 text-center text-sm text-muted">加载中…</div>}
      {factorsQuery.data?.length === 0 && (
        <EmptyState icon={FlaskConical} title="暂无因子" hint="在策略工作台评估并准入因子后，目录会显示在这里。" />
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-elevated/50 text-[11px] text-muted">
            <tr>
              <th className="px-4 py-2 font-medium">因子</th>
              <th className="px-4 py-2 font-medium">修订</th>
              <th className="px-4 py-2 text-right font-medium">IC</th>
              <th className="px-4 py-2 text-right font-medium">RankIC</th>
              <th className="px-4 py-2 font-medium">状态</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/70">
            {factorsQuery.data?.map(factor => (
              <FactorRow key={factor.id} factor={factor} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function FactorRow({ factor }: { factor: FactorRevisionDTO }) {
  const [expanded, setExpanded] = useState(false)
  const verdictQuery = useQuery({
    queryKey: QK.panelFactorVerdict(factor.id),
    queryFn: () => api.getAdmissionVerdict(factor.id),
    // 懒加载: 行未展开不请求; 404 = 该修订无准入记录 (fail-closed), 不重试。
    enabled: expanded,
    retry: 0,
  })
  const admitted = factor.status === 'admitted' || verdictQuery.data?.admitted === true

  return (
    <>
      <tr
        className="cursor-pointer transition-colors hover:bg-elevated/30"
        onClick={() => setExpanded(v => !v)}
      >
        <td className="px-4 py-2.5">
          <div className="flex items-center gap-2">
            {expanded ? <ChevronDown className="h-3 w-3 text-muted" /> : <ChevronRight className="h-3 w-3 text-muted" />}
            <span className="font-medium text-foreground">{factor.name}</span>
          </div>
          <div className="mt-0.5 pl-5 font-mono text-[10px] text-muted">{factor.factor_id}</div>
        </td>
        <td className="px-4 py-2.5 font-mono text-secondary">r{factor.revision_number}</td>
        <td className="px-4 py-2.5 text-right font-mono tabular-nums text-accent">
          {factor.ic != null ? factor.ic.toFixed(4) : '—'}
        </td>
        <td className="px-4 py-2.5 text-right font-mono tabular-nums text-bull">
          {factor.rank_ic != null ? factor.rank_ic.toFixed(4) : '—'}
        </td>
        <td className="px-4 py-2.5">
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${admitted ? 'bg-bear/15 text-bear' : 'bg-warning/15 text-warning'}`}>
            {admitted ? '已准入' : factor.status}
          </span>
        </td>
      </tr>
      {expanded && (
        <tr className="bg-elevated/20">
          <td colSpan={5} className="px-4 py-3">
            <div className="space-y-2">
              <div>
                <div className="text-[10px] font-medium uppercase tracking-wider text-muted">表达式</div>
                <code className="mt-0.5 block font-mono text-[11px] text-secondary">{factor.expression}</code>
              </div>
              {verdictQuery.isError && (
                <div className="text-[11px] text-muted">无准入记录(该修订未经过录取闸门)</div>
              )}
              {verdictQuery.data && (
                <div>
                  <div className="text-[10px] font-medium uppercase tracking-wider text-muted">准入结论 · {verdictQuery.data.policy_version}</div>
                  <div className="mt-0.5 text-[11px] text-secondary">
                    {verdictQuery.data.admitted ? '通过' : '拒绝'} — {verdictQuery.data.reason ?? '—'}
                  </div>
                  {verdictQuery.data.details && (
                    <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words text-[10px] text-muted">{JSON.stringify(verdictQuery.data.details, null, 2)}</pre>
                  )}
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function ModelCatalog() {
  const modelsQuery = useQuery({
    queryKey: QK.panelModels(),
    queryFn: () => api.listModels(),
  })

  return (
    <section className="rounded-card border border-border bg-surface">
      <div className="border-b border-border px-4 py-2.5 text-xs font-semibold text-secondary">
        组合模型 {modelsQuery.data ? `(${modelsQuery.data.length})` : ''}
      </div>
      {modelsQuery.data?.length === 0 && (
        <EmptyState icon={Layers} title="暂无组合模型" hint="准入多个因子后，可构建多因子预期收益模型。" />
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-elevated/50 text-[11px] text-muted">
            <tr>
              <th className="px-4 py-2 font-medium">模型</th>
              <th className="px-4 py-2 font-medium">加权方式</th>
              <th className="px-4 py-2 font-medium">因子修订</th>
              <th className="px-4 py-2 font-medium">输入快照</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/70">
            {modelsQuery.data?.map(model => <ModelRow key={model.model_id} model={model} />)}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function ModelRow({ model }: { model: ModelDefinitionDTO }) {
  const [expanded, setExpanded] = useState(false)
  const compositesQuery = useQuery({
    queryKey: QK.panelModelComposites(model.model_id),
    queryFn: () => api.listModelComposites(model.model_id),
    enabled: expanded,
  })

  return (
    <>
      <tr className="cursor-pointer transition-colors hover:bg-elevated/30" onClick={() => setExpanded(v => !v)}>
        <td className="px-4 py-2.5">
          <div className="flex items-center gap-2">
            {expanded ? <ChevronDown className="h-3 w-3 text-muted" /> : <ChevronRight className="h-3 w-3 text-muted" />}
            <span className="font-medium text-foreground">{model.name}</span>
          </div>
          <div className="mt-0.5 pl-5 font-mono text-[10px] text-muted">{model.model_id}</div>
        </td>
        <td className="px-4 py-2.5">
          <span className="rounded bg-elevated px-1.5 py-0.5 font-medium">{model.weighting}</span>
        </td>
        <td className="px-4 py-2.5 font-mono text-secondary">{model.revision_ids.length} 个</td>
        <td className="px-4 py-2.5 font-mono text-[10px] text-muted">{model.input_snapshot_sha256?.slice(0, 12) ?? '—'}…</td>
      </tr>
      {expanded && (
        <tr className="bg-elevated/20">
          <td colSpan={4} className="px-4 py-3">
            <div className="space-y-3">
              <div>
                <div className="text-[10px] font-medium uppercase tracking-wider text-muted">因子权重</div>
                {model.weights && Object.keys(model.weights).length > 0 ? (
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {Object.entries(model.weights).map(([revisionId, weight]) => (
                      <span key={revisionId} className="rounded-full border border-border bg-surface px-2 py-0.5 font-mono text-[10px] text-secondary">
                        {revisionId.slice(0, 8)}: {((weight as number) * 100).toFixed(1)}%
                      </span>
                    ))}
                  </div>
                ) : (
                  <div className="mt-1 text-[11px] text-muted">等权（未显式指定权重）</div>
                )}
              </div>
              <div>
                <div className="text-[10px] font-medium uppercase tracking-wider text-muted">不可变快照</div>
                {compositesQuery.data?.length === 0 && (
                  <div className="mt-1 text-[11px] text-muted">暂无复合快照</div>
                )}
                {compositesQuery.data?.map(composite => (
                  <div key={composite.id} className="mt-1 rounded-btn border border-border bg-surface px-2.5 py-1.5 font-mono text-[10px] text-secondary">
                    {composite.id.slice(0, 12)} · input {composite.input_snapshot_sha256.slice(0, 12)}…
                    {composite.mean_ic != null && <span className="ml-1 text-accent">mean IC {composite.mean_ic.toFixed(4)}</span>}
                  </div>
                ))}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
