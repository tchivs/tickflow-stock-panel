import { defineConfig } from '@playwright/test'

const baseURL = process.env.PHASE1_BASE_URL ?? 'http://127.0.0.1:4173'

export default defineConfig({
  testDir: './e2e',
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
  },
  webServer: process.env.PHASE1_BASE_URL ? undefined : {
    command: 'pnpm exec vite --host 127.0.0.1 --port 4173',
    url: baseURL,
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    {
      name: 'desktop-chromium',
      use: {
        browserName: 'chromium',
        viewport: { width: 1440, height: 960 },
      },
    },
    {
      name: 'mobile-chromium-320',
      use: {
        browserName: 'chromium',
        viewport: { width: 320, height: 800 },
        deviceScaleFactor: 1,
        hasTouch: true,
        isMobile: true,
      },
    },
    {
      name: 'phase4-fastapi-host',
      use: {
        browserName: 'chromium',
        viewport: { width: 1440, height: 960 },
      },
    },
  ],
})
