import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Layers, ShieldAlert } from 'lucide-react'
import { api, type AttributionEvidenceDTO } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import { PageHeader } from '@/components/PageHeader'
import { EmptyState } from '@/components/EmptyState'

const TYPE_LABEL: Record<string, string> = {
  exposure_contribution: '敞口归因',
  drawdown: '回撤归因',
}

/**
 * A reconciliation payload is server-owned and opaque to the browser; we never
 * interpret its meaning. We only surface a PSD-repair warning when the payload
 * carries the documented repair provenance (risk_model_json.psd_repair.method
 * != "none", or a non-null eigenvalues_after) — proving the covariance entering
 * the attribution was numerically repaired. Absent that, no chip is shown.
 */
function detectPsdRepair(rec: Record<string, unknown> | null): string | null {
  if (!rec || typeof rec !== 'object') return null
  const psd = rec['psd_repair']
  if (psd && typeof psd === 'object') {
    const method = (psd as Record<string, unknown>)['method']
    if (typeof method === 'string' && method !== 'none') return method
  }
  const after = rec['eigenvalues_after']
  if (after !== null && after !== undefined) return 'eigen_clip'
  return null
}

function fmtNum(v: number): string {
  if (!Number.isFinite(v)) return '—'
  if (v === 0) return '0'
  const abs = Math.abs(v)
  if (abs < 1e-3 || abs >= 1e6) return v.toExponential(2)
  return Number.isInteger(v) ? String(v) : v.toFixed(4)
}

function fmtVal(v: unknown): string {
  if (typeof v === 'number') return fmtNum(v)
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') return '{…}'
  return String(v)
}

function reconciliationSummary(rec: Record<string, unknown> | null): string {
  if (!rec) return '无对账载荷'
  const keys = Object.keys(rec)
  if (keys.length === 0) return '空对账'
  return keys.slice(0, 3).map(k => `${k}=${fmtVal(rec[k])}`).join(' · ')
}

export function RiskAttribution() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [typeFilter, setTypeFilter] = useState<string | undefined>(undefined)

  const listQuery = useQuery({
    queryKey: QK.attribution(undefined),
    queryFn: () => api.listAttribution({ attribution_type: typeFilter }),
  })
  const detailQuery = useQuery({
    queryKey: ['attribution-evidence', selectedId ?? ''],
    queryFn: () => api.listAttribution({ run_id: undefined }).then(rows => rows.find(r => r.id === selectedId) ?? null),
    enabled: !!selectedId,
  })

  const rows = listQuery.data ?? []
  const selected = selectedId ? rows.find(r => r.id === selectedId) ?? detailQuery.data ?? null : null

  return (
    <>
      <PageHeader
        title="风险归因"
        subtitle="不可变归因证据 · 敞口/回撤分解 · 对账审计"
        right={
          <div className="flex items-center gap-2">
            {(['exposure_contribution', 'drawdown'] as const).map(t => (
              <button
                key={t}
                onClick={() => { setTypeFilter(t === typeFilter ? undefined : t); setSelectedId(null) }}
                className={`min-h-8 rounded-btn px-3 text-xs font-medium transition-colors ${
                  typeFilter === t
                    ? 'bg-accent/15 text-accent'
                    : 'border border-border bg-surface text-secondary hover:text-foreground'
                }`}
              >
                {TYPE_LABEL[t]}
              </button>
            ))}
          </div>
        }
      />

      <div className="px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[20rem_minmax(0,1fr)]">
          {/* Evidence list */}
          <section className="rounded-card border border-border bg-surface">
            <div className="border-b border-border px-3 py-2 text-xs font-semibold text-secondary">
              归因证据 {listQuery.data ? `(${listQuery.data.length})` : ''}
            </div>
            <div className="max-h-[calc(100vh-16rem)] overflow-auto p-2 space-y-1">
              {listQuery.isLoading && <div className="px-3 py-6 text-center text-xs text-muted">加载中…</div>}
              {listQuery.isError && !listQuery.data && (
                <div role="alert" className="rounded-btn border border-danger/30 bg-danger/10 px-3 py-3 text-xs text-danger">
                  归因证据加载失败：{listQuery.error instanceof Error ? listQuery.error.message : String(listQuery.error ?? '未知错误')}
                  <button type="button" onClick={() => listQuery.refetch()} className="ml-2 inline-flex items-center rounded-btn border border-danger/30 bg-danger/10 px-2 py-1 text-xs font-medium text-danger hover:bg-danger/20 max-md:min-h-11 max-md:min-w-11">重试</button>
                </div>
              )}
              {listQuery.data?.length === 0 && (
                <EmptyState icon={Layers} title="暂无归因证据" hint="对优化运行做风险归因后,证据会出现在这里。" />
              )}
              {rows.map(row => (
                <EvidenceListItem
                  key={row.id}
                  evidence={row}
                  active={selectedId === row.id}
                  onClick={() => setSelectedId(row.id)}
                />
              ))}
            </div>
          </section>

          {/* Evidence detail */}
          <section className="min-w-0">
            {!selectedId ? (
              <div className="flex items-center justify-center rounded-card border border-border bg-surface py-20">
                <div className="text-center">
                  <Layers className="mx-auto h-8 w-8 text-muted/40" />
                  <p className="mt-3 text-sm text-secondary">选择左侧证据查看归因分解</p>
                  <p className="mt-1 text-xs text-muted">贡献分解、对账载荷与 PSD 修复溯源</p>
                </div>
              </div>
            ) : detailQuery.isLoading && !selected ? (
              <div className="rounded-card border border-border bg-surface p-6 text-center text-sm text-muted">加载证据详情…</div>
            ) : selected ? (
              <EvidenceDetail evidence={selected} />
            ) : null}
          </section>
        </div>
      </div>
    </>
  )
}

function EvidenceListItem({ evidence, active, onClick }: { evidence: AttributionEvidenceDTO; active: boolean; onClick: () => void }) {
  const typeLabel = TYPE_LABEL[evidence.attribution_type] ?? evidence.attribution_type
  return (
    <button
      onClick={onClick}
      className={`w-full rounded-lg px-3 py-2 text-left transition-colors ${active ? 'bg-accent/10 border border-accent/25' : 'border border-transparent hover:bg-elevated/60'}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs font-medium text-foreground">{evidence.id}</span>
        <span className="shrink-0 rounded bg-elevated px-1.5 py-px text-[10px] font-medium text-secondary">{typeLabel}</span>
      </div>
      <div className="mt-1 flex items-center gap-2 text-[10px] text-muted">
        <span className="font-mono">{evidence.risk_model ?? '—'}</span>
      </div>
      <div className="mt-0.5 truncate text-[10px] text-muted">{reconciliationSummary(evidence.reconciliation)}</div>
    </button>
  )
}

function EvidenceDetail({ evidence }: { evidence: AttributionEvidenceDTO }) {
  const [expanded, setExpanded] = useState<'contributions' | 'reconciliation' | null>('contributions')
  const typeLabel = TYPE_LABEL[evidence.attribution_type] ?? evidence.attribution_type
  const repairMethod = detectPsdRepair(evidence.reconciliation)
  const contributions = evidence.contributions
  const contribEntries = contributions
    ? Object.entries(contributions).map(([k, v]) => ({ k, v, abs: typeof v === 'number' ? Math.abs(v) : -1 })).sort((a, b) => b.abs - a.abs)
    : []
  const hasNumericContrib = contribEntries.length > 0 && contribEntries.some(e => typeof e.v === 'number')

  const toggle = (key: 'contributions' | 'reconciliation') => setExpanded(prev => prev === key ? null : key)

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="rounded-card border border-border bg-surface p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="font-mono text-sm font-semibold text-foreground">{evidence.id}</h2>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
              <span className="rounded bg-elevated px-1.5 py-0.5 font-medium">{typeLabel}</span>
              <span>风险模型 {evidence.risk_model ?? '—'}</span>
              <span>·</span>
              <span className="font-mono">run {evidence.run_id}</span>
            </div>
          </div>
          <div className="text-right">
            <div className="font-mono text-[10px] text-muted">created</div>
            <div className="font-mono text-[10px] text-secondary">{evidence.created_at}</div>
          </div>
        </div>

        {repairMethod && (
          <div className="mt-3 flex items-start gap-2 rounded-btn border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
            <ShieldAlert className="mt-px h-3.5 w-3.5 shrink-0" />
            <span>协方差已做 PSD 数值修复（method={repairMethod}）——归因基于修复后的矩阵。</span>
          </div>
        )}
      </div>

      {/* Contributions table */}
      {contribEntries.length > 0 && (
        <div className="rounded-card border border-border bg-surface p-4">
          <h3 className="text-sm font-semibold text-foreground">贡献分解</h3>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-[10px] text-muted">
                <tr>
                  <th className="px-2 py-1 font-medium">标的 / 因子</th>
                  <th className="px-2 py-1 text-right font-medium">贡献</th>
                </tr>
              </thead>
              <tbody>
                {contribEntries.map(({ k, v }) => (
                  <tr key={k} className="border-t border-border/50">
                    <td className="px-2 py-1.5 font-mono text-secondary">{k}</td>
                    <td className={`px-2 py-1.5 text-right font-mono tabular-nums ${typeof v === 'number' && v < 0 ? 'text-bear' : 'text-foreground'}`}>
                      {typeof v === 'number' ? fmtNum(v) : fmtVal(v)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!hasNumericContrib && (
            <p className="mt-2 text-[10px] text-muted">贡献载荷非数值表,已按原样展示键值。</p>
          )}
        </div>
      )}

      {/* Expandable audit sections */}
      <div className="space-y-2">
        <ExpandableSection title="对账载荷（reconciliation）" expanded={expanded === 'reconciliation'} onClick={() => toggle('reconciliation')}>
          <pre className="overflow-x-auto whitespace-pre-wrap break-words text-[11px] text-secondary">{JSON.stringify(evidence.reconciliation ?? {}, null, 2)}</pre>
        </ExpandableSection>
      </div>

      <div className="text-[10px] text-muted">
        output_sha256: <span className="font-mono">{(evidence.output_sha256 ?? '').slice(0, 16) || '—'}…</span>
        {evidence.artifact_relative_path && (
          <>
            {' · '}
            artifact: <span className="font-mono">{evidence.artifact_relative_path}</span>
          </>
        )}
      </div>
    </div>
  )
}

function ExpandableSection({ title, expanded, onClick, children }: { title: string; expanded: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <div className="rounded-card border border-border bg-surface">
      <button onClick={onClick} className="flex min-h-11 w-full items-center gap-2 px-3 text-left text-xs font-medium text-foreground hover:bg-elevated/40 transition-colors">
        {expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted" />}
        {title}
      </button>
      {expanded && <div className="border-t border-border px-3 py-3">{children}</div>}
    </div>
  )
}
