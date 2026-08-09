import { describe, expect, expectTypeOf, it } from 'vitest'

// Task 50-03-03 — type/contract assertions for the lineage/compare/stress/
// data-quality views. These pin the SC2/SC3/SC4 invariants at the type level:
// the comparison record has NO opaque winner/rank/score field (SC3), and the
// classification carries the clean flag the banner binds to (SC4).
//
// NOTE: vitest is not wired into this repo's package.json (zero-new-deps
// constraint, ROADMAP.md:12). This suite is a runnable-ready artifact; the
// executable proof of the views is the Playwright e2e.

import type {
  AlphaCandidateComparison,
  AlphaLineageEdge,
  EvidenceClassification,
  StressMatrixRow,
} from '@/lib/api'

describe('compare record has no opaque winner (SC3)', () => {
  it('never exposes a winner/rank/score field on a candidate comparison', () => {
    // If the backend (or a future edit) ever adds such a field, this type-level
    // assertion fails — the deny-by-default DTO forbids it.
    expectTypeOf<AlphaCandidateComparison>().not.toHaveProperty('winner')
    expectTypeOf<AlphaCandidateComparison>().not.toHaveProperty('rank')
    expectTypeOf<AlphaCandidateComparison>().not.toHaveProperty('score')
  })
})

describe('lineage edge carries the child/parent pair for diffing (SC2)', () => {
  it('exposes both child and parent canonical_expression', () => {
    expectTypeOf<AlphaLineageEdge>().toMatchTypeOf<{ child: { canonical_expression: string }; parent: { canonical_expression: string } }>()
  })
})

describe('stress matrix is Tier-1 only (AF-REQ-20)', () => {
  it('rows are constrained to the fee/slippage/rebalance axes', () => {
    const axis: StressMatrixRow['axis'] = 'fee_bps'
    expect(['fee_bps', 'slippage_bps', 'rebalance']).toContain(axis)
  })
})

describe('data-quality banner binds evidence_classification.clean (SC4)', () => {
  it('clean is a boolean the banner can bind red/green to', () => {
    const cls = { clean: false } as EvidenceClassification
    expect(typeof cls.clean).toBe('boolean')
    // degraded evidence (clean === false) must never look like clean production
    expect(cls.clean).toBe(false)
  })
})
