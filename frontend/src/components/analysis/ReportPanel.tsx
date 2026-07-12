import type { AnalysisEvidence, AnalysisReport } from '@/lib/api'

const disclaimer = 'AI 结论基于所列证据生成；来源等级和核验状态限制其可采信程度，不构成投资建议。'

function ConflictWarning({ limitations }: { limitations: string[] }) {
  if (!limitations.length) return null
  return <aside role="alert" className="rounded-card border border-warning/50 bg-warning/10 p-3 text-sm text-warning">
    <p className="font-semibold">存在未解决差异</p>
    {limitations.map(limitation => <p key={limitation} className="mt-1 break-words">{limitation}。查看差异依据后再判断结论。</p>)}
  </aside>
}

export function ReportPanel({ report, evidence }: { report: AnalysisReport; evidence?: AnalysisEvidence | null }) {
  const limitations = [...new Set([
    ...report.evidence_limitations,
    ...(evidence?.material_numbers.filter(number => number.cross_check === 'conflicting' || number.cross_check === 'unresolved').map(number => `${number.label} 的来源口径或数值不一致`) ?? []),
  ])]
  const hasConflict = limitations.length > 0

  return <article aria-labelledby="analysis-report-heading" className="space-y-6 rounded-card border border-border bg-surface p-4 md:p-6">
    <header className="space-y-2">
      <h2 id="analysis-report-heading" className="text-base font-semibold text-foreground">分析结论与证据状态</h2>
      <p className="font-mono text-xs text-muted">生成时间：{new Date(report.generated_at).toLocaleString('zh-CN')}</p>
      {evidence && <p className="text-sm text-secondary">已交叉核验 {evidence.material_numbers.filter(number => number.cross_check === 'confirmed').length}/{evidence.material_numbers.length} 项材料数字</p>}
    </header>
    <ConflictWarning limitations={limitations} />

    <section aria-labelledby="perspectives-heading" className="space-y-3">
      <h3 id="perspectives-heading" className="text-base font-semibold text-foreground">多视角</h3>
      {report.perspectives.map(perspective => <section key={perspective.name} className="border-l-2 border-border pl-3">
        <h4 className="text-sm font-semibold text-foreground">{perspective.name}</h4>
        {hasConflict && <p className="mt-1 text-sm text-warning">受未解决来源差异影响</p>}
        <p className="mt-1 max-w-[65ch] break-words text-sm text-secondary">{perspective.conclusion}</p>
        <p className="mt-1 text-xs text-muted">引用证据：{perspective.evidence_count} 项{perspective.limitations.length ? `；限制：${perspective.limitations.join('；')}` : ''}</p>
      </section>)}
    </section>

    <section aria-labelledby="score-heading" className="space-y-2">
      <h3 id="score-heading" className="text-base font-semibold text-foreground">评分理由</h3>
      {report.score?.dimensions.length ? <div className="overflow-x-auto"><table className="min-w-[640px] text-left text-sm"><caption className="sr-only">评分维度、贡献、证据和理由</caption><thead className="border-b border-border text-muted"><tr><th scope="col" className="p-2">维度</th><th scope="col" className="p-2">贡献</th><th scope="col" className="p-2">证据引用</th><th scope="col" className="p-2">判定说明</th></tr></thead><tbody>{report.score.dimensions.map(dimension => <tr key={dimension.name} className="border-b border-border/60"><th scope="row" className="p-2 font-medium text-foreground">{dimension.name}</th><td className="p-2 font-mono text-secondary">{dimension.contribution ?? dimension.weight ?? '—'}</td><td className="p-2 text-secondary">{dimension.evidence_ids.length}</td><td className="p-2 break-words text-secondary">{dimension.rationale}{dimension.uncertainty ? `；${dimension.uncertainty}` : ''}</td></tr>)}</tbody></table></div> : <p className="text-sm text-warning">评分暂不可解释，不能用于比较。</p>}
    </section>

    <section aria-labelledby="valuation-heading" className="space-y-2">
      <h3 id="valuation-heading" className="text-base font-semibold text-foreground">估值分析</h3>
      {report.valuation?.applicable ? <div className="space-y-1 text-sm text-secondary"><p>方法：{report.valuation.method ?? '—'}</p><p>基准日期：{report.valuation.as_of ?? '—'}</p><p>估值范围：{report.valuation.range ?? '—'}</p><p>限制：{report.valuation.limitations?.join('；') ?? '—'}</p></div> : <p className="text-sm text-secondary">{report.valuation?.reason ? `本报告不适用估值分析：${report.valuation.reason}` : '估值输入不完整，未形成估值结论。'}</p>}
    </section>

    <section aria-labelledby="memo-heading" className="space-y-3">
      <h3 id="memo-heading" className="text-base font-semibold text-foreground">投资委员会备忘录</h3>
      <ConflictWarning limitations={limitations} />
      <p className="max-w-[65ch] break-words text-sm text-secondary"><span className="font-semibold text-foreground">投资要点：</span>{report.ic_memo.thesis}</p>
      <MemoList title="支持证据" items={report.ic_memo.supporting_evidence ?? []} />
      <MemoList title="主要反方观点/风险" items={report.ic_memo.risks} />
      <MemoList title="待解决问题" items={report.ic_memo.open_questions} />
      {report.ic_memo.valuation_anchor && <p className="text-sm text-secondary"><span className="font-semibold text-foreground">估值锚点：</span>{report.ic_memo.valuation_anchor}</p>}
      <MemoList title="失效条件" items={report.ic_memo.invalidation_conditions ?? []} />
    </section>
    <p className="border-t border-border pt-4 text-sm text-muted">{disclaimer}</p>
  </article>
}

function MemoList({ title, items }: { title: string; items: string[] }) {
  return <section><h4 className="text-sm font-semibold text-foreground">{title}</h4>{items.length ? <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-secondary">{items.map(item => <li key={item} className="break-words">{item}</li>)}</ul> : <p className="mt-1 text-sm text-muted">未提供。</p>}</section>
}
