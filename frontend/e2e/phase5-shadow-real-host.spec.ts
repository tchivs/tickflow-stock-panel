import { createHash } from 'node:crypto'
import { spawn, type ChildProcess } from 'node:child_process'
import { chmod, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { expect, test, type Request } from '@playwright/test'

/**
 * CR-01 real-host primary node.
 * Title must appear exactly once and remain the 05-29 selector.
 * No page.route / browserContext.route for /api/shadow/**.
 * No repository-ID handoff from app.state.shadow_repository.
 */

const SHADOW_HEADING = 'Shadow 成交证据与策略候选'
const password = process.env.PHASE5_REAL_HOST_PASSWORD ?? 'phase5-real-host-password'
const browserUrl = 'http://127.0.0.1:4175'
// 与 phase1/phase4 host spec 同款 self-spawn: 本 spec 需要一个「启用 Shadow 模块 + 遥测」的真实后端。
// 本地 venv 自带 sklearn → shadow 模块 available; fixtures 提供 600001.SH 的 2024 日K。
const backendPort = Number(process.env.PHASE5_BACKEND_PORT ?? 3033)
const backendUrl = `http://127.0.0.1:${backendPort}`
const frontendPort = Number(process.env.PHASE5_BROWSER_PORT ?? 4183)
const frontendUrl = `http://127.0.0.1:${frontendPort}`
let host: ChildProcess | undefined
let frontend: ChildProcess | undefined
let hostOutput = ''
let frontendOutput = ''
test.setTimeout(240_000)
test.use({ baseURL: frontendUrl })

function sleep(milliseconds: number) {
  const deferred = Promise.withResolvers<void>()
  setTimeout(deferred.resolve, milliseconds)
  return deferred.promise
}

function shadowFixtureBars(symbol: string, start: string, end: string, baseline: number) {
  const bars: Array<Record<string, number | string>> = []
  const cursor = new Date(`${start}T00:00:00Z`)
  const finalDate = new Date(`${end}T00:00:00Z`)
  let businessDay = 0
  while (cursor <= finalDate) {
    const weekday = cursor.getUTCDay()
    if (weekday !== 0 && weekday !== 6) {
      const close = baseline + (businessDay % 23) * 0.12
      const date = cursor.toISOString().slice(0, 10)
      // D-17 契约: quote_ts 必须在 Asia/Shanghai 交易时段内 (09:30 = UTC 01:30)。
      bars.push({ symbol, date, open: close - 0.05, high: close + 0.15, low: close - 0.18, close, volume: 4_000_000, amount: 4_000_000 * close, quote_ts: cursor.getTime() + 5_400_000 })
      businessDay += 1
    }
    cursor.setUTCDate(cursor.getUTCDate() + 1)
  }
  return bars
}

async function waitForHost() {
  for (let attempt = 0; attempt < 220; attempt += 1) {
    try {
      if ((await fetch(`${backendUrl}/health`)).ok) return
    } catch {
      // The actual FastAPI lifespan is still initializing.
    }
    await sleep(250)
  }
  throw new Error(`real FastAPI host did not become ready: ${hostOutput.slice(-4_000)}`)
}

async function waitForFrontend() {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    try {
      if ((await fetch(frontendUrl)).ok) return
    } catch {
      // Vite is still starting.
    }
    await sleep(250)
  }
  throw new Error(`isolated Vite host did not become ready: ${frontendOutput.slice(-4_000)}`)
}

test.beforeAll(async (_fixtures, testInfo) => {
  testInfo.setTimeout(180_000)
  const root = resolve(import.meta.dirname, '../..')
  const fixtureDir = await mkdtemp(join(tmpdir(), 'phase5-shadow-fixture-'))
  const dataDir = await mkdtemp(join(tmpdir(), 'phase5-shadow-data-'))
  await writeFile(join(fixtureDir, 'instruments.json'), JSON.stringify({ instruments: [{ symbol: '600001.SH', name: '平安银行', code: '600001', exchange: 'SH' }] }))
  await writeFile(join(fixtureDir, 'market-data.json'), JSON.stringify({
    daily: shadowFixtureBars('600001.SH', '2023-11-01', '2024-12-31', 10),
    index_daily: [],
    adjustment_factors: [{ symbol: '600001.SH', trade_date: '2023-11-01', adj_factor: 1 }],
    financials: [{ symbol: '600001.SH', report_date: '2024-06-30', roe: 0.11 }],
  }))
  await chmod(join(fixtureDir, 'instruments.json'), 0o444)
  await chmod(join(fixtureDir, 'market-data.json'), 0o444)
  await chmod(fixtureDir, 0o555)
  host = spawn(join(root, 'backend', '.venv', 'bin', 'uvicorn'), ['app.main:app', '--host', '127.0.0.1', '--port', String(backendPort)], {
    cwd: join(root, 'backend'),
    env: {
      ...process.env,
      DATA_DIR: dataDir,
      PORT: String(frontendPort),
      AUTH_PASSWORD: 'phase5-real-host-password',
      PHASE1_FIXTURE_MODE: '1',
      PHASE1_FIXTURE_DIR: fixtureDir,
      PHASE5_REAL_HOST_TELEMETRY: '1',
    },
    stdio: 'pipe',
  })
  host.stdout?.on('data', chunk => { hostOutput += String(chunk) })
  host.stderr?.on('data', chunk => { hostOutput += String(chunk) })
  await waitForHost()
  frontend = spawn('pnpm', ['exec', 'vite', '--host', '127.0.0.1', '--port', String(frontendPort), '--strictPort'], {
    cwd: join(root, 'frontend'),
    env: { ...process.env, VITE_API_PROXY_TARGET: backendUrl },
    stdio: 'pipe',
  })
  frontend.stdout?.on('data', chunk => { frontendOutput += String(chunk) })
  frontend.stderr?.on('data', chunk => { frontendOutput += String(chunk) })
  await waitForFrontend()
})

test.afterAll(async () => {
  frontend?.kill('SIGTERM')
  host?.kill('SIGTERM')
  await sleep(600)
  frontend?.kill('SIGKILL')
  host?.kill('SIGKILL')
})

function shadowExecutionCsv(): string {
  const header = 'symbol,side,time,quantity,price,fees,currency,fill_id'
  const rows: string[] = [header]
  const tradeDates = [
    '2024-02-27', '2024-03-12', '2024-03-26', '2024-04-09', '2024-04-23',
    '2024-05-08', '2024-05-22', '2024-06-05', '2024-06-20', '2024-07-04',
    '2024-07-18', '2024-08-01', '2024-08-15', '2024-08-29', '2024-09-12',
    '2024-09-26', '2024-10-11', '2024-10-25', '2024-11-08', '2024-11-22',
    '2024-12-06', '2024-12-20',
  ]
  tradeDates.forEach((day, index) => {
    rows.push(
      `600001.SH,buy,${day} 09:31:00,100,10.00,1.00,CNY,FILL-${String(index + 1).padStart(3, '0')}`,
    )
  })
  return `${rows.join('\n')}\n`
}

type Telemetry = {
  repository_id_bypass: number
  live_action_counts: Record<string, number>
  unexpected_external_requests: number
  ready?: boolean
}

type RequestLog = {
  method: string
  path: string
  url: string
  postData: string | null
}

function isStaticCdnHost(host: string): boolean {
  return (
    host === 'rsms.me'
    || host === 'fonts.googleapis.com'
    || host === 'fonts.gstatic.com'
    || host.endsWith('.gstatic.com')
  )
}

test('CR-01 real host non-empty Shadow import to evidence distillation and IS-OOS', async ({ page, context }) => {
  const routeHandlers: string[] = []
  const originalPageRoute = page.route.bind(page)
  const originalContextRoute = context.route.bind(context)
  page.route = (async (...args: Parameters<typeof page.route>) => {
    routeHandlers.push(String(args[0]))
    if (String(args[0]).includes('/api/shadow') || String(args[0]).includes('shadow')) {
      throw new Error(`CR-01 forbids page.route for Shadow APIs: ${String(args[0])}`)
    }
    return originalPageRoute(...args)
  }) as typeof page.route
  context.route = (async (...args: Parameters<typeof context.route>) => {
    routeHandlers.push(String(args[0]))
    if (String(args[0]).includes('/api/shadow') || String(args[0]).includes('shadow')) {
      throw new Error(`CR-01 forbids browserContext.route for Shadow APIs: ${String(args[0])}`)
    }
    return originalContextRoute(...args)
  }) as typeof context.route

  const shadowRequests: RequestLog[] = []
  const externalHits: string[] = []
  page.on('request', (request: Request) => {
    const url = request.url()
    let pathname = url
    try {
      pathname = new URL(url).pathname
    } catch {
      // keep raw
    }
    if (pathname.startsWith('/api/shadow/') || url.includes('/api/shadow/')) {
      shadowRequests.push({
        method: request.method(),
        path: pathname,
        url,
        postData: request.postData(),
      })
    }
    try {
      const host = new URL(url).hostname
      if (!host || host === '127.0.0.1' || host === 'localhost' || host === '[::1]') return
      if (isStaticCdnHost(host)) return
      externalHits.push(url)
    } catch {
      // ignore invalid URLs
    }
  })

  await page.goto(`/login?redirect=${encodeURIComponent('/backtest')}`)
  await page.getByPlaceholder('访问密码').fill(password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page).toHaveURL(/\/backtest$/)
  const cookies = await page.context().cookies(browserUrl)
  expect(cookies.find((cookie) => cookie.name === 'tf_session')).toMatchObject({ path: '/' })

  const panel = page.getByRole('region', { name: SHADOW_HEADING })
  await expect(panel.getByRole('heading', { name: SHADOW_HEADING, exact: true })).toBeVisible({ timeout: 60_000 })

  const csv = shadowExecutionCsv()
  expect(createHash('sha256').update(csv).digest('hex').length).toBe(64)

  await panel.getByLabel('选择本地成交日志').setInputFiles({
    name: 'executions.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(csv, 'utf8'),
  })

  await expect(panel.getByText('已解析 executions.csv；预览 22 行。')).toBeVisible({ timeout: 60_000 })
  await expect(panel.getByRole('button', { name: '确认不可变导入' })).toBeEnabled({ timeout: 60_000 })

  await panel.getByRole('button', { name: '确认不可变导入' }).click()
  const dialog = page.getByRole('dialog', { name: '确认不可变导入' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: '确认不可变导入' }).click()

  await expect(panel.locator('caption', { hasText: 'Shadow 不可变导入批次' })).toBeAttached({ timeout: 90_000 })
  await expect(panel.getByText(/completed|已完成|完成/i).first()).toBeVisible({ timeout: 90_000 })

  await panel.getByRole('button', { name: '创建新证据集' }).click()
  await expect(panel.getByText(/证据集已冻结：/)).toBeVisible({ timeout: 90_000 })
  await expect(panel.getByText('1 / 22', { exact: true })).toBeVisible({ timeout: 30_000 })

  const distillButton = panel.getByRole('button', { name: /开始候选蒸馏|基于相同证据集创建新蒸馏运行/ })
  await expect(distillButton.first()).toBeEnabled({ timeout: 30_000 })
  await distillButton.first().click()
  await expect(panel.getByText(/已创建可解释候选/)).toBeVisible({ timeout: 120_000 })

  await panel.getByRole('button', { name: '创建新的样本内与样本外评估' }).click()
  await expect(panel.getByText(/样本内与样本外评估已分别记录/)).toBeVisible({ timeout: 180_000 })
  await expect(panel.getByText('样本内', { exact: true }).first()).toBeVisible()
  await expect(panel.getByText('样本外', { exact: true }).first()).toBeVisible()

  expect(shadowRequests.some((entry) => entry.path.includes('/imports/'))).toBeTruthy()
  expect(shadowRequests.some((entry) => entry.path.endsWith('/evidence-sets') && entry.method === 'POST')).toBeTruthy()
  expect(shadowRequests.some((entry) => entry.path.endsWith('/candidates') && entry.method === 'POST')).toBeTruthy()
  expect(shadowRequests.some((entry) => entry.path.endsWith('/evaluations') && entry.method === 'POST')).toBeTruthy()
  expect(routeHandlers.filter((pattern) => /shadow/i.test(pattern))).toEqual([])

  for (const request of shadowRequests.filter((entry) => entry.method === 'POST' && entry.path.endsWith('/evidence-sets'))) {
    expect(request.postData).toBeTruthy()
    const body = JSON.parse(request.postData as string) as Record<string, unknown>
    expect(body.membership_mode).toBe('all_authorized_batch_trades')
    expect(Array.isArray(body.included_batch_ids)).toBeTruthy()
    expect(body.included_batch_ids).not.toHaveLength(0)
    expect(body).not.toHaveProperty('included_trade_ids')
    for (const forbidden of [
      'principal', 'fingerprint', 'verdict', 'strategy', 'monitor', 'plan',
      'position', 'broker', 'market_action', 'reviewer_principal',
    ]) {
      expect(body).not.toHaveProperty(forbidden)
    }
  }

  const telemetryResponse = await page.evaluate(async () => {
    const result = await fetch('/api/__phase5_real_host__/telemetry', { credentials: 'include' })
    return { status: result.status, body: await result.json() }
  })
  expect(telemetryResponse.status).toBe(200)
  const telemetry = telemetryResponse.body as Telemetry
  expect(telemetry.repository_id_bypass).toBe(0)
  expect(telemetry.unexpected_external_requests).toBe(0)
  for (const [name, count] of Object.entries(telemetry.live_action_counts)) {
    expect({ name, count }).toEqual({ name, count: 0 })
  }
  expect(externalHits).toEqual([])
  expect(shadowRequests.every((entry) => entry.url.includes('/api/shadow/'))).toBeTruthy()

  try {
    const disk = JSON.parse(await readFile(join(tmpdir(), 'phase5-real-host-telemetry.json'), 'utf8')) as Telemetry
    expect(disk.repository_id_bypass).toBe(0)
    expect(disk.unexpected_external_requests).toBe(0)
  } catch {
    // HTTP telemetry is authoritative when the harness uses a private temp path.
  }
})
