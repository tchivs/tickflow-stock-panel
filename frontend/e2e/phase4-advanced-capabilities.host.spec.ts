import { spawn, type ChildProcess } from 'node:child_process'
import { mkdtemp, chmod, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { expect, test } from '@playwright/test'

const hostUrl = 'http://127.0.0.1:3018'
let host: ChildProcess | undefined

test.setTimeout(60_000)

async function waitForHost(): Promise<void> {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    try {
      if ((await fetch(`${hostUrl}/health`)).ok) return
    } catch {
      // The actual FastAPI lifespan is still initializing.
    }
    await new Promise(resolve => setTimeout(resolve, 250))
  }
  throw new Error('real FastAPI host did not become ready')
}

test.beforeAll(async () => {
  const root = resolve(import.meta.dirname, '../..')
  const fixtureDir = await mkdtemp(join(tmpdir(), 'phase4-fastapi-fixture-'))
  const dataDir = await mkdtemp(join(tmpdir(), 'phase4-fastapi-data-'))
  await writeFile(join(fixtureDir, 'instruments.json'), JSON.stringify({
    instruments: [{ symbol: '600000.SH', name: '浦发银行', code: '600000', exchange: 'SH' }],
  }))
  await writeFile(join(fixtureDir, 'market-data.json'), JSON.stringify({
    daily: [{ symbol: '600000.SH', date: '2024-01-02', open: 7.1, high: 7.3, low: 7.05, close: 7.25, volume: 1000, amount: 7250, quote_ts: 1704180600000 }],
    adjustment_factors: [{ symbol: '600000.SH', trade_date: '2024-01-02', adj_factor: 1 }],
    financials: [{ symbol: '600000.SH', report_date: '2023-09-30', roe: 0.09 }],
  }))
  await chmod(join(fixtureDir, 'instruments.json'), 0o444)
  await chmod(join(fixtureDir, 'market-data.json'), 0o444)
  await chmod(fixtureDir, 0o555)
  host = spawn('uv', ['run', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '3018'], {
    cwd: join(root, 'backend'),
    env: {
      ...process.env,
      AUTH_PASSWORD: 'phase4-host-password',
      DATA_DIR: dataDir,
      PHASE1_FIXTURE_MODE: '1',
      PHASE1_FIXTURE_DIR: fixtureDir,
    },
    stdio: 'pipe',
  })
  await waitForHost()
})

test.afterAll(() => host?.kill('SIGTERM'))

test('real FastAPI host accepts an authorized advanced job and emits root SSE progress', async ({ page }) => {
  const denied = await page.request.post(`${hostUrl}/api/advanced/subjects/600000.SH/jobs`, {
    data: { task_type: 'research_draft' },
  })
  expect(denied.status()).toBe(401)

  const login = await page.request.post(`${hostUrl}/api/auth/login`, { data: { password: 'phase4-host-password' } })
  expect(login.ok()).toBeTruthy()
  await page.goto('/stock-analysis')

  const result = await page.evaluate(async () => {
    const stream = new EventSource('/api/intraday/stream')
    const payloads: string[] = []
    const opened = new Promise<void>((resolve, reject) => {
      stream.addEventListener('stream_ready', () => resolve())
      stream.addEventListener('error', () => reject(new Error('root SSE did not connect')))
    })
    stream.addEventListener('advanced_progress', message => payloads.push(message.data))
    await opened
    const response = await fetch('/api/advanced/subjects/600000.SH/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_type: 'research_draft' }),
    })
    const body = await response.json()
    await new Promise(resolve => window.setTimeout(resolve, 250))
    stream.close()
    return { status: response.status, body, payloads }
  })

  expect(result.status).toBe(200)
  expect(result.body.job.audit_reference).toBeTruthy()
  const finalEvent = result.payloads.map(JSON.parse).find(event => (
    event.job_id === result.body.job.id && event.stage === result.body.job.stage
  ))
  expect(finalEvent).toMatchObject({
    job_id: result.body.job.id,
    stage: result.body.job.stage,
    audit_reference: result.body.job.audit_reference,
  })
})

test('real FastAPI host rejects unauthenticated, out-of-scope, and rate-limited advanced jobs before work', async ({ page }) => {
  const unauthenticated = await page.request.post(`${hostUrl}/api/advanced/subjects/600000.SH/jobs`, {
    data: { task_type: 'research_draft' },
  })
  expect(unauthenticated.status()).toBe(401)

  const login = await page.request.post(`${hostUrl}/api/auth/login`, { data: { password: 'phase4-host-password' } })
  expect(login.ok()).toBeTruthy()

  const outOfScope = await page.request.post(`${hostUrl}/api/advanced/subjects/000001.SZ/jobs`, {
    data: { task_type: 'research_draft' },
  })
  expect(outOfScope.status()).toBe(404)

  const allowed = await page.request.post(`${hostUrl}/api/advanced/subjects/600000.SH/jobs`, {
    data: { task_type: 'research_draft' },
  })
  expect(allowed.ok()).toBeTruthy()
  const rateLimited = await page.request.post(`${hostUrl}/api/advanced/subjects/600000.SH/jobs`, {
    data: { task_type: 'research_draft' },
  })
  expect(rateLimited.status()).toBe(409)
  expect(await rateLimited.json()).toEqual({ detail: 'advanced job rejected' })
})
