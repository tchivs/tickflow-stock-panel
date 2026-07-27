import { expect, test } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'

const baseline = {
  symbol: '600519.SH',
  entry_low: 100,
  entry_high: 102,
  stop: 95,
  target1: 110,
  target2: 118,
  position_pct: 0.2,
  action: '等待确认',
  score: 8,
  risk_reward: 2.4,
  reason_snapshot: { market: '确定性输入' },
}

const overview = {
  as_of: '2026-07-25',
  quote_status: { running: false, mode: 'none', quote_age_ms: null },
  indices: [],
  breadth: {
    total: 0, up: 0, down: 0, flat: 0, up_pct: 0, down_pct: 0,
    avg_pct: 0, median_pct: 0, strong_up: 0, strong_down: 0,
  },
  amount: { total: 0, avg: 0 },
  boards: [],
  limit: {
    limit_up: 0, broken: 0, failed: 0, limit_down: 0, max_boards: 0,
    seal_rate: 0, tiers: [], sealed_ready: false, fake_up: 0, fake_down: 0,
  },
  distribution: [],
  trend: {
    above_ma5: 0, above_ma20: 0, above_ma60: 0,
    above_ma5_pct: 0, above_ma20_pct: 0, above_ma60_pct: 0,
    new_high: 0, new_low: 0,
  },
  activity: { avg_turnover: 0, high_turnover: 0, high_vol_ratio: 0, vol_ratio: 0 },
  radar: [],
  emotion: { score: 50, label: '中性' },
  top_gainers: [],
  top_losers: [],
  turnover_leaders: [],
  active_leaders: [],
  concept_rank: { leading: [], lagging: [] },
  industry_rank: { leading: [], lagging: [] },
}

const json = (route: import('@playwright/test').Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

async function installDashboardShell(page: import('@playwright/test').Page) {
  await page.route('**/api/**', route => json(route, {}))
  await page.route('**/api/overview/market**', route => json(route, overview))
  await page.route('**/api/data/status', route => json(route, {
    daily: { trading_days: 1 },
    enriched: { trading_days: 1, latest_date: '2026-07-25' },
    storage: {},
  }))
  await page.route('**/api/settings', route => json(route, {
    onboarding_completed: true,
    mode: 'none',
  }))
  await page.route('**/api/capabilities', route => json(route, {
    label: 'Free',
    capabilities: {},
  }))
  await page.route('**/api/alerts**', route => json(route, { alerts: [], total: 0 }))
}

test('decision flow keeps AI advisory until explicit bounded apply, then compares and replays', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-chromium only')
  const mutations: Array<{ path: string; body: unknown }> = []
  let run = {
    id: 'decision-run-server-1',
    symbol: '600519.SH',
    data_as_of: '2026-07-25',
    engine_config_version: 'playbook-v1',
    created_at: '2026-07-25T10:00:00Z',
    baseline,
    final: { ...baseline },
    proposal: null as null | {
      provider: string
      model: string
      adjustments: Array<{ field: string; value: string; rationale: string }>
    },
    adjustments: [] as Array<Record<string, unknown>>,
  }

  await installDashboardShell(page)
  await page.route('**/api/decision/**', route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (request.method() !== 'GET') {
      mutations.push({
        path,
        body: request.postData() ? request.postDataJSON() : null,
      })
    }
    if (path === '/api/decision/runs' && request.method() === 'POST') {
      return json(route, run, 201)
    }
    if (path === `/api/decision/runs/${run.id}` && request.method() === 'GET') {
      return json(route, run)
    }
    if (path === `/api/decision/runs/${run.id}/review`) {
      run = {
        ...run,
        proposal: {
          provider: 'openai_compat',
          model: 'review-model',
          adjustments: [
            {
              field: 'entry_low',
              value: '101.0000',
              rationale: '等待价格确认',
            },
            {
              field: 'entry_high',
              value: '110.0000',
              rationale: '上限提案必须受约束',
            },
          ],
        },
      }
      return json(route, { review_status: 'available', final: run.final })
    }
    if (path === `/api/decision/runs/${run.id}/adjustments`) {
      run = {
        ...run,
        final: { ...run.final, entry_low: 101, entry_high: 103 },
        adjustments: [
          {
            field: 'entry_low',
            proposed_value: '101.0000',
            final_value: '101.0000',
            disposition: 'applied',
            rationale: '等待价格确认',
          },
          {
            field: 'entry_high',
            proposed_value: '110.0000',
            final_value: '103.0000',
            disposition: 'clamped',
            rationale: '上限提案必须受约束',
          },
        ],
      }
      return json(route, run)
    }
    if (path === '/api/decision/replay') {
      return json(route, {
        id: 'replay-server-1',
        as_of: '2026-07-25',
        engine_config_version: 'playbook-v1',
        result_hash: 'sha256:replay-result',
        snapshot: { symbols: ['600519.SH'] },
        provider: null,
        model: null,
        created_at: '2026-07-25T12:00:00Z',
      }, 201)
    }
    return json(route, { detail: `Unhandled decision fixture route: ${path}` }, 500)
  })

  await page.goto('/')
  await page.getByRole('button', { name: '查看决策计划' }).click()
  const dialog = page.getByRole('dialog', { name: '决策计划' })
  const generate = dialog.getByRole('form', { name: '生成决策计划' })
  await generate.getByLabel('标的代码').fill('600519.SH')
  await generate.getByLabel('数据截至').fill('2026-07-25')
  await generate.getByRole('button', { name: '生成确定性计划' }).click()

  await expect(dialog.getByText('decision-run-server-1')).toBeVisible()
  expect(mutations[0]).toEqual({
    path: '/api/decision/runs',
    body: { symbol: '600519.SH', as_of: '2026-07-25' },
  })

  await dialog.getByRole('button', { name: '请求 AI 审阅' }).click()
  const proposal = dialog.getByLabel('尚未应用的 AI 调整提案')
  await expect(proposal).toContainText('entry_low')
  await expect(proposal).toContainText('101.0000')
  await expect(proposal).toContainText('entry_high')
  await expect(proposal).toContainText('110.0000')
  await expect(dialog.getByText('100.00 – 102.00').first()).toBeVisible()
  expect(mutations.filter(item => item.path.endsWith('/adjustments'))).toHaveLength(0)

  await proposal.getByRole('button', { name: '应用受限调整' }).click()
  await expect(dialog.getByText('用户已提交提案，服务端受限校验结果见下方审计。')).toBeVisible()
  await expect(dialog.getByText('101.00 – 103.00')).toBeVisible()
  await expect(dialog.getByLabel('调整审计 entry_low')).toContainText('已应用')
  await expect(dialog.getByLabel('调整审计 entry_low')).toContainText('等待价格确认 · 提议 101.0000 · 最终 101.0000')
  await expect(dialog.getByLabel('调整审计 entry_high')).toContainText('已钳制')
  await expect(dialog.getByLabel('调整审计 entry_high')).toContainText('上限提案必须受约束 · 提议 110.0000 · 最终 103.0000')
  expect(mutations.find(item => item.path.endsWith('/adjustments'))).toEqual({
    path: `/api/decision/runs/${run.id}/adjustments`,
    body: {
      proposal: {
        entry_low: { value: '101.0000', rationale: '等待价格确认' },
        entry_high: { value: '110.0000', rationale: '上限提案必须受约束' },
      },
    },
  })

  await dialog.getByRole('button', { name: '运行历史回放' }).click()
  await expect(dialog.getByText('已完成 AI 禁用的历史回放')).toBeVisible()
  expect(mutations.find(item => item.path === '/api/decision/replay')).toEqual({
    path: '/api/decision/replay',
    body: { run_ids: ['decision-run-server-1'], as_of: '2026-07-25' },
  })
})

test('late review and replay settlements from the prior run never render into the selected run', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-chromium only')
  await installDashboardShell(page)
  const runs = {
    'decision-run-a': {
      id: 'decision-run-a',
      symbol: '600519.SH',
      data_as_of: '2026-07-25',
      engine_config_version: 'playbook-v1',
      created_at: '2026-07-25T10:00:00Z',
      baseline,
      final: { ...baseline },
      proposal: null,
      adjustments: [],
    },
    'decision-run-b': {
      id: 'decision-run-b',
      symbol: '000001.SZ',
      data_as_of: '2026-07-24',
      engine_config_version: 'playbook-v1',
      created_at: '2026-07-24T10:00:00Z',
      baseline: { ...baseline, symbol: '000001.SZ' },
      final: { ...baseline, symbol: '000001.SZ' },
      proposal: null,
      adjustments: [],
    },
  }
  let releaseReview!: () => void
  let releaseReplay!: () => void
  let markReviewStarted!: () => void
  let markReplayStarted!: () => void
  const reviewGate = new Promise<void>(resolve => { releaseReview = resolve })
  const replayGate = new Promise<void>(resolve => { releaseReplay = resolve })
  const reviewStarted = new Promise<void>(resolve => { markReviewStarted = resolve })
  const replayStarted = new Promise<void>(resolve => { markReplayStarted = resolve })

  await page.route('**/api/decision/**', async route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === '/api/decision/runs/decision-run-a' && request.method() === 'GET') {
      return json(route, runs['decision-run-a'])
    }
    if (path === '/api/decision/runs/decision-run-b' && request.method() === 'GET') {
      return json(route, runs['decision-run-b'])
    }
    if (path === '/api/decision/runs/decision-run-a/review') {
      markReviewStarted()
      await reviewGate
      return json(route, { review_status: 'unavailable', final: runs['decision-run-a'].final })
    }
    if (path === '/api/decision/replay') {
      markReplayStarted()
      await replayGate
      return json(route, {
        id: 'stale-replay-a',
        as_of: '2026-07-25',
        engine_config_version: 'playbook-v1',
        result_hash: 'sha256:stale-a',
        snapshot: {},
        provider: null,
        model: null,
        created_at: '2026-07-25T12:00:00Z',
      }, 201)
    }
    return json(route, { detail: `Unhandled decision fixture route: ${path}` }, 500)
  })

  await page.goto('/')
  await page.getByRole('button', { name: '查看决策计划' }).click()
  const dialog = page.getByRole('dialog', { name: '决策计划' })
  const openRun = dialog.getByRole('form', { name: '打开已保存决策计划' })
  await openRun.getByLabel('已保存计划 ID').fill('decision-run-a')
  await openRun.getByRole('button', { name: '查看' }).click()
  await expect(dialog.getByText('decision-run-a')).toBeVisible()

  await dialog.getByRole('button', { name: '请求 AI 审阅' }).click()
  await reviewStarted
  await dialog.getByRole('button', { name: '运行历史回放' }).click()
  await replayStarted

  await openRun.getByLabel('已保存计划 ID').fill('decision-run-b')
  await openRun.getByRole('button', { name: '查看' }).click()
  await expect(dialog.getByText('decision-run-b')).toBeVisible()
  await expect(dialog.getByRole('button', { name: '请求 AI 审阅' })).toBeEnabled()
  await expect(dialog.getByLabel('历史回放数据截至')).toHaveValue('2026-07-24')

  const staleReviewResponse = page.waitForResponse(response =>
    new URL(response.url()).pathname === '/api/decision/runs/decision-run-a/review')
  const staleReplayResponse = page.waitForResponse(response =>
    new URL(response.url()).pathname === '/api/decision/replay')
  releaseReview()
  releaseReplay()
  await Promise.all([staleReviewResponse, staleReplayResponse])

  await expect(dialog.getByText('AI 审阅当前不可用，确定性计划保持不变。')).toHaveCount(0)
  await expect(dialog.getByText('已完成 AI 禁用的历史回放')).toHaveCount(0)
  await expect(dialog.getByText('decision-run-b')).toBeVisible()
})

test('failed replay keeps its cutoff and retries with the same run-scoped variables', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-chromium only')
  await installDashboardShell(page)
  const run = {
    id: 'decision-run-retry',
    symbol: '600519.SH',
    data_as_of: '2026-07-25',
    engine_config_version: 'playbook-v1',
    created_at: '2026-07-25T10:00:00Z',
    baseline,
    final: { ...baseline },
    proposal: null,
    adjustments: [],
  }
  const replayBodies: unknown[] = []
  let replayAttempts = 0

  await page.route('**/api/decision/**', route => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    if (path === `/api/decision/runs/${run.id}` && request.method() === 'GET') {
      return json(route, run)
    }
    if (path === '/api/decision/replay') {
      replayAttempts += 1
      replayBodies.push(request.postDataJSON())
      if (replayAttempts === 1) {
        return json(route, { detail: 'historical data unavailable' }, 503)
      }
      return json(route, {
        id: 'replay-after-retry',
        as_of: '2026-07-20',
        engine_config_version: 'playbook-v1',
        result_hash: 'sha256:retry-success',
        snapshot: {},
        provider: null,
        model: null,
        created_at: '2026-07-25T12:00:00Z',
      }, 201)
    }
    return json(route, { detail: `Unhandled decision fixture route: ${path}` }, 500)
  })

  await page.goto('/')
  await page.getByRole('button', { name: '查看决策计划' }).click()
  const dialog = page.getByRole('dialog', { name: '决策计划' })
  const openRun = dialog.getByRole('form', { name: '打开已保存决策计划' })
  await openRun.getByLabel('已保存计划 ID').fill(run.id)
  await openRun.getByRole('button', { name: '查看' }).click()
  const cutoff = dialog.getByLabel('历史回放数据截至')
  await cutoff.fill('2026-07-20')
  await dialog.getByRole('button', { name: '运行历史回放' }).click()

  const alert = dialog.getByRole('alert')
  await expect(alert).toContainText('历史回放失败；数据截至仍保留为 2026-07-20。')
  await expect(cutoff).toHaveValue('2026-07-20')
  await alert.getByRole('button', { name: '重试历史回放' }).click()
  await expect(dialog.getByText('已完成 AI 禁用的历史回放')).toBeVisible()
  expect(replayBodies).toEqual([
    { run_ids: [run.id], as_of: '2026-07-20' },
    { run_ids: [run.id], as_of: '2026-07-20' },
  ])
})
