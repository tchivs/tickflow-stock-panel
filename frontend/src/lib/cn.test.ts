import { describe, it, expect } from 'vitest'
import { cn } from './cn'

describe('cn', () => {
  it('merges class names', () => {
    expect(cn('foo', 'bar')).toBe('foo bar')
  })
  it('handles conditional classes', () => {
    expect(cn('base', false && 'hidden', 'visible')).toBe('base visible')
  })
  it('deduplicates tailwind conflicting classes (twMerge)', () => {
    expect(cn('px-2', 'px-4')).toBe('px-4')
  })
  it('preserves non-conflicting classes', () => {
    expect(cn('text-red-500', 'font-bold')).toBe('text-red-500 font-bold')
  })
  it('handles empty inputs', () => {
    expect(cn()).toBe('')
  })
  it('handles undefined and null', () => {
    expect(cn('foo', undefined, null, 'bar')).toBe('foo bar')
  })
  it('handles arrays', () => {
    expect(cn(['foo', 'bar'])).toBe('foo bar')
  })
  it('handles nested arrays with conditionals', () => {
    expect(cn(['foo', ['bar', false && 'baz']])).toBe('foo bar')
  })
})
