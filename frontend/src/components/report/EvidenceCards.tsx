import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { FileSearch, Loader2, AlertTriangle, Clock, ExternalLink, Hash } from 'lucide-react'
import { fetchEvidence, type EvidenceResponse } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

/**
 * Phase 54 (MON-04) — 证据卡列表。
 *
 * 从 /api/report-ops/evidence 拉取报告关联的证据卡 (raw_hash/tool/category/
 * response_summary/duration), 展示为卡片网格; 每张卡可跳转到 /audit 查看明细。
 *
 * 支持两种入参:
 *   - runId:  决策/分析运行 ID
 *   - reportType + reportId:  报告类型 (financial|market_recap) + 报告 ID
 */
interface Props {
  runId?: string
  reportType?: string
  reportId?: string
}

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return iso
  }
}

function shortHash(hash: string): string {
  if (!hash) return '—'
  return hash.length > 12 ? `${hash.slice(0, 8)}…${hash.slice(-4)}` : hash
}

export function EvidenceCards({ runId, reportType, reportId }: Props) {
  const params = { run_id: runId, report_type: reportType, report_id: reportId }
  const query = useQuery<EvidenceResponse>({
    queryKey: QK.reportOps({ ...params, _t: 'evidence' }),
    queryFn: () => fetchEvidence(params as { run_id?: string; report_type?: string; report_id?: string }),
    enabled: !!(runId || (reportType && reportId)),
  })

  const cards = query.data?.evidence_cards ?? []

  if (query.isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-card border border-border bg-surface/60 px-4 py-8">
        <Loader2 className="h-4 w-4 animate-spin text-accent" />
        <span className="text-xs text-muted">加载证据卡…</span>
      </div>
    )
  }

  if (query.isError) {
    return (
      <div className="flex items-center justify-center gap-2 rounded-card border border-danger/30 bg-danger/5 px-4 py-8 text-xs text-danger">
        <AlertTriangle className="h-4 w-4" />
        证据卡加载失败
      </div>
    )
  }

  if (cards.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-card border border-dashed border-border/50 bg-surface/40 px-4 py-8 text-center">
        <FileSearch className="h-6 w-6 text-muted/40" />
        <span className="text-xs text-muted">暂无关联证据卡</span>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {cards.map((card, i) => (
          <div
            key={i}
            className="group rounded-card border border-border/60 bg-surface/60 px-3 py-2.5 transition-colors hover:border-accent/30"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex min-w-0 items-center gap-1.5">
                <span className="truncate text-xs font-medium text-foreground">
                  {card.title || card.tool}
                </span>
                {card.error && (
                  <span className="shrink-0 rounded bg-red-500/10 px-1 py-0.5 text-[9px] text-red-600 dark:text-red-400">
                    失败
                  </span>
                )}
              </div>
              <span className="shrink-0 rounded bg-elevated px-1.5 py-0.5 text-[9px] text-muted">
                {card.category}
              </span>
            </div>

            <div className="mt-1.5 flex items-center gap-2 text-[10px] text-muted">
              <span className="inline-flex items-center gap-0.5 font-mono" title={card.raw_hash}>
                <Hash className="h-2.5 w-2.5" />
                {shortHash(card.raw_hash)}
              </span>
              <span className="text-secondary">·</span>
              <span className="truncate">{card.tool}</span>
              {card.duration_ms > 0 && (
                <>
                  <span className="text-secondary">·</span>
                  <span className="tabular-nums">{card.duration_ms}ms</span>
                </>
              )}
            </div>

            {card.response_summary && (
              <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-secondary">
                {typeof card.response_summary === 'string'
                  ? card.response_summary
                  : JSON.stringify(card.response_summary)}
              </p>
            )}

            <div className="mt-2 flex items-center justify-between">
              <span className="flex items-center gap-0.5 text-[9px] text-muted">
                <Clock className="h-2.5 w-2.5" />
                {fmtTime(card.created_at)}
              </span>
              <Link
                to={`/audit?tool=${encodeURIComponent(card.tool)}`}
                className="inline-flex items-center gap-0.5 text-[10px] text-accent opacity-0 transition-opacity hover:underline group-hover:opacity-100"
              >
                <ExternalLink className="h-2.5 w-2.5" />
                审计
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
