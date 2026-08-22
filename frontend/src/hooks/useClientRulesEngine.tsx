/**
 * useClientRulesEngine — WS quotes 订阅 + 行情拉取 + 本地评估 + 通知触发 (D-02, D-03)
 *
 * 在 Layout 全局挂载一次 (常驻后台):
 * 1. subscribe('quotes', handler) — 收到 quotes_updated tick 时 invalidateQueries
 * 2. quotesQuery.data 更新后 evaluateRules → 命中检查防抖 → triggerAlert
 * 3. 暴露 rules/triggered 列表 + CRUD 方法 + notification 权限状态
 *
 * 规则数据仅存 localStorage, 不向后端发送 (D-01, D-06)。
 */

import { useState, useEffect, useCallback, useRef, createContext, useContext, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { subscribe } from '@/lib/useWsStream'
import { api } from '@/lib/api'
import { QK } from '@/lib/queryKeys'
import {
  loadRules,
  addRule as _addRule,
  updateRule as _updateRule,
  deleteRule as _deleteRule,
  markHandled as _markHandled,
  disableRule as _disableRule,
  evaluateRules,
  isDebounced,
  markTriggered,
  clearTriggered,
  getNotificationPermission,
  requestNotificationPermission,
  triggerAlert,
  type ClientRule,
  type TriggeredRecord,
} from '@/lib/clientRules'

export interface ClientRulesEngine {
  rules: ClientRule[]
  triggered: TriggeredRecord[]
  addRule: (rule: Omit<ClientRule, 'id' | 'createdAt'>) => ClientRule
  updateRule: (id: string, patch: Partial<ClientRule>) => void
  deleteRule: (id: string) => void
  markHandled: (id: string) => void
  disableRule: (id: string) => void
  notificationPermission: NotificationPermission
  requestPermission: () => void
}

export function useClientRulesEngine(): ClientRulesEngine {
  const [rules, setRules] = useState<ClientRule[]>(() => loadRules())
  const [triggered, setTriggered] = useState<TriggeredRecord[]>([])
  const [notificationPermission, setNotificationPermission] = useState<NotificationPermission>(
    () => getNotificationPermission(),
  )
  const rulesRef = useRef(rules)
  rulesRef.current = rules
  const triggeredRef = useRef(triggered)
  triggeredRef.current = triggered

  const qc = useQueryClient()

  // 行情查询: quotes_updated tick → invalidate → refetch
  const quotesQuery = useQuery({
    queryKey: QK.watchlistQuotes,
    queryFn: () => api.watchlistQuotes(),
    staleTime: 0,
  })

  // 订阅 quotes 频道 — 收到 quotes_updated 时 invalidate 触发 refetch (D-02)
  useEffect(() => {
    const unsub = subscribe('quotes', (_data: Record<string, unknown>, type: string) => {
      if (type === 'quotes_updated') {
        qc.invalidateQueries({ queryKey: QK.watchlistQuotes })
      }
    })
    return unsub
  }, [qc])

  // 行情更新后评估规则 (D-02, D-03)
  useEffect(() => {
    const quotes = quotesQuery.data?.quotes
    if (!quotes || quotes.length === 0) return

    const currentRules = rulesRef.current
    if (currentRules.length === 0) return

    const hits = evaluateRules(quotes, currentRules)
    if (hits.length === 0) return

    const now = Date.now()
    const newTriggered: TriggeredRecord[] = []

    for (const { rule, quote } of hits) {
      if (isDebounced(rule.id, now)) continue
      markTriggered(rule.id, now)
      triggerAlert(rule, quote)
      newTriggered.push({
        ruleId: rule.id,
        triggeredAt: now,
        triggeredPrice: quote.price ?? quote.close ?? null,
        triggeredPct: quote.pct ?? quote.change_pct ?? null,
      })
    }

    if (newTriggered.length > 0) {
      setTriggered(prev => [...prev, ...newTriggered])
    }
  }, [quotesQuery.data])

  // CRUD 方法 — 操作 storage + 同步 state
  const addRule = useCallback((rule: Omit<ClientRule, 'id' | 'createdAt'>): ClientRule => {
    const newRule = _addRule(rule)
    setRules(loadRules())
    return newRule
  }, [])

  const updateRule = useCallback((id: string, patch: Partial<ClientRule>): void => {
    _updateRule(id, patch)
    setRules(loadRules())
  }, [])

  const deleteRule = useCallback((id: string): void => {
    _deleteRule(id)
    setRules(loadRules())
    setTriggered(prev => prev.filter(t => t.ruleId !== id))
  }, [])

  const markHandled = useCallback((id: string): void => {
    _markHandled(id)
    setTriggered(prev => prev.filter(t => t.ruleId !== id))
  }, [])

  const disableRule = useCallback((id: string): void => {
    _disableRule(id)
    setRules(loadRules())
  }, [])

  const requestPermission = useCallback((): void => {
    requestNotificationPermission().then((perm: NotificationPermission) => setNotificationPermission(perm))
  }, [])

  return {
    rules,
    triggered,
    addRule,
    updateRule,
    deleteRule,
    markHandled,
    disableRule,
    notificationPermission,
    requestPermission,
  }
}

// ── Context + Provider (Task 2) ──────────────────────────────

const ClientRulesContext = createContext<ClientRulesEngine | null>(null)

export function ClientRulesProvider({ children }: { children: ReactNode }) {
  const engine = useClientRulesEngine()
  return <ClientRulesContext.Provider value={engine}>{children}</ClientRulesContext.Provider>
}

export function useClientRules(): ClientRulesEngine {
  const ctx = useContext(ClientRulesContext)
  if (!ctx) throw new Error('useClientRules must be used within ClientRulesProvider')
  return ctx
}

// re-export clearTriggered for test cleanup
export { clearTriggered }
