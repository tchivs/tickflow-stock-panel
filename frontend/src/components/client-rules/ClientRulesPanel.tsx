/**
 * ClientRulesPanel — 客户端规则主面板 (D-03, D-04, D-05, D-06)
 *
 * 消费 useClientRules() Context (Plan 01), 提供:
 * - 规则列表 (ClientRuleCard) + 空状态
 * - 命中列表 (命中时间 + 命中价格 + 标记已处理 / 关闭规则)
 * - 新建/编辑弹窗 (ClientRuleEditor)
 * - 清除全部按钮
 * - Notification 权限提示条 (未开启/被拒两种状态)
 *
 * 与服务端规则完全独立, 不共享数据 (D-06)。
 */

import { useState } from 'react'
import { AnimatePresence } from 'framer-motion'
import { Smartphone, Plus, Trash2, Bell, BellOff, Check, Power } from 'lucide-react'
import { useClientRules } from '@/hooks/useClientRulesEngine'
import { ClientRuleEditor } from './ClientRuleEditor'
import { ClientRuleCard } from './ClientRuleCard'
import { EmptyState } from '@/components/EmptyState'
import { fmtPrice, fmtPct } from '@/lib/format'
import { cn } from '@/lib/cn'
import type { ClientRule, TriggeredRecord } from '@/lib/clientRules'

function formatTime(ts: number): string {
  const d = new Date(ts)
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  const s = String(d.getSeconds()).padStart(2, '0')
  return `${h}:${m}:${s}`
}

export function ClientRulesPanel() {
  const {
    rules,
    triggered,
    addRule,
    updateRule,
    deleteRule,
    markHandled,
    disableRule,
    notificationPermission,
    requestPermission,
  } = useClientRules()

  const [editorOpen, setEditorOpen] = useState(false)
  const [editingRule, setEditingRule] = useState<ClientRule | null>(null)
  const [confirmClearAll, setConfirmClearAll] = useState(false)

  const triggeredByRuleId = new Map<string, TriggeredRecord>()
  for (const t of triggered) {
    if (!triggeredByRuleId.has(t.ruleId)) {
      triggeredByRuleId.set(t.ruleId, t)
    }
  }

  const hasEnabledRules = rules.some(r => r.enabled)
  const showPermissionBanner = notificationPermission !== 'granted' && hasEnabledRules

  const handleNew = () => {
    setEditingRule(null)
    setEditorOpen(true)
  }

  const handleEdit = (rule: ClientRule) => {
    setEditingRule(rule)
    setEditorOpen(true)
  }

  const handleSave = (rule: Omit<ClientRule, 'id' | 'createdAt'> | ClientRule) => {
    if (editingRule) {
      updateRule(editingRule.id, rule)
    } else {
      addRule(rule)
    }
    setEditorOpen(false)
    setEditingRule(null)
  }

  const handleClearAll = () => {
    if (confirmClearAll) {
      for (const r of rules) {
        deleteRule(r.id)
      }
      setConfirmClearAll(false)
    } else {
      setConfirmClearAll(true)
      setTimeout(() => setConfirmClearAll(false), 3000)
    }
  }

  return (
    <div className="flex flex-col">
      {/* 标题行 (D-04, D-06) */}
      <div className="flex items-center gap-2 bg-purple-500/5 px-3 py-2.5 border-b border-border/60">
        <Smartphone className="h-4 w-4 text-purple-500" />
        <h2 className="text-sm font-semibold text-foreground whitespace-nowrap">客户端规则</h2>
        <span className="text-[10px] text-muted">(浏览器本地)</span>
        <span className="rounded-md bg-purple-500/10 px-1.5 py-0.5 text-[10px] font-medium text-purple-500">{rules.length}</span>
        <div className="ml-auto flex items-center gap-1">
          <button
            onClick={handleNew}
            title="新建客户端规则"
            className="inline-flex h-6 w-6 items-center justify-center rounded-lg border border-border/60 bg-surface text-muted transition-all hover:border-purple-500/40 hover:text-purple-500 hover:shadow-sm cursor-pointer max-md:min-h-11 max-md:min-w-11"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={handleClearAll}
            disabled={rules.length === 0}
            title="清除全部客户端规则"
            className={cn(
              'inline-flex h-6 w-6 items-center justify-center rounded-lg border transition-all cursor-pointer max-md:min-h-11 max-md:min-w-11',
              confirmClearAll
                ? 'border-danger/40 bg-danger/15 text-danger animate-pulse'
                : 'border-border/60 bg-surface text-muted hover:border-danger/40 hover:text-danger disabled:opacity-30 disabled:cursor-not-allowed',
            )}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Notification 权限提示条 (D-05) */}
      {showPermissionBanner && (
        <div className={cn(
          'flex items-center gap-2 px-3 py-2 border-b border-border/40 text-[11px]',
          notificationPermission === 'denied'
            ? 'bg-danger/5 text-danger'
            : 'bg-warning/5 text-warning',
        )}>
          {notificationPermission === 'denied' ? <BellOff className="h-3.5 w-3.5 shrink-0" /> : <Bell className="h-3.5 w-3.5 shrink-0" />}
          <span className="flex-1">
            {notificationPermission === 'denied'
              ? '浏览器通知权限被拒绝, 请在浏览器设置中手动允许'
              : '浏览器通知权限未开启, 命中提醒将仅显示页内 toast + 声效'}
          </span>
          {notificationPermission !== 'denied' && (
            <button
              onClick={requestPermission}
              className="shrink-0 rounded-btn bg-warning/15 px-2 py-0.5 text-[10px] font-medium hover:bg-warning/25 transition-colors cursor-pointer max-md:min-h-11 max-md:min-w-11"
            >
              开启通知
            </button>
          )}
        </div>
      )}

      {/* 规则列表区 */}
      <div className="space-y-2.5 p-3.5">
        {rules.length === 0 ? (
          <EmptyState
            icon={Smartphone}
            title="暂无客户端规则"
            hint="点击 + 创建浏览器本地价格规则, 命中后弹窗 + toast 提醒。"
          />
        ) : (
          rules.map(rule => (
            <ClientRuleCard
              key={rule.id}
              rule={rule}
              isTriggered={triggeredByRuleId.has(rule.id)}
              onEdit={() => handleEdit(rule)}
              onDelete={() => deleteRule(rule.id)}
              onToggle={() => updateRule(rule.id, { enabled: !rule.enabled })}
            />
          ))
        )}
      </div>

      {/* 命中记录区 (D-03, D-04) */}
      {triggered.length > 0 && (
        <div className="border-t border-border/60">
          <div className="flex items-center gap-2 px-3 py-2 bg-surface/40">
            <span className="text-[11px] font-medium text-secondary">命中记录</span>
            <span className="rounded-md bg-warning/10 px-1.5 py-0.5 text-[10px] font-medium text-warning">{triggered.length}</span>
          </div>
          <div className="space-y-1.5 p-3.5 pt-2">
            {triggered.map((t, idx) => {
              const rule = rules.find(r => r.id === t.ruleId)
              return (
                <div
                  key={`${t.ruleId}-${t.triggeredAt}-${idx}`}
                  className="flex items-center gap-2 rounded-lg border border-warning/20 bg-warning/5 px-2.5 py-1.5"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] font-medium text-foreground truncate">
                        {rule?.name ?? '(已删除)'}
                      </span>
                      {rule && (
                        <span className="text-[9px] font-mono text-muted">{rule.symbol}</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="text-[9px] text-muted font-mono">{formatTime(t.triggeredAt)}</span>
                      {t.triggeredPrice != null && (
                        <span className="text-[9px] text-secondary">价格 {fmtPrice(t.triggeredPrice)}</span>
                      )}
                      {t.triggeredPct != null && (
                        <span className="text-[9px] text-secondary">涨跌 {fmtPct(t.triggeredPct)}%</span>
                      )}
                    </div>
                  </div>
                  {rule && (
                    <div className="flex items-center gap-0.5 shrink-0">
                      <button
                        onClick={() => markHandled(t.ruleId)}
                        title="标记已处理"
                        className="p-1 rounded-md text-secondary hover:bg-accent/10 hover:text-accent cursor-pointer max-md:min-h-11 max-md:min-w-11"
                      >
                        <Check className="h-3 w-3" />
                      </button>
                      <button
                        onClick={() => disableRule(t.ruleId)}
                        title="关闭规则"
                        className="p-1 rounded-md text-secondary hover:bg-danger/10 hover:text-danger cursor-pointer max-md:min-h-11 max-md:min-w-11"
                      >
                        <Power className="h-3 w-3" />
                      </button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* 新建/编辑弹窗 */}
      <AnimatePresence>
        {editorOpen && (
          <ClientRuleEditor
            rule={editingRule}
            onClose={() => { setEditorOpen(false); setEditingRule(null) }}
            onSave={handleSave}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
