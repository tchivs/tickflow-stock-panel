/**
 * ClientRuleCard — 单条客户端规则卡片 (D-04, D-06)
 *
 * 参照 RulesList in Monitor.tsx 的规则卡片样式, 但独立为客户端规则。
 * - 左侧: 规则名称 + 标的代码 + 条件描述
 * - 右侧: 启用开关 + 编辑按钮 + 删除按钮
 * - 顶部 badge: 「客户端」(紫色, 与服务端规则区分, D-06)
 * - disabled 规则卡片降低 opacity
 * - triggered 规则卡片左侧加警告色条
 */

import { useState, useRef } from 'react'
import { motion } from 'framer-motion'
import { Trash2, Settings2, Zap } from 'lucide-react'
import { cn } from '@/lib/cn'
import type { ClientRule } from '@/lib/clientRules'

interface Props {
  rule: ClientRule
  isTriggered: boolean
  onEdit: () => void
  onDelete: () => void
  onToggle: () => void
}

const OP_LABEL: Record<ClientRule['op'], string> = {
  '>': '>',
  '<': '<',
  '>=': '≥',
  '<=': '≤',
}

function describeCondition(rule: ClientRule): string {
  const typeLabel = rule.type === 'pct' ? '涨跌幅' : '价格'
  const valueLabel = rule.type === 'pct'
    ? (rule.value * 100).toFixed(2) + '%'
    : rule.value.toFixed(2)
  return `${rule.symbol} ${typeLabel} ${OP_LABEL[rule.op]} ${valueLabel}`
}

export function ClientRuleCard({ rule, isTriggered, onEdit, onDelete, onToggle }: Props) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const handleClickDelete = () => {
    if (confirmDelete) {
      clearTimeout(resetTimer.current ?? undefined)
      setConfirmDelete(false)
      onDelete()
    } else {
      setConfirmDelete(true)
      clearTimeout(resetTimer.current ?? undefined)
      resetTimer.current = setTimeout(() => setConfirmDelete(false), 3000)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn(
        'group relative overflow-hidden rounded-lg border pl-3.5 pr-2.5 py-2 shadow-sm transition-all duration-200 hover:shadow-md hover:shadow-black/10',
        rule.enabled
          ? 'border-border/50 bg-surface hover:border-purple-500/30'
          : 'border-border/30 bg-surface/40 opacity-50 hover:opacity-100',
      )}
    >
      {/* 左侧状态条 */}
      <div className={cn(
        'absolute left-0 top-0 h-full w-0.5',
        isTriggered ? 'bg-warning' : rule.enabled ? 'bg-purple-500/50' : 'bg-border',
      )} />

      {/* 第一行: badge + 名称 + 操作按钮 */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          {/* 客户端 badge (D-06) */}
          <span className="shrink-0 rounded px-1.5 py-0.5 text-[9px] font-semibold bg-purple-500/10 text-purple-500">
            客户端
          </span>
          <h3 className={cn('text-xs font-medium truncate', rule.enabled ? 'text-foreground' : 'text-muted')}>
            {rule.name}
          </h3>
          {isTriggered && (
            <span className="shrink-0 rounded bg-warning/15 px-1 py-px text-[9px] font-medium text-warning animate-pulse">
              已命中
            </span>
          )}
          {!rule.enabled && <span className="shrink-0 text-[9px] text-secondary">· 停用</span>}
        </div>
        <div className="flex items-center gap-0.5 shrink-0">
          <button
            onClick={onToggle}
            title={rule.enabled ? '停用' : '启用'}
            className={cn(
              'p-1 rounded-md transition-all cursor-pointer max-md:min-h-11 max-md:min-w-11',
              rule.enabled ? 'text-purple-500 hover:bg-purple-500/10' : 'text-muted hover:bg-elevated hover:text-purple-500',
            )}
          >
            <Zap className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={onEdit}
            className="p-1 rounded-md text-secondary transition-all hover:bg-accent/10 hover:text-accent cursor-pointer max-md:min-h-11 max-md:min-w-11"
            title="编辑"
          >
            <Settings2 className="h-3.5 w-3.5" />
          </button>
          {confirmDelete ? (
            <button
              onClick={handleClickDelete}
              title="再次点击确认删除"
              className="inline-flex items-center gap-1 rounded-md bg-danger/15 px-1.5 py-0.5 text-[9px] font-medium text-danger border border-danger/30 animate-pulse cursor-pointer"
            >
              <Trash2 className="h-2.5 w-2.5" />确认
            </button>
          ) : (
            <button
              onClick={handleClickDelete}
              className="p-1 rounded-md text-secondary transition-all hover:bg-danger/10 hover:text-danger cursor-pointer max-md:min-h-11 max-md:min-w-11"
              title="删除"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* 第二行: 条件描述 */}
      <div className="mt-0.5 pl-0.5">
        <span className="text-[9px] text-secondary font-mono">{describeCondition(rule)}</span>
      </div>
    </motion.div>
  )
}
