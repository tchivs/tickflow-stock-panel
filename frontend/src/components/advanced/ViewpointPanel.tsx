import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import type { AnalysisRequestSubject, AnalysisSubject, AdvancedCalibration, AdvancedJobStage, AdvancedViewpoint } from '@/lib/api'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

const stageLabels: Record<AdvancedJobStage, string> = {
  authorized: '已授权',
  frozen: '已冻结输入',
  drafted: '正在生成草稿',
  gates_complete: '正在校验门禁',
  awaiting_review: '等待人工复核',
  recorded: '已记录',
  rejected: '已拒绝',
}

function revisionLabel(viewpoint: AdvancedViewpoint) {
  if (viewpoint.revision_kind === 'material_stance_change') return '材料立场变化'
  if (viewpoint.revision_kind === 'correction') return `更正版本：${viewpoint.correction_reason ?? '已记录'}`
  if (viewpoint.revision_kind === 'non_material_revision') return '内容修订，未构成立场变化'
  return '初始版本'
}

export function ViewpointPanel({ subject, serverSubject }: { subject: AnalysisSubject; serverSubject: AnalysisRequestSubject }) {
  const queryClient = useQueryClient()
  const [jobId, setJobId] = useState<string | null>(null)
  const [editMode, setEditMode] = useState<'revision' | 'correction' | null>(null)
  const [conclusion, setConclusion] = useState('')
  const [correctionReason, setCorrectionReason] = useState('')
  const [revisionDirection, setRevisionDirection] = useState<AdvancedViewpoint['direction']>('bearish')
  const viewpointsQuery = useQuery({
    queryKey: QK.advancedViewpoints(subject.kind, subject.key),
    queryFn: () => api.advancedViewpoints(serverSubject),
    placeholderData: keepPreviousData,
  })
  const latest = viewpointsQuery.data?.viewpoints[0]
  const calibrationQuery = useQuery({
    queryKey: QK.advancedCalibration(subject.kind, subject.key, latest?.source_profile ?? 'none'),
    queryFn: () => api.advancedCalibration(latest!.source_profile),
    enabled: !!latest,
    placeholderData: keepPreviousData,
  })
  const startJob = useMutation({
    mutationFn: () => api.advancedStartJob(serverSubject, 'research_draft'),
    onSuccess: ({ job }) => setJobId(job.id),
  })
  const jobQuery = useQuery({
    queryKey: QK.advancedJob(subject.kind, subject.key, jobId ?? 'none'),
    queryFn: () => api.advancedJob(jobId!),
    enabled: !!jobId,
    placeholderData: keepPreviousData,
  })
  const job = jobQuery.data?.job ?? startJob.data?.job
  const auditQuery = useQuery({
    queryKey: QK.advancedAudit(subject.kind, subject.key, job?.audit_reference ?? 'none'),
    queryFn: () => api.advancedAudit(job!.audit_reference!),
    enabled: !!job?.audit_reference,
    placeholderData: keepPreviousData,
  })
  const rejectionReason = startJob.isError ? startJob.error.message : job?.stage === 'rejected' ? auditQuery.data?.audit.reason : null
  const invalidateViewpoint = (viewpoint: AdvancedViewpoint) => {
    queryClient.invalidateQueries({ queryKey: QK.advancedViewpoints(subject.kind, subject.key) })
    queryClient.invalidateQueries({ queryKey: QK.advancedViewpointVersions(subject.kind, subject.key, viewpoint.viewpoint_id) })
    queryClient.invalidateQueries({ queryKey: QK.advancedViewpoint(subject.kind, subject.key, viewpoint.viewpoint_id, viewpoint.version) })
    queryClient.invalidateQueries({ queryKey: QK.advancedCalibration(subject.kind, subject.key, viewpoint.source_profile) })
  }
  const revise = useMutation({
    mutationFn: () => api.advancedReviseViewpoint(latest!.viewpoint_id, { conclusion: conclusion.trim(), direction: revisionDirection }),
    onSuccess: ({ viewpoint }) => { invalidateViewpoint(viewpoint); setConclusion(''); setEditMode(null) },
  })
  const correct = useMutation({
    mutationFn: () => api.advancedCorrectViewpoint(latest!.viewpoint_id, { conclusion: conclusion.trim() || undefined, correction_reason: correctionReason.trim() }),
    onSuccess: ({ viewpoint }) => { invalidateViewpoint(viewpoint); setConclusion(''); setCorrectionReason(''); setEditMode(null) },
  })
  const evaluate = useMutation({
    mutationFn: () => api.advancedEvaluateViewpoint(latest!.id),
    onSuccess: ({ viewpoint }) => invalidateViewpoint(viewpoint),
  })

  return <section aria-labelledby="advanced-viewpoints-heading" className="space-y-4 rounded-card border border-border bg-surface p-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 id="advanced-viewpoints-heading" className="text-base font-semibold text-foreground">归因观点与表现校准</h2><p className="mt-1 max-w-prose text-sm text-secondary">来源版本为不可变研究证据，不构成交易指令。</p></div>
      <button type="button" onClick={() => startJob.mutate()} disabled={startJob.isPending || !!jobId && job?.stage !== 'rejected' && job?.stage !== 'recorded'} className="inline-flex min-h-11 items-center gap-2 rounded-btn bg-accent px-3 text-sm font-semibold text-white focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base disabled:opacity-60"><ShieldCheck className="h-4 w-4" aria-hidden="true" />启动受限研究任务</button>
    </div>
    {startJob.isPending && <p role="status" className="text-sm text-warning">正在验证授权范围…</p>}
    {rejectionReason && <div role="alert" className="rounded-card border border-danger/50 bg-danger/10 p-3 text-sm text-danger">任务未启动：{rejectionReason}</div>}
    {job && !rejectionReason && <div role="status" className="rounded-card border border-border bg-elevated p-3 text-sm text-foreground"><p className="font-semibold">{stageLabels[job.stage]}</p><p className="mt-1 text-secondary">最近受控事件时间：{job.stage_recorded_at}</p>{job.audit_reference && <details className="mt-2"><summary className="cursor-pointer text-accent">查看安全审计摘要</summary><p className="mt-2 text-secondary">{auditQuery.data?.audit.reason ?? '正在读取审计摘要…'}</p></details>}</div>}
    {viewpointsQuery.isLoading && <div role="status" className="min-h-28 rounded-card border border-border bg-elevated p-4 text-sm text-muted">正在读取归因观点…</div>}
    {viewpointsQuery.isError && !viewpointsQuery.data && <div role="alert" className="rounded-card border border-danger/50 bg-danger/10 p-4 text-sm text-danger">无法读取归因观点。<button type="button" onClick={() => viewpointsQuery.refetch()} className="ml-2 underline">重新加载</button></div>}
    {!viewpointsQuery.isLoading && !viewpointsQuery.isError && !latest && <div className="rounded-card border border-border bg-elevated p-4"><p className="text-sm font-semibold text-foreground">暂无可归因的市场观点</p><p className="mt-1 text-sm text-secondary">在支持的分析对象中导入或生成带来源档案、范围和发布时间的观点后，版本、变化和表现会在这里保留。</p></div>}
    {latest && <>
      <ViewpointSummary viewpoint={evaluate.data?.viewpoint ?? latest} />
      <div className="flex flex-wrap gap-2" aria-label="不可变观点操作">
        <button type="button" className="min-h-11 rounded-btn border border-border px-3 text-sm text-foreground focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base" onClick={() => setEditMode('revision')}>添加修订</button>
        <button type="button" className="min-h-11 rounded-btn border border-border px-3 text-sm text-foreground focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base" onClick={() => setEditMode('correction')}>添加更正</button>
        <button type="button" className="min-h-11 rounded-btn bg-accent px-3 text-sm font-semibold text-white focus:ring-2 focus:ring-accent focus:ring-offset-2 focus:ring-offset-base disabled:opacity-60" disabled={evaluate.isPending} onClick={() => evaluate.mutate()}>运行服务端评估</button>
      </div>
      {evaluate.isPending && <p role="status" className="text-sm text-secondary">正在请求服务端评估…</p>}
      {evaluate.isSuccess && <p role="status" className="text-sm text-secondary">已由服务端完成评估</p>}
      {(revise.isError || correct.isError || evaluate.isError) && <p role="alert" className="text-sm text-danger">无法更新观点：{(revise.error ?? correct.error ?? evaluate.error)?.message}</p>}
      {editMode && <form className="grid gap-3 rounded-card border border-border bg-elevated p-4" onSubmit={event => { event.preventDefault(); if (editMode === 'revision') revise.mutate(); else correct.mutate() }}>
        <label className="text-sm text-secondary">修订结论<textarea aria-label="修订结论" required={editMode === 'revision'} value={conclusion} onChange={event => setConclusion(event.target.value)} className="mt-1 min-h-24 w-full rounded-input border border-border bg-base p-2 text-foreground" /></label>
        {editMode === 'revision' && <label className="text-sm text-secondary">修订方向<select aria-label="修订方向" value={revisionDirection} onChange={event => setRevisionDirection(event.target.value as AdvancedViewpoint['direction'])} className="mt-1 min-h-11 w-full rounded-input border border-border bg-base p-2 text-foreground"><option value="bullish">看多</option><option value="bearish">看空</option><option value="neutral">中性</option></select></label>}
        {editMode === 'correction' && <label className="text-sm text-secondary">更正原因<textarea aria-label="更正原因" required value={correctionReason} onChange={event => setCorrectionReason(event.target.value)} className="mt-1 min-h-20 w-full rounded-input border border-border bg-base p-2 text-foreground" /></label>}
        <div className="flex flex-wrap gap-2"><button type="submit" disabled={editMode === 'correction' && !correctionReason.trim()} className="min-h-11 rounded-btn bg-accent px-3 text-sm font-semibold text-white disabled:opacity-60">{editMode === 'revision' ? '保存修订' : '保存更正'}</button><button type="button" className="min-h-11 rounded-btn border border-border px-3 text-sm" onClick={() => setEditMode(null)}>返回版本记录</button></div>
      </form>}
      <div className="overflow-x-auto" tabIndex={0} aria-describedby="viewpoint-lineage-scroll-instruction"><p id="viewpoint-lineage-scroll-instruction" className="mb-2 text-xs text-muted">左右滚动查看完整记录</p><table className="min-w-[680px] text-left text-sm"><caption className="mb-2 text-left text-sm font-semibold text-foreground">版本谱系</caption><thead className="border-b border-border text-secondary"><tr><th scope="col" className="p-2">版本</th><th scope="col" className="p-2">发布时间</th><th scope="col" className="p-2">变化</th><th scope="col" className="p-2">结论</th><th scope="col" className="p-2">证据</th></tr></thead><tbody>{viewpointsQuery.data!.viewpoints.map(item => <tr key={item.id} className="border-b border-border/70"><td className="p-2 font-mono">版本 {item.version}</td><td className="p-2">{item.published_at}</td><td className="p-2">{revisionLabel(item)}</td><td className="p-2">{item.conclusion}</td><td className="p-2"><details><summary className="cursor-pointer text-accent">查看此版本证据</summary><p className="mt-2 text-secondary">来源档案：{item.source_profile}</p></details></td></tr>)}</tbody></table></div>
      <Calibration calibration={calibrationQuery.data?.calibration} loading={calibrationQuery.isLoading} />
    </>}
  </section>
}

function ViewpointSummary({ viewpoint }: { viewpoint: AdvancedViewpoint }) {
  const evaluation = viewpoint.evaluation
  return <div className="space-y-3 rounded-card border border-border bg-elevated p-4 text-sm">
    {viewpoint.revision_kind === 'material_stance_change' && <p className="font-semibold text-warning">材料立场变化</p>}
    {evaluation?.status === 'unevaluable' && <p className="font-semibold text-warning">不可评估：{evaluation.reason ?? '服务端未提供原因'}</p>}
    <dl className="grid gap-3 sm:grid-cols-2"><div><dt className="text-secondary">来源档案</dt><dd>{viewpoint.source_profile}</dd></div><div><dt className="text-secondary">发布时间</dt><dd>{viewpoint.published_at}</dd></div><div><dt className="text-secondary">结论 / 置信度</dt><dd>{viewpoint.conclusion} / {viewpoint.confidence}</dd></div><div><dt className="text-secondary">冻结表现</dt><dd>{evaluation ? `${evaluation.window_days} 个交易日，${evaluation.benchmark ?? '无基准'}，${evaluation.relative_return == null ? '不可评估' : `${(evaluation.relative_return * 100).toFixed(2)}%`}` : '等待服务端评估'}</dd></div></dl>
  </div>
}

function Calibration({ calibration, loading }: { calibration: AdvancedCalibration | undefined; loading: boolean }) {
  if (loading) return <p role="status" className="text-sm text-muted">正在读取表现校准…</p>
  if (!calibration) return null
  return <div className="overflow-x-auto" tabIndex={0} aria-describedby="viewpoint-calibration-scroll-instruction">
    <p id="viewpoint-calibration-scroll-instruction" className="mb-2 text-xs text-muted">左右滚动查看完整记录</p>
    <table className="min-w-[640px] text-left text-sm"><caption className="mb-2 text-left text-sm font-semibold text-foreground">置信度校准</caption><thead className="border-b border-border text-secondary"><tr><th scope="col" className="p-2">置信度</th><th scope="col" className="p-2">命中率</th><th scope="col" className="p-2">相对收益</th><th scope="col" className="p-2">样本数</th><th scope="col" className="p-2">覆盖期</th></tr></thead><tbody>{(['low', 'medium', 'high'] as const).map(bucket => { const item = calibration[bucket]; return <tr key={bucket} className="border-b border-border/70"><th scope="row" className="p-2">{bucket === 'low' ? '低' : bucket === 'medium' ? '中' : '高'}</th><td className="p-2">{item.hit_rate == null ? '无' : `${(item.hit_rate * 100).toFixed(0)}%`}</td><td className="p-2">{item.mean_relative_return == null ? '无' : `${(item.mean_relative_return * 100).toFixed(2)}%`}</td><td className="p-2">{item.sample_count}</td><td className="p-2">{item.coverage_start ?? '无'} 至 {item.coverage_end ?? '无'}{item.status === 'insufficient_sample' && <span className="ml-2 text-warning">样本不足，暂不能评价置信度校准。</span>}</td></tr> })}</tbody></table>
  </div>
}
