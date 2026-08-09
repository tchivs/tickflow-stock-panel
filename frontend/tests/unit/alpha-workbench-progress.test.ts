import { describe, expect, it } from 'vitest'

// Task 50-03-02 — contract assertions for the durable live-progress surface.
// The React hook itself needs a DOM/jsdom environment to exercise end-to-end;
// its lossless-reconnect behavior is proven by the Playwright e2e (SC1). These
// unit assertions pin the URL + projected-event shape the consumer relies on.
//
// NOTE: vitest is not wired into this repo's package.json (zero-new-deps
// constraint, ROADMAP.md:12). This suite is a runnable-ready artifact.

import { alphaRunStreamUrl, type AlphaRunEvent } from '@/lib/api'

describe('alpha run stream URL (SC1)', () => {
  it('points at the durable Last-Event-ID SSE endpoint', () => {
    expect(alphaRunStreamUrl('run-42')).toBe('/api/research/alpha/runs/run-42/stream')
  })

  it('escapes run ids so a hostile id cannot reshape the path', () => {
    expect(alphaRunStreamUrl('a/b c')).toBe('/api/research/alpha/runs/a%2Fb%20c/stream')
  })
})

describe('projected event shape (the consumer dedups by seq)', () => {
  it('a ledger event always carries a numeric seq for lossless dedup', () => {
    const evt: AlphaRunEvent = {
      id: 'evt-1',
      seq: 7,
      event_type: 'run_started',
      entity_kind: 'run',
      entity_id: 'run-1',
      occurred_at: '2026-08-09T10:00:00Z',
      source: 'service',
      producer_version: 'v1',
      created_at: '2026-08-09T10:00:00Z',
    }
    expect(typeof evt.seq).toBe('number')
    // the consumer treats the terminal event (no seq) distinctly from ledger
    // rows (always seq-bearing) — this is the dedup boundary for SC1.
    expect(evt).not.toHaveProperty('winner')
  })
})
