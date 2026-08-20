import { useMutation } from '@tanstack/react-query'
import { Flame, Loader2, AlertTriangle, CheckCircle2, X } from 'lucide-react'
import { Modal } from '@/components/Modal'
import { testFireRule } from '@/lib/api'

/**
 * Phase 54 (MON-01) — 规则试触对话框。
 *
 * 点击规则行的「试触」按钮后弹出: 调用 /api/monitor-ops/test-fire 对指定规则
 * 执行 synthetic 评估 (不落盘/不推送), 展示触发事件预览 (symbol/name/type/message/severity)。
 * 无事件时显示"当前条件下无触发"; 接口报错时透传后端 error 信息。
 */
interface Props {
  ruleId: string
  ruleName: string
  onClose: () => void
}

const SEVERITY_STYLE: Record<string, string> = {
  info: 'text-secondary',
  warn: 'text-warning',
  critical: 'text-danger',
}

export function TestFireDialog({ ruleId, ruleName, onClose }: Props) {
  const mut = useMutation({ mutationFn: () => testFireRule(ruleId) })

  // 首次挂载自动触发一次 (用户已通过按钮确认要试触)
  if (mut.isIdle) void mut.mutate()

  const events = mut.data?.events ?? []
  const hasError = !!mut.data?.error || mut.isError
  const errorMsg =
    mut.data?.error ??
    (mut.isError && mut.error instanceof Error ? mut.error.message : null)

  return (
    <Modal
      onClose={onClose}
      ariaLabel={`试触规则 ${ruleName}`}
      panelClassName="w-[calc(100vw-32px)] max-w-lg rounded-dialog border border-border bg-surface p-0 shadow-xl overflow-hidden"
    >
      {/* 头部 */}
      <div className="flex items-center justify-between border-b border-border/60 bg-elevated/40 px-4 py-3">
        <div className="flex items-center gap-2">
          <Flame className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-semibold text-foreground">试触规则</h3>
          <span className="truncate text-xs text-secondary">{ruleName}</span>
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
        {mut.isPending ? (
          <div className="flex flex-col items-center justify-center gap-2 py-10">
            <Loader2 className="h-6 w-6 animate-spin text-accent" />
            <span className="text-xs text-secondary">正在评估规则条件…</span>
          </div>
        ) : hasError ? (
          <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
            <AlertTriangle className="h-6 w-6 text-danger" />
            <span className="text-xs text-danger">{errorMsg ?? '试触失败'}</span>
            <button
              onClick={() => mut.mutate()}
              className="mt-1 rounded-btn bg-accent/10 px-3 py-1.5 text-xs text-accent hover:bg-accent/15 max-md:min-h-11"
            >
              重试
            </button>
          </div>
        ) : events.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
            <CheckCircle2 className="h-6 w-6 text-emerald-500" />
            <span className="text-xs text-secondary">当前条件下无触发</span>
          </div>
        ) : (
          <div className="space-y-2.5">
            {mut.data?.would_notify && (
              <div className="rounded-md bg-accent/10 px-2.5 py-1.5 text-[11px] text-accent">
                该规则将推送通知 (符合触发条件)
              </div>
            )}
            {events.map((ev, i) => (
              <div
                key={i}
                className="rounded-card border border-border/60 bg-base/40 px-3 py-2.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-1.5">
                    {ev.symbol && (
                      <span className="shrink-0 font-mono text-xs font-medium text-foreground">
                        {ev.symbol}
                      </span>
                    )}
                    {ev.name && (
                      <span className="truncate text-xs text-secondary">{ev.name}</span>
                    )}
                  </div>
                  <span
                    className={`shrink-0 text-[10px] font-medium ${
                      SEVERITY_STYLE[ev.severity] ?? 'text-secondary'
                    }`}
                  >
                    {ev.severity}
                  </span>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-foreground/90">
                  {ev.message}
                </p>
                {ev.type && (
                  <span className="mt-1 inline-block rounded bg-elevated px-1.5 py-0.5 text-[9px] text-muted">
                    {ev.type}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 底部 */}
      <div className="flex justify-end gap-2 border-t border-border/60 px-4 py-2.5">
        <button
          onClick={onClose}
          className="rounded-btn bg-elevated px-3 py-1.5 text-xs text-secondary hover:text-foreground max-md:min-h-11 max-md:min-w-11"
        >
          关闭
        </button>
        {!mut.isPending && !hasError && events.length > 0 && (
          <button
            onClick={() => mut.mutate()}
            className="rounded-btn bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/15 max-md:min-h-11 max-md:min-w-11"
          >
            再次试触
          </button>
        )}
      </div>
    </Modal>
  )
}
