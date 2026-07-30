/**
 * Phase 9: Visual regression baselines for critical investor workflows.
 *
 * Captures committed baseline screenshots at desktop (1440×960) and mobile
 * (375×812) viewports. A regression run fails when unintended UI drift is
 * detected against the committed baselines.
 *
 * Run: npx playwright test visual-regression.spec.ts --update-snapshots  (first time)
 *      npx playwright test visual-regression.spec.ts                     (regression check)
 */
import { test, expect } from '@playwright/test'
import { promises as fs } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)
const BASELINE_DIR = join(__dirname, 'visual-baselines')

// Ensure the baseline directory exists for the first run.
test.beforeAll(async () => {
  await fs.mkdir(BASELINE_DIR, { recursive: true })
})

// Desktop visual regression — 1440×960 (visual-desktop project).
test.describe('desktop visual regression @1440', () => {
  test.skip(({ browserName }) => browserName !== 'chromium', 'desktop chromium only')
  test.skip(({ viewport }) => (viewport?.width ?? 0) < 1000, 'desktop viewport only')

  test('dashboard renders without drift', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveScreenshot('desktop-dashboard.png', {
      maxDiffPixelRatio: 0.01,
      threshold: 0.2,
    })
  })

  test('watchlist renders without drift', async ({ page }) => {
    await page.goto('/watchlist')
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveScreenshot('desktop-watchlist.png', {
      maxDiffPixelRatio: 0.01,
      threshold: 0.2,
    })
  })
})

// Mobile visual regression — 375px responsive breakpoint (visual-mobile-375 project).
test.describe('mobile visual regression @375', () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) > 500, 'mobile viewport only')

  test('dashboard renders without drift at 375px', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveScreenshot('mobile-dashboard.png', {
      maxDiffPixelRatio: 0.01,
      threshold: 0.2,
    })
  })

  test('watchlist renders without drift at 375px', async ({ page }) => {
    await page.goto('/watchlist')
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveScreenshot('mobile-watchlist.png', {
      maxDiffPixelRatio: 0.01,
      threshold: 0.2,
    })
  })
})
