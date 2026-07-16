import { createHash } from 'node:crypto'
import { spawn, type ChildProcess } from 'node:child_process'
import { chmod, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { expect, test, type Page } from '@playwright/test'

const hostUrl = 'http://127.0.0.1:3018'
const browserUrl = 'http://127.0.0.1:4173'
const password = 'phase4-host-password'
let host: ChildProcess | undefined
let capabilityBranch: 'affirmative_isolation_proved' | 'isolation_unavailable_fail_closed' | undefined
let hostOutput = ''
test.setTimeout(180_000)

function sleep(milliseconds: number) {
  const deferred = Promise.withResolvers<void>()
  setTimeout(deferred.resolve, milliseconds)
  return deferred.promise
}

function fixtureBars(symbol: string, start: string, end: string, baseline: number) {
  const bars: Array<Record<string, number | string>> = []
  const cursor = new Date(`${start}T00:00:00Z`)
  const finalDate = new Date(`${end}T00:00:00Z`)
  let businessDay = 0
  while (cursor <= finalDate) {
    const weekday = cursor.getUTCDay()
    if (weekday !== 0 && weekday !== 6) {
      const phase = businessDay % 43
      const close = baseline + (phase < 20 ? 16 - phase * 0.72 : 2 + (phase - 20) * 0.96)
      const date = cursor.toISOString().slice(0, 10)
      const volume = 3_000_000 + businessDay * 1_000
      bars.push({ symbol, date, open: close - 0.15, high: close + 0.35, low: close - 0.4, close, volume, amount: volume * close, quote_ts: cursor.getTime() + 5_400_000 })
      businessDay += 1
    }
    cursor.setUTCDate(cursor.getUTCDate() + 1)
  }
  return bars
}

async function waitForHost() {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    try {
      if ((await fetch(`${hostUrl}/health`)).ok) return
    } catch {
      // The actual FastAPI lifespan is still initializing.
    }
    await sleep(250)
  }
  throw new Error(`real FastAPI host did not become ready: ${hostOutput.slice(-4_000)}`)
}

async function sameOriginRequest(page: Page, path: string, method = 'GET', body?: object) {
  return page.evaluate(async ({ requestPath, requestMethod, requestBody }) => {
    const response = await fetch(requestPath, {
      method: requestMethod,
      headers: requestBody ? { 'Content-Type': 'application/json' } : undefined,
      body: requestBody ? JSON.stringify(requestBody) : undefined,
    })
    return { status: response.status, body: await response.json() }
  }, { requestPath: path, requestMethod: method, requestBody: body })
}

async function login(page: Page, redirect: '/stock-analysis' | '/backtest' = '/stock-analysis') {
  await page.goto(`/login?redirect=${encodeURIComponent(redirect)}`)
  await page.getByPlaceholder('访问密码').fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`${redirect}$`))
  const cookies = await page.context().cookies(browserUrl)
  expect(cookies.find(cookie => cookie.name === 'tf_session')).toMatchObject({ path: '/' })
}

async function selectFixtureStock(page: Page) {
  const search = page.getByPlaceholder('输入股票代码或名称，如 600000 / 浦发')
  await search.fill('600000')
  await search.press('Enter')
  await expect(page.getByRole('heading', { name: '归因观点与表现校准' })).toBeVisible()
}

async function startRootSse(page: Page) {
  await page.evaluate(async () => {
    const target = globalThis as typeof globalThis & { phase4Sse?: { stream: EventSource; payloads: string[] } }
    const ready = Promise.withResolvers<void>()
    const stream = new EventSource('/api/intraday/stream')
    const payloads: string[] = []
    stream.addEventListener('stream_ready', () => ready.resolve())
    stream.addEventListener('error', () => ready.reject(new Error('root SSE did not connect')))
    stream.addEventListener('advanced_progress', event => payloads.push(event.data))
    target.phase4Sse = { stream, payloads }
    await ready.promise
  })
}

async function stopRootSse(page: Page) {
  return page.evaluate(() => {
    const target = globalThis as typeof globalThis & { phase4Sse?: { stream: EventSource; payloads: string[] } }
    const payloads = target.phase4Sse?.payloads ?? []
    target.phase4Sse?.stream.close()
    delete target.phase4Sse
    return payloads
  })
}

test.beforeAll(async ({}, testInfo) => {
  testInfo.setTimeout(90_000)
  const root = resolve(import.meta.dirname, '../..')
  const fixtureDir = await mkdtemp(join(tmpdir(), 'phase4-fastapi-fixture-'))
  const dataDir = await mkdtemp(join(tmpdir(), 'phase4-fastapi-data-'))
  const advancedFixtureDir = await mkdtemp(join(tmpdir(), 'phase4-advanced-fixture-'))
  const advancedFixture = join(advancedFixtureDir, 'advanced-host-fixture.json')
  const daily = fixtureBars('600000.SH', '2023-07-03', '2024-07-15', 7)
  const indexDaily = fixtureBars('000300.SH', '2023-07-03', '2024-07-15', 3_500)
  await writeFile(join(fixtureDir, 'instruments.json'), JSON.stringify({ instruments: [{ symbol: '600000.SH', name: '浦发银行', code: '600000', exchange: 'SH' }] }))
  await writeFile(join(fixtureDir, 'market-data.json'), JSON.stringify({
    daily,
    index_daily: indexDaily,
    adjustment_factors: daily.map(bar => ({ symbol: '600000.SH', trade_date: bar.date, adj_factor: 1 })),
    financials: [{ symbol: '600000.SH', report_date: '2023-09-30', roe: 0.09 }],
  }))
  await writeFile(advancedFixture, JSON.stringify({
    policy: {
      version: 'advanced_policy_v1',
      source_profiles: { 'operator-research-v1': { market_scopes: ['CN-A'] } },
      benchmark_defaults: { stock: '000300.SH', etf: '000300.SH', index: '000001.SH' },
      benchmark_overrides: ['000300.SH', '000905.SH', '000852.SH'],
      agent_allowlist: { research_draft: ['CN-A'], experiment: ['CN-A'], strategy_evaluation: ['CN-A'] },
      rate_limits: { research_draft: 1, experiment: 1, strategy_evaluation: 1 },
    },
    advanced_subjects: ['600000.SH'],
    runner_wall_clock_seconds: 120,
    revoke_before_run_task_types: ['strategy_evaluation'],
    research_asset_binding: {
      strategy_id: 'bullish_alignment',
      name: 'Host bullish alignment asset',
      expression: 'close',
      description: 'Lifecycle-owned immutable research asset for the installed strategy.',
      hypothesis: 'The installed strategy resolves only through its persisted immutable lifecycle binding.',
      provenance: { fixture: 'phase4-host', version: 'v1' },
    },
    fixture_readiness: {
      benchmark_symbol: '000300.SH',
      symbols: ['600000.SH'],
      required_coverage: { start: '2023-07-03', end: '2024-07-15' },
      evaluation_windows: [20, 60, 120],
      strategy: { id: 'bullish_alignment', warmup_trading_days: 60 },
      aggregate_coverage: { start: '2023-07-03', end: '2024-07-15' },
      in_sample: { start: '2024-01-02', end: '2024-03-29' },
      out_of_sample: { start: '2024-04-01', end: '2024-06-28' },
    },
  }))
  await chmod(join(fixtureDir, 'instruments.json'), 0o444)
  await chmod(join(fixtureDir, 'market-data.json'), 0o444)
  await chmod(advancedFixture, 0o444)
  await chmod(fixtureDir, 0o555)
  host = spawn('uv', ['run', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '3018'], {
    cwd: join(root, 'backend'),
    env: { ...process.env, AUTH_PASSWORD: password, DATA_DIR: dataDir, PHASE1_FIXTURE_MODE: '1', PHASE1_FIXTURE_DIR: fixtureDir, ADVANCED_HOST_FIXTURE: advancedFixture },
    stdio: 'pipe',
  })
  host.stdout?.on('data', chunk => { hostOutput += String(chunk) })
  host.stderr?.on('data', chunk => { hostOutput += String(chunk) })
  await waitForHost()
})

test.afterAll(() => host?.kill('SIGTERM'))

test('real host visibly preserves immutable viewpoint lineage, correction, evaluation, calibration, viewport evidence, job audit, and root SSE', async ({ page }) => {
  await login(page)
  const bootstrap = await sameOriginRequest(page, '/api/advanced/viewpoints', 'POST', {
    source_profile: 'operator-research-v1', market_scope: 'CN-A', asset_type: 'stock', instrument: '600000.SH', published_at: '2024-01-02T00:00:00+00:00', direction: 'bullish', conclusion: '受控初始观点', rating: 'overweight', target_range: [7, 9], horizon_days: 60, confidence: 'high', evidence: [{ id: 'filing-1' }], evaluation_window_days: 60, benchmark: '000300.SH',
  })
  expect(bootstrap.status).toBe(200)
  await selectFixtureStock(page)
  await page.getByRole('button', { name: '添加修订' }).click()
  await page.getByLabel('修订结论').fill('新的材料要求将观点改为谨慎。')
  await page.getByLabel('修订方向').selectOption('bearish')
  await page.getByRole('button', { name: '保存修订' }).click()
  await expect(page.getByText('材料立场变化').first()).toBeVisible()
  await page.getByRole('button', { name: '添加更正' }).click()
  await page.getByLabel('更正原因').fill('修正单位说明。')
  await page.getByRole('button', { name: '保存更正' }).click()
  await expect(page.getByText('更正版本：修正单位说明。').first()).toBeVisible()
  await page.getByRole('button', { name: '运行服务端评估' }).click()
  await expect(page.getByRole('status').filter({ hasText: '已由服务端完成评估' })).toBeVisible()
  await expect(page.getByText(/60 个交易日，000300.SH/)).toBeVisible()
  await expect(page.getByText('置信度校准', { exact: true })).toBeVisible()
  for (const viewport of [{ width: 1440, height: 960 }, { width: 1024, height: 900 }, { width: 375, height: 844 }]) {
    await page.setViewportSize(viewport)
    const tableRegions = page.locator('[aria-describedby$="scroll-instruction"]')
    await expect(tableRegions).toHaveCount(2)
    for (const region of await tableRegions.all()) {
      await expect(region).toContainText('左右滚动查看完整记录')
      if (viewport.width === 375) expect(await region.evaluate(element => element.scrollWidth > element.clientWidth)).toBeTruthy()
    }
    if (viewport.width === 375) {
      const box = await page.getByRole('button', { name: '添加修订' }).boundingBox()
      expect(box?.height).toBeGreaterThanOrEqual(44)
    }
  }
  await startRootSse(page)
  await page.getByRole('button', { name: '启动受限研究任务' }).click()
  await expect(page.getByRole('status').filter({ hasText: /已记录|等待人工复核/ })).toBeVisible()
  const payloads = (await stopRootSse(page)).map(JSON.parse)
  expect(payloads).toContainEqual(expect.objectContaining({ subject_key: '600000.SH', audit_reference: expect.any(String) }))
})

test('real host visibly resolves the immutable binding, completes research feedback to five gates, promotion, and sandbox capability branch', async ({ page }) => {
  await login(page, '/backtest')
  await page.getByRole('button', { name: '均线多头', exact: true }).click()
  await expect(page.getByText('服务器解析的研究资产')).toBeVisible()
  await expect(page.getByLabel('服务器策略 ID')).toHaveText('bullish_alignment')
  await page.getByLabel('假设').fill('使用生命周期绑定的均线多头策略评估受控样本。')
  await page.getByLabel('开始日期').fill('2024-01-02')
  await page.getByLabel('结束日期').fill('2024-06-28')
  await page.getByLabel('标的代码（可选，逗号分隔）').fill('600000.SH')
  await page.getByLabel('参数（可选 JSON）').fill('{"require_ma_alignment":true}')
  await page.getByRole('button', { name: '新建实验规格' }).click()
  await expect(page.getByText(/不可变规格 v1/)).toBeVisible()
  await page.getByRole('button', { name: '运行受限实验' }).click()
  await expect(page.getByRole('status').filter({ hasText: '已完成' })).toBeVisible({ timeout: 140_000 })
  await page.getByRole('radio', { name: '支持' }).check()
  await page.getByLabel(/反馈说明/).fill('完成的受控运行支持该研究假设。')
  await page.getByRole('button', { name: '记录研究反馈' }).click()
  await expect(page.getByText('此运行未完成或已有反馈，不能记录新的研究反馈。')).toBeVisible()
  await page.getByRole('button', { name: '创建演化候选' }).click()
  for (const label of ['合同/沙箱安全', '来源完整性', '样本内与样本外', '稳健性', '成本与可实现性']) {
    await page.getByRole('button', { name: `评估门禁：${label}` }).click()
  }
  await expect(page.getByRole('button', { name: '批准晋级为研究策略' })).toBeEnabled()
  const promotionTrigger = page.getByRole('button', { name: '批准晋级为研究策略' })
  for (const viewport of [{ width: 1440, height: 960 }, { width: 1024, height: 900 }, { width: 375, height: 844 }]) {
    await page.setViewportSize(viewport)
    const tableRegions = page.locator('[aria-describedby="experiment-runs-scroll-instruction"], [aria-describedby^="gate-scroll-instruction-"]')
    await expect(tableRegions).toHaveCount(2)
    for (const region of await tableRegions.all()) {
      await expect(region).toContainText('左右滚动查看完整记录')
      if (viewport.width === 375) expect(await region.evaluate(element => element.scrollWidth > element.clientWidth)).toBeTruthy()
    }
    if (viewport.width === 375) {
      const box = await page.getByRole('button', { name: '新建实验规格' }).boundingBox()
      expect(box?.height).toBeGreaterThanOrEqual(44)
    }
    await expect(page.getByRole('status').filter({ hasText: '已完成' })).toBeVisible()
    await expect(page.getByRole('alert')).toHaveCount(0)
    await promotionTrigger.click()
    const dialog = page.getByRole('dialog', { name: '确认晋级为研究策略' })
    const rationale = page.getByLabel('批准理由（至少 10 个字符）')
    const confirm = dialog.getByRole('button', { name: '确认晋级为研究策略' })
    await expect(rationale).toBeFocused()
    await rationale.fill('三种真实主机视口均完成键盘焦点契约验证。')
    await confirm.focus()
    await page.keyboard.press('Tab')
    await expect(rationale).toBeFocused()
    await page.keyboard.press('Shift+Tab')
    await expect(confirm).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(promotionTrigger).toBeFocused()
  }
  const sandboxSource = "def run(panel):\n    return {'signal': 'hold'}\n"
  const sandboxSourceHash = createHash('sha256').update(sandboxSource).digest('hex')
  const sandboxRunsBefore = await sameOriginRequest(page, '/api/advanced/sandbox/runs')
  expect(sandboxRunsBefore.status).toBe(200)
  const existingSandboxRunIds = new Set((sandboxRunsBefore.body.runs as Array<{ run_id: string }>).map(run => run.run_id))
  const submissionResponsePromise = page.waitForResponse(response =>
    new URL(response.url()).pathname === '/api/advanced/sandbox/submissions' && response.request().method() === 'POST'
  )
  await page.getByLabel('受限策略源码').fill(sandboxSource)
  await page.getByRole('button', { name: '验证并运行受限策略' }).click()
  const submissionResponse = await submissionResponsePromise
  expect(submissionResponse.status()).toBe(200)
  const submissionPayload = submissionResponse.request().postDataJSON() as { source: string; contract: { source_sha256: string } }
  expect(submissionPayload).toMatchObject({ source: sandboxSource, contract: { source_sha256: sandboxSourceHash } })
  const submission = await submissionResponse.json() as {
    validation?: { status: string; reason: string; source_sha256: string }
    run?: { run_id: string }
  }
  if (submission.validation) {
    capabilityBranch = 'isolation_unavailable_fail_closed'
    expect(submission.validation).toEqual({
      status: 'rejected',
      reason: 'isolation_unavailable',
      source_sha256: sandboxSourceHash,
      audit_reference: expect.any(String),
    })
    await expect(page.getByRole('alert').filter({ hasText: 'isolation_unavailable' })).toBeVisible()
    const sandboxRunsAfter = await sameOriginRequest(page, '/api/advanced/sandbox/runs')
    expect(sandboxRunsAfter.status).toBe(200)
    expect((sandboxRunsAfter.body.runs as Array<{ run_id: string }>).filter(run => !existingSandboxRunIds.has(run.run_id))).toEqual([])
  } else {
    const runId = submission.run?.run_id
    expect(runId).toEqual(expect.any(String))
    if (!runId) throw new Error('sandbox submission did not return a terminal run identity')
    capabilityBranch = 'affirmative_isolation_proved'
    await expect.poll(async () => {
      const run = await sameOriginRequest(page, `/api/advanced/sandbox/runs/${encodeURIComponent(runId)}`)
      return run.status === 200 ? run.body.run : null
    }, { timeout: 60_000 }).toMatchObject({ run_id: runId, status: 'completed' })
  }
  console.log(`Phase 4 host capability branch: ${capabilityBranch}`)
  await page.getByRole('button', { name: '批准晋级为研究策略' }).click()
  await page.getByLabel('批准理由（至少 10 个字符）').fill('五项独立门禁均已由服务器完成审阅。')
  await page.getByRole('button', { name: '确认晋级为研究策略' }).click()
  await expect(page.getByText(/registered_research_only/)).toBeVisible()
  for (const viewport of [{ width: 1440, height: 960 }, { width: 1024, height: 900 }, { width: 375, height: 844 }]) {
    await page.setViewportSize(viewport)
    const strategyTab = page.getByRole('tab', { name: '策略回测' })
    await strategyTab.focus()
    await page.keyboard.press('ArrowRight')
    await expect(page.getByRole('tab', { name: '参数优化' })).toBeFocused()
    await page.keyboard.press('ArrowLeft')
    await expect(strategyTab).toBeFocused()
  }
})

test('real host denies unauthenticated, out-of-scope, rate-limited, and revoked jobs without unauthorized SSE work', async ({ page }) => {
  await page.goto('/')
  const unauthenticated = await sameOriginRequest(page, '/api/advanced/subjects/600000.SH/jobs', 'POST', { task_type: 'research_draft' })
  expect(unauthenticated.status).toBe(401)
  await login(page)
  await selectFixtureStock(page)
  await startRootSse(page)
  const outOfScope = await sameOriginRequest(page, '/api/advanced/subjects/000001.SZ/jobs', 'POST', { task_type: 'research_draft' })
  expect(outOfScope.status).toBe(404)
  // Revocation consumes only the strategy-evaluation quota; it must not emit work.
  const revoked = await sameOriginRequest(page, '/api/advanced/subjects/600000.SH/jobs', 'POST', { task_type: 'strategy_evaluation' })
  expect(revoked.status).toBe(200)
  expect(revoked.body.job).toMatchObject({ status: 'rejected', stage: 'rejected' })
  const payloads = (await stopRootSse(page)).map(JSON.parse)
  expect(payloads.filter(event => event.stage !== 'rejected')).toEqual([])
  const independent = await sameOriginRequest(page, '/api/advanced/subjects/600000.SH/jobs', 'POST', { task_type: 'research_draft' })
  expect(independent.status).toBe(200)
  const rateLimited = await sameOriginRequest(page, '/api/advanced/subjects/600000.SH/jobs', 'POST', { task_type: 'research_draft' })
  expect(rateLimited.status).toBe(409)
  const audit = await sameOriginRequest(page, `/api/advanced/audits/${revoked.body.job.audit_reference}`)
  expect(audit.body.audit).toMatchObject({ decision: 'rejected', reason: 'authorization_revoked' })
})
