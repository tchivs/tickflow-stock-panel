import {
  evaluateRules,
  markTriggered,
  isDebounced,
  clearTriggered,
  getNotificationPermission,
  showNotification,
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

// ── 评估引擎边界用例 (Task 3 TDD) ─────────────────────────────

describe('evaluateRules — edge cases', () => {
  it('pct 边界: change_pct <= value → 命中 (相等)', () => {
    const rule = makeRule({ type: 'pct', op: '<=', value: 0.05 })
    const quote = makeQuote({ change_pct: 0.05 })
    const hits = evaluateRules([quote], [rule])
    expect(hits).toHaveLength(1)
  })

  it('price 边界: price > value → 不命中 (严格大于)', () => {
    const rule = makeRule({ type: 'price', op: '>', value: 50 })
    const quote = makeQuote({ price: 50 })
    const hits = evaluateRules([quote], [rule])
    expect(hits).toHaveLength(0)
  })

  it('quote 缺 price/close 字段 → 不命中', () => {
    const rule = makeRule({ type: 'price', op: '>', value: 100 })
    const quote = makeQuote({ symbol: '600519.SH' })
    const hits = evaluateRules([quote], [rule])
    expect(hits).toHaveLength(0)
  })

  it('pct 优先取 pct 字段 (pct > change_pct)', () => {
    const rule = makeRule({ type: 'pct', op: '>', value: 0.04 })
    const quote = makeQuote({ pct: 0.05, change_pct: 0.03 })
    const hits = evaluateRules([quote], [rule])
    expect(hits).toHaveLength(1)
    expect(hits[0].matchedValue).toBe(0.05)
  })

  it('多规则同 tick 命中: 3 条 enabled 规则匹配同一 quotes → 返回 3 Hit', () => {
    const rules = [
      makeRule({ id: 'r1', name: '涨超3%', type: 'pct', op: '>', value: 0.03 }),
      makeRule({ id: 'r2', name: '价格超100', type: 'price', op: '>', value: 100 }),
      makeRule({ id: 'r3', name: '涨超1%', type: 'pct', op: '>', value: 0.01 }),
    ]
    const quote = makeQuote({ change_pct: 0.05, price: 120 })
    const hits = evaluateRules([quote], rules)
    expect(hits).toHaveLength(3)
  })
})

// ── 防抖重置 ──────────────────────────────────────────────────

describe('debounce reset', () => {
  beforeEach(() => {
    clearTriggered('r-reset')
  })

  it('markTriggered → isDebounced = true; clearTriggered → isDebounced = false', () => {
    const now = 1_000_000
    markTriggered('r-reset', now)
    expect(isDebounced('r-reset', now + 10_000)).toBe(true)
    clearTriggered('r-reset')
    expect(isDebounced('r-reset', now + 10_000)).toBe(false)
  })
})
describe('notification API', () => {
  it('getNotificationPermission returns "denied" when Notification is undefined', () => {
    const orig = globalThis.Notification
    // @ts-expect-error: simulate SSR / no Notification API
    delete globalThis.Notification
    expect(getNotificationPermission()).toBe('denied')
    globalThis.Notification = orig
  })

  it('showNotification is no-op when permission not granted', () => {
    const orig = globalThis.Notification
    const mock = { permission: 'denied' } as unknown as typeof Notification
    globalThis.Notification = mock
    expect(() => showNotification('test', 'body')).not.toThrow()
    globalThis.Notification = orig
  })

  it('showNotification catches errors silently', () => {
    const orig = globalThis.Notification
    function ThrowingNotification() { throw new Error('SW context') }
    ThrowingNotification.permission = 'granted'
    globalThis.Notification = ThrowingNotification as unknown as typeof Notification
    expect(() => showNotification('test', 'body')).not.toThrow()
    globalThis.Notification = orig
  })
})

// ── evaluateRules 空输入 ──────────────────────────────────────

describe('evaluateRules — empty inputs', () => {
  it('empty quotes → empty hits', () => {
    expect(evaluateRules([], [makeRule()])).toEqual([])
  })

  it('empty rules → empty hits', () => {
    expect(evaluateRules([makeQuote()], [])).toEqual([])
  })

  it('NaN threshold value → skip rule', () => {
    const rule = makeRule({ value: NaN })
    expect(evaluateRules([makeQuote({ pct: 0.05 })], [rule])).toEqual([])
  })

  it('Infinity threshold value → skip rule', () => {
    const rule = makeRule({ value: Infinity })
    expect(evaluateRules([makeQuote({ pct: 0.05 })], [rule])).toEqual([])
  })
})
