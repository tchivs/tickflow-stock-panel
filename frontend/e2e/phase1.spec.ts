import { expect, test } from '@playwright/test'

const DESKTOP_PROJECT = 'desktop-chromium'
const MOBILE_PROJECT = 'mobile-chromium-320'
const FIXTURE_SYMBOL = '600519.SH'
const FIXTURE_NAME = '贵州茅台'
const FRESHNESS_LABEL = /实时 · \d{2}:\d{2}:\d{2}|收盘 · \d{4}-\d{2}-\d{2}|报价可能已过期 · \d{2}:\d{2}:\d{2}|暂无法估值/


test.describe('Phase 1 isolated investor workflow', () => {
  test('desktop investor creates a holding, reviews delivery status, and replays a decision', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== DESKTOP_PROJECT, 'desktop-only workflow')

    await page.goto('/portfolio')
    await expect(page.getByRole('heading', { name: '投资组合' })).toBeVisible()

    await page.getByRole('button', { name: '新建账户' }).click()
    const accountDialog = page.getByRole('dialog', { name: '新建账户' })
    await accountDialog.getByLabel('账户名称').fill('验收账户')
    await accountDialog.getByLabel('可用资金').fill('20000')
    await accountDialog.getByRole('button', { name: '保存账户' }).click()
    await expect(accountDialog).toBeHidden()

    await page.getByRole('button', { name: '添加持仓' }).click()
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
    await expect(page.getByText('未实现盈亏', { exact: true })).toBeVisible()
    await expect(page.getByText(FRESHNESS_LABEL).first()).toBeVisible()

    await page.getByRole('link', { name: '监控中心' }).click()
    await expect(page).toHaveURL(/\/monitor$/)
    await page.getByRole('button', { name: '新建规则' }).click()
    const ruleDialog = page.getByRole('dialog', { name: '新建规则' })
    await ruleDialog.getByLabel('规则类型').selectOption('position')
    await ruleDialog.getByRole('checkbox', { name: new RegExp(`${FIXTURE_SYMBOL}.*${FIXTURE_NAME}|${FIXTURE_NAME}.*${FIXTURE_SYMBOL}`) }).check()
    await ruleDialog.getByRole('button', { name: '保存规则' }).click()
    await expect(ruleDialog).toBeHidden()

    const alertHistory = page.getByRole('region', { name: '触发记录' })
    await expect(alertHistory.getByText(FIXTURE_SYMBOL)).toBeVisible()
    const deliveryStatus = alertHistory.getByRole('button', { name: /待投递|已发送|投递失败|已跳过/ }).first()
    await expect(deliveryStatus).toBeVisible()
    await deliveryStatus.click()
    const deliveryDialog = page.getByRole('dialog', { name: '投递结果' })
    await expect(deliveryDialog.getByText(/Feishu|Telegram/)).toBeVisible()

    await page.getByRole('link', { name: '看板' }).click()
    await page.getByRole('button', { name: '查看决策计划' }).click()
    const playbookDialog = page.getByRole('dialog', { name: '决策计划' })
    await expect(playbookDialog.getByText('确定性基线', { exact: true })).toBeVisible()
    await expect(playbookDialog.getByText('最终计划', { exact: true })).toBeVisible()
    await playbookDialog.getByLabel('数据截至').selectOption({ index: 1 })
    await playbookDialog.getByRole('button', { name: '历史回放' }).click()
    await expect(playbookDialog.getByText('正在以历史数据回放；AI 已禁用')).toBeVisible()
    await expect(playbookDialog.getByText(/回放时间|结果哈希/)).toBeVisible()
  })

  test('mobile investor uses the shared drawer with compact, overflow-safe operational views', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== MOBILE_PROJECT, 'mobile-only workflow')

    await page.goto('/portfolio')
    const menuButton = page.getByRole('button', { name: '打开导航菜单' })
    await expect(menuButton).toBeVisible()
    await menuButton.click()

    const drawer = page.getByRole('dialog', { name: '主导航' })
    await expect(drawer.getByRole('link', { name: '投资组合' })).toBeVisible()
    await drawer.getByRole('link', { name: '投资组合' }).click()
    await expect(page).toHaveURL(/\/portfolio$/)

    const holdingCard = page.getByRole('article', { name: new RegExp(`${FIXTURE_SYMBOL}|${FIXTURE_NAME}`) })
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
