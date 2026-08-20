import { useEffect, useState } from 'react'
import { Clock3, CheckCircle2, Send, XCircle, MinusCircle } from 'lucide-react'
import { cn } from '@/lib/cn'

/**
 * Phase 54 (MON-02) — 规则状态徽标。
 *
 * - cooldownRemaining > 0: 显示冷却倒计时 (如"冷却 45m"), 每秒本地递减
 * - 否则: 显示"可触发"
 * - channelHealth: sent (绿) / failed (红) / skipped (灰) 三色 badge
 *
 * 服务端 cooldown_remaining 是评估时刻的剩余秒数; 这里用本地计时器递减以
 * 提供连续的倒计时观感, 但 0 以下视为可触发 (避免负数闪烁)。
 */
interface Props {
  cooldownRemaining: number
  lastFire: number | null
  channelHealth: { sent: number; failed: number; skipped: number }
}

function fmtCountdown(sec: number): string {
  if (sec <= 0) return '可触发'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  if (m > 0) return `冷却 ${m}m${s > 0 ? `${s}s` : ''}`
  return `冷却 ${s}s`
}

export function RuleStatusBadge({ cooldownRemaining, lastFire, channelHealth }: Props) {
  // 本地倒计时: 服务端给的是评估时刻剩余秒数, 客户端每秒递减保持观感连续
  const [remaining, setRemaining] = useState(cooldownRemaining)
  useEffect(() => {
    setRemaining(cooldownRemaining)
    if (cooldownRemaining <= 0) return
    const timer = setInterval(() => {
      setRemaining(prev => (prev <= 1 ? 0 : prev - 1))
    }, 1000)
    return () => clearInterval(timer)
  }, [cooldownRemaining])

  const inCooldown = remaining > 0

  return (
    <div className="flex items-center gap-1.5">
      {/* 冷却 / 可触发 */}
      <span
        className={cn(
          'inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[9px] font-medium',
          inCooldown
            ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
            : 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
        )}
        title={lastFire ? `上次触发: ${new Date(lastFire * 1000).toLocaleString()}` : '无触发记录'}
      >
        {inCooldown ? <Clock3 className="h-2.5 w-2.5" /> : <CheckCircle2 className="h-2.5 w-2.5" />}
        {fmtCountdown(remaining)}
      </span>

      {/* 渠道健康 */}
      <span className="flex items-center gap-0.5" title="渠道投递健康 (近 7 天)">
        {channelHealth.sent > 0 && (
          <span className="inline-flex items-center gap-0.5 rounded bg-emerald-500/10 px-1 py-0.5 text-[9px] text-emerald-600 dark:text-emerald-400">
            <Send className="h-2.5 w-2.5" />
            {channelHealth.sent}
          </span>
        )}
        {channelHealth.failed > 0 && (
          <span className="inline-flex items-center gap-0.5 rounded bg-red-500/10 px-1 py-0.5 text-[9px] text-red-600 dark:text-red-400">
            <XCircle className="h-2.5 w-2.5" />
            {channelHealth.failed}
          </span>
        )}
        {channelHealth.skipped > 0 && (
          <span className="inline-flex items-center gap-0.5 rounded bg-elevated px-1 py-0.5 text-[9px] text-muted">
            <MinusCircle className="h-2.5 w-2.5" />
            {channelHealth.skipped}
          </span>
        )}
      </span>
    </div>
  )
}
