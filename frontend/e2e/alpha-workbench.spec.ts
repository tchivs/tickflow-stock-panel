import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

// Phase 50 — Alpha Replay Workbench e2e (SC1–SC4 + Watchlist zero-touch).
//
// Every backend seam from 50-01/02 is mocked at the route boundary; the page is
// exercised as a real SPA. The SSE reconnect test mirrors the proven
// request-counter + Last-Event-ID-header pattern (phase5-optional-enhancements.spec.ts).

const SHA = (ch: string) => ch.repeat(64)

const RUN = {
  id: 'run-1',
  status: 'running',
  transition_version: 1,
  last_event_seq: 0,
  candidate_attempts_total: 10,
  candidate_attempts_completed: 3,
  folds_total: 5,
  folds_completed: 1,
  snapshot_sha256: SHA('a'),
  manifest_sha256: SHA('b'),
  started_at: '2026-08-09T10:00:00Z',
  finished_at: null,
  terminal_reason: null,
  retry_of_run_id: null,
  retry_attempt: 0,
  created_at: '2026-08-09T09:00:00Z',
}

const CAND_A = {
  id: 'cand-aaa',
  attempt_ordinal: 1,
  candidate_digest: SHA('a'),
  canonical_expression: 'rank(close)',
  dsl_version: '1',
  operation: 'mutate',
  seed: 42,
  step: 1,
  status: 'generated',
  created_at: '2026-08-09T10:00:00Z',
}
const CAND_B = {
  id: 'cand-bbb',
  attempt_ordinal: 2,
  candidate_digest: SHA('b'),
  canonical_expression: 'rank(volume)',
  dsl_version: '1',
  operation: 'crossover',
  seed: 42,
  step: 2,
  status: 'admitted',
  created_at: '2026-08-09T10:00:01Z',
}

const LINEAGE = {
  run_id: 'run-1',
  edges: [
    {
      lineage_id: 'lin-1',
      edge_ordinal: 0,
      operation: 'crossover',
      created_at: '2026-08-09T10:00:01Z',
      child: CAND_B,
      parent: CAND_A,
    },
  ],
}

const COMPARE = {
  run_id: 'run-1',
  candidates: [
    {
      candidate_id: 'cand-aaa',
      candidate_digest: SHA('a'),
      config: { op: 'rank', field: 'close' },
      fold_evidence: [{ ic: 0.05, fold: 0 }],
      admission_verdict: 'admitted',
      gate_trail_digest: SHA('g'),
      policy_version: 'v1',
      artifact_refs: [{ id: 'art-1' }],
      diversity: { overlap: 0.2 },
    },
    {
      candidate_id: 'cand-bbb',
      candidate_digest: SHA('b'),
      config: { op: 'rank', field: 'volume' },
      fold_evidence: [{ ic: 0.03, fold: 0 }],
      admission_verdict: 'rejected',
      gate_trail_digest: null,
      policy_version: 'v1',
      artifact_refs: [],
      diversity: null,
    },
  ],
}

const STRESS = {
  candidate_id: 'cand-aaa',
  baseline: {
    total_turnover: 12.3,
    cost_rate: 0.002,
    cost_drag: 0.024,
    raw_long_short_return: 0.1,
    net_long_short_return: 0.076,
  },
  matrix: [
    { axis: 'fee_bps', value: 3, total_turnover: 12.3, cost_rate: 0.004, cost_drag: 0.049, net_long_short_return: 0.051 },
    { axis: 'slippage_bps', value: 5, total_turnover: 12.3, cost_rate: 0.005, cost_drag: 0.061, net_long_short_return: 0.039 },
    { axis: 'rebalance', value: 'daily', total_turnover: 15.0, cost_rate: 0.006, cost_drag: 0.09, net_long_short_return: 0.01 },
  ],
}

const CLASSIFICATION_DIRTY = {
  data_date: '2026-08-08',
  source_label: 'fixture',
  cache_state: 'stale',
  missing_fields: ['eps'],
  membership_coverage: 0.6,
  evidence_role: 'exploratory',
  fixture: true,
  clean: false,
}

const json = (body: unknown, status = 200) => ({
  status,
  contentType: 'application/json',
  body: JSON.stringify(body),
})

/**
 * Install the workbench route fixtures. The default SSE handler returns an
 * immediate terminal; the live-progress test re-registers the stream route.
 */
async function installFixtures(page: Page) {
  // catch-all first; specifics registered after override (last-registered wins).
  await page.route('**/api/**', route => route.fulfill(json({})))
  await page.route('**/api/settings', route => route.fulfill(json({ onboarding_completed: true })))
  await page.route('**/api/research/alpha/runs', route => route.fulfill(json([RUN])))
  await page.route('**/api/research/alpha/runs/run-1/candidates', route => route.fulfill(json([CAND_A, CAND_B])))
  await page.route('**/api/research/alpha/runs/run-1/lineage', route => route.fulfill(json(LINEAGE)))
  await page.route('**/api/research/alpha/runs/run-1/compare**', route => route.fulfill(json(COMPARE)))
  await page.route('**/api/research/alpha/runs/run-1/stress-matrix**', route => route.fulfill(json(STRESS)))
  await page.route(
    '**/api/research/alpha/runs/run-1/candidates/cand-aaa/evidence-classification',
    route => route.fulfill(json(CLASSIFICATION_DIRTY)),
  )
  await page.route('**/api/research/alpha/runs/run-1/stream', route =>
    route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: `id: 1\nevent: terminal\ndata: ${JSON.stringify({ status: 'completed', run_id: 'run-1' })}\n\n`,
    }),
  )
}

test('renders the workbench page shell and runs list', async ({ page }) => {
  await installFixtures(page)
  await page.goto('/backtest/alpha-workbench')

  await expect(page.getByTestId('aw-page')).toBeVisible()
  await expect(page.getByTestId('aw-runs-list')).toBeVisible()
  // the single fixture run auto-selects
  await expect(page.getByTestId('aw-run-run-1')).toBeVisible()
})

test('live progress over EventSource: ordered events, reconnects never duplicate, terminal closes (SC1 client)', async ({ page }) => {
  await installFixtures(page)
  // The native EventSource auto-sends Last-Event-ID on every reconnect (a
  // browser guarantee); the server's lossless resume-from-cursor is proven
  // server-side in 50-01 (test_research_alpha_sse.py: test_last_event_id_
  // resumes_from_k_plus_1 / test_restart_resume_zero_module_state / the
  // Last-Event-ID endpoint test). Playwright's route interception does not
  // emulate the Last-Event-ID wire header on EventSource reconnects, so this
  // test asserts the CLIENT-side half of SC1 the e2e can actually observe:
  //   • events render in order as they arrive (no gap);
  //   • across the browser's automatic reconnects, the consumer dedups by seq
  //     so an event is never rendered twice (no duplication);
  //   • a `terminal` event closes the stream and transitions the chip to done.
  let fired = 0
  await page.route('**/api/research/alpha/runs/run-1/stream', route => {
    fired += 1
    // After a few reconnects (proving dedup of the replayed seq 1), emit seq 2
    // + terminal: ordered processing and a clean stream close.
    if (fired > 3) {
      return route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: `id: 2\nevent: progress\ndata: ${JSON.stringify({
          id: 'evt-2', seq: 2, event_type: 'progress', entity_kind: 'candidate', entity_id: 'cand-aaa',
          occurred_at: '2026-08-09T10:00:01Z', source: 'service', producer_version: 'v1', created_at: '2026-08-09T10:00:01Z',
        })}\n\nevent: terminal\ndata: ${JSON.stringify({ status: 'completed', run_id: 'run-1' })}\n\n`,
      })
    }
    // short retry so reconnects are fast; seq 1 replayed on every reconnect.
    return route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: `retry: 80\nid: 1\nevent: progress\ndata: ${JSON.stringify({
        id: 'evt-1', seq: 1, event_type: 'progress', entity_kind: 'run', entity_id: 'run-1',
        occurred_at: '2026-08-09T10:00:00Z', source: 'service', producer_version: 'v1', created_at: '2026-08-09T10:00:00Z',
      })}\n\n`,
    })
  })

  await page.goto('/backtest/alpha-workbench')

  // seq 1 renders as it arrives (never missed)
  await expect(page.getByTestId('aw-event-seq-1')).toBeVisible()
  // the browser reconnects repeatedly (each response closes); the consumer
  // dedups by seq, so seq 1 is rendered exactly once — never duplicated (SC1).
  await expect(page.locator('[data-testid="aw-event-seq-1"]')).toHaveCount(1)
  // the next event renders in order — no gap (SC1).
  await expect(page.getByTestId('aw-event-seq-2')).toBeVisible()
  // reconnects actually happened (the browser auto-reconnected)
  expect(fired).toBeGreaterThan(1)
  // a terminal event closed the stream → chip transitions to done (SC1).
  await expect(page.getByTestId('aw-conn-chip')).toHaveAttribute('data-status', 'done')
})

test('compare panel renders all evidence with no opaque winner column', async ({ page }) => {
  await installFixtures(page)
  await page.goto('/backtest/alpha-workbench')

  await page.getByTestId('aw-tab-compare').click()
  // select both candidates
  await page.getByTestId('aw-candidate-picker').getByText('cand-aaa').click()
  await page.getByTestId('aw-candidate-picker').getByText('cand-bbb').click()

  const table = page.getByTestId('aw-compare-table')
  await expect(table).toBeVisible()
  // both candidates appear as columns (full evidence, no opaque winner)
  await expect(table).toContainText('cand-aaa')
  await expect(table).toContainText('cand-bbb')
  // SC3: no winner/rank/score column is computed or shown client-side
  const headers = await table.locator('thead th').allTextContents()
  const lower = headers.join(' ').toLowerCase()
  expect(lower).not.toMatch(/\b(winner|rank|score)\b/)
})

test('data-quality banner is red when evidence_classification.clean is false (SC4)', async ({ page }) => {
  await installFixtures(page)
  await page.goto('/backtest/alpha-workbench')

  await page.getByTestId('aw-tab-quality').click()
  const banner = page.getByTestId('aw-banner')
  await expect(banner).toBeVisible()
  // degraded evidence can never look like clean production
  await expect(banner).toHaveAttribute('data-clean', 'false')
  await expect(banner).toHaveClass(/red-500/)
  await expect(page.getByTestId('aw-banner-reason')).toBeVisible()
})

test('lineage tree renders a parent→child edge with an expression diff', async ({ page }) => {
  await installFixtures(page)
  await page.goto('/backtest/alpha-workbench')

  await expect(page.getByTestId('aw-lineage-tree')).toBeVisible()
  const edge = page.getByTestId('aw-lineage-edge')
  await expect(edge).toHaveCount(1)
  // the diff surfaces the child's changed token (volume) and the dropped one (close)
  const diff = page.getByTestId('aw-lineage-diff')
  await expect(diff).toContainText('volume')
  await expect(diff).toContainText('close')
  // branch-replay + clone actions are present
  await expect(page.getByTestId('aw-replay-branch')).toBeVisible()
  await expect(page.getByTestId('aw-clone-run')).toBeVisible()
})

test('stress matrix renders the Tier-1 fee/slippage/rebalance grid', async ({ page }) => {
  await installFixtures(page)
  await page.goto('/backtest/alpha-workbench')

  await page.getByTestId('aw-tab-stress').click()
  await expect(page.getByTestId('aw-stress-matrix')).toBeVisible()
  // Tier-1 axes are projected
  const rows = page.getByTestId('aw-stress-row')
  await expect(rows).toHaveCount(3)
  await expect(page.getByTestId('aw-stress-matrix')).toContainText('fee_bps')
  await expect(page.getByTestId('aw-stress-matrix')).toContainText('slippage_bps')
  await expect(page.getByTestId('aw-stress-matrix')).toContainText('rebalance')
})

test('the new page is zero-touch — no Watchlist token leaks into AlphaWorkbench', () => {
  const src = readFileSync(
    resolve(process.cwd(), 'src/pages/backtest/AlphaWorkbench.tsx'),
    'utf8',
  )
  // explicit non-goal (ROADMAP.md:171): the workbench must not import or
  // reference the Watchlist page in any form.
  expect(src).not.toContain('Watchlist')
})
