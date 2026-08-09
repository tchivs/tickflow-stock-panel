import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Check, Clock3, Moon, RefreshCw } from 'lucide-react'
import { Modal } from '@/components/Modal'
import { Skeleton } from '@/components/data/Skeleton'
import { api, type DeliveryOutcome, type DeliveryStatus } from '@/lib/api'
import { QK } from '@/lib/queryKeys'

const DELIVERY_META: Record<DeliveryStatus, { label: string; tone: string; Icon: typeof Check }> = {
  pending: { label: '待投递', tone: 'text-muted', Icon: Clock3 },
  sent: { label: '已发送', tone: 'text-emerald-500', Icon: Check },
  failed: { label: '投递失败', tone: 'text-danger', Icon: AlertTriangle },
  skipped: { label: '已跳过', tone: 'text-warning', Icon: Moon },
}

function channelName(channel: DeliveryOutcome['channel']) {
  return channel === 'feishu' ? '飞书' : 'Telegram'
}

function safeReason(reason: string | null) {
  if (!reason) return null
  return reason
    .replace(/https?:\/\/\S+/gi, '[已隐藏链接]')
    .replace(/(?:token|secret|authorization|chat[_-]?id)\s*[:=]\s*[^\s,;]+/gi, '[已隐藏敏感信息]')
    .slice(0, 240)
}

function DeliveryRows({ deliveries }: { deliveries: DeliveryOutcome[] }) {
  return (
    <div className="divide-y divide-border/60 rounded-card border border-border bg-base/30">
      {deliveries.map(delivery => {
        const meta = DELIVERY_META[delivery.status]
        const Icon = meta.Icon
        const timestamp = delivery.updated_at ?? delivery.created_at
        return (
          <div key={delivery.channel} className="flex min-w-0 items-start gap-3 px-3 py-3 text-sm">
            <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${meta.tone}`} aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                <span className="font-medium text-foreground">{channelName(delivery.channel)}</span>
                <span className={`shrink-0 text-xs ${meta.tone}`}>{meta.label}</span>
              </div>
              {timestamp && <time className="mt-1 block font-mono text-xs text-muted">{new Date(timestamp).toLocaleString('zh-CN')}</time>}
              {delivery.status === 'failed' && safeReason(delivery.error) && (
                <p className="mt-1 break-words text-xs leading-5 text-danger">{safeReason(delivery.error)}</p>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function DeliveryDetailDialog({ eventId, onClose }: { eventId: string; onClose: () => void }) {
  const detail = useQuery({
    queryKey: QK.monitorDelivery(eventId),
    queryFn: () => api.alertDeliveryDetails(eventId),
    // 弹窗开着时轮询跟进 pending→sent/failed; 标签页切后台无人在看, 不必继续
    refetchInterval: 10_000,
  })
  const deliveries = detail.data?.deliveries ?? []

  return (
    <Modal
      onClose={onClose}
      ariaLabel="投递结果"
      panelClassName="w-[calc(100vw-32px)] max-w-lg max-h-[90vh] overflow-auto rounded-dialog border border-border bg-surface shadow-xl"
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <h2 className="text-base font-semibold text-foreground">投递结果</h2>
          <p className="mt-1 text-xs text-muted">仅显示已保存的渠道状态与安全错误摘要。</p>
        </div>
        <button onClick={() => detail.refetch()} disabled={detail.isFetching} className="inline-flex h-9 items-center gap-1 rounded-btn border border-border px-2 text-xs text-secondary hover:text-foreground disabled:opacity-50" title="重新加载投递结果">
          <RefreshCw className={`h-3.5 w-3.5 ${detail.isFetching ? 'animate-spin' : ''}`} />重新加载
        </button>
      </div>
      <div className="p-4">
        {detail.isLoading ? (
          <div className="space-y-2">
            <Skeleton h="h-14" rounded="rounded-card" />
            <Skeleton h="h-14" rounded="rounded-card" />
          </div>
        ) : detail.isError ? (
          <div className="space-y-3 text-sm text-danger">
            <p>无法读取投递结果。请稍后重新加载投递结果。</p>
            <button onClick={() => detail.refetch()} className="rounded-btn bg-accent px-3 py-2 text-xs font-medium text-base">重新加载投递结果</button>
          </div>
        ) : deliveries.length === 0 ? (
          <p className="text-sm text-muted">此规则未配置外部通知渠道。</p>
        ) : <DeliveryRows deliveries={deliveries} />}
      </div>
    </Modal>
  )
}
