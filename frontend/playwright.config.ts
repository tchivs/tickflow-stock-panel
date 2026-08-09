import { defineConfig } from '@playwright/test'

const baseURL = process.env.PHASE1_BASE_URL ?? 'http://127.0.0.1:4173'

export default defineConfig({
  testDir: '.',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL,
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
    launchOptions: {
      args: ['--disable-features=HttpsFirstBalancedModeAutoEnable,HttpsUpgrades'],
    },
  },
  webServer: process.env.PHASE1_BASE_URL ? undefined : {
    command: 'node ./node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4173 --strictPort',
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: 'desktop-chromium',
      testMatch: /e2e\/.*\.spec\.ts/,
      use: {
        browserName: 'chromium',
        viewport: { width: 1440, height: 960 },
      },
    },
    {
      name: 'mobile-chromium-320',
      testMatch: /e2e\/.*\.spec\.ts/,
      use: {
        browserName: 'chromium',
        viewport: { width: 320, height: 800 },
        deviceScaleFactor: 1,
        hasTouch: true,
        isMobile: true,
      },
    },
    {
      name: 'visual-desktop',
      testMatch: /visual-regression\.spec\.ts/,
      use: {
        browserName: 'chromium',
        viewport: { width: 1440, height: 960 },
      },
    },
    {
      name: 'visual-mobile-375',
      testMatch: /visual-regression\.spec\.ts/,
      use: {
        browserName: 'chromium',
        viewport: { width: 375, height: 812 },
        deviceScaleFactor: 2,
        hasTouch: true,
        isMobile: true,
      },
    },
    {
      name: 'phase4-fastapi-host',
      testMatch: /e2e\/.*\.spec\.ts/,
      use: {
        baseURL: 'http://127.0.0.1:4173',
        browserName: 'chromium',
        viewport: { width: 1440, height: 960 },
      },
    },
  ],
})
