import { describe, it, expect } from 'vitest'
import {
  fmtPrice,
  fmtPct,
  fmtVolume,
  priceColorClass,
  fmtBigNum,
  fmtDate,
  formatNumber,
  formatDuration,
  formatExtNumber,
} from './format'

describe('fmtPrice', () => {
  it('formats positive numbers with default 2 digits', () => {
    expect(fmtPrice(12.3456)).toBe('12.35')
  })
  it('respects custom digit count', () => {
    expect(fmtPrice(12.3456, 4)).toBe('12.3456')
  })
  it('returns dash for null/undefined/NaN', () => {
    expect(fmtPrice(null)).toBe('—')
    expect(fmtPrice(undefined)).toBe('—')
    expect(fmtPrice(NaN)).toBe('—')
  })
  it('handles zero', () => {
    expect(fmtPrice(0)).toBe('0.00')
  })
})

describe('fmtPct', () => {
  it('formats positive with + sign', () => {
    expect(fmtPct(0.05)).toBe('+5.00%')
  })
  it('formats negative without extra sign', () => {
    expect(fmtPct(-0.03)).toBe('-3.00%')
  })
  it('returns dash for null/undefined/NaN', () => {
    expect(fmtPct(null)).toBe('—')
    expect(fmtPct(undefined)).toBe('—')
    expect(fmtPct(NaN)).toBe('—')
  })
  it('respects custom digits', () => {
    expect(fmtPct(0.1234, 4)).toBe('+12.3400%')
  })
  it('zero has no + sign', () => {
    expect(fmtPct(0)).toBe('0.00%')
  })
})

describe('fmtVolume', () => {
  it('formats 亿 for >= 1e8', () => {
    expect(fmtVolume(1e8)).toBe('1.00亿')
    expect(fmtVolume(2.5e8)).toBe('2.50亿')
  })
  it('formats 万 for >= 1e4 and < 1e8', () => {
    expect(fmtVolume(1e4)).toBe('1.00万')
    expect(fmtVolume(99999)).toBe('10.00万')
  })
  it('formats raw integer for < 1e4', () => {
    expect(fmtVolume(1234)).toBe('1234')
    expect(fmtVolume(0)).toBe('0')
  })
  it('returns dash for null/undefined/NaN', () => {
    expect(fmtVolume(null)).toBe('—')
    expect(fmtVolume(undefined)).toBe('—')
    expect(fmtVolume(NaN)).toBe('—')
  })
})

describe('priceColorClass', () => {
  it('returns text-bull for positive', () => {
    expect(priceColorClass(0.01)).toBe('text-bull')
  })
  it('returns text-bear for negative', () => {
    expect(priceColorClass(-0.01)).toBe('text-bear')
  })
  it('returns text-muted for zero', () => {
    expect(priceColorClass(0)).toBe('text-muted')
  })
  it('returns text-muted for null/NaN', () => {
    expect(priceColorClass(null)).toBe('text-muted')
    expect(priceColorClass(NaN)).toBe('text-muted')
  })
})

describe('fmtBigNum', () => {
  it('formats 万亿 for >= 1e12', () => {
    expect(fmtBigNum(1e12)).toBe('1.00万亿')
  })
  it('formats 亿 for >= 1e8', () => {
    expect(fmtBigNum(1e8)).toBe('1.00亿')
  })
  it('formats 万 for >= 1e4', () => {
    expect(fmtBigNum(1e4)).toBe('1万')
  })
  it('returns raw for < 1e4', () => {
    expect(fmtBigNum(9999)).toBe('9999')
  })
  it('returns dash for null/NaN', () => {
    expect(fmtBigNum(null)).toBe('—')
    expect(fmtBigNum(NaN)).toBe('—')
  })
})

describe('fmtDate', () => {
  it('formats Date object', () => {
    expect(fmtDate(new Date('2026-03-05'))).toBe('2026-03-05')
  })
  it('formats ISO string', () => {
    expect(fmtDate('2026-03-05T12:30:00')).toBe('2026-03-05')
  })
  it('returns dash for null', () => {
    expect(fmtDate(null)).toBe('—')
  })
  it('returns original string for invalid date', () => {
    expect(fmtDate('not-a-date')).toBe('not-a-date')
  })
})

describe('formatNumber', () => {
  it('formats 亿 for >= 1e8', () => {
    expect(formatNumber(1e8)).toBe('1.0亿')
  })
  it('formats 万 for >= 1e4', () => {
    expect(formatNumber(1e4)).toBe('1.0万')
  })
  it('uses locale string for < 1e4', () => {
    expect(formatNumber(1234)).toBe('1,234')
  })
})

describe('formatDuration', () => {
  it('formats seconds < 60', () => {
    expect(formatDuration(30)).toBe('30s')
  })
  it('formats minutes without remainder', () => {
    expect(formatDuration(120)).toBe('2m')
  })
  it('formats minutes with seconds remainder', () => {
    expect(formatDuration(90)).toBe('1m 30s')
  })
  it('formats hours without remainder', () => {
    expect(formatDuration(3600)).toBe('1h')
  })
  it('formats hours with minutes remainder', () => {
    expect(formatDuration(3700)).toBe('1h 1m')
  })
})

describe('formatExtNumber', () => {
  it('returns dash for non-finite', () => {
    expect(formatExtNumber(NaN)).toBe('—')
    expect(formatExtNumber(Infinity)).toBe('—')
  })
  it('converts to 万', () => {
    expect(formatExtNumber(25000, { unitConvert: 'wan' })).toBe('2.50万')
  })
  it('converts to 亿', () => {
    expect(formatExtNumber(2.5e8, { unitConvert: 'yi' })).toBe('2.50亿')
  })
  it('auto-converts large numbers to 亿', () => {
    expect(formatExtNumber(1e8, { unitConvert: 'auto' })).toBe('1.00亿')
  })
  it('auto-converts to 万 for mid-range', () => {
    expect(formatExtNumber(5e4, { unitConvert: 'auto' })).toBe('5.00万')
  })
  it('none mode keeps integer without decimals', () => {
    expect(formatExtNumber(42)).toBe('42')
  })
  it('none mode strips trailing zeros for decimals', () => {
    expect(formatExtNumber(1.23)).toBe('1.23')
  })
  it('thousandSeparator adds commas', () => {
    expect(formatExtNumber(1234567, { thousandSeparator: true })).toBe('1,234,567')
  })
  it('thousandSeparator with decimals', () => {
    expect(formatExtNumber(1234567.89, { thousandSeparator: true })).toBe('1,234,567.89')
  })
})
