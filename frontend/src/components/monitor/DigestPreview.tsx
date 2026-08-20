import { useQuery } from '@tanstack/react-query'
import { FileText, Loader2, Inbox, X, Clock } from 'lucide-react'
import { Modal } from '@/components/Modal'
import { digestPreview, type DigestPreviewResponse } from '@/lib/api'

/**
 * Phase 54 (MON-03) — 通知摘要预览对话框。
 *
 * 汇总最近 24 小时触发的告警, 生成 digest 文本预览 (不投递)。
 * 展示 digest_text + 触发告警列表 (symbol/name/type/message/severity/occurred_at)。
 */
interface Props {
  onClose: () => void
}

const SEVERITY_STYLE: Record<string, string> = {
  info: 'text-secondary',
  warn: 'text-warning',
  critical: 'text-danger',
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

export function DigestPreviewDialog({ onClose }: Props) {
  const query = useQuery<DigestPreviewResponse>({
    queryKey: ['monitor-ops', 'digest-preview'],
    queryFn: digestPreview,
    staleTime: 30000,
  })

  const data = query.data

  return (
    <Modal
      onClose={onClose}
      ariaLabel="通知摘要预览"
      panelClassName="w-[calc(100vw-32px)] max-w-2xl rounded-dialog border border-border bg-surface p-0 shadow-xl overflow-hidden"
    >
      {/* 头部 */}
      <div className="flex items-center justify-between border-b border-border/60 bg-elevated/40 px-4 py-3">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-semibold text-foreground">通知摘要预览</h3>
          <span className="rounded bg-elevated px-1.5 py-0.5 text-[10px] text-muted">
            近 24 小时 {data?.total_alerts ?? 0} 条
          </span>
        </div>
        <button
          onClick={onClose}
          className="rounded-md p-1 text-muted transition-colors hover:bg-elevated hover:text-foreground max-md:min-h-11 max-md:min-w-11"
          title="关闭"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* 内容 */}
      <div className="max-h-[60vh] overflow-y-auto px-4 py-3.5">
        {query.isLoading ? (
          <div className="flex flex-col items-center justify-center gap-2 py-10">
            <Loader2 className="h-6 w-6 animate-spin text-accent" />
            <span className="text-xs text-secondary">正在生成摘要…</span>
          </div>
        ) : query.isError ? (
          <div className="py-10 text-center text-xs text-danger">
            摘要生成失败, 请稍后重试
          </div>
        ) : !data || data.total_alerts === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
            <Inbox className="h-6 w-6 text-muted/40" />
            <span className="text-xs text-muted">近 24 小时无告警触发</span>
          </div>
        ) : (
          <div className="space-y-3">
            {/* 摘要文本 */}
            {data.digest_text && (
              <div className="rounded-card border border-border/60 bg-base/40 px-3 py-2.5">
                <p className="whitespace-pre-wrap text-xs leading-relaxed text-foreground/90">
                  {data.digest_text}
                </p>
              </div>
            )}
            {/* 告警列表 */}
            <div className="space-y-1.5">
              {data.alerts.map((a, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 rounded-md border border-border/40 bg-base/20 px-2.5 py-2"
                >
                  <span
                    className={`mt-0.5 shrink-0 text-[10px] font-medium ${
                      SEVERITY_STYLE[a.severity] ?? 'text-secondary'
                    }`}
                  >
                    {a.severity}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      {a.symbol && (
                        <span className="shrink-0 font-mono text-[11px] font-medium text-foreground">
                          {a.symbol}
                        </span>
                      )}
                      {a.name && (
                        <span className="truncate text-[11px] text-secondary">{a.name}</span>
                      )}
                    </div>
                    <p className="mt-0.5 truncate text-[11px] text-muted">{a.message}</p>
                  </div>
                  <span className="flex shrink-0 items-center gap-0.5 text-[9px] text-muted">
                    <Clock className="h-2.5 w-2.5" />
                    {fmtTime(a.occurred_at)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 底部 */}
      <div className="flex items-center justify-between gap-2 border-t border-border/60 px-4 py-2.5">
        <span className="text-[10px] text-muted">
          {data?.as_of ? `生成时刻 ${fmtTime(data.as_of)}` : '预览模式, 不会投递'}
        </span>
        <button
          onClick={onClose}
          className="rounded-btn bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground max-md:min-h-11 max-md:min-w-11"
        >
          关闭
        </button>
      </div>
    </Modal>
  )
}
