import { defineConfig } from '@playwright/test'
export default defineConfig({
  testDir: './tests/browser', fullyParallel: false, workers: 1,
  use: { baseURL: 'http://127.0.0.1:4179', viewport: { width: 1440, height: 1100 },
    launchOptions: { args: ['--enable-unsafe-swiftshader'] }, trace: 'retain-on-failure' },
  webServer: { command: 'npm run preview -- --port 4179 --strictPort', url: 'http://127.0.0.1:4179', reuseExistingServer: !process.env.CI },
})
