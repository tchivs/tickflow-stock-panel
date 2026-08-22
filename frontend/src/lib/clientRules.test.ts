import { describe, it, expect, beforeEach } from 'vitest'
import {
  evaluateRules,
  markTriggered,
  isDebounced,
  clearTriggered,
  DEBOUNCE_MS,
  type ClientRule,
} from './clientRules'
import type { Quote } from './api'

// ── 工具: 构造规则 ────────────────────────────────────────────

function makeRule(over: Partial<ClientRule> = {}): ClientRule {
  return {
    id: 'r1',
    name: 'test',
    symbol: '600519.SH',
    type: 'pct',
    op: '>',
    value: 0.03,
    enabled: true,
    createdAt: '2026-01-01T00:00:00Z',
    ...over,
  }
}

function makeQuote(over: Partial<Quote> = {}): Quote {
  return { symbol: '600519.SH', ...over }
}

// ── 评估引擎基本用例 ──────────────────────────────────────────

describe('evaluateRules — basic', () => {
  it('pct 类型: change_pct > value → 命中', () => {
    const rule = makeRule({ type: 'pct', op: '>', value: 0.03 })
    const quote = makeQuote({ change_pct: 0.05 })
    const hits = evaluateRules([quote], [rule])
    expect(hits).toHaveLength(1)
    expect(hits[0].rule.id).toBe('r1')
    expect(hits[0].matchedValue).toBe(0.05)
  })

  it('pct 类型负值: change_pct < value → 命中', () => {
    const rule = makeRule({ type: 'pct', op: '<', value: -0.02 })
    const quote = makeQuote({ change_pct: -0.05 })
    const hits = evaluateRules([quote], [rule])
    expect(hits).toHaveLength(1)
  })

  it('price 类型: price >= value → 命中 (边界)', () => {
    const rule = makeRule({ type: 'price', op: '>=', value: 100 })
    const quote = makeQuote({ price: 100 })
    const hits = evaluateRules([quote], [rule])
    expect(hits).toHaveLength(1)
  })

  it('不匹配 symbol → 不命中', () => {
    const rule = makeRule({ symbol: '000001.SZ' })
    const quote = makeQuote({ symbol: '600519.SH', change_pct: 0.05 })
    const hits = evaluateRules([quote], [rule])
    expect(hits).toHaveLength(0)
  })

  it('disabled 规则 → 不评估', () => {
    const rule = makeRule({ enabled: false })
    const quote = makeQuote({ change_pct: 0.05 })
    const hits = evaluateRules([quote], [rule])
    expect(hits).toHaveLength(0)
  })
})

// ── 防抖 ──────────────────────────────────────────────────────

describe('debounce', () => {
  beforeEach(() => {
    clearTriggered('r1')
  })

  it('markTriggered 后 5 分钟内 isDebounced = true', () => {
    const now = 1_000_000
    markTriggered('r1', now)
    expect(isDebounced('r1', now + 10_000)).toBe(true)
  })

  it('超过 DEBOUNCE_MS 后 isDebounced = false', () => {
    const now = 1_000_000
    markTriggered('r1', now)
    expect(isDebounced('r1', now + DEBOUNCE_MS + 1)).toBe(false)
  })
})
