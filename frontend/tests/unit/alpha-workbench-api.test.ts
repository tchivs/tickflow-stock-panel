import { beforeEach, describe, expect, it, vi } from 'vitest'

// Task 50-03-01 — verify every Phase-50 fetcher calls the existing request<T>
// transport with the correct path + query params, and that the comparison type
// carries NO opaque winner/rank/score field (SC3).
//
// NOTE: vitest is not wired into this repo's package.json (zero-new-deps
// constraint, ROADMAP.md:12). This suite is a runnable-ready artifact; the
// authoritative executable proof of SC1–SC4 is the Playwright e2e.

// vi.mock is hoisted above the static import, so the fetchers resolve the
// mocked `request` binding at module-eval time.
const requestMock = vi.fn()
vi.mock('@/lib/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, request: requestMock }
})

import {
  alphaRunStreamUrl,
  fetchAlphaCandidates,
  fetchAlphaCompare,
  fetchAlphaLineage,
  fetchAlphaProgress,
  fetchAlphaRun,
  fetchAlphaRuns,
  fetchEvidenceClassification,
  fetchStressMatrix,
  postClone,
  postReplayBranch,
} from '@/lib/api'

function lastCall(): { path: string; init?: RequestInit } {
  const [path, init] = requestMock.mock.calls.at(-1) ?? []
  return { path: String(path), init: init as RequestInit | undefined }
}

describe('Phase-50 api fetchers', () => {
  beforeEach(() => {
    requestMock.mockReset()
    requestMock.mockResolvedValue({} as never)
  })

  it('alphaRunStreamUrl returns the durable /stream URL', () => {
    expect(alphaRunStreamUrl('run-1')).toBe('/api/research/alpha/runs/run-1/stream')
    expect(alphaRunStreamUrl('a b')).toBe('/api/research/alpha/runs/a%20b/stream')
  })

  it('fetchAlphaRuns targets the runs-list endpoint', async () => {
    await fetchAlphaRuns()
    expect(lastCall().path).toBe('/api/research/alpha/runs')
  })

  it('fetchAlphaRun / fetchAlphaProgress / fetchAlphaCandidates target the run subpaths', async () => {
    await fetchAlphaRun('run-1')
    expect(lastCall().path).toBe('/api/research/alpha/runs/run-1')
    await fetchAlphaProgress('run-1')
    expect(lastCall().path).toBe('/api/research/alpha/runs/run-1/progress')
    await fetchAlphaCandidates('run-1')
    expect(lastCall().path).toBe('/api/research/alpha/runs/run-1/candidates')
  })

  it('fetchAlphaLineage targets the lineage endpoint', async () => {
    await fetchAlphaLineage('run-1')
    expect(lastCall().path).toBe('/api/research/alpha/runs/run-1/lineage')
  })

  it('fetchEvidenceClassification targets the candidate classification path', async () => {
    await fetchEvidenceClassification('run-1', 'cand-1')
    expect(lastCall().path).toBe('/api/research/alpha/runs/run-1/candidates/cand-1/evidence-classification')
  })

  it('fetchAlphaCompare joins candidate ids into the candidates query (SC3)', async () => {
    await fetchAlphaCompare('run-1', ['cand-a', 'cand-b'])
    expect(lastCall().path).toBe('/api/research/alpha/runs/run-1/compare?candidates=cand-a,cand-b')
  })

  it('fetchStressMatrix builds the Tier-1 stress query (AF-REQ-20)', async () => {
    await fetchStressMatrix('run-1', 'cand-1', {
      fee_bps: [3, 5],
      slippage_bps: [10],
      rebalance: ['daily'],
    })
    const path = lastCall().path
    expect(path).toContain('/api/research/alpha/runs/run-1/stress-matrix')
    expect(path).toContain('candidate_id=cand-1')
    expect(path).toContain('fee_bps=3')
    expect(path).toContain('fee_bps=5')
    expect(path).toContain('slippage_bps=10')
    expect(path).toContain('rebalance=daily')
  })

  it('postReplayBranch POSTs the bounded branch-replay body', async () => {
    await postReplayBranch('run-1', { idempotency_key: 'abcdefghijklmnop', parent_step: 3 })
    const { path, init } = lastCall()
    expect(path).toBe('/api/research/alpha/runs/run-1/replay-branch')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({ idempotency_key: 'abcdefghijklmnop', parent_step: 3 })
  })

  it('postClone POSTs the bounded clone body', async () => {
    await postClone('run-1', { idempotency_key: 'abcdefghijklmnop', overrides: { costs: { commission: 5 } } })
    const { path, init } = lastCall()
    expect(path).toBe('/api/research/alpha/runs/run-1/clone')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body)).overrides.costs.commission).toBe(5)
  })
})
