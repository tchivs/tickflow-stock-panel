import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { expect, test, type Page, type Request } from '@playwright/test'

/**
 * CR-01 real-host primary node.
 * Title must appear exactly once and remain the 05-29 selector.
 * No page.route / browserContext.route for /api/shadow/**.
 * No repository-ID handoff from app.state.shadow_repository.
 */

const SHADOW_HEADING = 'Shadow 成交证据与策略候选'
const password = process.env.PHASE5_REAL_HOST_PASSWORD ?? 'phase5-real-host-password'
const browserUrl = 'http://127.0.0.1:4175'

test.setTimeout(240_000)

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
