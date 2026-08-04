import { AlertTriangle, CheckCircle2, Loader2 } from 'lucide-react'
import { useAuctionProbe, useRedetectAuctionProbe } from '@/lib/useSharedQueries'

// UI-SPEC Phase 16「Required status vocabulary」(approved 2026-08-04):
//   not_configured -> 竞价数据未配置 (muted, hint body, no probe action)
//   available      -> 竞价数据可用 (accent + CheckCircle2) —— 只能来自服务端 status === "available"
//   fail_closed    -> 未接入竞价数据（已退化派生因子） (warning + AlertTriangle, body copy)
//   error          -> 竞价数据探测失败：{message}。已按未接入处理，当前使用派生开盘涨幅因子。请重试。
//                     (danger + role="alert")
//   running        -> 竞价数据探测中… (Loader2 + role="status", 重新探测 disabled)
//
// 诚实规则 (DATA-03): 本面板从不把 09:30 起的连续竞价 bar 标记为集合竞价数据;
// available 处理只对服务端 status === "available" 渲染 —— 无客户端判定合成。
export function AuctionProbeCard() {
  const probe = useAuctionProbe()
  const redetect = useRedetectAuctionProbe()

  const verdict = probe.data
  const running = probe.isLoading || redetect.isPending

  // 服务端已确认未配置时没有任何探测动作 (UI-SPEC「No probe run」)
  const showRetry = verdict != null && verdict.status !== 'not_configured'

  const renderVerdict = () => {
    if (verdict == null) {
      // 探测请求本身失败 (无服务端判定)。按诚实错误态渲染, 永不 blank、永不降级为可用。
      return (
        <div role="alert" className="flex items-start gap-2 text-sm text-danger">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" aria-hidden />
          <span className="break-words [overflow-wrap:anywhere]">
            竞价数据探测失败：无法获取探测结果。已按未接入处理，当前使用派生开盘涨幅因子。请重试。
          </span>
        </div>
      )
    }

    if (verdict.status === 'available') {
      return (
        <div className="flex items-center gap-2 text-sm text-accent">
          <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden />
          <span className="font-medium">竞价数据可用</span>
        </div>
      )
    }

    if (verdict.status === 'fail_closed') {
      return (
        <>
          <div className="flex items-center gap-2 text-sm text-warning">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
            <span className="font-medium">未接入竞价数据（已退化派生因子）</span>
          </div>
          <div className="text-xs text-muted break-words [overflow-wrap:anywhere] leading-relaxed">
            {verdict.detail}
          </div>
        </>
      )
    }

    if (verdict.status === 'error') {
      return (
        <div role="alert" className="flex items-start gap-2 text-sm text-danger">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" aria-hidden />
          <span className="break-words [overflow-wrap:anywhere]">
            竞价数据探测失败：{verdict.detail}。已按未接入处理，当前使用派生开盘涨幅因子。请重试。
          </span>
        </div>
      )
    }

    // not_configured
    return (
      <>
        <div className="text-sm text-muted">
          <span className="font-medium">竞价数据未配置</span>
        </div>
        <div className="text-xs text-muted break-words [overflow-wrap:anywhere] leading-relaxed">
          {verdict.detail}
        </div>
      </>
    )
  }

  return (
    <div className="rounded-card border border-border bg-surface p-4 min-h-[88px]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1.5">
          {running ? (
            <div role="status" className="flex items-center gap-2 text-sm text-secondary">
              <Loader2 className="h-4 w-4 animate-spin shrink-0" aria-hidden />
              <span>竞价数据探测中…</span>
            </div>
          ) : (
            renderVerdict()
          )}
        </div>

        {showRetry && (
          <button
            type="button"
            onClick={() => redetect.mutate()}
            disabled={running}
            className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-btn bg-accent/10 border border-accent/30 text-accent text-xs font-medium hover:bg-accent/20 disabled:opacity-40 disabled:pointer-events-none transition-colors duration-150 ease-smooth min-h-[44px] md:min-h-8"
          >
            重新探测
          </button>
        )}
      </div>
    </div>
  )
}
