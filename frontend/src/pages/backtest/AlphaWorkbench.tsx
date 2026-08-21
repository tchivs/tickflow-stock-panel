import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Activity,
  Copy,
  Gauge,
  GitBranch,
  GitCompareArrows,
  GitFork,
  Play,
  ShieldAlert,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react'
import {
  fetchAlphaCandidates,
  fetchAlphaCompare,
  fetchAlphaLineage,
  fetchAlphaProgress,
  fetchAlphaRun,
  fetchAlphaRuns,
  fetchEvidenceClassification,
  fetchStressMatrix,
  postClone,
  postReplayBranch,
  type AlphaCandidate,
  type AlphaCandidateComparison,
  type AlphaLineageEdge,
  type AlphaRunEvent,
  type AlphaRunRead,
  type CloneResult,
  type EvidenceClassification,
  type ReplayBranchResult,
  type StressMatrix,
} from '@/lib/api'
import * as wsStream from '@/lib/useWsStream'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'
import { EvidenceCards } from '@/components/report/EvidenceCards'
import { ConflictPaths } from '@/components/report/ConflictPaths'
import { toast } from '@/components/Toast'

// ---------------------------------------------------------------------------
// Phase 50 — Alpha Replay Workbench (AF-REQ-18/20/22/24, SC1–SC4 UI).
//
// A single NEW page (sibling to WalkForward.tsx) projecting every backend seam
// from 50-01/02 to the researcher:
//   • durable live progress over native EventSource (Last-Event-ID reconnect)
//     with a bounded-polling fallback (SC1);
//   • the parent→child lineage tree with expression diffs + replay/clone (SC2);
//   • the side-by-side compare panel + Tier-1 stress matrix — no opaque winner (SC3);
//   • the data-quality banner bound to evidence_classification.clean (SC4).
//
// All server state flows through the existing request<T> fetcher + React Query;
// the live stream uses native EventSource (no new transport/dependency).
// ---------------------------------------------------------------------------

type ConnStatus = 'idle' | 'running' | 'done' | 'error' | 'reconnecting'

const TERMINAL_RUN: Record<AlphaRunRead['status'], boolean> = {
  queued: false,
  preflight_failed: true,
  running: false,
  cancel_requested: false,
  cancelled: true,
  completed: true,
  failed: true,
}

function isTerminalRun(status: AlphaRunRead['status']): boolean {
  return TERMINAL_RUN[status]
}

// The curated set of named alpha ledger event types the consumer listens to.
// (Phase 55: migrated to WS channel subscription; event set is now driven by
// useWsStream RUN_CHANNEL_EVENTS in the shared hook.)
const POLL_INTERVAL_MS = 2000
const EVENT_TAIL_MAX = 200

/**
 * Durable live progress over native EventSource (SC1 UI half).
 *
 * The browser auto-sends Last-Event-ID on every reconnect; the server honors it
 * durably (50-01-04), so reconnect resumes from the acknowledged seq. We dedup
 * by seq client-side so any reconnect overlap can never duplicate a rendered
 * event. When EventSource is unavailable we degrade to bounded polling of
 * GET /progress (+ GET /runs/{id} for the terminal check).
 */
function useAlphaStream(runId: string | null) {
  const [status, setStatus] = useState<ConnStatus>('idle')
  const [events, setEvents] = useState<AlphaRunEvent[]>([])
  const [polling, setPolling] = useState(false)
  const seenSeqs = useRef<Set<number>>(new Set())
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPoll = useCallback(() => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current)
      pollTimer.current = null
    }
    setPolling(false)
  }, [])

  useEffect(() => {
    stopPoll()
    seenSeqs.current = new Set()
    setEvents([])
    setStatus('idle')
    if (!runId) return

    // WS 广播的 data 载荷: {seq: number, data: {...AlphaRunEvent fields}}
    // type 即原 SSE event 名 (run_started / candidate_appended / terminal / ...)
    const onWsEvent = (data: Record<string, unknown>, type: string) => {
      // terminal 事件: 关闭流
      if (type === 'terminal') {
        setStatus('done')
        return
      }
      // 进度/候选事件: data.data 是原始 SSE payload (AlphaRunEvent JSON)
      try {
        const seq = typeof data.seq === 'number' ? data.seq : undefined
        const inner = data.data
        // 尝试从 data.data 或 data 本身重构 AlphaRunEvent
        const eventCandidate = (inner && typeof inner === 'object' ? inner : data) as Partial<AlphaRunEvent>
        if (typeof eventCandidate.seq === 'number') {
          if (seenSeqs.current.has(eventCandidate.seq)) return
          seenSeqs.current.add(eventCandidate.seq)
          setEvents(prev => {
            const next = [...prev, eventCandidate as AlphaRunEvent]
            return next.length > EVENT_TAIL_MAX ? next.slice(-EVENT_TAIL_MAX) : next
          })
          setStatus('running')
        } else if (seq != null) {
          // WS 包了 seq 在外层, inner 无 seq
          if (seenSeqs.current.has(seq)) return
          seenSeqs.current.add(seq)
          const eventWithSeq = { ...(eventCandidate as object), seq } as AlphaRunEvent
          setEvents(prev => {
            const next = [...prev, eventWithSeq]
            return next.length > EVENT_TAIL_MAX ? next.slice(-EVENT_TAIL_MAX) : next
          })
          setStatus('running')
        } else {
          // generic alive signal (no seq)
          setStatus('running')
        }
      } catch {
        /* malformed payload — ignore, never crash the stream */
      }
    }

    // 订阅 WS 频道 run:{run_id}
    const channel = `run:${runId}`
    const unsub = wsStream.subscribe(channel, onWsEvent)

    // 降级: 当 WS 不可用时启动轮询 (与原 EventSource===undefined 相同模式)
    // useWsStream 内部退避重连; 这里用 useWsStreamStatus 判断是否完全断开
    // 简化: 启动一个延迟轮询兜底, WS 收到消息后状态变为 running, 轮询检查到 terminal 时停止
    const checkAndPoll = () => {
      setPolling(true)
      pollTimer.current = setInterval(async () => {
        try {
          await fetchAlphaProgress(runId)
          setStatus(prev => prev === 'done' ? prev : 'running')
          const run = await fetchAlphaRun(runId)
          if (isTerminalRun(run.status)) {
            setStatus('done')
            stopPoll()
          }
        } catch {
          /* keep polling until terminal or unmount */
        }
      }, POLL_INTERVAL_MS)
    }
    // 轮询作为 fallback — 仅在 WS 未连上时启动 (延迟 3s 检查)
    const pollFallbackTimer = setTimeout(() => {
      if (status === 'idle' || status === 'reconnecting') {
        checkAndPoll()
      }
    }, 3000)

    return () => {
      unsub()
      clearTimeout(pollFallbackTimer)
      stopPoll()
    }
  }, [runId, stopPoll, status])

  return { status, events, polling }
}

function tokenizeExpression(expr: string): string[] {
  const matched = expr.match(/[A-Za-z_][A-Za-z0-9_]*|[0-9]+(?:\.[0-9]+)?|[+\-*/(),<>:=]|\S/g)
  return matched ?? [...expr]
}

interface DiffToken {
  text: string
  kind: 'same' | 'add' | 'del'
}

/** Longest-common-subsequence token diff of child vs parent canonical expression. */
function diffExpressions(parent: string, child: string): DiffToken[] {
  const a = tokenizeExpression(parent)
  const b = tokenizeExpression(child)
  const m = a.length
  const n = b.length
  // dp[i][j] = LCS length of a[i:] / b[j:]
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array<number>(n + 1).fill(0))
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }
  const out: DiffToken[] = []
  let i = 0
  let j = 0
  while (i < m && j < n) {
    if (a[i] === b[j]) {
      out.push({ text: a[i], kind: 'same' })
      i++
      j++
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      out.push({ text: a[i], kind: 'del' })
      i++
    } else {
      out.push({ text: b[j], kind: 'add' })
      j++
    }
  }
  while (i < m) out.push({ text: a[i++], kind: 'del' })
  while (j < n) out.push({ text: b[j++], kind: 'add' })
  return out
}

// ===== Connection-state chip (mirrors WalkForward.tsx) =====

function ConnChip({ status, polling }: { status: ConnStatus; polling: boolean }) {
  const styles: Record<ConnStatus, string> = {
    idle: 'bg-elevated text-muted border-border',
    running: 'bg-accent/10 text-accent border-accent/25',
    done: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/25',
    error: 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/25',
    reconnecting: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/25',
  }
  const labels: Record<ConnStatus, string> = {
    idle: '待机',
    running: polling ? '轮询中' : '运行中',
    done: '完成',
    error: '错误',
    reconnecting: '连接恢复中',
  }
  return (
    <span
      data-testid="aw-conn-chip"
      data-status={status}
      className={`inline-flex items-center gap-1.5 rounded-btn border px-2.5 py-1 text-xs font-medium ${styles[status]}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${status === 'running' ? 'animate-pulse bg-accent' : status === 'done' ? 'bg-emerald-500' : status === 'reconnecting' ? 'bg-amber-500' : 'bg-muted'}`} />
      {labels[status]}
    </span>
  )
}

// ===== Live progress (event tail) =====

function LiveProgress({ runId }: { runId: string }) {
  const { status, events, polling } = useAlphaStream(runId)
  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-semibold text-foreground">实时进度</h3>
          <span className="font-mono text-[10px] text-muted">
            {polling ? 'SSE 不可用 · 轮询 /progress' : 'EventSource · Last-Event-ID 恢复'}
          </span>
        </div>
        <ConnChip status={status} polling={polling} />
      </div>
      <div
        data-testid="aw-event-tail"
        className="mt-3 max-h-56 overflow-auto rounded-lg border border-border bg-muted/30 p-2 font-mono text-[11px] leading-relaxed"
      >
        {events.length === 0 ? (
          <p className="px-1 py-2 text-muted">等待事件…</p>
        ) : (
          <ul className="space-y-0.5">
            {events.map(evt => (
              <li
                key={`${evt.seq}-${evt.id}`}
                data-testid={`aw-event-seq-${evt.seq}`}
                className="flex items-center gap-2 px-1"
              >
                <span className="shrink-0 rounded bg-elevated px-1.5 text-[10px] text-muted">#{evt.seq}</span>
                <span className="shrink-0 text-accent">{evt.event_type}</span>
                <span className="truncate text-secondary">{evt.entity_kind}:{evt.entity_id}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

// ===== Lineage tree (SC2) =====

function LineageTree({ runId }: { runId: string }) {
  const query = useQuery({
    queryKey: ['alpha-lineage', runId],
    queryFn: () => fetchAlphaLineage(runId),
    enabled: !!runId,
  })

  const replay = useMutation({
    mutationFn: (parentStep: number) =>
      postReplayBranch(runId, {
        idempotency_key: `aw-replay-${runId}-${parentStep}-${Date.now().toString(36)}`,
        parent_step: parentStep,
      }),
    onSuccess: (data: ReplayBranchResult) =>
      toast(`已派生子运行 ${data.child_run_id.slice(0, 10)}…`, 'success'),
    onError: () => toast('分支重放失败', 'error'),
  })
  const clone = useMutation({
    mutationFn: () =>
      postClone(runId, { idempotency_key: `aw-clone-${runId}-${Date.now().toString(36)}` }),
    onSuccess: (data: CloneResult) =>
      toast(data.no_op ? '输入未变 · 返回父运行' : `已克隆 ${data.clone_run_id.slice(0, 10)}…`, 'success'),
    onError: () => toast('克隆失败', 'error'),
  })

  const edges: AlphaLineageEdge[] = query.data?.edges ?? []

  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="mb-3 flex items-center gap-2">
        <GitBranch className="h-4 w-4 text-accent" />
        <h3 className="text-sm font-semibold text-foreground">谱系树</h3>
        <span className="font-mono text-[10px] text-muted">父 → 子 · 规范表达式差异</span>
        <button
          data-testid="aw-clone-run"
          onClick={() => clone.mutate()}
          disabled={clone.isPending}
          className="ml-auto inline-flex items-center gap-1 rounded-btn border border-border px-2 py-1 text-xs text-secondary transition-colors hover:bg-elevated disabled:opacity-50"
        >
          <Copy className="h-3.5 w-3.5" /> 克隆运行
        </button>
      </div>
      {query.isLoading ? (
        <p className="py-4 text-xs text-muted">加载谱系…</p>
      ) : edges.length === 0 ? (
        <EmptyState icon={GitFork} title="暂无谱系边" hint="生成候选后会显示父→子变异/交叉谱系。" />
      ) : (
        <ul data-testid="aw-lineage-tree" className="space-y-2">
          {edges.map(edge => {
            const diff = diffExpressions(
              edge.parent.canonical_expression,
              edge.child.canonical_expression,
            )
            return (
              <li
                key={edge.lineage_id}
                data-testid="aw-lineage-edge"
                className="rounded-lg border border-border bg-muted/20 p-3"
              >
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
                  <span className="rounded bg-elevated px-1.5 py-0.5 font-mono text-[10px] text-secondary">
                    #{edge.edge_ordinal} {edge.operation}
                  </span>
                  <span>seed {edge.child.seed}</span>
                  <span>step {edge.child.step}</span>
                  <span className="text-accent">{edge.child.status}</span>
                </div>
                <div className="mt-2 flex flex-wrap items-start gap-2">
                  <code className="rounded bg-elevated px-1.5 py-1 font-mono text-[10px] text-muted">
                    {edge.parent.canonical_expression}
                  </code>
                  <span className="pt-1 text-muted">→</span>
                  <code data-testid="aw-lineage-diff" className="flex flex-wrap gap-px rounded bg-elevated px-1.5 py-1 font-mono text-[11px]">
                    {diff.map((tok, idx) => (
                      <span
                        key={idx}
                        className={
                          tok.kind === 'add'
                            ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
                            : tok.kind === 'del'
                              ? 'bg-red-500/15 text-red-600 dark:text-red-400 line-through'
                              : 'text-secondary'
                        }
                      >
                        {tok.text}
                      </span>
                    ))}
                  </code>
                </div>
                <button
                  data-testid="aw-replay-branch"
                  onClick={() => replay.mutate(edge.child.step)}
                  disabled={replay.isPending}
                  className="mt-2 inline-flex items-center gap-1 rounded-btn border border-accent/30 bg-accent/5 px-2 py-1 text-xs text-accent transition-colors hover:bg-accent/10 disabled:opacity-50"
                >
                  <Play className="h-3.5 w-3.5" /> 从 step {edge.child.step} 重放分支
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

// ===== Compare panel (SC3 — no opaque winner) =====

const COMPARE_ROWS: { key: keyof AlphaCandidateComparison; label: string; render: (c: AlphaCandidateComparison) => string }[] = [
  { key: 'admission_verdict', label: '准入裁决', render: c => c.admission_verdict ?? '—' },
  { key: 'gate_trail_digest', label: '闸门轨迹', render: c => c.gate_trail_digest?.slice(0, 12) ?? '—' },
  { key: 'policy_version', label: '策略版本', render: c => c.policy_version ?? '—' },
  { key: 'fold_evidence', label: '折证据', render: c => `${c.fold_evidence.length} 条` },
  { key: 'artifact_refs', label: '产物引用', render: c => `${c.artifact_refs.length} 条` },
  { key: 'diversity', label: '多样性', render: c => (c.diversity ? '已记录' : '—') },
]

function ComparePanel({ runId, candidates }: { runId: string; candidates: AlphaCandidate[] }) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const orderedSelected = useMemo(
    () => candidates.filter(c => selected.has(c.id)).map(c => c.id),
    [candidates, selected],
  )

  const query = useQuery({
    queryKey: ['alpha-compare', runId, orderedSelected],
    queryFn: () => fetchAlphaCompare(runId, orderedSelected),
    enabled: orderedSelected.length > 0,
  })

  const toggle = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const rows = useMemo<AlphaCandidateComparison[]>(() => query.data?.candidates ?? [], [query.data?.candidates])
  const configKeys = useMemo(() => {
    const keys = new Set<string>()
    for (const c of rows) for (const k of Object.keys(c.config)) keys.add(k)
    return [...keys].sort()
  }, [rows])

  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="mb-3 flex items-center gap-2">
        <GitCompareArrows className="h-4 w-4 text-accent" />
        <h3 className="text-sm font-semibold text-foreground">候选对比</h3>
        <span className="font-mono text-[10px] text-muted">并排证据 · 无聚合赢家</span>
      </div>
      <div data-testid="aw-candidate-picker" className="mb-3 flex flex-wrap gap-2">
        {candidates.map(c => (
          <label
            key={c.id}
            className={`inline-flex cursor-pointer items-center gap-1.5 rounded-btn border px-2 py-1 text-xs transition-colors ${selected.has(c.id) ? 'border-accent/40 bg-accent/10 text-accent' : 'border-border text-secondary hover:bg-elevated'}`}
          >
            <input
              type="checkbox"
              className="h-3 w-3 accent-accent"
              checked={selected.has(c.id)}
              onChange={() => toggle(c.id)}
            />
            <span className="font-mono">{c.id.slice(0, 10)}…</span>
          </label>
        ))}
        {candidates.length === 0 && <span className="text-xs text-muted">无候选</span>}
      </div>
      {orderedSelected.length === 0 ? (
        <p className="py-4 text-xs text-muted">选择两个或更多候选进行并排对比。</p>
      ) : query.isLoading ? (
        <p className="py-4 text-xs text-muted">加载对比…</p>
      ) : (
        <div className="overflow-x-auto">
          <table data-testid="aw-compare-table" className="w-full border-collapse text-xs">
            <thead>
              <tr className="border-b border-border">
                <th className="w-32 p-2 text-left font-medium text-muted">维度</th>
                {rows.map(c => (
                  <th key={c.candidate_id} className="p-2 text-left font-mono font-medium text-foreground">
                    {c.candidate_id.slice(0, 12)}…
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {configKeys.map(k => (
                <tr key={`cfg-${k}`} className="border-b border-border/60">
                  <td className="p-2 text-muted">配置 · {k}</td>
                  {rows.map(c => (
                    <td key={c.candidate_id} className="p-2 font-mono text-secondary">
                      {formatJsonValue(c.config[k])}
                    </td>
                  ))}
                </tr>
              ))}
              {COMPARE_ROWS.map(row => (
                <tr key={row.key} className="border-b border-border/60">
                  <td className="p-2 text-muted">{row.label}</td>
                  {rows.map(c => (
                    <td key={c.candidate_id} className="p-2 font-mono text-secondary">
                      {row.render(c)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

function formatJsonValue(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

// ===== Stress matrix (AF-REQ-20, Tier-1) =====

const DEFAULT_STRESS_AXES = {
  fee_bps: [0, 3, 5],
  slippage_bps: [0, 5, 10],
  rebalance: ['daily', 'weekly'],
}

function StressMatrixView({ runId, candidates }: { runId: string; candidates: AlphaCandidate[] }) {
  const [candidateId, setCandidateId] = useState<string>('')
  const effectiveId = candidateId || candidates[0]?.id || ''
  const query = useQuery({
    queryKey: ['alpha-stress', runId, effectiveId],
    queryFn: () => fetchStressMatrix(runId, effectiveId, DEFAULT_STRESS_AXES),
    enabled: !!effectiveId,
  })
  const matrix: StressMatrix | undefined = query.data

  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Gauge className="h-4 w-4 text-accent" />
        <h3 className="text-sm font-semibold text-foreground">压力矩阵 (Tier-1)</h3>
        <span className="font-mono text-[10px] text-muted">费率 / 滑点 / 调仓 · cost_drag / net 重投影</span>
        <select
          data-testid="aw-stress-candidate"
          value={effectiveId}
          onChange={e => setCandidateId(e.target.value)}
          aria-label="压力矩阵候选"
          className="ml-auto rounded-btn border border-border bg-surface px-2 py-1 text-xs text-foreground"
        >
          {candidates.map(c => (
            <option key={c.id} value={c.id}>
              {c.id.slice(0, 12)}…
            </option>
          ))}
        </select>
      </div>
      {!effectiveId ? (
        <p className="py-4 text-xs text-muted">无候选可分析。</p>
      ) : query.isLoading ? (
        <p className="py-4 text-xs text-muted">加载压力矩阵…</p>
      ) : matrix ? (
        <div data-testid="aw-stress-matrix" className="space-y-3">
          <div className="rounded-lg border border-border bg-muted/20 p-3">
            <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted">冻结基线</div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-secondary">
              <span>turnover {fmt(matrix.baseline.total_turnover)}</span>
              <span>cost_rate {fmt(matrix.baseline.cost_rate)}</span>
              <span>cost_drag {fmt(matrix.baseline.cost_drag)}</span>
              <span>net {fmt(matrix.baseline.net_long_short_return)}</span>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="border-b border-border">
                  <th className="p-2 text-left font-medium text-muted">轴</th>
                  <th className="p-2 text-left font-medium text-muted">取值</th>
                  <th className="p-2 text-right font-medium text-muted">cost_drag</th>
                  <th className="p-2 text-right font-medium text-muted">net</th>
                </tr>
              </thead>
              <tbody>
                {matrix.matrix.map((row, idx) => (
                  <tr key={`${row.axis}-${row.value}-${idx}`} data-testid="aw-stress-row" className="border-b border-border/60">
                    <td className="p-2 text-muted">{row.axis}</td>
                    <td className="p-2 font-mono text-secondary">{String(row.value)}</td>
                    <td className="p-2 text-right font-mono text-secondary">{fmt(row.cost_drag)}</td>
                    <td className="p-2 text-right font-mono text-secondary">{fmt(row.net_long_short_return)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  )
}

function fmt(n: number): string {
  if (!Number.isFinite(n)) return '—'
  return Math.abs(n) >= 1 ? n.toFixed(3) : n.toFixed(5)
}

// ===== Data-quality banner (SC4 — clean-bound) =====

/** Compose the specific degraded reason the red banner displays (SC4). */
function dirtyReason(cls: EvidenceClassification): string {
  const reasons: string[] = []
  if (cls.cache_state !== 'fresh') reasons.push(`缓存 ${cls.cache_state}`)
  if (cls.missing_fields.length > 0) reasons.push(`缺失字段 ${cls.missing_fields.length}`)
  if (cls.membership_coverage < 0.9) reasons.push(`覆盖 ${(cls.membership_coverage * 100).toFixed(0)}%`)
  if (cls.fixture) reasons.push('fixture 数据')
  if (cls.evidence_role === 'final_blind_unavailable') reasons.push('最终盲测不可用')
  return reasons.length > 0 ? reasons.join(' · ') : '证据不洁净'
}

function DataQualityBanner({ runId, candidates }: { runId: string; candidates: AlphaCandidate[] }) {
  const [candidateId, setCandidateId] = useState<string>('')
  const effectiveId = candidateId || candidates[0]?.id || ''
  const query = useQuery({
    queryKey: ['alpha-evidence-classification', runId, effectiveId],
    queryFn: () => fetchEvidenceClassification(runId, effectiveId),
    enabled: !!effectiveId,
  })
  const cls: EvidenceClassification | undefined = query.data

  return (
    <section className="rounded-card border border-border bg-surface p-4">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-foreground">数据质量</h3>
        <span className="font-mono text-[10px] text-muted">绑定 evidence_classification.clean</span>
        <select
          data-testid="aw-quality-candidate"
          value={effectiveId}
          onChange={e => setCandidateId(e.target.value)}
          aria-label="质量评估候选"
          className="ml-auto rounded-btn border border-border bg-surface px-2 py-1 text-xs text-foreground"
        >
          {candidates.map(c => (
            <option key={c.id} value={c.id}>
              {c.id.slice(0, 12)}…
            </option>
          ))}
        </select>
      </div>
      {!effectiveId ? (
        <p className="py-2 text-xs text-muted">无候选可分类。</p>
      ) : query.isLoading ? (
        <p className="py-2 text-xs text-muted">加载分类…</p>
      ) : cls ? (
        <div
          data-testid="aw-banner"
          data-clean={cls.clean ? 'true' : 'false'}
          className={`flex items-start gap-3 rounded-lg border p-3 ${cls.clean ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-red-500/40 bg-red-500/10'}`}
        >
          {cls.clean ? (
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600 dark:text-emerald-400" />
          ) : (
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-red-600 dark:text-red-400" />
          )}
          <div className="min-w-0">
            <div className={`text-sm font-semibold ${cls.clean ? 'text-emerald-700 dark:text-emerald-300' : 'text-red-700 dark:text-red-300'}`}>
              {cls.clean ? '洁净证据' : '证据不洁净 — 降级结果不可视为洁净生产'}
            </div>
            {!cls.clean && (
              <p data-testid="aw-banner-reason" className="mt-0.5 text-xs text-red-600 dark:text-red-400">
                {dirtyReason(cls)}
              </p>
            )}
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-muted">
              <span>角色 {cls.evidence_role}</span>
              <span>缓存 {cls.cache_state}</span>
              <span>覆盖 {(cls.membership_coverage * 100).toFixed(0)}%</span>
              {cls.data_date && <span>日期 {cls.data_date}</span>}
              {cls.source_label && <span>来源 {cls.source_label}</span>}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}

// ===== Page shell =====

type Tab = 'lineage' | 'compare' | 'stress' | 'quality'

const TABS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: 'lineage', label: '谱系', icon: GitBranch },
  { id: 'compare', label: '对比', icon: GitCompareArrows },
  { id: 'stress', label: '压力', icon: Gauge },
  { id: 'quality', label: '数据质量', icon: ShieldAlert },
]

export function AlphaWorkbench() {
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('lineage')

  const runsQuery = useQuery({
    queryKey: ['alpha-runs'],
    queryFn: fetchAlphaRuns,
  })

  const runs: AlphaRunRead[] = runsQuery.data ?? []
  const selectedRun = runs.find(r => r.id === selectedRunId) ?? runs[0] ?? null
  const activeRunId = selectedRun?.id ?? null

  const candidatesQuery = useQuery({
    queryKey: ['alpha-candidates', activeRunId],
    queryFn: () => fetchAlphaCandidates(activeRunId!),
    enabled: !!activeRunId,
  })
  const candidates: AlphaCandidate[] = candidatesQuery.data ?? []

  return (
    <>
      <PageHeader title="Alpha 回放工作台" subtitle="实时进度 · 谱系 · 对比 · 压力 · 数据质量" />
      <div data-testid="aw-page" className="px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
          {/* Runs list */}
          <section className="rounded-card border border-border bg-surface">
            <div className="border-b border-border px-3 py-2 text-xs font-semibold text-secondary">
              Alpha 运行 {runsQuery.data ? `(${runsQuery.data.length})` : ''}
            </div>
            <div data-testid="aw-runs-list" className="max-h-[calc(100vh-16rem)] overflow-auto p-2 space-y-1">
              {runs.length === 0 && !runsQuery.isLoading && (
                <EmptyState icon={GitFork} title="暂无运行" hint="创建 Alpha 运行后会显示在这里。" />
              )}
              {runsQuery.isLoading && <p className="px-1 py-2 text-xs text-muted">加载运行…</p>}
              {runs.map(run => (
                <button
                  key={run.id}
                  data-testid={`aw-run-${run.id}`}
                  onClick={() => setSelectedRunId(run.id)}
                  className={`w-full rounded-lg px-3 py-2 text-left transition-colors ${selectedRun?.id === run.id ? 'bg-accent/10 border border-accent/25' : 'border border-transparent hover:bg-elevated/60'}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-mono text-xs font-medium text-foreground">{run.id}</span>
                    <span className={`shrink-0 rounded px-1.5 py-px text-[9px] font-medium ${run.status === 'completed' ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400' : run.status === 'failed' || run.status === 'preflight_failed' ? 'bg-red-500/15 text-red-600 dark:text-red-400' : 'bg-accent/15 text-accent'}`}>
                      {run.status}
                    </span>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 text-[10px] text-muted">
                    <span>候选 {run.candidate_attempts_completed}/{run.candidate_attempts_total}</span>
                    <span>折 {run.folds_completed}/{run.folds_total}</span>
                  </div>
                </button>
              ))}
            </div>
          </section>

          {/* Detail */}
          <section className="min-w-0 space-y-4">
            {!selectedRun ? (
              <div className="flex items-center justify-center rounded-card border border-border bg-surface py-20">
                <div className="text-center">
                  <GitFork className="mx-auto h-8 w-8 text-muted/40" />
                  <p className="mt-3 text-sm text-secondary">选择左侧运行查看回放工作台</p>
                  <p className="mt-1 text-xs text-muted">实时进度 · 谱系树 · 候选对比 · 压力矩阵 · 数据质量</p>
                </div>
              </div>
            ) : (
              <>
                <div className="rounded-card border border-border bg-surface p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h2 className="font-mono text-sm font-semibold text-foreground">{selectedRun.id}</h2>
                      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
                        <span>状态 {selectedRun.status}</span>
                        <span>last_seq {selectedRun.last_event_seq}</span>
                        <span>snapshot {selectedRun.snapshot_sha256.slice(0, 10)}…</span>
                      </div>
                    </div>
                  </div>
                </div>
                <LiveProgress runId={selectedRun.id} />
                <div className="flex flex-wrap gap-1 rounded-card border border-border bg-surface p-1">
                  {TABS.map(t => {
                    const Icon = t.icon
                    return (
                      <button
                        key={t.id}
                        data-testid={`aw-tab-${t.id}`}
                        onClick={() => setTab(t.id)}
                        className={`inline-flex items-center gap-1.5 rounded-btn px-3 py-1.5 text-xs font-medium transition-colors ${tab === t.id ? 'bg-accent/10 text-accent' : 'text-secondary hover:bg-elevated/60'}`}
                      >
                        <Icon className="h-3.5 w-3.5" /> {t.label}
                      </button>
                    )
                  })}
                </div>
                {tab === 'lineage' && <LineageTree runId={selectedRun.id} />}
                {tab === 'compare' && <ComparePanel runId={selectedRun.id} candidates={candidates} />}
                {tab === 'stress' && <StressMatrixView runId={selectedRun.id} candidates={candidates} />}
                {tab === 'quality' && <DataQualityBanner runId={selectedRun.id} candidates={candidates} />}
                {/* Phase 54: 证据卡 + 冲突观点 (运行维度) */}
                <div className="space-y-4 rounded-card border border-border bg-surface p-4">
                  <div>
                    <h3 className="mb-2 text-xs font-semibold text-secondary">证据卡</h3>
                    <EvidenceCards runId={selectedRun.id} />
                  </div>
                  <div>
                    <h3 className="mb-2 text-xs font-semibold text-secondary">冲突观点与失败路径</h3>
                    <ConflictPaths runId={selectedRun.id} />
                  </div>
                </div>
              </>
            )}
          </section>
        </div>
      </div>
    </>
  )
}
