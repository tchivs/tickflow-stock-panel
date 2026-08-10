import { spawn, type ChildProcess } from 'node:child_process'
import { chmod, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { expect, test as base } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'
const MOBILE_PROJECT = 'mobile-chromium-320'
const FIXTURE_SYMBOL = '600519.SH'
const FIXTURE_NAME = '贵州茅台'
const FRESHNESS_LABEL = /实时 · \d{2}:\d{2}:\d{2}|收盘 · \d{4}-\d{2}-\d{2}|报价可能已过期 · \d{2}:\d{2}:\d{2}|暂无法估值/

// 与 phase4 host spec 同款 self-spawn 模式: 本 spec 需要一个「未配置密码 + fixture 数据」的真实后端。
// 停用 docker 后端亦可, 本 harness 完全自足 (独立端口), 不依赖外部服务。
const backendPort = Number(process.env.PHASE1_BACKEND_PORT ?? 3032)
const backendUrl = `http://127.0.0.1:${backendPort}`
const frontendPort = Number(process.env.PHASE1_BROWSER_PORT ?? 4182)
const frontendUrl = `http://127.0.0.1:${frontendPort}`
let host: ChildProcess | undefined
let frontend: ChildProcess | undefined
let hostOutput = ''
let frontendOutput = ''

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
      const close = baseline + (businessDay % 9) * 0.4
      const date = cursor.toISOString().slice(0, 10)
      // D-17 契约: quote_ts 必须在 Asia/Shanghai 交易时段内 (09:30 = UTC 01:30)。
      const quote_ts = cursor.getTime() + 5_400_000
      bars.push({ symbol, date, open: close - 0.15, high: close + 0.35, low: close - 0.4, close, volume: 3_000_000, amount: 3_000_000 * close, quote_ts })
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

// worker-scoped custom fixture: 与 beforeAll 等价, 但 codemod 只匹配 `test.beforeAll`,
// 对 fixture 定义免疫 — 不会再把空解构改写成非法的 `_fixtures` 破坏套件加载。
const test = base.extend<{ phase1RealHostStack: void }>({
      phase1RealHostStack: [async ({}, use, workerInfo) => {
  const root = resolve(import.meta.dirname, '../..')
  const fixtureDir = await mkdtemp(join(tmpdir(), 'phase1-fixture-'))
  const dataDir = await mkdtemp(join(tmpdir(), 'phase1-data-'))
  const today = new Date().toISOString().slice(0, 10)
  const start = new Date(Date.now() - 90 * 86_400_000).toISOString().slice(0, 10)
  await writeFile(join(fixtureDir, 'instruments.json'), JSON.stringify({ instruments: [{ symbol: FIXTURE_SYMBOL, name: FIXTURE_NAME, code: '600519', exchange: 'SH' }] }))
  await writeFile(join(fixtureDir, 'market-data.json'), JSON.stringify({
    daily: fixtureBars(FIXTURE_SYMBOL, start, today, 1600),
    index_daily: [],
    adjustment_factors: [{ symbol: FIXTURE_SYMBOL, trade_date: '2024-01-01', adj_factor: 1 }],
    financials: [{ symbol: FIXTURE_SYMBOL, report_date: '2024-06-30', roe: 0.25 }],
  }))
  await chmod(join(fixtureDir, 'instruments.json'), 0o444)
  await chmod(join(fixtureDir, 'market-data.json'), 0o444)
  await chmod(fixtureDir, 0o555)
  host = spawn(join(root, 'backend', '.venv', 'bin', 'uvicorn'), ['app.main:app', '--host', '127.0.0.1', '--port', String(backendPort)], {
    cwd: join(root, 'backend'),
    env: {
      ...process.env,
      DATA_DIR: dataDir,
      PORT: String(frontendPort), // origin 信任: _LOCAL_AUTHORITIES 含 127.0.0.1:{settings.port}
      PHASE1_FIXTURE_MODE: '1',
      PHASE1_FIXTURE_DIR: fixtureDir,
      // 不设 AUTH_PASSWORD → 未初始化模式, 可信本机 origin 免登录。
      AUTH_PASSWORD: '',
      // 测试/fixture 模式: 禁用外部 provider 探测 (TickFlow 能力 / stock-sdk), 后端确定性快速 ready。
      TICKFLOW_API_KEY: '',
      STOCK_SDK_NODE: '/nonexistent-node',
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
  // 预置一条触发记录 (monitor 投递状态按钮依赖它)。直接写 operational DB, 确定性。
  const seedScript = [
    'import os',
    'from datetime import datetime, timezone',
    'from pathlib import Path',
    'from app.operational.repository import OperationalRepository',
    'repo = OperationalRepository(Path(os.environ["DATA_DIR"]) / "operational.db")',
    'repo.migrate()',
    'now = datetime.now(timezone.utc).isoformat()',
    'ev = repo.record_alert_event({',
    '  "id": "phase1-fixture-alert", "rule_id": "phase1-fixture-rule", "source": "price",',
    '  "type": "price", "symbol": "600519.SH", "name": "贵州茅台", "price": 1500.0,',
    '  "change_pct": 0.01, "severity": "warn",',
    '  "conditions": [{"kind": "threshold", "symbol": "600519.SH", "op": "gt", "value": 100}],',
    '  "occurred_at": now,',
    '})',
    'repo.create_delivery_outcome(event_id="phase1-fixture-alert", channel="feishu", status="sent", error=None)',
    'repo.create_delivery_outcome(event_id="phase1-fixture-alert", channel="telegram", status="sent", error=None)',
  ]
  if (workerInfo.project.name === MOBILE_PROJECT) {
    // mobile 测试依赖预置持仓卡; desktop 测试需零持仓走「空态 → 添加持仓」流程, 不能预置。
    seedScript.push(
      'acc = repo.create_account(name="预置账户", available_funds=20000)',
      'repo.create_position(account_id=acc["id"], instrument_symbol="600519.SH", cost_price=1500, quantity=2, invested_amount=3000, trading_style="swing")',
    )
  }
  seedScript.push('print("seeded")')
  const scriptBody = seedScript.join('\n')
  await new Promise<void>((resolveSeed, rejectSeed) => {
    const seed = spawn(join(root, 'backend', '.venv', 'bin', 'python'), ['-c', scriptBody], {
      cwd: join(root, 'backend'),
      env: { ...process.env, DATA_DIR: dataDir },
      stdio: 'pipe',
    })
    let seedOut = ''
    seed.stdout?.on('data', chunk => { seedOut += String(chunk) })
    seed.stderr?.on('data', chunk => { seedOut += String(chunk) })
    seed.on('exit', code => {
      if (code === 0 && seedOut.includes('seeded')) resolveSeed()
      else rejectSeed(new Error(`alert seed failed (${code}): ${seedOut.slice(-2_000)}`))
    })
    seed.on('error', rejectSeed)
  })
  await use()
  frontend?.kill('SIGTERM')
  host?.kill('SIGTERM')
  await sleep(600)
  frontend?.kill('SIGKILL')
  host?.kill('SIGKILL')
  }, { scope: 'worker' }],
})

test.setTimeout(180_000)
test.use({ baseURL: frontendUrl })

test.describe('Phase 1 isolated investor workflow', () => {
  test('desktop investor creates a holding and reviews delivery status', async ({ page, phase1RealHostStack }, testInfo) => {
    void phase1RealHostStack
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')

    await page.goto('/portfolio')
    await expect(page.getByRole('heading', { name: '投资组合' })).toBeVisible()

    await page.getByRole('button', { name: '新建账户' }).click()
    const accountDialog = page.getByRole('dialog', { name: '新建账户' })
    await accountDialog.getByLabel('账户名称').fill('验收账户')
    await accountDialog.getByLabel('可用资金').fill('20000')
    await accountDialog.getByRole('button', { name: '保存账户' }).click()
    await expect(accountDialog).toBeHidden()

    await page.getByLabel('账户与持仓').getByRole('button', { name: '添加持仓' }).click()
    const holdingDialog = page.getByRole('dialog', { name: '添加持仓' })
    await holdingDialog.getByLabel('账户').selectOption({ label: '验收账户' })
    await holdingDialog.getByRole('combobox', { name: '标的搜索' }).fill(FIXTURE_SYMBOL)
    await holdingDialog.getByRole('option', { name: new RegExp(`${FIXTURE_SYMBOL}|${FIXTURE_NAME}`) }).click()
    await holdingDialog.getByLabel('成本价').fill('1500')
    await holdingDialog.getByLabel('数量').fill('2')
    await holdingDialog.getByLabel('投入金额').fill('3000')
    await holdingDialog.getByLabel('交易风格').selectOption({ label: '波段' })
    await holdingDialog.getByRole('button', { name: '保存持仓' }).click()
    await expect(holdingDialog).toBeHidden()

    const holdingRow = page.getByRole('row', { name: new RegExp(`${FIXTURE_SYMBOL}|${FIXTURE_NAME}`) })
    await expect(holdingRow).toBeVisible()
    await expect(page.getByRole('region', { name: '投资组合汇总' }).getByText('未实现盈亏', { exact: true })).toBeVisible()
    await expect(page.getByText(FRESHNESS_LABEL).first()).toBeVisible()

    await page.getByRole('link', { name: '监控中心' }).click()
    await expect(page).toHaveURL(/\/monitor$/)
    const alertHistory = page.getByRole('region', { name: '触发记录' })
    const deliveryStatus = alertHistory.getByRole('button', { name: /待投递|已发送|投递失败|已跳过/ }).first()
    await expect(deliveryStatus).toBeVisible()
    await deliveryStatus.click()
    const deliveryDialog = page.getByRole('dialog', { name: '投递结果' })
    await expect(deliveryDialog.getByText(/Feishu|Telegram/)).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(deliveryDialog).toBeHidden()

  })

  test('mobile investor uses the shared drawer with compact, overflow-safe operational views', async ({ page, phase1RealHostStack }, testInfo) => {
    void phase1RealHostStack
    test.skip(testInfo.project.name !== MOBILE_PROJECT, 'mobile-only workflow')

    await page.goto('/portfolio')
    const menuButton = page.getByRole('button', { name: '打开导航菜单' })
    await expect(menuButton).toBeVisible()
    await menuButton.click()

    const drawer = page.getByRole('dialog', { name: '主导航' })
    await expect(drawer.getByRole('link', { name: '投资组合' })).toBeVisible()
    await drawer.getByRole('link', { name: '投资组合' }).click()
    await expect(page).toHaveURL(/\/portfolio$/)

    const holdingCard = page.getByRole('article', { name: new RegExp(`${FIXTURE_SYMBOL}|${FIXTURE_NAME}`) }).first()
    await expect(holdingCard).toBeVisible()
    await expect(holdingCard.getByText('未实现盈亏', { exact: true })).toBeVisible()
    await expect(holdingCard.getByText(FRESHNESS_LABEL)).toBeVisible()

    const addHolding = page.getByRole('button', { name: '添加持仓' })
    const addHoldingBox = await addHolding.boundingBox()
    expect(addHoldingBox?.height).toBeGreaterThanOrEqual(44)
    expect(addHoldingBox?.width).toBeGreaterThanOrEqual(44)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()

    await menuButton.click()
    await page.getByRole('dialog', { name: '主导航' }).getByRole('link', { name: '监控中心' }).click()
    await expect(page).toHaveURL(/\/monitor$/)

    const alertHistory = page.getByRole('region', { name: '触发记录' })
    const rules = page.getByRole('region', { name: '监控规则' })
    await expect(alertHistory).toBeVisible()
    await expect(rules).toBeVisible()
    const [historyBox, rulesBox] = await Promise.all([alertHistory.boundingBox(), rules.boundingBox()])
    expect(historyBox?.y).toBeLessThan(rulesBox?.y ?? Number.POSITIVE_INFINITY)
    await expect(page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy()
  })
})
