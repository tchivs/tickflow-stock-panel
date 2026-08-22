/**
 * 客户端规则引擎 — 类型定义 + 评估 + 防抖 + Notification API (D-01..D-06)
 *
 * 规则存 localStorage key=client_rules, 不落后端 (D-01, D-06)。
 * 评估为纯函数, 由 useClientRulesEngine hook 在 WS quotes_updated tick 后调用 (D-02)。
 */

import { storage } from './storage'
import { toast } from '@/components/Toast'
import { playNotificationSound } from './notificationSound'
import { fmtPct, fmtPrice } from './format'
import type { Quote } from './api'

// ── 类型定义 (D-01) ──────────────────────────────────────────

export interface ClientRule {
  id: string
  name: string
  symbol: string
  type: 'pct' | 'price'
  op: '>' | '<' | '>=' | '<='
  value: number
  enabled: boolean
  createdAt: string
}

export interface TriggeredRecord {
  ruleId: string
  triggeredAt: number
  triggeredPrice: number | null
  triggeredPct: number | null
}

export interface Hit {
  rule: ClientRule
  quote: Quote
  matchedValue: number
}

// ── 防抖常量 (D-03) ───────────────────────────────────────────

/** 同一规则 5 分钟内不重复触发 */
export const DEBOUNCE_MS = 300_000

// ── 规则 CRUD (操作 storage.clientRules) ──────────────────────

export function loadRules(): ClientRule[] {
  return storage.clientRules.get([]) as ClientRule[]
}

export function saveRules(rules: ClientRule[]): void {
  storage.clientRules.set(rules)
}

export function addRule(rule: Omit<ClientRule, 'id' | 'createdAt'>): ClientRule {
  const rules = loadRules()
  const newRule: ClientRule = {
    ...rule,
    id: _genId(),
    createdAt: new Date().toISOString(),
  }
  saveRules([...rules, newRule])
  return newRule
}

export function updateRule(id: string, patch: Partial<ClientRule>): void {
  const rules = loadRules()
  saveRules(rules.map(r => (r.id === id ? { ...r, ...patch } : r)))
}

export function deleteRule(id: string): void {
  const rules = loadRules()
  saveRules(rules.filter(r => r.id !== id))
  // 清除防抖状态
  clearTriggered(id)
}

/** 清除该规则的 triggered 状态 (不改 rule 本身, D-03) */
export function markHandled(id: string): void {
  clearTriggered(id)
}

/** 关闭规则 (D-03) */
export function disableRule(id: string): void {
  updateRule(id, { enabled: false })
}

// ── 评估引擎 (纯函数, D-02) ───────────────────────────────────

/**
 * 遍历 rules, 过滤 enabled, 按 symbol 匹配 quotes。
 * - pct 类型: 取 q.pct ?? q.change_pct (小数制, 0.0366 = 3.66%)
 * - price 类型: 取 q.price ?? q.close
 *
 * value 非有限值时跳过该规则 (T-57-01 mitigate)。
 * quote 缺匹配字段时不命中。
 */
export function evaluateRules(quotes: Quote[], rules: ClientRule[]): Hit[] {
  const quoteMap = new Map(quotes.map(q => [q.symbol, q]))
  const hits: Hit[] = []

  for (const rule of rules) {
    if (!rule.enabled) continue
    if (!Number.isFinite(rule.value)) continue

    const q = quoteMap.get(rule.symbol)
    if (!q) continue

    const matchedValue = rule.type === 'pct'
      ? (q.pct ?? q.change_pct)
      : (q.price ?? q.close)

    if (matchedValue == null || Number.isNaN(matchedValue)) continue

    if (_compare(matchedValue, rule.op, rule.value)) {
      hits.push({ rule, quote: q, matchedValue })
    }
  }

  return hits
}

// ── 防抖 (模块级内存 Map, 不持久化, D-03) ──────────────────────

const _lastTriggered = new Map<string, number>()

export function isDebounced(ruleId: string, now: number): boolean {
  const ts = _lastTriggered.get(ruleId)
  if (ts == null) return false
  return now - ts < DEBOUNCE_MS
}

export function markTriggered(ruleId: string, now: number): void {
  _lastTriggered.set(ruleId, now)
}

export function clearTriggered(ruleId: string): void {
  _lastTriggered.delete(ruleId)
}

// ── Notification API (D-05) ───────────────────────────────────

export function getNotificationPermission(): NotificationPermission {
  if (typeof Notification === 'undefined') return 'denied'
  return Notification.permission
}

export async function requestNotificationPermission(): Promise<NotificationPermission> {
  if (typeof Notification === 'undefined') return 'denied'
  try {
    return await Notification.requestPermission()
  } catch {
    return 'denied'
  }
}

/** 权限被拒时静默跳过, 不报错 (D-05) */
export function showNotification(title: string, body: string): void {
  if (typeof Notification === 'undefined') return
  if (Notification.permission !== 'granted') return
  try {
    new Notification(title, { body, icon: '/favicon.ico' })
  } catch {
    // 某些浏览器在 SW 上下文外可能抛错, 静默忽略
  }
}

// ── 通知触发: 组合 toast + sound + notification (D-02) ──────────

export function triggerAlert(rule: ClientRule, quote: Quote): void {
  const title = `${rule.name} 命中`
  const valueDesc = rule.type === 'pct'
    ? `涨跌幅 ${rule.op} ${fmtPct(rule.value)}`
    : `价格 ${rule.op} ${fmtPrice(rule.value)}`

  const body = `${rule.symbol} ${valueDesc} (当前 ${rule.type === 'pct' ? fmtPct(quote.pct ?? quote.change_pct) : fmtPrice(quote.price ?? quote.close)})`

  toast(`${rule.symbol} ${rule.name}: ${valueDesc}`, 'error')
  playNotificationSound()
  showNotification(title, body)
}

// ── 内部工具 ──────────────────────────────────────────────────

function _compare(actual: number, op: ClientRule['op'], threshold: number): boolean {
  switch (op) {
    case '>':  return actual > threshold
    case '<':  return actual < threshold
    case '>=': return actual >= threshold
    case '<=': return actual <= threshold
  }
}

function _genId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}
