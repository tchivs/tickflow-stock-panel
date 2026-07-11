import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, CircleAlert, Clock3, RefreshCw, ShieldCheck } from 'lucide-react'
import { Modal } from '@/components/Modal'
import { Skeleton } from '@/components/data/Skeleton'
import { api, type AdjustmentAudit, type DecisionRun, type HistoricalReplay, type PlaybookSnapshot } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

const AUDIT_FIELDS = [
  { key: 'entry', label: '入场区间', fields: ['entry_low', 'entry_high'] },
  { key: 'stop', label: '止损', fields: ['stop'] },
  { key: 'target1', label: '目标 1', fields: ['target1'] },
  { key: 'target2', label: '目标 2', fields: ['target2'] },
  { key: 'position_pct', label: '仓位', fields: ['position_pct'] },
  { key: 'action', label: '动作 / 理由', fields: ['action'] },
] as const

const AUDIT_STATUS: Record<AdjustmentAudit['disposition'], { label: string; className: string }> = {
  applied: { label: '已应用', className: 'text-emerald-500' },
  clamped: { label: '已钳制', className: 'text-warning' },
  rejected: { label: '已拒绝', className: 'text-danger' },
}

function price(value: number) {
  return Number.isFinite(value) ? value.toFixed(2) : '—'
}

function valueFor(snapshot: PlaybookSnapshot, key: string) {
  if (key === 'entry') return `${price(snapshot.entry_low)} – ${price(snapshot.entry_high)}`
  if (key === 'position_pct') return `${(snapshot.position_pct * 100).toFixed(1)}%`
  if (key === 'action') return `${snapshot.action} · ${Object.values(snapshot.reason_snapshot).filter(Boolean).join('；') || '—'}`
  const value = snapshot[key as keyof PlaybookSnapshot]
  return typeof value === 'number' ? price(value) : String(value ?? '—')
}

function auditFor(fields: readonly string[], adjustments: AdjustmentAudit[]) {
  return adjustments.find(adjustment => fields.includes(adjustment.field))
}

function ReplayResult({ replay }: { replay: HistoricalReplay }) {
  return <div className="mt-3 rounded-btn border border-border bg-base/50 p-3 text-xs"><div className="flex items-center gap-1 text-emerald-500"><Check className="h-3.5 w-3.5" />已完成 AI 禁用的历史回放</div><dl className="mt-2 grid gap-1 text-muted"><div><dt className="inline">回放时间：</dt><dd className="inline font-mono text-secondary">{new Date(replay.created_at).toLocaleString('zh-CN')}</dd></div><div><dt className="inline">数据截至：</dt><dd className="inline font-mono text-secondary">{replay.as_of}</dd></div><div><dt className="inline">结果哈希：</dt><dd className="inline break-all font-mono text-secondary">{replay.result_hash}</dd></div></dl></div>
}

function PlaybookDetails({ run, replay, replaying, replayAsOf, setReplayAsOf, onReplay }: { run: DecisionRun; replay?: HistoricalReplay; replaying: boolean; replayAsOf: string; setReplayAsOf: (value: string) => void; onReplay: () => void }) {
  return <div className="space-y-5">
    <section className="grid grid-cols-1 gap-2 border-b border-border pb-4 text-xs text-muted sm:grid-cols-3"><div><span className="block">数据截至</span><span className="font-mono text-secondary">{run.data_as_of}</span></div><div><span className="block">引擎版本</span><span className="font-mono text-secondary">{run.engine_config_version}</span></div><div><span className="block">计划标的</span><span className="font-mono text-secondary">{run.symbol}</span></div></section>
    <section><h3 className="text-sm font-semibold text-foreground">确定性基线与最终计划</h3><div className="mt-2 overflow-hidden rounded-card border border-border"><div className="grid grid-cols-[minmax(5rem,1fr)_minmax(0,1.4fr)_minmax(0,1.4fr)] border-b border-border bg-elevated/50 px-3 py-2 text-xs font-medium text-muted"><span>字段</span><span>确定性基线</span><span>最终计划</span></div>{AUDIT_FIELDS.map(field => <div key={field.key} className="grid grid-cols-[minmax(5rem,1fr)_minmax(0,1.4fr)_minmax(0,1.4fr)] gap-2 border-b border-border/60 px-3 py-2 text-xs last:border-0"><span className="text-muted">{field.label}</span><span className="min-w-0 break-words font-mono text-secondary">{valueFor(run.baseline, field.key)}</span><span className="min-w-0 break-words font-mono text-foreground">{valueFor(run.final, field.key)}</span></div>)}</div><div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 rounded-btn bg-base/50 px-3 py-2 text-xs text-muted"><span>确定性动作 <strong className="font-mono text-foreground">{run.baseline.action}</strong></span><span>评分 <strong className="font-mono text-foreground">{run.baseline.score}</strong></span><span>风险收益 <strong className="font-mono text-foreground">{run.baseline.risk_reward}</strong></span></div></section>
    <section><h3 className="text-sm font-semibold text-foreground">字段调整审计</h3><div className="mt-2 space-y-2">{AUDIT_FIELDS.map(field => { const adjustment = auditFor(field.fields, run.adjustments); const status = adjustment ? AUDIT_STATUS[adjustment.disposition] : null; return <div key={field.key} className="rounded-btn border border-border px-3 py-2 text-xs"><div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium text-secondary">{field.label}</span>{status ? <span className={status.className}>{status.label}</span> : <span className="text-muted">未应用 AI 调整</span>}</div>{adjustment && <p className="mt-1 break-words text-muted">{adjustment.rationale || '未提供调整理由'}{adjustment.proposed_value != null && ` · 提议 ${adjustment.proposed_value}`}{adjustment.final_value != null && ` · 最终 ${adjustment.final_value}`}</p>}</div> })}</div></section>
    <section className="border-t border-border pt-4"><h3 className="text-sm font-semibold text-foreground">历史回放</h3><div className="mt-2 flex flex-wrap items-end gap-2"><label className="space-y-1 text-xs text-muted"><span className="block">数据截至</span><input type="date" value={replayAsOf} onChange={event => setReplayAsOf(event.target.value)} max={run.data_as_of} className="h-9 rounded-btn border border-border bg-base px-2 font-mono text-xs text-foreground" /></label><button type="button" disabled={!replayAsOf || replaying} onClick={onReplay} className="inline-flex h-9 items-center gap-1 rounded-btn bg-accent px-3 text-xs font-medium text-base disabled:opacity-50"><RefreshCw className={`h-3.5 w-3.5 ${replaying ? 'animate-spin' : ''}`} />{replaying ? '正在以历史数据回放；AI 已禁用' : '运行历史回放'}</button></div>{replaying && <p className="mt-2 flex items-center gap-1 text-xs text-muted"><Clock3 className="h-3.5 w-3.5" />正在以历史数据回放；AI 已禁用</p>}{replay && <ReplayResult replay={replay} />}</section>
  </div>
}

export function PlaybookInspector({ onClose }: { onClose: () => void }) {
  const [runIdInput, setRunIdInput] = useState('')
  const [runId, setRunId] = useState('')
  const [replayAsOf, setReplayAsOf] = useState('')
  const playbook = useQuery({ queryKey: QK.decisionPlaybook(runId), queryFn: () => api.decisionRun(runId), enabled: Boolean(runId), placeholderData: previous => previous })
  const replay = useMutation({ mutationFn: (asOf: string) => api.decisionReplay([runId], asOf) })
  const current = playbook.data

  return <Modal onClose={onClose} ariaLabel="决策计划" panelClassName="w-[calc(100vw-32px)] max-w-4xl max-h-[90vh] overflow-auto rounded-card border border-border bg-surface shadow-xl"><div className="sticky top-0 z-10 border-b border-border bg-surface px-4 py-3"><div className="flex items-start justify-between gap-3"><div><h2 className="text-base font-semibold text-foreground">决策计划</h2><p className="mt-1 text-xs text-muted">只读展示确定性计算、受限调整与历史回放。</p></div><ShieldCheck className="h-5 w-5 shrink-0 text-accent" /></div><form onSubmit={event => { event.preventDefault(); setRunId(runIdInput.trim()); setReplayAsOf('') }} className="mt-3 flex gap-2"><label className="sr-only" htmlFor="decision-run-id">决策计划 ID</label><input id="decision-run-id" value={runIdInput} onChange={event => setRunIdInput(event.target.value)} placeholder="输入已保存的决策计划 ID" className="h-9 min-w-0 flex-1 rounded-btn border border-border bg-base px-3 font-mono text-xs text-foreground" /><button type="submit" disabled={!runIdInput.trim()} className="h-9 rounded-btn bg-accent px-3 text-xs font-medium text-base disabled:opacity-50">查看</button></form></div><div className="p-4">{!runId ? <div className="py-8 text-center"><CircleAlert className="mx-auto h-5 w-5 text-muted" /><h3 className="mt-2 text-sm font-medium text-foreground">尚无可用决策计划</h3><p className="mt-1 text-xs text-muted">完成数据同步后生成确定性计划。</p></div> : playbook.isLoading && !current ? <div className="space-y-3">{Array.from({ length: 6 }, (_, index) => <Skeleton key={index} h="h-10" rounded="rounded-btn" />)}</div> : playbook.isError ? <div className="space-y-3"><p className="text-sm text-danger">无法读取决策计划。请检查数据状态后重新加载决策计划。</p><button onClick={() => playbook.refetch()} className="rounded-btn bg-accent px-3 py-2 text-xs font-medium text-base">重新加载决策计划</button></div> : current ? <PlaybookDetails run={current} replay={replay.data} replaying={replay.isPending} replayAsOf={replayAsOf || current.data_as_of} setReplayAsOf={setReplayAsOf} onReplay={() => replay.mutate(replayAsOf || current.data_as_of)} /> : null}</div></Modal>
}
