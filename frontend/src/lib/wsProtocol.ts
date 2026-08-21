/** WebSocket 消息协议类型 (D-05/D-07/D-13)。
 *
 * 消息格式: JSON {type: string, seq: number, data: object}
 * 客户端消息: subscribe / unsubscribe / resume / request
 * 服务端事件: quotes_updated / strategy_alert / ping / connected 等
 */

// ── 消息类型 ─────────────────────────────────────────────────

export interface WsMessage {
  type: string
  seq: number
  data: Record<string, unknown>
}

export interface SubscribeMessage {
  type: 'subscribe'
  channels: string[]
}

export interface UnsubscribeMessage {
  type: 'unsubscribe'
  channels: string[]
}

export interface ResumeMessage {
  type: 'resume'
  last_seq: number
}

export interface RequestMessage {
  type: 'request'
  channel: string
  params: Record<string, unknown>
}

// ── 连接状态 (D-13) ──────────────────────────────────────────

export type WsStatus = 'connected' | 'reconnecting' | 'disconnected'

// ── 指数退避序列 (D-13: 1s→2s→4s→8s→16s→30s) ─────────────────

export const BACKOFF_STEPS = [1000, 2000, 4000, 8000, 16000, 30000] as const

// 连续失败到达该阈值后弹一次 toast (只弹一次, 恢复后重置)
export const FAILS_BEFORE_TOAST = 3

// ── 类型守卫 ─────────────────────────────────────────────────

export function isWsMessage(value: unknown): value is WsMessage {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return false
  const v = value as Record<string, unknown>
  return (
    typeof v.type === 'string' &&
    typeof v.seq === 'number' &&
    typeof v.data === 'object' && v.data !== null && !Array.isArray(v.data)
  )
}
