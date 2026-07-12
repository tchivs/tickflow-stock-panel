import type { AnalysisEvidence, AnalysisMaterialNumber } from '@/lib/api'

function crossCheckLabel(number: AnalysisMaterialNumber) {
  if (number.cross_check === 'confirmed') return '已交叉核验'
  if (number.cross_check === 'conflicting') return '存在差异'
  if (number.cross_check === 'unresolved') return '尚未核验'
  return '核验上下文不足'
}

export function EvidencePanel({ evidence }: { evidence: AnalysisEvidence }) {
  return <section aria-labelledby="evidence-heading" className="space-y-4 rounded-card border border-border bg-surface p-4 md:p-6">
    <header><h2 id="evidence-heading" className="text-base font-semibold text-foreground">来源与核验</h2><p className="mt-1 text-sm text-secondary">A=原始或已治理来源；B=可追溯二级来源；C=待验证辅助来源。</p></header>
    {evidence.material_numbers.length === 0 ? <p className="text-sm text-warning">此报告没有可展示的来源记录。该结论不能视为已核验；请查看报告限制或重新生成分析。</p> : <><p className="text-sm text-muted">左右滚动查看全部证据列</p><div className="overflow-x-auto"><table className="min-w-[840px] text-left text-sm"><caption className="caption-top pb-2 text-left text-sm text-muted">材料数字、来源和独立核验状态</caption><thead className="border-b border-border text-muted"><tr><th scope="col" className="p-2">材料数字</th><th scope="col" className="p-2">值/单位</th><th scope="col" className="p-2">期间</th><th scope="col" className="p-2">来源</th><th scope="col" className="p-2">核验</th><th scope="col" className="p-2">差异说明</th></tr></thead><tbody>{evidence.material_numbers.map(number => <tr key={number.id} className="border-b border-border/60 align-top"><th scope="row" className="p-2 font-medium text-foreground">{number.label}</th><td className="p-2 font-mono text-right text-secondary">{number.value ?? '—'} {number.unit}</td><td className="p-2 font-mono text-secondary">{number.period}</td><td className="p-2 text-secondary">{number.source_count} 个可用来源</td><td className="p-2 text-secondary">{crossCheckLabel(number)}</td><td className="p-2 break-words text-secondary">{number.difference_reason ?? '—'}</td></tr>)}</tbody></table></div></>}
    <div className="space-y-2">{evidence.material_numbers.map(number => <details key={number.id} className="rounded-btn border border-border bg-base p-2"><summary className="min-h-11 cursor-pointer py-2 text-sm font-medium text-accent outline-none focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base">查看{number.label}的 {number.source_count} 个来源</summary><div className="mt-2 space-y-2 text-sm text-secondary">{evidence.sources.map(source => <p key={`${number.id}-${source.id}`} className="break-words"><span className="font-semibold text-foreground">{source.grade} 级 {source.name}</span> · {source.source_type} · <span className="font-mono">{source.retrieved_at}</span>{source.period ? ` · ${source.period}` : ''}{source.reference ? ` · ${source.reference}` : ''}</p>)}</div></details>)}</div>
  </section>
}
